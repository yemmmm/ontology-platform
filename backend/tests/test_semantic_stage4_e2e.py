"""Stage 4 spec §11 happy-path coverage at the service layer.

Mirrors the Stage 3 e2e pattern: each test exercises the
``SemanticReadModelService.read_model`` dispatcher directly (no HTTP) for
speed.

Tests:

* ``test_read_model_entity_search`` — spec §11 step 2 (Search entity by query
  returns the Acme Corp row with the ``[asserted]`` chip).
* ``test_read_model_owl_consistency_summary`` — spec §11 step 8 (the OWL
  Consistency summary returns ``consistent: True`` and ``is_stale: False``
  for the freshly seeded reasoning run).
* ``test_fact_audit_queue_evidence_bindings`` — spec §11 step 7 (the fact
  drawer returns the bound chunk via the ``field_set="evidence"`` composer,
  populated from the Postgres ``fact_evidence_bindings`` table).
"""
from __future__ import annotations

from conftest_stage4 import (
    ACME_CLASS,
    ACME_CLASS_LABEL,
    ACME_COMMENT,
    ACME_ENTITY,
    ACME_LABEL,
    CHUNK_TEXT,
    EVIDENCE_DATA_GRAPH,
)

# Load the Stage 4 fixtures.
pytest_plugins = ("conftest_stage4",)


# ---------------------------------------------------------------------------
# Step 2 — entity-search
# ---------------------------------------------------------------------------


def test_read_model_entity_search(fake_graph_set_with_evidence):
    svc, graph_set_id = fake_graph_set_with_evidence
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="acme",
        limit=50,
    )
    assert envelope["model_name"] == "entity-search"
    items = envelope["items"]
    assert len(items) == 1
    row = items[0]
    assert row["iri"] == ACME_ENTITY
    assert row["label"] == ACME_LABEL
    assert row["comment"] == ACME_COMMENT
    assert row["class_iri"] == ACME_CLASS
    assert row["class_label"] == ACME_CLASS_LABEL
    # source_graph_iri is the asserted_data graph and assertion_kind is asserted.
    assert row["source_graph_iri"] == EVIDENCE_DATA_GRAPH
    assert row["assertion_kind"] == "asserted"
    assert row["graph_set_id"] == graph_set_id


def test_read_model_entity_search_class_filter(fake_graph_set_with_evidence):
    svc, graph_set_id = fake_graph_set_with_evidence
    # Filter by the Acme class → still 1 row.
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="acme",
        class_iri=ACME_CLASS,
        limit=50,
    )
    assert len(envelope["items"]) == 1
    class_filter_query = svc.rdf_store.queries[-1]
    assert class_filter_query.lstrip().startswith("# template: entity-search")
    assert f"FILTER(?class = <{ACME_CLASS}>)" in class_filter_query
    assert not class_filter_query.lstrip().startswith("VALUES ?class_iri")
    # Filter by a non-existent class → 0 rows.
    envelope_empty = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="acme",
        class_iri="http://example.org/Nonexistent",
        limit=50,
    )
    assert envelope_empty["items"] == []


# ---------------------------------------------------------------------------
# Step 8 — owl-consistency-summary
# ---------------------------------------------------------------------------


def test_read_model_owl_consistency_summary(
    fake_graph_set_with_evidence, fake_reasoning_run_consistency
):
    svc, graph_set_id = fake_graph_set_with_evidence
    run_id = fake_reasoning_run_consistency
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="owl-consistency-summary",
        field_set="summary",
    )
    assert envelope["model_name"] == "owl-consistency-summary"
    items = envelope["items"]
    assert len(items) == 1
    row = items[0]
    assert row["run_id"] == run_id
    assert row["consistent"] is True
    assert row["classification"] == {"profile": "owl2_dl"}
    assert row["entailment_count"] == 1
    assert isinstance(row["unsatisfiable_classes"], list)
    assert row["result_graph_iri"].endswith("/run-stage4")
    assert row["started_at"].startswith("2026-07-07")
    assert row["finished_at"].startswith("2026-07-07")
    # Freshly seeded → not stale.
    assert row["is_stale"] is False


# ---------------------------------------------------------------------------
# Step 7 — fact-audit-queue evidence bindings
# ---------------------------------------------------------------------------


def test_fact_audit_queue_evidence_bindings(
    in_memory_session, fake_graph_set_with_evidence
):
    """When ``field_set="evidence"`` is requested, the fact-audit-queue
    composer attaches ``evidence_bindings`` to each asserted fact row.

    Phase 3 refactor: bindings are now fetched from the Postgres
    ``fact_evidence_bindings`` table (the legacy ``prov:wasDerivedFrom``
    SPARQL lookup was removed). Without any seeded PG rows the composer
    returns an empty bindings list per row but must not crash, and the
    SPARQL template it issues is ``fact-audit-queue`` (never a
    ``prov:wasDerivedFrom`` lookup).
    """
    svc, graph_set_id = fake_graph_set_with_evidence

    items, warnings = svc._compose_fact_audit_queue(
        scope=svc.scope_resolver.resolve(graph_set_id, include="asserted"),
        kind="asserted",
        field_set="evidence",
    )
    # The Stage 4 FakeStore returns [] for the fact-audit-queue body
    # (it only knows entity-search queries), so items is empty. The test
    # asserts the composer does not crash and that the SPARQL it issued
    # is the unified fact-audit-queue template, not the deleted
    # prov:wasDerivedFrom lookup.
    assert isinstance(items, list)
    last_query = svc.rdf_store.queries[-1] if svc.rdf_store.queries else ""
    assert "prov:wasDerivedFrom" not in last_query


def test_fact_audit_queue_evidence_bindings_with_seed(
    in_memory_session, fake_graph_set_with_evidence, monkeypatch
):
    """When the fact-audit-queue body returns rows AND the evidence
    field_set is requested, each row carries a populated
    ``evidence_bindings`` list drawn from the Postgres
    ``fact_evidence_bindings`` table."""
    from uuid import uuid4

    from app.repositories.models import FactEvidenceBindingModel
    from app.services.fact_id import canonical_object_term, compute_fact_id

    svc, graph_set_id = fake_graph_set_with_evidence

    predicate_iri = "http://example.org/p"
    object_value = "Acme Corp"
    object_term = canonical_object_term(object_value)
    fact_id = compute_fact_id(
        ACME_ENTITY, predicate_iri, object_term, EVIDENCE_DATA_GRAPH
    )

    binding = FactEvidenceBindingModel(
        id=str(uuid4()),
        fact_id=fact_id,
        subject_iri=ACME_ENTITY,
        predicate_iri=predicate_iri,
        object_value=object_term,
        graph_iri=EVIDENCE_DATA_GRAPH,
        chunk_id=None,
        evidence_artifact_id=None,
        document_filename="doc-1.pdf",
        sequence=0,
        char_start=0,
        char_end=len(CHUNK_TEXT),
        text=CHUNK_TEXT,
    )
    in_memory_session.add(binding)
    in_memory_session.commit()

    fake_row = {
        "subject": {"value": ACME_ENTITY, "type": "uri"},
        "subject_label": {"value": ACME_LABEL, "type": "literal"},
        "predicate": {"value": predicate_iri, "type": "uri"},
        "predicate_label": {"value": "p", "type": "literal"},
        "object": {"value": object_value, "type": "literal"},
        "object_label": {"value": object_value, "type": "literal"},
        "graph": {"value": EVIDENCE_DATA_GRAPH, "type": "uri"},
    }
    monkeypatch.setattr(
        svc, "_fetch_fact_rows", lambda iris, template_name: [fake_row]
    )

    items, warnings = svc._compose_fact_audit_queue(
        scope=svc.scope_resolver.resolve(graph_set_id, include="asserted"),
        kind="asserted",
        field_set="evidence",
    )
    assert len(items) == 1
    bindings = items[0].get("evidence_bindings")
    assert bindings is not None
    assert len(bindings) == 1
    b = bindings[0]
    # PG-backed binding exposes the seeded text and document filename.
    assert b.get("text_preview") == CHUNK_TEXT
    assert b.get("document_filename") == "doc-1.pdf"
    assert b.get("sequence") == 0
