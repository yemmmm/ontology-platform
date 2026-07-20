# R1.1-005 Claude Code Dual-Agent Modeling Harness Shared Test Plan

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-005
- Design:
  `docs/delivery/designs/2026-07-20-r1-1-005-claude-dual-agent-harness-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-1-005-claude-dual-agent-harness-delivery-record.md`
- Status: completed; plan review Round 2 PASS; independent test Round 2 PASS

## Completion gates

1. Plan reviewer reports PASS with no accepted Critical/High finding.
2. Existing 42 Harness/handoff tests and all new direct tests pass.
3. A real Claude Code Hook probe proves two distinct top-level session IDs bind one run, exchange
   mailbox messages, and capture nested modeler subagent events. An environment blocker keeps the
   requirement in progress and cannot yield tester PASS or completed delivery.
4. Independent tester reports PASS on a stable implementation state.
5. Requirements, design, runbook, delivery record, retrospective example/contract and status agree;
   scoped diff and commit contain no pre-existing semantic-context work.

## A. Static configuration and agent contracts

- Parse `.claude/settings.json`; assert every configured lifecycle event invokes the recorder via
  `${CLAUDE_PROJECT_DIR}` and no credential or machine-specific absolute path is committed.
- Validate all five Agent files have supported frontmatter, unique names, correct role boundaries,
  modeler-only platform authority, simulated-decision labeling, and fresh-context handoff guidance.
- Confirm runbook gives two-terminal commands, minimum/recommended version diagnostics, recovery,
  redaction, finalization, and explicit no-single-session-fallback behavior.

## B. Activation, identity, and compatibility

- Activate two distinct hook session IDs as `simulated_user` and `modeling_agent` for one run;
  status becomes ready only after both are present.
- Repeated same session/role activation is idempotent. Wrong/stale nonce, role collision, one session
  claiming both roles, unknown/third role, mode mixing, and project/Build Session mismatch fail.
- Concurrent activation yields one consistent participant map and registry without lost writes.
- Explicit participant replacement increments its epoch, invalidates the old registry and receipts,
  and accepts the replacement only after a new Hook-bound activation. Crash without SessionEnd, old
  delayed events, and concurrent replacement cannot revive the previous epoch.
- Existing no-role Codex activation, old metadata lookup, checkpoint, redact, repair and finalize
  behavior remain green.

## C. Visible interaction and decision provenance

- Execute Hook-authorized `message send/poll/ack` in both directions. Assert bounded sender,
  recipient, message kind, participant role, runtime session, epoch and order are recorded once.
- A role flag without a matching single-use PreToolUse receipt, replayed receipt, wrong command
  fingerprint, expired receipt, or receipt from the other session is rejected.
- Two sessions issuing otherwise identical mutations with different `operation_id` values consume
  only their own receipts. Reusing an operation ID with changed content or after consumption fails.
- Poll is documented and tested as read-only repo-local observability: it may read role-addressed
  bounded messages but cannot ack them, advance checkpoints, or claim session-level confidentiality.
- Approval/rejection/answer from simulated user is always `agent_reported` plus `simulated=true`;
  attempts to label it `user_reported` are normalized or rejected. No platform approval write occurs.
- Duplicate hook delivery is idempotent. Overlong text is bounded; secret-bearing content stores no
  original and can be replaced through redaction.
- Full unbounded prompt, transcript path, chain-of-thought, nonce and raw tool result do not appear
  in events, summary inputs or retrospectives; a scanned and bounded visible prompt may be retained.

## D. Nested agents, tasks, and phase authority

- Claude `PreToolUse Agent` and `Task` recognize `subagent_type`; extraction, analysis and reviewer dispatch,
  start, stop, agent ID and bounded last message are correlated under the modeling participant.
- TaskCreated/TaskCompleted/TeammateIdle/StopFailure/SessionEnd payloads produce bounded deduplicated
  events and tolerate optional fields across Claude versions.
- Equivalent nested-agent/task events from the simulated-user participant cannot create modeling
  phase checkpoints or masquerade as the modeler.
- Successful platform modeling tool calls from the modeler preserve stable IDs and checkpoints;
  failed tool results and simulated-user calls do not. Each participant's Stop consumes only its own
  pending state.
- Direct `checkpoint` CLI use in dual mode requires a receipt bound to `modeling_agent`; the
  simulated-user session, a naked CLI call, and a stale participant epoch are rejected.

## E. Summary, lifecycle, and recovery

- Stub Claude summary process to prove schema serialization, clean command/environment, allowed
  authentication source, empty working directory, no tools, no persistence, timeout, envelope and
  secret checks. Validate normal `structured_output`, missing output, extra stdout, authentication
  failure and timeout; invalid output leaves cursor intact.
- Legacy Codex summary command remains unchanged and existing tests pass.
- Participant interruption/restart preserves registry and next sequence; one Stop does not finalize
  the run. Explicit completed/cancelled finalization summarizes all participants and publishes one
  redacted retrospective; paused/interrupted stays local.
- `repair` resumes from saved cursor without duplicate summaries or events.

## F. Real runtime probes

- Record `claude --version`; diagnose installed versions below the documented/tested path rather than
  silently changing topology.
- From two separately launched top-level Claude sessions, activate opposite roles with distinct
  session IDs, exchange through the mailbox at least one visible question and one simulated
  answer/approval, acknowledge delivery, and inspect the shared status/events.
- In the modeler session invoke one extraction subagent and verify `subagent_type`, start/stop and
  result summary. Do not count a `task_type=local_agent` as the second main session.
- Launch a fresh no-tools Claude summary subprocess and validate its schema-conforming output.
- Use only synthetic scenario content and a unique temporary run; finalize or remove only that run.

## G. Required checks and independent handoff

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`.
- Ruff check and format-check on every changed Python file.
- JSON parse for `.claude/settings.json`, `.codex/hooks.json`, and summary schema.
- `python skills/ontology-builder/evals/validate_skill.py` if the Skill is changed.
- `git diff --check`; inspect `git status --short` and staged diff to exclude unrelated work.
- GitNexus `detect_changes(scope="compare", base_ref="main")` or scoped equivalent before commit.
- No backend/frontend modification means no service restart; if scope changes, apply repository test
  and restart rules in full.

## Independent test rounds

Rounds are append-only. Earlier failures remain below with the final PASS.

### Round 1 — 2026-07-20 — FAIL

- Verdict: **FAIL**. The real dual-session path passed, but the real Claude structured-output
  summarizer hard gate failed. This is a release-blocking High finding; the requirement cannot be
  marked complete on this implementation state.
- Handoff digest: `2eda250b4d375401cb7dcd22bcc61c3c03066a2cee94807ef872e8c4e5bd5ea4`.
  Independent recomputation over the stated `.codex` runner/test/runbook and `.claude`
  settings/runbook/Agent file set produced
  `ae7c08d64592b3ed68ce992f9beae25c8717dfa23a1a75f38df125b2d473dcb6`; the digest procedure or
  implementation stability must be reconfirmed before Round 2.
- Unit/static results:
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`:
    PASS, 50 tests in 12.392 seconds.
  - `cd backend && uv run ruff check ../.codex/hooks/modeling_harness.py
    ../.codex/tests/test_modeling_harness.py`: PASS.
  - `cd backend && uv run ruff format --check ../.codex/hooks/modeling_harness.py
    ../.codex/tests/test_modeling_harness.py`: PASS, two files already formatted.
  - Python JSON parsing of `.claude/settings.json`, `.codex/hooks.json`, and
    `.codex/hooks/summary.schema.json`: PASS.
  - `git diff --check`: PASS.
  - Static contracts: PASS. Project Hook commands use `${CLAUDE_PROJECT_DIR}`; five Agent
    definitions are distinct and keep modeler-only platform authority, fresh-context handoff, and
    simulated-decision labeling; the runbook covers two terminals, version diagnosis, recovery,
    redaction, finalization, and rejects a one-session/local-agent substitute.
- Identity/authorization review: PASS at the reviewed boundary. Dual mutations derive role,
  runtime session, and participant epoch from a Hook-created single-use receipt; `operation_id`,
  command fingerprint, current participant binding, expiry, invalidation, and consumption are all
  checked. A naked CLI `--participant-role` cannot authorize send, ack, or checkpoint. Poll remains
  the explicitly documented role-addressed, read-only local observability exception and cannot ack
  or advance workflow state.
- Real runtime versions: installed `claude` is `2.1.153`; the hard-gate run used
  `npx -y @anthropic-ai/claude-code@latest`, version `2.1.215`.
- Real dual-session probe: PASS for run `claude-e2e-5565db8920ea6e68`, Build Session
  `synthetic-build-9a4ac33b7226f8ca`, project `synthetic-project-ee35895c14d2ce47`.
  - Simulated-user top-level session: `6342fd79-f7ea-48de-95a8-61631ef5386f`.
  - Modeling-agent top-level session: `2d927f99-d003-4750-aabb-4e15f40dbef2`.
  - Both sessions independently ran Hook-bound activation and status became `ready=true`.
  - The modeler sent clarification `msg-12451938166df2c0c7bd`; the simulated user polled it and
    sent approval `msg-1ee0c0433d08e2c3724b`; the modeler polled and acknowledged that message.
    Event 12 records `report_source=agent_reported` and `simulated=true`.
  - The resumed modeler used the real `Agent` tool with `subagent_type=source-extractor`.
    Events 17–19 contain bounded `delegation_intent`, `subagent_started`, and
    `subagent_stopped`, all bound to the modeling participant and agent ID
    `aeda5f7da590a3349`. This was a nested local agent, not miscounted as the second top-level
    session.
  - Both `-p` invocations emitted `SessionEnd`, but metadata remained active and neither Stop nor
    SessionEnd prematurely finalized the run.
  - Run-file scan found no raw activation nonce, `agent_transcript_path`, API key, or common secret
    marker. Metadata contains only an `activation_nonce_hash` field.
- Real summary probe: **FAIL**.
  - Direct controlled call to `invoke_claude()` with the installed 2.1.153 executable failed with
    `HarnessError: Claude summarizer omitted structured_output`.
  - Repeating the runner's command contract with 2.1.215 and the checked-in schema failed before
    inference with: `Error: --json-schema is not a valid JSON Schema: no schema with key or ref
    "https://json-schema.org/draft/2020-12/schema"`.
  - A diagnostic-only invocation that removed the top-level `$schema` declaration returned a
    `structured_output` object and passed `validate_delta`. This isolates the defect to the Claude
    CLI schema adaptation; the checked-in schema may remain authoritative, but the command must
    pass a Claude-compatible projection and test it explicitly.
- Cleanup: the unique synthetic run was not finalized and no retrospective was published. It is
  intentionally retained under
  `workspaces/ontology-harness/claude-e2e-5565db8920ea6e68/` as Round 1 defect evidence; no other
  run was removed. The diagnostic summary subprocess used a temporary directory and left no
  product artifact.
- Required repair before Round 2: adapt the schema passed by `claude_command` to the Claude CLI's
  accepted dialect, add regression coverage that asserts the incompatible `$schema` declaration is
  not passed, and rerun both the real structured-output subprocess and the complete independent
  suite on a newly frozen digest.

### Round 2 — 2026-07-20 — PASS

- Verdict: **PASS** on stable implementation digest
  `80704b577cdf1a09a2ffd6e71cc114113731609c0e8add9c6fef147528d388f4`, computed with
  `{ sha256sum .codex/hooks/modeling_harness.py .codex/tests/test_modeling_harness.py
  .codex/modeling-harness.md .claude/settings.json .claude/modeling-harness.md
  .claude/agents/*.md; } | sha256sum`. The digest was identical before and after the runtime and
  cleanup probes.
- Repair review: PASS. `claude_command` copies the checked-in schema, removes only the unsupported
  top-level `$schema` declaration from the disposable CLI argument, and leaves the authoritative
  schema bytes and Luna path unchanged. The new regression test compares every remaining key,
  including `additionalProperties`, `required`, `properties`, and `$defs`.
- Unit/static results:
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`:
    PASS, 51 tests in 17.740 seconds.
  - `cd backend && uv run ruff check ../.codex/hooks/modeling_harness.py
    ../.codex/tests/test_modeling_harness.py`: PASS.
  - `cd backend && uv run ruff format --check ../.codex/hooks/modeling_harness.py
    ../.codex/tests/test_modeling_harness.py`: PASS, two files already formatted.
  - Python JSON parsing of `.claude/settings.json`, `.codex/hooks.json`, and
    `.codex/hooks/summary.schema.json`: PASS.
  - `git diff --check`: PASS before and after the probe cleanup.
  - Static Agent/settings/runbook and receipt/identity findings from Round 1 remain unchanged by
    the narrowly scoped schema adapter repair.
- Real Claude structured-output adapter: PASS with
  `npx -y @anthropic-ai/claude-code@latest` version `2.1.215`. A controlled import of the real
  runner replaced only the executable prefix (`claude` with the latest `npx` package), preserving
  all arguments, the isolated temporary working directory, clean environment, no-tools and
  no-persistence settings. `invoke_claude` returned all ten required keys, `validate_delta`
  accepted the result, and inspection confirmed `SCHEMA_DECLARATION_PASSED False`.
- End-to-end finalization: PASS using the retained Round 1 run
  `claude-e2e-5565db8920ea6e68` and the same latest executable substitution.
  - Final state was `status=completed`, `terminal_state=completed`,
    `finalization_status=published`, `last_summary_error=None`.
  - The summary cursor advanced from 0 through all 22 events in one delta `(1, 22)` and the
    generated retrospective SHA-256 was
    `75bf575b1cef9a8db7f2b28965557626a0d374595f108c2394bab76b2fa31db5`.
  - The retrospective preserved both top-level participant roles, the clarification, simulated
    approval provenance, acknowledgment, and source-extractor dispatch/start/stop result. It did
    not convert the simulated decision into human/platform authorization.
  - Finalization recorded two transient failed summary attempts before a retry passed. The bounded
    retry contract worked and publication occurred with no remaining error; this is a low residual
    nondeterminism/observability risk rather than a completion blocker.
  - A second scan of metadata, events, state, session summary, and retrospective found no raw
    activation nonce, `agent_transcript_path`, API key name/value, or common Anthropic secret
    marker. The adapter repair did not alter the existing mailbox, ack, subagent, SessionEnd, or
    participant-identity events.
- Cleanup: after verifying publication, the exact synthetic run directory and its one generated
  retrospective were moved with `gio trash`; both are absent from the repository and recoverable
  from the desktop trash. The now-empty generated `docs/modeling-retrospectives/` directory was
  removed. No other Harness run or retrospective was changed, and `git status --short` shows no
  probe artifact.
- Environment note: the system-installed CLI remains `2.1.153`, below the runbook's tested path;
  the hard gate passed against 2.1.215. The checked-in runbook correctly requires upgrade/version
  diagnosis and forbids silently replacing two top-level sessions with one local agent.
