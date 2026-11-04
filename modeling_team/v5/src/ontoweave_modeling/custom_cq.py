"""Fixed project CQ goals use existing material revisions and independent evaluation."""

import json
from pathlib import Path

from .contracts import FrameworkError, digest, validate_schema, write_json
from .revisions import SourceRevisions

MATERIAL_ID = "cq-goals"


def public_goal_questions(materials, manifest):
    """Read approved public seed goals or verified project snapshots without changing either."""
    questions = {}
    for entry in manifest.values():
        if entry.get("material_type") != "competency_goal":
            continue
        try:
            value = json.loads((Path(materials) / entry["path"]).read_text())
            if (
                isinstance(value, dict)
                and value.get("schema_version") == "ontoweave-cq-snapshot/v1"
            ):
                rows = validate_snapshot(value)["questions"]
            else:
                validate_schema(
                    value,
                    {
                        "type": "object",
                        "required": ["schema_version", "seed_id", "revision", "questions"],
                        "properties": {
                            "schema_version": {
                                "enum": [
                                    "ontoweave-custom-cq-seed/v1",
                                    "ontoweave-custom-cq-seed/design-v1",
                                ]
                            },
                            "seed_id": {"type": "string", "minLength": 1},
                            "revision": {"type": "integer", "minimum": 1},
                            "visibility": {"const": "public"},
                            "criteria_status": {"const": "draft"},
                            "questions": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "required": ["external_id", "question"],
                                    "properties": {
                                        "external_id": {"type": "string", "minLength": 1},
                                        "question": {"type": "string", "minLength": 1},
                                        "reference_answer": {"type": ["string", "null"]},
                                    },
                                },
                            },
                        },
                    },
                )
                rows = [
                    {
                        "cq_id": row["external_id"],
                        "question": row["question"],
                        # An import seed is a draft goal, never confirmation authority.
                        "cq_definition": {
                            "criteria_status": "draft",
                            "reference_answer": row.get("reference_answer"),
                        },
                    }
                    for row in value["questions"]
                ]
            if len({q["cq_id"] for q in rows}) != len(rows):
                raise FrameworkError("public_cq_identity_or_disposition_invalid")
            for question in rows:
                identity = question["cq_id"]
                if identity in questions and questions[identity] != question:
                    raise FrameworkError(
                        "public_cq_identity_or_disposition_invalid", cq_id=identity
                    )
                questions[identity] = question
        except (ValueError, KeyError, TypeError) as error:
            raise FrameworkError(
                "public_cq_seed_invalid",
                path=entry["path"],
                cause=error.as_dict() if isinstance(error, FrameworkError) else str(error),
                instruction="Supply a public draft ontoweave-custom-cq-seed/v1 (or design-v1), "
                "or an intact ontoweave-cq-snapshot/v1 from the project CQ snapshot entry. "
                "Keep stable question IDs; seed answers do not confirm business facts.",
            ) from error
    return questions


def validate_snapshot(snapshot):
    content = {
        key: value for key, value in snapshot.items() if key not in {"sha256", "snapshot_id"}
    }
    if (
        snapshot.get("schema_version") != "ontoweave-cq-snapshot/v1"
        or digest(content) != snapshot.get("sha256")
        or snapshot.get("snapshot_id") != "cq-" + snapshot["sha256"][:24]
    ):
        raise FrameworkError("cq_snapshot_digest_mismatch")
    seen = set()
    for question in snapshot["questions"]:
        row = {key: value for key, value in question.items() if key != "content_digest"}
        if digest(row) != question["content_digest"]:
            raise FrameworkError("cq_snapshot_digest_mismatch")
        if question["cq_id"] in seen or question.get("visibility") != "public":
            raise FrameworkError("cq_snapshot_scope_invalid")
        seen.add(question["cq_id"])
    return snapshot


def freeze_cases(snapshot, source_manifest):
    validate_snapshot(snapshot)
    questions = []
    for index, row in enumerate(snapshot["questions"], 1):
        bindings, missing = {}, []
        for reference in row["cq_definition"].get("source_refs", []):
            found = [
                key
                for key, value in source_manifest.items()
                if key != MATERIAL_ID
                and (
                    key == reference
                    or value.get("path") == reference
                    or value.get("source_ref") == reference
                )
            ]
            if len(found) == 1:
                bindings[found[0]] = source_manifest[found[0]]["sha256"]
            else:
                missing.append(reference)
        questions.append(
            {
                **row,
                "index": index,
                "source_bindings": bindings,
                "unresolved_source_refs": missing,
                "criteria_ready": bool(row["criteria_ready"] and bindings and not missing),
            }
        )
    return {
        "schema_version": "ontoweave-custom-cq-freeze/v1",
        "snapshot_id": snapshot["snapshot_id"],
        "questions": questions,
    }


def validate_cases(report, questions):
    if sorted(case["index"] for case in report["cases"]) != list(range(1, len(questions) + 1)):
        raise FrameworkError("evaluation_case_coverage_mismatch")
    public = []
    for case in sorted(report["cases"], key=lambda case: case["index"]):
        frozen = questions[case["index"] - 1]
        keys = ("cq_id", "content_revision", "content_digest")
        if any(case.get(key) != frozen[key] for key in keys):
            raise FrameworkError("cq_case_binding_mismatch", index=case["index"])
        outcome = case.get("outcome")
        if not frozen["criteria_ready"] and outcome not in {
            "question-answer-review",
            "platform-runtime-incomplete",
        }:
            raise FrameworkError("cq_unready_criteria_cannot_pass", index=case["index"])
        if case.get("sql_execution") not in {"not_run", "blocked"}:
            raise FrameworkError("cq_sql_execution_not_available", index=case["index"])
        if outcome not in {
            "pass",
            "model-recall-insufficient",
            "question-answer-review",
            "platform-runtime-incomplete",
        } or case["passed"] != (outcome == "pass"):
            raise FrameworkError("cq_outcome_inconsistent", index=case["index"])
        supported = {"supported", "conditional", "unsupported", "unverified"}
        if case.get("answerability") not in supported or case.get("sql_readiness") not in supported:
            raise FrameworkError("cq_readiness_required", index=case["index"])
        dimensions = frozen["cq_definition"].get(
            "validation_dimensions", ["model_answerability", "sql_readiness"]
        )
        if case["passed"] and (
            case["answerability"] != "supported"
            or ("sql_readiness" in dimensions and case["sql_readiness"] != "supported")
        ):
            raise FrameworkError("cq_capability_not_satisfied", index=case["index"])
        public.append(
            {
                key: case[key]
                for key in (
                    "index",
                    *keys,
                    "outcome",
                    "answerability",
                    "sql_readiness",
                    "sql_execution",
                )
            }
        )
    expected = (
        "REVISE"
        if any(case["outcome"] == "model-recall-insufficient" for case in public)
        else "PARTIAL"
        if any(case["outcome"] != "pass" for case in public)
        else "PASS"
    )
    if report["verdict"] != expected:
        raise FrameworkError("evaluation_verdict_inconsistent")
    return public


class CustomCQ:
    def __init__(self, binding, repository):
        self.binding, self.repository = binding, repository

    def sync(self, bridge):
        snapshot = bridge.call("cq_snapshot")
        if snapshot is None:
            return None
        return self.stage(snapshot)

    def stage(self, snapshot):
        validate_snapshot(snapshot)
        current = self.binding.data["source_manifest"].get(MATERIAL_ID)
        if current:
            previous = json.loads((self.binding.materials / current["path"]).read_text())
            if previous["sha256"] == snapshot["sha256"]:
                return None
        elif not snapshot["questions"]:
            return None
        destination = self.binding.root / "cq-inputs" / snapshot["snapshot_id"]
        manifest = {
            key: value
            for key, value in self.binding.data["source_manifest"].items()
            if key != MATERIAL_ID
        }
        for entry in manifest.values():
            path = destination / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.binding.materials / entry["path"]).read_bytes())
        path = destination / "custom-cq-goals.json"
        write_json(path, snapshot)
        import hashlib

        manifest[MATERIAL_ID] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_ref": snapshot["snapshot_id"],
            "material_type": "competency_goal",
        }
        write_json(destination / "manifest.json", manifest)
        return SourceRevisions(self.binding, self.repository).stage(
            {
                "change_id": snapshot["snapshot_id"],
                "reason": "Project CQ goals changed. Questions are goals, not confirmed business facts. "
                "Read their fixed revision, use approved sources, retain unknowns and pending "
                "criteria, and record cross-unit coverage without duplicating questions.",
            },
            destination,
        )

    def evaluation_package(self, snapshot, destination: Path):
        """Create an additive CQ batch, retaining the primary frozen standard and reports."""
        import hashlib

        frozen = freeze_cases(snapshot, self.binding.data["source_manifest"])
        if not frozen["questions"]:
            raise FrameworkError("cq_selection_empty")
        manifest = dict(self.binding.data["source_manifest"])
        for entry in manifest.values():
            path = destination / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.binding.materials / entry["path"]).read_bytes())
        path = destination / "frozen-custom-questions.json"
        write_json(path, frozen)
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["frozen-questions"] = {
            "path": path.name,
            "source_ref": snapshot["snapshot_id"],
            "sha256": sha256,
        }
        write_json(destination / "manifest.json", manifest)
        return {
            "freeze_id": "cq-freeze-" + sha256[:24],
            "sha256": sha256,
            "case_count": len(frozen["questions"]),
            "custom_cq": frozen["questions"],
            "cq_snapshot_id": snapshot["snapshot_id"],
        }
