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

### Round 1 — pending

- Stable state: pending implementation-ready handoff.
- Scope: automated contract and pre-retirement Pi path.
- Result: not run.
- Defects/unexecuted cases: pending.
- Evidence: pending.

### Final post-retirement round — pending

- Stable state: pending Pi real-runtime PASS and Claude retirement.
- Scope: post-removal regression, documentation/status consistency, cleanup, and final completion.
- Result: not run.
- Defects/unexecuted cases: pending.
- Evidence: pending.
