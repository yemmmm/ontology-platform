from __future__ import annotations

from collections.abc import Mapping

import pytest

from modeling_team.direct_binding import execute_bound_model_changes
from modeling_team.direct_execution import DirectModelExecutor
from modeling_team.staged_batch_write_forwarder import (
    StagedBatchForwardError,
    StagedBatchForwardUnknown,
)
from modeling_team.staged_decisions import platform_content_hash, read_submission_receipts


class _Scope:
    def __init__(self, *, authorized: list[str] | None = None) -> None:
        self.project_id = "project-1"
        self.protocol_key = "protocol-key"
        self.ontology_id = "onto-1"
        self.ontology_ids = list(authorized or ["onto-1"])
        self.authorized_ontology_ids = list(authorized or ["onto-1"])
        self.owned_session_ids: set[str] = set()
        self.calls: list[tuple[str, str, Mapping[str, object] | None, str]] = []

    def request(self, method: str, path: str, body: Mapping[str, object] | None, key: str):
        self.calls.append((method, path, body, key))
        if path == "/api/projects/project-1/build-sessions":
            return 201, {"id": "session-1", "revision": 1, "status": "active"}
        if "/ontology-leases/" in path and path.endswith(":acquire"):
            ontology_id = path.rsplit("/", 1)[1][:-len(":acquire")]
            prepared_ontology_ids = set(self.ontology_ids) or {self.ontology_id}
            if ontology_id not in prepared_ontology_ids:
                raise AssertionError(f"unexpected ontology lease request: {ontology_id}")
            return 200, {
                "ontology_id": ontology_id,
                "lease_token": f"lease-{ontology_id}",
                "lease_revision": 1,
                "state": "active",
            }
        if "/ontology-leases/" in path and path.endswith(":release"):
            ontology_id = path.rsplit("/", 1)[1][:-len(":release")]
            return 200, {"ontology_id": ontology_id, "state": "released"}
        if path.endswith(":complete"):
            return 200, {"id": "session-1", "status": "completed", "revision": 2}
        if path == "/api/build-sessions/session-1":
            return 200, {"session": {"id": "session-1", "revision": 1, "status": "active"}}
        raise AssertionError(f"unexpected scope request: {method} {path}")


def _batch(*, ontology_id: str = "onto-1", item_id: str = "item-1") -> list[dict[str, object]]:
    return [
        {
            "batch_index": 0,
            "ontology_id": ontology_id,
            "items": [
                {
                    "client_item_id": item_id,
                    "change_id": "change-1",
                    "resource_kind": "entity",
                    "command_kind": "create_entity",
                    "payload": {"label": "Ticket"},
                    "depends_on": [],
                    "rationale": None,
                    "competency_question_ids": [],
                }
            ],
        }
    ]


def _source_map(item_id: str = "item-1") -> dict[str, object]:
    return {
        "0": {
            item_id: {
                "change_id": "change-1",
                "item_id": "candidate-1",
                "resource_kind": "entity",
                "candidate_path": "/items/0",
                "json_pointer": "/items/0",
                "field_map": {"/payload/label": ["/items/0/value/label"]},
            }
        }
    }


def _applied_response(batch: Mapping[str, object], *, attempt_status: str = "applied", findings=None):
    return {
        "batch_id": "batch-1",
        "client_batch_id": batch["client_batch_id"],
        "attempt_id": "attempt-1",
        "idempotency_key": batch["idempotency_key"],
        "mode": "apply_atomic",
        "attempt_status": attempt_status,
        "content_hash": platform_content_hash(batch),
        "workspace": {"before_version": 4, "after_version": 5},
        "items": [
            {
                "client_item_id": "item-1",
                "resource_outputs": {"resource_id": "resource-1"},
            }
        ],
        "findings": list(findings or []),
        "retrieval_indexes": [{"name": "lexical", "status": "ready"}],
    }


def test_direct_executor_applies_atomic_batch_and_finishes(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    observed: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        return _applied_response(batch)

    def read(tool, arguments):
        assert tool == "get_modeling_context"
        assert arguments == {"ontology_id": "onto-1"}
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit=submit,
        read=read,
        observe_result=observed.append,
    )
    result = executor.execute(_batch(), _source_map())

    assert result["status"] == "completed"
    row = result["batches"][0]
    assert row["write_state"] == "applied"
    assert row["model_revision_before"] == 4
    assert row["model_revision_after"] == 5
    assert row["resource_bindings"] == [
        {
            "change_id": "change-1",
            "item_id": "candidate-1",
            "resource_kind": "entity",
            "resource_id": "resource-1",
        }
    ]
    assert submitted[0]["mode"] == "apply_atomic"
    assert "resource_kind" not in submitted[0]["items"][0]
    assert "change_id" not in submitted[0]["items"][0]
    assert all(event["tool"] != "modeling_submit_changes" for event in observed)
    assert any(event["tool"] == "modeling_submit_model_changes" for event in observed)
    assert read_submission_receipts(tmp_path)[0]["batch_id"] == "batch-1"
    proof_text = (tmp_path / "evidence" / "staged-decisions.jsonl").read_text(encoding="utf-8")
    assert '"mode": "apply_atomic"' in proof_text

    closed = executor.close_session()
    assert closed["closed"] is True
    assert not scope.owned_session_ids
    assert all(call[3] == "protocol-key" for call in scope.calls)


def test_successful_duplicate_reuses_sidecar_without_readback_or_submit(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    read_calls: list[str] = []
    observed: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        return _applied_response(batch)

    def read(tool, arguments):
        read_calls.append(tool)
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit,
        read,
        observe_result=observed.append,
    )
    first = executor.execute(_batch(), _source_map())
    second = executor.execute(_batch(), _source_map())

    assert first["status"] == second["status"] == "completed"
    assert len(submitted) == 1
    assert read_calls == ["get_modeling_context"]
    assert [event["tool"] for event in observed if event["tool"] == "submit_modeling_batch"] == [
        "submit_modeling_batch",
        "submit_modeling_batch",
    ]
    assert executor.close_session()["closed"] is True


def test_rebuilt_executor_reuses_success_sidecar_without_replaying(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    read_calls: list[str] = []

    def submit(batch):
        submitted.append(dict(batch))
        return _applied_response(batch)

    def read(tool, arguments):
        read_calls.append(tool)
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    first_executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    first = first_executor.execute(_batch(), _source_map())
    rebuilt_executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    second = rebuilt_executor.execute(_batch(), _source_map())

    assert first["status"] == second["status"] == "completed"
    assert len(submitted) == 1
    assert read_calls == ["get_modeling_context"]
    assert rebuilt_executor.close_session()["closed"] is True


def test_unknown_result_reconciles_original_attempt_without_resubmit(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    read_calls: list[str] = []
    reconcile_reads = 0

    def submit(batch):
        submitted.append(dict(batch))
        raise StagedBatchForwardUnknown("dispatch response lost")

    def read(tool, arguments):
        nonlocal reconcile_reads
        read_calls.append(tool)
        if tool == "get_modeling_context":
            return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}
        if tool == "list_session_modeling_batches":
            if arguments.get("cursor") is None:
                return {
                    "ok": True,
                    "data": {
                        "batches": [{"batch_id": "other", "client_batch_id": "other-batch"}],
                        "next_cursor": "page-2",
                    },
                }
            return {
                "ok": True,
                "data": {
                    "batches": [{"batch_id": "batch-unknown", "client_batch_id": submitted[0]["client_batch_id"]}],
                    "next_cursor": None,
                },
            }
        assert tool == "get_modeling_batch"
        reconcile_reads += 1
        attempt_status = "applying" if reconcile_reads == 1 else "applied"
        return {
            "ok": True,
            "data": {
                "batch_id": "batch-unknown",
                "content_hash": submitted[0].get("content_hash", "observed-hash"),
                "attempts": [
                    {
                        "attempt_id": "attempt-unknown",
                        "attempt_status": attempt_status,
                        "mode": "apply_atomic",
                        "workspace": {
                            "before_version": 4,
                            "after_version": 5 if attempt_status == "applied" else None,
                        },
                        "items": (
                            [{"client_item_id": "item-1", "resource_outputs": {"resource_id": "resource-1"}}]
                            if attempt_status == "applied"
                            else []
                        ),
                        "findings": [],
                        "retrieval_indexes": [],
                    }
                ],
            },
        }

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    first = executor.execute(_batch(), _source_map())
    blocked = executor.execute(_batch(item_id="item-2"), _source_map("item-2"))
    second = executor.execute(_batch(), _source_map())

    assert first["status"] == "uncertain"
    assert blocked["status"] == "not_written"
    assert blocked["errors"][0]["code"] == "ontology_write_frozen"
    assert blocked["errors"][0]["change_id"] == "change-1"
    assert blocked["errors"][0]["item_id"] == "candidate-1"
    assert blocked["pending_changes"][0]["reason"] == "ontology_write_frozen"
    assert second["status"] == "completed"
    assert first["batches"][0]["write_state"] == "uncertain"
    assert first["batches"][0]["batch_id"] == "batch-unknown"
    assert first["batches"][0]["attempt_id"] == "attempt-unknown"
    assert second["batches"][0]["attempt_status"] == "applied"
    assert second["batches"][0]["attempt_id"] == "attempt-unknown"
    assert len(submitted) == 1
    assert read_calls.count("get_modeling_batch") == 2
    assert [receipt["batch_id"] for receipt in read_submission_receipts(tmp_path)] == [
        "batch-unknown",
        "batch-unknown",
    ]
    assert executor.close_session()["closed"] is True


def test_unresolved_ontology_freezes_new_identity_but_other_ontology_continues(tmp_path):
    scope = _Scope()
    scope.ontology_ids = ["onto-1", "onto-2"]
    scope.authorized_ontology_ids = ["onto-1"]
    submitted: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        if batch["ontology_id"] == "onto-1":
            raise StagedBatchForwardUnknown("dispatch response lost")
        response = _applied_response(batch)
        response["items"][0]["client_item_id"] = batch["items"][0]["client_item_id"]
        return response

    def read(tool, arguments):
        if tool == "get_modeling_context":
            return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}
        assert tool == "list_session_modeling_batches"
        return {"ok": True, "data": {"batches": [], "next_cursor": None}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    first = executor.execute(_batch(), _source_map())
    blocked = executor.execute(_batch(item_id="item-2"), _source_map("item-2"))
    other = executor.execute(_batch(ontology_id="onto-2", item_id="item-3"), {})

    assert first["status"] == "uncertain"
    assert blocked["status"] == "not_written"
    assert blocked["errors"][0]["code"] == "ontology_write_frozen"
    assert blocked["errors"][0]["change_id"] == "change-1"
    assert blocked["errors"][0]["item_id"] == "candidate-1"
    assert other["status"] == "completed"
    assert [batch["ontology_id"] for batch in submitted] == ["onto-1", "onto-2"]
    assert executor.close_session()["closed"] is True


def test_rebuilt_executor_reconciles_unknown_original_identity_before_retry(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    listing_calls = 0

    def submit(batch):
        submitted.append(dict(batch))
        raise StagedBatchForwardUnknown("dispatch response lost")

    def read(tool, arguments):
        nonlocal listing_calls
        if tool == "get_modeling_context":
            return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}
        if tool == "list_session_modeling_batches":
            listing_calls += 1
            if listing_calls == 1:
                return {"ok": True, "data": {"batches": [], "next_cursor": None}}
            return {
                "ok": True,
                "data": {
                    "batches": [
                        {
                            "batch_id": "batch-reconciled",
                            "client_batch_id": submitted[0]["client_batch_id"],
                        }
                    ],
                    "next_cursor": None,
                },
            }
        assert tool == "get_modeling_batch"
        response = _applied_response(submitted[0])
        response["batch_id"] = "batch-reconciled"
        response["attempt_id"] = "attempt-reconciled"
        return {"ok": True, "data": response}

    first_executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    first = first_executor.execute(_batch(), _source_map())
    rebuilt_executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    second = rebuilt_executor.execute(_batch(), _source_map())

    assert first["status"] == "uncertain"
    assert second["status"] == "completed"
    assert second["batches"][0]["batch_id"] == "batch-reconciled"
    assert len(submitted) == 1
    assert listing_calls == 2
    assert rebuilt_executor.close_session()["closed"] is True


def test_index_failure_keeps_applied_state_and_maps_finding_to_source_field(tmp_path):
    scope = _Scope()
    finding = {
        "code": "invalid_label",
        "severity": "error",
        "blocking": True,
        "client_item_ids": ["item-1"],
        "path": ["items", 0, "payload", "label"],
        "message": "label is invalid",
        "retryable": True,
    }

    def submit(batch):
        response = _applied_response(batch, findings=[finding])
        response["retrieval_indexes"] = [{"name": "semantic", "status": "failed"}]
        return response

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    result = executor.execute(_batch(), _source_map())
    row = result["batches"][0]

    assert result["status"] == "partial"
    assert row["write_state"] == "applied"
    assert row["retrieval_indexes"] == [{"name": "semantic", "status": "failed"}]
    assert result["errors"][0]["change_id"] == "change-1"
    assert result["errors"][0]["item_id"] == "candidate-1"
    assert result["errors"][0]["path"] == "/items/0/value/label"
    assert executor.close_session()["closed"] is True


def test_partially_applied_attempt_is_partial_and_keeps_applied_state(tmp_path):
    scope = _Scope()

    def submit(batch):
        return _applied_response(batch, attempt_status="partially_applied")

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    result = executor.execute(_batch(), _source_map())

    assert result["status"] == "partial"
    assert result["batches"][0]["write_state"] == "applied"
    assert result["batches"][0]["attempt_status"] == "partially_applied"
    assert executor.close_session()["closed"] is True


def test_nonblocking_platform_finding_does_not_change_applied_status(tmp_path):
    scope = _Scope()

    def submit(batch):
        return _applied_response(
            batch,
            findings=[
                {
                    "code": "missing_rationale",
                    "severity": "info",
                    "blocking": False,
                    "client_item_ids": ["item-1"],
                    "path": [],
                    "message": "Modeling Item has no rationale",
                    "retryable": False,
                }
            ],
        )

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    result = executor.execute(_batch(), _source_map())

    assert result["status"] == "completed"
    assert result["batches"][0]["write_state"] == "applied"
    assert result["errors"] == []
    assert executor.close_session()["closed"] is True


def test_out_of_scope_batch_fails_before_session_creation(tmp_path):
    scope = _Scope(authorized=["other-ontology"])
    submitted: list[dict[str, object]] = []

    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit=lambda batch: submitted.append(dict(batch)),
        read=lambda _tool, _arguments: pytest.fail("read must not be called"),
    )
    result = executor.execute(_batch(), _source_map())

    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "ontology_out_of_scope"
    assert submitted == []
    assert scope.calls == []


def test_platform_scope_prepared_ontology_ids_override_empty_authorized_list(tmp_path):
    scope = _Scope()
    scope.ontology_ids = []
    scope.authorized_ontology_ids = []
    submitted: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        return _applied_response(batch)

    def read(tool, arguments):
        assert tool == "get_modeling_context"
        assert arguments == {"ontology_id": "onto-1"}
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit=submit,
        read=read,
    )
    result = executor.execute(_batch(), _source_map())

    assert result["status"] == "completed"
    assert len(submitted) == 1
    assert executor.close_session()["closed"] is True


def test_platform_scope_topology_ids_include_existing_and_created_ontologies(tmp_path):
    scope = _Scope()
    scope.ontology_id = "onto-old"
    scope.ontology_ids = ["onto-old", "onto-created"]
    scope.authorized_ontology_ids = ["onto-old"]
    submitted: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        response = _applied_response(batch)
        response["batch_id"] = f"batch-{batch['items'][0]['client_item_id']}"
        response["items"][0]["client_item_id"] = batch["items"][0]["client_item_id"]
        return response

    def read(tool, arguments):
        assert tool == "get_modeling_context"
        assert arguments["ontology_id"] in {"onto-old", "onto-created"}
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    second_batch = _batch(ontology_id="onto-created", item_id="created-item")[0]
    second_batch["batch_index"] = 1
    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit=submit,
        read=read,
    )
    result = executor.execute([_batch(ontology_id="onto-old")[0], second_batch], {})

    assert result["status"] == "completed"
    assert [batch["ontology_id"] for batch in submitted] == ["onto-old", "onto-created"]
    assert executor.close_session()["closed"] is True


def test_malformed_items_report_without_creating_session(tmp_path):
    scope = _Scope()
    executor = DirectModelExecutor(
        scope,
        tmp_path,
        "run-1",
        "task-1",
        submit=lambda _batch: pytest.fail("submit must not be called"),
        read=lambda _tool, _arguments: pytest.fail("read must not be called"),
    )

    result = executor.execute(
        [{"batch_index": 0, "ontology_id": "onto-1", "items": None}],
        {},
    )

    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "batch_items_required"
    assert result["pending_changes"] == []
    assert scope.calls == []


def test_definite_forward_failure_is_not_written_and_does_not_replay(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []

    def submit(batch):
        submitted.append(dict(batch))
        raise StagedBatchForwardError("validation rejected before write")

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    first = executor.execute(_batch(), _source_map())
    second = executor.execute(_batch(), _source_map())

    assert first["status"] == second["status"] == "not_written"
    assert first["batches"][0]["write_state"] == "not_written"
    assert second["errors"][0]["code"] == "staged_batch_rejected"
    assert len(submitted) == 1
    assert executor.close_session()["closed"] is True


def test_failed_batch_blocks_cross_batch_dependents_and_preserves_partial_result(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    batches = _batch() + [
        {
            "batch_index": 1,
            "ontology_id": "onto-1",
            "depends_on_batches": [0],
            "items": [
                {
                    "client_item_id": "item-2",
                    "change_id": "change-2",
                    "resource_kind": "relation",
                    "command_kind": "create_relation",
                    "payload": {"source_entity_iri": {"item_ref": {"client_item_id": "item-1", "output": "resource_iri"}}},
                    "depends_on": [],
                    "rationale": None,
                    "competency_question_ids": [],
                }
            ],
        },
    ]
    source_map = {
        **_source_map(),
        "1": {
            "item-2": {
                "change_id": "change-2",
                "item_id": "candidate-2",
                "resource_kind": "relation",
                "cross_batch_dependencies": [
                    {"depends_on": "item-1", "depends_on_batch": 0}
                ],
            }
        },
    }

    def submit(batch):
        submitted.append(dict(batch))
        raise StagedBatchForwardError("first batch rejected")

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    result = execute_bound_model_changes(executor, batches, source_map)

    assert result["status"] == "not_written"
    assert len(submitted) == 1
    assert result["pending_changes"] == [
        {
            "batch_index": 1,
            "ontology_id": "onto-1",
            "client_item_id": "item-2",
            "reason": "dependency_not_applied",
            "dependencies": ["batch:0"],
        }
    ]
    assert executor.close_session()["closed"] is True


def test_cross_batch_item_ref_is_bound_to_observed_output_before_submit(tmp_path):
    scope = _Scope()
    submitted: list[dict[str, object]] = []
    batches = _batch() + [
        {
            "batch_index": 1,
            "ontology_id": "onto-1",
            "depends_on_batches": [0],
            "items": [
                {
                    "client_item_id": "item-2",
                    "change_id": "change-2",
                    "resource_kind": "relation",
                    "command_kind": "create_relation",
                    "payload": {"source_entity_iri": {"item_ref": {"client_item_id": "item-1", "output": "resource_iri"}}},
                    "depends_on": [],
                    "rationale": None,
                    "competency_question_ids": [],
                }
            ],
        },
    ]
    source_map = {
        **_source_map(),
        "1": {
            "item-2": {
                "change_id": "change-2",
                "item_id": "candidate-2",
                "resource_kind": "relation",
                "cross_batch_dependencies": [
                    {"depends_on": "item-1", "depends_on_batch": 0}
                ],
            }
        },
    }

    def submit(batch):
        submitted.append(dict(batch))
        if len(submitted) == 1:
            response = _applied_response(batch)
            response["items"][0]["resource_outputs"] = {"resource_iri": "iri:entity-1"}
            return response
        assert batch["items"][0]["payload"]["source_entity_iri"] == "iri:entity-1"
        response = _applied_response(batch)
        response["items"] = [{"client_item_id": "item-2", "resource_outputs": {"statement": "stmt-2"}}]
        return response

    def read(tool, arguments):
        return {"ok": True, "data": {"workspace": {"state": "ready", "model_revision": 4}}}

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, read)
    result = execute_bound_model_changes(executor, batches, source_map)

    assert result["status"] == "completed"
    assert len(submitted) == 2
    assert executor.close_session()["closed"] is True


def _binding_batches() -> tuple[list[dict[str, object]], dict[str, object]]:
    batches = _batch() + [
        {
            "batch_index": 1,
            "ontology_id": "onto-1",
            "depends_on_batches": [0],
            "items": [
                {
                    "client_item_id": "item-2",
                    "change_id": "change-2",
                    "resource_kind": "relation",
                    "command_kind": "create_relation",
                    "payload": {
                        "source_entity_iri": {
                            "item_ref": {
                                "client_item_id": "item-1",
                                "output": "resource_iri",
                            }
                        },
                        "literal": {
                            "item_ref": {
                                "client_item_id": "literal-data",
                                "output": "resource_iri",
                            }
                        },
                    },
                    "depends_on": [],
                },
                {
                    "client_item_id": "item-3",
                    "change_id": "change-3",
                    "resource_kind": "relation",
                    "command_kind": "create_relation",
                    "payload": {
                        "source_entity_iri": {
                            "item_ref": {
                                "client_item_id": "item-2",
                                "output": "resource_iri",
                            }
                        }
                    },
                    "depends_on": [],
                },
            ],
        }
    ]
    source_map = {
        **_source_map(),
        "1": {
            "item-2": {
                "change_id": "change-2",
                "item_id": "candidate-2",
                "resource_kind": "relation",
                "field_map": {"/payload/source_entity_iri": ["/items/1/value/source_entity_iri"]},
                "cross_batch_dependencies": [
                    {"depends_on": "item-1", "depends_on_batch": 0}
                ],
            },
            "item-3": {
                "change_id": "change-3",
                "item_id": "candidate-3",
                "resource_kind": "relation",
            },
        },
    }
    return batches, source_map


class _BindingExecutor:
    def __init__(self, *, first_status: str = "completed", first_outputs=None):
        self.calls: list[tuple[list[dict[str, object]], dict[str, object]]] = []
        self.first_status = first_status
        self.first_outputs = first_outputs or {"resource_iri": "iri:entity-1"}

    def execute(self, batches, source_map):
        self.calls.append((batches, source_map))
        if len(self.calls) == 1 and self.first_status == "uncertain":
            return {
                "schema_version": "r4-3-025-model-change-result/v1",
                "submission_ref": "phase-1",
                "submission_digest": "sha256:phase-1",
                "status": "uncertain",
                "batches": [
                    {
                        "write_state": "uncertain",
                        "attempt_status": "applying",
                        "resource_bindings": [],
                        "errors": [],
                    }
                ],
                "errors": [],
                "pending_changes": [],
            }
        bindings = (
            [self.first_outputs]
            if len(self.calls) == 1
            else [{"statement": "statement-2"}, {"statement": "statement-3"}]
        )
        return {
            "schema_version": "r4-3-025-model-change-result/v1",
            "submission_ref": f"phase-{len(self.calls)}",
            "submission_digest": f"sha256:phase-{len(self.calls)}",
            "status": "completed",
            "batches": [
                {
                    "write_state": "applied",
                    "attempt_status": "applied",
                    "resource_bindings": bindings,
                    "errors": [],
                }
            ],
            "errors": [],
            "pending_changes": [],
        }


def test_binding_boundary_keeps_same_batch_ref_and_carries_original_stage():
    batches, source_map = _binding_batches()
    executor = _BindingExecutor()

    result = execute_bound_model_changes(executor, batches, source_map)

    assert result["status"] == "completed"
    assert [row["batch_index"] for row in result["batches"]] == [0, 1]
    second_batch, second_map = executor.calls[1]
    assert second_batch[0]["depends_on_batches"] == []
    assert second_batch[0]["items"][0]["payload"]["source_entity_iri"] == "iri:entity-1"
    assert second_batch[0]["items"][0]["payload"]["literal"] == {
        "item_ref": {"client_item_id": "literal-data", "output": "resource_iri"}
    }
    assert second_batch[0]["items"][1]["payload"]["source_entity_iri"] == {
        "item_ref": {"client_item_id": "item-2", "output": "resource_iri"}
    }
    assert "cross_batch_dependencies" not in second_map["1"]["item-2"]


def test_binding_boundary_does_not_call_dependent_phase_after_unknown():
    batches, source_map = _binding_batches()
    executor = _BindingExecutor(first_status="uncertain")

    result = execute_bound_model_changes(executor, batches, source_map)

    assert result["status"] == "uncertain"
    assert len(executor.calls) == 1
    assert {item["client_item_id"] for item in result["pending_changes"]} == {"item-2", "item-3"}


def test_binding_boundary_maps_missing_output_to_source_field():
    batches, source_map = _binding_batches()
    executor = _BindingExecutor(first_outputs={"resource_id": "resource-1"})

    result = execute_bound_model_changes(executor, batches, source_map)

    assert result["status"] == "partial"
    assert len(executor.calls) == 1
    assert result["errors"][0]["code"] == "cross_batch_output_unavailable"
    assert result["errors"][0]["change_id"] == "change-2"
    assert result["errors"][0]["item_id"] == "candidate-2"
    assert result["errors"][0]["path"] == "/items/1/value/source_entity_iri"


def test_exact_session_identity_is_created_once_for_ordered_batches(tmp_path):
    scope = _Scope()
    batches = _batch() + _batch(item_id="item-2")
    batches[1]["batch_index"] = 1
    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", _applied_response,
                                   lambda tool, args: {"workspace": {"model_revision": 4}})
    assert executor.execute(batches)["status"] == "completed"
    creates = [call for call in scope.calls if call[1] == "/api/projects/project-1/build-sessions"]
    assert len(creates) == 1
    assert creates[0][2] == {"client_session_id": "direct:run-1:task-1"}


def test_missing_read_uses_scoped_rest_workspace_context(tmp_path):
    scope = _Scope()
    original_request = scope.request

    def request(method, path, body, key):
        if path == "/api/ontologies/onto-1/modeling-context":
            scope.calls.append((method, path, body, key))
            return 200, {"workspace": {"state": "ready", "model_revision": 17}}
        return original_request(method, path, body, key)

    scope.request = request
    submitted = []

    def submit(batch):
        submitted.append(batch)
        return _applied_response(batch)

    executor = DirectModelExecutor(scope, tmp_path, "run-1", "task-1", submit, None)
    assert executor.execute(_batch())["status"] == "completed"
    assert submitted[0]["expected_model_revision"] == 17
    assert ("GET", "/api/ontologies/onto-1/modeling-context", None, "protocol-key") in scope.calls


@pytest.mark.parametrize("index_key", [0, "0"])
def test_command_index_source_map_maps_findings_to_candidate(tmp_path, index_key):
    def submit(batch):
        return _applied_response(batch, attempt_status="validation_failed", findings=[{
            "severity": "error", "code": "invalid_label", "client_item_ids": ["item-1"],
            "path": "/items/0/payload/label",
        }])

    executor = DirectModelExecutor(_Scope(), tmp_path, "run-1", "task-1", submit,
                                   lambda tool, args: {"workspace": {"model_revision": 4}})
    result = executor.execute(_batch(), {index_key: {
        "item_id": "candidate-1", "json_pointer": "/items/7",
        "field_map": {"/payload/label": ["/items/7/value/label"]},
    }})
    assert result["errors"][0]["item_id"] == "candidate-1"
    assert result["errors"][0]["path"] == "/items/7/value/label"
