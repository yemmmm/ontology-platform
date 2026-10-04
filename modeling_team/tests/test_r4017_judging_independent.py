"""Independent generic packet-to-native-Judge functional collection; explicit opt-in."""
from __future__ import annotations

import hashlib
import json
import os
from argparse import Namespace
from pathlib import Path

import pytest

from modeling_team import __main__ as cli
from modeling_team.acceptance_runtime import ReportSinkServer, V3BatchReportContract
from modeling_team.runtimes.codex import CodexRuntimeAdapter, _v3_acceptance_first_turn_text
from modeling_team.tests.test_r3011_acceptance import REPO_ROOT, _question
from modeling_team.tests.test_r3011_acceptance_runtime import _submit
from modeling_team.tests.test_r3012_platform_responses import (
    _Factory, _platform_context, _retained_receipt, _report, _write_handoff, _write_run_root,
)


@pytest.mark.skipif(os.environ.get("R4017_LIVE_JUDGE") != "1", reason="real generic Judge opt-in")
def test_independent_partial_batch_reaches_native_judge_and_preserves_evidence(
    monkeypatch, capsys,
):
    evidence = Path(os.environ["R4017_EVIDENCE_DIR"])
    evidence.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    questions = [_question(qid) for qid in ("oversize", "confirmed", "wrong", "unknown-fee")]
    for q in questions[:3]:
        q.update(question="仅收到预约请求回执，是否已确认并可派发？",
                 answer_points=["不能；确认须先获主管批准，确认后才可派发。"])
    questions[0]["answer_points"][0] += " " * 1_100_000 + " retained-overlimit-tail"
    questions[3].update(question="该预约改期费用为多少？",
                        answer_points=["费用尚未约定，应明确未知而非给出金额。"])
    run_root, frozen = _write_run_root(evidence, questions)
    # Whitespace size padding is explicitly a transport probe, not business content.
    source = ("确认预约必须先获主管批准；确认后方可派发；请求回执不等于确认。\n"
              + " " * 350_000 + "\n改期费用尚未约定。 retained-approved-source-tail\n")
    for role in ("coordinator", "modeling", "competency-question"):
        (run_root / "sources" / role / "scenario-brief").write_text(source)
    manifest_path = run_root / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sources"][0]["sha256"] = hashlib.sha256(source.encode()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    freeze_path = run_root / "competency-questions/frozen/freeze-0001.json"
    original_freeze = freeze_path.read_bytes()
    handoff = _write_handoff(evidence, frozen)
    pages = [
        {"ok": True, "matches": [{"iri": "urn:generic:Reservation",
          "semantics": "预约确认必须先获主管批准；回执不是确认；确认后可派发。"}],
         "matches_page": {"returned": 1, "truncated": True,
                          "next_match_cursor": "generic-page-two"}},
        {"ok": True, "matches": [{"iri": "urn:generic:Rescheduling",
          "semantics": "改期费用尚未约定。 retained-page-two-tail"}],
         "matches_page": {"returned": 1, "truncated": False, "next_match_cursor": None}},
    ]
    save("approved-pages.json", pages)
    observed = []
    sinks = []
    native_count = 0

    class Forwarder:
        def __init__(self):
            self.started = self.stopped = False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def forward(self, tool, arguments, key):
            assert key == "independent-read-key"
            if tool == "query_semantic_context":
                return pages[1 if arguments.get("match_cursor") else 0]
            return {"ok": True, "data": _platform_context()}

    forwarder = Forwarder()

    class ObservedAdapter(CodexRuntimeAdapter):
        def _write_child_private(self, path, payload, mode):
            super()._write_child_private(path, payload, mode)
            if path.name == "input.json":
                assert json.loads(payload) == observed[-1]["payload"]
                (evidence / f"native-input-{native_count}.json").write_bytes(payload)

        def run_v3_acceptance_child(self, packet, *, reports, **kwargs):
            nonlocal native_count
            if packet.role != "platform-examiner":
                native_count += 1
                observed.append(packet.to_dict())
                save(f"judge-packet-{native_count}.json", packet.to_dict())
                first = _v3_acceptance_first_turn_text(packet, kwargs["role_instructions"])
                (evidence / f"native-first-turn-{native_count}.txt").write_text(first)
                assert len(first) <= 1_048_576
                try:
                    return super().run_v3_acceptance_child(packet, reports=reports, **kwargs)
                finally:
                    save(f"judge-verdicts-{native_count}.json", reports)
                    save(f"judge-teardown-{native_count}.json", kwargs["teardown"])
            save("platform-packet.json", packet.to_dict())
            receipts = []
            for index, result in enumerate(pages):
                request = {"project_id": "project-1", "ontology_id": "ontology-1",
                           "graph_set_id": "graph-set-1", "query": "generic reservations"}
                if index:
                    request["match_cursor"] = "generic-page-two"
                receipt = _retained_receipt(run_root, request=request, result=result, ordinal=index,
                    page={"ordinal": index, "input_cursor": None if not index else "generic-page-two",
                          "output_cursor": "generic-page-two" if not index else None,
                          "has_more": not bool(index), "sequence_complete": bool(index)})
                receipts.append(receipt)
            kwargs["examiner_observables"].update(receipts=receipts, persistence_failures=0)
            # Controlled original Consumer outputs enter the real batch sink, not a verdict stub.
            sink = ReportSinkServer(evidence / "controlled-consumer.sock", "controlled-token",
                                    reports.append, kind="platform",
                                    batch_contract=V3BatchReportContract(role=packet.role, packet=packet))
            sinks.append(sink)
            sink.start()
            try:
                for q in questions:
                    report = _report(q["question_id"], ["p0", "p1"])
                    report["answer"] = (
                        "改期费用尚未约定，无法给出金额。" if q["question_id"] == "unknown-fee" else
                        "回执证明已确认，不需要批准，可立即派发。" if q["question_id"] == "wrong" else
                        "不能；主管批准才可确认，确认之后才可派发。"
                    )
                    assert _submit(sink.socket_path, report, token=sink.token)["ok"] is True
            finally:
                sink.stop()
                kwargs["teardown"].update(child_stopped=True, child_destroyed=True,
                    report_sink_stopped=True, proxy_stopped=True,
                    private_root_removed=True, socket_root_removed=True)
            save("controlled-consumer-reports.json", reports)
            return list(reports)

    monkeypatch.setattr(cli, "CodexRuntimeAdapter", ObservedAdapter)
    monkeypatch.setenv(cli._CQ_PLATFORM_READ_KEY_ENV, "independent-read-key")
    code = cli._run_cq_acceptance(Namespace(run_root=run_root, freeze_id="freeze-0001",
        model_handoff=handoff, model_profile="openai-sol-medium", session_timeout=600.0,
        unexecuted_report=False), REPO_ROOT, forwarder_factory=_Factory(forwarder))
    output = json.loads(capsys.readouterr().out)
    save("cli-output.json", output)
    report = json.loads(Path(output["report"]).read_text())
    save("retained-batch-report.json", report)
    assert freeze_path.read_bytes() == original_freeze
    assert forwarder.stopped
    assert all(s._thread is None or not s._thread.is_alive() for s in sinks)
    save("original-exit.json", {"code": code, "native_count": native_count})
    _verify_retained_chain(evidence)


def _verify_retained_chain(evidence):
    """Check original outputs without regenerating Consumer/Judge evidence."""
    run_root = evidence / "run"
    output = json.loads((evidence / "cli-output.json").read_text())
    report = json.loads((evidence / "retained-batch-report.json").read_text())
    source = (run_root / "sources/coordinator/scenario-brief").read_text()
    manifest = json.loads((run_root / "source-manifest.json").read_text())
    assert manifest["sources"][0]["sha256"] == hashlib.sha256(source.encode()).hexdigest()
    freeze_path = run_root / "competency-questions/frozen/freeze-0001.json"
    frozen = json.loads(freeze_path.read_text())
    assert frozen["snapshot_digest"] == report["freeze_digest"]
    assert report["executed_question_ids"] == sorted(["oversize", "confirmed", "wrong", "unknown-fee"])
    assert report["unexecuted_question_ids"] == []
    assert output["full_pass"] is report["full_pass"] is False
    sessions = report["sessions"]
    assert sessions["question_judging"]["skipped"] == {"oversize": "judge-input-too-large"}
    failure = sessions["acceptance_judge"]["input_failures"]["oversize"]
    assert failure["reason_code"] == "judge-input-too-large"
    assert failure["failure_layer"] == "runtime/infrastructure"
    assert failure["input_chars"] > failure["max_chars"]
    packet_paths = sorted(evidence.glob("judge-packet-*.json"))
    assert len(packet_paths) == 2
    observed = [json.loads(p.read_text()) for p in packet_paths]
    verdicts = {v["question_id"]: v for v in report["verdicts"]}
    assert set(verdicts) == {"confirmed", "wrong", "unknown-fee"}
    assert verdicts["confirmed"]["verdict"] == verdicts["unknown-fee"]["verdict"] == "pass"
    assert verdicts["wrong"]["verdict"] == "model-recall-insufficient"
    assert verdicts["wrong"]["failure_layer"] == "modeling-quality"
    assert "consumer" in str(verdicts["wrong"]["note"]).lower()
    assert [q["question_id"] for p in observed for q in p["payload"]["questions"]] == [
        "confirmed", "wrong", "unknown-fee"]
    pages = json.loads((evidence / "approved-pages.json").read_text())
    from modeling_team.acceptance_runtime import _packet_canonical
    for index, p in enumerate(observed, 1):
        payload = p["payload"]
        native_bytes = (evidence / f"native-input-{index}.json").read_bytes()
        assert native_bytes == _packet_canonical(payload)
        from modeling_team.acceptance_runtime import AcceptanceBatchPacket
        builder_input = json.loads(json.dumps(payload))
        builder_input["evidence_bundle"].pop("bundle_digest", None)
        rebuilt = AcceptanceBatchPacket.build("acceptance", builder_input)
        first = _v3_acceptance_first_turn_text(rebuilt, cli._CQ_JUDGE_ROLE_INSTRUCTIONS)
        assert first == (evidence / f"native-first-turn-{index}.txt").read_text()
        assert len(first) <= 1_048_576
        assert all(e["content"] == source for e in payload["evidence_bundle"]["entries"])
        for entries in payload["platform_read_responses"].values():
            assert [e["result"] for e in entries] == pages
            assert entries[0]["page"]["has_more"] is True
            assert entries[1]["page"]["sequence_complete"] is True
            for e in entries:
                document = json.loads((run_root / e["artifact_path"]).read_text())
                assert document["result"] == e["result"]
        assert "verdicts" not in payload
        teardown = json.loads((evidence / f"judge-teardown-{index}.json").read_text())
        assert teardown and all(v is True for v in teardown.values())
    assert sessions["cleanup"]["children_destroyed"] is True
    assert sessions["cleanup"]["forwarder_stopped"] is True
    assert len(report["examiner_reports"]) == 4
    (evidence / "retained-assertions.json").write_text(json.dumps({
        "full_denominator": 4, "valid_verdicts": 3, "oversized": 1,
        "approved_source_digest_valid": True, "page_bodies_unchanged": True,
        "actual_native_input_exact": True, "consumer_is_controlled": True,
        "judge_is_real_native": True, "production_starts": 0,
        "cleanup": sessions["cleanup"]}, indent=2))


@pytest.mark.skipif(os.environ.get("R4017_REPLAY_RETAINED") != "1", reason="retained evidence opt-in")
def test_retained_original_chain_contract():
    _verify_retained_chain(Path(os.environ["R4017_EVIDENCE_DIR"]))
