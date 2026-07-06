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


def _relation_iri(relation_type_id: str) -> str:
    return f"http://op.local/ns/relation-type/{relation_type_id}"


def test_update_relation_type_replaces_label_and_endpoints():
    payload = {
        "ontology_id": "ont-1",
        "relation_type_id": "rel-1",
        "name": "enrolledIn v2",
        "source_class_id": "class-2",
        "target_class_id": "class-3",
    }

    compiled = compile_command("update_relation_type", payload, _settings())

    assert compiled.command_kind == "update_relation_type"
    graph_iri = _ontology_graph_iri("ont-1")
    rel_term = f"<{_relation_iri('rel-1')}>"
    assert (rel_term, _RDFS_LABEL, "?o", graph_iri) in compiled.delta.deletes
    assert (rel_term, _RDFS_LABEL, '"enrolledIn v2"', graph_iri) in compiled.delta.inserts
    domain_pred = "<http://www.w3.org/2000/01/rdf-schema#domain>"
    range_pred = "<http://www.w3.org/2000/01/rdf-schema#range>"
    assert (rel_term, domain_pred, "?o", graph_iri) in compiled.delta.deletes
    assert (rel_term, domain_pred, f"<{_class_iri('class-2')}>", graph_iri) in compiled.delta.inserts
    assert (rel_term, range_pred, "?o", graph_iri) in compiled.delta.deletes
    assert (rel_term, range_pred, f"<{_class_iri('class-3')}>", graph_iri) in compiled.delta.inserts


def test_delete_relation_type_emits_subject_wildcard_deletes():
    payload = {
        "ontology_id": "ont-1",
        "relation_type_id": "rel-1",
    }

    compiled = compile_command("delete_relation_type", payload, _settings())

    assert compiled.command_kind == "delete_relation_type"
    graph_iri = _ontology_graph_iri("ont-1")
    rel_term = f"<{_relation_iri('rel-1')}>"
    assert (rel_term, "?p", "?o", graph_iri) in compiled.delta.deletes


def _shapes_custom_graph_iri(ontology_id: str) -> str:
    return f"http://op.local/graph/shapes/{ontology_id}/custom"


def test_create_shape_writes_node_shape_with_constraint_into_custom_subgraph():
    payload = {
        "ontology_id": "ont-1",
        "target_class_id": "class-1",
        "shape_id": "shape-1",
        "constraints": [
            {"path_id": "prop-1", "min_count": 1},
        ],
    }

    compiled = compile_command("create_shape", payload, _settings())

    assert compiled.command_kind == "create_shape"
    graph_iri = _shapes_custom_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    shape_term = "<http://op.local/ns/shape/shape-1>"
    # sh:NodeShape type.
    assert (shape_term, "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>", "<http://www.w3.org/ns/shacl#NodeShape>", graph_iri) in compiled.delta.inserts
    # sh:targetClass points at the class.
    assert (shape_term, "<http://www.w3.org/ns/shacl#targetClass>", f"<{_class_iri('class-1')}>", graph_iri) in compiled.delta.inserts
    # At least one sh:property triple exists; the PropertyShape carries sh:path and sh:minCount.
    property_links = [q for q in compiled.delta.inserts if q[1] == "<http://www.w3.org/ns/shacl#property>" and q[0] == shape_term]
    assert len(property_links) == 1
    property_term = property_links[0][2]
    constraint_quads = [q for q in compiled.delta.inserts if q[0] == property_term]
    paths = [q[2] for q in constraint_quads if q[1] == "<http://www.w3.org/ns/shacl#path>"]
    assert paths == [f"<{_prop_iri('prop-1')}>"]
    min_counts = [q[2] for q in constraint_quads if q[1] == "<http://www.w3.org/ns/shacl#minCount>"]
    assert min_counts == ['"1"^^<http://www.w3.org/2001/XMLSchema#integer>']


def test_delete_shape_emits_subject_wildcard_deletes_on_custom_subgraph():
    payload = {
        "ontology_id": "ont-1",
        "shape_id": "shape-1",
    }

    compiled = compile_command("delete_shape", payload, _settings())

    assert compiled.command_kind == "delete_shape"
    graph_iri = _shapes_custom_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    shape_term = "<http://op.local/ns/shape/shape-1>"
    assert (shape_term, "?p", "?o", graph_iri) in compiled.delta.deletes


def test_update_shape_replaces_constraints_via_delete_then_insert():
    payload = {
        "ontology_id": "ont-1",
        "shape_id": "shape-1",
        "target_class_id": "class-1",
        "constraints": [
            {"path_id": "prop-2", "max_count": 1},
        ],
    }

    compiled = compile_command("update_shape", payload, _settings())

    assert compiled.command_kind == "update_shape"
    graph_iri = _shapes_custom_graph_iri("ont-1")
    shape_term = "<http://op.local/ns/shape/shape-1>"
    # Existing shape is wildcarded out.
    assert (shape_term, "?p", "?o", graph_iri) in compiled.delta.deletes
    # New NodeShape + constraint are inserted.
    assert (shape_term, "<http://www.w3.org/ns/shacl#targetClass>", f"<{_class_iri('class-1')}>", graph_iri) in compiled.delta.inserts
    property_links = [q for q in compiled.delta.inserts if q[1] == "<http://www.w3.org/ns/shacl#property>" and q[0] == shape_term]
    assert len(property_links) == 1

