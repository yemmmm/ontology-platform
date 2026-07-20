import pytest
from sqlalchemy import select

from app.repositories.models import (
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticProjectionJobModel,
    SemanticProjectionManifestModel,
)
from app.services.semantic_projection_job import (
    SemanticProjectionJobService,
)


class FakeProjectionWriter:
    kind = "search"

    def __init__(self):
        self.calls: list[tuple[str, object, str]] = []

    def rebuild(self, job_id, scope, partition):
        self.calls.append((job_id, scope, partition))
        return {"node_count": 3, "relationship_count": 2, "document_count": 0}


def _seed_graph_set(session, signature="sig-1"):
    gs = SemanticGraphSetModel(
        id="gs-1",
        name="demo",
        scope_type="ontology_version",
        scope_id="ov-1",
        status="active",
        source_signature=signature,
    )
    session.add(gs)
    gs.members.append(
        SemanticGraphSetMemberModel(
            id="m-1",
            graph_iri="http://op/s/graph/data/ov-1",
            role="asserted_data",
            required=True,
            sort_order=0,
        )
    )
    session.commit()
    return gs


class _StaticResolver:
    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        from app.services.semantic_read_scope import ScopeResolution

        return ScopeResolution(
            graph_set_id=graph_set_id,
            source_signature="sig-1",
            include=include,
            source_graph_iris=["http://op/s/graph/data/ov-1"],
            shape_graph_iris=[],
            governance_graph_iris=[],
            reasoning_result_graph_iri=None,
            rule_result_graph_iri=None,
            derived_state={},
            warnings=[],
        )


def _service(session, **writers) -> SemanticProjectionJobService:
    return SemanticProjectionJobService(
        session=session,
        writers=writers,
        scope_resolver_builder=lambda s: _StaticResolver(),
    )


def test_create_job_snapshots_inputs(in_memory_session):
    _seed_graph_set(in_memory_session)
    writer = FakeProjectionWriter()
    service = _service(in_memory_session, search=writer)
    job = service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
        include="asserted",
        mode="rebuild",
    )
    assert job.graph_set_id == "gs-1"
    assert job.projection_kind == "search"
    assert job.source_signature == "sig-1"
    assert isinstance(job.input_graph_revisions, dict)
    assert isinstance(job.input_derived_pointers, dict)


def test_run_job_calls_writer_and_promotes_manifest(in_memory_session):
    _seed_graph_set(in_memory_session)
    writer = FakeProjectionWriter()
    service = _service(in_memory_session, search=writer)
    job = service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
        include="asserted",
        mode="rebuild",
    )
    service.run_job(job.id)
    refreshed = in_memory_session.get(SemanticProjectionJobModel, job.id)
    assert refreshed.status == "succeeded"
    assert refreshed.node_count == 3
    assert writer.calls
    manifest = in_memory_session.scalar(
        select(SemanticProjectionManifestModel).where(
            SemanticProjectionManifestModel.graph_set_id == "gs-1",
            SemanticProjectionManifestModel.projection_kind == "search",
        )
    )
    assert manifest is not None
    assert manifest.status == "current"
    assert manifest.active_job_id == job.id


def test_writer_flush_failure_marks_job_failed_and_allows_retry(in_memory_session):
    """A failed flush must not strand the committed job in ``running``."""
    _seed_graph_set(in_memory_session)

    class FlushFailingWriter:
        kind = "search"

        def rebuild(self, job_id, scope, partition):  # noqa: ARG002
            in_memory_session.add(
                SemanticGraphSetModel(
                    id="gs-1",
                    name="duplicate",
                    scope_type="ontology_version",
                    scope_id="duplicate",
                    source_signature="duplicate",
                )
            )
            in_memory_session.flush()
            return {"node_count": 0, "relationship_count": 0, "document_count": 0}

    service = _service(in_memory_session, search=FlushFailingWriter())
    failed = service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
    )
    with pytest.raises(Exception):
        service.run_job(failed.id)

    in_memory_session.expire_all()
    persisted = in_memory_session.get(SemanticProjectionJobModel, failed.id)
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.error
    assert persisted.finished_at is not None

    service.writers["search"] = FakeProjectionWriter()
    retry = service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
    )
    assert service.run_job(retry.id).status == "succeeded"


def test_dry_run_does_not_mutate_target(in_memory_session):
    _seed_graph_set(in_memory_session)
    writer = FakeProjectionWriter()
    service = _service(in_memory_session, search=writer)
    job = service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
        mode="dry_run",
    )
    service.run_job(job.id)
    assert not writer.calls
    refreshed = in_memory_session.get(SemanticProjectionJobModel, job.id)
    assert refreshed.status == "succeeded"


def test_reconcile_marks_stale_when_signature_changes(in_memory_session):
    _seed_graph_set(in_memory_session, signature="sig-1")
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="man-1",
            graph_set_id="gs-1",
            projection_kind="search",
            active_job_id="job-old",
            source_signature="sig-0",
            projection_version="search-v1",
            target_partition="gs-1/search/search-v1",
            status="current",
        )
    )
    in_memory_session.commit()
    service = _service(in_memory_session, search=FakeProjectionWriter())
    report = service.reconcile()
    assert "man-1" in report["marked_stale"]


def test_reconcile_marks_stale_when_pointer_status_changes(in_memory_session):
    _seed_graph_set(in_memory_session, signature="sig-1")
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="man-2",
            graph_set_id="gs-1",
            projection_kind="search",
            active_job_id="job-old",
            source_signature="sig-1",
            projection_version="search-v1",
            target_partition="gs-1/search/search-v1",
            status="current",
            manifest_metadata={
                "input_derived_pointers": {
                    "reasoning": {"status": "current"}
                }
            },
        )
    )
    in_memory_session.commit()
    service = _service(in_memory_session, search=FakeProjectionWriter())
    report = service.reconcile()
    # No live pointer rows in DB → current_status = missing != "current" → stale
    assert "man-2" in report["marked_stale"]


def test_status_returns_manifests_with_stale_and_missing(in_memory_session):
    _seed_graph_set(in_memory_session)
    in_memory_session.add(
        SemanticProjectionManifestModel(
            id="man-1",
            graph_set_id="gs-1",
            projection_kind="search",
            active_job_id="job-old",
            source_signature="old",
            projection_version="search-v1",
            target_partition="gs-1/search/search-v1",
            status="current",
        )
    )
    in_memory_session.commit()
    service = _service(in_memory_session)
    status = service.status(graph_set_id="gs-1")
    assert any(m["projection_kind"] == "search" for m in status["manifests"])
    assert "man-1" in status["stale"]


def test_list_jobs_filters_by_kind(in_memory_session):
    _seed_graph_set(in_memory_session)
    service = _service(in_memory_session, search=FakeProjectionWriter())
    service.create_job(
        graph_set_id="gs-1",
        projection_kind="search",
        projection_version="search-v1",
    )
    service.create_job(
        graph_set_id="gs-1",
        projection_kind="vector",
        projection_version="vector-v1",
    )
    jobs = service.list_jobs(projection_kind="search")
    assert len(jobs) == 1
    assert jobs[0].projection_kind == "search"
