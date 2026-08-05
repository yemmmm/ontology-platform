"""The stable Team Runner Runtime Adapter boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeIdentity:
    agent_id: str
    runtime_identity: str


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

    def __post_init__(self) -> None:
        if self.mode not in {"start", "steer"}:
            raise ValueError("runtime dispatch mode must be start or steer")
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


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    state: str
    last_started_turn_id: str | None = None
    last_completed_turn_id: str | None = None


class RuntimeAdapter(ABC):
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
