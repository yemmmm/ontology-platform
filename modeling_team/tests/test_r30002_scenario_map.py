"""R3.0-002 offline contract tests: scenario-map artifacts and frozen assets.

Covers test plan offline layers S1-S3: the pure scenario-map module (artifact
loading, closed structural validation, deterministic reason codes), the closed
tool-set extension, and the frozen Profile/Task/references assets.
"""

import json
from pathlib import Path

import pytest

from modeling_team import scenario_map
from modeling_team.contracts import (
    FORMAL_ROLE_VALUES,
    MULTI_SLICE_PROFILE_IDS,
    ROLE_VALUES,
    SAFE_PROTOCOL_TOOLS,
    SAFE_PROTOCOL_TOOLS_R23003,
    SAFE_PROTOCOL_TOOLS_R30002,
    SEMANTIC_PROTECTION_SET_TOOLS,
    TeamConfigurationError,
    load_formal_team_configuration,
    load_multi_slice_team_configuration,
    load_task,
    task_declares_multi_slice_workflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads(
    (
        REPO_ROOT / "modeling_team" / "tests" / "fixtures" / "r30002-scenario-map-fixtures.json"
    ).read_text(encoding="utf-8")
)

# The historical 21-tool allowlist, hard-coded so any silent change to
# SAFE_PROTOCOL_TOOLS itself (byte-compatibility guarantee) fails here.
HISTORICAL_SAFE_PROTOCOL_TOOLS = frozenset(
    {
        "check_platform_health",
        "get_project_build_context",
        "get_ontology_workspace_context",
        "create_build_session",
        "get_build_session",
        "save_build_checkpoint",
        "complete_build_session",
        "cancel_build_session",
        "acquire_ontology_lease",
        "renew_ontology_lease",
        "release_ontology_lease",
        "submit_modeling_batch",
        "get_modeling_batch",
        "list_session_modeling_batches",
        "list_ontology_modeling_batches",
        "get_modeling_context",
        "get_ontology_read_model",
        "query_semantic_context",
        "run_semantic_validation",
        "run_semantic_reasoning",
        "get_ontology_lineage",
        "inspect_semantic_statement_provenance",
    }
)
PROTECTION_SET_TOOL_NAMES = frozenset(
    {
        "list_semantic_protection_sets",
        "create_semantic_protection_set",
        "update_semantic_protection_set",
        "delete_semantic_protection_set",
        "add_semantic_protection_set_members",
        "remove_semantic_protection_set_members",
    }
)


def _issue_codes(issues):
    return tuple(issue.reason_code for issue in issues)


# --- S1: agent-readable references contract mirrors the module constants ---


def test_references_contract_matches_module_constants():
    references = json.loads(
        (
            REPO_ROOT
            / "modeling_team"
            / "references"
            / "r3-0-002-scenario-map-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert references["scenario_map"]["schema_version"] == scenario_map.SCENARIO_MAP_SCHEMA
    assert references["topology_decision"]["schema_version"] == (
        scenario_map.TOPOLOGY_DECISION_SCHEMA
    )
    assert references["protection_iri_suggestions"]["schema_version"] == (
        scenario_map.PROTECTION_IRI_SUGGESTIONS_SCHEMA
    )
    assert references["scenario_map"]["failure_reason_codes"] == list(
        scenario_map.MAP_REASON_CODES
    )
    assert references["topology_decision"]["gate_failure_reason_codes"] == list(
        scenario_map.TOPOLOGY_REASON_CODES
    )
    assert references["topology_decision"]["required_option_ids"] == list(
        scenario_map.TOPOLOGY_REQUIRED_OPTION_IDS
    )
    assert references["topology_decision"]["dimensions"] == list(
        scenario_map.TOPOLOGY_DIMENSIONS
    )
    assert references["artifact_locations"]["scenario_map"] == (
        scenario_map.SCENARIO_MAP_FILENAME
    )
    assert references["artifact_locations"]["topology_decision"] == (
        scenario_map.TOPOLOGY_DECISION_FILENAME
    )
    assert references["artifact_locations"]["protection_iri_suggestions"] == (
        scenario_map.PROTECTION_IRI_SUGGESTIONS_FILENAME
    )


def test_scenario_map_artifact_paths_are_run_workspace_locations(tmp_path):
    paths = scenario_map.scenario_map_artifact_paths(tmp_path)
    assert paths["scenario_map"] == tmp_path / "scenario-map" / "scenario-map.json"
    assert paths["topology_decision"] == tmp_path / "scenario-map" / "topology-decision.json"
    assert paths["protection_iri_suggestions"] == (
        tmp_path / "scenario-map" / "protection-iri-suggestions.json"
    )


# --- S1: artifact loading rejects missing, symlinked, non-JSON, non-object ---


@pytest.mark.parametrize(
    "loader,code",
    [
        (scenario_map.load_scenario_map, "map_unparsable"),
        (scenario_map.load_topology_decision, "topology_unparsable"),
        (
            scenario_map.load_protection_iri_suggestions,
            "suggestions_schema_mismatch",
        ),
    ],
)
def test_loaders_reject_missing_artifact(tmp_path, loader, code):
    with pytest.raises(scenario_map.ScenarioMapArtifactError) as excinfo:
        loader(tmp_path / "missing.json")
    assert excinfo.value.reason_code == code


def test_loaders_reject_symlinked_artifact(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(scenario_map.ScenarioMapArtifactError) as excinfo:
        scenario_map.load_topology_decision(link)
    assert excinfo.value.reason_code == "topology_unparsable"


def test_loaders_reject_non_json_and_non_object(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(scenario_map.ScenarioMapArtifactError) as excinfo:
        scenario_map.load_scenario_map(bad)
    assert excinfo.value.reason_code == "map_unparsable"
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(scenario_map.ScenarioMapArtifactError) as excinfo:
        scenario_map.load_scenario_map(array)
    assert excinfo.value.reason_code == "map_unparsable"


# --- S1: scenario-map structural validation ---


def test_valid_scenario_map_has_no_issues():
    assert scenario_map.validate_scenario_map(FIXTURES["scenario_map"]["valid"]) == ()


@pytest.mark.parametrize(
    "variant,expected_code",
    [
        ("missing_section", "map_missing_section"),
        ("schema_mismatch", "map_schema_mismatch"),
        ("dangling_dependency", "map_dangling_reference"),
        ("dangling_term_owner", "map_dangling_reference"),
        ("term_owner_not_unique", "map_term_owner_not_unique"),
        ("cq_spans_too_few", "map_schema_mismatch"),
        ("unknown_cq_span", "map_dangling_reference"),
    ],
)
def test_invalid_scenario_map_reports_expected_reason_code(variant, expected_code):
    issues = scenario_map.validate_scenario_map(FIXTURES["scenario_map"]["invalid"][variant])
    codes = _issue_codes(issues)
    assert codes, f"variant {variant} produced no issues"
    assert expected_code in codes
    assert set(codes) <= set(scenario_map.MAP_REASON_CODES)


# --- S1/F1: topology-decision structural validation ---


def test_valid_topology_decisions_have_no_issues():
    valid = FIXTURES["topology_decision"]["multi_ontology_plan_valid"]
    single = FIXTURES["topology_decision"]["single_ontology_selected_valid"]
    assert scenario_map.validate_topology_decision(valid) == ()
    # Selecting single_ontology never waives the three-option comparison.
    assert scenario_map.validate_topology_decision(single) == ()
    # R3.0-006 M3 registered revision: a non-single_ontology selection without
    # ontology_plan is no longer valid (topology_missing_ontology_plan).
    legacy = FIXTURES["topology_decision"]["valid"]
    codes = _issue_codes(scenario_map.validate_topology_decision(legacy))
    assert list(codes) == ["topology_missing_ontology_plan"]


@pytest.mark.parametrize(
    "variant,expected_code",
    [
        ("schema_mismatch", "topology_schema_mismatch"),
        ("insufficient_options", "topology_insufficient_options"),
        ("missing_required_option", "topology_missing_required_option"),
        ("missing_dimension", "topology_missing_dimension"),
        ("empty_dimension", "topology_empty_dimension"),
        ("missing_selection", "topology_missing_selection"),
        ("empty_rationale", "topology_empty_rationale"),
    ],
)
def test_invalid_topology_decision_reports_expected_reason_code(variant, expected_code):
    issues = scenario_map.validate_topology_decision(
        FIXTURES["topology_decision"]["invalid"][variant]
    )
    codes = _issue_codes(issues)
    assert codes, f"variant {variant} produced no issues"
    assert expected_code in codes
    assert set(codes) <= set(scenario_map.TOPOLOGY_REASON_CODES)


# --- S1/B: protection IRI suggestion handover (format only) ---


def test_valid_protection_suggestions_allow_dangling_iris():
    valid = FIXTURES["protection_iri_suggestions"]["valid"]
    slice_ids = {item["slice_id"] for item in FIXTURES["scenario_map"]["valid"]["slices"]}
    assert scenario_map.validate_protection_iri_suggestions(valid, slice_ids=slice_ids) == ()


@pytest.mark.parametrize(
    "variant,expected_code",
    [
        ("invalid_iri", "suggestions_invalid_iri"),
        ("invalid_target", "suggestions_invalid_target"),
    ],
)
def test_invalid_protection_suggestions_report_expected_reason_code(variant, expected_code):
    issues = scenario_map.validate_protection_iri_suggestions(
        FIXTURES["protection_iri_suggestions"]["invalid"][variant]
    )
    codes = _issue_codes(issues)
    assert codes, f"variant {variant} produced no issues"
    assert expected_code in codes
    assert set(codes) <= set(scenario_map.SUGGESTIONS_REASON_CODES)


def test_dangling_proposing_slice_is_reported_only_with_slice_ids():
    dangling = FIXTURES["protection_iri_suggestions"]["invalid"]["dangling_slice"]
    assert scenario_map.validate_protection_iri_suggestions(dangling) == ()
    issues = scenario_map.validate_protection_iri_suggestions(dangling, slice_ids={"S1"})
    assert _issue_codes(issues) == ("suggestions_dangling_slice",)


# --- S1: closed tool-set extension, SAFE_PROTOCOL_TOOLS byte-unchanged ---


def test_safe_protocol_tools_are_byte_unchanged():
    assert SAFE_PROTOCOL_TOOLS == HISTORICAL_SAFE_PROTOCOL_TOOLS - {"run_semantic_validation", "run_semantic_reasoning"}


def test_multi_slice_tool_superset_adds_only_protection_and_governed_scan_read():
    assert SEMANTIC_PROTECTION_SET_TOOLS == PROTECTION_SET_TOOL_NAMES
    assert SAFE_PROTOCOL_TOOLS_R30002 == (
        SAFE_PROTOCOL_TOOLS | PROTECTION_SET_TOOL_NAMES | {"semantic_sparql_query"}
    )
    assert not (SEMANTIC_PROTECTION_SET_TOOLS & SAFE_PROTOCOL_TOOLS)
    # The R2.3-003 superset is untouched by this requirement.
    assert SAFE_PROTOCOL_TOOLS_R23003 == SAFE_PROTOCOL_TOOLS | {
        "get_entity_statement_context"
    }


# --- S2/S3: frozen assets load through the multi-slice loader ---


REAL_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice.yaml"
SMOKE_TASK = REPO_ROOT / "modeling_team" / "tasks" / "r3-0-002-multi-slice-smoke.yaml"
PROFILE = REPO_ROOT / "modeling_team" / "profiles" / "r3-0-002-modeling-team.yaml"
INPUT_MANIFEST = (
    REPO_ROOT
    / "docs"
    / "evaluation-scenarios"
    / "industrial-service-v3"
    / "modeling-input"
    / "input-manifest.json"
)


@pytest.mark.parametrize("task_path", [REAL_TASK, SMOKE_TASK])
def test_multi_slice_assets_load_and_declare_the_parameter(task_path):
    assert task_declares_multi_slice_workflow(task_path) is True
    configuration = load_multi_slice_team_configuration(PROFILE, task_path)
    roles = {agent.package.role for agent in configuration.profile.agents}
    assert roles == {"coordinator", "modeling", "protocol"}
    assert configuration.profile.profile_id in MULTI_SLICE_PROFILE_IDS
    assert configuration.task.schema_version == 2
    assert configuration.task.parameters == {"multi_slice_workflow": True}


def test_multi_slice_real_task_role_sources_are_exactly_the_manifest_whitelist():
    configuration = load_multi_slice_team_configuration(PROFILE, REAL_TASK)
    manifest = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    allowed = {
        (
            REPO_ROOT
            / "docs"
            / "evaluation-scenarios"
            / "industrial-service-v3"
            / "modeling-input"
            / name
        ).resolve()
        for name in manifest["allowed_files"]
    }
    # R3.0-006 start2 narrow repair: role_sources now also stages the
    # platform/protocol reference contracts the frozen agent-package
    # instructions mandate (R2.3-005 formal-task staging precedent). The
    # business-input surface stays exactly the manifest whitelist; the extra
    # entries must all be declared reference contracts under
    # modeling_team/references/ and must never touch the parent directory.
    reference_contracts = {
        (
            REPO_ROOT / "modeling_team" / "references" / name
        ).resolve()
        for name in (
            "r3-0-002-scenario-map-contract.json",
            "platform-neutral-candidate-authoring.json",
            "modeling-batch-item-contract.json",
            "acceptance-stage-handoff-contract.json",
        )
    }
    mounted = {source.path.resolve() for source in configuration.task.role_sources}
    assert mounted == allowed | reference_contracts
    business_inputs = {
        path for path in mounted if "modeling-input" in path.parts
    }
    assert business_inputs == allowed
    assert "input-manifest.json" not in {
        path.name for path in mounted
    }


def test_multi_slice_real_task_permits_exactly_the_r30002_toolset():
    configuration = load_multi_slice_team_configuration(PROFILE, REAL_TASK)
    # The historical Task does not advertise the later R4.0-024 opt-in read.
    assert set(configuration.task.protocol_tools) == set(SAFE_PROTOCOL_TOOLS_R30002) - {
        "semantic_sparql_query"
    }


def test_multi_slice_profile_is_not_a_formal_profile():
    with pytest.raises(TeamConfigurationError):
        load_formal_team_configuration(PROFILE, REAL_TASK, root=REPO_ROOT)
    # The strict four-role contract is unchanged.
    assert FORMAL_ROLE_VALUES == {"coordinator", "modeling", "protocol", "acceptance"}
    assert ROLE_VALUES == {
        "coordinator",
        "modeling",
        "protocol",
        "source-specialist",
        "acceptance",
    }


@pytest.mark.parametrize(
    "task_name",
    [
        "r2-3-005-formal-acceptance.yaml",
        "r2-3-009-formal-acceptance.yaml",
        "base-capability-smoke.yaml",
    ],
)
def test_existing_tasks_do_not_declare_multi_slice_workflow(task_name):
    assert task_declares_multi_slice_workflow(
        REPO_ROOT / "modeling_team" / "tasks" / task_name
    ) is False


def test_multi_slice_loader_rejects_a_task_without_the_parameter(tmp_path):
    plain = tmp_path / "plain.yaml"
    plain.write_text(
        "\n".join(
            line
            for line in SMOKE_TASK.read_text(encoding="utf-8").splitlines()
            if not line.startswith("parameters:")
            and "multi_slice_workflow" not in line
            and not line.startswith("#")
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(TeamConfigurationError):
        load_multi_slice_team_configuration(PROFILE, plain, root=REPO_ROOT)


@pytest.mark.parametrize(
    "raw_parameters",
    [
        "not-a-dict",
        {},
        {"multi_slice_workflow": "true"},
        {"multi_slice_workflow": True, "extra_parameter": 1},
    ],
)
def test_task_parameters_extension_is_closed_and_boolean(tmp_path, raw_parameters):
    template = SMOKE_TASK.read_text(encoding="utf-8")
    body = "\n".join(
        line for line in template.splitlines() if not line.startswith("parameters:")
        and "multi_slice_workflow" not in line
        and not line.startswith("#")
    )
    task = tmp_path / "task.yaml"
    if isinstance(raw_parameters, str):
        rendered = f"{body}\nparameters: {raw_parameters}\n"
    else:
        rendered = (
            f"{body}\nparameters: {json.dumps(raw_parameters)}\n"
            if raw_parameters
            else f"{body}\nparameters: {{}}\n"
        )
    task.write_text(rendered, encoding="utf-8")
    with pytest.raises(TeamConfigurationError):
        load_task(task, root=REPO_ROOT)


# --- R3.0-006 execution-gap closure: ontology_plan slice sharing (G5) --------


def _shared_core_plan(slice_ids):
    """Shared-core-plus-domain plan where one slice is served by both entries."""

    return [
        {"name": "shared-core", "slice_ids": ["S1", "S2"]},
        {"name": "fault-domain", "slice_ids": ["S2", "S3"]},
    ]


def test_t_g5_1_shared_core_plan_allows_a_slice_in_two_ontologies():
    slice_ids = {"S1", "S2", "S3"}
    plan = _shared_core_plan(slice_ids)
    # The previously rejected overlap is now the registered shared-core shape.
    assert scenario_map._validate_ontology_plan(plan, slice_ids=slice_ids) == []
    decision = json.loads(
        json.dumps(FIXTURES["topology_decision"]["multi_ontology_plan_valid"])
    )
    decision["selected_option"] = "shared_core_plus_domain"
    decision["ontology_plan"] = plan
    assert scenario_map.validate_topology_decision(decision, slice_ids=slice_ids) == ()


def test_t_g5_2_existing_rejections_are_preserved():
    slice_ids = {"S1", "S2", "S3"}
    # Dangling slice reference stays rejected.
    issues = scenario_map._validate_ontology_plan(
        [{"name": "a", "slice_ids": ["S1"]}, {"name": "b", "slice_ids": ["S9"]}],
        slice_ids=slice_ids,
    )
    assert "topology_dangling_slice" in _issue_codes(issues)
    # Missing coverage of a scenario-map slice stays rejected, with the revised
    # "at least one" wording.
    issues = scenario_map._validate_ontology_plan(
        [{"name": "a", "slice_ids": ["S1"]}, {"name": "b", "slice_ids": ["S2"]}],
        slice_ids=slice_ids,
    )
    assert _issue_codes(issues) == ("topology_invalid_ontology_plan",)
    assert "at least one planned Ontology" in issues[0].detail
    # Single entry, duplicate name, empty and duplicated slice_ids stay rejected.
    assert _issue_codes(
        scenario_map._validate_ontology_plan([{"name": "a", "slice_ids": ["S1"]}], slice_ids=None)
    ) == ("topology_invalid_ontology_plan",)
    assert "topology_invalid_ontology_plan" in _issue_codes(
        scenario_map._validate_ontology_plan(
            [
                {"name": "a", "slice_ids": ["S1"]},
                {"name": "a", "slice_ids": ["S2"]},
            ],
            slice_ids=None,
        )
    )
    assert "topology_invalid_ontology_plan" in _issue_codes(
        scenario_map._validate_ontology_plan(
            [
                {"name": "a", "slice_ids": []},
                {"name": "b", "slice_ids": ["S1"]},
            ],
            slice_ids=None,
        )
    )
    assert "topology_invalid_ontology_plan" in _issue_codes(
        scenario_map._validate_ontology_plan(
            [
                {"name": "a", "slice_ids": ["S1", "S1"]},
                {"name": "b", "slice_ids": ["S2"]},
            ],
            slice_ids=None,
        )
    )


def test_t_g5_3_relaxation_is_pure_no_legacy_plan_regression():
    slice_ids = {item["slice_id"] for item in FIXTURES["scenario_map"]["valid"]["slices"]}
    valid = FIXTURES["topology_decision"]["multi_ontology_plan_valid"]
    # The frozen "every slice exactly one Ontology" plan is still legal.
    assert scenario_map._validate_ontology_plan(
        valid["ontology_plan"], slice_ids=slice_ids
    ) == []
    assert scenario_map.validate_topology_decision(valid, slice_ids=slice_ids) == ()


def test_t_g5_6_reference_contract_matches_the_relaxed_rule():
    references = json.loads(
        (
            REPO_ROOT
            / "modeling_team"
            / "references"
            / "r3-0-002-scenario-map-contract.json"
        ).read_text(encoding="utf-8")
    )
    rules = references["topology_decision"]["optional_fields"]["ontology_plan"]["rules"]
    joined = "\n".join(rules)
    assert "at least one planned Ontology" in joined
    assert "more than one planned Ontology" in joined
    assert "exactly one planned Ontology" not in joined
    # The rationale-free rule set is the only mounted wording, so no other
    # topology_decision rule re-introduces the exact-one requirement.
    for section in references["topology_decision"]["rules"]:
        assert "exactly one planned Ontology" not in section
