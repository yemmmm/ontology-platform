"""Validated formal model policy for the R2.3-005 Luna-max Team."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

from .contracts import TeamConfigurationError


FORMAL_MODEL_MANIFEST_RELATIVE = Path(
    "modeling_team/model-manifests/r2-3-005-luna-max.yaml"
)
FORMAL_MODEL_MANIFEST_ID = "r2-3-005-luna-max"
FORMAL_MODEL_PROFILE_ID = "r2-3-005-modeling-team"
FORMAL_MODEL_TASK_ID = "r2-3-005-formal-acceptance"
FORMAL_MODEL_SCHEMA_VERSION = 1
FORMAL_MODEL_TUPLE = ("gpt-5.6-luna", "openai", "max")
FORMAL_MODEL_PACKAGE_IDS = (
    "coordinator",
    "modeling",
    "protocol",
    "acceptance",
    "source-examiner",
    "platform-examiner",
)
_FORMAL_MODEL_KEYS = frozenset(
    {"model", "model_provider", "model_reasoning_effort"}
)
_FORMAL_MANIFEST_KEYS = frozenset(
    {"schema_version", "manifest_id", "profile_id", "task_id", "packages"}
)


@dataclass(frozen=True)
class FormalModelManifest:
    """Immutable validated mapping plus the exact source-artifact digest."""

    overrides: Mapping[str, tuple[str, str, str]]
    digest: str
    relative_path: str = str(FORMAL_MODEL_MANIFEST_RELATIVE)

    @property
    def artifact_digest(self) -> str:
        return self.digest

    @property
    def manifest_digest(self) -> str:
        return self.digest

    def __getitem__(self, package_id: str) -> tuple[str, str, str]:
        return self.override_for(package_id)

    def __iter__(self):
        return iter(self.overrides)

    def __len__(self) -> int:
        return len(self.overrides)

    def items(self):
        return self.overrides.items()

    def override_for(self, package_id: str) -> tuple[str, str, str]:
        try:
            value = self.overrides[package_id]
        except KeyError as exc:
            raise TeamConfigurationError(
                f"formal model manifest has no declaration for {package_id}"
            ) from exc
        return value

    def as_dict(self) -> dict[str, dict[str, str]]:
        """Return a non-secret serializable projection for tests/evidence."""

        return {
            package_id: {
                "model": value[0],
                "model_provider": value[1],
                "model_reasoning_effort": value[2],
            }
            for package_id, value in sorted(self.overrides.items())
        }


def _manifest_path(root: Path) -> Path:
    repository_root = Path(root).resolve()
    path = repository_root / FORMAL_MODEL_MANIFEST_RELATIVE
    current = repository_root
    for part in FORMAL_MODEL_MANIFEST_RELATIVE.parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise TeamConfigurationError("formal model manifest is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise TeamConfigurationError("formal model manifest cannot be a symlink")
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise TeamConfigurationError("formal model manifest is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise TeamConfigurationError("formal model manifest is invalid")
    return path


def _load_manifest(path: Path) -> tuple[dict[str, object], str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise TeamConfigurationError("formal model manifest is unreadable") from exc
    digest = hashlib.sha256(payload).hexdigest()
    try:
        value = yaml.safe_load(payload.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise TeamConfigurationError("formal model manifest is malformed") from exc
    if not isinstance(value, dict):
        raise TeamConfigurationError("formal model manifest is not an object")
    return value, digest


def _validate_manifest(value: Mapping[str, object]) -> dict[str, tuple[str, str, str]]:
    if set(value) != _FORMAL_MANIFEST_KEYS:
        raise TeamConfigurationError("formal model manifest fields drift")
    if value.get("schema_version") != FORMAL_MODEL_SCHEMA_VERSION:
        raise TeamConfigurationError("formal model manifest schema version is unsupported")
    if value.get("manifest_id") != FORMAL_MODEL_MANIFEST_ID:
        raise TeamConfigurationError("formal model manifest identifier drift")
    if value.get("profile_id") != FORMAL_MODEL_PROFILE_ID:
        raise TeamConfigurationError("formal model manifest profile binding drift")
    if value.get("task_id") != FORMAL_MODEL_TASK_ID:
        raise TeamConfigurationError("formal model manifest task binding drift")
    packages = value.get("packages")
    if not isinstance(packages, dict) or set(packages) != set(FORMAL_MODEL_PACKAGE_IDS):
        raise TeamConfigurationError("formal model manifest package bindings drift")
    overrides: dict[str, tuple[str, str, str]] = {}
    for package_id in FORMAL_MODEL_PACKAGE_IDS:
        declaration = packages.get(package_id)
        if not isinstance(declaration, dict) or set(declaration) != _FORMAL_MODEL_KEYS:
            raise TeamConfigurationError(
                f"formal model manifest declaration for {package_id} is incomplete"
            )
        values = tuple(
            declaration.get(name)
            for name in ("model", "model_provider", "model_reasoning_effort")
        )
        if any(not isinstance(item, str) or not item for item in values):
            raise TeamConfigurationError(
                f"formal model manifest declaration for {package_id} is malformed"
            )
        override = (values[0], values[1], values[2])
        if override != FORMAL_MODEL_TUPLE:
            raise TeamConfigurationError(
                f"formal model manifest declaration for {package_id} is unsupported"
            )
        overrides[package_id] = override
    if tuple(overrides.values()) != (FORMAL_MODEL_TUPLE,) * len(FORMAL_MODEL_PACKAGE_IDS):
        raise TeamConfigurationError("formal model manifest declarations are inconsistent")
    return overrides


def load_formal_model_manifest(root: Path) -> FormalModelManifest:
    """Read and validate the formal manifest without filesystem side effects."""

    path = _manifest_path(root)
    value, digest = _load_manifest(path)
    overrides = _validate_manifest(value)
    return FormalModelManifest(
        MappingProxyType(dict(overrides)),
        digest,
    )


__all__ = [
    "FORMAL_MODEL_MANIFEST_ID",
    "FORMAL_MODEL_MANIFEST_RELATIVE",
    "FORMAL_MODEL_PACKAGE_IDS",
    "FORMAL_MODEL_PROFILE_ID",
    "FORMAL_MODEL_SCHEMA_VERSION",
    "FORMAL_MODEL_TASK_ID",
    "FORMAL_MODEL_TUPLE",
    "FormalModelManifest",
    "load_formal_model_manifest",
]
