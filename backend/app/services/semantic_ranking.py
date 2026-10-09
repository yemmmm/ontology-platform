"""Versioned deterministic ranking of already authorized, deduplicated candidates."""
from __future__ import annotations

from typing import Any

RANKING_VERSION = 'evidence-rrf-v2'
RRF_OFFSET = 60


def rank_context_candidates(items: list[dict[str, Any]]) -> None:
    """Fuse lexical and semantic rank positions, without comparing their raw scales.

    Exact-expression evidence remains a separate priority in the public sorter.
    No candidate is dropped, and no score proves a business fact.
    """
    contributions = {id(item): 0.0 for item in items}
    for field in ('lexical_score', 'semantic_similarity'):
        qualified = [item for item in items if float(item['match'].get(field) or 0) > 0]
        qualified.sort(key=lambda item: (
            -float(item['match'][field]), item['ontology_id'], item['kind'], item['id'],
        ))
        last_value = None
        rank = 0
        for position, item in enumerate(qualified, 1):
            value = float(item['match'][field])
            if value != last_value:
                rank = position
                last_value = value
            contributions[id(item)] += 1 / (RRF_OFFSET + rank)
    for item in items:
        item['match']['rank_score'] = round(contributions[id(item)], 10)
        item['match']['ranking_version'] = RANKING_VERSION
