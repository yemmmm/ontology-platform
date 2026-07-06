# Semantic Stage 2 — Modeling / Knowledge Rebuild Design

- **Date:** 2026-07-06
- **Scope driver:** `docs/semantic/functional-semantic-load-inventory.md` → Stage 2 — Modeling / Knowledge
- **Architecture approach:** Just-in-time foundation, dependency-ordered pages (Approach C)
- **Status:** Draft, awaiting user review

## 1. Goal and Non-Goals

### Goal

Rebuild the four Stage 2 modeling pages onto the RDF canonical store (Oxigraph) so that
every read is a graph-derived read-model and every write is a governed canonical-write.
Specifically:

1. **ClassesPage** is rewritten as a SHACL-shape-driven workbench over
   `graph/ontology/{id}` and `graph/shapes/{id}`.
2. **EntitiesPage** is rewritten so an entity is an RDF resource whose form fields derive
   from its class shape; saves are governed semantic edits to `graph/data/{id}`.
3. **FactAuditPage** is rewritten to split facts by `AssertionKind` (`asserted` /
   `inferred` / `rule_derived` / `missing_evidence`), sourced from the corresponding
   graph roles.
4. **CatalogWizardPage** is split: connector configuration stays in Postgres; semantic
   mappings are rebuilt as RDF statements in `graph/ontology/{id}` or
   `graph/import/{source_id}/{run_id}`.

The rebuild follows the dependency chain from
`docs/semantic/functional-semantic-load-inventory.md` Rebuild Order: Classes → Entities →
FactAudit, with Catalog-mapping running parallel from Entities onward.

### Non-Goals

- **Stage 3 — Publish.** `PublicationPage` and `VersionsPage` rebuilds are out of scope.
  They will consume the same graph-set contracts but are sized separately.
- **Stage 4 — Tools.** `EntitiesSearchPage`, `AgentTestPage`, `EvidenceExplorer`,
  `McpToolsPage` are out of scope.
- **Legacy endpoint hard-removal.** Shadow mode keeps legacy endpoints routable throughout
  Stage 2 (see §10). Deletion lands post-Stage-2.
- **OWL reasoner or rule engine replacement.** Stage 2 wires pages onto the existing
  `/reasoning-runs` and `/rule-runs` infrastructure; it does not change the engines.
- **MCP tool rebuild.** The semantic MCP module absorbs coverage lost by the deleted
  legacy modules as a follow-up, not as a Stage 2 deliverable.
- **Topology canvas rebuild.** Per inventory Rebuild Order entry 6, the topology canvas
  lands last as a pure projection over a stable graph set. Stage 2 leaves the current
  placeholder in place.

## 2. Locked-In Decisions

These were resolved during the design dialogue and are not re-opened by this spec.

| Decision | Resolution | Source |
| --- | --- | --- |
| Spec scope | One unified Stage 2 spec | design dialogue 2026-07-06 |
| Sequencing approach | C — just-in-time foundation, dependency-ordered pages | design dialogue |
| Migration window | Shadow mode (legacy kept as fallback during Stage 2) | design dialogue |
| SHACL shape provenance | Generated from OWL as the base layer; hand-authored overlay allowed in a separate `custom` sub-graph | design dialogue |
| Legacy primary-key stability | Legacy IDs must keep resolving. Phase 2 IRI mapping carries them. New endpoints accept both IRI and legacy id | design dialogue |
| Editability UX | Top banner (`<GraphSetEditabilityBanner>`) + disabled actions with tooltip | design dialogue |

## 3. Shared Foundations

This section defines the substrate all four rebuilds build on.

### 3.1 Graph Set Context

Every Stage 2 page operates inside a graph set. The graph set bundles the asserted
ontology graph, asserted data graph, and the derived reasoning / rule / shape / import
graphs that are currently effective.

- The page receives its graph set id from the existing `GraphSetSelector`
  (`frontend/src/components/semantic/GraphSetSelector.tsx`).
- The active graph set id is persisted via URL param `graphSet` so deep links work.
- If no graph set is selected, the page renders an empty state prompting the user to pick
  one.
- Each graph in the set carries its own editability flag (already modelled in
  `NamedGraphsPage`). The page reads the flag once per render cycle and uses it to gate
  writes.

### 3.2 Read-Model Contract

Every Stage 2 read goes through the Phase 6 read-model endpoint:

```
GET /graph-sets/{graph_set_id}/read-models/{name}?limit=&offset=&filter=
```

Templates live in `backend/app/services/semantic_sparql_templates.py`. Each template
declares `name`, `projection_version`, `required_roles`, `needs_reasoning`,
`needs_rules`, `default_limit`, `assertion_kind`, `evidence_status`, `body`. The service
decorates each row with `graph_iri`, `graph_set_id`, `assertion_kind`, `evidence_status`,
and `staleness_state`.

Stage 2 adds the following templates, incrementally per page:

| Template | Lands with | Required roles |
| --- | --- | --- |
| `class-topology` | ClassesPage | `asserted_ontology` |
| `class-shape-generated` | ClassesPage | `asserted_ontology`, `shape_graph_generated` |
| `class-shape-custom` | ClassesPage | `shape_graph_custom` |
| `class-shape-merged` (composer) | ClassesPage | union of the above |
| `property-list` | ClassesPage | `asserted_ontology` |
| `relation-type-list` | ClassesPage | `asserted_ontology` |
| `entity-list` | EntitiesPage | `asserted_data` |
| `entity-shape` (composer, delegates to `class-shape-merged`) | EntitiesPage | same as `class-shape-merged` |
| `entity-relations` | EntitiesPage | `asserted_data`, `reasoning-result`, `rule-result` |
| `fact-audit-queue` (composer) | FactAuditPage | `asserted_data`, `reasoning-result`, `rule-result` |
| `missing-evidence-list` | FactAuditPage | `asserted_data` |
| `mapping-list` | Catalog-mapping | `asserted_ontology` |
| `import-graph-mappings` | Catalog-mapping | `import_graph` |

### 3.3 Canonical-Write Contract

Every Stage 2 write goes through the existing endpoint:

```
POST /canonical-writes:compile-and-apply
{ "kind": "...", "payload": {...}, "graph_set_id": "...", "audit": {...} }
```

The compiler in `backend/app/services/semantic_command_compiler.py` already handles
`create_class`, `create_relation_type`, `submit_assertion`, `update_evidence_status`.
Stage 2 adds the kinds listed in §3.3.1.

#### 3.3.1 New Canonical-Write Kinds

| Kind | Lands with | Notes |
| --- | --- | --- |
| `update_class` | ClassesPage | Patch label / description / aliases / parents |
| `delete_class` | ClassesPage | Soft delete; writes `op:deprecated true` |
| `create_property` | ClassesPage | OWL property attached to a class |
| `update_property` | ClassesPage | |
| `delete_property` | ClassesPage | |
| `update_relation_type` | ClassesPage | |
| `delete_relation_type` | ClassesPage | |
| `create_shape` | ClassesPage | SHACL NodeShape or PropertyShape in `graph/shapes/{id}/custom` |
| `update_shape` | ClassesPage | |
| `delete_shape` | ClassesPage | |
| `create_entity` | EntitiesPage | Wraps `submit_assertion`: writes `a owl:NamedIndividual`, label, class membership |
| `update_entity` | EntitiesPage | |
| `delete_entity` | EntitiesPage | Cascades to relations involving the entity |
| `create_relation` | EntitiesPage | |
| `delete_relation` | EntitiesPage | |
| `review_assertion` | FactAuditPage | Writes RDF-star reification with `op:auditStatus`, `op:reviewReason`, `op:reviewedBy`, `op:reviewedAt` |
| `create_mapping` | Catalog-mapping | Writes `op:SemanticMapping` to `graph/ontology/{id}` or `graph/import/{source_id}/{run_id}` |
| `update_mapping` | Catalog-mapping | |
| `delete_mapping` | Catalog-mapping | |

Each write produces an audited `RdfGraphDelta`, respects per-graph editability, runs SHACL
validation pre-apply, and records actor / reason / input format in `op:` audit metadata —
all already enforced by `semantic_canonical_write.py`.

### 3.4 SHACL Form Contract (Generated Base + Custom Overlay)

The shape graph is split into two sub-graphs:

- `graph/shapes/{ontology_id}/generated` — **derived**. The generator produces this from
  `graph/ontology/{id}`. Rebuildable; no audit metadata; subject to GC per ADR 0004.
- `graph/shapes/{ontology_id}/custom` — **editable**. Hand-authored SHACL shapes. All
  writes go through canonical-write with full audit.

#### 3.4.1 Generator Triggers

The generator runs:

- on demand before a `/validation-runs` invocation, if the ontology graph has changed
  since the last generation;
- on class save, incrementally for affected classes (`create_class` / `update_class`).
- via an explicit "regenerate shapes" action in `NamedGraphsPage` or Graph Governance.

It only ever writes to the `generated` sub-graph. The `custom` sub-graph is never
touched by the generator.

#### 3.4.2 Merge Rules

`GET /graph-sets/{graph_set_id}/shapes/classes/{class_iri_or_legacy_id}` returns merged
`ShaclFormGuidance`:

- Same `path`: custom wins; generated falls back.
- Each field carries `provenance: "generated" | "custom" | "merged"`.
- Custom-only fields (no generated counterpart) display normally with
  `provenance: "custom"`.
- Generated-only fields display normally with `provenance: "generated"`.

The frontend `ShaclFormRenderer` renders a small badge per field showing provenance.

#### 3.4.3 Generator / Custom Interaction

- After a `create_shape` write, the next `generated` regen leaves the custom shape
  untouched.
- "Regenerate shapes" only clears and rebuilds the `generated` sub-graph.
- If a user deletes an OWL class, the corresponding generated shape disappears. Custom
  shapes targeting the same class become orphans: retained and flagged with a warning;
  the user decides whether to clean up.

### 3.5 Editability Gating

A new shared component `<GraphSetEditabilityBanner>`
(`frontend/src/components/semantic/GraphSetEditabilityBanner.tsx`) renders:

```
[Graph Set: default-2026-07-06]
  ontology:         editable ✓
  data:             locked   ✗
  shapes/generated: derived (read-only)
  shapes/custom:    editable ✓
  reasoning-result: derived (read-only)
  rule-result:      derived (read-only)
```

Each page consumes the banner once at the top. Forms receive a `readOnly` prop derived
from the relevant per-graph flags:

| Page | Write gate |
| --- | --- |
| ClassesPage (topology / edit sub-mode) | `!ontologyGraph.editable` |
| ClassesPage (shape sub-mode) | `!shapesCustomGraph.editable` |
| EntitiesPage | `!dataGraph.editable` |
| FactAuditPage review actions | `!dataGraph.editable` for asserted; per-source for derived |
| Catalog mapping | `!ontologyGraph.editable && !importGraph.editable` |

Disabled buttons carry a tooltip explaining why ("Data graph is locked. Unlock on the
Named Graphs page to edit entities.").

### 3.6 Legacy ID Resolution

All Stage 2 read-model and shape endpoints accept either:

- the IRI form: `http://ontology-platform.local/ns/ontology/{id}/class/{class_id}`;
- or the legacy primary key: `class_id`, `entity_id`, `version_id`.

Resolution goes through `lookup_class_iri` / `lookup_relation_type_iri` in
`semantic_phase2_mapping.py` (already present). New endpoints' `{id}` path parameters
accept both forms.

## 4. ClassesPage Rebuild

### 4.1 File Layout

- `frontend/src/pages/ClassesPage.tsx` — new default implementation.
- `frontend/src/pages/ClassesPage.legacy.tsx` — the current inline implementation moved
  verbatim, used as fallback in shadow mode.
- `App.tsx` — `ClassesPage` / `ClassEditorPage` / `ClassTopologyCanvas` / `ClassFlowNode`
  inline definitions removed; replaced by a dispatch that imports `ClassesPage.tsx` and
  optionally falls back to `.legacy.tsx`.

### 4.2 Sub-Modes

```
ClassesPage (graph_set_id, ontology_id, editability)
├── GraphSetEditabilityBanner
├── ClassesToolbar (search + new class button)
└── ClassesContent
    ├── mode=topology  → ClassTopologyCanvas
    ├── mode=edit      → ClassEditorPage
    └── mode=shape     → ClassShapeEditor  (new)
```

Mode is local React state (existing `ClassPageMode` extended with `"shape"`). URL does
not reflect sub-mode.

### 4.3 Reads

Three concurrent fetches on mount:

| Read model | Purpose |
| --- | --- |
| `/graph-sets/{gs}/read-models/class-topology` | Topology graph nodes and edges |
| `/graph-sets/{gs}/read-models/property-list?class_iri=...` | Selected class property table |
| `/graph-sets/{gs}/read-models/relation-type-list` | Relation types |

The page maintains a `Map<legacy_id, ClassNode>`; child components reference classes by
legacy_id (preserves existing logic).

### 4.4 Writes

All writes go through `POST /canonical-writes:compile-and-apply`. Mapping from existing
UI action to canonical-write kind:

| UI action | Replaced by |
| --- | --- |
| `POST /ontologies/{id}/classes` | `kind=create_class` |
| `PATCH /classes/{id}` | `kind=update_class` |
| `DELETE /classes/{id}` | `kind=delete_class` |
| `POST /classes/{id}/properties` | `kind=create_property` |
| `PATCH /properties/{id}` | `kind=update_property` |
| `DELETE /properties/{id}` | `kind=delete_property` |
| `POST /ontologies/{id}/relation-types` | `kind=create_relation_type` |
| `PATCH /relation-types/{id}` | `kind=update_relation_type` |
| `DELETE /relation-types/{id}` | `kind=delete_relation_type` |

The compiler already translates `legacy_id` to IRI; missing `legacy_id` produces a new
UUID and registers the IRI mapping.

Successful writes:
1. update `graph/ontology/{id}` and trigger incremental regen of the affected class's
   generated shape;
2. invalidate the page's local read-model cache; refetch;
3. surface SHACL validation failures via the existing `ValidationReportPanel`.

### 4.5 ClassShapeEditor (new)

Layout:

```
Left:  Merged guidance (read-only display, provenance badge per field)
Right: Custom shape edit form (add / edit / delete custom constraints)
```

Reads `GET /graph-sets/{gs}/shapes/classes/{class_iri_or_legacy_id}` → merged
`ShaclFormGuidance`.

Writes custom shapes via `create_shape` / `update_shape` / `delete_shape`. After write,
the backend invalidates and recomputes `class-shape-merged` for the class.

`readOnly` is `!shapesCustomGraph.editable`.

### 4.6 Shadow Mode Switch

`<ClassesPageMode>` dispatcher (top of `App.tsx` workspace content) selects between
graph and legacy mode. Legacy mode is enabled when:

1. user explicitly toggles (dev-only control);
2. graph set is missing or empty (first run, no graph data yet);
3. canonical-write health check fails (operational fallback).

### 4.7 Edge Cases

| Case | Behavior |
| --- | --- |
| No graph set selected | Empty state; route to Governance → Graph Sets |
| Graph set has no `asserted_ontology` role | Empty state; "current graph set is missing asserted ontology" |
| Ontology graph locked | Banner shows lock state; new class button disabled; fields read-only |
| SHACL validation fails on save | Inline `ValidationReportPanel`; write rolled back |
| OWL class exists but shape missing | shape sub-mode prompts "shape pending generation"; button triggers `/validation-runs` to force regen |
| Class deleted while referenced as parent | Compiler returns structured error; editor surfaces it |
| Duplicate class label | Compiler detects `rdfs:label` conflict, returns 422 |

### 4.8 Exit Criteria

1. `App.tsx` no longer contains `ClassesPage` / `ClassEditorPage` /
   `ClassTopologyCanvas` / `ClassFlowNode` inline.
2. Default path is graph-derived; legacy implementation retained as
   `ClassesPage.legacy.tsx` fallback.
3. Read-model templates and canonical-write kinds marked "Lands with ClassesPage" are
   all live.
4. Stage 2 integration test plan (`docs/semantic/semantic-language-integration-test-plan.md`)
   gains coverage for the ClassesPage flow.

## 5. EntitiesPage Rebuild

### 5.1 File Layout

- `frontend/src/pages/EntitiesPage.tsx` — new default implementation.
- `frontend/src/pages/EntitiesPage.legacy.tsx` — current inline implementation moved
  verbatim.
- `App.tsx` — `EntitiesPage` / `EntityFormPage` / helpers removed from inline.

### 5.2 Sub-Modes

```
EntitiesPage (graph_set_id, ontology_id, editability)
├── GraphSetEditabilityBanner
├── EntitiesToolbar (search + class filter + layout switch + new entity)
└── EntitiesContent
    ├── mode=topology  → EntityGraphCanvas (existing React Flow component reused)
    └── mode=edit      → EntityFormPage
```

No `shape` sub-mode — entity's shape is its class's shape; editing happens in
ClassesPage.

### 5.3 Reads

| Read model | Purpose |
| --- | --- |
| `/graph-sets/{gs}/read-models/entity-list` | Topology graph nodes (id, label, aliases, class_iri, class_label, property_summary, evidence_status) |
| `/graph-sets/{gs}/read-models/entity-relations` | Topology edges (relation_type_iri, source_iri, target_iri, label, provenance) |
| `/graph-sets/{gs}/shapes/classes/{class_iri_or_legacy_id}` | Selected entity's class shape → form fields (reuses §3.4 merge) |

`entity-list` rows carry `evidence_status`; `entity-relations` rows carry `provenance`
(`asserted` / `inferred` / `rule_derived`). The topology canvas colors nodes and edges
by provenance.

### 5.4 Writes

| UI action | canonical-write kind | Target graph |
| --- | --- | --- |
| New entity | `create_entity` | `graph/data/{id}` |
| Edit entity | `update_entity` | `graph/data/{id}` |
| Delete entity | `delete_entity` | `graph/data/{id}` (cascade relations) |
| New / delete relation | `create_relation` / `delete_relation` | `graph/data/{id}` |

`create_entity` payload:

```json
{
  "class_iri_or_legacy_id": "...",
  "label": "...",
  "aliases": [...],
  "properties": { "name": "...", "email": "...", ... }
}
```

Compiler steps:
1. resolve class IRI (legacy id → IRI via Phase 2 mapping);
2. mint entity IRI (UUID unless caller supplies);
3. write `<entity> a owl:NamedIndividual, <class>; rdfs:label ...; skos:altLabel ...;
   <prop1> ...; <prop2> ...` into `graph/data/{id}`;
4. default `op:evidenceStatus` to `missing_evidence` per ADR 0004 §301-303.

### 5.5 Validation

Sync `/entities/validate` is dropped. The flow becomes:

1. canonical-write runs SHACL validation pre-apply (graph-set level);
2. failure → write rolled back; frontend renders `ValidationReportPanel`;
3. success → write lands;
4. "full validation" button → `POST /validation-runs`, polled until complete; full SHACL
   + OWL consistency report rendered.

### 5.6 Edge Cases

| Case | Behavior |
| --- | --- |
| Data graph locked | Banner; create / edit / delete all disabled |
| Class deleted while entity references it | Compiler returns structured error |
| Property value violates class shape | Compiler fails at SHACL; report rendered |
| Inferred relation appears in `entity-relations` | Rendered dashed; direct edit disabled |
| Rule-derived relation | Dotted line + badge; hover shows `rule_id` and `run_id` |
| `evidence_status=missing_evidence` | Node badge ⚠️; drawer shows "entity missing evidence" |
| Cross-ontology class IRI reference | Allowed; banner warns about external dependency |

### 5.7 Exit Criteria

1. `App.tsx` no longer contains `EntitiesPage` / `EntityFormPage` inline.
2. `/entities/validate` legacy endpoint marked deprecated (route retained with call
   counter).
3. `entity-list` / `entity-relations` / `entity-shape` templates live.
4. `create_entity` / `update_entity` / `delete_entity` / `create_relation` /
   `delete_relation` canonical-write kinds live.

## 6. FactAuditPage Rebuild

The largest rebuild in Stage 2.

### 6.1 Page Structure

```
FactAuditPage (graph_set_id, ontology_id, version legacy_id)
├── GraphSetEditabilityBanner
├── FactAuditToolbar
│   ├── Generate       (triggers reasoning + rule runs)
│   ├── Run rules      (triggers only rule runs)
│   ├── Refresh        (invalidate cache, refetch)
│   └── Recall         (SPARQL query)
├── StatsByKindTabs
│   ├── Asserted       [count]
│   ├── Inferred       [count, stale?]
│   ├── Rule-derived   [count, stale?]
│   └── Missing evidence [count]
└── FactQueue + FactInspector
```

The four tabs are `AssertionKind` switches. Within a tab, the fact list uses the same
component; only data source and available actions differ.

### 6.2 AssertionKind Data Sources

| AssertionKind | Source graph | Meaning |
| --- | --- | --- |
| `asserted` | `graph/data/{id}` | User / AI directly asserted entity attributes, relations, class membership |
| `inferred` | `graph/reasoning-result/{run_id}` | OWL reasoner output (inverse / subClass transitive / etc.) |
| `rule_derived` | `graph/rule-result/{run_id}` | Platform DSL / SPARQL CONSTRUCT rule output |
| `missing_evidence` | `graph/data/{id}` with `op:evidenceStatus "missing_evidence"` marker | Asserted but evidence missing |

### 6.3 Reads

#### Main Queue (Mixed)

`GET /graph-sets/{gs}/read-models/fact-audit-queue?kind=...&filter=...&limit=...`

Composer template (see §3.2). Backend logic:

1. Determine source graphs by `kind`:
   - `asserted` → `graph/data/{id}`
   - `inferred` → current effective `graph/reasoning-result/{run_id}`
   - `rule_derived` → current effective `graph/rule-result/{run_id}`
   - `missing_evidence` → `graph/data/{id}` rows marked
2. Decorate triples into unified fact rows:

```ts
type FactRow = {
  id: string;
  assertion_kind: "asserted" | "inferred" | "rule_derived" | "missing_evidence";
  subject_iri: string;
  subject_label: string;
  subject_legacy_id?: string;
  predicate_iri: string;
  predicate_label: string;
  object_value: unknown;
  object_label?: string;
  graph_iri: string;
  evidence_status: "with_evidence" | "missing_evidence" | "not_applicable";
  audit_status: "pending" | "approved" | "rejected" | "needs_correction";
  confidence?: number;
  derived_from?: {
    run_id: string;
    rule_id?: string;
    rule_version?: string;
    reason?: string;
  };
  stale: boolean;
  stale_reason?: string;
};
```

#### Missing-Evidence List

`GET /graph-sets/{gs}/read-models/missing-evidence-list` — lightweight template dedicated
to the "Missing evidence" tab; supports cross-graph-set aggregation.

#### Legacy Layer Concept Retirement

Old layer values (`entity_attribute`, `entity_relation`, `inferred_inverse`,
`value_conflict`, etc.) become **frontend filters** based on `predicate_iri` and
`assertion_kind`:

| Old layer | New derivation |
| --- | --- |
| `entity_attribute` | predicate is `owl:DatatypeProperty`, object is literal |
| `entity_relation` | predicate is `owl:ObjectProperty` |
| `inferred_inverse` | `assertion_kind=inferred` AND `derived_from.reason` contains "inverse" |
| `value_conflict` | same subject+predicate, multiple objects (separate query) |
| `rule_derived` / `rule_assertion` | `assertion_kind=rule_derived` |
| others | mapped similarly or dropped |

Old UX habits are preserved without re-introducing backend layer fields.

### 6.4 Writes

#### Generate

Legacy `/versions/{id}/fact-claims:generate` is deleted. New flow:

1. User clicks Generate → frontend `POST /reasoning-runs` and `POST /rule-runs` (already
   exist) with `graph_set_id` and selected `rule_definition` ids.
2. Backend executes async, writes to `graph/reasoning-result/{run_id}` and
   `graph/rule-result/{run_id}`.
3. Frontend polls `GET /reasoning-runs/{run_id}` and `GET /rule-runs/{run_id}` until
   completion.
4. On completion, invalidate `fact-audit-queue` cache; refetch.
5. New successful runs automatically become the graph-set's effective pointers (existing
   `reconcile_derived_results` logic).

#### Run Rules

Same flow but only triggers `/rule-runs`.

#### Review

`POST /canonical-writes:compile-and-apply` with `kind=review_assertion`:

```json
{
  "kind": "review_assertion",
  "payload": {
    "fact_id": "...",
    "decision": "approved",
    "reason": "...",
    "linked_fix_proposal_id": null
  },
  "graph_set_id": "...",
  "audit": { "actor": "...", "reason": "..." }
}
```

Compiler writes the review as RDF-star reification to the appropriate graph:

```turtle
<< <subject> <predicate> <object> >>
  op:auditStatus "approved" ;
  op:reviewReason "..." ;
  op:reviewedBy <user> ;
  op:reviewedAt "2026-07-06T..." .
```

For `inferred` / `rule_derived` kinds, review is written to the source derived graph.
Review actions on locked derived graphs are gated with a clear message: "Reasoning-result
graph is locked. Run a new reasoning round to update."

#### Recall

Legacy `/versions/{id}/background-knowledge:recall` is deleted. Replaced by direct
`POST /sparql:query` with caller-provided SPARQL or named template. Result rows are
tagged with `assertion_kind=asserted`, `graph_iri`, `evidence_status` so the user sees
that this is real graph data, not a separate "background knowledge" concept.

Vector-projection-based semantic search (the previous "background recall" semantic
retrieval) is preserved in Stage 4's `EntitiesSearchPage`, not here.

### 6.5 Staleness

Each derived graph row carries a `stale` flag:

- `graph/reasoning-result/{run_id}` is stale if the source graph set was modified after
  the run.
- `graph/rule-result/{run_id}` is stale if the source graph set or any rule_definition
  was modified after the run.

Staleness is computed by the existing `semantic_derived_state.py`. The frontend surfaces
it as a row badge; the inspector panel shows the reason and offers a "regenerate"
button (i.e. the Generate flow).

### 6.6 Edge Cases

| Case | Behavior |
| --- | --- |
| Data graph locked | Review actions disabled |
| Reasoning-result graph locked | Inferred tab review disabled; user prompted to run new reasoning |
| All derived graphs stale | Top banner warns; inferred/rule_derived row badges turn red |
| No effective reasoning run | Inferred tab empty state + "click Generate to run reasoning" |
| Cross-ontology inferred triple | Displayed with external-dependency badge |
| Missing-evidence fact approved | `evidence_status` stays `missing_evidence`; `audit_status` becomes `approved` (orthogonal) |
| `rule_definition` modified after `rule-result` | Stale + warning; review disabled on those facts |

### 6.7 Exit Criteria

1. `frontend/src/pages/FactAuditPage.tsx` is fully based on the new read-model and
   canonical-write.
2. `/versions/{id}/fact-claims`, `:generate`, `:sample`, `/fact-claims/{id}/review`,
   `/versions/{id}/rule-definitions:execute`,
   `/versions/{id}/background-knowledge:recall` are all deprecated (route retained with
   call counter).
3. `fact-audit-queue`, `missing-evidence-list` templates live.
4. `review_assertion` canonical-write kind lives.
5. Old layer concept survives as a frontend filter derived from `predicate_iri`.

## 7. Catalog Mapping Rebuild (Split)

### 7.1 Split Scope

`CatalogWizardPage` currently manages 5 object kinds. Stage 2 splits them:

| Object | Disposition | Data source |
| --- | --- | --- |
| DataSource | **K** (Postgres unchanged) | `/data-sources` |
| DataResource | **K** | `/data-resources` |
| ExternalField | **K** | `/external-fields` |
| ConnectorTemplate | **K** | `/connector-templates` |
| ConnectorTemplate query execution | **K** | `/connector-templates/{id}/query` |
| SemanticMapping | **R** (rebuilt as RDF) | new read-model + canonical-write |

### 7.2 Page Structure

The 5-step wizard shell is preserved as the outer skeleton. Each step renders a panel:

1. **Data sources** — unchanged
2. **Resources** — unchanged
3. **Fields** — unchanged
4. **Mappings** (rebuilt) — RDF writes to `graph/ontology/{id}` or
   `graph/import/{source_id}/{run_id}`
5. **Templates** — unchanged

Only step 4 is rewritten.

### 7.3 Reads

| Read model | Purpose |
| --- | --- |
| `/graph-sets/{gs}/read-models/mapping-list?ontology_id=...` | Current ontology's mappings (written to `graph/ontology/{id}`) |
| `/graph-sets/{gs}/read-models/import-graph-mappings?source_id=...&run_id=...` | Temporary mappings from a specific import run (`graph/import/{source_id}/{run_id}`) |

```ts
type SemanticMappingRow = {
  id: string;
  mapping_iri: string;
  external_field_legacy_id: string;
  external_field_name: string;
  target_type: "class" | "property" | "relation_type";
  target_iri: string;
  target_legacy_id: string;
  target_label: string;
  join_key: string;
  confidence: number;
  owner: string;
  graph_iri: string;
  provenance: "asserted" | "imported";
};
```

### 7.4 Writes

| UI action | canonical-write kind | Target graph |
| --- | --- | --- |
| New mapping | `create_mapping` | `graph/ontology/{id}` (default) or `graph/import/{source_id}/{run_id}` |
| Edit mapping | `update_mapping` | same |
| Delete mapping | `delete_mapping` | same |

Each mapping is a set of RDF triples:

```turtle
<mapping_iri> a op:SemanticMapping ;
  op:externalField <external_field_iri> ;
  op:targetClass <class_iri> ;
  op:joinKey "..." ;
  op:confidence 0.92 ;
  op:owner "..." ;
  prov:wasDerivedBy <import_run_iri> .
```

External-field IRI resolves to the Postgres `ExternalField` row via Phase 2 IRI mapping
(the K side stays untouched).

### 7.5 Connector Execution Re-wiring

Connector template execution (step 5, `/connector-templates/{id}/query`) currently writes
results directly to the legacy `fact-claims` table. After Stage 2:

- connector execution **no longer writes the legacy fact table**;
- results flow through an import process: written to
  `graph/import/{source_id}/{run_id}` together with a set of auto-generated temporary
  mappings;
- the user sees these import-source facts in `FactAuditPage` with
  `provenance: "imported"`;
- after review, the user can promote temporary mappings to permanent ones via
  `update_mapping`, which moves them into `graph/ontology/{id}`.

This is the most visible connector flow change in Stage 2; the connector configuration
itself does not change.

### 7.6 Edge Cases

| Case | Behavior |
| --- | --- |
| Ontology graph locked | Mapping edit disabled; banner explains |
| Import graph locked (run in progress) | Temporary mappings read-only |
| ExternalField deleted while mapping references it | Mapping row flagged yellow; bulk "clean orphan mappings" action available |
| Duplicate mapping for same external_field | Compiler returns 422 |
| Cross-ontology class_iri reference | Allowed; banner warns |

### 7.7 Exit Criteria

1. CatalogWizardPage step 4 (Mappings) is fully based on the new read-model and
   canonical-write.
2. `/projects/{id}/semantic-mappings` endpoint deprecated.
3. `mapping-list`, `import-graph-mappings` templates live.
4. `create_mapping` / `update_mapping` / `delete_mapping` canonical-write kinds live.
5. Connector execution flow change complete (writes through import graph, not fact
   table).

## 8. Backend Surface Summary

### 8.1 New Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/graph-sets/{gs}/read-models/{name}` | Existing; new template names added per §3.2 |
| GET | `/graph-sets/{gs}/shapes/classes/{class_iri_or_legacy_id}` | Merged shape guidance (custom + generated) |
| POST | `/canonical-writes:compile-and-apply` | Existing; new kinds added per §3.3.1 |
| POST | `/reasoning-runs` | Existing; FactAuditPage Generate calls it |
| POST | `/rule-runs` | Existing; FactAuditPage Generate / Run rules calls it |
| GET | `/reasoning-runs/{run_id}` | Existing; FactAuditPage polling |
| GET | `/rule-runs/{run_id}` | Existing; FactAuditPage polling |
| POST | `/sparql:query` | Existing; FactAuditPage Recall uses it |
| POST | `/validation-runs` | Existing; ClassesPage / EntitiesPage use it for full validation |

No new endpoint categories. Stage 2 is primarily a wiring exercise over the existing
Phase 6-8 surface.

### 8.2 New Read-Model Templates

(see §3.2 table)

### 8.3 New Canonical-Write Kinds

(see §3.3.1 table)

### 8.4 Generator Service

A new `backend/app/services/semantic_shape_generator.py` produces
`graph/shapes/{id}/generated` from `graph/ontology/{id}`. Triggered:

- before `/validation-runs` if ontology graph changed;
- incrementally on `create_class` / `update_class` writes;
- explicitly via "regenerate shapes" action in `NamedGraphsPage`.

## 9. Frontend Surface Summary

### 9.1 New Page Files

- `frontend/src/pages/ClassesPage.tsx` (new; default graph-derived)
- `frontend/src/pages/ClassesPage.legacy.tsx` (existing inline moved verbatim)
- `frontend/src/pages/EntitiesPage.tsx` (new)
- `frontend/src/pages/EntitiesPage.legacy.tsx` (existing inline moved verbatim)
- `frontend/src/pages/FactAuditPage.tsx` (rewritten in place)
- `frontend/src/pages/FactAuditPage.legacy.tsx` (current implementation moved)
- `frontend/src/pages/CatalogWizardPage.tsx` (rewritten step 4; other steps unchanged)
- `frontend/src/pages/CatalogWizardPage.legacy.tsx` (current implementation moved for
  step 4 fallback)

### 9.2 New Shared Components

- `frontend/src/components/semantic/GraphSetEditabilityBanner.tsx`
- `frontend/src/components/semantic/ClassShapeEditor.tsx`
- `frontend/src/components/semantic/FactAssertionKindTabs.tsx`
- `frontend/src/components/semantic/FactInspector.tsx`

Existing components reused: `ShaclFormRenderer`, `GraphSetSelector`,
`ValidationReportPanel`, `ReasoningResultPanel`, `RuleResultPanel`,
`EvidenceBindingPanel`, `ProvenanceTimeline`.

### 9.3 `App.tsx` Cleanup

The current `App.tsx` is 3154 lines and contains the entire `ClassesPage` /
`EntitiesPage` / `EntityFormPage` / `EvidenceArtifactsPage` inline implementations plus
shared helpers (`effectivePropertiesForClass`, `parseEntityPropertyValue`,
`classMatchesRelation`, etc.). Stage 2 reduces `App.tsx` to:

- Workspace shell (rail, top bar, workflow progress).
- `<WorkspaceContent>` dispatcher that imports the new page files.
- The legacy implementations moved to `*.legacy.tsx` files.

Target post-Stage-2 `App.tsx` size: under 1500 lines.

## 10. Migration Window and Legacy Endpoint Retirement

Shadow mode (per §2 locked-in decisions) plays out in three phases.

### 10.1 Phase A — Graph-Derived Reads Land (Legacy Preserved)

Per page, Phase A PR contains:

1. The page's new read-model templates (§3.2).
2. The page's new canonical-write kinds (§3.3.1).
3. Backend endpoint / schema definitions and unit tests.
4. Integration tests for the new path.
5. **No** change to the frontend's default call path.

Exit criteria: new path works end-to-end in staging on the same fixture data, with
output equivalent to the legacy path within an agreed tolerance.

### 10.2 Phase B — Frontend Cuts Over (Legacy as Fallback)

1. Add `<Page>.legacy.tsx` files; move the current inline implementation verbatim.
2. Default to the new `<Page>.tsx`; fall back to legacy on feature flag or runtime
   health-check failure.
3. `App.tsx` removes inline implementations; dispatch imports the new files.
4. Legacy endpoints retain their routes; `X-Deprecated: stage2-shadow` header added;
   call counter emitted to telemetry.

Exit criteria: production traffic share on the new path ≥ 95% for one release cycle, no
severe incidents on the new path.

### 10.3 Phase C — Legacy Endpoints Deleted (Post-Stage-2)

Out of Scope for Stage 2. Triggered when:

1. All four Stage 2 pages have completed Phase B.
2. Stage 3 (Publication / Versions) has also completed Phase B.
3. Legacy path call share < 5%.

The inventory's "Delete Candidates" list is then cleared in one batch.

### 10.4 Stage 2 Internal Sequencing

```
Phase A
  ├── (1) ClassesPage foundation (read-models, canonical-writes, shape endpoint,
  │     OWL→shape generator)
  ├── (2) EntitiesPage foundation              ← depends on (1)'s shape endpoint
  ├── (3) FactAuditPage foundation             ← depends on (2)'s entity graph data
  └── (4) Catalog mapping foundation           ← can start parallel with (2)

Phase B (per page, follows its Phase A)
  ├── ClassesPage cutover
  ├── EntitiesPage cutover                     ← waits for ClassesPage Phase B
  ├── FactAuditPage cutover                    ← waits for EntitiesPage Phase B
  └── Catalog mapping cutover                  ← parallel with EntitiesPage cutover
```

Each Phase A → Phase B pair forms one release unit and can be independently canaried.

## 11. Testing Strategy

| Layer | Coverage |
| --- | --- |
| Read-model SPARQL unit | Each new template returns the documented row shape on fixture data |
| Canonical-write unit | Each new kind: compile → apply → expected graph delta |
| Generator unit | OWL fixture → expected `generated` sub-graph; idempotent on repeat runs; safe when `custom` sub-graph has data |
| Shape merge unit | `class-shape-merged` returns correct `provenance` per field |
| Backend integration | End-to-end: "create class → add property → add relation → see shape → add custom constraint → validation passes" |
| Frontend component | Page render under: empty graph set, locked graph, SHACL failure, stale derived |
| Frontend integration | Each page's flow with mock backend |
| Regression | Legacy mode retains current smoke coverage |
| Stage 2 integration test plan | `docs/semantic/semantic-language-integration-test-plan.md` extended |

## 12. Open Questions Deferred to Implementation

These are not blocking the spec; the implementation plan may resolve them per phase.

- **`fact_id` stability.** The `review_assertion` payload uses `fact_id`. The
  implementation must define a stable hash function for `(subject, predicate, object,
  graph)` triples and document it. Likely SHA-256 of the canonical N-Triples
  serialization.
- **Layer filter derivation rules.** §6.3 lists provisional mappings; the implementation
  finalizes the predicate_iri-based classification (e.g. is `owl:DatatypeProperty`
  determined by `a owl:DatatypeProperty` or by `rdfs:range` being a datatype?).
- **Connector import-run lifecycle.** §7.5 introduces `graph/import/{source_id}/{run_id}`
  graphs. Their lifecycle (TTL, cleanup, who can delete) needs a small follow-up
  decision, but the inventory's `graph/import` category already implies their existence.
- **`<Page>.legacy.tsx` removal trigger.** Phase C removes legacy endpoints; the
  `.legacy.tsx` files retire in the same batch. The exact trigger conditions are
  operational, not architectural.
