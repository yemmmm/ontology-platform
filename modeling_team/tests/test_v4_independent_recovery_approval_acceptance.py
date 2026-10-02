"""Independent approval recovery acceptance using only synthetic saved packages."""

from __future__ import annotations

from copy import deepcopy

import pytest

from modeling_team.checkpoint_recovery import (
    REASON_APPROVAL_BINDING_CHANGED,
    validate_business_approvals,
)
from modeling_team.checkpoints import CheckpointError
from modeling_team.tests.test_r30015_resume import (
    APPROVALS_RELATIVE,
    _approvals_run,
    _manifest_of,
    _tree_state,
    _write_json,
)

AGENTS = [
    {"agent_id": "neutral-owner", "package": "coordinator"},
    {"agent_id": "neutral-modeler", "package": "modeling"},
]


def _history():
    # Deliberately non-monotonic list ordering: list position is not authority.
    return [
        {
            "kind": "conclusion_confirmation",
            "target_id": target,
            "revision": revision,
            "confirmed_enum_value": f"{target}-choice-{revision}",
            "approved_by": "neutral-owner",
            "note": "synthetic evidence",
        }
        for target, revision in [
            ("choice-a", 4),
            ("choice-b", 2),
            ("choice-a", 1),
            ("choice-b", 7),
            ("choice-a", 3),
        ]
    ] + [
        {
            "kind": "stage3_slot",
            "target_id": "neutral-slot",
            "revision": revision,
            "approved_by": "neutral-owner",
        }
        for revision in [6, 2]
    ]


def _fixture(tmp_path):
    entries = _history()
    root, saved = _approvals_run(tmp_path, entries=entries, profile_agents=AGENTS)
    return root, _manifest_of(root, saved["checkpoint_id"]), entries


def _current(root, entries):
    _write_json(
        root / APPROVALS_RELATIVE, {"schema_version": "r3-0-008b-approvals/v1", "entries": entries}
    )


def _read_only_validate(root, manifest):
    before = _tree_state(root)
    try:
        return validate_business_approvals(manifest, root)
    finally:
        assert _tree_state(root) == before


def test_unchanged_multirevision_history_and_unrelated_translation_append_reuse_heads(tmp_path):
    root, manifest, entries = _fixture(tmp_path)
    _current(
        root,
        [
            *reversed(entries),
            {
                "kind": "translation_approval",
                "target_id": "unrelated-plan",
                "revision": 1,
                "approved_by": "neutral-owner",
                "status": "approved",
            },
        ],
    )
    result = _read_only_validate(root, manifest)
    assert result["invalidated"] == []
    assert {
        (item["kind"], item["target_id"], item["revision"], item["approved_by"])
        for item in result["valid"]
    } == {
        ("conclusion_confirmation", "choice-a", 4, "neutral-owner"),
        ("conclusion_confirmation", "choice-b", 7, "neutral-owner"),
        ("stage3_slot", "neutral-slot", 6, "neutral-owner"),
    }
    assert result["source_path"] == APPROVALS_RELATIVE
    assert result["source_digest"].startswith("sha256:")


@pytest.mark.parametrize(
    "mutation", ["new_head", "revoked_head", "removed_head", "changed_content", "changed_approver"]
)
def test_current_head_change_cannot_resurrect_saved_history(tmp_path, mutation):
    root, manifest, entries = _fixture(tmp_path)
    head = next(
        item for item in entries if item["target_id"] == "choice-a" and item["revision"] == 4
    )
    current = deepcopy(entries)
    if mutation in {"new_head", "revoked_head"}:
        current.append(
            {
                **head,
                "revision": 8,
                "confirmed_enum_value": "withdrawn" if mutation == "revoked_head" else "new-choice",
            }
        )
    elif mutation == "removed_head":
        current = [
            item
            for item in current
            if not (item["target_id"] == "choice-a" and item["revision"] == 4)
        ]
    else:
        for item in current:
            if item["target_id"] == "choice-a" and item["revision"] == 4:
                item["confirmed_enum_value" if mutation == "changed_content" else "approved_by"] = (
                    "changed"
                )
    # Older revisions remain in every case; mere historical presence is insufficient.
    assert any(item["target_id"] == "choice-a" and item["revision"] == 1 for item in current)
    _current(root, current)
    result = _read_only_validate(root, manifest)
    assert [
        (item["target_id"], item["revision"], item["reason"]) for item in result["invalidated"]
    ] == [("choice-a", 4, REASON_APPROVAL_BINDING_CHANGED)]
    assert {item["target_id"] for item in result["valid"]} == {"choice-b", "neutral-slot"}


def test_changed_source_profile_channel_is_typed_rejection(tmp_path):
    root, manifest, _entries = _fixture(tmp_path)
    _write_json(
        root / "profile.snapshot.yaml",
        {
            "profile_id": "unrelated-profile",
            "agents": AGENTS,
        },
    )
    with pytest.raises(CheckpointError) as exc:
        _read_only_validate(root, manifest)
    assert exc.value.reason_code == REASON_APPROVAL_BINDING_CHANGED


def test_changed_source_coordinator_identity_does_not_import_saved_decisions(tmp_path):
    root, manifest, _entries = _fixture(tmp_path)
    _write_json(
        root / "profile.snapshot.yaml",
        {
            "profile_id": manifest["configuration"]["profile_id"],
            "agents": [{"agent_id": "replacement-owner", "package": "coordinator"}],
        },
    )
    result = _read_only_validate(root, manifest)
    assert {item["target_id"] for item in result["invalidated"]} == {"choice-a", "choice-b"}
    assert all(item["reason"] == REASON_APPROVAL_BINDING_CHANGED for item in result["invalidated"])
    # Slot is a marker, not conclusion approval authority under the frozen contract.
    assert {item["target_id"] for item in result["valid"]} == {"neutral-slot"}


def test_unpackaged_run_side_approvals_cannot_become_recovery_authority(tmp_path):
    root, manifest, _entries = _fixture(tmp_path)
    manifest = deepcopy(manifest)
    manifest["artifacts"] = [
        item for item in manifest["artifacts"] if item["source"] != APPROVALS_RELATIVE
    ]
    result = _read_only_validate(root, manifest)
    assert result["present"] is False
    assert result["valid"] == []
