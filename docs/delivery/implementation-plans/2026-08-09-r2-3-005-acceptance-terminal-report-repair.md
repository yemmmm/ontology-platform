# R2.3-005 Acceptance Terminal Report Repair Plan

## Observed live failure

Start71 reached the final semantic boundary on clean commit `b3ac7ca`: both ordered CQs were `PASS`, all four
Examiner children were recycled without infrastructure failure, and `acceptance-settlement.jsonl` recorded a matched
final readback and `status=settled`. Acceptance then sent delivery-9 to Coordinator saying the rounds were complete,
but ended its turn without calling Team Transport `report_task_result`. Because the formal dependency graph now
correctly starts with `acceptance -> modeling -> protocol -> coordinator`, no source terminal result existed to emit
the first terminal handoff. The run was stopped, cleaned, and ledgered `collaboration/routing,false`.

The cause is an authoritative prompt conflict. The shared package says to return a verdict to Coordinator and wait
for the next ticket or settlement instruction. The formal Acceptance branch of `TeamRunner._task_text` replaces the
generic task text and omits the generic `call report_task_result exactly once before ending` rule. The loaded Task's
initial instruction says to report completion to Coordinator, which the Agent satisfied with an ordinary delivery.

## Current minimal scope

1. In the Acceptance package and formal Acceptance task text, distinguish ordinary Coordinator delivery from the
   terminal tool. After non-final cq-001 PASS, FAIL, or BLOCKED, Acceptance remains live and must not report terminal.
   After final cq-002 usable PASS has been submitted and routed, Acceptance must call Team Transport
   `report_task_result(status=completed, ...)` exactly once before ending; an ordinary completion delivery does not
   substitute for it.
2. Remove the settlement race mechanically. Add one Runner-owned lock around the only settlement finalization method.
   Both foreground `drain` and the formal Acceptance terminal guard use that same serialized, idempotent method; it
   rechecks `is_settled` and `settlement_ready()` only after acquiring the lock. When the formal Acceptance terminal
   guard is evaluated with `status=completed`, it invokes that boundary before checking `acceptance.is_settled`.
   This does not fabricate a verdict or terminal result: settlement still requires exactly two same-state usable PASS
   verdicts, complete child recycle, current model-state revalidation, CAS, and final readback. If those prerequisites
   are absent, the report remains rejected and no dependency handoff is emitted. Concurrent drain/report paths must
   produce exactly one CAS artifact, one settlement artifact, and one Runner settlement evidence record; the later
   observer returns the same settled outcome rather than attempting an immutable rewrite.
3. For the formal Acceptance role, the terminal guard accepts only `status=completed`, and only after successful
   settlement. It rejects `blocked` (and every other non-completed status) even when the carrier is already settled;
   no terminal result or dependency handoff is created. FAIL/BLOCKED verdict paths therefore remain non-terminal and
   available for revision.
4. Preserve the reviewed formal-only dependency graph from commit `b3ac7ca`. No new dependency, lifecycle state,
   capability, automatic Agent report, or semantic decision is introduced. Non-formal terminal behavior is unchanged.

## Tests

- Prompt-contract tests load the real formal Acceptance task text and package instructions, proving cq-001/non-PASS
  paths stay live, final cq-002 usable PASS requires exactly one terminal tool call, and an ordinary Coordinator
  delivery is explicitly insufficient.
- Guard tests prove an Acceptance `completed` report presented after the second complete PASS but before the foreground
  drain's normal settlement call triggers the existing settlement exactly once and is accepted; incomplete, FAIL,
  BLOCKED, stale-state, child-residue, and settled-plus-`blocked` cases remain rejected without a terminal result or
  handoff.
- A true two-thread regression synchronizes foreground finalization and Acceptance terminal-guard evaluation at the
  settlement boundary, then asserts both complete without an immutable-write error, the completed report is accepted,
  the Modeling handoff is emitted once, and exactly one settlement CAS/artifact/evidence record exists.
- Actual `TeamRunner.prepare/start` integration verifies the full formal terminal chain: Acceptance result creates the
  Modeling handoff, Modeling result creates Protocol handoff, Protocol result creates Coordinator handoff, and all
  four results settle in order. Non-formal graph compatibility remains covered.
- Run focused tests, all R2.3-005 discovery, complete `modeling_team/tests`, full modeling-team Ruff,
  `git diff --check`, GitNexus change detection, service restart, backend health, and frontend HTTP 200.

## Delivery boundary

No semantic start is available or permitted: start69–start71 exhausted the user's exact three-start authorization.
This repair may reach deterministic implementation PASS only. A further real start requires new explicit user
authorization and must begin from a clean committed baseline. Start71's double-CQ PASS and settlement remain valid
partial evidence but do not satisfy the four-role terminal/Team settlement completion gate.

## Result

Implemented and independently verified in Round 12. Focused 7/7, R2.3-005 176/176 with one opt-in skip, complete
modeling-team 493/493 with one opt-in skip, modeling-team Ruff/diff/GitNexus, service restart, backend health, and
frontend HTTP 200 passed. No semantic start was performed; live completion remains authorization-gated.
