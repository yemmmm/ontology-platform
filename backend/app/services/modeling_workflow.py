"""R1.1-002 immutable artifacts and append-only modeling execution records."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    ModelingExecutionEventCreate,
    ModelingWorkflowArtifactCreate,
    WorkflowRelatedResource,
)
from app.repositories.models import (
    BuildSessionModel,
    CompetencyQuestionModel,
    EvidenceReferenceModel,
    InterviewAnswerModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    ModelingExecutionEventModel,
    ModelingWorkflowArtifactModel,
    OntologyLeaseModel,
    OntologyModel,
    SemanticGraphSetModel,
    SemanticValidationRunModel,
)
from app.security.secrets import SecretDetected, scan_domain_payload
from app.services.ontology_lineage import OntologyLineageError, OntologyLineageService
from app.services.semantic_lineage_identity import InvalidLineageStatement

ARTIFACT_CONTENT_LIMIT = 1024 * 1024
EVENT_PAYLOAD_LIMIT = 64 * 1024
EXPORT_LIMIT = 8 * 1024 * 1024
RESOLVED_QUESTION_STATES = {"answered", "skipped", "uncertain"}


class ModelingWorkflowError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class ModelingWorkflowService:
    def __init__(
        self,
        session: Session,
        *,
        actor: str = "system:unattributed",
        lineage_service: OntologyLineageService | None = None,
    ) -> None:
        self.session = session
        self.actor = actor
        self.lineage_service = lineage_service or OntologyLineageService(session)

    # ------------------------------------------------------------------
    # Artifact versions
    # ------------------------------------------------------------------

    def create_artifact(
        self, build_session_id: str, payload: ModelingWorkflowArtifactCreate
    ) -> tuple[dict[str, Any], bool]:
        request = payload.model_dump(mode="json")
        self._reject_secrets(request)
        request_hash = _hash(request)
        build_session = self._build_session(build_session_id, lock=True)
        self._assert_active(build_session)

        existing = self.session.scalar(
            select(ModelingWorkflowArtifactModel).where(
                ModelingWorkflowArtifactModel.build_session_id == build_session_id,
                ModelingWorkflowArtifactModel.client_version_id == payload.client_version_id,
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return self._artifact_read(existing), False

        self._ontology(build_session.project_id, payload.ontology_id)
        normalized_content = request["content"]
        canonical_content = self._artifact_content(payload.content_format, normalized_content)
        if len(canonical_content) > ARTIFACT_CONTENT_LIMIT:
            raise ModelingWorkflowError(
                "workflow_artifact_too_large",
                "Modeling Workflow Artifact exceeds the 1 MiB limit",
                status_code=413,
                actual=len(canonical_content),
                limit=ARTIFACT_CONTENT_LIMIT,
            )

        latest = self.session.scalar(
            select(ModelingWorkflowArtifactModel)
            .where(
                ModelingWorkflowArtifactModel.build_session_id == build_session_id,
                ModelingWorkflowArtifactModel.artifact_key == payload.artifact_key,
            )
            .order_by(ModelingWorkflowArtifactModel.version.desc())
            .limit(1)
        )
        if latest is None:
            if payload.supersedes_workflow_artifact_id is not None:
                self._artifact_version_conflict("First version cannot supersede another version")
            version = 1
        else:
            if (
                payload.supersedes_workflow_artifact_id != latest.id
                or payload.artifact_type != latest.artifact_type
                or payload.ontology_id != latest.ontology_id
            ):
                self._artifact_version_conflict(
                    "New version must supersede the current version with the same type and scope",
                    current_workflow_artifact_id=latest.id,
                    current_version=latest.version,
                )
            version = latest.version + 1

        row = ModelingWorkflowArtifactModel(
            id=str(uuid4()),
            project_id=build_session.project_id,
            build_session_id=build_session_id,
            ontology_id=payload.ontology_id,
            artifact_key=payload.artifact_key,
            client_version_id=payload.client_version_id,
            request_hash=request_hash,
            version=version,
            artifact_type=payload.artifact_type,
            content_format=payload.content_format,
            content=normalized_content,
            content_hash=hashlib.sha256(canonical_content).hexdigest(),
            content_size_bytes=len(canonical_content),
            created_by=self.actor,
            created_by_role=payload.created_by_role,
            workflow_name=payload.workflow_name,
            workflow_version=payload.workflow_version,
            role_prompt_version=payload.role_prompt_version,
            supersedes_workflow_artifact_id=payload.supersedes_workflow_artifact_id,
        )
        self.session.add(row)
        build_session.last_activity_at = self._now()
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ModelingWorkflowArtifactModel).where(
                    ModelingWorkflowArtifactModel.build_session_id == build_session_id,
                    ModelingWorkflowArtifactModel.client_version_id == payload.client_version_id,
                )
            )
            if concurrent is None:
                self._artifact_version_conflict("Concurrent Artifact version conflict")
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return self._artifact_read(concurrent), False
        self.session.refresh(row)
        return self._artifact_read(row), True

    def get_artifact(self, workflow_artifact_id: str) -> dict[str, Any]:
        row = self.session.get(ModelingWorkflowArtifactModel, workflow_artifact_id)
        if row is None:
            raise ModelingWorkflowError(
                "modeling_workflow_artifact_not_found",
                "Modeling Workflow Artifact was not found",
                status_code=404,
            )
        return self._artifact_read(row)

    def list_artifacts(
        self,
        build_session_id: str,
        *,
        artifact_type: str | None = None,
        artifact_key: str | None = None,
        ontology_id: str | None = None,
        current_only: bool = False,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        self._build_session(build_session_id)
        limit = max(1, min(limit, 100))
        statement = select(ModelingWorkflowArtifactModel).where(
            ModelingWorkflowArtifactModel.build_session_id == build_session_id
        )
        if artifact_type:
            statement = statement.where(
                ModelingWorkflowArtifactModel.artifact_type == artifact_type
            )
        if artifact_key:
            statement = statement.where(ModelingWorkflowArtifactModel.artifact_key == artifact_key)
        if ontology_id:
            statement = statement.where(ModelingWorkflowArtifactModel.ontology_id == ontology_id)
        if current_only:
            newer = ModelingWorkflowArtifactModel.__table__.alias("newer_artifact")
            statement = statement.where(
                ~select(newer.c.id)
                .where(
                    newer.c.build_session_id == ModelingWorkflowArtifactModel.build_session_id,
                    newer.c.artifact_key == ModelingWorkflowArtifactModel.artifact_key,
                    newer.c.version > ModelingWorkflowArtifactModel.version,
                )
                .exists()
            )
        if cursor:
            cursor_row = self.session.get(ModelingWorkflowArtifactModel, cursor)
            if cursor_row is None or cursor_row.build_session_id != build_session_id:
                raise ModelingWorkflowError(
                    "invalid_modeling_workflow_payload",
                    "Artifact cursor is invalid",
                    status_code=422,
                )
            statement = statement.where(
                or_(
                    ModelingWorkflowArtifactModel.artifact_key > cursor_row.artifact_key,
                    and_(
                        ModelingWorkflowArtifactModel.artifact_key == cursor_row.artifact_key,
                        ModelingWorkflowArtifactModel.version > cursor_row.version,
                    ),
                    and_(
                        ModelingWorkflowArtifactModel.artifact_key == cursor_row.artifact_key,
                        ModelingWorkflowArtifactModel.version == cursor_row.version,
                        ModelingWorkflowArtifactModel.id > cursor_row.id,
                    ),
                )
            )
        rows = list(
            self.session.scalars(
                statement.order_by(
                    ModelingWorkflowArtifactModel.artifact_key,
                    ModelingWorkflowArtifactModel.version,
                    ModelingWorkflowArtifactModel.id,
                ).limit(limit + 1)
            )
        )
        page = rows[:limit]
        return {
            "items": [self._artifact_read(row) for row in page],
            "next_cursor": page[-1].id if len(rows) > limit and page else None,
        }

    # ------------------------------------------------------------------
    # Execution events
    # ------------------------------------------------------------------

    def record_event(
        self, build_session_id: str, payload: ModelingExecutionEventCreate
    ) -> tuple[dict[str, Any], bool]:
        request = payload.model_dump(mode="json")
        self._reject_secrets(request)
        encoded = _canonical_json(request)
        if len(encoded) > EVENT_PAYLOAD_LIMIT:
            raise ModelingWorkflowError(
                "invalid_modeling_workflow_payload",
                "Modeling Execution Event exceeds the 64 KiB limit",
                status_code=413,
                actual=len(encoded),
                limit=EVENT_PAYLOAD_LIMIT,
            )
        request_hash = hashlib.sha256(encoded).hexdigest()
        build_session = self._build_session(build_session_id, lock=True)
        self._assert_active(build_session)

        existing = self.session.scalar(
            select(ModelingExecutionEventModel).where(
                ModelingExecutionEventModel.build_session_id == build_session_id,
                ModelingExecutionEventModel.client_event_id == payload.client_event_id,
            )
        )
        if existing is not None:
            self._assert_idempotent(existing.request_hash, request_hash)
            return self._event_read(existing), False

        self._ontology(build_session.project_id, payload.ontology_id)
        self._validate_artifact_references(build_session_id, payload)
        self._validate_related_resources(build_session, payload)
        self._validate_supersedes(build_session_id, payload)
        self._validate_question_transition(build_session, payload)

        sequence = (
            self.session.scalar(
                select(func.max(ModelingExecutionEventModel.sequence)).where(
                    ModelingExecutionEventModel.build_session_id == build_session_id
                )
            )
            or 0
        ) + 1
        row = ModelingExecutionEventModel(
            id=str(uuid4()),
            project_id=build_session.project_id,
            build_session_id=build_session_id,
            ontology_id=payload.ontology_id,
            client_event_id=payload.client_event_id,
            request_hash=request_hash,
            sequence=sequence,
            workflow_name=payload.workflow_name,
            workflow_version=payload.workflow_version,
            phase=payload.phase,
            event_type=payload.event_type,
            status=payload.status,
            report_source=payload.report_source,
            actor=self.actor,
            actor_role=payload.actor_role,
            role_prompt_version=payload.role_prompt_version,
            agent_runtime=payload.agent_runtime,
            agent_model=payload.agent_model,
            reasoning_effort=payload.reasoning_effort,
            summary=payload.summary,
            input_workflow_artifact_ids=list(payload.input_workflow_artifact_ids),
            output_workflow_artifact_ids=list(payload.output_workflow_artifact_ids),
            question_id=payload.question_id,
            question_state=payload.question_state,
            question_text=payload.question_text,
            answer_text=payload.answer_text,
            answer_reason=payload.answer_reason,
            expected_question_head_event_id=payload.expected_question_head_event_id,
            interview_answer_id=payload.interview_answer_id,
            decisions=list(payload.decisions),
            rejected_alternatives=list(payload.rejected_alternatives),
            unresolved_items=list(payload.unresolved_items),
            blockers=list(payload.blockers),
            next_step=payload.next_step,
            related_resources=[item.model_dump(mode="json") for item in payload.related_resources],
            quality_issues=[item.model_dump(mode="json") for item in payload.quality_issues],
            duration_ms=payload.duration_ms,
            token_usage=dict(payload.token_usage),
            cost_summary=dict(payload.cost_summary),
            supersedes_execution_event_id=payload.supersedes_execution_event_id,
            occurred_at=payload.occurred_at,
        )
        self.session.add(row)
        build_session.last_activity_at = self._now()
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.scalar(
                select(ModelingExecutionEventModel).where(
                    ModelingExecutionEventModel.build_session_id == build_session_id,
                    ModelingExecutionEventModel.client_event_id == payload.client_event_id,
                )
            )
            if concurrent is None:
                raise ModelingWorkflowError(
                    "question_state_conflict" if payload.question_id else "idempotency_conflict",
                    "Concurrent execution event conflict",
                )
            self._assert_idempotent(concurrent.request_hash, request_hash)
            return self._event_read(concurrent), False
        self.session.refresh(row)
        return self._event_read(row), True

    def get_event(self, execution_event_id: str) -> dict[str, Any]:
        row = self.session.get(ModelingExecutionEventModel, execution_event_id)
        if row is None:
            raise ModelingWorkflowError(
                "modeling_execution_event_not_found",
                "Modeling Execution Event was not found",
                status_code=404,
            )
        return self._event_read(row)

    def list_events(
        self,
        build_session_id: str,
        *,
        phase: str | None = None,
        event_type: str | None = None,
        cursor: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        self._build_session(build_session_id)
        limit = max(1, min(limit, 100))
        statement = select(ModelingExecutionEventModel).where(
            ModelingExecutionEventModel.build_session_id == build_session_id
        )
        if phase:
            statement = statement.where(ModelingExecutionEventModel.phase == phase)
        if event_type:
            statement = statement.where(ModelingExecutionEventModel.event_type == event_type)
        if cursor is not None:
            statement = statement.where(ModelingExecutionEventModel.sequence > cursor)
        rows = list(
            self.session.scalars(
                statement.order_by(ModelingExecutionEventModel.sequence).limit(limit + 1)
            )
        )
        page = rows[:limit]
        return {
            "items": [self._event_read(row) for row in page],
            "next_cursor": page[-1].sequence if len(rows) > limit and page else None,
        }

    # ------------------------------------------------------------------
    # Summary and export
    # ------------------------------------------------------------------

    def summary(self, build_session_id: str) -> dict[str, Any]:
        self._build_session(build_session_id)
        artifacts = list(
            self.session.scalars(
                select(ModelingWorkflowArtifactModel)
                .where(ModelingWorkflowArtifactModel.build_session_id == build_session_id)
                .order_by(
                    ModelingWorkflowArtifactModel.artifact_key,
                    ModelingWorkflowArtifactModel.version,
                )
            )
        )
        events = list(
            self.session.scalars(
                select(ModelingExecutionEventModel)
                .where(ModelingExecutionEventModel.build_session_id == build_session_id)
                .order_by(ModelingExecutionEventModel.sequence)
            )
        )
        current: dict[str, ModelingWorkflowArtifactModel] = {}
        for row in artifacts:
            current[row.artifact_key] = row
        question_heads: dict[str, ModelingExecutionEventModel] = {}
        for event in events:
            if event.question_id:
                question_heads[event.question_id] = event
        last = events[-1] if events else None
        return {
            "current_artifacts": [
                {
                    "workflow_artifact_id": row.id,
                    "artifact_key": row.artifact_key,
                    "artifact_type": row.artifact_type,
                    "version": row.version,
                    "content_hash": row.content_hash,
                }
                for row in current.values()
            ],
            "artifact_version_count": len(artifacts),
            "event_count": len(events),
            "last_sequence": last.sequence if last else 0,
            "next_step": last.next_step if last else None,
            "question_states": [
                {
                    "question_id": question_id,
                    "head_event_id": event.id,
                    "state": event.question_state,
                    "sequence": event.sequence,
                }
                for question_id, event in sorted(question_heads.items())
            ],
        }

    def export(self, build_session_id: str, *, export_format: str) -> Any:
        build_session = self._build_session(build_session_id)
        artifacts = list(
            self.session.scalars(
                select(ModelingWorkflowArtifactModel)
                .where(ModelingWorkflowArtifactModel.build_session_id == build_session_id)
                .order_by(
                    ModelingWorkflowArtifactModel.artifact_key,
                    ModelingWorkflowArtifactModel.version,
                )
            )
        )
        events = list(
            self.session.scalars(
                select(ModelingExecutionEventModel)
                .where(ModelingExecutionEventModel.build_session_id == build_session_id)
                .order_by(ModelingExecutionEventModel.sequence)
            )
        )
        summary = self.summary(build_session_id)
        current_index: dict[str, dict[str, Any]] = {}
        for row in artifacts:
            current_index[row.artifact_key] = {
                "workflow_artifact_id": row.id,
                "version": row.version,
                "content_hash": row.content_hash,
            }
        record = {
            "session": {
                "id": build_session.id,
                "project_id": build_session.project_id,
                "status": build_session.status,
                "revision": build_session.revision,
                "last_activity_at": _datetime(build_session.last_activity_at),
            },
            "summary": summary,
            "artifacts": [self._artifact_read(row) for row in artifacts],
            "current_artifact_index": current_index,
            "events": [self._event_read(row) for row in events],
        }
        if export_format == "json":
            self._assert_export_size(_canonical_json(record))
            return record
        if export_format != "markdown":
            raise ModelingWorkflowError(
                "invalid_modeling_workflow_payload",
                "Export format must be json or markdown",
                status_code=422,
            )
        markdown = self._markdown_export(record)
        self._assert_export_size(markdown.encode("utf-8"))
        return markdown

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_question_transition(
        self, build_session: BuildSessionModel, payload: ModelingExecutionEventCreate
    ) -> None:
        is_question_event = payload.event_type in {"question_asked", "answer_recorded"}
        supplied = any(
            value is not None
            for value in (
                payload.question_id,
                payload.question_state,
                payload.question_text,
                payload.answer_text,
                payload.answer_reason,
                payload.expected_question_head_event_id,
                payload.interview_answer_id,
            )
        )
        if not is_question_event:
            if supplied:
                self._invalid("Question fields are only valid on question events")
            return
        if not payload.question_id or not payload.question_state:
            self._question_conflict("Question events require question_id and question_state")
        head = self.session.scalar(
            select(ModelingExecutionEventModel)
            .where(
                ModelingExecutionEventModel.build_session_id == build_session.id,
                ModelingExecutionEventModel.question_id == payload.question_id,
            )
            .order_by(ModelingExecutionEventModel.sequence.desc())
            .limit(1)
        )
        if payload.event_type == "question_asked":
            if payload.supersedes_execution_event_id is not None:
                self._question_conflict("question_asked must not supersede another event", head)
            if payload.question_state == "open":
                if head is not None or payload.expected_question_head_event_id is not None:
                    self._question_conflict("Question already has a current head", head)
                if not payload.question_text:
                    self._question_conflict("Open question requires user-visible question_text")
                return
            if payload.question_state != "reopened":
                self._question_conflict("question_asked state must be open or reopened", head)
            if (
                head is None
                or head.question_state not in RESOLVED_QUESTION_STATES
                or payload.expected_question_head_event_id != head.id
            ):
                self._question_conflict("Reopen must compare-and-set the resolved head", head)
            if not payload.question_text:
                self._question_conflict("Reopened question requires question_text", head)
            return

        if payload.question_state not in RESOLVED_QUESTION_STATES:
            self._question_conflict("answer_recorded requires a resolved state", head)
        if head is None or payload.expected_question_head_event_id != head.id:
            self._question_conflict("Answer must compare-and-set the current question head", head)
        if head.question_state in {"open", "reopened"}:
            if payload.supersedes_execution_event_id is not None:
                self._question_conflict("Initial answer must not supersede its open event", head)
        elif head.question_state in RESOLVED_QUESTION_STATES:
            if payload.supersedes_execution_event_id != head.id:
                self._question_conflict("Answer correction must supersede the current head", head)
        else:
            self._question_conflict("Current question state cannot be answered", head)
        if payload.question_state == "answered":
            if not payload.answer_text and not payload.interview_answer_id:
                self._question_conflict("Answered question requires answer text or answer ID", head)
        elif not payload.answer_reason:
            self._question_conflict("Skipped or uncertain answer requires an explicit reason", head)
        if payload.interview_answer_id:
            answer = self.session.get(InterviewAnswerModel, payload.interview_answer_id)
            if answer is None or answer.project_id != build_session.project_id:
                self._reference_conflict("Interview Answer is outside this Project")

    def _validate_supersedes(
        self, build_session_id: str, payload: ModelingExecutionEventCreate
    ) -> None:
        target_id = payload.supersedes_execution_event_id
        if target_id is None:
            return
        target = self.session.get(ModelingExecutionEventModel, target_id)
        if target is None or target.build_session_id != build_session_id:
            self._reference_conflict("Superseded event is outside this Build Session")
        if target.question_id and payload.event_type != "answer_recorded":
            self._reference_conflict("Question events may only be superseded by answer correction")
        child = self.session.scalar(
            select(ModelingExecutionEventModel).where(
                ModelingExecutionEventModel.supersedes_execution_event_id == target_id
            )
        )
        if child is not None:
            self._reference_conflict("Superseded event already has a correction")

    def _validate_artifact_references(
        self, build_session_id: str, payload: ModelingExecutionEventCreate
    ) -> None:
        for artifact_id in dict.fromkeys(
            [
                *payload.input_workflow_artifact_ids,
                *payload.output_workflow_artifact_ids,
            ]
        ):
            row = self.session.get(ModelingWorkflowArtifactModel, artifact_id)
            if row is None or row.build_session_id != build_session_id:
                self._reference_conflict("Workflow Artifact is outside this Build Session")

    def _validate_related_resources(
        self, build_session: BuildSessionModel, payload: ModelingExecutionEventCreate
    ) -> None:
        for resource in payload.related_resources:
            kind = resource.resource_type
            resource_id = resource.resource_id
            if kind == "competency_question":
                row = self.session.get(CompetencyQuestionModel, resource_id)
                valid = row is not None and row.project_id == build_session.project_id
            elif kind == "evidence_reference":
                row = self.session.get(EvidenceReferenceModel, resource_id)
                valid = row is not None and row.project_id == build_session.project_id
            elif kind == "modeling_batch":
                row = self.session.get(ModelingBatchModel, resource_id)
                valid = row is not None and row.build_session_id == build_session.id
            elif kind == "modeling_attempt":
                row = self.session.get(ModelingBatchAttemptModel, resource_id)
                valid = row is not None and row.build_session_id == build_session.id
            elif kind == "finding":
                row = self.session.get(ModelingBatchAttemptModel, resource.attempt_id)
                valid = bool(
                    row is not None
                    and row.build_session_id == build_session.id
                    and any(
                        item.get("finding_fingerprint") == resource.finding_fingerprint
                        for item in (row.findings or [])
                    )
                )
            elif kind == "validation_run":
                row = self.session.get(SemanticValidationRunModel, resource_id)
                valid = (
                    row is not None and self._validation_project(row) == build_session.project_id
                )
            elif kind == "lineage":
                valid = self._validate_lineage_reference(build_session, resource)
            elif kind in {"ontology", "lease"}:
                ontology = self._owned_ontology(build_session.project_id, resource_id)
                if kind == "lease":
                    lease = self.session.get(OntologyLeaseModel, resource_id)
                    valid = (
                        ontology is not None
                        and lease is not None
                        and lease.build_session_id == build_session.id
                    )
                else:
                    valid = ontology is not None
            elif kind == "workflow_artifact":
                row = self.session.get(ModelingWorkflowArtifactModel, resource_id)
                valid = row is not None and row.build_session_id == build_session.id
            elif kind == "execution_event":
                row = self.session.get(ModelingExecutionEventModel, resource_id)
                valid = row is not None and row.build_session_id == build_session.id
            else:  # schema should make this unreachable
                valid = False
            if not valid:
                self._reference_conflict(f"Invalid or foreign related resource: {kind}")

    def _validate_lineage_reference(
        self, build_session: BuildSessionModel, resource: WorkflowRelatedResource
    ) -> bool:
        if (
            resource.ontology_id is None
            or resource.target_type is None
            or resource.target_id is None
        ):
            return False
        if self._owned_ontology(build_session.project_id, resource.ontology_id) is None:
            return False
        try:
            self.lineage_service.get_lineage(
                ontology_id=resource.ontology_id,
                target_type=resource.target_type,
                target_id=resource.target_id,
                include_history=False,
                max_depth=0,
                limit=1,
            )
        except (OntologyLineageError, InvalidLineageStatement):
            return False
        return True

    def _validation_project(self, run: SemanticValidationRunModel) -> str | None:
        metadata = run.run_metadata or {}
        ontology_id = metadata.get("ontology_id")
        if ontology_id:
            ontology = self.session.get(OntologyModel, ontology_id)
            return ontology.project_id if ontology else None
        graph_set_id = metadata.get("graph_set_id")
        if graph_set_id:
            graph_set = self.session.get(SemanticGraphSetModel, graph_set_id)
            if graph_set and graph_set.scope_type == "ontology":
                ontology = self.session.get(OntologyModel, graph_set.scope_id)
                return ontology.project_id if ontology else None
        return None

    def _owned_ontology(self, project_id: str, ontology_id: str | None) -> OntologyModel | None:
        if ontology_id is None:
            return None
        row = self.session.get(OntologyModel, ontology_id)
        return row if row is not None and row.project_id == project_id else None

    # ------------------------------------------------------------------
    # Serialization/helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _artifact_content(content_format: str, content: Any) -> bytes:
        if content_format == "json" and isinstance(content, (dict, list)):
            return _canonical_json(content)
        if content_format == "markdown" and isinstance(content, str):
            return content.encode("utf-8")
        raise ModelingWorkflowError(
            "invalid_modeling_workflow_payload",
            "JSON content must be an object/list and Markdown content must be a string",
            status_code=422,
        )

    @staticmethod
    def _artifact_read(row: ModelingWorkflowArtifactModel) -> dict[str, Any]:
        return {
            "workflow_artifact_id": row.id,
            "project_id": row.project_id,
            "build_session_id": row.build_session_id,
            "ontology_id": row.ontology_id,
            "artifact_key": row.artifact_key,
            "client_version_id": row.client_version_id,
            "version": row.version,
            "artifact_type": row.artifact_type,
            "content_format": row.content_format,
            "content": row.content,
            "content_hash": row.content_hash,
            "content_size_bytes": row.content_size_bytes,
            "created_by": row.created_by,
            "created_by_role": row.created_by_role,
            "workflow_name": row.workflow_name,
            "workflow_version": row.workflow_version,
            "role_prompt_version": row.role_prompt_version,
            "supersedes_workflow_artifact_id": row.supersedes_workflow_artifact_id,
            "created_at": _datetime(row.created_at),
        }

    @staticmethod
    def _event_read(row: ModelingExecutionEventModel) -> dict[str, Any]:
        return {
            "execution_event_id": row.id,
            "project_id": row.project_id,
            "build_session_id": row.build_session_id,
            "ontology_id": row.ontology_id,
            "client_event_id": row.client_event_id,
            "sequence": row.sequence,
            "workflow_name": row.workflow_name,
            "workflow_version": row.workflow_version,
            "phase": row.phase,
            "event_type": row.event_type,
            "status": row.status,
            "report_source": row.report_source,
            "actor": row.actor,
            "actor_role": row.actor_role,
            "role_prompt_version": row.role_prompt_version,
            "agent_runtime": row.agent_runtime,
            "agent_model": row.agent_model,
            "reasoning_effort": row.reasoning_effort,
            "summary": row.summary,
            "input_workflow_artifact_ids": list(row.input_workflow_artifact_ids or []),
            "output_workflow_artifact_ids": list(row.output_workflow_artifact_ids or []),
            "question_id": row.question_id,
            "question_state": row.question_state,
            "question_text": row.question_text,
            "answer_text": row.answer_text,
            "answer_reason": row.answer_reason,
            "expected_question_head_event_id": row.expected_question_head_event_id,
            "interview_answer_id": row.interview_answer_id,
            "decisions": list(row.decisions or []),
            "rejected_alternatives": list(row.rejected_alternatives or []),
            "unresolved_items": list(row.unresolved_items or []),
            "blockers": list(row.blockers or []),
            "next_step": row.next_step,
            "related_resources": list(row.related_resources or []),
            "quality_issues": list(row.quality_issues or []),
            "duration_ms": row.duration_ms,
            "token_usage": row.token_usage or {},
            "cost_summary": row.cost_summary or {},
            "supersedes_execution_event_id": row.supersedes_execution_event_id,
            "occurred_at": _datetime(row.occurred_at),
            "created_at": _datetime(row.created_at),
        }

    def _build_session(self, session_id: str, *, lock: bool = False) -> BuildSessionModel:
        statement = select(BuildSessionModel).where(BuildSessionModel.id == session_id)
        if lock:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        if row is None:
            raise ModelingWorkflowError(
                "build_session_not_found", "Build Session was not found", status_code=404
            )
        return row

    def _ontology(self, project_id: str, ontology_id: str | None) -> OntologyModel | None:
        if ontology_id is None:
            return None
        row = self.session.get(OntologyModel, ontology_id)
        if row is None or row.project_id != project_id:
            raise ModelingWorkflowError(
                "ontology_not_found", "Ontology was not found", status_code=404
            )
        return row

    @staticmethod
    def _assert_active(build_session: BuildSessionModel) -> None:
        if build_session.status != "active":
            raise ModelingWorkflowError(
                "session_terminal", "Build Session is terminal and cannot accept records"
            )

    @staticmethod
    def _assert_idempotent(existing_hash: str, request_hash: str) -> None:
        if existing_hash != request_hash:
            raise ModelingWorkflowError(
                "idempotency_conflict", "Client id identifies a different immutable request"
            )

    @staticmethod
    def _reject_secrets(value: Any) -> None:
        try:
            scan_domain_payload(value)
        except SecretDetected as exc:
            raise ModelingWorkflowError(
                "secret_in_payload",
                "A high-confidence secret was rejected",
                status_code=422,
                category=exc.category,
            ) from exc

    @staticmethod
    def _artifact_version_conflict(message: str, **detail: Any) -> None:
        raise ModelingWorkflowError("workflow_artifact_version_conflict", message, **detail)

    @staticmethod
    def _reference_conflict(message: str) -> None:
        raise ModelingWorkflowError("workflow_reference_conflict", message)

    @staticmethod
    def _invalid(message: str) -> None:
        raise ModelingWorkflowError("invalid_modeling_workflow_payload", message, status_code=422)

    @staticmethod
    def _question_conflict(message: str, head: ModelingExecutionEventModel | None = None) -> None:
        raise ModelingWorkflowError(
            "question_state_conflict",
            message,
            current_question_head_event_id=head.id if head else None,
            current_question_state=head.question_state if head else None,
        )

    @staticmethod
    def _assert_export_size(encoded: bytes) -> None:
        if len(encoded) > EXPORT_LIMIT:
            raise ModelingWorkflowError(
                "modeling_workflow_export_too_large",
                "Modeling workflow export exceeds the 8 MiB limit",
                status_code=413,
                actual=len(encoded),
                limit=EXPORT_LIMIT,
            )

    @staticmethod
    def _markdown_export(record: dict[str, Any]) -> str:
        session = record["session"]
        lines = [
            f"# Modeling Execution Record {session['id']}",
            "",
            f"- Project: `{session['project_id']}`",
            f"- Status: `{session['status']}`",
            f"- Revision: `{session['revision']}`",
            "",
            "## Artifact versions",
            "",
        ]
        if not record["artifacts"]:
            lines.append("No workflow artifacts recorded.")
        for artifact in record["artifacts"]:
            lines.extend(
                [
                    f"### {artifact['artifact_key']} v{artifact['version']}",
                    "",
                    f"- ID: `{artifact['workflow_artifact_id']}`",
                    f"- Type: `{artifact['artifact_type']}`",
                    f"- Role: `{artifact['created_by_role']}` / `{artifact['created_by']}`",
                    f"- Workflow: `{artifact['workflow_name']}@{artifact['workflow_version']}`",
                    f"- Content hash: `{artifact['content_hash']}`",
                    f"- Supersedes: `{artifact['supersedes_workflow_artifact_id'] or 'none'}`",
                    "",
                    "```json" if artifact["content_format"] == "json" else "```markdown",
                    json.dumps(artifact["content"], ensure_ascii=False, indent=2)
                    if artifact["content_format"] == "json"
                    else artifact["content"],
                    "```",
                    "",
                ]
            )
        lines.extend(["## Timeline", ""])
        if not record["events"]:
            lines.append("No execution events recorded.")
        for event in record["events"]:
            lines.extend(
                [
                    f"### {event['sequence']}. {event['event_type']}",
                    "",
                    f"- Phase/status: `{event['phase']}` / `{event['status']}`",
                    f"- Source: `{event['report_source']}` by `{event['actor_role']}` "
                    f"(`{event['actor']}`)",
                    f"- Runtime/model/effort: `{event['agent_runtime'] or 'unknown'}` / "
                    f"`{event['agent_model'] or 'unknown'}` / "
                    f"`{event['reasoning_effort'] or 'unknown'}`",
                    f"- Summary: {event['summary']}",
                    f"- Question: `{event['question_id'] or 'none'}` / "
                    f"`{event['question_state'] or 'none'}`",
                    f"- Answer: {event['answer_text'] or event['answer_reason'] or 'none'}",
                    f"- Decisions: `{json.dumps(event['decisions'], ensure_ascii=False)}`",
                    f"- Rejected alternatives: "
                    f"`{json.dumps(event['rejected_alternatives'], ensure_ascii=False)}`",
                    f"- Related resources: "
                    f"`{json.dumps(event['related_resources'], ensure_ascii=False)}`",
                    f"- Quality issues: "
                    f"`{json.dumps(event['quality_issues'], ensure_ascii=False)}`",
                    f"- Blockers: `{json.dumps(event['blockers'], ensure_ascii=False)}`",
                    f"- Next step: {event['next_step'] or 'none'}",
                    f"- Supersedes: `{event['supersedes_execution_event_id'] or 'none'}`",
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)


__all__ = ["ModelingWorkflowError", "ModelingWorkflowService"]
