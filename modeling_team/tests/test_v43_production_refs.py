"""v4.3 production capabilities through the real run-local native broker.

No production run, Agent start, live platform mutation, or semantic verdict.
The staged submission gates and durable proof/read retention paths are real.
"""
from copy import deepcopy
import json

import pytest

from modeling_team.acceptance import AcceptanceContractError
from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS
from modeling_team.staged_decisions import (
    StagedBatchForwardUnknown, canonical_json_digest, candidate_item_digest,
    projection_digest, platform_content_hash, staged_decision_artifact_paths,
    read_submission_intents,
)
from modeling_team.tests.test_r30008b_runner_wiring import _socket_request, _write_json
from modeling_team.tests.test_r30009_runner_wiring import (
    _UnifiedRunner, _open_platform_gate_unified,
)
from modeling_team.tests.test_r30009_plan_ref_capability_schema import _protocol_capability
from modeling_team.tests.test_r4024_model_check import Store, node, read, scope, EX
from app.services.semantic_query_scope import SemanticQueryScope
from rdflib import URIRef
from rdflib.namespace import OWL

PLAN1 = "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
PLAN2 = "stage3-neutral-graph/materialization-plans/plan-2-r1.json"
CANDIDATE = "stage3-neutral-graph/candidates/cand-1-r2.json"


@pytest.fixture
def production(tmp_path):
    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    _open_platform_gate_unified(staged)
    paths = staged_decision_artifact_paths(staged.run_root, unified=True)
    candidate = json.loads((staged.run_root / CANDIDATE).read_text())
    candidate["items"].append({**deepcopy(candidate["items"][0]), "item_id": "relation-1",
                              "item_kind": "relation", "business_meaning": "Related contract",
                              "relation_endpoints": {"source": "item-entity", "target": "external-contract"}})
    _write_json(staged.run_root / CANDIDATE, candidate)
    plan1 = json.loads((staged.run_root / PLAN1).read_text())
    plan1["projection"]["candidate_digest"] = canonical_json_digest(candidate["items"])
    plan1["projection_digest"] = projection_digest(plan1["projection"])
    _write_json(staged.run_root / PLAN1, plan1)
    plan2 = deepcopy(plan1)
    plan2["plan_id"] = "plan-2"
    p = plan2["projection"]
    p["client_batch_id"] = "relationship-batch-2"
    p["ontology_id"] = "https://example.test/ontology/relationships"
    p["items"] = [{**deepcopy(p["items"][0]), "client_item_id": "relationship-item",
                   "command_kind": "create_relation", "payload": {
                       "subject_iri": "https://example.test/ontology/placeholder/entity/1",
                       "predicate_iri": "https://example.test/property/linked",
                       "object_iri": "https://example.test/ontology/approved-shared/entity/2"},
                   "rationale": "complete approved relation"}]
    p["decision_bindings"][0].update(
        client_item_id="relationship-item", candidate_item_ids=["relation-1"],
        candidate_content_digests={"relation-1": candidate_item_digest(candidate["items"][1])},
        decision_ids=["decision-2"],
    )
    plan2["projection_digest"] = projection_digest(p)
    _write_json(staged.run_root / PLAN2, plan2)
    approvals = json.loads(paths["approvals"].read_text())
    approvals["decisions"].append({**deepcopy(approvals["decisions"][0]), "decision_id": "decision-2",
                                  "target_id": "relation-1",
                                  "content_digest": candidate_item_digest(candidate["items"][1])})
    approvals["translation_approvals"] = [
        {"plan_ref": ref, "projection_digest": plan["projection_digest"],
         "approved_by": staged.runner._multi_slice_role_ids()["coordinator"],
         "decision": "approved", "reason": "complete chain reviewed"}
        for ref, plan in ((PLAN1, plan1), (PLAN2, plan2))
    ]
    _write_json(paths["approvals"], approvals)
    versions = {plan1["projection"]["ontology_id"]: 1, p["ontology_id"]: 4}
    calls = []
    store = Store()
    shared_ontology = "https://example.test/ontology/approved-shared"
    shared_graph = EX + "graph-shared"
    node(store, "ontology/approved-shared/entity/2", graph=shared_graph)
    graphs = {ontology: EX + "graph-" + str(index) for index, ontology in enumerate(versions)}

    def forward(batch):
        batch = deepcopy(batch)
        calls.append(batch)
        version = versions[batch["ontology_id"]]
        assert batch["expected_model_revision"] == version
        if batch["mode"] == "apply_atomic":
            versions[batch["ontology_id"]] += 1
            graph = graphs[batch["ontology_id"]]
            for command in batch["items"]:
                if command["command_kind"] == "create_entity":
                    node(store, "ontology/placeholder/entity/1", graph=graph)
                elif command["command_kind"] == "create_relation":
                    payload = command["payload"]
                    node(store, "property/linked", kind=OWL.ObjectProperty, graph=graph)
                    store.dataset.graph(URIRef(graph)).add(tuple(URIRef(payload[key]) for key in
                        ("subject_iri", "predicate_iri", "object_iri")))
        return {"batch_id": batch["client_batch_id"], "client_batch_id": batch["client_batch_id"],
                "attempt_id": f"attempt-{len(calls)}", "idempotency_key": batch["idempotency_key"],
                "mode": batch["mode"],
                "attempt_status": "applied" if batch["mode"] == "apply_atomic" else "validated",
                "content_hash": platform_content_hash(batch),
                "workspace": {"before_version": version, "after_version": versions[batch["ontology_id"]]}}

    def context(tool, arguments):
        assert tool == "get_modeling_context"
        ontology = arguments["ontology_id"]
        return {"ok": True, "data": {"ontology": {"id": ontology},
                "workspace": {"state": "ready", "model_revision": versions[ontology]}}}

    staged.runner.staged_batch_forwarder = forward
    staged.runner.staged_plan_read_forwarder = context
    staged.calls, staged.versions, staged.plans = calls, versions, [plan1, plan2]
    staged.store, staged.graphs = store, graphs
    staged.shared_ontology, staged.shared_graph = shared_ontology, shared_graph
    yield staged
    staged.cleanup()


def call(endpoint, name, args):
    response = _socket_request(endpoint.socket_path, endpoint.token, "tools/call",
                               name=name, arguments=args)
    assert "error" not in response, response
    result = response["result"]["structuredContent"]
    return result["data"] if result.get("ok") is True else result


def execute_args(production):
    return {"protocol_id": production.runner._multi_slice_role_ids()["protocol"],
            "plan_refs": [PLAN1, PLAN2],
            "lease_tokens": {ontology: "owned-lease" for ontology in production.versions}}


def test_native_plan_refs_execute_ordered_complete_projections_and_do_not_replay(production):
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert result["ok"] is True, result
        assert [c["mode"] for c in production.calls] == ["dry_run", "apply_atomic"] * 2
        assert [c["expected_model_revision"] for c in production.calls] == [1, 1, 4, 4]
        for index, plan in enumerate(production.plans):
            assert production.calls[2 * index]["items"] == plan["projection"]["items"]
            assert production.calls[2 * index + 1]["items"] == plan["projection"]["items"]
            assert result["completed"][index]["version_readback_ref"]["artifact_path"]
            assert result["completed"][index]["apply"]["platform_ref"]["artifact_path"]
        replay = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert [row["status"] for row in replay["completed"]] == ["already_applied"] * 2
        assert len(production.calls) == 4
    assert "batch" not in CAPABILITY_TOOL_SCHEMAS["protocol_execute_approved_plans"]["properties"]


def test_second_plan_obtains_dry_run_at_version_advanced_by_first(production):
    # Same ontology: this directly catches dry-running every plan up front.
    plan = production.plans[1]
    plan["projection"]["ontology_id"] = production.plans[0]["projection"]["ontology_id"]
    plan["projection_digest"] = projection_digest(plan["projection"])
    _write_json(production.run_root / PLAN2, plan)
    paths = staged_decision_artifact_paths(production.run_root, unified=True)
    approvals = json.loads(paths["approvals"].read_text())
    approvals["translation_approvals"][1]["projection_digest"] = plan["projection_digest"]
    _write_json(paths["approvals"], approvals)
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
    assert result["ok"] is True, result
    assert [c["expected_model_revision"] for c in production.calls] == [1, 1, 2, 2]


def test_unapproved_or_changed_projection_returns_location_before_any_write(production):
    plan = production.plans[1]
    plan["projection"]["items"][0]["rationale"] = "changed after approval"
    _write_json(production.run_root / PLAN2, plan)
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
    assert result["ok"] is False and result["status"] == "PARTIAL"
    assert result["error"]["plan_ref"] == PLAN2
    assert result["error"]["reason_code"] == "approval_content_mismatch"
    assert production.calls == []


def test_unknown_apply_stops_then_retry_never_blindly_resubmits(production):
    original = production.runner.staged_batch_forwarder

    def unknown(batch):
        if batch["mode"] == "apply_atomic":
            raise StagedBatchForwardUnknown("write reply lost")
        return original(batch)

    production.runner.staged_batch_forwarder = unknown
    with _protocol_capability(production) as endpoint:
        first = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert first["error"]["reason_code"] == "staged_batch_forward_unknown"
        retry = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert retry["error"]["reason_code"] == "staged_unreconciled_batch"
        assert len(production.calls) == 1
    assert any(i["status"] == "unknown" for i in read_submission_intents(production.run_root))


def test_applied_with_failed_readback_can_resume_without_replay(production):
    original = production.runner.staged_plan_read_forwarder
    read_count = 0

    def read_fail(tool, arguments):
        nonlocal read_count
        read_count += 1
        if read_count == 2:
            raise RuntimeError("temporary read unavailable")
        return original(tool, arguments)

    production.runner.staged_plan_read_forwarder = read_fail
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert result["error"]["stage"] == "readback" and len(production.calls) == 2
        production.runner.staged_plan_read_forwarder = original
        retry = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert retry["ok"] is True, retry
        assert retry["completed"][0]["status"] == "already_applied"
        assert len(production.calls) == 4


def test_coverage_distinguishes_missing_relation_disposition_and_actual_apply(production):
    args = {"protocol_id": execute_args(production)["protocol_id"], "candidate_ref": CANDIDATE,
            "plan_refs": [PLAN1], "dispositions": []}
    with _protocol_capability(production) as endpoint:
        partial = call(endpoint, "protocol_check_plan_coverage", args)
        assert partial["unaccounted_item_ids"] == ["relation-1"]
        assert partial["status"] == "PARTIAL"
        args["dispositions"] = [{"candidate_item_id": "relation-1", "disposition": "unknown",
                                 "reason": "cross-slice relation confirmation pending"}]
        complete = call(endpoint, "protocol_check_plan_coverage", args)
        assert complete["status"] == "COMPLETE" and complete["semantic_verdict"] == "not_evaluated"
        assert all(not row["applied_plan_refs"] for row in complete["items"])
        args.update(plan_refs=[PLAN1, PLAN2], dispositions=[])
        call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        applied = call(endpoint, "protocol_check_plan_coverage", args)
        assert all(row["applied_plan_refs"] for row in applied["items"])


def retain_pages(carrier):
    store = Store()
    node(store, "orphan")
    pages = [read(store, offset=0, limit=1), read(store, offset=1, limit=1)]
    final = read(store, limit=1)
    refs = [carrier.register_platform_tool_result(
        tool="semantic_sparql_query", arguments=page["request"],
        result={"structuredContent": page["response"]})["artifact_path"] for page in pages]
    final_ref = carrier.register_platform_tool_result(
        tool="semantic_sparql_query", arguments=final["request"],
        result={"structuredContent": final["response"]})["artifact_path"]
    return refs, final_ref


def test_native_association_refs_complete_multiple_pages_with_locators_and_partial(production):
    carrier = production.runner.acceptance
    refs, final = retain_pages(carrier)
    args = {"protocol_id": execute_args(production)["protocol_id"], "project_id": "project-1",
            "ontology_ids": ["ontology-1"], "read_refs": refs,
            "final_read_ref": final, "semantic_base_iri": EX}
    with _protocol_capability(production) as endpoint:
        complete = call(endpoint, "protocol_inspect_associations", args)
        assert complete["status"] == "COMPLETE", complete
        assert complete["statement_count"] == 2
        assert complete["candidates"][0]["resource_iri"] == EX + "orphan"
        assert complete["candidates"][0]["read_locators"][0]["response_digest"]
        partial = call(endpoint, "protocol_inspect_associations", {**args, "read_refs": refs[:1]})
        assert partial["status"] == "PARTIAL"
        assert any(i["code"] == "read_window_incomplete" for i in partial["issues"])


@pytest.mark.parametrize("invalid", ["/etc/passwd", "../other-run/evidence/platform-responses/a.json",
                                     "evidence/platform-responses/unobserved.json"])
def test_association_refs_reject_unobserved_or_arbitrary_path(production, invalid):
    refs, final = retain_pages(production.runner.acceptance)
    args = {"protocol_id": execute_args(production)["protocol_id"], "project_id": "project-1",
            "ontology_ids": ["ontology-1"], "read_refs": [invalid],
            "final_read_ref": final, "semantic_base_iri": EX}
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_inspect_associations", args)
        assert result["ok"] is False
        assert result["error"]["reason_code"] == "association_read_ref_invalid"


def test_association_retained_digest_tampering_is_actionable(production):
    refs, final = retain_pages(production.runner.acceptance)
    (production.run_root / refs[0]).chmod(0o640)
    (production.run_root / refs[0]).write_text('{}')
    with pytest.raises(AcceptanceContractError) as error:
        production.runner.acceptance.protocol_inspect_associations({
            "project_id": "project-1", "ontology_ids": ["ontology-1"],
            "read_refs": refs, "final_read_ref": final, "semantic_base_iri": EX,
        })
    assert error.value.data["reason_code"] == "association_read_ref_invalid"


def test_execution_requires_actual_governed_definition_relation_and_shared_target_readback(production):
    carrier = production.runner.acceptance
    with _protocol_capability(production) as endpoint:
        execution = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert execution["resource_readback_status"] == "pending_protocol_governed_read"
        selections = [scope(signature=production.versions[ontology], ontology_id=ontology,
                            graph=graph).ontologies[0] for ontology, graph in production.graphs.items()]
        selections.append(scope(ontology_id=production.shared_ontology,
                                graph=production.shared_graph).ontologies[0])
        selected = SemanticQueryScope(project_id="project-1", mode="ontologies", status="complete",
                                      ontologies=tuple(selections))
        pages = []
        offset = 0
        while True:
            page = read(production.store, offset=offset, limit=2, selected=selected)
            pages.append(page)
            rows = page["response"]["data"]["result"]["results"]["bindings"]
            offset += len(rows)
            if not page["response"]["data"]["truncated"]:
                break
        original_rows = [row for page in pages for row in
                         page["response"]["data"]["result"]["results"]["bindings"]]
        assert any(row["subject"]["value"] == EX + "ontology/placeholder/entity/1"
                   and row["predicate"]["value"] == EX + "property/linked"
                   and row["object"]["value"] == EX + "ontology/approved-shared/entity/2"
                   for row in original_rows)
        refs = [carrier.register_platform_tool_result(tool="semantic_sparql_query",
                  arguments=page["request"], result={"structuredContent": page["response"]})[
                  "artifact_path"] for page in pages]
        final = read(production.store, limit=1, selected=selected)
        final_ref = carrier.register_platform_tool_result(tool="semantic_sparql_query",
            arguments=final["request"], result={"structuredContent": final["response"]})["artifact_path"]
        scan = call(endpoint, "protocol_inspect_associations", {
            "protocol_id": execute_args(production)["protocol_id"], "project_id": "project-1",
            "ontology_ids": [s.ontology_id for s in selections], "read_refs": refs,
            "final_read_ref": final_ref, "semantic_base_iri": EX,
        })
        assert scan["status"] == "COMPLETE", scan
        assert set(scan["connected_resource_iris"]) == {
            EX + "ontology/placeholder/entity/1", EX + "property/linked",
            EX + "ontology/approved-shared/entity/2"}
        assert scan["candidates"] == []
        assert scan["semantic_verdict"] == "not_evaluated"


def test_reference_execution_gate_blocks_platform_reads_before_topology_open(production):
    production.runner._candidate_platform_gate.close("topology_missing_artifact")
    production.runner.staged_plan_read_forwarder = lambda *_: pytest.fail("closed gate read")
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
    assert result["error"]["reason_code"] == "staged_gate_closed"
    assert production.calls == []


def test_missing_apply_terminal_proof_requires_reconciliation_before_retry(production):
    original = production.runner.staged_batch_forwarder

    def no_proof(batch):
        result = original(batch)
        if batch["mode"] == "apply_atomic":
            result.pop("attempt_status")
        return result

    production.runner.staged_batch_forwarder = no_proof
    with _protocol_capability(production) as endpoint:
        first = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert first["error"]["reason_code"] == "staged_plan_apply_incomplete"
        retry = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert retry["error"]["reason_code"] == "staged_unreconciled_batch"
        assert len(production.calls) == 2


def test_role_contracts_preserve_coverage_and_existing_bounded_public_feedback():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for role in ("protocol", "coordinator", "modeling"):
        text = (root / f"modeling_team/agent-packages/{role}/instructions.md").read_text()
        assert "protocol_check_plan_coverage" in text
        assert "protocol_execute_approved_plans" in text
        assert "materialization_progress" in text and "public-feedback" in text
        assert "hidden" in text.lower() and "not executed" in text
    protocol = (root / "modeling_team/agent-packages/protocol/instructions.md").read_text()
    assert "protocol_inspect_associations" in protocol and "Do not transcribe" in protocol
    assert "resource_readback_status" in protocol
