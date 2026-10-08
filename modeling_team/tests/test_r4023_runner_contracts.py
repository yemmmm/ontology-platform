"""Focused R4.0-023 Runner and model-binding contract checks.

These tests exercise the real prepared Runner with an offline adapter.  They do
not start a Team, provider session, service, or semantic run.
"""

from __future__ import annotations

import json

import pytest
import yaml

from modeling_team.__main__ import _handle_foreground_message
from modeling_team.contracts import (
    DELIVERY_ROLE,
    TeamConfigurationError,
    load_agent_package,
    load_profile,
    repository_root,
)
from modeling_team.model_routing import (
    RoleModelBinding,
    TeamModelProfile,
    TeamModelProfileError,
    load_team_model_profile,
    resolve_delivery_model_binding,
)
from modeling_team.runner import RecoverableOuterInputError
from modeling_team.tests.test_r3011_runner_wiring import _CQRunner


ROOT = repository_root()


@pytest.fixture()
def prepared_runner():
    harness = _CQRunner()
    runner = harness.prepare()
    yield harness, runner
    harness.cleanup()


def _instruction(runner, **overrides):
    message = {
        "action": "instruction",
        "kind": "user_supplement",
        "text": "业务补充第一行\n第二行：中文原文保持不变\n第三行",
        "source_reference": "approved-source/section-4",
        "authorization_reference": "user-auth/r4-0-023",
        "run_id": runner.run.run_id,
    }
    message.update(overrides)
    return message


def test_instruction_preserves_source_and_reaches_coordinator_once(prepared_runner):
    harness, runner = prepared_runner
    message = _instruction(runner)

    output = runner.receive_outer(message)

    assert [item["type"] for item in output] == [
        "instruction-accepted",
        "instruction-delivered",
    ]
    accepted, delivered = output
    assert accepted["delivery_status"] == "delivered"
    assert delivered["sender_id"] == "delivery/outer"
    assert delivered["recipient_id"] == "coordinator"
    sent = [item for item in harness.adapter.messages if item[0] == "coordinator"]
    assert len(sent) == 1
    recipient, delivery = sent[0]
    assert recipient == "coordinator"
    assert delivery.sender_id == "delivery/outer"
    assert delivery.kind == "outer-instruction"
    assert delivery.text == message["text"]
    assert delivery.delivery_id == accepted["instruction_id"]

    evidence = runner.run.root / "evidence"
    admitted = [json.loads(line) for line in (evidence / "outer-instruction.jsonl").read_text().splitlines()]
    delivered_records = [
        json.loads(line)
        for line in (evidence / "outer-instruction-delivery.jsonl").read_text().splitlines()
    ]
    assert admitted[-1]["kind"] == "user_supplement"
    assert admitted[-1]["sender_id"] == "delivery/outer"
    assert admitted[-1]["text"] == message["text"]
    assert admitted[-1]["source_reference"] == message["source_reference"]
    assert admitted[-1]["authorization_reference"] == message["authorization_reference"]
    assert delivered_records[-1]["status"] == "delivered"
    assert delivered_records[-1]["kind"] == "user_supplement"
    assert delivered_records[-1]["source_reference"] == message["source_reference"]
    assert delivered_records[-1]["authorization_reference"] == message[
        "authorization_reference"
    ]

    # This direct CQ fixture does not start a Team Transport broker.  The
    # absence of any direct Modeling delivery still verifies that admission
    # stops at Coordinator; the production drain path classifies a later
    # Coordinator forward from ``_outer_instruction_texts`` as outer-forward.
    assert not [item for item in harness.adapter.messages if item[0] == "modeling"]


def test_instruction_uses_foreground_known_action_and_request_receipt(prepared_runner):
    harness, runner = prepared_runner
    message = _instruction(runner)
    message["request_id"] = "instruction-request-1"
    emitted = []
    rejected = []

    _handle_foreground_message(
        runner,
        json.dumps(message, ensure_ascii=False),
        emitted.extend,
        lambda detail=None: rejected.append(detail),
    )

    assert not rejected
    assert emitted[0]["type"] == "instruction-accepted"
    receipt_path = runner.run.root / "evidence/outer-input-receipts.jsonl"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["request_id"] == "instruction-request-1"
    assert receipt["action"] == "instruction"
    assert receipt["outcome"] == "accepted"
    assert [item[0] for item in harness.adapter.messages] == ["coordinator"]


def test_instruction_admission_survives_a_recoverable_delivery_failure(prepared_runner):
    harness, runner = prepared_runner
    message = _instruction(runner, kind="delivery_guidance")
    original_send = harness.adapter.send_message

    def fail_once(*_args, **_kwargs):
        raise RuntimeError("offline coordinator adapter")

    harness.adapter.send_message = fail_once
    with pytest.raises(RecoverableOuterInputError) as failure:
        runner.receive_outer(message)
    assert failure.value.code == "instruction_delivery_deferred"
    admitted = (runner.run.root / "evidence/outer-instruction.jsonl").read_text()
    deferred = (runner.run.root / "evidence/outer-instruction-delivery.jsonl").read_text()
    assert '"admission_status": "accepted"' in admitted
    assert '"status": "deferred"' in deferred
    state = json.loads((runner.run.root / "state.json").read_text(encoding="utf-8"))
    assert state["state"] != "FAILED"

    harness.adapter.send_message = original_send
    retry = runner.receive_outer(message)
    assert retry[0]["type"] == "instruction-accepted"
    assert retry[0]["delivery_status"] == "delivered"
    assert "replayed" not in retry[0]


def test_instruction_rejections_are_recoverable_and_do_not_consume_owner_answers(
    prepared_runner,
):
    _harness, runner = prepared_runner
    baseline_answer_state = set(runner._owner_answer_consumed)

    with pytest.raises(RecoverableOuterInputError) as invalid:
        runner.receive_outer(_instruction(runner, forged_id="never-accepted"))
    assert invalid.value.code == "invalid_instruction"
    assert runner._owner_answer_consumed == baseline_answer_state

    with pytest.raises(RecoverableOuterInputError) as stale:
        runner.receive_outer(_instruction(runner, run_id="stale-run"))
    assert stale.value.code == "stale_instruction"
    assert runner._owner_answer_consumed == baseline_answer_state

    # The CQ fixture intentionally has no broker.  A terminal result is all
    # the instruction gate reads, so inject that narrow read-only stand-in and
    # restore the fixture's transport before cleanup.
    class _TerminalTransport:
        results = {"coordinator": object()}

    runner.transport = _TerminalTransport()
    try:
        with pytest.raises(RecoverableOuterInputError) as terminal:
            runner.receive_outer(_instruction(runner))
        assert terminal.value.code == "instruction_recipient_terminal"
        assert runner._owner_answer_consumed == baseline_answer_state
        state = json.loads((runner.run.root / "state.json").read_text(encoding="utf-8"))
        assert state["state"] != "FAILED"
    finally:
        runner.transport = None


def test_delivery_package_is_loadable_but_cannot_be_a_production_profile_role(tmp_path):
    package = load_agent_package(ROOT, "delivery")
    assert package.role == DELIVERY_ROLE

    profile_path = ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml"
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    payload["agents"].append({"agent_id": "delivery", "package": "delivery"})
    candidate = tmp_path / "profile.yaml"
    candidate.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="host-only"):
        load_profile(candidate, root=ROOT, multi_slice=True)


def test_delivery_model_binding_prefers_explicit_then_inherits_coordinator(tmp_path):
    profile = load_team_model_profile(ROOT, "openai-sol-medium")
    inherited, source = resolve_delivery_model_binding(profile)
    coordinator = profile.binding_for("coordinator")
    assert source == "coordinator"
    assert inherited.package_id == "delivery"
    assert inherited.provider_id == coordinator.provider_id
    assert inherited.model == coordinator.model
    assert inherited.effective_effort == coordinator.effective_effort

    explicit = RoleModelBinding(
        package_id="delivery",
        provider_id="openai-codex",
        model="gpt-5.6-luna",
        requested_effort="low",
        effective_effort="low",
    )
    explicit_profile = TeamModelProfile(
        profile_id=profile.profile_id,
        relative_path=profile.relative_path,
        digest=profile.digest,
        bindings={**profile.bindings, "delivery": explicit},
    )
    selected, source = resolve_delivery_model_binding(explicit_profile)
    assert selected == explicit
    assert source == "delivery"

    # The profile loader admits an optional explicit Delivery declaration while
    # preserving the old profile shape and all existing role checks.
    profile_document = yaml.safe_load(
        (ROOT / "modeling_team/model-profiles/openai-sol-medium.yaml").read_text(
            encoding="utf-8"
        )
    )
    profile_document["roles"]["delivery"] = {
        "model_provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "model_reasoning_effort": "low",
    }
    profile_root = tmp_path / "profile-fixture"
    profile_path = profile_root / "modeling_team/model-profiles/openai-sol-medium.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        yaml.safe_dump(profile_document, sort_keys=False), encoding="utf-8"
    )
    loaded_explicit = load_team_model_profile(profile_root, "openai-sol-medium")
    selected, source = resolve_delivery_model_binding(loaded_explicit)
    assert source == "delivery"
    assert selected.model == "gpt-5.6-luna"

    incomplete = TeamModelProfile(
        profile_id="incomplete",
        relative_path="fixture",
        digest="digest",
        bindings={"modeling": profile.binding_for("modeling")},
    )
    with pytest.raises(TeamModelProfileError, match="coordinator or delivery"):
        resolve_delivery_model_binding(incomplete)
