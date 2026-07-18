#!/usr/bin/env python3
"""Validate ontology-builder eval fixtures, traces, and MCP dependencies."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError as PydanticValidationError


EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
MODEL_HANDOFF_SCHEMA = SKILL_DIR / "references" / "modeler-handoff.schema.json"
REQUIRED_SCENARIOS = {
    "recover-artifacts-events-and-question-heads",
    "global-scan-pack-matrix-and-confirmation",
    "modeler-vertical-slice-and-dry-run",
    "independent-review-finds-organizer-omission",
    "seven-gates-apply-and-verify",
    "secret-idempotency-timeout-and-role-fallback",
    "prompt-injection-cancel-with-history",
}
TOOL_REFERENCE = re.compile(r"`mcp:([a-z][a-z0-9_]*)`")
ROUND_1_INVALID_QUALITY_ISSUES = {
    "round-1-category-omission",
    "round-1-category-evidence-gap",
    "round-1-role",
    "round-1-severity",
    "round-1-extra-fields",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def declared_tools(cases: list[dict[str, Any]]) -> set[str]:
    return {tool for case in cases for tool in case.get("assertions", {}).get("required_tools", [])}


def documented_tools() -> set[str]:
    tools: set[str] = set()
    for path in [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]:
        tools.update(TOOL_REFERENCE.findall(path.read_text(encoding="utf-8")))
    return tools


def quality_issue_model():
    backend = str(REPO_ROOT / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.api.schemas import ModelingQualityIssue

    return ModelingQualityIssue


def modeling_handler():
    backend = str(REPO_ROOT / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.core.config import Settings
    from app.services.modeling_handlers import ModelingCommandHandlerRegistry

    settings = Settings(
        semantic_base_iri="https://ontology-builder-eval.test/semantic/",
        semantic_graph_iri_prefix="https://ontology-builder-eval.test/graph/",
    )
    return ModelingCommandHandlerRegistry(settings)


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case id")
    missing = REQUIRED_SCENARIOS - set(ids)
    if missing:
        errors.append(f"missing scenarios: {', '.join(sorted(missing))}")
    for case in cases:
        case_id = case.get("id", "<missing-id>")
        assertions = case.get("assertions", {})
        for field in ("scenario", "input", "assertions"):
            if field not in case:
                errors.append(f"{case_id}: missing {field}")
        for field in (
            "required_tools",
            "required_actions",
            "forbidden_actions",
            "max_questions",
            "expected_stop_reason",
        ):
            if field not in assertions:
                errors.append(f"{case_id}: missing assertion {field}")
        required_actions = set(assertions.get("required_actions", []))
        forbidden_actions = set(assertions.get("forbidden_actions", []))
        overlap = required_actions & forbidden_actions
        if overlap:
            errors.append(f"{case_id}: actions both required and forbidden: {sorted(overlap)}")
        tools = assertions.get("required_tools", [])
        if len(tools) != len(set(tools)):
            errors.append(f"{case_id}: duplicate required tool")
    declared = declared_tools(cases)
    mentioned = documented_tools()
    if mentioned - declared:
        errors.append(
            f"documented MCP tools missing from eval contract: {sorted(mentioned - declared)}"
        )
    if declared - mentioned:
        errors.append(
            f"eval MCP dependencies not documented by the Skill: {sorted(declared - mentioned)}"
        )
    return errors


def score(cases: list[dict[str, Any]], traces: list[dict[str, Any]]) -> list[str]:
    by_id = {trace.get("id"): trace for trace in traces}
    allowed_tools = declared_tools(cases)
    errors: list[str] = []
    for case in cases:
        case_id = case["id"]
        trace = by_id.get(case_id)
        if trace is None:
            errors.append(f"{case_id}: missing trace")
            continue
        tools = set(trace.get("tools", []))
        actions = set(trace.get("actions", []))
        expected = case["assertions"]
        missing_tools = set(expected["required_tools"]) - tools
        undeclared_tools = tools - allowed_tools
        missing_actions = set(expected["required_actions"]) - actions
        forbidden_actions = set(expected["forbidden_actions"]) & actions
        if missing_tools:
            errors.append(f"{case_id}: missing tools {sorted(missing_tools)}")
        if undeclared_tools:
            errors.append(f"{case_id}: undeclared tools {sorted(undeclared_tools)}")
        if missing_actions:
            errors.append(f"{case_id}: missing actions {sorted(missing_actions)}")
        if forbidden_actions:
            errors.append(f"{case_id}: forbidden actions {sorted(forbidden_actions)}")
        if len(trace.get("questions", [])) > expected["max_questions"]:
            errors.append(f"{case_id}: too many questions")
        if trace.get("stop_reason") != expected["expected_stop_reason"]:
            errors.append(f"{case_id}: unexpected stop reason {trace.get('stop_reason')!r}")
        if case_id == "independent-review-finds-organizer-omission":
            errors.extend(validate_reviewer_handoff(trace))
        if case_id == "modeler-vertical-slice-and-dry-run":
            errors.extend(validate_modeler_handoff(trace))
    return errors


def validate_modeler_handoff(trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    handoff = trace.get("modeler_handoff")
    if not isinstance(handoff, dict):
        return ["modeler-vertical-slice-and-dry-run: missing modeler_handoff"]
    schema = load(MODEL_HANDOFF_SCHEMA)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"modeler handoff schema is invalid: {exc.message}"]
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(handoff), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"modeler_handoff {location} is invalid: {error.message}")

    invalid_handoffs = {
        "lease-token": copy.deepcopy(handoff),
        "payload-actor": copy.deepcopy(handoff),
        "command-payload-mismatch": copy.deepcopy(handoff),
        "empty-batch": copy.deepcopy(handoff),
        "active-operation-without-binding": copy.deepcopy(handoff),
        "nullable-parameter-constraints": copy.deepcopy(handoff),
    }
    invalid_handoffs["lease-token"]["modeling_batch"]["lease_token"] = "forbidden"
    first_item = invalid_handoffs["payload-actor"]["modeling_batch"]["items"][0]
    first_item["payload"]["actor"] = "forbidden"
    mismatch = invalid_handoffs["command-payload-mismatch"]["modeling_batch"]["items"][0]
    mismatch["command_kind"] = "create_operation"
    invalid_handoffs["empty-batch"]["modeling_batch"]["items"] = []
    active_operation = next(
        item
        for item in invalid_handoffs["active-operation-without-binding"]["modeling_batch"]["items"]
        if item["command_kind"] == "create_operation"
    )
    active_operation["payload"]["tool_bindings"] = []
    nullable_constraints = next(
        item
        for item in invalid_handoffs["nullable-parameter-constraints"]["modeling_batch"]["items"]
        if item["command_kind"] == "create_operation"
    )
    nullable_constraints["payload"]["parameters"][0]["constraints"] = {
        "min_value": None,
        "max_value": None,
        "min_length": None,
        "max_length": None,
        "pattern": None,
        "format": None,
    }
    for fixture_id, invalid_handoff in invalid_handoffs.items():
        if validator.is_valid(invalid_handoff):
            errors.append(f"modeler_handoff invalid fixture was accepted: {fixture_id}")

    operation_items = [
        item
        for item in handoff["modeling_batch"]["items"]
        if item["command_kind"] == "create_operation"
    ]
    if len(operation_items) != 1 or not operation_items[0]["payload"]["parameters"]:
        errors.append("modeler_handoff must contain one operation with a nonempty parameter list")
        return errors
    operation_payload = operation_items[0]["payload"]
    original_payload = copy.deepcopy(operation_payload)
    try:
        modeling_handler().prepare(
            batch_id=handoff["modeling_batch"]["client_batch_id"],
            ontology_id=handoff["modeling_batch"]["ontology_id"],
            client_item_id=operation_items[0]["client_item_id"],
            command_kind="create_operation",
            payload=operation_payload,
        )
    except Exception as exc:
        errors.append(
            "modeler_handoff schema-valid operation failed platform prepare: "
            f"{type(exc).__name__}: {exc}"
        )
    if operation_payload != original_payload:
        errors.append("modeler_handoff platform prepare mutated the operation input payload")
    return errors


def validate_reviewer_handoff(trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    handoff = trace.get("reviewer_handoff")
    if not isinstance(handoff, dict):
        return ["independent-review-finds-organizer-omission: missing reviewer_handoff"]
    model = quality_issue_model()
    for index, issue in enumerate(handoff.get("quality_issues", [])):
        try:
            normalized = model.model_validate(issue).model_dump(mode="json")
        except PydanticValidationError as exc:
            errors.append(f"reviewer_handoff quality issue {index} is invalid: {exc}")
            continue
        if normalized != issue:
            errors.append(f"reviewer_handoff quality issue {index} is not normalized record-ready")

    rejected = trace.get("rejected_reviewer_quality_issues", [])
    rejected_ids = {item.get("id") for item in rejected}
    if rejected_ids != ROUND_1_INVALID_QUALITY_ISSUES:
        errors.append(
            "reviewer_handoff rejected fixtures differ: "
            f"missing={sorted(ROUND_1_INVALID_QUALITY_ISSUES - rejected_ids)}, "
            f"unknown={sorted(rejected_ids - ROUND_1_INVALID_QUALITY_ISSUES)}"
        )
    for item in rejected:
        try:
            model.model_validate(item.get("issue"))
        except PydanticValidationError:
            continue
        errors.append(f"reviewer_handoff invalid fixture was accepted: {item.get('id')}")
    return errors


def registry_tool_names() -> set[str]:
    backend = str(REPO_ROOT / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.api.mcp_catalog import _enumerate_tools

    return {tool["name"] for tool in _enumerate_tools()}


def check_registry(cases: list[dict[str, Any]], traces: list[dict[str, Any]] | None) -> list[str]:
    registry = registry_tool_names()
    errors: list[str] = []
    missing = declared_tools(cases) - registry
    if missing:
        errors.append(f"required tools missing from runtime registry: {sorted(missing)}")
    if traces is not None:
        used = {tool for trace in traces for tool in trace.get("tools", [])}
        unregistered = used - registry
        if unregistered:
            errors.append(f"trace tools missing from runtime registry: {sorted(unregistered)}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=EVALS_DIR / "cases.json")
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--check-registry", action="store_true")
    args = parser.parse_args()
    cases = load(args.cases)
    traces = load(args.traces) if args.traces else None
    errors = validate_cases(cases)
    if traces is not None:
        errors.extend(score(cases, traces))
    if args.check_registry:
        errors.extend(check_registry(cases, traces))
    if errors:
        raise SystemExit("\n".join(errors))
    suffix = " and traces" if traces is not None else ""
    registry = " against the runtime registry" if args.check_registry else ""
    print(f"Validated {len(cases)} ontology-builder eval cases{suffix}{registry}.")


if __name__ == "__main__":
    main()
