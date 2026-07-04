from app.core.config import Settings


def test_semantic_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.oxigraph_url == "http://localhost:7878"
    assert settings.semantic_graph_iri_prefix.endswith("/graph/")
    assert settings.semantic_query_result_limit == 1000
    assert settings.semantic_shacl_inference == "none"
