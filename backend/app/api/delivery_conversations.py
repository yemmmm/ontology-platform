"""Project-bound public dialogue; messages never launch a Delivery runtime."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.repositories.models import ProjectModel
from app.security.auth import AuthPrincipal
from app.security.http import principal_dependency
from app.services.delivery_conversations import ConversationError, DeliveryConversationsService

router = APIRouter(prefix="/projects/{project_id}/delivery-conversations", tags=["delivery conversations"])


def get_conversations_service() -> DeliveryConversationsService:
    return DeliveryConversationsService()


def conversation_project(
    project_id: str, response: Response, session: Session = Depends(get_db_session),
) -> str:
    if session.get(ProjectModel, project_id) is None:
        raise HTTPException(404, detail={"code": "project_not_found"})
    response.headers["Cache-Control"] = "no-store"
    return project_id


def invoke(call):
    try:
        return call()
    except ConversationError as exc:
        raise HTTPException(exc.status, detail=exc.envelope()) from exc


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    kind: Literal["message", "answer", "control"]
    text: str = Field(min_length=1, max_length=65536)
    reply_to_message_id: str | None = None
    source_reference: str | None = None
    action: Literal["pause", "resume", "cancel", "revoke_budget", "stop"] | None = None


@router.get("")
def conversations(project_id: str = Depends(conversation_project),
                  service: DeliveryConversationsService = Depends(get_conversations_service)):
    return invoke(lambda: service.list(project_id))


@router.get("/{delivery_session_id}")
def conversation(delivery_session_id: str, project_id: str = Depends(conversation_project),
                 service: DeliveryConversationsService = Depends(get_conversations_service)):
    return invoke(lambda: service.detail(project_id, delivery_session_id))


@router.get("/{delivery_session_id}/events")
def events(delivery_session_id: str, after_seq: int = Query(0, ge=0),
           limit: int = Query(100, ge=1, le=200), project_id: str = Depends(conversation_project),
           service: DeliveryConversationsService = Depends(get_conversations_service)):
    return invoke(lambda: service.events(project_id, delivery_session_id, after_seq, limit))


@router.get("/{delivery_session_id}/messages/{message_id}")
def receipt(delivery_session_id: str, message_id: UUID,
            project_id: str = Depends(conversation_project),
            service: DeliveryConversationsService = Depends(get_conversations_service)):
    return invoke(lambda: service.receipt(project_id, delivery_session_id, str(message_id)))


@router.post("/{delivery_session_id}/messages")
def submit(delivery_session_id: str, body: MessageInput, response: Response,
           project_id: str = Depends(conversation_project),
           principal: AuthPrincipal = Depends(principal_dependency),
           service: DeliveryConversationsService = Depends(get_conversations_service)):
    envelope = body.model_dump(mode="json", exclude_none=True)
    actor = {"kind": "user", "reference": principal.user_id or principal.subject_id}
    envelope.update(sender=actor, submitted_by=actor, entrypoint="web")
    result = invoke(lambda: service.submit(project_id, delivery_session_id, envelope))
    response.status_code = 202 if result["created"] else 200
    return result
