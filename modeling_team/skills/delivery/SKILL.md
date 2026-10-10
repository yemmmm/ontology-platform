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

Preserve each user_input packet's original text and source_reference. Match a
reply to the actual pending question_delivery_id from get_pending_actions;
do not make one up. Send unsolicited supplements via submit_instruction with
kind user_supplement and the original source/authorization. Technical control
notes use kind delivery_guidance. Coordinator remains the internal production
coordinator; it forwards relevant content once. CQ interview/review tools use
their separate private channel.

CQ review is explicitly delegated. Read the current draft, review version and
approved source basis. For each submit_cq_review note, record delegated Agent
review, authorization, source/version references and the reason for the
decision. Ask the business user only about unresolved business ambiguity or
scope changes. Never claim that the human approved every CQ individually.

CQ question-pool phases run in their declared order: panorama draft, panorama
review and public projection, bounded slice proposal and assignment, then
slice-question drafting and review. Freeze the complete selected pool only
after these declared drafting/review stages have actually completed for every
selected question. A freeze tool becoming available early is not evidence that
drafting is complete, and later-approved slice questions must not remain
outside a frozen pool that already covers the rest of the selection. You
initiate the freeze and handoff yourself through the real Host bindings once
the phases are complete; never infer that the Runner or the CQ role will
autonomously publish a new freeze. Preserve already frozen snapshots: publish
a fresh complete freeze through the authorized tool instead of rewriting one.
Scope changes and unknown business decisions still go to the business input
party, not into a freeze decision.

When Coordinator or Protocol needs the author-supplied task_id, read it from
the frozen Task snapshot that get_run_status exposes as identity.task_id and
provide that exact value through submit_instruction with kind
delivery_guidance and its source reference. Never substitute run_id,
scenario_id or any platform-generated identifier, and never invent a business
input or question to carry it.

Observe active runs and operations after every phase. Accepted is not
consumed; a PID is not semantic start; exit zero or a preexisting report is not
independent acceptance. After production completes, continue the authorized
live cq-acceptance/public-feedback or the existing checkpoint acceptance
resume. Do not stop supervision just because Coordinator/source is terminal.

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
