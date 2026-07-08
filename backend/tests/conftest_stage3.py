"""Stage 3 shared test fixtures.

Provides:
* ``fake_graph_set_with_members`` — (service, graph_set_id) tuple with a
  registered graph set carrying asserted_ontology + asserted_data members.
* ``second_graph_set_same_scope`` — graph set id of a second set under the
  same scope.
* ``second_graph_set_with_one_fewer_entity`` — graph set id of a second set
  whose asserted_data graph contains one fewer triple than the base.
* ``fake_store`` — a FakeStore configured for the delta composer.

Pattern copied from ``backend/tests/test_semantic_stage2_e2e.py`` lines 30–80
and ``backend/tests/test_semantic_read_model_stage2_execution.py``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.semantic import router
from app.core.config import Settings
from app.repositories.models import (
    SemanticEditAuditModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
)
from app.repositories.rdf_store import RdfStoreRepository, SparqlResult, UpdateResult
from app.services.semantic_read_model import SemanticReadModelService
from app.services.semantic_read_scope import SemanticReadScopeResolver


PREFIX = "http://op.local/semantic/"
GRAPH_PREFIX = f"{PREFIX}graph/"
ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-stage3"
DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-stage3"
ONTOLOGY_GRAPH_B = f"{GRAPH_PREFIX}ontology/ont-stage3-b"
DATA_GRAPH_B = f"{GRAPH_PREFIX}data/ont-stage3-b"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.bindings = rows


class FakeStore(RdfStoreRepository):
    """Hybrid fake: stores triple data per named graph (for the delta
    composer's CONSTRUCT-style queries) and records update/queries for
    inspection."""

    def __init__(self) -> None:
        self.updates: list[str] = []
        self.queries: list[str] = []
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None
        # graph_iri -> list of (s, p, o) tuples
        self._triples: dict[str, set[tuple[str, str, str]]] = {}
        self._graphs: set[str] = set()

    # --- write paths (canonical-writes apply_dataset_delta) ------------

    def update_sparql(self, update: str):
        self.updates.append(update)
        return UpdateResult()

    def apply_dataset_delta(self, *args, **kwargs):  # type: ignore[override]
        # Some canonical-write tests apply deltas via this signature; we
        # accept anything and return a no-op result.
        return UpdateResult()

    def clear_graph(self, graph_iri: str):
        self._triples.pop(graph_iri, None)
        self._graphs.discard(graph_iri)
        return UpdateResult()

    # --- read paths ----------------------------------------------------

    def query_sparql(self, query: str, timeout_seconds: float, limit: int):
        self.queries.append(query)
        return SparqlResult(
            result={"head": {"vars": []}, "results": {"bindings": []}}
        )

    def query_read_model(
        self,
        query: str,
        graph_iris: list[str],
        timeout_seconds: float,
        limit: int,
    ):
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        # The graph-set-staleness template uses the ``?count`` projection
        # over asserted_data members; we return zero missing-evidence rows.
        if "COUNT" in query.upper() and "missing_evidence" in query:
            return _Result([{"count": {"value": "0"}}])
        # The CONSTRUCT-style triple listing used by the delta composer
        # (``SELECT ?s ?p ?o`` or ``CONSTRUCT``). We approximate by
        # returning the union of triples stored under each requested graph.
        rows: list[dict[str, Any]] = []
        for graph_iri in graph_iris:
            for s, p, o in self._triples.get(graph_iri, set()):
                rows.append({
                    "s": {"value": s, "type": "uri"},
                    "p": {"value": p, "type": "uri"},
                    "o": {"value": o, "type": "literal"},
                    "subject": {"value": s},
                    "predicate": {"value": p},
                    "object": {"value": o},
                    "graph": {"value": graph_iri},
                })
        return _Result(rows)

    def export_dataset(self, format: str, graph_iris=None) -> str:  # noqa: A002
        return ""

    def graph_exists(self, graph_iri: str) -> bool:
        return graph_iri in self._graphs

    def get_graph(self, graph_iri: str, format: str) -> str:  # noqa: A002
        return ""

    def set_graph(self, graph_iri: str, content: str) -> None:
        self._graphs.add(graph_iri)

    def graph_content_hash(self, graph_iri: str):
        return None

    # --- test helpers --------------------------------------------------

    def set_triples(
        self, graph_iri: str, triples: list[tuple[str, str, str]]
    ) -> None:
        """Replace the triple set for a named graph."""
        self._triples[graph_iri] = set(triples)
        self._graphs.add(graph_iri)


def _settings() -> Settings:
    return Settings(
        semantic_base_iri=f"{PREFIX}ns/",
        semantic_graph_iri_prefix=GRAPH_PREFIX,
        semantic_product_write_mode="canonical_only",
        semantic_read_mode="canonical",
        semantic_legacy_write_blocked=True,
    )


def _seed_graph_set(
    session: Session,
    *,
    graph_set_id: str,
    name: str,
    members: list[tuple[str, str]],
    scope_type: str = "ontology",
    scope_id: str = "ont-stage3",
    source_signature: str = "sig-stage3",
) -> str:
    gs = SemanticGraphSetModel(
        id=graph_set_id,
        name=name,
        scope_type=scope_type,
        scope_id=scope_id,
        status="active",
        source_signature=source_signature,
    )
    session.add(gs)
    for idx, (iri, role) in enumerate(members):
        gs.members.append(
            SemanticGraphSetMemberModel(
                id=f"{graph_set_id}-m-{idx}",
                graph_iri=iri,
                role=role,
                required=True,
                sort_order=idx,
            )
        )
    session.commit()
    return graph_set_id


def _build_service(session: Session, store: FakeStore) -> SemanticReadModelService:
    """Build a real SemanticReadModelService wired with the in-memory
    session and FakeStore, suitable for direct unit testing of composers."""
    resolver = SemanticReadScopeResolver(session)
    return SemanticReadModelService(
        rdf_store=store,
        scope_resolver=resolver,
        session=session,
    )


@pytest.fixture()
def fake_store() -> FakeStore:
    store = FakeStore()
    # The default asserted data graph contains two triples; the "second with
    # one fewer entity" fixture (below) builds a target graph with one triple
    # removed so the delta composer observes exactly one removal.
    store.set_triples(
        DATA_GRAPH,
        [
            (f"{PREFIX}ns/entity/alice", f"{PREFIX}ns/property/name", "Alice"),
            (f"{PREFIX}ns/entity/alice", f"{PREFIX}ns/property/email", "alice@example.com"),
        ],
    )
    store.set_triples(
        ONTOLOGY_GRAPH,
        [
            (f"{PREFIX}ns/class/Student", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2000/01/rdf-schema#Class"),
        ],
    )
    return store


@pytest.fixture()
def fake_graph_set_with_members(
    in_memory_session: Session, fake_store: FakeStore
) -> tuple[SemanticReadModelService, str]:
    graph_set_id = _seed_graph_set(
        in_memory_session,
        graph_set_id="gs-stage3-base",
        name="stage3-base",
        members=[
            (ONTOLOGY_GRAPH, "asserted_ontology"),
            (DATA_GRAPH, "asserted_data"),
        ],
    )
    service = _build_service(in_memory_session, fake_store)
    return service, graph_set_id


@pytest.fixture()
def second_graph_set_same_scope(
    in_memory_session: Session, fake_store: FakeStore
) -> str:
    return _seed_graph_set(
        in_memory_session,
        graph_set_id="gs-stage3-other",
        name="stage3-other",
        members=[
            (ONTOLOGY_GRAPH_B, "asserted_ontology"),
            (DATA_GRAPH_B, "asserted_data"),
        ],
    )


@pytest.fixture()
def second_graph_set_with_one_fewer_entity(
    in_memory_session: Session, fake_store: FakeStore
) -> str:
    """A second graph set whose asserted_data graph contains one fewer
    triple than the base fixture's DATA_GRAPH."""
    other_data_graph = f"{GRAPH_PREFIX}data/ont-stage3-dim"
    fake_store.set_triples(
        other_data_graph,
        [
            (f"{PREFIX}ns/entity/alice", f"{PREFIX}ns/property/name", "Alice"),
            # email triple deliberately omitted -> removed in delta
        ],
    )
    other_ontology_graph = f"{GRAPH_PREFIX}ontology/ont-stage3-dim"
    fake_store.set_triples(
        other_ontology_graph,
        [
            (f"{PREFIX}ns/class/Student", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2000/01/rdf-schema#Class"),
        ],
    )
    return _seed_graph_set(
        in_memory_session,
        graph_set_id="gs-stage3-dim",
        name="stage3-dim",
        members=[
            (other_ontology_graph, "asserted_ontology"),
            (other_data_graph, "asserted_data"),
        ],
    )


def client_for(store: FakeStore, session: Session) -> TestClient:
    """Helper for any test that needs the FastAPI client (HTTP-level tests)."""
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: _settings()
    return TestClient(app)


__all__ = [
    "PREFIX",
    "GRAPH_PREFIX",
    "ONTOLOGY_GRAPH",
    "DATA_GRAPH",
    "ONTOLOGY_GRAPH_B",
    "DATA_GRAPH_B",
    "FakeStore",
    "client_for",
    "fake_graph_set_with_members",
    "fake_store",
    "second_graph_set_same_scope",
    "second_graph_set_with_one_fewer_entity",
]
