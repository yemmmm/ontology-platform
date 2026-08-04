# R2.3-005 Complete Candidate Revision Repair Plan

## Outcome

Prevent a repeat of start5's final collaboration failure by making every Modeling candidate revision
a complete, self-contained immutable candidate. A revision must carry forward every unchanged item,
citation, constraint and query; it may replace explicitly named content, but it must never send a
cross-delivery patch or require Protocol to reconstruct prior deliveries. After deterministic and
independent PASS, use exactly one reviewed repair authorization and one fresh start6. This plan does
not append the repair or consume a semantic start.

## Retained evidence and classification

- Start5 `r23005-real-20260804t065900z-start5` proved the repaired Modeling-neutral -> Protocol
  handoff. Revisions 1-5 progressively narrowed pre-write conflicts without platform calls.
- Revision 6 (`delivery-18`) carried only `shape:ExplicitUnknown`, five constraints and three
  citations, while referencing revision 5 and asking to preserve all other items byte-for-byte.
  It omitted revision 5's other 37 items and full citations/queries.
- Protocol `delivery-19` correctly rejected the partial patch because deterministic translation may
  not reconstruct or mutate an immutable candidate across deliveries. No dry-run, apply, readback,
  validation, reasoning or Acceptance result existed.
- The retained terminal is therefore `collaboration/routing`,
  `complete_modeling_quality_result=false`. Cleanup deleted the fresh Project/Ontology empty and
  left zero resource/process residue. The ledger is cap/count/active `7/5/0`; start6 has not been
  repaired, reserved or started.

## Current minimal scope

1. Add one explicit rule to Modeling instructions: every candidate revision is a complete,
   self-contained candidate; include all prior unchanged items/citations/constraints/queries exactly,
   include explicit replacements in place, and never send `revision_basis`, `revision_operation`,
   `replace_item_id` or another patch instruction as a substitute for the full candidate.
2. Mirror the receiving rule in Protocol instructions and the R2.3-005 task: Protocol never merges
   candidate history, and runs `build_candidate_receipt` against the entire current candidate before
   every receipt or conflict response.
3. Add a production-shaped retained regression using start5 revision 5/6 shapes. The partial revision
   must be rejected as incomplete without cross-delivery reconstruction; the full revision 5 content
   with the one explicit Shape correction must retain all 38 items/full metadata and reach the normal
   neutral receipt path.
4. Add static prompt/task projection checks proving Modeling sees complete-revision/no-patch wording,
   Protocol sees no-merge/receipt-every-revision wording, and accepted proof-bound R2.3-002 plus
   non-proof R2.3-005 gates remain unchanged.
5. Run focused cases C94-C98, all R2.3-005 tests, complete `modeling_team` discovery, Ruff,
   compile, `git diff --check`, GitNexus `detect_changes(compare main)`, and before/after live-ledger/
   retained-start5 immutability checks. No Agent Runtime, smoke rerun, platform call, resource creation
   or ledger mutation is permitted during implementation/testing.

## Sequencing

1. Main records start5 and freezes this plan/test delta.
2. Plan Reviewer checks that the repair is prompt/contract-only and executable.
3. Requirement Developer changes only Modeling/Protocol instructions, R2.3-005 task and focused
   tests. Runner already projects the task objective, so no Runner behavior change is needed. No
   mechanics, Runtime, Acceptance, PlatformScope, Broker or ledger product code change.
4. Independent Requirement Tester records a new round in the existing shared plan.
5. After commit and independent PASS, Delivery computes one fresh start6 baseline, appends exactly one
   repair authorization for start5 under the canonical R2.3-005 lock, then one reservation and one
   semantic start. No budget event is added; readback must move from `7/5/0` to start6 only.

Stop at the first complete PASS. If start6 has a retryable incomplete failure, cleanup and stop before
any start7 repair/start. One authorized slot would remain, but it may be used only after another
evidence-backed narrow review. If cap 7 is eventually consumed, return to the user for authorization.

## Excluded

- candidate history storage, patch merge/reconstruction or a revision state machine;
- changing neutral/proof-v2 mechanics validation, Batch/platform contracts or proof gates;
- another no-semantic-start Runtime smoke, new harness or new business slice;
- Runner behavior, Acceptance/lifecycle/settlement, PlatformScope, backend, frontend,
  productization or UI changes;
- automatic start6/start7, concurrent runs, prior-scope reuse or retained-evidence mutation.
