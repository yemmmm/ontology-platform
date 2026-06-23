# HTTP API

Base URL: `http://localhost:8000/api`

The API manages ontology metadata in PostgreSQL and graph instances in Neo4j. Current routes are intended for local MVP use.

## v0.3 Governance Foundation

Version and proposal writes are scoped to a draft `OntologyVersion`. A proposal follows
`proposed -> validating -> validated -> approved/rejected -> applied`; approval and application are
separate operations. Reusing a `(project_id, idempotency_key)` returns the original proposal.

- `POST /api/ontologies/{ontology_id}/versions`: create an initial or successor draft.
- `GET /api/ontologies/{ontology_id}/versions`: list version lineage.
- `GET /api/versions/{from_id}/diff/{to_id}`: compare Schema snapshots and graph counts.
- `POST /api/proposals`: submit a version-scoped proposal and evidence.
- `GET /api/proposals/{proposal_id}`: read its audit log and evidence chain.
- `POST /api/proposals/{proposal_id}/validate`: run deterministic batch validation.
- `POST /api/proposals/{proposal_id}/review`: approve or reject a validated proposal.
- `POST /api/proposals/{proposal_id}/apply`: atomically apply an approved batch.
- `POST /api/versions/{version_id}/publish`: capture immutable Schema and graph snapshots.

Published and deprecated versions reject writes with HTTP `409`. Editing after publication requires a
successor draft whose `parent_version_id` points to the published version.

## Error Format

FastAPI errors use a `detail` field:

```json
{
  "detail": "Ontology not found"
}
```

Request validation errors use FastAPI's list format:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "name"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

Common status codes: `400` invalid ontology/graph data, `404` missing resource, `409` uniqueness or delete conflict, `422` request validation error.

## Health

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | API liveness. |
| `GET` | `/health/postgres` | PostgreSQL check. |
| `GET` | `/health/neo4j` | Neo4j check. |
| `GET` | `/health/dependencies` | PostgreSQL and Neo4j checks. |
| `GET` | `/ontologies/{ontology_id}/graph-consistency` | Audit copied metadata in Neo4j against PostgreSQL. |
| `POST` | `/ontologies/{ontology_id}/graph-consistency/repair` | Repair stale class and relation metadata in Neo4j. |

Example:

```bash
curl http://localhost:8000/api/health/dependencies
```

## Metadata Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/projects` | List projects. |
| `POST` | `/projects` | Create project. |
| `GET` | `/projects/{project_id}` | Get project. |
| `PATCH` | `/projects/{project_id}` | Update project. |
| `DELETE` | `/projects/{project_id}` | Delete project. |
| `GET` | `/projects/{project_id}/ontologies` | List ontologies in project. |
| `POST` | `/projects/{project_id}/ontologies` | Create ontology. |
| `GET` | `/ontologies/{ontology_id}` | Get ontology. |
| `GET` | `/ontologies/{ontology_id}/schema` | Get ontology with classes, properties, and relation types. |
| `PATCH` | `/ontologies/{ontology_id}` | Update ontology. |
| `DELETE` | `/ontologies/{ontology_id}` | Delete ontology. |
| `GET` | `/ontologies/{ontology_id}/classes` | List classes. |
| `POST` | `/ontologies/{ontology_id}/classes` | Create class. |
| `GET` | `/classes/{class_id}` | Get class. |
| `PATCH` | `/classes/{class_id}` | Update class. |
| `DELETE` | `/classes/{class_id}` | Delete class. |
| `GET` | `/classes/{class_id}/properties` | List class properties. |
| `POST` | `/classes/{class_id}/properties` | Create property definition. |
| `GET` | `/properties/{property_id}` | Get property definition. |
| `PATCH` | `/properties/{property_id}` | Update property definition. |
| `DELETE` | `/properties/{property_id}` | Delete property definition. |
| `GET` | `/ontologies/{ontology_id}/relation-types` | List relation types. |
| `POST` | `/ontologies/{ontology_id}/relation-types` | Create relation type. |
| `GET` | `/relation-types/{relation_type_id}` | Get relation type. |
| `PATCH` | `/relation-types/{relation_type_id}` | Update relation type. |
| `DELETE` | `/relation-types/{relation_type_id}` | Delete relation type. |

Create a project:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo","description":"Local ontology workspace"}'
```

Response:

```json
{
  "id": "project-id",
  "name": "Demo",
  "description": "Local ontology workspace",
  "created_at": "2026-06-17T00:00:00Z",
  "updated_at": "2026-06-17T00:00:00Z"
}
```

Create a class:

```bash
curl -X POST http://localhost:8000/api/ontologies/{ontology_id}/classes \
  -H 'Content-Type: application/json' \
  -d '{"name":"Tool","aliases":["Capability"],"parent_class_ids":[]}'
```

Create a property:

```bash
curl -X POST http://localhost:8000/api/classes/{class_id}/properties \
  -H 'Content-Type: application/json' \
  -d '{"name":"status","type":"enum","required":true,"enum_values":["active","deprecated"]}'
```

## Graph Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/entities/search?query=&mode=hybrid&ontology_id=&class_id=&limit=20` | Recall entities globally with optional filters. |
| `GET` | `/ontologies/{ontology_id}/entities?class_id=&limit=50` | List entities. |
| `GET` | `/ontologies/{ontology_id}/entities/search?query=&mode=text&class_id=&limit=20` | Search within one ontology using text, vector, or hybrid mode. |
| `POST` | `/ontologies/{ontology_id}/entities` | Create entity after ontology validation. |
| `GET` | `/ontologies/{ontology_id}/entities/{entity_id}?include_relations=true` | Get entity and optional relation context. |
| `POST` | `/ontologies/{ontology_id}/entities/validate` | Validate entity properties without writing. |
| `GET` | `/ontologies/{ontology_id}/entities/{entity_id}/related?depth=1&direction=both` | Find related entities. |
| `GET` | `/ontologies/{ontology_id}/entities/{entity_id}/explain` | Explain entity with schema and graph context. |
| `PATCH` | `/ontologies/{ontology_id}/entities/{entity_id}` | Update entity. |
| `DELETE` | `/ontologies/{ontology_id}/entities/{entity_id}` | Delete entity if it has no relations. |
| `GET` | `/ontologies/{ontology_id}/relations?entity_id=&relation_type_id=&limit=50` | List relations. |
| `POST` | `/ontologies/{ontology_id}/relations` | Create typed relation. |

Create an entity:

```bash
curl -X POST http://localhost:8000/api/ontologies/{ontology_id}/entities \
  -H 'Content-Type: application/json' \
  -d '{
    "class_id": "class-id",
    "name": "Entity name",
    "aliases": ["Entity alias"],
    "properties": {"status": "active"}
  }'
```

Entity create and searchable updates synchronously call Zhipu Embedding-3. Configure
`EMBEDDING_API_KEY`; provider failures return `502` without writing stale graph data. Search hits
include `score` and `match_source` (`text`, `vector`, or `hybrid`). The global endpoint defaults to
hybrid retrieval, while the ontology-scoped endpoint defaults to text for compatibility.

Backfill existing entities after enabling embeddings:

```bash
cd backend
uv run python -m app.cli.backfill_embeddings
```

Use `--ontology-id ID` to limit the run or `--force` to regenerate current vectors. Batches are
committed incrementally, so rerunning the command resumes by skipping unchanged entities.

Response:

```json
{
  "id": "entity-id",
  "project_id": "project-id",
  "ontology_id": "ontology-id",
  "ontology_version_id": null,
  "class_id": "class-id",
  "class_label": "Tool",
  "name": "Entity name",
  "aliases": ["Entity alias"],
  "properties": {"status": "active"}
}
```

Create a relation:

```bash
curl -X POST http://localhost:8000/api/ontologies/{ontology_id}/relations \
  -H 'Content-Type: application/json' \
  -d '{
    "relation_type_id": "relation-type-id",
    "source_entity_id": "source-entity-id",
    "target_entity_id": "target-entity-id",
    "properties": {}
  }'
```

## Import/Export

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/ontologies/{ontology_id}/export` | Export ontology schema, entities, and relations as JSON. |
| `POST` | `/projects/{project_id}/ontologies/import` | Import the same JSON shape into a project. |

Export includes `ontology`, `classes`, `relation_types`, `entities`, and `relations`.

## Agent Test

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/agent-test/run` | Run a demo ontology-grounded QA request. |

Request:

```json
{
  "ontology_id": "ontology-id",
  "question": "Which service depends on Payment API?"
}
```

Model, API endpoint, API key, and temperature are configured centrally through the
`LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_TEMPERATURE` settings. Response
includes `answer`, `tool_calls`, `graph_context`, `prompt_preview`, `warnings`, and
`errors`. If `LLM_API_KEY` or `LLM_MODEL` is missing, the endpoint returns a
graph-context fallback answer with a warning.
