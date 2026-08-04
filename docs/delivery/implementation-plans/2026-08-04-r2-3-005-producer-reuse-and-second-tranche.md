# R2.3-005 Producer Reuse and Second-Tranche Plan

## Outcome

Restore the accepted R2.3-002 Producer boundary in the R2.3-005 four-role run, prove the correction
without a semantic start, and only then make the user's second exact `+3` authorization available for
start5. Modeling owns business semantics and emits a platform-neutral candidate. Protocol alone owns
deterministic candidate-v2/Batch translation and every platform call. Acceptance remains independent
and starts only after Modeling and Protocol are ready and silent.

This plan does not itself append to either live ledger, create a Project/Ontology, or consume a
semantic start.

## Direct evidence and classification

- Retained start4 successfully routed three displayed owner questions and literal `未知` answers.
  That previously repaired interaction is not the current defect.
- Modeling delivery-10 emitted a source-grounded neutral candidate. Protocol rejected it before any
  platform call because the R2.3-002 proof-v2 envelope, assertion matrix and evidence-map mechanics
  had become unconditional schema-v2 prerequisites.
- Coordinator then directed reuse of a prior scope even though R2.3-005 requires a run-owned fresh
  Project/Ontology. Modeling and Protocol correctly refused that scope change.
- The retained terminal classification therefore remains `collaboration/routing` with
  `complete_modeling_quality_result=false`. No dry-run, application, readback, validation, reasoning
  or Acceptance verdict exists.
- The accepted R2.3-002 task and public protocol assign semantic interpretation to Modeling and
  deterministic platform translation/execution to Protocol. Reuse that division instead of creating
  another collaboration protocol.

## Current minimal implementation scope

1. **Make fresh scope unambiguous.** Update only the R2.3-005 formal task wording to require the
   Project/Ontology created for this run, prohibit reuse/binding of any prior scope, prohibit a second
   semantic start inside the task, and state that Acceptance begins only after separate Modeling and
   Protocol ready/silent signals. Add the accepted R2.3-002 `public-protocol.md` as a Protocol-only
   role source; do not expose raw business sources to Coordinator.
2. **Condition proof-v2 prompt material on the proof gate, not schema version.** In Runner prompt
   construction, include the assertion matrix, evidence map, native-verifier instructions and other
   proof-v2/P2 text only when the loaded run has a non-null `expected_matrix_binding`/gate binding.
   R2.3-002 proof tasks retain that binding. R2.3-005 has no such binding and receives the generic
   mechanics contract plus the accepted neutral-candidate-to-Protocol ownership language.
3. **Use the same proof gate at Runtime.** Stage retrieval/proof-v2 assets, configure the
   `protocol_mechanics` MCP server and require its proof-specific tools only for a proof-gated run.
   Always retain the generic mechanics contract and ordinary Protocol platform tools. Keep the
   baseline manifest entries as integrity metadata so the existing baseline and ledger contract do
   not drift merely because assets are not mounted for this run.
4. **Clarify package wording, without changing roles.** Mark proof-v2 sections in the Modeling and
   Protocol instructions as conditional on the provided proof binding. Preserve the general rule:
   Modeling supplies source-grounded semantics and explicit unknowns; Protocol translates the
   neutral candidate and performs platform operations.
5. **Prove a production-shaped neutral handoff deterministically.** Reuse the shape of retained
   start4 delivery-10 in tests. R2.3-005 Protocol must accept it for deterministic translation and
   produce the mechanical receipt/conflict surface instead of rejecting it for a missing proof-v2
   envelope. R2.3-002 proof-gated tasks must still require the full matrix/evidence-map/native
   verifier surface.
6. **Prove the second budget tranche without touching live state.** Extend temporary-ledger and CLI
   tests from cumulative cap/count/active `4/4/0` through one distinct exact `+3` event to `7/4/0`,
   then through repair, start5 reservation and semantic start. Cover wrong ordering, count below cap,
   duplicate authorization ID/reference across both tranches, malformed/forged events, concurrent
   contenders, interruption/resume and explicit R2.3-005 CLI selection. The R2.3-002 ledger remains
   byte-identical.
7. **Add one no-semantic-start real Runtime smoke.** Use the current R2.3-005 role packages/profile
   with a frozen synthetic platform-neutral candidate and a Runtime-generated, run-owned synthetic
   fresh-create Project/Ontology identity. Exercise actual Runtime prompt/config/tool projection and
   the Modeling-to-Protocol handoff far enough for Protocol to construct and validate candidate-v2/
   Batch mechanics, bind the receipt only to that synthetic fresh scope, and reject a caller-supplied
   or prior-run Project/Ontology identity. The synthetic identity is a non-platform test binding: the
   smoke must not perform business modeling, call a platform API, create/apply a model, start
   Acceptance, mutate a ledger, create a real Project/Ontology/Session/Lease/key, or claim semantic
   PASS. Retain raw prompt/config/tool/delivery/scope-binding evidence and before/after resource
   snapshots.

## Required sequencing and ownership

The repository's 20-minute first-real-attempt and semantic-effort gates have already triggered for
this tranche: work since authorization has been preparation/review rather than semantic modeling.
Main must record the elapsed time and consumers in the delivery record. This plan is the required
scope reduction: no additional harness, design branch or test category may be added. After the
existing deterministic cases and the single mandatory no-start smoke pass, hand off immediately to
the live start5 gate. If another prerequisite is discovered, pause and report it instead of expanding
the harness. Continue to record semantic versus infrastructure/harness/review/documentation time for
every live attempt.

1. Main agent freezes this plan, the shared C84-C93/I17-I19 cases and live-state hashes.
2. A Plan Reviewer checks the boundary, gates and executable sequencing. Any blocking finding is
   resolved in this plan before implementation.
3. One Requirement Developer owns the task/profile/package/Runner/Runtime changes, deterministic
   tests and bounded smoke fixture. The developer must run GitNexus impact analysis before editing
   every affected symbol and report any HIGH/CRITICAL result before proceeding.
4. A separate Requirement Tester independently runs focused tests, all R2.3-005 discovery, full
   managed `modeling_team` discovery, Ruff, `git diff --check`, GitNexus `detect_changes(compare
   main)`, and live-ledger/retained-evidence immutability checks. The Tester records its round in the
   existing shared test plan and does not create or continue a real modeling run.
5. After deterministic PASS, the Developer hands the tested smoke fixture/tool to Delivery.
   Delivery retains deterministic execution, lifecycle, cleanup and evidence-handoff ownership and
   runs the no-semantic-start real Runtime smoke. The independent Tester audits its retained evidence
   and resource/ledger immutability. A smoke result is only a handoff/runtime gate, never
   modeling-quality acceptance.
6. Only after the reviewed implementation is committed and both independent gates PASS may Delivery
   append live management events and start start5. Execution remains strictly serial.

## Post-fix live Delivery gate

Under the canonical R2.3-005 ledger lock, Delivery must use explicit
`--requirement-id R2.3-005` and append exactly:

1. one distinct `budget_authorization` with increment `3`, authorization ID
   `r23005-budget-plus3-20260804-tranche2`, and reference
   `user-authorized-plus3-after-start4-20260804-tranche2`;
2. one first repair authorization for the retained start4 failure, bound to the exact fresh start5
   tested baseline and the reviewed commit plus independent PASS;
3. one fresh start5 reservation and, only after all presemantic gates remain true, one semantic start.

Before each append, read back that the preceding event, run, cap/count/active and baseline are exact.
The required transition is `4/4/0 -> 7/4/0 -> start5`; do not duplicate the already recorded start4
terminal failure. Preserve the R2.3-002 ledger hash
`4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`.

Stop immediately at the first complete semantic PASS. A retry may occur only after a retained,
independently classified retryable incomplete failure and a narrow reviewed repair. If start5,
start6 and start7 are all consumed without full PASS, do not append another authorization or start;
return to the user for explicit approval.

## Future productization, excluded from this completion gate

- a generalized gate/plugin framework, arbitrary budget increments or a budget-management UI;
- P2/P2a expansion, Consumer/mutation suites, standalone Judge or automated acceptance program;
- new backend tables, APIs, recovery/orchestration services, cross-machine coordination or polished
  management UI;
- platform promotion of Dify Workflow/Input/Node/Output semantics;
- changing four-role topology, Acceptance lifecycle/verdict logic, PlatformScope, Broker, SSE/model
  settlement, foreground display binding, source corpus, competency questions or expected answers;
- reusing start4 or any R2.3-002 Project/Ontology, mutating retained evidence, concurrent semantic
  runs, or automatically spending all three authorized starts.

## Completion checks

- C84-C93 and I17-I18 PASS with unchanged live ledgers and retained start4 evidence.
- The proof-gated R2.3-002 path remains byte/behavior compatible while non-gated R2.3-005 reaches
  the Protocol translation receipt bound to its Runtime-generated synthetic fresh scope in the
  no-start smoke; prior/caller scope identities are rejected.
- Only then may I19 begin. R2.3-005 remains incomplete until the real run reaches independent
  Acceptance and its full semantic/retrieval completion rule.
