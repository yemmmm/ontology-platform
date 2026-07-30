# R2.3-001 Team Runner and Codex Adapter Design

## Status and sources

- Status: reviewed; plan review Round 3 PASS
- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-001
- Delivery record:
  `docs/delivery/records/2026-07-30-r2-3-001-ontology-modeling-team-standard-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-31-r2-3-001-team-runner-codex-adapter-test-plan.md`
- Implementation baseline: `5c0e61c45b1183b54a24de986ca38ff0e29a5e21`
- Reused evidence: R2.2-001 L0, L1, and L3 designs, launchers, tests, and retained acceptance
- Runtime under test: local Codex CLI/app-server `0.146.0`

## Goal

Deliver one deterministic, repository-local Team Runner that starts a fixed Modeling Team Profile
through a Runtime Adapter, keeps role semantics and professional Skills outside Runtime-specific
code, supports direct free-form Agent communication and continuing Coordinator conversation, and
owns exact empty-scope and credential cleanup.

R2.3-001 proves capability and lifecycle only. It submits no Modeling Batch, applies no ontology,
and makes no modeling-quality claim.

## Current minimal scope

The implementation adds one standalone Python package at `modeling_team/` and run data under the
already gitignored `workspaces/modeling-runs/` tree. It does not add backend routes, tables,
services, migrations, frontend code, or a background scheduler.

The package contains:

```text
modeling_team/
├── __init__.py
├── __main__.py
├── contracts.py
├── runner.py
├── platform_scope.py
├── transport_mcp.py
├── runtimes/
│   ├── __init__.py
│   ├── base.py
│   └── codex.py
├── agent-packages/
│   ├── coordinator/
│   ├── modeling/
│   ├── protocol/
│   └── source-specialist/
├── profiles/
│   ├── base-three-agent.yaml
│   └── source-specialist-smoke.yaml
├── tasks/
│   ├── base-capability-smoke.yaml
│   └── specialist-interoperability-smoke.yaml
└── tests/
```

Each Agent Package directory contains a small `package.yaml` and an `instructions.md`. Packages
reference existing repository Skills and references by repository-relative path; they do not copy
Skill text into Profiles.

The implementation also revises `skills/ontology-modeling/SKILL.md` at its existing path. The Skill
keeps one semantic method and the existing standalone single-Agent fallback, but makes execution
ownership conditional on the selected Profile: when a distinct Protocol role exists, Modeling owns
business interpretation and every semantic payload while Protocol alone performs platform calls;
when one Agent legitimately owns both roles, it may execute the existing end-to-end flow. The Skill
does not gain Runner, roster, dispatch, or Runtime mechanics.

The two committed Profiles are:

- `base-three-agent`: Coordinator, Modeling Agent, and Protocol Agent;
- `source-specialist-smoke`: the same roles plus one real Source Specialist Package.

The second Profile is used only to prove that a real Agent, Skill, communication permission, and
terminal result can be added without changing Runner or Adapter code.

## Future productization

R2.3-001 deliberately does not add:

- a daemon, service manager, multi-run scheduler, remote worker, or message database;
- a Pi Adapter, mixed-Runtime team, dynamic roster, or Runtime marketplace;
- long-term transcript/event audit, immutable history, recovery coordinator, or management UI;
- semantic candidate revisions, approval hashes, progress watchdogs, or a quality Judge;
- platform-side Agent identity, Team Run, Package, Profile, or communication concepts.

Pi implements the same stable Adapter contract in R2.3-004. New modeling approaches add or revise
Packages, Skills, and Profiles and are evaluated separately.

## Highest-risk probes and consequences

### Codex continuing conversation

The local `codex app-server generate-json-schema` output for version `0.146.0` exposes:

- `thread/start` and `thread/resume`;
- `turn/start`;
- `turn/steer` with `threadId`, `expectedTurnId`, and exact user input;
- `turn/interrupt`;
- turn, item, Agent-message, collaboration-tool, and settled-state notifications.

Consequence: the Codex Adapter uses app-server JSON-RPC, not the scenario launchers' blocking
`codex exec`. While a normal Coordinator turn is active, an outer caller can steer the exact user
text into that turn. When it is idle, the Adapter starts the next turn on the same Thread.

### Direct Agent communication and isolation

Separate Codex Threads do not provide a stable external native address space that a peer Thread can
call directly. Codex collaboration child names and rollout fields are Runtime-private and cannot
become the team contract.

Consequence: every Agent receives a narrow run-local Team Transport MCP. Its
`send_team_message(recipient_id, text)` tool accepts free-form text and appends a mechanically
attributed delivery request to a Runner-owned broker. Each Agent namespace sees only its own broker
socket endpoint, so it cannot write a sibling outbox or impersonate a sibling endpoint. The Codex
Adapter forwards the exact text to the recipient Thread via `turn/steer` or `turn/start`. The
Runner never interprets, approves, summarizes, or routes by semantics. Communication permissions
come only from the frozen Profile.

Codex `read-only` sandboxing does not hide same-UID host paths. It is defense in depth, not the role
isolation boundary. Each Agent app-server runs inside its own outer bubblewrap mount/PID namespace
with a file allowlist. No Agent namespace mounts the host repository, another Agent home/input/work
directory, the host run root, or another transport endpoint.

### Skill discovery and injection

Repository Skills currently live under top-level `skills/`, outside Codex's default discovered
roots. A structured `type: skill` input is not proof that Codex found or injected the Skill.

Consequence: the Adapter stages only each Package's declared Skill directories into that Agent's
private `/skills/` root, registers it with `skills/extraRoots/set`, and calls
`skills/list(forceReload=true)` before the first turn. Startup fails unless every required Skill is
enabled at the exact staged canonical path with no discovery error. The first turn uses only paths
returned by that call. Acceptance retains direct model-visible prompt/rollout evidence that the
Skill instructions were injected, rather than checking only the outgoing request.

### Platform lifecycle

The existing application already provides formal Project, Ontology, workspace-context, API-key
creation/revocation, and Project deletion interfaces. R2.2 L1/L3 proved the narrow local bootstrap
needed to create and self-revoke one ephemeral org-admin principal.

Consequence: `platform_scope.py` reuses those existing contracts. It may use the existing security
helper only to bootstrap and self-revoke the ephemeral admin key. All Project, Ontology, and
Project-scoped Agent-key lifecycle operations use the resident HTTP API. No backend change is
planned.

## Stable configuration contracts

### Modeling Team Profile

A Profile is YAML with only these stable fields:

```yaml
schema_version: 1
profile_id: base-three-agent
runtime: codex
agents:
  - agent_id: coordinator
    package: coordinator
  - agent_id: modeling
    package: modeling
  - agent_id: protocol
    package: protocol
communication:
  - from: coordinator
    to: [modeling, protocol]
  - from: modeling
    to: [coordinator, protocol]
  - from: protocol
    to: [coordinator, modeling]
parameters: {}
```

Validation requires:

- schema version `1`, a safe stable ID, and supported homogeneous Runtime;
- unique Agent IDs and referenced Package IDs;
- exactly one `coordinator` role and one `protocol` role;
- no undeclared communication endpoint;
- no duplicate edge or self-edge unless a future schema explicitly introduces one;
- no credential, absolute path, Runtime identity, Project ID, or Ontology ID in the Profile;
- a frozen roster after validation.

### Agent Package

An Agent Package `package.yaml` contains:

```yaml
schema_version: 1
package_id: modeling
role: modeling
description: Business-semantic modeling owner
instructions: instructions.md
required_skills:
  - skills/ontology-modeling/SKILL.md
references: []
permissions:
  team_transport: true
  platform: none
runtime:
  codex:
    sandbox: read-only
task_input:
  required: [task, allowed_sources, roster]
```

The shared fields are Runtime-neutral. `runtime.codex` is a thin loader section and may contain only
Codex sandbox/config choices that do not redefine the role.

Validation rejects missing files, paths that escape the repository, deprecated Skills, secrets,
unknown permission values, non-Protocol platform-write permission, Coordinator platform
permission, and a Protocol Package without the single allowed platform-write declaration.

The role `instructions.md` says who the Agent is, what it owns, and what it must not do. Skills
remain authoritative for how professional work is performed. The per-run Task supplies only this
run's objective, allowed sources, scope, and roster.

Package validation also checks the effective role instructions and declared Skill contract for an
obvious write-boundary contradiction. The committed Modeling Package plus revised
`ontology-modeling` Skill must explicitly defer platform calls to Protocol in this Profile.

### Task

The Task YAML identifies a stable task ID, plain-language capability objective, allowed
repository-relative sources, and expected non-semantic terminal evidence. It cannot change the
Profile, permissions, Runtime, or platform scope.

The R2.3-001 tasks explicitly prohibit Modeling Items and Modeling Batch calls. They ask Agents to
exercise assignment, Skill loading, direct message delivery, user conversation, platform-health
read, and terminal reporting without creating ontology content.

## Team Runner lifecycle

One foreground Team Runner process owns one run and communicates with its outer caller over
newline-delimited JSON on stdin/stdout. It does not daemonize. The outer caller can keep the process
handle, send exact user text, read Coordinator text, request status, or request stop.

Mechanical states are:

```text
PREPARING
  -> STARTING
  -> RUNNING
  -> PAUSED | SETTLING
  -> TERMINAL
  -> CLEANING
  -> CLEANED
```

Any mechanical failure can enter `FAILED`, followed by the same ownership-checked `CLEANING`.
These are Runtime/resource states, not semantic workflow stages.

Startup:

1. reject an existing run ID or unsafe path;
2. validate Profile, every Package, Task, Skill/reference path, permission, and scope request;
3. create a mode `0700` run directory and atomic non-secret `state.json`;
4. prepare `create` or `existing` empty scope and the Protocol-only temporary key;
5. start every frozen Agent through the selected Adapter;
6. collect stable team Agent IDs plus Runtime-private identities;
7. send the same task and complete frozen roster to every Agent;
8. start the Coordinator assignment turn and enter `RUNNING`.

The Runner event loop:

- accepts outer user text and mechanically delivers it only to Coordinator;
- returns Coordinator commentary/final text exactly to the outer caller;
- drains Team Transport delivery requests and forwards exact peer text;
- records question/answer envelopes and completed/blocked terminal envelopes;
- records mechanical Thread/turn state without interpreting content;
- considers a team settled only when every Agent has a declared terminal result and the Adapter
  reports no Agent turn still running.

An ordinary user message is not sent to any other Agent. Coordinator decides whether to respond,
ask for clarification, or explicitly call `send_team_message` with the user's verbatim text.

## Runtime Adapter contract

`runtimes/base.py` defines one interface with Runtime-neutral values:

- `start_roster(run, agents) -> list[AgentRuntimeIdentity]`;
- `start_task(agent_id, task_text, skill_paths, roster)`;
- `send_message(agent_id, exact_text)`;
- `receive_messages() -> list[RuntimeMessage]`;
- `get_agent_states() -> list[AgentState]`;
- `wait_settled(agent_ids, timeout)`;
- `pause()`, `resume()`, and `stop()`;
- `cleanup_identifiers()`.

Stable states are `starting`, `idle`, `running`, `completed`, `blocked`, `failed`, and `stopped`.
Codex Thread IDs, turn IDs, rollout paths, app-server process IDs, and notification names remain
inside the Codex implementation and its private runtime-state section.

R2.3-001 implements only `CodexRuntimeAdapter`. Unit fixtures may emulate app-server protocol
responses to test parsing and failure handling, but there is no second fake Adapter and no fake
Agent interoperability acceptance.

## Codex Team Adapter

### Outer isolation and role loading

The Adapter starts one Codex app-server process and one persistent Thread per Agent. Each process
runs in a separate outer bubblewrap mount and PID namespace. Its allowlist mounts only:

- the Codex binary and required system/runtime libraries;
- that Agent's private read-only staged Package, task, references, and Skill root;
- that Agent's own writable work directory and private `CODEX_HOME`;
- that Agent's own Runner-broker Unix socket endpoint;
- for Protocol only, the sanitized backend/MCP runtime required by its allowlisted platform tools.

The namespace creates its own `/proc` after PID unshare. It does not mount `/`, the repository root,
the host run root, sibling Agent directories/endpoints, host Codex home, backend `.env`, or
unlisted platform/runtime files. The inner Codex sandbox remains enabled as defense in depth.

This outer boundary makes role visibility mechanical:

- Coordinator gets no ontology-platform MCP;
- Modeling and the R2.3 specialist get no ontology-platform MCP;
- Protocol alone gets the run's Project-scoped `model` key and an allowlisted ontology-platform
  MCP configuration;
- no Package or task file contains a key;
- strict config validation runs before the first Agent turn.

Protocol's generated config and key exist only in its host-owned private home and Protocol
namespace. Same-UID sibling processes cannot see that host path because it is absent from their
mount namespaces. Non-Protocol adversarial probes must also fail to read sibling material through
`/proc`, guessed host paths, or transport endpoints and must fail to call a write endpoint without
a credential.

Before the first Agent turn, the Adapter:

1. stages and hashes only the Package's declared Skills and their referenced files;
2. calls `skills/extraRoots/set` with the private `/skills` root;
3. calls `skills/list` with the Agent cwd and `forceReload=true`;
4. requires the exact expected Skill names and canonical paths, `enabled=true`, and no errors;
5. fails startup when a Skill is missing, disabled, duplicated, or path-mismatched.

The app-server `thread/start` request supplies the Package role instructions. The first
`turn/start` supplies the Task, frozen roster, allowed sources, and only Skill input items returned
by the discovery preflight. The Adapter retains the first turn's model-visible prompt/rollout input
and verifies the declared Skill instruction text/hash is present. Codex-specific loading remains
in `runtimes/codex.py`.

### Messages and settlement

Each app-server connection is read continuously. Agent text is emitted as Runtime messages without
rewriting. The Runner-owned broker accepts connections through one distinct socket endpoint per
Agent and attributes the sender from that endpoint. Team Transport records only:

- sender Agent ID;
- allowed recipient Agent ID;
- exact free-form text;
- a monotonic delivery sequence and timestamp.

The MCP also exposes `report_task_result(status, summary)` with status `completed` or `blocked`.
Protocol uses the same tool to include its platform terminal summary. This structured terminal
envelope is not a semantic approval.

The Adapter forwards a peer or user message with `turn/steer` when the target has the expected
active turn; otherwise it starts a new turn on the same Thread. A stale turn precondition is
re-read and retried once only with the same exact message. It never silently drops or duplicates a
delivery.

The Runner waits for every Agent result plus Adapter settled state. Coordinator receives those
facts and produces the user-facing team summary; the Runner does not produce that summary.

## Platform scope and credential ownership

Input is one of:

```yaml
scope:
  mode: create
```

or:

```yaml
scope:
  mode: existing
  project_id: "<id>"
  ontology_id: "<id>"
```

For `create`, the Runner:

- creates an ephemeral org-admin key;
- creates one uniquely named empty Project and Ontology through HTTP;
- verifies workspace context is empty/current;
- creates one Project-scoped `model` key for Protocol;
- records exact resource/key IDs as run-owned;
- on cleanup revokes the Protocol key, deletes only the exact owned empty Project, verifies absence,
  then self-revokes the admin key.

Deletion is refused if the Project/Ontology identity no longer matches the ownership record or the
workspace indicates a Modeling Batch/write occurred.

For `existing`, the Runner:

- creates an ephemeral org-admin key;
- reads the named Project, Ontology, and workspace context;
- requires the Ontology to belong to the named Project and to be empty for R2.3-001 acceptance;
- creates one temporary Project-scoped Protocol key;
- records both scope IDs as external, never run-owned;
- on cleanup revokes only its key and admin key and re-reads the scope;
- never deletes, patches, acquires a Lease for, or opens a Build Session in the existing scope.

The independent test owns and later deletes its empty existing-mode fixture. The Runner cannot do
that cleanup.

## Local state and evidence

The host-only `workspaces/modeling-runs/<run-id>/` contains:

```text
state.json
profile.snapshot.yaml
task.snapshot.yaml
packages/
runtime/
transport/broker/
evidence/
secrets/
```

Snapshots and `state.json` are non-secret. The host Runner never mounts this root wholesale into an
Agent namespace. Runtime-private Agent homes and the Protocol key live under mode `0700`
`secrets/` and are destroyed after terminal cleanup. Evidence keeps:

- input hashes and validated roster;
- stable Agent IDs and redacted Runtime identities;
- question/answer, delivery, terminal, and settled envelopes;
- platform scope/key ownership receipts;
- cleanup and resident-health results.

It does not copy hidden reasoning or claim a complete long-term transcript. Atomic file replacement
and advisory file locking protect current-run state and transport append operations.

## Failure behavior

- Invalid Profile, Package, Task, Skill, permission, or Runtime config fails before any Agent starts.
- Scope preparation failure revokes any exact key and removes only an exactly owned empty scope.
- Partial Agent startup stops already started processes and cleans the prepared scope.
- An Agent `blocked` result is delivered to Coordinator and remains a legitimate terminal result.
- app-server exit, malformed protocol response, lost Thread, or unsteerable normal turn is a
  `runtime/infrastructure` failure.
- A missing/disabled/path-mismatched Skill or any Skill discovery error fails before the first
  Agent turn.
- Unauthorized recipient or platform permission is a `collaboration/routing` failure.
- Any Modeling Batch event during R2.3-001 is a `platform-contract` failure and blocks deletion
  until ownership and emptiness are re-established manually.
- No automatic progress watchdog or semantic timeout is added. Mechanical startup, JSON-RPC, and
  explicit settlement waits use bounded operational timeouts.
- Ambiguous cleanup ownership stops deletion, preserves evidence, and reports the exact blocker.

## Acceptance mapping

1. Profile/Package validation and real base run prove fixed roster and role/Skill/task loading.
2. Per-Agent namespace mount/PID inspection plus real adversarial read/write probes prove
   permission isolation; process/home/config inspection alone is insufficient.
3. Team Transport delivery receipts plus recipient Agent response prove direct communication.
4. A Coordinator turn held active while another Agent works, followed by exact `turn/steer`, proves
   continuing user conversation.
5. Ordinary and explicitly forwarded user-message cases prove routing behavior.
6. Protocol MCP config, tool event inspection, and absence elsewhere prove Protocol-only platform
   access; platform receipts prove zero Modeling Batch writes.
7. terminal envelopes, Adapter states, and Coordinator summary prove terminal ownership/settlement.
8. `create` run receipts prove empty creation/read/deletion and key cleanup.
9. `existing` run receipts prove empty read/no takeover/no deletion.
10. the specialist Profile real run and unchanged Runner hash prove Package/Profile-only extension.
11. process inventory proves one foreground Runner and no scheduler/daemon.
12. process/namespace/key/scope/secret cleanup plus backend/frontend health prove operational
    closure.

## Rollout and operational impact

The implementation is a local tool and committed configuration. No backend or frontend runtime code
change is planned, so the systemd service does not require restart solely for installation.
Real acceptance still checks resident backend `8001` and frontend `5173` health before and after
runs. If implementation unexpectedly changes backend/frontend code, the repository's full
test/restart rules become mandatory.
