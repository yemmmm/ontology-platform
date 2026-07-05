# Phase 8 Frontend and Workflow Reshaping

## Status

Detailed design. Phase 8 builds on the Phase 1 semantic runtime spine, Phase 2 namespace and
export baseline, Phase 3 governed semantic edit path, Phase 4 graph registry and graph sets,
Phase 5 reasoning/validation/derivation services, Phase 6 graph-derived product APIs, and Phase 7
canonical RDF Dataset migration.

Phase 8 is the user-facing migration from legacy custom-model screens to graph-native workflows.
It should not require ordinary users to author Turtle, TriG, JSON-LD, SPARQL, OWL, or SHACL syntax.
Those direct semantic inputs are for expert tools, AI agents, and power users, and they still flow
through platform validation, editability checks, evidence handling, audit, and warning semantics.

The current frontend shell is centered in `frontend/src/App.tsx` with stage-grouped workspace tabs.
The current catalog surface is implemented as `frontend/src/pages/CatalogWizardPage.tsx`; the
historical `CatalogPage.tsx` path is not present in this checkout. Phase 8 should reshape the
existing workspace rather than create a separate frontend product.

## Goal

Align the frontend and day-to-day workflows with graph-native governance.

Ordinary users should continue to work through business-friendly screens for classes, entities,
facts, evidence, validation, reasoning, rule runs, catalog mapping, import/export, and publication
readiness. Reviewers, auditors, expert users, and AI agents should gain direct visibility into
named graphs, graph sets, graph deltas, provenance, SHACL validation, OWL reasoning, business-rule
results, assertion kinds, warning state, and graph editability.

The frontend should make the semantic platform understandable without hiding the new governance
model. A user looking at any statement should be able to answer:

- where it came from,
- which graph contains it,
- whether it is asserted, inferred, rule-derived, imported, policy metadata, review metadata, or
  missing evidence,
- whether the graph is editable,
- whether validation, reasoning, or rule results are stale,
- which evidence or provenance supports it,
- which operation would change it.

## Confirmed Decisions

1. Business-friendly product workflows remain first-class. Raw semantic syntax is never required
   for ordinary class, relation, assertion, evidence, validation, reasoning, rule, or import/export
   workflows.
2. Direct semantic edit inputs are expert/agent surfaces. They support TriG, JSON-LD, constrained
   SPARQL Update, SHACL, and OWL-oriented payloads only through the governed semantic edit path.
3. The UI is graph-native after Phase 7. Pages may show compact business JSON, but the read models
   must expose graph IRI, graph set, assertion kind, provenance, evidence status, validation state,
   reasoning/rule staleness, editability, and warnings where relevant.
4. Named graphs replace draft/published graph promotion as the main semantic governance model.
   Editable state is per actual ontology/data graph.
5. SHACL shapes are the preferred source for ordinary-user forms, allowed-property guidance,
   required fields, cardinality hints, datatype hints, enum-like controls, and validation messages.
6. OWL reasoning, SHACL validation, SPARQL CONSTRUCT derivation, business rules, and workflow state
   remain separate execution paths. The UI must not collapse their outputs into one undifferentiated
   "facts" list.
7. Source assertions, OWL-inferred statements, business-rule-derived statements, imported
   statements, review metadata, and policy metadata must be visually distinguishable.
8. Missing-evidence facts remain writable only with explicit evidence status and warnings. Derived
   outputs that depend on missing evidence must show propagated warning state.
9. Protégé and WebProtégé stay outside platform core. The product provides standards-based
   import/export and inspection paths, not embedded Protégé/WebProtégé workflows.
10. Frontend navigation should evolve from the current `Intake`, `Modeling`, `Publish`, and
    `Tools` stage shell without breaking existing deep-link behavior until replacement routes are
    ready.

## Non-Goals

- Do not make ordinary users write Turtle, TriG, JSON-LD, SPARQL, OWL, or SHACL.
- Do not embed Protégé, WebProtégé, or a third-party ontology editor as a required workflow.
- Do not reintroduce draft/published graph promotion as the semantic governance model.
- Do not let direct semantic edits bypass graph editability, SHACL/platform validation, evidence
  status, warnings, audit, or graph-delta calculation.
- Do not make the frontend compute ontology semantics, reasoning, rule results, or graph-set
  staleness locally. It may render backend-provided status and trigger backend runs.
- Do not let Neo4j, search, vector indexes, browser caches, or frontend state become semantic
  sources of truth.
- Do not remove legacy screens until graph-derived projections and Playwright smoke coverage prove
  the replacement workflows.

## UI and Workflow Architecture

Phase 8 reshapes the workspace around four user-facing work areas:

| Work area | Audience | Purpose |
| --- | --- | --- |
| Business Modeling | ordinary users, analysts | Classes, properties, relation types, entities, assertions, and fact review through SHACL-guided forms. |
| Graph Governance | reviewers, auditors, expert users | Named graphs, graph sets, graph deltas, editability, provenance, validation, reasoning, rule state, and warnings. |
| Semantic Workbench | agents, expert users | Direct semantic edit input, graph diff preview, validation/reasoning preview, constrained SPARQL Update, and export inspection. |
| Operations and Exchange | operators, integrators | Imports, exports, catalog mappings, connector templates, projection rebuilds, and smoke/status checks. |

The existing workspace stages can evolve as follows:

| Current stage | Phase 8 direction |
| --- | --- |
| `Intake` | Keep brief, competency questions, and evidence originals. Add semantic evidence graph status and import readiness where relevant. |
| `Modeling` | Keep class/entity/fact/catalog flows, but back them with graph-derived projections and SHACL-guided forms. |
| `Publish` | Reframe from version publication only to release/readiness over graph sets, validation reports, reasoning/rule freshness, and export packages. |
| `Tools` | Split or expand into Graph Governance, Semantic Workbench, and Operations surfaces when navigation density requires it. |

The route shell should still keep stable URL query parameters for deep links:

```text
?project={project_id}&ontology={ontology_id}&version={version_id}&tab={workspace_tab}
```

New semantic drill-down parameters should be additive:

```text
graph={encoded_graph_iri}
graphSet={graph_set_id}
statement={statement_id}
edit={semantic_edit_audit_id}
run={validation|reasoning|rule}:{run_id}
format=trig|json-ld|turtle
```

## Screens and Workspaces

### 1. Graph Governance Dashboard

Purpose: show the semantic health of the selected ontology version or graph set.

Required content:

- graph counts by category,
- editable vs locked actual ontology/data graphs,
- active graph set membership,
- current validation status,
- current OWL reasoning pointer and staleness,
- current rule-result pointer and staleness,
- missing-evidence warning count,
- stale projection warning count,
- latest graph deltas and audit records.

Primary actions:

- open named graph registry,
- open graph set detail,
- run SHACL validation,
- run OWL reasoning,
- run rule set,
- reconcile staleness,
- lock or unlock an actual graph,
- export graph set.

This screen should become the graph-native replacement for any status panel that currently implies
only `draft`, `validated`, or `published` workflow progression.

### 2. Named Graph Registry

Purpose: inspect and manage platform-managed graph boundaries.

Required columns:

- graph label,
- graph IRI,
- category,
- owner type and owner id,
- role in selected graph set,
- revision,
- editability,
- current/stale status,
- statement count where available,
- latest audit timestamp.

Required filters:

- category,
- owner,
- editable/locked,
- stale/current,
- missing evidence,
- managed/unmanaged import.

Required row actions:

- open graph detail,
- export graph,
- lock or unlock when category allows direct edit,
- inspect latest graph delta,
- view validation/reasoning/rule dependencies.

Graph IRI values should be copyable for expert workflows, but ordinary labels and owner names must
be the primary visible handles.

### 3. Graph Set Detail

Purpose: show exactly which graphs define a working view.

Required content:

- graph set name, id, scope, status, and source signature,
- member graph list grouped by role,
- required vs optional membership,
- current effective reasoning and rule-result pointers,
- validation reports attached to this graph set,
- stale dependency explanation,
- query scopes: asserted-only, asserted plus reasoning, asserted plus rules, full working view.

Primary actions:

- add/remove graph members where governance allows,
- run validation over selected scope,
- run reasoning over selected scope,
- run rules over selected scope,
- export graph set as TriG or JSON-LD,
- open SPARQL query prefilled to this graph set for expert users.

Graph-set membership changes must be presented as governance events because they can make validation,
reasoning, rule results, and projections stale.

### 4. Graph Delta Review

Purpose: make every mutation understandable before and after commit.

Required content:

- added triples/quads,
- removed triples/quads,
- affected graph IRIs,
- changed shapes,
- changed entailments where previewed,
- validation impact,
- reasoning/rule staleness impact,
- evidence impact,
- audit metadata,
- warnings.

For business-friendly edits, the delta view should use compact labels by default and expose raw
triple/quad views behind an expert toggle. For direct semantic edits, raw graph syntax and compact
labels should both be available.

Delta badges:

- `Asserted`,
- `OWL inferred`,
- `Rule derived`,
- `Imported`,
- `Review metadata`,
- `Policy metadata`,
- `Missing evidence`,
- `Stale derived`,
- `Locked graph`.

### 5. SHACL-Guided Modeling Forms

Purpose: keep ordinary modeling workflows friendly while moving constraints to semantic shapes.

Affected screens:

- class creation/edit,
- property creation/edit,
- relation type creation/edit,
- entity creation/edit,
- assertion submission,
- catalog mapping where target class/property shapes matter,
- import mapping review.

Required behavior:

- render required fields from SHACL `sh:minCount`,
- render single/multiple controls from `sh:maxCount`,
- render datatype controls from XSD datatype constraints,
- render enum-like controls from `sh:in`,
- show allowed properties and relation targets for selected class,
- explain validation failures in business terms,
- show the target graph and editability state before submit,
- preview graph delta when feasible,
- preserve missing-evidence status controls for fact/assertion writes.

The frontend should not synthesize SHACL interpretation rules ad hoc. It should consume backend
form guidance derived from shapes, with the raw shape IRI available for expert inspection.

### 6. Assertion and Fact Audit

Purpose: display statements with origin, support, warning, and editability context.

Required statement fields:

- subject label and IRI,
- predicate label and IRI,
- object value/label and IRI where applicable,
- graph IRI,
- assertion kind,
- evidence status,
- evidence links,
- provenance activity,
- actor or agent/skill reference where available,
- audit status,
- validation state,
- warning state,
- stale dependency state,
- editability state.

The statement list should support origin filters:

- asserted by user/agent,
- OWL-inferred,
- business-rule-derived,
- imported,
- review metadata,
- policy metadata,
- missing evidence.

Clicking a statement opens a detail drawer with evidence, provenance, graph membership, latest
audit delta, and related validation/reasoning/rule runs.

### 7. Validation, Reasoning, and Rule Runs

Purpose: make separate semantic execution paths visible and actionable.

Required run views:

- SHACL validation runs with conforms flag, violation counts, shape version, data graph revisions,
  report graph, and form-guidance changes.
- OWL reasoning runs with consistency, classification, realization, entailment summary, engine
  version, input graph set, result graph, current/stale/superseded pointer state, and warnings.
- Rule runs with rule definition/version, engine profile, generated statements, evidence
  dependencies, missing-evidence propagation, review/audit status, result graph, and staleness.

Required behavior:

- running a validation/reasoning/rule job must clearly show which graph set and scope are inputs,
- stale results must remain readable only with clear stale labeling,
- current effective result pointers must be visible,
- superseded result graphs must not appear current,
- failed runs must show error summary without implying source graph mutation.

### 8. Direct Semantic Edit Workbench

Purpose: give expert users and AI agents a precise, governed semantic edit surface.

Inputs:

- TriG,
- Turtle when a target graph is selected,
- JSON-LD,
- constrained SPARQL Update,
- SHACL shapes,
- OWL/RDF serialization where supported by backend parsing.

Required controls:

- target graph selector,
- graph set context selector,
- input format selector,
- reason/audit note,
- evidence binding panel for fact writes,
- missing-evidence acknowledgement where applicable,
- validate/preview button,
- apply button disabled until backend preview permits it.

Required preview:

- parse result,
- graph delta,
- target graph editability,
- SHACL validation result,
- platform validation result,
- OWL reasoning impact when requested,
- stale derived results that would be created,
- warnings,
- audit record shape.

Raw syntax editing should use a monospace editor area with line numbers if a code editor is
introduced, but the MVP can start with a plain textarea plus backend line/column parse errors.

### 9. Import and Export Workspace

Purpose: keep standards exchange outside Protégé/WebProtégé integration.

Import support:

- upload or paste Turtle, TriG, JSON-LD, RDF/XML where backend supports it,
- classify incoming graphs as import graphs,
- map imported graph IRIs to platform graph categories,
- preview graph delta before promotion into actual ontology/data graphs,
- validate imported data with SHACL,
- run optional OWL consistency check,
- bind evidence/provenance for imported assertions,
- record import run graph and audit.

Export support:

- export selected graph,
- export graph set,
- export asserted-only,
- export asserted plus current reasoning,
- export asserted plus current rule results,
- export full working view,
- choose TriG, Turtle, JSON-LD, and compact business JSON where applicable,
- include or omit governance/evidence graphs based on explicit options.

The UI may mention that standards-compatible exports can be opened in external tools, but it should
not make a specific external tool part of the core workflow.

### 10. Catalog and Connector Workflow

Purpose: adapt the current catalog wizard to semantic graph governance.

The existing `CatalogWizardPage.tsx` already guides users through source, resource, field, mapping,
and connector template steps. Phase 8 should preserve that ordinary workflow while adding:

- graph IRI and semantic target labels for mapped classes/properties/entities,
- SHACL-based target compatibility hints,
- policy graph links for sensitivity, masking, approval, and obligations,
- provenance graph links for connector runs,
- import graph creation when connector output is staged,
- graph delta preview before connector data is promoted into actual data graphs,
- assertion kind badges for connector-imported statements,
- validation and missing-evidence warnings for connector output.

Connector query test results should not look like committed semantic facts. They are preview data
until an import or governed edit commits them to a managed graph.

## Frontend Route, Page, and Component Implications

### Workspace Tabs

Phase 8 should extend `WorkspaceTab` and `workspaceTabs` in `frontend/src/App.tsx` in a controlled
sequence. Candidate tabs:

- `graph-governance`,
- `named-graphs`,
- `graph-sets`,
- `semantic-edits`,
- `semantic-runs`,
- `semantic-import-export`.

Navigation should avoid one giant tool drawer. If the tab count becomes too dense, promote a new
stage such as `Governance` between `Modeling` and `Publish`, and keep `Tools` for search, agent,
MCP, and settings.

Any navigation change must update these together:

- `WorkspaceTab`,
- `WorkspaceStage` if adding a stage,
- `stageMeta`,
- `stageDefaultTab`,
- `workflowStatusToStage` if workflow status display changes,
- `workspaceTabs`,
- `WorkspaceContent`,
- `frontend/src/i18n/zh.ts`,
- Playwright selectors that rely on visible tab names.

### Page Components

Recommended page modules:

```text
frontend/src/pages/GraphGovernancePage.tsx
frontend/src/pages/NamedGraphsPage.tsx
frontend/src/pages/GraphSetPage.tsx
frontend/src/pages/SemanticEditWorkbenchPage.tsx
frontend/src/pages/SemanticRunsPage.tsx
frontend/src/pages/SemanticImportExportPage.tsx
```

Recommended shared components:

```text
frontend/src/components/semantic/AssertionKindBadge.tsx
frontend/src/components/semantic/GraphIriLabel.tsx
frontend/src/components/semantic/GraphEditabilityToggle.tsx
frontend/src/components/semantic/GraphDeltaViewer.tsx
frontend/src/components/semantic/GraphSetSelector.tsx
frontend/src/components/semantic/SemanticWarningList.tsx
frontend/src/components/semantic/ValidationReportPanel.tsx
frontend/src/components/semantic/ReasoningResultPanel.tsx
frontend/src/components/semantic/RuleResultPanel.tsx
frontend/src/components/semantic/EvidenceBindingPanel.tsx
frontend/src/components/semantic/ProvenanceTimeline.tsx
frontend/src/components/semantic/ShaclFormRenderer.tsx
```

Shared components should receive typed API DTOs and avoid re-parsing RDF syntax in the browser.
Raw Turtle/TriG/JSON-LD rendering is for display, copy, download, and expert editing only.

### Styling and UX

The existing frontend keeps most styling in `frontend/src/styles.css`. Phase 8 should keep that
convention until the frontend has a stronger component styling system.

Use compact operational layouts:

- tables for named graph registries and run histories,
- split panes for direct edit input plus preview,
- drawers for statement details and provenance,
- segmented controls for asserted/full working view scopes,
- tags/badges for assertion kind, evidence status, staleness, and editability,
- icon buttons with tooltips for export, copy IRI, refresh, lock/unlock, validate, reason, and run.

Do not turn semantic governance into a marketing-style dashboard. The primary audience will compare
graphs, statements, runs, and warnings repeatedly.

## API Contracts Needed From Earlier Phases

Phase 8 should not invent local-only semantics. It depends on graph-derived contracts from earlier
phases.

Required read APIs:

- `GET /api/semantic/status`
  returns graph counts, editability counts, stale derived counts, validation summary, current
  derived pointers, projection status, and warning counts.
- `GET /api/semantic/graphs`
  returns graph registry rows with category, owner, revision, editability, statement counts,
  latest audit, and derived status.
- `GET /api/semantic/graphs/{graph_iri}`
  returns graph detail, metadata, revisions, members, audits, statement summaries, and export links.
- `GET /api/semantic/graph-sets/{graph_set_id}`
  returns graph-set metadata, members, source signature, current pointers, stale explanations, and
  query scopes.
- `GET /api/semantic/statements`
  returns paginated statements with graph IRI, assertion kind, evidence status, provenance,
  warnings, editability, and stale state.
- `GET /api/semantic/edits/{audit_id}`
  returns graph delta, input format, actor, reason, validation state, warnings, and affected graph
  revisions.
- `GET /api/semantic/runs`
  returns validation, reasoning, and rule run history with graph set, engine, status, result graph,
  current/stale/superseded state, warnings, and errors.
- `GET /api/ontologies/{ontology_id}/semantic-export`
  remains available for graph/graph-set exports in TriG, Turtle, JSON-LD, and compact business JSON
  variants.
- SHACL form guidance endpoint, for example
  `GET /api/semantic/shacl-form-guidance?graph_set_id=...&class_iri=...`.

Required mutation APIs:

- governed semantic edit preview and apply endpoints from Phase 3,
- graph editability toggle endpoint from Phase 4,
- graph-set create/update endpoint from Phase 4,
- validation run endpoint from Phase 5,
- reasoning run endpoint from Phase 5,
- rule run endpoint from Phase 5,
- import preview/promote endpoint from Phase 8 backend work if not already covered by Phase 6/7,
- projection rebuild endpoint from Phase 6 operations where needed.

Mutation responses must return enough state for the UI to refresh without guessing:

- affected graph IRIs,
- graph revision changes,
- audit id,
- validation run id where applicable,
- stale derived pointers,
- warnings,
- next suggested action.

## Accessibility and UX Behavior

Required accessibility behavior:

- every graph table must support keyboard focus, row action buttons, and clear accessible labels,
- assertion kind badges must not rely on color alone,
- warning and stale states must include text labels and ARIA-visible summaries,
- direct edit parse errors must identify line/column and be announced near the editor,
- lock/unlock controls must have explicit graph labels in accessible names,
- run status changes must be conveyed through text, not only spinners,
- diff viewers must provide a text/table representation, not only colored code blocks,
- modal confirmations must focus the destructive or cancel action predictably.

Required UX behavior:

- ordinary edit forms show business labels first and IRIs second,
- raw graph syntax is opt-in except on expert workbench pages,
- stale reasoning/rule results are visible but clearly marked stale,
- locked graph actions are disabled with explanation and link to the graph editability control,
- missing-evidence facts show a warning at creation, in statement lists, and in derived outputs,
- graph-set changes explain which validation, reasoning, rule, and projection results become stale,
- import previews never imply data is committed until a governed apply/promote step succeeds,
- long-running validation/reasoning/rule/projection jobs show status, input graph set, and safe
  refresh behavior.

## Rollout Plan

1. Add backend DTOs and read endpoints to support graph governance summaries, named graph registry,
   graph sets, statements, runs, deltas, and SHACL form guidance.
2. Add frontend types and API helpers for semantic graph DTOs.
3. Add `AssertionKindBadge`, `GraphIriLabel`, `SemanticWarningList`, and `GraphEditabilityToggle`
   as shared read-only components first.
4. Add Graph Governance Dashboard and Named Graph Registry behind new workspace tabs.
5. Add Graph Set Detail and Run History screens.
6. Update existing class/entity/fact screens to consume SHACL form guidance and display target
   graph/editability/warning state.
7. Add Graph Delta Viewer to business-friendly edit confirmations.
8. Add Direct Semantic Edit Workbench with preview-before-apply.
9. Add Import/Export workspace and adapt the catalog wizard to show graph provenance and import
   staging.
10. After graph-derived screens pass smoke checks, remove or hide legacy-only views that no longer
    represent canonical RDF state.

Each step should be shippable without requiring the next one. Until Phase 7 canonical migration is
complete, pages may show transition labels such as "graph-derived preview" when they are backed by
new semantic APIs but legacy write paths still exist.

## Test and Smoke Guidance

Documentation-only changes do not require test execution. Phase 8 implementation changes must use
the normal frontend verification path:

```bash
cd frontend && npm run build
cd frontend && npx playwright test
```

Backend behavior changes must use:

```bash
cd backend && uv run pytest
```

Required Playwright smoke coverage:

- workspace navigation exposes Graph Governance, Named Graphs, Graph Sets, Semantic Edits,
  Semantic Runs, and Import/Export routes without breaking existing deep links,
- ordinary user can create/edit a class or entity through SHACL-guided fields without seeing raw
  Turtle/SPARQL requirements,
- locked graph disables ordinary edit submit and exposes the graph editability explanation,
- named graph registry lists ontology/data/reasoning-result/rule-result/import/evidence/policy
  graphs with accessible assertion and staleness labels,
- graph set detail shows member roles, source signature, current reasoning pointer, current rule
  pointer, and stale explanation,
- graph delta viewer shows added and removed quads for a previewed edit,
- direct semantic edit workbench previews TriG/JSON-LD/constrained SPARQL Update before apply,
- validation run view shows SHACL report summary and shape version,
- reasoning run view shows OWL consistency/classification/entailment summary and result graph,
- rule run view shows generated statements and missing-evidence propagation warnings,
- fact/assertion list can filter by asserted, OWL-inferred, rule-derived, imported, policy
  metadata, review metadata, and missing evidence,
- import/export workspace can export asserted-only and full working-view graph sets,
- catalog wizard shows semantic target compatibility and treats connector test output as preview,
  not committed facts.

Backend/API tests should cover response shape contracts used by the frontend:

- graph registry DTOs include category, editability, revision, and owner fields,
- statement DTOs include assertion kind, evidence status, graph IRI, provenance, warnings, and
  editability state,
- graph delta DTOs include added/removed quads and affected graph IRIs,
- SHACL form guidance DTOs are stable enough for deterministic form rendering,
- run DTOs distinguish validation, reasoning, and rule paths.

## Implementation Checklist

### 0. Documentation

- [x] Create this Phase 8 detailed design document.
- [ ] Link this document from `semantic-language-refactor-plan.md` after parallel phase-doc edits
      settle.
- [ ] Keep this document aligned with Phase 6 and Phase 7 detailed designs when those are added.

### 1. API and Types

- [ ] Add typed frontend DTOs for semantic graphs, graph sets, statements, deltas, runs, warnings,
      and SHACL form guidance.
- [ ] Add API helpers for graph governance summary, graph registry, graph sets, semantic statements,
      edit audit detail, run history, exports, and form guidance.
- [ ] Ensure mutation responses include affected graph IRIs, revision changes, audit ids, stale
      pointers, warnings, and next actions.

### 2. Shared Semantic Components

- [ ] Add assertion-kind, evidence-status, staleness, warning, and editability badges.
- [ ] Add graph IRI label/copy component.
- [ ] Add graph editability toggle with confirmation and accessible labels.
- [ ] Add graph delta viewer with compact label view and raw quad view.
- [ ] Add validation, reasoning, and rule result panels.
- [ ] Add SHACL form renderer backed by backend guidance.

### 3. New Workspaces

- [ ] Add Graph Governance Dashboard.
- [ ] Add Named Graph Registry.
- [ ] Add Graph Set Detail.
- [ ] Add Semantic Runs page.
- [ ] Add Direct Semantic Edit Workbench.
- [ ] Add Semantic Import/Export workspace.

### 4. Existing Workflow Updates

- [ ] Update class/property/relation/entity forms to show graph target, editability, SHACL guidance,
      validation errors, and graph delta preview.
- [ ] Update fact/assertion audit to show assertion kind, provenance, evidence, warning, and stale
      state.
- [ ] Update catalog wizard to show semantic target compatibility, policy/provenance links, import
      staging, and connector preview semantics.
- [ ] Update publication/readiness surfaces to evaluate graph sets, validation, reasoning, rule
      staleness, projection status, and export readiness.

### 5. Navigation and Localization

- [ ] Extend workspace tab/stage definitions in `frontend/src/App.tsx`.
- [ ] Add Chinese translations in `frontend/src/i18n/zh.ts` without duplicate keys.
- [ ] Preserve existing query-parameter deep links while adding graph, graph set, statement, edit,
      run, and format parameters.

### 6. Verification

- [ ] Run `cd frontend && npm run build`.
- [ ] Run `cd frontend && npx playwright test`.
- [ ] Add Playwright smoke coverage for graph governance, graph sets, graph deltas, semantic edit
      preview, validation/reasoning/rule runs, assertion kind filters, import/export, and catalog
      semantic compatibility.
- [ ] Run `cd backend && uv run pytest` for any backend contract changes.

## Completion Criteria

- [ ] Ordinary users can complete core modeling and assertion workflows without writing semantic
      syntax.
- [ ] Expert users and AI agents can preview and submit governed direct semantic edits.
- [ ] Named graphs, graph sets, graph deltas, evidence/provenance, validation, reasoning, rule
      staleness, assertion kinds, warnings, and editability are visible in the UI.
- [ ] SHACL-guided forms replace ad hoc frontend constraint assumptions for supported workflows.
- [ ] Import/export supports standards-based exchange without embedding Protégé/WebProtégé.
- [ ] Playwright smoke coverage protects the reshaped workflows before legacy-only screens are
      removed.
