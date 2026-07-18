# ADR 0004: Semantic-Web-First Refactor Target

## Status

Proposed

Updated on 2026-07-04: Phase 0 technical foundation is documented in
`docs/architecture/semantic/phase0-technical-foundation.md`. The selected route uses Oxigraph as an independent
RDF service, FastAPI as orchestration/governance layer, backend SHACL validation, a separate full
OWL reasoning service, Neo4j as rebuildable visualization projection, Postgres for operational
data, direct Agent SPARQL query, and governed semantic edits including constrained SPARQL Update.

Updated on 2026-07-03: the governance target no longer uses draft/published graph promotion as the
primary workflow. AI and expert semantic edits may apply to an actual graph when that graph is
editable. Each actual graph has its own editability switch, replacing the earlier publication
concept.

## Context

The current platform grew from a lightweight custom ontology model. That model is practical for
the MVP, but a future major refactor should optimize for semantic expressiveness, long-term
interoperability, and direct machine-generated modeling input.

This ADR describes the target shape for the standard semantic-language refactor. It focuses on the
preferred storage model, reasoning/validation boundaries, and authoring interfaces needed for a
standards-first semantic foundation.

The target should still preserve the product goals that make the platform useful:

- governed modeling changes
- versioned ontology and graph editability control
- evidence-bound assertions
- auditable rule execution
- deterministic validation
- AI-assisted model extraction and update workflows

## Decision

Use an RDF Dataset / quad-store model as the canonical semantic storage layer.

The canonical record should be a set of named graphs and annotated statements, not a custom
relational schema that only exports RDF afterward.

Core storage shape:

```text
subject, predicate, object, graph
```

Named graphs should represent boundaries such as:

- actual ontology graph
- actual data graph
- imported source graph
- evidence artifact or document chunk
- optional AI-generated candidate or review metadata graph
- reviewed and approved assertion graph
- rule execution result graph
- rule-derived result graph
- OWL reasoning result graph
- access-policy graph

Use RDF-star / RDF 1.2 reification or named graph metadata to attach statement-level metadata:

```turtle
<< :student_1 :hasStatus :Excellent >>
  prov:wasGeneratedBy :rule_run_123 ;
  :confidence 0.92 ;
  :auditStatus "pending" ;
  :evidence :doc_chunk_456 .
```

The platform should expose both high-level product APIs and direct modeling interfaces. Direct
modeling interfaces are important because AI systems can now generate precise modeling statements
directly, and forcing every model change through simplified CRUD shapes can lose intent.

## Target Language Stack

Use the following standards as first-class semantic building blocks:

- RDF Dataset / named graphs: canonical graph storage and version boundaries.
- RDFS / OWL 2 DL: class, property, hierarchy, domain/range, inverse, symmetric, transitive,
  equivalence, consistency, classification, realization, entailment, and other ontology semantics.
- SKOS: concepts, labels, aliases, controlled vocabularies, broader/narrower relations, and
  terminology alignment.
- SHACL: structural validation, required fields, cardinality, datatype, enum-like constraints,
  property shapes, and form/schema generation.
- PROV-O: evidence, provenance, extraction activity, rule execution activity, model/agent/skill
  version, and source attribution.
- ODRL: permission, prohibition, obligation, masking, approval-required, and usage-policy
  expression where policy interoperability matters.
- SPARQL: query, validation support, graph inspection, and controlled update interfaces.

Use the following carefully rather than as default core dependencies:

- SWRL: do not use as the primary rule runtime. It is too broad for deterministic, explainable,
  incremental platform execution. Support only a constrained import/export or compatibility subset
  if needed.
- OWL-S: do not include in the platform core unless the product explicitly becomes a semantic web
  service discovery and composition platform.

## Modeling Interfaces

The future platform should provide three authoring surfaces.

### 1. Direct Semantic Modeling Interface

Expose a direct or lightly wrapped modeling interface for AI agents and expert tools.

Accepted input formats should include:

- Turtle / TriG for RDF datasets and named graphs
- JSON-LD for API-friendly graph payloads
- SPARQL Update for constrained patch operations
- SHACL shapes for validation and UI/form generation
- OWL functional syntax or RDF serialization for ontology axioms where useful

The interface should support atomic modeling proposals such as:

```trig
:candidateGraph_001 {
  :Student a owl:Class ;
    rdfs:label "Student"@en ;
    skos:altLabel "Learner"@en .

  :averageScore a owl:DatatypeProperty ;
    rdfs:domain :Student ;
    rdfs:range xsd:decimal .

  :ExcellentStudent a owl:Class ;
    rdfs:subClassOf :Student .
}
```

The platform should not blindly apply those statements. It should parse, validate, audit, record
evidence status for fact writes, and check whether the target graph is editable. Model structure
edits do not require evidence by default, but they must record audit metadata. A separate proposal
graph may exist for review-heavy workflows, but it is not the required write path.

SPARQL and SPARQL Update have different roles. SPARQL query is the flexible read surface. SPARQL
Update is a semantic write format and must go through the governed semantic edit interface. It is
appropriate for complex writes, such as deleting and inserting related triples based on a pattern,
but it must still produce an auditable graph delta, respect graph editability, and pass validation
before commit.

### 2. Structured Product API

Keep a business-friendly API for UI and common workflows:

- create class
- create relation type
- create assertion
- submit rule
- validate graph edit
- lock or unlock graph editing
- recall knowledge

These APIs should compile to the same canonical RDF dataset representation rather than becoming a
separate source of truth.

### 3. Read and Query Interface

Expose standard read surfaces:

- SPARQL query endpoint, initially direct for Phase 0 and later policy-aware when the security
  model is added
- JSON-LD documents for application consumption
- Turtle / TriG exports for offline review and interoperability
- compact business JSON projections for frontend screens and agent tools

Agent-facing query flexibility is required. Agents should be able to submit SPARQL directly for
complex exploration instead of being forced through many fixed business APIs. The structured
product APIs remain convenience wrappers for common frontend and workflow operations.

For Phase 0, do not build the full security model for this query endpoint. The minimum useful
boundary is read/write separation: caller-provided SPARQL is used for reads, while mutations go
through the governed semantic edit interface. Complete authorization, graph visibility policy, and
query policy enforcement can be added after the core technical route is proven.

## Rules Target

Use full OWL reasoning for ontology semantics, SHACL for graph constraints, and a limited
deterministic rule layer for business derivations.

Preferred rule execution options:

- OWL reasoner service for ontology consistency, classification, realization, and entailment
  checks.
- SHACL constraints for validation.
- SPARQL CONSTRUCT for simple graph-derived assertions.
- A restricted Datalog-like or platform DSL for explainable business rules.
- Workflow/state-machine models for process rules.

Rule execution must produce derived assertions in separate rule-run/result graphs, not silently
mutate source facts. Locked source graphs may be rule inputs, but rule execution must not directly
write derived results back into those locked graphs.
Missing-evidence facts may participate in deterministic rule execution, but derived results must
record and surface that they depend on missing-evidence input.

Every rule-derived assertion should record:

- rule id
- rule version
- execution id
- input graph or named graph set
- matched entities and relations
- generated statement
- confidence if applicable
- evidence/provenance
- audit status

## Versioning and Governance Target

Versioning should be graph-native.

Recommended graph categories:

```text
ontology:{graph_id}
data:{graph_id}
proposal:{proposal_id} optional
evidence:{evidence_id}
rule-run:{run_id}
rule-result:{run_id}
reasoning-run:{run_id}
reasoning-result:{run_id}
review:{review_id}
policy:{policy_id}
```

The primary workflow is not draft-to-published promotion. The platform maintains actual ontology
and data graphs. Each actual graph has its own editability switch controlling whether validated
semantic edits may be applied. Locking a graph prevents ordinary edits to that graph; unlocking it
allows controlled edits to that graph without necessarily unlocking other graphs. In this phase,
lock/unlock is a collaboration state, not a role-based access-control boundary: any user may lock
or unlock a graph, and the platform records the operation in audit metadata.
For the Phase 0 POC, an attempted direct edit against a locked graph only needs to return failure;
it does not need to create a persisted failed-edit audit event.
The Phase 0 POC should expose minimal backend API endpoints for dataset loading/parsing, querying,
validation, direct semantic edits, graph editability toggling, and export. Phase 0 is not a shipped
product version; it is the stage that defines the core technical route for this version's
standardized semantic-language refactor. It should use the intended RDF-native stack from the
beginning, while keeping product functionality small. It should not introduce projection rebuilders
or full frontend workflows yet.
The detailed Phase 0 output is maintained in `docs/architecture/semantic/phase0-technical-foundation.md`.
The Phase 0 API surface should stay limited to seven endpoint categories: load/parse dataset, query
named graphs with caller-provided SPARQL, validate with SHACL, run OWL reasoning, submit direct
semantic edit, toggle one graph's editability, and export as TriG or JSON-LD.
Phase 0 SHACL validation runs in the FastAPI backend validation service, using `pyshacl` or an
equivalent runtime over data and shape graphs fetched from Oxigraph. Oxigraph is not required to
provide native SHACL validation in this phase.
Phase 0 also includes a separate OWL reasoning service over selected ontology/data graph sets. The
baseline reasoner candidate is HermiT for full OWL 2 DL reasoning, with Openllet as an evaluation
candidate where explanation or Jena integration is useful. Reasoning results are derived semantic
results and should be returned as reports or stored in explicit reasoning result graphs, not written
silently into source graphs.
Persisted reasoning result graphs are reusable for later SPARQL queries and Neo4j projection until
their source graph set, reasoner configuration, or reasoner version changes. Source ontology/data
graphs remain the record of asserted facts; reasoning result graphs are the record of inferred
facts.
Only the current effective reasoning result graph needs to be retained by default. Older reasoning
result graphs for the same graph set may be deleted or garbage-collected after a newer reasoning run
succeeds, because they are rebuildable derived data. Minimal reasoning-run metadata can remain for
audit and troubleshooting.
Deterministic rule execution may still write to a separate rule result graph when its source graph
is locked.

Review, audit, and editability status checks should operate over graph deltas:

- added triples/quads
- removed triples/quads
- changed shapes
- changed entailments
- new conflicts
- stale derived assertions
- policy changes
- rule result graphs derived from locked source graphs
- reasoning result graphs derived from ontology/data graph sets

## Validation Target

Validation should combine semantic and product rules:

- Full OWL reasoning for ontology consistency, classification, realization, and entailment over
  selected graph sets.
- SHACL validation for graph shape, cardinality, datatype, and required properties.
- Platform checks for evidence, review status where required, editability state, and policy. This
  target does not introduce role-based permission checks for graph lock/unlock.
- Rule safety checks for deterministic execution.

The validation service is separate from the RDF store boundary. Oxigraph stores and serves RDF
datasets; the backend validation service runs SHACL and returns validation reports. This keeps the
validation route portable if the RDF store changes later.
OWL reasoning is also separate from the RDF store boundary. Because ontology graph size is expected
to remain manageable, the platform should support full OWL reasoning over selected graph sets. The
reasoner remains separate from Oxigraph storage and SHACL validation.
Reasoning results and source assertions must remain separate graph boundaries. Query and display
layers may merge them, but storage should preserve whether a statement was asserted by a user/AI or
inferred by the reasoner.

Fact writes may enter the actual graph without evidence, but missing evidence must be stored as an
explicit evidence status. Recall surfaces must warn when returning facts that are missing evidence,
so a later AI or human workflow can verify them. Model structure edits do not require evidence by
default, but they require audit metadata such as actor, time, reason, input format, and validation
result.
If a missing-evidence fact contributes to a rule-derived result, that result must carry the same
warning forward.

SHACL should become the primary bridge between semantic modeling and UI/application convenience:

- generate forms from shapes
- validate AI-generated model statements
- validate imports
- describe allowed properties for each class
- explain validation failures in business terms

## Storage and Indexing Target

The canonical store should be an RDF quad store or RDF-native database.
For the Phase 0 PoC, use Oxigraph as an independent RDF-native graph service rather than an
embedded FastAPI-local store.

Add projections only for convenience and performance:

- full-text index for labels, aliases, evidence, and notes
- vector index for semantic retrieval and background knowledge
- Neo4j property-graph projection for visualization and high-speed traversal
- relational operational tables for users, jobs, credentials, and system audit events if the RDF
  store is not suitable for those workloads

The projections must be rebuildable from the canonical semantic store plus operational logs.
Neo4j must not become a second semantic source of truth: semantic writes go to Oxigraph first, then
projection jobs or explicit POC sync logic update Neo4j for graph-display reads.

## Consequences

Benefits:

- Stronger interoperability with semantic web tooling.
- Less custom invention around ontology, constraints, provenance, terminology, and policies.
- AI agents can submit precise modeling statements directly.
- Better long-term export/import story through RDF, OWL, SHACL, SKOS, PROV-O, ODRL, and SPARQL.
- Cleaner separation between canonical semantic meaning and UI/API convenience projections.

Costs:

- Higher implementation complexity.
- Developers need RDF, OWL, SHACL, SPARQL, and named-graph literacy.
- Query authorization becomes more subtle because graph visibility and statement metadata matter.
- OWL reasoning, SHACL validation, and rule execution need clear execution boundaries to stay
  predictable.
- UI and agent APIs still need friendly wrappers to prevent users from having to author raw graph
  syntax manually.

## Non-Goals

- Do not make every user write Turtle or SPARQL.
- Do not adopt the full RDF/OWL/SKOS/SWRL/OWL-S/ODRL/SPARQL set as mandatory core runtime beyond
  the selected Phase 0 semantic stack. Full OWL reasoning is intentionally included; SWRL and OWL-S
  are not.
- Do not use SWRL as the default rule execution engine.
- Do not introduce OWL-S unless service discovery/composition becomes a first-class product goal.
- Do not let AI-generated modeling statements bypass validation, evidence-status labeling for fact
  writes, audit, or editability governance.
- Do not build the platform on top of Protégé or WebProtégé, and do not integrate either tool in
  Phase 0. Keep standard RDF/OWL/Turtle/TriG/JSON-LD compatibility so expert-tool exchange remains
  possible later.

## Migration Direction

If moving from the current model toward this target, use an incremental path:

1. Establish the RDF-native service foundation:
   Oxigraph service, backend RDF store boundary, SHACL validation service, OWL reasoner boundary,
   minimal Neo4j projection, and Postgres operational metadata.
2. Add stable IRIs, namespaces, JSON-LD context definitions, and semantic mappings for current
   objects.
3. Add RDF/OWL/SKOS/SHACL export for current schemas and graph data.
4. Add direct Turtle/TriG/JSON-LD/constrained SPARQL Update semantic edit ingestion guarded by
   validation, evidence-status labeling, audit, and the graph editability switch.
5. Add named-graph storage for actual graphs, evidence, assertions, reasoning runs/results, rule
   runs/results, audit/review metadata, policies, imports, and versions.
6. Move read APIs to graph-derived projections, with Neo4j, full-text, and vector stores as
   rebuildable projections.
7. Promote RDF Dataset storage to canonical once round-trip parity, reasoning, validation, governed
   edit, and projection behavior are proven.

The most important early step is the direct semantic modeling edit interface: AI-generated
modeling statements should be first-class graph edits, while the platform remains responsible for
deterministic validation, audit, evidence-status labeling, and editability governance.
