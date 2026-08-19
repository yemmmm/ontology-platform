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
import re
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
FORMAL_TYPED_CONFLICT_FIELDS = frozenset(
    {
        "original_delivery_id",
        "receipt_digest",
        "workspace_version",
        "mutation_state",
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


# Task-neutral envelope shape.  The task-aware gate below must stay in sync
# with ``acceptance.register_accepted_candidate``/``_safe_id``
# (``[a-z][a-z0-9-]{1,127}``), which is where an integer revision killed a
# complete formal run after gate acceptance (R2.3-008 start7).
_SAFE_REVISION_RE = re.compile(r"[a-z][a-z0-9-]{1,127}")


def _validate_task_revision(value: Any, *, integer_revisions: bool) -> None:
    """Task-aware revision gate that keeps the envelope and registration aligned.

    The neutral envelope validator stays task-agnostic (positive integer or
    nonempty string) because Protocol-side asset validation has no task
    context.  The formal progress gate, which the Runner constructs with the
    run's task context, applies the decisive rule here: a non-R2.3-003 run
    requires the exact safe stable string identifier that
    ``register_accepted_candidate`` demands, so an Agent choosing an integer
    gets a typed ``FormalCandidateError`` at the first delivery (before gate
    acceptance) instead of a run-killing registration error afterwards.
    R2.3-003 existing-scope runs keep the historical positive-integer envelope.
    """

    if integer_revisions:
        return
    if not isinstance(value, str) or not _SAFE_REVISION_RE.fullmatch(value):
        raise FormalCandidateError(
            "formal candidate revision must be a lowercase safe identifier "
            "string matching [a-z][a-z0-9-]{1,127}; integer revisions are only "
            "valid for R2.3-003 existing-scope tasks"
        )


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

    if not isinstance(conflict, dict) or set(conflict) not in (
        FORMAL_CONFLICT_FIELDS,
        FORMAL_CONFLICT_FIELDS | FORMAL_TYPED_CONFLICT_FIELDS,
    ):
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
    if set(conflict) == FORMAL_CONFLICT_FIELDS | FORMAL_TYPED_CONFLICT_FIELDS:
        if not _nonempty_string(conflict.get("original_delivery_id")):
            raise FormalCandidateError("formal candidate conflict original delivery is not bound")
        if not _nonempty_string(conflict.get("receipt_digest")):
            raise FormalCandidateError("formal candidate conflict receipt digest is not bound")
        if not _nonempty_string(conflict.get("workspace_version")):
            raise FormalCandidateError("formal candidate conflict workspace version is not bound")
        if conflict.get("mutation_state") != "zero-mutation":
            raise FormalCandidateError("formal candidate conflict mutation state is invalid")
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
    accepted_receipt_delivery_id: str | None = None
    accepted_receipt_digest: str | None = None
    receipt_invalidated: bool = False
    conflict_delivery_id: str | None = None
    dispatch_mode: str | None = None
    dispatch_turn_id: str | None = None
    turn_barrier_complete: bool = False
    redrive_count: int = 0
    active_elapsed: float = 0.0
    paused: bool = False


class FormalCandidateProgress:
    """Small CAS-like progress gate shared by the formal Runner drain loop.

    It deliberately knows no transport storage or runtime implementation.  The
    Runner supplies delivery identity, protocol thread identity, dispatch
    receipts, and observed AgentState values; this class only binds those facts
    into one pending candidate and one optional redrive.
    """

    def __init__(
        self,
        *,
        clock: Any,
        timeout_seconds: float = 120.0,
        allow_post_receipt_revision: bool = False,
        integer_revisions: bool = False,
    ):
        self.clock = clock
        self.timeout_seconds = float(timeout_seconds)
        # R2.3-003 existing-scope runs use the strictly positive integer
        # revision sequence; every other formal task must deliver the safe
        # stable string identifier that candidate registration requires.
        self._integer_revisions = bool(integer_revisions)
        # R2.3-003 existing-scope runs have one additional, explicitly
        # bounded transition: a receipt accepted before a live binding read
        # may be invalidated by a typed zero-mutation conflict.  R2.3-005 and
        # all legacy callers retain the original complete terminal latch.
        self._allow_post_receipt_revision = bool(allow_post_receipt_revision)
        self.pending: _PendingCandidate | None = None
        self._invalidated_original_delivery_ids: set[str] = set()
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

    @property
    def post_receipt_revision_enabled(self) -> bool:
        return self._allow_post_receipt_revision

    @property
    def paused(self) -> bool:
        return self.pending is not None and self.pending.paused

    @property
    def active_elapsed(self) -> float:
        if self.pending is None:
            return 0.0
        elapsed = self.pending.active_elapsed
        if self.pending.accepted_at is not None and not self.pending.paused:
            elapsed += max(0.0, self.clock() - self.pending.accepted_at)
        return elapsed

    def pause(self, *, now: float | None = None) -> None:
        """Freeze active-time accounting without changing candidate identity/state."""
        if self.pending is None or self.pending.paused:
            return
        current = self.clock() if now is None else now
        if self.pending.accepted_at is not None:
            self.pending.active_elapsed += max(0.0, current - self.pending.accepted_at)
            self.pending.accepted_at = None
        self.pending.paused = True

    def resume(self, *, now: float | None = None) -> None:
        """Resume one paused candidate using the same delivery/thread identity."""
        if self.pending is None or not self.pending.paused:
            return
        current = self.clock() if now is None else now
        # ``active_elapsed`` already contains the pre-pause interval. Start a
        # fresh interval here so deadline checks do not count it twice.
        self.pending.accepted_at = current
        self.pending.paused = False

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
        _validate_task_revision(
            detached["candidate_revision"], integer_revisions=self._integer_revisions
        )
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

    @staticmethod
    def _revision_is_newer(previous: Any, current: Any) -> bool:
        """Require a strictly increasing revision without guessing ordering.

        Positive integers (R2.3-003) and digit strings keep the numeric
        comparison.  Safe identifier strings (every other formal task) order
        deterministically by strict lexicographic increase; without this the
        safe-string contract could never satisfy a conflict revision.
        """

        if isinstance(previous, bool) or isinstance(current, bool):
            return False
        if isinstance(previous, int) and isinstance(current, int):
            return current > previous
        if isinstance(previous, str) and isinstance(current, str):
            if previous.isdigit() and current.isdigit():
                return int(current) > int(previous)
            return current > previous
        return False

    def reopen_after_registration_rejection(self) -> bool:
        """Migrate one complete candidate back to ``awaiting_revision``.

        R2.3-009 A-class: the Runner calls this after an accepted-candidate
        registration was rejected as Agent-controllable.  The receipt is
        invalidated exactly like a post-receipt conflict, so the next strictly
        newer standalone revision re-enters the normal revision gates while a
        stale receipt for the invalidated revision can never re-complete the
        gate.  The Runner must invalidate the acceptance-side registration in
        the same transition (see ``invalidate_accepted_candidate``).
        """

        pending = self.pending
        if (
            pending is None
            or pending.state != "complete"
            or self._timeout_latched
            or self._terminal_failure_latched
        ):
            return False
        pending.state = "awaiting_revision"
        # The Runner-delivered conflict notice is not a Broker delivery, so the
        # revision arrives standalone (the defect-11 path): candidate-shaped,
        # strictly newer, distinct digest, still gated below in observe_delivery.
        pending.conflict_delivery_id = None
        pending.receipt_invalidated = True
        self._invalidated_original_delivery_ids.add(pending.identity.original_delivery_id)
        pending.accepted_at = self.clock()
        pending.dispatch_turn_id = None
        pending.turn_barrier_complete = False
        pending.redrive_count = 0
        return True

    def _post_receipt_conflict_envelope(self, delivery: Any, value: Any) -> bool:
        pending = self.pending
        return bool(
            self._allow_post_receipt_revision
            and pending is not None
            and pending.state == "complete"
            and getattr(delivery, "sender_id", None) == pending.identity.protocol_agent_id
            and getattr(delivery, "recipient_id", None) == pending.attribution.sender_id
            and getattr(delivery, "expects_reply", None) is True
            # The original candidate reply slot is occupied by receipt-v1.  A
            # post-receipt conflict therefore gets its own Protocol->Modeling
            # request and binds the revision to this new delivery ID.
            and getattr(delivery, "reply_to_delivery_id", None) is None
            and isinstance(value, dict)
            and value.get("status") == "conflict"
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
        # The one exception is the explicit R2.3-003 pre-mutation replacement
        # transition, where a typed conflict is allowed to invalidate the
        # accepted receipt and reopen exactly one revision slot.
        sender_id = getattr(delivery, "sender_id", None)
        recipient_id = getattr(delivery, "recipient_id", None)
        expects_reply = getattr(delivery, "expects_reply", False)
        reply_to = getattr(delivery, "reply_to_delivery_id", None)
        value = self._decode_candidate(getattr(delivery, "text", None))
        if self._timeout_latched or self._terminal_failure_latched:
            return None
        if self.pending is not None and self.pending.state in self._TERMINAL_STATES:
            if not self._post_receipt_conflict_envelope(delivery, value):
                return None

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
        # start13 defect: the conflict's one-shot reply slot may already be
        # consumed by an earlier Modeling prose reply to that same conflict,
        # after which Team Transport rejects every further reversed send and
        # the bound revision can never be delivered.  A standalone complete
        # revision (no reply binding) then remains the only deliverable form;
        # in a formal run there is exactly one candidate lineage, so a
        # candidate-shaped strictly-newer standalone delivery while a revision
        # is awaited is unambiguous and is accepted as that revision.  The
        # revision gates below (strictly newer revision, distinct digest)
        # still apply unchanged, and non-candidate standalone text keeps the
        # interim-message ignore semantics.
        standalone_revision = (
            self.pending is not None
            and self.pending.state == "awaiting_revision"
            and sender_id == modeling_agent_id
            and recipient_id == protocol_agent_id
            and expects_reply is True
            and reply_to is None
            and value is not None
            and self._is_candidate_like(value)
        )
        revision = revision or standalone_revision
        if (initial and self.pending is None) or revision:
            if value is None or not self._is_candidate_like(value):
                # A Modeling->Protocol interim message (start12: prose status
                # while owner clarification was still pending) is transport
                # content, not a candidate.  Parsing belongs to the tool
                # layer, so non-candidate text is ignored exactly like JSON
                # that is not candidate-shaped instead of failing the run:
                # the startup barrier/redrive keeps requesting the candidate,
                # the conflict slot stays open for a proper revision, and the
                # dispatch deadline still bounds the wait.
                return None
            if revision:
                assert self.pending is not None
                revised_digest, _ = formal_candidate_digests(value)
                if not self._revision_is_newer(
                    self.pending.identity.candidate_revision,
                    value.get("candidate_revision"),
                ):
                    raise FormalCandidateError(
                        "formal candidate revision is not strictly newer than the invalidated receipt"
                    )
                if revised_digest == self.pending.identity.candidate_digest:
                    raise FormalCandidateError(
                        "formal candidate revision reuses the invalidated candidate digest"
                    )
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
        # R2.3-003 post-receipt conflicts are standalone requests because the
        # original Modeling->Protocol reply slot is already occupied by the
        # accepted receipt.  Their typed payload still binds the original
        # delivery and receipt digest below; the revision replies to this new
        # conflict delivery ID.
        post_receipt_conflict = self._post_receipt_conflict_envelope(delivery, value)
        response = response or post_receipt_conflict
        if not response or value is None or self.pending is None:
            return None
        identity = self.pending.identity
        status = value.get("status")
        if status == "accepted":
            # A receipt cannot be accepted twice.  In particular, an old
            # receipt arriving after a 003 conflict must not reopen the gate.
            if self.pending.state == "complete" or self.pending.receipt_invalidated:
                return None
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
            self.pending.accepted_receipt_delivery_id = self._delivery_id(delivery)
            self.pending.accepted_receipt_digest = canonical_digest(value)
            return "accepted"
        if status == "conflict":
            if self.pending.receipt_invalidated:
                return None
            if self.pending.state == "complete":
                if not self._post_receipt_conflict_envelope(delivery, value):
                    return None
                if set(value) != FORMAL_CONFLICT_FIELDS | FORMAL_TYPED_CONFLICT_FIELDS:
                    return None
                if value.get("original_delivery_id") != identity.original_delivery_id:
                    return None
                if value.get("receipt_digest") != self.pending.accepted_receipt_digest:
                    return None
            try:
                validate_formal_conflict(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return None
            if "original_delivery_id" in value and value.get("original_delivery_id") != identity.original_delivery_id:
                return None
            self.pending.state = "awaiting_revision"
            self.pending.conflict_delivery_id = self._delivery_id(delivery)
            self.pending.receipt_invalidated = True
            self._invalidated_original_delivery_ids.add(identity.original_delivery_id)
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

        if self._timeout_latched or self._terminal_failure_latched or self.pending is None:
            return False
        if self.pending.state in self._TERMINAL_STATES and not (
            self._allow_post_receipt_revision and self.pending.state == "complete"
        ):
            return False
        sender_id = getattr(delivery, "sender_id", None)
        recipient_id = getattr(delivery, "recipient_id", None)
        expects_reply = getattr(delivery, "expects_reply", None)
        reply_to = getattr(delivery, "reply_to_delivery_id", None)
        delivery_id = getattr(delivery, "delivery_id", None)
        if (
            sender_id == protocol_agent_id
            and recipient_id == modeling_agent_id
            and reply_to in self._invalidated_original_delivery_ids
            and delivery_id != self.pending.conflict_delivery_id
        ):
            return True
        standalone_post_receipt = (
            self._allow_post_receipt_revision
            and self.pending.state == "complete"
            and sender_id == protocol_agent_id
            and recipient_id == modeling_agent_id
            and expects_reply is True
            and reply_to is None
        )
        if standalone_post_receipt:
            value = self._decode_candidate(getattr(delivery, "text", None))
            if not isinstance(value, dict) or value.get("status") != "conflict":
                return True
            identity = self.pending.identity
            try:
                validate_formal_conflict(
                    value,
                    candidate_revision=identity.candidate_revision,
                    semantic_digest=identity.semantic_digest,
                    candidate_digest=identity.candidate_digest,
                )
            except FormalCandidateError:
                return True
            return not (
                set(value) == FORMAL_CONFLICT_FIELDS | FORMAL_TYPED_CONFLICT_FIELDS
                and value.get("original_delivery_id") == identity.original_delivery_id
                and value.get("receipt_digest") == self.pending.accepted_receipt_digest
            )
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
        if self.pending.receipt_invalidated:
            if status == "accepted":
                return True
            if status == "conflict":
                return getattr(delivery, "delivery_id", None) != self.pending.conflict_delivery_id
        if self.pending.state in self._TERMINAL_STATES:
            if (
                status == "accepted"
                and getattr(delivery, "delivery_id", None)
                == self.pending.accepted_receipt_delivery_id
            ):
                return False
            # Complete is normally terminal.  For 003, only a correctly bound
            # typed conflict is valid; any late receipt or malformed response
            # is quarantined as stale rather than delivered as ordinary text.
            if not self._post_receipt_conflict_envelope(delivery, value):
                return True
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
            if self.pending.state == "complete":
                return not (
                    set(value) == FORMAL_CONFLICT_FIELDS | FORMAL_TYPED_CONFLICT_FIELDS
                    and value.get("original_delivery_id") == identity.original_delivery_id
                    and value.get("receipt_digest") == self.pending.accepted_receipt_digest
                )
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
        self.pending.active_elapsed = 0.0
        self.pending.paused = False
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
        if self.pending.paused:
            return
        accepted_at = self.pending.accepted_at
        if accepted_at is None:
            return
        current = self.clock() if now is None else now
        if self.pending.active_elapsed + (current - accepted_at) >= self.timeout_seconds:
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
