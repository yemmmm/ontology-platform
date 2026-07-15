# Ontology Platform Glossary

> **Note (2026-07-08):** As of the evidence-storage refactor, "evidence
> status" / "missing-evidence fact" / "derived_from_missing_evidence" are
> derived states computed from the Postgres `fact_evidence_bindings`
> table, not RDF markers. The legacy `op:evidenceStatus` literal and
> `prov:wasDerivedFrom` evidence edges have been removed. See
> `docs/superpowers/specs/2026-07-08-evidence-postgres-refactor-design.md`.

This context defines the language for governed ontology and knowledge graph modeling in the
platform. It keeps semantic-web refactor terms distinct from current storage and UI terms.

## Language

**Semantic Resource**:
A thing identified by a stable IRI in the platform's semantic model, such as a class, property,
entity, proposal, evidence item, review decision, rule, or policy.
_Avoid_: row, record, node

**Evidence Reference**:
A project-owned evidence item consisting of a document name and the exact document excerpt supplied
by an external modeling Agent. Any ontology in the project may associate a model structure or fact
with the same reference. The reference preserves what the Agent cited; it does not mean the platform
stores, parses, versions, or independently verifies the complete source document.
_Avoid_: uploaded document, evidence artifact, parsed chunk, platform-verified quotation

**Evidence Association**:
The project-validated relationship from one concrete modeling item or fact to an Evidence Reference.
One item may cite multiple references, and one reference may support items in multiple ontologies
within the same project. It is not a general assignment of a document to an ontology.
_Avoid_: ontology document ownership, batch-level evidence, copied evidence

**Statement Occurrence**:
One immutable occurrence of a normalized RDF statement in a named graph at a specific graph
revision. Re-inserting the same statement after deletion creates a new occurrence. It is the
technical lineage unit beneath facts and RDF-backed model structures, not a business-facing
Semantic Resource.
_Avoid_: resource version, database row, current triple only

**Lineage**:
The trace that explains a knowledge item's origin, supporting context, derivation dependencies, and
edit audit. Evidence, Agent rationale, competency questions, edit audits, and derivation premises
remain distinct parts of the trace and never substitute for one another.
_Avoid_: evidence only, source graph label, generated-by string

**Lineage Completeness**:
Whether the platform can return the complete recorded origin and, for a derived statement, the
available premise chain. `complete` means the required trace is recorded, `partial` means only a
coarse run/input snapshot or legacy origin is known, and `missing` means no trustworthy origin is
available.
_Avoid_: evidence status, validation status, truth score

**Derivation Proof Level**:
The precision of a derived statement's dependency trace. `exact` identifies concrete premise
Statement Occurrences, `coarse` identifies only the producing run and its versioned input snapshot,
and `unavailable` means the engine supplied neither. A coarse or unavailable proof must never be
expanded into invented premises or copied document evidence.
_Avoid_: confidence, evidence status, inferred proof

**Named Graph**:
A semantic or governance boundary inside an RDF Dataset that contains statements for the actual
ontology model, actual business data, evidence item, reasoning result, rule result, review/audit
metadata, policy, or import.
_Avoid_: table, project graph, property graph

**Graph Set**:
The group of named graphs that together define the current semantic state, such as an ontology
graph plus its data graph, governing policy graph, and current effective reasoning/rule result
graphs where inferred or derived statements are needed.
_Avoid_: snapshot, bundle

**Build Context**:
A project-level, server-derived recovery view for external modeling Agents. It summarizes the
Project Brief, all Ontologies in the Project, unresolved work, active or recent Build Sessions,
accepted modeling batches, failures, and recent activity. It is not an Agent conversation or a
single Ontology's graph view.
_Avoid_: Graph Set context, chat history, Agent local workspace

**Modeling Context**:
An Ontology-scoped, server-derived view of the current authoritative semantic baseline, its
workspace version, validation state, and detailed query entry points. Batch history explains how
the baseline changed but does not replace it.
_Avoid_: previous Session state, Checkpoint summary, replayed batch history

**Build Session**:
A project-owned durable record of one externally coordinated continuous work process. One session
may be resumed by a different authorized Agent instance and may inspect or update multiple
Ontologies in the Project. The platform records progress, checkpoints, accepted batches, and
activity, but does not run or host the Agent.
_Avoid_: model runtime, chat session, Graph Set session

**Build Checkpoint**:
An append-only progress statement reported by an external modeling Agent within a Build Session.
It records the current phase and step, intended next step, current Ontology focus, blockers, or a
failure explanation. It complements, but never replaces, progress derived from accepted platform
records.
_Avoid_: platform-inferred Agent plan, mutable progress note

**Ontology Lease**:
A time-limited exclusive right held by a Build Session to apply modeling changes to one Ontology.
It prevents concurrent Agents from silently overwriting the same Ontology, while reads and work on
other Ontologies remain available. Lease expiry removes edit authority but does not cancel the
Build Session or delete its progress.
_Avoid_: Graph Set lock, project-wide lock, user permission

**Modeling Batch**:
A client-identified immutable unit of modeling content that groups one or more changes for exactly
one Ontology. The same Batch may be previewed or applied through multiple Batch Attempts, while its
Modeling Items and supporting context remain unchanged.
_Avoid_: proposal, Agent message, cross-Ontology transaction

**Batch Attempt**:
One idempotent dry-run, application, or recovery execution of an immutable Modeling Batch against a
specific workspace version. Multiple attempts preserve processing history without duplicating the
modeled content.
_Avoid_: new Modeling Batch, content revision, duplicate application

**Modeling Item**:
One client-identified modeling change inside a Modeling Batch. It is the smallest unit for command
compilation, validation status, modeling rationale, competency-question links, and evidence links.
_Avoid_: RDF statement, batch-level evidence, chat step

**Atomic Dependency Group**:
A maximal cyclic group of Modeling Items whose successful application depends on one another and
which must therefore be applied or withheld together during partial application. The cycle itself
does not imply invalid domain semantics.
_Avoid_: invalid cycle, sequential execution order, partial cyclic write

**Validation Finding**:
A structured deterministic result that identifies a modeling error, warning, or informational
observation at Batch, Atomic Dependency Group, or Modeling Item scope.
_Avoid_: exception text, Agent opinion, unstructured validation message

**Modeling Command Handler**:
A registered adapter that validates and normalizes one Modeling Item command and produces its
deterministic write effects and operation plan without controlling Batch transactions or mode.
_Avoid_: endpoint-specific compiler, Agent tool implementation, unrestricted command executor

**Ontology Write Fence**:
A durable guard owned by an applying or recovering Batch Attempt that prevents another write from
crossing an expired or rotating Ontology Lease until the original Attempt reaches a safe terminal state.
_Avoid_: Project lock, user permission, permanent graph lock

**Rule**:
An Ontology-scoped logical resource with a stable identity, lifecycle status, and one current Rule
Definition Version.
_Avoid_: rule execution, mutable rule body, Rule Result

**Rule Definition Version**:
An immutable version of a Rule's executable definition, inputs, outputs, safety policy, and metadata.
Updating a Rule creates a new version and preserves the superseded version.
_Avoid_: logical Rule, Rule Run, in-place rule edit

**Actual Graph**:
The named graph that semantic edits affect when graph editing is enabled.
_Avoid_: draft graph, published graph

**Editable Graph**:
An actual graph whose own editability switch allows validated semantic changes to be applied.
_Avoid_: draft graph

**Locked Graph**:
An actual graph whose own editability switch prevents ordinary semantic changes. In the current
platform target, locking is a collaboration state and not a permission boundary.
_Avoid_: published graph

**Lock Audit**:
The record of who or what locked or unlocked a graph, when it happened, and why. It is not a record
of every failed edit attempt.
_Avoid_: approval

**Rule Result Graph**:
A named graph that stores statements produced by deterministic rule execution, separate from the
source graph the rule read.
_Avoid_: source graph mutation, hidden update

**Reasoning Result Graph**:
A named graph that stores statements inferred by the OWL reasoning service, separate from the source
ontology or data graphs used as input. It is rebuildable derived data; older result graphs may be
deleted after a newer result for the same graph set succeeds.
_Avoid_: source graph mutation, asserted fact

**Fact Write**:
A semantic edit that adds, changes, or removes a concrete business fact about a real class member,
relationship, event, measurement, or assertion.
_Avoid_: model edit, schema change

**Evidence Status**:
The recorded state that says whether a fact has supporting evidence, is missing evidence, or still
needs later verification.
_Avoid_: proof

**Missing-Evidence Fact**:
A fact that is allowed into the actual graph without supporting evidence, but must be clearly
marked and surfaced with a warning during recall.
_Avoid_: verified fact

**Derived Risk Warning**:
A warning carried by a rule result when the result depends on missing-evidence input.
_Avoid_: verified conclusion

**Model Structure Edit**:
A semantic edit that changes the ontology model itself, such as a class, property, relation type,
shape, label, alias, or hierarchy.
_Avoid_: fact write

**Edit Audit**:
The required record of a semantic edit, including who or what made the edit, when it happened, why
it happened, what input was used, and how validation ended.
_Avoid_: evidence

**Validation Service**:
The backend service responsible for checking semantic data against SHACL shapes and platform
validation rules. It reads graph data from the RDF store but is not the RDF store itself.
_Avoid_: Oxigraph native validation, database constraint

**OWL Reasoning Service**:
The semantic service that runs OWL reasoning over selected ontology/data graph sets to check
consistency, compute class/property hierarchies, classify individuals, and answer entailment
questions. It reads from the RDF store but does not own source graph truth.
_Avoid_: SHACL validation service, business rule engine, Oxigraph storage

**Projection**:
A rebuildable operational representation derived from canonical semantic state for product APIs,
UI screens, search, vector retrieval, or property-graph traversal.
_Avoid_: source of truth, cache when it implies semantic ownership

**Property-Graph Projection**:
A graph view rebuilt from canonical RDF data for visualization and high-speed traversal.
It is not allowed to own semantic truth or accept independent semantic writes.
_Avoid_: canonical graph, ontology store, truth store

**Business Overview**:
The user-facing summary of the current ontology workspace, including the requirement brief, modeling
scope, progress, quality signals, projection freshness, and recent changes.
_Avoid_: graph set dashboard, RDF graph overview

**Business Modeling Workspace**:
The user-facing modeling area for class diagrams, entity diagrams, and fact lists. It exposes
business concepts and CRUD actions, while the platform translates accepted changes into governed
semantic storage updates.
_Avoid_: RDF editor, graph set editor, named graph workspace

**Class Diagram**:
A product graph view focused on classes, attributes, class hierarchy, and class-level relationship
types.
_Avoid_: ontology graph, RDF schema graph

**Entity Diagram**:
A product graph view focused on entities, entity-to-entity relationships, class membership, and
important attached facts.
_Avoid_: data graph, property graph source

**Fact List**:
A product list view of business assertions with evidence status, source context, validation state,
and edit history where available.
_Avoid_: triple table, statement registry

**Workspace Edit Lock**:
The single user-facing switch that controls whether ordinary modeling changes can be applied in the
current workspace. It is a product safety control, not a user permission system.
_Avoid_: per-action permission, graph editability UI

**Debug and Settings Workspace**:
The user-facing operations area for edit lock control, projection rebuild/status, validation or
reasoning job controls, import/export settings, and runtime diagnostics. It does not expose raw RDF
graphs as editable objects.
_Avoid_: named graph registry, RDF admin console

**Technical Route**:
The Phase 0 decision stage that establishes the intended RDF-native foundation for the current
standardized semantic-language refactor version while keeping user-facing functionality small.
_Avoid_: throwaway stack, in-memory-only prototype, shipped version

**Direct Semantic Modeling Interface**:
The agent-facing or expert-facing input surface that accepts semantic modeling statements such as
TriG, Turtle, JSON-LD, SHACL, OWL, or constrained SPARQL Update as governed graph edits.
_Avoid_: CRUD API, raw write endpoint

**Agent SPARQL Query Interface**:
The agent-facing read surface that accepts SPARQL queries for flexible exploration of canonical
semantic data. It is separate from semantic write/edit interfaces.
_Avoid_: fixed CRUD API, semantic edit endpoint

**Constrained SPARQL Update**:
A SPARQL-based semantic write patch that is accepted only through the governed semantic edit
interface. It may express complex inserts/deletes, but it must still be validated, audited, and
checked against graph editability before commit.
_Avoid_: raw database write, query endpoint

**Structured Product API**:
The business-friendly input surface for ordinary workflows, such as creating classes, submitting
assertions, validating graph edits, and controlling graph editability.
_Avoid_: semantic core, canonical store
