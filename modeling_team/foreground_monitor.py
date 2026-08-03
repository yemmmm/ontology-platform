"""Small, persistent foreground lifecycle monitor for the independent P2 smoke path.

The monitor deliberately owns only process observation and run-local evidence.  It does not
construct a TeamRunner, create platform resources, or interpret semantic/modeling results.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .contracts import repository_root
from .monitor_handoff import (
    HANDOFF_CONTRACT_RELATIVE_PATH,
    HANDOFF_ENV,
    create_handoff_root,
    load_handoff_contract,
    output_digest,
    read_phase,
    validate_target_run_root,
    write_monitor_phase,
)


REQUIRED_CONTRACT_FIELDS = (
    "schema_version",
    "command",
    "argv",
    "required_stages",
    "parent_pm_boundary_count",
    "evidence_mode",
    "secret_targets",
    "resource_policy",
    "adverse_order_profile",
    "adverse_order_task",
    "adverse_order_extractor",
    "adverse_order_evidence",
)


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def load_contract(path: Path) -> dict[str, Any]:
    """Load and fail closed on the stable descriptor rather than deriving a command at runtime."""
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("P2 monitor contract is unreadable") from exc
    if not isinstance(contract, dict) or set(contract) != set(REQUIRED_CONTRACT_FIELDS):
        raise ValueError("P2 monitor contract has missing or extra fields")
    if contract.get("schema_version") != "p2-monitor-contract/v1":
        raise ValueError("P2 monitor contract schema version is invalid")
    if contract.get("command") != "uv" or not isinstance(contract.get("argv"), list):
        raise ValueError("P2 monitor command contract is invalid")
    expected_argv = [
        "run",
        "--project",
        "backend",
        "python",
        "-m",
        "modeling_team.foreground_monitor",
        "--contract",
        "modeling_team/references/p2-monitor-contract.json",
    ]
    if contract["argv"] != expected_argv:
        raise ValueError("P2 monitor argv drifted")
    stages = contract.get("required_stages")
    if stages != [
        "monitor_started",
        "foreground_started",
        "parent_pm_boundary",
        "agent_terminal_settled",
        "secret_absent",
        "monitor_stopped",
    ]:
        raise ValueError("P2 monitor lifecycle stages drifted")
    if contract.get("parent_pm_boundary_count") != 1:
        raise ValueError("P2 monitor boundary count must equal one")
    if contract.get("evidence_mode") != "append_only_run_local":
        raise ValueError("P2 monitor evidence mode is invalid")
    if contract.get("secret_targets") != ["auth.json", "config.toml", "temporary_credentials"]:
        raise ValueError("P2 monitor secret target list drifted")
    if contract.get("resource_policy") != "at_most_one_owned_ephemeral_scope":
        raise ValueError("P2 monitor resource policy is invalid")
    if contract.get("adverse_order_profile") != "modeling_team/profiles/p2-adverse-order-smoke.yaml":
        raise ValueError("P2 adverse-order profile input drifted")
    if contract.get("adverse_order_task") != "modeling_team/tasks/p2-adverse-order-smoke.yaml":
        raise ValueError("P2 adverse-order Task input drifted")
    if contract.get("adverse_order_extractor") != "modeling_team.foreground_monitor.extract_adverse_order":
        raise ValueError("P2 adverse-order extractor drifted")
    if contract.get("adverse_order_evidence") != "evidence/p2-adverse-order.jsonl":
        raise ValueError("P2 adverse-order evidence path drifted")
    return contract


def append_evidence(path: Path, stage: str, **payload: Any) -> None:
    """Append one fsynced JSONL event; existing evidence is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"stage": stage, **payload}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _secret_paths(run_root: Path, targets: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        candidate = Path(target)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("secret target escapes run root")
        paths.extend((run_root / "secrets" / candidate, run_root / candidate))
    return paths


def destroy_secrets(run_root: Path, targets: Sequence[str]) -> bool:
    """Remove only the descriptor-listed secret files and prove the paths are absent."""
    paths = _secret_paths(run_root, targets)
    for path in paths:
        if path.is_file() or path.is_symlink():
            path.unlink()
    return all(not path.exists() for path in paths)


_ORDER_EVENT_KEYS = {
    "stage",
    "agent",
    "tool",
    "status",
    "order",
    "category",
    "ack",
}
_ORDER_FORBIDDEN_KEYS = {
    "text",
    "message",
    "summary",
    "result",
    "credentials",
    "token",
    "secret",
    "prompt",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("P2 adverse-order evidence is unreadable") from exc
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("P2 adverse-order evidence is not JSONL") from exc
        if not isinstance(value, dict):
            raise ValueError("P2 adverse-order evidence record is not an object")
        values.append(value)
    return values


def _event_time_ns(value: dict[str, Any]) -> int:
    direct = value.get("recorded_at_ns")
    if isinstance(direct, int) and not isinstance(direct, bool) and direct > 0:
        return direct
    recorded_at = value.get("recorded_at")
    if isinstance(recorded_at, str):
        try:
            return int(datetime.fromisoformat(recorded_at).timestamp() * 1_000_000_000)
        except ValueError:
            pass
    raise ValueError("P2 adverse-order event has no stable order timestamp")


def _safe_order_record(
    *,
    agent: str,
    tool: str,
    status: str,
    category: str,
    ack: bool | str,
) -> dict[str, Any]:
    return {
        "stage": "adverse_order",
        "agent": agent,
        "tool": tool,
        "status": status,
        "order": 0,
        "category": category,
        "ack": ack,
    }


def extract_adverse_order(run_root: Path, *, output_path: Path | None = None) -> list[dict[str, Any]]:
    """Extract only safe ordering metadata before the private Runtime is deleted.

    The extractor consumes monitor-owned Runner evidence and the Codex adapter's sanitized
    Team Transport events.  It intentionally never copies the raw prompt, message, summary,
    tool result, or credential fields into the append-only output.
    """
    run_root = run_root.resolve()
    evidence_root = run_root / "evidence"
    if not run_root.is_dir() or not evidence_root.is_dir() or not (run_root / "runtime").is_dir():
        raise ValueError("P2 adverse-order extraction requires live private runtime evidence")
    destination = output_path or evidence_root / "p2-adverse-order.jsonl"
    try:
        destination.resolve().relative_to(evidence_root.resolve())
    except ValueError as exc:
        raise ValueError("P2 adverse-order evidence must remain run-local") from exc
    if destination.exists():
        raise ValueError("P2 adverse-order evidence is immutable and already exists")

    transport_events = _jsonl(evidence_root / "team-transport-events.jsonl")
    protocol_reports = [
        event
        for event in transport_events
        if event.get("agent") == "protocol" and event.get("tool") == "report_task_result"
    ]
    if len(protocol_reports) != 2:
        raise ValueError("P2 adverse-order requires exactly one rejection and one retry")
    if any(
        set(event) - {"agent", "tool", "status", "category", "ack", "recorded_at_ns"}
        or any(key in event for key in _ORDER_FORBIDDEN_KEYS)
        for event in protocol_reports
    ):
        raise ValueError("P2 adverse-order transport evidence contains unsafe fields")
    first, retry = protocol_reports
    if (
        first.get("status") != "rejected"
        or first.get("category") != "missing_modeling_handoff"
        or first.get("ack") != "not_applicable"
        or retry.get("status") != "accepted"
        or retry.get("category") != "terminal_report_accepted"
        or retry.get("ack") != "not_applicable"
    ):
        raise ValueError("P2 adverse-order report sequence is not the required rejection/retry")

    handoffs = [
        event
        for event in _jsonl(evidence_root / "terminal-result-handoff.jsonl")
        if event.get("source_id") == "modeling" and event.get("recipient_id") == "protocol"
    ]
    acknowledgements = [
        event
        for event in _jsonl(evidence_root / "terminal-handoff-ack.jsonl")
        if event.get("agent") == "protocol"
        and event.get("tool") == "ack_terminal_handoff"
        and event.get("source_id") == "modeling"
    ]
    if len(handoffs) != 1 or len(acknowledgements) != 1:
        raise ValueError("P2 adverse-order requires one Modeling handoff and one real ack")
    handoff, acknowledgement = handoffs[0], acknowledgements[0]
    if acknowledgement.get("status") != "accepted" or acknowledgement.get("ack") is not True:
        raise ValueError("P2 adverse-order handoff acknowledgement is not accepted")
    handoff_id = handoff.get("handoff_id")
    handoff_sequence = handoff.get("sequence")
    acknowledgement_sequence = acknowledgement.get("sequence")
    if (
        not isinstance(handoff_id, str)
        or not handoff_id
        or not isinstance(handoff_sequence, int)
        or isinstance(handoff_sequence, bool)
        or handoff_sequence <= 0
        or acknowledgement.get("handoff_id") != handoff_id
        or not isinstance(acknowledgement_sequence, int)
        or isinstance(acknowledgement_sequence, bool)
        or acknowledgement_sequence <= handoff_sequence
    ):
        raise ValueError("P2 adverse-order handoff sequence or identity is invalid")

    settled_events = _jsonl(evidence_root / "settled.jsonl")
    if len(settled_events) != 1:
        raise ValueError("P2 adverse-order requires one all-Agent settlement")
    settled = settled_events[0]
    results = settled.get("results")
    required_roles = {"coordinator", "modeling", "protocol"}
    if (
        not isinstance(results, dict)
        or set(results) != required_roles
        or any(
            not isinstance(value, dict) or value.get("status") != "completed"
            for value in results.values()
        )
    ):
        raise ValueError("P2 adverse-order settlement is not all-three completed")
    records = [
        _safe_order_record(
            agent="protocol",
            tool="report_task_result",
            status="rejected",
            category="missing_modeling_handoff",
            ack="not_applicable",
        ),
        _safe_order_record(
            agent="protocol",
            tool="terminal-handoff",
            status="delivered",
            category="modeling_terminal_handoff",
            ack="not_applicable",
        ),
        _safe_order_record(
            agent="protocol",
            tool="ack_terminal_handoff",
            status="accepted",
            category="modeling_terminal_handoff",
            ack=True,
        ),
        _safe_order_record(
            agent="protocol",
            tool="report_task_result",
            status="accepted",
            category="terminal_report_accepted",
            ack="not_applicable",
        ),
    ]
    records.extend(
        _safe_order_record(
            agent=role,
            tool="report_task_result",
            status="completed",
            category="terminal_result",
            ack="accepted",
        )
        for role in sorted(required_roles)
    )
    records.append(
        _safe_order_record(
            agent="team",
            tool="settled",
            status="completed",
            category="all_three_settled",
            ack="accepted",
        )
    )
    safe_records: list[dict[str, Any]] = []
    for order, record in enumerate(records, start=1):
        record["order"] = order
        if set(record) != _ORDER_EVENT_KEYS:
            raise ValueError("P2 adverse-order output fields drifted")
        safe_records.append(record)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("P2 adverse-order evidence is immutable and already exists") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        for record in safe_records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return safe_records


def _adverse_order_task_selected(run_root: Path) -> bool:
    """Enable the extractor only for the dedicated nonbusiness smoke Task."""
    snapshot = run_root / "task.snapshot.yaml"
    try:
        return "task_id: p2-adverse-order-smoke" in snapshot.read_text(encoding="utf-8")
    except OSError:
        return False


def run_foreground(
    contract_path: Path,
    *,
    command: Sequence[str] | None = None,
    run_root: Path | None = None,
    evidence_path: Path | None = None,
    boundary: bool = True,
    env: dict[str, str] | None = None,
    extract_order: bool = False,
) -> int:
    """Observe an already-selected foreground command and return its exit status.

    ``command`` is supplied by the caller (normally the real foreground CLI).  The monitor does
    not synthesize a command from a run ID or fixture.  Omitting it is useful for descriptor and
    lifecycle smoke checks and performs no platform work.
    """
    contract = load_contract(contract_path)
    repository = repository_root().resolve()
    requested_root = run_root or contract_path.parent.parent.parent
    handoff_mode = bool(command and extract_order)
    target_root = requested_root.resolve(strict=False)
    handoff_root: Path | None = None
    handoff_contract: dict[str, Any] | None = None
    prepared = False
    pending_events: list[tuple[str, dict[str, Any]]] = []
    fallback_evidence: Path | None = None

    if handoff_mode:
        if run_root is None:
            raise ValueError("P2 adverse-order monitor requires an explicit target run root")
        target_root = validate_target_run_root(repository, requested_root, requested_root.name)
        if target_root.exists() or target_root.is_symlink():
            raise ValueError("P2 adverse-order monitor target run root must not exist")
        handoff_contract = load_handoff_contract(repository / HANDOFF_CONTRACT_RELATIVE_PATH)
        handoff_root, _ = create_handoff_root(repository, target_root)
        fallback_evidence = handoff_root / "fallback-monitor.jsonl"

    evidence = evidence_path or target_root / "evidence" / "p2-monitor.jsonl"
    if not evidence.is_absolute():
        evidence = (repository / evidence).resolve(strict=False)
    if handoff_mode:
        try:
            evidence.relative_to(target_root)
        except ValueError as exc:
            raise ValueError("P2 adverse monitor evidence must remain in target run root") from exc

    def record(stage: str, **payload: Any) -> None:
        nonlocal prepared
        if handoff_mode and not prepared:
            pending_events.append((stage, payload))
            return
        append_evidence(evidence, stage, **payload)

    def flush_pending(destination: Path | None = None) -> None:
        nonlocal prepared
        target = destination or evidence
        for stage, payload in pending_events:
            append_evidence(target, stage, **payload)
        pending_events.clear()
        prepared = destination is None

    return_code = 0
    process: subprocess.Popen[str] | None = None
    live_root = target_root
    failure: BaseException | None = None
    extraction_done = False
    try:
        record("monitor_started", contract=str(contract_path))
        if command:
            record("foreground_started", argv=list(command))
            child_env = os.environ.copy()
            if env:
                child_env.update(env)
            if handoff_root is not None:
                child_env[HANDOFF_ENV] = str(handoff_root)
            process = subprocess.Popen(
                list(command),
                cwd=str(repository if handoff_mode else target_root),
                env=child_env if env is not None or handoff_mode else None,
                text=True,
                start_new_session=handoff_mode,
            )
        else:
            record("foreground_started", argv=[])
        if boundary:
            record("parent_pm_boundary", count=1)

        if handoff_mode:
            assert handoff_root is not None and handoff_contract is not None and process is not None
            prepared_deadline = _monotonic() + float(
                handoff_contract["phase_deadlines_seconds"]["prepared"]
            )
            foreground_deadline: float | None = None
            while process.poll() is None:
                if not prepared:
                    phase = read_phase(handoff_root, "runner", "prepared")
                    if phase is not None:
                        reported_root = Path(phase["run_root"]).resolve(strict=False)
                        if reported_root != target_root or not target_root.is_dir() or target_root.is_symlink():
                            raise ValueError("P2 monitor prepared handoff root mismatch")
                        if os.stat(target_root).st_mode & 0o777 != 0o700:
                            raise ValueError("P2 monitor prepared run root mode drifted")
                        if evidence.parent.is_symlink() or not evidence.parent.is_dir():
                            raise ValueError("P2 monitor target evidence directory is unsafe")
                        live_root = target_root
                        flush_pending()
                        foreground_deadline = _monotonic() + float(
                            handoff_contract["phase_deadlines_seconds"]["foreground_run"]
                        )
                    elif _monotonic() >= prepared_deadline:
                        raise TimeoutError("P2 monitor prepared handoff timed out")
                if prepared and not extraction_done:
                    cleanup = read_phase(handoff_root, "runner", "cleanup_pending")
                    failed = read_phase(handoff_root, "runner", "failed")
                    if failed is not None:
                        raise RuntimeError("foreground CLI failed before adverse extraction")
                    if cleanup is not None:
                        if foreground_deadline is not None and _monotonic() >= foreground_deadline:
                            raise TimeoutError("P2 monitor foreground run timed out")
                        extraction_deadline = _monotonic() + float(
                            handoff_contract["phase_deadlines_seconds"]["extraction_complete"]
                        )
                        extract_adverse_order(live_root)
                        digest, length = output_digest(live_root / contract["adverse_order_evidence"])
                        if _monotonic() >= extraction_deadline:
                            raise TimeoutError("P2 monitor extraction acknowledgement timed out")
                        write_monitor_phase(
                            handoff_root,
                            "extraction_complete",
                            run_root=live_root,
                            output_digest=digest,
                            output_length=length,
                        )
                        extraction_done = True
                    elif foreground_deadline is not None and _monotonic() >= foreground_deadline:
                        raise TimeoutError("P2 monitor foreground run timed out")
                _sleep(0.05)
            return_code = process.wait()
            if not prepared:
                raise RuntimeError("foreground CLI exited before prepared handoff")
            if not extraction_done:
                cleanup = read_phase(handoff_root, "runner", "cleanup_pending")
                if cleanup is None:
                    if foreground_deadline is not None and _monotonic() >= foreground_deadline:
                        raise TimeoutError("P2 monitor foreground run timed out")
                    raise RuntimeError("foreground CLI exited before cleanup handoff")
                if foreground_deadline is not None and _monotonic() >= foreground_deadline:
                    raise TimeoutError("P2 monitor foreground run timed out")
                extraction_deadline = _monotonic() + float(
                    handoff_contract["phase_deadlines_seconds"]["extraction_complete"]
                )
                extract_adverse_order(live_root)
                digest, length = output_digest(live_root / contract["adverse_order_evidence"])
                if _monotonic() >= extraction_deadline:
                    raise TimeoutError("P2 monitor extraction acknowledgement timed out")
                write_monitor_phase(
                    handoff_root,
                    "extraction_complete",
                    run_root=live_root,
                    output_digest=digest,
                    output_length=length,
                )
                extraction_done = True
            record("agent_terminal_settled", returncode=return_code)
        else:
            if process is not None:
                return_code = process.wait()
            record("agent_terminal_settled", returncode=return_code)
            if extract_order or _adverse_order_task_selected(target_root):
                extract_adverse_order(target_root)
    except BaseException as exc:
        failure = exc
        if handoff_mode and handoff_root is not None:
            try:
                if not read_phase(handoff_root, "foreground_monitor", "extraction_failed"):
                    write_monitor_phase(
                        handoff_root,
                        "extraction_failed",
                        run_root=target_root,
                        error_type=type(exc).__name__,
                    )
            except (OSError, ValueError):
                pass
        raise
    finally:
        if process is not None and process.poll() is None:
            if failure is not None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    _terminate_process_group(process)
            else:
                _terminate_process_group(process)
            return_code = process.returncode if process.returncode is not None else 2
        if handoff_mode and not prepared:
            assert fallback_evidence is not None
            try:
                flush_pending(fallback_evidence)
                append_evidence(fallback_evidence, "agent_terminal_settled", returncode=return_code)
                append_evidence(fallback_evidence, "secret_absent", failed=True)
                append_evidence(fallback_evidence, "monitor_stopped", returncode=return_code)
            except OSError:
                pass
        else:
            if destroy_secrets(live_root, contract["secret_targets"]):
                record("secret_absent")
            record("monitor_stopped", returncode=return_code)
    if failure is not None:
        raise failure
    return return_code


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Interrupt a monitor-owned process group, then bound TERM/KILL escalation."""
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
    process.wait(timeout=3)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persistent P2 foreground lifecycle monitor")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--no-boundary", action="store_true")
    parser.add_argument("--extract-adverse-order", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    try:
        return run_foreground(
            args.contract,
            command=command or None,
            run_root=args.run_root,
            evidence_path=args.evidence,
            boundary=not args.no_boundary,
            extract_order=args.extract_adverse_order,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"foreground monitor failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
