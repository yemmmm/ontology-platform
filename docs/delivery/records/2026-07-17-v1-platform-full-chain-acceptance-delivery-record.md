# v1 平台全链路验收 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.0.md` R-001～R-008、R-011
- Status: delivered
- Started: 2026-07-17T14:27:35+08:00
- Last updated: 2026-07-17T15:25:34+08:00
- Design: `docs/delivery/designs/2026-07-17-v1-platform-full-chain-acceptance-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-17-v1-platform-full-chain-acceptance-test-plan.md`
- Delivery baseline: `72df4ad Secure API and MCP access`, plus pre-existing uncommitted R-009/R-010 status and v1.1 document edits
- Delivery commit: pending

## Confirmed contract

- Current behavior: R-001～R-008 have focused tests and recorded full-suite runs; no single real-dependency scenario proves their combined protocol.
- Target behavior: a reproducible, authenticated platform acceptance proves the build/write/evidence/lineage/query/recovery/isolation path across REST, MCP and runtime dependencies.
- In scope: R-001～R-008, R-011; new cross-requirement acceptance automation and its documentation.
- Non-goals: R-009, R-010, Pending requirements, external Agent execution, Dify calls, and business-model quality.
- Acceptance summary: design and shared plan define main, failure/isolation, regression and runtime gates.
- Refinement: the user requested “请完成全链路验收” after being presented this exact v1 platform scope; this is treated as confirmation of that scope. Low-impact fixture and harness details remain conservative implementation choices.

## Timeline

### 2026-07-17T00:00:00+08:00 — discovery and scope freeze — main agent

- Context: current v1 requirements mark R-001～R-008 and R-011 implemented; R-009 is Pending and R-010 is adjusted into v1.1.
- Action/decision: preserve existing user worktree changes; define release-level platform acceptance without reviving the former R-010 Dify metrics.
- Evidence: `docs/requirements/requirements-v1.0.md`, `docs/requirements/requirements-v1.1.md`, `frontend/tests/live-contract.spec.ts`, PostgreSQL opt-in test files.
- Outcome/next step: design and shared test plan created; send for plan review.

### 2026-07-17T14:27:35+08:00 — risk probes and plan revision — main agent

- Context: local service is active; health is 200 and unauthenticated `/api/projects` is 401. A real stdio MCP probe authenticated with the protected local operator credential and listed 55 tools without exposing the key.
- Action/decision: plan review found the service defaults to `legacy_only`, which blocks R-004 RDF writes, and identified four omitted requirement-critical boundaries.
- Evidence: `backend/app/core/config.py`, `backend/app/services/semantic_canonical_write.py`, `docs/delivery/test-plans/2026-07-16-r007-operation-semantics-test-plan.md`, and review Round 1.
- Outcome/next step: add controlled `rdf_primary` setup/restore, recovery/partial apply, actor/secret, real Project-bound MCP, and multi-Ontology scope cases; resubmit for review.

### 2026-07-17T14:32:00+08:00 — plan review Round 2 — plan_reviewer

- Context: revised design and shared plan were rechecked against R-001～R-008/R-011 and the runtime/code paths.
- Action/decision: PASS. All previous Critical/High findings are covered by executable gates.
- Evidence: plan-review Round 2 report; reviewed design and test plan.
- Outcome/next step: freeze the reviewed scope and delegate implementation of the acceptance harness and focused regressions.

### 2026-07-17T14:45:00+08:00 — development handoff complete — requirement_developer

- Context: reviewed acceptance scope was implemented without changing production code or the user's R-011 document edits.
- Action/decision: added opt-in `backend/tests/test_v1_full_chain_acceptance.py` for real HTTP, PostgreSQL/Oxigraph and stdio MCP execution with reversible systemd write-mode setup, resource cleanup and key revocation.
- Evidence: `uv run ruff check tests/test_v1_full_chain_acceptance.py`, py_compile, and `uv run pytest tests/test_modeling_batches_service.py tests/test_mcp_auth.py -q` = `53 passed`.
- Outcome/next step: developer reports a stable worktree but no clean live PASS artifact; freeze and hand to independent tester for code review and full plan execution.

### 2026-07-17T15:05:00+08:00 — independent test Round 1 — requirement_tester

- Context: the tester reviewed the harness and ran it against the real local service with temporary `rdf_primary` mode.
- Action/decision: FAIL / High. The harness expected `scope.ontology_ids`, while the live API returns `scope.ontologies[].ontology_id`, so it stopped before later assertions. Review also confirmed missing contract proof for lineage/Evidence reads, `apply_partial` and controlled recovery, actor/audit non-persistence, and `GRAPH ?g` isolation.
- Evidence: `RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest -vv -s --tb=long tests/test_v1_full_chain_acceptance.py` = `1 failed` in 34.43s; shared test plan Round 1; backend `689 passed, 4 skipped`, PostgreSQL concurrency `3 passed`, docs sync `10 passed`, frontend build passed, Playwright `33 passed, 3 skipped`.
- Outcome/next step: confirmed harness defects return to requirement_developer; prior successful checks remain recorded, but independent PASS is not achieved.

### 2026-07-17T15:18:00+08:00 — repair Cycle 2 development-ready — requirement_developer

- Context: Round 1 High findings were reproduced against the real API and treated as acceptance-harness defects.
- Action/decision: corrected the public scope shape and added real assertions for Evidence Reference/Association, REST and stdio MCP lineage, partial apply, authenticated actor/audit and secret non-persistence, cross-Project `GRAPH ?g`, Project-bound MCP success/denial and no-key startup. Existing controlled `UncertainRdfStore` regression is explicitly rerun for recovery/fence/original-key convergence rather than adding a production fault hook.
- Evidence: live harness `1 passed` on repeated execution; focused partial/recovery/MCP checks `8 passed`; service active and health succeeded after exact manager mode restoration.
- Outcome/next step: send the fixed stable worktree to the same tester for Round 2 retest.

### 2026-07-17T15:32:00+08:00 — independent test Round 2 — requirement_tester

- Context: repaired live harness passed its executable HTTP/stdin MCP path and the separate controlled recovery seam passed.
- Action/decision: FAIL / High acceptance gaps remain. `apply_partial` did not prove no Evidence/lineage residue for failed or blocked items. Modeling Batch rejects a supplied top-level `actor` with 422 although R-008 requires the field be ignored and replaced by the authenticated actor. Required authenticated Playwright live-contract cases remain skipped.
- Evidence: shared plan Round 2; live harness PASS; backend `689 passed, 4 skipped`, Postgres races `3 passed`, recovery seam `4 passed`, frontend `33 passed, 3 skipped`.
- Outcome/next step: repair the real actor compatibility contract, partial residue assertions, and cleaned authenticated browser scenarios before Round 3.

### 2026-07-17T15:48:00+08:00 — repair Cycle 3 development-ready — requirement_developer

- Context: Round 2 identified a real R-008 Modeling Batch compatibility gap and two missing acceptance/cleanup proofs.
- Action/decision: added optional untrusted `ModelingBatchSubmit.actor` compatibility input while retaining `ModelingAuthorizationContext` as the sole audit actor; successful forged-actor apply now verifies `key:*` audit ownership. The harness checks partial Evidence/Association and lineage residue. Live Playwright reads protected local credentials without display, has no mandatory skips, and cleans projects/graphs after each test.
- Evidence: backend Ruff; `test_modeling_batches_api.py test_security_audit.py` = `3 passed`; full-chain `1 passed`; `npx playwright test tests/live-contract.spec.ts` = `4 passed`.
- Outcome/next step: independent Round 3 must retest actor compatibility, partial residue and browser cleanup along with all earlier gates.

### 2026-07-17T16:05:00+08:00 — independent test Round 3 — requirement_tester

- Context: functional checks passed, including live HTTP/stdin MCP, actor compatibility, partial association, recovery seam, concurrency, documentation, build and zero-skip browser execution.
- Action/decision: FAIL / High. Cleanup audit found six owned `R006 Live/Rules` Projects from the browser suite; only one DELETE succeeded, while five rule-bearing Projects returned `409 Project could not be deleted`. The browser cleanup hook did not assert its deletion responses. The tester did not raw-delete dependent rows.
- Evidence: Round 3 in shared test plan; authenticated cleanup returned `[204, 409, 409, 409, 409, 409]`; full Playwright `36/36` passed but cannot prove cleanup.
- Outcome/next step: repair Project deletion dependency handling and make browser cleanup assert success; use the repaired supported deletion path to remove the five verified owned residues, then independently retest.

### 2026-07-17T16:22:00+08:00 — repair Cycle 4 development-ready — requirement_developer

- Context: rule-bearing browser test Projects exposed a supported deletion dependency cycle and unasserted cleanup failures.
- Action/decision: `ontology_crud` now removes linked rule definitions then rules before ontology/Project cascade; both Project and Ontology deletion are protected. Browser afterEach requires every owned Project DELETE to return 204 and every owned registered graph deletion to succeed. The shared plan explicitly makes the existing `UncertainRdfStore` recovery suite a companion gate.
- Evidence: new rule-cycle regression, recovery companion and API/security focused tests passed; live-contract `4 passed` with cleanup assertions; authenticated API deleted all five verified owned residues and a second query returned zero.
- Outcome/next step: independent Round 4 retests deletion, cleanup, recovery companion and all previous acceptance gates.

### 2026-07-17T15:25:34+08:00 — independent test Round 4 — requirement_tester

- Context: all prior High defects had been repaired; the tester reran the complete shared plan independently.
- Action/decision: PASS. The real HTTP/stdin MCP chain, recovery companion, rule-bearing Project deletion, concurrency, migration, documentation, browser cleanup and final runtime checks all met their gates.
- Evidence: backend `690 passed, 4 skipped`; PostgreSQL concurrency `3 passed`; frontend `36 passed` with zero skips; browser before/after audit unchanged at 10 `R006 Live/Rules` Projects and 3714 `/live-` Oxigraph graphs; the five prior residues are absent; service restart active, health/frontend successful, anonymous Project access 401 and manager write mode unset.
- Outcome/next step: perform final diff/health inspection and commit only delivery-owned files.

### 2026-07-17 — R-011 post-R-008 documentation refresh — main agent

- Context: R-008 is now implemented; the authoritative R-011 entry requires documentation to reflect protected business API and MCP boundaries rather than its original anonymous-runtime baseline.
- Action/decision: classify pre-R-008 statements in the R-011 design and test plan as historical evidence, replace current acceptance assertions with authenticated `401`/scope/Project-isolation expectations, and retain the original test records without rewriting their evidence.
- Evidence: `docs/requirements/requirements-v1.0.md` R-008/R-011 and `docs/architecture/overview.md` security boundary.
- Outcome/next step: R-011 documentation is aligned for the R-008 completion state; no product code, credentials, runtime configuration, or registry inventory was changed by this refresh.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | Runtime default `legacy_only` blocks R-004 RDF batch writes. | accepted-high | config/write guard and R-007 prior runtime plan | Added reversible `rdf_primary` setup, restart, verification and restore. |
| 1 | Recovery/partial apply, actor/secret, real Project-bound MCP and multi-Ontology scope were absent. | accepted-high | R-004, R-006 and R-008 acceptance criteria | Added deterministic scenarios and completion gates; re-review required. |
| 2 | Controlled RDF write runtime. | passed | revised setup/restore gate | No further plan change. |
| 2 | Recovery/partial, actor/secret, real MCP isolation and multi-Ontology scope. | passed | revised scenario matrices | No further plan change. |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | Uncommitted harness worktree | Added real full-chain acceptance harness; retained existing deterministic partial/recovery fault-seam coverage. | Ruff, py_compile, 53 focused tests passed. | development-ready; independent live run pending. |
| 2 | Round 1 tested harness | API scope-shape assumption and five missing acceptance assertions. | Independent live test failed; tester supplied exact coverage gaps. | confirmed High; repair required. |
| 3 | Cycle 2 repaired harness | Scope response fixed and missing assertions added. | Live harness 1 passed; partial/recovery/MCP focused 8 passed. | development-ready; independent retest required. |
| 4 | Round 2 tested harness | Partial residue proof missing; Modeling Batch actor compatibility contradicts R-008; required live browser tests skipped. | Independent review/real runtime. | confirmed High; repair required. |
| 5 | Cycle 3 repaired product/harness/browser checks | Actor compatibility, partial residue assertions and live browser cleanup added. | Focused backend, live harness and 4 live browser tests passed. | development-ready; independent retest required. |
| 6 | Round 3 tested product/harness/browser | Rule-bearing test Projects cannot be deleted; cleanup hook ignored failure. | Independent cleanup audit after otherwise green gates. | confirmed High; repair required. |
| 7 | Cycle 4 repaired deletion/cleanup | Rule definition/rule dependency cycle handled explicitly; cleanup assertions and recovery companion gate added. | Focused backend/browser checks and verified API cleanup. | development-ready; independent retest required. |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Uncommitted harness after Cycle 1 | FAIL / High | scope shape mismatch; no completed lineage/Evidence, partial/recovery, actor/audit, GRAPH isolation, Project-bound MCP proof; Playwright live cases skipped. | Shared test plan Round 1 and tester report. |

## Final verification

- Required checks: independent Round 4 passed backend, PostgreSQL, migration, docs, frontend and browser gates; `git diff --check` passed.
- Runtime/restart health: `ontology-platform.service` active; `/api/health` 200; frontend 200; anonymous `/api/projects` 401; temporary write mode restored unset.
- Documentation/status sync: reviewed design, shared plan and delivery record record the final contract and all failure/retest rounds.
- Cleanup: harness revokes temporary keys and deletes owned Projects; browser cleanup asserts Project 204 and graph deletion. The five Round 3 Rule residues were removed through the repaired authenticated API and independently confirmed absent.
- Residual risks and follow-ups: cross-store uncertainty is exercised by the existing controlled service-level `UncertainRdfStore` seam, not an injected production Oxigraph outage; normal HTTP/MCP/RDF paths run against real dependencies.

## Retrospective

- Scope or design deviations: R-010/Dify model-quality evaluation remains excluded as specified; the v1 platform protocol is the delivered scope.
- Rework and root causes: independent rounds exposed incomplete harness assertions, actor input incompatibility, restart readiness timing and a rule-definition deletion cycle; all were repaired and retained in the test history.
- What shortened or delayed delivery: real systemd restarts and cleanup audits surfaced defects early enough to avoid leaving test data or configuration drift.
- Reusable lessons: a passing browser test must assert cleanup, compatibility actor fields must be accepted but never trusted, and release gates must distinguish real-dependency flows from controlled fault seams.
