"""OntoWeave v5 task entry. scripts/modeling selects this stack for new tasks."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import uuid
from pathlib import Path

from .acceptance import read_coverage, report_schema, validate_report
from .budget import synchronize_budget
from .contracts import FrameworkError, TaskBinding, _check_sources, digest, safe_id, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .flow import WorkUnitFlow
from .host_bridge import HostBridge
from .human_input import HumanInput
from .results import ResultContractError, decode_json_result
from .workspace import WorkspaceRepository


def repository(binding: TaskBinding) -> tuple[WorkspaceRepository, dict]:
    config = json.loads((binding.root / "private-runtime.json").read_text())
    return WorkspaceRepository(
        config["connection"],
        config["workspace_schema"],
        binding.data.get("workspace_ref", binding.data["task_ref"]),
    ), config


def evaluate(
    binding, repo, bridge, package: Path, evaluation_id: str, required_artifacts=(), scope=None
) -> dict:
    """An independent native context with its own immutable inputs and control record."""
    safe_id(evaluation_id)
    if any(r["content"]["status"] == "queued" for r in repo.list_kind("source_change")):
        raise FrameworkError("source_change_pending", next_action="resume")
    work = repo.get(binding.identity + ":work")["content"]
    if work["status"] != "handoff_ready":
        raise FrameworkError("handoff_not_ready")
    handoff = repo.read_reference(work["handoff_ref"])
    if scope is not None:
        if scope["base_freeze_id"] != handoff["evaluation"]["freeze_id"]:
            raise FrameworkError("evaluation_scope_base_mismatch")
        selected = scope.get("source_ids", list(handoff["source_revisions"]))
        if set(selected) - handoff["source_revisions"].keys():
            raise FrameworkError("evaluation_scope_source_forbidden")
        handoff = {
            **handoff,
            "evaluation": scope["evaluation"],
            "evaluation_scope": {
                "scope_id": scope["scope_id"],
                "base_freeze_id": scope["base_freeze_id"],
            },
            "source_revisions": {key: handoff["source_revisions"][key] for key in selected},
        }
    manifest = _check_sources(package)
    material_roots = {key: package for key in manifest}
    # CQ goals are public targets added by Host, not replacements for the private main freeze.
    if "cq-goals" in handoff["source_revisions"] and "cq-goals" not in manifest:
        manifest["cq-goals"] = binding.data["source_manifest"]["cq-goals"]
        material_roots["cq-goals"] = binding.materials
    if set(required_artifacts) - manifest.keys():
        raise FrameworkError(
            "evaluation_artifact_missing",
            material_ids=sorted(set(required_artifacts) - manifest.keys()),
        )
    questions = manifest.get("frozen-questions", {})
    if questions.get("sha256") != handoff["evaluation"]["sha256"]:
        raise FrameworkError("evaluation_freeze_mismatch")
    for material_id, sha256 in handoff["source_revisions"].items():
        if manifest.get(material_id, {}).get("sha256") != sha256:
            raise FrameworkError("evaluation_source_mismatch", material_id=material_id)
    if required_artifacts:
        handoff = {
            **handoff,
            "required_artifacts": {key: manifest[key]["sha256"] for key in required_artifacts},
        }
    root = binding.root / "evaluations" / evaluation_id
    if not root.exists():
        root.mkdir(parents=True, mode=0o700)
        for material_id, entry in manifest.items():
            path = root / "materials" / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes((material_roots[material_id] / entry["path"]).read_bytes())
        human = handoff.get("human_context", {})
        answers = [
            {key: answer[key] for key in ("message_id", "body", "metadata")}
            for answer in human.get("answers", [])
            if answer.get("metadata", {}).get("source") == "user"
        ]
        if answers:
            dialogue = {
                "answers": answers,
                "questions": [
                    {key: question[key] for key in ("request_id", "question", "basis_ref")}
                    for question in human.get("requests", [])
                ],
            }
            human_bytes = json.dumps(dialogue, ensure_ascii=False, sort_keys=True).encode()
            (root / "materials/human-inputs.json").write_bytes(human_bytes)
            manifest["human-inputs"] = {
                "path": "human-inputs.json",
                "source_ref": "approved-attributed-human-inputs",
                "sha256": hashlib.sha256(human_bytes).hexdigest(),
            }
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
    manifest = _check_sources(root / "materials")
    attempt_path = root / "report-attempt.json"
    attempt = json.loads(attempt_path.read_text()) if attempt_path.exists() else {"index": 0}
    execution_id = f"evaluation-{digest(evaluation_id)[:20]}-{attempt['index']:03d}"
    schema = report_schema(handoff["evaluation"])
    read_refs = attempt.get("read_execution_refs", [])
    previous = None
    resume_from = None
    if previous_ref := attempt.get("previous_execution_ref"):
        previous = repo.read_reference(previous_ref)
        prior_id = previous["intent"]["execution_id"]
        if previous["intent"]["purpose"] != "acceptance" or not prior_id.startswith(
            f"evaluation-{digest(evaluation_id)[:20]}-"
        ):
            raise FrameworkError("evaluation_correction_scope_mismatch")
        if previous["result"].get("thread_id"):
            resume_from = binding.root / "executions" / prior_id / "agent"
            if previous_ref not in read_refs:
                read_refs = [*read_refs, previous_ref]
        else:
            read_refs = []
    # Host task controls count all in-flight roles; the evaluator gets no production inputs.
    control = TaskControl(repo)
    invocation = CodexInvocation(
        binding,
        bridge,
        materials=root / "materials",
        model_revisions=handoff["target"]["model_revisions"],
        resume_from=resume_from,
        instructions="You are an independent read-only semantic evaluator. Read the original sources, "
        "every frozen case, target and any human-inputs using read_material; query the actual "
        "governed model. Explicitly read_material with material_id=frozen-questions before "
        "interpreting case indices. Preserve each original case's numbering and scope; do not "
        "replace workflow/evidence questions with your own model-content checklist. "
        "Read each source_ids entry directly in this independent context even if artifacts "
        "quote it; copied excerpts do not replace the original-source read. "
        "Follow read_material.next_offset until the required source range is complete; "
        "one page with the correct SHA256 is not a complete read. On a correction in your "
        "same native context, reuse unchanged prior actual reads and finish the listed gaps. "
        "Before reporting, directly read every required_artifacts entry in this context, including "
        "each workspace/history chunk; other artifacts quoting it do not replace that read. "
        "Attributed human replies are additional approved sources; preserve "
        "their partial status and scope rather than assuming every question was resolved. "
        "Never create, continue, repair or modify production work. A candidate or production "
        "self-check is not model evidence. When recall leaves a known resource unverified, use "
        "read_model_resource with its actual ontology_id/IRI and class-detail, property-list, "
        "relation-type-list, entity-detail, operation-detail, table-mapping-detail or join-mapping-detail family. "
        "For a consistency or completeness claim, inspect all relevant actual resources in "
        "target.resource_bindings, including properties and nested mappings, rather than only "
        "the top search hits or selected summary definitions. Record the inspected scope and "
        "preserve unread relevant definitions as an evidence gap. "
        "For model_read_scope=whole_model, read resource-list without resource_iri for each "
        "Ontology, inspect every returned definition body and nested mapping, and read the "
        "complete resource-relations graph. A resource_iri filters resource-list; paging.complete "
        "only describes that request scope. Prefer exact known IRIs over repeating broad queries "
        "when search is truncated or degraded. Read coverage qualifies evidence availability, "
        "not whether its business meaning satisfies the criterion. "
        "Preserve retrieval gaps separately from "
        "confirmed model omissions; sources cannot fill missing model facts. "
        "For each criterion, locate every operative condition in actual model fields, definitions "
        "or relationships. Include the decisive model wording or field path in actual_answer/reason; "
        "an IRI, role label or a read receipt alone is not proof of all required conditions. "
        "Check contradictions across related definitions and nested mapping units, state/time scope "
        "and stored facts versus response values. A rule may use natural language, but verify its "
        "scope and relevant object/action/process relationships when the criterion requires them. "
        "Read the governed resource-relations family for actual ontology edges when assessing "
        "links. This family returns the whole authorized Ontology relation graph; resource_iri "
        "does not filter it to an anchor. Read it once per model revision, inspect its returned "
        "endpoints and completeness, and do not repeat the same graph for different anchors. "
        "For each required association name its actual source, predicate and target; "
        "relationships among other resources, matching names, role labels or prose that merely "
        "mentions an object do not prove this link. Preserve graph completeness limitations. "
        "Missing required actual evidence cannot receive passed=true just because the intended "
        "meaning can be inferred from source text. If no returned triple establishes a required "
        "association, preserve that gap rather than substituting an unrelated edge. "
        "For modeled relationships, verify actual endpoints resolve to the intended actual "
        "resources; correct definition text alone does not prove valid topology. "
        "Also verify the predicate's declared meaning and both endpoints' applicability against "
        "the original sources. For follows/implements rule links, different triggers, responsibilities "
        "or effects need a source-supported shared identity or explicit distinction; sharing an "
        "object or having an edge does not establish that business association. "
        "For relation-type-list exact reads use the relation IRI itself as entity, not its source "
        "Class IRI; a zero-item response does not verify that relation or its endpoints. "
        "For workflow claims, match the exact proof's unit, generation, model revision and native "
        "purpose to the same incident and stage. An older ready/revise check cannot prove a later "
        "fault was detected or rechecked. A modeling proposal is not a self_check execution. "
        "Keep observer identity explicit: a Host-collected observation is not an original unit's "
        "read. Attribute an Agent read only to its matching native execution and proof. "
        "A parent's requested or promised bottom-up check does not prove an intermediate declared "
        "or actually executed its leaf checks. Verify the precise referenced proofs and timelines; "
        "preserve missing evidence as a gap and decide each case from its frozen criterion. "
        "Count distinct resource IRIs; several change IDs may reference the same actual resource. "
        "Keep questions, answers and private reasons private. Return exactly one valid JSON object "
        "matching result_schema, without Markdown or narration. When custom_cq_cases is null, use "
        "only the required per-case fields and omit optional CQ/SQL keys. "
        "Escape quotation marks inside strings.",
    )
    prompt = json.dumps(
        {
            "objective": scope.get("objective", binding.data["objective"])
            if scope
            else binding.data["objective"],
            "evaluation_scope": handoff.get("evaluation_scope"),
            "required_artifacts": list(required_artifacts),
            "artifact_contract": "Read required artifacts as scoped targets or attributed subordinate reports. They cannot supply facts missing from the actual model. Judge overall conditions independently, not by adding subordinate PASS scores.",
            "materials": list(manifest),
            "custom_cq_cases": handoff["evaluation"].get("custom_cq"),
            "custom_cq_contract": (
                "For each custom CQ return its frozen cq_id, content_revision and content_digest, "
                "plus outcome, answerability, sql_readiness and sql_execution. If criteria_ready is "
                "false, use question-answer-review (or platform-runtime-incomplete when reads "
                "cannot finish), passed=false, and retain every case. Questions are goals, not "
                "business facts. Read original sources to check criteria; source gaps or out-of-scope "
                "goals need question-answer-review, not modeling-quality failure. Only a source-backed "
                "fact missing from the actual model/recall warrants model-recall-insufficient. "
                "State exact missing codes, time semantics or event sources privately in reason. "
                "Correctly acknowledging a gap does not satisfy a requested statistics capability. "
                "sql_execution must be not_run or blocked: this evaluator has no SQL executor. "
                "PASS requires all selected goals supported; unresolved criteria produce PARTIAL; "
                "any confirmed model/recall insufficiency produces REVISE, retaining incomplete counts."
            )
            if "custom_cq" in handoff["evaluation"]
            else None,
            "source_ids": [
                *handoff["source_revisions"],
                *(["human-inputs"] if "human-inputs" in manifest else []),
            ],
            "target": handoff["target"],
            "evaluation": handoff["evaluation"],
            "model_read_scope": handoff["evaluation"].get(
                "model_read_scope", "referenced_resources"
            ),
            "result_schema": schema,
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
                "read_execution_refs": [*read_refs, ref] if native.get("thread_id") else [],
            },
        )
        raise FrameworkError("evaluation_turn_failed", layer="runtime/infrastructure")
    if resume_from and native.get("thread_id") != previous["result"]["thread_id"]:
        raise FrameworkError("evaluation_correction_context_changed")
    events = [
        binding.root
        / "executions"
        / repo.read_reference(old)["intent"]["execution_id"]
        / "agent/events.jsonl"
        for old in read_refs
    ] + [binding.root / "executions" / execution_id / "agent/events.jsonl"]
    try:
        report = decode_json_result(native["final_response"], schema)
        public = validate_report(
            report,
            handoff,
            events,
            required_materials={
                key: manifest[key]["sha256"]
                for key in [
                    *(["human-inputs"] if "human-inputs" in manifest else []),
                    *required_artifacts,
                ]
            },
        )
    except (ResultContractError, FrameworkError) as error:
        # Correct only report structure/reads; the independent frozen standard stays intact.
        coverage = read_coverage(
            events,
            {
                "frozen-questions": manifest["frozen-questions"]["sha256"],
                **handoff["source_revisions"],
                **handoff.get("required_artifacts", {}),
            },
            handoff["target"],
            model_read_scope=handoff["evaluation"].get("model_read_scope", "referenced_resources"),
        )
        feedback = (
            error.as_dict()
            if isinstance(error, FrameworkError)
            else {"code": "result_contract_error", "detail": str(error), **error.details}
        )
        feedback["coverage"] = coverage
        write_json(
            attempt_path,
            {
                "index": attempt["index"] + 1,
                "error": feedback,
                "previous_execution_ref": ref,
                "read_execution_refs": [*read_refs, ref],
            },
        )
        raise FrameworkError("evaluation_report_needs_correction", detail=str(error)) from error
    if bridge.call("snapshot")["model_revisions"] != handoff["target"]["model_revisions"]:
        raise FrameworkError("frozen_target_changed")
    write_json(root / "private-report.json", report)
    if scope is not None:
        public["evaluation_scope"] = handoff["evaluation_scope"]
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
    commands[-1].add_argument("--required-artifact", action="append", default=[])
    commands[-1].add_argument(
        "--scope-file",
        type=Path,
        help="Frozen bounded/additional evaluation scope; preserves primary reports",
    )
    commands.append(
        sub.add_parser("cq-sync", help="Queue current project CQ goals at a safe boundary")
    )
    cq_evaluate = sub.add_parser(
        "cq-evaluate", help="Freeze and independently check project CQ goals"
    )
    cq_evaluate.add_argument("--evaluation-id", required=True)
    cq_evaluate.add_argument("--question-id", action="append", default=None)
    commands.append(cq_evaluate)
    commands.append(sub.add_parser("questions", help="List durable questions and reply states"))
    commands.append(sub.add_parser("budget", help="Read and refresh the bound amount budget"))
    budget_add = sub.add_parser("budget-add", help="Apply a Host-authorized budget addition file")
    budget_add.add_argument("--authorization-file", type=Path, required=True)
    commands.append(budget_add)
    board = sub.add_parser("board", help="Read task member cards and signed requests")
    board.add_argument("--agent-id")
    board.add_argument("--revision", type=int)
    commands.append(board)
    snapshot_save = sub.add_parser("snapshot-save", help="Save a named Host workflow snapshot")
    snapshot_save.add_argument("--name", required=True)
    snapshot_save.add_argument("--include-platform", action="store_true")
    commands.append(snapshot_save)
    commands.append(sub.add_parser("snapshot-list"))
    snapshot_show = sub.add_parser("snapshot-show")
    snapshot_show.add_argument("--snapshot", required=True)
    commands.append(snapshot_show)
    snapshot_diff = sub.add_parser("snapshot-diff")
    snapshot_diff.add_argument("--before", required=True)
    snapshot_diff.add_argument("--after", required=True)
    commands.append(snapshot_diff)
    fork = sub.add_parser(
        "snapshot-fork", help="Fork captured platform data and business context; archive source"
    )
    fork.add_argument("--snapshot", required=True)
    fork.add_argument("--new-run-dir", type=Path, required=True)
    fork.add_argument("--new-run-id", required=True)
    fork.add_argument("--fork-reason", required=True)
    fork.add_argument("--authorization-reference", required=True)
    fork.add_argument("--archive-source", action="store_true")
    commands.append(fork)
    overview = sub.add_parser(
        "overview-refresh", help="Generate authorized actual-model navigation"
    )
    overview.add_argument("--overview-id", required=True)
    overview.add_argument("--topic", required=True)
    overview.add_argument("--view", choices=("consumer", "user"), default="consumer")
    commands.append(overview)
    overview_show = sub.add_parser(
        "overview-show", help="Read navigation with current access and freshness"
    )
    overview_show.add_argument("--overview-id", required=True)
    overview_show.add_argument("--view", choices=("consumer", "user"), default="consumer")
    commands.append(overview_show)
    revise = sub.add_parser(
        "source-revise", help="Queue an explicit source version and affected units"
    )
    revise.add_argument("--change-file", type=Path, required=True)
    commands.append(revise)
    tree = sub.add_parser("work-tree", help="Read one level of the current dynamic work tree")
    tree.add_argument("--parent-id", default="modeling")
    unit_check = sub.add_parser(
        "check-unit", help="Run an original unit's bounded production read-back"
    )
    unit_check.add_argument("--unit-id", required=True)
    commands.append(unit_check)
    tree.add_argument("--offset", type=int, default=0)
    tree.add_argument("--limit", type=int, default=20)
    commands.append(tree)
    for name in ("reply", "input"):
        command = sub.add_parser(name, help="Persist a human reply or unsolicited input")
        commands.append(command)
        text = command.add_mutually_exclusive_group(required=True)
        text.add_argument("--text")
        text.add_argument("--text-file", type=Path)
        command.add_argument("--message-id", default=None)
        command.add_argument("--author", default="user")
        command.add_argument("--partial", action="store_true")
        if name == "input":
            command.add_argument("--unit-id")
        if name == "reply":
            command.add_argument("--request-id", required=True)
            command.add_argument("--request-revision", type=int)
    for command in commands:
        command.add_argument("--run-dir", type=Path, required=True)
    return result


def dispatch(args) -> dict:
    if args.command in {"snapshot-list", "snapshot-show", "snapshot-diff"}:
        from .snapshots import RunSnapshots

        snapshots = RunSnapshots(root=args.run_dir)
        if args.command == "snapshot-list":
            return {"snapshots": snapshots.list()}
        if args.command == "snapshot-show":
            return snapshots.read(args.snapshot)
        return snapshots.diff(args.before, args.after)
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
    pending_path = binding.root / "fork-pending.json"
    if (
        args.command in {"resume", "evaluate", "cq-evaluate"}
        and pending_path.exists()
        and json.loads(pending_path.read_text())["status"] != "ready"
    ):
        raise FrameworkError(
            "fork_result_unsettled", next_action="Inspect preallocated target in fork-pending.json"
        )
    repo, config = repository(binding)
    from .work_plan import WorkPlan

    plan = WorkPlan(binding.data, repo)
    if repo.get(plan.identity):
        binding = plan.binding(binding)
    control, bridge = TaskControl(repo), HostBridge(binding.root)
    human = HumanInput(binding, repo, control)
    if args.command == "cq-sync":
        from .custom_cq import CustomCQ

        if control.synchronize()["mode"] == "stopped":
            return {"status": "task_stopped", "queued": False}
        staged = CustomCQ(binding, repo).sync(bridge)
        return {"status": "queued" if staged else "unchanged", "change": staged}
    if args.command == "cq-evaluate":
        from .custom_cq import CustomCQ

        safe_id(args.evaluation_id)
        folder = binding.root / "cq-evaluation-inputs" / args.evaluation_id
        if (folder / "scope.json").exists():
            scope = json.loads((folder / "scope.json").read_text())
            frozen_snapshot = json.loads((folder / "snapshot.json").read_text())
            if args.question_id is not None and args.question_id != scope.get("selection_ids"):
                raise FrameworkError("cq_evaluation_selection_changed")
        else:
            work = repo.get(binding.identity + ":work")
            if not work or work["content"]["status"] != "handoff_ready":
                raise FrameworkError("handoff_not_ready")
            handoff = repo.read_reference(work["content"]["handoff_ref"])
            frozen_snapshot = bridge.call(
                "cq_snapshot",
                {"question_ids": args.question_id} if args.question_id is not None else {},
            )
            if frozen_snapshot is None:
                raise FrameworkError("cq_project_binding_missing")
            evaluation = CustomCQ(binding, repo).evaluation_package(
                frozen_snapshot, folder / "materials"
            )
            scope = {
                "scope_id": args.evaluation_id,
                "base_freeze_id": handoff["evaluation"]["freeze_id"],
                "source_ids": list(handoff["source_revisions"]),
                "objective": "Check the frozen project CQ goals against the actual governed model.",
                "evaluation": evaluation,
                "selection_ids": args.question_id,
            }
            write_json(folder / "snapshot.json", frozen_snapshot)
            write_json(folder / "scope.json", scope)
        public = evaluate(
            binding, repo, bridge, folder / "materials", args.evaluation_id, scope=scope
        )
        receipt = bridge.call(
            "cq_results",
            {
                "snapshot": frozen_snapshot,
                "public": public,
                "evaluation_id": args.evaluation_id,
            },
        )
        return {**public, "project_result_receipt": receipt}
    if args.command in {"overview-refresh", "overview-show"}:
        from .overviews import read_overview, refresh_overview

        if args.command == "overview-show":
            return read_overview(binding, repo, bridge, args.overview_id, args.view)
        return refresh_overview(binding, repo, bridge, args.overview_id, args.topic, args.view)
    if args.command == "work-tree":
        return plan.tree(args.parent_id, args.offset, args.limit)
    if args.command == "check-unit":
        from .unit_checks import check_unit

        return check_unit(binding, repo, bridge, args.unit_id)
    if args.command == "snapshot-fork":
        from .snapshot_fork import SnapshotFork

        return SnapshotFork(binding, repo, bridge).create(
            args.snapshot,
            args.new_run_dir,
            args.new_run_id,
            args.fork_reason,
            args.authorization_reference,
            args.archive_source,
        )
    if args.command == "source-revise":
        from .revisions import SourceRevisions

        change = json.loads(args.change_file.read_text())
        revisions = SourceRevisions(binding, repo)
        staged = revisions.stage(change, (args.change_file.parent / change["materials"]).resolve())
        with (binding.root / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"change": staged, "status": "queued"}
            selected = revisions.activate()
        recorded = repo.get(binding.identity + ":source-change:" + change["change_id"])["content"]
        return {"change": recorded, "cycle_id": selected.data.get("cycle_id"), "status": "recorded"}
    if args.command in {"budget", "budget-add"}:
        addition = (
            json.loads(args.authorization_file.read_text())
            if args.command == "budget-add"
            else None
        )
        return {
            "budget": synchronize_budget(binding, control, addition=addition),
            "control": control.view(),
        }
    if args.command == "status":
        row = repo.get(binding.identity + ":work")
        budget = synchronize_budget(binding, control)
        return {
            "work": row["content"] if row else None,
            "control": control.view(),
            "budget": budget,
            "source_changes": [
                {
                    k: r["content"][k]
                    for k in ("change_id", "status", "changed_materials", "affected_units")
                }
                for r in repo.list_kind("source_change")
            ],
            "units": {
                unit["unit_id"]: row["content"] if row else None
                for unit in binding.data.get("work_units", [])
                for row in [repo.get(binding.for_unit(unit["unit_id"]).identity + ":work")]
            },
        }
    if args.command == "questions":
        return {"questions": human.requests()}
    if args.command == "board":
        from .team import TeamChannel

        return TeamChannel(binding.data, repo, control).board(args.agent_id, args.revision)
    if args.command == "snapshot-save":
        from .snapshots import RunSnapshots

        snapshots = RunSnapshots(binding, repo)
        with repo.checkpointer(config["checkpoint_schema"]) as saver:
            graph = WorkUnitFlow(binding, repo, bridge, None).compile(saver)
            return snapshots.save(args.name, graph, bridge, args.include_platform)
    if args.command in {"reply", "input"}:
        if getattr(args, "unit_id", None):
            human = HumanInput(binding.for_unit(args.unit_id), repo, control)
        text = args.text if args.text is not None else args.text_file.read_text()
        return human.submit(
            text,
            args.message_id or uuid.uuid4().hex,
            request_id=getattr(args, "request_id", None),
            partial=args.partial,
            author=args.author,
            request_revision=getattr(args, "request_revision", None),
        )
    if args.command in {"pause", "stop"}:
        control.enqueue(uuid.uuid4().hex, args.command)
        return {"control": control.synchronize()}
    if args.command == "cleanup":
        if control.view()["active"]:
            raise FrameworkError("original_activity_unsettled")
        return bridge.call("cleanup")
    if args.command == "evaluate":
        return evaluate(
            binding,
            repo,
            bridge,
            args.package.resolve(),
            args.evaluation_id,
            args.required_artifact,
            json.loads(args.scope_file.read_text()) if args.scope_file else None,
        )
    repo.setup()

    def create_flow(selected):
        if selected.data.get("work_units") or selected.data.get("work_management"):
            from .multi_unit import MultiUnitFlow

            return MultiUnitFlow(selected, repo, bridge, config["checkpoint_schema"])
        return WorkUnitFlow(selected, repo, bridge, CodexInvocation(selected, bridge))

    if args.command == "start" and args.prepare_only:
        return {"status": "prepared", "work": create_flow(binding).initialize()}
    if args.command == "resume":
        synchronize_budget(binding, control)
        control.enqueue(uuid.uuid4().hex, "resume")
        if control.synchronize()["mode"] == "stopped":
            raise FrameworkError("task_stopped")
    with (binding.root / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FrameworkError("run_already_active") from error
        from .revisions import SourceRevisions

        if binding.data.get("custom_cq"):
            from .custom_cq import CustomCQ

            CustomCQ(binding, repo).sync(bridge)
        binding = SourceRevisions(binding, repo).activate()
        while True:
            flow = create_flow(binding)
            if binding.data.get("work_units") or binding.data.get("work_management"):
                result = flow.advance()
            else:
                with repo.checkpointer(config["checkpoint_schema"]) as saver:
                    result = flow.advance(saver)
            revised = SourceRevisions(binding, repo).activate()
            if revised.data == binding.data:
                return result
            binding = revised


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
