"""Independent R4.0-001 contract acceptance; never starts semantic modeling."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.mcp.runtime import set_runtime_principal
from app.mcp.server import mcp
from app.repositories.models import OntologyModel
from app.security.auth import resolve_api_key
from subject_access_support import create_api_key


def _headers(env, kind="p1_read_key"):
    return {"Authorization": "Bearer " + env[kind]}


def _submission(env, **overrides):
    body = {
        "feedback_id": str(uuid4()),
        "query_request": {
            "project_id": env["ids"]["p1"],
            "scope_mode": "project",
            "query": "返修责任如何判断",
            "search_mode": "lexical",
            "depth": 0,
            "context_limit": 0,
            "resource_types": ["concept"],
            "limit": 5,
        },
        "reasons": ["incomplete", "other"],
        "description": " 原话：未读完后续页，不能判断模型缺失。\n需要保留旧修订。 ",
        "result_snapshot": {
            "scope": {"project_id": env["ids"]["p1"], "model_revision": 12},
            "primary_matches": [],
            "matches_page": {"returned": 0, "truncated": True},
            "warnings": ["retrieval degraded"],
        },
        "snapshot_complete": False,
    }
    body.update(overrides)
    return body


def _post(env, body, key="p1_read_key"):
    return env["client"].post("/api/semantic/feedback", json=body, headers=_headers(env, key))


def _detail(env, feedback_id, key="p1_admin_key"):
    return env["client"].get(
        f"/api/semantic/feedback/{feedback_id}", headers=_headers(env, key)
    )


def _mcp(env, monkeypatch, name, args, key="p1_read_key"):
    with env["factory"]() as db:
        principal = resolve_api_key(db, env[key])
    assert principal is not None
    monkeypatch.setattr("app.mcp.runtime.get_resources", lambda: (env["factory"], None, None))
    set_runtime_principal(principal)
    try:
        tool = mcp._tool_manager.get_tool(name)  # noqa: SLF001 - registered runtime tool
        assert tool is not None
        return tool.fn(**args)
    finally:
        set_runtime_principal(None)


def test_read_submission_preserves_report_and_revision_without_workspace(r008_client):
    env = r008_client
    oid = str(uuid4())
    with env["factory"]() as db:
        db.add(OntologyModel(id=oid, project_id=env["ids"]["p1"], name="Current", model_revision=19))
        db.commit()
    body = _submission(env)
    body["result_snapshot"]["scope"]["ontologies"] = [{"ontology_id": oid, "model_revision": 12}]
    reply = _post(env, body)
    assert reply.status_code in {200, 201}, reply.text
    receipt = reply.json()
    assert receipt["feedback_id"] == body["feedback_id"]
    assert receipt["status"] == "received"
    assert receipt["received_at"]
    readback = _detail(env, body["feedback_id"])
    assert readback.status_code == 200, readback.text
    saved = readback.json()["submission"]
    assert saved["description"] == body["description"]
    assert saved["query_request"]["query"] == body["query_request"]["query"]
    assert saved["query_request"]["limit"] == 5
    assert saved["query_request"]["resource_types"] == ["concept"]
    assert saved["result_snapshot"] == body["result_snapshot"]
    assert saved["snapshot_complete"] is False
    with env["factory"]() as db:
        assert db.get(OntologyModel, oid).model_revision == 19


def test_missing_snapshot_and_multiexpression_pagination_are_collectable(r008_client):
    env = r008_client
    body = _submission(env, result_snapshot=None)
    body["query_request"].pop("query")
    body["query_request"].update(queries=["责任", "保修期限"], match_cursor="reported-old-cursor")
    reply = _post(env, body)
    assert reply.status_code in {200, 201}, reply.text
    saved = _detail(env, body["feedback_id"]).json()["submission"]
    assert saved["query_request"]["queries"] == ["责任", "保修期限"]
    assert saved["query_request"]["match_cursor"] == "reported-old-cursor"
    assert saved["result_snapshot"] is None


def test_utf8_snapshot_oversize_rejected_then_same_id_can_retry(r008_client):
    env = r008_client
    body = _submission(env, result_snapshot={"reported": "中" * 90000})
    reply = _post(env, body)
    assert reply.status_code == 413, reply.text
    assert "snapshot" in reply.text.lower()
    body["result_snapshot"] = {"reported": "仅保存相关窗口"}
    assert _post(env, body).status_code in {200, 201}


@pytest.mark.parametrize("changes", [
    {"reasons": []}, {"reasons": ["invented"]}, {"description": ""},
    {"description": "a" * 65537},
])
def test_invalid_observation_has_recoverable_rejection(r008_client, changes):
    reply = _post(r008_client, _submission(r008_client, **changes))
    assert reply.status_code == 422, reply.text


def test_same_identity_retry_is_idempotent_different_body_and_subject_conflict(r008_client):
    env = r008_client
    body = _submission(env)
    first = _post(env, body)
    assert first.status_code in {200, 201}, first.text
    again = _post(env, deepcopy(body))
    assert again.status_code in {200, 201}
    assert again.json() == first.json()
    changed = deepcopy(body)
    changed["description"] = "不同正文"
    assert _post(env, changed).status_code == 409
    with env["factory"]() as db:
        _, other_key = create_api_key(db, name="other-reader", project_id=env["ids"]["p1"], scopes=["read"])
    reply = env["client"].post("/api/semantic/feedback", json=body,
                               headers={"Authorization": "Bearer " + other_key})
    assert reply.status_code in {403, 409}
    assert body["description"] not in reply.text
    assert first.json()["received_at"] not in reply.text


def test_internal_reads_require_admin_and_feedback_owner_scope(r008_client):
    env = r008_client
    body = _submission(env)
    assert _post(env, body).status_code in {200, 201}
    assert _detail(env, body["feedback_id"], "p1_read_key").status_code == 403
    assert env["client"].get("/api/semantic/feedback", params={"project_id": env["ids"]["p1"]},
                             headers=_headers(env)).status_code == 403
    other = _submission(env)
    other["query_request"]["project_id"] = env["ids"]["p2"]
    assert _post(env, other).status_code == 403
    assert _post(env, other, "org_key").status_code in {200, 201}
    denied = _detail(env, other["feedback_id"])
    assert denied.status_code in {403, 404}
    assert other["description"] not in denied.text
    denied = env["client"].post(f"/api/semantic/feedback/{other['feedback_id']}/resolution",
                                json={}, headers=_headers(env, "p1_admin_key"))
    assert denied.status_code in {403, 404}, denied.text


def test_mcp_submit_and_get_use_runtime_read_admin_and_shared_storage(r008_client, monkeypatch):
    env = r008_client
    body = _submission(env)
    reply = _mcp(env, monkeypatch, "submit_semantic_feedback", body)
    assert reply["ok"], reply
    assert reply["data"]["status"] == "received"
    rest = _post(env, body)
    assert rest.status_code in {200, 201}, rest.text
    assert rest.json() == reply["data"]
    denied = _mcp(env, monkeypatch, "get_semantic_feedback", {"feedback_id": body["feedback_id"]})
    assert not denied["ok"]
    assert body["description"] not in str(denied)
    detail = _mcp(env, monkeypatch, "get_semantic_feedback", {"feedback_id": body["feedback_id"]}, "p1_admin_key")
    assert detail["ok"], detail
    assert detail["data"] == _detail(env, body["feedback_id"]).json()


def test_explicit_foreign_ontology_scope_rejected_without_resource_detail(r008_client):
    env = r008_client
    oid = str(uuid4())
    with env["factory"]() as db:
        db.add(OntologyModel(id=oid, project_id=env["ids"]["p2"], name="PRIVATE-ONTOLOGY"))
        db.commit()
    body = _submission(env)
    body["query_request"].update(scope_mode="ontologies", ontology_ids=[oid])
    denied = _post(env, body)
    assert denied.status_code == 403, denied.text
    assert "PRIVATE-ONTOLOGY" not in denied.text


def test_mcp_conflict_oversize_and_project_denial_match_rest(r008_client, monkeypatch):
    env = r008_client
    body = _submission(env)
    assert _post(env, body).status_code in {200, 201}
    body["description"] = "new conflicting observation"
    conflict = _mcp(env, monkeypatch, "submit_semantic_feedback", body)
    assert not conflict["ok"]
    assert conflict["error_code"] == "feedback_identity_conflict"
    big = _submission(env, result_snapshot={"reported": "中" * 90000})
    rest = _post(env, big)
    assert rest.status_code == 413
    mcp_reply = _mcp(env, monkeypatch, "submit_semantic_feedback", big)
    assert not mcp_reply["ok"]
    assert "snapshot" in mcp_reply["error_code"]
    wrong = _submission(env)
    wrong["query_request"]["project_id"] = env["ids"]["p2"]
    denied = _mcp(env, monkeypatch, "submit_semantic_feedback", wrong)
    assert not denied["ok"]
    assert wrong["description"] not in str(denied)


def test_optional_omission_has_same_retry_identity_across_rest_mcp(r008_client, monkeypatch):
    env = r008_client
    body = _submission(env)
    body.pop("result_snapshot")
    body.pop("snapshot_complete")
    first = _post(env, body)
    assert first.status_code in {200, 201}
    reply = _mcp(env, monkeypatch, "submit_semantic_feedback", body)
    assert reply["ok"], reply
    assert reply["data"] == first.json()


def test_mcp_resolution_appends_shared_history_and_rejects_read_caller(r008_client, monkeypatch):
    env = r008_client
    body = _submission(env)
    assert _post(env, body).status_code in {200, 201}
    args = {"feedback_id": body["feedback_id"], "resolution": {
        "outcome": "unresolved", "diagnosis": "consumer_understanding",
        "explanation": "需要核对消费方解释；暂不认定模型缺失"}}
    assert not _mcp(env, monkeypatch, "record_semantic_feedback_resolution", args)["ok"]
    saved = _mcp(env, monkeypatch, "record_semantic_feedback_resolution", args, "p1_admin_key")
    assert saved["ok"], saved
    readback = _detail(env, body["feedback_id"]).json()
    assert readback["resolution_history"] == [saved["data"]]


def _resolve(env, fid, body, key="p1_admin_key"):
    return env["client"].post(f"/api/semantic/feedback/{fid}/resolution",
                               json=body, headers=_headers(env, key))


def test_resolution_append_keeps_original_and_rejects_unsupported_closed_outcome(r008_client):
    env = r008_client
    body = _submission(env)
    assert _post(env, body).status_code in {200, 201}
    fid = body["feedback_id"]
    for outcome, diagnosis in [("unresolved", "retrieval"), ("needs_clarification", "unknown")]:
        reply = _resolve(env, fid, {"outcome": outcome, "diagnosis": diagnosis,
                                    "explanation": "分页或业务含义尚待确认"})
        assert reply.status_code in {200, 201}, reply.text
    assert _resolve(env, fid, {"outcome": "resolved", "explanation": "仅修复者自测通过"}).status_code == 422
    assert _resolve(env, fid, {"outcome": "no_change_needed", "explanation": "没有证据"}).status_code == 422
    saved = _detail(env, fid).json()
    assert saved["submission"] == body
    history = saved["resolution_history"]
    assert [item["outcome"] for item in history] == ["unresolved", "needs_clarification"]
    assert len({item["resolution_id"] for item in history}) == 2
    assert all(item["recorded_by"] and item["recorded_at"] for item in history)


def test_closed_resolution_requires_current_same_scope_and_independent_reference(r008_client):
    env = r008_client
    oid = str(uuid4())
    with env["factory"]() as db:
        db.add(OntologyModel(id=oid, project_id=env["ids"]["p1"], name="Current", model_revision=19))
        db.commit()
    body = _submission(env)
    body["query_request"].update(scope_mode="ontologies", ontology_ids=[oid])
    assert _post(env, body).status_code in {200, 201}
    verification = {"project_id": env["ids"]["p1"], "model_revisions": {oid: 19},
                    "readback_references": ["test://readback-receipt"]}
    payload = {"outcome": "resolved", "explanation": "结构验证案例，非真实语义结论",
               "verification": verification}
    assert _resolve(env, body["feedback_id"], payload).status_code == 422
    verification["independent_validation_reference"] = "test://independent-record"
    verification["model_revisions"][oid] = 12
    assert _resolve(env, body["feedback_id"], payload).status_code == 409
    verification["model_revisions"][oid] = 19
    verification["project_id"] = env["ids"]["p2"]
    assert _resolve(env, body["feedback_id"], payload).status_code == 403
    verification["project_id"] = env["ids"]["p1"]
    closed = _resolve(env, body["feedback_id"], payload)
    assert closed.status_code in {200, 201}, closed.text
    with env["factory"]() as db:
        db.get(OntologyModel, oid).model_revision = 20
        db.commit()
    saved = _detail(env, body["feedback_id"]).json()
    assert saved["submission"] == body
    assert saved["resolution_history"][0]["verification"]["model_revisions"] == {oid: 19}


def test_pending_pagination_is_stable_including_latest_open_outcomes(r008_client, monkeypatch):
    env = r008_client
    bodies = [_submission(env) for _ in range(4)]
    for body in bodies:
        assert _post(env, body).status_code in {200, 201}
    for body, outcome in zip(bodies[1:], ["unresolved", "needs_clarification", "unresolved"]):
        assert _resolve(env, body["feedback_id"], {"outcome": outcome, "explanation": "等待定位"}).status_code in {200, 201}
    seen = []
    cursor = None
    while True:
        args = {"project_id": env["ids"]["p1"], "pending_only": True, "limit": 1}
        if cursor:
            args["cursor"] = cursor
        rest = env["client"].get("/api/semantic/feedback", params=args,
                                   headers=_headers(env, "p1_admin_key"))
        assert rest.status_code == 200, rest.text
        page = rest.json()
        remote = _mcp(env, monkeypatch, "list_semantic_feedback", args, "p1_admin_key")
        assert remote["ok"] and remote["data"] == page
        seen.extend(item["feedback_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            assert cursor is None
            break
        assert cursor and len(seen) <= len(bodies)
    assert seen == [body["feedback_id"] for body in bodies]
    oid = str(uuid4())
    with env["factory"]() as db:
        db.add(OntologyModel(id=oid, project_id=env["ids"]["p1"], name="Current", model_revision=1))
        db.commit()
    no_change = {"outcome": "no_change_needed", "explanation": "结构测试；已取得相关页",
                 "verification": {"project_id": env["ids"]["p1"], "model_revisions": {oid: 1},
                                  "readback_references": ["test://current-page"]}}
    assert _resolve(env, bodies[-1]["feedback_id"], no_change).status_code in {200, 201}
    page = env["client"].get("/api/semantic/feedback", params={"project_id": env["ids"]["p1"]},
                               headers=_headers(env, "p1_admin_key")).json()
    assert [item["feedback_id"] for item in page["items"]] == seen[:-1]
    all_records = env["client"].get("/api/semantic/feedback", params={
        "project_id": env["ids"]["p1"], "pending_only": False},
        headers=_headers(env, "p1_admin_key")).json()
    assert [item["feedback_id"] for item in all_records["items"]] == seen


def test_029_adapter_exports_selected_public_observation_and_revokes_internal_key(r008_client, monkeypatch):
    from modeling_team.incremental import IncrementalError, read_public_feedback

    env = r008_client
    body = _submission(env, result_snapshot={"hidden_answer": "PRIVATE-SNAPSHOT"})
    assert _post(env, body).status_code in {200, 201}
    assert _resolve(env, body["feedback_id"], {"outcome": "unresolved", "explanation": "PRIVATE-HISTORY"}).status_code in {200, 201}
    revoked = []
    monkeypatch.setattr("modeling_team.__main__._bootstrap_helpers", lambda root: (
        lambda: (env["p1_admin_key"], "temporary-key-id"), revoked.append))

    def transport(base, method, path, payload, key):
        assert method == "GET"
        assert payload is None
        result = env["client"].get(path, headers={"Authorization": "Bearer " + key})
        return result.status_code, result.json()

    monkeypatch.setattr("modeling_team.platform_scope._http", transport)
    projection = read_public_feedback(Path.cwd(), "http://testserver", env["ids"]["p1"], body["feedback_id"], [])
    assert set(projection) == {"project_id", "feedback_id", "observation", "status"}
    assert body["description"] == json.loads(projection["observation"])["description"]
    assert "Client observation" in projection["observation"]
    assert "PRIVATE-SNAPSHOT" not in str(projection)
    assert "PRIVATE-HISTORY" not in str(projection)
    assert revoked == ["temporary-key-id"]
    with pytest.raises(IncrementalError):
        read_public_feedback(Path.cwd(), "http://testserver", env["ids"]["p2"], body["feedback_id"], [])
    assert revoked == ["temporary-key-id", "temporary-key-id"]


def test_029_adapter_does_not_expand_explicit_authorized_ontology_scope(r008_client, monkeypatch):
    from modeling_team.incremental import IncrementalError, read_public_feedback

    env = r008_client
    oid = str(uuid4())
    with env["factory"]() as db:
        db.add(OntologyModel(id=oid, project_id=env["ids"]["p1"], name="Owned"))
        db.commit()
    body = _submission(env)
    body["query_request"].update(scope_mode="ontologies", ontology_ids=[oid])
    assert _post(env, body).status_code in {200, 201}
    revoked = []
    monkeypatch.setattr("modeling_team.__main__._bootstrap_helpers", lambda root: (
        lambda: (env["p1_admin_key"], "temporary"), revoked.append))

    def transport(base, method, path, payload, key):
        response = env["client"].get(path, headers={"Authorization": "Bearer " + key})
        return response.status_code, response.json()

    monkeypatch.setattr("modeling_team.platform_scope._http", transport)
    with pytest.raises(IncrementalError, match="authorized model scope"):
        read_public_feedback(Path.cwd(), "http://testserver", env["ids"]["p1"], body["feedback_id"], ["another-model"])
    assert revoked == ["temporary"]


def test_029_default_preparation_reads_saved_selected_feedback_without_launch(r008_client, monkeypatch, tmp_path):
    from modeling_team.incremental import prepare_incremental

    env = r008_client
    origin = Path(__file__).resolve().parents[2]
    for folder in ("tasks", "profiles", "agent-packages", "skills", "references", "model-profiles"):
        shutil.copytree(origin / "modeling_team" / folder, tmp_path / "modeling_team" / folder)
    source = tmp_path / "approved/business.md"
    source.parent.mkdir()
    source.write_text("Bounded public business source, no hidden questions.")
    selected = _submission(env, result_snapshot={"private_answer": "PRIVATE-SNAPSHOT"})
    unselected = _submission(env, description="UNSELECTED-OBSERVATION")
    for body in (selected, unselected):
        assert _post(env, body).status_code in {200, 201}
    revoked = []
    monkeypatch.setattr("modeling_team.__main__._bootstrap_helpers", lambda root: (
        lambda: (env["p1_admin_key"], "temporary"), revoked.append))

    def transport(base, method, path, payload, key):
        response = env["client"].get(path, headers={"Authorization": "Bearer " + key})
        return response.status_code, response.json()

    monkeypatch.setattr("modeling_team.platform_scope._http", transport)
    request = {"request_id": str(uuid4()), "project_id": env["ids"]["p1"],
               "ontology_ids": ["bounded-current-model"], "objective": "Inspect selected public observation",
               "approved_sources": [{"path": "approved/business.md", "source_reference": "test-authorized-public-source",
                                     "valid_at": "2026-10-12"}],
               "profile": "modeling_team/profiles/r3-0-011-competency-question.yaml",
               "model_profile": "openai-sol-medium", "authorization_reference": "controlled-test-only",
               "valid_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
               "production_start_limit": 1, "acceptance_scope": "selected observation only",
               "feedback_ids": [selected["feedback_id"]]}
    result = prepare_incremental(request, repository_root=tmp_path, scope_probe=lambda _: {"model_revision": 19})
    assert result["status"] == "prepared"
    assert result["semantic_start"] == "not_observed"
    feedback = tmp_path / Path(result["config"]).parent / "public-feedback.json"
    saved = json.loads(feedback.read_text())["feedback"]
    assert [row["feedback_id"] for row in saved] == [selected["feedback_id"]]
    assert "PRIVATE-SNAPSHOT" not in feedback.read_text()
    assert "UNSELECTED-OBSERVATION" not in feedback.read_text()
    assert revoked == ["temporary"]


def test_stopped_team_closed_candidate_gate_does_not_block_feedback_or_relax_auth(r008_client, monkeypatch):
    env = r008_client
    closed = {"schema_version": "r2-3-005-candidate-platform-gate/v1", "state": "closed",
              "reason_code": "team_stopped", "run_id": "stopped-test-run",
              "modeling_context": {"project_id": env["ids"]["p1"], "ontology_id": "old-model",
                                   "model_revision": 1, "context_receipt_digest": "old-receipt",
                                   "response_digest": "old-response", "call_receipt_digest": "old-call"}}
    monkeypatch.setattr("app.mcp.runtime._read_candidate_platform_gate", lambda: ("closed-stopped-gate", closed))

    def unexpected_model_read(*args, **kwargs):
        raise AssertionError("Feedback must not revalidate a stopped modeling context")

    monkeypatch.setattr("app.mcp.runtime._read_live_modeling_context", unexpected_model_read)
    body = _submission(env)
    submit = _mcp(env, monkeypatch, "submit_semantic_feedback", body)
    assert submit["ok"], submit
    args = {"feedback_id": body["feedback_id"]}
    assert not _mcp(env, monkeypatch, "get_semantic_feedback", args)["ok"]
    assert _mcp(env, monkeypatch, "get_semantic_feedback", args, "p1_admin_key")["ok"]
    resolution = {**args, "resolution": {"outcome": "unresolved", "explanation": "Team已退出，独立持久记录"}}
    assert _mcp(env, monkeypatch, "record_semantic_feedback_resolution", resolution, "p1_admin_key")["ok"]
    page = _mcp(env, monkeypatch, "list_semantic_feedback", {"project_id": env["ids"]["p1"]}, "p1_admin_key")
    assert page["ok"] and page["data"]["items"][0]["feedback_id"] == body["feedback_id"]
    foreign = _submission(env)
    foreign["query_request"]["project_id"] = env["ids"]["p2"]
    assert not _mcp(env, monkeypatch, "submit_semantic_feedback", foreign)["ok"]
    modeling = _mcp(env, monkeypatch, "get_modeling_context", {"ontology_id": "old-model"}, "p1_admin_key")
    assert not modeling["ok"]
    assert modeling["error_code"] == "candidate_receipt_required"
    assert closed["state"] == "closed"
