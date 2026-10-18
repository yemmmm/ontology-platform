"""DSH v3 acceptance children using the existing packet, proxy and report sink.

The 031 transport supplies only SDK events, namespace loading and process control.
No production roster, capability, Team transport or Codex app-server is started.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from ..acceptance_runtime import (
    AcceptanceBatchPacket,
    CQ_ACCEPTANCE_PLATFORM_ROLE,
    ExaminerRuntimeBlocked,
    ReportSinkServer,
    ScopedReadProxy,
    V3BatchReportContract,
    _packet_canonical,
    _unfreeze_packet,
    v3_examiner_proxy_schemas,
    v3_proxy_scope_entries,
    v3_ticket_digest,
)
from ..deepseek_provider_proxy import read_deepseek_credential
from ..messages_provider_proxy import MessagesProviderSession
from ..model_routing import preflight_profile_credentials
from ..read_proxy_mcp import _v3_child_tool_schema
from ..report_sink_mcp import native_report_tool_specs
from .acceptance import validate_acceptance_profile
from .acceptance_inputs import _v3_acceptance_first_turn_text
from .base import RuntimeDelivery
from .dsh import DshRuntimeAdapter, DshRuntimeError, _DshAgent
from .dsh_build import digest, freeze_build
from .dsh_events import DispatchProjection


class DshAcceptanceChild:
    runtime = "dsh"
    thread_id = None

    def __init__(self, adapter, packet, reports, private_root, evidence_root):
        self.adapter, self.packet = adapter, packet
        self.submitted_reports = reports
        self.evidence_root = evidence_root
        self.spec = {"private_root": str(private_root), "_packet": packet, "v3_role": packet.role}
        self.proxy = self.report_sink = self.agent = None
        self.destroyed = self.task_closed = self.user_waiting = False
        self._watchdog_stop = threading.Event()
        self._report_lock = threading.RLock()
        self._reports_open = True
        self._first_failure = None

    @property
    def process(self):
        return self.agent.process if self.agent else None

    @property
    def identity(self):
        return {
            "runtime": "dsh",
            "runtime_session_id": self.agent.session_id if self.agent else None,
            "process_instance": self.agent.instance if self.agent else self.evidence_root.name,
        }

    @property
    def terminal_event(self):
        if not self.agent:
            return False
        projection = self.agent.projection
        return (
            not projection.gap
            and not projection.conflict
            and projection.activity is None
            and bool(self.agent.dispatches)
            and all(
                r["state"] in {"settled", "canceled", "failed"}
                for r in self.adapter.transport.dispatch_status(self.agent.agent_id)
            )
        )

    def accept(self, report):
        with self._report_lock:
            if not self._reports_open:
                raise ValueError(
                    "report session closed; retained conversation cannot alter the report"
                )
            self.adapter.transport._record(
                "reports",
                {
                    **self.identity,
                    "packet_digest": self.packet.canonical_digest,
                    "accepted_index": len(self.submitted_reports) + 1,
                    "report_digest": hashlib.sha256(_packet_canonical(report)).hexdigest(),
                },
            )
            self.submitted_reports.append(dict(report))

    def close_reports(self):
        # The callback and closure share a lock. stop joins an in-flight handler;
        # accepted reports remain fixed even if its response is lost.
        with self._report_lock:
            self._reports_open = False
        if self.report_sink:
            self.report_sink.stop()

    def control(self, message):
        action = message["action"]
        transport = self.adapter.transport
        if action in {"pause", "resume"}:
            groups = getattr(transport, action)()
            self.user_waiting = action == "pause"
            return {"status": "effective", **self.identity, "groups": groups}
        if self.user_waiting:
            raise DshRuntimeError("session paused; resume the original process before consultation")
        text = json.dumps(
            {
                **message,
                "instruction": "只读追问；原报告固定，禁止重新提交或覆盖，不改变原批次结果。",
            },
            ensure_ascii=False,
        )
        receipt = transport.send_message(
            self.agent.agent_id,
            RuntimeDelivery("user/outer", self.agent.agent_id, "user-control", text),
        )
        return {
            "status": "instruction_delivered",
            **self.identity,
            "dispatch": dataclasses.asdict(receipt),
        }

    def messages(self):
        return self.adapter.transport.receive_messages()

    def failure_evidence(self):
        if self.destroyed:
            return self._first_failure
        if self._first_failure is not None:
            return self._first_failure
        failures = self.adapter.transport.consume_runtime_failures()
        if failures:
            self._first_failure = failures[0][1]
        elif self.agent and self.agent.wait:
            self._first_failure = {"category": "runtime/infrastructure", **self.agent.wait}
        elif self.process and self.process.poll() is not None:
            self._first_failure = {
                "category": "runtime/infrastructure",
                "reason_code": "child-exited",
            }
        return self._first_failure

    def destroy(self):
        if self.destroyed:
            return
        self.close_reports()
        self.adapter.transport.stop()
        if self.proxy:
            self.proxy.destroy()
        # Keep native history and startup/partial failure originals Host-private.
        root = Path(self.spec["private_root"])
        if root.exists():
            if (root / "home" / "sessions").exists():
                shutil.copytree(
                    root / "home" / "sessions", self.evidence_root / "sessions", dirs_exist_ok=True
                )
            if (root / "stderr.log").exists():
                shutil.copyfile(root / "stderr.log", self.evidence_root / "stderr.log")
        cleanup = self.adapter.transport.cleanup_identifiers()
        if not cleanup.get("complete"):
            raise DshRuntimeError(
                "acceptance-cleanup-incomplete: inspect retained cleanup evidence"
            )
        shutil.rmtree(root)
        self.destroyed = True


class DshAcceptanceRuntime:
    runtime = "dsh"

    def __init__(
        self, *, repository_root, harness_root=None, provider_factory=MessagesProviderSession
    ):
        self.root = Path(repository_root)
        self.transport = DshRuntimeAdapter(
            repository_root=self.root, harness_root=harness_root, provider_factory=provider_factory
        )
        self._run_root = None
        self.profile = None
        self.resource = None

    def bind_acceptance_model_profile(self, profile):
        validate_acceptance_profile("dsh", profile, judge=False)
        self.profile = profile

    def _stop_standalone_provider_sessions(self):
        # Each child owns and stops its provider through transport.stop().
        pass

    def launch_v3_acceptance_child(
        self,
        packet,
        *,
        role_instructions,
        reports,
        read_key=None,
        platform_forwarder=None,
        timeout_seconds=300,
        ontology_ids=None,
        response_persistence=None,
    ):
        if not isinstance(packet, AcceptanceBatchPacket):
            raise DshRuntimeError(
                "acceptance-input: v3 packet required", category="platform-contract"
            )
        platform = packet.role == CQ_ACCEPTANCE_PLATFORM_ROLE
        validate_acceptance_profile("dsh", self.profile, judge=not platform)
        if platform and (not read_key or not callable(platform_forwarder)):
            raise DshRuntimeError(
                "acceptance-input: platform read key/forwarder required",
                category="platform-contract",
            )
        if platform:
            scope = list(packet.payload["authorized_scope"])
            if (
                not ontology_ids
                or set(ontology_ids) != set(scope)
                or any(not isinstance(v, str) or not v for v in ontology_ids.values())
            ):
                raise DshRuntimeError(
                    "acceptance-input: incomplete ontology_ids", category="platform-contract"
                )
        if not role_instructions or not isinstance(reports, list):
            raise DshRuntimeError(
                "acceptance-input: role instructions/report list required",
                category="platform-contract",
            )
        if self.resource and not self.resource.destroyed:
            raise DshRuntimeError("original child still owned; no implicit replacement session")
        instance = uuid.uuid4().hex
        evidence_root = (
            Path(self._run_root or tempfile.mkdtemp(prefix="dsh-acceptance-evidence-"))
            / "acceptance-runtime"
            / instance
        )
        evidence_root.mkdir(parents=True, mode=0o700)
        private = Path(tempfile.mkdtemp(prefix="r4333-"))
        if self.resource is not None:
            previous = self.transport
            self.transport = DshRuntimeAdapter(
                repository_root=self.root,
                harness_root=previous.harness_root,
                provider_factory=previous.provider_factory,
            )
        child = self.resource = DshAcceptanceChild(self, packet, reports, private, evidence_root)
        transport = self.transport
        transport._run = SimpleNamespace(root=evidence_root)
        transport._closed = transport._paused = False
        transport.agents.clear()
        try:
            transport._build = freeze_build(transport.harness_root)
            role = "platform-examiner" if platform else "acceptance"
            binding = self.profile.bindings[role]
            credential = bytearray(
                read_deepseek_credential(
                    preflight_profile_credentials(
                        dataclasses.replace(self.profile, bindings={role: binding})
                    )["deepseek-official"]
                )
            )
            try:
                transport._provider = transport.provider_factory(
                    credential, on_attempt=lambda event: transport._record("provider", event)
                )
            finally:
                credential[:] = b"\0" * len(credential)
            transport._provider.start()
            home, work, skills = (private / name for name in ("home", "work", "skills"))
            for folder in (home, work, skills):
                folder.mkdir(mode=0o700)
            input_path = home / "input.json"
            input_path.write_bytes(_packet_canonical(_unfreeze_packet(packet.payload)))
            input_path.chmod(0o400)
            package = SimpleNamespace(role=role, runtime={"dsh": {"sandbox": "read-only"}})
            agent = child.agent = _DshAgent(
                role, package, private, "acceptance-" + instance, instance=instance
            )
            agent.projection = DispatchProjection(agent.session_id)
            transport.agents[role] = agent
            kind = "platform" if platform else "acceptance"
            sink = child.report_sink = ReportSinkServer(
                home / "report.sock",
                secrets.token_urlsafe(24),
                child.accept,
                kind=kind,
                batch_contract=V3BatchReportContract(role=packet.role, packet=packet),
                material_root=evidence_root / "handoff-materials",
                material_actor_id=kind,
                material_scope_id=instance,
                material_sources={"/agent/home/input.json": input_path},
                material_host_sources={"/packet": input_path},
            )
            publication = sink.handoff_materials.publish("host", kind, "/packet")
            sink.start()
            report_args = [
                "/agent/home/report_sink_mcp.py",
                "--stdio",
                "--kind",
                kind,
                "--socket",
                "/agent/home/report.sock",
                "--token-file",
                "/agent/home/report.token",
                "--schema",
                sink.batch_contract.schema_version,
                "--batch-id",
                sink.batch_contract.batch_id,
                "--role",
                packet.role,
                "--question-ids",
                ",".join(sink.batch_contract.question_ids),
            ]
            if packet.source_registry is not None:
                report_args.append("--frozen-evidence-reads")
            (home / "report.token").write_text(sink.token)
            (home / "report.token").chmod(0o400)
            servers = [{"serverName": "examiner_report", "args": report_args, "env": {}}]
            agent.expected_tools = [
                ("examiner_report", tool)
                for tool in native_report_tool_specs(
                    kind,
                    v3_batch=True,
                    role=packet.role,
                    frozen_evidence_reads=packet.source_registry is not None,
                )
            ]
            if platform:
                schemas = v3_examiner_proxy_schemas(packet.payload["authorized_read_tools"])

                def response_material(result):
                    output = sink.handoff_materials.write_output(
                        "host",
                        "response-" + uuid.uuid4().hex + ".json",
                        json.dumps(result, ensure_ascii=False, sort_keys=True),
                    )
                    published = sink.handoff_materials.publish("host", kind, output["source_path"])
                    return {"material_id": published["material_id"]}

                child.proxy = ScopedReadProxy(
                    socket_path=home / "read.sock",
                    token=secrets.token_urlsafe(24),
                    read_key=read_key,
                    authorized_ontologies=v3_proxy_scope_entries(packet),
                    ticket_digest=v3_ticket_digest(packet.freeze_digest),
                    model_state_digest="0" * 64,
                    allowed_tools=list(schemas),
                    forward=platform_forwarder,
                    acceptance_round_id="r3011-" + packet.batch_id,
                    child_handle_digest=hashlib.sha256(instance.encode()).hexdigest(),
                    exact_schemas=schemas,
                    persist_response=response_persistence,
                    response_material=response_material,
                )
                child.proxy.start()
                (home / "read.token").write_text(child.proxy.token)
                (home / "read.token").chmod(0o400)
                servers.append(
                    {
                        "serverName": "platform_read_proxy",
                        "args": [
                            "/agent/home/read_proxy_mcp.py",
                            "--stdio",
                            "--socket",
                            "/agent/home/read.sock",
                            "--token-file",
                            "/agent/home/read.token",
                        ],
                        "env": {
                            "PLATFORM_PROXY_MODE": "v3-acceptance",
                            "PLATFORM_PROXY_TICKET_DIGEST": v3_ticket_digest(packet.freeze_digest),
                        },
                    }
                )
                listing = child.proxy.handle(
                    {"token": child.proxy.token, "operation": "tools/list"}
                )
                agent.expected_tools += [
                    ("platform_read_proxy", _v3_child_tool_schema(tool))
                    for tool in listing["schemas"]
                ]
            for name in ("read_proxy_mcp.py", "report_sink_mcp.py"):
                shutil.copyfile(self.root / "modeling_team" / name, home / name)
            assets = self.root / "modeling_team" / "agent-packages" / "v3-acceptance-batch"
            instructions = assets / ("platform-examiner.md" if platform else "acceptance-judge.md")
            skill = self.root / "modeling_team" / "skills" / "v3-acceptance-batch" / "SKILL.md"
            instructions_text = instructions.read_text() + "\n" + skill.read_text()
            entry = self.root / "modeling_team/runtimes/dsh_node/entry.mjs"
            shutil.copyfile(entry, home / "entry.mjs")
            config = {
                "modules": {
                    key: "/dsh/" + str(Path(path).relative_to(transport.harness_root))
                    for key, path in transport._build["modules"].items()
                },
                "providerURL": transport._provider.base_url,
                "instructions": instructions_text,
                "servers": servers,
            }
            (home / "dsh.json").write_text(json.dumps(config))
            transport._launch(agent)
            result = transport._rpc(
                agent,
                "initialize",
                {
                    "cwd": "/agent/work",
                    "provider": binding.provider_id,
                    "model": binding.model,
                    "reasoningEffort": binding.effective_effort,
                },
            )
            effective = result.get("effectiveBinding", {})
            if any(
                effective.get(key) != expected
                for key, expected in (
                    ("provider", binding.provider_id),
                    ("model", binding.model),
                    ("reasoningEffort", binding.effective_effort),
                )
            ):
                raise DshRuntimeError("dsh-model-binding-drift", category="platform-contract")
            inspection = transport._rpc(agent, "host/inspect", {})
            transport._check_tools(agent, inspection)
            agent.ready = True
            child.first_turn_text = _v3_acceptance_first_turn_text(packet, role_instructions) + (
                " Authorized handoff entries (optional; inline packet remains valid): "
                + json.dumps(
                    {
                        "input_ref": {"material_id": publication["material_id"]},
                        "frozen_evidence_ref": sink.frozen_material_ref,
                    }
                )
                + " Use list/read_handoff_material for contents. Use private write_handoff_output then "
                "publish_handoff_material to recipient host for report_ref. Frozen source receipts still apply."
            )
            transport._record(
                "baseline",
                {
                    **child.identity,
                    "packet_digest": packet.canonical_digest,
                    "build": transport._build,
                    "tools": inspection,
                    "model_profile": self.profile.as_dict(),
                    "requested_binding": binding.as_dict(),
                    "effective_binding": effective,
                    "composition_sha256": digest(entry),
                    "materials": {
                        str(p.relative_to(self.root)): digest(p) for p in (instructions, skill)
                    },
                    "first_input_sha256": hashlib.sha256(
                        child.first_turn_text.encode()
                    ).hexdigest(),
                },
            )
            return child
        except Exception as exc:
            child._first_failure = {
                "category": getattr(exc, "category", "runtime/infrastructure"),
                "reason_code": getattr(exc, "reason_code", "child-start-failed"),
                "detail": str(exc),
            }
            transport._record("startup-failure", child._first_failure)
            try:
                child.destroy()
            except Exception as cleanup_error:
                transport._record("cleanup-failure", {"detail": str(cleanup_error)})
            raise

    def run_v3_acceptance_child(
        self,
        packet,
        *,
        reports,
        teardown=None,
        examiner_observables=None,
        cooperative_owner=None,
        timeout_seconds=300,
        **kwargs,
    ):
        if cooperative_owner:
            cooperative_owner.before_next_task()
        previous_resource = self.resource
        try:
            child = self.launch_v3_acceptance_child(
                packet, reports=reports, timeout_seconds=timeout_seconds, **kwargs
            )
        except Exception:
            if (
                teardown is not None
                and self.resource is not None
                and self.resource is not previous_resource
            ):
                child = self.resource
                teardown.update(
                    **child.identity,
                    child_destroyed=child.destroyed,
                    private_root_removed=not Path(child.spec["private_root"]).exists(),
                    socket_root_removed=not Path(child.spec["private_root"]).exists(),
                    report_sink_stopped=child.report_sink is None
                    or child.report_sink._thread is None,
                    first_failure=child.failure_evidence(),
                    evidence_root=str(child.evidence_root),
                )
            raise
        complete = retained = False
        terminal_at = None
        cleanup_error = None
        try:
            if cooperative_owner:
                cooperative_owner.bind(self, child)
                cooperative_owner.before_next_task()
            while True:
                if cooperative_owner:
                    cooperative_owner.before_next_task()
                lock = cooperative_owner._lock if cooperative_owner else child._report_lock
                with lock:
                    if cooperative_owner and cooperative_owner.pending_pause:
                        continue
                    self.transport.send_message(
                        child.agent.agent_id,
                        RuntimeDelivery(
                            "host", child.agent.agent_id, "acceptance-task", child.first_turn_text
                        ),
                    )
                    break
            deadline = time.monotonic() + max(0.1, timeout_seconds)
            last_tick = time.monotonic()
            while True:
                if cooperative_owner:
                    cooperative_owner.poll()
                now = time.monotonic()
                if child.user_waiting:
                    deadline += now - last_tick
                last_tick = now
                # Sink acceptance precedes process failures: never discard an accepted answer.
                if child.report_sink.batch_contract.is_complete and not child.user_waiting:
                    if child.terminal_event or child.failure_evidence() or now >= deadline:
                        complete = True
                        return list(reports)
                failure = child.failure_evidence()
                if failure:
                    raise ExaminerRuntimeBlocked(
                        "runtime-infrastructure", role=packet.role, evidence=failure
                    )
                if child.terminal_event and not child.user_waiting:
                    terminal_at = terminal_at or now
                    if now - terminal_at >= 1:
                        raise ExaminerRuntimeBlocked(
                            "runtime-infrastructure",
                            role=packet.role,
                            evidence={"reason_code": "batch-incomplete", "reports": len(reports)},
                        )
                else:
                    terminal_at = None
                if now >= deadline:
                    raise ExaminerRuntimeBlocked(
                        "runtime-infrastructure",
                        role=packet.role,
                        evidence={"reason_code": "batch-incomplete", "reports": len(reports)},
                    )
                time.sleep(0.05)
        finally:
            if examiner_observables is not None:
                examiner_observables.update(
                    receipts=list(child.proxy.receipt_snapshot) if child.proxy else [],
                    persistence_failures=child.proxy.persistence_failures if child.proxy else 0,
                )
            try:
                safe_incomplete = (
                    not complete and child.terminal_event and not child.failure_evidence()
                )
                retained = (
                    (complete or safe_incomplete)
                    and packet.role == CQ_ACCEPTANCE_PLATFORM_ROLE
                    and cooperative_owner is not None
                    and not cooperative_owner.stopping
                    and child.process.poll() is None
                    and not child.failure_evidence()
                    and child.terminal_event
                )
                if retained:
                    child.blocked_task = not complete
                    child.close_reports()
                    cooperative_owner.retain(child)
                else:
                    child.destroy()
            except Exception as exc:
                cleanup_error = f"{type(exc).__name__}: {exc}"
            finally:
                if cooperative_owner and not retained:
                    cooperative_owner.release(child)
            if teardown is not None:
                teardown.update(
                    **child.identity,
                    child_destroyed=child.destroyed,
                    private_root_removed=not Path(child.spec["private_root"]).exists(),
                    report_sink_stopped=child.report_sink._thread is None,
                    proxy_destroyed=child.proxy._read_key is None if child.proxy else True,
                    socket_root_removed=not Path(child.spec["private_root"]).exists(),
                    consumer_retained=retained,
                    task_closed=True,
                    owner_pid=os.getpid() if retained else None,
                    child_alive=child.process.poll() is None if child.process else False,
                    first_failure=child.failure_evidence(),
                    evidence_root=str(child.evidence_root),
                    frozen_source_read_receipts=list(
                        child.report_sink.batch_contract.source_read_receipts
                    ),
                    report_ref_receipts=list(child.report_sink.report_ref_receipts),
                    native_usage=None,
                    usage_gap="unknown; raw DSH events retained for R4.3-034",
                )
                if cleanup_error:
                    teardown["destroy_error"] = cleanup_error
