# R2.2-001 Ontology Modeling Team L3 Design

## Status and sources

- Status: implemented; real L3 run and independent Requirement Tester Round 22 passed
- Requirement: `docs/requirements/requirements-v2.2.md`, R2.2-001 L3
- Baseline: commit `640dee9`
- Prior implementation reused: L0 role/isolation proof and L1 isolated write workflow
- Business references: R2.1-001 M1 and M6 Workflow-as-Tool `C -> B -> A` slice

## Goal

Run one fresh, isolated Ontology Modeling Team against the complete bounded Dify
Workflow-as-Tool `C -> B -> A` slice and obtain directly reviewable evidence that:

1. the Modeling Coordinator, Modeling Agent, and Platform Protocol Agent retain their confirmed
   responsibilities;
2. the team discovers consequential source gaps and asks one grounded business question at a time;
3. the approved candidate is applied through immutable Modeling Batch `dry_run -> apply_atomic`;
4. managed validation conforms, reasoning is consistent, and generic governed query evidence
   recovers the published `C -> B -> A` path while excluding Current Draft from that active chain;
5. an unconfirmable business fact remains a queryable explicit unknown; and
6. credentials, resources, events, receipts, cleanup, and resident-service health remain auditable.

L3 proves one bounded end-to-end result. It does not compare the team with a single Agent or claim
general quality improvement.

## Current minimal scope

The implementation is a new repository-local evaluation scenario under
`docs/evaluation-scenarios/ontology-modeling-team-l3/`. It reuses L1 mechanics by code adaptation,
not by changing the accepted L1 scenario or creating a product Runtime.

The scenario owns:

- a frozen and hashed Agent-visible input pack;
- a tester-only answer and acceptance contract;
- a deterministic script used by the Delivery Agent for fresh OS namespaces, Codex Sessions,
  platform scope, ephemeral credentials, question/answer continuation, protocol execution,
  evidence retention, cleanup, and failure classification;
- focused offline tests for that mechanical execution contract; and
- a README with bounded live-run and evidence-review commands.

It also includes one scenario-local, Protocol-only deterministic mechanics helper. The helper owns
UUID/request-ID generation, canonical JSON and hashes, atomic file publication, public request-schema
validation, immutable Batch freeze/replay envelopes, revision/lease state, lease-renewal request
preparation, checkpoint bodies, and response parsing. The Protocol Agent supplies and remains
accountable for every semantic Modeling Item, evidence/rationale, query and decision to call or
route an error. The helper cannot invent, add, remove, reorder, or semantically repair Items.

No frontend, migration, platform schema, or domain-specific API change is planned. A generic
backend dry-run correctness defect discovered by the live run may be fixed only if it directly
protects atomic Modeling Batch application.

## Non-goals and future productization

The following are outside current completion:

- M7 Workflow orchestration and typed-variable-flow expansion;
- single-Agent control, repeated-success measurement, statistical comparison, or Runtime parity;
- new Judge, Consumer, mutation suite, fault-injection framework, or dedicated acceptance program;
- Dify-specific platform routes, read models, sorting, interpretation, or DSL parsing;
- generalized Host Workflow, Runtime Adapter, credential broker, sandbox product, backend Agent
  Runtime, remote scheduler, recovery service, or management UI;
- production-grade cross-machine isolation, immutable audit platform, or automatic crash recovery.

These may be future productization only after a demonstrated need. They are not L3 gates.

## Frozen inputs and isolation

### Agent-visible

The Delivery Agent's script stages only a new manifest and copied immutable sources:

- the pinned Dify Workflow-as-Tool, Output, Version Control, User Input, and IF/ELSE pages already
  committed in the M1 source pack or Dify foundations snapshot;
- the M6 synthetic `workflow-landscape`, `interface-notes`, `release-register`, and
  `exception-handling` business materials;
- the bounded L3 business task and consumer questions;
- the public platform Modeling Batch and semantic-operation contract.

The visible task names the synthetic C/B/A fixture, the published `quality_score:number` deletion,
the Current Draft countercase, and the required business outcomes. Those are the problem statement,
not hidden answers. It does not expose prior ontology terms, IRIs, Batch payloads, SPARQL, historical
run records, hidden gap categories, or the expected model.

### Tester-only

The tester-only contract freezes:

- invocation target: B invokes C through C's Latest published Version;
- output continuity: `quality_rating:number` is the documented successor of
  `quality_score:number`;
- missing-score behavior: the business owner cannot confirm B's behavior when scoring is absent;
- required acceptance outcomes for the published path, draft exclusion, explicit unknown, Shape,
  validation, reasoning, query completeness, and cleanup.

The M1 TTL, Shapes, queries, fixtures, M6 answer contract, historical applied resources, and prior
run evidence remain outside every team namespace. They may be read only by Delivery and independent
test roles after the run.

### OS and Session boundary

Every start uses:

- a new run directory;
- a fresh non-forked/non-resumed coordinator Session;
- fresh Modeling Agent children with `fork_turns="none"`;
- a separately launched fresh Protocol Agent;
- a new Project, Ontology, Build Session, and Project-scoped `model` key;
- the L1 split namespace: coordinator/modeler have no platform environment or MCP; protocol has
  sanitized platform runtime plus the temporary key; and
- bubblewrap mounts that expose only role-appropriate `agent-visible` and `team-work` paths.

The Delivery Session, repository, historical runtime paths, host Codex state beyond the minimum
copied authentication material, `.env`, and tester-only inputs are not mounted.

## Collaboration flow

### 1. Coordinator and Modeling Agent

The fresh coordinator spawns a fresh Modeling Agent and asks it to assess source completeness before
forming the candidate. The Modeling Agent returns business/ontology descriptions, not Modeling
Items. The coordinator may request corrections and owns the final semantic approval.

When a consequential business gap is found, the coordinator writes one `pending-question.json`
containing:

- the plain business question;
- concrete visible-source citations;
- the model or consumer conclusion affected; and
- no ontology-design request, hidden category, or proposed answer.

It then emits `L3_WAITING_FOR_ANSWER` and stops cleanly with its Session identity retained.

### 2. Conditional answer release

The Delivery Agent inspects the one question and selects only the corresponding frozen tester-side
answer. This selection is a manual mechanical match, not semantic scoring and not an automated Judge.
The Delivery Agent records the exact question, selected answer-contract entry, verbatim answer,
hashes, and coordinator Session ID through the deterministic script, then resumes that same
coordinator Session.

If the question does not match a frozen business gap, Delivery does not invent an answer. It either
returns an already explicit visible fact, records an unsupported question as a collaboration defect,
or asks the user when the fact is genuinely outside the frozen contract. Only one unanswered
question may exist at a time.

The cycle continues until the coordinator approves one candidate or returns a bounded blocker.
There is no fixed required question count. Unasked frozen answers are never released.

### 3. Protocol dispatch

The coordinator writes an approved business/ontology candidate and a minimal dispatch containing
the task identity, canonical candidate hash, and requested outcome. It does not include credentials,
platform IDs, Modeling Items, Batch IDs, queries, or hidden acceptance material.

The Delivery Agent's script mechanically canonicalizes and verifies the dispatch, then starts the
separate Platform Protocol Agent. Only that Agent receives:

- the approved candidate;
- the public protocol;
- the owned Project/Ontology scope; and
- the temporary Project-scoped `model` key through process environment.

### 4. Platform protocol execution

The Protocol Agent owns semantic conversion to Modeling Items and all team-scope platform calls. It
uses the deterministic mechanics helper for canonical envelopes and lifecycle state. It must:

1. read health, modeling context, and workspace context;
2. create a Build Session and acquire the Ontology lease;
3. create all required schema resources and at least one executable Shape;
4. use immutable validated `dry_run -> apply_atomic` transitions for schema and instances;
5. prove one separate invalid instance is rejected by a Shape and is never applied;
6. run managed semantic validation and reasoning;
7. run generic scoped semantic query or read-model operations chosen from the applied model to
   recover the required current published path, draft state, and explicit unknown;
8. save a checkpoint, complete the Build Session, and re-read its terminal state.

Mechanical JSON, IRI, item-reference, required-field, and call-order errors may be corrected by the
Protocol Agent after deterministic schema/helper feedback. The helper owns stable IDs, exact
validated-Batch replay, current revision/workspace state and lease-expiry timing. It prepares a
renewal only before expiry; the Protocol Agent issues it and records the response. It may re-read
state without semantic change. Workspace, Batch content, scope, concurrency, or semantic conflicts
must be returned to the coordinator; they must not be blindly retried or semantically altered by
the launcher.

The Delivery Agent and its mechanical helper never create Modeling Items, choose ontology
structure, write SPARQL, repair semantic content, or supply an answer model.

## Platform tools and credential boundary

The protocol namespace allowlists only the existing tools needed for:

- system health;
- Build Session and Lease lifecycle;
- Modeling Batch submit/detail and modeling/workspace context;
- fixed read models;
- semantic validation, reasoning, scoped SPARQL/context query, and graph-set state; and
- checkpoint/completion.

The existing Project-scoped `model` policy covers the mutating operations and implies read scope.
The Delivery Agent's script creates the temporary model key under an ephemeral admin identity,
verifies no-key rejection before Agent launch, revokes and verifies the model key before deleting
the owned Project, then revokes that admin key. Neither plaintext key is written to
repository/runtime evidence.

The live scenario uses the L1 pattern of a unique loopback `rdf_primary` REST environment plus a
sanitized stdio MCP pointed at the same PostgreSQL/Oxigraph and write mode. Resident `8001` remains
unchanged.

Unlike L1, both isolated REST and Protocol namespaces read-only mount the single verified
`backend/scripts/dev_owl_reasoner.py` command at `/backend/scripts/dev_owl_reasoner.py` and set
`SEMANTIC_REASONER_COMMAND` to that namespace path. No other repository script or source tree is
mounted.

Before the first team starts, Delivery creates a separate uniquely owned probe Project/Ontology
under the ephemeral host-admin identity, invokes one real managed reasoning run through the isolated
REST environment, requires a succeeded/current `consistent=true` result, deletes the probe Project,
and records cleanup. This probe contains no business data and is never exposed to the team. A
failed probe blocks Agent startup as `runtime/infrastructure`; a direct executable check or host
unit test is not a substitute.

## Evidence and direct acceptance

The scenario retains raw or normalized evidence for:

- input manifest and hashes;
- coordinator/modeler/protocol Session and child identities;
- questions, exact answers, coordinator resumes, and candidate revisions;
- protocol-only MCP events and error routing;
- Project/Ontology/Build Session/Lease ownership;
- immutable Batch Items and attempt transitions;
- workspace before/after versions;
- invalid Shape finding;
- validation and reasoning runs;
- complete, non-truncated governed query/read-model responses;
- key revocation, Project deletion, isolated-runtime exit, and resident health.

The deterministic script validates mechanical integrity and scope ownership only. The Delivery
Agent and a fresh independent Requirement Tester directly inspect the retained evidence against the
shared test plan. They do not add or run a Judge/Consumer/acceptance executable.

## Failure categories and start budget

Every terminal attempt is classified as:

- `runtime/infrastructure`: provider, Codex lifecycle, process, timeout, isolated runtime, network,
  or cleanup infrastructure failure;
- `platform-contract`: public protocol/format/state failure that does not itself prove the semantic
  model wrong;
- `collaboration/routing`: role boundary, question/answer continuation, or error-routing failure;
- `modeling-quality`: a completed applied model fails one or more semantic completion gates.

At most five fresh starts are allowed after the user's 2026-07-30 authorization added two starts
to the original three-start budget. A runtime/infrastructure or non-semantic mechanical
platform-contract failure may be repaired narrowly after evidence retention and cleanup, followed
by a wholly fresh start. A completed model that fails semantic acceptance is terminal
`modeling-quality`; no further modeling start, prompt tuning, hidden-answer release, or acceptance
relaxation is allowed.

The execution phase records `preparation_started_at` when the reviewed developer handoff begins and
`first_modeling_started_at` when the first fresh coordinator delegates the real C→B→A task to the
Modeling Agent. The first real modeling attempt must start within 20 minutes. If it has not, work
stops before further harness expansion, the record names the time consumers, and the implementation
is reduced to the smallest executable L1-derived path. A missed 20-minute gate cannot be waived by
finishing more offline infrastructure; it requires user authorization before a longer preparation
phase.

Cleanup failure is always preserved and reported; no unrelated or ambiguously owned resource is
deleted.

## Acceptance criteria

L3 passes only when one fresh attempt satisfies all of the following:

1. fresh isolated team Sessions, run directory, Project, Ontology, and Build Session are evidenced;
2. all three roles execute, only Protocol calls platform write MCP, and Delivery does not make
   semantic/protocol choices;
3. all released answers were preceded by a grounded material question and were forwarded verbatim
   one at a time to the same coordinator Session;
4. immutable Batch transitions apply the candidate and advance workspace state;
5. an executable Shape rejects one invalid candidate; final validation is conforming and reasoning
   is consistent;
6. complete governed query evidence returns the current published `C -> B -> A` invocation,
   binding, variable-use, and version context;
7. Current Draft is visible but excluded from the current published chain;
8. the unknown missing-score behavior is represented as a queryable explicit unknown;
9. naturally occurring mechanical/state/semantic errors, if any, are routed to the correct role;
   absence of a natural error is not a failure;
10. evidence is complete, credentials are revoked, the owned Project is deleted, the isolated
    runtime exits, and resident backend/frontend service health passes; and
11. focused regressions and an independent manual Requirement Tester round pass.
12. the attempt ledger proves the first real modeling start occurred within 20 minutes of the
    recorded execution-phase preparation start, or records that execution was stopped at the gate.

## Rollout and operational impact

This is a test-only local scenario. No service restart is required unless implementation unexpectedly
changes backend/frontend code, dependencies, migrations, or shared runtime configuration. Any such
need is a scope change requiring impact analysis and plan revision before coding.

## Recovery amendment — raw rollout reuse and two added starts

The earlier aggregate terminal diagnosis is invalidated by the retained raw evidence. Runs `g`,
`h`, and `i` each have a coordinator rollout under `coordinator-home/sessions`, a real
`spawn_agent` call, a child rollout linked to that coordinator, and a produced
`pending-question.json`. However, `g` omitted `agent_type=modeling_agent` and its child metadata has
`agent_role=null`; it remains a real role-boundary `collaboration/routing` negative case. Runs
`h/i` satisfy the configured-role and `fork_turns=none` contract. The outer `codex exec --json`
transcript is a CLI summary and is not authoritative for child identity.

The recovery is deliberately smaller than a new L3 implementation:

1. Keep the accepted L3 input pack, prompts, role TOML, isolation, deterministic Protocol helper,
   answer contract, platform lifecycle, acceptance gates, and cleanup path unchanged.
2. Reuse the L0/L1 raw-rollout audit contract and helper behavior as the regression oracle.
   Coordinator identity comes from the outer `thread.started`; delegation comes from the raw
   coordinator `spawn_agent` call plus `sub_agent_activity`; child identity and parentage come
   from the raw child `session_meta`. The role must be `modeling_agent` with
   `fork_turns="none"`.
3. Use retained `h/i` as positive role/fork fixtures, retained `g` as a negative fixture proving
   that a valid parent-child chain without `agent_type` is rejected, and add a negative
   transcript-only case. `task_name` must never substitute for `agent_type`, and the old
   transcript-only verifier must not remain as an alternate path.
4. Version the execution policy so it records `starts_consumed=3`, `max_starts=5`, the exact three
   consumed run IDs, and the user's two-start authorization. Budget enforcement remains global
   and happens before run-root, probe, Project, key, or Agent creation.
5. Append per-run corrections to historical classification evidence; never rewrite raw state or
   raw rollouts. For `g`, retain `collaboration/routing` but correct the reason from “no child” to
   “child role not configured”. For `h/i`, supersede the false no-child classification with the
   acceptance-harness finding. The fact that all three scopes stopped before Protocol/platform
   application remains historical evidence.
6. After offline developer and independent-test PASS, execute one fresh start. Use the fifth only
   if the fourth ends in a repairable `runtime/infrastructure`, `platform-contract`, or
   collaboration transport failure. A completed-model `modeling-quality` failure remains terminal.

No backend/frontend/platform code, new Host workflow, new prompt, new role, new Judge, or relaxed
semantic gate is authorized by this amendment.

## Implemented outcome

The recovery retained and reused run `l3-real-20260730k`; it did not create a sixth modeling-team
start. The same coordinator and Modeling Agent identified three consequential business gaps,
consumed the three exact frozen answers one at a time, and published one approved candidate and
dispatch.

Protocol application exposed four narrow non-modeling defects before the terminal success:

1. the Protocol namespace mounted the wrong Python path;
2. the Protocol prompt repeated the launcher-owned no-key probe;
3. platform dry-run admitted relative relation IRIs that could fail only during atomic apply; and
4. the original generic 300-second terminal budget was too short for the valid Protocol workload.

Each failure retained its transcript and exact cleanup evidence. The fixes reused the L1 runtime
mount and credential-proof pattern, validated all relation IRIs before delta creation, and assigned
the 900-second budget only to Protocol. A fifth Protocol execution completed successfully but the
Delivery Agent's deterministic execution script still expected one applied Batch receipt; that
result was hash-archived and the mechanical audit was corrected to require and verify every receipt
in a non-empty applied list.

The terminal Protocol execution applied three immutable Batches and left the separate invalid
dry-run Batch unapplied. Platform rereads prove a completed Build Session, released lease,
conforming validation, consistent reasoning, complete published path, Current Draft exclusion and
the explicit unknown. Cleanup proves model-key revocation, Project deletion, admin revocation,
isolated-process exit, Protocol credential-home destruction and absence of the exact temporary
secret. The Delivery Agent's execution record reports `PASS / PASSED / passed`; semantic acceptance
remains the independent Requirement Tester's responsibility, not an automatic Judge in the script.
Round 22 directly inspected those retained facts and returned `PASS` without starting or continuing
any live run.
