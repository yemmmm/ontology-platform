#!/usr/bin/env python3
"""Deterministic Modeling Batch exchange for the visible M4 file spool.

This helper owns only transport mechanics.  A caller supplies the candidate
projection and expected attempt result; it validates only structural references
and never interprets candidate business semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path


class BatchExchangeError(RuntimeError):
    """A local Batch-exchange contract violation."""


FIRST_VALID_INSTANCE_EXPECTED = "validated_or_shacl_correction"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reject_item_refs_outside_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "item_ref":
                raise BatchExchangeError("item_ref is allowed only inside payload")
            _reject_item_refs_outside_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_item_refs_outside_payload(nested)


def _validate_payload_item_refs(
    value: object,
    *,
    prior_item_ids: set[str],
    dependencies: list[object],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "item_ref":
                if (
                    not isinstance(nested, dict)
                    or set(nested) != {"client_item_id", "output"}
                    or not _non_empty_string(nested.get("client_item_id"))
                    or nested.get("output") not in {"resource_id", "resource_iri"}
                ):
                    raise BatchExchangeError("payload item_ref is malformed")
                referenced_id = nested["client_item_id"]
                if referenced_id not in prior_item_ids:
                    raise BatchExchangeError("payload item_ref must reference a prior item")
                if referenced_id not in dependencies:
                    raise BatchExchangeError("payload item_ref must be listed in depends_on")
            else:
                _validate_payload_item_refs(
                    nested,
                    prior_item_ids=prior_item_ids,
                    dependencies=dependencies,
                )
    elif isinstance(value, list):
        for nested in value:
            _validate_payload_item_refs(
                nested,
                prior_item_ids=prior_item_ids,
                dependencies=dependencies,
            )


def validate_candidate_projection(candidate: object) -> dict[str, object]:
    """Validate the answer-free candidate structure before it can be published."""
    if (
        not isinstance(candidate, dict)
        or set(candidate) != {"client_batch_id", "items"}
        or not _non_empty_string(candidate.get("client_batch_id"))
        or not isinstance(candidate.get("items"), list)
    ):
        raise BatchExchangeError("candidate must contain only client_batch_id and items")

    items = candidate["items"]
    prior_item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise BatchExchangeError("candidate items must be objects")
        item_id = item.get("client_item_id")
        if not _non_empty_string(item_id) or item_id in prior_item_ids:
            raise BatchExchangeError("candidate client_item_id values must be unique non-empty strings")
        dependencies = item.get("depends_on")
        if not isinstance(dependencies, list) or not all(
            _non_empty_string(dependency) and dependency in prior_item_ids
            for dependency in dependencies
        ):
            raise BatchExchangeError("depends_on must contain only prior client item ID strings")
        for key, value in item.items():
            if key == "item_ref":
                raise BatchExchangeError("item_ref is allowed only inside payload")
            if key != "payload":
                _reject_item_refs_outside_payload(value)
        if "payload" in item:
            _validate_payload_item_refs(
                item["payload"],
                prior_item_ids=prior_item_ids,
                dependencies=dependencies,
            )
        prior_item_ids.add(item_id)
    return {"client_batch_id": candidate["client_batch_id"], "items": items}


def check_candidate(candidate_path: Path) -> dict[str, object]:
    """Read and structurally validate a candidate without runtime or spool effects."""
    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BatchExchangeError("candidate is not a JSON object") from error
    projection = validate_candidate_projection(candidate)
    return {
        "candidate_sha256": hashlib.sha256(canonical_json(projection)).hexdigest(),
        "status": "valid",
    }


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(canonical_json(value))
    os.replace(temporary, path)


class BatchExchange:
    """Freeze a candidate projection and advance only from protected responses."""

    def __init__(
        self,
        *,
        runtime_path: Path,
        request_dir: Path,
        response_dir: Path,
        response_timeout_seconds: float = 30,
    ) -> None:
        self.runtime_path = runtime_path
        self.request_dir = request_dir
        self.response_dir = response_dir
        self.response_timeout_seconds = response_timeout_seconds

    def _runtime(self) -> dict[str, object]:
        try:
            value = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BatchExchangeError("runtime record is unavailable") from error
        if not isinstance(value, dict) or not isinstance(value.get("run_tag"), str):
            raise BatchExchangeError("runtime record has no protected run tag")
        if value.get("terminal_status") == "BLOCKED":
            raise BatchExchangeError("batch exchange is blocked")
        return value

    def _save(self, runtime: dict[str, object]) -> None:
        _atomic_json(self.runtime_path, runtime)

    def _block(self, reason: str) -> None:
        try:
            runtime = self._runtime()
        except BatchExchangeError:
            return
        runtime["terminal_status"] = "BLOCKED"
        runtime["block_reason"] = reason
        self._save(runtime)

    def _state(self, runtime: dict[str, object]) -> dict[str, object]:
        state = runtime.get("batch_exchange")
        if not isinstance(state, dict):
            state = {}
            runtime["batch_exchange"] = state
        return state

    def _version(self, runtime: dict[str, object]) -> str:
        value = self._state(runtime).get("workspace_version")
        if not isinstance(value, str) or not value:
            raise BatchExchangeError("initial workspace version was not seeded")
        return value

    def _admit_dry_run(self, runtime: dict[str, object], expected: str) -> None:
        """Permit only the next Batch action in the bounded correction path."""
        state = self._state(runtime)
        frozen = state.get("frozen")
        if isinstance(frozen, dict) and frozen.get("applied") is not True:
            raise BatchExchangeError("validated freeze requires apply before another dry-run")
        if state.get("correction_pending") is True and expected != "validated":
            raise BatchExchangeError("correction dry-run must expect validated")

    def _projection(self, candidate_path: Path) -> dict[str, object]:
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BatchExchangeError("candidate is not a JSON object") from error
        return validate_candidate_projection(candidate)

    def check(self, candidate_path: Path) -> dict[str, object]:
        """Validate a candidate without reading or changing runtime state."""
        return check_candidate(candidate_path)

    def _identifiers(self, runtime: dict[str, object], *, apply: bool) -> tuple[str, str, str | None]:
        resource_ids = runtime.get("resource_ids")
        if not isinstance(resource_ids, dict):
            raise BatchExchangeError("runtime resource IDs are unavailable")
        session_id = resource_ids.get("build_session_id")
        scoped_id = resource_ids.get("ontology_id")
        if not isinstance(session_id, str) or not session_id or not isinstance(scoped_id, str) or not scoped_id:
            raise BatchExchangeError("runtime resource IDs are incomplete")
        token: str | None = None
        if apply:
            lease = runtime.get("lease")
            token = lease.get("token") if isinstance(lease, dict) else None
            if not isinstance(token, str) or not token:
                raise BatchExchangeError("runtime lease token is unavailable")
        return session_id, scoped_id, token

    def _publish(self, request: dict[str, object]) -> dict[str, object]:
        request_id = request["id"]
        if not isinstance(request_id, str):
            raise BatchExchangeError("request ID is invalid")
        target = self.request_dir / f"{request_id}.json"
        if target.exists():
            raise BatchExchangeError("request ID already exists")
        _atomic_json(target, request)
        response_path = self.response_dir / f"{request_id}.json"
        deadline = time.monotonic() + self.response_timeout_seconds
        while time.monotonic() < deadline:
            if response_path.is_file():
                try:
                    response = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise BatchExchangeError("spool response is invalid") from error
                if not isinstance(response, dict) or response.get("id") != request_id:
                    raise BatchExchangeError("spool response does not match request")
                return response
            time.sleep(0.01)
        raise BatchExchangeError("spool response timed out")

    @staticmethod
    def _body(response: dict[str, object]) -> dict[str, object]:
        status = response.get("status")
        body = response.get("body")
        if not isinstance(status, int) or not 200 <= status < 300 or not isinstance(body, dict):
            raise BatchExchangeError("unexpected HTTP response")
        return body

    @staticmethod
    def _is_shacl_correction_response(response_body: dict[str, object]) -> bool:
        """Accept only the M4 first-valid-instance correction branch."""
        findings = response_body.get("findings")
        if not isinstance(findings, list):
            return False
        blocking_findings = [
            finding
            for finding in findings
            if isinstance(finding, dict) and finding.get("blocking") is True
        ]
        return bool(blocking_findings) and all(
            finding.get("code") == "shacl_violation"
            and isinstance(finding.get("finding_fingerprint"), str)
            and bool(finding["finding_fingerprint"])
            and isinstance(finding.get("client_item_ids"), list)
            and bool(finding["client_item_ids"])
            and all(isinstance(item_id, str) and item_id for item_id in finding["client_item_ids"])
            for finding in blocking_findings
        )

    def seed(self) -> dict[str, object]:
        """Seed once from the already-issued pre-sequence modeling-context receipt."""
        try:
            runtime = self._runtime()
            receipts = runtime.get("receipts")
            receipt = receipts.get("modeling_context") if isinstance(receipts, dict) else None
            request_id = receipt.get("request_id") if isinstance(receipt, dict) else None
            if not isinstance(request_id, str) or not request_id:
                raise BatchExchangeError("initial modeling-context receipt is unavailable")
            response = json.loads((self.response_dir / f"{request_id}.json").read_text(encoding="utf-8"))
            if not isinstance(response, dict):
                raise BatchExchangeError("initial modeling-context response is invalid")
            body = self._body(response)
            workspace = body.get("workspace")
            version = workspace.get("workspace_version") if isinstance(workspace, dict) else None
            if not isinstance(version, str) or not version:
                raise BatchExchangeError("initial modeling-context version is unavailable")
            state = self._state(runtime)
            if state.get("workspace_version") not in (None, version):
                raise BatchExchangeError("initial workspace version changed")
            state["workspace_version"] = version
            state["initial_context_request_id"] = request_id
            self._save(runtime)
            return {"workspace_version": version}
        except BatchExchangeError as error:
            self._block(str(error))
            raise

    def dry_run(self, candidate_path: Path, expected: str) -> dict[str, object]:
        if expected not in {"validated", "validation_failed", FIRST_VALID_INSTANCE_EXPECTED}:
            raise BatchExchangeError("dry-run expected result is invalid")
        try:
            runtime = self._runtime()
            self._admit_dry_run(runtime, expected)
            version = self._version(runtime)
            projection = self._projection(candidate_path)
            session_id, scoped_id, _token = self._identifiers(runtime, apply=False)
            request_id = f"batch-{uuid.uuid4().hex}"
            body = {
                **projection,
                "expected_workspace_version": version,
                "idempotency_key": f"batch-key-{uuid.uuid4().hex}",
                "mode": "dry_run",
                "ontology_id": scoped_id,
            }
            response = self._publish(
                {
                    "body": body,
                    "headers": {"content-type": "application/json"},
                    "id": request_id,
                    "method": "POST",
                    "path": f"/api/build-sessions/{session_id}/modeling-batches",
                }
            )
            response_body = self._body(response)
            workspace = response_body.get("workspace")
            before = workspace.get("before_version") if isinstance(workspace, dict) else None
            expected_version = workspace.get("expected_version") if isinstance(workspace, dict) else None
            if before != version or expected_version != version:
                raise BatchExchangeError("dry-run workspace transition is inconsistent")
            if response_body.get("mode") != "dry_run":
                raise BatchExchangeError("dry-run result differs from expected result")
            attempt_status = response_body.get("attempt_status")
            branch: str | None = None
            if expected == FIRST_VALID_INSTANCE_EXPECTED:
                if attempt_status == "validated":
                    branch = "validated"
                elif attempt_status == "validation_failed" and self._is_shacl_correction_response(
                    response_body
                ):
                    branch = "shacl_correction_required"
                else:
                    raise BatchExchangeError("dry-run result differs from expected result")
            elif attempt_status != expected:
                raise BatchExchangeError("dry-run result differs from expected result")
            state = self._state(runtime)
            if attempt_status == "validated":
                frozen = canonical_json(projection)
                state["frozen"] = {
                    "projection": projection,
                    "sha256": hashlib.sha256(frozen).hexdigest(),
                }
                state.pop("correction_pending", None)
            elif branch == "shacl_correction_required":
                state["correction_pending"] = True
            self._save(runtime)
            result = {"request_id": request_id, "response": response, "workspace_version": version}
            if branch is not None:
                result["branch"] = branch
            return result
        except BatchExchangeError as error:
            self._block(str(error))
            raise

    def apply(self, candidate_path: Path, expected: str = "applied") -> dict[str, object]:
        if expected != "applied":
            raise BatchExchangeError("apply expected result is invalid")
        try:
            runtime = self._runtime()
            version = self._version(runtime)
            projection = self._projection(candidate_path)
            state = self._state(runtime)
            frozen = state.get("frozen")
            if not isinstance(frozen, dict) or frozen.get("projection") != projection:
                raise BatchExchangeError("apply candidate does not match validated freeze")
            if frozen.get("applied") is True:
                raise BatchExchangeError("validated freeze was already applied")
            session_id, scoped_id, token = self._identifiers(runtime, apply=True)
            request_id = f"batch-{uuid.uuid4().hex}"
            body = {
                **projection,
                "expected_workspace_version": version,
                "idempotency_key": f"batch-key-{uuid.uuid4().hex}",
                "lease_token": token,
                "mode": "apply_atomic",
                "ontology_id": scoped_id,
            }
            response = self._publish(
                {
                    "body": body,
                    "headers": {"content-type": "application/json"},
                    "id": request_id,
                    "method": "POST",
                    "path": f"/api/build-sessions/{session_id}/modeling-batches",
                }
            )
            response_body = self._body(response)
            workspace = response_body.get("workspace")
            before = workspace.get("before_version") if isinstance(workspace, dict) else None
            after = workspace.get("after_version") if isinstance(workspace, dict) else None
            if before not in (None, version) or not isinstance(after, str) or not after:
                raise BatchExchangeError("apply workspace transition is inconsistent")
            if response_body.get("mode") != "apply_atomic" or response_body.get("attempt_status") != expected:
                raise BatchExchangeError("apply result differs from expected result")
            state["workspace_version"] = after
            frozen["applied"] = True
            self._save(runtime)
            return {"request_id": request_id, "response": response, "workspace_version": after}
        except BatchExchangeError as error:
            self._block(str(error))
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "seed", "dry-run", "apply"))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--expected")
    args = parser.parse_args()
    try:
        if args.action == "check":
            if args.candidate is None:
                raise BatchExchangeError("check requires candidate")
            result = check_candidate(args.candidate)
        else:
            runtime_path = Path("/mnt/runtime-record.json")
            request_dir = Path(os.environ["M4_API_REQUEST_DIR"])
            response_dir = Path(os.environ["M4_API_RESPONSE_DIR"])
            exchange = BatchExchange(
                runtime_path=runtime_path,
                request_dir=request_dir,
                response_dir=response_dir,
            )
            if args.action == "seed":
                result = exchange.seed()
            elif args.action == "dry-run":
                if args.candidate is None or args.expected is None:
                    raise BatchExchangeError("dry-run requires candidate and expected result")
                result = exchange.dry_run(args.candidate, args.expected)
            else:
                if args.candidate is None:
                    raise BatchExchangeError("apply requires candidate")
                result = exchange.apply(args.candidate, args.expected or "applied")
    except BatchExchangeError as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
