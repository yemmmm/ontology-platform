"""Real SDK and Linux namespace checks; no model endpoint is reachable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib

import pytest

from ontoweave_modeling.preflight import (
    ModelBinding,
    candidate_config,
    inspect_runtime,
    namespace_command,
)

BINDING = ModelBinding("glm-direct", "glm-5.3-flash", "low")


def test_import_does_not_load_legacy_runner():
    # Test startup itself, independent of contract tests that legitimately use
    # shared pure helpers later in the pytest process.
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import ontoweave_modeling.preflight; "
                "import ontoweave_modeling.role_candidates; "
                "assert 'modeling_team' not in sys.modules; "
                "assert 'modeling_team.runner' not in sys.modules"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_profile_preserves_role_binding(tmp_path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "roles:\n  acceptance:\n    model_provider: glm-direct\n"
        "    model: glm-5.3-flash\n    model_reasoning_effort: low\n"
    )
    assert ModelBinding.from_profile(profile, "acceptance") == BINDING
    with pytest.raises(KeyError):
        ModelBinding.from_profile(profile, "modeling")


@pytest.mark.parametrize("effort", ["null", "''", "false"])
def test_profile_does_not_silently_default_missing_effort(tmp_path, effort):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "roles:\n  modeling:\n    model_provider: glm-direct\n"
        f"    model: glm-5.3-flash\n    model_reasoning_effort: {effort}\n"
    )
    with pytest.raises(ValueError, match="explicit"):
        ModelBinding.from_profile(profile, "modeling")


def test_config_is_explicit_and_has_no_authentication():
    config = tomllib.loads(candidate_config(BINDING))
    assert config["model_provider"] == "glm-direct"
    assert config["model"] == "glm-5.3-flash"
    assert config["model_reasoning_effort"] == "low"
    assert config["model_providers"]["glm-direct"]["base_url"] == "http://127.0.0.1:9/v1"
    assert config["model_providers"]["glm-direct"]["requires_openai_auth"] is False
    assert config["sandbox_mode"] == "read-only"
    assert config["features"]["shell_tool"] is False
    assert config["features"]["memories"] is False
    assert config["project_doc_max_bytes"] == 0
    assert "mcp_servers" not in config
    assert "default_tools_enabled" not in config


def test_namespace_cannot_read_host_inputs_or_sibling_home(tmp_path):
    hidden = tmp_path / "hidden-evaluation.md"
    hidden.write_text("private test sentinel")
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    # Parent instructions and credentials must stay outside the child view.
    (tmp_path / "AGENTS.md").write_text("unapproved host instructions")
    (tmp_path / "auth.json").write_text("unapproved credentials")
    probe = (
        "import json,os,pathlib,socket; "
        "print(json.dumps({'host_file':pathlib.Path(" + repr(str(hidden)) + ").exists(),"
        "'parent_instructions':pathlib.Path('/agent/AGENTS.md').exists(),"
        "'host_env':os.environ.get('ONTOWEAVE_TEST_HOST_SENTINEL'),"
        "'auth':pathlib.Path('/agent/home/auth.json').exists(),"
        "'cwd':os.getcwd(),"
        "'interfaces':[name for _,name in socket.if_nameindex()]}))"
    )
    result = subprocess.run(
        [*namespace_command(home, work), "/usr/bin/python3", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={**os.environ, "ONTOWEAVE_TEST_HOST_SENTINEL": "must-not-be-inherited"},
    )
    actual = json.loads(result.stdout)
    assert actual == {
        "host_file": False,
        "parent_instructions": False,
        "host_env": None,
        "auth": False,
        "cwd": "/agent/work",
        "interfaces": ["lo"],
    }


def test_real_sdk_reads_back_binding_without_starting_a_turn(tmp_path):
    result = inspect_runtime(tmp_path / "evidence", BINDING)
    assert result["sdk"] == result["runtime_package"] == "0.163.0"
    assert result["cli_version"] == "codex-cli 0.163.0"
    thread = result["thread"]
    assert thread["model"] == BINDING.model
    assert thread["modelProvider"] == BINDING.provider
    assert thread["reasoningEffort"] == BINDING.effort
    assert thread["thread"]["turns"] == []
    assert thread["instructionSources"] == []
    assert thread["approvalPolicy"] == "never"
    assert thread["sandbox"]["type"] == "readOnly"
    assert result["features"]["nextCursor"] is None
    features = {row["name"]: row["enabled"] for row in result["features"]["data"]}
    assert all(
        features[name] is False
        for name in (
            "shell_tool",
            "sleep_tool",
            "view_image",
            "goals",
            "multi_agent",
            "memories",
        )
    )
    assert result["mcp"]["data"] == []
    assert "turn/start" not in result["rpc_methods"]
    assert "V1--V8 remain unverified" in result["scope"]
    saved = json.loads((tmp_path / "evidence" / "preflight.json").read_text())
    assert saved == result


def test_preflight_preserves_previous_evidence(tmp_path):
    target = tmp_path / "previous"
    target.mkdir()
    original = target / "preflight.json"
    original.write_text("previous result")
    with pytest.raises(FileExistsError):
        inspect_runtime(target, BINDING)
    assert original.read_text() == "previous result"
