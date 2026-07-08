# Phase 1 Semantic Runtime Spine

Date: 2026-07-04

This document turns Phase 1 of the standard semantic-language refactor into an implementation
checklist. It follows `semantic-language-refactor-plan.md` and
`docs/semantic/phase0-technical-foundation.md`.

## Goal

Install the selected semantic stack as a real backend boundary while keeping existing product
behavior unchanged.

Phase 1 is a sidecar semantic runtime POC. Existing product APIs continue to use the current
Postgres-backed implementation. The Phase 1 semantic runtime proves the new boundaries
before later phases map or migrate current product behavior into RDF.

## Confirmed Decisions

1. Phase 1 adds an independent `semantic runtime POC` path and does not migrate existing product
   APIs to RDF.
2. Oxigraph is a first-class local development service in `docker-compose.yml` and
   `scripts/start-local.sh`, while `OXIGRAPH_URL` remains configurable for external services.
3. Postgres stores only operational semantic-runtime metadata:
   graph editability state, validation runs, reasoning runs, and projection jobs.
4. Phase 1 POC APIs live under `/api/semantic/...`.
5. `POST /api/semantic/edits` initially supports Turtle, TriG, JSON-LD, `INSERT DATA`, and
   `DELETE DATA`. `DELETE/INSERT WHERE` is deferred to Phase 3.

## Non-Goals

- Do not migrate existing `metadata`, `graph`, `governance`, `facts`, or `catalog` product APIs to
  RDF in Phase 1.
- Do not store RDF triples, quads, facts, evidence semantics, or IRI mappings in Postgres.
- Do not implement full query security, graph visibility policy, RBAC, or permission enforcement.
- Do not implement full SPARQL Update governance beyond explicit `INSERT DATA` and `DELETE DATA`.
- Do not persist a full semantic edit audit table yet; durable edit audit belongs to Phase 3.

## API Surface

The Phase 1 POC API surface is:

- `POST /api/semantic/datasets:load`
- `POST /api/semantic/sparql:query`
- `POST /api/semantic/validation-runs`
- `POST /api/semantic/reasoning-runs`
- `POST /api/semantic/edits`
- `PATCH /api/semantic/graphs/{graph_iri:path}/editability`
- `GET /api/semantic/export`

`sparql:query` is read-only. All semantic writes, including constrained SPARQL Update, go through
`semantic/edits`.

## Phase 1 Design

### Runtime Boundary

Phase 1 introduces a semantic sidecar boundary without changing the existing product source of
truth.

```text
FastAPI /api/semantic
  -> SemanticService
     -> RdfStoreRepository over Oxigraph HTTP
     -> Semantic runtime metadata repositories over Postgres
     -> SHACL validator using rdflib + pySHACL
     -> OWL reasoner runner command boundary
     -> Neo4j projection POC
```

Existing product routers continue to use the current repositories and services. No current
metadata, graph, governance, fact, catalog, or MCP route should depend on the new semantic runtime
until later phases explicitly migrate or project those behaviors.

The implementation should keep these layers separate:

- `backend/app/api/semantic.py`: HTTP request/response mapping and status-code decisions.
- `backend/app/services/semantic.py`: orchestration, validation order, editability checks, and run
  state transitions.
- `backend/app/repositories/rdf_store.py`: Oxigraph HTTP protocol and RDF/SPARQL error mapping.
- `backend/app/services/owl_reasoner.py`: command/service wrapper for OWL reasoning.
- `backend/app/services/semantic_projection.py`: minimal RDF-to-Neo4j projection POC.
- `backend/app/repositories/models.py`: operational metadata only.

### Configuration Contract

Add semantic settings to the existing `Settings` object with safe local defaults:

```text
OXIGRAPH_URL=http://localhost:7878
SEMANTIC_BASE_IRI=http://ontology-platform.local/semantic/
SEMANTIC_GRAPH_IRI_PREFIX=http://ontology-platform.local/semantic/graph/
SEMANTIC_QUERY_TIMEOUT_SECONDS=10
SEMANTIC_QUERY_RESULT_LIMIT=1000
SEMANTIC_SHACL_INFERENCE=none
SEMANTIC_REASONER_COMMAND=
SEMANTIC_REASONER_TIMEOUT_SECONDS=60
```

`semantic_graph_iri_prefix` is the Phase 1 guardrail for platform-managed named graphs. The POC may
read or export arbitrary graphs already in Oxigraph, but governed writes and editability toggles
should default to platform-managed graph IRIs unless a test explicitly overrides the policy.

### Local Service Shape

Local development adds Oxigraph as an independent service, not an embedded library:

- Docker Compose service name: `oxigraph`.
- Host port: `7878`.
- Persistent volume: `oxigraph_data`.
- Readiness check: HTTP request to the Oxigraph endpoint before backend startup reports the
  semantic store as healthy.

`/api/health/dependencies` should include `oxigraph` once the RDF store repository exists. If the
semantic store is unavailable, the health response should report that dependency failure without
changing the existing Postgres and Neo4j checks.

### Postgres Metadata Design

Postgres records semantic runtime operation state. It does not store RDF triples, quads, facts,
evidence semantics, ontology structures, or canonical graph data.

`semantic_graph_states`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key. |
| `graph_iri` | text | Unique named graph IRI. |
| `editable` | bool | Defaults to `true` for newly recorded graphs. |
| `reason` | text nullable | Last lock/unlock reason. |
| `updated_by` | string nullable | Actor supplied by request when available. |
| `created_at` | timestamptz | Server default. |
| `updated_at` | timestamptz | Server default plus update timestamp. |

`semantic_validation_runs`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and API run id. |
| `data_graph_iris` | JSONB array | Graph set validated as data. |
| `shape_graph_iris` | JSONB array | Graph set used as SHACL shapes. |
| `status` | string | `pending`, `running`, `succeeded`, or `failed`. |
| `conforms` | bool nullable | Set after pySHACL completes. |
| `report_graph_iri` | text nullable | Optional future report graph pointer. |
| `started_at` / `finished_at` | timestamptz | Run timing. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Engine options, summary counts, warnings. |

`semantic_reasoning_runs`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and reasoning run id. |
| `source_graph_iris` | JSONB array | Input graph set. |
| `result_graph_iri` | text nullable | `.../graph/reasoning-result/{run_id}` when persisted. |
| `reasoner` | string | Command or configured runner name. |
| `status` | string | `pending`, `running`, `succeeded`, or `failed`. |
| `consistent` | bool nullable | Reasoner consistency result. |
| `started_at` / `finished_at` | timestamptz | Run timing. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Classification, entailment, version, warnings. |

`semantic_projection_jobs`:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string UUID | Primary key and job id. |
| `source_graph_iris` | JSONB array | Input source graphs. |
| `reasoning_result_graph_iri` | text nullable | Optional inferred graph input. |
| `status` | string | `pending`, `running`, `succeeded`, or `failed`. |
| `node_count` / `relationship_count` | int | Result summary. |
| `started_at` / `finished_at` | timestamptz | Job timing. |
| `error` | text nullable | Failure summary. |
| `metadata` | JSONB | Projection options and warnings. |

Do not add `semantic_edit_audits` in Phase 1. Failed or accepted edit details can be returned in
the API response and recomputed in tests; durable edit audit belongs to Phase 3.

### RDF Store Repository Design

`RdfStoreRepository` owns Oxigraph HTTP calls and presents a storage-neutral boundary to services.
The first implementation can use `httpx.Client` or `httpx.AsyncClient`, but it should not expose
HTTP response objects outside the repository.

Required methods:

```python
load_dataset(content: str | bytes, format: RdfFormat) -> DatasetLoadResult
query_sparql(query: str, timeout_seconds: float, limit: int) -> SparqlResult
update_sparql(update: str) -> UpdateResult
export_dataset(format: RdfFormat, graph_iris: list[str] | None = None) -> str
get_graph(graph_iri: str, format: RdfFormat) -> str
graph_exists(graph_iri: str) -> bool
health() -> dict[str, str]
```

Repository error types should distinguish:

- semantic store unavailable
- unsupported RDF format
- RDF parse failure
- SPARQL syntax failure
- query timeout
- query result too large
- update rejected by Oxigraph

The API layer should map these errors to deterministic 4xx/5xx responses. Store connectivity is a
dependency failure. Parse, unsupported format, syntax, locked graph, and unsupported update forms
are client errors.

### API Contract

`POST /api/semantic/datasets:load`

Request:

```json
{
  "content": "...",
  "format": "trig",
  "base_iri": "http://ontology-platform.local/semantic/"
}
```

Response:

```json
{
  "loaded": true,
  "format": "trig",
  "graph_count": 1,
  "triple_count": 3,
  "warnings": []
}
```

If Oxigraph does not return exact counts cheaply, Phase 1 may return `null` counts and cover exact
counts in repository-level tests with a fake store.

`POST /api/semantic/sparql:query`

Request:

```json
{
  "query": "SELECT ?s WHERE { ?s ?p ?o } LIMIT 10",
  "timeout_seconds": 5,
  "result_limit": 100
}
```

The service must reject write forms on this endpoint before forwarding to Oxigraph. At minimum,
reject queries whose parsed or normalized leading operation is `INSERT`, `DELETE`, `LOAD`, `CLEAR`,
`CREATE`, `DROP`, `COPY`, `MOVE`, or `ADD`.

`POST /api/semantic/validation-runs`

Request:

```json
{
  "data_graph_iris": ["http://ontology-platform.local/semantic/graph/data/demo"],
  "shape_graph_iris": ["http://ontology-platform.local/semantic/graph/shapes/demo"],
  "inference": "none"
}
```

Response includes `run_id`, `status`, `conforms`, `report_text`, `summary`, and `error`.

`POST /api/semantic/reasoning-runs`

Request:

```json
{
  "source_graph_iris": ["http://ontology-platform.local/semantic/graph/ontology/demo"],
  "tasks": ["consistency", "classification", "entailment"],
  "persist_result_graph": true
}
```

Response includes `run_id`, `status`, `consistent`, `classification`, `entailments`,
`result_graph_iri`, and `error`. Tests should use a fake reasoner runner.

`POST /api/semantic/edits`

Request:

```json
{
  "format": "trig",
  "content": "...",
  "target_graph_iri": "http://ontology-platform.local/semantic/graph/data/demo",
  "validate": true,
  "actor": "local-dev",
  "reason": "POC edit"
}
```

For `format = "sparql-update"`, Phase 1 accepts only `INSERT DATA` and `DELETE DATA`.
`target_graph_iri` is required for Turtle and JSON-LD edits because those formats do not
necessarily carry a dataset graph boundary. TriG and SPARQL Update may carry graph boundaries in
the payload, but the service still needs to compute the affected graph IRIs before applying.

`PATCH /api/semantic/graphs/{graph_iri:path}/editability`

Request:

```json
{
  "editable": false,
  "actor": "local-dev",
  "reason": "freeze POC graph"
}
```

Because graph IRIs contain slashes, callers should URL-encode `graph_iri` or use query-string
fallback if the router cannot reliably bind the path. The design preference is to keep the path
form and add tests for encoded graph IRIs.

`GET /api/semantic/export`

Query parameters:

```text
format=trig|json-ld|turtle
graph_iri=... repeated, optional
```

Export is read-only and does not consult editability.

### Governed Edit Flow

Semantic edit orchestration must be atomic from the caller's perspective:

```text
receive edit
  -> check format support
  -> parse RDF or SPARQL Update
  -> compute affected graph IRIs
  -> reject unsupported SPARQL Update forms
  -> reject locked affected graphs
  -> optionally run SHACL/platform validation against the candidate graph state
  -> apply Oxigraph update
  -> return graph delta and warnings
```

For Phase 1, graph deltas only need to be exact for:

- TriG/Turtle/JSON-LD additions.
- `INSERT DATA`.
- `DELETE DATA`.

The service should avoid best-effort mutation if delta calculation fails. Return a client error
instead of applying an opaque update. `DELETE/INSERT WHERE` is explicitly deferred because it
requires pattern evaluation, candidate-state validation, and more complete audit support.

Validation can start conservative:

- Turtle/JSON-LD edit: parse into the target named graph, validate that candidate graph if shape
  graphs are supplied or configured.
- TriG edit: parse affected named graphs and validate only affected graphs.
- SPARQL `INSERT DATA` / `DELETE DATA`: compute candidate additions/removals before apply where
  practical; skip SHACL only when the request sets `validate=false` and document the warning in the
  response.

### SHACL Validation Design

The SHACL service fetches selected graph content from Oxigraph, combines it with `rdflib.Dataset`,
and calls `pyshacl.validate`.

Inputs:

- data graph IRIs
- shape graph IRIs
- optional ontology graph IRIs for inference context in later phases
- inference mode from settings or request

Outputs:

- `conforms`
- report graph or report text
- counts by severity where available
- run metadata persisted in Postgres

Phase 1 should keep validation synchronous. Async/background validation can be added after the
runtime boundary is stable.

### OWL Reasoner Design

The reasoner boundary is intentionally outside AI logic. It receives RDF/OWL graph materialized from
Oxigraph and returns deterministic reasoning output.

Initial runner contract:

```python
class OwlReasonerRunner:
    def run(
        self,
        source_documents: list[ReasonerInputDocument],
        tasks: list[str],
        timeout_seconds: float,
    ) -> OwlReasonerResult:
        ...
```

The command runner can write source graph exports to a temporary directory, execute the configured
command, parse a small JSON or text result, and optionally return inferred RDF content for
`graph:reasoning-result/{run_id}`. If no command is configured, the API should return a clear
dependency/configuration error. Unit and API tests must use a fake runner so Java/HermiT/Openllet is
not required in CI or local test runs.

### Neo4j Projection POC Design

The projection POC proves directionality: RDF is input, Neo4j is rebuildable output.

Flow:

```text
export selected source graphs from Oxigraph
  -> optionally include current reasoning result graph
  -> parse RDF
  -> map IRI subjects/objects to Neo4j nodes
  -> map IRI predicates to relationships
  -> replace the POC projection subgraph
  -> return node and relationship counts
```

The POC should mark projected nodes and relationships with a projection namespace or job id so a
rebuild can delete only Phase 1 projection data. It must not accept independent semantic writes to
Neo4j.

### Test Strategy

Phase 1 tests should not require a live Oxigraph, HermiT/Openllet, or Neo4j unless explicitly
marked as integration tests. The default backend test suite should use fakes:

- fake RDF store repository with in-memory datasets for service and API tests
- fake OWL reasoner runner with deterministic consistency/classification/entailment output
- fake projection service returning deterministic counts

Repository tests can mock Oxigraph HTTP responses. A later integration suite may exercise the real
Docker Compose stack, but Phase 1 completion should not depend on external Java reasoner setup.

Fixture files live under `backend/tests/fixtures/semantic/` and should be small enough to inspect in
test failures.

### Implementation Order

1. Add config, dependencies, and local Oxigraph wiring.
2. Add Postgres metadata models and migration.
3. Add RDF store repository plus health check.
4. Add semantic service with fake-able dependency boundaries.
5. Add API schemas and router.
6. Add SHACL validation.
7. Add reasoner runner abstraction and fake tests.
8. Add minimal Neo4j projection POC.
9. Add fixtures and acceptance tests.

## Implementation Checklist

### 0. Documentation

- [x] Keep this document linked from `semantic-language-refactor-plan.md`.
- [x] Record Phase 1 as a sidecar semantic runtime POC, not a canonical migration phase.
- [x] Complete Phase 1 design before code implementation.

### 1. Dependencies and Configuration

- [x] Add backend dependencies in `backend/pyproject.toml`:
  - `rdflib`
  - `pyshacl`
  - explicit `httpx`
- [x] Add settings in `backend/app/core/config.py`:
  - `oxigraph_url`
  - `semantic_base_iri`
  - `semantic_graph_iri_prefix`
  - `semantic_query_timeout_seconds`
  - `semantic_query_result_limit`
  - `semantic_shacl_inference`
  - `semantic_reasoner_command`
  - `semantic_reasoner_timeout_seconds`
- [x] Update `.env.example` and the README configuration table.

### 2. Local Services

- [x] Add an `oxigraph` service, port mapping, and volume to `docker-compose.yml`.
- [x] Add Oxigraph host and port configuration to `scripts/start-local.sh`.
- [x] Wait for Oxigraph HTTP readiness during local startup.
- [x] Add an Oxigraph health check through `/api/health/dependencies` or
  `/api/health/semantic-store`.

### 3. Postgres Runtime Metadata

- [x] Add models in `backend/app/repositories/models.py`:
  - `SemanticGraphStateModel`
  - `SemanticValidationRunModel`
  - `SemanticReasoningRunModel`
  - `SemanticProjectionJobModel`
- [x] Add Alembic migration `backend/migrations/versions/0011_semantic_runtime_metadata.py`.
- [x] Make `semantic_graph_states.graph_iri` unique.
- [x] Include `id`, `status`, `started_at`, `finished_at`, `error`, and `metadata` JSON fields on
  run/job records where applicable.
- [x] Do not add RDF triple/quad storage tables.
- [x] Do not add a standalone `semantic_edit_audits` table in Phase 1.

### 4. RDF Store Boundary

- [x] Add `backend/app/repositories/rdf_store.py`.
- [x] Implement an Oxigraph client for:
  - `load_dataset(content, format)`
  - `query_sparql(query, timeout, limit)`
  - `update_sparql(update)`
  - `export_dataset(format, graph_iris?)`
  - `get_graph(graph_iri, format)`
  - `graph_exists(graph_iri)`
- [x] Map repository errors for connection failure, SPARQL syntax failure, timeout, and unsupported
  format.

### 5. Semantic Service

- [x] Add `backend/app/services/semantic.py`.
- [x] Implement dataset load orchestration.
- [x] Guard `sparql:query` as read-only.
- [x] Implement graph editability lookup and update.
- [x] Implement semantic edit parse, delta calculation, validation, editability check, and apply.
- [x] Reject locked graph mutations before applying any mutation.
- [x] Reject unsupported SPARQL Update forms without mutation.
- [x] Coordinate SHACL validation runs.
- [x] Coordinate OWL reasoning runs.
- [x] Coordinate minimal Neo4j projection jobs.

### 6. API Layer

- [x] Add `backend/app/api/semantic.py`.
- [x] Include the semantic router from `backend/app/api/routes.py`.
- [x] Add request and response schemas in `backend/app/api/schemas.py`.
- [x] Implement the seven Phase 1 endpoint categories under `/api/semantic/...`.

### 7. SHACL Validation

- [x] Fetch data graph and shape graph content from Oxigraph.
- [x] Run validation with `pyshacl.validate`.
- [x] Return `conforms` and a validation report summary.
- [x] Store `semantic_validation_runs`.
- [x] Test invalid data returning a non-conformant report.

### 8. OWL Reasoner Boundary

- [x] Add a reasoner runner abstraction, for example `backend/app/services/owl_reasoner.py`.
- [x] Start with a command wrapper configured by settings.
- [ ] Use HermiT as the baseline candidate and Openllet as an evaluation candidate.
- [x] Use a fake runner in tests so unit/API tests do not require a real Java reasoner.
- [x] Return consistency, classification, and entailment summaries.
- [x] Optionally persist inferred statements to `graph:reasoning-result/{run_id}`.
- [x] Store `semantic_reasoning_runs`.

### 9. Neo4j Projection POC

- [x] Add a minimal projection service.
- [x] Accept source graph IRIs and an optional current reasoning-result graph.
- [x] Rebuild a small Neo4j projection from RDF state.
- [x] Return node and relationship counts.
- [x] Store `semantic_projection_jobs`.
- [x] Keep Neo4j projection rebuildable; do not allow independent semantic writes to Neo4j.

### 10. Fixtures and Tests

- [x] Add fixture files under `backend/tests/fixtures/semantic/`:
  - tiny TriG
  - tiny Turtle
  - tiny JSON-LD
  - tiny SHACL shapes
  - tiny OWL example
- [x] Add focused backend tests:
  - `test_semantic_config.py`
  - `test_rdf_store_repository.py`
  - `test_semantic_service.py`
  - `test_semantic_api.py`
  - `test_semantic_validation.py`
  - `test_semantic_reasoning.py`
  - `test_semantic_projection.py`
- [x] Cover these acceptance scenarios:
  - load TriG, query named graph, and export again
  - read SPARQL has timeout/result controls
  - SHACL report is produced by backend `pyshacl`
  - locked graph rejects edit and does not mutate
  - unsupported SPARQL Update returns an error without mutation
  - reasoning result graph does not mutate source graphs
  - Neo4j projection can be rebuilt from RDF state

## Completion Criteria

- [x] `cd backend && uv sync --extra dev`
- [x] `cd backend && uv run alembic upgrade head`
- [x] `cd backend && uv run pytest`
- [x] `./scripts/start-local.sh` starts Postgres, Oxigraph, backend, and frontend.
- [x] Documentation still states that Phase 1 is a runtime spine POC, not the canonical semantic
  migration phase.
