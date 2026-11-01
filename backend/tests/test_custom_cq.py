"""Project questions stay usable before a model exists and retain execution baselines."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import interview as api
from app.repositories.models import ProjectModel


@pytest.fixture
def cq_client(in_memory_session):
    in_memory_session.add(ProjectModel(id="cq-project", name="CQ", normalized_label="CQ"))
    in_memory_session.commit()
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db_session] = lambda: in_memory_session
    app.dependency_overrides[api.get_rdf_store] = lambda: object()
    from app.core.config import Settings

    app.dependency_overrides[api.get_settings] = lambda: Settings()
    return TestClient(app)


def create(client, **fields):
    response = client.post(
        "/projects/cq-project/competency-questions",
        json={"question": "调用多少次？\n包含零调用。", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_question_only_create_does_not_require_ontology_or_answer(cq_client):
    question = create(cq_client)
    assert question["ontology_id"] is None
    assert question["cq_definition"]["kind"] == "custom"
    assert question["cq_definition"]["reference_answer"] is None
    assert question["cq_definition"]["criteria_status"] == "draft"
    assert question["content_revision"] == 1
    assert cq_client.get("/projects/cq-project/competency-questions").json()[0]["question"] == (
        "调用多少次？\n包含零调用。"
    )


def test_custom_edits_require_current_revision_and_old_snapshot_is_immutable(cq_client):
    question = create(cq_client)
    path = f"/competency-questions/{question['id']}"
    frozen = cq_client.post("/projects/cq-project/competency-questions/snapshot", json={}).json()
    assert frozen["questions"][0]["question"] == question["question"]
    assert cq_client.patch(path, json={"question": "另一个问题"}).status_code == 409
    updated = cq_client.patch(path, json={"question": "按月有多少次？", "expected_revision": 1})
    assert updated.status_code == 200, updated.text
    assert updated.json()["content_revision"] == 2
    stale = cq_client.patch(path, json={"active": False, "expected_revision": 1})
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_revision"] == 2
    assert frozen["questions"][0]["question"] == question["question"]
    current = cq_client.post("/projects/cq-project/competency-questions/snapshot", json={}).json()
    assert current["snapshot_id"] != frozen["snapshot_id"]
    assert current["questions"][0]["content_revision"] == 2


def test_missing_criteria_does_not_become_ready_or_passed(cq_client):
    question = create(cq_client)
    snapshot = cq_client.post("/projects/cq-project/competency-questions/snapshot", json={})
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["questions"][0]["criteria_ready"] is False
    response = cq_client.post(
        f"/competency-questions/{question['id']}/status",
        json={"status": "passed", "validation_result": {"passed": True}},
    )
    assert response.status_code == 409


def test_deselection_and_deactivation_do_not_rewrite_frozen_question_set(cq_client):
    first = create(cq_client)
    second = create(cq_client, question="跨业务问题")
    frozen = cq_client.post("/projects/cq-project/competency-questions/snapshot", json={}).json()
    definition = {**first["cq_definition"], "selected": False}
    assert (
        cq_client.patch(
            f"/competency-questions/{first['id']}",
            json={"cq_definition": definition, "expected_revision": 1},
        ).status_code
        == 200
    )
    assert (
        cq_client.patch(
            f"/competency-questions/{second['id']}",
            json={"active": False, "expected_revision": 1},
        ).status_code
        == 200
    )
    assert (
        cq_client.post("/projects/cq-project/competency-questions/snapshot", json={}).json()[
            "questions"
        ]
        == []
    )
    assert len(frozen["questions"]) == 2
    assert len(cq_client.get("/projects/cq-project/competency-questions").json()) == 1


def test_seed_import_reuses_identity_and_does_not_overwrite_user_edits(cq_client):
    seed = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "examples/llm-access-lab/competency-questions.json"
        ).read_text()
    )
    path = "/projects/cq-project/competency-questions/import"
    first = cq_client.post(path, json=seed)
    assert first.status_code == 200, first.text
    original_ids = [q["id"] for q in first.json()["questions"]]
    assert len(original_ids) == 9
    again = cq_client.post(path, json=seed)
    assert again.status_code == 200, again.text
    assert [q["id"] for q in again.json()["questions"]] == original_ids
    assert len(cq_client.get("/projects/cq-project/competency-questions").json()) == 9
    assert (
        cq_client.patch(
            f"/competency-questions/{original_ids[0]}",
            json={"question": "用户已经改过的题", "expected_revision": 1},
        ).status_code
        == 200
    )
    conflict = cq_client.post(path, json=seed)
    assert conflict.status_code == 409
    assert cq_client.get("/projects/cq-project/competency-questions").json()[0]["question"] == (
        "用户已经改过的题"
    )


def test_private_fields_and_unsupported_confirmations_are_rejected(cq_client):
    for definition in (
        {"kind": "custom", "hidden_answer": "private"},
        {"kind": "custom", "criteria_status": "confirmed"},
    ):
        response = cq_client.post(
            "/projects/cq-project/competency-questions",
            json={"question": "问题", "cq_definition": definition},
        )
        assert response.status_code == 422, response.text
    assert cq_client.get("/projects/cq-project/competency-questions").json() == []


def test_custom_question_cannot_use_legacy_count_validator(cq_client):
    question = create(cq_client)
    response = cq_client.post(f"/competency-questions/{question['id']}/validate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "custom_cq_requires_semantic_evaluation"


def test_runtime_result_targets_its_frozen_revision_and_cannot_overwrite_new_question(
    cq_client,
    in_memory_session,
):
    from app.services import custom_cq

    question = create(cq_client)
    frozen = cq_client.post("/projects/cq-project/competency-questions/snapshot", json={}).json()
    case = frozen["questions"][0]
    public = {
        "model_revisions": {"ontology": 4},
        "cq_snapshot_id": frozen["snapshot_id"],
        "custom_cq": [
            {
                "cq_id": case["cq_id"],
                "content_revision": 1,
                "content_digest": case["content_digest"],
                "outcome": "question-answer-review",
                "answerability": "unsupported",
                "sql_readiness": "unsupported",
                "sql_execution": "not_run",
            }
        ],
    }
    custom_cq.record_results(in_memory_session, "cq-project", frozen, public, "evaluation-1")
    current = cq_client.get("/projects/cq-project/competency-questions").json()[0]
    assert current["validation_result"]["sql_execution"] == "not_run"
    assert current["validation_result"]["model_revisions"] == {"ontology": 4}
    cq_client.patch(
        f"/competency-questions/{question['id']}",
        json={"question": "新问题", "expected_revision": 1},
    )
    custom_cq.record_results(in_memory_session, "cq-project", frozen, public, "evaluation-old")
    current = cq_client.get("/projects/cq-project/competency-questions").json()[0]
    assert current["validation_result"]["stale"] is True
    assert current["validation_result"]["evaluation_id"] == "evaluation-1"


def test_custom_cq_project_authorization_is_enforced(r008_client):
    env = r008_client
    client, ids = env["client"], env["ids"]
    created = client.post(
        f"/api/projects/{ids['p1']}/competency-questions",
        headers={"Authorization": "Bearer " + env["p1_admin_key"]},
        json={"question": "问题"},
    )
    assert created.status_code == 201, created.text
    read_headers = {"Authorization": "Bearer " + env["p1_read_key"]}
    assert (
        client.get(
            f"/api/projects/{ids['p1']}/competency-questions", headers=read_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/projects/{ids['p1']}/competency-questions",
            headers=read_headers,
            json={"question": "越权修改"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/projects/{ids['p2']}/competency-questions/import",
            headers={"Authorization": "Bearer " + env["p1_admin_key"]},
            json={},
        ).status_code
        == 403
    )


def test_host_preserves_typed_cq_selection_errors(
    cq_client, in_memory_session, monkeypatch, tmp_path
):
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.syspath_prepend(str(root / "modeling_team/v5/src"))
    from modeling_team.v5.host.worker import PlatformWorker
    from ontoweave_modeling.contracts import FrameworkError
    from app.repositories import postgres

    monkeypatch.setattr(
        postgres,
        "create_session_factory",
        lambda settings: sessionmaker(bind=in_memory_session.bind),
    )
    binding = SimpleNamespace(root=tmp_path, data={"project_ref": "cq-project", "scope": {}})
    with pytest.raises(FrameworkError, match="cq_selection_unavailable") as error:
        PlatformWorker(binding).competency_questions({"question_ids": ["not-in-this-project"]})
    assert error.value.layer == "platform-contract"


def test_same_definition_from_a_new_actor_does_not_create_a_spurious_revision(
    cq_client, in_memory_session
):
    from app.api.schemas import CompetencyQuestionUpdate, CustomCQDefinition
    from app.services import interview

    question = create(cq_client)
    unchanged = interview.update_question(
        in_memory_session,
        question["id"],
        CompetencyQuestionUpdate(
            expected_revision=1,
            cq_definition=CustomCQDefinition.model_validate(question["cq_definition"]),
        ),
        actor_id="user:another-session",
    )
    assert unchanged.content_revision == 1
