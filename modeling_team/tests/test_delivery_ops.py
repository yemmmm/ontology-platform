"""R4.0-023 host-side Delivery operation contracts.

These tests use a real temporary run workspace, one real FIFO write, and
controlled local processes.  No model provider, platform mutation, or global
provider configuration is touched.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from modeling_team import delivery_ops, host_ops


def _run_root(repository_root: Path, run_id: str = "delivery-run") -> Path:
    root = repository_root / "workspaces" / "modeling-runs" / run_id
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "state.json").write_text(
        json.dumps({"state": "RUNNING", "run_id": run_id}), encoding="utf-8"
    )
    return root


class _Process:
    def __init__(self, pid: int = 31337, exit_code: int = 0) -> None:
        self.pid = pid
        self.exit_code = exit_code

    def wait(self) -> int:
        return self.exit_code


def _wait_for_exit(operation_id: str, repository_root: Path) -> dict:
    for _ in range(100):
        status = delivery_ops.get_repair_status(
            operation_id=operation_id, repository_root=repository_root
        )
        if status["ended_at"] is not None:
            return status
        time.sleep(0.005)
    raise AssertionError("controlled Delivery process did not reach an exited record")


def test_submit_instruction_writes_the_existing_fifo_without_owner_question_binding(
    tmp_path: Path,
) -> None:
    run_id = "instruction-run"
    root = _run_root(tmp_path, run_id)
    fifo = root / "control" / "outer-input.fifo"
    os.mkfifo(fifo)
    received: list[dict] = []

    def consume() -> None:
        with fifo.open("rb") as handle:
            received.append(json.loads(handle.readline().decode("utf-8")))

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    result = host_ops.submit_instruction(
        run_id,
        kind="user_supplement",
        text="The approved return window is 30 days.",
        source_reference="user-message-42",
        authorization_reference="auth-r4-023-1",
        request_id="instruction-1",
        repository_root=tmp_path,
    )
    reader.join(timeout=2)

    assert result["status"] == "submitted"
    assert result["action"] == "instruction"
    assert result["consumption_evidence"] == "evidence/outer-instruction.jsonl"
    assert received == [
        {
            "action": "instruction",
            "authorization_reference": "auth-r4-023-1",
            "kind": "user_supplement",
            "request_id": "instruction-1",
            "source_reference": "user-message-42",
            "text": "The approved return window is 30 days.",
        }
    ]
    assert "question_delivery_id" not in received[0]


def test_submit_instruction_rejects_unknown_kind_before_fifo_write(tmp_path: Path) -> None:
    with pytest.raises(host_ops.HostOpError) as error:
        host_ops.submit_instruction(
            "missing-run",
            kind="owner_answer",
            text="text",
            source_reference="source",
            authorization_reference="auth",
            repository_root=tmp_path,
        )
    assert error.value.code == "instruction_kind_invalid"


def test_start_evaluation_binds_only_a_report_created_after_this_operation(
    tmp_path: Path,
) -> None:
    run_id = "evaluation-run"
    run_root = _run_root(tmp_path, run_id)
    old_report = run_root / "acceptance-v3" / "reports" / "old" / "batch-report.json"
    old_report.parent.mkdir(parents=True)
    old_report.write_text(json.dumps({"full_pass": True}), encoding="utf-8")
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"schema_version": "handoff/test"}), encoding="utf-8")
    launched: list[dict] = []

    def launcher(argv, *, cwd, env, stdin, stdout, stderr):
        launched.append({"argv": list(argv), "cwd": cwd, "env": dict(env)})
        return _Process(exit_code=0)

    result = delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-1",
        mode="cq-acceptance",
        freeze_id="freeze-1",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="hidden",
        session_timeout=42,
        service_tier="default",
        repository_root=tmp_path,
        launcher=launcher,
    )
    assert result["initial_report_count"] == 1
    assert launched and launched[0]["cwd"] == tmp_path.resolve()
    argv = launched[0]["argv"]
    assert "--unexecuted-report" not in argv
    assert ["--freeze-id", "freeze-1"] == argv[argv.index("--freeze-id") : argv.index("--freeze-id") + 2]
    assert "--question-visibility" in argv
    assert "--model-handoff" in argv

    no_new = delivery_ops.get_evaluation_status(
        operation_id="evaluation-1", repository_root=tmp_path
    )
    assert no_new["report_status"] == "no_new_report"
    assert no_new["report_binding"] is None
    old_report.write_text(json.dumps({"full_pass": True, "tampered": True}), encoding="utf-8")
    tampered_old = delivery_ops.get_evaluation_status(
        operation_id="evaluation-1", repository_root=tmp_path
    )
    assert tampered_old["report_status"] == "no_new_report"
    assert tampered_old["report_binding"] is None

    new_report = run_root / "acceptance-v3" / "reports" / "new" / "batch-report.json"
    new_report.parent.mkdir(parents=True)
    new_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": run_id,
                "executed_question_ids": ["cq-1"],
                "verdicts": [{"verdict": "pass"}],
                "batch_id": "freeze-1",
                "freeze_digest": "sha256:test",
                "sessions": {"model_profile": "openai-sol-medium"},
            }
        ),
        encoding="utf-8",
    )
    bound = delivery_ops.get_evaluation_status(
        operation_id="evaluation-1", repository_root=tmp_path
    )
    assert bound["report_status"] == "new_report_bound"
    assert bound["report_binding"]["preexisted"] is False
    assert bound["report_binding"]["valid"] is True
    assert bound["report_binding"]["summary"]["executed_question_ids"] == ["cq-1"]


def test_evaluation_status_observes_a_report_published_just_after_process_exit(
    tmp_path: Path,
) -> None:
    run_id = "evaluation-publish-race"
    run_root = _run_root(tmp_path, run_id)
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")

    def launcher(argv, **_kwargs):
        def publish() -> None:
            time.sleep(0.03)
            report = run_root / "acceptance-v3" / "reports" / "late" / "batch-report.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(
                    {
                        "status": "completed",
                        "full_pass": True,
                        "run_id": run_id,
                        "batch_id": "freeze-race",
                        "executed_question_ids": ["cq-1"],
                        "unexecuted_question_ids": [],
                        "verdicts": [{"verdict": "pass"}],
                        "sessions": {"model_profile": "openai-sol-medium"},
                    }
                ),
                encoding="utf-8",
            )

        threading.Thread(target=publish, daemon=True).start()
        return _Process(exit_code=0)

    delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-publish-race",
        mode="cq-acceptance",
        freeze_id="freeze-race",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="hidden",
        repository_root=tmp_path,
        launcher=launcher,
    )
    status = delivery_ops.get_evaluation_status(
        operation_id="evaluation-publish-race", repository_root=tmp_path
    )
    assert status["report_status"] == "new_report_bound"
    assert status["report_binding"]["valid"] is True


def test_public_feedback_uses_only_its_supported_cli_arguments(tmp_path: Path) -> None:
    _run_root(tmp_path, "feedback-run")
    launched: list[list[str]] = []

    def launcher(argv, **_kwargs):
        launched.append(list(argv))
        return _Process(exit_code=1)

    delivery_ops.start_evaluation(
        run_id="feedback-run",
        operation_id="feedback-1",
        mode="public-feedback",
        freeze_id="freeze-public",
        checkpoint_id="checkpoint-1",
        question_ids=["cq-1", "cq-2"],
        model_profile="openai-sol-medium",
        session_timeout=17,
        repository_root=tmp_path,
        launcher=launcher,
    )
    argv = launched[0]
    assert "--checkpoint-id" in argv
    assert argv.count("--question-id") == 2
    assert "--question-visibility" not in argv
    assert "--model-handoff" not in argv
    with pytest.raises(host_ops.HostOpError) as error:
        delivery_ops.start_evaluation(
            run_id="feedback-run",
            operation_id="feedback-bad",
            mode="public-feedback",
            freeze_id="freeze-public",
            checkpoint_id="checkpoint-1",
            question_ids=["cq-1"],
            question_visibility="public",
            repository_root=tmp_path,
            launcher=launcher,
        )
    assert error.value.code == "evaluation_argument_invalid"


def test_evaluation_report_with_wrong_batch_identity_is_rejected(tmp_path: Path) -> None:
    run_id = "evaluation-mismatch-run"
    run_root = _run_root(tmp_path, run_id)
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"schema_version": "handoff/test"}), encoding="utf-8")

    def launcher(argv, **_kwargs):
        return _Process(exit_code=0)

    delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-mismatch",
        mode="cq-acceptance",
        freeze_id="expected-freeze",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="hidden",
        repository_root=tmp_path,
        launcher=launcher,
    )
    report = run_root / "acceptance-v3" / "reports" / "wrong" / "batch-report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": run_id,
                "executed_question_ids": ["cq-1"],
                "verdicts": [{"verdict": "pass"}],
                "batch_id": "WRONG-FREEZE",
                "freeze_digest": "sha256:test",
                "sessions": {"model_profile": "openai-sol-medium"},
            }
        ),
        encoding="utf-8",
    )
    rejected = delivery_ops.get_evaluation_status(
        operation_id="evaluation-mismatch", repository_root=tmp_path
    )
    assert rejected["report_status"] == "new_report_rejected"
    assert rejected["report_binding"]["valid"] is False
    assert rejected["report_binding"]["summary"]["full_pass"] is None
    assert rejected["report_binding"]["summary"]["reported_full_pass"] is True
    assert any(
        item.startswith("batch_id_mismatch")
        for item in rejected["report_binding"]["validation_errors"]
    )


def test_hidden_evaluation_never_selects_a_public_report_as_its_own(
    tmp_path: Path,
) -> None:
    run_id = "evaluation-visibility-run"
    run_root = _run_root(tmp_path, run_id)
    handoff = tmp_path / "handoff.json"
    handoff.write_text(json.dumps({"schema_version": "handoff/test"}), encoding="utf-8")

    def launcher(argv, **_kwargs):
        return _Process(exit_code=0)

    delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-visibility",
        mode="cq-acceptance",
        freeze_id="freeze-visibility",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="hidden",
        repository_root=tmp_path,
        launcher=launcher,
    )
    # A public regression report published inside this hidden operation's
    # window is another operation's report.  Even as the only new report it
    # must not be selected or attributed to this operation.
    public_report = run_root / "acceptance-v3" / "public-regression" / "pub" / "batch-report.json"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": run_id,
                "batch_id": "freeze-visibility",
                "freeze_digest": "sha256:test",
                "executed_question_ids": ["pq-1"],
                "unexecuted_question_ids": [],
                "verdicts": [{"verdict": "pass"}],
                "question_selection": {"visibility": "public", "question_ids": ["pq-1"]},
                "sessions": {"model_profile": "openai-sol-medium"},
            }
        ),
        encoding="utf-8",
    )
    skipped = delivery_ops.get_evaluation_status(
        operation_id="evaluation-visibility", repository_root=tmp_path
    )
    assert skipped["report_status"] == "no_new_report"
    assert skipped["report_binding"] is None
    record_path = Path(skipped["record_path"])
    record = json.loads(
        (record_path if record_path.is_absolute() else tmp_path / record_path).read_text(
            encoding="utf-8"
        )
    )
    assert [item["visibility"] for item in record["excluded_report_candidates"]] == ["public"]

    # Once this operation's own hidden report is also new, it is the one bound;
    # the coexisting public report stays excluded, and the same-visibility
    # foreign-identity rejection contract is untouched.
    hidden_report = run_root / "acceptance-v3" / "reports" / "new" / "batch-report.json"
    hidden_report.parent.mkdir(parents=True)
    hidden_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": run_id,
                "batch_id": "freeze-visibility",
                "freeze_digest": "sha256:test",
                "executed_question_ids": ["cq-1"],
                "unexecuted_question_ids": [],
                "verdicts": [{"verdict": "pass"}],
                "sessions": {"model_profile": "openai-sol-medium"},
            }
        ),
        encoding="utf-8",
    )
    bound = delivery_ops.get_evaluation_status(
        operation_id="evaluation-visibility", repository_root=tmp_path
    )
    assert bound["report_status"] == "new_report_bound"
    assert bound["report_binding"]["valid"] is True
    assert bound["report_binding"]["summary"]["executed_question_ids"] == ["cq-1"]


def test_public_evaluation_never_selects_a_hidden_report_as_its_own(
    tmp_path: Path,
) -> None:
    run_id = "evaluation-public-visibility-run"
    run_root = _run_root(tmp_path, run_id)
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")

    def launcher(argv, **_kwargs):
        return _Process(exit_code=0)

    delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-public-visibility",
        mode="cq-acceptance",
        freeze_id="freeze-public-visibility",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="public",
        repository_root=tmp_path,
        launcher=launcher,
    )
    hidden_report = run_root / "acceptance-v3" / "reports" / "hid" / "batch-report.json"
    hidden_report.parent.mkdir(parents=True)
    hidden_report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": run_id,
                "batch_id": "freeze-public-visibility",
                "freeze_digest": "sha256:test",
                "executed_question_ids": ["cq-1"],
                "unexecuted_question_ids": [],
                "verdicts": [{"verdict": "pass"}],
                "sessions": {"model_profile": "openai-sol-medium"},
            }
        ),
        encoding="utf-8",
    )
    status = delivery_ops.get_evaluation_status(
        operation_id="evaluation-public-visibility", repository_root=tmp_path
    )
    assert status["report_status"] == "no_new_report"
    assert status["report_binding"] is None


def test_cq_report_requires_run_identity_and_profile_digest_when_report_supplies_it(
    tmp_path: Path,
) -> None:
    run_id = "evaluation-binding-fields"
    run_root = _run_root(tmp_path, run_id)
    (run_root / "baseline-manifest.json").write_text(
        json.dumps(
            {
                "team_model_profile": {
                    "profile_id": "openai-sol-medium",
                    "sha256": "frozen-profile-digest",
                }
            }
        ),
        encoding="utf-8",
    )
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}", encoding="utf-8")

    def launcher(argv, **_kwargs):
        return _Process(exit_code=0)

    delivery_ops.start_evaluation(
        run_id=run_id,
        operation_id="evaluation-fields",
        mode="cq-acceptance",
        freeze_id="freeze-fields",
        model_handoff="handoff.json",
        model_profile="openai-sol-medium",
        question_visibility="hidden",
        repository_root=tmp_path,
        launcher=launcher,
    )
    report = run_root / "acceptance-v3" / "reports" / "new" / "batch-report.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "status": "completed",
                "full_pass": True,
                "run_id": "different-run",
                "batch_id": "freeze-fields",
                "freeze_digest": "sha256:test",
                "executed_question_ids": ["cq-1"],
                "verdicts": [],
                "sessions": {
                    "model_profile": "openai-sol-medium",
                    "model_profile_digest": "wrong-profile-digest",
                },
            }
        ),
        encoding="utf-8",
    )
    rejected = delivery_ops.get_evaluation_status(
        operation_id="evaluation-fields", repository_root=tmp_path
    )
    assert rejected["report_status"] == "new_report_rejected"
    errors = rejected["report_binding"]["validation_errors"]
    assert "run_id_mismatch" in errors
    assert "model_profile_digest_mismatch" in errors


def test_repair_uses_file_backed_stdin_and_keeps_effectiveness_unverified(
    tmp_path: Path,
) -> None:
    public_ref = tmp_path / "public-reference.md"
    public_ref.write_text("Publicly confirmed parser behavior.\n", encoding="utf-8")
    owned = tmp_path / "owned.py"
    owned.write_text("before = True\n", encoding="utf-8")
    task = tmp_path / "repair-task.md"
    task.write_text(
        "Authorized bounded repair.\n"
        + json.dumps(
            {
                "authorization_reference": "auth-repair-1",
                "source_references": ["public-reference.md"],
                "owned_paths": ["owned.py"],
            }
        )
        + "\nRepair only the confirmed parser defect.\n",
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def launcher(argv, *, stdin, **_kwargs):
        observed["argv"] = list(argv)
        observed["stdin"] = stdin.read()
        return _Process(exit_code=3)

    result = delivery_ops.start_repair(
        operation_id="repair-1",
        repair_task_file="repair-task.md",
        executor="codex",
        model="gpt-6.1-sol",
        effort="medium",
        authorization_reference="auth-repair-1",
        issue_id="issue-42",
        repository_root=tmp_path,
        launcher=launcher,
    )
    assert result["repair_task_file"] == "repair-task.md"
    assert b"Repair only the confirmed parser defect." in observed["stdin"]
    assert "Repair only the confirmed parser defect." not in observed["argv"]
    assert observed["argv"][0].endswith("bwrap")
    assert str(tmp_path / "workspaces") not in observed["argv"]
    assert str(tmp_path / ".codex") not in observed["argv"]
    assert "--bind" in observed["argv"]
    assert "/agent/home" in observed["argv"]
    assert "--model" in observed["argv"]
    status = _wait_for_exit("repair-1", tmp_path)
    assert status["exit_code"] == 3
    assert status["outcome"] == "failed"
    assert status["effect_verified"] is False
    assert status["request_binding"]["authorization_reference"] == "auth-repair-1"
    assert "log_tails" in status
    assert "stdout_tail" in status and "stderr_tail" in status
    assert status["repair_result_artifact"]["path"].endswith("repair-1.repair-result.json")
    assert status["artifact_locators"]["repair_task_file"] == "repair-task.md"
    assert status["repair_diff_artifact"]["path"].endswith("repair-1.repair-result.patch")


def test_stop_delivery_operation_verifies_and_terminates_owned_group(tmp_path: Path) -> None:
    argv = [
        os.sys.executable,
        "-c",
        "import time; time.sleep(30)",
    ]
    result = delivery_ops._launch_operation(
        operation_id="repair-stop",
        kind="repair",
        argv=argv,
        repository_root=tmp_path,
        request={"repair_task_file": "repair-task.md"},
        service_tier="unset",
    )
    stopped = delivery_ops.stop_delivery_operation(
        operation_id="repair-stop",
        reason="user revoked the repair authorization",
        repository_root=tmp_path,
    )
    assert stopped["stop_status"] == "requested"
    assert stopped["reason"].startswith("user revoked")
    for _ in range(100):
        status = delivery_ops.get_repair_status(
            operation_id="repair-stop", repository_root=tmp_path
        )
        if status["status"] in {"stopped", "exited"}:
            break
        time.sleep(0.01)
    else:
        raise AssertionError(f"stop did not settle: {result}")
    assert status["outcome"] == "stopped"
    assert status["effect_verified"] is False
    assert status["repair_result_artifact"]["available"] is True


class _Readback:
    def __init__(self) -> None:
        self.pages_read = 0
        self.batches_read = 0
        self.sessions_read = 0

    def get_batch(self, batch_id: str) -> dict:
        self.batches_read += 1
        return {
            "batch_id": batch_id,
            "project_id": "project-1",
            "ontology_id": "ontology-1",
            "attempts": [],
        }

    def get_session(self, session_id: str) -> dict:
        self.sessions_read += 1
        return {"session_id": session_id, "status": "completed"}

    def list_ontology_batches(self, ontology_id: str) -> list[dict]:
        self.pages_read += 1
        return []


def test_platform_readback_is_scoped_and_never_exposes_mutation(tmp_path: Path) -> None:
    readback = _Readback()
    result = delivery_ops.read_platform_record(
        record_type="batch",
        record_id="batch-1",
        project_id="project-1",
        ontology_id="ontology-1",
        repository_root=tmp_path,
        readback=readback,  # type: ignore[arg-type]
    )
    assert result["scope"] == {"project_id": "project-1", "ontology_id": "ontology-1"}
    assert result["record"]["batch_id"] == "batch-1"
    assert result["readback_only"] is True
    assert result["mutation_capabilities"] == {"apply": False, "delete": False}
    assert readback.batches_read == 1

    _run_root(tmp_path, "reconcile-run")
    reconciled = delivery_ops.reconcile_write_state(
        run_id="reconcile-run",
        project_id="project-1",
        ontology_ids=["ontology-1"],
        repository_root=tmp_path,
        readback=readback,  # type: ignore[arg-type]
    )
    assert reconciled["readback_only"] is True
    assert reconciled["mutation_capabilities"] == {"apply": False, "delete": False}
    assert reconciled["reconciliation"]["scope_drift"] == []


def test_platform_readback_requires_an_explicit_ontology_scope(tmp_path: Path) -> None:
    with pytest.raises(host_ops.HostOpError) as error:
        delivery_ops.read_platform_record(
            record_type="session",
            record_id="session-1",
            project_id="project-1",
            repository_root=tmp_path,
            readback=_Readback(),  # type: ignore[arg-type]
        )
    assert error.value.code == "platform_scope_invalid"
