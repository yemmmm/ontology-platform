"""Stage 2 canonical-write compiler tests.

Spec §3.3.1 lists the new kinds Stage 2 introduces. Each kind is tested
in isolation against the pure compile_* functions; the canonical-write
service's I/O behavior (apply, audit, SHACL pre-check) is exercised in
test_semantic_canonical_write.py.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.semantic_command_compiler import InvalidCommandPayload, compile_command
from app.services.semantic_export import namespace_from_settings


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


# Stage 2 §5.4 — EntitiesPage canonical-write kinds -------------------------------------


def _data_graph_iri(ontology_id: str) -> str:
    return f"http://op.local/graph/data/{ontology_id}"


def _entity_iri(entity_id: str) -> str:
    return f"http://op.local/ns/entity/{entity_id}"


def test_create_entity_writes_named_individual_label_and_class_membership():
    """create_entity mints an entity IRI and writes owl:NamedIndividual, rdfs:label,
    rdf:type owl:NamedIndividual + class membership, skos:altLabel aliases, and
    property values into the data graph."""
    payload = {
        "ontology_id": "ont-1",
        "entity_id": "entity-1",
        "class_iri_or_legacy_id": "class-1",
        "label": "Alice",
        "aliases": ["Al"],
        "properties": {
            "http://op.local/ns/property/email": "alice@example.com",
        },
    }

    compiled = compile_command("create_entity", payload, _settings())

    assert compiled.command_kind == "create_entity"
    assert compiled.object_kind == "entity"
    assert compiled.source_ids == ["entity-1"]
    graph_iri = _data_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    entity_term = f"<{_entity_iri('entity-1')}>"
    class_term = f"<{_class_iri('class-1')}>"
    rdf_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"

    # rdf:type owl:NamedIndividual
    assert (entity_term, rdf_type, "<http://www.w3.org/2002/07/owl#NamedIndividual>", graph_iri) in compiled.delta.inserts
    # rdf:type <class>
    assert (entity_term, rdf_type, class_term, graph_iri) in compiled.delta.inserts
    # rdfs:label
    assert (entity_term, _RDFS_LABEL, '"Alice"', graph_iri) in compiled.delta.inserts
    # alias
    skos_alt = "<http://www.w3.org/2004/02/skos/core#altLabel>"
    assert (entity_term, skos_alt, '"Al"', graph_iri) in compiled.delta.inserts
    # property triple
    assert (entity_term, "<http://op.local/ns/property/email>", '"alice@example.com"', graph_iri) in compiled.delta.inserts


def test_update_entity_replaces_label_aliases_and_properties():
    """update_entity patches label / aliases / properties on an existing entity.
    Each patch is implemented as delete-then-insert; only fields present in the
    payload are touched."""
    payload = {
        "ontology_id": "ont-1",
        "entity_id": "entity-1",
        "label": "Alice v2",
        "aliases": ["Al2"],
        "properties": {
            "http://op.local/ns/property/email": "alice2@example.com",
        },
    }

    compiled = compile_command("update_entity", payload, _settings())

    assert compiled.command_kind == "update_entity"
    assert compiled.object_kind == "entity"
    graph_iri = _data_graph_iri("ont-1")
    entity_term = f"<{_entity_iri('entity-1')}>"
    # Label patch
    assert (entity_term, _RDFS_LABEL, "?o", graph_iri) in compiled.delta.deletes
    assert (entity_term, _RDFS_LABEL, '"Alice v2"', graph_iri) in compiled.delta.inserts
    # Alias patch: wildcard delete + new value
    skos_alt = "<http://www.w3.org/2004/02/skos/core#altLabel>"
    assert (entity_term, skos_alt, "?o", graph_iri) in compiled.delta.deletes
    assert (entity_term, skos_alt, '"Al2"', graph_iri) in compiled.delta.inserts
    # Property patch: delete-then-insert for the supplied predicate
    prop_pred = "<http://op.local/ns/property/email>"
    assert (entity_term, prop_pred, "?o", graph_iri) in compiled.delta.deletes
    assert (entity_term, prop_pred, '"alice2@example.com"', graph_iri) in compiled.delta.inserts


def test_entity_property_keys_expand_bare_ids_and_preserve_explicit_iris():
    create = compile_command(
        "create_entity",
        {
            "ontology_id": "ont-1",
            "entity_id": "entity-1",
            "class_iri_or_legacy_id": "class-1",
            "label": "Alice",
            "properties": {
                "is_latest": True,
                "http://op.local/ns/property/email": "alice@example.com",
            },
        },
        _settings(),
    )
    update = compile_command(
        "update_entity",
        {
            "ontology_id": "ont-1",
            "entity_id": "entity-1",
            "properties": {
                "is_latest": False,
                "http://op.local/ns/property/email": None,
            },
        },
        _settings(),
    )
    graph_iri = _data_graph_iri("ont-1")
    entity_term = f"<{_entity_iri('entity-1')}>"
    bare_predicate = "<http://op.local/ns/property/is_latest>"
    explicit_predicate = "<http://op.local/ns/property/email>"

    assert (entity_term, bare_predicate, '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>', graph_iri) in create.delta.inserts
    assert (entity_term, explicit_predicate, '"alice@example.com"', graph_iri) in create.delta.inserts
    assert (entity_term, bare_predicate, "?o", graph_iri) in update.delta.deletes
    assert (entity_term, bare_predicate, '"false"^^<http://www.w3.org/2001/XMLSchema#boolean>', graph_iri) in update.delta.inserts
    assert (entity_term, explicit_predicate, "?o", graph_iri) in update.delta.deletes
    assert all(predicate != "<is_latest>" for _, predicate, _, _ in create.delta.inserts)
    assert all(predicate != "<is_latest>" for _, predicate, _, _ in update.delta.deletes)


@pytest.mark.parametrize(
    ("command_kind", "payload"),
    [
        (
            "create_entity",
            {
                "ontology_id": "ont-1",
                "class_iri_or_legacy_id": "class-1",
                "label": "Alice",
                "properties": {"": None},
            },
        ),
        (
            "update_entity",
            {
                "ontology_id": "ont-1",
                "entity_id": "entity-1",
                "properties": {1: "invalid"},
            },
        ),
    ],
)
def test_entity_property_keys_must_be_non_empty_strings(command_kind, payload):
    with pytest.raises(InvalidCommandPayload, match="properties keys must be non-empty strings"):
        compile_command(command_kind, payload, _settings())


def test_delete_entity_cascades_to_relations():
    """delete_entity removes all triples with the entity as subject OR object,
    so any relation that references the entity is also removed."""
    payload = {
        "ontology_id": "ont-1",
        "entity_id": "entity-1",
    }

    compiled = compile_command("delete_entity", payload, _settings())

    assert compiled.command_kind == "delete_entity"
    assert compiled.object_kind == "entity"
    graph_iri = _data_graph_iri("ont-1")
    entity_term = f"<{_entity_iri('entity-1')}>"
    # Subject wildcard delete
    assert (entity_term, "?p", "?o", graph_iri) in compiled.delta.deletes
    # Object wildcard delete (cascade to relations referencing this entity)
    assert ("?s", "?p", entity_term, graph_iri) in compiled.delta.deletes


def _relation_type_iri(relation_type_id: str) -> str:
    return f"http://op.local/ns/relation-type/{relation_type_id}"


def test_create_relation_writes_asserted_relation_triple():
    """create_relation writes the (source, relation_type, target) triple to the
    data graph. relation_type_iri is used verbatim so callers can point at
    arbitrary OWL ObjectProperties."""
    payload = {
        "ontology_id": "ont-1",
        "source_entity_iri": _entity_iri("entity-1"),
        "relation_type_iri": _relation_type_iri("rel-1"),
        "target_entity_iri": _entity_iri("entity-2"),
    }

    compiled = compile_command("create_relation", payload, _settings())

    assert compiled.command_kind == "create_relation"
    assert compiled.object_kind == "relation"
    graph_iri = _data_graph_iri("ont-1")
    expected = (
        f"<{_entity_iri('entity-1')}>",
        f"<{_relation_type_iri('rel-1')}>",
        f"<{_entity_iri('entity-2')}>",
        graph_iri,
    )
    assert expected in compiled.delta.inserts


def test_delete_relation_targets_specific_triple_pattern():
    """delete_relation removes the (source, predicate, target) triple from the
    data graph. Object position is pinned to the target entity so other objects
    under the same predicate remain untouched."""
    payload = {
        "ontology_id": "ont-1",
        "source_entity_iri": _entity_iri("entity-1"),
        "relation_type_iri": _relation_type_iri("rel-1"),
        "target_entity_iri": _entity_iri("entity-2"),
    }

    compiled = compile_command("delete_relation", payload, _settings())

    assert compiled.command_kind == "delete_relation"
    assert compiled.object_kind == "relation"
    graph_iri = _data_graph_iri("ont-1")
    expected = (
        f"<{_entity_iri('entity-1')}>",
        f"<{_relation_type_iri('rel-1')}>",
        f"<{_entity_iri('entity-2')}>",
        graph_iri,
    )
    assert expected in compiled.delta.deletes


# Stage 2 §7.4 — Catalog mapping canonical-write kinds ----------------------------------


def _external_field_iri(field_id: str) -> str:
    return f"http://op.local/ns/external-field/{field_id}"


def _mapping_iri(mapping_id: str) -> str:
    return f"http://op.local/ns/mapping/{mapping_id}"


def _import_graph_iri(source_id: str, run_id: str) -> str:
    return f"http://op.local/graph/import/{source_id}/{run_id}"


def test_create_mapping_writes_semantic_mapping_to_ontology_graph():
    """create_mapping writes an op:SemanticMapping resource with externalField,
    targetClass, joinKey, confidence, and owner links into graph/ontology/{id}.
    When source_id/run_id are absent the ontology graph is the default target."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-1",
        "external_field_iri": _external_field_iri("field-1"),
        "target_type": "class",
        "target_iri": _class_iri("class-1"),
        "join_key": '{"entity_property": "student_number", "external_field": "student_no"}',
        "confidence": 0.92,
        "owner": "owner-1",
    }

    compiled = compile_command("create_mapping", payload, _settings())

    assert compiled.command_kind == "create_mapping"
    assert compiled.object_kind == "mapping"
    assert compiled.source_ids == ["map-1"]
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    mapping_term = f"<{_mapping_iri('map-1')}>"
    op = "http://op.local/ns/vocab/"
    rdf_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
    # rdf:type op:SemanticMapping
    assert (mapping_term, rdf_type, f"<{op}SemanticMapping>", graph_iri) in compiled.delta.inserts
    # op:externalField
    assert (mapping_term, f"<{op}externalField>", f"<{_external_field_iri('field-1')}>", graph_iri) in compiled.delta.inserts
    # op:targetClass (target_type=class)
    assert (mapping_term, f"<{op}targetClass>", f"<{_class_iri('class-1')}>", graph_iri) in compiled.delta.inserts
    # op:joinKey literal
    assert (mapping_term, f"<{op}joinKey>", '"{\\"entity_property\\": \\"student_number\\", \\"external_field\\": \\"student_no\\"}"', graph_iri) in compiled.delta.inserts
    # op:confidence decimal
    assert (mapping_term, f"<{op}confidence>", '"0.92"^^<http://www.w3.org/2001/XMLSchema#decimal>', graph_iri) in compiled.delta.inserts
    # op:owner
    assert (mapping_term, f"<{op}owner>", '"owner-1"', graph_iri) in compiled.delta.inserts


def test_create_mapping_with_import_run_targets_import_graph_and_writes_prov_link():
    """When source_id + run_id are supplied the target graph becomes
    graph/import/{source_id}/{run_id} and a prov:wasDerivedBy link is written."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-2",
        "external_field_iri": _external_field_iri("field-1"),
        "target_type": "property",
        "target_iri": "http://op.local/ns/property/prop-1",
        "join_key": "{}",
        "confidence": 0.5,
        "owner": "owner-2",
        "source_id": "src-1",
        "run_id": "run-1",
        "import_run_iri": "http://op.local/ns/import-run/run-1",
    }

    compiled = compile_command("create_mapping", payload, _settings())

    assert compiled.command_kind == "create_mapping"
    graph_iri = _import_graph_iri("src-1", "run-1")
    assert compiled.target_graph_iris == [graph_iri]
    mapping_term = f"<{_mapping_iri('map-2')}>"
    op = "http://op.local/ns/vocab/"
    prov = "http://www.w3.org/ns/prov#"
    assert (mapping_term, f"<{prov}wasDerivedBy>", f"<http://op.local/ns/import-run/run-1>", graph_iri) in compiled.delta.inserts
    # op:targetProperty (target_type=property)
    assert (mapping_term, f"<{op}targetProperty>", f"<http://op.local/ns/property/prop-1>", graph_iri) in compiled.delta.inserts


def test_create_mapping_target_relation_type_uses_target_relation_type_predicate():
    """target_type=relation_type writes op:targetRelationType."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-3",
        "external_field_iri": _external_field_iri("field-1"),
        "target_type": "relation_type",
        "target_iri": "http://op.local/ns/relation-type/rel-1",
        "join_key": "{}",
        "confidence": 1.0,
    }

    compiled = compile_command("create_mapping", payload, _settings())

    op = "http://op.local/ns/vocab/"
    graph_iri = _ontology_graph_iri("ont-1")
    mapping_term = f"<{_mapping_iri('map-3')}>"
    assert (mapping_term, f"<{op}targetRelationType>", f"<http://op.local/ns/relation-type/rel-1>", graph_iri) in compiled.delta.inserts


def test_update_mapping_patches_join_key_confidence_and_owner():
    """update_mapping patches join_key / confidence / owner via delete-then-insert.
    Only fields present in the payload are touched."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-1",
        "join_key": '{"k": "v2"}',
        "confidence": 0.8,
        "owner": "owner-3",
    }

    compiled = compile_command("update_mapping", payload, _settings())

    assert compiled.command_kind == "update_mapping"
    assert compiled.object_kind == "mapping"
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    mapping_term = f"<{_mapping_iri('map-1')}>"
    op = "http://op.local/ns/vocab/"
    # join_key patch
    assert (mapping_term, f"<{op}joinKey>", "?o", graph_iri) in compiled.delta.deletes
    assert (mapping_term, f"<{op}joinKey>", '"{\\"k\\": \\"v2\\"}"', graph_iri) in compiled.delta.inserts
    # confidence patch
    assert (mapping_term, f"<{op}confidence>", "?o", graph_iri) in compiled.delta.deletes
    assert (mapping_term, f"<{op}confidence>", '"0.8"^^<http://www.w3.org/2001/XMLSchema#decimal>', graph_iri) in compiled.delta.inserts
    # owner patch
    assert (mapping_term, f"<{op}owner>", "?o", graph_iri) in compiled.delta.deletes
    assert (mapping_term, f"<{op}owner>", '"owner-3"', graph_iri) in compiled.delta.inserts


def test_delete_mapping_emits_subject_wildcard_deletes():
    """delete_mapping removes every triple whose subject is the mapping IRI."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-1",
    }

    compiled = compile_command("delete_mapping", payload, _settings())

    assert compiled.command_kind == "delete_mapping"
    assert compiled.object_kind == "mapping"
    graph_iri = _ontology_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    mapping_term = f"<{_mapping_iri('map-1')}>"
    assert (mapping_term, "?p", "?o", graph_iri) in compiled.delta.deletes


def test_delete_mapping_with_import_run_targets_import_graph():
    """delete_mapping with source_id + run_id removes the mapping from the
    import graph rather than the ontology graph."""
    payload = {
        "ontology_id": "ont-1",
        "mapping_id": "map-2",
        "source_id": "src-1",
        "run_id": "run-1",
    }

    compiled = compile_command("delete_mapping", payload, _settings())

    graph_iri = _import_graph_iri("src-1", "run-1")
    assert compiled.target_graph_iris == [graph_iri]
    mapping_term = f"<{_mapping_iri('map-2')}>"
    assert (mapping_term, "?p", "?o", graph_iri) in compiled.delta.deletes


# Stage 2 §6.4 — review_assertion canonical-write kind -----------------------------


def _data_graph_iri(ontology_id: str) -> str:
    return f"http://op.local/graph/data/{ontology_id}"


def _reasoning_result_graph_iri(run_id: str) -> str:
    return f"http://op.local/graph/reasoning-result/{run_id}"


def _rule_result_graph_iri(run_id: str) -> str:
    return f"http://op.local/graph/rule-result/{run_id}"


def test_review_assertion_writes_rdf_star_reification_to_data_graph_for_asserted():
    """review_assertion for an asserted fact writes RDF-star reification
    triples onto the data graph: <<s p o>> op:auditStatus / op:reviewReason /
    op:reviewedBy / op:reviewedAt."""
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "asserted",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/email",
        "object_value": "alice@example.com",
        "decision": "approved",
        "reason": "looks good",
        "reviewed_by": "user:alice",
    }

    compiled = compile_command("review_assertion", payload, _settings())

    assert compiled.command_kind == "review_assertion"
    assert compiled.object_kind == "fact_review"
    graph_iri = _data_graph_iri("ont-1")
    assert compiled.target_graph_iris == [graph_iri]
    op = "http://op.local/ns/vocab/"

    # The triple-subject is the RDF-star quoted triple term.
    # Literal object form: <<<s> <p> "literal">>
    quoted = (
        f"<<<http://op.local/ns/entity/alice> "
        f"<http://op.local/ns/property/email> "
        f'"alice@example.com">>'
    )
    # auditStatus approved
    assert (quoted, f"<{op}auditStatus>", '"approved"', graph_iri) in compiled.delta.inserts
    # reviewReason text
    assert (quoted, f"<{op}reviewReason>", '"looks good"', graph_iri) in compiled.delta.inserts
    # reviewedBy
    assert (
        quoted, f"<{op}reviewedBy>", f"<http://op.local/ns/user/alice>", graph_iri
    ) in compiled.delta.inserts or (
        quoted, f"<{op}reviewedBy>", '"user:alice"', graph_iri
    ) in compiled.delta.inserts
    # reviewedAt is an ISO-8601 literal
    reviewed_at_inserts = [
        (s, p, o, g)
        for (s, p, o, g) in compiled.delta.inserts
        if s == quoted and p == f"<{op}reviewedAt>"
    ]
    assert len(reviewed_at_inserts) == 1


def test_review_assertion_iri_object_is_emitted_as_iri_term():
    """When object_value is a dict with kind=iri (or has an ``iri`` key),
    the reification object is rendered as an IRI term, not a literal."""
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "asserted",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/knows",
        "object_value": {"iri": "http://op.local/ns/entity/bob"},
        "decision": "approved",
        "reason": "friend",
        "reviewed_by": "user:alice",
    }

    compiled = compile_command("review_assertion", payload, _settings())
    graph_iri = _data_graph_iri("ont-1")
    quoted = (
        f"<<<http://op.local/ns/entity/alice> "
        f"<http://op.local/ns/property/knows> "
        f"<http://op.local/ns/entity/bob>>>"
    )
    op = "http://op.local/ns/vocab/"
    assert (quoted, f"<{op}auditStatus>", '"approved"', graph_iri) in compiled.delta.inserts


def test_review_assertion_inferred_kind_targets_reasoning_result_graph():
    """For assertion_kind=inferred the reification is written to the
    reasoning-result graph passed in via ``result_graph_iri``."""
    reasoning_iri = _reasoning_result_graph_iri("run-7")
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "inferred",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/parent",
        "object_value": {"iri": "http://op.local/ns/entity/parent-bob"},
        "decision": "needs_correction",
        "reason": "verify",
        "reviewed_by": "user:carol",
        "result_graph_iri": reasoning_iri,
    }

    compiled = compile_command("review_assertion", payload, _settings())
    assert compiled.target_graph_iris == [reasoning_iri]


def test_review_assertion_rule_derived_kind_targets_rule_result_graph():
    """For assertion_kind=rule_derived the reification is written to the
    rule-result graph passed in via ``result_graph_iri``."""
    rule_iri = _rule_result_graph_iri("run-9")
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "rule_derived",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/category",
        "object_value": "vip",
        "decision": "rejected",
        "reason": "rule outdated",
        "linked_fix_proposal_id": "fix-prop-1",
        "reviewed_by": "user:carol",
        "result_graph_iri": rule_iri,
    }

    compiled = compile_command("review_assertion", payload, _settings())
    assert compiled.target_graph_iris == [rule_iri]
    op = "http://op.local/ns/vocab/"
    quoted = (
        f"<<<http://op.local/ns/entity/alice> "
        f"<http://op.local/ns/property/category> "
        f'"vip">>'
    )
    # linkedFixProposal is only written when the decision is rejected and
    # the caller supplied a fix proposal id.
    assert (
        quoted, f"<{op}linkedFixProposal>",
        f"<http://op.local/ns/fix-proposal/fix-prop-1>", rule_iri
    ) in compiled.delta.inserts


def test_review_assertion_fact_id_is_stable_sha256_over_canonical_ntriples():
    """The compiled command metadata carries a ``fact_id`` that is the
    SHA-256 hex digest of the canonical N-Triples serialization of
    (subject, predicate, object). Calling twice with the same triple
    yields the same fact_id; changing the object changes it."""
    base_payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "asserted",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/email",
        "object_value": "alice@example.com",
        "decision": "approved",
        "reason": "ok",
        "reviewed_by": "user:alice",
    }

    compiled_one = compile_command("review_assertion", dict(base_payload), _settings())
    compiled_two = compile_command("review_assertion", dict(base_payload), _settings())
    fact_id_one = compiled_one.metadata["fact_id"]
    assert fact_id_one == compiled_two.metadata["fact_id"]
    assert len(fact_id_one) == 64  # SHA-256 hex digest

    # Different object → different digest.
    different = dict(base_payload)
    different["object_value"] = "alice@different.example"
    compiled_diff = compile_command("review_assertion", different, _settings())
    assert compiled_diff.metadata["fact_id"] != fact_id_one


def test_review_assertion_rejects_invalid_decision():
    """decision must be one of approved / rejected / needs_correction."""
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "asserted",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/email",
        "object_value": "alice@example.com",
        "decision": "maybe",
        "reason": "unsure",
        "reviewed_by": "user:alice",
    }

    from app.services.semantic_command_compiler import InvalidCommandPayload
    import pytest

    with pytest.raises(InvalidCommandPayload):
        compile_command("review_assertion", payload, _settings())


def test_review_assertion_rejected_requires_linked_fix_proposal_id():
    """A rejected review must carry a linked_fix_proposal_id."""
    payload = {
        "ontology_id": "ont-1",
        "assertion_kind": "asserted",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/email",
        "object_value": "alice@example.com",
        "decision": "rejected",
        "reason": "nope",
        "reviewed_by": "user:alice",
        # linked_fix_proposal_id missing
    }

    from app.services.semantic_command_compiler import InvalidCommandPayload
    import pytest

    with pytest.raises(InvalidCommandPayload):
        compile_command("review_assertion", payload, _settings())


def test_update_fact_replaces_literal_object_in_data_graph():
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/email",
        "old_object_value": "alice@example.com",
        "new_object_value": "alice@school.example",
    }

    compiled = compile_command("update_fact", payload, _settings())

    graph_iri = "http://op.local/graph/data/ont-1"
    assert compiled.command_kind == "update_fact"
    assert compiled.object_kind == "fact"
    assert compiled.target_graph_iris == [graph_iri]
    subject = "<http://op.local/ns/entity/alice>"
    predicate = "<http://op.local/ns/property/email>"
    assert (subject, predicate, '"alice@example.com"', graph_iri) in compiled.delta.deletes
    assert (subject, predicate, '"alice@school.example"', graph_iri) in compiled.delta.inserts


def test_delete_fact_uses_iri_object_when_requested():
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/advisor",
        "object_value": "http://op.local/ns/entity/bob",
        "object_is_iri": True,
    }

    compiled = compile_command("delete_fact", payload, _settings())

    graph_iri = "http://op.local/graph/data/ont-1"
    assert compiled.command_kind == "delete_fact"
    assert (
        "<http://op.local/ns/entity/alice>",
        "<http://op.local/ns/property/advisor>",
        "<http://op.local/ns/entity/bob>",
        graph_iri,
    ) in compiled.delta.deletes


def test_bind_and_unbind_fact_evidence():
    """bind_fact_evidence / unbind_fact_evidence compile to Postgres-only commands.

    The compiler emits an empty RdfGraphDelta (writes go through the dedicated
    fact-evidence REST endpoint at apply time) and surfaces the computed
    fact_id / binding_id in metadata.
    """
    bind_payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://op.local/ns/entity/alice",
        "predicate_iri": "http://op.local/ns/property/enrolledIn",
        "object_value": "http://op.local/ns/class/Class1",
        "object_is_iri": True,
        "text": "Alice is enrolled in Class 1.",
    }

    bound = compile_command("bind_fact_evidence", bind_payload, _settings())

    graph_iri = "http://op.local/graph/data/ont-1"
    assert bound.command_kind == "bind_fact_evidence"
    assert bound.object_kind == "fact_evidence"
    assert bound.delta.inserts == []
    assert bound.delta.deletes == []
    assert bound.target_graph_iris == []
    # fact_id is deterministically computed from (s, p, o, g)
    assert bound.metadata["fact_id"]
    assert bound.metadata["subject_iri"] == "http://op.local/ns/entity/alice"
    assert bound.metadata["predicate_iri"] == "http://op.local/ns/property/enrolledIn"
    assert bound.metadata["object_value"] == "<http://op.local/ns/class/Class1>"
    assert bound.metadata["graph_iri"] == graph_iri
    assert bound.metadata["text"] == "Alice is enrolled in Class 1."

    # Providing a mismatched fact_id must be rejected.
    from app.services.semantic_command_compiler import InvalidCommandPayload

    bad_payload = dict(bind_payload)
    bad_payload["fact_id"] = "sha256:deadbeef"
    with pytest.raises(InvalidCommandPayload):
        compile_command("bind_fact_evidence", bad_payload, _settings())

    # Providing the matching fact_id is accepted.
    good_payload = dict(bind_payload)
    good_payload["fact_id"] = bound.metadata["fact_id"]
    recompiled = compile_command("bind_fact_evidence", good_payload, _settings())
    assert recompiled.metadata["fact_id"] == bound.metadata["fact_id"]

    # unbind_fact_evidence resolves purely by binding_id; the compiler records
    # it in metadata and emits no RDF writes either.
    unbound = compile_command(
        "unbind_fact_evidence",
        {
            "ontology_id": "ont-1",
            "binding_id": "00000000-0000-0000-0000-000000000001",
        },
        _settings(),
    )
    assert unbound.command_kind == "unbind_fact_evidence"
    assert unbound.object_kind == "fact_evidence"
    assert unbound.delta.inserts == []
    assert unbound.delta.deletes == []
    assert unbound.metadata["binding_id"] == "00000000-0000-0000-0000-000000000001"
