"""REST adapter for the R-004 Modeling Batch protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.schemas import ModelingBatchSubmit
from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_batches import (
    ModelingAuthorizationContext,
    ModelingBatchError,
    ModelingBatchService,
)
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_read_model import ReadModelError, SemanticReadModelService
from app.services.semantic_read_scope import ReadScopeError, SemanticReadScopeResolver
from app.services.semantic_retrieval import SemanticResourceRetrievalService
from app.services.semantic_access import (
    SemanticAccessDependencyError,
    SemanticAccessResolver,
)
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency

router = APIRouter(tags=["modeling batches"])


def _service(
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
) -> ModelingBatchService:
    return ModelingBatchService(session, settings, rdf_store)


def _call(operation):
    try:
        return operation()
    except ModelingBatchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=jsonable_encoder({"code": exc.code, "message": exc.message, **exc.detail}),
        ) from exc


@router.post("/build-sessions/{session_id}/modeling-batches")
async def submit_modeling_batch(
    session_id: str,
    payload: ModelingBatchSubmit,
    request: Request,
    principal: AuthPrincipal = Depends(principal_dependency),
    service: ModelingBatchService = Depends(_service),
):
    request_bytes = len(await request.body())
    return _call(
        lambda: service.submit(
            session_id,
            payload,
            authorization=ModelingAuthorizationContext(actor=principal.actor, surface="rest"),
            request_bytes=request_bytes,
        )
    )


@router.get("/modeling-batches/{batch_id}")
def get_modeling_batch(batch_id: str, service: ModelingBatchService = Depends(_service)):
    return _call(lambda: service.get_batch(batch_id))


@router.get("/build-sessions/{session_id}/modeling-batches")
def list_session_modeling_batches(
    session_id: str,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Annotated[list[str] | None, Query()] = None,
    service: ModelingBatchService = Depends(_service),
):
    return _call(
        lambda: service.list_session_batches(
            session_id, cursor=cursor, limit=limit, statuses=status
        )
    )


@router.get("/ontologies/{ontology_id}/modeling-batches")
def list_ontology_modeling_batches(
    ontology_id: str,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: Annotated[list[str] | None, Query()] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    service: ModelingBatchService = Depends(_service),
):
    return _call(
        lambda: service.list_ontology_batches(
            ontology_id,
            cursor=cursor,
            limit=limit,
            statuses=status,
            created_from=created_from,
            created_to=created_to,
        )
    )


@router.get("/ontologies/{ontology_id}/modeling-context")
def get_modeling_context(ontology_id: str, service: ModelingBatchService = Depends(_service)):
    return _call(lambda: service.get_modeling_context(ontology_id))


READ_MODEL_NAMES = {
    "classes": "ontology-schema-summary",
    "entities": "entity-list",
    "facts": "statement-list",
    # R4.0-010 keeps the exact list/detail model names available through the
    # Ontology read-model adapter used by the MCP surface as well as REST.
    "table-mapping-list": "table-mapping-list",
    "table-mapping-detail": "table-mapping-detail",
    "join-mapping-list": "join-mapping-list",
    "join-mapping-detail": "join-mapping-detail",
    "enum-meaning-list": "enum-meaning-list",
    "enum-meaning-detail": "enum-meaning-detail",
    "metric-list": "metric-list",
    "metric-detail": "metric-detail",
}


@router.get("/ontologies/{ontology_id}/semantic-read-models/{model_name}")
def get_ontology_read_model(
    ontology_id: str,
    model_name: str,
    include: str = "asserted",
    allow_stale_derived: bool = True,
    field_set: str = "summary",
    limit: Annotated[int | None, Query(ge=1, le=2000)] = None,
    entity_iri: str | None = None,
    class_iri: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    search_mode: str = "hybrid",
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    workspace = OntologyWorkspaceService(session, settings).context(ontology_id)
    ontology_id = workspace.get("ontology_id")
    if workspace.get("state") != "ready" or not ontology_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "workspace_revision_conflict",
                "message": "Ontology workspace is incomplete",
            },
        )
    canonical_name = READ_MODEL_NAMES.get(model_name)
    if canonical_name is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unsupported_read_model", "message": "Unsupported Ontology read model"},
        )
    try:
        ontology_for_access = session.get(OntologyModel, ontology_id)
        access_view = SemanticAccessResolver(session).resolve(
            principal, ontology_for_access.project_id if ontology_for_access else None
        )
    except SemanticAccessDependencyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "dependency_error", "message": str(exc)},
        ) from exc
    service = SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=SemanticReadScopeResolver(session),
        access_view=access_view,
        session=session,
        retrieval_service=SemanticResourceRetrievalService(session, settings),
    )
    try:
        response = service.read_model(
            ontology_id=ontology_id,
            model_name=canonical_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            field_set=field_set,
            limit=limit,
            entity_iri=entity_iri,
            class_iri=class_iri,
            kind=kind,
            q=q,
            search_mode=search_mode,
        )
        if canonical_name == "entity-list":
            # Protocol consumes an explicit, scope-bound identity projection.
            # Do not derive semantic IDs or class IDs by splitting IRIs; the
            # SPARQL projection supplies those values and this adapter only
            # binds the authenticated Project/Ontology/workspace envelope.
            ontology = session.get(OntologyModel, ontology_id)
            if ontology is None:
                raise HTTPException(status_code=404, detail="Ontology not found")
            workspace_version = ModelingWorkspaceVersionService(
                session, settings
            ).version_for(ontology_id)
            for item in response.get("items", []):
                if not isinstance(item, dict):
                    continue
                item.update(
                    {
                        "project_id": ontology.project_id,
                        "ontology_id": ontology_id,
                        "workspace_version": workspace_version,
                    }
                )
        return response
    except (ReadModelError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
