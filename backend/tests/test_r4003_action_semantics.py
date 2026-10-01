"""Developer contracts for reusable actions, parameters and ordinary links."""

import json
from copy import deepcopy

import pytest
from rdflib import URIRef
from rdflib.namespace import RDFS
from rdflib.util import from_n3

from app.core.config import Settings
from app.services.operation_semantics import decode_operations
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
from modeling_team.protocol_mechanics import build_candidate_receipt, translate_candidate_to_batches
from test_r4002_multiview_semantics import _item, _materialize
from test_r3009_unified_semantic_graph import (
    DATA_GRAPH, NS, ONTOLOGY_GRAPH, ONTOLOGY_ID, _client, _read_model, _seed_graph_set,
)


def candidate():
    def entity(key, role, meaning, scope="工单处理", **fields):
        return _item(key, "entity", {
            "entity_id": key, "values": {"label": key},
            "semantic_definition": {
                "semantic_role": role, "business_meaning": meaning, "applicability": scope,
            }, **fields,
        })

    items = [
        _item("ticket", "class", {"class_id": "ticket", "label": "工单"}),
        _item("repair", "class", {"class_id": "repair", "superclass": "ticket"}),
        entity("unclassified", "object", "无需正式分类的业务对象"),
        entity("flow-a", "process", "流程一"), entity("flow-b", "process", "流程二"),
        entity("close", "behavior", "人工关闭工单", action_definition={
            "input_status": "defined", "output_status": "none",
        }),
        entity("merge", "behavior", "合并工单", action_definition={
            "input_status": "defined", "output_status": "defined",
        }),
        entity("no-input", "behavior", "定期核对", action_definition={"input_status": "none"}),
        entity("missing-output", "behavior", "结果说明尚未提供"),
        entity("unknown-output", "behavior", "返回值待确认", action_definition={
            "output_status": "unknown",
        }),
        entity("keep", "parameter", "保留工单", parameter_definition={
            "direction": "input", "value_kind": "object_reference", "required": True,
            "cardinality": "single",
        }),
        entity("others", "parameter", "待合并工单集合", parameter_definition={
            "direction": "input", "value_kind": "object_reference", "required": True,
            "cardinality": "collection",
        }),
        entity("merged", "parameter", "保留工单的更新结果", parameter_definition={
            "direction": "output", "value_kind": "object_reference", "cardinality": "single",
            "occurrence_condition": "合并成功时", "result_kind": "updated_input",
        }),
        entity("duration", "parameter", "计算后的耗时", parameter_definition={
            "direction": "output", "value_kind": "value", "value_type": "number",
            "cardinality": "single", "unit": "小时", "enum_values": [0, 1, 2],
            "missing_meaning": "无已确认耗时", "required": None,
            "result_kind": "computed_value", "occurrence_condition": None,
        }),
        entity("unconfirmed-result", "parameter", "输出含义未知", parameter_definition={
            "direction": "output", "value_kind": "unknown", "value_type": None,
            "cardinality": "unknown", "result_kind": "unknown",
        }),
        entity("accepted", "precondition", "需已验收", "所有普通关闭工单"),
        entity("report", "precondition", "维修报告已提交，且仍需共同验收", "仅维修工单"),
        entity("exception", "precondition", "免验收必须独立确认共同条件范围", "仅批准的免验收场景"),
        entity("closed-effect", "effect", "工单状态预期变为已关闭", "关闭成功时"),
        entity("failure", "effect", "被拒绝时工单保持原状态", "拒绝关闭时"),
        entity("role", "business_role", "审核员"),
        entity("duty", "responsibility", "负责检查验收", "仅关闭前审核"),
        entity("rule", "rule", "共享验收规则"),
        entity("cap-a", "capability_association", "提供自动关闭能力；与人工动作对应待确认", "系统A"),
        entity("cap-b", "capability_association", "仅提交报告，需组合；顺序未确认", "维修工单"),
    ]
    items[17]["semantic"]["semantic_definition"]["conflicting_meanings"] = [
        "多分类下验收要求与免验收范围尚冲突",
    ]
    items.append(_item("state", "predicate", {
        "predicate": "state", "predicate_kind": "fact", "range": "string",
    }))
    for name in (
        "uses", "appliesTo", "parameter", "objectDefinition", "resultOf", "condition", "effect",
        "references", "scope", "duty", "role", "capability", "operation",
    ):
        items.append(_item("p-" + name, "predicate", {
            "predicate": name, "predicate_kind": "relation",
        }))
    for name in ("op-a", "op-b"):
        items.append(_item(name, "operation", {
            "operation_id": name, "name": "外部关闭能力", "target_class": "ticket",
            "idempotency": {"kind": "unknown"}, "risk_level": "medium",
            "tool_bindings": [{"binding_id": name, "kind": "http_api", "system": name,
                               "operation_identifier": "close"}],
            "preconditions": [{"name": "external", "description": "接口条件独立声明"}],
        }))
    links = [
        ("flow-a", "uses", "close"), ("flow-b", "uses", "close"),
        ("close", "appliesTo", "ticket"), ("merge", "appliesTo", "unclassified"),
        ("close", "condition", "accepted"), ("close", "condition", "report"),
        ("report", "scope", "repair"), ("close", "condition", "exception"),
        ("merge", "parameter", "keep"), ("merge", "parameter", "others"),
        ("merge", "parameter", "merged"), ("keep", "objectDefinition", "ticket"),
        ("others", "objectDefinition", "ticket"), ("merged", "resultOf", "keep"),
        ("accepted", "references", "rule"), ("accepted", "references", "keep"),
        ("accepted", "references", "state"), ("close", "effect", "closed-effect"),
        ("close", "effect", "failure"), ("close", "duty", "duty"),
        ("duty", "role", "role"), ("close", "capability", "cap-a"),
        ("close", "capability", "cap-b"), ("merge", "capability", "cap-a"),
        ("cap-a", "operation", "op-a"), ("cap-b", "operation", "op-b"),
    ]
    items.extend(_item("r-" + str(i), "relation", {
        "subject": {"definition_ref": s}, "predicate": p, "object": {"definition_ref": o},
    }) for i, (s, p, o) in enumerate(links))
    return {"candidate_kind": "platform-neutral-candidate-v3", "candidate_revision": "r4003-v1",
            "scope": "approved-project", "constraints": [], "items": items}


def test_candidate_rdf_and_governed_resource_roundtrip(in_memory_session):
    value = candidate()
    assert build_candidate_receipt(value)["status"] == "accepted"
    plan, store = _materialize(value)
    assert plan == translate_candidate_to_batches(value)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    rows = {r["iri"].removeprefix(NS + "entity/"): r
            for r in _read_model(client, "entity-list")["items"]}
    for key, expected in (
        ("close", {"input_status": "defined", "output_status": "none"}),
        ("unknown-output", {"output_status": "unknown"}),
    ):
        assert rows[key]["class_iris"] == []
        assert rows[key]["detail_fields"]["action_definition"] == expected
        response = client.get(f"/api/semantic/resources/{NS}entity/{key}",
                              params={"graph_set_id": "gs-009"})
        assert response.status_code == 200
        assert response.json()["properties"]["action_definition"] == expected
    assert "action_definition" not in rows["missing-output"]["detail_fields"]
    assert rows["keep"]["iri"] != rows["others"]["iri"]
    assert rows["merged"]["detail_fields"]["parameter_definition"]["result_kind"] == "updated_input"
    duration = client.get(f"/api/semantic/resources/{NS}entity/duration",
                          params={"graph_set_id": "gs-009"}).json()["properties"]
    assert duration["parameter_definition"]["unit"] == "小时"
    assert duration["parameter_definition"]["required"] is None
    assert duration["parameter_definition"]["enum_values"] == [0, 1, 2]
    assert rows["unconfirmed-result"]["detail_fields"]["parameter_definition"]["value_type"] is None
    assert rows["exception"]["detail_fields"]["semantic_definition"]["conflicting_meanings"]
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    assert len(list(graph.subjects(URIRef(NS + "property/uses"), URIRef(NS + "entity/close")))) == 2
    assert set(map(str, graph.objects(URIRef(NS + "entity/close"), URIRef(NS + "property/condition")))) == {
        NS + "entity/accepted", NS + "entity/report", NS + "entity/exception",
    }
    assert not list(graph.triples((None, URIRef(NS + "property/state"), None)))
    assert (URIRef(NS + "class/repair"), RDFS.subClassOf, URIRef(NS + "class/ticket")) in (
        store.dataset.graph(URIRef(ONTOLOGY_GRAPH))
    )
    operations = decode_operations(store.dataset.graph(URIRef(ONTOLOGY_GRAPH)), Settings())
    assert len(operations) == 2
    assert operations[0]["preconditions"] == [{"name": "external", "description": "接口条件独立声明"}]
    statements = client.get("/api/semantic/statements", params={"graph_set_id": "gs-009"}).json()
    assert any(r.get("object") == NS + "operation/op-a" for r in statements["items"])


def test_patch_and_clear_preserve_independent_action_meaning():
    for field, term in (("action_definition", "actionDefinition"),
                        ("parameter_definition", "parameterDefinition")):
        command = compile_command("update_entity", {
            "ontology_id": ONTOLOGY_ID, "entity_iri": NS + "entity/x", field: None,
        }, Settings())
        assert command.delta.deletes == [(f"<{NS}entity/x>", f"<{NS}vocab/{term}>", "?o", DATA_GRAPH)]
        assert command.delta.inserts == []
    command = compile_command("update_entity", {
        "ontology_id": ONTOLOGY_ID, "entity_id": "x", "action_definition": {"output_status": "unknown"},
    }, Settings())
    assert json.loads(str(from_n3(command.delta.inserts[0][2]))) == {"output_status": "unknown"}
    for kind in ("create_relation", "delete_relation"):
        delta = compile_command(kind, {"ontology_id": ONTOLOGY_ID,
            "source_entity_iri": NS + "entity/cap-a", "relation_type_iri": NS + "property/operation",
            "target_entity_iri": NS + "operation/op-b"}, Settings()).delta
        assert all("Definition>" not in p for _, p, _, _ in (*delta.inserts, *delta.deletes))


def test_canonical_create_annotations_follow_the_compiled_entity_identity():
    # Canonical create_entity accepts a dictionary and owns the created IRI;
    # an irrelevant caller field must not redirect only the annotation.
    command = compile_command("create_entity", {
        "ontology_id": ONTOLOGY_ID, "entity_id": "created", "entity_iri": NS + "entity/other",
        "label": "Created definition", "action_definition": {"output_status": "none"},
        "parameter_definition": {"direction": "unknown"},
        "semantic_definition": {"semantic_role": "behavior", "business_meaning": "Created meaning"},
    }, Settings())
    assert {s for s, _, _, _ in command.delta.inserts} == {f"<{NS}entity/created>"}


@pytest.mark.parametrize("field,value", [
    ("action_definition", {}), ("action_definition", {"output_status": "absent"}),
    ("action_definition", {"operation_iri": "hidden"}),
    ("parameter_definition", {"direction": "inout"}),
    ("parameter_definition", {"required": 1}),
    ("parameter_definition", {"enum_values": [{"iri": "hidden"}]}),
    ("parameter_definition", {"cardinality": []}),
    ("parameter_definition", {"unit": ""}),
])
def test_annotation_errors_are_local_and_repairable(field, value):
    payload = {"ontology_id": ONTOLOGY_ID, "entity_id": "x", "label": "x", field: value}
    with pytest.raises(InvalidCommandPayload, match=field):
        compile_command("create_entity", payload, Settings())
    payload[field] = {"output_status": "unknown"} if field == "action_definition" else {"direction": "unknown"}
    assert compile_command("create_entity", payload, Settings()).delta.inserts


def test_operation_keeps_original_contract_and_bad_reference_is_repairable():
    value = candidate()
    operation = next(i for i in value["items"] if i["item_id"] == "op-a")
    operation["semantic"]["tool_bindings"] = []
    plan = translate_candidate_to_batches(value)
    payload = next(i["payload"] for b in plan["batches"] for i in b["items"]
                   if i["client_item_id"] == "op-a")
    with pytest.raises(InvalidCommandPayload, match="tool binding"):
        compile_command("create_operation", {"ontology_id": ONTOLOGY_ID, **payload}, Settings())
    bad = deepcopy(candidate())
    bad["items"][-1]["semantic"]["object"] = {"definition_ref": "nonexistent-operation"}
    assert translate_candidate_to_batches(bad)["conflicts"][0]["code"] == "unbound_definition_reference"
    assert not translate_candidate_to_batches(candidate())["conflicts"]


def test_hidden_parameter_rule_and_operation_do_not_leak(in_memory_session, monkeypatch):
    from app.api import semantic

    _, store = _materialize(candidate())
    _seed_graph_set(in_memory_session)
    hidden = {NS + "entity/keep", NS + "entity/rule", NS + "operation/op-a"}
    view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(hidden))
    monkeypatch.setattr(semantic, "_access_view", lambda *_args, **_kwargs: view)
    client = _client(store, in_memory_session)
    for iri in hidden:
        response = client.get(f"/api/semantic/resources/{iri}", params={"graph_set_id": "gs-009"})
        assert response.status_code == 404
        assert response.json() == {"detail": f"Resource not found: {iri}"}
    before = _read_model(client, "entity-list")
    page = _read_model(client, "entity-list", limit=1)
    assert page["items"] == before["items"][:1]
    assert page["paging"]["visible_count"] == len(before["items"])
    for path in ("/api/semantic/statements", "/api/semantic/graph-sets/gs-009/read-models/entity-relations"):
        response = client.get(path, params={"graph_set_id": "gs-009"})
        assert response.status_code == 200
        assert all(iri not in response.text for iri in hidden)
