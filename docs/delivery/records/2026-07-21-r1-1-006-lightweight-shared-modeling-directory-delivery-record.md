# R1.1-006 轻量共享建模目录与分片协作 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-006
- Status: in-progress (design realignment against R1.1-007)
- Started: 2026-07-21T18:44:46+08:00
- Last updated: 2026-07-22T00:41:14+08:00
- Design: `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-test-plan.md`
- Delivery baseline: `e7c4dd4`; unrelated in-progress R1.1-005 fast-local changes are preserved
- Delivery commit: `Adjust R1.1-006 design for execution profiles` (resolve hash with
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

No implementation cycle has started.

## Independent test rounds

No independent test round has started.

## Final verification

- Required checks: document consistency and `git diff --check` for this design turn.
- Runtime/restart health: not required for documentation-only redesign.
- Documentation/status sync: complete for the redesign; implementation remains pending.
- Cleanup: none.
- Residual risks and follow-ups: first implementation and real multi-session quality run remain;
  multi-Batch apply is intentionally not atomic, and deterministic hash behavior needs implementation
  tests.

## Retrospective

- Scope or design deviations: replaced the platform-grade shared-space proposal with a repo-local
  current-state directory.
- Rework and root causes: the earlier design optimized future productization before proving modeling
  and retrieval benefit.
- What shortened or delayed delivery: reusing existing platform dry-run/apply/query capabilities
  avoids backend work.
- Reusable lessons: make the main Agent a coordinator, not a courier, but do not productize the
  coordination channel before the quality experiment proves value.
