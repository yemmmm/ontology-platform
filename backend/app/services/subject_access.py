"""Project subject/role control plane; RDF declarations never determine authorization."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.repositories.models import (
    ApiKeyModel,
    OntologyModel,
    ProjectUserMembershipModel,
    SemanticAccessRoleMemberModel,
    SemanticAccessRoleModel,
    SemanticGraphRegistryModel,
)
from app.services.semantic_export import SemanticNamespace
from app.services.semantic_protection_set import normalize_grants, ProtectionSetError


def commit_configuration(session):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, detail={"code": "configuration_conflict"}) from exc


def remove_member(session, project_id, user_id):
    session.execute(
        update(ApiKeyModel)
        .where(
            ApiKeyModel.project_id == project_id,
            ApiKeyModel.user_id == user_id,
            ApiKeyModel.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    session.execute(
        delete(SemanticAccessRoleMemberModel).where(
            SemanticAccessRoleMemberModel.project_id == project_id,
            SemanticAccessRoleMemberModel.user_id == user_id,
        )
    )
    session.execute(
        delete(ProjectUserMembershipModel).where(
            ProjectUserMembershipModel.project_id == project_id,
            ProjectUserMembershipModel.user_id == user_id,
        )
    )
    commit_configuration(session)


def replace_roles(session, project_id, user_id, role_ids):
    selected = set(role_ids)
    existing = set(
        session.scalars(
            select(SemanticAccessRoleModel.id).where(
                SemanticAccessRoleModel.project_id == project_id,
                SemanticAccessRoleModel.id.in_(selected),
            )
        )
    )
    if existing != selected:
        raise HTTPException(422, detail={"code": "invalid_role_ids", "field": "role_ids"})
    session.execute(
        delete(SemanticAccessRoleMemberModel).where(
            SemanticAccessRoleMemberModel.project_id == project_id,
            SemanticAccessRoleMemberModel.user_id == user_id,
        )
    )
    session.add_all(
        SemanticAccessRoleMemberModel(
            project_id=project_id,
            user_id=user_id,
            role_id=role_id,
        )
        for role_id in sorted(selected)
    )
    commit_configuration(session)


def business_role_status(session, store, settings, project_id, ontology_id, iri):
    if iri is None and ontology_id is None:
        return "unassociated"
    ontology = session.get(OntologyModel, ontology_id) if ontology_id else None
    if ontology is None or ontology.project_id != project_id or not iri:
        return "missing"
    if any(c.isspace() or ord(c) < 32 or c in '<>"{}|^`\\' for c in iri) or ":" not in iri:
        return "invalid_definition"
    graphs = list(
        session.scalars(
            select(SemanticGraphRegistryModel.graph_iri).where(
                SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                SemanticGraphRegistryModel.semantic_owner_id == ontology_id,
                SemanticGraphRegistryModel.category.in_(["ontology", "data"]),
            )
        )
    )
    if not graphs:
        return "missing"
    predicate = (
        str(SemanticNamespace(settings.semantic_base_iri, settings.semantic_graph_iri_prefix).vocab)
        + "semanticDefinition"
    )
    graph_terms = " ".join(f"<{g}>" for g in graphs)
    query = (
        f"SELECT ?definition WHERE {{ VALUES ?g {{ {graph_terms} }} "
        f"GRAPH ?g {{ <{iri}> <{predicate}> ?definition }} }}"
    )
    try:
        result = store.query_sparql(query, timeout_seconds=5, limit=100)
    except Exception as exc:
        raise HTTPException(
            503,
            detail={"code": "dependency_error", "message": "Business role read unavailable; retry"},
        ) from exc
    rows = result.result.get("results", {}).get("bindings", [])
    if not rows:
        return "missing"
    for row in rows:
        try:
            definition = json.loads(row["definition"]["value"])
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(definition, dict) and definition.get("semantic_role") == "business_role":
            return "valid"
    return "invalid_definition"


def save_role(session, store, settings, project_id, values, record=None):
    creating = record is None
    record = record or SemanticAccessRoleModel(id=str(uuid4()), project_id=project_id)
    if "grants" in values:
        try:
            values["grants"] = normalize_grants(values["grants"])
        except ProtectionSetError as exc:
            raise HTTPException(
                exc.status_code, detail={"code": exc.code, "field": "grants", "message": str(exc)}
            ) from exc
    if creating or {"business_role_iri", "business_role_ontology_id"} & values.keys():
        iri = values.get("business_role_iri", record.business_role_iri)
        ontology_id = values.get("business_role_ontology_id", record.business_role_ontology_id)
        if (iri is None) != (ontology_id is None):
            raise HTTPException(422, detail={"code": "business_role_pair_required"})
        if (
            iri is not None
            and business_role_status(
                session,
                store,
                settings,
                project_id,
                ontology_id,
                iri,
            )
            != "valid"
        ):
            raise HTTPException(422, detail={"code": "invalid_business_role_reference"})
    for field, value in values.items():
        setattr(record, field, value)
    session.add(record)
    commit_configuration(session)
    session.refresh(record)
    return record
