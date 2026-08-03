# R2.3-005 Schema-v2 Outer Answer Routing Repair Plan

## Outcome

Repair the `collaboration/routing` defect proven by retained run
`r23005-real-20260803t141820z`: the authoritative schema-v2 user input remains exactly
`{"action":"user","text":"<verbatim answer>"}`, while `TeamRunner` deterministically binds that
text to the one current Modeling question that Coordinator has actually surfaced. The repair is
offline only. It does not reopen the consumed semantic-start budget and does not make the retained
run acceptable.

## Authority and observed failure

- Authority: `docs/requirements/requirements-v2.3.md:460-469` and the owner-answer ordering contract
  at `:1257-1275`.
- Direct evidence: `delivery-1` is a Modeling-to-Coordinator `expects_reply` delivery and the same
  text appears in the Coordinator output, but no `outer-question.jsonl` or `outer-user.jsonl` exists.
- Current mismatch: `TeamRunner.receive_outer` reads `question_delivery_id` from the user object even
  though the required user envelope cannot contain it. `_record_outer_question` is reachable only by
  an implementation-only outer `action=question` object. Existing tests cover schema v1 or call the
  private owner-answer helper after manually seeding question state.
- Independent round 1 verdict: `BLOCKED/collaboration/routing`; Protocol and Acceptance semantics were
  not reached.

## Current minimal scope

### 1. Runner-owned pending-question observation

Owner: requirement developer. Files: `modeling_team/runner.py` and focused tests only.

- In formal schema-v2 coordination, observe a question candidate only after Team Transport has
  successfully forwarded and acknowledged a delivery that is:
  - from the Modeling role to the Coordinator role;
  - `expects_reply=true`;
  - not itself a reply;
  - bound to the active run/project.
- Keep the candidate internal and immutable. Do not trust an ID or text supplied by the outer user.
- When a Coordinator Runtime message is received, mark/register the candidate as outer-visible only
  if the message contains the exact candidate text. Persist the existing four-field
  `outer-question.jsonl` record at that point. Reject ambiguous output that exposes more than one
  unresolved candidate in a single prompt; do not guess by ordering, substring preference, or newest
  delivery.
- Do not change `TeamTransportBroker.send`, Delivery ID allocation, role permissions, task prompts,
  model/SSE semantics, `agent_end`/`agent_settled`, or Platform cleanup.

### 2. Strict text-only schema-v2 answer resolution

Owner: requirement developer. Files: `modeling_team/runner.py`, `modeling_team/transport_mcp.py`,
`modeling_team/runtimes/base.py`, `modeling_team/runtimes/codex.py`, Modeling's formal instructions,
and focused tests.

- For schema-v2 `action=user`, require exactly the keys `action` and `text`; reject caller-provided
  `question_delivery_id` and every other extra field.
- Resolve the answer internally to exactly one outer-visible, unanswered question. Fail fast before
  writing evidence or sending a Runtime message when there are zero or multiple eligible questions,
  when the question was not shown by Coordinator, or when the run/project binding drifts.
- Call the existing owner-answer persistence/release path with the internally resolved delivery ID.
  Preserve the exact nine-field `outer-user` record, canonical `owner_answer_id`, fsync-before-send,
  correlated `reply_to_delivery_id`, exact Unicode text, authorization binding, and send-failure
  burn/no-reuse behavior. The specific Round-63 owner-answer contract overrides the ordinary
  supplement route: after fsync, Runner delivers the answer directly to the Modeling role that
  originated the question, not to Coordinator for a text-only Team Transport re-forward.
- Publish the direct Modeling answer through a new, narrowly typed Broker owner-answer reply path,
  not by calling `RuntimeAdapter.send_message` outside Team Transport. After the outer-user record is
  fsynced, Runner asks the Broker to publish exactly one reply with `sender_id=user/outer`, recipient
  equal to the Modeling originator, the Runner-generated `release_id` as its Delivery ID,
  `reply_to_delivery_id` equal to the original question ID, and the exact owner ID/release/text.
  The Broker method must validate that the original active request is an acknowledged formal
  Modeling-to-Coordinator `expects_reply` delivery, that no reply/owner answer is already bound, and
  that the supplied IDs cannot collide with ordinary deliveries. It is not a generic permission bypass.
- Do not mutate Broker queues or pending-reply state before the immutable outer-user record is fsynced.
  After fsync, Broker publication enqueues the special reply and atomically binds the original pending
  request to that release ID. Runner's existing drain sends it only to Modeling; normal
  `ack_delivery(release_id)` removes the original pending request. Until that ack, Modeling's terminal
  report must remain blocked. A Broker publish or Runtime delivery failure leaves the question consumed,
  the run failed and evidence retained; it never reopens a second answer.
- Extend `Delivery` and `RuntimeDelivery` additively only as necessary to give Modeling distinct,
  machine-readable `owner_answer_id` and `release_id` fields alongside the exact original `text`.
  Codex serialization includes the two owner fields only for this owner-answer kind so legacy delivery
  envelopes remain byte/shape compatible. Update Modeling's formal instruction to preserve the
  delivered owner ID in candidate citations. Ordinary supplements, corrections, scope changes and
  schema-v1 input continue through Coordinator; they are not this owner-answer exception.
- Lock consumption by `question_delivery_id`, never by `(question_delivery_id, answer text)`. Mark a
  question ineligible for every later answer text as soon as its one release attempt begins. A
  successful release, a persistence/open/write/fsync failure, and a post-fsync Runtime send failure
  must all prevent the same question from generating a second owner ID, release, record, or message.
  Preserve the failed run/evidence behavior and never reopen the question by changing the text.
- Keep any `(question_delivery_id, text)` map only as an immutable record lookup if required for
  compatibility; it must not be the replay/consumption authority. Repeated same-text and different-text
  input after success or failure must fail closed before any new sequence/ID allocation.
- Preserve schema-v1 behavior. The existing `action=question` code path may remain only for non-formal
  compatibility, but formal schema-v2 correctness and tests must not depend on an operator sending it.

### 3. Strict outer-control JSON decoding and cleanup

Owner: requirement developer. Files: `modeling_team/__main__.py` and focused CLI tests.

- Add one deterministic decoder used by `_foreground_event_loop`. It must accept only a UTF-8 JSON
  object, reject duplicate object keys at every relevant envelope level, and return a mapping suitable
  for `receive_outer`. A JSON array, scalar, `null`, malformed JSON, or duplicated `action`/`text` key
  must raise a fixed caught configuration/value error, never an uncaught `AttributeError`.
- Keep schema-v2 user-object exact-key validation in `receive_outer`; decoding an object does not make
  extra keys legal. Preserve supported non-user control actions and schema-v1 compatibility.
- Prove through the real `main`/foreground boundary that every rejected line reaches `cleanup_once`
  exactly once and returns the fixed failure exit, with no second start, process or scope residue.

### 4. Real foreground JSONL regression

Owner: requirement developer. Files: focused Runner/CLI test modules; no real model or platform.

Add a no-model test that exercises the actual chain:

1. a formal schema-v2 Modeling-to-Coordinator `expects_reply` delivery is forwarded;
2. Coordinator emits a prompt containing the exact question;
3. `_foreground_event_loop` reads and decodes `{"action":"user","text":"未知"}`;
4. Runner creates the bound outer-question record, fsyncs the exact outer-user record before send,
   sends one correlated owner answer with the same owner ID/release/text directly to Modeling, and
   drains normally; Coordinator receives no duplicate answer to re-forward.

Required negative coverage:

- no pending question, multiple displayed pending questions, question not yet displayed;
- Modeling delivery not addressed to Coordinator, non-Modeling sender, reply delivery, or
  `expects_reply=false`;
- Coordinator prompt text mismatch and a prompt containing multiple candidates;
- extra `question_delivery_id`, unknown action, non-string text, malformed JSON, JSON non-object roots,
  and duplicate JSON keys; each foreground failure must exercise one-and-only-one cleanup;
- same-text and different-text replay after a successful release;
- persistence failure before a complete fsync and Runtime send failure after the record is fsynced;
  both lock the `question_delivery_id` against same-text and different-text retries without allocating
  another owner ID/release;
- source record/project/run immutability and exact Unicode/newline preservation;
- owner-answer recipient is the originating Modeling role; rendered Runtime input contains the exact
  `owner_answer_id`, `release_id`, original `text`, `delivery_id=release_id`, and
  `reply_to_delivery_id=question_delivery_id`; a candidate citation can retain that owner ID;
- Coordinator receives no owner-answer copy and ordinary schema-v1/non-answer supplements still use
  its existing route;
- before Broker publication there is no queued reply or pending-state mutation; after publication but
  before ack, Modeling terminal report is rejected; normal drain delivers exactly once, ack closes the
  original pending request, and Modeling may then reach its ordinary terminal/settlement gates;
- duplicate/colliding owner publication, wrong sender/recipient/request direction, unacknowledged or
  inactive original request, publish failure and Adapter delivery failure all fail closed without a
  Coordinator duplicate or a second owner ID;
- schema-v1 compatibility and existing owner-answer identity tests.

### 5. Verification and delivery

- Before editing each Runner/CLI symbol, run GitNexus upstream impact. Current read-only baseline:
  `receive_outer` MEDIUM (15 affected, six direct); `_record_outer_question`,
  `_release_owner_answer`, `_foreground_event_loop`, and `TeamTransportBroker.send` LOW. Impact the new
  decoder/main cleanup call site, `Delivery`, `RuntimeDelivery`, Broker owner-answer publish/ack/report
  state, Runner drain, Codex delivery serialization, and Modeling instructions before editing as well.
  Warn before any newly discovered HIGH/CRITICAL edit.
- Run focused new tests, all R2.3-005/Runner/CLI tests, complete `modeling_team` discovery, Ruff and
  `git diff --check`.
- Run GitNexus `detect_changes(compare main)` before commit. Review unexpected touched processes.
- This repair changes no backend/frontend file, so backend pytest, service restart and endpoint health
  are not required unless implementation scope expands into those paths. If it does, stop and return
  for plan revision.
- A fresh requirement tester must independently rerun the deterministic tests and record round 2.
- Commit only after round 2 closes deterministic defects. Do not invoke a real Producer, create a
  Project/Ontology, touch either start ledger, or claim semantic acceptance.

## Separate optional evidence item

The missing machine-readable PTY exit receipt is P2 evidence completeness, not part of D1. If later
authorized, add a sanitized operator-owned exit receipt without raw stdout or secrets and test its
write/hash behavior separately. Do not couple it to answer routing or make it a D1 completion gate.

## Future productization — excluded

- multiple simultaneous owner questions, queues, prioritization or arbitrary correlation UI;
- durable cross-process recovery of pending questions;
- new API/table/event schema, remote controller, scheduler or management UI;
- semantic answer inference, automated owner answering, tester-answer exposure or retry budget;
- a second real semantic start without explicit user authorization.

## Completion gate

D1 is complete only when the authoritative text-only envelope passes the actual schema-v2 foreground
path, every ambiguity and replay case fails closed, owner-answer identity/order remains intact, the
full deterministic suite passes, and a fresh independent Tester records round 2. This proves routing
correctness only; it does not convert the retained run from BLOCKED or authorize another real run.
