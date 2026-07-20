# Claude Code dual-session modeling Harness

This runbook launches two independent top-level Claude Code sessions: one simulated user and one
ontology modeling lead. They share a repo-local run and exchange visible messages through an
append-only mailbox. The modeler may start fresh extraction, analysis, and review subagents inside
its own session. The mailbox and Hook record are evaluation evidence; platform Build Checkpoints,
Execution Events, validation, batches, lineage, and read models remain authoritative.

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
