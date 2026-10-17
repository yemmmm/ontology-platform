"""Repeated gate observations retain enforcement without repeated decisions."""
from types import SimpleNamespace

from modeling_team.runner import TeamRunner


def test_repeated_gate_fingerprint_keeps_gate_closed_but_emits_once():
    closed, evidence, feedback = [], [], []
    runner = SimpleNamespace(
        _candidate_platform_gate=SimpleNamespace(close=closed.append),
        _multi_slice_gate_feedback_fingerprints=set(),
        _append_evidence=lambda source, data: evidence.append((source, data)),
        _deliver_multi_slice_gate_feedback=lambda *args: feedback.append(args),
    )
    for _ in range(3):
        TeamRunner._multi_slice_gate_reject(
            runner, 'topology_missing_artifact', 'scenario-map/topology-decision.json',
            'topology_missing_artifact',
        )
    assert closed == ['topology_missing_artifact'] * 3
    assert len(evidence) == len(feedback) == 1
    TeamRunner._multi_slice_gate_reject(
        runner, 'map_unparsable', 'scenario-map/scenario-map.json', 'map-v2',
    )
    assert closed[-1] == 'map_unparsable'
    assert len(evidence) == len(feedback) == 2
