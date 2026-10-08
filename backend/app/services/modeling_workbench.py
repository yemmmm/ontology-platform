"""Fixed, administrator-only public projection of existing Team run artifacts.

The general projection never reads CQ private data. The administrator CQ overview
reads frozen question text and visibility only, without answers or diagnostics.
Source files remain authoritative; no second state store is introduced.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.security.secrets import SecretDetected, scan_domain_payload

RUNS_ROOT = Path(__file__).resolve().parents[3] / "workspaces/modeling-runs"
RUN_LIMIT = 1000
ARTIFACT_LIMIT = 500
MAX_FILE_BYTES = 8 * 1024 * 1024
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$")
TERMINAL_STATES = {"CLEANED", "FAILED", "TERMINAL_REPORT_COMPLETE"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def content_digest(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def report_digest_scope(value: dict) -> str:
    body = {k: v for k, v in value.items() if k != "report_digest"}
    if value.get("report_digest") == content_digest(body):
        return "complete_record"
    # build_batch_report hashes its core. The CLI subsequently appends
    # sessions and computes full_pass; those fields are recorded observations,
    # not part of the producer's report digest preimage.
    if value.get("schema_version") == "r3-0-011-acceptance-batch-report/v1" and value.get(
        "report_digest"
    ) == content_digest({k: v for k, v in body.items() if k not in {"sessions", "full_pass"}}):
        return "batch_report_core"
    return "mismatch"


def workspace_digests(context: dict) -> tuple[dict, dict]:
    """Same read-only observation recipe as the CQ producer; no verdict logic."""
    if (
        not isinstance(context, dict)
        or context.get("state") != "ready"
        or not context.get("default_graph_set_id")
        or not isinstance(context.get("members"), list)
    ):
        raise ValueError("workspace observation incomplete")
    revisions = sorted(
        (q.get("role"), q.get("revision"), q.get("content_hash"))
        for q in context["members"]
        if isinstance(q, dict)
    )
    return (
        {
            "state_digest": content_digest(
                {"state": context["state"], "source_signature": context.get("source_signature")}
            )
        },
        {
            "state_digest": content_digest(
                {
                    "graph_set_id": context["default_graph_set_id"],
                    "status": context.get("graph_set_status"),
                    "revisions": revisions,
                }
            )
        },
    )


def scalars(value: Any, fields: str) -> dict:
    """Closed fields, scalar or scalar-list values only (never arbitrary JSON)."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in fields.split():
        x = value.get(key)
        if key not in value:
            continue
        if x is None or isinstance(x, (str, int, float, bool)):
            result[key] = x
        elif isinstance(x, list) and all(
            item is None or isinstance(item, (str, int, float, bool)) for item in x
        ):
            result[key] = x
    return result


def records(value: Any, fields: str) -> list[dict]:
    return (
        [scalars(item, fields) for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def object_field(value: dict, key: str, fields: str) -> dict:
    return scalars(value.get(key), fields)


SCOPE_FIELDS = "project_id ontology_id ontology_ids kind slice_id slice_ids viewpoint viewpoints"
REF_FIELDS = "candidate_id revision candidate_revision item_id item_ids candidate_digest"
BINDING_FIELDS = (
    "candidate_revision candidate_item_ids candidate_content_digests client_item_id "
    "command_index decision_ids"
)
QUESTION_FIELDS = (
    "question_id question answer_points unknown review_content_version content_version"
)
ANSWER_FIELDS = (
    "question_id question_content_version content_version answer reason status "
    "failure_layer explicit_unknown evidence_refs schema_version batch_id"
)
VERDICT_FIELDS = "question_id batch_id verdict failure_layer note schema_version"
POINT_FIELDS = (
    "point_id answer_point_id point_index answer_point_index verdict status "
    "diagnosis category cause reason note model_expression retrieval consumer_understanding "
    "question_scope reason_unknown"
)


def question(item: dict) -> dict:
    return {
        **scalars(item, QUESTION_FIELDS),
        "scope": object_field(item, "scope", SCOPE_FIELDS),
        "review_binding": object_field(
            item,
            "review_binding",
            "review_id content_version digest review_content_version decision_digest",
        ),
    }


def scalar_map(value: Any) -> dict:
    """Schema-declared business property maps contain flat literal values."""
    if not isinstance(value, dict):
        return {}
    forbidden = {
        "password",
        "api_key",
        "token",
        "authorization",
        "credentials",
        "secret",
        "hidden_answers",
        "private_diagnostics",
        "env",
    }
    return scalars(
        value, " ".join(k for k in value if isinstance(k, str) and k.lower() not in forbidden)
    )


def neutral_value(value: Any) -> Any:
    """Published neutral candidate payload, projected along its declared shape."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if not isinstance(value, dict):
        return None
    result = scalars(
        value,
        "entity_id class_id property_id relation_type_id shape_id name label "
        "description business_meaning range datatype predicate predicate_kind "
        "table_mapping_id join_mapping_id enum_meaning_id metric_id column "
        "enum_value schema_name table_name schema_source conversion_rule_iri "
        "source target value language kind definition_id",
    )
    for key in (
        "subject",
        "object",
        "property_ref",
        "class_ref",
        "mapped_definition",
        "table_mapping_ref",
        "left_table_mapping",
        "right_table_mapping",
        "semantic_value_ref",
    ):
        if key in value:
            result[key] = (
                scalars(value[key], "definition_ref")
                if isinstance(value[key], dict)
                else value[key]
                if isinstance(value[key], str)
                else None
            )
    result["column_mappings"] = records(value.get("column_mappings"), "column meaning")
    result["join_columns"] = records(value.get("join_columns"), "left right")
    for key in (
        "semantic_definition",
        "action_definition",
        "parameter_definition",
    ):
        if key in value:
            result[key] = object_field(
                value,
                key,
                "semantic_role business_meaning applicability unknowns "
                "conflicting_meanings not_applicable input_status output_status "
                "direction value_kind value_type required occurrence_condition "
                "cardinality unit enum_values missing_meaning result_kind kind "
                "script_language script_version script_source execution_environment "
                "missing_policy change_note",
            )
    mapping = value.get("mapping_definition")
    if isinstance(mapping, dict):
        result["mapping_definition"] = {
            **scalars(
                mapping,
                "schema_version row_grain row_scope record_key_columns object_key_columns "
                "source_key duplicate_risk relationship_meaning step_semantics execution_prerequisite "
                "null_value_rule denominator_rule aggregation time_field grain value_expression "
                "join_cardinality encoding conversion_rule metric_definition mapping_direction "
                "request_location response_location interface_version operation_iri binding_iri",
            ),
            "field_meanings": scalar_map(mapping.get("field_meanings")),
            "identifiers": scalar_map(mapping.get("identifiers")),
        }
    values = value.get("values")
    if isinstance(values, dict):
        result["values"] = scalar_map(values)
        # These are explicit annotation/payload slots in neutral entity values,
        # rather than arbitrary recursively nested business JSON.
        for key in (
            "semantic_definition",
            "action_definition",
            "parameter_definition",
                "mapping_payload",
        ):
            if isinstance(values.get(key), dict):
                result["values"][key] = (
                    neutral_value(values[key])
                    if key == "mapping_payload"
                    else neutral_value({key: values[key]})[key]
                )
    return result


def scenario(value: dict) -> dict:
    result = scalars(value, "schema_version scenario_id topology_decision_ref")
    result["explicit_unknowns"] = records(
        value.get("explicit_unknowns"), "topic needed_from status"
    )
    result["slices"] = []
    for item in value.get("slices", []):
        if not isinstance(item, dict):
            continue
        row = scalars(item, "slice_id name scope owner status")
        row["viewpoints"] = []
        for cell in item.get("viewpoints", []):
            if isinstance(cell, dict):
                c = scalars(
                    cell,
                    "viewpoint status note expressed_scope unknowns not_applicable "
                    "conflicts pending_work owner responsible verified_at",
                )
                c["candidate_refs"] = records(cell.get("candidate_refs"), REF_FIELDS)
                c["artifact_refs"] = records(
                    cell.get("artifact_refs"), "artifact path digest revision"
                )
                row["viewpoints"].append(c)
        result["slices"].append(row)
    result["shared_terms"] = []
    for item in value.get("shared_terms", []):
        if isinstance(item, dict):
            result["shared_terms"].append(
                {
                    **scalars(
                        item,
                        "term definition_id meaning_scope status used_by_slices owner_slice notes",
                    ),
                    "candidate_refs": records(item.get("candidate_refs"), REF_FIELDS),
                }
            )
    result["cross_slice_dependencies"] = records(
        value.get("cross_slice_dependencies"), "from_slice to_slice direction connection_points"
    )
    # The map contract expressly forbids hidden diagnostic content. Only its
    # registered cross-slice public business coverage is exposed.
    result["cross_slice_competency_questions"] = records(
        value.get("cross_slice_competency_questions"),
        "question_id cq_id question slice_ids spans_slices scope status",
    )
    result["adjustments"] = []
    for item in value.get("adjustments", []):
        if not isinstance(item, dict):
            continue
        adjustment = scalars(
            item,
            "adjustment_id kind from_slice to_slice reason status affected_slice_ids "
            "change approved_by_coordinator",
        )
        review = item.get("review")
        if isinstance(review, dict):
            adjustment["review"] = scalars(
                review, "definition_ids coverage coverage_note outcome reason"
            )
            for key in ("before_refs", "after_refs", "references"):
                fields = "candidate_id revision item_id"
                if key == "references":
                    fields += " slice_id result note"
                adjustment["review"][key] = records(review.get(key), fields)
        result["adjustments"].append(adjustment)
    return result


def candidate(value: dict) -> dict:
    result = scalars(value, "schema_version scenario_id candidate_id revision explicit_unknowns")
    result["items"] = []
    for item in value.get("items", []):
        if not isinstance(item, dict):
            continue
        row = scalars(
            item, "item_id item_kind business_meaning value slice_ids shared_scope unknowns"
        )
        row["value"] = neutral_value(item.get("value"))
        row["relation_endpoints"] = object_field(
            item, "relation_endpoints", "source target predicate from_item_id to_item_id"
        )
        row["semantic_definition"] = object_field(
            item,
            "semantic_definition",
            "definition_id semantic_role description meaning scope "
            "state rationale unknowns analyzed_not_materialized applicability business_meaning "
            "conflicting_meanings not_applicable",
        )
        result["items"].append(row)
    return result


def materialization(value: dict) -> dict:
    result = scalars(
        value,
        "schema_version plan_id revision projection_digest ordinal intent_ordinal "
        "mode batch_id attempt_id status submitted_via plan_ref response_digest "
        "idempotency_key candidate_id candidate_revision candidate_digest",
    )
    projection = value.get("projection", {})
    if isinstance(projection, dict):
        p = scalars(
            projection,
            "task_id contract_version scenario_id session_id client_batch_id "
            "ontology_id candidate_id candidate_revision candidate_digest",
        )
        p["decision_bindings"] = records(projection.get("decision_bindings"), BINDING_FIELDS)
        p["identity_bindings"] = records(
            projection.get("identity_bindings"), "item_id resource_iri resource_id identity_kind"
        )
        p["items"] = records(
            projection.get("items"),
            "client_item_id item_id command_kind resource_iri candidate_item_id",
        )
        result["projection"] = p
    result["decision_bindings"] = records(value.get("decision_bindings"), BINDING_FIELDS)
    result["command_digests"] = [v for v in value.get("commands", []) if isinstance(v, str)]
    result["commands"] = []
    for item in value.get("commands", []):
        if isinstance(item, dict):
            result["commands"].append(
                {
                    **scalars(item, "command_index command_kind status client_item_id item_id"),
                    "result": object_field(
                        item,
                        "result",
                        "status batch_id attempt_id audit_id "
                        "workspace_version resource_iri resource_id applied_at",
                    ),
                    "outputs": object_field(item, "outputs", "resource_iri resource_id"),
                }
            )
    result["entries"] = records(
        value.get("entries"),
        "decision_id status target_id candidate_id candidate_revision "
        "item_ids applied_batch_id applied_attempt_id plan_ref projection_digest",
    )
    result["decisions"] = records(
        value.get("decisions"),
        "decision_id decision candidate_id candidate_revision candidate_digest "
        "item_ids approved_by reviewed_at",
    )
    result["translation_approvals"] = records(
        value.get("translation_approvals"), "plan_ref projection_digest decision reviewed_at note"
    )
    return result


class WorkbenchNotFound(LookupError):
    pass


class ModelingWorkbenchService:
    def __init__(self, runs_root: Path | None = None, workspace_reader=None):
        self.root = runs_root or RUNS_ROOT
        self.workspace_reader = workspace_reader

    def _safe(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
            current = self.root
            if current.is_symlink():
                return False
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    return False
            return True
        except ValueError:
            return False

    def _read(self, path: Path) -> tuple[Any, dict, list[str]]:
        if not self._safe(path):
            return None, {}, ["unsafe_source"]
        if not path.exists():
            return None, {}, ["missing_source"]
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                return None, {}, ["unreadable_or_oversized_source"]
            content = path.read_bytes()
            source = {
                "path": path.relative_to(self.root).as_posix(),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            }
            value = (
                tomllib.loads(content.decode())
                if path.suffix == ".toml"
                else [json.loads(line) for line in content.splitlines() if line.strip()]
                if path.suffix == ".jsonl"
                else json.loads(content)
            )
            return value, source, []
        except (OSError, ValueError):
            return None, {}, ["unreadable_source"]

    def _binding(self, run: Path, state: dict) -> tuple[dict | None, list[str]]:
        candidates = [
            state.get("platform_binding"),
            state.get("cleanup", {}).get("scope")
            if isinstance(state.get("cleanup"), dict)
            else None,
        ]
        handoff, _, _ = self._read(run / "acceptance-v3/production-handoff.json")
        if isinstance(handoff, dict):
            candidates.append(handoff.get("scope_binding"))
        bindings = []
        for value in candidates:
            if not isinstance(value, dict) or not isinstance(value.get("project_id"), str):
                continue
            ids = value.get("ontology_ids")
            if not isinstance(ids, list):
                ids = [value["ontology_id"]] if value.get("ontology_id") else []
            if any(not isinstance(i, str) or not i for i in ids):
                return None, ["invalid_platform_binding"]
            bindings.append({"project_id": value["project_id"], "ontology_ids": sorted(set(ids))})
        if not bindings:
            return None, ["platform_binding_missing"]
        if any(b != bindings[0] for b in bindings[1:]):
            return None, ["platform_binding_conflict"]
        return bindings[0], []

    def _summary(self, run: Path, project_id: str) -> dict | None:
        state, source, _ = self._read(run / "state.json")
        if not isinstance(state, dict):
            return None
        binding, limitations = self._binding(run, state)
        if binding is None or binding["project_id"] != project_id:
            return None
        if state.get("run_id", run.name) != run.name:
            return None
        return {
            "run_id": run.name,
            "state": state.get("state"),
            "source_updated_at": source.get("updated_at"),
            "platform_binding": binding,
            "limitations": limitations + ["recorded_state_is_not_process_liveness"],
        }

    def list_runs(self, project_id: str) -> dict:
        try:
            paths = sorted(
                (
                    p
                    for p in self.root.iterdir()
                    if RUN_ID.fullmatch(p.name) and p.is_dir() and self._safe(p)
                ),
                key=lambda p: p.name,
            )
        except OSError:
            paths = []
        runs = [v for p in paths[:RUN_LIMIT] if (v := self._summary(p, project_id)) is not None]
        runs.sort(key=lambda r: r["source_updated_at"] or "", reverse=True)
        active = [r for r in runs if r["state"] and r["state"] not in TERMINAL_STATES]
        limitations = [
            "unbound_or_conflicting_runs_are_not_assigned_to_a_project",
            "current_run_requires_one_explicit_nonterminal_binding",
        ]
        if len(paths) > RUN_LIMIT:
            limitations.append("run_enumeration_limit_reached")
        return {
            "schema_version": "v4.1-workbench/v1",
            "project_id": project_id,
            "observed_at": now(),
            "current_run_id": active[0]["run_id"] if len(active) == 1 else None,
            "runs": runs,
            "completeness": {"complete": len(paths) <= RUN_LIMIT, "limit": RUN_LIMIT},
            "limitations": limitations,
        }

    def _paths(self, run: Path, pattern: str) -> list[Path]:
        # Patterns are implementation constants, never request data. glob does
        # not recursively traverse arbitrary run folders.
        return sorted(run.glob(pattern))[: ARTIFACT_LIMIT + 1]

    def _artifact(self, run: Path, path: Path, kind: str, binding: dict, projector) -> dict:
        value, source, issues = self._read(path)
        try:
            data = projector(value) if isinstance(value, (dict, list)) else {}
            scan_domain_payload(data)
        except SecretDetected:
            data = {}
            issues.append("source_contains_credentials")
        except (ValueError, TypeError, AttributeError, KeyError):
            data = {}
            issues.append("source_schema_invalid")
        return {
            "artifact_id": path.relative_to(run).as_posix(),
            "kind": kind,
            "availability": "available"
            if isinstance(value, (dict, list)) and not issues
            else "missing"
            if issues == ["missing_source"]
            else "error",
            "schema_version": value.get("schema_version") if isinstance(value, dict) else None,
            "version": (
                value.get(
                    "revision",
                    value.get(
                        "projection_digest", value.get("report_digest", source.get("sha256"))
                    ),
                )
            )
            if isinstance(value, dict)
            else None,
            "source": source,
            "observed_at": now(),
            "scope": {**binding, "run_id": run.name},
            "limitations": issues,
            "data": data,
        }

    def detail(self, project_id: str, run_id: str) -> dict:
        if not RUN_ID.fullmatch(run_id) or run_id in {".", ".."}:
            raise WorkbenchNotFound()
        run = self.root / run_id
        summary = self._summary(run, project_id)
        if summary is None:
            raise WorkbenchNotFound()
        binding = summary["platform_binding"]
        groups = {
            key: []
            for key in (
                "competency_questions",
                "scenario_map",
                "candidates",
                "materialization",
                "public_feedback",
                "reports",
                "host",
                "handoff",
            )
        }
        limitations = list(summary["limitations"])

        def add(group, pattern, projector, *, kind=None, fixed=False):
            paths = [run / pattern] if fixed else self._paths(run, pattern)
            if len(paths) > ARTIFACT_LIMIT:
                limitations.append(group + "_artifact_limit_reached")
            for p in paths[:ARTIFACT_LIMIT]:
                groups[group].append(self._artifact(run, p, kind or group, binding, projector))

        add(
            "competency_questions",
            "competency-questions/public/public-projection-*.json",
            lambda v: {
                **scalars(v, "schema_version batch_id projection_digest snapshot_digest"),
                "questions": [question(q) for q in v.get("questions", []) if isinstance(q, dict)],
            },
        )
        projections = [
            a["data"] for a in groups["competency_questions"] if a["availability"] == "available"
        ]
        freeze_events, _, _ = self._read(run / "evidence/cq-freeze.jsonl")
        current_freeze = (
            next(
                (
                    v
                    for v in reversed(freeze_events)
                    if isinstance(v, dict) and v.get("snapshot_digest")
                ),
                None,
            )
            if isinstance(freeze_events, list)
            else None
        )

        def public_binding(value):
            matches = [
                p
                for p in projections
                if value.get("freeze_digest")
                and p.get("snapshot_digest") == value["freeze_digest"]
                and (not value.get("batch_id") or p.get("batch_id") == value["batch_id"])
            ]
            # A reused ID from another frozen pool never releases its answer.
            if len(matches) != 1:
                return {}, False
            return {
                q["question_id"]: q for q in matches[0].get("questions", []) if q.get("question_id")
            }, True

        add("scenario_map", "scenario-map/scenario-map.json", scenario, fixed=True)
        add("candidates", "stage3-neutral-graph/candidates/*.json", candidate)
        add(
            "materialization",
            "stage3-neutral-graph/materialization-plans/*.json",
            materialization,
            kind="materialization_plan",
        )
        for path, kind in [
            ("value-semantics/submission-intents/intent-*.json", "submission_intent"),
            ("value-semantics/submission-receipts/receipt-*.json", "submission_receipt"),
            ("value-semantics/approvals/approvals.json", "approvals"),
            ("value-semantics/ledger/materialization-ledger.json", "materialization_ledger"),
        ]:
            add("materialization", path, materialization, kind=kind, fixed="*" not in path)
        add(
            "materialization",
            "evidence/staged-decisions.jsonl",
            self._attempt_proofs,
            kind="attempt_proofs",
            fixed=True,
        )
        add(
            "public_feedback",
            "early-feedback/*/feedback.json",
            lambda v: self._feedback(v, *public_binding(v)),
        )
        add(
            "reports",
            "acceptance-v3/reports/*/*/batch-report.json",
            lambda v: self._report(v, *public_binding(v), binding, current_freeze),
        )
        add(
            "reports",
            "acceptance-v3/public-regression/*/*/batch-report.json",
            lambda v: self._report(v, *public_binding(v), binding, current_freeze),
            kind="public_regression_report",
        )
        add("handoff", "acceptance-v3/production-handoff.json", self._handoff, fixed=True)
        add(
            "host",
            "baseline-manifest.json",
            self._configuration,
            kind="role_configuration",
            fixed=True,
        )
        for role in ("coordinator", "modeling", "protocol", "competency-question", "acceptance"):
            add(
                "host",
                f"runtime/{role}/home/config.toml",
                lambda v, role=role: {
                    "role": role,
                    **scalars(v, "model model_provider model_reasoning_effort service_tier"),
                    "verification": "observed_config_file",
                    "hot_switch_verified": False,
                },
                kind="actual_role_configuration",
                fixed=True,
            )
        add("host", "state.json", self._state, kind="run_lifecycle", fixed=True)
        for name in (
            "runtime-failure",
            "terminal-classification",
            "settled",
            "semantic-start",
            "cq-handoff-complete",
            "cq-acceptance-complete",
            "cq-freeze",
            "session-configure",
        ):
            add("host", f"evidence/{name}.jsonl", self._events, kind=name, fixed=True)
        launch = self.root / ".host-launches" / f"{run_id}.json"
        groups["host"].append(self._external_artifact(launch, binding, run_id))
        add(
            "host",
            "recovery/acceptance-continuation.json",
            self._continuation,
            kind="acceptance_continuation",
            fixed=True,
        )
        for group in groups:
            if not groups[group]:
                limitations.append(group + "_source_missing")
        limitations += [
            "authorization_balance_unknown_no_bound_balance_record",
            "classified_effective_time_not_recorded_in_a_structured_run_artifact",
            "summary_notes_not_reconstructed_from_private_logs",
        ]
        return {
            "schema_version": "v4.1-workbench-run/v1",
            "project_id": project_id,
            "observed_at": now(),
            **summary,
            "artifacts": groups,
            "limitations": limitations,
        }

    def competency_questions(self, project_id: str, run_id: str) -> dict:
        """Latest CQ baseline for administrators; never a production-role input."""
        detail = self.detail(project_id, run_id)
        run = self.root / run_id
        binding = detail["platform_binding"]
        host = detail["artifacts"]["host"]
        freezes = [
            record
            for artifact in host
            if artifact["kind"] == "cq-freeze" and artifact["availability"] == "available"
            for record in artifact["data"].get("records", [])
            if record.get("snapshot_digest")
        ]

        def frozen_questions(value):
            if value.get("schema_version") != "r3-0-011-cq-freeze/v1" or value.get(
                "snapshot_digest"
            ) != content_digest({k: v for k, v in value.items() if k != "snapshot_digest"}):
                raise ValueError("frozen_question_digest_mismatch")
            questions = value.get("questions")
            if not isinstance(questions, list) or any(
                not isinstance(q, dict) or not isinstance(q.get("question_id"), str)
                or not isinstance(q.get("question"), str)
                or q.get("visibility") not in {"public", "hidden"}
                for q in questions
            ) or len({q["question_id"] for q in questions}) != len(questions):
                raise ValueError("frozen_question_schema_invalid")
            return {
                **scalars(value, "batch_id snapshot_digest"),
                "questions": [
                    scalars(q, "question_id question visibility content_version")
                    for q in value["questions"]
                ],
            }

        paths = self._paths(run, "competency-questions/frozen/freeze-*.json")
        if len(paths) > ARTIFACT_LIMIT:
            return {**detail, "current_questions_available": False,
                    "artifacts": {"competency_questions": [], "reports": [], "host": []}}
        snapshots = [
            self._artifact(run, path, "competency_questions", binding, frozen_questions)
            for path in paths
        ]
        if freezes:
            freeze = freezes[-1]
            matches = [
                a for a in snapshots
                if a["data"].get("batch_id") == freeze.get("batch_id")
                and a["data"].get("snapshot_digest") == freeze["snapshot_digest"]
            ]
            chosen = matches[0] if len(matches) == 1 else None
        else:
            chosen = max(snapshots, key=lambda a: a["source"].get("updated_at", ""), default=None)
            latest = [
                a for a in snapshots if chosen and a["source"].get("updated_at")
                == chosen["source"].get("updated_at")
            ]
            if len(latest) != 1:
                chosen = None
        if not snapshots and not freezes:
            # Before a full freeze exists, show only the latest public record.
            return {
                **detail,
                "artifacts": {
                    "competency_questions": [{
                        **a, "data": {
                            **scalars(a["data"], "batch_id snapshot_digest"),
                            "questions": [{
                                **scalars(q, "question_id question content_version review_content_version"),
                                "visibility": "public",
                            } for q in a["data"].get("questions", [])],
                        },
                    } for a in detail["artifacts"]["competency_questions"]],
                    "reports": [], "host": [],
                },
            }
        groups = {"competency_questions": [], "reports": [], "host": []}
        if chosen is None or chosen["availability"] != "available":
            return {**detail, "current_questions_available": False, "artifacts": groups}
        groups["competency_questions"] = [chosen]
        current_freeze = scalars(chosen["data"], "batch_id snapshot_digest")
        groups["host"] = [{
            **chosen, "kind": "cq-freeze", "data": {"records": [current_freeze]},
        }]
        public_ids = {
            q["question_id"]: q for q in chosen["data"]["questions"]
            if q.get("visibility") == "public"
        }
        all_ids = {q["question_id"] for q in chosen["data"]["questions"]}

        def acceptance(value):
            if value.get("batch_id") != current_freeze["batch_id"] or value.get(
                "freeze_digest"
            ) != current_freeze["snapshot_digest"]:
                return {}
            result = self._report(value, public_ids, True, binding, current_freeze)
            # Per-question badges need verdicts, never hidden answers or notes.
            result["question_verdicts"] = [
                scalars(q, "question_id verdict") for q in value.get("verdicts", [])
                if isinstance(q, dict) and q.get("question_id") in all_ids
            ]
            result["question_ids"] = sorted((
                set(value.get("executed_question_ids", []))
                | set(value.get("unexecuted_question_ids", []))
                | {q["question_id"] for q in result["question_verdicts"]}
            ) & all_ids)
            return {k: result[k] for k in (
                "batch_id", "freeze_digest", "applicability", "denominator", "public_count",
                "verdicts", "unexecuted_question_ids", "hidden_summary", "question_verdicts",
                "question_ids",
            )} | {"verdicts": [scalars(q, "question_id verdict") for q in result["verdicts"]]}

        # Acceptance-only runs have no production state.json. Their formal
        # reports carry the project, ontology, freeze and before/after model
        # bindings needed by _report_applicability; do not infer these from IDs.
        paths = self._paths(self.root, "*/acceptance-v3/reports/*/*/batch-report.json")
        for path in paths[:ARTIFACT_LIMIT]:
            source_run = self.root / path.relative_to(self.root).parts[0]
            artifact = self._artifact(source_run, path, "reports", binding, acceptance)
            if source_run == run or (
                artifact["availability"] == "available"
                and artifact["data"].get("applicability") == "verified_current"
            ):
                artifact["artifact_id"] = source_run.name + "/" + artifact["artifact_id"]
                groups["reports"].append(artifact)
        return {**detail, "artifacts": groups,
                "acceptance_reports_complete": len(paths) <= ARTIFACT_LIMIT}

    @staticmethod
    def _feedback(value: dict, public_ids: dict, projection_bound: bool = True) -> dict:
        result = scalars(
            value,
            "run_id checkpoint_id freeze_id freeze_digest status purpose "
            "formal_acceptance review_status feedback_summary next_route model_drift",
        )
        result["public_questions"] = [
            question(q)
            for q in value.get("public_questions", [])
            if isinstance(q, dict) and q.get("question_id") in public_ids
        ]
        result["reports"] = [
            scalars(q, ANSWER_FIELDS)
            for q in value.get("reports", [])
            if isinstance(q, dict) and q.get("question_id") in public_ids
        ]
        result["first_failure"] = object_field(value, "first_failure", "stage code failure_layer")
        first_failure = value.get("first_failure")
        failure = first_failure.get("failure") if isinstance(first_failure, dict) else None
        if isinstance(failure, dict):
            projected = scalars(
                failure,
                "schema_version status code blocked_layer failure_layer blocked_reason role",
            )
            # Runtime evidence is a typed host diagnostic, not a raw log or a
            # semantic answer. Only machine codes and numerical observations
            # cross this public projection.
            projected["evidence"] = object_field(
                failure,
                "evidence",
                "reason_code binding_code code status blocked_layer failure_layer "
                "exit_code steps inherited_turns report_ref_count proxy_receipt_count",
            )
            reason = failure.get("reason")
            if projection_bound and isinstance(reason, str):
                projected["reason"] = reason
            elif isinstance(reason, str):
                # A checkpoint failure may precede any public freeze binding.
                # Keep its typed code while withholding unbound free text.
                code = reason.split(":", 1)[0]
                if re.fullmatch(r"[a-z][a-z0-9_.-]{0,79}", code):
                    projected["reason"] = code
                projected["reason_detail_visibility"] = "withheld_without_public_binding"
            result["first_failure"]["failure"] = projected
        result["pre_write_tail"] = object_field(
            value, "pre_write_tail", "digest intent_count receipt_count"
        )
        result["post_write_tail"] = object_field(
            value, "post_write_tail", "digest intent_count receipt_count"
        )
        result["public_projection_binding"] = "matched" if projection_bound else "unknown"
        return result

    def _report(
        self,
        value: dict,
        public_ids: dict,
        projection_bound: bool = True,
        scope_binding: dict | None = None,
        current_freeze: dict | None = None,
    ) -> dict:
        result = scalars(
            value,
            "schema_version run_id batch_id acceptance_mode blind_status freeze_digest "
            "model_binding_digest report_digest full_pass",
        )
        verdicts = [q for q in value.get("verdicts", []) if isinstance(q, dict)]
        result["verdicts"] = []
        for q in verdicts:
            if q.get("question_id") not in public_ids:
                continue
            item = scalars(q, VERDICT_FIELDS)
            item["approved_answer_points"] = public_ids[q["question_id"]].get("answer_points", [])
            item["structured_point_verdicts"] = "not_recorded"
            for field in ("answer_point_diagnostics", "point_diagnostics", "answer_points"):
                item[field] = records(q.get(field), POINT_FIELDS)
            result["verdicts"].append(item)
        result["examiner_reports"] = [
            scalars(q, ANSWER_FIELDS)
            for q in value.get("examiner_reports", [])
            if isinstance(q, dict)
            and q.get("question_id") in public_ids
            and q.get("question_content_version")
            == public_ids[q["question_id"]].get(
                "review_content_version", public_ids[q["question_id"]].get("content_version")
            )
        ]
        result["blind_status"] = object_field(
            value, "blind_status", "blind_status exposure_evidence_digest exposure_record_count"
        )
        exposed = (
            value.get("blind_status", {}).get("exposed_question_ids", [])
            if isinstance(value.get("blind_status"), dict)
            else []
        )
        result["blind_status"]["exposed_question_ids"] = [q for q in exposed if q in public_ids]
        result["public_projection_binding"] = "matched" if projection_bound else "unknown"
        executed = value.get("executed_question_ids", [])
        unexecuted = value.get("unexecuted_question_ids", [])
        result["executed_question_ids"] = [q for q in executed if q in public_ids]
        result["unexecuted_question_ids"] = [q for q in unexecuted if q in public_ids]
        result["denominator"] = len(
            set(executed)
            | set(unexecuted)
            | {q.get("question_id") for q in verdicts if isinstance(q.get("question_id"), str)}
        )
        result["public_count"] = len(
            {
                q
                for q in set(executed) | set(unexecuted) | {v.get("question_id") for v in verdicts}
                if q in public_ids
            }
        )
        result["hidden_summary"] = {
            "verdict_counts": dict(
                Counter(
                    q.get("verdict", "unknown")
                    for q in verdicts
                    if q.get("question_id") not in public_ids
                )
            ),
            "unexecuted_count": sum(q not in public_ids for q in unexecuted),
        }
        result["summary_by_scope"] = {
            key: scalars(
                v,
                "pass model-recall-insufficient question-answer-review "
                "platform-runtime-incomplete not-executed incomplete pending-review",
            )
            for key, v in value.get("summary_by_scope", {}).items()
            if key in {"panorama", "slice", "cross_slice"} and isinstance(v, dict)
        }
        result["coverage_gaps"] = object_field(
            value,
            "coverage_gaps",
            "cross_slice_projection_gap empty_hidden_set slices_without_hidden_question",
        )
        # Reports are historical records. Current model-state and freeze
        # verification cannot be inferred from a stored PASS or file mtime.
        applicability, issues = self._report_applicability(
            value, scope_binding, projection_bound, current_freeze
        )
        result["applicability"] = applicability
        result["applicability_limitations"] = issues
        result["report_digest_scope"] = report_digest_scope(value)
        result["full_pass_verification"] = "recorded_only_not_rescored"
        if result["report_digest_scope"] == "batch_report_core":
            result["applicability_limitations"].append(
                "sessions_and_full_pass_outside_report_digest"
            )
        if not projection_bound:
            result["applicability_limitations"].append("exact_public_freeze_projection_missing")
        return result

    def _report_applicability(
        self, value: dict, scope: dict | None, projection_bound: bool, current_freeze: dict | None
    ):
        if report_digest_scope(value) == "mismatch":
            return "stale", ["report_digest_mismatch"]
        if current_freeze is None:
            return "binding_unknown", ["current_frozen_pool_not_observed"]
        if current_freeze.get("snapshot_digest") != value.get(
            "freeze_digest"
        ) or current_freeze.get("batch_id") != value.get("batch_id"):
            return "stale", ["frozen_pool_superseded"]
        sessions = value.get("sessions", {})
        before = sessions.get("batch_model_binding") if isinstance(sessions, dict) else None
        after = sessions.get("post_batch_model_binding") if isinstance(sessions, dict) else None
        if (
            not projection_bound
            or not scope
            or not isinstance(before, dict)
            or not isinstance(after, dict)
        ):
            return "binding_unknown", ["report_model_or_freeze_binding_missing"]
        if value.get("model_binding_digest") != content_digest(before):
            return "stale", ["model_binding_digest_mismatch"]
        for record in (before, after):
            if record.get("freeze_digest") != value.get("freeze_digest") or record.get(
                "batch_id"
            ) != value.get("batch_id"):
                return "stale", ["model_binding_freeze_mismatch"]
            entries = record.get("ontologies")
            if (
                not isinstance(entries, list)
                or not entries
                or not {q.get("ontology_id") for q in entries if isinstance(q, dict)}
                <= set(scope["ontology_ids"])
            ):
                return "stale", ["report_scope_mismatch"]
            if any(
                not isinstance(q, dict) or q.get("project_id") != scope["project_id"]
                for q in entries
            ):
                return "stale", ["report_project_mismatch"]
        if before.get("ontologies") != after.get("ontologies"):
            return "stale", ["model_changed_during_report"]
        if self.workspace_reader is None:
            return "binding_unknown", ["live_model_binding_not_observed"]
        try:
            for entry in after["ontologies"]:
                context = self.workspace_reader(scope["project_id"], entry["ontology_id"])
                observed = workspace_digests(context)
                if observed != (entry.get("workspace_state"), entry.get("graph_state")):
                    return "stale", ["live_model_binding_changed"]
        except LookupError:
            return "stale", ["bound_online_resource_missing"]
        except (OSError, ValueError, RuntimeError, SQLAlchemyError):
            return "binding_unknown", ["live_model_binding_unavailable"]
        return "verified_current", []

    @staticmethod
    def _handoff(value: dict) -> dict:
        result = scalars(
            value,
            "schema_version run_id batch_id freeze_id freeze_digest ready "
            "write_phase pending_writes "
            "acceptance_attempt_id acceptance_target profile_id task_id",
        )
        result["scope_binding"] = object_field(value, "scope_binding", SCOPE_FIELDS)
        result["role_states"] = object_field(value, "role_states", "coordinator modeling protocol")
        result["applied_batches"] = records(
            value.get("applied_batches"), "intent_ordinal batch_id mode response_digest"
        )
        result["not_applied"] = records(value.get("not_applied"), "source kind ticket")
        result["unknown_writes"] = records(
            value.get("unknown_writes"), "source detail intent_ordinal idempotency_key kind ticket"
        )
        result["joint_checklist"] = object_field(
            value, "joint_checklist", "state note status digest artifact"
        )
        return result

    @staticmethod
    def _configuration(value: dict) -> dict:
        profile = value.get("team_model_profile", {})
        if not isinstance(profile, dict):
            return {}
        return {
            **scalars(profile, "profile_id schema_version sha256"),
            "roles": {
                role: scalars(
                    config, "model_provider model requested_effort effective_effort auth_mode"
                )
                for role, config in profile.get("roles", {}).items()
                if role
                in {
                    "coordinator",
                    "modeling",
                    "protocol",
                    "source-specialist",
                    "platform-examiner",
                    "acceptance",
                    "acceptance-judge",
                    "competency-question",
                }
            },
            "configuration_status": "frozen_run_configuration",
            "hot_switch_verified": False,
        }

    @staticmethod
    def _continuation(value: dict) -> dict:
        result = scalars(
            value,
            "schema_version source_run_id new_run_id batch_id attempt_id mode "
            "outcome report_published finished_at prep_seconds acceptance_seconds full_pass",
        )
        result["accounting"] = object_field(
            value,
            "accounting",
            "consumes_semantic_start semantic_starts_consumed timing_basis wall_seconds",
        )
        return result

    @staticmethod
    def _attempt_proofs(value: list) -> dict:
        return {
            "records": [
                scalars(
                    v,
                    "schema_version event intent_ordinal receipt_ordinal plan_ref "
                    "projection_digest batch_id attempt_id client_batch_id mode attempt_status "
                    "content_hash workspace_before_version response_digest recorded_at",
                )
                for v in value
                if isinstance(v, dict) and v.get("schema_version") == "r3-0-014-attempt-proof/v1"
            ]
        }

    @staticmethod
    def _state(value: dict) -> dict:
        cleanup = value.get("cleanup", {})
        cleanup = cleanup if isinstance(cleanup, dict) else {}
        result = scalars(value, "state run_id reason code failure_layer")
        result["scope"] = object_field(
            cleanup,
            "scope",
            "project_id ontology_id ontology_ids "
            "scope_disposition sessions_terminal owned mode "
            "protocol_key_revoked admin_key_revoked completed_session_id",
        )
        result["runtime"] = object_field(
            cleanup, "runtime", "processes_stopped locks_released stopped cleaned success"
        )
        result["acceptance"] = object_field(cleanup, "acceptance", "status started complete")
        result["terminal_results"] = {
            role: scalars(v, "status result outcome complete_modeling_quality_result")
            for role, v in (value.get("terminal_results") or {}).items()
            if role in {"coordinator", "modeling", "protocol", "acceptance"}
        }
        result["process_liveness"] = "unknown"
        return result

    @staticmethod
    def _events(value: list) -> dict:
        return {
            "records": records(
                value,
                "event recorded_at stage code reason_code failure_layer "
                "classification complete_modeling_quality_result acceptance_phase "
                "write_phase freeze_id freeze_digest handoff_digest report_digest "
                "acceptance_attempt_id batch_id configuration_status model "
                "requested_effort effective_effort service_tier snapshot_digest "
                "freeze_ref public_question_ids hidden_question_count",
            )
        }

    def _external_artifact(self, path: Path, binding: dict, run_id: str) -> dict:
        value, source, issues = self._read(path)
        return {
            "artifact_id": f"host-launch/{run_id}",
            "kind": "launch_configuration",
            "availability": "available"
            if isinstance(value, dict) and not issues
            else "missing"
            if issues == ["missing_source"]
            else "error",
            "schema_version": value.get("schema") if isinstance(value, dict) else None,
            "version": source.get("sha256"),
            "source": source,
            "observed_at": now(),
            "scope": {**binding, "run_id": run_id},
            "limitations": issues,
            "data": scalars(
                value,
                "run_id started_at finished_at service_tier service_tier_note "
                "model_profile mode exit_status status",
            ),
        }
