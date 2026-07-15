"""Opt-in PostgreSQL concurrency coverage for R-004.

Run with ``RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest
tests/test_modeling_batches_postgres.py`` against the migrated local database.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.schemas import (
    BuildSessionCreate,
    ModelingBatchSubmit,
    ModelingItemInput,
    OntologyLeaseAcquire,
)
from app.core.config import Settings
from app.repositories.models import (
    EvidenceAssociationModel,
    EvidenceReferenceModel,
    ModelingBatchAttemptModel,
    ModelingBatchModel,
    OntologyModel,
    ProjectModel,
)
from app.repositories.rdf_store import GraphWriteResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_CONCURRENCY_TESTS") != "1",
    reason="set RUN_POSTGRES_CONCURRENCY_TESTS=1 to use the migrated PostgreSQL database",
)


class FakeRdfStore:
    def graph_exists(self, _graph_iri):
        return False

    def get_graph(self, _graph_iri, _format):
        return ""

    def apply_dataset_delta(self, delta):
        return GraphWriteResult(
            graph_iri=delta.affected_graph_iris()[0] if delta.affected_graph_iris() else "",
            applied=not delta.is_empty,
            inserted_quad_count=len(delta.inserts),
            deleted_quad_count=len(delta.deletes),
        )


def _settings() -> Settings:
    values = Settings().model_dump()
    values["semantic_product_write_mode"] = "rdf_primary"
    return Settings(**values)


def _item(client_item_id: str) -> ModelingItemInput:
    return ModelingItemInput(
        client_item_id=client_item_id,
        command_kind="create_class",
        payload={"name": f"Customer {client_item_id}"},
        evidence=[{"document_name": "domain.md", "excerpt": "A customer exists."}],
    )


def test_concurrent_same_batch_and_attempt_converge_to_one_record() -> None:
    settings = _settings()
    engine = create_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex
    project_id = str(uuid4())
    ontology_id = str(uuid4())
    with factory() as session:
        session.add(ProjectModel(id=project_id, name=suffix, normalized_label=suffix))
        ontology = OntologyModel(id=ontology_id, project_id=project_id, name=suffix)
        session.add(ontology)
        session.flush()
        OntologyWorkspaceService(session, settings).ensure(ontology)
        session.commit()
        build, _created = BuildSessionService(session, settings).create_session(
            project_id, BuildSessionCreate(client_session_id=f"agent-{suffix}")
        )
        version = ModelingWorkspaceVersionService(session, settings).version_for(ontology_id)

    def submit() -> tuple[str, str]:
        with factory() as session:
            result = ModelingBatchService(session, settings, FakeRdfStore()).submit(
                build["id"],
                ModelingBatchSubmit(
                    client_batch_id="same-batch",
                    ontology_id=ontology_id,
                    idempotency_key="same-attempt",
                    mode="dry_run",
                    expected_workspace_version=version,
                    items=[_item("same-item")],
                ),
            )
            return result["batch_id"], result["attempt_id"]

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: submit(), range(2)))
        assert len({result[0] for result in results}) == 1
        assert len({result[1] for result in results}) == 1
        with factory() as session:
            assert session.scalar(
                select(func.count(ModelingBatchModel.id)).where(
                    ModelingBatchModel.project_id == project_id
                )
            ) == 1
            assert session.scalar(
                select(func.count(ModelingBatchAttemptModel.id)).join(ModelingBatchModel).where(
                    ModelingBatchModel.project_id == project_id
                )
            ) == 1
    finally:
        with factory() as session:
            project = session.get(ProjectModel, project_id)
            if project:
                session.delete(project)
                session.commit()
        engine.dispose()


def test_concurrent_inline_evidence_upserts_one_reference_for_two_ontologies() -> None:
    settings = _settings()
    engine = create_engine(settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex
    project_id = str(uuid4())
    work: list[tuple[str, str, str, str]] = []
    ontology_ids = [str(uuid4()), str(uuid4())]
    with factory() as session:
        session.add(ProjectModel(id=project_id, name=suffix, normalized_label=suffix))
        for index in range(2):
            ontology_id = ontology_ids[index]
            ontology = OntologyModel(id=ontology_id, project_id=project_id, name=ontology_id)
            session.add(ontology)
            session.flush()
            OntologyWorkspaceService(session, settings).ensure(ontology)
        session.commit()
        for index in range(2):
            ontology_id = ontology_ids[index]
            build, _created = BuildSessionService(session, settings).create_session(
                project_id, BuildSessionCreate(client_session_id=f"agent-{suffix}-{index}")
            )
            lease = BuildSessionService(session, settings).acquire_ontology_lease(
                build["id"],
                ontology_id,
                OntologyLeaseAcquire(
                    client_request_id=f"lease-{suffix}-{index}", expected_session_revision=1
                ),
            )
            version = ModelingWorkspaceVersionService(session, settings).version_for(ontology_id)
            work.append((build["id"], ontology_id, lease["lease_token"], version))

    def submit(index: int) -> str:
        build_id, ontology_id, token, version = work[index]
        with factory() as session:
            result = ModelingBatchService(session, settings, FakeRdfStore()).submit(
                build_id,
                ModelingBatchSubmit(
                    client_batch_id=f"batch-{index}",
                    ontology_id=ontology_id,
                    idempotency_key=f"attempt-{index}",
                    mode="apply_atomic",
                    expected_workspace_version=version,
                    lease_token=token,
                    items=[_item(f"item-{index}")],
                ),
            )
            return result["attempt_status"]

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(submit, range(2))) == ["applied", "applied"]
        with factory() as session:
            assert session.scalar(
                select(func.count(EvidenceReferenceModel.id)).where(
                    EvidenceReferenceModel.project_id == project_id
                )
            ) == 1
            assert session.scalar(
                select(func.count(EvidenceAssociationModel.id)).where(
                    EvidenceAssociationModel.project_id == project_id
                )
            ) == 2
    finally:
        with factory() as session:
            project = session.get(ProjectModel, project_id)
            if project:
                session.delete(project)
                session.commit()
        engine.dispose()
