# R2.3-005 Outer Display-Binding Repair Plan

## Goal

Repair retry3's narrow `collaboration/routing` failure without changing the business slice,
Runtime Adapter, Team Transport contract, model/SSE semantics, or semantic-start accounting. A
formal Modeling question becomes answerable only after the exact Runner delivery envelope that
contains its `delivery_id` has been emitted successfully to the foreground host.

The retained business contract remains the approved R2.3-002 `C -> B -> A` slice. For the missing
numeric-score question, the approved source does not state whether B blocks, continues, retries, or
marks for review. The correct owner response is therefore the literal `未知`; this preserves an
explicit unknown and is not a new business assumption.

## Evidence and root cause

- retry3 run `r23005-real-20260804t030823z-retry3` registered Modeling question
  `delivery-4`, but Coordinator returned a faithful paraphrase rather than the original text.
- `_observe_coordinator_message()` currently marks a question displayed only when the original
  question is an exact substring of Coordinator text. No match meant no `outer-question` evidence,
  and the one authorized `{"action":"user","text":"未知"}` failed closed with
  `owner answer question has not been displayed`.
- `TeamRunner.drain()` already returns the exact acknowledged delivery as a structured foreground
  envelope containing `type`, `delivery_id`, sender, recipient, question text and reply metadata.
  `_foreground_event_loop()` calls `emit(output)` before it accepts the next input. The production
  emitter prints JSON with `flush=True`, so successful return is the deterministic host-display
  boundary that the current implementation failed to bind.
- retry3 is CLEANED with zero owned residue and no complete modeling-quality result. The formal
  ledger is cap 4 / starts 3 / active 0. One semantic start remains and must not be used until this
  repair is independently PASS and committed.

## Current minimal scope

1. Add one narrow Runner operation that observes only the Runner-generated foreground output after
   the caller has emitted it successfully. For each formal pending question, bind display by its
   exact `delivery_id` and immutable envelope fields, never by answer text or semantic similarity.
2. Centralize the foreground output action so **both** `_foreground_event_loop()` output paths use
   the same ordering: call `emit(output)`, then only after successful return ask Runner to observe
   that exact emitted output. This covers output returned by the top-of-loop `runner.drain()` and
   output returned by `runner.receive_outer()` (which itself drains and can contain a newly arrived
   Modeling question). If either emit raises, do not mark display and do not write
   `outer-question.jsonl`.
3. Stop using Coordinator prose as the formal display authority. A verbatim repeat, paraphrase, or
   omission by Coordinator must not create, select, or suppress a formal question binding. Existing
   Coordinator output remains visible and otherwise unchanged.
4. Preserve the current text-only outer input schema. The user/operator continues to send exactly
   `{"action":"user","text":"<verbatim answer>"}`; no caller-supplied question ID is accepted.
5. Preserve fail-closed resolution. Zero displayed questions fails, and more than one displayed,
   unanswered question fails as ambiguous. Do not choose by order, fuzzy text, or answer content.
6. Make display observation idempotent. Re-emitting the same exact envelope must not duplicate
   evidence or reopen a consumed question. An unknown ID or any sender, recipient, text,
   `expects_reply`, `reply_to_delivery_id`, run, Project, or origin drift must not mark a question.
   Treat a contradictory envelope for a known pending ID as configuration failure rather than
   silently accepting it.
7. Validate the complete emitted batch before changing any pending question or writing evidence, so
   a contradictory known-ID envelope cannot leave earlier items partially acknowledged. For every
   valid new display, durably append and fsync its exact `outer-question` evidence before setting
   `displayed=true`. An evidence open/write/fsync failure propagates immediately and the foreground
   loop must not read or release an owner answer. Displays that were each fully evidenced before a
   later independent persistence failure may remain recorded, but the run aborts rather than
   continuing with a partially acknowledged batch; no displayed state may exist without its durable
   evidence.
8. Preserve the existing owner-answer identity, durable evidence-before-publication order, direct
   release to Modeling, Broker reply closure, replay burn, cleanup and settlement behavior.
9. Do not change `RuntimeMessage`, `RuntimeDelivery`, `CodexRuntimeAdapter`,
   `TeamTransportBroker`, App Server item IDs, SSE events, model prompts, ledger policy, platform
   APIs, or the accepted business source/question set.

## Test contract

- Foreground emit success marks exactly the emitted formal question by `delivery_id`, writes one
  `outer-question` record with the original question, and allows the next exact owner answer to
  reach Modeling even when Coordinator only paraphrases it.
- Foreground emit failure leaves the question undisplayed and creates no display evidence; a later
  owner answer fails closed.
- A question first returned by `runner.receive_outer()` is acknowledged through the same
  post-success emit hook as a question returned by the top-of-loop `runner.drain()`; neither call
  site may bypass the display observation.
- Unknown/forged/drifted envelopes cannot mark display. A contradictory known-ID envelope fails
  closed without changing the pending record or evidence.
- Mixed valid-plus-contradictory batches are fully validated before mutation. Injected evidence
  open/write/fsync failure never leaves `displayed=true` without the matching durable record and
  prevents the foreground loop from reading the next owner input.
- Duplicate display is idempotent; consumed or late display cannot reopen a question or duplicate
  evidence.
- If two distinct pending questions were actually emitted, both may be recorded as displayed but a
  text-only owner answer must fail as ambiguous. The Runner must never select one implicitly.
- Existing non-formal/schema-v1 routing and formal direct owner-answer identity/replay/failure tests
  remain unchanged.
- A production-shaped deterministic path must cover formal `prepare()` normalization, `start()`,
  live Project creation, Modeling `expects_reply`, `drain()`, successful foreground emit,
  Coordinator paraphrase, literal `未知`, direct Modeling release and cleanup without model/network
  use.
- Run focused owner-answer/foreground tests, all R2.3-005 tests, complete managed
  `modeling_team` discovery, Ruff and `git diff --check`. Before commit, run GitNexus
  `detect_changes()` and confirm only expected symbols/flows changed. Because no backend/frontend
  surface is in scope, backend pytest and service restart are required only if implementation
  actually crosses those boundaries.

## Delivery and last-start gate

The developer must run GitNexus upstream impact analysis before editing every existing function or
method and report the blast radius. Any HIGH/CRITICAL result pauses editing until the main agent has
warned the user and accepted the exact narrow scope. The main agent owns the delivery record; the
developer must not edit it or commit.

Only after plan-review PASS, development-ready handoff, independent test PASS, documentation sync,
`detect_changes()`, and a clean commit may Delivery prepare start4. Under the formal ledger lock it
must append retry3's `terminal_failure` as `collaboration/routing` with
`complete_modeling_quality_result=false`, freeze a fresh start4 run ID and exact post-repair
baseline, then append `repair_authorization` for failed retry3 bound to that start4 baseline. No
budget event is allowed. Read back cap 4 / starts 3 / active 0 and the unchanged R2.3-002 ledger
before reservation.

Start4 must use a fresh Project/Ontology, four fresh persistent Agents, new child Examiners and new
credentials. The literal `未知` is released once only if the new run asks the same grounded
question. Stop at the first complete PASS. If start4 consumes the final budget and fails, do not
start again without new user authorization.

## Future productization

Structured UI acknowledgements, external display receipts, multi-question interactive selection,
App Server item correlation, generalized Host orchestration, and transport-level reply correlation
remain future work. They are not prerequisites for this local modeling-quality experiment.
