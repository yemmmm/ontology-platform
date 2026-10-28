"""Bounded shared-memory validation using the existing versioned workspace.

Two real writers merge source-grounded contributions after contention. A fresh
read-only consumer answers from memory alone; an independent evaluator checks
the answers against the original source and an already frozen question set.
This probes the current exact-ID memory path, not a new memory service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from host_support import ROOT, TASK_REF, HostAgent, write_json
from integration_cases import json_turn, materials, source, workspace
from openai_codex.generated.v2_all import McpServerToolCallResponse

from ontoweave_modeling.results import ResultContractError, validate_evaluation_binding

WRITER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "object_id": {"type": "string"},
        "recorded_revision": {"type": "integer"},
        "contribution_ids": {"type": "array", "items": {"type": "string"}},
        "unresolved": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["object_id", "recorded_revision", "contribution_ids", "unresolved"],
}
CONSUMER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "target_revision": {"type": "integer"},
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "answer": {"type": "string"},
                    "memory_entry_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "answer", "memory_entry_ids"],
            },
        },
    },
    "required": ["target_revision", "answers"],
}
EVALUATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["PASS", "REVISE", "PARTIAL"]},
        "target_revision": {"type": "integer"},
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "passed": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "memory_entry_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["index", "passed", "reason", "memory_entry_ids"],
            },
        },
    },
    "required": ["verdict", "target_revision", "cases"],
}


def tool_items(actor: HostAgent) -> list[dict]:
    result = []
    for line in (actor.agent.root / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        item = event.get("params", {}).get("item", {})
        if event["method"] == "item/completed" and item.get("type") == "mcpToolCall":
            result.append(item)
    return result


def payload(item: dict) -> dict:
    result = item.get("result") or {}
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = "\n".join(row.get("text", "") for row in result.get("content", []))
    return json.loads(text)


def require_reads(actor: HostAgent, material_ids: set[str], object_id: str, revision: int):
    items = [item for item in tool_items(actor) if item["status"] == "completed"]
    read_materials = {
        item["arguments"]["material_id"] for item in items if item["tool"] == "read_material"
    }
    if not material_ids.issubset(read_materials):
        raise ResultContractError("memory_required_material_reads_missing")
    reads = [
        payload(item)
        for item in items
        if item["tool"] == "read_workspace_object" and item["arguments"]["object_id"] == object_id
    ]
    if not any(item.get("revision") == revision for item in reads):
        raise ResultContractError("memory_exact_revision_not_read")


def authorized_config(root: Path, read_ids: list[str], write_ids: list[str]):
    # The same existing PostgreSQL repository is reused; no additional Store.
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return workspace(root, read_ids, write_ids)


def write_phase(root: Path, questions_path: Path):
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    object_id = root.name + ":shared-memory"
    private_id = root.name + ":private-record"
    repository, config = authorized_config(root, [object_id], [object_id])
    repository.put(object_id, "business_memory", {"entries": []}, 0)
    repository.put(
        private_id,
        "private_memory",
        {"canary": hashlib.sha256((root.name + ":private").encode()).hexdigest()},
        0,
    )
    public = materials(root / "writer-materials", {"scenario": source()})
    freeze = questions_path.read_bytes()
    (root / "private-question-freeze.json").write_bytes(freeze)
    (root / "private-question-freeze.json").chmod(0o400)
    write_json(
        root / "authorization.json",
        {
            "task_ref": TASK_REF,
            "authorization_ref": "user-2026-10-28-continue-shared-memory-validation",
            "resource_policy": "usage_only",
            "model_profile": "glm-flash-low",
            "scope": "existing workspace concurrency, exact-ID fresh-context consumption and independent evaluation",
            "production_platform_writes": False,
            "source_ref": source()[1],
            "source_sha256": hashlib.sha256(source()[0].encode()).hexdigest(),
            "question_sha256": hashlib.sha256(freeze).hexdigest(),
        },
    )
    actors = {}
    barrier = threading.Barrier(2)
    try:
        for unit in ("A", "B"):
            actors[unit] = HostAgent(
                root / ("writer-" + unit),
                materials=public,
                workspace_config=config,
                allowed_tools=("read_material", "read_workspace_object", "put_workspace_object"),
                instructions="Maintain authorized shared business memory through workspace tools. "
                "Preserve source conditions, negation and unknowns. Never use last-write-wins or "
                "timestamps to decide business truth. On version_conflict, read current content, "
                "preserve committed entries, and merge your additions. Actual contradictory meanings "
                "must remain explicit unresolved alternatives. Do not apply or accept a platform model.",
            ).start()

        def contribute(unit):
            focus = (
                "Capture source definitions 1 and 2 and the concept distinction in definition 4."
                if unit == "A"
                else "Capture source definition 3, the explicit non-ownership statement in definition 4, "
                "and every supplied scope limit/unknown."
            )
            barrier.wait(timeout=30)
            result = json_turn(
                actors[unit],
                f'Call read_material(material_id="scenario") and '
                f'read_workspace_object(object_id="{object_id}", revision=1). {focus} '
                "The shared content is {entries:[{id,kind,statement,source_refs,status}]}; use complete "
                f"source-grounded statements, unique IDs prefixed {unit}:, and supported or unknown status. "
                "Do not add facts from other sources. Both writers deliberately start from baseline 1: "
                "your FIRST put_workspace_object attempt must use expected_revision=1. "
                "If it conflicts, call read_workspace_object without a revision, preserve ALL other "
                "entries exactly, append your contributions, and retry at the returned revision. "
                "Do not replace the record with only your portion. Report actual recorded revision "
                "and contribution IDs from successful tool results.",
                WRITER_SCHEMA,
            )
            assert result["status"] == "completed" and "structured_result" in result
            return result["structured_result"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {unit: pool.submit(contribute, unit) for unit in actors}
            outcomes = {unit: future.result() for unit, future in futures.items()}
        intervals = {}
        for unit, actor in actors.items():
            events = [
                json.loads(line)
                for line in (actor.root / "evidence/close-statistics-capture/activity.jsonl")
                .read_text()
                .splitlines()
            ]
            start = next(event for event in events if event["event"] == "llm_start")
            end = next(
                event
                for event in events
                if event["event"] == "llm_end" and event["call_id"] == start["call_id"]
            )
            intervals[unit] = {"start_ns": start["monotonic_ns"], "end_ns": end["monotonic_ns"]}
        overlap = max(row["start_ns"] for row in intervals.values()) < min(
            row["end_ns"] for row in intervals.values()
        )
        assert overlap
        final = repository.get(object_id)
        all_puts = []
        writer_proofs = {}
        for unit, actor in actors.items():
            require_reads(actor, {"scenario"}, object_id, 1)
            puts = [item for item in tool_items(actor) if item["tool"] == "put_workspace_object"]
            assert puts and puts[0]["arguments"]["expected_revision"] == 1
            assert all(item["arguments"]["object_id"] == object_id for item in puts)
            records = [payload(item) for item in puts if item["status"] == "completed"]
            assert any(item.get("status") == "recorded" for item in records)
            all_puts.extend(records)
            writer_proofs[unit] = {
                "native_thread": actor.agent.thread_id,
                "first_expected_revision": 1,
                "write_attempts": len(puts),
                "conflicts": sum(item.get("code") == "version_conflict" for item in records),
                "result": outcomes[unit],
            }
        assert any(item.get("code") == "version_conflict" for item in all_puts)
        committed = [item["object"] for item in all_puts if item.get("status") == "recorded"]
        first = min(committed, key=lambda item: item["revision"])
        final_entries = {item["id"]: item for item in final["content"]["entries"]}
        assert all(final_entries[item["id"]] == item for item in first["content"]["entries"])
        assert all(any(key.startswith(unit + ":") for key in final_entries) for unit in actors)
        denial = actors["A"].agent.client.request(
            "mcpServer/tool/call",
            {
                "threadId": actors["A"].agent.thread_id,
                "server": "workspace",
                "tool": "read_workspace_object",
                "arguments": {"object_id": private_id},
            },
            response_model=McpServerToolCallResponse,
        )
        assert denial.is_error
        write_json(root / "private-read-denial.json", denial.model_dump(mode="json", by_alias=True))
        write_json(root / "frozen-memory.json", final)
        (root / "frozen-memory.json").chmod(0o400)
        write_json(
            root / "target.json",
            {
                "object_id": object_id,
                "revision": final["revision"],
                "authority": "candidate_workspace",
                "question_sha256": hashlib.sha256(freeze).hexdigest(),
            },
        )
        summary = {
            "phase": "write",
            "actual_native_overlap": overlap,
            "native_intervals": intervals,
            "writers": writer_proofs,
            "revision": final["revision"],
            "first_commit_preserved": True,
            "private_read_denied": True,
            "semantic_acceptance": "pending",
        }
        write_json(root / "summary-write.json", summary)
        return summary
    finally:
        for actor in actors.values():
            actor.close()


def consume_phase(root: Path):
    target = json.loads((root / "target.json").read_text())
    questions = json.loads((root / "private-question-freeze.json").read_text())["cases"]
    projection = {
        "cases": [{"index": i, "question": case["question"]} for i, case in enumerate(questions, 1)]
    }
    public = materials(
        root / "consumer-materials",
        {
            "questions": (
                json.dumps(projection, ensure_ascii=False),
                "evaluation-questions-without-expected-answers",
            )
        },
    )
    _, config = authorized_config(root / "consumer-scope", [target["object_id"]], [])
    actor = HostAgent(
        root / "fresh-consumer",
        role="acceptance",
        materials=public,
        workspace_config=config,
        allowed_tools=("read_material", "read_workspace_object"),
        instructions="Independent fresh read-only memory consumer. You have no writer history, "
        "original source or expected answers. Answer only from the authorized exact memory revision. "
        "Read required inputs via tools; preserve unknowns and cite actual memory entry IDs. "
        "Do not repair or write any production memory or model.",
    )
    try:
        actor.start()
        denials = {}
        for material_id in ("scenario", "frozen-questions"):
            denied = actor.agent.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": actor.agent.thread_id,
                    "server": "workspace",
                    "tool": "read_material",
                    "arguments": {"material_id": material_id},
                },
                response_model=McpServerToolCallResponse,
            )
            assert denied.is_error
            denials[material_id] = denied.model_dump(mode="json", by_alias=True)
        write_json(root / "consumer-source-denials.json", denials)
        result = json_turn(
            actor,
            f'Call read_material(material_id="questions") and read_workspace_object(object_id='
            f'"{target["object_id"]}", revision={target["revision"]}). Answer all questions with unique '
            f"indices 1 through {len(questions)}. target_revision={target['revision']}. "
            "The original source and answer key are unavailable; do not reconstruct missing facts "
            "from general knowledge. Unsupported answers must disclose missing memory evidence.",
            CONSUMER_SCHEMA,
        )
        assert result["status"] == "completed" and "structured_result" in result
        answers = result["structured_result"]
        require_reads(actor, {"questions"}, target["object_id"], target["revision"])
        assert answers["target_revision"] == target["revision"]
        assert sorted(item["index"] for item in answers["answers"]) == list(
            range(1, len(questions) + 1)
        )
        write_json(root / "consumer-answers.json", answers)
        (root / "consumer-answers.json").chmod(0o400)
        summary = {
            "phase": "consume",
            "fresh_native_thread": actor.agent.thread_id,
            "answer_count": len(answers["answers"]),
            "target_revision": target["revision"],
            "source_or_expected_answers_available": False,
            "semantic_acceptance": "pending",
        }
        write_json(root / "summary-consume.json", summary)
        return summary
    finally:
        actor.close()


def evaluate_phase(root: Path):
    target = json.loads((root / "target.json").read_text())
    questions = json.loads((root / "private-question-freeze.json").read_text())["cases"]
    private = materials(
        root / "evaluation-materials",
        {
            "scenario": source(),
            "frozen-questions": (
                (root / "private-question-freeze.json").read_text(),
                "private-frozen-questions",
            ),
            "consumer-answers": (
                (root / "consumer-answers.json").read_text(),
                "frozen-consumer-output",
            ),
        },
    )
    _, config = authorized_config(root / "evaluation-scope", [target["object_id"]], [])
    actor = HostAgent(
        root / "independent-judge",
        role="acceptance",
        materials=private,
        workspace_config=config,
        allowed_tools=("read_material", "read_workspace_object"),
        instructions="Independent read-only evaluator of shared-memory fidelity and fresh consumption. "
        "You did not create, continue or repair the writers or consumer. Judge each frozen question "
        "using original source, actual memory, and the consumer answer. A correct answer must be "
        "supported by that memory, not merely recoverable from the original source. Do not write or "
        "repair the target. Keep hidden questions, expected answers and diagnostics private.",
    )
    try:
        actor.start()
        goal = (
            "Call read_material for each material_id: scenario, frozen-questions, consumer-answers. "
            f'Call read_workspace_object(object_id="{target["object_id"]}", revision={target["revision"]}). '
            "Evaluate preservation of meanings, relation direction, negative statements and unknowns, "
            f"and source-supported consumer answers. Cover exactly unique indices 1 through {len(questions)}, "
            f"target_revision={target['revision']}. Never repair the writers or consumer."
        )
        result = json_turn(actor, goal, EVALUATION_SCHEMA)
        assert result["status"] == "completed" and "structured_result" in result
        report = result["structured_result"]
        require_reads(
            actor,
            {"scenario", "frozen-questions", "consumer-answers"},
            target["object_id"],
            target["revision"],
        )
        validate_evaluation_binding(
            report, case_count=len(questions), target_revision=target["revision"]
        )
        write_json(root / "private-evaluation.json", report)
        summary = {
            "phase": "evaluate",
            "verdict": report["verdict"],
            "target_revision": target["revision"],
            "passed": sum(item["passed"] for item in report["cases"]),
            "total": len(questions),
            "scope": "exact-ID shared memory and fresh consumer; not full R5.0-008 or platform L1",
        }
        write_json(root / "public-feedback.json", summary)
        return summary
    finally:
        actor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("write", "consume", "evaluate"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--frozen-questions",
        type=Path,
        default=ROOT / "workspaces/v5-codex-p0/isolation-live-002/private-question-freeze.json",
    )
    args = parser.parse_args()
    root = args.output_dir.resolve()
    if args.phase == "write":
        result = write_phase(root, args.frozen_questions)
    else:
        result = {"consume": consume_phase, "evaluate": evaluate_phase}[args.phase](root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
