from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories.models import (
    ClassModel,
    FactClaimModel,
    OntologyModel,
    OntologyVersionModel,
    PropertyDefModel,
    RuleDefinitionModel,
    UnanchoredKnowledgeModel,
)


def test_fact_claim_model_defaults_are_pending_and_stale_false() -> None:
    columns = {c.name: c for c in FactClaimModel.__table__.columns}
    assert columns["audit_status"].default.arg == "pending"
    assert columns["stale"].default.arg is False
    assert columns["confidence"].default.arg == 1.0
    assert columns["sensitivity"].default.arg == "normal"
    assert columns["anchor"].default.arg(None) == {}


def test_v05_storage_models_include_rules_and_background_knowledge() -> None:
    rule_columns = {c.name for c in RuleDefinitionModel.__table__.columns}
    background_columns = {c.name for c in UnanchoredKnowledgeModel.__table__.columns}

    assert {
        "rule_type", "scope", "condition", "conclusion", "priority",
        "status", "evidence_ids", "version",
    } <= rule_columns
    assert {
        "text", "summary", "embedding", "tags", "confidence",
        "applicability", "promoted_proposal_id",
    } <= background_columns


def test_generate_direct_attribute_facts_uses_graph_properties() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: (
        version if model is OntologyVersionModel else ontology if model is OntologyModel else None
    )
    session.scalars.return_value = []
    graph_data = {
        "entities": [
            {
                "id": "e1", "class_id": "c1", "class_label": "Supplier", "name": "Acme",
                "properties": {"legal_name": "Acme Inc.", "tier": "A"},
                "ontology_version_id": "v1",
            }
        ],
        "relations": [],
    }
    evidence_index = {"e1": ["ev1"]}

    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value=evidence_index):
        claims = facts.generate_fact_claims(session, driver, "v1")

    attribute_claims = [c for c in claims if c.layer == "entity_attribute"]
    assert {c.predicate for c in attribute_claims} == {"legal_name", "tier"}
    assert all(c.claim_type == "direct" for c in attribute_claims)
    session.query.assert_called()  # cleared prior claims
    session.commit.assert_called_once()


def test_generate_low_confidence_facts_for_risky_relations() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([])
    graph_data = {
        "entities": [
            {"id": "e1", "class_id": "c1", "class_label": "C", "name": "X",
             "properties": {}, "ontology_version_id": "v1"},
            {"id": "e2", "class_id": "c2", "class_label": "D", "name": "Y",
             "properties": {}, "ontology_version_id": "v1"},
        ],
        "relations": [
            {"id": "r1", "relation_type_id": "rt1", "relation_type": "REL",
             "source_entity_id": "e1", "target_entity_id": "e2",
             "properties": {"confidence": 0.4}, "ontology_version_id": "v1"}
        ],
    }
    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        claims = facts.generate_fact_claims(session, driver, "v1")

    low = [c for c in claims if c.layer == "low_confidence"]
    assert any(c.subject["entity_id"] == "e1" and c.predicate == "REL" for c in low)
    assert all(c.confidence < 0.7 for c in low)


def test_generate_relation_fact_marks_rejected_relation_rejected_and_stale() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([])
    graph_data = {
        "entities": [
            {"id": "e1", "class_id": "c1", "class_label": "C", "name": "X",
             "properties": {}, "ontology_version_id": "v1"},
            {"id": "e2", "class_id": "c2", "class_label": "D", "name": "Y",
             "properties": {}, "ontology_version_id": "v1"},
        ],
        "relations": [
            {"id": "r1", "relation_type_id": "rt1", "relation_type": "FRIEND_OF",
             "source_entity_id": "e1", "target_entity_id": "e2",
             "properties": {}, "status": "rejected", "ontology_version_id": "v1"}
        ],
    }
    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        claims = facts.generate_fact_claims(session, driver, "v1")

    relation_claim = next(c for c in claims if c.layer == "entity_relation")
    assert relation_claim.audit_status == "rejected"
    assert relation_claim.stale is True
    assert relation_claim.stale_reason == "relation_rejected"


def test_generate_relation_fact_marks_past_valid_to_stale() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([])
    graph_data = {
        "entities": [
            {"id": "e1", "class_id": "c1", "class_label": "C", "name": "X",
             "properties": {}, "ontology_version_id": "v1"},
            {"id": "e2", "class_id": "c2", "class_label": "D", "name": "Y",
             "properties": {}, "ontology_version_id": "v1"},
        ],
        "relations": [
            {"id": "r1", "relation_type_id": "rt1", "relation_type": "FRIEND_OF",
             "source_entity_id": "e1", "target_entity_id": "e2",
             "properties": {}, "valid_to": "2000-01-01", "ontology_version_id": "v1"}
        ],
    }
    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        claims = facts.generate_fact_claims(session, driver, "v1")

    relation_claim = next(c for c in claims if c.layer == "entity_relation")
    assert relation_claim.audit_status == "pending"
    assert relation_claim.stale is True
    assert relation_claim.stale_reason == "relation_expired"


def test_generate_inferred_inverse_facts_when_relation_has_inverse() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    relation_type = SimpleNamespace(
        id="rt1", name="SUPPLIES", inverse_name="SUPPLIED_BY",
        source_class_id="c1", target_class_id="c2",
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([relation_type])
    graph_data = {
        "entities": [
            {"id": "e1", "class_id": "c1", "class_label": "Supplier", "name": "Acme",
             "properties": {}, "ontology_version_id": "v1"},
            {"id": "e2", "class_id": "c2", "class_label": "Component", "name": "Widget",
             "properties": {}, "ontology_version_id": "v1"},
        ],
        "relations": [
            {"id": "r1", "relation_type_id": "rt1", "relation_type": "SUPPLIES",
             "source_entity_id": "e1", "target_entity_id": "e2",
             "properties": {}, "ontology_version_id": "v1"}
        ],
    }
    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        claims = facts.generate_fact_claims(session, driver, "v1")

    inferred = [c for c in claims if c.claim_type == "inferred"]
    assert any(c.predicate == "SUPPLIED_BY" and c.subject["entity_id"] == "e2" for c in inferred)


def test_generate_replaces_existing_facts_idempotently() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([])
    graph_data = {"entities": [], "relations": []}

    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        first = facts.generate_fact_claims(session, driver, "v1")
        facts.generate_fact_claims(session, driver, "v1")

    assert first == []
    # Each run must clear prior claims (delete) before adding.
    assert session.query.call_count == 2


def test_generate_only_replaces_graph_generated_fact_layers() -> None:
    from app.services import facts

    session = MagicMock()
    driver = MagicMock()
    version = SimpleNamespace(
        id="v1", ontology_id="o1", status="draft", workflow_status="graph_review"
    )
    ontology = SimpleNamespace(id="o1", project_id="p1")
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.return_value = iter([])
    graph_data = {"entities": [], "relations": []}

    with patch.object(facts, "_graph_snapshot", return_value=graph_data), \
         patch.object(facts, "_entity_evidence_index", return_value={}):
        facts.generate_fact_claims(session, driver, "v1")

    filter_args = session.query.return_value.filter.call_args.args
    assert len(filter_args) == 2
    assert str(filter_args[0].left) == "fact_claims.ontology_version_id"
    assert str(filter_args[1].left) == "fact_claims.layer"
    assert set(filter_args[1].right.value) == facts.GENERATED_FACT_LAYERS
    assert not facts.CORE_ASSERTION_LAYERS & facts.GENERATED_FACT_LAYERS


def test_generate_rejects_non_draft_version() -> None:
    from app.services import facts

    session = MagicMock()
    version = SimpleNamespace(id="v1", ontology_id="o1", status="published", workflow_status="published")
    session.get.return_value = version

    with pytest.raises(HTTPException, match="Only draft versions"):
        facts.generate_fact_claims(session, MagicMock(), "v1")


def _make_claim(**overrides) -> FactClaimModel:
    defaults = dict(
        id="c", ontology_version_id="v1", claim_type="direct", layer="entity_attribute",
        subject={"entity_id": "e"}, predicate="p", value=1, evidence_ids=[],
        generation_reason="entity_property", confidence=1.0, audit_status="pending",
        anchor={"type": "entity", "target_id": "e"},
        claim_key="entity_attribute:e:p:1",
    )
    defaults.update(overrides)
    return FactClaimModel(**defaults)


def test_sample_fact_claims_returns_stratified_subset_per_layer() -> None:
    from app.services import facts

    session = MagicMock()
    claims = [
        _make_claim(id=f"a{i}", predicate="p", value=i, claim_key=f"entity_attribute:e:p:{i}")
        for i in range(10)
    ] + [
        _make_claim(
            id=f"r{i}", predicate="r", value=i, layer="low_confidence",
            claim_type="low_confidence", confidence=0.3,
            claim_key=f"low_confidence:e:r:{i}",
        )
        for i in range(5)
    ]
    session.scalars.return_value = claims

    sampled = facts.sample_fact_claims(
        session, "v1", {"entity_attribute": 3, "low_confidence": 2}
    )

    layers: dict[str, int] = {}
    for claim in sampled:
        layers[claim.layer] = layers.get(claim.layer, 0) + 1
    assert layers == {"entity_attribute": 3, "low_confidence": 2}


def test_sample_prioritizes_pending_and_stale_claims() -> None:
    from app.services import facts

    session = MagicMock()
    claims = [
        _make_claim(id="approved1", audit_status="approved", claim_key="k1"),
        _make_claim(id="pending1", audit_status="pending", claim_key="k2"),
        _make_claim(id="stale1", audit_status="pending", stale=True, claim_key="k3"),
    ]
    session.scalars.return_value = claims

    sampled = facts.sample_fact_claims(session, "v1", {"entity_attribute": 2})

    ids = [c.id for c in sampled]
    assert ids == ["stale1", "pending1"]


def test_review_fact_claim_approved_marks_status() -> None:
    from app.services import facts

    session = MagicMock()
    claim = _make_claim(id="c1")
    session.get.return_value = claim

    facts.review_fact_claim(
        session, "c1", decision="approved", reviewer_id="user-1", reason="ok"
    )

    assert claim.audit_status == "approved"
    assert claim.review_decision["reviewer_id"] == "user-1"
    assert claim.reviewed_at is not None


def test_review_fact_claim_rejected_requires_fix_proposal() -> None:
    from app.services import facts

    session = MagicMock()
    claim = _make_claim(id="c1")
    session.get.return_value = claim

    with pytest.raises(HTTPException, match="linked_fix_proposal_id"):
        facts.review_fact_claim(
            session, "c1", decision="rejected", reviewer_id="u", reason="wrong"
        )


def test_review_fact_claim_rejected_with_fix_links_proposal() -> None:
    from app.services import facts

    session = MagicMock()
    claim = _make_claim(id="c1")
    session.get.return_value = claim

    facts.review_fact_claim(
        session, "c1", decision="rejected", reviewer_id="u",
        reason="wrong", linked_fix_proposal_id="prop-1",
    )

    assert claim.audit_status == "rejected"
    assert claim.linked_fix_proposal_id == "prop-1"


def test_review_fact_claim_invalid_decision_rejected() -> None:
    from app.services import facts

    session = MagicMock()
    claim = _make_claim(id="c1")
    session.get.return_value = claim

    with pytest.raises(HTTPException, match="Unsupported decision"):
        facts.review_fact_claim(session, "c1", decision="maybe", reviewer_id="u")


def test_invalidate_for_graph_change_marks_affected_pending_claims() -> None:
    from app.services import facts

    session = MagicMock()
    direct = _make_claim(
        id="c1", subject={"entity_id": "e1"},
        graph_path=[{"node": "e1"}],
    )
    relation_claim = _make_claim(
        id="c2", subject={"entity_id": "e2"},
        graph_path=[{"node": "e2"}, {"edge": "r1"}, {"node": "e1"}],
    )
    unrelated = _make_claim(
        id="c3", subject={"entity_id": "e9"},
        graph_path=[{"node": "e9"}],
    )
    session.scalars.return_value = [direct, relation_claim, unrelated]

    affected = facts.invalidate_for_graph_change(
        session, "o1", "v1", entity_ids={"e1"}, relation_ids=set()
    )

    assert affected == 2
    assert direct.stale is True
    assert relation_claim.stale is True
    assert not unrelated.stale
    session.commit.assert_called_once()


def test_invalidate_for_graph_change_marks_approved_core_assertion_stale() -> None:
    from app.services import facts

    session = MagicMock()
    approved_core = _make_claim(
        id="core", layer="entity_assertion", audit_status="approved",
        subject={"entity_id": "e1"}, graph_path=[{"node": "e1"}],
    )
    approved_generated = _make_claim(
        id="generated", layer="entity_attribute", audit_status="approved",
        subject={"entity_id": "e1"}, graph_path=[{"node": "e1"}],
    )
    session.scalars.return_value = [approved_core, approved_generated]

    affected = facts.invalidate_for_graph_change(
        session, "o1", "v1", entity_ids={"e1"}, relation_ids=set()
    )

    assert affected == 1
    assert approved_core.stale is True
    assert approved_core.stale_reason == "graph_data_changed"
    assert not approved_generated.stale
    session.commit.assert_called_once()


def test_invalidate_for_graph_change_noops_without_changes() -> None:
    from app.services import facts

    session = MagicMock()
    affected = facts.invalidate_for_graph_change(
        session, "o1", "v1", entity_ids=set(), relation_ids=set()
    )

    assert affected == 0
    session.commit.assert_not_called()


def test_create_class_assertion_validates_anchor_and_records_v05_metadata() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    class_ = ClassModel(id="c1", ontology_id="o1", name="TeachingBuilding", normalized_label="teachingbuilding")

    def get(model, _id):
        return {
            OntologyVersionModel: version,
            OntologyModel: ontology,
            ClassModel: class_,
        }.get(model)

    session.get.side_effect = get

    claim = facts.create_assertion(
        session,
        "v1",
        anchor={"type": "class", "target_id": "c1", "scope": "default_for_instances"},
        subject={"class_id": "c1", "name": "TeachingBuilding"},
        predicate="closes_at",
        value="23:00",
        evidence_ids=["ev1"],
    )

    assert claim.layer == "class_assertion"
    assert claim.anchor["scope"] == "default_for_instances"
    assert claim.evidence_ids == ["ev1"]
    assert claim.sensitivity == "normal"
    session.add.assert_called_once_with(claim)
    session.commit.assert_called_once()


def test_create_assertion_rejects_missing_class_anchor_target() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")

    def get(model, _id):
        return version if model is OntologyVersionModel else ontology if model is OntologyModel else None

    session.get.side_effect = get

    with pytest.raises(HTTPException, match="Class anchor target does not exist"):
        facts.create_assertion(
            session,
            "v1",
            anchor={"type": "class", "target_id": "missing"},
            subject={"class_id": "missing"},
            predicate="p",
            value="v",
        )


def test_recall_background_knowledge_marks_background_recall_not_core_fact() -> None:
    from app.services import facts

    session = MagicMock()
    row = UnanchoredKnowledgeModel(
        id="bg1", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        text="8 小时睡眠能保证上课状态", source={"kind": "note"},
        summary="sleep background", embedding=[1.0, 0.0], tags=["sleep"],
        confidence=0.6,
    )
    session.scalars.return_value = [row]

    results = facts.recall_background_knowledge(
        session, "v1", query="sleep", query_embedding=[1.0, 0.0]
    )

    assert results[0]["source_type"] == "background_recall"
    assert results[0]["core_fact"] is False
    assert results[0]["knowledge_id"] == "bg1"


def test_mark_background_knowledge_promoted_links_governed_proposal() -> None:
    from app.services import facts

    session = MagicMock()
    knowledge = UnanchoredKnowledgeModel(
        id="bg1", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        text="8 hours of sleep helps class readiness", source={"kind": "note"},
        summary=None, embedding=[], tags=[], confidence=0.6,
    )
    session.get.return_value = knowledge

    promoted = facts.mark_background_knowledge_promoted(
        session,
        "v1",
        "bg1",
        "proposal-1",
    )

    assert promoted.status == "promoted"
    assert promoted.promoted_proposal_id == "proposal-1"
    session.add.assert_called_once_with(knowledge)
    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(knowledge)


def test_recall_entity_knowledge_includes_class_default_and_entity_override() -> None:
    from app.services import facts

    class_default = _make_claim(
        id="class-default", layer="class_assertion", subject={"class_id": "building"},
        predicate="closes_at", value="23:00",
        anchor={"type": "class", "target_id": "building", "scope": "default_for_instances"},
        audit_status="approved",
        claim_key="class_assertion:building:closes_at:1",
    )
    override = _make_claim(
        id="override", layer="entity_assertion", subject={"entity_id": "lab1"},
        predicate="closes_at", value="22:30",
        anchor={"type": "entity", "target_id": "lab1"},
        audit_status="approved", override_of_claim_id="class-default",
        claim_key="entity_assertion:lab1:closes_at:2",
    )
    session = MagicMock()
    session.scalars.return_value = [class_default, override]

    results = facts.recall_entity_knowledge(
        session,
        "v1",
        {"id": "lab1", "class_id": "lab_building", "parent_class_ids": ["building"], "properties": {}},
    )

    assert any(item["value"] == "22:30" and item["overrides"] == "class-default" for item in results)
    assert any(item.get("claim_id") == "class-default" and item.get("overridden") for item in results)


def test_recall_entity_knowledge_redacts_sensitive_assertions_by_default() -> None:
    from app.services import facts

    masked = _make_claim(
        id="masked", layer="entity_assertion", subject={"entity_id": "student-1"},
        predicate="family_structure", value="single_parent",
        anchor={"type": "entity", "target_id": "student-1"},
        audit_status="approved", sensitivity="restricted",
        access_policy={"policy": "mask", "masking_rule": "[masked]"},
        claim_key="entity_assertion:student-1:family_structure:1",
    )
    denied = _make_claim(
        id="denied", layer="entity_assertion", subject={"entity_id": "student-1"},
        predicate="health_status", value="private",
        anchor={"type": "entity", "target_id": "student-1"},
        audit_status="approved", sensitivity="restricted",
        access_policy={"policy": "deny"},
        claim_key="entity_assertion:student-1:health_status:2",
    )
    session = MagicMock()
    session.scalars.return_value = [masked, denied]

    results = facts.recall_entity_knowledge(
        session, "v1", {"id": "student-1", "class_id": "student", "properties": {}}
    )

    by_predicate = {item["predicate"]: item for item in results}
    assert by_predicate["family_structure"]["value"] == "[masked]"
    assert by_predicate["family_structure"]["redacted"] is True
    assert by_predicate["family_structure"]["access_decision"] == "mask"
    assert by_predicate["health_status"]["value"] is None
    assert by_predicate["health_status"]["access_decision"] == "deny"


def test_recall_entity_knowledge_returns_sensitive_value_when_authorized() -> None:
    from app.services import facts

    claim = _make_claim(
        id="sensitive", layer="entity_assertion", subject={"entity_id": "student-1"},
        predicate="family_structure", value="single_parent",
        anchor={"type": "entity", "target_id": "student-1"},
        audit_status="approved", sensitivity="restricted",
        access_policy={"policy": "mask", "masking_rule": "[masked]"},
        claim_key="entity_assertion:student-1:family_structure:1",
    )
    session = MagicMock()
    session.scalars.return_value = [claim]

    results = facts.recall_entity_knowledge(
        session,
        "v1",
        {"id": "student-1", "class_id": "student", "properties": {}},
        authorized=True,
    )

    assert results[0]["value"] == "single_parent"
    assert results[0]["redacted"] is False
    assert results[0]["access_decision"] == "allow"


def test_validate_rule_definition_rejects_non_numeric_comparison_property() -> None:
    from app.services import facts

    session = MagicMock()
    class_ = ClassModel(id="student", ontology_id="o1", name="Student", normalized_label="student")
    score = PropertyDefModel(id="p1", class_id="student", name="average_score", type="string")
    session.get.return_value = class_
    session.scalars.return_value = [score]

    result = facts.validate_rule_definition(
        session,
        "o1",
        {
            "rule_type": "classification",
            "scope": {"class": "student"},
            "condition": {">": [{"property": "average_score"}, 90]},
            "conclusion": {"assert": {"predicate": "student_status", "value": "excellent"}},
        },
    )

    assert result["valid"] is False
    assert "condition property must be numeric: average_score" in result["errors"]


def test_create_and_execute_classification_rule_generates_derived_assertion() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    class_ = ClassModel(id="student", ontology_id="o1", name="Student", normalized_label="student")
    score = PropertyDefModel(id="p1", class_id="student", name="average_score", type="number")
    status = PropertyDefModel(
        id="p2", class_id="student", name="student_status", type="string",
        enum_values=["excellent", "normal"],
    )

    def get(model, _id):
        return {
            OntologyVersionModel: version,
            OntologyModel: ontology,
            ClassModel: class_,
        }.get(model)

    session.get.side_effect = get
    session.scalars.side_effect = [[score, status]]

    rule = facts.create_rule_definition(
        session,
        "v1",
        {
            "rule_type": "classification",
            "scope": {"class": "student"},
            "condition": {">": [{"property": "average_score"}, 90]},
            "conclusion": {"assert": {"predicate": "student_status", "value": "excellent"}},
            "evidence_ids": ["ev-rule"],
        },
    )
    rule.id = "rule1"

    session.add.reset_mock()
    session.commit.reset_mock()
    session.refresh.reset_mock()
    session.scalars.side_effect = [[rule], []]
    graph_data = {
        "entities": [
            {
                "id": "s1", "class_id": "student", "name": "小明",
                "properties": {"average_score": 93}, "ontology_version_id": "v1",
            }
        ],
        "relations": [],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_classification_rules(session, MagicMock(), "v1")

    assert len(claims) == 1
    claim = claims[0]
    assert claim.claim_type == "derived"
    assert claim.layer == "rule_derived"
    assert claim.anchor["type"] == "rule"
    assert claim.anchor["target_id"] == "rule1"
    assert claim.subject["entity_id"] == "s1"
    assert claim.predicate == "student_status"
    assert claim.value == "excellent"
    assert claim.evidence_ids == ["ev-rule"]


def test_execute_classification_rules_marks_missing_derivations_stale() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    rule = RuleDefinitionModel(
        id="rule1", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        rule_type="classification", scope={"class": "student"},
        condition={">": [{"property": "average_score"}, 90]},
        conclusion={"assert": {"predicate": "student_status", "value": "excellent"}},
        status="active", evidence_ids=[],
    )
    old = _make_claim(
        id="old", layer="rule_derived", claim_type="derived", generation_reason="rule:rule1",
        claim_key="rule_derived:rule1:s1:student_status:old",
        anchor={"type": "rule", "target_id": "rule1"},
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.side_effect = [[rule], [old]]
    graph_data = {
        "entities": [
            {
                "id": "s1", "class_id": "student", "name": "小明",
                "properties": {"average_score": 88}, "ontology_version_id": "v1",
            }
        ],
        "relations": [],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_classification_rules(session, MagicMock(), "v1")

    assert claims == []
    assert old.stale is True
    assert old.stale_reason == "rule_inputs_changed"


def test_rule_version_change_creates_new_derivation_and_stales_old_claim() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    rule = RuleDefinitionModel(
        id="rule1", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        rule_type="classification", scope={"class": "student"},
        condition={">": [{"property": "average_score"}, 90]},
        conclusion={"assert": {"predicate": "student_status", "value": "excellent"}},
        status="active", evidence_ids=[], version=2,
    )
    old = _make_claim(
        id="old", layer="rule_derived", claim_type="derived", generation_reason="rule:rule1",
        claim_key="rule_derived:rule1:v1:s1:student_status:old",
        anchor={"type": "rule", "target_id": "rule1"},
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.side_effect = [[rule], [old]]
    graph_data = {
        "entities": [
            {
                "id": "s1", "class_id": "student", "name": "小明",
                "properties": {"average_score": 93}, "ontology_version_id": "v1",
            }
        ],
        "relations": [],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_rule_definitions(session, MagicMock(), "v1")

    assert len(claims) == 1
    assert ":v2:s1:" in claims[0].claim_key
    assert old.stale is True
    assert old.stale_reason == "rule_inputs_changed"


def test_execute_derived_relation_rule_generates_relation_scoped_assertion() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    rule = RuleDefinitionModel(
        id="rule-rel", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        rule_type="derived_relation", scope={},
        condition={"relation": {
            "source_class": "student", "relation_type": "ENROLLED_IN", "target_class": "course",
        }},
        conclusion={"assert": {"predicate": "TAKES_COURSE"}},
        status="active", evidence_ids=["ev-rel"],
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.side_effect = [[rule], []]
    graph_data = {
        "entities": [
            {"id": "s1", "class_id": "student", "name": "小明", "properties": {}, "ontology_version_id": "v1"},
            {"id": "c1", "class_id": "course", "name": "数学", "properties": {}, "ontology_version_id": "v1"},
        ],
        "relations": [
            {
                "id": "rel1", "relation_type": "ENROLLED_IN",
                "source_entity_id": "s1", "target_entity_id": "c1",
                "properties": {}, "ontology_version_id": "v1",
            }
        ],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_rule_definitions(session, MagicMock(), "v1")

    assert len(claims) == 1
    claim = claims[0]
    assert claim.layer == "rule_derived"
    assert claim.claim_type == "derived"
    assert claim.predicate == "TAKES_COURSE"
    assert claim.subject["entity_id"] == "s1"
    assert claim.value["target_entity_id"] == "c1"
    assert claim.anchor["output_anchor"] == {"type": "relation", "target_id": "rel1"}
    assert claim.evidence_ids == ["ev-rel"]


def test_execute_validation_rule_generates_constraint_violation_when_condition_fails() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    rule = RuleDefinitionModel(
        id="rule-val", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        rule_type="validation", scope={"class": "student"},
        condition={">=": [{"property": "average_score"}, 0]},
        conclusion={"assert": {"predicate": "constraint_violation"}},
        status="active", evidence_ids=["ev-val"],
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.side_effect = [[rule], []]
    graph_data = {
        "entities": [
            {
                "id": "s1", "class_id": "student", "name": "小明",
                "properties": {"average_score": -1}, "ontology_version_id": "v1",
            }
        ],
        "relations": [],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_rule_definitions(session, MagicMock(), "v1")

    assert len(claims) == 1
    claim = claims[0]
    assert claim.layer == "rule_validation"
    assert claim.claim_type == "validation"
    assert claim.predicate == "constraint_violation"
    assert claim.value["failed_condition"] == {">=": [{"property": "average_score"}, 0]}


def test_execute_workflow_rule_blocks_then_allows_next_ordered_step() -> None:
    from app.services import facts

    session = MagicMock()
    version = OntologyVersionModel(id="v1", ontology_id="o1", version_number=1, status="draft")
    ontology = OntologyModel(id="o1", project_id="p1", name="Campus")
    rule = RuleDefinitionModel(
        id="rule-flow", project_id="p1", ontology_id="o1", ontology_version_id="v1",
        rule_type="workflow", scope={"class": "approval_file", "workflow_template": "file_approval"},
        condition={},
        conclusion={"workflow": {"steps": [
            {"role": "counselor", "order": 1},
            {"role": "program_director", "order": 2},
        ]}},
        status="active", evidence_ids=["ev-flow"],
    )
    session.get.side_effect = lambda model, _id: version if model is OntologyVersionModel else ontology
    session.scalars.side_effect = [[rule], []]
    graph_data = {
        "entities": [
            {
                "id": "f1", "class_id": "approval_file", "name": "文件1",
                "properties": {"completed_steps": [], "requested_step_role": "program_director"},
                "ontology_version_id": "v1",
            },
            {
                "id": "f2", "class_id": "approval_file", "name": "文件2",
                "properties": {
                    "completed_steps": ["counselor"],
                    "requested_step_role": "program_director",
                },
                "ontology_version_id": "v1",
            },
        ],
        "relations": [],
    }

    with patch.object(facts, "_graph_snapshot", return_value=graph_data):
        claims = facts.execute_rule_definitions(session, MagicMock(), "v1")

    blocked = next(c for c in claims if c.subject["entity_id"] == "f1")
    allowed = next(c for c in claims if c.subject["entity_id"] == "f2")
    assert blocked.layer == "rule_validation"
    assert blocked.claim_type == "validation"
    assert blocked.predicate == "workflow_transition_blocked"
    assert blocked.value["next_role"] == "counselor"
    assert blocked.value["allowed"] is False
    assert allowed.layer == "workflow"
    assert allowed.claim_type == "workflow"
    assert allowed.predicate == "workflow_transition_allowed"
    assert allowed.value["next_role"] == "program_director"
    assert allowed.value["allowed"] is True
