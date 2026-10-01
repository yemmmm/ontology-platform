"""Developer checks of ordinary process definitions; no business workflow execution."""

import json
from copy import deepcopy
from pathlib import Path

from rdflib import URIRef

from app.core.config import Settings
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_command_compiler import compile_command
from modeling_team.protocol_mechanics import translate_candidate_to_batches
from test_r4002_multiview_semantics import _item, _materialize
from test_r3009_unified_semantic_graph import (
    DATA_GRAPH, NS, ONTOLOGY_ID, _client, _read_model, _seed_graph_set,
)

ROOT = Path(__file__).resolve().parents[2]


def candidate():
    value = json.loads((ROOT / "modeling_team/references/platform-neutral-candidate-authoring.json")
                       .read_text())["process_binding_example_candidate"]
    items = value["items"]

    def entity(key, role, meaning, values=None, **declaration):
        items.append(_item(key, "entity", {
            "entity_id": key, "values": {"label": key, **(values or {})},
            "semantic_definition": {"semantic_role": role, "business_meaning": meaning,
                                    "applicability": "本流程定义；不是运行实例", **declaration},
        }))

    relations = {
        "baseValue", "viaProperty", "inScope", "iteratesOver", "currentItemOf", "bodyEntry",
        "exitStep", "continuesWhen", "initialValue", "iterationResult", "collectsValue",
        "selectedBy", "hasProcessOutput", "atProcess",
    }
    for name in sorted(relations):
        items.append(_item("p-" + name, "predicate", {
            "predicate": name, "predicate_kind": "relation",
        }))
    for name, datatype in (("ticketNumber", "string"), ("literalValue", "integer"),
                           ("loopKind", "string"), ("conditionTiming", "string")):
        items.append(_item("p-" + name, "predicate", {
            "predicate": name, "predicate_kind": "fact", "range": datatype,
        }))
    entity("v-number", "value_reference", "从原工单正向取单值编号，不是编号实参",
           {"sourceKind": "object_property"})
    entity("v-constant", "value_reference", "已确认的语义常量：归档等级一",
           {"sourceKind": "constant", "literalValue": 1})
    entity("v-items", "value_reference", "流程输入的工单集合", {"sourceKind": "process_input"})
    entity("outer", "iteration_scope", "逐项处理集合；空集合不进入体",
           {"loopKind": "collection"})
    entity("inner", "iteration_scope", "内层逐项处理；集合来源未确认",
           {"loopKind": "collection"}, unknowns=["内层集合来源尚未确认"])
    entity("v-outer-item", "value_reference", "外层当前工单位置", {"sourceKind": "iteration_item"})
    entity("v-inner-item", "value_reference", "内层当前工单位置", {"sourceKind": "iteration_item"})
    entity("pre", "iteration_scope", "先判断再进入；零次迭代不产生输出",
           {"loopKind": "conditional", "conditionTiming": "pre"})
    entity("post", "iteration_scope", "先执行再判断下一轮",
           {"loopKind": "conditional", "conditionTiming": "post"})
    entity("carried", "value_reference", "首次取流程输入，后续取本轮输出；未改写原输入")
    entity("v-collected", "value_reference", "循环外消费按迭代收集的集合",
           unknowns=["某次失败或缺失时集合是否保留部分结果尚未确认"])
    entity("collect-rule", "rule", "收集已有成功输出；空集合输出为空集合；不默认有序")
    entity("flow-out", "process_parameter", "流程输出的返修集合")
    items[-1]["semantic"]["parameter_definition"] = {
        "direction": "output", "value_kind": "object_reference", "cardinality": "collection",
        "occurrence_condition": "遍历结束；缺失策略待确认",
    }
    entity("bind-out", "parameter_binding", "将收集结果用于流程输出")
    links = [
        ("v-number", "baseValue", "v-original"), ("v-number", "viaProperty", "p-ticketNumber"),
        ("outer", "iteratesOver", "v-items"), ("v-items", "inputOfProcess", "process-a"),
        ("v-items", "forParameter", "original-input"),
        ("v-outer-item", "currentItemOf", "outer"), ("v-inner-item", "currentItemOf", "inner"),
        ("inner", "inScope", "outer"), ("call-create", "inScope", "outer"),
        ("v-repair", "inScope", "outer"), ("outer", "bodyEntry", "call-create"),
        ("outer", "exitStep", "end"), ("carried", "initialValue", "v-original"),
        ("carried", "iterationResult", "v-repair"), ("v-collected", "collectsValue", "v-repair"),
        ("v-collected", "selectedBy", "collect-rule"),
        ("process-a", "hasProcessOutput", "flow-out"), ("bind-out", "atProcess", "process-a"),
        ("bind-out", "toParameter", "flow-out"), ("bind-out", "fromValue", "v-collected"),
    ]
    for scope in ("pre", "post"):
        links.extend([(scope, "continuesWhen", "ready"), (scope, "bodyEntry", "call-create"),
                      (scope, "exitStep", "end")])
    items.extend(_item("extra-r-" + str(i), "relation", {
        "predicate": p, "subject": {"definition_ref": s}, "object": {"definition_ref": o},
    }) for i, (s, p, o) in enumerate(links))
    return value


def _objects(graph, source, predicate):
    return set(map(str, graph.objects(URIRef(NS + "entity/" + source),
                                     URIRef(NS + "property/" + predicate))))


def test_repeated_calls_sources_and_loop_scopes_roundtrip(in_memory_session):
    value = candidate()
    plan, store = _materialize(value)
    assert plan == translate_candidate_to_batches(value)
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    assert _objects(graph, "call-close-original", "invokesAction") == {NS + "entity/close"}
    assert _objects(graph, "call-close-repair", "invokesAction") == {NS + "entity/close"}
    assert _objects(graph, "call-b-close", "invokesAction") == {NS + "entity/close"}
    for binding, source in (("bind-original", "v-original"), ("bind-repair", "v-repair")):
        assert _objects(graph, binding, "toParameter") == {NS + "entity/close-target"}
        assert _objects(graph, binding, "fromValue") == {NS + "entity/" + source}
    assert _objects(graph, "v-repair", "outputOfCall") == {NS + "entity/call-create"}
    assert _objects(graph, "v-repair", "forParameter") == {NS + "entity/repair-output"}
    assert _objects(graph, "v-number", "viaProperty") == {NS + "property/ticketNumber"}
    assert _objects(graph, "v-outer-item", "currentItemOf") == {NS + "entity/outer"}
    assert _objects(graph, "v-inner-item", "currentItemOf") == {NS + "entity/inner"}
    assert _objects(graph, "carried", "initialValue") == {NS + "entity/v-original"}
    assert _objects(graph, "carried", "iterationResult") == {NS + "entity/v-repair"}
    assert _objects(graph, "bind-out", "fromValue") == {NS + "entity/v-collected"}
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    entities = _read_model(client, "entity-list")["items"]
    assert len(entities) == sum(i["item_kind"] == "entity" for i in value["items"])
    assert all(not row["class_iris"] for row in entities)
    for item in value["items"]:
        if item["item_kind"] != "entity":
            continue
        response = client.get(f"/api/semantic/resources/{NS}entity/{item['item_id']}",
                              params={"graph_set_id": "gs-009"})
        assert response.status_code == 200
        assert response.json()["properties"]["semantic_definition"] == (
            item["semantic"]["semantic_definition"]
        )
    statements = client.get("/api/semantic/statements", params={"graph_set_id": "gs-009"}).json()
    assert any(r["predicate"] == NS + "property/literalValue" for r in statements["items"])
    assert any(r.get("object") == NS + "property/ticketNumber" for r in statements["items"])
    for key, timing in (("pre", "pre"), ("post", "post")):
        assert str(next(graph.objects(URIRef(NS + "entity/" + key),
                                      URIRef(NS + "property/conditionTiming")))) == timing


def test_item_order_does_not_define_business_order_and_reference_repair():
    value = candidate()
    _, original = _materialize(value)
    reordered = deepcopy(value)
    reordered["items"].reverse()
    _, after = _materialize(reordered)
    assert set(original.dataset.quads()) == set(after.dataset.quads())
    bad = deepcopy(value)
    bad["items"][-1]["semantic"]["object"] = {"definition_ref": "missing"}
    conflict = translate_candidate_to_batches(bad)["conflicts"][0]
    assert conflict["code"] == "unbound_definition_reference"
    assert conflict["item_id"] == bad["items"][-1]["item_id"]
    assert "semantic.object" in str(conflict)
    assert not translate_candidate_to_batches(value)["conflicts"]


def test_structural_success_does_not_establish_correct_business_binding():
    value = candidate()
    edge = next(i for i in value["items"] if i["item_kind"] == "relation"
                and i["semantic"] == {"subject": {"definition_ref": "bind-repair"},
                    "predicate": "fromValue", "object": {"definition_ref": "v-repair"}})
    edge["semantic"]["object"] = {"definition_ref": "v-original"}
    _, store = _materialize(value)
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    # This ordinary graph is legal but contradicts the intended repair target.
    assert _objects(graph, "bind-repair", "fromValue") != {NS + "entity/v-repair"}


def test_local_binding_revision_preserves_shared_action():
    _, store = _materialize(candidate())
    graph = store.dataset.graph(URIRef(DATA_GRAPH))
    shared = set(graph.triples((URIRef(NS + "entity/close"), None, None)))
    for kind, source in (("delete_relation", "v-original"), ("create_relation", "v-repair")):
        command = compile_command(kind, {
            "ontology_id": ONTOLOGY_ID, "source_entity_iri": NS + "entity/bind-original",
            "relation_type_iri": NS + "property/fromValue",
            "target_entity_iri": NS + "entity/" + source,
        }, Settings())
        from rdflib.util import from_n3
        for s, p, o, _ in command.delta.deletes:
            graph.remove((from_n3(s), from_n3(p), from_n3(o)))
        for s, p, o, g in command.delta.inserts:
            store.dataset.graph(URIRef(g)).parse(data=f"{s} {p} {o} .", format="turtle")
    assert _objects(graph, "bind-original", "fromValue") == {NS + "entity/v-repair"}
    assert set(graph.triples((URIRef(NS + "entity/close"), None, None))) == shared


def test_hidden_sources_and_guards_keep_existing_response_and_count_contract(
    in_memory_session, monkeypatch,
):
    from app.api import semantic

    _, store = _materialize(candidate())
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    hidden = {NS + "entity/v-repair", NS + "entity/ready", NS + "entity/close-target"}
    # Same subject/same IRI before creation vs after authorization filtering.
    missing = NS + "entity/not-created"
    before = client.get(f"/api/semantic/resources/{missing}",
                        params={"graph_set_id": "gs-009"})
    view = SemanticAccessView(requires_filtering=True,
                             _unauthorized_iris=frozenset(hidden | {missing}))
    monkeypatch.setattr(semantic, "_access_view", lambda *_a, **_kw: view)
    after = client.get(f"/api/semantic/resources/{missing}", params={"graph_set_id": "gs-009"})
    assert (before.status_code, before.json()) == (after.status_code, after.json())
    for iri in hidden:
        response = client.get(f"/api/semantic/resources/{iri}", params={"graph_set_id": "gs-009"})
        assert response.status_code == 404
        assert response.json() == {"detail": f"Resource not found: {iri}"}
    all_visible = _read_model(client, "entity-list")
    page = _read_model(client, "entity-list", limit=1)
    assert page["items"] == all_visible["items"][:1]
    assert page["paging"]["visible_count"] == len(all_visible["items"])
    for path in ("/api/semantic/statements", "/api/semantic/graph-sets/gs-009/read-models/entity-relations"):
        response = client.get(path, params={"graph_set_id": "gs-009"})
        assert response.status_code == 200
        assert all(iri not in response.text for iri in hidden)
