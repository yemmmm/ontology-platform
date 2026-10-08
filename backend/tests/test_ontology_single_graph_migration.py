"""R4.0-026 migration preserves asserted identity and rejects conflicting definitions."""

from copy import deepcopy

import pytest
from rdflib import Graph, URIRef

from app.core.config import Settings
from app.services.ontology_single_graph_migration import (
    ModelMergeConflict,
    merge_model_graphs,
    model_content_hash,
    upgrade_checkpoint,
)
from app.services.checkpoint_data import CheckpointDataService, snapshot_digest
from test_checkpoint_data import source


def test_merge_unifies_definitions_nodes_and_relations_without_changing_identity():
    schema = "<urn:Class> a <http://www.w3.org/2002/07/owl#Class> ."
    data = "<urn:node> a <urn:Class> ; <urn:rel> <urn:other> ."
    graph = merge_model_graphs({"urn:schema": schema, "urn:data": data})
    assert len(graph) == 3
    assert (URIRef("urn:node"), URIRef("urn:rel"), URIRef("urn:other")) in graph


def test_conflict_reports_both_locations_before_any_merge_can_be_used():
    with pytest.raises(ModelMergeConflict) as failure:
        merge_model_graphs(
            {
                "urn:first": '<urn:a> <https://op/vocab/id> "one" .',
                "urn:second": '<urn:a> <https://op/vocab/id> "two" .',
            }
        )
    assert failure.value.conflicts == [
        {
            "iri": "urn:a",
            "predicate": "https://op/vocab/id",
            "values": ['"one"', '"two"'],
            "storage_locations": ["urn:first", "urn:second"],
        }
    ]


def test_blank_node_content_hash_is_independent_of_parser_ids():
    a = Graph().parse(data='<urn:a> <urn:p> [ <urn:v> "x" ] .', format="turtle")
    b = Graph().parse(data='<urn:a> <urn:p> [ <urn:v> "x" ] .', format="turtle")
    assert model_content_hash(a) == model_content_hash(b)


def test_retained_v2_checkpoint_upgrades_in_memory_then_forks_without_derived_content(source):
    session, store, settings, _ = source
    snapshot = CheckpointDataService(session, store).capture("project", ["ontology"])
    session.commit()
    legacy = deepcopy(snapshot)
    legacy["schema_version"] = "r3-0-017-platform-data/v2"
    ontology = legacy["tables"]["ontologies"][0]
    for key in (
        "model_graph_iri",
        "model_revision",
        "model_content_hash",
        "reference_ontology_ids",
    ):
        ontology.pop(key)
    registry = legacy["tables"]["semantic_graph_registry"][0]
    data = "urn:legacy-data"
    inferred = "urn:old-inferred"
    legacy["tables"]["semantic_graph_registry"].extend(
        [
            {**registry, "id": "legacy-data", "graph_iri": data, "category": "data"},
            {
                **registry,
                "id": "legacy-derived",
                "graph_iri": inferred,
                "category": "reasoning_result",
            },
        ]
    )
    legacy["tables"]["semantic_graph_sets"] = [
        {
            "id": "legacy-set",
            "scope_type": "ontology",
            "scope_id": "ontology",
            "status": "active",
            "graph_set_metadata": {},
        }
    ]
    legacy["tables"]["semantic_graph_set_members"] = [
        {"graph_set_id": "legacy-set", "graph_iri": data, "role": "asserted_data"}
    ]
    legacy["graphs"][data] = '<urn:business> <urn:meaning> "asserted" .'
    legacy["graphs"][inferred] = '<urn:business> <urn:meaning> "inferred" .'
    legacy["digest"] = snapshot_digest(legacy)
    retained = deepcopy(legacy)
    upgraded = upgrade_checkpoint(legacy, settings)
    assert legacy == retained
    assert "semantic_graph_sets" not in upgraded["tables"]
    assert len(upgraded["graphs"]) == 1
    contents = next(iter(upgraded["graphs"].values()))
    assert "asserted" in contents and "inferred" not in contents
    fork = CheckpointDataService(session, store).fork(legacy, name="Legacy fork", settings=settings)
    assert len(fork["ontology_ids"]) == 1
    assert legacy == retained


def test_reference_migration_preserves_scope_and_rejects_conflicts():
    from app.services.ontology_single_graph_migration import migrate_reference_scopes

    ontologies = [dict(id="owner", project_id="p"), dict(id="shared", project_id="p")]
    registry = [
        dict(graph_iri="urn:o", semantic_owner_type="ontology", semantic_owner_id="owner"),
        dict(graph_iri="urn:s", semantic_owner_type="ontology", semantic_owner_id="shared"),
    ]
    scope = dict(
        id="scope", scope_id="owner", status="active", metadata={"mapping_reference_scope": True}
    )
    members = [
        dict(graph_set_id="scope", graph_iri="urn:o"),
        dict(graph_set_id="scope", graph_iri="urn:s"),
    ]
    assert migrate_reference_scopes(ontologies, registry, [scope], members)["owner"] == ["shared"]
    with pytest.raises(ValueError, match="Conflicting reference scopes"):
        migrate_reference_scopes(ontologies, registry, [scope, {**scope, "id": "other"}], members)
    with pytest.raises(ValueError, match="unresolved or cross-project"):
        migrate_reference_scopes(
            ontologies,
            registry,
            [scope],
            members + [dict(graph_set_id="scope", graph_iri="urn:unknown")],
        )
