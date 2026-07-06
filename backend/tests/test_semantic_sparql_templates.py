import pytest

from app.services.semantic_sparql_templates import get_template, list_templates


def test_graph_set_staleness_template_registered():
    template = get_template("graph-set-staleness")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology", "asserted_data")
    assert template.needs_reasoning is True
    assert template.needs_rules is True
    assert template.default_limit == 1
    assert "missing-evidence" in template.body


def test_list_templates_includes_graph_set_staleness():
    names = {t.name for t in list_templates()}
    assert "graph-set-staleness" in names


# Stage 2 §3.2 templates ---------------------------------------------------

def test_class_topology_template_registered():
    template = get_template("class-topology")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology",)
    assert template.needs_reasoning is False
    assert template.needs_rules is False
    assert "owl:Class" in template.body or "rdfs:Class" in template.body


def test_property_list_template_registered():
    template = get_template("property-list")
    assert template.required_roles == ("asserted_ontology",)
    assert "rdfs:domain" in template.body


def test_relation_type_list_template_registered():
    template = get_template("relation-type-list")
    assert template.required_roles == ("asserted_ontology",)
    assert "owl:ObjectProperty" in template.body


def test_class_shape_generated_template_targets_generated_subgraph():
    template = get_template("class-shape-generated")
    assert template.required_roles == ("shape_graph_generated",)
    assert "sh:" in template.body or "shacl" in template.body


def test_class_shape_custom_template_targets_custom_subgraph():
    template = get_template("class-shape-custom")
    assert template.required_roles == ("shape_graph_custom",)
    assert "sh:" in template.body or "shacl" in template.body


# Stage 2 §5.3 — EntitiesPage read-model templates ---------------------------------------


def test_entity_list_template_registered():
    template = get_template("entity-list")
    assert template.projection_version == "semantic-read-v1"
    # entity-list reads from asserted_data and optionally decorates with derived.
    assert "asserted_data" in template.required_roles
    assert "owl:NamedIndividual" in template.body or "NamedIndividual" in template.body
    # Should project the class IRI so the frontend can group by class.
    assert "?class" in template.body


def test_entity_relations_template_registered():
    template = get_template("entity-relations")
    assert template.projection_version == "semantic-read-v1"
    # entity-relations needs derived graphs to surface inferred / rule-derived edges.
    assert template.needs_reasoning is True or template.needs_rules is True
    assert "?source" in template.body
    assert "?target" in template.body
    assert "?relation" in template.body or "?predicate" in template.body


def test_entity_shape_template_registered_as_composer():
    template = get_template("entity-shape")
    assert template.projection_version == "semantic-read-v1"
    # entity-shape delegates to class-shape-merged; the composer branch in
    # SemanticReadModelService detects this name and short-circuits to the
    # shape endpoint service. Required roles mirror class-shape-merged.
    assert "asserted_ontology" in template.required_roles
    # Body is a marker — the composer does not run this SPARQL directly.
    assert "composer" in template.body.lower() or "delegates" in template.body.lower()


# Stage 2 §7.3 — Catalog mapping templates -----------------------------------------------


def test_mapping_list_template_registered():
    template = get_template("mapping-list")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology",)
    assert template.needs_reasoning is False
    assert template.needs_rules is False
    # SPARQL must look for op:SemanticMapping instances.
    assert "SemanticMapping" in template.body


def test_import_graph_mappings_template_registered():
    template = get_template("import-graph-mappings")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("import_graph",)
    assert template.needs_reasoning is False
    assert template.needs_rules is False
    assert "SemanticMapping" in template.body


# Stage 2 §6.3 — FactAuditPage read-model templates --------------------------------------


def test_fact_audit_queue_template_registered_as_composer():
    """fact-audit-queue is a composer; the SemanticReadModelService branch
    selects source graphs by ``?kind=`` query parameter and decorates each
    row into a unified FactRow."""
    template = get_template("fact-audit-queue")
    assert template.projection_version == "semantic-read-v1"
    # Sources span asserted + reasoning + rule derived.
    assert "asserted_data" in template.required_roles
    # Body is a marker — composer does not run it directly.
    assert "composer" in template.body.lower()


def test_fact_audit_queue_template_needs_reasoning_and_rules():
    """fact-audit-queue needs derived graphs to surface inferred and
    rule-derived facts."""
    template = get_template("fact-audit-queue")
    assert template.needs_reasoning is True
    assert template.needs_rules is True


def test_missing_evidence_list_template_registered():
    """missing-evidence-list is a lightweight template that aggregates
    missing-evidence triples across the graph-set members."""
    template = get_template("missing-evidence-list")
    assert template.projection_version == "semantic-read-v1"
    assert "asserted_data" in template.required_roles
    assert template.needs_reasoning is False
    assert template.needs_rules is False
    # Template body must filter on op:evidenceStatus "missing_evidence".
    assert "missing_evidence" in template.body
    assert "evidenceStatus" in template.body
    # Must project the triple so the composer can decorate rows.
    assert "?subject" in template.body
    assert "?predicate" in template.body
    assert "?object" in template.body

