"""Explicit runtime wiring and legacy binding compatibility, with no inference."""

import shutil
from pathlib import Path

import pytest

from modeling_team import delivery_ops, host_ops, host_ops_mcp
from modeling_team.tests.test_delivery_ops import _run_root, _write_frozen_snapshot, _Process

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "dsh-acceptance-deepseek-flash-low"


def stage_profile(tmp_path):
    folder = tmp_path / "modeling_team/model-profiles"
    folder.mkdir(parents=True)
    shutil.copyfile(
        ROOT / f"modeling_team/model-profiles/{PROFILE}.yaml", folder / f"{PROFILE}.yaml"
    )


def test_host_operation_binds_runtime_argv_environment_and_rejects_missing_binding(
    tmp_path, monkeypatch
):
    root = _run_root(tmp_path)
    _write_frozen_snapshot(root)
    stage_profile(tmp_path)
    seen = []
    monkeypatch.setenv("MODELING_TEAM_CODEX_SERVICE_TIER", "fast")

    def launcher(argv, **kwargs):
        seen.append((argv, kwargs["env"]))
        return _Process()

    args = dict(
        run_id=root.name,
        operation_id="dsh-eval",
        mode="public-feedback",
        freeze_id="freeze-0001",
        checkpoint_id="checkpoint",
        question_ids=["cq-1"],
        runtime="dsh",
        model_profile=PROFILE,
        repository_root=tmp_path,
        launcher=launcher,
    )
    delivery_ops.start_evaluation(**args)
    assert seen[0][0][seen[0][0].index("--runtime") + 1] == "dsh"
    assert "MODELING_TEAM_CODEX_SERVICE_TIER" not in seen[0][1]
    record = delivery_ops._read_record("dsh-eval", tmp_path)
    assert (
        record["request"]["runtime"] == record["request"]["report_expectations"]["runtime"] == "dsh"
    )
    with pytest.raises(host_ops.HostOpError, match="retained record"):
        delivery_ops.start_evaluation(**{**args, "runtime": "codex", "model_profile": None})
    for change in ({"model_profile": None}, {"service_tier": "fast"}, {"runtime": "unknown"}):
        with pytest.raises(host_ops.HostOpError) as error:
            delivery_ops.start_evaluation(**{**args, "operation_id": "bad", **change})
        assert error.value.retryable
    assert len(seen) == 1


def test_new_dsh_report_cannot_match_legacy_missing_runtime_but_old_codex_can():
    record = {
        "request": {
            "mode": "public-feedback",
            "runtime": "dsh",
            "report_expectations": {"runtime": "dsh"},
        }
    }
    assert "runtime_mismatch" in delivery_ops._report_binding_errors(record, {})
    assert "runtime_mismatch" not in delivery_ops._report_binding_errors(record, {"runtime": "dsh"})
    assert "runtime_mismatch" not in delivery_ops._report_binding_errors(
        {"request": {"mode": "public-feedback"}}, {}
    )


def test_mcp_and_delivery_expose_independent_runtime_selection(tmp_path):
    from modeling_team.tests.test_delivery_session import session

    host = session(tmp_path)
    specs = {s["name"]: s for s in host.tool_specs()}
    for name in ("start_evaluation", "resume_from_checkpoint"):
        assert "runtime" in specs[name]["inputSchema"]["properties"]
    assert host.config.get("evaluation_runtime", "codex") == "codex"
    # Both native Host APIs keep their backwards-compatible default.
    import inspect

    assert inspect.signature(host_ops_mcp.start_evaluation).parameters["runtime"].default == "codex"
    assert (
        inspect.signature(host_ops.resume_from_checkpoint).parameters["runtime"].default == "codex"
    )


def test_acceptance_resume_forwards_runtime_without_production_or_fast_env(tmp_path, monkeypatch):
    stage_profile(tmp_path)
    monkeypatch.setenv(host_ops.HOST_CREDENTIAL_ENV, "engineering-only")
    seen = []
    monkeypatch.setattr(
        host_ops, "_launch_managed_run", lambda **kwargs: seen.append(kwargs) or {"pid": 1}
    )
    result = host_ops.resume_from_checkpoint(
        source_run_id="source",
        checkpoint_id="handoff-1",
        new_run_id="read-only-attempt",
        mode="acceptance",
        authorization_reference="engineering",
        runtime="dsh",
        model_profile=PROFILE,
        repository_root=tmp_path,
    )
    assert result["runtime"] == "dsh"
    assert seen[0]["argv"][seen[0]["argv"].index("--runtime") + 1] == "dsh"
    assert seen[0]["service_tier"] == "default"
    assert "--runtime" in host_ops.CHECKPOINT_RESUME_FLAGS
    with pytest.raises(host_ops.HostOpError, match="acceptance-only"):
        host_ops.resume_from_checkpoint(
            source_run_id="source",
            checkpoint_id="handoff-1",
            new_run_id="production-attempt",
            mode="production",
            authorization_reference="engineering",
            runtime="dsh",
            model_profile=PROFILE,
            repository_root=tmp_path,
        )
    assert len(seen) == 1


@pytest.mark.parametrize("failed", [False, True])
def test_dsh_selection_uses_existing_full_denominator_and_post_consumer_judging(
    tmp_path, monkeypatch, capsys, failed
):
    from argparse import Namespace
    from modeling_team import __main__ as cli
    from modeling_team.runtimes import acceptance
    from modeling_team.tests.test_r3011_acceptance import _question
    from modeling_team.tests.test_r3012_partial_judging import _batch_adapter
    from modeling_team.tests.test_r3012_platform_responses import (
        _DualForwarder,
        _Factory,
        _RETAINED_QUERY_RESULT,
        _platform_context,
        _read_report,
        _write_handoff,
        _write_run_root,
    )

    questions = [_question(f"cq-{i}") for i in range(1, 6)]
    run, frozen = _write_run_root(tmp_path, questions)
    handoff = _write_handoff(tmp_path, frozen)
    base, state = _batch_adapter(omitted=("cq-2",) if failed else ())
    selected = []

    def factory(runtime, **kwargs):
        selected.append(runtime)
        return base(**kwargs)

    monkeypatch.setattr(acceptance, "acceptance_runtime", factory)
    monkeypatch.setenv(cli._CQ_PLATFORM_READ_KEY_ENV, "engineering-only")
    code = cli._run_cq_acceptance(
        Namespace(
            run_root=run,
            freeze_id="freeze-0001",
            model_handoff=handoff,
            runtime="dsh",
            model_profile=PROFILE,
            session_timeout=2,
            unexecuted_report=False,
        ),
        ROOT,
        forwarder_factory=_Factory(
            _DualForwarder(_platform_context(), [_RETAINED_QUERY_RESULT] * 5)
        ),
    )
    capsys.readouterr()
    report = _read_report(run, frozen["batch_id"])
    assert code == (1 if failed else 0)
    assert report["runtime"] == "dsh" and report["full_pass"] is not failed
    assert selected == ["dsh"] * 6  # five Consumers then one independently loaded Judge
    assert len(report["executed_question_ids"]) + len(report["unexecuted_question_ids"]) == 5
    assert report["unexecuted_question_ids"] == (["cq-2"] if failed else [])
    assert len(report["verdicts"]) == (4 if failed else 5)


def test_dsh_judge_grouping_does_not_inherit_codex_native_turn_limit(monkeypatch):
    from modeling_team import __main__ as cli
    from modeling_team.tests.test_v43_judge_references import reference_packet

    packet = reference_packet(1, platform_body={"text": "large" * 500})
    monkeypatch.setattr(cli, "_CODEX_MAX_INPUT_TEXT_CHARS", 100)
    failures = {}
    assert cli._cq_judge_input_packets(packet, runtime="codex", input_failures=failures) == []
    assert failures
    assert cli._cq_judge_input_packets(packet, runtime="dsh") == [packet]


@pytest.mark.parametrize("previous_runtime", [None, "codex", "dsh"])
def test_readonly_continuation_does_not_claim_old_codex_pass_as_dsh(
    monkeypatch, capsys, previous_runtime
):
    import json
    import os
    from shutil import rmtree
    from modeling_team import __main__ as cli
    from modeling_team.tests import test_r30015_acceptance as original
    from modeling_team.tests.test_r30015_resume import FakeCursorPlatform, _readback

    run_root, frozen, checkpoint = original._acceptance_source_run()
    new_id = "r4333out-" + os.urandom(4).hex()
    output = original.RUNS_ROOT / new_id
    try:
        report = original._batch_report_for(frozen, run_root.name, passed=["cq-1", "cq-2"])
        if previous_runtime is not None:
            report["runtime"] = previous_runtime
        directory = run_root / "acceptance-v3/reports" / frozen["batch_id"] / "attempt-0001"
        directory.mkdir(parents=True)
        (directory / "batch-report.json").write_text(json.dumps(report))
        monkeypatch.setattr(cli, "http_readback", lambda *args: _readback(FakeCursorPlatform()))
        calls = []
        monkeypatch.setattr(
            cli, "_run_cq_acceptance", lambda args, *a, **kw: calls.append((args, kw)) or 1
        )
        args = original._cli_args(run_root.name, checkpoint, new_id)
        args.runtime = "dsh"
        args.model_profile = PROFILE
        code = cli._run_checkpoint_resume_acceptance(args, original.REPO_ROOT)
        capsys.readouterr()
        assert code == (0 if previous_runtime == "dsh" else 1)
        assert len(calls) == (0 if previous_runtime == "dsh" else 1)
        if calls:
            assert calls[0][0].runtime == "dsh"
            assert calls[0][1]["continuation"]["attempt_id"] == "attempt-0002"
        assert json.loads((directory / "batch-report.json").read_text()) == report
    finally:
        original._cleanup_run(run_root)
        rmtree(output, ignore_errors=True)


def test_public_feedback_selects_dsh_consumer_without_judge(tmp_path, monkeypatch, capsys):
    import json
    from argparse import Namespace
    from modeling_team import __main__ as cli
    from modeling_team.runtimes import acceptance
    from modeling_team.tests.test_r4015_public_feedback import seed_feedback_run, _ScriptedForwarder
    from modeling_team.tests.test_r3012_partial_judging import _batch_adapter
    from modeling_team.tests.test_r3012_platform_responses import _platform_context

    run, checkpoint, frozen = seed_feedback_run(tmp_path)
    base, state = _batch_adapter()
    selected = []
    monkeypatch.setattr(
        acceptance,
        "acceptance_runtime",
        lambda runtime, **kw: selected.append(runtime) or base(**kw),
    )
    monkeypatch.setenv(cli._CQ_PLATFORM_READ_KEY_ENV, "engineering-only")
    code = cli._run_public_feedback(
        Namespace(
            run_root=run,
            checkpoint_id=checkpoint,
            freeze_id="freeze-0001",
            question_id=["cq-public"],
            runtime="dsh",
            model_profile=PROFILE,
            session_timeout=2,
        ),
        ROOT,
        forwarder_factory=lambda **kw: _ScriptedForwarder([_platform_context()]),
    )
    capsys.readouterr()
    record = json.loads(next((run / "early-feedback").glob("*/feedback.json")).read_text())
    assert code == 0 and record["runtime"] == "dsh"
    assert selected == ["dsh"] and state["judge_payload"] is None
    assert record["formal_acceptance"] is False
    assert record["consumer_tasks"][0]["packet_digest"]


def test_delivery_pins_acceptance_runtime_independently_of_its_own_model(tmp_path, monkeypatch):
    from functools import wraps
    from modeling_team.tests.test_delivery_session import session

    host = session(tmp_path)
    host.config.update(evaluation_runtime="dsh", evaluation_model_profile=PROFILE)
    host.allowed_operations.add("evaluation")
    host.run_ids.add("owned-run")
    seen = []

    @wraps(host_ops_mcp.start_evaluation)
    def launch(**kwargs):
        seen.append(kwargs)
        return {"status": "running", "operation_id": kwargs["operation_id"]}

    monkeypatch.setattr(host_ops_mcp, "start_evaluation", launch)
    args = {
        "run_id": "owned-run",
        "operation_id": "selected-eval",
        "mode": "public-feedback",
        "freeze_id": "freeze-1",
        "checkpoint_id": "checkpoint",
        "question_ids": ["cq-public"],
    }
    result = host.call_tool("start_evaluation", args)
    assert result["ok"], result
    assert seen[0]["runtime"] == "dsh" and seen[0]["model_profile"] == PROFILE
    assert host.runtime_name == "codex"
    assert not host.call_tool(
        "start_evaluation", {**args, "operation_id": "wrong-runtime", "runtime": "codex"}
    )["ok"]
    assert len(seen) == 1
