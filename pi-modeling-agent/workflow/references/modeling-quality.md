# Modeling Quality References

Shared quality gates every role applies. Domain-specific names (for example Dify Workflow or Node)
appear only in tracked scenarios and test assertions; production code and prompts operate on generic
modeled resources.

## Source fidelity

- Every proposed entity, property, relation, and value must trace to cited source coverage.
- Unsupported invention is a blocking Finding. Missing important-item Evidence is a blocking Finding.
- Never invent facts to satisfy a competency question; mark an explicit gap instead.

## Coverage

- Coverage partitions the business scope into Work Units with exact dependencies.
- Silent Coverage loss is a failure: a Work Unit result that drops covered facts cannot merge.
- A stale input fingerprint blocks merge until the affected unit is rerun or a bounded `no_change`
  assessment satisfies the existing contract.

## Candidate hash and review binding

- Same-Ontology Work Unit results merge into one candidate before review.
- The candidate hash is bound to the review; a mismatched hash is rejected before content review.
- Independent review returns exactly `PASS | REVISE | BLOCKED` with bounded findings and affected
  locators. `REVISE`/`BLOCKED` requires regeneration, merge, review, and dry-run before apply.

## Evidence, dry-run, apply

- Blocking dry-run Findings map back to affected Work Units; they are never waived in the Runtime.
- Apply reuses one `client_batch_id` across dry-run/apply with immutable content fixed; new attempt
  and idempotency identities are used where the platform contract requires them.
- Unknown apply outcomes reconcile the original Batch/attempt/idempotency identity; a replacement
  Batch is never created to guess a result.
- Later Batch failure retains the valid applied prefix; final verification cannot PASS until the
  remaining plan succeeds.

## Verification

- CQ, semantic retrieval, and provenance must pass on the applied model. A failed CQ blocks
  verification and maps back for repair; it is never recorded as PASS without an observed result.
- Qualitative assertions are not presented as platform-executed CQ results.
