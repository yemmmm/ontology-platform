"""Offline comparison on fixed, public, authorized candidate packets.

Run: uv run python -m app.cli.compare_semantic_ranking public-candidates.json
No provider, database, or model calls. The same packet can later be scored by Jev.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import time
from pathlib import Path

from app.services.semantic_ranking import RANKING_VERSION, rank_context_candidates
from app.services.semantic_retrieval import EXACT_EVIDENCE_REASONS


def _exact(item, baseline=False):
    match = item.get('baseline_match', item['match']) if baseline else item['match']
    return bool(set(match.get('reasons', [])) & EXACT_EVIDENCE_REASONS)


def _tie(item):
    return item['ontology_id'], item['kind'], item.get('label', '').casefold(), item['id']


def _metrics(items, grades, k):
    ids = [item['id'] for item in items[:k]]
    relevant = {iri for iri, grade in grades.items() if grade > 0}
    dcg = sum((2 ** grades.get(iri, 0) - 1) / math.log2(i + 2) for i, iri in enumerate(ids))
    ideal = sum((2 ** grade - 1) / math.log2(i + 2)
                for i, grade in enumerate(sorted(grades.values(), reverse=True)[:k]))
    return {'recall': len(set(ids) & relevant) / len(relevant) if relevant else None,
            'ndcg': dcg / ideal if ideal else None,
            'required_entry_coverage': len(set(ids) & {iri for iri, grade in grades.items() if grade == 1})}


def compare(packet):
    if packet.get('visibility') != 'public':
        raise ValueError('Only an explicitly public evaluation packet is accepted')
    reports = []
    for case in packet['cases']:
        candidates = copy.deepcopy(case['candidates'])
        identities = [(item['ontology_id'], item['kind'], item['id']) for item in candidates]
        if len(set(identities)) != len(identities):
            raise ValueError('Candidate identities must already be deduplicated')
        start = time.perf_counter()
        old = sorted(candidates, key=lambda item: (
            not _exact(item, True),
            -max(float(item.get('baseline_match', item['match']).get('lexical_score') or 0),
                 float(item['match'].get('semantic_similarity') or 0) * 1000),
            _tie(item),
        ))
        baseline_seconds = time.perf_counter() - start
        start = time.perf_counter()
        rank_context_candidates(candidates)
        new = sorted(candidates, key=lambda item: (not _exact(item), -item['match']['rank_score'], _tie(item)))
        ranking_seconds = time.perf_counter() - start
        grades = case['relevance']  # human/business-owned relevance; never confidence
        if any(grade not in (0, 1, 2, 3) for grade in grades.values()):
            raise ValueError('Relevance grades must be 0..3 (1 includes necessary background/entry)')
        missing = sorted(set(grades) - {item['id'] for item in candidates})
        metrics = {str(k): {'baseline': _metrics(old, grades, k), 'candidate': _metrics(new, grades, k)}
                   for k in (5, 10)}
        reports.append({'question_id': case['question_id'], 'query': case['query'],
                        'candidate_count': len(candidates), 'not_recalled': missing,
                        'baseline_top10': [item['id'] for item in old[:10]],
                        'candidate_top10': [item['id'] for item in new[:10]],
                        'metrics': metrics, 'baseline_seconds': baseline_seconds,
                        'ranking_seconds': ranking_seconds,
                        'regression': any(metrics[str(k)]['candidate']['ndcg'] is not None and
                                          metrics[str(k)]['candidate']['ndcg'] < metrics[str(k)]['baseline']['ndcg']
                                          for k in (5, 10))})
    return {'ranking_version': RANKING_VERSION, 'cases': reports,
            'graded_cases': sum(bool(case['relevance']) for case in packet['cases']),
            'evaluation_status': 'evaluated' if all(case['relevance'] for case in packet['cases']) else 'pending_relevance',
            'regressions': sum(item['regression'] for item in reports),
            'consumer_coverage': 'not_measured', 'jev': 'pending_user_api_key',
            'evidence_scope': packet.get('evidence_scope', 'caller_supplied_public_candidates')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    raw = args.packet.read_bytes()
    result = compare(json.loads(raw))
    result['packet_sha256'] = hashlib.sha256(raw).hexdigest()
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    else:
        print(content, end='')


if __name__ == '__main__':
    main()
