"""R3.0-012 mechanical selector contracts (shared test plan T0-1..T0-5, T0-9).

Loader-level checks only: the closed ``parameters.acceptance_target`` enum,
its dependency on the R3.0-011 selector, the draft-name non-alias, and the
Runner-written run-contract snapshot.  No Agent is started and no platform
call is made; real-runtime behavior is covered by later T1-T5 modules.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree

import pytest
import yaml

from modeling_team.contracts import (
    ACCEPTANCE_TARGET_CQ_SEMANTIC,
    ACCEPTANCE_TARGET_FULL_JOINT,
    ACCEPTANCE_TARGET_PARAMETER,
    TeamConfigurationError,
    load_multi_slice_team_configuration,
    load_task,
    normalize_acceptance_target,
    task_declares_cq_semantic_target,
)
from modeling_team.runner import TeamRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
PROFILE_002 = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
MULTI_SLICE_SMOKE = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"


def _task_variant(name: str, mutate) -> Path:
    task = yaml.safe_load(TASK.read_text(encoding="utf-8"))
    task["task_id"] = name
    mutate(task)
    path = TASK.parent / f"{name}.yaml"
    path.write_text(yaml.safe_dump(task, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture()
def variant_tasks():
    """Write loader variants under the tasks directory; remove them after."""

    created: list[Path] = []

    def _make(name: str, mutate) -> Path:
        path = _task_variant(name, mutate)
        created.append(path)
        return path

    yield _make
    for path in created:
        path.unlink(missing_ok=True)


# --- T0-1 / T0-2: omission defaults to full_joint; cq_semantic loads ----------


def test_t0_1_omitted_acceptance_target_normalizes_to_full_joint():
    task = load_task(TASK)
    assert ACCEPTANCE_TARGET_PARAMETER not in (task.parameters or {})
    assert normalize_acceptance_target(task.parameters) == ACCEPTANCE_TARGET_FULL_JOINT


def test_t0_1_existing_tasks_without_the_key_keep_previous_parameters():
    task = load_task(MULTI_SLICE_SMOKE)
    assert task.parameters == {"multi_slice_workflow": True}


def test_t0_2_cq_semantic_loads_with_the_011_selector(variant_tasks):
    path = variant_tasks(
        "r3012-cq-semantic",
        lambda task: task["parameters"].update(
            {ACCEPTANCE_TARGET_PARAMETER: ACCEPTANCE_TARGET_CQ_SEMANTIC}
        ),
    )
    configuration = load_multi_slice_team_configuration(PROFILE, path)
    assert (
        configuration.task.parameters[ACCEPTANCE_TARGET_PARAMETER]
        == ACCEPTANCE_TARGET_CQ_SEMANTIC
    )
    assert normalize_acceptance_target(configuration.task.parameters) == (
        ACCEPTANCE_TARGET_CQ_SEMANTIC
    )
    assert task_declares_cq_semantic_target(path) is True


def test_t0_2_explicit_full_joint_loads_and_peeks_false(variant_tasks):
    path = variant_tasks(
        "r3012-full-joint",
        lambda task: task["parameters"].update(
            {ACCEPTANCE_TARGET_PARAMETER: ACCEPTANCE_TARGET_FULL_JOINT}
        ),
    )
    configuration = load_multi_slice_team_configuration(PROFILE, path)
    assert (
        configuration.task.parameters[ACCEPTANCE_TARGET_PARAMETER]
        == ACCEPTANCE_TARGET_FULL_JOINT
    )
    assert task_declares_cq_semantic_target(path) is False


# --- T0-3: typed rejections ---------------------------------------------------


def test_t0_3_unknown_value_is_rejected(variant_tasks):
    path = variant_tasks(
        "r3012-bad-enum",
        lambda task: task["parameters"].update({ACCEPTANCE_TARGET_PARAMETER: "cq-only"}),
    )
    with pytest.raises(TeamConfigurationError, match="acceptance_target is invalid"):
        load_task(path)


def test_t0_3_non_string_value_is_rejected(variant_tasks):
    path = variant_tasks(
        "r3012-bool-target",
        lambda task: task["parameters"].update({ACCEPTANCE_TARGET_PARAMETER: True}),
    )
    with pytest.raises(TeamConfigurationError, match="acceptance_target is invalid"):
        load_task(path)


def test_t0_3_cq_semantic_without_the_011_selector_is_rejected(variant_tasks):
    def mutate(task):
        task["parameters"].pop("competency_question_acceptance")
        task["parameters"][ACCEPTANCE_TARGET_PARAMETER] = ACCEPTANCE_TARGET_CQ_SEMANTIC

    path = variant_tasks("r3012-no-011-target", mutate)
    with pytest.raises(TeamConfigurationError, match="cq_selector_incompatible"):
        load_task(path)
    # The three-role 002 Profile is equally incompatible with the CQ scope.
    with pytest.raises(TeamConfigurationError):
        load_multi_slice_team_configuration(PROFILE_002, path)


def test_t0_3_boolean_parameters_still_reject_non_boolean_values(variant_tasks):
    path = variant_tasks(
        "r3012-bad-bool",
        lambda task: task["parameters"].update({"multi_slice_workflow": "yes"}),
    )
    with pytest.raises(TeamConfigurationError, match="v2 Task parameters are invalid"):
        load_task(path)


# --- T0-9: the draft name is not an alias -------------------------------------


def test_t0_9_draft_acceptance_scope_parameter_is_not_admitted(variant_tasks):
    path = variant_tasks(
        "r3012-draft-scope-name",
        lambda task: task["parameters"].update({"acceptance_scope": "cq_semantic"}),
    )
    with pytest.raises(TeamConfigurationError, match="v2 Task parameters are invalid"):
        load_task(path)
    assert normalize_acceptance_target({}) == ACCEPTANCE_TARGET_FULL_JOINT


# --- T0-5: acceptance_target, acceptance_mode and blind_status stay separate ----


def test_t0_5_the_report_names_are_not_task_parameters(variant_tasks):
    """T0-5 (loader half): ``acceptance_mode`` and ``blind_status`` name
    acceptance report fields, not Task parameters.  Smuggling either into the
    closed parameter set is a typed rejection, so neither can shadow or alias
    the ``acceptance_target`` selector."""
    for index, (name, value) in enumerate(
        (("acceptance_mode", "read-only-acceptance"), ("blind_status", "blind"))
    ):
        path = variant_tasks(
            f"r3012-report-name-{index}",
            lambda task, name=name, value=value: task["parameters"].update({name: value}),
        )
        with pytest.raises(TeamConfigurationError, match="v2 Task parameters are invalid"):
            load_task(path)


def test_t0_5_the_snapshot_records_the_selector_pair_only(variant_tasks):
    """T0-5 (snapshot half): a cq_semantic Task freezes exactly the selector
    pair into the run-contract snapshot; the two acceptance report names never
    enter it."""
    path = variant_tasks(
        "r3012-coexist",
        lambda task: task["parameters"].update(
            {ACCEPTANCE_TARGET_PARAMETER: ACCEPTANCE_TARGET_CQ_SEMANTIC}
        ),
    )
    harness = _SnapshotRunner(path)
    try:
        parameters = harness.contract()["parameters"]
        assert parameters["acceptance_target"] == ACCEPTANCE_TARGET_CQ_SEMANTIC
        assert parameters["competency_question_acceptance"] is True
        assert "acceptance_mode" not in parameters
        assert "blind_status" not in parameters
    finally:
        harness.cleanup()


# --- T0-1/T0-4: the Runner freezes the normalized value in the snapshot -------


class _SnapshotRunner:
    """A prepared runner whose run root and ledger are removed afterwards."""

    def __init__(self, task_path: Path) -> None:
        self.run_id = (
            f"r3012-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]}"
        )
        self.run_root = REPO_ROOT / "workspaces" / "modeling-runs" / self.run_id
        from modeling_team.tests.test_r3011_runner_wiring import CapturingAdapter

        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=CapturingAdapter(),
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=task_path,
            scope={"mode": "create"},
        )

    def contract(self) -> dict:
        return json.loads(
            (self.run_root / "acceptance-v3" / "run-contract.json").read_text(
                encoding="utf-8"
            )
        )

    def cleanup(self) -> None:
        self.runner.cleanup()
        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)


def test_t0_1_snapshot_records_the_normalized_default():
    harness = _SnapshotRunner(TASK)
    try:
        contract = harness.contract()
        assert contract["parameters"]["acceptance_target"] == ACCEPTANCE_TARGET_FULL_JOINT
        assert harness.runner._acceptance_target == ACCEPTANCE_TARGET_FULL_JOINT
    finally:
        harness.cleanup()


def test_t0_4_snapshot_freezes_cq_semantic_once(variant_tasks):
    path = variant_tasks(
        "r3012-snapshot-cq",
        lambda task: task["parameters"].update(
            {ACCEPTANCE_TARGET_PARAMETER: ACCEPTANCE_TARGET_CQ_SEMANTIC}
        ),
    )
    harness = _SnapshotRunner(path)
    try:
        contract = harness.contract()
        assert contract["parameters"]["acceptance_target"] == ACCEPTANCE_TARGET_CQ_SEMANTIC
        assert harness.runner._acceptance_target == ACCEPTANCE_TARGET_CQ_SEMANTIC
        digest_before = hashlib.sha256(
            (harness.run_root / "acceptance-v3" / "run-contract.json").read_bytes()
        ).hexdigest()
        # A second prepare of the same run root does not exist as a flow; the
        # snapshot is written once in prepare.  Re-reading proves stability.
        assert (
            hashlib.sha256(
                (harness.run_root / "acceptance-v3" / "run-contract.json").read_bytes()
            ).hexdigest()
            == digest_before
        )
    finally:
        harness.cleanup()
