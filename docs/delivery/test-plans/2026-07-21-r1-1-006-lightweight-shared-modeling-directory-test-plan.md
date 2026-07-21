# R1.1-006 轻量共享建模目录共享测试计划

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-006
- Downstream contract: `docs/requirements/requirements-v1.1.md` R1.1-007
- Design: `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`
- Delivery record: `docs/delivery/records/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-delivery-record.md`
- Status: delivered; independent test Round 2 PASS

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

### Independent test Round 1 — 2026-07-22

Result: **FAIL**. The real collaboration and platform path passed, but verification completeness
has one confirmed High defect, so R1.1-006 cannot close yet.

Stable input under test:

- baseline commit `c8f3495`;
- `.codex/shared_modeling_directory.py`
  `86a3b612b047cba8df4954ed12402d0d8865986dac765e7f8e0371a5a25fb1f6`;
- `.codex/tests/test_shared_modeling_directory.py`
  `1b02a4bed1c2baae8d15817afe61806d6f9c5b51c62d52e0d569c84776e20597`;
- `.codex/shared-modeling-directory.md`
  `d686521d432598678430db3226d5efb223525d0098586f0263d1af89e3aff044`.

Executed evidence:

- Focused Shared Modeling Directory suite: `13 tests`, all passed. It covered initialization,
  missing/cross-scope references, secret/source-body/mailbox rejection, direct dependencies,
  disjoint writers, stale-input blocking, explicit semantic `no_change`, hash/review gates,
  duplicate/conflict/unresolved references, deterministic item/Evidence/byte partitioning,
  overlong excerpt and unsplittable request rejection, Batch-local reference materialization,
  dry-run/apply platform identity mismatch rejection, 205-item simulated binding, and complete-CQ
  verification requirements.
- Full `.codex` regression command
  `backend/.venv/bin/python -m unittest discover -s .codex/tests -p 'test_*.py' -v`:
  `81 tests`, all passed.
- Ruff command
  `backend/.venv/bin/ruff check .codex/shared_modeling_directory.py
  .codex/tests/test_shared_modeling_directory.py`: passed.
- Two different-Ontology Agent units used only one run path plus `work_unit_id` as dynamic
  business handoff. `start-unit` completed in one fresh Session. A second Session left `llm-unit`
  at `working` with no result; a third, genuinely fresh Session observed that state and completed
  it to `ready` from the directory alone. The run validated with zero errors/warnings and both
  candidates merged. No Agent wrote outside its assigned unit directory.
- Independent Ontology review first caught and blocked a non-verbatim Evidence excerpt before
  planning. After the acceptance fixture was corrected, the final review independently verified
  exact source text/hash, live platform Competency Question ownership, candidate hash
  `5e21bbc26be0a5f196187351b1858fa68b72bc4365e1180a1e6b4ce41395ab14`, 205 unique items
  (`200 create_entity`, one class, one relation type, three relations), all 211 item references,
  dependencies, CQ bindings, and zero gaps; verdict `PASS`.
- The real authenticated platform run temporarily used the required `rdf_primary` product-write
  mode because the restored local default `legacy_only` deterministically rejects canonical
  Modeling Batch validation. The reviewed candidate split to `[100, 100, 5]` using the live limits
  `100 items / 1,048,576 bytes / 100 inline Evidence / 20,000 excerpt chars`.
- All three real Batches reused their planned `client_batch_id` between dry-run/apply and returned
  the same platform Batch ID. Their immutable hashes were respectively
  `639149667c94db24148d449debcc2508549f19dbf256b5f0a2a60c2f4a75db4f`,
  `c74b23d9a741a048d6b0d1b0085098d81a5dda3abde0aaf1bab4ffe0086a197b`, and
  `11617128ad516cd7d570ef94b74fe94ffa3e3a18b825487cb9634e2a53e42e2e`.
  Actual dry-run/apply request sizes were `47,003/47,070`, `46,638/46,705`, and
  `3,002/3,069` bytes. Submitted payload inspection found zero cross-Batch item refs or
  `depends_on`; later materialization used applied predecessor resource identities after a real
  Modeling Context refresh.
- Before applying Batch 2, an apply using the pre-Batch-1 workspace version returned HTTP `409`
  `workspace_revision_conflict`. Scoped SPARQL still counted `99` already applied entities,
  proving the valid prefix remained and no rollback was claimed. The driver refreshed current
  Modeling Context, retried the same reviewed Batch content with the current version, and completed
  all Batches.
- Final scoped SPARQL returned exactly `200` entities and `3` representative relations. Lexical
  Context Query returned `matched` with `20` primary matches for the unique Node 199 label. The
  original evidence-bearing verification file passed and the complete directory validated with
  zero errors/warnings.

Confirmed defect:

- **High — R1.1-006-IT-001: verification PASS does not require executed-query/result evidence.**
  Replacing the successful check with only
  `{"competency_question_id": <current-id>, "status": "passed"}`—no `query`, no
  `returned_resources`, and therefore no observable retrieval result—still made
  `validate_verification(...)` return `PASS`. The original file was restored and revalidated.
  This contradicts the requirement that file completeness cannot substitute for competency-
  question/retrieval acceptance and can falsely close an unexecuted verification. The validator
  must require bounded evidence of an executed check (at minimum a non-empty query/check
  description and structured returned result or an explicit, contract-valid empty-result
  assertion) before accepting `status=passed`/`verdict=PASS`, with focused regressions for missing,
  malformed, and valid evidence.

Cleanup and runtime restoration:

- Each failed acceptance-fixture attempt stopped before apply or at dry-run and deleted its unique
  Project; the final real run also deleted its unique Project after verification. PostgreSQL checks
  returned zero Project and Modeling Batch rows for every cleaned run. Four uniquely indexed
  workspace graphs per run were explicitly dropped and graph-existence checks returned zero
  residual graphs.
- The temporary systemd manager override was removed and the service restarted back to
  `legacy_only`. `ontology-platform.service` is active; backend `/api/health` is `200` with
  `{"status":"ok"}` and frontend `/` is `200`.
- No credential value was printed or written into a shared run. Gitignored local acceptance
  directories remain only as bounded test evidence and can be removed after the repair round.

Unexecuted or residual cases:

- No real worker happened to need business clarification; focused tests prove mailbox/reasoning
  files are rejected, but an actual Runtime clarification return was not forced.
- R1.1-007 Profile, Harness, credential loader, automatic Build Session/Lease/submission adapter,
  and capability Skills remain intentionally downstream and untested here.
- The independently found High defect is the only completion blocker from this round; all other
  executed acceptance, boundary, recovery, cleanup, regression, and runtime checks passed.

### Independent test Round 2 — 2026-07-22

Result: **PASS**. R1.1-006-IT-001 is fixed, no new Critical/High defect was found, and the preserved
Round 1 real-platform acceptance remains valid under the repaired verification contract.

Stable repair input under test:

- `.codex/shared_modeling_directory.py`
  `7a37bdb9148f0c8bece2af3886f2e6a612643e6fad7d4fd3bddce97b5ef63fa1`;
- `.codex/tests/test_shared_modeling_directory.py`
  `e43f72929c01e2cfe831f4c7ea7d5a4f94d86b3dd7dee95f82e6fbbcb6a058a3`;
- `.codex/shared-modeling-directory.md`
  `1f063db211379f524dc18ac78d68f24035fb89cd422bb70f495550b2689e1c2d`.

Defect retest and contract matrix:

- The exact Round 1 failure—one `passed` check containing only
  `competency_question_id` and no query/result evidence—now fails with
  `lacks an executed query/check description`.
- A non-empty query without any structured observed result fails with
  `lacks structured result evidence`.
- A scalar/object `returned_resources` value fails with
  `must be a structured result list`.
- The preserved real Round 1 check, containing a non-empty executed-query description and
  non-empty returned-resource list, passes.
- An expected-empty check containing a non-empty `check_description`, an empty structured result
  list, and `empty_result={expected: true, observed_count: 0, assertion: ...}` passes.
- The same explicit-empty check with `observed_count=1` fails with
  `empty_result must assert expected=true and observed_count=0`.
- The original preserved live verification file was restored after the mutations and independently
  revalidated as `PASS`.

Regression and static checks:

- Focused command
  `backend/.venv/bin/python .codex/tests/test_shared_modeling_directory.py -v`:
  `13 tests`, all passed. The verification test now covers the missing-description,
  missing-result, malformed-result, valid non-empty, valid explicit-empty, malformed explicit-empty,
  and missing-CQ cases while retaining all Round 1 planner/materialization/hash regressions.
- Full command
  `backend/.venv/bin/python -m unittest discover -s .codex/tests -p 'test_*.py' -v`:
  `81 tests`, all passed.
- `backend/.venv/bin/ruff check .codex/shared_modeling_directory.py
  .codex/tests/test_shared_modeling_directory.py`: passed.
- `git diff --check`: passed.

Real-platform evidence disposition:

- The repair adds bounded passed-check evidence validation and its tests/runbook contract; it does
  not change candidate hashing, review gates, capacity planning, materialization, response binding,
  cross-Batch reference resolution, or platform submission semantics. Focused and full regressions
  for those paths passed.
- Therefore the expensive 205-item platform apply was not repeated. Round 1's independently
  reviewed `[100, 100, 5]` real dry-run/apply, immutable identities, later-Batch failure and
  forward recovery, exact `200` Entity/`3` Relation SPARQL result, and matched Context Query are
  carried forward as unaffected evidence. The resulting live `verification.json` now also passes
  the stricter repaired validator, directly connecting that evidence to the repair.

Cleanup and runtime health:

- All four preserved `r11006-live*` run identities were rechecked. Each has zero PostgreSQL Project
  rows, zero Modeling Batch rows, and zero RDF named graphs containing its unique Ontology ID.
- `ontology-platform.service` is active. Backend `/api/health` is `200` with `{"status":"ok"}`;
  frontend `/` is `200`.
- Authenticated canonical-mode inspection returns `200` and `product_write_mode=legacy_only`.
  The temporary Round 1 systemd manager override remains absent.
- No cleanup or new real-platform writes were needed in Round 2; the gitignored Round 1 directory
  remains only as bounded local evidence.

Residual risks and unexecuted cases:

- The real worker clarification-return scenario remains unforced; mailbox/reasoning-file rejection
  is covered by focused tests. This does not contradict a completion criterion because no worker in
  the accepted run needed clarification.
- R1.1-007 Profile/Harness/credential-loader/automatic Adapter and capability-Skill behavior remains
  intentionally downstream.
- No residual Critical/High risk or unexecuted R1.1-006 completion gate remains after this round.
