# R4.0-014 controlled round-2 and recovery progress handoff

Run: `r4014-controlled-20261003`

Candidate message for Coordinator through the existing handoff channel. This message uses the
published full r2 candidate and the approved recovery input. It does not change the shared map,
call the platform, or alter the previously delivered `modeling-handoff.md`.

```text
to: Coordinator
kind: progress-handoff
run: r4014-controlled-20261003
phase: round-2-and-recovery

scope: flow
slice_id: flow
affected_viewpoints: [process, rule]
current_candidate:
  artifact_path: workspaces/r4014-controlled-20261003/flow-r2.json
  candidate_id: flow-candidate
  revision: 2
  key_item_ids: [rule-unknown]
  expressed_scope: rule-unknown still expresses the unresolved compensation trigger;
    there is no current main-process expression in this full revision.
  analyzed_scope: the compensation path remains unmodeled; r1's main-flow expression
    was the sole process expression and is not retained as current content.
  remaining_work: author a complete current process expression; obtain business-owner
    confirmation before asserting the compensation trigger's meaning.
  true_business_unknowns: [Compensation trigger needs business owner confirmation]
  current_status: process pending; rule-unknown modeled but unconfirmed.
  old_expression: flow-r1.json / flow-candidate revision 1 / main-flow is replaced
    as the current process expression. rule-unknown survives unchanged.
  approval_state: no new approval or application; no independent semantic PASS.
next: Modeling authors the next complete current candidate, while the business owner
resolves the trigger. Coordinator checks this actual r2 content and updates only the
affected flow progress.

scope: other
slice_id: other
affected_viewpoints: [object]
current_candidate:
  artifact_path: workspaces/r4014-controlled-20261003/object-r1.json
  candidate_id: object-candidate
  revision: 1
  key_item_ids: [object-a]
  expressed_scope: object-a remains the current object expression and is unaffected by
    the flow revision.
  analyzed_scope: shared-a remains proposed only; the approved input supplies no
    business confirmation. This unconfirmed proposal alone is not a business unknown.
  remaining_work: preserve this unrelated scope; seek confirmation only if a later
    business decision requires it.
  true_business_unknowns: none supplied for this scope.
  current_status: modeled.
next: Coordinator preserves object-a and does not reset the other scope.

recovery_boundary:
  source_history: Host reconciled source Batch source-b / Attempt source-a /
    receipt source-receipt as definite success for source main-flow r1.
  current_position: this is source history only and does not prove that flow-r2 was
    applied. It is an evidence/state gap, not a business semantic conclusion.
  source_write_rule: do not replay the definite source write; restore/reconcile the
    current candidates, checkpoint/scope mapping and identity mapping before next work.
  fork: the fork is a NEW project with identity_mapping object-a -> new-object-a.
    No approved new translation or apply plan exists.
  immutable_records: do not modify any immutable saved map or handoff to repair stale
    progress; retain r1 receipt history as history only.
next_recovery_owner: Delivery/Coordinator restores the writable current working copy
and verifies reconciliation. Modeling resumes only from the restored current candidates
and an approved next input; no platform call is made by this role.
```

