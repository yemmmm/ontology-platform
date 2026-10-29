"""Read-only model navigation generated independently of production notes and candidates."""

import hashlib
import json

from .acceptance import require_governed_read, successful_reads
from .contracts import FrameworkError, digest, safe_id, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .results import ResultContractError, decode_json_result
from .semantic_workspace import SemanticWorkspace

OVERVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "evidence_iris": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "body", "evidence_iris"],
            },
        },
        "open_items": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "string"},
        "model_revisions": {"type": "object", "additionalProperties": {"type": "integer"}},
    },
    "required": ["summary", "sections", "open_items", "limitations", "model_revisions"],
}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def refresh_overview(binding, repository, bridge, overview_id, topic, view="consumer", invoke=None):
    safe_id(overview_id)
    target = bridge.call("snapshot")
    identity = f"overview-{view}-{overview_id}"
    request = {"target": target, "topic": topic, "view": view}
    directory = binding.root / "overview-inputs" / identity / digest(request)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target_bytes = json.dumps(target, ensure_ascii=False).encode()
    (directory / "target.json").write_bytes(target_bytes)
    write_json(
        directory / "manifest.json",
        {
            "target": {
                "path": "target.json",
                "source_ref": "authorized-actual-model-scope",
                "sha256": hashlib.sha256(target_bytes).hexdigest(),
            }
        },
    )
    attempt_path = directory / "attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {"index": 0}
    execution_id = f"overview-{digest(request)[:24]}-{attempt['index']:03d}"
    invocation = invoke or CodexInvocation(
        binding,
        bridge,
        materials=directory,
        model_revisions=target["model_revisions"],
        read_only=True,
        instructions="Generate business navigation only from the authorized actual model. Read target "
        "and query the governed model; follow relevant paging and preserve conditions, exceptions, "
        "negation, modality, shared definitions and unknowns. Organize an overall summary and bounded "
        "topic sections with exact resource IRIs for deeper reading. Disclose unqueried/incomplete "
        "scope. Do not invent a missing fact, use production work, or write/repair the model. "
        "The overview is navigation; precise decisions must return to actual definitions.",
    )
    prompt = json.dumps(
        {
            "topic": topic,
            "view": view,
            "target": target,
            "result_schema": OVERVIEW_SCHEMA,
            "feedback": attempt.get("error"),
        }
    )
    ref = ExecutionManager(repository, TaskControl(repository), binding, unit_id=identity).run(
        execution_id, "overview", prompt, invocation
    )
    native = repository.read_reference(ref)["result"]
    events = binding.root / "executions" / execution_id / "agent/events.jsonl"
    try:
        if native["status"] != "completed":
            raise FrameworkError("overview_turn_failed", layer="runtime/infrastructure")
        report = decode_json_result(native["final_response"], OVERVIEW_SCHEMA)
        if report["model_revisions"] != target["model_revisions"]:
            raise FrameworkError("overview_target_mismatch")
        require_governed_read(events, target["model_revisions"])
        actual = {
            value
            for tool, _, data in successful_reads(events)
            if tool == "query_semantic_context"
            for value in _strings(data)
        }
        if any(
            iri not in actual for section in report["sections"] for iri in section["evidence_iris"]
        ):
            raise FrameworkError("overview_reference_not_read")
    except (ResultContractError, FrameworkError) as error:
        write_json(attempt_path, {"index": attempt["index"] + 1, "error": str(error)})
        raise FrameworkError("overview_needs_correction", detail=str(error)) from error
    write_json(directory / "report.json", report)
    space = SemanticWorkspace(repository, binding.data, "overview", view=view)
    space.observe_models(bridge.call("snapshot")["model_revisions"])
    space.observe_models(target["model_revisions"])
    scope = "project" if space.project else "task"
    previous = space.read(identity, scope=scope)
    return space.write(
        identity,
        "summary",
        topic,
        json.dumps(report, ensure_ascii=False),
        expected_revision=previous.get("revision", 0),
        scope=scope,
    )


def read_overview(binding, repository, bridge, overview_id, view="consumer"):
    safe_id(overview_id)
    # Check present access and the current actual model before exposing stored navigation.
    space = SemanticWorkspace(repository, binding.data, "overview", view=view)
    space.observe_models(bridge.call("snapshot")["model_revisions"])
    return space.read(
        f"overview-{view}-{overview_id}", scope="project" if space.project else "task"
    )
