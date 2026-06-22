import json
from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.services.embedding import (
    EmbeddingClient,
    EmbeddingServiceError,
    entity_embedding_text,
)


def test_entity_embedding_text_is_stable_and_bounded() -> None:
    entity = {
        "name": "Alice",
        "aliases": ["A"],
        "properties": {"z": 1, "a": "x" * 100},
    }

    first = entity_embedding_text(entity, max_chars=80)
    second = entity_embedding_text(entity, max_chars=80)

    assert first == second
    assert len(first) == 80
    assert first.startswith('name: Alice\naliases: A\nproperties: {"a":')


def test_embedding_client_sends_embedding_3_request() -> None:
    settings = Settings(
        embedding_api_key="secret",
        embedding_dimensions=256,
        _env_file=None,
    ).model_copy(update={"embedding_dimensions": 3})
    client = EmbeddingClient(settings)
    response = Mock()
    response.read.return_value = json.dumps(
        {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
    ).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch("app.services.embedding.urlopen", return_value=response) as urlopen:
        assert client.embed(["hello"]) == [[0.1, 0.2, 0.3]]

    request = urlopen.call_args.args[0]
    body = json.loads(request.data)
    assert body == {"model": "embedding-3", "input": ["hello"], "dimensions": 3}
    assert request.headers["Authorization"] == "Bearer secret"


def test_embedding_client_requires_api_key() -> None:
    client = EmbeddingClient(Settings(embedding_api_key="", _env_file=None))

    with pytest.raises(EmbeddingServiceError, match="EMBEDDING_API_KEY"):
        client.embed(["hello"])
