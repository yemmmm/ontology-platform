"""Stable identifiers and RDF-term normalization for R-005 lineage."""

from __future__ import annotations

import hashlib

from rdflib import Literal, URIRef
from rdflib.term import Identifier
from rdflib.util import from_n3

from app.services.fact_id import compute_fact_id


class InvalidLineageStatement(ValueError):
    pass


def canonical_iri(value: str) -> str:
    term = _parse_term(value, iri_default=True)
    if not isinstance(term, URIRef):
        raise InvalidLineageStatement(f"Expected RDF IRI, got: {value!r}")
    return str(term)


def canonical_object_ntriples(value: str) -> str:
    return _parse_term(value, iri_default=False).n3()


def normalize_quad(
    subject: str,
    predicate: str,
    obj: str,
    graph_iri: str,
) -> tuple[str, str, str, str]:
    return (
        canonical_iri(subject),
        canonical_iri(predicate),
        canonical_object_ntriples(obj),
        canonical_iri(graph_iri),
    )


def statement_id_for_quad(
    subject: str,
    predicate: str,
    obj: str,
    graph_iri: str,
) -> str:
    subject_iri, predicate_iri, object_ntriples, normalized_graph = normalize_quad(
        subject, predicate, obj, graph_iri
    )
    return compute_fact_id(
        subject_iri,
        predicate_iri,
        object_ntriples,
        normalized_graph,
    )


def occurrence_id_for(statement_id: str, graph_revision: int) -> str:
    if graph_revision < 0:
        raise ValueError("graph_revision must be non-negative")
    return hashlib.sha256(f"{statement_id}:{graph_revision}".encode("utf-8")).hexdigest()


def _parse_term(value: str, *, iri_default: bool) -> Identifier:
    if not isinstance(value, str) or not value.strip():
        raise InvalidLineageStatement("RDF term must be a non-empty string")
    text = value.strip()
    try:
        parsed = from_n3(text)
    except Exception:
        parsed = None
    if parsed is not None:
        return parsed
    if text.startswith(("http://", "https://", "urn:")):
        return URIRef(text)
    if iri_default:
        raise InvalidLineageStatement(f"Expected absolute RDF IRI, got: {value!r}")
    return Literal(text)


__all__ = [
    "InvalidLineageStatement",
    "canonical_iri",
    "canonical_object_ntriples",
    "normalize_quad",
    "occurrence_id_for",
    "statement_id_for_quad",
]
