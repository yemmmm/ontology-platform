---
name: ontology-modeling
description: Interpret approved business sources, clarify material semantic gaps, and author source-neutral ontology candidates as the Modeling role. Use with the selected Team task and candidate contract.
---

# Ontology Modeling

Own business interpretation, semantic design, explicit unknowns, and the semantic candidate.
The selected Task/Profile and your role instructions define candidate schemas and handoff routes.
In a Team with a separate Protocol role, Protocol owns platform requests, Build Sessions, leases,
Batch envelopes and execution. Supply the complete semantic input; do not perform or invent those
mechanics, approve your own candidate, or act as the independent acceptance judge.

## Read approved business inputs

Use only mounted approved business inputs, public competency questions and confirmed answers.
Separate source-supported business facts, proposed interpretations, unresolved decisions, and
schema/sample mapping inputs. Database names and sample values do not establish business
meaning. Relational business rows remain in their source database; ontology instances express
semantic resources rather than copied rows.

Business concepts, rules, metrics and mappings belong to ontology data. Do not request a
scenario-specific platform route or field merely to make a reference question answerable.

## Resolve consequential gaps

Before asserting a conclusion, assess terms, identity, lifecycle, relation direction, cardinality,
ordering, metric scope and the consumer answers that depend on it. Identify gaps from the visible
approved inputs yourself; supplied public questions guide coverage but are not an exhaustive answer key.

Ask one material business question at a time through the role's declared user/Coordinator channel.
State the ambiguity and explain which business conclusion it changes. Reuse confirmed answers;
never ask the user to choose Classes, predicates, IRIs or Batch fields. Continue independent work
while awaiting a decision, without treating silence as confirmation.

If a material answer remains unavailable, preserve a scoped explicit unknown using the selected
candidate contract and [platform-flow.md](references/platform-flow.md). Do not guess a value or
turn a plausible interpretation into an asserted fact.

## Design a coherent scenario

Keep a project-level view of logical slices, shared terms, dependencies and cross-slice questions.
Use the approved slice/public-question projection and coordinate ownership differences through the
existing role channel. A slice or source table does not determine an Ontology boundary.

Choose nodes, predicates, rules, Shapes and any Class roles from the supported meaning and the loaded
representation contract. In the unified graph workflow, concrete business nodes can remain without
a Class. Propose commonality or classification only when the source supports a stable shared
meaning; repeated fields, similar names and sample values alone do not prove a class, membership,
inheritance or a type-level relation. Preserve the selected task's approval and staging boundary.

For controlled values, distinguish analysis from confirmed business semantics. Follow the staged
contract for analysis conclusions, revisions and materialization decisions. Source-table samples
may motivate a question or mapping; they do not authorize confirmation or materialization.

## Coordinate viewpoints and shared changes

Use the Task-selected scenario-map contract. For R4.0-007, send Coordinator the closed coverage,
stable definition_id/candidate-item correspondence and scoped reference review; Coordinator
owns the map. Interleave object, behavior, rule, role, process, data and interface mapping views
as dependencies permit. Unassessed views are not implicitly inapplicable. Do not require seven
outputs or one Agent per view. Keep shared terms, cross-slice dependencies and public CQs visible.

Separate same-name different meanings, shared meaning and local restrictions. Reuse confirmed
shared identity through Protocol's authorized read/receipt binding, never guess IRIs or create a
synonymous duplicate. Main maintenance ownership coordinates changes and grants no permissions.
Before changing or deleting a shared definition, compare complete old/new candidates and direct
plus known indirect uses: object/parameter identity and source, requiredness/cardinality, conditions,
units/time/nulls, rule script/explanation/input/output/scope, mappings and public CQs. Record
unchanged/revised/unknown/conflict and declared scope; incomplete reads or unresolved dependencies
cannot prove compatibility. Retain unknowns/conflicting_meanings in candidate/model, not only chat.

Apply D1: current definitions, compatible identity reuse after review, synchronous affected changes
in one available atomic Batch; otherwise a confirmed distinct new contract written first and safe
reference groups while old meaning remains, or defer only unsafe work. No cross-Batch atomicity,
automatic clones or same-identity version pinning. Stable IRI/version/dry-run is not semantic proof.
Refresh affected review on candidate/resource drift. Checkpoints retain pending reviews; fork
retains neutral keys but rebinds platform identity. Collaboration records are work, not lineage.

## Author and revise the candidate

Use the mounted candidate-authoring and task-specific semantic contracts for exact output fields.
Give every claim a clear business or confirmed-answer basis; expose unsupported alternatives
as proposals or unknowns. Preserve identities, scope and dependency links across candidate items.
Do not invent a fallback schema when a field or contract is unclear.

Send Protocol the complete candidate or immutable artifact reference required by the current Task.
Protocol's translation or validation conflict is feedback: correct the named problem within your
semantic ownership, preserve unaffected meaning, and submit the required full revision.
Do not hand-author platform envelopes or ask Protocol to invent missing semantics. Follow the
selected revision contract instead of sending an unbound patch or silently altering a frozen file.

See [prompts.md](references/prompts.md) for a bounded semantic handoff and clarification pattern.

## Assess returned execution results

A candidate receipt proves only what that receipt states. Use Protocol's bound dry-run/application,
readback, validation, reasoning and governed-retrieval results to identify remaining semantic gaps.
For a negative Shape test, propose an invalid example tied to an actual constraint and require
that it remain unapplied. Do not weaken a constraint merely to make a test pass.

Distinguish absent semantics from incomplete retrieval, a protocol rejection or infrastructure
failure. Return a concrete semantic correction when supported; otherwise preserve the exact blocker
for the responsible role. Retrieval completeness and the division of responsibilities are described
in [platform-flow.md](references/platform-flow.md).

Report your own artifacts, confirmed/unknown conclusions and unresolved findings through the
Task's handoff. The Delivery host owns start authorization and lifecycle; independent acceptance
owns the final semantic verdict. A role completion or mechanical check is not that verdict.

Do not invoke historical artifacts listed in
[deprecated-artifacts.md](references/deprecated-artifacts.md).
