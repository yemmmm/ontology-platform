# R2.0-002 Pi 第一方建模 Agent Runtime 正式集成共享测试计划

- Requirement: `docs/requirements/requirements-v2.0.md` R2.0-002
- Design:
  `docs/delivery/designs/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-delivery-record.md`
- Status: paused at G2 checkpoint; original completion gates not met, remaining rounds will not
  continue before R2.0-003 refinement

## Completion gates

1. Plan review has no unresolved accepted Critical/High finding.
2. Pi dependency, lock, Node lower bound, Workflow Package, role/tool inventories, schemas, Runner,
   deterministic libraries, local config template, and runbook agree on one Pi Local contract.
3. Automated lifecycle, role isolation, artifact, hash/review, adapter, event/Summary, recovery, and
   retirement tests pass, including proof that `agent_end` cannot prematurely complete a role.
4. A real pinned Pi/model run completes the fixed Dify Foundations scenario from source/interview
   through real platform apply and post-apply CQ/retrieval/provenance verification.
5. The real run has no silent Coverage loss, unsupported invention, unresolved blocking Finding,
   missing important-item Evidence, failed CQ/retrieval check, or unproved provenance result.
6. After the Pi real-runtime PASS, Claude-specific modeling entrypoints and current support claims
   are removed; a final independent round passes on that post-retirement state.
7. Docs/status, uniquely owned test-data cleanup, diff/secret checks, runtime health, and commit
   closure are complete.

No gate compares Pi with Claude, requires a second optimization run, or measures token, duration,
cost, exact tool-call count, or Formal parity.

## A. Dependency, installation, and entry command

- Install with the committed lock using the documented clean command. Assert exactly the approved
  `@earendil-works/pi-coding-agent` version and Node `>=22.19.0` check.
- Reject a missing lock, unsupported Node version, unavailable Pi executable, malformed scenario,
  missing local config, unknown model/provider, or unloaded project Extension before platform
  business writes.
- Prove the tracked config/scenario contains no credential and the gitignored config can select one
  real model/provider without changing Workflow Package files.
- Start one run from the documented command and verify it reports stable run/Build Session IDs and
  the loaded role/tool inventory.
- Drive a disposable role through a normal low-level `agent_end`, an automatic retry, an automatic
  compaction retry, and a queued follow-up. In every case assert that the candidate artifact is not
  accepted and the child is not stopped until `agent_settled`, Extension idle/no-pending confirmation,
  and an empty Runner-observed queue agree.
- Prove an ordinary `agent_end` without subsequent `agent_settled` cannot satisfy role completion.
  Prove a persistent coordinator's per-turn settlement does not end the Session before the workflow
  reaches a terminal state.
- Send interrupt/timeout to a synthetic child and prove only that child is terminated and awaited;
  the Runner exits without an orphan process after the run ends.

## B. Role isolation and structured handoff

- Start coordinator, business organizer, two Work Unit modelers, reviewer, and summarizer with
  distinct Pi Session identities and exact role-specific prompts/tools.
- Business organizer writes only Brief/CQ/Coverage artifacts and cannot submit Modeling Items or
  platform apply actions.
- Each worker receives only its Work Unit, shared locators, output schema, and completed dependency
  references. It cannot write another unit or shared candidate.
- Allow parallel workers only when dependency/Coverage scopes are disjoint and within the local
  cap. Same-Ontology results still merge once before review.
- Reviewer sees sources, confirmed business state, Coverage, and candidate hash but no hidden
  modeler conversation. It returns only `PASS | REVISE | BLOCKED` with bounded findings.
- Reject malformed/oversized output, unknown locator, stale fingerprint, mismatched identity,
  unbound candidate hash, and hidden/transcript/reasoning files.

## C. Business confirmation and clarification

- Start from Project, source locators, goal, and constraints without a prebuilt Brief/CQ. Complete
  at least one real multi-turn business clarification.
- Prove no business commit or Work Unit modeling occurs before explicit Brief/CQ confirmation.
- Ask a structured ambiguity question, observe `paused`, submit the answer through the coordinator,
  and continue the same run using stable shared artifacts.
- Cancel before business confirmation and prove no candidate/Batch business write was performed.
- Retry business synchronization with stored identities and prove no duplicate CQ or changed
  confirmed content under the same identity.

## D. Candidate, review, Batch, and platform correctness

- Preserve current source/Coverage reference validation, deterministic input fingerprint,
  topological item ordering, candidate hash, candidate-bound review, capacity-aware Batch planning,
  and request materialization tests after migration from `.codex`.
- Block planning/apply for missing Evidence, unsupported command, unresolved item reference,
  candidate/review mismatch, stale result, review `REVISE/BLOCKED`, capacity violation, or blocking
  dry-run Finding.
- For an ordinary addition with confirmed Brief/CQ, reviewer PASS, matching hashes, and clean
  dry-run, apply without an extra per-Batch user prompt.
- For deletion, irreversible change, or unknown impact, require an explicit user decision before
  apply and prove rejection leaves the Batch unapplied.
- Reuse one `client_batch_id` across dry-run/apply, keep immutable content fixed, and use new
  attempt/idempotency identities where the existing platform contract requires them.
- Materialize later Batches only after predecessor apply returns stable resource identities; never
  submit cross-Batch item references.

## E. Events and stage summaries

- Assert ordered JSONL events for run/role/Session, stage, model, tool, clarification, artifact, and
  terminal state with stable run and role correlation.
- Assert queue updates, auto-retry, compaction, `agent_end`, `agent_settled`, and terminal-idle
  eligibility remain ordered and distinguish low-level completion from final role settlement.
- Assert tool start is written before the internal adapter call and success/failure is written after
  the bounded result.
- Generate schema-valid summaries after business organization, every Work Unit, independent
  review/apply, and final verification.
- Summary input is limited to that stage's visible events and artifact references. Reject extra
  fields, hidden reasoning, full transcript, raw source body, raw platform response, or credential.
- Simulate a Summary failure. Keep already applied platform state, mark stage completion pending,
  and allow a targeted Summary retry without rerunning successful modeling.

## F. Failure and local recovery

- Kill a worker after partial transient output; reject the partial file and rerun only that Work
  Unit with the same stable inputs.
- Change one referenced input and prove stale output cannot merge. Unaffected accepted units remain
  reusable.
- Return a platform Finding, map it to affected units, and require result regeneration, candidate
  merge, review, and dry-run before apply.
- Simulate timeout after platform apply but before local success recording. Reconcile the original
  Batch/attempt/idempotency identity and prove no replacement Batch or duplicate fact is created.
- Fail a later Batch and retain the already applied valid prefix. Final verification cannot PASS
  until the remaining plan succeeds.
- Restart the coordinator process against stable run files. Do not claim restoration of full chat,
  hidden reasoning, or the lost Pi process.

## G. Real Pi and real platform acceptance

- Freeze the tracked Dify Foundations snapshot, scenario hash, Pi/package lock, model/provider, and
  acceptance questions before the run. Do not add Dify-specific branches to production code.
- Use a fresh uniquely named Project/Ontology/run or another ownership-proven isolated target.
- Run the documented Pi command with a real model and current local platform. Exercise business
  organizer, at least two meaningful Work Units when the scenario supports them, independent
  reviewer, clarification, stage summaries, dry-run, apply, CQ, retrieval, and provenance.
- Inspect the applied ontology and artifacts for source fidelity, business scope, class/property/
  relation correctness, evidence on important items, explicit gaps, and absence of invented facts.
- Execute every tracked acceptance question and record observed CQ/retrieval/provenance evidence.
  Qualitative assertions must not be presented as platform-executed CQ results.
- The real run verdict is `PASS | FAIL | BLOCKED`. A failure remains in this plan and enters the
  developer/tester defect loop; it is never replaced by a cleaner report.

## H. Claude retirement and regression

- Keep the frozen Claude path until section G has an independent PASS. Before that PASS, fail any
  change that removes the only working modeling entry.
- After PASS, remove Claude-specific modeling Agent definitions, Hook/Harness, fast-local launcher,
  scenario adapters, summary path, active tests, and current runbooks.
- Migrate still-used Shared Modeling Directory and deterministic platform Adapter code/tests into
  the Pi package; prove their established contracts still pass.
- Update v1.1/v2.0 status, architecture, guide, and active capability tables so Claude
  Local/fast-local/strict-eval/Formal are historical/unsupported and Pi Local is current.
- Replace README's ontology-builder installation/run instructions, the hard-coded
  `backend/tests/test_documentation_sync.py` ontology-builder dependency contract, and the
  `.github/workflows/docs-sync.yml` legacy Skill validator/eval steps with Pi package checks or an
  explicitly justified deletion of obsolete assertions. Assert no active test or CI reads a removed
  Claude modeling path.
- Verify ADR 0007 is accepted and v1.0, v2.0, ADR 0001, ADR 0007, and architecture overview agree
  that Pi is first-party product code outside Semantic Platform Core and has no privileged write path.
- Scan tracked active files for old modeling entry commands and support claims. Historical delivery
  records may retain accurate past wording.
- Prove unrelated `.claude/skills/gitnexus`, repository instructions, and non-modeling development
  configuration remain intact.
- Run the final independent regression round on the post-retirement stable state; section G evidence
  remains linked and no rerun is required unless retirement changed Pi/runtime behavior.

## I. Security, cleanup, and documentation bounds

- Scan prompts, events, summaries, shared artifacts, stdout/stderr captures, tracked/staged diff,
  and new commit content for the configured secret sentinel; it may occur only in its ignored source.
- Verify no backend/frontend schema, Pi Session/event public API, service unit, remote scheduler,
  monitoring UI, or server event table was added.
- Remove only uniquely owned synthetic Project/Ontology/run data. If ownership cannot be proven,
  preserve it and record the reason.
- Verify the affected local service remains healthy during the real acceptance run. Product runtime
  restart/health rules apply if implementation changes backend/frontend runtime code or shared
  runtime configuration; the planned backend documentation-contract test edit still requires the
  full backend test suite.
- Run `git diff --check`, required package/Python tests, scoped doc consistency checks, GitNexus
  `detect_changes`, and final `git status` before commit.

## Planned command groups

Exact package scripts may be shortened during implementation, but the final documented commands
must cover:

```text
cd pi-modeling-agent && npm ci
cd pi-modeling-agent && npm test
python3 -m unittest discover -s pi-modeling-agent/tests
cd backend && uv run pytest
cd backend && uv run python ../scripts/sync-interface-docs.py --check
<Pi Local fixed-scenario real-runtime command>
curl --fail http://127.0.0.1:8001/api/health
git diff --check
```

The full backend suite is mandatory because retirement deliberately changes the backend documentation
contract test. If backend/frontend runtime code or shared runtime configuration also changes, run
every repository-mandated suite and restart/health procedure for that surface.

## Independent test rounds

Append every round below. Do not delete failed or blocked rounds.

### Round 1 — 2026-07-22 — PASS (phase 1, sections A–F)

- Tester: requirement_tester (independent). Did not trust developer numbers; re-ran all suites and
  reviewed implementation source.
- Stable state: worktree at HEAD `294e5eb` + untracked `pi-modeling-agent/` (43 tracked files,
  `node_modules` installed) + modified delivery-record. Developer stopped (development-ready).
- Scope: shared test plan sections A–F only (automated contract + pre-retirement Pi path). G (real
  Pi/model/platform run), H (Claude retirement), and the retirement portion of I are out of phase 1
  and were NOT attempted: no real model call, no real platform apply, no Claude file removed/retired.
- Result: PASS. All A–F automated contracts hold; no Critical/High defect found. Phase 1 may proceed
  to G after the Medium residual below is dispositioned by the main agent.

Execution (exact commands and results):

- `cd pi-modeling-agent && npm test` -> 29/29 pass, 0 fail (node:test). Covers A lifecycle/entry,
  B role isolation, C clarification, E events/summaries, F recovery, entry-validation.
- `python3 -m unittest discover -s pi-modeling-agent/tests` -> 59/59 pass (test_shared_modeling_directory
  16, test_platform_adapter 20, test_modeling_handoff 21, test_modeling_profiles 2). Covers D migrated
  deterministic core + runner-authorization gating.
- `git diff --check` -> clean.
- `git diff --stat 294e5eb -- .claude .codex skills README.md .github backend/tests/test_documentation_sync.py`
  -> empty (frozen paths untouched). `git diff --stat 294e5eb -- backend/app` -> empty (backend product
  code untouched).
- grep `recording_grant|recording_health|recording_unavailable|modeling_harness` across
  `pi-modeling-agent` -> 0 matches (receipt/Harness coupling fully removed).
- grep Pi Session/event types into `backend/app` -> 0 matches (no backend schema/API leakage).
- Secret scan across tracked pi files -> only deliberate test fixtures in `tests/*.py`/`*.test.mjs`;
  no real credential in production files.

Independent contract verification (highlights, not just developer assertions):

- A lifecycle (load-bearing): `src/rpc-session.mjs` `isCompleteEligible()` requires
  settled && extensionIdle && queueEmpty && pendingInputs empty && !exited, all simultaneously.
  `RESET_EVENTS` (agent_end/turn_start/auto_retry/compaction_start/compaction_end) clear
  settled/idle. `a-lifecycle.test.mjs` proves a plain `agent_end` without `agent_settled` rejects
  (`/before role settlement/`), and parametrized normal/auto-retry/compaction/queued-follow-up cases
  each complete only after the final triple signal. Interrupt/timeout kills only the victim child and
  `dispose()` leaves `run.sessions.size == 0` with every child exited (no orphan).
- D migration: `lib/{shared_modeling_directory,modeling_handoff,modeling_profiles}.py` are byte-identical
  to the `.codex` originals (contracts preserved); `lib/platform_adapter.py` is the cleaned
  `local_modeling_adapter.py` (1278->1209 lines, receipt coupling removed). Every protected write
  (commit_business/dry_run_next/apply_next/verify/finish) calls `_consume_runner_grant`; tests prove
  refusal before any platform call (request_mock call_count == 2 / assert_not_called) and single-use
  consumption. apply-timeout keeps original client_batch_id + idempotency key, no lease-token leak.
  failed-CQ blocks before local verification, marks `cq_recovery_required`, recovers with a fresh
  grant; reconcile uses the real platform batch detail attempt without resubmission.
- B/C/E/F: reviewer forbidden-key (transcript) rejection, unsettled-artifact rejection, clarification
  requested->paused->answered ordering with no duplicate id, cancel-before-confirm writes no accepted
  artifact, summary schema rejects missing/extra/hidden fields and keeps applied state on summary
  failure, worker-kill rejects partial output and reruns same unit, coordinator per-turn settlement
  does not end the persistent session until `markTerminal`.

Defects (by severity):

- Medium (residual, not phase-1 blocking): `pi-modeling-agent/lib/modeling_handoff.py` is byte-identical
  to `.codex/modeling_handoff.py` and still contains a Codex CLI subprocess launcher
  (`start_codex`/`supervisor` spawning `codex exec`, `--codex-bin` args) plus a hard-coded reference to
  `skills/ontology-builder/references/modeler-handoff.schema.json`. It is dead code in the Pi package
  (no non-test reference; the Pi Runner and `platform_adapter.py` do not import it). It does NOT carry
  the removed receipt coupling, and its own 21 tests pass. Risk: it ships in the "only actively
  maintained" Pi package and its schema/supervisor paths will break when Claude retirement (H) deletes
  `skills/ontology-builder`. The design's proposed layout listed only `shared_modeling_directory.py`
  and `platform_adapter.py` under `lib/`; this module should be removed from the Pi package or its
  Codex supervisor stripped before/in H. ADR/requirement boundary not violated because nothing invokes
  it. Related: README "Layout" line and delivery-record handoff both describe `lib/` as including
  handoff/profiles, so wording should track the final disposition.
- Low (already documented by main agent): `lib/platform_adapter.py` has ~7 lines >100 chars (longest
  159), inherited verbatim from the `.codex` original to preserve migration fidelity. Ruff 100-col
  style conformance deferred.

Unexecuted cases (out of phase 1, not counted as pass):

- G real Pi/model/platform run; H Claude retirement regression; I retirement cleanup + final backend
  suite + docs-sync CI rewrite. These require a real model key and the post-retirement stable state.
- Entry-command rejection matrix for "unavailable Pi executable" and "unloaded project Extension" is
  only unit-covered indirectly (`resolvePiBinary`/`validateWorkflowPackage`); full rejection proof
  belongs to the real run (G).

Residual risks:

- `modeling_handoff.py` dead-coupling (see Medium above) surfaces at Claude retirement.
- Mock/fake-based A–F cannot prove real Pi 0.81.1 event sequencing, real model correctness, or real
  platform apply idempotency; that remains G's gate.
- Phase 1 did not run the full `cd backend && uv run pytest` suite or restart
  `ontology-platform.service` (no backend/frontend runtime code changed; only the documentation-contract
  test edit is planned for retirement in a later phase).

### Round 2 — 2026-07-23 — PASS (G1 end-to-end orchestrator, section G subset)

- Tester: requirement_tester (independent). Reviewed `orchestrator.mjs` source before testing; did not trust
  developer numbers and re-ran all suites plus targeted probes for paths the fake harness masks.
- Stable state: HEAD `2c4a678` (phase 1 committed) + uncommitted G1 worktree changes only under
  `pi-modeling-agent/`: modified `{scenarios/dify-foundations-v1.json, src/cli.mjs, src/runner.mjs,
  tests/fixtures/fake-pi.mjs}`; new `{src/orchestrator.mjs, tests/fixtures/fake-adapter.mjs,
  tests/g-orchestration.test.mjs, tests/smoke-real-pi.mjs}`. Developer stopped (development-ready). Not committed.
- Scope: G1 only — the end-to-end `ModelingOrchestrator` over the phase-1 `ModelingRun` primitives, driven by
  the fake-Pi subprocess + fake platform adapter. G2 (real model call, real platform apply, real CQ/retrieval/
  provenance verification), H (Claude retirement), and I retirement cleanup are NOT attempted and not counted
  as pass. No real `pi` model call and no real platform write occurred (the G2 gate).
- Result: PASS for the G1 automated gate. The orchestration contract holds end to end with fakes: stage
  ordering, business-confirmation gate, same-Ontology candidate merge, review hard-gate, protected-write
  wrapping with one-shot authorize, clarification routing, schema-valid stage summaries, local Work-Unit
  recovery, terminal disposal with no orphan, frozen-path and secret/leak invariants, and the phase-1 A–F
  suite still green after the `acceptArtifact`/`fake-pi` race fix. Four recovery-completeness/prompt findings
  (below) are masked by the fake harness and do not break the G1 gate but must be dispositioned before G2.

Execution (exact commands and results):

- `cd pi-modeling-agent && npm test` -> 32/32 pass, 0 fail (node:test). 30–32 are the G1 orchestrator cases
  (full stage sequence, local recovery, cancel-before-confirm); 1–29 are the phase-1 A–F cases re-run after
  the race fix.
- `python3 -m unittest discover -s pi-modeling-agent/tests` -> 59/59 pass (unchanged deterministic core +
  runner-authorization gating).
- `git diff --check` -> clean (exit 0).
- `git diff --stat 2c4a678 -- .claude .codex skills README.md .github backend/` -> empty; same for `backend/app`
  -> empty (frozen paths and backend product code untouched by G1).
- Secret scan across `pi-modeling-agent/{src,lib,workflow,extensions,scenarios}` -> 0 hits. Receipt/Harness
  residue (`recording_grant|recording_health|recording_unavailable|modeling_harness|.codex/hooks`) -> 0.
  Pi Session/event types (`agent_settled|extension_ui_request|queue_update|modeling_idle|RpcSession|ModelingRun|
  invokeAdapter`) into `backend/app` -> 0 (no backend schema/API leakage).
- Scenario `dify-foundations-v1.json` source locators repointed to the real evaluation-corpus snapshot
  (`docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a/official/...`);
  all 5 locators exist on disk; top keys are exactly the allowed business-input set; the Dify business-concept
  constraint is retained (no platform-domain promotion, no credential).

Independent contract verification (not just developer assertions; highlights of the load-bearing paths):

- Stage ordering (`_runWorkflow`): coordinator introduce -> business organize (Brief/CQ/Coverage accepted after
  settlement) -> host `confirm` gate -> directory init + platform start + commit_business -> per ontology:
  capacity-aware dependency-disjoint Work-Unit scheduling -> merge one candidate -> review -> plan + dry-run/
  apply loop -> per-stage summary -> per-ontology verify -> finish -> final-verification summary. Matches the
  design Runtime lifecycle. Coordinator is persistent and only stopped in `execute()` finally after
  `markTerminal`; `stopRole` enforces `terminal` for the coordinator.
- Business confirmation gate (`_organizeBusiness`): `confirm(plan)` returning false calls `_platform("cancel")`
  and throws before any `start`/`commit_business`. The dedicated test proves no `commit-business` adapter call
  and a `cancel` was issued. Cancel is not a runner-granted write (matches the real adapter, which has no
  `_consume_runner_grant` on `cancel`).
- Review hard-gate (`_reviewOntology`): PASS returns and is the only path into `_planAndApply`; REVISE/BLOCKED
  never reaches apply. Protected writes are wrapped (`_platform` -> `invokeAdapter` records `tool_start` before
  and `tool_end` after; test proves balanced counts and dry-run start-before-end ordering). Each protected write
  (commit/dry/apply/verify/finish) is preceded by its own `authorize-runner-write` (one-shot grant; the real
  adapter's `authorize_runner_write` stores one unconsumed grant per `operation_id` and `_consume_runner_grant`
  marks it consumed exactly once). The adapter CLI records `role_settled=True` by internal trust; the
  orchestrator only calls `_authorize` at points where the producing role already settled (`acceptArtifact`
  requires `isCompleteEligible()`), so the trust boundary holds.
- Clarification routing (`driveRole` + `_observe`): `extension_ui_request input` -> `clarification_requested`
  -> `clarification_paused` -> handler -> `respondUi` -> `clarification_answered`, ordered, single handler
  invocation, no duplicate request id.
- Same-Ontology candidate merge: two Work Units under one ontology merge into one candidate per review round;
  the test asserts `mergeCount >= 2` (initial + after REVISE).
- Local Work-Unit recovery (`_driveWorkUnit`): a Work Unit that hangs/is killed mid-output is `reclaimRole`-ed
  and re-run with the same stable inputs (bounded by `MAX_WORK_UNIT_ATTEMPTS`); the rerun's complete artifact is
  accepted. The dedicated test proves a reclaim event and post-rerun acceptance.
- Race-fix non-regression: `acceptArtifact` still gates on `isCompleteEligible()` at the top (settled + idle +
  empty queue + no pending + not exited); `readArtifactWithGrace` only retries on `ENOENT` and never changes
  accept/reject semantics. `fake-pi.mjs` now writes artifacts atomically (temp + rename). All 29 phase-1 cases
  re-pass under these changes.
- Stage summaries: business-organization, work-unit-<ontology>, and final-verification each produced a Summary
  whose key set exactly matches the shared schema (`validateSummary` runs inside `summarizeStage`).
- Lifecycle/dispose: `execute()` finally stops the coordinator (only when terminal) and `dispose()` force-reclaims
  every remaining session; `sessions.size === 0` after every case (no orphan).

Defects (by severity; all masked by the fake harness, none breaks the G1 automated gate):

- Medium — `_reviewerPrompt` emits a literal `${ontologyId}` instead of the ontology id
  (`src/orchestrator.mjs:669` uses a double-quoted string, not a template literal). The fake reviewer ignores the
  prompt, so G1 passes; in G2 a real reviewer model would be told the file path
  `artifacts/review-${ontologyId}.json` literally. Trivial one-token fix (double quotes -> backticks). Related
  acceptance: B/E reviewer bounded output + correct artifact locator.
- Medium (High for G2 readiness) — REVISE/BLOCKED does not regenerate Work Units. `_reviewOntology` only
  re-merges the unchanged Work-Unit outputs and re-reviews (`src/orchestrator.mjs:441-471`); its own comment
  claims "regenerate the affected Work Units" but no `_driveWorkUnit` re-occurs. Independent probe (all-REVISE
  sequence) confirmed: `wuLaunches == 1`, 3 re-merges, then throw after `MAX_REVIEW_ROUNDS`. The fake masks it
  because the fake merge returns a fresh hash per round and the fake reviewer is scripted PASS on round 2. In G2
  a genuine reviewer REVISE on an unchanged candidate would loop to the round cap and fail with no recovery. The
  "never apply on REVISE" hard gate still holds. Design "Failure and recovery" requires "regenerate, merge, and
  review again". Recommend disposition before G2 (implement finding->affected-Work-Unit regeneration, or
  explicitly scope it and document).
- Medium — blocking dry-run Finding hard-stops instead of mapping to Work Units. `_planAndApply` throws on
  `dry_run_findings` (`src/orchestrator.mjs:493-495`) rather than mapping the Finding to affected Work Units for
  regeneration/re-merge/re-review/re-dry-run. It correctly never waives (no apply — probe confirmed `apply-next`
  count 0), but it does not auto-recover. Design "Failure and recovery" requires "map to affected Work Units and
  repeat merge/review/dry-run". Masked in G1 (fake adapter never returns a Finding on the happy path).
- Low — candidate-hash early-mismatch check absent. `_modelOntology` replaces the merged hash with
  `review.artifact.candidate_hash` (`src/orchestrator.mjs:382,456`) without verifying the reviewer's hash equals
  the merged one. The real adapter is the backstop (grant binds `artifact_hash`), so this is defense-in-depth
  only.
- Low — Summary granularity vs the literal design. The design lists summaries at "each Work Unit" and
  "independent review/apply" as distinct points; the orchestrator emits one per-ontology summary
  (`work-unit-<ontology>`) combining Work-Unit-modeler and reviewer records. Schema is still valid; only
  granularity collapses for multi-Work-Unit ontologies.

Unexecuted cases (out of G1, not counted as pass):

- G2 real Pi/model/platform run (real model call, real platform apply, real post-apply CQ/retrieval/provenance);
  H Claude retirement regression; I retirement cleanup + final backend suite + docs-sync CI rewrite.
- `tests/smoke-real-pi.mjs` (real pinned-pi startup/reclaim, no prompt/model) is manual-only (not matched by
  `*.test.mjs`); not run here because it needs a gitignored `.pi/agent/{auth,models-store}.json`. It is a G2
  readiness aid, not a G1 gate.
- Full `cd backend && uv run pytest` and `ontology-platform.service` restart were not run: G1 changed no
  backend/frontend runtime code or shared runtime configuration (only `pi-modeling-agent/`).

Residual risks:

- The four findings above are masked by fakes and will surface in G2. The REVISE-regeneration gap is the highest
  G2-readiness risk: a real reviewer is likely to REVISE at least once, after which the unchanged candidate
  re-review cannot satisfy the gate and the run throws. The main agent should resolve the prompt bug and
  disposition REVISE-regeneration + dry-run-Finding mapping before launching G2.
- G1 routes business confirmation through an independent host `confirm` callback (not a persistent-coordinator
  clarification turn), and clarifications through an injectable `clarify` handler. This cleanly avoids
  multi-driving the persistent coordinator. For G2 the host (main agent/user) must wire real handlers; the CLI's
  `runRealModeling` intentionally leaves both at their throwing defaults, so the shipped CLI cannot complete a
  real run unattended — that is expected and is G2's integration point, not a G1 defect.
- `_verificationDoc` is a placeholder (`candidate_hash: null`, empty checks/gaps, verdict PASS); G2 must populate
  real CQ/retrieval/provenance content before the platform verify gate is meaningful.

### Round 3 — 2026-07-23 — PASS (G1 orchestrator repair retest, #1-#4 fixed, no regression)

- Tester: requirement_tester (independent repair retest). Did not trust the developer's 5 regression tests; wrote a
  separate probe harness with deliberately different targets (findings on the OTHER work unit, transitive-dependency
  expansion, REVISE+wrong-hash combos) so a hardcoded-to-developer-scenario bug would still be caught.
- Stable state: HEAD `2c4a678` (phase 1 committed) + uncommitted G1+repair worktree changes only under
  `pi-modeling-agent/`. The repair round touched ONLY the G1 untracked files: `src/orchestrator.mjs`,
  `tests/g-orchestration.test.mjs`, `tests/fixtures/fake-adapter.mjs` (+ the pre-repair G1 tracked modifications
  `scenarios/dify-foundations-v1.json`, `src/{cli,runner}.mjs`, `tests/fixtures/fake-pi.mjs`, unchanged by the repair).
  Developer stopped (development-ready). Not committed.
- Scope: repair retest of Round 2 defects #1-#4 plus full A-F + G1 contract non-regression, all under the fake-Pi +
  fake-adapter harness. G2 (real model call, real platform apply, real CQ/retrieval/provenance), H (Claude retirement),
  and I retirement cleanup remain NOT attempted and not counted as pass.
- Result: PASS. #1-#4 are independently confirmed fixed; the phase-1 A-F (race-fix) and G1 happy/recover/cancel
  contracts still hold (37/37 npm, 59/59 python); frozen paths and secret/leak invariants are clean. No new defect.

Execution (exact commands and results):

- `cd pi-modeling-agent && npm test` -> 37/37 pass, 0 fail (node:test). 1-29 phase-1 A-F (race-fix); 30-32 G1
  happy/recover/cancel; 33-37 the developer's 5 repair-round regression tests (#1/#2x2/#3/#4).
- `python3 -m unittest discover -s pi-modeling-agent/tests` -> 59/59 pass (unchanged deterministic core).
- Independent Round 3 probe harness (`/tmp/r3-probe.mjs`, written by tester, since-removed): 12/12 probe checks passed.
- `git diff --check` -> clean (exit 0).
- `git diff --stat 2c4a678 -- .claude .codex skills README.md .github backend/ docs/architecture docs/requirements
  docs/delivery/designs` -> empty (frozen paths untouched by repair).
- Secret scan across `pi-modeling-agent/{src,lib,workflow,extensions,scenarios}` -> 0 real-credential hits. Receipt/Harness
  residue (`recording_grant|recording_health|recording_unavailable|modeling_harness|.codex/hooks`) -> 0. Pi
  Session/event types into `backend/app` -> 0 (no backend schema/API leakage).

Independent contract verification (#1-#4, not just developer assertions — each probed with a target/shape the
developer's tests did not use):

- #1 — reviewer prompt: `_reviewerPrompt` now uses a backtick template literal
  (`\`artifacts/review-${ontologyId}.json\``). Direct call with ids `ont-xyz`, `ont-probe`, `dify-foundations` each
  produced a prompt containing the concrete path `artifacts/review-<id>.json` and containing neither the literal
  `${ontologyId}` nor any `review-${` token. Static source check confirms the backtick form and the absence of the old
  single/double-quoted literal placeholder. The literal-leak defect from Round 2 is gone.
- #2 — REVISE/BLOCKED regeneration: `_modelOntology` stabilization loop merges -> reviews -> on a non-`{ok:true}`
  outcome calls `_regenerateAffected` which re-fires `_driveWorkUnit` for each affected unit, then re-merges and
  re-reviews. Independent probes: (a) REVISE finding naming `wu-b` (the OTHER unit, not the developer's `wu-workflow`)
  regenerated ONLY `wu-b` (`wuLaunchCount(wu-b)==2`, `wu-a==1`) then PASS -> apply — confirms mapping is not hardcoded;
  (b) three-unit chain `wu-c <- wu-b <- wu-a`, finding on the root `wu-a` regenerated all three (transitive dependent
  closure in `_affectedUnits`); (c) a locator-shaped finding `artifacts/wu-b.json` mapped to `wu-b`; (d) a finding with
  no resolvable work_unit reference conservatively regenerated ALL units; (e) an unresolvable all-REVISE sequence threw
  after exactly `MAX_REVIEW_ROUNDS(3)` review rounds with `/did not stabilize/`, never reached `dry-run-next` or
  `apply-next`, and left `sessions.size==0`. The developer's locator/`reviewSequence:["REVISE"]` assertions were
  reproduced independently.
- #3 — blocking dry-run Finding: `_planAndApply` surfaces `dry_run_findings` to the stabilization loop
  (`{blocked:"dry_run_findings", findings}`) instead of throwing; the loop regenerates affected Work Units, re-merges,
  re-reviews, and re-dry-runs; apply runs only after a clean dry-run. Independent probe with a Finding pointing at
  `wu-workflow` and a companion `wu-other`: `dry-run-next` ran >= 2 times, `wu-workflow` regenerated (launch 2),
  `wu-other` untouched (launch 1), `apply-next` ran exactly once, a `FAILURE` event with `reason:"dry_run_findings"` was
  recorded. The Finding is never waived.
- #4 — candidate_hash mismatch: `_reviewOnce` returns `{ok:true}` only when `verdict==="PASS" && returnedHash===candidateHash`;
  any mismatch is classified `candidate_hash_mismatch` (hash precedence over verdict) and routed to regeneration.
  Independent probe: PASS verdict with a mismatched hash on round 1 was rejected (not silently applied), recorded a
  `candidate_hash_mismatch` FAILURE event, regenerated, then round-2 PASS with matching hash applied. A second probe
  (REVISE + wrong hash + finding) confirmed the mismatch classification takes precedence over REVISE and the run still
  recovered and applied. Static check confirms the source encodes `returnedHash !== candidateHash ? "candidate_hash_mismatch"
  : verdict` and that ok requires PASS AND matching hash.
- Non-regression (race-fix + G1 contracts): `rpc-session.mjs` triple gate intact (`isCompleteEligible` requires
  `settled && extensionIdle && ...`; `RESET_EVENTS` still includes `agent_end` and clears `settled`/`extensionIdle`;
  `acceptArtifact` gates on `isCompleteEligible()`). `cli.mjs` still wires `ModelingOrchestrator.execute()` via
  `runRealModeling`. `agent_settled` three-door, dispose-no-orphan, one-shot authorize, business-confirmation gate, and
  cancel-before-confirm no-commit all hold (assertions unchanged in tests 1-32). `smoke-real-pi.mjs` remains manual-only
  (not matched by `tests/*.test.mjs`; needs gitignored `.pi/agent`).

Defects (by severity): none. #1-#4 from Round 2 are fixed; no new defect introduced by the repair round.

Residual risks carried forward (not blocking G1, tracked for G2):

- #5 (Round 2 Low, unchanged): Summary granularity is per-ontology (`work-unit-<ontology>`) rather than the design's
  literal per-Work-Unit + independent-review/apply points; schema is valid. G2 must judge whether this collapses useful
  signal for multi-Work-Unit ontologies.
- Finding locator/work_unit mapping relies on the real reviewer naming `work_unit_id`/`work_unit`/a locator that
  contains the unit id. The conservative fallback regenerates ALL units when a finding is unmappable, so a blocker is
  never silently skipped, but G2 with a real reviewer is the first test of locator fidelity. BLOCKED is treated as
  recoverable via regeneration (design lumps REVISE/BLOCKED together); a genuinely user-blocking BLOCKED would still
  loop to the cap rather than pause — acceptable for G1, to confirm against real reviewer semantics in G2.
- G1 routes business confirmation through an independent host `confirm` callback and clarifications through an injectable
  `clarify` handler; the shipped CLI leaves both at their throwing defaults, so a real run needs the host (G2) to wire
  real handlers. Expected G2 integration point, not a defect.
- `_verificationDoc` is still a placeholder; G2 must populate real CQ/retrieval/provenance content.

Unexecuted cases (out of G1, not counted as pass):

- G2 real Pi/model/platform run; H Claude retirement regression; I retirement cleanup + final backend suite + docs-sync
  CI rewrite. `smoke-real-pi.mjs` is manual-only (needs gitignored `.pi/agent/{auth,models-store}.json`).
- Full `cd backend && uv run pytest` and `ontology-platform.service` restart were not run: the repair changed no
  backend/frontend runtime code or shared runtime configuration (only `pi-modeling-agent/`).

### Final post-retirement round — pending

- Stable state: pending Pi real-runtime PASS and Claude retirement.
- Scope: post-removal regression, documentation/status consistency, cleanup, and final completion.
- Result: not run.
- Defects/unexecuted cases: pending.
- Evidence: pending.
