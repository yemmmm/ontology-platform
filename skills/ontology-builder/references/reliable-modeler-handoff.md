# Reliable Codex modeler handoff

Use the repository-local `.codex/modeling_handoff.py` command whenever a Codex modeler produces the
seven-field `modeler-handoff.schema.json` result. PTY, chat, rollout text, and Harness events are not
payload transports.

The main Agent owns this sequence:

1. Recover platform facts first and choose the first missing safe step.
2. Prepare an explicit versioned input bundle with no platform credential or Lease token.
3. Run a fresh ephemeral Codex modeler through the controlled spool.
4. Inspect the bounded Manifest and fail closed on every conflict or validation error.
5. Perform platform-dependent Evidence, ownership, Modeling Context, and version checks.
6. Persist one immutable `modeling_draft` Artifact using `generation_id` as the client version.
7. Verify the platform canonical hash, mark the local generation persisted, and create/resume the
   exact Modeling Batch once.

The modeler writes no platform fact and receives no MCP write tool. The main Agent never repairs a
draft in place. Correction round 1 or 2 uses a new ephemeral context and gets the complete previous
draft plus structured failures. A repeated same-class failure or a third automatic correction is
blocked until an explicit user authorization is recorded.

After reviewer PASS, apply the immutable persisted Batch, not the modeler's dry-run envelope:
reuse its client batch ID, ontology ID, normalized items, item IDs, and content hash; create a new
apply Attempt/idempotency key, set `mode=apply_atomic`, read the current allowed workspace version,
and use only the main Agent's current Lease. Any content change requires a new immutable
draft/dry-run/review cycle.

Exact CLI syntax, recovery states, cleanup commands, and stable Event/Checkpoint mappings are in
`.codex/modeling-handoff.md`. If that repo-local command is absent, stop the large-draft workflow;
do not fall back to printing or reconstructing the full JSON.
