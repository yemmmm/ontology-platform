"""Empty single models are valid read scopes; member roles are retired."""
import pytest
from single_model_support import seed_model
from app.mcp.tools import semantic as semantic_tools
from app.services.semantic_read_scope import ReadScopeError


def test_resolve_empty_model_without_materialization_gate(in_memory_session):
    ontology = seed_model(in_memory_session, "empty")
    assert ontology.model_revision == 0
    assert semantic_tools._resolve_data_graphs(in_memory_session, ontology.id) == [ontology.model_graph_iri]
    assert not hasattr(semantic_tools, "_resolve_role_graphs")


def test_missing_ontology_is_localized_and_existing_scope_remains_readable(in_memory_session):
    ontology = seed_model(in_memory_session, "o")
    with pytest.raises(ReadScopeError, match="not ready"):
        semantic_tools._resolve_data_graphs(in_memory_session, "absent")
    assert len(semantic_tools._resolve_data_graphs(in_memory_session, ontology.id)) == 1
