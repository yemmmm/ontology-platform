from __future__ import annotations

import json
from pathlib import Path

import pytest

from modeling_team.handoff_materials import HandoffMaterials, MaterialError
from modeling_team.runtimes.base import RuntimeDelivery
from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker, mcp_response


@pytest.fixture
def materials(tmp_path):
    sources = tmp_path / "drafts"
    sources.mkdir()
    store = HandoffMaterials(tmp_path / "handoff-materials", "run-one")
    store.register_actor("modeling", {"/agent/work": sources}, {"protocol", "runner"})
    store.register_actor("protocol", {}, {"modeling", "runner"})
    store.register_actor("runner", {}, {"modeling", "protocol"})
    return store, sources


def test_snapshot_is_immutable_and_utf8_pages_lossless(materials):
    store, sources = materials
    content = "a中🙂b" * 5000
    (sources / "candidate.json").write_text(content)
    publication = store.publish("modeling", "protocol", "/agent/work/candidate.json")
    ref = {"material_id": publication["material_id"]}
    (sources / "candidate.json").unlink()
    assert store.resolve("protocol", ref) == content
    pieces, offset = [], 0
    while True:
        page = store.read("protocol", ref["material_id"], offset=offset, max_bytes=3)
        pieces.append(page["content"])
        assert page["offset"] == offset
        offset = page["next_offset"]
        if page["read_complete"]:
            break
    assert "".join(pieces) == content
    assert offset == len(content.encode())
    with pytest.raises(MaterialError, match="material_cursor_invalid"):
        store.read("protocol", ref["material_id"], offset=2)


def test_public_terminal_summary_reference_keeps_original_guard_body(materials, tmp_path):
    store, sources = materials
    complete = "正式总结" * 5000
    (sources / "summary.txt").write_text(complete)
    publication = store.publish("modeling", "runner", "/agent/work/summary.txt")
    broker = TeamTransportBroker(tmp_path / "broker", {("modeling", "protocol")},
                                 materials=store)
    catalog = mcp_response({"method": "tools/list"}, broker=broker, agent_id="modeling")
    schema = next(t["inputSchema"] for t in catalog["tools"] if t["name"] == "report_task_result")
    assert "summary_ref" in schema["properties"] and "body_ref" not in schema["properties"]
    response = mcp_response({"method": "tools/call", "params": {
        "name": "report_task_result", "arguments": {"status": "completed", "summary": "阅读正式总结",
        "summary_ref": {"material_id": publication["material_id"]}}}}, broker=broker, agent_id="modeling")
    assert complete not in response["content"][0]["text"]
    assert broker.results["modeling"].summary == complete


def test_full_directory_listing_subset_and_bound_cursor(materials):
    store, sources = materials
    for index in range(205):
        (sources / f"{index:03}.txt").write_text(str(index))
    publication = store.publish("modeling", "protocol", "/agent/work")
    assert publication["file_count"] == 205 and not publication["list_complete"]
    paths, cursor = [], None
    while True:
        page = store.list("protocol", publication["material_id"], cursor, max_entries=17)
        paths.extend(e["path"] for e in page["entries"])
        cursor = page["next_cursor"]
        if page["list_complete"]:
            break
    assert paths == sorted(p.name for p in sources.iterdir())
    with pytest.raises(MaterialError, match="material_member_required"):
        store.resolve("protocol", {"material_id": publication["material_id"]})
    with pytest.raises(MaterialError, match="material_cursor_invalid"):
        store.list("modeling", publication["material_id"], store.list("protocol", publication["material_id"])["next_cursor"])
    subset = store.publish("modeling", "protocol", "/agent/work", ["002.txt", "010.txt"])
    assert subset["file_count"] == 2


def test_scoped_output_channel_grants_symlinks_and_revocation(materials, tmp_path):
    store, sources = materials
    result = store.write_output("modeling", "notes/x.txt", "draft")
    assert not result["published"]
    published = store.publish("modeling", "protocol", result["source_path"])
    assert store.resolve("protocol", {"material_id": published["material_id"]}) == "draft"
    for path in ["../secret", "/tmp/secret"]:
        with pytest.raises(MaterialError, match="material_path_invalid"):
            store.write_output("modeling", path, "x")
    (sources / "secret").symlink_to(tmp_path / "hidden")
    with pytest.raises(MaterialError, match="material_path_invalid"):
        store.publish("modeling", "protocol", "/agent/work")
    with pytest.raises(MaterialError, match="material_forbidden"):
        store.publish("modeling", "coordinator", result["source_path"])
    store.register_actor("modeling", {"/agent/work": sources}, {"runner"})
    with pytest.raises(MaterialError, match="material_forbidden"):
        store.read("protocol", published["material_id"])
    other = HandoffMaterials(tmp_path / "handoff-materials", "other-run")
    other.register_actor("protocol", {}, set())
    with pytest.raises(MaterialError, match="material_forbidden"):
        other.read("protocol", published["material_id"])


def test_mixed_source_permissions_and_unsupported_media_fail_whole_package(materials):
    store, sources = materials
    secret = sources / "private.txt"
    secret.write_text("hidden")
    store.register_actor("modeling", {"/agent/work": sources, "/agent/work/private.txt": secret},
                         {"protocol", "runner"}, {"/agent/work/private.txt": {"runner"}})
    with pytest.raises(MaterialError, match="material_forbidden"):
        store.publish("modeling", "protocol", "/agent/work")
    assert not list(store.root.glob("material-*"))
    secret.unlink()
    (sources / "binary").write_bytes(b"\xff")
    with pytest.raises(MaterialError, match="material_media_unsupported"):
        store.publish("modeling", "protocol", "/agent/work")
    assert not list(store.root.glob("material-*"))


def test_published_directory_rechecks_narrowed_member_authorization(materials):
    store, sources = materials
    member = sources / "member.txt"
    member.write_text("formerly shared")
    publication = store.publish("modeling", "protocol", "/agent/work")
    store.register_actor("modeling", {"/agent/work": sources, "/agent/work/member.txt": member},
                         {"protocol", "runner"}, {"/agent/work/member.txt": {"runner"}})
    with pytest.raises(MaterialError, match="material_forbidden"):
        store.read("protocol", publication["material_id"], "member.txt")


def test_corruption_is_typed_and_old_package_not_rebuilt(materials):
    store, sources = materials
    (sources / "body").write_text("original")
    result = store.publish("modeling", "protocol", "/agent/work/body")
    package = store.root / result["material_id"]
    (package / "files/body").chmod(0o600)
    (package / "files/body").write_text("changed")
    with pytest.raises(MaterialError, match="material_digest_mismatch"):
        store.resolve("protocol", {"material_id": result["material_id"]})
    (package / "manifest.json").chmod(0o600)
    (package / "manifest.json").write_text("{}")
    with pytest.raises(MaterialError, match="material_digest_mismatch"):
        store.list("protocol", result["material_id"])


def test_body_ref_normalizes_before_validator_and_preserves_reply_slot(materials, tmp_path):
    store, sources = materials
    original = json.dumps({"candidate": "中" * 20000}, ensure_ascii=False)
    (sources / "candidate.json").write_text(original)
    package = store.publish("modeling", "protocol", "/agent/work/candidate.json")
    ref = {"material_id": package["material_id"]}
    observed = []
    broker = TeamTransportBroker(tmp_path / "broker", {("modeling", "protocol"), ("protocol", "modeling")},
                                 materials=store, pre_send_validator=lambda *args: observed.append(args))
    response = mcp_response({"method": "tools/call", "params": {"name": "send_team_message", "arguments": {
        "recipient_id": "protocol", "text": "Review candidate", "body_ref": ref, "expects_reply": True,
    }}}, broker=broker, agent_id="modeling")
    delivery = broker.drain()[0]
    assert delivery.text == original and observed[0][2] == original
    assert "中" * 100 not in response["content"][0]["text"]
    outbound = RuntimeDelivery("modeling", "protocol", "peer", delivery.text,
                               display_text=delivery.display_text, body_ref=ref)
    rendered = json.loads(CodexRuntimeAdapter._delivery_input(outbound)[0]["text"])
    assert rendered["text"] == "Review candidate" and rendered["body_ref"] == ref
    reply = store.write_output("protocol", "reply.json", '{"approved":true}')
    published = store.publish("protocol", "modeling", reply["source_path"])
    with pytest.raises(RoutingError, match="material_member_missing"):
        broker.send("protocol", "modeling", "", reply_to_delivery_id=delivery.delivery_id,
                    body_ref={"material_id": published["material_id"], "path": "absent"})
    corrected = broker.send("protocol", "modeling", "", reply_to_delivery_id=delivery.delivery_id,
                            body_ref={"material_id": published["material_id"]})
    assert corrected.text == '{"approved":true}' and corrected.reply_to_delivery_id == delivery.delivery_id


def test_source_changed_during_copy_preserves_no_package(materials, monkeypatch):
    store, sources = materials
    target = sources / "draft"
    target.write_text("draft")
    original = Path.read_bytes
    count = 0
    def change(path):
        nonlocal count
        data = original(path)
        if path == target:
            count += 1
            if count == 1:
                path.write_text("edited")
        return data
    monkeypatch.setattr(Path, "read_bytes", change)
    with pytest.raises(MaterialError, match="material_source_changed"):
        store.publish("modeling", "protocol", "/agent/work/draft")
    assert not list(store.root.glob("material-*"))
