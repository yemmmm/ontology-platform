from __future__ import annotations

from types import SimpleNamespace

from rdflib import Graph, URIRef
from rdflib.util import from_n3

from app.api.schemas import (
    BuildSessionCreate,
    ModelingBatchSubmit,
    ModelingItemInput,
    OntologyLeaseAcquire,
)
from app.core.config import Settings
from app.repositories.models import OntologyModel, ProjectModel
from app.repositories.rdf_store import GraphWriteResult
from app.services.build_sessions import BuildSessionService
from app.services.modeling_batches import ModelingBatchService, _hash
from app.services.modeling_workspace import ModelingWorkspaceVersionService
from app.services.ontology_workspace import OntologyWorkspaceService


GRAPH = "https://r23003.test/graph/data"
TARGET = "https://r23003.test/entity/unknown-a"
SOURCE = "https://r23003.test/entity/source"
PREDICATE = "https://r23003.test/relation/incident"


class _RdfStore:
    def __init__(self, content: str) -> None:
        self.content = content

    def get_graph(self, graph_iri: str, _format: str) -> str:
        assert graph_iri == GRAPH
        return self.content


class _InjectedDeleteStore:
    """Small RDF store that applies a delta, then injects a SQL-boundary failure."""

    def __init__(self, graph_iri: str, statements: list[dict]) -> None:
        self.graph_iri = graph_iri
        self.graph = Graph()
        self.deltas = []
        self.fail_after_apply = False
        for statement in statements:
            self.graph.add(
                (
                    URIRef(statement["subject"]),
                    URIRef(statement["predicate"]),
                    from_n3(
                        f'<{statement["object"]}>'
                        if statement.get("object_kind") == "uri"
                        else json_literal(statement["object"])
                    ),
                )
            )

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri == self.graph_iri and len(self.graph) > 0

    def get_graph(self, graph_iri: str, _format: str) -> str:
        assert graph_iri == self.graph_iri
        return self.graph.serialize(format="turtle")

    @staticmethod
    def _term(value: str):
        if value.startswith("?"):
            return None
        return from_n3(value)

    def apply_dataset_delta(self, delta):
        for subject, predicate, obj, graph_iri in delta.deletes:
            if graph_iri != self.graph_iri:
                continue
            subject_term = self._term(subject)
            predicate_term = self._term(predicate)
            object_term = self._term(obj)
            for triple in list(self.graph.triples((subject_term, predicate_term, object_term))):
                self.graph.remove(triple)
        for subject, predicate, obj, graph_iri in delta.inserts:
            if graph_iri == self.graph_iri:
                self.graph.add((from_n3(subject), from_n3(predicate), from_n3(obj)))
        self.deltas.append(delta)
        if self.fail_after_apply:
            self.fail_after_apply = False
            raise RuntimeError("injected post-RDF/pre-SQL failure")
        return GraphWriteResult(
            graph_iri=self.graph_iri,
            applied=not delta.is_empty,
            deleted_quad_count=len(delta.deletes),
            inserted_quad_count=len(delta.inserts),
        )


def json_literal(value: str) -> str:
    """Encode the simple test literals accepted by rdflib's N3 parser."""

    import json

    return json.dumps(value, ensure_ascii=False)


def _complete_receipt(
    statements: list[dict],
    *,
    project_id: str,
    ontology_id: str,
    workspace_version: str,
    entity_iri: str,
) -> dict:
    ordered = sorted(statements, key=_hash)
    body = {
        "schema_version": "r2-3-003-delete-impact/v1",
        "target_semantic_id": "unknown-cross-release-output-meaning",
        "project_id": project_id,
        "ontology_id": ontology_id,
        "workspace_version": workspace_version,
        "candidate_digest": "r23003-candidate",
        "entity_iri": entity_iri,
        "snapshot_digest": _hash(ordered),
        "page_digests": [_hash(statements)],
        "statements": ordered,
        "complete": True,
    }
    return {**body, "receipt_digest": _hash(body)}


def _receipt(statements: list[dict]) -> dict:
    body = {
        "schema_version": "r2-3-003-delete-impact/v1",
        "target_semantic_id": "unknown-cross-release-output-meaning",
        "project_id": "r23003-project",
        "ontology_id": "r23003-ontology",
        "workspace_version": "workspace-v1",
        "candidate_digest": "candidate-digest",
        "entity_iri": TARGET,
        "snapshot_digest": "snapshot-digest",
        "page_digests": ["page-digest"],
        "statements": statements,
        "complete": True,
    }
    return {**body, "receipt_digest": _hash(body)}


def _attempt(receipt: dict) -> SimpleNamespace:
    return SimpleNamespace(
        operation_plan={
            "delete_only_recovery": {
                "schema_version": "r2-3-003-delete-impact/v1",
                "receipts": [
                    {
                        "client_item_id": "delete-target",
                        "entity_iri": TARGET,
                        "impact_receipt": receipt,
                    }
                ],
            }
        },
        target_snapshot={"graphs": [{"graph_iri": GRAPH}]},
    )


def _service(store: _RdfStore) -> ModelingBatchService:
    return ModelingBatchService(
        session=None,  # type: ignore[arg-type]
        settings=Settings(
            semantic_graph_iri_prefix="https://r23003.test/graph/",
            semantic_base_iri="https://r23003.test/resource/",
        ),
        rdf_store=store,  # type: ignore[arg-type]
    )


def test_delete_only_recovery_distinguishes_unapplied_applied_and_partial() -> None:
    statements = [
        {
            "subject": TARGET,
            "predicate": "https://r23003.test/property/label",
            "object": "Unknown A",
            "object_kind": "literal",
            "graph": GRAPH,
        },
        {
            "subject": SOURCE,
            "predicate": PREDICATE,
            "object": TARGET,
            "object_kind": "uri",
            "graph": GRAPH,
        },
    ]
    receipt = _receipt(statements)
    store = _RdfStore(
        f'<{TARGET}> <https://r23003.test/property/label> "Unknown A" .\n'
        f"<{SOURCE}> <{PREDICATE}> <{TARGET}> .\n"
    )
    service = _service(store)
    assert service._observe_delete_only_recovery(_attempt(receipt))["state"] == "not_applied"

    store.content = ""
    assert service._observe_delete_only_recovery(_attempt(receipt))["state"] == "applied"

    store.content = f'<{TARGET}> <https://r23003.test/property/label> "Unknown A" .\n'
    assert service._observe_delete_only_recovery(_attempt(receipt))["state"] == "partial_or_drifted"


def test_delete_only_recovery_rejects_new_incident_edge() -> None:
    statements = [
        {
            "subject": TARGET,
            "predicate": "https://r23003.test/property/label",
            "object": "Unknown A",
            "object_kind": "literal",
            "graph": GRAPH,
        }
    ]
    receipt = _receipt(statements)
    store = _RdfStore(
        f'<{TARGET}> <https://r23003.test/property/label> "Unknown A" .\n'
        f'<{SOURCE}> <{PREDICATE}> <{TARGET}> .\n'
    )
    observed = _service(store)._observe_delete_only_recovery(_attempt(receipt))
    assert observed["state"] == "partial_or_drifted"


def test_injected_post_rdf_pre_sql_failure_recovers_delete_without_reapplying(
    in_memory_session, monkeypatch
) -> None:
    project_id = "r23003-recovery-project"
    ontology_id = "r23003-recovery-ontology"
    settings = Settings(
        semantic_graph_iri_prefix="https://r23003.test/graph/",
        semantic_base_iri="https://r23003.test/resource/",
        semantic_product_write_mode="rdf_primary",
    )
    in_memory_session.add(ProjectModel(id=project_id, name="R2.3-003", normalized_label="r23003"))
    ontology = OntologyModel(id=ontology_id, project_id=project_id, name="R2.3-003 recovery")
    in_memory_session.add(ontology)
    in_memory_session.flush()
    OntologyWorkspaceService(in_memory_session, settings).ensure(ontology)
    in_memory_session.commit()
    build = BuildSessionService(in_memory_session, settings)
    session_data, _ = build.create_session(
        project_id, BuildSessionCreate(client_session_id="r23003-recovery-session")
    )
    session_id = session_data["id"]
    lease = build.acquire_ontology_lease(
        session_id,
        ontology_id,
        OntologyLeaseAcquire(client_request_id="r23003-recovery-lease", expected_session_revision=1),
    )
    version = ModelingWorkspaceVersionService(in_memory_session, settings).version_for(ontology_id)
    graph_iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/data/{ontology_id}"
    target = f"{settings.semantic_base_iri.rstrip('/')}/entity/unknown-cross-release-output-meaning"
    source = f"{settings.semantic_base_iri.rstrip('/')}/entity/source"
    predicate = f"{settings.semantic_base_iri.rstrip('/')}/property/incident"
    statements = [
        {
            "subject": target,
            "predicate": f"{settings.semantic_base_iri.rstrip('/')}/property/label",
            "object": "Unknown target",
            "object_kind": "literal",
            "graph": graph_iri,
        },
        {
            "subject": source,
            "predicate": predicate,
            "object": target,
            "object_kind": "uri",
            "graph": graph_iri,
        },
    ]
    receipt = _complete_receipt(
        statements,
        project_id=project_id,
        ontology_id=ontology_id,
        workspace_version=version,
        entity_iri=target,
    )
    store = _InjectedDeleteStore(graph_iri, statements)
    service = ModelingBatchService(in_memory_session, settings, store)  # type: ignore[arg-type]
    item = ModelingItemInput(
        client_item_id="delete-target",
        command_kind="delete_entity",
        payload={
            "entity_iri": target,
            "impact_receipt": receipt,
            "impact_receipt_digest": receipt["receipt_digest"],
        },
        rationale="Remove one frozen explicit unknown after live impact binding.",
        evidence=[{"document_name": "domain.md", "excerpt": "The target is explicitly unknown."}],
    )
    request = ModelingBatchSubmit(
        client_batch_id="r23003-recovery-batch",
        ontology_id=ontology_id,
        idempotency_key="r23003-recovery-attempt",
        mode="apply_atomic",
        expected_workspace_version=version,
        lease_token=lease["lease_token"],
        items=[item],
    )
    original_persist = service._persist_evidence

    def fail_after_rdf(*_args, **_kwargs):
        raise RuntimeError("injected post-RDF/pre-SQL failure")

    monkeypatch.setattr(service, "_persist_evidence", fail_after_rdf)
    first = service.submit(session_id, request)
    assert first["attempt_status"] == "recovering"
    assert first["recovery"]["state"] == "pending"
    assert len(store.graph) == 0

    monkeypatch.setattr(service, "_persist_evidence", original_persist)
    second = service.submit(session_id, request)
    assert second["attempt_status"] == "applied"
    assert second["recovery"]["state"] == "converged"
    assert len(store.deltas) == 1
    assert len(store.graph) == 0
