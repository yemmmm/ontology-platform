"""Deterministic Fact Claim generation, sampling and audit for v0.3 phase 5."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from neo4j import Driver
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories import graph as graph_repo
from app.repositories.models import (
    ClassModel,
    EvidenceModel,
    FactClaimModel,
    KnowledgeConflictModel,
    OntologyModel,
    OntologyVersionModel,
    PropertyDefModel,
    ProposalModel,
    RelationTypeModel,
    RuleDefinitionModel,
    UnanchoredKnowledgeModel,
    VersionStatus,
)

LOW_CONFIDENCE_THRESHOLD = 0.7
ALLOWED_ANCHOR_TYPES = {"unanchored", "entity", "relation", "class", "rule"}
RULE_DERIVED_LAYERS = {"rule_derived", "rule_validation", "workflow"}
GENERATED_FACT_LAYERS = {
    "entity_attribute",
    "entity_relation",
    "inferred_inverse",
    "low_confidence",
    "value_conflict",
}
CORE_ASSERTION_LAYERS = {
    "entity_assertion",
    "relation_assertion",
    "class_assertion",
    "rule_assertion",
    "rule_derived",
    "rule_validation",
    "workflow",
}


def _id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_value(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _policy_name(access_policy: dict[str, Any] | None) -> str:
    if not isinstance(access_policy, dict):
        return "allow"
    raw = (
        access_policy.get("policy")
        or access_policy.get("access_policy")
        or access_policy.get("action")
        or "allow"
    )
    return str(raw)


def _redacted_value(
    value: Any,
    *,
    sensitivity: str,
    access_policy: dict[str, Any] | None,
    authorized: bool,
) -> tuple[Any, str, bool]:
    if authorized:
        return value, "allow", False
    policy = _policy_name(access_policy)
    if policy == "deny":
        return None, "deny", True
    if policy == "approval_required":
        return None, "approval_required", True
    if policy == "mask":
        masking_rule = access_policy.get("masking_rule") if isinstance(access_policy, dict) else None
        return masking_rule or "***", "mask", True
    if sensitivity in {"confidential", "restricted", "sensitive"}:
        return "***", "mask", True
    return value, "allow", False


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


def _anchor(anchor_type: str, target_id: str | None = None, **metadata: Any) -> dict[str, Any]:
    return {"type": anchor_type, "target_id": target_id, **metadata}


def _parse_valid_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def _relation_lifecycle_decision(relation: dict[str, Any]) -> tuple[str, bool, str | None]:
    relation_status = str(relation.get("status") or "active")
    if relation_status == "rejected":
        return "rejected", True, "relation_rejected"
    if relation_status in {"expired", "inactive"}:
        return "pending", True, f"relation_{relation_status}"
    valid_to = _parse_valid_date(relation.get("valid_to"))
    if valid_to is not None and valid_to < _now().date():
        return "pending", True, "relation_expired"
    return "pending", False, None


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
        anchor=_anchor("entity", subject_id),
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
    audit_status, stale, stale_reason = _relation_lifecycle_decision(relation)
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
        anchor=_anchor("relation", relation.get("id")),
        graph_path=[
            {"node": source["id"], "kind": "entity"},
            {"edge": relation.get("id"), "type": relation.get("relation_type")},
            {"node": target["id"], "kind": "entity"},
        ],
        evidence_ids=evidence_ids,
        generation_reason=reason,
        confidence=confidence,
        audit_status=audit_status,
        stale=stale,
        stale_reason=stale_reason,
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
                anchor=_anchor("unanchored", None, reason="value_conflict"),
                graph_path=[],
                evidence_ids=[],
                generation_reason="knowledge_conflict",
                confidence=0.0,
            )
        )
    return claims


def _ontology_for_version(session: Session, version_id: str) -> tuple[OntologyVersionModel, OntologyModel]:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    ontology = session.get(OntologyModel, version.ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    return version, ontology


def _validate_anchor(
    session: Session,
    ontology_id: str,
    anchor: dict[str, Any],
    graph: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    anchor_type = anchor.get("type")
    target_id = anchor.get("target_id")
    if anchor_type not in ALLOWED_ANCHOR_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported anchor type: {anchor_type}")
    if anchor_type == "unanchored":
        return
    if not target_id:
        raise HTTPException(status_code=422, detail=f"{anchor_type} anchor requires target_id")
    if anchor_type == "class":
        class_ = session.get(ClassModel, target_id)
        if class_ is None or class_.ontology_id != ontology_id:
            raise HTTPException(status_code=422, detail="Class anchor target does not exist")
    elif anchor_type == "rule":
        rule = session.get(RuleDefinitionModel, target_id)
        if rule is None or rule.ontology_id != ontology_id:
            raise HTTPException(status_code=422, detail="Rule anchor target does not exist")
    elif graph is not None:
        bucket = "entities" if anchor_type == "entity" else "relations"
        if not any(item.get("id") == target_id for item in graph.get(bucket, [])):
            raise HTTPException(status_code=422, detail=f"{anchor_type} anchor target does not exist")


def create_assertion(
    session: Session,
    version_id: str,
    *,
    anchor: dict[str, Any],
    subject: dict[str, Any],
    predicate: str,
    value: Any,
    evidence_ids: list[str] | None = None,
    generation_reason: str = "direct_user_statement",
    claim_type: str = "direct",
    layer: str | None = None,
    graph_path: list[dict[str, Any]] | None = None,
    confidence: float = 1.0,
    sensitivity: str = "normal",
    access_policy: dict[str, Any] | None = None,
    override_of_claim_id: str | None = None,
) -> FactClaimModel:
    version, ontology = _ontology_for_version(session, version_id)
    if version.status != VersionStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only draft versions can accept assertions")
    _validate_anchor(session, ontology.id, anchor)
    anchor_type = anchor["type"]
    target_id = anchor.get("target_id") or subject.get("entity_id") or subject.get("class_id") or "none"
    resolved_layer = layer or f"{anchor_type}_assertion"
    claim = FactClaimModel(
        id=_id(),
        claim_key=_claim_key(resolved_layer, str(target_id), predicate, _hash_value(value)),
        project_id=ontology.project_id,
        ontology_id=ontology.id,
        ontology_version_id=version_id,
        claim_type=claim_type,
        layer=resolved_layer,
        subject=subject,
        predicate=predicate,
        value=value,
        anchor=anchor,
        graph_path=graph_path or [],
        evidence_ids=evidence_ids or [],
        generation_reason=generation_reason,
        confidence=confidence,
        sensitivity=sensitivity,
        access_policy=access_policy or {},
        override_of_claim_id=override_of_claim_id,
    )
    session.add(claim)
    session.commit()
    session.refresh(claim)
    return claim


def save_unanchored_knowledge(
    session: Session,
    version_id: str,
    *,
    text: str,
    source: dict[str, Any] | None = None,
    summary: str | None = None,
    embedding: list[float] | None = None,
    tags: list[str] | None = None,
    confidence: float = 0.0,
    applicability: str | None = None,
) -> UnanchoredKnowledgeModel:
    version, ontology = _ontology_for_version(session, version_id)
    if version.status != VersionStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only draft versions can accept background knowledge")
    row = UnanchoredKnowledgeModel(
        id=_id(),
        project_id=ontology.project_id,
        ontology_id=ontology.id,
        ontology_version_id=version_id,
        text=text,
        source=source or {},
        summary=summary,
        embedding=embedding or [],
        tags=tags or [],
        confidence=confidence,
        applicability=applicability,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def recall_background_knowledge(
    session: Session,
    version_id: str,
    *,
    query: str | None = None,
    query_embedding: list[float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(UnanchoredKnowledgeModel).where(
                UnanchoredKnowledgeModel.ontology_version_id == version_id,
                UnanchoredKnowledgeModel.status == "background",
            )
        )
    )
    query_terms = {term.lower() for term in (query or "").split() if term}

    def score(row: UnanchoredKnowledgeModel) -> float:
        text = f"{row.text} {row.summary or ''} {' '.join(row.tags or [])}".lower()
        lexical = sum(1 for term in query_terms if term in text)
        vector = _cosine(query_embedding or [], row.embedding or [])
        return lexical + vector

    ranked = sorted(rows, key=score, reverse=True)[:limit]
    return [
        {
            "source_type": "background_recall",
            "knowledge_id": row.id,
            "text": row.text,
            "summary": row.summary,
            "tags": row.tags,
            "confidence": row.confidence,
            "score": score(row),
            "core_fact": False,
        }
        for row in ranked
    ]


def get_background_knowledge(
    session: Session,
    version_id: str,
    knowledge_id: str,
) -> UnanchoredKnowledgeModel:
    knowledge = session.get(UnanchoredKnowledgeModel, knowledge_id)
    if knowledge is None or knowledge.ontology_version_id != version_id:
        raise HTTPException(status_code=404, detail="Background knowledge not found")
    return knowledge


def mark_background_knowledge_promoted(
    session: Session,
    version_id: str,
    knowledge_id: str,
    proposal_id: str,
) -> UnanchoredKnowledgeModel:
    knowledge = get_background_knowledge(session, version_id, knowledge_id)
    knowledge.status = "promoted"
    knowledge.promoted_proposal_id = proposal_id
    session.add(knowledge)
    session.commit()
    session.refresh(knowledge)
    return knowledge


def _properties_for_class(session: Session, class_id: str) -> dict[str, PropertyDefModel]:
    return {
        prop.name: prop
        for prop in session.scalars(select(PropertyDefModel).where(PropertyDefModel.class_id == class_id))
    }


def validate_rule_definition(session: Session, ontology_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    rule_type = payload.get("rule_type")
    if rule_type not in {"classification", "derived_relation", "validation", "workflow"}:
        errors.append(f"unsupported rule_type: {rule_type}")
    scope = payload.get("scope") or {}
    class_id = scope.get("class")
    class_ = session.get(ClassModel, class_id) if class_id else None
    if class_id and (class_ is None or class_.ontology_id != ontology_id):
        errors.append(f"scope class does not exist: {class_id}")
    properties = _properties_for_class(session, class_id) if class_ else {}
    condition = payload.get("condition") or {}
    op, args = next(iter(condition.items()), (None, [])) if isinstance(condition, dict) else (None, [])
    if rule_type == "classification":
        if op not in {">", ">=", "<", "<=", "==", "!="} or not isinstance(args, list) or len(args) != 2:
            errors.append("classification condition must be a binary comparison")
        else:
            left = args[0]
            prop_name = left.get("property") if isinstance(left, dict) else None
            prop = properties.get(prop_name or "")
            if prop is None:
                errors.append(f"condition property does not exist: {prop_name}")
            elif op in {">", ">=", "<", "<="} and prop.type not in {"number", "integer", "float"}:
                errors.append(f"condition property must be numeric: {prop_name}")
    assertion = (payload.get("conclusion") or {}).get("assert") or {}
    predicate = assertion.get("predicate")
    value = assertion.get("value")
    conclusion_prop = properties.get(predicate or "")
    if predicate and conclusion_prop and conclusion_prop.enum_values and value not in conclusion_prop.enum_values:
        errors.append(f"conclusion value is not allowed for {predicate}: {value}")
    return {"valid": not errors, "errors": errors}


def create_rule_definition(
    session: Session,
    version_id: str,
    payload: dict[str, Any],
    *,
    status: str = "active",
) -> RuleDefinitionModel:
    version, ontology = _ontology_for_version(session, version_id)
    validation = validate_rule_definition(session, ontology.id, payload)
    if not validation["valid"]:
        raise HTTPException(status_code=422, detail=validation)
    rule = RuleDefinitionModel(
        id=_id(),
        project_id=ontology.project_id,
        ontology_id=ontology.id,
        ontology_version_id=version.id,
        rule_type=payload["rule_type"],
        scope=payload.get("scope") or {},
        condition=payload.get("condition") or {},
        conclusion=payload.get("conclusion") or {},
        priority=int(payload.get("priority", 0)),
        status=status,
        evidence_ids=payload.get("evidence_ids") or [],
        created_from_proposal_id=payload.get("created_from_proposal_id"),
        version=int(payload.get("version", 1)),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def _condition_matches(condition: dict[str, Any], properties: dict[str, Any]) -> bool:
    op, args = next(iter(condition.items()), (None, [])) if isinstance(condition, dict) else (None, [])
    if not isinstance(args, list) or len(args) != 2:
        return False
    left, right = args
    left_value = properties.get(left.get("property")) if isinstance(left, dict) else left
    try:
        if op == ">":
            return left_value > right
        if op == ">=":
            return left_value >= right
        if op == "<":
            return left_value < right
        if op == "<=":
            return left_value <= right
        if op == "==":
            return left_value == right
        if op == "!=":
            return left_value != right
    except TypeError:
        return False
    return False


def _rule_output_claim(
    *,
    version: OntologyVersionModel,
    ontology: OntologyModel,
    rule: RuleDefinitionModel,
    layer: str,
    claim_type: str,
    subject: dict[str, Any],
    predicate: str,
    value: Any,
    output_anchor: dict[str, Any],
    graph_path: list[dict[str, Any]],
    confidence: float = 1.0,
) -> FactClaimModel:
    subject_id = (
        subject.get("entity_id")
        or subject.get("relation_id")
        or subject.get("workflow_instance_id")
        or "rule"
    )
    claim_key = _claim_key(layer, f"{rule.id}:v{rule.version}:{subject_id}", predicate, _hash_value(value))
    return FactClaimModel(
        id=_id(),
        claim_key=claim_key,
        project_id=ontology.project_id,
        ontology_id=ontology.id,
        ontology_version_id=version.id,
        claim_type=claim_type,
        layer=layer,
        subject=subject,
        predicate=predicate,
        value=value,
        anchor=_anchor("rule", rule.id, output_anchor=output_anchor),
        graph_path=[*graph_path, {"rule": rule.id, "version": rule.version}],
        evidence_ids=rule.evidence_ids,
        generation_reason=f"rule:{rule.id}",
        confidence=confidence,
    )


def _classification_claims(
    version: OntologyVersionModel,
    ontology: OntologyModel,
    graph: dict[str, list[dict[str, Any]]],
    rule: RuleDefinitionModel,
) -> list[FactClaimModel]:
    class_id = (rule.scope or {}).get("class")
    assertion = (rule.conclusion or {}).get("assert") or {}
    predicate = assertion.get("predicate")
    value = assertion.get("value")
    if not predicate:
        return []
    claims: list[FactClaimModel] = []
    for entity in graph["entities"]:
        if entity.get("class_id") != class_id:
            continue
        if not _condition_matches(rule.condition or {}, entity.get("properties") or {}):
            continue
        claims.append(
            _rule_output_claim(
                version=version,
                ontology=ontology,
                rule=rule,
                layer="rule_derived",
                claim_type="derived",
                subject={
                    "entity_id": entity["id"],
                    "name": entity.get("name"),
                    "class_id": entity.get("class_id"),
                },
                predicate=predicate,
                value=value,
                output_anchor={"type": "entity", "target_id": entity["id"]},
                graph_path=[{"node": entity["id"], "kind": "entity"}],
            )
        )
    return claims


def _derived_relation_claims(
    version: OntologyVersionModel,
    ontology: OntologyModel,
    graph: dict[str, list[dict[str, Any]]],
    rule: RuleDefinitionModel,
) -> list[FactClaimModel]:
    pattern = (rule.condition or {}).get("relation") or (rule.condition or {}).get("path") or {}
    source_class = pattern.get("source_class")
    relation_type = pattern.get("relation_type")
    target_class = pattern.get("target_class")
    assertion = (rule.conclusion or {}).get("assert") or {}
    predicate = assertion.get("predicate") or (rule.conclusion or {}).get("relation_type")
    if not predicate:
        return []
    entities = {entity["id"]: entity for entity in graph["entities"]}
    claims: list[FactClaimModel] = []
    for relation in graph["relations"]:
        source = entities.get(relation.get("source_entity_id"))
        target = entities.get(relation.get("target_entity_id"))
        if source is None or target is None:
            continue
        if source_class and source.get("class_id") != source_class:
            continue
        if relation_type and relation.get("relation_type") != relation_type:
            continue
        if target_class and target.get("class_id") != target_class:
            continue
        value = {
            "target_entity_id": target["id"],
            "target_name": target.get("name"),
            **(assertion.get("value") if isinstance(assertion.get("value"), dict) else {}),
        }
        claims.append(
            _rule_output_claim(
                version=version,
                ontology=ontology,
                rule=rule,
                layer="rule_derived",
                claim_type="derived",
                subject={
                    "entity_id": source["id"],
                    "name": source.get("name"),
                    "class_id": source.get("class_id"),
                },
                predicate=predicate,
                value=value,
                output_anchor={"type": "relation", "target_id": relation.get("id")},
                graph_path=[
                    {"node": source["id"], "kind": "entity"},
                    {"edge": relation.get("id"), "type": relation.get("relation_type")},
                    {"node": target["id"], "kind": "entity"},
                ],
            )
        )
    return claims


def _validation_claims(
    version: OntologyVersionModel,
    ontology: OntologyModel,
    graph: dict[str, list[dict[str, Any]]],
    rule: RuleDefinitionModel,
) -> list[FactClaimModel]:
    class_id = (rule.scope or {}).get("class")
    assertion = (rule.conclusion or {}).get("assert") or {}
    predicate = assertion.get("predicate") or "constraint_violation"
    claims: list[FactClaimModel] = []
    for entity in graph["entities"]:
        if class_id and entity.get("class_id") != class_id:
            continue
        if _condition_matches(rule.condition or {}, entity.get("properties") or {}):
            continue
        value = assertion.get("value") or {
            "rule_id": rule.id,
            "rule_version": rule.version,
            "failed_condition": rule.condition,
        }
        claims.append(
            _rule_output_claim(
                version=version,
                ontology=ontology,
                rule=rule,
                layer="rule_validation",
                claim_type="validation",
                subject={
                    "entity_id": entity["id"],
                    "name": entity.get("name"),
                    "class_id": entity.get("class_id"),
                },
                predicate=predicate,
                value=value,
                output_anchor={"type": "entity", "target_id": entity["id"]},
                graph_path=[{"node": entity["id"], "kind": "entity"}],
                confidence=1.0,
            )
        )
    return claims


def _workflow_next_step(steps: list[dict[str, Any]], completed_roles: set[str]) -> dict[str, Any] | None:
    ordered = sorted(steps, key=lambda step: int(step.get("order", 0)))
    for step in ordered:
        role = step.get("role")
        if role and role not in completed_roles:
            return step
    return None


def _workflow_claims(
    version: OntologyVersionModel,
    ontology: OntologyModel,
    graph: dict[str, list[dict[str, Any]]],
    rule: RuleDefinitionModel,
) -> list[FactClaimModel]:
    workflow = (rule.conclusion or {}).get("workflow") or {}
    steps = workflow.get("steps") or (rule.condition or {}).get("steps") or []
    if not steps:
        return []
    class_id = (rule.scope or {}).get("class")
    claims: list[FactClaimModel] = []
    for entity in graph["entities"]:
        if class_id and entity.get("class_id") != class_id:
            continue
        properties = entity.get("properties") or {}
        completed_roles = set(properties.get("completed_steps") or [])
        requested_role = properties.get("requested_step_role")
        next_step = _workflow_next_step(steps, completed_roles)
        allowed = bool(next_step and requested_role == next_step.get("role"))
        predicate = "workflow_transition_allowed" if allowed else "workflow_transition_blocked"
        value = {
            "allowed": allowed,
            "requested_role": requested_role,
            "next_role": next_step.get("role") if next_step else None,
            "completed_steps": sorted(completed_roles),
            "workflow_template": (rule.scope or {}).get("workflow_template"),
        }
        claims.append(
            _rule_output_claim(
                version=version,
                ontology=ontology,
                rule=rule,
                layer="workflow" if allowed else "rule_validation",
                claim_type="workflow" if allowed else "validation",
                subject={
                    "workflow_instance_id": entity["id"],
                    "entity_id": entity["id"],
                    "name": entity.get("name"),
                    "class_id": entity.get("class_id"),
                },
                predicate=predicate,
                value=value,
                output_anchor={"type": "entity", "target_id": entity["id"]},
                graph_path=[{"node": entity["id"], "kind": "workflow_instance"}],
            )
        )
    return claims


RULE_EXECUTORS = {
    "classification": _classification_claims,
    "derived_relation": _derived_relation_claims,
    "validation": _validation_claims,
    "workflow": _workflow_claims,
}


def execute_rule_definitions(
    session: Session, driver: Driver, version_id: str
) -> list[FactClaimModel]:
    version, ontology = _ontology_for_version(session, version_id)
    graph = _graph_snapshot(driver, ontology.id, version_id)
    rules = list(
        session.scalars(
            select(RuleDefinitionModel).where(
                RuleDefinitionModel.ontology_version_id == version_id,
                RuleDefinitionModel.status == "active",
            )
        )
    )
    existing = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
                FactClaimModel.layer.in_(RULE_DERIVED_LAYERS),
            )
        )
    )
    existing_by_key = {claim.claim_key: claim for claim in existing}
    produced_keys: set[str] = set()
    produced: list[FactClaimModel] = []
    for rule in rules:
        executor = RULE_EXECUTORS.get(rule.rule_type)
        if executor is None:
            continue
        for claim in executor(version, ontology, graph, rule):
            produced_keys.add(claim.claim_key)
            if claim.claim_key in existing_by_key:
                continue
            session.add(claim)
            produced.append(claim)
    active_rule_ids = {rule.id for rule in rules}
    for claim in existing:
        rule_id = claim.generation_reason.removeprefix("rule:")
        if rule_id in active_rule_ids and claim.claim_key not in produced_keys:
            claim.stale = True
            claim.stale_reason = "rule_inputs_changed"
    session.commit()
    return produced


def execute_classification_rules(
    session: Session, driver: Driver, version_id: str
) -> list[FactClaimModel]:
    return execute_rule_definitions(session, driver, version_id)


def recall_entity_knowledge(
    session: Session,
    version_id: str,
    entity: dict[str, Any],
    *,
    background_query: str | None = None,
    authorized: bool = False,
) -> list[dict[str, Any]]:
    claims = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
                FactClaimModel.stale.is_(False),
                FactClaimModel.audit_status.in_(["pending", "approved"]),
            )
        )
    )
    entity_id = entity["id"]
    class_chain = [entity.get("class_id"), *(entity.get("parent_class_ids") or [])]
    results: list[dict[str, Any]] = []
    for name, value in (entity.get("properties") or {}).items():
        results.append({"source_type": "entity_property", "predicate": name, "value": value})
    for claim in claims:
        anchor = claim.anchor or {}
        anchor_type = anchor.get("type")
        output_anchor = anchor.get("output_anchor") if isinstance(anchor.get("output_anchor"), dict) else {}
        claim_subject_entity = (
            claim.subject.get("entity_id") if isinstance(claim.subject, dict) else None
        )
        applies = (
            (anchor_type == "entity" and anchor.get("target_id") == entity_id)
            or (anchor_type == "class" and anchor.get("target_id") in class_chain)
            or (
                claim.generation_reason.startswith("rule:")
                and (
                    claim_subject_entity == entity_id
                    or output_anchor.get("target_id") == entity_id
                )
            )
        )
        if not applies:
            continue
        value, access_decision, redacted = _redacted_value(
            claim.value,
            sensitivity=claim.sensitivity,
            access_policy=claim.access_policy,
            authorized=authorized,
        )
        item = {
            "source_type": f"{anchor_type}_assertion" if anchor_type else claim.layer,
            "claim_id": claim.id,
            "predicate": claim.predicate,
            "value": value,
            "anchor": anchor,
            "audit_status": claim.audit_status,
            "overrides": claim.override_of_claim_id,
            "sensitivity": claim.sensitivity,
            "access_policy": claim.access_policy,
            "access_decision": access_decision,
            "redacted": redacted,
        }
        results.append(item)
    overridden = {item["overrides"] for item in results if item.get("overrides")}
    for item in results:
        if item.get("claim_id") in overridden:
            item["overridden"] = True
    if background_query:
        results.extend(recall_background_knowledge(session, version_id, query=background_query))
    return results


def _class_chain_for_entity(
    session: Session,
    ontology_id: str,
    class_id: str,
) -> list[ClassModel]:
    classes = list(session.scalars(select(ClassModel).where(ClassModel.ontology_id == ontology_id)))
    by_id = {class_.id: class_ for class_ in classes}
    chain: list[ClassModel] = []

    def visit(current_id: str, seen: set[str]) -> None:
        if current_id in seen:
            return
        class_ = by_id.get(current_id)
        if class_ is None:
            return
        chain.append(class_)
        next_seen = {*seen, current_id}
        for parent_id in class_.parent_class_ids or []:
            visit(parent_id, next_seen)

    visit(class_id, set())
    return chain


def _rule_summary(rule: RuleDefinitionModel) -> dict[str, Any]:
    return {
        "id": rule.id,
        "rule_type": rule.rule_type,
        "scope": rule.scope,
        "condition": rule.condition,
        "conclusion": rule.conclusion,
        "status": rule.status,
        "priority": rule.priority,
        "evidence_ids": rule.evidence_ids,
        "version": rule.version,
    }


def _knowledge_item(
    claim: FactClaimModel,
    *,
    source_type: str,
    authorized: bool = False,
    relation_id: str | None = None,
    rule_id: str | None = None,
    inherited_from_class_id: str | None = None,
) -> dict[str, Any]:
    value, access_decision, redacted = _redacted_value(
        claim.value,
        sensitivity=claim.sensitivity,
        access_policy=claim.access_policy,
        authorized=authorized,
    )
    return {
        "source_type": source_type,
        "claim_id": claim.id,
        "predicate": claim.predicate,
        "value": value,
        "anchor": claim.anchor or {},
        "layer": claim.layer,
        "audit_status": claim.audit_status,
        "confidence": claim.confidence,
        "sensitivity": claim.sensitivity,
        "access_policy": claim.access_policy,
        "access_decision": access_decision,
        "redacted": redacted,
        "evidence_ids": claim.evidence_ids,
        "generation_reason": claim.generation_reason,
        "relation_id": relation_id,
        "rule_id": rule_id,
        "inherited_from_class_id": inherited_from_class_id,
        "overrides": claim.override_of_claim_id,
        "overridden": False,
    }


def get_entity_knowledge_context(
    session: Session,
    driver: Driver,
    version_id: str,
    entity_id: str,
    *,
    authorized: bool = False,
) -> dict[str, Any]:
    version = session.get(OntologyVersionModel, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ontology version not found")
    ontology = session.get(OntologyModel, version.ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology not found")
    entity = graph_repo.get_entity_node(driver, entity_id, ontology.project_id, ontology.id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    relations = graph_repo.list_relation_edges(
        driver,
        ontology.project_id,
        ontology.id,
        entity_id,
        relation_type_id=None,
        limit=100,
    )
    relation_ids = {relation["id"] for relation in relations}
    class_chain = _class_chain_for_entity(session, ontology.id, entity["class_id"])
    class_ids = {class_.id for class_ in class_chain}

    claims = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
                FactClaimModel.stale.is_(False),
                FactClaimModel.audit_status.in_(["pending", "approved"]),
            )
        )
    )

    context: dict[str, Any] = {
        "entity": entity,
        "class_chain": class_chain,
        "relation_ids": sorted(relation_ids),
        "properties": [
            {
                "source_type": "entity_property",
                "predicate": name,
                "value": value,
                "anchor": {"type": "entity", "target_id": entity_id},
            }
            for name, value in (entity.get("properties") or {}).items()
        ],
        "entity_assertions": [],
        "inherited_class_assertions": [],
        "relation_assertions": [],
        "rule_assertions": [],
        "rules": [],
    }
    rule_ids: set[str] = set()

    for claim in claims:
        anchor = claim.anchor or {}
        anchor_type = anchor.get("type")
        target_id = anchor.get("target_id")
        output_anchor = anchor.get("output_anchor") if isinstance(anchor.get("output_anchor"), dict) else {}
        subject_entity_id = claim.subject.get("entity_id") if isinstance(claim.subject, dict) else None

        if anchor_type == "entity" and target_id == entity_id:
            context["entity_assertions"].append(
                _knowledge_item(claim, source_type="entity_assertion", authorized=authorized)
            )
            continue

        if anchor_type == "class" and target_id in class_ids:
            context["inherited_class_assertions"].append(
                _knowledge_item(
                    claim,
                    source_type="class_assertion",
                    authorized=authorized,
                    inherited_from_class_id=str(target_id),
                )
            )
            continue

        if anchor_type == "relation" and target_id in relation_ids:
            context["relation_assertions"].append(
                _knowledge_item(
                    claim,
                    source_type="relation_assertion",
                    authorized=authorized,
                    relation_id=str(target_id),
                )
            )
            continue

        rule_id = None
        if anchor_type == "rule" and isinstance(target_id, str):
            rule_id = target_id
        elif claim.generation_reason.startswith("rule:"):
            rule_id = claim.generation_reason.removeprefix("rule:").split(":", 1)[0]
        applies_to_entity = (
            subject_entity_id == entity_id
            or output_anchor.get("target_id") == entity_id
        )
        if rule_id and applies_to_entity:
            rule_ids.add(rule_id)
            context["rule_assertions"].append(
                _knowledge_item(
                    claim,
                    source_type=claim.layer,
                    authorized=authorized,
                    rule_id=rule_id,
                )
            )

    all_items = (
        context["entity_assertions"]
        + context["inherited_class_assertions"]
        + context["relation_assertions"]
        + context["rule_assertions"]
    )
    overridden = {item["overrides"] for item in all_items if item.get("overrides")}
    for item in all_items:
        if item.get("claim_id") in overridden:
            item["overridden"] = True

    if rule_ids:
        rules = session.scalars(
            select(RuleDefinitionModel).where(
                RuleDefinitionModel.ontology_version_id == version_id,
                RuleDefinitionModel.id.in_(rule_ids),
            )
        )
        context["rules"] = [_rule_summary(rule) for rule in rules]
    return context


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
        FactClaimModel.ontology_version_id == version_id,
        FactClaimModel.layer.in_(GENERATED_FACT_LAYERS),
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
    """Mark affected pending facts and governed v0.5 Assertions stale after graph changes."""
    if not entity_ids and not relation_ids:
        return 0
    rows = list(
        session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.ontology_version_id == version_id,
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
            if claim.audit_status != "pending" and claim.layer not in CORE_ASSERTION_LAYERS:
                continue
            claim.stale = True
            claim.stale_reason = "graph_data_changed"
            affected += 1
    if affected:
        session.commit()
    return affected
