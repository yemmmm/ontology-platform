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

Observe active runs and operations after every phase. Accepted is not
consumed; a PID is not semantic start; exit zero or a preexisting report is not
independent acceptance. After production completes, continue the authorized
live cq-acceptance/public-feedback or the existing checkpoint acceptance
resume. Do not stop supervision just because Coordinator/source is terminal.

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
treat elapsed waiting time as approval. The local business adapter handles
the exact controls 暂停 / 取消 / 撤回预算 immediately and passes their original
text back to you. A host interruption is recorded as supervision interrupted,
not success. Resume from real state without silently relaunching production.

Finish with an explicit final business message stating what is verified and
what remains unknown, then finish_delivery. Keep functional PASS separate
from L0 runtime and independent L1 semantic acceptance. No self-review can
replace Consumer/Judge acceptance.
