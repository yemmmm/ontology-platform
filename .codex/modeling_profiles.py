#!/usr/bin/env python3
"""Small, deterministic routing rules for R1.1-007 execution Profiles.

This module deliberately contains no ontology rules, quality thresholds, or platform protocol.
Those remain in ``skills/ontology-builder/references`` and the shared modeling directory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class ProfileContractError(ValueError):
    """Raised when a caller would silently select or mutate a Profile."""


@dataclass(frozen=True)
class ProfileSelection:
    execution_profile: str
    evaluation_profile: str | None
    reason: str


FORMAL_INTENT_FLAGS = {
    "formal_delivery",
    "full_chain_acceptance",
    "complete_platform_record",
    "strict_evaluation",
}


def select_profile(intent: dict[str, Any] | None = None) -> ProfileSelection:
    """Choose the execution envelope without conflating it with evaluation Profiles."""
    intent = intent or {}
    if not isinstance(intent, dict):
        raise ProfileContractError("profile intent must be an object")
    requested = intent.get("execution_profile")
    evaluation = intent.get("evaluation_profile")
    if requested not in {None, "local", "formal"}:
        raise ProfileContractError("execution_profile must be local or formal")
    if evaluation not in {None, "fast_local", "strict_eval"}:
        raise ProfileContractError("unknown evaluation_profile; choose explicitly")
    flags = {name for name in FORMAL_INTENT_FLAGS if intent.get(name) is True}
    if evaluation == "strict_eval":
        flags.add("strict_evaluation")
    implied = "formal" if flags else "local"
    if requested and requested != implied and flags:
        raise ProfileContractError(
            "explicit execution_profile conflicts with requested formal intent"
        )
    profile = requested or implied
    if evaluation == "strict_eval" and profile != "formal":
        raise ProfileContractError("strict_eval requires the formal execution_profile")
    reason = (
        "explicit formal delivery or strict evaluation intent"
        if profile == "formal"
        else "ordinary modeling defaults to local"
    )
    return ProfileSelection(profile, evaluation, reason)


def freeze_profile(run: dict[str, Any], selection: ProfileSelection) -> dict[str, Any]:
    """Return an immutable run-level Profile declaration, refusing in-place switches."""
    if not isinstance(run, dict):
        raise ProfileContractError("run must be an object")
    existing = run.get("execution_profile")
    if existing is not None and existing != selection.execution_profile:
        raise ProfileContractError("execution_profile is fixed; create a new run to switch")
    existing_evaluation = run.get("evaluation_profile")
    if existing_evaluation is not None and existing_evaluation != selection.evaluation_profile:
        raise ProfileContractError("evaluation_profile is fixed; create a new run to switch")
    result = dict(run)
    result.update(asdict(selection))
    return result


def main_handoff(
    *,
    run_path: str,
    phase: str,
    questions: list[str] | None = None,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """The only coordinator-facing Local handoff shape; it intentionally has no payload fields."""
    return {
        "run_path": run_path,
        "phase": phase,
        "questions": list(questions or []),
        "findings": list(findings or []),
    }


def worker_handoff(
    *,
    run_path: str,
    work_unit_id: str | None = None,
    ontology_id: str | None = None,
    schema_path: str | None = None,
    output_path: str | None = None,
    change: str | None = None,
) -> dict[str, str]:
    """Build a reference-only role handoff; business data stays in the shared directory."""
    result = {"run_path": run_path}
    for key, value in {
        "work_unit_id": work_unit_id,
        "ontology_id": ontology_id,
        "schema_path": schema_path,
        "output_path": output_path,
        "change": change,
    }.items():
        if value is not None:
            if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
                raise ProfileContractError(f"{key} must be a bounded non-empty string")
            result[key] = value
    return result
