"""Project-scoped mapping views shared by Batch and canonical writes.

Only explicitly selected Graph Sets open cross-Ontology reference scope.
Project-wide views are used solely to protect existing reverse dependencies.
"""

from __future__ import annotations

import json

from rdflib import Graph, URIRef
from rdflib.namespace import RDF
from rdflib.util import from_n3
from sqlalchemy import select

from app.repositories.models import (
    OntologyModel,
    OntologyWriteFenceModel,
    SemanticGraphRegistryModel,
    SemanticGraphSetModel,
)
from app.services.semantic_export import namespace_from_settings


class MappingWriteError(RuntimeError):
    def __init__(self, code, message, findings=None):
        super().__init__(message)
        self.code = code
        self.findings = findings or []


def project_fence_check(session, project_ids, attempt_id=None):
    fence = session.scalar(
        select(OntologyWriteFenceModel)
        .join(OntologyModel, OntologyModel.id == OntologyWriteFenceModel.ontology_id)
        .where(OntologyModel.project_id.in_(project_ids))
        .where(OntologyWriteFenceModel.attempt_id != attempt_id)
    )
    if fence is not None:
        raise MappingWriteError(
            "mapping_reference_write_fenced",
            "A Project dependency has an unresolved write; inspect/reconcile its Attempt and retry",
        )


def _read(rdf_store, graph_iri):
    graph = Graph()
    if not hasattr(rdf_store, "graph_exists") or rdf_store.graph_exists(graph_iri):
        content = rdf_store.get_graph(graph_iri, "turtle")
        if content and content.strip():
            graph.parse(data=content, format="turtle")
    return graph


def _project(graph, delta, graph_iri):
    final = Graph()
    if graph_iri not in {*delta.clear_graphs, *delta.drop_graphs}:
        for triple in graph:
            final.add(triple)
    for subject, predicate, obj, target in delta.deletes:
        if target == graph_iri:
            final.remove(
                tuple(
                    None if term.startswith("?") else from_n3(term)
                    for term in (subject, predicate, obj)
                )
            )
    for subject, predicate, obj, target in delta.inserts:
        if target == graph_iri:
            final.add(tuple(from_n3(term) for term in (subject, predicate, obj)))
    return final


def _union(graphs):
    result = Graph()
    for graph in graphs:
        for triple in graph:
            result.add(triple)
    return result


def _references(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)
    elif isinstance(value, str) and value.startswith(("http://", "https://", "urn:")):
        yield value


def mapping_state(session, rdf_store, settings, delta, ontology_id=None):
    """Return relevant Project graphs, projected views and explicit scopes."""
    owner_query = select(SemanticGraphRegistryModel.semantic_owner_id).where(
        SemanticGraphRegistryModel.graph_iri.in_(delta.affected_graph_iris()),
        SemanticGraphRegistryModel.semantic_owner_type == "ontology",
    )
    owner_ids = set(session.scalars(owner_query))
    if ontology_id:
        owner_ids.add(str(ontology_id))
    projects = set(
        session.scalars(select(OntologyModel.project_id).where(OntologyModel.id.in_(owner_ids)))
    )
    owners = list(
        session.scalars(select(OntologyModel).where(OntologyModel.project_id.in_(projects)))
    )
    registry = list(
        session.scalars(
            select(SemanticGraphRegistryModel).where(
                SemanticGraphRegistryModel.semantic_owner_type == "ontology",
                SemanticGraphRegistryModel.semantic_owner_id.in_([owner.id for owner in owners]),
                SemanticGraphRegistryModel.category.in_(["ontology", "data"]),
            )
        )
    )
    graphs_by_owner = {owner.id: [] for owner in owners}
    graph_owner = {}
    for row in registry:
        graphs_by_owner[row.semantic_owner_id].append(row.graph_iri)
        graph_owner[row.graph_iri] = row.semantic_owner_id
    before = {iri: _read(rdf_store, iri) for iri in graph_owner}
    after = {iri: _project(graph, delta, iri) for iri, graph in before.items()}
    scopes = {owner.id: set(graphs_by_owner[owner.id]) for owner in owners}
    owner_project = {owner.id: owner.project_id for owner in owners}
    for graph_set in session.scalars(
        select(SemanticGraphSetModel).where(
            SemanticGraphSetModel.scope_type == "ontology",
            SemanticGraphSetModel.scope_id.in_(list(scopes)),
            SemanticGraphSetModel.status == "active",
        )
    ):
        if (graph_set.graph_set_metadata or {}).get("mapping_reference_scope") is not True:
            continue
        for member in graph_set.members:
            member_owner = graph_owner.get(member.graph_iri)
            if member_owner and owner_project[member_owner] == owner_project[graph_set.scope_id]:
                scopes[graph_set.scope_id].add(member.graph_iri)
    return projects, graphs_by_owner, before, after, scopes


def mapping_write_findings(session, rdf_store, settings, delta, ontology_id=None):
    from app.services.semantic_mapping_integrity import validate_mapping_graph

    projects, owners, before, after, scopes = mapping_state(
        session, rdf_store, settings, delta, ontology_id
    )
    findings = []
    touched = {
        str(from_n3(subject))
        for subject, _predicate, _obj, _graph in (*delta.inserts, *delta.deletes)
        if not subject.startswith("?")
    }
    for owner, graph_iris in owners.items():
        original = _union(before[iri] for iri in graph_iris)
        final = _union(after[iri] for iri in graph_iris)
        references = _union(after[iri] for iri in scopes[owner])
        original_refs = _union(before[iri] for iri in scopes[owner])
        previous = validate_mapping_graph(original, reference_graph=original_refs)
        old_keys = {json.dumps(finding, sort_keys=True) for finding in previous}
        for finding in validate_mapping_graph(final, original, references):
            if finding.get("subject") in touched or json.dumps(finding, sort_keys=True) not in old_keys:
                findings.append(finding)
    return findings


def mapping_write_relevant(session, rdf_store, settings, delta, ontology_id=None):
    """Identify mapping writes and changes to their declared dependencies."""
    _projects, _owners, before, after, _scopes = mapping_state(
        session, rdf_store, settings, delta, ontology_id
    )
    ns = namespace_from_settings(settings)
    mapping_types = {
        URIRef(f"{ns.vocab}{name}")
        for name in ("TableMapping", "JoinMapping", "EnumValueMeaning", "MetricDefinition")
    }
    resources = set()
    for graph in [*before.values(), *after.values()]:
        subjects = {
            subject
            for subject, _, kind in graph.triples((None, RDF.type, None))
            if kind in mapping_types
        }
        resources.update(str(subject) for subject in subjects)
        for subject in subjects:
            for _s, _p, obj in graph.triples((subject, None, None)):
                if isinstance(obj, URIRef):
                    resources.add(str(obj))
                else:
                    try:
                        resources.update(_references(json.loads(str(obj))))
                    except (ValueError, TypeError):
                        pass
    touched = set()
    for subject, _p, _o, _g in (*delta.inserts, *delta.deletes):
        if subject.startswith("?"):
            return bool(resources)
        touched.add(str(from_n3(subject)))
    for iri in {*delta.clear_graphs, *delta.drop_graphs}:
        touched.update(str(subject) for subject in before.get(iri, Graph()).subjects())
    return bool(touched & resources)


def require_batch_mapping_write(session, rdf_store, settings, delta, ontology_id=None):
    if mapping_write_relevant(session, rdf_store, settings, delta, ontology_id):
        raise MappingWriteError(
            "mapping_batch_required",
            "Submit this mapping/dependency change through Modeling Batch dry_run/apply_atomic "
            "so its Attempt, write fence and recovery receipt are retained",
        )
