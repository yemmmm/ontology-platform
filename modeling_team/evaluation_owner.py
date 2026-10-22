"""Original acceptance process's cooperative input and retained Consumer lifecycle."""
from __future__ import annotations

import json
import os
import select
import time
import threading
import hashlib
from functools import wraps
from pathlib import Path

from .outer_input import OuterInputFifo, OuterInputFramingError
from .runtimes.base import RuntimeDelivery
from .close_statistics import publish_close_statistics, register_statistics_link
from .task_budget import BudgetError, budget_for


class EvaluationStopped(RuntimeError):
    pass


def _serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


class EvaluationOwner:
    def __init__(self, root: Path):
        self._lock = threading.RLock()
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.fifo = OuterInputFifo(root / "input.fifo")
        self.fifo.open()
        self.current = None
        self.active = []
        self.executors = []
        self.retained = []
        self.receipts = {}
        self.consult_replies = []
        self.destroyed_members = []
        self.stopping = False
        self.task_closed = False
        self.pending_pause = None
        self._flow_message = None
        self.budget = budget_for(root)
        self.budget_owner_id = "evaluation:" + root.name.removesuffix(".owner")
        self._budget_control_epoch = None
        self._budget_paused = False
        self._pause_reasons = set()
        self._queued_controls = []
        self._save()

    def _identity(self, resource):
        packet = resource.spec.get("_packet")
        return {"role": resource.spec.get("v3_role"), "thread_id": resource.thread_id,
                **(resource.identity if getattr(resource, "runtime", None) == "dsh" else {"runtime": "codex"}),
                "question_ids": [q["question_id"] for q in getattr(packet, "payload", {}).get("questions", ())],
                "pid": getattr(resource.process, "pid", None),
                "alive": resource.process.poll() is None if resource.process else False,
                "task_closed": bool(getattr(resource, "task_closed", False)),
                "work_state": "blocked" if getattr(resource, "blocked_task", False) else "completed" if getattr(resource, "task_closed", False) else "working",
                "user_waiting": bool(getattr(resource, "user_waiting", False))}

    @_serialized
    def _save(self):
        value = {"owner_pid": os.getpid(), "task_closed": self.task_closed,
                 "lifecycle": "stopped" if getattr(self, "closed", False) else "stopping" if self.stopping else "standby" if self.task_closed else "active",
                 "current": self._identity(self.current) if self.current else None,
                 "active_members": [self._identity(r) for r in self.active],
                 "retained_members": [self._identity(r) for r in self.retained], "receipts": self.receipts}
        value["queued_controls"] = self._queued_controls
        if self.budget:
            value["budget_ref"] = str(self.budget.ref)
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

    @_serialized
    def bind(self, adapter, resource):
        if self.stopping:
            raise EvaluationStopped("explicit evaluation stop")
        self.active.append(resource)
        self.current = self.active[0]
        resource.spec["_evaluation_owner"] = self
        resource.spec["_owner_adapter"] = adapter
        statistics_root = getattr(resource, "statistics_root", None)
        if statistics_root is not None:
            register_statistics_link(self.root, statistics_root, "evaluation-owner-bound-member")
        sink = getattr(resource, "report_sink", None)
        if sink is not None:
            sink.flow_confirmation = lambda arguments: self.confirm(resource, arguments)
        if self.pending_pause and self._flow_message:
            receipt = self.receipts[self._flow_message["request_id"]]
            receipt.setdefault("target_threads", []).append(self._member_id(resource))
            receipt["status"] = "dispatch_started"
            self._dispatch_control(resource, self._flow_message)
        self._save()

    @staticmethod
    def _member_id(resource):
        return resource.identity["process_instance"] if getattr(resource, "runtime", None) == "dsh" else resource.thread_id

    @_serialized
    def confirm(self, resource, arguments):
        if not isinstance(arguments, dict) or set(arguments) != {"request_id", "action"}:
            raise ValueError("confirmation requires exactly request_id and action")
        identity, action = arguments["request_id"], arguments["action"]
        receipt = self.receipts.get(identity)
        if not receipt or receipt.get("action") != action or action not in {"pause", "resume"}:
            raise ValueError("confirm the actual current pause/resume request")
        if resource not in self.active and resource not in self.retained:
            raise ValueError("confirmation belongs to another current role")
        if resource.thread_id not in receipt.get("target_threads", [resource.thread_id]):
            raise ValueError("confirmation belongs to another control request")
        current = self._flow_message and self._flow_message.get("request_id") == identity
        if self.budget and (not current or (receipt.get("source") == "task_budget"
                           and receipt.get("epoch") != self.budget.show()["epoch"])):
            return {"status": "stale_control", "action": action}
        resource.user_waiting = action == "pause"
        confirmed = receipt.setdefault("confirmed_threads", [])
        if resource.thread_id not in confirmed:
            confirmed.append(resource.thread_id)
        if receipt.get("source") == "task_budget":
            member_budget = getattr(resource, "budget", None) or getattr(getattr(resource, "_child_agent", None), "budget", None)
            if member_budget is not None:
                member_budget.record_control(receipt["epoch"], "effective", action=action)
        if set(confirmed) == set(receipt.get("target_threads", confirmed)):
            receipt.update(status="effective", thread_id=resource.thread_id)
        self._record_budget_control(receipt)
        if action == "pause":
            self.pending_pause = identity
        elif receipt["status"] == "effective":
            self.pending_pause = None
        self._save()
        return {"status": "effective", "action": action}

    @_serialized
    def poll(self):
        if self.stopping:
            raise EvaluationStopped("explicit evaluation stop")
        # A completed peer may acknowledge a control request while another
        # question is still working. Drain it without waiting for global idle.
        for resource in self.retained:
            adapter = resource.spec["_owner_adapter"]
            native = getattr(resource, "runtime", None) == "dsh"
            messages = resource.messages() if native else adapter.receive_messages()
            for message in messages:
                if (native or message.agent_id == resource._child_agent.agent_id) and message.text.strip():
                    try:
                        confirmation = json.loads(message.text).get("flow_confirmation")
                        if confirmation is not None:
                            self.confirm(resource, confirmation)
                    except (ValueError, AttributeError):
                        pass
                    self.consult_replies.append({**self._identity(resource), "text": message.text})
                    self._save()
        def busy(resource):
            if getattr(resource, "runtime", None) == "dsh":
                return resource.agent.projection.activity is not None
            return bool(getattr(getattr(resource, "_child_agent", None), "active_turn_id", None))

        working = any(busy(resource) for resource in [*self.active, *self.retained])
        message = None
        if self._queued_controls and not working:
            message = self._queued_controls.pop(0)
            self.receipts.pop(message["request_id"], None)
        if message is None:
            message = self._next_budget_control()
        if message is None:
            if select.select([self.fifo], [], [], 0)[0]:
                self.fifo.read_ready()
            try:
                line = self.fifo.pop_line()
            except OuterInputFramingError:
                return
        else:
            line = json.dumps(message)
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
            if working:
                self._queued_controls.append(message)
                self.receipts[identity] = {"action": action, "status": "queued",
                                          "basis": "waiting_for_natural_turn_completion"}
                self._save()
                return
            cause = "task_budget" if message.get("source") == "task_budget" else "user"
            if cause == "task_budget" and self.budget and message.get("epoch") != self.budget.show()["epoch"]:
                return
            self.receipts[identity] = {"action": action, "status": "dispatch_started",
                                      **{k: message[k] for k in ("source", "epoch") if k in message}}
            self._save()
            if action == "stop":
                self.stopping = True
                self.receipts[identity]["status"] = "stopping"
                self._save()
                raise EvaluationStopped("explicit evaluation stop")
            if action == "pause":
                self._pause_reasons.add(cause)
            elif action == "resume":
                self._pause_reasons.discard(cause)
                if self._pause_reasons or (self.budget and not self.budget.show()["admission_open"]):
                    self.receipts[identity]["status"] = "pause_pending"
                    self._save()
                    return
            resources = list(self.active) + list(self.retained) if action in {"pause", "resume"} else list(self.active) or self.retained[:1]
            if action == "consult":
                resources = resources[:1]
            self.receipts[identity]["target_threads"] = [self._member_id(r) for r in resources]
            if action in {"pause", "resume"}:
                self._flow_message = message
            if action == "pause":
                self.pending_pause = identity
            if self.current is None and action in {"pause", "resume"}:
                # The owner can receive instructions between tasks, before the
                # next role exists. Hold that next task without creating a Judge.
                self.pending_pause = identity if action == "pause" else None
            if not resources:
                self.receipts[identity]["status"] = "owner_waiting" if action == "pause" else "owner_ready" if action == "resume" else "rejected_no_current_role"
            for resource in resources:
                self._dispatch_control(resource, message)
            self._record_budget_control(self.receipts[identity])
            self._save()
        except (ValueError, KeyError, TypeError):
            return

    def _next_budget_control(self):
        if not self.budget:
            return None
        try:
            self.budget.require_available(operation="evaluation")
        except BudgetError:
            pass
        state = self.budget.show()
        paused = not state["admission_open"]
        key = (state["epoch"], paused)
        if key == self._budget_control_epoch or not (paused or self._budget_paused):
            return None
        self._budget_control_epoch = key
        self._budget_paused = paused
        return {"source": "task_budget", "budget_ref": str(self.budget.ref),
                "epoch": state["epoch"], "reason": ",".join(state["pause_reasons"]),
                "request_id": "budget-" + str(state["epoch"]) + "-" + hashlib.sha256(self.budget_owner_id.encode()).hexdigest()[:20],
                "action": "pause" if paused else "resume", "text": "任务预算暂停" if paused else "按原任务预算继续"}

    def _record_budget_control(self, receipt):
        if self.budget and receipt.get("source") == "task_budget":
            status = receipt["status"]
            if status in {"owner_waiting", "owner_ready"}:
                status = "not_started"
            elif status in {"dispatch_started", "pause_pending"}:
                status = "pending"
            self.budget.record_control(self.budget_owner_id, receipt["epoch"], status,
                action=receipt["action"], confirmed_members=receipt.get("confirmed_threads", []),
                evidence_ref=str(self.root / "state.json"))

    def _dispatch_control(self, resource, message):
        """Called under the owner lock; release it across native dispatch."""
        identity = message["request_id"]
        action = message["action"]
        if getattr(resource, "runtime", None) == "dsh":
            try:
                # Process control is confirmed by actual PIDs, never model prose.
                evidence = resource.control(message)
                receipt = self.receipts[identity]
                receipt.setdefault("member_results", {})[self._member_id(resource)] = evidence
                if action in {"pause", "resume"}:
                    if evidence.get("status") != "effective":
                        receipt["status"] = "unknown"
                        return
                    confirmed = receipt.setdefault("confirmed_threads", [])
                    if self._member_id(resource) not in confirmed:
                        confirmed.append(self._member_id(resource))
                    if set(confirmed) == set(receipt.get("target_threads", confirmed)):
                        receipt["status"] = "effective"
                        self.pending_pause = identity if action == "pause" else None
                else:
                    receipt["status"] = evidence["status"]
            except Exception as exc:
                self.receipts[identity].update(status="unknown", detail=str(exc))
            return
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
            # The report socket may synchronously confirm from another
            # thread before the native RPC returns. Do not hold the
            # owner lock across that round trip.
            self._lock.release()
            try:
                dispatch = adapter.send_message(agent.agent_id, RuntimeDelivery(
                    sender_id="host/task-budget" if message.get("source") == "task_budget" else "user/outer", recipient_id=agent.agent_id,
                    kind="budget-control" if message.get("source") == "task_budget" else "user-control",
                    text=json.dumps({**message, "instruction": instruction}, ensure_ascii=False)))
            finally:
                self._lock.acquire()
            if self.receipts[identity]["status"] != "effective":
                self.receipts[identity]["status"] = (
                    "queued" if getattr(dispatch, "mode", None) == "enqueue" else "instruction_delivered")
        except Exception:
            self.receipts[identity]["status"] = "unknown"

    def before_next_task(self):
        self.poll()
        while self.pending_pause or (self.budget and not self.budget.show()["admission_open"]):
            self.poll()
            time.sleep(0.1)

    @_serialized
    def release(self, resource):
        if resource in self.active:
            self.active.remove(resource)
        self.current = self.active[0] if self.active else None
        self._save()

    def retain(self, resource):
        resource.task_closed = True
        resource.user_waiting = False
        resource._watchdog_stop.set()
        sink = getattr(resource, "report_sink", None)
        if sink is not None:
            sink.stop()
        with self._lock:
            if resource not in self.retained:
                self.retained.append(resource)
            self.release(resource)

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
                failures.append({**self._identity(resource), "cleanup_error": str(exc)})
        forwarder = getattr(self, "forwarder", None)
        try:
            if forwarder is not None:
                forwarder.stop()
        except Exception as exc:
            failures.append({"forwarder_cleanup_error": str(exc)})
        self.limits = failures
        for executor in self.executors:
            executor.shutdown(wait=True)
        self.executors.clear()
        self.closed = not failures and not self.retained
        if self.closed:
            self.current = None
            self.fifo.close()
        self._closing = False
        self._save()
        # No owner/control lock is held during offline report generation.
        self.close_statistics = publish_close_statistics(
            self.root, view="operation_close", task_ref=self.root.name,
            cleanup_complete=self.closed,
        )
        if failures:
            raise RuntimeError("evaluation cleanup is incomplete; see original owner state")
