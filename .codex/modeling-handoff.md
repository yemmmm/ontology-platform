# Reliable modeler handoff

`.codex/modeling_handoff.py` is the R1.1-003 repo-local transport for a Codex modeler's complete
seven-field JSON. Runtime files live only under the gitignored
`backend/.local/modeling-handoffs/`. The command prints a bounded Manifest; it never prints the
draft, prompt, subprocess stdout, credential, or absolute spool path.

Run commands from the repository root. `prepare` copies the explicit, secret-scanned input bundle
into an owner-only generation directory and atomically advances the Build Session/artifact-key
head. Input names are logical names, not model-controlled paths.

```bash
python3 .codex/modeling_handoff.py prepare \
  --build-session-id <build-session-id> \
  --artifact-key <modeling-draft-artifact-key> \
  --generation-id <stable-generation-id> \
  --correction-round 0 \
  --input prompt.md=<explicit-modeler-prompt> \
  --input business-pack.json=<versioned-pack-json> \
  --input coverage-matrix.json=<versioned-matrix-json> \
  --input modeling-context.json=<current-context-json> \
  --input evidence-index.json=<evidence-index-json> \
  --prompt-input prompt.md
```

Start a fresh credential-free modeler. The runner always uses `codex exec --ephemeral
--ignore-user-config`, the checked-in output schema, a read-only sandbox, a restricted environment,
discarded stdout, and a detached supervisor. Ignoring user config prevents a global
`$CODEX_HOME/config.toml` from auto-starting MCP servers; `HOME`/`CODEX_HOME` remain available only
so Codex can locate its file-backed authentication, while platform/MCP credential environment
categories and credential-bearing proxy URLs are removed. Do not use `codex exec resume`.

The supervisor drains stderr through a bounded in-memory scanner. It never creates a raw stderr
file; durable process status contains only byte counts, boolean drain state, and secret category
names, never prompt/source text, diagnostics, hidden reasoning, or matched secret values.

```bash
python3 .codex/modeling_handoff.py run \
  --build-session-id <build-session-id> \
  --artifact-key <modeling-draft-artifact-key> \
  --generation-id <stable-generation-id>
```

## Platform-first recovery

Before every local `inspect`, the main Agent must read Build Context, Build Session, Workflow
Artifacts, Execution Events, Modeling Context, and Batch state from the platform. Then:

- if the matching Artifact exists, verify `client_version_id == generation_id` and the canonical
  hash, call `mark-persisted`, and continue from the first missing Batch/Attempt/review step;
- if platform state says generated/validated but not persisted, run `inspect`; it recovers only a
  matching exit-zero supervised result and never starts Codex again;
- if state is `prepared`, the main Agent decides whether to launch; `prepared` is not generation
  completion;
- `handoff_still_running` means wait/inspect; do not launch another modeler;
- every other failure code is fail-closed. Record the bounded blocker and do not create an
  Artifact/Batch, dry-run, acquire a Lease, review, or apply.

```bash
python3 .codex/modeling_handoff.py inspect \
  --build-session-id <build-session-id> \
  --artifact-key <modeling-draft-artifact-key> \
  --generation-id <stable-generation-id>
```

After local validation, the authorized main Agent performs Project/Session/Ontology alignment,
Evidence Reference accessibility, current Modeling Context/version, and platform-reference checks.
Create `artifact_type=modeling_draft` with `client_version_id=generation_id` and the exact current
Artifact ID as `supersedes_workflow_artifact_id`. Verify the returned platform canonical hash, then:

```bash
python3 .codex/modeling_handoff.py mark-persisted \
  --build-session-id <build-session-id> \
  --artifact-key <modeling-draft-artifact-key> \
  --generation-id <stable-generation-id> \
  --workflow-artifact-id <platform-artifact-id> \
  --canonical-content-hash <platform-canonical-sha256>
```

This removes the complete draft and copied inputs. The bounded Manifest/hash/platform ID remain.
At Build Session completion or cancellation, remove only that unique Session spool:

```bash
python3 .codex/modeling_handoff.py cleanup-session \
  --build-session-id <build-session-id>
```

An operator may remove inactive crash leftovers older than a bounded age with `cleanup-stale`.
Cleanup refuses active locks, symlinks, unknown roots, ambiguous ownership, and a threshold below
60 seconds.

## Rework and concurrency

A correction uses a new generation ID and a new ephemeral context. Include the previous complete
draft, Pack, Matrix, current Modeling Context, schema version, structured Findings, and exact
correction scope as explicit inputs. Pass `--expected-previous-generation-id`, increment
`--correction-round`, and pass `--failure-class`. The main Agent must not edit either draft.

Two automatic correction generations are allowed. A repeated same-class failure or round 3 is
`handoff_rework_limit`; only an explicit user decision recorded on the platform may be supplied as
`--user-authorization-id`. CAS conflicts are `generation_conflict`; identical generation inputs
are idempotent and changed inputs under the same ID are `generation_id_conflict`.

## Stable platform facts

Use the event/checkpoint mapping frozen in the R1.1-003 design. Generated, validated, persisted, and
blocked facts use stable `r11003:<generation-id>:...` client IDs. Before persistence, only the
relative Manifest locator may be recorded. After persistence, the Artifact ID replaces the local
locator as recovery authority. Never put content or an absolute spool path in an Event,
Checkpoint, Harness record, or retrospective.
