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

