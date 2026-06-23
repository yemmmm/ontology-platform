from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import ProposalCreate, ReviewDecisionCreate
from app.domain.naming import normalize_neo4j_label, normalize_neo4j_relationship_type
from app.repositories import graph as graph_repo
from app.repositories.models import (
    ClassModel,
    ConstraintModel,
    EvidenceModel,
    OntologyModel,
    OntologyVersionModel,
    ProposalModel,
    PropertyDefModel,
    PublicationGateModel,
    RelationTypeModel,
    ReviewDecisionModel,
    ValidationRunModel,
    VersionStatus,
)
from app.repositories.postgres import assert_version_mutable

ALLOWED_TRANSITIONS = {
    "proposed": {"validating"},
    "validating": {"validated", "proposed"},
    "validated": {"approved", "rejected"},
    "approved": {"applied"},
    "rejected": set(),
    "applied": set(),
}


def _id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event(action: str, **details: Any) -> dict[str, Any]:
    return {"action": action, "at": _now().isoformat(), **details}


def _transition(proposal: ProposalModel, target: str, **details: Any) -> None:
    if target not in ALLOWED_TRANSITIONS.get(proposal.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid proposal transition: {proposal.status} -> {target}",
        )
    proposal.status = target
    proposal.audit_log = [*proposal.audit_log, _event(target, **details)]


def _version(session: Session, version_id: str) -> OntologyVersionModel:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    return version


def create_draft_version(
    session: Session, ontology_id: str, parent_version_id: str | None = None
) -> OntologyVersionModel:
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    parent = None
    if parent_version_id:
        parent = _version(session, parent_version_id)
        if parent.ontology_id != ontology_id:
            raise HTTPException(status_code=400, detail="Parent version belongs to another ontology")
        if parent.status != VersionStatus.PUBLISHED.value:
            raise HTTPException(status_code=409, detail="Only a published version can have a successor")
    current_draft = session.scalar(
        select(OntologyVersionModel).where(
            OntologyVersionModel.ontology_id == ontology_id,
            OntologyVersionModel.status == VersionStatus.DRAFT.value,
        )
    )
    if current_draft is not None:
        raise HTTPException(status_code=409, detail="Ontology already has a draft version")
    number = session.scalar(
        select(func.coalesce(func.max(OntologyVersionModel.version_number), 0)).where(
            OntologyVersionModel.ontology_id == ontology_id
        )
    )
    version = OntologyVersionModel(
        id=_id(),
        ontology_id=ontology_id,
        parent_version_id=parent_version_id,
        version_number=int(number or 0) + 1,
        status=VersionStatus.DRAFT.value,
        workflow_status="gathering",
        schema_snapshot=dict(parent.schema_snapshot) if parent else {},
        graph_snapshot=dict(parent.graph_snapshot) if parent else {},
    )
    session.add(version)
    session.flush()
    ontology.current_version_id = version.id
    ontology.status = "draft"
    session.commit()
    session.refresh(version)
    return version


def list_versions(session: Session, ontology_id: str) -> list[OntologyVersionModel]:
    return list(
        session.scalars(
            select(OntologyVersionModel)
            .where(OntologyVersionModel.ontology_id == ontology_id)
            .order_by(OntologyVersionModel.version_number)
        )
    )


def create_proposal(session: Session, payload: ProposalCreate) -> ProposalModel:
    existing = session.scalar(
        select(ProposalModel).where(
            ProposalModel.project_id == payload.project_id,
            ProposalModel.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return existing
    version = assert_version_mutable(session, payload.target_version_id)
    if version.ontology_id != payload.ontology_id:
        raise HTTPException(status_code=400, detail="Target version belongs to another ontology")
    ontology = session.get(OntologyModel, payload.ontology_id)
    if ontology is None or ontology.project_id != payload.project_id:
        raise HTTPException(status_code=400, detail="Project, ontology and version do not match")
    proposal = ProposalModel(
        id=_id(),
        project_id=payload.project_id,
        ontology_id=payload.ontology_id,
        target_version_id=payload.target_version_id,
        proposal_type=payload.proposal_type,
        source_type=payload.source_type,
        idempotency_key=payload.idempotency_key,
        payload=payload.payload,
        created_by_type=payload.created_by_type,
        created_by=payload.created_by,
        model_identifier=payload.model_identifier,
        prompt_version=payload.prompt_version,
        status="proposed",
        audit_log=[_event("proposed", actor_type=payload.created_by_type)],
    )
    session.add(proposal)
    try:
        # Flush the parent first because these models intentionally avoid an ORM relationship;
        # PostgreSQL still enforces the evidence foreign key.
        session.flush()
        for item in payload.evidence:
            session.add(EvidenceModel(id=_id(), proposal_id=proposal.id, **item.model_dump()))
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(ProposalModel).where(
                ProposalModel.project_id == payload.project_id,
                ProposalModel.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is None:
            raise
        return existing
    session.refresh(proposal)
    return proposal


def _proposal(session: Session, proposal_id: str) -> ProposalModel:
    proposal = session.get(ProposalModel, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def _validate_items(proposal: ProposalModel) -> list[str]:
    items = proposal.payload.get("items")
    if not isinstance(items, list) or not items:
        return ["payload.items must be a non-empty list"]
    errors: list[str] = []
    allowed = {
        "schema_change": {"class", "property", "relation_type"},
        "constraint": {"constraint"},
        "entity": {"entity"},
        "relation": {"relation"},
        "merge": {"merge"},
    }[proposal.proposal_type]
    keys: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        if item.get("kind") not in allowed:
            errors.append(f"items[{index}].kind is invalid for {proposal.proposal_type}")
        key = item.get("key")
        if not isinstance(key, str) or not key:
            errors.append(f"items[{index}].key is required")
        elif key in keys:
            errors.append(f"duplicate item key: {key}")
        else:
            keys.add(key)
        if not isinstance(item.get("data"), dict):
            errors.append(f"items[{index}].data must be an object")
    return errors


def validate_proposal(session: Session, proposal_id: str) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    _transition(proposal, "validating")
    run = ValidationRunModel(id=_id(), proposal_id=proposal.id, status="running", errors=[], result={})
    session.add(run)
    errors = _validate_items(proposal)
    run.completed_at = _now()
    run.errors = errors
    if errors:
        run.status = "failed"
        run.result = {"valid": False}
        proposal.validation_result = {"valid": False, "errors": errors, "run_id": run.id}
        _transition(proposal, "proposed", validation_run_id=run.id, errors=errors)
    else:
        run.status = "passed"
        run.result = {"valid": True, "item_count": len(proposal.payload["items"])}
        proposal.validation_result = {"valid": True, "errors": [], "run_id": run.id}
        _transition(proposal, "validated", validation_run_id=run.id)
    session.commit()
    session.refresh(proposal)
    return proposal


def review_proposal(
    session: Session, proposal_id: str, payload: ReviewDecisionCreate
) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    _transition(proposal, payload.decision, reviewer_id=payload.reviewer_id, reason=payload.reason)
    decision = ReviewDecisionModel(
        id=_id(), proposal_id=proposal.id, **payload.model_dump()
    )
    session.add(decision)
    proposal.review_result = {
        "decision": payload.decision,
        "reviewer_type": payload.reviewer_type,
        "reviewer_id": payload.reviewer_id,
        "reason": payload.reason,
    }
    session.commit()
    session.refresh(proposal)
    return proposal


def _apply_schema(session: Session, proposal: ProposalModel) -> dict[str, Any]:
    created: dict[str, str] = {}
    classes: dict[str, ClassModel] = {}
    for item in proposal.payload["items"]:
        data = item["data"]
        if item["kind"] == "class":
            model = ClassModel(
                id=data.get("id", _id()), ontology_id=proposal.ontology_id,
                name=data["name"], normalized_label=normalize_neo4j_label(data["name"]),
                description=data.get("description"), aliases=data.get("aliases", []),
                parent_class_ids=data.get("parent_class_ids", []),
                external_mappings=data.get("external_mappings", {}),
            )
            session.add(model)
            classes[item["key"]] = model
            created[item["key"]] = model.id
    session.flush()
    for item in proposal.payload["items"]:
        data = item["data"]
        if item["kind"] == "property":
            class_id = created.get(data.get("class_key"), data.get("class_id"))
            if not class_id:
                raise ValueError(f"property {item['key']} has no class reference")
            model = PropertyDefModel(
                id=data.get("id", _id()), class_id=class_id, name=data["name"], type=data["type"],
                description=data.get("description"), required=data.get("required", False),
                multi_valued=data.get("multi_valued", False), enum_values=data.get("enum_values", []),
                constraints=data.get("constraints", {}), external_mappings=data.get("external_mappings", {}),
            )
            session.add(model)
            created[item["key"]] = model.id
        elif item["kind"] == "constraint":
            model = ConstraintModel(
                id=data.get("id", _id()), ontology_id=proposal.ontology_id,
                scope=data["scope"], kind=data["kind"], severity=data.get("severity", "error"),
                expression=data.get("expression"), config=data.get("config", {}),
            )
            session.add(model)
            created[item["key"]] = model.id
        elif item["kind"] == "relation_type":
            source_id = created.get(data.get("source_class_key"), data.get("source_class_id"))
            target_id = created.get(data.get("target_class_key"), data.get("target_class_id"))
            if not source_id or not target_id:
                raise ValueError(f"relation type {item['key']} has invalid endpoints")
            model = RelationTypeModel(
                id=data.get("id", _id()), ontology_id=proposal.ontology_id, name=data["name"],
                description=data.get("description"), aliases=data.get("aliases", []),
                parent_relation_type_id=data.get("parent_relation_type_id"),
                source_class_id=source_id, target_class_id=target_id,
                inverse_name=data.get("inverse_name"),
                normalized_type=normalize_neo4j_relationship_type(data["name"]),
                external_mappings=data.get("external_mappings", {}),
            )
            session.add(model)
            created[item["key"]] = model.id
    session.flush()
    return {"created_ids": created}


def _apply_graph(session: Session, driver: Driver, proposal: ProposalModel) -> dict[str, Any]:
    ontology = session.get(OntologyModel, proposal.ontology_id)
    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for item in proposal.payload["items"]:
        data = dict(item["data"])
        if item["kind"] == "entity":
            class_ = session.get(ClassModel, data["class_id"])
            if class_ is None or class_.ontology_id != proposal.ontology_id:
                raise ValueError(f"entity {item['key']} has invalid class")
            entities.append({
                "id": data.get("id", _id()), "project_id": proposal.project_id,
                "ontology_id": proposal.ontology_id,
                "ontology_version_id": proposal.target_version_id,
                "class_id": class_.id, "class_label": class_.normalized_label,
                "name": data["name"], "aliases": data.get("aliases", []),
                "properties": data.get("properties", {}),
                "proposal_item_key": f"{proposal.id}:{item['key']}",
            })
        elif item["kind"] == "relation":
            relation_type = session.get(RelationTypeModel, data["relation_type_id"])
            if relation_type is None or relation_type.ontology_id != proposal.ontology_id:
                raise ValueError(f"relation {item['key']} has invalid relation type")
            relations.append({
                "id": data.get("id", _id()), "project_id": ontology.project_id,
                "ontology_id": proposal.ontology_id,
                "ontology_version_id": proposal.target_version_id,
                "relation_type_id": relation_type.id,
                "relation_type": relation_type.normalized_type,
                "source_entity_id": data["source_entity_id"],
                "target_entity_id": data["target_entity_id"],
                "properties": data.get("properties", {}),
                "proposal_item_key": f"{proposal.id}:{item['key']}",
            })
    return graph_repo.apply_graph_batch(
        driver, ontology_id=proposal.ontology_id, version_id=proposal.target_version_id,
        entities=entities, relations=relations,
    )


def apply_proposal(session: Session, driver: Driver, proposal_id: str) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    if proposal.status == "applied":
        return proposal
    if proposal.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved proposals can be applied")
    try:
        if proposal.proposal_type in {"schema_change", "constraint"}:
            result = _apply_schema(session, proposal)
        elif proposal.proposal_type in {"entity", "relation"}:
            result = _apply_graph(session, driver, proposal)
        else:
            raise ValueError("Merge proposal application is not available in phase one")
        proposal.application_result = {"success": True, **result}
        proposal.applied_at = _now()
        _transition(proposal, "applied")
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=f"Proposal application failed: {exc}") from exc
    session.refresh(proposal)
    return proposal


def proposal_detail(session: Session, proposal_id: str) -> dict[str, Any]:
    proposal = _proposal(session, proposal_id)
    result = {column.name: getattr(proposal, column.name) for column in proposal.__table__.columns}
    result["evidence"] = list(
        session.scalars(select(EvidenceModel).where(EvidenceModel.proposal_id == proposal.id))
    )
    result["decisions"] = [
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
        for row in session.scalars(
            select(ReviewDecisionModel).where(ReviewDecisionModel.proposal_id == proposal.id)
        )
    ]
    result["validation_runs"] = [
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
        for row in session.scalars(
            select(ValidationRunModel).where(ValidationRunModel.proposal_id == proposal.id)
        )
    ]
    return result


def _schema_snapshot(session: Session, ontology_id: str) -> dict[str, Any]:
    classes = list(session.scalars(select(ClassModel).where(ClassModel.ontology_id == ontology_id)))
    relations = list(
        session.scalars(select(RelationTypeModel).where(RelationTypeModel.ontology_id == ontology_id))
    )
    return {
        "classes": sorted(
            [{"id": row.id, "name": row.name, "parents": row.parent_class_ids} for row in classes],
            key=lambda row: row["id"],
        ),
        "relation_types": sorted(
            [{"id": row.id, "name": row.name, "source": row.source_class_id,
              "target": row.target_class_id} for row in relations],
            key=lambda row: row["id"],
        ),
    }


def publish_version(session: Session, driver: Driver, version_id: str) -> OntologyVersionModel:
    version = assert_version_mutable(session, version_id)
    unapplied = session.scalar(
        select(func.count()).select_from(ProposalModel).where(
            ProposalModel.target_version_id == version_id,
            ProposalModel.status.in_(["validated", "approved"]),
        )
    )
    if unapplied:
        raise HTTPException(status_code=409, detail="All validated proposals must be decided and applied")
    failed_gate = session.scalar(
        select(PublicationGateModel).where(
            PublicationGateModel.ontology_version_id == version_id,
            PublicationGateModel.status != "passed",
        )
    )
    if failed_gate is not None:
        raise HTTPException(status_code=409, detail="Publication gates have not passed")
    version.schema_snapshot = _schema_snapshot(session, version.ontology_id)
    version.graph_snapshot = graph_repo.graph_version_stats(driver, version.ontology_id, version.id)
    version.status = VersionStatus.PUBLISHED.value
    version.workflow_status = "published"
    version.published_at = _now()
    ontology = session.get(OntologyModel, version.ontology_id)
    ontology.current_version_id = version.id
    ontology.status = "active"
    session.commit()
    session.refresh(version)
    return version


def version_diff(session: Session, driver: Driver, from_id: str, to_id: str) -> dict[str, Any]:
    before = _version(session, from_id)
    after = _version(session, to_id)
    if before.ontology_id != after.ontology_id:
        raise HTTPException(status_code=400, detail="Versions belong to different ontologies")
    before_schema = (
        _schema_snapshot(session, before.ontology_id)
        if before.status == VersionStatus.DRAFT.value else before.schema_snapshot
    )
    after_schema = (
        _schema_snapshot(session, after.ontology_id)
        if after.status == VersionStatus.DRAFT.value else after.schema_snapshot
    )
    before_graph = (
        graph_repo.graph_version_stats(driver, before.ontology_id, before.id)
        if before.status == VersionStatus.DRAFT.value else before.graph_snapshot
    )
    after_graph = (
        graph_repo.graph_version_stats(driver, after.ontology_id, after.id)
        if after.status == VersionStatus.DRAFT.value else after.graph_snapshot
    )
    def ids(snapshot: dict[str, Any], key: str) -> set[str]:
        return {item["id"] for item in snapshot.get(key, [])}
    schema: dict[str, Any] = {}
    for key in ("classes", "relation_types"):
        old, new = ids(before_schema, key), ids(after_schema, key)
        schema[key] = {"added": sorted(new - old), "removed": sorted(old - new)}
    graph_keys = set(before_graph) | set(after_graph)
    graph = {
        key: {"from": before_graph.get(key, 0), "to": after_graph.get(key, 0),
              "delta": after_graph.get(key, 0) - before_graph.get(key, 0)}
        for key in sorted(graph_keys)
        if isinstance(before_graph.get(key, 0), int)
        and isinstance(after_graph.get(key, 0), int)
    }
    for key in ("entities_by_class", "relations_by_type"):
        old_counts = before_graph.get(key, {})
        new_counts = after_graph.get(key, {})
        graph[key] = {
            item_id: {
                "from": old_counts.get(item_id, 0),
                "to": new_counts.get(item_id, 0),
                "delta": new_counts.get(item_id, 0) - old_counts.get(item_id, 0),
            }
            for item_id in sorted(set(old_counts) | set(new_counts))
        }
    return {"from_version_id": from_id, "to_version_id": to_id, "schema": schema, "graph": graph}
