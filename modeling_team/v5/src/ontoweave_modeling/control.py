"""Persisted input queue and admission at natural native-turn boundaries."""

from __future__ import annotations

import copy
import time
from collections.abc import Callable

from .workspace import WorkspaceRepository


class TaskControl:
    def __init__(self, repository: WorkspaceRepository, object_id: str = "task-control"):
        self.repository = repository
        self.object_id = object_id

    def _change(self, change: Callable[[dict], dict]) -> dict:
        while True:
            row = self.repository.get(self.object_id)
            state = (
                copy.deepcopy(row["content"])
                if row
                else {
                    "mode": "running",
                    "budget_open": True,
                    "active": {},
                    "messages": [],
                }
            )
            result = change(state)
            saved = self.repository.put(
                self.object_id, "task_control", state, row["revision"] if row else 0
            )
            if saved.get("code") == "version_conflict":
                continue
            if saved.get("status") != "recorded":
                raise RuntimeError(saved)
            return result

    def enqueue(self, message_id: str, kind: str, body: str = "", target: str | None = None):
        if kind not in {"input", "pause", "stop", "resume", "budget_pause", "budget_resume"}:
            raise ValueError("unsupported control message kind")

        def change(state):
            existing = next((m for m in state["messages"] if m["id"] == message_id), None)
            if existing:
                if (existing["kind"], existing["body"], existing["target"]) != (kind, body, target):
                    raise ValueError("message identity has different content")
                return existing
            message = {
                "id": message_id,
                "kind": kind,
                "body": body,
                "target": target,
                "status": "queued",
                "queued_at": time.time(),
            }
            state["messages"].append(message)
            return message

        return self._change(change)

    @staticmethod
    def _controls(state):
        for message in state["messages"]:
            if message["status"] != "queued" or message["kind"] == "input":
                continue
            kind = message["kind"]
            if kind in {"pause", "stop", "resume"}:
                state["mode"] = {"pause": "paused", "stop": "stopped", "resume": "running"}[kind]
            else:
                state["budget_open"] = kind == "budget_resume"
            message.update(status="effective", effective_at=time.time())

    @staticmethod
    def _status(state):
        if state["mode"] == "running" and state["budget_open"]:
            return "running"
        return "waiting_for_turn_end" if state["active"] else "settled"

    def begin_turn(self, unit: str, execution_id: str) -> dict:
        def change(state):
            self._controls(state)
            if unit in state["active"]:
                return {
                    "admitted": False,
                    "reason": "original_execution_active",
                    "execution_id": state["active"][unit],
                }
            if state["mode"] != "running" or not state["budget_open"]:
                return {
                    "admitted": False,
                    "mode": state["mode"],
                    "budget_open": state["budget_open"],
                    "status": self._status(state),
                }
            inputs = [
                m
                for m in state["messages"]
                if m["kind"] == "input"
                and m["target"] in {None, unit}
                and (
                    m["status"] == "queued"
                    or (m["status"] == "delivered" and m.get("delivered_to") == unit)
                )
            ]
            for message in inputs:
                prior = message.get("execution_id")
                message["previous_delivery_unconfirmed"] = prior is not None
                message.setdefault("deliveries", []).append(
                    {"execution_id": execution_id, "at": time.time()}
                )
                message.update(
                    status="delivered",
                    delivered_at=time.time(),
                    execution_id=execution_id,
                    delivered_to=unit,
                )
            state["active"][unit] = execution_id
            return {"admitted": True, "inputs": inputs}

        return self._change(change)

    def finish_turn(self, unit: str, execution_id: str, *, consumed_ids: tuple[str, ...] = ()):
        def change(state):
            if state["active"].get(unit) != execution_id:
                raise ValueError("finish must match the active execution")
            del state["active"][unit]
            for message in state["messages"]:
                if message["id"] in consumed_ids:
                    if (
                        message.get("execution_id") != execution_id
                        or message["status"] != "delivered"
                    ):
                        raise ValueError("consumption must match a delivered input")
                    message.update(status="consumed", consumed_at=time.time())
            self._controls(state)
            return {
                "mode": state["mode"],
                "status": self._status(state),
                "active": dict(state["active"]),
            }

        return self._change(change)

    def view(self) -> dict:
        row = self.repository.get(self.object_id)
        if row is None:
            return {"mode": "running", "status": "running", "active": {}, "messages": []}
        return {**row["content"], "status": self._status(row["content"])}
