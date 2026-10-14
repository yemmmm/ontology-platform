from app.main import create_app


def test_openapi_uses_ontoweave_name_without_changing_api_routes() -> None:
    schema = create_app().openapi()

    assert schema["info"]["title"] == "OntoWeave API"
    assert "/api/health" in schema["paths"]
    assert "/api/projects" in schema["paths"]
