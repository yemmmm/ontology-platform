from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas import ProposalCreate, ProposalItemReview, ReviewDecisionCreate
from app.repositories.models import (
    ClassModel,
    OntologyVersionModel,
    PropertyDefModel,
    ProposalModel,
    RelationTypeModel,
    ReviewBatchModel,
)
from app.repositories.postgres import assert_version_mutable
from app.services import governance


def proposal(status: str = "proposed") -> ProposalModel:
    return ProposalModel(
        id="proposal",
        project_id="project",
        ontology_id="ontology",
        target_version_id="version",
        proposal_type="schema_change",
        status=status,
        source_type="agent",
        idempotency_key="request-1",
        payload={
            "items": [
                {
                    "key": "person",
                    "kind": "class",
                    "data": {"name": "Person", "source_kind": "domain_concept"},
                    "competency_question_ids": ["question-1"],
                }
            ]
        },
        created_by_type="agent",
        validation_result={},
        review_result={},
        application_result={},
        audit_log=[],
    )


def test_proposal_state_machine_rejects_skipping_validation() -> None:
    item = proposal()

    with pytest.raises(HTTPException, match="proposed -> approved"):
        governance._transition(item, "approved")

    assert item.status == "proposed"


def test_validation_failure_returns_proposal_to_editable_state() -> None:
    session = MagicMock()
    item = proposal()
    item.payload = {"items": []}
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )

    governance.validate_proposal(session, item.id)

    assert item.status == "proposed"
    assert item.validation_result["valid"] is False
    assert [event["action"] for event in item.audit_log] == ["validating", "proposed"]
    session.commit.assert_called_once_with()


def test_duplicate_idempotency_key_returns_existing_proposal() -> None:
    session = MagicMock()
    existing = proposal()
    session.scalar.return_value = existing
    payload = ProposalCreate(
        project_id="project",
        ontology_id="ontology",
        target_version_id="version",
        proposal_type="schema_change",
        source_type="agent",
        idempotency_key="request-1",
        payload=existing.payload,
        created_by_type="agent",
    )

    result = governance.create_proposal(session, payload)

    assert result is existing
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("version_status", ["published", "deprecated"])
def test_repository_rejects_non_draft_version_writes(version_status: str) -> None:
    session = MagicMock()
    session.get.return_value = OntologyVersionModel(
        id="version", ontology_id="ontology", version_number=1, status=version_status
    )

    with pytest.raises(HTTPException, match="immutable") as exc_info:
        assert_version_mutable(session, "version")

    assert exc_info.value.status_code == 409


def test_apply_failure_rolls_back_entire_schema_batch() -> None:
    session = MagicMock()
    item = proposal(status="approved")
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )

    with (
        patch.object(governance, "_apply_schema", side_effect=ValueError("second item invalid")),
        pytest.raises(HTTPException, match="second item invalid"),
    ):
        governance.apply_proposal(session, MagicMock(), item.id)

    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()
    assert item.application_result == {}


def test_apply_is_idempotent_after_proposal_is_applied() -> None:
    session = MagicMock()
    item = proposal(status="applied")
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )

    result = governance.apply_proposal(session, MagicMock(), item.id)

    assert result is item
    session.commit.assert_not_called()


def test_get_review_batch_returns_stable_workbench_deep_link() -> None:
    session = MagicMock()
    batch = ReviewBatchModel(
        id="batch-1",
        stable_key="proposal:proposal",
        project_id="project",
        ontology_id="ontology",
        ontology_version_id="version",
        review_type="schema",
        status="pending",
        item_ids=["person"],
        counts={"pending": 1, "approved": 0, "rejected": 0, "modified": 0},
    )
    session.get.return_value = batch

    result = governance.get_review_batch(session, batch.id)

    assert result["id"] == "batch-1"
    assert result["deep_link"] == (
        "/?project=project&ontology=ontology&tab=schema-review&batch=batch-1"
    )


def test_get_review_batch_rejects_unknown_id() -> None:
    session = MagicMock()
    session.get.return_value = None

    with pytest.raises(HTTPException, match="Review batch not found") as exc_info:
        governance.get_review_batch(session, "missing")

    assert exc_info.value.status_code == 404


def test_list_version_proposals_rejects_unknown_version() -> None:
    session = MagicMock()
    session.get.return_value = None

    with pytest.raises(HTTPException, match="Ontology version not found") as exc_info:
        governance.list_version_proposals(session, "missing")

    assert exc_info.value.status_code == 404


def test_rejected_proposal_cannot_modify_formal_data() -> None:
    session = MagicMock()
    item = proposal(status="rejected")
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )

    with (
        patch.object(governance, "_apply_schema") as apply_schema,
        pytest.raises(HTTPException, match="Only approved"),
    ):
        governance.apply_proposal(session, MagicMock(), item.id)

    apply_schema.assert_not_called()
    session.commit.assert_not_called()


def schema_validation_session(
    classes: list[ClassModel] | None = None,
    relations: list[RelationTypeModel] | None = None,
    properties: list[PropertyDefModel] | None = None,
) -> MagicMock:
    session = MagicMock()
    session.scalar.return_value = 1  # proposal evidence count
    session.scalars.side_effect = [classes or [], relations or [], properties or []]
    return session


def test_schema_validation_detects_inheritance_cycle() -> None:
    item = proposal()
    item.payload = {
        "items": [
            {
                "key": "a",
                "kind": "class",
                "data": {"name": "A", "parent_class_keys": ["b"]},
            },
            {
                "key": "b",
                "kind": "class",
                "data": {"name": "B", "parent_class_keys": ["a"]},
            },
        ]
    }

    errors, _ = governance._validate_items(schema_validation_session(), item)

    assert "class inheritance cycle detected" in errors


def test_schema_validation_rejects_cross_ontology_parent_and_relation_endpoint() -> None:
    item = proposal()
    item.payload = {
        "items": [
            {
                "key": "child",
                "kind": "class",
                "data": {"name": "Child", "parent_class_ids": ["foreign-class"]},
            },
            {
                "key": "owns",
                "kind": "relation_type",
                "data": {
                    "name": "OWNS",
                    "source_class_key": "child",
                    "target_class_id": "foreign-class",
                },
            },
        ]
    }

    errors, _ = governance._validate_items(schema_validation_session(), item)

    assert any("cross-ontology parents" in error for error in errors)
    assert any("cross-ontology endpoints" in error for error in errors)


def test_schema_validation_rejects_invalid_relation_scope_policy() -> None:
    item = proposal()
    item.payload = {
        "items": [
            {"key": "course", "kind": "class", "data": {"name": "Course"}},
            {
                "key": "conflicts",
                "kind": "relation_type",
                "data": {
                    "name": "CONFLICTS_WITH",
                    "source_class_key": "course",
                    "target_class_key": "course",
                    "scope_policy": "invalid",
                },
            },
        ]
    }

    errors, _ = governance._validate_items(schema_validation_session(), item)

    assert "relation type conflicts has invalid scope_policy" in errors


def test_schema_validation_detects_duplicate_names_and_invalid_property_type() -> None:
    existing = ClassModel(
        id="existing", ontology_id="ontology", name="Person", normalized_label="Person"
    )
    item = proposal()
    item.payload = {
        "items": [
            {"key": "person", "kind": "class", "data": {"name": "person"}},
            {
                "key": "age",
                "kind": "property",
                "data": {"name": "age", "class_id": "existing", "type": "integer"},
            },
        ]
    }

    errors, _ = governance._validate_items(schema_validation_session([existing]), item)

    assert any("conflicts with existing class" in error for error in errors)
    assert "property age has unsupported type: integer" in errors


def test_schema_validation_requires_evidence_and_competency_question() -> None:
    session = schema_validation_session()
    session.scalar.return_value = 0
    item = proposal()
    item.payload = {
        "items": [
            {"key": "person", "kind": "class", "data": {"name": "Person"}}
        ]
    }

    errors, _ = governance._validate_items(session, item)

    assert "schema proposal must cite evidence" in errors
    assert "schema proposal must cite at least one competency question" in errors


def test_schema_validation_accepts_source_kind_and_rejects_invalid_source_kind() -> None:
    item = proposal()
    item.payload = {
        "items": [
            {
                "key": "student",
                "kind": "class",
                "data": {"name": "Student", "source_kind": "domain_concept"},
                "competency_question_ids": ["q1"],
            },
            {
                "key": "raw-table",
                "kind": "class",
                "data": {"name": "student_table", "source_kind": "database_table"},
                "competency_question_ids": ["q1"],
            },
        ]
    }

    errors, _ = governance._validate_items(schema_validation_session(), item)

    assert "class raw-table has invalid source_kind" in errors
    assert not any("class student has invalid source_kind" in error for error in errors)


def test_schema_batch_accepts_constraint_and_rejects_duplicate_class_property() -> None:
    existing = ClassModel(
        id="person", ontology_id="ontology", name="Person", normalized_label="Person"
    )
    existing_property = PropertyDefModel(
        id="name", class_id="person", name="name", type="string"
    )
    item = proposal()
    item.payload = {
        "items": [
            {
                "key": "name-again",
                "kind": "property",
                "data": {"name": "Name", "class_id": "person", "type": "string"},
            },
            {
                "key": "person-name-required",
                "kind": "constraint",
                "data": {"scope": "person", "kind": "required_property"},
            },
        ]
    }

    errors, _ = governance._validate_items(
        schema_validation_session([existing], properties=[existing_property]), item
    )

    assert any("property name conflicts" in error for error in errors)
    assert not any("constraint" in error for error in errors)


def test_apply_schema_persists_relation_type_v0_4_metadata() -> None:
    session = MagicMock()
    item = proposal(status="approved")
    item.payload = {
        "items": [
            {"key": "course", "kind": "class", "data": {"id": "course", "name": "Course"}},
            {
                "key": "conflicts",
                "kind": "relation_type",
                "data": {
                    "id": "conflicts",
                    "name": "CONFLICTS_WITH",
                    "source_class_key": "course",
                    "target_class_key": "course",
                    "scope_policy": "entity_only",
                    "symmetric": True,
                    "transitive": False,
                    "status": "active",
                    "valid_from": "2026-06-25T00:00:00+00:00",
                    "valid_to": None,
                },
            },
        ]
    }

    governance._apply_schema(session, item)

    relation_type = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], RelationTypeModel)
    ][0]
    assert relation_type.scope_policy == "entity_only"
    assert relation_type.symmetric is True
    assert relation_type.transitive is False
    assert relation_type.status == "active"
    assert relation_type.valid_from == "2026-06-25T00:00:00+00:00"
    assert relation_type.valid_to is None


def test_graph_validation_rejects_schema_only_relation_type() -> None:
    session = MagicMock()
    relation_type = RelationTypeModel(
        id="rel",
        ontology_id="ontology",
        name="REL",
        normalized_type="REL",
        source_class_id="class",
        target_class_id="class",
        external_mappings={},
        scope_policy="schema_allowed",
    )
    item = proposal()
    item.proposal_type = "relation"
    item.payload = {
        "items": [
            {
                "key": "r1",
                "kind": "relation",
                "data": {
                    "relation_type_id": "rel",
                    "source_entity_id": "e1",
                    "target_entity_id": "e2",
                },
                "evidence_ids": ["ev"],
            }
        ]
    }
    session.scalars.side_effect = [["ev"], [], [relation_type]]

    errors, _ = governance._validate_items(session, item, driver=None)

    assert "relation r1 uses a schema-only relation type" in errors


def test_apply_graph_preserves_relation_instance_metadata() -> None:
    session = MagicMock()
    driver = MagicMock()
    ontology = SimpleNamespace(id="ontology", project_id="project")
    relation_type = RelationTypeModel(
        id="rel",
        ontology_id="ontology",
        name="REL",
        normalized_type="REL",
        source_class_id="class",
        target_class_id="class",
        external_mappings={},
        scope_policy="entity_only",
    )
    item = proposal(status="approved")
    item.proposal_type = "relation"
    item.payload = {
        "items": [
            {
                "key": "r1",
                "kind": "relation",
                "data": {
                    "id": "r1",
                    "relation_type_id": "rel",
                    "source_entity_id": "e1",
                    "target_entity_id": "e2",
                    "scope": "instance",
                    "status": "active",
                    "valid_from": "2026-06-25",
                    "valid_to": None,
                    "properties": {"reason": "same time slot"},
                },
            }
        ]
    }
    session.get.side_effect = lambda model, _id: (
        ontology if model.__name__ == "OntologyModel" else relation_type
    )

    with patch.object(governance.graph_repo, "apply_graph_batch", return_value={}) as apply_batch:
        governance._apply_graph(session, driver, item)

    relation = apply_batch.call_args.kwargs["relations"][0]
    assert relation["scope"] == "instance"
    assert relation["status"] == "active"
    assert relation["valid_from"] == "2026-06-25"
    assert relation["valid_to"] is None


def test_schema_snapshot_includes_relation_type_scope_metadata() -> None:
    session = MagicMock()
    relation_type = RelationTypeModel(
        id="rel",
        ontology_id="ontology",
        name="CONFLICTS_WITH",
        normalized_type="CONFLICTS_WITH",
        source_class_id="course",
        target_class_id="course",
        external_mappings={},
        scope_policy="entity_only",
        symmetric=True,
        transitive=False,
        status="active",
        valid_from=None,
        valid_to=None,
    )
    session.scalars.side_effect = [[], [relation_type]]

    snapshot = governance._schema_snapshot(session, "ontology")

    assert snapshot["relation_types"] == [
        {
            "id": "rel",
            "name": "CONFLICTS_WITH",
            "source": "course",
            "target": "course",
            "scope_policy": "entity_only",
            "symmetric": True,
            "transitive": False,
            "status": "active",
            "valid_from": None,
            "valid_to": None,
        }
    ]


def test_schema_item_edit_keeps_item_editable_and_invalidates_validation() -> None:
    session = MagicMock()
    item = proposal(status="validated")
    item.payload["items"][0]["review_status"] = "approved"
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )
    session.scalar.return_value = None

    governance.review_proposal_item(
        session,
        item.id,
        "person",
        ProposalItemReview(action="edited", data={"name": "Human"}),
    )

    assert item.status == "proposed"
    assert item.payload["items"][0]["data"] == {"name": "Human"}
    assert item.payload["items"][0]["review_status"] == "pending"
    assert item.payload["items"][0]["modified"] is True


def test_proposal_approval_requires_every_schema_item_to_be_reviewed() -> None:
    session = MagicMock()
    item = proposal(status="validated")
    session.get.side_effect = lambda model, _id: (
        item if model is ProposalModel else SimpleNamespace(status="draft")
    )

    with pytest.raises(HTTPException, match="must be reviewed"):
        governance.review_proposal(
            session,
            item.id,
            ReviewDecisionCreate(decision="approved", reviewer_type="user"),
        )

    session.commit.assert_not_called()
