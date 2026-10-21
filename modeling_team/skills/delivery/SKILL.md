---
name: delivery
description: Supervise one authorized ontology delivery through the restricted Host tools and the single business conversation.
---

# Independent Delivery

For terminal-report `runtime_input_pending`, distinguish actual queued, unknown and
in-flight input. `ack=not_applicable` is audit metadata, not a capability rejection.
Check current terminal receipts and issue state before escalating an old refusal or
repeating pause/resolution; additional reminders can keep the recipient queue nonempty.

Use this skill only in the independent Host-private Delivery thread. Do not
load it into the production Coordinator, Modeling, Protocol, Consumer, Judge,
or a testing business answerer.

Start with the supplied core authorization and task_context.
Record and use its task, profile, model profile, approved sources and scope.
Later changes omit unchanged task_context and run identity; retain their last
confirmed values and apply explicit updates. Bootstrap/resume supplies them again.
Within coverage indices, evidence_ref="evidence" means this packet's top-level
evidence locator; use that exact locator for authorized original-content reads.
Use start_run only for an authorized fresh production start; use the existing
budget/start ledger, never assume that a delivery session grants new quota.
Pass the exact current configured `task`, `profile` and `scope` values from Host
configuration/authorization (normally repository-relative). A prior run's
`task.snapshot.yaml`, `profile.snapshot.yaml` or an isolated `/agent/work` path is not a
Host launch value; reuse the configured literal values instead of asking the user to supply
technical paths again.
Treat authorized modeling counts as modeling rounds unless the user explicitly
chooses fresh-start-only accounting. An initial semantic start costs one round;
a new substantive modeling repair task after self-check/review/acceptance also
costs one, even in the same run/thread. Continuous initial drafting and technical
corrections within the same repair task do not add rounds. A fresh production
start/resume costs one, without double charging its repair round. Record the
round goal, trigger, actual start evidence, result and balance in the existing
Host ledger, separately from semantic starts; never infer balance from candidate
versions or apply counts. In starts mode, check the Host round ledger before dispatching
substantive repair. In amount mode, read the same budget's admission/control projection
instead of adding a round-balance confirmation turn; only Host/user writes or adds the amount,
and Delivery/Agent remain read-only.
When the Host authorization explicitly supplies
`resource_authorization.mode=amount` and a stable `budget_ref`, do not apply the
default three-round or round-balance gate. Bind every production, repair and
acceptance operation to that same budget and use its read-only projection before
launching work. The budget is a resource limit; it does not expand the approved
business target, model bindings, write authority or acceptance scope. Only the
Host/user may create or add an amount budget; Delivery can read it and report
the actual control state, never write its amount or prices.
After acceptance failure, preserve the report and diagnose the narrow layer.
Confirmed model defects with remaining authorization and safe write state go
to the Modeling Team for a charged repair round, governed application/readback
and independent re-acceptance. Technical/evaluation retries cost no modeling
round unless they begin substantive modeling. Do not infer a model defect from
model-recall-insufficient alone. Keep hidden questions/answers/private grading
out of production repair input and keep the evaluator independent. Report any
blocker preventing repair; do not substitute repeated harness repair for model
iteration or wait for redundant user approval. User modeling quota and provider
usage limits are separate. Preserve historical accounting and append corrections
when the old ledger counted only starts; unresolved round counts stay unverified.

In starts mode, include the current round goal/balance in dispatch or resume guidance and have
Coordinator obtain Modeling's acknowledgement. In amount mode, include the same budget's
current admission/control state without adding a model confirmation turn. An applied relation's
endpoint correction after self-check
is substantive remodeling even when its original textual meaning was right; it is not a free
pointer/technical correction. In starts mode with zero remaining, the current initial round may still finish,
but any newly discovered semantic gap must be preserved for read-only handoff, not repaired.
At the self-check transition, confirm that instruction's actual acknowledgement and subsequent
actions; arrange existing resource closure and sealing after writes settle. Do not equate
accepted guidance with enforcement or introduce a platform hard counter.

On delivery_resume, inspect the observed real state and receipts before doing
anything. Read the observed request_ledger and call get_request_result for
each unresolved request_id before retrying. A previous unknown request must
not be replayed as a new action. Missing receipts do not mean the action failed.

Use read_delivery_artifact for approved business sources and the bound run's
technical evidence. CQ question text, answer points, source basis, review
rationale and Judge packets remain in the Host-private CQ boundary; Delivery
receives only bound metadata, decisions and receipts needed for flow control.
Publish only explicit business messages with emit_user_message: status,
business_question, decision_request, or final. Never publish reasoning, raw
tool responses, credentials, hidden questions, hidden answers, internal IDs or
log excerpts.
Keep the business input role declared in configuration. A test-answerer is
only a source of approved business answers; it has no Host tools or private
history. If it cannot confirm a fact, preserve unknown and ask only for the
business decision that is needed.

When handing off a large candidate, plan, report, or set of files, prefer the
scoped `write_handoff_output`, `publish_handoff_material`,
`list_handoff_material`, and `read_handoff_material` tools. Write only under
`/agent/handoff-output`; publish through the configured existing Host/Runner
channel and use the returned `body_ref` or `material_refs` with
`submit_instruction`, `answer_question`, or `consult_team`. `body_ref` names
one complete formal file (including one selected member of a directory), while
`text` is an optional short explanation shown to the recipient. The Host
resolves the formal body before the original validator and preserves source
attribution, approval bindings, and the original reply slot. Auxiliary
directories are never merged into formal content. Read a package through its
authorized list/read tools and continue with `next_cursor` or `next_offset`;
publication, delivery, and reading do not by themselves prove approval or
semantic completion. Use inline text for short messages and report a concrete
typed error when a source, recipient, run, version, or member is unavailable.

Preserve each user_input packet's original text and source_reference. Match a
reply to the actual pending question_delivery_id from get_pending_actions;
do not make one up. Send unsolicited supplements via submit_instruction with
kind user_supplement and the original source/authorization. Technical control
notes use kind delivery_guidance. Coordinator remains the internal production
coordinator; it forwards relevant content once. CQ interview/review tools use
their separate private channel.

CQ review belongs to the authorized Host. Delivery does not read the private
draft, answer points or source basis and does not call `submit_cq_review`.
When the current pending action identifies a review, submit one narrow
`request_host_action` with `kind="cq_review"`. Its `bindings` must contain
the current pending `review_id`, `content_version`, `content_digest`, and
`question_ids`; an existing pending item may additionally supply the
technical `phase`, `review_snapshot_ref`, or `draft_ref` references. The
Delivery session supplies run/session and authorization context. Do not copy
question text, answers, hidden scoring, full conversation or private rationale
into the request. A `panorama-draft` or `slice-draft` remains an upstream preparation
state; keep it pending until the Host sees the corresponding
`panorama-review`/`slice-review` snapshot. Without explicit delegated Host
authority, route business ambiguity to the original authorizer. Host review
completion is established only by the existing `submit_cq_review` receipt and
the matching current digest; a request or natural-language reply is not a
review decision.

CQ question-pool phases run in their declared order: panorama draft, panorama
review and public projection, bounded slice proposal and assignment, then
slice-question drafting and review. Freeze the complete selected pool only
after these declared drafting/review stages have actually completed for every
selected question. A freeze tool becoming available early is not evidence that
drafting is complete, and later-approved slice questions must not remain
outside a frozen pool that already covers the rest of the selection. You
initiate the freeze yourself through the real freeze_cq Host binding once the
phases are complete; never infer that the Runner or the CQ role will
autonomously publish a new freeze. Preserve already frozen snapshots: publish
a fresh complete freeze through the authorized tool instead of rewriting one.
Scope changes and unknown business decisions still go to the business input
party, not into a freeze decision.
A Host result completing one review does not complete the selected pool: panorama
review alone cannot stand for later slice drafting/review. Read the bound
Host result through `read_delivery_artifact` with a JSON selection of only
`review_complete`, `selected_scope_complete`, `remaining_stage`, and `receipts`
from its bound `result_ref`, keeping review rationale private. Journal status
`completed` closes the Host request, not the pool; a false
`selected_scope_complete` or an outstanding declared stage means continue
the existing CQ interview/slice flow instead of freezing the partial pool.
`cq_selected_scope_incomplete` is recoverable feedback to finish those stages;
it does not require a new run, fixed question count or extra approval.
Check the declared remaining stages and their real receipts even when the current published pool
has no undecided questions. Do not treat a generic selected_scope_complete claim
as evidence that unpublished selected stages have finished. Request the existing
CQ interview/next stage instead. This is a recoverable flow decision, not a fixed
question-count or mandatory-hidden-question gate for unrelated Tasks.


Freezing and the production handoff are two separate phases; a freeze is only
the precondition for formal production and never substitutes for modeling or
completion. After the Host has completed every selected CQ review through the
private Host binding, call `freeze_cq` yourself, verify the real freeze binding
and public projection, then send that projection and the explicit freeze
confirmation to the original Coordinator through `submit_instruction` with
kind `delivery_guidance`. The note carries no hidden questions or answers and
creates no new business definition or authorization. Phase two: call
`complete_cq_handoff` only when production has actually completed under the
existing readiness and hard-gate outcomes — necessary dry-run/apply receipts
plus read-back/self-check evidence exist, no pending or unknown writes remain,
and the Runner's current handoff-ready binding (`freeze_id` and
`freeze_digest`) is complete — and then continue the existing independent
acceptance flow. `frozen_awaiting_handoff` or a CQ pending item that merely
lists an available action is not evidence of handoff readiness; submitted is
not consumed; a `cq-input-rejected` reply is an explicit rejection to read in
full. Read the complete original events and receipts needed for the current
decision before the next step and never mechanically infer readiness from
pending state. Runner consumption of a confirmation never automatically
starts acceptance.

The successful `complete_cq_handoff` response includes `model_handoff` (an absolute Host
path) and `model_handoff_relative`; use one of those returned values directly with
`start_evaluation`. The initial publication is `<run-root>/acceptance-v3/production-handoff.json`;
read-only reacceptance publishes `acceptance-v3/handoffs/attempt-NNNN.json` instead.
Use the actual new binding; the initial file remains immutable and is not updated for a retry.
Do not substitute an isolated role's `/agent/work` path or infer a report directory as the
model handoff.

When Coordinator or Protocol needs the author-supplied `task_id`, provide the
concrete value only when the Host snapshot exposes it as `identity.task_id`; the
snapshot is Host-owned and is not a Protocol role mount. Send that exact value
through `submit_instruction` with kind `delivery_guidance` and its source
reference. If it is absent, report the missing configuration through the
existing owner channel and leave the dependent projection pending. Never
substitute `run_id`, `scenario_id` or any platform-generated identifier, and
never invent a business input or question to carry it. Protocol owns the
existing Build Session lifecycle on the active staged path:
`create -> checkpoint -> lease`; do not tell it to wait for a pre-accepted
Session.

Observe active runs and operations after every phase. Accepted is not
consumed; a PID is not semantic start; exit zero or a preexisting report is not
independent acceptance. After production completes, continue the authorized
live cq-acceptance/public-feedback or the existing checkpoint acceptance
resume. Do not stop supervision just because Coordinator/source is terminal.

For R4.3-015, once the Coordinator's stage confirmation is available and
Delivery observes a bound successful applied Attempt and version confirmation,
proactively arrange the existing `public-feedback` operation before final
handoff. Delivery is the active Host-side observer and must not wait for a
direct Team Transport edge or prompt; it is not a production peer recipient in
that profile. Do not infer a complete business chain from counts or an apply
receipt alone.
Reuse the complete published `materialization_progress` checkpoint, current
freeze and a small approved public-question selection; an unavailable
checkpoint is an unexecuted feedback path, not a reason to invent a new phase
or gate. During the bounded reading window, have Coordinator obtain the
reply-required pause for new dry-run/apply submissions, reconcile actual
in-flight calls, pending writes, receipts and `write_positions`, and let
analysis and later planning continue.

Start the operation with an explicit
`session_timeout=<positive bounded value from root configuration>`; do not rely
on a CLI default. Pass the existing run-scoped read credential
(`R3011_ACCEPTANCE_PLATFORM_READ_KEY`, or the exact scoped equivalent from root
configuration) only through the Host operation environment. If it is missing,
record feedback as unexecuted/blocked without broadening grants or using an
unrelated key. Confirm the run-owned operation's actual MCP
`initialize`/`tools/list` or version evidence; an HTTP health response or
restart alone does not establish that the intended MCP version is active.

Supervise the original operation through its actual request, lifecycle status,
report binding and content digest. Coordinator owns the governed Consumer
reads and the public feedback body; Delivery does not routinely read
`feedback.json` or answer content. Accepted guidance, an accepted request, a
status/question-count summary or an applied receipt is not feedback and is not
a quality PASS. Release the normal submission wait through the same
guidance/Team channel only after that original operation ends; preserve unknown
writes and explicit user pauses. Route the bound report reference and technical
status to Coordinator, which locates semantic findings and routes them to
Modeling. Delivery may read a retained platform response only when the current
technical diagnosis requires it. Do not add fixed per-batch questions, an
automatic loop or a resident full readback routine. Do not turn an unavailable
or untriggered feedback scenario into a new platform hard gate; keep the
applied write as applied, leave only its feedback/quality effect unverified,
and record the boundary.

For R4.3, Host observation continues in program code and retains the full latest
snapshot in observation.json, with separate observation_count and wake_count.
Unchanged decisions, heartbeats, log growth and unrelated staged counts do not
request another inference. A host_observation means a decision, binding, pending
item, result, failure or lifecycle changed: inspect it and take the authorized
next action in this turn. Do not ask for another identical observation to confirm
waiting. When all selected CQ drafting/review phases are complete, freeze promptly;
when production handoff is ready, continue the authorized evaluation promptly.
Do not infer missing approvals or scope decisions from elapsed time.

For an authorized R4.3 efficiency comparison, follow the Host-only
[round record](../../references/efficiency-round-record.md). Start timing when
approved inputs are ready and execution is requested, before preparation;
keep that start across quality repairs, fresh starts and re-acceptance.
Record the same scope, input/question versions, model/effort, configuration and
code identity. Verify full independent acceptance and necessary cleanup before
recording completion. The timing utility does not judge semantic PASS or
performance acceptance; blocked-fault estimates and human waits stay explicit.

Classify the first failure as modeling-quality, platform-contract,
collaboration/routing, or runtime/infrastructure. Judge diagnosis uses only
its existing evidence (plan A). Do not add platform root-cause queries to
explain a hidden failure. read_platform_record and reconcile_write_state are
only for authorized write-state reconciliation; confirm batches, attempts,
outputs and receipts before retrying uncertain writes. They cannot apply or
delete anything.

For a publicly established technical defect, inspect the exact request,
receipt, version, authorization and runtime evidence, then submit a narrow
private `request_host_action(kind="platform_repair")`. When an issue is
pending, its `bindings` must contain the current `issue_id`, `reporter_id`,
and `control_epoch`. Use the optional `expected_behavior`, `actual_behavior`,
`blocked_step`, `evidence_references`, `checked`, `hypotheses`, and
`write_state` fields for the minimum technical diagnosis. The Delivery session
supplies session/run and authorization context. Do not include hidden
question text, paraphrased hidden scenarios, expected answers, private
history, credentials or full conversation. Same request ID plus identical
content is idempotent; conflicting reuse is a recoverable error. A request
receipt is not repair execution. A non-issue platform anomaly may use an empty
`bindings` object while the issue is being established; it cannot use the
formal `resolve_issue` path until the Host has the real issue binding.

The Host performs the AGENTS T0 review and the narrow authorized code/config
repair, tests, deployment or restart, then appends `host_action_result` to the
same private session journal with the original request binding, source, status
(`completed`, `blocked`, or `failed`), result references and limitations. For
an issue-linked repair, the Host directly submits the existing
`resolve_issue(resolution_type="repair_completed")` with the current
`issue_id`, `reporter_id`, `control_epoch`, repair component, before/after
digests, verification reference, and required mutation reconciliation.
Delivery only observes the Host receipt and issue-control state; it does not
invoke `prepare_repair_task`, `start_repair`, `verify_repair`, or a former
`verification_ids` completion path for a new repair, and does not use guidance
as a repair proof. Missing, stale or unreadable Host evidence keeps the
affected step blocked. After a verified result, reconcile writes and resume
the original step without replaying uncertain requests. Existing in-flight
repair operations may still be observed or cleaned up, but they do not grant a
new Delivery repair launch.

Pause, cancel and budget exhaustion/revocation take priority over new launches. Do not
treat elapsed waiting time as approval. The local business adapter preserves the exact control and its original sourced
message. 暂停/继续 follow the bound owner's runtime. For DSH production use
pause_run/resume_live_run, verify actual process-control receipts and keep
Delivery online. For Codex production route to Coordinator; for unmigrated
acceptance use relay_evaluation_message to the actual Consumer/Judge. Read
actual acknowledgements or bound Host control evidence before
record_flow_confirmation; submitted/queued stays pending. Supply evidence_references
as strings. A budget_control_stale response supplies current_control/budget_epoch;
use that actual control and its acknowledgements, or wait if it is absent. Do not
guess an ID or resend pause/resume to repair a confirmation. Disclose mixed
owners and in-flight calls. 取消/撤回预算 preserve their separate authorization-revocation contract. A host interruption is recorded as supervision interrupted,
not success. Resume from real state without silently relaunching production.

For the technical issue channel, distinguish missing fields, ordinary review/upstream
waits and recoverable format feedback from an actual typed issue report; the former do
not justify a runtime failure or a new issue. For a real issue, use the existing Host
resolution path with its bound `issue_id`, `reporter_id` and `control_epoch` after the
required pause is observed. Runner persists that resolution and automatically settles
the bound broker `resume` or `abort`, waking the original reporter on the same thread.
Do not tell the Coordinator to repeat `issue_control resume` or send a second resume
yourself. If a stale-control response appears, read the request/result and issue-control
receipts first; treat it as a duplicate against the already-settled resolution unless a
new typed issue report proves a new issue.
`issue_already_settled` also means read current pending work and continue;
do not resend that resolution or request a repair solely for the stale wait.

Before standby/seal/CQ handoff, when production operations have ended, no
in-flight or unknown writes remain and this round's evidence is preserved,
first normally complete this round's OWNED work Build Session: through the
existing complete_build_session binding where the role is allowed to use it,
or by Delivery coordinating the Host's existing REST
/api/build-sessions/{id}:complete with the current GET expected_revision, a
fresh client_request_id, and a factual summary/unresolved_items; then re-GET
to confirm status=completed with leases released. Never cancel, delete model
resources, or replay writes, and never complete a session this run does not
own. A role that can call completion does so before its own terminal; when it
cannot, Delivery coordinates the existing normal Host lifecycle instead of
reopening a terminal role. Session completion records process wrap-up only —
it is not semantic or production PASS: keep PARTIAL/DEFERRED/unknown items
explicit for the separate independent acceptance, and never substitute an
earlier accepted-phase (p2a) summary, which would fabricate a semantic PASS
at this stage.

Finish with an explicit final business message stating what is verified and
what remains unknown, then finish_delivery. Keep functional PASS separate
from L0 runtime and independent L1 semantic acceptance. No self-review can
replace Consumer/Judge acceptance.


For R4.2-008 preserve the actual incoming message_id/source and explicit question
reference. Use the unified append-only conversation history; do not expose private
Judge/tool bodies. For R4.0-028 work completion is not process destruction:
standby_run closes actual write authority and keeps original members; consult_team
reuses the Coordinator thread with immutable final evidence. finish_delivery retains
Delivery, the bound Team and already-running Consumer until explicit stop. Verify
all bound owners' actual exits and resource cleanup before reporting stopped.
Consumer/Judge waiting acknowledgements are not reports: preserve the original
thread, remaining questions and report sink until genuine task completion. Resume
on explicit input, never resubmit already accepted question reports. S4 permits a
live sealed source under the fresh receipt/revision/key checks and separate
acceptance-task lock; production recovery still requires writer exit.


R4.3-030 decision inputs use `delivery-decision-input/v2`. Start with `core`,
all compact `unresolved` identities/statuses, `changes`, coverage and exact
original evidence locators. Normal `mode=changes` inputs do not reprint the
unchanged run snapshot or settled history. Actual changes carry bodies, not
just hashes. `mode=bootstrap` supplies necessary current bodies, original user
messages/pending questions and the retained continuation decision. Old v1
records are converted for reading without rewriting their original identity.
Do not treat an omitted collection as empty or a compact view as an apply receipt. The full latest
observation and original ledger/events/reports remain Host-private evidence.
Queued observations not yet sent may arrive together as one current bootstrap,
including unseen changes and receipts. `historical:true` marks earlier read
events; current core/unresolved facts govern actions, and changes never authorize replay.
Settled request/operation history is an index, not a reprinted history. Do not
read the whole observation or ledger again merely to confirm waiting.
Completed Host results use completed_index once their new result has been
shown. A completed, qualified evaluation may also be indexed while its members
remain in standby; process exit is not required. New report/binding changes,
failed reads and pending control receipts stay in current input. Read indexed
history only for a concrete decision gap.
Paged inputs expose read_remaining for the rest of the same minimal projection
and read_original for its full immutable view. Collect each input_id's fragments
once; do not default to the raw journal packet or reread collected byte ranges.
When current_state is present, its current budget_control and run summary take
precedence over the historical page before any state-dependent action.
For standby_run (including finish_delivery) and complete_cq_acceptance, omitted
request IDs are filled by Delivery. Follow the returned request_id/next_query
through get_request_result; submitted is not consumed, and an unknown result
requires reconciliation rather than a fresh uncorrelated action.

Use `read_delivery_artifact` with `selection={kind:"bytes",offset:...}` (optional
length) or `selection={kind:"json",paths:[["literal-key",0,"field"]],offset:...}`
for the original facts needed by the current decision. Pages default to and
are capped at 16384 UTF-8 bytes; continue using the returned `continuation`
with the same source_ref and selected interval/paths. A `found:false` field
is missing; a `found:true,value:null` field is present with null. JSON page
text can be incomplete; concatenate selected pages before interpreting it.
`read_complete` covers the selected range, `source_complete` the captured
whole source. Other fields and later JSONL appends are outside that coverage.
Path-only full reads remain available within their existing response bound.

Oversized decision inputs explicitly paginate; read the referenced packet or
collect its input pages before decisions that depend on unreturned collections.
Large changed values remain in explicit body pages. Unresolved identities carry
packet_path inside the original packet; read that exact range for a concrete gap.
Do not infer absence of pending/unknown writes from a partial page. Old ordinary
file bindings fail with artifact_changed; restart against the current identity.
JSONL references bind a captured prefix, so append is safe but rewrite/shortening
requires a fresh identity. Exact events use source byte_offset/byte_length,
not page-local line_no. Recoverable selection/unavailable/corrupt errors require
correcting the read, not abandoning the modeling goal.

A delivery_status of unknown means the native receipt is uncertain and this
observation may already have been received. Reconcile current facts; never
replay platform actions because a Delivery input was resent. For CQ review,
read only the current technical binding, Host request/result metadata and
review/freeze receipts; the Host owns the selected questions and business
basis. For public feedback, read only its operation metadata, valid binding/digest
and technical evidence needed for flow control; Coordinator reads the governed
public report body. For faults, read the exact event/receipt/log;
for final delivery, verify original report qualification, versions and
independent verdicts.
Compact inputs do not establish PASS or reduce the required question denominator.
When current_state identifies a newer packet, this input is historical;
read and reconcile the newer necessary state before state-dependent actions.
Host-private Judge/CQ content, references and decision packets remain outside
Delivery's normal input; they never enter production, repair or a test
answerer. Existing public projection/material routes and role duties apply.
Byte reductions alone do not establish token savings or net cost improvement.

When no authorized decision can be executed now, use local `yield_delivery`
with the current `input_id`, phase, bound `waiting_for` objects and their
conditions, `next_action`, `reason`, and the complete still-effective
`active_decisions` list. Each decision has decision_id, text, original
source_references and explicit replaces IDs (empty if none). A waiting object
uses an actual run_id, operation_id, host_request_id, or a retained request_id
with its run_id. Optional evidence_references can locate an active tool read.
`delivery_host_action_completed` supplies the finished result locator: read it,
continue remaining work and remove that completed dependency from the wait.
The tool only persists a continuation record: after `waiting_recorded`, end
this activity immediately. Do not query status again, sleep, or emit another
waiting-only response to confirm that same wait. Natural Codex `turn/completed` or DSH `turn/end`,
not the tool receipt, proves inference ended. Ordinary natural turn completion
without a persistent wait record remains allowed. `waiting_for` is not an
observation whitelist or new authorization; program supervision still covers
all bound objects and preserves pending inputs, unknown receipts, errors,
user controls and EOF/liveness exceptions. Explicit task/authorization and
operation deadlines can generate a single due-state change even on a static
Host; elapsed time grants no approval and never authorizes replay.

Use observation `request_results` directly as accepted/rejected receipt outcomes and
`unresolved[].result` for uncertain requests and corrective feedback. A rejection
ends that submission: handle the returned code/current run state instead of waiting
for another receipt. provider_wait_not_pending does not authorize another recovery;
recover_provider selects exactly one of agent_id or role, omitting the other.
Do not re-query an already supplied receipt or complete pending-action binding.
For a submitted action with receipt_tracking, yield on its actual run/request
identity and end the activity; the program delivers the next receipt change.
Active queries are for concrete missing facts, unknown outcomes before a retry,
or recovery. cq_production_pending is a readiness wait, not a platform defect.
Copy every supplied source_ref field, including byte_length; correct a named
missing field without refreshing a file or repeating the incomplete call.
Read native/transport logs for concrete unresolved failures, not routine progress.

The four active get queries (get_run_status, get_pending_actions,
get_evaluation_status, get_request_result) return model-only compact views
with raw-result references and omission coverage. Correct any concrete gap
through bounded read_delivery_artifact selection; do not fetch whole histories
or poll merely to explain waiting. Program observation and receipt/binding
checks continue using the full original Host results. A recovery bootstrap
acknowledges only itself; outstanding input pages and original message
acknowledgements remain independent. Resent unknown facts do not authorize
repeating an action. Original user messages preserve earlier effective
constraints; a later message does not silently replace them.

Host `phase_thread_boundaries` optionally selects production and/or acceptance;
the default is empty. At a selected boundary, yield with
thread_boundary={phase,run_id,request_ids} and complete effective active_decisions,
original references and reasons, then end the activity. Production requires
accepted cq_freeze and freeze-notification instruction receipts plus confirmed
production continuation. Acceptance requires accepted cq_handoff_complete and
actual authorized evaluation operations after writes settle. The program defers
unsafe switches; continue normally without redoing production or resetting quota.
New phases receive current facts, original constraints and effective decisions.
Mechanical continuations remain separate work; yield does not execute them.
If core.phase_thread_handoff.status is deferred, follow its bound blocker and the
unresolved request feedback. Continue the original task on the current thread;
do not repeat that handoff or resend an uncertain action merely to obtain an ID.
Otherwise, treat current core.phase_thread_handoff as the immediate handoff decision before
repeating the same wait. Copy its request identities into thread_boundary; for production
select the actual accepted freeze-notification instruction from notification_request_ids,
never an unrelated instruction. Preserve still-effective decisions and original constraints,
then end this activity. This candidate does not prove a switch; original receipt, activity,
input and write-safety checks still decide whether it can happen.
submit_instruction and resolve_issue fill an omitted request_id and return the actual receipt-tracking
identity. Use that returned identity for notification/handoff bindings; native replay
retains the same identity. Explicit request IDs remain unchanged.
An explicit thread_boundary survives later ordinary yield records. Keep current
effective decisions in each yield; omit the field to retain that pending handoff,
or send null to cancel it. New inputs still need a fresh yield; pending controls,
unknown receipts/writes and active inference continue to defer the switch.

## Deterministic phase progression after a semantic decision

When actual production reports and write receipts are complete, reconcile
readiness and call `complete_cq_handoff`; do not wait for `state.json` to
become terminal first. `RUNNING` can mean the Runner is waiting for this
Host action. Respect typed readiness rejections and correct their stated gaps.
At this handoff, `cq_production_pending` means production role reports have
not settled. Follow the returned reason and next_action; once they settle,
retry the same freeze binding with a new request ID. No broader authorization,
added `delivery_binding`, or terminal `state.json` is required. Historical receipts
may use `cq_batch_scope_unauthorized` for this wait; confirm their actual detail
or production readiness rather than interpreting that legacy code alone.
After `cq_production_pending`, a new production-role `terminal_report_accepted`
receipt (`agent_id` identifies the role) is a readiness change: retry
`complete_cq_handoff` with the same freeze and a new request ID. The returned
readiness check decides whether another role remains pending. Do not wait for
an extra run-settled signal or poll unchanged state; CQ can keep the run open
until this handoff.
An accepted CQ handoff creates an acceptance binding, not an evaluation
process. If no matching operation exists, call `start_evaluation` for each
authorized public/hidden group with the returned handoff/freeze binding,
selected model profile and configured timeout; only then wait for reports.
Do not resend the same freeze or terminal-report reminder while its production
inputs are queued. Let the recipient consume them and react to actual results or
a new actionable gap; repeated reminders can prevent a DSH terminal report.
After an acceptance runtime failure retains its final report, explicitly call
complete_cq_handoff with retry_of=<current acceptance_attempt_id> and a new
request ID to allocate read-only reacceptance. Evaluate and complete using the
returned model_handoff/attempt, retaining the old reports and full frozen scope.
An ordinary duplicate handoff remains idempotent; do not rebuild the model for
an acceptance-only retry.
`evaluation_handoff_stale` returns the already allocated current model_handoff/attempt;
use it with a new operation_id. `cq_handoff_immutable` means the selected group already
published a report: request the new read-only attempt using retry_of, then use that
actual accepted binding. These are correctable inputs, not model-quality failures.
Execute all requested final public/hidden groups on that new binding; preserve
prior passes as history rather than mixing attempts to declare a new full PASS.

For each authorized acceptance scope, track the selected public and hidden question
groups separately. A hidden report covers only its selected questions; public CQ
review/public projection is not public Consumer/Judge acceptance. Do not emit final
until every requested group has its actual bound report, or explicitly report the
remaining group as unfinished. Keep early public-feedback separate from final public
acceptance. Preserve the existing total of at most three concurrent question tasks.

A valid new report and work_state=completed mean evaluation work has finished even
when status=running and lifecycle=standby. Use complete_cq_acceptance to return the
actual hidden report, then proceed to any remaining authorized group with the same
freeze/model_handoff. Do not wait for owner/PID exit or call stop_delivery_operation
to advance. Only explicit user stop permits stopping retained owners.
Keep the source production Runner alive through the accepted complete_cq_acceptance
receipt. Production readiness and read-only sealing permit acceptance while the
Runner remains available; stopping it early removes its control channel and
prevents the final acceptance acknowledgement. Then use standby_run and
finish_delivery for normal successful closure.

Use the existing tools to carry out already-decided deterministic follow-through
without another planning-only turn: copy returned bindings, submit the original
request, reconcile its actual receipt, and continue the next ready authorized step.
Batch independent reads in one turn; keep dependent writes/confirmations ordered.
For the Delivery-to-Host CQ request copy the current `review_id`,
`content_version`, `content_digest`, and `question_ids`; these are technical
bindings, not additional review decisions. The Host alone later uses the
existing per-question `question_id` binding when it calls `submit_cq_review`.
Use Attempt status for applied batch counts, not the number of receipts. Pause for
a genuine unresolved semantic/authorization choice or unknown write, not a successful
receipt or a retained idle owner. Do not invent an extra phase or bypass declared
CQ review/freeze dependencies to reduce time.

For final public cq-acceptance use question_visibility=public and the current
model_handoff/freeze_id. Omit question_ids and checkpoint_id: those arguments belong
to public-feedback. Use the same selected model profile and configured bounded
session timeout. After reports are verified use finish_delivery's existing sealing
and retention path; report limitations rather than stopping an owner to force exit.


## R4.4-001 work visibility

For a specific coordination gap, use the bound read-only `get_team_work_board` tool. It returns
shareable production reports, request/transport states and references, with optional fixed-prefix
history, exact versions and already published member/session statistics. Your flow projection
excludes Host context, peer result bodies and private acceptance members. Times filter history,
not the original statistics window; missing bindings stay unknown. Follow returned pagination
and source references. Reports and open requests do not prove progress or add a closure gate.
Do not poll the board, copy the full board into each decision, or request redundant reports:
ordinary card updates do not wake you. Necessary errors/blockers still use the original messages,
issues and `request_host_action` paths. Keep your existing yield/wait journal; do not maintain a
second production card for Delivery. Host can query the retained archive after closure without
reopening a run. Actual adoption and maintenance cost require separate authorized observations.
