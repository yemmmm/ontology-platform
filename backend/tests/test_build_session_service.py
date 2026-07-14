"""Service-level invariants for R-003 build-session recovery and leases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import func, select
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
    OntologyLeaseModel,
    OntologyModel,
    ProjectModel,
    SemanticGraphRevisionModel,
)
from app.services.build_sessions import BuildSessionError, BuildSessionService
from app.services.ontology_workspace import OntologyWorkspaceService


PROJECT_ID = "service-project"
OTHER_PROJECT_ID = "service-other-project"
ONTOLOGY_ID = "service-ontology"
OTHER_ONTOLOGY_ID = "service-other-ontology"


def _settings() -> Settings:
    return Settings(
        semantic_graph_iri_prefix="https://service.internal/graph/",
        build_session_lease_ttl_seconds=300,
    )


def _seed(session: Session) -> None:
    session.add_all(
        [
            ProjectModel(
                id=PROJECT_ID,
                name="Service project",
                normalized_label="service project",
            ),
            ProjectModel(
                id=OTHER_PROJECT_ID,
                name="Service other project",
                normalized_label="service other project",
            ),
        ]
    )
    session.flush()
    ontologies = [
        OntologyModel(
            id=ONTOLOGY_ID,
            project_id=PROJECT_ID,
            name="Service ontology",
        ),
        OntologyModel(
            id=OTHER_ONTOLOGY_ID,
            project_id=OTHER_PROJECT_ID,
            name="Service foreign ontology",
        ),
    ]
    session.add_all(ontologies)
    session.flush()
    workspace = OntologyWorkspaceService(session, _settings())
    for ontology in ontologies:
        workspace.ensure(ontology)
    session.commit()


@pytest.fixture()
def service(in_memory_session: Session) -> tuple[BuildSessionService, Session]:
    _seed(in_memory_session)
    return BuildSessionService(in_memory_session, _settings()), in_memory_session


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    assert isinstance(value, dict)
    return value


def _session_data(detail: Any) -> dict[str, Any]:
    data = _dump(detail)
    return data.get("session", data)


def _create(
    service: BuildSessionService,
    client_session_id: str,
    *,
    project_id: str = PROJECT_ID,
    initial_checkpoint: InitialBuildCheckpoint | None = None,
) -> tuple[dict[str, Any], bool]:
    detail, created = service.create_session(
        project_id,
        BuildSessionCreate(
            client_session_id=client_session_id,
            initial_checkpoint=initial_checkpoint,
        ),
    )
    return _session_data(detail), created


def _assert_error(exc: pytest.ExceptionInfo[BuildSessionError], code: str, status: int) -> None:
    assert exc.value.code == code
    assert exc.value.status_code == status


def _workspace_version(context: dict[str, Any], ontology_id: str) -> str:
    ontology = next(
        item
        for item in context["platform_state"]["ontologies"]
        if item["id"] == ontology_id
    )
    version = ontology["workspace"]["workspace_version"]
    assert isinstance(version, str) and version
    return version


def _advance_one_graph_revision(session: Session, ontology_id: str) -> None:
    revision = session.scalar(
        select(SemanticGraphRevisionModel)
        .where(SemanticGraphRevisionModel.graph_iri.like(f"%/{ontology_id}"))
        .order_by(SemanticGraphRevisionModel.graph_iri)
        .limit(1)
    )
    assert revision is not None
    revision.revision += 1
    session.commit()


def test_create_with_initial_checkpoint_is_atomic_and_idempotent(service) -> None:
    build_service, db_session = service
    initial = InitialBuildCheckpoint(
        client_checkpoint_id="cp-initial",
        phase="intake",
        current_step="Review the complete project",
        next_step="Select an Ontology",
        blockers=[],
    )

    first, created = _create(
        build_service, "client-session-initial", initial_checkpoint=initial
    )
    retry, retry_created = _create(
        build_service, "client-session-initial", initial_checkpoint=initial
    )

    assert created is True
    assert retry_created is False
    assert first["id"] == retry["id"]
    assert first["revision"] == retry["revision"] == 2
    assert db_session.scalar(select(func.count(BuildSessionModel.id))) == 1
    assert db_session.scalar(select(func.count(BuildCheckpointModel.id))) == 1

    with pytest.raises(BuildSessionError) as conflict:
        _create(build_service, "client-session-initial")
    _assert_error(conflict, "idempotency_conflict", 409)


def test_checkpoint_is_append_only_idempotent_and_revision_guarded(service) -> None:
    build_service, db_session = service
    session, _created = _create(build_service, "checkpoint-session")
    payload = BuildCheckpointCreate(
        client_checkpoint_id="cp-001",
        expected_revision=1,
        phase="modeling",
        current_step="Model the local Ontology",
        ontology_id=ONTOLOGY_ID,
        blockers=[],
    )

    first = _dump(build_service.save_checkpoint(session["id"], payload))
    retry = _dump(build_service.save_checkpoint(session["id"], payload))
    assert first["checkpoint"]["id"] == retry["checkpoint"]["id"]
    assert first["session"]["revision"] == retry["session"]["revision"] == 2
    assert db_session.scalar(select(func.count(BuildCheckpointModel.id))) == 1

    with pytest.raises(BuildSessionError) as stale:
        build_service.save_checkpoint(
            session["id"],
            BuildCheckpointCreate(
                client_checkpoint_id="cp-stale",
                expected_revision=1,
                phase="verification",
                current_step="Overwrite newer progress",
                blockers=[],
            ),
        )
    _assert_error(stale, "session_revision_conflict", 409)
    assert stale.value.detail["current_revision"] == 2

    with pytest.raises(BuildSessionError) as cross_project:
        build_service.save_checkpoint(
            session["id"],
            BuildCheckpointCreate(
                client_checkpoint_id="cp-foreign",
                expected_revision=2,
                phase="modeling",
                current_step="Reference another Project",
                ontology_id=OTHER_ONTOLOGY_ID,
                blockers=[],
            ),
        )
    _assert_error(cross_project, "ontology_not_found", 404)


def test_resume_preserves_revision_and_terminal_sessions_cannot_resume(service) -> None:
    build_service, _db_session = service
    session, _created = _create(build_service, "resume-session")

    first = _dump(
        build_service.resume_session(
            session["id"],
            BuildSessionResume(client_request_id="resume-001", expected_revision=1),
        )
    )
    retry = _dump(
        build_service.resume_session(
            session["id"],
            BuildSessionResume(client_request_id="resume-001", expected_revision=1),
        )
    )
    assert first["session"]["revision"] == retry["session"]["revision"] == 1

    completed = _dump(
        build_service.complete_session(
            session["id"],
            BuildSessionComplete(
                client_request_id="complete-resume",
                expected_revision=1,
                summary="Done",
            ),
        )
    )
    with pytest.raises(BuildSessionError) as terminal:
        build_service.resume_session(
            session["id"],
            BuildSessionResume(
                client_request_id="resume-terminal",
                expected_revision=completed["revision"],
            ),
        )
    _assert_error(terminal, "session_terminal", 409)


def test_lease_tokens_are_hashed_rotated_and_expired_without_ending_session(service) -> None:
    build_service, db_session = service
    owner, _created = _create(build_service, "lease-owner")
    contender, _created = _create(build_service, "lease-contender")

    first = _dump(
        build_service.acquire_ontology_lease(
            owner["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id="acquire-owner",
                expected_session_revision=1,
            ),
        )
    )
    row = db_session.get(OntologyLeaseModel, ONTOLOGY_ID)
    assert row is not None
    assert row.token_hash != first["lease_token"]
    assert len(row.token_hash) == 64

    rotated = _dump(
        build_service.acquire_ontology_lease(
            owner["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id="rotate-owner",
                expected_session_revision=1,
                rotate_token=True,
            ),
        )
    )
    assert rotated["lease_token"] != first["lease_token"]
    assert rotated["lease_revision"] > first["lease_revision"]

    with pytest.raises(BuildSessionError) as old_token:
        build_service.renew_ontology_lease(
            owner["id"],
            ONTOLOGY_ID,
            OntologyLeaseRenew(
                client_request_id="renew-old-token",
                lease_token=first["lease_token"],
                expected_lease_revision=rotated["lease_revision"],
            ),
        )
    assert old_token.value.status_code == 409

    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    replacement = _dump(
        build_service.acquire_ontology_lease(
            contender["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id="acquire-after-expiry",
                expected_session_revision=1,
            ),
        )
    )
    assert replacement["build_session_id"] == contender["id"]
    assert replacement["lease_token"] != rotated["lease_token"]
    db_session.refresh(db_session.get(BuildSessionModel, owner["id"]))
    assert db_session.get(BuildSessionModel, owner["id"]).status == "active"


@pytest.mark.parametrize("action", ["complete", "cancel"])
def test_terminal_operations_are_idempotent_and_release_every_lease(service, action) -> None:
    build_service, db_session = service
    session, _created = _create(build_service, f"terminal-{action}")
    lease = _dump(
        build_service.acquire_ontology_lease(
            session["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id=f"lease-{action}", expected_session_revision=1
            ),
        )
    )
    if action == "complete":
        payload = BuildSessionComplete(
            client_request_id="terminal-request",
            expected_revision=1,
            summary="Completed scoped work",
            unresolved_items=["One later benchmark"],
        )
        first = _dump(build_service.complete_session(session["id"], payload))
        retry = _dump(build_service.complete_session(session["id"], payload))
        assert first["status"] == retry["status"] == "completed"
    else:
        payload = BuildSessionCancel(
            client_request_id="terminal-request",
            expected_revision=1,
            reason="Cancelled by the user",
        )
        first = _dump(build_service.cancel_session(session["id"], payload))
        retry = _dump(build_service.cancel_session(session["id"], payload))
        assert first["status"] == retry["status"] == "cancelled"

    row = db_session.get(OntologyLeaseModel, ONTOLOGY_ID)
    assert row is not None and row.released_at is not None
    assert row.token_hash != lease["lease_token"]


def test_release_is_idempotent_but_request_id_cannot_change_payload(service) -> None:
    build_service, _db_session = service
    session, _created = _create(build_service, "release-session")
    lease = _dump(
        build_service.acquire_ontology_lease(
            session["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id="acquire-release", expected_session_revision=1
            ),
        )
    )
    payload = OntologyLeaseRelease(
        client_request_id="release-idempotent",
        lease_token=lease["lease_token"],
        expected_lease_revision=lease["lease_revision"],
    )
    first = _dump(build_service.release_ontology_lease(session["id"], ONTOLOGY_ID, payload))
    retry = _dump(build_service.release_ontology_lease(session["id"], ONTOLOGY_ID, payload))
    assert first == retry

    with pytest.raises(BuildSessionError) as conflict:
        build_service.release_ontology_lease(
            session["id"],
            ONTOLOGY_ID,
            OntologyLeaseRelease(
                client_request_id="release-idempotent",
                lease_token="different-token",
                expected_lease_revision=lease["lease_revision"],
            ),
        )
    _assert_error(conflict, "idempotency_conflict", 409)


def test_authorize_apply_accepts_current_workspace_and_rejects_changed_revision(
    service,
) -> None:
    build_service, db_session = service
    session, _created = _create(build_service, "authorize-apply-session")
    version = _workspace_version(
        build_service.get_project_build_context(PROJECT_ID), ONTOLOGY_ID
    )
    lease = _dump(
        build_service.acquire_ontology_lease(
            session["id"],
            ONTOLOGY_ID,
            OntologyLeaseAcquire(
                client_request_id="authorize-lease", expected_session_revision=1
            ),
        )
    )

    guard = build_service.authorize_apply(
        session_id=session["id"],
        ontology_id=ONTOLOGY_ID,
        lease_token=lease["lease_token"],
        expected_workspace_version=version,
    )
    assert guard["build_session_id"] == session["id"]
    assert guard["ontology_id"] == ONTOLOGY_ID
    assert guard["workspace_version"] == version
    assert guard["graph_set_id"]

    _advance_one_graph_revision(db_session, ONTOLOGY_ID)
    with pytest.raises(BuildSessionError) as stale:
        build_service.authorize_apply(
            session_id=session["id"],
            ontology_id=ONTOLOGY_ID,
            lease_token=lease["lease_token"],
            expected_workspace_version=version,
        )
    _assert_error(stale, "workspace_revision_conflict", 409)
    assert stale.value.detail["current_workspace_version"] != version


def test_build_context_workspace_version_is_recomputed_from_graph_revisions(service) -> None:
    build_service, db_session = service
    before = _workspace_version(
        build_service.get_project_build_context(PROJECT_ID), ONTOLOGY_ID
    )

    _advance_one_graph_revision(db_session, ONTOLOGY_ID)
    after = _workspace_version(
        build_service.get_project_build_context(PROJECT_ID), ONTOLOGY_ID
    )

    assert after != before
