"""R4.0-013 contracts and opt-in real Judge collection.

The live test collects raw model verdicts. Semantic validation is independent
human comparison in the shared test record, never a script predicting note text.
All packet facts are synthetic and public functional fixtures, not business runs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from modeling_team.__main__ import _CQ_JUDGE_ROLE_INSTRUCTIONS
from modeling_team.acceptance_runtime import build_acceptance_judge_packet
from modeling_team.competency_questions import (
    CQ_BATCH_REPORT_SCHEMA,
    CQContractError,
    batch_report_is_full_pass,
    build_batch_report,
    content_digest,
    public_projection,
    review_decision_digest,
)
from modeling_team.contracts import repository_root
from modeling_team.model_routing import load_team_model_profile
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.tests.test_r3011_acceptance import _freeze, _platform_packet, _question
from modeling_team.tests.test_r3011_runner_wiring import (
    _draft,
    _review_payload,
    _question as cq_question,
)

from modeling_team.tests import test_r3011_runner_wiring as cq_fixtures

# Reuse the existing isolated synthetic runner fixture.
cq_runner = cq_fixtures.cq_runner
ROOT = repository_root()
BATCH = "r4013-controlled-functional"


def test_private_review_note_round_trip_and_recoverable_version(cq_runner):
    note = (
        "Q-01 / answer_points[1]: 保留，source-X §1 说明受理不等于完成，题干直接询问完成。\n"
        "Q-01 / answer_points[2]: 移出，平台不执行 API 有依据但超出本题意，专项题继续覆盖。\n"
        "Q-02 / answer_points[1]: 修改，source-X 未约定两天退款，不能以猜测评分。\n"
        "Q-03 / answer_points[1]: 保留，审批是退款成立的必要隐含条件，遗漏改变业务判断。"
    )
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([cq_question("Q-01")])}
    )
    with pytest.raises(CQContractError) as error:
        cq_runner.handle_cq_outer_input(_review_payload(cq_runner, content_version=99, note=note))
    assert error.value.data["reason_code"] == "cq_review_stale"
    decision = _review_payload(cq_runner, note=note)
    cq_runner.handle_cq_outer_input(decision)
    record = json.loads(
        (cq_runner.run.root / "competency-questions/reviews/decision-0001.json").read_text()
    )
    assert record["decision"]["note"] == note
    assert record["decision_digest"] == content_digest(record["decision"])
    assert review_decision_digest(record["decision"]) == review_decision_digest(
        dict(record["decision"], note="different private explanation")
    )
    assert note not in json.dumps(cq_runner._cq_public_projection(), ensure_ascii=False)


def test_formal_review_modification_is_not_a_note_override(cq_runner):
    original = cq_question("Q-01")
    original["answer_points"] = ["受理不等于完成", "平台不执行 API"]
    cq_runner._publish_cq_question_draft(
        {"cq_id": "competency-question", "draft": _draft([original])}
    )
    replacement = dict(original, answer_points=["受理不等于完成"], content_version=2)
    note = "Q-01 / 原必答点 2：移出本题评分；执行主体在已批准专项范围检查。"
    cq_runner.handle_cq_outer_input(
        _review_payload(cq_runner, decision="modify", modified_question=replacement, note=note)
    )
    record = json.loads(
        (cq_runner.run.root / "competency-questions/reviews/decision-0001.json").read_text()
    )
    assert record["decision"]["modified_question"] == replacement
    projection = cq_runner._cq_public_projection()
    assert projection["questions"][0]["answer_points"] == ["受理不等于完成"]
    assert projection["questions"][0]["review_content_version"] == 2
    assert note not in json.dumps(projection, ensure_ascii=False)


def test_hidden_review_and_diagnostics_stay_outside_consumer_packet():
    questions = [_question("Q-01"), _question("Q-private")]
    frozen = _freeze(questions)
    frozen["note"] = "private grading rationale"
    assert public_projection(frozen)["questions"] == []
    packet = _platform_packet(freeze=questions).to_dict()["payload"]
    assert set(packet["questions"][0]) == {"question_id", "content_version", "question", "scope"}
    assert not ({"evidence_bundle", "platform_read_responses", "verdicts", "note"} & set(packet))
    assert "private grading rationale" not in json.dumps(packet)


def test_active_v3_assets_and_actual_judge_first_turn_are_loaded():
    _, instructions, skill = CodexRuntimeAdapter._child_package_assets("acceptance", ROOT, v3_batch=True)
    assert instructions == ROOT / "modeling_team/agent-packages/v3-acceptance-batch/acceptance-judge.md"
    assert skill.is_file()
    packet = controlled_judge_packet()
    captured = {}

    def inspect(spec):
        captured.update(spec)
        raise RuntimeError("intentional inspection before launching any process")

    adapter = CodexRuntimeAdapter(repository_root=ROOT, acceptance_child_factory=inspect)
    with pytest.raises(RuntimeError, match="intentional inspection"):
        adapter.launch_v3_acceptance_child(packet, role_instructions=_CQ_JUDGE_ROLE_INSTRUCTIONS, reports=[])
    assert _CQ_JUDGE_ROLE_INSTRUCTIONS in captured["first_turn_input"][0]["text"]
    assert captured["allowed_read_tools"] == []
    assert captured["platform_forwarder"] is None
    assert captured["read_key_plaintext"] is None
    assert not Path(captured["private_root"]).exists()


def test_multicause_note_is_preserved_without_duplicate_question_count():
    packet = controlled_judge_packet().to_dict()["payload"]
    question = packet["questions"][7]
    examiner = packet["examiner_reports"][7]
    note = "点1 Consumer 误解；点2 模型含义冲突；点3 原因未确定，投影不足。"
    verdict = {
        "schema_version": CQ_BATCH_REPORT_SCHEMA, "batch_id": BATCH,
        "question_id": question["question_id"], "verdict": "model-recall-insufficient",
        "failure_layer": "modeling-quality", "conflicting_evidence": [], "note": note,
    }
    report = build_batch_report(
        run_id="r4013-functional-only", batch_id=BATCH, freeze_digest=packet["freeze_digest"],
        model_binding_digest=packet["model_binding_digest"], hidden_questions=[question],
        examiner_reports=[examiner], verdicts=[verdict],
        executed_question_ids=[question["question_id"]], unexecuted_question_ids=[],
    )
    assert report["verdicts"][0]["note"] == note
    assert report["summary_by_scope"]["panorama"]["model-recall-insufficient"] == 1
    assert not batch_report_is_full_pass(report)


@pytest.mark.parametrize("verdict_state", ["question-answer-review", None])
def test_review_or_missing_verdict_keeps_full_denominator(verdict_state):
    payload = controlled_judge_packet().to_dict()["payload"]
    question, examiner = payload["questions"][5], payload["examiner_reports"][5]
    verdicts = [] if verdict_state is None else [{
        "schema_version": CQ_BATCH_REPORT_SCHEMA, "batch_id": BATCH,
        "question_id": question["question_id"], "verdict": verdict_state,
        "failure_layer": None, "conflicting_evidence": [], "note": "附加评分点待复核",
    }]
    report = build_batch_report(
        run_id="r4013-functional-only", batch_id=BATCH, freeze_digest=payload["freeze_digest"],
        model_binding_digest=payload["model_binding_digest"], hidden_questions=[question],
        examiner_reports=[examiner], verdicts=verdicts,
        executed_question_ids=[question["question_id"]], unexecuted_question_ids=[],
    )
    assert report["executed_question_ids"] == [question["question_id"]]
    assert not batch_report_is_full_pass(report)


def controlled_judge_packet(*, without_corroboration: bool = False):
    """Synthetic retained facts; no expected verdict/diagnosis is in the packet."""
    acceptance = "202 仅表示受理，不能证明关闭完成；完成须另有 closed=true 的业务成功结果。本体平台不执行外部 API。"
    empty = {"status": "no_match", "completeness": "complete", "matches": []}
    correct = {"status": "ok", "iri": "urn:fixture:Closing", "semantics": acceptance}
    cases = [
        ("收到 202 能否证明工单已关闭？", ["202 只表示受理，不证明完成；须业务成功结果。"], acceptance,
         "202 已证明关闭完成。", [correct]),
        ("收到 202 能否证明工单已关闭？", ["202 只表示受理，不证明完成；须业务成功结果。"], acceptance,
         "202 已证明关闭完成。", [{"status": "ok", "iri": "urn:fixture:Closing", "semantics": "202 表示关闭已完成。"}]),
        ("退款执行有什么前提？", ["执行退款前须主管批准。"], "退款执行必须先获主管批准。",
         "模型未列出前提，不能确认。", [{"status": "ok", "entity": {"iri": "urn:fixture:Refund", "definition": "退款执行", "rules": []},
          "enumeration": {"scope": "urn:fixture:Refund 的全部直接规则、前提和限制表达", "closed_scope": True, "complete": True, "has_more": False, "included_expression_kinds": ["Rule", "Policy", "Constraint", "precondition"], "omitted_fields": []}}]),
        ("只收到 202 能否确认工单关闭？", ["不能，202 只表示受理。"], acceptance,
         "没有查到资料，无法回答。", [empty]),
        ("蓝色方案的 SLA 是多少？", ["获准资料未定义 SLA，应明确未知。"], "蓝色方案的 SLA 尚未定义，不能给出时限。",
         "SLA 尚未定义，无法给出时限。", [{"status": "ok", "iri": "urn:fixture:Blue", "sla_status": "unknown", "semantics": "蓝色方案 SLA 尚未定义。"}]),
        ("收到 202 能否证明工单已关闭？", ["202 仅受理；还须业务成功结果。", "本体平台不执行外部 API。"], acceptance,
         "不能，202 仅表示受理；须检查 closed=true 的业务成功结果。", [correct]),
        ("退款多久完成？", ["退款在两天内完成。"], "退款完成时限尚未决定。",
         "时限尚未决定，无法承诺。", [{"status": "ok", "iri": "urn:fixture:Refund", "semantics": "时限尚未决定。"}]),
        ("说明受理是否完成、退款审批前提、记录保留期限。", ["受理不等于完成。", "退款须主管批准。", "记录保留期限为七年。"],
         "受理不等于完成；退款须主管批准；记录保留七年。", "受理就是完成；退款无需批准；保留期限未查到。",
         [{"status": "ok", "iri": "urn:fixture:Multi", "acceptance": "受理不等于完成", "refund": "退款无需主管批准", "projection": {"omitted": ["retention"], "completeness": "partial"}}]),
        ("紫色任务已受理能否视为完成？", ["不能，受理不等于完成。"], "紫色任务 accepted 只表示受理，不等于 completed。",
         "查不到相关内容，无法判断。", [empty]),
        ("紫色任务中 accepted 表示什么？", ["仅受理，不等于 completed。"], "紫色任务 accepted 只表示受理，不等于 completed。",
         "accepted 仅表示受理，不等于 completed。", [{"status": "ok", "iri": "urn:fixture:Purple", "semantics": "紫色任务 accepted 仅受理，不等于 completed。"}]),
        ("金色任务已受理能否视为完成？", ["不能，受理不等于完成。"], "金色任务 accepted 只表示受理，不等于 completed。",
         "查不到相关内容，无法判断。", [empty]),
        ("收到 202 能否确认工单关闭？", ["不能，202 只表示受理。"], acceptance,
         "最后查询没结果，无法判断。", [correct, empty]),
        ("收到 202 能否确认工单关闭？", ["不能，202 只表示受理。"], acceptance,
         "连接失败，无法完成读取。", [{"status": "error", "error": "runtime connection refused"}]),
        ("没有读取蓝色私有任务的权限时能否声称已确认其完成？", ["不能；遵守拒绝，保留无法确认。"], "权限不足必须遵守拒绝，不得声称读取私有任务结果。",
         "读取被拒，无法确认完成。", [{"status": "forbidden", "reason": "read denied", "semantics": "禁止披露受保护任务；没有权限时不能确认其结果。"}]),
        ("退款执行是否须主管批准？", ["须主管批准。"], "退款执行必须先获主管批准。",
         "须主管批准。", [{"status": "ok", "iri": "urn:fixture:Refund", "label": "退款", "projection": {"completeness": "partial", "omitted": ["precondition"]}}]),
        ("收到 202 能否确认工单关闭？", ["不能，202 只表示受理。"], acceptance,
         "不能确认，202 仅受理；本体平台会直接执行外部 API 完成关闭。", [correct]),
    ]
    questions, entries, reports, responses = [], [], [], {}
    for number, (text, points, source, answer, results) in enumerate(cases, 1):
        question_id = f"Q-{number:02d}"
        locator = f"fixture section {number}"
        questions.append({
            "question_id": question_id, "content_version": 1, "question": text,
            "answer_points": points, "evidence_refs": [{"source": "synthetic-approved-brief", "locator": locator}],
            "unknown": [], "scope": {"kind": "panorama", "slice_ids": []},
        })
        entries.append({
            "question_id": question_id, "source": "synthetic-approved-brief", "locator": locator,
            "content": source, "content_digest": content_digest(source), "review_content_version": 1,
        })
        projections, refs = [], []
        for page, result in enumerate(results):
            digest = content_digest({"question_id": question_id, "page": page, "result": result})
            refs.append(digest)
            projections.append({
                "tool": "get_entity_statement_context" if number == 3 else "query_semantic_context",
                "request_digest": content_digest({"question_id": question_id, "page": page}),
                "response_digest": digest,
                "artifact_path": f"acceptance/r4013-controlled/platform-read/{question_id}/{page}.json",
                "page": {"page": page, "has_more": False}, "result": result,
            })
        responses[question_id] = projections
        reports.append({
            "schema_version": CQ_BATCH_REPORT_SCHEMA, "batch_id": BATCH,
            "question_id": question_id, "question_content_version": 1,
            "answer": answer, "evidence_refs": refs,
            "explicit_unknown": ["SLA 尚未定义"] if number == 5 else [],
            "status": "runtime-incomplete" if number == 13 else "completed",
            "failure_layer": "runtime/infrastructure" if number == 13 else None,
            "reason": "runtime connection refused" if number == 13 else None,
        })
    if without_corroboration:
        questions = [item for item in questions if item["question_id"] == "Q-09"]
        entries = [item for item in entries if item["question_id"] == "Q-09"]
        reports = [item for item in reports if item["question_id"] == "Q-09"]
        responses = {"Q-09": responses["Q-09"]}
    return build_acceptance_judge_packet(
        run_id="r4013-functional-only-no-production-run", batch_id=BATCH,
        freeze_digest=content_digest(questions), questions=questions,
        model_binding_digest=content_digest("synthetic single model state"),
        evidence_bundle={"schema_version": "r3-0-011-acceptance-evidence/v1", "batch_id": BATCH,
                         "freeze_digest": content_digest(questions), "entries": entries},
        examiner_reports=reports, platform_read_responses=responses,
        verdict_schema={"schema_version": CQ_BATCH_REPORT_SCHEMA},
    )


@pytest.mark.skipif(os.environ.get("R4013_LIVE_JUDGE") != "1", reason="explicit real-model opt-in")
def test_real_judge_raw_verdict_collection():
    variant = os.environ.get("R4013_LIVE_CASE", "full")
    assert variant in {"full", "without-corroboration"}
    packet = controlled_judge_packet(without_corroboration=variant == "without-corroboration")
    evidence_root = Path(os.environ.get("R4013_EVIDENCE_DIR", ROOT / "workspaces/r4013-functional-tests/round-1"))
    evidence_root.mkdir(parents=True, exist_ok=False)
    (evidence_root / "packet.json").write_text(json.dumps(packet.to_dict(), ensure_ascii=False, indent=2))
    _, active, skill = CodexRuntimeAdapter._child_package_assets("acceptance", ROOT, v3_batch=True)
    (evidence_root / "prompt-snapshot.json").write_text(json.dumps({
        "active_path": str(active.relative_to(ROOT)), "active_text": active.read_text(),
        "role_instructions": _CQ_JUDGE_ROLE_INSTRUCTIONS, "skill_text": skill.read_text(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "proxy_presence": {key: bool(os.environ.get(key)) for key in ("http_proxy", "https_proxy", "no_proxy")},
    }, ensure_ascii=False, indent=2))
    adapter = CodexRuntimeAdapter(repository_root=ROOT)
    adapter.bind_acceptance_model_profile(load_team_model_profile(ROOT, "openai-sol-medium"))
    reports, teardown = [], {}
    try:
        returned = adapter.run_v3_acceptance_child(
            packet, role_instructions=_CQ_JUDGE_ROLE_INSTRUCTIONS,
            reports=reports, timeout_seconds=600, teardown=teardown,
        )
        expected = [entry["question_id"] for entry in packet.to_dict()["payload"]["questions"]]
        assert [entry["question_id"] for entry in returned] == expected
    except Exception as exc:
        (evidence_root / "error.txt").write_text(f"{type(exc).__name__}: {exc}")
        if callable(getattr(exc, "as_dict", None)):
            (evidence_root / "blocked.json").write_text(json.dumps(exc.as_dict(), ensure_ascii=False, indent=2))
        raise
    finally:
        (evidence_root / "verdicts.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
        (evidence_root / "teardown.json").write_text(json.dumps(teardown, ensure_ascii=False, indent=2))
        (evidence_root / "runtime-failures.json").write_text(json.dumps(adapter.consume_runtime_failures(), ensure_ascii=False, indent=2))


def controlled_cq_authoring_inputs():
    """Approved generic material only; no predicted draft, review or verdict.

    The independent tester mounts these bytes as a normal approved source and
    runs the actual CQ role before independently reviewing the resulting draft.
    This factory does not decide which points should appear in any question.
    """
    return {
        "source_name": "service-reservation-policy.md",
        "source_content": (
            "# Service reservation policy\n"
            "## 1 Reservation and dispatch\n"
            "A reservation becomes confirmed only after a supervisor approves the slot.\n"
            "A confirmed reservation can enter dispatch. A request receipt alone is not confirmation.\n"
            "## 2 Visitor access\n"
            "Visitors entering the service area must wear a temporary badge.\n"
            "## 3 Charges\n"
            "The surcharge for rescheduling has not been agreed. Do not infer an amount or deadline.\n"
            "## 4 Semantic platform boundary\n"
            "The semantic platform describes the service policy and does not dispatch vehicles itself.\n"
        ),
        "task": (
            "From the approved policy, draft business competency questions that test reservation "
            "readiness and the agreed conditions and unknowns. Use the mounted CQ role, skill, "
            "and exact draft contract; publish through cq_publish_question_draft and await review. "
            "Use only the approved source and preserve public/hidden isolation. "
            "Do not create a reference answer from invented rules or execute a business action."
        ),
    }


def test_review_successor_freeze_matches_approved_change_and_preserves_old_reports(cq_runner):
    # Lifecycle proof only; method quality is independently tested with actual
    # CQ authoring and host review using the approved generic material above.
    original = cq_question("Q-01", answer_points=["request receipt", "unrelated badge"])
    draft = _draft([original])
    cq_runner._publish_cq_question_draft({"cq_id": "competency-question", "draft": draft})
    root = cq_runner.run.root
    initial_review = root / "competency-questions/reviews/cq-review-0001.json"
    initial_bytes = initial_review.read_bytes()
    cq_runner.handle_cq_outer_input(_review_payload(cq_runner))
    cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    old_freeze = root / "competency-questions/frozen/freeze-0001.json"
    old_freeze_bytes = old_freeze.read_bytes()
    report = root / "acceptance-v3/reports/historical/batch-report.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"retained":"historical failure"}')
    historical_bytes = report.read_bytes()
    # Reopen the normal review with an explicit successor, then apply the host
    # modification against this review's actual identity rather than old note.
    draft.update({"draft_id": "cq-draft-0002", "superseded_draft_id": "cq-draft-0001"})
    cq_runner._publish_cq_question_draft({"cq_id": "competency-question", "draft": draft})
    replacement = dict(original, question="When is a reservation confirmed?",
                       answer_points=["supervisor approval"], content_version=2)
    cq_runner.handle_cq_outer_input(cq_fixtures._decision(
        cq_runner, 2, decision="modify", modified_question=replacement,
        note="Q-01 v2 point 1: approved policy §1; approval determines confirmation."))
    successor = _draft([replacement])
    successor.update({"draft_id": "cq-draft-0003", "superseded_draft_id": draft["draft_id"]})
    cq_runner._publish_cq_question_draft({"cq_id": "competency-question", "draft": successor})
    cq_runner.handle_cq_outer_input(cq_fixtures._decision(
        cq_runner, 3, note="Q-01 v2 point 1 checked against final question and approved policy §1."))
    ack = cq_runner.handle_cq_outer_input({"action": "cq_freeze"})
    freeze_path = root / "competency-questions/frozen/freeze-0002.json"
    frozen = json.loads(freeze_path.read_text())
    actual = frozen["questions"][0]
    assert actual["question_id"] == replacement["question_id"]
    assert actual["content_version"] == 2
    assert actual["question"] == replacement["question"]
    assert actual["answer_points"] == replacement["answer_points"]
    assert len(frozen["ordering"]) == 1
    assert frozen["snapshot_digest"] == ack["snapshot_digest"]
    assert initial_review.read_bytes() == initial_bytes
    assert old_freeze.read_bytes() == old_freeze_bytes
    assert report.read_bytes() == historical_bytes
    assert "checked against final" not in json.dumps(public_projection(frozen))
