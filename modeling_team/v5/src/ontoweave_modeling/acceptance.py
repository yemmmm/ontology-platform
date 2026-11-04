"""Frozen target and report contracts; semantic verdicts belong to the independent reader."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import FrameworkError, validate_schema

REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["PASS", "REVISE", "PARTIAL"]},
        "freeze_id": {"type": "string"},
        "model_revisions": {"type": "object", "additionalProperties": {"type": "integer"}},
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "passed": {"type": "boolean"},
                    "actual_answer": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence_iris": {"type": "array", "items": {"type": "string"}},
                    "cq_id": {"type": "string"},
                    "content_revision": {"type": "integer", "minimum": 1},
                    "content_digest": {"type": "string"},
                    "outcome": {
                        "enum": [
                            "pass",
                            "model-recall-insufficient",
                            "question-answer-review",
                            "platform-runtime-incomplete",
                        ]
                    },
                    "answerability": {
                        "enum": ["supported", "conditional", "unsupported", "unverified"]
                    },
                    "sql_readiness": {
                        "enum": ["supported", "conditional", "unsupported", "unverified"]
                    },
                    "sql_execution": {"enum": ["pass", "fail", "not_run", "blocked"]},
                },
                "required": ["index", "passed", "actual_answer", "reason", "evidence_iris"],
            },
        },
    },
    "required": ["verdict", "freeze_id", "model_revisions", "cases"],
}


def report_schema(evaluation: dict) -> dict:
    schema = json.loads(json.dumps(REPORT_SCHEMA))
    if "custom_cq" not in evaluation:
        case = schema["properties"]["cases"]["items"]
        case["properties"] = {key: case["properties"][key] for key in case["required"]}
    return schema


def independent_target(target: dict, *, whole_model: bool = False) -> dict:
    """Keep the frozen read scope; an evaluator does not use mutation-receipt references."""
    view = {
        key: value
        for key, value in target.items()
        if key not in {"resource_refs", "resource_bindings"}
    }
    if not whole_model and "resource_bindings" in target:
        execution_fields = {
            "resource_id",
            "item_id",
            "change_id",
            "receipt_item_path",
            "existing_resource_ref",
        }
        view["resource_bindings"] = {
            key: {field: value for field, value in binding.items() if field not in execution_fields}
            for key, binding in target["resource_bindings"].items()
        }
    return view


def successful_reads(events_path: Path | list[Path]) -> list[tuple[str, dict, dict]]:
    if isinstance(events_path, list):
        return [read for path in dict.fromkeys(events_path) for read in successful_reads(path)]
    reads = []
    for line in events_path.read_text().splitlines():
        event = json.loads(line)
        item = event.get("params", {}).get("item", {})
        if (
            event["method"] != "item/completed"
            or item.get("status") != "completed"
            or item.get("error")
        ):
            continue
        result = item.get("result") or {}
        if result.get("isError"):
            continue
        data = result.get("structuredContent")
        if data is None:
            for block in result.get("content", []):
                if block.get("type") == "text":
                    try:
                        data = json.loads(block["text"])
                    except (ValueError, KeyError):
                        continue
        if isinstance(data, dict) and not data.get("isError"):
            reads.append((item.get("tool"), item.get("arguments", {}), data))
    return reads


def read_coverage(
    events_path: Path | list[Path],
    materials: dict[str, str],
    target: dict,
    *,
    model_read_scope: str = "referenced_resources",
    evidence_iris: list[str] | tuple[str, ...] = (),
) -> dict:
    """Account for returned ranges/bodies, never comprehension or semantic correctness."""
    if model_read_scope not in {"referenced_resources", "whole_model"}:
        raise FrameworkError("model_read_scope_invalid")
    reads = [read for read in successful_reads(events_path) if read[2].get("ok") is not False]
    material_gaps = []
    for material_id, sha256 in materials.items():
        pages = [
            data
            for tool, args, data in reads
            if tool == "read_material"
            and args.get("material_id") == material_id
            and data.get("sha256") == sha256
        ]
        total = next(
            (p["total_characters"] for p in pages if isinstance(p.get("total_characters"), int)),
            None,
        )
        ranges = sorted(
            (p["offset"], p["offset"] + len(p["text"]))
            for p in pages
            if isinstance(p.get("offset"), int) and isinstance(p.get("text"), str)
        )
        missing, position = [], 0
        if total is None:
            missing = [[0, None]]
        else:
            for start, end in ranges:
                if position >= total:
                    break
                if start > position:
                    missing.append([position, min(start, total)])
                position = max(position, min(end, total))
            if position < total:
                missing.append([position, total])
        if missing:
            material_gaps.append(
                {
                    "material_id": material_id,
                    "sha256": sha256,
                    "total_characters": total,
                    "missing_ranges": missing,
                }
            )

    revisions = target["model_revisions"]
    bodies, inventories, relations = set(), {}, set()
    for tool, args, data in reads:
        if tool == "read_model_resource":
            oid = args["ontology_id"]
            if data.get("model_revision") != revisions.get(oid):
                continue
            family = args.get("family")
            items = data.get("items", [])
            if family != "resource-relations":
                bodies.update(
                    (oid, item["iri"])
                    for item in items
                    if item.get("iri") and "detail_fields" in item
                )
            complete = data.get("paging", {}).get("complete") is True
            if complete and family == "resource-relations":
                relations.add(oid)
            if complete and family == "resource-list" and not args.get("resource_iri"):
                inventories[oid] = {(oid, item["iri"]) for item in items if item.get("iri")}
        elif tool == "query_semantic_context":
            observed = {
                r["ontology_id"]: r["model_revision"]
                for r in data.get("scope", {}).get("ontologies", [])
            }
            for item in data.get("primary_matches", []) + data.get("related_context", []):
                oid, fields = item.get("ontology_id"), item.get("data", {})
                if oid not in revisions or observed.get(oid) != revisions[oid]:
                    continue
                if "semantic_definition" in fields or "mapping_definition" in fields:
                    bodies.add((oid, item["iri"]))
                if fields.get("predicate", "").endswith("/vocab/semanticDefinition"):
                    bodies.add((oid, fields["subject"]))

    required = {
        (b["ontology_id"], b["resource_iri"])
        for b in target.get("resource_bindings", {}).values()
        if b.get("resource_iri") in evidence_iris
    }
    whole_model = model_read_scope == "whole_model"
    if whole_model:
        required.update(resource for inventory in inventories.values() for resource in inventory)
    model_gaps = []
    for oid in revisions:
        unread = sorted(iri for ontology, iri in required - bodies if ontology == oid)
        missing_inventory = whole_model and oid not in inventories
        missing_relations = whole_model and oid not in relations
        if unread or missing_inventory or missing_relations:
            model_gaps.append(
                {
                    "ontology_id": oid,
                    "unread_resources": unread,
                    "missing_inventory": missing_inventory,
                    "missing_relations": missing_relations,
                }
            )
    return {
        "complete": not material_gaps and not model_gaps,
        "materials": material_gaps,
        "models": model_gaps,
        "model_read_scope": model_read_scope,
        "returned_resource_bodies": len(bodies),
        "required_resources": len(required),
    }


def coverage_summary(coverage: dict) -> dict:
    return {
        "complete": coverage["complete"],
        "model_read_scope": coverage["model_read_scope"],
        "unread_materials": len(coverage["materials"]),
        "unread_resources": sum(len(g["unread_resources"]) for g in coverage["models"]),
        "incomplete_model_scopes": len(coverage["models"]),
    }


def require_governed_read(events_path: Path | list[Path], model_revisions: dict) -> None:
    observed = {}
    for tool, arguments, data in successful_reads(events_path):
        # The scoped MCP adapter returns the successful REST body without an `ok` envelope.
        if data.get("ok") is False:
            continue
        if tool == "query_semantic_context":
            observed.update(
                {
                    row["ontology_id"]: row["model_revision"]
                    for row in data.get("scope", {}).get("ontologies", [])
                }
            )
        elif tool == "read_model_resource" and "model_revision" in data:
            observed[arguments["ontology_id"]] = data["model_revision"]
        if observed == model_revisions:
            return
    raise FrameworkError("actual_governed_read_missing")


def validate_report(
    report: dict,
    handoff: dict,
    events_path: Path | list[Path],
    *,
    required_materials: dict[str, str] | None = None,
) -> dict:
    frozen, target = handoff["evaluation"], handoff["target"]
    validate_schema(report, report_schema(frozen))
    if (
        report["freeze_id"] != frozen["freeze_id"]
        or report["model_revisions"] != target["model_revisions"]
    ):
        raise FrameworkError("evaluation_binding_mismatch")
    if sorted(case["index"] for case in report["cases"]) != list(
        range(1, frozen["case_count"] + 1)
    ):
        raise FrameworkError("evaluation_case_coverage_mismatch")
    if report["verdict"] == "PASS" and not all(case["passed"] for case in report["cases"]):
        raise FrameworkError("evaluation_verdict_inconsistent")
    material_reads = {
        (args.get("material_id"), data.get("sha256"))
        for tool, args, data in successful_reads(events_path)
        if tool == "read_material" and "text" in data
    }
    if ("frozen-questions", frozen["sha256"]) not in material_reads:
        raise FrameworkError("evaluation_frozen_source_not_read")
    for material_id, sha256 in handoff["source_revisions"].items():
        if (material_id, sha256) not in material_reads:
            raise FrameworkError("evaluation_original_source_not_read", material_id=material_id)
    for material_id, sha256 in (required_materials or {}).items():
        if (material_id, sha256) not in material_reads:
            raise FrameworkError("evaluation_human_source_not_read", material_id=material_id)
    require_governed_read(events_path, target["model_revisions"])
    coverage = read_coverage(
        events_path,
        {
            "frozen-questions": frozen["sha256"],
            **handoff["source_revisions"],
            **(required_materials or {}),
        },
        target,
        model_read_scope=frozen.get("model_read_scope", "referenced_resources"),
        evidence_iris=[iri for case in report["cases"] for iri in case["evidence_iris"]],
    )
    if report["verdict"] == "PASS" and not coverage["complete"]:
        raise FrameworkError("evaluation_read_coverage_incomplete", coverage=coverage)
    public = {
        "verdict": report["verdict"],
        "freeze_id": frozen["freeze_id"],
        "model_revisions": report["model_revisions"],
        "passed": sum(c["passed"] for c in report["cases"]),
        "total": frozen["case_count"],
        "read_coverage": coverage_summary(coverage),
    }
    if "custom_cq" in frozen:
        from .custom_cq import validate_cases

        public["custom_cq"] = validate_cases(report, frozen["custom_cq"])
        public["cq_snapshot_id"] = frozen["cq_snapshot_id"]
    return public
