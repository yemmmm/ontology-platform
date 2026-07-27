"""Tester-side positive semantic gates for M4 baseline and withheld variants.

These checks consume normalized observations from public semantic queries.  They deliberately do
not inspect response text or accept a missing baseline relation as proof of an alternative decision.
"""

from __future__ import annotations


class SemanticAuditError(ValueError):
    """An M4 observation does not prove the required positive semantic behavior."""


def _require_string(observation: dict[str, object], key: str) -> str:
    value = observation.get(key)
    if not isinstance(value, str) or not value:
        raise SemanticAuditError(f"missing positive {key}")
    return value


def assert_lifecycle_observation(variant: str, observation: dict[str, object]) -> None:
    """Require the current B target and its concrete contract in every alternative."""
    target = _require_string(observation, "current_c_target")
    contract = _require_string(observation, "current_target_contract")
    if variant == "baseline":
        if target != "C Latest Version" or contract != "quality_rating:number":
            raise SemanticAuditError("baseline must positively return C Latest Version and quality_rating")
    elif variant == "pinned-non-successor":
        if target != "C published Version 1" or contract != "quality_score:number":
            raise SemanticAuditError("pinned variant must positively return older C Version 1 and quality_score")
    else:
        raise SemanticAuditError("unknown variant")


def assert_output_identity_observation(variant: str, observation: dict[str, object]) -> None:
    """Reject a negative-only proof for the non-successor alternative."""
    if variant == "baseline":
        if observation.get("continuity") != "quality_score:number -> quality_rating:number":
            raise SemanticAuditError("baseline must positively return successor continuity")
        return
    if variant != "pinned-non-successor":
        raise SemanticAuditError("unknown variant")
    if observation.get("old_contract_status") != "quality_score:number removed":
        raise SemanticAuditError("non-successor must positively return old-contract removal")
    if observation.get("new_contract_status") != "quality_rating:number distinct addition":
        raise SemanticAuditError("non-successor must positively return distinct new-contract addition")
    if observation.get("discontinuity") != "continuity not confirmed":
        raise SemanticAuditError("non-successor must positively return discontinuity")


def assert_unknown_observation(observation: dict[str, object]) -> None:
    """Require the unanswered decision to stay explicit and non-invented."""
    if observation.get("missing_score_status") != "unknown":
        raise SemanticAuditError("missing-score handling must remain unknown")
    reason = _require_string(observation, "missing_score_reason")
    if "cannot confirm" not in reason.lower():
        raise SemanticAuditError("unknown result must retain the business reason")
    forbidden = {"fallback", "absence", "confirmed"}
    if any(key in observation for key in forbidden):
        raise SemanticAuditError("unknown branch contains an invented business fact")


def assert_variant_pair(
    baseline: dict[str, object], variant: dict[str, object], unknown: dict[str, object]
) -> None:
    """Run all positive baseline/variant and shared-unknown gates."""
    assert_lifecycle_observation("baseline", baseline)
    assert_lifecycle_observation("pinned-non-successor", variant)
    assert_output_identity_observation("baseline", baseline)
    assert_output_identity_observation("pinned-non-successor", variant)
    assert_unknown_observation(unknown)
