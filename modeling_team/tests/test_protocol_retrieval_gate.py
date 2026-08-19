from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier, model_state_digest
from modeling_team.protocol_retrieval_gate import ORDINARY_RETRIEVAL_RECEIPT_SCHEMA


def _binding(path: str) -> tuple[str, str, str]:
    relation_bindings = {
        "invokesTool": ("relation", "workflow-b", "workflow-c"),
        "currentlyConsumesOutput": ("relation", "workflow-b", "quality-rating-field"),
        "unknownConcernsWorkflow": ("relation", "unknown-b-no-score-behavior", "workflow-b"),
    }
    if path in relation_bindings:
        return relation_bindings[path]
    fact_bindings = {
        "fieldName": ("fact", "quality-rating-field", "quality_rating"),
        "fieldDatatype": ("fact", "quality-rating-field", "number"),
        "unknownQuestion": (
            "fact",
            "unknown-b-no-score-behavior",
            "Does B block, continue, retry, or mark for review when C has no numeric score?",
        ),
        "unknownRationale": (
            "fact",
            "unknown-b-no-score-behavior",
            "B's note says low-scoring content is not publishable but does not state its behavior when the score is absent.",
        ),
    }
    return fact_bindings.get(path, ("fact", f"subject-{path}", f"value-{path}"))


def _candidate(*, paths: list[tuple[str, str]] | None = None) -> dict:
    paths = paths or [("q-one", "invokesTool"), ("q-two", "fieldName")]
    relation_paths = {"invokesTool", "currentlyConsumesOutput", "unknownConcernsWorkflow"}
    items = [
        {
            "item_id": f"predicate-{path}",
            "item_kind": "predicate",
            "semantic": {"predicate": path, "predicate_kind": "relation" if path in relation_paths else "fact"},
        }
        for _, path in paths
    ]
    fact_values: dict[str, dict[str, object]] = {}
    for _, path in paths:
        kind, subject, object_value = _binding(path)
        if kind == "relation":
            items.append(
                {
                    "item_id": f"relation-{path}",
                    "item_kind": "relation",
                    "semantic": {
                        "relation_id": f"relation-{path}",
                        "subject": subject,
                        "predicate": path,
                        "object": object_value,
                    },
                }
            )
        else:
            fact_values.setdefault(subject, {})[path] = object_value
    for index, (subject, values) in enumerate(sorted(fact_values.items())):
        items.append(
            {
                "item_id": f"entity-{index}",
                "item_kind": "entity",
                "semantic": {
                    "entity_id": subject,
                    "class": "TestEntity",
                    "values": {"label": subject, **values},
                },
            }
        )
    for index, (query_id, path) in enumerate(paths):
        items.append(
            {
                "item_id": f"consumer-{index}",
                "item_kind": "consumer_query",
                "semantic": {
                    "query_id": query_id,
                    "question": f"Question for {path}",
                    "required_paths": [path],
                },
            }
        )
    return {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": "revision-1",
        "scope": "slice",
        "constraints": ["preserve source meaning"],
        "items": items,
    }


def _candidate_digest(candidate: dict) -> str:
    return hashlib.sha256(
        json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _shared_path_candidate() -> dict:
    predicates = ["sharedPath", "anchorA", "anchorB"]
    items: list[dict] = [
        {
            "item_id": f"predicate-{path}",
            "item_kind": "predicate",
            "semantic": {"predicate": path, "predicate_kind": "relation"},
        }
        for path in predicates
    ]
    relations = [
        ("shared-a", "sharedPath", "root", "target-a"),
        ("shared-b", "sharedPath", "root", "target-b"),
        ("anchor-a", "anchorA", "target-a", "leaf-a"),
        ("anchor-b", "anchorB", "target-b", "leaf-b"),
    ]
    for item_id, predicate, subject, object_value in relations:
        items.append(
            {
                "item_id": item_id,
                "item_kind": "relation",
                "semantic": {
                    "relation_id": item_id,
                    "predicate": predicate,
                    "subject": subject,
                    "object": object_value,
                },
            }
        )
    items.extend(
        [
            {
                "item_id": "consumer-a",
                "item_kind": "consumer_query",
                "semantic": {"query_id": "q-a", "question": "A", "required_paths": ["sharedPath", "anchorA"]},
            },
            {
                "item_id": "consumer-b",
                "item_kind": "consumer_query",
                "semantic": {"query_id": "q-b", "question": "B", "required_paths": ["sharedPath", "anchorB"]},
            },
        ]
    )
    return {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": "revision-1",
        "scope": "slice",
        "constraints": ["preserve source meaning"],
        "items": items,
    }


def _state() -> dict:
    state = {
        "project_id": "project-1",
        "ontology_id": "ontology-1",
        "workspace_version": "workspace-1",
        "source_signature": "source-1",
        "build_session_id": "session-1",
        "graph_set_id": "graph-1",
    }
    state["state_digest"] = model_state_digest(state)
    return state


def _carrier(tmp_path: Path, candidate: dict | None = None) -> RunnerAcceptanceCarrier:
    carrier = RunnerAcceptanceCarrier(
        tmp_path / "modeling-runs" / "run-1" / "acceptance-carrier",
        task_id="r2-3-005-formal-acceptance",
        acceptance_id="acceptance",
    )
    carrier.bind_model_state(_state())
    if candidate is not None:
        carrier.register_accepted_candidate(
            candidate_revision=candidate["candidate_revision"],
            candidate_digest=_candidate_digest(candidate),
            candidate=candidate,
        )
    return carrier


def _query_args(path: str, *, resource_type: str, search_mode: str = "lexical", **extra: object) -> dict:
    return {
        "query": path,
        "project_id": "project-1",
        "scope_mode": "ontologies",
        "ontology_ids": ["ontology-1"],
        "resource_types": [resource_type],
        "assertion_types": ["asserted"],
        "search_mode": search_mode,
        "depth": 1,
        "limit": 20,
        "context_limit": 100,
        "context_cursor": None,
        "match_cursor": None,
        **extra,
    }


def _result(
    path: str,
    *,
    predicate: str | None = None,
    resource_type: str = "relation",
    evidence: bool = True,
    lineage: bool = True,
    next_context: str | None = None,
    next_match: str | None = None,
    truncated: bool = False,
    subject: str | None = None,
    object_value: object | None = None,
    object_type: str | None = None,
    result_status: str = "matched",
    recall_completeness: str = "complete",
    warnings: list[dict[str, str]] | None = None,
) -> dict:
    default_kind, default_subject, default_object = _binding(path)
    if subject is None:
        subject = default_subject
    if object_value is None:
        object_value = default_object
    if object_type is None:
        object_type = "uri" if default_kind == "relation" else "literal"
    row = {
        "id": f"statement-{path}",
        "kind": resource_type,
        "target_kind": "statement",
        "ontology_id": "ontology-1",
        "data": {
            "predicate": predicate or f"urn:test#{path}",
            "subject": subject,
            "object": object_value,
            "object_type": object_type,
            "object_datatype": "http://www.w3.org/2001/XMLSchema#string"
            if object_type == "literal"
            else None,
            "object_language": None,
        },
        "evidence_status": "supported" if evidence else "missing",
        "evidence_reference_ids": [f"evidence-{path}"] if evidence else [],
        "lineage": {"status": "complete" if lineage else "partial"},
    }
    return {
        "structuredContent": {
            "ok": True,
            "data": {
                "result_status": result_status,
                "primary_matches": [row],
                "related_context": [],
                "matches_page": {"truncated": bool(next_match), "next_match_cursor": next_match},
                "context_page": {"truncated": bool(next_context), "next_context_cursor": next_context},
                "truncated": truncated,
                "recall": {"completeness": recall_completeness, "mode": "lexical"},
                "warnings": warnings or [],
            },
        }
    }


def _register_query(carrier: RunnerAcceptanceCarrier, path: str, *, resource_type: str = "relation", result: dict | None = None, search_mode: str = "lexical", **extra: object) -> dict[str, str]:
    return carrier.register_platform_tool_result(
        tool="query_semantic_context",
        arguments=_query_args(path, resource_type=resource_type, search_mode=search_mode, **extra),
        result=result or _result(path, resource_type=resource_type),
    )


def test_platform_artifact_identity_includes_tool_name(tmp_path: Path) -> None:
    carrier = _carrier(tmp_path)
    arguments = {"ontology_id": "ontology-1", "project_id": "project-1"}
    result = {"structuredContent": {"ok": True, "data": {}}}

    first = carrier.register_platform_tool_result(
        tool="get_ontology_workspace_context", arguments=arguments, result=result
    )
    second = carrier.register_platform_tool_result(
        tool="get_modeling_context", arguments=arguments, result=result
    )

    assert first["request_digest"] != second["request_digest"]
    assert first["artifact_path"] != second["artifact_path"]
    assert first["artifact_path"].startswith("evidence/platform-responses/")
    assert second["artifact_path"].startswith("evidence/platform-responses/")


def test_candidate_plan_rejects_duplicate_required_path(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool"), ("q-one", "invokesTool")])
    with pytest.raises(AcceptanceContractError, match="duplicated"):
        _carrier(tmp_path, candidate)


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (lambda args: args.update(query="question text"), "required retrieval path"),
        (lambda args: args.update(resource_types=["concept"]), "required retrieval path"),
        (lambda args: args.update(ontology_ids=["foreign-ontology"]), "required retrieval path"),
    ],
)
def test_wrong_query_type_or_ontology_does_not_satisfy_path(tmp_path: Path, mutator, expected: str) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    args = _query_args("invokesTool", resource_type="relation")
    mutator(args)
    carrier.register_platform_tool_result(
        tool="query_semantic_context", arguments=args, result=_result("invokesTool")
    )
    with pytest.raises(AcceptanceContractError, match=expected):
        carrier.validate_ordinary_retrieval()


@pytest.mark.parametrize("kwargs", [{"predicate": "urn:test#wrong"}, {"evidence": False}, {"lineage": False}])
def test_invalid_selected_statement_does_not_satisfy_path(tmp_path: Path, kwargs: dict) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    _register_query(carrier, "invokesTool", result=_result("invokesTool", **kwargs))
    with pytest.raises(AcceptanceContractError, match="required retrieval path"):
        carrier.validate_ordinary_retrieval()


@pytest.mark.parametrize(
    ("path", "resource_type", "kwargs"),
    [
        (
            "invokesTool",
            "relation",
            {"subject": "workflow-b", "object_value": "workflow-a", "object_type": "uri"},
        ),
        (
            "fieldName",
            "fact",
            {"subject": "quality-score-field", "object_value": "quality_score", "object_type": "literal"},
        ),
    ],
)
def test_candidate_binding_rejects_wrong_subject_or_object(
    tmp_path: Path,
    path: str,
    resource_type: str,
    kwargs: dict,
) -> None:
    candidate = _candidate(paths=[("q-one", path)])
    carrier = _carrier(tmp_path, candidate)
    _register_query(carrier, path, resource_type=resource_type, result=_result(path, resource_type=resource_type, **kwargs))
    with pytest.raises(AcceptanceContractError, match="required retrieval path"):
        carrier.validate_ordinary_retrieval()


def test_invalid_cursor_chain_is_rejected(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    _register_query(
        carrier,
        "invokesTool",
        result=_result("invokesTool", next_context="context-1"),
    )
    _register_query(
        carrier,
        "invokesTool",
        result=_result("invokesTool"),
        context_cursor="wrong-context",
    )
    with pytest.raises(AcceptanceContractError, match="required retrieval path"):
        carrier.validate_ordinary_retrieval()


def test_response_may_expose_both_cursors_and_continue_match_page_context_chains(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    # First match page opens a context sub-chain and retains a pending match
    # cursor.  The context terminates, then a second match page starts a new
    # context sub-chain before the final terminal match page.
    pages = [
        (None, None, "context-1", "match-1"),
        ("context-1", None, "context-2", "match-1"),
        ("context-2", None, None, None),
        (None, "match-1", "context-3", "match-2"),
        ("context-3", None, None, None),
        (None, "match-2", None, None),
    ]
    for context_cursor, match_cursor, next_context, next_match in pages:
        result = _result(
            "invokesTool",
            next_context=next_context,
            next_match=next_match,
        )
        _register_query(
            carrier,
            "invokesTool",
            context_cursor=context_cursor,
            match_cursor=match_cursor,
            result=result,
        )
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["chains"][0]["statement_ids"] == ["statement-invokesTool"]


def test_same_path_in_two_cqs_selects_each_connected_binding(tmp_path: Path) -> None:
    candidate = _shared_path_candidate()
    carrier = _carrier(tmp_path, candidate)
    _register_query(
        carrier,
        "sharedPath",
        result=_result("sharedPath", subject="root", object_value="target-a", object_type="uri"),
    )
    _register_query(
        carrier,
        "anchorA",
        result=_result("anchorA", subject="target-a", object_value="leaf-a", object_type="uri"),
    )
    _register_query(
        carrier,
        "sharedPath",
        result=_result("sharedPath", subject="root", object_value="target-b", object_type="uri"),
    )
    _register_query(
        carrier,
        "anchorB",
        result=_result("anchorB", subject="target-b", object_value="leaf-b", object_type="uri"),
    )
    receipt = carrier.validate_ordinary_retrieval()
    shared = [chain for chain in receipt["chains"] if chain["required_path"] == "sharedPath"]
    assert [chain["binding"]["object"] for chain in shared] == ["target-a", "target-b"]


def test_same_path_cross_cq_binding_is_rejected(tmp_path: Path) -> None:
    candidate = _shared_path_candidate()
    carrier = _carrier(tmp_path, candidate)
    _register_query(
        carrier,
        "sharedPath",
        result=_result("sharedPath", subject="root", object_value="target-b", object_type="uri"),
    )
    _register_query(
        carrier,
        "anchorA",
        result=_result("anchorA", subject="target-a", object_value="leaf-a", object_type="uri"),
    )
    _register_query(
        carrier,
        "anchorB",
        result=_result("anchorB", subject="target-b", object_value="leaf-b", object_type="uri"),
    )
    with pytest.raises(AcceptanceContractError, match="required retrieval path"):
        carrier.validate_ordinary_retrieval()


def test_degraded_hybrid_warning_is_recorded_and_chain_completes(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    hybrid = _result(
        "invokesTool",
        recall_completeness="degraded",
        warnings=[{"code": "vector_index_missing", "message": "vector unavailable"}],
    )
    _register_query(carrier, "invokesTool", search_mode="hybrid", result=hybrid)
    _register_query(carrier, "invokesTool", search_mode="lexical")
    receipt = carrier.validate_ordinary_retrieval()
    # R2.3-009 C-class: quality warnings never block the chain.  The completed
    # chain carries the observed warning codes and the receipt aggregates them
    # for the independent Examiner instead of failing the handoff.
    assert receipt["chains"][0]["search_mode"] == "hybrid"
    assert (
        "retrieval recall is incomplete or degraded"
        in receipt["chains"][0]["warnings_observed"]
    )
    assert (
        "retrieval response has blocking warning: vector_index_missing"
        in receipt["warnings_observed"]
    )
    warnings_path = carrier.root.parent / "evidence" / "retrieval-quality-warnings.jsonl"
    recorded = [json.loads(line) for line in warnings_path.read_text().splitlines()]
    assert recorded and recorded[-1]["event"] == "warnings_observed"
    assert "retrieval recall is incomplete or degraded" in recorded[-1]["warnings_observed"]


def test_only_degraded_chain_builds_receipt_with_recorded_warnings(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    degraded = _result(
        "invokesTool",
        recall_completeness="degraded",
        warnings=[{"code": "degraded", "message": "incomplete recall"}],
    )
    _register_query(carrier, "invokesTool", search_mode="hybrid", result=degraded)
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["schema_version"] == ORDINARY_RETRIEVAL_RECEIPT_SCHEMA
    assert "retrieval recall is incomplete or degraded" in receipt["warnings_observed"]


def test_hybrid_failure_then_lexical_chain_completes(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    failed_hybrid = _result("invokesTool")
    failed_hybrid["structuredContent"]["data"]["primary_matches"] = []
    failed_hybrid["structuredContent"]["data"]["result_status"] = "no_match"
    _register_query(carrier, "invokesTool", result=failed_hybrid, search_mode="hybrid")
    _register_query(carrier, "invokesTool", search_mode="lexical")
    receipt = carrier.validate_ordinary_retrieval()
    assert receipt["schema_version"] == ORDINARY_RETRIEVAL_RECEIPT_SCHEMA
    assert receipt["chains"][0]["search_mode"] == "lexical"


def test_complete_two_cq_receipt_is_registered(tmp_path: Path) -> None:
    candidate = _candidate()
    carrier = _carrier(tmp_path, candidate)
    _register_query(carrier, "invokesTool", resource_type="relation")
    _register_query(carrier, "fieldName", resource_type="fact")
    receipt = carrier.ordinary_retrieval_receipt
    assert receipt is not None
    assert len(receipt["chains"]) == 2
    assert receipt["receipt_digest"]


def test_complete_formal_two_cq_seven_path_plan(tmp_path: Path) -> None:
    paths = [
        ("current-c-behavior-consumed-by-b", "invokesTool"),
        ("current-c-behavior-consumed-by-b", "currentlyConsumesOutput"),
        ("current-c-behavior-consumed-by-b", "fieldName"),
        ("current-c-behavior-consumed-by-b", "fieldDatatype"),
        ("b-behavior-without-c-score", "unknownConcernsWorkflow"),
        ("b-behavior-without-c-score", "unknownQuestion"),
        ("b-behavior-without-c-score", "unknownRationale"),
    ]
    # The gate allows a path to be shared by different query IDs, but the
    # production candidate has seven distinct required paths.  Keep this test
    # close to that real plan shape so accidental CQ-answer coupling is visible.
    candidate = _candidate(paths=paths)
    carrier = _carrier(tmp_path, candidate)
    relation_paths = {"invokesTool", "currentlyConsumesOutput", "unknownConcernsWorkflow"}
    for _, path in paths:
        _register_query(
            carrier,
            path,
            resource_type="relation" if path in relation_paths else "fact",
        )
    receipt = carrier.ordinary_retrieval_receipt
    assert receipt is not None
    assert len(receipt["chains"]) == 7


def _register_stage_artifacts(carrier: RunnerAcceptanceCarrier) -> dict[str, dict[str, object]]:
    calls = {
        "dry-run": (
            "submit_modeling_batch",
            {
                "session_id": "session-1",
                "client_batch_id": "batch-dry",
                "ontology_id": "ontology-1",
                "idempotency_key": "idem-dry",
                "expected_workspace_version": "workspace-0",
                "items": [{"client_item_id": "item-dry", "command_kind": "create_class", "payload": {"name": "X"}}],
                "mode": "dry_run",
            },
            {"mode": "dry_run", "attempt_status": "validated"},
        ),
        "apply": (
            "submit_modeling_batch",
            {
                "session_id": "session-1",
                "client_batch_id": "batch-apply",
                "ontology_id": "ontology-1",
                "idempotency_key": "idem-apply",
                "expected_workspace_version": "workspace-0",
                "items": [{"client_item_id": "item-apply", "command_kind": "create_class", "payload": {"name": "X"}}],
                "mode": "apply_atomic",
                "lease_token": "lease-1",
            },
            {
                "mode": "apply_atomic",
                "attempt_status": "applied",
                "workspace": {"after_version": "workspace-1"},
                "target": {"source_signature_after": "source-1"},
            },
        ),
        "readback": (
            "get_modeling_context",
            {"ontology_id": "ontology-1"},
            {"ontology": {"id": "ontology-1"}, "workspace": {"workspace_version": "workspace-1"}},
        ),
        "validation": (
            "run_semantic_validation",
            {"graph_set_id": "graph-1"},
            {"status": "succeeded", "graph_set_id": "graph-1"},
        ),
        "reasoning": (
            "run_semantic_reasoning",
            {"graph_set_id": "graph-1"},
            {"status": "succeeded", "graph_set_id": "graph-1"},
        ),
    }
    records: dict[str, dict[str, object]] = {}
    for stage, (tool, arguments, data) in calls.items():
        records[stage] = {
            **carrier.register_platform_tool_result(
                tool=tool,
                arguments=arguments,
                result={"structuredContent": {"ok": True, "data": {"stage": stage, **data}}},
            ),
            "tool": tool,
            "arguments": arguments,
        }
    return records


def _stage_selection(carrier: RunnerAcceptanceCarrier, records: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        stage: {
            "tool": record["tool"],
            "arguments": record["arguments"],
            "artifact_path": record["artifact_path"],
        }
        for stage, record in records.items()
    }


def test_handoff_requires_receipt_but_keeps_schema_unchanged(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path, candidate)
    records = _register_stage_artifacts(carrier)
    with pytest.raises(AcceptanceContractError, match="required retrieval path"):
        carrier.protocol_build_acceptance_stage_handoff(
            _stage_selection(carrier, records),
            protocol_id="protocol",
            capability=carrier.capability_token("protocol"),
        )

    _register_query(carrier, "invokesTool")
    built = carrier.protocol_build_acceptance_stage_handoff(
        _stage_selection(carrier, records),
        protocol_id="protocol",
        capability=carrier.capability_token("protocol"),
    )
    assert set(built["handoff_json"]) == {
        "schema_version",
        "handoff_id",
        "handoff_nonce",
        "task_id",
        "producer_run_id",
        "slice_id",
        "slice_revision",
        "model_state",
        "model_state_digest",
        "candidate_digest",
        "modeling_receipts",
        "handoff_digest",
    }


def test_foreign_artifact_is_rejected(tmp_path: Path) -> None:
    candidate = _candidate(paths=[("q-one", "invokesTool")])
    carrier = _carrier(tmp_path / "local", candidate)
    foreign = _carrier(tmp_path / "foreign", candidate)
    _register_query(foreign, "invokesTool")
    foreign_record = next(iter(foreign._platform_read_artifacts.values()))
    foreign_path = foreign.root.parent / foreign_record["artifact_path"]
    carrier._ordinary_retrieval_gate.observe(foreign_record, foreign_path)
    with pytest.raises(AcceptanceContractError, match="foreign|Runner-owned"):
        carrier.validate_ordinary_retrieval()


def test_legacy_carrier_without_candidate_plan_is_unchanged(tmp_path: Path) -> None:
    carrier = RunnerAcceptanceCarrier(
        tmp_path / "modeling-runs" / "run-legacy" / "acceptance-carrier",
        task_id="legacy-task",
        acceptance_id="acceptance",
    )
    assert carrier.ordinary_retrieval_receipt is None
    with pytest.raises(AcceptanceContractError, match="candidate plan"):
        carrier.validate_ordinary_retrieval()
