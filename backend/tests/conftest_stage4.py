"""Stage 4 shared test fixtures.

Provides:
* ``fake_graph_set_with_evidence`` — (service, graph_set_id) tuple with a
  registered graph set whose asserted_data graph carries a fact with a
  ``prov:wasDerivedFrom`` triple pointing to an EvidenceChunk.
* ``fake_store_with_prov_bindings`` — FakeStore pre-seeded with entity-search
  rows (Acme Corp) and a ``prov:wasDerivedFrom`` triple plus chunk metadata
  for the evidence_bindings field set.
* ``fake_reasoning_run_consistency`` — inserts a ``SemanticReasoningRunModel``
  row whose ``run_metadata['tasks']`` contains ``"consistency"`` and whose
  ``consistent`` is True so the ``owl-consistency-summary`` composer has data
  to project.

Mirrors the FakeStore pattern from ``conftest_stage3.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.repositories.models import (
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticReasoningRunModel,
)
from app.repositories.rdf_store import RdfStoreRepository, SparqlResult, UpdateResult
from app.services.semantic_read_model import SemanticReadModelService
from app.services.semantic_read_scope import SemanticReadScopeResolver

from conftest_stage3 import PREFIX, GRAPH_PREFIX


# Stage 4 fixtures reuse the Stage 3 graph-set iris to keep the test
# surface minimal. A separate data graph would require a new member row and
# would dilute the entity-search result set.
EVIDENCE_DATA_GRAPH = f"{GRAPH_PREFIX}data/ont-stage4"
EVIDENCE_ONTOLOGY_GRAPH = f"{GRAPH_PREFIX}ontology/ont-stage4"

# IRIs used in the seeded triples below.
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
RDFS_COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
OWL_CLASS = "http://www.w3.org/2000/01/rdf-schema#Class"
PROV_DERIVED = "http://www.w3.org/ns/prov#wasDerivedFrom"
ACME_ENTITY = f"{PREFIX}ns/entity/acme"
ACME_LABEL = "Acme Corp"
ACME_CLASS = f"{PREFIX}ns/class/Organization"
ACME_CLASS_LABEL = "Organization"
ACME_COMMENT = "Acme is a manufacturer of widgets"

# EvidenceChunk IRI per the Phase 2 namespace convention
# (tag:ontology-platform.internal,2026:evidence/{doc_id}/{sequence}).
CHUNK_IRI = "tag:ontology-platform.internal,2026:evidence/doc-1/0"
DOC_IRI = "tag:ontology-platform.internal,2026:evidence/doc-1"
DOC_FILENAME = "acme-overview.pdf"
CHUNK_SEQUENCE = "0"
CHUNK_TEXT = "Acme is a manufacturer of widgets."

# Tag namespace used by the canonical-write namespace mapper.
TAG_NS = "tag:ontology-platform.internal,2026:"
TAG_SOURCE_DOC = TAG_NS + "sourceDocument"
TAG_SEQUENCE = TAG_NS + "sequence"
TAG_TEXT = TAG_NS + "text"
TAG_EVIDENCE_CHUNK = TAG_NS + "EvidenceChunk"


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.bindings = rows


class FakeStoreStage4(RdfStoreRepository):
    """FakeStore variant that interprets a subset of SPARQL query shapes
    used by the Stage 4 read-model composers:

    1. ``entity-search`` (``?entity ?label ?comment ?class ?class_label``)
       with an optional ``?q`` substring filter and an optional ``?class``
       IRI equality filter. Rows come from a pre-seeded list.
    2. ``prov:wasDerivedFrom`` lookup for the evidence bindings field set —
       projects ``?chunk ?doc ?sequence ?char_start ?char_end ?text`` rows
       joined to ``?fact``.
    3. Anything else falls through to an empty result.

    Tests seed entities via ``add_entity`` and bindings via ``add_binding``.
    """

    def __init__(self) -> None:
        self.entities: list[dict[str, Any]] = []
        self.bindings: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self._triples: dict[str, set[tuple[str, str, str]]] = {}
        self._graphs: set[str] = set()

    # --- write paths (canonical writes) -------------------------------
    def update_sparql(self, update: str):
        return UpdateResult()

    def apply_dataset_delta(self, *args, **kwargs):  # type: ignore[override]
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
        self.queries.append(query)
        upper = query.upper()
        # Entity search projects ?entity, ?label, ?class, and ?class_label. The
        # bound ?q literal appears inside the FILTER as LCASE(?q).
        if "?ENTITY" in upper and "?CLASS" in upper and "?LABEL" in upper:
            q_value = _extract_marker_literal(query, "q_filter")
            class_filter = _extract_marker_iri(query, "class_iri_filter")
            rows: list[dict[str, Any]] = []
            for ent in self.entities:
                if q_value and q_value.lower() not in (
                    (ent.get("label") or "").lower()
                    + (ent.get("comment") or "").lower()
                    + ent["iri"].lower()
                ):
                    continue
                if class_filter and ent.get("class") != class_filter:
                    continue
                row = {
                    "entity": {"value": ent["iri"], "type": "uri"},
                    "label": {"value": ent.get("label") or "", "type": "literal"},
                    "class": {"value": ent.get("class") or "", "type": "uri"},
                    "class_label": {
                        "value": ent.get("class_label") or "",
                        "type": "literal",
                    },
                    "graph": {"value": ent["graph"], "type": "uri"},
                }
                if "?COMMENT" in upper:
                    row["comment"] = {
                        "value": ent.get("comment") or "",
                        "type": "literal",
                    }
                rows.append(row)
            return _Result(rows[:limit])
        # prov:wasDerivedFrom evidence binding lookup.
        if "WASDERIVEDFROM" in upper or "?CHUNK" in upper:
            rows = []
            for b in self.bindings:
                row_dict: dict[str, Any] = {
                    "chunk": {"value": b["chunk"], "type": "uri"},
                    "doc": {"value": b["doc"], "type": "uri"},
                    "sequence": {"value": str(b["sequence"]), "type": "literal"},
                    "char_start": {"value": str(b["char_start"]), "type": "literal"},
                    "char_end": {"value": str(b["char_end"]), "type": "literal"},
                    "text": {"value": b["text"], "type": "literal"},
                    "graph": {"value": b["graph"], "type": "uri"},
                }
                if b.get("fact") is not None:
                    row_dict["fact"] = {"value": b["fact"], "type": "uri"}
                rows.append(row_dict)
            return _Result(rows[:limit])
        # Fallback: return empty bindings.
        return _Result([])

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
    def add_entity(
        self,
        *,
        iri: str,
        label: str | None,
        comment: str | None,
        klass: str | None,
        class_label: str | None,
        graph: str,
    ) -> None:
        self.entities.append({
            "iri": iri,
            "label": label,
            "comment": comment,
            "class": klass,
            "class_label": class_label,
            "graph": graph,
        })

    def add_binding(
        self,
        *,
        chunk: str,
        doc: str,
        sequence: int,
        char_start: int,
        char_end: int,
        text: str,
        graph: str,
        fact: str | None = None,
    ) -> None:
        self.bindings.append({
            "chunk": chunk,
            "doc": doc,
            "sequence": sequence,
            "char_start": char_start,
            "char_end": char_end,
            "text": text,
            "graph": graph,
            "fact": fact,
        })


def _extract_marker_literal(query: str, marker: str) -> str | None:
    """Find a comment marker ``# marker: "value"`` in a SPARQL query and
    return the value, or None if absent."""
    import re

    pattern = rf"#\s*{re.escape(marker)}:\s*\"([^\"]*)\""
    match = re.search(pattern, query)
    if match:
        return match.group(1)
    return None


def _extract_marker_iri(query: str, marker: str) -> str | None:
    """Find a comment marker ``# marker: <iri>`` in a SPARQL query and
    return the IRI, or None if absent."""
    import re

    pattern = rf"#\s*{re.escape(marker)}:\s*<([^>]+)>"
    match = re.search(pattern, query)
    if match:
        return match.group(1)
    return None


def _extract_bound_literal(query: str, var_name: str) -> str | None:
    """Find a literal binding ``?var_name "value"`` in a SPARQL query and
    return the value, or None if the variable is unbound / optional."""
    import re

    pattern = rf"\?{var_name}\s+\"([^\"]*)\""
    match = re.search(pattern, query)
    if match:
        return match.group(1)
    return None


def _extract_bound_iri(query: str, var_name: str) -> str | None:
    """Find a literal binding ``?var_name <iri>`` in a SPARQL query and
    return the IRI, or None if unbound."""
    import re

    pattern = rf"\?{var_name}\s+<([^>]+)>"
    match = re.search(pattern, query)
    if match:
        return match.group(1)
    return None


def _seed_stage4_graph_set(
    session: Session,
    *,
    graph_set_id: str,
    name: str,
    members: list[tuple[str, str]],
    scope_type: str = "ontology",
    scope_id: str = "ont-stage4",
    source_signature: str = "sig-stage4",
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


def _build_service(
    session: Session, store: FakeStoreStage4
) -> SemanticReadModelService:
    resolver = SemanticReadScopeResolver(session)
    return SemanticReadModelService(
        rdf_store=store,
        scope_resolver=resolver,
        session=session,
    )


@pytest.fixture()
def fake_store_with_prov_bindings() -> FakeStoreStage4:
    """Pre-seed the FakeStore with the Acme Corp entity + an evidence binding."""
    store = FakeStoreStage4()
    store.add_entity(
        iri=ACME_ENTITY,
        label=ACME_LABEL,
        comment=ACME_COMMENT,
        klass=ACME_CLASS,
        class_label=ACME_CLASS_LABEL,
        graph=EVIDENCE_DATA_GRAPH,
    )
    store.add_binding(
        chunk=CHUNK_IRI,
        doc=DOC_IRI,
        sequence=0,
        char_start=0,
        char_end=len(CHUNK_TEXT),
        text=CHUNK_TEXT,
        graph=EVIDENCE_DATA_GRAPH,
        fact=ACME_ENTITY,
    )
    return store


@pytest.fixture()
def fake_graph_set_with_evidence(
    in_memory_session: Session, fake_store_with_prov_bindings: FakeStoreStage4
) -> tuple[SemanticReadModelService, str]:
    graph_set_id = _seed_stage4_graph_set(
        in_memory_session,
        graph_set_id="gs-stage4-evidence",
        name="stage4-evidence",
        members=[
            (EVIDENCE_ONTOLOGY_GRAPH, "asserted_ontology"),
            (EVIDENCE_DATA_GRAPH, "asserted_data"),
        ],
    )
    service = _build_service(in_memory_session, fake_store_with_prov_bindings)
    return service, graph_set_id


@pytest.fixture()
def fake_reasoning_run_consistency(
    in_memory_session: Session,
) -> str:
    """Insert a SemanticReasoningRunModel row for the graph set returned by
    ``fake_graph_set_with_evidence``. Returns the run id."""
    run_id = "rr-stage4-consistency"
    reasoning_result = f"{GRAPH_PREFIX}reasoning-result/run-stage4"
    in_memory_session.add(
        SemanticReasoningRunModel(
            id=run_id,
            source_graph_iris=[EVIDENCE_ONTOLOGY_GRAPH, EVIDENCE_DATA_GRAPH],
            result_graph_iri=reasoning_result,
            reasoner="owl2dl",
            status="completed",
            consistent=True,
            started_at=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 7, 10, 5, tzinfo=timezone.utc),
            run_metadata={
                "tasks": ["consistency"],
                "classification": {"profile": "owl2_dl"},
                "entailments": [
                    {"subject": ACME_ENTITY, "predicate": RDF_TYPE, "object": ACME_CLASS},
                ],
                "graph_set_id": "gs-stage4-evidence",
            },
        )
    )
    in_memory_session.commit()
    return run_id


__all__ = [
    "ACME_ENTITY",
    "ACME_LABEL",
    "ACME_CLASS",
    "ACME_CLASS_LABEL",
    "ACME_COMMENT",
    "CHUNK_IRI",
    "DOC_IRI",
    "DOC_FILENAME",
    "CHUNK_TEXT",
    "EVIDENCE_DATA_GRAPH",
    "EVIDENCE_ONTOLOGY_GRAPH",
    "FakeStoreStage4",
    "fake_graph_set_with_evidence",
    "fake_store_with_prov_bindings",
    "fake_reasoning_run_consistency",
]
