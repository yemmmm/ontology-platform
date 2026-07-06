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

