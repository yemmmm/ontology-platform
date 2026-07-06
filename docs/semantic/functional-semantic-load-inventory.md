# Functional Semantic-Load Inventory

## Purpose

This inventory classifies every current frontend page, backend endpoint group, and
MCP tool by how much semantic state it reads or writes. It is the input used to
decide, for each existing feature, whether to:

- **R — Rebuild** on top of the RDF canonical store (Oxigraph).
- **P — Project-bridge** the existing UI concept onto graph-derived read models
  and route writes through the canonical-write service.
- **K — Keep** the current Postgres / operational implementation unchanged.

It is a planning artifact, not a phase design. Each **R** row here will become a
scoped rebuild task; each **P** row will become a projection-wiring task; **K**
rows document why a feature stays out of the semantic cutover scope.

## Sources

- ADR `docs/adr/0004-semantic-web-first-refactor-target.md`
- Phase 7 `docs/semantic/phase7-canonical-rdf-dataset-migration.md`
- Phase 8 `docs/semantic/phase8-frontend-workflow-reshaping.md`
- Backend route registrations: `backend/app/api/routes.py`
- Frontend workspace shell: `frontend/src/App.tsx`
- Generated on 2026-07-06.

## Disposition Summary

| Disposition | Pages | Backend routes (approx) | MCP tools |
| --- | --- | --- | --- |
| **R** Rebuild | 7 | ~50 | 22 deleted |
| **P** Projection-bridge | 5 | ~10 | 0 |
| **K** Keep | 4 | ~25 | 13 kept |

## Stage 1 — Intake

| Page / feature | Current backend | Semantic dimension | Disposition | Notes |
| --- | --- | --- | --- | --- |
| `BuildOverviewPage` overview | `/projects/{id}/build-context`, `/ontologies/{id}/versions`, `/ontologies/{id}/proposals` | cross-semantic aggregation | **P** | The page itself writes no semantic state. Replace version/proposal status reads with a graph-set + validation/reasoning/rule staleness read model. |
| `ProjectBriefPage` brief | `/projects/{id}/brief` (GET/PATCH) | non-semantic | **K** | Plain-text project metadata. Stays in Postgres. |
| `CompetencyQuestionsPage` competency questions | `/projects/{id}/competency-questions`, `/competency-questions/{id}/validate` | partial semantic | **P** | CRUD stays in Postgres. `validate` currently runs SPARQL-style checks; rebuild to call SHACL or SPARQL CONSTRUCT over the active graph set. |
| Sources (file list) | `/projects/{id}/evidence-artifacts`, `/source-documents` | file artifacts | **K** | Binary artifacts and parsed chunks are operational data. The binding from a chunk to a fact (evidence semantics) moves to RDF — see Stage 2 `FactAuditPage`. |
| Topology (placeholder) | — | — | **R** (new design) | Currently an empty reserved panel. Rebuild on top of the Neo4j projection + graph-set membership. |

## Stage 2 — Modeling / Knowledge

| Page / feature | Current backend | Semantic dimension | Disposition | Notes |
| --- | --- | --- | --- | --- |
| `ClassesPage` class management | `/ontologies/{id}/classes`, `/classes/{id}`, `/classes/{id}/properties`, `/ontologies/{id}/relation-types` | schema (core) | **R** | Rewrite as a SHACL-shape-driven workbench. Left tree populated from `graph/ontology/{id}` OWL classes/properties; right form populated from `graph/shapes/{id}`. `create_class` / `create_property` / `create_relation_type` route through `/canonical-writes:compile-and-apply`. Legacy endpoints deleted. |
| `EntitiesPage` entity editing | `/ontologies/{id}/entities`, `/ontologies/{id}/entities/{id}`, `/relations`, `/entities/validate` | data (core) | **R** | An entity is an RDF resource. Form fields derive from the SHACL shape. Save equals a governed semantic edit writing into `graph/data/{id}`. Validation calls `/validation-runs` instead of the legacy synchronous endpoint. |
| `FactAuditPage` fact audit | `/versions/{id}/fact-claims`, `:generate`, `:sample`, `/fact-claims/{id}/review`, `/versions/{id}/rule-definitions:execute`, `/versions/{id}/background-knowledge:recall` | data + evidence + rule-derived + reasoning | **R** | Deepest rebuild in the platform. Today every fact shares one table. After rebuild, facts must be split by `AssertionKind`: asserted / inferred / rule-derived / missing-evidence, sourced from `graph/data`, `graph/reasoning-result`, `graph/rule-result`, and missing-evidence markers respectively. `:generate` triggers a reasoning run; `recall` becomes a SPARQL query. |
| `CatalogWizardPage` catalog and mappings | `/data-sources`, `/data-resources`, `/external-fields`, `/semantic-mappings`, `/connector-templates` | mixed (connectors operational, mappings semantic) | **split** | Connector configuration and credentials stay in Postgres (**K**). `semantic-mappings` rebuild (**R**) as RDF statements in `graph/ontology/{id}` or `graph/import/{source_id}/{run_id}` mapping external fields to classes/properties. Connector execution results feed projections. |

## Stage 3 — Publish

| Page / feature | Current backend | Semantic dimension | Disposition | Notes |
| --- | --- | --- | --- | --- |
| `PublicationPage` publication readiness | `/versions/{id}/publication-readiness`, `/versions/{id}/mutability`, `/versions/{id}/publish` | concept replaced | **R** | The draft→published state machine is explicitly retired by ADR 0004; the new model gives each actual graph its own editability switch. Rewrite the page as a graph-set readiness dashboard: validation/reasoning/rule staleness, missing-evidence count, projection freshness. "Publish" becomes "lock ontology/data graphs in this graph set + export a package." |
| `VersionsPage` versions and diff | `/ontologies/{id}/versions`, `/versions/{from}/diff/{to}` | version boundary | **R** | A version is no longer a Postgres row. It becomes the combination of a graph set and its current effective derived-result pointers. Diff is the RDF delta between two graph sets, building on `RdfStoreRepository.apply-dataset-delta`. Legacy `versions` table deleted. |

## Stage 4 — Tools

| Page / feature | Current backend | Semantic dimension | Disposition | Notes |
| --- | --- | --- | --- | --- |
| `EntitiesSearchPage` search | `/entities/search`, `/ontologies/{id}/entities/search` | semantic consumer | **P** | Search results must carry `AssertionKind`, graph IRI, and provenance. Backend joins the search projection against `graph/data`. |
| `AgentTestPage` agent test | `/agent-test/run` | semantic consumer | **P** | Question → SPARQL or graph-derived read-model query. Responses distinguish asserted vs inferred vs rule-derived. |
| `EvidenceExplorer` evidence browser | `/evidence-artifacts/{id}`, `/chunks`, `/proposals/{id}/items/{key}/sources` | files + evidence bindings | **split** | File and chunk rendering stays in Postgres (**K**). The "evidence→fact" binding rebuild (**R**) by reading `prov:wasDerivedFrom` triples. |
| `McpToolsPage` MCP tools | static frontend list | metadata | **P** | Replace hardcoded tool list with a dynamic enumeration from `/mcp/tools`. Content points at the semantic MCP set in `backend/app/mcp/tools/semantic.py`. |
| Settings (runtime status) | `/health/dependencies`, `/health/neo4j`, `/health/postgres` | operational | **K** | Pure runtime telemetry. Stays unchanged. |
| Knowledge conflicts (no UI) | `/ontologies/{id}/knowledge-conflicts`, `/conflicts/{id}/resolve` | reasoning output | **R** | Currently surfaced in no page. After rebuild, becomes a section of the OWL consistency report inside the governance dashboard. |

## Stage 5 — Governance (already built)

These six tabs were added by Phase 8. They remain as-is, but their role shifts
once Stages 2 and 3 are rebuilt: from "the only entry point into semantic
capabilities" to "the expert and auditor view of an otherwise graph-native
product."

| Page | Backend |
| --- | --- |
| `GraphGovernancePage` | `/status`, `/derived-results:gc`, `/edits/audits` |
| `NamedGraphsPage` | `/graphs`, `/graphs/{iri}`, `/graphs/{iri}/editability` |
| `GraphSetPage` | `/graph-sets`, `/graph-sets/{id}`, `/graph-sets/{id}/members`, `/graph-sets/{id}/export` |
| `SemanticEditWorkbenchPage` | `/edits`, `/validation-runs`, `/reasoning-runs`, `/edits/audits` |
| `SemanticRunsPage` | `/validation-runs/{id}`, `/reasoning-runs/{id}`, `/rule-runs/{id}`, `/rule-definitions` |
| `SemanticImportExportPage` | `/datasets:load`, `/sparql:query`, `/graph-sets/{id}/export` |

## MCP Tools

`backend/app/mcp/tools/` currently hosts two parallel sets. The legacy set is
mostly thin wrappers over the legacy endpoints and becomes obsolete once the
endpoints it wraps are removed.

| File | Wraps | Disposition |
| --- | --- | --- |
| `graph.py` (5 tools) | entity/relation search and validate | **delete** — replaced by semantic SPARQL and read-model tools |
| `facts.py` (5 tools) | fact-claim CRUD, rule execution | **delete** — rule execution has its semantic counterpart |
| `documents.py` (6 tools) | file artifacts and chunks | **keep** — operational |
| `catalog.py` (10+ tools) | data sources, resources, mappings | **split** — connector parts kept, mapping parts moved into semantic |
| `interview.py` (7 tools) | brief, competency questions | **keep** — non-semantic |
| `proposals.py` (10 tools) | proposals, versions, publish | **delete** — draft→published model retired |
| `publication.py` | publish, readiness | **delete** — same |
| `system.py` | health | **keep** |
| `semantic.py` | SPARQL, validation, reasoning, rules, migration | **keep and extend** — must absorb coverage lost by the deleted modules |

## Delete Candidates

Endpoints and UI entries that no longer have a corresponding concept after the
RDF cutover. They should be marked deprecated once the canonical write mode is
switched on, and removed after one release cycle.

- `/ontologies/{id}/versions`, `/versions/{id}/*` — replaced by graph-set +
  effective derived-result pointers
- `/ontologies/{id}/proposals`, `/proposals/{id}/apply`, `/proposals/{id}/validate`
  — governed semantic edits land on actual graphs directly
- `/versions/{id}/publication-readiness`, `/versions/{id}/publish`,
  `/versions/{id}/mutability` — superseded by per-graph editability
- `/ontologies/{id}/graph-consistency`, `/repair` — folded into OWL consistency
  runs and automatic GC
- `/versions/{id}/fact-claims:generate`, `:sample` — replaced by triggering
  reasoning / validation runs
- `/versions/{id}/knowledge:recall`, `/versions/{id}/background-knowledge:recall`
  — replaced by direct SPARQL queries
- `/ontologies/{id}/knowledge-conflicts`, `/conflicts/{id}/resolve` — folded into
  the OWL consistency report

## Rebuild Order

The **R** rows have a dependency chain that constrains the order of work.

1. **ClassesPage first.** Its SHACL shape output drives every downstream form.
   Cannot rebuild entities, facts, or publication without it.
2. **EntitiesPage.** Depends on class shapes; produces the bulk of `graph/data`
   writes that fact audit and publication consume.
3. **FactAuditPage.** Depends on entity data, reasoning runs, and rule runs all
   existing. Largest single rebuild effort.
4. **PublicationPage + VersionsPage together.** They consume the outputs of
   steps 1–3 and present graph-set readiness.
5. **Catalog mapping rebuild** can run in parallel from step 2 onward, since it
   only depends on class/property definitions existing.
6. **Topology canvas** lands last; it is a pure projection view over a stable
   graph set.

**P** rows can be deferred until the **R** rows they consume are stable. **K**
rows require no work outside the evidence-binding piece, which is part of
FactAuditPage.

## Read-Model Contract Discipline

Before any **R** page is rebuilt, the read model it consumes must be defined as
a Phase 6 read-model endpoint under `/graph-sets/{id}/read-models/{name}`. The
contract must specify:

- fields, including `AssertionKind`, graph IRI, graph-set id, staleness state,
  evidence status, and provenance where relevant
- whether derived fields are allowed to be stale
- field sets (`summary` vs `detail`)
- pagination shape

Frontend pages are written against this contract; backend projection writers are
responsible for keeping the underlying data fresh.

## Open Questions

These are not resolved by the inventory itself and need a separate decision
before rebuild work starts.

- **Migration window.** Will legacy endpoints stay available in shadow mode for
  one release, or be hard-removed as soon as their replacements are live?
- **Top-level navigation.** After Stages 2 and 3 are graph-native, does the
  `Governance` stage stay as a separate top-level entry, or do its tabs fold
  back into Modeling/Publish as sub-views?
- **Identifier stability.** Phase 2 IRI mapping is the migration contract for
  existing product objects. Need to confirm whether legacy primary keys must
  remain resolvable after the legacy tables are dropped.
- **SHACL shape provenance.** Shapes can be hand-authored or generated from
  OWL. The rebuild assumes generated shapes from `graph/shapes/{ontology_id}`;
  need to confirm the generation pipeline is stable.
