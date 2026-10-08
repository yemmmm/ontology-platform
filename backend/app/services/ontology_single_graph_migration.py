"""One-time legacy model merge; never used to resolve live read/write scope."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from rdflib import Graph
from rdflib.compare import to_canonical_graph
from rdflib.namespace import OWL, RDF


class ModelMergeConflict(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(
            "Conflicting model definitions: " + json.dumps(conflicts, ensure_ascii=False)
        )


def merge_model_graphs(contents: dict[str, str]) -> Graph:
    """Union asserted business content; reject contradictory singular definitions."""
    merged = Graph()
    origins = defaultdict(set)
    for iri, content in contents.items():
        graph = Graph().parse(data=content, format="turtle") if content.strip() else Graph()
        for triple in graph:
            merged.add(triple)
            origins[triple].add(iri)
    functional = set(merged.subjects(RDF.type, OWL.FunctionalProperty))
    values = defaultdict(set)
    for subject, predicate, obj in merged:
        if predicate in functional or str(predicate).rsplit("/", 1)[-1] in {
            "semanticDefinition",
            "mappingDefinition",
            "parameters",
            "result",
            "id",
        }:
            values[subject, predicate].add(obj)
    conflicts = [
        {
            "iri": str(s),
            "predicate": str(p),
            "values": sorted(o.n3() for o in objects),
            "storage_locations": sorted({g for o in objects for g in origins[s, p, o]}),
        }
        for (s, p), objects in values.items()
        if len(objects) > 1
    ]
    if conflicts:
        raise ModelMergeConflict(conflicts)
    return merged


def model_content_hash(graph: Graph) -> str:
    triples = sorted(" ".join(term.n3() for term in triple) for triple in to_canonical_graph(graph))
    return hashlib.sha256("\n".join(triples).encode()).hexdigest()


def upgrade_checkpoint(snapshot, settings):
    """Convert a validated retained v2 snapshot in memory; preserve the original artifact."""
    result = deepcopy(snapshot)
    tables = result["tables"]
    registries = tables["semantic_graph_registry"]
    old_graphs = result["graphs"]
    new_graphs = {}
    kept_registry, kept_revision, kept_state = [], [], []
    graph_map = {}
    owners = {row["id"]: row for row in tables["ontologies"]}
    sets = tables.pop("semantic_graph_sets", [])
    members = tables.pop("semantic_graph_set_members", [])
    graph_owners = {row["graph_iri"]: row["semantic_owner_id"] for row in registries}
    for oid, ontology in owners.items():
        iri = f"{settings.semantic_graph_iri_prefix.rstrip('/')}/ontology/{oid}"
        owned = [row for row in registries if row["semantic_owner_id"] == oid]
        business = [row for row in owned if row["category"] in {"ontology", "data", "policy"}]
        graph = merge_model_graphs(
            {row["graph_iri"]: old_graphs[row["graph_iri"]] for row in business}
        )
        new_graphs[iri] = graph.serialize(format="turtle")
        graph_map.update({row["graph_iri"]: iri for row in business})
        revision = (
            max(
                (
                    row["revision"]
                    for row in tables["semantic_graph_revisions"]
                    if row["graph_iri"] in graph_map and graph_owners.get(row["graph_iri"]) == oid
                ),
                default=0,
            )
            + 1
        )
        ontology.update(
            model_graph_iri=iri,
            model_revision=revision,
            model_content_hash=model_content_hash(graph),
            reference_ontology_ids=[],
        )
        registry = next((row for row in owned if row["graph_iri"] == iri), None)
        if registry is None:
            registry = {
                "id": str(uuid5(NAMESPACE_URL, f"model-registry:{oid}")),
                "graph_iri": iri,
                "category": "ontology",
                "semantic_owner_type": "ontology",
                "semantic_owner_id": oid,
                "mutable_by_direct_edit": True,
                "managed": True,
                "registry_metadata": {},
            }
        registry["registry_metadata"] = {}
        kept_registry.append(registry)
        rev = next(
            (row for row in tables["semantic_graph_revisions"] if row["graph_iri"] == iri),
            {
                "id": str(uuid5(NAMESPACE_URL, f"model-revision:{oid}")),
                "graph_iri": iri,
                "revision_metadata": {},
            },
        )
        rev.update(revision=revision, content_hash=ontology["model_content_hash"])
        kept_revision.append(rev)
        kept_state.extend(row for row in tables["semantic_graph_states"] if row["graph_iri"] == iri)
    references = migrate_reference_scopes(tables["ontologies"], registries, sets, members)
    for oid, dependencies in references.items():
        owners[oid]["reference_ontology_ids"] = dependencies
    scope_ids = {
        scope["id"]: scope["scope_id"] for scope in sets if scope.get("scope_type") == "ontology"
    }
    for rows in tables.values():
        for row in rows:
            for old, new in (
                ("graph_set_id", "ontology_id"),
                ("target_graph_set_id", "target_ontology_id"),
                ("source_graph_iris", "model_graph_iris"),
            ):
                if old in row:
                    value = row.pop(old)
                    if new not in row:
                        row[new] = scope_ids.get(value, value) if isinstance(value, str) else value
    tables.update(
        semantic_graph_registry=kept_registry,
        semantic_graph_revisions=kept_revision,
        semantic_graph_states=kept_state,
    )
    result["graphs"] = new_graphs
    result["schema_version"] = "r4-0-026-platform-data/v3"
    from app.services.checkpoint_data import snapshot_digest

    result["digest"] = snapshot_digest(result)
    return result


def migrate_reference_scopes(ontologies, registry, scopes, members):
    """Preserve one agreed reference window per Ontology; report conflicting windows."""
    projects = {row["id"]: row["project_id"] for row in ontologies}
    owners = {
        row["graph_iri"]: row["semantic_owner_id"]
        for row in registry
        if row["semantic_owner_type"] == "ontology"
    }
    result = {oid: [] for oid in projects}
    selected = {}
    for scope in scopes:
        metadata = scope.get("graph_set_metadata", scope.get("metadata", {}))
        if scope.get("status") != "active" or not metadata.get("mapping_reference_scope"):
            continue
        oid = scope["scope_id"]
        dependencies = set()
        for member in members:
            if member["graph_set_id"] != scope["id"]:
                continue
            owner = owners.get(member["graph_iri"])
            if oid not in projects or owner not in projects or projects[owner] != projects[oid]:
                raise ValueError(
                    f"Reference scope {scope['id']} has an unresolved or cross-project member: {member['graph_iri']}"
                )
            if owner != oid:
                dependencies.add(owner)
        if oid in selected and result[oid] != sorted(dependencies):
            raise ValueError(
                f"Conflicting reference scopes for Ontology {oid}: {selected[oid]}, {scope['id']}"
            )
        selected[oid] = scope["id"]
        result[oid] = sorted(dependencies)
    return result
