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
