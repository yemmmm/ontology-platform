# R1.1-003 Reliable Modeling Artifact Handoff Design

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-003
- Contract frozen: 2026-07-19
- Status: implemented; plan review Round 3 PASS; independent test Round 5 PASS
- Delivery record:
  `docs/delivery/records/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-test-plan.md`

## Goal

Make a Codex modeling subagent's complete seven-field Modeling Draft recoverable independently of
PTY, chat, or rollout output. The subagent remains credential-free. An authorized main Agent must
validate the exact draft, persist it through the existing Modeling Workflow Artifact contract, and
continue the existing dry-run, review, apply, query, validation, and lineage workflow without
silent content repair or duplicate work.

## Non-goals

- General file upload, object storage, chunking, or a frontend file manager.
- Large-file support for Pack, Matrix, Review Report, or arbitrary Artifact types.
- A platform-hosted Agent Runtime or adapters for Claude Code/OpenCode.
- Granting a modeling subagent a platform credential, MCP write tool, Ontology Lease, or apply.
- Changing the 1 MiB platform Artifact limit or automatically splitting an oversized draft.
- Replacing Build Checkpoint, Modeling Execution Event, Modeling Workflow Artifact, Batch,
  Attempt, validation, lineage, or audit as platform facts.

## Verified assumptions

1. Two persisted 32-item Dify Modeling Drafts are 32,422 and 32,433 canonical bytes, leaving
   96.91% headroom under the current 1 MiB limit.
2. A real fresh `codex exec --ephemeral` produced a 42,227-byte, 40-item file whose hash, size,
   and item count matched a 163-byte final manifest; the temporary file was absent after atomic
   publication.
3. Existing Artifact service tests prove canonical linear versions, stale-head rejection, and
   idempotency; the opt-in real PostgreSQL concurrency test passes. Platform persistence therefore
   reuses `client_version_id`, `artifact_key`, and exact `supersedes_workflow_artifact_id` rather
   than introducing another persistent version graph.

## Actors and authority

- **Modeling subagent:** a fresh, ephemeral Codex context. It can read only the explicitly prepared
  input bundle and write only its generation directory. It receives no platform or lease secret.
- **Local handoff runner:** trusted repo-local code launched by the main Agent. It prepares the
  spool, runs Codex, captures the final message to a temporary file, validates it, publishes it
  atomically, exposes bounded state, and cleans local payloads.
- **Main Agent:** prepares versioned inputs, evaluates the bounded manifest, performs authorized
  platform validation, creates the Artifact/Batch and Events/Checkpoints, controls rework, and is
  the only actor allowed to obtain Lease/apply.
- **Reviewer:** an independent fresh context receiving the exact persisted draft and platform
  Findings; it cannot edit or apply.
- **Platform:** remains authoritative for persisted Artifact content, workflow events,
  checkpoints, Batch/Attempt, current semantic state, validation, lineage, and audit.

## Controlled spool

The implementation adds one repo-local handoff command, located with the existing Codex Harness.
Its state root is under the already gitignored `backend/.local/` tree:

```text
backend/.local/modeling-handoffs/
  <build-session-id>/
    <artifact-key>/
      head.json
      <generation-id>/
        generation.json
        input/
        draft.tmp
        draft.json
        manifest.json
        process-status.json
        .lock
```

Directory and file names are derived from validated identifier segments, never raw paths supplied
by a subagent. Directories are owner-only and files are owner-read/write only. Inputs are copied or
materialized before launch, made read-only to the subagent, and contain only the explicit Pack,
Matrix, Modeling Context, Evidence index, schema/version, prior draft when correcting, structured
Findings, and correction scope.

`draft.tmp` is the `codex exec --output-last-message` target. Codex stdout is discarded rather
than forwarded to the parent PTY; stderr is reduced to a bounded, secret-redacted diagnostic.
The runner starts a minimal detached supervisor, which launches Codex in its own process group,
waits for it even if the runner dies, and atomically fsyncs an owner-only `process-status.json`.
That trusted status contains supervisor/child process identities, start/completion timestamps,
exit code or signal, and post-exit temp-file size/hash when present; it contains no model content.
The modeling sandbox is read-only and cannot write the generation metadata/status directory—the
Runtime client alone writes `draft.tmp`, and only trusted runner/supervisor code writes state.

After and only after a matching durable status proves `exit_code=0`, the runner fsyncs the temporary
file, performs the fail-closed secret and regular-file checks, atomically renames it to `draft.json`,
fsyncs the parent directory, and records `generated`. Full schema/reference validation then records
`validated`. The runner itself emits only a bounded JSON manifest. It never emits draft content.

If the runner dies while state is `running`, recovery never starts a second model immediately. It
first checks the recorded supervisor/child identity and durable process status:

- a matching live supervisor/child means `handoff_still_running`; recovery does not read its
  partial output;
- a matching durable `exit_code=0` status plus `draft.tmp` resumes the fsync,
  secret/regular-file checks, rename, and validation path without invoking Codex;
- a non-zero/signal status is `handoff_process_failed`; missing, invalid, mismatched, or
  unverifiable status after both processes terminate is `handoff_exit_status_unknown`; neither may
  publish, validate, or automatically rerun the model even when the temp file looks complete;
- `draft.json` already present means publication won the crash race; recovery recomputes its hash,
  requires the same matching exit-zero status, repairs state to `generated`, and validates it;
- no safe complete file, two live owners, changed process identity, or both temp/final with
  conflicting content is `handoff_state_conflict` and never an automatic model rerun.

## Generation state machine

```text
prepared -> running -> generated -> validated -> persisted -> cleaned
                     \-> blocked
```

- `prepared`: generation directory, immutable input metadata, and CAS reservation exist.
- `running`: a fresh ephemeral Codex process has started under the detached supervisor; a complete
  `draft.tmp` and exit status may exist after child exit but before publication, so recovery must
  apply the explicit running-state rules above.
- `generated`: `draft.json` has been atomically published after child success and minimal
  secret/regular-file checks; process success is separate from full structural validation.
- `validated`: secret scan, byte limit, raw hash, JSON parse, JSON Schema, unique client IDs,
  dependency/item references, item count, and canonical content hash pass.
- `persisted`: the main Agent supplies the platform Artifact ID and returned canonical hash; the
  runner verifies they match its validated generation.
- `cleaned`: complete local draft and copied prior draft are deleted; bounded manifest, hash,
  platform ID, state, and redacted diagnostics remain.
- `blocked`: failure code and redacted detail are durable. Secret detection deletes content
  immediately. Other invalid content remains only until a valid successor is persisted or the
  Build Session becomes terminal.

Every state transition rewrites `generation.json` atomically while holding the generation lock.
Deliberate test failpoints may terminate the runner while a successful or failing supervised child
continues, after durable child status with a complete temp file, after atomic rename before the
generated-state write, after `generated`, or after `validated`; they are test-only and cannot be
enabled by model content.

## Manifest contract

The bounded manifest is strict JSON and at most 4 KiB. It contains:

- `manifest_version`, `schema_version`, `build_session_id`, `artifact_key`;
- `generation_id`, optional `expected_previous_generation_id`, and `correction_round`;
- state and stable local locator relative to the controlled spool root;
- raw `sha256`, `canonical_content_hash`, `size_bytes`, and `item_count`;
- creation/validation timestamps and, after persistence, `workflow_artifact_id`;
- optional redacted failure code; never draft content, credentials, prompts, or hidden reasoning.

The manifest path and every content-derived field are recomputed by the runner. The subagent cannot
declare its own trusted size, hash, state, path, or platform ID.

## Validation boundary

Local validation, before any platform write, must perform:

1. regular-file and controlled-root checks; no symlink or path traversal;
2. exact byte count and raw SHA-256;
3. strict UTF-8 JSON parse and the existing unchanged
   `skills/ontology-builder/references/modeler-handoff.schema.json` contract;
4. the existing 1 MiB canonical Artifact limit;
5. exact seven top-level fields and Modeling Batch item count;
6. unique `client_item_id`, resolvable `depends_on` and item references, and no dependency cycle;
7. domain secret scanning with no secret echoed on failure.

The authorized main Agent then verifies Project/Build Session/Ontology alignment, Evidence
Reference accessibility, current Modeling Context/version, and any platform-dependent references.
It creates `artifact_type=modeling_draft`, uses `generation_id` as the stable client version ID,
passes the current Artifact ID as `supersedes_workflow_artifact_id`, and verifies the returned
canonical hash before marking the local generation persisted.

## Recovery and idempotency

Recovery always reads platform facts first, then the bounded local state:

- `prepared`: no child/result exists; report not-started and require the main Agent to decide
  whether to launch. Do not claim generation completed.
- `running`: apply the live-child/temp/final recovery rules above; never start another model while
  a matching child or recoverable result exists.
- `generated`: rerun local validation; do not call the model again.
- `validated` without matching Artifact: perform the idempotent Artifact create.
- matching Artifact without Batch: create the Batch once using stable IDs from the draft.
- Batch/Attempt/review already present: continue the first missing safe workflow step.
- matching Artifact and local payload present: mark persisted and clean; do not create a duplicate.

The runner uses an atomic `head.json` CAS per Build Session and artifact key. `prepare` succeeds only
when `expected_previous_generation_id` equals the current head. A concurrent loser returns
`generation_conflict`, writes no new head, and cannot persist or merge. Different artifact keys or
Build Sessions do not share a head lock.

The same generation ID with the same immutable inputs is idempotent. The same ID with different
inputs, schema, expected head, or content is `generation_id_conflict`. Platform stale-head and
idempotency conflicts remain authoritative and fail closed.

## Dry-run to exact apply

The modeler handoff intentionally contains a dry-run request envelope. The main Agent does not
apply that envelope verbatim and does not edit its immutable Batch content. It performs this fixed
transformation after reviewer PASS:

- reuse the persisted Batch's `client_batch_id`, `ontology_id`, normalized item set, item IDs, and
  Batch content hash exactly;
- create a distinct apply Attempt with a fresh stable apply idempotency key;
- set `mode=apply_atomic`, read the current allowed workspace version immediately before apply,
  and supply the main Agent's current lease token;
- reject any item/content-hash change by returning to a new immutable draft/dry-run/review cycle.

The Review Artifact records the immutable Batch ID/content hash and dry-run Attempt ID. The apply
Event records the same Batch ID/content hash plus the distinct apply Attempt ID. Acceptance asserts
that dry-run and apply attempts differ in mode/idempotency/workspace/lease envelope only, while both
reference the same immutable Batch content.

## Rework limit

A validation or review stage permits at most two automatic correction generations. Each uses a
fresh ephemeral Codex context and receives the complete previous draft plus structured failures.
The main Agent never edits the draft. A third automatic correction, or an earlier repeated
same-class failure, is blocked unless the command receives an explicit user-authorization marker
recorded in state and the platform timeline.

## Platform recording

No new public REST/MCP endpoint or database table is required. Existing facts are used as follows:

- Build Checkpoint records the current step and next safe action.
- Execution Event records generation/validation/persistence/blocker summaries without local
  absolute paths or content. Existing event types are used conservatively: `decision_recorded`,
  `artifact_created`, `rework_requested`, `blocked`, and `phase_completed`.
- Modeling Workflow Artifact stores the validated seven-field JSON and canonical hash.
- Modeling Batch, Attempt, Review Artifact, verification, lineage, and audit remain unchanged.

The local generation state is authoritative only before Artifact persistence. After persistence,
the platform Artifact is the sole content authority; recovery may delete or reconstruct local
bounded state from platform IDs but must never prefer an old file over the Artifact.

The exact first-version mapping is:

| Local milestone | Stable Execution Event | Stable Build Checkpoint |
| --- | --- | --- |
| `prepared` / `running` | none; these do not claim completion | existing prior checkpoint remains current |
| `generated` | client ID `r11003:<generation_id>:generation-completed`; `phase_completed`, `core_modeling`, completed | ID `r11003:<generation_id>:generated`; phase `modeling`; current `modeling_draft_generated`; next `validate_modeling_handoff` |
| `validated` | client ID `r11003:<generation_id>:handoff-validated`; `decision_recorded`, `core_modeling`, completed | ID `r11003:<generation_id>:validated`; current `modeling_handoff_validated`; next `persist_modeling_draft` |
| `persisted` | client ID `r11003:<generation_id>:artifact-persisted`; `artifact_created`, `core_modeling`, completed, output Artifact ID | ID `r11003:<generation_id>:persisted`; current `modeling_draft_persisted`; next `create_or_resume_modeling_batch` |
| `blocked` | client ID `r11003:<generation_id>:blocked:<failure-fingerprint>`; `blocked`, current phase, blocked | matching checkpoint ID suffix; current `modeling_handoff_blocked`; next `await_user_or_recover`; redacted failure |

The generation/validation events carry `generation_id`, `artifact_key`, relative spool locator,
manifest/schema version, raw hash, canonical hash, byte count, item count, correction round, and
expected previous generation in bounded `decisions`. They never carry an absolute path or content.
The persisted event replaces the locator as recovery authority with the Artifact ID. Checkpoints
repeat only generation ID, relative locator before persistence, hash, state, blocker, and next step.

At interruption point 1 the main Agent may not yet have recorded the generated milestone. Recovery
still reads platform state first, then the local head; after recovering the complete temp/final file
it idempotently appends the generated Event/Checkpoint using the original manifest timestamp before
continuing validation. At interruption point 2 it similarly appends any missing generated and
validated facts before idempotent Artifact creation. Stable client IDs make replay safe; existing
payload disagreement is a state conflict rather than a branch.

## Skill and Harness integration

`ontology-builder` documents the exact prepare/run/inspect/mark-persisted/cleanup sequence, fresh
context rule, two-round cap, platform-first recovery algorithm, and stop conditions. The existing
repo-local Harness records bounded command outcomes and platform-tool success but does not copy the
draft, manifest absolute path, or raw subprocess output into retrospectives.

Tests cover the handoff command directly and its interaction with Harness sanitization/finalization.
Runtime-neutral field names are used, but only the current Codex command is implemented.

## Errors

Stable local errors include `generation_conflict`, `generation_id_conflict`,
`handoff_process_failed`, `handoff_exit_status_unknown`, `handoff_file_missing`,
`handoff_file_unsafe`, `handoff_too_large`,
`handoff_hash_mismatch`, `handoff_schema_invalid`, `handoff_reference_invalid`,
`handoff_secret_detected`, `handoff_state_conflict`, `handoff_platform_hash_conflict`, and
`handoff_rework_limit`. Errors are non-zero, bounded, and redacted.

## Rollout and cleanup

This is a repo-local Codex/Skill delivery. No migration or frontend build is expected unless plan
review or implementation evidence proves otherwise. Terminal Build Session cleanup removes all
complete local payloads; crash leftovers are inspected by recovery and removed by a bounded-age
cleanup command. Cleanup refuses unknown roots, symlinks, active locks, or ambiguous ownership.

## Acceptance

Completion requires the shared test plan to pass, then one fixed-corpus Dify run that proves at
least 27 items, deliberately bounded terminal output, both required interruption points, exact
Artifact/Batch lineage, independent review/rework, main-Agent apply, competency queries,
validation, lineage, Build Session completion, cleanup, and no secret/credential exposure. That
run may close R1.1-004's remaining integration gate; repeatable business-value improvement remains
R1.1-001.

## Implementation result

Independent Round 5 completed the fixed-corpus Dify chain with 39 model items, 32/32 Coverage
Matrix alignment, 39/39 Evidence, immutable Draft Artifact
`02f62ea4-3bc7-4fa0-b9a4-2d299321c9e1`, applied Batch
`d3302dc5-6ea3-4a67-b9df-44f1f31bbb46`, PASS Review Artifact
`c59a9712-73bf-4b08-8fd7-c88d69a55dbc`, and final Verification Artifact
`9fc18f35-d0b7-4d31-8b1b-2a1053fcc742`. Dry-run, exact apply, Context Query, scoped SPARQL,
SHACL validation, lineage, Build Session completion, export, cleanup, and runtime restoration all
passed. The live run also required schema-summary/class-detail to read graph-scoped `owl:Class`
and `rdfs:Class` resources without duplicates. This closes R1.1-003 and R1.1-004; repeatable
business-quality improvement remains R1.1-001.
