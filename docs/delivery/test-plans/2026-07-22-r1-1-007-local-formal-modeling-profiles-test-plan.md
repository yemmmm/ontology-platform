# R1.1-007 本地/正式建模执行 Profile 共享测试计划

- Requirement: `docs/requirements/requirements-v1.1.md` R1.1-007
- Design:
  `docs/delivery/designs/2026-07-22-r1-1-007-local-formal-modeling-profiles-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-21-r1-1-007-local-modeling-mode-delivery-record.md`
- Status: independent plan review PASS; implementation not started and awaits user approval

## Completion gates

1. Independent plan review reports PASS with no unresolved accepted Critical/High finding.
2. Requirement, design, shared core, Profile schemas, Local runbook, Agent/Skill definitions, and
   tests agree on one modeling workflow and two persistence/adapter envelopes.
3. Focused Local Adapter, Harness, shared-directory, Skill, and routing tests all pass, and existing
   R1.1-005/R1.1-006/Formal regressions remain green.
4. A real authenticated single-main-Claude Local run uses the four preloaded capability Skills and
   completes multi-round business confirmation, protected dry-run/apply, and retrieval/provenance
   acceptance on the fixed Dify corpus or an equally representative scenario.
5. The real run meets the last accepted scenario quality floor: no silent Coverage loss,
   unsupported invention, unresolved blocking Finding, missing important-item Evidence, failed CQ,
   or unproved retrieval result.
6. Independent tester appends a PASS round to this plan on a stable implementation state.
7. Documentation/status, uniquely owned test-data cleanup, runtime health, diff/secret checks, and
   commit closure are complete.

No gate compares duration, Token use, tool-call count, or exact Local/Formal graph equality.

## A. Profile selection and composition

- Ordinary real-user modeling/update selects `execution_profile=local` by default and reports it
  before the first modeling action.
- Explicit formal delivery, complete platform recording, or full-chain acceptance selects
  `formal`; strict evaluation selects `formal + evaluation_profile=strict_eval`.
- R1.1-005 `fast_local` remains a simulated-user evaluation profile and never becomes the ordinary
  Local entry by name collision or fallback.
- Profile selection is written once per run. Attempts to mutate it in place fail and instruct the
  caller to create a new run. A new Formal run can reference selected Local artifacts/current
  platform state but cannot claim retroactive Artifact/Event/Checkpoint history.
- Unknown/ambiguous intent produces a visible recommendation but no silent switch. A requested
  Formal path never downgrades to Local when a Formal dependency fails.

## B. Shared core and information-minimization contract

- Static dependency tests prove Local and Formal reference the same business interview, source,
  modeling guideline, quality-gate, Modeling Item, review, and verification definitions. Fail on a
  copied Profile-specific rule file or divergent quality threshold.
- Feed one canonical candidate fixture to both adapters and prove normalized Modeling Items,
  Evidence associations, CQ bindings, candidate hash, and semantic request content are identical;
  only profile envelope/recording fields may differ.
- Inspect generated main-Agent and subagent handoffs. The main receives only Profile/run/phase,
  bounded questions/Findings/status/next action. Each subagent receives only run path,
  Work Unit/Ontology, Schema/output paths, and a bounded change message.
- Fail if a handoff embeds the Brief/source body, unrelated unit result, complete candidate/Batch,
  raw HTTP/MCP response, platform history, cost/runtime metadata, credential, Lease token,
  workspace revision, or idempotency value.
- Prove full current business semantics remain available by reference: goal/success, scope/non-goal,
  source authority, terminology, participants/objects/events, identity/lifecycle, boundaries,
  rules/exceptions, ambiguities/gaps, accepted CQ, and explicit Coverage states.
- Prove the Shared Modeling Directory continues to contain legitimate current candidate and Batch
  plan files; information minimization must not delete its data-plane contract.

## C. Local start, bounded Adapter surface, and secrets

- Start against the same repo-local service with a valid ignored configuration. Check health,
  Project/Ontology ownership, one active Build Session, initialized run, fixed Local Profile, and
  active single-main Harness.
- The Local Claude entry does not load `.claude/ontology-mcp.json` or expose Workflow
  Artifact/Event/Checkpoint/Lease write tools. It can reach the platform only through bounded Local
  Adapter actions. Capability subagents have no platform write interface.
- Reject non-loopback/unknown remote `api_base_url`, missing/mismatched local capacity settings,
  invalid Project ownership, missing/revoked/insufficient-scope key, and unhealthy service before
  modeling continues.
- Reuse existing config semantics; never add an unauthenticated fallback. Verify errors contain a
  stable redacted code and no response body or secret substring.
- Use a unique secret sentinel as the configured key. Scan prompts, run/shared files, private
  Adapter state, Harness, stdout/stderr captures, tracked diff, staged diff, and new commit content;
  the sentinel must occur zero times outside its source credential file.
- Inspect owner permissions for private Adapter/Harness state. API key and Lease token never persist;
  durable state may contain only non-secret request/recovery identities.
- Every CLI action returns only the versioned bounded envelope and rejects oversized/raw diagnostic
  output.

## D. Business commit boundary

- Before commit, conduct source scan and multi-round business confirmation entirely in the Shared
  Modeling Directory. Cancel and prove no Project Brief/CQ/candidate/Batch business write occurred;
  only the empty automated Build Session/Harness may exist and is safely cancelled/finalized.
- Enter commit only after the business gate and first Coverage/CQ set are confirmed. Synchronize
  supported confirmed Brief fields without creating per-turn Interview Answer records.
- Create/bind accepted CQ before Work Unit modeling, place returned platform CQ IDs into Coverage
  and task contracts, and prove every resulting candidate/review/Batch uses those IDs without a
  post-review rewrite.
- Retry a previously created CQ after a simulated client crash. Reuse the stored platform ID or one
  unique exact `(ontology_id, normalized question, query_definition)` match; create no duplicate.
  Multiple exact matches fail as `business_sync_ambiguous`.
- Mark accepted CQ `approved` only when its confirmed Brief source exists. Advance to `testable` and
  `passed/failed` only for a platform-supported query definition that is actually executed.
  Context Query/qualitative acceptance remains structured local verification and never fabricates
  platform `passed`.
- Change a confirmed Brief field after prior CQ validation and prove stale CQ state is observed and
  revalidated; stale state cannot pass final acceptance.
- Fail later apply/verification after commit and prove confirmed Brief/CQ remain, the run is
  recoverable, and no unsupported cross-resource rollback is claimed.

## E. Capability Skills and Runtime handoff

- Validate all four Skill directories with repository/static validation and the current
  skill-creator validator. Shared core links resolve; no role Skill copies the common guideline or
  embeds domain-specific business content.
- `claude agents --setting-sources project` lists the four corresponding wrappers and recognizes
  their `skills:` frontmatter.
- In an authenticated real Claude session, invoke each wrapper and use a unique marker assertion to
  prove its Skill content was preloaded, not merely discoverable by filename.
- Business organizer reads sources/current user confirmations and writes Brief/Coverage/questions,
  never Modeling Items. Work-unit modeler writes only its assigned result and change assessment.
  Reviewer independently returns candidate-bound PASS/REVISE/BLOCKED. Retrieval evaluator returns
  structured observed verification/gaps without inventing results.
- Have a worker raise a real clarification. It stops and returns directly to the main Agent through
  the Runtime; no shared-directory mailbox/reasoning file appears. The main Agent answers from
  confirmed context or asks the user, then resumes the same bounded task.
- Replace one worker with a fresh Session and complete from run files without prior chat or Harness
  replay.

## F. Single-main Local Harness

- Activate one real Claude top-level Session as `mode=single_claude`,
  `execution_profile=local`, `participant=main_agent`; no simulated-user peer or mailbox is required.
- Record the triggering request as a secret-scanned bounded startup summary, then capture subsequent
  visible user/main dialogue, subagent start/stop and bounded return, phase change, review/rework,
  Adapter outcome, and final verification.
- Before each defined safe point, run `recording-health`. Prove the command consumes a fresh
  Hook-issued receipt for the current Session/epoch and advances/observes a current sequence.
  Old `ready=true`, a different Session, replayed receipt, expired receipt, or removed binding fails.
- Simulate activation failure and mid-run Hook interruption. The next safe point pauses and reports
  the problem. Only explicit user choice resumes as `recording_unavailable`; the run can pass model
  acceptance but is marked incomplete for process optimization.
- Feed short and long source/candidate/payload-like content below/above generic text limits. Both
  are stored only as path/hash/bounded summary; hidden reasoning, transcript paths, credentials,
  raw source/candidate/Batch and activation material occur zero times.
- Normal Local finish stays gitignored/local and publishes no retrospective. R1.1-005 strict and
  fast-local Harness tests remain unchanged and green.

## G. Protected dry-run/apply and recovery

- Plan with the exact four local-service limits and serialize every request before submission.
  Reject a config identity mismatch rather than guessing remote limits.
- Candidate-level independent review PASS is required before planning. Dry-run every next
  dependency-ready materialized Batch; any material Finding pauses apply and is returned to the
  affected unit/reviewer. Zero Findings may reuse the candidate review.
- Acquire Lease only inside apply, use current workspace version and a durable idempotency identity,
  submit the exact dry-run content with `apply_atomic`, wait/reconcile the Attempt, release Lease,
  refresh context, and then materialize the next Batch.
- Prove the Agent-facing result never contains Lease token, workspace revision, idempotency key,
  capacity mechanics, raw request/response, audit body, or internal graph identifiers.
- Exercise item count, request bytes, inline Evidence count, excerpt length, cross-Batch references,
  and at least a `[100, 100, 5]`-class ordered plan. Every dry-run/apply pair reuses the planned
  `client_batch_id` and platform `batch_id` with identical immutable content.
- Attempt `apply_partial`; require explicit user authorization and never silently fall back from
  atomic application.
- Inject timeout/connection loss. Reconcile the original Batch/Attempt and retry the same
  idempotency key; do not create a replacement Batch.
- Inject a workspace conflict/later-Batch failure. Preserve the applied prefix, refresh current
  state, and continue only if exact reviewed semantics remain valid. Semantic change requires a new
  candidate hash/review/Batch identity.
- Verify Local did not explicitly create Workflow Artifact/Event/Checkpoint or retrospective, but
  platform-required Batch/Attempt/Item/Finding/Evidence Association/edit-audit/revision facts exist
  as appropriate. Do not assert that protected apply is audit-free.

## H. Business change and correction

- Change one user-confirmed statement and notify only possibly affected workers. Require each to
  return `no_change`, `modify_existing`, or `remodel` plus reason.
- Accept `no_change` only when normalized semantic items and gaps are identical; rebind the input
  fingerprint without changing candidate hash/review/Batch usability.
- A semantic edit changes candidate hash and invalidates review and Batch plan. Unaffected units
  remain reusable.
- After apply, create an incremental correction from platform current state and repeat review,
  dry-run/apply, affected/dependent CQ, retrieval, and provenance checks.
- Deletion, irreversible/unknown impact, out-of-scope work, unresolved material Finding, or a need
  for partial apply stops for real user confirmation.

## I. Verification and quality floor

- Use the fixed R1.1-004 Dify corpus or an equally representative immutable source set. Declare CQ,
  retrieval expectations, scope/non-goals, source authority, and quality floor before modeling.
- Execute a real Local run with multiple user-confirmation rounds, at least two bounded Work Units,
  independent review, real platform dry-run/apply, and persisted-state verification.
- Coverage has no silently dropped important item; every item is modeled/deferred/ambiguous/
  unsupported/missing with an accepted disposition.
- Important applied Items have exact Evidence excerpt/reference associations. Retrieval results
  contain stable resources/relations and bounded provenance. If they do not prove traceability,
  execute targeted lineage checks; stale/partial/unexecuted evidence fails.
- `verification.json` covers every accepted CQ and contains an executed query/check description plus
  structured non-empty results or a contract-valid expected-empty assertion. All blocking gaps are
  closed or explicitly accepted under the user-confirmation rules.
- Independent reviewer and retrieval evaluator both report PASS. Result supports every predeclared
  high-priority CQ at least as well as the last accepted scenario; no exact graph or efficiency
  comparison is required.

## J. Formal regression and compatibility

- Run existing `ontology-builder` validation/evals and representative Formal workflow tests.
  Formal still persists Artifact/Event/Checkpoint/formal verification and uses complete MCP.
- Strict evaluation still requires the R1.1-005 dual-session Harness and cannot pass with a Local
  single-main run. Formal delivery without strict evaluation does not require Local Harness.
- Existing legacy Codex Harness, strict-eval, fast-local, reliable handoff, and R1.1-006 directory
  fixtures remain readable and green.
- Profile additions do not change backend API schemas, migrations, frontend behavior, or applied
  platform semantic semantics.

## K. Required checks

At each stable developer/tester handoff, run the applicable subset; run all before closure:

- `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m unittest discover -s .codex/tests -p 'test_*.py' -v`
- focused new Adapter/Profile/Harness/role tests;
- `cd backend && uv run ruff check <all changed Python files>`;
- `cd backend && uv run ruff format --check <all changed Python files>`;
- `python skills/ontology-builder/evals/validate_skill.py`;
- `python skills/ontology-builder/evals/run_evals.py` when shared Skill behavior/evals change;
- current skill-creator `quick_validate.py` for `ontology-builder` and each new capability Skill;
- JSON/YAML parsing for Profile schemas, Claude Agent frontmatter/config, and representative run
  fixtures;
- authenticated real Claude Skill-preload, clarification-return, Harness-health, and full Local run
  probes;
- real local platform health, authenticated Batch/query path, and uniquely scoped DB/RDF cleanup
  evidence;
- `git diff --check`, scoped `git status --short`, secret-sentinel scan, and GitNexus
  `detect_changes(scope="compare", base_ref="main")` before commit.

No backend/frontend change is planned, so no service restart is required merely for repo-local
Skill/Adapter/Harness files. The real platform acceptance still verifies
`ontology-platform.service`, backend `/api/health`, frontend `/`, and restores any temporary product
write mode/configuration. If implementation unexpectedly changes backend or frontend, apply the
full `AGENTS.md` test and restart rules.

## Cleanup and residual evidence

- Use unique run/Project/Ontology/Session identities. Delete only test data whose ownership is
  proven by those identities.
- Recheck zero matching Project/Batch rows and RDF graphs after cleanup. Restore product write mode
  and any temporary manager override/configuration.
- Remove or retain gitignored Harness/Adapter/run evidence only when the shared test round states
  its exact purpose and ownership. Never delete an unrelated developer run.
- Record unexecuted GUI/interactive/runtime cases and environment blockers; static or mock success
  cannot replace the authenticated Claude and real platform hard gates.

## Plan review rounds

### Round 1 — 2026-07-22 — PASS

- Reviewer: independent `plan_reviewer` subagent.
- Reviewed scope: authoritative R1.1-007 requirement, design, this unique shared test plan,
  delivery record, glossary, and the relevant current repository implementation.
- Result: PASS. No evidence-backed Critical or High finding was found.
- Reviewer-confirmed coverage: Local information minimization preserves business/Coverage/Evidence,
  independent review, protected dry-run/apply, CQ/retrieval and provenance gates; the business
  commit boundary precedes Work Unit modeling; the narrow Adapter isolates the Formal MCP surface;
  receipt-backed Harness health blocks on interrupted recording; Local/Formal/evaluation profiles
  remain orthogonal; authenticated Claude and real-platform quality acceptance remain hard gates.
- Disposition: no design change required. Implementation remains paused pending user approval.

## Independent test rounds

Implementation has not started. Test rounds are append-only; a later PASS must not delete an
earlier failed round.

### Independent test Round 1 — 2026-07-22 — FAIL

- Tester: independent requirement tester. Scope was the R1.1-007 implementation manifest supplied
  at handoff; no product source, requirement, design, glossary, delivery record, test fixture, or
  runtime configuration was changed. The implementation-file manifest reconstructed from the 23
  changed/new `.codex/`, `.claude/`, and `skills/` files matched the supplied
  `f21a1c483c762b723c397ce25e1c3b4dd45c950973b80df64cac3fffe0ff9ce9` exactly. The checkout HEAD
  observed during this round was `c5818418f3ee539000e324052915f49fcde4800c`, rather than the
  handoff's earlier `ae81d305b65edbae291e4d6449fdd2bb67a40b20`.
- Executed PASS evidence:
  `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m unittest discover -s .codex/tests -p
  'test_*.py' -v` completed `99/99`; focused Adapter/Profile/Harness/shared-directory discovery
  suites completed `13 + 2 + 37 + 14` tests; Ruff check and format check passed for all four changed
  Python implementation files; `python3 skills/ontology-builder/evals/validate_skill.py` and
  `run_evals.py` passed (`10` references, `34` declared MCP dependencies, `7` eval cases); current
  `quick_validate.py` passed for ontology-builder and all four new Skills; JSON/YAML/frontmatter
  parsing passed; all role-Skill shared reference links resolved; profile routing probes passed;
  the Adapter request field names were compared with current REST schema source; `git diff --check`
  passed; no backend/frontend path is changed; `ontology-platform.service` was active and both
  `GET /api/health` and frontend `/` succeeded. Static role/wrapper inspection also confirmed the
  four wrappers are listed by `claude agents --setting-sources project`, their `skills:` values
  match their role Skills, and no new local config or full-MCP config file is checked in.
- **High — Local path still exposes and directs the full Formal MCP workflow.**
  `skills/ontology-builder/SKILL.md:23-30` requires Local to use the Adapter as its only
  platform-write path, but the same unqualified Skill later instructs the selected caller to use
  `mcp:get_project_build_context`, Workflow Artifact/Event calls, checkpoint calls, direct lease
  and batch calls, and formal verification at lines `63-79`, `93-110`, and `131-160`. No branch
  confines those instructions to Formal. A Local main Agent can therefore receive and follow the
  forbidden full MCP surface, contrary to requirement R1.1-007 lines `1070-1073` and the Local
  minimum-scope contract. Reproduce: select `execution_profile=local`, then follow the Skill's
  next `Start by recovering` and staged-workflow instructions. Expected: only the bounded Local
  Adapter performs Local platform writes and no Artifact/Event/Checkpoint orchestration is
  prescribed. Actual: the same Local-visible Skill prescribes those calls. Existing static/eval
  checks did not detect this contradiction.
- **High — fresh Harness health is not enforced at later Local safe points.**
  `.codex/local_modeling_adapter.py:328-347` calls `_require_recording_ready` only in
  `commit_business`; `dry_run_next` (`841-904`), `apply_next` (`907-1020`), `verify` (`678-730`),
  and `finish` (`733-792`) do not require or consume a new receipt. `recording_health` stores only
  a matching `harness_run_id` at lines `668-669`, so an old successful health result can allow the
  later actions. Reproduce: complete the initial health call, then invoke the later Adapter
  commands without another health receipt. Expected: each required phase/review/apply/final
  verification safe point fails closed until a fresh current-session receipt is consumed. Actual:
  only the business-commit boundary is checked. This contradicts requirement lines `1046-1053` and
  test-plan section F.
- **High — Adapter can approve an unaccepted CQ whose stated Brief source is not confirmed.**
  `.codex/local_modeling_adapter.py:351-357` rejects only an explicit `accepted: false`, and
  lines `421-427` default a missing `accepted` value to approval. `_question_payload` at lines
  `307-325` validates the shape of `source_brief_fields` but never proves the fields are in the
  manifest's `confirmed_fields`; no later check supplies that proof. An isolated temporary-fixture
  probe submitted a question with no `accepted` field and `source_brief_fields: ["scope"]` while
  only `business_goal` was confirmed: `commit_business` returned `ok`, created the CQ, and posted
  its `approved` status. Expected: no CQ is approved unless acceptance is explicit and its
  confirmed Brief source exists. This contradicts test-plan section D and requirement lines
  `974-999`. The existing `test_unaccepted_question_rejects_before_any_platform_write` covers only
  explicit `false`, not this omission/source mismatch.
- BLOCKED hard gates and unexecuted cases: `claude auth status` reported
  `loggedIn: true`/`oauth_token`, and `claude agents --setting-sources project` listed all four
  wrappers, but each authenticated preload probe (`claude -p --setting-sources project --agent
  <role> --tools '' ...`) returned exactly `Not logged in · Please run /login`. Consequently
  authenticated Skill-preload marker assertions, real worker clarification return, fresh Claude
  Hook-receipt flow, and the full single-main Local run were not executable. In addition,
  `.claude/local-modeling.json` is absent (only the redacted example exists), so there is no
  proven-owned Project/API-key configuration. A real Batch/query acceptance cannot be safely
  created or cleaned up without that identity and was not attempted. The required unique secret
  sentinel scan was likewise not executable because no configured test credential may be added by
  this tester. API OpenAPI endpoints returned `401` without credentials; source-level route/schema
  comparison was performed instead. No test Project, Ontology, Session, Batch, RDF graph, Harness
  run, configuration, or product data was created, so no cleanup action was required.
- Residual/tooling evidence: GitNexus `detect_changes(scope="compare", base_ref="main")` reported
  low affected-process risk but its index is 13 commits behind HEAD, so it is not treated as
  current coverage evidence. `python` is absent from PATH; all planned repository Python checks
  were run with explicit `python3` or `backend/.venv/bin/python`.
- Conclusion: **FAIL**. The three High defects violate Local's required bounded interface, recording
  safe-point, and accepted-CQ contracts. The missing authenticated Claude and uniquely scoped real
  platform execution are independent hard completion-gate blockers. Recommend developer repair,
  restore a working Claude execution login and a proven-owned Local acceptance configuration, then
  reuse this document for a focused Round 2 plus the required real run and cleanup verification.

### Independent test Round 2 — 2026-07-22 — BLOCKED

- Tester: independent requirement tester. This retest reused the same requirement, design, plan,
  implementation scope, and current checkout (`HEAD c5818418f3ee539000e324052915f49fcde4800c`).
  The reconstructed changed/new implementation-only manifest of the 23 `.codex/`, `.claude/`, and
  `skills/` files matched the developer-supplied
  `3f7338da89656956c6f219e42fef79c417bb13296aa806b8fb7245af9035b3d8` exactly.
- FIXED — the Local/Formal full-MCP conflict: `skills/ontology-builder/SKILL.md:47-53` is now an
  explicit `Formal execution only — never follow this section for local` boundary before the former
  full-MCP instructions. The Local path says to stop and use only the Adapter/shared-directory
  contracts. `skills/ontology-builder/evals/validate_skill.py:201-214` requires exactly that
  boundary and rejects unqualified Local `mcp:`/Formal orchestration. The ontology-builder validator
  passed, so the old contradiction is no longer reproduced.
- FIXED — stale Harness health reuse: `.codex/local_modeling_adapter.py:330-353` consumes a
  `harness_run_id` plus operation-ID-matched grant and removes it. `commit_business` (`365`),
  `dry_run_next` (`902`), `apply_next` (`970`), `verify` (`737`), and `finish` (`792`) all consume
  it before platform work. `recording_health` stores one grant at `691-693`; the separate explicit
  `authorize_recording_unavailable` path is also operation-specific and one-use (`702-723`). Focused
  `test_safe_point_grants_are_required_by_each_protected_action_and_single_use` passed, including
  replay and unavailable-authorisation consumption; the Harness one-time receipt test also passed.
- FIXED — CQ approval boundary: `commit_business` now requires `accepted is True` at
  `.codex/local_modeling_adapter.py:369-380`, verifies every `source_brief_fields` member against
  confirmed fields before the first network request, and rejects `business_question_not_accepted` or
  `business_question_source_not_confirmed`. Focused
  `test_cq_acceptance_and_confirmed_sources_are_required_before_any_write` passed. This closes the
  Round 1 omitted-acceptance/unconfirmed-source reproduction.
- Executed PASS evidence: full `.codex` discovery suite completed `101/101`; focused Local Adapter
  completed `15/15` and Harness completed `37/37`; Ruff check/format passed; ontology-builder
  validation/evals passed (`10` references, `34` MCP dependencies, `7` cases); all five current
  Skill quick validations passed; JSON/YAML/frontmatter parsing and tracked secret/diff checks
  passed; service was active and backend `/api/health` plus frontend `/` passed. No backend/frontend
  code path changed, so a restart was not required for this repo-local change.
- BLOCKED hard gates: the project has no `.claude/local-modeling.json`, only its redacted example;
  therefore there is still no proven-owned Project/API-key identity for a safe real Batch/query
  acceptance or cleanup. `claude auth status` still reports `loggedIn: true`/`oauth_token`, and
  `claude agents --setting-sources project` lists all four wrappers, but each real
  `claude -p --setting-sources project --agent <role> --tools ''` marker probe returns exactly
  `Not logged in · Please run /login`. Authenticated Skill preload, direct clarification return,
  real Hook receipt from a Claude Session, the two-work-unit multi-round Local run, secret-sentinel
  scan against a configured credential, real protected Batch/query/retrieval/provenance validation,
  and owned-data cleanup remain unexecuted. Static/mock success is not substituted for these gates.
- Cleanup: no Project, Ontology, Build Session, Batch, RDF graph, Harness run, config, or product
  data was created by this round; cleanup was therefore not needed. This tester changed only this
  shared test-plan file.
- Conclusion: **BLOCKED**, not PASS. Round 1 High defects are fixed and their affected regressions
  pass, but R1.1-007 completion gates still require authenticated Claude execution and a uniquely
  owned Local platform acceptance run. Restore both prerequisites, then run a Round 3 using this
  plan; do not treat the current static/listing evidence as satisfying them.

### Independent test Round 3 — 2026-07-22 — FAIL

- Tester: independent requirement tester. This retest reused the same requirement, design, and
  plan at `HEAD c5818418f3ee539000e324052915f49fcde4800c`; the supplied implementation manifest
  remained `3f7338da89656956c6f219e42fef79c417bb13296aa806b8fb7245af9035b3d8`. The tester changed
  only this append-only plan and uniquely owned gitignored evidence below
  `workspaces/modeling-runs/r11007-live-round3-20260722T014732Z/` plus its two bounded local
  planning JSON files. No product source, main documentation, configuration, Project, Ontology,
  or pre-existing harness data was edited or deleted.
- Real acceptance identity supplied by the main agent: Project
  `b668f613-5767-4149-92ee-e4dd74e16a43`, ready Ontology
  `84e61f82-54a4-4ee7-89cc-fe2edd566e5c`, and ignored owner-only Adapter configuration. The
  configuration was mode `0600`; the round-specific Adapter ledger was also mode `0600` and
  contained only `schema_version`, Build Session/revision, and attempt identities (no credential
  or Lease token).
- Executed real-platform PASS evidence: initialized and validated the shared Local run
  `r11007-live-round3-20260722T014732Z`; Adapter `start` created active Build Session
  `22437377-d181-4ce1-89ed-0599b96a5b61`; the one-use explicit
  `recording-unavailable` authorization was consumed for `commit_business`; and the accepted,
  confirmed-source CQ was created and approved as
  `c5972dfa-4551-4ac8-9f6c-a70c31c349b5`. The run has two distinct bounded Work Units
  (`r11007-workflow-schema`, `r11007-workflow-instance`) over the fixed Dify foundations README
  and one accepted local CQ. `shared_modeling_directory.py validate`, `merge`, independent PASS
  review, and `plan` all passed. The candidate hash was
  `9c49b132f36d39cb8c77c2edd266d67ec41a23452d7b090c73e96fd1a003d404`; planning used the live
  four limits (100 items, 1,048,576 request bytes, 100 inline Evidence, 20,000 excerpt chars) and
  produced one two-Item Batch. The test uses only supported `create_class` and `create_entity`
  items and the fixed source excerpt that explicitly covers Workflow and Chatflow.
- **High — accepted Local CQ bindings are not substituted into submitted Modeling Items.** After
  `commit_business` bound local CQ `cq-r11007-dify-workflow-fixture` to real platform CQ
  `c5972dfa-4551-4ac8-9f6c-a70c31c349b5`, Adapter `dry-run-next` created real Batch
  `800d9898-9831-44ca-834f-d26233ef2716` and dry-run Attempt
  `1928f129-fce5-49e1-8713-3906f063f012`, but returned two blocking
  `competency_question_not_found` Findings. Both Item payloads sent the local ID, which does not
  exist as a Project CQ. Read-only Batch detail confirms both Items `failed` and the Attempt status
  is `validation_failed`; no apply was submitted. Reproduce: initialize a Local run with a local
  CQ ID, run `recording-unavailable --operation-id <commit>` then `commit-business`, build/merge
  reviewed Items that retain that local ID, plan, authorize the dry-run safe point, and run
  `dry-run-next`. Expected: `bind_platform_competency_questions` keeps local IDs stable in
  Shared-Directory contracts while the Adapter materializes their bound platform IDs before
  `/build-sessions/{id}/modeling-batches`, as promised by its own docstring and test-plan section
  D. Actual: `commit_business` records the binding, but `dry_run_next` sends
  `materialized["items"]` unchanged through `_request_for_batch`; neither
  `.codex/shared_modeling_directory.py` nor `.codex/local_modeling_adapter.py` maps
  `competency_question_ids` at submission. This prevents every evidence-backed Item that refers to
  a freshly committed local CQ from passing real dry-run.
- Required non-claims/unexecuted scope: because that real protocol defect produced a material
  Finding, this tester stopped before `apply_atomic`, Lease acquisition, real resource creation,
  Evidence Association/edit-audit/revision inspection, CQ execution, retrieval/provenance,
  `verification.json`, Adapter `verify`, or `finish`. The active Session and failed Batch remain
  recoverable for diagnosis; the Project/Ontology were intentionally retained for the later Claude
  run. Read-only Session evidence confirms one modeling Batch, zero Leases, zero Checkpoints,
  `artifact_version_count=0`, `event_count=0`, and zero Evidence references, so this round did not
  explicitly create Artifact/Event/Checkpoint and did not falsely claim applied evidence/audit
  facts.
- Claude hard gate remains independently BLOCKED: exactly one corrected probe,
  `printf '%s' 'Return only the single word READY.' | claude -p --setting-sources project --agent
  ontology-business-organizer --tools ''`, returned `Not logged in · Please run /login`.
  Therefore this is an Adapter-only real platform protocol check, not the required authenticated
  single-main-Claude run, Skill-preload proof, clarification handoff, or Hook-receipt flow.
- Secret evidence: the configured key was compared in memory without printing it. It appears zero
  times in this round's Adapter ledger/run/shared files and zero times in tracked or staged diff.
  It was found once in pre-existing, unrelated, mode-`0600`
  `workspaces/ontology-harness/harness-eval-admin.json` (dated before this round); that file was
  neither read into output, changed, nor deleted. The supplied credential was not replaced with a
  unique sentinel, so the strict configured-sentinel case is **not executed**. A separate unused
  round sentinel scan returned zero occurrences. This pre-existing duplicate and the unavailable
  Claude gate mean the secret hard gate cannot be counted as PASS.
- Conclusion: **FAIL**. The real protected dry-run reached the platform and exposed a High
  Local-CQ-to-platform-CQ submission defect. Recommend the requirement developer repair the
  materialization/submission mapping and add a focused regression that exercises a newly bound CQ
  through real/mock Batch request construction; then reuse this same plan for Round 4, first
  re-running the failed dry-run and only then the affected apply/verification/retrieval/provenance
  checks. Restore Claude execution login before treating any later run as the R1.1-007 full Local
  acceptance gate.

### Independent test Round 4 — 2026-07-22 — FAIL

- Tester: independent requirement tester. Retested the developer-supplied implementation manifest
  `c686dd1e6cc0b8de710e28ac78b579c4f81a7eb0b2d5db857a6d636608a16bf8` on the same checkout HEAD
  (`c5818418f3ee539000e324052915f49fcde4800c`). The tester appended only this plan and created
  uniquely owned ignored Round 4 spec/business/limit/attempt/run evidence under `workspaces/`.
  The retained Round 3 Session `22437377-d181-4ce1-89ed-0599b96a5b61`, Batch
  `800d9898-9831-44ca-834f-d26233ef2716`, and Attempt
  `1928f129-fce5-49e1-8713-3906f063f012` were not modified.
- Focused regression PASS: discovery tests
  `test_shared_modeling_directory.py` (`16/16`) and `test_local_modeling_adapter.py` (`15/15`)
  passed. This includes `test_local_cq_binding_projects_platform_ids_through_task_candidate_and_batch`.
  A new real Local run `r11007-live-round4-20260722T020100Z` was initialized under the supplied
  Project/Ontology. Adapter `start` created Build Session
  `d2313104-1201-4b04-aeac-d57d7cbd4442`; accepted business commit created and bound platform CQ
  `106a1420-3fa0-4b8d-8cf3-d524a3795a47` from local alias
  `cq-r11007-round4-workflow-fixture` before any Work Unit result existed. Read-only evidence
  proves both Coverage items and both pending tasks were projected to that platform ID. Two
  bounded Work Units, results, independent PASS review, candidate
  `c5d8b9d2118eb53aa268ca2aef976db9d18b4ee050e39ce81f5ab9661b7aa99d`, and exact-live-limit plan
  all passed.
- FIXED — Round 3 Local-CQ submission defect. The new materialized two-Item request contains
  platform CQ `106a1420-3fa0-4b8d-8cf3-d524a3795a47` and contains no
  `cq-r11007-round4-workflow-fixture` string. The local alias remains only in the traceable
  Coverage CQ metadata, not in Coverage-item references, pending tasks, results, candidate, or
  materialized Batch. This proves the new pre-modeling projection is effective and does not use a
  post-review candidate rewrite.
- **High — real protected modeling path is disabled by active platform runtime configuration.** A
  fresh one-use `recording-unavailable` authorization was consumed for real `dry-run-next`; it
  created Batch `f2f7e39b-c2a7-465e-9cc1-017a5b1b0359` and dry-run Attempt
  `e4acb9c8-c3fc-4ec0-a63f-4bdc990e8797`, but the platform returned one blocking
  `candidate_validation_failed` Finding: `Canonical writer is not enabled in this mode;
  SEMANTIC_PRODUCT_WRITE_MODE=legacy_only`. Batch detail reports `batch_status=open` and
  `attempt_status=validation_failed`. Reproduce: start a Local Adapter run against the supplied
  ready Ontology, complete accepted business commit/CQ projection, submit a review-approved,
  capacity-valid `create_class`/`create_entity` dry-run using the current service configuration.
  Expected: the required canonical Modeling Batch dry-run validates and can proceed to its
  guarded `apply_atomic`. Actual: the configured live platform rejects every such candidate before
  semantic validation. This is a runtime/product acceptance defect, not a local-CQ mapping
  regression.
- Required stop/unexecuted scope: per the blocking real Finding, no apply/Lease, resource creation,
  Evidence Association, audit/revision inspection, CQ execution, retrieval/provenance,
  `verification.json`, Adapter `verify`, or `finish` was attempted. Session and failed Batch remain
  recoverable; Project/Ontology are retained for the final Claude run. The round did not create or
  claim Artifact/Event/Checkpoint. The strict unique-configured-sentinel case remains unexecuted
  because the supplied credential was not replaced; an in-memory scan found the configured key
  zero times in all Round 4 run files and zero times in tracked/staged diff.
- Claude hard gate is also still BLOCKED: the one corrected probe
  `printf '%s' 'Return only the single word READY.' | claude -p --setting-sources project --agent
  ontology-business-organizer --tools ''` returned `Not logged in · Please run /login`.
- Scope/integrity evidence: `git diff --check` passed; Round 4 run/spec evidence is ignored by the
  workspace rule. No product code, documentation other than this plan, retained Round 3 evidence,
  shared Project configuration, or platform cleanup target was modified.
- Conclusion: **FAIL**, not Claude-only BLOCKED. The original CQ-mapping defect is fixed, but the
  active service's `legacy_only` writer mode makes the required real dry-run/apply path impossible.
  Recommend restoring the owned acceptance runtime to canonical writer mode, then reuse this plan
  for Round 5: re-run the current Batch only if the platform's intended recovery contract permits;
  otherwise create a new uniquely owned Batch identity, then complete apply, verification,
  retrieval/provenance, audit/revision, finish, and cleanup checks. Restore Claude login before
  treating that later run as full R1.1-007 Local acceptance.

### Independent test Round 5 — 2026-07-22 — FAIL

- Tester: independent requirement tester. Reused the developer-supplied unchanged implementation
  manifest `c686dd1e6cc0b8de710e28ac78b579c4f81a7eb0b2d5db857a6d636608a16bf8` after the main agent
  restored the owned service's canonical writer mode. The tester appended only this plan and added
  uniquely owned ignored Round 5 spec/business/limit/attempt/run evidence under `workspaces/`.
  Rounds 3 and 4 Sessions/Batches/Attempts were left immutable.
- Runtime precondition PASS: `ontology-platform.service` was active; backend health returned
  `{"status":"ok"}` and frontend returned HTTP `200`. New Run
  `r11007-live-round5-20260722T021500Z` started Build Session
  `e3536f8a-ea94-415e-9235-3381ba6353cc`. Accepted confirmed-source business commit created/bound
  CQ `e62fd16a-1806-45c2-baea-b79d93f59a60` and projected it from local alias
  `cq-r11007-round5-workflow-fixture` into both Coverage items, both pending tasks, both results,
  candidate, and materialized request before modeling. Two bounded Work Units used exact inline
  Dify README Evidence; shared validation/merge, independent PASS review, and exact-live-limit
  plan all passed. Candidate hash:
  `8764441eea6b2686924896b05c76a25a8fb9f69483afdf5c5387500a21aa575e`.
- Real protected Batch PASS: dry-run and `apply_atomic` used one immutable Batch
  `b69603e8-c6c4-4250-a094-ad9539cf808f` / immutable hash
  `e2b90a43e03b4851bdfc816a8a0035ef376db52d9c1fa9669b60cdf8121aea11`. Dry-run Attempt
  `8cfbdd06-6dfc-4e70-8f60-52f637d3efa0` is `validated`; apply Attempt
  `ca000144-a901-4c95-ac64-03170fec6213` is `applied`; Batch is `applied` and plan context refresh
  is true. This proves the Round 4 `legacy_only` runtime blocker was removed and the fixed CQ
  projection works through a real canonical apply.
- Real persisted-state PASS evidence: entity-list retrieval returned
  `R11007Round5DifyWorkflowFixture`; IRI-based resource lineage returned
  `lineage_status=complete`, `evidence_status=supported`, and five lineage items. Evidence reference
  `75cef57a-4555-560d-bda4-0e2a407b73b4` has two Modeling-Item associations
  (`46fd3ff4-86af-53de-ab55-bc92fd033a48` and
  `2e5503d8-d6e8-59a7-a970-e746819358b3`). The latest semantic edit audit
  `0e91c0d7-8fc4-562b-8ee7-9ceba2cf1133` is applied, includes the Ontology graph/data graph delta,
  and records validation/revision facts. Static `verification.json` validation passed with the exact
  Batch/content binding and structured retrieval/provenance/Evidence observations. No Workflow
  Artifact/Event/Checkpoint was explicitly created (`artifact_version_count=0`, `event_count=0`,
  `checkpoint_count=0`).
- **High — supported entity-count CQ validation crashes after a successful canonical apply.** Fresh
  one-use verify authorization moved CQ `e62fd16a-1806-45c2-baea-b79d93f59a60` from `approved` to
  `testable`, then Adapter `verify` returned `platform_http_500`; the CQ remains `testable`.
  Service evidence shows `POST /api/competency-questions/{id}/validate` called
  `run_question_validation -> run_select_count`, Oxigraph `/query` returned HTTP `400`, and the
  uncaught error is `app.repositories.rdf_store.SparqlSyntaxFailure: error at 1:243: expected
  OPTIONAL`. Reproduce: apply the two supported Items above under `rdf_primary`, use the supported
  CQ definition `{"kind":"entity_count","class_id":"r11007-round5-dify-workflow-class",
  "min_count":1}`, transition the bound CQ to testable, then invoke its validate endpoint.
  Expected: return an executed `passed` or `failed` CQ result for the supported query definition.
  Actual: returns HTTP 500 after the applied model is visible through retrieval and lineage. This
  prevents Adapter verification and violates the real CQ hard gate.
- Query/format evidence: the exact persisted structured definition was
  `{"kind":"entity_count","class_id":"r11007-round5-dify-workflow-class","min_count":1}`;
  `entity_count` is an explicitly documented supported kind in
  `backend/app/services/interview.py:351-359` and is generated at lines `379-391` as a
  `SELECT (COUNT(DISTINCT ?e) AS ?count) ... GRAPH ?g ... rdf:type/rdfs:subClassOf*` query. The
  graph-scoping wrapper in `backend/app/services/semantic_sparql_runner.py:45-58` embeds that
  complete `SELECT` directly after `VALUES ?g` within another `SELECT ... WHERE { ... }`, before
  `rdf_store.query_sparql` at `backend/app/repositories/rdf_store.py:156-171`. The bounded Adapter
  deliberately does not print raw query/response text; the locatable service log at
  `2026-07-22 10:16:24` records the Oxigraph HTTP `400` and the above syntax error. This makes the
  failure reproducible without exposing request diagnostics or credentials.
- Required stop/unexecuted scope: after that product defect, this tester did not retry validation,
  alter the CQ/query, invoke Adapter finish, cancel the active Session, or delete any owned Project
  data. Thus no run-wide completion or cleanup is claimed. The session currently has one Batch and
  one recorded Lease entry; its session summary still has zero Artifact/Event/Checkpoint. A bare
  legacy resource ID supplied to the lineage endpoint separately returned HTTP 500 because the API
  requires an RDF IRI; the IRI form above is the successful provenance evidence and is the only
  form asserted by this round.
- Claude and secret scope: the one corrected Claude probe still returned `Not logged in · Please run
  /login`. In-memory configured-key scans found zero occurrences in all Round 5 run files and zero
  in tracked/staged diff; `git diff --check` passed and Round 5 workspace evidence is ignored. The
  supplied credential was not replaced with a unique sentinel, so that strict configured-sentinel
  case remains unexecuted.
- Conclusion: **FAIL**, not Claude-only BLOCKED. The full protected modeling, apply, retrieval,
  Evidence, lineage, audit, and revision path now works, but the required platform CQ execution
  crashes for the supported `entity_count` definition. Recommend the requirement developer repair
  the generated SPARQL/query-runner compatibility error and add a live/integration regression for
  validated entity-count CQs under the canonical writer. Then reuse this plan for Round 6, first
  revalidating this exact applied CQ before Adapter verify/finish and final cleanup; restore Claude
  login before treating that round as full Local acceptance.

### Independent test Round 6 — 2026-07-22 — FAIL

- Tester: independent requirement tester. Retested stable manifest
  `84bc0489669ee8bdacfca688ee3dc605bbc80fbfea4b3157471eb9be7a25a3e2` at supplied HEAD
  `c5818418f3ee539000e324052915f49fcde4800c`. Only this plan and retained ignored Round 5 evidence
  were written; no Round 3/4 failure evidence, product source, main documentation, or runtime
  configuration was changed. Service/runtime health passed: unit active, backend health OK, and
  frontend HTTP `200`.
- Affected regression PASS: with `RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1`,
  `cd backend && uv run pytest tests/test_semantic_sparql_runner.py tests/test_interview_service.py
  -q` passed `32/32`, including real Oxigraph query shapes. Ruff check passed for the changed runner
  and affected tests. Ruff format check reported one existing delivery defect:
  `tests/test_interview_service.py` would be reformatted; the tester did not modify it.
- Independently assessed unrelated known test result: combined affected suite had one failure,
  `test_mcp_startup_requires_environment_key`, while the other `36` tests passed and one skipped.
  This is environment/test-isolation behavior, not evidence against this SPARQL patch: process
  environment lacked `ONTOLOGY_MCP_API_KEY`, but `Settings()` still loaded a non-empty key from its
  configured `.env` file. The test only clears process environment and the implementation under
  test was not changed in this manifest.
- Retained Adapter-flow execution: no CQ state was changed outside the Adapter. The existing applied
  Round 5 Batch `b69603e8-c6c4-4250-a094-ad9539cf808f` and structured verification file were
  reused. A fresh one-use unavailable-recording authorization for operation
  `r11007-round6-verify` was consumed; Adapter `verify` returned `ok` / `next_action=finish` after
  invoking CQ `e62fd16a-1806-45c2-baea-b79d93f59a60` validation. Finish was deliberately **not**
  authorized or invoked after the observed failed CQ result below.
- **High — the repaired parser no longer throws, but the supported entity-count CQ still gives a
  false negative, and Adapter verify accepts it as success.** The exact platform result is
  `status=failed`, `validation_result={"kind":"entity_count","matches":0,"expected_min":1,
  "passed":false}`; CQ is now terminal `failed`. This contradicts the already applied and
  independently retrieved/lineage-supported Round 5 fixture. Nonetheless Adapter `verify` accepts
  either `passed` or `failed` platform statuses and validates only the pre-existing local
  `verification.json`, so it returned `ok` despite the live CQ failure. Expected: a failed required
  CQ causes verification to be non-PASS and blocks finish. Actual: it advertises finish eligibility.
- Read-only localization/evidence for the false negative (no secret): active CQ graph IRIs are
  `http://ontology-platform.local/semantic/graph/ontology/84e61f82-54a4-4ee7-89cc-fe2edd566e5c`
  and `http://ontology-platform.local/semantic/graph/data/84e61f82-54a4-4ee7-89cc-fe2edd566e5c`.
  `resolve_class_iri` resolves requested class ID `r11007-round5-dify-workflow-class` to fallback
  `http://ontology-platform.local/semantic/ontology/84e61f82-54a4-4ee7-89cc-fe2edd566e5c/class/r11007-round5-dify-workflow-class`.
  The applied fixture is in the active data graph and has actual RDF types
  `owl:NamedIndividual` and
  `http://ontology-platform.local/semantic/class/r11007-round5-dify-workflow-class`; it is a real
  instance of the canonical applied class, but not of the fallback IRI that the CQ resolves. The
  generated scoped count query uses `FROM`/`FROM NAMED` over those two graphs and targets that
  fallback IRI; in direct read-only execution its unprefixed `rdf:type/rdfs:subClassOf*` form also
  produces `SparqlSyntaxFailure` (`Prefix not found`). Therefore this fixture is truly created, but
  the CQ class-resolution/query-generation path does not test the created class.
- Platform state preserved: Session `e3536f8a-ea94-415e-9235-3381ba6353cc` remains active; Round 5
  Batch and both validated/applied Attempts remain unchanged; no finish/cancel/delete was performed.
  The historical applied resource, Evidence associations, audit/revision, and zero
  Artifact/Event/Checkpoint evidence remain as recorded in Round 5. Corrected Claude probe still
  returned `Not logged in · Please run /login`; in-memory configured-key scan remained zero for
  Round 5 evidence and diff. `git diff --check` passed.
- Conclusion: **FAIL**, not Claude-only BLOCKED. Before final Local acceptance, repair both
  canonical class-ID-to-IRI resolution (and the generated query's RDF prefix handling) and Adapter
  verification's requirement to reject observed failed CQs. Reuse the retained applied CQ only if
  its state-transition/revalidation contract permits; otherwise create a new uniquely owned CQ in
  the next round. Do not finish the current run as passing.

### Independent test Round 7 — 2026-07-22 — TEST_FAIL

- Tester: independent requirement tester. This round reused only the retained Round 5 Project,
  Ontology, Run, Build Session, CQ, Batch, and structured verification evidence. It appended only
  this test plan; it did not alter product code, requirement/design/delivery documents, runtime
  configuration, Round 3/4 failures, or retained Project data. Runtime health passed
  (`ontology-platform.service` active, backend health OK, frontend HTTP `200`).
- PASS — failed-CQ recovery is now fail-closed before it can overwrite local verification. With
  fresh one-use authorization `r11007-round7-verify-guard`, retained failed CQ
  `e62fd16a-1806-45c2-baea-b79d93f59a60` made Adapter `verify` return
  `status=blocked`, `error_code=competency_question_failed`, and next action
  `recording-health-and-retry-verify`. The existing `verification.json` SHA-256
  `45afa8399daefa997c19bf3aad864d1ae150c8f95e3433480c0b042f816554af` and mtime
  `1784687781` were identical before and after this guard, proving no local verification write.
- PASS — exact retained CQ recovery. A new one-use authorization
  `r11007-round7-verify-recovery` used the same Adapter `verify` route, transitioned the CQ
  `failed -> testable -> passed`, and returned `ok` / `next_action=finish`. The persisted supported
  definition remains `{"kind":"entity_count","class_id":"r11007-round5-dify-workflow-class",
  "min_count":1}`; platform result is `matches=1`, `expected_min=1`, `passed=true`, timestamp
  `2026-07-22T02:51:00.312647+00:00`. Local `validate-verification` then passed with the exact
  applied Batch/content hash and structured real retrieval/lineage/Evidence observations.
- **High — retained Local run cannot complete after successful CQ recovery because the Adapter
  requires a Harness binding that its explicit recording-unavailable path never creates.** Fresh
  finish authorization `r11007-round7-finish` was consumed and Adapter `finish` returned blocked
  `harness_binding_required`; no Session completion was submitted. This run's original documented
  `local_modeling_adapter.py ... start <run>` returned Build Session
  `e3536f8a-ea94-415e-9235-3381ba6353cc` and next action `activate-harness`, but the prior
  Adapter-only continuity flow used authorized `recording-unavailable` because Claude was
  unavailable. Retained `run.json` has only
  `local_execution.build_session_id`, no `harness_run_id`; its Adapter ledger has only session and
  Batch attempt identities; `workspaces/ontology-harness` has no Round 5 run. The tester did not
  hand-write a Harness ID, invoke finish again, cancel, or change the run. Expected: an explicit
  recording-unavailable Local run can either finish as incomplete-process or offer a supported
  recoverable completion path after model acceptance. Actual: it reaches validated/apply/CQ PASS
  but is terminally blocked at finish solely by a missing Harness never created in that permitted
  path. Session remains `active`.
- Retained platform-state regression PASS: Batch
  `b69603e8-c6c4-4250-a094-ad9539cf808f` remains `applied`; Attempts
  `8cfbdd06-6dfc-4e70-8f60-52f637d3efa0`/`ca000144-a901-4c95-ac64-03170fec6213` remain
  `validated`/`applied`; two Batch Items and two Evidence associations remain. Applied audit
  `0e91c0d7-8fc4-562b-8ee7-9ceba2cf1133` records two affected graphs and validation facts. Session
  still has `artifact_version_count=0`, `event_count=0`, and `checkpoint_count=0`; no Artifact,
  Event, or Checkpoint is claimed. One Lease record remains visible and is not modified by this
  tester.
- Automated checks: real-Oxigraph affected runner/interview suite passed `32/32`. Full backend
  regression with `RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1` was stopped by the first unrelated failure:
  `tests/test_build_session_mcp.py::test_new_and_compatibility_build_context_tools_return_same_shape`
  compares two independently generated `generated_at` timestamps one second apart. Its failure is
  unrelated to R1.1-007 changes. The known `test_mcp_startup_requires_environment_key` isolation
  failure is also independent: the process environment has no key but `Settings()` loads one from
  `.env`. Ruff check passed for runner/interview/scoped-query and relevant tests; Ruff format check
  reports `app/services/scoped_sparql_query.py` would be reformatted. `git diff --check` passed.
- Claude is a separate external blocker: all four minimal real calls (business organizer,
  work-unit modeler, model reviewer, retrieval evaluator) returned `Not logged in · Please run
  /login`. Configured-key scan found zero matches in retained Round 5 evidence and tracked/staged
  diff; the credential was not printed.
- Conclusion: **TEST_FAIL**. The platform modeling/CQ/retrieval/evidence/audit path now passes,
  and Claude login is independently unavailable, but platform acceptance cannot be marked PASS or
  Claude-only BLOCKED because the required retained run completion is blocked by the missing-Harness
  recovery gap. Add a supported incomplete-recording completion/recovery path (or require and
  provision a real Harness before any permitted Local write), then repeat only fresh finish
  authorization against this retained completed-verification run before final Claude acceptance.

### Independent test Round 8 — 2026-07-22 — TEST_FAIL

- Tester: independent requirement tester. Product implementation was treated as frozen; this round
  appended only this shared plan and used the retained ignored Run/Session/CQ/verification state.
  No Project cleanup, writer-mode restore, commit, product-code edit, main-document edit, or
  synthetic Harness state was made. Runtime remained healthy: service active, backend health OK,
  frontend HTTP `200`.
- PASS — isolated old-marker/no-fresh-grant safety. The Adapter suite now passes `21/21`, including
  `test_finish_requires_current_safe_point_when_harness_is_unbound` and
  `test_finish_allows_current_recording_unavailable_without_harness_and_is_idempotent`; together
  they prove an unbound Harness cannot use no/old authorization and that only a current
  operation-matched unavailable authorization opens the incomplete-recording branch. This evidence
  is isolated and did not perturb retained Run state.
- PASS — real retained completion. A fresh exactly-once authorization with operation
  `r11007-round8-finish` was consumed, then Adapter `finish` returned `status=ok`, finding
  `[{"code":"recording_unavailable"}]`, `next_action=done-recording-incomplete`, and references
  containing only Build Session `e3536f8a-ea94-415e-9235-3381ba6353cc` (no `harness_run_id`). The
  Session now reports `status=completed` and completion summary `Local modeling verification
  passed; recording unavailable`. Retained `run.json` remains bound only to that Build Session,
  ledger contains the recording-unavailable marker/terminal state, and no matching Harness path was
  created under `workspaces/ontology-harness`; therefore no Harness run, summary, or `finalize` call
  was fabricated by this completion route.
- PASS — final semantic acceptance evidence remains intact: CQ
  `e62fd16a-1806-45c2-baea-b79d93f59a60` is `passed` with the supported entity-count result
  `matches=1 >= expected_min=1`; local structured verification validates PASS. Batch
  `b69603e8-c6c4-4250-a094-ad9539cf808f` remains applied, with dry-run/apply Attempts
  `8cfbdd06-6dfc-4e70-8f60-52f637d3efa0`/`ca000144-a901-4c95-ac64-03170fec6213` validated/applied.
  Retrieval still returns the Round 5 fixture; IRI lineage is complete/supported with five items;
  Evidence reference `75cef57a-4555-560d-bda4-0e2a407b73b4` retains two Modeling-Item
  associations; audit `0e91c0d7-8fc4-562b-8ee7-9ceba2cf1133` is applied with two affected graphs
  and validation facts. Session summary still reports Artifact/Event/Checkpoint all zero.
- Automated evidence: all `.codex` tests passed `109/109`; affected real-Oxigraph runner/interview
  suite passed `35/35`; affected Ruff check passed. `git diff --check` and configured-key scans
  passed (zero key matches in retained run and tracked/staged diff). Full backend regression remains
  non-green because its first failure is the unrelated timestamp race in
  `test_new_and_compatibility_build_context_tools_return_same_shape`; the known MCP-startup test
  continues to load `.env` after environment deletion. **A deterministic affected formatting gate
  also still fails:** `ruff format --check` reports
  `app/services/scoped_sparql_query.py` would be reformatted. No automatic formatting was applied
  because this tester may not edit product code.
- Claude is the sole external runtime blocker: all four minimal real role probes again returned
  `Not logged in · Please run /login`. This blocks authenticated Skill preload, Claude main-session,
  Hook receipt, and final full-Local run, but not the completed retained platform acceptance path.
- Conclusion: platform functional acceptance is **PASS** and the prior recovery/finish defect is
  fixed. Overall result is **TEST_FAIL** rather than Claude-only `TEST_BLOCKED`, because the changed
  affected source still fails the required deterministic Ruff format check. After the developer
  formats that one file and reruns the affected checks, the only remaining requirement blocker is
  external Claude authentication; at that point the overall result should be `TEST_BLOCKED` pending
  the final authenticated Claude run.

### Independent test Round 9 — 2026-07-22 — TEST_BLOCKED

- Tester: independent requirement tester. This was a read-only closure retest against current HEAD
  `3a13fbf0b5369d8ecdaf80fef4708a8767100637`; only this plan was appended. No retained Project,
  writer-mode, platform data, product source, requirements/design/delivery document, or commit was
  changed. Service health passed: active unit, backend health OK, frontend HTTP `200`.
- PASS — the former deterministic formatting gate is closed without semantic regression. Affected
  Ruff check passed and `ruff format --check` reports all five affected runner/interview/scoped
  query/test files already formatted. The real-Oxigraph runner/interview suite passed `35/35`; full
  `.codex` discovery passed `109/109`; `git diff --check` passed. The previously reported full
  backend timestamp-race/MCP dotenv-isolation cases were not reclassified as R1.1-007 code failures.
- PASS — retained completed platform state, read-only: Session
  `e3536f8a-ea94-415e-9235-3381ba6353cc` is `completed` with explicit
  `recording unavailable` completion summary; CQ
  `e62fd16a-1806-45c2-baea-b79d93f59a60` is `passed` with `matches=1`; Batch
  `b69603e8-c6c4-4250-a094-ad9539cf808f` is applied with validated/applied Attempts and two Items.
  Retrieval returns `R11007Round5DifyWorkflowFixture`; lineage is complete/supported with five
  items; Evidence reference has two associations; applied audit
  `0e91c0d7-8fc4-562b-8ee7-9ceba2cf1133` retains validation facts. Artifact/Event/Checkpoint counts
  remain zero. Configured-key scans found zero matches in retained run evidence and tracked/staged
  diff.
- BLOCKED — the only remaining requirement gate is external Claude authentication. Each minimal
  real probe for `ontology-business-organizer`, `ontology-work-unit-modeler`,
  `ontology-model-reviewer`, and `ontology-retrieval-evaluator` returned exactly
  `Not logged in · Please run /login`. Thus authenticated Skill preload, a real Claude main Session,
  Hook receipt, worker clarification return, and the required final authenticated full-Local run
  cannot be honestly claimed from static or Adapter evidence.
- Conclusion: **TEST_BLOCKED**. All implemented code and retained real platform acceptance checks
  now pass; only Claude CLI authentication blocks final R1.1-007 closure. After login is restored,
  the minimum revalidation is one authenticated single-main Local run exercising the four role
  Skills and fresh Harness receipt, then verify its bounded Adapter dry-run/apply/CQ/retrieval path
  and completion. Keep the retained Project/data until that run is complete.

### Independent test Round 10 — 2026-07-22 — TEST_BLOCKED

- Tester: independent requirement tester. This round corrected the earlier Claude probe's settings
  source: `--setting-sources user,project` was used so user-level cc-switch Provider settings are
  not excluded. Only this test plan was appended; no new Project Run/Session/Batch, product code,
  requirement/design/delivery document, writer mode, or retained data was changed.
- Authentication/configuration PASS: `claude auth status` reports `loggedIn: true`,
  `authMethod: oauth_token`, and `apiProvider: firstParty`; `claude agents --setting-sources
  user,project` lists all four project roles (`ontology-business-organizer`,
  `ontology-work-unit-modeler`, `ontology-model-reviewer`, and
  `ontology-retrieval-evaluator`). No token, endpoint, model name, or credential content was
  printed or persisted.
- BLOCKED — corrected real Provider invocation does not return. The first real minimal Organizer
  call used stdin prompt `Read your preloaded project Skill instructions. Reply with exactly:
  ORGANIZER_SKILL_READY`, `--setting-sources user,project`, `--agent
  ontology-business-organizer`, empty tool surface, and a 180-second Provider timeout. It produced
  no stdout, stderr, marker, or structured error before timing out. A second same-config Modeler
  call had begun but was intentionally terminated after the Organizer's definitive 180-second
  silent timeout, rather than serially spending another three 180-second waits against the same
  global Provider path. Therefore none of the four Skill preload markers, role tool boundaries, or
  authenticated Claude handoffs can be honestly claimed; no Claude-controlled platform action was
  attempted.
- Classification: this is a **Provider reachability/response blocker**, not the prior false
  `Not logged in` diagnosis. Login and project-agent discovery both succeed under the corrected
  sources, while the actual Provider request fails only by silent timeout. The retained completed
  platform acceptance from Round 9 remains valid and untouched.
- Conclusion: **TEST_BLOCKED**. The only blocker is the external Provider's non-response under the
  correctly configured user+project source set. After Provider service returns, minimally rerun all
  four marker probes, then execute one new uniquely owned authenticated single-main Local run with
  Harness activation/receipt, four role handoffs, Adapter dry-run/apply/CQ/retrieval, and completion.

### Independent test Round 11 — 2026-07-22 — TEST_FAIL

- Tester: independent requirement tester. This round used the required `user,project` setting
  sources and a live Provider that now responds. It appended only this plan; test-only ignored
  bootstrap/evidence files were created under `workspaces/` for the new run. No product source,
  requirement/design/delivery record, runtime configuration, retained Round 5 data, writer mode,
  or commit was changed. The workspace was already dirty with developer-owned R1.1-007 changes;
  `git diff --check` passed.
- PASS — all four real project Agents returned bounded preload/authority markers using actual
  `claude -p --setting-sources user,project --agent <role> --tools ''` calls: Organizer
  `ORGANIZER_SKILL_READY | responsibility=brief_coverage_cq | platform_write=none`; Modeler
  `MODELER_SKILL_READY | responsibility=assigned_result_only | platform_write=none`; Reviewer
  `REVIEWER_SKILL_READY | responsibility=candidate_review_only | platform_write=none`; Retriever
  `RETRIEVER_SKILL_READY | responsibility=structured_verification_only | platform_write=none`.
  This proves real Provider response, project Skill preload, distinct role responsibility, and no
  direct normal-role platform write surface. No model token or credential was printed.
- Setup PASS — an initial malformed tester bootstrap was rejected locally before any platform
  action with `at least one Work Unit and Ontology are required`; it was corrected to the existing
  declared Shared Modeling Directory shape. The newly initialized uniquely identifiable Local run
  is `r11007-live-round11-20260722T032400Z` and Adapter `start` created active Build Session
  `3f75a472-aedc-43d4-b7f2-1b38741db2df`, returning `next_action=activate-harness`.
- **High — fresh Harness activation cannot work in the documented real Claude invocation.** Two
  independent real single-main calls, including a second call with `--permission-mode
  bypassPermissions --debug hooks`, used the literal documented Local activation form with the
  new Run/Session/Project IDs, `--runtime claude`, `--execution-profile local`, and the required
  `--setting-sources user,project`. Both ran the Bash command but returned exit code `2`:
  `modeling Harness error: this session is not being recorded: activation Hook did not acknowledge`.
  The debug evidence shows the client loading project Skills but, immediately around the Bash tool,
  `Hooks: Found 0 total hooks in registry`; it later reports only the user-level Stop matcher.
  Repository `.claude/settings.json` does contain the required `PreToolUse` matcher
  `Bash|Agent|Task`, so the observed user+project settings merge/invocation does not install the
  project Hook that the documented activation requires.
- Expected: a real Claude main session launched with the documented `user,project` configuration
  invokes project `PreToolUse`, acknowledges activation, creates a fresh receipt, and permits
  Adapter `recording-health` before business commit. Actual: no Harness metadata exists for the
  Run, `modeling_harness.py status` has no `metadata.json`, and Adapter `status` is correctly
  fail-closed with `status=blocked`, `error_code=recording_health_required`,
  `next_action=activate-harness`. This prevented business CQ commit, structured candidate/schema,
  four bounded runtime handoffs, independent review, dry-run/apply, CQ/retrieval/provenance
  verification, and finish; none is counted as passed or executed.
- Platform containment PASS: the new Session remains `active` at revision `1`, with no summary,
  and its modeling-batch list has count `0`. The new run contains only bootstrap/brief/coverage/
  source-index and pending task/status files; there is no Harness directory/receipt. Therefore no
  candidate, Batch, CQ, semantic resource, Artifact, Event, Checkpoint, or fake runtime decision
  was created or claimed. The Run and Session are retained for a post-fix retry as requested.
- Automated/regression PASS: full `.codex` discovery passed `109/109`; real-Oxigraph affected
  runner/interview suite passed `35/35`; affected Ruff check passed and format check reports all
  five files formatted. Runtime is healthy: `ontology-platform.service` active, backend health
  returns `{"status":"ok"}`, and frontend HTTP `200`. A targeted secret-field scan of the new
  run/spec/business evidence found no credential material; the temporary Claude debug diagnostic
  was inspected separately and showed only redacted Authorization values, never a raw credential.
- Conclusion: **TEST_FAIL**. This is no longer an external Provider/authentication block: real
  Agents and Skills work under the required source set, but the same required execution path drops
  the project Harness Hook, making the documented Local workflow impossible to start. A requirement
  developer should fix the Claude settings/hook merge or document and implement an equivalent
  supported invocation that preserves `user,project`; then rerun this same retained Round 11 Run
  from fresh Harness activation and execute the previously unexecuted bounded end-to-end cases.

### Independent test Round 12 — 2026-07-22 — TEST_FAIL

- Tester: independent requirement tester. This round reused retained Run
  `r11007-live-round11-20260722T032400Z` and Build Session
  `3f75a472-aedc-43d4-b7f2-1b38741db2df`; only this plan and ignored test-run evidence changed.
  The developer-provided frozen correction removes Claude Code 2.1.74-unsupported
  `TaskCreated`/`StopFailure` entries from `.claude/settings.json`, fixes Local documentation to
  `user,project`, and updates matching expectations. No product/requirement/design/delivery record
  or runtime configuration was modified by this tester; no cleanup, writer-mode restoration, or
  commit was made.
- PASS — real Hook repair and activation state. The retained Harness reports
  `mode=single_claude`, `execution_profile=local`, `status=active`, and `ready=true`. The recorded
  Hook health receipt `r11007-hook-probe-20260722t0410z` has a real `consumed_at` timestamp. A
  direct repeat of `modeling_harness.py recording-health` with that same Run and operation returns
  exit `2`, `operation receipt is stale, consumed, or does not match`; an old receipt therefore
  cannot be replayed. This is an independent real safe-point boundary check, not a hand-written
  Harness state.
- PASS — fresh real main-session receipt and business commit. The resumed real DeepSeek Claude
  main session, with `--setting-sources user,project`, executed a fresh Adapter
  `recording-health` then the protected `commit-business` action using operation
  `r11007-round12-business-20260722t0420z`. Both bounded Adapter envelopes returned `status=ok`.
  The platform-created CQ is `9307f5e5-6049-4cdb-a3fe-068f5216ba2c`, status `approved`, importance
  `5`, with the exact Round 11 fixture question. Its ID was projected into both Coverage rows, both
  Work Unit task contracts, and the merged current candidate. Local directory validation passes;
  candidate hash is `f57e6211ef8a7251ea05a95f6806f2c2216c24f24b63559a270b62ca65f622bd` with the
  declared test-only class and fixture entity.
- **High — real normal-role handoffs do not stay within their supplied bounded inputs.** The
  Harness recorded real delegation/start events for Organizer, Modeler, Reviewer, and Retriever;
  normal roles made no platform writes. However, their resulting read-only outputs enumerate broad
  repository files rather than only the bounded task references. Most seriously, the Retriever
  reported retained Round 5 Run `r11007-live-round5-20260722T021500Z`, its old CQ/Batch/retrieval
  evidence and verdict in response to a current Round 11 probe. The Reviewer likewise performed a
  repository-wide implementation review rather than an independent review of the current candidate.
  These outputs are not accepted as current-run business/model/review/verification evidence.
  Expected: normal roles accept only the provided Run/Work Unit/candidate/output references and
  return only their bounded role result. Actual: read-only tool permissions do not prevent them
  from traversing unrelated retained workspace/repository data. No stale agent judgement was used
  as a platform fact or written to candidate/verification data.
- BLOCKED after the failure — a separate current-candidate independent Reviewer retry was made with
  the exact current candidate path and only the Read tool. The live DeepSeek Provider returned
  `API Error: 402 Insufficient Balance`. With no valid independent review and no new live Claude
  safe-point receipt, the tester stopped before `review.json`, Batch materialization, dry-run,
  apply, CQ validation, retrieval/provenance verification, or finish. This preserves fail-closed
  ordering rather than applying an unreviewed candidate.
- Platform containment: Build Session remains `active`, revision `1`, summary null; its Modeling
  Batch list count is `0`. The only new platform fact is the approved, intentionally retained CQ
  above. Adapter status after business commit is correctly `blocked` with
  `recording_health_required`, demonstrating the consumed business grant is not reusable. No
  semantic class/entity, Batch, Audit, explicit Artifact, Event, or Checkpoint was created or
  claimed.
- Automated/regression PASS: full `.codex` discovery passed `109/109`; real-Oxigraph affected
  runner/interview suite passed `35/35`; affected Ruff check passed and format check reports all
  five files formatted; `git diff --check` passed. `ontology-platform.service` is active, backend
  health returns `{"status":"ok"}`, and frontend HTTP `200`. Targeted run/adapter/Harness secret
  scan found only instructional words such as `secrets` in agent prose, not a credential value,
  Authorization header, bearer token, API key, password, or lease token.
- Conclusion: **TEST_FAIL**. The Hook-loading defect is fixed, fresh receipts and business CQ
  binding now work, but real role handoff confinement fails: roles can substitute unrelated retained
  Run/repository information for the supplied current references. The external DeepSeek 402 then
  blocks the valid Reviewer retry and remaining end-to-end stages. A requirement developer should
  enforce allowed input paths/reference-only access (not merely read-only tool permissions), then
  restore Provider balance and rerun this same retained Run from an independently bounded review;
  only after that can fresh health, plan, dry-run/apply, CQ/retrieval/provenance verification, and
  finish be re-tested.

### Independent test Round 13 — 2026-07-22 — TEST_BLOCKED

- Tester: independent requirement tester. This round tested the frozen four-Skill/four-thin-Agent
  reference-confinement correction and appended only this existing plan. No product/requirement/
  design/delivery record, retained Project/Run/session data, writer mode, or runtime configuration
  was changed by this tester. No cleanup, restore, or commit occurred.
- PASS — all four role contracts define the exact role-specific required reference sets in
  `.codex/tests/test_role_assignment_contract.py`: Organizer requires run/Brief/Coverage/source
  index and output refs; Modeler requires run/unit/task/result and task-declared context/schema;
  Reviewer requires run/candidate/candidate hash/Brief/Coverage/source index/Findings/output; and
  Retriever requires run/candidate hash/CQ binding/observed-query evidence/schema/output. Full
  `.codex` discovery passed `111/111`, including both new contract tests. The Agent wrappers
  independently assert that before `Read`/`Grep`/`Glob`/search an incomplete assignment returns
  exactly the no-tool JSON `status=BLOCKED`, `error_code=missing_reference`, with the missing
  reference and `next_action=supply_complete_assignment`.
- PASS — confinement and mismatch contract inspection. Each Skill's Assignment gate precedes any
  read instruction; requires resolved paths inside `assigned_run_root`; permits only exact
  dependency locators; forbids cwd/repository/workspaces/other-run discovery; and specifies
  `reference_mismatch` BLOCKED handling for a foreign `run_id` and, where candidate-bound, a
  mismatched `candidate_hash`. An independent manifest check against retained Round 11 Run confirmed
  its single exact source locator is
  `docs/evaluation-corpora/dify-foundations/README.md`, rooted at the configured repository, and
  all four Skills contain those confinement/missing/mismatch contracts. This is static/structural
  evidence only; it is not represented as a live Agent verdict.
- PASS — skill and adjacent regression gates: skill-creator `quick_validate.py` passes for all four
  new capability Skills; `python3 skills/ontology-builder/evals/validate_skill.py` validates the
  ontology-builder structure with 10 references and 34 declared MCP dependencies; real-Oxigraph
  affected runner/interview suite passes `35/35`; affected Ruff check and format check pass;
  `git diff --check` passes. Targeted secret scanning found no credential material. Runtime remains
  healthy: `ontology-platform.service` active, backend health `{"status":"ok"}`, frontend HTTP
  `200`.
- BLOCKED — the only live blocker is DeepSeek Provider balance. One deliberately minimal,
  deidentified no-tool Provider probe under the required `--setting-sources user,project` returned
  `API Error: 402 Insufficient Balance`. Per this round's safety rule, the tester did not launch a
  real role Agent, consume another Harness receipt, create a review/Batch, submit dry-run/apply,
  create semantic resources, or fabricate dynamic role acceptance after that result.
- Retained state is untouched for recovery: Round 11 Run remains
  `r11007-live-round11-20260722T032400Z`; its Session
  `3f75a472-aedc-43d4-b7f2-1b38741db2df` remains active with the Round 12 approved CQ and no
  Modeling Batch. No explicit Artifact/Event/Checkpoint is created or claimed by this round.
- Conclusion: **TEST_BLOCKED**. The previously failing reference-confinement contract now has
  complete static/automated coverage and all executable local gates pass; the sole blocker is the
  real Provider's insufficient balance. After balance is restored, the minimum next round is: (1)
  real no-tool missing-reference probes for all four roles proving no tool invocation; (2) one
  fully assigned, current-Run/candidate-hash bounded independent Reviewer handoff; (3) fresh
  Harness health; (4) materialize, dry-run/apply, CQ/retrieval/provenance verification; and (5)
  fresh finish against this retained Round 11 Run. Do not reuse prior receipts or stale Round 5
  role evidence.

### Independent test Round 14 — 2026-07-22 — TEST_PASS_WITH_ACCEPTED_RESIDUAL

- Tester: independent requirement tester. This is a compositional closure review under the user's
  explicitly adjusted R1.1-007 completion standard: a single real Claude Run is no longer required
  to repeat Reviewer through finish after Provider balance is restored, provided the independently
  established workflow has no material known product defect. Only this existing plan was appended;
  no product/requirement/design/delivery record, retained Project data, runtime configuration,
  writer mode, cleanup, or commit was changed.
- PASS — completed real platform acceptance is retained and still observable. Round 8's Build
  Session `e3536f8a-ea94-415e-9235-3381ba6353cc` currently reports `completed`; its Batch
  `b69603e8-c6c4-4250-a094-ad9539cf808f` currently reports `applied` with two items. The retained
  Round 8 evidence establishes the same Batch's real immutable dry-run/apply Attempts, passed
  entity-count CQ (`matches=1`), retrieval of `R11007Round5DifyWorkflowFixture`, complete/supported
  IRI lineage, Evidence associations, applied audit/validation facts, and protected incomplete-
  recording finish. No explicit Artifact/Event/Checkpoint was claimed by the Local profile.
- PASS — actual Claude/Harness and Local commit boundaries were independently proved rather than
  inferred from static contracts. Round 11 obtained real responses from all four project Agents
  under `user,project`, confirmed their no-platform-write role markers, and repaired the real
  `PreToolUse` activation/receipt path. Round 12 then used a fresh real main-session Hook receipt
  to commit business data; created approved platform CQ
  `9307f5e5-6049-4cdb-a3fe-068f5216ba2c`; and projected that exact ID through current Coverage,
  Work Unit contracts, and candidate. The retained Round 11 Harness still reports
  `single_claude`, Local, active, and ready. Its Session
  `3f75a472-aedc-43d4-b7f2-1b38741db2df` deliberately remains active with no Batch, so no partial
  Run is misrepresented as a completed acceptance run.
- PASS — Round 13 remedied the known role-reference-confinement gap at the contract/automated
  surface: complete role-specific refs, no-tool `missing_reference` JSON, resolved run-root and
  exact-manifest containment, discovery prohibitions, and `run_id`/`candidate_hash` mismatch
  blocking are covered by `.codex` `111/111`. Four capability-Skill quick validations,
  ontology-builder validation (10 references/34 MCP dependencies), real-Oxigraph `35/35`, Ruff
  check/format, `git diff --check`, targeted secret scan, and service/backend/frontend health pass.
  This round also rechecked `git diff --check`, service active, backend health OK, frontend HTTP
  200, retained Round 8 Batch applied, and retained Round 11 Harness ready.
- Accepted residual — these cases were **not** executed in one common Run: (1) live no-tool
  missing-reference probes for each fixed role; (2) a fully assigned fixed-role current-candidate
  Reviewer; and (3) planning through dry-run/apply/CQ/retrieval/provenance/finish after that
  Reviewer in the retained Round 11 Run. The reason is the independently observed DeepSeek
  `402 Insufficient Balance` in Rounds 12/13. The user expressly accepted that the same real Claude
  Run need not be resumed from Reviewer to finish after balance restoration and requested closure
  when no major known workflow problem remains. These items are therefore documented as accepted
  residual validation, not described as executed or silently reclassified as passing.
- Conclusion: **TEST_PASS_WITH_ACCEPTED_RESIDUAL** (independent PASS under the user-approved
  standard). The evidence covers real platform apply/verification/finish, real Agent/Hook receipt,
  real business/CQ binding, and the subsequent confinement/automated regression repair. No
  unresolved product defect is currently known. The residual remains a useful future confidence
  revalidation when Provider service is available, but is not a release blocker under this accepted
  completion decision.
