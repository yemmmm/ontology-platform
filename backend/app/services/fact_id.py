"""Canonical fact_id computation (4-tuple sha256).

This is the authoritative fact_id algorithm for the ontology platform. Both
the read side (semantic_read_model) and the write side (semantic_command_compiler)
must call these functions so fact identifiers stay consistent across PG and RDF
boundaries.
"""
import hashlib


def canonical_object_term(
    value: str,
    *,
    is_iri: bool = False,
    datatype: str | None = None,
    lang: str | None = None,
) -> str:
    """Render an object value as an N-Triples term string.

    - IRI: ``<http://...>``
    - Plain literal: ``"value"``
    - Typed literal: ``"value"^^<datatype-iri>``
    - Lang-tagged literal: ``"value"@lang``
    """
    if is_iri:
        return f"<{value}>"
    if lang:
        return f'"{value}"@{lang}'
    if datatype:
        return f'"{value}"^^<{datatype}>'
    return f'"{value}"'


def compute_fact_id(
    subject_iri: str,
    predicate_iri: str,
    object_ntriples: str,
    graph_iri: str,
) -> str:
    """SHA-256 hex digest over the canonical N-Triples-style (s, p, o, g) tuple.

    The object term must already be N-Triples serialized (use
    :func:`canonical_object_term`). Including ``graph_iri`` in the hash means
    the same triple in two different graph_sets produces two distinct fact_ids
    — this is intentional.
    """
    canonical = f"<{subject_iri}> <{predicate_iri}> {object_ntriples} <{graph_iri}>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
