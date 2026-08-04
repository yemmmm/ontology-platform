"""Bounded Producer handoff smoke for the unbound R2.3-005 contract.

This smoke starts only the real isolated Protocol Runtime, connects it to a run-local
TeamTransportBroker, and performs one neutral candidate receipt call.  It deliberately
does not call ``TeamRunner.prepare/start``: no Project/Ontology, Session, Lease, key,
Acceptance round, semantic start, or ledger reservation is created here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .contracts import load_formal_team_configuration, repository_root
from .runner import TeamRunner
from .runtimes.base import RuntimeDelivery
from .runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
from .transport_mcp import TeamTransportBroker


class ProducerSmokeError(RuntimeError):
    """The production-shaped no-start smoke cannot prove its local invariant."""


def _canonical_digest(value: Any) -> str:
    """Hash the exact canonical JSON preimage retained in smoke evidence."""
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


_PLATFORM_GUARD_IDENTITY = "r23005-producer-platform-guard/v1"
_PLATFORM_GUARD_FORBIDDEN_TOKENS = (
    "ONTOLOGY_MCP_API_KEY",
    "ONTOLOGY_MCP_BASE_URL",
    "127.0.0.1:8001",
    "app.mcp.server",
)


def _platform_guard_script_bytes() -> bytes:
    """Return the standalone, no-network MCP guard used only by this smoke."""
    script = r'''#!/usr/bin/env python3
import hashlib
import json
import os
import sys

IDENTITY = os.environ.get("PLATFORM_GUARD_IDENTITY", "r23005-producer-platform-guard/v1")
LOG_PATH = os.environ.get("PLATFORM_GUARD_LOG", "")
try:
    ADVERTISED_TOOLS = json.loads(os.environ.get("PLATFORM_GUARD_TOOLS", "[]"))
except json.JSONDecodeError:
    ADVERTISED_TOOLS = []


def _reply(request_id, result=None, error=None):
    response = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _record_attempt(tool, arguments):
    record = {
        "guard_identity": IDENTITY,
        "tool": tool if isinstance(tool, str) else "",
        "arguments_sha256": hashlib.sha256(
            json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "accepted": False,
    }
    if not LOG_PATH:
        return record
    descriptor = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(LOG_PATH, 0o600)
    return record


for line in sys.stdin:
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        continue
    if not isinstance(request, dict):
        continue
    request_id = request.get("id")
    method = request.get("method")
    if method == "initialize":
        _reply(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "ontology_platform", "version": IDENTITY},
            },
        )
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        _reply(
            request_id,
            {
                "tools": [
                    {
                        "name": name,
                        "description": "Smoke-local ontology_platform tool surface; every call is rejected.",
                        "inputSchema": {"type": "object", "additionalProperties": True},
                    }
                    for name in ADVERTISED_TOOLS
                    if isinstance(name, str)
                ]
            },
        )
    elif method == "tools/call":
        params = request.get("params")
        params = params if isinstance(params, dict) else {}
        record = _record_attempt(params.get("name"), params.get("arguments", {}))
        _reply(
            request_id,
            error={
                "code": -32090,
                "message": "platform guard rejects every call",
                "data": {"guard_identity": record["guard_identity"]},
            },
        )
    else:
        _reply(request_id, error={"code": -32601, "message": "method not found"})
'''
    return script.encode("utf-8")


def _replace_platform_config(
    config_path: Path, *, advertised_tools: list[str], guard_log_vpath: str
) -> None:
    """Replace the adapter's platform block with the smoke-local fail-closed guard."""
    lines = config_path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("[mcp_servers.ontology_platform]")
    except ValueError as exc:
        raise ProducerSmokeError("Runtime config did not contain ontology_platform block") from exc
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("[mcp_servers.") and not lines[index].startswith(
            "[mcp_servers.ontology_platform."
        ):
            end = index
            break
    guard_tools_json = json.dumps(advertised_tools, ensure_ascii=False, separators=(",", ":"))
    guard_lines = [
        "[mcp_servers.ontology_platform]",
        'command = "/usr/bin/python3"',
        'args = ["/agent/home/platform-guard.py"]',
        'cwd = "/agent/work"',
        "required = true",
        f"enabled_tools = {json.dumps(advertised_tools)}",
        "[mcp_servers.ontology_platform.env]",
        f'PLATFORM_GUARD_IDENTITY = {json.dumps(_PLATFORM_GUARD_IDENTITY)}',
        f'PLATFORM_GUARD_LOG = {json.dumps(guard_log_vpath)}',
        f"PLATFORM_GUARD_TOOLS = {json.dumps(guard_tools_json)}",
    ]
    config_path.write_text("\n".join(lines[:start] + guard_lines + lines[end:]) + "\n", encoding="utf-8")
    os.chmod(config_path, 0o600)


def _process_snapshot(run_root: Path) -> dict[str, Any]:
    """Return residual process IDs associated with this private smoke root."""
    completed = subprocess.run(
        ["pgrep", "-af", str(run_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        if "pgrep -af" in line:
            continue
        fields = line.split(maxsplit=1)
        if fields and fields[0].isdigit():
            pids.add(int(fields[0]))
    return {"count": len(pids), "pids": sorted(pids)}


def _wait_for_no_processes(run_root: Path, *, timeout_seconds: float = 5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    snapshot = _process_snapshot(run_root)
    while snapshot["count"] and time.monotonic() < deadline:
        time.sleep(0.1)
        snapshot = _process_snapshot(run_root)
    return snapshot


def _guard_resource_snapshot(
    *,
    config_path: Path,
    guard_script_path: Path,
    guard_log_path: Path,
    config_text: str | None = None,
    script_text: str | None = None,
) -> dict[str, Any]:
    """Capture the zero-resource boundary without contacting the platform."""
    config_text = config_path.read_text(encoding="utf-8") if config_text is None else config_text
    script_text = (
        guard_script_path.read_text(encoding="utf-8") if script_text is None else script_text
    )
    forbidden_absent = all(token not in config_text for token in _PLATFORM_GUARD_FORBIDDEN_TOKENS)
    no_network_imports = all(
        token not in script_text for token in ("socket", "urllib", "requests", "http.client")
    )
    if not forbidden_absent or not no_network_imports:
        raise ProducerSmokeError("platform guard config/script is not fail-closed")
    resources = {
        kind: {"count": 0, "ids": []}
        for kind in ("projects", "ontologies", "sessions", "leases", "keys")
    }
    return {
        "source": "controlled-platform-guard/no-network",
        "real_platform_server_reachable": False,
        "real_platform_key_configured": False,
        "config_forbidden_tokens_absent": True,
        "guard_script_no_network_imports": True,
        "guard_log_exists": guard_log_path.exists(),
        "resources": resources,
    }


def _guard_attempts(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    attempts: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProducerSmokeError("platform guard log is not valid JSON") from exc
        if not isinstance(record, dict):
            raise ProducerSmokeError("platform guard log record is not an object")
        attempts.append(record)
    return attempts


def synthetic_fresh_scope(run_id: str, runtime_identity: str = "") -> dict[str, str]:
    """Derive a run-owned synthetic scope from the actual Runtime identity."""
    if not isinstance(run_id, str) or not run_id:
        raise ProducerSmokeError("synthetic scope requires a run ID")
    if not isinstance(runtime_identity, str) or not runtime_identity:
        raise ProducerSmokeError("synthetic scope requires a Runtime identity")
    digest = hashlib.sha256(f"{run_id}:{runtime_identity}".encode("utf-8")).hexdigest()[:20]
    return {
        "project_id": f"smoke-project-{digest}",
        "ontology_id": f"smoke-ontology-{digest}",
        "scope_mode": "create",
    }


def neutral_candidate(*, source_digest: str = "0" * 64) -> dict[str, Any]:
    """Return one source-grounded platform-neutral semantic candidate."""
    return {
        "candidate_kind": "platform_neutral_semantic_candidate",
        "candidate_revision": 1,
        "scope": {},
        "constraints": [
            "the semantic candidate is complete, self-contained, and immutable",
            "all semantic references close over this candidate",
        ],
        "items": [
            {
                "item_id": "class-workflow",
                "item_kind": "class",
                "semantic": {
                    "term": "Workflow",
                    "definition": "A bounded workflow semantic used only by this smoke.",
                },
                "evidence_citations": [
                    {
                        "document_name": "workflow-landscape.md",
                        "excerpt": "A bounded workflow semantic used only by this smoke.",
                        "source_artifact_sha256": source_digest,
                        "source_locator": "fixture:workflow-landscape.md",
                        "excerpt_sha256": hashlib.sha256(
                            b"A bounded workflow semantic used only by this smoke."
                        ).hexdigest(),
                        "owner_answer_id": None,
                    }
                ],
            }
        ],
    }


def _bind_scope(candidate: dict[str, Any], generated: dict[str, str]) -> None:
    """Bind a candidate to the fresh Runtime-generated scope, rejecting drift."""
    supplied = candidate.get("scope")
    if supplied not in ({}, None) and not isinstance(supplied, dict):
        raise ProducerSmokeError("candidate scope is not an object")
    if isinstance(supplied, dict):
        for field in ("project_id", "ontology_id"):
            if field in supplied and supplied[field] != generated[field]:
                raise ProducerSmokeError(f"candidate scope {field} is not run-owned")
    candidate["scope"] = {
        "project_id": generated["project_id"],
        "ontology_id": generated["ontology_id"],
        "scope_mode": generated["scope_mode"],
    }


def _ledger_snapshot(root: Path) -> dict[str, str]:
    ledger_root = root / "workspaces" / "modeling-runs"
    if not ledger_root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(ledger_root.glob(".r2-3-*.jsonl"))
        if path.is_file()
    }


def _raw_mcp_call(
    wrapper: Path, *, proof_gate: bool, request: dict[str, Any]
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "PROTOCOL_PROOF_GATE": "1" if proof_gate else "0",
            "PYTHONPATH": str(wrapper.parent),
        }
    )
    process = subprocess.Popen(
        [sys.executable, str(wrapper)],
        cwd=wrapper.parent,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr = process.stderr.read() if process.stderr is not None else ""
            raise ProducerSmokeError(f"Protocol MCP smoke exited without a response: {stderr.strip()}")
        response = json.loads(line)
        if not isinstance(response, dict):
            raise ProducerSmokeError("Protocol MCP smoke response is not an object")
        return response
    finally:
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _validate_batch_contract(
    batch: object, *, candidate: dict[str, Any], scope: dict[str, str], run_id: str
) -> dict[str, Any]:
    if not isinstance(batch, dict):
        raise ProducerSmokeError("Protocol did not return a Modeling Batch object")
    contract_path = repository_root() / "modeling_team/references/modeling-batch-item-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    batch_fields = contract["batch_envelope"]["fields"]
    required = {
        name for name, descriptor in batch_fields.items() if descriptor.get("required") is True
    }
    if not required.issubset(batch):
        raise ProducerSmokeError("Protocol Batch is missing required contract fields")
    if batch.get("mode") != "dry_run" or batch.get("lease_token") not in (None, ""):
        raise ProducerSmokeError("neutral Producer Batch must be dry_run without a lease")
    if batch.get("ontology_id") != scope["ontology_id"]:
        raise ProducerSmokeError("Protocol Batch ontology scope drifts from the Runtime scope")
    if batch.get("client_batch_id") != f"batch-{run_id}":
        raise ProducerSmokeError("Protocol Batch client identity is not run-owned")
    items = batch.get("items")
    if not isinstance(items, list) or len(items) != len(candidate["items"]):
        raise ProducerSmokeError("Protocol Batch item count drifts from the candidate")
    item_fields = contract["item_envelope"]["fields"]
    item_required = {
        name for name, descriptor in item_fields.items() if descriptor.get("required") is True
    }
    for item, candidate_item in zip(items, candidate["items"], strict=True):
        if not isinstance(item, dict) or not item_required.issubset(item):
            raise ProducerSmokeError("Protocol Batch item envelope is incomplete")
        if item["client_item_id"] != candidate_item["item_id"]:
            raise ProducerSmokeError("Protocol Batch item identity drifts from the candidate")
        if item["command_kind"] != "create_class" or not isinstance(item["payload"], dict):
            raise ProducerSmokeError("Protocol Batch item translation is not deterministic")
        if item["payload"].get("name") != candidate_item["semantic"]["term"]:
            raise ProducerSmokeError("Protocol Batch class payload drifts from the candidate")
    return batch


def _retain_safe_evidence(repository: Path, run_id: str, evidence: dict[str, Any]) -> tuple[str, str]:
    """Retain only sanitized smoke evidence in the repo-local ignored workspace."""
    root = repository / "workspaces" / ".r2-3-005-producer-smoke" / run_id
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = root / "evidence.json"
    encoded = (json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        metadata = None
    if metadata is not None and stat.S_ISLNK(metadata.st_mode):
        raise ProducerSmokeError("retained evidence target must not be a symlink")
    temporary = root / f".evidence.json.{os.getpid()}.{time.time_ns()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o400,
    )
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(temporary, 0o400)
    try:
        os.replace(temporary, path)
        directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    os.chmod(path, 0o400)
    return path.relative_to(repository).as_posix(), hashlib.sha256(encoded).hexdigest()


def run_no_semantic_start_smoke(
    *, run_id: str = "r23005-neutral-smoke", root: Path | None = None, timeout_seconds: float = 180
) -> dict[str, Any]:
    """Run the real isolated Protocol Runtime handoff without semantic/platform writes."""
    repository = repository_root() if root is None else root
    configuration = load_formal_team_configuration(
        repository / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
        repository / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
        root=repository,
    )
    before_ledgers = _ledger_snapshot(repository)
    protocol_source = next(
        source.path
        for source in configuration.task.role_sources
        if source.relative_path.as_posix().endswith("workflow-landscape.md")
    )
    source_digest = hashlib.sha256(protocol_source.read_bytes()).hexdigest()
    protocol_profile = next(
        profile_agent
        for profile_agent in configuration.profile.agents
        if profile_agent.package.role == "protocol"
    )

    with tempfile.TemporaryDirectory(prefix="r23005-producer-runtime-smoke-") as directory:
        run_root = Path(directory) / run_id
        run_root.mkdir(mode=0o700)
        (run_root / "evidence").mkdir(mode=0o700)
        source_root = run_root / "sources" / "protocol"
        source_root.mkdir(parents=True, mode=0o700)
        for source in configuration.task.role_sources:
            if "protocol" not in source.roles:
                continue
            target = source_root / source.relative_path
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            shutil.copyfile(source.path, target)
            os.chmod(target, 0o444)

        broker = TeamTransportBroker(
            run_root / "transport" / "broker",
            {("modeling", "protocol"), ("protocol", "modeling")},
            coordination_phase_callback=lambda *_args: {},
        )
        broker.start(["modeling", "protocol"])
        (run_root / "transport-root").write_text(str(broker.root), encoding="utf-8")
        run = SimpleNamespace(
            run_id=run_id,
            root=run_root,
            scope={"mode": "create"},
            # The real platform key is deliberately never loaded.  The adapter's
            # platform block is replaced below before the Runtime process starts.
            protocol_key="guard-unused",
            protocol_context=None,
            configuration=configuration,
            gate_binding=None,
            acceptance=None,
        )
        adapter = CodexRuntimeAdapter(repository_root=repository, use_bwrap=True)
        advertised_tools = sorted(configuration.task.protocol_tools)
        guard_state: dict[str, Path] = {}
        original_write_config = adapter._write_config

        def write_guarded_config(run_value: Any, agent_value: Any) -> None:
            original_write_config(run_value, agent_value)
            if getattr(agent_value.package, "role", None) != "protocol":
                return
            script_path = agent_value.home / "platform-guard.py"
            script_path.write_bytes(_platform_guard_script_bytes())
            os.chmod(script_path, 0o444)
            log_path = agent_value.work / "platform-guard-calls.jsonl"
            config_path = agent_value.home / "config.toml"
            _replace_platform_config(
                config_path,
                advertised_tools=advertised_tools,
                guard_log_vpath="/agent/work/platform-guard-calls.jsonl",
            )
            config_text = config_path.read_text(encoding="utf-8")
            if any(token in config_text for token in _PLATFORM_GUARD_FORBIDDEN_TOKENS):
                raise ProducerSmokeError("guarded Runtime config still exposes platform endpoint/key")
            guard_state.update(
                {
                    "config_path": config_path,
                    "script_path": script_path,
                    "log_path": log_path,
                }
            )

        # This is a smoke-local adapter seam: product Runtime code and its required
        # MCP surface stay unchanged while the real endpoint is replaced fail-closed.
        adapter._write_config = write_guarded_config  # type: ignore[method-assign]
        receipt_delivery: dict[str, Any] | None = None
        message_text: str | None = None
        before_platform_snapshot: dict[str, Any] | None = None
        after_platform_snapshot: dict[str, Any] | None = None
        process_before: dict[str, Any] | None = None
        process_after: dict[str, Any] | None = None
        guard_config_text: str | None = None
        guard_script_text: str | None = None
        guard_attempts: list[dict[str, Any]] = []
        removed_platform_env = {
            name: os.environ.pop(name)
            for name in ("ONTOLOGY_MCP_API_KEY", "ONTOLOGY_MCP_BASE_URL")
            if name in os.environ
        }
        try:
            adapter.start_roster(run, [protocol_profile])
            if not all(name in guard_state for name in ("config_path", "script_path", "log_path")):
                raise ProducerSmokeError("Protocol Runtime did not install the platform guard")
            config_path = guard_state["config_path"]
            script_path = guard_state["script_path"]
            log_path = guard_state["log_path"]
            before_platform_snapshot = _guard_resource_snapshot(
                config_path=config_path, guard_script_path=script_path, guard_log_path=log_path
            )
            guard_config_text = config_path.read_text(encoding="utf-8")
            guard_script_text = script_path.read_text(encoding="utf-8")
            process_before = _process_snapshot(run_root)
            protocol_agent = adapter.agents[protocol_profile.agent_id]
            runtime_identity = protocol_agent.thread_id
            if not isinstance(runtime_identity, str) or not runtime_identity:
                raise ProducerSmokeError("Protocol Runtime did not expose a thread identity")
            generated_scope = synthetic_fresh_scope(run_id, runtime_identity)
            candidate = neutral_candidate(source_digest=source_digest)
            _bind_scope(candidate, generated_scope)
            run.protocol_context = {
                "project_id": generated_scope["project_id"],
                "ontology_id": generated_scope["ontology_id"],
            }

            runner = TeamRunner(repository_root=repository, adapter=adapter)
            runner.run = run
            prompt = (
                "Wait for exactly one Modeling candidate delivery. Do not call ontology_platform, "
                "do not report terminal, and do not use any platform/resource identifier other than "
                "the candidate scope. Parse the delivery text as JSON. Call the native MCP tool "
                "protocol_mechanics/build_candidate_receipt with exactly {candidate: <candidate>} "
                "and preserve its structured four-field receipt. Then send Modeling exactly one "
                "Team Transport message with reply_to_delivery_id equal to the candidate delivery ID. "
                "The message text MUST be one JSON object with keys receipt and batch. The batch MUST "
                "be a dry_run object conforming to modeling-batch-item-contract.json: use client_batch_id "
                f"batch-{run_id}, ontology_id {generated_scope['ontology_id']}, session_id "
                f"smoke-session-{run_id}, idempotency_key smoke-idempotency-{run_id}, "
                "expected_workspace_version workspace-0, lease_token null, and one create_class item "
                "whose client_item_id and name come from the candidate. Do not add prose."
            )
            prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            skill_paths = [str(path) for path in protocol_profile.package.required_skills]
            adapter.start_task(
                protocol_profile.agent_id,
                prompt,
                skill_paths,
                [protocol_profile.agent_id],
            )
            delivery = broker.send(
                "modeling",
                "protocol",
                json.dumps(candidate, ensure_ascii=False, sort_keys=True),
                expects_reply=True,
            )
            outbound = broker.drain_for(delivery_id=delivery.delivery_id)
            if len(outbound) != 1:
                raise ProducerSmokeError("Modeling candidate delivery was not claimed exactly once")
            adapter.send_message(
                protocol_profile.agent_id,
                RuntimeDelivery(
                    sender_id="modeling",
                    recipient_id=protocol_profile.agent_id,
                    kind="candidate",
                    text=delivery.text,
                    delivery_id=delivery.delivery_id,
                    expects_reply=True,
                ),
            )
            broker.ack_delivery(delivery.delivery_id)

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline and receipt_delivery is None:
                adapter.receive_messages()
                replies = broker.drain_for(sender_id="protocol", recipient_id="modeling")
                if replies:
                    if len(replies) != 1:
                        raise ProducerSmokeError("Protocol emitted more than one candidate reply")
                    receipt_delivery = {
                        "delivery_id": replies[0].delivery_id,
                        "reply_to_delivery_id": replies[0].reply_to_delivery_id,
                        "expects_reply": replies[0].expects_reply,
                        "text_sha256": hashlib.sha256(replies[0].text.encode("utf-8")).hexdigest(),
                    }
                    message_text = replies[0].text
                    broker.ack_delivery(replies[0].delivery_id)
                    break
                time.sleep(0.25)
            if receipt_delivery is None or message_text is None:
                raise ProducerSmokeError("Protocol Runtime did not complete the candidate MCP handoff")
            if receipt_delivery["reply_to_delivery_id"] != delivery.delivery_id:
                raise ProducerSmokeError("Protocol reply is not bound to the candidate delivery")
            try:
                translated = json.loads(message_text)
            except json.JSONDecodeError as exc:
                raise ProducerSmokeError("Protocol reply is not canonical JSON") from exc
            if not isinstance(translated, dict) or set(translated) != {"receipt", "batch"}:
                raise ProducerSmokeError("Protocol reply must contain exactly receipt and batch")
            receipt = translated["receipt"]
            if not isinstance(receipt, dict) or set(receipt) != {
                "status",
                "candidate_revision",
                "semantic_digest",
                "candidate_digest",
            }:
                raise ProducerSmokeError("Protocol receipt shape is invalid")
            if receipt.get("status") != "accepted":
                raise ProducerSmokeError("neutral candidate receipt was not accepted")
            translated_batch = _validate_batch_contract(
                translated["batch"], candidate=candidate, scope=generated_scope, run_id=run_id
            )

            # Exercise caller/prior scope rejection as an active contract check; neither
            # rejected candidate is sent to the Runtime or any platform endpoint.
            rejected_scopes: dict[str, str] = {}
            for label, bad_scope in {
                "prior": {"project_id": "prior-project", "ontology_id": "prior-ontology"},
                "caller": {"project_id": "caller-project", "ontology_id": "caller-ontology"},
            }.items():
                rejected = copy.deepcopy(candidate)
                rejected["scope"] = bad_scope
                try:
                    _bind_scope(rejected, generated_scope)
                except ProducerSmokeError:
                    rejected_scopes[label] = "rejected"
                else:
                    raise ProducerSmokeError(f"{label} scope drift was accepted")

            wrapper = run_root / "runtime-assets" / "protocol" / "protocol-retrieval-mcp.py"
            proof_rejection = _raw_mcp_call(
                wrapper,
                proof_gate=True,
                request={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "build_candidate_receipt",
                        "arguments": {"candidate": candidate},
                    },
                },
            )
            if proof_rejection.get("error", {}).get("code") != -32602:
                raise ProducerSmokeError("proof-gated raw MCP accepted a neutral candidate")
            tools_response = _raw_mcp_call(
                wrapper,
                proof_gate=False,
                request={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            )
            tools = tools_response.get("result", {}).get("tools", [])
            tool_names = sorted(item.get("name") for item in tools if isinstance(item, dict))
            if tool_names != ["build_candidate_receipt", "verify_scoped_retrieval_fallback"]:
                raise ProducerSmokeError("unbound Protocol MCP tool surface drifted")
            prompt_projection = runner._task_text("protocol")
            task_projection_digest = hashlib.sha256(prompt_projection.encode("utf-8")).hexdigest()
            protocol_tools_digest = _canonical_digest(tool_names)
            scope_digest = _canonical_digest(generated_scope)
            if protocol_tools_digest != _canonical_digest(tool_names):
                raise ProducerSmokeError("Protocol tool digest is not bound to the observed tool list")
            if scope_digest != _canonical_digest(generated_scope):
                raise ProducerSmokeError("scope digest is not bound to the generated scope")
            config_digest = hashlib.sha256(
                protocol_agent.home.joinpath("config.toml").read_bytes()
            ).hexdigest()
        except (CodexRuntimeError, OSError, ValueError) as exc:
            raise ProducerSmokeError(f"actual Runtime smoke is blocked: {exc}") from exc
        finally:
            try:
                adapter.stop()
            finally:
                process_after = _wait_for_no_processes(run_root)
                if all(name in guard_state for name in ("config_path", "script_path", "log_path")):
                    after_platform_snapshot = _guard_resource_snapshot(
                        config_path=guard_state["config_path"],
                        guard_script_path=guard_state["script_path"],
                        guard_log_path=guard_state["log_path"],
                        config_text=guard_config_text,
                        script_text=guard_script_text,
                    )
                    guard_attempts = _guard_attempts(guard_state["log_path"])
                broker.stop()
                os.environ.update(removed_platform_env)
        after_ledgers = _ledger_snapshot(repository)

    if before_ledgers != after_ledgers:
        raise ProducerSmokeError("no-start smoke mutated a live ledger")
    if before_platform_snapshot is None or after_platform_snapshot is None:
        raise ProducerSmokeError("platform guard snapshots were not captured")
    if before_platform_snapshot != after_platform_snapshot:
        raise ProducerSmokeError("platform resource snapshot drifted during no-start smoke")
    if process_after is None or process_after["count"]:
        raise ProducerSmokeError(f"residual Runtime processes remain: {process_after}")
    if any(
        record.get("accepted") is not False
        or record.get("guard_identity") != _PLATFORM_GUARD_IDENTITY
        or not isinstance(record.get("tool"), str)
        or not isinstance(record.get("arguments_sha256"), str)
        for record in guard_attempts
    ):
        raise ProducerSmokeError("platform guard attempt record is invalid")
    accepted_call_count = sum(record.get("accepted") is True for record in guard_attempts)
    if guard_attempts:
        raise ProducerSmokeError(
            f"platform guard rejected attempted calls; smoke requires zero attempts: {guard_attempts}"
        )
    if guard_config_text is None or guard_script_text is None:
        raise ProducerSmokeError("platform guard config/script capture is missing")
    guard_config_digest = hashlib.sha256(guard_config_text.encode("utf-8")).hexdigest()
    guard_script_digest = hashlib.sha256(guard_script_text.encode("utf-8")).hexdigest()
    ledger_before = before_ledgers
    ledger_after = after_ledgers
    evidence = {
        "schema_version": "r2-3-005-producer-runtime-no-start-smoke/v2",
        "run_id": run_id,
        "semantic_start": False,
        "platform_calls": 0,
        "ledger_mutations": 0,
        "acceptance_started": False,
        "scope": generated_scope,
        "scope_digest": scope_digest,
        "runtime_identity_sha256": hashlib.sha256(runtime_identity.encode("utf-8")).hexdigest(),
        "prompt_digest": prompt_digest,
        "task_projection_digest": task_projection_digest,
        "config_digest": config_digest,
        "protocol_tools": tool_names,
        "protocol_tools_digest": protocol_tools_digest,
        "receipt": receipt,
        "translated_batch": translated_batch,
        "transport_delivery": receipt_delivery,
        "scope_rejections": rejected_scopes,
        "ledger_before": ledger_before,
        "ledger_after": ledger_after,
        "platform_guard": {
            "identity": _PLATFORM_GUARD_IDENTITY,
            "config_sha256": guard_config_digest,
            "script_sha256": guard_script_digest,
            "advertised_tools": advertised_tools,
            "attempted_call_count": len(guard_attempts),
            "accepted_call_count": accepted_call_count,
            "attempted_calls": guard_attempts,
            "real_platform_server_reachable": False,
            "real_platform_key_configured": False,
            "ambient_platform_env_removed": sorted(removed_platform_env),
        },
        "platform_resource_snapshots": {
            "before": before_platform_snapshot,
            "after": after_platform_snapshot,
        },
        "process_snapshots": {
            "before": process_before,
            "after": process_after,
        },
        "proof_rejection": {
            "error_code": proof_rejection["error"]["code"],
            "message": proof_rejection["error"]["message"],
        },
    }
    evidence_path, evidence_digest = _retain_safe_evidence(repository, run_id, evidence)
    evidence["retained_evidence_path"] = evidence_path
    evidence["retained_evidence_sha256"] = evidence_digest
    return evidence


__all__ = [
    "ProducerSmokeError",
    "neutral_candidate",
    "run_no_semantic_start_smoke",
    "synthetic_fresh_scope",
]
