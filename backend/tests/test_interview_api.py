"""Tests for interview API routes including build-overview."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_mocked_services(in_memory_session, monkeypatch):
    """Return a FastAPI app with the interview router and mocked store/settings."""
    from fastapi import FastAPI
    from app.api import interview as interview_mod
    from app.core.config import Settings

    app = FastAPI()
    app.include_router(interview_mod.router)

    # Mock the RDF store dependency
    fake_store = MagicMock()
    fake_settings = Settings(competency_question_sparql_timeout_seconds=5.0)

    async def _override_session():
        return in_memory_session

    def _override_store():
        return fake_store

    def _override_settings():
        return fake_settings

    app.dependency_overrides[interview_mod.get_db_session] = _override_session
    app.dependency_overrides[interview_mod.get_rdf_store] = _override_store
    app.dependency_overrides[interview_mod.get_settings] = _override_settings

    return app


def test_build_overview_returns_404_when_no_active_graph_set(
    app_with_mocked_services, monkeypatch
):
    monkeypatch.setattr(
        "app.api.interview._active_graph_set_for_ontology",
        lambda session, ontology_id: None,
    )
    client = TestClient(app_with_mocked_services)
    response = client.get("/ontologies/o-1/build-overview?project_id=p-1")
    assert response.status_code == 404
    assert "active graph-set" in response.json()["detail"].lower()


def test_build_overview_returns_200_with_valid_graph_set(
    app_with_mocked_services, monkeypatch, in_memory_session
):
    monkeypatch.setattr(
        "app.api.interview._active_graph_set_for_ontology",
        lambda session, ontology_id: "gs-1",
    )
    # Mock the BuildOverviewService to return a known response
    from app.services.semantic_build_overview import (
        BuildOverviewResponse, GraphSetStaleness,
        GraphSetMemberStaleness, BriefSummary, CompetencyQuestionSummary,
    )

    def _fake_build(self, *, session, project_id, ontology_id, graph_set_id):
        return BuildOverviewResponse(
            ontology_id=ontology_id,
            graph_set=GraphSetStaleness(
                graph_set_id=graph_set_id,
                members=[GraphSetMemberStaleness(
                    iri="http://x/g", role="asserted_data",
                    editable=True, validation_stale=False,
                    reasoning_stale=False, rule_stale=False,
                    last_semantic_edit_at=None,
                )],
                missing_evidence_count=0,
                last_semantic_edit_at=None,
            ),
            project_brief=BriefSummary(1.0, []),
            competency_questions=CompetencyQuestionSummary(0, {}),
            next_actions=[],
        )

    monkeypatch.setattr(
        "app.services.semantic_build_overview.BuildOverviewService.build",
        _fake_build,
    )
    client = TestClient(app_with_mocked_services)
    response = client.get("/ontologies/o-1/build-overview?project_id=p-1")
    assert response.status_code == 200
    body = response.json()
    assert body["ontology_id"] == "o-1"
    assert body["graph_set"]["graph_set_id"] == "gs-1"
    assert body["graph_set"]["members"][0]["role"] == "asserted_data"
    assert "next_actions" in body


# ---------------------------------------------------------------------------
# Deprecation header tests for legacy routes
# ---------------------------------------------------------------------------


def test_build_context_legacy_route_returns_deprecation_header(
    app_with_mocked_services, monkeypatch
):
    monkeypatch.setattr(
        "app.api.interview.service.get_build_context",
        lambda session, project_id: {},
    )
    client = TestClient(app_with_mocked_services)
    response = client.get("/projects/p-1/build-context")
    assert response.headers.get("Deprecation") == "true"
    assert "Sunset" in response.headers
