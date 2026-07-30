"""Foreground single-run lifecycle and newline-delimited JSON outer protocol."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any


from .contracts import (
    TeamConfiguration,
    TeamConfigurationError,
    digest_file,
    load_team_configuration,
)
from .runtimes.base import RuntimeAdapter, RuntimeDelivery
from .transport_mcp import TeamTransportBroker


@dataclass
class TeamRun:
    run_id: str
    root: Path
    configuration: TeamConfiguration
    scope: dict[str, str]
    protocol_key: str | None = None
    transport_root: Path | None = None


class TeamRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        adapter: RuntimeAdapter,
        scope_factory: Any | None = None,
    ):
        self.repository_root, self.adapter, self.scope_factory = (
            repository_root,
            adapter,
            scope_factory,
        )
        self.run: TeamRun | None = None
        self.transport: TeamTransportBroker | None = None
        self.scope: Any | None = None
        self._terminal_emitted = False
        self._terminal_results_notified_to_coordinator: set[str] = set()
        self._post_settlement_reporting_requested = False
        self._coordinator_final_captured = False
        self._outer_user_texts: set[str] = set()

    @staticmethod
    def _safe_run_id(value: str) -> bool:
        import re

        return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", value))

    def prepare(
        self, *, run_id: str, profile_path: Path, task_path: Path, scope: dict[str, str]
    ) -> TeamRun:
        if self.run is not None or not self._safe_run_id(run_id):
            raise TeamConfigurationError("unsafe or already attached run ID")
        config = load_team_configuration(
            profile_path, task_path, root=self.repository_root
        )
        root = self.repository_root / "workspaces" / "modeling-runs" / run_id
        if root.exists():
            raise TeamConfigurationError("run directory already exists")
        root.mkdir(parents=True, mode=0o700)
        (root / "evidence").mkdir(mode=0o700)
        sources = root / "sources"
        sources.mkdir(mode=0o700)
        for source in config.task.allowed_sources:
            target = sources / source.name
            shutil.copyfile(source, target)
            os.chmod(target, 0o444)
        self.run = TeamRun(run_id, root, config, scope)
        self._atomic_json(
            root / "state.json",
            {
                "state": "PREPARING",
                "run_id": run_id,
                "profile_id": config.profile.profile_id,
                "task_id": config.task.task_id,
            },
        )
        shutil.copyfile(profile_path, root / "profile.snapshot.yaml")
        shutil.copyfile(task_path, root / "task.snapshot.yaml")
        self._record_runtime_core_hashes("before_start")
        return self.run

    def start(self) -> None:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        self._state("STARTING")
        try:
            if self.scope_factory:
                self.scope = self.scope_factory(self.run)
                self.scope.prepare(self.run.scope)
                self.run.protocol_key = self.scope.protocol_key
            self.transport = TeamTransportBroker(
                self.run.root / "transport" / "broker",
                set(self.run.configuration.profile.communication),
            )
            self.transport.start(
                [agent.agent_id for agent in self.run.configuration.profile.agents]
            )
            self.run.transport_root = self.transport.root
            (self.run.root / "transport-root").write_text(
                str(self.transport.root), encoding="utf-8"
            )
            identities = self.adapter.start_roster(
                self.run, self.run.configuration.profile.agents
            )
            roster = [identity.agent_id for identity in identities]
            task_text = self._task_text()
            for agent in self.run.configuration.profile.agents:
                self.adapter.start_task(
                    agent.agent_id,
                    task_text,
                    [str(path) for path in agent.package.required_skills],
                    roster,
                )
            self._state("RUNNING", identities=[item.agent_id for item in identities])
        except Exception:
            self._state("FAILED")
            self.cleanup()
            raise

    def _task_text(self) -> str:
        assert self.run
        return (
            self.run.configuration.task.objective
            + "\nAllowed sources: "
            + ", ".join(
                f"/agent/home/sources/{path.name}"
                for path in self.run.configuration.task.allowed_sources
            )
            + "\nUse Team Transport for direct messages and call report_task_result exactly once before ending. Protocol must call check_platform_health once; do not call another platform tool."
        )

    def receive_outer(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.run:
            raise RuntimeError("Runner is not prepared")
        action = message.get("action")
        if action == "user":
            text = message.get("text")
            if not isinstance(text, str):
                raise TeamConfigurationError("outer user text must be a string")
            coordinator = next(
                agent.agent_id
                for agent in self.run.configuration.profile.agents
                if agent.package.role == "coordinator"
            )
            self.adapter.send_message(
                coordinator,
                RuntimeDelivery(
                    sender_id="user/outer",
                    recipient_id=coordinator,
                    kind="outer-user",
                    text=text,
                ),
            )
            self._outer_user_texts.add(text)
            self._append_evidence("outer-user", {"text": text})
        elif action == "status":
            pass
        elif action == "pause":
            self.adapter.pause()
            self._state("PAUSED")
        elif action == "resume":
            self.adapter.resume()
            self._state("RUNNING")
        elif action == "stop":
            self.cleanup()
            return [{"type": "stopped"}]
        else:
            raise TeamConfigurationError("unknown outer Runner action")
        return self.drain()

    def drain(self) -> list[dict[str, Any]]:
        if not self.run or not self.transport:
            return []
        output: list[dict[str, Any]] = []
        coordinator = next(
            agent.agent_id
            for agent in self.run.configuration.profile.agents
            if agent.package.role == "coordinator"
        )
        for delivery in self.transport.drain():
            if delivery.recipient_id in self.transport.results:
                self._append_evidence(
                    "terminal-delivery-blocked",
                    {
                        "sender_id": delivery.sender_id,
                        "recipient_id": delivery.recipient_id,
                        "reason": "recipient already reported terminal result",
                    },
                )
                continue
            self.adapter.send_message(
                delivery.recipient_id,
                RuntimeDelivery(
                    sender_id=delivery.sender_id,
                    recipient_id=delivery.recipient_id,
                    kind=(
                        "outer-forward"
                        if delivery.sender_id == coordinator
                        and delivery.text in self._outer_user_texts
                        else "peer"
                    ),
                    text=delivery.text,
                ),
            )
            envelope = {"type": "delivery", **delivery.__dict__}
            output.append(envelope)
            self._append_evidence("deliveries", envelope)
        results = self.transport.results
        for agent_id, result in results.items():
            if agent_id == coordinator or agent_id in self._terminal_results_notified_to_coordinator:
                continue
            if coordinator in results:
                self._append_evidence(
                    "terminal-result-coordinator-handoff-blocked",
                    {
                        "agent_id": agent_id,
                        "reason": "coordinator already reported terminal result",
                        "result": result.__dict__,
                    },
                )
                self._terminal_results_notified_to_coordinator.add(agent_id)
                continue
            text = json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True)
            self.adapter.send_message(
                coordinator,
                RuntimeDelivery(
                    sender_id="runner/terminal-result",
                    recipient_id=coordinator,
                    kind="terminal-handoff",
                    text=text,
                ),
            )
            envelope = {
                "type": "terminal-result-coordinator-handoff",
                "recipient_id": coordinator,
                "result": result.__dict__,
            }
            output.append(envelope)
            self._append_evidence("terminal-result-coordinator-handoff", envelope)
            self._terminal_results_notified_to_coordinator.add(agent_id)
        for message in self.adapter.receive_messages():
            if message.agent_id == coordinator:
                if self._post_settlement_reporting_requested:
                    self._capture_coordinator_final(message, output)
                    continue
                envelope = {"type": "coordinator", "text": message.text}
                output.append(envelope)
                self._append_evidence("coordinator", envelope)
        if not self._terminal_emitted and len(self.transport.results) == len(
            self.run.configuration.profile.agents
        ) and self.adapter.wait_settled(
            [agent.agent_id for agent in self.run.configuration.profile.agents], 1
        ):
            self._terminal_emitted = True
            envelope = {
                "type": "settled",
                "results": {
                    key: value.__dict__ for key, value in self.transport.results.items()
                },
            }
            output.append(envelope)
            self._append_evidence("settled", envelope)
            self._state("POST_SETTLEMENT_REPORTING")
            self._post_settlement_reporting_requested = True
            self.adapter.send_message(
                coordinator,
                RuntimeDelivery(
                    sender_id="runner/post-settlement",
                    recipient_id=coordinator,
                    kind="post-settlement",
                    text=self._post_settlement_prompt(envelope["results"]),
                ),
            )
        return output

    @staticmethod
    def _post_settlement_prompt(results: dict[str, Any]) -> str:
        return (
            "Runtime settlement is complete. Generate exactly one non-empty user-facing final "
            "summary from this immutable structured terminal-result snapshot. Preserve every "
            "Agent status and summary faithfully; do not call tools, send peer messages, or call "
            "report_task_result again.\nTerminal-result snapshot:\n"
            + json.dumps(results, ensure_ascii=False, sort_keys=True)
        )

    def _capture_coordinator_final(
        self, message: Any, output: list[dict[str, Any]]
    ) -> None:
        if self._coordinator_final_captured or not isinstance(message.text, str):
            return
        text = message.text.strip()
        if not text:
            return
        self._coordinator_final_captured = True
        envelope = {"type": "coordinator", "text": text}
        output.append(envelope)
        self._append_evidence("coordinator-final", envelope)
        self._state("TERMINAL_REPORT_COMPLETE")

    def cleanup(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        self._state("CLEANING") if self.run else None
        try:
            self.adapter.stop()
            evidence["runtime"] = self.adapter.cleanup_identifiers()
        finally:
            if self.scope:
                evidence["scope"] = self.scope.cleanup()
            if self.transport:
                self.transport.stop()
            if self.run:
                secrets = self.run.root / "secrets"
                if secrets.exists():
                    shutil.rmtree(secrets)
                    evidence["secrets_destroyed"] = True
                self._record_runtime_core_hashes("after_cleanup")
                self._state("CLEANED", cleanup=evidence)
        return evidence

    def _record_runtime_core_hashes(self, phase: str) -> None:
        self._append_evidence(
            "runtime-core-hashes",
            {
                "phase": phase,
                "runner_sha256": digest_file(self.repository_root / "modeling_team/runner.py"),
                "codex_adapter_sha256": digest_file(
                    self.repository_root / "modeling_team/runtimes/codex.py"
                ),
            },
        )

    def _state(self, value: str, **extra: Any) -> None:
        if self.run:
            self._atomic_json(
                self.run.root / "state.json",
                {"state": value, "run_id": self.run.run_id, **extra},
            )

    def _append_evidence(self, name: str, value: dict[str, Any]) -> None:
        if not self.run:
            return
        path = self.run.root / "evidence" / f"{name}.jsonl"
        envelope = {"recorded_at": datetime.now(UTC).isoformat(), **value}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
