"""Explicit v5 task entry; the legacy Team entry and default routing are unchanged."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import uuid
from pathlib import Path

from .acceptance import REPORT_SCHEMA, validate_report
from .contracts import FrameworkError, TaskBinding, _check_sources, digest, safe_id, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .flow import WorkUnitFlow
from .host_bridge import HostBridge
from .results import ResultContractError, decode_json_result
from .workspace import WorkspaceRepository


def repository(binding: TaskBinding) -> tuple[WorkspaceRepository, dict]:
    config = json.loads((binding.root / "private-runtime.json").read_text())
    return WorkspaceRepository(
        config["connection"], config["workspace_schema"], binding.data["task_ref"]
    ), config


def evaluate(binding, repo, bridge, package: Path, evaluation_id: str) -> dict:
    """An independent native context with its own immutable inputs and control record."""
    safe_id(evaluation_id)
    work = repo.get(binding.identity + ":work")["content"]
    if work["status"] != "handoff_ready":
        raise FrameworkError("handoff_not_ready")
    handoff = repo.read_reference(work["handoff_ref"])
    manifest = _check_sources(package)
    questions = manifest.get("frozen-questions", {})
    if questions.get("sha256") != handoff["evaluation"]["sha256"]:
        raise FrameworkError("evaluation_freeze_mismatch")
    for material_id, source in binding.data["source_manifest"].items():
        if manifest.get(material_id, {}).get("sha256") != source["sha256"]:
            raise FrameworkError("evaluation_source_mismatch", material_id=material_id)
    root = binding.root / "evaluations" / evaluation_id
    if not root.exists():
        root.mkdir(parents=True, mode=0o700)
        for entry in manifest.values():
            path = root / "materials" / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes((package / entry["path"]).read_bytes())
        target_bytes = json.dumps(handoff["target"]).encode()
        (root / "materials" / "target.json").write_bytes(target_bytes)
        manifest["target"] = {
            "path": "target.json",
            "source_ref": "frozen-actual-target",
            "sha256": hashlib.sha256(target_bytes).hexdigest(),
        }
        write_json(root / "materials" / "manifest.json", manifest)
        write_json(root / "handoff.json", handoff)
    elif json.loads((root / "handoff.json").read_text()) != handoff:
        raise FrameworkError("evaluation_binding_mismatch")
    _check_sources(root / "materials")
    attempt_path = root / "report-attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {"index": 0}
    execution_id = f"evaluation-{digest(evaluation_id)[:20]}-{attempt['index']:03d}"
    # Host task controls count all in-flight roles; the evaluator gets no production inputs.
    control = TaskControl(repo)
    invocation = CodexInvocation(
        binding,
        bridge,
        materials=root / "materials",
        model_revisions=handoff["target"]["model_revisions"],
        instructions="You are an independent read-only semantic evaluator. Read the original sources, "
        "every frozen case and target using read_material; query the actual governed model. "
        "Never create, continue, repair or modify production work. A candidate or production "
        "self-check is not model evidence. Keep questions, answers and private reasons private.",
    )
    prompt = json.dumps(
        {
            "objective": binding.data["objective"],
            "materials": list(manifest),
            "target": handoff["target"],
            "evaluation": handoff["evaluation"],
            "result_schema": REPORT_SCHEMA,
            "contract_feedback": attempt.get("error"),
        }
    )
    ref = ExecutionManager(repo, control, binding, unit_id="acceptance:" + evaluation_id).run(
        execution_id, "acceptance", prompt, invocation
    )
    native = repo.read_reference(ref)["result"]
    if native["status"] != "completed":
        write_json(
            attempt_path,
            {
                "index": attempt["index"] + 1,
                "error": "evaluation_turn_failed",
                "previous_execution_ref": ref,
            },
        )
        raise FrameworkError("evaluation_turn_failed", layer="runtime/infrastructure")
    events = binding.root / "executions" / execution_id / "agent/events.jsonl"
    try:
        report = decode_json_result(native["final_response"], REPORT_SCHEMA)
        public = validate_report(report, handoff, events)
    except (ResultContractError, FrameworkError) as error:
        # Correct only report structure/reads; the independent frozen standard stays intact.
        write_json(
            attempt_path,
            {"index": attempt["index"] + 1, "error": str(error), "previous_execution_ref": ref},
        )
        raise FrameworkError("evaluation_report_needs_correction", detail=str(error)) from error
    if bridge.call("snapshot")["model_revisions"] != handoff["target"]["model_revisions"]:
        raise FrameworkError("frozen_target_changed")
    write_json(root / "private-report.json", report)
    write_json(root / "public-feedback.json", public)
    return public


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Freeze a new explicit v5 task and advance its work unit")
    start.add_argument("--task", type=Path, required=True)
    start.add_argument("--postgres-config", type=Path, required=True)
    start.add_argument("--workspace-schema", default="ontoweave_v5_workspace")
    start.add_argument("--checkpoint-schema", default="ontoweave_v5_checkpoints")
    start.add_argument(
        "--prepare-only", action="store_true", help="Persist inputs without model/platform calls"
    )
    commands = [start]
    for name in ("status", "pause", "stop", "resume", "cleanup", "evaluate"):
        commands.append(sub.add_parser(name))
    commands[-1].add_argument("--package", type=Path, required=True)
    commands[-1].add_argument("--evaluation-id", required=True)
    for command in commands:
        command.add_argument("--run-dir", type=Path, required=True)
    return result


def dispatch(args) -> dict:
    if args.command == "start":
        if args.workspace_schema == args.checkpoint_schema:
            raise FrameworkError("checkpoint_namespace_must_be_separate")
        connection = json.loads(args.postgres_config.read_text())
        binding = TaskBinding.prepare(args.task, args.run_dir)
        write_json(
            binding.root / "private-runtime.json",
            {
                "connection": connection,
                "workspace_schema": args.workspace_schema,
                "checkpoint_schema": args.checkpoint_schema,
            },
        )
    else:
        binding = TaskBinding.load(args.run_dir)
    repo, config = repository(binding)
    control, bridge = TaskControl(repo), HostBridge(binding.root)
    if args.command == "status":
        row = repo.get(binding.identity + ":work")
        return {"work": row["content"] if row else None, "control": control.view()}
    if args.command in {"pause", "stop"}:
        control.enqueue(uuid.uuid4().hex, args.command)
        return {"control": control.synchronize()}
    if args.command == "cleanup":
        if control.view()["active"]:
            raise FrameworkError("original_activity_unsettled")
        return bridge.call("cleanup")
    if args.command == "evaluate":
        return evaluate(binding, repo, bridge, args.package.resolve(), args.evaluation_id)
    repo.setup()
    flow = WorkUnitFlow(binding, repo, bridge, CodexInvocation(binding, bridge))
    if args.command == "start" and args.prepare_only:
        return {"status": "prepared", "work": flow.initialize()}
    if args.command == "resume":
        control.enqueue(uuid.uuid4().hex, "resume")
        if control.synchronize()["mode"] == "stopped":
            raise FrameworkError("task_stopped")
    with (binding.root / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FrameworkError("run_already_active") from error
        with repo.checkpointer(config["checkpoint_schema"]) as saver:
            return flow.advance(saver)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except FrameworkError as error:
        print(json.dumps({"ok": False, "error": error.as_dict()}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "input_or_runtime_error",
                        "recoverable": True,
                        "type": type(error).__name__,
                    },
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
