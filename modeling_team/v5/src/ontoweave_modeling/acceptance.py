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
                },
                "required": ["index", "passed", "actual_answer", "reason", "evidence_iris"],
            },
        },
    },
    "required": ["verdict", "freeze_id", "model_revisions", "cases"],
}


def successful_reads(events_path: Path) -> list[tuple[str, dict, dict]]:
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


def require_governed_read(events_path: Path, model_revisions: dict) -> None:
    for tool, _, data in successful_reads(events_path):
        # The scoped MCP adapter returns the successful REST body without an `ok` envelope.
        if tool != "query_semantic_context" or data.get("ok") is False:
            continue
        actual = {
            row["ontology_id"]: row["model_revision"]
            for row in data.get("scope", {}).get("ontologies", [])
        }
        if actual == model_revisions:
            return
    raise FrameworkError("actual_governed_read_missing")


def validate_report(report: dict, handoff: dict, events_path: Path) -> dict:
    validate_schema(report, REPORT_SCHEMA)
    frozen, target = handoff["evaluation"], handoff["target"]
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
        args.get("material_id"): data
        for tool, args, data in successful_reads(events_path)
        if tool == "read_material" and "text" in data
    }
    if material_reads.get("frozen-questions", {}).get("sha256") != frozen["sha256"]:
        raise FrameworkError("evaluation_frozen_source_not_read")
    for material_id, sha256 in handoff["source_revisions"].items():
        if material_reads.get(material_id, {}).get("sha256") != sha256:
            raise FrameworkError("evaluation_original_source_not_read", material_id=material_id)
    require_governed_read(events_path, target["model_revisions"])
    return {
        "verdict": report["verdict"],
        "freeze_id": frozen["freeze_id"],
        "model_revisions": report["model_revisions"],
        "passed": sum(c["passed"] for c in report["cases"]),
        "total": frozen["case_count"],
    }
