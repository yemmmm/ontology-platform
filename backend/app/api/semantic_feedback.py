"""Independent usage-feedback endpoints, sharing the MCP service contract."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.semantic_feedback import (
    FeedbackError,
    FeedbackResolution,
    FeedbackSubmission,
    SemanticFeedbackService,
)

router = APIRouter(prefix="/semantic/feedback", tags=["semantic"])


def _call(fn):
    try:
        return fn()
    except FeedbackError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.post("")
async def submit_semantic_feedback(
    request: FeedbackSubmission,
    raw_request: Request,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
):
    payload = await raw_request.json()
    return _call(lambda: SemanticFeedbackService(session, principal).submit(payload))


@router.get("")
def list_semantic_feedback(
    project_id: str,
    pending_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
):
    return _call(
        lambda: SemanticFeedbackService(session, principal).list(
            project_id, pending_only=pending_only, limit=limit, cursor=cursor
        )
    )


@router.get("/{feedback_id}")
def get_semantic_feedback(
    feedback_id: str,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
):
    return _call(lambda: SemanticFeedbackService(session, principal).get(feedback_id))


@router.post("/{feedback_id}/resolution")
def record_semantic_feedback_resolution(
    feedback_id: str,
    request: FeedbackResolution,
    principal: AuthPrincipal = Depends(principal_dependency),
    session: Session = Depends(get_db_session),
):
    return _call(
        lambda: SemanticFeedbackService(session, principal).record_resolution(
            feedback_id, request.model_dump(mode="json", exclude_unset=True)
        )
    )
