# R1.1-007 本地/正式建模执行 Profile 设计

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-007
- Delivery record:
  `docs/delivery/records/2026-07-21-r1-1-007-local-modeling-mode-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-22-r1-1-007-local-formal-modeling-profiles-test-plan.md`
- Status: implemented; independent test Round 14 composite-evidence PASS with accepted residual
- Priority: reduce nonessential Agent information without reducing modeling or retrieval quality

## Outcome

Deliver one modeling method with two execution profiles:

- **Local Modeling Mode** is the default for ordinary modeling and workflow optimization. It keeps
  current business meaning, source coverage, independent review, protected platform apply, and
  retrieval acceptance, while a narrow repo-local Adapter hides platform protocol mechanics and
  omits explicit productization records.
- **Formal Modeling Mode** keeps the existing platform-first Artifact/Event/Checkpoint workflow for
  formal delivery and full-chain evidence.

The profiles do not maintain different ontology rules, quality thresholds, or Modeling Item
semantics. Local is a smaller information and persistence envelope around the same work, not a
shorter workflow.

## Current state and gap

R1.1-006 already supplies the Local data plane through
`.codex/shared_modeling_directory.py`: current-state Brief/Coverage/Work Units, deterministic merge,
candidate hash, review gate, capacity-aware Batch planning, response binding, and structured
verification. It deliberately does not choose a Profile, activate Harness, load credentials,
create Build Sessions, acquire Leases, submit requests, or refresh Modeling Context.

The current `skills/ontology-builder/SKILL.md` is the Formal path. It explicitly restores and
persists Workflow Artifacts/Events, saves Checkpoints, handles Lease/apply, and completes the Build
Session. `.codex/fast_local_launcher.py` is a dual-session evaluation launcher, not an ordinary
Local modeling entry. The current Harness supports legacy Codex and dual-Claude evaluation modes,
but not a single-main-Claude Local profile with a current recording-health proof.

No backend, migration, REST/MCP, or frontend capability is missing for the first Local delivery.
The implementation gap is repo-local orchestration and Agent context shaping.

## Current minimal scope

The first version is restricted to one trusted developer machine, this repository checkout, the
local `ontology-platform.service`, and gitignored workspaces. It contains:

1. one shared modeling core and explicit Local/Formal selection rules in `ontology-builder`;
2. one narrow Local Adapter over the existing HTTP/platform contracts and R1.1-006 directory;
3. one ordinary single-main-Claude Local Harness profile plus recording-health checks;
4. four mode-neutral capability Skills and thin Claude subagent definitions;
5. deterministic tests and one real Local end-to-end quality run.

It does not add a generic workflow engine, remote deployment client, server-side Profile state,
platform Agent Runtime, credential vault, UI, or new API.

## Information contract

The Local design classifies information by whether a modeling role needs it, rather than whether it
already exists somewhere in the system.

| Information | Main modeling Agent | Capability subagent | Local Adapter/Harness | Platform |
| --- | --- | --- | --- | --- |
| Confirmed goal, scope, terms, rules, exceptions, CQ and gaps | current bounded Brief/Coverage | only referenced unit scope | path/hash or bounded visible summary | confirmed Brief fields and accepted CQ at commit boundary |
| Source material | stable locator/hash and selected excerpts | referenced sources for its task | never duplicates full body | exact Evidence excerpts/associations needed by applied Items |
| Current semantic baseline | bounded current read/query result | only when its role requires it | fetches authoritative context | authoritative current state |
| Candidate, review, Batch plan and verification | path, hash, verdict, Findings, next action | role-specific file only | reads/writes current adapter results | Batch/Attempt/Finding/Evidence and semantic results |
| Credentials, Lease token, workspace revision, idempotency and HTTP details | never | never | credential/Lease only in memory; durable retry metadata in private ignored state | authoritative protocol state |
| Artifact versions, Events, Checkpoints, audit history, runtime/cost metadata | omitted in Local | omitted | no explicit creation in Local | mandatory Batch/edit facts still arise from protected writes |
| Harness events | never used as modeling input | never used as modeling input | bounded background capture | never a platform fact |

The Shared Modeling Directory may contain its legitimate current candidate and Batch plan. “Do not
copy large payloads” means do not put them in prompts, messages, Harness, or duplicate adapter
records; it does not remove R1.1-006 files.

## Profile selection and composition

The main Skill selects and announces `execution_profile` before the first modeling action:

- default ordinary modeling/update and local workflow experiments: `local`;
- explicit formal delivery, complete platform record, or full-chain acceptance: `formal`;
- strict evaluation: `formal` plus R1.1-005 `evaluation_profile=strict_eval`;
- R1.1-005 `fast_local` remains a simulated-user evaluation aid and is not selected merely because
  execution is Local.

`execution_profile` is immutable for one run. Switching starts another run from current platform
state and explicitly selected local artifacts. The new run references the predecessor but cannot
retroactively manufacture Formal records for Local work.

The initial user intent plus confirmed scope authorizes Local to apply reviewed, non-destructive
additions and modifications in that scope. The main Agent does not ask for approval for each
deterministic Batch. It pauses for deletion, irreversible or unclear impact, scope expansion,
`apply_partial`, acceptance of unresolved material Findings, or a material conflict between current
platform state and confirmed user intent.

## Shared modeling core

`ontology-builder` owns one invariant phase and gate definition:

```text
business conversation and source analysis
  -> current Brief, CQ and Coverage
  -> bounded Work Units
  -> Work Unit modeling and Ontology merge
  -> candidate-bound independent review
  -> deterministic platform dry-run/apply
  -> CQ, retrieval, validation and provenance acceptance
```

Existing `modeling-guidelines.md`, the R1.1-006 schemas, Evidence rules, and semantic quality gates
remain shared. Profile-specific references define only persistence proof and adapter behavior:

- Local proof: current Shared Modeling Directory files, Adapter action results, platform Batch
  facts, and `verification.json`;
- Formal proof: versioned Workflow Artifacts, Events, Checkpoints, current platform facts, and the
  existing formal verification report.

The quality-gate reference must separate semantic conditions from the mechanism used to retain
their proof. No Local copy of the modeling guidelines or quality rules is permitted.

## Local runtime topology

```text
real user <-> main Agent using ontology-builder
                    |
                    +-- bounded runtime returns -- capability subagents
                    |                               (read referenced files)
                    |
                    +-- Local Adapter CLI ---------- protected platform HTTP
                    |       |                         Build Session / Batch / query
                    |       +-- Shared Modeling Directory
                    |       +-- private ignored retry state
                    |
                    +-- single-main Claude Harness (background evidence only)
```

The ordinary Local main Agent does not load `.claude/ontology-mcp.json`, because that server exposes
the complete Formal tool surface, including Workflow Artifact/Event/Checkpoint and Lease tools.
It uses the Local Adapter CLI plus ordinary file/Agent tools. Capability subagents receive no
platform write interface. This is context minimization, not a new authorization boundary; all
writes still authenticate through R-008.

## Local files and ownership

R1.1-006 remains authoritative for:

```text
workspaces/modeling-runs/<run-id>/
  run.json
  shared/...
  units/...
  ontologies/<ontology-id>/{candidate,review,batch-plan,verification}.json
```

R1.1-007 may add non-secret current execution references to `run.json`, including
`execution_profile=local`, Harness run ID, Build Session ID, and local-to-platform CQ bindings. It
does not store a Lease token, credential, raw response, hidden reasoning, or complete dialogue.

Protocol retry state is Adapter-owned and separate from worker-readable task state:

```text
workspaces/modeling-adapter/<run-id>/state.json
```

The directory and file are owner-only and gitignored. They may contain stable request IDs,
idempotency keys, current Session revision, Batch/Attempt IDs, and the last reconciled workspace
version needed for safe retry. They never contain the API key or Lease token. Platform current
state remains authoritative; this file is a recoverable client ledger, not a second workflow fact
store. A corrupt or missing ledger fails closed when an unknown apply outcome cannot be reconciled.

Harness raw state remains under `workspaces/ontology-harness/` and is never copied into either run
directory.

## Local lifecycle and Adapter actions

The implementation should expose one repo-local module, provisionally
`.codex/local_modeling_adapter.py`, with bounded JSON results. Exact CLI spelling is secondary, but
the functional actions are fixed:

1. **start**
   - require a loopback/local service and the same repository configuration;
   - load the existing gitignored API-key configuration without echoing it;
   - check health and Project/Ontology ownership;
   - create or reconcile one active Build Session without an initial Checkpoint;
   - initialize/bind the R1.1-006 run and activate the single-main Local Harness;
   - output only run/Profile/Session references, recording state, and the next business action.
2. **status / recording-health**
   - reconcile platform Session/Batch state, shared-directory validity, and Adapter state;
   - use a Hook-issued, current-session receipt/heartbeat to prove recording is advancing;
   - return one bounded current phase, blockers, and next action.
3. **commit-business**
   - run only after the business gate and first Coverage/CQ set are confirmed;
   - update only platform-supported confirmed Brief fields, without saving per-turn Interview
     Answers;
   - bind accepted CQ by existing platform ID or a unique exact
     `(ontology_id, normalized question, query_definition)` match; otherwise create once and store
     the returned binding;
   - mark user-accepted CQ `approved`; only use `testable/passed/failed` after a supported platform
     query definition is actually executed;
   - replace local CQ references with platform IDs before Work Unit modeling begins.
4. **dry-run-next / apply-next**
   - validate the run, candidate hash, candidate-level reviewer PASS, Batch plan, live limits, and
     current semantic baseline;
   - materialize the next dependency-ready Batch, serialize it, submit dry-run with a durable
     idempotency identity, and bind the platform response;
   - return Findings to the affected unit/reviewer. A material Finding pauses apply until explicit
     disposition; zero Findings may reuse the candidate review;
   - acquire a Lease only inside `apply-next`, apply the exact dry-run content with
     `apply_atomic`, release after the Attempt settles, refresh context, and continue in order.
5. **verify**
   - execute the predeclared platform-supported CQ checks and bounded Context Query/SPARQL checks;
   - store structured observed results or a contract-valid expected-empty assertion;
   - confirm every important applied Item has Evidence and sampled/targeted provenance; use a
     targeted lineage read only when query results do not prove traceability;
   - reject stale, partial, unsupported, or unexecuted checks.
6. **finish / cancel**
   - finish only after all planned Batches and verification pass; complete the Build Session and
     finalize Harness locally without publishing a retrospective;
   - cancel only an explicitly abandoned run with no in-flight Batch; do not erase confirmed
     Brief/CQ or applied platform facts;
   - interruption without explicit abandonment leaves the Session active for recovery.

Every action result uses one small versioned envelope containing action, status, stable public
references, bounded Findings/error code, retryability, and next action. It must not return raw
request/response bodies or protocol secrets.

## Capacity and deployment assumption

R1.1-006 planning needs the live item, request-byte, inline-Evidence, and excerpt limits. The current
platform does not expose them through Modeling Context or a public capability endpoint. The first
Local Adapter therefore accepts only the same repo-local service and reads the same `Settings`
configuration as that service. It rejects a non-loopback/unknown remote base URL or configuration
identity that cannot be tied to this checkout. Adding a server capability endpoint is future work,
not an R1.1-007 prerequisite.

## Harness design

Extend the existing recorder with `mode=single_claude` and
`execution_profile=local`; do not reuse `evaluation_profile=fast_local` or the two-role mailbox.
Activation binds the current Claude Session as `main_agent` through the trusted PreToolUse Hook.
The triggering user request is recorded as a secret-scanned bounded startup summary because the
run did not exist when that prompt originally arrived.

At phase boundaries, before resuming a subagent, before independent review, before apply, and before
final acceptance, the main Agent invokes `recording-health`. The command itself is acknowledged by
the current Hook and consumes a short-lived receipt, proving the current Session is still writing;
old metadata `ready=true` alone is insufficient. Failure pauses at that safe point. The user may
retry or explicitly continue as `recording_unavailable`; such a run can pass model quality but is
not a complete optimization sample.

Visible prompts and Agent outcomes pass both secret scanning and content classification. Source
bodies, candidates, and Batch payloads are recorded only by stable relative path, hash, and bounded
summary even when their byte count is under an existing generic text limit. Harness remains
fail-open at Hook execution level; the explicit safe-point health gate supplies workflow-level
pause semantics.

## Capability Skills and Claude wrappers

Create four repo-local Agent Skills:

| Skill | Reads | Writes/returns | Forbidden |
| --- | --- | --- | --- |
| `ontology-business-organizer` | run/shared sources and user-confirmed input | current Brief, Coverage, bounded questions | ontology design, platform writes |
| `ontology-work-unit-modeler` | one task, referenced sources/dependencies/current context | one schema-valid `result.json`, change assessment | user contact, Lease/apply, unrelated scope |
| `ontology-model-reviewer` | Brief/Coverage/sources/candidate and applicable dry-run Findings | candidate-bound PASS/REVISE/BLOCKED | editing candidate or apply |
| `ontology-retrieval-evaluator` | accepted CQ, current platform query results and verification schema | structured verification verdict/gaps | inventing results, platform writes |

Each Skill contains only role-specific methods and stop rules. Shared modeling rules stay under
`skills/ontology-builder/references/` and are referenced rather than copied. Existing Claude role
definitions become thin wrappers with `skills:` and narrow tools; add the retrieval evaluator
wrapper. The main Agent delegates only run/unit/Ontology, Schema/output paths, and a bounded change
message. Clarification returns directly through the Runtime to the main Agent and is not written to
a mailbox.

Official Claude Code documentation defines `skills:` as full Skill-content preload for custom
subagents. Local CLI 2.1.74 successfully parsed and listed a temporary project Agent using that
field; a real inference probe was blocked by missing Claude login. Implementation acceptance must
therefore perform a real authenticated preload/behavior probe rather than treating static parsing
as sufficient.

## Business changes and correction

Before apply, the main Agent sends each possibly affected Work Unit only the bounded change and
stable run references. The worker returns `no_change`, `modify_existing`, or `remodel` with reason.
`no_change` may rebind an input fingerprint only when normalized semantic content and gaps are
identical. Any semantic change invalidates review and Batch plan.

After apply, correction starts from platform current state. Additions/modifications follow the same
candidate-review-dry-run-apply-verification gates. Deletion, irreversible impact, unknown blast
radius, or a need for partial apply stops for user confirmation. Already applied valid Batch
prefixes are never automatically rolled back.

## Failure and recovery semantics

- Missing/invalid credential or Project scope: redacted failure; no downgrade or unauthenticated
  path.
- Harness activation/health failure: pause at the next safe point; retry or explicit
  `recording_unavailable` only.
- Missing source/dependency/schema: block the affected Work Unit; do not infer.
- CQ exact-match ambiguity: block business commit; never create another likely duplicate.
- Candidate/review/request hash mismatch: stop before platform submission.
- Dry-run Finding: return the bounded Finding and affected unit; no automatic waiver.
- Workspace conflict: keep successful prefix, read current context, and continue only if the exact
  reviewed content remains valid; otherwise regenerate and re-review.
- Timeout/unknown apply: reconcile the original Batch/Attempt and retry the same idempotency key;
  never create a replacement Batch to guess.
- Adapter ledger loss with unreconciled apply: fail closed and expose stable platform IDs for
  operator recovery.
- Brief/CQ committed but later Batch failed: keep confirmed business facts and resume; no
  cross-resource rollback claim.

## Formal Profile

Formal is the existing platform-first `ontology-builder` path, adjusted only to consume the same
core phase/gate definitions and capability Skills. It continues to persist immutable Pack/Matrix,
draft, review and verification Artifact versions; Execution Events; Checkpoints; reliable large
handoffs; formal recovery; and explicit completion records. Formal delivery does not require Local
Harness. `strict_eval` composes Formal with the R1.1-005 dual-session Harness and remains a separate
hard gate.

## Expected implementation surfaces

- `skills/ontology-builder/SKILL.md` and existing shared references;
- four new `skills/ontology-*/` capability Skill directories;
- `.claude/agents/` thin wrappers and one retrieval-evaluator wrapper;
- `.codex/local_modeling_adapter.py` and a concise Local/Formal runbook;
- narrowly necessary R1.1-006 extensions for Profile/CQ binding and current dry-run evidence;
- `.codex/hooks/modeling_harness.py` for single-Claude Local activation and recording health;
- focused `.codex/tests/`, Skill validation/evals, requirements/glossary/guide alignment.

Backend/frontend code is not expected. If implementation evidence proves an existing API cannot
safely satisfy the contract, stop and revise this plan rather than silently adding a platform
surface.

## Acceptance and rollout

Acceptance follows the shared test plan. The hard proof is one real Local run over the fixed Dify
corpus or an equally representative source set. It must preserve complete current business
semantics and Coverage, use independent Claude subagents with preloaded Skills, perform protected
multi-Batch dry-run/apply, answer predeclared CQ/retrieval checks, and prove important-item
provenance. The last accepted scenario is the quality floor; exact graph equality is not required,
but silent coverage loss, unsupported claims, weaker evidence, unresolved blocking Findings, or
failed CQ are failures.

No Local-vs-Formal duration, Token, or tool-count comparison is required. Deterministic fixture
tests prove that both adapters consume the same candidate semantics; Formal regression proves the
existing full path remains usable. Rollback removes the Local Adapter/Profile and new wrappers,
leaving R1.1-006 files, Formal platform facts, and existing Harness modes readable.

## Future productization

Deferred until real use proves a need: remote service capability discovery, cross-machine shared
state, server-hosted Profile runs, durable distributed Adapter recovery, automatic crash cleanup,
fine-grained role credentials, generic tool-surface filtering, UI, retention, audit export, and
Codex subagent wiring.
