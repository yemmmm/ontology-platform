# Repo-local modeling Harness

This Harness records one legacy `ontology-builder` main Codex session for later process review and
also provides the common recorder for the Claude dual-session experiment. It is local to this
repository: `.codex/hooks.json`, `.claude/settings.json`, and `.codex/hooks/` implement it, while runtime
files stay under the gitignored `workspaces/ontology-harness/`. It does not replace platform
Modeling Workflow Artifacts or Execution Events.

For the two-top-level-session workflow, use [the Claude runbook](../.claude/modeling-harness.md).
The no-role command below remains the compatible version-1 Codex activation path.

R1.1-003 modeler payload transport is a separate local mechanism documented in
[`modeling-handoff.md`](modeling-handoff.md). The Harness records only its bounded command outcome;
it never copies the Manifest locator, draft, prompt, subprocess output, or absolute spool path into
events or retrospectives.

## Trust before activation

Open `/hooks` in Codex and review/trust the exact project Hook hashes. Repeat this after changing
`.codex/hooks.json`, `.codex/hooks/modeling_harness.py`, or `summary.schema.json`. Never use
`--dangerously-bypass-hook-trust` as a substitute for interactive review. If activation reports
`this session is not being recorded`, continue platform modeling only after showing that warning;
do not claim that a retrospective is being captured.

## Lifecycle commands

The main Agent generates a unique run ID and a random 24+ character nonce, then executes this exact
shape from the repository root. The trusted `PreToolUse` Hook binds the current Codex session; the
CLI only verifies that acknowledgment and cannot activate itself.

```bash
python3 .codex/hooks/modeling_harness.py activate \
  --run-id <unique-run-id> \
  --activation-nonce <random-one-time-nonce> \
  --build-session-id <platform-build-session-id> \
  --project-id <platform-project-id>
```

Successful platform `record_modeling_execution_event` phase events are authoritative checkpoints.
When the platform is temporarily unavailable, record an explicitly local checkpoint:

```bash
python3 .codex/hooks/modeling_harness.py checkpoint \
  --run-id <run-id> \
  --phase <phase> \
  --event-type <phase_completed|review_completed|rework_requested|blocked|verification_completed> \
  --summary '<redacted user-visible summary>' \
  --client-checkpoint-id <unique-id>
```

If the scanner rejects an event, it stores no original value. Supply a user-reviewed replacement:

```bash
python3 .codex/hooks/modeling_harness.py redact \
  --run-id <run-id> --for-sequence <sequence> \
  --replacement '<redacted substitute>'
```

Successful `complete_build_session` or `cancel_build_session` calls automatically finalize. A
manual terminal retry uses `finalize`; unresolved Luna failures stay `finalization_pending`, and
`repair` retries from the saved cursor:

```bash
python3 .codex/hooks/modeling_harness.py finalize \
  --run-id <run-id> --terminal-state <completed|cancelled|paused|interrupted>
python3 .codex/hooks/modeling_harness.py repair <run-id>
```

Only fully summarized `completed` or `cancelled` runs publish a redacted document under
`docs/modeling-retrospectives/`. Paused/interrupted runs remain local. There is currently no timed
cleanup; remove uniquely identified raw run directories only through an explicit operator action.

## Verification

```bash
python3 -m unittest discover -s .codex/tests -v
```

Luna runs as a fresh ephemeral `gpt-5.6-luna` session with medium reasoning, an empty temporary
working directory, a restricted environment, read-only sandbox, ignored user config/rules, Hooks
disabled, web disabled, and all other nonessential tool features disabled. Invalid safety config,
output, timeout, or process failure leaves the event cursor unchanged.
