#!/usr/bin/env python3
"""Development-only OWL reasoner command.

This command implements the manifest/stdout contract used by
``CommandOwlReasonerRunner`` so local reasoning workflows can run without a
Java OWL reasoner installed. It only reports a deterministic, conservative
success result; it does not perform OWL DL reasoning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.namespace import RDF, RDFS, XSD
from rdflib.term import Node


def _read_source_graphs(documents: list[dict[str, object]]) -> Graph:
    graph = Graph()
    for document in documents:
        path = document.get("path")
        if not isinstance(path, str):
            continue
        source_path = Path(path)
        source_format = document.get("format")
        graph_iri = document.get("graph_iri")
        graph.parse(
            source_path,
            format=source_format if isinstance(source_format, str) else None,
            publicID=graph_iri if isinstance(graph_iri, str) else None,
        )
    return graph


def _transitive_closure(edges: dict[Node, set[Node]], child: Node) -> set[Node]:
    parents: set[Node] = set()
    pending = list(edges.get(child, set()))
    while pending:
        parent = pending.pop()
        if parent in parents or parent == child:
            continue
        parents.add(parent)
        pending.extend(edges.get(parent, set()) - parents)
    return parents


def _turtle_term(term: Node, graph: Graph) -> str:
    return term.n3(graph.namespace_manager)


def _copy_labels(source_graph: Graph, inferred_graph: Graph) -> None:
    label_subjects = {term for triple in inferred_graph for term in triple if hasattr(term, "n3")}
    for subject in label_subjects:
        for _, _, label in source_graph.triples((subject, RDFS.label, None)):
            inferred_graph.add((subject, RDFS.label, label))


def _serialize_inferred_turtle(inferred_graph: Graph) -> str:
    if not inferred_graph:
        return ""
    inferred_graph.bind("rdf", RDF)
    inferred_graph.bind("rdfs", RDFS)
    inferred_graph.bind("xsd", XSD)
    lines = [
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    for subject, predicate, obj in sorted(
        inferred_graph,
        key=lambda triple: tuple(term.n3() for term in triple),
    ):
        lines.append(
            f"{_turtle_term(subject, inferred_graph)} "
            f"{_turtle_term(predicate, inferred_graph)} "
            f"{_turtle_term(obj, inferred_graph)} ."
        )
    return "\n".join(lines) + "\n"


def _infer_limited_rdfs(graph: Graph) -> tuple[list[dict[str, object]], str]:
    subclasses: dict[Node, set[Node]] = {}
    for child, _, parent in graph.triples((None, RDFS.subClassOf, None)):
        subclasses.setdefault(child, set()).add(parent)
    subproperties: dict[Node, set[Node]] = {}
    for child, _, parent in graph.triples((None, RDFS.subPropertyOf, None)):
        subproperties.setdefault(child, set()).add(parent)
    domains = {
        property_iri: class_iri
        for property_iri, _, class_iri in graph.triples((None, RDFS.domain, None))
    }
    ranges = {
        property_iri: class_iri
        for property_iri, _, class_iri in graph.triples((None, RDFS.range, None))
    }

    inferred_graph = Graph()
    entailments: list[dict[str, object]] = []
    for instance, _, child_class in sorted(
        graph.triples((None, RDF.type, None)),
        key=lambda triple: tuple(term.n3() for term in triple),
    ):
        for parent_class in sorted(
            _transitive_closure(subclasses, child_class),
            key=lambda term: term.n3(),
        ):
            triple = (instance, RDF.type, parent_class)
            if triple in graph or triple in inferred_graph:
                continue
            inferred_graph.add(triple)
            entailments.append(
                {
                    "kind": "rdfs_subclass_type",
                    "subject": str(instance),
                    "predicate": str(RDF.type),
                    "object": str(parent_class),
                    "source_class": str(child_class),
                    "rule": "rdfs:subClassOf",
                }
            )
    for subject, predicate, obj in sorted(
        graph.triples((None, None, None)),
        key=lambda triple: tuple(term.n3() for term in triple),
    ):
        for parent_property in sorted(
            _transitive_closure(subproperties, predicate),
            key=lambda term: term.n3(),
        ):
            triple = (subject, parent_property, obj)
            if triple in graph or triple in inferred_graph:
                continue
            inferred_graph.add(triple)
            entailments.append(
                {
                    "kind": "rdfs_subproperty_assertion",
                    "subject": str(subject),
                    "predicate": str(parent_property),
                    "object": str(obj),
                    "source_property": str(predicate),
                    "rule": "rdfs:subPropertyOf",
                }
            )
        if predicate in domains:
            inferred_type = (subject, RDF.type, domains[predicate])
            if inferred_type not in graph and inferred_type not in inferred_graph:
                inferred_graph.add(inferred_type)
                entailments.append(
                    {
                        "kind": "rdfs_domain_type",
                        "subject": str(subject),
                        "predicate": str(RDF.type),
                        "object": str(domains[predicate]),
                        "source_property": str(predicate),
                        "rule": "rdfs:domain",
                    }
                )
        if predicate in ranges and not isinstance(obj, Literal):
            inferred_type = (obj, RDF.type, ranges[predicate])
            if inferred_type not in graph and inferred_type not in inferred_graph:
                inferred_graph.add(inferred_type)
                entailments.append(
                    {
                        "kind": "rdfs_range_type",
                        "subject": str(obj),
                        "predicate": str(RDF.type),
                        "object": str(ranges[predicate]),
                        "source_property": str(predicate),
                        "rule": "rdfs:range",
                    }
                )

    _copy_labels(graph, inferred_graph)
    return entailments, _serialize_inferred_turtle(inferred_graph)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: dev_owl_reasoner.py <manifest.json>", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1])
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"cannot read manifest: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid manifest json: {exc}", file=sys.stderr)
        return 2

    tasks = list(manifest.get("tasks") or [])
    documents = list(manifest.get("documents") or [])
    try:
        source_graph = _read_source_graphs(documents)
        entailments, inferred_rdf = _infer_limited_rdfs(source_graph)
    except Exception as exc:
        print(f"cannot parse source documents: {exc}", file=sys.stderr)
        return 2

    payload = {
        "consistent": True,
        "classification": {
            "mode": "development_stub",
            "source_graph_count": len(documents),
        },
        "entailments": entailments,
        "inferred_rdf": inferred_rdf,
        "metadata": {
            "engine_name": "development_stub",
            "engine_version": "dev",
            "tasks": tasks,
            "warning": "Development stub only; no OWL DL reasoning was performed.",
        },
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
