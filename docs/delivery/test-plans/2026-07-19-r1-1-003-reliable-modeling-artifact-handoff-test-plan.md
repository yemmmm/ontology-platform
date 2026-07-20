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
