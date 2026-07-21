# R1.1-006 轻量共享建模目录共享测试计划

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-006
- Design: `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`
- Delivery record: `docs/delivery/records/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-delivery-record.md`
- Status: plan review PASS; implementation pending

## Completion gates

1. Plan review reports no unresolved Critical/High issue that can reduce modeling or retrieval quality.
2. Directory initializer/validator focused tests pass.
3. Two fresh Agent sessions complete separate Ontology Work Units using only run path and unit ID.
4. One session replacement resumes from files without original chat.
5. Merged candidates, Ontology reviews, Batch plans, and submitted payloads have matching canonical
   content hashes.
6. A candidate above the live single-Batch capacity completes deterministic multi-Batch
   dry-run/apply.
7. Applied results pass the scenario's competency-question and semantic-retrieval acceptance.

## Focused scenarios

- Initialize one run and inspect every required shared/unit file.
- Reject missing brief, source index, coverage, task, dependency, or malformed JSON with an
  actionable error; never continue by guessing.
- Validate the minimum contracts for `run.json`, source index, coverage, task, and result. Reject a
  missing or cross-scope Source, Coverage item, competency question, dependency, input path,
  Ontology, or output-contract reference even when every file is valid JSON.
- Change one referenced source/task input and prove its fingerprint invalidates only affected ready
  results.
- Prove canonical JSON and input-fingerprint hashes are identical across repeated runs and object-key
  order, while a semantic content or referenced-byte change changes the expected hash.
- Run two different-Ontology units concurrently and prove they write only their assigned directories.
- Keep a dependent unit blocked until its direct dependency is ready.
- Replace a stopped worker with a fresh session and complete from the same files.
- Modify one task or prompt and rerun only that unit; unrelated ready results remain usable.
- Detect duplicate identifiers, conflicting shared terminology, unresolved references, and result
  schema errors before platform dry-run.
- Merge one Ontology into `candidate.json`; prove review and Batch plan bind its canonical hash and
  that a semantic edit makes the previous review unusable.
- Build a representative candidate with more items than the active `modeling_batch_max_items`
  setting, including at least 200 `create_entity` items and representative `create_relation` items.
  Prove deterministic topological partitioning, every serialized request below both live item and
  byte limits, ordered dry-run/apply, and Modeling Context refresh between dependent Batches.
- Review the merged Ontology model, complete multi-Batch dry-run/apply, then run the predefined
  retrieval questions and record returned resources, relations, evidence, and explicit gaps.

## Explicitly untested future features

Cross-machine synchronization, hostile local writers, fine-grained authorization, immutable version
history, audit export, dynamic claims, TTL/fencing, crash-safe distributed recovery, UI, retention,
and generic scheduling are outside the current completion gate.

## Required repository checks

- Focused tests for the repo-local initializer/validator once implemented.
- `python skills/ontology-builder/evals/validate_skill.py` if the Skill changes.
- `git diff --check` and scoped `git status --short`.
- No backend/frontend change means no service restart; otherwise follow `AGENTS.md` in full.

## Independent test rounds

No implementation has been handed to an independent tester yet.
