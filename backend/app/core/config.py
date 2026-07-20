from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = ""
    ontology_bootstrap_admin_user: str = ""
    ontology_bootstrap_admin_password: str = ""
    ontology_bootstrap_admin_api_key: str = ""
    ontology_mcp_api_key: str = ""
    ontology_ui_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    database_url: str = (
        "postgresql+psycopg://ontology:ontology@localhost:5434/"
        "ontology_platform?client_encoding=utf8"
    )
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_api_key: str = ""
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = Field(default=1024, ge=256, le=2048)
    embedding_timeout_seconds: float = Field(default=45, gt=0, le=300)

    oxigraph_url: str = "http://localhost:7878"
    semantic_base_iri: str = "http://ontology-platform.local/semantic/"
    semantic_graph_iri_prefix: str = "http://ontology-platform.local/semantic/graph/"
    semantic_query_timeout_seconds: float = Field(default=10, gt=0, le=120)
    competency_question_sparql_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    semantic_query_result_limit: int = Field(default=1000, ge=1, le=10000)
    semantic_shacl_inference: str = "none"
    semantic_reasoner_command: str = ""
    semantic_reasoner_timeout_seconds: float = Field(default=60, gt=0, le=600)
    semantic_graph_visibility_labels: dict[str, str] = Field(default_factory=dict)

    build_session_lease_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    modeling_batch_max_items: int = Field(default=100, ge=1, le=10_000)
    modeling_batch_max_request_bytes: int = Field(default=1_048_576, ge=1024)
    modeling_batch_max_inline_evidence: int = Field(default=100, ge=0, le=10_000)
    modeling_batch_max_evidence_excerpt_chars: int = Field(default=20_000, ge=1)
    modeling_batch_recovery_max_steps: int = Field(default=3, ge=1, le=100)
    modeling_batch_execution_claim_ttl_seconds: int = Field(default=300, ge=30, le=3600)

    # Phase 7 canonical RDF dataset migration controls. These settings govern the
    # source-of-truth transition from legacy product behavior to the governed RDF
    # dataset path. Modes are resolved per scope by the migration orchestrator.
    semantic_canonical_store: str = "legacy"
    semantic_product_write_mode: str = "legacy_only"
    semantic_read_mode: str = "legacy"
    semantic_legacy_write_blocked: bool = False
    semantic_migration_batch_size: int = Field(default=200, ge=1, le=10_000)
    semantic_migration_parity_required: bool = True
    semantic_migration_phase2_mapping_version: str = "phase2-v1"
    semantic_migration_default_scope: str = "ad_hoc"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("ontology_ui_origins", mode="before")
    @classmethod
    def parse_ui_origins(cls, value):
        if isinstance(value, str):
            value = [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        if "*" in value:
            raise ValueError("ONTOLOGY_UI_ORIGINS must not contain '*'")
        return value
