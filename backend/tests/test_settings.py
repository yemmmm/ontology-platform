from app.core.config import Settings


def test_competency_question_sparql_timeout_default():
    settings = Settings()
    assert settings.competency_question_sparql_timeout_seconds == 5.0


def test_competency_question_sparql_timeout_override():
    settings = Settings(competency_question_sparql_timeout_seconds=10.0)
    assert settings.competency_question_sparql_timeout_seconds == 10.0
