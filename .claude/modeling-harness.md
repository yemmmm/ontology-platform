# Claude Code dual-session modeling Harness

This runbook launches two independent top-level Claude Code sessions: one simulated user and one
ontology modeling lead. They share a repo-local run and exchange visible messages through an
append-only mailbox. The modeler may start fresh extraction, analysis, and review subagents inside
its own session. The mailbox and Hook record are evaluation evidence; platform Build Checkpoints,
Execution Events, validation, batches, lineage, and read models remain authoritative.

## Fast local iteration

Use `fast-local` for frequent modeling-Agent experiments where setup speed matters more than formal
release evidence. It still launches two independent top-level Claude sessions, but deterministically
creates the Build Session, pre-binds both session UUIDs, isolates MCP configuration and injects the
first prompt. It is not a substitute for the `strict-eval` procedure below.

Copy the credential-free template into the ignored Harness workspace and set the existing local
Project ID. The default reads `ONTOLOGY_MCP_API_KEY` from `backend/.env`; do not put a key in the
tracked template or scenario.

```bash
mkdir -p workspaces/ontology-harness
cp .claude/fast-local.example.json workspaces/ontology-harness/fast-local.json
${EDITOR:-vi} workspaces/ontology-harness/fast-local.json
python3 .codex/fast_local_launcher.py
```

For headless preparation and deterministic command inspection, use:

```bash
python3 .codex/fast_local_launcher.py --no-launch
```

The checked-in default scenario is `.claude/scenarios/dify-foundations-v1.json`. A non-terminal
`active-run.json` is never overwritten implicitly; inspect it and pass `--replace-active-locator`
only when the older recoverable experiment should no longer be the active convenience locator.
Retry a failed launch with its printed `--run-id` to reuse the durable launch intent and idempotent
Build Session create payload. To recover an already known active session, pass
`--build-session-id ID`; missing, terminal, and foreign-Project sessions are rejected.

Before creating a Build Session, the launcher runs a captured project-settings-only MCP inventory
probe. It requires exactly `ontology-platform` for the modeler and no MCP server for the simulated
user. Raw diagnostic output is never echoed because some plugin commands may contain credentials.
If the installed Claude runtime cannot prove those inventories, the launcher fails before the API
POST and asks for Claude Code 2.1.215 or newer (or the strict-eval workflow).

Fast-local completion/cancellation records a local-only terminal run without starting the Claude
summarizer. Publish only when the retrospective is useful:

```bash
python3 .codex/hooks/modeling_harness.py finalize \
  --run-id RUN_ID_LITERAL --terminal-state completed --publish
```

Everything below is the formal `strict-eval` workflow.

## 1. Verify the runtime and project Hooks

Run from the repository root:

```bash
claude --version
python3 -m json.tool .claude/settings.json >/dev/null
```

The tested/recommended CLI is `2.1.215` or newer. If the installed CLI is older, upgrade before the
hard-gate runtime probe instead of silently collapsing both roles into one session:

```bash
npm install -g @anthropic-ai/claude-code@latest
claude --version
```

Open Claude Code once in the repository and approve the checked-in project Hook configuration if
prompted. All Hook commands resolve through `${CLAUDE_PROJECT_DIR}`. Do not edit settings, Agent
definitions, the runner, schema, or this runbook after activation because their combined hash is
part of the run identity.

## 2. Prepare literal run values

Choose one unique run ID, the existing platform Build Session ID, and project ID. Generate two
different nonces in an operator shell:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Copy the resulting literal values into the commands below. Do not leave shell variables, command
substitution, or angle-bracket placeholders in a command executed by Claude: the PreToolUse Hook
must fingerprint the same literal arguments the CLI receives.

## 3. Start two top-level sessions

In terminal A, start a top-level simulated-user session:

```bash
claude --agent simulated-user
```

Ask that session to execute this command with literal values:

```bash
python3 .codex/hooks/modeling_harness.py activate \
  --run-id RUN_ID_LITERAL \
  --activation-nonce USER_NONCE_LITERAL \
  --build-session-id BUILD_SESSION_ID_LITERAL \
  --project-id PROJECT_ID_LITERAL \
  --runtime claude \
  --participant-role simulated_user
```

It should report `waiting for peer participant`. In terminal B, independently start the modeler:

```bash
claude --agent ontology-modeling-agent
```

Ask it to execute:

```bash
python3 .codex/hooks/modeling_harness.py activate \
  --run-id RUN_ID_LITERAL \
  --activation-nonce MODELER_NONCE_LITERAL \
  --build-session-id BUILD_SESSION_ID_LITERAL \
  --project-id PROJECT_ID_LITERAL \
  --runtime claude \
  --participant-role modeling_agent
```

Check readiness from either operator shell. Status deliberately omits session IDs and nonces:

```bash
python3 .codex/hooks/modeling_harness.py status --run-id RUN_ID_LITERAL
```

Continue only when `ready` is `true`. A `local_agent` task or a single session role-playing both
sides does not satisfy this topology and must not be recorded as a successful run.

## 4. Exchange visible messages

Every send or acknowledgment needs a fresh literal operation ID. Generate it first, copy it, and
then ask the relevant Claude session to run the mutation. Never use `$(uuidgen)` inline.

Modeler asks a question:

```bash
python3 .codex/hooks/modeling_harness.py message send \
  --run-id RUN_ID_LITERAL \
  --operation-id OPERATION_ID_LITERAL \
  --recipient-role simulated_user \
  --message-kind clarification \
  --content 'Which source definition should control this ambiguous term?'
```

The simulated user reads its mailbox without mutating state:

```bash
python3 .codex/hooks/modeling_harness.py message poll \
  --run-id RUN_ID_LITERAL --participant-role simulated_user
```

It sends an answer, approval, or rejection using a new operation ID. Decisions are always normalized
to `agent_reported` and `simulated=true`:

```bash
python3 .codex/hooks/modeling_harness.py message send \
  --run-id RUN_ID_LITERAL \
  --operation-id ANOTHER_OPERATION_ID_LITERAL \
  --recipient-role modeling_agent \
  --message-kind approval \
  --content 'approval: the simulated scenario accepts proposal version 3'
```

The recipient acknowledges a polled `message_id` with another fresh operation ID:

```bash
python3 .codex/hooks/modeling_harness.py message ack \
  --run-id RUN_ID_LITERAL \
  --operation-id ACK_OPERATION_ID_LITERAL \
  --message-id MESSAGE_ID_LITERAL
```

Poll is intentionally read-only and repo-local; it does not provide OS-level confidentiality and
cannot acknowledge delivery or advance a checkpoint.

## 5. Delegate and checkpoint

The modeling lead invokes `source-extractor`, `semantic-analyst`, and `ontology-reviewer` as fresh
Agent contexts with versioned artifact locators and bounded output contracts. Large drafts use the
R1.1-003 Modeling Workflow Artifact handoff, not mailbox messages.

Successful platform modeling events are preferred checkpoints. If a local checkpoint is necessary,
only the modeler session may run it and it also needs a fresh operation ID:

```bash
python3 .codex/hooks/modeling_harness.py checkpoint \
  --run-id RUN_ID_LITERAL \
  --phase review \
  --event-type review_completed \
  --summary 'Independent reviewer returned PASS for proposal version 3.' \
  --client-checkpoint-id CHECKPOINT_ID_LITERAL \
  --operation-id OPERATION_ID_LITERAL
```

## 6. Recovery, redaction, and finalization

`Stop` is only a turn boundary. If one top-level session is lost, explicitly replace that role:

```bash
python3 .codex/hooks/modeling_harness.py replace-participant \
  --run-id RUN_ID_LITERAL --participant-role simulated_user
```

The command prints a new nonce. Launch a new top-level session with the same Agent definition and
run the activation command using that nonce. Replacement increments the role epoch and invalidates
the old session and its unused receipts.

If an event is rejected by the secret scanner, review and supply a bounded substitute:

```bash
python3 .codex/hooks/modeling_harness.py redact \
  --run-id RUN_ID_LITERAL --for-sequence SEQUENCE_LITERAL \
  --replacement 'Credential-bearing content removed; user requested source clarification.'
```

Successful platform completion/cancellation finalizes automatically. An operator may explicitly
finalize or repair a pending Claude structured-output summary:

```bash
python3 .codex/hooks/modeling_harness.py finalize \
  --run-id RUN_ID_LITERAL --terminal-state completed
python3 .codex/hooks/modeling_harness.py repair RUN_ID_LITERAL
```

Only fully summarized `completed` or `cancelled` runs publish a redacted retrospective. Paused or
interrupted runs remain local. Raw data stays under `workspaces/ontology-harness/RUN_ID_LITERAL/`;
remove only the uniquely identified synthetic probe run after inspection.
