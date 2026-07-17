"""Project-scoped external Agent build sessions, checkpoints, and Ontology leases."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    BuildCheckpointCreate,
    BuildSessionCancel,
    BuildSessionComplete,
    BuildSessionCreate,
    BuildSessionResume,
    InitialBuildCheckpoint,
    OntologyLeaseAcquire,
    OntologyLeaseRelease,
    OntologyLeaseRenew,
)
from app.core.config import Settings
from app.repositories.models import (
    BuildCheckpointModel,
    BuildSessionModel,
    CompetencyQuestionModel,
    EvidenceReferenceModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    OntologyLeaseModel,
    OntologyModel,
    OntologyWriteFenceModel,
    ProjectModel,
)
from app.services import interview
from app.services.ontology_workspace import OntologyWorkspaceService
from app.services.modeling_workspace import ModelingWorkspaceVersionService


class BuildSessionError(RuntimeError):
    """Stable service error shared by REST and MCP adapters."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        **detail: Any,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _id() -> str:
    return str(uuid4())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class BuildSessionService:
    def __init__(self, session: Session, settings: Settings, actor: str | None = None) -> None:
        self.session = session
        self.settings = settings
        self.actor = actor

    # ------------------------------------------------------------------
    # Public session and checkpoint workflow
    # ------------------------------------------------------------------

    def create_session(
        self, project_id: str, payload: BuildSessionCreate
    ) -> tuple[dict[str, Any], bool]:
        request_hash = _canonical_hash(payload)
        existing = self.session.scalar(
            select(BuildSessionModel).where(
                BuildSessionModel.project_id == project_id,
                BuildSessionModel.client_session_id == payload.client_session_id,
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.create_request_hash, request_hash)
            return self._session_summary(existing), False

        self._project(project_id)
        if payload.previous_session_id is not None:
            previous = self.session.get(BuildSessionModel, payload.previous_session_id)
            if previous is None or previous.project_id != project_id:
                raise BuildSessionError(
                    "build_session_not_found",
                    "Previous Build Session was not found",
                    status_code=404,
                )
        if payload.initial_checkpoint and payload.initial_checkpoint.ontology_id:
            self._ontology(project_id, payload.initial_checkpoint.ontology_id)

        now = self._database_now()
        build_session = BuildSessionModel(
            id=_id(),
            project_id=project_id,
            client_session_id=payload.client_session_id,
            create_request_hash=request_hash,
            previous_session_id=payload.previous_session_id,
            status="active",
            revision=1,
            unresolved_items=[],
            last_activity_at=now,
            created_by=self.actor,
        )
        self.session.add(build_session)
        checkpoint: BuildCheckpointModel | None = None
        if payload.initial_checkpoint is not None:
            checkpoint = self._new_checkpoint(
                build_session,
                payload.initial_checkpoint,
                sequence=1,
            )
            self.session.add(checkpoint)
            build_session.revision = 2

        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(BuildSessionModel).where(
                    BuildSessionModel.project_id == project_id,
                    BuildSessionModel.client_session_id == payload.client_session_id,
                )
            )
            if existing is None:
                raise
            self._assert_idempotent(existing.create_request_hash, request_hash)
            return self._session_summary(existing), False
        self.session.refresh(build_session)
        if checkpoint is not None:
            self.session.refresh(checkpoint)
        return self._session_summary(build_session, checkpoint), True

    def get_project_build_context(
        self,
        project_id: str,
        *,
        recent_session_limit: int = 10,
        recent_session_cursor: int = 0,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        recent_session_limit = max(1, min(recent_session_limit, 100))
        recent_session_cursor = max(0, recent_session_cursor)
        ontologies = list(
            self.session.scalars(
                select(OntologyModel)
                .where(OntologyModel.project_id == project_id)
                .order_by(OntologyModel.created_at, OntologyModel.id)
            )
        )
        question_counts: dict[str, int] = {}
        question_rows = self.session.execute(
            select(
                CompetencyQuestionModel.status,
                CompetencyQuestionModel.active,
                func.count(CompetencyQuestionModel.id),
            )
            .where(CompetencyQuestionModel.project_id == project_id)
            .group_by(CompetencyQuestionModel.status, CompetencyQuestionModel.active)
        )
        for status, active, count in question_rows:
            key = status if active else "inactive"
            question_counts[key] = question_counts.get(key, 0) + int(count)

        workspace_service = OntologyWorkspaceService(self.session, self.settings)
        version_service = ModelingWorkspaceVersionService(self.session, self.settings)
        ontology_state: list[dict[str, Any]] = []
        for ontology in ontologies:
            workspace = workspace_service.context(ontology.id)
            fence = self.session.get(OntologyWriteFenceModel, ontology.id)
            recent_batch = self.session.scalar(
                select(ModelingBatchModel)
                .where(ModelingBatchModel.ontology_id == ontology.id)
                .order_by(ModelingBatchModel.created_at.desc(), ModelingBatchModel.id.desc())
                .limit(1)
            )
            workspace_version = None
            if workspace["default_graph_set_id"] is not None:
                workspace_version = version_service.version_for(ontology.id)
            ontology_state.append(
                {
                    "id": ontology.id,
                    "name": ontology.name,
                    "status": ontology.status,
                    "workspace": {
                        "state": workspace["state"],
                        "workspace_version": workspace_version,
                        "editable": workspace["state"] == "ready"
                        and any(member["editable"] for member in workspace["members"]),
                        "issues": []
                        if workspace["state"] == "ready"
                        else ["semantic_workspace_incomplete"],
                    },
                    "modeling": {
                        "fenced": fence is not None,
                        "recovering_attempt_id": fence.attempt_id if fence else None,
                        "recent_batch": (
                            self._modeling_batch_summary(recent_batch)
                            if recent_batch is not None
                            else None
                        ),
                    },
                }
            )

        active = list(
            self.session.scalars(
                select(BuildSessionModel)
                .where(
                    BuildSessionModel.project_id == project_id,
                    BuildSessionModel.status == "active",
                )
                .order_by(BuildSessionModel.last_activity_at.desc(), BuildSessionModel.id)
            )
        )
        terminal = list(
            self.session.scalars(
                select(BuildSessionModel)
                .where(
                    BuildSessionModel.project_id == project_id,
                    BuildSessionModel.status.in_(("completed", "cancelled")),
                )
                .order_by(BuildSessionModel.last_activity_at.desc(), BuildSessionModel.id)
                .offset(recent_session_cursor)
                .limit(recent_session_limit + 1)
            )
        )
        has_more = len(terminal) > recent_session_limit
        terminal_page = terminal[:recent_session_limit]
        unresolved_items = [
            item
            for build_session in terminal_page
            for item in (build_session.unresolved_items or [])
        ]
        recent_batches = list(
            self.session.scalars(
                select(ModelingBatchModel)
                .where(ModelingBatchModel.project_id == project_id)
                .order_by(ModelingBatchModel.created_at.desc(), ModelingBatchModel.id.desc())
                .limit(20)
            )
        )
        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
            },
            "generated_at": self._database_now(),
            "platform_state": {
                "project_brief": interview.get_project_brief(self.session, project_id),
                "competency_question_counts": question_counts,
                "ontologies": ontology_state,
                "evidence_reference_count": int(
                    self.session.scalar(
                        select(func.count(EvidenceReferenceModel.id)).where(
                            EvidenceReferenceModel.project_id == project_id
                        )
                    )
                    or 0
                ),
                "modeling_batches": [self._modeling_batch_summary(item) for item in recent_batches],
            },
            "agent_state": {
                "active_sessions": [self._session_summary(item) for item in active],
                "recent_sessions": [self._session_summary(item) for item in terminal_page],
                "recent_sessions_next_cursor": (
                    recent_session_cursor + recent_session_limit if has_more else None
                ),
                "unresolved_items": unresolved_items,
            },
        }

    def get_session_detail(
        self,
        session_id: str,
        *,
        checkpoint_limit: int = 50,
        checkpoint_cursor: int | None = None,
    ) -> dict[str, Any]:
        build_session = self._build_session(session_id)
        limit = max(1, min(checkpoint_limit, 100))
        statement = select(BuildCheckpointModel).where(
            BuildCheckpointModel.build_session_id == session_id
        )
        if checkpoint_cursor is not None:
            statement = statement.where(BuildCheckpointModel.sequence < checkpoint_cursor)
        checkpoints = list(
            self.session.scalars(
                statement.order_by(BuildCheckpointModel.sequence.desc()).limit(limit + 1)
            )
        )
        has_more = len(checkpoints) > limit
        checkpoint_page = checkpoints[:limit]
        latest = self._latest_checkpoint(session_id)

        ontology_ids = set(
            self.session.scalars(
                select(BuildCheckpointModel.ontology_id).where(
                    BuildCheckpointModel.build_session_id == session_id,
                    BuildCheckpointModel.ontology_id.is_not(None),
                )
            )
        )
        leases = list(
            self.session.scalars(
                select(OntologyLeaseModel)
                .where(OntologyLeaseModel.build_session_id == session_id)
                .order_by(OntologyLeaseModel.updated_at.desc())
            )
        )
        ontology_ids.update(lease.ontology_id for lease in leases)
        recent_activity = self._recent_activity(
            list(
                self.session.scalars(
                    select(BuildCheckpointModel).where(
                        BuildCheckpointModel.build_session_id == session_id
                    )
                )
            ),
            leases,
        )
        session_batches = list(
            self.session.scalars(
                select(ModelingBatchModel)
                .where(ModelingBatchModel.build_session_id == session_id)
                .order_by(ModelingBatchModel.created_at.desc(), ModelingBatchModel.id.desc())
                .limit(50)
            )
        )
        return {
            "session": self._session_summary(build_session, latest),
            "latest_checkpoint": self._checkpoint_read(latest) if latest else None,
            "checkpoints": [self._checkpoint_read(item) for item in checkpoint_page],
            "checkpoints_next_cursor": (
                checkpoint_page[-1].sequence if has_more and checkpoint_page else None
            ),
            "involved_ontology_ids": sorted(item for item in ontology_ids if item),
            "leases": [self._lease_summary(item) for item in leases],
            "modeling_batches": [self._modeling_batch_summary(item) for item in session_batches],
            "evidence": {"references": [], "next_cursor": None},
            "recent_activity": recent_activity,
        }

    def resume_session(self, session_id: str, payload: BuildSessionResume) -> dict[str, Any]:
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        self._assert_session_revision(build_session, payload.expected_revision)
        build_session.last_resume_request_id = payload.client_request_id
        build_session.last_activity_at = self._database_now()
        self.session.commit()
        return self.get_session_detail(session_id)

    def save_checkpoint(self, session_id: str, payload: BuildCheckpointCreate) -> dict[str, Any]:
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        existing = self.session.scalar(
            select(BuildCheckpointModel).where(
                BuildCheckpointModel.build_session_id == session_id,
                BuildCheckpointModel.client_checkpoint_id == payload.client_checkpoint_id,
            )
        )
        if existing is not None:
            if not self._checkpoint_matches(existing, payload):
                raise BuildSessionError(
                    "idempotency_conflict",
                    "Checkpoint ID was already used with different content",
                )
            return {
                "session": self._session_summary(build_session),
                "checkpoint": self._checkpoint_read(existing),
            }
        self._assert_session_revision(build_session, payload.expected_revision)
        if payload.ontology_id is not None:
            self._ontology(build_session.project_id, payload.ontology_id)
        sequence = (
            int(
                self.session.scalar(
                    select(func.max(BuildCheckpointModel.sequence)).where(
                        BuildCheckpointModel.build_session_id == session_id
                    )
                )
                or 0
            )
            + 1
        )
        checkpoint = self._new_checkpoint(build_session, payload, sequence=sequence)
        self.session.add(checkpoint)
        build_session.revision += 1
        build_session.last_activity_at = self._database_now()
        self.session.commit()
        self.session.refresh(checkpoint)
        self.session.refresh(build_session)
        return {
            "session": self._session_summary(build_session, checkpoint),
            "checkpoint": self._checkpoint_read(checkpoint),
        }

    def complete_session(self, session_id: str, payload: BuildSessionComplete) -> dict[str, Any]:
        request_hash = _canonical_hash({"operation": "complete", **payload.model_dump(mode="json")})
        build_session = self._build_session(session_id, lock=True)
        terminal = self._terminal_retry(build_session, payload.client_request_id, request_hash)
        if terminal is not None:
            return terminal
        self._assert_active(build_session)
        self._assert_session_revision(build_session, payload.expected_revision)
        self._assert_no_in_flight_batch(build_session.id)
        now = self._database_now()
        build_session.status = "completed"
        build_session.revision += 1
        build_session.terminal_request_id = payload.client_request_id
        build_session.terminal_request_hash = request_hash
        build_session.completion_summary = payload.summary
        build_session.unresolved_items = list(payload.unresolved_items)
        build_session.completed_at = now
        build_session.last_activity_at = now
        self._release_all_leases(build_session.id, now)
        self.session.commit()
        self.session.refresh(build_session)
        return self._session_summary(build_session)

    def cancel_session(self, session_id: str, payload: BuildSessionCancel) -> dict[str, Any]:
        request_hash = _canonical_hash({"operation": "cancel", **payload.model_dump(mode="json")})
        build_session = self._build_session(session_id, lock=True)
        terminal = self._terminal_retry(build_session, payload.client_request_id, request_hash)
        if terminal is not None:
            return terminal
        self._assert_active(build_session)
        self._assert_session_revision(build_session, payload.expected_revision)
        self._assert_no_in_flight_batch(build_session.id)
        now = self._database_now()
        build_session.status = "cancelled"
        build_session.revision += 1
        build_session.terminal_request_id = payload.client_request_id
        build_session.terminal_request_hash = request_hash
        build_session.cancel_reason = payload.reason
        build_session.cancelled_at = now
        build_session.last_activity_at = now
        self._release_all_leases(build_session.id, now)
        self.session.commit()
        self.session.refresh(build_session)
        return self._session_summary(build_session)

    # ------------------------------------------------------------------
    # Ontology lease workflow
    # ------------------------------------------------------------------

    def acquire_ontology_lease(
        self,
        session_id: str,
        ontology_id: str,
        payload: OntologyLeaseAcquire,
    ) -> dict[str, Any]:
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        self._assert_session_revision(build_session, payload.expected_session_revision)
        self._ontology(build_session.project_id, ontology_id, lock=True)
        self._assert_not_fenced(ontology_id)
        now = self._database_now()
        lease = self._lease(ontology_id, lock=True)
        request_hash = _canonical_hash(payload)
        if lease is not None and self._lease_is_active(lease, now):
            if lease.build_session_id != session_id:
                raise BuildSessionError(
                    "ontology_lease_conflict",
                    "Ontology is currently leased by another Build Session",
                    expires_at=lease.expires_at,
                )
            self._assert_request_id(lease, "acquire", payload.client_request_id, request_hash)
            # The plaintext token is never stored. Re-acquiring an already-held lease
            # therefore rotates it so the caller always receives a usable token.
            return self._rotate_lease(
                lease,
                build_session,
                payload.client_request_id,
                request_hash,
                now,
            )

        token = secrets.token_urlsafe(32)
        if lease is None:
            lease = OntologyLeaseModel(
                ontology_id=ontology_id,
                project_id=build_session.project_id,
                build_session_id=session_id,
                token_hash=_token_hash(token),
                revision=1,
                acquired_by=self.actor,
                acquired_at=now,
                expires_at=now + timedelta(seconds=self.settings.build_session_lease_ttl_seconds),
                last_request_id=payload.client_request_id,
                last_request_operation="acquire",
                last_request_hash=request_hash,
            )
            self.session.add(lease)
        else:
            lease.project_id = build_session.project_id
            lease.build_session_id = session_id
            lease.token_hash = _token_hash(token)
            lease.revision += 1
            lease.acquired_by = self.actor
            lease.acquired_at = now
            lease.renewed_at = None
            lease.expires_at = now + timedelta(
                seconds=self.settings.build_session_lease_ttl_seconds
            )
            lease.released_at = None
            lease.last_request_id = payload.client_request_id
            lease.last_request_operation = "acquire"
            lease.last_request_hash = request_hash
        build_session.last_activity_at = now
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            current = self._lease(ontology_id, lock=True)
            if current is not None and self._lease_is_active(current, self._database_now()):
                raise BuildSessionError(
                    "ontology_lease_conflict",
                    "Ontology is currently leased by another Build Session",
                    expires_at=current.expires_at,
                )
            raise
        self.session.refresh(lease)
        return self._lease_token_response(lease, token)

    def renew_ontology_lease(
        self,
        session_id: str,
        ontology_id: str,
        payload: OntologyLeaseRenew,
    ) -> dict[str, Any]:
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        self._ontology(build_session.project_id, ontology_id, lock=True)
        self._assert_not_fenced(ontology_id)
        lease = self._lease(ontology_id, lock=True)
        if lease is None or lease.build_session_id != session_id:
            raise BuildSessionError(
                "ontology_lease_conflict", "Build Session does not hold this Ontology lease"
            )
        request_hash = _canonical_hash(payload)
        if lease.last_request_id == payload.client_request_id:
            self._assert_request_id(lease, "renew", payload.client_request_id, request_hash)
            if not self._lease_is_active(lease, self._database_now()):
                raise BuildSessionError("lease_expired", "Ontology lease has expired")
            return self._lease_token_response(lease, payload.lease_token)

        self._assert_lease_revision(lease, payload.expected_lease_revision)
        self._assert_lease_token(lease, payload.lease_token)
        now = self._database_now()
        if not self._lease_is_active(lease, now):
            raise BuildSessionError("lease_expired", "Ontology lease has expired")
        lease.revision += 1
        lease.renewed_at = now
        lease.expires_at = now + timedelta(seconds=self.settings.build_session_lease_ttl_seconds)
        lease.last_request_id = payload.client_request_id
        lease.last_request_operation = "renew"
        lease.last_request_hash = request_hash
        build_session.last_activity_at = now
        self.session.commit()
        self.session.refresh(lease)
        return self._lease_token_response(lease, payload.lease_token)

    def release_ontology_lease(
        self,
        session_id: str,
        ontology_id: str,
        payload: OntologyLeaseRelease,
    ) -> dict[str, Any]:
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        self._ontology(build_session.project_id, ontology_id, lock=True)
        self._assert_not_fenced(ontology_id)
        lease = self._lease(ontology_id, lock=True)
        if lease is None or lease.build_session_id != session_id:
            raise BuildSessionError(
                "ontology_lease_conflict", "Build Session does not hold this Ontology lease"
            )
        request_hash = _canonical_hash(payload)
        if lease.last_request_id == payload.client_request_id:
            self._assert_request_id(lease, "release", payload.client_request_id, request_hash)
            return self._released_response(lease)

        self._assert_lease_revision(lease, payload.expected_lease_revision)
        self._assert_lease_token(lease, payload.lease_token)
        now = self._database_now()
        if not self._lease_is_active(lease, now):
            raise BuildSessionError("lease_expired", "Ontology lease has expired")
        lease.revision += 1
        lease.released_at = now
        lease.last_request_id = payload.client_request_id
        lease.last_request_operation = "release"
        lease.last_request_hash = request_hash
        build_session.last_activity_at = now
        self.session.commit()
        self.session.refresh(lease)
        return self._released_response(lease)

    def authorize_apply(
        self,
        *,
        session_id: str,
        ontology_id: str,
        lease_token: str,
        expected_workspace_version: str,
    ) -> dict[str, Any]:
        """Narrow R-004 guard: validate session, lease, and workspace version."""
        build_session = self._build_session(session_id, lock=True)
        self._assert_active(build_session)
        self._ontology(build_session.project_id, ontology_id, lock=True)
        self._assert_not_fenced(ontology_id)
        lease = self._lease(ontology_id, lock=True)
        if lease is None or lease.build_session_id != session_id:
            raise BuildSessionError(
                "ontology_lease_conflict", "Build Session does not hold this Ontology lease"
            )
        self._assert_lease_token(lease, lease_token)
        if not self._lease_is_active(lease, self._database_now()):
            raise BuildSessionError("lease_expired", "Ontology lease has expired")
        workspace = OntologyWorkspaceService(self.session, self.settings).context(ontology_id)
        graph_set_id = workspace["default_graph_set_id"]
        if workspace["state"] != "ready" or graph_set_id is None:
            raise BuildSessionError(
                "workspace_revision_conflict", "Ontology workspace is incomplete"
            )
        current_version = ModelingWorkspaceVersionService(self.session, self.settings).version_for(
            ontology_id
        )
        if current_version != expected_workspace_version:
            raise BuildSessionError(
                "workspace_revision_conflict",
                "Ontology workspace changed after the caller last read it",
                current_workspace_version=current_version,
            )
        return {
            "build_session_id": session_id,
            "ontology_id": ontology_id,
            "graph_set_id": graph_set_id,
            "workspace_version": current_version,
            "lease_revision": lease.revision,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _database_now(self) -> datetime:
        value = self.session.scalar(select(func.now()))
        if not isinstance(value, datetime):
            return datetime.now(timezone.utc)
        return _as_utc(value)

    def _project(self, project_id: str) -> ProjectModel:
        project = self.session.get(ProjectModel, project_id)
        if project is None:
            raise BuildSessionError("project_not_found", "Project was not found", status_code=404)
        return project

    def _ontology(self, project_id: str, ontology_id: str, *, lock: bool = False) -> OntologyModel:
        statement = select(OntologyModel).where(OntologyModel.id == ontology_id)
        if lock:
            statement = statement.with_for_update()
        ontology = self.session.scalar(statement)
        if ontology is None or ontology.project_id != project_id:
            raise BuildSessionError("ontology_not_found", "Ontology was not found", status_code=404)
        return ontology

    def _build_session(self, session_id: str, *, lock: bool = False) -> BuildSessionModel:
        statement = select(BuildSessionModel).where(BuildSessionModel.id == session_id)
        if lock:
            statement = statement.with_for_update()
        build_session = self.session.scalar(statement)
        if build_session is None:
            raise BuildSessionError(
                "build_session_not_found",
                "Build Session was not found",
                status_code=404,
            )
        return build_session

    def _lease(self, ontology_id: str, *, lock: bool = False) -> OntologyLeaseModel | None:
        statement = select(OntologyLeaseModel).where(OntologyLeaseModel.ontology_id == ontology_id)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _assert_not_fenced(self, ontology_id: str) -> None:
        fence = self.session.get(OntologyWriteFenceModel, ontology_id)
        if fence is not None:
            raise BuildSessionError(
                "ontology_write_fenced",
                "Ontology has an in-flight Modeling Batch write",
                attempt_id=fence.attempt_id,
            )

    def _assert_no_in_flight_batch(self, build_session_id: str) -> None:
        in_flight = self.session.scalar(
            select(ModelingBatchAttemptModel.id)
            .where(
                ModelingBatchAttemptModel.build_session_id == build_session_id,
                ModelingBatchAttemptModel.status.in_(("validating", "applying", "recovering")),
                ModelingBatchAttemptModel.mode != "dry_run",
            )
            .limit(1)
        )
        if in_flight is not None:
            raise BuildSessionError(
                "in_flight_batch",
                "Build Session has an in-flight Modeling Batch",
                attempt_id=in_flight,
            )

    def _latest_checkpoint(self, session_id: str) -> BuildCheckpointModel | None:
        return self.session.scalar(
            select(BuildCheckpointModel)
            .where(BuildCheckpointModel.build_session_id == session_id)
            .order_by(BuildCheckpointModel.sequence.desc())
            .limit(1)
        )

    def _new_checkpoint(
        self,
        build_session: BuildSessionModel,
        payload: InitialBuildCheckpoint | BuildCheckpointCreate,
        *,
        sequence: int,
    ) -> BuildCheckpointModel:
        failure = payload.failure
        return BuildCheckpointModel(
            id=_id(),
            build_session_id=build_session.id,
            client_checkpoint_id=payload.client_checkpoint_id,
            sequence=sequence,
            ontology_id=payload.ontology_id,
            phase=payload.phase,
            current_step=payload.current_step,
            next_step=payload.next_step,
            summary=payload.summary,
            blockers=list(payload.blockers),
            failure_code=failure.code if failure else None,
            failure_message=failure.message if failure else None,
            related_batch_id=payload.related_batch_id,
            reported_by=self.actor,
        )

    def _session_summary(
        self,
        build_session: BuildSessionModel,
        latest: BuildCheckpointModel | None = None,
    ) -> dict[str, Any]:
        if latest is None:
            latest = self._latest_checkpoint(build_session.id)
        return {
            "id": build_session.id,
            "project_id": build_session.project_id,
            "client_session_id": build_session.client_session_id,
            "previous_session_id": build_session.previous_session_id,
            "status": build_session.status,
            "revision": build_session.revision,
            "created_by": build_session.created_by,
            "completion_summary": build_session.completion_summary,
            "unresolved_items": list(build_session.unresolved_items or []),
            "cancel_reason": build_session.cancel_reason,
            "last_activity_at": build_session.last_activity_at,
            "completed_at": build_session.completed_at,
            "cancelled_at": build_session.cancelled_at,
            "created_at": build_session.created_at,
            "updated_at": build_session.updated_at,
            "latest_checkpoint": self._checkpoint_read(latest) if latest else None,
        }

    @staticmethod
    def _checkpoint_read(checkpoint: BuildCheckpointModel) -> dict[str, Any]:
        failure = None
        if checkpoint.failure_code is not None:
            failure = {
                "code": checkpoint.failure_code,
                "message": checkpoint.failure_message or "",
            }
        return {
            "id": checkpoint.id,
            "build_session_id": checkpoint.build_session_id,
            "client_checkpoint_id": checkpoint.client_checkpoint_id,
            "sequence": checkpoint.sequence,
            "ontology_id": checkpoint.ontology_id,
            "phase": checkpoint.phase,
            "current_step": checkpoint.current_step,
            "next_step": checkpoint.next_step,
            "summary": checkpoint.summary,
            "blockers": list(checkpoint.blockers or []),
            "failure": failure,
            "related_batch_id": checkpoint.related_batch_id,
            "reported_by": checkpoint.reported_by,
            "created_at": checkpoint.created_at,
        }

    @staticmethod
    def _modeling_batch_summary(batch: ModelingBatchModel) -> dict[str, Any]:
        latest = batch.attempts[-1] if batch.attempts else None
        return {
            "batch_id": batch.id,
            "client_batch_id": batch.client_batch_id,
            "ontology_id": batch.ontology_id,
            "build_session_id": batch.build_session_id,
            "batch_status": batch.status,
            "item_count": len(batch.items),
            "latest_attempt": (
                {
                    "attempt_id": latest.id,
                    "mode": latest.mode,
                    "attempt_status": latest.status,
                    "finding_count": len(latest.findings or []),
                    "recovery_state": latest.recovery_state,
                }
                if latest
                else None
            ),
            "created_at": batch.created_at,
            "terminal_at": batch.terminal_at,
        }

    def _lease_summary(self, lease: OntologyLeaseModel) -> dict[str, Any]:
        now = self._database_now()
        state = (
            "released"
            if lease.released_at is not None
            else ("active" if self._lease_is_active(lease, now) else "expired")
        )
        return {
            "ontology_id": lease.ontology_id,
            "build_session_id": lease.build_session_id,
            "lease_revision": lease.revision,
            "state": state,
            "acquired_at": lease.acquired_at,
            "renewed_at": lease.renewed_at,
            "expires_at": lease.expires_at,
            "released_at": lease.released_at,
        }

    @staticmethod
    def _lease_token_response(lease: OntologyLeaseModel, token: str) -> dict[str, Any]:
        return {
            "ontology_id": lease.ontology_id,
            "build_session_id": lease.build_session_id,
            "lease_token": token,
            "lease_revision": lease.revision,
            "expires_at": lease.expires_at,
            "state": "active",
        }

    @staticmethod
    def _released_response(lease: OntologyLeaseModel) -> dict[str, Any]:
        return {
            "ontology_id": lease.ontology_id,
            "build_session_id": lease.build_session_id,
            "lease_revision": lease.revision,
            "expires_at": lease.expires_at,
            "released_at": lease.released_at,
            "state": "released",
            "released": True,
        }

    def _rotate_lease(
        self,
        lease: OntologyLeaseModel,
        build_session: BuildSessionModel,
        request_id: str,
        request_hash: str,
        now: datetime,
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        lease.token_hash = _token_hash(token)
        lease.revision += 1
        lease.renewed_at = now
        lease.expires_at = now + timedelta(seconds=self.settings.build_session_lease_ttl_seconds)
        lease.last_request_id = request_id
        lease.last_request_operation = "acquire"
        lease.last_request_hash = request_hash
        build_session.last_activity_at = now
        self.session.commit()
        self.session.refresh(lease)
        return self._lease_token_response(lease, token)

    @staticmethod
    def _lease_is_active(lease: OntologyLeaseModel, now: datetime) -> bool:
        return lease.released_at is None and _as_utc(lease.expires_at) > _as_utc(now)

    @staticmethod
    def _assert_active(build_session: BuildSessionModel) -> None:
        if build_session.status != "active":
            raise BuildSessionError("session_terminal", "Build Session is already terminal")

    @staticmethod
    def _assert_session_revision(build_session: BuildSessionModel, expected_revision: int) -> None:
        if build_session.revision != expected_revision:
            raise BuildSessionError(
                "session_revision_conflict",
                "Build Session changed after the caller last read it",
                current_revision=build_session.revision,
            )

    @staticmethod
    def _assert_lease_revision(lease: OntologyLeaseModel, expected_revision: int) -> None:
        if lease.revision != expected_revision:
            raise BuildSessionError(
                "lease_revision_conflict",
                "Ontology lease changed after the caller last read it",
                current_revision=lease.revision,
            )

    @staticmethod
    def _assert_lease_token(lease: OntologyLeaseModel, token: str) -> None:
        if not secrets.compare_digest(lease.token_hash, _token_hash(token)):
            raise BuildSessionError(
                "lease_token_invalid", "Ontology lease token is no longer valid"
            )

    @staticmethod
    def _assert_idempotent(stored_hash: str, request_hash: str) -> None:
        if stored_hash != request_hash:
            raise BuildSessionError(
                "idempotency_conflict",
                "Client request ID was already used with different content",
            )

    @staticmethod
    def _assert_request_id(
        lease: OntologyLeaseModel,
        operation: str,
        request_id: str,
        request_hash: str,
    ) -> None:
        if lease.last_request_id != request_id:
            return
        if lease.last_request_operation != operation or lease.last_request_hash != request_hash:
            raise BuildSessionError(
                "idempotency_conflict",
                "Client request ID was already used with different content",
            )

    def _terminal_retry(
        self, build_session: BuildSessionModel, request_id: str, request_hash: str
    ) -> dict[str, Any] | None:
        if build_session.terminal_request_id == request_id:
            self._assert_idempotent(build_session.terminal_request_hash or "", request_hash)
            return self._session_summary(build_session)
        return None

    @staticmethod
    def _checkpoint_matches(
        checkpoint: BuildCheckpointModel, payload: BuildCheckpointCreate
    ) -> bool:
        failure = payload.failure
        return (
            checkpoint.phase == payload.phase
            and checkpoint.current_step == payload.current_step
            and checkpoint.next_step == payload.next_step
            and checkpoint.ontology_id == payload.ontology_id
            and checkpoint.summary == payload.summary
            and list(checkpoint.blockers or []) == list(payload.blockers)
            and checkpoint.failure_code == (failure.code if failure else None)
            and checkpoint.failure_message == (failure.message if failure else None)
            and checkpoint.related_batch_id == payload.related_batch_id
        )

    def _release_all_leases(self, session_id: str, now: datetime) -> None:
        leases = list(
            self.session.scalars(
                select(OntologyLeaseModel)
                .where(
                    OntologyLeaseModel.build_session_id == session_id,
                    OntologyLeaseModel.released_at.is_(None),
                )
                .with_for_update()
            )
        )
        for lease in leases:
            lease.revision += 1
            lease.released_at = now

    @staticmethod
    def _recent_activity(
        checkpoints: list[BuildCheckpointModel], leases: list[OntologyLeaseModel]
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = [
            {
                "type": "checkpoint_saved",
                "at": checkpoint.created_at,
                "checkpoint_id": checkpoint.id,
                "ontology_id": checkpoint.ontology_id,
            }
            for checkpoint in checkpoints
        ]
        for lease in leases:
            if lease.released_at is not None:
                event_type = "lease_released"
                at = lease.released_at
            elif lease.renewed_at is not None:
                event_type = "lease_renewed"
                at = lease.renewed_at
            else:
                event_type = "lease_acquired"
                at = lease.acquired_at
            events.append(
                {
                    "type": event_type,
                    "at": at,
                    "ontology_id": lease.ontology_id,
                }
            )
        events.sort(key=lambda item: _as_utc(item["at"]), reverse=True)
        return events[:50]
