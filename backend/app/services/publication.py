"""Publication gate evaluation, readiness and explicit-confirmation publish."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.repositories import graph as graph_repo
from app.repositories.models import (
    ClassModel,
    CompetencyQuestionModel,
    EvidenceModel,
    FactClaimModel,
    KnowledgeConflictModel,
    OntologyModel,
    OntologyVersionModel,
    ProposalModel,
    PublicationGateModel,
    ValidationRunModel,
    VersionStatus,
)
from app.repositories.postgres import assert_version_mutable

GATE_ORDER = [
    "schema_validation",
    "pending_proposals",
    "unresolved_conflicts",
    "low_confidence_review",
    "evidence_coverage",
    "competency_questions",
    "fact_audit",
]
DEFAULT_FACT_ACCURACY_THRESHOLD = 0.8
CRITICAL_QUESTION_IMPORTANCE = 4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gate(gate_type: str, status: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_type": gate_type,
        "status": status,
        "details": details,
        "checked_at": _now().isoformat(),
    }


def _evaluate_schema_validation(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    runs = list(
        session.scalars(
            select(ValidationRunModel)
            .join(ProposalModel, ProposalModel.id == ValidationRunModel.proposal_id)
            .where(
                ProposalModel.target_version_id == version.id,
                ProposalModel.proposal_type.in_(["schema_change", "constraint"]),
            )
            .order_by(ValidationRunModel.started_at.desc())
        )
    )
    last_run = runs[0] if runs else None
    failed = bool(last_run and last_run.status == "failed")
    return _gate(
        "schema_validation",
        "passed" if not failed else "failed",
        {
            "last_run_id": last_run.id if last_run else None,
            "errors": last_run.errors if last_run else [],
        },
    )


def _evaluate_pending_proposals(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    count = session.scalar(
        select(func.count())
        .select_from(ProposalModel)
        .where(
            ProposalModel.target_version_id == version.id,
            ProposalModel.status.in_(["validated", "approved"]),
        )
    )
    return _gate(
        "pending_proposals",
        "passed" if not count else "failed",
        {"unapplied_proposals": int(count or 0)},
    )


def _evaluate_unresolved_conflicts(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    count = session.scalar(
        select(func.count())
        .select_from(KnowledgeConflictModel)
        .where(
            KnowledgeConflictModel.ontology_id == version.ontology_id,
            KnowledgeConflictModel.status == "pending",
        )
    )
    return _gate(
        "unresolved_conflicts",
        "passed" if not count else "failed",
        {"pending_conflicts": int(count or 0)},
    )


def _evaluate_low_confidence_review(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    unaudited = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version.id,
                FactClaimModel.layer == "low_confidence",
                FactClaimModel.audit_status == "pending",
            )
        )
    )
    return _gate(
        "low_confidence_review",
        "passed" if not unaudited else "failed",
        {
            "unaudited_count": len(unaudited),
            "claim_ids": [c.id for c in unaudited[:10]],
        },
    )


def _evaluate_evidence_coverage(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    classes = list(
        session.scalars(
            select(ClassModel).where(ClassModel.ontology_id == version.ontology_id)
        )
    )
    rows = list(
        session.execute(
            select(ProposalModel, EvidenceModel)
            .join(EvidenceModel, EvidenceModel.proposal_id == ProposalModel.id)
            .where(
                ProposalModel.ontology_id == version.ontology_id,
                ProposalModel.target_version_id == version.id,
                ProposalModel.status == "applied",
            )
        ).all()
    )
    covered: set[str] = set()
    for proposal, _evidence in rows:
        for item in proposal.payload.get("items", []):
            data = item.get("data") or {}
            if item.get("kind") == "entity":
                class_id = data.get("class_id")
                if class_id:
                    covered.add(class_id)
    missing = sorted({c.id for c in classes} - covered)
    return _gate(
        "evidence_coverage",
        "passed" if not missing else "failed",
        {"classes_without_evidence": missing},
    )


def _evaluate_competency_questions(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    critical = list(
        session.scalars(
            select(CompetencyQuestionModel).where(
                CompetencyQuestionModel.ontology_id == version.ontology_id,
                CompetencyQuestionModel.active.is_(True),
                CompetencyQuestionModel.importance >= CRITICAL_QUESTION_IMPORTANCE,
            )
        )
    )
    blocking = [
        {"question_id": q.id, "status": q.status}
        for q in critical
        if q.status in {"testable", "failed"}
    ]
    return _gate(
        "competency_questions",
        "passed" if not blocking else "failed",
        {"blocking_questions": blocking},
    )


def _fact_audit_summary(session: Session, version_id: str) -> dict[str, Any]:
    rows = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
                FactClaimModel.layer.in_(
                    [
                        "entity_attribute",
                        "entity_relation",
                        "inferred_inverse",
                        "value_conflict",
                    ]
                ),
            )
        )
    )
    total = len(rows)
    approved = sum(1 for r in rows if r.audit_status == "approved")
    rejected_unfixed = sum(
        1
        for r in rows
        if r.audit_status == "rejected" and not r.linked_fix_proposal_id
    )
    unaudited = sum(1 for r in rows if r.audit_status == "pending")
    accuracy = approved / total if total else 0.0
    return {
        "total": total,
        "approved": approved,
        "unaudited": unaudited,
        "rejected_unfixed": rejected_unfixed,
        "accuracy": accuracy,
    }


def _evaluate_fact_audit(
    session: Session, version: OntologyVersionModel
) -> dict[str, Any]:
    summary = _fact_audit_summary(session, version.id)
    threshold = DEFAULT_FACT_ACCURACY_THRESHOLD
    ok = (
        summary["unaudited"] == 0
        and summary["rejected_unfixed"] == 0
        and summary["accuracy"] >= threshold
    )
    return _gate(
        "fact_audit",
        "passed" if ok else "failed",
        {**summary, "accuracy_threshold": threshold},
    )


GATE_EVALUATORS = {
    "schema_validation": _evaluate_schema_validation,
    "pending_proposals": _evaluate_pending_proposals,
    "unresolved_conflicts": _evaluate_unresolved_conflicts,
    "low_confidence_review": _evaluate_low_confidence_review,
    "evidence_coverage": _evaluate_evidence_coverage,
    "competency_questions": _evaluate_competency_questions,
    "fact_audit": _evaluate_fact_audit,
}


def evaluate_readiness(
    session: Session, driver: Driver | None, version_id: str
) -> dict[str, Any]:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    gates = [GATE_EVALUATORS[name](session, version) for name in GATE_ORDER]
    _persist_gates(session, version_id, gates)
    blocking = [g["gate_type"] for g in gates if g["status"] == "failed"]
    warnings = [g["gate_type"] for g in gates if g["status"] == "warning"]
    return {
        "version_id": version_id,
        "ready": not blocking,
        "gates": gates,
        "blocking": blocking,
        "warnings": warnings,
    }


def _persist_gates(
    session: Session, version_id: str, gates: list[dict[str, Any]]
) -> None:
    existing_by_type: dict[str, PublicationGateModel] = {
        gate.gate_type: gate
        for gate in session.scalars(
            select(PublicationGateModel).where(
                PublicationGateModel.ontology_version_id == version_id
            )
        )
    }
    for gate_data in gates:
        existing = existing_by_type.get(gate_data["gate_type"])
        if existing is None:
            session.add(
                PublicationGateModel(
                    id=str(uuid.uuid4()),
                    ontology_version_id=version_id,
                    gate_type=gate_data["gate_type"],
                    status=gate_data["status"],
                    details=gate_data["details"],
                    checked_at=_now(),
                )
            )
        else:
            existing.status = gate_data["status"]
            existing.details = gate_data["details"]
            existing.checked_at = _now()
    session.commit()


def _persist_published_snapshot(
    session: Session,
    driver: Driver,
    version: OntologyVersionModel,
    readiness: dict[str, Any],
) -> None:
    from app.services.governance import _schema_snapshot

    version.schema_snapshot = _schema_snapshot(session, version.ontology_id)
    version.graph_snapshot = graph_repo.graph_version_stats(
        driver, version.ontology_id, version.id
    )
    version.publication_report = {
        "readiness": readiness,
        "fact_audit_summary": _fact_audit_summary(session, version.id),
        "published_at": _now().isoformat(),
    }
    version.workflow_status = "published"
    version.published_at = _now()


def publish_version(
    session: Session, driver: Driver, version_id: str, confirm: bool
) -> OntologyVersionModel:
    version = assert_version_mutable(session, version_id)
    readiness = evaluate_readiness(session, driver, version_id)
    if readiness["blocking"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Publication gates have not passed",
                "blocking": readiness["blocking"],
                "gates": readiness["gates"],
            },
        )
    if not confirm:
        raise HTTPException(
            status_code=428,
            detail="Publication requires explicit confirmation (confirm=true)",
        )
    _persist_published_snapshot(session, driver, version, readiness)
    version.status = VersionStatus.PUBLISHED.value
    ontology = session.get(OntologyModel, version.ontology_id)
    if ontology is not None:
        ontology.current_version_id = version.id
        ontology.status = "active"
    session.commit()
    session.refresh(version)
    return version
