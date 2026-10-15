"""Small host-owned executor for the R4.3-025 direct modeling path.

The compiler owns semantic decisions and returns dependency-ordered batches.  This
module owns only the platform boundary: a real Build Session and Ontology lease,
the current workspace revision, one ``apply_atomic`` dispatch per batch, and the
existing staged intent/receipt/Attempt evidence.  It deliberately does not know
how to compile a candidate or decide whether a business model is complete.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path
from typing import Any

from .platform_scope import PlatformScope
from .staged_batch_write_forwarder import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
)
from .staged_decisions import (
    StagedDecisionArtifactError,
    build_attempt_proof,
    build_submission_intent,
    build_submission_receipt,
    canonical_command_digest,
    mark_intent_status,
    next_intent_ordinal,
    next_receipt_ordinal,
    platform_content_hash,
    read_submission_intents,
    read_submission_receipts,
    write_submission_intent,
    write_submission_receipt,
)


RESULT_SCHEMA = "r4-3-025-model-change-result/v1"
MODE = "apply_atomic"
_TERMINAL_APPLIED = frozenset({"applied", "partially_applied"})
_TERMINAL_NOT_WRITTEN = frozenset(
    {"failed", "rejected", "validation_failed", "not_applied", "cancelled"}
)


class DirectExecutionError(RuntimeError):
    """A typed, repairable direct-execution boundary failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        actual: Any = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.actual = actual
        self.retryable = retryable


@dataclass
class _Lease:
    ontology_id: str
    token: str
    revision: int | None


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _stable_id(prefix: str, *parts: Any, limit: int = 255) -> str:
    raw = ":".join(str(part) for part in parts)
    value = f"{prefix}:{raw}"
    if len(value) <= limit:
        return value
    return f"{prefix}:{_digest(raw)[: limit - len(prefix) - 2]}"


def _unwrap(value: Any) -> Mapping[str, Any]:
    """Unwrap the two read/lifecycle response shapes used by the adapters."""

    if not isinstance(value, Mapping):
        raise DirectExecutionError("platform_response_invalid", "platform response is not an object")
    if value.get("ok") is False:
        error = value.get("error")
        code = str(value.get("error_code") or value.get("code") or "platform_error")
        message = str(error or value.get("message") or value.get("detail") or code)
        raise DirectExecutionError(code, message, actual=value, retryable=True)
    if value.get("ok") is True and isinstance(value.get("data"), Mapping):
        return value["data"]
    if isinstance(value.get("data"), Mapping) and set(value).issubset(
        {"data", "ok", "request_digest", "response_digest", "artifact_path"}
    ):
        return value["data"]
    return value


def _session_value(value: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = value.get("session")
    return candidate if isinstance(candidate, Mapping) else value


def _lease_value(value: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = value.get("lease")
    return candidate if isinstance(candidate, Mapping) else value


def _attempt_status(value: Mapping[str, Any] | None) -> str | None:
    if not isinstance(value, Mapping):
        return None
    status = value.get("attempt_status")
    if isinstance(status, str):
        return status
    latest = value.get("latest_attempt")
    if isinstance(latest, Mapping) and isinstance(latest.get("attempt_status"), str):
        return latest["attempt_status"]
    attempts = value.get("attempts")
    if isinstance(attempts, list):
        for attempt in reversed(attempts):
            if isinstance(attempt, Mapping) and isinstance(attempt.get("attempt_status"), str):
                return attempt["attempt_status"]
    return None


def _terminal_attempt(value: Mapping[str, Any] | None) -> bool:
    return _attempt_status(value) in (_TERMINAL_APPLIED | _TERMINAL_NOT_WRITTEN)


def _platform_items(items: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(items, list) or not items:
        raise DirectExecutionError("batch_items_required", "each Ontology batch needs non-empty items")
    result: list[dict[str, Any]] = []
    source_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append({"index": index, "code": "item_invalid", "message": "item is not an object"})
            continue
        item_id = item.get("client_item_id")
        if not _nonempty(item_id):
            errors.append({"index": index, "code": "client_item_id_required", "message": "client_item_id is required"})
            continue
        if item_id in seen:
            errors.append({"index": index, "code": "duplicate_client_item_id", "message": f"duplicate client_item_id {item_id!r}"})
            continue
        seen.add(item_id)
        command_kind = item.get("command_kind")
        payload = item.get("payload")
        if not _nonempty(item.get("resource_kind")):
            errors.append({"index": index, "code": "resource_kind_required", "message": "resource_kind is required"})
            continue
        if not _nonempty(command_kind) or not isinstance(payload, Mapping):
            errors.append({"index": index, "code": "item_shape_invalid", "message": "command_kind and payload are required"})
            continue
        # ``change_id`` and compiler metadata stay in source_map; they are not
        # platform fields and must never be forwarded as an Agent-authored
        # technical envelope.
        projected: dict[str, Any] = {
            "client_item_id": item_id,
            "command_kind": command_kind,
            "payload": dict(payload),
            "depends_on": list(item.get("depends_on") or []),
            "rationale": item.get("rationale"),
            "competency_question_ids": list(item.get("competency_question_ids") or []),
        }
        if not all(isinstance(dep, str) and dep for dep in projected["depends_on"]):
            errors.append({"index": index, "code": "depends_on_invalid", "message": "depends_on must contain item IDs"})
            continue
        if not all(isinstance(cq, str) and cq for cq in projected["competency_question_ids"]):
            errors.append({"index": index, "code": "competency_question_ids_invalid", "message": "competency_question_ids must contain strings"})
            continue
        if projected["rationale"] is not None and not isinstance(projected["rationale"], str):
            errors.append({"index": index, "code": "rationale_invalid", "message": "rationale must be a string or null"})
            continue
        result.append(projected)
        source_items.append(dict(item))
    if errors:
        raise DirectExecutionError(
            "compiled_batch_invalid",
            "compiled batch contains invalid items",
            actual=errors,
            retryable=True,
        )
    return result, source_items


def _path_join(base: Any, suffix: Any) -> str:
    if isinstance(base, (list, tuple)):
        base_path = "/" + "/".join(str(part) for part in base)
    elif isinstance(base, str):
        base_path = base
    else:
        base_path = ""
    if isinstance(suffix, (list, tuple)):
        tail = "/" + "/".join(str(part) for part in suffix)
    elif isinstance(suffix, str):
        tail = suffix if suffix.startswith("/") else f"/{suffix}" if suffix else ""
    else:
        tail = ""
    if not base_path:
        return tail or ""
    if not tail:
        return base_path
    return base_path.rstrip("/") + tail


class DirectModelExecutor:
    """Execute already compiled Ontology batches through existing platform contracts.

    ``submit`` is the host's existing staged batch forwarder and ``read`` is the
    scoped read forwarder.  Neither callback is allowed to choose a different
    Session, lease, revision, or mode; those values are filled here.
    """

    def __init__(
        self,
        scope: PlatformScope,
        run_root: str | PathLike[str],
        run_id: str,
        task_id: str,
        submit: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None,
        observe_result: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.scope = scope
        self.run_root = Path(run_root)
        self.run_id = run_id
        self.task_id = task_id
        self.submit = submit
        self.read = read
        self.observe_result = observe_result
        self.session_id: str | None = None
        self.session_revision: int | None = None
        self._leases: dict[str, _Lease] = {}

    def execute(
        self,
        batches: Sequence[Mapping[str, Any]],
        source_map: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_map = source_map if isinstance(source_map, Mapping) else {}
        if not isinstance(batches, Sequence) or isinstance(batches, (str, bytes)):
            return self._failure_result(
                "compiled_batches_invalid", "compiled batches must be an ordered sequence", source_map
            )
        if not batches:
            return self._result([], [], [], _digest({"batches": [], "source_map": source_map}))

        prepared: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        for index, batch in enumerate(batches):
            try:
                prepared.append(self._prepare_batch(batch, index))
            except DirectExecutionError as exc:
                errors.extend(
                    self._errors_from_exception(
                        exc,
                        batch_index=index,
                        source_map=source_map,
                        batch=batch if isinstance(batch, Mapping) else None,
                    )
                )
                pending.extend(self._pending_from_batch(batch, index))
        self._attach_source_dependencies(prepared, source_map)
        submission_digest = _digest(
            {"batches": [{"ontology_id": b.get("ontology_id"), "items": b.get("items")} for b in prepared], "source_map": source_map}
        )
        if errors:
            # Static validation is all-or-nothing before Session creation. All
            # valid batches are therefore explicitly reported as unexecuted
            # alongside the malformed batch that supplied the error.
            pending = [
                pending_item
                for batch_index, batch in enumerate(batches)
                for pending_item in self._pending_from_batch(batch, batch_index)
            ]
            return self._result([], errors, pending, submission_digest)

        batch_results: list[dict[str, Any]] = []
        blocked_items: set[str] = set()
        results_by_index: dict[int, dict[str, Any]] = {}
        for index, batch in enumerate(prepared):
            item_ids = [str(item["client_item_id"]) for item in batch["items"]]
            dependency_batches = [int(value) for value in batch.get("depends_on_batches", [])]
            blocked_batches = [
                dependency
                for dependency in dependency_batches
                if results_by_index.get(dependency, {}).get("write_state") != "applied"
                or results_by_index.get(dependency, {}).get("attempt_status") == "partially_applied"
            ]
            dependencies = {
                dep
                for item in batch["items"]
                for dep in item.get("depends_on", [])
                if dep in blocked_items
            }
            if dependencies or blocked_batches:
                pending.extend(
                    self._pending_from_batch(
                        batch,
                        index,
                        reason="dependency_not_applied",
                        dependencies=sorted({*dependencies, *[f"batch:{value}" for value in blocked_batches]}),
                    )
                )
                blocked_items.update(item_ids)
                results_by_index[int(batch.get("index", index))] = {
                    "write_state": "not_written",
                    "attempt_status": None,
                }
                continue
            try:
                row = self._execute_batch(batch, index, source_map)
            except DirectExecutionError as exc:
                row = self._batch_error(batch, index, exc, source_map)
                if exc.code == "ontology_write_frozen":
                    pending.extend(
                        self._pending_from_batch(
                            batch,
                            index,
                            reason="ontology_write_frozen",
                        )
                    )
            batch_results.append(row)
            results_by_index[int(batch.get("index", index))] = row
            state = row.get("write_state")
            if state != "applied" or row.get("attempt_status") == "partially_applied":
                blocked_items.update(item_ids)

        result = self._result(batch_results, errors, pending, submission_digest)
        self._notify("modeling_submit_model_changes", {"batches": prepared}, result)
        return result

    def close_session(
        self,
        *,
        complete: bool = True,
        summary: str = "Direct modeling execution finished",
        unresolved_items: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Release owned leases and terminally close the owned Build Session."""

        if not self.session_id:
            return {"closed": True, "session_id": None, "leases": [], "errors": []}
        errors: list[dict[str, Any]] = []
        for ontology_id, lease in list(self._leases.items()):
            try:
                response = self._scope_request(
                    "POST",
                    f"/api/build-sessions/{self.session_id}/ontology-leases/{ontology_id}:release",
                    {
                        "client_request_id": _stable_id("direct-release", self.run_id, self.task_id, ontology_id),
                        "lease_token": lease.token,
                        "expected_lease_revision": lease.revision,
                    },
                    tool="release_ontology_lease",
                )
                value = _lease_value(_unwrap(response))
                if value.get("state") != "released" and value.get("released") is not True:
                    raise DirectExecutionError("lease_release_unconfirmed", "Ontology lease release was not confirmed")
                self._leases.pop(ontology_id, None)
            except DirectExecutionError as exc:
                errors.append(self._error(code=exc.code, message=exc.message, actual=exc.actual, retryable=exc.retryable))
        if not errors:
            try:
                endpoint = ":complete" if complete else ":cancel"
                body: dict[str, Any] = {
                    "client_request_id": _stable_id("direct-finish", self.run_id, self.task_id, "complete" if complete else "cancel"),
                    "expected_revision": self.session_revision,
                }
                if complete:
                    body.update({"summary": summary, "unresolved_items": list(unresolved_items or [])})
                else:
                    body["reason"] = summary
                response = self._scope_request(
                    "POST",
                    f"/api/build-sessions/{self.session_id}{endpoint}",
                    body,
                    tool="complete_build_session" if complete else "cancel_build_session",
                )
                value = _session_value(_unwrap(response))
                if value.get("status") not in {"completed", "cancelled"}:
                    raise DirectExecutionError("session_terminal_unconfirmed", "Build Session terminal state was not confirmed")
                if hasattr(self.scope, "owned_session_ids"):
                    self.scope.owned_session_ids.discard(self.session_id)
                session_id = self.session_id
                self.session_id = None
                return {"closed": True, "session_id": session_id, "leases": [], "errors": []}
            except DirectExecutionError as exc:
                errors.append(self._error(code=exc.code, message=exc.message, actual=exc.actual, retryable=exc.retryable))
        return {"closed": False, "session_id": self.session_id, "leases": sorted(self._leases), "errors": errors}

    def _prepare_batch(self, batch: Mapping[str, Any], index: int) -> dict[str, Any]:
        if not isinstance(batch, Mapping):
            raise DirectExecutionError("compiled_batch_invalid", "batch is not an object")
        ontology_id = batch.get("ontology_id")
        if not _nonempty(ontology_id):
            raise DirectExecutionError("ontology_required", "compiled batch ontology_id is required")
        authorized = self._authorized_ontology_ids()
        if not authorized:
            raise DirectExecutionError(
                "scope_binding_required",
                "scope has no authorized Ontology set",
            )
        if ontology_id not in authorized:
            raise DirectExecutionError(
                "ontology_out_of_scope",
                "compiled batch Ontology is outside the authorized scope",
                actual={"ontology_id": ontology_id},
                retryable=False,
            )
        items, source_items = _platform_items(batch.get("items"))
        depends_on_batches = batch.get("depends_on_batches", [])
        if not isinstance(depends_on_batches, list) or not all(
            type(value) is int and value >= 0 for value in depends_on_batches
        ):
            raise DirectExecutionError(
                "compiled_batch_invalid",
                "depends_on_batches must contain non-negative batch indexes",
                actual={"depends_on_batches": depends_on_batches},
            )
        batch_index = batch.get("batch_index", index)
        if type(batch_index) is not int or batch_index < 0:
            raise DirectExecutionError(
                "compiled_batch_invalid",
                "batch_index must be a non-negative integer",
                actual={"batch_index": batch_index},
            )
        return {
            "ontology_id": ontology_id,
            "items": items,
            "source_items": source_items,
            "depends_on_batches": list(dict.fromkeys(depends_on_batches)),
            "index": batch_index,
        }

    def _authorized_ontology_ids(self) -> set[str]:
        ontology_ids = getattr(self.scope, "ontology_ids", None)
        values = (
            list(ontology_ids)
            if isinstance(ontology_ids, (list, tuple, set, frozenset))
            else []
        )
        if not values:
            single = getattr(self.scope, "ontology_id", None)
            if single is not None:
                values.append(single)
        return {value for value in values if _nonempty(value)}

    @staticmethod
    def _attach_source_dependencies(
        batches: list[dict[str, Any]], source_map: Mapping[str, Any]
    ) -> None:
        """Carry compiler sidecar cross-batch edges into execution ordering."""

        if not isinstance(source_map, Mapping):
            return
        for batch in batches:
            batch_index = batch.get("index")
            group = source_map.get(str(batch_index))
            if not isinstance(group, Mapping):
                continue
            dependencies = {
                edge.get("depends_on_batch")
                for entry in group.values()
                if isinstance(entry, Mapping)
                for edge in (entry.get("cross_batch_dependencies") or [])
                if isinstance(edge, Mapping) and type(edge.get("depends_on_batch")) is int
            }
            if dependencies:
                batch["depends_on_batches"] = sorted(
                    set(batch.get("depends_on_batches", [])) | dependencies
                )

    def _ensure_session(self) -> None:
        if self.session_id:
            return
        project_id = getattr(self.scope, "project_id", None)
        if not _nonempty(project_id):
            raise DirectExecutionError("scope_binding_required", "Project binding is unavailable")
        if not _nonempty(getattr(self.scope, "protocol_key", None)):
            raise DirectExecutionError("protocol_key_unavailable", "Protocol key is unavailable")
        client_session_id = f"direct:{self.run_id}:{self.task_id}"
        response = self._scope_request(
            "POST",
            f"/api/projects/{project_id}/build-sessions",
            {"client_session_id": client_session_id},
            tool="create_build_session",
        )
        value = _session_value(_unwrap(response))
        session_id = value.get("id") or value.get("session_id")
        if not _nonempty(session_id):
            raise DirectExecutionError("session_identity_missing", "Build Session response has no identity", actual=value)
        self.session_id = str(session_id)
        self.session_revision = value.get("revision") if type(value.get("revision")) is int else None
        owned = getattr(self.scope, "owned_session_ids", None)
        if owned is not None and hasattr(owned, "add"):
            owned.add(self.session_id)

    def _ensure_lease(self, ontology_id: str) -> _Lease:
        existing = self._leases.get(ontology_id)
        if existing is not None:
            return existing
        if not self.session_id:
            raise DirectExecutionError("session_missing", "Build Session is not available")
        if self.session_revision is None:
            self._refresh_session_revision()
        response = self._scope_request(
            "POST",
            f"/api/build-sessions/{self.session_id}/ontology-leases/{ontology_id}:acquire",
            {
                "client_request_id": _stable_id("direct-acquire", self.run_id, self.task_id, ontology_id),
                "expected_session_revision": self.session_revision,
                "rotate_token": False,
            },
            tool="acquire_ontology_lease",
        )
        value = _lease_value(_unwrap(response))
        token, revision = value.get("lease_token"), value.get("lease_revision")
        if not _nonempty(token) or type(revision) is not int:
            raise DirectExecutionError("lease_identity_missing", "Ontology lease response is incomplete", actual=value)
        lease = _Lease(ontology_id, str(token), revision)
        self._leases[ontology_id] = lease
        return lease

    def _refresh_session_revision(self) -> None:
        if not self.session_id:
            raise DirectExecutionError("session_missing", "Build Session is not available")
        response = self._scope_request(
            "GET", f"/api/build-sessions/{self.session_id}", None, tool="get_build_session"
        )
        value = _session_value(_unwrap(response))
        revision = value.get("revision")
        if type(revision) is not int:
            raise DirectExecutionError("session_revision_missing", "Build Session revision is unavailable", actual=value)
        self.session_revision = revision

    def _read_context(self, ontology_id: str) -> Mapping[str, Any]:
        if callable(self.read):
            response = self._read_tool("get_modeling_context", {"ontology_id": ontology_id})
        else:
            response = _unwrap(self._scope_request(
                "GET", f"/api/ontologies/{ontology_id}/modeling-context", None,
                tool="get_modeling_context",
            ))
        workspace = response.get("workspace") if isinstance(response.get("workspace"), Mapping) else response
        revision = workspace.get("model_revision") if isinstance(workspace, Mapping) else None
        if type(revision) is not int or revision < 0:
            raise DirectExecutionError("model_revision_unavailable", "current Ontology model_revision is unavailable", actual=response)
        if isinstance(workspace, Mapping) and workspace.get("state") not in {None, "ready"}:
            raise DirectExecutionError("workspace_not_ready", "Ontology workspace is not ready", actual=workspace)
        return response

    def _execute_batch(
        self,
        batch: Mapping[str, Any],
        index: int,
        source_map: Mapping[str, Any],
    ) -> dict[str, Any]:
        ontology_id = str(batch["ontology_id"])
        batch_ordinal = int(batch.get("index", index))
        # Cross-batch binding is owned by the Runner capability layer.  Keep
        # same-batch item_ref values intact for the platform Batch service.
        platform_items = [dict(item) for item in batch["items"]]
        content_digest = platform_content_hash({"ontology_id": ontology_id, "items": platform_items})
        identity_digest = _digest(
            {
                "ontology_id": ontology_id,
                "items": list(batch.get("source_items") or batch["items"]),
                "platform_content_hash": content_digest,
            }
        )
        client_batch_id = _stable_id("direct-batch", self.run_id, self.task_id, batch_ordinal, identity_digest)
        idempotency_key = _stable_id("direct-apply", self.run_id, self.task_id, ontology_id, identity_digest)
        intents, receipts = self._load_records()
        identity_batch = {
            "client_batch_id": client_batch_id,
            "idempotency_key": idempotency_key,
            "items": platform_items,
        }
        intent, _ordinal = self._intent_for(identity_batch, intents)
        existing_receipt = self._receipt_for(intent, receipts) if intent is not None else None
        if existing_receipt is not None:
            snapshot = self._load_snapshot(intent)
            result_batch = (
                {
                    **snapshot["batch"],
                    "index": batch.get("index", 0),
                    "source_items": snapshot.get("source_items", batch.get("source_items", [])),
                }
                if snapshot is not None
                else {
                    "ontology_id": ontology_id,
                    "items": list(batch["items"]),
                    "source_items": batch.get("source_items", []),
                }
            )
            observed = snapshot.get("result") if snapshot is not None else None
            original_batch = snapshot.get("batch") if snapshot is not None else result_batch
            receipt = existing_receipt
            if isinstance(observed, Mapping) and _terminal_attempt(observed):
                # Only a terminal platform outcome is safe to reuse from the
                # sidecar.  applying/recovering/unknown must be reconciled by
                # the original Batch identity before returning a result.
                detail = dict(observed)
            else:
                expected_attempt_id = (
                    str(observed.get("attempt_id"))
                    if isinstance(observed, Mapping) and _nonempty(observed.get("attempt_id"))
                    else None
                )
                detail = self._reconcile_batch(
                    str(existing_receipt.get("batch_id") or ""),
                    result_batch,
                    allow_missing=False,
                    expected_attempt_id=expected_attempt_id,
                )
                if detail is None:
                    raise DirectExecutionError(
                        "staged_unreconciled_batch",
                        "existing receipt could not be reconciled",
                    )
                if not _nonempty(detail.get("batch_id")):
                    detail = {
                        **dict(detail),
                        "batch_id": existing_receipt.get("batch_id"),
                    }
                if snapshot is not None:
                    receipt = self._persist_receipt(intent, detail, original_batch)
            # Re-observe the original platform envelope so the host can
            # restore its run-relative acceptance artifact reference after a
            # restart; this is observation only and never a new submit.
            self._notify("submit_modeling_batch", original_batch, detail)
            return self._batch_from_platform(detail, result_batch, intent, receipt, index, source_map)

        platform_batch: dict[str, Any]
        if intent is not None:
            if intent.get("status") == "rejected":
                raise DirectExecutionError(
                    "staged_batch_rejected",
                    "the original Batch was definitely rejected; submit a corrected request with a new identity",
                    retryable=True,
                )
            if intent.get("status") not in {"unknown", "submitted"}:
                raise DirectExecutionError(
                    "staged_unreconciled_batch",
                    "submission intent has no receipt and is not safely replayable",
                    retryable=True,
                )
            snapshot = self._load_snapshot(intent)
            if snapshot is None:
                raise DirectExecutionError(
                    "staged_snapshot_missing",
                    "original Batch snapshot is unavailable; reconcile the existing intent before retrying",
                    retryable=True,
                )
            platform_batch = snapshot["batch"]
            self._adopt_snapshot_context(snapshot, ontology_id)
            result_batch = {
                **dict(batch),
                "source_items": snapshot.get("source_items", batch.get("source_items", [])),
            }
            # Reconcile the original identity before any forward call.  A
            # reachable, complete listing with no match proves that reusing
            # the exact original envelope is safe; an unavailable or truncated
            # listing remains uncertain.
            found, complete = self._find_original_batch(platform_batch)
            if found is not None:
                self._notify("submit_modeling_batch", platform_batch, found)
                receipt = self._persist_receipt(intent, found, platform_batch)
                return self._batch_from_platform(found, result_batch, intent, receipt, index, source_map)
            if not complete:
                raise DirectExecutionError(
                    "staged_unreconciled_batch",
                    "original unknown Batch identity could not be reconciled",
                    retryable=True,
                )
        else:
            unresolved = self._unresolved_ontology_write(ontology_id, intents, receipts)
            if unresolved is not None:
                raise DirectExecutionError(
                    "ontology_write_frozen",
                    "an earlier write for this Ontology is unresolved; reconcile its original Batch/Attempt before starting a new request",
                    actual=unresolved,
                    retryable=True,
                )
            self._ensure_session()
            lease = self._ensure_lease(ontology_id)
            context = self._read_context(ontology_id)
            workspace = context.get("workspace") if isinstance(context.get("workspace"), Mapping) else context
            revision = workspace.get("model_revision")
            platform_batch = {
                "session_id": self.session_id,
                "client_batch_id": client_batch_id,
                "ontology_id": ontology_id,
                "idempotency_key": idempotency_key,
                "expected_model_revision": revision,
                "items": platform_items,
                "mode": MODE,
                "lease_token": lease.token,
            }
            ordinal = next_intent_ordinal(intents)
            intent = build_submission_intent(
                ordinal,
                idempotency_key=idempotency_key,
                client_batch_id=client_batch_id,
                session_id=str(self.session_id),
                mode=MODE,
                commands=list(platform_batch["items"]),
                value_traces=[],
                l3_nodes=[],
            )
            try:
                write_submission_intent(self.run_root, intent)
                self._write_snapshot(intent, platform_batch, batch.get("source_items", []))
            except (OSError, StagedDecisionArtifactError) as exc:
                raise DirectExecutionError("intent_persist_failed", str(exc), retryable=True) from exc
            result_batch = batch

        result: Mapping[str, Any]
        try:
            result = self.submit(platform_batch)
        except StagedBatchForwardUnknown as exc:
            self._mark_intent(intent, "unknown")
            detail = self._reconcile_batch_by_identity(platform_batch)
            if detail is not None:
                self._notify("submit_modeling_batch", platform_batch, detail)
                receipt = self._persist_receipt(intent, detail, platform_batch)
                return self._batch_from_platform(detail, result_batch, intent, receipt, index, source_map)
            raise DirectExecutionError("staged_batch_forward_unknown", str(exc), retryable=True) from exc
        except StagedBatchForwardError as exc:
            self._mark_intent(intent, "rejected")
            raise DirectExecutionError("staged_batch_forward_failed", str(exc), retryable=True) from exc
        except Exception as exc:  # noqa: BLE001 - external forwarder boundary
            self._mark_intent(intent, "unknown")
            raise DirectExecutionError("staged_batch_forward_unknown", str(exc), retryable=True) from exc
        if not isinstance(result, Mapping):
            self._mark_intent(intent, "unknown")
            raise DirectExecutionError("staged_batch_forward_unknown", "forwarder returned no mapping")
        self._notify("submit_modeling_batch", platform_batch, result)
        if not _nonempty(result.get("batch_id")):
            self._mark_intent(intent, "unknown")
            raise DirectExecutionError("staged_batch_forward_unknown", "forwarder returned no batch identity")
        receipt = self._persist_receipt(intent, result, platform_batch)
        return self._batch_from_platform(result, result_batch, intent, receipt, index, source_map)

    def _intent_for(
        self, batch: Mapping[str, Any], intents: Sequence[Mapping[str, Any]]
    ) -> tuple[Mapping[str, Any] | None, int | None]:
        for intent in intents:
            if intent.get("idempotency_key") != batch.get("idempotency_key"):
                continue
            if list(intent.get("commands") or []) != [canonical_command_digest(item) for item in batch["items"]]:
                raise DirectExecutionError("idempotency_conflict", "same idempotency identity has different batch content", retryable=True)
            return intent, int(intent.get("ordinal")) if type(intent.get("ordinal")) is int else None
        return None, None

    def _load_records(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            return read_submission_intents(self.run_root), read_submission_receipts(self.run_root)
        except StagedDecisionArtifactError as exc:
            raise DirectExecutionError(exc.reason_code, str(exc), retryable=True) from exc

    def _unresolved_ontology_write(
        self,
        ontology_id: str,
        intents: Sequence[Mapping[str, Any]],
        receipts: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        """Find an unsettled prior write for one Ontology.

        Intent/receipt records do not carry the target Ontology themselves;
        the durable submission snapshot is the existing source of that
        identity.  A terminal platform outcome is safe to reuse.  Every
        nonterminal outcome keeps only its own Ontology frozen so an unrelated
        Ontology can continue.
        """

        for intent in intents:
            if intent.get("status") not in {"submitted", "unknown", "receipted"}:
                continue
            snapshot = self._load_snapshot(intent)
            if snapshot is None:
                continue
            platform_batch = snapshot.get("batch")
            if not isinstance(platform_batch, Mapping) or platform_batch.get("ontology_id") != ontology_id:
                continue
            receipt = self._receipt_for(intent, receipts)
            observed = snapshot.get("result")
            if isinstance(observed, Mapping) and _terminal_attempt(observed):
                continue
            return {
                "ontology_id": ontology_id,
                "intent_ordinal": intent.get("ordinal"),
                "client_batch_id": platform_batch.get("client_batch_id"),
                "batch_id": receipt.get("batch_id") if isinstance(receipt, Mapping) else None,
                "attempt_id": (
                    observed.get("attempt_id")
                    if isinstance(observed, Mapping)
                    else None
                ),
                "attempt_status": _attempt_status(observed),
            }
        return None

    def _snapshot_path(self, intent: Mapping[str, Any]) -> Path:
        ordinal = intent.get("ordinal")
        if type(ordinal) is not int or ordinal < 1:
            raise DirectExecutionError("staged_snapshot_invalid", "submission intent has no valid ordinal")
        return (
            self.run_root
            / "value-semantics"
            / "direct-submission-snapshots"
            / f"snapshot-{ordinal}.json"
        )

    def _write_snapshot(
        self,
        intent: Mapping[str, Any],
        platform_batch: Mapping[str, Any],
        source_items: Any,
    ) -> None:
        path = self._snapshot_path(intent)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lease = self._leases.get(str(platform_batch.get("ontology_id")))
        payload = {
            "schema_version": "r4-3-025-direct-submission-snapshot/v1",
            "intent_ordinal": intent.get("ordinal"),
            "batch": dict(platform_batch),
            "source_items": [dict(item) for item in source_items if isinstance(item, Mapping)]
            if isinstance(source_items, list)
            else [],
            "session_revision": self.session_revision,
            "lease_revision": lease.revision if lease is not None else None,
        }
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_snapshot(self, intent: Mapping[str, Any]) -> dict[str, Any] | None:
        path = self._snapshot_path(intent)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DirectExecutionError("staged_snapshot_invalid", str(exc), retryable=True) from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != "r4-3-025-direct-submission-snapshot/v1":
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot schema is invalid")
        batch = payload.get("batch")
        if not isinstance(batch, Mapping):
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot has no Batch envelope")
        required = ("session_id", "client_batch_id", "ontology_id", "idempotency_key", "expected_model_revision", "items", "mode", "lease_token")
        if any(key not in batch for key in required) or batch.get("mode") != MODE:
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot Batch envelope is incomplete")
        source_items = payload.get("source_items")
        if not isinstance(source_items, list):
            source_items = []
        return {
            "batch": dict(batch),
            "source_items": [dict(item) for item in source_items if isinstance(item, Mapping)],
            "session_revision": payload.get("session_revision"),
            "lease_revision": payload.get("lease_revision"),
            "result": dict(payload["result"]) if isinstance(payload.get("result"), Mapping) else None,
        }

    def _write_snapshot_result(self, intent: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        path = self._snapshot_path(intent)
        if not path.is_file():
            raise DirectExecutionError("staged_snapshot_missing", "submission snapshot is unavailable")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("submission snapshot is not an object")
            payload["result"] = dict(result)
            temporary = path.with_name(f".{path.name}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DirectExecutionError("staged_snapshot_persist_failed", str(exc), retryable=True) from exc

    def _adopt_snapshot_context(self, snapshot: Mapping[str, Any], ontology_id: str) -> None:
        batch = snapshot.get("batch")
        if not isinstance(batch, Mapping) or batch.get("ontology_id") != ontology_id:
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot Ontology identity differs")
        session_id = batch.get("session_id")
        lease_token = batch.get("lease_token")
        session_revision = snapshot.get("session_revision")
        lease_revision = snapshot.get("lease_revision")
        if (
            not _nonempty(session_id)
            or not _nonempty(lease_token)
            or type(session_revision) is not int
            or type(lease_revision) is not int
        ):
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot lifecycle identity is incomplete")
        owned = getattr(self.scope, "owned_session_ids", None)
        if owned is not None and session_id not in owned:
            raise DirectExecutionError(
                "scope_session_not_owned",
                "submission snapshot Session is not owned by the current scope",
                actual={"session_id": session_id},
                retryable=False,
            )
        if self.session_id is not None and self.session_id != session_id:
            raise DirectExecutionError("staged_snapshot_invalid", "submission snapshot Session differs from active Session")
        self.session_id = str(session_id)
        self.session_revision = session_revision
        self._leases[ontology_id] = _Lease(ontology_id, str(lease_token), lease_revision)

    @staticmethod
    def _receipt_for(intent: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        for receipt in receipts:
            if receipt.get("intent_ordinal") == intent.get("ordinal"):
                return receipt
        return None

    def _mark_intent(self, intent: Mapping[str, Any], status: str) -> None:
        try:
            write_submission_intent(self.run_root, mark_intent_status(intent, status))
        except (OSError, StagedDecisionArtifactError):
            # The original forward result remains the authoritative boundary;
            # callers still receive unknown when the evidence file cannot be updated.
            return

    def _persist_receipt(
        self,
        intent: Mapping[str, Any],
        result: Mapping[str, Any],
        platform_batch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        response_digest = str(result.get("response_digest") or f"sha256:{_digest(result)}")
        try:
            receipts = read_submission_receipts(self.run_root)
            receipt = build_submission_receipt(
                next_receipt_ordinal(receipts),
                intent,
                batch_id=str(result["batch_id"]),
                response_digest=response_digest,
            )
            write_submission_receipt(self.run_root, receipt)
        except (OSError, StagedDecisionArtifactError) as exc:
            raise DirectExecutionError("staged_receipt_persist_failed", str(exc), retryable=True) from exc
        self._write_snapshot_result(intent, result)
        self._mark_intent(intent, "receipted")
        proof = build_attempt_proof(
            intent_ordinal=int(intent.get("ordinal")),
            receipt_ordinal=int(receipt.get("ordinal")),
            plan_ref=None,
            projection_digest=None,
            batch=platform_batch or {
                "mode": MODE,
                **{key: value for key, value in result.items() if key in {"client_batch_id", "idempotency_key"}},
            },
            result=result,
            response_digest=response_digest,
        )
        if proof is not None:
            try:
                self._append_attempt_proof(proof)
            except OSError as exc:
                raise DirectExecutionError("staged_attempt_proof_persist_failed", str(exc), retryable=True) from exc
        return receipt

    def _append_attempt_proof(self, proof: Mapping[str, Any]) -> None:
        path = self.run_root / "evidence" / "staged-decisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        value = {**dict(proof), "recorded_at": datetime.now(UTC).isoformat()}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")

    def _reconcile_batch_by_identity(self, batch: Mapping[str, Any]) -> Mapping[str, Any] | None:
        found, _complete = self._find_original_batch(batch)
        return found

    def _find_original_batch(
        self, batch: Mapping[str, Any]
    ) -> tuple[Mapping[str, Any] | None, bool]:
        if not self.session_id:
            return None, False
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            arguments: dict[str, Any] = {"session_id": self.session_id}
            if cursor is not None:
                if cursor in seen_cursors:
                    return None, False
                seen_cursors.add(cursor)
                arguments["cursor"] = cursor
            try:
                listing = self._read_tool("list_session_modeling_batches", arguments)
            except DirectExecutionError:
                return None, False
            rows = (
                listing.get("batches")
                if isinstance(listing.get("batches"), list)
                else listing.get("items")
            )
            if not isinstance(rows, list):
                return None, False
            match = next(
                (
                    row
                    for row in rows
                    if isinstance(row, Mapping)
                    and (
                        row.get("client_batch_id") == batch.get("client_batch_id")
                        or row.get("idempotency_key") == batch.get("idempotency_key")
                    )
                ),
                None,
            )
            if isinstance(match, Mapping) and _nonempty(match.get("batch_id")):
                try:
                    return (
                        self._reconcile_batch(str(match["batch_id"]), batch, allow_missing=False),
                        True,
                    )
                except DirectExecutionError:
                    return None, False
            next_cursor = listing.get("next_cursor")
            if not _nonempty(next_cursor):
                return None, True
            cursor = str(next_cursor)

    def _reconcile_batch(
        self,
        batch_id: str,
        batch: Mapping[str, Any],
        *,
        allow_missing: bool,
        expected_attempt_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        if not batch_id:
            if allow_missing:
                return None
            raise DirectExecutionError("staged_unreconciled_batch", "original batch identity is unavailable")
        detail = self._read_tool("get_modeling_batch", {"batch_id": batch_id})
        if detail.get("batch_id") not in {None, batch_id}:
            raise DirectExecutionError("staged_unreconciled_batch", "get_modeling_batch returned a different identity", actual=detail)
        for identity_field in ("client_batch_id", "idempotency_key"):
            expected_identity = batch.get(identity_field)
            observed_identity = detail.get(identity_field)
            if (
                _nonempty(expected_identity)
                and _nonempty(observed_identity)
                and observed_identity != expected_identity
            ):
                raise DirectExecutionError(
                    "staged_unreconciled_batch",
                    "get_modeling_batch returned a different original request identity",
                    actual={
                        "field": identity_field,
                        "expected": expected_identity,
                        "observed": observed_identity,
                    },
                )
        attempts = detail.get("attempts")
        if isinstance(attempts, list):
            latest = (
                next(
                    (
                        entry
                        for entry in reversed(attempts)
                        if isinstance(entry, Mapping)
                        and (
                            expected_attempt_id is None
                            or entry.get("attempt_id") == expected_attempt_id
                        )
                    ),
                    None,
                )
                if expected_attempt_id is not None
                else next((entry for entry in reversed(attempts) if isinstance(entry, Mapping)), None)
            )
            if expected_attempt_id is not None and latest is None:
                raise DirectExecutionError(
                    "staged_unreconciled_batch",
                    "get_modeling_batch did not return the original Attempt",
                    actual={"batch_id": batch_id, "attempt_id": expected_attempt_id},
                )
            if latest is not None:
                merged = dict(detail)
                for key in (
                    "attempt_id",
                    "mode",
                    "attempt_status",
                    "workspace",
                    "items",
                    "findings",
                    "retrieval_indexes",
                    "recovery",
                    "groups",
                ):
                    if key in latest:
                        merged[key] = latest[key]
                return merged
        if expected_attempt_id is not None and detail.get("attempt_id") not in {
            None,
            expected_attempt_id,
        }:
            raise DirectExecutionError(
                "staged_unreconciled_batch",
                "get_modeling_batch returned a different Attempt",
                actual={"batch_id": batch_id, "attempt_id": expected_attempt_id},
            )
        return detail

    def _batch_from_platform(
        self,
        result: Mapping[str, Any],
        batch: Mapping[str, Any],
        intent: Mapping[str, Any],
        receipt: Mapping[str, Any],
        index: int,
        source_map: Mapping[str, Any],
    ) -> dict[str, Any]:
        status = _attempt_status(result)
        state = "applied" if status in _TERMINAL_APPLIED else "not_written" if status in _TERMINAL_NOT_WRITTEN else "uncertain"
        errors = self._errors_from_findings(result.get("findings"), source_map=source_map, batch=batch, batch_index=index)
        retrieval_indexes = result.get("retrieval_indexes")
        if not isinstance(retrieval_indexes, list) or not retrieval_indexes:
            retrieval_indexes = {"status": "unknown"}
        return {
            "ontology_id": batch.get("ontology_id"),
            "change_ids": [
                self._source_for_item(batch, source_map, item.get("client_item_id")).get("change_id")
                or item.get("client_item_id")
                for item in batch.get("items", [])
            ],
            "batch_id": result.get("batch_id"),
            "attempt_id": result.get("attempt_id"),
            "write_state": state,
            "attempt_status": status,
            "resource_bindings": self._resource_bindings(result, batch, source_map),
            "model_revision_before": self._revision(result, "before"),
            "model_revision_after": self._revision(result, "after"),
            "retrieval_indexes": retrieval_indexes,
            "receipt_ref": f"value-semantics/submission-receipts/receipt-{receipt.get('ordinal')}.json",
            "intent_ordinal": intent.get("ordinal"),
            "errors": errors,
        }

    def _batch_error(
        self, batch: Mapping[str, Any], index: int, exc: DirectExecutionError, source_map: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "ontology_id": batch.get("ontology_id"),
            "change_ids": [
                self._source_for_item(batch, source_map, item.get("client_item_id")).get("change_id")
                or item.get("client_item_id")
                for item in batch.get("items", [])
            ],
            "batch_id": None,
            "attempt_id": None,
            "write_state": (
                "uncertain"
                if any(
                    marker in exc.code
                    for marker in ("unknown", "unreconciled", "receipt", "attempt_proof", "snapshot")
                )
                else "not_written"
            ),
            "attempt_status": None,
            "resource_bindings": [],
            "model_revision_before": None,
            "model_revision_after": None,
            "retrieval_indexes": {"status": "unknown"},
            "receipt_ref": None,
            "errors": self._errors_from_exception(exc, batch_index=index, source_map=source_map, batch=batch),
        }

    @staticmethod
    def _revision(result: Mapping[str, Any], phase: str) -> int | None:
        workspace = result.get("workspace")
        if isinstance(workspace, Mapping):
            value = workspace.get(f"{phase}_version")
            if type(value) is int:
                return value
        value = result.get(f"model_revision_{phase}")
        return value if type(value) is int else None

    @staticmethod
    def _resource_bindings(
        result: Mapping[str, Any], batch: Mapping[str, Any], source_map: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        rows = result.get("items")
        by_id = {
            item.get("client_item_id"): item
            for item in rows
            if isinstance(item, Mapping) and _nonempty(item.get("client_item_id"))
        } if isinstance(rows, list) else {}
        bindings: list[dict[str, Any]] = []
        for item in batch.get("items", []):
            client_id = item.get("client_item_id")
            observed = by_id.get(client_id, {})
            outputs = observed.get("resource_outputs") if isinstance(observed, Mapping) else None
            source = DirectModelExecutor._source_for_item(batch, source_map, client_id)
            row = {
                "change_id": source.get("change_id") or client_id,
                "item_id": source.get("item_id") or client_id,
                "resource_kind": source.get("resource_kind")
                or DirectModelExecutor._source_item(batch, client_id).get("resource_kind"),
            }
            if isinstance(outputs, Mapping):
                for key in ("resource_id", "resource_iri", "statement", "fact"):
                    if outputs.get(key) is not None:
                        row[key] = outputs[key]
            bindings.append(row)
        return bindings

    @staticmethod
    def _source_item(batch: Mapping[str, Any], item_id: Any) -> dict[str, Any]:
        for item in batch.get("source_items", []):
            if isinstance(item, Mapping) and item.get("client_item_id") == item_id:
                return dict(item)
        return {}

    @staticmethod
    def _source_for_item(
        batch: Mapping[str, Any], source_map: Mapping[str, Any], item_id: Any
    ) -> dict[str, Any]:
        source = DirectModelExecutor._source_for(source_map, item_id)
        if not source:
            batch_index = batch.get("index")
            nested = source_map.get(str(batch_index)) if isinstance(source_map, Mapping) else None
            if isinstance(nested, Mapping):
                value = nested.get(item_id)
                if isinstance(value, Mapping):
                    source = dict(value)
        if not source:
            for command_index, item in enumerate(batch.get("items", [])):
                if item.get("client_item_id") != item_id:
                    continue
                value = source_map.get(command_index, source_map.get(str(command_index)))
                if isinstance(value, str):
                    source = {"path": value}
                elif isinstance(value, Mapping) and any(
                    key in value for key in ("item_id", "path", "json_pointer", "candidate_path", "field_map")
                ):
                    source = dict(value)
                break
        original = DirectModelExecutor._source_item(batch, item_id)
        for key in ("change_id", "item_id", "resource_kind"):
            if source.get(key) is None and original.get(key) is not None:
                source[key] = original[key]
        return source

    @staticmethod
    def _source_for(source_map: Mapping[str, Any], item_id: Any) -> dict[str, Any]:
        if not isinstance(source_map, Mapping):
            return {}
        value = source_map.get(item_id)
        if value is None and isinstance(item_id, str):
            value = source_map.get(f"item:{item_id}") or source_map.get(f"/items/{item_id}")
        if value is None:
            for candidate in source_map.values():
                if isinstance(candidate, Mapping) and (
                    candidate.get("client_item_id") == item_id
                    or candidate.get("item_id") == item_id
                    or candidate.get("change_id") == item_id
                ):
                    value = candidate
                    break
        if isinstance(value, str):
            return {"item_id": item_id, "path": value}
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    def _errors_from_findings(
        self,
        findings: Any,
        *,
        source_map: Mapping[str, Any],
        batch: Mapping[str, Any],
        batch_index: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(findings, list):
            return []
        errors: list[dict[str, Any]] = []
        for finding in findings:
            if not isinstance(finding, Mapping):
                continue
            # Modeling Batch findings retain informational and warning
            # observations in the platform receipt. Only the platform's
            # blocking/error classification changes the execution result;
            # an informational finding such as missing_rationale does not
            # make an already-applied batch partial.
            if finding.get("blocking") is not True and finding.get("severity") != "error":
                continue
            ids = finding.get("client_item_ids")
            ids = ids if isinstance(ids, list) and ids else [None]
            for item_id in ids:
                source = self._source_for_item(batch, source_map, item_id)
                path = self._finding_path(source, finding.get("path"))
                errors.append(
                    self._error(
                        code=str(finding.get("code") or "platform_finding"),
                        change_id=source.get("change_id") or item_id,
                        item_id=source.get("item_id") or item_id,
                        path=path,
                        message=str(finding.get("message") or finding.get("code") or "platform finding"),
                        expected=finding.get("expected"),
                        actual=(finding.get("actual") if finding.get("actual") is not None else finding.get("details")),
                        platform_ref=finding.get("finding_fingerprint"),
                        retryable=bool(finding.get("retryable", False)),
                    )
                )
        return errors

    @staticmethod
    def _finding_path(source: Mapping[str, Any], finding_path: Any) -> str:
        """Map a platform field path back through the compiler's source map."""

        if isinstance(finding_path, (list, tuple)):
            raw_path = (
                "/"
                + "/".join(
                    str(part).replace("~", "~0").replace("/", "~1") for part in finding_path
                )
                if finding_path
                else ""
            )
        else:
            raw_path = finding_path if isinstance(finding_path, str) else ""
        normalized = raw_path if raw_path.startswith("/") else f"/{raw_path}" if raw_path else ""
        local_path = normalized
        path_parts = normalized.lstrip("/").split("/") if normalized else []
        if len(path_parts) >= 3 and path_parts[0] == "items" and path_parts[1].isdigit():
            local_path = "/" + "/".join(path_parts[2:])
        field_map = source.get("field_map")
        if isinstance(field_map, Mapping):
            for payload_pointer, input_pointers in field_map.items():
                pointer = str(payload_pointer)
                candidates = {
                    pointer,
                    pointer.lstrip("/"),
                    pointer.rsplit("/", 1)[-1],
                    f"/{pointer.rsplit('/', 1)[-1]}",
                }
                if (
                    normalized in candidates
                    or raw_path in candidates
                    or local_path in candidates
                    or local_path.lstrip("/") in candidates
                ):
                    if isinstance(input_pointers, list) and input_pointers:
                        first = input_pointers[0]
                        if isinstance(first, str) and first:
                            return first
            # Findings inside a mapped container retain the original nested
            # location (for example join_path/0/from_columns/0). Exact parent
            # matches alone incorrectly returned candidate/payload paths.
            prefixes = sorted(field_map, key=lambda value: len(str(value)), reverse=True)
            for payload_pointer in prefixes:
                pointer = str(payload_pointer)
                inputs = field_map[payload_pointer]
                if (local_path.startswith(pointer.rstrip("/") + "/")
                        and isinstance(inputs, list) and inputs and isinstance(inputs[0], str)):
                    original = inputs[0]
                    suffix = local_path[len(pointer):]
                    if pointer == "/payload/semantic_definition" and not original.endswith("/semantic_definition"):
                        return original  # Generated annotation points to its actual source field.
                    return original.rstrip("/") + suffix
        elif isinstance(field_map, list):
            for entry in field_map:
                if not isinstance(entry, Mapping):
                    continue
                payload_pointer = entry.get("payload_pointer")
                payload_path = entry.get("payload_path")
                candidates = {
                    value
                    for value in (payload_pointer, payload_path)
                    if isinstance(value, str) and value
                }
                if (
                    normalized in candidates
                    or raw_path in candidates
                    or local_path in candidates
                    or local_path.lstrip("/") in candidates
                ):
                    input_pointer = entry.get("input_pointer")
                    if isinstance(input_pointer, str) and input_pointer:
                        return input_pointer
        base = source.get("path") or source.get("json_pointer") or source.get("candidate_path")
        if isinstance(base, str) and base:
            if normalized == base or normalized.startswith(base.rstrip("/") + "/"):
                return normalized
            return _path_join(base, local_path or raw_path)
        return normalized or raw_path

    @staticmethod
    def _error(
        *,
        code: str,
        message: str,
        change_id: Any = None,
        item_id: Any = None,
        path: Any = "",
        expected: Any = None,
        actual: Any = None,
        platform_ref: Any = None,
        retryable: bool = True,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "change_id": change_id,
            "item_id": item_id,
            "path": path if isinstance(path, str) else "",
            "message": message,
            "expected": expected,
            "actual": actual,
            "platform_ref": platform_ref,
            "retryable": retryable,
        }

    def _errors_from_exception(
        self,
        exc: DirectExecutionError,
        *,
        batch_index: int | None,
        source_map: Mapping[str, Any],
        batch: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        actual = exc.actual
        if exc.code == "ontology_write_frozen" and batch is not None:
            rows = []
            for item in batch.get("items", []):
                if not isinstance(item, Mapping):
                    continue
                item_id = item.get("client_item_id")
                source = self._source_for_item(batch, source_map, item_id)
                rows.append(
                    self._error(
                        code=exc.code,
                        message=exc.message,
                        change_id=source.get("change_id") or item_id,
                        item_id=source.get("item_id") or item_id,
                        path=source.get("path") or source.get("candidate_path", ""),
                        actual=actual,
                        retryable=exc.retryable,
                    )
                )
            if rows:
                return rows
        if isinstance(actual, list) and batch is not None:
            rows = []
            for entry in actual:
                if not isinstance(entry, Mapping):
                    continue
                item_index = entry.get("index")
                item = batch.get("items", [])[item_index] if isinstance(item_index, int) and item_index < len(batch.get("items", [])) else None
                item_id = item.get("client_item_id") if isinstance(item, Mapping) else None
                source_batch = dict(batch)
                source_batch["index"] = batch.get("batch_index", batch_index)
                source_batch["source_items"] = batch.get("items", [])
                source = self._source_for_item(source_batch, source_map, item_id)
                rows.append(self._error(code=str(entry.get("code") or exc.code), message=str(entry.get("message") or exc.message), change_id=source.get("change_id") or item_id, item_id=source.get("item_id") or item_id, path=source.get("path") or source.get("candidate_path", ""), actual=entry, retryable=exc.retryable))
            if rows:
                return rows
        return [self._error(code=exc.code, message=exc.message, actual=actual, retryable=exc.retryable)]

    @staticmethod
    def _pending_from_batch(
        batch: Mapping[str, Any], index: int, *, reason: str = "not_executed", dependencies: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if not isinstance(batch, Mapping):
            return []
        items = batch.get("items")
        if not isinstance(items, list):
            return []
        return [
            {
                "batch_index": index,
                "ontology_id": batch.get("ontology_id"),
                "client_item_id": item.get("client_item_id"),
                "reason": reason,
                **({"dependencies": list(dependencies)} if dependencies else {}),
            }
            for item in items
            if isinstance(item, Mapping)
        ]

    def _result(
        self,
        batch_results: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        pending: list[dict[str, Any]],
        submission_digest: str,
    ) -> dict[str, Any]:
        states = [row.get("write_state") for row in batch_results]
        row_errors = [error for row in batch_results for error in row.get("errors", [])]
        has_errors = bool(errors or row_errors)
        has_partial_applied = any(
            row.get("attempt_status") == "partially_applied" for row in batch_results
        )
        if any(state == "uncertain" for state in states):
            status = "uncertain"
        elif any(state == "applied" for state in states) and (
            any(state == "not_written" for state in states)
            or pending
            or has_errors
            or has_partial_applied
        ):
            status = "partial"
        elif states and all(state == "applied" for state in states) and not pending and not has_errors:
            status = "completed"
        elif states or errors or pending:
            status = "not_written"
        else:
            status = "completed"
        return {
            "schema_version": RESULT_SCHEMA,
            "submission_ref": f"direct:{self.run_id}:{self.task_id}:{submission_digest[:16]}",
            "submission_digest": f"sha256:{submission_digest}",
            "status": status,
            "batches": batch_results,
            "errors": errors + row_errors,
            "pending_changes": pending,
        }

    def _failure_result(self, code: str, message: str, source_map: Mapping[str, Any]) -> dict[str, Any]:
        error = self._error(code=code, message=message, retryable=True)
        return self._result([], [error], [], _digest({"source_map": source_map}))

    def _scope_request(
        self, method: str, path: str, body: Mapping[str, Any] | None, *, tool: str
    ) -> Any:
        request = getattr(self.scope, "request", None)
        key = getattr(self.scope, "protocol_key", None)
        if not callable(request) or not _nonempty(key):
            raise DirectExecutionError("protocol_key_unavailable", "scope protocol request is unavailable")
        try:
            status, value = request(method, path, dict(body) if isinstance(body, Mapping) else body, key)
        except DirectExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - external REST boundary
            raise DirectExecutionError("scope_request_failed", str(exc), retryable=True) from exc
        self._notify(tool, dict(body or {}), {"status": status, "body": value})
        if not isinstance(status, int) or status < 200 or status >= 300:
            detail = value if isinstance(value, Mapping) else {}
            code = str(detail.get("code") or detail.get("error_code") or f"http_{status}")
            message = str(detail.get("message") or detail.get("detail") or f"platform request failed ({status})")
            raise DirectExecutionError(code, message, actual=detail, retryable=status in {409, 423, 429} or status >= 500)
        return value

    def _read_tool(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            if not callable(self.read):
                raise DirectExecutionError(
                    "scoped_read_unavailable", "the scoped read forwarder is unavailable"
                )
            raw = self.read(tool, dict(arguments))
            self._notify(tool, dict(arguments), raw)
            return _unwrap(raw)
        except DirectExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - scoped forwarder boundary
            raise DirectExecutionError("scoped_read_failed", str(exc), retryable=True) from exc

    def _notify(self, tool: str, arguments: Mapping[str, Any], result: Any) -> None:
        callback = self.observe_result
        if not callable(callback):
            return
        event = {"tool": tool, "arguments": dict(arguments), "result": result}
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - observation must not alter execution state
            return

__all__ = [
    "DirectExecutionError",
    "DirectModelExecutor",
    "RESULT_SCHEMA",
]
