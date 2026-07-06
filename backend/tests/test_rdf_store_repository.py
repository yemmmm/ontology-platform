import httpx

from app.repositories.rdf_store import RdfStoreRepository, _query_with_limit


def test_rdf_store_query_applies_default_limit(monkeypatch) -> None:
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={"head": {"vars": ["s"]}, "results": {"bindings": []}},
            headers={"content-type": "application/sparql-results+json"},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = RdfStoreRepository("http://oxigraph.test").query_sparql(
        "SELECT ?s WHERE { ?s ?p ?o }",
        timeout_seconds=5,
        limit=7,
    )

    assert captured["url"] == "http://oxigraph.test/query"
    assert "LIMIT 7" in captured["data"]["query"]
    assert result.result["results"]["bindings"] == []


def test_query_with_limit_uses_space_separator() -> None:
    """Regression: Oxigraph rejects ``}\\nLIMIT`` — LIMIT must follow with a space."""
    query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    effective = _query_with_limit(query, limit=10)
    assert effective == "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } LIMIT 10"
    assert "\n" not in effective


def test_query_with_limit_preserves_existing_limit() -> None:
    query = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"
    assert _query_with_limit(query, limit=10) == query


def test_query_with_limit_handles_trailing_whitespace() -> None:
    query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }   \n  "
    effective = _query_with_limit(query, limit=3)
    assert effective == "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } LIMIT 3"
    assert "\n" not in effective
