"""Single Ontology scope, export and retired GraphSet read surfaces."""
import pytest
from app.services.semantic_read_model import ReadModelError
from app.services.semantic_read_scope import SemanticReadScopeResolver
from conftest_stage3 import ONTOLOGY_GRAPH, client_for
pytest_plugins = ("conftest_stage3",)


def test_scope_and_export_use_one_model(fake_graph_set_with_members, in_memory_session, fake_store):
    service, ontology_id = fake_graph_set_with_members
    scope = service.scope_resolver.resolve(ontology_id)
    assert scope.model_graph_iris == [ONTOLOGY_GRAPH]
    assert not hasattr(scope, "members")
    client = client_for(fake_store, in_memory_session)
    response = client.get(f"/api/semantic/ontologies/{ontology_id}/export?format=turtle")
    assert response.status_code == 200


@pytest.mark.parametrize("name", ["graph-set-staleness", "graph-set-delta", "graph-set-history-list"])
def test_graph_set_read_models_are_retired(fake_graph_set_with_members, name):
    service, ontology_id = fake_graph_set_with_members
    with pytest.raises(ReadModelError, match="Unknown read model"):
        service.read_model(ontology_id, name)


def test_separate_ontology_isolation(fake_graph_set_with_members, second_graph_set_same_scope):
    service, ontology_id = fake_graph_set_with_members
    first = service.scope_resolver.resolve(ontology_id)
    second = service.scope_resolver.resolve(second_graph_set_same_scope)
    assert first.ontology_id != second.ontology_id
    assert set(first.model_graph_iris).isdisjoint(second.model_graph_iris)
