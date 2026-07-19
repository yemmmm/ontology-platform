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

### Round 1 — pending

- Stable state: pending development-ready handoff
- Result: pending
- Evidence: pending
- Defects/unexecuted cases: pending
- Residual risks: pending
