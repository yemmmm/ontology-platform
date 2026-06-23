from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories.models import (
    CompetencyQuestionModel,
    EvidenceModel,
    FactClaimModel,
    KnowledgeConflictModel,
    OntologyVersionModel,
    ProposalModel,
    VersionStatus,
)
from app.services import publication


def version(status: str = "draft") -> OntologyVersionModel:
    return OntologyVersionModel(
        id="v1", ontology_id="o1", version_number=1, status=status, workflow_status="graph_review"
    )


def _mock_question(**overrides) -> CompetencyQuestionModel:
    values = dict(
        id="q1", project_id="p1", ontology_id="o1", question="q", importance=5,
        position=0, status="testable", active=True,
        query_definition={"kind": "entity_count", "class_id": "c1", "min_count": 1},
        validation_result={}, source_answer_ids=[], source_brief_fields=[],
    )
    values.update(overrides)
    return CompetencyQuestionModel(**values)


def _mock_fact_claim(layer: str = "entity_attribute", audit_status: str = "pending", **overrides) -> FactClaimModel:
    values = dict(
        id="c1", ontology_version_id="v1", claim_type="direct", layer=layer,
        subject={"entity_id": "e"}, predicate="p", value=1, evidence_ids=[],
        generation_reason="entity_property", confidence=1.0, audit_status=audit_status,
        claim_key=f"{layer}:e:p:1",
    )
    values.update(overrides)
    return FactClaimModel(**values)


def _make_readiness_session(
    *,
    scalars_returns: list | None = None,
    scalar_returns: list | None = None,
    execute_rows: list | None = None,
    version_status: str = "draft",
) -> tuple[MagicMock, OntologyVersionModel]:
    """Build a MagicMock session configured for evaluate_readiness."""
    session = MagicMock()
    v = version(status=version_status)
    session.get.side_effect = lambda model, _id: v
    session.scalars.side_effect = lambda *a, **kw: iter(scalars_returns.pop(0) if scalars_returns else [])
    if scalar_returns is not None:
        session.scalar.side_effect = scalar_returns
    execute_result = MagicMock()
    execute_result.all.return_value = execute_rows or []
    session.execute.return_value = execute_result
    return session, v


def test_evaluate_readiness_blocks_when_pending_proposals_exist() -> None:
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [], [], []],
        scalar_returns=[2, 0],
    )

    result = publication.evaluate_readiness(session, MagicMock(), "v1")

    gate = next(g for g in result["gates"] if g["gate_type"] == "pending_proposals")
    assert gate["status"] == "failed"
    assert result["ready"] is False
    assert "pending_proposals" in result["blocking"]


def test_evaluate_readiness_blocks_when_testable_critical_question_is_not_passed() -> None:
    pending_question = _mock_question(status="testable")
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [pending_question], [], []],
        scalar_returns=[0, 0],
    )

    result = publication.evaluate_readiness(session, MagicMock(), "v1")

    gate = next(g for g in result["gates"] if g["gate_type"] == "competency_questions")
    assert gate["status"] == "failed"


def test_evaluate_readiness_blocks_when_low_confidence_facts_unreviewed() -> None:
    unreviewed = _mock_fact_claim(layer="low_confidence", claim_type="low_confidence", confidence=0.3)
    session, _ = _make_readiness_session(
        scalars_returns=[[], [unreviewed], [], [], [], []],
        scalar_returns=[0, 0],
    )

    result = publication.evaluate_readiness(session, MagicMock(), "v1")

    gate = next(g for g in result["gates"] if g["gate_type"] == "low_confidence_review")
    assert gate["status"] == "failed"


def test_evaluate_readiness_blocks_when_conflict_pending() -> None:
    conflict = KnowledgeConflictModel(
        id="k1", project_id="p1", ontology_id="o1", proposal_id="prop",
        item_key="i", field="f", existing_value="a", proposed_value="b",
        status="pending", resolution={},
    )
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [], [], []],
        scalar_returns=[0, 1],
    )

    result = publication.evaluate_readiness(session, MagicMock(), "v1")

    gate = next(g for g in result["gates"] if g["gate_type"] == "unresolved_conflicts")
    assert gate["status"] == "failed"
    assert conflict.status == "pending"


def test_evaluate_readiness_passes_when_all_gates_green() -> None:
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [], [], []],
        scalar_returns=[0, 0],
    )

    with patch.object(
        publication, "_fact_audit_summary",
        return_value={"total": 5, "approved": 5, "unaudited": 0, "rejected_unfixed": 0, "accuracy": 1.0},
    ):
        result = publication.evaluate_readiness(session, MagicMock(), "v1")

    assert result["ready"] is True
    assert result["blocking"] == []
    assert {g["status"] for g in result["gates"]} == {"passed"}


def test_publish_rejects_when_readiness_fails() -> None:
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [], [], []],
        scalar_returns=[1, 0],
    )

    with pytest.raises(HTTPException, match="Publication gates have not passed"):
        publication.publish_version(session, MagicMock(), "v1", confirm=True)


def test_publish_requires_explicit_confirmation() -> None:
    session, _ = _make_readiness_session(
        scalars_returns=[[], [], [], [], [], []],
        scalar_returns=[0, 0],
    )

    with patch.object(
        publication, "_fact_audit_summary",
        return_value={"total": 5, "approved": 5, "unaudited": 0, "rejected_unfixed": 0, "accuracy": 1.0},
    ):
        with pytest.raises(HTTPException, match="explicit confirmation"):
            publication.publish_version(session, MagicMock(), "v1", confirm=False)


def test_publish_action_blocks_when_already_published() -> None:
    session = MagicMock()
    session.get.return_value = version(status="published")

    with pytest.raises(HTTPException, match="immutable"):
        publication.publish_version(session, MagicMock(), "v1", confirm=True)


def test_publish_creates_immutable_snapshot_with_report() -> None:
    from app.repositories.models import OntologyModel

    session = MagicMock()
    v = version()
    ontology = SimpleNamespace(id="o1", current_version_id=None, status="draft")
    session.get.side_effect = lambda model, _id: v if model is OntologyVersionModel else ontology
    session.scalars.side_effect = lambda *a, **kw: iter([])
    session.scalar.side_effect = [0, 0]
    execute_result = MagicMock()
    execute_result.all.return_value = []
    session.execute.return_value = execute_result

    captured = {}

    def fake_persist(_session, _driver, version_arg, readiness):
        captured["version"] = version_arg
        captured["readiness"] = readiness
        version_arg.workflow_status = "published"
        version_arg.published_at = publication._now()

    with patch.object(
        publication, "_fact_audit_summary",
        return_value={"total": 5, "approved": 5, "unaudited": 0, "rejected_unfixed": 0, "accuracy": 1.0},
    ), patch.object(publication, "_persist_published_snapshot", side_effect=fake_persist) as persist:
        publication.publish_version(session, MagicMock(), "v1", confirm=True)

    persist.assert_called_once()
    assert v.status == VersionStatus.PUBLISHED.value
    assert v.workflow_status == "published"
    assert ontology.status == "active"
    assert captured["readiness"]["ready"] is True
    session.commit.assert_called()
