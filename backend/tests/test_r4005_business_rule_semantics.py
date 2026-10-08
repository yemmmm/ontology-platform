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
    for item in value["items"]:
        item["semantic"].pop("rule_definition", None)
    return value


def test_hidden_rule_script_and_endpoints_filtered_before_paging(in_memory_session, monkeypatch):
    from app.api import semantic

    _, store = _materialize(candidate())
    _seed_graph_set(in_memory_session)
    hidden = {NS + "entity/allow-close", NS + "entity/v-repair"}
    view = SemanticAccessView(requires_filtering=True, _unauthorized_iris=frozenset(hidden))
    monkeypatch.setattr(semantic, "_access_view", lambda *_args, **_kwargs: view)
    client = _client(store, in_memory_session)
    for iri in hidden | {NS + "entity/nonexistent"}:
        response = client.get(f"/api/semantic/resources/{iri}", params={"ontology_id": "gs-009"})
        assert response.status_code == 404
        assert response.json() == {"detail": f"Resource not found: {iri}"}
    full = _read_model(client, "entity-list")
    page = _read_model(client, "entity-list", limit=1)
    assert page["items"] == full["items"][:1]
    assert page["paging"]["visible_count"] == len(full["items"])
    statements = client.get("/api/semantic/statements", params={"ontology_id": "gs-009"}).json()
    for row in statements["items"]:
        assert row["subject"] not in hidden
        assert row.get("object") not in hidden
    assert "must never execute" not in json.dumps(full)


def test_retirement_preserves_business_rule_context_query_and_rejects_old_kind(in_memory_session):
    from app.core.config import Settings
    from app.services.semantic_context_query import (
        SemanticContextQueryError, SemanticContextQueryService,
    )
    from app.services.semantic_query_scope import SemanticQueryScopeResolver
    from test_semantic_context_query import DatasetStore, _principal, _ready_ontology

    settings = Settings()
    _ready_ontology(in_memory_session, settings, project_id="rule-project", ontology_id=ONTOLOGY_ID)
    value = candidate()
    _, store = _materialize(value)
    service = SemanticContextQueryService(
        in_memory_session, DatasetStore(store.dataset), SemanticQueryScopeResolver(in_memory_session, settings),
    )
    args = dict(project_id="rule-project", scope_mode="ontologies", ontology_ids=[ONTOLOGY_ID],
                query="金额规则", search_mode="lexical", semantic_roles=["rule"],
                depth=0, principal=_principal())
    result = service.query(**args, resource_types=["instance"])
    matches = result["primary_matches"]
    assert {m["iri"] for m in matches} == {NS + "entity/allow-close", NS + "entity/risk"}
    for match in matches:
        assert match["kind"] == "instance"
        assert match["data"]["semantic_definition"]["semantic_role"] == "rule"
        assert "rule_definition" not in match["data"]
        assert match["data"]["semantic_definition"]["conflicting_meanings"] == ["说明 > 与脚本 >= 待业务确认"]
    with pytest.raises(SemanticContextQueryError, match="resource_types contains an unsupported value"):
        service.query(**args, resource_types=["rule"])
    assert not any("rule-result" in str(q[3]) for q in store.dataset.quads())
