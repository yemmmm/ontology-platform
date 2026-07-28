"""Minimal M6 input isolation, attempt-budget, and Host preflight helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib import request


SCENARIO_ROOT = Path(__file__).resolve().parent
AGENT_INPUT = SCENARIO_ROOT / "agent-input"
MANIFEST = AGENT_INPUT / "manifest.json"
ATTEMPT_LIMIT = 3
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
FORBIDDEN_VISIBLE_TEXT = (
    "material-gap-contract",
    "invocation-target",
    "output-continuity",
    "missing-score-behavior",
    "there are three",
    "three gaps",
    "expected gap count",
)


class ScenarioError(RuntimeError):
    """The M6 isolation or execution contract was violated."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_agent_input() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declared = {entry["path"] for entry in manifest["files"]}
    actual = {
        path.relative_to(AGENT_INPUT).as_posix()
        for path in AGENT_INPUT.rglob("*")
        if path.is_file() and path != MANIFEST
    }
    if declared != actual:
        raise ScenarioError("Agent-visible file set differs from manifest")
    for entry in manifest["files"]:
        path = AGENT_INPUT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ScenarioError(f"Agent-visible hash mismatch: {entry['path']}")
        lowered = path.read_text(encoding="utf-8").lower()
        if any(marker in lowered for marker in FORBIDDEN_VISIBLE_TEXT):
            raise ScenarioError(f"Agent-visible answer/category leak: {entry['path']}")
    return manifest


class AttemptLedger:
    """Append-only evidence for at most three fresh modeling subagents."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def append(self, event: dict[str, Any]) -> None:
        if not RUN_ID.fullmatch(str(event.get("run_id", ""))):
            raise ScenarioError("unsafe run_id")
        events = self.events()
        started = [item for item in events if item.get("event") == "modeling_started"]
        if event.get("event") == "modeling_started":
            if len(started) >= ATTEMPT_LIMIT:
                raise ScenarioError("M6 modeling attempt limit reached")
            if any(item["run_id"] == event["run_id"] for item in started):
                raise ScenarioError("run_id already used")
            required = {"event", "run_id", "agent_id", "fork_turns", "input_manifest_sha256"}
            if set(event) != required or event["fork_turns"] != "none":
                raise ScenarioError("invalid modeling_started event")
        elif event.get("event") in {"question", "answer", "attempt_finished"}:
            if not any(item["run_id"] == event["run_id"] for item in started):
                raise ScenarioError("event has no modeling start")
        else:
            raise ScenarioError("unsupported ledger event")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(canonical_json(event) + b"\n")

    def must_pause(self) -> bool:
        return sum(item.get("event") == "modeling_started" for item in self.events()) >= ATTEMPT_LIMIT


def create_empty_scope(base_url: str, api_key: str, run_id: str) -> dict[str, str]:
    """Host-only REST setup. It creates no semantic model content."""
    if not RUN_ID.fullmatch(run_id):
        raise ScenarioError("unsafe run_id")

    def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        call = request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=canonical_json(body),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(call, timeout=30) as response:  # noqa: S310 - bounded configured API
            return json.load(response)

    project = post(
        "/api/projects",
        {"name": f"M6 {run_id}", "description": "Empty Host-created scope for blind M6 modeling."},
    )
    ontology = post(
        f"/api/projects/{project['id']}/ontologies",
        {"name": f"M6 {run_id}", "description": "Empty ontology; Agent owns all semantics.", "external_mappings": {}},
    )
    return {"project_id": str(project["id"]), "ontology_id": str(ontology["id"])}
