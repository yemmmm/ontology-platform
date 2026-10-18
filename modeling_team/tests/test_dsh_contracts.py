import hashlib
from pathlib import Path

import pytest

from modeling_team.capability_mcp import read_role_material
from modeling_team.contracts import load_profile, TeamConfigurationError
from modeling_team.model_routing import (
    load_team_model_profile,
    validate_runtime_model_profile,
    TeamModelProfileError,
)
from modeling_team.runner import CQWriteAdmission

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_route_is_exact_and_does_not_reuse_codex_effort_mapping():
    native = load_team_model_profile(ROOT, "dsh-deepseek-flash-low")
    binding = native.binding_for("modeling")
    assert binding.requested_effort == binding.effective_effort == "low"
    validate_runtime_model_profile("dsh", native)
    with pytest.raises(TeamModelProfileError, match="unsupported-runtime-provider"):
        validate_runtime_model_profile("codex", native)
    with pytest.raises(TeamModelProfileError, match="unsupported-runtime-provider"):
        validate_runtime_model_profile("dsh", load_team_model_profile(ROOT, "openai-sol-medium"))
    old = load_profile(
        ROOT / "modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml",
        root=ROOT,
        multi_slice=True,
        direct_modeling=True,
    )
    assert old.runtime == "codex"


def test_selected_package_requires_its_own_valid_runtime_block(tmp_path):
    import shutil
    import yaml

    base = tmp_path / "modeling_team"
    for directory in ("agent-packages", "profiles", "skills/minimal-chain-modeling"):
        (base / directory).mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "modeling_team/agent-packages").glob("minimal-chain-*"):
        shutil.copytree(source, base / "agent-packages" / source.name)
    shutil.copyfile(
        ROOT / "modeling_team/skills/minimal-chain-modeling/SKILL.md",
        base / "skills/minimal-chain-modeling/SKILL.md",
    )
    profile = base / "profiles/test.yaml"
    shutil.copyfile(
        ROOT / "modeling_team/profiles/r4-3-026-minimal-installation-chain-dsh.yaml", profile
    )
    assert (
        load_profile(profile, root=tmp_path, multi_slice=True, direct_modeling=True).runtime
        == "dsh"
    )
    package = base / "agent-packages/minimal-chain-modeling/package.yaml"
    value = yaml.safe_load(package.read_text())
    del value["runtime"]["dsh"]
    package.write_text(yaml.safe_dump(value))
    with pytest.raises(TeamConfigurationError, match="runtime.dsh"):
        load_profile(profile, root=tmp_path, multi_slice=True, direct_modeling=True)
    value["runtime"]["dsh"] = {"sandbox": "danger-full-access"}
    package.write_text(yaml.safe_dump(value))
    with pytest.raises(TeamConfigurationError, match="invalid dsh sandbox"):
        load_profile(profile, root=tmp_path, multi_slice=True, direct_modeling=True)


def test_material_reader_preserves_utf8_and_denies_unknown_ids_and_changes(tmp_path):
    source = tmp_path / "original.txt"
    source.write_text("原始资料abc")
    manifest = {
        "material-1": {
            "file": str(source),
            "source": "role/source.txt",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    }
    first = read_role_material(manifest, {"material_id": "material-1", "limit": 3})
    assert first["text"] == "原始资" and first["next_offset"] == 3 and not first["read_complete"]
    rest = read_role_material(manifest, {"material_id": "material-1", "offset": 3})
    assert rest["text"] == "料abc" and rest["read_complete"]
    for arguments in (
        {"material_id": "../../hidden"},
        {"material_id": "material-1", "path": "/etc/passwd"},
        {"material_id": "material-1", "limit": 16385},
    ):
        with pytest.raises(ValueError):
            read_role_material(manifest, arguments)
    source.write_text("changed")
    with pytest.raises(ValueError, match="material changed"):
        read_role_material(manifest, {"material_id": "material-1"})


def test_pause_closes_admission_but_late_original_write_completes():
    admission = CQWriteAdmission()
    ticket = admission.admit("application")
    admission.set_flow_paused(True)
    assert admission.admit("late-application") is None
    assert admission.snapshot()["in_flight"][0]["ticket"] == ticket
    admission.complete(ticket, "applied-original-application")
    assert not admission.snapshot()["in_flight"]
    admission.set_flow_paused(False)
    assert admission.admit("new-application") is not None


def test_runner_dsh_control_uses_host_evidence_and_preserves_unknown_write_gate(tmp_path):
    from types import SimpleNamespace
    from modeling_team.runner import TeamRunner

    class ControlAdapter:
        runtime = "dsh"

        def pause(self):
            assert runner._cq_write_admission.admit("forbidden-after-pause") is None
            return {"modeling": [{"pid": 123, "state": "T"}]}

        def resume(self):
            return {"modeling": [{"pid": 123, "state": "T"}]}

        def send_message(self, *args):
            raise AssertionError("user control must not wait for a frozen Coordinator")

    adapter = ControlAdapter()
    runner = TeamRunner(repository_root=ROOT, adapter=adapter)
    (tmp_path / "evidence").mkdir()
    runner.run = SimpleNamespace(root=tmp_path, run_id="dsh-control")
    runner._staged_resolution_blocker = lambda: "original-unknown-write"
    ticket = runner._cq_write_admission.admit("original-application")
    paused = runner._relay_flow_message("pause", {"request_id": "pause-1"})[0]
    assert paused["status"] == "effective" and runner._flow_waiting
    assert paused["write_admission"]["in_flight"][0]["ticket"] == ticket
    assert not runner._observe_flow_confirmation(SimpleNamespace(agent_id="coordinator", text="{}"))
    runner._relay_flow_message("resume", {"request_id": "resume-1"})
    assert not runner._flow_waiting
    assert runner._cq_write_admission.admit("still-unknown") is None
    runner._cq_write_admission.complete(ticket, "original-application-reconciled")
    runner._staged_resolution_blocker = lambda: None
    runner._relay_flow_message("resume", {"request_id": "resume-2"})
    assert runner._cq_write_admission.admit("new-safe-application") is not None
