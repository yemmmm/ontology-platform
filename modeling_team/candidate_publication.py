"""Runtime-neutral staged candidate validation and typed publication."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .candidate_progress import (
    FormalCandidateError,
    formal_candidate_digests,
    validate_formal_candidate,
    validate_formal_receipt,
)
from .contracts import TeamConfigurationError
from .task_overlay import TaskInputOverlay


_CARRIER_FIELDS = {
    "acceptance_scope",
    "accepted_delivery_id",
    "accepted_receipt",
    "candidate",
    "candidate_identity",
    "candidate_text",
    "continuation_directive",
    "owner_answers",
    "provenance",
    "read_only_diagnosis",
    "revision_request",
    "schema_version",
    "source_delivery_id",
    "source_protocol_conflict",
    "source_run_id",
    "terminal_blocker",
}


class _DuplicateJsonKey(ValueError):
    pass


class CandidatePublicationError(TeamConfigurationError):
    """A staged candidate cannot be published through the fixed contract."""


def _strict_json_loads(value: bytes | str) -> Any:
    def object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, child in pairs:
            if key in result:
                raise _DuplicateJsonKey(key)
            result[key] = child
        return result

    return json.loads(value, object_pairs_hook=object_from_pairs)


@dataclass(frozen=True)
class CandidatePublicationIdentity:
    candidate_revision: Any
    candidate_digest: str
    semantic_digest: str
    source_run_id: str
    source_delivery_id: str
    accepted_delivery_id: str


@dataclass(frozen=True)
class ValidatedCandidatePublication:
    carrier_bytes: bytes
    carrier_digest: str
    candidate_text: str
    identity: CandidatePublicationIdentity


class StagedCandidatePublication:
    """One immutable candidate that can produce one ordinary peer request."""

    def __init__(
        self,
        *,
        staged_path: Path,
        carrier_digest: str,
        candidate_text: str,
        identity: CandidatePublicationIdentity,
    ) -> None:
        self.staged_path = staged_path
        self.carrier_digest = carrier_digest
        self.candidate_text = candidate_text
        self.identity = identity
        self._lock = threading.Lock()
        self._published_receipt: dict[str, Any] | None = None

    @property
    def published(self) -> bool:
        return self._published_receipt is not None

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "carrier_digest": self.carrier_digest,
            "staged_path": self.staged_path.name,
            "candidate_revision": self.identity.candidate_revision,
            "candidate_digest": self.identity.candidate_digest,
            "semantic_digest": self.identity.semantic_digest,
            "source_run_id": self.identity.source_run_id,
            "source_delivery_id": self.identity.source_delivery_id,
            "accepted_delivery_id": self.identity.accepted_delivery_id,
            "publication_operation": "modeling_publish_staged_candidate",
            "sender_role": "modeling",
            "recipient_role": "protocol",
            "expects_reply": True,
        }

    def publish(
        self,
        *,
        actor_id: str,
        modeling_id: str,
        protocol_id: str,
        send: Callable[..., Any],
    ) -> dict[str, Any]:
        """Publish once after all identities are fixed by Runner-owned code."""

        if actor_id != modeling_id or not actor_id:
            raise CandidatePublicationError("staged candidate publication is Modeling-only")
        if not isinstance(protocol_id, str) or not protocol_id:
            raise CandidatePublicationError("staged candidate Protocol identity is unavailable")
        with self._lock:
            if self._published_receipt is not None:
                raise CandidatePublicationError("staged candidate was already published")
            delivery = send(
                modeling_id,
                protocol_id,
                self.candidate_text,
                expects_reply=True,
            )
            delivery_id = getattr(delivery, "delivery_id", None)
            if (
                not isinstance(delivery_id, str)
                or not delivery_id
                or getattr(delivery, "sender_id", None) != modeling_id
                or getattr(delivery, "recipient_id", None) != protocol_id
                or getattr(delivery, "expects_reply", None) is not True
                or getattr(delivery, "reply_to_delivery_id", None) is not None
            ):
                raise CandidatePublicationError("staged candidate publication lacked a delivery ID")
            receipt = {
                "delivery_id": delivery_id,
                "sender_id": modeling_id,
                "recipient_id": protocol_id,
                "expects_reply": True,
                "reply_to_delivery_id": None,
                "candidate_revision": self.identity.candidate_revision,
                "candidate_digest": self.identity.candidate_digest,
                "semantic_digest": self.identity.semantic_digest,
                "carrier_digest": self.carrier_digest,
                "source_run_id": self.identity.source_run_id,
                "source_delivery_id": self.identity.source_delivery_id,
                "accepted_delivery_id": self.identity.accepted_delivery_id,
            }
            self._published_receipt = receipt
            return dict(receipt)


def _write_immutable(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise CandidatePublicationError("staged candidate path is already occupied")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("staged candidate write did not progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, mode)
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise CandidatePublicationError("staged candidate metadata is invalid")


def _carrier_identity(
    carrier: Mapping[str, Any],
    *,
    candidate_revision: Any,
    candidate_digest: str,
    semantic_digest: str,
) -> CandidatePublicationIdentity:
    receipt = validate_formal_receipt(
        carrier.get("accepted_receipt"),
        candidate_revision=candidate_revision,
        candidate_digest=candidate_digest,
        semantic_digest=semantic_digest,
    )
    identity = carrier.get("candidate_identity")
    expected_fields = {
        "accepted_delivery_id",
        "candidate_digest",
        "candidate_revision",
        "run_id",
        "semantic_digest",
        "source_delivery_id",
    }
    if not isinstance(identity, Mapping) or set(identity) != expected_fields:
        raise CandidatePublicationError("candidate carrier identity fields are invalid")
    if any(
        identity.get(field) != value
        for field, value in {
            "candidate_revision": candidate_revision,
            "candidate_digest": candidate_digest,
            "semantic_digest": semantic_digest,
            "accepted_delivery_id": carrier.get("accepted_delivery_id"),
        }.items()
    ):
        raise CandidatePublicationError("candidate carrier identity drifted")
    if any(
        not isinstance(identity.get(field), str) or not identity.get(field)
        for field in ("run_id", "source_delivery_id", "accepted_delivery_id")
    ):
        raise CandidatePublicationError("candidate carrier source identity is invalid")
    if any(
        carrier.get(field) != identity.get(identity_field)
        for field, identity_field in {
            "source_run_id": "run_id",
            "source_delivery_id": "source_delivery_id",
            "accepted_delivery_id": "accepted_delivery_id",
        }.items()
    ):
        raise CandidatePublicationError("candidate carrier top-level identity drifted")
    if receipt["candidate_digest"] != identity["candidate_digest"]:
        raise CandidatePublicationError("candidate carrier accepted identity drifted")
    return CandidatePublicationIdentity(
        candidate_revision=candidate_revision,
        candidate_digest=candidate_digest,
        semantic_digest=semantic_digest,
        source_run_id=str(identity["run_id"]),
        source_delivery_id=str(identity["source_delivery_id"]),
        accepted_delivery_id=str(identity["accepted_delivery_id"]),
    )


def validate_candidate_publication(
    overlay: TaskInputOverlay,
) -> ValidatedCandidatePublication:
    """Validate source bytes before ledger reservation or run-root creation."""
    try:
        carrier_bytes = overlay.candidate_publication.path.read_bytes()
    except OSError as exc:
        raise TeamConfigurationError("candidate publication source is unreadable") from exc
    carrier_digest = hashlib.sha256(carrier_bytes).hexdigest()
    if carrier_digest != overlay.candidate_publication.sha256:
        raise TeamConfigurationError("candidate publication source drifted after overlay load")
    try:
        carrier = _strict_json_loads(carrier_bytes)
    except (UnicodeError, json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise CandidatePublicationError("candidate carrier is not JSON") from exc
    if not isinstance(carrier, Mapping):
        raise CandidatePublicationError("candidate carrier is not an object")
    if set(carrier) != _CARRIER_FIELDS or carrier.get("schema_version") != "r2-3-005-continuation/v1":
        raise CandidatePublicationError("candidate carrier envelope fields are invalid")
    candidate_text = carrier.get("candidate_text")
    candidate_value = carrier.get("candidate")
    if not isinstance(candidate_text, str) or not candidate_text:
        raise CandidatePublicationError("candidate carrier text is unavailable")
    try:
        parsed = _strict_json_loads(candidate_text)
    except (json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise CandidatePublicationError("candidate carrier text is not JSON") from exc
    if parsed != candidate_value:
        raise CandidatePublicationError("candidate carrier text and object differ")
    try:
        candidate = validate_formal_candidate(parsed)
        candidate_digest, semantic_digest = formal_candidate_digests(candidate)
        identity = _carrier_identity(
            carrier,
            candidate_revision=candidate["candidate_revision"],
            candidate_digest=candidate_digest,
            semantic_digest=semantic_digest,
        )
    except FormalCandidateError as exc:
        raise CandidatePublicationError(str(exc)) from exc
    return ValidatedCandidatePublication(
        carrier_bytes=carrier_bytes,
        carrier_digest=carrier_digest,
        candidate_text=candidate_text,
        identity=identity,
    )


def stage_candidate_publication(
    overlay: TaskInputOverlay,
    validated: ValidatedCandidatePublication,
    *,
    run_root: Path,
) -> StagedCandidatePublication:
    """Stage the exact bytes frozen and validated before reservation."""

    if validated.carrier_digest != overlay.candidate_publication.sha256:
        raise TeamConfigurationError("validated candidate identity drifted")
    staged_path = run_root / "inputs" / "candidate-publication.json"
    _write_immutable(staged_path, validated.carrier_bytes, 0o440)
    return StagedCandidatePublication(
        staged_path=staged_path,
        carrier_digest=validated.carrier_digest,
        candidate_text=validated.candidate_text,
        identity=validated.identity,
    )
