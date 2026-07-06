"""Stage 2 canonical-write compiler tests.

Spec §3.3.1 lists the new kinds Stage 2 introduces. Each kind is tested
in isolation against the pure compile_* functions; the canonical-write
service's I/O behavior (apply, audit, SHACL pre-check) is exercised in
test_semantic_canonical_write.py.
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.semantic_command_compiler import compile_command


_RDFS_LABEL = "<http://www.w3.org/2000/01/rdf-schema#label>"
_RDFS_COMMENT = "<http://www.w3.org/2000/01/rdf-schema#comment>"


def _settings():
    return Settings(
        semantic_base_iri="http://op.local/ns/",
        semantic_graph_iri_prefix="http://op.local/graph/",
    )


def _ontology_graph_iri(ontology_id: str) -> str:
    return f"http://op.local/graph/ontology/{ontology_id}"


def _class_iri(class_id: str) -> str:
    return f"http://op.local/ns/class/{class_id}"


def test_update_class_replaces_label_only():
    """Updating a class name produces a delta that deletes any existing
    rdfs:label and inserts the new one. Other predicates are untouched."""
    payload = {
        "ontology_id": "ont-1",
        "class_id": "class-1",
        "name": "Student v2",
    }

    compiled = compile_command("update_class", payload, _settings())

    assert compiled.command_kind == "update_class"
    assert compiled.object_kind == "class"
    assert compiled.source_ids == ["class-1"]
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    class_term = f"<{_class_iri('class-1')}>"
    expected_delete = (class_term, _RDFS_LABEL, "?o", graph_iri)
    assert expected_delete in compiled.delta.deletes
    expected_insert = (
        class_term,
        _RDFS_LABEL,
        '"Student v2"',
        graph_iri,
    )
    assert expected_insert in compiled.delta.inserts


def test_delete_class_emits_subject_wildcard_deletes():
    """delete_class removes every triple whose subject is the class IRI,
    plus marks the class as deprecated via op:deprecated true (soft delete)."""
    payload = {
        "ontology_id": "ont-1",
        "class_id": "class-1",
    }

    compiled = compile_command("delete_class", payload, _settings())

    assert compiled.command_kind == "delete_class"
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    class_term = f"<{_class_iri('class-1')}>"
    # Every predicate/object combo for this subject is removed.
    assert (class_term, "?p", "?o", graph_iri) in compiled.delta.deletes
    # Soft-delete marker is inserted.
    op_deprecated = "<http://op.local/ns/vocab/deprecated>"
    assert (class_term, op_deprecated, '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>', graph_iri) in compiled.delta.inserts


def test_create_property_writes_owl_datatype_property_with_domain_and_range():
    payload = {
        "ontology_id": "ont-1",
        "class_id": "class-1",
        "property_id": "prop-1",
        "name": "email",
        "description": "Student email",
        "datatype": "xsd:string",
    }

    compiled = compile_command("create_property", payload, _settings())

    assert compiled.command_kind == "create_property"
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    prop_term = f"<http://op.local/ns/property/prop-1>"
    class_term = f"<{_class_iri('class-1')}>"
    # Type owl:DatatypeProperty inferred from datatype field.
    assert (prop_term, "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>", "<http://www.w3.org/2002/07/owl#DatatypeProperty>", graph_iri) in compiled.delta.inserts
    # Domain and range set.
    assert (prop_term, "<http://www.w3.org/2000/01/rdf-schema#domain>", class_term, graph_iri) in compiled.delta.inserts
    assert (prop_term, "<http://www.w3.org/2000/01/rdf-schema#range>", "<http://www.w3.org/2001/XMLSchema#string>", graph_iri) in compiled.delta.inserts
    # Label and description set.
    assert (prop_term, "<http://www.w3.org/2000/01/rdf-schema#label>", '"email"', graph_iri) in compiled.delta.inserts
    assert (prop_term, "<http://www.w3.org/2000/01/rdf-schema#comment>", '"Student email"', graph_iri) in compiled.delta.inserts


def _prop_iri(property_id: str) -> str:
    return f"http://op.local/ns/property/{property_id}"


def test_update_property_replaces_label_and_range():
    payload = {
        "ontology_id": "ont-1",
        "property_id": "prop-1",
        "name": "email v2",
        "datatype": "xsd:integer",
    }

    compiled = compile_command("update_property", payload, _settings())

    assert compiled.command_kind == "update_property"
    graph_iri = _ontology_graph_iri("ont-1")
    prop_term = f"<{_prop_iri('prop-1')}>"
    assert (prop_term, _RDFS_LABEL, "?o", graph_iri) in compiled.delta.deletes
    assert (prop_term, _RDFS_LABEL, '"email v2"', graph_iri) in compiled.delta.inserts
    # Range delete-and-replace.
    range_pred = "<http://www.w3.org/2000/01/rdf-schema#range>"
    assert (prop_term, range_pred, "?o", graph_iri) in compiled.delta.deletes
    assert (prop_term, range_pred, "<http://www.w3.org/2001/XMLSchema#integer>", graph_iri) in compiled.delta.inserts


def test_delete_property_emits_subject_wildcard_deletes():
    payload = {
        "ontology_id": "ont-1",
        "property_id": "prop-1",
    }

    compiled = compile_command("delete_property", payload, _settings())

    assert compiled.command_kind == "delete_property"
    graph_iri = _ontology_graph_iri("ont-1")
    prop_term = f"<{_prop_iri('prop-1')}>"
    assert (prop_term, "?p", "?o", graph_iri) in compiled.delta.deletes

