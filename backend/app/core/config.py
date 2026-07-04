from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"

    database_url: str = (
        "postgresql+psycopg://ontology:ontology@localhost:5434/"
        "ontology_platform?client_encoding=utf8"
    )
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ontology-platform"

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = Field(default=0.2, ge=0, le=2)

    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_api_key: str = ""
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = Field(default=1024, ge=256, le=2048)
    embedding_timeout_seconds: float = Field(default=45, gt=0, le=300)

    oxigraph_url: str = "http://localhost:7878"
    semantic_base_iri: str = "http://ontology-platform.local/semantic/"
    semantic_graph_iri_prefix: str = "http://ontology-platform.local/semantic/graph/"
    semantic_query_timeout_seconds: float = Field(default=10, gt=0, le=120)
    semantic_query_result_limit: int = Field(default=1000, ge=1, le=10000)
    semantic_shacl_inference: str = "none"
    semantic_reasoner_command: str = ""
    semantic_reasoner_timeout_seconds: float = Field(default=60, gt=0, le=600)
    semantic_neo4j_projection_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
