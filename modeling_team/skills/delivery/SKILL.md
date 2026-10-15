---
name: delivery
description: Supervise one authorized ontology delivery through the restricted Host tools and the single business conversation.
---

# Independent Delivery

Use this skill only in the independent Host-private Delivery thread. Do not
load it into the production Coordinator, Modeling, Protocol, Consumer, Judge,
or a testing business answerer.

Start by reading the supplied deployment configuration and its authorization.
Record and use its task, profile, model profile, approved sources and scope.
Use start_run only for an authorized fresh production start; use the existing
budget/start ledger, never assume that a delivery session grants new quota.
Treat authorized modeling counts as modeling rounds unless the user explicitly
chooses fresh-start-only accounting. An initial semantic start costs one round;
a new substantive modeling repair task after self-check/review/acceptance also
costs one, even in the same run/thread. Continuous initial drafting and technical
corrections within the same repair task do not add rounds. A fresh production
start/resume costs one, without double charging its repair round. Record the
round goal, trigger, actual start evidence, result and balance in the existing
Host ledger, separately from semantic starts; never infer balance from candidate
versions or apply counts. Check quota before dispatching substantive repair.
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

On delivery_resume, inspect the observed real state and receipts before doing
anything. Read the observed request_ledger and call get_request_result for
each unresolved request_id before retrying. A previous unknown request must
not be replayed as a new action. Missing receipts do not mean the action failed.

Use read_delivery_artifact for approved business sources and the bound run's
private CQ/review/evidence. These responses are private. Publish only explicit
business messages with emit_user_message: status, business_question,
decision_request, or final. Never publish reasoning, raw tool responses,
credentials, hidden questions, hidden answers, internal IDs or log excerpts.
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

CQ review is explicitly delegated. Read the current draft, review version and
approved source basis, and verify that the review snapshot phase is exactly
`panorama-review` or `slice-review`. A `panorama-draft` or `slice-draft`
snapshot is preparation only: do not approve it, freeze around it, or keep
retrying freeze; ask the CQ role to republish the same material in the exact
review phase, then review the new snapshot. For each submit_cq_review note,
record delegated Agent review, authorization, source/version references and
the reason for the decision. Bind slice questions to the exact approved slice IDs from
the current scenario/topology handoff; an underscore/hyphen variant is a different ID.
Correct a scope mismatch through the existing review decision before freezing, rather
than normalizing IDs or approving against an anticipated future map. Ask the business user only about unresolved
business ambiguity or scope changes. Never claim that the human approved
every CQ individually.

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

Freezing and the production handoff are two separate phases; a freeze is only
the precondition for formal production and never substitutes for modeling or
completion. Phase one, right after freeze_cq succeeds: verify the real freeze
binding and the public projection, then send the located public projection and
the explicit Host freeze confirmation to the original Coordinator through the
existing submit_instruction with kind delivery_guidance, and let formal
semantic Modeling/Protocol production continue. That note carries no hidden
questions or answers and creates no new business definition or authorization.
Phase two: call complete_cq_handoff only when production has actually
completed under the existing readiness and hard-gate outcomes — necessary
dry-run/apply receipts plus read-back/self-check evidence exist, no pending or
unknown writes remain, and the Runner's current handoff-ready binding
(freeze_id and freeze_digest) is complete — and then continue the existing
independent acceptance flow. frozen_awaiting_handoff or a CQ pending item that
merely lists an available action is not evidence of handoff readiness;
submitted is not consumed; a cq-input-rejected reply is an explicit rejection
to read in full, not an unknown request awaiting confirmation. Read the
complete original events and receipts needed for the current decision before the next step and never
mechanically infer readiness from pending state. Runner consumption of a
confirmation never automatically starts acceptance, so never tell the user
that it does.

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

Supervise the original operation through its actual request, governed
Consumer reads, complete feedback body and current report binding/digest.
Accepted guidance, an accepted request, a status/question-count summary or an
applied receipt is not feedback and is not a quality PASS. Release the normal
submission wait through the same guidance/Team channel only after that original
operation ends; preserve unknown writes and explicit user pauses. Route only
affected content and real dependents for correction, keep independent work
moving, and do not add fixed per-batch questions, an automatic loop or a
resident full readback routine. Do not turn an unavailable or untriggered
feedback scenario into a new platform hard gate; keep the applied write as
applied, leave only its feedback/quality effect unverified, and record the
boundary.

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

For a publicly established technical defect, prepare_repair_task can write a
narrow task under the configured public references and owned paths. Use the
selected executor/model/effort with start_repair. Do not pass hidden question
text, paraphrased hidden scenarios, expected answers or your private history
to the repairer or production. A public citation does not make hidden content
public. Require the repairer to report concrete diff, checks, deployment
effectiveness and unresolved limits in a public result artifact. Observe its
actual exit and read the owned repair-result patch/JSON. Use verify_repair for
fixed Host checks, and get_repair_verification_status for their real completion.
These checks run asynchronously; continue observing business input and runs.
Backend/frontend changes require explicitly configured repair.allow_deployment
and fresh successful write-state reconciliation of bound runs before changing
the runtime. A failed test, denied deployment, unhealthy endpoint or target
drift remains unverified. Only a current verification record bound to the
original issue can support resolve_issue(repair_completed). Then request fresh
independent semantic acceptance; local checks are not a Judge verdict.

Pause, cancel and budget revocation take priority over new launches. Do not
treat elapsed waiting time as approval. The local business adapter preserves the exact control and its original sourced
message. 暂停/继续 are cooperative instructions: route to the Coordinator during
production, or via relay_evaluation_message to the actual Consumer/Judge during
acceptance. Read their actual acknowledgement before record_flow_confirmation;
a delivery receipt alone stays pending. Do not interrupt or install a global pause
switch. 取消/撤回预算 preserve their separate authorization-revocation contract. A host interruption is recorded as supervision interrupted,
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


R4.3-022 decision inputs use `delivery-decision-input/v1`. Start with current
state, coverage, actual changes and exact evidence locators. The full latest
observation and original ledger/events/reports remain Host-private evidence.
Settled request/operation history is an index, not a reprinted history. Do not
read the whole observation or ledger again merely to confirm waiting.

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
Large referenced values carry their packet_path inside the original packet.
Do not infer absence of pending/unknown writes from a partial page. Old ordinary
file bindings fail with artifact_changed; restart against the current identity.
JSONL references bind a captured prefix, so append is safe but rewrite/shortening
requires a fresh identity. Exact events use source byte_offset/byte_length,
not page-local line_no. Recoverable selection/unavailable/corrupt errors require
correcting the read, not abandoning the modeling goal.

A delivery_status of unknown means the native receipt is uncertain and this
observation may already have been received. Reconcile current facts; never
replay platform actions because a Delivery input was resent. For CQ review,
read the selected questions and necessary business basis. For public feedback,
read all actual answers, read evidence and complete feedback for the selected
questions. For faults, read the exact event/receipt/log; for final delivery,
verify original report qualification, versions and independent verdicts.
Compact inputs do not establish PASS or reduce the required question denominator.
When current_state identifies a newer packet, this packet snapshot is historical;
read and reconcile the newer necessary state before state-dependent actions.
Host-private Judge/CQ content, references and decision packets remain private;
reading them grants no permission to forward them to production, repair or a
test answerer. Existing public projection/material routes and role duties apply.
Byte reductions alone do not establish token savings or net cost improvement.
