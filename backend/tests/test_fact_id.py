from app.services.fact_id import compute_fact_id, canonical_object_term


def test_canonical_object_term_iri():
    assert canonical_object_term("http://example.org/x", is_iri=True) == "<http://example.org/x>"


def test_canonical_object_term_string_literal():
    assert canonical_object_term("hello", is_iri=False) == '"hello"'


def test_canonical_object_term_typed_literal():
    term = canonical_object_term("42", is_iri=False, datatype="http://www.w3.org/2001/XMLSchema#integer")
    assert term == '"42"^^<http://www.w3.org/2001/XMLSchema#integer>'


def test_canonical_object_term_lang_literal():
    term = canonical_object_term("hello", is_iri=False, lang="en")
    assert term == '"hello"@en'


def test_compute_fact_id_is_stable_4_tuple():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    assert fid1 == fid2
    assert len(fid1) == 64


def test_compute_fact_id_changes_with_graph():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g1")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g2")
    assert fid1 != fid2


def test_compute_fact_id_changes_with_object():
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"42"', "http://a/g")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"43"', "http://a/g")
    assert fid1 != fid2


def test_compute_fact_id_changes_with_subject():
    fid1 = compute_fact_id("http://a/s1", "http://a/p", '"42"', "http://a/g")
    fid2 = compute_fact_id("http://a/s2", "http://a/p", '"42"', "http://a/g")
    assert fid1 != fid2
