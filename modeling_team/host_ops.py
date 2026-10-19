"""R3.0-016 S1 local host operation layer (交付设计 §3–§9).

This module is the reusable local operation layer behind the host-only MCP
tool surface ``host_ops_mcp``.  It provides:

- safe ``run_id`` → run-root resolution (design §8);
- read-only run status snapshots, incremental event cursors and pending-action
  derivation (design §6/§7) with zero side effects;
- bounded ``control/outer-input.fifo`` writes that reuse the existing outer
  action envelopes, plus the host-private ``control/host-requests.jsonl``
  submission ledger (design §5.2);
- request-result correlation against the Runner-side
  ``evidence/outer-input-receipts.jsonl`` receipts (design §5.4/§5.5).

Boundaries (design §1/§8): the layer never imports the Runner runtime, never
instantiates ``TeamRunner``, never judges business semantics, never approves
anything and never reopens write gates.  Natural-language understanding,
business judgment and authorization decisions stay with the host.  Read tools
perform no drain, no model call, no recovery, no cleanup and no platform
write; only the pure contract helpers from ``competency_questions`` and the
read-only liveness helpers from ``checkpoint_recovery`` are reused.

Typed errors follow design §9: Runner rejections keep their original codes and
semantics (:class:`HostOpError.as_envelope` copies the passthrough fields
instead of folding them into a generic failure), and the new op-layer codes
are only the minimal transport/correlation/read set listed there.
"""

from __future__ import annotations

import base64
import binascii
import errno
import hashlib
import json
import os
import re
import select
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple
from urllib.parse import urlsplit

import yaml

from .checkpoint_recovery import (
    chain_writer_lock_report,
    http_readback,
    load_origin_record,
    pid_is_alive,
)
from .checkpoint_recovery import (
    settle_source_run as settle_source_run_record,
)
from .checkpoints import CheckpointError
from .checkpoints import inspect_checkpoints as inspect_checkpoints_readonly
from .handoff_materials import HandoffMaterials, MaterialError
from .competency_questions import (
    CQ_ACCEPTANCE_COMPLETE_FIELDS,
    CQ_FREEZE_DIRECTORY,
    CQ_REVIEW_SCHEMA,
    CQContractError,
    batch_report_acceptance_verdict,
    content_digest,
    reload_frozen_pool,
)

# The transport layer's line limit (``OuterInputFifo`` default).  The op layer
# refuses an oversized line before writing anything so no half line is ever
# written; tests assert the constant matches the transport default.
FIFO_MAX_LINE_BYTES = 65_536
FIFO_OPEN_TIMEOUT_SECONDS = 3.0
FIFO_WRITE_TIMEOUT_SECONDS = 3.0

# Design §6: single-event byte cap; oversized complete lines surface as a
# truncated placeholder instead of returning whole log payloads.
EVENT_LINE_BYTE_CAP = 256 * 1024
EVENTS_DEFAULT_LIMIT = 200
EVENTS_MAX_LIMIT = 1000
CURSOR_VERSION = 1

REQUEST_ID_MAX_LENGTH = 128

# Recorded ``state.json`` states after which the foreground admission path is
# gone.  ``ABORTING``/``CLEANING`` stay non-terminal here: the Runner may still
# be processing outer input while winding down, and a false
# ``outer_input_channel_unavailable`` would hide a live channel.
TERMINAL_STATES = frozenset({"CLEANED", "FAILED", "TERMINAL_REPORT_COMPLETE"})
ISSUE_WAITING_STATES = frozenset({"WAITING_OWNER", "ABORTING"})

# Design §7.1 "阶段": stage-indicating evidence sources for the latest-stage
# field.  Sources are probed in this order; the latest ``recorded_at`` wins.
STAGE_SOURCES = (
    "coordination-phase",
    "semantic-start",
    "staged-decisions",
    "multi-slice-workflow",
    "multi-slice-gate",
    "cq-interview",
    "cq-review-request",
    "cq-review-decision",
    "cq-freeze",
    "cq-handoff-complete",
    "cq-acceptance-complete",
    "settled",
    "team-lifecycle",
    "terminal-classification",
)

# Per-action evidence files for ``get_request_result`` references (design
# §5.4: an accepted receipt links to the action-specific consumption evidence).
ACTION_EVIDENCE: dict[str, str] = {
    "user": "evidence/outer-user.jsonl",
    "question": "evidence/outer-question.jsonl",
    "instruction": "evidence/outer-instruction.jsonl",
    "cq_interview": "evidence/cq-interview.jsonl",
    "cq_review": "evidence/cq-review-decision.jsonl",
    "cq_freeze": "evidence/cq-freeze.jsonl",
    "cq_handoff_complete": "evidence/cq-handoff-complete.jsonl",
    "cq_acceptance_complete": "evidence/cq-acceptance-complete.jsonl",
    "issue_resolution": "evidence/issue-resolution.jsonl",
    "recover_provider": "evidence/provider-wait.jsonl",
    "standby": "evidence/team-lifecycle.jsonl",
    "consult": "evidence/team-lifecycle.jsonl",
    "pause": "evidence/team-lifecycle.jsonl",
    "resume": "evidence/team-lifecycle.jsonl",
}

RECEIPTS_EVIDENCE = "evidence/outer-input-receipts.jsonl"
HOST_REQUESTS_LEDGER = "control/host-requests.jsonl"
HOST_SUPERVISOR_RECORD = "control/host-supervisor.json"
OUTER_INPUT_FIFO = "control/outer-input.fifo"

# --- R3.0-016 S2 (design §5/§6/§9): managed launch + lifecycle/checkpoint ops ---

# Runs-root dot directory holding the host-owned launch registrations and the
# per-launch stdout/stderr logs.  It follows the `.recovery-locks/` /
# `.recovery-settlements/` runs-root dot-directory precedent (design §6.2).
HOST_LAUNCHES_DIRECTORY = ".host-launches"
HOST_LAUNCH_RECORD_SCHEMA = "modeling-team-host-launch/v1"
# S1 §7.1 supervisor record schema: the Runner never writes it; the S2 launch
# operation writes it for the process it just started.
HOST_SUPERVISOR_SCHEMA = "modeling-team-host-supervisor/v1"

HOST_LAUNCH_KINDS = ("run", "checkpoint_resume", "checkpoint_settle")
HOST_LAUNCH_STATUS_LAUNCHED = "launched"
HOST_LAUNCH_STATUS_EXITED = "exited"

# Design §6.2: the launch operation polls for the run root for at most this
# long (0.5s interval) and then returns without blocking on the modeling work.
LAUNCH_RUN_ROOT_WAIT_SECONDS = 10.0
LAUNCH_RUN_ROOT_POLL_SECONDS = 0.5
# Design §5/§9: bounded local writes for the launch registration surfaces.
HOST_RECORD_WRITE_BOUND_SECONDS = 3.0

HOST_CREDENTIAL_ENV = "ONTOLOGY_PLATFORM_ADMIN_API_KEY"
DEFAULT_PLATFORM_BASE_URL = "http://127.0.0.1:8001"

# The exact flags of the encapsulated CLI entry points (design §5.1/§5.5 and
# the frozen argv contract): the op layer passes inputs through under their
# original CLI names and never invents a flag the subcommand does not have.
RUN_SUBCOMMAND_FLAGS = (
    "--profile",
    "--task",
    "--task-overlay",
    "--model-profile",
    "--run-id",
    "--scope",
    "--base-url",
    "--freeze-started-at",
    "--enable-outer-input-fifo",
)
CHECKPOINT_RESUME_FLAGS = (
    "--runtime",
    "--run-id",
    "--checkpoint-id",
    "--new-run-id",
    "--mode",
    "--session-timeout",
    "--model-profile",
    "--question-visibility",
    "--authorization-reference",
    "--base-url",
    "--freeze-started-at",
    "--write-tail-run-id",
    "--enable-outer-input-fifo",
)

# Where the Runner records the consumption of a lifecycle/checkpoint action
# (design §5.2/§5.4 return contract). Cooperative controls and consultation
# append actual acknowledgements to the lifecycle evidence stream.
LIFECYCLE_CONSUMPTION_EVIDENCE = {
    "pause": "evidence/team-lifecycle.jsonl",
    "resume": "evidence/team-lifecycle.jsonl",
    "stop": "state.json",
    "checkpoint": "evidence/checkpoints.jsonl",
    "standby": "state.json",
    "consult": "evidence/team-lifecycle.jsonl",
}


class HostOpError(Exception):
    """Typed op-layer error carrying the design §9 envelope.

    ``passthrough`` keeps original Runner rejection fields (``run_id``,
    ``issue_id``, ``phase``, ``retry`` ...) next to the envelope keys so no
    typed rejection is folded into a generic "execution failed".
    """

    def __init__(
        self,
        code: str,
        reason: str,
        *,
        obj: str | None = None,
        retryable: bool = False,
        next_action: str | None = None,
        passthrough: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.obj = obj
        self.retryable = retryable
        self.next_action = next_action
        self.passthrough = dict(passthrough or {})

    def as_envelope(self) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "code": self.code,
            "reason": self.reason,
            "retryable": self.retryable,
        }
        if self.obj is not None:
            envelope["object"] = self.obj
        if self.next_action is not None:
            envelope["next_action"] = self.next_action
        envelope.update(self.passthrough)
        return envelope

    @classmethod
    def from_outer_rejection(cls, payload: dict[str, Any]) -> HostOpError:
        """Map one Runner ``outer-input-rejected`` payload (design §9)."""

        passthrough = {
            key: payload[key]
            for key in ("run_id", "issue_id", "reporter_id", "control_epoch")
            if payload.get(key) is not None
        }
        return cls(
            str(payload.get("code") or "invalid_outer_input"),
            str(payload.get("detail") or "the Runner rejected the outer input"),
            retryable=bool(payload.get("retryable")),
            next_action="fix the reported binding and resend with a NEW request_id",
            passthrough=passthrough,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def default_repository_root() -> Path:
    """The repository root that owns this checkout's run workspace."""

    return Path(__file__).resolve().parent.parent


# --- run-root resolution (design §8) --------------------------------------------


def _validated_run_root(
    run_id: str, *, repository_root: Path | None = None
) -> tuple[Path, Path]:
    """Shape + containment check for ``run_id`` without an existence gate.

    S2 launch operations must be able to name a run root that does not exist
    yet (design §5.1/§5.5 pre-checks).  The rules are exactly the S1 ones; only
    the ``run_not_found`` existence gate is left to the caller.
    """

    if (
        not isinstance(run_id, str)
        or not run_id
        or len(run_id) > REQUEST_ID_MAX_LENGTH
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or "\0" in run_id
        or os.path.basename(run_id) != run_id
    ):
        raise HostOpError(
            "run_id_invalid",
            "run_id must be a non-empty single path component of at most "
            f"{REQUEST_ID_MAX_LENGTH} characters",
            obj="run_id",
            retryable=False,
            next_action="pass the modeling Team run id exactly as recorded",
        )
    root = Path(repository_root) if repository_root is not None else default_repository_root()
    runs_root = (root / "workspaces" / "modeling-runs").resolve()
    run_root = runs_root / run_id
    try:
        resolved = run_root.resolve()
        resolved.relative_to(runs_root)
    except (OSError, ValueError) as exc:
        raise HostOpError(
            "run_id_invalid",
            f"run id {run_id!r} does not resolve inside {runs_root}",
            obj="run_id",
            retryable=False,
            next_action="pass the modeling Team run id exactly as recorded",
        ) from exc
    return resolved, runs_root


def resolve_run_root(
    run_id: str, *, repository_root: Path | None = None
) -> tuple[Path, Path]:
    """Resolve ``run_id`` to ``(run_root, runs_root)`` under the workspace.

    ``run_id`` must be a non-empty string without path separators, ``.`` or
    ``..`` components and at most 128 characters; the resolved directory must
    stay inside ``<repository_root>/workspaces/modeling-runs``.  Anything else
    is a typed ``run_id_invalid`` / ``run_not_found`` rejection -- never an
    arbitrary path read primitive.
    """

    resolved, runs_root = _validated_run_root(run_id, repository_root=repository_root)
    if not resolved.is_dir():
        raise HostOpError(
            "run_not_found",
            f"no run directory exists for run id {run_id!r} under {runs_root}",
            obj="run_id",
            retryable=False,
            next_action="check the run id; read-only tools only see runs on this machine",
        )
    return resolved, runs_root


# --- shared read helpers --------------------------------------------------------


def _read_json_file(path: Path) -> tuple[Any | None, str | None]:
    """Read one JSON file; return ``(value, limitation)`` -- never raise."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path.name} is unreadable: {exc.strerror or exc}"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"{path.name} is not valid JSON: {exc.msg}"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read complete JSONL lines; corrupt lines become limitations, not errors."""

    records: list[dict[str, Any]] = []
    limitations: list[str] = []
    try:
        raw = path.read_bytes()
    except OSError:
        return [], []
    if raw and not raw.endswith(b"\n"):
        limitations.append(f"{path.name} ends with an unterminated partial line")
    for line_no, line in enumerate(raw.split(b"\n")[:-1] if raw else [], start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            limitations.append(f"{path.name} line {line_no} is not valid JSON: {exc}")
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            limitations.append(f"{path.name} line {line_no} is not a JSON object")
    return records, limitations


def _read_state(run_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    value, limitation = _read_json_file(run_root / "state.json")
    if value is not None and not isinstance(value, dict):
        return None, "state.json is not a JSON object"
    return value, limitation


def _evidence_source(run_root: Path, name: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Read one evidence source; corrupt lines surface as limitations."""

    return _read_jsonl(run_root / "evidence" / f"{name}.jsonl")


def _evidence_records(run_root: Path, name: str) -> list[dict[str, Any]]:
    records, _ = _read_jsonl(run_root / "evidence" / f"{name}.jsonl")
    return records


def _latest(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The record with the greatest ``recorded_at`` (stable for equal stamps)."""

    best: dict[str, Any] | None = None
    best_key = ""
    for record in records:
        stamp = record.get("recorded_at")
        if isinstance(stamp, str) and stamp >= best_key:
            best_key = stamp
            best = record
    return best


# --- get_run_status (design §7.1) -----------------------------------------------


def _read_yaml_file(path: Path) -> tuple[Any | None, str | None]:
    """Read one YAML file; return ``(value, limitation)`` -- never raise."""

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path.name} is unreadable: {exc.strerror or exc}"
    try:
        return yaml.safe_load(raw), None
    except yaml.YAMLError as exc:
        return None, f"{path.name} is not valid YAML: {exc}"


def _identity_block(run_root: Path, run_id: str) -> tuple[dict[str, Any], list[str]]:
    """Identity from the run root only; ``run_id`` is not a session id."""

    limitations: list[str] = []
    identity: dict[str, Any] = {
        "run_id": run_id,
        "run_root": f"workspaces/modeling-runs/{run_id}",
        "run_id_note": "run_id is the modeling Team run id, not a platform session_id",
        "task_snapshot": None,
        "task_id": None,
        "profile_snapshot": None,
        "profile_id": None,
        "runtime": None,
        "baseline_manifest": None,
        "model_binding": "unknown",
        "model_binding_source": "unavailable",
        "platform_binding": None,
    }
    for name in ("task.snapshot.yaml", "profile.snapshot.yaml"):
        if not (run_root / name).is_file():
            limitations.append(f"{name} is missing; identity fields stay unknown")
    profile, profile_limitation = _read_yaml_file(run_root / "profile.snapshot.yaml")
    if profile_limitation:
        limitations.append(profile_limitation)
    elif isinstance(profile, dict):
        identity["profile_snapshot"] = "profile.snapshot.yaml"
        if isinstance(profile.get("profile_id"), str):
            identity["profile_id"] = profile["profile_id"]
        if isinstance(profile.get("runtime"), str):
            identity["runtime"] = profile["runtime"]
        model_profile = profile.get("model_profile")
        if isinstance(model_profile, str) and model_profile:
            identity["model_binding"] = model_profile
            identity["model_binding_source"] = "profile.snapshot.yaml"
    task, task_limitation = _read_yaml_file(run_root / "task.snapshot.yaml")
    if task_limitation:
        limitations.append(task_limitation)
    elif isinstance(task, dict):
        identity["task_snapshot"] = "task.snapshot.yaml"
        if isinstance(task.get("task_id"), str):
            identity["task_id"] = task["task_id"]
        model_profile = task.get("model_profile")
        if (
            identity["model_binding"] == "unknown"
            and isinstance(model_profile, str)
            and model_profile
        ):
            identity["model_binding"] = model_profile
            identity["model_binding_source"] = "task.snapshot.yaml"
    if (run_root / "baseline-manifest.json").is_file():
        identity["baseline_manifest"] = "baseline-manifest.json"
    return identity, limitations


def _recorded_state_block(
    run_root: Path,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    state, limitation = _read_state(run_root)
    if state is None:
        if limitation:
            return None, None, [limitation]
        return None, "state.json is missing; the recorded state is unknown", []
    extras = {
        key: value
        for key, value in state.items()
        if key not in {"state", "run_id", "cleanup", "terminal_results"}
    }
    terminal_results = state.get("terminal_results")
    statuses = (
        {
            agent: result.get("status")
            for agent, result in terminal_results.items()
            if isinstance(result, dict)
        }
        if isinstance(terminal_results, dict)
        else None
    )
    block = {
        "state": state.get("state"),
        "extra_fields": extras,
        "has_cleanup_record": isinstance(state.get("cleanup"), dict),
        "terminal_result_statuses": statuses,
    }
    return block, limitation, []


def _last_activity(run_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    evidence_dir = run_root / "evidence"
    best: dict[str, Any] | None = None
    best_key = ""
    sources = 0
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.glob("*.jsonl")):
            sources += 1
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            for line in raw.splitlines():
                try:
                    value = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict) and isinstance(value.get("recorded_at"), str):
                    stamp = value["recorded_at"]
                    if stamp >= best_key:
                        best_key = stamp
                        best = {"recorded_at": stamp, "source": path.name}
    limitations = []
    if best is None:
        limitations.append("no evidence record with a recorded_at stamp was readable")
    return best, limitations


def _stage_block(run_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    best: dict[str, Any] | None = None
    best_key = ""
    for source in STAGE_SOURCES:
        record = _latest(_evidence_records(run_root, source))
        if record is None:
            continue
        stamp = record.get("recorded_at")
        if isinstance(stamp, str) and stamp >= best_key:
            best_key = stamp
            summary: dict[str, Any] = {"source": f"evidence/{source}.jsonl", "recorded_at": stamp}
            for key in ("phase", "batch_id", "review_id", "classification", "ordinal"):
                if isinstance(record.get(key), (str, int)):
                    summary[key] = record[key]
            best = summary
    return best, []


def _semantic_progress_block(run_root: Path) -> dict[str, Any]:
    starts = _evidence_records(run_root, "semantic-start")
    staged = _evidence_records(run_root, "staged-decisions")
    classification = _latest(_evidence_records(run_root, "terminal-classification"))
    return {
        "semantic_start_count": len(starts),
        "first_semantic_start_at": starts[0].get("recorded_at") if starts else None,
        "staged_decision_count": len(staged),
        "latest_staged_decision_at": (
            _latest(staged) or {}).get("recorded_at") if staged else None,
        "terminal_classification": (
            {
                "classification": classification.get("classification"),
                "complete_modeling_quality_result": classification.get(
                    "complete_modeling_quality_result"
                ),
            }
            if classification
            else None
        ),
        "note": "RUNNING is recorded state, not semantic progress; these are "
        "recorded facts only",
    }


def _issue_pending(run_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Derive the current cooperative issue wait (design §7.2 issue row).

    ``issue-resolution`` records persist guidance, but do not prove that the
    corresponding control reached the reporter.  Only an issue-control
    terminal dispatch, or the Runner's matching abort-control record, closes
    the host-side wait; informational control events (which carry ``event``)
    remain pending until the actual dispatch record.
    """

    reports, report_limits = _evidence_source(run_root, "issue-report")
    limitations = list(report_limits)
    if not reports:
        return None, limitations
    _, resolution_limits = _evidence_source(run_root, "issue-resolution")
    controls, control_limits = _evidence_source(run_root, "issue-control")
    aborts, abort_limits = _evidence_source(run_root, "issue-abort")
    limitations.extend(resolution_limits)
    limitations.extend(control_limits)
    limitations.extend(abort_limits)
    report_epochs = {
        record.get("issue_id"): record.get("control_epoch")
        for record in reports
        if isinstance(record.get("issue_id"), str)
    }
    resolved = {
        record.get("issue_id")
        for record in controls
        if (
            isinstance(record.get("issue_id"), str)
            and record.get("action") in {"resume", "abort"}
            and "event" not in record
        )
    }
    resolved.update(
        issue_id
        for record in aborts
        for issue_id in [record.get("issue_id")]
        if (
            isinstance(issue_id, str)
            and record.get("action") == "abort"
            and "event" not in record
            and isinstance(record.get("control_epoch"), int)
            and not isinstance(record.get("control_epoch"), bool)
            and isinstance(report_epochs.get(issue_id), int)
            and not isinstance(report_epochs.get(issue_id), bool)
            and record["control_epoch"] == report_epochs[issue_id]
        )
    )
    # The latest reported issue without a terminal control dispatch wins
    # (recorded order in the file); persisted guidance and waiting events do
    # not hide a still-unsettled issue.
    active = None
    for record in reports:
        issue_id = record.get("issue_id")
        if isinstance(issue_id, str) and issue_id not in resolved:
            active = record
    state, _ = _read_state(run_root)
    state_issue_id = state.get("issue_id") if isinstance(state, dict) else None
    if active is None:
        return None, limitations
    issue_id = active.get("issue_id")
    control_epoch = active.get("control_epoch")
    for record in controls:
        if (
            record.get("issue_id") == issue_id
            and isinstance(record.get("control_epoch"), int)
            and not isinstance(record.get("control_epoch"), bool)
            and (active.get("recorded_at") or "") <= (record.get("recorded_at") or "")
        ):
            control_epoch = record["control_epoch"]
    if isinstance(state_issue_id, str) and state_issue_id != issue_id:
        limitations.append(
            f"state.json names issue {state_issue_id!r} while the latest open "
            f"issue-report is {issue_id!r}; bindings follow the issue-report record"
        )
    item = {
        "id": issue_id,
        "type": "issue_wait",
        "status": state.get("state") if isinstance(state, dict) else "unknown",
        "category": active.get("category"),
        "bindings": {
            "issue_id": issue_id,
            "reporter_id": active.get("reporter_id"),
            "control_epoch": control_epoch,
        },
        "summary_ref": "evidence/issue-report.jsonl",
        "recorded_at": active.get("recorded_at"),
        "available_actions": [
            {
                "action": "resolve_issue",
                "required_bindings": ["issue_id", "reporter_id", "control_epoch",
                                      "resolution_type", "resolution_text"],
                "note": "guidance/abort take resolution_text; repair_completed "
                "additionally binds repair_component",
            }
        ],
    }
    return item, limitations


PROVIDER_WAIT_CLOSE_EVENTS = frozenset({"host-recovery", "cleared"})


def _provider_pending(run_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-agent provider waits not closed by host recovery (design §7.2).

    A wait opens with its ``observed`` record and closes only when the same
    agent later records ``host-recovery`` or ``cleared``.  Every other event
    leaves the state unchanged: ``issue-report-unavailable``,
    ``issue-reported`` and ``coordinator-delivery-failed`` arrive while the
    wait is still pending, and ``issue-settlement-skipped`` follows
    ``host-recovery`` without reopening it.  Runtime wait snapshots carry no
    ``event`` key at all and are equally informational.  Records are consumed
    in file order: ``provider-wait.jsonl`` is append-only, so file order is
    the causal order (I-D2).
    """

    events, event_limits = _evidence_source(run_root, "provider-wait")
    if not events:
        return [], list(event_limits)
    observed_by_agent: dict[str, dict[str, Any]] = {}
    closed_agents: set[str] = set()
    for record in events:
        agent_id = record.get("agent_id")
        if not isinstance(agent_id, str):
            continue
        event = record.get("event")
        if event == "observed":
            observed_by_agent[agent_id] = record
            closed_agents.discard(agent_id)
        elif event in PROVIDER_WAIT_CLOSE_EVENTS:
            closed_agents.add(agent_id)
        # Any other event (or a runtime snapshot without ``event``) is
        # informational: it neither opens nor closes the wait.
    items: list[dict[str, Any]] = []
    for agent_id in sorted(observed_by_agent):
        if agent_id in closed_agents:
            continue
        record = observed_by_agent[agent_id]
        wait_id = record.get("wait_id")
        items.append(
            {
                "id": f"{agent_id}:{wait_id}",
                "type": "provider_wait",
                "status": "waiting",
                "agent_id": agent_id,
                "role": record.get("role"),
                "variant": record.get("variant"),
                "wait_id": wait_id,
                "recorded_at": record.get("recorded_at"),
                "available_actions": [
                    {
                        "action": "recover_provider",
                        "required_bindings": ["agent_id or role", "text"],
                        "optional_bindings": ["wait_id"],
                        "note": "the Runner re-checks the pending wait at "
                        "admission time",
                    }
                ],
            }
        )
    return items, list(event_limits)


def _owner_questions_pending(
    run_root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Displayed-minus-answered owner questions (design §7.2 question row)."""

    limitations: list[str] = []
    questions, question_limits = _evidence_source(run_root, "outer-question")
    limitations.extend(question_limits)
    answers, answer_limits = _evidence_source(run_root, "outer-user")
    limitations.extend(answer_limits)
    answered: set[str] = set()
    legacy_answers = 0
    for record in answers:
        delivery_id = record.get("question_delivery_id")
        if isinstance(delivery_id, str) and delivery_id:
            answered.add(delivery_id)
        else:
            legacy_answers += 1
    if legacy_answers:
        limitations.append(
            f"{legacy_answers} outer-user record(s) carry no question binding "
            "(legacy run); answered questions cannot be reliably deducted"
        )
    failures, failure_limits = _evidence_source(run_root, "owner-answer-failure")
    limitations.extend(failure_limits)
    if failures:
        # Real failure records carry owner_answer_id/release_id only (verified
        # against retained run recordings).  The Runner burns the question
        # BEFORE the answer attempt (runner.py marks it consumed ahead of
        # persistence/send), so a failed answer leaves the question consumed
        # on the Runner side while this file-derived view — lacking a
        # question_delivery_id binding in the failure record — cannot deduct
        # it; the limitation below makes that gap visible instead (I-D3).
        limitations.append(
            f"{len(failures)} owner-answer-failure record(s) exist; they bind no "
            "question delivery, so this view cannot deduct them (the Runner "
            "consumes the question before the attempt; a retry is rejected)"
        )
    counts: dict[str, int] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for record in questions:
        delivery_id = record.get("question_delivery_id")
        if not isinstance(delivery_id, str):
            continue
        counts[delivery_id] = counts.get(delivery_id, 0) + 1
        by_id[delivery_id] = record
    items: list[dict[str, Any]] = []
    for delivery_id in sorted(counts):
        if delivery_id in answered:
            continue
        record = by_id[delivery_id]
        displayed = counts[delivery_id] >= 2
        item = {
            "id": delivery_id,
            "type": "owner_question",
            "status": "displayed" if displayed else "registered_not_displayed",
            "question_delivery_id": delivery_id,
            "text": record.get("text"),
            "recorded_at": record.get("recorded_at"),
            "available_actions": [
                {
                    "action": "answer_question",
                    "channel": "user",
                    "required_bindings": ["question_delivery_id", "text"],
                }
            ],
        }
        if not displayed:
            item["reason"] = (
                "the registration record exists but the display record has not "
                "appeared yet; the Runner rejects answers to undisplayed questions"
            )
        items.append(item)
    return items, limitations


def _cq_window_state(run_root: Path) -> dict[str, Any]:
    """CQ interview/review window state from file evidence only (design §7.2).

    ``cq-wait-windows.jsonl`` only records a cleanup-time ``closed-on-exit``
    line and is deliberately NOT a source: the runtime window state is derived
    from the latest ``cq-interview`` ``wait_window_open`` snapshot plus the
    review request/decision transitions, all of which are evidence files.
    """

    transitions: list[tuple[str, str, Any]] = []
    cq_limitations: list[str] = []
    for name, kind in (
        ("cq-interview", "interview"),
        ("cq-review-request", "review_open"),
        ("cq-review-decision", "review_close"),
    ):
        records, file_limits = _evidence_source(run_root, name)
        cq_limitations.extend(file_limits)
        for record in records:
            if isinstance(record.get("recorded_at"), str):
                transitions.append((record["recorded_at"], kind, record))
    transitions.sort(key=lambda item: item[0])
    interview_open: bool | None = None
    review_open = False
    for _stamp, kind, record in transitions:
        if kind == "interview":
            interview_open = bool(record.get("wait_window_open"))
        elif kind == "review_open":
            review_open = True
            interview_open = False
        else:
            review_open = False
    return {
        "interview_window_open": interview_open,
        "review_window_open": review_open,
        "any_transition": bool(transitions),
        "limitations": cq_limitations,
    }


def _cq_pending(run_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    items: list[dict[str, Any]] = []
    windows = _cq_window_state(run_root)
    limitations.extend(windows["limitations"])
    if windows["interview_window_open"]:
        items.append(
            {
                "id": "cq-interview-wait",
                "type": "cq_interview_window",
                "status": "open",
                "available_actions": [
                    {
                        "action": "answer_question",
                        "channel": "cq_interview",
                        "required_bindings": ["text"],
                        "optional_bindings": ["wait_for_draft"],
                    }
                ],
            }
        )
    requests, request_limits = _evidence_source(run_root, "cq-review-request")
    limitations.extend(request_limits)
    decisions, decision_limits = _evidence_source(run_root, "cq-review-decision")
    limitations.extend(decision_limits)
    decided = {
        record.get("review_id")
        for record in decisions
        if isinstance(record.get("review_id"), str)
    }
    latest_request = _latest(requests)
    if latest_request is not None:
        review_id = latest_request.get("review_id")
        if isinstance(review_id, str) and review_id not in decided:
            snapshot_rel = f"competency-questions/reviews/{review_id}.json"
            snapshot, snapshot_limitation = _read_json_file(run_root / snapshot_rel)
            if snapshot_limitation:
                limitations.append(snapshot_limitation)
            binding: dict[str, Any] = {
                "review_id": review_id,
                "phase": latest_request.get("phase"),
                "content_digest": latest_request.get("content_digest"),
                "question_ids": latest_request.get("question_ids"),
                "review_snapshot_ref": snapshot_rel,
            }
            if isinstance(snapshot, dict):
                binding["content_version"] = snapshot.get("content_version")
                binding["draft_ref"] = snapshot.get("draft_ref")
            else:
                limitations.append(
                    f"the review snapshot {snapshot_rel} is missing or unreadable; "
                    "decision bindings beyond the evidence record stay unknown"
                )
            items.append(
                {
                    "id": review_id,
                    "type": "cq_review",
                    "status": "pending",
                    "bindings": binding,
                    "recorded_at": latest_request.get("recorded_at"),
                    "available_actions": [
                        {
                            "action": "submit_cq_review",
                            "required_bindings": [
                                "review_id",
                                "question_id",
                                "decision",
                                "content_version",
                                "content_digest",
                            ],
                            "optional_bindings": ["revision", "modified_question", "note"],
                            "note": "schema_version is filled by the tool; the "
                            "Runner validates the review/question/content bindings "
                            "against the snapshot; revision is a positive reviewer "
                            "ordinal and is not stored in the snapshot; decision must "
                            "be approve, modify, delete or supplement; modify/supplement "
                            "require modified_question as a complete question object, "
                            "not a question-text string",
                        }
                    ],
                }
            )
    freeze_records, freeze_limits = _evidence_source(run_root, "cq-freeze")
    limitations.extend(freeze_limits)
    freeze = _latest(freeze_records)
    handoff_records, handoff_limits = _evidence_source(run_root, "cq-handoff-complete")
    limitations.extend(handoff_limits)
    handoff = _latest(handoff_records)
    acceptance_records, acceptance_limits = _evidence_source(run_root, "cq-acceptance-complete")
    limitations.extend(acceptance_limits)
    acceptance = _latest(acceptance_records)
    if freeze is not None and handoff is None:
        items.append(
            {
                "id": freeze.get("batch_id"),
                "type": "cq_handoff",
                "status": "frozen_awaiting_handoff",
                "bindings": {
                    "freeze_id": freeze.get("batch_id"),
                    "freeze_digest": freeze.get("snapshot_digest"),
                },
                "public_question_ids": freeze.get("public_question_ids"),
                "hidden_question_count": freeze.get("hidden_question_count"),
                "recorded_at": freeze.get("recorded_at"),
                "available_actions": [
                    {
                        "action": "complete_cq_handoff",
                        "required_bindings": ["freeze_id", "freeze_digest"],
                        "optional_bindings": ["delivery_binding"],
                    }
                ],
            }
        )
    if freeze is None and decisions:
        items.append(
            {
                "id": "cq-freeze",
                "type": "cq_freeze_pending",
                "status": "reviewed_not_frozen",
                "recorded_at": (_latest(decisions) or {}).get("recorded_at"),
                "available_actions": [
                    {
                        "action": "freeze_cq",
                        "required_bindings": [],
                        "note": "the Runner rejects freezing while any published "
                        "question still lacks a user decision",
                    }
                ],
            }
        )
    if handoff is not None:
        phase = handoff.get("acceptance_phase")
        if acceptance is not None:
            items.append(
                {
                    "id": acceptance.get("acceptance_attempt_id"),
                    "type": "cq_acceptance_closure",
                    "status": "completed",
                    "bindings": {
                        "cq_verdict": acceptance.get("cq_verdict"),
                        "report_digest": acceptance.get("report_digest"),
                        "acceptance_attempt_id": acceptance.get("acceptance_attempt_id"),
                    },
                    "recorded_at": acceptance.get("recorded_at"),
                    "available_actions": [],
                    "note": "closure completed; completion success is not "
                    "acceptance PASS",
                }
            )
        elif phase == "acceptance_pending":
            items.append(
                {
                    "id": handoff.get("acceptance_attempt_id"),
                    "type": "cq_acceptance_closure",
                    "status": "acceptance_pending",
                    "bindings": {
                        "freeze_id": handoff.get("freeze_id"),
                        "freeze_digest": handoff.get("freeze_digest"),
                        "acceptance_attempt_id": handoff.get("acceptance_attempt_id"),
                        "report_directory": handoff.get("report_directory"),
                    },
                    "recorded_at": handoff.get("recorded_at"),
                    "available_actions": [
                        {
                            "action": "complete_cq_acceptance",
                            "optional_bindings": ["acceptance_attempt_id"],
                            "note": "the report comes from the retained CLI "
                            "cq-acceptance run; the tool computes report_digest "
                            "and cq_verdict from the retained report file",
                        }
                    ],
                }
            )
    return items, limitations


def pending_items(run_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """All design §7.2 pending derivations for one run root (read-only)."""

    items: list[dict[str, Any]] = []
    limitations: list[str] = []
    evidence_dir = run_root / "evidence"
    if not evidence_dir.is_dir():
        limitations.append("the evidence directory is missing; pending derivation is empty")
        return items, limitations
    owner_items, owner_limits = _owner_questions_pending(run_root)
    items.extend(owner_items)
    limitations.extend(owner_limits)
    cq_items, cq_limits = _cq_pending(run_root)
    items.extend(cq_items)
    limitations.extend(cq_limits)
    issue_item, issue_limits = _issue_pending(run_root)
    if issue_item is not None:
        items.append(issue_item)
    limitations.extend(issue_limits)
    provider_items, provider_limits = _provider_pending(run_root)
    items.extend(provider_items)
    limitations.extend(provider_limits)
    return items, limitations


def get_pending_actions(
    run_id: str, *, repository_root: Path | None = None
) -> dict[str, Any]:
    """Design §7.2 pending list: file-derived, no memory inference, no drain."""

    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    items, limitations = pending_items(run_root)
    state, _state_limitation = _read_state(run_root)
    return {
        "run_id": run_id,
        "items": items,
        "recorded_state": state.get("state") if isinstance(state, dict) else None,
        "observed_at": _utc_now(),
        "limitations": sorted(set(limitations)) or ["none"],
        "note": "pending items are file-derived facts; the Runner re-checks "
        "every binding at admission time",
    }


def _process_observation(run_root: Path, runs_root: Path) -> dict[str, Any]:
    """Design §7.1 liveness split (b): process observation only with evidence."""

    origin = load_origin_record(run_root)
    if origin is not None:
        report = chain_writer_lock_report(run_root, origin, runs_root)
        return {
            "basis": "chain_writer_lock",
            "observed_at": _utc_now(),
            "report": report,
        }
    payload, limitation = _read_json_file(run_root / HOST_SUPERVISOR_RECORD)
    if isinstance(payload, dict) and isinstance(payload.get("pid"), int) and not isinstance(
        payload.get("pid"), bool
    ):
        return {
            "basis": "host_supervisor",
            "observed_at": _utc_now(),
            "pid": payload["pid"],
            "pid_alive": pid_is_alive(payload["pid"]),
            "started_at": _optional_str(payload.get("started_at")),
            "session_ref": _optional_str(payload.get("session_ref")),
            **({"limitation": limitation} if limitation else {}),
        }
    return {
        "basis": "unknown",
        "observed_at": _utc_now(),
        "reason": "no recovery origin and no control/host-supervisor.json "
        "registration; recorded state, waits, stage and terminal records stay "
        "authoritative",
    }


def get_run_status(run_id: str, *, repository_root: Path | None = None) -> dict[str, Any]:
    """Design §7.1 snapshot; strictly read-only with per-field sources."""

    run_root, runs_root = resolve_run_root(run_id, repository_root=repository_root)
    from .close_statistics import read_close_statistics
    limitations: list[str] = []
    identity, identity_limits = _identity_block(run_root, run_id)
    limitations.extend(identity_limits)
    recorded_state, state_limitation, state_limits = _recorded_state_block(run_root)
    if state_limitation:
        limitations.append(state_limitation)
    limitations.extend(state_limits)
    stage, _ = _stage_block(run_root)
    last_activity, activity_limits = _last_activity(run_root)
    limitations.extend(activity_limits)
    items, pending_limits = pending_items(run_root)
    limitations.extend(pending_limits)
    terminal_conclusion: dict[str, Any] = {
        "state_json_state": (
            recorded_state.get("state") if recorded_state else None
        ),
        "is_terminal_state": bool(
            recorded_state and recorded_state.get("state") in TERMINAL_STATES
        ),
    }
    classification = _latest(_evidence_records(run_root, "terminal-classification"))
    if classification is not None:
        terminal_conclusion["terminal_classification"] = {
            "classification": classification.get("classification"),
            "complete_modeling_quality_result": classification.get(
                "complete_modeling_quality_result"
            ),
            "recorded_at": classification.get("recorded_at"),
        }
    settled = _latest(_evidence_records(run_root, "settled"))
    if settled is not None:
        terminal_conclusion["settled"] = {"recorded_at": settled.get("recorded_at")}
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    evidence_refs = []
    evidence_dir = run_root / "evidence"
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.glob("*.jsonl")):
            evidence_refs.append(
                {
                    "path": f"evidence/{path.name}",
                    "readable": os.access(path, os.R_OK),
                }
            )
    else:
        limitations.append("the evidence directory is missing")
    for name in ("state.json", "task.snapshot.yaml", "profile.snapshot.yaml"):
        evidence_refs.append(
            {
                "path": name,
                "readable": (run_root / name).is_file()
                and os.access(run_root / name, os.R_OK),
            }
        )
    return {
        "run_id": run_id,
        "identity": identity,
        "close_statistics": read_close_statistics(run_root),
        "recorded_state": recorded_state,
        "stage": stage,
        "last_verifiable_activity": (
            {**({"basis": "evidence-file"} if last_activity else {}), **(last_activity or {})}
        ),
        "semantic_progress": _semantic_progress_block(run_root),
        "first_blocker": _first_blocker(run_root, items),
        "pending_summary": {"counts": counts, "detail_tool": "get_pending_actions"},
        "terminal_conclusion": terminal_conclusion,
        "lifecycle": recorded_state.get("lifecycle") if recorded_state else None,
        "work_state": recorded_state.get("work_state") if recorded_state else None,
        "write_phase": recorded_state.get("write_phase") if recorded_state else None,
        "retained_members": recorded_state.get("retained_members", []) if recorded_state else [],
        "liveness": {
            "recorded_state": recorded_state.get("state") if recorded_state else None,
            "process_observation": _process_observation(run_root, runs_root),
            "fifo_present": (run_root / OUTER_INPUT_FIFO).exists(),
            "fifo_note": "FIFO presence is an independent fact, not liveness or "
            "semantic-progress evidence",
        },
        "events_cursor": _encode_cursor(run_id, _current_offsets(run_root)),
        "observed_at": _utc_now(),
        "evidence_refs": evidence_refs,
        "limitations": sorted(set(limitations)) or ["none"],
    }


def _first_blocker(
    run_root: Path, items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Runtime-failure first, then issue wait, then provider wait (§7.1)."""

    failure = _latest(_evidence_records(run_root, "runtime-failure"))
    if failure is not None:
        return {
            "kind": "runtime_failure",
            "source": "evidence/runtime-failure.jsonl",
            "recorded_at": failure.get("recorded_at"),
            "event": failure.get("event"),
        }
    for kind in ("issue_wait", "provider_wait", "cq_interview_window", "cq_review"):
        for item in items:
            if item.get("type") == kind:
                return {
                    "kind": kind,
                    "id": item.get("id"),
                    "source": "pending derivation (design §7.2)",
                    "recorded_at": item.get("recorded_at"),
                }
    return None


# --- get_run_events (design §6) --------------------------------------------------


def _current_offsets(run_root: Path) -> dict[str, int]:
    offsets: dict[str, int] = {}
    evidence_dir = run_root / "evidence"
    if not evidence_dir.is_dir():
        return offsets
    for path in sorted(evidence_dir.glob("*.jsonl")):
        try:
            offsets[path.name] = path.stat().st_size
        except OSError:
            continue
    return offsets


def _encode_cursor(run_id: str, offsets: dict[str, int]) -> str:
    payload = json.dumps(
        {"v": CURSOR_VERSION, "run_id": run_id, "offsets": offsets},
        sort_keys=True,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None, run_id: str) -> dict[str, int]:
    if cursor is None or cursor == "":
        return {}
    try:
        payload = json.loads(
            base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
        )
    except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError) as exc:
        raise HostOpError(
            "cursor_invalid",
            f"the cursor is not a decodable v{CURSOR_VERSION} cursor: {exc}",
            obj="cursor",
            retryable=False,
            next_action="restart from offset 0 (no cursor) if losing the position is "
            "acceptable; otherwise recover the original cursor",
        ) from exc
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        raise HostOpError(
            "cursor_invalid",
            "unsupported cursor version "
            f"{payload.get('v') if isinstance(payload, dict) else None!r}",
            obj="cursor",
            retryable=False,
            next_action="use a cursor returned by this interface",
        )
    if payload.get("run_id") != run_id:
        raise HostOpError(
            "cursor_run_mismatch",
            f"the cursor belongs to run {payload.get('run_id')!r}, not {run_id!r}",
            obj="cursor",
            retryable=False,
            next_action="re-read the target run from offset 0 with no cursor",
        )
    offsets = payload.get("offsets")
    if not isinstance(offsets, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and value >= 0
        for key, value in offsets.items()
    ):
        raise HostOpError(
            "cursor_invalid",
            "the cursor offsets payload is malformed",
            obj="cursor",
            retryable=False,
            next_action="use a cursor returned by this interface",
        )
    return dict(offsets)


def _complete_line_remains(handle: Any) -> bool:
    """Probe whether another DELIVERABLE line follows the read cap.

    ``has_more`` must never promise a page the next call cannot fill: a lone
    trailing half line is deferred (not deliverable), so it must not pin
    ``has_more`` true.  A complete line (newline-terminated) or an oversized
    remainder (delivered as a truncated placeholder) does.
    """

    probe = handle.readline(EVENT_LINE_BYTE_CAP + 1)
    return probe.endswith(b"\n") or len(probe) > EVENT_LINE_BYTE_CAP


def _scan_source(
    path: Path, start: int, limit: int
) -> tuple[list[tuple[str, int, int, dict[str, Any], int | None]], int, bool, list[str]]:
    """Read complete lines from ``start``; return candidates and scan state.

    Each candidate is ``(sort_stamp, line_no, end_offset, item, recorded_at)``
    where ``item`` is either the event wrapper or an explicit corrupt/truncated
    placeholder.  ``scanned_end`` is the file position after the last consumed
    line (cumulative across the scan); ``stopped_early`` is true when the
    per-source read cap was hit with another deliverable line remaining.
    ``line_no`` counts lines
    consumed by THIS scan (it restarts at 1 on each continuation), so the
    unambiguous position of an event is its ``byte_offset``: the offset of the
    line's first byte within the source (I-D4).
    """

    candidates: list[tuple[str, int, int, dict[str, Any], int | None]] = []
    limitations: list[str] = []
    try:
        with path.open("rb") as handle:
            handle.seek(start)
            position = start
            line_no = 0
            stopped_early = False
            while True:
                line = handle.readline(EVENT_LINE_BYTE_CAP + 1)
                if not line:
                    break
                line_no += 1
                line_start = position
                end = line_start + len(line)
                if not line.endswith(b"\n"):
                    if len(line) <= EVENT_LINE_BYTE_CAP:
                        # Half line at EOF: defer it; the offset does not advance.
                        break
                    # An oversized line: emit the truncated placeholder and
                    # consume the whole line (up to and including its newline)
                    # so later calls resume at the next record boundary.
                    remainder = handle.readline()
                    end = line_start + len(line) + len(remainder)
                    candidates.append(
                        (
                            _sort_stamp(None),
                            line_no,
                            end,
                            {
                                "source": path.name,
                                "line_no": line_no,
                                "byte_offset": line_start,
                                "truncated": True,
                                "byte_length": len(line) + len(remainder),
                            },
                            None,
                        )
                    )
                    limitations.append(
                        f"{path.name} line {line_no} exceeds the "
                        f"{EVENT_LINE_BYTE_CAP}-byte event cap and is truncated"
                    )
                    position = end
                    if len(candidates) >= limit:
                        stopped_early = _complete_line_remains(handle)
                        break
                    continue
                # A complete line always advances the offset past itself, so
                # ``position`` accumulates across the lines of one scan and the
                # returned offsets stay at record boundaries (I-D1: a page
                # must never resume inside a line it already delivered).
                position = end
                if len(line) > EVENT_LINE_BYTE_CAP:
                    candidates.append(
                        (
                            _sort_stamp(None),
                            line_no,
                            end,
                            {
                                "source": path.name,
                                "line_no": line_no,
                                "byte_offset": line_start,
                                "truncated": True,
                                "byte_length": len(line),
                            },
                            None,
                        )
                    )
                    limitations.append(
                        f"{path.name} line {line_no} exceeds the "
                        f"{EVENT_LINE_BYTE_CAP}-byte event cap and is truncated"
                    )
                else:
                    try:
                        value = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        candidates.append(
                            (
                                _sort_stamp(None),
                                line_no,
                                end,
                                {
                                    "source": path.name,
                                    "line_no": line_no,
                                    "byte_offset": line_start,
                                    "corrupt": True,
                                    "parse_error": str(exc),
                                },
                                None,
                            )
                        )
                        limitations.append(
                            f"{path.name} line {line_no} is not valid JSON: {exc}"
                        )
                    else:
                        stamp = (
                            value.get("recorded_at")
                            if isinstance(value, dict)
                            else None
                        )
                        candidates.append(
                            (
                                _sort_stamp(stamp if isinstance(stamp, str) else None),
                                line_no,
                                end,
                                {
                                    "source": path.name,
                                    "line_no": line_no,
                                    "byte_offset": line_start,
                                    "recorded_at": stamp if isinstance(stamp, str) else None,
                                    "data": value,
                                },
                                stamp if isinstance(stamp, str) else None,
                            )
                        )
                if len(candidates) >= limit:
                    stopped_early = _complete_line_remains(handle)
                    # ``probe`` after the cap check: reading further would only
                    # grow memory; the remaining bytes stay for the next call.
                    break
            return candidates, position, stopped_early, limitations
    except OSError as exc:
        limitations.append(f"{path.name} could not be scanned: {exc.strerror or exc}")
        return [], start, False, limitations


def _sort_stamp(stamp: str | None) -> tuple[int, str]:
    return (0, stamp) if stamp is not None else (1, "")


class _EventCandidate(NamedTuple):
    """One scanned complete line of one evidence source (design §6)."""

    byte_offset: int  # offset of the line's first byte in the source
    end: int  # offset just past the line (its terminating newline)
    stamp_key: tuple[int, str]  # _sort_stamp(recorded_at); stamp-less sorts last
    line_no: int  # line's position within THIS scan (restarts per continuation)
    source: str  # evidence file name, e.g. "outer-question.jsonl"
    item: dict[str, Any]  # the event wrapper or corrupt/truncated placeholder


def get_run_events(
    run_id: str,
    *,
    cursor: str | None = None,
    limit: int | None = EVENTS_DEFAULT_LIMIT,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §6 incremental event read: per-source byte offsets, no drain."""

    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    limitations: list[str] = []
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        limitations.append(f"limit {limit!r} is invalid; using {EVENTS_DEFAULT_LIMIT}")
        limit = EVENTS_DEFAULT_LIMIT
    if limit > EVENTS_MAX_LIMIT:
        limitations.append(f"limit {limit} clamped to {EVENTS_MAX_LIMIT}")
        limit = EVENTS_MAX_LIMIT
    offsets = _decode_cursor(cursor, run_id)
    evidence_dir = run_root / "evidence"
    sources: list[Path] = sorted(evidence_dir.glob("*.jsonl")) if evidence_dir.is_dir() else []
    if not sources:
        return {
            "run_id": run_id,
            "events": [],
            "next_cursor": _encode_cursor(run_id, {}),
            "has_more": False,
            "ordering": "recorded_at-approximate",
            "complete": True,
            "limitations": ["no evidence event sources exist for this run"],
        }
    # --- page selection: parked-head guarantee + merge fill (I3-D1 rewrite) ---
    #
    # Per-source pools hold the complete-line candidates scanned from each
    # source's cursor offset, in file order.  Selection invariants:
    #
    #   * head guarantee: pool[0] is the source's parked line -- the previous
    #     page's minimum undelivered byte offset -- so it is always due a
    #     delivery slot, whatever its stamp.  When limit < number of non-empty
    #     pools the heads compete in (head byte_offset, source) order: parks
    #     only ever move forward, so a source can win again only after the
    #     others moved past it -- starvation-free and deterministic for any
    #     limit >= 1.
    #   * progress: a non-empty pool always contributes its winning head, and
    #     a head delivery strictly advances that source's park, so every page
    #     delivers at least one line and pagination converges within
    #     (#lines + #sources + 1) pages.  A page following has_more=True is
    #     therefore never empty.
    #   * fill: remaining slots (if any) go to the pools' other candidates in
    #     global merge order (stamp, source, line_no).  Re-delivery inside a
    #     parked window is allowed: delivery is at-least-once per line and the
    #     host deduplicates by (source, byte_offset).
    #   * page order: the selection decides WHICH events a page returns; the
    #     returned list stays in global merge order, preserving the
    #     recorded_at-approximate contract (design §6).
    pools: dict[str, list[_EventCandidate]] = {}
    next_offsets: dict[str, int] = {}
    stopped_early_by_source: dict[str, bool] = {}
    for path in sources:
        start = int(offsets.get(path.name, 0))
        try:
            size = path.stat().st_size
        except OSError as exc:
            limitations.append(f"{path.name} stat failed: {exc.strerror or exc}")
            continue
        if start > size:
            limitations.append(
                f"{path.name} shrank below the cursor offset ({start} > {size}); "
                "resuming this source from 0"
            )
            start = 0
        read_candidates, _scanned_end, stopped_early, scan_limits = _scan_source(
            path, start, limit
        )
        limitations.extend(scan_limits)
        next_offsets[path.name] = start
        stopped_early_by_source[path.name] = stopped_early
        pools[path.name] = [
            _EventCandidate(
                byte_offset=item.get("byte_offset", start),
                end=end,
                stamp_key=stamp_key,
                line_no=line_no,
                source=path.name,
                item=item,
            )
            for stamp_key, line_no, end, item, _stamp in read_candidates
        ]

    selected: list[_EventCandidate] = []
    selected_ids: set[tuple[str, int]] = set()
    for head in sorted(
        (pool[0] for pool in pools.values() if pool),
        key=lambda cand: (cand.byte_offset, cand.source),
    ):
        if len(selected) >= limit:
            break
        selected.append(head)
        selected_ids.add((head.source, head.byte_offset))
    if len(selected) < limit:
        rest = sorted(
            (
                candidate
                for pool in pools.values()
                for candidate in pool[1:]
            ),
            key=lambda cand: (cand.stamp_key, cand.source, cand.line_no),
        )
        for candidate in rest:
            if len(selected) >= limit:
                break
            selected.append(candidate)
            selected_ids.add((candidate.source, candidate.byte_offset))

    for source, pool in pools.items():
        # Park (I2-D1): the offset moves only up to the FIRST UNDELIVERED
        # candidate of the source in file order; delivering a physically later
        # line must never skip an earlier undelivered one (a stamp-less
        # placeholder sorts last; a late-appended line carries an early
        # stamp).  When every scanned candidate was delivered the offset
        # advances to the scan frontier (last end, else the unchanged start).
        undelivered_starts = [
            candidate.byte_offset
            for candidate in pool
            if (source, candidate.byte_offset) not in selected_ids
        ]
        if undelivered_starts:
            next_offsets[source] = min(undelivered_starts)
        else:
            next_offsets[source] = max(
                [candidate.end for candidate in pool] + [next_offsets[source]]
            )

    # ``has_more`` only counts deliverable candidates: pool candidates left
    # unselected by this page, or a source whose read hit the per-source scan
    # cap with another deliverable line remaining.  A trailing half line is
    # deferred, not deliverable, so it never pins ``has_more`` true.
    leftover = sum(len(pool) for pool in pools.values()) - len(selected)
    has_more = leftover > 0 or any(stopped_early_by_source.values())

    selected.sort(key=lambda cand: (cand.stamp_key, cand.source, cand.line_no))
    return {
        "run_id": run_id,
        "events": [candidate.item for candidate in selected],
        "next_cursor": _encode_cursor(run_id, next_offsets),
        "has_more": bool(has_more),
        "ordering": "recorded_at-approximate",
        "complete": not any(
            "is not valid JSON" in limitation or "truncated" in limitation
            for limitation in limitations
        ),
        "limitations": limitations or ["none"],
    }


# --- host request ledger + bounded FIFO submission (design §5.2/§9) --------------


def _append_host_request(
    run_root: Path, request_id: str | None, action: str, digest: str
) -> None:
    control = run_root / "control"
    control.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = run_root / HOST_REQUESTS_LEDGER
    record = {
        "request_id": request_id,
        "action": action,
        "content_digest": digest,
        "submitted_at": _utc_now(),
    }
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, line)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ledger_entries(run_root: Path, request_id: str) -> list[dict[str, Any]]:
    entries, _ = _read_jsonl(run_root / "control" / "host-requests.jsonl")
    return [
        entry
        for entry in entries
        if entry.get("request_id") == request_id
    ]


def _receipt_entries(run_root: Path, request_id: str) -> list[dict[str, Any]]:
    entries, _ = _read_jsonl(run_root / RECEIPTS_EVIDENCE)
    return [entry for entry in entries if entry.get("request_id") == request_id]


def _validate_request_id(request_id: str | None) -> None:
    if request_id is None:
        return
    if (
        not isinstance(request_id, str)
        or not request_id
        or len(request_id) > REQUEST_ID_MAX_LENGTH
    ):
        raise HostOpError(
            "request_id_invalid",
            "request_id must be a non-empty string of at most "
            f"{REQUEST_ID_MAX_LENGTH} characters",
            obj="request_id",
            retryable=False,
            next_action="resend with a fresh request_id or none at all",
        )


def _write_fifo_line(fifo: Path, encoded: bytes) -> None:
    """Bounded open+write (design §9): O_NONBLOCK open, poll, typed timeouts."""

    deadline = time.monotonic() + FIFO_OPEN_TIMEOUT_SECONDS
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno not in (errno.ENXIO, errno.ENOENT):
                raise
            if time.monotonic() >= deadline:
                raise HostOpError(
                    "outer_input_channel_unavailable",
                    "no Runner reader opened the outer-input FIFO within "
                    f"{FIFO_OPEN_TIMEOUT_SECONDS:.0f}s; nothing was written",
                    retryable=False,
                    next_action="check run liveness via get_run_status before "
                    "resending",
                ) from exc
            time.sleep(0.05)
    try:
        write_deadline = time.monotonic() + FIFO_WRITE_TIMEOUT_SECONDS
        view = memoryview(encoded)
        while view:
            remaining = write_deadline - time.monotonic()
            if remaining <= 0:
                raise HostOpError(
                    "outer_input_write_timeout",
                    f"the FIFO write did not complete within "
                    f"{FIFO_WRITE_TIMEOUT_SECONDS:.0f}s; {len(view)} of "
                    f"{len(encoded)} bytes were not accepted; a partial line may "
                    "be in the pipe",
                    retryable=False,
                    next_action="do not blindly resend: check "
                    "get_request_result and the run events before using a NEW "
                    "request_id",
                )
            poller = select.poll()
            poller.register(descriptor, select.POLLOUT)
            ready = poller.poll(max(remaining, 0.01) * 1000)
            if not ready:
                continue
            try:
                written = os.write(descriptor, view)
            except BlockingIOError:
                continue
            view = view[written:]
    finally:
        os.close(descriptor)


def submit_fifo_action(
    run_id: str,
    action: str,
    envelope: dict[str, Any],
    *,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Write one complete NDJSON outer-action line (design §4/§5.2/§9)."""

    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    _validate_request_id(request_id)
    state, state_limitation = _read_state(run_root)
    if isinstance(state, dict) and state.get("state") in TERMINAL_STATES:
        raise HostOpError(
            "outer_input_channel_unavailable",
            f"the run's recorded state {state.get('state')!r} is terminal; the "
            "outer admission path is closed",
            retryable=False,
            next_action="terminal runs are read-only in S1; settle follow-up "
            "work through the retained CLI records",
        )
    fifo = run_root / OUTER_INPUT_FIFO
    try:
        fifo_stat = os.stat(fifo)
    except FileNotFoundError as exc:
        raise HostOpError(
            "outer_input_channel_unavailable",
            "the run has no outer-input FIFO (not started with "
            "--enable-outer-input-fifo, or the control directory is gone)",
            retryable=False,
            next_action="read-only tools stay available; change actions need a "
            "FIFO-enabled live run",
            passthrough=({"state_limitation": state_limitation} if state_limitation else None),
        ) from exc
    if not stat.S_ISFIFO(fifo_stat.st_mode):
        raise HostOpError(
            "outer_input_channel_unavailable",
            "control/outer-input.fifo exists but is not a FIFO",
            retryable=False,
            next_action="inspect the run root; refusing to write a non-FIFO file",
        )
    payload = dict(envelope)
    if request_id is not None:
        payload["request_id"] = request_id
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if len(encoded) > FIFO_MAX_LINE_BYTES:
        raise HostOpError(
            "fifo_line_too_large",
            f"the encoded envelope is {len(encoded)} bytes, above the "
            f"{FIFO_MAX_LINE_BYTES}-byte FIFO line limit; nothing was written",
            retryable=False,
            next_action="shorten the text or reference an approved artifact and "
            "resend",
        )
    digest = content_digest(envelope)
    if request_id is not None:
        ledger = _ledger_entries(run_root, request_id)
        if ledger:
            entry = ledger[-1]
            if entry.get("content_digest") != digest:
                raise HostOpError(
                    "request_id_conflict",
                    f"request_id {request_id!r} was already submitted with a "
                    "different content digest",
                    obj="request_id",
                    retryable=False,
                    next_action="use a NEW request_id for different content",
                    passthrough={"recorded_content_digest": entry.get("content_digest")},
                )
            receipts = _receipt_entries(run_root, request_id)
            if receipts:
                receipt = receipts[-1]
                if receipt.get("content_digest") != digest:
                    raise HostOpError(
                        "request_id_conflict",
                        f"the receipt for request_id {request_id!r} records a "
                        "different content digest than the ledger",
                        obj="request_id",
                        retryable=False,
                        next_action="inspect evidence/outer-input-receipts.jsonl "
                        "and control/host-requests.jsonl before resending",
                    )
                return _receipt_outcome(run_id, request_id, receipt, idempotent=True)
            return {
                "run_id": run_id,
                "request_id": request_id,
                "action": action,
                "status": "submitted",
                "idempotent": True,
                "note": "this request_id is already in the submission ledger "
                "without a Runner receipt; the line was NOT written again",
                "next_query": "get_request_result",
            }
    _write_fifo_line(fifo, encoded)
    _append_host_request(run_root, request_id, action, digest)
    return {
        "run_id": run_id,
        "request_id": request_id,
        "action": action,
        "status": "submitted",
        "note": "FIFO delivery is not Runner acceptance; poll get_request_result "
        "and the run events",
        "consumption_evidence": ACTION_EVIDENCE.get(action),
    }


def _material_host_error(exc: MaterialError, *, obj: str = "material") -> HostOpError:
    """Translate a scoped handoff failure into the existing Host error tuple."""

    return HostOpError(
        exc.code,
        str(exc),
        obj=obj,
        retryable=exc.code not in {"material_forbidden", "material_media_unsupported"},
        next_action=(
            "choose an authorized material reference and retry the same action"
            if exc.code != "material_forbidden"
            else "use a reference published for this Host channel"
        ),
    )


def _open_run_handoff_store(
    run_id: str, repository_root: Path | None,
) -> tuple[HandoffMaterials, dict[str, str]]:
    """Open the existing run-owned store for direct Host/MCP callers.

    Delivery normally transfers a session package into this store before it
    invokes a FIFO action.  The standalone Host MCP surface has no Python
    object to pass, so it binds the already published Runner package from the
    run root and derives the existing role ids from the frozen profile.
    """

    run_root, _ = resolve_run_root(run_id, repository_root=repository_root)
    agents: list[dict[str, Any]] = []
    try:
        profile = yaml.safe_load(
            (run_root / "profile.snapshot.yaml").read_text(encoding="utf-8")
        )
        agents = profile.get("agents") if isinstance(profile, dict) else []
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        pass
    recipients = {
        str(agent.get("agent_id"))
        for agent in agents
        if isinstance(agent, dict)
        and isinstance(agent.get("agent_id"), str)
        and agent.get("agent_id")
    }
    store = HandoffMaterials(run_root / "handoff-materials", run_id)
    store.register_actor("runner", {}, recipients)
    role_ids = {
        str(agent.get("package")): str(agent.get("agent_id"))
        for agent in agents
        if isinstance(agent, dict)
        and isinstance(agent.get("package"), str)
        and isinstance(agent.get("agent_id"), str)
        and agent.get("agent_id")
    }
    return store, role_ids


def _auto_material_binding(
    run_id: str,
    *,
    channel: str | None = None,
    repository_root: Path | None,
) -> tuple[HandoffMaterials | None, str | None]:
    """Resolve a direct Host call's Runner actor and existing role recipient."""

    if repository_root is None:
        return None, None
    store, role_ids = _open_run_handoff_store(run_id, repository_root)
    role = "coordinator"
    if channel == "user":
        role = "modeling"
    elif channel == "cq_interview":
        role = "competency-question"
    return store, role_ids.get(role, role)


def _material_payload(
    text: str | None,
    *,
    body_ref: dict[str, Any] | None,
    material_refs: list[dict[str, Any]] | None,
    display_text: str | None,
    material_origins: list[dict[str, Any]] | None,
    handoff_materials: HandoffMaterials | None,
    material_actor_id: str,
    material_recipient_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return complete formal text plus separate display/reference metadata.

    The in-process Delivery path supplies ``handoff_materials`` so the Host
    resolves and authorizes the immutable body in the target run before the
    FIFO write.  A body reference without that recipient-bound resolver is
    rejected; a path visible only to the sender is never enough.
    """

    formal_text = text
    if body_ref is not None:
        # A ref without a live target-store resolver would leave the Runner
        # with a path it cannot read.  Inline text is a display hint only in
        # this mode; require the Host to verify the actual recipient binding.
        if handoff_materials is None:
            raise HostOpError(
                "material_source_unavailable",
                "body_ref requires the bound recipient material resolver",
                obj="body_ref",
                retryable=True,
                next_action="retry with the run-bound material resolver",
            )
        try:
            handoff_materials.authorize_ref(material_actor_id, material_recipient_id, body_ref)
            formal_text = handoff_materials.resolve(material_actor_id, body_ref)
        except MaterialError as exc:
            raise _material_host_error(exc, obj="body_ref") from exc
        display = display_text or text or (
            f"Formal content is in handoff material {body_ref.get('material_id')}"
        )
    else:
        display = display_text
    if not isinstance(formal_text, str) or not formal_text.strip():
        raise HostOpError(
            "invalid_owner_answer",
            "text must be a non-empty string unless body_ref resolves complete content",
            obj="text",
            retryable=True,
            next_action="resend complete text or an authorized body_ref",
        )
    refs = material_refs or []
    if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs):
        raise HostOpError(
            "material_path_invalid",
            "material_refs must be a list of reference objects",
            obj="material_refs",
            retryable=True,
            next_action="provide material_id references published for this channel",
        )
    if handoff_materials is not None:
        try:
            for ref in refs:
                handoff_materials.authorize_ref(material_actor_id, material_recipient_id, ref)
        except MaterialError as exc:
            raise _material_host_error(exc, obj="material_refs") from exc
    metadata: dict[str, Any] = {}
    if body_ref is not None:
        metadata["body_ref"] = body_ref
    if refs:
        metadata["material_refs"] = refs
    if material_origins:
        metadata["material_origins"] = material_origins
    if display is not None:
        if not isinstance(display, str) or not display.strip():
            raise HostOpError(
                "material_path_invalid",
                "display_text must be a non-empty string when provided",
                obj="display_text",
                retryable=True,
                next_action="omit display_text or provide its intended short explanation",
            )
        metadata["display_text"] = display
    # ``formal_text`` is returned for pre-write validation only.  A body_ref
    # keeps the FIFO bounded: the wire text is the short display explanation,
    # while the Runner resolves the complete immutable body in its run store.
    return formal_text, metadata


# --- per-action submission builders (design §4) ----------------------------------


def answer_question(
    run_id: str,
    *,
    channel: str,
    text: str | None = None,
    question_delivery_id: str | None = None,
    wait_for_draft: bool | None = None,
    request_id: str | None = None,
    body_ref: dict[str, Any] | None = None,
    material_refs: list[dict[str, Any]] | None = None,
    display_text: str | None = None,
    material_origins: list[dict[str, Any]] | None = None,
    handoff_materials: HandoffMaterials | None = None,
    material_actor_id: str = "host",
    material_recipient_id: str = "runner",
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``answer_question``: the ``user`` and ``cq_interview`` channels."""

    if (body_ref is not None or material_refs) and handoff_materials is None:
        handoff_materials, auto_recipient = _auto_material_binding(
            run_id, channel=channel, repository_root=repository_root
        )
        if handoff_materials is not None:
            material_actor_id = "runner"
            material_recipient_id = auto_recipient or material_recipient_id
    formal_text, material_metadata = _material_payload(
        text,
        body_ref=body_ref,
        material_refs=material_refs,
        display_text=display_text,
        material_origins=material_origins,
        handoff_materials=handoff_materials,
        material_actor_id=material_actor_id,
        material_recipient_id=material_recipient_id,
    )
    if channel == "user":
        if not isinstance(question_delivery_id, str) or not question_delivery_id:
            raise HostOpError(
                "invalid_owner_answer",
                "the user channel requires the question_delivery_id binding "
                "from the pending list",
                obj="question_delivery_id",
                retryable=False,
                next_action="call get_pending_actions and resend with the "
                "displayed question's delivery id",
            )
        wire_text = material_metadata.get("display_text", formal_text) if body_ref is not None else formal_text
        envelope = {
            "action": "user",
            "text": wire_text,
            "question_delivery_id": question_delivery_id,
            **material_metadata,
        }
    elif channel == "cq_interview":
        wire_text = material_metadata.get("display_text", formal_text) if body_ref is not None else formal_text
        envelope = {"action": "cq_interview", "text": wire_text, **material_metadata}
        if wait_for_draft is not None:
            envelope["wait_for_draft"] = wait_for_draft
    else:
        raise HostOpError(
            "invalid_owner_answer",
            "channel must be 'user' or 'cq_interview'; the two channels are "
            "not interchangeable",
            obj="channel",
            retryable=False,
            next_action="use 'user' for owner questions and 'cq_interview' for "
            "the competency-question interview window",
        )
    return submit_fifo_action(
        run_id, "user" if channel == "user" else "cq_interview", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def submit_instruction(
    run_id: str,
    *,
    kind: str,
    text: str | None = None,
    source_reference: str,
    authorization_reference: str,
    request_id: str | None = None,
    body_ref: dict[str, Any] | None = None,
    material_refs: list[dict[str, Any]] | None = None,
    display_text: str | None = None,
    material_origins: list[dict[str, Any]] | None = None,
    handoff_materials: HandoffMaterials | None = None,
    material_actor_id: str = "host",
    material_recipient_id: str = "runner",
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Submit a Delivery instruction without impersonating an owner answer.

    ``user_supplement`` carries an explicit business-source supplement and
    ``delivery_guidance`` carries a host-side control note.  Both use the
    existing outer-input FIFO and request receipt contract, but deliberately
    do not carry ``question_delivery_id`` or any other owner-question binding.
    The Runner remains the authority for whether the instruction can be
    consumed by the current run.
    """

    if kind not in {"user_supplement", "delivery_guidance"}:
        raise HostOpError(
            "instruction_kind_invalid",
            "kind must be 'user_supplement' or 'delivery_guidance'",
            obj="kind",
            retryable=True,
            next_action="choose the instruction kind that matches its source",
        )
    if (body_ref is not None or material_refs) and handoff_materials is None:
        handoff_materials, auto_recipient = _auto_material_binding(
            run_id, repository_root=repository_root
        )
        if handoff_materials is not None:
            material_actor_id = "runner"
            material_recipient_id = auto_recipient or material_recipient_id
    formal_text, material_metadata = _material_payload(
        text,
        body_ref=body_ref,
        material_refs=material_refs,
        display_text=display_text,
        material_origins=material_origins,
        handoff_materials=handoff_materials,
        material_actor_id=material_actor_id,
        material_recipient_id=material_recipient_id,
    )
    for field, value in (
        ("source_reference", source_reference),
        ("authorization_reference", authorization_reference),
    ):
        if not isinstance(value, str) or not value.strip():
            raise HostOpError(
                "instruction_invalid",
                f"{field} must be a non-empty source/authorization reference",
                obj=field,
                retryable=True,
                next_action=f"provide the recorded {field} for this instruction",
            )
    wire_text = material_metadata.get("display_text", formal_text) if body_ref is not None else formal_text
    envelope = {
        "action": "instruction",
        "kind": kind,
        "text": wire_text,
        "source_reference": source_reference,
        "authorization_reference": authorization_reference,
        **material_metadata,
    }
    return submit_fifo_action(
        run_id,
        "instruction",
        envelope,
        request_id=request_id,
        repository_root=repository_root,
    )


def register_question(
    run_id: str,
    *,
    delivery_id: str,
    text: str,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``register_question``: the explicit ``question`` registration action."""

    if not isinstance(delivery_id, str) or not delivery_id.strip():
        raise HostOpError(
            "invalid_outer_question",
            "delivery_id must be a non-empty host-chosen delivery identifier",
            obj="delivery_id",
            retryable=False,
            next_action="choose an explicit delivery id and resend",
        )
    if not isinstance(text, str) or not text.strip():
        raise HostOpError(
            "invalid_outer_question",
            "question text must be a non-empty string",
            obj="text",
            retryable=False,
            next_action="resend with the question text",
        )
    return submit_fifo_action(
        run_id,
        "question",
        {"action": "question", "delivery_id": delivery_id, "text": text},
        request_id=request_id,
        repository_root=repository_root,
    )


def submit_cq_review(
    run_id: str,
    *,
    review_id: str,
    question_id: str,
    decision: Literal["approve", "modify", "delete", "supplement"],
    content_version: int,
    content_digest_value: str,
    revision: int = 1,
    modified_question: dict[str, Any] | None = None,
    note: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Submit approve/modify/delete/supplement using the existing review envelope.

    modify/supplement require a complete modified_question object, with
    question_id, scope, question, answer_points, evidence_refs, unknown,
    proposed_visibility and content_version. Other decisions use null.
    Submission is not acceptance; check get_request_result for Runner validation.
    """

    envelope = {
        "action": "cq_review",
        "schema_version": CQ_REVIEW_SCHEMA,
        "review_id": review_id,
        "question_id": question_id,
        "decision": decision,
        "content_version": content_version,
        "content_digest": content_digest_value,
        "revision": revision,
        "modified_question": modified_question,
        "note": note,
    }
    return submit_fifo_action(
        run_id, "cq_review", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def freeze_cq(
    run_id: str, *, request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``freeze_cq``: the host freeze trigger (review and freeze differ)."""

    return submit_fifo_action(
        run_id, "cq_freeze", {"action": "cq_freeze"},
        request_id=request_id, repository_root=repository_root,
    )


def complete_cq_handoff(
    run_id: str,
    *,
    freeze_id: str,
    freeze_digest: str,
    delivery_binding: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``complete_cq_handoff``: release the production handoff."""

    envelope: dict[str, Any] = {
        "action": "cq_handoff_complete",
        "freeze_id": freeze_id,
        "freeze_digest": freeze_digest,
    }
    if delivery_binding is not None:
        envelope["delivery_binding"] = delivery_binding
    return submit_fifo_action(
        run_id, "cq_handoff_complete", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def _cq_completion_binding(
    run_root: Path, acceptance_attempt_id: str | None
) -> dict[str, Any]:
    """Derive the current acceptance-completion bindings from the run root."""

    freeze = _latest(_evidence_records(run_root, "cq-freeze"))
    handoffs = _evidence_records(run_root, "cq-handoff-complete")
    published_handoff: dict[str, Any] | None = None
    handoff_path = run_root / "acceptance-v3" / "production-handoff.json"
    if handoff_path.is_file() and not handoff_path.is_symlink():
        value, _limitation = _read_json_file(handoff_path)
        if isinstance(value, dict):
            published_handoff = value

    # A resumed Runner restores the immutable freeze snapshot and published
    # handoff, but it does not replay the original cq-freeze event into the
    # new evidence stream.  Rebuild the freeze binding from that retained
    # source rather than asking the host to fabricate an event or freeze it
    # again.  The snapshot is still revalidated before it is trusted.
    if freeze is None and published_handoff is not None:
        expected_batch = published_handoff.get("freeze_id")
        expected_digest = published_handoff.get("freeze_digest")
        freeze_directory = run_root / CQ_FREEZE_DIRECTORY
        snapshot_binding_mismatch = False
        for snapshot_path in sorted(freeze_directory.glob("freeze-*.json")):
            if snapshot_path.is_symlink() or not snapshot_path.is_file():
                continue
            raw_snapshot, _limitation = _read_json_file(snapshot_path)
            if not isinstance(raw_snapshot, dict):
                continue
            try:
                snapshot = reload_frozen_pool(raw_snapshot)
            except CQContractError:
                continue
            if (
                snapshot.get("batch_id") == expected_batch
                and snapshot.get("snapshot_digest") == expected_digest
            ):
                freeze = {
                    "batch_id": snapshot["batch_id"],
                    "snapshot_digest": snapshot["snapshot_digest"],
                }
                break
            snapshot_binding_mismatch = True
        if snapshot_binding_mismatch and freeze is None:
            raise HostOpError(
                "cq_review_stale",
                "the published production handoff does not match the retained freeze",
                obj="cq_acceptance_complete",
                retryable=False,
                next_action="use the immutable freeze and handoff binding from the same run",
            )
    if freeze is None:
        next_action = (
            "restore or verify the immutable frozen snapshot for this run; do not "
            "re-freeze the pool or replay a cq-freeze event"
            if published_handoff is not None
            else "freeze the question pool before the acceptance handoff"
        )
        raise HostOpError(
            "cq_freeze_schema_mismatch",
            "no frozen question pool exists for this run",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action=next_action,
        )
    if not handoffs and published_handoff is None:
        raise HostOpError(
            "cq_review_stale",
            "no production handoff exists for this run yet",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="complete_cq_handoff first; a re-acceptance is requested "
            "as a new handoff",
        )
    if (
        published_handoff is not None
        and acceptance_attempt_id is not None
        and published_handoff.get("acceptance_attempt_id") != acceptance_attempt_id
    ):
        raise HostOpError(
            "cq_review_stale",
            f"no handoff matches acceptance_attempt_id {acceptance_attempt_id!r}",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="call get_pending_actions for the current attempt binding",
        )
    selected_handoff: dict[str, Any] | None = None
    for record in handoffs:
        if (
            acceptance_attempt_id is not None
            and record.get("acceptance_attempt_id") != acceptance_attempt_id
        ):
            continue
        # Evidence is append-only; keep the newest matching record, as the
        # pre-recovery path did, before comparing it with the immutable file.
        selected_handoff = record
    handoff = selected_handoff or published_handoff
    if selected_handoff is not None and published_handoff is not None and any(
            selected_handoff.get(field) != published_handoff.get(field)
            for field in (
                "freeze_id",
                "freeze_digest",
                "acceptance_attempt_id",
                "report_directory",
            )
    ):
        raise HostOpError(
            "cq_review_stale",
            "the evidence handoff does not match the published production handoff",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="read the immutable production handoff and use its current attempt",
        )
    if handoff is None:
        raise HostOpError(
            "cq_review_stale",
            f"no handoff matches acceptance_attempt_id {acceptance_attempt_id!r}",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="call get_pending_actions for the current attempt binding",
        )
    if published_handoff is not None:
        if published_handoff.get("run_id") not in (None, run_root.name):
            raise HostOpError(
                "cq_review_stale",
                "the published production handoff belongs to another run",
                obj="cq_acceptance_complete",
                retryable=False,
                next_action="use the handoff for this run",
            )
        if published_handoff.get("freeze_id") != freeze.get("batch_id") or (
            published_handoff.get("freeze_digest") != freeze.get("snapshot_digest")
        ):
            raise HostOpError(
                "cq_review_stale",
                "the published production handoff does not match the retained freeze",
                obj="cq_acceptance_complete",
                retryable=False,
                next_action="use the immutable freeze and handoff binding from the same run",
            )
    report_directory = handoff.get("report_directory")
    if not isinstance(report_directory, str) or not report_directory:
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            "the handoff record carries no report directory",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="inspect evidence/cq-handoff-complete.jsonl",
        )
    parts = report_directory.split("/")
    if len(parts) != 4 or parts[0] != "acceptance-v3" or parts[1] != "reports":
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            f"the report directory {report_directory!r} is not an "
            "acceptance-v3 attempt directory",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="inspect the handoff record",
        )
    return {
        "freeze_id": freeze.get("batch_id"),
        "freeze_digest": freeze.get("snapshot_digest"),
        "batch_id": parts[2],
        "acceptance_attempt_id": handoff.get("acceptance_attempt_id"),
        "report_directory": report_directory,
    }


def complete_cq_acceptance(
    run_id: str,
    *,
    acceptance_attempt_id: str | None = None,
    continuation_run_id: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``complete_cq_acceptance``: digest/verdict envelope from the report.

    The tool computes ``report_digest`` and ``cq_verdict`` from the retained
    ``batch-report.json`` using the same pure helpers the Runner re-verifies
    with (design §4); a missing/unreadable/mismatched report is rejected here
    without writing the FIFO, so a retry after the report lands can reuse the
    same content (A11-5).
    """

    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    binding = _cq_completion_binding(run_root, acceptance_attempt_id)
    report_path = run_root / binding["report_directory"] / "batch-report.json"
    if continuation_run_id is not None:
        from .checkpoint_recovery import acceptance_continuation_report
        output_root, _ = resolve_run_root(continuation_run_id, repository_root=repository_root)
        try:
            report_path = acceptance_continuation_report(run_root, output_root)
        except (CheckpointError, OSError, ValueError) as exc:
            raise HostOpError("cq_acceptance_report_mismatch", str(exc), obj=continuation_run_id,
                              retryable=True, next_action="verify the closed S4 continuation report and source binding") from exc
    if not report_path.is_file() or report_path.is_symlink():
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            "the registered attempt report is missing",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="let the cq-acceptance process write the attempt report, "
            "then resend",
        )
    try:
        report_bytes = report_path.read_bytes()
    except OSError as exc:
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            f"the retained attempt report is unreadable: {exc.strerror or exc}",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="let the cq-acceptance process rewrite the attempt report",
        ) from exc
    report_digest = f"sha256:{hashlib.sha256(report_bytes).hexdigest()}"
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            f"the retained attempt report is not readable JSON: {exc}",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="let the cq-acceptance process rewrite the attempt report",
        ) from exc
    if not isinstance(report, dict):
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            "the retained attempt report is not a JSON object",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="let the cq-acceptance process rewrite the attempt report",
        )
    selection = report.get("question_selection", {"visibility": "hidden"})
    if not isinstance(selection, dict) or selection.get("visibility") != "hidden":
        raise HostOpError(
            "cq_acceptance_report_mismatch", "public regression cannot complete hidden acceptance",
            obj="cq_acceptance_complete", retryable=True,
            next_action="run the frozen hidden batch and submit its retained report",
        )
    cq_verdict = batch_report_acceptance_verdict(report)
    envelope = {
        "action": "cq_acceptance_complete",
        "run_id": run_id,
        "freeze_id": binding["freeze_id"],
        "freeze_digest": binding["freeze_digest"],
        "batch_id": binding["batch_id"],
        "acceptance_attempt_id": binding["acceptance_attempt_id"],
        "report_digest": report_digest,
        "cq_verdict": cq_verdict,
    }
    if continuation_run_id is not None:
        envelope["continuation_run_id"] = continuation_run_id
    if set(envelope) - {"continuation_run_id"} != set(CQ_ACCEPTANCE_COMPLETE_FIELDS):
        raise HostOpError(
            "cq_acceptance_report_mismatch",
            "internal error: the assembled envelope does not match the "
            "cq_acceptance_complete field contract",
            obj="cq_acceptance_complete",
            retryable=False,
            next_action="report this as an implementation defect",
        )
    return submit_fifo_action(
        run_id, "cq_acceptance_complete", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def resolve_issue(
    run_id: str,
    *,
    issue_id: str,
    reporter_id: str,
    control_epoch: int,
    resolution_type: str,
    resolution_text: str | None = None,
    repair_component: str | None = None,
    before_digest: str | None = None,
    after_digest: str | None = None,
    verification_reference: str | None = None,
    mutation_reconciliation: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Submit guidance/abort text or the separate repair-completed envelope."""

    repair_fields = (
        ("repair_component", repair_component),
        ("before_digest", before_digest),
        ("after_digest", after_digest),
        ("verification_reference", verification_reference),
        ("mutation_reconciliation", mutation_reconciliation),
    )
    if resolution_type in {"guidance", "abort"}:
        for field, value in repair_fields:
            if value is not None:
                raise HostOpError(
                    "invalid_issue_resolution",
                    f"{field} is only supported for repair_completed",
                    obj=field,
                    retryable=True,
                    next_action="remove repair-only fields and submit guidance/abort with "
                    "resolution_text; retain any guidance source reference in that text",
                )

    envelope: dict[str, Any] = {
        "action": "issue_resolution",
        "issue_id": issue_id,
        "reporter_id": reporter_id,
        "control_epoch": control_epoch,
        "resolution_type": resolution_type,
    }
    for key, value in (
        ("resolution_text", resolution_text),
        *repair_fields,
    ):
        if value is not None:
            envelope[key] = value
    return submit_fifo_action(
        run_id, "issue_resolution", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def recover_provider(
    run_id: str,
    *,
    text: str,
    agent_id: str | None = None,
    role: str | None = None,
    wait_id: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """``recover_provider``: host takeover of one pending provider wait."""

    if not isinstance(text, str) or not text.strip():
        raise HostOpError(
            "invalid_provider_recovery",
            "recovery text must be a non-empty string",
            obj="text",
            retryable=False,
            next_action="resend with the recovery explanation",
        )
    if (agent_id is None) == (role is None):
        raise HostOpError(
            "invalid_provider_recovery",
            "exactly one of agent_id or role is required",
            obj="agent_id",
            retryable=False,
            next_action="bind the recovery to one pending wait via "
            "get_pending_actions",
        )
    envelope: dict[str, Any] = {
        "action": "recover_provider",
        "run_id": run_id,
        "text": text,
    }
    if agent_id is not None:
        envelope["agent_id"] = agent_id
    if role is not None:
        envelope["role"] = role
    if wait_id is not None:
        envelope["wait_id"] = wait_id
    return submit_fifo_action(
        run_id, "recover_provider", envelope,
        request_id=request_id, repository_root=repository_root,
    )


# --- get_request_result (design §5.4) --------------------------------------------


def _receipt_outcome(
    run_id: str, request_id: str, receipt: dict[str, Any], *, idempotent: bool = False
) -> dict[str, Any]:
    action = receipt.get("action")
    if receipt.get("outcome") == "accepted":
        return {
            "run_id": run_id,
            "request_id": request_id,
            "outcome": "accepted",
            "action": action,
            "ack_type": receipt.get("ack_type"),
            "content_digest": receipt.get("content_digest"),
            "receipt_ref": RECEIPTS_EVIDENCE,
            "consumption_evidence": ACTION_EVIDENCE.get(action if isinstance(action, str) else ""),
            "idempotent": idempotent,
            "note": "acceptance is not modeling progress or a semantic start; "
            "follow the consumption evidence and get_run_events",
        }
    result = {
        "run_id": run_id,
        "request_id": request_id,
        "outcome": "rejected",
        "action": action,
        "code": receipt.get("code"),
        "content_digest": receipt.get("content_digest"),
        "receipt_ref": RECEIPTS_EVIDENCE,
        "idempotent": idempotent,
        "next_action": "fix the reported binding and resend with a NEW request_id",
    }
    if receipt.get("detail"):
        result["reason"] = receipt["detail"]
    if receipt.get("retry"):
        result["retryable"] = True
        result["next_action"] = receipt["retry"] + "; resend with a NEW request_id"
    return result


def get_request_result(
    run_id: str, *, request_id: str, repository_root: Path | None = None
) -> dict[str, Any]:
    """Design §5.4 resolution order: receipt → ledger+alive → unknown → error."""

    from .close_statistics import read_close_statistics
    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    _validate_request_id(request_id)
    receipts = _receipt_entries(run_root, request_id)
    if receipts:
        receipt = receipts[-1]
        ledger = _ledger_entries(run_root, request_id)
        if ledger and ledger[-1].get("content_digest") != receipt.get("content_digest"):
            raise HostOpError(
                "request_id_conflict",
                "the ledger and the receipt record different content digests "
                f"for request_id {request_id!r}",
                obj="request_id",
                retryable=False,
                next_action="inspect control/host-requests.jsonl and "
                "evidence/outer-input-receipts.jsonl before resending",
            )
        return {**_receipt_outcome(run_id, request_id, receipt),
                "close_statistics": read_close_statistics(run_root)}
    ledger = _ledger_entries(run_root, request_id)
    if not ledger:
        raise HostOpError(
            "request_id_unknown",
            f"no submission ledger entry for request_id {request_id!r} in this "
            "run; request_id correlation covers only submissions made through "
            "this interface, and legacy no-request_id messages leave no "
            "correlation record",
            obj="request_id",
            retryable=False,
            next_action="check the run_id and the request_id, or resend with a "
            "new request_id",
        )
    entry = ledger[-1]
    state, _limitation = _read_state(run_root)
    terminal = isinstance(state, dict) and state.get("state") in TERMINAL_STATES
    fifo_present = (run_root / OUTER_INPUT_FIFO).exists()
    if terminal or not fifo_present:
        return {
            "close_statistics": read_close_statistics(run_root),
            "run_id": run_id,
            "request_id": request_id,
            "outcome": "unknown",
            "action": entry.get("action"),
            "submitted_at": entry.get("submitted_at"),
            "observed_at": _utc_now(),
            "reason": (
                "the run reached a terminal recorded state without a Runner "
                "receipt for this request_id"
                if terminal
                else "the outer-input FIFO disappeared without a Runner receipt "
                "for this request_id"
            ),
            "next_action": "do not auto-resend or switch to a new request_id to "
            "bypass; reconcile against the run evidence directly",
        }
    return {
        "close_statistics": read_close_statistics(run_root),
        "run_id": run_id,
        "request_id": request_id,
        "outcome": "submitted",
        "action": entry.get("action"),
        "submitted_at": entry.get("submitted_at"),
        "observed_at": _utc_now(),
        "note": "the last known fact is a successful FIFO write; re-query "
        "get_request_result after the Runner processes the line",
    }


# --- R3.0-016 S2: launch / lifecycle / checkpoint operation layer (design §5/§6) --


def resolve_repo_path(
    value: Any, *, field: str, repository_root: Path | None = None
) -> Path:
    """Design §8 path containment for a repo-relative input reference.

    ``task``/``profile``/``task_overlay``/``scope`` are passed through to the
    encapsulated CLI under their original names; this helper only proves the
    value resolves inside the repository root (symlinks resolved, then
    re-checked) before anything is executed or read.  Nothing else is checked:
    existence and contract validity stay with the CLI/Runner.
    """

    root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else default_repository_root()
    )
    if not isinstance(value, str) or not value.strip():
        raise HostOpError(
            "input_path_invalid",
            f"{field} must be a non-empty repository-relative or in-repository "
            "absolute path string",
            obj=field,
            retryable=False,
            next_action=f"pass the {field} reference as recorded inside this "
            "repository checkout",
        )
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HostOpError(
            "input_path_invalid",
            f"{field} {value!r} does not resolve inside the repository root "
            f"{root}",
            obj=field,
            retryable=False,
            next_action=f"pass a {field} reference inside this repository "
            "checkout; nothing was executed or read",
        ) from exc
    return resolved


def validate_freeze_started_at(value: Any, *, field: str = "freeze_started_at") -> str:
    """Design §5.1 shape gate: tz-aware ISO-8601, passed through verbatim.

    The op layer never substitutes, fills or rewrites a timepoint and never
    judges its truth: for multi-slice budget-exempt runs the platform has no
    freeze-time gate at all, so the real-timepoint discipline is the host's
    (design §3.1/§5.5).  A value that is missing, not a string, not an
    ISO-8601 timestamp or timezone-naive is rejected without any side effect.
    """

    def _invalid(reason: str) -> HostOpError:
        return HostOpError(
            "freeze_started_at_invalid",
            reason,
            obj=field,
            retryable=True,
            next_action="provide the real freeze-start record of this round; "
            "the tool never fills in the current time or rewrites the value",
            passthrough={},
        )

    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            f"{field} is required and must be a timezone-aware ISO-8601 "
            "timepoint; the tool never substitutes the current time"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _invalid(f"{field} {value!r} is not an ISO-8601 timepoint: {exc}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid(
            f"{field} {value!r} carries no UTC offset; a timezone-naive "
            "timepoint is not accepted"
        )
    return value


def _validate_base_url(value: Any, *, field: str = "base_url") -> str:
    if not isinstance(value, str) or not value.strip():
        raise HostOpError(
            "launch_arguments_invalid",
            f"{field} must be a non-empty http(s) URL",
            obj=field,
            retryable=True,
            next_action=f"pass the platform base URL as an http:// or https:// "
            f"address (default {DEFAULT_PLATFORM_BASE_URL})",
        )
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HostOpError(
            "launch_arguments_invalid",
            f"{field} {value!r} is not an http(s) URL",
            obj=field,
            retryable=True,
            next_action="pass an http:// or https:// platform base URL",
        )
    return value


def _require_host_credential() -> str:
    """Design §5.5/§5.6: the shared host credential channel, fail closed.

    The credential value is only ever read into the process environment
    hand-off; it is never recorded, logged or echoed (appendix A.3).
    """

    value = os.environ.get(HOST_CREDENTIAL_ENV)
    if not value:
        raise HostOpError(
            "host_credential_missing",
            f"the host environment does not set {HOST_CREDENTIAL_ENV}; the "
            "checkpoint resume/settle entries share the run command's host "
            "credential channel and fail closed without it",
            retryable=True,
            next_action="inject the host platform credential into the host "
            "process environment; repository configuration files are never "
            "modified",
        )
    return value


def _atomic_write_json(path: Path, payload: dict[str, Any], *, what: str) -> None:
    """Bounded atomic registration write (design §6.2): tmp file + rename.

    A torn read of `.host-launches/<run_id>.json` would corrupt the very
    evidence the reaper and the pre-checks rely on, so every write lands in a
    uniquely named temporary file and is moved into place with ``os.replace``.
    """

    deadline = time.monotonic() + HOST_RECORD_WRITE_BOUND_SECONDS
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise HostOpError(
            "run_launch_failed",
            f"{what} could not be written: {exc.strerror or exc}",
            obj=str(path.name),
            retryable=False,
            next_action="check the runs-root permissions; no run was started "
            "and no existing record was overwritten",
        ) from exc
    if time.monotonic() > deadline:
        raise HostOpError(
            "run_launch_failed",
            f"{what} took longer than {HOST_RECORD_WRITE_BOUND_SECONDS:.0f}s; "
            "the launch was not started",
            obj=str(path.name),
            retryable=False,
            next_action="check the host machine's I/O health and retry with "
            "the same explicit run id",
        )


def _host_launches_root(runs_root: Path) -> Path:
    return runs_root / HOST_LAUNCHES_DIRECTORY


def launch_record_path(
    run_id: str, *, repository_root: Path | None = None
) -> tuple[Path, Path]:
    """The contained `.host-launches/<run_id>.json` path and its runs root."""

    _run_root, runs_root = _validated_run_root(run_id, repository_root=repository_root)
    return _host_launches_root(runs_root) / f"{run_id}.json", runs_root


def read_launch_record(
    run_id: str, *, repository_root: Path | None = None
) -> dict[str, Any] | None:
    """The host-owned launch registration for ``run_id`` (design §6.2), or None."""

    path, _runs_root = launch_record_path(run_id, repository_root=repository_root)
    payload, _limitation = _read_json_file(path)
    return payload if isinstance(payload, dict) else None


def _launch_log_paths(run_id: str, runs_root: Path) -> dict[str, str]:
    directory = _host_launches_root(runs_root)
    return {
        "stdout": f"{HOST_LAUNCHES_DIRECTORY}/{run_id}.out.log",
        "stderr": f"{HOST_LAUNCHES_DIRECTORY}/{run_id}.err.log",
        "directory": str(directory),
    }


def _record_launch_observation(
    run_id: str, record: dict[str, Any], observed: bool, supervisor_written: bool
) -> dict[str, Any]:
    limitation = None
    if not observed:
        limitation = (
            "the run root did not appear within "
            f"{LAUNCH_RUN_ROOT_WAIT_SECONDS:.0f}s, so no supervisor record was "
            "written and the process observation stays unknown; the process "
            "keeps starting and get_run_status becomes queryable once prepare "
            "creates the run root"
        )
    return {
        "run_id": run_id,
        "launched": True,
        "pid": record.get("pid"),
        **({"supervisor_ref": HOST_SUPERVISOR_RECORD} if supervisor_written else {}),
        "launch_record": record,
        "observation_limitation": limitation,
    }


def _managed_launch(
    argv: list[str], *, cwd: str, env: dict[str, str], stdout: int, stderr: int
) -> subprocess.Popen:
    """The default launcher: one detached session, no shell, no handle held.

    ``start_new_session=True`` keeps the modeling run alive when the host MCP
    server exits (design §6.1); the host never joins the modeling work.
    """

    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _spawn_exit_reaper(process: Any, record_path: Path, run_id: str) -> None:
    """Design §6.1: the only observer that flips ``status`` to ``exited``.

    The per-launch daemon thread calls ``wait()`` without a timeout, so a long
    modeling run never accumulates as a zombie inside the host process and no
    tool call ever joins it.  Best effort by design: if the record cannot be
    read or written the registration stays ``launched`` -- the same documented
    limitation as a host that exited before the child did.
    """

    def _reap() -> None:
        try:
            exit_code = process.wait()
        except Exception:  # noqa: BLE001 - a daemon thread must never crash the host
            return
        try:
            record, _limitation = _read_json_file(record_path)
            if not isinstance(record, dict) or record.get("run_id") != run_id:
                return
            if record.get("status") != HOST_LAUNCH_STATUS_LAUNCHED:
                return
            _atomic_write_json(
                record_path,
                {
                    **record,
                    "status": HOST_LAUNCH_STATUS_EXITED,
                    "exit_code": exit_code,
                    "exited_at": _utc_now(),
                    "recorded_at": _utc_now(),
                },
                what=f"the exit record for run id {run_id!r}",
            )
        except (HostOpError, OSError):
            return

    threading.Thread(
        target=_reap, name=f"modeling-team-launch-reaper-{run_id}", daemon=True
    ).start()


def _await_run_root(run_root: Path, window_seconds: float) -> bool:
    """Bounded non-blocking poll for the run root (design §6.2, ≤10s total)."""

    deadline = time.monotonic() + max(window_seconds, 0.0)
    while True:
        if run_root.is_dir():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(LAUNCH_RUN_ROOT_POLL_SECONDS, remaining))


def _write_supervisor_record(
    run_root: Path,
    *,
    pid: int,
    started_at: str,
    session_ref: str | None,
) -> bool:
    """Idempotent ``control/host-supervisor.json`` write (design §6.2).

    "存在即不改写": an existing record for the same pid is left untouched, and
    a record naming a *different* pid is never overwritten -- the conflict is
    reported as ``run_launch_in_progress`` for manual adjudication instead
    (appendix A.6).
    """

    control = run_root / "control"
    control.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = run_root / HOST_SUPERVISOR_RECORD
    payload, _limitation = _read_json_file(path)
    if isinstance(payload, dict) and payload.get("pid") is not None:
        if payload.get("pid") == pid:
            return False
        raise HostOpError(
            "run_launch_in_progress",
            f"control/host-supervisor.json already registers writer pid "
            f"{payload.get('pid')!r} for this run root; the launched process "
            f"pid {pid} was not recorded over it",
            obj="run_id",
            retryable=False,
            next_action="adjudicate the two writers manually; neither record "
            "was modified and no process was stopped",
            passthrough={
                "existing_supervisor_pid": payload.get("pid"),
                "launched_pid": pid,
            },
        )
    record: dict[str, Any] = {
        "schema": HOST_SUPERVISOR_SCHEMA,
        "pid": pid,
        "started_at": started_at,
    }
    if session_ref:
        record["session_ref"] = session_ref
    _atomic_write_json(path, record, what="the supervisor record")
    return True


def _assert_launch_target_free(
    run_id: str, run_root: Path, runs_root: Path
) -> None:
    """Design §5.1/§6.2 occupancy pre-check: three branches, no implicit fix.

    Any branch refuses to start a second run for the same id; none of them
    stops an old process, deletes a record or invents a new run id.
    """

    if run_root.exists():
        state, _state_limitation = _read_state(run_root)
        raise HostOpError(
            "run_id_already_exists",
            f"a run directory already exists for run id {run_id!r}; no new run "
            "was started",
            obj="run_id",
            retryable=False,
            next_action="inspect the existing run through get_run_status, or "
            "choose a new explicit run id; never stop the old run implicitly",
            passthrough={
                "existing_run_root": f"workspaces/modeling-runs/{run_id}",
                "recorded_state": (
                    state.get("state") if isinstance(state, dict) else None
                ),
                "query": {"status": "get_run_status", "events": "get_run_events"},
            },
        )
    record, _record_limitation = _read_json_file(
        _host_launches_root(runs_root) / f"{run_id}.json"
    )
    if record is None:
        return
    pid = record.get("pid")
    alive = pid_is_alive(pid)
    if alive:
        raise HostOpError(
            "run_launch_in_progress",
            f"run id {run_id!r} has a registered managed launch whose process "
            f"pid {pid!r} is observed alive",
            obj="run_id",
            retryable=False,
            next_action="re-check the run later through get_run_status",
            passthrough={
                "launch_record": record,
                "observed_pid": pid,
                "query": {"status": "get_run_status", "events": "get_run_events"},
            },
        )
    raise HostOpError(
        "run_launch_failed",
        f"run id {run_id!r} has a registered managed launch whose process is "
        "not alive and no run root exists; the stale registration is kept as "
        "evidence",
        obj="run_id",
        retryable=False,
        next_action="read the registered launch logs, then remove the stale "
        f"{HOST_LAUNCHES_DIRECTORY}/{run_id}.json record manually (runbook) "
        "before reusing this run id; the tool never deletes it",
        passthrough={
            "launch_record": record,
            "log_paths": record.get("log_paths"),
            "observed_pid": pid,
        },
    )


def _launch_managed_run(
    *,
    run_id: str,
    kind: str,
    argv: list[str],
    service_tier: str = "unset",
    repository_root: Path | None = None,
    launcher: Callable[..., Any] | None = None,
    host_session_ref: str | None = None,
    request_id: str | None = None,
    run_root_wait_seconds: float = LAUNCH_RUN_ROOT_WAIT_SECONDS,
) -> dict[str, Any]:
    """Design §6: one managed launch, registered before anything else.

    The registration (`.host-launches/<run_id>.json` plus the two log files) is
    written *before* the subprocess is created so a crash before ``prepare``
    still leaves the host a place to read; the pid is written back once the
    process exists and the reaper thread is the only writer of ``exited``.
    """

    if kind not in HOST_LAUNCH_KINDS:
        raise HostOpError(
            "launch_arguments_invalid",
            f"launch kind must be one of {list(HOST_LAUNCH_KINDS)}",
            obj="kind",
            retryable=False,
            next_action="report this as an implementation defect",
        )
    if service_tier not in {"unset", "fast", "default"}:
        raise HostOpError(
            "launch_arguments_invalid",
            "service_tier must be 'unset', 'fast', or 'default' (explicit off)",
            obj="service_tier",
            retryable=True,
            next_action="pass the latest applicable session choice; omit for unset",
        )
    child_env = dict(os.environ)
    if service_tier == "fast":
        child_env["MODELING_TEAM_CODEX_SERVICE_TIER"] = "fast"
    elif service_tier == "default":
        child_env.pop("MODELING_TEAM_CODEX_SERVICE_TIER", None)
    run_root, runs_root = _validated_run_root(run_id, repository_root=repository_root)
    repository = (
        Path(repository_root).resolve()
        if repository_root is not None
        else default_repository_root()
    )
    launches = _host_launches_root(runs_root)
    try:
        launches.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise HostOpError(
            "run_launch_failed",
            f"the launch registration directory could not be created: "
            f"{exc.strerror or exc}",
            obj=HOST_LAUNCHES_DIRECTORY,
            retryable=False,
            next_action="check the runs-root permissions; nothing was started",
        ) from exc
    started_at = _utc_now()
    log_paths = _launch_log_paths(run_id, runs_root)
    record: dict[str, Any] = {
        "schema": HOST_LAUNCH_RECORD_SCHEMA,
        "run_id": run_id,
        "kind": kind,
        "argv": list(argv),
        "service_tier": service_tier,
        "service_tier_note": "requested child environment override only; verify "
        "actual role config separately; existing threads are unchanged",
        "argv_note": "credential-free by construction: the platform credential "
        "travels only in the process environment, never in argv or this record",
        "pid": None,
        "started_at": started_at,
        "host_session_ref": host_session_ref,
        "request_id": request_id,
        "log_paths": {
            "stdout": log_paths["stdout"],
            "stderr": log_paths["stderr"],
        },
        "status": HOST_LAUNCH_STATUS_LAUNCHED,
        "recorded_at": started_at,
    }
    record_path = launches / f"{run_id}.json"
    _atomic_write_json(record_path, record, what=f"the launch record for run id {run_id!r}")
    launch = _managed_launch if launcher is None else launcher
    out_path = launches / f"{run_id}.out.log"
    err_path = launches / f"{run_id}.err.log"
    try:
        with out_path.open("ab") as out_handle, err_path.open("ab") as err_handle:
            process = launch(
                list(argv),
                cwd=str(repository),
                env=child_env,
                stdout=out_handle.fileno(),
                stderr=err_handle.fileno(),
            )
    except OSError as exc:
        raise HostOpError(
            "run_launch_failed",
            f"the managed launch for run id {run_id!r} could not create the "
            f"subprocess: {exc.strerror or exc}",
            obj="run_id",
            retryable=False,
            next_action="read the registered launch logs; the registration and "
            "the logs are kept as evidence and are never deleted implicitly",
            passthrough={"launch_record": record, "log_paths": record["log_paths"]},
        ) from exc
    record = {**record, "pid": process.pid, "recorded_at": _utc_now()}
    _atomic_write_json(record_path, record, what=f"the launch record for run id {run_id!r}")
    _spawn_exit_reaper(process, record_path, run_id)
    supervisor_written = False
    observed = _await_run_root(run_root, run_root_wait_seconds)
    if observed:
        supervisor_written = _write_supervisor_record(
            run_root,
            pid=process.pid,
            started_at=started_at,
            session_ref=host_session_ref,
        )
    return _record_launch_observation(run_id, record, observed, supervisor_written)


def _lifecycle_result(result: dict[str, Any], action: str) -> dict[str, Any]:
    """Design §5.2/§5.4 return shape for one FIFO-backed S2 action.

    The S1 submission result is passed through untouched and only annotated:
    ``consumption_evidence`` points at the S2 evidence file, and a still
    pending submission names the polling tool.  An already recorded receipt
    keeps its ``accepted``/``rejected`` outcome fields verbatim (a replayed
    request_id never triggers a second save).
    """

    payload: dict[str, Any] = {
        **result,
        "action": result.get("action", action),
        "consumption_evidence": LIFECYCLE_CONSUMPTION_EVIDENCE.get(action),
    }
    if "status" not in payload:
        payload["status"] = payload.get("outcome")
    if payload.get("status") == "submitted":
        payload["next_action"] = "get_request_result"
    return payload


def _submit_lifecycle_action(
    run_id: str,
    action: str,
    envelope: dict[str, Any],
    *,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    try:
        result = submit_fifo_action(
            run_id,
            action,
            envelope,
            request_id=request_id,
            repository_root=repository_root,
        )
    except HostOpError as exc:
        if exc.code == "outer_input_channel_unavailable" and action == "resume":
            # Design §5.2: resume_live_run states its limit instead of silently
            # turning into a 015 checkpoint continuation.
            raise HostOpError(
                exc.code,
                exc.reason,
                obj=exc.obj,
                retryable=exc.retryable,
                next_action="resume_live_run continues a live thread only; a "
                "stopped or ended run continues exclusively through "
                "resume_from_checkpoint",
                passthrough={**exc.passthrough, "requested_action": action},
            ) from exc
        raise
    return _lifecycle_result(result, action)


def start_run(
    *,
    run_id: str,
    task: str,
    profile: str,
    model_profile: str,
    scope: str,
    freeze_started_at: str,
    service_tier: str = "unset",
    task_overlay: str | None = None,
    base_url: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
    launcher: Callable[..., Any] | None = None,
    host_session_ref: str | None = None,
    run_root_wait_seconds: float = LAUNCH_RUN_ROOT_WAIT_SECONDS,
) -> dict[str, Any]:
    """Design §5.1: one managed ``python -m modeling_team run`` launch.

    The pre-checks are side-effect free and short-circuit in order (run id
    shape/containment, input reference containment, freeze-timepoint shape,
    base URL protocol, then the run-id occupancy branches).  ``freeze_started_at``
    is only shape-checked here and passed through verbatim: the tool never
    fills or rewrites a timepoint, and for a multi-slice budget-exempt task the
    platform has no freeze-time gate, so the real-timepoint discipline is the
    host's.  Accepting the launch never means a semantic start happened.
    """

    _validate_request_id(request_id)
    run_root, runs_root = _validated_run_root(run_id, repository_root=repository_root)
    resolved_profile = resolve_repo_path(
        profile, field="profile", repository_root=repository_root
    )
    resolved_task = resolve_repo_path(task, field="task", repository_root=repository_root)
    resolved_scope = resolve_repo_path(scope, field="scope", repository_root=repository_root)
    resolved_overlay = (
        resolve_repo_path(
            task_overlay, field="task_overlay", repository_root=repository_root
        )
        if task_overlay is not None
        else None
    )
    validated_freeze = validate_freeze_started_at(freeze_started_at)
    if base_url is not None:
        _validate_base_url(base_url)
    _assert_launch_target_free(run_id, run_root, runs_root)
    argv = [
        sys.executable,
        "-m",
        "modeling_team",
        "run",
        "--profile",
        str(resolved_profile),
        "--task",
        str(resolved_task),
    ]
    if resolved_overlay is not None:
        argv.extend(["--task-overlay", str(resolved_overlay)])
    argv.extend(
        [
            "--model-profile",
            str(model_profile),
            "--run-id",
            run_id,
            "--scope",
            str(resolved_scope),
        ]
    )
    if base_url is not None:
        argv.extend(["--base-url", base_url])
    argv.extend(["--freeze-started-at", validated_freeze, "--enable-outer-input-fifo"])
    launched = _launch_managed_run(
        run_id=run_id,
        kind="run",
        argv=argv,
        service_tier=service_tier,
        repository_root=repository_root,
        launcher=launcher,
        host_session_ref=host_session_ref,
        request_id=request_id,
        run_root_wait_seconds=run_root_wait_seconds,
    )
    relative_root = f"workspaces/modeling-runs/{run_id}"
    return {
        **launched,
        "baseline_evidence": {
            "manifest": f"{relative_root}/baseline-manifest.json (locatable once "
            "the run root appears)",
            "hash_ref": "evidence/start-ledger.jsonl reservation record field "
            "baseline_hash",
        },
        "query": {"status": "get_run_status", "events": "get_run_events"},
        "note": "launch accepted ≠ semantic start happened",
        "semantic_start_evidence": (
            "evidence/semantic-start.jsonl (appears asynchronously once a real "
            "semantic start happened; evidence/start-ledger.jsonl records only "
            "reservation/presemantic_release/terminal_settlement events and "
            "never proves a semantic start)"
        ),
    }


def pause_run(
    run_id: str,
    *,
    request_id: str | None = None,
    text: str | None = None,
    source_reference: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.2: the outer ``pause`` envelope -- a pause is not a stop."""

    return _submit_lifecycle_action(
        run_id, "pause", {"action": "pause", **({"text": text} if text is not None else {}),
                              **({"source_reference": source_reference} if source_reference is not None else {})},
        request_id=request_id, repository_root=repository_root,
    )


def resume_live_run(
    run_id: str,
    *,
    request_id: str | None = None,
    text: str | None = None,
    source_reference: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.2: continue the same live thread, never rebuild or hot-load."""

    return _submit_lifecycle_action(
        run_id, "resume", {"action": "resume", **({"text": text} if text is not None else {}),
                              **({"source_reference": source_reference} if source_reference is not None else {})},
        request_id=request_id, repository_root=repository_root,
    )


def stop_run(
    run_id: str,
    *,
    reason: str | None = None,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.2: the outer ``stop`` envelope with its existing cleanup.

    ``reason`` only travels in the envelope (and therefore in the host
    submission digest): the Runner's stop branch does not read it, and this
    tool never claims otherwise.
    """

    envelope: dict[str, Any] = {"action": "stop"}
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip():
            raise HostOpError(
                "launch_arguments_invalid",
                "reason must be a non-empty string when provided",
                obj="reason",
                retryable=True,
                next_action="pass the host ledger reason for this stop or omit it",
            )
        envelope["reason"] = reason
    return _submit_lifecycle_action(
        run_id, "stop", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def standby_run(run_id: str, *, request_id: str | None = None,
                repository_root: Path | None = None) -> dict[str, Any]:
    """Request actual write sealing while retaining the original Team owner."""
    return _submit_lifecycle_action(run_id, "standby", {"action": "standby"},
                                    request_id=request_id, repository_root=repository_root)


def consult_team(run_id: str, *, text: str | None = None, request_id: str | None = None,
                 body_ref: dict[str, Any] | None = None,
                 material_refs: list[dict[str, Any]] | None = None,
                 display_text: str | None = None,
                 material_origins: list[dict[str, Any]] | None = None,
                 handoff_materials: HandoffMaterials | None = None,
                 material_actor_id: str = "host",
                 material_recipient_id: str = "runner",
                 repository_root: Path | None = None) -> dict[str, Any]:
    if body_ref is None and (not isinstance(text, str) or not text.strip()):
        raise HostOpError(
            "consult_text_missing",
            "consult requires original text unless a body_ref supplies the complete content",
            obj="text",
            retryable=True,
            next_action="provide the consult text or an authorized body_ref",
        )
    if (body_ref is not None or material_refs) and handoff_materials is None:
        handoff_materials, auto_recipient = _auto_material_binding(
            run_id, repository_root=repository_root
        )
        if handoff_materials is not None:
            material_actor_id = "runner"
            material_recipient_id = auto_recipient or material_recipient_id
    formal_text, material_metadata = _material_payload(
        text,
        body_ref=body_ref,
        material_refs=material_refs,
        display_text=display_text,
        material_origins=material_origins,
        handoff_materials=handoff_materials,
        material_actor_id=material_actor_id,
        material_recipient_id=material_recipient_id,
    )
    wire_text = material_metadata.get("display_text", formal_text) if body_ref is not None else formal_text
    return _submit_lifecycle_action(
        run_id, "consult", {"action": "consult", "text": wire_text, **material_metadata},
        request_id=request_id, repository_root=repository_root)


def inspect_checkpoints(
    run_id: str,
    *,
    checkpoint_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.3: the existing read-only 015 inspection, passed through."""

    run_root, _runs_root = resolve_run_root(run_id, repository_root=repository_root)
    if checkpoint_id is not None and (
        not isinstance(checkpoint_id, str) or not checkpoint_id
    ):
        raise HostOpError(
            "launch_arguments_invalid",
            "checkpoint_id must be a non-empty string when provided",
            obj="checkpoint_id",
            retryable=False,
            next_action="inspect without checkpoint_id to list every package",
        )
    try:
        result = inspect_checkpoints_readonly(run_root, checkpoint_id)
    except CheckpointError as exc:
        raise HostOpError(
            exc.reason_code,
            exc.detail,
            obj=exc.object,
            retryable=exc.retryable,
            next_action=exc.retry,
        ) from exc
    return {"run_id": run_id, "read_only": True, "observed_at": _utc_now(), **result}


def save_checkpoint(
    run_id: str,
    *,
    kind: str | None,
    request_id: str | None = None,
    scope_refs: dict[str, Any] | None = None,
    command: str = "save",
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.4/§7.3: one top-level ``request_id``, two recorded faces.

    The same id is written to the host submission ledger plus the Runner
    receipt (through :func:`submit_fifo_action`) and re-injected by the shared
    admission wrapper for the 015 manifest provenance.  Kind and selector
    validation stays with the Runner, so its original codes come back
    unchanged; frozen results are never edited and no historical checkpoint is
    back-filled here.
    """

    if command != "save":
        raise HostOpError(
            "launch_arguments_invalid",
            "save_checkpoint only submits the 'save' command; read-only "
            "inspection goes through inspect_checkpoints",
            obj="command",
            retryable=False,
            next_action="call inspect_checkpoints for a read-only listing",
        )
    envelope: dict[str, Any] = {"action": "checkpoint", "command": "save", "kind": kind}
    if scope_refs is not None:
        if not isinstance(scope_refs, dict):
            raise HostOpError(
                "launch_arguments_invalid",
                "scope_refs must be a JSON object when provided",
                obj="scope_refs",
                retryable=False,
                next_action="pass the 015 selector contract as an object",
            )
        envelope["scope_refs"] = scope_refs
    return _submit_lifecycle_action(
        run_id, "checkpoint", envelope,
        request_id=request_id, repository_root=repository_root,
    )


def resume_from_checkpoint(
    *,
    source_run_id: str,
    checkpoint_id: str,
    new_run_id: str,
    mode: str,
    authorization_reference: str,
    service_tier: str = "unset",
    fork_reason: str | None = None,
    write_tail_run_id: str | None = None,
    freeze_started_at: str | None = None,
    session_timeout: float | int | None = None,
    model_profile: str | None = None,
    runtime: str = "codex",
    question_visibility: str = "hidden",
    request_id: str | None = None,
    repository_root: Path | None = None,
    launcher: Callable[..., Any] | None = None,
    host_session_ref: str | None = None,
    run_root_wait_seconds: float = LAUNCH_RUN_ROOT_WAIT_SECONDS,
) -> dict[str, Any]:
    """Design §5.5: one managed ``checkpoint resume`` of an explicit package.

    ``--run-id`` is the SOURCE run id and ``--new-run-id`` the fresh one; the
    checkpoint id is never auto-selected and ``--enable-outer-input-fifo`` is
    always passed so the continuation run stays host-interactive.  The
    credential pre-check runs before anything else, so a missing host
    credential never spawns a subprocess.
    """

    if mode == "acceptance":
        from .delivery_ops import validate_evaluation_runtime
        validate_evaluation_runtime(runtime, model_profile, service_tier, mode="cq-acceptance", repository_root=repository_root)
    elif runtime != "codex":
        raise HostOpError("launch_arguments_invalid", "runtime is an acceptance-only option", obj="runtime", retryable=True,
                          next_action="select runtime only for acceptance continuation")
    _require_host_credential()
    _validate_request_id(request_id)
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise HostOpError(
            "checkpoint_id_required",
            "an explicit checkpoint id is required; the tool never auto-selects "
            "the latest package",
            obj="checkpoint_id",
            retryable=True,
            next_action="list the packages with inspect_checkpoints and pass "
            "one explicit checkpoint_id",
        )
    _new_root, new_runs_root = _validated_run_root(
        new_run_id, repository_root=repository_root
    )
    _validated_run_root(source_run_id, repository_root=repository_root)
    _assert_launch_target_free(new_run_id, _new_root, new_runs_root)
    if mode not in {"production", "acceptance"}:
        raise HostOpError(
            "launch_arguments_invalid",
            f"mode must be 'production' or 'acceptance', not {mode!r}",
            obj="mode",
            retryable=True,
            next_action="pass the 015 continuation mode explicitly",
        )
    if fork_reason is not None and (
        mode != "production" or not isinstance(fork_reason, str) or not fork_reason.strip()
    ):
        raise HostOpError(
            "launch_arguments_invalid", "fork_reason requires production mode and a nonempty reason",
            obj="fork_reason", retryable=True,
            next_action="use production mode and name the reason for an explicit fork",
        )
    if write_tail_run_id is not None and (
        mode != "production"
        or not isinstance(write_tail_run_id, str)
        or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", write_tail_run_id) is None
    ):
        raise HostOpError(
            "launch_arguments_invalid",
            "write_tail_run_id requires production mode and a run id",
            obj="write_tail_run_id", retryable=True,
            next_action="name the dead continuation run whose post-checkpoint "
            "writes the production resume must reconcile, or omit it",
        )
    if mode == "production" and freeze_started_at is None:
        raise HostOpError(
            "launch_arguments_invalid",
            "mode 'production' requires freeze_started_at: the schema-v2 Task "
            "contract demands an explicit fresh freeze timepoint on the resume "
            "path",
            obj="freeze_started_at",
            retryable=True,
            next_action="record the real freeze window of the NEW run and pass "
            "it; never reuse the source run's old timepoint",
        )
    if mode == "acceptance" and freeze_started_at is not None:
        raise HostOpError(
            "launch_arguments_invalid",
            "mode 'acceptance' does not take freeze_started_at",
            obj="freeze_started_at",
            retryable=True,
            next_action="drop freeze_started_at for an acceptance-only "
            "continuation",
        )
    validated_freeze = (
        validate_freeze_started_at(freeze_started_at) if mode == "production" else None
    )
    if not isinstance(question_visibility, str) or question_visibility not in {"hidden", "public"} or (
        mode != "acceptance" and question_visibility != "hidden"
    ):
        raise HostOpError(
            "launch_arguments_invalid",
            "question_visibility requires acceptance mode and hidden or public",
            obj="question_visibility", retryable=True,
            next_action="choose hidden or public in acceptance mode",
        )
    if model_profile is not None and (
        mode != "acceptance" or not isinstance(model_profile, str)
        or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", model_profile) is None
    ):
        raise HostOpError(
            "launch_arguments_invalid",
            "model_profile requires acceptance mode and a model profile identifier",
            obj="model_profile", retryable=True,
            next_action="pass the explicit acceptance model profile id, or omit it",
        )
    if not isinstance(authorization_reference, str) or not authorization_reference.strip():
        raise HostOpError(
            "launch_arguments_invalid",
            "authorization_reference is required: the host-ledger reference for "
            "this continuation is recorded verbatim by the resume entry",
            obj="authorization_reference",
            retryable=True,
            next_action="pass the host-recorded authorization reference (for "
            "example auth-<batch>/<action> (user-approved <time>))",
        )
    if session_timeout is not None and (
        not isinstance(session_timeout, (int, float))
        or isinstance(session_timeout, bool)
        or session_timeout <= 0
    ):
        raise HostOpError(
            "launch_arguments_invalid",
            "session_timeout must be a positive number of seconds",
            obj="session_timeout",
            retryable=True,
            next_action="pass the acceptance-mode per-child session timeout in "
            "seconds",
        )
    argv = [
        sys.executable,
        "-m",
        "modeling_team",
        "checkpoint",
        "resume",
        "--run-id",
        source_run_id,
        "--checkpoint-id",
        checkpoint_id,
        "--new-run-id",
        new_run_id,
        "--mode",
        mode,
        "--authorization-reference",
        authorization_reference,
    ]
    if validated_freeze is not None:
        argv.extend(["--freeze-started-at", validated_freeze])
    if fork_reason is not None:
        argv.extend(["--fork-reason", fork_reason])
    if write_tail_run_id is not None:
        argv.extend(["--write-tail-run-id", write_tail_run_id])
    if session_timeout is not None:
        argv.extend(["--session-timeout", str(session_timeout)])
    if question_visibility != "hidden":
        argv.extend(["--question-visibility", question_visibility])
    if mode == "acceptance" and runtime != "codex":
        argv.extend(["--runtime", runtime])
    if model_profile is not None:
        argv.extend(["--model-profile", model_profile])
    argv.append("--enable-outer-input-fifo")
    launched = _launch_managed_run(
        run_id=new_run_id,
        kind="checkpoint_resume",
        argv=argv,
        service_tier="default" if runtime == "dsh" else service_tier,
        repository_root=repository_root,
        launcher=launcher,
        host_session_ref=host_session_ref,
        request_id=request_id,
        run_root_wait_seconds=run_root_wait_seconds,
    )
    return {
        **launched,
        "run_id": new_run_id,
        "source_run_id": source_run_id,
        "checkpoint_id": checkpoint_id,
        "write_tail_run_id": write_tail_run_id,
        "mode": mode,
        "runtime": runtime,
        "semantic_starts_note": (
            "production resume consumes 1 semantic start and an acceptance-only "
            "continuation consumes 0; the 015 inspection result is authoritative"
        ),
        "query": {"status": "get_run_status", "events": "get_run_events"},
    }


def settle_source_run(
    source_run_id: str,
    *,
    stop_reference: str,
    base_url: str = DEFAULT_PLATFORM_BASE_URL,
    request_id: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Design §5.6: in-process settlement of an existing controlled stop.

    The CLI's exact call semantics are reused: the same module-level function,
    the same ``http_readback`` construction and the same
    ``.recovery-settlements/<run_id>.json`` record path.  A refusal keeps its
    original typed code, and "the process could not be found" is never treated
    as proof that the writer stopped.
    """

    _require_host_credential()
    _validate_request_id(request_id)
    run_root, runs_root = resolve_run_root(source_run_id, repository_root=repository_root)
    _validate_base_url(base_url)
    readback = http_readback(base_url, os.environ[HOST_CREDENTIAL_ENV])
    try:
        record = settle_source_run_record(
            run_root=run_root,
            stop_reference=stop_reference,
            readback=readback,
        )
    except CheckpointError as exc:
        raise HostOpError(
            exc.reason_code,
            exc.detail,
            obj=exc.object,
            retryable=exc.retryable,
            next_action=exc.retry,
        ) from exc
    settlement_path = runs_root / ".recovery-settlements" / f"{source_run_id}.json"
    try:
        relative = settlement_path.resolve().relative_to(
            Path(repository_root).resolve()
            if repository_root is not None
            else default_repository_root()
        )
        settlement_ref = relative.as_posix()
    except (OSError, ValueError):
        settlement_ref = settlement_path.as_posix()
    return {
        "source_run_id": source_run_id,
        "settled": True,
        "settlement_record": record,
        "settlement_record_ref": settlement_ref,
        "request_id": request_id,
        "note": "this records the existing controlled-stop evidence only; an "
        "unknown write stays behind its own reconciliation boundary",
    }


__all__ = [
    "ACTION_EVIDENCE",
    "EVENTS_DEFAULT_LIMIT",
    "EVENTS_MAX_LIMIT",
    "EVENT_LINE_BYTE_CAP",
    "FIFO_MAX_LINE_BYTES",
    "HostOpError",
    "answer_question",
    "complete_cq_acceptance",
    "complete_cq_handoff",
    "default_repository_root",
    "freeze_cq",
    "get_pending_actions",
    "get_request_result",
    "get_run_events",
    "get_run_status",
    "inspect_checkpoints",
    "launch_record_path",
    "pause_run",
    "pending_items",
    "read_launch_record",
    "recover_provider",
    "register_question",
    "resolve_issue",
    "resolve_repo_path",
    "resume_from_checkpoint",
    "resume_live_run",
    "save_checkpoint",
    "settle_source_run",
    "start_run",
    "stop_run",
    "submit_instruction",
    "submit_cq_review",
    "submit_fifo_action",
    "validate_freeze_started_at",
]
