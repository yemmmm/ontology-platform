"""R-001 default semantic workspace creation, context, and repair tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db_session, get_settings
from app.api.ontologies import router
from app.api.schemas import OntologyCreate
from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticGraphSetMemberModel,
    SemanticGraphSetModel,
    SemanticRuleDefinitionModel,
    SemanticRuleModel,
)
from app.services import ontology_crud
from app.services.ontology_workspace import OntologyWorkspaceError, OntologyWorkspaceService
from app.services.semantic_graph_set import GraphSetError, SemanticGraphSetService


def _project(session, project_id: str = "p-1") -> ProjectModel:
    project = ProjectModel(id=project_id, name="Project", normalized_label="project")
    session.add(project)
    session.commit()
    return project


def _ontology(session, ontology_id: str = "o-1") -> OntologyModel:
    ontology = OntologyModel(id=ontology_id, project_id="p-1", name="Ontology")
    session.add(ontology)
    session.commit()
    return ontology


def test_delete_project_removes_rule_definition_cycle_before_ontology_cascade(in_memory_session):
    project = _project(in_memory_session, "rule-project")
    ontology = OntologyModel(id="rule-ontology", project_id=project.id, name="Rule ontology")
    rule = SemanticRuleModel(
        id="rule", ontology_id=ontology.id, rule_iri="urn:rule", status="active"
    )
    definition = SemanticRuleDefinitionModel(
        id="definition",
        semantic_rule_id=rule.id,
        rule_iri=rule.rule_iri,
        name="Rule",
        language="platform_dsl",
        version="v1",
        body={"statements": []},
    )
    in_memory_session.add_all([ontology, rule])
    in_memory_session.flush()
    in_memory_session.add(definition)
    in_memory_session.flush()
    rule.current_definition_id = definition.id
    in_memory_session.commit()
    rule_id, definition_id = rule.id, definition.id

    ontology_crud.delete_project(in_memory_session, project.id)

    assert in_memory_session.get(ProjectModel, project.id) is None
    assert in_memory_session.get(SemanticRuleModel, rule_id) is None
    assert in_memory_session.get(SemanticRuleDefinitionModel, definition_id) is None


def test_create_ontology_initializes_complete_default_workspace(in_memory_session):
    _project(in_memory_session)
    settings = Settings(semantic_graph_iri_prefix="https://example.test/graphs/")

    ontology = ontology_crud.create_ontology(
        in_memory_session,
        "p-1",
        OntologyCreate(name="School"),
        settings,
    )
    context = OntologyWorkspaceService(in_memory_session, settings).context(ontology.id)

    assert context["state"] == "ready"
    assert context["default_graph_set_id"]
    assert len(context["source_signature"]) == 32
    assert [member["role"] for member in context["members"]] == [
        "asserted_ontology",
        "asserted_data",
        "shapes",
        "policy",
    ]
    assert all(member["revision"] == 0 for member in context["members"])
    assert [member["editable"] for member in context["members"]] == [True, True, True, False]
    assert all(member["owner_id"] == ontology.id for member in context["members"])

    graph_set = in_memory_session.get(SemanticGraphSetModel, context["default_graph_set_id"])
    assert graph_set is not None
    assert graph_set.is_default is True
    assert graph_set.status == "active"
    assert len(graph_set.members) == 4


def test_ensure_is_idempotent_and_preserves_existing_revision(in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)
    settings = Settings()
    service = OntologyWorkspaceService(in_memory_session, settings)
    service.ensure(ontology)
    in_memory_session.commit()
    first = service.context(ontology.id)

    data_revision = in_memory_session.scalar(
        select(SemanticGraphRevisionModel).where(
            SemanticGraphRevisionModel.graph_iri.endswith(f"/data/{ontology.id}")
        )
    )
    assert data_revision is not None
    data_revision.revision = 7
    data_revision.content_hash = "existing-content"
    in_memory_session.commit()

    report = service.repair(ontology.id)
    second = service.context(ontology.id)

    assert report["actions"] == []
    assert report["conflicts"] == []
    assert second["default_graph_set_id"] == first["default_graph_set_id"]
    assert next(m for m in second["members"] if m["role"] == "asserted_data")["revision"] == 7
    assert data_revision.content_hash == "existing-content"
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticGraphSetModel)) == 1
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticGraphSetMemberModel)) == 4
    )
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticGraphRegistryModel)) == 4
    )
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticGraphRevisionModel)) == 4
    )


def test_repair_dry_run_reports_missing_resources_without_writing(in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)
    service = OntologyWorkspaceService(in_memory_session, Settings())

    report = service.repair(ontology.id, dry_run=True)

    assert report["ready"] is False
    assert len(report["actions"]) == 13
    assert report["workspace"]["state"] == "incomplete"
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticGraphSetModel)) == 0


def test_repair_rejects_registry_owner_conflict_without_overwriting(in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)
    settings = Settings()
    graph_iri = f"{settings.semantic_graph_iri_prefix}ontology/{ontology.id}"
    in_memory_session.add(
        SemanticGraphRegistryModel(
            id="registry-conflict",
            graph_iri=graph_iri,
            category="ontology",
            semantic_owner_type="ontology",
            semantic_owner_id="another-ontology",
            mutable_by_direct_edit=True,
        )
    )
    in_memory_session.commit()

    with pytest.raises(OntologyWorkspaceError):
        OntologyWorkspaceService(in_memory_session, settings).repair(ontology.id)
    in_memory_session.rollback()

    record = in_memory_session.get(SemanticGraphRegistryModel, "registry-conflict")
    assert record.semantic_owner_id == "another-ontology"
    assert in_memory_session.scalar(select(func.count()).select_from(SemanticGraphSetModel)) == 0


def test_creation_rolls_back_ontology_when_workspace_initialization_fails(
    in_memory_session, monkeypatch
):
    _project(in_memory_session)

    def fail(*_args, **_kwargs):
        raise OntologyWorkspaceError("initialization failed")

    monkeypatch.setattr(OntologyWorkspaceService, "ensure", fail)
    with pytest.raises(OntologyWorkspaceError):
        ontology_crud.create_ontology(
            in_memory_session, "p-1", OntologyCreate(name="Broken"), Settings()
        )

    assert (
        in_memory_session.scalar(
            select(func.count()).select_from(OntologyModel).where(OntologyModel.name == "Broken")
        )
        == 0
    )


def test_default_graph_set_membership_cannot_be_removed(in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)
    settings = Settings()
    workspace = OntologyWorkspaceService(in_memory_session, settings)
    workspace.ensure(ontology)
    in_memory_session.commit()
    graph_set_id = workspace.context(ontology.id)["default_graph_set_id"]

    with pytest.raises(GraphSetError, match="membership is fixed"):
        SemanticGraphSetService(in_memory_session, settings).update_membership(
            graph_set_id,
            [
                {
                    "role": "asserted_data",
                    "graph_iri": f"{settings.semantic_graph_iri_prefix}data/{ontology.id}",
                }
            ],
        )


def test_database_rejects_second_default_graph_set_for_same_ontology(in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)
    settings = Settings()
    workspace = OntologyWorkspaceService(in_memory_session, settings)
    workspace.ensure(ontology)
    in_memory_session.commit()
    in_memory_session.add(
        SemanticGraphSetModel(
            id="second-default",
            name="Invalid duplicate",
            scope_type="ontology",
            scope_id=ontology.id,
            status="active",
            is_default=True,
            source_signature="",
        )
    )

    with pytest.raises(IntegrityError):
        in_memory_session.commit()
    in_memory_session.rollback()


@pytest.fixture()
def workspace_client(in_memory_session):
    app = FastAPI()
    app.include_router(router)
    settings = Settings()

    def session_override():
        yield in_memory_session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_create_api_returns_ready_workspace_and_context_endpoint(
    workspace_client, in_memory_session
):
    _project(in_memory_session)

    response = workspace_client.post("/projects/p-1/ontologies", json={"name": "School"})

    assert response.status_code == 201
    body = response.json()
    assert body["workspace"]["state"] == "ready"
    context = workspace_client.get(f"/ontologies/{body['id']}/workspace-context")
    assert context.status_code == 200
    assert context.json() == body["workspace"]


def test_repair_api_restores_historical_ontology(workspace_client, in_memory_session):
    _project(in_memory_session)
    ontology = _ontology(in_memory_session)

    response = workspace_client.post(
        f"/ontologies/{ontology.id}/workspace/repair", json={"dry_run": False}
    )

    assert response.status_code == 200
    assert response.json()["workspace"]["state"] == "ready"
