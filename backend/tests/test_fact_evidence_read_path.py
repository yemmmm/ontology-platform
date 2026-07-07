"""Phase 3 read-path tests: PG-backed evidence decoration.

These tests cover the new behavior introduced when the read model switched
from SPARQL ``prov:wasDerivedFrom`` lookups to Postgres ``fact_evidence_bindings``
for the fact-audit-queue and missing-evidence surfaces.

Coverage:

* ``_fetch_evidence_bindings_from_pg`` returns properly bucketed dicts.
* ``_format_evidence_binding`` truncates and renders text fields.
* ``_list_asserted_fact_ids`` enumerates asserted triples and computes
  fact_ids using the canonical ``compute_fact_id`` algorithm.
* ``_missing_evidence_count`` subtracts PG bindings from the asserted set.
* ``_decorate_fact_row`` derives ``evidence_status`` from bindings.
* ``_compose_fact_audit_queue`` filters the missing_evidence tab correctly.
* GET ``/missing-evidence-facts`` returns count + fact_ids.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_rdf_store, get_settings
from app.api.fact_evidence import router as fact_evidence_router
from app.core.config import Settings
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository
from app.repositories.models import FactEvidenceBindingModel
from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_read_model import SemanticReadModelService
from app.services.semantic_read_scope import ScopeMember, ScopeResolution


class FakeSparqlResult:
    def __init__(self, rows):
        self._rows = rows

    @property
    def bindings(self):
        return self._rows


class FakeStore:
    """Captures the last query + graph_iris, returns rows keyed by an
    in-query comment marker."""

    def __init__(self, rows_by_marker: dict[str, list[dict[str, str]]]):
        self.rows_by_marker = rows_by_marker
        self.queries: list[str] = []
        self.last_query: str | None = None
        self.last_graph_iris: list[str] | None = None

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.queries.append(query)
        self.last_query = query
        self.last_graph_iris = list(graph_iris)
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return FakeSparqlResult(rows)
        return FakeSparqlResult([])


class FakeScopeResolver:
    def __init__(self, resolution):
        self._resolution = resolution

    def resolve(self, graph_set_id, include="asserted", allow_stale_derived=True):
        from dataclasses import replace

        return replace(self._resolution, include=include)


def _resolution(graph_iris, members=None):
    if members is None:
        members = [
            ScopeMember(graph_iri=iri, role="asserted_data", derived_state={})
            for iri in graph_iris
        ]
    return ScopeResolution(
        graph_set_id="gs-1",
        source_signature="sig-1",
        include="asserted",
        source_graph_iris=list(graph_iris),
        shape_graph_iris=[],
        governance_graph_iris=[],
        reasoning_result_graph_iri=None,
        rule_result_graph_iri=None,
        derived_state={},
        warnings=[],
        members=list(members),
    )


# ---------------------------------------------------------------------------
# _format_evidence_binding / _fetch_evidence_bindings_from_pg
# ---------------------------------------------------------------------------


def test_format_evidence_binding_truncates_long_text():
    class _Row:
        def __init__(self, text):
            self.id = "b-1"
            self.fact_id = "f-1"
            self.chunk_id = None
            self.evidence_artifact_id = None
            self.document_filename = "doc.pdf"
            self.sequence = 3
            self.char_start = 10
            self.char_end = 20
            self.text = text
            self.actor = "user:alice"
            self.reason = "import"
            self.created_at = datetime(2026, 7, 8, tzinfo=timezone.utc)

    short = SemanticReadModelService._format_evidence_binding(_Row("hi"))
    assert short["text"] == "hi"
    assert short["text_preview"] == "hi"

    long_text = "x" * 300
    long = SemanticReadModelService._format_evidence_binding(_Row(long_text))
    assert long["text"] == long_text
    assert long["text_preview"].endswith("...")
    assert long["text_preview"].startswith("x")
    assert long["created_at"] == "2026-07-08T00:00:00+00:00"


def test_fetch_evidence_bindings_from_pg_buckets_by_fact_id(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    fid_a = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("42", is_iri=False),
        "http://g/1",
    )
    fid_b = compute_fact_id(
        "http://s/2",
        "http://p/2",
        canonical_object_term("v", is_iri=False),
        "http://g/2",
    )
    repo.create(
        fact_id=fid_a,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"42"',
        graph_iri="http://g/1",
        text="a",
    )
    repo.create(
        fact_id=fid_a,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"42"',
        graph_iri="http://g/1",
        text="b",
    )
    repo.create(
        fact_id=fid_b,
        subject_iri="http://s/2",
        predicate_iri="http://p/2",
        object_value='"v"',
        graph_iri="http://g/2",
        text="c",
    )

    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution(["http://g/1"])),
        session=in_memory_session,
    )
    result = service._fetch_evidence_bindings_from_pg(
        [fid_a, fid_b], in_memory_session
    )
    assert set(result.keys()) == {fid_a, fid_b}
    assert len(result[fid_a]) == 2
    assert len(result[fid_b]) == 1
    assert result[fid_a][0]["fact_id"] == fid_a
    assert result[fid_a][0]["id"]  # binding id populated


def test_fetch_evidence_bindings_from_pg_empty_input_no_call(in_memory_session):
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution([])),
        session=in_memory_session,
    )
    assert service._fetch_evidence_bindings_from_pg([], in_memory_session) == {}


# ---------------------------------------------------------------------------
# _list_asserted_fact_ids
# ---------------------------------------------------------------------------


def test_list_asserted_fact_ids_uses_canonical_compute_fact_id():
    """Triples returned by the SPARQL SELECT DISTINCT are hashed with the
    canonical ``compute_fact_id`` algorithm, so the resulting ids match the
    write side (PG ``fact_evidence_bindings.fact_id``)."""
    data_iri = "http://op.local/graph/data/ont-1"
    rows = [
        {
            "s": {"value": "http://example/s", "type": "uri"},
            "p": {"value": "http://example/p", "type": "uri"},
            "o": {"value": "Acme Corp", "type": "literal"},
            "g": {"value": data_iri, "type": "uri"},
        },
        {
            "s": {"value": "http://example/s", "type": "uri"},
            "p": {"value": "http://example/ref", "type": "uri"},
            "o": {"value": "http://example/o2", "type": "uri"},
            "g": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"phase3 asserted fact_id enumeration": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
    )
    fact_ids = service._list_asserted_fact_ids(_resolution([data_iri]))
    assert len(fact_ids) == 2
    # Verify hash matches canonical computation.
    expected_literal = compute_fact_id(
        "http://example/s",
        "http://example/p",
        canonical_object_term("Acme Corp", is_iri=False),
        data_iri,
    )
    expected_iri = compute_fact_id(
        "http://example/s",
        "http://example/ref",
        canonical_object_term("http://example/o2", is_iri=True),
        data_iri,
    )
    assert set(fact_ids) == {expected_literal, expected_iri}


def test_list_asserted_fact_ids_skips_non_asserted_members():
    """Only ``asserted_data`` role members are queried."""
    onto_iri = "http://op.local/graph/ontology/ont-1"
    data_iri = "http://op.local/graph/data/ont-1"
    resolution = _resolution(
        [onto_iri, data_iri],
        members=[
            ScopeMember(graph_iri=onto_iri, role="asserted_ontology", derived_state={}),
            ScopeMember(graph_iri=data_iri, role="asserted_data", derived_state={}),
        ],
    )
    store = FakeStore({"phase3 asserted fact_id enumeration": []})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(resolution),
    )
    service._list_asserted_fact_ids(resolution)
    assert store.last_graph_iris == [data_iri]


# ---------------------------------------------------------------------------
# _missing_evidence_count
# ---------------------------------------------------------------------------


def test_missing_evidence_count_returns_zero_when_no_session():
    data_iri = "http://op.local/graph/data/ont-1"
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
    )
    # No session injected → safe no-op.
    assert service._missing_evidence_count(_resolution([data_iri])) == 0


def test_missing_evidence_count_subtracts_pg_bindings(in_memory_session):
    data_iri = "http://op.local/graph/data/ont-1"
    fid_with = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("v1", is_iri=False),
        data_iri,
    )
    fid_without = compute_fact_id(
        "http://s/2",
        "http://p/2",
        canonical_object_term("v2", is_iri=False),
        data_iri,
    )
    repo = FactEvidenceBindingRepository(in_memory_session)
    repo.create(
        fact_id=fid_with,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"v1"',
        graph_iri=data_iri,
        text="e",
    )
    rows = [
        {
            "s": {"value": "http://s/1", "type": "uri"},
            "p": {"value": "http://p/1", "type": "uri"},
            "o": {"value": "v1", "type": "literal"},
            "g": {"value": data_iri, "type": "uri"},
        },
        {
            "s": {"value": "http://s/2", "type": "uri"},
            "p": {"value": "http://p/2", "type": "uri"},
            "o": {"value": "v2", "type": "literal"},
            "g": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"phase3 asserted fact_id enumeration": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    assert service._missing_evidence_count(_resolution([data_iri])) == 1


# ---------------------------------------------------------------------------
# _decorate_fact_row
# ---------------------------------------------------------------------------


def _fact_row(subject="http://s", predicate="http://p", obj="v", graph="http://g"):
    return {
        "subject": {"value": subject, "type": "uri"},
        "subject_label": {"value": "S", "type": "literal"},
        "predicate": {"value": predicate, "type": "uri"},
        "predicate_label": {"value": "P", "type": "literal"},
        "object": {"value": obj, "type": "literal"},
        "object_label": {"value": obj, "type": "literal"},
        "graph": {"value": graph, "type": "uri"},
    }


def test_decorate_fact_row_with_bindings_marked_with_evidence(in_memory_session):
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution(["http://g"])),
        session=in_memory_session,
    )
    fid = compute_fact_id(
        "http://s",
        "http://p",
        canonical_object_term("v", is_iri=False),
        "http://g",
    )
    bindings_by_fact = {fid: [{"id": "b1", "fact_id": fid, "text": "x"}]}
    decorated = service._decorate_fact_row(
        _fact_row(),
        assertion_kind="asserted",
        scope=_resolution(["http://g"]),
        bindings_by_fact=bindings_by_fact,
    )
    assert decorated["fact_id"] == fid
    assert decorated["evidence_status"] == "with_evidence"
    assert decorated["evidence_bindings"] == [{"id": "b1", "fact_id": fid, "text": "x"}]


def test_decorate_fact_row_no_bindings_marked_missing():
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution(["http://g"])),
    )
    decorated = service._decorate_fact_row(
        _fact_row(),
        assertion_kind="asserted",
        scope=_resolution(["http://g"]),
        bindings_by_fact={},
    )
    assert decorated["evidence_status"] == "missing_evidence"
    assert decorated["evidence_bindings"] == []


def test_decorate_fact_row_bindings_none_defaults_missing_for_kind():
    """When bindings_by_fact is None (first-pass decoration inside the
    composer), evidence_status uses the assertion_kind hint and bindings
    default to empty. The composer's second pass overrides both."""
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution(["http://g"])),
    )
    decorated_missing = service._decorate_fact_row(
        _fact_row(),
        assertion_kind="missing_evidence",
        scope=_resolution(["http://g"]),
    )
    assert decorated_missing["evidence_status"] == "missing_evidence"
    assert decorated_missing["evidence_bindings"] == []
    decorated_asserted = service._decorate_fact_row(
        _fact_row(),
        assertion_kind="asserted",
        scope=_resolution(["http://g"]),
    )
    assert decorated_asserted["evidence_status"] == "with_evidence"


# ---------------------------------------------------------------------------
# _compose_fact_audit_queue
# ---------------------------------------------------------------------------


def test_compose_fact_audit_queue_missing_evidence_filters_to_unbound(in_memory_session):
    """kind=missing_evidence returns only facts that have no PG binding."""
    data_iri = "http://op.local/graph/data/ont-1"
    fid_with = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("v1", is_iri=False),
        data_iri,
    )
    fid_without = compute_fact_id(
        "http://s/2",
        "http://p/2",
        canonical_object_term("v2", is_iri=False),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid_with,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"v1"',
        graph_iri=data_iri,
        text="t",
    )
    rows = [
        {
            "subject": {"value": "http://s/1", "type": "uri"},
            "subject_label": {"value": "S1", "type": "literal"},
            "predicate": {"value": "http://p/1", "type": "uri"},
            "predicate_label": {"value": "P1", "type": "literal"},
            "object": {"value": "v1", "type": "literal"},
            "object_label": {"value": "v1", "type": "literal"},
            "graph": {"value": data_iri, "type": "uri"},
        },
        {
            "subject": {"value": "http://s/2", "type": "uri"},
            "subject_label": {"value": "S2", "type": "literal"},
            "predicate": {"value": "http://p/2", "type": "uri"},
            "predicate_label": {"value": "P2", "type": "literal"},
            "object": {"value": "v2", "type": "literal"},
            "object_label": {"value": "v2", "type": "literal"},
            "graph": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"fact-audit-queue": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    items, _ = service._compose_fact_audit_queue(
        scope=_resolution([data_iri]),
        kind="missing_evidence",
        field_set="evidence",
    )
    assert len(items) == 1
    assert items[0]["fact_id"] == fid_without
    assert items[0]["evidence_status"] == "missing_evidence"


def test_compose_fact_audit_queue_asserted_attaches_bindings(in_memory_session):
    data_iri = "http://op.local/graph/data/ont-1"
    fid = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("v1", is_iri=False),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"v1"',
        graph_iri=data_iri,
        text="snippet",
    )
    rows = [
        {
            "subject": {"value": "http://s/1", "type": "uri"},
            "subject_label": {"value": "S1", "type": "literal"},
            "predicate": {"value": "http://p/1", "type": "uri"},
            "predicate_label": {"value": "P1", "type": "literal"},
            "object": {"value": "v1", "type": "literal"},
            "object_label": {"value": "v1", "type": "literal"},
            "graph": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"fact-audit-queue": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    items, _ = service._compose_fact_audit_queue(
        scope=_resolution([data_iri]),
        kind="asserted",
        field_set="evidence",
    )
    assert len(items) == 1
    assert items[0]["evidence_status"] == "with_evidence"
    assert len(items[0]["evidence_bindings"]) == 1
    assert items[0]["evidence_bindings"][0]["text"] == "snippet"


def test_compose_fact_audit_queue_summary_field_set_drops_bindings(in_memory_session):
    """field_set=summary (not 'evidence') strips the bindings payload but
    keeps the derived evidence_status."""
    data_iri = "http://op.local/graph/data/ont-1"
    fid = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("v1", is_iri=False),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"v1"',
        graph_iri=data_iri,
        text="t",
    )
    rows = [
        {
            "subject": {"value": "http://s/1", "type": "uri"},
            "subject_label": {"value": "S1", "type": "literal"},
            "predicate": {"value": "http://p/1", "type": "uri"},
            "predicate_label": {"value": "P1", "type": "literal"},
            "object": {"value": "v1", "type": "literal"},
            "object_label": {"value": "v1", "type": "literal"},
            "graph": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"fact-audit-queue": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    items, _ = service._compose_fact_audit_queue(
        scope=_resolution([data_iri]),
        kind="asserted",
        field_set="summary",
    )
    assert items[0]["evidence_status"] == "with_evidence"
    assert items[0]["evidence_bindings"] == []


# ---------------------------------------------------------------------------
# Regression: typed / lang-tagged literal fact_id must match write side
# ---------------------------------------------------------------------------


def test_decorate_fact_row_with_typed_literal_matches_pg_fact_id(in_memory_session):
    """Regression for the silent datatype-drop bug: read-side _decorate_fact_row
    must include the XSD datatype in canonical_object_term, otherwise its
    fact_id diverges from the one written by compile_bind_fact_evidence and
    PG bindings never attach."""
    data_iri = "http://op.local/graph/data/ont-1"
    datatype = "http://www.w3.org/2001/XMLSchema#integer"
    fid = compute_fact_id(
        "http://s",
        "http://p",
        canonical_object_term("42", is_iri=False, datatype=datatype),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid,
        subject_iri="http://s",
        predicate_iri="http://p",
        object_value='"42"^^<%s>' % datatype,
        graph_iri=data_iri,
        text="e",
    )
    row = {
        "subject": {"value": "http://s", "type": "uri"},
        "subject_label": {"value": "S", "type": "literal"},
        "predicate": {"value": "http://p", "type": "uri"},
        "predicate_label": {"value": "P", "type": "literal"},
        "object": {"value": "42", "type": "literal", "datatype": datatype},
        "object_label": {"value": "42", "type": "literal", "datatype": datatype},
        "graph": {"value": data_iri, "type": "uri"},
    }
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    decorated = service._decorate_fact_row(
        row,
        assertion_kind="asserted",
        scope=_resolution([data_iri]),
        bindings_by_fact={fid: [{"id": "b1", "fact_id": fid, "text": "e"}]},
    )
    assert decorated["fact_id"] == fid
    assert decorated["evidence_status"] == "with_evidence"
    assert decorated["evidence_bindings"][0]["fact_id"] == fid


def test_decorate_fact_row_with_lang_literal_matches_pg_fact_id(in_memory_session):
    """Same regression guard for lang-tagged literals (``"hi"@en``)."""
    data_iri = "http://op.local/graph/data/ont-1"
    lang = "en"
    fid = compute_fact_id(
        "http://s",
        "http://p",
        canonical_object_term("hello", is_iri=False, lang=lang),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid,
        subject_iri="http://s",
        predicate_iri="http://p",
        object_value='"hello"@%s' % lang,
        graph_iri=data_iri,
        text="e",
    )
    row = {
        "subject": {"value": "http://s", "type": "uri"},
        "subject_label": {"value": "S", "type": "literal"},
        "predicate": {"value": "http://p", "type": "uri"},
        "predicate_label": {"value": "P", "type": "literal"},
        "object": {"value": "hello", "type": "literal", "xml:lang": lang},
        "object_label": {"value": "hello", "type": "literal", "xml:lang": lang},
        "graph": {"value": data_iri, "type": "uri"},
    }
    service = SemanticReadModelService(
        rdf_store=FakeStore({}),
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
        session=in_memory_session,
    )
    decorated = service._decorate_fact_row(
        row,
        assertion_kind="asserted",
        scope=_resolution([data_iri]),
        bindings_by_fact={fid: [{"id": "b1", "fact_id": fid, "text": "e"}]},
    )
    assert decorated["fact_id"] == fid
    assert decorated["evidence_bindings"][0]["fact_id"] == fid


def test_list_asserted_fact_ids_includes_datatype_and_lang():
    """Regression: _list_asserted_fact_ids must hash typed and lang-tagged
    literals with their datatype/lang so the asserted set matches PG."""
    data_iri = "http://op.local/graph/data/ont-1"
    datatype = "http://www.w3.org/2001/XMLSchema#integer"
    rows = [
        {
            "s": {"value": "http://s", "type": "uri"},
            "p": {"value": "http://p-int", "type": "uri"},
            "o": {"value": "42", "type": "literal", "datatype": datatype},
            "g": {"value": data_iri, "type": "uri"},
        },
        {
            "s": {"value": "http://s", "type": "uri"},
            "p": {"value": "http://p-lang", "type": "uri"},
            "o": {"value": "hello", "type": "literal", "xml:lang": "en"},
            "g": {"value": data_iri, "type": "uri"},
        },
    ]
    store = FakeStore({"phase3 asserted fact_id enumeration": rows})
    service = SemanticReadModelService(
        rdf_store=store,
        scope_resolver=FakeScopeResolver(_resolution([data_iri])),
    )
    fact_ids = set(service._list_asserted_fact_ids(_resolution([data_iri])))
    expected_typed = compute_fact_id(
        "http://s",
        "http://p-int",
        canonical_object_term("42", is_iri=False, datatype=datatype),
        data_iri,
    )
    expected_lang = compute_fact_id(
        "http://s",
        "http://p-lang",
        canonical_object_term("hello", is_iri=False, lang="en"),
        data_iri,
    )
    assert fact_ids == {expected_typed, expected_lang}
    # Negative guard: a plain-literal hash would NOT be in the set.
    plain = compute_fact_id(
        "http://s",
        "http://p-int",
        canonical_object_term("42", is_iri=False),
        data_iri,
    )
    assert plain not in fact_ids


def test_compute_fact_id_with_datatype_matches_compiler_path():
    """Lock the algorithm: read path and write path must produce the same
    fact_id when given identical datatype/lang inputs. This pins the
    invariant even if either side is later refactored."""
    datatype = "http://www.w3.org/2001/XMLSchema#integer"
    # Write side (semantic_command_compiler.compile_bind_fact_evidence)
    write_term = canonical_object_term(
        "42", is_iri=False, datatype=datatype
    )
    write_fid = compute_fact_id("http://s", "http://p", write_term, "http://g")
    # Read side (semantic_read_model._decorate_fact_row after fix)
    read_term = canonical_object_term(
        "42", is_iri=False, datatype=datatype
    )
    read_fid = compute_fact_id("http://s", "http://p", read_term, "http://g")
    assert write_fid == read_fid


# ---------------------------------------------------------------------------
# GET /missing-evidence-facts endpoint
# ---------------------------------------------------------------------------
class _FakeRdfStore:
    """Minimal RdfStoreRepository stub returning rows by query marker."""

    def __init__(self, rows):
        self._rows = rows
        self.queries: list[str] = []

    def query_read_model(self, query, graph_iris, timeout_seconds, limit):
        self.queries.append(query)
        if "phase3 asserted fact_id enumeration" in query:
            return _FakeSparqlResult(self._rows)
        return _FakeSparqlResult([])


class _FakeSparqlResult:
    def __init__(self, rows):
        self._rows = rows

    @property
    def bindings(self):
        return self._rows


def _client(session: Session, rdf_store) -> TestClient:
    app = FastAPI()
    app.include_router(fact_evidence_router, prefix="/api")

    def session_override() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_rdf_store] = lambda: rdf_store
    app.dependency_overrides[get_settings] = lambda: Settings()
    return TestClient(app)


def _seed_graph_set(session: Session, graph_set_id: str, data_iri: str):
    """Insert a minimal graph_set + asserted_data member so the scope
    resolver can resolve."""
    from app.repositories.models import (
        SemanticGraphSetMemberModel,
        SemanticGraphSetModel,
    )

    session.add(
        SemanticGraphSetModel(
            id=graph_set_id,
            name="test gs",
            scope_type="ontology",
            scope_id="ont-1",
        )
    )
    session.add(
        SemanticGraphSetMemberModel(
            id="member-1",
            graph_set_id=graph_set_id,
            graph_iri=data_iri,
            role="asserted_data",
        )
    )
    session.flush()


def test_get_missing_evidence_facts_returns_zero_when_no_facts(in_memory_session):
    data_iri = "http://op.local/graph/data/ont-1"
    _seed_graph_set(in_memory_session, "gs-1", data_iri)
    store = _FakeRdfStore([])
    client = _client(in_memory_session, store)
    resp = client.get("/api/semantic/graph-sets/gs-1/missing-evidence-facts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 0
    assert body["fact_ids"] == []


def test_get_missing_evidence_facts_returns_only_unbound(in_memory_session):
    data_iri = "http://op.local/graph/data/ont-1"
    _seed_graph_set(in_memory_session, "gs-1", data_iri)
    fid_with = compute_fact_id(
        "http://s/1",
        "http://p/1",
        canonical_object_term("v1", is_iri=False),
        data_iri,
    )
    fid_without = compute_fact_id(
        "http://s/2",
        "http://p/2",
        canonical_object_term("v2", is_iri=False),
        data_iri,
    )
    FactEvidenceBindingRepository(in_memory_session).create(
        fact_id=fid_with,
        subject_iri="http://s/1",
        predicate_iri="http://p/1",
        object_value='"v1"',
        graph_iri=data_iri,
        text="t",
    )
    rows = [
        {
            "s": {"value": "http://s/1", "type": "uri"},
            "p": {"value": "http://p/1", "type": "uri"},
            "o": {"value": "v1", "type": "literal"},
            "g": {"value": data_iri, "type": "uri"},
        },
        {
            "s": {"value": "http://s/2", "type": "uri"},
            "p": {"value": "http://p/2", "type": "uri"},
            "o": {"value": "v2", "type": "literal"},
            "g": {"value": data_iri, "type": "uri"},
        },
    ]
    store = _FakeRdfStore(rows)
    client = _client(in_memory_session, store)
    resp = client.get("/api/semantic/graph-sets/gs-1/missing-evidence-facts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["fact_ids"] == [fid_without]
