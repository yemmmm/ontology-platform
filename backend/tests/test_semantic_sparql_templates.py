from app.services.semantic_sparql_templates import get_template, list_templates


def test_generic_entity_queries_do_not_bypass_mapping_reference_authorization():
    from rdflib import Dataset, Literal, URIRef
    from rdflib.namespace import RDF, RDFS, OWL
    from app.services.semantic_read_model import SemanticReadModelService

    dataset = Dataset()
    graph_iri = "https://r4010.test/ontology"
    graph = dataset.graph(URIRef(graph_iri))
    ordinary = URIRef("https://r4010.test/entity/ordinary")
    graph.add((ordinary, RDF.type, OWL.NamedIndividual))
    graph.add((ordinary, RDFS.label, Literal("ordinary")))
    id_predicate = URIRef("http://ontology-platform.local/semantic/vocab/id")
    graph.add((ordinary, id_predicate, Literal("ordinary")))
    for kind in ("TableMapping", "JoinMapping", "EnumValueMeaning", "MetricDefinition"):
        resource = URIRef("https://r4010.test/mapping/" + kind)
        graph.add((resource, RDF.type, OWL.NamedIndividual))
        graph.add(
            (resource, RDF.type, URIRef("http://ontology-platform.local/semantic/vocab/" + kind))
        )
        graph.add((resource, RDFS.label, Literal(kind)))
        graph.add((resource, id_predicate, Literal(kind)))
    for name in ("entity-detail", "entity-list"):
        query = SemanticReadModelService._compile_template_query(
            get_template(name), [graph_iri], 100
        )
        assert {str(row.entity) for row in dataset.query(query)} == {str(ordinary)}


def test_graph_set_staleness_template_registered():
    template = get_template("graph-set-staleness")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology", "asserted_data")
    assert template.needs_reasoning is True
    assert not hasattr(template, "needs_rules")
    assert template.default_limit == 1
    assert "missing-evidence" not in template.body


def test_list_templates_includes_graph_set_staleness():
    names = {t.name for t in list_templates()}
    assert "graph-set-staleness" in names


# Stage 2 §3.2 templates ---------------------------------------------------


def test_class_topology_template_registered():
    template = get_template("class-topology")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology",)
    assert template.needs_reasoning is False
    assert not hasattr(template, "needs_rules")
    assert "owl:Class" in template.body or "rdfs:Class" in template.body


def test_property_list_template_registered():
    template = get_template("property-list")
    assert template.required_roles == ("asserted_ontology",)
    assert "rdfs:domain" in template.body


def test_relation_type_list_template_registered():
    template = get_template("relation-type-list")
    assert template.required_roles == ("asserted_ontology",)
    assert "owl:ObjectProperty" in template.body


# Stage 2 §5.3 — EntitiesPage read-model templates ---------------------------------------


def test_entity_list_template_registered():
    template = get_template("entity-list")
    assert template.projection_version == "semantic-read-v2"
    assert "semantic_definition" in template.detail_variables
    # entity-list reads from asserted_data and optionally decorates with derived.
    assert "asserted_data" in template.required_roles
    assert template.needs_reasoning is True
    assert not hasattr(template, "needs_rules")
    assert "owl:NamedIndividual" in template.body or "NamedIndividual" in template.body
    # Should project the class IRI so the frontend can group by class.
    assert "?class" in template.body
    # Derived result graphs do not need to repeat the entity identity triple;
    # the query anchors identity in any scoped graph.
    assert "VALUES ?ig" in template.body


def test_entity_relations_template_registered():
    template = get_template("entity-relations")
    assert template.projection_version == "semantic-read-v1"
    # entity-relations needs derived graphs to surface inferred / rule-derived edges.
    assert template.needs_reasoning is True
    assert "?source" in template.body
    assert "?target" in template.body
    assert "?relation" in template.body or "?predicate" in template.body
    assert "VALUES ?sg" in template.body
    assert "VALUES ?tg" in template.body


def test_entity_literal_facts_template_registered():
    template = get_template("entity-literal-facts")
    assert template.projection_version == "semantic-read-v1"
    assert template.needs_reasoning is True
    assert not hasattr(template, "needs_rules")
    assert "VALUES ?subject" in template.body
    assert "isLiteral(?object)" in template.body
    assert "{entity_iri}" in template.body


# Stage 2 §7.3 — Catalog mapping templates -----------------------------------------------


def test_mapping_list_template_registered():
    template = get_template("mapping-list")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("asserted_ontology",)
    assert template.needs_reasoning is False
    assert not hasattr(template, "needs_rules")
    # SPARQL must look for op:SemanticMapping instances.
    assert "SemanticMapping" in template.body


def test_import_graph_mappings_template_registered():
    template = get_template("import-graph-mappings")
    assert template.projection_version == "semantic-read-v1"
    assert template.required_roles == ("import_graph",)
    assert template.needs_reasoning is False
    assert not hasattr(template, "needs_rules")
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
    assert not hasattr(template, "needs_rules")


def test_rule_derived_fact_template_is_retired():
    import pytest
    with pytest.raises(KeyError):
        get_template("fact-audit-queue-with-types")
