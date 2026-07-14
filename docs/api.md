# HTTP API

Base URL: `http://localhost:8000/api`

The API manages ontology metadata in PostgreSQL and graph instances. Current routes are intended for local MVP use.

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

## v0.4 Semantic Mapping, Catalog, and Connectors

v0.4 separates ontology semantics from external storage. Ontology Classes, Properties,
RelationTypes, and Entities can be mapped to cataloged external fields without changing a published
ontology version. Connector templates are whitelisted query shapes; the API records every query
attempt and returns authorization metadata instead of exposing database credentials or arbitrary SQL.

- `POST /api/projects/{project_id}/data-sources`: register an external system and owner.
- `POST /api/projects/{project_id}/data-resources`: register a table, endpoint, or file-like resource.
- `POST /api/projects/{project_id}/external-fields`: register field sensitivity, access policy,
  masking, approval, and audit metadata.
- `POST /api/projects/{project_id}/semantic-mappings`: map a class, property, relation type, or
  entity to an external field with join keys, validity, confidence, and owner.
- `POST /api/projects/{project_id}/connector-templates`: define a whitelisted query template and
  the external fields it may return.
- `POST /api/projects/{project_id}/connector-templates/{template_id}/query`: perform policy checks,
  record an audit row, and return source/query authorization metadata.
- `POST /api/projects/{project_id}/identity-resolution/analyze`: compare identifier sets and return
  deterministic overlap/coverage statistics without creating `SAME_AS` or merge facts.

RelationTypes now include `scope_policy` (`schema_allowed`, `entity_only`, or `both`), `symmetric`,
`transitive`, and `status`. Entity-level relations are stored with `scope="instance"`, `status`,
`valid_from`, and `valid_to`; a RelationType explicitly marked `schema_allowed` is rejected for
entity relation writes.

For the local v0.4 connector implementation, `result_schema.rows` can hold whitelisted static rows.
Authorized connector queries filter those rows by exact parameter matches and apply field masking or
approval/deny policies before returning data.
Catalog, field, mapping, and connector template resources expose `PATCH` routes. Renaming an external
resource or field updates the denormalized mapping location metadata and does not require a new
ontology version.

## v0.3 Schema Review

- `GET /api/ontologies/{ontology_id}/proposals?proposal_type=schema_change` lists Schema batches.
- `GET /api/ontologies/{ontology_id}/review-batches` lists stable batches and workbench deep links.
- `GET /api/review-batches/{review_batch_id}` reads one stable batch for interrupted Agent recovery.
- `POST /api/proposals/{proposal_id}/items/{item_key}/review` approves, rejects, edits, or merges one
  candidate. Editing or merging invalidates its previous validation.
- `POST /api/proposals/{proposal_id}/items/review` approves or rejects multiple candidates.

Schema validation detects name conflicts, inheritance cycles, cross-ontology references, invalid
Property domain/range, invalid RelationType endpoints and duplicate definitions. It also returns
Class-versus-Entity and Property-versus-RelationType ambiguities for human review. Proposal items may
be `class`, `property`, `relation_type`, or `constraint`; schema proposals must cite persisted
Evidence and at least one competency question before validation can pass. Candidate data may include
`source_kind` as `domain_concept`, `data_source_structure`, `domain_fact`, or
`governance_metadata` so reviewers can distinguish domain concepts from storage-derived structures.
Final approval requires an explicit decision on every item. Applying the batch uses one PostgreSQL
transaction and records a non-destructive compatibility check of existing graph data.

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
| `GET` | `/health/dependencies` | PostgreSQL and graph checks. |
| `GET` | `/ontologies/{ontology_id}/graph-consistency` | Audit copied metadata against PostgreSQL. |
| `POST` | `/ontologies/{ontology_id}/graph-consistency/repair` | Repair stale class and relation metadata. |

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
| `POST` | `/projects/{project_id}/ontologies` | Create ontology and its ready default semantic workspace atomically. |
| `GET` | `/ontologies/{ontology_id}/workspace-context` | Read the default Graph Set, graph roles, revisions, editability, and source signature. |
| `POST` | `/ontologies/{ontology_id}/workspace/repair` | Idempotently repair one ontology workspace; accepts `{ "dry_run": true|false }`. |
| `POST` | `/projects/{project_id}/ontology-workspaces/repair` | Inspect or repair all historical ontology workspaces in a project. |
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
    "properties": {},
    "scope": "instance",
    "status": "active",
    "valid_from": "2026-06-25",
    "valid_to": null
  }'
```

## Catalog Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/projects/{project_id}/data-sources` | List external data sources. |
| `POST` | `/projects/{project_id}/data-sources` | Register an external data source. |
| `PATCH` | `/projects/{project_id}/data-sources/{data_source_id}` | Update source metadata. |
| `GET` | `/projects/{project_id}/data-resources` | List catalog resources. |
| `POST` | `/projects/{project_id}/data-resources` | Register a source resource. |
| `PATCH` | `/projects/{project_id}/data-resources/{resource_id}` | Update resource metadata and mapping location names. |
| `GET` | `/projects/{project_id}/external-fields` | List fields with sensitivity and policy metadata. |
| `POST` | `/projects/{project_id}/external-fields` | Register an external field. |
| `PATCH` | `/projects/{project_id}/external-fields/{field_id}` | Update field policy/location metadata. |
| `GET` | `/projects/{project_id}/semantic-mappings` | List mappings, optionally filtered by ontology and target. |
| `POST` | `/projects/{project_id}/semantic-mappings` | Create a semantic mapping to an external field. |
| `PATCH` | `/projects/{project_id}/semantic-mappings/{mapping_id}` | Update mapping target, join key, validity, confidence, owner, or field. |
| `GET` | `/projects/{project_id}/connector-templates` | List whitelisted connector templates. |
| `POST` | `/projects/{project_id}/connector-templates` | Create a connector template. |
| `PATCH` | `/projects/{project_id}/connector-templates/{template_id}` | Update whitelisted connector template metadata. |
| `POST` | `/projects/{project_id}/connector-templates/{template_id}/query` | Run policy checks and audit a connector query. |
| `POST` | `/projects/{project_id}/identity-resolution/analyze` | Analyze cross-system identifier overlap. |

## Import/Export

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/ontologies/{ontology_id}/export` | Export ontology schema, entities, and relations as JSON. |
| `POST` | `/projects/{project_id}/ontologies/import` | Import the same JSON shape into a project. |

Export includes `ontology`, `classes`, `relation_types`, `entities`, and `relations`.

## External Agent Build Sessions

Build Context and Build Sessions are Project-scoped. A session can report work on several Ontologies,
while an Ontology Lease protects writes to one Ontology at a time. Ordinary Agent requests use
Project, Build Session, and Ontology IDs; they do not carry Graph Set IDs or graph IRIs.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/projects/{project_id}/build-context?recent_session_limit=10&recent_session_cursor=0` | Read platform facts plus paged active/recent Agent session state for the whole Project. |
| `POST` | `/projects/{project_id}/build-sessions` | Idempotently create a Build Session and optional initial Checkpoint. |
| `GET` | `/build-sessions/{session_id}` | Read paged Checkpoints, involved Ontologies, lease summaries, and recent activity. |
| `POST` | `/build-sessions/{session_id}:resume` | Resume an active session without incrementing its revision. |
| `POST` | `/build-sessions/{session_id}/checkpoints` | Idempotently append a progress Checkpoint. |
| `POST` | `/build-sessions/{session_id}:complete` | Complete a session and release all its Ontology leases. |
| `POST` | `/build-sessions/{session_id}:cancel` | Cancel a session and release all its Ontology leases. |
| `POST` | `/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire` | Acquire or rotate an Ontology write lease. |
| `POST` | `/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew` | Renew a valid lease. |
| `POST` | `/build-sessions/{session_id}/ontology-leases/{ontology_id}:release` | Idempotently release a valid lease. |

Every mutation uses a stable client ID. Checkpoint, complete, and cancel calls also carry the latest
session revision. Lease tokens are returned only by acquire/renew and are stored only as SHA-256
hashes. Build Context, session detail, logs, and ordinary error responses never contain a token.
The server controls lease lifetime through `BUILD_SESSION_LEASE_TTL_SECONDS` (default `300`).

Build-session errors use a structured detail object, for example:

```json
{
  "detail": {
    "code": "session_revision_conflict",
    "message": "Build Session changed after the caller last read it",
    "current_revision": 4
  }
}
```

Stable conflict codes include `idempotency_conflict`, `session_revision_conflict`,
`session_terminal`, `ontology_lease_conflict`, `lease_revision_conflict`, `lease_expired`, and
`workspace_revision_conflict`.

## Project Interview and Competency Questions

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/projects/{project_id}/brief` | Read fields, completeness, missing fields, and up to three clarification items. |
| `PATCH` | `/projects/{project_id}/brief` | Update, confirm, or skip fields and attach saved answer IDs. |
| `POST` | `/projects/{project_id}/interview-answers` | Save a traceable conversation answer. |
| `GET` | `/projects/{project_id}/competency-questions` | List active questions in explicit order. |
| `POST` | `/projects/{project_id}/competency-questions` | Create a draft question with answer or brief sources. |
| `PATCH` | `/competency-questions/{question_id}` | Edit, reorder, deactivate, or reactivate a question. |
| `POST` | `/competency-questions/{question_id}/status` | Apply a validated question state transition. |

Required brief fields are `domain_name`, `business_goal`, `scope`, `core_concepts`,
`identity_rules`, and `expected_granularity`. Optional fields may be skipped; the response explains
the quality impact.
Question transitions are `draft -> approved -> testable -> passed/failed`. Approval requires a
saved answer or confirmed Project Brief source. Changing a cited brief field moves a tested question
back to `approved` with `validation_result.stale=true`.

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

## v0.3 Evidence Artifact Storage and Knowledge Candidates

- `POST /api/projects/{project_id}/evidence-artifacts` uploads a multipart `file` (PDF,
  Markdown, or UTF-8 text), parses it synchronously, and returns parse status and chunk count.
- `GET /api/projects/{project_id}/evidence-artifacts` lists artifact status.
- `GET /api/evidence-artifacts/{artifact_id}` reads one artifact status.
- `POST /api/evidence-artifacts/{artifact_id}/reparse?force=true` creates a new parse revision;
  old chunks remain immutable so existing Evidence stays valid. Without `force`, unchanged
  successfully parsed content reuses the current revision.
- `GET /api/evidence-artifacts/{artifact_id}/chunks` returns the current parse revision with page,
  sequence, document-relative character range, text, and SHA-256 hash.
- `GET /api/evidence-artifacts/{artifact_id}/proposals` lists all candidates citing an artifact.
- `GET /api/proposals/{proposal_id}/items/{item_key}/sources` returns all Evidence for one item.
- `GET /api/ontologies/{ontology_id}/knowledge-conflicts` lists conflicting candidate values.
- `POST /api/knowledge-conflicts/{conflict_id}/resolve` records an explicit human resolution.

Entity and relation proposal items support canonical `name`, `aliases`, `properties`, relation
properties, and `confidence`. Every item must bind at least one saved artifact or user-statement
Evidence record. Artifact Evidence is rejected unless its artifact, chunk, page, character range,
quote, and chunk hash agree. Repeated extraction runs should reuse the same project-scoped proposal
`idempotency_key`; retries return the existing proposal and application uses stable item keys.

Artifact bytes and extracted text are inert evidence data. The ingestion service does not interpret
commands in an artifact or invoke models/tools while parsing. External Agents read chunks, extract
candidate knowledge, and submit evidence-bound proposals.

## v0.5 Anchored Assertions, Background Recall, and Rules

- `POST /api/versions/{version_id}/assertions` creates an anchored Assertion backed by the
  extended Fact Claim model. `anchor.type` must be one of `unanchored`, `entity`, `relation`,
  `class`, or `rule`; Class and Rule anchors are validated against the current ontology.
- `POST /api/versions/{version_id}/background-knowledge` stores unanchored background knowledge
  with source, summary, embedding, tags, confidence, and applicability. It is stored separately from
  core Assertions and does not participate in publication gates.
- `POST /api/versions/{version_id}/background-knowledge:recall` returns background hits marked as
  `source_type=background_recall` and `core_fact=false`.
- `POST /api/versions/{version_id}/background-knowledge/{knowledge_id}:promote` creates a normal
  governed Proposal from background knowledge and records `promoted_proposal_id`; the promoted
  content must still pass Proposal, Evidence, Review, and Assertion/RuleDefinition application.
- `POST /api/versions/{version_id}/rule-definitions` stores a validated, immediately usable
  `RuleDefinition`.
  Supported `rule_type` values are `classification`, `derived_relation`, `validation`, and
  `workflow`.
- Rule candidates are checked against referenced Class, Property, RelationType, enum values,
  conditions, and Assertion templates before storage.
- `POST /api/versions/{version_id}/rule-definitions:execute` runs deterministic rules
  against the current graph snapshot and writes only derived or validation Assertions for review.
- `POST /api/versions/{version_id}/knowledge:recall` merges entity properties, entity Assertions,
  Class defaults and inherited Class Assertions, overrides, rule-derived Assertions, and optional
  background recall in one response. The request defaults to `authorized=false`; sensitive
  Assertions are masked or withheld according to `access_policy` unless an authorized service
  context explicitly sets `authorized=true`.

`POST /api/versions/{version_id}/fact-claims:generate` refreshes only graph-generated layers such
as direct entity attributes, relation facts, inferred inverse relations, low-confidence flags, and
value-conflict facts. Core v0.5 Assertion and rule layers are preserved across graph fact
regeneration.

Publication readiness now treats pending, stale, rejected-unfixed, and conflicting core Assertions
as blockers. Entity-level overrides are represented with `override_of_claim_id` and are not treated
as conflicts with the Class default they override.

## v1.0 Lightweight Evidence References (R-002)

The v1.0 target does not require complete document upload or parsing. External modeling Agents submit
the exact source excerpt they used:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/projects/{project_id}/evidence-references` | Create or idempotently reuse `{document_name, excerpt}`. |
| `GET` | `/api/projects/{project_id}/evidence-references` | Search and page through project references. |
| `GET` | `/api/evidence-references/{id}` | Read one immutable reference. |
| `GET` | `/api/evidence-references/{id}/associations` | List concrete modeling results supported by the reference. |
| `GET` | `/api/projects/{project_id}/evidence-associations` | Resolve one modeling target back to its full evidence references. |
| `POST` | `/api/projects/{project_id}/evidence-references:resolve` | Dry-run or persist existing IDs and inline excerpts. |
| `POST` | `/api/projects/{project_id}/evidence-associations` | Resolve excerpts and associate one modeling target. |
| `POST` | `/api/projects/{project_id}/evidence-associations:batch` | Dry-run or apply atomic/explicit-partial association items. |

Canonical product writes accept optional `evidence_reference_ids`, inline `evidence`,
`client_item_id`, and `evidence_target_id`. The older Artifact/Chunk endpoints above remain a
compatibility surface and are not the v1.0 R-002 workflow.
