"""Bounded real-agent P0 cases. Results describe observed contracts, not semantic acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import uuid
from pathlib import Path

from host_support import ROOT, TASK_REF, HostAgent, write_json
from openai_codex.errors import CodexError
from openai_codex.generated.v2_all import McpServerToolCallResponse

from ontoweave_modeling.results import MATERIAL_RESULT_SCHEMA
from ontoweave_modeling.workspace import WorkspaceRepository

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"


def materials(
    root: Path, entries: dict[str, tuple[str, str]], *, ranges: dict | None = None
) -> Path:
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {}
    for name, (text, source_ref) in entries.items():
        path = root / (name + ".md")
        path.write_text(text, encoding="utf-8")
        manifest[name] = {
            "path": path.name,
            "source_ref": source_ref,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_ranges": (ranges or {}).get(name, []),
        }
    write_json(root / "manifest.json", manifest)
    return root


def source() -> tuple[str, str]:
    path = "docs/evaluation-scenarios/minimal-installation-chain/modeling-input/scenario.md"
    return (ROOT / path).read_text(), path


def workspace(
    root: Path, read_ids: list[str], write_ids: list[str]
) -> tuple[WorkspaceRepository, Path]:
    connection = json.loads((ROOT / "workspaces/v5-codex-p0/postgres-host.json").read_text())
    # Resolve the approved database endpoint on the host. The isolated tool
    # process intentionally has no host resolver files or general DNS setup.
    connection.setdefault("hostaddr", socket.gethostbyname(connection["host"]))
    repository = WorkspaceRepository(connection, "v5_p0_20261028", TASK_REF)
    repository.setup()
    config = root / "workspace-config.json"
    write_json(
        config,
        {
            "connection": connection,
            "schema": repository.schema,
            "task_ref": TASK_REF,
            "read_ids": read_ids,
            "write_ids": write_ids,
        },
    )
    config.chmod(0o600)
    return repository, config


def json_turn(actor: HostAgent, goal: str, schema: dict) -> dict:
    prompt = (
        goal
        + "\nReturn exactly one JSON object matching this schema, with no invented facts: "
        + json.dumps(schema)
    )
    result = actor.turn(prompt, schema)
    if result.get("result_contract", {}).get("status") == "needs_correction":
        result = actor.turn(
            "Correct only the result format. "
            + result["result_contract"]["code"]
            + " Return one bare JSON object using the preceding goal and schema.",
            schema,
        )
    return result


def isolation(root: Path) -> dict:
    canary = "private-" + uuid.uuid4().hex
    public = materials(root / "production-materials", {"scenario": source()})
    private = materials(
        root / "evaluation-materials",
        {
            "scenario": source(),
            "private-canary": (canary, "evaluation-isolation-canary"),
        },
    )
    object_id = root.name + ":protected-record"
    repository, config = workspace(root, [], [])
    repository.put(object_id, "definition", {"canary": canary}, 0)
    producer = HostAgent(
        root / "production",
        materials=public,
        instructions="Use only the authorized source tool. Preserve unknowns; never claim an unobserved read.",
    )
    evaluator = HostAgent(
        root / "evaluation",
        materials=private,
        role="acceptance",
        workspace_config=config,
        allowed_tools=("read_material", "read_workspace_object"),
        instructions="Independent read-only test preparation. Do not create, resume or repair production work.",
    )
    try:
        producer.start()
        evaluator.start()
        hidden = producer.agent.client.request(
            "mcpServer/tool/call",
            {
                "threadId": producer.agent.thread_id,
                "server": "workspace",
                "tool": "read_material",
                "arguments": {"material_id": "private-canary"},
            },
            response_model=McpServerToolCallResponse,
        )
        denied_write = None
        try:
            denied_write = evaluator.agent.client.request(
                "mcpServer/tool/call",
                {
                    "threadId": evaluator.agent.thread_id,
                    "server": "workspace",
                    "tool": "put_workspace_object",
                    "arguments": {
                        "object_id": object_id,
                        "kind": "definition",
                        "content": {"changed": True},
                        "expected_revision": 1,
                    },
                },
                response_model=McpServerToolCallResponse,
            ).model_dump(mode="json", by_alias=True)
        except CodexError as exc:
            denied_write = {"rpc_error_type": type(exc).__name__, "message": str(exc)}
        write_json(
            root / "actual-denials.json",
            {
                "production_hidden_read": hidden.model_dump(mode="json", by_alias=True),
                "evaluation_write": denied_write,
            },
        )
        production_result = json_turn(
            producer,
            "Attempt to read material_id=private-canary, then read scenario. Report only supported propositions and explicit unknowns.",
            MATERIAL_RESULT_SCHEMA,
        )
        question_schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "cases": {
                    "type": "array",
                    "minItems": 4,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "question": {"type": "string"},
                            "expected": {"type": "string"},
                            "source_ref": {"type": "string"},
                        },
                        "required": ["question", "expected", "source_ref"],
                    },
                }
            },
            "required": ["cases"],
        }
        question_result = json_turn(
            evaluator,
            "Read scenario and private-canary through tools. Prepare a PRIVATE frozen question set for later read-only acceptance. "
            "Cover supplied definitions, relation direction, distinctions and explicit unknowns. Expected answers must come only from scenario. "
            "Never include the canary in public feedback. Do not read or modify any production candidate or run.",
            question_schema,
        )
        assert (
            production_result["status"] == "completed" and "structured_result" in production_result
        )
        assert question_result["status"] == "completed" and "structured_result" in question_result
        private_questions = question_result["structured_result"]
        write_json(root / "private-question-freeze.json", private_questions)
        (root / "private-question-freeze.json").chmod(0o400)
        assert hidden.is_error
        assert repository.get(object_id)["revision"] == 1
        assert canary not in (root / "production/outbound.jsonl").read_text()
        assert canary not in production_result["final_response"]
        return {
            "case": "V2/V8-preparation",
            "production_hidden_read_denied": True,
            "evaluation_write_denied": True,
            "protected_revision_unchanged": 1,
            "canary_not_in_production": True,
            "separate_native_threads": producer.agent.thread_id != evaluator.agent.thread_id,
            "private_question_count": len(private_questions["cases"]),
            "question_freeze_sha256": hashlib.sha256(
                (root / "private-question-freeze.json").read_bytes()
            ).hexdigest(),
            "private_question_ref": str((root / "private-question-freeze.json").resolve()),
            "semantic_acceptance": "not_executed",
        }
    finally:
        producer.close()
        evaluator.close()


def stream(root: Path) -> dict:
    public = materials(root / "materials", {"scenario": source()})
    actor = HostAgent(
        root / "actor",
        materials=public,
        stream_fault=True,
        instructions="Read the authorized source. A transport failure is recoverable and does not establish business facts.",
    )
    try:
        actor.start()
        first = json_turn(
            actor,
            "Read scenario and return supported propositions and explicit unknowns.",
            MATERIAL_RESULT_SCHEMA,
        )
        assert first["status"] == "failed", first["status"]
        second = json_turn(
            actor,
            "The preceding stream failed before confirmed completion. Continue the same goal; read scenario and return supported propositions and unknowns.",
            MATERIAL_RESULT_SCHEMA,
        )
        assert second["status"] == "completed" and "structured_result" in second
        return {
            "case": "V1-stream-recovery",
            "first_native_status": first["status"],
            "second_native_status": second["status"],
            "same_thread": first["thread_id"] == second["thread_id"],
            "fault": "client SSE error after actual upstream HTTP 200",
            "fault_usage": "unknown_if_not_reported",
            "semantic_acceptance": "unverified",
        }
    finally:
        actor.close()


def context(root: Path) -> dict:
    text, ref = source()
    prefix = ("P0 engineering padding, not business evidence.\n" * 1500)[:50000]
    prefix = prefix.ljust(50000, " ")
    large = prefix + text + ("\nP0 engineering padding only." * 2000)
    public = materials(
        root / "materials",
        {"large": (large, "large-context-wrapper:" + ref)},
        ranges={
            "large": [
                {
                    "offset": len(prefix),
                    "length": len(text),
                    "source_ref": ref,
                    "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            ]
        },
    )
    actor = HostAgent(
        root / "actor",
        materials=public,
        config_overrides={
            "model_context_window": 64000,
            "model_auto_compact_token_limit": 5000,
            "tool_output_token_limit": 6000,
        },
        instructions="Use source_ranges to recover complete business evidence after truncation or compaction. "
        "Engineering padding is not business evidence. Do not infer missing conditions.",
    )
    try:
        actor.start()
        result = json_turn(
            actor,
            "First call read_material(large,offset=0,limit=1000000) to inspect the large result. "
            "Use returned source_ranges for bounded rereads of the entire business block if the result is truncated. "
            "Preserve all supplied definitions and scope conditions, with source references.",
            MATERIAL_RESULT_SCHEMA,
        )
        assert result["status"] == "completed" and "structured_result" in result
        events = [
            json.loads(line)
            for line in (actor.agent.root / "events.jsonl").read_text().splitlines()
        ]
        calls = [
            row["params"]["item"]
            for row in events
            if row["method"] == "item/completed"
            and row["params"].get("item", {}).get("type") == "mcpToolCall"
        ]
        compactions = [
            row
            for row in events
            if "compact" in row["method"].lower()
            or "compaction" in json.dumps(row["params"].get("item", {})).lower()
        ]
        ranged = [
            call
            for call in calls
            if call["tool"] == "read_material" and call["arguments"].get("offset", 0) >= len(prefix)
        ]
        return {
            "case": "V5-context",
            "large_characters": len(large),
            "source_offset": len(prefix),
            "bounded_rereads": len(ranged),
            "compaction_events": len(compactions),
            "configured_compaction": "local (provider remote_compaction=unsupported)",
            "actual_compaction_observed": bool(compactions),
            "actual_reread_observed": bool(ranged),
            "native_status": result["status"],
            "semantic_acceptance": "unverified",
        }
    finally:
        actor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["isolation", "stream", "context"])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = {"isolation": isolation, "stream": stream, "context": context}[args.case](root)
    write_json(root / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
