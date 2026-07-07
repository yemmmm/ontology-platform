# Phase 8 Frontend Workflow Design

## Status

Detailed design. This document supersedes the earlier Phase 8 direction that exposed named graphs,
graph sets, and graph governance as primary frontend workspaces.

The confirmed product direction is:

- ordinary users work with business concepts only;
- RDF named graphs, graph sets, RDF syntax, and raw triple management are platform internals;
- Neo4j-backed property-graph projections are the preferred source for interactive graph
  visualization and traversal;
- canonical semantic truth remains in the RDF Dataset / quad-store;
- default edits take effect immediately after backend validation;
- the current platform does not include version publication, role-based permissions, or separate
  create/update/delete permissions.

## Goal

Provide a smaller, clearer frontend for the current platform:

1. Requirement brief and overview.
2. Business modeling workspace with class diagram, entity diagram, and fact list.
3. A simple workspace edit lock.
4. Debug and settings tools.

The frontend must not require users to understand RDF graphs, graph sets, named graphs, Turtle,
TriG, JSON-LD, SPARQL, OWL, or SHACL. Those concepts may exist behind the product API, but they are
not navigation concepts, editable resources, or required mental models in the UI.

## Product Principles

1. The user sees business objects, not storage partitions.
2. Class and entity diagrams are product graph views, not RDF graph editors.
3. Neo4j projections power graph exploration, layout, neighborhood expansion, and traversal.
4. RDF remains the canonical semantic store; Neo4j is rebuildable derived data.
5. Changes are made through business CRUD APIs and backend validation, not direct RDF writes.
6. The edit lock is a workspace safety switch, not a permission system.
7. Debug tools explain platform state without exposing raw RDF graph editing.
8. Publication/version workflows are out of scope for this stage; accepted changes are effective
   immediately.

## Navigation

The main workspace should be reduced to four top-level areas.

| Area | Purpose | Primary user |
| --- | --- | --- |
| Overview | Requirement brief, current ontology summary, progress, quality, freshness, and recent changes. | Analyst, modeler |
| Modeling | Class diagram, entity diagram, and fact list with business CRUD. | Analyst, modeler |
| Debug | Validation, projection, import/export, diagnostics, and job status. | Maintainer, advanced user |
| Settings | Workspace edit lock and platform configuration. | Maintainer |

`Debug` and `Settings` may be combined as `Debug & Settings` if navigation space is tight.

Recommended first implementation tabs:

```text
overview
modeling/classes
modeling/entities
modeling/facts
debug
settings
```

The current "Graph Sets" entry should not be a required entry point for modeling. Any internal
graph-set selection must happen automatically on the backend or in a hidden application state.

## 1. Overview

### Purpose

Show the current ontology workspace at a glance.

### Content

- Requirement brief.
- Business scope and modeling objective.
- Key competency questions or target use cases.
- Counts for classes, relation types, entities, facts, and evidence items.
- Modeling completeness indicators.
- Validation summary in business language.
- Projection freshness status.
- Recent changes.
- Current edit state: locked or unlocked.

### Actions

- Continue modeling.
- Open class diagram.
- Open entity diagram.
- Open fact list.
- Run validation.
- Rebuild projection when stale.
- Open settings to lock or unlock editing.

### UI Rules

- Do not show graph IRIs, graph sets, named graph counts, or RDF syntax.
- If backend state depends on internal RDF graph sets, summarize it as "workspace data" or
  "semantic storage" only when a diagnostic explanation is needed.
- If the Neo4j projection is stale, explain it as "graph view is out of date" and provide a rebuild
  action.

## 2. Modeling Workspace

The modeling workspace has three primary views.

### 2.1 Class Diagram

#### Purpose

Model ontology structure through classes, attributes, hierarchy, and class-level relationship types.

#### Read Model

The class diagram should be loaded from a backend product projection. The backend may combine RDF
source data, SHACL shapes, inference output, and Neo4j projection data, but the frontend receives a
business-oriented graph model:

```text
ClassNode
ClassAttribute
ClassRelationship
ClassHierarchyEdge
ValidationSummary
EditState
```

#### Required CRUD

- Create class.
- Rename class.
- Edit class description, aliases, and business notes.
- Add, edit, or remove attributes.
- Add, edit, or remove class-level relationship types.
- Add, edit, or remove superclass/subclass links.
- Delete class when backend confirms it is safe.

#### UX Behavior

- Use graph canvas for structure and side panel/drawer for details.
- Use forms with business labels, not RDF predicates.
- Show validation errors before or after save in business terms.
- Disable all mutating controls when the workspace is locked.
- For destructive operations, show impact: affected entities, facts, and relationships.

### 2.2 Entity Diagram

#### Purpose

Model and inspect entities, entity relationships, class membership, and important attached facts.

#### Read Model

The entity diagram should primarily use Neo4j projection APIs for interactive graph traversal and
layout:

```text
EntityNode
EntityRelationship
ClassMembership
AttachedFactSummary
EvidenceStatusSummary
ProjectionFreshness
EditState
```

#### Required CRUD

- Create entity.
- Edit entity label, aliases, class membership, and key attributes.
- Delete entity when backend confirms impact.
- Create relationship between entities.
- Edit relationship type and relationship properties.
- Delete relationship.
- Add or edit key facts attached to an entity or relationship.

#### UX Behavior

- Start from the current ontology overview or search result, not from graph-set selection.
- Support expand-neighborhood, collapse, search, filter by class, and filter by relationship type.
- Show evidence and validation summaries without requiring users to open raw statements.
- Warn when projection is stale and provide rebuild action.
- Disable mutating controls when the workspace is locked.

### 2.3 Fact List

#### Purpose

Provide a dense operational list of facts and evidence status.

#### Read Model

```text
FactRow
SubjectLabel
PredicateLabel
ObjectLabelOrValue
EvidenceStatus
SourceContext
ValidationState
UpdatedAt
EditState
```

#### Required CRUD

- Create fact.
- Edit fact value, subject, predicate, evidence binding, and notes where supported.
- Delete fact.
- Link or unlink evidence.
- Mark missing evidence when allowed by platform validation.

#### Filters

- Subject/entity.
- Class.
- Predicate/fact type.
- Evidence status.
- Validation state.
- Source/import context.
- Last updated time.

#### UI Rules

- Do not show triples, graph IRIs, or named graph membership as primary columns.
- Use "Fact", "Evidence", "Source", "Validation" and "Status" as user-facing language.
- Raw semantic identifiers may be hidden behind copy/debug affordances only if needed for support.

## 3. Edit Lock

### Purpose

Provide one simple control for whether the current workspace accepts modeling changes.

### Behavior

- `Unlocked`: create, edit, and delete controls are available.
- `Locked`: create, edit, and delete controls are disabled.
- Locking applies to class diagram, entity diagram, and fact list changes.
- Locking does not imply user permissions, approval workflow, publication workflow, or per-action
  authorization.
- Lock/unlock events should still be audited by the backend.

### Placement

The primary control belongs in Settings:

```text
Settings -> Editing -> Lock workspace / Unlock workspace
```

The current state should also appear in the global header or overview summary.

### Disabled State Copy

Use direct explanations:

- "Workspace is locked. Unlock in Settings to edit."
- "This change cannot be saved because editing is locked."

Do not say:

- "Graph is not editable."
- "Target named graph is locked."
- "You do not have create permission."

## 4. Debug and Settings

### Purpose

Give maintainers enough operational control without exposing RDF graph management as a frontend
concept.

### Debug Capabilities

- Projection status:
  - current or stale,
  - last rebuild time,
  - source signature,
  - rebuild action,
  - latest error.
- Validation status:
  - latest validation result,
  - issue count,
  - run validation action,
  - issue list in business terms.
- Reasoning/rule status where available:
  - current or stale,
  - last run time,
  - run action,
  - warning count.
- Import/export status:
  - latest imports,
  - export business model,
  - export standards package if supported.
- API/runtime diagnostics:
  - backend health,
  - semantic storage health,
  - Neo4j projection health,
  - search/vector index health if enabled.

### Settings Capabilities

- Lock/unlock workspace.
- Configure graph view display defaults.
- Configure projection rebuild behavior where needed.
- Configure import/export options.
- Configure validation strictness if the backend exposes safe presets.

### Explicit Non-Goals

- No named graph registry page.
- No graph set selection page for ordinary or advanced users.
- No raw RDF graph editor.
- No direct triple table editing.
- No SPARQL update workbench in the product UI for this stage.
- No publication/version management.
- No role-based permission matrix.
- No separate create/update/delete permission toggles.

## Backend and Data Flow

### Read Flow

```text
RDF Dataset / quad-store
  -> backend semantic read model
  -> Neo4j property-graph projection for graph traversal where useful
  -> product APIs
  -> frontend business views
```

The frontend should call product APIs such as:

```text
GET /api/workspace/overview
GET /api/modeling/classes/graph
GET /api/modeling/entities/graph
GET /api/modeling/facts
GET /api/debug/status
GET /api/settings/edit-lock
```

Actual endpoint names can follow existing backend conventions, but the contract should be
business-oriented.

### Write Flow

```text
frontend business CRUD action
  -> product API command
  -> backend edit-lock check
  -> backend validation
  -> governed semantic write to canonical RDF storage
  -> audit record
  -> projection marked stale or rebuilt
  -> updated product read model
```

Class, entity, relationship, and fact changes should never write directly to Neo4j as semantic
truth. Neo4j may be updated by a projection rebuild or controlled projection writer after the
canonical write succeeds.

## Projection Strategy

For the current stage, map the key semantic data needed by the UI into Neo4j:

- classes;
- class hierarchy;
- class attributes;
- class-level relationship types;
- entities;
- entity-to-entity relationships;
- class membership;
- key facts;
- evidence status summaries;
- validation warning summaries.

The projection should carry internal metadata needed for rebuild and diagnosis:

- workspace or ontology id;
- source signature;
- projection job id;
- projection build time;
- asserted/inferred/derived classification where relevant;
- stale/current state.

The UI should render the classification as business labels such as "modeled", "inferred",
"calculated", or "needs review", not as graph names.

## Information Architecture Summary

```text
Overview
  Requirement brief
  Modeling summary
  Quality and freshness
  Recent changes

Modeling
  Class Diagram
    CRUD classes, attributes, hierarchy, relation types
  Entity Diagram
    CRUD entities, relationships, key facts
  Fact List
    CRUD facts and evidence bindings

Debug
  Projection status and rebuild
  Validation status and run
  Reasoning/rule status if enabled
  Import/export status
  Runtime health

Settings
  Lock/unlock workspace
  Graph display defaults
  Import/export options
  Validation presets
```

## Implementation Notes

1. Remove Graph Sets as a required frontend step before modeling.
2. Auto-resolve the active internal graph scope in the backend.
3. Rename user-facing "graph set" language to "workspace", "current model", or "current ontology
   data" depending on context.
4. Use Neo4j projection APIs for interactive class/entity graph canvases where traversal and layout
   matter.
5. Keep fact lists and overview panels backed by product read models, not raw RDF queries in the
   browser.
6. Keep RDF graph identifiers out of normal UI copy, table columns, filters, and route parameters.
7. Preserve internal provenance and source signatures for correctness and diagnostics.
8. Treat stale projection as a visible operational state, not as a user-selected graph problem.

## Acceptance Criteria

- A user can open the platform and see overview content without selecting a graph set.
- A user can open class diagram, entity diagram, and fact list without understanding RDF.
- Class diagram supports create, read, update, and delete flows.
- Entity diagram supports create, read, update, and delete flows for entities and relationships.
- Fact list supports create, read, update, and delete flows for facts and evidence bindings.
- Locking the workspace disables all mutating modeling controls.
- Unlocking the workspace enables mutating modeling controls.
- Debug pages show projection, validation, and runtime state without exposing raw RDF graph editing.
- Neo4j projection can be stale, rebuilt, and inspected operationally.
- Canonical semantic writes still go through backend validation and RDF storage.
