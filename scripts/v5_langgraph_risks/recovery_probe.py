#!/usr/bin/env python3
"""Small, isolated LangGraph effect/checkpoint recovery experiment."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    requested: bool
    status: str
    operation_id: str
    effect_row_id: int | None


def now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_event(path: Path, event: str, **fields: Any) -> None:
    record = {"at": now(), "pid": os.getpid(), "event": event, **fields}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def setup_ledger(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS effects ("
            "row_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "operation_id TEXT NOT NULL, payload TEXT NOT NULL, committed_at TEXT NOT NULL)"
        )
        conn.commit()


def ledger_rows(path: Path) -> list[dict[str, Any]]:
    setup_ledger(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT row_id, operation_id, payload, committed_at FROM effects ORDER BY row_id"
        ).fetchall()
    return [
        {"row_id": row[0], "operation_id": row[1], "payload": row[2], "committed_at": row[3]}
        for row in rows
    ]


def apply_effect(path: Path, operation_id: str, *, idempotent: bool) -> dict[str, Any]:
    """Commit one external effect; idempotence is intentionally application-side."""
    setup_ledger(path)
    with sqlite3.connect(path) as conn:
        if idempotent:
            cursor = conn.execute(
                "INSERT INTO effects(operation_id, payload, committed_at) "
                "SELECT ?, ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM effects WHERE operation_id = ?)",
                (operation_id, "test-effect", now(), operation_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO effects(operation_id, payload, committed_at) VALUES (?, ?, ?)",
                (operation_id, "test-effect", now()),
            )
        conn.commit()
        inserted = cursor.rowcount == 1
        row = conn.execute(
            "SELECT row_id FROM effects WHERE operation_id = ? ORDER BY row_id LIMIT 1",
            (operation_id,),
        ).fetchone()
    return {"inserted": inserted, "row_id": row[0] if row else None}


def checkpoint_snapshot(path: Path, thread_id: str) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    if not path.exists():
        return {"exists": False, "count": 0, "ids": [], "steps": [], "next": [], "values": {}}
    with SqliteSaver.from_conn_string(str(path)) as saver:
        saver.setup()
        checkpoints = list(saver.list(config))
        # Compile the same node topology with a no-op body so get_state can
        # report pending work without executing the application effect.
        builder = StateGraph(State)
        builder.add_node("effect", lambda state: {})
        builder.add_edge(START, "effect")
        builder.add_edge("effect", END)
        graph = builder.compile(checkpointer=saver)
        snapshot = graph.get_state(config)
    ids: list[str] = []
    steps: list[Any] = []
    for item in checkpoints:
        checkpoint_id = item.config.get("configurable", {}).get("checkpoint_id")
        ids.append(str(checkpoint_id) if checkpoint_id is not None else "")
        steps.append((item.metadata or {}).get("step"))
    latest = checkpoints[0].checkpoint if checkpoints else {}
    return {
        "exists": True,
        "count": len(checkpoints),
        "ids": ids,
        "steps": steps,
        "next": list(snapshot.next),
        "values": dict(snapshot.values),
        "latest_updated_channels": latest.get("updated_channels", []),
        "latest_pending_writes": [
            list(item) for item in (checkpoints[0].pending_writes if checkpoints else [])
        ],
    }


def worker(args: argparse.Namespace) -> int:
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ledger = output / "application-ledger.sqlite"
    checkpoints = output / "langgraph-checkpoints.sqlite"
    events = output / "events.jsonl"
    gate = output / "committed-before-return.json" if args.phase == "crash" else None
    setup_ledger(ledger)
    append_event(events, "worker_started", phase=args.phase, mode=args.mode)
    write_json(output / "worker-start.json", {"pid": os.getpid(), "phase": args.phase})

    with SqliteSaver.from_conn_string(str(checkpoints)) as saver:
        saver.setup()

        def effect_node(state: State) -> dict[str, Any]:
            operation_id = state["operation_id"]
            append_event(events, "node_started", operation_id=operation_id)
            if args.mode == "timeout-unknown":
                append_event(
                    events, "timeout_raised", operation_id=operation_id, effect_state="unknown"
                )
                raise TimeoutError("simulated external timeout before effect visibility")
            result = apply_effect(
                ledger,
                operation_id,
                idempotent=args.mode in {"idempotent", "timeout-committed"},
            )
            append_event(
                events,
                "effect_committed",
                operation_id=operation_id,
                inserted=result["inserted"],
                row_id=result["row_id"],
            )
            if args.mode == "timeout-committed":
                append_event(
                    events, "timeout_raised", operation_id=operation_id, effect_state="committed"
                )
                raise TimeoutError("simulated external timeout after effect commit")
            if gate is not None:
                write_json(
                    gate,
                    {
                        "pid": os.getpid(),
                        "operation_id": operation_id,
                        "ledger_rows": ledger_rows(ledger),
                        "checkpoint": checkpoint_snapshot(checkpoints, args.thread_id),
                    },
                )
                append_event(events, "waiting_before_node_return", gate=str(gate))
                release = gate.with_name(gate.name + ".release")
                while not release.exists():
                    time.sleep(0.02)
                append_event(events, "release_seen")
            append_event(events, "node_returning", operation_id=operation_id)
            return {
                "status": "applied",
                "operation_id": operation_id,
                "effect_row_id": result["row_id"],
            }

        builder = StateGraph(State)
        builder.add_node("effect", effect_node)
        builder.add_edge(START, "effect")
        builder.add_edge("effect", END)
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": args.thread_id}}
        input_state: State | None = (
            {"requested": True, "operation_id": args.operation_id}
            if args.phase in {"start", "crash"}
            else None
        )
        result = graph.invoke(input_state, config)
        append_event(events, "graph_returned", result=result)
        write_json(
            output / "worker-summary.json",
            {
                "pid": os.getpid(),
                "phase": args.phase,
                "mode": args.mode,
                "result": result,
                "ledger_rows": ledger_rows(ledger),
                "checkpoint": checkpoint_snapshot(checkpoints, args.thread_id),
            },
        )
    return 0


def wait_for(path: Path, process: subprocess.Popen[str], timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise RuntimeError(f"worker exited before {path.name}: rc={process.returncode}")
        time.sleep(0.02)
    process.kill()
    process.wait()
    raise TimeoutError(f"timed out waiting for {path}")


def launch_worker(output: Path, mode: str, phase: str, operation_id: str, thread_id: str) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--output-dir",
        str(output),
        "--mode",
        mode,
        "--phase",
        phase,
        "--operation-id",
        operation_id,
        "--thread-id",
        thread_id,
    ]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if phase == "crash":
        gate = output / "committed-before-return.json"
        wait_for(gate, child)
        write_json(
            output / "parent-before-kill.json",
            {
                "pid": child.pid,
                "checkpoint": checkpoint_snapshot(
                    output / "langgraph-checkpoints.sqlite", thread_id
                ),
            },
        )
        os.kill(child.pid, signal.SIGKILL)
        rc = child.wait(timeout=5)
        write_json(
            output / "crash-process.json",
            {"pid": child.pid, "returncode": rc, "signal": signal.SIGKILL},
        )
        return rc
    stdout, stderr = child.communicate(timeout=15)
    write_json(
        output / "worker-stdio.json",
        {"stdout": stdout, "stderr": stderr, "returncode": child.returncode},
    )
    if child.returncode != 0:
        raise RuntimeError(f"worker failed: rc={child.returncode}; stderr={stderr}")
    return child.returncode


def launch_timeout_worker(output: Path, mode: str, operation_id: str, thread_id: str) -> int:
    """Run a real node TimeoutError path and retain its non-zero process evidence."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "worker",
        "--output-dir",
        str(output),
        "--mode",
        mode,
        "--phase",
        "start",
        "--operation-id",
        operation_id,
        "--thread-id",
        thread_id,
    ]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = child.communicate(timeout=15)
    write_json(
        output / "timeout-process.json",
        {"pid": child.pid, "returncode": child.returncode, "stdout": stdout, "stderr": stderr},
    )
    return child.returncode


def reconcile_operation(ledger: Path, operation_id: str, outcome: str) -> str:
    existing = [row for row in ledger_rows(ledger) if row["operation_id"] == operation_id]
    if existing:
        return "read_back_existing_effect"
    if outcome == "confirmed_not_written":
        result = apply_effect(ledger, operation_id, idempotent=True)
        return "applied_once" if result["inserted"] else "read_back_existing_effect"
    if outcome == "unknown":
        return "deferred_for_reconciliation"
    return "effect_missing_after_reported_commit"


def run_recovery_scenario(root: Path, mode: str) -> dict[str, Any]:
    output = root / mode
    output.mkdir(parents=True, exist_ok=True)
    operation_id, thread_id = f"operation-{mode}", f"thread-{mode}"
    crash_rc = launch_worker(output, mode, "crash", operation_id, thread_id)
    before = checkpoint_snapshot(output / "langgraph-checkpoints.sqlite", thread_id)
    rows_after_crash = ledger_rows(output / "application-ledger.sqlite")
    launch_worker(output, mode, "resume", operation_id, thread_id)
    after = checkpoint_snapshot(output / "langgraph-checkpoints.sqlite", thread_id)
    rows_after_resume = ledger_rows(output / "application-ledger.sqlite")
    events = [
        json.loads(line)
        for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return {
        "mode": mode,
        "operation_id": operation_id,
        "thread_id": thread_id,
        "crash_returncode": crash_rc,
        "before_resume_checkpoint": before,
        "after_resume_checkpoint": after,
        "rows_after_crash": rows_after_crash,
        "rows_after_resume": rows_after_resume,
        "node_started_count": sum(event["event"] == "node_started" for event in events),
        "evidence_dir": str(output),
    }


def run_r3(root: Path) -> dict[str, Any]:
    output = root / "r3-reconciliation"
    output.mkdir(parents=True, exist_ok=True)
    ledger = output / "application-ledger.sqlite"
    setup_ledger(ledger)
    initial_commit = apply_effect(ledger, "committed-op", idempotent=True)
    timeout_committed_dir = output / "timeout-committed"
    timeout_committed_dir.mkdir(parents=True, exist_ok=True)
    timeout_committed_rc = launch_timeout_worker(
        timeout_committed_dir,
        "timeout-committed",
        "timeout-committed-op",
        "thread-timeout-committed",
    )
    timeout_unknown_dir = output / "timeout-unknown"
    timeout_unknown_dir.mkdir(parents=True, exist_ok=True)
    timeout_unknown_rc = launch_timeout_worker(
        timeout_unknown_dir, "timeout-unknown", "timeout-unknown-op", "thread-timeout-unknown"
    )
    result = {
        "initial_commit": initial_commit,
        "real_timeout_nodes": {
            "committed": {
                "returncode": timeout_committed_rc,
                "rows": ledger_rows(timeout_committed_dir / "application-ledger.sqlite"),
                "checkpoint": checkpoint_snapshot(
                    timeout_committed_dir / "langgraph-checkpoints.sqlite",
                    "thread-timeout-committed",
                ),
                "decision": reconcile_operation(
                    timeout_committed_dir / "application-ledger.sqlite",
                    "timeout-committed-op",
                    "unknown",
                ),
                "evidence_dir": str(timeout_committed_dir),
            },
            "unknown": {
                "returncode": timeout_unknown_rc,
                "rows": ledger_rows(timeout_unknown_dir / "application-ledger.sqlite"),
                "checkpoint": checkpoint_snapshot(
                    timeout_unknown_dir / "langgraph-checkpoints.sqlite", "thread-timeout-unknown"
                ),
                "decision": reconcile_operation(
                    timeout_unknown_dir / "application-ledger.sqlite",
                    "timeout-unknown-op",
                    "unknown",
                ),
                "evidence_dir": str(timeout_unknown_dir),
            },
        },
        "decisions": {
            "committed": reconcile_operation(ledger, "committed-op", "committed"),
            "confirmed_not_written": reconcile_operation(
                ledger, "not-written-op", "confirmed_not_written"
            ),
            "unknown": reconcile_operation(ledger, "unknown-op", "unknown"),
        },
        "rows": ledger_rows(ledger),
        "evidence_dir": str(output),
    }
    write_json(output / "summary.json", result)
    return result


def run_all(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "probe": "v5-langgraph-recovery",
        "python": sys.version,
        "langgraph": "1.2.18 (environment pin)",
        "checkpoint": "langgraph-checkpoint==4.3.1; langgraph-checkpoint-sqlite==3.1.2 (environment pin)",
        "naive": run_recovery_scenario(output_dir, "naive"),
        "idempotent": run_recovery_scenario(output_dir, "idempotent"),
        "r3": run_r3(output_dir),
    }
    completed = output_dir / "completed-replay"
    completed.mkdir(parents=True, exist_ok=True)
    operation_id, thread_id = "operation-completed", "thread-completed"
    launch_worker(completed, "idempotent", "start", operation_id, thread_id)
    first = ledger_rows(completed / "application-ledger.sqlite")
    launch_worker(completed, "idempotent", "completed", operation_id, thread_id)
    second = ledger_rows(completed / "application-ledger.sqlite")
    result["r4_completed_replay"] = {
        "rows_after_first": first,
        "rows_after_second": second,
        "checkpoint": checkpoint_snapshot(completed / "langgraph-checkpoints.sqlite", thread_id),
        "evidence_dir": str(completed),
    }
    write_json(output_dir / "summary.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument("--output-dir", required=True)
    worker_parser.add_argument(
        "--mode",
        choices=["naive", "idempotent", "timeout-committed", "timeout-unknown"],
        required=True,
    )
    worker_parser.add_argument(
        "--phase", choices=["start", "crash", "resume", "completed"], required=True
    )
    worker_parser.add_argument("--operation-id", required=True)
    worker_parser.add_argument("--thread-id", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "worker":
        return worker(args)
    if args.command == "run":
        print(json.dumps(run_all(Path(args.output_dir)), indent=2, sort_keys=True))
        return 0
    raise SystemExit("use 'run' or 'worker'")


if __name__ == "__main__":
    raise SystemExit(main())
