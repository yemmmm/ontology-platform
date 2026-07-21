# R1.1-006 轻量共享建模目录与分片协作 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-006
- Status: delivered; independent test Round 2 PASS
- Started: 2026-07-21T18:44:46+08:00
- Last updated: 2026-07-22T01:41:48+08:00
- Design: `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-test-plan.md`
- Delivery baseline: `e7c4dd4`; unrelated in-progress R1.1-005 fast-local changes are preserved
- Delivery commit: `Implement R1.1-006 shared modeling directory` (resolve hash with
  `git log -- docs/delivery/records/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-delivery-record.md`)

## Confirmed contract

- Current behavior: the main Agent coordinates a long artifact/event/handoff chain and must pass many
  references between fresh sessions, making modeling-quality iteration slow and error-prone.
- Target behavior: local sessions share one gitignored directory; workers receive only a run path and
  Work Unit ID, read complete task inputs themselves, and write bounded current results.
- In scope: repo-local directory contract, Work Unit splitting, same-machine multi-session reads and
  per-unit writes, local validation, Ontology-level merge/review, platform dry-run/apply and retrieval
  acceptance.
- Non-goals: platform storage/API/schema/UI, fine-grained security, version/audit history,
  cross-machine synchronization, dynamic scheduling, automated recovery, and productized governance.
- Acceptance summary: simpler reruns must not reduce source fidelity, model quality, platform dry-run
  correctness, or competency-question/retrieval quality.
- Refinement: the user explicitly set modeling and retrieval quality as the current priority,
  directed unrelated productization features to future scope, and confirmed that R1.1-006 remains
  independently end-to-end acceptable while R1.1-007 exclusively owns Profile/Harness policy,
  protected-write automation, capability Skills, and Agent wiring.

## Timeline

### 2026-07-21T18:44:46+08:00 — requirement redesign — user and main agent

- Context: the current complete workflow made every debug run and small change expensive; a proposed
  platform-grade shared collaboration space would add more permissions, versions, claims, and audit.
- Action/decision: add the repository-wide simple-first rule and redesign the requirement around a
  same-machine repo-local Shared Modeling Directory with preassigned Work Units. Keep only
  modeling/retrieval quality gates; mark productization capabilities as future.
- Evidence: `AGENTS.md`; `docs/requirements/requirements-v1.1.md`; current R1.1-002/R1.1-003/R1.1-005
  workflow and handoff documents.
- Outcome/next step: complete mandatory plan review; no product implementation begins in this turn.

### 2026-07-21T18:51:37+08:00 — plan review round 1 — plan reviewer and main agent

- Context: the first simple-first design named the shared files and quality flow but left several
  correctness contracts implicit.
- Action/decision: reviewer returned `REVISE` with three High findings. All were accepted: define
  minimum cross-file reference contracts; add one stable Ontology candidate whose review and Batch
  plan bind the same canonical hash; and prove Entity/Relation modeling above the current single-
  Batch capacity with deterministic ordered splitting.
- Evidence: revised requirement, design, and shared test plan linked above.
- Outcome/next step: request re-review of the minimal revisions; platform-hosted storage, audit,
  versions, claims, scheduling, and UI remain deferred.

### 2026-07-21T18:57:10+08:00 — plan review round 2 — plan reviewer and main agent

- Context: re-review checked only Critical/High risks to modeling quality, retrieval quality, and
  shared collaboration correctness.
- Action/decision: reviewer returned `PASS`; all three Round 1 High findings are closed and no new
  Critical/High finding remains. Canonical JSON/fingerprint repeatability and the intentionally
  non-atomic multi-Batch failure behavior were recorded as implementation notes and test cases.
- Evidence: final design status and shared test plan linked above.
- Outcome/next step: requirement redesign is ready for implementation; no product implementation
  was authorized or started in this turn.

### 2026-07-22T00:24:46+08:00 — R1.1-007 downstream-contract audit — main agent

- Context: R1.1-007 was refined after the original R1.1-006 plan review and now fixes the
  Local/Formal Profile boundary, continuous user dialogue, direct subagent-to-main clarification,
  business-change impact assessment, default local Harness behavior, automatic platform write
  contracts, and capability-Skill ownership.
- Action/decision: reopen the R1.1-006 design gate. Keep R1.1-006 focused on the Shared Modeling
  Directory, Work Unit current-state contract, deterministic validation/merge/Batch planning, and
  quality evidence; remove or qualify statements that let it choose an execution Profile, make
  Harness policy, own credentials/Build Session/Lease automation, persist a clarification mailbox,
  or automatically force remodeling after any business-input edit. The previous Round 2 PASS only
  covers the pre-R1.1-007 contract and cannot authorize implementation until the adjusted plan is
  reviewed again.
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-006/R1.1-007; the linked R1.1-006
  design/test plan; `docs/delivery/records/2026-07-21-r1-1-007-local-modeling-mode-delivery-record.md`;
  current `skills/ontology-builder/SKILL.md`, Modeling Batch schemas/settings, and compiler reference
  resolution.
- Outcome/next step: confirm whether R1.1-006 remains independently end-to-end acceptable before
  rewriting the design and shared test plan, then run a new plan-review round.

### 2026-07-22T00:34:52+08:00 — boundary confirmation and design revision — user and main agent

- Context: R1.1-006 could either stop at directory primitives and depend on R1.1-007 for every real
  platform check, or remain independently acceptable while keeping 007-only execution automation
  out of scope.
- Action/decision: user confirmed the recommended boundary. R1.1-006 remains independently
  end-to-end acceptable through the existing authenticated platform interface or a thin acceptance
  driver, while R1.1-007 exclusively owns Profile selection, Harness policy, credential and
  Build Session/Lease/workspace/idempotency automation, capability Skills, and Agent wiring. The
  design and shared test plan were revised accordingly.
- Evidence: linked requirement/design/test-plan documents and user confirmation in this turn.
- Outcome/next step: send the adjusted requirement, design, and test plan to a new independent plan
  review; do not start implementation from the historical Round 2 PASS.

### 2026-07-22T00:34:52+08:00 — risk probes — main agent

- Context: two pre-007 assumptions could produce incorrect reuse or invalid platform submissions.
- Action/decision: current Modeling Batch compilation resolves `depends_on` and item-output
  references only against Items in the same Batch, so the revised plan materializes later Batches
  from predecessor resource IDs/IRIs and forbids submitted cross-Batch `client_item_id` references.
  Separately, R1.1-007 requires affected subagents to assess business changes; the revised
  fingerprint rule therefore blocks stale results but does not automatically force remodeling.
- Evidence: `backend/app/services/modeling_batches.py` `_compile`/`_resolve_refs` behavior;
  `backend/app/api/schemas.py` Modeling Batch schemas; R1.1-007 confirmed contract and record.
- Outcome/next step: include both contracts in focused tests and plan review.

### 2026-07-22T00:40:08+08:00 — plan review round 3 — plan reviewer and main agent

- Context: the first R1.1-007-aligned plan was reviewed against the current immutable Modeling Batch
  implementation and live capacity checks.
- Action/decision: reviewer returned `REVISE` with two High findings and no Critical finding. Both
  are accepted. First, the plan now fixes `ontology_id` and stable `client_batch_id` per materialized
  Batch, hashes the platform-equivalent immutable content, captures the first returned platform
  `batch_id`, and requires dry-run/apply to reuse both Batch identities. Second, the planner and
  tests now cover inline-Evidence count and per-excerpt length in addition to item and request-byte
  limits; unsplittable violations block before submission.
- Evidence: current `ModelingBatchService._content`, `_get_or_create_batch`, `_check_capacity`, and
  `ModelingCommandHandlerRegistry.outputs_for`; revised design and test plan.
- Outcome/next step: send the two accepted revisions to the same reviewer for re-review.

### 2026-07-22T00:41:14+08:00 — plan review round 4 — plan reviewer and main agent

- Context: re-review checked the two accepted Round 3 High revisions and looked for new
  Critical/High regressions.
- Action/decision: reviewer returned `PASS`. Stable Ontology/client/platform Batch identity plus
  platform-equivalent immutable-content hashing closes the dry-run/apply identity gap. All four
  current capacity contracts and splittable-versus-blocking behavior close the capacity gap. No new
  Critical/High finding was reported, and the R1.1-006/R1.1-007 responsibility boundary remains
  intact.
- Evidence: final requirement, design, and shared test plan linked above; reviewer record-ready PASS.
- Outcome/next step: the adjusted R1.1-006 design is ready for a later implementation handoff; this
  turn closes documentation and plan review only.

### 2026-07-22T00:43:23+08:00 — development handoff freeze — main agent

- Context: the user authorized continuation from the reviewed design into complete requirement
  delivery. Commit `c8f3495` is a clean, stable baseline; Round 4 plan review is PASS with every
  accepted High finding closed.
- Action/decision: freeze R1.1-006 implementation to the linked design and shared test plan. The
  developer may add only repo-local shared-directory commands/modules, focused tests, and directly
  necessary documentation. Backend tables/routes, frontend, Profile/Harness policy, credentials and
  protected-write automation, capability Skills, and Agent wiring remain R1.1-007 or future scope.
- Evidence: `git status --short --branch` clean at `c8f3495`; review disposition table above.
- Outcome/next step: hand off to `requirement_developer`; require GitNexus impact before editing any
  existing symbol, focused and full `.codex` unit tests, Ruff checks, diff checks, and an explicit
  development-ready signal. Real multi-session and authenticated platform integration remain part
  of the stable independent-test handoff.

### 2026-07-22T01:11:55+08:00 — development ready — requirement developer and main agent

- Context: the first developer execution completed repository/design analysis but produced no file
  changes or blocker after repeated bounded follow-ups, so the main agent replaced that execution
  while preserving the frozen scope. The replacement developer changed no existing function,
  class, or method and therefore had no existing-symbol impact gate.
- Action/decision: add one repo-local implementation module, one focused unittest module, and one
  operator runbook. The implementation covers initialize/inspect/validate/reset, explicit semantic
  `no_change` rebind, deterministic merge/hash/review gates, four-limit Batch planning,
  cross-Batch materialization, stable client/platform Batch identity, response binding, and
  retrieval-verification validation. It does not implement any R1.1-007-owned capability.
- Evidence: `.codex/shared_modeling_directory.py` SHA-256
  `86a3b612b047cba8df4954ed12402d0d8865986dac765e7f8e0371a5a25fb1f6`;
  `.codex/tests/test_shared_modeling_directory.py` SHA-256
  `1b02a4bed1c2baae8d15817afe61806d6f9c5b51c62d52e0d569c84776e20597`;
  `.codex/shared-modeling-directory.md` SHA-256
  `d686521d432598678430db3226d5efb223525d0098586f0263d1af89e3aff044`.
- Outcome/next step: development-ready at the uncommitted three-file state. Focused 13 tests and
  full `.codex` 81 tests passed; Ruff check/format and diff checks passed. One pre-existing
  `ResourceWarning` remained non-failing. Start independent testing only against this stable state.

### 2026-07-22T01:33:35+08:00 — independent test Round 1 and repair handoff — tester and main agent

- Context: independent testing exercised real Agent replacement and the authenticated live platform
  after two acceptance-fixture corrections were safely blocked before apply. A reversible
  `rdf_primary` runtime override was required because the restored local default is `legacy_only`.
- Action/decision: Round 1 is `FAIL` with one confirmed High defect,
  `R1.1-006-IT-001`. The main agent accepts the severity: `validate_verification` accepted
  `verdict=PASS` when a passed check contained only a CQ ID/status and no executed query or
  structured result evidence. This can falsely close an unexecuted retrieval acceptance and is
  directly within R1.1-006 completion scope. Route only this defect to the developer; preserve the
  successful real-platform evidence and failed Round 1 history.
- Evidence: shared test plan Round 1; real `[100, 100, 5]` Batch sequence, 409 stale-workspace
  recovery with 99-Entity prefix retained, final SPARQL `200` Entities/`3` Relations, Context Query
  `matched`, and exact cleanup/runtime-restoration results recorded there.
- Outcome/next step: add focused missing/malformed/valid verification-evidence regressions, require
  bounded executed-check evidence for PASS, return a new development-ready state, then retest the
  defect plus affected/full/runtime gates in Round 2.

### 2026-07-22T01:37:27+08:00 — defect repair ready — requirement developer and main agent

- Context: the repair was limited to confirmed High `R1.1-006-IT-001`. GitNexus could not resolve
  the symbol because the implementation file is still new/untracked, so the developer recorded
  risk `UNKNOWN` and inspected all direct same-file/CLI/test call sites instead of claiming a false
  safe impact result.
- Action/decision: a passed verification check now requires a bounded non-empty query or check
  description plus structured non-empty result evidence, or an explicit valid empty-result
  assertion with `expected=true`, `observed_count=0`, and a bounded assertion. Missing, malformed,
  and contradictory evidence is rejected. The runbook and focused regressions were updated.
- Evidence: implementation SHA-256
  `7a37bdb9148f0c8bece2af3886f2e6a612643e6fad7d4fd3bddce97b5ef63fa1`;
  focused-test SHA-256
  `e43f72929c01e2cfe831f4c7ea7d5a4f94d86b3dd7dee95f82e6fbbcb6a058a3`;
  runbook SHA-256
  `1f063db211379f524dc18ac78d68f24035fb89cd422bb70f495550b2689e1c2d`.
- Outcome/next step: DEVELOPMENT READY FOR RETEST. Focused 13/13, full `.codex` 81/81, existing
  valid live verification recheck, Ruff, format, and diff checks passed; send the stable state back
  to the independent tester for Round 2.

### 2026-07-22T01:41:48+08:00 — independent test Round 2 and delivery close — tester and main agent

- Context: Round 2 retested the exact verification-evidence defect and the stable repaired files,
  while preserving Round 1's expensive live platform evidence because the repair did not touch
  candidate hashing, Batch planning/materialization, binding, or submission behavior.
- Action/decision: accept Round 2 `PASS`. Missing query/check description, missing structured
  result, malformed result shape, and contradictory empty-result assertions now block; valid
  non-empty evidence and a contract-valid explicit empty result pass. No Critical/High defect or
  unexecuted R1.1-006 completion gate remains.
- Evidence: shared test plan Round 2; focused 13/13 and full `.codex` 81/81; Ruff and diff checks;
  preserved live verification revalidated under the repaired contract; all four acceptance run
  identities at zero Project, zero Batch, and zero matching RDF graph; systemd active, backend and
  frontend HTTP 200, product write mode restored to `legacy_only` with no manager override.
- Outcome/next step: R1.1-006 is delivered. Synchronize requirement/design/test status, run final
  repository checks including GitNexus change detection, and create the delivery commit.

## Review disposition

The Round 2 PASS remains historical evidence for the original scope. R1.1-007 introduced a newer
downstream contract, so a fresh review is required after realignment.

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | High: named files did not yet guarantee complete Source/Coverage/CQ/dependency/output references | Accepted | Minimum data-contract table and cross-scope validator scenarios | Local validator contract expanded; no platform service added |
| 1 | High: review/dry-run/apply had no single stable merged Ontology target | Accepted | `ontologies/<ontology-id>/candidate.json` plus canonical-hash-bound review and Batch plan | Semantic edits invalidate current review; no version chain added |
| 1 | High: design and tests did not prove hundreds of Entity/Relation items under live Batch limits | Accepted | Live settings-based deterministic splitting and >200 Entity test scenario | Ordered multi-Batch quality gate added; no scheduler added |
| 2 | Re-review of the three accepted High findings | PASS; all closed | Plan reviewer checked revised requirement/design/test plan | No new Critical/High; implementation may begin in a later turn |
| 3 | High: materialized hash did not bind Ontology/stable client Batch identity or prove the same platform Batch was applied | Accepted | Stable `ontology_id`/`client_batch_id`, platform-equivalent immutable-content hash, and returned `batch_id` assertions | Design and tests revised; re-review required |
| 3 | High: planner omitted inline-Evidence count and per-excerpt capacity limits enforced by the platform | Accepted | All four current capacity settings and pre-submit boundary cases | Design and tests revised; re-review required |
| 4 | Re-review of both accepted Round 3 High findings | PASS; both closed | Reviewer verified Batch identity/hash and all four capacity contracts against current implementation | No unresolved Critical/High; implementation may begin in a later turn |

## Development and defect history

Implementation completed through the following development and repair cycles.

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `c8f3495` plus the three SHA-256-pinned uncommitted `.codex` files | Initial R1.1-006 repo-local implementation | 13 focused and 81 full `.codex` tests; Ruff check/format; diff checks; GitNexus low risk/0 mapped symbols | DEVELOPMENT READY; real Agent/platform acceptance deferred to independent test |
| 2 | Round 1 stable state | Confirmed High `R1.1-006-IT-001`: verification PASS accepted without executed query/result evidence | Independent minimal failing check in shared plan Round 1 | Repair handed to developer; implementation remains incomplete |
| 3 | Three repaired `.codex` files pinned by the 2026-07-22T01:37:27 hashes | Require executed query/result evidence or explicit valid empty-result assertion | 13 focused and 81 full `.codex` tests; prior valid live artifact recheck; Ruff/format/diff | DEVELOPMENT READY FOR RETEST |
| 4 | Same repaired files | No product change; independent defect retest and full acceptance closure | Shared test plan Round 2; focused 13/13, full 81/81, preserved real acceptance, cleanup/runtime checks | DELIVERED |

## Independent test rounds

Independent testing completed in two rounds.

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 | `c8f3495` plus the three pinned `.codex` files | FAIL | High `R1.1-006-IT-001`; real clarification-return case unforced; R1.1-007 intentionally out of scope | Shared test plan Round 1: 13/13 focused, 81/81 full, real Agent replacement, live 205-item multi-Batch/recovery/retrieval, zero residual DB/Graph data, restored healthy runtime |
| 2 | Three files pinned by the 2026-07-22T01:37:27 hashes | PASS | No residual Critical/High; real clarification return remained unnecessary in the accepted run; R1.1-007 remains downstream | Exact defect matrix passed; 13/13 focused, 81/81 full, preserved live verification passed stricter contract, zero platform residuals, healthy restored runtime |

## Final verification

- Required checks: focused 13/13, full `.codex` 81/81, Ruff check/format, `git diff --check`, and
  GitNexus `detect_changes` before commit.
- Runtime/restart health: no backend/frontend product code changed, so no delivery restart is
  required. Independent testing restored the temporary acceptance override and verified systemd
  active, backend/frontend HTTP 200, and `product_write_mode=legacy_only`.
- Documentation/status sync: requirement, design, shared test plan, runbook, and this delivery
  record are aligned to delivered / independent test Round 2 PASS.
- Cleanup: all four live acceptance identities have zero Project, Modeling Batch, and matching RDF
  graph residuals. The bounded gitignored run directory remains local test evidence.
- Residual risks and follow-ups: multi-Batch apply intentionally preserves an already applied valid
  prefix instead of promising atomic rollback. Profile/Harness/credential/Agent automation remains
  R1.1-007 scope, and the real clarification-return branch was not needed by the accepted run.

## Retrospective

- Scope or design deviations: the delivered implementation stayed repo-local and did not absorb any
  R1.1-007 Profile/Harness/credential/Agent responsibility.
- Rework and root causes: the earlier design optimized future productization before proving modeling
  and retrieval benefit; Round 1 then exposed that file completeness alone could falsely represent
  retrieval acceptance.
- What shortened or delayed delivery: reusing existing platform dry-run/apply/query capabilities
  avoided backend work; the real 205-item run revealed both the expected `legacy_only` boundary and
  the intended non-atomic stale-workspace recovery behavior.
- Reusable lessons: make the main Agent a coordinator, not a courier; bind acceptance to observable
  query results, not status labels; and do not productize the coordination channel before the
  quality experiment proves value.
