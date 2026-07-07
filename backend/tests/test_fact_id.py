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


def test_canonical_object_term_escapes_quote():
    # A literal containing a quote must be escaped to avoid hash collision
    term = canonical_object_term('a"b', is_iri=False)
    assert term == '"a\\"b"'


def test_canonical_object_term_escapes_backslash():
    term = canonical_object_term("a\\b", is_iri=False)
    assert term == '"a\\\\b"'


def test_canonical_object_term_escapes_newline():
    term = canonical_object_term("a\nb", is_iri=False)
    assert term == '"a\\nb"'


def test_compute_fact_id_distinguishes_quoted_vs_unquoted():
    # Without escaping these two would collide
    fid1 = compute_fact_id("http://a/s", "http://a/p", '"a","b"', "http://a/g")
    fid2 = compute_fact_id("http://a/s", "http://a/p", '"a\\"\\,b"', "http://a/g")
    assert fid1 != fid2


def test_compute_fact_id_no_collision_with_concatenated_values():
    # Critical regression: pre-fix, 'a","b' and 'a' + '","' + 'b' would hash
    # to the same id because no escaping. Verify escaping prevents this.
    term1 = canonical_object_term('a","b', is_iri=False)
    # If we forgot escaping, term1 would be '"a","b"' which could be parsed
    # as two literals. With escaping it becomes a single literal.
    assert term1 == '"a\\",\\"b"'
