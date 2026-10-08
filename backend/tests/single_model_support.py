"""Direct Ontology fixtures for read/projection tests migrated from split graphs."""

from app.repositories.models import OntologyModel, ProjectModel


def seed_model(session, ontology_id, graph_iri=None, name="Model"):
    project = session.get(ProjectModel, "single-model-test-project")
    if project is None:
        project = ProjectModel(
            id="single-model-test-project", name="Model tests", normalized_label="model-tests"
        )
        session.add(project)
        session.flush()
    ontology = session.get(OntologyModel, ontology_id)
    if ontology is None:
        ontology = OntologyModel(
            id=ontology_id,
            project_id=project.id,
            name=name + str(ontology_id),
            model_revision=0,
            model_content_hash="",
            model_graph_iri=graph_iri
            or f"http://ontology-platform.local/semantic/graph/ontology/{ontology_id}",
        )
        session.add(ontology)
        session.flush()
    return ontology
