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
class RuntimeDelivery:
    """A mechanically attributed inbound delivery for one Runtime thread."""

    sender_id: str
    recipient_id: str
    kind: str
    text: str
    delivery_id: str | None = None
    expects_reply: bool = False
    reply_to_delivery_id: str | None = None


@dataclass(frozen=True)
class AgentState:
    agent_id: str
    state: str


class RuntimeAdapter(ABC):
    def terminal_report_blocked(
        self, agent_id: str, already_synchronized: bool = False
    ) -> bool:
        """Return whether a terminal report must be rejected before broker mutation."""
        del agent_id, already_synchronized
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
    def send_message(self, agent_id: str, delivery: RuntimeDelivery) -> None: ...
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
