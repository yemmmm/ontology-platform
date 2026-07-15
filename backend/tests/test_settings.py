from app.core.config import Settings


def test_competency_question_sparql_timeout_default():
    settings = Settings()
    assert settings.competency_question_sparql_timeout_seconds == 5.0


def test_competency_question_sparql_timeout_override():
    settings = Settings(competency_question_sparql_timeout_seconds=10.0)
    assert settings.competency_question_sparql_timeout_seconds == 10.0


def test_modeling_batch_capacity_and_recovery_defaults():
    settings = Settings()
    assert settings.modeling_batch_max_items == 100
    assert settings.modeling_batch_max_request_bytes == 1_048_576
    assert settings.modeling_batch_max_inline_evidence == 100
    assert settings.modeling_batch_max_evidence_excerpt_chars == 20_000
    assert settings.modeling_batch_recovery_max_steps == 3
    assert settings.modeling_batch_execution_claim_ttl_seconds == 300
