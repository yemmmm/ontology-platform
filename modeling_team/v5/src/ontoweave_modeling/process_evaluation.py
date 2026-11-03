"""Optional, explicit, read-only stage diagnostics; never a production completion gate."""

from __future__ import annotations

import fcntl
import hashlib
import json
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from .acceptance import read_coverage, require_governed_read
from .contracts import FrameworkError, digest, safe_id, write_json
from .control import TaskControl
from .execution import CodexInvocation, ExecutionManager
from .results import ResultContractError, decode_json_result

RUBRIC_VERSION = "process-evaluation/v2"
DIMENSION_FIELDS = (
    "dimension",
    "status",
    "score",
    "expectation",
    "finding",
    "evidence",
    "gap",
    "impact",
    "priority",
)
REPORT_SCHEMA = {
    "type": "object",
    "required": [
        "binding_digest",
        "dimensions",
        "combination_cases",
        "unexamined",
        "key_gaps",
    ],
    "properties": {
        "binding_digest": {"type": "string"},
        "dimensions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "object", "required": list(DIMENSION_FIELDS)},
        },
        "combination_cases": {
            "type": "array",
            "items": {"type": "object", "required": ["scenario", "expected", "actual", "evidence"]},
        },
        "unexamined": {"type": "array"},
        "key_gaps": {"type": "array"},
    },
}
DIMENSIONS = {
    "cq": ["goal_coverage", "clarity", "conditions_and_cross_unit_questions", "source_fidelity"],
    "slicing": ["scope_allocation", "whole_rules", "shared_identity", "integration_responsibility"],
    "integration": [
        "compatible_definitions",
        "conditions_and_exceptions",
        "whole_constraints",
        "combination_cases",
    ],
}
INSTRUCTIONS = """You are an independent read-only process evaluator, not formal acceptance.
Read all bound sources and stage artifacts. Assess only the declared scope and versions.
Do not create, continue or repair production; do not write production memory or completion.
Stage boundaries (binding.point):
- cq: assess the source-grounded questions or capability goals, including their coverage,
  clarity, business conditions/exceptions and cross-unit questions. Capability goals may
  include expected answers; this is a defect only if their declared use requires blind
  questions. CQ quality, answer evidence readiness and actual model answerability are
  separate. Missing an applied model or answers is not a question-quality defect.
- slicing: assess the declared plan's scope allocation, whole rules, shared meanings,
  dependencies and integration responsibility. No applied model, receipts or completed
  execution are required to judge a plan. A coherent single unit is valid; do not demand
  delegation, extra roles, hypothetical recovery branches or distinct author/unit names.
- integration: verify the actual combined model at the bound revision with governed
  resource bodies. Check shared identities, upstream conditions, exceptions, units/time
  and whole rules; include a discriminating correct/incorrect combination scenario.
  Read-back of a definition or domain/range does not prove automatic rejection of invalid
  writes or inference enforcement. Do not claim such behavior without execution evidence.
For every stage, distinguish a missing bound artifact from an actual missing production
record or wrong business meaning. Required but unreadable evidence means unverified, not
an invented defect or score. Optional/out-of-scope checks belong in boundary_notes, not
unexamined. Do not require implementation-only evidence for cq or slicing.
evaluator_feedback describes only this diagnostic evaluator's previous error and how to
repair its own report. It is never evidence of a production failure, a missing CQ answer,
or a business gap, and must not affect production scores.
Do not infer correctness from labels, counts, graph paths or self-checks. Generated
answers cannot prove question coverage. Preserve unknowns and unallocated parent scope.
Inspect absent links and rare exceptions, not only existing dependencies. Do not invent
relations. Scope/unit identifiers and actor names may differ without a responsibility gap.
0=core contradiction, 1=major gap, 2=partial with material gap, 3=meets declared scope,
4=meets scope with verified boundaries/exceptions/counterexamples. Missing evidence means
unverified (null score); not_applicable needs a verifiable scope reason. Each dimension
requires expectation, finding, evidence, gap, impact and priority. No weighted total.
For each scored dimension, priority=none means no established gap; any established gap,
including a minor one at score 3 or 4, needs low/medium/high/critical priority and evidence.
Every key_gaps entry must summarize an established gap in a scored dimension with a
non-none priority. Do not use prose alone to declare gaps. When no gap exists, use gap=""
and key_gaps=[]; put normal limits, scope exclusions and notes in boundary_notes. Use
unexamined only for required checks within this stage and declared scope.
Only actual governed model bodies at the bound revision prove integration. Historical
saved reads are historical diagnostics, never current online validation.
Return only one JSON object, without commentary or additional JSON examples:
{binding_digest, dimensions:[{dimension,status,score,expectation,finding,
evidence:[string],gap,impact,priority}], combination_cases:[{scenario,expected,actual,evidence}],
unexamined:[string], key_gaps:[string], boundary_notes:[string]}.
status is scored/unverified/not_applicable;
priority is critical/high/medium/low/none. Evidence strings cite source fields/ranges or
actual model relationships. All required dimensions must appear exactly once.
"""


def validate_config(config):
    if not isinstance(config, dict) or set(config) - {"enabled", "points"}:
        raise FrameworkError("process_evaluation_config_invalid")
    if type(config.get("enabled", False)) is not bool or not isinstance(
        config.get("points", list(DIMENSIONS)), list
    ):
        raise FrameworkError("process_evaluation_config_invalid")
    if set(config.get("points", DIMENSIONS)) - DIMENSIONS.keys():
        raise FrameworkError("process_evaluation_point_invalid")


def require_current_rubric(basis):
    if basis["rubric_version"] != RUBRIC_VERSION or basis["rubric_digest"] != digest(INSTRUCTIONS):
        raise FrameworkError(
            "process_rubric_version_unavailable",
            rubric_version=basis["rubric_version"],
            next_action="Explicitly submit the same artifact versions under the current rubric.",
        )


class ProcessEvaluation:
    def __init__(self, binding, repository, bridge=None):
        self.binding, self.repo, self.bridge = binding, repository, bridge
        self.prefix = "run:" + binding.data["run_id"] + ":process:"
        self.control_id = self.prefix + "control"
        self.root = binding.root / "process-evaluations"

    def settings(self):
        row = self.repo.get(self.control_id)
        if row:
            return row["content"]
        config = self.binding.data.get("process_evaluation", {})
        return {
            "enabled": config.get("enabled", False),
            "points": config.get("points", list(DIMENSIONS)),
            "epoch": 0,
        }

    @contextmanager
    def _control_lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "control.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def configure(self, enabled, points=None):
        with self._control_lock():
            return self._configure(enabled, points)

    @contextmanager
    def _admission_guard(self, basis):
        with self._control_lock():
            settings = self.settings()
            if not settings["enabled"] or basis["point"] not in settings["points"]:
                raise FrameworkError("process_disabled_before_admission")
            require_current_rubric(basis)
            yield

    def _configure(self, enabled, points=None):
        row = self.repo.get(self.control_id)
        prior = self.settings()
        value = {
            "enabled": enabled,
            "points": prior["points"] if points is None else points,
            "epoch": prior["epoch"] + 1,
            "effective_at": time.time(),
        }
        validate_config({k: value[k] for k in ("enabled", "points")})
        self.repo.put_reference(
            self.control_id, "process_control", value, row["revision"] if row else 0
        )
        for record in self.records():
            if record["content"]["state"] == "queued" and (
                not enabled or record["content"]["binding"]["point"] not in value["points"]
            ):
                self._save(
                    record, state="cancelled", reason="disabled_at_epoch:" + str(value["epoch"])
                )
        return value

    def records(self):
        return [
            r
            for r in self.repo.list_kind("process_evaluation")
            if r["object_id"].startswith(self.prefix)
        ]

    def _save(self, row, **changes):
        self.repo.put_reference(
            row["object_id"], "process_evaluation", {**row["content"], **changes}, row["revision"]
        )
        return self.repo.get(row["object_id"])

    def submit(self, submission):
        settings = self.settings()
        point = submission.get("point")
        if not settings["enabled"] or point not in settings["points"]:
            return {"state": "disabled", "reason": "observation_not_enabled"}
        if point not in DIMENSIONS or not submission.get("scope") or not submission.get("goal"):
            raise FrameworkError("process_submission_invalid")
        # Host owns standards/configuration; producers only declare references and scope.
        allowed = {
            "point",
            "scope",
            "goal",
            "unit_ids",
            "source_ids",
            "artifact_refs",
            "reevaluation_id",
        }
        if set(submission) - allowed:
            raise FrameworkError("process_submission_field_forbidden")
        source_ids = sorted(set(submission.get("source_ids", [])))
        if set(source_ids) - self.binding.data["source_manifest"].keys():
            raise FrameworkError("process_source_forbidden")
        refs = sorted(
            {digest(r): r for r in submission.get("artifact_refs", [])}.values(), key=digest
        )
        for ref in refs:
            artifact_row = self.repo.get(ref["object_id"], ref["revision"])
            if not artifact_row or artifact_row["kind"] not in {
                "semantic_record",
                "candidate",
                "team_material",
                "work_plan",
                "work_unit",
            }:
                raise FrameworkError("process_artifact_forbidden")
            content = self.repo.read_reference(ref)  # exact immutable version and digest
            if (
                artifact_row["kind"] == "semantic_record"
                and content.get("view", "production") != "production"
            ):
                raise FrameworkError("process_artifact_forbidden")
        units = sorted(set(submission.get("unit_ids", [])))
        known = {self.binding.actor, self.binding.data["work_unit_id"], "modeling"}
        known.update(u["unit_id"] for u in self.binding.data.get("work_units", []))
        if set(units) - known:
            raise FrameworkError("process_unit_scope_invalid")
        target = self.bridge.call("snapshot") if point == "integration" and self.bridge else None
        basis = {
            "task_ref": self.binding.data["task_ref"],
            "run_id": self.binding.data["run_id"],
            "point": point,
            "scope": submission["scope"],
            "goal": submission["goal"],
            "unit_ids": units,
            "sources": {k: self.binding.data["source_manifest"][k] for k in source_ids},
            "artifact_refs": refs,
            "rubric_version": RUBRIC_VERSION,
            "rubric_digest": digest(INSTRUCTIONS),
            "configuration": {
                "model": self.binding.data["models"]["acceptance"],
                "points": settings["points"],
            },
            "model_revisions": target["model_revisions"] if target else {},
            "reevaluation_id": submission.get("reevaluation_id"),
        }
        identity = self.prefix + digest(basis)
        if prior := self.repo.get(identity):
            return prior["content"]
        missing = []
        if not refs:
            missing.append("artifacts_missing")
        if not source_ids:
            missing.append("sources_missing")
        if point == "integration" and (not target or not target.get("model_revisions")):
            missing.append("actual_model_not_reached")
        value = {
            "binding": basis,
            "binding_digest": digest(basis),
            "state": "unverified" if missing else "queued",
            "reason": missing,
            "submitted_at": time.time(),
            "epoch": settings["epoch"],
            "attempt": 0,
            "target": target,
            "snapshot_atomic": False,
        }
        self.repo.put_reference(identity, "process_evaluation", value, 0)
        for old in self.records():
            b = old["content"]["binding"]
            if (
                old["object_id"] != identity
                and (b["point"], b["scope"]) == (point, basis["scope"])
                and not old["content"].get("superseded_by")
            ):
                self._save(old, superseded_by=identity)
        return value

    def _materials(self, record):
        basis = record["binding"]
        folder = self.root / record["binding_digest"] / "materials"
        manifest_path = folder / "manifest.json"
        if manifest_path.exists():
            saved = json.loads(manifest_path.read_text())
            if all(
                hashlib.sha256((folder / m["path"]).read_bytes()).hexdigest() == m["sha256"]
                for m in saved.values()
            ):
                return folder, saved
            raise FrameworkError("process_frozen_material_changed")
        manifest = {}
        # No hidden evaluation package, chat, production memory or repository mount.
        for material_id, entry in basis["sources"].items():
            path = (self.binding.materials / entry["path"]).resolve()
            if not path.is_relative_to(self.binding.materials.resolve()):
                raise FrameworkError("process_source_forbidden")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise FrameworkError("process_source_version_unavailable", material_id=material_id)
            manifest[material_id] = {**entry, "path": digest(material_id) + ".txt"}
            folder.mkdir(parents=True, exist_ok=True)
            (folder / manifest[material_id]["path"]).write_bytes(payload)
        for index, ref in enumerate(basis["artifact_refs"]):
            payload = json.dumps(self.repo.read_reference(ref), ensure_ascii=False).encode()
            material_id = "stage-artifact-" + str(index)
            if material_id in manifest:
                raise FrameworkError("process_material_identity_conflict")
            manifest[material_id] = {
                "path": material_id + ".json",
                "source_ref": ref,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            (folder / manifest[material_id]["path"]).write_bytes(payload)
        write_json(folder / "manifest.json", manifest)
        return folder, manifest

    def run(self, binding_digest, *, invoke=None, retry=False):
        safe_id(binding_digest)
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / (binding_digest + ".lock")).open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"state": "running", "reason": "original_worker_active"}
            return self._run(binding_digest, invoke=invoke, retry=retry)

    def _run(self, binding_digest, *, invoke=None, retry=False):
        safe_id(binding_digest)
        row = self.repo.get(self.prefix + binding_digest)
        if not row:
            raise FrameworkError("process_evaluation_not_found")
        record = row["content"]
        if record["state"] in {"completed", "cancelled", "unverified"}:
            return record
        settings = self.settings()
        if record["state"] != "running" and (
            not settings["enabled"] or record["binding"]["point"] not in settings["points"]
        ):
            return self._save(row, state="cancelled", reason="disabled")["content"]
        if record["state"] == "failed":
            if not retry:
                return record
            record = self._save(row, state="queued", attempt=record["attempt"] + 1)["content"]
            row = self.repo.get(row["object_id"])
        execution_id = "process-" + binding_digest[:24] + f"-{record['attempt']:03d}"
        manager = ExecutionManager(
            self.repo, TaskControl(self.repo), self.binding, unit_id="process:" + binding_digest
        )
        error_scope = "evaluation_runtime"
        try:
            basis = record["binding"]
            folder, manifest = self._materials(record)
            if (
                basis["point"] == "integration"
                and self.bridge.call("snapshot")["model_revisions"] != basis["model_revisions"]
            ):
                raise FrameworkError("process_target_changed")
            if record["state"] != "running":
                with self._control_lock():
                    current = self.settings()
                    row = self.repo.get(row["object_id"])
                    if (
                        row["content"]["state"] == "cancelled"
                        or not current["enabled"]
                        or basis["point"] not in current["points"]
                    ):
                        return self._save(
                            row, state="cancelled", reason="disabled_before_dispatch"
                        )["content"]
                    row = self._save(
                        row, state="running", started_at=time.time(), execution_id=execution_id
                    )
            prompt = json.dumps(
                {
                    "binding_digest": binding_digest,
                    "binding": basis,
                    "dimensions": DIMENSIONS[basis["point"]],
                    "target": record["target"],
                    "materials": manifest,
                    "evaluator_feedback": {
                        "scope": "process_evaluation_only",
                        "previous_error": record["error"],
                        "action": "Repair your diagnostic report only; this is not production evidence.",
                    }
                    if record.get("error") and record.get("error_scope") == "evaluator_report"
                    else None,
                }
            )
            ref = manager.run(
                execution_id,
                "process_evaluation",
                prompt,
                invoke
                or CodexInvocation(
                    self.binding,
                    self.bridge,
                    materials=folder,
                    instructions=INSTRUCTIONS,
                    model_revisions=basis["model_revisions"],
                    read_only=True,
                    materials_only=basis["point"] != "integration",
                ),
                resume_original=True,
                admission_guard=lambda: self._admission_guard(basis),
            )
            native = self.repo.read_reference(ref)["result"]
            if native["status"] != "completed":
                raise FrameworkError("process_native_turn_failed", layer="runtime/infrastructure")
            require_current_rubric(basis)
            error_scope = "evaluator_report"
            report = decode_json_result(native["final_response"], REPORT_SCHEMA)
            validate_report(report, basis["point"], binding_digest)
            events = (
                self.binding.root
                / "executions"
                / self.binding.execution_id(execution_id)
                / "agent/events.jsonl"
            )
            coverage = read_coverage(
                events,
                {k: v["sha256"] for k, v in manifest.items()},
                record["target"] or {"model_revisions": {}},
                evidence_iris=[e for d in report["dimensions"] for e in d["evidence"]],
            )
            if basis["point"] == "integration":
                require_governed_read(events, basis["model_revisions"])
                if not coverage["returned_resource_bodies"]:
                    raise FrameworkError("process_actual_model_body_missing")
                error_scope = "evaluation_runtime"
                if self.bridge.call("snapshot")["model_revisions"] != basis["model_revisions"]:
                    raise FrameworkError("process_target_changed")
                error_scope = "evaluator_report"
            if not coverage["complete"]:
                raise FrameworkError("process_evidence_incomplete", coverage=coverage)
            row = self.repo.get(row["object_id"])
            result = self._save(
                row,
                state="completed",
                report=report,
                satisfaction=satisfaction(report),
                execution_ref=ref,
                coverage=coverage,
                error=None,
                error_scope=None,
                finished_at=time.time(),
            )["content"]
        except (FrameworkError, ValueError, OSError, TypeError, KeyError) as error:
            row = self.repo.get(row["object_id"])
            # Unknown in-flight identity stays running for reconciliation, never new dispatch.
            active = TaskControl(self.repo).view()["active"]
            state = "running" if "process:" + binding_digest in active else "failed"
            if (
                isinstance(error, FrameworkError)
                and error.code == "process_disabled_before_admission"
            ):
                state = "cancelled"
            result = self._save(
                row,
                state=state,
                error=error.as_dict()
                if isinstance(error, FrameworkError)
                else {"code": str(error), **error.details}
                if isinstance(error, ResultContractError)
                else str(error),
                error_scope=error_scope,
                **({"finished_at": time.time()} if state == "failed" else {}),
            )["content"]
        self.summary("progress")
        return result

    def summary(self, production_status="progress"):
        with self._control_lock():
            return self._summary(production_status)

    def _summary(self, production_status):
        previous = self.repo.get(self.prefix + "summary")
        if production_status == "progress" and previous:
            production_status = previous["content"]["report"]["production_status"]
        records = [r["content"] for r in self.records()]
        for record in records:
            changed_sources = [
                k
                for k, source in record["binding"]["sources"].items()
                if self.binding.data["source_manifest"].get(k, {}).get("sha256") != source["sha256"]
            ]
            changed_artifacts = [
                ref["object_id"]
                for ref in record["binding"]["artifact_refs"]
                if not (current := self.repo.get(ref["object_id"]))
                or current["revision"] != ref["revision"]
            ]
            record["applicability"] = {
                "state": "superseded"
                if record.get("superseded_by")
                else "historical"
                if changed_sources or changed_artifacts
                else "bound_version_only",
                "changed_sources": changed_sources,
                "changed_artifacts": changed_artifacts,
                "current_online_model_verified": False,
            }
        stages = [
            {
                "point": p,
                "state": "observed"
                if any(r["binding"]["point"] == p for r in records)
                else "unobserved",
            }
            for p in DIMENSIONS
        ]
        executions = [
            r["content"]
            for r in self.repo.list_kind("execution")
            if r["content"]["intent"]["purpose"] == "process_evaluation"
        ]
        usage = []
        ledger = None
        if self.binding.data["authorization"]["mode"] == "amount":
            ledger_path = Path(self.binding.data["authorization"]["budget_ref"]) / "state.json"
            try:
                if ledger_path.exists():
                    ledger = json.loads(ledger_path.read_text())
            except (OSError, ValueError):
                ledger = None
        for execution in executions:
            directory = self.binding.root / "executions" / execution["intent"]["execution_id"]
            source_prefix = "v5-" + digest(str(directory))[:24]
            priced_units = [
                u
                for u in (ledger or {}).get("units", {}).values()
                if str(u.get("source", {}).get("source_id", "")).startswith(source_prefix)
            ]
            usage.append(
                {
                    "execution_id": directory.name,
                    "state": execution["state"],
                    "evidence_files": [
                        str(p.relative_to(self.binding.root))
                        for name in (
                            "usage.jsonl",
                            "provider-usage.jsonl",
                            "budget-native-usage.jsonl",
                        )
                        if (p := directory / name).exists()
                    ],
                    "budget_units": priced_units,
                    "cost": str(sum((Decimal(u["amount"]) for u in priced_units), Decimal(0)))
                    if priced_units and all(u.get("amount") is not None for u in priced_units)
                    else None,
                    "cost_authority": "original_task_budget_ledger; missing is unknown",
                }
            )
        report = {
            "production_status": production_status,
            "production_complete": production_status
            in {"handoff_ready", "failed", "stopped", "closed"},
            "evaluation_complete": all(r["state"] not in {"queued", "running"} for r in records),
            "formal_acceptance": {
                "state": "separate",
                "report_refs": [
                    str(p.relative_to(self.binding.root))
                    for p in sorted(
                        (self.binding.root / "evaluations").glob("*/private-report.json")
                    )
                ],
            },
            "settings": self.settings(),
            "stages": stages,
            "records": records,
            "usage": usage,
            "budget_ref": self.binding.data["authorization"].get("budget_ref"),
            "external_host_usage": "separate; excluded from task budget",
            "duration_seconds": sum(
                r.get("finished_at", r.get("started_at", 0)) - r.get("started_at", 0)
                for r in records
            ),
            "score_deltas": [],
            "comparability": "No automatic score deltas across changed bindings.",
        }
        prior = self.repo.get(self.prefix + "summary")
        if prior and prior["content"]["report"] == report:
            return prior["content"]
        version = prior["revision"] + 1 if prior else 1
        result = {"version": version, "report": report}
        write_json(self.root / f"summary-{version:04d}.json", result)
        lines = [
            f"# Process evaluation {version}",
            f"Production: {production_status}",
            "Formal acceptance: separate",
            "",
        ]
        lines.extend(f"- {s['point']}: {s['state']}" for s in stages)
        lines.extend(
            ["", "| Stage | Scope | Execution | Expectation |", "| --- | --- | --- | --- |"]
        )
        for r in records:
            lines.append(
                f"| {r['binding']['point']} | {r['binding']['scope']} | {r['state']} | {r.get('satisfaction', 'unverified')} |"
            )
            for d in r.get("report", {}).get("dimensions", []):
                lines.append(
                    f"\n- {d['dimension']}: {d['score'] if d['score'] is not None else d['status']}; {d['finding']}; gap: {d['gap']}"
                )
            for gap in r.get("report", {}).get("key_gaps", []):
                lines.append(f"\n- Key gap: {gap}")
            for note in r.get("report", {}).get("boundary_notes", []):
                lines.append(f"\n- Boundary note: {note}")
        lines.extend(
            [
                "",
                "## Full evidence",
                "",
                "```json",
                json.dumps(report, ensure_ascii=False, indent=2),
                "```",
            ]
        )
        (self.root / f"summary-{version:04d}.md").write_text("\n".join(lines))
        self.repo.put_reference(self.prefix + "summary", "process_summary", result, version - 1)
        return result


def validate_report(report, point, binding_digest):
    if report.get("binding_digest") != binding_digest:
        raise FrameworkError("process_report_binding_mismatch")
    dimensions = report.get("dimensions", [])
    if not isinstance(dimensions, list) or any(not isinstance(d, dict) for d in dimensions):
        raise FrameworkError("process_report_dimensions_invalid")
    if sorted(d.get("dimension", "") for d in dimensions) != sorted(DIMENSIONS[point]):
        raise FrameworkError("process_report_dimensions_invalid")
    for d in dimensions:
        if not all(k in d for k in DIMENSION_FIELDS):
            raise FrameworkError("process_report_dimension_fields_missing")
        if d["status"] not in {"scored", "unverified", "not_applicable"} or not isinstance(
            d["evidence"], list
        ):
            raise FrameworkError("process_report_status_invalid")
        if (
            any(
                not isinstance(d[k], str)
                for k in ("expectation", "finding", "gap", "impact", "priority")
            )
            or not d["expectation"]
            or not d["finding"]
            or any(not isinstance(e, str) or not e for e in d["evidence"])
        ):
            raise FrameworkError("process_report_evidence_invalid")
        if d["priority"] not in {"critical", "high", "medium", "low", "none"}:
            raise FrameworkError("process_report_priority_invalid")
        if d["status"] == "scored":
            if type(d["score"]) is not int or not 0 <= d["score"] <= 4 or not d["evidence"]:
                raise FrameworkError("process_report_score_invalid")
        elif d["score"] is not None:
            raise FrameworkError("process_unknown_must_not_score")
        if d["status"] == "not_applicable" and not d["evidence"]:
            raise FrameworkError("process_not_applicable_reason_missing")
    if not all(
        isinstance(report.get(k), list) for k in ("key_gaps", "unexamined", "combination_cases")
    ):
        raise FrameworkError("process_report_coverage_missing")
    for field in ("key_gaps", "unexamined", "boundary_notes"):
        values = report.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise FrameworkError("process_report_notes_invalid", field=field)
    if (
        point == "integration"
        and any(d["status"] == "scored" for d in dimensions)
        and not report["combination_cases"]
    ):
        raise FrameworkError("process_combination_cases_missing")

    for case in report["combination_cases"]:
        if not isinstance(case, dict) or not all(
            case.get(k) for k in ("scenario", "expected", "actual", "evidence")
        ):
            raise FrameworkError("process_combination_case_incomplete")


def satisfaction(report):
    ds = report["dimensions"]
    # Narrative fields explain the judgment; they must not make semantic decisions.
    if any(d["status"] == "scored" and (d["score"] < 3 or d["priority"] != "none") for d in ds):
        return "gaps"
    if report["unexamined"] or any(d["status"] == "unverified" for d in ds):
        return "unverified"
    if all(d["status"] == "not_applicable" for d in ds):
        return "not_applicable"
    return "satisfied"
