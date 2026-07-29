from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

import m7_contract as contract  # noqa: E402
from m7_host import HostError, compiler_preflight, stage_run_manifest  # noqa: E402


def public_map() -> dict[str, dict[str, str]]:
    return {
        "workflow_class": {"resource_id": "class-workflow", "resource_iri": "https://m7.test/class/workflow"},
        "variable_class": {"resource_id": "class-variable", "resource_iri": "https://m7.test/class/variable"},
    }


def test_frozen_agent_sources_are_exactly_manifested_and_english_only() -> None:
    manifest = contract.verify_agent_input()
    names = {entry["path"] for entry in manifest["files"]}
    assert "official/tools.mdx" in names
    assert {"authoring-contract.json", "seal_semantic_package.py"} <= names
    assert all("/zh/" not in name and "hidden" not in name for name in names)
    assert (SCENARIO_ROOT / "host-only" / "answer-contract-v1.json").is_file()


def test_visible_authoring_grammar_does_not_publish_hidden_semantic_mapping_or_cases() -> None:
    visible_grammar = "\n".join(
        (SCENARIO_ROOT / "agent-input" / name).read_text(encoding="utf-8").lower()
        for name in ("authoring-contract.json", "task.md", "seal_semantic_package.py")
    )
    for hidden_term in ("start_topic", "start_channel", "manual_review", "missing_score", "quality_contract", "affected_binding", "template-output-identity"):
        assert hidden_term not in visible_grammar


def test_base_package_is_deterministic_and_has_no_historical_runtime_id() -> None:
    manifest = contract.verify_base_slice()
    assert manifest["manifest_version"] == 1
    package = json.loads((SCENARIO_ROOT / "base-slice" / "semantic-package.json").read_text())
    ids = {item["client_item_id"] for item in package["items"]}
    assert ids >= {"workflow-class", "binding-relation-type", "workflow-a", "workflow-b", "workflow-c-v2"}
    relation_type = next(item for item in package["items"] if item["client_item_id"] == "binding-relation-type")
    assert set(relation_type["payload"]) >= {"name", "source_class_id", "target_class_id"}
    assert relation_type["payload"]["source_class_id"]["item_ref"]["output"] == "resource_id"
    relation = next(item for item in package["items"] if item["client_item_id"] == "b-c-invokes-c-v2")
    assert all(value["item_ref"]["output"] == "resource_iri" for value in relation["payload"].values())
    assert {"quality-score", "quality-rating", "missing-score-unknown", "a-publish-binding"} <= ids
    compiler_preflight(package["items"])


def test_host_only_contracts_and_published_command_inventory_are_frozen() -> None:
    manifest = contract.verify_host_only()
    assert {entry["path"] for entry in manifest["files"]} == {
        "acceptance-contract.json",
        "answer-contract-v1.json",
        "mutation-contract.json",
        "published-command-kinds.json",
    }


def test_run_manifest_publishes_only_scope_and_public_base_map() -> None:
    staged = stage_run_manifest(
        {"project_id": "project", "ontology_id": "ontology", "build_session_id": "session"},
        public_map(),
        "input-manifest",
        "base-manifest",
    )
    encoded = json.dumps(staged)
    assert staged["contract_version"] == contract.CONTRACT_VERSION
    assert "answer-contract" not in encoded and "mutation-contract" not in encoded
    assert staged["permitted_locations"] == ["clarifications.jsonl", "semantic-package.json"]


def test_public_map_requires_both_exact_representations() -> None:
    invalid = public_map()
    invalid["workflow_class"] = {"resource_id": "class-workflow"}
    with pytest.raises(contract.ContractError, match="resource_iri"):
        contract.validate_public_resource_map(invalid)


def test_invalid_scope_is_rejected_before_agent_staging() -> None:
    with pytest.raises(HostError, match="run scope"):
        stage_run_manifest({"project_id": "p"}, public_map(), "input", "base")
