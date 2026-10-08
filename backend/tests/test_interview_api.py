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


def test_build_overview_returns_404_for_unknown_ontology(app_with_mocked_services):
    response = TestClient(app_with_mocked_services).get("/ontologies/o-1/build-overview?project_id=p-1")
    assert response.status_code == 404


def test_build_overview_returns_direct_model_state(app_with_mocked_services, in_memory_session):
    from app.repositories.models import OntologyModel, ProjectModel
    in_memory_session.add(ProjectModel(id="p-1", name="P", normalized_label="P"))
    in_memory_session.flush()
    in_memory_session.add(OntologyModel(id="o-1", project_id="p-1", name="O", model_revision=2))
    in_memory_session.commit()
    response = TestClient(app_with_mocked_services).get("/ontologies/o-1/build-overview?project_id=p-1")
    assert response.status_code == 200, response.text
    assert response.json()["model"] == {"ontology_id": "o-1", "revision": 2, "editable": True}
    assert "graph_set" not in response.json()
