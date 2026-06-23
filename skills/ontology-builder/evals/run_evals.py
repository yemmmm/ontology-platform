#!/usr/bin/env python3
"""Validate eval fixtures and optionally score structured agent traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_SCENARIOS = {
    "conversation-only-intake",
    "conversation-with-document",
    "conflicting-documents",
    "idempotent-retry-and-resume",
    "document-prompt-injection",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids = {case.get("id") for case in cases}
    missing = REQUIRED_SCENARIOS - ids
    if missing:
        errors.append(f"missing scenarios: {', '.join(sorted(missing))}")
    for case in cases:
        case_id = case.get("id", "<missing-id>")
        assertions = case.get("assertions", {})
        for field in ("scenario", "input", "assertions"):
            if field not in case:
                errors.append(f"{case_id}: missing {field}")
        for field in ("required_actions", "forbidden_actions", "max_questions", "expected_stop_reason"):
            if field not in assertions:
                errors.append(f"{case_id}: missing assertion {field}")
        overlap = set(assertions.get("required_actions", [])) & set(assertions.get("forbidden_actions", []))
        if overlap:
            errors.append(f"{case_id}: actions both required and forbidden: {sorted(overlap)}")
    return errors


def score(cases: list[dict[str, Any]], traces: list[dict[str, Any]]) -> list[str]:
    by_id = {trace.get("id"): trace for trace in traces}
    errors: list[str] = []
    for case in cases:
        case_id = case["id"]
        trace = by_id.get(case_id)
        if trace is None:
            errors.append(f"{case_id}: missing trace")
            continue
        actions = set(trace.get("actions", []))
        expected = case["assertions"]
        missing = set(expected["required_actions"]) - actions
        forbidden = set(expected["forbidden_actions"]) & actions
        if missing:
            errors.append(f"{case_id}: missing actions {sorted(missing)}")
        if forbidden:
            errors.append(f"{case_id}: forbidden actions {sorted(forbidden)}")
        if len(trace.get("questions", [])) > expected["max_questions"]:
            errors.append(f"{case_id}: too many questions")
        if trace.get("stop_reason") != expected["expected_stop_reason"]:
            errors.append(f"{case_id}: unexpected stop reason {trace.get('stop_reason')!r}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--traces", type=Path)
    args = parser.parse_args()
    cases = load(args.cases)
    errors = validate_cases(cases)
    if args.traces:
        errors.extend(score(cases, load(args.traces)))
    if errors:
        raise SystemExit("\n".join(errors))
    suffix = " and traces" if args.traces else ""
    print(f"Validated {len(cases)} ontology-builder eval cases{suffix}.")


if __name__ == "__main__":
    main()
