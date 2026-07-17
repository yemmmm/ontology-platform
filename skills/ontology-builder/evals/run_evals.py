#!/usr/bin/env python3
"""Validate ontology-builder eval fixtures, traces, and MCP dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


EVALS_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVALS_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
REQUIRED_SCENARIOS = {
    "start-or-resume-and-clarify",
    "new-session-evidence-modeling",
    "apply-and-verify",
    "conflicting-evidence",
    "idempotent-timeout-recovery",
    "document-prompt-injection-and-cancel",
}
TOOL_REFERENCE = re.compile(r"`mcp:([a-z][a-z0-9_]*)`")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def declared_tools(cases: list[dict[str, Any]]) -> set[str]:
    return {tool for case in cases for tool in case.get("assertions", {}).get("required_tools", [])}


def documented_tools() -> set[str]:
    tools: set[str] = set()
    for path in [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]:
        tools.update(TOOL_REFERENCE.findall(path.read_text(encoding="utf-8")))
    return tools


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
