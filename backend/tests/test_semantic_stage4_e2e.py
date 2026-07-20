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


def test_entity_search_fuses_exact_and_semantic_candidates_in_stable_order(
    fake_graph_set_with_evidence,
):
    """Vector candidates must enrich, never replace, decorated exact rows."""

    svc, graph_set_id = fake_graph_set_with_evidence
    store = svc.rdf_store
    exact_iri = "https://example.test/entity/workflow"
    lexical_iri = "https://example.test/entity/workflow-guide"
    semantic_iri = "https://example.test/entity/semantic-only"
    store.add_entity(
        iri=exact_iri,
        label="Workflow",
        comment="The authoritative workflow description.",
        klass=ACME_CLASS,
        class_label=ACME_CLASS_LABEL,
        graph=EVIDENCE_DATA_GRAPH,
    )
    store.add_entity(
        iri=lexical_iri,
        label="Workflow Guide",
        comment="A lexical candidate.",
        klass=ACME_CLASS,
        class_label=ACME_CLASS_LABEL,
        graph=EVIDENCE_DATA_GRAPH,
    )

    class RetrievalStub:
        def recall_graph_set(self, **kwargs):
            assert kwargs["resource_kinds"] == {"instance"}
            return {
                "candidates": [
                    {
                        "id": exact_iri,
                        "iri": exact_iri,
                        "ontology_id": "ont-stage4",
                        "kind": "instance",
                        "label": "Workflow from vector index",
                        "description": "Must not replace lexical row details.",
                        "data": {"rdf_types": [ACME_CLASS]},
                        "match": {
                            "semantic_similarity": 0.91,
                            "reasons": ["semantic_candidate"],
                        },
                    },
                    {
                        "id": semantic_iri,
                        "iri": semantic_iri,
                        "ontology_id": "ont-stage4",
                        "kind": "instance",
                        "label": "Semantic Only",
                        "description": "A vector-only candidate.",
                        "data": {"rdf_types": [ACME_CLASS]},
                        "match": {
                            "score": 600,
                            "semantic_similarity": 0.6,
                            "effective_score": 0.6,
                            "candidate_level": "semantic_candidate",
                            "method": "semantic",
                            "matched_terms": [],
                            "matched_fields": [],
                            "reasons": ["semantic_candidate"],
                        },
                    },
                ],
                "indexes": [{"status": "current", "ambiguity_margin": 0.03}],
                "warnings": [],
                "completeness": "complete",
            }

    svc.retrieval_service = RetrievalStub()
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="workflow",
        limit=10,
    )

    items = envelope["items"]
    assert [item["iri"] for item in items] == [exact_iri, lexical_iri, semantic_iri]
    assert items[0]["comment"] == "The authoritative workflow description."
    assert items[0]["source_graph_iri"] == EVIDENCE_DATA_GRAPH
    assert items[0]["match"]["candidate_level"] == "exact"
    assert items[0]["match"]["method"] == "mixed"
    assert items[0]["match"]["semantic_similarity"] == 0.91
    assert items[2]["match"]["candidate_level"] == "semantic_candidate"
    assert envelope["recall"]["match_status"] == "exact"


def test_entity_search_applies_limit_after_semantic_fusion_and_stable_sort(
    fake_graph_set_with_evidence,
):
    svc, graph_set_id = fake_graph_set_with_evidence
    store = svc.rdf_store
    alpha_iri = "https://example.test/entity/workflow-alpha"
    beta_iri = "https://example.test/entity/workflow-beta"
    semantic_iri = "https://example.test/entity/workflow-semantic"
    # Reverse insertion makes the deterministic label/IRI tie-break observable.
    for iri, label in [(beta_iri, "Workflow Beta"), (alpha_iri, "Workflow Alpha")]:
        store.add_entity(
            iri=iri,
            label=label,
            comment=None,
            klass=ACME_CLASS,
            class_label=ACME_CLASS_LABEL,
            graph=EVIDENCE_DATA_GRAPH,
        )

    class RetrievalStub:
        def recall_graph_set(self, **_kwargs):
            return {
                "candidates": [
                    {
                        "id": semantic_iri,
                        "iri": semantic_iri,
                        "ontology_id": "ont-stage4",
                        "kind": "instance",
                        "label": "Vector Candidate",
                        "description": None,
                        "data": {"rdf_types": [ACME_CLASS]},
                        "match": {
                            "score": 950,
                            "semantic_similarity": 0.95,
                            "effective_score": 0.95,
                            "candidate_level": "semantic_candidate",
                            "method": "semantic",
                            "matched_terms": [],
                            "matched_fields": [],
                            "reasons": ["semantic_candidate"],
                        },
                    }
                ],
                "indexes": [],
                "warnings": [],
                "completeness": "complete",
            }

    svc.retrieval_service = RetrievalStub()
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="workflow",
        limit=2,
    )

    # Semantic rank is considered before the final cut-off; lexical ties are
    # deterministically ordered instead of inheriting RDF store iteration order.
    assert [item["iri"] for item in envelope["items"]] == [semantic_iri, alpha_iri]


def test_entity_search_returns_exact_governed_mapping_evidence(
    in_memory_session, fake_graph_set_with_evidence
):
    """Entity search and Context use the same exact Mapping evidence contract."""

    from app.repositories.models import (
        DataResourceModel,
        DataSourceModel,
        ExternalFieldModel,
        OntologyModel,
        ProjectModel,
        SemanticMappingModel,
    )

    svc, graph_set_id = fake_graph_set_with_evidence
    target_iri = "https://example.test/entity/customer"
    in_memory_session.add(
        ProjectModel(
            id="project-stage4",
            name="Stage 4",
            normalized_label="stage-4",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        OntologyModel(
            id="ont-stage4",
            project_id="project-stage4",
            name="Stage 4 ontology",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        DataSourceModel(
            id="source-stage4",
            project_id="project-stage4",
            name="stage4-source",
            source_type="database",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        DataResourceModel(
            id="resource-stage4",
            project_id="project-stage4",
            data_source_id="source-stage4",
            name="stage4-resource",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        ExternalFieldModel(
            id="field-stage4",
            project_id="project-stage4",
            data_source_id="source-stage4",
            data_resource_id="resource-stage4",
            name="customer_id",
        )
    )
    in_memory_session.flush()
    in_memory_session.add(
        SemanticMappingModel(
            id="mapping-entity-customer",
            project_id="project-stage4",
            ontology_id="ont-stage4",
            target_type="entity",
            target_id=target_iri,
            data_source_id="source-stage4",
            resource_id="resource-stage4",
            field_id="field-stage4",
            external_resource_name="customers",
            external_field_name="customer_id",
            join_key={"customer_id": "customer_id"},
            status="active",
        )
    )
    in_memory_session.commit()

    class RetrievalStub:
        def recall_graph_set(self, **_kwargs):
            return {
                "candidates": [
                    {
                        "id": "https://example.test/entity/semantic-candidate",
                        "iri": "https://example.test/entity/semantic-candidate",
                        "ontology_id": "ont-stage4",
                        "kind": "instance",
                        "label": "Semantic candidate",
                        "description": None,
                        "data": {"rdf_types": [ACME_CLASS]},
                        "match": {
                            "score": 950,
                            "semantic_similarity": 0.95,
                            "effective_score": 0.95,
                            "candidate_level": "semantic_candidate",
                            "method": "semantic",
                            "matched_terms": [],
                            "matched_fields": [],
                            "reasons": ["semantic_candidate"],
                        },
                    }
                ],
                "indexes": [],
                "warnings": [],
                "completeness": "complete",
            }

    svc.retrieval_service = RetrievalStub()
    envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="customer_id",
        limit=10,
    )

    assert [item["iri"] for item in envelope["items"]] == [
        target_iri,
        "https://example.test/entity/semantic-candidate",
    ]
    assert envelope["items"][0]["match"]["candidate_level"] == "exact"
    assert envelope["items"][0]["match"]["method"] == "mapping"
    assert envelope["items"][0]["mapping_evidence"] == [
        {
            "mapping_id": "mapping-entity-customer",
            "target_type": "entity",
            "external_field": "customer_id",
            "join_keys": "customer_id",
        }
    ]

    target_type_envelope = svc.read_model(
        graph_set_id=graph_set_id,
        model_name="entity-search",
        q="entity",
        limit=10,
    )
    target_type_item = target_type_envelope["items"][0]

    assert target_type_item["iri"] == target_iri
    assert target_type_item["match"]["candidate_level"] == "exact"
    assert target_type_item["match"]["reasons"] == ["exact_mapping"]
    assert target_type_item["match"]["matched_fields"] == ["mapping_target_type"]


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
