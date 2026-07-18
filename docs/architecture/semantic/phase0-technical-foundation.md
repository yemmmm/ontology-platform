# Phase 0 Technical Foundation

Date: 2026-07-04

This document is the Phase 0 output for the standard semantic-language refactor. Phase 0 is not a
release version. It defines the technical route that later implementation phases should follow.

## Goal

Build the platform around standard semantic languages and graph-native governance:

- RDF Dataset and named graphs for canonical semantic storage.
- SPARQL for flexible graph query.
- Turtle, TriG, JSON-LD, and constrained SPARQL Update for direct semantic edits.
- SHACL for structural validation.
- OWL 2 DL reasoning for ontology semantics.
- PROV-O/SKOS/ODRL where they fit provenance, terminology, and policy needs.

## Baseline Architecture

```text
FastAPI
  -> Oxigraph: canonical RDF dataset, named graphs, SPARQL query/update
  -> OWL reasoner: full OWL 2 DL consistency, classification, realization, entailment
  -> pySHACL: backend SHACL validation
  -> Neo4j: rebuildable property-graph projection for visualization/traversal
  -> Postgres: operational data, jobs, service settings, run metadata, current result pointers
```

## Component Decisions

### Oxigraph

Oxigraph is the RDF-native store for Phase 0. It runs as an independent service, not embedded
inside FastAPI.

Responsibilities:

- Store RDF datasets and named graphs.
- Serve SPARQL query/update.
- Persist source ontology/data graphs and derived result graphs.
- Export TriG and JSON-LD through backend-controlled endpoints.

Non-responsibilities:

- Native SHACL validation.
- OWL reasoning.
- Neo4j-style visualization traversal.
- Application permissions or credentials.

### FastAPI

FastAPI is the orchestration and governance layer.

Responsibilities:

- Expose backend API endpoints.
- Apply graph editability checks.
- Route agent SPARQL query requests to Oxigraph.
- Route semantic writes through deterministic parse/validate/audit/apply logic.
- Run SHACL validation through backend validation service.
- Run OWL reasoning through a reasoner boundary.
- Coordinate Neo4j projection.
- Store operational metadata in Postgres where appropriate.

### SHACL Validation

SHACL validation runs in the FastAPI backend validation service with `pyshacl` or an equivalent
runtime.

Flow:

```text
FastAPI
  -> fetch data graph and shape graph from Oxigraph
  -> run SHACL validation
  -> return validation report
  -> record validation-run metadata
```

Oxigraph is not required to support SHACL natively.

### OWL Reasoning

OWL reasoning is a system computation, not an AI guess or an AI query.

Baseline:

- HermiT is the baseline candidate for full OWL 2 DL reasoning.
- Openllet is an evaluation candidate where explanation support or Jena integration is useful.

Reasoner responsibilities:

- Consistency checks.
- Class/property hierarchy classification.
- Individual realization.
- Entailment checks.

Reasoner results:

- Source ontology/data graphs are never mutated by inferred statements.
- Persisted inferred statements go into `graph:reasoning-result/{run_id}`.
- `graph:reasoning-run/{run_id}` records run metadata.
- Only the current effective reasoning result graph needs to be retained by default.
- Older reasoning result graphs may be deleted after a newer successful run for the same graph set.

Enhancement hook:

- Phase 0 can call the reasoner through a command wrapper or simple service.
- Later phases can promote it to a long-running service and async/background recomputation.

### Neo4j

Neo4j remains in the architecture as a rebuildable property-graph projection.

Responsibilities:

- Graph visualization.
- High-speed traversal.
- UI-friendly relationship exploration.

Non-responsibilities:

- Owning semantic truth.
- Accepting independent semantic writes.
- Deciding validation, reasoning, or evidence truth.

Neo4j data must be rebuildable from Oxigraph source graphs plus current reasoning/rule result
graphs where the view requires inferred or derived statements.

### Postgres

Postgres remains for operational data where RDF is not the right workload.

Examples:

- Users and sessions when authentication exists.
- Jobs and task state.
- Service settings.
- Validation/reasoning run status summaries.
- Current effective reasoning result pointers.
- Credentials and external connector settings.

Semantic meaning, provenance, evidence status, ontology structure, and facts should move into RDF
graphs as the refactor progresses.

## Graph Model

Canonical graph IRI patterns:

```text
graph:ontology/{graph_id}
graph:data/{graph_id}
graph:proposal/{proposal_id}
graph:evidence/{evidence_id}
graph:rule-run/{run_id}
graph:rule-result/{run_id}
graph:reasoning-run/{run_id}
graph:reasoning-result/{run_id}
graph:review/{review_id}
graph:policy/{policy_id}
graph:import/{source_id}/{import_run_id}
```

Source and derived data are separate:

```text
graph:ontology/{graph_id}          asserted ontology structure
graph:data/{graph_id}              asserted business facts
graph:reasoning-result/{run_id}    OWL-inferred statements
graph:rule-result/{run_id}         business-rule-derived statements
```

Query and display layers may merge these graph boundaries, but storage must preserve the difference
between asserted, inferred, and rule-derived statements.

## Editability Model

There is no draft/published graph workflow.

Each actual graph has its own editability switch:

- Editable graph: validated semantic edits may apply.
- Locked graph: ordinary semantic edits are rejected.

For Phase 0 POC simplicity, locked write attempts only need to return failure. They do not need
persisted failed-edit audit events.

Any user may lock/unlock graphs for now. The platform does not implement RBAC or permission control
in Phase 0.

## Agent Interfaces

### SPARQL Query

Agents may submit SPARQL directly for flexible reads. Fixed product APIs are convenience wrappers,
not the only query path.

Phase 0 controls are intentionally minimal:

- Keep query and write paths separate.
- Keep the query endpoint read-oriented.
- Apply simple timeout/result-size limits if available.
- Do not implement full authorization, graph visibility policy, or query policy enforcement yet.

### Semantic Edit

Semantic writes go through a governed semantic edit endpoint.

Accepted input formats:

- Turtle.
- TriG.
- JSON-LD.
- Constrained SPARQL Update.

Semantic edit flow:

```text
parse input
  -> compute graph delta where practical
  -> validate with SHACL and platform checks
  -> check graph editability
  -> record audit metadata
  -> write to Oxigraph
  -> update derived/projection state when explicitly triggered
```

Constrained SPARQL Update is allowed for complex writes, but it is not a raw database write bypass.
Start with delta-friendly update forms and expand later.

## Evidence and Derived Warnings

Fact writes may enter the actual graph without evidence, but they must carry explicit evidence
status. Recall and query-facing surfaces should warn when returning missing-evidence facts.

If a missing-evidence fact contributes to a business rule result, the derived result must carry a
propagated warning.

## Protégé Decision

Protégé/WebProtégé is not used as platform core and is not integrated in Phase 0.

The platform should implement its own governed semantic backend and modeling workflows. It should
preserve interoperability through RDF/OWL/Turtle/TriG/JSON-LD so expert users can inspect or
exchange models with external tools later.

## Phase 0 POC API Surface

The minimal backend API surface has seven endpoint categories:

1. Load or parse a dataset into Oxigraph.
2. Query named graphs with caller-provided SPARQL.
3. Validate a dataset or target graph with backend SHACL validation.
4. Run OWL reasoning over a selected graph set.
5. Submit a direct semantic edit against an actual graph.
6. Toggle one graph's editability switch.
7. Export the RDF dataset as TriG or JSON-LD.

Do not add broad product workflows, frontend workflows, permissions, full graph visibility policy,
broad search APIs, or a full Neo4j projection pipeline in Phase 0.

## Phase 0 Done Means

Phase 0 is complete when these artifacts exist:

1. Namespace and IRI convention documentation.
2. Current object to semantic mapping.
3. JSON-LD context draft.
4. Minimal backend named-graph POC API backed by Oxigraph.
5. Backend SHACL validation report from Oxigraph-loaded data and shapes.
6. OWL reasoning report and reasoning result graph from Oxigraph-loaded graph sets.
7. Minimal Neo4j visualization projection sourced from Oxigraph.
8. Store/library evaluation note covering Oxigraph, pySHACL, HermiT, Openllet, and projection
   boundaries.
