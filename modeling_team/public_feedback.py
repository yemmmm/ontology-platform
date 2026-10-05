"""Read-only checkpoint and write-tail binding for early public feedback.

No production lifecycle or formal acceptance state is changed here. The host
uses the existing checkpoint and staged-write contracts, then observes live
platform state through the existing CQ read path.
"""
from __future__ import annotations

import json
from pathlib import Path

from .checkpoints import (
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, file_digest, manifest_digest,
    manifest_path, verify_checkpoint,
)
from .competency_questions import content_digest, public_projection, reload_frozen_pool
from .contracts import TeamConfigurationError
from .staged_decisions import (
    StagedDecisionArtifactError, applied_attempt_proof, read_submission_intents,
    read_submission_receipts, staged_decision_artifact_paths, staged_intent_receipt_issues,
)


def _unavailable(reason: str):
    raise TeamConfigurationError("public_feedback_unavailable: " + reason)


def observe_write_tail(run_root: Path) -> dict:
    """Observe durable intent/receipt state; never replay or reconcile a write."""
    try:
        issues = staged_intent_receipt_issues(run_root)
        intents = read_submission_intents(run_root)
        receipts = read_submission_receipts(run_root)
    except StagedDecisionArtifactError as exc:
        _unavailable("staged artifact unreadable; use the existing reconciliation path: " + str(exc))
    if issues:
        _unavailable("staged write reconciliation required: " + issues[0].reason_code)
    receipt_by_intent = {item.get("intent_ordinal"): item for item in receipts}
    if any(item.get("status") not in {"receipted", "rejected"} for item in intents):
        _unavailable("pending or unknown write; settle through the existing write path")
    if not any(applied_attempt_proof(run_root, intent=item,
                                     receipt=receipt_by_intent.get(item.get("ordinal")))
               is not None for item in intents):
        _unavailable("no confirmed applied write; dry-run alone is not a consumable chain")
    return {"digest": content_digest({"intents": intents, "receipts": receipts}),
            "intent_count": len(intents), "receipt_count": len(receipts)}


def load_feedback_checkpoint(run_root: Path, checkpoint_id: str, freeze_id: str,
                             question_ids: list[str]) -> dict:
    """Resolve only published, digest-verified checkpoint input and public IDs."""
    manifest, issues = verify_checkpoint(run_root, checkpoint_id)
    if issues:
        _unavailable("checkpoint package is incomplete or changed: " + "; ".join(issues))
    if manifest.get("kind") != CHECKPOINT_KIND_MATERIALIZATION_PROGRESS:
        _unavailable("a materialization_progress checkpoint is required")
    digest = manifest_digest(manifest_path(run_root, checkpoint_id))
    events_path = run_root / "evidence/checkpoints.jsonl"
    if not events_path.is_file():
        _unavailable("checkpoint publication receipt is missing")
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    published = [item for item in events if item.get("checkpoint_id") == checkpoint_id
                 and item.get("event") in {"checkpoint-saved", "checkpoint-reused"}]
    if not published or any(item.get("manifest_digest") != digest for item in published):
        _unavailable("checkpoint manifest digest does not match its publication receipt")
    parameters = manifest.get("configuration", {}).get("task_parameters", {})
    if parameters.get("modeling_checkpoints") is not True or parameters.get(
            "competency_question_acceptance") is not True:
        _unavailable("checkpoint/CQ selectors were not enabled; do not change the running Task")
    identities = manifest.get("platform_bindings", {})
    project_id = identities.get("project_id")
    ontology_ids = identities.get("ontology_ids")
    if (not isinstance(project_id, str) or not project_id or not isinstance(ontology_ids, list)
            or not ontology_ids or any(not isinstance(item, str) or not item for item in ontology_ids)
            or not isinstance(identities.get("run_scope"), dict)):
        _unavailable("checkpoint platform scope identity is not verified")
    positions = manifest.get("write_positions", {})
    if (positions.get("in_flight") or positions.get("unknown")
            or not positions.get("positions")
            or any(item.get("state") not in {"applied", "validated_not_applied", "rejected"}
                   for item in positions["positions"])):
        _unavailable("checkpoint write positions are not closed")
    if Path(freeze_id).name != freeze_id or freeze_id in {"", ".", ".."}:
        _unavailable("freeze_id must name one frozen artifact")
    source = f"competency-questions/frozen/{freeze_id}.json"
    artifacts = manifest.get("artifacts", [])
    staged_paths = staged_decision_artifact_paths(run_root)
    for name in ("intents_dir", "receipts_dir"):
        prefix = staged_paths[name].relative_to(run_root).as_posix() + "/"
        if not any(item.get("source", "").startswith(prefix) for item in artifacts):
            _unavailable("checkpoint has no captured " + name)
    matches = [item for item in artifacts if item.get("source") == source]
    if len(matches) != 1:
        _unavailable("frozen CQ artifact is not in this checkpoint")
    entry = matches[0]
    snapshot = run_root / "checkpoints" / checkpoint_id / entry["snapshot_path"]
    # The normal checkpoint validator verifies the per-side source path; check
    # the explicit snapshot path too before resolving any private host input.
    if (not snapshot.resolve().is_relative_to((run_root / "checkpoints" / checkpoint_id).resolve())
            or snapshot.is_symlink() or file_digest(snapshot) != entry["digest"]):
        _unavailable("frozen CQ snapshot path/digest is invalid")
    freeze = reload_frozen_pool(json.loads(snapshot.read_text()))
    current = run_root / source
    if not current.is_file() or current.is_symlink() or file_digest(current) != entry["digest"]:
        _unavailable("current frozen CQ differs from checkpoint; choose a current checkpoint")
    projection = public_projection(freeze)
    public_ids = {item["question_id"] for item in projection["questions"]}
    if not question_ids or len(set(question_ids)) != len(question_ids) or not set(question_ids) <= public_ids:
        _unavailable("question selection must contain unique approved frozen public IDs")
    # Preserve the explicit host selection order; never use private pool order
    # as an implicit selector or disclose hidden IDs in an error.
    by_id = {item["question_id"]: item for item in freeze["questions"]}
    selected = [by_id[question_id] for question_id in question_ids]
    return {"manifest": manifest, "manifest_digest": digest,
            "freeze": freeze, "freeze_file_digest": entry["digest"],
            "projection_digest": projection["projection_digest"], "questions": selected,
            "platform_bindings": identities, "write_tail": observe_write_tail(run_root)}
