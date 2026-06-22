# MCP Tools

Run the MCP server from the backend environment:

```bash
cd backend
python -m app.mcp.server
```

All tools return:

```json
{
  "ok": true,
  "data": {}
}
```

On failure they return:

```json
{
  "ok": false,
  "error": "Error message"
}
```

## Tools

### `search_entities`

Recall entities globally using hybrid search by default. Ontology and class filters are optional.

```json
{
  "query": "payment",
  "mode": "hybrid",
  "ontology_id": "optional-ontology-id",
  "class_id": "optional-class-id",
  "limit": 10
}
```

`mode` accepts `text`, `vector`, or `hybrid`. Returns `data.results` and `data.count`; each result
includes a relevance `score` and `match_source`.

### `get_entity`

Fetch one entity and optional relation context.

```json
{
  "ontology_id": "ontology-id",
  "entity_id": "entity-id",
  "include_relations": true,
  "relation_limit": 50
}
```

Returns the entity plus `incoming` and `outgoing` relation arrays.

### `find_related_entities`

Traverse nearby graph context.

```json
{
  "ontology_id": "ontology-id",
  "entity_id": "entity-id",
  "depth": 1,
  "direction": "both",
  "relation_type_ids": ["optional-relation-type-id"],
  "target_class_ids": ["optional-class-id"],
  "limit": 20
}
```

`depth` is capped at 3 and `limit` is capped at 100.

### `validate_entity`

Validate proposed properties against the ontology class schema without writing data.

```json
{
  "ontology_id": "ontology-id",
  "class_id": "class-id",
  "properties": {"status": "active"}
}
```

Returns:

```json
{
  "valid": true,
  "errors": []
}
```

### `explain_entity`

Return entity, class schema, direct relations, related entities, and a short explanation.

```json
{
  "ontology_id": "ontology-id",
  "entity_id": "entity-id",
  "depth": 1,
  "limit": 20
}
```

## Agent Integration Example

```json
{
  "mcpServers": {
    "ontology-platform": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/home/yangxiang/ontology-platform/backend"
    }
  }
}
```

Suggested flow:

1. Call `search_entities` with the user's domain terms.
2. Call `get_entity` or `explain_entity` for the best matches.
3. Call `find_related_entities` when planning or explaining dependencies.
4. Call `validate_entity` before suggesting new graph data.
