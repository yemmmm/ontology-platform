# R3.0-015 minimal real-runtime scenario

Purpose: exercise checkpoint recovery through actual model application and
`production_handoff`, followed by acceptance-only continuation after production exits.
This is L0 runtime evidence for an artificial two-concept scenario, not acceptance
of the industrial-service-v3 corpus or a general L1 modeling-quality claim.

The only business source is [scenario.md](modeling-input/scenario.md).
The Team task is [r3-0-015-minimal-flow.yaml](../../../modeling_team/tasks/r3-0-015-minimal-flow.yaml).
The [R3.0-015 test plan](../../delivery/test-plans/2026-09-14-r3-0-015-modeling-checkpoint-recovery-test-plan.md)
remains the shared acceptance record.

## Execution and evidence

1. Start an isolated Team run with a fresh platform scope and the existing CQ profile.
   Review and freeze CQ against this source through the normal authorized channel.
2. Publish source-grounded scenario and approved candidate artifacts; save the
   available scenario, CQ and semantic checkpoints through existing Runner actions.
3. Publish and review a complete bounded plan, including source evidence. Run the
   deterministic dry-run and retain its `materialization_progress` checkpoint.
4. Stop production safely. Resume that explicit checkpoint in a new run; reuse
   business decisions, review the new translation and dry-run against the new Session.
5. Apply the approved complete bounded plan, read back model/Evidence, and run the
   required validation, reasoning and authorized semantic retrieval. Publish a real
   production handoff only when these results satisfy the current contract.
6. After production exits, inspect the COMPLETE `production_handoff` checkpoint and
   continue in acceptance mode. Record whether it executed a new independent attempt
   or only verified an existing complete report; do not confuse those outcomes.

Use existing CLI/FIFO/checkpoint/acceptance paths. Do not manufacture candidate,
approval, receipt, handoff or acceptance artifacts outside their owning roles.
Preserve source runs and all failures. Record each fresh production start against
the current user authorization; acceptance-only continuation costs no modeling start.
CQ private questions and answers stay outside production-role inputs.

Success requires actual apply/readback evidence, a COMPLETE handoff package and a
settled independent acceptance continuation. A saved dry-run or clean process exit
alone is a partial result. Scope-external SQL/value/lifecycle unknowns are not
additional readiness requirements for this scenario.
