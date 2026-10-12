"""Private usage observations, independent of recall execution and Team lifetime."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from functools import wraps
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy.exc import SQLAlchemyError

from app.api.schemas import SemanticContextQueryRequest
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.semantic_feedback import SemanticFeedbackRepository
from app.security.auth import AuthPrincipal
from typing import Any, Literal


class FeedbackError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: UUID
    query_request: SemanticContextQueryRequest
    reasons: list[Literal["incomplete", "incorrect", "irrelevant", "other"]] = Field(min_length=1)
    description: str = Field(min_length=1, max_length=65536)
    result_snapshot: dict[str, Any] | None = None
    snapshot_complete: bool = False

    @model_validator(mode="after")
    def validate_snapshot(self):
        scope = self.query_request
        if scope.scope_mode == "ontologies" and not scope.ontology_ids:
            raise ValueError("query_request.ontology_ids must be nonempty for ontologies scope")
        if scope.scope_mode == "project" and scope.ontology_ids:
            raise ValueError("query_request.ontology_ids must be empty for project scope")
        if len(set(scope.ontology_ids)) != len(scope.ontology_ids):
            raise ValueError("query_request.ontology_ids must be unique")
        if self.result_snapshot is not None:
            try:
                json.dumps(self.result_snapshot, allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise ValueError("result_snapshot must contain finite JSON values") from exc
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons must be unique")
        if self.result_snapshot is None and self.snapshot_complete:
            raise ValueError("snapshot_complete must be false when result_snapshot is missing")
        return self


class FeedbackVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1)
    model_revisions: dict[str, StrictInt] = Field(min_length=1)
    readback_references: list[str] = Field(min_length=1)
    independent_validation_reference: str | None = None

    @model_validator(mode="after")
    def validate_references(self):
        if any(not key or value < 0 for key, value in self.model_revisions.items()):
            raise ValueError("model_revisions requires Ontology IDs and nonnegative revisions")
        if any(not ref.strip() for ref in self.readback_references):
            raise ValueError("readback_references must be nonempty")
        if (
            self.independent_validation_reference is not None
            and not self.independent_validation_reference.strip()
        ):
            raise ValueError("independent_validation_reference must be nonempty")
        return self


class FeedbackResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["unresolved", "needs_clarification", "resolved", "no_change_needed"]
    explanation: str = Field(min_length=1, max_length=65536)
    diagnosis: Literal[
        "model_expression", "retrieval", "consumer_understanding", "visibility", "unknown"
    ] = "unknown"
    run_reference: str | None = None
    operation_reference: str | None = None
    verification: FeedbackVerification | None = None

    @model_validator(mode="after")
    def validate_conclusion(self):
        if self.outcome in {"resolved", "no_change_needed"} and self.verification is None:
            raise ValueError("verification with actual readback and model revisions is required")
        if (
            self.outcome == "resolved"
            and self.verification is not None
            and not self.verification.independent_validation_reference
        ):
            raise ValueError("resolved requires an independent_validation_reference")
        return self


def _database_boundary(fn):
    @wraps(fn)
    def run(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise FeedbackError(
                "dependency_error",
                "Feedback storage unavailable; retry with the "
                "same feedback_id and unchanged submission",
                503,
            ) from exc

    return run


class SemanticFeedbackService:
    def __init__(self, session, principal: AuthPrincipal):
        self.session = session
        self.principal = principal
        self.repository = SemanticFeedbackRepository(session)

    def _authorize(self, project_id: str, scope: str):
        if (
            scope not in self.principal.effective_scopes
            or (self.principal.project_id is not None and self.principal.project_id != project_id)
            or self.session.get(ProjectModel, project_id) is None
        ):
            raise FeedbackError("forbidden_scope", "Feedback scope is not authorized", 403)

    def _receipt(self, row):
        stamp = row.created_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return {
            "feedback_id": row.feedback_id,
            "received_at": stamp.isoformat(),
            "status": "received",
        }

    def _read(self, row):
        return {
            **self._receipt(row),
            "project_id": row.project_id,
            "submitted_by": row.submitted_by,
            "submission": row.submission,
            "resolution_history": row.resolution_history,
            "outcome": row.outcome,
        }

    def _row(self, feedback_id: str, *, lock: bool = False):
        row = self.repository.get(feedback_id, lock=lock)
        if row is None or (
            self.principal.project_id is not None and row.project_id != self.principal.project_id
        ):
            raise FeedbackError("not_found", "Feedback not found", 404)
        self._authorize(row.project_id, "admin")
        return row

    @_database_boundary
    def submit(self, payload: dict):
        request = FeedbackSubmission.model_validate(payload)
        project_id = request.query_request.project_id
        self._authorize(project_id, "read")
        for ontology_id in request.query_request.ontology_ids or []:
            ontology = self.session.get(OntologyModel, ontology_id)
            if ontology is None or ontology.project_id != project_id:
                raise FeedbackError("forbidden_scope", "Feedback scope is not authorized", 403)
        if request.result_snapshot is not None:
            size = len(
                json.dumps(
                    request.result_snapshot,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            if size > 256 * 1024:
                raise FeedbackError(
                    "feedback_snapshot_too_large",
                    "result_snapshot exceeds 256 KiB; "
                    "retain relevant results, set snapshot_complete=false and retry",
                    413,
                )
        # Preserve the supplied body, including old revisions and query text, not model defaults.
        submission = json.loads(
            json.dumps(
                {
                    **payload,
                    "feedback_id": str(request.feedback_id),
                    "result_snapshot": request.result_snapshot,
                    "snapshot_complete": request.snapshot_complete,
                },
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        row = self.repository.create(
            str(request.feedback_id),
            project_id,
            self.principal.subject_type + ":" + self.principal.subject_id,
            submission,
        )
        if row.submitted_by != self.principal.subject_type + ":" + self.principal.subject_id:
            raise FeedbackError(
                "feedback_identity_conflict", "Feedback ID unavailable; use a new ID", 409
            )
        if row.submission != submission:
            raise FeedbackError(
                "feedback_identity_conflict",
                "feedback_id already binds different content; retry unchanged or use a new ID",
                409,
            )
        return self._receipt(row)

    @_database_boundary
    def get(self, feedback_id: str):
        if "admin" not in self.principal.effective_scopes:
            raise FeedbackError("forbidden_scope", "Feedback scope is not authorized", 403)
        return self._read(self._row(feedback_id))

    @_database_boundary
    def list(
        self,
        project_id: str,
        *,
        pending_only: bool = True,
        limit: int = 50,
        cursor: str | None = None,
    ):
        self._authorize(project_id, "admin")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise FeedbackError("validation_error", "limit must be between 1 and 200")
        after = None
        if cursor:
            try:
                saved_project, stamp, fid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if saved_project != project_id:
                    raise ValueError()
                after = (datetime.fromisoformat(stamp), str(UUID(fid)))
            except (ValueError, TypeError, UnicodeError) as exc:
                raise FeedbackError(
                    "validation_error", "Invalid cursor; restart feedback listing"
                ) from exc
        rows = self.repository.list(project_id, pending_only, limit + 1, after)
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if more:
            last = rows[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps([project_id, last.created_at.isoformat(), last.feedback_id]).encode()
            ).decode()
        return {
            "items": [self._read(row) for row in rows],
            "has_more": more,
            "next_cursor": next_cursor,
        }

    @_database_boundary
    def record_resolution(self, feedback_id: str, payload: dict):
        if "admin" not in self.principal.effective_scopes:
            raise FeedbackError("forbidden_scope", "Feedback scope is not authorized", 403)
        request = FeedbackResolution.model_validate(payload)
        row = self._row(feedback_id, lock=True)
        if request.verification:
            verification = request.verification
            if verification.project_id != row.project_id:
                raise FeedbackError(
                    "forbidden_scope", "Verification scope differs from feedback", 403
                )
            for oid, revision in verification.model_revisions.items():
                ontology = self.session.get(OntologyModel, oid)
                if ontology is None or ontology.project_id != row.project_id:
                    raise FeedbackError(
                        "forbidden_scope", "Verification scope is not authorized", 403
                    )
                if ontology.model_revision != revision:
                    raise FeedbackError(
                        "feedback_verification_stale",
                        "Read the current model and verify again before recording a conclusion",
                        409,
                    )
            submitted = row.submission["query_request"]
            if (
                submitted.get("scope_mode") == "ontologies"
                and not set(submitted.get("ontology_ids", []))
                <= verification.model_revisions.keys()
            ):
                raise FeedbackError(
                    "validation_error", "Verification must cover the reported Ontology scope"
                )
        resolution = {
            **request.model_dump(mode="json"),
            "resolution_id": str(uuid4()),
            "recorded_by": self.principal.subject_type + ":" + self.principal.subject_id,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        self.repository.append_resolution(row, resolution)
        return resolution
