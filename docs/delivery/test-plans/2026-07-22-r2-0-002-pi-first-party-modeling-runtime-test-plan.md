# R2.0-002 Pi 第一方建模 Agent Runtime 正式集成共享测试计划

- Requirement: `docs/requirements/requirements-v2.0.md` R2.0-002
- Design:
  `docs/delivery/designs/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-22-r2-0-002-pi-first-party-modeling-runtime-delivery-record.md`
- Status: reviewed; mandatory plan review PASS, implementation rounds pending

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

### Final post-retirement round — pending

- Stable state: pending Pi real-runtime PASS and Claude retirement.
- Scope: post-removal regression, documentation/status consistency, cleanup, and final completion.
- Result: not run.
- Defects/unexecuted cases: pending.
- Evidence: pending.
