import pytest
from single_model_support import seed_model
from app.services.semantic_read_scope import SemanticReadScopeResolver, ReadScopeError


@pytest.mark.parametrize("include", ["asserted", "full-working-view"])
def test_scope_is_the_ontology_model_only(in_memory_session, include):
    ontology = seed_model(in_memory_session, "o")
    result = SemanticReadScopeResolver(in_memory_session).resolve(ontology.id, include)
    assert result.ontology_id == ontology.id
    assert result.model_graph_iris == [ontology.model_graph_iri]
    assert result.model_revision == ontology.model_revision
    assert result.shape_graph_iris == []
    assert result.reasoning_result_graph_iri is None
    assert result.derived_state == {}
    assert not hasattr(result, "members")


def test_unknown_scope_and_invalid_include_have_recoverable_errors(in_memory_session):
    resolver = SemanticReadScopeResolver(in_memory_session)
    with pytest.raises(ReadScopeError, match="not ready"):
        resolver.resolve("missing")
    ontology = seed_model(in_memory_session, "o")
    with pytest.raises(ReadScopeError, match="include"):
        resolver.resolve(ontology.id, "invalid")
    assert resolver.resolve(ontology.id).ontology_id == ontology.id
