"""Active role inputs expose the process method and a translatable complete example."""

import json
from pathlib import Path
from types import SimpleNamespace

from modeling_team.contracts import load_multi_slice_team_configuration
from modeling_team.protocol_mechanics import build_candidate_receipt, translate_candidate_to_batches
from modeling_team.runner import TeamRunner

ROOT = Path(__file__).resolve().parents[2]


def test_active_role_inputs_include_process_contract_and_complete_example():
    refs = ROOT / "modeling_team/references"
    authoring = json.loads((refs / "platform-neutral-candidate-authoring.json").read_text())
    role = json.loads((refs / "r4-0-012-modeling-contract.json").read_text())
    assert authoring["process_binding_semantics"] == role["process_binding_semantics"]
    example = authoring["process_binding_example_candidate"]
    assert build_candidate_receipt(example)["status"] == "accepted"
    assert not translate_candidate_to_batches(example)["conflicts"]
    config = load_multi_slice_team_configuration(
        ROOT / "modeling_team/profiles/r3-0-011-competency-question.yaml",
        ROOT / "modeling_team/tasks/r4-0-012-tracing-suspension.yaml",
    )
    runner = TeamRunner(repository_root=ROOT, adapter=SimpleNamespace())
    runner.run = SimpleNamespace(configuration=config, protocol_context=None, gate_binding=None)
    runner._competency_questions = True
    for name in ("modeling", "protocol"):
        source = next(
            s for s in config.task.role_sources
            if s.path.name == "platform-neutral-candidate-authoring.json" and name in s.roles
        )
        assert "process_binding_semantics" in source.path.read_text()
        assert f"/agent/home/sources/{source.relative_path.as_posix()}" in runner._task_text(name)
        package = next(a.package for a in config.profile.agents if a.agent_id == name)
        instructions = package.instructions_path.read_text()
        assert "process_binding_semantics" in instructions
        assert "process_binding_example_candidate" in instructions
