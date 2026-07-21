# R1.1-006 轻量共享建模目录共享测试计划

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-006
- Downstream contract: `docs/requirements/requirements-v1.1.md` R1.1-007
- Design: `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`
- Delivery record: `docs/delivery/records/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-delivery-record.md`
- Status: realigned with R1.1-007; independent plan re-review PASS; implementation pending

## Completion gates

1. A new plan review reports no unresolved Critical/High issue after the R1.1-007 realignment.
2. Directory initializer/validator/merge/planner focused tests pass.
3. Two fresh Agent sessions complete separate Ontology Work Units using only run path and unit ID.
4. One session replacement resumes from files without original chat.
5. Stale inputs cannot enter merge without a rerun or explicit semantic `no_change` resolution.
6. Merged candidates, Ontology reviews, logical Batch plans, and submitted payloads have matching
   candidate/materialized immutable-content hashes; dry-run/apply reuse the planned
   `client_batch_id` and return the same platform `batch_id`.
7. A candidate above the live single-Batch capacity completes deterministic multi-Batch
   dry-run/apply without cross-Batch item references in submitted payloads.
8. Applied results pass the scenario's competency-question and semantic-retrieval acceptance.
9. Tests prove R1.1-006 does not own Profile routing, Harness policy, credentials, platform write
   automation, clarification mailbox, Agent definitions, or capability Skills.

## Focused scenarios

- Initialize one run and inspect every required shared/unit/Ontology file and index entry.
- Reject missing brief, source index, coverage, task, dependency, or malformed JSON with an
  actionable error; never continue by guessing.
- Validate the minimum contracts for `run.json`, source index, coverage, task, status, result,
  candidate, review, Batch plan, and verification. Reject a missing or cross-scope Source, Coverage
  item, competency question, dependency, input path, Ontology, or output-contract reference even
  when every file is valid JSON.
- Prove the directory and diagnostics never require or persist an API key, Lease token, credential,
  full source body duplication, clarification mailbox, or hidden reasoning.
- Change one referenced source/task input and prove the validator blocks only affected ready results
  from merge. In the standalone 006 path, rerun that unit. Through the documented R1.1-007 seam,
  prove an explicit `no_change` resolution can rebind only when normalized semantic content is
  identical; `modify_existing`/`remodel` produces a new result.
- Prove a non-semantic rebind preserves the candidate hash and review/Batch-plan usability, while a
  semantic result change changes the candidate hash and invalidates both.
- Prove canonical JSON, input-fingerprint, candidate, and materialized semantic-request hashes are
  identical across repeated runs and object-key order, while relevant list order or semantic bytes
  change the expected hash.
- Run two different-Ontology units concurrently and prove they write only their assigned directories.
- Keep a dependent unit blocked until its direct dependency is ready.
- Have a worker request clarification and prove it stops/returns to the coordinating Runtime without
  writing a directory mailbox or guessing an answer.
- Replace a stopped worker with a fresh session and complete from the same files.
- Modify one task or prompt and rerun only that unit; unrelated ready results remain usable.
- Detect duplicate identifiers, conflicting shared terminology, unresolved references, and result
  schema errors before platform dry-run.
- Merge one Ontology into `candidate.json`; prove review and Batch plan bind its canonical hash and
  that a semantic edit makes the previous review unusable.
- Build a representative candidate with more items than the active `modeling_batch_max_items`
  setting, including at least 200 `create_entity` items and representative `create_relation` items.
  Prove deterministic topological partitioning and ordered execution.
- Prove item-output references and `depends_on` are Batch-local: materialize later Batch payloads
  only after predecessor apply returns stable resource IDs/IRIs and Modeling Context is refreshed;
  reject any submitted cross-Batch `client_item_id` reference.
- Serialize each real request before its first dry-run, deterministically split an unsubmitted
  partition that exceeds the live byte limit, and prove every submitted request stays below both
  live item and byte limits.
- Before first submission, assign each materialized Batch one stable `client_batch_id` and hash the
  platform-equivalent immutable content `{ontology_id, normalized items}`. Prove dry-run and apply
  reuse that `client_batch_id`, return the same platform `batch_id`, and preserve the immutable-
  content hash even though mode, workspace version, Lease token, idempotency key, and Attempt ID
  differ. Never mutate an already submitted immutable Batch.
- Exercise all current capacity contracts: item count, serialized request bytes, total inline-
  Evidence count, and per-excerpt character length. Prove excess inline-Evidence count causes
  deterministic partitioning, while one overlong excerpt or unsplittable Item blocks before
  submission with an actionable error.
- Inject a later-Batch failure after an earlier Batch applied. Prove the valid prefix is retained,
  recovery starts from platform current state, final acceptance waits for the complete plan, and no
  cross-Batch atomic rollback is claimed.
- Drive the existing authenticated platform interface with a thin acceptance driver or explicit
  coordinator calls, complete multi-Batch dry-run/apply, then run predefined retrieval questions
  and record returned resources, relations, evidence, and explicit gaps.
- Run initializer/validator/merge/planner tests without Harness or Profile routing, and state clearly
  that an eventual R1.1-007 Local run must separately obey its default Harness contract.

## Explicitly untested or downstream features

R1.1-007 Profile selection, continuous user-conversation orchestration, Harness activation/failure,
credential loading, Build Session/Lease/workspace/idempotency automation, capability Skills, Claude
Agent wiring, and Local/Formal adapters are downstream and not R1.1-006 completion gates.

Cross-machine synchronization, hostile local writers, fine-grained authorization, immutable version
history, audit export, dynamic claims, TTL/fencing, crash-safe distributed recovery, UI, retention,
and generic scheduling are future productization and also outside this completion gate.

## Required repository checks

- Focused tests for the repo-local initializer/validator/merge/planner once implemented.
- `python skills/ontology-builder/evals/validate_skill.py` only if the shared Skill changes; R1.1-006
  itself does not require such a change.
- Real platform integration evidence for authenticated multi-Batch dry-run/apply and retrieval.
- `git diff --check` and scoped `git status --short`.
- No backend/frontend change means no service restart; otherwise follow `AGENTS.md` in full.

## Independent test rounds

No implementation has been handed to an independent tester yet.
