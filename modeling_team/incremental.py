"""R4.0-029 trusted Host preparation; Delivery remains the only supervisor."""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import yaml

from .contracts import load_multi_slice_team_configuration
from .host_ops import get_run_status, read_launch_record
from .model_routing import load_team_model_profile
from .platform_scope import PlatformScope
from .staged_decisions import _atomic_write, canonical_json_digest


class IncrementalError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(detail)


def platform_envelope(response):
    """Unwrap supported MCP transport shapes, preserving error outcomes."""
    if not isinstance(response, dict) or response.get("isError") is True:
        return response
    if isinstance(response.get("structuredContent"), dict):
        return platform_envelope(response["structuredContent"])
    for part in response.get("content", []):
        if isinstance(part, dict) and part.get("type") == "text":
            try:
                return platform_envelope(json.loads(part["text"]))
            except (KeyError, ValueError, TypeError):
                return response
    return response


def _required(value, field):
    if not isinstance(value, str) or not value.strip():
        raise IncrementalError("incremental_input_invalid", f"{field} is required")
    return value


def _path(root, value):
    path = (root / _required(value, "path")).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise IncrementalError("incremental_input_invalid", f"invalid repository file: {value}")
    return path


def validate_request(request: dict, *, check_authorization: bool = True) -> dict:
    if not isinstance(request, dict):
        raise IncrementalError("incremental_input_invalid", "request must be an object")
    required = {"request_id", "project_id", "ontology_ids", "objective", "approved_sources",
                "profile", "model_profile", "authorization_reference", "valid_until",
                "production_start_limit", "acceptance_scope"}
    optional = {"allow_new_ontologies", "feedback_ids", "base_url", "service_tier"}
    if required - request.keys() or request.keys() - required - optional:
        raise IncrementalError("incremental_input_invalid", "request fields differ from the 029 contract")
    for field in required - {"ontology_ids", "approved_sources", "production_start_limit"}:
        _required(request[field], field)
    try:
        request = dict(request, request_id=str(UUID(request["request_id"])))
        deadline = datetime.fromisoformat(request["valid_until"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncrementalError("incremental_input_invalid", "request_id UUID or valid_until is invalid") from exc
    if deadline.tzinfo is None or (check_authorization and datetime.now(UTC) >= deadline):
        raise IncrementalError("incremental_authorization_expired", "authorization is expired or lacks a timezone")
    if type(request["production_start_limit"]) is not int or request["production_start_limit"] < 1:
        raise IncrementalError("incremental_authorization_exhausted", "no authorized production starts remain")
    ids = request["ontology_ids"]
    if (not isinstance(ids, list) or not ids
            or not all(isinstance(x, str) and x.strip() for x in ids)
            or len(set(ids)) != len(ids)):
        raise IncrementalError("incremental_scope_invalid", "ontology_ids must be nonempty unique explicit IDs")
    if type(request.get("allow_new_ontologies", False)) is not bool:
        raise IncrementalError("incremental_scope_invalid", "allow_new_ontologies must be boolean")
    if not isinstance(request["approved_sources"], list) or not request["approved_sources"]:
        raise IncrementalError("incremental_sources_invalid", "approved business sources are required")
    feedback = request.get("feedback_ids", [])
    if (not isinstance(feedback, list) or not all(isinstance(x, str) and x for x in feedback)
            or len(set(feedback)) != len(feedback)):
        raise IncrementalError("incremental_feedback_invalid", "feedback_ids must be unique strings")
    return request


def read_public_feedback(repository_root: Path, base_url: str, project_id: str,
                         feedback_id: str, ontology_ids: list[str]) -> dict:
    """Trusted Host projects a selected report; private snapshots/history stay private."""
    from urllib.parse import quote
    from .__main__ import _bootstrap_helpers
    from .platform_scope import _http

    create, revoke = _bootstrap_helpers(repository_root)
    key, key_id = create()
    try:
        status, record = _http(base_url, "GET", "/api/semantic/feedback/" +
                               quote(feedback_id, safe=""), None, key)
    finally:
        revoke(key_id)
    if status != 200 or not isinstance(record, dict) or record.get("project_id") != project_id:
        raise IncrementalError("incremental_feedback_unavailable", "Selected feedback is unavailable in the authorized Project")
    submission = record.get("submission", {})
    query = submission.get("query_request", {})
    if (query.get("project_id") != project_id or
            not set(query.get("ontology_ids") or []).issubset(ontology_ids)):
        raise IncrementalError("incremental_feedback_invalid", "Feedback query exceeds the authorized model scope")
    observation = json.dumps({"query_request": query, "reasons": submission.get("reasons"),
                              "description": submission.get("description"),
                              "snapshot_complete": submission.get("snapshot_complete", False),
                              "notice": "Client observation, not verified model truth; private result snapshot omitted"},
                             ensure_ascii=False)
    return {"project_id": project_id, "feedback_id": record.get("feedback_id"),
            "observation": observation, "status": record.get("outcome", "pending")}


def _snapshot(path: Path, body: str) -> None:
    if path.exists():
        if path.read_text() != body:
            raise IncrementalError("incremental_snapshot_conflict", f"retained snapshot changed: {path.name}")
        return
    path.write_text(body)
    path.chmod(0o444)


def prepare_incremental(request: dict, *, repository_root: Path, scope_probe=None,
                        feedback_reader=None) -> dict:
    """Prepare an immutable normal v4 Task, with no Agent or semantic start."""
    root = repository_root.resolve()
    request = validate_request(request, check_authorization=False)
    rid = request["request_id"]
    package = root / "workspaces/incremental-requests" / rid
    package.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (package.parent / (rid + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = package / "prepared.json"
        if manifest.exists():
            existing = json.loads(manifest.read_text())
            if existing["request_digest"] != canonical_json_digest(request):
                raise IncrementalError("incremental_request_conflict", "request_id already binds different content")
            return existing
        validate_request(request)
        scope = {"mode": "existing", "project_id": request["project_id"],
                 "ontology_ids": request["ontology_ids"],
                 "allow_new_ontologies": request.get("allow_new_ontologies", False)}
        if scope_probe is None:
            from .__main__ import _bootstrap_helpers
            create, revoke = _bootstrap_helpers(root)
            bound = PlatformScope(request.get("base_url", "http://127.0.0.1:8001"),
                                  "incremental-" + rid, create, revoke)
            bound.admin_key, bound.admin_key_id = create()
            try:
                # Read-only pre-launch check, no protocol credential or Session.
                bound._existing(scope)
                before = bound.existing_context_before
            finally:
                revoke(bound.admin_key_id)
        else:
            before = scope_probe(scope)
        template = yaml.safe_load((root / "modeling_team/tasks/r4-0-029-existing-model-incremental.yaml").read_text())
        sources = []
        for source in request["approved_sources"]:
            if not isinstance(source, dict) or set(source) != {"path", "source_reference", "valid_at"}:
                raise IncrementalError("incremental_sources_invalid", "source requires path, source_reference and valid_at")
            _required(source["source_reference"], "source_reference")
            _required(source["valid_at"], "valid_at")
            path = _path(root, source["path"])
            relative = path.relative_to(root)
            if (relative.parts[:2] == ("workspaces", "modeling-runs")
                    or "private" in relative.parts or "tests" in relative.parts):
                raise IncrementalError("incremental_sources_invalid", "old runs and private/test material are not production sources")
            content = path.read_text()
            if not content.strip():
                raise IncrementalError("incremental_sources_invalid", f"source has no body: {relative}")
            sources.append((source, content))
        public_feedback = []
        for fid in request.get("feedback_ids", []):
            if feedback_reader is None:
                feedback = read_public_feedback(root, request.get("base_url", "http://127.0.0.1:8001"),
                                                request["project_id"], fid, request["ontology_ids"])
            else:
                feedback = feedback_reader(request["project_id"], fid)
            if (not isinstance(feedback, dict) or feedback.get("project_id") != request["project_id"]
                    or feedback.get("feedback_id") != fid
                    or not all(isinstance(feedback.get(key), str) and feedback[key].strip()
                               for key in ("observation", "status"))):
                raise IncrementalError("incremental_feedback_invalid", "feedback Project/ID binding differs")
            # Whitelist the public projection; never pass private Judge material.
            public_feedback.append({key: feedback[key] for key in
                                    ("project_id", "feedback_id", "observation", "status")})
        package.mkdir(exist_ok=True, mode=0o700)
        template["objective"] += "\nThis round's authorized objective: " + request["objective"]
        template["objective"] += "\nThis round's acceptance scope: " + request["acceptance_scope"]
        for index, (source, content) in enumerate(sources):
            target = package / f"source-{index}.md"
            body = f"Source: {source['source_reference']}\nValid at: {source['valid_at']}\n\n" + content
            _snapshot(target, body)
            target.chmod(0o444)
            template["role_sources"].append({"path": str(target.relative_to(root)),
                "classification": "business-source", "roles": ["coordinator", "modeling", "competency-question"]})
        if public_feedback:
            target = package / "public-feedback.json"
            _atomic_write(target, {"feedback": public_feedback})
            target.chmod(0o444)
            template["role_sources"].append({"path": str(target.relative_to(root)),
                "classification": "business-source", "roles": ["coordinator", "modeling", "competency-question"]})
        task_path, scope_path = package / "task.yaml", package / "scope.yaml"
        for target, value in ((task_path, template), (scope_path, scope), (package / "request.yaml", request)):
            _snapshot(target, yaml.safe_dump(value, allow_unicode=True, sort_keys=False))
            target.chmod(0o444)
        profile = _path(root, request["profile"])
        load_multi_slice_team_configuration(profile, task_path, root=root)
        load_team_model_profile(root, request["model_profile"])
        run_id, session_id = "incremental-" + rid, "delivery-incremental-" + rid
        config = {"session_id": session_id, "project_id": request["project_id"],
                  "authorization_reference": request["authorization_reference"],
                  "authorization_valid_until": request["valid_until"],
                  "production_start_limit": request["production_start_limit"],
                  "allowed_operations": ["read", "supervise", "production", "evaluation"],
                  "model_profile": request["model_profile"], "profile": str(profile.relative_to(root)),
                  "task": str(task_path.relative_to(root)), "scope": str(scope_path.relative_to(root)),
                  "allowed_sources": [x["path"] for x in template["role_sources"]],
                  "readback_scope": scope, "incremental_request_id": rid,
                  "incremental_run_id": run_id, "objective": template["objective"],
                  "base_url": request.get("base_url", "http://127.0.0.1:8001"),
                  "service_tier": request.get("service_tier", "unset")}
        config_path = package / "delivery.yaml"
        _snapshot(config_path, yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
        config_path.chmod(0o444)
        result = {"request_id": rid, "request_digest": canonical_json_digest(request),
                  "session_id": session_id, "run_id": run_id, "config": str(config_path.relative_to(root)),
                  "current_scope": before, "status": "prepared", "semantic_start": "not_observed",
                  "query": {"status": "get_run_status", "events": "get_run_events",
                            "delivery": f"workspaces/delivery-sessions/{session_id}/session.json"}}
        _atomic_write(manifest, result)
        return result


def start_incremental(request_path: Path, *, repository_root: Path, launcher=None,
                      scope_probe=None, feedback_reader=None) -> dict:
    request = yaml.safe_load(request_path.read_text())
    result = prepare_incremental(request, repository_root=repository_root,
                                 scope_probe=scope_probe, feedback_reader=feedback_reader)
    root = repository_root.resolve()
    package = root / "workspaces/incremental-requests" / result["request_id"]
    with (package / "launch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = read_launch_record(result["run_id"], repository_root=root)
        if record is not None:
            return {**result, "status": "production_launch_observed", "launch": record,
                    "run_status": get_run_status(run_id=result["run_id"], repository_root=root)}
        receipt_path = package / "delivery-launch.json"
        if receipt_path.exists():
            return {**result, "delivery_launch": json.loads(receipt_path.read_text()),
                    "status": "delivery_launch_recorded", "retry": "observe the same session/run; use delivery --resume for a confirmed interrupted supervisor"}
        validate_request(request)
        receipt = {"status": "unknown", "request_id": result["request_id"], "pid": None}
        _atomic_write(receipt_path, receipt)
        with (package / "delivery.out.log").open("ab") as out, (package / "delivery.err.log").open("ab") as err:
            process = (launcher or subprocess.Popen)(
                [sys.executable, "-m", "modeling_team", "delivery", "--config", result["config"]],
                cwd=str(root), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True)
        receipt.update(status="accepted", pid=process.pid)
        _atomic_write(receipt_path, receipt)
        return {**result, "status": "delivery_launch_accepted", "delivery_launch": receipt,
                "note": "Delivery launch acceptance is not semantic start or task completion"}
