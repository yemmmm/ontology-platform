"""The stable Team Runner Runtime Adapter boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeIdentity:
    agent_id: str
    runtime_identity: str
    runtime: str = "codex"
    process_instance: str | None = None
    activity_id: str | None = None


@dataclass(frozen=True)
class RuntimeMessage:
    agent_id: str
    text: str
    kind: str = "text"


@dataclass(frozen=True)
class RuntimeDispatchReceipt:
    """Identity returned by a runtime dispatch.

    ``turn_id`` is optional for legacy adapters and fake runtimes.  The formal
    R2.3-005 gate treats a missing id as a platform-contract failure, while
    older gates continue to accept ``None`` for backwards compatibility.
    """

    mode: str
    turn_id: str | None
    runtime: str = "codex"
    dispatch_id: str | None = None
    runtime_identity: str | None = None
    message_id: str | None = None
    process_instance: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"start", "steer", "enqueue"}:
            raise ValueError("runtime dispatch mode must be start, steer or enqueue")
        if self.mode == "enqueue" and (
            self.runtime != "dsh" or self.turn_id is not None
            or not all((self.dispatch_id, self.runtime_identity, self.message_id))
        ):
            raise ValueError("DSH enqueue requires dispatch/session/message identities and null turn_id")
        if self.turn_id is not None and not isinstance(self.turn_id, str):
            raise TypeError("runtime dispatch turn_id must be a string or null")


@dataclass(frozen=True)
class RuntimeDelivery:
    """A mechanically attributed inbound delivery for one Runtime thread."""

    sender_id: str
    recipient_id: str
    kind: str
    text: str
    delivery_id: str | None = None
    expects_reply: bool = False
    reply_to_delivery_id: str | None = None
    owner_answer_id: str | None = None
    release_id: str | None = None
    display_text: str | None = None
    body_ref: dict | None = None
    material_refs: tuple[dict, ...] = ()


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    state: str
    last_started_turn_id: str | None = None
    last_completed_turn_id: str | None = None
    runtime: str = "codex"
    runtime_identity: str | None = None
    activity_id: str | None = None
    pending_dispatches: tuple[dict[str, Any], ...] = ()


class RuntimeAdapter(ABC):
    runtime = "codex"

    def runtime_identity(self, agent_id: str) -> AgentRuntimeIdentity | None:
        """Public identity, including the original native Codex thread/turn."""
        agent = getattr(self, "agents", {}).get(agent_id)
        identity = getattr(agent, "thread_id", None)
        return (AgentRuntimeIdentity(agent_id, identity, activity_id=getattr(agent, "active_turn_id", None))
                if identity else None)

    def dispatch_status(self, agent_id: str) -> list[dict[str, Any]]:
        return []

    def provider_wait_status(self, agent_id: str) -> dict[str, Any] | None:
        return getattr(getattr(self, "agents", {}).get(agent_id), "provider_wait", None)

    def consume_provider_waits(self) -> list[tuple[str, dict[str, Any]]]:
        return []

    def recover_provider_wait(
        self, agent_id: str, text: str, *, wait_id: str | None = None,
        sender_id: str = "user/outer",
    ) -> RuntimeDispatchReceipt:
        raise NotImplementedError("this runtime does not support provider wait recovery")

    def terminal_report_blocked(
        self,
        agent_id: str,
        already_synchronized: bool = False,
        status: str = "completed",
    ) -> bool:
        """Return whether a terminal report must be rejected before broker mutation."""
        del agent_id, already_synchronized, status
        return False

    @abstractmethod
    def start_roster(self, run: Any, agents: Any) -> list[AgentRuntimeIdentity]: ...
    @abstractmethod
    def probe_role_visibility(self, run: Any) -> dict[str, Any]: ...
    @abstractmethod
    def start_task(
        self, agent_id: str, task_text: str, skill_paths: list[str], roster: list[str]
    ) -> None: ...
    @abstractmethod
    def send_message(
        self, agent_id: str, delivery: RuntimeDelivery
    ) -> RuntimeDispatchReceipt | None: ...
    @abstractmethod
    def receive_messages(self) -> list[RuntimeMessage]: ...
    @abstractmethod
    def get_agent_states(self) -> list[AgentState]: ...
    @abstractmethod
    def wait_settled(self, agent_ids: list[str], timeout: float) -> bool: ...
    @abstractmethod
    def pause(self) -> None: ...
    @abstractmethod
    def resume(self) -> None: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def cleanup_identifiers(self) -> dict[str, Any]: ...
