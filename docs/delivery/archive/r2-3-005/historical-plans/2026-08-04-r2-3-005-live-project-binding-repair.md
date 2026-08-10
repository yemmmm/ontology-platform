# R2.3-005 Live Project-Binding Repair Plan

## Outcome

Repair the deterministic owner-question routing failure observed by live run
`r23005-real-20260804t021921z-retry2`. Formal create-mode coordination must bind every outer question
and owner answer to the Project ID created by the live `PlatformScope`, while preserving historical
non-formal behavior and all source-fidelity rules. This plan does not launch another semantic start.

## Direct evidence and classification

- The run recorded `delivery-1` from Modeling to Coordinator with `expects_reply=true`, then exited
  with `outer question project binding is missing` before any owner answer was sent.
- `normalize_formal_scope()` intentionally reduces the input to `{"mode":"create"}`. The created
  Project/Ontology IDs live on `TeamRunner.scope`; they are not copied into `TeamRun.scope`.
- `_observe_modeling_question()` and three later owner-question/answer paths read
  `self.run.scope["project_id"]`. This is the exact production-shape mismatch.
- The failure is `collaboration/routing` with `complete_modeling_quality_result=false`. The run
  consumed semantic start two, produced no modeling-quality result, and cleaned to zero residue.
  Formal cap/count/active is now `4/2/0`; two authorized starts remain.

## Frozen implementation scope

1. Add one private `TeamRunner` helper that resolves the current Project binding. Its branch
   predicate must be the existing `_formal_coordination_enabled()` contract, not
   `schema_version == 2`: formal coordination accepts only a non-empty live
   `self.scope.project_id` and fails closed without fallback; every non-formal path, including
   historical schema-v2 R2.3-002 fixtures, retains its existing `TeamRun.scope` lookup. The helper
   must not copy or inject generated IDs into normalized `TeamRun.scope`.
2. Use that helper consistently in `_observe_modeling_question`,
   `_resolve_formal_owner_question`, `_record_outer_question`, and `_release_owner_answer`.
   Non-formal/historical paths retain their existing `TeamRun.scope` lookup unless a reviewed test
   proves that path already owns a live PlatformScope binding.
3. Preserve delivery identity, run/project drift checks, immutable question records, displayed and
   consumed gates, exact nine-field owner record, authorization/release identity, duplicate/replay
   rejection, and the repaired schema-v2 user envelope. Do not alter business question text or
   inject the user's `未知` answer.
4. Update the small owner-answer fixture to the production data shape:
   `run.scope={"mode":"create"}` and a separate live scope object with `project_id`. This unit
   fixture is not sufficient acceptance by itself.
5. Add a deterministic integration regression that actually executes formal `TeamRunner.prepare()`
   through `normalize_formal_scope`, then `start()` with a non-network scope factory/test double whose
   `PlatformScope.prepare({"mode":"create"})` creates the live Project/Ontology binding. Drive the
   first Modeling -> Coordinator reply-request through `drain()` without a model call and prove:
   `run.scope` remains exactly `{"mode":"create"}`; the generated live Project ID is used in
   outer-question and outer-user identity/evidence; no caller-supplied ID is accepted; and cleanup
   leaves no test-double resource. Do not replace this chain with direct private-helper calls.
6. Add remaining deterministic regression cases for:
   - `drain()` observing the first Modeling -> Coordinator reply request with a live Project ID;
   - missing live Project binding failing before outer-question/owner evidence mutation;
   - displayed question -> text-only user envelope -> exact Modeling owner-answer delivery;
   - project/run/origin drift, duplicate/replay, and non-formal compatibility, including a
     schema-v2 non-formal R2.3-002 case that must continue reading `TeamRun.scope`.
7. Run the focused owner-answer/Runner suites, all R2.3-005 tests, full managed `modeling_team`
   discovery, Ruff, `git diff --check`, GitNexus `detect_changes(compare main)`, and before/after
   live-ledger plus retained-evidence snapshots. No real Agent or semantic start is permitted.

## Post-fix Delivery gate

Only after a reviewed commit and independent PASS may Delivery, under the R2.3-005 ledger lock, run
the explicit sequence:

1. append `terminal_failure(run_id=r23005-real-20260804t021921z-retry2,
   classification=collaboration/routing, complete_modeling_quality_result=false)`;
2. choose a fresh retry3 run ID, complete the no-start gates, and preview its exact baseline;
3. append `repair_authorization(failed_run_id=retry2, baseline_hash=<fresh retry3 baseline>,
   repair_reference=<reviewed commit and independent PASS>)`.

Both CLI calls must specify `--requirement-id R2.3-005`; no budget event is allowed. Read back exact
event/run/baseline order, cap/count/active `4/2/0`, and the unchanged legacy hash before any
reservation. The next run remains serialized and, if started, will be semantic start three with one
further authorized start remaining.

## Excluded

- changing formal scope normalization or permitting caller-supplied Project/Ontology IDs;
- platform/backend schema, APIs, storage, security, UI or productization work;
- changing business sources, the grounded question, expected answers or semantic acceptance;
- direct ledger edits, reuse of retry2 resources, concurrent runs, or automatic use of both
  remaining starts.
