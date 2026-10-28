"""Real-agent exchange over PostgreSQL, resumed by a separate process.

This is a bounded integration probe, not the production scheduler or a semantic judge.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

from host_support import HostAgent, write_json
from integration_cases import json_turn, materials, source, workspace
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ontoweave_modeling.results import MATERIAL_RESULT_SCHEMA


class State(TypedDict, total=False):
    unit: str
    object_id: str
    revision: int
    review_id: str
    review_revision: int
    response_id: str
    response_revision: int


REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topic": {"type": "string"},
        "source_ref": {"type": "string"},
        "review": {"type": "string"},
        "question": {"type": "string"},
    },
    "required": ["topic", "source_ref", "review", "question"],
}
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "review_revision": {"type": "integer"},
        "topic": {"type": "string"},
        "answer": {"type": "string"},
        "source_ref": {"type": "string"},
        "explicit_unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["review_revision", "topic", "answer", "source_ref", "explicit_unknowns"],
}


def run(root: Path, phase: str) -> dict:
    prefix = root.name + ":"
    ids = {name: prefix + name for name in ("a", "b", "review", "response")}
    repository, _ = workspace(root, list(ids.values()), [])
    events = root / f"events-{phase}.jsonl"
    lock = threading.Lock()
    actors = {}
    published = threading.Event()
    waiting = threading.Event()

    def record(unit: str, event: str, **extra):
        with lock, events.open("a") as output:
            output.write(
                json.dumps({"at": time.time(), "unit": unit, "event": event, **extra}) + "\n"
            )

    def actor(unit: str):
        if unit not in actors:
            config = root / f"workspace-{unit}-{phase}.json"
            write_json(
                config,
                {
                    "connection": repository.connection,
                    "schema": repository.schema,
                    "task_ref": repository.task_ref,
                    "read_ids": list(ids.values()),
                    "write_ids": [],
                },
            )
            config.chmod(0o600)
            actors[unit] = HostAgent(
                root / f"{unit}-{phase}",
                materials=root / "materials",
                native_root=root / f"native-{unit}",
                resume=phase != "initial",
                workspace_config=config,
                allowed_tools=("read_material", "read_workspace_object"),
                instructions="Use only authorized sources and exact workspace revisions. "
                "Workspace records are candidate understanding, never platform facts. "
                "Keep all unsupported matters explicitly unknown.",
            ).start()
        return actors[unit]

    def turn(unit, goal, schema):
        record(unit, "turn_begin")
        result = json_turn(actor(unit), goal, schema)
        record(unit, "turn_end", thread=result["thread_id"], turn=result["turn_id"])
        assert result["status"] == "completed" and "structured_result" in result
        return result["structured_result"]

    def prepare(state: State):
        unit = state["unit"]
        content = turn(
            unit,
            "Read scenario and capture its complete supported scope with sources.",
            MATERIAL_RESULT_SCHEMA,
        )
        receipt = repository.put(ids[unit.lower()], "understanding", content, 0)
        assert receipt.get("status") == "recorded", receipt
        record(unit, "published", object_id=ids[unit.lower()], revision=1)
        if unit == "A":
            published.set()
        return {"object_id": ids[unit.lower()], "revision": 1}

    def wait_for_review(state: State):
        record("A", "waiting_for_review")
        waiting.set()
        selected = interrupt({"kind": "scoped_clarification", "review_id": ids["review"]})
        return {"review_id": ids["review"], "review_revision": selected["review_revision"]}

    def review(state: State):
        assert published.wait(180) and waiting.wait(180)
        content = turn(
            "B",
            f"Read object {ids['a']} revision 1 and scenario using tools. "
            "Prepare a source-grounded clarification for A about the installation relation: "
            "its direction, meaning and what it does not imply. Set topic=installation_relation. "
            "The question must be answerable from scenario. Do not add business facts.",
            REVIEW_SCHEMA,
        )
        receipt = repository.put(ids["review"], "review", content, 0)
        assert receipt.get("status") == "recorded", receipt
        record("B", "review_published", review_revision=1)
        return {"review_id": ids["review"], "review_revision": 1}

    def respond(state: State):
        content = turn(
            "A",
            f"Read workspace object {state['review_id']} at exact revision "
            f"{state['review_revision']} and scenario through tools. Answer its question and "
            "adopt that review's topic in the output. Report the exact consumed revision. "
            "Keep unsupported details unknown; do not substitute prior review history.",
            RESPONSE_SCHEMA,
        )
        assert content["review_revision"] == state["review_revision"]
        current = repository.get(ids["response"])
        receipt = repository.put(
            ids["response"], "response", content, current["revision"] if current else 0
        )
        assert receipt.get("status") == "recorded", receipt
        record("A", "review_consumed", review_revision=state["review_revision"])
        return {"response_id": ids["response"], "response_revision": receipt["current_revision"]}

    builder = StateGraph(State)
    builder.add_node("prepare", prepare)
    builder.add_node("wait", wait_for_review)
    builder.add_node("review", review)
    builder.add_node("respond", respond)
    builder.add_edge(START, "prepare")
    builder.add_conditional_edges(
        "prepare", lambda state: "wait" if state["unit"] == "A" else "review"
    )
    builder.add_edge("wait", "respond")
    builder.add_edge("respond", END)
    builder.add_edge("review", END)
    configs = {unit: {"configurable": {"thread_id": prefix + unit}} for unit in ("A", "B")}
    try:
        if phase == "initial":
            materials(root / "materials", {"scenario": source()})

            def invoke(unit):
                with repository.checkpointer() as saver:
                    graph = builder.compile(checkpointer=saver)
                    result = graph.invoke({"unit": unit}, configs[unit])
                    return {
                        "interrupted": bool(result.get("__interrupt__")),
                        "next": list(graph.get_state(configs[unit]).next),
                    }

            # Set up migrations once before independent connections are used.
            with repository.checkpointer():
                pass
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {unit: pool.submit(invoke, unit) for unit in ("A", "B")}
                observed = {unit: future.result() for unit, future in futures.items()}
            assert observed["A"]["interrupted"] and observed["B"]["next"] == []
            summary = {
                "phase": phase,
                "checkpoints": observed,
                "native_threads": {unit: a.agent.thread_id for unit, a in actors.items()},
                "semantic_acceptance": "unverified",
            }
        else:
            with repository.checkpointer() as saver:
                graph = builder.compile(checkpointer=saver)
                before = graph.get_state(configs["A"])
                assert list(before.next) == ["wait"]
                graph.invoke(Command(resume={"review_revision": 1}), configs["A"])
                first = repository.get(ids["response"])
                # A changed, source-grounded B artifact must change A's actual response.
                content = turn(
                    "B",
                    f"Read {ids['a']} revision 1 and scenario. Replace the focus "
                    "with the distinction between the two concepts; set topic=concept_distinction. "
                    "Ask a source-answerable question on that topic. Keep unknowns unknown.",
                    REVIEW_SCHEMA,
                )
                second = repository.put(ids["review"], "review", content, 1)
                assert second.get("current_revision") == 2
                respond({"review_id": ids["review"], "review_revision": 2})
                last = repository.get(ids["response"])
                assert first["content"]["topic"] != last["content"]["topic"]
                summary = {
                    "phase": phase,
                    "postgres_pending_node_recovered": list(before.next),
                    "native_threads": {unit: a.agent.thread_id for unit, a in actors.items()},
                    "consumed_review_revisions": [
                        first["content"]["review_revision"],
                        last["content"]["review_revision"],
                    ],
                    "input_change_changed_response": first["content"] != last["content"],
                    "business_revision": repository.get(ids["a"])["revision"],
                    "semantic_acceptance": "unverified",
                }
        write_json(root / f"summary-{phase}.json", summary)
        return summary
    finally:
        for value in actors.values():
            value.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("initial", "resume"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=args.phase == "resume", mode=0o700)
    print(json.dumps(run(root, args.phase), ensure_ascii=False))


if __name__ == "__main__":
    main()
