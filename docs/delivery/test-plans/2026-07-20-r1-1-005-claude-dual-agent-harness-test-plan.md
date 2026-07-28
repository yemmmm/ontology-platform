# R1.1-005 Claude Code Dual-Agent Modeling Harness Shared Test Plan

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-005
- Design:
  `docs/delivery/designs/2026-07-20-r1-1-005-claude-dual-agent-harness-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-1-005-claude-dual-agent-harness-delivery-record.md`
- Status: DEPRECATED and superseded by `skills/ontology-modeling/`; historical PASS evidence only

> [!CAUTION]
> These tests describe the retired ClaudeCode Harness and are not completion gates for new modeling
> work.

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

## Fast-local extension completion gates

The extension reopens delivery history without invalidating strict-eval Round 2. Completion requires:

1. Plan review reports PASS with no accepted Critical/High finding for the extension.
2. Existing strict dual/legacy tests and all new fast-local tests pass.
3. Independent tester reports PASS on a stable implementation state and appends a new round below.
4. A real local API call creates and cancels a unique Build Session; a real MCP stdio client lists
   and calls the authenticated ontology-platform server; a controlled Claude CLI probe proves
   predetermined session ID and strict MCP source isolation. GUI launch is exercised when safe and
   otherwise recorded as unexecuted with `--no-launch` coverage.
5. Scenario/config/runbook/requirement/design agree, test artifacts are uniquely cleaned, and actual
   local API key values are absent from the staged diff and commit increment.

### H. Fast preparation and compatibility

- `prepare-fast` validates IDs, scenario location and distinct UUID sessions, atomically creates
  `evaluation_profile=fast_local`, `summary_policy=explicit`, two active participants/registries and
  bounded preparation events. Status exposes profile/readiness without nonce or credential.
- Existing run/session conflict, same UUID for both roles, missing/outside-repo scenario, malformed
  configuration and partial write failures fail closed. Repeating identical preparation is
  idempotent; changed identity data is rejected.
- Concurrent different run IDs sharing one session UUID serialize through the root registry lock;
  exactly one completes and no registry points at the rejected run. Inject a failure after every
  metadata/state/event/registry durable write, then retry: incomplete metadata never becomes ready,
  Hooks reject it, matching partial registries are repaired, and the final identity graph is whole.
- Assert the final `preparation_complete=true` metadata write is the commit point after required
  events. Failures before it clean/repair only matching incomplete state; a retry deduplicates any
  pre-commit events. Once it succeeds, no required preparation write remains that could trigger
  rollback of a ready participant registry.
- Strict activation and participant replacement use the same registry lock, so they cannot race a
  fast preparation for the same runtime session.
- Strict Hook activation, participant replacement/epoch, operation receipts, legacy Codex and
  activation commands with harmless trailing shell tokens remain green.
- Fast terminal platform completion records a local-only terminal state without spawning summary;
  explicit publish/repair uses the existing Claude structured-output path.

### I. Launcher, scenario, MCP, and credential boundaries

- Parse the checked-in scenario and empty MCP JSON. Reject missing required fields, secret-like
  scenario content, missing corpus path and non-repository paths.
- With a fake HTTP server and fake terminal executable, prove health check, authenticated Build
  Session creation, unique client/session/run IDs, argv-safe two-process launch, modeler-only
  ontology MCP config, simulated-user empty MCP config, initial prompts and no credential leakage.
- Assert launcher argv uses `--mcp-config=<path>` as one token and strict mode; the known variadic
  space form must not appear. An existing non-terminal active-run locator blocks before Build
  Session creation unless explicit locator replacement is requested.
- Persist launch intent before POST. Simulate crash immediately after HTTP 201, retry the same run,
  and assert the identical payload/client ID receives HTTP 200 and only one Build Session exists.
  Changed-payload retry fails locally; explicit recovery rejects missing, terminal and foreign-
  Project sessions before Harness preparation.
- `--no-launch` prepares the run without a terminal process and prints only bounded stable IDs and
  reproducible commands. Missing GUI support gives an actionable error unless `--no-launch` is used.
- Real-runtime probe uses the ignored local credential without printing it, creates/cancels only a
  unique Build Session, and cleans uniquely identified Harness/session artifacts.
- A real MCP stdio client confirms authentication, tool inventory and one bounded read call. A
  persisted controlled Claude probe must reference only `ontology-platform` under strict config;
  the simulated-user command must use the empty config. The same probe asserts expected session ID
  and receipt of the exact bounded positional initial prompt.
- Read actual API-key values from ignored local runtime files only inside the final scanner; assert
  none occur in `git diff --cached`, tracked files changed by this delivery, or the new commit diff.

### J. Fast-local real workflow smoke

- Run launcher `--no-launch` against the real service and default Dify scenario. Confirm a new
  active Build Session, ready dual Harness state, distinct predetermined session IDs, profile and
  scenario locator; cancel/finalize only that unique run after inspection.
- If GUI launch is executed, verify two distinct Claude processes receive their initial prompts and
  Hooks update last-seen under the pre-bound roles without manual activation input. Confirm the
  modeler session exposes ontology-platform MCP and the simulated-user session exposes none.
- Do not require a full Dify ontology rebuild to close this infrastructure optimization; strict
  modeling-quality experiments remain under R1.1-001 and strict-eval remains the R1.1-005 hard gate.

### Fast-local independent test rounds

Rounds below are append-only and start at Round 3 because strict-eval already used Rounds 1–2.

### Round 3 — 2026-07-21 — FAIL

- Verdict: **TEST_FAIL** on the stable implementation digest
  `d8ae11b817d24566101f679ca15c56b53c3155f49015bc9e734c13686e1e342b`. Independent
  recomputation with the delivery handoff's exact `sha256sum` file set matched before the probes.
  The deterministic Harness, platform API, and direct MCP paths passed, but the real Claude launch
  argv did not provide the promised MCP isolation or expose ontology-platform to the modeler.
- **High — real Claude MCP isolation/configuration contract fails.** With the installed Claude Code
  `2.1.74`, both actual launcher-shaped commands used `--agent`, predetermined `--session-id`,
  `--dangerously-skip-permissions`, `--strict-mcp-config`, and the required single-token
  `--mcp-config=<absolute-path>` before one final prompt. Both returned exit 0 and their persisted
  transcripts contained the exact positional prompt and expected session ID. However:
  - the `ontology-modeling-agent` reported only `4_5v_mcp` and `web_reader`, and explicitly reported
    that ontology-platform was not registered as an online MCP tool;
  - the `simulated-user` command using `.claude/empty-mcp.json` also reported those same two MCP
    sources instead of an empty MCP surface;
  - transcript tool prefixes confirmed the two unexpected sources. Therefore the current launcher
    neither gives the modeler its required platform MCP nor removes unrelated MCP startup/context,
    which defeats the principal fast-local optimization and blocks completion.
  - A diagnostic `claude --strict-mcp-config --mcp-config=<config> mcp list` also listed unrelated
    configured/plugin MCPs for both the ontology and empty configs. Its raw local output included a
    credential embedded in an unrelated plugin command, so that raw output was deliberately not
    copied into this repository or this record. No credential value appears here.
- **Medium — existing corpus directories are rejected as missing.** The checked-in default scenario
  currently points to the snapshot's existing `manifest.json` file and parses successfully. The
  corpus itself is the existing directory
  `docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a`.
  Calling the launcher's path helper for that real directory reproduces
  `LauncherError: scenario corpus does not exist`: `repo_path(..., must_exist=True)` requires
  `is_file()` before `load_scenario` reaches its explicit file-or-directory check. Directory-shaped
  corpus locators therefore cannot satisfy the apparent contract, and the launcher tests cover only
  a temporary file corpus plus a missing file.
- Unit/static checks:
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`: PASS, 63 tests in
    17.272 seconds. This includes strict dual/legacy, harmless trailing shell token parsing,
    participant replacement/epoch, receipt, summary, root-lock concurrency, every fast preparation
    durable write fault/retry, launch-intent retry, recovery ownership, and explicit publish tests.
  - `uv --directory backend run ruff check ../.codex/hooks/modeling_harness.py
    ../.codex/fast_local_launcher.py ../.codex/tests/test_modeling_harness.py
    ../.codex/tests/test_fast_local_launcher.py`: PASS. Ruff format-check on the same four files:
    PASS, four files already formatted. A first chained shell attempt changed into `backend` and made
    the following relative `cd`/JSON command invalid; the checks were rerun from repository root with
    `uv --directory backend`, so that operator-command error is not a product failure.
  - Python JSON parsing of `.claude/settings.json`, `.codex/hooks.json`, the summary schema,
    ontology/empty MCP configs, tracked fast-local config example, and tracked scenario: PASS, seven
    files. `git diff --check`: PASS.
  - Static implementation audit: PASS for root `.sessions` registry locking across strict
    activation, fast preparation, and participant replacement; incomplete preparation Hook
    rejection; preparation-ID cleanup; the final ready metadata commit marker after required events;
    durable pre-POST launch intent and same-payload retry; active/owned recovery checks; exact
    one-token MCP argv construction; local-only explicit-summary terminal behavior and explicit
    `finalize --publish`.
- Real platform/MCP probes:
  - A unique authenticated REST create returned 201/active for Build Session
    `15aafc39-9409-4500-8d51-f15a2cfe4b60`, revision 2. Exact cleanup cancel returned
    200/cancelled, revision 3. The credential was loaded internally and never printed.
  - A real Python MCP stdio client started the checked-in ontology-platform command, listed 64 tools,
    found `get_project_build_context`, and called it for the configured Project with
    `isError=false`, `ok=true`, and an object result. This proves platform authentication/server
    health independently of the failed Claude configuration surface.
  - `python3 .codex/fast_local_launcher.py --no-launch` against the real ignored config returned 2
    with the expected non-terminal active-locator guard. Hash comparison proved
    `active-run.json` was unchanged; code/order and the zero-output guard prove refusal occurred
    before intent/POST/Harness/terminal work. The existing strict run was not replaced, finalized,
    cancelled, or edited.
  - `ontology-platform.service` was active; backend `/api/health` returned `ok` and frontend `/`
    returned HTTP 200. No backend/frontend files changed, so no restart was required.
- Credential gate: a final scanner loaded the actual `ONTOLOGY_MCP_API_KEY` value from ignored local
  runtime configuration without printing it. The value had no occurrence in changed tracked files,
  the unstaged delivery diff, or the empty staged diff. One actual value was checked; plaintext hits
  were zero.
- Cleanup and unexecuted scope: the three unique controlled Claude probe transcripts and their
  matching session-environment directories were moved with `gio trash`; they are absent from the
  active Claude directories and recoverable from desktop trash. The unique REST Build Session was
  cancelled. No Harness run was created by the guarded real launcher. Real GUI launch was not
  executed because it would require replacing the user's non-terminal active locator and the same
  commands already fail the MCP isolation gate; this non-execution is not the cause of FAIL.
- Required repair before Round 4: make actual launcher-shaped Claude sessions expose only
  ontology-platform to the modeler and no MCP to the simulated user on the supported local runtime,
  or fail before platform mutation with a bounded actionable incompatibility/version diagnosis.
  Add a controlled real-runtime regression rather than relying only on argv inspection. Also make
  corpus path validation consistently accept the intended checked-in file/directory shapes and add
  a real-directory test. Freeze a new implementation digest, rerun the full suite and real probes,
  and append Round 4 without rewriting this failed history.

### Round 4 — 2026-07-21 — FAIL

- Verdict: **TEST_FAIL** on stable implementation digest
  `c839e5fc0a36ccb426e6b15fe6425aa150ecea4e9f58af1b769012ce44a06db1`. Independent
  recomputation used the exact handoff ordering across the two Agent definitions, runbook, three
  tracked JSON inputs, Harness, launcher, and two test modules, and matched before testing. The two
  Round 3 defects are directly closed, but a new exact-inventory fail-closed defect remains.
- Round 3 High closure: **PASS for the current unsupported runtime boundary.** The installed Claude
  Code remains `2.1.74`. A direct real `probe_claude_mcp_isolation` invocation captured rather than
  echoed both inventory streams and failed in 0.67 seconds with a bounded message containing all of
  `2.1.215`, `strict-eval`, and `No platform state was created`. The raw `mcp list` stdout/stderr was
  never emitted or persisted because local plugin command text may contain credentials.
  - A real-run ordering probe loaded the actual ignored config and scenario, bypassed only the
    existing active-locator guard in memory, and left the real isolation probe intact. It raised the
    same actionable error with `prepare_intent=0` and `request_json=0`; launch-intent filenames,
    active-locator SHA-256, and GUI state were unchanged. Static order confirms the executable and
    inventory gate precede run-ID generation, launch-intent persistence, health/HTTP, Build Session,
    Harness preparation, locator replacement, command construction, and terminal launch.
  - Launcher commands and probe commands use `--setting-sources=project`,
    `--strict-mcp-config`, and exactly one single-token `--mcp-config=<absolute-path>`. The two
    inventory cases require the ontology config for the modeler and the checked-in empty config for
    the simulated user. Fake supported-runtime coverage proves the intended positive one-server and
    zero-server paths continue into no-launch/Harness and two argv-safe terminal commands.
  - The current machine therefore cannot claim a successful fast-local GUI run until Claude is
    upgraded and the real inventory passes. This is the intended compatibility boundary, not a
    successful runtime smoke or a fallback to one session.
- Round 3 Medium closure: **PASS.** The default checked-in scenario loads its existing
  `manifest.json` file, and an in-memory scenario variant pointing at the real repository snapshot
  directory
  `docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a`
  also loads successfully. Existing directory paths are still rejected when used as the scenario
  JSON, fast-local config JSON, or credential env file; an outside-repository corpus locator is
  rejected. Unit coverage exercises the same file/directory distinctions.
- **High — inventory acceptance is not exact and can accept an unusable/wrong server.** The probe
  first identifies status-looking lines but then validates the modeler case with
  `expected_server in inventory[0]`. It neither parses the server name before the first colon nor
  requires a healthy connected status. Controlled subprocess results reproduce three false PASS
  cases while the simulated-user case correctly reports no servers:
  - the sole server name `ontology-platform-shadow` is accepted;
  - the sole server `other-server` is accepted when its command text contains
    `/tmp/ontology-platform-adapter`;
  - an exact `ontology-platform` line with `Failed to connect` is accepted when the CLI command
    exits zero.
  A runtime with one wrong or unhealthy source can therefore pass the preflight, create platform
  state, and launch sessions even though the modeler lacks the required authenticated MCP. This
  violates the exact role inventory and fail-before-mutation contract and blocks Round 4.
- Unit/static results:
  - `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .codex/tests -q`: PASS, 66 tests in
    18.572 seconds. Strict/legacy, receipt/epoch/summary, root registry lock, fault/retry,
    launch-intent, active-locator, supported fake runtime, pre-HTTP incompatibility, and corpus path
    suites remain green.
  - `uv --directory backend run ruff check` and `ruff format --check` over the Harness, launcher,
    and both test modules: PASS; four files already formatted.
  - Python parsing of `.claude/settings.json`, `.codex/hooks.json`, summary schema,
    ontology/empty MCP configs, tracked config example, and tracked scenario: PASS, seven files.
    `git diff --check`: PASS.
  - One independent test script initially patched the shared `subprocess.Popen` object while trying
    to count impossible GUI calls; that also affected Python's internal `subprocess.run` and caused
    a local `ValueError`. The invalid test instrumentation made no product or platform mutation and
    was removed before the successful ordering probe above.
- Runtime and non-repeated integration evidence:
  - The real active-locator path was exercised without bypass: `--no-launch` returned 2 at the
    non-terminal locator guard, produced no stdout, and left the locator hash unchanged. The current
    strict run was not overwritten, replaced, finalized, cancelled, or edited.
  - A fresh real MCP stdio read probe again listed 64 tools, found
    `get_project_build_context`, and called it successfully with `isError=false` and `ok=true`.
    This confirms the platform server/auth path remains healthy independently of Claude 2.1.74.
  - A second REST create/cancel was intentionally not repeated: Round 3 already created and
    cancelled its unique real Build Session, no API/request code changed in this repair, and the
    current-runtime acceptance condition now explicitly requires zero HTTP calls. Fake supported
    path tests still cover authenticated POST/idempotency and exact cleanup semantics.
  - `ontology-platform.service` was active; backend health returned `ok` and frontend `/` returned
    HTTP 200. No backend/frontend code changed, so no restart was required.
- Credential and artifact gate: the final scanner loaded the one actual ignored
  `ONTOLOGY_MCP_API_KEY` value without printing it and found zero plaintext hits in changed tracked
  files, the unstaged delivery diff, or the empty staged diff. This round created no Claude print
  session/transcript, Harness run, launch intent, Build Session, or GUI process, so no probe artifact
  required deletion. No file was staged or committed by the independent tester.
- Required repair before Round 5: parse each inventory line into an exact server identifier and
  explicit connection state. Accept the modeler only when the identifier set is exactly
  `{ontology-platform}` and that server is connected; accept the simulated user only on the
  explicit no-server result. Add negative tests for a prefixed/suffixed name, an unrelated server
  whose command contains the expected text, and failed/authentication-required status. Freeze a new
  digest and rerun this suite without rewriting Rounds 3–4.
