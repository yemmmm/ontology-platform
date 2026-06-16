# MCP Tools

Run the MCP server from the backend environment:

```bash
cd backend
python -m app.mcp.server
```

Each tool accepts an optional `api_key` argument. It must match `MCP_API_KEY` from the backend environment.

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
  "error": "Invalid MCP API key"
}
```

## Tools

### `search_entities`

Search entities inside one ontology.

```json
{
  "ontology_id": "ontology-id",
  "query": "payment",
  "class_id": "optional-class-id",
  "limit": 10,
  "api_key": "change-me-mcp-key"
}
```

Returns `data.results` and `data.count`.

### `get_entity`

Fetch one entity and optional relation context.

```json
{
  "ontology_id": "ontology-id",
  "entity_id": "entity-id",
  "include_relations": true,
  "relation_limit": 50,
  "api_key": "change-me-mcp-key"
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
  "limit": 20,
  "api_key": "change-me-mcp-key"
}
```

`depth` is capped at 3 and `limit` is capped at 100.

### `validate_entity`

Validate proposed properties against the ontology class schema without writing data.

```json
{
  "ontology_id": "ontology-id",
  "class_id": "class-id",
  "properties": {"status": "active"},
  "api_key": "change-me-mcp-key"
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
  "limit": 20,
  "api_key": "change-me-mcp-key"
}
```

## Agent Integration Example

```json
{
  "mcpServers": {
    "ontology-platform": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/home/yangxiang/ontology-platform/backend",
      "env": {
        "MCP_API_KEY": "change-me-mcp-key"
      }
    }
  }
}
```

Suggested flow:

1. Call `search_entities` with the user's domain terms.
2. Call `get_entity` or `explain_entity` for the best matches.
3. Call `find_related_entities` when planning or explaining dependencies.
4. Call `validate_entity` before suggesting new graph data.
