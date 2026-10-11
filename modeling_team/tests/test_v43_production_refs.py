"""v4.3 production capabilities through the real run-local native broker.

No production run, Agent start, live platform mutation, or semantic verdict.
The staged submission gates and durable proof/read retention paths are real.
"""
from copy import deepcopy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.acceptance import AcceptanceContractError, RunnerAcceptanceCarrier
from modeling_team.capability_mcp import (
    CAPABILITY_TOOL_SCHEMAS, PROTOCOL_OPERATIONS, STAGED_UNIFIED_PROTOCOL_OPERATIONS,
    UNIFIED_PROTOCOL_RUN_OPERATIONS,
)
from modeling_team.runtimes.codex import CodexRuntimeAdapter
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


def test_dry_run_references_preserve_items_without_lease_or_apply(production):
    args = {**execute_args(production), "mode": "dry_run", "lease_tokens": {}}
    before = dict(production.versions)
    with _protocol_capability(production) as endpoint:
        listing = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        tools = {tool["name"]: tool for tool in listing["result"]["tools"]}
        reference = tools["protocol_execute_approved_plans"]
        assert reference["inputSchema"]["properties"]["mode"]["enum"] == [
            "dry_run", "apply_atomic",
        ]
        assert "dry_run" in reference["description"]
        assert reference["description"] != tools["protocol_staged_submit_modeling_batch"]["description"]
        result = call(endpoint, "protocol_execute_approved_plans", args)
        assert result["ok"] is True and result["status"] == "COMPLETE", result
        assert result["resource_readback_status"] == "not_applied"
        assert [row["status"] for row in result["completed"]] == ["validated", "validated"]
        assert all("apply" not in row for row in result["completed"])
        replay = call(endpoint, "protocol_execute_approved_plans", args)
        assert replay["ok"] is True, replay
    assert production.versions == before
    assert [batch["mode"] for batch in production.calls] == ["dry_run", "dry_run"]
    for batch, plan in zip(production.calls, production.plans):
        assert batch["items"] == plan["projection"]["items"]
        assert "lease_token" not in batch


def test_apply_after_reference_dry_run_reuses_current_proofs(production):
    with _protocol_capability(production) as endpoint:
        validation = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "mode": "dry_run", "lease_tokens": {},
        })
        assert validation["ok"] is True, validation
        applied = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert applied["ok"] is True, applied
    assert [batch["mode"] for batch in production.calls] == [
        "dry_run", "dry_run", "apply_atomic", "apply_atomic",
    ]
    assert all(row["status"] == "applied" for row in applied["completed"])


def test_reference_dry_run_does_not_require_translation_approval_but_apply_does(production):
    paths = staged_decision_artifact_paths(production.run_root, unified=True)
    approvals = json.loads(paths["approvals"].read_text())
    approvals["translation_approvals"] = []
    _write_json(paths["approvals"], approvals)
    with _protocol_capability(production) as endpoint:
        validation = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "mode": "dry_run", "lease_tokens": {},
        })
        assert validation["ok"] is True, validation
        applied = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert applied["ok"] is False, applied
        assert applied["error"]["reason_code"] == "approval_missing"
    assert [batch["mode"] for batch in production.calls] == ["dry_run", "dry_run"]


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


@pytest.mark.parametrize("mode", ["dry_run", "apply_atomic"])
def test_unapproved_or_changed_projection_returns_location_before_any_write(production, mode):
    plan = production.plans[1]
    plan["projection"]["items"][0]["rationale"] = "changed after approval"
    _write_json(production.run_root / PLAN2, plan)
    with _protocol_capability(production) as endpoint:
        result = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "mode": mode,
        })
    assert result["ok"] is False and result["status"] == "PARTIAL"
    assert result["error"]["plan_ref"] == PLAN2
    assert result["error"]["reason_code"] == "approval_content_mismatch"
    assert production.calls == []


@pytest.mark.parametrize("retry_mode", ["dry_run", "apply_atomic"])
def test_unknown_apply_stops_then_retry_never_blindly_resubmits(production, retry_mode):
    original = production.runner.staged_batch_forwarder

    def unknown(batch):
        if batch["mode"] == "apply_atomic":
            raise StagedBatchForwardUnknown("write reply lost")
        return original(batch)

    production.runner.staged_batch_forwarder = unknown
    with _protocol_capability(production) as endpoint:
        first = call(endpoint, "protocol_execute_approved_plans", execute_args(production))
        assert first["error"]["reason_code"] == "staged_batch_forward_unknown"
        retry = call(endpoint, "protocol_execute_approved_plans", {
            **execute_args(production), "mode": retry_mode,
        })
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


# --- R4 staged native reads: real runtime retention and the association catalog ---


class _StagedAssociationRun:
    """A real staged non-formal carrier plus the runtime sink bound to it.

    No docs fixtures, live platform, Agent start, or semantic verdict: the
    carrier, its unified capability endpoint, and the runtime notification
    sink are the production objects under test.
    """

    def __init__(self, tmp_path) -> None:
        self.run_root = tmp_path / "modeling-runs" / "staged-association-run"
        self.run_root.mkdir(parents=True)
        self.carrier = RunnerAcceptanceCarrier(
            self.run_root / "acceptance-carrier",
            task_id="staged-association-run",
            acceptance_id="acceptance",
            staged_protocol_capability=True,
            staged_plan_handler=lambda args: {"status": "COMPLETE"},
        )
        self.endpoint = self.carrier.capability_endpoint("protocol")
        self.endpoint.start()
        self.runtime = CodexRuntimeAdapter(
            repository_root=Path(__file__).resolve().parents[2], use_bwrap=False
        )
        self.runtime._run_root = self.run_root
        self.runtime._acceptance = self.carrier
        self.runtime._coordination_enabled = False
        # start_roster binds exactly these two flags for a staged unified run;
        # the notification sink keys its staged observation on both.
        self.runtime._staged_decisions_enabled = True
        self.runtime._unified_graph = True
        self.runtime._active_run = SimpleNamespace(
            root=self.run_root,
            run_id="staged-association-run",
            configuration=SimpleNamespace(
                task=SimpleNamespace(
                    schema_version=2,
                    task_id="staged-association-run",
                    parameters={
                        "multi_slice_workflow": True,
                        "staged_modeling_decisions": True,
                        "unified_semantic_graph": True,
                    },
                )
            ),
        )

    def cleanup(self) -> None:
        self.endpoint.stop()
        self.runtime.stop()
        self.carrier.cleanup()


@pytest.fixture
def staged_run(tmp_path):
    staged = _StagedAssociationRun(tmp_path)
    yield staged
    staged.cleanup()


def _notification_agent(role="protocol"):
    # The real _Agent carries a reentrant RLock and _notification holds it
    # while it calls the completed-item hooks; a plain Lock would deadlock.
    return SimpleNamespace(
        agent_id=role,
        package=SimpleNamespace(role=role, package_id=role),
        state_lock=threading.RLock(),
        fallback_eligible=False,
    )


def _completed_sparql_item(item_id, page, *, status="completed", server="ontology_platform"):
    return {
        "method": "item/completed",
        "params": {
            "item": {
                "id": item_id,
                "type": "mcpToolCall",
                "server": server,
                "tool": "semantic_sparql_query",
                "status": status,
                "arguments": page["request"],
                "result": {"structuredContent": page["response"]},
            }
        },
    }


def _sparql_pages():
    store = Store()
    node(store, "orphan")
    pages = [read(store, offset=0, limit=1), read(store, offset=1, limit=1)]
    final = read(store, limit=1)
    assert final["request"] == pages[0]["request"]
    return pages, final


def _sparql_read_records(carrier):
    return [
        record
        for record in carrier._platform_read_artifacts.values()
        if record["tool"] == "semantic_sparql_query"
    ]


def test_staged_runtime_retains_completed_ontology_platform_reads(staged_run):
    """Non-formal staged Protocol runs with a carrier keep their real reads.

    The app-server ``item/completed`` notification is the trusted owner of the
    native ``ontology_platform`` request/result bytes.  A staged R4 run binds a
    real RunnerAcceptanceCarrier even though formal coordination stays off, so
    completed governed SPARQL pages must land in the immutable registry;
    failed, non-Protocol, other-server, and carrier-less events stay excluded.
    """

    pages, final = _sparql_pages()
    runtime, carrier = staged_run.runtime, staged_run.carrier
    agent = _notification_agent()
    for index, page in enumerate([*pages, final]):
        runtime._notification(agent, _completed_sparql_item(f"native-{index}", page))
    reads = _sparql_read_records(carrier)
    assert len(reads) == 2  # page0 and the final snapshot share one identity
    evidence = staged_run.run_root / "evidence" / "platform-response-artifacts.jsonl"
    # The sink appends one evidence line per processed completed item; the
    # registry itself dedupes the identical final snapshot observation.
    assert len(evidence.read_text().splitlines()) == 3
    for record in reads:
        artifact = staged_run.run_root / record["artifact_path"]
        assert artifact.is_file()
        assert record["request_digest"] in record["artifact_path"]
        assert record["response_digest"] in record["artifact_path"]
        assert record["successful"] is True
    # Replaying the same completed item keeps exactly one observation.
    runtime._notification(agent, _completed_sparql_item("native-0", pages[0]))
    assert len(_sparql_read_records(carrier)) == 2
    assert len(evidence.read_text().splitlines()) == 4

    # Existing boundaries: failed, non-Protocol, and other-server events are
    # still not retained.
    runtime._notification(
        agent, _completed_sparql_item("native-failed", pages[0], status="failed")
    )
    runtime._notification(
        _notification_agent(role="modeling"),
        _completed_sparql_item("native-modeling", pages[0]),
    )
    runtime._notification(
        agent,
        _completed_sparql_item("native-other", pages[0], server="protocol_mechanics"),
    )
    assert len(_sparql_read_records(carrier)) == 2
    assert len(evidence.read_text().splitlines()) == 4


def test_runtime_sink_without_carrier_or_staged_unified_records_nothing(tmp_path):
    """No carrier, or staged without the unified capability: prior boundary.

    A staged 008B run without the R4.0-024 unified surface keeps the old
    no-recording behavior even though it binds a carrier.
    """

    pages, _ = _sparql_pages()
    for carrier_bound, staged_unified in ((False, False), (True, False)):
        label = "carrier-less" if not carrier_bound else "staged-not-unified"
        run_root = tmp_path / "modeling-runs" / label
        run_root.mkdir(parents=True)
        runtime = CodexRuntimeAdapter(
            repository_root=Path(__file__).resolve().parents[2], use_bwrap=False
        )
        runtime._run_root = run_root
        runtime._coordination_enabled = False
        runtime._staged_decisions_enabled = True
        runtime._unified_graph = staged_unified
        if carrier_bound:
            runtime._acceptance = SimpleNamespace()
        try:
            runtime._notification(
                _notification_agent(),
                _completed_sparql_item(f"native-{label}", pages[0]),
            )
            assert not (
                run_root / "evidence" / "platform-response-artifacts.jsonl"
            ).exists(), label
        finally:
            runtime.stop()


def test_formal_coordination_runtime_sink_keeps_recording(staged_run):
    """The formal coordination semantics of the sink are unchanged."""

    pages, _ = _sparql_pages()
    staged_run.runtime._coordination_enabled = True
    staged_run.runtime._notification(
        _notification_agent(), _completed_sparql_item("native-formal", pages[0])
    )
    assert len(_sparql_read_records(staged_run.carrier)) == 1


def test_formal_capability_assembly_stays_duplicate_free_with_staged_handlers(tmp_path):
    """A formal carrier that also mounts the staged handlers never duplicates
    the listing operation: PROTOCOL_OPERATIONS already advertises it, and the
    staged run operations add no second copy."""

    carrier = RunnerAcceptanceCarrier(
        tmp_path / "formal-staged",
        task_id="formal-staged-assembly",
        acceptance_id="acceptance",
        candidate_receipt_builder=lambda protocol_id, delivery_id: {},
        candidate_conflict_builder=lambda *args, **kwargs: {},
        staged_submission_handler=lambda args: {"ok": True},
        staged_plan_handler=lambda args: {"status": "COMPLETE"},
        staged_protocol_capability=True,
    )
    operations = carrier.capability_endpoint("protocol").operations
    assert operations == (*PROTOCOL_OPERATIONS, *UNIFIED_PROTOCOL_RUN_OPERATIONS)
    assert operations.count("protocol_list_platform_artifacts") == 1
    assert len(set(operations)) == len(operations)


def test_staged_association_scan_uses_runtime_retained_refs_from_catalog(staged_run):
    """Staged scans take observation metadata from the advertised catalog.

    ``protocol_inspect_associations`` resolves only retained read references,
    so the staged unified Protocol surface must also advertise the existing
    ``protocol_list_platform_artifacts`` catalog read that publishes those
    observed artifact identities; the scan then completes on actual
    references instead of Agent-transcribed pages.
    """

    pages, final = _sparql_pages()
    runtime = staged_run.runtime
    agent = _notification_agent()
    for index, page in enumerate([*pages, final]):
        runtime._notification(agent, _completed_sparql_item(f"native-{index}", page))
    endpoint = staged_run.endpoint
    listing = _socket_request(
        endpoint.socket_path, endpoint.token, "tools/list"
    )
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert set(names) == set(STAGED_UNIFIED_PROTOCOL_OPERATIONS)
    assert "protocol_list_platform_artifacts" in names
    assert "protocol_inspect_associations" in names
    # The runtime's declared preflight surface matches the live socket exactly.
    assert staged_run.runtime._role_capability_operations(
        "protocol", run=staged_run.runtime._active_run
    ) == tuple(names)

    catalog = call(endpoint, "protocol_list_platform_artifacts", {"protocol_id": "protocol"})
    reads = [
        artifact for artifact in catalog["artifacts"]
        if artifact["tool"] == "semantic_sparql_query"
    ]
    assert len(reads) == 2
    assert all(artifact["successful"] is True for artifact in reads)
    assert reads[0]["request_arguments"] == pages[0]["request"]
    assert reads[1]["request_arguments"] == pages[1]["request"]
    read_refs = [artifact["artifact_path"] for artifact in reads]
    final_ref = next(
        artifact["artifact_path"] for artifact in reads
        if artifact["request_arguments"] == final["request"]
    )
    scan = call(endpoint, "protocol_inspect_associations", {
        "protocol_id": "protocol", "project_id": "project-1",
        "ontology_ids": ["ontology-1"], "read_refs": read_refs,
        "final_read_ref": final_ref, "semantic_base_iri": EX,
    })
    assert scan["status"] == "COMPLETE", scan
    assert scan["candidates"][0]["resource_iri"] == EX + "orphan"
    assert scan["candidates"][0]["read_locators"][0]["artifact_path"] in read_refs
    assert scan["candidates"][0]["read_locators"][0]["response_digest"]
    assert scan["final_read_ref"] == final_ref


def _wrapped_native_result(page, *, inner_error=False, ok_payload=True, raw_text=None):
    """The production native CallToolResult shape for a large governed read.

    ``structuredContent`` is null and the whole result rides as JSON inside a
    text content item; that wrapper carries the payload twice (its own
    ``content[0].text`` JSON and its ``structuredContent``), matching the
    observed ~1MB pages byte-for-byte in shape.
    """
    if raw_text is not None:
        inner = {"isError": inner_error, "content": [{"type": "text", "text": raw_text}]}
    else:
        payload = page["response"] if ok_payload else {
            "ok": False, "error": {"code": "scope_not_ready"}}
        inner = {
            "isError": inner_error,
            "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
            "structuredContent": payload,
        }
    return {
        "structuredContent": None,
        "content": [{"type": "text", "text": json.dumps(inner, sort_keys=True)}],
    }


def _retained_native_result(staged_run, agent, label, request, result):
    """Observe one completed native item through the real runtime sink."""
    before = set(staged_run.carrier._platform_read_artifacts)
    staged_run.runtime._notification(agent, {
        "method": "item/completed",
        "params": {"item": {
            "id": f"native-{label}", "type": "mcpToolCall", "server": "ontology_platform",
            "tool": "semantic_sparql_query", "status": "completed",
            "arguments": request, "result": result,
        }},
    })
    registry = staged_run.carrier._platform_read_artifacts
    fresh = sorted(set(registry) - before)
    assert len(fresh) == 1
    return registry[fresh[0]]


def test_staged_association_scan_unwraps_native_text_envelope_pages(staged_run):
    """Large native pages ride as text-JSON MCP envelopes; the scan still sees {ok,data}.

    The retained, hash-verified bytes stay authoritative: both supported
    native shapes (the plain ``structuredContent`` mapping and the
    CallToolResult whose governed read is JSON-encoded inside a text content
    item) resolve to the same original payload, so a mixed plain/wrapped
    scan completes on real references with unchanged artifact bytes and the
    same candidates as an all-plain scan.  An error wrapper, a malformed
    text item or a non-MCP payload never becomes a success: the scan stays
    PARTIAL with ``governed_read_failed`` and zero statements, and
    unobserved references keep their rejection.
    """
    import hashlib

    store = Store()
    node(store, "orphan")
    node(store, "linked")
    # limit-2 pages keep the final read (limit 1, OFFSET 0) a distinct
    # observation: the ~1MB page shape and the small final shape coexist in
    # one registry exactly as in production.
    wrapped_page = read(store, offset=0, limit=2)
    plain_page = read(store, offset=2, limit=2)
    final = read(store, limit=1)
    assert len(wrapped_page["response"]["data"]["result"]["results"]["bindings"]) == 2
    assert wrapped_page["request"] != final["request"]

    runtime, carrier = staged_run.runtime, staged_run.carrier
    agent = _notification_agent()
    wrapped_record = _retained_native_result(
        staged_run, agent, "wrapped-0", wrapped_page["request"],
        _wrapped_native_result(wrapped_page))
    _retained_native_result(
        staged_run, agent, "plain-1", plain_page["request"], plain_page["response"])
    _retained_native_result(
        staged_run, agent, "plain-final", final["request"], final["response"])
    assert len(_sparql_read_records(carrier)) == 3
    assert wrapped_record["successful"] is True
    artifact = staged_run.run_root / wrapped_record["artifact_path"]
    assert artifact.stat().st_mode & 0o777 == 0o440
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == wrapped_record["response_digest"]

    endpoint = staged_run.endpoint
    listing = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert set(names) == set(STAGED_UNIFIED_PROTOCOL_OPERATIONS)
    assert staged_run.runtime._role_capability_operations(
        "protocol", run=staged_run.runtime._active_run
    ) == tuple(names)

    catalog = call(endpoint, "protocol_list_platform_artifacts", {"protocol_id": "protocol"})
    by_request = {
        json.dumps(a["request_arguments"], sort_keys=True): a["artifact_path"]
        for a in catalog["artifacts"] if a["tool"] == "semantic_sparql_query"
    }
    wrapped_ref = by_request[json.dumps(wrapped_page["request"], sort_keys=True)]
    plain_ref = by_request[json.dumps(plain_page["request"], sort_keys=True)]
    final_ref = by_request[json.dumps(final["request"], sort_keys=True)]
    assert wrapped_ref == wrapped_record["artifact_path"]
    scan = call(endpoint, "protocol_inspect_associations", {
        "protocol_id": "protocol", "project_id": "project-1",
        "ontology_ids": ["ontology-1"], "read_refs": [wrapped_ref, plain_ref],
        "final_read_ref": final_ref, "semantic_base_iri": EX,
    })
    # The wrapped page and the plain page resolve to the same payload: the
    # mixed-shape scan is identical to an all-plain scan.
    assert scan["status"] == "COMPLETE", scan
    assert scan["issues"] == []
    assert {c["resource_iri"] for c in scan["candidates"]} == {EX + "orphan", EX + "linked"}
    # The wrapped page's rows are actually consumed: the subject sorted first
    # lives on the wrapped page and its locator binds to that artifact.
    linked = next(c for c in scan["candidates"] if c["resource_iri"] == EX + "linked")
    locator = linked["read_locators"][0]
    assert locator["page"] == 0
    assert locator["artifact_path"] == wrapped_ref
    assert locator["response_digest"] == wrapped_record["response_digest"]
    orphan = next(c for c in scan["candidates"] if c["resource_iri"] == EX + "orphan")
    assert orphan["read_locators"][0]["page"] == 1
    # Scanning never rewrites the retained bytes.
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == wrapped_record["response_digest"]
    assert artifact.stat().st_mode & 0o777 == 0o440

    # Failure shapes stay failures: an outer isError wrapper (with a success
    # payload behind structuredContent AND with a success payload nested in
    # the text item), an inner isError wrapper, inner ok=false, malformed
    # JSON text, a non-MCP text payload, an arbitrary object and a malformed
    # non-list inner content type each keep the scan PARTIAL with
    # governed_read_failed and zero statements.  (Shapes beyond these eight
    # cases are not exercised here and are not claimed as covered.)
    failure_results = [
        {"isError": True, "structuredContent": wrapped_page["response"]},
        {"isError": True, "content": [
            {"type": "text", "text": json.dumps(wrapped_page["response"], sort_keys=True)}]},
        _wrapped_native_result(wrapped_page, inner_error=True),
        _wrapped_native_result(wrapped_page, ok_payload=False),
        _wrapped_native_result(wrapped_page, raw_text="{definitely not json"),
        _wrapped_native_result(wrapped_page, raw_text=json.dumps("a bare string")),
        {"foo": {"bar": 1}},
        {"structuredContent": None, "content": [{"type": "text", "text": json.dumps(
            {"isError": False, "structuredContent": None, "content": 5}, sort_keys=True)}]},
    ]
    for index, failure_result in enumerate(failure_results):
        # OFFSET 0 with a per-variant result_limit keeps the request shape
        # valid (so only the response can fail) while every variant stays a
        # distinct observation identity.
        variant = read(Store(), offset=0, limit=2 + index)
        record = _retained_native_result(
            staged_run, agent, f"failure-{index}", variant["request"], failure_result)
        failed_artifact = staged_run.run_root / record["artifact_path"]
        assert hashlib.sha256(failed_artifact.read_bytes()).hexdigest() == record["response_digest"]
        scan = call(endpoint, "protocol_inspect_associations", {
            "protocol_id": "protocol", "project_id": "project-1",
            "ontology_ids": ["ontology-1"], "read_refs": [record["artifact_path"]],
            "final_read_ref": final_ref, "semantic_base_iri": EX,
        })
        assert scan["status"] == "PARTIAL", scan
        assert any(issue["code"] == "governed_read_failed" for issue in scan["issues"])
        assert scan["statement_count"] == 0
        assert hashlib.sha256(failed_artifact.read_bytes()).hexdigest() == record["response_digest"]

    # Unobserved references keep their existing rejection.
    with pytest.raises(AcceptanceContractError) as error:
        carrier.protocol_inspect_associations({
            "project_id": "project-1", "ontology_ids": ["ontology-1"],
            "read_refs": ["evidence/platform-responses/unobserved-0-0.json"],
            "final_read_ref": final_ref, "semantic_base_iri": EX,
        })
    assert error.value.data["reason_code"] == "association_read_ref_invalid"

    # A tampered retained file keeps its digest rejection.
    tampered = staged_run.run_root / wrapped_record["artifact_path"]
    tampered.chmod(0o640)
    tampered.write_text("{}")
    with pytest.raises(AcceptanceContractError) as error:
        carrier.protocol_inspect_associations({
            "project_id": "project-1", "ontology_ids": ["ontology-1"],
            "read_refs": [wrapped_ref, plain_ref],
            "final_read_ref": final_ref, "semantic_base_iri": EX,
        })
    assert error.value.data["reason_code"] == "association_read_ref_invalid"
    assert "changed" in str(error.value.args[0])
