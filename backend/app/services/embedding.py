import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import Settings


class EmbeddingServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntityEmbedding:
    vector: list[float]
    model: str
    dimensions: int
    source_hash: str


class EmbeddingClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.embedding_api_key
        self.base_url = settings.embedding_base_url.rstrip("/")
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.timeout = settings.embedding_timeout_seconds

    def embed(self, inputs: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingServiceError("EMBEDDING_API_KEY is not configured")
        if not inputs:
            return []
        body = {
            "model": self.model,
            "input": inputs,
            "dimensions": self.dimensions,
        }
        request = Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise EmbeddingServiceError(f"Embedding request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise EmbeddingServiceError(f"Embedding request failed: {exc}") from exc

        try:
            rows = sorted(payload["data"], key=lambda item: item["index"])
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError):
            vectors = []
        if len(vectors) != len(inputs) or any(
            not isinstance(vector, list) or len(vector) != self.dimensions for vector in vectors
        ):
            raise EmbeddingServiceError("Embedding response has an invalid vector payload")
        return vectors


def entity_embedding_text(entity: dict[str, Any], max_chars: int = 2000) -> str:
    aliases = ", ".join(str(item) for item in entity.get("aliases", []))
    properties = json.dumps(
        entity.get("properties", {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    text = f"name: {entity['name']}\naliases: {aliases}\nproperties: {properties}"
    return text[:max_chars]


def create_entity_embedding(client: EmbeddingClient, entity: dict[str, Any]) -> EntityEmbedding:
    source = entity_embedding_text(entity)
    vector = client.embed([source])[0]
    return EntityEmbedding(
        vector=vector,
        model=client.model,
        dimensions=client.dimensions,
        source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )


def embedding_properties(embedding: EntityEmbedding) -> dict[str, Any]:
    return {
        "embedding": embedding.vector,
        "embedding_model": embedding.model,
        "embedding_dimensions": embedding.dimensions,
        "embedding_source_hash": embedding.source_hash,
    }
