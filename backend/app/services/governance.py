from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ProposalBatchReview,
    ProposalCreate,
    ProposalItemReview,
    ReviewDecisionCreate,
)
from app.domain.naming import normalize_neo4j_label, normalize_neo4j_relationship_type
from app.repositories import graph as graph_repo
from app.repositories.models import (
    ClassModel,
    CompetencyQuestionModel,
    ConstraintModel,
    EvidenceModel,
    KnowledgeConflictModel,
    OntologyModel,
    OntologyVersionModel,
    ProposalModel,
    PropertyDefModel,
    RelationTypeModel,
    ReviewDecisionModel,
    ReviewBatchModel,
    SourceChunkModel,
    SourceDocumentModel,
    ValidationRunModel,
    VersionStatus,
)
from app.repositories.postgres import assert_version_mutable
from app.services import facts as facts_service
from app.services import interview as interview_service

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
    _validate_evidence_payload(session, payload)
    evidence_rows = [EvidenceModel(id=_id(), proposal_id="", **item.model_dump()) for item in payload.evidence]
    proposal_payload = dict(payload.payload)
    if evidence_rows:
        proposal_items: list[Any] = []
        for raw_item in proposal_payload.get("items", []):
            if not isinstance(raw_item, dict):
                proposal_items.append(raw_item)
                continue
            item = dict(raw_item)
            indexes = item.pop("evidence_indexes", None)
            if indexes is None:
                item["evidence_ids"] = [row.id for row in evidence_rows]
            elif isinstance(indexes, list):
                item["evidence_ids"] = [
                    evidence_rows[index].id
                    for index in indexes
                    if isinstance(index, int) and 0 <= index < len(evidence_rows)
                ]
            proposal_items.append(item)
        proposal_payload = {**proposal_payload, "items": proposal_items}
    proposal = ProposalModel(
        id=_id(),
        project_id=payload.project_id,
        ontology_id=payload.ontology_id,
        target_version_id=payload.target_version_id,
        proposal_type=payload.proposal_type,
        source_type=payload.source_type,
        idempotency_key=payload.idempotency_key,
        payload=proposal_payload,
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
        for evidence in evidence_rows:
            evidence.proposal_id = proposal.id
            session.add(evidence)
        if payload.proposal_type in {"schema_change", "constraint", "entity", "relation", "merge"}:
            keys = [
                item.get("key")
                for item in payload.payload.get("items", [])
                if isinstance(item, dict) and item.get("key")
            ]
            session.add(
                ReviewBatchModel(
                    id=_id(),
                    stable_key=f"proposal:{proposal.id}",
                    project_id=payload.project_id,
                    ontology_id=payload.ontology_id,
                    ontology_version_id=payload.target_version_id,
                    review_type="schema" if payload.proposal_type in {"schema_change", "constraint"} else payload.proposal_type,
                    status="pending",
                    item_ids=keys,
                    counts={"pending": len(keys), "approved": 0, "rejected": 0, "modified": 0},
                )
            )
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


def _validate_evidence_payload(session: Session, payload: ProposalCreate) -> None:
    if payload.proposal_type in {"entity", "relation"} and not payload.evidence:
        raise HTTPException(
            status_code=422,
            detail="Entity and relation proposals require document or user-statement evidence",
        )
    for index, evidence in enumerate(payload.evidence):
        if evidence.char_end is not None and evidence.char_start is not None and evidence.char_end <= evidence.char_start:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] has an invalid character range")
        if evidence.source_type != "document":
            continue
        if not evidence.document_id or not evidence.chunk_id:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] must identify a document and chunk")
        document = session.get(SourceDocumentModel, evidence.document_id)
        chunk = session.get(SourceChunkModel, evidence.chunk_id)
        if document is None or chunk is None or chunk.document_id != document.id:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] does not identify a valid source chunk")
        if document.project_id != payload.project_id:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] belongs to another project")
        if evidence.page_number != chunk.page_number:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] page does not match its source chunk")
        if evidence.char_start is None or evidence.char_end is None:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] requires a character range")
        if evidence.char_start < chunk.char_start or evidence.char_end > chunk.char_end:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] range is outside its source chunk")
        relative_start = evidence.char_start - chunk.char_start
        relative_end = evidence.char_end - chunk.char_start
        source_quote = chunk.text[relative_start:relative_end]
        if source_quote != evidence.quote or evidence.content_hash != chunk.content_hash:
            raise HTTPException(status_code=422, detail=f"evidence[{index}] quote or hash does not match the source chunk")


def _proposal(session: Session, proposal_id: str) -> ProposalModel:
    proposal = session.get(ProposalModel, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


PROPERTY_TYPES = {"string", "number", "boolean", "date", "enum", "reference", "json"}


def _item_ref(data: dict[str, Any], key_name: str, id_name: str, created: dict[str, str]) -> str | None:
    return created.get(data.get(key_name), data.get(id_name))


def _schema_validation(session: Session, proposal: ProposalModel) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    ambiguities: list[dict[str, Any]] = []
    items = proposal.payload.get("items", [])
    has_evidence = bool(
        session.scalar(
            select(func.count()).select_from(EvidenceModel).where(EvidenceModel.proposal_id == proposal.id)
        )
    )
    has_question_source = any(
        isinstance(item, dict) and bool(item.get("competency_question_ids")) for item in items
    )
    if not has_evidence and not has_question_source:
        errors.append("schema proposal must cite evidence or competency questions")
    current_classes = list(
        session.scalars(select(ClassModel).where(ClassModel.ontology_id == proposal.ontology_id))
    )
    current_relations = list(
        session.scalars(
            select(RelationTypeModel).where(RelationTypeModel.ontology_id == proposal.ontology_id)
        )
    )
    current_properties = list(
        session.scalars(
            select(PropertyDefModel).where(
                PropertyDefModel.class_id.in_([row.id for row in current_classes])
            )
        )
    ) if current_classes else []
    class_ids = {row.id for row in current_classes}
    class_names = {row.name.casefold() for row in current_classes}
    relation_ids = {row.id for row in current_relations}
    relation_names = {row.name.casefold() for row in current_relations}
    class_keys: dict[str, str] = {}
    relation_keys: dict[str, str] = {}
    proposed_names: set[tuple[str, str]] = set()

    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
            continue
        kind, key, data = item.get("kind"), item.get("key"), item["data"]
        if item.get("review_status") == "rejected" or item.get("merged_into_key"):
            continue
        if kind == "constraint":
            if not data.get("scope") or not data.get("kind"):
                errors.append(f"constraint {key} requires scope and kind")
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"items[{index}].data.name is required")
            continue
        normalized_name = name.casefold()
        if kind == "property":
            owner = data.get("class_key") or data.get("class_id") or "missing"
            name_scope = f"property:{owner}"
        else:
            name_scope = "class" if kind == "class" else "relation"
        if (name_scope, normalized_name) in proposed_names:
            errors.append(f"duplicate {kind} definition: {name}")
        proposed_names.add((name_scope, normalized_name))
        if kind == "class":
            if normalized_name in class_names:
                errors.append(f"class name conflicts with existing class: {name}")
            class_keys[key] = data.get("id", f"proposal:{key}")
            if data.get("instance_like") or (data.get("properties") or {}).get("unique_identity"):
                ambiguities.append({"item_key": key, "kind": "class_or_entity", "message": f"Review whether {name} is a Class or Entity"})
        elif kind == "relation_type":
            if normalized_name in relation_names:
                errors.append(f"relation type name conflicts with existing definition: {name}")
            relation_keys[key] = data.get("id", f"proposal:{key}")
        elif kind == "property" and data.get("object_like"):
            ambiguities.append({"item_key": key, "kind": "property_or_relation", "message": f"Review whether {name} is a Property or RelationType"})

    known_classes = class_ids | set(class_keys.values())
    known_relations = relation_ids | set(relation_keys.values())
    parent_graph: dict[str, list[str]] = {
        row.id: list(row.parent_class_ids or []) for row in current_classes
    }
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
            continue
        if item.get("review_status") == "rejected" or item.get("merged_into_key"):
            continue
        kind, key, data = item.get("kind"), item.get("key"), item["data"]
        if kind == "class":
            node_id = class_keys.get(key)
            parents = [class_keys.get(parent, parent) for parent in data.get("parent_class_keys", [])]
            parents += data.get("parent_class_ids", [])
            invalid = [parent for parent in parents if parent not in known_classes]
            if invalid:
                errors.append(f"class {key} has invalid or cross-ontology parents: {', '.join(invalid)}")
            parent_graph[node_id] = parents
        elif kind == "property":
            class_id = _item_ref(data, "class_key", "class_id", class_keys)
            if class_id not in known_classes:
                errors.append(f"property {key} has invalid or cross-ontology domain")
            if any(
                row.class_id == class_id and row.name.casefold() == str(data.get("name", "")).casefold()
                for row in current_properties
            ):
                errors.append(
                    f"property name conflicts with existing definition on class {class_id}: {data.get('name')}"
                )
            if data.get("type") not in PROPERTY_TYPES:
                errors.append(f"property {key} has unsupported type: {data.get('type')}")
            if data.get("type") == "enum" and not data.get("enum_values"):
                errors.append(f"property {key} enum_values must not be empty")
            if data.get("type") == "reference":
                range_id = _item_ref(data, "range_class_key", "range_class_id", class_keys)
                if range_id not in known_classes:
                    errors.append(f"property {key} has invalid or cross-ontology range")
        elif kind == "relation_type":
            source = _item_ref(data, "source_class_key", "source_class_id", class_keys)
            target = _item_ref(data, "target_class_key", "target_class_id", class_keys)
            if source not in known_classes or target not in known_classes:
                errors.append(f"relation type {key} has invalid or cross-ontology endpoints")
            parent = _item_ref(data, "parent_relation_type_key", "parent_relation_type_id", relation_keys)
            if parent is not None and parent not in known_relations:
                errors.append(f"relation type {key} has invalid or cross-ontology parent relation")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        cyclic = any(visit(parent) for parent in parent_graph.get(node, []) if parent in parent_graph)
        visiting.remove(node)
        visited.add(node)
        return cyclic
    if any(visit(node) for node in list(parent_graph)):
        errors.append("class inheritance cycle detected")
    return errors, ambiguities


def _knowledge_validation(
    session: Session, proposal: ProposalModel, driver: Driver | None
) -> tuple[list[str], list[dict[str, Any]]]:
    from app.services.graph import validate_entity_properties

    errors: list[str] = []
    ambiguities: list[dict[str, Any]] = []
    evidence_ids = set(
        session.scalars(select(EvidenceModel.id).where(EvidenceModel.proposal_id == proposal.id))
    )
    classes = {
        row.id: row
        for row in session.scalars(select(ClassModel).where(ClassModel.ontology_id == proposal.ontology_id))
    }
    relation_types = {
        row.id: row
        for row in session.scalars(
            select(RelationTypeModel).where(RelationTypeModel.ontology_id == proposal.ontology_id)
        )
    }
    seen_entities: dict[tuple[str, str], str] = {}
    session.query(KnowledgeConflictModel).filter(
        KnowledgeConflictModel.proposal_id == proposal.id
    ).delete(synchronize_session=False)
    conflicts: list[KnowledgeConflictModel] = []
    for index, item in enumerate(proposal.payload.get("items", [])):
        data = item["data"]
        item_evidence = set(item.get("evidence_ids", []))
        if proposal.proposal_type in {"entity", "relation"} and not item_evidence.intersection(evidence_ids):
            errors.append(f"items[{index}] must bind at least one valid evidence record")
        confidence = data.get("confidence")
        if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            errors.append(f"items[{index}].data.confidence must be between 0 and 1")
        if item["kind"] == "entity":
            class_ = classes.get(data.get("class_id"))
            if class_ is None:
                errors.append(f"entity {item['key']} has an invalid or cross-ontology class")
                continue
            if not isinstance(data.get("name"), str) or not data["name"].strip():
                errors.append(f"entity {item['key']} requires a canonical name")
                continue
            identity = (class_.id, data["name"].strip().casefold())
            if identity in seen_entities:
                ambiguities.append(
                    {"kind": "duplicate_candidate", "item_key": item["key"], "matches_item_key": seen_entities[identity]}
                )
            else:
                seen_entities[identity] = item["key"]
            try:
                validate_entity_properties(class_, classes, data.get("properties", {}))
            except HTTPException as exc:
                errors.append(f"entity {item['key']}: {exc.detail}")
            if driver is not None:
                matches = graph_repo.search_entity_nodes(
                    driver, proposal.project_id, proposal.ontology_id, data["name"], class_.id, 10
                )
                exact = [row for row in matches if row["name"].casefold() == data["name"].casefold()]
                for match in exact:
                    ambiguities.append(
                        {"kind": "existing_entity_match", "item_key": item["key"], "entity_id": match["id"], "requires_merge_review": True}
                    )
                    for field, proposed_value in data.get("properties", {}).items():
                        existing_value = match.get("properties", {}).get(field)
                        if existing_value is not None and existing_value != proposed_value:
                            conflicts.append(
                                KnowledgeConflictModel(
                                    id=_id(), project_id=proposal.project_id,
                                    ontology_id=proposal.ontology_id, proposal_id=proposal.id,
                                    item_key=item["key"], field=field,
                                    existing_value=existing_value, proposed_value=proposed_value,
                                    status="pending", resolution={},
                                )
                            )
        elif item["kind"] == "relation":
            relation_type = relation_types.get(data.get("relation_type_id"))
            if relation_type is None:
                errors.append(f"relation {item['key']} has an invalid or cross-ontology relation type")
                continue
            if not data.get("source_entity_id") or not data.get("target_entity_id"):
                errors.append(f"relation {item['key']} requires source and target entities")
            elif driver is not None:
                source = graph_repo.get_entity_node(driver, data["source_entity_id"], proposal.project_id, proposal.ontology_id)
                target = graph_repo.get_entity_node(driver, data["target_entity_id"], proposal.project_id, proposal.ontology_id)
                if source is None or target is None:
                    errors.append(f"relation {item['key']} references a missing entity")
                elif source["class_id"] != relation_type.source_class_id or target["class_id"] != relation_type.target_class_id:
                    errors.append(f"relation {item['key']} endpoints do not match its relation type")
        elif item["kind"] == "merge":
            source_id, target_id = data.get("source_entity_id"), data.get("target_entity_id")
            if not source_id or not target_id or source_id == target_id:
                errors.append(f"merge {item['key']} requires two distinct entities")
            elif driver is not None:
                source = graph_repo.get_entity_node(driver, source_id, proposal.project_id, proposal.ontology_id)
                target = graph_repo.get_entity_node(driver, target_id, proposal.project_id, proposal.ontology_id)
                if source is None or target is None:
                    errors.append(f"merge {item['key']} references a missing entity")
                elif source["class_id"] != target["class_id"]:
                    errors.append(f"merge {item['key']} entities must have the same class")
    session.add_all(conflicts)
    if conflicts:
        ambiguities.extend(
            {"kind": "value_conflict", "conflict_id": row.id, "item_key": row.item_key, "field": row.field}
            for row in conflicts
        )
        batch = session.scalar(
            select(ReviewBatchModel).where(ReviewBatchModel.stable_key == f"conflict:{proposal.id}")
        )
        if batch is None:
            batch = ReviewBatchModel(
                id=_id(), stable_key=f"conflict:{proposal.id}", project_id=proposal.project_id,
                ontology_id=proposal.ontology_id, ontology_version_id=proposal.target_version_id,
                review_type="conflict", status="pending", item_ids=[row.id for row in conflicts],
                counts={"pending": len(conflicts), "approved": 0, "rejected": 0, "modified": 0},
            )
            session.add(batch)
        else:
            batch.item_ids = [row.id for row in conflicts]
            batch.status = "pending"
            batch.counts = {"pending": len(conflicts), "approved": 0, "rejected": 0, "modified": 0}
    return errors, ambiguities


def _validate_items(
    session: Session, proposal: ProposalModel, driver: Driver | None = None
) -> tuple[list[str], list[dict[str, Any]]]:
    items = proposal.payload.get("items")
    if not isinstance(items, list) or not items:
        return ["payload.items must be a non-empty list"], []
    errors: list[str] = []
    allowed = {
        "schema_change": {"class", "property", "relation_type", "constraint"},
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
    ambiguities: list[dict[str, Any]] = []
    if proposal.proposal_type in {"schema_change", "constraint"} and not errors:
        schema_errors, ambiguities = _schema_validation(session, proposal)
        errors.extend(schema_errors)
    elif proposal.proposal_type in {"entity", "relation", "merge"} and not errors:
        graph_errors, graph_ambiguities = _knowledge_validation(session, proposal, driver)
        errors.extend(graph_errors)
        ambiguities.extend(graph_ambiguities)
    return errors, ambiguities


def validate_proposal(
    session: Session, proposal_id: str, driver: Driver | None = None
) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    _transition(proposal, "validating")
    run = ValidationRunModel(id=_id(), proposal_id=proposal.id, status="running", errors=[], result={})
    session.add(run)
    errors, ambiguities = _validate_items(session, proposal, driver)
    run.completed_at = _now()
    run.errors = errors
    if errors:
        run.status = "failed"
        run.result = {"valid": False, "ambiguities": ambiguities}
        proposal.validation_result = {"valid": False, "errors": errors, "ambiguities": ambiguities, "run_id": run.id}
        _transition(proposal, "proposed", validation_run_id=run.id, errors=errors)
    else:
        run.status = "passed"
        run.result = {"valid": True, "item_count": len(proposal.payload["items"]), "ambiguities": ambiguities}
        proposal.validation_result = {"valid": True, "errors": [], "ambiguities": ambiguities, "run_id": run.id}
        _transition(proposal, "validated", validation_run_id=run.id)
    session.commit()
    session.refresh(proposal)
    return proposal


def review_proposal(
    session: Session, proposal_id: str, payload: ReviewDecisionCreate
) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    if payload.decision == "approved" and proposal.proposal_type in {"entity", "relation", "merge"}:
        pending_conflicts = session.scalar(
            select(func.count()).select_from(KnowledgeConflictModel).where(
                KnowledgeConflictModel.proposal_id == proposal.id,
                KnowledgeConflictModel.status == "pending",
            )
        )
        if pending_conflicts:
            raise HTTPException(
                status_code=409,
                detail="All knowledge conflicts must be resolved before approval",
            )
    if payload.decision == "approved" and proposal.proposal_type in {"schema_change", "constraint"}:
        pending = [
            item.get("key")
            for item in proposal.payload.get("items", [])
            if item.get("review_status", "pending") == "pending"
        ]
        if pending:
            raise HTTPException(
                status_code=409,
                detail=f"All schema items must be reviewed before approval: {', '.join(pending)}",
            )
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


def _review_batch(session: Session, proposal_id: str) -> ReviewBatchModel | None:
    return session.scalar(
        select(ReviewBatchModel).where(ReviewBatchModel.stable_key == f"proposal:{proposal_id}")
    )


def _refresh_review_batch(batch: ReviewBatchModel, items: list[dict[str, Any]]) -> None:
    counts = {"pending": 0, "approved": 0, "rejected": 0, "modified": 0}
    for item in items:
        state = item.get("review_status", "pending")
        counts[state if state in {"approved", "rejected"} else "pending"] += 1
        if item.get("modified"):
            counts["modified"] += 1
    batch.counts = counts
    decided = counts["approved"] + counts["rejected"]
    batch.status = "completed" if decided == len(items) else "in_review" if decided else "pending"


def review_proposal_item(
    session: Session, proposal_id: str, item_key: str, payload: ProposalItemReview
) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    assert_version_mutable(session, proposal.target_version_id)
    if proposal.proposal_type not in {"schema_change", "constraint", "entity", "relation", "merge"}:
        raise HTTPException(status_code=409, detail="Item review is not supported for this proposal")
    if proposal.status not in {"proposed", "validated"}:
        raise HTTPException(status_code=409, detail="Proposal is not editable in its current state")
    items = [dict(item) for item in proposal.payload.get("items", [])]
    target = next((item for item in items if item.get("key") == item_key), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Proposal item not found")
    if payload.action == "edited":
        if payload.data is None:
            raise HTTPException(status_code=422, detail="Edited items require data")
        target["data"] = payload.data
        target["modified"] = True
        target["review_status"] = "pending"
        target.pop("merged_into_key", None)
    elif payload.action == "merged":
        destination = next(
            (item for item in items if item.get("key") == payload.merge_into_key), None
        )
        if destination is None or destination is target:
            raise HTTPException(status_code=422, detail="merge_into_key must identify another item")
        if destination.get("kind") != target.get("kind"):
            raise HTTPException(status_code=422, detail="Only items of the same kind can be merged")
        target["review_status"] = "rejected"
        target["merged_into_key"] = payload.merge_into_key
        target["modified"] = True
    else:
        target["review_status"] = payload.action
    target["review"] = {
        "action": payload.action,
        "reviewer_type": payload.reviewer_type,
        "reviewer_id": payload.reviewer_id,
        "reason": payload.reason,
        "at": _now().isoformat(),
    }
    proposal.payload = {**proposal.payload, "items": items}
    if proposal.status == "validated" and payload.action in {"edited", "merged"}:
        proposal.status = "proposed"
        proposal.validation_result = {}
    proposal.audit_log = [*proposal.audit_log, _event("item_reviewed", item_key=item_key, review_action=payload.action)]
    batch = _review_batch(session, proposal.id)
    if batch:
        _refresh_review_batch(batch, items)
    session.commit()
    session.refresh(proposal)
    return proposal


def batch_review_proposal_items(
    session: Session, proposal_id: str, payload: ProposalBatchReview
) -> ProposalModel:
    proposal = _proposal(session, proposal_id)
    item_keys = {item.get("key") for item in proposal.payload.get("items", [])}
    missing = sorted(set(payload.item_keys) - item_keys)
    if missing:
        raise HTTPException(status_code=404, detail=f"Proposal items not found: {', '.join(missing)}")
    for item_key in payload.item_keys:
        proposal = review_proposal_item(
            session,
            proposal_id,
            item_key,
            ProposalItemReview(
                action=payload.action,
                reviewer_type=payload.reviewer_type,
                reviewer_id=payload.reviewer_id,
                reason=payload.reason,
            ),
        )
    return proposal


def list_proposals(
    session: Session, ontology_id: str, proposal_type: str | None = None
) -> list[dict[str, Any]]:
    statement = select(ProposalModel).where(ProposalModel.ontology_id == ontology_id)
    if proposal_type:
        statement = statement.where(ProposalModel.proposal_type == proposal_type)
    statement = statement.order_by(ProposalModel.created_at.desc())
    return [proposal_detail(session, row.id) for row in session.scalars(statement)]


def list_version_proposals(session: Session, version_id: str) -> list[ProposalModel]:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    return list(
        session.scalars(
            select(ProposalModel)
            .where(ProposalModel.target_version_id == version_id)
            .order_by(ProposalModel.created_at)
        )
    )


def list_review_batches(session: Session, ontology_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ReviewBatchModel)
        .where(ReviewBatchModel.ontology_id == ontology_id)
        .order_by(ReviewBatchModel.created_at.desc())
    )
    return [
        review_batch_detail(row)
        for row in rows
    ]


def review_batch_detail(row: ReviewBatchModel) -> dict[str, Any]:
    return {
        **{column.name: getattr(row, column.name) for column in row.__table__.columns},
        "deep_link": (
            f"/?project={row.project_id}&ontology={row.ontology_id}"
            f"&tab={'schema-review' if row.review_type == 'schema' else 'graph-review'}"
            f"&batch={row.id}"
        ),
    }


def get_review_batch(session: Session, review_batch_id: str) -> dict[str, Any]:
    row = session.get(ReviewBatchModel, review_batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review batch not found")
    return review_batch_detail(row)


def _apply_schema(session: Session, proposal: ProposalModel) -> dict[str, Any]:
    created: dict[str, str] = {}
    classes: dict[str, ClassModel] = {}
    for item in proposal.payload["items"]:
        if item.get("review_status") == "rejected" or item.get("merged_into_key"):
            continue
        data = item["data"]
        if item["kind"] == "class":
            model = ClassModel(
                id=data.get("id", _id()), ontology_id=proposal.ontology_id,
                name=data["name"], normalized_label=normalize_neo4j_label(data["name"]),
                description=data.get("description"), aliases=data.get("aliases", []),
                parent_class_ids=[
                    created.get(parent, parent)
                    for parent in data.get("parent_class_keys", []) + data.get("parent_class_ids", [])
                ],
                external_mappings=data.get("external_mappings", {}),
            )
            session.add(model)
            classes[item["key"]] = model
            created[item["key"]] = model.id
    session.flush()
    for item in proposal.payload["items"]:
        if item.get("review_status") == "rejected" or item.get("merged_into_key"):
            continue
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
                parent_relation_type_id=created.get(
                    data.get("parent_relation_type_key"), data.get("parent_relation_type_id")
                ),
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


def _apply_merges(driver: Driver, proposal: ProposalModel) -> dict[str, Any]:
    merged = [
            {"source_entity_id": data["source_entity_id"], "target_entity_id": data["target_entity_id"]}
        for item in proposal.payload["items"]
        for data in [item["data"]]
    ]
    graph_repo.merge_entity_batch(
        driver, project_id=proposal.project_id, ontology_id=proposal.ontology_id, merges=merged
    )
    return {"merged": merged}


def _revalidate_affected_graph(session: Session, driver: Driver, ontology_id: str) -> dict[str, Any]:
    """Report incompatibilities after schema changes without mutating graph data."""
    from app.services.graph import validate_entity_properties

    graph = graph_repo.inspect_ontology_graph(driver, ontology_id)
    classes = list(session.scalars(select(ClassModel).where(ClassModel.ontology_id == ontology_id)))
    by_id = {row.id: row for row in classes}
    relation_types = {
        row.id: row
        for row in session.scalars(
            select(RelationTypeModel).where(RelationTypeModel.ontology_id == ontology_id)
        )
    }
    issues: list[dict[str, str]] = []
    entity_classes: dict[str, str] = {}
    for entity in graph["entities"]:
        entity_classes[entity["id"]] = entity["class_id"]
        class_ = by_id.get(entity["class_id"])
        if class_ is None:
            issues.append({"kind": "invalid_entity_class", "graph_id": entity["id"]})
            continue
        try:
            validate_entity_properties(class_, by_id, entity.get("properties", {}))
        except HTTPException as exc:
            issues.append({"kind": "invalid_entity_properties", "graph_id": entity["id"], "detail": str(exc.detail)})
    for relation in graph["relations"]:
        relation_type = relation_types.get(relation["relation_type_id"])
        if relation_type is None:
            issues.append({"kind": "invalid_relation_type", "graph_id": relation["id"]})
            continue
        if (
            entity_classes.get(relation.get("source_entity_id")) != relation_type.source_class_id
            or entity_classes.get(relation.get("target_entity_id")) != relation_type.target_class_id
        ):
            issues.append({"kind": "invalid_relation_endpoint", "graph_id": relation["id"]})
    return {
        "checked_entities": len(graph["entities"]),
        "checked_relations": len(graph["relations"]),
        "compatible": not issues,
        "issues": issues,
        "deleted": 0,
    }


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
            result["graph_revalidation"] = _revalidate_affected_graph(
                session, driver, proposal.ontology_id
            )
        elif proposal.proposal_type in {"entity", "relation"}:
            result = _apply_graph(session, driver, proposal)
        elif proposal.proposal_type == "merge":
            result = _apply_merges(driver, proposal)
        else:
            raise ValueError("Unsupported proposal type")
        proposal.application_result = {"success": True, **result}
        proposal.applied_at = _now()
        _transition(proposal, "applied")
        session.commit()
        _notify_graph_change(session, proposal)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=f"Proposal application failed: {exc}") from exc
    session.refresh(proposal)
    return proposal


def _notify_graph_change(session: Session, proposal: ProposalModel) -> None:
    """Knock stale any facts or competency questions whose graph data changed."""
    entity_ids: set[str] = set()
    relation_ids: set[str] = set()
    for item in proposal.payload.get("items", []):
        data = item.get("data") or {}
        if item.get("kind") == "entity":
            if data.get("id"):
                entity_ids.add(data["id"])
        elif item.get("kind") == "relation":
            if data.get("id"):
                relation_ids.add(data["id"])
            entity_ids.update(
                filter(None, [data.get("source_entity_id"), data.get("target_entity_id")])
            )
        elif item.get("kind") == "merge":
            entity_ids.update(
                filter(None, [data.get("source_entity_id"), data.get("target_entity_id")])
            )
    facts_service.invalidate_for_graph_change(
        session, proposal.ontology_id, proposal.target_version_id, entity_ids, relation_ids
    )
    questions = session.scalars(
        select(CompetencyQuestionModel).where(
            CompetencyQuestionModel.project_id == proposal.project_id
        )
    )
    interview_service.invalidate_questions_for_graph_change(list(questions), entity_ids)


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
    result["conflicts"] = [
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
        for row in session.scalars(
            select(KnowledgeConflictModel).where(KnowledgeConflictModel.proposal_id == proposal.id)
        )
    ]
    return result


def list_conflicts(session: Session, ontology_id: str) -> list[KnowledgeConflictModel]:
    return list(
        session.scalars(
            select(KnowledgeConflictModel)
            .where(KnowledgeConflictModel.ontology_id == ontology_id)
            .order_by(KnowledgeConflictModel.created_at.desc())
        )
    )


def resolve_conflict(
    session: Session, conflict_id: str, action: str, value: Any, reviewer_id: str | None
) -> KnowledgeConflictModel:
    conflict = session.get(KnowledgeConflictModel, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Knowledge conflict not found")
    if conflict.status != "pending":
        return conflict
    if action == "manual" and value is None:
        raise HTTPException(status_code=422, detail="Manual conflict resolution requires a value")
    conflict.status = "resolved"
    conflict.resolution = {
        "action": action,
        "value": value,
        "reviewer_id": reviewer_id,
        "resolved_at": _now().isoformat(),
    }
    batch = session.scalar(
        select(ReviewBatchModel).where(ReviewBatchModel.stable_key == f"conflict:{conflict.proposal_id}")
    )
    session.flush()
    if batch is not None:
        pending = session.scalar(
            select(func.count()).select_from(KnowledgeConflictModel).where(
                KnowledgeConflictModel.proposal_id == conflict.proposal_id,
                KnowledgeConflictModel.status == "pending",
            )
        )
        total = len(batch.item_ids)
        batch.counts = {"pending": int(pending or 0), "approved": total - int(pending or 0), "rejected": 0, "modified": 0}
        batch.status = "completed" if not pending else "in_review"
    session.commit()
    session.refresh(conflict)
    return conflict


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


def publish_version(
    session: Session, driver: Driver, version_id: str, confirm: bool = False
) -> OntologyVersionModel:
    from app.services import publication as publication_service

    return publication_service.publish_version(session, driver, version_id, confirm=confirm)


def get_publication_readiness(
    session: Session, driver: Driver, version_id: str
) -> dict[str, Any]:
    from app.services import publication as publication_service

    return publication_service.evaluate_readiness(session, driver, version_id)


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
