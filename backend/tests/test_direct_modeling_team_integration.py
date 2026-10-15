"""Native Modeling capability through compiler, executor and real Batch services.

Synthetic isolated resources, no provider or production modeling start. SQLite
persists the real application models; RDF reads/writes use an actual rdflib Dataset.
"""
from types import SimpleNamespace
import json

import pytest
from rdflib import Dataset, URIRef
from rdflib.util import from_n3
from fastapi.encoders import jsonable_encoder

from app.api.schemas import (
    BuildSessionCreate, BuildSessionComplete, OntologyLeaseAcquire, OntologyLeaseRelease,
    ModelingBatchSubmit,
)
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import GraphWriteResult, SparqlResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_context_query import SemanticContextQueryService
from app.services.semantic_query_scope import SemanticQueryScopeResolver
from app.services.semantic_read_scope import SemanticReadScopeResolver
from app.services.scoped_sparql_query import ScopedSparqlQueryService
from app.security.auth import AuthPrincipal
from modeling_team.modeling_readonly import ModelingReadProxy
from modeling_team.staged_decisions import read_submission_intents
from modeling_team.tests.test_r30008b_runner_wiring import _socket_request, _write_json
from modeling_team.tests.test_r30009_runner_wiring import _UnifiedRunner, _open_platform_gate_unified


class DatasetStore:
    def __init__(self):
        self.dataset = Dataset()
        self.writes = []

    def graph_exists(self, graph):
        return bool(len(self.dataset.graph(URIRef(graph))))

    def get_graph(self, graph, _format):
        return self.dataset.graph(URIRef(graph)).serialize(format="nt")

    def query_sparql(self, query, **kwargs):
        import json
        return SparqlResult(result=json.loads(self.dataset.query(query).serialize(format="json")))

    def query_read_model(self, **kwargs):
        return self.query_sparql(kwargs["query"])

    def apply_dataset_delta(self, delta):
        self.writes.append(delta)
        for triples, remove in ((delta.deletes, True), (delta.inserts, False)):
            for subject, predicate, obj, graph in triples:
                triple = tuple(None if remove and value.startswith("?") else from_n3(value)
                               for value in (subject, predicate, obj))
                target = self.dataset.graph(URIRef(graph))
                target.remove(triple) if remove else target.add(triple)
        return GraphWriteResult(graph_iri=delta.affected_graph_iris()[0], applied=True,
                                inserted_quad_count=len(delta.inserts), deleted_quad_count=len(delta.deletes))


@pytest.fixture
def direct_run(in_memory_session, tmp_path):
    settings = Settings(semantic_base_iri="https://direct.test/resource/",
                        semantic_graph_iri_prefix="https://direct.test/graph/",
                        semantic_product_write_mode="rdf_primary")
    db = in_memory_session
    db.add(ProjectModel(id="direct-p", name="Direct", normalized_label="direct"))
    ontology = OntologyModel(id="direct-o", project_id="direct-p", name="Direct ontology")
    db.add(ontology)
    db.flush()
    OntologyWorkspaceService(db, settings).ensure(ontology)
    db.commit()
    store = DatasetStore()
    service = ModelingBatchService(db, settings, store)
    build = BuildSessionService(db, settings)

    def lifecycle(method, path, body, _key):
        if path == "/api/projects/direct-p/build-sessions":
            result, _ = build.create_session("direct-p", BuildSessionCreate(**body))
            return 201, result
        sid = path.split("/")[3].split(":")[0]
        oid = path.split("/ontology-leases/")[1].split(":")[0] if "/ontology-leases/" in path else "direct-o"
        if path.endswith(":acquire"):
            return 200, build.acquire_ontology_lease(sid, oid, OntologyLeaseAcquire(**body))
        if path.endswith(":release"):
            return 200, build.release_ontology_lease(sid, oid, OntologyLeaseRelease(**body))
        if path.endswith(":complete"):
            return 200, build.complete_session(sid, BuildSessionComplete(**body))
        if path.endswith("/modeling-batches"):
            return 200, service.list_session_batches(sid)
        if method == "GET":
            return 200, build.get_session_detail(sid)
        raise AssertionError((method, path, body))

    staged = _UnifiedRunner(tmp_path)
    staged.prepare()
    _open_platform_gate_unified(staged)
    runner = staged.runner
    runner.scope = SimpleNamespace(project_id="direct-p", ontology_id="direct-o", ontology_ids=["direct-o"],
                                   protocol_key="synthetic-key", owned_session_ids=set(), request=lifecycle)
    runner.run.protocol_context = {"semantic_base_iri": settings.semantic_base_iri}
    calls = []

    def submit(batch):
        calls.append(batch)
        return jsonable_encoder(service.submit(batch["session_id"], ModelingBatchSubmit(**{k: v for k, v in batch.items() if k != "session_id"})))

    def read(tool, arguments):
        if tool == "get_ontology_read_model":
            from app.api.modeling_batches import get_ontology_read_model
            return {"ok": True, "data": jsonable_encoder(get_ontology_read_model(
                **arguments, limit=500, principal=AuthPrincipal(
                    subject_type="api_key", subject_id="reader", actor="reader",
                    scopes=frozenset({"read"}), project_id="direct-p", auth_method="bearer"),
                session=db, rdf_store=store, settings=settings,
            ))}
        if tool == "get_modeling_context":
            return {"ok": True, "data": jsonable_encoder(service.get_modeling_context(arguments["ontology_id"]))}
        if tool == "get_modeling_batch":
            return {"ok": True, "data": jsonable_encoder(service.get_batch(arguments["batch_id"]))}
        if tool == "list_session_modeling_batches":
            return {"ok": True, "data": jsonable_encoder(service.list_session_batches(
                arguments["session_id"], cursor=arguments.get("cursor"), limit=arguments.get("limit", 50),
            ))}
        if tool == "semantic_sparql_query":
            query = ScopedSparqlQueryService(SemanticQueryScopeResolver(db, settings), store, settings)
            return {"ok": True, "data": jsonable_encoder(query.query(**arguments))}
        if tool == "get_entity_statement_context":
            from modeling_team.r23003_contract import get_entity_statement_context
            scope = SemanticReadScopeResolver(db).resolve(arguments["ontology_id"])
            assert scope.model_revision == arguments["model_revision"]
            rows = []
            for graph in scope.model_graph_iris:
                for subject, predicate, obj in store.dataset.graph(URIRef(graph)):
                    if str(subject) == arguments["entity_iri"] or (isinstance(obj, URIRef) and str(obj) == arguments["entity_iri"]):
                        rows.append({"subject": str(subject), "predicate": str(predicate), "object": str(obj),
                                     "object_kind": "uri" if isinstance(obj, URIRef) else "literal", "graph": graph})
            page = get_entity_statement_context(rows, project_id="direct-p", **arguments)
            page["cursor"] = arguments.get("cursor")
            return {"ok": True, "data": page}
        if tool == "query_semantic_context":
            query = SemanticContextQueryService(db, store, SemanticQueryScopeResolver(db, settings))
            arguments = dict(arguments)
            question = arguments.pop("query")
            return {"ok": True, "data": jsonable_encoder(query.query_multi(
                **arguments, queries=[question], principal=AuthPrincipal(subject_type="api_key", subject_id="reader",
                    actor="reader", scopes=frozenset({"read"}), project_id="direct-p", auth_method="bearer"),
            ))}
        raise AssertionError(tool)

    runner.staged_batch_forwarder = submit
    runner.staged_plan_read_forwarder = read
    endpoint = runner.acceptance.capability_endpoint("modeling")
    endpoint.start()
    try:
        yield SimpleNamespace(staged=staged, runner=runner, endpoint=endpoint, calls=calls, store=store,
                              service=service, settings=settings, read=read, tmp_path=tmp_path, db=db)
    finally:
        endpoint.stop()
        runner.scope = None
        staged.cleanup()


def call(run, request):
    response = _socket_request(run.endpoint.socket_path, run.endpoint.token, "tools/call",
                              name="modeling_submit_model_changes",
                              arguments={"modeling_id": "modeling", "request": request})
    assert "result" in response, response
    envelope = response["result"]["structuredContent"]
    return envelope["data"] if envelope.get("ok") is True else envelope


def request_for(run, *, label="Work order", revision=1):
    ref = f"stage3-neutral-graph/candidates/direct-r{revision}.json"
    candidate = {
        "schema_version": "r3-0-009-unified-graph/v2", "scenario_id": "direct",
        "candidate_id": "direct", "revision": revision, "explicit_unknowns": [],
        "items": [{"item_id": "work-order", "item_kind": "entity", "business_meaning": "A service work order",
                   "value": {"label": label}, "relation_endpoints": None, "slice_ids": ["slice-1"],
                   "shared_scope": None, "unknowns": ["Customer severity policy is unknown"]}],
    }
    _write_json(run.staged.run_root / ref, candidate)
    return {"schema_version": "r4-3-025-model-changes/v1", "candidate_ref": ref,
            "changes": [{"change_id": "create-work-order", "action": "create", "resource_kind": "entity",
                         "item_id": "work-order", "target_ref": None, "fields": None}]}


def test_native_modeling_direct_apply_trusts_receipt_and_does_not_replay(direct_run):
    run = direct_run
    request = request_for(run)
    result = call(run, request)
    assert result["status"] == "completed", json.dumps(result, ensure_ascii=False, default=str)
    assert len(run.calls) == 1
    assert run.calls[0]["mode"] == "apply_atomic"
    assert run.calls[0]["items"][0]["client_item_id"] == "work-order"
    assert run.calls[0]["items"][0]["payload"]["semantic_definition"]["unknowns"] == ["Customer severity policy is unknown"]
    assert result["batches"][0]["model_revision_after"] > result["batches"][0]["model_revision_before"]
    iri = result["batches"][0]["resource_bindings"][0]["resource_iri"]
    assert any(subject == URIRef(iri) and "Customer severity policy is unknown" in str(obj)
               for subject, _, obj, _ in run.store.dataset.quads((None, None, None, None)))
    proxy = ModelingReadProxy(socket_path=run.tmp_path / "reads.sock", token="token", read_key="reader",
                              project_id="direct-p", ontology_id="direct-o",
                              forward=lambda tool, args, key: run.read(tool, args))
    responses = []
    for question in ("Work order", iri):
        response = proxy.handle({"token": "token", "operation": "tools/call",
                                "tool": "query_semantic_context", "arguments": {
            "project_id": "direct-p", "scope_mode": "ontologies", "ontology_ids": ["direct-o"],
            "query": question, "context_detail": "full",
        }})
        assert response["ok"] is True, response
        responses.append(response["result"]["data"])
    assert responses[1]["primary_matches"][0]["iri"] == iri
    assert responses[1]["scope"]["ontologies"][0]["model_revision"] == result["batches"][0]["model_revision_after"]
    repeated = call(run, request)
    assert repeated["status"] == "completed", repeated
    assert len(run.calls) == 1
    assert [intent["mode"] for intent in read_submission_intents(run.staged.run_root)] == ["apply_atomic"]
    closed = _socket_request(run.endpoint.socket_path, run.endpoint.token, "tools/call",
                             name="modeling_finish_changes", arguments={"modeling_id": "modeling"})
    assert closed["result"]["structuredContent"]["data"]["closed"] is True, closed


def test_missing_semantic_choice_is_repairable_before_any_model_write(direct_run):
    run = direct_run
    invalid = request_for(run, label="")
    rejected = call(run, invalid)
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"] and "/value/label" in rejected["errors"][0]["path"]
    assert run.calls == [] and run.store.writes == []
    corrected = call(run, request_for(run, revision=2))
    assert corrected["status"] == "completed", corrected
    assert len(run.calls) == 1


def test_authorized_two_ontology_dependency_reads_and_final_scan(direct_run):
    run = direct_run
    ontology = OntologyModel(id="direct-o2", project_id="direct-p", name="Second ontology")
    run.db.add(ontology)
    run.db.flush()
    OntologyWorkspaceService(run.db, run.settings).ensure(ontology)
    run.db.commit()
    run.runner.scope.ontology_ids = ["direct-o", "direct-o2"]
    run.runner.scope.ontology_plan_ids = ["direct-o", "direct-o2"]
    _write_json(run.staged.run_root / "scenario-map/topology-decision.json", {
        "ontology_plan": [{"slice_ids": ["slice-1"]}, {"slice_ids": ["slice-2"]}],
    })
    request = request_for(run)
    path = run.staged.run_root / request["candidate_ref"]
    candidate = json.loads(path.read_text())
    second = dict(candidate["items"][0], item_id="fault", slice_ids=["slice-2"],
                  value={"label": "Fault"}, business_meaning="A declared fault", unknowns=[])
    prop = dict(second, item_id="links", item_kind="property", slice_ids=["slice-1"],
                value={"name": "links", "predicate_kind": "relation"})
    relation = dict(second, item_id="order-fault", item_kind="relation", slice_ids=["slice-1"],
                    value={"predicate": {"definition_ref": "links"}},
                    relation_endpoints={"from_item_id": "work-order", "to_item_id": "fault"})
    candidate["items"].extend([second, prop, relation])
    _write_json(path, candidate)
    for item in (second, prop, relation):
        request["changes"].append({"change_id": "create-" + item["item_id"], "action": "create",
                                   "resource_kind": item["item_kind"], "item_id": item["item_id"],
                                   "target_ref": None, "fields": None})
    invalid_join = dict(second, item_id="bad-join", item_kind="join_mapping", value={
        "name": "Invalid direction", "relation_type_iri": {"definition_ref": "links"},
        "join_direction": "sideways", "schema_source": None,
        "join_path": [{"from_table": "a", "to_table": "b", "from_columns": ["b_id"], "to_columns": ["id"]}],
    })
    candidate["items"].append(invalid_join)
    _write_json(path, candidate)
    request["changes"].append({"change_id": "create-bad-join", "action": "create", "resource_kind": "join_mapping",
                               "item_id": "bad-join", "target_ref": None, "fields": None})
    rejected = call(run, request)
    assert rejected["status"] == "not_written", rejected
    assert any(error["path"].endswith("/value/join_direction") for error in rejected["errors"])
    assert run.calls == [] and not run.runner.scope.owned_session_ids
    candidate["items"].pop()
    candidate["revision"] = 2
    request["changes"].pop()
    request["candidate_ref"] = "stage3-neutral-graph/candidates/direct-r2.json"
    _write_json(run.staged.run_root / request["candidate_ref"], candidate)
    result = call(run, request)
    assert result["status"] == "completed", json.dumps(result, ensure_ascii=False, default=str)
    assert {batch["ontology_id"] for batch in result["batches"]} == {"direct-o", "direct-o2"}
    bindings = {entry["item_id"]: entry for batch in result["batches"] for entry in batch["resource_bindings"]}
    proxy = ModelingReadProxy(socket_path=run.tmp_path / "two-reads.sock", token="token", read_key="reader",
                              project_id="direct-p", ontology_id="direct-o",
                              ontology_ids=["direct-o", "direct-o2"],
                              forward=lambda tool, args, key: run.read(tool, args))
    response = proxy.handle({"token": "token", "operation": "tools/call", "tool": "query_semantic_context",
                             "arguments": {"project_id": "direct-p", "scope_mode": "ontologies",
                                           "ontology_ids": ["direct-o", "direct-o2"],
                                           "query": bindings["work-order"]["resource_iri"],
                                           "context_detail": "full"}})
    assert response["ok"] is True, response
    data = response["result"]["data"]
    assert {entry["ontology_id"] for entry in data["scope"]["ontologies"]} == {"direct-o", "direct-o2"}
    assert bindings["fault"]["resource_iri"] in json.dumps(data)
    scan = _socket_request(run.endpoint.socket_path, run.endpoint.token, "tools/call",
                           name="modeling_inspect_associations", arguments={"modeling_id": "modeling"})
    assert scan["result"]["structuredContent"]["data"]["status"] == "COMPLETE", scan


def test_changed_immutable_candidate_cannot_create_new_execution_identity(direct_run):
    run = direct_run
    request = request_for(run)
    assert call(run, request)["status"] == "completed"
    request_for(run, label="Changed under the same revision")
    rejected = call(run, request)
    assert rejected["status"] == "not_written", rejected
    assert rejected["errors"][0]["code"] == "candidate_revision_changed"
    assert len(run.calls) == 1


def test_delete_collects_tool_owned_impact_and_reuses_success_after_target_is_gone(direct_run):
    run = direct_run
    created = call(run, request_for(run))
    row = created["batches"][0]
    iri = row["resource_bindings"][0]["resource_iri"]
    request = {"schema_version": "r4-3-025-model-changes/v1", "candidate_ref": None,
               "changes": [{"change_id": "delete-order", "action": "delete", "resource_kind": "entity",
                            "item_id": None, "fields": None,
                            "target_ref": {"artifact_ref": row["receipt_ref"], "path": "/structuredContent/data/items/0"}}]}
    deleted = call(run, request)
    assert deleted["status"] == "completed", json.dumps(deleted, ensure_ascii=False, default=str)
    receipt = run.calls[-1]["items"][0]["payload"]["impact_receipt"]
    assert receipt["complete"] is True and receipt["entity_iri"] == iri
    assert receipt["statements"] and receipt["model_revision"] == row["model_revision_after"]
    assert not list(run.store.dataset.quads((URIRef(iri), None, None, None)))
    assert call(run, request)["status"] == "completed"
    assert len(run.calls) == 2


def test_new_property_key_is_bound_in_a_later_atomic_batch_and_keeps_iri_text_literal(direct_run):
    run = direct_run
    request = request_for(run)
    path = run.staged.run_root / request["candidate_ref"]
    candidate = json.loads(path.read_text())
    property_item = dict(candidate["items"][0], item_id="source-url", item_kind="property", unknowns=[],
                         value={"name": "Source URL", "predicate_kind": "fact",
                                "datatype": "http://www.w3.org/2001/XMLSchema#string"})
    literal = "https://business.example/evidence/original"
    candidate["items"][0]["value"]["properties"] = [
        {"property_ref": {"definition_ref": "source-url"}, "value": literal},
    ]
    candidate["items"].append(property_item)
    _write_json(path, candidate)
    request["changes"].append({"change_id": "create-source-url", "action": "create", "resource_kind": "property",
                               "item_id": "source-url", "target_ref": None, "fields": None})
    result = call(run, request)
    assert result["status"] == "completed", json.dumps(result, ensure_ascii=False, default=str)
    assert len(run.calls) == 2
    assert run.calls[0]["items"][0]["client_item_id"] == "source-url"
    bindings = {entry["item_id"]: entry for batch in result["batches"] for entry in batch["resource_bindings"]}
    property_iri = bindings["source-url"]["resource_iri"]
    entity_iri = bindings["work-order"]["resource_iri"]
    assert run.calls[1]["items"][0]["payload"]["properties"] == {property_iri: literal}
    objects = [obj for _, _, obj, _ in run.store.dataset.quads((URIRef(entity_iri), URIRef(property_iri), None, None))]
    assert len(objects) == 1 and str(objects[0]) == literal and not isinstance(objects[0], URIRef)
    assert call(run, request)["status"] == "completed" and len(run.calls) == 2
    observed = run.runner._direct_platform_read("get_ontology_read_model", {
        "ontology_id": "direct-o", "model_name": "facts", "entity_iri": entity_iri, "field_set": "full",
    })
    facts = observed["data"]["items"]
    position = next(index for index, fact in enumerate(facts) if fact["predicate"] == property_iri)
    fact_request = {"schema_version": "r4-3-025-model-changes/v1", "candidate_ref": None,
                    "changes": [{"change_id": "correct-source", "action": "set_fact", "resource_kind": "fact",
                                 "item_id": None, "fields": {"new_object_value": "Corrected source", "new_object_is_iri": False},
                                 "target_ref": {"artifact_ref": observed["platform_ref"]["artifact_path"],
                                                "path": f"/structuredContent/data/items/{position}"}}]}
    corrected = call(run, fact_request)
    assert corrected["status"] == "completed", corrected
    assert call(run, fact_request)["status"] == "completed" and len(run.calls) == 3
    objects = [str(obj) for _, _, obj, _ in run.store.dataset.quads((URIRef(entity_iri), URIRef(property_iri), None, None))]
    assert objects == ["Corrected source"]
    observed = run.runner._direct_platform_read("get_ontology_read_model", {
        "ontology_id": "direct-o", "model_name": "facts", "entity_iri": entity_iri, "field_set": "full",
    })
    position = next(index for index, fact in enumerate(observed["data"]["items"])
                    if fact["predicate"] == property_iri)
    deletion = {"schema_version": "r4-3-025-model-changes/v1", "candidate_ref": None,
                "changes": [{"change_id": "remove-source", "action": "delete_fact", "resource_kind": "fact",
                             "item_id": None, "fields": None,
                             "target_ref": {"artifact_ref": observed["platform_ref"]["artifact_path"],
                                            "path": f"/structuredContent/data/items/{position}"}}]}
    removed = call(run, deletion)
    assert removed["status"] == "completed", removed
    assert call(run, deletion)["status"] == "completed" and len(run.calls) == 4
    assert not list(run.store.dataset.quads((URIRef(entity_iri), URIRef(property_iri), None, None)))


def test_lost_reply_after_real_apply_reconciles_original_backend_attempt(direct_run):
    from modeling_team.staged_batch_write_forwarder import StagedBatchForwardUnknown

    run = direct_run
    forward = run.runner.staged_batch_forwarder

    def lose_reply(batch):
        forward(batch)
        raise StagedBatchForwardUnknown("Injected response loss after the actual atomic apply")

    run.runner.staged_batch_forwarder = lose_reply
    request = request_for(run)
    result = call(run, request)
    assert result["status"] == "completed", result
    assert len(run.calls) == 1
    row = result["batches"][0]
    assert row["batch_id"] and row["attempt_id"] and row["resource_bindings"]
    actual = run.service.get_batch(row["batch_id"])
    assert len(actual["attempts"]) == 1
    assert actual["attempts"][0]["attempt_id"] == row["attempt_id"]
    assert call(run, request)["status"] == "completed" and len(run.calls) == 1
