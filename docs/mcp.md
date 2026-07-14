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
Schema errors and modeling ambiguities. v0.4 validation requires the batch to cite persisted Evidence
and at least one competency question. Candidate data may include `source_kind`
(`domain_concept`, `data_source_structure`, `domain_fact`, or `governance_metadata`) so storage-shaped
candidates remain visibly distinct from domain concepts. Human item edits, merges, decisions, and
final approval are performed through the governance HTTP API and Schema Review workbench; MCP does
not infer those decisions from chat text.

The `ontology-builder` Skill uses these additional semantic tools:

- `propose_schema_changes`: force a proposal to the `schema_change` type.
- `propose_rules`: force a proposal to the `rule` type for governed RuleDefinition candidates.
- `validate_draft`: validate all editable proposals targeting a draft version.
- `list_review_items`: list review batches, counts, states, and deep links for an ontology.
- `get_review_batch`: retrieve one stable batch after an interruption or while waiting; the response includes the workbench `deep_link`.
- `get_publication_readiness`: evaluate publication gates without publishing.
- `check_platform_health`: confirm PostgreSQL and platform services are reachable without direct DB credentials.
- `list_data_sources` / `create_data_source` / `update_data_source`: register and maintain external systems.
- `list_data_resources` / `create_data_resource` / `update_data_resource`: register tables, endpoints, or files; renames propagate to mapping metadata.
- `list_external_fields` / `create_external_field` / `update_external_field`: manage field sensitivity, masking, approval, and audit metadata.
- `list_semantic_mappings` / `create_semantic_mapping` / `update_semantic_mapping`: link ontology objects or entities to cataloged external fields.
- `list_connector_templates` / `create_connector_template` / `update_connector_template`: maintain whitelisted connector query templates.
- `run_connector_query`: execute a whitelisted connector template through platform policy checks.
- `analyze_identifier_resolution`: compare identifier sets without asserting `SAME_AS`.

Fact audit decisions, proposal approval/rejection, conflict resolution, waivers, merges, and
publication are intentionally absent from Agent MCP tools. They require authenticated HTTP and an
explicit user action in the review workbench. Agent-visible natural-language consent is not a
governance decision.

External system credentials and arbitrary SQL are also absent from MCP. Agents can inspect mappings
and request connector templates, but the platform performs deterministic policy checks and records an
audit result for every connector query attempt.

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
  "error": "Human-readable message",
  "error_code": "not_found"
}
```

`error_code` is one of: `not_found`, `validation_error`, `conflict`,
`governance_rejection`, `dependency_error`, `internal_error`.

## Tools

### `search_entities`

Recall entities globally using hybrid search by default. Ontology and class filters are optional.

```json
{
  "query": "payment",
  "mode": "hybrid",
  "ontology_id": "optional-ontology-id",
  "class_id": "optional-class-id",
  "limit": 20
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

## v0.4 Catalog and Connector Tools

### `check_platform_health`

Verify connectivity to platform services. Returns `{"postgres": {"status": "ok"}}`
on success. Use this instead of probing `/api/health/dependencies` over HTTP.

```json
{}
```

### `list_data_sources` / `create_data_source` / `update_data_source`

Register an external system (database, API, file store) and its connection policy. Each project scopes
its own data sources by unique name.

```json
{
  "project_id": "project-id",
  "data_source": {
    "name": "教务系统",
    "source_type": "postgres",
    "owner": "registrar",
    "authority_level": "authoritative",
    "status": "available",
    "connection_policy": {}
  }
}
```

`update_data_source` takes `data_source_id` and an `update` object with the editable fields.

### `list_data_resources` / `create_data_resource` / `update_data_resource`

Register a table, endpoint, or file under a data source. Renaming a resource propagates to the
denormalized `external_resource_name` on every Semantic Mapping that references it.

```json
{
  "project_id": "project-id",
  "data_resource": {
    "data_source_id": "data-source-id",
    "name": "assessment_results",
    "resource_type": "table",
    "authority_level": "authoritative",
    "status": "available"
  }
}
```

### `list_external_fields` / `create_external_field` / `update_external_field`

Register a field with its sensitivity (`public`/`internal`/`confidential`/`restricted`), access policy
(`allow`/`mask`/`approval_required`/`deny`), masking rule, and audit requirement. Field renames
propagate to mapping location metadata.

```json
{
  "project_id": "project-id",
  "external_field": {
    "data_resource_id": "resource-id",
    "name": "id_card_number",
    "data_type": "string",
    "sensitivity": "restricted",
    "access_policy": "approval_required",
    "audit_required": true
  }
}
```

### `list_semantic_mappings` / `create_semantic_mapping` / `update_semantic_mapping`

Map an ontology class, property, relation type, or entity to a cataloged external field with join keys,
validity window, confidence, and owner. Mappings do not change the published ontology version.

```json
{
  "project_id": "project-id",
  "semantic_mapping": {
    "ontology_id": "ontology-id",
    "target_type": "entity",
    "target_id": "student-li-si",
    "field_id": "field-id",
    "join_key": {"entity_property": "student_number", "external_field": "student_no"},
    "confidence": 0.95,
    "owner": "registrar"
  }
}
```

### `list_connector_templates` / `create_connector_template` / `update_connector_template`

Define a whitelisted connector query template and the external fields it may return. The local v0.4
implementation accepts deterministic static rows in `result_schema.rows`.

```json
{
  "project_id": "project-id",
  "connector_template": {
    "data_source_id": "data-source-id",
    "name": "student grade lookup",
    "allowed_field_ids": ["score-field"],
    "parameter_schema": {},
    "result_schema": {"rows": [{"student_number": "S1", "midterm_score": 88}]},
    "access_policy": "allow"
  }
}
```

### `run_connector_query`

Run a whitelisted connector template. The result includes `authorized`, `denial_reason`, `source`,
`queried_at`, and an audit id. This tool does not expose raw database credentials or arbitrary SQL.

```json
{
  "project_id": "project-id",
  "template_id": "template-id",
  "parameters": {"student_number": "S1"},
  "actor_id": "agent-id",
  "approved": false
}
```

### `analyze_identifier_resolution`

Compare two identifier sets and return counts, overlap, coverage, and unmapped values. It does not
create identity mappings, `SAME_AS`, or merge proposals.

```json
{
  "left_values": ["S1", "S2"],
  "right_values": ["S2", "S3"]
}
```

## Ontology Building Interview

The following tools use the same interview service as the HTTP API:

- `get_build_context`: read durable project, ontology, brief, and question state before continuing.
- `get_ontology_workspace_context`: read the ready default Graph Set, canonical graph roles,
  revisions, editability, and source signature for one Ontology.
- `repair_ontology_workspace`: dry-run or idempotently repair missing default workspace resources;
  ownership and membership conflicts are reported rather than overwritten.
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

### Evidence artifact and graph-candidate tools

- `list_evidence_artifacts(project_id)`
- `get_evidence_artifact_status(artifact_id)`
- `get_evidence_artifact_chunks(artifact_id, offset?, limit?)`
- `propose_entities(proposal)`
- `propose_relations(proposal)`
- `propose_entity_merges(proposal)`
- `propose_rules(proposal)`

The `propose_*` tools are convenience wrappers around `submit_proposal` that force the matching
`proposal_type` (`entity` / `relation` / `merge` / `rule`); they accept the same payload shape.
Entity, relation, and rule items require persisted Evidence. Merge proposals never merge entities at
submission time and still require validation plus an explicit platform review decision. Rule
proposals validate Class, Property, RelationType, enum values, conditions, and Assertion templates
before a human review can approve them. Files are uploaded as evidence artifacts through the
authenticated HTTP endpoint so binary content is not embedded in MCP arguments.
`validate_proposal` runs current Schema and graph endpoint checks using the shared service.

### Fact audit tools

- `generate_fact_claims(version_id)`: deterministically regenerate structured Fact Claims from the draft graph.
- `list_fact_claims(version_id, layer?, claim_type?)`: list Fact Claims stratified by audit layer.
- `sample_fact_claims(version_id, config?)`: return a stratified fact sample for human audit.
- `execute_rule_definitions(version_id)`: run deterministic rules and write derived Assertions for review.
- `recall_background_knowledge(version_id, query?, query_embedding?, limit?)`: recall unanchored background knowledge separately from governed facts.

Fact-generating tools emit the full `FactClaimRead` shape (id, claim_key, layer, claim_type,
subject, predicate, value, anchor, graph_path, evidence_ids, generation_reason, confidence,
sensitivity, access_policy, override_of_claim_id, audit_status, stale, stale_reason, reviewed_at,
review_decision, linked_fix_proposal_id, project_id, ontology_id, ontology_version_id, created_at,
updated_at). Fact review decisions
(approve/reject/needs_correction) are HTTP-only.

## v1.0 Lightweight Evidence (R-002)

- `create_evidence_reference(project_id, document_name, excerpt, actor?)`
- `list_evidence_references(project_id, search?, limit?, offset?)`
- `get_evidence_reference(reference_id)`
- `associate_evidence_reference(project_id, ontology_id, target_type, target_id, ...)`

These tools store only the document name and exact excerpt supplied by the external Agent. They do
not upload or parse complete source files. References belong to a Project and may support concrete
modeling results in any Ontology in that Project; cross-project IDs are returned as unavailable.
