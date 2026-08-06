"""Append-only, Runtime-neutral Task input overlay contract.

The overlay never rewrites a Team Task.  It binds one authoritative base Task
and one Runner-private candidate carrier used by the optional typed Modeling
publication capability.
"""

from __future__ import annotations

import hashlib
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .contracts import TeamConfigurationError, TeamTask, digest_file


_SAFE_OVERLAY_ID = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OVERLAY_FIELDS = {
    "schema_version",
    "overlay_id",
    "base_task",
    "candidate_publication",
}
_BASE_TASK_FIELDS = {"path", "task_id", "sha256"}
_CANDIDATE_PUBLICATION_FIELDS = {
    "path",
    "sha256",
    "mode",
    "classification",
    "roles",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class CandidatePublicationSource:
    path: Path
    relative_path: Path
    sha256: str
    mode: int


@dataclass(frozen=True)
class TaskInputOverlay:
    overlay_id: str
    base_task_id: str
    path: Path
    relative_path: Path
    sha256: str
    overlay_bytes: bytes
    base_task_path: Path
    base_task_relative_path: Path
    base_task_sha256: str
    base_task_bytes: bytes
    candidate_publication: CandidatePublicationSource

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "overlay_id": self.overlay_id,
            "overlay": {
                "path": self.relative_path.as_posix(),
                "sha256": self.sha256,
                "mode": "0444",
            },
            "base_task": {
                "task_id": self.base_task_id,
                "path": self.base_task_relative_path.as_posix(),
                "sha256": self.base_task_sha256,
            },
            "candidate_publication": {
                "path": self.candidate_publication.relative_path.as_posix(),
                "sha256": self.candidate_publication.sha256,
                "mode": f"{self.candidate_publication.mode:04o}",
                "classification": "coordination",
                "roles": ["modeling"],
            },
        }


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise TeamConfigurationError(f"{field} must be a lowercase SHA-256")
    return value


def _repository_file(
    root: Path,
    value: object,
    *,
    field: str,
    mode: int | None,
) -> tuple[Path, Path]:
    if not isinstance(value, str) or not value:
        raise TeamConfigurationError(f"{field} must be a repository-relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise TeamConfigurationError(f"{field} escapes repository")
    root = root.resolve()
    candidate = root / relative
    try:
        current = root
        for component in relative.parts:
            current /= component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise TeamConfigurationError(f"{field} contains a symlink")
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except TeamConfigurationError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise TeamConfigurationError(f"{field} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise TeamConfigurationError(f"{field} is not a regular repository file")
    if mode is not None and stat.S_IMODE(metadata.st_mode) != mode:
        raise TeamConfigurationError(f"{field} mode must be {mode:04o}")
    return resolved, resolved.relative_to(root)


def load_task_input_overlay(
    path: Path,
    *,
    root: Path,
    task_path: Path,
    task: TeamTask,
) -> TaskInputOverlay:
    """Load one exact append-only overlay without changing ``task``."""

    root = root.resolve()
    if task.task_id != "r2-3-005-formal-acceptance":
        raise TeamConfigurationError("Task overlay is formal R2.3-005-only")
    supplied_path = Path(path)
    if not supplied_path.is_absolute():
        supplied_path = root / supplied_path
    try:
        supplied_metadata = supplied_path.lstat()
        overlay_relative = supplied_path.absolute().relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise TeamConfigurationError("Task overlay escapes repository or is unavailable") from exc
    if stat.S_ISLNK(supplied_metadata.st_mode):
        raise TeamConfigurationError("Task overlay is not a regular repository file")
    overlay_path, overlay_relative = _repository_file(
        root,
        overlay_relative.as_posix(),
        field="Task overlay",
        mode=0o444,
    )
    try:
        overlay_bytes = overlay_path.read_bytes()
        data = yaml.load(overlay_bytes.decode("utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise TeamConfigurationError("Task overlay is unreadable") from exc
    if not isinstance(data, dict) or set(data) != _OVERLAY_FIELDS:
        raise TeamConfigurationError("Task overlay fields drift from schema")
    if data.get("schema_version") != 1:
        raise TeamConfigurationError("Task overlay schema version is invalid")
    overlay_id = data.get("overlay_id")
    if not isinstance(overlay_id, str) or not _SAFE_OVERLAY_ID.fullmatch(overlay_id):
        raise TeamConfigurationError("Task overlay ID is invalid")

    base = data.get("base_task")
    if not isinstance(base, dict) or set(base) != _BASE_TASK_FIELDS:
        raise TeamConfigurationError("Task overlay base Task fields drift")
    if base.get("task_id") != task.task_id:
        raise TeamConfigurationError("Task overlay base Task ID drifted")
    base_path, base_relative = _repository_file(
        root,
        base.get("path"),
        field="Task overlay base Task",
        mode=None,
    )
    if base_relative.as_posix() != "modeling_team/tasks/r2-3-005-formal-acceptance.yaml":
        raise TeamConfigurationError("Task overlay base Task is not the authoritative formal Task")
    supplied_task_path = Path(task_path)
    if not supplied_task_path.is_absolute():
        supplied_task_path = root / supplied_task_path
    try:
        supplied_task_relative = supplied_task_path.absolute().relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise TeamConfigurationError("Task overlay base Task is unavailable") from exc
    supplied_task, _ = _repository_file(
        root,
        supplied_task_relative.as_posix(),
        field="supplied Task overlay base Task",
        mode=None,
    )
    if supplied_task != base_path:
        raise TeamConfigurationError("Task overlay requires its authoritative base Task path")
    expected_task_digest = _sha256(base.get("sha256"), "Task overlay base Task sha256")
    base_task_bytes = base_path.read_bytes()
    if hashlib.sha256(base_task_bytes).hexdigest() != expected_task_digest:
        raise TeamConfigurationError("Task overlay base Task digest drifted")

    publication = data.get("candidate_publication")
    if not isinstance(publication, dict) or set(publication) != _CANDIDATE_PUBLICATION_FIELDS:
        raise TeamConfigurationError("Task overlay candidate publication fields drift")
    if publication.get("mode") != "0444":
        raise TeamConfigurationError("Task overlay candidate publication mode is invalid")
    if publication.get("classification") != "coordination":
        raise TeamConfigurationError("Task overlay candidate publication classification is invalid")
    if publication.get("roles") != ["modeling"]:
        raise TeamConfigurationError("Task overlay candidate publication role is invalid")
    candidate_path, candidate_relative = _repository_file(
        root,
        publication.get("path"),
        field="Task overlay candidate publication source",
        mode=0o444,
    )
    expected_candidate_digest = _sha256(
        publication.get("sha256"),
        "Task overlay candidate publication sha256",
    )
    if digest_file(candidate_path) != expected_candidate_digest:
        raise TeamConfigurationError("Task overlay candidate publication digest drifted")
    if candidate_path in {overlay_path, base_path}:
        raise TeamConfigurationError("Task overlay candidate publication source is duplicated")

    return TaskInputOverlay(
        overlay_id=overlay_id,
        base_task_id=task.task_id,
        path=overlay_path,
        relative_path=overlay_relative,
        sha256=hashlib.sha256(overlay_bytes).hexdigest(),
        overlay_bytes=overlay_bytes,
        base_task_path=base_path,
        base_task_relative_path=base_relative,
        base_task_sha256=expected_task_digest,
        base_task_bytes=base_task_bytes,
        candidate_publication=CandidatePublicationSource(
            path=candidate_path,
            relative_path=candidate_relative,
            sha256=expected_candidate_digest,
            mode=0o444,
        ),
    )
