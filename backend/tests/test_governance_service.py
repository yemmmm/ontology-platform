from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.schemas import ProposalCreate
from app.repositories.models import OntologyVersionModel, ProposalModel
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
        payload={"items": [{"key": "person", "kind": "class", "data": {"name": "Person"}}]},
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
