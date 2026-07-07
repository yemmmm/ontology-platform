"""Tests for compile_bind_fact_evidence and compile_unbind_fact_evidence."""
import pytest

from app.services.fact_id import canonical_object_term, compute_fact_id
from app.services.semantic_command_compiler import (
    compile_bind_fact_evidence,
    compile_unbind_fact_evidence,
)
from app.services.semantic_export import SemanticNamespace


@pytest.fixture
def ns_factory():
    """Factory fixture returning a fresh SemanticNamespace for tests."""

    def _make() -> SemanticNamespace:
        return SemanticNamespace(
            base_iri="http://ontology-platform.local/semantic/",
            graph_iri_prefix="http://ontology-platform.local/semantic/graph",
        )

    return _make


def test_bind_fact_evidence_with_text_only(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "evidence snippet",
        "actor": "user:alice",
    }
    cmd = compile_bind_fact_evidence(payload, ns, settings=None)
    assert cmd.command_kind == "bind_fact_evidence"
    assert cmd.object_kind == "fact_evidence"
    expected_fid = compute_fact_id(
        "http://example/s",
        "http://example/p",
        canonical_object_term("42", is_iri=False),
        "http://example/g",
    )
    assert cmd.metadata["fact_id"] == expected_fid
    assert cmd.metadata["text"] == "evidence snippet"
    # No RDF delta — evidence lives in PG only
    assert cmd.delta.inserts == []
    assert cmd.delta.deletes == []


def test_bind_fact_evidence_rejects_fact_id_mismatch(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "fact_id": "0" * 64,  # wrong
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "object_is_iri": False,
        "graph_iri": "http://example/g",
        "text": "t",
    }
    with pytest.raises(Exception, match="fact_id mismatch"):
        compile_bind_fact_evidence(payload, ns, settings=None)


def test_bind_fact_evidence_uses_default_graph_when_omitted(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "http://example/o",
        "object_is_iri": True,
        "text": "t",
    }
    cmd = compile_bind_fact_evidence(payload, ns, settings=None)
    # graph_iri should fall back to data graph for the ontology
    assert cmd.metadata["graph_iri"]


def test_bind_fact_evidence_rejects_empty_text(ns_factory):
    ns = ns_factory()
    payload = {
        "ontology_id": "ont-1",
        "subject_iri": "http://example/s",
        "predicate_iri": "http://example/p",
        "object_value": "42",
        "graph_iri": "http://example/g",
        "text": "   ",
    }
    with pytest.raises(Exception, match="text must not be empty"):
        compile_bind_fact_evidence(payload, ns, settings=None)


def test_unbind_fact_evidence_by_binding_id(ns_factory):
    ns = ns_factory()
    payload = {"ontology_id": "ont-1", "binding_id": "abc-123"}
    cmd = compile_unbind_fact_evidence(payload, ns, settings=None)
    assert cmd.command_kind == "unbind_fact_evidence"
    assert cmd.metadata["binding_id"] == "abc-123"
    assert cmd.delta.inserts == []
    assert cmd.delta.deletes == []


def test_unbind_fact_evidence_requires_binding_id(ns_factory):
    ns = ns_factory()
    with pytest.raises(Exception):
        compile_unbind_fact_evidence({"ontology_id": "ont-1"}, ns, settings=None)
