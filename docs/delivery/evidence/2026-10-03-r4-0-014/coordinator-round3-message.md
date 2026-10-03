# Coordinator round 3 artifact-gap and recovery handoff

Run: `r4014-controlled-20261003`

I processed the artifact-gap supplement against the current writable r2 copy. `flow-r2.json` revision 2 remains the current flow candidate, with `rule-unknown` as its only item; r1 `main-flow` remains historical. `object-r1.json` / `object-a` remains current and unrelated. The claimed `oral-r1.json` is still absent. A missing or unverified artifact is a progress/evidence gap, not a business unknown, so `oral/process` remains `pending` and the gap is recorded in its note rather than in `explicit_unknowns`. This controlled handoff performs no platform call, real checkpoint, approval, application, semantic start, or independent semantic PASS.

## Immediate next actions

1. Teammate/Coordinator supplies the exact claimed `oral-r1.json` artifact. Coordinator checks its actual content, candidate ID, revision and item IDs before changing `oral/process`. Until then, retain `pending` and do not promote the oral claim.
2. Modeling continues from the current r2 candidate: author a complete current process expression, preserve `rule-unknown`, and wait for business-owner confirmation before asserting the compensation trigger meaning. The separate blocked slice still waits for its actual trigger fact; no candidate is invented.
3. Delivery/Coordinator restores the writable production recovery copy only after checking the actual recovery scope, any supplied checkpoint state, write reconciliation and current candidates. The host-reconciled source Batch `source-b` / Attempt `source-a` / receipt `source-receipt` prove only the source r1 `main-flow` write; do not replay it and do not treat it as proof that r2 was applied. The fork remains a new project with identity mapping `object-a -> new-object-a`, with no approved new translation or apply plan.

## Save, final synchronization and stale binding order

- Planned save: first check the available current candidate and execution facts, then synchronize the writable map. Keep `pending`, `unknown`, and missing-artifact notes explicit; do not wait for perfect progress and do not treat a save as approval or application.
- Emergency stop/save: preserve the actual current candidates and map immediately, including the oral artifact gap and genuine business unknowns. Request exact missing paths/revisions later. Do not reconstruct candidates or overwrite the r1/r2 maps, source handoff, or any immutable record.
- Normal final synchronization: Coordinator checks final candidate and execution facts, synchronizes the map, and reports the production terminal. The Host then verifies production quiescence and write draining, publishes the existing handoff, and binds the map digest. Coordinator does not publish or bind that Host handoff. Map writes must finish before the terminal report.
- After digest binding: keep the bound map, checkpoint, and report immutable. If progress is discovered stale, tell the Host the discrepancy outside business evidence; do not repair the bound artifact in place.
- Bound-map stale recovery: update only a writable recovery copy after checking checkpoint/scope state, write state, identity mapping and actual current candidates. Reconcile definite writes without replay; reconcile unknown writes through the existing recovery path. Modeling resumes only from the restored current candidates and an approved next input.

The round-3 writable map is [coordinator-round3-map.json](coordinator-round3-map.json). The r1/r2 outputs, source `scenario-map.json`, and original handoffs remain untouched.
