import argparse
import hashlib

from app.core.config import Settings
from app.repositories import graph as graph_repo
from app.repositories.neo4j import create_neo4j_driver, ensure_graph_constraints
from app.services.embedding import EmbeddingClient, entity_embedding_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill entity embeddings in Neo4j")
    parser.add_argument("--ontology-id", help="Only backfill one ontology")
    parser.add_argument("--batch-size", type=int, default=64, choices=range(1, 65))
    parser.add_argument("--force", action="store_true", help="Rebuild embeddings that are current")
    return parser.parse_args()


def run_backfill(
    settings: Settings,
    *,
    ontology_id: str | None = None,
    batch_size: int = 64,
    force: bool = False,
) -> tuple[int, int]:
    client = EmbeddingClient(settings)
    driver = create_neo4j_driver(settings)
    updated = 0
    skipped = 0
    after_id = ""
    try:
        ensure_graph_constraints(driver, settings.embedding_dimensions)
        while True:
            records = graph_repo.list_entity_embedding_records(
                driver, ontology_id, after_id, batch_size
            )
            if not records:
                break
            after_id = records[-1]["id"]
            pending: list[tuple[dict, str, str]] = []
            for entity in records:
                source = entity_embedding_text(entity)
                source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
                current = (
                    entity.get("has_embedding")
                    and entity.get("embedding_model") == client.model
                    and entity.get("embedding_dimensions") == client.dimensions
                    and entity.get("embedding_source_hash") == source_hash
                )
                if current and not force:
                    skipped += 1
                else:
                    pending.append((entity, source, source_hash))
            if not pending:
                continue
            vectors = client.embed([source for _, source, _ in pending])
            for (entity, _source, source_hash), vector in zip(pending, vectors, strict=True):
                graph_repo.update_entity_embedding(
                    driver,
                    entity["id"],
                    {
                        "embedding": vector,
                        "embedding_model": client.model,
                        "embedding_dimensions": client.dimensions,
                        "embedding_source_hash": source_hash,
                    },
                )
                updated += 1
    finally:
        driver.close()
    return updated, skipped


def main() -> None:
    args = parse_args()
    settings = Settings()
    updated, skipped = run_backfill(
        settings,
        ontology_id=args.ontology_id,
        batch_size=args.batch_size,
        force=args.force,
    )
    print(f"Embedding backfill complete: updated={updated}, skipped={skipped}")


if __name__ == "__main__":
    main()
