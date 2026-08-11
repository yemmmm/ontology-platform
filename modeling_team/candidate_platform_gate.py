"""Runner-owned carrier that gates Protocol platform MCP calls.

The carrier is intentionally a tiny filesystem protocol.  The Runner writes the
state on the host and the Runtime exposes the directory read-only inside the
Protocol namespace.  The backend only needs to know whether the current state is
``open``; all candidate identity remains Runner evidence.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any, Mapping


CANDIDATE_PLATFORM_GATE_SCHEMA = "r2-3-005-candidate-platform-gate/v1"
CANDIDATE_PLATFORM_GATE_ENV = "FORMAL_CANDIDATE_GATE_PATH"
CANDIDATE_PLATFORM_GATE_MOUNT = "/opt/candidate-gate/state.json"
CANDIDATE_PLATFORM_GATE_DIR_MOUNT = "/opt/candidate-gate"
CANDIDATE_RECEIPT_REGISTERED_KIND = "candidate-receipt-registered"
CANDIDATE_RECEIPT_REGISTERED_SCHEMA = "r2-3-005-candidate-receipt-registered/v1"


class CandidatePlatformGateError(RuntimeError):
    """The Runner-owned platform gate carrier is invalid or unavailable."""


def candidate_receipt_registered_notice(
    identity: Mapping[str, Any], accepted_receipt_delivery_id: str
) -> dict[str, str]:
    """Build the bounded fact sent directly to Protocol after gate opening."""

    if not isinstance(accepted_receipt_delivery_id, str) or not accepted_receipt_delivery_id:
        raise CandidatePlatformGateError("accepted receipt delivery identity is invalid")
    required = ("run_id", "original_delivery_id", "candidate_digest")
    if any(not isinstance(identity.get(field), str) or not identity[field] for field in required):
        raise CandidatePlatformGateError("candidate receipt registration identity is invalid")
    return {
        "schema_version": CANDIDATE_RECEIPT_REGISTERED_SCHEMA,
        "run_id": identity["run_id"],
        "original_delivery_id": identity["original_delivery_id"],
        "accepted_receipt_delivery_id": accepted_receipt_delivery_id,
        "candidate_digest": identity["candidate_digest"],
    }


class CandidatePlatformGate:
    """Atomically publish a closed/open platform-call gate for one formal run."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.state_path = self.directory / "state.json"

    @classmethod
    def ensure(cls, directory: Path) -> "CandidatePlatformGate":
        gate = cls(directory)
        gate._ensure_directory()
        if not gate.state_path.exists() and not gate.state_path.is_symlink():
            gate._write(
                {
                    "schema_version": CANDIDATE_PLATFORM_GATE_SCHEMA,
                    "state": "closed",
                    "reason_code": "awaiting_candidate_receipt",
                }
            )
        gate._validate_state_path()
        return gate

    def close(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code:
            raise CandidatePlatformGateError("candidate platform gate reason is invalid")
        self._ensure_directory()
        self._write(
            {
                "schema_version": CANDIDATE_PLATFORM_GATE_SCHEMA,
                "state": "closed",
                "reason_code": reason_code,
            }
        )

    def open(self, identity: Mapping[str, Any]) -> None:
        """Open only for the exact identity formally accepted by Runner."""

        required = {
            "run_id",
            "protocol_agent_id",
            "protocol_thread_id",
            "original_delivery_id",
            "candidate_revision",
            "semantic_digest",
            "candidate_digest",
        }
        if not isinstance(identity, Mapping) or not required.issubset(identity):
            raise CandidatePlatformGateError("candidate platform gate identity is incomplete")
        for field in (
            "run_id",
            "protocol_agent_id",
            "protocol_thread_id",
            "original_delivery_id",
            "semantic_digest",
            "candidate_digest",
        ):
            value = identity.get(field)
            if not isinstance(value, str) or not value:
                raise CandidatePlatformGateError("candidate platform gate identity is invalid")
        revision = identity.get("candidate_revision")
        if isinstance(revision, bool) or not (
            (isinstance(revision, int) and revision > 0)
            or (isinstance(revision, str) and bool(revision))
        ):
            raise CandidatePlatformGateError("candidate platform gate revision is invalid")
        context_binding = identity.get("modeling_context")
        if context_binding is not None:
            required_context = {
                "project_id",
                "ontology_id",
                "workspace_version",
                "context_receipt_digest",
                "response_digest",
                "call_receipt_digest",
            }
            if not isinstance(context_binding, Mapping) or set(context_binding) != required_context:
                raise CandidatePlatformGateError("candidate Modeling context binding is incomplete")
            for field in required_context:
                value = context_binding.get(field)
                if not isinstance(value, str) or not value:
                    raise CandidatePlatformGateError("candidate Modeling context binding is invalid")
        self._ensure_directory()
        payload: dict[str, Any] = {
            "schema_version": CANDIDATE_PLATFORM_GATE_SCHEMA,
            "state": "open",
            "run_id": identity["run_id"],
            "protocol_agent_id": identity["protocol_agent_id"],
            "protocol_thread_id": identity["protocol_thread_id"],
            "original_delivery_id": identity["original_delivery_id"],
            "candidate_revision": revision,
            "semantic_digest": identity["semantic_digest"],
            "candidate_digest": identity["candidate_digest"],
        }
        if context_binding is not None:
            payload["modeling_context"] = dict(context_binding)
            payload["protocol_revalidation"] = {"state": "required"}
        self._write(payload)

    def _ensure_directory(self) -> None:
        if self.directory.is_symlink():
            raise CandidatePlatformGateError("candidate platform gate directory is a symlink")
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = os.lstat(self.directory)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()
        ):
            raise CandidatePlatformGateError("candidate platform gate directory is invalid")

    def _validate_state_path(self) -> None:
        try:
            metadata = os.lstat(self.state_path)
        except OSError as exc:
            raise CandidatePlatformGateError("candidate platform gate state is unavailable") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
        ):
            raise CandidatePlatformGateError("candidate platform gate state is invalid")

    def _write(self, value: dict[str, Any]) -> None:
        payload = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        temporary = self.directory / f".state.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o444)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o444)
            os.replace(temporary, self.state_path)
            directory_fd = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
