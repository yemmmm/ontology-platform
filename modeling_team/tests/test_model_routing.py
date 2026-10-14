"""R2.3-007 deterministic focused tests: Groups A-F of the shared test plan.

Group G (real provider probes) and the final H gates belong to the independent
tester; every test here uses repository fixtures, fake upstreams, or session
doubles only.
"""

from __future__ import annotations

from modeling_team.handoff_materials import HANDOFF_TOOL_NAMES

import hashlib
import http.client
import io
import json
import subprocess
import threading
import time
import tomllib
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

import modeling_team.model_routing as model_routing_module
import modeling_team.runner as runner_module
import modeling_team.runtimes.codex as codex_module
from modeling_team.contracts import (
    TeamConfigurationError,
    _load_package,
    repository_root,
)
from modeling_team.deepseek_provider_proxy import (
    RESPONSES_UPSTREAM_FAILURE,
    ResponsesProviderSession,
)
from modeling_team.model_routing import (
    CODEX_AUTH_MODE,
    CODEX_HOME_ENV,
    CODEX_PROVIDER_ID,
    CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH,
    CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
    DEFAULT_MODEL_PROFILE_ID,
    DEEPSEEK_DIRECT_ROUTE,
    DELIVERY_MODEL_PROFILE_PACKAGE_ID,
    GLM_DIRECT_ROUTE,
    MODEL_PROFILE_PACKAGE_IDS,
    MODEL_PROFILE_ROLE_UNIVERSE,
    OPENAI_CODEX_ROUTE,
    PROVIDER_CATALOG,
    REQUESTED_EFFORT_TIERS,
    CodexSubscriptionAuthError,
    ProviderCredentialUnavailableError,
    ProviderSessionManager,
    ProviderSessionManagerError,
    TeamModelProfile,
    load_team_model_profile,
    preflight_codex_subscription_auth,
    preflight_profile_credentials,
    profile_requires_codex_subscription_auth,
    resolve_delivery_model_binding,
    uses_external_credential_session,
)
from modeling_team.runner import TeamRunner
from modeling_team.runtimes.codex import CodexRuntimeAdapter, CodexRuntimeError, _Agent


ROOT = repository_root()

_MIXED_ROLES: dict[str, dict[str, str]] = {
    "coordinator": {
        "model_provider": "deepseek-direct",
        "model": "deepseek-v4-flash",
        "model_reasoning_effort": "low",
    },
    "modeling": {
        "model_provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "model_reasoning_effort": "medium",
    },
    "protocol": {
        "model_provider": "deepseek-direct",
        "model": "deepseek-v4-flash",
        "model_reasoning_effort": "high",
    },
    "acceptance": {
        "model_provider": "deepseek-direct",
        "model": "deepseek-v4-flash",
        "model_reasoning_effort": "xhigh",
    },
    "source-examiner": {
        "model_provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "model_reasoning_effort": "none",
    },
    "platform-examiner": {
        "model_provider": "deepseek-direct",
        "model": "deepseek-v4-flash",
        "model_reasoning_effort": "max",
    },
}

_MIXED_EFFECTIVE = {
    "coordinator": "high",
    "modeling": "medium",
    "protocol": "high",
    "acceptance": "max",
    "source-examiner": "none",
    "platform-examiner": "max",
}


def _write_profile(root: Path, profile_id: str, roles: dict[str, dict[str, str]]) -> Path:
    directory = root / "modeling_team" / "model-profiles"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{profile_id}.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "model_profile_id": profile_id,
                "roles": roles,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _mixed_profile(root: Path) -> TeamModelProfile:
    _write_profile(root, "mixed-routing-fixture", _MIXED_ROLES)
    return load_team_model_profile(root, "mixed-routing-fixture")


def _credential_file(root: Path, name: str, assignment: str) -> Path:
    path = root / name
    path.write_text(assignment, encoding="utf-8")
    path.chmod(0o600)
    return path


class _SessionsDouble:
    """ProviderSessionManager double with per-provider loopback URLs."""

    def __init__(self, base_urls: dict[str, str] | None = None) -> None:
        self._base_urls = base_urls or {
            "deepseek-direct": "http://127.0.0.1:49001",
        }

    def base_url_for(self, provider_id: str) -> str:
        return self._base_urls[provider_id]

    def listening(self) -> bool:
        return True

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {provider_id: {"listening": True} for provider_id in self._base_urls}

    def secret_values(self) -> tuple[bytes, ...]:
        return ()

    def stop(self) -> dict[str, dict[str, bool | int]]:
        return {}


class _NotListeningSessions(_SessionsDouble):
    def listening(self) -> bool:
        return False


def _formal_run(root: Path) -> SimpleNamespace:
    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        (root / "sources" / role).mkdir(parents=True)
    return SimpleNamespace(
        root=root,
        run_id="r23007-run",
        protocol_key="platform-key",
        configuration=SimpleNamespace(
            task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
            profile=SimpleNamespace(profile_id="r2-3-005-modeling-team"),
        ),
        acceptance=None,
        scope={"mode": "create"},
    )


def _agent(root: Path, role: str) -> _Agent:
    home, work, skills = (root / f"{role}-home", root / f"{role}-work", root / f"{role}-skills")
    for path in (home, work, skills):
        path.mkdir(parents=True)
        path.chmod(0o700)
    return _Agent(role, _load_package(ROOT, role), home, work, skills)


# --------------------------------------------------------------------------
# Group A: profile loader and capability
# --------------------------------------------------------------------------


def test_openai_profile_binds_all_six_roles_to_luna_medium() -> None:
    first = load_team_model_profile(ROOT, "openai-luna-medium")
    second = load_team_model_profile(ROOT, "openai-luna-medium")
    assert first == second
    assert first.relative_path == "modeling_team/model-profiles/openai-luna-medium.yaml"
    for package_id in MODEL_PROFILE_PACKAGE_IDS:
        binding = first.binding_for(package_id)
        assert binding.provider_id == "openai-codex"
        assert binding.model == "gpt-5.6-luna"
        assert binding.requested_effort == "medium"
        assert binding.effective_effort == "medium"
    assert profile_requires_codex_subscription_auth(first) is True
    assert not any(
        uses_external_credential_session(provider_id)
        for provider_id in first.provider_ids()
    )


def test_openai_sol_profile_binds_every_role_to_requested_model_and_effort() -> None:
    profile = load_team_model_profile(ROOT, "openai-sol-medium")
    assert set(profile.bindings) == set(MODEL_PROFILE_ROLE_UNIVERSE)
    for binding in profile.bindings.values():
        assert binding.provider_id == "openai-codex"
        assert binding.model == "gpt-6.1-sol"
        assert binding.requested_effort == binding.effective_effort == "medium"
    assert profile_requires_codex_subscription_auth(profile) is True
    assert profile.provider_ids() == ("openai-codex",)


def test_openai_6_luna_profile_binds_every_role_without_model_substitution() -> None:
    profile = load_team_model_profile(ROOT, "openai-6-luna-medium")
    assert set(profile.bindings) == set(MODEL_PROFILE_ROLE_UNIVERSE) | {
        DELIVERY_MODEL_PROFILE_PACKAGE_ID
    }
    for binding in profile.bindings.values():
        assert binding.provider_id == "openai-codex"
        assert binding.model == "gpt-6-luna"
        assert binding.requested_effort == binding.effective_effort == "medium"
    assert profile_requires_codex_subscription_auth(profile) is True
    assert profile.provider_ids() == ("openai-codex",)
    delivery, source = resolve_delivery_model_binding(profile)
    assert source == "delivery"
    assert delivery.model == "gpt-6-luna"
    assert delivery.requested_effort == delivery.effective_effort == "medium"


def test_catalog_effort_capability_mapping_is_closed() -> None:
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("low") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("medium") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("high") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("xhigh") == "max"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("max") == "max"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("none") is None
    for tier in REQUESTED_EFFORT_TIERS:
        assert OPENAI_CODEX_ROUTE.effective_effort(tier) == tier
    assert set(PROVIDER_CATALOG) == {"deepseek-direct", "glm-direct", "openai-codex"}
    assert PROVIDER_CATALOG["deepseek-direct"].upstream_url == (
        "https://api.deepseek.com/responses"
    )
    assert PROVIDER_CATALOG["deepseek-direct"].credential_env == "DEEPSEEK_API_KEY"
    # ``glm-direct`` mirrors ``deepseek-direct``: both the upstream URL and the
    # credential env var must be set.  ``uses_external_credential`` is an AND, so
    # a route that set only one of them would silently project the Codex ChatGPT
    # subscription instead of the loopback provider session.
    assert GLM_DIRECT_ROUTE.upstream_url == "https://open.bigmodel.cn/api/v1/responses"
    assert GLM_DIRECT_ROUTE.credential_env == "GLM_API_KEY"
    assert GLM_DIRECT_ROUTE.wire_api == "responses"
    assert GLM_DIRECT_ROUTE.models == frozenset(
        {"glm-5.3", "glm-5.3-flash", "glm-5.3-flashx"}
    )
    assert GLM_DIRECT_ROUTE.uses_external_credential is True
    # ``low`` passes through verbatim (upstream-verified 2026-09-13; the
    # auth-r3-0-012 batch runs the Platform Examiner at low effort), while the
    # middle/top tiers resolve as DeepSeek's do, including ``none`` unmapped.
    assert GLM_DIRECT_ROUTE.effective_effort("low") == "low"
    assert GLM_DIRECT_ROUTE.effective_effort("medium") == "high"
    assert GLM_DIRECT_ROUTE.effective_effort("high") == "high"
    assert GLM_DIRECT_ROUTE.effective_effort("xhigh") == "max"
    assert GLM_DIRECT_ROUTE.effective_effort("max") == "max"
    assert GLM_DIRECT_ROUTE.effective_effort("none") is None
    # The Codex route is the built-in OpenAI Responses route: no upstream URL,
    # no API-key credential assignment, no ambient environment variable.
    assert OPENAI_CODEX_ROUTE.upstream_url is None
    assert OPENAI_CODEX_ROUTE.credential_env is None
    assert uses_external_credential_session("deepseek-direct") is True
    assert uses_external_credential_session("openai-codex") is False
    for route in PROVIDER_CATALOG.values():
        assert route.wire_api == "responses"


def test_mixed_profile_routes_each_role_with_capability_effort(tmp_path: Path) -> None:
    profile = _mixed_profile(tmp_path)
    assert profile.provider_ids() == ("deepseek-direct", "openai-codex")
    assert profile_requires_codex_subscription_auth(profile) is True
    assert profile_requires_codex_subscription_auth(
        load_team_model_profile(ROOT, DEFAULT_MODEL_PROFILE_ID)
    ) is False
    for package_id in MODEL_PROFILE_PACKAGE_IDS:
        binding = profile.binding_for(package_id)
        declaration = _MIXED_ROLES[package_id]
        assert binding.provider_id == declaration["model_provider"]
        assert binding.model == declaration["model"]
        assert binding.requested_effort == declaration["model_reasoning_effort"]
        assert binding.effective_effort == _MIXED_EFFECTIVE[package_id]


def test_deepseek_flash_is_in_the_closed_model_catalog() -> None:
    # R3.0-006 real validation: the official DeepSeek model list carries
    # ``deepseek-flash`` (``deepseek-v4.1-flash`` was rejected upstream with
    # HTTP 400), so the catalog must accept the user-confirmed exact model.
    assert "deepseek-flash" in DEEPSEEK_DIRECT_ROUTE.models
    assert "deepseek-v4-flash" in DEEPSEEK_DIRECT_ROUTE.models
    assert "deepseek-v4.1-flash" not in DEEPSEEK_DIRECT_ROUTE.models
    assert "deepseek-flash" not in OPENAI_CODEX_ROUTE.models


def test_glm_full_model_is_in_the_closed_model_catalog() -> None:
    # 2026-09-12 model-comparison round (auth-r3-0-006-010): the user named
    # ``glm-5.3`` (the full model, not the flash variant) as a candidate team
    # model, so the glm-direct catalog must accept that exact string the same
    # way ``deepseek-flash`` was admitted after its versioned sibling was
    # rejected upstream.
    assert "glm-5.3" in GLM_DIRECT_ROUTE.models
    assert "glm-5.3-flash" in GLM_DIRECT_ROUTE.models
    assert "glm-5.3" not in DEEPSEEK_DIRECT_ROUTE.models
    assert "glm-5.3" not in OPENAI_CODEX_ROUTE.models


def test_deepseek_flash_max_profile_binds_every_v3_role_to_deepseek() -> None:
    # The v3 multi-slice run binds the roster plus both CQ acceptance
    # children; every one of them must be pinned to the DeepSeek direct
    # route with the user-confirmed model, with no Codex subscription
    # route anywhere in the profile.
    profile = load_team_model_profile(ROOT, "deepseek-flash-max")
    assert set(profile.bindings) == {
        "coordinator",
        "modeling",
        "protocol",
        "competency-question",
        "platform-examiner",
        "acceptance",
    }
    for binding in profile.bindings.values():
        assert binding.provider_id == "deepseek-direct"
        assert binding.model == "deepseek-flash"
        assert binding.requested_effort == "max"
        assert binding.effective_effort == "max"
    assert profile.provider_ids() == ("deepseek-direct",)
    assert profile_requires_codex_subscription_auth(profile) is False
    assert uses_external_credential_session("deepseek-direct") is True


def test_profile_accepts_a_declared_subset_of_the_role_universe(
    tmp_path: Path,
) -> None:
    # Profiles declare non-empty subsets of the closed universe; only the
    # formal-contract and roster-coverage checks may demand specific roles.
    roles = {
        package_id: {
            "model_provider": "deepseek-direct",
            "model": "deepseek-flash",
            "model_reasoning_effort": "max",
        }
        for package_id in ("modeling", "competency-question")
    }
    _write_profile(tmp_path, "subset-fixture", roles)
    profile = load_team_model_profile(tmp_path, "subset-fixture")
    assert set(profile.bindings) == {"modeling", "competency-question"}


def test_profile_rejects_null_and_unknown_role_declarations(tmp_path: Path) -> None:
    _write_profile(tmp_path, "null-role-fixture", dict(_MIXED_ROLES))
    directory = tmp_path / "modeling_team" / "model-profiles"
    path = directory / "null-role-fixture.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    # An explicit ``role: null`` is a malformed declaration, not an
    # undeclared role: it must fail validation like any other bad binding.
    value["roles"]["coordinator"] = None
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="declaration for coordinator"):
        load_team_model_profile(tmp_path, "null-role-fixture")

    value["roles"]["coordinator"] = dict(_MIXED_ROLES["coordinator"])
    value["roles"]["unknown-role"] = dict(_MIXED_ROLES["coordinator"])
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="role bindings drift"):
        load_team_model_profile(tmp_path, "null-role-fixture")


@pytest.mark.parametrize(
    "profile_id",
    ["../escape", "/absolute/path.yaml", "https://provider.example/profile", ""],
)
def test_profile_id_is_restricted_and_paths_are_rejected(profile_id: str) -> None:
    with pytest.raises(TeamConfigurationError):
        load_team_model_profile(ROOT, profile_id)


def test_profile_rejects_symlink_duplicate_keys_and_identity_drift(tmp_path: Path) -> None:
    real = _write_profile(tmp_path, "symlinked-profile", dict(_MIXED_ROLES))
    link = tmp_path / "modeling_team" / "model-profiles" / "linked-profile.yaml"
    link.symlink_to(real)
    with pytest.raises(TeamConfigurationError, match="symlink"):
        load_team_model_profile(tmp_path, "linked-profile")

    directory = tmp_path / "modeling_team" / "model-profiles"
    duplicate = directory / "duplicate-profile.yaml"
    duplicate.write_text(
        "schema_version: 1\n"
        'model_profile_id: "duplicate-profile"\n'
        "roles:\n"
        "  coordinator:\n"
        '    model_provider: "deepseek-direct"\n'
        '    model: "deepseek-v4-flash"\n'
        '    model_reasoning_effort: "low"\n'
        "  coordinator:\n"
        '    model_provider: "openai-codex"\n'
        '    model: "gpt-5.6-luna"\n'
        '    model_reasoning_effort: "low"\n',
        encoding="utf-8",
    )
    with pytest.raises(TeamConfigurationError, match="duplicate"):
        load_team_model_profile(tmp_path, "duplicate-profile")

    drifted = directory / "drifted-profile.yaml"
    payload = yaml.safe_load(real.read_text(encoding="utf-8"))
    payload["model_profile_id"] = "other-profile"
    drifted.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError, match="identifier drifts"):
        load_team_model_profile(tmp_path, "drifted-profile")


@pytest.mark.parametrize(
    "edit",
    [
        lambda roles: roles["coordinator"].update(model=""),
        lambda roles: roles["coordinator"].update(model_reasoning_effort="ultra"),
        lambda roles: roles["coordinator"].update(model="gpt-5.6-luna"),
        lambda roles: roles["coordinator"].update(schema_version=2),
        lambda roles: roles["coordinator"].update(extra_field=True),
        lambda roles: roles["protocol"].update(model_reasoning_effort="none"),
        lambda roles: roles["protocol"].pop("model_reasoning_effort"),
    ],
)
def test_profile_rejects_unsupported_values_before_side_effects(
    tmp_path: Path, edit
) -> None:
    _mixed_profile(tmp_path)
    path = tmp_path / "modeling_team" / "model-profiles" / "mixed-routing-fixture.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(value["roles"])
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    with pytest.raises(TeamConfigurationError):
        load_team_model_profile(tmp_path, "mixed-routing-fixture")
    assert runner_side_effects_absent(tmp_path)


def runner_side_effects_absent(root: Path) -> bool:
    return not (root / "workspaces").exists()


def test_runner_freezes_profile_across_external_preflight(
    monkeypatch, tmp_path: Path
) -> None:
    credential = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=drift-check-sentinel\n"
    )
    real_loader = runner_module.load_team_model_profile
    flip = {"drift": False}

    def flipping_loader(root: Path, profile_id: str) -> TeamModelProfile:
        profile = real_loader(root, profile_id)
        if flip["drift"]:
            return replace(
                profile,
                bindings={
                    **profile.bindings,
                    "coordinator": replace(
                        profile.bindings["coordinator"],
                        requested_effort="low",
                        effective_effort="high",
                    ),
                },
            )
        return profile

    def preflight(**_kwargs: object) -> dict[str, object]:
        flip["drift"] = True
        return {}

    run_id = "r23007-drift-freeze"
    runner = TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=credential,
        freeze_started_at="2026-08-17T00:00:00+00:00",
    )
    with (
        patch("modeling_team.runner.load_team_model_profile", flipping_loader),
        patch("modeling_team.runner.run_prestart_preflight", preflight),
    ):
        with pytest.raises(TeamConfigurationError, match="drifted during preflight"):
            runner.prepare(
                run_id=run_id,
                profile_path=ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                task_path=ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                scope={"mode": "create"},
            )
    assert runner.run is None
    assert not (ROOT / "workspaces" / "modeling-runs" / run_id).exists()


def test_runner_formal_contract_requires_the_complete_six_role_profile(
    tmp_path: Path,
) -> None:
    # The exact-six requirement lives in ``TeamRunner.prepare`` since the
    # shared loader widened to declared subsets: a formal contract may only
    # ride a profile that binds the complete formal role set.
    config = SimpleNamespace(
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=()),
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
    )
    incomplete = SimpleNamespace(
        profile_id=DEFAULT_MODEL_PROFILE_ID,
        bindings={
            package_id: object()
            for package_id in MODEL_PROFILE_PACKAGE_IDS[:-1]
        },
    )
    runner = TeamRunner(repository_root=tmp_path, adapter=SimpleNamespace())
    with (
        patch(
            "modeling_team.runner.load_formal_team_configuration",
            return_value=config,
        ),
        patch(
            "modeling_team.runner.load_team_model_profile",
            return_value=incomplete,
        ),
    ):
        with pytest.raises(
            TeamConfigurationError, match="team model profile role bindings drift"
        ):
            runner.prepare(
                run_id="luna-six-role-gate",
                profile_path=tmp_path / "profile.yaml",
                task_path=tmp_path / "task.yaml",
                scope={"mode": "create"},
            )
    assert runner.run is None
    assert not (tmp_path / "workspaces").exists()


# --------------------------------------------------------------------------
# Group B: CLI and baseline
# --------------------------------------------------------------------------


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    from modeling_team import __main__ as team_main

    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(team_main.sys, "argv", argv):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = team_main.main()
    return code, stdout.getvalue(), stderr.getvalue()


def _cli_configuration() -> SimpleNamespace:
    return SimpleNamespace(
        profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=()),
        task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
    )


def _validate_cli(monkeypatch, model_profile: str | None) -> tuple[int, dict, str]:
    from modeling_team import __main__ as team_main

    monkeypatch.setattr(team_main, "repository_root", lambda: ROOT)
    monkeypatch.setattr(
        team_main, "load_formal_team_configuration", lambda *_a, **_k: _cli_configuration()
    )
    argv = [
        "modeling-team",
        "validate",
        "--profile",
        str(ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml"),
        "--task",
        str(ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"),
    ]
    if model_profile is not None:
        argv += ["--model-profile", model_profile]
    code, stdout, stderr = _run_cli(argv)
    return code, json.loads(stdout) if stdout else {}, stderr


def test_cli_validate_accepts_model_profile_and_defaults_to_contract(
    monkeypatch,
) -> None:
    code, payload, _stderr = _validate_cli(monkeypatch, "openai-luna-medium")
    assert code == 0
    projection = payload["model_profile"]
    assert projection["profile_id"] == "openai-luna-medium"
    assert projection == load_team_model_profile(ROOT, "openai-luna-medium").as_dict()

    code, payload, _stderr = _validate_cli(monkeypatch, None)
    assert code == 0
    assert payload["model_profile"]["profile_id"] == DEFAULT_MODEL_PROFILE_ID
    assert payload["model_profile"] == load_team_model_profile(
        ROOT, DEFAULT_MODEL_PROFILE_ID
    ).as_dict()

    from modeling_team.formal_runs import FORMAL_RUN_CONTRACTS

    # The closed registry keeps the exact requirement-owned defaults: R2.3-008
    # and its R2.3-009 gate-relaxation successor are the Luna subscription
    # carriers; every other formal contract still defaults to the DeepSeek
    # profile.
    assert {
        contract.requirement_id: contract.default_model_profile_id
        for contract in FORMAL_RUN_CONTRACTS
    } == {
        "R2.3-005": DEFAULT_MODEL_PROFILE_ID,
        "R2.3-003": DEFAULT_MODEL_PROFILE_ID,
        "R2.3-008": "openai-luna-medium",
        "R2.3-009": "openai-luna-medium",
    }


@pytest.mark.parametrize(
    ("model_profile", "pattern"),
    [
        ("../secrets", "model profile ID is invalid"),
        ("/tmp/profile.yaml", "model profile ID is invalid"),
        ("missing-profile", "unavailable"),
    ],
)
def test_cli_rejects_non_id_profile_values(
    monkeypatch, model_profile: str, pattern: str
) -> None:
    code, _payload, stderr = _validate_cli(monkeypatch, model_profile)
    assert code == 2
    assert pattern in stderr


def test_cli_non_formal_fixture_is_never_promoted(monkeypatch) -> None:
    from modeling_team import __main__ as team_main

    monkeypatch.setattr(team_main, "repository_root", lambda: ROOT)
    monkeypatch.setattr(
        team_main,
        "load_formal_team_configuration",
        lambda *_a, **_k: SimpleNamespace(
            profile=SimpleNamespace(profile_id="legacy-fixture"),
            task=SimpleNamespace(schema_version=1, task_id="legacy-task"),
        ),
    )
    argv = [
        "modeling-team",
        "validate",
        "--profile",
        "profile.yaml",
        "--task",
        "task.yaml",
        "--model-profile",
        DEFAULT_MODEL_PROFILE_ID,
    ]
    code, _stdout, stderr = _run_cli(argv)
    assert code == 2
    assert "requires a formal run contract" in stderr

    from modeling_team.__main__ import _resolve_model_profile_selection

    assert (
        _resolve_model_profile_selection(None, None) is None
    )
    with pytest.raises(TeamConfigurationError):
        _resolve_model_profile_selection("openai-luna-medium", None)


def test_run_subcommand_accepts_model_profile_and_passes_selection_to_prepare(
    monkeypatch, tmp_path: Path
) -> None:
    from modeling_team import __main__ as team_main

    captured: dict[str, object] = {}

    class Adapter:
        pass

    class Runner:
        def __init__(self, **kwargs):
            self.run = None
            self.scope_factory = kwargs.get("scope_factory")

        def prepare(self, **kwargs) -> None:
            captured.update(kwargs)
            self.run = SimpleNamespace(root=tmp_path / "run")

        def start(self) -> None:
            raise TeamConfigurationError("stop after prepare")

        def cleanup(self) -> None:
            return None

    scope = tmp_path / "scope.yaml"
    scope.write_text("mode: create\n", encoding="utf-8")
    monkeypatch.setattr(team_main, "repository_root", lambda: ROOT)
    monkeypatch.setattr(
        team_main, "load_formal_team_configuration", lambda *_a, **_k: _cli_configuration()
    )
    monkeypatch.setattr(team_main, "CodexRuntimeAdapter", lambda **_k: Adapter())
    monkeypatch.setattr(team_main, "TeamRunner", lambda **_k: Runner())
    code, _stdout, stderr = _run_cli(
        [
            "modeling-team",
            "run",
            "--profile",
            str(ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml"),
            "--task",
            str(ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml"),
            "--run-id",
            "r23007-cli-run-projection",
            "--scope",
            str(scope),
            "--model-profile",
            "openai-luna-medium",
        ]
    )
    assert code == 2, stderr
    assert captured["model_profile_id"] == "openai-luna-medium"


def test_baseline_projects_safe_profile_binding_without_provider_text() -> None:
    manifest, _baseline_hash = TeamRunner.preview_baseline(
        repository_root=ROOT,
        run_id="r23007-baseline-check",
        profile_path=ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
        task_path=ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
        model_profile_id="openai-luna-medium",
    )
    projection = manifest["team_model_profile"]
    assert projection == load_team_model_profile(ROOT, "openai-luna-medium").as_dict()
    assert set(projection) == {"profile_id", "path", "sha256", "roles"}
    for package_id in MODEL_PROFILE_PACKAGE_IDS:
        role = projection["roles"][package_id]
        assert role["model_provider"] == "openai-codex"
        assert role["auth_mode"] == "chatgpt-subscription"
        assert set(role) == {
            "model_provider",
            "model",
            "requested_effort",
            "effective_effort",
            "auth_mode",
        }
    serialized = json.dumps(manifest)
    assert "api.openai.com" not in serialized
    assert "api.deepseek.com" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized
    # The profile projection carries no auth cache path or digest hints.
    projection_serialized = json.dumps(projection)
    assert ".codex" not in projection_serialized
    assert "auth.json" not in projection_serialized
    assert "codex login" not in projection_serialized


# --------------------------------------------------------------------------
# Group C: Responses session behavior
# --------------------------------------------------------------------------


class _JSONUpstream(BaseHTTPRequestHandler):
    status = 200
    body = b"{}"

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *_args: object) -> None:
        return


@pytest.fixture()
def json_upstream():
    server = HTTPServer(("127.0.0.1", 0), _JSONUpstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def _loopback_client(session: ResponsesProviderSession) -> http.client.HTTPConnection:
    return http.client.HTTPConnection(
        "127.0.0.1", int(session.base_url.rsplit(":", 1)[1])
    )


def test_session_listens_only_on_loopback_and_rejects_non_responses_surfaces(
    json_upstream,
) -> None:
    failures: list[str] = []
    session = ResponsesProviderSession(
        b"loopback-sentinel",
        upstream_url=f"http://127.0.0.1:{json_upstream.server_port}/responses",
        on_failure=failures.append,
    )
    session.start()
    try:
        assert session.base_url.startswith("http://127.0.0.1:")
        connection = _loopback_client(session)
        connection.request(
            "POST", "/responses", body=b"{}", headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b"{}"
        connection.close()

        connection = _loopback_client(session)
        connection.request(
            "POST", "/other", body=b"{}", headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 404
        response.read()
        connection.close()

        connection = _loopback_client(session)
        connection.request(
            "POST",
            "/responses",
            body=b"{}",
            headers={"Content-Type": "text/plain"},
        )
        response = connection.getresponse()
        assert response.status == 415
        response.read()
        connection.close()

        connection = _loopback_client(session)
        connection.request("GET", "/responses")
        response = connection.getresponse()
        assert response.status == 501
        response.read()
        connection.close()

        snapshot = session.snapshot()
        assert snapshot["requests"] == 1
        # GET is refused by the stdlib base class (501) without reaching the
        # Responses rejection accounting; only the local 404/415 paths count.
        assert snapshot["rejected"] == 2
        assert snapshot["upstream_errors"] == 0
        assert failures == []
    finally:
        session.stop()


def test_non_2xx_upstream_status_is_preserved_with_body_dropped(
    json_upstream,
) -> None:
    sentinel = b"provider-controlled-boom-text-418"
    _JSONUpstream.status = 500
    _JSONUpstream.body = sentinel
    failures: list[str] = []
    session = ResponsesProviderSession(
        b"non-2xx-sentinel",
        upstream_url=f"http://127.0.0.1:{json_upstream.server_port}/responses",
        on_failure=failures.append,
        # Historical fail-fast semantics: one non-2xx signals immediately.
        # 2026-09-17 abort-park fix: the default fuse now retries transient
        # statuses inside one request, so this boundary pins the single-attempt
        # opt-out instead of the default budget.
        upstream_failure_threshold=1,
        max_upstream_attempts=1,
    )
    session.start()
    try:
        connection = _loopback_client(session)
        connection.request(
            "POST", "/responses", body=b"{}", headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 500
        body = response.read()
        assert body == b""
        connection.close()
        assert failures == [RESPONSES_UPSTREAM_FAILURE]
        snapshot = session.snapshot()
        assert snapshot["upstream_errors"] == 1
        assert snapshot["upstream_status_5xx"] == 1
        assert sentinel.decode() not in json.dumps(snapshot)
        assert sentinel.decode() not in repr(session.stop_snapshot())
    finally:
        _JSONUpstream.status = 200
        _JSONUpstream.body = b"{}"
        session.stop()


class _PartialStreamUpstream(BaseHTTPRequestHandler):
    # The newline terminator lets the proxy's line iteration yield this chunk
    # before the framing breaks; the bytes already sent stay client-visible.
    chunk = b"transparent-model-chunk\n"

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Deliver one complete chunk, then start a next chunk-size line and
        # close the socket mid-framing: a 2xx stream that breaks before any
        # terminal state without ending cleanly at a chunk boundary.
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self.wfile.write(f"{len(self.chunk):x}\r\n".encode() + self.chunk + b"\r\n")
        self.wfile.write(b"8")
        self.wfile.flush()
        self.connection.close()

    def log_message(self, *_args: object) -> None:
        return


def test_partial_2xx_stream_keeps_sent_output_transparent_and_signals_failure() -> None:
    server = HTTPServer(("127.0.0.1", 0), _PartialStreamUpstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    failures: list[str] = []
    session = ResponsesProviderSession(
        b"partial-stream-sentinel",
        upstream_url=f"http://127.0.0.1:{server.server_port}/responses",
        on_failure=failures.append,
        # Historical fail-fast semantics: one broken 2xx stream signals.
        upstream_failure_threshold=1,
    )
    session.start()
    try:
        connection = _loopback_client(session)
        connection.request(
            "POST", "/responses", body=b"{}", headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.read(len(_PartialStreamUpstream.chunk)) == (
            _PartialStreamUpstream.chunk
        )
        connection.close()
        # The proxy signals the fixed upstream failure only after its next
        # line read observes the truncated chunked stream; wait for the latch
        # instead of racing the session's handler thread.
        deadline = time.monotonic() + 5.0
        while not failures and time.monotonic() < deadline:
            time.sleep(0.02)
        assert failures == [RESPONSES_UPSTREAM_FAILURE]
        assert session.snapshot()["upstream_errors"] == 1
    finally:
        session.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


# --------------------------------------------------------------------------
# Group A2: Host ChatGPT subscription preflight (amendment: Codex routing)
# --------------------------------------------------------------------------


def _codex_home_fixture(tmp_path: Path, *, mode: int = 0o600) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir(mode=0o700, parents=True)
    auth = home / "auth.json"
    # Fixture bytes only; the real cache content is never read by production.
    auth.write_text("{}", encoding="utf-8")
    auth.chmod(mode)
    return home


def test_subscription_preflight_accepts_owner_private_chatgpt_login(
    tmp_path: Path,
) -> None:
    home = _codex_home_fixture(tmp_path)
    assert (
        preflight_codex_subscription_auth(
            codex_home=home,
            login_status=lambda _home: (0, "Logged in using ChatGPT\n"),
        )
        == "chatgpt-subscription"
    )


def test_subscription_preflight_respects_codex_home_env(
    monkeypatch, tmp_path: Path
) -> None:
    home = _codex_home_fixture(tmp_path / "env-home")
    monkeypatch.setenv(CODEX_HOME_ENV, str(home))
    seen: list[Path] = []

    def login_status(resolved_home: Path) -> tuple[int, str]:
        seen.append(resolved_home)
        return 0, "Logged in using ChatGPT"

    assert preflight_codex_subscription_auth(login_status=login_status) == (
        "chatgpt-subscription"
    )
    assert seen == [home]


def test_subscription_preflight_reads_login_mode_written_to_stderr(
    monkeypatch, tmp_path: Path
) -> None:
    # codex-cli (e.g. 0.147.0) writes ``Logged in using ChatGPT`` to stderr
    # with rc=0 and an empty stdout; the runner must merge the streams before
    # the fixed-mode conclusion.
    home = _codex_home_fixture(tmp_path)

    class _Completed:
        # With stderr=subprocess.STDOUT the subprocess layer merges the
        # stderr text into stdout before the call returns.
        returncode = 0
        stdout = "Logged in using ChatGPT\n"
        stderr = None

    def fake_run(*_args, **_kwargs) -> _Completed:
        assert _kwargs.get("stderr") == subprocess.STDOUT
        return _Completed()

    monkeypatch.setattr(model_routing_module.subprocess, "run", fake_run)
    assert preflight_codex_subscription_auth(codex_home=home) == (
        "chatgpt-subscription"
    )


def test_subscription_preflight_api_key_hint_wins_over_chatgpt_text(
    tmp_path: Path,
) -> None:
    home = _codex_home_fixture(tmp_path)
    with pytest.raises(CodexSubscriptionAuthError) as excinfo:
        preflight_codex_subscription_auth(
            codex_home=home,
            login_status=lambda _home: (0, "auth via API key (not ChatGPT)"),
        )
    assert excinfo.value.reason_code == CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH


@pytest.mark.parametrize(
    "prepare",
    [
        # cache missing entirely
        lambda home: (home / "auth.json").unlink(),
        # group/other readable
        lambda home: (home / "auth.json").chmod(0o644),
        # symlinked cache
        lambda home: (
            (home / "auth.json").rename(home / "real.json"),
            (home / "auth.json").symlink_to(home / "real.json"),
        ),
        # cache replaced by a directory
        lambda home: (
            (home / "auth.json").unlink(),
            (home / "auth.json").mkdir(),
        ),
    ],
)
def test_subscription_preflight_missing_or_insecure_cache_fails_unavailable(
    tmp_path: Path, prepare
) -> None:
    home = _codex_home_fixture(tmp_path)
    prepare(home)
    with pytest.raises(CodexSubscriptionAuthError) as excinfo:
        preflight_codex_subscription_auth(
            codex_home=home,
            login_status=lambda _home: (0, "Logged in using ChatGPT"),
        )
    assert excinfo.value.reason_code == CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE
    assert excinfo.value.category == "runtime/infrastructure"


@pytest.mark.parametrize(
    ("returncode", "output"),
    [
        (1, "Not logged in"),
        (1, ""),
        (0, "Logged in using an OpenAI API key"),
        (0, "auth mode: ApiKey"),
        (0, ""),
    ],
)
def test_subscription_preflight_rejects_api_key_or_unresolved_login_mode(
    tmp_path: Path, returncode: int, output: str
) -> None:
    home = _codex_home_fixture(tmp_path)
    with pytest.raises(CodexSubscriptionAuthError) as excinfo:
        preflight_codex_subscription_auth(
            codex_home=home, login_status=lambda _home: (returncode, output)
        )
    assert excinfo.value.reason_code in {
        CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
        CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH,
    }
    if "api key" in output.lower() or "apikey" in output.lower():
        assert excinfo.value.reason_code == CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH
    # No raw login-status output is ever carried into the failure message.
    if output:
        assert output not in str(excinfo.value)


def test_subscription_preflight_failure_carries_no_login_status_output(
    tmp_path: Path,
) -> None:
    home = _codex_home_fixture(tmp_path)
    secret_output = "Logged in with API key sk-login-status-sentinel"
    with pytest.raises(CodexSubscriptionAuthError) as excinfo:
        preflight_codex_subscription_auth(
            codex_home=home, login_status=lambda _home: (0, secret_output)
        )
    assert excinfo.value.reason_code == CODEX_SUBSCRIPTION_AUTH_MODE_MISMATCH
    assert "sk-login-status-sentinel" not in str(excinfo.value)
    assert secret_output not in repr(excinfo.value)


def test_runner_subscription_preflight_precedes_credentials_and_reservation(
    monkeypatch, tmp_path: Path
) -> None:
    credential = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=subscription-order-sentinel\n"
    )
    calls: list[str] = []
    real_loader = runner_module.load_team_model_profile
    flip = {"drift": False}

    def flipping_loader(root: Path, profile_id: str) -> TeamModelProfile:
        profile = real_loader(root, profile_id)
        if flip["drift"]:
            return replace(
                profile,
                bindings={
                    **profile.bindings,
                    "modeling": replace(
                        profile.bindings["modeling"],
                        requested_effort="low",
                        effective_effort="low",
                    ),
                },
            )
        return profile

    def fake_subscription_preflight(**_kwargs: object) -> str:
        calls.append("codex-subscription")
        return "chatgpt-subscription"

    def fake_credential_preflight(profile, **_kwargs: object) -> dict[str, object]:
        calls.append("profile-credentials")
        return {}

    def preflight(**_kwargs: object) -> dict[str, object]:
        flip["drift"] = True
        return {}

    monkeypatch.setattr(
        runner_module, "preflight_codex_subscription_auth", fake_subscription_preflight
    )
    monkeypatch.setattr(
        runner_module, "preflight_profile_credentials", fake_credential_preflight
    )
    monkeypatch.setattr(runner_module, "run_prestart_preflight", preflight)

    run_id = "r23007-subscription-order"
    runner = TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=credential,
        freeze_started_at="2026-08-17T00:00:00+00:00",
    )
    with (
        patch("modeling_team.runner.load_team_model_profile", flipping_loader),
        pytest.raises(TeamConfigurationError, match="drifted during preflight"),
    ):
        runner.prepare(
            run_id=run_id,
            profile_path=ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            task_path=ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            scope={"mode": "create"},
            model_profile_id="openai-luna-medium",
        )
    assert calls == ["codex-subscription", "profile-credentials"]
    assert runner.run is None
    assert not (ROOT / "workspaces" / "modeling-runs" / run_id).exists()


def test_runner_subscription_preflight_failure_fails_closed_before_reservation(
    monkeypatch, tmp_path: Path
) -> None:
    credential = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=subscription-fail-sentinel\n"
    )
    monkeypatch.setattr(runner_module, "run_prestart_preflight", lambda **_k: {})
    monkeypatch.setattr(
        runner_module,
        "preflight_codex_subscription_auth",
        lambda **_kwargs: (_ for _ in ()).throw(
            CodexSubscriptionAuthError(
                CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE,
                "Codex subscription auth cache is unavailable",
            )
        ),
    )
    run_id = "r23007-subscription-unavailable"
    runner = TeamRunner(
        repository_root=ROOT,
        adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
        deepseek_credential_path=credential,
        freeze_started_at="2026-08-17T00:00:00+00:00",
    )
    with pytest.raises(CodexSubscriptionAuthError) as excinfo:
        runner.prepare(
            run_id=run_id,
            profile_path=ROOT / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            task_path=ROOT / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            scope={"mode": "create"},
            model_profile_id="openai-luna-medium",
        )
    assert excinfo.value.reason_code == CODEX_SUBSCRIPTION_AUTH_UNAVAILABLE
    assert runner.run is None
    assert not (ROOT / "workspaces" / "modeling-runs" / run_id).exists()


def test_runner_deepseek_only_profile_never_triggers_subscription_preflight(
    monkeypatch, tmp_path: Path
) -> None:
    credential = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=deepseek-only-sentinel\n"
    )
    real_loader = runner_module.load_team_model_profile
    flip = {"drift": False}

    def flipping_loader(root: Path, profile_id: str) -> TeamModelProfile:
        profile = real_loader(root, profile_id)
        if flip["drift"]:
            return replace(
                profile,
                bindings={
                    **profile.bindings,
                    "coordinator": replace(
                        profile.bindings["coordinator"],
                        requested_effort="low",
                        effective_effort="high",
                    ),
                },
            )
        return profile

    def forbidden_subscription_preflight(**_kwargs: object) -> str:
        raise AssertionError("DeepSeek-only profile must not trigger ChatGPT preflight")

    def preflight(**_kwargs: object) -> dict[str, object]:
        flip["drift"] = True
        return {}

    monkeypatch.setattr(
        runner_module,
        "preflight_codex_subscription_auth",
        forbidden_subscription_preflight,
    )
    monkeypatch.setattr(runner_module, "run_prestart_preflight", preflight)
    with patch("modeling_team.runner.load_team_model_profile", flipping_loader):
        run_id = "r23007-deepseek-only-no-chatgpt"
        runner = TeamRunner(
            repository_root=ROOT,
            adapter=SimpleNamespace(stop=lambda: None, cleanup_identifiers=lambda: {}),
            deepseek_credential_path=credential,
            freeze_started_at="2026-08-17T00:00:00+00:00",
        )
        # Reaching the post-preflight drift check proves the credential
        # preflight phase completed without consulting the Host login.
        with pytest.raises(TeamConfigurationError, match="drifted during preflight"):
            runner.prepare(
                run_id=run_id,
                profile_path=ROOT
                / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
                task_path=ROOT
                / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
                scope={"mode": "create"},
            )
        assert runner.run is None
        assert not (ROOT / "workspaces" / "modeling-runs" / run_id).exists()


# --------------------------------------------------------------------------
# Group A3: no OpenAI API-key credential surface for the Codex route
# --------------------------------------------------------------------------


def test_codex_route_reads_no_openai_credential_or_ambient_key(
    monkeypatch, tmp_path: Path
) -> None:
    # An ambient API key and a legacy credential file must have no effect: the
    # Codex built-in route never reads either surface.
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-sentinel")
    legacy = tmp_path / "modeling-team-openai.env"
    legacy.write_text("OPENAI_API_KEY=sk-legacy-sentinel\n", encoding="utf-8")
    legacy.chmod(0o600)
    luna = load_team_model_profile(ROOT, "openai-luna-medium")
    assert profile_requires_codex_subscription_auth(luna) is True
    assert preflight_profile_credentials(luna) == {}
    monkeypatch.chdir(tmp_path)
    assert preflight_profile_credentials(luna) == {}


def test_deepseek_default_credential_path_is_unchanged(
    monkeypatch, tmp_path: Path
) -> None:
    deepseek = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=mixed-deepseek-sentinel\n"
    )
    deepseek_only = load_team_model_profile(ROOT, DEFAULT_MODEL_PROFILE_ID)
    bindings = preflight_profile_credentials(
        deepseek_only, deepseek_credential_path=deepseek
    )
    assert set(bindings) == {"deepseek-direct"}

    mixed = _mixed_profile(tmp_path)
    mixed_bindings = preflight_profile_credentials(
        mixed, deepseek_credential_path=deepseek
    )
    assert set(mixed_bindings) == {"deepseek-direct"}

    calls: list[str] = []
    real_preflights = dict(model_routing_module._PROVIDER_CREDENTIAL_PREFLIGHTS)

    def spy(provider_id: str):
        def wrapper(path):
            calls.append(provider_id)
            return real_preflights[provider_id](path)

        return wrapper

    monkeypatch.setattr(
        model_routing_module,
        "_PROVIDER_CREDENTIAL_PREFLIGHTS",
        MappingProxyType(
            {key: spy(key) for key in real_preflights},
        ),
    )
    preflight_profile_credentials(mixed, deepseek_credential_path=deepseek)
    assert calls == ["deepseek-direct"]

    with pytest.raises(ProviderCredentialUnavailableError) as excinfo:
        preflight_profile_credentials(
            mixed, deepseek_credential_path=tmp_path / "absent.env"
        )
    assert excinfo.value.reason_code == "provider-credential-unavailable"
    assert excinfo.value.category == "runtime/infrastructure"
    assert excinfo.value.args[0] == (
        "provider credential preflight failed for deepseek-direct"
    )


# --------------------------------------------------------------------------
# Group A4: glm-direct is a first-class external credential route
# --------------------------------------------------------------------------


_GLM_ONLY_ROLES = {
    role: {
        "model_provider": "glm-direct",
        "model": "glm-5.3-flash",
        "model_reasoning_effort": "max",
    }
    for role in MODEL_PROFILE_PACKAGE_IDS
}


def _glm_only_profile(root: Path) -> TeamModelProfile:
    _write_profile(root, "glm-only-fixture", _GLM_ONLY_ROLES)
    return load_team_model_profile(root, "glm-only-fixture")


def test_external_catalog_routes_are_fully_registered() -> None:
    """Every external route must carry a preflight, a reader, and both fields.

    ``ProviderRoute.uses_external_credential`` is an AND over ``upstream_url`` and
    ``credential_env``.  A route declaring only one of them is not an external
    route at all: it is skipped by ``preflight_profile_credentials`` and every
    role bound to it silently projects the Codex built-in ChatGPT subscription.
    ``model_routing`` asserts this at import time; this test keeps the wiring
    observable and pins ``glm-direct`` into the external set.
    """

    external = {
        provider_id
        for provider_id, route in PROVIDER_CATALOG.items()
        if route.uses_external_credential
    }
    assert external == {"deepseek-direct", "glm-direct"}
    assert external == set(model_routing_module._PROVIDER_CREDENTIAL_PREFLIGHTS)
    assert external == set(model_routing_module._PROVIDER_CREDENTIAL_READERS)
    for provider_id in external:
        route = PROVIDER_CATALOG[provider_id]
        assert route.upstream_url is not None
        assert route.credential_env is not None


def test_glm_only_profile_preflights_exactly_its_own_route(tmp_path: Path) -> None:
    glm = _credential_file(tmp_path, "glm.env", "GLM_API_KEY=glm-route-sentinel\n")
    profile = _glm_only_profile(tmp_path)

    assert profile.provider_ids() == ("glm-direct",)
    assert uses_external_credential_session("glm-direct") is True
    # Nothing declares the built-in route, so nothing needs subscription auth.
    assert profile_requires_codex_subscription_auth(profile) is False

    bindings = preflight_profile_credentials(profile, glm_credential_path=glm)
    # An empty mapping here would mean the roles had fallen through to the
    # built-in provider rather than the loopback GLM session.
    assert set(bindings) == {"glm-direct"}


def test_glm_profile_never_borrows_the_deepseek_credential(tmp_path: Path) -> None:
    """The DeepSeek override seam must not satisfy a GLM profile."""

    deepseek = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=deepseek-sentinel\n"
    )
    profile = _glm_only_profile(tmp_path)
    # Point the GLM seam at a path that does not exist, so this asserts "the
    # DeepSeek override leaves ``glm-direct`` uncovered" rather than depending on
    # whether the host happens to have a real GLM credential at the default path.
    absent_glm = tmp_path / "absent-glm.env"
    with pytest.raises(ProviderCredentialUnavailableError) as excinfo:
        preflight_profile_credentials(
            profile,
            deepseek_credential_path=deepseek,
            glm_credential_path=absent_glm,
        )
    assert excinfo.value.reason_code == "provider-credential-unavailable"
    assert excinfo.value.category == "runtime/infrastructure"
    assert excinfo.value.args[0] == (
        "provider credential preflight failed for glm-direct"
    )


def test_glm_route_builds_one_shared_provider_session(tmp_path: Path) -> None:
    glm = _credential_file(tmp_path, "glm.env", "GLM_API_KEY=glm-session-sentinel\n")
    profile = _glm_only_profile(tmp_path)
    bindings = preflight_profile_credentials(profile, glm_credential_path=glm)
    created: list[str] = []

    def factory(key: bytes, *, provider_id: str, **_kwargs: object) -> _FakeSession:
        assert key
        created.append(provider_id)
        return _FakeSession(key, provider_id)

    manager = ProviderSessionManager(bindings, session_factory=factory)
    manager.start()
    try:
        assert manager.provider_ids() == ("glm-direct",)
        assert created == ["glm-direct"]
        assert manager.base_url_for("glm-direct").startswith("http://127.0.0.1:")
        assert manager.secret_values() == (b"glm-session-sentinel",)
    finally:
        manager.stop()


def test_glm_route_projects_the_loopback_provider_config(tmp_path: Path) -> None:
    """The per-role TOML selects the loopback session, never the built-in route."""

    profile = _glm_only_profile(tmp_path)
    binding = profile.bindings["modeling"]
    lines = codex_module._formal_provider_config_lines(
        binding, "http://127.0.0.1:49011"
    )
    parsed = tomllib.loads("\n".join(lines))

    assert parsed["model"] == "glm-5.3-flash"
    assert parsed["model_provider"] == "glm-direct"
    assert parsed["model_reasoning_effort"] == "max"
    # The loopback table carries no credential key: the Host session injects it.
    assert set(parsed["model_providers"]["glm-direct"]) == {
        "name",
        "base_url",
        "wire_api",
    }
    assert parsed["model_providers"]["glm-direct"]["wire_api"] == "responses"
    # The role's shell must not inherit the GLM key, nor any other route's.
    excluded = parsed["shell_environment_policy"]["exclude"]
    assert "GLM_API_KEY" in excluded
    assert "DEEPSEEK_API_KEY" in excluded
    assert "OPENAI_API_KEY" in excluded
    assert excluded == list(codex_module._CODEX_EXCLUDED_ENV_NAMES)


def test_repository_glm_profile_binds_every_role_to_glm() -> None:
    """The checked-in peak profile binds the whole roster to glm-direct."""

    profile = load_team_model_profile(ROOT, "glm-flash-max")
    assert profile.provider_ids() == ("glm-direct",)
    assert profile_requires_codex_subscription_auth(profile) is False
    assert set(profile.bindings) == {
        "coordinator",
        "modeling",
        "protocol",
        "competency-question",
        "platform-examiner",
        "acceptance",
    }
    for binding in profile.bindings.values():
        assert binding.provider_id == "glm-direct"
        assert binding.model == "glm-5.3-flash"
        assert binding.requested_effort == "max"
        assert binding.effective_effort == "max"


def test_repository_glm_flashx_high_profile_binds_every_role_to_flashx_high() -> None:
    """The user-authorized flashx profile pins every declared role exactly.

    2026-10-13 explicit user authorization (R4.0-019): the Team runs the
    glm-direct route on the exact model ``glm-5.3-flashx`` at ``high``.  No
    downgrade to ``glm-5.3-flash`` and no silent fallback onto another route
    or effort is permitted.
    """

    # The exact model must sit in the closed glm-direct allowlist; the
    # runtime guard in ``runtimes.codex`` revalidates bindings against the
    # same catalog, so admission here covers the child path too.
    assert "glm-5.3-flashx" in GLM_DIRECT_ROUTE.models
    profile = load_team_model_profile(ROOT, "glm-flashx-high")
    assert profile.provider_ids() == ("glm-direct",)
    # Nothing declares the built-in route, so nothing can fall back onto the
    # Codex ChatGPT subscription.
    assert profile_requires_codex_subscription_auth(profile) is False
    assert set(profile.bindings) == set(MODEL_PROFILE_PACKAGE_IDS) | {
        "competency-question",
        DELIVERY_MODEL_PROFILE_PACKAGE_ID,
    }
    for binding in profile.bindings.values():
        assert binding.provider_id == "glm-direct"
        assert binding.model == "glm-5.3-flashx"
        assert binding.requested_effort == "high"
        # The existing glm-direct mapping passes ``high`` through verbatim;
        # the profile adds no effort mapping of its own.
        assert binding.effective_effort == "high"
    # ``delivery`` is an explicit declaration, not Coordinator inheritance.
    delivery_binding, delivery_source = resolve_delivery_model_binding(profile)
    assert delivery_source == DELIVERY_MODEL_PROFILE_PACKAGE_ID
    assert delivery_binding.model == "glm-5.3-flashx"
    assert delivery_binding.effective_effort == "high"
    # The loopback child config projects the exact model, provider, and
    # effective effort onto the shared loopback session table, exactly as
    # the fresh-child TOML writer does for external-credential routes.
    binding = profile.bindings["modeling"]
    lines = codex_module._formal_provider_config_lines(
        binding, "http://127.0.0.1:49013"
    )
    parsed = tomllib.loads("\n".join(lines))
    assert parsed["model"] == "glm-5.3-flashx"
    assert parsed["model_provider"] == "glm-direct"
    assert parsed["model_reasoning_effort"] == "high"
    assert parsed["model_providers"]["glm-direct"]["base_url"] == (
        "http://127.0.0.1:49013/"
    )
    assert parsed["model_providers"]["glm-direct"]["wire_api"] == "responses"


# --------------------------------------------------------------------------
# Group E: failure, no fallback, cleanup (manager-level doubles)
# --------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, key: bytes, provider_id: str, *, fail_stop: bool = False) -> None:
        self.provider_id = provider_id
        self.key = bytearray(key)
        self.started = False
        self.stopped = False
        self.cleared = False
        self.fail_stop = fail_stop
        self.base_url = f"http://127.0.0.1:{49010 + abs(hash(provider_id)) % 100}"

    def start(self) -> str:
        self.started = True
        return self.base_url

    def snapshot(self) -> dict[str, object]:
        return {"listening": self.started}

    def secret_snapshot(self) -> bytes:
        return bytes(self.key)

    def stop(self) -> bool:
        self.stopped = True
        if self.fail_stop:
            raise RuntimeError("synthetic provider session stop failure")
        return True

    def stop_snapshot(self) -> dict[str, bool]:
        return {"lifecycle_failure": self.fail_stop}

    def clear_secret(self) -> None:
        self.cleared = True
        for index in range(len(self.key)):
            self.key[index] = 0


def _real_bindings(tmp_path: Path) -> dict[str, object]:
    deepseek = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=manager-deepseek-sentinel\n"
    )
    mixed = _mixed_profile(tmp_path)
    return preflight_profile_credentials(mixed, deepseek_credential_path=deepseek)


def test_manager_creates_one_session_per_external_provider_and_shares_it(
    tmp_path: Path,
) -> None:
    bindings = _real_bindings(tmp_path)
    # A mixed profile binds only its external credential route into a session.
    assert set(bindings) == {"deepseek-direct"}
    created: list[_FakeSession] = []

    def factory(key: bytes, *, provider_id: str, **_kwargs: object) -> _FakeSession:
        assert key
        session = _FakeSession(key, provider_id)
        created.append(session)
        return session

    manager = ProviderSessionManager(bindings, session_factory=factory)
    manager.start()
    assert [session.provider_id for session in created] == ["deepseek-direct"]
    assert manager.provider_ids() == ("deepseek-direct",)
    deepseek_url = manager.base_url_for("deepseek-direct")
    for _role in MODEL_PROFILE_PACKAGE_IDS:
        # Every role on the provider resolves to that provider's shared session.
        assert manager.base_url_for("deepseek-direct") == deepseek_url
    assert set(manager.secret_values()) == {b"manager-deepseek-sentinel"}
    reports = manager.stop()
    assert set(reports) == {"deepseek-direct"}
    assert all(session.stopped and session.cleared for session in created)
    assert all(not any(bytes(session.key)) for session in created)


def test_manager_rejects_codex_builtin_route_and_empty_bindings(tmp_path: Path) -> None:
    bindings = _real_bindings(tmp_path)
    with pytest.raises(ProviderSessionManagerError) as excinfo:
        ProviderSessionManager(
            {**bindings, CODEX_PROVIDER_ID: object()},
            session_factory=lambda *_a, **_k: None,
        )
    assert "external credential session" in str(excinfo.value)
    with pytest.raises(ProviderSessionManagerError):
        ProviderSessionManager({}, session_factory=lambda *_a, **_k: None)


def test_manager_stop_reports_independent_session_outcome(tmp_path: Path) -> None:
    bindings = _real_bindings(tmp_path)
    sessions: dict[str, _FakeSession] = {}

    def factory(key: bytes, *, provider_id: str, **_kwargs: object) -> _FakeSession:
        fail_stop = provider_id == "deepseek-direct"
        session = _FakeSession(key, provider_id, fail_stop=fail_stop)
        sessions[provider_id] = session
        return session

    manager = ProviderSessionManager(bindings, session_factory=factory)
    manager.start()
    reports = manager.stop()
    assert sessions["deepseek-direct"].stopped is True
    assert reports["deepseek-direct"]["lifecycle_failure"] is True
    assert all(session.cleared for session in sessions.values())
    assert manager.cleanup_failed(reports) is True


def test_session_upstream_failure_parks_and_only_cleanup_failure_latches(
    tmp_path: Path,
) -> None:
    # 2026-09-17 abort-park fix: an upstream session failure is no longer a
    # terminal runtime failure.  Only the lifecycle-boundary cleanup failure
    # keeps the latch, and it can never be overwritten afterwards.
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._provider_sessions = _SessionsDouble()
    adapter._on_provider_session_failure("provider-upstream-failed")
    with adapter._runtime_failure_lock:
        assert adapter._runtime_failures == []
    assert adapter._provider_session_failure_latched is False

    adapter._on_provider_session_failure("provider-session-cleanup-failed")
    with adapter._runtime_failure_lock:
        failures = list(adapter._runtime_failures)
    assert failures == [
        (
            "provider-sessions",
            {
                "category": "runtime/infrastructure",
                "reason_code": "provider-session-cleanup-failed",
            },
        )
    ]
    assert adapter._provider_session_failure_latched is True

    adapter2 = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter2._coordination_enabled = True
    adapter2._provider_sessions = _NotListeningSessions()
    adapter2.receive_messages()
    with adapter2._runtime_failure_lock:
        assert adapter2._runtime_failures == []
    # The other provider's session mapping is untouched: no role is re-routed.
    assert adapter2._provider_sessions.base_url_for("deepseek-direct").startswith(
        "http://127.0.0.1:"
    )
    adapter.stop()
    adapter2.stop()


def test_session_startup_failure_is_typed_with_zero_agent_starts(tmp_path: Path) -> None:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    run = _formal_run(tmp_path)
    run.team_model_profile = load_team_model_profile(ROOT, DEFAULT_MODEL_PROFILE_ID)
    run.provider_credential_bindings = {"deepseek-direct": object()}

    class _BrokenManager:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def start(self) -> None:
            raise RuntimeError("synthetic provider startup failure")

    with patch(
        "modeling_team.runtimes.codex.ProviderSessionManager", _BrokenManager
    ):
        with pytest.raises(CodexRuntimeError, match="provider session startup failed"):
            adapter.start_roster(run, [_agent(tmp_path, "coordinator")])
    assert adapter.agents == {}
    with adapter._runtime_failure_lock:
        assert adapter._runtime_failures == [
            (
                "provider-sessions",
                {
                    "category": "runtime/infrastructure",
                    "reason_code": "provider-session-start-failed",
                },
            )
        ]
    assert adapter._provider_sessions is None


# --------------------------------------------------------------------------
# Group D: per-role Codex projection
# --------------------------------------------------------------------------


def _formal_adapter(profile: TeamModelProfile, base_urls: dict[str, str] | None = None):
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._team_model_profile = profile
    adapter._provider_sessions = _SessionsDouble(base_urls)
    return adapter


def test_persistent_role_projection_equals_frozen_mixed_bindings(
    monkeypatch, tmp_path: Path
) -> None:
    import tomllib

    profile = _mixed_profile(tmp_path)
    adapter = _formal_adapter(profile)
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)
    run = _formal_run(tmp_path / "run")
    starts: dict[str, dict[str, object]] = {}

    adapter._require_expected_mcp_servers = lambda _agent: None  # type: ignore[method-assign]

    for role in ("coordinator", "modeling", "protocol", "acceptance"):
        agent = _agent(tmp_path, role)

        def rpc(_agent: _Agent, method: str, params: dict[str, object]) -> dict[str, object]:
            if method == "skills/list":
                return {
                    "data": [
                        {
                            "skills": [
                                {
                                    "name": path.parent.name,
                                    "path": f"/skills/{path.parent.name}/SKILL.md",
                                    "enabled": True,
                                }
                                for path in _agent.package.required_skills
                            ]
                        }
                    ]
                }
            if method == "thread/start":
                starts[_agent.agent_id] = dict(params)
                return {"thread": {"id": f"thread-{_agent.agent_id}"}}
            return {}

        adapter._rpc = rpc  # type: ignore[method-assign]
        adapter._write_config(run, agent)
        parsed = tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
        binding = profile.binding_for(role)
        assert parsed["model"] == binding.model
        assert parsed["model_reasoning_effort"] == binding.effective_effort
        if uses_external_credential_session(binding.provider_id):
            # External credential routes keep the loopback provider table.
            assert parsed["model_provider"] == binding.provider_id
            provider_table = parsed["model_providers"][binding.provider_id]
            assert set(provider_table) == {"name", "base_url", "wire_api"}
            assert provider_table["wire_api"] == "responses"
            assert provider_table["base_url"] == (
                _SessionsDouble().base_url_for(binding.provider_id) + "/"
            )
            # No private auth is ever staged for a deepseek-direct role.
            assert not (agent.home / "auth.json").exists()
            assert agent.auth_path is None
            assert agent.credential_mode == "provider_proxy"
        else:
            # ``openai-codex`` projects onto Codex's built-in provider with no
            # custom provider table and no base URL, and receives the staged
            # Host ChatGPT login cache behind the first-turn auth barrier.
            assert binding.provider_id == CODEX_PROVIDER_ID
            assert parsed["model_provider"] == "openai"
            assert "model_providers" not in parsed
            assert "base_url" not in (agent.home / "config.toml").read_text()
            assert (agent.home / "auth.json").exists()
            assert agent.auth_path == agent.home / "auth.json"
            assert agent.credential_mode == "file_auth"
            assert agent.auth_barrier_pending is True
        assert parsed["shell_environment_policy"]["exclude"] == [
            "DEEPSEEK_API_KEY",
            "GLM_API_KEY",
            "OPENAI_API_KEY",
            "LLM_API_KEY",
        ]
        adapter._initialize(agent)
        assert starts[role]["model"] == binding.model
        assert "model_provider" not in starts[role]
        assert "model_reasoning_effort" not in starts[role]
    adapter.stop()


def test_openai_only_runtime_needs_no_provider_sessions_or_bindings(
    monkeypatch, tmp_path: Path
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._team_model_profile = load_team_model_profile(ROOT, "openai-luna-medium")
    run = _formal_run(tmp_path)
    run.team_model_profile = adapter._team_model_profile
    run.provider_credential_bindings = None
    # An OpenAI-only formal run creates no loopback session manager and needs
    # no external credential bindings; roster startup proceeds normally.
    with patch("modeling_team.runtimes.codex.ProviderSessionManager") as manager:
        assert adapter.start_roster(run, []) == []
        manager.assert_not_called()
    assert adapter._provider_sessions is None

    deepseek_adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    deepseek_adapter._coordination_enabled = True
    deepseek_adapter._team_model_profile = load_team_model_profile(
        ROOT, DEFAULT_MODEL_PROFILE_ID
    )
    deepseek_run = _formal_run(tmp_path / "deepseek")
    deepseek_run.team_model_profile = deepseek_adapter._team_model_profile
    deepseek_run.provider_credential_bindings = None
    with pytest.raises(CodexRuntimeError, match="credential bindings are unavailable"):
        deepseek_adapter.start_roster(deepseek_run, [])
    adapter.stop()
    deepseek_adapter.stop()


def test_openai_role_staged_auth_exists_only_through_first_turn_barrier(
    monkeypatch, tmp_path: Path
) -> None:
    import os as os_module

    profile = _mixed_profile(tmp_path)
    adapter = _formal_adapter(profile)
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text('{"tokens": "barrier-secret-sentinel"}', encoding="utf-8")
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)
    run = _formal_run(tmp_path / "run")
    agent = _agent(tmp_path, "modeling")
    adapter._write_config(run, agent)
    staged = agent.home / "auth.json"
    assert staged.exists()
    assert agent.credential_mode == "file_auth"

    read_fd, write_fd = os_module.pipe()
    stream = os_module.fdopen(read_fd, "r", encoding="utf-8")
    agent.process = SimpleNamespace(stdin=io.StringIO(), stdout=stream)
    request_id = 77

    def server() -> None:
        ordinary = {"method": "turn/started", "params": {"turn": {"id": "turn-1"}}}
        server_request = {
            "id": request_id,
            "method": "item/tool/call",
            "params": {"tool": "mcp__unknown__tool", "arguments": {}},
        }
        os_module.write(write_fd, (json.dumps(ordinary) + "\n").encode())
        os_module.write(write_fd, (json.dumps(server_request) + "\n").encode())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if f'"id": {request_id}' in agent.process.stdin.getvalue():
                break
            time.sleep(0.01)
        os_module.write(
            write_fd,
            (json.dumps({"id": 1, "result": {"turn": {"id": "turn-1"}}}) + "\n").encode(),
        )

    thread = threading.Thread(target=server)
    thread.start()
    try:
        result = adapter._rpc(agent, "turn/start", {})
        assert result == {"turn": {"id": "turn-1"}}
    finally:
        thread.join(timeout=2)
        os_module.close(write_fd)
        stream.close()
    # The private ChatGPT login cache was removed strictly before any
    # model-selected server-request/tool dispatch.
    assert not staged.exists()
    assert agent.auth_unlinked_monotonic is not None
    assert agent.first_dispatch_monotonic is not None
    assert agent.auth_unlinked_monotonic <= agent.first_dispatch_monotonic
    adapter.stop()


def test_openai_role_staged_auth_is_removed_by_cleanup(tmp_path: Path) -> None:
    profile = _mixed_profile(tmp_path)
    adapter = _formal_adapter(profile)
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    with patch.object(adapter, "preflight_host_auth", return_value=host_auth):
        run = _formal_run(tmp_path / "run")
        agent = _agent(tmp_path, "modeling")
        adapter.agents[agent.agent_id] = agent
        adapter._write_config(run, agent)
        staged = agent.home / "auth.json"
        assert staged.exists()
        adapter.stop()
        assert not staged.exists()


def test_examiner_children_route_by_canonical_package_id(tmp_path: Path) -> None:
    profile = _mixed_profile(tmp_path)
    adapter = _formal_adapter(profile)
    for package_id in ("source-examiner", "platform-examiner"):
        package = yaml.safe_load(
            (ROOT / "modeling_team/agent-packages" / package_id / "package.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert package["role"] == "source-specialist"
    assert (
        adapter._validated_formal_role_binding("source-examiner").provider_id
        == "openai-codex"
    )
    assert (
        adapter._validated_formal_role_binding("platform-examiner").provider_id
        == "deepseek-direct"
    )
    adapter.stop()


@pytest.mark.parametrize("kind", ["source", "platform"])
def test_fresh_examiner_child_uses_own_binding_session_and_effort(
    monkeypatch, tmp_path: Path, kind: str
) -> None:
    from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS

    profile = _mixed_profile(tmp_path)
    adapter = _formal_adapter(profile)
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(adapter, "preflight_host_auth", lambda: host_auth)
    thread_starts: list[dict[str, object]] = []

    def rpc(_agent: _Agent, method: str, _params: dict[str, object]) -> dict[str, object]:
        if method == "thread/start":
            thread_starts.append(dict(_params))
            return {"thread": {"id": f"{kind}-thread"}}
        if method == "turn/start":
            return {"turn": {"id": f"{kind}-turn"}}
        if method == "mcpServerStatus/list":
            servers = [
                {"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}, *({"name": name} for name in sorted(HANDOFF_TOOL_NAMES))]}
            ]
            if kind == "platform":
                servers.append(
                    {
                        "name": "platform_read_proxy",
                        "tools": [{"name": name} for name in PLATFORM_PROXY_READ_TOOLS],
                    }
                )
            return {"data": servers}
        return {}

    adapter._rpc = rpc  # type: ignore[method-assign]
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    (private_root / "input.json").write_text("{}", encoding="utf-8")

    if kind == "source":
        # A formal Source Examiner now requires the carrier-staged approved
        # bytes (R2.3-009 start21 SOURCE_TEXT_JSON seam); stage a minimal
        # manifest-shaped tree for the formal fixtures.
        sources = private_root / "sources"
        sources.mkdir()
        (sources / "source.md").write_text("# approved source\n", encoding="utf-8")
    spec: dict[str, object] = {
        "task_id": "r2-3-005-formal-acceptance",
        "acceptance_round_id": "round-1",
        "kind": kind,
        "attempt": 0,
        "session_id": "session-1",
        "child_handle_digest": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        "ticket_digest": "c" * 64,
        "input_digest": "d" * 64,
        "private_root": str(private_root),
        "private_input": str(private_root / "input.json"),
        "descriptor": {"kind": f"{kind}_examiner", "package_digest": "e" * 64},
        "timeout_seconds": 30,
    }
    if kind == "platform":
        spec.update(
            {
                "read_key_id": "read-key",
                "read_key_digest": "f" * 64,
                "platform_read_scope": {
                    "project_id": "project",
                    "ontology_id": "ontology",

                },
                "model_state_digest": "0" * 64,
                "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
                "read_key_plaintext": "platform-secret",
                "read_key_revoke": lambda _key: None,
            }
        )
    resource = adapter.acceptance_child_factory(spec)
    config = (private_root / "home" / "config.toml").read_text(encoding="utf-8")
    binding = profile.binding_for(f"{kind}-examiner")
    assert f'model = "{binding.model}"' in config
    assert f'model_reasoning_effort = "{binding.effective_effort}"' in config
    assert len(thread_starts) == 1
    assert thread_starts[0]["model"] == binding.model
    if kind == "source":
        # ``openai-codex`` child: built-in TOML provider, no loopback table or
        # base URL, and the Host ChatGPT login cache staged into its own home
        # behind the first-turn barrier.  Route identity stays ``openai-codex``
        # in the child package runtime record with only the safe auth mode.
        assert binding.provider_id == CODEX_PROVIDER_ID
        assert binding.effective_effort == "none"
        assert 'model_provider = "openai"' in config
        assert "model_providers" not in config
        assert "base_url" not in config
        assert (private_root / "home" / "auth.json").exists()
        runtime_codex = resource._child_agent.package.runtime["codex"]
        assert runtime_codex["model_provider"] == CODEX_PROVIDER_ID
        assert runtime_codex["auth_mode"] == CODEX_AUTH_MODE
        assert resource._child_agent.credential_mode == "file_auth"
    else:
        assert binding.provider_id == "deepseek-direct"
        assert binding.effective_effort == "max"
        expected_url = _SessionsDouble().base_url_for(binding.provider_id)
        assert f'model_provider = "{binding.provider_id}"' in config
        assert f'base_url = "{expected_url}/"' in config
        # auth.json is never projected to a deepseek-direct-bound role.
        assert not (private_root / "home" / "auth.json").exists()
        runtime_codex = resource._child_agent.package.runtime["codex"]
        assert "auth_mode" not in runtime_codex
        assert resource._child_agent.credential_mode == "provider_proxy"
    resource.destroy()
    adapter.stop()


def test_route_change_does_not_alter_role_permissions(tmp_path: Path) -> None:
    import tomllib

    default_adapter = _formal_adapter(
        load_team_model_profile(ROOT, DEFAULT_MODEL_PROFILE_ID)
    )
    mixed_adapter = _formal_adapter(_mixed_profile(tmp_path))
    host_auth = tmp_path / "auth.json"
    host_auth.write_text("{}", encoding="utf-8")
    run = _formal_run(tmp_path / "run")
    parsed_configs = []
    for adapter, label in ((default_adapter, "default"), (mixed_adapter, "mixed")):
        agent = _agent(tmp_path / label, "modeling")
        with patch.object(adapter, "preflight_host_auth", return_value=host_auth):
            adapter._write_config(run, agent)
        parsed_configs.append(
            tomllib.loads((agent.home / "config.toml").read_text(encoding="utf-8"))
        )
    default_adapter.stop()
    mixed_adapter.stop()
    default, mixed = parsed_configs
    assert set(default["mcp_servers"]) == set(mixed["mcp_servers"])
    assert default.get("sandbox") == mixed.get("sandbox")
    assert (
        default["shell_environment_policy"] == mixed["shell_environment_policy"]
    )
    for server, config in default["mcp_servers"].items():
        assert mixed["mcp_servers"][server] == config
    assert default["model_provider"] == "deepseek-direct"
    assert "model_providers" in default
    # The mixed modeling role rides the Codex built-in route: the TOML provider
    # is the built-in ``openai`` ID with no custom provider table.
    assert mixed["model_provider"] == "openai"
    assert "model_providers" not in mixed


# --------------------------------------------------------------------------
# Group F: evidence
# --------------------------------------------------------------------------


def test_low_effort_evidence_records_requested_and_effective(tmp_path: Path) -> None:
    profile = _mixed_profile(tmp_path)
    evidence = profile.as_dict()
    binding = evidence["roles"]["coordinator"]
    assert binding["model_provider"] == "deepseek-direct"
    assert binding["requested_effort"] == "low"
    assert binding["effective_effort"] == "high"
    # The runner baseline embeds profile.as_dict() verbatim, so this is the
    # exact evidence shape fresh runs must project for a DeepSeek low request.
    assert set(evidence) == {"profile_id", "path", "sha256", "roles"}
    assert set(binding) == {
        "model_provider",
        "model",
        "requested_effort",
        "effective_effort",
    }


def test_codex_role_evidence_records_provider_model_effort_and_safe_auth_mode(
    tmp_path: Path,
) -> None:
    profile = _mixed_profile(tmp_path)
    evidence = profile.as_dict()
    binding = evidence["roles"]["modeling"]
    assert binding["model_provider"] == "openai-codex"
    assert binding["model"] == "gpt-5.6-luna"
    assert binding["requested_effort"] == "medium"
    assert binding["effective_effort"] == "medium"
    assert binding["auth_mode"] == "chatgpt-subscription"
    serialized = json.dumps(evidence)
    # No token/account material, no auth cache path or digest, no raw
    # login-status output, and no OpenAI API-key surface anywhere.
    for forbidden in (
        "token",
        "account",
        "auth.json",
        ".codex",
        "codex login",
        "OPENAI_API_KEY",
        "api.openai.com",
    ):
        assert forbidden not in serialized
    # DeepSeek roles keep their exact four-field projection.
    assert set(evidence["roles"]["coordinator"]) == {
        "model_provider",
        "model",
        "requested_effort",
        "effective_effort",
    }

def test_consecutive_upstream_failures_gate_the_provider_failure_signal() -> None:
    """One transient upstream error must not signal; the threshold must.

    2026-09-11 calibration: glm-5.3-flash rejected one request mid-burst while
    the upstream stayed alive for other concurrent requests, and a single
    provider-upstream-failed latch killed three real modeling starts.  The
    consecutive-failure threshold keeps a single error recoverable through the
    App Server's own request retry while a persistently dead upstream still
    fails the run with the stable reason code.
    """

    failures: list[str] = []
    session = ResponsesProviderSession(
        b"threshold-sentinel",
        on_failure=failures.append,
        upstream_url="https://127.0.0.1:1/responses",
    )
    assert session.upstream_failure_threshold == 3
    # Two consecutive failures stay below the default threshold.
    session.note_upstream_failure()
    session.note_upstream_failure()
    assert failures == []
    # A success resets the consecutive counter.
    session.note_upstream_success()
    session.note_upstream_failure()
    session.note_upstream_failure()
    assert failures == []
    # The third consecutive failure crosses the threshold and signals once.
    session.note_upstream_failure()
    assert failures == [RESPONSES_UPSTREAM_FAILURE]
    # The counter restarts after signaling; another signal needs another run.
    session.note_upstream_failure()
    session.note_upstream_failure()
    assert failures == [RESPONSES_UPSTREAM_FAILURE]
    session.stop()
