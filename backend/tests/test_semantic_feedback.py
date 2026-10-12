"""Developer boundary regressions for independent feedback storage."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.services.semantic_feedback import (
    FeedbackError,
    FeedbackSubmission,
    SemanticFeedbackService,
)
from app.security.auth import AuthPrincipal


def payload(project_id="p"):
    return {
        "feedback_id": str(uuid4()),
        "query_request": {
            "project_id": project_id,
            "scope_mode": "project",
            "queries": ["  原文  "],
        },
        "reasons": ["other"],
        "description": "  观察\n",
    }


@pytest.mark.parametrize(
    "query",
    [
        {"scope_mode": "ontologies"},
        {"scope_mode": "project", "ontology_ids": ["o"]},
        {"scope_mode": "ontologies", "ontology_ids": ["o", "o"]},
    ],
)
def test_query_scope_structure_rejected_without_workspace_lookup(query):
    body = payload()
    body["query_request"].update(query)
    with pytest.raises(ValueError):
        FeedbackSubmission.model_validate(body)


def test_nonfinite_snapshot_and_boolean_revision_rejected():
    body = payload()
    body["result_snapshot"] = {"value": float("nan")}
    with pytest.raises(ValueError):
        FeedbackSubmission.model_validate(body)
    from app.services.semantic_feedback import FeedbackVerification

    with pytest.raises(ValueError):
        FeedbackVerification.model_validate(
            {"project_id": "p", "model_revisions": {"o": True}, "readback_references": ["readback"]}
        )


def test_database_failure_is_retryable_and_not_saved(in_memory_session, monkeypatch):
    principal = AuthPrincipal("api_key", "k", "key:k", frozenset({"read"}), "p", "bearer")

    def unavailable(*args, **kwargs):
        raise OperationalError("storage", {}, Exception("offline"))

    monkeypatch.setattr(in_memory_session, "get", unavailable)
    with pytest.raises(FeedbackError) as failure:
        SemanticFeedbackService(in_memory_session, principal).submit(payload())
    assert failure.value.status_code == 503
    assert failure.value.code == "dependency_error"
    assert "same feedback_id" in str(failure.value)


def test_rest_retains_raw_query_despite_recall_normalization(r008_client):
    body = payload(r008_client["ids"]["p1"])
    submitted = deepcopy(body)
    client = r008_client["client"]
    response = client.post(
        "/api/semantic/feedback",
        json=body,
        headers={"Authorization": "Bearer " + r008_client["p1_read_key"]},
    )
    assert response.status_code == 200
    saved = client.get(
        "/api/semantic/feedback/" + body["feedback_id"],
        headers={"Authorization": "Bearer " + r008_client["p1_admin_key"]},
    ).json()
    assert saved["submission"]["query_request"] == submitted["query_request"]
    assert saved["submission"]["description"] == submitted["description"]
