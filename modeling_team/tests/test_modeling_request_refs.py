"""Complete request references use the real capability/compiler/executor path."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from modeling_team.staged_decisions import platform_content_hash
from modeling_team.staged_batch_write_forwarder import StagedBatchForwardUnknown
from modeling_team.tests.test_direct_execution import _Scope
from modeling_team.tests.test_r30008b_runner_wiring import _socket_request
from modeling_team.tests.test_r30009_runner_wiring import _UnifiedRunner


def _request():
    return {
        "schema_version": "r4-3-025-model-changes/v1",
        "candidate_ref": None,
        "changes": [{
            "change_id": "define-object", "action": "create", "resource_kind": "class",
            "item_id": None, "target_ref": None,
            "fields": {"name": "仪表", "description": "完整说明" * 1800},
        }],
    }


@pytest.fixture
def direct_run(tmp_path):
    submitted = []
    revision = 4

    def submit(batch):
        nonlocal revision
        submitted.append(deepcopy(batch))
        assert batch["mode"] == "apply_atomic"
        before, revision = revision, revision + 1
        return {
            "batch_id": "batch-1", "client_batch_id": batch["client_batch_id"],
            "attempt_id": "attempt-1", "idempotency_key": batch["idempotency_key"],
            "mode": "apply_atomic", "attempt_status": "applied",
            "content_hash": platform_content_hash(batch),
            "workspace": {"before_version": before, "after_version": revision},
            "items": [{
                "client_item_id": item["client_item_id"],
                "resource_outputs": {
                    "resource_id": "class-1",
                    "resource_iri": "http://example.test/class/class-1",
                },
            } for item in batch["items"]],
            "findings": [], "retrieval_indexes": [],
        }

    staged = _UnifiedRunner(tmp_path, forwarder=submit)
    staged.prepare()
    owner = staged.runner
    owner.scope = _Scope()
    owner._competency_questions = False
    owner._modeling_checkpoints = False

    def read(tool, arguments):
        assert tool == "get_modeling_context"
        assert arguments == {"ontology_id": "onto-1"}
        return {"ok": True, "data": {"workspace": {
            "state": "ready", "model_revision": revision,
        }}}

    owner._direct_platform_read = read
    gate = owner.run.root / "candidate-gate/state.json"
    gate.parent.mkdir(parents=True, exist_ok=True)
    owner._atomic_json(gate, {"state": "open"})
    try:
        yield owner, submitted
    finally:
        owner.scope = None
        owner._direct_model_executor = None
        staged.cleanup()


def _publish(owner, content, *, recipient="runner", publisher="modeling", directory=False):
    store = owner.run.handoff_materials
    source = store.write_output(publisher, "requests/change.json", content)["source_path"]
    package = store.publish(publisher, recipient, source.rsplit("/", 1)[0] if directory else source)
    ref = {"material_id": package["material_id"]}
    if directory:
        ref["path"] = "change.json"
    return ref


def _call(owner, **arguments):
    endpoint = owner.acceptance.capability_endpoint("modeling")
    response = endpoint.handle({
        "id": 1, "token": endpoint.token, "method": "tools/call",
        "params": {"name": "modeling_submit_model_changes", "arguments": {
            "modeling_id": "modeling", **arguments,
        }},
    })
    assert "error" not in response, response
    return response["result"]["structuredContent"]["data"]


@pytest.mark.parametrize("directory", [False, True])
def test_request_ref_applies_complete_published_bytes_and_deduplicates_inline(direct_run, directory):
    owner, submitted = direct_run
    request = _request()
    ref = _publish(owner, json.dumps(request, ensure_ascii=False), directory=directory)
    # Editing/deleting the author's source must not change its published request.
    source = owner.run.handoff_materials.actors["modeling"]["output"] / "requests/change.json"
    source.write_text('{"changes":[]}')
    source.unlink()

    result = _call(owner, request_ref=ref)

    assert result["status"] == "completed", [(e["code"], e["message"]) for e in result["errors"]]
    assert len(submitted) == 1
    item = submitted[0]["items"][0]
    assert item["command_kind"] == "create_class"
    assert item["payload"]["name"] == "仪表"
    assert item["payload"]["description"] == "完整说明" * 1800
    assert json.loads((owner.run.root / result["submission_ref"]).read_text()) == request
    repeated = _call(owner, request=request)
    assert repeated["status"] == "completed"
    assert repeated["submission_digest"] == result["submission_digest"]
    assert len(submitted) == 1


@pytest.mark.parametrize("content", ['{"broken":', '[]', 'null'])
def test_bad_referenced_json_is_recoverable_without_a_write(direct_run, content):
    owner, submitted = direct_run
    result = _call(owner, request_ref=_publish(owner, content))
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "model_change_request_invalid"
    assert result["errors"][0]["path"] == "/request_ref"
    assert result["errors"][0]["retryable"] is True
    assert submitted == []
    corrected = _call(owner, request_ref=_publish(owner, json.dumps(_request())))
    assert corrected["status"] == "completed", corrected["errors"]


@pytest.mark.parametrize("arguments", [{}, {"request": _request(), "request_ref": {
    "material_id": "material-unused",
}}])
def test_exactly_one_request_source_is_required_without_an_opaque_error(direct_run, arguments):
    owner, submitted = direct_run
    result = _call(owner, **arguments)
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "model_change_request_invalid"
    assert "exactly one" in result["errors"][0]["message"]
    assert submitted == []


@pytest.mark.parametrize("publisher,recipient", [("modeling", "coordinator"), ("coordinator", "runner")])
def test_request_reference_cannot_reuse_another_role_or_channel(direct_run, publisher, recipient):
    owner, submitted = direct_run
    ref = _publish(owner, json.dumps(_request()), publisher=publisher, recipient=recipient)
    result = _call(owner, request_ref=ref)
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "material_forbidden"
    assert result["errors"][0]["path"] == "/request_ref"
    assert submitted == []


def test_changed_snapshot_is_rejected_before_platform_execution(direct_run):
    owner, submitted = direct_run
    ref = _publish(owner, json.dumps(_request()))
    snapshot = owner.run.handoff_materials.root / ref["material_id"] / "files/change.json"
    snapshot.chmod(0o600)
    snapshot.write_text(json.dumps(_request()).replace("define-object", "changed-object"))
    result = _call(owner, request_ref=ref)
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "material_digest_mismatch"
    assert submitted == []


def test_request_reference_keeps_compiler_field_errors_and_freeze_gate(direct_run):
    owner, submitted = direct_run
    wrong = _request()
    wrong["changes"][0]["fields"]["item_id"] = None
    result = _call(owner, request_ref=_publish(owner, json.dumps(wrong)))
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "unsupported_change_field"
    assert result["errors"][0]["path"] == "/changes/0/fields"
    owner._competency_questions = True
    owner._cq_freeze = None
    result = _call(owner, request_ref=_publish(owner, json.dumps(_request())))
    assert result["errors"][0]["code"] == "cq_freeze_pending"
    assert submitted == []


def test_missing_reference_and_missing_directory_member_can_be_corrected(direct_run):
    owner, submitted = direct_run
    missing = _call(owner, request_ref={"material_id": "material-missing"})
    assert missing["status"] == "not_written"
    assert missing["errors"][0]["code"] == "material_source_unavailable"
    ref = _publish(owner, json.dumps(_request()), directory=True)
    ambiguous = _call(owner, request_ref={"material_id": ref["material_id"]})
    assert ambiguous["errors"][0]["code"] == "material_member_required"
    assert submitted == []
    assert _call(owner, request_ref=ref)["status"] == "completed"


def test_switching_input_source_does_not_bypass_an_unknown_write(direct_run):
    owner, submitted = direct_run

    def unknown(batch):
        submitted.append(deepcopy(batch))
        raise StagedBatchForwardUnknown("connection lost after dispatch")

    owner.staged_batch_forwarder = unknown
    request = _request()
    first = _call(owner, request_ref=_publish(owner, json.dumps(request)))
    assert first["status"] == "uncertain"
    repeated = _call(owner, request=request)
    assert repeated["status"] == "uncertain"
    assert repeated["submission_digest"] == first["submission_digest"]
    assert len(submitted) == 1


def test_reference_is_usable_through_the_actual_mcp_socket(direct_run):
    owner, submitted = direct_run
    ref = _publish(owner, json.dumps(_request()))
    endpoint = owner.acceptance.capability_endpoint("modeling")
    endpoint.start()
    try:
        catalog = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        tool = next(t for t in catalog["result"]["tools"]
                    if t["name"] == "modeling_submit_model_changes")
        assert tool["inputSchema"]["properties"]["request_ref"]["required"] == ["material_id"]
        response = _socket_request(
            endpoint.socket_path, endpoint.token, "tools/call",
            name="modeling_submit_model_changes",
            arguments={"modeling_id": "modeling", "request_ref": ref},
        )
        assert response["result"]["structuredContent"]["data"]["status"] == "completed"
        assert submitted[0]["items"][0]["payload"]["name"] == "仪表"
    finally:
        endpoint.stop()


@pytest.mark.parametrize("duplicate", [False, True])
def test_rejected_request_can_be_corrected_by_explicit_small_edits_without_retranscription(
    direct_run, duplicate,
):
    owner, submitted = direct_run
    intended = _request()
    wrong = deepcopy(intended)
    change = wrong["changes"][0]
    for key in ("item_id", "target_ref", "resource_kind"):
        change["fields"][key] = change[key] if duplicate else change.pop(key)

    rejected = _call(owner, request=wrong)
    assert rejected["status"] == "not_written"
    assert submitted == []
    correction = rejected["correction"]
    ref = correction["request_ref"]
    # The program captures exactly the rejected input, not a silent repair.
    assert json.loads(owner.run.handoff_materials.resolve("modeling", ref)) == wrong
    assert correction["suggested_edits"]
    repeated = _call(owner, request=wrong)
    assert repeated["correction"]["request_ref"] == ref
    unchanged = _call(owner, request_ref=ref)
    assert unchanged["status"] == "not_written" and not submitted

    fixed = _call(owner, request_ref=ref, request_edits=correction["suggested_edits"])
    assert fixed["status"] == "completed", fixed["errors"]
    assert json.loads((owner.run.root / fixed["submission_ref"]).read_text()) == intended
    assert submitted[0]["items"][0]["payload"]["description"] == intended["changes"][0]["fields"]["description"]
    assert json.loads(owner.run.handoff_materials.resolve("modeling", ref)) == wrong
    # Corrected contents, inline and reference input must share execution identity.
    same = _call(owner, request=intended)
    assert same["submission_digest"] == fixed["submission_digest"]
    assert len(submitted) == 1


def test_conflicting_control_values_are_never_chosen_by_the_program(direct_run):
    owner, submitted = direct_run
    wrong = _request()
    wrong["changes"][0]["fields"]["item_id"] = "a-different-candidate"
    rejected = _call(owner, request=wrong)
    correction = rejected["correction"]
    assert correction["suggested_edits"] == []
    assert not submitted
    fixed = _call(owner, request_ref=correction["request_ref"], request_edits=[{
        "op": "remove", "path": "/changes/0/fields/item_id",
    }])
    assert fixed["status"] == "completed"


def test_field_contract_and_explicit_edits_preserve_unedited_business_content(direct_run):
    owner, submitted = direct_run
    wrong = _request()
    wrong["changes"][0]["fields"]["source"] = "来源 / 定义1"
    rejected = _call(owner, request=wrong)
    correction = rejected["correction"]
    assert correction["suggested_edits"] == []  # No automatic deletion of source meaning.
    contract = correction["field_contracts"][0]
    assert contract["path"] == "/changes/0/fields"
    assert "name" in contract["allowed_fields"] and "source" not in contract["allowed_fields"]
    fixed = _call(owner, request_ref=correction["request_ref"], request_edits=[
        {"op": "move", "from": "/changes/0/fields/source",
         "path": "/changes/0/fields/semantic_definition"},
        {"op": "replace", "path": "/changes/0/fields/semantic_definition",
         "value": {"business_meaning": "Agent explicitly supplied meaning", "unknowns": ["未知"]}},
        {"op": "add", "path": "/changes/0/fields/aliases", "value": ["仪表名称"]},
    ])
    assert fixed["status"] == "completed", fixed["errors"]
    payload = submitted[0]["items"][0]["payload"]
    assert payload["description"] == wrong["changes"][0]["fields"]["description"]
    assert payload["aliases"] == ["仪表名称"]
    assert payload["semantic_definition"]["unknowns"] == ["未知"]


@pytest.mark.parametrize("edits", [
    [], [{"op": "guess", "path": "/changes/0/item_id"}],
    [{"op": "remove", "path": "/changes/0/absent"}],
    [{"op": "remove", "path": "/changes/-1"}],
    [{"op": "remove", "path": "/changes/00"}],
    [{"op": "remove", "path": "/changes/0/fields/~2invalid"}],
    [{"op": "add", "path": "/changes/0/item_id"}],
    [{"op": "replace", "path": "/changes/0/absent", "value": None}],
    [{"op": "move", "from": "/changes/0", "path": "/changes/0/fields/nested"}],
    [{"op": "replace", "path": "", "value": {}}],
    [{"op": "remove", "path": "/changes/0/fields/name"},
     {"op": "remove", "path": "/changes/9"}],
])
def test_invalid_edits_are_recoverable_atomic_and_do_not_mutate_material(direct_run, edits):
    owner, submitted = direct_run
    original = _request()
    ref = _publish(owner, json.dumps(original))
    result = _call(owner, request_ref=ref, request_edits=edits)
    assert result["status"] == "not_written"
    assert result["errors"][0]["code"] == "request_edits_invalid"
    assert result["errors"][0]["path"].startswith("/request_edits")
    assert not submitted
    assert json.loads(owner.run.handoff_materials.resolve("modeling", ref)) == original


def test_edits_require_reference_and_keep_original_material_authorization(direct_run):
    owner, submitted = direct_run
    edits = [{"op": "remove", "path": "/changes/0/fields/name"}]
    inline = _call(owner, request=_request(), request_edits=edits)
    assert inline["errors"][0]["code"] == "request_edits_invalid"
    foreign = _publish(owner, json.dumps(_request()), recipient="coordinator")
    refused = _call(owner, request_ref=foreign, request_edits=edits)
    assert refused["errors"][0]["code"] == "material_forbidden"
    assert not submitted


def test_edited_input_cannot_bypass_the_original_unknown_write(direct_run):
    owner, submitted = direct_run

    def unknown(batch):
        submitted.append(deepcopy(batch))
        raise StagedBatchForwardUnknown("lost response")

    owner.staged_batch_forwarder = unknown
    intended = _request()
    assert _call(owner, request=intended)["status"] == "uncertain"
    wrong = deepcopy(intended)
    wrong["changes"][0]["fields"]["item_id"] = wrong["changes"][0].pop("item_id")
    rejected = _call(owner, request_ref=_publish(owner, json.dumps(wrong)))
    correction = rejected["correction"]
    retried = _call(owner, request_ref=correction["request_ref"],
                    request_edits=correction["suggested_edits"])
    assert retried["status"] == "uncertain"
    assert len(submitted) == 1


def test_edit_schema_and_recovery_round_trip_through_actual_mcp_socket(direct_run):
    owner, submitted = direct_run
    wrong = _request()
    wrong["changes"][0]["fields"]["item_id"] = wrong["changes"][0].pop("item_id")
    endpoint = owner.acceptance.capability_endpoint("modeling")
    endpoint.start()
    try:
        listing = _socket_request(endpoint.socket_path, endpoint.token, "tools/list")
        tool = next(t for t in listing["result"]["tools"]
                    if t["name"] == "modeling_submit_model_changes")
        assert "request_edits" in tool["inputSchema"]["properties"]
        first = _socket_request(endpoint.socket_path, endpoint.token, "tools/call",
            name="modeling_submit_model_changes",
            arguments={"modeling_id": "modeling", "request": wrong})
        correction = first["result"]["structuredContent"]["data"]["correction"]
        fixed = _socket_request(endpoint.socket_path, endpoint.token, "tools/call",
            name="modeling_submit_model_changes", arguments={"modeling_id": "modeling",
                "request_ref": correction["request_ref"],
                "request_edits": correction["suggested_edits"]})
        assert fixed["result"]["structuredContent"]["data"]["status"] == "completed"
        assert len(submitted) == 1
    finally:
        endpoint.stop()


def test_second_rejection_references_the_edited_body_not_the_old_base(direct_run):
    owner, submitted = direct_run
    wrong = _request()
    wrong["changes"][0]["fields"]["item_id"] = wrong["changes"][0].pop("item_id")
    wrong["changes"][0]["fields"]["source"] = "source retained for Agent disposition"
    first = _call(owner, request=wrong)["correction"]
    second = _call(owner, request_ref=first["request_ref"], request_edits=first["suggested_edits"])
    assert second["status"] == "not_written" and not submitted
    corrected = second["correction"]
    assert corrected["request_ref"] != first["request_ref"]
    body = json.loads(owner.run.handoff_materials.resolve("modeling", corrected["request_ref"]))
    assert "item_id" in body["changes"][0]
    assert body["changes"][0]["fields"]["source"] == wrong["changes"][0]["fields"]["source"]
    final = _call(owner, request_ref=corrected["request_ref"], request_edits=[{
        "op": "remove", "path": "/changes/0/fields/source",
    }])
    assert final["status"] == "completed"
    assert len(submitted) == 1


def test_edits_support_escaped_keys_and_sequential_array_operations():
    from modeling_team.direct_submission import apply_request_edits
    original = {"a/b": {"~key": ["keep", "move"]}}
    result = apply_request_edits(original, [
        {"op": "add", "path": "/a~1b/~0key/-", "value": "last"},
        {"op": "move", "from": "/a~1b/~0key/1", "path": "/a~1b/~0key/0"},
        {"op": "replace", "path": "/a~1b/~0key/2", "value": "updated"},
        {"op": "remove", "path": "/a~1b/~0key/1"},
    ])
    assert result == {"a/b": {"~key": ["move", "updated"]}}
    assert original == {"a/b": {"~key": ["keep", "move"]}}


def _retained_misnested_requests():
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/modeling-misnested-requests.json").read_text())


@pytest.mark.parametrize("case", _retained_misnested_requests(), ids=lambda c: str(c["sources"][0]))
def test_actual_historical_invalid_calls_compile_after_explicit_selected_edits(case):
    from modeling_team.direct_modeling import (
        ModelChangeCompilationError, compile_model_changes, model_change_correction,
    )
    from modeling_team.direct_submission import apply_request_edits
    original = case["request"]

    def compile_request(request):
        return compile_model_changes(request, candidate=None,
            ontology_by_item={c.get("item_id") or c.get("change_id"): "onto-replay"
                              for c in request["changes"]}, resolve_binding=lambda _: None)

    with pytest.raises(ModelChangeCompilationError):
        compile_request(original)
    correction = model_change_correction(original)
    fixed = apply_request_edits(original, correction["suggested_edits"])
    batches, _ = compile_request(fixed)
    assert sum(len(b["items"]) for b in batches) == len(original["changes"])
    for before, after in zip(original["changes"], fixed["changes"], strict=True):
        for key, value in before["fields"].items():
            if key not in {"change_id", "action", "resource_kind", "item_id", "target_ref"}:
                assert after["fields"][key] == value
