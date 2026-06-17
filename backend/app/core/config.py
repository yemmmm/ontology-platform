from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    admin_token: str = "change-me-admin-token"
    mcp_api_key: str = "change-me-mcp-key"

    database_url: str = (
        "postgresql+psycopg://ontology:ontology@localhost:5432/"
        "ontology_platform?client_encoding=utf8"
    )
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ontology-platform"

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.2

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
