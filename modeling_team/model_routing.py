"""R2.3-007 Team Model Profile routing.

Loads repository-owned Team Model Profiles, resolves per-role provider/model/
effort bindings through a closed provider catalog, binds Host-owned provider
credentials, and owns one loopback Responses session per external
credential-backed provider actually referenced by the profile.  ``openai-codex``
uses the Codex built-in OpenAI Responses route with the Host's cached ChatGPT
subscription login instead of an API key or loopback session.  Profiles declare
business routing only; the catalog fixes endpoints, TLS, model allowlists,
effort capability, and credential validators.  No plugin discovery, no ambient
environment fallback.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

import yaml

from .contracts import SAFE_ID, TeamConfigurationError
from .deepseek_provider_proxy import (
    ProviderCredentialError,
    ResponsesProviderSession,
    preflight_deepseek_credential,
    preflight_glm_credential,
    read_deepseek_credential,
    read_glm_credential,
)


MODEL_PROFILE_SCHEMA_VERSION = 1
MODEL_PROFILE_DIRECTORY = Path("modeling_team/model-profiles")
DEFAULT_MODEL_PROFILE_ID = "deepseek-v4-flash-max"
MODEL_PROFILE_PACKAGE_IDS = (
    "coordinator",
    "modeling",
    "protocol",
    "acceptance",
    "source-examiner",
    "platform-examiner",
)
DELIVERY_MODEL_PROFILE_PACKAGE_ID = "delivery"
MODEL_PROFILE_OPTIONAL_PACKAGE_IDS = (DELIVERY_MODEL_PROFILE_PACKAGE_ID,)
# The closed role universe a profile may declare.  The formal six remain the
# formal-run requirement; ``competency-question`` lets a v3 multi-slice
# profile bind the R3.0-011 roster role that is absent from formal rosters.
MODEL_PROFILE_ROLE_UNIVERSE = MODEL_PROFILE_PACKAGE_IDS + ("competency-question",)
# R4.0-023 host-side Delivery is an optional profile declaration.  Keep it out
# of MODEL_PROFILE_ROLE_UNIVERSE so old profiles and the formal six-role gate
# remain byte-compatible; only the standalone Delivery resolver consults it.
MODEL_PROFILE_ALLOWED_ROLE_UNIVERSE = (
    MODEL_PROFILE_ROLE_UNIVERSE + MODEL_PROFILE_OPTIONAL_PACKAGE_IDS
)
REQUESTED_EFFORT_TIERS = ("none", "low", "medium", "high", "xhigh", "max")
# ``openai-codex`` is the route identity used by profiles, baselines, and run
# evidence.  Only the per-role Codex TOML projection maps it onto Codex's
# built-in provider ID ``openai``; no custom provider table is declared there.
CODEX_PROVIDER_ID = "openai-codex"
CODEX_TOML_PROVIDER_ID = "openai"
CODEX_AUTH_MODE = "chatgpt-subscription"
CODEX_HOME_ENV = "CODEX_HOME"
CODEX_AUTH_CACHE_NAME = "auth.json"
CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE = "codex-subscription-auth-unavailable"
CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH = "codex-subscription-auth-mode-mismatch"


class TeamModelProfileError(TeamConfigurationError):
    """Fixed-code configuration failure for any invalid team model profile."""

    category = "configuration"
    reason_code = "model-profile-invalid"


class ProviderCredentialUnavailableError(TeamConfigurationError):
    """Machine-readable pre-run credential failure for a referenced provider."""

    category = "runtime/infrastructure"
    reason_code = "provider-credential-unavailable"


class CodexSubscriptionAuthError(TeamConfigurationError):
    """Typed pre-run failure for the Host ChatGPT subscription login.

    Only fixed local reason codes and messages leave this class; the auth cache
    content, token values, account identifiers, cache path, and the raw
    ``codex login status`` output are never carried or exposed.
    """

    category = "runtime/infrastructure"

    def __init__(self, reason_code: str, message: str) -> None:
        if reason_code not in {
            CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
            CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH,
        }:
            raise ValueError("invalid Codex subscription auth reason code")
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True)
class ProviderRoute:
    """Closed catalog entry; profiles cannot override any field.

    ``upstream_url``/``credential_env`` are ``None`` for the Codex built-in
    OpenAI route: it has no loopback session and no API-key credential, and is
    authenticated by the Host's cached ChatGPT subscription login instead.
    """

    provider_id: str
    wire_api: str
    upstream_url: str | None
    credential_env: str | None
    models: frozenset[str]
    effort_effective: Mapping[str, str]

    def effective_effort(self, requested: str) -> str | None:
        return self.effort_effective.get(requested)

    @property
    def uses_external_credential(self) -> bool:
        return self.upstream_url is not None and self.credential_env is not None


DEEPSEEK_DIRECT_ROUTE = ProviderRoute(
    provider_id="deepseek-direct",
    wire_api="responses",
    upstream_url="https://api.deepseek.com/responses",
    credential_env="DEEPSEEK_API_KEY",
    models=frozenset({"deepseek-v4-flash", "deepseek-flash"}),
    effort_effective=MappingProxyType(
        {"low": "high", "medium": "high", "high": "high", "xhigh": "max", "max": "max"}
    ),
)
GLM_DIRECT_ROUTE = ProviderRoute(
    provider_id="glm-direct",
    wire_api="responses",
    upstream_url="https://open.bigmodel.cn/api/v1/responses",
    credential_env="GLM_API_KEY",
    # ``glm-5.3`` (full model) admitted 2026-09-12 for the user-authorized
    # model-comparison round; it rides the same credential and loopback session.
    # ``glm-5.3-flashx`` admitted 2026-10-13 by explicit user authorization
    # (R4.0-019): the user-specified exact Team model -- no downgrade to
    # ``glm-5.3-flash`` and no silent fallback.  Same credential, loopback
    # session, and effort mapping.
    models=frozenset({"glm-5.3", "glm-5.3-flash", "glm-5.3-flashx"}),
    # The upstream Responses endpoint accepts ``low`` verbatim for both models
    # (verified 2026-09-13 with a one-shot probe: effort=low completed with
    # reasoning_tokens=0), so unlike the DeepSeek route ``low`` passes through
    # instead of collapsing onto ``high`` -- the auth-r3-0-012 user
    # authorization runs the Platform Examiner at low effort.  ``medium``
    # still collapses onto ``high`` and the top two onto ``max``.  ``none``
    # is deliberately unmapped, exactly as in the DeepSeek route, so a profile
    # asking for it fails at load rather than silently running at some other
    # effort.
    effort_effective=MappingProxyType(
        {"low": "low", "medium": "high", "high": "high", "xhigh": "max", "max": "max"}
    ),
)
OPENAI_CODEX_ROUTE = ProviderRoute(
    provider_id=CODEX_PROVIDER_ID,
    wire_api="responses",
    upstream_url=None,
    credential_env=None,
    models=frozenset({"gpt-5.6-luna", "gpt-6-luna", "gpt-6.1-sol"}),
    effort_effective=MappingProxyType(
        {tier: tier for tier in REQUESTED_EFFORT_TIERS}
    ),
)
DEEPSEEK_DSH_ROUTE = ProviderRoute(
    provider_id="deepseek-official",
    wire_api="messages",
    upstream_url="https://api.deepseek.com/anthropic/v1/messages",
    credential_env="DEEPSEEK_API_KEY",
    models=frozenset({"deepseek-flash"}),
    effort_effective=MappingProxyType({tier: tier for tier in ("low", "high", "max")}),
)
PROVIDER_CATALOG: Mapping[str, ProviderRoute] = MappingProxyType(
    {
        route.provider_id: route
        for route in (DEEPSEEK_DIRECT_ROUTE, GLM_DIRECT_ROUTE, OPENAI_CODEX_ROUTE, DEEPSEEK_DSH_ROUTE)
    }
)


def uses_external_credential_session(provider_id: str) -> bool:
    """Whether a provider needs a Host-owned loopback credential session."""

    route = PROVIDER_CATALOG.get(provider_id)
    return route is not None and route.uses_external_credential


def validate_runtime_model_profile(runtime: str, profile: TeamModelProfile) -> None:
    """Validate before reading credentials or starting any runtime; never remap routes."""
    for binding in profile.bindings.values():
        supported = (binding.provider_id == "deepseek-official" if runtime == "dsh"
                     else binding.provider_id != "deepseek-official")
        if not supported:
            raise TeamModelProfileError(
                f"unsupported-runtime-provider: runtime={runtime} provider={binding.provider_id} "
                f"model={binding.model} effort={binding.requested_effort}; "
                "select an explicitly authorized compatible model profile"
            )


def profile_requires_codex_subscription_auth(profile: TeamModelProfile) -> bool:
    """Whether any frozen role binding rides the Host ChatGPT login cache."""

    return any(
        binding.provider_id == CODEX_PROVIDER_ID
        for binding in profile.bindings.values()
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
        # The auth mode is a catalog-owned property of the ``openai-codex``
        # route, not a per-role editable field: it is projected only as the
        # fixed safe label, never as a token, account, cache path, or digest.
        projection: dict[str, str] = {
            "model_provider": self.provider_id,
            "model": self.model,
            "requested_effort": self.requested_effort,
            "effective_effort": self.effective_effort,
        }
        if self.provider_id == CODEX_PROVIDER_ID:
            projection["auth_mode"] = CODEX_AUTH_MODE
        return projection


@dataclass(frozen=True)
class TeamModelProfile:
    """Immutable loaded profile: identity, source digest, declared role bindings."""

    profile_id: str
    relative_path: str
    digest: str
    bindings: Mapping[str, RoleModelBinding]

    def binding_for(
        self, package_id: str, *, semantic_role: str | None = None
    ) -> RoleModelBinding:
        """Resolve a package binding, falling back to its declared semantic role.

        Profiles are keyed by the closed semantic-role vocabulary. A task may
        use a task-specific package ID for the same role, so callers that have
        already loaded that package may provide its declared role as the
        compatibility lookup key. The direct package-ID binding always wins;
        no new profile role is admitted by this fallback.
        """

        binding = self.bindings.get(package_id)
        if binding is None and semantic_role is not None:
            binding = self.bindings.get(semantic_role)
        if binding is not None:
            return binding
        raise TeamModelProfileError(
            f"team model profile has no declaration for {package_id}"
        )

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted({binding.provider_id for binding in self.bindings.values()}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "path": self.relative_path,
            "sha256": self.digest,
            "roles": {
                package_id: binding.as_dict()
                for package_id, binding in self.bindings.items()
            },
        }


def resolve_delivery_model_binding(
    profile: TeamModelProfile,
) -> tuple[RoleModelBinding, str]:
    """Resolve the standalone Delivery model and identify its source.

    An explicit ``delivery`` declaration wins.  Otherwise Delivery inherits
    the selected Coordinator's exact provider/model/effort binding, with a
    new package identity so downstream runtime code cannot accidentally treat
    the inherited route as a production Coordinator binding.  The returned
    source is one of ``"delivery"`` or ``"coordinator"`` and is safe to
    persist as configuration provenance.  A profile without either binding
    is a typed configuration error; no ambient model is selected.
    """

    if not isinstance(profile, TeamModelProfile):
        raise TeamModelProfileError("team model profile is invalid")
    explicit = profile.bindings.get(DELIVERY_MODEL_PROFILE_PACKAGE_ID)
    if explicit is not None:
        return explicit, DELIVERY_MODEL_PROFILE_PACKAGE_ID
    coordinator = profile.bindings.get("coordinator")
    if coordinator is None:
        raise TeamModelProfileError(
            "team model profile requires a coordinator or delivery binding"
        )
    return (
        RoleModelBinding(
            package_id=DELIVERY_MODEL_PROFILE_PACKAGE_ID,
            provider_id=coordinator.provider_id,
            model=coordinator.model,
            requested_effort=coordinator.requested_effort,
            effective_effort=coordinator.effective_effort,
        ),
        "coordinator",
    )


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
    if (
        not isinstance(roles, dict)
        or not roles
        or set(roles) - set(MODEL_PROFILE_ALLOWED_ROLE_UNIVERSE)
    ):
        raise TeamModelProfileError("team model profile role bindings drift")
    bindings: dict[str, RoleModelBinding] = {}
    for package_id in MODEL_PROFILE_ALLOWED_ROLE_UNIVERSE:
        # An explicit ``role: null`` is a malformed declaration, not an
        # undeclared role: only an absent key skips validation.
        if package_id not in roles:
            continue
        declaration = roles[package_id]
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
            if provider_id == "deepseek-official":
                raise TeamModelProfileError(
                    f"unsupported-runtime-model: runtime=dsh provider={provider_id} model={model} "
                    f"effort={requested_effort}; use the exact native model name"
                )
            raise TeamModelProfileError(
                f"team model profile model for {package_id} is unsupported"
            )
        if requested_effort not in REQUESTED_EFFORT_TIERS:
            raise TeamModelProfileError(
                f"team model profile effort for {package_id} is unsupported"
            )
        effective_effort = route.effective_effort(requested_effort)
        if effective_effort is None:
            if provider_id == "deepseek-official":
                raise TeamModelProfileError(
                    f"unsupported-runtime-effort: runtime=dsh provider={provider_id} model={model} "
                    f"effort={requested_effort}; native supported efforts are low/high/max"
                )
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


def _default_codex_home() -> Path:
    value = os.environ.get(CODEX_HOME_ENV)
    return Path(value).expanduser() if value else Path("~/.codex").expanduser()


def codex_auth_cache_path(codex_home: Path | str | None = None) -> Path:
    """Resolve the file-backed Codex login cache path (metadata use only)."""

    home = Path(codex_home).expanduser() if codex_home is not None else _default_codex_home()
    return home / CODEX_AUTH_CACHE_NAME


def _validate_codex_auth_cache_metadata(path: Path) -> None:
    """Metadata-only owner-private/regular-file/non-symlink check.

    The cache content is never opened, parsed, printed, or logged here; only
    ``lstat`` metadata is inspected, mirroring the established DeepSeek/host
    auth file contract.
    """

    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise CodexSubscriptionAuthError(
            CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
            "Codex subscription auth cache is unavailable",
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise CodexSubscriptionAuthError(
            CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
            "Codex subscription auth cache is insecure",
        )


def _run_codex_login_status(codex_home: Path) -> tuple[int, str]:
    """Ask the Codex CLI for its login mode; return only (exit code, output).

    codex-cli (e.g. 0.147.0) may print ``Logged in using ChatGPT`` on stderr
    with an empty stdout, so stderr is merged into the captured stream here.
    The merged output stays inside this module's fixed-mode parsing.  Callers
    must not persist or forward it: only the resulting auth-mode conclusion is
    safe to project as evidence.
    """

    environment = dict(os.environ)
    environment[CODEX_HOME_ENV] = str(codex_home)
    try:
        completed = subprocess.run(
            ["codex", "login", "status"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return completed.returncode, completed.stdout or ""


def _codex_login_mode_conclusion(returncode: int, output: str) -> str:
    if returncode != 0:
        raise CodexSubscriptionAuthError(
            CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
            "Codex subscription login status is unavailable",
        )
    lowered = output.lower()
    # An API-key hint wins even when a ChatGPT string is also present: the
    # mode-mismatch failure is the safer conclusion for an ambiguous login.
    if "api key" in lowered or "apikey" in lowered:
        raise CodexSubscriptionAuthError(
            CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH,
            "Codex subscription login mode mismatch",
        )
    if "chatgpt" in lowered:
        return CODEX_AUTH_MODE
    raise CodexSubscriptionAuthError(
        CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
        "Codex subscription login status is unavailable",
    )


def preflight_codex_subscription_auth(
    *,
    codex_home: Path | str | None = None,
    login_status: Callable[[Path], tuple[int, str]] | None = None,
) -> str:
    """Fail closed unless the Host is logged into Codex with ChatGPT.

    Checks, in order: the file-backed login cache exists and satisfies the
    owner-private/regular-file/non-symlink metadata contract (content is never
    read), and ``codex login status`` confirms the ChatGPT login mode.  Returns
    only the fixed safe auth-mode label ``chatgpt-subscription``.
    """

    home = Path(codex_home).expanduser() if codex_home is not None else _default_codex_home()
    _validate_codex_auth_cache_metadata(home / CODEX_AUTH_CACHE_NAME)
    returncode, output = (login_status or _run_codex_login_status)(home)
    return _codex_login_mode_conclusion(returncode, output)


_PROVIDER_CREDENTIAL_PREFLIGHTS: Mapping[
    str, Callable[[Path | str | None], Any]
] = MappingProxyType(
    {
        "deepseek-direct": preflight_deepseek_credential,
        "deepseek-official": preflight_deepseek_credential,
        "glm-direct": preflight_glm_credential,
    }
)
_PROVIDER_CREDENTIAL_READERS: Mapping[str, Callable[[Any], bytes]] = MappingProxyType(
    {
        "deepseek-direct": read_deepseek_credential,
        "deepseek-official": read_deepseek_credential,
        "glm-direct": read_glm_credential,
    }
)
# Every external-credential route needs all three wirings.  Asserting here turns
# a forgotten registration into an import-time failure instead of a role silently
# falling back to the Codex ChatGPT subscription at run time.
_EXTERNAL_CREDENTIAL_PROVIDER_IDS = frozenset(
    provider_id
    for provider_id, route in PROVIDER_CATALOG.items()
    if route.uses_external_credential
)
assert _EXTERNAL_CREDENTIAL_PROVIDER_IDS == frozenset(_PROVIDER_CREDENTIAL_PREFLIGHTS), (
    "provider catalog and credential preflight registry disagree"
)
assert _EXTERNAL_CREDENTIAL_PROVIDER_IDS == frozenset(_PROVIDER_CREDENTIAL_READERS), (
    "provider catalog and credential reader registry disagree"
)


def preflight_profile_credentials(
    profile: TeamModelProfile,
    *,
    deepseek_credential_path: Path | str | None = None,
    glm_credential_path: Path | str | None = None,
) -> dict[str, Any]:
    """Preflight every external credential route the profile references.

    Returns a mapping of provider ID to non-secret credential binding for the
    external credential-backed routes only; the Codex built-in ``openai-codex``
    route is authenticated by the Host ChatGPT subscription preflight instead
    and never reads an OpenAI API key or credential file.  Any failure raises
    the typed ``runtime/infrastructure`` credential failure; no run root or
    fake evidence is created by this function.

    Each path argument is an override seam for tests and callers; ``None`` means
    the route's fixed default in its credential contract.  Only providers the
    profile actually names are touched, so an unused route's file is never read.
    """

    paths: dict[str, Path | str | None] = {
        "deepseek-direct": deepseek_credential_path,
        "deepseek-official": deepseek_credential_path,
        "glm-direct": glm_credential_path,
    }
    bindings: dict[str, Any] = {}
    for provider_id in profile.provider_ids():
        if not uses_external_credential_session(provider_id):
            continue
        preflight = _PROVIDER_CREDENTIAL_PREFLIGHTS.get(provider_id)
        if preflight is None:
            raise TeamModelProfileError(
                f"team model profile provider {provider_id} is unknown"
            )
        try:
            bindings[provider_id] = preflight(paths.get(provider_id))
        except ProviderCredentialError as exc:
            raise ProviderCredentialUnavailableError(
                f"provider credential preflight failed for {provider_id}"
            ) from exc
    return bindings


class ProviderSessionManagerError(RuntimeError):
    """Typed, provider-text-free provider session lifecycle failure."""


class ProviderSessionManager:
    """Host-owned map of one loopback Responses session per external provider.

    Roles sharing a provider share its session; no secret or listener is
    duplicated per role.  Only external credential-backed routes (currently
    ``deepseek-direct``) belong here; the Codex built-in ``openai-codex`` route
    has no loopback session.  ``start`` re-opens each referenced provider's
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
        on_attempt: Callable[[dict], None] | None = None,
    ) -> None:
        if not isinstance(credential_bindings, Mapping) or not credential_bindings:
            raise ProviderSessionManagerError("provider credential bindings are unavailable")
        self._bindings: dict[str, Any] = {}
        self._routes: dict[str, ProviderRoute] = {}
        for provider_id in sorted(credential_bindings):
            route = PROVIDER_CATALOG.get(provider_id)
            if route is None or provider_id not in _PROVIDER_CREDENTIAL_READERS:
                raise ProviderSessionManagerError(
                    "provider route does not use an external credential session"
                )
            if route.wire_api != "responses":
                raise ProviderSessionManagerError(
                    f"unsupported-runtime-provider: {provider_id} requires the DSH Messages session"
                )
            self._bindings[provider_id] = credential_bindings[provider_id]
            self._routes[provider_id] = route
        self._on_attempt = on_attempt
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
                            **({"on_attempt": self._on_attempt} if self._on_attempt else {}),
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

    def restart_dead_sessions(self) -> dict[str, bool]:
        """Rebuild every session whose listener died; report per-provider outcome.

        2026-09-17 abort-park fix: an external host recovery must not assume the
        loopback session is still alive.  Each dead listener is stopped (its key
        buffer wiped) and started again, preferring the port the running
        app-servers already point at; a port that cannot be rebound falls back
        to an ephemeral one and the outcome stays visible to the caller.  A
        provider that cannot be rebuilt reports ``False`` and never raises.
        """

        with self._lock:
            targets = {
                provider_id: session
                for provider_id, session in sorted(self._sessions.items())
                if not session.snapshot().get("listening")
            }
        results: dict[str, bool] = {}
        for provider_id, session in targets.items():
            route = self._routes[provider_id]
            previous_port = getattr(session, "bound_port", None)
            try:
                session.stop()
            except Exception:
                pass
            rebuilt = False
            for port in ([previous_port, 0] if previous_port else [0]):
                # The manager holds no key copy: restart re-opens the credential
                # through the same no-follow read contract and zeroes the
                # intermediate buffer exactly like ``start`` does.
                key_buffer = bytearray(
                    _PROVIDER_CREDENTIAL_READERS[provider_id](self._bindings[provider_id])
                )
                try:
                    candidate = self._session_factory(
                        key_buffer,
                        provider_id=provider_id,
                        upstream_url=route.upstream_url,
                        port=port,
                        on_failure=self._on_failure,
                        **({"on_attempt": self._on_attempt} if self._on_attempt else {}),
                    )
                    candidate.start()
                except Exception:
                    rebuilt = False
                    continue
                finally:
                    for index in range(len(key_buffer)):
                        key_buffer[index] = 0
                rebuilt = True
                break
            with self._lock:
                if rebuilt:
                    self._sessions[provider_id] = candidate
                else:
                    self._sessions.pop(provider_id, None)
            results[provider_id] = rebuilt
        return results


__all__ = [
    "CODEX_AUTH_CACHE_NAME",
    "CODEX_AUTH_MODE",
    "CODEX_HOME_ENV",
    "CODEX_PROVIDER_ID",
    "CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH",
    "CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE",
    "CODEX_TOML_PROVIDER_ID",
    "DEFAULT_MODEL_PROFILE_ID",
    "DEEPSEEK_DIRECT_ROUTE",
    "DELIVERY_MODEL_PROFILE_PACKAGE_ID",
    "GLM_DIRECT_ROUTE",
    "MODEL_PROFILE_DIRECTORY",
    "MODEL_PROFILE_ALLOWED_ROLE_UNIVERSE",
    "MODEL_PROFILE_OPTIONAL_PACKAGE_IDS",
    "MODEL_PROFILE_PACKAGE_IDS",
    "MODEL_PROFILE_ROLE_UNIVERSE",
    "MODEL_PROFILE_SCHEMA_VERSION",
    "OPENAI_CODEX_ROUTE",
    "PROVIDER_CATALOG",
    "REQUESTED_EFFORT_TIERS",
    "CodexSubscriptionAuthError",
    "ProviderCredentialUnavailableError",
    "ProviderSessionManager",
    "ProviderSessionManagerError",
    "RoleModelBinding",
    "TeamModelProfile",
    "TeamModelProfileError",
    "codex_auth_cache_path",
    "load_team_model_profile",
    "resolve_delivery_model_binding",
    "preflight_codex_subscription_auth",
    "preflight_profile_credentials",
    "profile_requires_codex_subscription_auth",
    "uses_external_credential_session",
]
