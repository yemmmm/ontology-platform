import httpx

from app.repositories.rdf_store import RdfStoreRepository


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
