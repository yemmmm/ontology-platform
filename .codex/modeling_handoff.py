#!/usr/bin/env python3
"""DEPRECATED handoff for historical ontology-builder modeler output.

Retained only for historical delivery compatibility. The current ontology-modeling skill must not
invoke or depend on this module.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence


MANIFEST_VERSION = "1"
SCHEMA_VERSION = "modeler-handoff-v1"
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024
MAX_SECRET_SCAN_OVERLAP = 4 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
INPUT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}\.(?:json|md|txt)$")
SAFE_ENV_KEYS = {
    "PATH",
    "HOME",
    "CODEX_HOME",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "TERM",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
}
DENIED_ENV_PARTS = (
    "ONTOLOGY",
    "MCP_",
    "API_KEY",
    "AUTHORIZATION",
    "COOKIE",
    "CREDENTIAL",
    "LEASE",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
SECRET_PATTERNS = (
    ("authorization", re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+\S+")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|password|secret|lease[_-]?token)\b"
            r"\s*[:=]\s*['\"]?(?!REDACTED|<|\$\{|\*{3})[^\s,'\"]{12,}"
        ),
    ),
)
FINAL_STATES = {"persisted", "cleaned", "blocked"}


class HandoffError(RuntimeError):
    """A stable, fail-closed error safe to expose in a bounded manifest."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def strict_json_loads(payload: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(
        payload.decode("utf-8"),
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def contains_secret(value: bytes | str) -> bool:
    text = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value
    return any(pattern.search(text) for _, pattern in SECRET_PATTERNS)


def safe_modeler_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Keep Codex auth lookup and credential-free proxies, never platform credentials.

    Codex authentication remains file-backed through ``HOME``/``CODEX_HOME``.  The child command
    separately uses ``--ignore-user-config``, which skips ``$CODEX_HOME/config.toml`` while still
    allowing Codex to read its auth store.  A positive allowlist is backed by category denial so a
    future allowlist expansion cannot accidentally expose a platform, MCP, or generic credential.
    """
    source = os.environ if source is None else source
    safe: dict[str, str] = {}
    for key in SAFE_ENV_KEYS:
        value = source.get(key)
        if value is None or any(part in key.upper() for part in DENIED_ENV_PARTS):
            continue
        if key.lower().endswith("proxy") and re.match(r"^[a-z]+://[^/@]+@", value, re.I):
            continue
        safe[key] = value
    safe.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    safe.setdefault("LANG", "C.UTF-8")
    return safe


class DiagnosticAccumulator:
    """Drain stderr while retaining only bounded scan overlap and category metadata."""

    def __init__(self) -> None:
        self.byte_count = 0
        self._overlap = b""
        self.categories: set[str] = set()
        self.drain_failed = False

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self.byte_count += len(chunk)
        candidate = self._overlap + chunk
        text = candidate.decode("utf-8", errors="ignore")
        self.categories.update(
            category for category, pattern in SECRET_PATTERNS if pattern.search(text)
        )
        self._overlap = candidate[-MAX_SECRET_SCAN_OVERLAP:]

    def finish(self) -> dict[str, Any]:
        self._overlap = b""
        return {
            "stderr_present": self.byte_count > 0,
            "stderr_bytes_observed": self.byte_count,
            "stderr_bounded_in_memory": True,
            "secret_categories": sorted(self.categories),
            "drain_failed": self.drain_failed,
        }


def drain_diagnostic_stream(stream: Any, accumulator: DiagnosticAccumulator) -> None:
    try:
        while chunk := stream.read(8192):
            accumulator.feed(chunk)
    except (OSError, ValueError):
        accumulator.drain_failed = True
    finally:
        with contextlib.suppress(OSError):
            stream.close()


def validate_identifier(value: str, field: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise HandoffError(f"invalid_{field}")
    return value


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode())
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def read_object(path: Path, error: str = "handoff_state_conflict") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError(error) from exc
    if not isinstance(value, dict):
        raise HandoffError(error)
    return value


def regular_owned_file(path: Path, root: Path) -> os.stat_result:
    try:
        resolved_parent = path.parent.resolve(strict=True)
        root_resolved = root.resolve(strict=True)
        details = path.lstat()
    except (OSError, RuntimeError) as exc:
        raise HandoffError("handoff_file_missing") from exc
    if root_resolved != resolved_parent and root_resolved not in resolved_parent.parents:
        raise HandoffError("handoff_file_unsafe")
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise HandoffError("handoff_file_unsafe")
    if details.st_uid != os.getuid() or details.st_mode & 0o077:
        raise HandoffError("handoff_file_unsafe")
    return details


def process_identity(pid: int) -> dict[str, Any] | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = raw.rfind(")")
        fields = raw[close + 2 :].split()
        start_ticks = int(fields[19])
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError, IndexError):
        return None
    return {"pid": pid, "start_ticks": start_ticks, "cmdline_sha256": sha256_bytes(cmdline)}


def identity_is_live(identity: dict[str, Any] | None) -> bool:
    if not isinstance(identity, dict) or not isinstance(identity.get("pid"), int):
        return False
    current = process_identity(identity["pid"])
    return bool(current and current["start_ticks"] == identity.get("start_ticks"))


@dataclass(frozen=True)
class GenerationPaths:
    root: Path
    build_session_id: str
    artifact_key: str
    generation_id: str

    @property
    def chain(self) -> Path:
        return self.root / self.build_session_id / self.artifact_key

    @property
    def generation(self) -> Path:
        return self.chain / self.generation_id

    @property
    def state(self) -> Path:
        return self.generation / "generation.json"

    @property
    def manifest(self) -> Path:
        return self.generation / "manifest.json"

    @property
    def status(self) -> Path:
        return self.generation / "process-status.json"

    @property
    def temporary(self) -> Path:
        return self.generation / "draft.tmp"

    @property
    def draft(self) -> Path:
        return self.generation / "draft.json"

    @property
    def inputs(self) -> Path:
        return self.generation / "input"


class Spool:
    def __init__(self, repo: Path, *, root: Path | None = None) -> None:
        self.repo = repo.resolve(strict=True)
        default = self.repo / "backend" / ".local" / "modeling-handoffs"
        self.root = (root or default).resolve()
        if root is None:
            backend_local = (self.repo / "backend" / ".local").resolve()
            if backend_local != self.root and backend_local not in self.root.parents:
                raise HandoffError("handoff_file_unsafe")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def paths(
        self, build_session_id: str, artifact_key: str, generation_id: str
    ) -> GenerationPaths:
        return GenerationPaths(
            self.root,
            validate_identifier(build_session_id, "build_session_id"),
            validate_identifier(artifact_key, "artifact_key"),
            validate_identifier(generation_id, "generation_id"),
        )

    @contextlib.contextmanager
    def lock(self, path: Path, *, blocking: bool = True) -> Iterator[None]:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        with path.open("a+b") as handle:
            os.chmod(path, 0o600)
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as exc:
                raise HandoffError("handoff_still_running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _state(self, paths: GenerationPaths) -> dict[str, Any]:
        return read_object(paths.state)

    def _write_state(self, paths: GenerationPaths, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        atomic_json(paths.state, state)

    def _manifest_value(self, paths: GenerationPaths, state: dict[str, Any]) -> dict[str, Any]:
        value = {
            "manifest_version": MANIFEST_VERSION,
            "schema_version": state["schema_version"],
            "build_session_id": paths.build_session_id,
            "artifact_key": paths.artifact_key,
            "generation_id": paths.generation_id,
            "expected_previous_generation_id": state.get("expected_previous_generation_id"),
            "correction_round": state["correction_round"],
            "state": state["state"],
            "locator": paths.generation.relative_to(self.root).as_posix(),
            "sha256": state.get("sha256"),
            "canonical_content_hash": state.get("canonical_content_hash"),
            "size_bytes": state.get("size_bytes"),
            "item_count": state.get("item_count"),
            "created_at": state["created_at"],
            "validated_at": state.get("validated_at"),
            "workflow_artifact_id": state.get("workflow_artifact_id"),
            "failure_code": state.get("failure_code"),
        }
        encoded = canonical_bytes(value)
        if len(encoded) > MAX_MANIFEST_BYTES or contains_secret(encoded):
            raise HandoffError("handoff_state_conflict")
        atomic_json(paths.manifest, value)
        return value

    def manifest(
        self, paths: GenerationPaths, state: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._manifest_value(paths, state or self._state(paths))

    def prepare(
        self,
        *,
        build_session_id: str,
        artifact_key: str,
        generation_id: str,
        expected_previous_generation_id: str | None,
        correction_round: int,
        inputs: dict[str, Path],
        prompt_input: str,
        failure_class: str | None = None,
        user_authorization_id: str | None = None,
    ) -> dict[str, Any]:
        paths = self.paths(build_session_id, artifact_key, generation_id)
        if expected_previous_generation_id is not None:
            validate_identifier(expected_previous_generation_id, "previous_generation_id")
        if correction_round < 0 or correction_round > 999:
            raise HandoffError("invalid_correction_round")
        if prompt_input not in inputs or not INPUT_NAME.fullmatch(prompt_input):
            raise HandoffError("invalid_prompt_input")
        if not inputs or any(not INPUT_NAME.fullmatch(name) for name in inputs):
            raise HandoffError("invalid_input_name")
        if correction_round > 2 and not user_authorization_id:
            raise HandoffError("handoff_rework_limit")
        source_records: list[dict[str, Any]] = []
        source_payloads: dict[str, bytes] = {}
        for name, source in sorted(inputs.items()):
            try:
                details = source.lstat()
            except OSError as exc:
                raise HandoffError("handoff_file_missing") from exc
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                raise HandoffError("handoff_file_unsafe")
            payload = source.read_bytes()
            if contains_secret(payload):
                raise HandoffError("handoff_secret_detected")
            source_payloads[name] = payload
            source_records.append(
                {"name": name, "size_bytes": len(payload), "sha256": sha256_bytes(payload)}
            )
        immutable = {
            "schema_version": SCHEMA_VERSION,
            "expected_previous_generation_id": expected_previous_generation_id,
            "correction_round": correction_round,
            "prompt_input": prompt_input,
            "inputs": source_records,
            "failure_class": failure_class,
            "user_authorization_id": user_authorization_id,
        }
        immutable_hash = sha256_bytes(canonical_bytes(immutable))
        paths.chain.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(paths.chain, 0o700)
        with self.lock(paths.chain / ".head.lock"):
            head_path = paths.chain / "head.json"
            head = read_object(head_path) if head_path.exists() else {"generation_id": None}
            if paths.state.exists():
                existing = self._state(paths)
                if existing.get("immutable_hash") != immutable_hash:
                    raise HandoffError("generation_id_conflict")
                if head.get("generation_id") == expected_previous_generation_id:
                    atomic_json(
                        head_path,
                        {"generation_id": generation_id, "updated_at": now_iso()},
                    )
                elif head.get("generation_id") != generation_id:
                    raise HandoffError("generation_conflict")
                return self.manifest(paths, existing)
            if paths.generation.exists():
                raise HandoffError("handoff_state_conflict")
            if head.get("generation_id") != expected_previous_generation_id:
                raise HandoffError("generation_conflict")
            if expected_previous_generation_id:
                previous = self.paths(
                    build_session_id, artifact_key, expected_previous_generation_id
                )
                previous_state = self._state(previous)
                if (
                    correction_round <= 2
                    and failure_class
                    and previous_state.get("failure_class") == failure_class
                    and not user_authorization_id
                ):
                    raise HandoffError("handoff_rework_limit")
            paths.generation.mkdir(mode=0o700)
            paths.inputs.mkdir(mode=0o700)
            for name, payload in source_payloads.items():
                target = paths.inputs / name
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            os.chmod(paths.inputs, 0o500)
            timestamp = now_iso()
            state = {
                "state_version": 1,
                "schema_version": SCHEMA_VERSION,
                "state": "prepared",
                "build_session_id": build_session_id,
                "artifact_key": artifact_key,
                "generation_id": generation_id,
                "expected_previous_generation_id": expected_previous_generation_id,
                "correction_round": correction_round,
                "prompt_input": prompt_input,
                "input_records": source_records,
                "immutable_hash": immutable_hash,
                "failure_class": failure_class,
                "user_authorization_id": user_authorization_id,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            self._write_state(paths, state)
            atomic_json(head_path, {"generation_id": generation_id, "updated_at": timestamp})
            return self.manifest(paths, state)

    def start_codex(
        self, paths: GenerationPaths, *, codex_bin: str = "codex", wait: bool = True
    ) -> dict[str, Any]:
        already_running = False
        with self.lock(paths.generation / ".lock"):
            state = self._state(paths)
            if state["state"] == "running":
                already_running = True
            elif state["state"] != "prepared":
                raise HandoffError("handoff_state_conflict")
            if already_running:
                process = None
            else:
                executable = shutil.which(codex_bin)
                if executable is None:
                    raise HandoffError("handoff_process_failed")
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--repo",
                    str(self.repo),
                    "_supervise",
                    "--build-session-id",
                    paths.build_session_id,
                    "--artifact-key",
                    paths.artifact_key,
                    "--generation-id",
                    paths.generation_id,
                    "--codex-bin",
                    executable,
                ]
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )
                identity = None
                for _ in range(50):
                    identity = process_identity(process.pid)
                    if identity:
                        break
                    time.sleep(0.01)
                if identity is None:
                    raise HandoffError("handoff_state_conflict")
                state["state"] = "running"
                state["supervisor_identity"] = identity
                state["started_at"] = now_iso()
                self._write_state(paths, state)
                self.manifest(paths, state)
        if already_running:
            return self.recover(paths)
        assert process is not None
        if not wait:
            threading.Thread(target=process.wait, daemon=True).start()
            return self.manifest(paths)
        process.wait()
        return self.recover(paths)

    def _matching_status(
        self, paths: GenerationPaths, state: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not paths.status.exists():
            return None
        status_value = read_object(paths.status, "handoff_exit_status_unknown")
        if (
            status_value.get("generation_id") != paths.generation_id
            or status_value.get("supervisor_identity") != state.get("supervisor_identity")
            or not isinstance(status_value.get("child_identity"), dict)
        ):
            raise HandoffError("handoff_exit_status_unknown")
        return status_value

    def _block(self, paths: GenerationPaths, state: dict[str, Any], code: str) -> dict[str, Any]:
        state["state"] = "blocked"
        state["failure_code"] = code
        state["failure_class"] = state.get("failure_class") or code
        if code == "handoff_secret_detected":
            for target in (paths.temporary, paths.draft):
                with contextlib.suppress(FileNotFoundError):
                    target.unlink()
            fsync_directory(paths.generation)
        self._write_state(paths, state)
        self.manifest(paths, state)
        raise HandoffError(code)

    def recover(self, paths: GenerationPaths) -> dict[str, Any]:
        with self.lock(paths.generation / ".lock"):
            state = self._state(paths)
            current = state["state"]
            if current in {"validated", "persisted", "cleaned"}:
                if current == "validated":
                    self._verify_unchanged(paths, state)
                elif current == "persisted":
                    self._clean_payload(paths, state)
                    state["state"] = "cleaned"
                    state["cleaned_at"] = now_iso()
                    self._write_state(paths, state)
                return self.manifest(paths, state)
            if current == "blocked":
                raise HandoffError(str(state.get("failure_code") or "handoff_state_conflict"))
            if current == "prepared":
                return self.manifest(paths, state)
            if current == "generated":
                return self._validate_locked(paths, state)
            if current != "running":
                return self._block(paths, state, "handoff_state_conflict")
            try:
                status_value = self._matching_status(paths, state)
            except HandoffError as exc:
                return self._block(paths, state, exc.code)
            if status_value is None:
                if identity_is_live(state.get("supervisor_identity")):
                    raise HandoffError("handoff_still_running")
                return self._block(paths, state, "handoff_exit_status_unknown")
            if status_value.get("completed_at") is None:
                if identity_is_live(status_value.get("child_identity")) or identity_is_live(
                    state.get("supervisor_identity")
                ):
                    raise HandoffError("handoff_still_running")
                return self._block(paths, state, "handoff_exit_status_unknown")
            if status_value.get("exit_code") != 0:
                return self._block(paths, state, "handoff_process_failed")
            temporary_exists = paths.temporary.exists() or paths.temporary.is_symlink()
            draft_exists = paths.draft.exists() or paths.draft.is_symlink()
            if temporary_exists and draft_exists:
                return self._block(paths, state, "handoff_state_conflict")
            source = paths.draft if draft_exists else paths.temporary
            if not source.exists() and not source.is_symlink():
                return self._block(paths, state, "handoff_file_missing")
            try:
                regular_owned_file(source, paths.generation)
            except HandoffError as exc:
                return self._block(paths, state, exc.code)
            payload = source.read_bytes()
            if len(payload) != status_value.get("output_size_bytes") or sha256_bytes(
                payload
            ) != status_value.get("output_sha256"):
                return self._block(paths, state, "handoff_hash_mismatch")
            if contains_secret(payload):
                return self._block(paths, state, "handoff_secret_detected")
            if source == paths.temporary:
                with source.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(source, paths.draft)
                os.chmod(paths.draft, 0o600)
                fsync_directory(paths.generation)
            state["state"] = "generated"
            state["generated_at"] = status_value["completed_at"]
            state["sha256"] = sha256_bytes(payload)
            state["size_bytes"] = len(payload)
            self._write_state(paths, state)
            self.manifest(paths, state)
            return self._validate_locked(paths, state)

    def _verify_unchanged(self, paths: GenerationPaths, state: dict[str, Any]) -> bytes:
        regular_owned_file(paths.draft, paths.generation)
        payload = paths.draft.read_bytes()
        if len(payload) != state.get("size_bytes") or sha256_bytes(payload) != state.get("sha256"):
            return self._block(paths, state, "handoff_hash_mismatch")  # type: ignore[return-value]
        return payload

    def _validate_locked(self, paths: GenerationPaths, state: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = self._verify_unchanged(paths, state)
            if contains_secret(payload):
                return self._block(paths, state, "handoff_secret_detected")
            try:
                document = strict_json_loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                return self._block(paths, state, "handoff_schema_invalid")
            if not isinstance(document, dict):
                return self._block(paths, state, "handoff_schema_invalid")
            canonical = canonical_bytes(document)
            if len(canonical) > MAX_ARTIFACT_BYTES:
                return self._block(paths, state, "handoff_too_large")
            self._validate_schema(document)
            items = document["modeling_batch"]["items"]
            self._validate_references(items)
        except HandoffError as exc:
            if state.get("state") == "blocked":
                raise
            return self._block(paths, state, exc.code)
        state["state"] = "validated"
        state["canonical_content_hash"] = sha256_bytes(canonical)
        state["canonical_size_bytes"] = len(canonical)
        state["item_count"] = len(items)
        state["validated_at"] = now_iso()
        self._write_state(paths, state)
        return self.manifest(paths, state)

    def _validate_schema(self, document: dict[str, Any]) -> None:
        schema_path = (
            self.repo / "skills" / "ontology-builder" / "references" / "modeler-handoff.schema.json"
        )
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            definitions = schema["$defs"]
            self._validate_schema_node(document, schema, definitions)
        except Exception as exc:
            raise HandoffError("handoff_schema_invalid") from exc

    @classmethod
    def _validate_schema_node(
        cls, value: Any, schema: dict[str, Any], definitions: dict[str, Any]
    ) -> None:
        """Validate the closed Draft 2020-12 subset used by the checked-in schema."""
        reference = schema.get("$ref")
        if isinstance(reference, str):
            prefix = "#/$defs/"
            if not reference.startswith(prefix) or reference[len(prefix) :] not in definitions:
                raise ValueError("invalid schema reference")
            cls._validate_schema_node(value, definitions[reference[len(prefix) :]], definitions)
            return
        alternatives = schema.get("anyOf")
        if isinstance(alternatives, list):
            for alternative in alternatives:
                try:
                    cls._validate_schema_node(value, alternative, definitions)
                    return
                except (TypeError, ValueError, KeyError):
                    pass
            raise ValueError("no schema alternative matched")
        allowed_types = schema.get("type")
        if isinstance(allowed_types, str):
            allowed_types = [allowed_types]
        type_checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "null": lambda item: item is None,
            "boolean": lambda item: isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        }
        if isinstance(allowed_types, list) and not any(
            name in type_checks and type_checks[name](value) for name in allowed_types
        ):
            raise TypeError("schema type mismatch")
        if "const" in schema and value != schema["const"]:
            raise ValueError("schema const mismatch")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError("schema enum mismatch")
        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
                "maxLength", len(value)
            ):
                raise ValueError("schema string length mismatch")
        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
                "maxItems", len(value)
            ):
                raise ValueError("schema array length mismatch")
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for item in value:
                    cls._validate_schema_node(item, item_schema, definitions)
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            if any(name not in value for name in required):
                raise KeyError("schema required property missing")
            if schema.get("additionalProperties") is False and not set(value) <= set(properties):
                raise ValueError("schema extra property")
            for name, child in value.items():
                child_schema = properties.get(name)
                if isinstance(child_schema, dict):
                    cls._validate_schema_node(child, child_schema, definitions)

    @staticmethod
    def _validate_references(items: list[dict[str, Any]]) -> None:
        ids = [item.get("client_item_id") for item in items]
        if any(not isinstance(item_id, str) or not item_id for item_id in ids) or len(ids) != len(
            set(ids)
        ):
            raise HandoffError("handoff_reference_invalid")
        known = set(ids)
        graph: dict[str, set[str]] = {}

        def item_references(value: Any) -> Iterator[str]:
            if isinstance(value, dict):
                if set(value) == {"item_ref"} and isinstance(value["item_ref"], dict):
                    referenced = value["item_ref"].get("client_item_id")
                    if isinstance(referenced, str):
                        yield referenced
                for child in value.values():
                    yield from item_references(child)
            elif isinstance(value, list):
                for child in value:
                    yield from item_references(child)

        for item in items:
            item_id = item["client_item_id"]
            dependencies = item.get("depends_on")
            if not isinstance(dependencies, list) or any(
                value not in known for value in dependencies
            ):
                raise HandoffError("handoff_reference_invalid")
            references = set(item_references(item.get("payload")))
            if not references <= known or not references <= set(dependencies):
                raise HandoffError("handoff_reference_invalid")
            graph[item_id] = set(dependencies)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise HandoffError("handoff_reference_invalid")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for item_id in graph:
            visit(item_id)

    def mark_persisted(
        self,
        paths: GenerationPaths,
        *,
        workflow_artifact_id: str,
        canonical_content_hash: str,
    ) -> dict[str, Any]:
        validate_identifier(workflow_artifact_id, "workflow_artifact_id")
        with self.lock(paths.generation / ".lock"):
            state = self._state(paths)
            if state["state"] in {"persisted", "cleaned"}:
                if (
                    state.get("workflow_artifact_id") != workflow_artifact_id
                    or state.get("canonical_content_hash") != canonical_content_hash
                ):
                    raise HandoffError("handoff_platform_hash_conflict")
                if state["state"] == "persisted":
                    self._clean_payload(paths, state)
                    state["state"] = "cleaned"
                    state["cleaned_at"] = now_iso()
                    self._write_state(paths, state)
                return self.manifest(paths, state)
            if state["state"] != "validated":
                raise HandoffError("handoff_state_conflict")
            self._verify_unchanged(paths, state)
            if state["canonical_content_hash"] != canonical_content_hash:
                raise HandoffError("handoff_platform_hash_conflict")
            state["state"] = "persisted"
            state["workflow_artifact_id"] = workflow_artifact_id
            state["persisted_at"] = now_iso()
            self._write_state(paths, state)
            self._clean_payload(paths, state)
            state["state"] = "cleaned"
            state["cleaned_at"] = now_iso()
            self._write_state(paths, state)
            self._clean_predecessors(paths, state)
            return self.manifest(paths, state)

    def _clean_payload(self, paths: GenerationPaths, state: dict[str, Any]) -> None:
        for target in (paths.temporary, paths.draft):
            if target.is_symlink():
                raise HandoffError("handoff_file_unsafe")
            with contextlib.suppress(FileNotFoundError):
                target.unlink()
        if paths.inputs.exists():
            if paths.inputs.is_symlink():
                raise HandoffError("handoff_file_unsafe")
            os.chmod(paths.inputs, 0o700)
            shutil.rmtree(paths.inputs)
        fsync_directory(paths.generation)

    def _clean_predecessors(self, paths: GenerationPaths, state: dict[str, Any]) -> None:
        previous_id = state.get("expected_previous_generation_id")
        visited: set[str] = set()
        while isinstance(previous_id, str) and previous_id not in visited:
            visited.add(previous_id)
            previous = self.paths(paths.build_session_id, paths.artifact_key, previous_id)
            with self.lock(previous.generation / ".lock"):
                previous_state = self._state(previous)
                self._clean_payload(previous, previous_state)
                previous_state["payload_cleaned_at"] = now_iso()
                self._write_state(previous, previous_state)
                self.manifest(previous, previous_state)
                previous_id = previous_state.get("expected_previous_generation_id")

    def cleanup_session(self, build_session_id: str) -> int:
        validate_identifier(build_session_id, "build_session_id")
        session = self.root / build_session_id
        if not session.exists():
            return 0
        if session.is_symlink() or session.resolve().parent != self.root.resolve():
            raise HandoffError("handoff_file_unsafe")
        generations = list(session.glob("*/*/generation.json"))
        count = len(generations)
        with contextlib.ExitStack() as locks:
            for head_lock in session.glob("*/.head.lock"):
                locks.enter_context(self.lock(head_lock, blocking=False))
            for state_path in generations:
                locks.enter_context(self.lock(state_path.parent / ".lock", blocking=False))
            for input_path in session.glob("*/*/input"):
                if input_path.is_symlink():
                    raise HandoffError("handoff_file_unsafe")
                os.chmod(input_path, 0o700)
            shutil.rmtree(session)
        fsync_directory(self.root)
        return count

    def cleanup_stale(self, age_seconds: int) -> int:
        if age_seconds < 60:
            raise HandoffError("invalid_cleanup_age")
        cutoff = time.time() - age_seconds
        removed = 0
        state_paths = list(self.root.glob("*/*/*/generation.json"))
        referenced = {
            value
            for path in state_paths
            if isinstance(value := read_object(path).get("expected_previous_generation_id"), str)
        }
        for state_path in state_paths:
            generation = state_path.parent
            if generation.is_symlink() or state_path.stat().st_mtime >= cutoff:
                continue
            paths = self.paths(*generation.relative_to(self.root).parts)
            if paths.generation_id in referenced:
                continue
            with self.lock(paths.chain / ".head.lock", blocking=False):
                with self.lock(generation / ".lock", blocking=False):
                    state = self._state(paths)
                    if state["state"] == "running" and identity_is_live(
                        state.get("supervisor_identity")
                    ):
                        continue
                    head_path = paths.chain / "head.json"
                    head = read_object(head_path)
                    is_head = head.get("generation_id") == paths.generation_id
                    eligible = state["state"] in {"prepared", "cleaned"} or (
                        state["state"] == "blocked" and not is_head
                    )
                    if not eligible:
                        continue
                    if is_head:
                        atomic_json(
                            head_path,
                            {
                                "generation_id": state.get("expected_previous_generation_id"),
                                "updated_at": now_iso(),
                            },
                        )
                    if paths.inputs.exists():
                        if paths.inputs.is_symlink():
                            raise HandoffError("handoff_file_unsafe")
                        os.chmod(paths.inputs, 0o700)
                    shutil.rmtree(generation)
                    removed += 1
        return removed


def supervisor(spool: Spool, paths: GenerationPaths, codex_bin: str) -> int:
    os.umask(0o077)
    state = spool._state(paths)
    expected_supervisor = state.get("supervisor_identity")
    current_supervisor = process_identity(os.getpid())
    # The launcher may not have persisted the identity before this process starts.
    for _ in range(200):
        state = spool._state(paths)
        expected_supervisor = state.get("supervisor_identity")
        if (
            isinstance(expected_supervisor, dict)
            and current_supervisor
            and expected_supervisor.get("pid") == current_supervisor.get("pid")
            and expected_supervisor.get("start_ticks") == current_supervisor.get("start_ticks")
            and state.get("state") == "running"
        ):
            break
        time.sleep(0.01)
    else:
        return 70
    prompt_path = paths.inputs / state["prompt_input"]
    regular_owned_file(prompt_path, paths.generation)
    prompt = prompt_path.read_bytes()
    schema_path = (
        spool.repo / "skills" / "ontology-builder" / "references" / "modeler-handoff.schema.json"
    )
    command = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "-C",
        str(paths.inputs),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(paths.temporary),
        "-",
    ]
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=safe_modeler_environment(),
        start_new_session=True,
        close_fds=True,
    )
    accumulator = DiagnosticAccumulator()
    assert child.stderr is not None
    diagnostic_thread = threading.Thread(
        target=drain_diagnostic_stream,
        args=(child.stderr, accumulator),
        daemon=True,
    )
    diagnostic_thread.start()
    child_identity = None
    for _ in range(50):
        child_identity = process_identity(child.pid)
        if child_identity:
            break
        time.sleep(0.01)
    if child_identity is None:
        child.kill()
        child.wait()
        diagnostic_thread.join(5)
        return 70
    empty_diagnostic = {
        "stderr_present": False,
        "stderr_bytes_observed": 0,
        "stderr_bounded_in_memory": True,
        "secret_categories": [],
        "drain_failed": False,
    }
    status_value = {
        "status_version": 1,
        "generation_id": paths.generation_id,
        "supervisor_identity": expected_supervisor,
        "child_identity": child_identity,
        "started_at": now_iso(),
        "completed_at": None,
        "exit_code": None,
        "signal": None,
        "output_size_bytes": None,
        "output_sha256": None,
        "diagnostic": empty_diagnostic,
    }
    atomic_json(paths.status, status_value)
    try:
        assert child.stdin is not None
        child.stdin.write(prompt)
        child.stdin.close()
        exit_code = child.wait()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
        child.wait()
        raise
    finally:
        if child.stdin is not None and not child.stdin.closed:
            with contextlib.suppress(OSError):
                child.stdin.close()
        diagnostic_thread.join(5)
        if diagnostic_thread.is_alive():
            accumulator.drain_failed = True
    output_size = None
    output_hash = None
    if paths.temporary.exists() and not paths.temporary.is_symlink():
        output = paths.temporary.read_bytes()
        output_size = len(output)
        output_hash = sha256_bytes(output)
        os.chmod(paths.temporary, 0o600)
    status_value.update(
        {
            "completed_at": now_iso(),
            "exit_code": exit_code if exit_code is not None and exit_code >= 0 else None,
            "signal": -exit_code if exit_code is not None and exit_code < 0 else None,
            "output_size_bytes": output_size,
            "output_sha256": output_hash,
            "diagnostic": accumulator.finish(),
        }
    )
    atomic_json(paths.status, status_value)
    return 0


def find_repo(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "skills" / "ontology-builder").is_dir():
            return candidate
    raise HandoffError("repository_not_found")


def parse_inputs(values: Sequence[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise HandoffError("invalid_input_name")
        name, raw_path = value.split("=", 1)
        if name in parsed:
            raise HandoffError("invalid_input_name")
        try:
            parsed[name] = Path(raw_path).resolve(strict=True)
        except OSError as exc:
            raise HandoffError("handoff_file_missing") from exc
    return parsed


def add_locator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--build-session-id", required=True)
    parser.add_argument("--artifact-key", required=True)
    parser.add_argument("--generation-id", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    add_locator_arguments(prepare)
    prepare.add_argument("--expected-previous-generation-id")
    prepare.add_argument("--correction-round", type=int, default=0)
    prepare.add_argument("--input", action="append", default=[])
    prepare.add_argument("--prompt-input", required=True)
    prepare.add_argument("--failure-class")
    prepare.add_argument("--user-authorization-id")
    run = commands.add_parser("run")
    add_locator_arguments(run)
    run.add_argument("--codex-bin", default="codex")
    run.add_argument("--no-wait", action="store_true")
    inspect = commands.add_parser("inspect")
    add_locator_arguments(inspect)
    persisted = commands.add_parser("mark-persisted")
    add_locator_arguments(persisted)
    persisted.add_argument("--workflow-artifact-id", required=True)
    persisted.add_argument("--canonical-content-hash", required=True)
    cleanup = commands.add_parser("cleanup-session")
    cleanup.add_argument("--build-session-id", required=True)
    stale = commands.add_parser("cleanup-stale")
    stale.add_argument("--age-seconds", type=int, required=True)
    internal = commands.add_parser("_supervise", help=argparse.SUPPRESS)
    add_locator_arguments(internal)
    internal.add_argument("--codex-bin", required=True)
    return parser


def output(value: dict[str, Any]) -> None:
    encoded = canonical_bytes(value)
    if len(encoded) > MAX_MANIFEST_BYTES or contains_secret(encoded):
        raise HandoffError("handoff_state_conflict")
    sys.stdout.buffer.write(encoded + b"\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = find_repo(args.repo)
        spool = Spool(repo)
        if args.command == "cleanup-session":
            output(
                {
                    "manifest_version": MANIFEST_VERSION,
                    "state": "cleaned",
                    "removed": spool.cleanup_session(args.build_session_id),
                }
            )
            return 0
        if args.command == "cleanup-stale":
            output(
                {
                    "manifest_version": MANIFEST_VERSION,
                    "state": "cleaned",
                    "removed": spool.cleanup_stale(args.age_seconds),
                }
            )
            return 0
        paths = spool.paths(args.build_session_id, args.artifact_key, args.generation_id)
        if args.command == "prepare":
            value = spool.prepare(
                build_session_id=args.build_session_id,
                artifact_key=args.artifact_key,
                generation_id=args.generation_id,
                expected_previous_generation_id=args.expected_previous_generation_id,
                correction_round=args.correction_round,
                inputs=parse_inputs(args.input),
                prompt_input=args.prompt_input,
                failure_class=args.failure_class,
                user_authorization_id=args.user_authorization_id,
            )
        elif args.command == "run":
            value = spool.start_codex(paths, codex_bin=args.codex_bin, wait=not args.no_wait)
        elif args.command == "inspect":
            value = spool.recover(paths)
        elif args.command == "mark-persisted":
            value = spool.mark_persisted(
                paths,
                workflow_artifact_id=args.workflow_artifact_id,
                canonical_content_hash=args.canonical_content_hash,
            )
        elif args.command == "_supervise":
            return supervisor(spool, paths, args.codex_bin)
        else:
            raise HandoffError("handoff_state_conflict")
        output(value)
        return 0
    except HandoffError as exc:
        output({"manifest_version": MANIFEST_VERSION, "state": "blocked", "failure_code": exc.code})
        return 2
    except (OSError, ValueError, json.JSONDecodeError):
        output(
            {
                "manifest_version": MANIFEST_VERSION,
                "state": "blocked",
                "failure_code": "handoff_state_conflict",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
