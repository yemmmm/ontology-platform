"""Regression coverage for direct-submission envelope and identity boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modeling_team.direct_submission import ObservedModelBindings, SubmissionInputError


PROJECT = "project-1"
ONTOLOGY = "ontology-1"
CLASS_IRI = "http://ontology-platform.local/semantic/class/class-1"
CLASS_ID = "class-1"


def _observe(root: Path, *, name: str, tool: str, payload: dict, arguments: dict) -> str:
    path = root / "evidence" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(raw)
    ref = f"evidence/{name}"
    observations[ref] = {
        "tool": tool,
        "successful": True,
        "response_digest": hashlib.sha256(raw).hexdigest(),
        "request_arguments": arguments,
    }
    return ref


def _reader(*, revision: int, visible: bool = True):
    def read(tool: str, arguments: dict) -> dict:
        if tool == "get_modeling_context":
            return {"ok": True, "data": {"workspace": {"model_revision": revision}}}
        if tool == "query_semantic_context":
            return {
                "ok": True,
                "data": {"primary_matches": [{"iri": CLASS_IRI}] if visible else []},
            }
        raise AssertionError(f"unexpected read: {tool} {arguments}")

    return read


def test_read_model_envelope_keeps_iri_out_of_resource_id(tmp_path):
    global observations
    observations = {}
    ref = _observe(
        tmp_path,
        name="classes.json",
        tool="get_ontology_read_model",
        payload={
            "structuredContent": {
                "data": {
                    "model_revision": 2,
                    "items": [
                        {
                            "id": CLASS_IRI,
                            "iri": CLASS_IRI,
                            "class_iri": CLASS_IRI,
                            "ontology_id": ONTOLOGY,
                        }
                    ],
                }
            }
        },
        arguments={"ontology_id": ONTOLOGY, "model_name": "classes"},
    )

    binding = ObservedModelBindings(
        tmp_path, observations, PROJECT, [ONTOLOGY], _reader(revision=2)
    ).resolve({"artifact_ref": ref, "path": "/structuredContent/data/items/0"})

    assert binding["resource_iri"] == CLASS_IRI
    assert "resource_id" not in binding
    assert binding["model_revision"] == 2


def test_applied_receipt_uuid_is_reusable_after_current_read_revision_advances(tmp_path):
    global observations
    observations = {}
    ref = _observe(
        tmp_path,
        name="class-apply.json",
        tool="submit_modeling_batch",
        payload={
            "structuredContent": {
                "data": {
                    "attempt_status": "applied",
                    "ontology_id": ONTOLOGY,
                    "workspace": {"after_version": 1},
                    "items": [
                        {
                            "client_item_id": "create-class",
                            "resource_outputs": {
                                "resource_id": CLASS_ID,
                                "resource_iri": CLASS_IRI,
                            },
                        }
                    ],
                }
            }
        },
        arguments={
            "ontology_id": ONTOLOGY,
            "items": [{"client_item_id": "create-class", "command_kind": "create_class"}],
        },
    )

    binding = ObservedModelBindings(
        tmp_path, observations, PROJECT, [ONTOLOGY], _reader(revision=2)
    ).resolve({"artifact_ref": ref, "path": "/structuredContent/data/items/0"})

    assert binding["resource_id"] == CLASS_ID
    assert binding["resource_iri"] == CLASS_IRI
    assert binding["resource_kind"] == "class"
    assert binding["model_revision"] == 2


def test_advanced_receipt_requires_current_authorized_iri_visibility(tmp_path):
    global observations
    observations = {}
    ref = _observe(
        tmp_path,
        name="class-apply.json",
        tool="submit_modeling_batch",
        payload={
            "structuredContent": {
                "data": {
                    "attempt_status": "applied",
                    "ontology_id": ONTOLOGY,
                    "workspace": {"after_version": 1},
                    "items": [
                        {
                            "client_item_id": "create-class",
                            "resource_outputs": {
                                "resource_id": CLASS_ID,
                                "resource_iri": CLASS_IRI,
                            },
                        }
                    ],
                }
            }
        },
        arguments={
            "ontology_id": ONTOLOGY,
            "items": [{"client_item_id": "create-class", "command_kind": "create_class"}],
        },
    )

    with pytest.raises(SubmissionInputError, match="not currently readable"):
        ObservedModelBindings(
            tmp_path, observations, PROJECT, [ONTOLOGY], _reader(revision=2, visible=False)
        ).resolve({"artifact_ref": ref, "path": "/structuredContent/data/items/0"})
