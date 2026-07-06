"""Phase 2 IRI mapping lookup helpers.

These functions translate legacy UUIDs (class_id, relation_type_id) to RDF IRIs
using the Phase 2 namespace mapping contract. If no mapping row exists, they
return None so callers can fall back to a deterministic IRI.
"""

from __future__ import annotations


def lookup_class_iri(session, ontology_id: str, class_id: str) -> str | None:
    """Return the RDF IRI for a class_id via Phase 2 mapping, or None."""
    # Phase 2 mapping table may not exist yet; return None to trigger fallback.
    # When the mapping table is populated, query it here.
    return None


def lookup_relation_type_iri(session, ontology_id: str, relation_type_id: str) -> str | None:
    """Return the RDF IRI for a relation_type_id via Phase 2 mapping, or None."""
    return None
