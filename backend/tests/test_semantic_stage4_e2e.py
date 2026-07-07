"""Stage 4 spec §11 happy-path coverage at the service layer.

Mirrors the Stage 3 e2e pattern: each test exercises the
``SemanticReadModelService.read_model`` dispatcher directly (no HTTP) for
speed.

Tests:

* ``test_read_model_entity_search`` — spec §11 step 2 (Search entity by query
  returns the Acme Corp row with the ``[asserted]`` chip).
* ``test_read_model_agent_test_context`` — spec §11 step 5 prelude (the
  agent-test-context read model returns the Acme Corp entry for the keyword
  "acme"). AgentTestService itself is covered by Phase B (Task B2); this test
  only exercises the read model.
* ``test_read_model_owl_consistency_summary`` — spec §11 step 8 (the OWL
  Consistency summary returns ``consistent: True`` and ``is_stale: False``
  for the freshly seeded reasoning run).
* ``test_fact_audit_queue_evidence_bindings`` — spec §11 step 7 (the fact
  drawer returns the bound chunk via the ``field_set="evidence"`` composer).
"""
from __future__ import annotations

# Load the Stage 4 fixtures.
pytest_plugins = ("conftest_stage4",)

from app.repositories.models import SemanticEditAuditModel

from conftest_stage4 import (
    ACME_CLASS,
    ACME_CLASS_LABEL,
    ACME_COMMENT,
    ACME_ENTITY,
    ACME_LABEL,
    CHUNK_IRI,
    CHUNK_TEXT,
    DOC_IRI,
    EVIDENCE_DATA_GRAPH,
    EVIDENCE_ONTOLOGY_GRAPH,
)


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
# Step 5 prelude — agent-test-context
# ---------------------------------------------------------------------------


def test_read_model_agent_test_context(fake_graph_set_with_evidence):
    svc, graph_set_id = fake_graph_set_with_evidence
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="agent-test-context",
        q="acme",
        limit=15,
    )
    assert envelope["model_name"] == "agent-test-context"
    items = envelope["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["iri"] == ACME_ENTITY
    assert entry["label"] == ACME_LABEL
    assert entry["class_label"] == ACME_CLASS_LABEL
    assert entry["source_graph_iri"] == EVIDENCE_DATA_GRAPH
    # The agent field_set does NOT carry comment in the projection.
    assert "comment" not in entry


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
    composer attaches ``evidence_bindings`` to each asserted fact row,
    populated from the ``prov:wasDerivedFrom`` SPARQL lookup."""
    svc, graph_set_id = fake_graph_set_with_evidence

    # Seed an asserted fact row that the queue can pick up. We use the
    # existing fact-audit-queue template body which selects (subject,
    # predicate, object) triples from the asserted_data graph. Since the
    # Stage 4 FakeStore's ``query_read_model`` only answers entity-search
    # and binding queries, we fall back to the Stage 3-style fixture by
    # seeding an asserted_data triple and using a regular FakeStore-shape
    # query for the queue body. The Stage 4 FakeStore returns [] for the
    # queue body, so the items list is empty and we cannot iterate rows.
    #
    # Instead, this test exercises the new composer path directly: call
    # ``_compose_fact_audit_queue`` with kind="asserted" and
    # field_set="evidence" so the evidence_bindings projection fires on
    # an empty row set, asserting that the composer does not crash and
    # that the evidence SPARQL was issued.
    items, warnings = svc._compose_fact_audit_queue(
        scope=svc.scope_resolver.resolve(graph_set_id, include="asserted"),
        kind="asserted",
        field_set="evidence",
    )
    # The Stage 4 FakeStore returns [] for the fact-audit-queue body
    # (it only knows entity-search + binding queries), so items is empty.
    # The test asserts the composer runs the evidence lookup SPARQL
    # against the store, proving the field_set branch fired.
    assert isinstance(items, list)
    # The last query the store saw should mention prov:wasDerivedFrom.
    last_query = svc.rdf_store.queries[-1] if svc.rdf_store.queries else ""
    assert "prov:wasDerivedFrom" in last_query or "wasDerivedFrom" in last_query


def test_fact_audit_queue_evidence_bindings_with_seed(
    in_memory_session, fake_graph_set_with_evidence, monkeypatch
):
    """When the fact-audit-queue body returns rows AND the evidence
    field_set is requested, each row carries a populated
    ``evidence_bindings`` list drawn from the prov:wasDerivedFrom lookup."""
    svc, graph_set_id = fake_graph_set_with_evidence

    # Monkeypatch _fetch_fact_rows to return a single asserted fact row
    # whose subject is the Acme entity (the binding fixture is keyed
    # against any fact IRI in the Stage 4 FakeStore).
    fake_row = {
        "subject": {"value": ACME_ENTITY, "type": "uri"},
        "subject_label": {"value": ACME_LABEL, "type": "literal"},
        "predicate": {"value": "http://example.org/p", "type": "uri"},
        "predicate_label": {"value": "p", "type": "literal"},
        "object": {"value": "Acme Corp", "type": "literal"},
        "object_label": {"value": "Acme Corp", "type": "literal"},
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
    assert b["chunk_iri"] == CHUNK_IRI
    assert b["document_iri"] == DOC_IRI
    assert b["sequence"] == 0
    assert b["text_preview"] == CHUNK_TEXT
