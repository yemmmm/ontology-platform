"""Deterministic Fact Claim generation, sampling and audit for v0.3 phase 5."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from neo4j import Driver
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories import graph as graph_repo
from app.repositories.models import (
    EvidenceModel,
    FactClaimModel,
    KnowledgeConflictModel,
    OntologyModel,
    OntologyVersionModel,
    ProposalModel,
    RelationTypeModel,
    VersionStatus,
)

LOW_CONFIDENCE_THRESHOLD = 0.7


def _id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_value(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _graph_snapshot(driver: Driver, ontology_id: str, version_id: str) -> dict[str, list[dict[str, Any]]]:
    raw = graph_repo.inspect_ontology_graph(driver, ontology_id)
    return {
        "entities": [e for e in raw["entities"] if e.get("ontology_version_id") == version_id],
        "relations": [r for r in raw["relations"] if r.get("ontology_version_id") == version_id],
    }


def _item_entity_ids(item: dict[str, Any]) -> list[str]:
    data = item.get("data") or {}
    if item.get("kind") == "entity":
        candidate = data.get("id")
        return [candidate] if candidate else []
    if item.get("kind") == "relation":
        return [data.get("source_entity_id"), data.get("target_entity_id")]
    return []


def _entity_evidence_index(
    session: Session, ontology_id: str, version_id: str
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    rows = list(
        session.execute(
            select(ProposalModel, EvidenceModel)
            .join(EvidenceModel, EvidenceModel.proposal_id == ProposalModel.id)
            .where(
                ProposalModel.ontology_id == ontology_id,
                ProposalModel.target_version_id == version_id,
                ProposalModel.status == "applied",
            )
        ).all()
    )
    for proposal, evidence in rows:
        for item in proposal.payload.get("items", []):
            for entity_id in _item_entity_ids(item):
                if entity_id:
                    index.setdefault(entity_id, []).append(evidence.id)
    return index


def _claim_key(layer: str, subject_id: str, predicate: str, value_hash: str) -> str:
    return f"{layer}:{subject_id}:{predicate}:{value_hash}"


def _attribute_fact(
    version_id: str,
    project_id: str,
    ontology_id: str,
    entity: dict[str, Any],
    name: str,
    value: Any,
    evidence_ids: list[str],
) -> FactClaimModel:
    subject_id = entity["id"]
    return FactClaimModel(
        id=_id(),
        claim_key=_claim_key("entity_attribute", subject_id, name, _hash_value(value)),
        project_id=project_id,
        ontology_id=ontology_id,
        ontology_version_id=version_id,
        claim_type="direct",
        layer="entity_attribute",
        subject={
            "entity_id": subject_id,
            "name": entity.get("name"),
            "class_id": entity.get("class_id"),
        },
        predicate=name,
        value=value,
        graph_path=[{"node": subject_id, "kind": "entity"}],
        evidence_ids=evidence_ids,
        generation_reason="entity_property",
        confidence=1.0,
    )


def _relation_fact(
    version_id: str,
    project_id: str,
    ontology_id: str,
    relation: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    evidence_ids: list[str],
    confidence: float,
    *,
    claim_type: str = "direct",
    layer: str = "entity_relation",
    reason: str = "direct_relation",
    predicate_override: str | None = None,
) -> FactClaimModel:
    predicate = predicate_override or relation.get("relation_type") or "RELATED_TO"
    value = {"target_entity_id": target["id"], "target_name": target.get("name")}
    return FactClaimModel(
        id=_id(),
        claim_key=_claim_key(layer, source["id"], predicate, _hash_value(value)),
        project_id=project_id,
        ontology_id=ontology_id,
        ontology_version_id=version_id,
        claim_type=claim_type,
        layer=layer,
        subject={
            "entity_id": source["id"],
            "name": source.get("name"),
            "class_id": source.get("class_id"),
        },
        predicate=predicate,
        value=value,
        graph_path=[
            {"node": source["id"], "kind": "entity"},
            {"edge": relation.get("id"), "type": relation.get("relation_type")},
            {"node": target["id"], "kind": "entity"},
        ],
        evidence_ids=evidence_ids,
        generation_reason=reason,
        confidence=confidence,
    )


def _conflict_facts(
    session: Session, version_id: str, project_id: str, ontology_id: str
) -> list[FactClaimModel]:
    conflicts = list(
        session.scalars(
            select(KnowledgeConflictModel).where(
                KnowledgeConflictModel.ontology_id == ontology_id,
                KnowledgeConflictModel.status == "pending",
            )
        )
    )
    claims: list[FactClaimModel] = []
    for conflict in conflicts:
        claims.append(
            FactClaimModel(
                id=_id(),
                claim_key=_claim_key(
                    "value_conflict",
                    conflict.proposal_id,
                    conflict.field,
                    _hash_value(conflict.proposed_value),
                ),
                project_id=project_id,
                ontology_id=ontology_id,
                ontology_version_id=version_id,
                claim_type="conflict",
                layer="value_conflict",
                subject={"proposal_id": conflict.proposal_id, "item_key": conflict.item_key},
                predicate=conflict.field,
                value={"existing": conflict.existing_value, "proposed": conflict.proposed_value},
                graph_path=[],
                evidence_ids=[],
                generation_reason="knowledge_conflict",
                confidence=0.0,
            )
        )
    return claims


def generate_fact_claims(
    session: Session, driver: Driver, version_id: str
) -> list[FactClaimModel]:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    if version.status != VersionStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only draft versions can regenerate facts")
    ontology = session.get(OntologyModel, version.ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology not found")

    graph = _graph_snapshot(driver, ontology.id, version_id)
    evidence_index = _entity_evidence_index(session, ontology.id, version_id)
    relation_types = {
        rt.id: rt
        for rt in session.scalars(
            select(RelationTypeModel).where(RelationTypeModel.ontology_id == ontology.id)
        )
    }
    entities_by_id = {entity["id"]: entity for entity in graph["entities"]}

    session.query(FactClaimModel).filter(
        FactClaimModel.ontology_version_id == version_id
    ).delete(synchronize_session=False)

    claims: list[FactClaimModel] = []
    for entity in graph["entities"]:
        entity_evidence = evidence_index.get(entity["id"], [])
        for name, value in (entity.get("properties") or {}).items():
            claims.append(
                _attribute_fact(
                    version_id, ontology.project_id, ontology.id, entity, name, value, entity_evidence
                )
            )
    for relation in graph["relations"]:
        source = entities_by_id.get(relation.get("source_entity_id"))
        target = entities_by_id.get(relation.get("target_entity_id"))
        if source is None or target is None:
            continue
        confidence = float((relation.get("properties") or {}).get("confidence", 1.0))
        relation_evidence = (
            evidence_index.get(relation["id"])
            or evidence_index.get(source["id"], [])
        )
        claims.append(
            _relation_fact(
                version_id,
                ontology.project_id,
                ontology.id,
                relation,
                source,
                target,
                relation_evidence,
                confidence,
            )
        )
        if confidence < LOW_CONFIDENCE_THRESHOLD:
            claims.append(
                _relation_fact(
                    version_id,
                    ontology.project_id,
                    ontology.id,
                    relation,
                    source,
                    target,
                    relation_evidence,
                    confidence,
                    claim_type="low_confidence",
                    layer="low_confidence",
                    reason="low_confidence_relation",
                )
            )
        rt = relation_types.get(relation.get("relation_type_id"))
        if rt and rt.inverse_name:
            claims.append(
                _relation_fact(
                    version_id,
                    ontology.project_id,
                    ontology.id,
                    relation,
                    target,
                    source,
                    relation_evidence,
                    confidence,
                    claim_type="inferred",
                    layer="inferred_inverse",
                    reason="inverse_relation",
                    predicate_override=rt.inverse_name,
                )
            )
    claims.extend(_conflict_facts(session, version_id, ontology.project_id, ontology.id))
    for claim in claims:
        session.add(claim)
    session.commit()
    return claims


def list_fact_claims(
    session: Session,
    version_id: str,
    layer: str | None = None,
    claim_type: str | None = None,
) -> list[FactClaimModel]:
    statement = select(FactClaimModel).where(FactClaimModel.ontology_version_id == version_id)
    if layer:
        statement = statement.where(FactClaimModel.layer == layer)
    if claim_type:
        statement = statement.where(FactClaimModel.claim_type == claim_type)
    return list(
        session.scalars(statement.order_by(FactClaimModel.layer, FactClaimModel.created_at))
    )


DEFAULT_STRATIFIED_SAMPLE: dict[str, int] = {
    "entity_attribute": 5,
    "entity_relation": 5,
    "inferred_inverse": 3,
    "low_confidence": 5,
    "value_conflict": 5,
}


def sample_fact_claims(
    session: Session, version_id: str, config: dict[str, int] | None = None
) -> list[FactClaimModel]:
    config = config or DEFAULT_STRATIFIED_SAMPLE
    rows = list(
        session.scalars(
            select(FactClaimModel).where(FactClaimModel.ontology_version_id == version_id)
        )
    )
    by_layer: dict[str, list[FactClaimModel]] = defaultdict(list)
    for row in rows:
        by_layer[row.layer].append(row)
    sampled: list[FactClaimModel] = []
    for layer, count in config.items():
        bucket = by_layer.get(layer, [])
        # Prefer non-reviewed and stale first so reviewers see the riskiest claims.
        bucket_sorted = sorted(
            bucket,
            key=lambda c: (
                c.audit_status != "pending",
                not c.stale,
                c.created_at if c.created_at else "",
            ),
        )
        sampled.extend(bucket_sorted[:count])
    return sampled


ALLOWED_DECISIONS = {"approved", "rejected", "needs_correction"}


def review_fact_claim(
    session: Session,
    claim_id: str,
    decision: str,
    reviewer_id: str | None = None,
    reason: str | None = None,
    linked_fix_proposal_id: str | None = None,
) -> FactClaimModel:
    claim = session.get(FactClaimModel, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Fact claim not found")
    if decision not in ALLOWED_DECISIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported decision: {decision}")
    if decision == "rejected" and not linked_fix_proposal_id:
        raise HTTPException(
            status_code=422,
            detail="Rejected facts must reference a linked_fix_proposal_id",
        )
    claim.audit_status = decision
    claim.review_decision = {
        "decision": decision,
        "reviewer_id": reviewer_id,
        "reason": reason,
        "at": _now().isoformat(),
    }
    claim.reviewed_at = _now()
    if decision == "rejected":
        claim.linked_fix_proposal_id = linked_fix_proposal_id
    session.commit()
    session.refresh(claim)
    return claim


def invalidate_for_graph_change(
    session: Session,
    ontology_id: str,
    version_id: str,
    entity_ids: set[str],
    relation_ids: set[str],
) -> int:
    """Mark pending Fact Claims stale when their referenced graph data changes."""
    if not entity_ids and not relation_ids:
        return 0
    rows = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
                FactClaimModel.audit_status == "pending",
            )
        )
    )
    affected = 0
    for claim in rows:
        subject_id = (
            claim.subject.get("entity_id") if isinstance(claim.subject, dict) else None
        )
        path_ids = {
            step.get("node") if isinstance(step, dict) else None
            for step in (claim.graph_path or [])
        }
        path_ids.discard(None)
        touched = (
            (subject_id in entity_ids)
            or (path_ids & entity_ids)
            or (path_ids & relation_ids)
        )
        if touched:
            claim.stale = True
            claim.stale_reason = "graph_data_changed"
            affected += 1
    if affected:
        session.commit()
    return affected
