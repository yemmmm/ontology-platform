"""R4.3-035 deterministic wiring; no external model or platform writes."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.handoff_materials import MaterialError
from modeling_team.runtime_handoff import DshRunMaterials


@pytest.fixture
def materials(tmp_path):
    store = DshRunMaterials(tmp_path / "handoff-materials", "run-1", {"coord"})
    for actor in ("coord", "model", "cq"):
        store.register_actor(actor, {}, {"runner"})
    public = tmp_path / "competency-questions/public"
    public.mkdir(parents=True)
    store.register_actor("runner", {str(public): public}, {"coord", "model"})
    return store


def test_artifacts_arrive_exactly_with_versions_and_no_repeat_effect(materials):
    data = '{\n "中文": "原文"\n}\n'
    result = materials.write_output("coord", "scenario-map/scenario-map.json", data)
    receipt = result["runner_receipt"]
    target = materials.root.parent / receipt["target"]
    assert target.read_bytes() == data.encode()
    assert receipt["run_id"] == "run-1" and receipt["state"] == "received"
    assert materials.resolve("runner", receipt["material_ref"]) == data
    mtime = target.stat().st_mtime_ns
    retry = materials.write_output("coord", "scenario-map/scenario-map.json", data)
    assert retry["runner_receipt"] == receipt
    assert target.stat().st_mtime_ns == mtime
    updated = materials.write_output("coord", "scenario-map/scenario-map.json", data + " ")
    assert updated["runner_receipt"]["material_ref"] != receipt["material_ref"]
    assert materials.resolve("runner", receipt["material_ref"]) == data


def test_role_path_and_binding_errors_are_recoverable(materials):
    with pytest.raises(MaterialError, match="material_forbidden"):
        materials.write_output("model", "scenario-map/scenario-map.json", "{}")
    with pytest.raises(MaterialError, match="material_path_invalid"):
        materials.write_output("coord", "scenario-map/../outside", "{}")
    with pytest.raises(MaterialError, match="material_path_invalid"):
        materials.write_output("coord", "scenario-map/unexpected.json", "{}")
    ordinary = materials.write_output("model", "notes.json", "{}")
    assert "runner_receipt" not in ordinary
    good = materials.write_output("coord", "scenario-map/topology-decision.json", "{}")
    ref = good["runner_receipt"]["material_ref"]
    with pytest.raises(MaterialError, match="material_forbidden"):
        materials.resolve("model", ref)
    with pytest.raises(MaterialError, match="material_binding_changed"):
        DshRunMaterials(materials.root, "other-run", {"coord"})


def test_target_failure_and_lost_receipt_resume_original_version(materials, monkeypatch):
    original = Path.replace

    def fail(source, target):
        if str(target).endswith("topology-decision.json"):
            raise OSError("fixture disk failure")
        return original(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        with pytest.raises(MaterialError, match="material_target_unavailable"):
            materials.write_output("coord", "scenario-map/topology-decision.json", "{}")
    record = list(materials.artifacts.values())[0]
    ref = record["material_ref"]
    repaired = materials.write_output("coord", "scenario-map/topology-decision.json", "{}")
    assert repaired["runner_receipt"]["material_ref"] == ref
    target = materials.root.parent / record["target"]
    mtime = target.stat().st_mtime_ns
    restored = DshRunMaterials(materials.root, "run-1", {"coord"})
    restored.register_actor("coord", {}, {"runner"})
    restored.register_actor("runner", {}, {"coord"})
    assert (
        restored.write_output("coord", record["target"], "{}")["runner_receipt"]["material_ref"]
        == ref
    )
    assert target.stat().st_mtime_ns == mtime


def test_public_input_is_original_readable_and_keeps_freeze_and_version_identity(materials):
    path = materials.root.parent / "competency-questions/public/public-projection-0001.json"
    path.write_text('{"questions":[{"text":"公开"}]}')
    materials.queue_public_input(path, ["coord", "model"], "projection-digest")
    next_path = path.with_name("public-projection-0002.json")
    next_path.write_text('{"questions":[]}')
    materials.queue_public_input(
        next_path,
        ["coord", "model"],
        "new-digest",
        freeze={"batch_id": "batch-1", "snapshot_digest": "freeze-digest"},
    )
    deliveries = []

    class Adapter:
        def send_message(self, recipient, delivery):
            deliveries.append(delivery)
            return SimpleNamespace(dispatch_id=delivery.delivery_id)

        def dispatch_status(self, recipient):
            return [
                {"dispatch_id": d.delivery_id, "state": "queued"}
                for d in deliveries
                if d.recipient_id == recipient
            ]

    materials.flush_public_inputs(Adapter())
    assert len(deliveries) == 4
    first = deliveries[0]
    notice = json.loads(first.text)
    assert notice["run_id"] == "run-1" and notice["version"].endswith("0001.json")
    assert "freeze" not in notice
    assert materials.resolve(first.recipient_id, first.material_refs[0]) == path.read_text()
    assert json.loads(deliveries[2].text)["freeze"]["batch_id"] == "batch-1"
    assert not any("hidden" in delivery.text for delivery in deliveries)
    with pytest.raises(MaterialError, match="material_forbidden"):
        materials.resolve("cq", first.material_refs[0])
    # Native queue evidence, not a local sent bit, proves no resend is needed.
    materials.flush_public_inputs(Adapter())
    assert len(deliveries) == 4


def test_public_failure_retries_same_material_and_id_without_killing_run(materials):
    path = materials.root.parent / "competency-questions/public/public-projection-0001.json"
    path.write_text("{}")
    materials.queue_public_input(path, ["coord"], "digest")
    sent = []

    class Adapter:
        def send_message(self, recipient, delivery):
            sent.append(delivery)
            if len(sent) == 1:
                raise RuntimeError("temporarily paused")
            return SimpleNamespace(dispatch_id="native-dispatch")

    adapter = Adapter()
    materials.flush_public_inputs(adapter)
    assert list(materials.public_inputs.values())[0]["error"] == "temporarily paused"
    materials.flush_public_inputs(adapter)
    assert sent[0] == sent[1]


def test_actual_runner_review_and_freeze_project_public_only(tmp_path):
    from modeling_team.tests.test_r3011_runner_wiring import _CQRunner, _run_lifecycle_to_frozen

    harness = _CQRunner()
    runner = harness.prepare()
    try:
        old = runner.run.handoff_materials
        store = DshRunMaterials(old.root, old.scope_id, {"coordinator"})
        store.actors = old.actors
        runner.run.handoff_materials = store
        ack = _run_lifecycle_to_frozen(runner)
        notices = [
            json.loads(d.text) for _, d in runner.adapter.messages if d.kind == "cq-public-input"
        ]
        assert notices and all(n["run_id"] == runner.run.run_id for n in notices)
        frozen = [n for n in notices if "freeze" in n]
        assert frozen and all(
            n["freeze"]["snapshot_digest"] == ack["snapshot_digest"] for n in frozen
        )
        for notice in notices:
            material_id = notice["material_ref"]["material_id"]
            manifest, _ = store._manifest("runner", material_id)
            content = store.resolve(manifest["recipient_id"], notice["material_ref"])
            assert "cq-2" not in content  # The lifecycle fixture's hidden question.
        assert all("freeze" not in n for n in notices if n["version"].endswith("0001.json"))
    finally:
        harness.cleanup()


def test_late_old_artifact_never_overwrites_new_version_even_after_reload(materials):
    materials.write_output("coord", "scenario-map/scenario-map.json", '{"version":"A"}')
    latest = materials.write_output("coord", "scenario-map/scenario-map.json", '{"version":"B"}')
    target = materials.root.parent / "scenario-map/scenario-map.json"
    before = target.stat().st_mtime_ns
    for store in (materials, DshRunMaterials(materials.root, "run-1", {"coord"})):
        if not store.actors:
            store.actors = materials.actors
        with pytest.raises(MaterialError, match="material_version_stale") as failure:
            store.write_output("coord", "scenario-map/scenario-map.json", '{"version":"A"}')
        assert (
            failure.value.data["current_material_ref"] == latest["runner_receipt"]["material_ref"]
        )
        assert target.read_text() == '{"version":"B"}'
        assert target.stat().st_mtime_ns == before


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_original_can_be_republished_without_reapplying_target(
    materials, damage
):
    content = '{"version":"A"}'
    result = materials.write_output("coord", "scenario-map/scenario-map.json", content)
    ref = result["runner_receipt"]["material_ref"]
    target = materials.root.parent / "scenario-map/scenario-map.json"
    before = target.stat().st_mtime_ns
    snapshot = materials.root / ref["material_id"] / "files/scenario-map.json"
    if damage == "missing":
        snapshot.unlink()
    else:
        snapshot.chmod(0o600)
        snapshot.write_text("broken")
    repaired = materials.write_output("coord", "scenario-map/scenario-map.json", content)[
        "runner_receipt"
    ]
    assert repaired["material_ref"] != ref
    assert repaired["replaces_material_ref"] == ref
    assert materials.resolve("runner", repaired["material_ref"]) == content
    assert target.stat().st_mtime_ns == before
    assert not snapshot.exists() if damage == "missing" else snapshot.read_text() == "broken"


def test_receipt_persistence_failure_after_transfer_does_not_reapply(materials, monkeypatch):
    save = materials._save

    def lose_received_receipt(record):
        if record["kind"] == "artifact" and record["state"] == "received":
            raise OSError("fixture lost receipt persistence")
        save(record)

    with monkeypatch.context() as patch:
        patch.setattr(materials, "_save", lose_received_receipt)
        with pytest.raises(MaterialError, match="material_target_unavailable"):
            materials.write_output("coord", "scenario-map/topology-decision.json", "{}")
    target = materials.root.parent / "scenario-map/topology-decision.json"
    before = target.stat().st_mtime_ns
    ref = materials.artifacts["coord:scenario-map/topology-decision.json"]["material_ref"]
    restored = DshRunMaterials(materials.root, "run-1", {"coord"})
    restored.actors = materials.actors
    receipt = restored.write_output("coord", "scenario-map/topology-decision.json", "{}")[
        "runner_receipt"
    ]
    assert receipt["material_ref"] == ref and receipt["state"] == "received"
    assert target.stat().st_mtime_ns == before


def test_public_original_missing_can_be_corrected_before_dispatch(materials):
    path = materials.root.parent / "competency-questions/public/public-projection-0001.json"
    materials.queue_public_input(path, ["coord"], "digest")
    deliveries = []

    class Adapter:
        def send_message(self, recipient, delivery):
            deliveries.append(delivery)
            return SimpleNamespace(dispatch_id="native-dispatch")

    adapter = Adapter()
    materials.flush_public_inputs(adapter)
    original = next(iter(materials.public_inputs.values()))
    assert "material_source_unavailable" in original["error"]
    assert not deliveries
    path.write_text('{"questions":[]}')
    materials.flush_public_inputs(adapter)
    repaired = next(iter(materials.public_inputs.values()))
    assert repaired["handoff_id"] == original["handoff_id"]
    assert repaired["state"] == "queued" and len(deliveries) == 1
