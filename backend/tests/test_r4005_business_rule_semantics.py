"""Business rule storage, real RDF reads and complete Batch service validation.

Fixtures prove mechanical contracts; no script evaluation or source-based verdict.
"""

import json
from copy import deepcopy

import pytest
from rdflib.util import from_n3

from app.core.config import Settings
from app.services.semantic_access import SemanticAccessView
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
from modeling_team.protocol_mechanics import translate_candidate_to_batches
import test_modeling_batches_service as batch_tests
from test_modeling_batches_service import _item as batch_item, _request
from test_r4002_multiview_semantics import _item, _materialize
from test_r4004_process_binding import candidate as process_candidate
from test_r3009_unified_semantic_graph import NS, ONTOLOGY_ID, _client, _read_model, _seed_graph_set


@pytest.fixture
def batch_context(in_memory_session):
    return batch_tests.modeling.__wrapped__(in_memory_session)


def rule_definition(kind="judgment_constraint"):
    return {
        "kind": kind, "script_language": "Python", "script_version": "3.11",
        "script_source": "raise RuntimeError('must never execute')\namount >= 100000",
        "execution_environment": "External Consumer only; bind amount via input relations; "
                                 "return eligibility; report error; no side effects.",
        "input_status": "defined", "output_status": "defined",
        "missing_policy": "unknown stays unknown; not_applicable stays not_applicable; "
                          "empty is known empty; rejected/error never yields success",
        "change_note": "Joint revision: script, explanation, inputs, output and scope",
    }


def candidate():
    value = process_candidate()
    for key, kind, language in (("allow-close", "judgment_constraint", "Python"),
                                ("risk", "derivation", "JavaScript")):
        definition = rule_definition(kind)
        definition["script_language"] = language
        if language == "JavaScript":
            definition["script_source"] = "return amount >= 100000 ? 'high' : 'normal';"
            definition["script_version"] = "ES2022"
        value["items"].append(_item(key, "entity", {
            "entity_id": key, "values": {"label": "金额规则"},
            "semantic_definition": {
                "semantic_role": "rule", "business_meaning": "金额 > 100000",
                "applicability": "工单定义；不是业务行",
                "conflicting_meanings": ["说明 > 与脚本 >= 待业务确认"],
            }, "rule_definition": definition,
        }))
    for index, (s, p, o) in enumerate([
        ("allow-close", "usesValue", "v-original"),
        ("allow-close", "usesValue", "v-repair"),
        ("allow-close", "refersToDefinition", "close"),
        ("risk", "refersToDefinition", "original-input"),
    ]):
        value["items"].append(_item("rule-link-" + str(index), "relation", {
            "subject": {"definition_ref": s}, "predicate": p, "object": {"definition_ref": o},
        }))
    return value


def test_rule_script_explanation_sources_and_conflicts_roundtrip(in_memory_session):
    value = candidate()
    _, store = _materialize(value)
    _seed_graph_set(in_memory_session)
    client = _client(store, in_memory_session)
    for model in ("entity-list", "entity-detail"):
        rows = {r["iri"]: r for r in _read_model(client, model)["items"]}
        for item in value["items"]:
            if "rule_definition" not in item["semantic"]:
                continue
            iri = NS + "entity/" + item["item_id"]
            fields = rows[iri]["detail_fields"]
            assert fields["rule_definition"] == item["semantic"]["rule_definition"]
            assert fields["semantic_definition"] == item["semantic"]["semantic_definition"]
            response = client.get(f"/api/semantic/resources/{iri}",
                                  params={"graph_set_id": "gs-009"})
            assert response.status_code == 200
            assert response.json()["properties"]["rule_definition"] == fields["rule_definition"]
    statements = client.get("/api/semantic/statements", params={"graph_set_id": "gs-009"}).json()
    triples = {(r["subject"], r["predicate"], r.get("object")) for r in statements["items"]}
    for source in ("v-original", "v-repair"):
        assert (NS + "entity/allow-close", NS + "property/usesValue", NS + "entity/" + source) in triples
    # Definitions are stored, not evaluated, classified or automatically generated.
    assert not any("rule-result" in str(q[3]) for q in store.dataset.quads())


@pytest.mark.parametrize("annotation", [
    [], {}, "script", {"kind": "conversion"}, {"input_status": "empty"},
    {"output_status": None}, {"script_source": " "}, {"execution_environment": {}},
    {"missing_policy": []}, {"change_note": 3}, {"script_language": False},
    {"target_iri": NS + "entity/hidden"},
])
def test_invalid_annotations_are_field_local_and_repairable(annotation):
    payload = {"ontology_id": ONTOLOGY_ID, "entity_id": "rule", "label": "rule",
               "rule_definition": annotation}
    with pytest.raises(InvalidCommandPayload, match="rule_definition"):
        compile_command("create_entity", payload, Settings())
    payload["rule_definition"] = rule_definition()
    assert compile_command("create_entity", payload, Settings()).delta.inserts


def test_replacement_clear_and_partial_declarations_preserve_unknowns():
    for annotation in (rule_definition("derivation"), {"input_status": "none"},
                       {"output_status": "unknown", "missing_policy": None}, None):
        compiled = compile_command("update_entity", {
            "ontology_id": ONTOLOGY_ID, "entity_id": "rule", "rule_definition": annotation,
        }, Settings())
        assert len(compiled.delta.deletes) == 1
        assert "ruleDefinition" in compiled.delta.deletes[0][1]
        if annotation is None:
            assert not compiled.delta.inserts
        else:
            assert json.loads(str(from_n3(compiled.delta.inserts[0][2]))) == annotation
    unchanged = compile_command("update_entity", {
        "ontology_id": ONTOLOGY_ID, "entity_id": "rule", "label": "new label",
    }, Settings())
    assert not any("ruleDefinition" in p for _, p, _, _ in unchanged.delta.deletes)


def test_annotation_target_and_unresolved_references_are_repairable():
    value = candidate()
    predicate = next(i for i in value["items"] if i["item_kind"] == "predicate")
    predicate["semantic"]["rule_definition"] = rule_definition()
    conflict = translate_candidate_to_batches(value)["conflicts"][0]
    assert conflict["item_id"] == predicate["item_id"]
    assert conflict["code"] == "invalid_rule_annotation_target"
    assert "rule_definition" in conflict["detail"]
    value = candidate()
    value["items"][-1]["semantic"]["object"] = {"definition_ref": "missing"}
    assert translate_candidate_to_batches(value)["conflicts"][0]["code"] == "unbound_definition_reference"
    assert not translate_candidate_to_batches(candidate())["conflicts"]


def test_protocol_annotation_through_batch_compile_prepare_apply_and_update(batch_context):
    service, _db, rdf, session_id, lease, version = batch_context
    neutral = {"candidate_kind": "platform-neutral-candidate-v3", "candidate_revision": "rule-v1",
               "scope": "approved", "constraints": [], "items": [_item("rule", "entity", {
                   "entity_id": "rule", "values": {"label": "rule"},
                   "rule_definition": rule_definition(),
               })]}
    plan = translate_candidate_to_batches(neutral)
    assert not plan["conflicts"]
    translated = plan["batches"][0]["items"][0]
    created = None
    for index, annotation in enumerate((rule_definition(), rule_definition("derivation"), None)):
        kind = "create_entity" if index == 0 else "update_entity"
        payload = deepcopy(translated["payload"]) if index == 0 else {"entity_iri": created}
        payload["rule_definition"] = annotation
        items = [batch_item("rule", command_kind=kind, payload=payload)]
        batch = f"rule-{index}"
        dry = service.submit(session_id, _request(version, items, batch=batch, key=batch + "-dry"))
        assert dry["attempt_status"] == "validated", dry["findings"]
        applied = service.submit(session_id, _request(
            version, items, batch=batch, key=batch + "-apply", mode="apply_atomic",
            token=lease["lease_token"],
        ))
        assert applied["attempt_status"] == "applied", applied["findings"]
        version = applied["workspace"]["after_version"]
        if index == 0:
            created = applied["items"][0]["resource_outputs"]["resource_iri"]
        inserts = [o for _, p, o, _ in rdf.deltas[-1].inserts if "ruleDefinition" in p]
        assert [json.loads(str(from_n3(o))) for o in inserts] == ([] if annotation is None else [annotation])


@pytest.mark.parametrize("patch,expected", [
    ({"rule_definition": {"kind": "invalid"}}, "rule_definition.kind"),
    ({"rule_definition": []}, "rule_definition"),
    ({"unapproved_field": "bad"}, "Unknown payload field"),
])
def test_batch_rejection_locates_item_and_can_continue(batch_context, patch, expected):
    service, _db, rdf, session_id, _lease, version = batch_context
    payload = {"label": "rule", "rule_definition": rule_definition(), **patch}
    result = service.submit(session_id, _request(version, [batch_item(
        "bad-rule", command_kind="create_entity", payload=payload,
    )]))
    assert result["attempt_status"] == "validation_failed"
    assert any(f["client_item_ids"] == ["bad-rule"] and expected in f["message"]
               for f in result["findings"])
    assert not rdf.deltas
    fixed = service.submit(session_id, _request(version, [batch_item(
        "fixed-rule", command_kind="create_entity",
        payload={"label": "rule", "rule_definition": rule_definition()},
    )], batch="fixed", key="fixed"))
    assert fixed["attempt_status"] == "validated", fixed["findings"]


def test_hidden_rule_script_and_endpoints_filtered_before_paging(in_memory_session, monkeypatch):
    from app.api import semantic

    _, store = _materialize(candidate())
    _seed_graph_set(in_memory_session)
    hidden = {NS + "entity/allow-close", NS + "entity/v-repair"}
    view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(hidden))
    monkeypatch.setattr(semantic, "_access_view", lambda *_args, **_kwargs: view)
    client = _client(store, in_memory_session)
    for iri in hidden | {NS + "entity/nonexistent"}:
        response = client.get(f"/api/semantic/resources/{iri}", params={"graph_set_id": "gs-009"})
        assert response.status_code == 404
        assert response.json() == {"detail": f"Resource not found: {iri}"}
    full = _read_model(client, "entity-list")
    page = _read_model(client, "entity-list", limit=1)
    assert page["items"] == full["items"][:1]
    assert page["paging"]["visible_count"] == len(full["items"])
    statements = client.get("/api/semantic/statements", params={"graph_set_id": "gs-009"}).json()
    for row in statements["items"]:
        assert row["subject"] not in hidden
        assert row.get("object") not in hidden
    assert "must never execute" not in json.dumps(full)
