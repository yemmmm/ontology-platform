# R2.0-002 Pi 第一方建模 Agent Runtime 正式集成设计

- Requirement: `docs/requirements/requirements-v2.0.md` R2.0-002
- Delivery record:
  `docs/delivery/records/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-test-plan.md`
- Architecture decision:
  `docs/architecture/decisions/0007-first-party-modeling-runtime-boundary.md`
- Status: paused at retained checkpoint; reviewed contract kept as historical baseline, no further
  execution before v2.1 R2.1-001 refinement
- Priority: modeling quality and semantic retrieval quality first

## Outcome

Deliver one repo-local Pi Local modeling command that owns the complete daily modeling workflow:
source understanding, user interview, Brief/CQ confirmation, Work Unit modeling, independent review,
deterministic dry-run/apply, and post-apply CQ/retrieval/provenance verification.

Pi becomes the only supported and actively maintained modeling Runtime. Semantic Platform Core keeps
its current deterministic authority and receives no Pi-specific API, database schema, or special
write path.

## Current minimal scope

The current delivery is a local development workflow on one machine and one checkout. It includes:

1. a pinned Pi dependency and one local command;
2. a Pi-only Workflow Package with the confirmed roles and quality gates;
3. a small Runner that launches and observes headless Pi RPC child processes;
4. the existing Shared Modeling Directory and deterministic Local Adapter core, migrated out of
   Claude/Codex-specific wrappers;
5. repo-local events and stage summaries;
6. one real fixed-corpus end-to-end run against the existing platform;
7. retirement of the old Claude modeling path after the Pi run independently passes.

Future productization is explicitly excluded: backend hosting, remote execution, distributed
scheduling, production sandbox/security, complete crash recovery, service-side event storage, UI,
release distribution, automatic upgrades, and Pi Formal/strict-eval.

## Functional contract

### Entry and result

The entry command accepts a gitignored local configuration plus a tracked scenario. The local
configuration selects the existing Project, platform base URL, credential source, model/provider,
and an optional bounded Work Unit concurrency limit. The tracked scenario contains only reusable
business input: goal, source locators, constraints, and acceptance questions.

The run is complete only when the applied model passes the required CQ, semantic retrieval, and
provenance checks. Candidate generation or dry-run alone is not completion.

### Roles

- **Coordinator:** one persistent Pi RPC Session for user conversation and stage decisions.
- **Business organizer:** a fresh Session that produces Brief/CQ/Coverage artifacts only.
- **Work Unit modeler:** a fresh Session per Work Unit that writes only its assigned result.
- **Model reviewer:** a fresh Session that sees sources, business contract, and candidate but no
  hidden modeler conversation.
- **Stage summarizer:** a short-lived restricted Session that reads bounded visible events and
  stable artifact references and writes one schema-valid Summary.

Only Work Units proven independent by the current Coverage/dependency contract may run in parallel.
The local config may cap parallel workers; the default is one. Same-Ontology results always merge
into one candidate before review.

### User confirmation

The coordinator pauses for the user before the business commit, when source evidence cannot resolve
an ambiguity, and before applying deletion, irreversible, or unknown-impact changes. Ordinary
additions and bounded modifications apply automatically after independent PASS, candidate/request
hash agreement, and clean dry-run.

## Component boundary

```text
terminal user
  -> pi-modeling-agent Runner
       -> coordinator RPC Session
       -> disposable role RPC Sessions
       -> Pi-only Workflow Package
       -> repo-local events and Shared Modeling Directory
       -> internal deterministic platform adapter
            -> existing REST/MCP contracts
                 -> Semantic Platform Core
```

The Runner owns Runtime lifecycle and observable orchestration. The Workflow Package owns modeling
judgment and role methods. The migrated Python library owns deterministic files, hashes, Batch
planning, platform requests, idempotency, and verification. The platform remains the sole authority
for applied semantic facts.

## Proposed repository layout

```text
pi-modeling-agent/
  package.json
  package-lock.json
  README.md
  src/
    cli.mjs
    runner.mjs
    rpc-session.mjs
    event-recorder.mjs
    stage-summary.mjs
  extensions/
    modeling-tools.ts
  workflow/
    coordinator.md
    business-organizer.md
    work-unit-modeler.md
    model-reviewer.md
    stage-summarizer.md
    references/
    schemas/
  lib/
    shared_modeling_directory.py
    platform_adapter.py
  scenarios/
    dify-foundations-v1.json
  tests/
```

The exact file split is implementation-level and may be reduced, but the ownership boundaries must
remain. No second Claude-compatible rule tree is generated.

Run data remains gitignored under `workspaces/modeling-runs/<run-id>/`. Machine-local configuration
uses a separate gitignored path under `workspaces/pi-modeling/`. Credentials never enter the tracked
scenario, prompts, event file, artifacts, or committed configuration.

## Runtime lifecycle

1. The CLI validates Node `>=22.19.0`, pinned package availability, local config, tracked scenario,
   platform health, and explicit project resource trust.
2. It creates or reconciles the local run and empty active Build Session using the existing
   idempotent identities.
3. It starts the coordinator with exact Workflow Package and tool inventory and records its Pi
   Session ID as local observability data, not platform truth.
4. The Runner starts each role as a headless RPC child with bounded role prompt, tools, and stable
   input locators. `agent_end` is only a low-level run boundary: an auto-retry, compaction retry, or
   queued follow-up may still continue the same role.
5. A disposable role's schema-valid artifact remains a candidate until the Runner observes
   `agent_settled`, the modeling Extension confirms `ctx.isIdle()` and no pending messages, and the
   latest `queue_update` is empty. Only then may the Runner accept the artifact, gracefully shut
   down, and await that child. A timeout kills only the affected role and leaves stable artifacts
   for a targeted rerun.
6. The persistent coordinator may settle after an individual user turn without being complete. It
   remains alive until final verification, explicit cancellation, or a visible terminal failure;
   only after that workflow terminal state and the same settled/idle/empty-queue checks does the
   Runner shut it down and write the terminal local result.

The Runner does not promise to restore a crashed Pi process or chat. Recovery starts a new process
against the same validated shared artifacts.

## Workflow Package and context rules

The Pi Workflow Package is the canonical modeling method. Existing `ontology-builder` and role
Skill content may be migrated and simplified, but the final maintained source lives only under the
Pi package.

Every role receives:

- its role prompt and shared quality references;
- the run, phase, Work Unit/Ontology, schema, output, and dependency locators it needs;
- bounded user answers or Findings relevant to its task;
- no unrelated Work Unit result, full chat history, hidden reasoning, raw platform response,
  credential, Lease token, or unneeded Batch content.

Domain names such as Dify Workflow or Node occur only in the tracked acceptance scenario and test
assertions. Runtime and platform production code operate on generic modeled resources and commands.

## Structured tools and deterministic adapter

Pi Extensions expose schema-validated tools for clarification, artifact writes, stage completion,
and platform actions. Tools return bounded envelopes with status, stable references, Findings, and
next action; they never return credentials or large raw responses.

The current deterministic core is migrated rather than reimplemented:

- `shared_modeling_directory.py` keeps current file ownership, fingerprints, candidate hashing,
  review binding, Batch partitioning, materialization, and verification contracts;
- `local_modeling_adapter.py` becomes an internal `platform_adapter.py` used only by the Pi Runner;
- Build Session, Brief/CQ, capacity, dry-run/apply, idempotency, reconciliation, and verification
  semantics stay unchanged;
- Claude Harness receipt, `recording-health`, `recording-unavailable`, profile routing, and Harness
  finalization are removed.

The Runner records `tool_execution_start` before each internal adapter call and
`tool_execution_end` after its bounded result. This event wrapping is observability, not a new
authorization protocol. Unknown apply outcomes still reconcile the original stored attempt before
any retry.

The model never receives an unrestricted generic platform write tool. Role tools are narrower than
the adapter; only the Runner advances deterministic stages and invokes protected writes after the
required artifacts and confirmations exist.

## Events and stage summaries

Each run stores an append-only local JSONL event stream. Minimum event classes are:

- run/role/Session and stage start/end;
- model call start/end/error;
- queue changes, auto-retry, compaction start/end, `agent_end`, `agent_settled`, and terminal idle
  eligibility;
- tool call start/end/error with tool name and bounded references;
- clarification requested, paused, answered, and resumed;
- artifact accepted/rejected with locator/hash;
- terminal success, cancellation, timeout, or failure reason.

The event stream does not contain hidden reasoning, full prompts/transcripts, source bodies, raw
tool responses, or secrets.

At the end of business organization, each Work Unit, independent review/apply, and final
verification, the Runner launches a restricted summarizer. It sees only the stage's bounded events
and artifact references and must produce the shared Summary schema fields: stage, roles, goal,
actions, inputs/outputs, issues/decisions, result, unresolved, and next step. A missing or invalid
Summary blocks that stage's completion record but does not roll back already applied platform data.

## Failure and recovery

- Invalid role output: reject it before merge and rerun only that role with the same stable inputs.
- Stale input fingerprint: block merge until the affected Work Unit is rerun or a bounded
  `no_change` assessment satisfies the existing contract.
- Review `REVISE/BLOCKED`: return only findings and affected locators; regenerate, merge, and review
  again before Batch planning.
- Platform Finding: map to affected Work Units and repeat merge/review/dry-run; never waive it in
  the Runtime.
- Unknown apply: reconcile original Batch/attempt/idempotency identity; never create a replacement
  Batch to guess.
- Later Batch failure: keep the valid applied prefix and continue from platform current state.
- Clarification: pause the run and resume from shared artifacts after the user's answer.
- Process loss: start a new role process; no complete chat/hidden-state recovery claim.

## Claude retirement and rollout

Retirement is two-phase so the only fallback is removed after, not before, Pi proves the contract:

1. implement and independently run the complete Pi path while the frozen Claude files still exist;
2. after the Pi real-runtime round passes, remove Claude-specific modeling Agents, Hook/Harness,
   launchers, summaries, scenarios/adapters, active tests, and current runbooks;
3. retain Git history and historical delivery records; migrate platform-neutral deterministic code
   and tests into the Pi package;
4. replace README's ontology-builder installation/run claims, the hard-coded
   `backend/tests/test_documentation_sync.py` ontology-builder contract, and
   `.github/workflows/docs-sync.yml` Skill validator/eval steps with the current Pi package contract
   or remove a check proven obsolete; no active CI or documentation may read a deleted path;
5. update v1.1 current-status wording to state that those delivered historical paths are superseded
   and no longer supported after R2.0-002;
6. accept ADR 0007 and synchronize the v1.0/v2.0/architecture boundary wording;
7. run the full backend suite required by the planned backend contract-test edit, the docs-sync
   check, and a final independent retirement/regression round on the post-removal stable state.

Do not delete `.claude/skills/gitnexus`, repository instructions, or other non-modeling developer
configuration merely because it lives under `.claude`.

After closure the supported matrix is deliberately small: Pi Local is supported; Claude Local,
Claude fast-local/strict-eval, and Formal are unsupported. A future Pi Formal path requires a new
requirement.

## Verification and completion

Automated verification covers dependency/lock checks, RPC lifecycle including retry/compaction/
queued-continuation settlement, role tool inventories, artifact schemas, context boundaries, Shared
Directory invariants, adapter semantics, event/Summary contracts, targeted recovery, and absence of
active Claude modeling references or CI dependencies.

Real-runtime acceptance uses the fixed Dify Foundations corpus or an explicitly approved equivalent.
It must use a real pinned Pi runtime/model and the real local platform to complete interview through
apply and post-apply CQ/retrieval/provenance verification. Mock-only success cannot close the
requirement.

There is no Claude quality comparison, performance/cost target, required bottleneck discovery, or
second optimization run. Completion means the migrated Pi workflow passes the existing quality
floor and the old Claude workflow is cleanly retired.
