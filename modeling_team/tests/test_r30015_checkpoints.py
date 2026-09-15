"""R3.0-015 segment S1 tests (shared test plan M01-M09, M23, M41/M42
serialized-read parts, M44 S1 side, M47 listing part).

Runner-tier fixtures reuse the prepared R3.0-011 profile harness with the
frozen R3.0-015 Task.  ``CapturingAdapter`` is a controlled Runtime stand-in,
not a real model provider: no Agent process, no LLM call and no platform write
happens anywhere in this file.  Module-tier cases build plain temporary run
roots.  Hidden-material markers below stay inside temporary test run roots and
never enter formal modeling materials.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from types import SimpleNamespace

import pytest
import yaml

import modeling_team.runner as runner_module
from modeling_team import checkpoints as ck
from modeling_team.checkpoints import (
    CHECKPOINT_ARTIFACTS_DIRECTORY,
    CHECKPOINT_DELIVERY_SEGMENTS,
    CHECKPOINT_DIRECTORY,
    CHECKPOINT_HOST_PRIVATE_DIRECTORY,
    CHECKPOINT_KIND_CQ_FROZEN,
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CHECKPOINT_KIND_SCENARIO_MAPPED,
    CHECKPOINT_KIND_SEMANTIC_APPROVED,
    CHECKPOINT_KINDS,
    CheckpointArtifactSpec,
    CheckpointError,
    StagePackage,
    file_digest,
    inspect_checkpoints,
    list_checkpoints,
    manifest_digest,
    production_resume_bindings,
    public_role_projection,
    safe_checkpoint_id,
    save_checkpoint,
    scope_retention_reference,
)
from modeling_team.competency_questions import CQ_FREEZE_SCHEMA
from modeling_team.contracts import (
    TeamConfigurationError,
    load_task,
    repository_root,
)
from modeling_team.interventions import RecoverableOuterInputError
from modeling_team.platform_scope import PlatformScope
from modeling_team.runner import CQWriteAdmission, TeamRunner
from modeling_team.staged_decisions import (
    StagedSubmissionRejection,
    build_submission_intent,
    build_submission_receipt,
    mark_intent_status,
    staged_decision_artifact_paths,
    write_submission_intent,
    write_submission_receipt,
)
from modeling_team.tests.test_platform_scope import ScopeClient
from modeling_team.tests.test_r3011_runner_wiring import _question, _read_evidence
from modeling_team.tests.test_runner import CapturingAdapter

REPO_ROOT = repository_root()
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-011-competency-question.yaml"
TASK_015 = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-015-checkpoint-recovery.yaml"
TASK_008B = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-008b-staged-real.yaml"
RUNS_ROOT = REPO_ROOT / "workspaces" / "modeling-runs"
CONFIGURATION = {"task_id": "r3-0-015-checkpoint-recovery", "profile_id": "r3-0-011"}


# --- module-tier helpers -------------------------------------------------------


def _write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


#: The platform identity a package saved by a scope-bound run carries since
#: the R3.0-015 binding fix; missing-bindings cases pass ``{}`` explicitly.
_BOUND_BINDINGS = {"project_id": "project-1", "ontology_ids": ["ontology-1"]}


def _package(
    kind: str = CHECKPOINT_KIND_CQ_FROZEN,
    *,
    sources: list[tuple[str, str]] | None = None,
    stage_facts: dict | None = None,
    scope_refs: dict | None = None,
    write_positions: dict | None = None,
    host_private: set[str] | None = None,
    platform_bindings: dict | None = None,
) -> StagePackage:
    private = host_private or set()
    artifacts = [
        CheckpointArtifactSpec(
            source=source,
            owner=owner,
            visible_to=(
                ("host", "competency-question")
                if source in private
                else ("coordinator", "modeling", "protocol")
            ),
            host_private=source in private,
        )
        for source, owner in (sources or [("evidence/stage.json", "coordinator")])
    ]
    return StagePackage(
        kind=kind,
        scope_refs=scope_refs or {"freeze_id": "f1"},
        artifacts=artifacts,
        stage_facts=stage_facts or {},
        platform_bindings=_BOUND_BINDINGS if platform_bindings is None else platform_bindings,
        write_positions=write_positions or {},
    )


def _seed_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "run"
    _write_json(run_root / "evidence" / "stage.json", {"stage": "fixture"})
    return run_root


def _save_ok(run_root: Path, package: StagePackage, **kwargs) -> dict:
    kwargs.setdefault("source_run_id", "r3015-unit")
    kwargs.setdefault("configuration", dict(CONFIGURATION))
    return save_checkpoint(run_root, package, **kwargs)


def _read_manifest(run_root: Path, checkpoint_id: str) -> dict:
    return json.loads(
        (run_root / CHECKPOINT_DIRECTORY / checkpoint_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )


def _tree_state(run_root: Path) -> dict:
    return {
        str(path.relative_to(run_root)): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(run_root.rglob("*"))
        if path.is_file()
    }


# --- module tier: schema, digest, layout (design §3.2) -------------------------


def test_manifest_carries_the_six_groups_and_never_embeds_its_own_hash(tmp_path):
    run_root = _seed_run(tmp_path)
    result = _save_ok(run_root, _package(), request_id="req-1")
    manifest = _read_manifest(run_root, result["checkpoint_id"])
    assert set(manifest) == {
        "schema_version",
        "checkpoint_id",
        "source_run_id",
        "root_run_id",
        "created_at",
        "kind",
        "scope_refs",
        "configuration",
        "artifacts",
        "stage_facts",
        "platform_bindings",
        "write_positions",
        "request_id",
    }
    assert manifest["schema_version"] == "r3-0-015-checkpoint/v1"
    assert manifest["request_id"] == "req-1"
    # The manifest never embeds its own hash: the digest is recomputed at read
    # time so a later segment (S2 origin.json) can bind to exact bytes.
    assert "manifest_digest" not in manifest
    assert not any("manifest" in key for key in manifest)
    path = run_root / CHECKPOINT_DIRECTORY / result["checkpoint_id"] / "manifest.json"
    assert result["manifest_digest"] == manifest_digest(path)
    assert result["manifest_digest"].startswith("sha256:")
    artifact = manifest["artifacts"][0]
    assert artifact["source"] == "evidence/stage.json"
    assert artifact["snapshot_path"] == f"{CHECKPOINT_ARTIFACTS_DIRECTORY}/evidence/stage.json"
    assert artifact["digest"] == file_digest(run_root / "evidence" / "stage.json")


def test_save_without_request_id_omits_the_field(tmp_path):
    run_root = _seed_run(tmp_path)
    result = _save_ok(run_root, _package())
    assert "request_id" not in _read_manifest(run_root, result["checkpoint_id"])


def test_invalid_kind_is_a_typed_rejection(tmp_path):
    run_root = _seed_run(tmp_path)
    with pytest.raises(CheckpointError) as error:
        _save_ok(run_root, _package(kind="not-a-kind"))
    assert error.value.reason_code == "checkpoint_invalid_kind"
    assert error.value.retryable is False
    assert error.value.data()["next_action"] == f"use one of {list(CHECKPOINT_KINDS)}"


# --- module tier: M05 half-packages, tampering, source change -------------------


def test_m05_interrupted_write_leaves_no_package_and_keeps_old_ones_usable(
    tmp_path, monkeypatch
):
    run_root = _seed_run(tmp_path)
    first = _save_ok(run_root, _package())

    def broken_copy(source, destination, expected_digest):
        raise OSError("disk full during checkpoint copy")

    monkeypatch.setattr(ck, "_copy_artifact", broken_copy)
    with pytest.raises(CheckpointError) as error:
        _save_ok(run_root, _package(stage_facts={"stage": "second"}))
    assert error.value.reason_code == "checkpoint_write_failed"

    # Only the first package (plus nothing half-written) remains; the failed
    # save never terminated anything and the old package stays readable.
    ids = [entry["checkpoint_id"] for entry in list_checkpoints(run_root)]
    assert ids == [first["checkpoint_id"]]
    leftovers = [
        entry.name
        for entry in (run_root / CHECKPOINT_DIRECTORY).iterdir()
        if entry.name != first["checkpoint_id"]
    ]
    assert leftovers == []
    assert inspect_checkpoints(run_root, first["checkpoint_id"])["checkpoint"]["status"] in {
        "ready",
        "needs_reconciliation",
    }


def test_m05_package_without_manifest_is_never_listed(tmp_path):
    run_root = _seed_run(tmp_path)
    first = _save_ok(run_root, _package())
    orphan = run_root / CHECKPOINT_DIRECTORY / "cq_frozen-9999" / CHECKPOINT_ARTIFACTS_DIRECTORY
    orphan.mkdir(parents=True)
    (orphan / "stage.json").write_text("{}", encoding="utf-8")
    listing = list_checkpoints(run_root)
    assert [entry["checkpoint_id"] for entry in listing] == [first["checkpoint_id"]]
    assert inspect_checkpoints(run_root)["published_count"] == 1


def test_m05_tampered_artifact_is_incompatible_and_drops_retention(tmp_path):
    run_root = _seed_run(tmp_path)
    first = _save_ok(run_root, _package())
    tampered = (
        run_root
        / CHECKPOINT_DIRECTORY
        / first["checkpoint_id"]
        / CHECKPOINT_ARTIFACTS_DIRECTORY
        / "evidence"
        / "stage.json"
    )
    tampered.write_text('{"stage": "tampered"}', encoding="utf-8")
    inspection = inspect_checkpoints(run_root, first["checkpoint_id"])
    assert inspection["checkpoint"]["status"] == "incompatible"
    assert any("digest mismatch" in issue for issue in inspection["checkpoint"]["issues"])
    # A non-verifying package is not a retention reference (test plan M23).
    assert scope_retention_reference(run_root) is None
    # The listing itself survives the corrupt sibling (M08).
    assert list_checkpoints(run_root)[0]["checkpoint_id"] == first["checkpoint_id"]


def test_m05_source_changed_during_copy_is_refused(tmp_path, monkeypatch):
    run_root = _seed_run(tmp_path)
    _save_ok(run_root, _package())

    def drifting_copy(source, destination, expected_digest):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("different bytes than the pre-copy digest", encoding="utf-8")

    monkeypatch.setattr(ck, "_copy_artifact", drifting_copy)
    with pytest.raises(CheckpointError) as error:
        _save_ok(run_root, _package(stage_facts={"stage": "second"}))
    assert error.value.reason_code == "artifact_changed"
    assert error.value.retry == "retry this save once the source files are stable"


# --- module tier: M06 dedup -----------------------------------------------------


def test_m06_same_content_reuses_the_package_under_new_request_ids(tmp_path):
    run_root = _seed_run(tmp_path)
    first = _save_ok(
        run_root,
        _package(),
        request_id="req-1",
        now=lambda: datetime(2026, 9, 14, 8, 0, tzinfo=UTC),
    )
    manifest_before = (
        run_root / CHECKPOINT_DIRECTORY / first["checkpoint_id"] / "manifest.json"
    ).read_bytes()

    second = _save_ok(
        run_root,
        _package(),
        request_id="req-2",
        now=lambda: datetime(2026, 9, 14, 9, 30, tzinfo=UTC),
    )
    assert second["status"] == "reused"
    assert second["checkpoint_id"] == first["checkpoint_id"]
    # Dedup never rewrites the existing package: request ids, timestamps and
    # checkpoint-save events cannot mint new packages or alter old bytes.
    assert (
        run_root / CHECKPOINT_DIRECTORY / first["checkpoint_id"] / "manifest.json"
    ).read_bytes() == manifest_before
    assert inspect_checkpoints(run_root)["published_count"] == 1


def test_m06_changed_content_saves_a_new_package_without_overwriting(tmp_path):
    run_root = _seed_run(tmp_path)
    _write_json(run_root / "evidence" / "stage.json", {"stage": "first"})
    first = _save_ok(run_root, _package(), request_id="req-1")
    _write_json(run_root / "evidence" / "stage.json", {"stage": "second"})
    second = _save_ok(run_root, _package(), request_id="req-2")
    assert second["status"] == "saved"
    assert second["checkpoint_id"] != first["checkpoint_id"]
    manifests = {item["checkpoint_id"] for item in list_checkpoints(run_root)}
    assert manifests == {first["checkpoint_id"], second["checkpoint_id"]}
    assert (
        _read_manifest(run_root, first["checkpoint_id"])["artifacts"][0]["digest"]
        != _read_manifest(run_root, second["checkpoint_id"])["artifacts"][0]["digest"]
    )


def test_m06_save_events_themselves_do_not_change_the_signature(tmp_path):
    run_root = _seed_run(tmp_path)
    base = _package(stage_facts={"stage": "cq_frozen", "events": ["checkpoint-save-failed"]})
    first = _save_ok(run_root, base, request_id="req-1")
    # A save event (or its absence) in stage facts is part of the content only
    # through the excluded event fields; identical stage decisions dedup.
    again = _save_ok(run_root, base, request_id="req-9")
    assert again["status"] == "reused"
    assert again["checkpoint_id"] == first["checkpoint_id"]


# --- module tier: M08 inspect listing and typed rejections ----------------------


def test_m08_inspect_without_id_lists_every_package_and_reports_sizes(tmp_path):
    run_root = _seed_run(tmp_path)
    _write_json(run_root / "evidence" / "stage.json", {"stage": "first"})
    _save_ok(run_root, _package(), request_id="req-1")
    _write_json(run_root / "evidence" / "stage.json", {"stage": "second"})
    _save_ok(run_root, _package(), request_id="req-2")

    result = inspect_checkpoints(run_root)
    assert result["published_count"] == 2
    assert result["consumes_semantic_start"] is False
    sizes = [entry["size_bytes"] for entry in result["checkpoints"]]
    assert all(size > 0 for size in sizes)
    assert result["cumulative_size_bytes"] == sum(sizes)
    actual = sum(
        path.stat().st_size
        for path in (run_root / CHECKPOINT_DIRECTORY).rglob("*")
        if path.is_file()
    )
    assert result["cumulative_size_bytes"] == actual


def test_m08_inspect_is_strictly_read_only(tmp_path):
    run_root = _seed_run(tmp_path)
    _save_ok(run_root, _package())
    before = _tree_state(run_root)
    inspect_checkpoints(run_root)
    listing = inspect_checkpoints(run_root)
    inspect_checkpoints(run_root, listing["checkpoints"][0]["checkpoint_id"])
    assert _tree_state(run_root) == before


def test_m08_nonexistent_corrupt_and_escaping_ids_are_typed_rejections(tmp_path):
    run_root = _seed_run(tmp_path)
    saved = _save_ok(run_root, _package())

    with pytest.raises(CheckpointError) as missing:
        inspect_checkpoints(run_root, "cq_frozen-9999")
    assert missing.value.reason_code == "checkpoint_not_found"
    assert missing.value.retryable is False

    manifest = run_root / CHECKPOINT_DIRECTORY / saved["checkpoint_id"] / "manifest.json"
    manifest.write_text("{not json", encoding="utf-8")
    with pytest.raises(CheckpointError) as corrupt:
        inspect_checkpoints(run_root, saved["checkpoint_id"])
    assert corrupt.value.reason_code == "checkpoint_manifest_unparsable"
    # A corrupt sibling never silently substitutes another package: the
    # listing reports it as unusable and the count still matches the disk.
    listing = list_checkpoints(run_root)
    assert listing[0]["status"] == "unparsable"

    for bad_id in ("../evil", "UPPER", "a/b", "", "x", "-leading"):
        with pytest.raises(CheckpointError) as escaping:
            inspect_checkpoints(run_root, bad_id)
        assert escaping.value.reason_code == "checkpoint_invalid_id"


def test_m08_safe_checkpoint_id_rejects_before_any_filesystem_join(tmp_path):
    with pytest.raises(CheckpointError):
        safe_checkpoint_id("../escape")
    assert safe_checkpoint_id("cq_frozen-0001") == "cq_frozen-0001"


def test_m08_inspection_statuses_ready_needs_reconciliation_incompatible(tmp_path):
    run_root = _seed_run(tmp_path)
    ready = _save_ok(run_root, _package())
    inspection = inspect_checkpoints(run_root, ready["checkpoint_id"])
    assert inspection["checkpoint"]["status"] == "ready"
    assert inspection["checkpoint"]["remaining_work"] == {"pending": [], "next_step": None}
    assert inspection["checkpoint"]["compatibility"]["compatible"] is True
    assert inspection["checkpoint"]["reusable_artifacts"][0]["source"] == "evidence/stage.json"

    pending = _save_ok(
        run_root,
        _package(
            scope_refs={"freeze_id": "f2"},
            stage_facts={"stage": "cq_frozen", "pending": ["topology_decision"]},
        ),
        request_id="req-pending",
    )
    inspection = inspect_checkpoints(run_root, pending["checkpoint_id"])
    assert inspection["checkpoint"]["status"] == "needs_reconciliation"
    assert inspection["checkpoint"]["remaining_work"]["pending"] == ["topology_decision"]
    assert inspection["checkpoint"]["write_reconciliation"]["unreconciled"] == []

    handoff = _save_ok(
        run_root,
        _package(
            kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            scope_refs={"freeze_id": "f3"},
        ),
    )
    estimated = inspect_checkpoints(run_root, handoff["checkpoint_id"])["checkpoint"][
        "estimated_authorization_consumption"
    ]
    assert estimated == {
        "acceptance_only_semantic_starts": 0,
        "note": "acceptance-only continuation consumes no semantic start",
    }
    other = inspect_checkpoints(run_root, ready["checkpoint_id"])["checkpoint"][
        "estimated_authorization_consumption"
    ]
    assert other["production_resume_semantic_starts"] == 1


def test_m08_missing_configuration_identity_is_incompatible(tmp_path):
    run_root = _seed_run(tmp_path)
    saved = save_checkpoint(
        run_root, _package(), source_run_id="r3015-unit", configuration={}
    )
    inspection = inspect_checkpoints(run_root, saved["checkpoint_id"])
    assert inspection["checkpoint"]["status"] == "incompatible"
    assert any("profile_id" in issue for issue in inspection["checkpoint"]["issues"])


def test_m08_missing_platform_bindings_is_not_production_resumable(tmp_path):
    """The auth017 failure: inspect must not call a bindingless package ready."""

    run_root = _seed_run(tmp_path)
    saved = _save_ok(run_root, _package(platform_bindings={}))
    inspection = inspect_checkpoints(run_root, saved["checkpoint_id"])["checkpoint"]
    assert inspection["production_resume"] == {
        "available": False,
        "reason": "the manifest records no Project/Ontology platform bindings "
        "to reattach",
    }
    assert inspection["status"] == "incompatible"
    assert any(
        "platform_bindings" in issue and "production resume" in issue
        for issue in inspection["issues"]
    )


def test_m08_inspection_reports_the_resume_identity_for_a_bound_checkpoint(tmp_path):
    run_root = _seed_run(tmp_path)
    saved = _save_ok(
        run_root,
        _package(
            platform_bindings={
                "project_id": "proj-x",
                "ontology_ids": ["onto-x", "onto-y"],
            }
        ),
    )
    inspection = inspect_checkpoints(run_root, saved["checkpoint_id"])["checkpoint"]
    assert inspection["production_resume"] == {
        "available": True,
        "project_id": "proj-x",
        "ontology_ids": ["onto-x", "onto-y"],
    }
    assert inspection["status"] == "ready"


def test_m08_production_handoff_inspection_points_at_acceptance_continuation(tmp_path):
    run_root = _seed_run(tmp_path)
    saved = _save_ok(
        run_root,
        _package(
            kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            platform_bindings={"project_id": "proj-x", "ontology_ids": ["onto-x"]},
        ),
    )
    inspection = inspect_checkpoints(run_root, saved["checkpoint_id"])["checkpoint"]
    assert inspection["production_resume"]["available"] is False
    assert "--mode acceptance" in inspection["production_resume"]["reason"]


def test_legacy_bindingless_manifest_resolves_to_no_reattachable_identity():
    """The exact auth017 manifest shape: run_scope mode only, no identity."""

    manifest = {
        "platform_bindings": {
            "run_scope": {"mode": "create"},
            "model_profile_digest": "sha256:" + "0" * 64,
        }
    }
    assert production_resume_bindings(manifest) is None


# --- module tier: M09 source boundaries and host-private projection -------------


@pytest.mark.parametrize(
    "source",
    [
        "secrets/old-key.json",
        "control/outer-input.fifo",
        f"{CHECKPOINT_DIRECTORY}/cq_frozen-0001/manifest.json",
        "recovery/origin.json",
    ],
)
def test_m09_deny_listed_sources_are_never_packageable(tmp_path, source):
    run_root = tmp_path / "run"
    path = run_root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(CheckpointError) as error:
        _save_ok(run_root, _package(sources=[(source, "host")]))
    assert error.value.reason_code == "checkpoint_invalid_source"
    assert error.value.retryable is False


def test_m09_hidden_interview_stays_out_of_every_production_projection(tmp_path):
    run_root = _seed_run(tmp_path)
    _write_json(
        run_root / "competency-questions" / "private" / "interview-0001.json",
        {"question_id": "cq-1", "note": "hidden-material-marker: host-only stand-in"},
    )
    saved = _save_ok(
        run_root,
        _package(
            sources=[
                ("evidence/stage.json", "coordinator"),
                ("competency-questions/private/interview-0001.json", "competency-question"),
            ],
            host_private={"competency-questions/private/interview-0001.json"},
        ),
    )
    manifest = _read_manifest(run_root, saved["checkpoint_id"])
    interview = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["source"].endswith("interview-0001.json")
    )
    assert interview["host_private"] is True
    assert interview["visible_to"] == ["host", "competency-question"]
    assert interview["snapshot_path"].startswith(f"{CHECKPOINT_HOST_PRIVATE_DIRECTORY}/")
    packaged = (
        run_root
        / CHECKPOINT_DIRECTORY
        / saved["checkpoint_id"]
        / CHECKPOINT_HOST_PRIVATE_DIRECTORY
        / "competency-questions"
        / "private"
        / "interview-0001.json"
    )
    assert packaged.is_file()

    for role in ("coordinator", "modeling", "protocol"):
        projection = public_role_projection(manifest, role)
        sources = [item["source"] for item in projection["visible_artifacts"]]
        assert "evidence/stage.json" in sources
        assert all(not source.endswith("interview-0001.json") for source in sources)


# --- module tier: M44 delivery boundary, M47 listing ----------------------------


def test_m44_delivery_segments_report_the_s2_boundary(tmp_path):
    run_root = _seed_run(tmp_path)
    _save_ok(run_root, _package())
    result = inspect_checkpoints(run_root)
    assert result["delivery_segments"] == dict(CHECKPOINT_DELIVERY_SEGMENTS)
    assert result["delivery_segments"]["s1_save_inspect"] == "delivered"
    assert result["delivery_segments"]["s2_production_resume"] == "delivered"
    assert (
        result["delivery_segments"]["s3_translation_approval_migration"]
        == "deferred_by_design"
    )
    assert result["delivery_segments"]["s4_acceptance_continuation"] == "delivered"
    assert result["resume"]["available"] is True
    assert result["resume"]["modes"]["production"]["delivered"] is True
    assert result["resume"]["modes"]["production"]["semantic_starts"] == 1
    assert result["resume"]["modes"]["acceptance"]["delivered"] is True
    assert result["resume"]["modes"]["acceptance"]["semantic_starts"] == 0
    assert result["resume"]["modes"]["acceptance"]["entry"].endswith("--mode acceptance")
    assert "never doubles as a launch credential" in result["resume"]["note"]


def test_m47_listing_reports_counts_and_sizes_for_manual_cleanup(tmp_path):
    run_root = _seed_run(tmp_path)
    _write_json(run_root / "evidence" / "stage.json", {"stage": "first"})
    _save_ok(run_root, _package())
    _write_json(run_root / "evidence" / "stage.json", {"stage": "second"})
    _save_ok(run_root, _package())
    # A half package (temp directory) exists but is excluded from the listing.
    temp = run_root / CHECKPOINT_DIRECTORY / ".cq_frozen-0003.tmp-1-ab"
    temp.mkdir(parents=True)
    result = inspect_checkpoints(run_root)
    assert result["published_count"] == 2
    assert len(result["checkpoints"]) == 2
    for entry in result["checkpoints"]:
        assert entry["manifest_digest"].startswith("sha256:")
    # Nothing in the module deletes packages: cleanup stays a host decision.
    assert _tree_state(run_root)


# --- module tier: cross bindings and retention ----------------------------------


def test_cross_bindings_must_match_the_packaged_digests(tmp_path):
    run_root = _seed_run(tmp_path)
    with pytest.raises(CheckpointError) as unpackaged:
        _save_ok(
            run_root,
            _package(
                stage_facts={
                    "bindings": [{"artifact": "evidence/missing.json", "digest": "sha256:0"}]
                }
            ),
        )
    assert unpackaged.value.reason_code == "checkpoint_binding_invalid"
    with pytest.raises(CheckpointError) as mismatched:
        _save_ok(
            run_root,
            _package(
                stage_facts={
                    "bindings": [
                        {"artifact": "evidence/stage.json", "digest": "sha256:" + "0" * 64}
                    ]
                }
            ),
        )
    assert mismatched.value.reason_code == "artifact_changed"


def test_scope_retention_reference_counts_only_verifying_packages(tmp_path):
    empty_root = tmp_path / "empty-run"
    empty_root.mkdir()
    assert scope_retention_reference(empty_root) is None

    run_root = _seed_run(tmp_path)
    saved = _save_ok(run_root, _package())
    reference = scope_retention_reference(run_root)
    assert reference == {
        "reason": "published-valid-checkpoint-reference",
        "checkpoint_ids": [saved["checkpoint_id"]],
        "count": 1,
    }
    (run_root / "evidence" / "stage.json").write_text('{"changed": true}', encoding="utf-8")
    # The run-side source changing later does not matter; only the packaged
    # bytes and manifest digests are verified at read time.
    assert scope_retention_reference(run_root)["count"] == 1


# --- contracts tier --------------------------------------------------------------


def _task_yaml_with_parameters(tmp_path: Path, parameters: dict, name: str) -> Path:
    data = yaml.safe_load(TASK_015.read_text(encoding="utf-8"))
    data["task_id"] = name
    data["parameters"] = parameters
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_frozen_015_task_declares_the_checkpoint_selector():
    task = load_task(TASK_015, root=REPO_ROOT)
    assert task.parameters["modeling_checkpoints"] is True
    assert task.parameters["multi_slice_workflow"] is True
    assert task.parameters["staged_modeling_decisions"] is True
    assert task.parameters["unified_semantic_graph"] is True


def test_selector_requires_all_three_underlying_parameters(tmp_path):
    with pytest.raises(TeamConfigurationError) as both_missing:
        load_task(
            _task_yaml_with_parameters(
                tmp_path,
                {"modeling_checkpoints": True},
                "r3015-gate-none",
            ),
            root=REPO_ROOT,
        )
    assert "modeling_checkpoints requires multi_slice_workflow and staged_modeling_decisions" in str(
        both_missing.value
    )
    with pytest.raises(TeamConfigurationError) as unified_missing:
        load_task(
            _task_yaml_with_parameters(
                tmp_path,
                {
                    "multi_slice_workflow": True,
                    "staged_modeling_decisions": True,
                    "modeling_checkpoints": True,
                },
                "r3015-gate-unified",
            ),
            root=REPO_ROOT,
        )
    assert "modeling_checkpoints requires unified_semantic_graph" in str(unified_missing.value)


def test_parameter_set_stays_closed(tmp_path):
    with pytest.raises(TeamConfigurationError):
        load_task(
            _task_yaml_with_parameters(
                tmp_path,
                {"multi_slice_workflow": True, "checkpoints": True},
                "r3015-gate-unknown",
            ),
            root=REPO_ROOT,
        )


# --- runner tier harness ----------------------------------------------------------


class _CheckpointRunner:
    """A prepared 011-profile runner on the frozen R3.0-015 Task."""

    def __init__(self, task_path: Path = TASK_015) -> None:
        self.run_id = f"r3015c-{os.urandom(4).hex()}"
        self.run_root = RUNS_ROOT / self.run_id
        self.adapter = CapturingAdapter()
        self.runner = TeamRunner(
            repository_root=REPO_ROOT,
            adapter=self.adapter,
            ledger_root=self.run_root.parent / f"{self.run_id}-ledger",
            freeze_started_at=datetime.now(UTC).isoformat(),
        )
        self._task_path = task_path

    def prepare(self) -> TeamRunner:
        self.runner.prepare(
            run_id=self.run_id,
            profile_path=PROFILE,
            task_path=self._task_path,
            scope={"mode": "create"},
        )
        return self.runner

    def cleanup(self) -> None:
        self.runner.cleanup()
        self.remove()

    def remove(self) -> None:
        """Remove the run tree without a second Runner cleanup."""

        rmtree(self.run_root, ignore_errors=True)
        rmtree(self.run_root.parent / f"{self.run_id}-ledger", ignore_errors=True)


def _freeze(runner: TeamRunner, batch_id: str = "batch-r3015") -> dict:
    return runner.freeze_cq_question_pool(
        {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": batch_id,
            "material_digest": f"material-{batch_id}",
            "panorama_question_ids": ["cq-1"],
            "slice_question_ids": [],
            "ordering": ["cq-1"],
            "review_binding": {
                "review_id": "cq-review-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": [_question("cq-1", visibility="hidden")],
        }
    )


def _outer_save(runner: TeamRunner, kind: str, **fields) -> dict:
    message = {"action": "checkpoint", "command": "save", "kind": kind}
    message.update(fields)
    records = runner.receive_outer(message)
    return records[-1]


def _checkpoint_events(runner: TeamRunner) -> list[dict]:
    return _read_evidence(runner, "checkpoints")


def _settled_apply_intent(runner: TeamRunner, ordinal: int = 1, mode: str = "apply") -> None:
    intent = build_submission_intent(
        ordinal,
        idempotency_key=f"idem-{ordinal}",
        client_batch_id=f"cb-{ordinal}",
        session_id="session-1",
        mode=mode,
        commands=[],
        value_traces=[],
        l3_nodes=[],
    )
    write_submission_intent(runner.run.root, mark_intent_status(intent, "receipted"))
    write_submission_receipt(
        runner.run.root,
        build_submission_receipt(
            ordinal, intent, batch_id=f"platform-batch-{ordinal}", response_digest="sha256:" + "1" * 64
        ),
    )


class _SettledTransport:
    """Production roles reported terminal status; stop() is a no-op."""

    def __init__(self, runner: TeamRunner, status: str = "completed") -> None:
        self.results = {
            agent.agent_id: type("R", (), {"status": status})()
            for agent in runner.run.configuration.profile.agents
            if agent.package.role in {"coordinator", "modeling", "protocol"}
        }

    def stop(self):
        return None


# --- runner tier: selector, automatic saves, outer dispatch ----------------------


def test_prepare_enables_the_selector_and_creates_the_private_directory():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        assert runner._modeling_checkpoints is True
        directory = runner.run.root / CHECKPOINT_DIRECTORY
        assert directory.is_dir()
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        events = _checkpoint_events(runner)
        assert events[0]["event"] == "selector-enabled"
        assert events[0]["segments"] == "s1-save-inspect-only"
        assert runner._cq_write_admission.snapshot()["capturing"] is False
    finally:
        harness.cleanup()


def test_selector_off_run_refuses_outer_checkpoint_saves():
    harness = _CheckpointRunner(task_path=TASK_008B)
    try:
        runner = harness.prepare()
        assert runner._modeling_checkpoints is False
        with pytest.raises(RecoverableOuterInputError) as refused:
            runner.receive_outer(
                {"action": "checkpoint", "command": "save", "kind": "cq_frozen"}
            )
        assert refused.value.code == "checkpoint_selector_required"
        assert not (runner.run.root / CHECKPOINT_DIRECTORY / "cq_frozen-0001").exists()
    finally:
        harness.cleanup()


def test_phase_complete_claim_without_artifacts_is_refused_with_retry_guidance():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        with pytest.raises(RecoverableOuterInputError) as refused:
            _outer_save(runner, CHECKPOINT_KIND_SCENARIO_MAPPED)
        assert refused.value.code == "checkpoint_missing_artifact"
        assert "stage-complete claim without artifacts" in str(refused.value)
        events = _checkpoint_events(runner)
        assert events[-1]["event"] == "checkpoint-save-failed"
        assert events[-1]["code"] == "checkpoint_missing_artifact"
        # Both branches of this evidence record carry the §8 key shape.
        assert events[-1]["phase"] == "checkpoint-save"
        assert not set(events[-1]) & {"reason_code", "detail", "object", "retry"}
        assert list_checkpoints(runner.run.root) == []
    finally:
        harness.cleanup()


def test_checkpoint_save_failed_evidence_uses_the_s8_shape_for_oserrors(monkeypatch):
    """I — Round 2 follow-up: the OSError branch matches the §8 key shape.

    The CheckpointError branch already spreads ``error.data()`` (§8 names);
    an I/O failure around the save must land in the SAME shape -- same
    ``code/object_ref/phase/retryable/reason`` fields, same save-side phase
    literal -- so downstream readers never see two key spellings.
    """

    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()

        def broken_save(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(runner, "_save_run_checkpoint", broken_save)
        runner._save_checkpoint_after_trigger(
            CHECKPOINT_KIND_SCENARIO_MAPPED, trigger="outer-request"
        )
        record = _checkpoint_events(runner)[-1]
        assert record["event"] == "checkpoint-save-failed"
        assert record["kind"] == CHECKPOINT_KIND_SCENARIO_MAPPED
        assert record["trigger"] == "outer-request"
        assert record["code"] == "checkpoint_write_failed"
        assert record["reason"] == "OSError"
        assert record["object_ref"] == "checkpoints"
        assert record["phase"] == "checkpoint-save"
        assert record["retryable"] is True
        assert "next_action" in record
        assert not set(record) & {"reason_code", "detail", "object", "retry"}
        # A failed save never terminated the run and left no package.
        assert list_checkpoints(runner.run.root) == []
    finally:
        harness.cleanup()


def test_m01_cq_freeze_automatically_saves_cq_frozen_with_topology_pending():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _freeze(runner)
        ids = [item["checkpoint_id"] for item in list_checkpoints(runner.run.root)]
        assert ids == ["cq_frozen-0001"]
        manifest = _read_manifest(runner.run.root, "cq_frozen-0001")
        assert manifest["kind"] == CHECKPOINT_KIND_CQ_FROZEN
        assert manifest["scope_refs"] == {"freeze_id": "batch-r3015"}
        facts = manifest["stage_facts"]
        assert facts["topology_decided"] is False
        assert "topology_decision" in facts["pending"]
        assert "semantic_modeling" in facts["pending"]
        binding = facts["bindings"][0]
        assert binding["artifact"].startswith("competency-questions/frozen/freeze-")
        assert binding["digest"] == file_digest(runner.run.root / binding["artifact"])
        frozen_entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["source"].startswith("competency-questions/frozen/")
        )
        assert frozen_entry["host_private"] is True
        projection_entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["source"].startswith("competency-questions/public/")
        )
        assert projection_entry["host_private"] is False
        events = _checkpoint_events(runner)
        assert events[-1]["event"] == "checkpoint-saved"
        assert events[-1]["trigger"] == "cq-freeze"
        # A second identical freeze-triggered save (manual request) dedups.
        record = _outer_save(runner, CHECKPOINT_KIND_CQ_FROZEN)
        assert record["status"] == "reused"
        assert record["checkpoint_id"] == "cq_frozen-0001"
    finally:
        harness.cleanup()


def test_confirmed_interview_saves_early_checkpoint_before_cq_freeze():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        ack = runner.handle_cq_outer_input(
            {"action": "cq_interview", "text": "confirmed service terminology"}
        )
        assert ack["type"] == "cq-interview-accepted"
        assert [item["checkpoint_id"] for item in list_checkpoints(runner.run.root)] == [
            "scenario_mapped-0001"
        ]
        early = _read_manifest(runner.run.root, "scenario_mapped-0001")
        assert early["stage_facts"]["cq_frozen"] is False
        interview = next(
            item for item in early["artifacts"] if item["source"].endswith("interview-0001.json")
        )
        assert interview["host_private"] is True
        assert _checkpoint_events(runner)[-1]["trigger"] == "cq-interview"

        _freeze(runner)
        assert {item["kind"] for item in list_checkpoints(runner.run.root)} == {
            CHECKPOINT_KIND_SCENARIO_MAPPED,
            CHECKPOINT_KIND_CQ_FROZEN,
        }
    finally:
        harness.cleanup()


def test_outer_inspect_returns_the_read_only_view():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _freeze(runner)
        records = runner.receive_outer({"action": "checkpoint", "command": "inspect"})
        payload = records[-1]
        assert payload["type"] == "checkpoint-inspect"
        assert payload["published_count"] == 1
        assert payload["resume"]["available"] is True
        with pytest.raises(RecoverableOuterInputError) as missing:
            runner.receive_outer(
                {
                    "action": "checkpoint",
                    "command": "inspect",
                    "checkpoint_id": "cq_frozen-9999",
                }
            )
        assert missing.value.code == "checkpoint_not_found"
    finally:
        harness.cleanup()


# --- runner tier: real platform bindings on save (R3.0-015 regression) ----------


class _PlanOntologyClient(ScopeClient):
    """ScopeClient that mints a distinct id for each planned Ontology create."""

    def __init__(self) -> None:
        super().__init__()
        self.ontology_creates = 0

    def __call__(self, method, path, body, key):
        if method == "POST" and path.endswith("/ontologies"):
            self.calls.append((method, path))
            self.ontology_creates += 1
            return 201, {"id": f"ontology-{self.ontology_creates}"}
        return super().__call__(method, path, body, key)


def _bound_runner_scope(client: ScopeClient | None = None) -> PlatformScope:
    """A real PlatformScope prepared in create mode (project-1/ontology-1)."""

    scope = PlatformScope(
        "http://example",
        "unit-run-123",
        lambda: ("admin", "admin-id"),
        lambda _: True,
        client or ScopeClient(),
    )
    scope.prepare({"mode": "create"})
    return scope


def _saved_cq_frozen_manifest(runner: TeamRunner) -> dict:
    ids = [item["checkpoint_id"] for item in list_checkpoints(runner.run.root)]
    assert ids == ["cq_frozen-0001"]
    return _read_manifest(runner.run.root, "cq_frozen-0001")


def test_checkpoint_save_records_the_real_single_ontology_scope_identity():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        runner.scope = _bound_runner_scope()
        _freeze(runner)
        manifest = _saved_cq_frozen_manifest(runner)
        bindings = manifest["platform_bindings"]
        assert bindings["project_id"] == "project-1"
        # Single-Ontology create path: the bound Ontology is the full verified set.
        assert bindings["ontology_ids"] == ["ontology-1"]
        assert bindings["ontology_id"] == "ontology-1"
        # The saved manifest satisfies exactly the resume gate's resolution.
        assert production_resume_bindings(manifest) == {
            "project_id": "project-1",
            "ontology_ids": ["ontology-1"],
        }
    finally:
        harness.runner.scope = None
        harness.remove()


def test_checkpoint_save_records_the_full_multi_ontology_set():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        scope = _bound_runner_scope(_PlanOntologyClient())
        scope.apply_ontology_plan(
            [
                {"name": "ontology-1", "slice_ids": ["slice-a"]},
                {"name": "slice-b-ontology", "slice_ids": ["slice-b"]},
            ]
        )
        assert scope.ontology_ids == ["ontology-1", "ontology-2"]
        runner.scope = scope
        _freeze(runner)
        bindings = _saved_cq_frozen_manifest(runner)["platform_bindings"]
        assert bindings["ontology_ids"] == ["ontology-1", "ontology-2"]
    finally:
        harness.runner.scope = None
        harness.remove()


def test_checkpoint_save_without_bound_scope_records_no_fabricated_bindings():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        assert runner.scope is None
        _freeze(runner)
        bindings = _saved_cq_frozen_manifest(runner)["platform_bindings"]
        assert bindings["run_scope"] == {"mode": "create"}
        assert "project_id" not in bindings
        assert "ontology_ids" not in bindings
        assert "ontology_id" not in bindings
        assert (
            production_resume_bindings(_saved_cq_frozen_manifest(runner)) is None
        )
    finally:
        harness.cleanup()


def test_m41_scenario_mapped_saves_confirmed_interviews_with_pending_topology():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        interview = runner.run.root / "competency-questions" / "private" / "interview-0001.json"
        _write_json(
            interview,
            {"question_id": "cq-1", "answer": "confirmed", "note": "hidden-material-marker"},
        )
        record = _outer_save(runner, CHECKPOINT_KIND_SCENARIO_MAPPED)
        assert record["status"] == "saved"
        manifest = _read_manifest(runner.run.root, record["checkpoint_id"])
        facts = manifest["stage_facts"]
        assert facts["topology_decided"] is False
        assert facts["cq_frozen"] is False
        assert "topology_decision" in facts["pending"]
        assert "cq_freeze" in facts["pending"]
        assert "semantic_modeling" in facts["pending"]
        assert "confirmed interviews" in facts["next_step"]
        entry = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["source"].endswith("interview-0001.json")
        )
        assert entry["host_private"] is True

        # Once the topology decision is published but CQ is still unfrozen,
        # the same kind saves with exactly that pending state (M41 variant).
        _write_json(
            runner.run.root / "scenario-map" / "topology-decision.json",
            {"decision": "multi-ontology"},
        )
        _write_json(
            runner.run.root / "scenario-map" / "scenario-map.json",
            {"sections": ["six-sections-maintained"]},
        )
        second = _outer_save(runner, CHECKPOINT_KIND_SCENARIO_MAPPED, request_id="req-2")
        assert second["status"] == "saved"
        facts = _read_manifest(runner.run.root, second["checkpoint_id"])["stage_facts"]
        assert facts["topology_decided"] is True
        assert "topology_decision" not in facts["pending"]
        assert "cq_freeze" in facts["pending"]
    finally:
        harness.cleanup()


def test_m02_semantic_approved_keeps_undecided_content_pending():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        paths = staged_decision_artifact_paths(runner.run.root, unified=True)
        _write_json(
            paths["approvals"],
            {"schema_version": "r3-0-008b-approvals/v1", "decisions": ["approved"]},
        )
        _write_json(
            paths["conclusions"],
            {
                "schema_version": "r3-0-008b-conclusions/v1",
                "slice_a": {"status": "analyzed_not_materialized"},
                "slice_b": {"status": "open"},
            },
        )
        _write_json(
            paths["candidates_dir"] / "candidate-0001.json",
            {"candidate_id": "c1", "statements": []},
        )
        record = _outer_save(runner, CHECKPOINT_KIND_SEMANTIC_APPROVED)
        assert record["status"] == "saved"
        manifest = _read_manifest(runner.run.root, record["checkpoint_id"])
        facts = manifest["stage_facts"]
        assert facts["analyzed_not_materialized"] == 1
        assert facts["candidate_count"] == 1
        assert "value_materialization" in facts["pending"]
        assert "remaining_semantics" in facts["pending"]
        root = runner.run.root
        sources = [artifact["source"] for artifact in manifest["artifacts"]]
        expected_approvals = paths["approvals"].relative_to(root).as_posix()
        expected_conclusions = paths["conclusions"].relative_to(root).as_posix()
        assert expected_approvals in sources
        assert expected_conclusions in sources
        # The semantic approval package deliberately excludes write positions:
        # it claims no recoverable platform write state.
        assert not any(source.startswith("value-semantics/submission-intents/") for source in sources)
    finally:
        harness.cleanup()


def test_m03_apply_and_dry_run_receipts_are_distinguishable_states():
    for mode, expected in (("apply", "applied"), ("dry_run", "validated_not_applied")):
        harness = _CheckpointRunner()
        try:
            runner = harness.prepare()
            _settled_apply_intent(runner, ordinal=1, mode=mode)
            record = _outer_save(runner, CHECKPOINT_KIND_MATERIALIZATION_PROGRESS)
            assert record["status"] == "saved"
            manifest = _read_manifest(runner.run.root, record["checkpoint_id"])
            position = manifest["write_positions"]["positions"][0]
            assert position["state"] == expected
            assert position["idempotency_key"] == "idem-1"
            assert position["batch_id"] == "platform-batch-1"
        finally:
            harness.cleanup()


def test_m07_write_claiming_save_waits_for_in_flight_and_unknown_writes(monkeypatch):
    monkeypatch.setattr(runner_module, "_CQ_WRITE_DRAIN_TIMEOUT_SECONDS", 0.05)

    # (a) an admitted, never-completed staged write blocks the save.
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _settled_apply_intent(runner)
        ticket = runner._cq_write_admission.admit("staged_submit_modeling_batch")
        assert ticket is not None
        with pytest.raises(CheckpointError) as in_flight:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
            )
        assert in_flight.value.reason_code == "checkpoint_write_unreconciled"
        assert "bounded drain wait" in in_flight.value.detail
        assert list_checkpoints(runner.run.root) == []
    finally:
        harness.cleanup()

    # (b) an unknown admission outcome blocks even after draining.
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _settled_apply_intent(runner)
        ticket = runner._cq_write_admission.admit("staged_submit_modeling_batch")
        runner._cq_write_admission.complete(ticket, "unknown")
        with pytest.raises(CheckpointError) as unknown:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
            )
        assert unknown.value.reason_code == "checkpoint_write_unreconciled"
        assert unknown.value.retry.startswith("let the staged writes settle")
    finally:
        harness.cleanup()

    # (c) a durable intent recorded unknown blocks the save.
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        intent = build_submission_intent(
            1,
            idempotency_key="idem-1",
            client_batch_id="cb-1",
            session_id="session-1",
            mode="apply",
            commands=[],
            value_traces=[],
            l3_nodes=[],
        )
        write_submission_intent(runner.run.root, mark_intent_status(intent, "unknown"))
        receipt = build_submission_receipt(
            1, intent, batch_id="platform-batch-1", response_digest="sha256:" + "1" * 64
        )
        write_submission_receipt(runner.run.root, receipt)
        with pytest.raises(CheckpointError) as unknown_intent:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
            )
        assert unknown_intent.value.reason_code == "checkpoint_write_unreconciled"
    finally:
        harness.cleanup()

    # (d) a pending intent without a receipt blocks the save.
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _settled_apply_intent(runner)
        pending = build_submission_intent(
            2,
            idempotency_key="idem-2",
            client_batch_id="cb-2",
            session_id="session-1",
            mode="apply",
            commands=[],
            value_traces=[],
            l3_nodes=[],
        )
        write_submission_intent(runner.run.root, pending)
        with pytest.raises(CheckpointError) as unsettled:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
            )
        assert unsettled.value.reason_code == "checkpoint_write_unreconciled"
        assert "unsettled intents" in unsettled.value.detail
    finally:
        harness.cleanup()


def test_m07_settled_writes_save_with_positions_and_do_not_block_forever():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        # A materialization-progress save happens on a scope-bound run.
        runner.scope = _bound_runner_scope()
        ticket = runner._cq_write_admission.admit("staged_submit_modeling_batch")
        runner._cq_write_admission.complete(ticket, "receipted")
        _settled_apply_intent(runner)
        result = runner._save_run_checkpoint(
            CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, trigger="outer-request"
        )
        assert result["status"] == "saved"
        manifest = _read_manifest(runner.run.root, result["checkpoint_id"])
        assert manifest["write_positions"]["in_flight"] == []
        assert manifest["write_positions"]["unknown"] == []
        assert manifest["write_positions"]["positions"][0]["state"] == "applied"
        inspection = inspect_checkpoints(runner.run.root, result["checkpoint_id"])
        reconciliation = inspection["checkpoint"]["write_reconciliation"]
        assert reconciliation["completed_operations"] == ["idem-1"]
        assert reconciliation["unreconciled"] == []
        assert inspection["checkpoint"]["status"] in {"ready", "needs_reconciliation"}
    finally:
        harness.cleanup()


def test_m04_production_handoff_save_binds_evidence_not_a_ready_boolean():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        handoff_dir = runner.run.root / "acceptance-v3"
        # A handoff whose only evidence is a boolean is refused (M04).
        _write_json(handoff_dir / "production-handoff.json", {"ready": True})
        with pytest.raises(CheckpointError) as bare_bool:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="outer-request"
            )
        assert bare_bool.value.reason_code == "checkpoint_missing_artifact"
        assert "freeze_id" in bare_bool.value.detail

        # A handoff recording unknown writes is never a recoverable package.
        _write_json(
            handoff_dir / "production-handoff.json",
            {
                "freeze_id": "batch-r3015",
                "freeze_digest": "sha256:" + "0" * 64,
                "scope_binding": {"project_id": "p1", "ontology_ids": []},
                "applied_batches": [],
                "unknown_writes": [{"idempotency_key": "idem-9"}],
                "write_phase": "read-only",
                "acceptance_target": "full_joint",
            },
        )
        with pytest.raises(CheckpointError) as unknown_writes:
            runner._save_run_checkpoint(
                CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="outer-request"
            )
        assert unknown_writes.value.reason_code == "checkpoint_write_unreconciled"

        # The real published handoff saves with its evidence bindings.
        _write_json(
            handoff_dir / "production-handoff.json",
            {
                "freeze_id": "batch-r3015",
                "freeze_digest": "sha256:" + "0" * 64,
                "scope_binding": {"project_id": "p1", "ontology_ids": ["o1"]},
                "applied_batches": [{"batch_id": "b1"}, {"batch_id": "b2"}],
                "not_applied": [{"batch_id": "b3"}],
                "unknown_writes": [],
                "write_phase": "read-only",
                "acceptance_target": "full_joint",
                "acceptance_attempt_id": "attempt-0001",
            },
        )
        result = runner._save_run_checkpoint(
            CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            trigger="outer-request",
            scope_refs={},
        )
        assert result["status"] == "saved"
        manifest = _read_manifest(runner.run.root, result["checkpoint_id"])
        facts = manifest["stage_facts"]
        assert facts["freeze_id"] == "batch-r3015"
        assert facts["freeze_digest"] == "sha256:" + "0" * 64
        assert facts["acceptance_target"] == "full_joint"
        assert facts["applied_batch_count"] == 2
        assert facts["not_applied_count"] == 1
        sources = [artifact["source"] for artifact in manifest["artifacts"]]
        assert "acceptance-v3/production-handoff.json" in sources
        assert "acceptance-v3/run-contract.json" in sources
        for entry in manifest["artifacts"]:
            if entry["source"].startswith("acceptance-v3/"):
                assert entry["host_private"] is True
                assert entry["visible_to"] == ["host"]
    finally:
        harness.cleanup()


def test_m04_real_handoff_flow_automatically_saves_production_handoff():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        frozen = _freeze(runner)
        runner.transport = _SettledTransport(runner)
        ack = runner.handle_cq_outer_input(
            {
                "action": "cq_handoff_complete",
                "freeze_id": "batch-r3015",
                "freeze_digest": frozen["snapshot_digest"],
                "delivery_binding": {"delivery_id": "d1", "digest": frozen["snapshot_digest"]},
            }
        )
        assert ack["ok"] is True
        kinds = {
            item["kind"]: item["checkpoint_id"] for item in list_checkpoints(runner.run.root)
        }
        assert kinds.get(CHECKPOINT_KIND_CQ_FROZEN) == "cq_frozen-0001"
        handoff_id = kinds[CHECKPOINT_KIND_PRODUCTION_HANDOFF]
        manifest = _read_manifest(runner.run.root, handoff_id)
        assert manifest["stage_facts"]["freeze_id"] == "batch-r3015"
        assert manifest["stage_facts"]["pending"] == []
        events = _checkpoint_events(runner)
        assert events[-1]["event"] == "checkpoint-saved"
        assert events[-1]["trigger"] == "production-handoff"
        # The handoff package claims a read-only write phase and zero unknowns.
        assert manifest["write_positions"]["unknown"] == []
        assert manifest["write_positions"]["positions"] == []
    finally:
        harness.cleanup()


def test_d1_reversible_capture_barrier_is_not_the_phase_ladder():
    admission = CQWriteAdmission()
    assert admission.begin_capture() is True
    assert admission.capturing is True
    assert admission.phase == "open"
    assert admission.admit("staged_submit_modeling_batch") is None
    assert admission.snapshot()["capturing"] is True
    admission.end_capture()
    assert admission.capturing is False
    assert admission.phase == "open"
    assert admission.admit("staged_submit_modeling_batch") is not None
    admission.end_capture()  # idempotent

    admission.begin_quiescing()
    assert admission.begin_capture() is False
    assert admission.phase == "quiescing"


def test_d1_staged_write_entry_points_defer_while_capturing():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        runner._cq_write_admission.begin_capture()
        with pytest.raises(StagedSubmissionRejection) as batch_deferred:
            runner._handle_staged_submit_modeling_batch({})
        assert batch_deferred.value.data["reason_code"] == "staged_write_checkpoint_capture"
        with pytest.raises(StagedSubmissionRejection) as evidence_deferred:
            runner._handle_staged_associate_evidence({})
        assert (
            evidence_deferred.value.data["reason_code"] == "staged_write_checkpoint_capture"
        )
        runner._cq_write_admission.end_capture()
        # Outside the capture window the same malformed input fails for its
        # own typed reasons again -- admission itself is restored.
        with pytest.raises(StagedSubmissionRejection) as normal:
            runner._handle_staged_submit_modeling_batch({})
        assert normal.value.data["reason_code"] != "staged_write_checkpoint_capture"
    finally:
        harness.cleanup()


def test_cleanup_wires_checkpoint_retention_into_scope_evidence():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        _freeze(runner)
        scope = SimpleNamespace(
            checkpoint_retention=None,
            cleanup=lambda: {"scope_disposition": "retained-checkpoint-reference"},
        )
        runner.scope = scope
        runner.cleanup()
        assert scope.checkpoint_retention["checkpoint_ids"] == ["cq_frozen-0001"]
        events = _checkpoint_events(runner)
        final = events[-1]
        assert final["event"] == "scope-retention-reference"
        assert final["scope_disposition"] == "retained-checkpoint-reference"
        assert final["count"] == 1
    finally:
        harness.runner.scope = None
        harness.remove()


def test_cleanup_without_packages_leaves_retention_unset():
    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        scope = SimpleNamespace(
            checkpoint_retention=None,
            cleanup=lambda: {"scope_disposition": "deleted-empty"},
        )
        runner.scope = scope
        runner.cleanup()
        assert scope.checkpoint_retention is None
        assert all(
            event["event"] != "scope-retention-reference" for event in _checkpoint_events(runner)
        )
    finally:
        harness.runner.scope = None
        harness.remove()


# --- platform scope retention (M23) ----------------------------------------------


def test_m23_empty_owned_scope_is_retained_on_checkpoint_reference():
    client = ScopeClient()
    scope = PlatformScope(
        "http://example",
        "unit-run-123",
        lambda: ("admin", "admin-id"),
        lambda _: True,
        client,
    )
    scope.prepare({"mode": "create"})
    scope.checkpoint_retention = {
        "reason": "published-valid-checkpoint-reference",
        "checkpoint_ids": ["cq_frozen-0001"],
        "count": 1,
    }
    cleanup = scope.cleanup()
    assert cleanup["scope_disposition"] == "retained-checkpoint-reference"
    assert cleanup["checkpoint_retention"]["checkpoint_ids"] == ["cq_frozen-0001"]
    assert ("DELETE", "/api/projects/project-1") not in client.calls
    assert cleanup["admin_key_revoked"] is True
    assert scope.admin_key is None


def test_m23_without_retention_the_empty_scope_still_deletes():
    client = ScopeClient()
    scope = PlatformScope(
        "http://example",
        "unit-run-123",
        lambda: ("admin", "admin-id"),
        lambda _: True,
        client,
    )
    scope.prepare({"mode": "create"})
    cleanup = scope.cleanup()
    assert cleanup["scope_disposition"] == "deleted-empty"
    assert ("DELETE", "/api/projects/project-1") in client.calls


# --- CLI tier (M08 host-only dispatch) ---------------------------------------------


def _run_cli(monkeypatch, argv: list[str], *, credential: str | None = "host-key") -> int:
    from modeling_team.__main__ import main

    monkeypatch.setattr(sys, "argv", ["modeling_team", *argv])
    if credential is None:
        monkeypatch.delenv("ONTOLOGY_PLATFORM_ADMIN_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ONTOLOGY_PLATFORM_ADMIN_API_KEY", credential)
    return main()


def test_cli_missing_host_credential_fails_closed(monkeypatch, capsys):
    assert (
        _run_cli(
            monkeypatch,
            ["checkpoint", "inspect", "--run-id", "whatever"],
            credential=None,
        )
        == 2
    )
    message = capsys.readouterr().err
    assert "host platform credential is missing" in message
    assert "ONTOLOGY_PLATFORM_ADMIN_API_KEY" in message


def test_cli_inspect_lists_and_rejects_accurately(monkeypatch, capsys):
    run_id = f"r3015cli-{os.urandom(4).hex()}"
    run_root = RUNS_ROOT / run_id
    try:
        _write_json(run_root / "evidence" / "stage.json", {"stage": "cli"})
        saved = save_checkpoint(
            run_root,
            _package(),
            source_run_id=run_id,
            configuration=dict(CONFIGURATION),
        )
        before = _tree_state(run_root)

        assert _run_cli(monkeypatch, ["checkpoint", "inspect", "--run-id", run_id]) == 0
        listing = json.loads(capsys.readouterr().out)
        assert listing["published_count"] == 1
        assert listing["cumulative_size_bytes"] > 0
        assert listing["checkpoints"][0]["checkpoint_id"] == saved["checkpoint_id"]
        assert listing["resume"]["available"] is True

        assert (
            _run_cli(
                monkeypatch,
                [
                    "checkpoint",
                    "inspect",
                    "--run-id",
                    run_id,
                    "--checkpoint-id",
                    saved["checkpoint_id"],
                ],
            )
            == 0
        )
        detail = json.loads(capsys.readouterr().out)
        assert detail["checkpoint"]["status"] in {
            "ready",
            "needs_reconciliation",
            "incompatible",
        }
        assert detail["checkpoint"]["reusable_artifacts"][0]["source"] == "evidence/stage.json"

        assert (
            _run_cli(
                monkeypatch,
                ["checkpoint", "inspect", "--run-id", run_id, "--checkpoint-id", "no-such-1"],
            )
            == 2
        )
        assert "checkpoint_not_found" in capsys.readouterr().err
        assert (
            _run_cli(
                monkeypatch,
                [
                    "checkpoint",
                    "inspect",
                    "--run-id",
                    run_id,
                    "--checkpoint-id",
                    "../escape",
                ],
            )
            == 2
        )
        assert "checkpoint_invalid_id" in capsys.readouterr().err
        assert _run_cli(monkeypatch, ["checkpoint", "inspect", "--run-id", "../evil"]) == 2
        assert "--run-id" in capsys.readouterr().err
        assert _run_cli(monkeypatch, ["checkpoint", "inspect", "--run-id", "absent-run"]) == 2
        assert "does not exist" in capsys.readouterr().err
        # Read-only end to end: nothing under the run root changed.
        assert _tree_state(run_root) == before
    finally:
        rmtree(run_root, ignore_errors=True)


def test_cli_resume_without_required_arguments_fails_closed(monkeypatch, capsys):
    # S2 ships the resume subcommand; argparse still fails closed on the
    # missing mandatory identity arguments (explicit checkpoint id, new run
    # id, mode) instead of silently substituting any of them.
    with pytest.raises(SystemExit) as rejected:
        _run_cli(
            monkeypatch,
            ["checkpoint", "resume", "--run-id", "x", "--checkpoint-id", "y"],
        )
    assert rejected.value.code == 2
    err = capsys.readouterr().err
    assert "--new-run-id" in err or "--mode" in err


def test_cli_outer_action_gate_admits_checkpoint():
    from modeling_team.__main__ import _KNOWN_OUTER_ACTIONS

    assert "checkpoint" in _KNOWN_OUTER_ACTIONS
