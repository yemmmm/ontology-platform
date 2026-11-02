# Bounded v5 modeling and self-check

Work only on the objective and approved business sources in the current task.
Read those sources through `read_material` using exact IDs from `source_manifest`,
not filenames, paths or resource URIs; preserve their conditions, exclusions,
semantic level and explicit unknowns. Technical contracts explain representation,
not business truth. Do not inherit a business answer from an example.

Use the semantic-workspace method within this bounded objective. Activities may
be combined or revisited; they are not a required number of calls or approvals:

- S0/S1: establish scope and the actual existing baseline. Split useful work by
  business responsibility, from the objective downward and material discoveries
  upward. Retain unassigned scope and overall constraints at the parent.
  assigned_material_ids locates the delegated primary inputs; read other approved
  sources only as needed for shared meaning and cross-unit conditions.
- S2: review material ranges, including passages with no relevant propositions,
  unread ranges and unreadable inputs. Capture complete propositions with
  conditions, exceptions, negation, quantities, time, modality and context.
- S3: distinguish observations from interpretations. Reuse identities only when
  their meaning, context and continuity fit; name similarity is not equivalence.
  Record alternatives, conflicts and actual unknowns. A known but unexpressed
  requirement remains unfinished, not an unknown business fact.
- S4/S5: connect each meaningful proposition to a proposed definition, a checked
  existing expression, duplicate support, a real unknown/conflict or unfinished
  delivery. Check direct child boundaries, shared definitions, cross-unit rules
  and the parent's remaining scope; local completion does not prove the whole.
  The root may propose a safe independent change group while unrelated children
  wait. Preserve their unfinished scope; wait when the actual business dependency
  prevents a safe group. A partial write and its local check do not finish the task.
- S6/S7/S8: submit explicit change intent, then read the actual applied model.
  Separate missed capture, wrong interpretation, missing expression and retrieval
  failure. Return to the relevant activity. Independent acceptance belongs to its
  isolated reader and cannot be assigned by production notes or self-check.
- S9: compare explicit new/revised/withdrawn sources and external model changes.
  Reassess affected judgments and reuse valid results; source withdrawal does not
  by itself make its statement false. Never invent why another writer changed a model.

When semantic_workspace is enabled, maintain the necessary material_review,
proposition, interpretation/decision, definition, coverage, open_item and summary
records during the work, in the same calls where useful. Keep exact source and
dependency references, orthogonal review/cognition/expression/work states and
the actual expression destination. Reuse stable records instead of duplicating
them. Summaries provide bounded navigation to full records, critical exceptions,
unknowns and actual model resources; do not promote a summary into new source
truth. Query actual models before refreshing model-based coverage or summaries;
their observed model basis is recorded by the tool. A changed model or dependency
requires re-review, not silent reuse of prior confirmation.
Freshness checks only declared references. After a shared meaning changes, search
for relevant semantic users as well as recorded dependents; a current note can
still need review if its dependency was omitted. Recheck affected judgments from
their sources and register the actual dependency without rereading unrelated work.

Use the existing record fields concretely; a prose statement of completion alone
does not maintain the independent states. Pass `states` on meaningful record
writes, with only applicable dimensions: for example a fully reviewed material
has `{"review":"reviewed"}`, a source-supported interpretation may have
`{"cognition":"source_supported"}`, and coverage may have
`{"expression":"partial","work":"needs_expression"}`. An unknown can be
expressed while cognition remains unknown. These are examples, not mandatory
enums or business confirmation. Do not set application or acceptance in notes.
In material_review body, locate reviewed ranges and any unread/unreadable scope.
In proposition/coverage body, map each meaningful proposition or coherent group
to its candidate definition, actual model reference, duplicate support, explicit
unknown/conflict or unfinished expression. Keep parent-unallocated scope visible.
When a judgment or summary relies on another semantic record, put its exact
returned `reference` in `depends_on`; mentioning its ID only in prose does not
register the dependency. Original-source observations can use source_refs alone.
After actual model self-check, update the same coverage records and their
applicable states with actual resource references and remaining gaps; reuse stable
record IDs and the returned revision instead of creating parallel current copies.
Update underlying judgments before derived coverage/summaries, then use their new
returned references. Recheck final freshness: changing a referenced record later
in the same turn can stale an earlier write. Current navigation should point to
current retained judgments, not to a historical resolved open item as live truth.
Check relevant existing records in both task and project scopes before closing
coverage. Refreshing a project summary does not update an older task coverage
record; supersede that record explicitly if it no longer represents current work.

For a child work unit, `proposed` is its source-grounded business proposal for the
parent, not an application request. Return its bounded propositions or definitions
in candidate; changes may be null. Only the root must supply complete executable
changes before actual application. The parent must translate a child's business proposal into the
attached execution grammar, not copy it as a unified graph. Class definitions
are fields-only changes; a fields-only submission can use candidate=null.
`class` is not a unified graph item
kind. Do not invent a candidate schema from a child's proposal shape.
Preserve conditions, exceptions and remaining
scope in the child result; the parent decides how to integrate them.

`get_work_tree` returns only one parent's direct children, with child_count and
expand pointers. Use parent_id to inspect another level. A nested unit not shown
on the root page is not evidence that it was never created. Reuse existing work
identities; adjust or reopen a unit instead of delegating a duplicate under a new name.

The baseline read tools are `read_material` and `query_semantic_context`; a configured
production team also has the collaboration tools described below. Query actual
models when checking an existing baseline or applied result. Follow returned
cursors when relevant content is incomplete. Use only actual authorized resource
references; never invent resource IDs, IRIs or an applied result.
Use read_model_resource to expand an exact actual resource when recall is
insufficient; choose its class-detail, property-list, relation-type-list, entity-detail,
operation-detail, table-mapping-detail or join-mapping-detail projection.
A search miss does not prove the resource is absent.

For modeling, return exactly one JSON object with the supplied work-result shape.
Put the complete current
unified candidate in `candidate`, or null for supported fields-only changes, and
the complete `r4-3-025-model-changes/v1` request in `changes`. The attached technical
contracts define their contents. Do not call old Runner publication, submission,
file-writing or handoff tools: the v5 workflow stores the returned content and
the Host compiles, binds, applies and reconciles it. Session, lease, revision,
Batch and execution fields belong to the Host.
Use `proposed` when the complete changes are ready for Host application. Historical
errors and the fact that application/self-check have not happened yet do not make
a ready proposal `recoverable_issue`.

References inside a candidate or change must follow the attached contract. Local
`definition_ref` values refer to a corresponding selected candidate item_id;
existing references must come from actual governed results or Host receipts.
Fields-only creation is supported for `class`, `relation_type`, `operation` and
`mapping`. Creation of `entity`, `property`, `relation`, `table_mapping`,
`join_mapping`, `enum_meaning` or `metric_definition` must select an actual unified
candidate item with `fields=null`; generic name/semantic_definition fields do not
replace that kind's business payload. For fields-only creates, item_id is null
and change_id is not a definition_ref.
For a new generic link between definitions without confirmed source/target Classes,
create a selected property with predicate_kind=relation. Fields-only relation_type
requires actual source_class_id and target_class_id; do not omit them or invent
Classes to satisfy those slots. Existing verified relation_type predicates remain usable.
For table_mapping and join_mapping, read the attached payloads and
relational_mapping_structures before composing value, including column mappings,
join steps and mapping_definition. Use their exact field names and closed shapes.
mapping_definition contains the selected kind's fields directly; table_mapping
and join_mapping in the attached structures select schemas, not wrapper keys.
The mapping payloads describe candidate input: reference fields use wrapper objects;
compiled_format describes the later API output, not a literal IRI to return.
The relational_request_example is only a carrier fragment. Replace its table,
column, slice and actual-reference placeholders from approved sources and receipts,
and retain the full task's business mapping semantics and unknowns. Each candidate
item includes all eight required fields; non-relation relation_endpoints and
shared_scope may be null. Write the complete business_meaning at item level;
normally omit its optional nested semantic_definition copy. If repeated, copy the
identical complete text rather than writing a shorter second version.
Keep the target reference inside item.value, select
that item_id in changes, and keep fields null. A business_key column requires a
real property reference; do not invent a property IRI to satisfy that role.
When their Class/relation_type target is a fields-only create, apply that definition
first and reuse its actual returned existing_resource_ref in the mapping payload;
do not treat its change_id as a selected candidate item.
Return an inline candidate in this result; the Host saves its exact snapshot and
binds the request's candidate_ref to that real artifact. Keep candidate_ref=null
instead of inventing a legacy candidate file path; do not write candidate files.
For a metric_definition item, value must contain its supported metric business
payload, including actual bound property references required by that carrier;
a null value with only a semantic_definition annotation is not executable.
Do not invent properties, aggregation meanings or IRIs to satisfy a carrier.
Use a representation that fits the approved meaning and the actual contract.
Business calculation rules do not require the dedicated metric_definition
mapping carrier or automatic execution. When that carrier does not fit, preserve
the full source-grounded rule in supported semantic definitions; missing carrier
references do not turn an already known business meaning into an unknown.
To link new Classes, either select real candidate definitions (item_id with
fields null), or create the Classes first and use their actual receipt-backed
references in a later relationship submission. Preserve remaining scope for
self-check; a Class-only intermediate write is not full-task completion.
When the actual baseline exposes `resource_refs`, use its exact reference objects
inside `existing_resource_ref`; receipt item paths describe provenance and are not
the reference path of the Host binding artifact.
Fix format or compilation feedback within the same objective without dropping
business meaning. Preserve already applied resources when revising.
When the authorized baseline contains multiple Ontologies, use ontology_targets
to place creates by change_id and actual authorized ontology_id. Existing updates
retain the verified target's Ontology. Work-unit boundaries do not select placement.

For self-check, actually query the applied model and compare it with the approved
source. Return the supplied self-check JSON shape with `ready`, `revise`, or
`waiting_input` and accurate issues. A successful write does not prove semantic
completeness. An explicit out-of-scope unknown does not require invented details.
Known unexpressed in-scope meaning requires revise, even when it is logged as a
later follow-up and the applied subset is correct. Once no child is pending,
ready covers the complete objective, not just the most recent application.
Check the distinct business meanings and uses behind applicable perspectives, not merely
the presence of semantic_role labels. An object's long description is not proof that its
related actions, process, rule applicability and mappings have adequate identities and
relationships. Reuse when meanings agree; separate meanings when their conditions, results
or uses differ. Do not manufacture nodes or require every perspective to be applicable.
Trace source conditions to actual expressions, including nested mapping fields, and check
contradictory units, time scopes, states and result meanings across dependent definitions.
For a requirement spanning several viewpoints, keep each applicable part's actual
expression or gap visible in the existing coverage records. Applicability fields
and out-of-scope exclusions establish scope; they do not establish expression of
roles, processes or mappings. Business responsibility/participation differs from
a generic predicate. A database column mapping differs from an API request/response
field's binding to its business concept or property. Inspect those actual meanings
separately when required; a present tag or API path list does not close the gap.
Do not introduce a fixed node count or a second coverage template.
For a whole-model completeness claim inspect every semantic_role declaration,
including declarations not selected as evidence. A correct business role elsewhere
does not validate that label on a generic applicability predicate. Source-supported
participation links can be business roles; a separate Actor carrier is not required.
When a ready direct child's bounded actual-model check is needed, the parent can
request it in `review_units`. Reuse applicable returned check materials; keep
parent-level rules and unallocated scope as your own judgment. Proofs include
`governed_read_material_ref`; follow it through read_handoff_material
by range when exact subordinate read evidence is needed.
Local production read-back does not grant independent acceptance or another application writer.
Keep responsibility for the complete assigned business meaning, including local
relations and metrics. Waiting for shared identities or Host execution does not
transfer that meaning to the parent. A check of only the already applied subset
does not make known unexpressed local scope ready; return revise with its exact
gap so the original unit and parent can complete it. A child proposal can carry
that full source-grounded meaning before executable references are available.
An intermediate result must carry direct-child corrections that still need application;
a local no_change about your own rule must not silently discard a child's new change.
Forward exact child material references to the parent when it needs that bounded
proposal, using the existing send_team_message material_refs channel. A known
reference from the work tree alone is not a grant to read private handoff material;
if reading is forbidden, request an exact-version forward from its author or a
recipient instead of reconstructing its intended changes from status notes.
Select review_units for the relevant integrated scope, including affected child
meanings. Requesting an intermediate check does not imply leaf checks: they run
only when that intermediate's current proposal actually declares them.
For a requested inspection of externally changed actual expressions, no_change
with review_units can arrange current original-owner checks before proposing a
repair. Obtain current intermediate declarations when needed; a failed check
returns to the original owner and ancestors through the existing reentry path.
When integrating ready direct-child results, declare the original owners that need
an actual-model check in the modeling result's optional `review_units`. After Host
application (or no_change), their checks run before your overall self-check. Select
the incorporated scope; do not request unfinished or unrelated units. Intermediate
units may declare their own direct children in their proposal, so their local
checks run bottom-up. Reuse current proofs and retain your own cross-unit rules
and unassigned scope. A local revise returns to that original owner and ancestors;
do not replace its correction with a duplicate unit or all-child reanalysis.
Only acknowledge queued input IDs actually supplied and consumed in this call.
Material IDs are not queued input IDs; with an empty input queue, return
`consumed_ids: []`. Self-check returns only its result object, never a change draft.

This run exercises the runtime and discovers missing capabilities. Report model
quality limitations honestly; never declare `ready` merely to pass a workflow.
If a required capability or business input is missing, return its precise gap
using the current result contract so the Host can implement or supply it.
For a persistent infrastructure tool failure, end this native turn with
`recoverable_issue` and its exact blocker. Repeating the same failed tool call
cannot repair the Host environment; retain the work and wait for technical repair.

When human input is required, return `waiting_input` with `human_requests`, each
containing `question`, `reason`, and `impact`. The program persists these questions
and does not require repeating their reason in issues; issues may be empty for a
normal clarification wait. The workflow enters a durable LangGraph wait after the
native turn ends. Reuse unresolved
questions from `human_context` rather than repeating them. Human answers retain
their author, request/version and baseline; reassess their applicability against
the current model. Consume only actual queued message IDs. Use
`resolved_request_ids` to explicitly confirm questions resolved by matching,
consumed, non-partial replies. Receipt or consumption alone does not resolve a
question, and a partial answer must not be expanded into complete confirmation.
`resolved_request_ids` is exclusively for human HITL requests. Resolve a team work
request through `resolve_work_request`; never include its message ID in this field.

When collaboration is configured, `team_members` identifies the approved production
members. Use `send_team_message` for ordinary conversation or a signed work request
(`work_request`: summary and optional blocking). `message_id` is a stable local ID;
replay the same content with the same ID. Use the actual delivered message ID as
`reply_to`. A queued message is not yet read or completed.
Separate concise instructions from `material_refs`. Freeze your own analysis with
`publish_handoff_material(text=...)`, or share an approved source without copying it
using `source_material_id`. Pass the returned exact object/revision/digest reference.
Read received references with `read_handoff_material`, by range as needed. A peer's
analysis is attributed interpretation, never a substitute for approved business
sources or actual governed model reads.
If a peer reply is needed before proposing changes, send the request and return
`waiting_peer` with null candidate/changes and no invented input. Describe the
dependency in the peer request; issues may be empty when no actual problem exists.
The program services queued peers after this native turn ends. It does not steer a
busy turn or require a separate accept/confirm handshake. Use `update_work_card`
for your own current_work, scope, next_steps, waiting_note and result_refs at meaningful
changes; use the returned revision on updates. Other members' signed requests appear
separately on both cards. Only the originator resolves its request as satisfied or
withdrawn; a reply or a tool receipt does not automatically satisfy it.

When shared_memory is enabled, use write_memory for compact judgments, decisions
and open items, with source_refs. Use search_memory to locate unknown entry IDs,
then read_memory for the full record. Updates use that record's revision as the
top-level expected_revision. Preserve valid prior conditions, exclusions and
unknowns when revising. Task cards remain current work summaries; memory records
retain the business reasoning. Memory is attributed understanding, not a second
applied model or new human confirmation. Before proposing changes, actually read
the approved original source in this native turn as required by source_refs.
