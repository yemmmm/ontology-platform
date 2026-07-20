# R1.1-003 Reliable Modeling Artifact Handoff Shared Test Plan

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-003
- Design:
  `docs/delivery/designs/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-delivery-record.md`
- Status: reviewed; plan review Round 3 PASS; independent rounds append below

## Completion gates

1. Reviewed design has no accepted Critical/High issue.
2. Direct unit/integration tests cover publication, validation, recovery, CAS, cleanup, and secrets.
3. Existing backend, Skill, Harness, docs-sync, and repository-required checks pass.
4. A fresh Codex runtime test proves complete output is independent of bounded PTY/stdout.
5. A fixed R1.1-004 Dify run completes the technical workflow with at least 27 items.
6. An independent tester appends PASS; earlier failures remain recorded.
7. Service restart, backend/frontend health, cleanup, docs/status sync, and commit closure pass.

## A. Static contract and scope

- Confirm only `modeling_draft` is supported; no general upload/API/UI/migration appears.
- Manifest is strict, bounded, content-free, runtime-neutral, and contains both raw and canonical
  hashes computed by trusted code.
- Subagent command is fresh/ephemeral and receives no platform/MCP/lease credential.
- Existing seven-field modeler schema remains authoritative for draft content.
- Platform Artifact remains the sole content authority after persistence.

## B. Publication and positive validation

- Prepare a generation under a valid Build Session/artifact key and confirm owner-only modes.
- Run a deterministic fake Codex process that writes a valid seven-field result to the configured
  output-last-message target. Confirm stdout is not forwarded and runner output is only Manifest.
- Confirm temporary output becomes `draft.json` only after a matching durable exit-zero status and
  minimal secret/regular-file publication checks; full schema/reference validation follows the
  generated milestone.
- Validate exact size, raw SHA-256, canonical hash, item count, schema version, unique IDs,
  dependencies, and item references.
- Confirm exactly 1 MiB canonical content is accepted and 1 MiB + 1 byte is rejected without
  truncation.

## C. Real Codex boundary

- Use `codex exec --ephemeral` in a fresh context with the real output schema and a controlled
  spool. Generate a representative multi-item draft larger than the PTY display budget.
- Redirect/discard Codex stdout, then verify the published file independently.
- Assert final runner output is at most 4 KiB and contains no draft body.
- Verify a second fresh context can consume the explicit previous draft/input bundle and produce a
  correction without using `codex exec resume` or hidden prior context.

## D. Failure-closed validation

- Non-zero Codex exit, missing output, invalid UTF-8/JSON/schema, duplicate client item ID,
  unresolved/cyclic dependency, invalid item reference, oversized content, symlink, path traversal,
  raw/canonical hash mismatch, and modified-after-validation all return stable errors.
- No invalid case creates a platform Artifact/Batch, obtains Lease, or calls apply.
- Secret/API key/Authorization/lease-token cases delete the payload immediately and return only a
  redacted blocker. Search stdout, stderr, state, events, and retrospective output for the secret.
- Kill the runner while a supervised child continues, then let it exit 0 after writing
  `draft.tmp`; the detached supervisor persists status, recovery publishes/validates the complete
  file, and never starts Codex again.
- Repeat with a child that writes complete-looking output but exits non-zero: durable status causes
  `handoff_process_failed`, and the file is never published or validated.
- Missing, corrupt, mismatched, or absent durable status after supervisor/child death returns
  `handoff_exit_status_unknown` and never infers success from a complete-looking file.
- Kill the runner after rename but before the generated-state write; recovery recognizes the final
  file, repairs state, and never discards or regenerates it.
- A matching live child returns still-running; mismatched PID identity, conflicting temp/final, or
  two live owners blocks without reading partial output.

## E. CAS, idempotency, and concurrency

- Same generation ID and immutable inputs is idempotent.
- Same generation ID with changed input/schema/head is `generation_id_conflict`.
- Two processes prepare the same Build Session/artifact key/head concurrently: exactly one wins,
  the other gets `generation_conflict`, and no merge/overwrite occurs.
- Different artifact keys and different Build Sessions can prepare concurrently.
- Platform Artifact retry with the same generation ID returns the same Artifact; stale supersedes
  fails closed. Run the opt-in real PostgreSQL concurrency coverage.

## F. Required interruption recovery

- Failpoint 1: stop after output publication but before main-Agent read/validation. A new process
  inspects, validates, and continues without invoking Codex again.
- Failpoint 2: stop after validation/read but before platform Artifact persistence. A new process
  persists the exact draft once, verifies the returned canonical hash, and continues.
- Stop after Artifact persistence but before local `mark-persisted`: recovery finds the matching
  platform Artifact, marks/cleans locally, and does not create another Artifact.
- Stop after Artifact but before Batch: stable item IDs produce one Batch; later recovery resumes
  from dry-run/review rather than regenerating or duplicating review.
- Missing file, conflicting hash, ambiguous platform match, or state regression is blocked.
- At each recovery point, assert stable Event and Checkpoint IDs/payloads: generated has relative
  locator and `validate_modeling_handoff`; validated has `persist_modeling_draft`; persisted has the
  Artifact ID and `create_or_resume_modeling_batch`. Replaying recovery creates no duplicate fact.
- When interruption occurs before the main Agent records generation, recovery appends the missing
  generated fact with the manifest occurrence time before appending validation/persistence facts.

## G. Rework and lifecycle

- Validation/review correction round 1 and 2 create fresh contexts, complete immutable successors,
  and exact supersedes relationships; main Agent makes no model-content changes.
- Round 3 without explicit recorded user authorization returns `handoff_rework_limit`.
- Successful persistence deletes the complete current and copied-prior payloads while retaining the
  bounded Manifest/hash/platform ID.
- Invalid non-secret content remains only until a valid successor persists or Session terminates.
- Terminal cleanup removes uniquely owned files; active/foreign/symlinked/unknown paths are refused.
- Crash-age cleanup removes only eligible inactive generations.

## H. Platform and Harness regression

- Existing Artifact/event/checkpoint service, REST, MCP, export, question CAS, and PostgreSQL tests
  pass unchanged unless a justified focused change is reviewed.
- Harness hooks store only bounded handoff outcomes and platform IDs; no absolute spool path, draft,
  prompt, subprocess stdout, credential, or hidden reasoning appears in events/retrospectives.
- `ontology-builder` validation/evals/representative traces cover the new handoff/recovery rules.
- Runtime documentation remains truthful: no new REST/MCP endpoint is claimed.

## I. Fixed-corpus Dify integration acceptance

Use the checked-in R1.1-004 corpus and a uniquely identified temporary Project/Build Session.

1. Create or reuse versioned Pack, Matrix, Evidence References, and high-priority competency
   questions from the fixed corpus.
2. Run a fresh credential-free Codex Modeler through the new handoff runner and produce at least
   27 valid candidate items. Prove bounded terminal output and exact file/Manifest integrity.
3. Exercise both required interruption points using the same workflow and recover without a model
   rerun, duplicate Artifact, duplicate Batch, or duplicate review.
4. Persist the Modeling Draft Artifact, create/dry-run the exact Batch, and preserve Attempt/Finding
   fingerprints.
5. Run an independent fresh Reviewer against original corpus evidence, Pack, Matrix, exact draft,
   Modeling Context, and Findings. `REVISE` uses a fresh Modeler context and immutable successor;
   `PASS` must be schema-valid and content-preserving.
6. Only the main Agent acquires Lease and applies the exact reviewed Batch.
7. Run competency-question query/SPARQL, validation, lineage, and current-read checks; persist a
   Verification Report and complete the Build Session.
8. Verify Artifact -> Batch -> Attempt -> Review -> apply -> verification IDs/hashes/events and
   export the timeline.
9. Clean uniquely owned Project/session/test files and prove no credentials or payload remnants.

For step 6, assert the modeler handoff remains `mode=dry_run`. The persisted immutable Batch ID,
normalized items, item IDs, and content hash must match reviewer inputs and apply exactly. Dry-run
and apply use distinct Attempt IDs and idempotency keys; apply alone uses `mode=apply_atomic`, the
current allowed workspace version, and the main-Agent lease token. Reusing the dry-run key or
changing content must fail.

The technical run closes R1.1-003 and R1.1-004's remaining integration gate when PASS. It records
semantic limitations but does not claim R1.1-001 repeatable business-quality completion.

## J. Repository and runtime gates

- `python -m unittest discover -s .codex/tests -p 'test_*.py'`.
- `python skills/ontology-builder/evals/validate_skill.py`.
- `cd backend && uv run python ../skills/ontology-builder/evals/run_evals.py`.
- `cd backend && uv run pytest` for any backend-affecting delivery and final regression confidence.
- `cd backend && RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest -q
  tests/test_modeling_workflow_postgres.py`.
- Ruff check/format on every changed Python file; full-repo baseline differences are reported.
- `git diff --check` and documentation sync checks.
- `systemctl --user restart ontology-platform.service`, unit active, backend `/api/health`, frontend
  `5173`, and affected authenticated runtime path.
- GitNexus `detect_changes(scope="compare", base_ref="main")` or scoped equivalent before commit.

## Cleanup proof

Record exact generated Project/Session/Ontology IDs, local generation IDs, platform Artifact/Batch
IDs, and cleanup counts. Delete only uniquely identified test data. If ownership is ambiguous,
leave it and report the residual instead of broad deletion.

## Independent test rounds

### Round 1 — FAIL (2026-07-19)

- Stable state: commit `c4a61578ebceb28a5524908fc830e5a256d05e6f` plus implementation
  file-set digest `96d00401cac9017bde1f8f200a125f28161cf64a57df5b0f8561622d56cca964`.
- Result: **FAIL**. Direct validation, CAS, lifecycle, Harness, fixed-corpus, real Codex,
  interruption, Artifact persistence, and dry-run gates passed far enough to expose one High
  product defect. The tester stopped before Lease/apply and did not change product code.

Evidence:

- `.codex` direct/Harness suite: `python -m unittest discover -s .codex/tests -p 'test_*.py'`
  returned `Ran 38 tests in 11.743s`, `OK`.
- Skill/static checks: `validate_skill.py` passed with 10 references and 34 MCP dependencies;
  `run_evals.py` passed 7 cases; Ruff check and format-check passed for all four changed Python
  files.
- Fixed corpus `dify-foundations-2026-07-18-5396c1a` verified 32 files and its independent suite
  returned `Ran 24 tests`, `OK`. Real PostgreSQL Artifact concurrency returned `2 passed`.
- The service was initially active with backend `/api/health` and frontend `5173` healthy. The run
  temporarily selected `rdf_primary` for canonical dry-run, then restored the original unset
  manager override/`legacy_only`; final service state was active with backend `200` and frontend
  `200`.
- Unique real-runtime scope: Project `53f3b21c-8068-473a-b13e-8a0ac49a9ba2`, Build Session
  `0b3050da-aba3-47e4-97eb-60ae4e969f1e`, Ontology
  `a4e5d988-e578-4974-bf3f-bbe7b5f17f4b`. No modeler/reviewer received a platform key or Lease.
- Fresh production `codex exec --ephemeral` generation v1 completed in 13m18s with discarded
  stdout. Durable exit was zero; raw output was 42,342 bytes with SHA-256
  `a95b324a9b889ef2371397d0acf0d903f6778735bfb1eb72f5afb84a2ec1c686`. Recovery validated 32
  items and canonical hash `40e1ce67bf9639cf38f84f6f169a9dde5e228bde917bf5ccf3dd6e85de7c6e68`;
  the bounded Manifest was content-free and below 4 KiB.
- Interruption point 1 started from durable exit-zero plus `draft.tmp`, while platform state still
  had only Pack/Matrix, one prior Event, no Draft Artifact, and no Batch. A new process read platform
  facts first, atomically published/validated without invoking Codex again, and appended stable
  generated/validated Events and Checkpoints. Interruption point 2 resumed from validated/no Draft
  Artifact/no Batch and persisted exactly one Draft Artifact
  `db89b224-b889-43fa-8c95-b92fc93a94bd`; platform and local canonical hashes matched. Stable
  persisted Event/Checkpoint were recorded before `mark-persisted`; current draft and copied inputs
  were then deleted.
- Exact immutable Batch `55b35370-0264-4c2e-a4e0-94e4aba56b8a`, content hash
  `467af3c586b2b5849af8e240a4446d1f99f47f2c86c249e4b043563321d93df7`, preserved its first
  environment-failed Attempt `ebc4c091-08d2-49cb-8f9c-ccd5c30c4f97`. After the canonical mode
  correction, Attempt `969534ce-22dc-4be2-84bd-a29293e90380` validated the same 32 items with zero
  Findings and no Lease.
- Fresh credential-free review v1 was preserved as BLOCKED Artifact
  `abd45f7f-7399-4e5e-b32b-2db5b3e441e3` and Event
  `2a025fac-2eae-45f1-a47f-24cc16c0704f`. Its five normalized quality issues (one critical, three
  high, one medium) were accepted as test-input/modeling findings, not R1.1-003 product defects.
  Pack `f91cfc66-7c1f-4aab-859c-b9f1394186aa` and Matrix
  `dc3c55a3-28ec-45b3-888f-495a73999ef5` then superseded v1 with the complete 32-file corpus and
  exact per-source evidence. Fresh correction Modeler v2 received the complete previous Draft and
  normalized issues; the main Agent did not edit model content.

Confirmed defect:

- **High — in-progress/crashed Codex stderr is stored unbounded and unredacted in the controlled
  spool.** `.codex/modeling_handoff.py:927` opens `.diagnostic.tmp`, and line 934 directs the child
  stderr to it without a bound or streaming redaction. Only after normal child completion do lines
  978-989 read the final 2 KiB, delete the raw file, and secret-scan that tail. In the real v1 run
  the live raw diagnostic reached 93,436 bytes. Correction v2's owner-only raw diagnostic contained
  the complete explicit prompt; after more than 20 minutes it remained present while the child was
  live. A crash would preserve earlier unscanned prompt/source/possible hidden-reasoning bytes.
  Owner-only mode reduces exposure but does not satisfy the reviewed bounded/redacted diagnostic
  contract or the no-prompt/no-hidden-reasoning acceptance gate. Existing tests do not exercise
  this live/crash window.

Containment and cleanup:

- At main-agent direction, the tester verified the unique correction child identity and sent
  SIGTERM only to that process group; no partial output was read or reused and no replacement model
  was started. The supervisor exited, deleted `.diagnostic.tmp`, and recovery durably blocked the
  generation as `handoff_file_missing` because no final output existed.
- `cleanup-session` removed both uniquely owned local generations (`removed: 2`). Temporary raw
  reviewer diagnostics and prompt/input copies are cleanup-only data and are not platform evidence.
  The platform Project/Session and immutable BLOCKED history remain intentionally retained for the
  repair/retest handoff; no Lease was acquired and no apply occurred.

Unexecuted because of the High stop condition:

- Correction v2 persistence, second dry-run, fresh review PASS, exact apply, competency queries,
  SPARQL, validation, lineage, Verification Artifact/Event, Build Session completion, and platform
  Project cleanup.
- The independent full-backend run's final terminal summary was not captured before the stop, so
  no independent full-suite PASS is claimed for Round 1. Final diff/GitNexus/commit closure belongs
  to the post-repair stable round.

Residual risks:

- Until stderr capture is bounded/redacted during execution and on abnormal exit, a real Codex run
  may retain prompt/source or hidden-reasoning material in the spool despite successful payload and
  Harness secret tests. Round 2 must first reproduce the failed diagnostic case, then rerun all
  affected lifecycle/security checks and the remaining fixed-corpus platform gates.

### Round 2 — FAIL (2026-07-19)

- Stable state: commit `c4a61578ebceb28a5524908fc830e5a256d05e6f` plus repaired
  implementation file-set digest
  `a1bef6ff4a79f3e712cece4bef7b3b68f146eb0406da61691dc45a24fe47dab8`.
- Result: **FAIL**. The Round 1 diagnostic-spool defect and all independently rerun static,
  corpus, concurrency, and backend regressions passed. A fresh real correction Modeler then exposed
  a separate High credential-isolation defect before producing a complete draft. The tester stopped
  before Artifact persistence, second Batch dry-run, review, Lease, or apply and did not change
  product code.

Evidence:

- The repaired diagnostic cases passed before this handoff: live stderr above 200 KiB, non-zero
  stderr above 250 KiB containing a secret marker, split secret across chunk boundaries, and forced
  supervisor `SIGKILL` retained no raw diagnostic file or marker/token. The independent full direct
  suite returned `Ran 41 tests in 12.927s`, `OK`; a live spool search found no
  diagnostic/stderr/stdout/rollout/reasoning file.
- Independent repository regressions passed: backend `729 passed, 6 skipped, 166 warnings in
  70.80s`; real PostgreSQL Artifact concurrency `2 passed`; Skill structure 10 references/34 MCP
  dependencies; Skill eval 7 cases; fixed corpus verification 32 files and corpus unit suite 24/24;
  backend-configured Ruff check/format-check on all four changed Python files and
  `git diff --check`.
- Retained real-runtime scope remained Project `53f3b21c-8068-473a-b13e-8a0ac49a9ba2`, Build
  Session `0b3050da-aba3-47e4-97eb-60ae4e969f1e`, and Ontology
  `a4e5d988-e578-4974-bf3f-bbe7b5f17f4b`. Before containment it still had exactly six workflow
  Artifacts, one Batch, eight Execution Events, and four Checkpoints; no new platform fact had been
  written by the correction run.
- The unique fresh correction generation was `r11003-correction-v2-round2`, correction round 1. Its
  detached supervisor PID was `4074121`; Codex process group `4074134` ran for about 76 minutes with
  continuing I/O and established connections. `inspect` correctly returned
  `handoff_still_running`; no `draft.tmp` or final draft existed and the tester never read an
  incomplete model output.

Confirmed defect:

- **High — the supposedly credential-free Modeler loads the user's global Codex MCP configuration
  and receives an authenticated platform MCP server.** The live Codex process tree contained
  `python -m app.mcp.server` as PID `4074591`, descended from the Modeler. Inspecting environment
  *names only* showed `ONTOLOGY_MCP_API_KEY` in that MCP server process; it was absent from the
  direct launcher/modeler process environments but remained callable by the model context through
  MCP. `.codex/modeling_handoff.py:958-973` starts `codex exec --ephemeral --sandbox read-only`
  while retaining `HOME`/`CODEX_HOME`, but does not disable user configuration. The installed CLI
  documents `--ignore-user-config` as preventing `$CODEX_HOME/config.toml` loading while preserving
  Codex authentication. A read-only filesystem sandbox does not constrain an external authenticated
  MCP write tool. This violates the reviewed fresh-context contract that the Modeler receives no
  platform/MCP credential, Lease, or apply capability even though no unauthorized write was
  observed in this run.

Containment and cleanup:

- With main-agent authorization, the tester sent `SIGTERM` only to process group `4074134`; the
  supervisor, Codex, code-mode host, and all MCP descendants exited within the bounded wait, so no
  `SIGKILL` was required. No partial output was read, copied, persisted, or reused and no replacement
  Modeler was started.
- Post-exit `inspect` returned `handoff_file_missing` and durably blocked the generation. The
  uniquely owned `cleanup-session` operation removed exactly one generation (`removed: 1`), and a
  temporary tester-only helper/schema plus bytecode cache were removed. The retained platform
  history was intentionally preserved for the next repair round.
- Runtime configuration remained at its pre-test `legacy_only` state because Round 2 never reached
  dry-run/apply mode switching. Final service state was active; backend `/api/health` returned
  `{"status":"ok"}` and frontend `5173` returned HTTP 200.

Unexecuted because of the High stop condition:

- Correction draft publication/validation and CAS successor Artifact; exact successor Batch
  dry-run; fresh independent review; exact Lease/apply; competency-question Context Query/SPARQL;
  validation, lineage, Verification Artifact/Event, Build Session completion/export; and unique
  Project cleanup.

Residual risks:

- Until the handoff launch explicitly isolates user Codex configuration/MCP servers and tests prove
  that no configured MCP process or platform credential reaches the model context, a Modeler can
  bypass the intended credential-free authority boundary independently of the now-fixed diagnostic
  spool. Round 3 must first reproduce this process-tree/environment check, then start a new single
  correction generation and rerun the remaining fixed-corpus gates.

### Round 3 — BLOCKED (2026-07-20)

- Stable state: commit `920b5ed7df1e2f3575b6ef5ff0f5fe900c60d432`; the tester changed no
  product code and appended only this round to the shared plan.
- Result: **BLOCKED, not a product-code FAIL**. The Round 2 credential/configuration High repair,
  real 39-item handoff, both interruption points, exact Artifact persistence, immutable Batch, and
  zero-finding dry-run passed. Independent review then found a confirmed Modeling Draft coverage
  defect after both automatic correction rounds had been consumed. The contract therefore requires
  explicit user authorization before another Modeler run; the tester did not acquire a Lease or
  apply.

Evidence:

- Production `codex-cli 0.144.6` was invoked as `codex exec --ephemeral --ignore-user-config
  --sandbox read-only`. During the live boundary probe, the Modeler environment contained only
  `HOME`, locale, `PATH`, `TERM`, and credential-free lowercase proxy names; no denied credential
  category or credential-bearing proxy was present. Its process group had no MCP process, and its
  only observed descendant was `codex-code-mode-host`. The probe completed in 41 seconds with five
  schema-valid items, 5,040 raw bytes, raw SHA-256
  `9d0f321c4e5619926817c49ec2f4f91278eb5efd50eb4dd8f0734f3ec2a3d293`, and canonical hash
  `24c5fa8b32bd7002119b257c6d7c2b4b35546adb38aec23c58c0a8cfadb74605`.
- The fixed-corpus correction Modeler received the complete previous Draft, current Pack, 32-row
  Matrix, Modeling Context, structured Findings, and all 32 snapshot files in a fresh restricted
  process. Before recovery, durable exit was zero, platform counts remained exactly six Artifacts,
  one Batch, eight Events, and four Checkpoints, and the only unpublished payload was a 48,634-byte
  `draft.tmp` with raw SHA-256
  `cde0cabb254f8c09f052adcddc0c84f10a73e7d143cdea6d40e3f0575b8863c0`.
  This proved interruption point 1 without a model rerun. A new process published and validated 39
  items with canonical hash
  `b7a5494dd80d73064127b05c5536145a32d52a40aa69caa4f7c3038afd37341b`, proving interruption
  point 2 before any Artifact existed.
- Main-Agent fixed-corpus verification then failed closed on two non-contiguous lifecycle excerpts.
  Event `e3976b46-3414-4d96-ad56-0664e6b13203` and a stable blocked Checkpoint recorded the exact
  two client item IDs; no Artifact, Batch, Lease, or apply was created from that version. The second
  and final automatic correction used a fresh context, changed only those two excerpts, and produced
  39 items in 48,647 bytes with raw SHA-256
  `5bdeedd49b63241fdbc969f2609066df53993cb6196a15855fbadd4b57b89c43` and canonical hash
  `6669a61b93c60bd7fe3a5e9e1f2a214f7bf5eb6acf2c0df908b6bc4b0c2ee69c`.
  All 39 excerpts then matched their declared fixed source exactly, and a structural comparison
  proved no field outside the two allowed evidence arrays changed.
- Modeling Draft Artifact `6e4cfea4-9912-40fc-b037-8acfccf32892` supersedes the original Draft,
  has the exact local canonical hash, and returned the same ID on idempotent retry. Generated,
  validated, and persisted Events are `9efdcc92-d60f-4825-9f93-e4aa20a8976f`,
  `43f6d544-9230-4e94-9f36-d462c8bf297c`, and
  `0dde0ed2-60da-46cf-b16a-34d051765dd1`; matching Checkpoints were appended before
  `mark-persisted` removed the current and predecessor complete payloads.
- Exact immutable Batch `5e93f7f6-a522-4db1-b2c9-8995ee854673` has content hash
  `2071aae2d1456bbf058207e3af28086f4d464ae5ae44ced1d9662fa365e2e58a`.
  Dry-run Attempt `308a2e45-2b28-4400-b656-e83b7c73a097` validated all 39 items with zero
  findings and no workspace change. Identical retry returned the same Batch/Attempt with both
  `created_*` flags false; changed content under the same key returned HTTP 409
  `idempotency_conflict`.
- Fresh restricted Reviewer output was persisted unchanged as BLOCKED Review Artifact
  `d43b7475-2f4b-4f88-b898-e913560fbbca` with hash
  `5bc4a3656711951668c4f79b25ab3de484509c67f82df92fadad0d37a03cc453` and Event
  `d6a353c8-32d5-4ad3-85e5-679064465203`. The session is active at revision 10 with nine
  Checkpoints and 14 Events; the Batch remains open with only the dry-run Attempt, the Ontology has
  zero applied resources, and no Lease is active.

Finding disposition:

- **Confirmed High modeling-output finding — coverage updates are mapped to the wrong fixed Matrix
  rows.** The Draft retains 15 old-order updates, while Matrix v2 has 32 source-specific rows:
  `coverage-00` is LICENSE and `coverage-01` is `docs.json`, but the Draft assigns workflow-node
  and versioning elements respectively. Seventeen later rows remain `AMBIGUOUS` even where the
  Draft models their subjects. This is not an R1.1-003 transport implementation defect, but an exact
  apply blocker under the reviewed workflow contract.
- **Rejected reviewer finding — 31 corpus bodies were unavailable.** The review directory contained
  every `source00` through `source31` body, corpus verification passed 32/32, and the main-Agent
  exact check matched all 39 final excerpts. The Reviewer's file-availability statement conflicts
  with direct filesystem and hash evidence and was not treated as a product or model defect.
- No new R1.1-003 product-code defect was found. The repaired live diagnostic path observed
  260,074 and 210,766 stderr bytes in the two Dify runs while retaining only bounded category
  metadata; no raw diagnostic file or secret category remained.

Regression and runtime evidence:

- `.codex` direct/Harness suite: `Ran 42 tests in 13.563s`, `OK`; Skill structure validated 10
  references and 34 MCP dependencies; Skill evals passed seven cases; fixed corpus verified 32
  files and its suite passed 24/24; PostgreSQL Artifact concurrency passed 2/2; changed-file Ruff
  check/format-check and `git diff --check` passed.
- The first full backend run crossed the generated-at second boundary in
  `test_new_and_compatibility_build_context_tools_return_same_shape` and returned one failure with
  719 passed/6 skipped. The exact failed test immediately passed alone; an independent second full
  run passed `720 passed, 6 skipped, 166 warnings in 70.69s`. This timing flake is unrelated to the
  handoff change and did not recur.
- The service was switched temporarily to `rdf_primary` only for canonical dry-run, then restored to
  its original unset manager environment and `legacy_only` mode. Final unit state is active; backend
  `/api/health` returned `{"status":"ok"}`, frontend `5173` returned HTTP 200, and canonical mode
  reported legacy/legacy-only/legacy.

Unexecuted because of the contractual stop:

- A third correction, fresh PASS review, Lease acquisition, exact `apply_atomic`, reuse-of-dry-run-
  key apply rejection, competency-question Context Query and validation, SPARQL, semantic
  validation, lineage/current reads, Verification Artifact/Event, workflow export, Build Session
  completion, and Project deletion were not executed.
- Resume only after an explicit user decision is recorded with authorization marker
  `r11003-round3-coverage-correction-authorized`. The allowed correction scope is only to rebuild
  `coverage_updates` against all 32 Matrix v2 rows while preserving the immutable 39 items, Batch
  envelope, IDs, dependencies, evidence, exclusions, and corpus. The new generation must use a fresh
  Modeler context and immutable successor; then rerun exact excerpt/Matrix checks, persist a
  successor Draft and Batch, and start another fresh independent review before any Lease or apply.

Containment, cleanup, and residual state:

- Secret scanning found zero flagged files across 49 temporary input/review files. Both Modelers and
  the Reviewer had no MCP descendant or credential environment, and no local raw diagnostic existed.
  `cleanup-session` removed exactly two Dify generations and one boundary-probe generation. The 49
  uniquely owned temporary input/review files and three temporary helper/prompt files were removed;
  all named paths were verified absent.
- Project `53f3b21c-8068-473a-b13e-8a0ac49a9ba2`, Build Session
  `0b3050da-aba3-47e4-97eb-60ae4e969f1e`, and Ontology
  `a4e5d988-e578-4974-bf3f-bbe7b5f17f4b` are intentionally retained because they contain the
  immutable blocker and are the only safe resume authority. Broad platform cleanup is not allowed
  while the active blocked workflow must remain recoverable.
- The Round 1/2 containment had already removed the original local generation chain. Round 3
  therefore started a new local pre-persistence CAS chain while preserving the authoritative
  platform supersedes link to Draft v1; its second correction correctly used
  `expected_previous_generation_id` within that new chain. This test-history discontinuity is
  explicit and does not justify claiming closure.
- Stable state is **not closure-ready**: the High modeling-output finding prevents independent PASS,
  apply, verification, Build Session completion, R1.1-003 closure, and R1.1-004 integration closure.

### Independent Round 4 — FAIL (2026-07-20)

Scope and result:

- Round 4 resumed only the explicitly authorized coverage correction. It preserved the 39 immutable
  modeling items and independently checked the successor Draft, Batch, fixed corpus, Matrix,
  evidence, review, exact apply, and semantic verification path. The overall result is **FAIL**
  because the applied `owl:Class` resources are invisible through the supported classes/class-detail
  current-read templates, and the repository format gate is also red.
- No product code or delivery record was modified by the independent tester. This section is the
  only tracked tester edit.

Successor integrity and fresh review:

- Successor Draft Artifact `02f62ea4-3bc7-4fa0-b9a4-2d299321c9e1` has canonical hash
  `84c05dd08170af149acb61810870ff03bab759dbaee117ea9caea537a97b07ba`, supersedes Draft
  `6e4cfea4-9912-40fc-b037-8acfccf32892`, and uses client version
  `r11003-coverage-v5-20260720t1055`. Its six non-coverage fields exactly match the predecessor;
  their independently recomputed combined hash is
  `85a234ac5239824a525048e3dba973d8611d30556ff495b655b999da74fd55d4`.
- Exact successor Batch `d3302dc5-6ea3-4a67-b9df-44f1f31bbb46`, client Batch
  `dify-round3-v3-r11003-8411a0085ece`, contains 39 unique items and has immutable normalized hash
  `2071aae2d1456bbf058207e3af28086f4d464ae5ae44ced1d9662fa365e2e58a`.
  Dry-run Attempt `d6eb0baa-850a-4a50-b33b-3d1b7be6a8be` validated all 39 items with zero
  findings. The independently recomputed complete Batch request hash is
  `b60d101d20eeb67ac8d87d5e4f3ae54c7ff511a37ec91086cbe1efaebbeb9c3f`.
- All 32 Matrix rows have exactly one coverage update; every update Evidence ID is a subset of its
  source row, every referenced model element exists, all 39 inline excerpts occur contiguously in
  the fixed corpus, both persistent Evidence References are readable, and all three referenced
  competency-question IDs exist. Fixed-corpus verification passed 32/32 files and 24/24 tests.
- A fresh credential-free, MCP-free, read-only Codex Reviewer returned schema-valid `PASS`, with no
  quality issues or required rework, after reading the exact Draft/Batch, all 32 source bodies,
  Pack, Matrix, Modeling Context, and invariant manifests. PASS Review Artifact
  `c59a9712-73bf-4b08-8fd7-c88d69a55dbc` has hash
  `da74ef4cd1b7011827cef7980b5dac3a84786684db1bd29348f0de1e20c0742b`, supersedes the prior
  BLOCKED Review, and Review Event `99262306-d37a-4112-8a5d-65eee5fac837` plus Checkpoint sequence
  17 preserve the decision.
- The permission-boundary probe used `codex exec --ephemeral --ignore-user-config --sandbox
  read-only`, had no MCP descendants or credential environment, bounded 5,040 diagnostic stderr
  bytes in memory, and produced four schema-valid items. Raw output hash was
  `3fe87f2b3091cc27f22d8cb2dc3a6fb838ac668f8aeec2b6b7eaa2a56da90304`; canonical hash was
  `221223ab4036b09832a28669063de7bda0976970f9087f231835f6e225a196b9`.

Exact apply and fail-closed evidence:

- Reusing the dry-run idempotency key for apply returned HTTP 409 `idempotency_conflict`. An
  accidentally reused historical Round-4 key replayed the already applied v2 Attempt without a new
  write. Switching from the legacy view to RDF then correctly rejected the stale reviewed workspace
  version with HTTP 409 `workspace_revision_conflict`, reporting current version
  `051052af13ebfbef3606fe41e5f3dfb25de1019cd76f3692acc1dc9b0af391ec`.
- Under `rdf_primary`, the main-Agent-authorized exact apply kept Batch ID, 39 normalized items, item
  IDs, dependencies, evidence, and content hash frozen. Only the permitted Attempt envelope changed:
  mode `apply_atomic`, fresh idempotency key
  `r11003-round4-successor-v3-rdf-apply-exact`, current workspace version, and Lease token. Apply
  Attempt `c418ce1d-3cce-4836-8a0e-b391ffc430ef` succeeded with zero findings; workspace moved from
  `051052af13ebfbef3606fe41e5f3dfb25de1019cd76f3692acc1dc9b0af391ec` to
  `16f56c805b97439c2aed873b892678078e7947e94d886789ebacc5b2876bd2da`.
- The Lease was released and Checkpoint `3580fb8d-3bab-47b9-a8cd-ccd7f6eefcbe`, sequence 18,
  records the exact apply. The Build Session remains active at revision 19 so a repair can resume
  without reconstructing authority.

Semantic verification and finding disposition:

- Context Query returned `matched` for `Workflow Trigger`, `Chatflow`, and `DSL`, with 20, 2, and 2
  primary matches respectively. Explicit SPARQL returned the applied ontology resources; a distinct
  class query sees 21 modeled classes. Semantic validation run
  `d58f3803-1b08-4b6f-a346-40c2ffe6ed46` succeeded and conformed with zero violations, warnings, or
  info findings. Resource lineage for Workflow Trigger Node is `complete`, has eight items, and has
  no warnings. The facts current-read returned 100 items.
- **Confirmed High product integration defect — classes/class-detail current reads omit applied
  R-004 classes.** R-004 persists the modeled resources as `owl:Class`, while
  `ontology-schema-summary` and `class-detail` query only `rdfs:Class`; therefore
  `/api/ontologies/{id}/semantic-read-models/classes` returned zero items although scoped SPARQL sees
  all 21 classes. The supported current-read contract is broken after a successful exact apply and
  must be repaired and regression-tested before closure.
- **Rejected as a product defect — direct validation of the three Pack competency questions.** The
  questions are intentionally `draft` with `query_definition.kind=semantic_context`; their three
  `POST .../validate` calls correctly returned HTTP 409 `Only testable questions can be validated`.
  This requirement verifies them through matched Context Query plus explicit SPARQL. They were not
  mutated into unrelated `sparql_count` questions.

Regression, cleanup, and stable handoff:

- `.codex` direct/Harness suite passed 42 tests; Skill structure passed 10 references and 34 MCP
  dependencies; seven Skill evals passed; full backend passed `720 passed, 6 skipped, 166 warnings`;
  and PostgreSQL Artifact concurrency passed 2/2. Ruff lint and `git diff --check` passed.
- **Confirmed repository completion-gate defect:** `ruff format --check` reports both
  `.codex/modeling_handoff.py` and `.codex/tests/test_modeling_handoff.py` would be reformatted. The
  tester did not modify them; the implementation owner must format them and rerun the gate.
- Secret scanning found zero flagged files across 46 Round-4 temporary files. `cleanup-session`
  removed one boundary-probe generation and two Build-Session generations. All four named local
  helper/review paths were moved to trash and verified absent. The applied Project, Build Session,
  Ontology, Artifacts, Batch, Attempts, validation run, Events, and Checkpoints remain intentionally
  available as the repair authority.
- Runtime manager overrides were removed. Final service state is active; backend health and frontend
  returned success, and canonical mode is restored to legacy/legacy-only/legacy.
- Verification Artifact/Event, workflow export, Build Session completion, Project deletion, and
  R1.1-003/R1.1-004 closure remain unexecuted. Resume by repairing the `owl:Class` read-model
  contract and formatting the two handoff files, then independently rerun classes/class-detail,
  regression gates, Verification persistence/export, completion, and final unique Project cleanup.

### Independent Round 5 — PASS (2026-07-20)

Scope and repair review:

- Round 5 retested stable baseline `a3405b263ad90ff6d9cc14f1727b180722a01c13` plus the intended
  R1.1-003 repair in `backend/app/services/semantic_sparql_templates.py` and new regression file
  `backend/tests/test_semantic_class_type_read_models.py`. The tester changed no product code or
  main delivery record; this append-only section is the tester's only tracked edit.
- Both `ontology-schema-summary` and `class-detail` now bind the resolved Graph Set members explicitly
  and accept `owl:Class` or `rdfs:Class` through a type variable under `SELECT DISTINCT`. The focused
  real-RDFLib regression proves owl-only, rdfs-only, and dual-typed resources appear exactly once in
  both read models, while identically shaped resources in an out-of-scope graph are excluded.
- The prior format finding was caused by executing Ruff from the wrong configuration root, not by
  malformed files. From `backend/`, Ruff `0.15.17` passed both lint and the exact repo-configured
  format check for `../.codex/modeling_handoff.py`, `../.codex/tests/test_modeling_handoff.py`, the
  changed template, and the new test: `4 files already formatted`.

Focused and live repair verification:

- The new regression passed 1/1. The affected semantic API/read-model/modeling-batch set passed
  50/50.
- With temporary canonical RDF read/write mode, the tester derived the 21 `create_class` resource
  IRIs directly from applied Batch `d3302dc5-6ea3-4a67-b9df-44f1f31bbb46`, apply Attempt
  `c418ce1d-3cce-4836-8a0e-b391ffc430ef`, and Graph Set
  `57f07326-3246-5791-a611-d322b4b92050`. Both classes and class-detail returned 42 globally unique
  current IRIs. Every current-Batch IRI was present 21/21 exactly once, with zero missing, zero
  duplicates, and zero source graphs outside the four resolved Graph Set members. The additional 21
  are pre-existing distinct resources and are not duplicates of the current Batch.
- Context Query remained `matched` for `Workflow Trigger`, `Chatflow`, and `DSL`, with 20, 2, and 2
  primary matches. Explicit scoped SPARQL returned 42 distinct OWL class IRIs. Fresh semantic
  validation run `c8bbb08d-cfb7-4e47-9d3e-0fc1bd1cfcab` succeeded and conformed with zero
  violations, warnings, or info findings. Workflow Trigger Node lineage remained `complete` with
  eight items and no warnings.
- The three intentionally draft `semantic_context` competency questions again returned HTTP 409
  `Only testable questions can be validated`; this is the accepted boundary disposition, not a
  product defect, and no question was mutated.

Immutable workflow evidence:

- PASS Review Artifact `c59a9712-73bf-4b08-8fd7-c88d69a55dbc` retains hash
  `da74ef4cd1b7011827cef7980b5dac3a84786684db1bd29348f0de1e20c0742b` and Review Event
  `99262306-d37a-4112-8a5d-65eee5fac837` remains completed.
- Applied Batch `d3302dc5-6ea3-4a67-b9df-44f1f31bbb46` retains 39 items and normalized hash
  `2071aae2d1456bbf058207e3af28086f4d464ae5ae44ced1d9662fa365e2e58a`. Dry-run Attempt
  `d6eb0baa-850a-4a50-b33b-3d1b7be6a8be` remains validated; exact `apply_atomic` Attempt
  `c418ce1d-3cce-4836-8a0e-b391ffc430ef` remains applied with zero findings and workspace
  transition `051052af13ebfbef3606fe41e5f3dfb25de1019cd76f3692acc1dc9b0af391ec` to
  `16f56c805b97439c2aed873b892678078e7947e94d886789ebacc5b2876bd2da`.

Regression and completion evidence:

- Full backend passed `725 passed, 6 skipped, 176 warnings in 62.98s`. `.codex` direct/Harness
  passed 42 tests in 11.747s. The ontology-builder structure passed 10 references and 34 declared
  MCP dependencies; all seven Skill eval cases passed. The fixed corpus verified all 32 files and
  its suite passed 24/24. PostgreSQL Artifact concurrency passed 2/2. `git diff --check` passed.
- Final Verification Artifact `9fc18f35-d0b7-4d31-8b1b-2a1053fcc742` has content hash
  `4d57f3f7423cd9926f01f65c93da0940e747373777add56064352f0b18157555`; Verification Event
  `8f07513b-8367-4269-8210-c93ac50808ef` and Checkpoint
  `02b81ff0-0544-4e58-973f-075b148670b2`, sequence 19, preserve the independent PASS. The Build
  Session completed at revision 21 with no unresolved items.
- Final JSON export contained 11 Artifacts and 23 Events, 278,940 bytes, SHA-256
  `abb323f854dd3b8038a8fa826cf7f7b662dc9058069f18c4191c0c4ec86859d1`. Markdown export was
  332,604 bytes with SHA-256
  `fcbf1c4a06feae61b36d0f20d90f7bea7997ce66f3de268f11858a2a8dd9142e`.
- The uniquely owned Project was deleted only after both exports. Project, Build Session, Ontology,
  Batch, and Verification Artifact endpoints each returned 404 afterward. The one Round-5 helper
  file had zero secret findings, was moved to trash, and was verified absent.
- Runtime overrides were removed and the service restarted. Final unit state is active; backend
  health and frontend returned success, and the authenticated canonical-mode endpoint reports the
  restored legacy/legacy-only/legacy defaults.

Change-scope disposition and closure:

- GitNexus `detect_changes(scope=unstaged)` reported global `CRITICAL` risk across 140 changed
  symbols, 54 affected symbols/process entries, and 27 indexed changed files. That aggregate includes
  concurrent R1.2 retrieval, API/MCP, configuration, migration, frontend, `AGENTS.md`, and
  `CLAUDE.md` work explicitly outside this test handoff. The intended R1.1 repair is confined to the
  two template bodies plus its focused test and is covered by focused, full-suite, and live RDF
  evidence above; the tester neither modified nor disposed of the unrelated work.
- Round 5 independently closes the R1.1-003 technical acceptance and the R1.1-004 post-R1.1-003
  fixed-corpus integration gate. R1.1-001 repeatable business-quality improvement remains a separate
  residual acceptance concern. Requirement/status documentation synchronization and the scoped final
  commit remain main-Agent closure work.
