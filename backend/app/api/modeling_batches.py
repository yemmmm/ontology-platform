"""REST adapter for the R-004 Modeling Batch protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.schemas import ModelingBatchSubmit
from app.core.config import Settings
from app.repositories.models import (
    SemanticGraphSetModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
)
from app.repositories.rdf_store import RdfStoreRepository
from app.services.modeling_batches import (
    ModelingAuthorizationContext,
    ModelingBatchError,
    ModelingBatchService,
)
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.semantic_read_model import ReadModelError, SemanticReadModelService
from app.services.semantic_read_scope import ReadScopeError, SemanticReadScopeResolver
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
    "history": "graph-set-history-list",
    "delta": "graph-set-delta",
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
    session: Session = Depends(get_db_session),
    rdf_store: RdfStoreRepository = Depends(get_rdf_store),
    settings: Settings = Depends(get_settings),
):
    workspace = OntologyWorkspaceService(session, settings).context(ontology_id)
    graph_set_id = workspace.get("default_graph_set_id")
    if workspace.get("state") != "ready" or not graph_set_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "workspace_revision_conflict",
                "message": "Ontology workspace is incomplete",
            },
        )
    if model_name == "rules":
        rows = session.execute(
            select(SemanticRuleModel, SemanticRuleDefinitionModel)
            .outerjoin(
                SemanticRuleDefinitionModel,
                SemanticRuleDefinitionModel.id == SemanticRuleModel.current_definition_id,
            )
            .where(SemanticRuleModel.ontology_id == ontology_id)
            .order_by(SemanticRuleModel.rule_iri)
            .limit(limit or 500)
        )
        return {
            "model_name": "rules",
            "ontology_id": ontology_id,
            "items": [
                {
                    "rule_id": rule.id,
                    "rule_iri": rule.rule_iri,
                    "status": rule.status,
                    "current_definition_id": definition.id if definition else None,
                    "version": definition.version if definition else None,
                    "name": definition.name if definition else None,
                }
                for rule, definition in rows
            ],
            "warnings": [],
        }
    canonical_name = READ_MODEL_NAMES.get(model_name)
    if canonical_name is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unsupported_read_model", "message": "Unsupported Ontology read model"},
        )
    service = SemanticReadModelService(
        rdf_store=rdf_store,
        scope_resolver=SemanticReadScopeResolver(session),
        session=session,
    )
    try:
        base_graph_set_id = graph_set_id
        target_graph_set_id = None
        no_delta_baseline = False
        if model_name == "delta":
            baseline = session.scalar(
                select(SemanticGraphSetModel)
                .where(
                    SemanticGraphSetModel.scope_type == "ontology",
                    SemanticGraphSetModel.scope_id == ontology_id,
                    SemanticGraphSetModel.id != graph_set_id,
                )
                .order_by(SemanticGraphSetModel.created_at.desc())
                .limit(1)
            )
            base_graph_set_id = baseline.id if baseline else graph_set_id
            target_graph_set_id = graph_set_id
            no_delta_baseline = baseline is None
        response = service.read_model(
            graph_set_id=base_graph_set_id,
            model_name=canonical_name,
            include=include,
            allow_stale_derived=allow_stale_derived,
            field_set=field_set,
            limit=limit,
            target=target_graph_set_id,
            entity_iri=entity_iri,
            class_iri=class_iri,
            kind=kind,
            q=q,
        )
        if no_delta_baseline:
            response["warnings"] = [
                *response.get("warnings", []),
                {"code": "no_prior_graph_set", "message": "No prior Ontology baseline exists"},
            ]
        return response
    except (ReadModelError, ReadScopeError) as exc:
        raise HTTPException(status_code=getattr(exc, "status_code", 400), detail=str(exc)) from exc
