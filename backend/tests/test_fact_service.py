from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories.models import (
    FactClaimModel,
    OntologyModel,
    OntologyVersionModel,
)


def test_fact_claim_model_defaults_are_pending_and_stale_false() -> None:
    columns = {c.name: c for c in FactClaimModel.__table__.columns}
    assert columns["audit_status"].default.arg == "pending"
    assert columns["stale"].default.arg is False
    assert columns["confidence"].default.arg == 1.0


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


def test_invalidate_for_graph_change_noops_without_changes() -> None:
    from app.services import facts

    session = MagicMock()
    affected = facts.invalidate_for_graph_change(
        session, "o1", "v1", entity_ids=set(), relation_ids=set()
    )

    assert affected == 0
    session.commit.assert_not_called()
