#!/usr/bin/env python3
"""Internal deterministic platform adapter for the Pi first-party modeling Runner.

It is intentionally a small HTTP client around the existing Build Session and Modeling Batch APIs.
Credentials and lease tokens are kept in process memory only; the recoverable ledger contains only
stable IDs and idempotency identities.

The Claude Harness receipt, ``recording-health`` and ``recording-unavailable`` safe points that the
legacy ``local_modeling_adapter`` required were removed when this core was migrated under the Pi
package. Protected writes are now gated by a one-shot Runner authorization that the Pi Runner
records only after it has confirmed role settlement, the candidate artifact hash, an independent
review PASS and (where applicable) a clean dry-run. The deterministic platform write semantics,
candidate hash, review binding, capacity-aware Batch planning, idempotency, reconciliation and
verification contracts are preserved unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_RESPONSE_BYTES = 256 * 1024
MAX_FINDINGS = 20
LIMIT_FIELDS = (
    "MODELING_BATCH_MAX_ITEMS",
    "MODELING_BATCH_MAX_REQUEST_BYTES",
    "MODELING_BATCH_MAX_INLINE_EVIDENCE",
    "MODELING_BATCH_MAX_EVIDENCE_EXCERPT_CHARS",
)
DEFAULT_LIMITS = (100, 1_048_576, 100, 20_000)
BRIEF_FIELDS = {
    "domain_name",
    "business_goal",
    "scope",
    "core_concepts",
    "identity_rules",
    "expected_granularity",
    "data_sources",
    "boundaries",
    "terminology",
    "inference_scope",
}
# The local ontology_id is the deterministic Shared Modeling Directory key. The platform owns a
# separate generated Ontology id; this external_mappings marker durably binds the two so a resumed
# or re-initialized run rediscovers the same platform Ontology instead of creating a duplicate.
ONTOLOGY_EXTERNAL_KEY = "pi_modeling_local_ontology_id"


class AdapterError(RuntimeError):
    """A stable, redacted operator-facing failure."""


def _load_shared() -> Any:
    path = Path(__file__).with_name("shared_modeling_directory.py")
    spec = importlib.util.spec_from_file_location("shared_modeling_directory", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smd = _load_shared()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("local_config_invalid") from exc
    if not isinstance(value, dict):
        raise AdapterError("local_config_invalid")
    return value


def _atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AdapterError("credential_unavailable") from exc
    for raw in lines:
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip("'\"")
    return values


def _repo_path(repo: Path, value: str, label: str) -> Path:
    target = (repo / value).resolve()
    try:
        target.relative_to(repo.resolve())
    except ValueError as exc:
        raise AdapterError(f"{label}_outside_repository") from exc
    return target


def load_config(repo: Path, config_path: Path) -> tuple[dict[str, Any], dict[str, int]]:
    config = _read_json(config_path)
    allowed = {
        "schema_version",
        "project_id",
        "api_base_url",
        "api_key_env_file",
        "api_key_env_name",
    }
    if set(config) - allowed or config.get("schema_version") != 1:
        raise AdapterError("local_config_invalid")
    project_id = config.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise AdapterError("project_id_invalid")
    base_url = str(config.get("api_base_url", "http://127.0.0.1:8001/api")).rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.query:
        raise AdapterError("local_service_required")
    env_path = _repo_path(repo, str(config.get("api_key_env_file", "backend/.env")), "credential")
    key_name = str(config.get("api_key_env_name", "ONTOLOGY_MCP_API_KEY"))
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", key_name):
        raise AdapterError("credential_config_invalid")
    api_key = _env_file(env_path).get(key_name)
    if not api_key:
        raise AdapterError("credential_unavailable")
    values = _env_file(env_path)
    limits = {
        key.lower(): int(values.get(key, default))
        for key, default in zip(LIMIT_FIELDS, DEFAULT_LIMITS)
    }
    if any(value <= 0 for value in limits.values()):
        raise AdapterError("local_capacity_invalid")
    return {"project_id": project_id, "api_base_url": base_url, "api_key": api_key}, limits


def _request(
    config: dict[str, Any], method: str, path: str, payload: dict[str, Any] | None = None
) -> Any:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{config['api_base_url']}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # Never echo a remote response: it may include request diagnostics or secret-like text.
        raise AdapterError(f"platform_http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AdapterError("platform_unavailable") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AdapterError("platform_response_too_large")
    try:
        value = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise AdapterError("platform_response_invalid") from exc
    if not isinstance(value, (dict, list)):
        raise AdapterError("platform_response_invalid")
    return value


def _ontology_external_mappings(local_id: str) -> dict[str, str]:
    return {ONTOLOGY_EXTERNAL_KEY: local_id}


def _ensure_platform_ontologies(
    config: dict[str, Any], run: dict[str, Any], state: dict[str, Any]
) -> dict[str, str]:
    """Idempotently create or rediscover one platform Ontology per local ontology id.

    The local ontology_id is the deterministic Shared Modeling Directory key (run.json, Coverage,
    candidate, Batch plan and verification are all keyed on it); the platform owns a separate
    generated Ontology id. Each local id is durably bound to its platform id through the Ontology
    ``external_mappings`` so a resumed or re-initialized run rediscovers the same Ontology instead
    of creating a duplicate. This is a platform setup step (like Build Session creation in
    ``start``), not a protected modeling write, so it is not Runner-grant gated.
    """
    bindings: dict[str, str] = {
        key: value
        for key, value in (state.get("ontology_bindings") or {}).items()
        if isinstance(key, str) and isinstance(value, str) and value
    }
    listed: list[dict[str, Any]] | None = None
    project_ontology_path = (
        f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/ontologies"
    )
    for entry in run.get("ontologies", []):
        local_id = entry.get("ontology_id") if isinstance(entry, dict) else None
        if not isinstance(local_id, str) or not local_id:
            raise AdapterError("run_ontology_invalid")
        if bindings.get(local_id):
            continue
        if listed is None:
            listed = _request(config, "GET", project_ontology_path)
            if not isinstance(listed, list):
                raise AdapterError("platform_response_invalid")
        existing_id: str | None = None
        for item in listed:
            if not isinstance(item, dict):
                continue
            mappings = item.get("external_mappings")
            if isinstance(mappings, dict) and mappings.get(ONTOLOGY_EXTERNAL_KEY) == local_id:
                candidate = item.get("id")
                if isinstance(candidate, str) and candidate:
                    existing_id = candidate
                    break
        if existing_id:
            bindings[local_id] = existing_id
            continue
        created = _request(
            config,
            "POST",
            project_ontology_path,
            {
                "name": local_id[:200],
                "description": f"Pi modeling ontology {local_id}",
                "external_mappings": _ontology_external_mappings(local_id),
            },
        )
        platform_id = created.get("id") if isinstance(created, dict) else None
        if not isinstance(platform_id, str) or not platform_id:
            raise AdapterError("ontology_create_invalid")
        bindings[local_id] = platform_id
    return bindings


def _platform_ontology_id(state: dict[str, Any], local_id: str) -> str:
    """Resolve the bound platform Ontology id for one local ontology id at a platform boundary."""
    bindings = state.get("ontology_bindings")
    platform_id = bindings.get(local_id) if isinstance(bindings, dict) else None
    if not isinstance(platform_id, str) or not platform_id:
        raise AdapterError("ontology_binding_missing")
    return platform_id


def _ledger(repo: Path, run_id: str) -> Path:
    return repo / "workspaces" / "modeling-adapter" / run_id / "state.json"


def _envelope(
    action: str,
    status: str,
    *,
    refs: dict[str, str] | None = None,
    next_action: str,
    error: str | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "action": action,
        "status": status,
        "references": refs or {},
        "findings": list(findings or [])[:MAX_FINDINGS],
        "error_code": error,
        "retryable": error in {"platform_unavailable", "platform_http_409"},
        "next_action": next_action,
    }


def start(repo: Path, run_dir: Path, config_path: Path) -> dict[str, Any]:
    config, _limits = load_config(repo, config_path)
    report = smd.validate_run(run_dir)
    if not report["valid"]:
        raise AdapterError("shared_run_invalid")
    run = smd._load_run(run_dir)
    if run.get("execution_profile") != "local":
        raise AdapterError("local_profile_required")
    _request(config, "GET", "/health")
    run_id = run["run_id"]
    state_path = _ledger(repo, run_id)
    state = _read_json(state_path) if state_path.exists() else {}
    session_id = state.get("build_session_id")
    if session_id:
        detail = _request(
            config, "GET", f"/build-sessions/{urllib.parse.quote(session_id, safe='')}"
        )
    else:
        detail = _request(
            config,
            "POST",
            f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/build-sessions",
            {"client_session_id": f"local-{run_id}"[:255]},
        )
        session_id = detail.get("session", detail).get("id")
    session = detail.get("session", detail)
    if (
        not isinstance(session_id, str)
        or session.get("project_id") != config["project_id"]
        or session.get("status") != "active"
    ):
        raise AdapterError("build_session_invalid")
    state = {
        **state,
        "schema_version": 1,
        "build_session_id": session_id,
        "session_revision": session.get("revision"),
    }
    # Bind every local ontology id to a platform Ontology id before any CQ or Batch references it.
    # A resumed start rediscovers existing bindings and only creates missing Ontologies.
    state["ontology_bindings"] = _ensure_platform_ontologies(config, run, state)
    # A resumed start drops any stale one-shot Runner authorizations: each protected write must be
    # re-confirmed against the current settled role, artifact hash, review verdict and dry-run.
    state.pop("runner_grants", None)
    _atomic_json(state_path, state)
    smd.bind_local_execution(run_dir, build_session_id=session_id)
    return _envelope(
        "start",
        "ok",
        refs={"run_id": run_id, "build_session_id": session_id},
        next_action="organize_business",
    )


def status(repo: Path, run_dir: Path, config_path: Path) -> dict[str, Any]:
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state_path = _ledger(repo, run["run_id"])
    if not state_path.exists():
        return _envelope("status", "blocked", next_action="start", error="adapter_state_missing")
    state = _read_json(state_path)
    session_id = state.get("build_session_id")
    if not isinstance(session_id, str):
        raise AdapterError("adapter_state_invalid")
    session = _request(
        config, "GET", f"/build-sessions/{urllib.parse.quote(session_id, safe='')}"
    ).get("session", {})
    ready = session.get("status") == "active"
    return _envelope(
        "status",
        "ok" if ready else "blocked",
        refs={"run_id": run["run_id"], "build_session_id": session_id},
        next_action="organize_business" if ready else "start",
        error=None if ready else "build_session_invalid",
    )


def _canonical_question(question: str) -> str:
    return " ".join(question.casefold().split())


def _canonical_query(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _business_manifest(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    allowed = {"brief", "questions"}
    if (
        set(value) != allowed
        or not isinstance(value["brief"], dict)
        or not isinstance(value["questions"], dict)
    ):
        raise AdapterError("business_commit_invalid")
    brief = value["brief"]
    if set(brief) != {"fields", "confirmed_fields"}:
        raise AdapterError("business_commit_invalid")
    if not isinstance(brief["fields"], dict) or not isinstance(brief["confirmed_fields"], list):
        raise AdapterError("business_commit_invalid")
    if (
        not set(brief["fields"]) <= BRIEF_FIELDS
        or not set(brief["confirmed_fields"]) <= BRIEF_FIELDS
    ):
        raise AdapterError("business_brief_field_unsupported")
    return value


def _question_payload(
    local: dict[str, Any], metadata: dict[str, Any], ontology_id: str
) -> dict[str, Any]:
    query = metadata.get("query_definition", local.get("query_definition", {}))
    if not isinstance(query, dict):
        raise AdapterError("business_question_invalid")
    question = metadata.get("question", local.get("text"))
    if not isinstance(question, str) or not question.strip():
        raise AdapterError("business_question_invalid")
    source_fields = metadata.get("source_brief_fields", [])
    if not isinstance(source_fields, list) or not all(
        isinstance(item, str) and item for item in source_fields
    ):
        raise AdapterError("business_question_invalid")
    return {
        "ontology_id": ontology_id,
        "question": question.strip(),
        "importance": int(metadata.get("importance", 3)),
        "query_definition": query,
        "source_brief_fields": sorted(set(source_fields)),
    }


def _consume_runner_grant(
    repo: Path, run: dict[str, Any], operation_id: str | None
) -> dict[str, Any]:
    """Consume one Runner-confirmed authorization for a protected platform write.

    The Pi Runner records a grant via ``authorize_runner_write`` only after confirming that the role
    has settled (``agent_settled`` plus idle Extension and empty queue), the candidate artifact hash
    is current, the independent review is ``PASS`` and (where applicable) the dry-run is clean. The
    adapter consumes exactly one grant per protected operation, so a protected write can never reach
    the platform when the Runner has not confirmed its preconditions.
    """
    if not isinstance(operation_id, str) or not operation_id:
        raise AdapterError("runner_authorization_required")
    state = _session_state(repo, run["run_id"])
    grants = state.get("runner_grants")
    record = grants.get(operation_id) if isinstance(grants, dict) else None
    if not isinstance(record, dict) or record.get("consumed"):
        raise AdapterError("runner_authorization_required")
    record["consumed"] = True
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return state


def commit_business(
    repo: Path, run_dir: Path, config_path: Path, manifest_path: Path, operation_id: str | None
) -> dict[str, Any]:
    """Synchronize only confirmed Brief/CQ facts and bind platform IDs before Work Units run."""
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    if run.get("execution_profile") != "local":
        raise AdapterError("local_profile_required")
    manifest = _business_manifest(manifest_path)
    state = _consume_runner_grant(repo, run, operation_id)
    smd.validate_cq_binding_window(run_dir)
    coverage = smd._read_json(run_dir / run["shared_paths"]["coverage"])
    # Refuse an unaccepted CQ before writing the Brief: allowing it through would let later Work
    # Units observe a local CQ that is neither approved nor bound on the platform.
    for local in coverage.get("competency_questions", []):
        local_id = local.get("local_competency_question_id", local.get("competency_question_id"))
        metadata = manifest["questions"].get(local_id)
        if not isinstance(local_id, str) or not isinstance(metadata, dict):
            raise AdapterError("business_question_missing")
        if metadata.get("accepted") is not True:
            raise AdapterError("business_question_not_accepted")
        payload = _question_payload(
            local, metadata, _platform_ontology_id(state, local["ontology_id"])
        )
        source_fields = set(payload["source_brief_fields"])
        confirmed_fields = set(manifest["brief"]["confirmed_fields"])
        if not source_fields <= BRIEF_FIELDS or not source_fields <= confirmed_fields:
            raise AdapterError("business_question_source_not_confirmed")
    brief = manifest["brief"]
    _request(
        config,
        "PATCH",
        f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/brief",
        {"fields": brief["fields"], "confirmed_fields": brief["confirmed_fields"]},
    )
    listed = _request(
        config,
        "GET",
        f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/competency-questions",
    )
    if not isinstance(listed, list):
        # REST returns an array, while the generic bounded client intentionally accepts objects only.
        raise AdapterError("platform_response_invalid")
    bindings: dict[str, str] = {}
    for local in coverage.get("competency_questions", []):
        local_id = local.get("local_competency_question_id", local.get("competency_question_id"))
        metadata = manifest["questions"].get(local_id)
        if not isinstance(local_id, str) or not isinstance(metadata, dict):
            raise AdapterError("business_question_missing")
        payload = _question_payload(
            local, metadata, _platform_ontology_id(state, local["ontology_id"])
        )
        exact = [
            item
            for item in listed
            if item.get("ontology_id") == payload["ontology_id"]
            and _canonical_question(str(item.get("question", "")))
            == _canonical_question(payload["question"])
            and _canonical_query(item.get("query_definition", {}))
            == _canonical_query(payload["query_definition"])
        ]
        existing_id = local.get("platform_competency_question_id")
        bound = [item for item in listed if item.get("id") == existing_id] if existing_id else []
        if existing_id and len(bound) != 1:
            raise AdapterError("business_sync_binding_conflict")
        if len(exact) > 1:
            raise AdapterError("business_sync_ambiguous")
        if bound and exact and exact[0].get("id") == existing_id:
            remote = bound[0]
        elif bound:
            # A prior bound platform CQ is the only record eligible for mutation.  This preserves
            # the binding across a confirmed wording/query correction without creating a duplicate.
            remote = _request(
                config,
                "PATCH",
                f"/competency-questions/{urllib.parse.quote(existing_id, safe='')}",
                {
                    key: payload[key]
                    for key in ("question", "importance", "query_definition", "source_brief_fields")
                },
            )
        elif exact:
            remote = exact[0]
        else:
            remote = _request(
                config,
                "POST",
                f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/competency-questions",
                payload,
            )
        remote_id = remote.get("id")
        if not isinstance(remote_id, str) or not remote_id:
            raise AdapterError("business_sync_invalid_response")
        if remote.get("status") != "approved":
            remote = _request(
                config,
                "POST",
                f"/competency-questions/{urllib.parse.quote(remote_id, safe='')}/status",
                {"status": "approved"},
            )
        # Business confirmation may only approve a CQ.  Testable/pass/fail transitions are owned by
        # `verify`, which calls the platform validation endpoint and records its observed result.
        if metadata.get("make_testable") or metadata.get("validated_execution"):
            raise AdapterError("business_validation_must_execute")
        local["query_definition"] = payload["query_definition"]
        local["source_brief_fields"] = payload["source_brief_fields"]
        bindings[local_id] = remote_id
    smd._atomic_write_json(run_dir / run["shared_paths"]["coverage"], coverage)
    result = smd.bind_platform_competency_questions(run_dir, bindings)
    return _envelope(
        "commit-business", "ok", refs={"run_id": result["run_id"]}, next_action="model_work_units"
    )


def _next_planned_batch(run_dir: Path, ontology_id: str) -> dict[str, Any]:
    run = smd._load_run(run_dir)
    entry = smd._ontology_entry(run, ontology_id)
    plan = smd._read_json(run_dir / entry["batch_plan_path"])
    for batch in plan.get("batches", []):
        if batch.get("state") in {"logical", "materialized", "dry_run_bound"} and all(
            plan["batches"][order].get("state") == "applied"
            for order in batch.get("depends_on_batch_orders", [])
        ):
            return batch
    raise AdapterError("no_dependency_ready_batch")


def _attempt_identity(run_id: str, client_batch_id: str, mode: str) -> str:
    return hashlib.sha256(f"{run_id}:{client_batch_id}:{mode}".encode()).hexdigest()[:48]


def _session_state(repo: Path, run_id: str) -> dict[str, Any]:
    state_path = _ledger(repo, run_id)
    if not state_path.exists():
        raise AdapterError("adapter_state_missing")
    state = _read_json(state_path)
    if not isinstance(state.get("build_session_id"), str):
        raise AdapterError("adapter_state_invalid")
    return state


def _request_for_batch(
    config: dict[str, Any],
    session_id: str,
    batch: dict[str, Any],
    *,
    run_id: str,
    mode: str,
    workspace_version: str,
    lease_token: str | None = None,
) -> dict[str, Any]:
    payload = {
        "client_batch_id": batch["client_batch_id"],
        "ontology_id": batch["ontology_id"],
        "idempotency_key": _attempt_identity(run_id, batch["client_batch_id"], mode),
        "mode": mode,
        "expected_workspace_version": workspace_version,
        "items": batch["items"],
    }
    if lease_token:
        payload["lease_token"] = lease_token
    return _request(
        config,
        "POST",
        f"/build-sessions/{urllib.parse.quote(session_id, safe='')}/modeling-batches",
        payload,
    )


def _save_attempt(
    repo: Path, run_id: str, *, client_batch_id: str, mode: str, immutable_content_hash: str
) -> dict[str, Any]:
    state = _session_state(repo, run_id)
    attempts = state.setdefault("attempts", {})
    identity = _attempt_identity(run_id, client_batch_id, mode)
    batch_attempt = attempts.get(client_batch_id)
    # Earlier local ledgers held one attempt directly under a Batch ID.  Normalize that shape on
    # write so a dry-run and its apply_atomic retry can safely retain distinct stable identities.
    if isinstance(batch_attempt, dict) and "modes" not in batch_attempt:
        legacy_mode = batch_attempt.get("mode")
        batch_attempt = {
            "immutable_content_hash": batch_attempt.get("immutable_content_hash"),
            "modes": {legacy_mode: batch_attempt} if isinstance(legacy_mode, str) else {},
        }
        attempts[client_batch_id] = batch_attempt
    if not isinstance(batch_attempt, dict):
        batch_attempt = {"immutable_content_hash": immutable_content_hash, "modes": {}}
        attempts[client_batch_id] = batch_attempt
    modes = batch_attempt.setdefault("modes", {})
    if not isinstance(modes, dict):
        raise AdapterError("adapter_state_invalid")
    existing = modes.get(mode)
    expected = {
        "mode": mode,
        "idempotency_key": identity,
        "immutable_content_hash": immutable_content_hash,
    }
    if existing and any(existing.get(key) != value for key, value in expected.items()):
        raise AdapterError("attempt_identity_conflict")
    batch_attempt["immutable_content_hash"] = immutable_content_hash
    modes[mode] = {**(existing or {}), **expected}
    _atomic_json(_ledger(repo, run_id), state)
    return state


def _attempt_record(state: dict[str, Any], client_batch_id: str, mode: str) -> dict[str, Any]:
    value = state.get("attempts", {}).get(client_batch_id, {})
    if not isinstance(value, dict):
        return {}
    modes = value.get("modes")
    if isinstance(modes, dict):
        record = modes.get(mode, {})
        return record if isinstance(record, dict) else {}
    return value if value.get("mode") == mode else {}


def _all_attempt_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for value in state.get("attempts", {}).values():
        if not isinstance(value, dict):
            continue
        modes = value.get("modes")
        if isinstance(modes, dict):
            records.extend(record for record in modes.values() if isinstance(record, dict))
        else:
            records.append(value)
    return records


def reconcile_apply(
    repo: Path, run_dir: Path, config_path: Path, ontology_id: str
) -> dict[str, Any]:
    """Look up the original client Batch after an unknown apply outcome; never submit a replacement."""
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _session_state(repo, run["run_id"])
    batch = _next_planned_batch(run_dir, ontology_id)
    attempt = _attempt_record(state, batch["client_batch_id"], "apply_atomic")
    if attempt.get("mode") != "apply_atomic":
        raise AdapterError("apply_reconciliation_missing")
    listed = _request(
        config,
        "GET",
        f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}/modeling-batches",
    )
    rows = listed.get("batches", []) if isinstance(listed, dict) else []
    matches = [row for row in rows if row.get("client_batch_id") == batch["client_batch_id"]]
    if len(matches) != 1:
        return _envelope(
            "reconcile-apply",
            "blocked",
            refs={"client_batch_id": batch["client_batch_id"]},
            error="apply_outcome_unknown",
            next_action="operator_reconcile",
        )
    platform_batch_id = matches[0].get("batch_id") or matches[0].get("id")
    if not isinstance(platform_batch_id, str):
        raise AdapterError("apply_reconciliation_invalid")
    detail = _request(
        config, "GET", f"/modeling-batches/{urllib.parse.quote(platform_batch_id, safe='')}"
    )
    if not isinstance(detail, dict):
        raise AdapterError("apply_reconciliation_invalid")
    attempts = detail.get("attempts", [])
    if not isinstance(attempts, list) or not attempts:
        raise AdapterError("apply_reconciliation_invalid")
    # The detail endpoint returns batch fields plus attempt responses; retain the original Batch and
    # choose its latest platform attempt rather than constructing a replacement submission.
    response = attempts[-1]
    if response.get("mode") != "apply_atomic" or response.get("attempt_status") != "applied":
        return _envelope(
            "reconcile-apply",
            "blocked",
            refs={"client_batch_id": batch["client_batch_id"], "batch_id": platform_batch_id},
            error="apply_outcome_pending",
            next_action="reconcile-apply",
        )
    smd.bind_platform_response(
        run_dir,
        ontology_id,
        batch["client_batch_id"],
        "apply_atomic",
        batch["immutable_content_hash"],
        response,
        context_refreshed=True,
    )
    attempt["platform_batch_id"] = platform_batch_id
    attempt["reconciled"] = True
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return _envelope(
        "reconcile-apply",
        "ok",
        refs={"client_batch_id": batch["client_batch_id"], "batch_id": platform_batch_id},
        next_action="dry-run-next",
    )


def authorize_runner_write(
    repo: Path,
    run_dir: Path,
    operation_id: str,
    *,
    operation: str,
    role_settled: bool,
    artifact_hash: str | None = None,
    review_verdict: str | None = None,
    dry_run_clean: bool = False,
) -> dict[str, Any]:
    """Record one Runner-confirmed authorization for a single protected platform write.

    The Pi Runner calls this only after it has observed ``agent_settled``, an idle Extension with no
    pending message, and an empty queue for the role that produced the protected input, and after it
    has verified the candidate artifact hash, the independent review verdict and (where applicable)
    a clean dry-run. The adapter stores one grant per ``operation_id``; the matching protected write
    consumes it exactly once.
    """
    if not isinstance(operation_id, str) or not operation_id:
        raise AdapterError("runner_authorization_required")
    if not isinstance(operation, str) or not operation.strip():
        raise AdapterError("runner_authorization_invalid")
    if role_settled is not True:
        raise AdapterError("runner_authorization_required")
    if review_verdict is not None and review_verdict not in {"PASS", "REVISE", "BLOCKED"}:
        raise AdapterError("runner_authorization_invalid")
    if artifact_hash is not None and (
        not isinstance(artifact_hash, str) or not artifact_hash.strip()
    ):
        raise AdapterError("runner_authorization_invalid")
    run = smd._load_run(run_dir)
    state = _session_state(repo, run["run_id"])
    grants = state.setdefault("runner_grants", {})
    if not isinstance(grants, dict):
        grants = {}
        state["runner_grants"] = grants
    grants[operation_id] = {
        "operation_id": operation_id,
        "operation": operation.strip(),
        "role_settled": True,
        "artifact_hash": artifact_hash,
        "review_verdict": review_verdict,
        "dry_run_clean": bool(dry_run_clean),
        "consumed": False,
    }
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return _envelope(
        "authorize-runner-write",
        "ok",
        refs={"operation_id": operation_id, "operation": operation.strip()},
        next_action="execute_protected_write",
    )


def _mark_cq_recovery_required(state: dict[str, Any], remote_id: str) -> None:
    pending = state.get("cq_recovery_required", [])
    if not isinstance(pending, list):
        pending = []
    state["cq_recovery_required"] = sorted(
        {item for item in pending if isinstance(item, str) and item} | {remote_id}
    )


def _clear_cq_recovery_requirement(state: dict[str, Any], remote_id: str) -> None:
    pending = state.get("cq_recovery_required", [])
    if not isinstance(pending, list):
        return
    remaining = [item for item in pending if isinstance(item, str) and item != remote_id]
    if remaining:
        state["cq_recovery_required"] = remaining
    else:
        state.pop("cq_recovery_required", None)


def _cq_recovery_is_required(state: dict[str, Any], remote_id: str) -> bool:
    pending = state.get("cq_recovery_required", [])
    return isinstance(pending, list) and remote_id in pending


def _blocked_failed_cq(
    repo: Path, run_id: str, state: dict[str, Any], ontology_id: str, remote_id: str
) -> dict[str, Any]:
    _mark_cq_recovery_required(state, remote_id)
    _atomic_json(_ledger(repo, run_id), state)
    return _envelope(
        "verify",
        "blocked",
        refs={"ontology_id": ontology_id, "competency_question_id": remote_id},
        error="competency_question_failed",
        next_action="retry_verify",
    )


def verify(
    repo: Path,
    run_dir: Path,
    config_path: Path,
    ontology_id: str,
    verification_path: Path,
    operation_id: str | None,
) -> dict[str, Any]:
    """Persist only observed verification and execute supported bound CQ validation."""
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _consume_runner_grant(repo, run, operation_id)
    verification = _read_json(verification_path)
    coverage = smd._read_json(run_dir / run["shared_paths"]["coverage"])
    listed = _request(
        config,
        "GET",
        f"/projects/{urllib.parse.quote(config['project_id'], safe='')}/competency-questions",
    )
    if not isinstance(listed, list):
        raise AdapterError("platform_response_invalid")
    by_id = {item.get("id"): item for item in listed if isinstance(item.get("id"), str)}
    for local in coverage.get("competency_questions", []):
        if local.get("ontology_id") != ontology_id:
            continue
        remote_id = local.get("platform_competency_question_id")
        query = local.get("query_definition", {})
        if remote_id and query:
            current = by_id.get(remote_id)
            if not isinstance(current, dict):
                raise AdapterError("competency_question_binding_missing")
            status = current.get("status")
            if status == "failed":
                if not _cq_recovery_is_required(state, remote_id):
                    return _blocked_failed_cq(repo, run["run_id"], state, ontology_id, remote_id)
                current = _request(
                    config,
                    "POST",
                    f"/competency-questions/{urllib.parse.quote(remote_id, safe='')}/status",
                    {"status": "testable"},
                )
                status = current.get("status")
            elif status == "approved":
                current = _request(
                    config,
                    "POST",
                    f"/competency-questions/{urllib.parse.quote(remote_id, safe='')}/status",
                    {"status": "testable"},
                )
                status = current.get("status")
            if status == "passed":
                _clear_cq_recovery_requirement(state, remote_id)
                continue
            if status != "testable":
                raise AdapterError("competency_question_not_testable")
            observed = _request(
                config,
                "POST",
                f"/competency-questions/{urllib.parse.quote(remote_id, safe='')}/validate",
            )
            observed_status = observed.get("status")
            if observed_status == "failed":
                return _blocked_failed_cq(repo, run["run_id"], state, ontology_id, remote_id)
            if observed_status != "passed":
                raise AdapterError("competency_question_validation_invalid")
            _clear_cq_recovery_requirement(state, remote_id)
    _atomic_json(_ledger(repo, run["run_id"]), state)
    entry = smd._ontology_entry(run, ontology_id)
    smd._atomic_write_json(run_dir / entry["verification_path"], verification)
    result = smd.validate_verification(run_dir, ontology_id)
    if result.get("verdict") != "PASS":
        return _envelope(
            "verify",
            "blocked",
            refs={"ontology_id": ontology_id},
            error="verification_not_passed",
            next_action="resolve_verification",
        )
    return _envelope("verify", "ok", refs={"ontology_id": ontology_id}, next_action="finish")


def finish(
    repo: Path, run_dir: Path, config_path: Path, operation_id: str | None
) -> dict[str, Any]:
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _consume_runner_grant(repo, run, operation_id)
    ontology_ids = [entry.get("ontology_id") for entry in run.get("ontologies", [])]
    if not ontology_ids or not all(
        isinstance(ontology_id, str) and ontology_id for ontology_id in ontology_ids
    ):
        raise AdapterError("run_ontology_invalid")
    for ontology_id in ontology_ids:
        verification = smd.validate_verification(run_dir, ontology_id)
        if verification.get("verdict") != "PASS":
            raise AdapterError("verification_not_passed")
        plan = smd.validate_batch_plan(run_dir, ontology_id)
        if any(batch.get("state") != "applied" for batch in plan.get("batches", [])):
            raise AdapterError("batches_not_applied")
    detail = _request(
        config, "GET", f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}"
    )
    session = detail.get("session", detail)
    if not isinstance(session.get("revision"), int):
        raise AdapterError("build_session_invalid")
    _request(
        config,
        "POST",
        f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}:complete",
        {
            "client_request_id": _attempt_identity(run["run_id"], "session", "complete"),
            "expected_revision": session["revision"],
            "summary": "Local modeling verification passed",
            "unresolved_items": [],
        },
    )
    state["terminal_state"] = "completed"
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return _envelope(
        "finish",
        "ok",
        refs={"build_session_id": state["build_session_id"]},
        next_action="done",
    )


def cancel(repo: Path, run_dir: Path, config_path: Path, reason: str) -> dict[str, Any]:
    if not isinstance(reason, str) or not reason.strip():
        raise AdapterError("abandonment_reason_required")
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _session_state(repo, run["run_id"])
    if any(
        value.get("mode") == "apply_atomic" and not value.get("reconciled")
        for value in _all_attempt_records(state)
    ):
        raise AdapterError("in_flight_batch_requires_reconciliation")
    listed = _request(
        config,
        "GET",
        f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}/modeling-batches",
    )
    rows = listed.get("batches", []) if isinstance(listed, dict) else []
    if any(
        isinstance(row, dict)
        and row.get("latest_attempt", {}).get("attempt_status") in {"applying", "recovering"}
        for row in rows
    ):
        raise AdapterError("in_flight_batch_requires_reconciliation")
    detail = _request(
        config, "GET", f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}"
    )
    session = detail.get("session", detail)
    if not isinstance(session.get("revision"), int):
        raise AdapterError("build_session_invalid")
    _request(
        config,
        "POST",
        f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}:cancel",
        {
            "client_request_id": _attempt_identity(run["run_id"], "session", "cancel"),
            "expected_revision": session["revision"],
            "reason": reason.strip(),
        },
    )
    state["terminal_state"] = "cancelled"
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return _envelope(
        "cancel", "ok", refs={"build_session_id": state["build_session_id"]}, next_action="done"
    )


def dry_run_next(
    repo: Path, run_dir: Path, config_path: Path, ontology_id: str, operation_id: str | None
) -> dict[str, Any]:
    config, limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _consume_runner_grant(repo, run, operation_id)
    platform_ontology_id = _platform_ontology_id(state, ontology_id)
    smd.validate_review(run_dir, ontology_id)
    plan = smd.validate_batch_plan(run_dir, ontology_id)
    if plan.get("limits") != limits:
        raise AdapterError("local_capacity_mismatch")
    next_batch = _next_planned_batch(run_dir, ontology_id)
    materialized = smd.materialize_batch(
        run_dir, ontology_id, next_batch["client_batch_id"], plan["attempt_templates"]
    )
    _save_attempt(
        repo,
        run["run_id"],
        client_batch_id=materialized["client_batch_id"],
        mode="dry_run",
        immutable_content_hash=materialized["immutable_content_hash"],
    )
    context = _request(
        config,
        "GET",
        f"/ontologies/{urllib.parse.quote(platform_ontology_id, safe='')}/modeling-context",
    )
    version = context.get("workspace", {}).get("workspace_version")
    if not isinstance(version, str) or not version:
        raise AdapterError("workspace_context_invalid")
    response = _request_for_batch(
        config,
        state["build_session_id"],
        {
            "client_batch_id": materialized["client_batch_id"],
            "ontology_id": platform_ontology_id,
            "items": materialized["items"],
        },
        run_id=run["run_id"],
        mode="dry_run",
        workspace_version=version,
    )
    findings = response.get("findings", [])
    if response.get("attempt_status") != "validated":
        return _envelope(
            "dry-run-next",
            "blocked",
            refs={"client_batch_id": materialized["client_batch_id"]},
            findings=findings if isinstance(findings, list) else [],
            error="dry_run_findings",
            next_action="review_findings",
        )
    smd.bind_platform_response(
        run_dir,
        ontology_id,
        materialized["client_batch_id"],
        "dry_run",
        materialized["immutable_content_hash"],
        response,
    )
    return _envelope(
        "dry-run-next",
        "ok",
        refs={
            "client_batch_id": materialized["client_batch_id"],
            "batch_id": str(response.get("batch_id", "")),
        },
        next_action="apply-next",
    )


def apply_next(
    repo: Path, run_dir: Path, config_path: Path, ontology_id: str, operation_id: str | None
) -> dict[str, Any]:
    config, _limits = load_config(repo, config_path)
    run = smd._load_run(run_dir)
    state = _consume_runner_grant(repo, run, operation_id)
    platform_ontology_id = _platform_ontology_id(state, ontology_id)
    batch = _next_planned_batch(run_dir, ontology_id)
    if batch.get("state") != "dry_run_bound":
        raise AdapterError("dry_run_required")
    detail = _request(
        config, "GET", f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}"
    )
    session = detail.get("session", detail)
    revision = session.get("revision")
    if not isinstance(revision, int):
        raise AdapterError("build_session_invalid")
    lease = _request(
        config,
        "POST",
        f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}/ontology-leases/{urllib.parse.quote(platform_ontology_id, safe='')}:acquire",
        {
            "client_request_id": _attempt_identity(
                run["run_id"], batch["client_batch_id"], "lease"
            ),
            "expected_session_revision": revision,
        },
    )
    token = lease.get("lease_token")
    lease_revision = lease.get("lease_revision")
    if not isinstance(token, str) or not isinstance(lease_revision, int):
        raise AdapterError("lease_acquire_invalid")
    _save_attempt(
        repo,
        run["run_id"],
        client_batch_id=batch["client_batch_id"],
        mode="apply_atomic",
        immutable_content_hash=batch["immutable_content_hash"],
    )
    response: dict[str, Any] | None = None
    unknown_error: AdapterError | None = None
    release_error: AdapterError | None = None
    try:
        context = _request(
            config,
            "GET",
            f"/ontologies/{urllib.parse.quote(platform_ontology_id, safe='')}/modeling-context",
        )
        version = context.get("workspace", {}).get("workspace_version")
        if not isinstance(version, str) or not version:
            raise AdapterError("workspace_context_invalid")
        response = _request_for_batch(
            config,
            state["build_session_id"],
            {
                "client_batch_id": batch["client_batch_id"],
                "ontology_id": platform_ontology_id,
                "items": batch.get("materialized_items", []),
            },
            run_id=run["run_id"],
            mode="apply_atomic",
            workspace_version=version,
            lease_token=token,
        )
    except AdapterError as exc:
        unknown_error = exc
    finally:
        # The token never enters the ledger or result envelope. A failed release remains a bounded
        # platform failure and must be reconciled through the same stable Batch identity.
        try:
            _request(
                config,
                "POST",
                f"/build-sessions/{urllib.parse.quote(state['build_session_id'], safe='')}/ontology-leases/{urllib.parse.quote(platform_ontology_id, safe='')}:release",
                {
                    "client_request_id": _attempt_identity(
                        run["run_id"], batch["client_batch_id"], "release"
                    ),
                    "lease_token": token,
                    "expected_lease_revision": lease_revision,
                },
            )
        except AdapterError as exc:
            release_error = exc
    if unknown_error is not None or release_error is not None:
        return _envelope(
            "apply-next",
            "blocked",
            refs={"client_batch_id": batch["client_batch_id"]},
            error="apply_outcome_unknown",
            next_action="reconcile-apply",
        )
    assert response is not None
    if response.get("attempt_status") != "applied":
        state = _session_state(repo, run["run_id"])
        _attempt_record(state, batch["client_batch_id"], "apply_atomic")["reconciled"] = True
        _atomic_json(_ledger(repo, run["run_id"]), state)
        return _envelope(
            "apply-next",
            "blocked",
            refs={"client_batch_id": batch["client_batch_id"]},
            findings=response.get("findings", [])
            if isinstance(response.get("findings"), list)
            else [],
            error="apply_not_completed",
            next_action="reconcile",
        )
    smd.bind_platform_response(
        run_dir,
        ontology_id,
        batch["client_batch_id"],
        "apply_atomic",
        batch["immutable_content_hash"],
        response,
        context_refreshed=True,
    )
    state = _session_state(repo, run["run_id"])
    _attempt_record(state, batch["client_batch_id"], "apply_atomic").update(
        {"platform_batch_id": response.get("batch_id"), "reconciled": True}
    )
    _atomic_json(_ledger(repo, run["run_id"]), state)
    return _envelope(
        "apply-next",
        "ok",
        refs={
            "client_batch_id": batch["client_batch_id"],
            "batch_id": str(response.get("batch_id", "")),
        },
        next_action="dry-run-next",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="workspaces/modeling-adapter/local.json")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "status"):
        item = subparsers.add_parser(name)
        item.add_argument("run_dir")
    commit = subparsers.add_parser("commit-business")
    commit.add_argument("run_dir")
    commit.add_argument("--business", required=True)
    commit.add_argument("--operation-id", required=True)
    authorize = subparsers.add_parser("authorize-runner-write")
    authorize.add_argument("run_dir")
    authorize.add_argument("--operation-id", required=True)
    authorize.add_argument("--operation", required=True)
    authorize.add_argument("--artifact-hash")
    authorize.add_argument("--review-verdict", choices=["PASS", "REVISE", "BLOCKED"])
    authorize.add_argument("--dry-run-clean", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("run_dir")
    verify_parser.add_argument("ontology_id")
    verify_parser.add_argument("--verification", required=True)
    verify_parser.add_argument("--operation-id", required=True)
    for name in ("dry-run-next", "apply-next", "reconcile-apply"):
        item = subparsers.add_parser(name)
        item.add_argument("run_dir")
        item.add_argument("ontology_id")
        if name != "reconcile-apply":
            item.add_argument("--operation-id", required=True)
    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("run_dir")
    finish_parser.add_argument("--operation-id", required=True)
    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument("run_dir")
    cancel_parser.add_argument("--reason", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo = Path(__file__).resolve().parents[2]
    try:
        config_path = _repo_path(repo, args.config, "config")
        if args.action == "start":
            result = start(repo, Path(args.run_dir).resolve(), config_path)
        elif args.action == "status":
            result = status(repo, Path(args.run_dir).resolve(), config_path)
        elif args.action == "commit-business":
            result = commit_business(
                repo,
                Path(args.run_dir).resolve(),
                config_path,
                Path(args.business).resolve(),
                args.operation_id,
            )
        elif args.action == "authorize-runner-write":
            result = authorize_runner_write(
                repo,
                Path(args.run_dir).resolve(),
                args.operation_id,
                operation=args.operation,
                role_settled=True,
                artifact_hash=args.artifact_hash,
                review_verdict=args.review_verdict,
                dry_run_clean=bool(args.dry_run_clean),
            )
        elif args.action == "dry-run-next":
            result = dry_run_next(
                repo, Path(args.run_dir).resolve(), config_path, args.ontology_id, args.operation_id
            )
        elif args.action == "apply-next":
            result = apply_next(
                repo, Path(args.run_dir).resolve(), config_path, args.ontology_id, args.operation_id
            )
        elif args.action == "reconcile-apply":
            result = reconcile_apply(
                repo, Path(args.run_dir).resolve(), config_path, args.ontology_id
            )
        elif args.action == "verify":
            result = verify(
                repo,
                Path(args.run_dir).resolve(),
                config_path,
                args.ontology_id,
                Path(args.verification).resolve(),
                args.operation_id,
            )
        elif args.action == "finish":
            result = finish(repo, Path(args.run_dir).resolve(), config_path, args.operation_id)
        else:
            result = cancel(repo, Path(args.run_dir).resolve(), config_path, args.reason)
    except (AdapterError, smd.DirectoryContractError, OSError) as exc:
        result = _envelope(args.action, "blocked", next_action="resolve_blocker", error=str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
