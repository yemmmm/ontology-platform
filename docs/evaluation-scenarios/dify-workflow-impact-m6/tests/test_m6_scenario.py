from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

import m6_scenario as scenario  # noqa: E402


def test_frozen_agent_input_has_no_hidden_contract_or_explicit_gap_list() -> None:
    manifest = scenario.verify_agent_input()
    assert manifest["manifest_version"] == 1
    assert all("host-only" not in entry["path"] for entry in manifest["files"])
    visible = "\n".join(
        (scenario.AGENT_INPUT / entry["path"]).read_text(encoding="utf-8")
        for entry in manifest["files"]
    ).lower()
    assert "question list" not in visible
    assert "problem count" not in visible
    assert "problem categories" not in visible


def test_host_contract_gaps_are_discoverable_from_declared_visible_files() -> None:
    contract = json.loads(
        (SCENARIO_ROOT / "host-only" / "material-gap-contract.json").read_text(encoding="utf-8")
    )
    for decision in contract["decisions"]:
        assert len(decision["evidence_files"]) >= 2
        for relative in decision["evidence_files"]:
            path = (scenario.AGENT_INPUT / relative).resolve()
            assert scenario.AGENT_INPUT.resolve() in path.parents
            assert path.is_file()
        assert decision["consumer_impact"].strip()
        assert ("answer" in decision) ^ ("uncertain" in decision)


def started(run_id: str) -> dict[str, str]:
    return {
        "event": "modeling_started",
        "run_id": run_id,
        "agent_id": f"agent-{run_id}",
        "fork_turns": "none",
        "input_manifest_sha256": hashlib.sha256(scenario.MANIFEST.read_bytes()).hexdigest(),
    }


def test_attempt_ledger_rejects_fourth_modeling_agent(tmp_path: Path) -> None:
    ledger = scenario.AttemptLedger(tmp_path / "attempts.jsonl")
    for number in range(1, 4):
        ledger.append(started(f"m6-run-{number}"))
    assert ledger.must_pause()
    with pytest.raises(scenario.ScenarioError, match="limit reached"):
        ledger.append(started("m6-run-4"))


def test_attempt_ledger_requires_fresh_no_context_agent(tmp_path: Path) -> None:
    ledger = scenario.AttemptLedger(tmp_path / "attempts.jsonl")
    invalid = started("m6-run-1")
    invalid["fork_turns"] = "all"
    with pytest.raises(scenario.ScenarioError, match="invalid modeling_started"):
        ledger.append(invalid)


def test_host_scope_preflight_creates_only_project_and_empty_ontology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Response:
        def __init__(self, value: dict[str, str]) -> None:
            self.value = value

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(call: object, timeout: int) -> Response:
        assert timeout == 30
        body = json.loads(call.data)
        calls.append((call.full_url, body))
        return Response({"id": "project-1" if len(calls) == 1 else "ontology-1"})

    monkeypatch.setattr(scenario.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(scenario.json, "load", lambda response: response.value)
    scope = scenario.create_empty_scope("http://127.0.0.1:8001", "host-secret", "m6-run-1")
    assert scope == {"project_id": "project-1", "ontology_id": "ontology-1"}
    assert [path.rsplit("/", 1)[-1] for path, _body in calls] == ["projects", "ontologies"]
    assert all("class" not in json.dumps(body).lower() for _path, body in calls)
