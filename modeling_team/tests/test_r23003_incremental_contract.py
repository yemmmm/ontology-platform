from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from modeling_team import runner as runner_module
from modeling_team import preflight as preflight_module
from modeling_team.candidate_progress import FormalCandidateProgress, formal_candidate_digests
from modeling_team.contracts import TeamConfigurationError
from modeling_team.formal_runs import load_formal_run_configuration
from modeling_team.model_routing import load_team_model_profile
from modeling_team.platform_scope import PlatformScope
from modeling_team.proof_v2 import canonical_digest
from modeling_team.preflight import (
    R2_3_003_HANDOFF_RELATIVE,
    R2_3_003_ONTOLOGY_ID,
    R2_3_003_PROJECT_ID,
    load_existing_scope_handoff,
    normalize_existing_scope,
    canonical_existing_scope_preflight,
    run_existing_scope_preflight,
)
from modeling_team.protocol_mechanics import (
    ProtocolRetrievalFallbackError,
    build_existing_entity_binding_receipt,
    translate_candidate_to_batches,
)
from modeling_team.r23003_contract import build_delete_impact_receipt
from modeling_team.start_ledger import StartLedger
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.transport_mcp import TeamTransportBroker, mcp_response


ROOT = Path(__file__).resolve().parents[2]
SCOPE = {
    "mode": "existing",
    "project_id": R2_3_003_PROJECT_ID,
    "ontology_id": R2_3_003_ONTOLOGY_ID,
    "handoff_path": R2_3_003_HANDOFF_RELATIVE,
}


def test_issue_abort_zero_mutation_terminal_failure_unlocks_next_r23003_reservation(tmp_path: Path) -> None:
    """A cleanup-only abort is a retryable failure, never an implicit semantic PASS."""

    now = datetime(2026, 8, 11, 5, 0, tzinfo=UTC)
    ledger = StartLedger(tmp_path, requirement_id="R2.3-003", now=lambda: now)
    ledger.initial_authorization()
    freeze = now.isoformat()
    ledger.reserve("r23003-start7-fixture", "baseline-start7", freeze)
    ledger.mark_semantic_start("r23003-start7-fixture")
    evidence = {
        "run_id": "r23003-start7-fixture",
        "baseline_hash": "baseline-start7",
        "classification": "platform-contract",
        "mutation_state": "zero-mutation",
        "issue_id": "issue-1",
        "evidence_path": "evidence/terminal-reconciliation.jsonl",
        "evidence_digest": "a" * 64,
    }
    ledger.terminal_failure(
        "r23003-start7-fixture",
        "platform-contract",
        False,
        terminal_evidence=evidence,
    )
    ledger.reserve("r23003-start8-fixture", "baseline-start8", freeze)
    records = ledger._records()
    assert records[-1]["event"] == "reservation"
    assert any(
        record.get("event") == "terminal_failure"
        and record.get("run_id") == "r23003-start7-fixture"
        and record.get("terminal_evidence", {}).get("mutation_state") == "zero-mutation"
        for record in records
    )


def test_runner_issue_abort_reconciliation_appends_bound_terminal_failure(tmp_path: Path) -> None:
    now = datetime(2026, 8, 11, 5, 0, tzinfo=UTC)
    ledger = StartLedger(tmp_path / "ledger", requirement_id="R2.3-003", now=lambda: now)
    ledger.initial_authorization()
    ledger.reserve("r23003-run", "baseline-run", now.isoformat())
    ledger.mark_semantic_start("r23003-run")
    run_root = tmp_path / "run"
    (run_root / "evidence").mkdir(parents=True)
    runner = object.__new__(runner_module.TeamRunner)
    runner.run = SimpleNamespace(
        run_id="r23003-run",
        root=run_root,
        baseline_hash="baseline-run",
        configuration=SimpleNamespace(
            task=SimpleNamespace(task_id="r2-3-003-existing-scope-incremental", schema_version=2),
            profile=SimpleNamespace(profile_id="r2-3-003-modeling-team"),
        ),
    )
    runner._ledger = ledger
    runner._issue_abort_terminal_failure_recorded = False
    issue = SimpleNamespace(
        run_id="r23003-run",
        issue_id="issue-1",
        mutation_state="zero-mutation; only read-only platform calls",
        failing_operation="existing binding",
        error="Workflow vs InvokingWorkflow",
    )
    cleanup = {
        "acceptance": {"status": "aborted", "zero_child_residue": True},
        "scope": {
            "no_in_flight_attempts": True,
            "existing_context_before": {"workspace_version": "workspace-v1"},
            "existing_context_after": {"workspace_version": "workspace-v1"},
        },
    }
    runner._record_issue_abort_terminal_failure(issue, cleanup)
    terminal = [record for record in ledger._records() if record.get("event") == "terminal_failure"]
    assert len(terminal) == 1
    assert terminal[0]["terminal_evidence"]["baseline_hash"] == "baseline-run"
    assert terminal[0]["terminal_evidence"]["mutation_state"] == "zero-mutation"
    ledger.reserve("r23003-next", "baseline-next", now.isoformat())


def test_issue_abort_reconciliation_rejects_nonzero_mutation_state_without_ledger_write(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 11, 5, 0, tzinfo=UTC)
    ledger = StartLedger(tmp_path / "ledger", requirement_id="R2.3-003", now=lambda: now)
    ledger.initial_authorization()
    ledger.reserve("r23003-run", "baseline-run", now.isoformat())
    ledger.mark_semantic_start("r23003-run")
    runner = object.__new__(runner_module.TeamRunner)
    runner.run = SimpleNamespace(
        run_id="r23003-run",
        root=tmp_path / "run",
        baseline_hash="baseline-run",
        configuration=SimpleNamespace(
            task=SimpleNamespace(task_id="r2-3-003-existing-scope-incremental", schema_version=2),
            profile=SimpleNamespace(profile_id="r2-3-003-modeling-team"),
        ),
    )
    runner._ledger = ledger
    runner._issue_abort_terminal_failure_recorded = False
    issue = SimpleNamespace(
        run_id="r23003-run",
        issue_id="issue-1",
        mutation_state="mutation-started",
        failing_operation="existing binding",
        error="write may have occurred",
    )
    cleanup = {
        "acceptance": {"status": "aborted", "zero_child_residue": True},
        "scope": {"no_in_flight_attempts": True},
    }
    with pytest.raises(TeamConfigurationError, match="zero-mutation"):
        runner._record_issue_abort_terminal_failure(issue, cleanup)
    assert not [record for record in ledger._records() if record.get("event") == "terminal_failure"]


def _candidate() -> dict:
    return {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": 1,
        "scope": "retained",
        "constraints": ["source-grounded"],
        "items": [
            {
                "item_id": "rel",
                "item_kind": "predicate",
                "semantic": {
                    "predicate": "related_to",
                    "domain": "Review",
                    "range": "Review",
                    "predicate_kind": "relation",
                },
            },
            {
                "item_id": "existing",
                "item_kind": "existing_entity_ref",
                "semantic": {
                    "semantic_id": "review-001",
                    "expected_class": "Review",
                },
            },
            {
                "item_id": "relation",
                "item_kind": "relation",
                "semantic": {
                    "subject": {
                        "existing_entity_ref": {
                            "semantic_id": "review-001",
                            "expected_class": "Review",
                        }
                    },
                    "predicate": "related_to",
                    "object": {
                        "existing_entity_ref": {
                            "semantic_id": "review-001",
                            "expected_class": "Review",
                        }
                    },
                },
            },
            {
                "item_id": "delete-unknown-a",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-cross-release-output-meaning",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
            {
                "item_id": "delete-unknown-b",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": "unknown-b-no-score-behavior",
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            },
        ],
    }


def test_runner_validator_allows_only_bound_post_receipt_revision_via_broker(
    tmp_path: Path,
) -> None:
    """A 003 receipt-v1 conflict opens exactly one bound full-revision slot."""

    runner = runner_module.TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=SimpleNamespace())
    runner._is_r23003_modeling_run = lambda: True
    runner._formal_coordination_role_ids = lambda: {"modeling": "modeling", "protocol": "protocol"}
    runner._modeling_context_gate = runner_module.ModelingContextGate(
        run_id="run-r23003", project_id="P", ontology_id="O"
    )
    runner._modeling_context_gate.observe(
        {"ok": True, "data": {
            "project": {"id": "P"},
            "ontology": {"id": "O"},
            "workspace": {"state": "ready", "workspace_version": "v1", "issues": []},
            "resource_counts": {"classes": 1},
            "derived_state": {"stale_count": 0, "warning": None},
        }},
        call_receipt={"ordinal": 0},
    )
    progress = FormalCandidateProgress(clock=lambda: 0.0, allow_post_receipt_revision=True)
    runner._candidate_progress = progress
    broker = TeamTransportBroker(
        tmp_path / "broker",
        {("modeling", "protocol"), ("protocol", "modeling")},
        pre_send_validator=runner._validate_modeling_transport_send,
    )

    candidate = _candidate()
    initial = broker.send("modeling", "protocol", json.dumps(candidate), expects_reply=True)
    assert progress.observe_delivery(
        initial,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-r23003",
        protocol_thread_id="protocol-thread",
    ) == "candidate"
    candidate_digest, semantic_digest = formal_candidate_digests(candidate)
    receipt_value = {
        "status": "accepted",
        "candidate_revision": candidate["candidate_revision"],
        "semantic_digest": semantic_digest,
        "candidate_digest": candidate_digest,
    }
    receipt = broker.send(
        "protocol",
        "modeling",
        json.dumps(receipt_value),
        expects_reply=True,
        reply_to_delivery_id=initial.delivery_id,
    )
    assert progress.observe_delivery(
        receipt,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-r23003",
        protocol_thread_id="protocol-thread",
    ) == "accepted"
    assert progress.pending is not None
    conflict_value = {
        "status": "conflict",
        "candidate_revision": candidate["candidate_revision"],
        "semantic_digest": semantic_digest,
        "candidate_digest": candidate_digest,
        "conflict_code": "live-binding-mismatch",
        "conflict_detail": "Workflow vs InvokingWorkflow",
        "original_delivery_id": initial.delivery_id,
        "receipt_digest": progress.pending.accepted_receipt_digest,
        "workspace_version": "v1",
        "mutation_state": "zero-mutation",
    }
    conflict = broker.send(
        "protocol", "modeling", json.dumps(conflict_value), expects_reply=True
    )
    assert progress.observe_delivery(
        conflict,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-r23003",
        protocol_thread_id="protocol-thread",
    ) == "conflict"

    revised = {**candidate, "candidate_revision": 2}
    revision = broker.send(
        "modeling",
        "protocol",
        json.dumps(revised),
        expects_reply=True,
        reply_to_delivery_id=conflict.delivery_id,
    )
    assert progress.observe_delivery(
        revision,
        modeling_agent_id="modeling",
        protocol_agent_id="protocol",
        run_id="run-r23003",
        protocol_thread_id="protocol-thread",
    ) == "revision"
    with pytest.raises(runner_module.RoutingError, match="current standalone Protocol conflict"):
        broker.send(
            "modeling",
            "protocol",
            json.dumps({**revised, "candidate_revision": 3}),
            expects_reply=True,
            reply_to_delivery_id=conflict.delivery_id,
        )
    with pytest.raises(runner_module.RoutingError, match="current standalone Protocol conflict"):
        broker.send(
            "modeling",
            "protocol",
            json.dumps({**revised, "candidate_revision": 4}),
            expects_reply=True,
            reply_to_delivery_id="delivery-foreign",
        )
    with pytest.raises(runner_module.RoutingError, match="complete candidate"):
        broker.send(
            "modeling", "protocol", json.dumps(receipt_value), expects_reply=True
        )


def test_formal_r23003_pair_and_model_profile_are_closed() -> None:
    configuration, contract = load_formal_run_configuration(
        ROOT / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml",
        ROOT / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml",
        root=ROOT,
    )
    assert contract.requirement_id == "R2.3-003"
    assert configuration.task.task_id == contract.task_id
    profile = load_team_model_profile(ROOT, contract.default_model_profile_id)
    assert profile.profile_id == contract.default_model_profile_id
    assert (
        profile.relative_path
        == f"modeling_team/model-profiles/{contract.default_model_profile_id}.yaml"
    )


def test_r23003_scope_handoff_is_exact() -> None:
    assert normalize_existing_scope(SCOPE) == SCOPE
    handoff = load_existing_scope_handoff(SCOPE, repository_root=ROOT)
    assert handoff["scope_disposition"] == "retained"
    assert handoff["run_id"] == "r23003-real-20260812-deepseek-start20"
    assert handoff["workspace_version"] == "18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0"
    with pytest.raises(ValueError):
        normalize_existing_scope({**SCOPE, "project_id": "wrong"})


def test_r23003_initial_authorization_opens_exact_four_starts(tmp_path: Path) -> None:
    ledger = StartLedger(tmp_path, requirement_id="R2.3-003")
    freeze = datetime.now(UTC).isoformat()
    with pytest.raises(ValueError):
        ledger.reserve("run-before-auth", "a" * 64, freeze)
    ledger.initial_authorization()
    assert ledger._start_cap(ledger._records()) == 4
    with pytest.raises(ValueError):
        ledger.initial_authorization()
    ledger.reserve("run-after-auth", "a" * 64, freeze)
    ledger.mark_semantic_start("run-after-auth")
    assert sum(item["event"] == "semantic_start" for item in ledger._records()) == 1


def test_r23003_consumed_initial_budget_accepts_explicit_plus_three_extension(
    tmp_path: Path,
) -> None:
    ledger = StartLedger(tmp_path, requirement_id="R2.3-003")
    freeze = datetime.now(UTC).isoformat()
    ledger.initial_authorization()
    for index in range(1, 5):
        run_id = f"run-{index}"
        ledger.reserve(run_id, f"baseline-{index}", freeze)
        ledger.mark_semantic_start(run_id)
        ledger.terminal_failure(run_id, "platform-contract", False)

    ledger.authorize_budget(
        3,
        "user-20260811-r23003-revision-start1-3",
        "user-20260811-r23003-revision-start1-3",
    )
    records = ledger._records()
    assert ledger._start_cap(records) == 7
    assert ledger._semantic_start_count(records) == 4
    reservations = {
        item["run_id"] for item in records if item.get("event") == "reservation"
    }
    inactive = {
        item["run_id"]
        for item in records
        if item.get("event") in {"semantic_start", "presemantic_release"}
    }
    assert reservations - inactive == set()

    for amount in (True, 0, -1):
        with pytest.raises(ValueError):
            ledger.authorize_budget(amount, f"invalid-{amount}", f"invalid-ref-{amount}")
    with pytest.raises(ValueError):
        ledger.authorize_budget(
            3,
            "user-20260811-r23003-revision-start1-3",
            "different-reference",
        )
    with pytest.raises(ValueError):
        ledger.authorize_budget(3, "different-id", "user-20260811-r23003-revision-start1-3")


def test_r23003_budget_extension_still_requires_consumed_cap_and_retryable_predecessor(
    tmp_path: Path,
) -> None:
    ledger = StartLedger(tmp_path, requirement_id="R2.3-003")
    ledger.initial_authorization()
    with pytest.raises(ValueError):
        ledger.authorize_budget(3, "premature", "premature-reference")


def test_r23003_team_transport_uses_advertised_fully_qualified_call(tmp_path: Path) -> None:
    """The App Server-facing prompt must name the callable MCP tool, not a bare alias."""

    packages = ROOT / "modeling_team" / "agent-packages"
    required_name = "mcp__team_transport__send_team_message"
    for package_id in ("modeling", "protocol", "acceptance", "coordinator"):
        instructions = (packages / package_id / "instructions.md").read_text(encoding="utf-8")
        assert required_name in instructions
        assert "Do not call an unqualified" in instructions
        assert re.search(r"call\s+`send_team_message`", instructions) is None

    broker = TeamTransportBroker(
        tmp_path / "transport",
        {("modeling", "protocol")},
    )
    broker.start(["modeling", "protocol"])
    try:
        advertised = mcp_response(
            {"method": "tools/list"}, broker=broker, agent_id="modeling"
        )
        names = {entry["name"] for entry in advertised["tools"]}
        assert "send_team_message" in names

        adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
        adapter._run_root = tmp_path
        (tmp_path / "transport-root").write_text(str(broker.root), encoding="utf-8")
        agent = SimpleNamespace(agent_id="modeling")
        result = adapter._dynamic_tool_result(
            agent,
            required_name,
            {"recipient_id": "protocol", "text": "exact transport call"},
        )
        assert result["success"] is True
        deliveries = broker.drain()
        assert len(deliveries) == 1
        assert deliveries[0].text == "exact transport call"
    finally:
        broker.stop()


def test_r23003_preflight_runs_live_probe_before_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "modeling_team.preflight.capture_clean_checkout",
        lambda _root: {"head": "a" * 40, "status_porcelain": "", "status_digest": "b" * 64},
    )
    evidence = run_existing_scope_preflight(
        repository_root=ROOT,
        scope=SCOPE,
        admin_key="delivery-only-secret",
        probe=lambda **_: {
            "project_id": R2_3_003_PROJECT_ID,
            "ontology_id": R2_3_003_ONTOLOGY_ID,
            "workspace_version": "18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0",
            "secret": "must-not-be-retained",
        },
    )
    assert evidence["live"]["workspace_version"].startswith("18e491")
    assert "secret" not in json.dumps(evidence)


@pytest.mark.parametrize("project_payload", [{}, [], {"id": "wrong-project"}])
def test_r23003_existing_project_identity_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    project_payload: object,
) -> None:
    monkeypatch.setattr(
        preflight_module,
        "_authenticated_json_get",
        lambda *_args, **_kwargs: project_payload,
    )
    with pytest.raises(TeamConfigurationError, match="Project identity"):
        canonical_existing_scope_preflight(
            scope=SCOPE,
            handoff={"workspace_version": "v1"},
            base_url="http://example",
            admin_key="delivery-only-secret",
        )


def test_r23003_runner_reads_credential_only_after_existing_live_preflight(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    ledger_root = tmp_path / "ledger"
    run_id = "r23003-credential-order"
    run_root = ROOT / "workspaces" / "modeling-runs" / run_id

    def live_preflight(**_kwargs: object) -> dict[str, object]:
        events.append("live-preflight")
        return {"status": "ready", "live": {"workspace_version": "v1"}}

    def credential_preflight(_profile: object, **_kwargs: object) -> object:
        events.append("credential")
        return {}

    runner = runner_module.TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=tmp_path / "deepseek.env",
        freeze_started_at=datetime.now(UTC).isoformat(),
        ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
    )
    runner._canonical_ledger_root = lambda: ledger_root
    StartLedger(ledger_root, requirement_id="R2.3-003").initial_authorization()
    try:
        with patch.object(runner_module, "run_existing_scope_preflight", live_preflight), patch.object(
            runner_module, "preflight_profile_credentials", credential_preflight
        ):
            runner.prepare(
                run_id=run_id,
                profile_path=ROOT
                / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml",
                task_path=ROOT
                / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml",
                scope=SCOPE,
            )
        assert events == ["live-preflight", "credential"]
        assert runner._ledger is not None
        assert runner._ledger._records()[1]["event"] == "reservation"
    finally:
        runner.cleanup()
        if run_root.exists():
            import shutil

            shutil.rmtree(run_root)


def test_r23003_protocol_task_text_waits_for_candidate_receipt_before_platform_calls(
    tmp_path: Path,
) -> None:
    """Generated task text must close every ontology_platform path until receipt binding."""

    ledger_root = tmp_path / "ledger"
    run_id = "r23003-protocol-startup-barrier"
    run_root = ROOT / "workspaces" / "modeling-runs" / run_id
    runner = runner_module.TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=tmp_path / "deepseek.env",
        freeze_started_at=datetime.now(UTC).isoformat(),
        ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
    )
    runner._canonical_ledger_root = lambda: ledger_root
    StartLedger(ledger_root, requirement_id="R2.3-003").initial_authorization()
    try:
        with patch.object(
            runner_module,
            "run_existing_scope_preflight",
            lambda **_kwargs: {"status": "ready", "live": {"workspace_version": "v1"}},
        ), patch.object(
            runner_module,
            "preflight_profile_credentials",
            lambda _profile, **_kwargs: {},
        ):
            runner.prepare(
                run_id=run_id,
                profile_path=ROOT
                / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml",
                task_path=ROOT
                / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml",
                scope=SCOPE,
            )
        protocol = runner._task_text("protocol")
        objective = runner.run.configuration.task.objective
        assert protocol.count(objective) == 1
        # Business semantics stay in the Task objective/package.  Runner adds
        # only the mechanical startup/revalidation contract, so these literals
        # must not occur more often than they do in the objective itself.
        for literal in (
            "unknown-cross-release-output-meaning",
            "unknown-b-no-score-behavior",
            "item_kind=delete_existing_entity",
            "full_live_impact",
            "delivery-8 -> delivery-9",
            "r23003-retained-scope-increment-1",
        ):
            assert protocol.count(literal) == objective.count(literal)
        barrier = protocol.index("Protocol startup barrier")
        mechanics = protocol.index("Before any platform call, read /opt/mechanics-contract.json")
        assert barrier < mechanics
        for tool in (
            "check_platform_health",
            "get_project_build_context",
            "get_ontology_workspace_context",
            "get_modeling_context",
        ):
            assert f"`{tool}`" in protocol
        assert "wait for a direct Modeling Team Transport delivery" in protocol
        assert "candidate receipt is successfully built" in protocol
        assert "`candidate_receipt_required` error means this barrier is still closed" in protocol
        assert "mcp__team_transport__send_team_message" in protocol
        assert "mcp__team_transport__send_coordination" in protocol
        assert "mcp__team_transport__report_task_result" in protocol
        assert "protocol_build_candidate_receipt itself fails at the receipt gate" in protocol
        assert "build_candidate_conflict with the unchanged complete candidate" in protocol
        assert "native MCP result has only content and structuredContent" in protocol
        assert "content[0].text parses to structuredContent" in protocol
        assert "canonical JSON serialization" in protocol
        assert "no conflict_json" in protocol
        assert "reply-bound request for Modeling to send one full revised candidate" in protocol
        assert "duplicate receipt/reply" in protocol
        assert "new standalone Protocol-to-Modeling delivery" in protocol
        assert "reply_to_delivery_id=None" in protocol
        assert "Pre-receipt conflicts and all R2.3-005 candidates keep" in protocol
    finally:
        runner.cleanup()
        if run_root.exists():
            import shutil

            shutil.rmtree(run_root)


def test_r23003_modeling_prompt_bounds_candidate_and_requires_inline_transport(
    tmp_path: Path,
) -> None:
    ledger_root = tmp_path / "ledger"
    run_id = "r23003-modeling-candidate-boundary"
    run_root = ROOT / "workspaces" / "modeling-runs" / run_id
    runner = runner_module.TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=tmp_path / "deepseek.env",
        freeze_started_at=datetime.now(UTC).isoformat(),
        ledger_factory=lambda *, root, config, now: StartLedger(root, config=config, now=now),
    )
    runner._canonical_ledger_root = lambda: ledger_root
    StartLedger(ledger_root, requirement_id="R2.3-003").initial_authorization()
    try:
        with patch.object(
            runner_module,
            "run_existing_scope_preflight",
            lambda **_kwargs: {"status": "ready", "live": {"workspace_version": "v1"}},
        ), patch.object(
            runner_module,
            "preflight_profile_credentials",
            lambda _profile, **_kwargs: {},
        ):
            runner.prepare(
                run_id=run_id,
                profile_path=ROOT
                / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml",
                task_path=ROOT
                / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml",
                scope=SCOPE,
            )
        generated = runner._task_text("modeling")
        package = (
            ROOT / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        objective = runner.run.configuration.task.objective
        assert generated.count(objective) == 1
        assert 'JSON number `1`, not the quoted string `"1"`' in objective
        assert 'JSON numbers, never strings: initial `1` (not `"1"`)' in " ".join(
            package.split()
        )
        for literal in (
            "unknown-cross-release-output-meaning",
            "unknown-b-no-score-behavior",
            "item_kind=delete_existing_entity",
            "full_live_impact",
            "delivery-8 -> delivery-9",
            "r23003-retained-scope-increment-1",
        ):
            assert generated.count(literal) == objective.count(literal)
        for text in (package,):
            assert "12-24" in text or "12–24" in text
            assert "32 items" in text
            assert "existing_entity_ref" in text
            assert "do not enumerate every source field" in text
            assert "exec" in text
            assert "the filesystem" in text
            assert "mcp__team_transport__send_team_message" in text
            assert "recipient_id=protocol" in text or 'recipient_id="protocol"' in text
            assert "expects_reply=true" in text
            assert "candidate JSON" in text
            assert "message text" in text or "JSON as text" in text
            assert "never end with prose" in text or "Never finish a turn" in text
            assert "unknown-cross-release-output-meaning" in text
            assert "unknown-b-no-score-behavior" in text
            assert "item_kind=delete_existing_entity" in text
            assert "independent standalone" in text
            assert "r23003-retained-scope-increment-1" in text
            assert "delivery-8 -> delivery-9" in text
            assert "strictly greater" in text
            assert (
                "semantic exactly {semantic_id, expected_class, delete_mode=full_live_impact}" in text
                or "object containing exactly semantic_id, expected_class, and delete_mode=full_live_impact" in text
                or "object containing exactly `semantic_id`, `expected_class`, and `delete_mode=full_live_impact" in text
            )
            assert "do not use `entity_delete`" in text or "Do not use entity_delete" in text
        for text in (generated,):
            assert text.count("existing_entity_ref") == objective.count("existing_entity_ref")
            assert "12-24" not in text
            assert "32 items" not in text
            assert "do not enumerate every source field" not in text
            assert "exec" not in text
            assert "the filesystem" not in text
            assert "mcp__team_transport__send_team_message" in text
            assert "R2.3-003 Modeling has one independent project-scoped read key" in text
        assert "Reply to the delivered conflict `delivery_id`" in package
        assert "full, self-contained revised candidate" in package
    finally:
        runner.cleanup()
        if run_root.exists():
            import shutil

            shutil.rmtree(run_root)


def test_r23003_initial_target_refs_and_revision_sequence_are_explicitly_bound() -> None:
    """The prompt contract names both standalone target refs and the next revision rule."""

    task = (ROOT / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml").read_text(
        encoding="utf-8"
    )
    modeling = (ROOT / "modeling_team/agent-packages/modeling/instructions.md").read_text(
        encoding="utf-8"
    )
    protocol = (ROOT / "modeling_team/agent-packages/protocol/instructions.md").read_text(
        encoding="utf-8"
    )
    for text in (task, modeling, protocol):
        assert "unknown-cross-release-output-meaning" in text
        assert "unknown-b-no-score-behavior" in text
        assert "standalone" in text and "existing_entity_ref" in text
        assert "candidate_revision" in text
        assert "r23003-retained-scope-increment-1" in text
        assert "delivery-8 -> delivery-9" in text
    for phrase in (
        'requirement_id="R2.3-003"',
        "existing_binding_receipt",
        "deletion_impact_receipts",
        "phase_a_readback=true",
        "phase_a_readback_required",
        "durable Phase-A readback",
        "final `delete-only` Phase-B batch last",
        "never be sent on the R2.3-005 candidate-only path",
    ):
        assert phrase in protocol



def test_r23003_existing_binding_receipt_and_translation_are_read_only() -> None:
    candidate = _candidate()
    receipt = build_existing_entity_binding_receipt(
        candidate,
        {
            "entities": [
                {
                    "semantic_id": "review-001",
                    "entity_iri": "http://ontology-platform.local/semantic/entity/review-001",
                    "class_semantic_id": "Review",
                    "class_iri": "http://ontology-platform.local/semantic/class/Review",
                    "project_id": R2_3_003_PROJECT_ID,
                    "ontology_id": R2_3_003_ONTOLOGY_ID,
                    "workspace_version": "v1",
                    "read_evidence": {"source": "live-read"},
                }
            ]
        },
        project_id=R2_3_003_PROJECT_ID,
        ontology_id=R2_3_003_ONTOLOGY_ID,
        workspace_version="v1",
    )
    translated = translate_candidate_to_batches(
        candidate, receipt, requirement_id="R2.3-003"
    )
    assert translated["batches"][-1]["items"][0]["payload"]["source_entity_iri"].endswith(
        "/review-001"
    )
    with pytest.raises(ProtocolRetrievalFallbackError):
        translate_candidate_to_batches(candidate)
    with pytest.raises(ProtocolRetrievalFallbackError):
        translate_candidate_to_batches(candidate, receipt, requirement_id="R2.3-005")


def test_r23003_continuation_reuses_phase_a_entities_and_splits_delete_batches() -> None:
    """A post-Phase-A continuation binds retained entities and emits deletes only."""

    target_ids = (
        "unknown-cross-release-output-meaning",
        "unknown-b-no-score-behavior",
    )
    retained_refs = (
        ("content-review-001", "Content"),
        ("evaluation-review-001", "ContentEvaluation"),
        ("decision-review-001", "PublishabilityDecision"),
        ("publication-outcome-review-001", "PublicationOutcome"),
    )
    candidate = {
        "candidate_kind": "platform-neutral-candidate-v2",
        "candidate_revision": 2,
        "scope": "retained-continuation",
        "constraints": ["source-grounded", "phase-a-readback-continuation"],
        "items": [
            {
                "item_id": f"existing-{semantic_id}",
                "item_kind": "existing_entity_ref",
                "semantic": {"semantic_id": semantic_id, "expected_class": expected_class},
            }
            for semantic_id, expected_class in retained_refs
            + tuple((semantic_id, "ExplicitUnknown") for semantic_id in target_ids)
        ]
        + [
            {
                "item_id": f"delete-{semantic_id}",
                "item_kind": "delete_existing_entity",
                "semantic": {
                    "semantic_id": semantic_id,
                    "expected_class": "ExplicitUnknown",
                    "delete_mode": "full_live_impact",
                },
            }
            for semantic_id in target_ids
        ],
    }
    rows = [
        {
            "semantic_id": semantic_id,
            "entity_iri": f"http://ontology-platform.local/semantic/entity/{semantic_id}",
            "class_semantic_id": expected_class,
            "class_iri": f"http://ontology-platform.local/semantic/class/{expected_class}",
            "project_id": R2_3_003_PROJECT_ID,
            "ontology_id": R2_3_003_ONTOLOGY_ID,
            "workspace_version": "phase-a-v1",
            "read_evidence": {"source": "durable-phase-a-readback"},
        }
        for semantic_id, expected_class in retained_refs
        + tuple((semantic_id, "ExplicitUnknown") for semantic_id in target_ids)
    ]
    binding = build_existing_entity_binding_receipt(
        candidate,
        {"entities": rows},
        project_id=R2_3_003_PROJECT_ID,
        ontology_id=R2_3_003_ONTOLOGY_ID,
        workspace_version="phase-a-v1",
    )
    candidate_digest = canonical_digest(candidate)
    impact_receipts = {}
    for semantic_id in target_ids:
        entity_iri = next(row["entity_iri"] for row in rows if row["semantic_id"] == semantic_id)
        empty_digest = canonical_digest([])
        impact_receipts[semantic_id] = build_delete_impact_receipt(
            [
                {
                    "project_id": R2_3_003_PROJECT_ID,
                    "ontology_id": R2_3_003_ONTOLOGY_ID,
                    "entity_iri": entity_iri,
                    "workspace_version": "phase-a-v1",
                    "statements": [],
                    "page_digest": empty_digest,
                    "snapshot_digest": empty_digest,
                    "next_cursor": None,
                    "complete": True,
                }
            ],
            target_semantic_id=semantic_id,
            candidate_digest=candidate_digest,
            project_id=R2_3_003_PROJECT_ID,
            ontology_id=R2_3_003_ONTOLOGY_ID,
            workspace_version="phase-a-v1",
        )

    translated = translate_candidate_to_batches(
        candidate,
        binding,
        requirement_id="R2.3-003",
        deletion_impact_receipts=impact_receipts,
        phase_a_readback=True,
    )
    assert [batch["stage_kind"] for batch in translated["batches"]] == [
        "delete-only",
        "delete-only",
    ]
    delete_batches = translated["batches"]
    assert [len(batch["items"]) for batch in delete_batches] == [1, 1]
    assert [
        batch["items"][0]["payload"]["semantic_id"] for batch in delete_batches
    ] == list(target_ids)
    assert len({batch["client_batch_id"] for batch in delete_batches}) == 2
    assert len({batch["idempotency_key"] for batch in delete_batches}) == 2
    assert all(batch["phase"] == "B" and batch["delete_only"] for batch in delete_batches)
    assert all(
        item["command_kind"] == "delete_entity"
        for batch in delete_batches
        for item in batch["items"]
    )


def test_existing_platform_scope_allows_completed_history_without_delete() -> None:
    calls: list[tuple[str, str]] = []

    def request(method: str, path: str, body: object, key: str):
        calls.append((method, path))
        if path.endswith("/ontologies"):
            return 200, [{"id": R2_3_003_ONTOLOGY_ID}]
        if path.endswith("workspace-context"):
            return 200, {
                "state": "ready",
                "default_graph_set_id": "graph-1",
                "workspace": {"workspace_version": "v1"},
            }
        if path.endswith("modeling-batches"):
            return 200, {"items": [{"id": "history-1"}]}
        if path.endswith("build-context"):
            return 200, {
                "platform_state": {
                    "ontologies": [{"id": R2_3_003_ONTOLOGY_ID, "workspace": {"workspace_version": "v1"}}]
                },
                "agent_state": {"active_sessions": [], "recent_sessions": []},
            }
        if path == "/api/api-keys":
            return 201, {"id": "protocol-key", "plaintext_key": "secret"}
        if path.endswith(":revoke"):
            return 200, {"revoked_at": "now"}
        if method == "GET":
            return 200, {"id": path.rsplit("/", 1)[-1]}
        return 200, {}

    scope = PlatformScope(
        "http://example",
        "r23003-test",
        lambda: ("admin", "admin-id"),
        lambda _key_id: True,
        request,
    )
    scope.prepare(SCOPE)
    cleanup = scope.cleanup()
    assert cleanup["existing_context_before"]["modeling_batch_count"] == 1
    assert not any(method == "DELETE" for method, _ in calls)
