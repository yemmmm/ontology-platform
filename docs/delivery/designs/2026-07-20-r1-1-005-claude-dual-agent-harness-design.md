# R1.1-005 Claude Code Dual-Agent Modeling Harness Design

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-005
- Contract frozen: 2026-07-20
- Status: implemented; plan review Round 2 PASS; independent test Round 2 PASS
- Delivery record:
  `docs/delivery/records/2026-07-20-r1-1-005-claude-dual-agent-harness-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-20-r1-1-005-claude-dual-agent-harness-test-plan.md`

## Goal and non-goals

Provide a repo-local experiment Harness in which two independently launched Claude Code top-level
sessions simulate the user and ontology modeler. The modeler can invoke fresh extraction, analysis,
and review subagents. Hooks correlate their visible interaction and bounded stage summaries without
competing with platform workflow facts.

This does not add a platform Agent Runtime, REST/MCP/schema/UI changes, a general orchestration
engine, or production authorization. It does not treat a local subagent as a second main session,
store hidden reasoning/full transcripts, or turn simulated approval into human approval.

## Runtime topology

```text
operator terminal A                         operator terminal B
Claude top-level session                    Claude top-level session
participant=simulated_user  <--mailbox CLI--> participant=modeling_agent
                                                     |
                                      +--------------+-------------+
                                      |              |             |
                                 source_extractor semantic_analyst ontology_reviewer
                                      fresh local subagent contexts
```

Both terminals activate the same `run_id`, `build_session_id`, and `project_id`, but present a
different one-time nonce and `participant_role`. The Hook acknowledgment binds the actual runtime
`session_id`; the CLI cannot self-assert it. A run is ready for dual interaction only when both
required roles are bound. Legacy Codex activation defaults to `main_agent` and remains supported.

Arbitrary top-level sessions are not members of the same native Agent Team and therefore cannot use
Claude's `SendMessage` to address one another. Dual mode uses a Harness-owned append-only mailbox:
`message send`, `message poll`, and `message ack`. Every mutating command supplies a random unique
`operation_id`; send and ack require a single-use receipt keyed by `(run_id, operation_id)` and
written by `PreToolUse` after it resolves the invoking runtime session to its bound participant.
The receipt also binds the complete command fingerprint, session, role and epoch so identical
commands from concurrent sessions cannot collide. Poll is role-scoped and read-only; it returns
only bounded visible messages and stable IDs, never nonces or raw event state. In v1 it is a
repo-local observability interface and does not isolate messages from a malicious local process;
poll cannot acknowledge delivery, write a checkpoint, or otherwise advance state. The mailbox is
transport for the experiment, not a platform workflow fact.

Agent Teams is experimental and its noninteractive behavior is not used as identity evidence.
Claude Code 2.1.215 proved nested local-agent execution, while neither tested `-p` path created an
independent teammate. The runbook therefore uses two explicit top-level sessions and fails visibly
if only one is active.

## Run and participant state

Harness metadata advances to version 2 and adds a `mode` plus `participants` map. Each participant
stores role, runtime, session ID, activation/last-seen/stopped timestamps, and a per-participant
pending checkpoint. The legacy `session_id` field remains readable for version-1 runs; migration is
in-memory/atomic on the next locked write.

The session registry maps one runtime session to one `(run_id, participant_role, participant_epoch)`.
Valid roles are
`main_agent` for legacy mode and exactly `simulated_user` or `modeling_agent` for dual mode. The
following fail closed: role reuse by another live session, one session binding multiple roles,
project/Build Session mismatch, mode mixing, unknown roles, stale or wrong nonce, and a third top
level participant. Repeated activation of the same session/role is idempotent.

Crash recovery never infers liveness from `Stop`. An explicit operator `replace-participant`
command issues a new activation nonce and atomically increments that role's epoch, removes the old
session registry entry, and invalidates outstanding operation receipts. The replacement session
then completes the normal Hook-bound activation. All Hook events and receipts carry the epoch; a
late event from the old session is ignored. `SessionEnd` records an observation but does not grant
replacement authority.

Every event includes `participant_role`, `runtime`, and runtime `session_id`. The existing run lock,
atomic metadata writes, append-only sequence, fingerprint deduplication, secret scanner, size
bounds, redaction replacement, summary cursor, and terminal publication rules remain shared.

## Hook mapping

The project-level `.claude/settings.json` invokes the same runtime-neutral Python recorder with
`${CLAUDE_PROJECT_DIR}` for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStart`,
`SubagentStop`, `TaskCreated`, `TaskCompleted`, `TeammateIdle`, `Stop`, `StopFailure`,
`PostToolUseFailure`, and `SessionEnd`. Existing `.codex/hooks.json` remains unchanged except where
common coverage requires it.

- User prompts are visible bounded input events; the simulated-user definition requires structured
  message prefixes for answer, clarification, approval, rejection, and scope change.
- `PreToolUse` for the exact Harness mailbox/checkpoint Bash command writes a short-lived receipt
  containing command fingerprint, session ID, role and participant epoch. The command consumes that
  receipt under the run lock. Arbitrary Bash, a claimed role flag, or another session's receipt does
  not authorize mutation.
- Mailbox send records sender role, receiver role, message kind and bounded visible content.
  Approval/rejection from `simulated_user` is forced to `source=agent_reported` and
  `simulated=true`; no mailbox or Hook event invokes a platform approval API.
- Agent dispatch recognizes Claude `Agent` and compatibility alias `Task`, and reads Claude's
  `subagent_type` as well as legacy role keys. Start/stop records agent
  ID/type and bounded final message only. Full `agent_transcript_path` is deliberately ignored.
- Task and teammate-idle hooks record only bounded task identifiers, subjects, status and ownership;
  failed tool calls are recorded as failures and never as delivered messages.
- Successful modeling MCP `PostToolUse` events may update phase checkpoints only for
  `modeling_agent` or legacy `main_agent`. The simulated user can observe/message but cannot
  advance an authoritative modeling phase.
- The local `checkpoint` command uses the same operation receipt and is rejected unless the bound
  role is `modeling_agent` (or legacy `main_agent`); pending state is stored per participant.
- Stop is a participant-local turn boundary, not participant termination. Run finalization occurs
  only through existing terminal platform tools
  or explicit CLI finalization, so one participant stopping cannot truncate the other participant's
  history.

## Agent definitions and handoff

Checked-in `.claude/agents/` definitions establish narrow behavioral roles:

- `simulated-user`: consumes a scenario brief, behaves consistently as the user, asks for
  explanations, answers questions, and labels every decision as simulated.
- `ontology-modeling-agent`: owns workflow coordination and platform writes, sends user-visible
  questions to the simulated user, and delegates source extraction, semantic analysis, and review.
- `source-extractor`: extracts evidenced business facts and coverage only; no ontology design.
- `semantic-analyst`: proposes terminology, competency-question implications, and model candidates;
  no apply or user impersonation.
- `ontology-reviewer`: independently returns PASS/REVISE/BLOCKED with structured findings; no edits
  or apply.

The modeler passes explicit versioned artifacts or bounded locators, not conversational memory.
Large Modeling Draft output continues to use the R1.1-003 reliable handoff rather than messages.

## Summary and retrospective

For Claude dual runs the summarizer serializes the checked-in schema as the argument to
`--json-schema`, launches a fresh `claude -p --bare --tools '' --no-session-persistence
--output-format json` process in an empty temporary directory, and supplies bounded events on stdin.
The restricted environment retains only the documented runtime/authentication variables needed by
the installed provider but never persists their values. The runner parses the Claude JSON envelope,
requires a `structured_output` object (not the envelope itself), then validates it against the same
strict local schema and secret limits. Missing structured output, extra stdout, authentication
failure, timeout, invalid JSON, or schema mismatch leaves the cursor unchanged and marks
finalization pending. Legacy Codex runs retain the existing Luna path and are selected from run
metadata, not ambient executable availability.

Stage input is bounded append-only events, not transcripts. Summaries must preserve participant
roles, visible decisions/questions, subagent outcomes, platform IDs, unresolved issues, and next
step, while distinguishing `agent_reported`, `platform_observed`, and simulated decisions. Only
fully summarized completed/cancelled runs publish a redacted retrospective.

## Compatibility, rollout, and recovery

Version-1 Codex runs and commands continue working. New CLI options add runtime and participant role;
`status` exposes readiness without leaking nonces. The dual-terminal runbook includes version check,
activation, mailbox send/poll/ack, role prompts, status, checkpoint/redaction/finalization,
participant replacement, recovery, and unique-run cleanup. No automatic single-session fallback is
allowed when dual mode was requested. The workflow/config hash includes Claude settings, all Agent
definitions and the runbook so retrospective comparisons identify the exact experiment version.

Because only repo-local `.claude`, `.codex`, tests, and docs change, backend/frontend service restart
is not required. Rollback is removal of Claude config/agents plus use of legacy activation; existing
platform records and version-1 Harness data remain readable.

## 2026-07-21 fast-local optimization extension

### Functional contract and profile boundary

The existing behavior is named `strict-eval`: operators explicitly activate two top-level Claude
sessions, Hook-issued identity/operation receipts remain mandatory, and real dual interaction plus
structured retrospective publication are release evidence. The new `fast-local` profile is an
iteration aid for optimizing the modeling agent and is never accepted as a substitute for that
hard gate.

One launcher performs the non-modeling setup: validate a checked-in scenario, read a gitignored
local credential/config file, check backend health, create a fresh Project Build Session, generate a
Harness run ID and two Claude session UUIDs, pre-bind those sessions as the two existing participant
roles, write the ignored active-run locator, and launch both top-level sessions with an initial
prompt. `--no-launch` performs every deterministic preparation step and emits bounded commands for
test/headless use. It never collapses the roles into one session.

Before creating platform state, the launcher checks an existing active-run locator. It refuses to
replace a locator whose referenced Harness run is still non-terminal unless the operator supplies
an explicit replacement option; replacement changes only the locator and never deletes or finalizes
the earlier run. This prevents a convenience file from silently hiding a recoverable experiment.

The launcher may read the existing local evaluation API key because this profile is explicitly
machine-local. It must not echo the key, put it in a Claude command/prompt, write it to Harness
events, or copy it into tracked configuration. A delivery gate compares the actual ignored local
values against the staged diff and new commit content. Building a general credential store is a
non-goal.

### Scenario and Build Session lifecycle

A versioned JSON scenario contains only reusable business input: scenario/version, goal, fixed
corpus snapshot/path, constraints, simulated-user facts/decision policy, and acceptance questions.
Machine-specific Project identity and the API key remain in the ignored local runtime file. The
launcher creates a new idempotent Build Session with a unique client ID and intake checkpoint on
every run unless an explicit existing active Build Session is supplied for recovery. A failed
launch after Build Session creation reports the stable session/run IDs for recovery; it does not
silently cancel work that may already have been observed by a started Agent.

Before the create request, the launcher durably writes an ignored launch-intent manifest keyed by
run ID. It contains no credential, but freezes Project ID, client session ID, exact create payload
hash, scenario hash, and both Claude session UUIDs. Retrying the same run reuses the intent and
identical POST payload, accepting the API's idempotent 200 response after an earlier 201. A changed
payload for the same intent fails locally. An explicitly supplied recovery Build Session is read
first and must be active and owned by the configured Project before Harness preparation; terminal,
missing, or foreign-Project sessions are rejected.

### Fast participant preparation

`modeling_harness.py prepare-fast` accepts the generated run ID, Project/Build Session IDs, scenario
locator, launch-intent hash, and two caller-generated UUID session IDs. All registry mutations,
including strict activation and participant replacement, share a root-level registry lock before
acquiring a run lock. While holding it, prepare-fast preflights the run plus both globally registered
session UUIDs before making any participant active.

Preparation first writes version-2 metadata with `evaluation_profile=fast_local`,
`summary_policy=explicit`, a unique `preparation_id`, `preparation_complete=false`, and non-ready
status. State and both registry entries carry the same preparation ID. Bounded preparation and two
activation events are written while the run is still incomplete and therefore invisible to Hooks.
Only after metadata, state, both registries, and all required events succeed does the final metadata
write act as the commit marker by setting both epoch-1 participants active,
`preparation_complete=true`, and status active. Hooks reject an incomplete preparation even if a
registry or event file exists.
On an ordinary write failure the command removes only registry entries carrying its preparation ID
and leaves bounded failed metadata. On retry after a process crash, the root lock detects and repairs
incomplete matching preparation files before proceeding. A completed preparation is idempotent only
for the same full identity and intent hash; conflicts fail without replacement.

Existing strict activation continues to create `evaluation_profile=strict_eval` implicitly and
still requires nonce plus PreToolUse acknowledgment.

Pre-binding is intentionally weaker identity evidence and is allowed only for `fast_local`; status
must expose the profile so it cannot be mistaken for strict evidence. Once launched, ordinary Hook
events and mailbox/checkpoint mutations still resolve the actual CLI `--session-id` through the
same registry and retain role/epoch receipts. A conflicting existing run/session binding fails
without partial replacement.

### Runtime launch and MCP isolation

The launcher starts two GNOME Terminal processes when available:

- simulated user: `--agent simulated-user`, predetermined `--session-id`, initial scenario prompt,
  bypassed interactive permission prompts, `--strict-mcp-config`, and a checked-in empty MCP config;
- modeler: `--agent ontology-modeling-agent`, predetermined `--session-id`, initial modeling prompt,
bypassed interactive permission prompts, `--strict-mcp-config`, and only
  `.claude/ontology-mcp.json`.

Arguments are passed as a subprocess argv, never shell-joined with credentials or inline command
substitution. The initial prompts include stable run/Build Session/scenario locators but no key.
The launcher uses the single-token `--mcp-config=<path>` form because the installed Claude CLI
treats the space form as variadic and can consume following command arguments.
The canonical argv puts all named options before one final bounded positional prompt; tests assert
the exact token order and a real CLI probe proves the prompt was received unchanged.
Agent definitions treat `fast_local` as already activated, confirm status once, then begin their
role; the strict runbook retains manual activation commands.

### Summary, errors, compatibility, and rollback

Incremental summary calls are disabled when `summary_policy=explicit`. A successful terminal
platform tool marks a fast run completed/cancelled and local-only without invoking a Claude
summarizer; explicit `finalize --publish` or existing `repair` performs the normal bounded summary
and retrospective path. Strict and legacy profiles retain their current automatic behavior.

Configuration, health, credential, HTTP, scenario, Harness preparation, terminal, and Claude
executable errors are bounded and actionable. `--no-launch` is not an error and is the deterministic
test seam. No backend/frontend code or service configuration changes. Rollback removes the launcher,
scenario/empty MCP config and fast preparation branch; strict/legacy metadata and runs remain
readable.
