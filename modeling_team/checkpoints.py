"""R3.0-015 segment S1: persistent modeling-stage checkpoints (save/inspect).

Design §3: five business-stage kinds, one immutable package per save under
``<run-root>/checkpoints/<checkpoint-id>/`` with ``manifest.json`` published
last, a ``host-private/`` side that production roles never receive, content
dedup across request IDs, and a read-only host inspection view.  The module
owns only save/read; cross-process production resume (S2) and acceptance-only
continuation (S4) live in ``checkpoint_recovery`` / the CLI, while translation
approval auto-migration (S3) is deliberately NOT implemented —
:data:`CHECKPOINT_DELIVERY_SEGMENTS` records that boundary so no caller can
mistake a package for a resume capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

CHECKPOINT_SCHEMA = "r3-0-015-checkpoint/v1"
CHECKPOINT_DIRECTORY = "checkpoints"
CHECKPOINT_MANIFEST_NAME = "manifest.json"
CHECKPOINT_ARTIFACTS_DIRECTORY = "artifacts"
CHECKPOINT_HOST_PRIVATE_DIRECTORY = "host-private"
CHECKPOINT_EVIDENCE_NAME = "checkpoints"
PLATFORM_DATA_PATH = "host-private/platform-data.json"

CHECKPOINT_KIND_SCENARIO_MAPPED = "scenario_mapped"
CHECKPOINT_KIND_CQ_FROZEN = "cq_frozen"
CHECKPOINT_KIND_SEMANTIC_APPROVED = "semantic_approved"
CHECKPOINT_KIND_MATERIALIZATION_PROGRESS = "materialization_progress"
CHECKPOINT_KIND_PRODUCTION_HANDOFF = "production_handoff"
CHECKPOINT_KINDS = (
    CHECKPOINT_KIND_SCENARIO_MAPPED,
    CHECKPOINT_KIND_CQ_FROZEN,
    CHECKPOINT_KIND_SEMANTIC_APPROVED,
    CHECKPOINT_KIND_MATERIALIZATION_PROGRESS,
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
)

#: Kinds whose package claims a recoverable platform-write state.  While a
#: staged write is in flight or an intent is ``unknown``, these saves are
#: refused with the specific wait reason instead of packaging an in-flight
#: state as recoverable (design §3.3.3 / test plan M07).
WRITE_CLAIMING_KINDS = frozenset(
    {CHECKPOINT_KIND_MATERIALIZATION_PROGRESS, CHECKPOINT_KIND_PRODUCTION_HANDOFF}
)

#: Visibility labels for the per-role public projection.  Host-private entries
#: are never projected to a production role (design §3.2 / §7).
HOST_VISIBILITY = "host"
PRODUCTION_ROLES = ("coordinator", "modeling", "protocol")
COMPETENCY_QUESTION_VISIBILITY = ("host", "competency-question")

#: Delivery boundary, reported verbatim by ``inspect`` (test plan M44).
#: Production resume (S2) and acceptance-only continuation (S4) are delivered;
#: the S3 translation-approval auto-migration stays deferred by design (the
#: new translation plan is re-reviewed through the normal 014 path), and S4
#: does not depend on it.
CHECKPOINT_DELIVERY_SEGMENTS = {
    "s1_save_inspect": "delivered",
    "s2_production_resume": "delivered",
    "s3_translation_approval_migration": "deferred_by_design",
    "s4_acceptance_continuation": "delivered",
}

_CHECKPOINT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")
#: Run-relative source prefixes that are never packaged: credentials, the
#: control FIFO surface and the checkpoint tree itself (test plan M09).
_DENY_SOURCE_PREFIXES = (
    "secrets/",
    "control/",
    f"{CHECKPOINT_DIRECTORY}/",
    "recovery/",
)

#: Manifest fields excluded from the dedup signature: timestamps, the request
#: id and checkpoint-save events must never turn saving itself into new
#: packages (design §3.4 / test plan M06).
_SIGNATURE_EXCLUDED_FIELDS = ("created_at", "checkpoint_id", "request_id")


class CheckpointError(ValueError):
    """One typed, recoverable checkpoint save/read failure (design §8).

    Carries the ``code``/``object_ref``/``phase``/``retryable``/``reason``
    tuple (plus the optional ``next_action``) the host channels back verbatim;
    the detail never includes hidden question text, answer basis or secrets.
    """

    def __init__(
        self,
        reason_code: str,
        detail: str,
        *,
        obj: str,
        phase: str | None = None,
        retryable: bool = True,
        retry: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail
        self.object = obj
        self.phase = phase
        self.retryable = retryable
        self.retry = retry

    def data(self) -> dict[str, Any]:
        """The design §8 host tuple with the contract field names.

        ``next_action`` travels only when the rejection names one, so a
        rejection is five or six fields -- never an internal spelling.
        """

        return {
            "code": self.reason_code,
            "object_ref": self.object,
            "phase": self.phase,
            "retryable": self.retryable,
            "reason": self.detail,
            **({"next_action": self.retry} if self.retry else {}),
        }


@dataclass(frozen=True)
class CheckpointArtifactSpec:
    """One explicitly listed published artifact to copy into the package."""

    source: str
    owner: str
    visible_to: tuple[str, ...]
    required: bool = True
    host_private: bool = False


@dataclass(frozen=True)
class ResolvedArtifact:
    """A spec plus the digest observed before the copy starts."""

    spec: CheckpointArtifactSpec
    digest: str


@dataclass
class StagePackage:
    """The per-kind collected package handed to :func:`save_checkpoint`."""

    kind: str
    scope_refs: dict[str, Any]
    artifacts: list[CheckpointArtifactSpec]
    stage_facts: dict[str, Any] = field(default_factory=dict)
    platform_bindings: dict[str, Any] = field(default_factory=dict)
    write_positions: dict[str, Any] = field(default_factory=dict)
    missing: list[dict[str, Any]] = field(default_factory=list)
    platform_data: dict[str, Any] | None = None


def _now_iso(now: Callable[[], datetime] | None = None) -> str:
    return (now() if now else datetime.now(UTC)).isoformat()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def safe_checkpoint_id(value: Any) -> str:
    """Reject path escapes and malformed ids before any filesystem join (M08)."""

    if not isinstance(value, str) or not _CHECKPOINT_ID_PATTERN.fullmatch(value):
        raise CheckpointError(
            "checkpoint_invalid_id",
            "checkpoint id must match [a-z0-9][a-z0-9_-]{1,79}",
            obj="checkpoint_id",
            retryable=False,
            retry="use the checkpoint id exactly as inspect listed it",
        )
    return value


def checkpoints_root(run_root: Path) -> Path:
    return Path(run_root) / CHECKPOINT_DIRECTORY


def manifest_path(run_root: Path, checkpoint_id: str) -> Path:
    return checkpoints_root(run_root) / safe_checkpoint_id(checkpoint_id) / CHECKPOINT_MANIFEST_NAME


def manifest_digest(path: Path) -> str:
    """Recompute the exact manifest byte digest at read time (design §3.2).

    The manifest never embeds its own hash; the host records this value in its
    evidence and later segments (S2 ``origin.json``) bind recovery to it.
    """

    return f"sha256:{hashlib.sha256(Path(path).read_bytes()).hexdigest()}"


def _safe_source(run_root: Path, source: str) -> Path:
    """Resolve one run-relative source, rejecting escapes and deny-listed trees."""

    if not isinstance(source, str) or not source or "\\" in source:
        raise CheckpointError(
            "checkpoint_invalid_source",
            "artifact source must be a run-relative posix path",
            obj="artifact_source",
            retryable=False,
        )
    pure = PurePosixPath(source)
    if pure.is_absolute() or ".." in pure.parts:
        raise CheckpointError(
            "checkpoint_invalid_source",
            f"artifact source {source!r} escapes the run root",
            obj="artifact_source",
            retryable=False,
        )
    normalized = pure.as_posix()
    if normalized.startswith(_DENY_SOURCE_PREFIXES):
        raise CheckpointError(
            "checkpoint_invalid_source",
            f"artifact source {source!r} is not packageable material",
            obj="artifact_source",
            retryable=False,
        )
    candidate = Path(run_root).joinpath(*pure.parts)
    if not candidate.is_file() or candidate.is_symlink():
        raise CheckpointError(
            "artifact_unavailable",
            f"artifact source {source!r} is not a regular file in the run root",
            obj="artifact_source",
        )
    return candidate


def _signature_payload(manifest: Mapping[str, Any]) -> Any:
    """The dedup comparison key: content only, never save-event side effects."""

    stage_facts = {
        key: value
        for key, value in (manifest.get("stage_facts") or {}).items()
        if key not in _SIGNATURE_EXCLUDED_FIELDS
    }
    artifacts = sorted(
        (
            {
                "source": artifact.get("source"),
                "digest": artifact.get("digest"),
                "owner": artifact.get("owner"),
                "host_private": bool(artifact.get("host_private")),
            }
            for artifact in manifest.get("artifacts") or []
        ),
        key=lambda item: (item["source"] or "", item["digest"] or ""),
    )
    return {
        "schema_version": manifest.get("schema_version"),
        "kind": manifest.get("kind"),
        "scope_refs": manifest.get("scope_refs") or {},
        "artifacts": artifacts,
        "stage_facts": stage_facts,
        "write_positions": manifest.get("write_positions") or {},
        **({"platform_data": manifest["platform_data"]} if "platform_data" in manifest else {}),
    }


def content_signature(manifest: Mapping[str, Any]) -> str:
    return f"sha256:{hashlib.sha256(_canonical_bytes(_signature_payload(manifest))).hexdigest()}"


def _copy_artifact(source: Path, destination: Path, expected_digest: str) -> None:
    """Copy one artifact preserving bytes; the recheck happens in the caller."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    with destination.open("rb") as stream:
        os.fsync(stream.fileno())


def _load_manifest_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(
            "checkpoint_manifest_unparsable",
            f"checkpoint manifest is not readable JSON ({type(exc).__name__})",
            obj="manifest.json",
            retryable=False,
        ) from exc
    if not isinstance(value, dict):
        raise CheckpointError(
            "checkpoint_manifest_unparsable",
            "checkpoint manifest is not a JSON object",
            obj="manifest.json",
            retryable=False,
        )
    return value


def _published_checkpoint_ids(run_root: Path) -> list[str]:
    """Only directories whose manifest is present count as usable (§3.3.4)."""

    base = checkpoints_root(run_root)
    if not base.is_dir():
        return []
    published: list[str] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.is_symlink() or entry.name.startswith("."):
            continue
        if (entry / CHECKPOINT_MANIFEST_NAME).is_file():
            published.append(entry.name)
    return published


def _verify_package(run_root: Path, checkpoint_id: str) -> tuple[dict[str, Any], list[str]]:
    """Load one package and verify every packaged digest (read-only)."""

    manifest = _load_manifest_file(manifest_path(run_root, checkpoint_id))
    issues: list[str] = []
    if manifest.get("schema_version") != CHECKPOINT_SCHEMA:
        issues.append("schema_version is not " + CHECKPOINT_SCHEMA)
    package_root = checkpoints_root(run_root) / checkpoint_id
    data_ref = manifest.get("platform_data")
    if data_ref:
        data_path = package_root / PLATFORM_DATA_PATH
        if (not data_path.is_file() or data_path.is_symlink()
                or file_digest(data_path) != data_ref.get("digest")):
            issues.append("platform data snapshot is missing or changed")
    for artifact in manifest.get("artifacts") or []:
        if not isinstance(artifact, Mapping):
            issues.append("artifact entry is not an object")
            continue
        side = (
            CHECKPOINT_HOST_PRIVATE_DIRECTORY
            if artifact.get("host_private")
            else CHECKPOINT_ARTIFACTS_DIRECTORY
        )
        snapshot = package_root / side / str(artifact.get("source") or "")
        if not snapshot.is_file() or snapshot.is_symlink():
            issues.append(f"packaged artifact {artifact.get('source')!r} is missing")
            continue
        if file_digest(snapshot) != artifact.get("digest"):
            issues.append(f"packaged artifact {artifact.get('source')!r} digest mismatch")
    return manifest, issues


def verify_checkpoint(run_root: Path, checkpoint_id: str) -> tuple[dict[str, Any], list[str]]:
    """Public S2 entry: load one package and verify every packaged digest.

    Same read-only semantics as the inspect path; resume callers use this as
    the trust root for every downstream artifact copy.
    """

    return _verify_package(Path(run_root), checkpoint_id)


def production_resume_bindings(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    """The exact Project/Ontology identity a production resume would rebind.

    ``inspect`` availability and the resume hard gate share this one decision
    (design §3.2 平台绑定 / §5.2): direct ``platform_bindings`` first, then the
    ``run_scope`` recorded at save time, and ``None`` when the manifest records
    no Project/Ontology identity to reattach — never a name-based rebuild.
    """

    bindings = manifest.get("platform_bindings")
    if not isinstance(bindings, Mapping):
        bindings = {}
    project_id = bindings.get("project_id")
    ontology_ids = [str(item) for item in bindings.get("ontology_ids") or []]
    if not isinstance(project_id, str) or not project_id:
        # Fall back to the run scope recorded at save time.
        run_scope = bindings.get("run_scope") or {}
        project_id = run_scope.get("project_id")
        ontology_ids = [str(item) for item in run_scope.get("ontology_ids") or []]
        if not ontology_ids and isinstance(run_scope.get("ontology_id"), str):
            ontology_ids = [run_scope["ontology_id"]]
    if not isinstance(project_id, str) or not project_id or not ontology_ids:
        return None
    return {"project_id": project_id, "ontology_ids": ontology_ids}


# --- Save ---------------------------------------------------------------------


def save_checkpoint(
    run_root: Path,
    package: StagePackage,
    *,
    source_run_id: str,
    root_run_id: str | None = None,
    configuration: dict[str, Any] | None = None,
    request_id: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Persist one immutable checkpoint package (design §3.3).

    Copy only the explicitly listed published artifacts into a unique temp
    directory, verify digests and cross bindings, detect a source change during
    the copy, then publish ``manifest.json`` last via one atomic rename.  A
    failure removes only the temp directory: the previous checkpoints stay
    readable and the run is never terminated by this function.
    """

    if package.kind not in CHECKPOINT_KINDS:
        raise CheckpointError(
            "checkpoint_invalid_kind",
            f"unknown checkpoint kind {package.kind!r}",
            obj="kind",
            retryable=False,
            retry=f"use one of {list(CHECKPOINT_KINDS)}",
        )
    run_root = Path(run_root)
    resolved: list[ResolvedArtifact] = []
    for spec in package.artifacts:
        source = _safe_source(run_root, spec.source)
        resolved.append(ResolvedArtifact(spec=spec, digest=file_digest(source)))
    manifest_payload = {
        "schema_version": CHECKPOINT_SCHEMA,
        "checkpoint_id": "",  # allocated below; never part of the signature
        "source_run_id": source_run_id,
        "root_run_id": root_run_id or source_run_id,
        "created_at": _now_iso(now),
        "kind": package.kind,
        "scope_refs": dict(package.scope_refs or {}),
        "configuration": dict(configuration or {}),
        "artifacts": [
            {
                "source": item.spec.source,
                "snapshot_path": (
                    f"{CHECKPOINT_HOST_PRIVATE_DIRECTORY if item.spec.host_private else CHECKPOINT_ARTIFACTS_DIRECTORY}"
                    f"/{item.spec.source}"
                ),
                "digest": item.digest,
                "owner": item.spec.owner,
                "visible_to": list(item.spec.visible_to),
                "host_private": item.spec.host_private,
            }
            for item in resolved
        ],
        "stage_facts": dict(package.stage_facts or {}),
        "platform_bindings": dict(package.platform_bindings or {}),
        "write_positions": dict(package.write_positions or {}),
        **({"request_id": request_id} if request_id else {}),
    }
    platform_data_bytes = None
    if package.platform_data is not None:
        platform_data_bytes = _canonical_bytes(package.platform_data)
        manifest_payload["platform_data"] = {
            "path": PLATFORM_DATA_PATH,
            "digest": "sha256:" + hashlib.sha256(platform_data_bytes).hexdigest(),
            "snapshot_digest": package.platform_data["digest"],
        }
    _verify_cross_bindings(manifest_payload, resolved, run_root)
    # Dedup (design §3.4): same kind/scope/artifact digests/stage decisions/
    # write positions returns the existing package even under a new request id.
    signature = content_signature(manifest_payload)
    for existing_id in _published_checkpoint_ids(run_root):
        try:
            existing = _load_manifest_file(manifest_path(run_root, existing_id))
        except CheckpointError:
            continue
        if content_signature(existing) == signature:
            return {
                "status": "reused",
                "checkpoint_id": existing_id,
                "manifest_digest": manifest_digest(manifest_path(run_root, existing_id)),
                "artifact_count": len(existing.get("artifacts") or []),
            }
    base = checkpoints_root(run_root)
    base.mkdir(parents=True, exist_ok=True)
    occupied = {name for name in _published_checkpoint_ids(run_root)} | {
        entry.name.split(".")[0]
        for entry in base.iterdir()
        if entry.is_dir()
    }
    ordinal = 1
    while True:
        checkpoint_id = f"{package.kind}-{ordinal:04d}"
        if checkpoint_id not in occupied:
            break
        ordinal += 1
    manifest_payload["checkpoint_id"] = checkpoint_id
    final_directory = base / checkpoint_id
    temp_directory = base / f".{checkpoint_id}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        temp_directory.mkdir(parents=True, mode=0o700)
        if platform_data_bytes is not None:
            data_path = temp_directory / PLATFORM_DATA_PATH
            data_path.parent.mkdir(mode=0o700, exist_ok=True)
            with data_path.open("xb") as stream:
                os.chmod(data_path, 0o600)
                stream.write(platform_data_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        for item in resolved:
            source = run_root.joinpath(*PurePosixPath(item.spec.source).parts)
            side = (
                CHECKPOINT_HOST_PRIVATE_DIRECTORY
                if item.spec.host_private
                else CHECKPOINT_ARTIFACTS_DIRECTORY
            )
            destination = temp_directory / side / item.spec.source
            _copy_artifact(source, destination, item.digest)
            # §3.3.1: confirm neither the copy nor the source drifted while the
            # package was being assembled.
            if file_digest(destination) != item.digest or file_digest(source) != item.digest:
                raise CheckpointError(
                    "artifact_changed",
                    f"artifact {item.spec.source!r} changed while the checkpoint "
                    "was being captured",
                    obj="artifact_source",
                    retry="retry this save once the source files are stable",
                )
        manifest_bytes = _canonical_bytes(manifest_payload) + b"\n"
        manifest_file = temp_directory / CHECKPOINT_MANIFEST_NAME
        with manifest_file.open("wb") as stream:
            stream.write(manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic publish LAST: the rename makes manifest presence the sole
        # usability marker; a crash before it leaves only an ignorable temp dir.
        os.rename(temp_directory, final_directory)
    except CheckpointError:
        shutil.rmtree(temp_directory, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(temp_directory, ignore_errors=True)
        raise CheckpointError(
            "checkpoint_write_failed",
            f"checkpoint package could not be written ({type(exc).__name__})",
            obj="checkpoints",
        ) from exc
    return {
        "status": "saved",
        "checkpoint_id": checkpoint_id,
        "manifest_digest": f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}",
        "artifact_count": len(resolved),
    }


def _verify_cross_bindings(
    manifest_payload: Mapping[str, Any],
    resolved: list[ResolvedArtifact],
    run_root: Path,
) -> None:
    """Check the stage-fact bindings against the packaged digests (§3.3.1).

    ``stage_facts.bindings`` lists ``{"artifact": <source>, "digest": <sha256>}``
    entries the kind builder derived from the candidate/decision/plan/freeze
    artifacts; every entry must be packaged with exactly that digest.
    """

    stage_facts = manifest_payload.get("stage_facts") or {}
    digests = {item.spec.source: item.digest for item in resolved}
    for binding in stage_facts.get("bindings") or []:
        if not isinstance(binding, Mapping):
            raise CheckpointError(
                "checkpoint_binding_invalid",
                "a stage-fact binding entry is not an object",
                obj="stage_facts.bindings",
                retryable=False,
            )
        source = binding.get("artifact")
        digest = binding.get("digest")
        if source not in digests:
            raise CheckpointError(
                "checkpoint_binding_invalid",
                f"binding references unpackaged artifact {source!r}",
                obj="stage_facts.bindings",
                retry=f"package {source!r} before saving this checkpoint",
            )
        if digests[source] != digest:
            raise CheckpointError(
                "artifact_changed",
                f"binding digest for {source!r} does not match the packaged file",
                obj="stage_facts.bindings",
                retry="retry this save once the source files are stable",
            )


# --- Read-only inspection -------------------------------------------------------


def list_checkpoints(run_root: Path) -> list[dict[str, Any]]:
    """Summaries of published packages only; half-packages are never listed."""

    run_root = Path(run_root)
    summaries: list[dict[str, Any]] = []
    for checkpoint_id in _published_checkpoint_ids(run_root):
        package_root = checkpoints_root(run_root) / checkpoint_id
        size = sum(
            path.stat().st_size for path in package_root.rglob("*") if path.is_file()
        )
        try:
            manifest = _load_manifest_file(manifest_path(run_root, checkpoint_id))
        except CheckpointError:
            # A corrupt sibling package must not break the listing of the
            # others; it is reported as unusable, never as an available
            # checkpoint (test plan M08).
            summaries.append(
                {
                    "checkpoint_id": checkpoint_id,
                    "kind": None,
                    "source_run_id": None,
                    "created_at": None,
                    "artifact_count": 0,
                    "size_bytes": size,
                    "manifest_digest": None,
                    "status": "unparsable",
                }
            )
            continue
        summaries.append(
            {
                "checkpoint_id": checkpoint_id,
                "kind": manifest.get("kind"),
                "source_run_id": manifest.get("source_run_id"),
                "created_at": manifest.get("created_at"),
                "artifact_count": len(manifest.get("artifacts") or []),
                "size_bytes": size,
                "manifest_digest": manifest_digest(manifest_path(run_root, checkpoint_id)),
                "status": "listed",
            }
        )
    return summaries


def _checkpoint_inspection(run_root: Path, checkpoint_id: str) -> dict[str, Any]:
    manifest, issues = _verify_package(run_root, checkpoint_id)
    stage_facts = manifest.get("stage_facts") or {}
    write_positions = manifest.get("write_positions") or {}
    positions = write_positions.get("positions") or []
    completed = [
        item for item in positions if isinstance(item, Mapping) and item.get("state") == "applied"
    ]
    unreconciled = [
        item
        for item in positions
        if isinstance(item, Mapping)
        and item.get("state") in {"unknown", "pending", "in_flight"}
    ]
    configuration = manifest.get("configuration") or {}
    configuration_issues = [
        f"configuration is missing {name}"
        for name in ("profile_id", "task_id")
        if not isinstance(configuration.get(name), str) or not configuration.get(name)
    ]
    issues.extend(configuration_issues)
    kind = manifest.get("kind")
    resume_bindings = production_resume_bindings(manifest)
    handoff_kind = kind == CHECKPOINT_KIND_PRODUCTION_HANDOFF
    if not handoff_kind and resume_bindings is None:
        # Same criterion as the resume hard gate (§5.2): a package without a
        # reattachable Project/Ontology identity is never reported as ready
        # for a production resume it cannot deliver.
        issues.append(
            "platform_bindings record no Project/Ontology identity for a "
            "production resume"
        )
    if issues:
        status = "incompatible"
    elif unreconciled or stage_facts.get("pending"):
        status = "needs_reconciliation"
    else:
        status = "ready"
    production_resume: dict[str, Any]
    if handoff_kind:
        production_resume = {
            "available": False,
            "reason": "a production_handoff checkpoint continues through "
            "independent acceptance continuation (--mode acceptance), not a "
            "production resume",
        }
    elif resume_bindings is not None:
        production_resume = {
            "available": True,
            "project_id": resume_bindings["project_id"],
            "ontology_ids": resume_bindings["ontology_ids"],
        }
    else:
        production_resume = {
            "available": False,
            "reason": "the manifest records no Project/Ontology platform bindings "
            "to reattach",
        }
    estimated = (
        {
            "acceptance_only_semantic_starts": 0,
            "note": "acceptance-only continuation consumes no semantic start",
        }
        if kind == CHECKPOINT_KIND_PRODUCTION_HANDOFF
        else {
            "production_resume_semantic_starts": 1,
            "note": "a new production thread from a checkpoint counts as one fresh "
            "semantic start; save/inspect consume none",
        }
    )
    return {
        "checkpoint_id": checkpoint_id,
        "kind": kind,
        "source_run_id": manifest.get("source_run_id"),
        "root_run_id": manifest.get("root_run_id"),
        "created_at": manifest.get("created_at"),
        "scope_refs": manifest.get("scope_refs") or {},
        "status": status,
        "issues": issues,
        "production_resume": production_resume,
        "fork_resume": {
            "available": bool(manifest.get("platform_data")) and not issues and not handoff_kind,
            "snapshot": manifest.get("platform_data"),
            "requires": "explicit fork_reason and stopped source writer",
        },
        "reusable_artifacts": [
            {
                "source": artifact.get("source"),
                "digest": artifact.get("digest"),
                "owner": artifact.get("owner"),
                "visible_to": artifact.get("visible_to"),
                "host_private": artifact.get("host_private"),
            }
            for artifact in manifest.get("artifacts") or []
            if isinstance(artifact, Mapping)
        ],
        "remaining_work": {
            "pending": stage_facts.get("pending") or [],
            "next_step": stage_facts.get("next_step"),
        },
        "write_reconciliation": {
            "completed_operations": [item.get("idempotency_key") for item in completed],
            "unreconciled": [
                {key: item.get(key) for key in ("idempotency_key", "state")}
                for item in unreconciled
            ],
            "recorded_at_save": {
                "in_flight": write_positions.get("in_flight") or [],
                "unknown": write_positions.get("unknown") or [],
            },
        },
        "compatibility": {
            "schema_version": manifest.get("schema_version"),
            "configuration": configuration,
            "compatible": not issues,
        },
        "estimated_authorization_consumption": estimated,
        "manifest_digest": manifest_digest(manifest_path(run_root, checkpoint_id)),
    }


def inspect_checkpoints(run_root: Path, checkpoint_id: str | None = None) -> dict[str, Any]:
    """Host-only read-only inspection (design §4.1 / test plan M08, M47).

    Without ``checkpoint_id`` every published package is listed with counts,
    sizes and retention state; no checkpoint is auto-selected and nothing is
    written.  A bad id, an unreadable manifest or a path escape is a typed
    rejection, not a silent fallback to another package.
    """

    run_root = Path(run_root)
    summaries = list_checkpoints(run_root)
    result: dict[str, Any] = {
        "run_root": str(run_root),
        "published_count": len(summaries),
        "cumulative_size_bytes": sum(item["size_bytes"] for item in summaries),
        "checkpoints": summaries,
        "consumes_semantic_start": False,
        "delivery_segments": dict(CHECKPOINT_DELIVERY_SEGMENTS),
        "resume": {
            "available": True,
            "modes": {
                "production": {
                    "delivered": True,
                    "entry": "checkpoint resume --run-id <source> --checkpoint-id <id> "
                    "--new-run-id <new> --mode production",
                    "semantic_starts": 1,
                },
                "acceptance": {
                    "delivered": True,
                    "entry": "checkpoint resume --run-id <source> --checkpoint-id "
                    "<id> --new-run-id <new> --mode acceptance",
                    "semantic_starts": 0,
                    "note": "acceptance-only continuation of a "
                    "production_handoff checkpoint; it consumes no semantic "
                    "start and never starts a production thread",
                },
            },
            "note": "an inspect result never doubles as a launch credential; "
            "resume re-verifies all state at resume time",
        },
    }
    if checkpoint_id is None:
        return result
    safe_checkpoint_id(checkpoint_id)
    if checkpoint_id not in _published_checkpoint_ids(run_root):
        raise CheckpointError(
            "checkpoint_not_found",
            f"no published checkpoint {checkpoint_id!r} in this run",
            obj="checkpoint_id",
            retryable=False,
            retry="list checkpoints without --checkpoint-id and use a published id",
        )
    result["checkpoint"] = _checkpoint_inspection(run_root, checkpoint_id)
    return result


# --- Retention and projection ---------------------------------------------------


def scope_retention_reference(run_root: Path) -> dict[str, Any] | None:
    """Design §3.3.5: published *and digest-verifiable* checkpoints only.

    The cleanup path may keep an otherwise-empty owned scope only when at least
    one fully published, fully verifying package references the run.  A
    selector flag alone, a failed save or a temp directory never counts.
    """

    run_root = Path(run_root)
    references: list[str] = []
    for checkpoint_id in _published_checkpoint_ids(run_root):
        try:
            _manifest, issues = _verify_package(run_root, checkpoint_id)
        except (CheckpointError, OSError):
            continue
        if not issues:
            references.append(checkpoint_id)
    if not references:
        return None
    return {
        "reason": "published-valid-checkpoint-reference",
        "checkpoint_ids": references,
        "count": len(references),
    }


def public_role_projection(manifest: Mapping[str, Any], role: str) -> dict[str, Any]:
    """Per-role visible projection generated from artifact ownership (§3.2).

    The projection is derived from each entry's ``visible_to``/``host_private``
    ownership, never by copying the run and filtering a few file names.  A
    production role can only ever see its explicitly granted entries; the
    host-private side (frozen pool, hidden basis, approved interview
    originals) is invisible to it by construction.
    """

    role = str(role)
    visible = [
        {
            "source": artifact.get("source"),
            "digest": artifact.get("digest"),
            "owner": artifact.get("owner"),
        }
        for artifact in manifest.get("artifacts") or []
        if isinstance(artifact, Mapping)
        and not artifact.get("host_private")
        and role in (artifact.get("visible_to") or [])
    ]
    return {
        "role": role,
        "visible_artifacts": visible,
        "host_private_note": (
            "host-private material (frozen pool, hidden basis, approved "
            "interview originals) is not part of this projection"
        ),
    }
