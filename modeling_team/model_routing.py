"""R2.3-007 Team Model Profile routing.

Loads repository-owned Team Model Profiles, resolves per-role provider/model/
effort bindings through a closed provider catalog, binds Host-owned provider
credentials, and owns one loopback Responses session per provider actually
referenced by the profile.  Profiles declare business routing only; the catalog
fixes endpoints, TLS, model allowlists, effort capability, and credential
validators.  No plugin discovery, no ambient environment fallback.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

import yaml

from .contracts import SAFE_ID, TeamConfigurationError
from .deepseek_provider_proxy import (
    DeepSeekCredentialError,
    ResponsesProviderSession,
    preflight_deepseek_credential,
    read_deepseek_credential,
)


MODEL_PROFILE_SCHEMA_VERSION = 1
MODEL_PROFILE_DIRECTORY = Path("modeling_team/model-profiles")
DEFAULT_MODEL_PROFILE_ID = "deepseek-v4-flash-max"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_CREDENTIAL_PATH = Path(
    "~/.config/ontology-platform/modeling-team-openai.env"
).expanduser()
MODEL_PROFILE_PACKAGE_IDS = (
    "coordinator",
    "modeling",
    "protocol",
    "acceptance",
    "source-examiner",
    "platform-examiner",
)
REQUESTED_EFFORT_TIERS = ("none", "low", "medium", "high", "xhigh", "max")

_OPENAI_CREDENTIAL_MAX_BYTES = 4096
_OPENAI_CREDENTIAL_RE = re.compile(r"OPENAI_API_KEY=([^\s\"'\r\n=]+)\n?\Z")


class TeamModelProfileError(TeamConfigurationError):
    """Fixed-code configuration failure for any invalid team model profile."""

    category = "configuration"
    reason_code = "model-profile-invalid"


class ProviderCredentialUnavailableError(TeamConfigurationError):
    """Machine-readable pre-run credential failure for a referenced provider."""

    category = "runtime/infrastructure"
    reason_code = "provider-credential-unavailable"


class OpenAICredentialError(RuntimeError):
    """Typed, provider-text-free OpenAI credential validation failure."""


@dataclass(frozen=True)
class ProviderRoute:
    """Closed catalog entry; profiles cannot override any field."""

    provider_id: str
    wire_api: str
    upstream_url: str
    credential_env: str
    models: frozenset[str]
    effort_effective: Mapping[str, str]

    def effective_effort(self, requested: str) -> str | None:
        return self.effort_effective.get(requested)


DEEPSEEK_DIRECT_ROUTE = ProviderRoute(
    provider_id="deepseek-direct",
    wire_api="responses",
    upstream_url="https://api.deepseek.com/responses",
    credential_env="DEEPSEEK_API_KEY",
    models=frozenset({"deepseek-v4-flash"}),
    effort_effective=MappingProxyType(
        {"low": "high", "medium": "high", "high": "high", "xhigh": "max", "max": "max"}
    ),
)
OPENAI_DIRECT_ROUTE = ProviderRoute(
    provider_id="openai-direct",
    wire_api="responses",
    upstream_url="https://api.openai.com/v1/responses",
    credential_env="OPENAI_API_KEY",
    models=frozenset({"gpt-5.6-luna"}),
    effort_effective=MappingProxyType(
        {tier: tier for tier in REQUESTED_EFFORT_TIERS}
    ),
)
PROVIDER_CATALOG: Mapping[str, ProviderRoute] = MappingProxyType(
    {"deepseek-direct": DEEPSEEK_DIRECT_ROUTE, "openai-direct": OPENAI_DIRECT_ROUTE}
)


@dataclass(frozen=True)
class RoleModelBinding:
    """Frozen per-role route binding with requested and effective effort."""

    package_id: str
    provider_id: str
    model: str
    requested_effort: str
    effective_effort: str

    def as_dict(self) -> dict[str, str]:
        return {
            "model_provider": self.provider_id,
            "model": self.model,
            "requested_effort": self.requested_effort,
            "effective_effort": self.effective_effort,
        }


@dataclass(frozen=True)
class TeamModelProfile:
    """Immutable loaded profile: identity, source digest, six role bindings."""

    profile_id: str
    relative_path: str
    digest: str
    bindings: Mapping[str, RoleModelBinding]

    def binding_for(self, package_id: str) -> RoleModelBinding:
        try:
            return self.bindings[package_id]
        except KeyError as exc:
            raise TeamModelProfileError(
                f"team model profile has no declaration for {package_id}"
            ) from exc

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted({binding.provider_id for binding in self.bindings.values()}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "path": self.relative_path,
            "sha256": self.digest,
            "roles": {
                package_id: self.bindings[package_id].as_dict()
                for package_id in MODEL_PROFILE_PACKAGE_IDS
            },
        }


class _StrictProfileLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
            except TypeError:
                duplicate = False
            if duplicate:
                raise TeamModelProfileError("team model profile has duplicate keys")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _profile_relative_path(profile_id: str) -> Path:
    if not isinstance(profile_id, str) or not SAFE_ID.fullmatch(profile_id or ""):
        raise TeamModelProfileError("team model profile ID is invalid")
    return MODEL_PROFILE_DIRECTORY / f"{profile_id}.yaml"


def _resolve_profile_path(repository_root_path: Path, relative: Path) -> Path:
    root = Path(repository_root_path).resolve()
    path = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise TeamModelProfileError("team model profile is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise TeamModelProfileError("team model profile cannot be a symlink")
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise TeamModelProfileError("team model profile is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise TeamModelProfileError("team model profile is not a regular file")
    return path


def load_team_model_profile(root: Path, profile_id: str) -> TeamModelProfile:
    """Load and fully validate one repository-owned profile by restricted ID."""

    relative = _profile_relative_path(profile_id)
    path = _resolve_profile_path(root, relative)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise TeamModelProfileError("team model profile is unreadable") from exc
    digest = hashlib.sha256(payload).hexdigest()
    try:
        value = yaml.load(payload.decode("utf-8"), Loader=_StrictProfileLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise TeamModelProfileError("team model profile is malformed") from exc
    if not isinstance(value, dict):
        raise TeamModelProfileError("team model profile is not an object")
    if set(value) != {"schema_version", "model_profile_id", "roles"}:
        raise TeamModelProfileError("team model profile fields drift")
    if value.get("schema_version") != MODEL_PROFILE_SCHEMA_VERSION:
        raise TeamModelProfileError("team model profile schema version is unsupported")
    if value.get("model_profile_id") != profile_id:
        raise TeamModelProfileError("team model profile identifier drifts")
    roles = value.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(MODEL_PROFILE_PACKAGE_IDS):
        raise TeamModelProfileError("team model profile role bindings drift")
    bindings: dict[str, RoleModelBinding] = {}
    for package_id in MODEL_PROFILE_PACKAGE_IDS:
        declaration = roles.get(package_id)
        if not isinstance(declaration, dict) or set(declaration) != {
            "model_provider",
            "model",
            "model_reasoning_effort",
        }:
            raise TeamModelProfileError(
                f"team model profile declaration for {package_id} is incomplete"
            )
        provider_id = declaration.get("model_provider")
        model = declaration.get("model")
        requested_effort = declaration.get("model_reasoning_effort")
        if any(
            not isinstance(item, str) or not item
            for item in (provider_id, model, requested_effort)
        ):
            raise TeamModelProfileError(
                f"team model profile declaration for {package_id} is malformed"
            )
        route = PROVIDER_CATALOG.get(provider_id)
        if route is None:
            raise TeamModelProfileError(
                f"team model profile provider for {package_id} is unknown"
            )
        if model not in route.models:
            raise TeamModelProfileError(
                f"team model profile model for {package_id} is unsupported"
            )
        if requested_effort not in REQUESTED_EFFORT_TIERS:
            raise TeamModelProfileError(
                f"team model profile effort for {package_id} is unsupported"
            )
        effective_effort = route.effective_effort(requested_effort)
        if effective_effort is None:
            raise TeamModelProfileError(
                f"team model profile effort for {package_id} has no provider mapping"
            )
        bindings[package_id] = RoleModelBinding(
            package_id=package_id,
            provider_id=provider_id,
            model=model,
            requested_effort=requested_effort,
            effective_effort=effective_effort,
        )
    return TeamModelProfile(
        profile_id=profile_id,
        relative_path=relative.as_posix(),
        digest=digest,
        bindings=MappingProxyType(bindings),
    )


@dataclass(frozen=True)
class OpenAICredentialBinding:
    """Non-secret file identity frozen during Runner.prepare."""

    path: Path
    st_dev: int
    st_ino: int
    st_size: int
    st_mtime_ns: int

    @property
    def canonical_path(self) -> str:
        return str(self.path)

    def metadata_matches(self, metadata: os.stat_result) -> bool:
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_dev == self.st_dev
            and metadata.st_ino == self.st_ino
            and metadata.st_size == self.st_size
            and metadata.st_mtime_ns == self.st_mtime_ns
        )


def _canonical_openai_credential_path(path: Path | str | None) -> Path:
    value = Path(path) if path is not None else OPENAI_CREDENTIAL_PATH
    try:
        expanded = value.expanduser().absolute()
        try:
            metadata = os.lstat(expanded)
        except FileNotFoundError:
            metadata = None
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise OpenAICredentialError("OpenAI credential file is insecure")
        return expanded.resolve(strict=False)
    except OpenAICredentialError:
        raise
    except (OSError, RuntimeError) as exc:
        raise OpenAICredentialError("OpenAI credential path is invalid") from exc


def _validate_openai_credential_bytes(payload: bytes) -> bytes:
    if not payload or len(payload) > _OPENAI_CREDENTIAL_MAX_BYTES:
        raise OpenAICredentialError("OpenAI credential file is malformed")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpenAICredentialError("OpenAI credential file is malformed") from exc
    match = _OPENAI_CREDENTIAL_RE.fullmatch(text)
    if match is None:
        raise OpenAICredentialError("OpenAI credential assignment is malformed")
    value = match.group(1)
    if not value or value.strip() != value:
        raise OpenAICredentialError("OpenAI credential assignment is malformed")
    return value.encode("utf-8")


def preflight_openai_credential(path: Path | str | None = None) -> OpenAICredentialBinding:
    """Validate the fixed external file and return only non-secret metadata."""

    canonical = _canonical_openai_credential_path(path)
    try:
        metadata = os.lstat(canonical)
    except OSError as exc:
        raise OpenAICredentialError("OpenAI credential file is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise OpenAICredentialError("OpenAI credential file is insecure")
    try:
        payload = canonical.read_bytes()
    except OSError as exc:
        raise OpenAICredentialError("OpenAI credential file is unreadable") from exc
    # Validate now but deliberately discard the value; only file identity leaves
    # this function.
    _validate_openai_credential_bytes(payload)
    return OpenAICredentialBinding(
        canonical,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def read_openai_credential(binding: OpenAICredentialBinding) -> bytes:
    """Open with O_NOFOLLOW and revalidate the prepare-time identity."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(binding.path, flags)
    except OSError as exc:
        raise OpenAICredentialError("OpenAI credential open failed") from exc
    try:
        metadata = os.fstat(descriptor)
        if not binding.metadata_matches(metadata):
            raise OpenAICredentialError("OpenAI credential binding changed")
        payload = os.read(descriptor, _OPENAI_CREDENTIAL_MAX_BYTES + 1)
        if len(payload) > _OPENAI_CREDENTIAL_MAX_BYTES:
            raise OpenAICredentialError("OpenAI credential file is malformed")
    except OSError as exc:
        raise OpenAICredentialError("OpenAI credential read failed") from exc
    finally:
        os.close(descriptor)
    return _validate_openai_credential_bytes(payload)


_PROVIDER_CREDENTIAL_PREFLIGHTS: Mapping[
    str, Callable[[Path | str | None], Any]
] = MappingProxyType(
    {
        "deepseek-direct": preflight_deepseek_credential,
        "openai-direct": preflight_openai_credential,
    }
)
_PROVIDER_CREDENTIAL_READERS: Mapping[str, Callable[[Any], bytes]] = MappingProxyType(
    {
        "deepseek-direct": read_deepseek_credential,
        "openai-direct": read_openai_credential,
    }
)


def preflight_profile_credentials(
    profile: TeamModelProfile,
    *,
    deepseek_credential_path: Path | str | None = None,
    openai_credential_path: Path | str | None = None,
) -> dict[str, Any]:
    """Preflight every provider the profile references, and no others.

    Returns a mapping of provider ID to non-secret credential binding.  Any
    failure raises the typed ``runtime/infrastructure`` credential failure; no
    run root or fake evidence is created by this function.
    """

    paths: dict[str, Path | str | None] = {
        "deepseek-direct": deepseek_credential_path,
        "openai-direct": openai_credential_path,
    }
    bindings: dict[str, Any] = {}
    for provider_id in profile.provider_ids():
        preflight = _PROVIDER_CREDENTIAL_PREFLIGHTS.get(provider_id)
        if preflight is None:
            raise TeamModelProfileError(
                f"team model profile provider {provider_id} is unknown"
            )
        try:
            bindings[provider_id] = preflight(paths.get(provider_id))
        except (DeepSeekCredentialError, OpenAICredentialError) as exc:
            raise ProviderCredentialUnavailableError(
                f"provider credential preflight failed for {provider_id}"
            ) from exc
    return bindings


class ProviderSessionManagerError(RuntimeError):
    """Typed, provider-text-free provider session lifecycle failure."""


class ProviderSessionManager:
    """Host-owned map of one loopback Responses session per referenced provider.

    Roles sharing a provider share its session; no secret or listener is
    duplicated per role.  ``start`` re-opens each referenced provider's
    credential with the no-follow/revalidation contract, keeps the key only in
    that session's mutable buffer, and wipes the intermediate copy.  ``stop``
    independently stops and wipes every session; one cleanup failure cannot
    skip the others.
    """

    def __init__(
        self,
        credential_bindings: Mapping[str, Any],
        *,
        on_failure: Callable[[str], None] | None = None,
        session_factory: Callable[..., ResponsesProviderSession] = ResponsesProviderSession,
    ) -> None:
        if not isinstance(credential_bindings, Mapping) or not credential_bindings:
            raise ProviderSessionManagerError("provider credential bindings are unavailable")
        self._bindings: dict[str, Any] = {}
        self._routes: dict[str, ProviderRoute] = {}
        for provider_id in sorted(credential_bindings):
            route = PROVIDER_CATALOG.get(provider_id)
            if route is None or provider_id not in _PROVIDER_CREDENTIAL_READERS:
                raise ProviderSessionManagerError("provider route is unknown")
            self._bindings[provider_id] = credential_bindings[provider_id]
            self._routes[provider_id] = route
        self._on_failure = on_failure
        self._session_factory = session_factory
        self._lock = threading.RLock()
        self._sessions: dict[str, ResponsesProviderSession] = {}
        self._stop_reports: dict[str, dict[str, bool | int]] = {}

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._routes))

    def base_url_for(self, provider_id: str) -> str:
        with self._lock:
            session = self._sessions.get(provider_id)
        if session is None:
            raise ProviderSessionManagerError("provider session is not started")
        return session.base_url

    def started(self) -> bool:
        with self._lock:
            return bool(self._sessions)

    def listening(self) -> bool:
        with self._lock:
            sessions = dict(self._sessions)
        return any(session.snapshot().get("listening") for session in sessions.values())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            sessions = dict(self._sessions)
        return {
            provider_id: dict(session.snapshot())
            for provider_id, session in sorted(sessions.items())
        }

    def secret_values(self) -> tuple[bytes, ...]:
        with self._lock:
            sessions = dict(self._sessions)
        values: list[bytes] = []
        for _provider_id, session in sorted(sessions.items()):
            value = session.secret_snapshot()
            if value:
                values.append(value)
        return tuple(values)

    def start(self) -> None:
        with self._lock:
            if self._sessions:
                return
            startup_error: Exception | None = None
            for provider_id in self.provider_ids():
                try:
                    reader = _PROVIDER_CREDENTIAL_READERS[provider_id]
                    key_buffer = bytearray(reader(self._bindings[provider_id]))
                    try:
                        session = self._session_factory(
                            key_buffer,
                            provider_id=provider_id,
                            upstream_url=self._routes[provider_id].upstream_url,
                            on_failure=self._on_failure,
                        )
                        session.start()
                    finally:
                        # The intermediate key copy never outlives construction.
                        for index in range(len(key_buffer)):
                            key_buffer[index] = 0
                    self._sessions[provider_id] = session
                except Exception as exc:  # fail closed on the first failure
                    startup_error = exc
                    break
        if startup_error is not None:
            self.stop()
            raise ProviderSessionManagerError("provider session startup failed") from (
                startup_error
            )

    def stop(self) -> dict[str, dict[str, bool | int]]:
        """Independently stop and wipe every session; report each outcome."""

        with self._lock:
            sessions = dict(self._sessions)
        reports: dict[str, dict[str, bool | int]] = {}
        for provider_id, session in sorted(sessions.items()):
            report: dict[str, bool | int] = {"lifecycle_failure": True}
            try:
                result = session.stop()
                if result is False:
                    report["lifecycle_failure"] = True
            except Exception:
                pass
            try:
                snapshot_fn = getattr(session, "stop_snapshot", None)
                if callable(snapshot_fn):
                    details = snapshot_fn()
                    if isinstance(details, dict):
                        report = {
                            key: value
                            for key, value in details.items()
                            if isinstance(value, (bool, int))
                        }
            except Exception:
                report = {"lifecycle_failure": True}
            try:
                clear_fn = getattr(session, "clear_secret", None)
                if callable(clear_fn):
                    clear_fn()
            except Exception:
                report["lifecycle_failure"] = True
            reports[provider_id] = report
        with self._lock:
            self._sessions = {}
            self._stop_reports = reports
        return reports

    def cleanup_failed(self, reports: Mapping[str, Mapping[str, Any]] | None = None) -> bool:
        if reports is None:
            with self._lock:
                reports = self._stop_reports
        return any(bool(report.get("lifecycle_failure")) for report in reports.values())


__all__ = [
    "DEFAULT_MODEL_PROFILE_ID",
    "DEEPSEEK_DIRECT_ROUTE",
    "MODEL_PROFILE_DIRECTORY",
    "MODEL_PROFILE_PACKAGE_IDS",
    "MODEL_PROFILE_SCHEMA_VERSION",
    "OPENAI_API_KEY_ENV",
    "OPENAI_CREDENTIAL_PATH",
    "OPENAI_DIRECT_ROUTE",
    "PROVIDER_CATALOG",
    "REQUESTED_EFFORT_TIERS",
    "OpenAICredentialBinding",
    "OpenAICredentialError",
    "ProviderCredentialUnavailableError",
    "ProviderSessionManager",
    "ProviderSessionManagerError",
    "RoleModelBinding",
    "TeamModelProfile",
    "TeamModelProfileError",
    "load_team_model_profile",
    "preflight_openai_credential",
    "preflight_profile_credentials",
    "read_openai_credential",
]
