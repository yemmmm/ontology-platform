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
