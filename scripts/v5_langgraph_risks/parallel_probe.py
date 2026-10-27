#!/usr/bin/env python3
"""Bounded LangGraph probes for parallel execution and cooperative work units.

Nodes use deterministic functions instead of an LLM. These probes establish
control-flow and persistence observations only; they are not semantic-agent or
production-application acceptance tests.
"""

from __future__ import annotations

import argparse
import json
import operator
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt


class FanoutState(TypedDict, total=False):
    items: list[str]
    item: str
    results: Annotated[list[str], operator.add]


class UnitState(TypedDict, total=False):
    unit: str
    result: str
    question: str
    answer: dict[str, Any] | str
    consumed_decision: dict[str, Any] | str
    final: str


def _record(
    events: list[dict[str, Any]],
    lock: threading.Lock,
    agent: str,
    event: str,
    **extra: Any,
) -> None:
    with lock:
        events.append(
            {
                "ts": time.time(),
                "monotonic": time.monotonic(),
                "agent": agent,
                "event": event,
                **extra,
            }
        )


def _write_json(output_dir: Path, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return {"path": str(path), **payload}


def _checkpoint_snapshot(graph: Any, config: dict[str, Any]) -> dict[str, Any]:
    state = graph.get_state(config)
    return {
        "next": list(state.next),
        "values": dict(state.values),
        "metadata": dict(state.metadata),
        "tasks": [
            {"name": task.name, "interrupts": [repr(item) for item in task.interrupts]}
            for task in state.tasks
        ],
    }


def run_p1(output_dir: Path) -> dict[str, Any]:
    """Dynamic Send fan-out; a barrier proves two graph nodes overlap."""
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def dispatch(state: FanoutState) -> list[Send]:
        _record(events, lock, "dispatcher", "dispatch", items=state["items"])
        return [Send("agent", {"item": item}) for item in state["items"]]

    def agent(state: FanoutState) -> dict[str, Any]:
        item = state["item"]
        _record(events, lock, item, "started")
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError as exc:  # pragma: no cover - diagnostic failure
            _record(events, lock, item, "barrier_failed", error=str(exc))
            raise
        _record(events, lock, item, "barrier_passed")
        _record(events, lock, item, "ended")
        return {"results": [f"done:{item}"]}

    builder = StateGraph(FanoutState)
    builder.add_node("agent", agent)
    builder.add_conditional_edges(START, dispatch)
    builder.add_edge("agent", END)
    result = builder.compile().invoke({"items": ["agent-a", "agent-b"]})
    starts = [event for event in events if event["event"] == "started"]
    ends = [event for event in events if event["event"] == "ended"]
    overlap = (
        len(starts) == 2
        and len(ends) == 2
        and max(e["monotonic"] for e in starts) <= min(e["monotonic"] for e in ends)
    )
    payload = {
        "case": "P1",
        "status": "PASS"
        if overlap and sorted(result["results"]) == ["done:agent-a", "done:agent-b"]
        else "FAIL",
        "native_mechanism": "StateGraph conditional Send fan-out",
        "observed_parallel_overlap": overlap,
        "result": result,
        "events": events,
        "limitations": ["Deterministic node doubles; no LLM tool or semantic-quality claim."],
    }
    return _write_json(output_dir, "p1_fanout", payload)


def _build_naive_barrier_graph(events: list[dict[str, Any]], lock: threading.Lock) -> StateGraph:
    def waiting_agent(_: UnitState) -> dict[str, Any]:
        _record(events, lock, "agent-a", "before_interrupt")
        answer = interrupt("agent-a needs a clarification")
        _record(events, lock, "agent-a", "after_interrupt", answer=answer)
        return {}

    def independent_first(_: UnitState) -> dict[str, Any]:
        _record(events, lock, "agent-b", "first_step")
        return {}

    def independent_follow(_: UnitState) -> dict[str, Any]:
        _record(events, lock, "agent-b", "follow_step")
        return {}

    builder = StateGraph(UnitState)
    builder.add_node("waiting_agent", waiting_agent)
    builder.add_node("independent_first", independent_first)
    builder.add_node("independent_follow", independent_follow)
    builder.add_edge(START, "waiting_agent")
    builder.add_edge(START, "independent_first")
    builder.add_edge("waiting_agent", END)
    builder.add_edge("independent_first", "independent_follow")
    builder.add_edge("independent_follow", END)
    return builder


def run_p2(output_dir: Path) -> dict[str, Any]:
    """Negative control: one thread's interrupt leaves a sibling's next step pending."""
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "p2_checkpoints.sqlite"
    config = {"configurable": {"thread_id": "p2-naive-single-thread"}}
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = _build_naive_barrier_graph(events, lock).compile(checkpointer=checkpointer)
        first = graph.invoke({}, config)
        events_before_resume = list(events)
        before_resume = _checkpoint_snapshot(graph, config)
        second = graph.invoke(Command(resume="clarified"), config)
        after_resume = _checkpoint_snapshot(graph, config)
    names = [event["event"] for event in events]
    names_before_resume = [event["event"] for event in events_before_resume]
    observed_block = (
        "first_step" in names_before_resume and "follow_step" not in names_before_resume
    )
    follow_only_after_resume = names.index("follow_step") > names.index("after_interrupt")
    payload = {
        "case": "P2",
        "status": "LIMITATION_OBSERVED" if observed_block and follow_only_after_resume else "FAIL",
        "native_mechanism": "single graph superstep/checkpoint barrier",
        "first_invoke": {
            "has_interrupt": "__interrupt__" in first,
            "result": repr(first),
        },
        "resume_result": repr(second),
        "checkpoint_before_resume": before_resume,
        "checkpoint_after_resume": after_resume,
        "events": events,
        "events_before_resume": events_before_resume,
        "interpretation": "The interrupt returned control, but the sibling follow-up did not execute until resume; this is a limitation control, not a parallel-success claim.",
        "limitations": [
            "This tests one graph/thread; it does not prohibit independent graph threads."
        ],
    }
    return _write_json(output_dir, "p2_naive_interrupt_barrier", payload)


def _build_independent_units(events: list[dict[str, Any]], lock: threading.Lock) -> StateGraph:
    def route(state: UnitState) -> str:
        return "agent_a_wait" if state["unit"] == "A" else "agent_b_prepare"

    def agent_a_wait(_: UnitState) -> dict[str, Any]:
        _record(events, lock, "A", "before_interrupt")
        answer = interrupt("A needs a scoped clarification")
        _record(events, lock, "A", "after_interrupt", answer=answer)
        return {"answer": str(answer), "result": "A-complete"}

    def agent_b_prepare(_: UnitState) -> dict[str, Any]:
        _record(events, lock, "B", "prepare")
        return {"result": "B-prepared"}

    def agent_b_finish(state: UnitState) -> dict[str, Any]:
        _record(events, lock, "B", "finish", result=state["result"])
        return {"result": "B-complete"}

    builder = StateGraph(UnitState)
    builder.add_node("route", lambda _: {})
    builder.add_node("agent_a_wait", agent_a_wait)
    builder.add_node("agent_b_prepare", agent_b_prepare)
    builder.add_node("agent_b_finish", agent_b_finish)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        route,
        {"agent_a_wait": "agent_a_wait", "agent_b_prepare": "agent_b_prepare"},
    )
    builder.add_edge("agent_a_wait", END)
    builder.add_edge("agent_b_prepare", "agent_b_finish")
    builder.add_edge("agent_b_finish", END)
    return builder


def run_p3(output_dir: Path) -> dict[str, Any]:
    """Independent thread IDs let B finish while A remains interrupted."""
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "p3_checkpoints.sqlite"
    config_a = {"configurable": {"thread_id": "p3-unit-A"}}
    config_b = {"configurable": {"thread_id": "p3-unit-B"}}
    builder = _build_independent_units(events, lock)
    # Close the first checkpointer and compile a fresh graph before continuing;
    # this exercises disk-backed recovery rather than an in-memory continuation.
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        first_a = graph.invoke({"unit": "A"}, config_a)
        a_waiting = _checkpoint_snapshot(graph, config_a)
    with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        result_b = graph.invoke({"unit": "B"}, config_b)
        a_still_waiting = _checkpoint_snapshot(graph, config_a)
        b_done = _checkpoint_snapshot(graph, config_b)
        result_a = graph.invoke(Command(resume="scope-A-only"), config_a)
        a_done = _checkpoint_snapshot(graph, config_a)
    b_events = [e["event"] for e in events if e["agent"] == "B"]
    a_events = [e["event"] for e in events if e["agent"] == "A"]
    # The second A ``before_interrupt`` is expected: LangGraph restarts the
    # interrupted node from its beginning when a thread is resumed.
    passed = (
        "__interrupt__" in first_a
        and a_waiting["next"] == ["agent_a_wait"]
        and a_still_waiting["next"] == ["agent_a_wait"]
        and b_events == ["prepare", "finish"]
        and a_events == ["before_interrupt", "before_interrupt", "after_interrupt"]
        and "B-complete" in repr(result_b)
        and "A-complete" in repr(result_a)
    )
    payload = {
        "case": "P3",
        "status": "PASS" if passed else "FAIL",
        "application_layer_mechanism": "separate thread_id per independently resumable work unit",
        "first_a": {
            "has_interrupt": "__interrupt__" in first_a,
            "result": repr(first_a),
        },
        "result_b": result_b,
        "result_a_after_resume": repr(result_a),
        "checkpoint_a_while_waiting": a_waiting,
        "checkpoint_b_done": b_done,
        "checkpoint_a_after_b_before_resume": a_still_waiting,
        "checkpoint_a_done": a_done,
        "events": events,
        "restart_observed": a_events.count("before_interrupt") == 2,
        "limitations": [
            "Independent-thread dispatch and unit identity are application orchestration; LangGraph does not provide a distributed scheduler here.",
            "Deterministic node doubles; no LLM tool or semantic-quality claim.",
        ],
    }
    return _write_json(output_dir, "p3_independent_threads", payload)


class Workspace:
    """Tiny durable shared workspace used only by P4's test fixture."""

    def __init__(self, path: Path):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS facts (fact_id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL); CREATE TABLE IF NOT EXISTS exchanges (id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, event TEXT, payload TEXT NOT NULL);"
        )
        self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def publish(self, fact_id: str, payload: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO facts(fact_id,payload,status) VALUES (?,?,?)",
                (fact_id, payload, "pending"),
            )
            self.conn.execute(
                "INSERT INTO exchanges(actor,event,payload) VALUES (?,?,?)",
                ("A", "published", fact_id),
            )
            self.conn.commit()

    def read_fact(self, fact_id: str) -> tuple[str, str, str] | None:
        with self.lock:
            return self.conn.execute(
                "SELECT fact_id,payload,status FROM facts WHERE fact_id=?", (fact_id,)
            ).fetchone()

    def exchange(self, actor: str, event: str, payload: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO exchanges(actor,event,payload) VALUES (?,?,?)",
                (actor, event, payload),
            )
            self.conn.commit()

    def exchanges(self) -> list[tuple[Any, ...]]:
        with self.lock:
            return list(self.conn.execute("SELECT actor,event,payload FROM exchanges ORDER BY id"))


def _run_p4_scenario(
    output_dir: Path, scenario: str, fact_payload: str, expected_status: str
) -> dict[str, Any]:
    """Run one positive or out-of-scope exchange with independent durable files."""
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    start_barrier = threading.Barrier(2)
    fact_published = threading.Event()
    decision_ready = threading.Event()
    interrupt_ready = threading.Event()
    b_done = threading.Event()
    a_ready_to_resume = threading.Event()
    resume_gate = threading.Event()
    results: dict[str, Any] = {}
    snapshots: dict[str, Any] = {}
    failures: list[str] = []
    fact_id = f"fact-{scenario}-acceptance-v1"
    workspace = Workspace(output_dir / f"p4_{scenario}_workspace.sqlite")
    checkpoint_path = output_dir / f"p4_{scenario}_checkpoints.sqlite"
    config_a = {"configurable": {"thread_id": f"p4-{scenario}-A"}}
    config_b = {"configurable": {"thread_id": f"p4-{scenario}-B"}}

    def route(state: UnitState) -> str:
        return "a_publish" if state["unit"] == "A" else "b_consume"

    def a_publish(_: UnitState) -> dict[str, Any]:
        workspace.publish(fact_id, fact_payload)
        _record(
            events,
            lock,
            "A",
            "published",
            fact_id=fact_id,
            revision="v1",
            payload=fact_payload,
        )
        fact_published.set()
        return {"question": "Which scope does this definition apply to?"}

    def a_wait(state: UnitState) -> dict[str, Any]:
        _record(events, lock, "A", "waiting_for_b_decision")
        if not decision_ready.wait(10):
            raise TimeoutError("B did not publish a decision")
        answer = interrupt(state["question"])
        _record(events, lock, "A", "received_answer", answer=answer)
        workspace.exchange("A", "received_answer", json.dumps(answer, sort_keys=True))
        return {"answer": answer}

    def a_finalize(state: UnitState) -> dict[str, Any]:
        answer = state["answer"]
        decision_rows = [row for row in workspace.exchanges() if row[1] == "consumer_decision"]
        if not decision_rows:
            raise RuntimeError("A resumed without B's scoped decision")
        decision = json.loads(decision_rows[-1][2])
        if answer != decision:
            raise RuntimeError("A did not resume with B's actual durable result")
        if decision["status"] != "accepted":
            rejected = f"rejected:{fact_id}:scope={decision['scope']}"
            workspace.exchange("A", "rejected", rejected)
            _record(events, lock, "A", "rejected", result=rejected)
            return {"result": rejected}
        final = f"finalized:{fact_id}:scope={decision['scope']}"
        workspace.exchange("A", "finalized", final)
        _record(events, lock, "A", "finalized", final=final)
        return {"final": final}

    def b_consume(_: UnitState) -> dict[str, Any]:
        if not fact_published.wait(10):
            raise TimeoutError("A did not publish the fact")
        fact = workspace.read_fact(fact_id)
        if fact is None:
            raise RuntimeError("B could not see A's published fact")
        # The consumed payload determines both scope and acceptance. This is
        # deliberately not a constant decision or a driver-provided answer.
        scope = fact[1].split(":", 1)[1] if ":" in fact[1] else "unknown"
        status = "accepted" if fact[1] == "definition:installation" else "rejected"
        decision = {
            "fact_id": fact[0],
            "revision": "v1",
            "scope": scope,
            "status": status,
        }
        _record(
            events,
            lock,
            "B",
            "consumed",
            fact_id=fact[0],
            revision="v1",
            payload=fact[1],
        )
        workspace.exchange(
            "B",
            "consumed",
            json.dumps({"fact_id": fact[0], "revision": "v1", "payload": fact[1]}),
        )
        workspace.exchange("B", "consumer_decision", json.dumps(decision, sort_keys=True))
        decision_ready.set()
        return {"consumed_decision": decision}

    def b_finish(state: UnitState) -> dict[str, Any]:
        decision = state["consumed_decision"]
        if not interrupt_ready.wait(10):
            raise TimeoutError("A did not persist its interrupt")
        _record(events, lock, "B", "finished", decision=decision)
        return {"result": f"B-used:{decision['status']}:{decision['scope']}"}

    builder = StateGraph(UnitState)
    builder.add_node("route", lambda _: {})
    builder.add_node("a_publish", a_publish)
    builder.add_node("a_wait", a_wait)
    builder.add_node("a_finalize", a_finalize)
    builder.add_node("b_consume", b_consume)
    builder.add_node("b_finish", b_finish)
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route", route, {"a_publish": "a_publish", "b_consume": "b_consume"}
    )
    builder.add_edge("a_publish", "a_wait")
    builder.add_edge("a_wait", "a_finalize")
    builder.add_edge("a_finalize", END)
    builder.add_edge("b_consume", "b_finish")
    builder.add_edge("b_finish", END)

    def run_a(graph: Any) -> None:
        try:
            _record(events, lock, "A", "unit_run_started")
            start_barrier.wait(10)
            _record(events, lock, "A", "graph_call_started", phase="initial")
            results["first_a"] = graph.invoke({"unit": "A"}, config_a)
            _record(events, lock, "A", "graph_call_finished", phase="initial")
            snapshots["A_while_waiting"] = _checkpoint_snapshot(graph, config_a)
            interrupt_ready.set()
            if not b_done.wait(10):
                raise TimeoutError("B did not finish while A was interrupted")
            snapshots["A_after_B_before_resume"] = _checkpoint_snapshot(graph, config_a)
            a_ready_to_resume.set()
            if not resume_gate.wait(10):
                raise TimeoutError("resume gate was not released")
            decision = json.loads(
                next(row[2] for row in workspace.exchanges() if row[1] == "consumer_decision")
            )
            _record(
                events,
                lock,
                "A",
                "graph_call_started",
                phase="resume",
                decision=decision,
            )
            results["resumed_a"] = graph.invoke(Command(resume=decision), config_a)
            _record(events, lock, "A", "graph_call_finished", phase="resume")
            _record(events, lock, "A", "unit_run_finished")
        except BaseException as exc:  # pragma: no cover - diagnostic failure path
            failures.append(f"A:{type(exc).__name__}:{exc}")
            resume_gate.set()

    def run_b(graph: Any) -> None:
        try:
            _record(events, lock, "B", "unit_run_started")
            start_barrier.wait(10)
            _record(events, lock, "B", "graph_call_started", phase="initial")
            results["first_b"] = graph.invoke({"unit": "B"}, config_b)
            _record(events, lock, "B", "graph_call_finished", phase="initial")
            b_done.set()
            if not a_ready_to_resume.wait(10):
                raise TimeoutError("A did not capture its waiting checkpoint")
            resume_gate.set()
            _record(events, lock, "B", "unit_run_finished")
        except BaseException as exc:  # pragma: no cover - diagnostic failure path
            failures.append(f"B:{type(exc).__name__}:{exc}")
            b_done.set()
            resume_gate.set()

    try:
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            graph = builder.compile(checkpointer=checkpointer)
            thread_a = threading.Thread(
                target=run_a, args=(graph,), name=f"p4-{scenario}-A", daemon=True
            )
            thread_b = threading.Thread(
                target=run_b, args=(graph,), name=f"p4-{scenario}-B", daemon=True
            )
            thread_a.start()
            thread_b.start()
            thread_a.join(30)
            thread_b.join(30)
            if thread_a.is_alive():
                failures.append("A:thread_timeout")
            if thread_b.is_alive():
                failures.append("B:thread_timeout")
            snapshots["B_done"] = (
                _checkpoint_snapshot(graph, config_b) if "first_b" in results else {}
            )
    finally:
        exchanges = workspace.exchanges()
        workspace.close()

    intervals: dict[str, dict[str, float]] = {"A": {}, "B": {}}
    for event in events:
        if event["event"] == "graph_call_started" and event.get("phase") == "initial":
            intervals[event["agent"]]["start"] = event["monotonic"]
        elif event["event"] == "graph_call_finished" and event.get("phase") == "initial":
            intervals[event["agent"]]["end"] = event["monotonic"]
    graph_call_overlap = all(
        "start" in intervals[agent] and "end" in intervals[agent] for agent in ("A", "B")
    ) and max(intervals["A"]["start"], intervals["B"]["start"]) < min(
        intervals["A"]["end"], intervals["B"]["end"]
    )
    expected_result = "finalized:" if expected_status == "accepted" else "rejected:"
    first_a = results.get("first_a", {})
    first_b = results.get("first_b", {})
    resumed_a = results.get("resumed_a", {})
    passed = (
        not failures
        and graph_call_overlap
        and "__interrupt__" in first_a
        and f"B-used:{expected_status}" in repr(first_b)
        and expected_result in repr(resumed_a)
        and snapshots.get("A_after_B_before_resume", {}).get("next") == ["a_wait"]
        and any(event["event"] == "consumed" for event in events)
    )
    return {
        "scenario": scenario,
        "fact_payload": fact_payload,
        "expected_status": expected_status,
        "status": "PASS" if passed else "FAIL",
        "graph_call_overlap": graph_call_overlap,
        "graph_call_intervals": intervals,
        "failures": failures,
        "first_a": {
            "has_interrupt": "__interrupt__" in first_a,
            "result": repr(first_a),
        },
        "first_b": first_b,
        "resumed_a": repr(resumed_a),
        "checkpoints": snapshots,
        "workspace_exchanges": [list(row) for row in exchanges],
        "events": events,
    }


def run_p4(output_dir: Path) -> dict[str, Any]:
    """A publishes, B consumes and scopes, then A resumes from B's result."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [
        _run_p4_scenario(output_dir, "installation", "definition:installation", "accepted"),
        _run_p4_scenario(output_dir, "repair", "definition:repair", "rejected"),
    ]
    payload = {
        "case": "P4",
        "status": "PASS" if all(item["status"] == "PASS" for item in scenarios) else "FAIL",
        "application_layer_mechanism": "durable shared workspace + separate thread IDs + explicit result exchange",
        "scenarios": scenarios,
        "limitations": [
            "The workspace is a test-only SQLite fixture, not OntoWeave application or RDF storage.",
            "Deterministic node doubles; no LLM semantic-quality claim.",
        ],
    }
    return _write_json(output_dir, "p4_exchange_and_reentry", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["all", "p1", "p2", "p3", "p4"], default="all")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    runners = {"p1": run_p1, "p2": run_p2, "p3": run_p3, "p4": run_p4}
    results = [
        run
        for run in (
            [run_p1, run_p2, run_p3, run_p4] if args.case == "all" else [runners[args.case]]
        )
    ]
    payloads = [run(args.output_dir) for run in results]
    print(
        json.dumps(
            {
                "results": [
                    {"case": p["case"], "status": p["status"], "path": p["path"]} for p in payloads
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if all(p["status"] in {"PASS", "LIMITATION_OBSERVED"} for p in payloads) else 1


if __name__ == "__main__":
    sys.exit(main())
