"""R4.0-026 retirement: no GraphSet management or persistence."""
from app.main import create_app
from app.repositories.postgres import Base


def test_graph_set_management_and_storage_are_removed():
    assert "semantic_graph_sets" not in Base.metadata.tables
    assert "semantic_graph_set_members" not in Base.metadata.tables
    paths = create_app().openapi()["paths"]
    assert not any("graph-sets" in path for path in paths)
    assert "/api/semantic/ontologies/{ontology_id}/read-models/{model_name}" in paths
