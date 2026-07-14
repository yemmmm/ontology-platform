# UI

The frontend is a React/Vite operational workspace in `frontend/`.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` to override the default `http://localhost:8000/api`.

## Implemented Pages

- Projects: list/create/delete projects, list/create/delete ontologies, select active context.
- Build Overview: workflow stage, current version, deterministic blockers, next actions, and recent review batches.
- Project Brief: structured field editing, confirmation/skipping, completeness, clarification, and unsaved-change protection.
- Competency Questions: create/edit/order, approve/testable transitions, activation, and validation results.
- Evidence Artifacts: upload, parse status, chunks, retry/reparse, and links to citing proposals.
- Schema and Graph Review: proposal queues, item decisions, evidence, conflicts, and batch-scoped deep links.
- Fact Audit: generation, stratified sampling, filters, stale-state handling, and approve/reject/correction decisions.
- Publication: deterministic readiness gates, remediation links, final recheck, explicit confirmation, and immutable report.
- Versions: lineage, snapshot metadata, schema/graph diff, and successor drafts from published versions.
- Evidence Explorer: proposal-item evidence, source metadata, chunk location, and integrity warnings.
- Ontology Designer: list/create/delete classes, properties, and relation types.
- Graph Manager: list/create entities and relations, inspect a simple SVG graph view.
- MCP/Agent Test: send a question to `POST /api/agent-test/run`, inspect answer, tool calls, graph context, and prompt preview.
- Health: call `/api/health/dependencies` and show PostgreSQL/Neo4j status.

### v1.0 Evidence References

The Overview navigation includes an Evidence page for the R-002 lightweight workflow. It is a
project-shared ledger even though it is opened from an ontology workspace. Users can create a
reference from only a document name and exact excerpt, search the ledger, inspect hashes and creator
metadata, and see which concrete modeling results cite it. The page explicitly states that the full
document is not uploaded. Workspace lock keeps the ledger readable and disables creation.

## Navigation and Deep Links

Workspace navigation is grouped into Build, Review, Model, and Tools. The selected version is part of
the global workspace context; published versions are visibly read-only.

Review links use URL state as the source of truth:

```text
/?project=<project-id>&ontology=<ontology-id>&version=<version-id>&tab=<tab>&batch=<batch-id>
```

Schema and Graph review also accept `proposal`; Fact Audit accepts `claim`. Invalid cross-project,
cross-ontology, version, or review-type combinations show an error instead of opening unrelated data.

The current backend exposes Evidence through proposal-item sources. Fact Claims contain Evidence IDs
but no proposal/item mapping, so unresolved Fact Evidence is shown as a traceability warning rather
than an inferred source location.

## Data Flow

```text
React UI
  -> FastAPI /api routes
  -> PostgreSQL for ontology metadata
  -> Neo4j for graph instances
```

The UI never connects directly to PostgreSQL or Neo4j.

## Manual Checks

At both 1280 px and 768 px widths, verify Overview, Brief, Questions, Facts, Publication, Versions,
Evidence, and a batch deep link. Exercise loading/empty/error states, confirm published versions expose
no mutation actions, and confirm a failed publication gate keeps Publish disabled.

The Playwright mock-API smoke suite covers workspace loading and navigation through Overview, Brief,
Questions, Facts, Publication, Versions, and Evidence at 1280 px and 768 px, including a horizontal
overflow assertion, blocked publication state, and a fresh-session Schema Review Batch deep link. Run
it with `cd frontend && npm run test:ui`.
