from unittest.mock import Mock, patch

from app.cli.backfill_embeddings import run_backfill
from app.core.config import Settings


def test_backfill_updates_stale_entities_and_skips_current_entities() -> None:
    settings = Settings(embedding_api_key="secret", embedding_dimensions=256, _env_file=None)
    driver = Mock()
    client = Mock(model="embedding-3", dimensions=256)
    client.embed.return_value = [[0.1] * 256]
    stale = {
        "id": "a",
        "name": "Alice",
        "aliases": [],
        "properties": {},
        "has_embedding": False,
    }
    current = {
        "id": "b",
        "name": "Bob",
        "aliases": [],
        "properties": {},
        "has_embedding": True,
    }
    from app.services.embedding import entity_embedding_text
    import hashlib

    source = entity_embedding_text(current)
    current.update(
        embedding_model="embedding-3",
        embedding_dimensions=256,
        embedding_source_hash=hashlib.sha256(source.encode()).hexdigest(),
    )

    with (
        patch("app.cli.backfill_embeddings.EmbeddingClient", return_value=client),
        patch("app.cli.backfill_embeddings.create_neo4j_driver", return_value=driver),
        patch("app.cli.backfill_embeddings.ensure_graph_constraints"),
        patch(
            "app.cli.backfill_embeddings.graph_repo.list_entity_embedding_records",
            side_effect=[[stale, current], []],
        ),
        patch(
            "app.cli.backfill_embeddings.graph_repo.update_entity_embedding"
        ) as update_embedding,
    ):
        assert run_backfill(settings) == (1, 1)

    update_embedding.assert_called_once()
    assert update_embedding.call_args.args[1] == "a"
    driver.close.assert_called_once()
