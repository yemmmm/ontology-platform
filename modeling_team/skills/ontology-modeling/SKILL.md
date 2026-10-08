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

When expressing a confirmed rule or policy, preserve each operative condition, prohibition and
required response behavior. A related precaution is not a substitute for the complete obligation.
Before handing off a candidate, compare its modeled wording with the approved source; identify and
correct any lost qualifier rather than letting a Consumer infer it from a broad policy label.

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

Choose nodes, predicates, rules and any Class roles from the supported meaning and the loaded
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

### Report current progress (R4.0-014)

At candidate handoff and content-affecting revision, send Coordinator through the existing message
channel the slice/viewpoint, current complete candidate_id/revision/key item_id or approved path,
analyzed/expressed scope, remaining work/unknowns and next role/input. State what survives or is
invalidated from the old revision, preserving unrelated scope. Final handoff includes remaining
unknowns and work. Coordinator checks actual content and alone writes the shared map.

Partial current expression is modeled plus its limits; analysis without expression is pending,
or unknown if unresolved business facts block it. A correctly expressed necessary unknown may be
modeled but remains unconfirmed. not_applicable requires scoped business grounds, not missing
sources. Keep real business unknowns consistent in the candidate and map's explicit_unknowns;
ordinary unstarted work is a progress task, not an invented business unknown. Missing/unverified
artifacts, pending approval/application/acceptance and absent plans are progress/evidence gaps.
An unconfirmed proposal alone does not establish semantic ambiguity; identify an actual unresolved
business meaning before reporting it for explicit_unknowns. Do not infer business
confirmation, applied state, independent PASS or write permission from modeled. Use actual bound
execution results and original verdicts for those separate conclusions; never copy hidden material.

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

For R4.0-010, model the four neutral mapping item kinds (`table_mapping`, `join_mapping`,
`enum_meaning`, `metric_definition`) in either active candidate form. Include the complete
physical role, grain, key, path, encoding or metric context plus `mapping_definition`, and use
recursive `{definition_ref: item_id}` links. Use an explicit unknown for unsupported business
identity, cardinality, conversion or deduplication decisions. Do not copy database rows or put
IRIs, Batch/receipt fields, credentials or SQL in the candidate. Protocol owns the mapping
command order and the resource-kind governed binding; read the active R4 reference before each
full revision.

See [prompts.md](references/prompts.md) for a bounded semantic handoff and clarification pattern.

## Assess returned execution results

A candidate receipt proves only what that receipt states. Use Protocol's bound dry-run/application,
readback and governed-retrieval results to identify remaining semantic gaps.
Preserve source-supported business constraints as ordinary semantic knowledge; do not require
SHACL/OWL runs, specialized rule annotations, scripts or their receipts (R4.0-025).

Distinguish absent semantics from incomplete retrieval, a protocol rejection or infrastructure
failure. Return a concrete semantic correction when supported; otherwise preserve the exact blocker
for the responsible role. Retrieval completeness and the division of responsibilities are described
in [platform-flow.md](references/platform-flow.md).

Report your own artifacts, confirmed/unknown conclusions and unresolved findings through the
Task's handoff. The Delivery host owns start authorization and lifecycle; independent acceptance
owns the final semantic verdict. A role completion or mechanical check is not that verdict.

Do not invoke historical artifacts listed in
[deprecated-artifacts.md](references/deprecated-artifacts.md).

## Map external API descriptions

For R4.0-011 read the mounted `r4-0-011-api-mapping-contract.json` and its complete
`neutral_example`; the `interface_mapping` section of both authoring/role contracts applies
also to unified candidates. Use ordinary definitions and explicit edges, not a new platform kind.
A query interface can have no Class, Action or Operation. Keep system/interface/document versions,
request/response variants and stable field identities separate; use parent/member/element edges
for nested structures. Distinguish no body, unknown structure, missing, null and empty collection.

Bind fields to the specific business parameter/object position and call context. Do not equate
API IDs, business numbers or database keys; describe composite members and conversion direction.
Codes belong to a field and scope and may share business reference values with database mappings.
Preserve unknowns/conflicts, units, time zones and default/null meanings; do not execute conversions.

If using an Operation, reference the exact `(Operation, bindingId)` and read that binding's
location; never default to the first binding or keep a second authoritative location. Without
one, retain independent nonsecret location and scoped unknowns. Distinguish alternatives,
combination steps and partial capability; 004 owns ordering. A page is not all results, protocol
success is not business success, and async acceptance/task identity is not object completion.

Review affected references on field/code/result/binding changes; use distinct identities for
concurrent incompatible versions. Keep credentials, actual messages/runtime IDs and business rows
out of the model. Use governed entity/role/edge reads and controlled Operation projections;
incomplete retrieval does not prove absence. Static samples and fixture PASS do not establish
A10 real semantic acceptance, online availability or execution success.
