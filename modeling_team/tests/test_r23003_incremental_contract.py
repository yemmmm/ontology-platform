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
from modeling_team.contracts import TeamConfigurationError
from modeling_team.formal_runs import load_formal_run_configuration
from modeling_team.model_manifest import load_formal_model_manifest
from modeling_team.platform_scope import PlatformScope
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
        ],
    }


def test_formal_r23003_pair_and_manifest_are_closed() -> None:
    configuration, contract = load_formal_run_configuration(
        ROOT / "modeling_team/profiles/r2-3-003-existing-scope-modeling-team.yaml",
        ROOT / "modeling_team/tasks/r2-3-003-existing-scope-incremental.yaml",
        root=ROOT,
    )
    assert contract.requirement_id == "R2.3-003"
    assert configuration.task.task_id == contract.task_id
    manifest = load_formal_model_manifest(
        ROOT,
        manifest_path=Path(contract.model_manifest_path),
        manifest_id="r2-3-003-deepseek-v4-flash",
        profile_id=contract.profile_id,
        task_id=contract.task_id,
    )
    assert manifest.relative_path == contract.model_manifest_path


def test_r23003_scope_handoff_is_exact() -> None:
    assert normalize_existing_scope(SCOPE) == SCOPE
    handoff = load_existing_scope_handoff(SCOPE, repository_root=ROOT)
    assert handoff["scope_disposition"] == "retained"
    assert handoff["workspace_version"] == "0d34f5ada161d2c6deb4a7b117c6b1469b540eef7eb1f04c8bdce97e5100ef02"
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
            "workspace_version": "0d34f5ada161d2c6deb4a7b117c6b1469b540eef7eb1f04c8bdce97e5100ef02",
            "secret": "must-not-be-retained",
        },
    )
    assert evidence["live"]["workspace_version"].startswith("0d34")
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

    def credential_preflight(_path: object) -> object:
        events.append("credential")
        return object()

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
            runner_module, "preflight_deepseek_credential", credential_preflight
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


def test_r23003_existing_binding_receipt_and_translation_are_read_only() -> None:
    candidate = _candidate()
    receipt = build_existing_entity_binding_receipt(
        candidate,
        {
            "entities": [
                {
                    "semantic_id": "review-001",
                    "class": "Review",
                    "entity_iri": "http://ontology-platform.local/semantic/entity/review-001",
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
