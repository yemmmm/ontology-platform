"""Active multiview contracts, submission bindings and recovery; no model provider starts."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.contracts import load_multi_slice_team_configuration, digest_file
from modeling_team.scenario_map import (
    MULTIVIEW_SCENARIO_MAP_SCHEMA,
    validate_scenario_map,
    collaboration_projection,
)
from modeling_team.runner import TeamRunner
from modeling_team.staged_decisions import (
    unified_candidate_issue,
    projection_digest,
    StagedSubmissionRejection,
)
from modeling_team.tests.test_r30002_runner_wiring import FIXTURES
from modeling_team.tests.test_r30009_runner_wiring import (
    _candidate,
    _projection,
    _batch_items,
    _open_platform_gate_unified,
    _unified_args,
)
from modeling_team.tests.test_r30008b_runner_wiring import _ForwarderRecorder

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "modeling_team/tasks/r4-0-012-tracing-suspension.yaml"
PROFILE = ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml"


def multiview_map():
    value = deepcopy(FIXTURES["scenario_map"]["valid"])
    value["schema_version"] = MULTIVIEW_SCENARIO_MAP_SCHEMA
    for item in value["slices"]:
        item["viewpoints"] = [
            dict(viewpoint="process", status="modeled", note="outline"),
            dict(viewpoint="rule", status="unknown", note="needs business answer"),
        ]
    for i, item in enumerate(value["shared_terms"]):
        item.update(
            definition_id=f"def-{i}",
            meaning_scope="shared closure action",
            status="confirmed",
            candidate_refs=[],
        )
    return value


def ref(candidate, item_id="item-entity"):
    return dict(
        candidate_id=candidate["candidate_id"], revision=candidate["revision"], item_id=item_id
    )


def review(value, candidate=None):
    return dict(
        definition_ids=[value["shared_terms"][0]["definition_id"]],
        before_refs=[],
        after_refs=[ref(candidate)] if candidate else [],
        coverage="incomplete",
        coverage_note="authorized scope; external consumers unresolved",
        references=[],
        outcome="deferred",
        reason="retain old contract; independent work continues",
    )


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_new_and_old_schema_dispatch_and_same_name_different_meanings():
    assert not validate_scenario_map(FIXTURES["scenario_map"]["valid"])
    value = multiview_map()
    other = deepcopy(value["shared_terms"][0])
    other.update(definition_id="different-meaning", meaning_scope="closing a financial period")
    value["shared_terms"].append(other)
    assert not validate_scenario_map(value)
    other["definition_id"] = value["shared_terms"][0]["definition_id"]
    assert any(i.reason_code == "map_term_owner_not_unique" for i in validate_scenario_map(value))
    value["schema_version"] = "r3-0-002-scenario-map/v1"
    assert validate_scenario_map(value)


@pytest.mark.parametrize(
    "mutation,path",
    [
        (
            lambda v: v["slices"][0]["viewpoints"].append(v["slices"][0]["viewpoints"][0]),
            "viewpoint",
        ),
        (lambda v: v["shared_terms"][0].update(owner_slice="absent"), "owner_slice"),
        (
            lambda v: v["shared_terms"][0].update(
                candidate_refs=[dict(candidate_id="c", revision=True, item_id="x")]
            ),
            "candidate_refs",
        ),
        (
            lambda v: v["shared_terms"][0].update(definition_id="urn:platform:identity"),
            "definition_id",
        ),
        (
            lambda v: v["adjustments"].append(
                dict(change="edit", approved_by_coordinator="coordinator", review={"bad": True})
            ),
            "review",
        ),
    ],
)
def test_fixable_errors_name_field_and_repair(mutation, path):
    original = multiview_map()
    broken = deepcopy(original)
    mutation(broken)
    assert any(path in i.detail for i in validate_scenario_map(broken))
    assert validate_scenario_map(original) == ()


def test_candidate_closure_stale_revision_historical_before_and_scoped_references(tmp_path):
    candidate = _candidate()
    value = multiview_map()
    value["scenario_id"] = candidate["scenario_id"]
    candidate["items"][0]["slice_ids"] = [value["slices"][0]["slice_id"]]
    value["shared_terms"][0]["candidate_refs"] = [ref(candidate)]
    change = review(value, candidate)
    change["references"] = [
        dict(
            **ref(candidate),
            slice_id=value["slices"][0]["slice_id"],
            result="unknown",
            note="unconfirmed required parameter",
        )
    ]
    value["adjustments"] = [
        dict(change="parameter revision", approved_by_coordinator="coordinator", review=change)
    ]
    directory = tmp_path / "stage3-neutral-graph/candidates"
    write_json(directory / "cand-1-r2.json", candidate)
    assert validate_scenario_map(value, run_root=tmp_path) == ()
    new = deepcopy(candidate)
    new["revision"] = 3
    write_json(directory / "cand-1-r3.json", new)
    assert any("stale" in i.detail for i in validate_scenario_map(value, run_root=tmp_path))
    change["before_refs"] = [ref(candidate)]
    change["after_refs"] = [ref(new)]
    change["references"][0]["revision"] = 3
    value["shared_terms"][0]["candidate_refs"] = [ref(new)]
    assert validate_scenario_map(value, run_root=tmp_path) == ()
    change["references"][0]["slice_id"] = value["slices"][1]["slice_id"]
    assert any("item scope" in i.detail for i in validate_scenario_map(value, run_root=tmp_path))
    value["shared_terms"][0]["candidate_refs"][0]["item_id"] = "missing"
    assert any(
        "candidate/item binding" in i.detail
        for i in validate_scenario_map(value, run_root=tmp_path)
    )


def test_runner_actual_active_inputs_and_blind_cq_scope():
    config = load_multi_slice_team_configuration(PROFILE, TASK)
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=config, protocol_context=None, gate_binding=None)
    runner._competency_questions = True
    for name in ("coordinator", "modeling", "protocol"):
        source = next(
            s
            for s in config.task.role_sources
            if s.path.name == "r4-0-007-scenario-map-contract.json" and name in s.roles
        )
        assert (
            json.loads(source.path.read_text())["scenario_map"]["schema_version"]
            == MULTIVIEW_SCENARIO_MAP_SCHEMA
        )
        assert f"/agent/home/sources/{source.relative_path.as_posix()}" in runner._task_text(name)
    assert "r4-0-007-scenario-map-contract.json" not in runner._task_text("competency-question")
    assert not any("acceptance-scenarios" in str(s.path) for s in config.task.role_sources)


def test_existing_binding_cannot_create_and_update_targets_match(tmp_path):
    candidate = _candidate()
    write_json(tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json", candidate)
    projection = _projection(candidate, _batch_items())
    issue = unified_candidate_issue(tmp_path, projection, check_existing_identity=True)
    assert issue.reason_code == "approval_content_mismatch"
    assert "existing identity cannot use create_entity" in issue.detail
    command = projection["items"][0]
    command["command_kind"] = "update_entity"
    command["payload"] = {
        "entity_iri": projection["identity_bindings"][0]["resource_iri"],
        "label": "shared closure",
    }
    assert unified_candidate_issue(tmp_path, projection, check_existing_identity=True) is None
    command["payload"]["entity_iri"] = "urn:wrong"
    assert (
        "target differs"
        in unified_candidate_issue(tmp_path, projection, check_existing_identity=True).detail
    )
    command["command_kind"] = "create_entity"
    projection["identity_bindings"][0].update(
        resource_iri=None, evidence_ref=None, receipt_ref="future-create-receipt"
    )
    assert unified_candidate_issue(tmp_path, projection, check_existing_identity=True) is None


def test_actual_active_runner_rejects_duplicate_create_before_forwarding(tmp_path):
    forwarder = _ForwarderRecorder()
    from modeling_team.tests.test_r30015_checkpoints import _CheckpointRunner, _freeze

    staged = _CheckpointRunner(TASK)
    staged.runner.staged_batch_forwarder = forwarder
    try:
        staged.prepare()
        _open_platform_gate_unified(staged)
        _freeze(staged.runner)
        plan_path = staged.run_root / "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
        plan = json.loads(plan_path.read_text())
        plan["projection"]["task_id"] = staged.runner.run.configuration.task.task_id
        plan["projection_digest"] = projection_digest(plan["projection"])
        write_json(plan_path, plan)
        with pytest.raises(
            StagedSubmissionRejection, match="existing identity cannot use create_entity"
        ):
            staged.runner._handle_staged_submit_modeling_batch(
                _unified_args(
                    _batch_items(), "stage3-neutral-graph/materialization-plans/plan-1-r1.json"
                )
            )
        assert forwarder.calls == []
        corrected = deepcopy(plan)
        command = corrected["projection"]["items"][0]
        command["command_kind"] = "update_entity"
        command["payload"] = {
            "entity_iri": corrected["projection"]["identity_bindings"][0]["resource_iri"],
            "label": "shared",
        }
        corrected["projection_digest"] = projection_digest(corrected["projection"])
        write_json(plan_path, corrected)
        accepted = staged.runner._handle_staged_submit_modeling_batch(
            _unified_args(
                corrected["projection"]["items"],
                "stage3-neutral-graph/materialization-plans/plan-1-r1.json",
            )
        )
        assert accepted["ok"] is True and len(forwarder.calls) == 1
    finally:
        staged.cleanup()


def test_scoped_projection_never_discloses_private_names_or_reference_counts():
    value = multiview_map()
    visible = value["shared_terms"][0]
    visible.update(
        status="conflict", candidate_refs=[dict(candidate_id="c", revision=1, item_id="a")]
    )
    private = deepcopy(visible)
    private.update(
        definition_id="SECRET",
        term="SECRET-NAME",
        candidate_refs=[dict(candidate_id="c", revision=1, item_id="b")],
    )
    value["shared_terms"].append(private)
    value["adjustments"] = [
        dict(change="secret change", approved_by_coordinator="coordinator", review=review(value))
    ]
    result = collaboration_projection(
        value,
        bindings={("c", 1, "a"): "urn:visible", ("c", 1, "b"): "urn:secret"},
        visible_iris={"urn:visible"},
    )
    assert result["definitions"] == [
        dict(
            definition_id=visible["definition_id"],
            resource_iri="urn:visible",
            status="conflict",
            reviews=[dict(coverage="incomplete", outcome="deferred")],
        )
    ]
    encoded = json.dumps(result)
    assert "SECRET" not in encoded and "urn:secret" not in encoded
    assert "references" not in encoded and "secret change" not in encoded
    assert "Omissions do not mean absence" in result["scope_note"]


@pytest.mark.parametrize("new", [True, False])
def test_active_save_restore_preserves_pending_reviews_and_legacy_schema(tmp_path, new):
    from modeling_team.tests.test_r30015_checkpoints import (
        _CheckpointRunner,
        _freeze,
        _read_manifest,
    )
    from modeling_team.checkpoint_recovery import restore_checkpoint_artifacts

    harness = _CheckpointRunner(TASK)
    try:
        runner = harness.prepare()
        value = multiview_map() if new else deepcopy(FIXTURES["scenario_map"]["valid"])
        if new:
            value["adjustments"] = [
                dict(
                    change="defer breaking change",
                    approved_by_coordinator="coordinator",
                    review=review(value),
                )
            ]
        path = runner.run.root / "scenario-map/scenario-map.json"
        write_json(path, value)
        original = path.read_bytes()
        _freeze(runner)
        manifest = _read_manifest(runner.run.root, "cq_frozen-0001")
        restore_checkpoint_artifacts(manifest, runner.run.root, tmp_path / "restored")
        restored = tmp_path / "restored/scenario-map/scenario-map.json"
        assert restored.read_bytes() == original
        assert validate_scenario_map(json.loads(restored.read_text())) == ()
        if new:
            assert (
                json.loads(restored.read_text())["adjustments"][0]["review"]["outcome"]
                == "deferred"
            )
            assert (
                json.loads(restored.read_text())["slices"][0]["owner"]
                == value["slices"][0]["owner"]
            )
    finally:
        harness.cleanup()


@pytest.mark.parametrize("created", [False, True])
def test_real_judge_assembly_includes_only_authorized_statuses(tmp_path, monkeypatch, created):
    from modeling_team.tests.test_r3012_partial_judging import (
        _write_run_root,
        _question,
        _production_handoff,
        _publish_handoff,
        _handoff_file,
        _DualForwarder,
        _platform_context,
        _run_cli,
        _batch_adapter,
    )

    root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    candidate = _candidate()
    value = multiview_map()
    value["scenario_id"] = candidate["scenario_id"]
    value["shared_terms"][0].update(candidate_refs=[ref(candidate)], status="unknown")
    value["adjustments"] = [
        dict(
            change="required parameter unresolved",
            approved_by_coordinator="coordinator",
            review=review(value, candidate),
        )
    ]
    write_json(root / "stage3-neutral-graph/candidates/cand-1-r2.json", candidate)
    projection = _projection(candidate, _batch_items())
    iri = "iri:1"
    if created:
        from modeling_team.protocol_mechanics import _platform_resource_iri

        projection["identity_bindings"][0].update(
            resource_iri=None, evidence_ref=None, receipt_ref="staged-decisions/receipt-1"
        )
        command = projection["items"][0]
        command["payload"]["entity_id"] = "shared-closure"
        iri = _platform_resource_iri("entity", "shared-closure")
    else:
        projection["identity_bindings"][0]["resource_iri"] = iri
    plan = dict(
        schema_version="r3-0-009-materialization-plan/v2",
        plan_id="plan-1",
        revision=1,
        projection=projection,
        projection_digest=projection_digest(projection),
    )
    write_json(root / "stage3-neutral-graph/materialization-plans/plan-1-r1.json", plan)
    # The plans directory also carries validated read evidence: a read-result
    # array and a non-plan object here must not abort the attempt before its
    # batch report is published (independent-CQ attempt regression).
    write_json(
        root / "stage3-neutral-graph/materialization-plans/read-evidence-1.json",
        [dict(question_id="cq-1", result=dict(ok=True, matches=[]))],
    )
    write_json(
        root / "stage3-neutral-graph/materialization-plans/read-evidence-2.json",
        dict(note="not a materialization plan"),
    )
    path = root / "scenario-map/scenario-map.json"
    write_json(path, value)
    handoff = _production_handoff(frozen)
    handoff["collaboration_artifact"] = dict(
        path="scenario-map/scenario-map.json", digest=digest_file(path)
    )
    _publish_handoff(root, handoff)
    result = {"ok": True, "matches": [{"id": "resource-1", "iri": iri}]}
    examiner = []
    adapter, state = _batch_adapter(
        result=result, on_examiner_packet=lambda p: examiner.append(p.to_dict()["payload"])
    )
    code = _run_cli(
        tmp_path,
        root,
        _handoff_file(tmp_path, handoff),
        _DualForwarder(_platform_context(), [result]),
        adapter,
        monkeypatch,
    )
    assert code == 0
    context = state["judge_payload"]["collaboration_context"]
    assert context["definitions"][0]["status"] == "unknown"
    assert context["definitions"][0]["reviews"] == [dict(coverage="incomplete", outcome="deferred")]
    assert "required parameter unresolved" not in json.dumps(context)
    assert "collaboration_context" not in examiner[0]
    from modeling_team.__main__ import _cq_collaboration_context

    assert _cq_collaboration_context(root, {})[0]["definitions"] == []
    path.write_text("{}")
    with pytest.raises(Exception, match="collaboration_binding_changed"):
        _cq_collaboration_context(root, {"cq-1": [{"result": result}]})


def _collaboration_run_root(tmp_path):
    """Minimal handoff-bound run root for ``_cq_collaboration_context``."""

    candidate = _candidate()
    value = multiview_map()
    value["scenario_id"] = candidate["scenario_id"]
    value["shared_terms"][0].update(candidate_refs=[ref(candidate)], status="unknown")
    write_json(tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json", candidate)
    projection = _projection(candidate, _batch_items())
    projection["identity_bindings"][0]["resource_iri"] = "iri:1"
    plan = dict(
        schema_version="r3-0-009-materialization-plan/v2",
        plan_id="plan-1",
        revision=1,
        projection=projection,
        projection_digest=projection_digest(projection),
    )
    write_json(tmp_path / "stage3-neutral-graph/materialization-plans/plan-1-r1.json", plan)
    path = tmp_path / "scenario-map/scenario-map.json"
    write_json(path, value)
    write_json(
        tmp_path / "acceptance-v3/production-handoff.json",
        dict(
            collaboration_artifact=dict(
                path="scenario-map/scenario-map.json", digest=digest_file(path)
            )
        ),
    )
    return plan


def test_collaboration_context_skips_non_plan_evidence_keeps_work_state(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context

    _collaboration_run_root(tmp_path)
    plans = tmp_path / "stage3-neutral-graph/materialization-plans"
    write_json(
        plans / "read-evidence-1.json",
        [dict(question_id="cq-1", result=dict(ok=True, matches=[dict(iri="iri:9")]))],
    )
    write_json(plans / "read-evidence-2.json", dict(note="not a materialization plan"))
    result = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"}]}

    context = _cq_collaboration_context(tmp_path, {"cq-1": [{"result": result}]})[0]
    assert context["definitions"] == [
        dict(definition_id="def-0", resource_iri="iri:1", status="unknown", reviews=[])
    ]
    assert "iri:9" not in json.dumps(context)
    assert _cq_collaboration_context(tmp_path, {})[0]["definitions"] == []


def test_invalid_ordinary_adjustment_is_ignored_with_judge_warning(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context

    _collaboration_run_root(tmp_path)
    path = tmp_path / "scenario-map/scenario-map.json"
    value = json.loads(path.read_text())
    # An outer closure/audit note is progress metadata, not a substantive map
    # adjustment.  It is intentionally malformed under the closed map schema.
    value["adjustments"] = ["outer closure audit note"]
    write_json(path, value)
    handoff_path = tmp_path / "acceptance-v3/production-handoff.json"
    handoff = json.loads(handoff_path.read_text())
    handoff["collaboration_artifact"]["digest"] = digest_file(path)
    write_json(handoff_path, handoff)
    original_map = path.read_bytes()
    original_handoff = handoff_path.read_bytes()

    context, warnings = _cq_collaboration_context(
        tmp_path, {"cq-1": [{"result": {"iri": "iri:1"}}]}
    )

    assert context["definitions"] == [dict(
        definition_id="def-0", resource_iri="iri:1", status="unknown", reviews=[]
    )]
    assert warnings == [{
        "warning": "collaboration_progress_invalid",
        "reason_code": "map_schema_mismatch",
        "detail": "adjustments[0]: fields",
    }]
    # The handoff-bound source artifacts remain byte-identical; only the Judge
    # work copy omits the malformed progress entry.
    assert path.read_bytes() == original_map
    assert handoff_path.read_bytes() == original_handoff


def _superseded_review_run_root(tmp_path, stale_fields):
    plan = _collaboration_run_root(tmp_path)
    path = tmp_path / "scenario-map/scenario-map.json"
    value = json.loads(path.read_text())
    candidate = json.loads((tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json").read_text())
    candidate["items"][0]["slice_ids"] = [value["slices"][0]["slice_id"]]
    write_json(tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json", candidate)
    historical = review(value, candidate)
    historical.update(coverage="complete", outcome="ready")
    historical["references"] = [dict(
        **ref(candidate), slice_id=candidate["items"][0]["slice_ids"][0],
        result="unchanged", note="historical reference",
    )]
    value["adjustments"] = [dict(
        change="historical review", approved_by_coordinator="coordinator", review=historical,
    )]
    current = deepcopy(candidate)
    current["revision"] += 1
    write_json(tmp_path / "stage3-neutral-graph/candidates/cand-1-r3.json", current)
    value["shared_terms"][0]["candidate_refs"] = [ref(current)]
    for field in ("after_refs", "references"):
        if field not in stale_fields:
            historical[field][0]["revision"] = current["revision"]
    plan["projection"]["candidate_revision"] = current["revision"]
    plan["projection_digest"] = projection_digest(plan["projection"])
    write_json(tmp_path / "stage3-neutral-graph/materialization-plans/plan-1-r1.json", plan)
    write_json(path, value)
    write_json(tmp_path / "acceptance-v3/production-handoff.json", dict(
        collaboration_artifact=dict(path="scenario-map/scenario-map.json", digest=digest_file(path)),
    ))
    original = path.read_bytes()
    handoff = (tmp_path / "acceptance-v3/production-handoff.json").read_bytes()
    issues = validate_scenario_map(value, run_root=tmp_path)
    assert len(issues) == len(stale_fields)
    assert all(issue.detail.endswith(".revision: stale") for issue in issues)
    return path, value, original, handoff


@pytest.mark.parametrize("stale_fields", [("after_refs",), ("references",), ("after_refs", "references")])
def test_collaboration_context_omits_superseded_reviews_without_editing_bound_map(
    tmp_path, stale_fields
):
    from modeling_team.__main__ import _cq_collaboration_context

    path, value, original, handoff = _superseded_review_run_root(tmp_path, stale_fields)

    context = _cq_collaboration_context(tmp_path, {"cq-1": [{"result": {"iri": "iri:1"}}]})[0]

    assert context["definitions"] == [dict(
        definition_id="def-0", resource_iri="iri:1", status="unknown", reviews=[],
    )]
    assert "superseded" in context["scope_note"]
    assert path.read_bytes() == original
    assert (tmp_path / "acceptance-v3/production-handoff.json").read_bytes() == handoff
    assert _cq_collaboration_context(tmp_path, {})[0]["definitions"] == []


@pytest.mark.parametrize("defect", ["missing_candidate", "wrong_item", "slice_scope", "schema", "shared_stale"])
def test_superseded_review_does_not_bypass_other_map_binding_errors(tmp_path, defect):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError

    path, value, _, _ = _superseded_review_run_root(tmp_path, ("after_refs", "references"))
    historical = value["adjustments"][0]["review"]
    if defect == "missing_candidate":
        historical["after_refs"][0]["candidate_id"] = "missing"
    elif defect == "wrong_item":
        historical["after_refs"][0]["item_id"] = "missing"
    elif defect == "slice_scope":
        historical["references"][0]["slice_id"] = value["slices"][1]["slice_id"]
    elif defect == "schema":
        historical["coverage"] = "invalid"
    else:
        value["shared_terms"][0]["candidate_refs"][0]["revision"] = 2
    write_json(path, value)
    write_json(tmp_path / "acceptance-v3/production-handoff.json", dict(
        collaboration_artifact=dict(path="scenario-map/scenario-map.json", digest=digest_file(path)),
    ))
    with pytest.raises(TeamConfigurationError, match="invalid scenario map"):
        _cq_collaboration_context(tmp_path, {"cq-1": [{"result": {"iri": "iri:1"}}]})


def _stale_shared_terms_run_root(tmp_path):
    """Handoff-bound map whose only defects are shared_terms candidate refs."""

    _collaboration_run_root(tmp_path)
    path = tmp_path / "scenario-map/scenario-map.json"
    value = json.loads(path.read_text())
    candidate = json.loads(
        (tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json").read_text()
    )
    newer = deepcopy(candidate)
    newer["revision"] = 3
    write_json(tmp_path / "stage3-neutral-graph/candidates/cand-1-r3.json", newer)
    value["shared_terms"][0]["candidate_refs"] = [
        ref(candidate),
        dict(
            candidate_id=candidate["candidate_id"], revision=candidate["revision"],
            item_id="missing-item",
        ),
    ]
    write_json(path, value)
    write_json(tmp_path / "acceptance-v3/production-handoff.json", dict(
        collaboration_artifact=dict(
            path="scenario-map/scenario-map.json", digest=digest_file(path),
        ),
    ))
    original = path.read_bytes()
    handoff = (tmp_path / "acceptance-v3/production-handoff.json").read_bytes()
    issues = validate_scenario_map(value, run_root=tmp_path)
    assert [issue.detail for issue in issues] == [
        "shared_terms[0].candidate_refs[0].revision: stale",
        "shared_terms[0].candidate_refs[1]: candidate/item binding",
    ]
    return path, original, handoff


def test_stale_shared_terms_refs_accepted_as_warnings_when_binding_stable(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError

    path, original, handoff = _stale_shared_terms_run_root(tmp_path)
    result = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"}]}

    # Unknown model binding drift keeps the original fail-closed hard failure.
    with pytest.raises(
        TeamConfigurationError, match="collaboration_binding_changed: invalid scenario map"
    ):
        _cq_collaboration_context(tmp_path, {"cq-1": [{"result": result}]})

    context, warnings = _cq_collaboration_context(
        tmp_path, {"cq-1": [{"result": result}]}, model_binding_stable=True
    )
    # The untrusted references are omitted from the Judge's work copy, so the
    # term establishes no visible binding; the omission is disclosed, and the
    # warning carries the exact entry locations for the retained report.
    assert context["definitions"] == []
    assert "untrusted" in context["scope_note"]
    assert [item["detail"] for item in warnings] == [
        "shared_terms[0].candidate_refs[0].revision: stale",
        "shared_terms[0].candidate_refs[1]: candidate/item binding",
    ]
    assert all(
        item["warning"] == "collaboration_metadata_stale"
        and item["reason_code"] == "map_dangling_reference"
        for item in warnings
    )
    # The handoff-bound source map and handoff stay immutable.
    assert path.read_bytes() == original
    assert (tmp_path / "acceptance-v3/production-handoff.json").read_bytes() == handoff


def test_stale_shared_terms_digest_mismatch_still_hard_fails(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError

    path, _original, _handoff = _stale_shared_terms_run_root(tmp_path)
    value = json.loads(path.read_text())
    value["slices"][0]["viewpoints"][0]["note"] = "post-handoff edit"
    write_json(path, value)
    with pytest.raises(
        TeamConfigurationError,
        match="collaboration_binding_changed: handoff content changed",
    ):
        _cq_collaboration_context(
            tmp_path, {"cq-1": [{"result": {"iri": "iri:1"}}]}, model_binding_stable=True
        )


@pytest.mark.parametrize("defect", ["candidate_unavailable", "schema_drift"])
def test_other_map_binding_errors_still_hard_fail_with_stable_binding(tmp_path, defect):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError

    path, _original, _handoff = _stale_shared_terms_run_root(tmp_path)
    if defect == "candidate_unavailable":
        (tmp_path / "stage3-neutral-graph/candidates/cand-1-r2.json").unlink()
    else:
        # Rebind the handoff digest so the digest gate stays satisfied and the
        # failure isolates the map's own structural contract.
        path.write_text("{}")
        write_json(tmp_path / "acceptance-v3/production-handoff.json", dict(
            collaboration_artifact=dict(
                path="scenario-map/scenario-map.json", digest=digest_file(path),
            ),
        ))
    with pytest.raises(
        TeamConfigurationError, match="collaboration_binding_changed: invalid scenario map"
    ):
        _cq_collaboration_context(
            tmp_path, {"cq-1": [{"result": {"iri": "iri:1"}}]}, model_binding_stable=True
        )


def test_judge_starts_on_stale_shared_terms_and_records_report_warning(
    tmp_path, monkeypatch
):
    from modeling_team.tests.test_r3012_partial_judging import (
        _write_run_root,
        _question,
        _production_handoff,
        _publish_handoff,
        _handoff_file,
        _DualForwarder,
        _platform_context,
        _run_cli,
        _batch_adapter,
    )

    root, frozen = _write_run_root(tmp_path, [_question("cq-1")])
    candidate = _candidate()
    value = multiview_map()
    value["scenario_id"] = candidate["scenario_id"]
    value["shared_terms"][0].update(candidate_refs=[ref(candidate)], status="unknown")
    write_json(root / "stage3-neutral-graph/candidates/cand-1-r2.json", candidate)
    newer = deepcopy(candidate)
    newer["revision"] = 3
    write_json(root / "stage3-neutral-graph/candidates/cand-1-r3.json", newer)
    value["shared_terms"][0]["candidate_refs"].append(
        dict(
            candidate_id=candidate["candidate_id"], revision=candidate["revision"],
            item_id="missing-item",
        )
    )
    projection = _projection(candidate, _batch_items())
    projection["identity_bindings"][0]["resource_iri"] = "iri:1"
    plan = dict(
        schema_version="r3-0-009-materialization-plan/v2",
        plan_id="plan-1",
        revision=1,
        projection=projection,
        projection_digest=projection_digest(projection),
    )
    write_json(root / "stage3-neutral-graph/materialization-plans/plan-1-r1.json", plan)
    path = root / "scenario-map/scenario-map.json"
    write_json(path, value)
    handoff = _production_handoff(frozen)
    handoff["collaboration_artifact"] = dict(
        path="scenario-map/scenario-map.json", digest=digest_file(path)
    )
    _publish_handoff(root, handoff)
    original_map = path.read_bytes()
    result = {"ok": True, "matches": [{"id": "resource-1", "iri": "iri:1"}]}
    adapter, state = _batch_adapter(result=result)
    code = _run_cli(
        tmp_path,
        root,
        _handoff_file(tmp_path, handoff),
        _DualForwarder(_platform_context(), [result]),
        adapter,
        monkeypatch,
    )
    assert code == 0
    report = json.loads(
        (
            root / "acceptance-v3" / "reports" / frozen["batch_id"]
            / "attempt-0001" / "batch-report.json"
        ).read_text(encoding="utf-8")
    )
    # The Judge started and judged; the stale metadata is a recorded warning,
    # never a lifecycle error or a full-pass gate.
    assert report["sessions"]["acceptance_judge"]["verdicts"] == 1
    assert [item["detail"] for item in report["sessions"]["lifecycle_warnings"]] == [
        "shared_terms[0].candidate_refs[0].revision: stale",
        "shared_terms[0].candidate_refs[1]: candidate/item binding",
    ]
    assert all(
        item["stage"] == "acceptance-judge-setup"
        and item["warning"] == "collaboration_metadata_stale"
        for item in report["sessions"]["lifecycle_warnings"]
    )
    assert report["sessions"]["lifecycle_errors"] == []
    assert report["full_pass"] is True
    # The Judge's work copy discloses the omitted references as untrusted.
    context = state["judge_payload"]["collaboration_context"]
    assert context["definitions"] == []
    assert "untrusted" in context["scope_note"]
    # The handoff-bound source map stays immutable.
    assert path.read_bytes() == original_map


def test_collaboration_context_keeps_plan_parse_and_identity_guards(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError
    from modeling_team.staged_decisions import StagedDecisionArtifactError

    plan = _collaboration_run_root(tmp_path)
    plans = tmp_path / "stage3-neutral-graph/materialization-plans"
    broken = plans / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(StagedDecisionArtifactError, match="missing_candidate_reference"):
        _cq_collaboration_context(tmp_path, {})
    broken.unlink()
    second = deepcopy(plan)
    second["plan_id"] = "plan-2"
    second["projection"]["identity_bindings"][0]["resource_iri"] = "iri:2"
    second["projection_digest"] = projection_digest(second["projection"])
    write_json(plans / "plan-2-r1.json", second)
    visible = {"cq-1": [{"result": {"ok": True, "matches": [{"iri": "iri:1"}, {"iri": "iri:2"}]}}]}
    with pytest.raises(TeamConfigurationError, match="identity conflict"):
        _cq_collaboration_context(tmp_path, visible)


def test_ordinary_prepare_cannot_import_fork_membership_authorization(tmp_path):
    from modeling_team.tests.test_r30015_checkpoints import _CheckpointRunner

    harness = _CheckpointRunner(TASK)
    try:
        harness.runner.prepare(
            run_id=harness.run_id,
            profile_path=PROFILE,
            task_path=TASK,
            scope={"mode": "create", "fork_created_by_run": harness.run_id},
        )
        assert "fork_created_by_run" not in harness.runner.run.scope
    finally:
        harness.cleanup()


def test_progress_note_change_after_handoff_still_rejects_digest_drift(tmp_path):
    from modeling_team.__main__ import _cq_collaboration_context
    from modeling_team.contracts import TeamConfigurationError

    _collaboration_run_root(tmp_path)
    path = tmp_path / "scenario-map/scenario-map.json"
    original = path.read_bytes()
    assert _cq_collaboration_context(tmp_path, {})[0]["definitions"] == []
    value = json.loads(original)
    value["slices"][0]["viewpoints"][0]["note"] = "Updated current coverage only"
    assert validate_scenario_map(value, run_root=tmp_path) == ()
    write_json(path, value)
    with pytest.raises(TeamConfigurationError, match="collaboration_binding_changed"):
        _cq_collaboration_context(tmp_path, {})
    path.write_bytes(original)
    assert _cq_collaboration_context(tmp_path, {})[0]["definitions"] == []


def test_emergency_save_restores_stale_progress_and_current_candidate_without_editing_source(tmp_path):
    from modeling_team.tests.test_r30015_checkpoints import (
        _CheckpointRunner,
        _outer_save,
        _read_manifest,
    )
    from modeling_team.checkpoint_recovery import restore_checkpoint_artifacts

    from modeling_team.checkpoints import CHECKPOINT_KIND_SEMANTIC_APPROVED
    from modeling_team.staged_decisions import staged_decision_artifact_paths
    from modeling_team.tests.test_r30009_runner_wiring import _unified_approvals

    harness = _CheckpointRunner(TASK)
    try:
        runner = harness.prepare()
        candidate = _candidate()
        value = multiview_map()
        value["scenario_id"] = candidate["scenario_id"]
        value["slices"][0]["viewpoints"][0].update(
            status="pending", note="Analysis done; candidate r1 historical; current revision unchecked"
        )
        candidate_relative = "stage3-neutral-graph/candidates/cand-1-r2.json"
        map_relative = "scenario-map/scenario-map.json"
        write_json(runner.run.root / candidate_relative, candidate)
        write_json(runner.run.root / map_relative, value)
        original_map = (runner.run.root / map_relative).read_bytes()
        original_candidate = (runner.run.root / candidate_relative).read_bytes()
        paths = staged_decision_artifact_paths(runner.run.root, unified=True)
        write_json(paths["approvals"], _unified_approvals(candidate))
        record = _outer_save(runner, CHECKPOINT_KIND_SEMANTIC_APPROVED)
        assert record["status"] == "saved"
        manifest = _read_manifest(runner.run.root, record["checkpoint_id"])
        restored_root = tmp_path / "restored"
        restore_checkpoint_artifacts(manifest, runner.run.root, restored_root)
        assert (restored_root / map_relative).read_bytes() == original_map
        assert (restored_root / candidate_relative).read_bytes() == original_candidate
        # Production can update its working copy; the published source stays immutable.
        restored = json.loads((restored_root / map_relative).read_text())
        restored["slices"][0]["viewpoints"][0].update(
            status="modeled", note="cand-1 revision 2 / item-entity; partial expression; review pending"
        )
        write_json(restored_root / map_relative, restored)
        assert validate_scenario_map(restored, run_root=restored_root) == ()
        assert (runner.run.root / map_relative).read_bytes() == original_map
        assert (runner.run.root / candidate_relative).read_bytes() == original_candidate
    finally:
        harness.cleanup()
