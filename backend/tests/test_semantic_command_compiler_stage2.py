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


# Stage 2 §5.4 — EntitiesPage canonical-write kinds -------------------------------------


def _data_graph_iri(ontology_id: str) -> str:
    return f"http://op.local/graph/data/{ontology_id}"


def _entity_iri(entity_id: str) -> str:
    return f"http://op.local/ns/entity/{entity_id}"


def test_create_entity_writes_named_individual_label_and_class_membership():
    """create_entity mints an entity IRI and writes owl:NamedIndividual, rdfs:label,
    rdf:type owl:NamedIndividual + class membership, skos:altLabel aliases, and
    property values into the data graph. op:evidenceStatus defaults to
    missing_evidence per ADR 0004 §301-303."""
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
    # evidence_status defaults to missing_evidence
    op_ev = "<http://op.local/ns/vocab/evidenceStatus>"
    assert (entity_term, op_ev, '"missing_evidence"', graph_iri) in compiled.delta.inserts


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
    # op:evidenceStatus marked missing_evidence to match create_entity default.
    op_ev = "<http://op.local/ns/vocab/evidenceStatus>"
    assert any(q[1] == op_ev and q[3] == graph_iri for q in compiled.delta.inserts)


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

