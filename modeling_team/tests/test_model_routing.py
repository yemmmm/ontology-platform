"""R2.3-007 deterministic focused tests: Groups A-F of the shared test plan.

Group G (real provider probes) and the final H gates belong to the independent
tester; every test here uses repository fixtures, fake upstreams, or session
doubles only.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import threading
import time
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
    DEFAULT_MODEL_PROFILE_ID,
    DEEPSEEK_DIRECT_ROUTE,
    MODEL_PROFILE_PACKAGE_IDS,
    OPENAI_CREDENTIAL_PATH,
    OPENAI_DIRECT_ROUTE,
    PROVIDER_CATALOG,
    REQUESTED_EFFORT_TIERS,
    ProviderCredentialUnavailableError,
    ProviderSessionManager,
    TeamModelProfile,
    load_team_model_profile,
    preflight_openai_credential,
    preflight_profile_credentials,
    read_openai_credential,
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
        "model_provider": "openai-direct",
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
        "model_provider": "openai-direct",
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
            "openai-direct": "http://127.0.0.1:49002",
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
        assert binding.provider_id == "openai-direct"
        assert binding.model == "gpt-5.6-luna"
        assert binding.requested_effort == "medium"
        assert binding.effective_effort == "medium"


def test_catalog_effort_capability_mapping_is_closed() -> None:
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("low") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("medium") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("high") == "high"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("xhigh") == "max"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("max") == "max"
    assert DEEPSEEK_DIRECT_ROUTE.effective_effort("none") is None
    for tier in REQUESTED_EFFORT_TIERS:
        assert OPENAI_DIRECT_ROUTE.effective_effort(tier) == tier
    assert set(PROVIDER_CATALOG) == {"deepseek-direct", "openai-direct"}
    for route in PROVIDER_CATALOG.values():
        assert route.wire_api == "responses"
        assert route.upstream_url.startswith("https://")


def test_mixed_profile_routes_each_role_with_capability_effort(tmp_path: Path) -> None:
    profile = _mixed_profile(tmp_path)
    assert profile.provider_ids() == ("deepseek-direct", "openai-direct")
    for package_id in MODEL_PROFILE_PACKAGE_IDS:
        binding = profile.binding_for(package_id)
        declaration = _MIXED_ROLES[package_id]
        assert binding.provider_id == declaration["model_provider"]
        assert binding.model == declaration["model"]
        assert binding.requested_effort == declaration["model_reasoning_effort"]
        assert binding.effective_effort == _MIXED_EFFECTIVE[package_id]


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
        '    model_provider: "openai-direct"\n'
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

    assert all(
        contract.default_model_profile_id == DEFAULT_MODEL_PROFILE_ID
        for contract in FORMAL_RUN_CONTRACTS
    )


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
        def preflight_host_auth(self) -> None:
            return None

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
    serialized = json.dumps(manifest)
    assert "api.openai.com" not in serialized
    assert "api.deepseek.com" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "DEEPSEEK_API_KEY" not in serialized
    assert str(OPENAI_CREDENTIAL_PATH) not in serialized


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


def test_non_2xx_upstream_body_is_dropped_with_fixed_local_failure(
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
    )
    session.start()
    try:
        connection = _loopback_client(session)
        connection.request(
            "POST", "/responses", body=b"{}", headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 502
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


def test_openai_credential_file_contract_mirrors_deepseek_rules(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-sentinel")
    with pytest.raises(Exception, match="unavailable"):
        preflight_openai_credential(tmp_path / "missing.env")

    path = _credential_file(tmp_path, "openai.env", "OPENAI_API_KEY=sk-openai-sentinel")
    binding = preflight_openai_credential(path)
    assert "sk-openai-sentinel" not in repr(binding)
    assert read_openai_credential(binding) == b"sk-openai-sentinel"

    no_newline = _credential_file(
        tmp_path, "openai-no-newline.env", "OPENAI_API_KEY=sk-openai-sentinel"
    )
    assert read_openai_credential(preflight_openai_credential(no_newline)) == (
        b"sk-openai-sentinel"
    )

    path.write_text("OPENAI_API_KEY=rotated\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(Exception, match="binding changed"):
        read_openai_credential(binding)

    insecure = _credential_file(
        tmp_path, "openai-insecure.env", "OPENAI_API_KEY=sk-openai-sentinel\n"
    )
    insecure.chmod(0o640)
    with pytest.raises(Exception, match="insecure"):
        preflight_openai_credential(insecure)

    target = _credential_file(
        tmp_path, "openai-target.env", "OPENAI_API_KEY=sk-openai-sentinel\n"
    )
    link = tmp_path / "openai-link.env"
    link.symlink_to(target)
    with pytest.raises(Exception, match="insecure"):
        preflight_openai_credential(link)


@pytest.mark.parametrize(
    "payload",
    [
        b"OPENAI_API_KEY=\n",
        b"OPENAI_API_KEY='quoted'\n",
        b"OPENAI_API_KEY=\"quoted\"\n",
        b"OPENAI_API_KEY = spaced\n",
        b"export OPENAI_API_KEY=exported\n",
        b"OPENAI_API_KEY=one\nOPENAI_API_KEY=two\n",
        b"OTHER=value\n",
        b"OPENAI_API_KEY=trailing space\n",
        b"\n",
        b"",
    ],
)
def test_openai_credential_rejects_non_exact_assignments(
    tmp_path: Path, payload: bytes
) -> None:
    path = tmp_path / "openai.env"
    path.write_bytes(payload)
    path.chmod(0o600)
    with pytest.raises(Exception):
        preflight_openai_credential(path)


def test_missing_referenced_credential_fails_typed_before_any_read_of_others(
    monkeypatch, tmp_path: Path
) -> None:
    deepseek = _credential_file(
        tmp_path, "deepseek.env", "DEEPSEEK_API_KEY=mixed-deepseek-sentinel\n"
    )
    openai = _credential_file(
        tmp_path, "openai.env", "OPENAI_API_KEY=sk-mixed-openai-sentinel\n"
    )
    deepseek_only = load_team_model_profile(ROOT, DEFAULT_MODEL_PROFILE_ID)
    bindings = preflight_profile_credentials(
        deepseek_only, deepseek_credential_path=deepseek
    )
    assert set(bindings) == {"deepseek-direct"}

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
    preflight_profile_credentials(
        deepseek_only, deepseek_credential_path=deepseek, openai_credential_path=openai
    )
    assert calls == ["deepseek-direct"]

    mixed = _mixed_profile(tmp_path)
    with pytest.raises(ProviderCredentialUnavailableError) as excinfo:
        preflight_profile_credentials(
            mixed,
            deepseek_credential_path=deepseek,
            openai_credential_path=tmp_path / "absent.env",
        )
    assert excinfo.value.reason_code == "provider-credential-unavailable"
    assert excinfo.value.category == "runtime/infrastructure"
    assert excinfo.value.args[0] == (
        "provider credential preflight failed for openai-direct"
    )


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
    openai = _credential_file(
        tmp_path, "openai.env", "OPENAI_API_KEY=sk-manager-openai-sentinel\n"
    )
    mixed = _mixed_profile(tmp_path)
    return preflight_profile_credentials(
        mixed, deepseek_credential_path=deepseek, openai_credential_path=openai
    )


def test_manager_creates_one_session_per_referenced_provider_and_shares_it(
    tmp_path: Path,
) -> None:
    bindings = _real_bindings(tmp_path)
    created: list[_FakeSession] = []

    def factory(key: bytes, *, provider_id: str, **_kwargs: object) -> _FakeSession:
        assert key
        session = _FakeSession(key, provider_id)
        created.append(session)
        return session

    manager = ProviderSessionManager(
        {key: value for key, value in bindings.items() if key == "deepseek-direct"},
        session_factory=factory,
    )
    manager.start()
    assert [session.provider_id for session in created] == ["deepseek-direct"]
    assert manager.provider_ids() == ("deepseek-direct",)
    assert manager.base_url_for("deepseek-direct") == created[0].base_url
    manager.stop()

    created.clear()
    mixed_manager = ProviderSessionManager(bindings, session_factory=factory)
    mixed_manager.start()
    assert [session.provider_id for session in created] == [
        "deepseek-direct",
        "openai-direct",
    ]
    deepseek_url = mixed_manager.base_url_for("deepseek-direct")
    openai_url = mixed_manager.base_url_for("openai-direct")
    assert deepseek_url != openai_url
    for _role in MODEL_PROFILE_PACKAGE_IDS:
        # Every role on one provider resolves to that provider's shared session.
        assert mixed_manager.base_url_for("deepseek-direct") == deepseek_url
    assert set(mixed_manager.secret_values()) == {
        b"manager-deepseek-sentinel",
        b"sk-manager-openai-sentinel",
    }
    reports = mixed_manager.stop()
    assert set(reports) == {"deepseek-direct", "openai-direct"}
    assert all(session.stopped and session.cleared for session in created)
    assert all(not any(bytes(session.key)) for session in created)


def test_manager_stop_attempts_every_session_independently(tmp_path: Path) -> None:
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
    assert sessions["openai-direct"].stopped is True
    assert reports["deepseek-direct"]["lifecycle_failure"] is True
    assert reports["openai-direct"]["lifecycle_failure"] is False
    assert all(session.cleared for session in sessions.values())
    assert manager.cleanup_failed(reports) is True


def test_runtime_latches_first_provider_failure_and_cannot_be_overwritten(
    tmp_path: Path,
) -> None:
    adapter = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter._coordination_enabled = True
    adapter._provider_sessions = _SessionsDouble()
    adapter._on_provider_session_failure("provider-upstream-failed")
    adapter._on_provider_session_failure("provider-session-cleanup-failed")
    with adapter._runtime_failure_lock:
        failures = list(adapter._runtime_failures)
    assert failures == [
        (
            "provider-sessions",
            {
                "category": "runtime/infrastructure",
                "reason_code": "provider-upstream-failed",
            },
        )
    ]
    assert adapter._provider_session_failure_latched is True

    adapter2 = CodexRuntimeAdapter(repository_root=ROOT, use_bwrap=False)
    adapter2._coordination_enabled = True
    adapter2._provider_sessions = _NotListeningSessions()
    adapter2.receive_messages()
    with adapter2._runtime_failure_lock:
        assert adapter2._runtime_failures == [
            (
                "provider-sessions",
                {
                    "category": "runtime/infrastructure",
                    "reason_code": "provider-upstream-failed",
                },
            )
        ]
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
        assert parsed["model_provider"] == binding.provider_id
        assert parsed["model_reasoning_effort"] == binding.effective_effort
        provider_table = parsed["model_providers"][binding.provider_id]
        assert set(provider_table) == {"name", "base_url", "wire_api"}
        assert provider_table["wire_api"] == "responses"
        assert provider_table["base_url"] == (
            _SessionsDouble().base_url_for(binding.provider_id) + "/"
        )
        assert parsed["shell_environment_policy"]["exclude"] == [
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "LLM_API_KEY",
        ]
        adapter._initialize(agent)
        assert starts[role]["model"] == binding.model
        assert "model_provider" not in starts[role]
        assert "model_reasoning_effort" not in starts[role]
    adapter.stop()


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
        == "openai-direct"
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
                {"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}]}
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
                    "graph_set_id": "graph",
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
    expected_url = _SessionsDouble().base_url_for(binding.provider_id)
    assert f'model = "{binding.model}"' in config
    assert f'model_provider = "{binding.provider_id}"' in config
    assert f'model_reasoning_effort = "{binding.effective_effort}"' in config
    assert f'base_url = "{expected_url}/"' in config
    assert len(thread_starts) == 1
    assert thread_starts[0]["model"] == binding.model
    if kind == "source":
        assert binding.provider_id == "openai-direct"
        assert binding.effective_effort == "none"
    else:
        assert binding.provider_id == "deepseek-direct"
        assert binding.effective_effort == "max"
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
    assert mixed["model_provider"] == "openai-direct"


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
