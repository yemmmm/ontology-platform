from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from m7_host import (  # noqa: E402
    SNAPSHOT_ROW_CEILING,
    AttemptLedger,
    HostError,
    _complete_rdf_snapshot,
    _seal_public_evidence_bundle,
    _seal_producer_evidence_boundary,
    _stage_judge,
    _write_json,
    abort_consumer,
    abort_judge,
    append_additional_read_evidence,
    complete_consumer,
    finalize_judge,
)
from m7_stable_hash import included_files, stable_scenario_hash  # noqa: E402


SCOPE = {"project_id": "project", "ontology_id": "ontology", "build_session_id": "session"}


class JudgeTransport:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, truncated: bool = False,
                 partial: bool = False, stale: bool = False, foreign_scope: bool = False,
                 missing_graph_set: bool = False, mismatched_graph_set: bool = False,
                 cleanup_success: bool = True) -> None:
        self.rows = rows if rows is not None else [
            {"s": {"type": "uri", "value": "https://m7.test/s"},
             "p": {"type": "uri", "value": "https://m7.test/p"},
             "o": {"type": "literal", "value": "complete"}}
        ]
        self.truncated, self.partial, self.stale = truncated, partial, stale
        self.foreign_scope, self.missing_graph_set = foreign_scope, missing_graph_set
        self.mismatched_graph_set, self.cleanup_success = mismatched_graph_set, cleanup_success
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, path, body))
        if method == "DELETE":
            return {"status": 204 if self.cleanup_success else 500, "body": {}}
        assert (method, path) == ("POST", "/api/semantic/sparql:query")
        assert body and body["scope_mode"] == "ontologies" and body["ontology_ids"] == ["ontology"]
        ontology_id = "other" if self.foreign_scope else "ontology"
        derived_state = {} if self.missing_graph_set else {"graph_set_id": "other-set" if self.mismatched_graph_set else "set"}
        scope = {
            "status": "partial" if self.partial else "complete",
            "ontologies": [{"ontology_id": ontology_id, "workspace_version": "1", "source_signature": "stale" if self.stale else "sig", "derived_state": derived_state}],
            "excluded_ontologies": [{"ontology_id": "other"}] if self.partial else [],
        }
        warnings = [{"code": "source_signature_stale"}] if self.stale else []
        return {"status": 200, "body": {"result": {"bindings": self.rows}, "scope": scope, "truncated": self.truncated, "warnings": warnings}}


def _producer() -> dict[str, Any]:
    verification = {
        "scope": {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "set"},
        "validation": {"run_id": "validation", "conforms": True, "source_signature": "sig"},
        "reasoning": {"run_id": "reasoning", "consistent": True, "source_signature": "sig"},
    }
    return {
        "principal_dry_run": {"client_batch_id": "dry"},
        "principal_apply": {"client_batch_id": "apply"},
        "producer_claim_query_evidence": {"producer-claim": {"result": {"boolean": True}, "query_sha256": "hint"}},
        "verification": verification,
    }


def _awaiting_judge(tmp_path: Path, transport: JudgeTransport, run_id: str = "judge-run") -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "run"
    root.mkdir(parents=True)
    state_path = root / "host-only-state.json"
    state: dict[str, Any] = {
        "state_version": 1,
        "status": "PREPARED",
        "run_id": run_id,
        "scope": SCOPE,
        "workspace": {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "set"},
        "base_dry_run": {"client_batch_id": "base"},
        "run_manifest_sha256": "run-manifest",
    }
    bundle = _seal_public_evidence_bundle(
        transport, root=root, state=state, semantic_package={"producer": "untrusted"}, producer=_producer()
    )
    state.update({
        "status": "PRODUCER_EVIDENCE_SEALED",
        "public_evidence": bundle,
        "producer_evidence_boundary": _seal_producer_evidence_boundary(state, bundle),
    })
    state["judge"] = _stage_judge(root, state, bundle)
    state["status"] = "AWAITING_JUDGE"
    _write_json(state_path, state)
    return state_path, state


def _citation(state: dict[str, Any]) -> dict[str, str]:
    manifest = json.loads((Path(state["public_evidence"]["directory"]) / "evidence-manifest.json").read_text())
    item = next(entry for entry in manifest["files"] if entry["id"].endswith(":snapshot"))
    return {"evidence_id": item["id"], "sha256": item["sha256"]}


def _verdict(state: dict[str, Any], status: str = "PASS", citation: dict[str, str] | None = None) -> dict[str, Any]:
    acceptance = json.loads((SCENARIO_ROOT / "host-only" / "acceptance-contract.json").read_text())
    ids = [*acceptance["capability_questions"], *acceptance["required_regressions"]]
    return {
        "schema_version": 1,
        "run_id": state["run_id"],
        "scope": state["scope"],
        "source_signature": state["public_evidence"]["source_signature"],
        "answers": [{
            "cq_id": cq_id,
            "status": status,
            "conclusion": f"Judge conclusion for {cq_id}",
            "missing_or_contradictory_evidence": [],
            "failure_classification": None if status == "PASS" else "evidence-insufficient",
            "citations": [citation or _citation(state)],
        } for cq_id in ids],
        "additional_evidence_hashes": [],
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"truncated": True}, "truncated or stale"),
        ({"partial": True}, "incomplete"),
        ({"stale": True}, "truncated or stale"),
        ({"foreign_scope": True}, "different Ontology"),
        ({"missing_graph_set": True}, "graph-set receipt is missing"),
        ({"mismatched_graph_set": True}, "graph-set drift"),
        ({"rows": [{"s": {"type": "uri", "value": "x"}}] * SNAPSHOT_ROW_CEILING}, "ceiling"),
        ({"rows": [{"s": {"type": "uri", "value": "x"}}] * (SNAPSHOT_ROW_CEILING + 1)}, "ceiling"),
    ],
)
def test_m7_31_snapshot_fails_closed_for_incomplete_or_unbounded_modes(kwargs: dict[str, Any], message: str) -> None:
    expected = {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "set"}
    with pytest.raises(HostError, match=message):
        _complete_rdf_snapshot(JudgeTransport(**kwargs), SCOPE, expected)


def test_m7_31_m7_32_seals_complete_snapshot_and_isolates_judge_staging(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    assert state["public_evidence"]["row_count"] == 1 < state["public_evidence"]["ceiling"]
    stage = Path(state["judge"]["directory"])
    assert (stage / "answer-contract-v1.json").is_file() and (stage / "acceptance-contract.json").is_file()
    assert (stage / "public-sources" / "business-fixture.md").is_file()
    assert json.loads((stage / "public-source-manifest.json").read_text())["files"]
    assert not (stage / "semantic-package.json").exists()
    assert not (stage / "host-evidence.json").exists() and not (stage / "agent-visible").exists()
    assert json.loads(state_path.read_text())["status"] == "AWAITING_JUDGE"


def test_m7_32_rejects_prepared_state_even_with_a_complete_public_bundle(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    root.mkdir()
    state = {
        "status": "PREPARED", "run_id": "prepared-run", "scope": SCOPE,
        "workspace": {"workspace_version": "1", "source_signature": "sig", "graph_set_id": "set"},
        "base_dry_run": {"client_batch_id": "base"}, "run_manifest_sha256": "run-manifest",
    }
    bundle = _seal_public_evidence_bundle(JudgeTransport(), root=root, state=state, semantic_package={}, producer=_producer())
    with pytest.raises(HostError, match="sealed Producer evidence boundary"):
        _stage_judge(root, state, bundle)


@pytest.mark.parametrize(
    "fixture_value, judge_status, expected_state",
    [("complete", "PASS", "AWAITING_L2_CONSUMER"), ("missing", "FAIL", "FAILED"), ("contradictory", "INCONCLUSIVE", "FAILED")],
)
def test_m7_33_judge_semantic_fixture_is_external_and_producer_claim_is_not_authority(
    tmp_path: Path, fixture_value: str, judge_status: str, expected_state: str
) -> None:
    rows = [{"s": {"type": "uri", "value": "https://m7.test/s"}, "p": {"type": "uri", "value": "https://m7.test/p"}, "o": {"type": "literal", "value": fixture_value}}]
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport(rows=rows))
    # The Host does not infer a semantic verdict from the fixture literal or Producer's true claim hint.
    result = finalize_judge(
        JudgeTransport(), state_path=state_path, verdict=_verdict(state, judge_status),
        adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True,
    )
    assert result["status"] == expected_state
    persisted = json.loads(state_path.read_text())
    assert persisted["judge_semantic_outcome"] == judge_status
    assert persisted["judge_verdict"]["answers"][0]["conclusion"]
    assert persisted["judge_verdict"]["answers"][0]["citations"]


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("conclusion", "", "conclusion"),
        ("missing_or_contradictory_evidence", [1], "evidence notes"),
        ("failure_classification", "runtime-infrastructure", "PASS Judge"),
    ],
)
def test_judge_verdict_semantic_fields_are_required_mechanically(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    verdict = _verdict(state)
    verdict["answers"][0][field] = value
    with pytest.raises(HostError, match=message):
        finalize_judge(JudgeTransport(), state_path=state_path, verdict=verdict, adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True)


def test_non_pass_judge_answer_requires_an_allowed_failure_classification(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    verdict = _verdict(state, "FAIL")
    verdict["answers"][0]["failure_classification"] = None
    with pytest.raises(HostError, match="non-PASS"):
        finalize_judge(JudgeTransport(), state_path=state_path, verdict=verdict, adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True)


def test_m7_34_invented_stale_and_cross_run_citations_fail_and_clean(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    bad = _verdict(state, citation={"evidence_id": "snapshot", "sha256": "invented"})
    with pytest.raises(HostError, match="citation"):
        finalize_judge(JudgeTransport(), state_path=state_path, verdict=bad, adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True)
    assert json.loads(state_path.read_text())["status"] == "FAILED"
    second_path, second_state = _awaiting_judge(tmp_path / "other", JudgeTransport(), run_id="other-run")
    cross = _verdict(second_state, citation=_citation(state))
    with pytest.raises(HostError, match="citation"):
        finalize_judge(JudgeTransport(), state_path=second_path, verdict=cross, adjudication={"run_id": second_state["run_id"], "decision": "accept"}, execute_guarded=True)


def test_m7_35_allowlisted_additional_read_is_append_only_and_rejects_injection_or_staleness(tmp_path: Path) -> None:
    state_path, _state = _awaiting_judge(tmp_path, JudgeTransport())
    with pytest.raises(HostError, match="only an allowlisted"):
        append_additional_read_evidence(JudgeTransport(), state_path=state_path, request_contract={"query": "DELETE WHERE {}"}, execute_guarded=True)
    with pytest.raises(HostError, match="not allowlisted"):
        append_additional_read_evidence(JudgeTransport(), state_path=state_path, request_contract={"query_id": "SERVICE <x>"}, execute_guarded=True)
    with pytest.raises(HostError, match="only an allowlisted"):
        append_additional_read_evidence(JudgeTransport(), state_path=state_path, request_contract={"query_id": "triple-exists", "ontology_ids": ["other"]}, execute_guarded=True)
    first = append_additional_read_evidence(JudgeTransport(), state_path=state_path, request_contract={"query_id": "triple-exists"}, execute_guarded=True)
    second = append_additional_read_evidence(JudgeTransport(), state_path=state_path, request_contract={"query_id": "rdf-snapshot"}, execute_guarded=True)
    assert first["id"] != second["id"]
    with pytest.raises(HostError, match="stale"):
        append_additional_read_evidence(JudgeTransport(stale=True), state_path=state_path, request_contract={"query_id": "triple-exists"}, execute_guarded=True)
    with pytest.raises(HostError, match="different Ontology"):
        append_additional_read_evidence(JudgeTransport(foreign_scope=True), state_path=state_path, request_contract={"query_id": "triple-exists"}, execute_guarded=True)


def test_m7_36_m7_37_pass_then_read_only_consumer_completion_and_abort_idempotency(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    finalized = finalize_judge(JudgeTransport(), state_path=state_path, verdict=_verdict(state), adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True)
    assert finalized["status"] == "AWAITING_L2_CONSUMER"
    consumer_stage = Path(finalized["consumer"]["directory"])
    assert not (consumer_stage / "answer-contract-v1.json").exists()
    consumer = {"schema_version": 1, "run_id": state["run_id"], "scope": SCOPE, "source_signature": state["public_evidence"]["source_signature"], "read_only": True, "citations": [_citation(state)]}
    completed = complete_consumer(JudgeTransport(), state_path=state_path, result=consumer, execute_guarded=True)
    assert completed["status"] == "CLEANED"
    assert complete_consumer(JudgeTransport(), state_path=state_path, result=consumer, execute_guarded=True) == completed
    assert abort_consumer(JudgeTransport(), state_path=state_path, reason="timeout", execute_guarded=True) == completed


def test_m7_37_invalid_consumer_result_cleans_retained_scope(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    finalize_judge(JudgeTransport(), state_path=state_path, verdict=_verdict(state), adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True)
    with pytest.raises(HostError, match="Consumer result"):
        complete_consumer(JudgeTransport(), state_path=state_path, result={"run_id": state["run_id"]}, execute_guarded=True)
    assert json.loads(state_path.read_text())["status"] == "FAILED"
    assert complete_consumer(JudgeTransport(), state_path=state_path, result={"run_id": state["run_id"]}, execute_guarded=True)["status"] == "FAILED"


def test_m7_36_abort_judge_preserves_inconclusive_cause_and_cleanup_failure(tmp_path: Path) -> None:
    state_path, _state = _awaiting_judge(tmp_path, JudgeTransport())
    receipt = abort_judge(JudgeTransport(cleanup_success=False), state_path=state_path, reason="timeout", execute_guarded=True)
    assert receipt["status"] == "CLEANUP_FAILED" and receipt["primary_cause"] == "judge_inconclusive:timeout"
    assert receipt["judge_no_verdict"]["no_verdict"] is True and receipt["judge_semantic_outcome"] == "INCONCLUSIVE"
    assert abort_judge(JudgeTransport(), state_path=state_path, reason="ignored", execute_guarded=True) == receipt


def test_valid_fail_verdict_survives_cleanup_failure_with_its_citations(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    receipt = finalize_judge(
        JudgeTransport(cleanup_success=False), state_path=state_path, verdict=_verdict(state, "FAIL"),
        adjudication={"run_id": state["run_id"], "decision": "accept"}, execute_guarded=True,
    )
    persisted = json.loads(state_path.read_text())
    assert receipt["status"] == "CLEANUP_FAILED" and receipt["judge_semantic_outcome"] == "FAIL"
    assert persisted["judge_verdict"]["answers"][0]["citations"]


def test_stable_hash_has_one_documented_exclusion_and_sorted_file_algorithm(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.txt").write_text("b")
    before = stable_scenario_hash(tmp_path)
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "mutable.json").write_text("runtime")
    (tmp_path / "attempts.jsonl").write_text("ledger")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.pyc").write_text("cache")
    assert stable_scenario_hash(tmp_path) == before
    assert [item.as_posix() for item in included_files(tmp_path)] == ["a.txt", "nested/b.txt"]
    (tmp_path / "a.txt").write_text("changed")
    assert stable_scenario_hash(tmp_path) != before


def test_main_accepted_l1_pass_can_append_the_paired_recovery_authorization(tmp_path: Path) -> None:
    state_path, state = _awaiting_judge(tmp_path, JudgeTransport())
    ledger = AttemptLedger(tmp_path / "recovery-ledger.jsonl")
    ledger.append_modeling_started({
        "event": "modeling_started", "run_id": state["run_id"], "agent_id": "agent-judge",
        "fork_turns": "none", "input_manifest_sha256": "input", "base_manifest_sha256": "base",
        "contract_version": json.loads((SCENARIO_ROOT / "host-only" / "acceptance-contract.json").read_text())["contract_version"],
    })
    finalized = finalize_judge(
        JudgeTransport(), state_path=state_path, verdict=_verdict(state),
        adjudication={"run_id": state["run_id"], "decision": "accept"}, attempt_ledger=ledger,
        execute_guarded=True,
    )
    assert finalized["status"] == "AWAITING_L2_CONSUMER"
    assert ledger.events()[-1]["event"] == "l1_pass_authorized"
