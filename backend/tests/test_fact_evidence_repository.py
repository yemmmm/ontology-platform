"""Tests for FactEvidenceBindingRepository."""
from app.repositories.fact_evidence_repository import FactEvidenceBindingRepository


def test_create_and_list_by_fact_id(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    binding = repo.create(
        fact_id="a" * 64,
        subject_iri="http://example/s",
        predicate_iri="http://example/p",
        object_value='"42"',
        graph_iri="http://example/g",
        text="evidence text",
        actor="user:alice",
    )
    assert binding.id
    assert binding.fact_id == "a" * 64
    assert binding.text == "evidence text"
    assert binding.actor == "user:alice"

    listed = repo.list_by_fact_id("a" * 64)
    assert len(listed) == 1
    assert listed[0].text == "evidence text"


def test_create_with_chunk_reference(in_memory_session):
    """Bindings can reference an evidence chunk from the document parser."""
    repo = FactEvidenceBindingRepository(in_memory_session)
    binding = repo.create(
        fact_id="b" * 64,
        subject_iri="http://example/s",
        predicate_iri="http://example/p",
        object_value='"v"',
        graph_iri="http://example/g",
        text="snippet",
        chunk_id=None,  # would need a real EvidenceChunkModel row in practice
        document_filename="report.pdf",
        sequence=5,
        char_start=100,
        char_end=200,
    )
    assert binding.document_filename == "report.pdf"
    assert binding.sequence == 5
    assert binding.char_start == 100
    assert binding.char_end == 200


def test_list_by_fact_ids_batch(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    for fact_id in ["f1" * 32, "f2" * 32]:
        repo.create(
            fact_id=fact_id,
            subject_iri="s",
            predicate_iri="p",
            object_value='"v"',
            graph_iri="g",
            text="t",
        )
    # Add two bindings to one fact to verify bucketing
    repo.create(
        fact_id="f1" * 32,
        subject_iri="s",
        predicate_iri="p",
        object_value='"v"',
        graph_iri="g",
        text="t2",
    )
    result = repo.list_by_fact_ids(["f1" * 32, "f2" * 32, "f3" * 32])
    assert set(result.keys()) == {"f1" * 32, "f2" * 32}
    assert len(result["f1" * 32]) == 2
    assert len(result["f2" * 32]) == 1
    assert "f3" * 32 not in result  # no bindings = no key


def test_list_by_fact_ids_empty_input(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    assert repo.list_by_fact_ids([]) == {}


def test_count_facts_with_bindings(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    repo.create(
        fact_id="a" * 64,
        subject_iri="s",
        predicate_iri="p",
        object_value='"v"',
        graph_iri="g",
        text="t",
    )
    result = repo.count_facts_with_bindings(["a" * 64, "b" * 64])
    assert result == {"a" * 64}


def test_count_facts_with_bindings_empty_input(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    assert repo.count_facts_with_bindings([]) == set()


def test_delete(in_memory_session):
    repo = FactEvidenceBindingRepository(in_memory_session)
    binding = repo.create(
        fact_id="a" * 64,
        subject_iri="s",
        predicate_iri="p",
        object_value='"v"',
        graph_iri="g",
        text="t",
    )
    assert repo.delete(binding.id) is True
    assert repo.delete(binding.id) is False  # already deleted
    assert repo.list_by_fact_id("a" * 64) == []
