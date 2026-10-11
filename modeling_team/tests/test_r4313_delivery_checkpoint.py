from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

import pytest

from modeling_team.checkpoint_recovery import restore_checkpoint_artifacts
from modeling_team.checkpoints import (
    CHECKPOINT_KIND_PRODUCTION_HANDOFF,
    CheckpointArtifactSpec,
    CheckpointError,
    StagePackage,
    save_checkpoint,
)
from modeling_team.handoff_materials import HandoffMaterials
from modeling_team.host_ops import submit_instruction


def _write_material_package(root: Path, material_id: str = "material-body") -> list[CheckpointArtifactSpec]:
    package = root / "handoff-materials" / material_id
    (package / "files").mkdir(parents=True)
    body = "完整正文：中文内容\n" * 20
    (package / "files" / "body.txt").write_text(body, encoding="utf-8")
    manifest = {
        "material_id": material_id,
        "kind": "file",
        "scope_id": "source-run",
        "publisher_id": "runner",
        "recipient_id": "coordinator",
        "source_alias": "/agent/handoff-output",
        "source_path": "/agent/handoff-output/body.txt",
        "entries": [{
            "path": "body.txt",
            "digest": hashlib.sha256(body.encode()).hexdigest(),
            "bytes": len(body.encode()),
        }],
    }
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    (package / "manifest.json").write_bytes(raw)
    (package / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="utf-8")
    return [
        CheckpointArtifactSpec(
            source=f"handoff-materials/{material_id}/{name}",
            owner="runner",
            visible_to=("coordinator",),
        )
        for name in ("manifest.json", "manifest.sha256", "files/body.txt")
    ]


def test_delivery_relay_binds_session_material_to_run_recipient(tmp_path: Path):
    from modeling_team.delivery import DeliverySession

    source = tmp_path / "source"
    source.mkdir()
    (source / "body.txt").write_text("正式正文\n" * 8, encoding="utf-8")
    session_store = HandoffMaterials(tmp_path / "session" / "handoff-materials", "session")
    session_store.register_actor("delivery", {"/agent/work": source}, {"runner"})
    published = session_store.publish("delivery", "runner", "/agent/work/body.txt")

    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    run_root.mkdir(parents=True)
    (run_root / "profile.snapshot.yaml").write_text(
        "agents:\n  - agent_id: coord-1\n    package: coordinator\n", encoding="utf-8"
    )
    delivery = object.__new__(DeliverySession)
    delivery.repository_root = tmp_path
    delivery.run_ids = {"run-one"}
    delivery.handoff_materials = session_store

    result = delivery._resolve_material_submission(
        "submit_instruction",
        {
            "run_id": "run-one",
            "text": "请审核下方完整正文",
            "body_ref": {"material_id": published["material_id"]},
        },
    )
    assert result["text"] == "正式正文\n" * 8
    assert result["display_text"] == "请审核下方完整正文"
    assert result["material_recipient_id"] == "coord-1"
    target = result["handoff_materials"]
    assert target.resolve("runner", result["body_ref"]) == result["text"]
    assert result["material_origins"][0]["from"]["material_id"] == published["material_id"]
    assert result["material_origins"][0]["from"]["source_binding"]["publisher_id"] == "delivery"


def test_delivery_directory_body_ref_republishes_selected_member_as_readable_file(tmp_path: Path):
    from modeling_team.delivery import DeliverySession

    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "body.json").write_text('{"正式": "正文"}', encoding="utf-8")
    session_store = HandoffMaterials(tmp_path / "session" / "handoff-materials", "session")
    session_store.register_actor("delivery", {"/agent/work": source}, {"runner"})
    published = session_store.publish("delivery", "runner", "/agent/work")

    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    run_root.mkdir(parents=True)
    (run_root / "profile.snapshot.yaml").write_text(
        "agents:\n  - agent_id: model-1\n    package: modeling\n", encoding="utf-8"
    )
    delivery = object.__new__(DeliverySession)
    delivery.repository_root = tmp_path
    delivery.run_ids = {"run-one"}
    delivery.handoff_materials = session_store

    result = delivery._resolve_material_submission(
        "answer_question",
        {
            "run_id": "run-one",
            "channel": "user",
            "text": "请读取正文",
            "question_delivery_id": "question-1",
            "body_ref": {
                "material_id": published["material_id"],
                "path": "nested/body.json",
            },
        },
    )
    assert result["handoff_materials"].resolve("runner", result["body_ref"]) == '{"正式": "正文"}'


def test_host_fifo_sends_display_and_recipient_bound_body_ref(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "body.txt").write_text("full formal body", encoding="utf-8")
    origin = HandoffMaterials(tmp_path / "origin" / "handoff-materials", "session")
    origin.register_actor("delivery", {"/agent/work": source}, {"runner"})
    source_ref = origin.publish("delivery", "runner", "/agent/work/body.txt")

    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    fifo = run_root / "control" / "outer-input.fifo"
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    target = HandoffMaterials(run_root / "handoff-materials", "run-one")
    target.register_actor("runner", {}, {"coord-1"})
    ref = target.relay_ref(
        "runner", "coord-1", {"material_id": source_ref["material_id"]},
        origin_store=origin, origin_actor_id="delivery",
    )
    received: list[dict] = []

    def consume() -> None:
        with fifo.open("rb") as handle:
            received.append(json.loads(handle.readline().decode()))

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    submit_instruction(
        "run-one",
        kind="delivery_guidance",
        text="简短展示说明",
        source_reference="source-1",
        authorization_reference="auth-1",
        body_ref=ref,
        handoff_materials=target,
        material_actor_id="runner",
        material_recipient_id="coord-1",
        repository_root=tmp_path,
    )
    reader.join(timeout=2)
    assert received[0]["text"] == "简短展示说明"
    assert received[0]["body_ref"] == ref
    assert "full formal body" not in json.dumps(received[0], ensure_ascii=False)


def test_host_mcp_style_call_binds_existing_runner_store_without_python_injection(tmp_path: Path):
    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    fifo = run_root / "control" / "outer-input.fifo"
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    (run_root / "profile.snapshot.yaml").write_text(
        "agents:\n  - agent_id: coord-1\n    package: coordinator\n", encoding="utf-8"
    )
    target = HandoffMaterials(run_root / "handoff-materials", "run-one")
    target.register_actor("runner", {}, {"coord-1"})
    output = target.write_output("runner", "formal.txt", "完整 Host 正文")
    published = target.publish("runner", "coord-1", output["source_path"])
    received: list[dict] = []

    def consume() -> None:
        with fifo.open("rb") as handle:
            received.append(json.loads(handle.readline().decode()))

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    submit_instruction(
        "run-one",
        kind="delivery_guidance",
        text="请读取已发布正文",
        source_reference="source-1",
        authorization_reference="auth-1",
        body_ref={"material_id": published["material_id"]},
        repository_root=tmp_path,
    )
    reader.join(timeout=2)
    assert received[0]["body_ref"] == {"material_id": published["material_id"]}
    assert received[0]["text"] == "请读取已发布正文"


def test_delivery_observe_relays_public_run_refs_into_session_identity(tmp_path: Path):
    from modeling_team.delivery import DeliverySession

    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    run_root.mkdir(parents=True)
    (run_root / "profile.snapshot.yaml").write_text(
        "agents:\n"
        "  - agent_id: model-1\n    package: modeling\n"
        "  - agent_id: coord-1\n    package: coordinator\n"
        "communication: []\n",
        encoding="utf-8",
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "result.json").write_text('{"结果": "完整"}', encoding="utf-8")
    run_store = HandoffMaterials(run_root / "handoff-materials", "run-one")
    run_store.register_actor("model-1", {"/agent/work": source}, {"runner"})
    run_store.register_actor("runner", {}, {"model-1", "coord-1"})
    published = run_store.publish("model-1", "runner", "/agent/work/result.json")

    session_root = tmp_path / "session"
    session_root.mkdir()
    session_store = HandoffMaterials(session_root / "handoff-materials", "session")
    session_store.register_actor("delivery", {}, {"runner"})
    delivery = object.__new__(DeliverySession)
    delivery.repository_root = tmp_path
    delivery.session_root = session_root
    delivery.run_ids = {"run-one"}
    delivery.config = {}
    delivery.handoff_materials = session_store
    delivery._event_cursors = {}
    delivery._run_material_imports = {}
    delivery._save = lambda *_args, **_kwargs: None
    event = {
        "source": "terminal-result-handoff.jsonl",
        "data": {
            "source_id": "model-1",
            "result": {"agent_id": "model-1", "body_ref": {"material_id": published["material_id"]}},
        },
    }
    result = delivery._project_run_events(
        "run-one", {"run_id": "run-one", "events": [event], "limitations": []}
    )
    projected_ref = result["events"][0]["data"]["result"]["body_ref"]
    assert projected_ref["material_id"] != published["material_id"]
    assert session_store.resolve("delivery", projected_ref) == '{"结果": "完整"}'
    origin = result["events"][0]["data"]["result"]["material_origins"][0]
    assert origin["origin_run_id"] == "run-one"
    assert origin["origin_material_id"] == published["material_id"]


def test_delivery_event_projection_drops_private_run_refs(tmp_path: Path):
    from modeling_team.delivery import DeliverySession

    delivery = object.__new__(DeliverySession)
    delivery.config = {}
    delivery._run_material_imports = {}
    projected = delivery._project_run_events(
        "run-one",
        {"events": [{
            "source": "acceptance-report.jsonl",
            "data": {"body_ref": {"material_id": "material-hidden"}, "status": "private"},
        }]},
    )
    assert "body_ref" not in projected["events"][0]["data"]


def test_imported_private_cq_material_is_readable_but_not_routable(tmp_path: Path):
    from modeling_team.delivery import DeliverySession, _LOCAL_SPECS

    run_root = tmp_path / "workspaces" / "modeling-runs" / "run-one"
    run_root.mkdir(parents=True)
    (run_root / "profile.snapshot.yaml").write_text(
        "agents:\n"
        "  - agent_id: cq-1\n    package: competency-question\n"
        "  - agent_id: coord-1\n    package: coordinator\n"
        "communication: []\n",
        encoding="utf-8",
    )
    session_store = HandoffMaterials(tmp_path / "session" / "handoff-materials", "session")
    session_store.register_actor("delivery", {}, {"runner"})
    output = session_store.write_output("delivery", "cq-draft.json", '{"hidden": true}')
    published = session_store.publish("delivery", "runner", output["source_path"])
    ref = {"material_id": published["material_id"]}
    delivery = object.__new__(DeliverySession)
    delivery.repository_root = tmp_path
    delivery.session_root = tmp_path / "session"
    delivery.run_ids = {"run-one"}
    delivery.config = {
        "public_repair_references": [],
        "repair_owned_paths": [str(tmp_path / "owned")],
    }
    delivery.sources = set()
    delivery.authorization = "auth-cq"
    delivery.repair_task_files = set()
    delivery.allowed_operations = {"repair"}
    delivery.handoff_materials = session_store
    delivery._run_material_imports = {
        ("run-one", ref["material_id"], None): {
            "origin_run_id": "run-one",
            "origin_binding": {"publisher_id": "cq-1", "recipient_id": "runner"},
            "target_ref": ref,
        }
    }
    delivery._tools = {item["name"]: item for item in _LOCAL_SPECS}
    listing = delivery.call_tool("list_handoff_material", ref)
    reading = delivery.call_tool("read_handoff_material", ref)
    assert listing["ok"] and reading["ok"]
    assert delivery._is_private_cq_material(ref)
    with pytest.raises(Exception, match="private CQ material"):
        delivery._resolve_material_submission(
            "consult_team",
            {
                "run_id": "run-one",
                "text": "请协调处理",
                "recipient_id": "coord-1",
                "body_ref": ref,
            },
        )
    repair = delivery.call_tool(
        "prepare_repair_task",
        {
            "operation_id": "repair-cq",
            "text": "尝试把 CQ 草稿交给修复",
            "source_references": [f"material:{ref['material_id']}"],
            "material_refs": [ref],
            "owned_paths": [str(tmp_path / "owned" / "file.py")],
        },
    )
    assert not repair["ok"] and repair["error"]["code"] == "delivery_contract"
    assert "private CQ material" in repair["error"]["message"]


def test_checkpoint_snapshots_public_handoff_and_reports_restore_binding(tmp_path: Path):
    run_root = tmp_path / "source-run"
    run_root.mkdir()
    specs = _write_material_package(run_root)
    saved = save_checkpoint(
        run_root,
        StagePackage(
            kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            scope_refs={},
            artifacts=specs,
        ),
        source_run_id="source-run",
    )
    manifest = json.loads(
        (run_root / "checkpoints" / saved["checkpoint_id"] / "manifest.json").read_text()
    )
    assert len([
        entry for entry in manifest["artifacts"]
        if entry["source"].startswith("handoff-materials/")
    ]) == len(specs)
    target = tmp_path / "target-run"
    target_store = HandoffMaterials(target / "handoff-materials", "target-run")
    target_store.register_actor("runner", {}, {"coordinator"})
    result = restore_checkpoint_artifacts(
        manifest, run_root, target, handoff_materials=target_store
    )
    assert result["handoff_material_bindings"][0]["origin_scope_id"] == "source-run"
    restored_manifest = json.loads(
        (target / "handoff-materials" / "material-body" / "manifest.json").read_text()
    )
    assert restored_manifest["scope_id"] == "source-run"
    assert target_store.resolve("runner", {"material_id": "material-body"}).startswith("完整正文")


def test_checkpoint_restore_rebinds_physical_run_root_source(tmp_path: Path):
    source_run = tmp_path / "source-run"
    source_run.mkdir()
    specs = _write_material_package(source_run, "material-physical")
    old_source = source_run / "runtime" / "modeling" / "work"
    old_source.mkdir(parents=True)
    old_path = old_source / "body.txt"
    old_path.write_text("物理源快照", encoding="utf-8")
    manifest_path = source_run / "handoff-materials" / "material-physical" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_alias"] = str(old_source)
    manifest["source_path"] = str(old_path)
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
    manifest_path.write_bytes(raw)
    (manifest_path.parent / "manifest.sha256").write_text(
        hashlib.sha256(raw).hexdigest(), encoding="utf-8"
    )
    saved = save_checkpoint(
        source_run,
        StagePackage(
            kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
            scope_refs={},
            artifacts=specs,
        ),
        source_run_id="source-run",
    )
    checkpoint_manifest = json.loads(
        (source_run / "checkpoints" / saved["checkpoint_id"] / "manifest.json").read_text()
    )
    target = tmp_path / "target-run"
    new_source = target / "runtime" / "modeling" / "work"
    new_source.mkdir(parents=True)
    (new_source / "body.txt").write_text("当前授权源", encoding="utf-8")
    target_store = HandoffMaterials(target / "handoff-materials", "target-run")
    target_store.register_actor("runner", {str(new_source): new_source}, {"coordinator"})
    restore_checkpoint_artifacts(
        checkpoint_manifest, source_run, target, handoff_materials=target_store
    )
    binding = json.loads(
        (target / "handoff-materials" / "material-physical" / "restored-binding.json").read_text()
    )
    assert binding["source_alias"] == str(new_source)
    assert binding["source_path"] == str(new_source / "body.txt")
    assert target_store.resolve("runner", {"material_id": "material-physical"}).startswith("完整正文")


def test_checkpoint_rejects_host_private_handoff_package(tmp_path: Path):
    run_root = tmp_path / "source-run"
    run_root.mkdir()
    specs = _write_material_package(run_root)
    specs[0] = CheckpointArtifactSpec(
        source=specs[0].source, owner="acceptance", visible_to=("host",), host_private=True
    )
    with pytest.raises(CheckpointError) as error:
        save_checkpoint(
            run_root,
            StagePackage(
                kind=CHECKPOINT_KIND_PRODUCTION_HANDOFF,
                scope_refs={},
                artifacts=specs,
            ),
            source_run_id="source-run",
        )
    assert error.value.reason_code == "checkpoint_private_material"


def test_runner_checkpoint_collects_scoped_handoff_packages(tmp_path: Path):
    """The Runner collector packages real stores, including CQ private refs."""

    from modeling_team.tests.test_r30015_checkpoints import (
        _CheckpointRunner,
        _read_manifest,
        _write_json,
    )

    harness = _CheckpointRunner()
    try:
        runner = harness.prepare()
        store = runner.run.handoff_materials
        modeling_output = store.write_output("modeling", "candidate.json", '{"candidate": true}')
        store.publish("modeling", "coordinator", modeling_output["source_path"])
        cq_output = store.write_output("competency-question", "draft.json", '{"draft": true}')
        store.publish("competency-question", "runner", cq_output["source_path"])
        _write_json(
            runner.run.root / "acceptance-v3" / "production-handoff.json",
            {
                "freeze_id": "batch-r4313",
                "freeze_digest": "sha256:" + "0" * 64,
                "scope_binding": {"project_id": "p1", "ontology_ids": ["o1"]},
                "applied_batches": [],
                "unknown_writes": [],
                "write_phase": "read-only",
            },
        )
        result = runner._save_run_checkpoint(
            CHECKPOINT_KIND_PRODUCTION_HANDOFF, trigger="r4313-test"
        )
        manifest = _read_manifest(runner.run.root, result["checkpoint_id"])
        artifacts = {
            item["source"]: item for item in manifest["artifacts"]
            if item["source"].startswith("handoff-materials/")
        }
        assert any(item["owner"] == "modeling" and item["visible_to"] == ["coordinator"]
                   and not item["host_private"] for item in artifacts.values())
        assert any(item["owner"] == "competency-question"
                   and item["visible_to"] == ["host", "competency-question"]
                   and item["host_private"] for item in artifacts.values())
    finally:
        harness.cleanup()
