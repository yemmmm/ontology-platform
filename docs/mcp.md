# MCP Tools

## v0.3 Governance Tools

- `submit_proposal`: create or retrieve an idempotent proposal; it never writes formal data.
- `validate_proposal`: run deterministic proposal validation.
- `get_proposal_status`: retrieve the complete audit and evidence chain.

MCP proposal writes use the same governance service and immutability checks as HTTP. Approval and
application, fact review, conflict resolution, and publication remain explicit HTTP/workbench
governance actions rather than natural-language interpretations.

For phase-three Schema construction, `submit_proposal` accepts a `schema_change` batch containing
Class, Property, RelationType, and Constraint candidates. `validate_proposal` returns deterministic
Schema errors and modeling ambiguities. Human item edits, merges, decisions, and final approval are
performed through the governance HTTP API and Schema Review workbench; MCP does not infer those
decisions from chat text.

The `ontology-builder` Skill uses these additional semantic tools:

- `propose_schema_changes`: force a proposal to the `schema_change` type.
- `validate_draft`: validate all editable proposals targeting a draft version.
- `list_review_items`: list review batches, counts, states, and deep links for an ontology.
- `get_review_batch`: retrieve one stable batch after an interruption or while waiting.
- `get_review_workspace_link`: retrieve the exact workbench deep link for a batch.
- `get_publication_readiness`: evaluate publication gates without publishing.

Fact audit decisions, proposal approval/rejection, conflict resolution, waivers, merges, and
publication are intentionally absent from Agent MCP tools. They require authenticated HTTP and an
explicit user action in the review workbench. Agent-visible natural-language consent is not a
governance decision.

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

## Ontology Building Interview

The following tools use the same interview service as the HTTP API:

- `get_build_context`: read durable project, ontology, brief, and question state before continuing.
- `get_project_brief`: return completeness, missing fields, and no more than three clarification items.
- `save_interview_answer`: persist user wording for source traceability.
- `update_project_brief`: update/confirm fields or skip optional fields with explicit impact.
- `list_competency_questions`: read ordered active or inactive questions and validation states.
- `propose_competency_questions`: create draft questions only; it cannot approve them.

Agent tools do not expose question approval. Approval and later validation-state changes remain
governance actions on the authenticated HTTP surface.

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

### Document and graph-candidate tools

- `list_source_documents(project_id)`
- `get_source_document_status(document_id)`
- `propose_entities(proposal)`
- `propose_relations(proposal)`
- `propose_entity_merges(proposal)`

The three proposal tools force their corresponding proposal type and only create governance
candidates. Entity and relation items require persisted Evidence. Merge proposals never merge
entities at submission time and still require validation plus an explicit platform review decision.
Files are uploaded through the authenticated HTTP endpoint so binary content is not embedded in MCP
arguments. `validate_proposal` runs current Schema and graph endpoint checks using the shared service.
