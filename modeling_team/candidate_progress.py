"""Formal-only candidate progress primitives for the R2.3-005 handoff.

The older neutral-candidate receipt remains intentionally permissive because it
is used by the v1/R2.3-002 smoke paths.  This module is the stricter contract
used only by the formal acceptance runner: a candidate is a complete immutable
envelope and every receipt is bound to the exact candidate and revision.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


FORMAL_CANDIDATE_KIND = "platform-neutral-candidate-v2"
FORMAL_CANDIDATE_FIELDS = frozenset(
    {"candidate_kind", "candidate_revision", "scope", "constraints", "items"}
)
FORMAL_RECEIPT_FIELDS = frozenset(
    {"status", "candidate_revision", "semantic_digest", "candidate_digest"}
)
FORMAL_CONFLICT_FIELDS = frozenset(
    {
        "status",
        "candidate_revision",
        "semantic_digest",
        "candidate_digest",
        "conflict_code",
        "conflict_detail",
    }
)


class FormalCandidateError(ValueError):
    """A formal candidate or its progress envelope is not contract-valid."""


class FormalCandidateProgressTimeout(TimeoutError):
    """The bounded formal candidate/revision handoff did not complete."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FormalCandidateError("formal candidate is not canonical JSON") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_revision(value: Any) -> None:
    if isinstance(value, bool) or not (
        (isinstance(value, int) and value > 0) or _nonempty_string(value)
    ):
        raise FormalCandidateError("formal candidate revision is invalid")


def validate_formal_candidate(candidate: Any) -> dict[str, Any]:
    """Return a detached candidate after validating the exact formal envelope."""

    if not isinstance(candidate, dict):
        raise FormalCandidateError("formal candidate must be an object")
    if set(candidate) != FORMAL_CANDIDATE_FIELDS:
        missing = sorted(FORMAL_CANDIDATE_FIELDS - set(candidate))
        extra = sorted(set(candidate) - FORMAL_CANDIDATE_FIELDS)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise FormalCandidateError(
            "formal candidate fields are not exact" + (f" ({'; '.join(details)})" if details else "")
        )
    if candidate.get("candidate_kind") != FORMAL_CANDIDATE_KIND:
        raise FormalCandidateError("formal candidate kind is not platform-neutral-candidate-v2")
    _validate_revision(candidate.get("candidate_revision"))
    scope = candidate.get("scope")
    if not (_nonempty_string(scope) or (isinstance(scope, dict) and bool(scope))):
        raise FormalCandidateError("formal candidate scope is not bound")
    constraints = candidate.get("constraints")
    if not isinstance(constraints, list) or any(not _nonempty_string(item) for item in constraints):
        raise FormalCandidateError("formal candidate constraints must be a string list")
    items = candidate.get("items")
    if not isinstance(items, list) or not items:
        raise FormalCandidateError("formal candidate items are empty")
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise FormalCandidateError("formal candidate item must be an object")
        for field in ("item_id", "item_kind"):
            if not _nonempty_string(item.get(field)):
                raise FormalCandidateError(f"formal candidate {field} is not bound")
        if item["item_id"] in item_ids:
            raise FormalCandidateError("formal candidate item IDs are duplicated")
        item_ids.add(item["item_id"])
        if "semantic" not in item or item["semantic"] is None:
            raise FormalCandidateError("formal candidate semantic payload is missing")
        citations = item.get("evidence_citations")
        if citations is not None and (
            not isinstance(citations, list)
            or any(not isinstance(citation, dict) for citation in citations)
        ):
            raise FormalCandidateError("formal candidate evidence citations are invalid")
    try:
        detached = copy.deepcopy(candidate)
        _canonical_bytes(detached)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, FormalCandidateError):
            raise
        raise FormalCandidateError("formal candidate is not JSON") from exc
    return detached


def formal_semantic_value(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_kind": candidate["candidate_kind"],
        "candidate_revision": candidate["candidate_revision"],
        "scope": candidate["scope"],
        "constraints": candidate["constraints"],
        "items": candidate["items"],
    }


def formal_candidate_digests(candidate: Any) -> tuple[str, str]:
    """Return ``(candidate_digest, semantic_digest)`` for a complete candidate."""

    detached = validate_formal_candidate(candidate)
    return canonical_digest(detached), canonical_digest(formal_semantic_value(detached))


def validate_formal_receipt(
    receipt: Any,
    *,
    candidate_revision: Any,
    semantic_digest: str,
    candidate_digest: str,
) -> dict[str, Any]:
    """Validate the exact four-field accepted receipt against pending identity."""

    if not isinstance(receipt, dict) or set(receipt) != FORMAL_RECEIPT_FIELDS:
        raise FormalCandidateError("formal candidate receipt fields are not exact")
    if receipt.get("status") != "accepted":
        raise FormalCandidateError("formal candidate receipt status is not accepted")
    if receipt.get("candidate_revision") != candidate_revision:
        raise FormalCandidateError("formal candidate receipt revision does not match")
    if receipt.get("semantic_digest") != semantic_digest:
        raise FormalCandidateError("formal candidate receipt semantic digest does not match")
    if receipt.get("candidate_digest") != candidate_digest:
        raise FormalCandidateError("formal candidate receipt candidate digest does not match")
    return dict(receipt)


def validate_formal_conflict(
    conflict: Any,
    *,
    candidate_revision: Any,
    semantic_digest: str,
    candidate_digest: str,
) -> dict[str, Any]:
    """Validate the exact six-field formal conflict against pending identity."""

    if not isinstance(conflict, dict) or set(conflict) != FORMAL_CONFLICT_FIELDS:
        raise FormalCandidateError("formal candidate conflict fields are not exact")
    if conflict.get("status") != "conflict":
        raise FormalCandidateError("formal candidate conflict status is not conflict")
    if conflict.get("candidate_revision") != candidate_revision:
        raise FormalCandidateError("formal candidate conflict revision does not match")
    if conflict.get("semantic_digest") != semantic_digest:
        raise FormalCandidateError("formal candidate conflict semantic digest does not match")
    if conflict.get("candidate_digest") != candidate_digest:
        raise FormalCandidateError("formal candidate conflict candidate digest does not match")
    if not _nonempty_string(conflict.get("conflict_code")):
        raise FormalCandidateError("formal candidate conflict code is not bound")
    if not _nonempty_string(conflict.get("conflict_detail")):
        raise FormalCandidateError("formal candidate conflict detail is not bound")
    return dict(conflict)


@dataclass(frozen=True)
class CandidateIdentity:
    """Stable identity carried through candidate receipt/revision progress."""

    run_id: str
    protocol_agent_id: str
    protocol_thread_id: str
    original_delivery_id: str
    candidate_revision: Any
    semantic_digest: str
    candidate_digest: str


@dataclass(frozen=True)
class CandidateRuntimeAttribution:
    """The immutable Runtime envelope retained for a formal candidate redrive.

    The candidate text is deliberately kept as the original string rather than being
    reconstructed from the parsed JSON object.  This preserves Unicode, whitespace,
    and key order while keeping the redrive bound to the original Team Transport
    request identity.
    """

    sender_id: str
    recipient_id: str
    delivery_id: str
    expects_reply: bool
    reply_to_delivery_id: str | None
    text: str


class FormalCandidatePlatformContractError(RuntimeError):
    """A formal dispatch did not expose the turn identity required by the gate."""

    category = "platform-contract"


class FormalCandidateRoutingError(RuntimeError):
    """The bounded formal redrive completed without a valid Protocol response."""

    category = "collaboration/routing"


@dataclass
class _PendingCandidate:
    identity: CandidateIdentity
    candidate: dict[str, Any]
    attribution: CandidateRuntimeAttribution
    state: str
    accepted_at: float | None = None
    conflict_delivery_id: str | None = None
    dispatch_mode: str | None = None
    dispatch_turn_id: str | None = None
    turn_barrier_complete: bool = False
    redrive_count: int = 0


class FormalCandidateProgress:
    """Small CAS-like progress gate shared by the formal Runner drain loop.

    It deliberately knows no transport storage or runtime implementation.  The
    Runner supplies delivery identity, protocol thread identity, dispatch
    receipts, and observed AgentState values; this class only binds those facts
    into one pending candidate and one optional redrive.
    """

    def __init__(self, *, clock: Any, timeout_seconds: float = 120.0):
        self.clock = clock
        self.timeout_seconds = float(timeout_seconds)
        self.pending: _PendingCandidate | None = None
        self._timeout_latched = False
        self._terminal_failure_latched = False

    _TERMINAL_STATES = frozenset({"complete", "exhausted", "terminal_failure"})

    @property
    def state(self) -> str:
        return self.pending.state if self.pending is not None else "idle"

    @property
    def identity(self) -> CandidateIdentity | None:
        return self.pending.identity if self.pending is not None else None

    @property
    def candidate(self) -> dict[str, Any] | None:
        return self.pending.candidate if self.pending is not None else None

    @property
    def original_runtime_attribution(self) -> CandidateRuntimeAttribution | None:
        return self.pending.attribution if self.pending is not None else None

    @property
    def timeout_latched(self) -> bool:
        return self._timeout_latched

    @property
    def terminal_failure_latched(self) -> bool:
        return self._terminal_failure_latched

    def mark_terminal_failure(self) -> None:
        """Latch terminal failure without replacing the retained identity/state."""

        self._terminal_failure_latched = True

    @staticmethod
    def _decode_candidate(text: Any) -> dict[str, Any] | None:
        if not isinstance(text, str):
            return None
        try:
            value = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _is_candidate_like(value: Mapping[str, Any]) -> bool:
        return any(field in value for field in FORMAL_CANDIDATE_FIELDS)

    @staticmethod
    def _delivery_id(delivery: Any) -> str:
        value = getattr(delivery, "delivery_id", None)
        if not isinstance(value, str) or not value:
            raise FormalCandidateError("formal candidate delivery ID is not bound")
        return value

    def _new_pending(
        self,
        candidate: dict[str, Any],
        *,
        delivery: Any,
        run_id: str,
        protocol_agent_id: str,
        protocol_thread_id: str,
        delivery_id: str,
        state: str,
    ) -> None:
        detached = validate_formal_candidate(candidate)
        candidate_digest, semantic_digest = formal_candidate_digests(detached)
        text = getattr(delivery, "text", None)
        sender_id = getattr(delivery, "sender_id", None)
        recipient_id = getattr(delivery, "recipient_id", None)
        expects_reply = getattr(delivery, "expects_reply", None)
        reply_to_delivery_id = getattr(delivery, "reply_to_delivery_id", None)
        if (
            not isinstance(text, str)
            or not isinstance(sender_id, str)
            or not sender_id
            or not isinstance(recipient_id, str)
            or not recipient_id
            or not isinstance(expects_reply, bool)
            or (reply_to_delivery_id is not None and not isinstance(reply_to_delivery_id, str))
        ):
            raise FormalCandidateError("formal candidate Runtime attribution is invalid")
        self.pending = _PendingCandidate(
            identity=CandidateIdentity(
                run_id=run_id,
                protocol_agent_id=protocol_agent_id,
                protocol_thread_id=protocol_thread_id,
                original_delivery_id=delivery_id,
                candidate_revision=detached["candidate_revision"],
                semantic_digest=semantic_digest,
                candidate_digest=candidate_digest,
            ),
            candidate=detached,
            attribution=CandidateRuntimeAttribution(
                sender_id=sender_id,
                recipient_id=recipient_id,
                delivery_id=delivery_id,
                expects_reply=expects_reply,
                reply_to_delivery_id=reply_to_delivery_id,
                text=text,
            ),
            state=state,
        )

    def observe_delivery(
        self,
        delivery: Any,
        *,
        modeling_agent_id: str,
        protocol_agent_id: str,
        run_id: str,
        protocol_thread_id: str,
    ) -> str | None:
        """Observe one TeamTransport delivery; invalid receipts never clear pending."""

        # A terminal progress decision wins over every late transport delivery.
        # Check this before decoding or binding anything so timeout/exhaustion
        # cannot be resurrected by an accepted receipt, conflict, or revision.
        if self._timeout_latched or self._terminal_failure_latched:
            return None
        if self.pending is not None and self.pending.state in self._TERMINAL_STATES:
            return None

        sender_id = getattr(delivery, "sender_id", None)
        recipient_id = getattr(delivery, "recipient_id", None)
        expects_reply = getattr(delivery, "expects_reply", False)
        reply_to = getattr(delivery, "reply_to_delivery_id", None)
        value = self._decode_candidate(getattr(delivery, "text", None))

        initial = (
            sender_id == modeling_agent_id
            and recipient_id == protocol_agent_id
            and expects_reply is True
            and reply_to is None
        )
        revision = (
            self.pending is not None
            and self.pending.state == "awaiting_revision"
            and sender_id == modeling_agent_id
            and recipient_id == protocol_agent_id
            and expects_reply is True
            and reply_to == self.pending.conflict_delivery_id
        )
        if (initial and self.pending is None) or revision:
            if value is None:
                raise FormalCandidateError("formal candidate delivery is not canonical JSON")
            if not self._is_candidate_like(value):
                return None
            self._new_pending(
                value,
                delivery=delivery,
                run_id=run_id,
                protocol_agent_id=protocol_agent_id,
                protocol_thread_id=protocol_thread_id,
                delivery_id=self._delivery_id(delivery),
                state="awaiting_receipt",
            )
            return "revision" if revision else "candidate"

        response = (
            self.pending is not None
            and sender_id == protocol_agent_id
            and recipient_id == modeling_agent_id
            and isinstance(expects_reply, bool)
            and reply_to == self.pending.identity.original_delivery_id
        )
        if not response or value is None or self.pending is None:
            return None
        identity = self.pending.identity
        status = value.get("status")
        if status == "accepted":
            try:
                validate_formal_receipt(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return None
            self.pending.state = "complete"
            return "accepted"
        if status == "conflict":
            try:
                validate_formal_conflict(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return None
            self.pending.state = "awaiting_revision"
            self.pending.conflict_delivery_id = self._delivery_id(delivery)
            self.pending.accepted_at = self.clock()
            self.pending.dispatch_turn_id = None
            self.pending.turn_barrier_complete = False
            return "conflict"
        return None

    def is_invalid_response(
        self,
        delivery: Any,
        *,
        modeling_agent_id: str,
        protocol_agent_id: str,
    ) -> bool:
        """Identify a bound Protocol response that the formal validator rejects.

        This is intentionally separate from :meth:`observe_delivery`: invalid responses
        do not advance semantic progress, but the Runner still needs to tell the Broker
        that one formal-only replacement reply slot may be reopened.  Free text is a
        bound response with an invalid payload and is therefore included.
        """

        if (
            self._timeout_latched
            or self._terminal_failure_latched
            or self.pending is None
            or self.pending.state in self._TERMINAL_STATES
        ):
            return False
        sender_id = getattr(delivery, "sender_id", None)
        recipient_id = getattr(delivery, "recipient_id", None)
        reply_to = getattr(delivery, "reply_to_delivery_id", None)
        delivery_id = getattr(delivery, "delivery_id", None)
        if (
            sender_id != protocol_agent_id
            or recipient_id != modeling_agent_id
            or reply_to != self.pending.identity.original_delivery_id
            or not isinstance(delivery_id, str)
            or not delivery_id
        ):
            return False
        value = self._decode_candidate(getattr(delivery, "text", None))
        if value is None:
            return True
        identity = self.pending.identity
        status = value.get("status")
        if status == "accepted":
            try:
                validate_formal_receipt(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return True
            return False
        if status == "conflict":
            try:
                validate_formal_conflict(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return True
            return False
        return True

    def bind_dispatch(self, receipt: Any, *, now: float | None = None) -> None:
        if self.pending is None or self.pending.state != "awaiting_receipt":
            return
        turn_id = getattr(receipt, "turn_id", None) if receipt is not None else None
        mode = getattr(receipt, "mode", None) if receipt is not None else None
        if not isinstance(turn_id, str) or not turn_id:
            raise FormalCandidatePlatformContractError(
                "formal candidate dispatch did not return a non-empty turn_id"
            )
        if mode not in {"start", "steer"}:
            raise FormalCandidatePlatformContractError("formal candidate dispatch mode is invalid")
        self.pending.dispatch_mode = mode
        self.pending.dispatch_turn_id = turn_id
        self.pending.accepted_at = self.clock() if now is None else now
        self.pending.turn_barrier_complete = False

    def observe_states(self, states: Any, *, protocol_agent_id: str) -> bool:
        if self.pending is None or not isinstance(states, list):
            return False
        turn_id = self.pending.dispatch_turn_id
        if not isinstance(turn_id, str):
            return False
        for state in states:
            if getattr(state, "agent_id", None) != protocol_agent_id:
                continue
            if (
                getattr(state, "last_started_turn_id", None) == turn_id
                and getattr(state, "last_completed_turn_id", None) == turn_id
            ):
                self.pending.turn_barrier_complete = True
                return True
        return False

    def check_deadline(self, *, now: float | None = None) -> None:
        if self._timeout_latched:
            raise FormalCandidateProgressTimeout(
                f"formal candidate progress exceeded {self.timeout_seconds:.0f}s"
            )
        if self.pending is None or self.pending.state in self._TERMINAL_STATES:
            return
        accepted_at = self.pending.accepted_at
        if accepted_at is None:
            return
        current = self.clock() if now is None else now
        if current - accepted_at >= self.timeout_seconds:
            self._timeout_latched = True
            raise FormalCandidateProgressTimeout(
                f"formal candidate progress exceeded {self.timeout_seconds:.0f}s"
            )

    def redrive_ready(self, *, now: float | None = None) -> bool:
        self.check_deadline(now=now)
        if self.pending is None or not self.pending.turn_barrier_complete:
            return False
        if self.pending.state == "awaiting_receipt" and self.pending.redrive_count == 0:
            return True
        if self.pending.state == "redrive_sent":
            self.pending.state = "exhausted"
            raise FormalCandidateRoutingError(
                "formal candidate redrive completed without a valid receipt or conflict"
            )
        return False

    def mark_redrive_dispatch(self, receipt: Any, *, now: float | None = None) -> None:
        if self.pending is None or self.pending.state != "awaiting_receipt":
            return
        if self.pending.redrive_count != 0:
            raise FormalCandidateRoutingError("formal candidate redrive was attempted more than once")
        self.pending.redrive_count = 1
        self.pending.turn_barrier_complete = False
        self.pending.dispatch_mode = None
        self.pending.dispatch_turn_id = None
        self.bind_dispatch(receipt, now=now)
        self.pending.state = "redrive_sent"

    def redrive_text(self) -> str:
        if self.pending is None:
            raise FormalCandidateError("formal candidate redrive has no pending identity")
        return self.pending.attribution.text
