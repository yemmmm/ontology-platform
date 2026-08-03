"""Production, foreground-Runner-free P2 Protocol driver.

This module is intentionally a small host-owned driver, not another Runner.  It starts exactly
one schema-v2 Protocol Agent through :class:`CodexRuntimeAdapter`, wires the real
``TeamTransportBroker`` socket, and records only the bounded P2 provenance up to the Protocol
terminal report.  It never starts a Modeling or Coordinator Agent and it never writes a ledger
event.  The command is therefore useful to an independent tester without being a second semantic
producer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .contracts import (
    ProfileAgent,
    SAFE_PROTOCOL_TOOLS,
    TaskSource,
    TeamConfiguration,
    TeamProfile,
    TeamTask,
    digest_file,
    load_profile,
    repository_root,
)
from .platform_scope import PlatformScope, PlatformScopeError
from .runtimes.base import RuntimeDelivery
from .runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError
from .transport_mcp import Delivery, TeamTransportBroker


CONTRACT_RELATIVE_PATH = Path("modeling_team/references/p2-protocol-driver-contract.json")
SYNTHETIC_MODELING_ID = "p2-synthetic-modeling"
PROTOCOL_ID = "protocol"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
SYNTHETIC_SOURCE_IRI = "https://p2.example.test/entity/source"
SYNTHETIC_RELATION_IRI = "https://p2.example.test/relation/related"
SYNTHETIC_TARGET_IRI = "https://p2.example.test/entity/target"

_CONTRACT_FIELDS = {
    "schema_version",
    "command",
    "argv",
    "required_stages",
    "forbidden_evidence",
    "candidate_sender_id",
    "protocol_agent_id",
    "scope_mode",
    "protocol_tools",
    "runtime_contract",
    "max_runtime_seconds",
    "evidence_mode",
    "cleanup_policy",
}
_REQUIRED_STAGES = [
    "driver_started",
    "protocol_roster_started",
    "candidate_delivered",
    "candidate_receipt",
    "query_completed",
    "fallback_required",
    "verifier_completed",
    "broker_terminal_guard",
    "protocol_report_accepted",
    "protocol_runtime_cleanup",
    "scope_cleanup_first_stage",
    "scope_deleted",
    "scope_cleanup_second_stage",
    "driver_stopped",
]
_FORBIDDEN_EVIDENCE = [
    "teamrunner",
    "modeling_team" + " " + "run",
    "start_ledger",
    "semantic_start",
    "modeling terminal",
    "terminal-result-handoff",
    "ack_terminal_handoff",
    "all-agent settlement",
    "runner/terminal-result",
]
_RUNTIME_CONTRACT = {
    "adapter": "CodexRuntimeAdapter.start_roster",
    "broker": "TeamTransportBroker",
    "stdio": True,
    "private_bwrap": True,
    "app_server": True,
    "native_mcp": ["team_transport", "ontology_platform", "protocol_mechanics"],
}
_CLEANUP_POLICY = {
    "scope_mode": "create",
    "max_owned_ephemeral_scopes": 1,
    "delete_requires_first_stage": True,
    "admin_revoke_in_finally": True,
    "no_direct_db_delete": True,
    "no_new_deletion_key": True,
}


class P2ProtocolDriverError(RuntimeError):
    """A fail-closed production-driver error."""


@dataclass
class _DriverRun:
    run_id: str
    root: Path
    configuration: TeamConfiguration
    scope: dict[str, str]
    protocol_key: str | None = None
    transport_root: Path | None = None
    protocol_context: dict[str, str] | None = None


class _Evidence:
    """Append-only, safe-stage evidence writer shared by driver and Broker callback."""

    def __init__(self, path: Path, forbidden: Sequence[str]) -> None:
        self.path = path
        self.forbidden = tuple(item.lower() for item in forbidden)
        self.lock = threading.Lock()
        self.stages: list[str] = []

    def append(self, stage: str, **payload: Any) -> None:
        safe = {"stage": stage, **payload}
        encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        lower = encoded.lower()
        if any(token in lower for token in self.forbidden):
            raise P2ProtocolDriverError("forbidden P2 provenance appeared in evidence")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.stages.append(stage)


def load_contract(path: Path) -> dict[str, Any]:
    """Read the stable descriptor and reject command or lifecycle drift."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P2ProtocolDriverError("P2 Protocol driver contract is unreadable") from exc
    if not isinstance(value, dict) or set(value) != _CONTRACT_FIELDS:
        raise P2ProtocolDriverError("P2 Protocol driver contract fields drifted")
    if value.get("schema_version") != "p2-protocol-driver/v1":
        raise P2ProtocolDriverError("P2 Protocol driver contract schema drifted")
    if value.get("command") != "uv" or value.get("argv") != [
        "run",
        "--project",
        "backend",
        "python",
        "-m",
        "modeling_team.p2_protocol_driver",
        "--contract",
        CONTRACT_RELATIVE_PATH.as_posix(),
    ]:
        raise P2ProtocolDriverError("P2 Protocol driver command drifted")
    if value.get("required_stages") != _REQUIRED_STAGES:
        raise P2ProtocolDriverError("P2 Protocol driver lifecycle drifted")
    if value.get("forbidden_evidence") != _FORBIDDEN_EVIDENCE:
        raise P2ProtocolDriverError("P2 Protocol driver provenance boundary drifted")
    if value.get("candidate_sender_id") != SYNTHETIC_MODELING_ID:
        raise P2ProtocolDriverError("P2 Protocol candidate sender drifted")
    if value.get("protocol_agent_id") != PROTOCOL_ID or value.get("scope_mode") != "create":
        raise P2ProtocolDriverError("P2 Protocol roster or scope contract drifted")
    tools = value.get("protocol_tools")
    if (
        not isinstance(tools, list)
        or not tools
        or len(set(tools)) != len(tools)
        or any(tool not in SAFE_PROTOCOL_TOOLS for tool in tools)
        or "query_semantic_context" not in tools
    ):
        raise P2ProtocolDriverError("P2 Protocol tool contract is invalid")
    if value.get("runtime_contract") != _RUNTIME_CONTRACT:
        raise P2ProtocolDriverError("P2 Protocol runtime contract drifted")
    maximum = value.get("max_runtime_seconds")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 1800:
        raise P2ProtocolDriverError("P2 Protocol runtime bound is invalid")
    if value.get("evidence_mode") != "append_only_run_local":
        raise P2ProtocolDriverError("P2 Protocol evidence mode is invalid")
    if value.get("cleanup_policy") != _CLEANUP_POLICY:
        raise P2ProtocolDriverError("P2 Protocol cleanup policy drifted")
    return value


def _safe_run_id(value: str) -> str:
    if not isinstance(value, str) or not RUN_ID_RE.fullmatch(value):
        raise P2ProtocolDriverError("unsafe P2 Protocol run ID")
    return value


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _synthetic_candidate() -> tuple[dict[str, Any], str]:
    """Return a nonbusiness candidate and its stable semantic digest."""
    items = [
        {
            "graph_role": "asserted_data",
            "subject": SYNTHETIC_SOURCE_IRI,
            "predicate": SYNTHETIC_RELATION_IRI,
            "object": SYNTHETIC_TARGET_IRI,
            "object_kind": "iri",
            "object_datatype": None,
            "object_language": None,
        }
    ]
    items.sort(
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    candidate = {
        "schema_version": "candidate-required-assertions/v1",
        "candidate_revision": "p2-protocol-synthetic-1",
        "items": items,
    }
    return candidate, _canonical_digest({"schema_version": candidate["schema_version"], "statements": items})


def _build_configuration(root: Path, contract: dict[str, Any]) -> TeamConfiguration:
    profile = load_profile(root / "modeling_team/profiles/base-three-agent.yaml", root=root)
    package = next(
        (agent.package for agent in profile.agents if agent.package.role == "protocol"), None
    )
    if package is None:
        raise P2ProtocolDriverError("Protocol package is unavailable")
    protocol_agent = ProfileAgent(PROTOCOL_ID, package)
    single_profile = TeamProfile(
        "p2-protocol-production",
        profile.runtime,
        (protocol_agent,),
        frozenset(),
        {},
    )
    source = root / "modeling_team/references/modeling-batch-item-contract.json"
    if not source.is_file() or source.is_symlink():
        raise P2ProtocolDriverError("Protocol mechanics reference is unavailable")
    relative = source.relative_to(root)
    role_source = TaskSource(source, relative, "protocol", frozenset({"protocol"}))
    tools = tuple(contract["protocol_tools"])
    task = TeamTask(
        "p2-protocol-production",
        "",
        (source,),
        ("candidate receipt", "query", "fallback verifier", "Protocol terminal result"),
        schema_version=2,
        role_sources=(role_source,),
        protocol_tools=tools,
        retain_nonempty=False,
        semantic_start_evidence=(),
    )
    return TeamConfiguration(single_profile, task)


def _stage_run(run: _DriverRun, root: Path) -> None:
    """Stage only the protocol contract; no business source is ever copied."""
    (run.root / "evidence").mkdir(parents=True, mode=0o700, exist_ok=True)
    source_root = run.root / "sources" / "protocol"
    source_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    source = root / "modeling_team/references/modeling-batch-item-contract.json"
    target = source_root / source.relative_to(root)
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    shutil.copyfile(source, target)
    baseline = {
        "files": {
            "protocol_retrieval_mcp": digest_file(root / "modeling_team/protocol_retrieval_mcp.py"),
            "protocol_retrieval_verifier": digest_file(root / "modeling_team/protocol_mechanics.py"),
            "proof_v2": digest_file(root / "modeling_team/proof_v2.py"),
        }
    }
    (run.root / "baseline-manifest.json").write_text(
        json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _bootstrap_helpers(root: Path) -> tuple[Callable[[], tuple[str, str]], Callable[[str], bool]]:
    """Use the existing local admin API helper without importing the foreground Runner."""
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    from app.core.config import Settings
    from app.repositories.models import ApiKeyModel
    from app.repositories.postgres import create_session_factory
    from app.security.auth import create_api_key, revoke_key

    def create() -> tuple[str, str]:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            record, plaintext = create_api_key(
                session,
                name="r2-3-002-p2-protocol-admin",
                project_id=None,
                scopes=["admin"],
            )
        return plaintext, record.id

    def revoke(key_id: str) -> bool:
        with create_session_factory(Settings(_env_file=backend / ".env"))() as session:
            record = session.get(ApiKeyModel, key_id)
            return bool(record and revoke_key(session, record).revoked_at)

    return create, revoke


def _task_text(run: _DriverRun, candidate: dict[str, Any], semantic_digest: str) -> str:
    context = run.protocol_context or {}
    return (
        "P2 Protocol-only production fixture. No business source is available and no business fact "
        "may be invented. Wait for the synthetic Modeling candidate delivered over Team Transport. "
        "Reply exactly once to that delivery with reply_to_delivery_id bound to its delivery_id, "
        "as a JSON mechanical receipt containing status=accepted, candidate_revision, and the exact "
        "semantic_digest; preserve the candidate revision and digest. This receipt is only an "
        "acknowledgement: continue materializing the immutable candidate in the same turn. Then use the public v2 platform MCP "
        "surface to materialize this candidate in the owned fresh create scope using the declared "
        "mechanics contract. Read every formal receipt and lineage record before constructing native "
        "proof; never invent platform IDs or IRIs. After materialization, issue one eligible, "
        "ontology-scoped query_semantic_context with ontology_ids=[%s], scope_mode=ontologies, and "
        "a bounded limit that observes the real incomplete/truncated result. The completed query must "
        "enter fallback_required before any verifier call. Only then call native protocol_mechanics/"
        "verify_scoped_retrieval_fallback with mode=create and the ten direct proof fields. Wait for "
        "complete=true. Only after that verifier completion call team_transport/report_task_result "
        "exactly once. Never call a fabricated Runner handoff or claim another Agent terminal. "
        "Mechanical scope context (non-secret): %s. Candidate digest (for binding): %s. Candidate: %s"
        % (
            json.dumps(context.get("ontology_id", "")),
            json.dumps(context, ensure_ascii=False, sort_keys=True),
            semantic_digest,
            json.dumps(candidate, ensure_ascii=False, sort_keys=True),
        )
    )


def _runtime_delivery(delivery: Delivery) -> RuntimeDelivery:
    return RuntimeDelivery(
        sender_id=delivery.sender_id,
        recipient_id=delivery.recipient_id,
        kind="p2-candidate" if delivery.sender_id == SYNTHETIC_MODELING_ID else "p2-reply",
        text=delivery.text,
        delivery_id=delivery.delivery_id,
        expects_reply=delivery.expects_reply,
        reply_to_delivery_id=delivery.reply_to_delivery_id,
    )


def _validate_candidate_receipt(
    reply: Delivery, candidate: dict[str, Any], semantic_digest: str, delivery_id: str
) -> None:
    """Accept only a sanitized, identity-bound mechanical candidate receipt."""
    if (
        reply.sender_id != PROTOCOL_ID
        or reply.recipient_id != SYNTHETIC_MODELING_ID
        or reply.reply_to_delivery_id != delivery_id
        or not isinstance(reply.delivery_id, str)
        or not reply.delivery_id
        or not isinstance(reply.text, str)
        or not reply.text
        or len(reply.text) > 4096
    ):
        raise P2ProtocolDriverError("Protocol candidate receipt envelope is invalid")
    try:
        value = json.loads(reply.text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise P2ProtocolDriverError("Protocol candidate receipt is not JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "status", "candidate_revision", "semantic_digest"
    }:
        raise P2ProtocolDriverError("Protocol candidate receipt fields are invalid")
    if (
        value.get("status") != "accepted"
        or value.get("candidate_revision") != candidate.get("candidate_revision")
        or value.get("semantic_digest") != semantic_digest
    ):
        raise P2ProtocolDriverError("Protocol candidate receipt binding drifted")


def _cleanup_scope(scope: PlatformScope, evidence: _Evidence) -> None:
    """Cancel safe terminal state, freeze two-stage evidence, delete, then revoke admin."""
    cleanup: dict[str, Any] = {}
    try:
        terminal = scope._terminal_state(allow_cancel=True, require_completed=False)  # noqa: SLF001
        cleanup.update(terminal)
        if scope.protocol_key_id and scope.admin_key:
            cleanup["protocol_key_revoked"] = scope._revoke_project_key(cleanup)  # noqa: SLF001
        first = scope._first_stage_delete_evidence(cleanup, terminal)  # noqa: SLF001
        evidence.append(
            "scope_cleanup_first_stage",
            ready_for_delete=first.get("ready_for_delete") is True,
            session_terminal=first.get("session_terminal") is True,
            lease_auto_released=first.get("lease_auto_released") is True,
            project_scoped_keys=first.get("project_scoped_keys", []),
            bootstrap_admin=first.get("bootstrap_admin", {}),
            cleanup_receipts=first.get("cleanup_receipts", {}),
        )
        if first.get("ready_for_delete") is not True:
            raise P2ProtocolDriverError("ephemeral scope first-stage cleanup is incomplete")
        if not scope.project_id or not scope.admin_key or scope.request is None:
            raise P2ProtocolDriverError("ephemeral scope delete credential is unavailable")
        status, value = scope.request(
            "DELETE", f"/api/projects/{scope.project_id}", None, scope.admin_key
        )
        post_delete = scope._post_delete_evidence()  # noqa: SLF001
        scope.scope_disposition = "deleted-empty" if status == 204 else "delete-failed"
        evidence.append(
            "scope_deleted",
            status=status,
            body_type=type(value).__name__,
            scope_disposition=scope.scope_disposition,
            project_absent=post_delete.get("project_absent"),
            ontology_absent=post_delete.get("ontology_absent"),
            active_project_residual_count=post_delete.get("active_project_residual_count"),
            residual_counts=post_delete.get("residual_counts"),
            fk_cascade=post_delete.get("fk_cascade"),
        )
        if status != 204 or post_delete.get("project_absent") is not True or post_delete.get("ontology_absent") is not True:
            raise P2ProtocolDriverError("ephemeral scope deletion proof is incomplete")
    finally:
        # Revocation is deliberately in finally so a failed DELETE cannot leave the org key active.
        try:
            scope._revoke_keys(cleanup)  # noqa: SLF001
        finally:
            second = cleanup.get("second_stage", {})
            org_admin = second.get("org_admin_key", {}) if isinstance(second, dict) else {}
            evidence.append(
                "scope_cleanup_second_stage",
                admin_key_revoked=cleanup.get("admin_key_revoked") is True,
                org_admin_key={
                    "id": org_admin.get("id"),
                    "active": org_admin.get("active"),
                    "non_active": org_admin.get("non_active"),
                    "revoked_at": org_admin.get("revoked_at"),
                },
                retained_org_admin_audit_row=second.get("retained_org_admin_audit_row", {})
                if isinstance(second, dict)
                else {},
            )
            if cleanup.get("admin_key_revoked") is not True:
                raise P2ProtocolDriverError("ephemeral scope admin key remained active")


def _remove_runtime_artifacts(run_root: Path) -> None:
    """Remove only this driver's private process/socket staging after credential destruction."""
    for relative in ("runtime", "runtime-assets", "transport"):
        target = run_root / relative
        if target.exists():
            shutil.rmtree(target)
    (run_root / "transport-root").unlink(missing_ok=True)


def run_driver(
    *,
    contract_path: Path,
    root: Path | None = None,
    run_id: str,
    base_url: str = "http://127.0.0.1:8001",
    evidence_path: Path | None = None,
    timeout: float | None = None,
    adapter_factory: Callable[[Path], CodexRuntimeAdapter] | None = None,
    scope_factory: Callable[[str, str, Callable[[], tuple[str, str]], Callable[[str], bool]], PlatformScope]
    | None = None,
) -> dict[str, Any]:
    """Execute the bounded production path and return sanitized stage evidence.

    ``adapter_factory`` and ``scope_factory`` are dependency seams for unit tests only; the CLI
    supplies neither and therefore always uses the production Codex/bwrap and PlatformScope path.
    """
    contract = load_contract(contract_path)
    repository = (root or repository_root()).resolve()
    run_id = _safe_run_id(run_id)
    maximum = float(contract["max_runtime_seconds"])
    if timeout is not None:
        maximum = min(maximum, max(1.0, float(timeout)))
    run_root = repository / "workspaces" / "p2-protocol-runs" / run_id
    if run_root.exists():
        raise P2ProtocolDriverError("P2 Protocol run directory already exists")
    run = _DriverRun(run_id, run_root, _build_configuration(repository, contract), {"mode": "create"})
    if evidence_path is not None:
        try:
            evidence_path.resolve().relative_to(run_root.resolve())
        except ValueError as exc:
            raise P2ProtocolDriverError("P2 Protocol evidence must remain run-local") from exc
    evidence = _Evidence(
        evidence_path or run_root / "evidence" / "p2-protocol-driver.jsonl",
        contract["forbidden_evidence"],
    )
    scope: PlatformScope | None = None
    broker: TeamTransportBroker | None = None
    adapter: CodexRuntimeAdapter | None = None
    started = time.monotonic()
    candidate, semantic_digest = _synthetic_candidate()
    terminal_result: dict[str, Any] | None = None
    guard_calls: list[dict[str, Any]] = []
    try:
        run_root.mkdir(parents=True, mode=0o700)
        _stage_run(run, repository)
        evidence.append("driver_started", run_id=run_id, scope_mode="create")
        create_admin, revoke_admin = _bootstrap_helpers(repository)
        scope = (scope_factory or (lambda base, ident, create, revoke: PlatformScope(base, ident, create, revoke)))(
            base_url, run_id, create_admin, revoke_admin
        )
        scope.prepare({"mode": "create"})
        scope.retain_nonempty = False
        run.protocol_key = scope.protocol_key
        run.protocol_context = scope.read_protocol_context()
        if not run.protocol_key or not run.protocol_context:
            raise P2ProtocolDriverError("Protocol scope credentials/context unavailable")
        (run.root / "transport").mkdir(mode=0o700, exist_ok=True)
        broker_root = run.root / "transport" / "broker"
        adapter = (adapter_factory or (lambda path: CodexRuntimeAdapter(repository_root=path)))(repository)

        def terminal_guard(agent_id: str, already_synchronized: bool = False) -> bool:
            if adapter is None:
                return True
            blocked = adapter.terminal_report_blocked(agent_id, already_synchronized)
            guard_calls.append({"agent_id": agent_id, "blocked": blocked is True})
            return blocked

        broker = TeamTransportBroker(
            broker_root,
            {(SYNTHETIC_MODELING_ID, PROTOCOL_ID), (PROTOCOL_ID, SYNTHETIC_MODELING_ID)},
            terminal_report_guard=terminal_guard,
        )
        broker.start([PROTOCOL_ID])
        run.transport_root = broker.root
        (run.root / "transport-root").write_text(str(broker.root), encoding="utf-8")
        profile_agents = list(run.configuration.profile.agents)
        identities = adapter.start_roster(run, profile_agents)
        if [item.agent_id for item in identities] != [PROTOCOL_ID]:
            raise P2ProtocolDriverError("Protocol roster drifted")
        evidence.append("protocol_roster_started", agent_id=PROTOCOL_ID, adapter="CodexRuntimeAdapter.start_roster")
        adapter.start_task(
            PROTOCOL_ID,
            _task_text(run, candidate, semantic_digest),
            [str(path) for path in profile_agents[0].package.required_skills],
            [PROTOCOL_ID],
        )
        delivery = broker.send(
            SYNTHETIC_MODELING_ID,
            PROTOCOL_ID,
            json.dumps(
                {"candidate": candidate, "semantic_digest": semantic_digest},
                ensure_ascii=False,
                sort_keys=True,
            ),
            expects_reply=True,
        )
        # Claim the synthetic request by identity before handing it to the real Protocol thread.
        # The generic ``drain`` is the foreground Runner's all-recipient FIFO operation; using it
        # here would return this still-queued outbound candidate as if it were a Protocol reply.
        claimed = broker.drain_for(delivery_id=delivery.delivery_id)
        if claimed != [delivery]:
            raise P2ProtocolDriverError("synthetic candidate queue ownership drifted")
        adapter.send_message(PROTOCOL_ID, _runtime_delivery(delivery))
        broker.ack_delivery(delivery.delivery_id)
        evidence.append(
            "candidate_delivered",
            sender_id=SYNTHETIC_MODELING_ID,
            recipient_id=PROTOCOL_ID,
            delivery_id=delivery.delivery_id,
            candidate_revision=candidate["candidate_revision"],
            semantic_digest=semantic_digest,
        )
        receipt_seen = False
        query_seen = False
        fallback_seen = False
        verifier_seen = False
        deadline = time.monotonic() + maximum
        while time.monotonic() < deadline:
            adapter.receive_messages()
            for reply in broker.drain_for(
                sender_id=PROTOCOL_ID,
                recipient_id=SYNTHETIC_MODELING_ID,
            ):
                _validate_candidate_receipt(reply, candidate, semantic_digest, delivery.delivery_id)
                if receipt_seen:
                    raise P2ProtocolDriverError("duplicate Protocol candidate receipt")
                receipt_seen = True
                broker.ack_delivery(reply.delivery_id)
                evidence.append(
                    "candidate_receipt",
                    sender_id=reply.sender_id,
                    recipient_id=reply.recipient_id,
                    delivery_id=reply.delivery_id,
                    reply_to_delivery_id=reply.reply_to_delivery_id,
                )
            agent = adapter.agents.get(PROTOCOL_ID)
            state = getattr(agent, "retrieval_state", "idle") if agent is not None else "idle"
            episode = getattr(agent, "retrieval_episode", 0) if agent is not None else 0
            if receipt_seen and not query_seen and agent is not None and getattr(agent, "state", "") == "idle":
                evidence.append(
                    "post_receipt_idle",
                    agent_id=PROTOCOL_ID,
                    runtime_state="idle",
                    retrieval_episode=episode,
                    next_required_stage="query_completed",
                )
                raise P2ProtocolDriverError("Protocol became idle before query progress")
            if not query_seen and episode >= 1:
                query_seen = True
                evidence.append("query_completed", episode=episode)
            if not fallback_seen and state == "fallback_required":
                fallback_seen = True
                evidence.append("fallback_required", episode=episode)
            if not verifier_seen and state == "fallback_satisfied":
                verifier_seen = True
                evidence.append("verifier_completed", episode=episode, mode="create")
            if broker.results:
                terminal_result = {
                    "agent_id": next(iter(broker.results)),
                    "status": broker.results[next(iter(broker.results))].status,
                }
                break
            if agent is not None and getattr(agent, "state", "") == "failed":
                raise P2ProtocolDriverError("Protocol app-server entered failed state")
            time.sleep(0.05)
        if not receipt_seen or not query_seen or not fallback_seen or not verifier_seen:
            raise P2ProtocolDriverError("P2 Protocol sequence did not complete before timeout")
        if terminal_result is None or terminal_result.get("agent_id") != PROTOCOL_ID:
            raise P2ProtocolDriverError("Broker did not accept Protocol terminal result")
        evidence.append("broker_terminal_guard", calls=guard_calls)
        evidence.append("protocol_report_accepted", status=terminal_result.get("status"))
        if any(call.get("blocked") is True for call in guard_calls):
            # A blocked early report is safe, but the final accepted report must follow verifier.
            if not verifier_seen:
                raise P2ProtocolDriverError("terminal guard was bypassed before verifier")
    except P2ProtocolDriverError as exc:
        try:
            evidence.append("driver_failed", error_type=type(exc).__name__)
        except P2ProtocolDriverError:
            pass
        raise
    except (CodexRuntimeError, PlatformScopeError, OSError, ValueError) as exc:
        # Error text is not retained: it can include runtime paths or server data.
        try:
            evidence.append("driver_failed", error_type=type(exc).__name__)
        except P2ProtocolDriverError:
            pass
        raise P2ProtocolDriverError("P2 Protocol production path failed") from exc
    finally:
        cleanup_errors: list[str] = []
        if adapter is not None:
            try:
                adapter.stop()
            except Exception as exc:  # pragma: no cover - defensive production closeout
                cleanup_errors.append(type(exc).__name__)
        if broker is not None:
            try:
                broker.stop()
            except Exception as exc:  # pragma: no cover - defensive production closeout
                cleanup_errors.append(type(exc).__name__)
        if adapter is not None:
            try:
                _remove_runtime_artifacts(run.root)
            except OSError as exc:  # pragma: no cover - defensive production closeout
                cleanup_errors.append(type(exc).__name__)
            try:
                evidence.append(
                    "protocol_runtime_cleanup",
                    credentials_destroyed=True,
                    cleanup_error=cleanup_errors[-1] if cleanup_errors else None,
                )
            except P2ProtocolDriverError:
                cleanup_errors.append("evidence")
        if scope is not None:
            try:
                _cleanup_scope(scope, evidence)
            except Exception as exc:  # pragma: no cover - defensive production closeout
                cleanup_errors.append(type(exc).__name__)
        try:
            evidence.append(
                "driver_stopped",
                elapsed_seconds=round(time.monotonic() - started, 3),
                cleanup_error_types=cleanup_errors,
            )
        except P2ProtocolDriverError:
            pass
        if cleanup_errors:
            raise P2ProtocolDriverError("P2 Protocol cleanup did not complete")
    return {
        "status": "p2_protocol_complete",
        "run_id": run_id,
        "evidence": str(evidence.path),
        "stages": list(evidence.stages),
        "terminal_result": terminal_result,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Foreground-Runner-free production P2 Protocol driver")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--timeout", type=float)
    args = parser.parse_args(argv)
    root = repository_root()
    run_id = args.run_id or f"p2-protocol-{int(time.time())}"
    try:
        result = run_driver(
            contract_path=args.contract,
            root=root,
            run_id=run_id,
            base_url=args.base_url,
            evidence_path=args.evidence,
            timeout=args.timeout,
        )
    except P2ProtocolDriverError as exc:
        print(f"p2 protocol driver failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
