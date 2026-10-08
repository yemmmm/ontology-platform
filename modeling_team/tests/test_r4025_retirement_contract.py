"""Current role catalogs and private handoff schemas follow the retired engine boundary."""
import json

from modeling_team.acceptance import MODELING_STAGES, CHECK_KEYS, canonical_platform_allowlist
from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS, examiner_proxy_schemas
from modeling_team.capability_mcp import CAPABILITY_TOOL_SCHEMAS
from modeling_team.contracts import load_task, repository_root
from modeling_team.protocol_mcp_launch import protocol_mcp_launch_spec


RETIRED = {"run_semantic_validation", "run_semantic_reasoning",
           "list_semantic_validation_runs", "get_semantic_validation_run",
           "list_semantic_reasoning_runs", "get_semantic_reasoning_run",
           "list_semantic_derived_pointers", "check_semantic_staleness"}


def test_actual_current_catalogs_and_explicit_handoff_schema_retire_engines():
    assert MODELING_STAGES == ("dry-run", "apply", "readback")
    assert "validation_reasoning" not in CHECK_KEYS
    assert "deterministic_write_readback" in CHECK_KEYS
    assert RETIRED.isdisjoint(canonical_platform_allowlist())
    assert RETIRED.isdisjoint(PLATFORM_PROXY_READ_TOOLS)
    assert RETIRED.isdisjoint(examiner_proxy_schemas())
    schema = CAPABILITY_TOOL_SCHEMAS["protocol_build_acceptance_stage_handoff"]
    calls = schema["properties"]["stage_calls"]
    assert tuple(calls["properties"]) == MODELING_STAGES
    assert calls["required"] == list(MODELING_STAGES)
    assert calls["additionalProperties"] is False
    root = repository_root()
    for path in (root / "modeling_team/tasks").glob("*.yaml"):
        task = load_task(path, root=root)
        assert RETIRED.isdisjoint(task.protocol_tools), path
    spec = protocol_mcp_launch_spec(frozenset({"submit_modeling_batch"}))
    assert not hasattr(spec, "reasoner_env")
    assert "SEMANTIC_REASONER_COMMAND" not in dict(spec.hardening_env)
    assert not (root / "backend/scripts/dev_owl_reasoner.py").exists()


def test_current_candidate_contracts_have_no_shape_or_script_requirements():
    root = repository_root() / "modeling_team/references"
    batch = json.loads((root / "modeling-batch-item-contract.json").read_text())
    for section in ("create_payloads", "update_payloads"):
        assert not any(command.endswith("_shape") for command in batch[section])
        assert all("rule_definition" not in payload["fields"] for payload in batch[section].values())
    assert "shape_constraint" not in batch
    assert "semantic_validation_invocation_contract" not in batch
    neutral = json.loads((root / "platform-neutral-candidate-authoring.json").read_text())
    assert not any(item["item_kind"] in {"shape", "negative_probe"}
                   for item in neutral["example_candidate"]["items"])
    for stem in ("r2-3-003", "r2-3-005", "r2-3-008"):
        historical = json.loads((root / f"{stem}-acceptance-standard.json").read_text())
        current = json.loads((root / f"{stem}-acceptance-standard-v2.json").read_text())
        assert historical["schema_version"].endswith("/v1")
        assert "validation_reasoning" in historical["checks"]
        assert current["schema_version"].endswith("/v2")
        assert current["checks"] == list(CHECK_KEYS)
        assert current["competency_questions"] == historical["competency_questions"]
