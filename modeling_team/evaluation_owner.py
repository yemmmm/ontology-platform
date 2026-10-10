"""Original acceptance process's cooperative input and retained Consumer lifecycle."""
from __future__ import annotations

import json
import os
import select
import time
from pathlib import Path

from .outer_input import OuterInputFifo, OuterInputFramingError
from .runtimes.base import RuntimeDelivery


class EvaluationStopped(RuntimeError):
    pass


class EvaluationOwner:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fifo = OuterInputFifo(root / "input.fifo")
        self.fifo.open()
        self.current = None
        self.retained = []
        self.receipts = {}
        self.consult_replies = []
        self.destroyed_members = []
        self.stopping = False
        self.task_closed = False
        self.pending_pause = None
        self._save()

    def _identity(self, resource):
        return {"role": resource.spec.get("v3_role"), "thread_id": resource.thread_id,
                "pid": getattr(resource.process, "pid", None),
                "alive": resource.process.poll() is None if resource.process else False,
                "task_closed": bool(getattr(resource, "task_closed", False)),
                "work_state": "blocked" if getattr(resource, "blocked_task", False) else "completed" if getattr(resource, "task_closed", False) else "working",
                "user_waiting": bool(getattr(resource, "user_waiting", False))}

    def _save(self):
        value = {"owner_pid": os.getpid(), "task_closed": self.task_closed,
                 "lifecycle": "stopped" if getattr(self, "closed", False) else "stopping" if self.stopping else "standby" if self.task_closed else "active",
                 "current": self._identity(self.current) if self.current else None,
                 "retained_members": [self._identity(r) for r in self.retained], "receipts": self.receipts}
        value["stage_waiting"] = bool(self.current is None and self.pending_pause)
        value["consult_replies"] = self.consult_replies
        value["destroyed_members"] = self.destroyed_members
        value["limits"] = getattr(self, "limits", [])
        serialized = json.dumps(value, ensure_ascii=False)
        if getattr(self, "_last_state", None) == serialized:
            return
        temporary = self.root / "state.tmp"
        temporary.write_text(serialized)
        temporary.replace(self.root / "state.json")
        self._last_state = serialized

    def bind(self, adapter, resource):
        self.current = resource
        resource.spec["_evaluation_owner"] = self
        resource.spec["_owner_adapter"] = adapter
        sink = getattr(resource, "report_sink", None)
        if sink is not None:
            sink.flow_confirmation = lambda arguments: self.confirm(resource, arguments)
        self._save()

    def confirm(self, resource, arguments):
        if not isinstance(arguments, dict) or set(arguments) != {"request_id", "action"}:
            raise ValueError("confirmation requires exactly request_id and action")
        identity, action = arguments["request_id"], arguments["action"]
        receipt = self.receipts.get(identity)
        if not receipt or receipt.get("action") != action or action not in {"pause", "resume"}:
            raise ValueError("confirm the actual current pause/resume request")
        if self.current is not resource and resource not in self.retained:
            raise ValueError("confirmation belongs to another current role")
        resource.user_waiting = action == "pause"
        receipt.update(status="effective", thread_id=resource.thread_id)
        if action == "pause":
            self.pending_pause = identity
        else:
            self.pending_pause = None
        self._save()
        return {"status": "effective", "action": action}

    def poll(self):
        if self.current is None:
            for resource in self.retained:
                adapter = resource.spec["_owner_adapter"]
                for message in adapter.receive_messages():
                    if message.agent_id == resource._child_agent.agent_id and message.text.strip():
                        try:
                            confirmation = json.loads(message.text).get("flow_confirmation")
                            if confirmation is not None:
                                self.confirm(resource, confirmation)
                        except (ValueError, AttributeError):
                            pass
                        self.consult_replies.append({"role": "consumer", "thread_id": resource.thread_id, "text": message.text})
                        self._save()
        if select.select([self.fifo], [], [], 0)[0]:
            self.fifo.read_ready()
        try:
            line = self.fifo.pop_line()
        except OuterInputFramingError:
            return
        if line is None:
            self._save()
            return
        try:
            message = json.loads(line)
            identity = message["request_id"]
            if identity in self.receipts:
                return
            action, text = message["action"], message["text"]
            if action not in {"consult", "pause", "resume", "stop"} or not isinstance(text, str):
                raise ValueError("unsupported evaluation control")
            self.receipts[identity] = {"action": action, "status": "dispatch_started"}
            self._save()
            if action == "stop":
                self.stopping = True
                self.receipts[identity]["status"] = "stopping"
                self._save()
                raise EvaluationStopped("explicit evaluation stop")
            resource = self.current or (self.retained[0] if self.retained else None)
            if self.current is None and action in {"pause", "resume"}:
                # The owner can receive instructions between tasks, before the
                # next role exists. Hold that next task without creating a Judge.
                self.pending_pause = identity if action == "pause" else None
            if resource is None:
                self.receipts[identity]["status"] = "owner_waiting" if action == "pause" else "owner_ready" if action == "resume" else "rejected_no_current_role"
            else:
                adapter = resource.spec["_owner_adapter"]
                agent = resource._child_agent
                # Reuse the native dispatch contract on the SAME thread.  Unknown RPC receipts
                # remain unknown; they are never automatically replayed.
                adapter.agents[agent.agent_id] = agent
                resource.terminal_event = False
                instruction = ("请自行等待，不继续原验收任务，并调用 record_flow_confirmation 确认。" if action == "pause"
                               else "沿原任务继续，勿重复已提交题目，并调用 record_flow_confirmation 确认。" if action == "resume"
                               else "只读追问；原报告固定，不重新提交或覆盖报告。")
                if getattr(resource, "task_closed", False) and action in {"pause", "resume"}:
                    instruction = '原报告入口已关闭，请自行等待/继续只读对话，并在回复正文提交 {"flow_confirmation":{"request_id":"本消息ID","action":"本动作"}} 确认。'
                try:
                    metrics = getattr(resource, "metrics", None)
                    if metrics is not None:
                        metrics.allow_control_turn()
                    dispatched = adapter.send_message(agent.agent_id, RuntimeDelivery(sender_id="user/outer", recipient_id=agent.agent_id,
                        kind="user-control", text=json.dumps({**message, "instruction": instruction}, ensure_ascii=False)))
                    if metrics is not None and getattr(dispatched, "mode", None) == "steer":
                        metrics._pending_control_turn = False
                    if self.receipts[identity]["status"] != "effective":
                        self.receipts[identity]["status"] = "instruction_delivered"
                except Exception:
                    self.receipts[identity]["status"] = "unknown"
            self._save()
        except (ValueError, KeyError, TypeError):
            return

    def before_next_task(self):
        self.poll()
        while self.pending_pause:
            self.poll()
            time.sleep(0.1)

    def retain(self, resource):
        resource.task_closed = True
        resource.user_waiting = False
        resource._watchdog_stop.set()
        sink = getattr(resource, "report_sink", None)
        if sink is not None:
            sink.stop()
        if resource not in self.retained:
            self.retained.append(resource)
        self.current = None
        self._save()

    def wait(self):
        self.task_closed = True
        self.current = None
        self._save()
        try:
            while self.retained:
                self.poll()
                if not any(self._identity(r)["alive"] for r in self.retained):
                    break
                time.sleep(0.1)
        except EvaluationStopped:
            pass
        finally:
            self.close()

    def close(self):
        if getattr(self, "closed", False) or getattr(self, "_closing", False):
            return
        self._closing = True
        self.stopping = True
        failures = []
        for resource in list(self.retained):
            try:
                private_root = Path(resource.spec["private_root"])
                resource.destroy()
                self.destroyed_members.append({**self._identity(resource), "child_destroyed": resource.destroyed,
                                               "private_root_removed": not private_root.exists()})
                adapter = resource.spec.get("_owner_adapter")
                if adapter is not None:
                    adapter._stop_standalone_provider_sessions()
                self.retained.remove(resource)
            except Exception as exc:
                failures.append({"thread_id": resource.thread_id, "cleanup_error": str(exc)})
        forwarder = getattr(self, "forwarder", None)
        try:
            if forwarder is not None:
                forwarder.stop()
        except Exception as exc:
            failures.append({"forwarder_cleanup_error": str(exc)})
        self.limits = failures
        self.closed = not failures and not self.retained
        if self.closed:
            self.current = None
            self.fifo.close()
        self._closing = False
        self._save()
        if failures:
            raise RuntimeError("evaluation cleanup is incomplete; see original owner state")
