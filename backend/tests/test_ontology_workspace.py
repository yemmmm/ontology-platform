from sqlalchemy import select, func
from app.api.schemas import OntologyCreate
from app.core.config import Settings
from app.repositories.models import (
    OntologyModel,
    ProjectModel,
    SemanticGraphRegistryModel,
    SemanticGraphRevisionModel,
    SemanticRuleModel,
    SemanticRuleDefinitionModel,
)
from app.services import ontology_crud
from app.services.ontology_workspace import OntologyWorkspaceService


def _project(session, project_id="p-1"):
    project = ProjectModel(id=project_id, name="Project", normalized_label="project")
    session.add(project)
    session.commit()
    return project


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


def test_creation_initializes_one_owned_model(in_memory_session):
    _project(in_memory_session)
    settings = Settings()
    ontology = ontology_crud.create_ontology(
        in_memory_session, "p-1", OntologyCreate(name="Model"), settings
    )
    service = OntologyWorkspaceService(in_memory_session, settings)
    before = service.context(ontology.id)
    assert before["state"] == "ready"
    assert before["model_revision"] == 0
    assert len(before["source_signature"]) == 64
    assert before["editable"]
    assert "members" not in before
    assert "graph_set_id" not in before
    assert (
        in_memory_session.scalar(select(func.count()).select_from(SemanticGraphRegistryModel)) == 1
    )
    service.ensure(ontology)
    assert service.context(ontology.id) == before


def test_repair_is_dry_run_then_idempotent(in_memory_session):
    _project(in_memory_session)
    ontology = OntologyModel(id="o", project_id="p-1", name="Model")
    in_memory_session.add(ontology)
    in_memory_session.commit()
    service = OntologyWorkspaceService(in_memory_session, Settings())
    report = service.repair("o", dry_run=True)
    assert report["actions"]
    assert ontology.model_graph_iri is None
    assert service.context("o")["state"] == "incomplete"
    assert service.repair("o")["workspace"]["state"] == "ready"
    assert service.repair("o")["actions"] == []
