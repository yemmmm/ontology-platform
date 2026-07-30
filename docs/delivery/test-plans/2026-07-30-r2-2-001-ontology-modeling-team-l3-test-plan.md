# R2.2-001 Ontology Modeling Team L3 Shared Test Plan

## Status

- Contract: `docs/requirements/requirements-v2.2.md`, R2.2-001 L3
- Design:
  `docs/delivery/designs/2026-07-30-r2-2-001-ontology-modeling-team-l3-design.md`
- Current state: recovery plan pending review; prior transcript-only pause diagnosis invalidated
- Test owner: independent Requirement Tester appends rounds to this document
- Start budget: at most five fresh L3 team starts; three consumed and two newly authorized

## Completion rule

One real attempt must pass the complete semantic, collaboration, platform, isolation, evidence, and
cleanup gate. Earlier failed starts remain recorded. A completed model with a semantic failure ends
L3 as `modeling-quality` and prohibits another modeling attempt.

No new Judge, Consumer, mutation, failure-injection framework, or dedicated acceptance program may
be created or used. Automated tests may validate launcher mechanics; semantic acceptance is direct
inspection of retained Agent and platform evidence.

## Preconditions

1. Worktree baseline and existing unrelated changes are recorded.
2. M1 offline scenario and L1 launcher regressions pass.
3. Resident `ontology-platform.service`, backend `8001`, and frontend `5173` are healthy.
4. PostgreSQL, Oxigraph, bubblewrap, Codex, and the isolated `rdf_primary` port are available.
5. The Agent-visible manifest is hash-valid and contains no tester-only path, answer, ontology,
   Batch, historical run, query answer, credential, or hidden acceptance contract.
6. The tester-only answer contract is frozen before the first team starts.
7. Attempt ledger is append-only; the versioned policy records three consumed starts, a maximum of
   five, and exactly two newly authorized starts.
8. The execution-phase `preparation_started_at` timer is running; the first real modeling delegation
   must occur within 20 minutes or preparation stops and the path is reduced/reported.
9. A uniquely owned, business-empty probe scope has passed one real managed reasoning run inside the
   same isolated REST namespace, and that probe scope has been deleted.

## Automated launcher and regression cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| L3-01 | Verify manifest and staged mounts | Exact hashes pass; only Agent-visible files are staged |
| L3-02 | Reject tester-only/history/repository access | Isolation probes cannot read forbidden paths |
| L3-03 | Enforce fresh role Sessions | Coordinator, modeler, and protocol identities are distinct and non-forked as specified |
| L3-04 | Enforce role MCP boundary | Coordinator/modeler have no platform MCP/env; protocol is the only platform caller |
| L3-05 | Enforce one pending question | A second unanswered question or answer without a question is rejected |
| L3-06 | Preserve exact answer/resume | Answer hash equals frozen entry; same coordinator Session resumes |
| L3-07 | Protect dispatch integrity | Candidate/dispatch canonical hash drift fails closed |
| L3-08 | Sanitize protocol namespace | `.env`, long-term keys, repository and tester-only are absent |
| L3-09 | Prove no-key rejection | Protocol MCP authentication fails before the temporary key is injected |
| L3-10 | Enforce protocol allowlist | Unexpected platform tools, callers, scopes, or cross-Project resources fail audit |
| L3-11 | Reconcile immutable Batch facts | Platform detail proves identical validated dry-run/applied Items and advancing workspace |
| L3-12 | Reconcile negative Shape evidence | Invalid Batch is validation-failed, has blocking SHACL evidence, and is never applied |
| L3-13 | Reconcile validation/reasoning/query | Platform run IDs and current graph-set scope match the owned Ontology |
| L3-14 | Preserve failure category/progress | First response, progress, terminal cause, and category remain observable |
| L3-15 | Enforce start budget | Starts six and above and any retry after semantic failure are rejected before resources are created |
| L3-16 | Cleanup key/Project ownership | Both ephemeral keys are revoked and only the exact owned Project is deleted |
| L3-17 | Atomic evidence publication | Final receipts are repeatable, atomic, protected, and failure-safe |
| L3-18 | L0/L1/M1 regression | Existing focused suites remain PASS |
| L3-18A | Deterministic mechanics helper | Stable IDs, schema validation, canonical files, exact Batch replay, revisions, lease renewal and checkpoint envelopes are deterministic; semantic Items are never synthesized |
| L3-18B | Isolated managed-reasoning preflight | Namespace path/config executes a real managed reasoning run and the separate probe scope is cleaned |
| L3-18C | First-attempt clock | Ledger rejects/halts preparation when no real Modeling Agent delegation occurs within 20 minutes |
| L3-18D | Reuse accepted raw rollout audit | Retained h/i pass parent/role/fork verification; retained g proves a linked child without `agent_type` is rejected; the outer transcript alone cannot produce a false failure or false child |
| L3-18E | Authorized recovery budget | Policy permits only starts four and five, records the user authorization, and rejects a sixth before run-root/probe/key creation |

## Real attempt acceptance cases

### Team and interaction

| ID | Check | PASS condition |
| --- | --- | --- |
| L3-19 | Fresh coordinator | New non-resumed coordinator has no Delivery history or hidden inputs |
| L3-20 | Three-role execution | Distinct coordinator, Modeling Agent, and Protocol Agent events exist |
| L3-21 | Semantic ownership | Modeling Agent forms the candidate; coordinator approves/routes; Protocol converts/calls |
| L3-22 | Conditional release | Every released answer follows a grounded source-citing consequential question |
| L3-23 | One-at-a-time continuation | One pending question at a time; exact answer; same coordinator Session resumes |
| L3-24 | Explicit unknown decision | “Cannot confirm” is not defaulted and affects the approved candidate |

### Platform application

| ID | Check | PASS condition |
| --- | --- | --- |
| L3-25 | Fresh scope | New Project, Ontology, Build Session, Lease, run root and Session IDs |
| L3-26 | Protocol-only writes | All write MCP calls belong to Protocol Agent; no Host-authored Modeling Items |
| L3-27 | Immutable apply | Principal and instance candidates use validated dry-run then exact atomic apply |
| L3-28 | Workspace transition | Authoritative before/after workspace versions differ and match Batch facts |
| L3-29 | Negative constraint | Applied Shape rejects a separate invalid candidate; invalid Batch is not applied |
| L3-30 | Build Session closure | Session completed, checkpoint linked, Lease released |

### Semantic quality and retrieval

| ID | Check | PASS condition |
| --- | --- | --- |
| L3-31 | Validation | Managed final run reports `conforms=true` for the owned graph set |
| L3-32 | Reasoning | Managed run reports succeeded/current and `consistent=true` |
| L3-33 | Published C→B→A path | Complete non-truncated governed evidence contains C deletion, C→B invocation/binding/use, B output, B→A invocation/binding/use and relevant published Versions |
| L3-34 | Draft exclusion | Current Draft change is queryable but not part of the active Latest published path |
| L3-35 | Explicit unknown | Missing-score behavior is a named, queryable unknown with source/rationale; no invented behavior |
| L3-36 | Platform neutrality | Evidence uses generic platform facts/query surfaces; no Dify-specific production behavior |

### Evidence, cleanup, and runtime

| ID | Check | PASS condition |
| --- | --- | --- |
| L3-37 | Event/receipt traceability | Inputs, role events, MCP calls, Batches, Session/Lease, validation, reasoning and query are cross-linked |
| L3-38 | Error routing | Any naturally occurring error is routed per role; absence of a natural error is accepted |
| L3-39 | Credential closure | Protocol model key revoked before Project deletion; host-admin key separately revoked |
| L3-40 | Resource cleanup | Exact run-owned Project is deleted and confirmed absent; no ambiguous cleanup |
| L3-41 | Runtime health | Isolated `rdf_primary` exits; resident systemd service, `8001`, and `5173` are healthy |
| L3-42 | Independent acceptance | Requirement Tester directly inspects raw evidence and records PASS with no acceptance executable |
| L3-43 | Preparation budget | `first_modeling_started_at - preparation_started_at <= 20 minutes` |

## Failure and boundary checks

- Manifest/hash/mount drift: fail before Agent startup.
- Missing or leaked credential: fail closed, revoke known keys, and classify accurately.
- Coordinator/modeler platform call: collaboration/routing failure.
- Protocol mechanical error: allow only Protocol self-correction or state re-read without semantic
  change; preserve before/after events.
- Scope/workspace/Batch-content conflict: stop Protocol retry and route to coordinator.
- Semantic candidate conflict: return to Modeling Agent; Delivery does not repair it.
- Unsupported question: do not release a hidden answer; record and route.
- Provider/Agent terminal error: stop promptly after retained partial evidence; do not wait for one
  global timeout.
- Cleanup uncertainty: report cleanup failure and do not delete any non-uniquely-owned resource.
- Completed-model semantic failure: record `modeling-quality`, stop L3, and prohibit another start.
- Missed first-attempt clock: stop preparation, report time consumers, reduce to the smallest
  executable L1-derived path, and do not continue without user authorization.

## Required commands

Exact scenario command names may be finalized during reviewed implementation, but closure requires:

```bash
uv run --directory backend python -m unittest discover \
  ../docs/evaluation-scenarios/ontology-modeling-team-l3/tests
uv run --directory backend python -m unittest discover \
  ../docs/evaluation-scenarios/ontology-modeling-team-l1/tests
uv run --directory backend python \
  ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py
uv run --directory backend ruff check \
  ../docs/evaluation-scenarios/ontology-modeling-team-l3
git diff --check
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

If backend/frontend product code changes after an approved scope revision, run their complete
repository-required suites and restart/verify `ontology-platform.service` before acceptance.

## Attempt ledger

| Start | Run ID | Fresh scope | Category/result | Cleanup | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | `l3-real-20260730g` | fresh coordinator + default-role child; pending question | `collaboration/routing`; reason corrected to missing configured role | probe Project/key/runtime cleaned | raw coordinator/child rollout + pending question |
| 2 | `l3-real-20260730h` | fresh coordinator + Modeling Agent child; pending question | harness misclassification; superseded | probe Project/key/runtime cleaned | raw coordinator/child rollout + pending question |
| 3 | `l3-real-20260730i` | fresh coordinator + Modeling Agent child; pending question | harness misclassification; superseded | probe Project/key/runtime cleaned | raw coordinator/child rollout + pending question |
| 4 | reserved after offline PASS | must be wholly fresh | pending | required | raw rollout + platform evidence |
| 5 | reserved only after repairable start-4 failure | must be wholly fresh | pending | required | raw rollout + platform evidence |

Execution-phase timing:

- `preparation_started_at`: set at reviewed developer handoff
- `first_modeling_started_at`: absent from the old ledger because the verifier read the wrong
  evidence source; retained raw rollouts prove the child executions occurred
- Recovery clock: reset only at the reviewed developer handoff immediately preceding start 4

### Recovery correction — 2026-07-30

- Direct raw-evidence review invalidates the premise of Independent Rounds 1–5 that g/h/i had no
  child. Those rounds remain append-only historical test records. Run g remains a
  `collaboration/routing` failure because its linked child has no configured Modeling Agent role;
  h/i are valid role/fork positive cases. The three-run aggregate pause conclusion is superseded.
- The repair must pass L3-18D and L3-18E plus all existing focused regressions before any new live
  start. No semantic acceptance criterion, source pack, answer, prompt, or cleanup criterion is
  relaxed.
- User authorization adds exactly two opportunities. Start 5 is not automatic after a completed
  semantic failure.

## Independent test rounds

### Independent Round 1 — 2026-07-30T12:59:24+08:00

- Stable worktree/state: uncommitted reviewed L3 scenario plus the Delivery-owned record; no
  backend, frontend, migration, or existing L0/L1/M1 scenario change. `git diff --check` passed.
  This round did not edit product/scenario code or the Delivery record.
- Overall result: **FAIL** for the claimed stable `PAUSED / NOT PASSED` outcome. This is not an L3
  completion PASS. The retained evidence proves three incomplete fresh coordinator launches, but
  does not prove the required three-Agent collaboration, a real Modeling Agent start, correct
  failure classification, or an enforced global exhausted-start pause.
- Executed automated/regression checks:
  - `uv run --directory backend python -m unittest discover ../docs/evaluation-scenarios/ontology-modeling-team-l3/tests` — PASS, 14 tests.
  - `uv run --directory backend python -m unittest discover ../docs/evaluation-scenarios/ontology-modeling-team-l1/tests` — PASS, 15 tests.
  - `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` — PASS, 13 tests.
  - `uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l3` — PASS.
  - `git diff --check` — PASS. `ontology-platform.service` active; `8001/api/health` and `5173/`
    both returned success.
- Direct evidence review — runs `l3-real-20260730g`, `h`, and `i`:
  - All three manifest stages and business-empty isolated managed-reasoning preflights passed;
    each result was `succeeded`/`consistent=true`. Each preflight cleanup receipt records its exact
    probe `project_id`, `project_deleted=true`, `host_admin_revoked=true`, and
    `isolated_runtime_exited=true`. No isolated L3 REST/bwrap process remained.
  - Their ledgers record 591 s, 740 s, and 982 s respectively from
    `preparation_started_at=2026-07-30T12:37:43+08:00`, all under 20 minutes. This is only a
    launcher timestamp: it was written before `launch_coordinator`, so it is not evidence that a
    real Modeling Agent delegation occurred.
  - Coordinator identities exist (`019fb159-6a93-7163-b3df-e50f4bbd6122`,
    `019fb15b-b257-7b73-8156-c375a92bcf3e`, and
    `019fb15f-6436-7ea1-8569-71f9366b9347`). Every retained `collab_tool_call` is `wait` with
    `receiver_thread_ids=[]`; no `spawn_agent` event, Modeling Agent child identity, Protocol
    Agent identity, or Protocol MCP receipt exists. The coordinator instead wrote one pending
    question in each run. Thus L3-03, L3-20, and L3-21 are FAIL, not merely unobserved.
  - The absence of a business Project/Ontology/Build Session/Lease/model key, Modeling Batch,
    platform write, or Protocol process is expected from the incomplete launch and avoids business
    resource leakage. It is not positive evidence for L3-25--L3-40. Only the three preflight
    admin-key/project cleanups can be directly verified.
- Defects:
  1. **High — incorrect terminal category/state (L3-14, L3-38).** Raw events show a
     collaboration/routing failure: required Modeling Agent delegation never happened. Yet every
     `audit/state.json` records `state=INCONCLUSIVE` and
     `category=runtime/infrastructure`; `run_l3.py` catches every exception and assigns that
     category. Expected: preserve `collaboration/routing` and terminal paused/not-passed evidence
     after the third exhausted attempt. Actual: category is wrong and no run state is `PAUSED` or
     `NOT PASSED`. Evidence: all three `audit/coordinator.jsonl` and `audit/state.json` files.
  2. **High — start budget and first-modeling clock are not enforced/proven globally (L3-15,
     L3-18C, L3-43).** `start_modeling` reads only the run-local
     `runtime/runs/<run-id>/attempts.jsonl`, and `run()` records `modeling_started` before
     `launch_coordinator`. A fourth distinct run ID would have an empty local ledger, while these
     three entries do not represent a real child delegation. Expected: one shared append-only
     attempt ledger; record the timestamp only after an evidenced child identity; reject any
     fourth run. Actual: 14 unit tests only prove the limit within a supplied single ledger.
     Evidence: `run_l3.py:186-196, 414-433` and raw ledgers above.
  3. **High — role-specific Protocol handoff is absent/inconsistent (L3-04, L3-26).** The visible
     public protocol requires `/opt/mechanics-contract.json`, but it is neither staged by the
     manifest nor emitted by the launcher; the launcher ends immediately after coordinator output
     and never creates the separate Protocol namespace/key/Agent. In addition, runs `h` and `i`
     show the coordinator reading `/opt/public-protocol.md`, although the design says only the
     Protocol Agent receives it at dispatch. Expected: separate, role-scoped Protocol handoff with
     the required mechanics artifact and auditable no-key/key/write lifecycle. Actual: none.
     Evidence: `agent-input/public-protocol.md`, manifest/staged-file receipts,
     `run_l3.py:427-430`, and `h`/`i` coordinator JSONL.
- Unexecuted / not passed because no real Modeling Agent or Protocol Agent existed: L3-05--L3-13
  beyond unit mechanics, L3-16--L3-18C beyond the limited offline tests, L3-19 and L3-22--L3-43
  except the preflight/runtime-health observations stated above. In particular, no answer/resume,
  approved candidate/dispatch, Project/Ontology scope, key lifecycle, Batch, validation, reasoning
  of business data, governed C->B->A query, draft exclusion, explicit unknown, or full cleanup can
  be accepted.
- Residual risk: direct evidence supports only safe preflight cleanup and coordinator isolation;
  it cannot establish semantic quality or platform write correctness. The input-manifest hash also
  changed from `30e82c...b54` in `g`/`h` to `5a5d51...2e4` in `i`, so the third launch was not
  evidence over the identical frozen Agent-visible input pack.
- Recommendation: have the Requirement Developer correct the child-start/role handoff, shared
  budget/timing ledger, and classification/pause evidence; obtain fresh plan review and explicit
  user authorization before any new start budget. Then reuse this plan for the next independent
  round, first retesting these three defects and the affected cleanup/role boundaries.

### Independent Round 2 — 2026-07-30T13:08:14+08:00

- Scope and safety: offline retest only. No coordinator, Modeling Agent, Protocol Agent, managed
  reasoning probe, business Project, temporary key, Batch, or platform write was started. Round 1
  and the Delivery-owned record were not altered.
- Overall result: **FAIL** for the full claim that the paused state is authoritatively classified
  `collaboration/routing`; **PASS** for mechanical enforcement that L3 is globally
  `PAUSED / NOT_PASSED` after the three preserved starts. L3 itself remains **NOT PASSED** and is
  not an L3 completion PASS.
- Re-executed checks:
  - L3 launcher suite — PASS, 19 tests:
    `uv run --directory backend python -m unittest discover ../docs/evaluation-scenarios/ontology-modeling-team-l3/tests`.
  - L1 focused regression — PASS, 15 tests; M1 scenario — PASS, 13 tests.
  - L3 Ruff, `git diff --check`, active `ontology-platform.service`, `8001/api/health`, and `5173/`
    — PASS.
- Fixed offline mechanics verified:
  - `runtime/attempt-ledger.jsonl` is locked/append-only and has exactly the preserved starts
    `l3-real-20260730g`, `h`, and `i`; `runtime/state.json` reports
    `state=PAUSED`, `outcome=NOT_PASSED`, `team_starts=3`. The `run()` control flow reserves this
    global start before it creates a run root, stages inputs, runs a probe, or creates credentials.
    The new tests reject a fourth distinct run ID and a post-deadline start.
  - `first_modeling_started_at` is now written only by `record_modeling_delegation` after
    `verified_modeling_child` finds exactly one `spawn_agent` receiver identity. The historical
    starts are correctly preserved only as `historical_coordinator_started`, not as verified
    modeling delegations.
  - Role staging now excludes `public-protocol.md` from the coordinator pack and provides it only
    with the Protocol pack, together with the semantic-free mechanics and credential-lifecycle
    contracts. Protocol configuration/prompt requires the no-key rejection before an ephemeral
    project-scoped model key is injected, and focused tests verify no plaintext key is staged.
- Preserved-evidence recheck: `g`/`h`/`i` still have zero `spawn_agent` events and zero nonempty
  child receiver lists, so no business scope/write occurred. All three independent preflight
  receipts still prove their exact probe Project deletion, host-admin-key revocation and isolated
  runtime exit. No isolated L3 runtime remains. These facts support pausing rather than any
  semantic acceptance.
- Remaining defect:
  1. **High — historical terminal classification is not authoritative (L3-14, L3-38).** The new
     global `runtime/state.json` has no failure category, and each immutable raw
     `runtime/runs/l3-real-20260730{g,h,i}/audit/state.json` still says
     `category=runtime/infrastructure` and `state=INCONCLUSIVE`, despite raw JSONL proving the
     failure is missing child delegation (`collaboration/routing`). Expected: an append-only
     canonical historical classification/terminal record that links each retained run to
     `collaboration/routing` and the aggregate `PAUSED / NOT_PASSED` conclusion without rewriting
     raw evidence. Actual: the global ledger records only `historical_coordinator_started`; the
     corrected category exists only as prospective code behavior/documentation. Evidence:
     `runtime/attempt-ledger.jsonl`, `runtime/state.json`, and the three raw state/transcript files.
- Still unexecuted because the three-start budget remains exhausted: all real semantic and platform
  cases L3-19--L3-43 (apart from preserved preflight cleanup/runtime health), including answer
  resume, three-Agent collaboration, protocol key lifecycle, Batch apply, validation/reasoning of
  business data, C->B->A query, Draft exclusion and explicit unknown. No new run may be used to
  convert these to PASS.
- Recommendation: Requirement Developer should add only an append-only canonical classification
  record for the three preserved failures, then rerun this same offline round. Any future real L3
  attempt still requires plan review and explicit user authorization for a new start budget.

### Independent Round 3 — 2026-07-30T13:12:38+08:00

- Scope and safety: offline historical-evidence retest only. No coordinator/team/probe, Project,
  key, Batch, platform write, or new run root was created; raw `g`/`h`/`i` evidence was read only.
  Earlier rounds remain unchanged.
- Overall result: **PASS** — the stable paused state is now trustworthy as
  `PAUSED / NOT_PASSED / collaboration/routing`. This is a PASS for the exhausted-start terminal
  state only, not an L3 semantic-completion PASS; L3 remains **NOT PASSED**.
- Exact authoritative evidence:
  - `runtime/historical-classification-ledger.jsonl` contains exactly three append-only corrections
    for `l3-real-20260730g`, `h`, and `i` — no extra/missing run. Each preserves the original
    `INCONCLUSIVE / runtime/infrastructure` observation and adds authoritative
    `PAUSED / NOT_PASSED / collaboration/routing`, with the reason that no verified Modeling Agent
    child Session/delegation existed.
  - For each run, independent `sha256sum` values for the immutable raw `audit/state.json` and
    `audit/coordinator.jsonl` exactly match the corresponding ledger fields. The focused suite
    mutates a temporary transcript and proves hash drift fails closed. It also proves duplicate
    reconciliation leaves the ledger byte-identical.
  - Two direct `run_l3.py status` reads left the classification-ledger SHA-256 unchanged
    (`f887a2e18206aa4dffb35ef763574f7527e20286925bc2a627cb78d3c5ca93e8`) and returned
    `state=PAUSED`, `outcome=NOT_PASSED`, `category=collaboration/routing`, `team_starts=3`, and
    `classification_count=3` with its ledger reference. No isolated L3 runtime remained.
- Regression/runtime checks: L3 launcher tests PASS `21/21`; L1 PASS `15/15`; M1 PASS `13/13`;
  L3 Ruff, `git diff --check`, active `ontology-platform.service`, `8001/api/health`, and `5173/`
  all PASS.
- Defects: none in this Round 3 scope. The Round 2 historical-classification defect is FIXED by
  the bound, append-only correction ledger; raw history was not rewritten.
- Still unexecuted by design: real semantic/platform cases L3-19--L3-43, including a real
  three-Agent collaboration, answer/resume, Protocol key/write lifecycle, Batch application,
  business validation/reasoning, C->B->A query, Draft exclusion and explicit unknown. They remain
  NOT PASSED, and no fourth attempt is authorized by this test result.

### Independent Round 4 — 2026-07-30T13:18:45+08:00

- Scope and safety: offline pre-commit retest only. No coordinator/team/probe, run root, Project,
  key, Batch, platform write, or other live resource was started.
- Overall result: **FAIL** for the requested durable *committed* paused state. The implementation
  and runtime policy behavior pass locally, but `execution-policy.json` is currently untracked and
  absent from the Git index; it cannot provide a durable cross-checkout pause until it is staged
  and committed with the scenario.
- Verified local behavior:
  - The non-ignored policy has the exact disabled state: `PAUSED`, `NOT_PASSED`,
    `collaboration/routing`, `starts_consumed=3`, and exactly `g`, `h`, `i`; it also lists all
    three required recovery conditions (verified child delegation, plan re-review, explicit user
    authorization for a new budget).
  - `reserve_coordinator_start()` calls policy authorization before any global-ledger mutation;
    `run()` reserves before it creates a runtime root, stages input, runs the isolated probe, or
    reaches credential creation. Focused tests prove a disabled policy rejects there with no runtime
    root/probe and prove policy/local-ledger mismatch fails closed.
  - `run_l3.py status` PASS: committed-policy view and local ledger agree on
    `PAUSED / NOT_PASSED / collaboration/routing`, three starts and three classifications.
    README now states that live execution is disabled and no longer advertises a runnable live
    command.
- Regression/runtime checks: L3 launcher PASS `23/23`; L1 PASS `15/15`; M1 PASS `13/13`; L3 Ruff,
  `git diff --check`, active `ontology-platform.service`, `8001/api/health`, and `5173/` all PASS.
- Defect:
  1. **High — policy is not committed/staged.** `git check-ignore` confirms the path is not ignored,
     but `git ls-files --stage -- docs/evaluation-scenarios/ontology-modeling-team-l3/execution-policy.json`
     returns no index entry and `git status --short` returns `??`. Expected: the policy is included
     in the commit that makes the durable pause claim. Actual: committing the presently staged L3
     surface would omit it and remove the fail-closed policy in another checkout. Evidence: Git
     index/status at this round.
- Still unexecuted: L3 semantic/platform cases L3-19--L3-43 remain NOT PASSED. Staging/committing
  this policy only makes the pause durable; it neither authorizes nor supplies a fourth live run.
- Recommendation: stage `execution-policy.json` in the intended L3 commit, then rerun this same
  pre-commit Round 4 check. No product/scenario code repair or live execution is required.

### Independent Round 5 — 2026-07-30T13:19:45+08:00

- Scope and safety: pre-commit offline packaging retest only. No coordinator/team/probe, run root,
  Project, key, Batch, platform write, or live resource was created.
- Overall result: **PASS** — the durable paused delivery is now correctly included in the staged
  L3 scope. This PASS covers the terminal execution policy only; L3 itself remains **NOT PASSED**.
- Packaging evidence: `execution-policy.json` has the required Git index entry
  `100644 3658fca86afa7c423d82e91afb1f912b12657797`, is staged as an added scenario file, is not
  ignored, and appears with `run_l3.py` in the cached scenario diff. The cached diff includes both
  `live_execution_authorized=false` / `PAUSED` / `NOT_PASSED` and the launcher pre-root
  `require_live_execution_authorized()` check.
- Behavior/evidence: L3 tests PASS `23/23`, including fresh-no-runtime disabled-policy rejection
  before root/probe/key and local-ledger-policy mismatch fail-closed. `run_l3.py status` reports
  confirmed policy/local agreement: `PAUSED / NOT_PASSED / collaboration/routing`, three starts,
  and three historical classifications. No L3 isolated process was present.
- Verification: `git diff --check` and `git diff --cached --check` PASS; active
  `ontology-platform.service`, `8001/api/health`, and `5173/` PASS.
- Defects: none in this Round 5 scope. Round 4's untracked-policy packaging defect is FIXED.
- Still unexecuted by design: L3-19--L3-43 real semantic/platform cases remain NOT PASSED. This
  durable policy does not authorize a fourth run; recovery still requires the recorded proof,
  plan re-review, and explicit user authorization for a fresh budget.

### Independent Round 6 — 2026-07-30T14:40:43+08:00

- Scope and safety: offline recovery review only. No coordinator/team/probe, run root, Project,
  key, Batch, platform write, or new live resource was created. Raw `g`/`h`/`i` rollout evidence
  was read only; earlier rounds and the Delivery-owned record were not edited.
- Overall result: **FAIL** — raw-rollout recovery and policy/budget mechanics pass, but the
  recovery clock is not reset for start 4 and would immediately and permanently halt the newly
  authorized execution phase. L3 remains **IN PROGRESS**, not completed and not accepted.
- Passed evidence:
  - Direct raw audit accepts `h` and `i`: each has one `spawn_agent` with
    `agent_type=modeling_agent`, `fork_turns=none`, a linked `sub_agent_activity.agent_thread_id`,
    and child `session_meta`/`thread_spawn` parent-role proof. It rejects `g` because its linked
    child lacks `agent_type=modeling_agent`; `task_name` alone is not accepted. A transcript-only
    fixture is fail-closed, so the former outer-summary false no-child diagnosis cannot recur.
  - Historical raw files remain untouched. The append-only correction ledger retains v1 and adds
    exactly three v2 corrections: `g` is a role-boundary `collaboration/routing` negative, while
    `h/i` are `SUPERSEDED / NOT_APPLICABLE / acceptance-harness` false-diagnosis corrections.
  - Policy v2 reports exactly three historical IDs, `starts_consumed=3`, `max_starts=5`, and the
    explicit two-start authorization. Offline tests enforce a repairable terminal start 4 before
    start 5, reject modeling-quality before start 5, and reject a sixth start. Existing L3 prompts,
    roles, input pack, Protocol mechanics/key lifecycle and semantic acceptance surfaces are not
    modified in the recovery diff; L0/L1 suites remain regression oracles.
  - L3 tests PASS `27/27`; L1 PASS `15/15`; M1 PASS `13/13`; L3 Ruff, working/cached diff checks,
    `run_l3.py status`, active `ontology-platform.service`, `8001/api/health`, and `5173/` PASS.
- Defect:
  1. **High — recovery start 4 is impossible because the first-delegation clock was not reset.**
     The plan requires the recovery clock to reset at the reviewed developer handoff immediately
     before start 4, but `run_l3.py` retains
     `PREPARATION_STARTED_AT=2026-07-30T12:37:43+08:00` and derives a fixed deadline at 12:57:43.
     `reserve_coordinator_start()` defaults to current time and, when it is past that deadline,
     appends `preparation_halted` before creating any run root. Expected: a versioned recovery
     handoff/preparation timestamp associated with the newly authorized start budget and covered by
     an offline current-time test. Actual: attempting start 4 now would append a permanent halt to
     the shared ledger and prevent both authorized starts. Evidence: plan Recovery clock line 167;
     `run_l3.py:44-45, 576, 593-597, 913`; current time for this round is after the fixed deadline.
- Still unexecuted: all live L3-19--L3-43 semantic/platform cases, including recovery start 4,
  three-Agent collaboration, answer/resume, Protocol write/key lifecycle, Batch application,
  business validation/reasoning, C->B->A query, Draft exclusion and explicit unknown. Do not start
  a live run until the recovery-clock defect is fixed and independently retested.
- Recommendation: Requirement Developer should make the recovery handoff timestamp explicit,
  versioned and bound to policy v2 (or a reviewed equivalent), add an offline current-time
  start-4 test proving no `preparation_halted` is written, then repeat this same Round 6 scope.

### Independent Round 7 — 2026-07-30T14:45:26+08:00

- Scope and safety: focused offline recovery-clock retest only. No coordinator/team/probe, run
  root, Project, key, Batch, platform write, or live L3 resource was started; no isolated L3
  process is running.
- Overall result: **PASS** — Round 6's stale-clock defect is fixed. L3 remains **IN PROGRESS**;
  this is not a semantic-completion PASS.
- Recovery clock evidence:
  - Committed policy v2 binds `recovery_preparation_started_at` to
    `2026-07-30T14:42:13+08:00`; the derived deadline is `15:02:13+08:00`. Direct read-only
    calculation at `14:45:26+08:00` confirms the current authorized start-4 window is open.
  - `reserve_coordinator_start` and `record_modeling_delegation` now derive both the deadline and
    recorded preparation timestamp from that policy field. Focused tests prove a current-time
    start 4 does not append `preparation_halted`, while an expired handoff appends the halt and a
    naive/missing-timezone policy is rejected fail-closed.
- Regression and state: L3 launcher PASS `30/30`; L1 PASS `15/15`; M1 PASS `13/13`; L3 Ruff,
  working/cached diff checks, `run_l3.py status`, active `ontology-platform.service`,
  `8001/api/health`, and `5173/` all PASS. Status confirms policy/local ledger agreement:
  `READY / PENDING`, three historical starts, `max_starts=5`, and exactly two authorized
  remaining starts.
- Defects: none in this Round 7 scope. The Round 6 High recovery-clock defect is FIXED.
- Still unexecuted: live L3-19--L3-43, including start 4, real three-Agent collaboration,
  question/answer continuation, Protocol key/write lifecycle, Batch apply, validation/reasoning,
  C->B->A retrieval, Draft exclusion and explicit unknown. Those remain pending and must be
  assessed from new raw evidence if a separately authorized live start proceeds.

### Independent Round 8 — 2026-07-30T15:00:48+08:00

- Scope and safety: offline continuation-repair review only. I did not invoke `continue` against
  `l3-real-20260730j`, start a coordinator/Protocol Agent, create a Project/Ontology/key/Batch, or
  perform platform writes. The non-secret file-inventory SHA-256 for `j` was identical before and
  after all checks: `2c4bec3355f808a4f21b45472502262d784c0380a14ab89d161222735b083ead`.
  Earlier rounds and the Delivery-owned record were not edited.
- Overall result: **FAIL** — retained-session and dispatch mechanics pass offline, but two High
  defects make live continuation unsafe: plaintext credentials persist in the retained run, and
  runtime failures are reclassified as collaboration/platform failures.
- Passed continuation mechanics:
  - `continue_run()` is a separate `continue --run-id ... --execute` entrypoint. It accepts only
    `WAITING_FOR_COORDINATOR_OUTPUT`, the exact retained run ID and recorded coordinator Session,
    and an exact mechanically released frozen answer; it does not call
    `reserve_coordinator_start()` or create a fresh run root. A temporary two-cycle test kept both
    cycles non-terminal, mechanically released each answer, and proved a patched fresh-reservation
    call was never reached.
  - A resumed Session identity mismatch is rejected and canonical dispatch drift fails closed.
    Only canonical candidate/dispatch reaches `_apply_protocol`; a pending question blocks it.
  - The intended application path reuses isolated bwrap/sanitized REST, the no-key MCP probe,
    ephemeral admin/Project/Ontology/model key, Protocol MCP allowlist/audit, and finally order of
    model-key revoke before exact Project deletion, host-admin revoke, and runtime exit.
  - L3 launcher `35/35`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached `git diff --check`;
    active `ontology-platform.service`; `8001/api/health`; and `5173/` all PASS. `status` reports
    policy/local-ledger agreement `READY / PENDING`, three historical starts, two authorized fresh
    starts.
- Defects:
  1. **High — continuation leaves plaintext credential artifacts in the retained run (L3-08,
     L3-39, L3-40).** Reproduction: canonical dispatch reaches `_apply_protocol`, which calls
     `_write_protocol_config(run_root / "protocol-home", model_key, settings)`. That config
     contains `ONTOLOGY_MCP_API_KEY=<plaintext model key>` and the directory receives copied host
     `auth.json`. Finally revokes the key/deletes the Project but never removes `protocol-home`.
     Expected: no plaintext model key or host Codex authentication remains in retained artifacts
     after cleanup. Actual: both remain if Protocol starts. Evidence: `run_l3.py:1085-1107,
     1301,1318-1337`; temporary isolated reproduction confirmed
     `protocol_config_contains_model_key=true`; source search found no protocol-home cleanup.
  2. **High — continuation terminal category is wrong for runtime/infrastructure failures
     (L3-14, L3-38).** Injecting `coordinator runtime/infrastructure: agent_terminal_error` into
     resume records `collaboration/routing`; the equivalent Protocol error records
     `platform-contract`. Expected: `runtime/infrastructure`, preserving the actual layer.
     Evidence: direct isolated outcomes and `run_l3.py:1252-1253`, whose substring branch has no
     runtime-category case.
- Still unexecuted by design: live continuation of `j` and all real L3-19--L3-43 evidence,
  including a resumed coordinator Session, Protocol MCP transcript, scope/Batch apply, semantic
  validation/reasoning/query and real cleanup receipts. This round supplies no semantic-completion
  PASS.
- Recommendation: Requirement Developer should securely remove run-local Protocol/Codex-auth
  artifacts after the process exits and add an artifact-scan test; it should also preserve explicit
  runtime/infrastructure, collaboration/routing and platform-contract categories through terminal
  recording. Rerun this Round 8 scope before any live `j` resume.

### Independent Round 9 — 2026-07-30T15:06:31+08:00

- Scope and safety: focused offline retest of the two Round 8 High fixes. I did not invoke
  `continue` for `l3-real-20260730j`, start an Agent or Protocol process, create a scope/key/Batch,
  or make a platform write. The non-secret `j` inventory SHA-256 stayed
  `2c4bec3355f808a4f21b45472502262d784c0380a14ab89d161222735b083ead` before and after testing.
  Only this shared plan was edited.
- Overall result: **FAIL** — credential artifact closure is FIXED, and most terminal routing is
  FIXED, but a remaining actual Protocol process-start failure is still classified as
  `platform-contract` instead of `runtime/infrastructure`. Do not resume `j`.
- Fixed and passed:
  - `_destroy_protocol_home` securely destroys the uniquely-owned `protocol-home` after process
    exit, retains raw audit evidence outside that directory, scans every remaining run-local file
    for the exact temporary model key, returns a redacted cleanup receipt, and fails closed if the
    key is found. Focused tests prove config/auth destruction, retained redacted audit, and a leak
    in `audit/` rejection. The cleanup order remains key revoke, exact Project deletion, host-admin
    revoke, process exit, credential-home destruction and retained-artifact scan.
  - Correct routing is verified for coordinator/provider/timeout and Protocol
    `runtime/infrastructure`/`exit_` errors; recorded Session identity and pending-question routing
    go to `collaboration/routing`; dispatch/public-protocol/platform-format/state text maps to
    `platform-contract`. Existing continuation tests still prove exact waiting state/frozen answer,
    no fresh reservation, same-session identity, canonical dispatch and non-terminal question
    cycles.
  - Required checks PASS: L3 `39/39`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
    `git diff --check`; active `ontology-platform.service`; `8001/api/health`; `5173/`; and L3
    `status` (`READY / PENDING`, three historical starts, two authorized fresh starts).
- Defect:
  1. **High — Protocol process-start failure remains misclassified (L3-14, L3-38).** Reproduction:
     `_start_application_rest` raises the actual message `isolated application REST exited before
     health` when the owned isolated REST process exits. `_continuation_failure_category` does not
     match `exited`/`process`, so `continue_run` records `platform-contract`. Expected:
     `runtime/infrastructure`, because the process did not reach health and no platform contract
     was evaluated. Actual: `platform-contract`. Evidence: direct category-injection matrix:
     `coordinator process exited before health -> platform-contract`; source
     `run_l3.py:1130,1245-1251`. All other requested injection cases matched their expected
     categories.
- Still unexecuted: live `j` continuation and real L3-19--L3-43 Protocol/platform/semantic
  evidence. This is not a semantic-completion PASS.
- Recommendation: Requirement Developer should extend the runtime matcher to cover the actual
  isolated REST process-exit message (and add it as a direct regression test), then rerun this same
  Round 9 scope before any live continuation.

### Independent Round 10 — 2026-07-30T15:08:58+08:00

- Scope and safety: focused offline retest of the Round 9 process-start category repair. I did not
  invoke `continue` for `l3-real-20260730j`, start an Agent/Protocol process, create a
  Project/Ontology/key/Batch, or make platform writes. `j`'s non-secret inventory SHA-256 remained
  `2c4bec3355f808a4f21b45472502262d784c0380a14ab89d161222735b083ead` before and after testing.
  Only this shared plan was edited.
- Overall result: **PASS** — Round 9's remaining High category defect is fixed. This is an offline
  continuation-safety PASS only; it is not a real semantic/platform acceptance of `j`.
- Category-injection evidence:
  - Exact `isolated application REST exited before health`, startup-not-healthy, generic process
    exit, coordinator `exit_`, provider and timeout variants all resolve to
    `runtime/infrastructure`.
  - Recorded Session mismatch and pending-question/dispatch-while-pending variants resolve to
    `collaboration/routing`.
  - Dispatch integrity, public-protocol contract, platform-result format and retained-state drift
    variants remain `platform-contract`. The independent matrix returned zero mismatches, and the
    focused test verifies the exact isolated-REST message is recorded as runtime/infrastructure.
- Prior safety gates rechecked:
  - Protocol credential-home destruction, exact retained-run model-key scan, redacted cleanup
    receipt and leak fail-closed tests remain PASS. Raw audit outside `protocol-home` remains
    retained.
  - A temporary exact-WAITING continuation reached PASS with `reserve_coordinator_start` patched
    to fail if called; it was not called, confirming continuation still consumes no fresh start.
- Required checks PASS: L3 `40/40`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
  `git diff --check`; active `ontology-platform.service`; `8001/api/health`; `5173/`; and L3
  `status` (`READY / PENDING`, three historical starts, two authorized fresh starts).
- Defects: none in this Round 10 scope. Round 9's High process-start classification defect is
  FIXED.
- Still unexecuted: live `j` continuation and real L3-19--L3-43 Agent/Protocol/platform/semantic
  evidence. A later live run must be accepted from its retained raw evidence, not this offline
  result.
- Recommendation: the repaired continuation gate is ready for the main agent's separately
  authorized decision on whether to resume `j`; no additional repair is required before that
  decision.

### Independent Round 11 — 2026-07-30T15:20:02+08:00

- Scope and safety: offline start-4 correction/start-5 timing review only. I did not invoke a
  live command, reserve start 5, alter `j`, create a scope/key/Batch, or make platform writes.
  Only this shared plan was edited.
- Overall result: **PASS** — the correction and recovery-phase first-modeling gates correctly
  preserve raw evidence while allowing the separately authorized start-5 timing path only after a
  valid start-4 modeling record and a repairable authoritative terminal category.
- Raw `j` and correction evidence:
  - Original raw `audit/state.json` remains `PAUSED / NOT_PASSED / platform-contract`, including
    its original terminal outcome, SHA-256
    `8476f6c3481289ef714cdad2c354d25f1d86b40142ac033b6800dc9d5ab37c05`.
    `audit/coordinator-resume-1.jsonl` remains SHA-256
    `d8ae88280a6a9b0efeb3b8adb4e22296a2b8c5fb3da1aaaedbf90909025c4783`, contains exactly one
    `L3_WAITING_FOR_ANSWER`, and no pending question exists. The full non-secret `j` inventory
    SHA-256 stayed `b904391928fd50095ba1000626c5b2720a19cdddf50f4c308d99698d3d5be039`.
  - The append-only ledger has exactly one `l3-wait-marker-correction-v1` for `j`, binding those
    two raw SHA values plus `pending_question_absent=true`; its authoritative category is
    `collaboration/routing`. Two `status` reads left the ledger SHA unchanged
    (`cfed3380b952133797c5923e5644795d9c98b775298eae4d755ad1e0d6dab4a8`). The focused test proves
    transcript drift fails closed.
  - `status` reports local `PAUSED / NOT_PASSED / collaboration/routing` with
    `terminal_correction_count=1`; direct read-only evaluation confirms actual start-5
    repairability uses that authoritative correction.
- Timing and boundary evidence:
  - The actual recovery-phase `modeling_started` is valid against the reviewed preparation time,
    so an elapsed original 20-minute wall-clock does not itself halt start 5. The focused test
    proves a valid before-deadline modeling record permits the later reservation without appending
    `preparation_halted`.
  - Direct invalid-record checks reject missing coordinator/modeler IDs and a mismatched
    preparation timestamp; the focused absent-record test appends `preparation_halted` instead.
    Existing budget tests retain the maximum-five and `modeling-quality` hard-stop gates.
- Regression/safety PASS: L3 `44/44`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
  `git diff --check`; active `ontology-platform.service`; `8001/api/health`; and `5173/` all PASS.
  The previously verified credential-home destruction and retained-artifact secret scan remain
  covered by the L3 suite.
- Defects: none in this Round 11 scope.
- Still unexecuted: any real start-5 work and all remaining live L3-19--L3-43 semantic/platform
  acceptance. This offline PASS does not create authorization or acceptance for a new run.
- Recommendation: no correction/timing repair is needed. The main agent may make a separate
  authorization decision for the next live step; any such step requires fresh raw-evidence review.

### Independent Round 12 — 2026-07-30T15:31:29+08:00

- Scope and safety: offline `k` append-only recovery review. No live Agent/Protocol command,
  Project/Ontology/key/Batch creation, or actual answer release occurred. I invoked only the
  documented unresolved-pending early-return path and compared artifacts before/after; only this
  shared plan was edited.
- Overall result: **FAIL** — `k` raw evidence/correction and unresolved-pending protection are
  sound, but an exact released answer makes the next real same-session continuation fail before it
  can resume the coordinator.
- Passed evidence:
  - Raw `k` state (`aff85998affc07af68b82ae45092b0cb1962626a3003c4643e7d6834aceef768`),
    coordinator transcript (`78c243c40d86d4900de4a215f22ae1d3e6681c0cfce1e3e22e8f31185da31e67`),
    coordinator/child rollout hashes, grounded pending-question SHA, and original
    `preparation_halted`/`terminal_outcome` events are unchanged. The raw state remains the
    original `PAUSED / NOT_PASSED / runtime/infrastructure` record.
  - One append-only correction binds all raw file and rollout SHA values plus hashes of both
    superseded events. It is idempotent and drift-fail-closed, and overlays the authoritative
    `WAITING_FOR_ANSWER / PENDING / pending`, `halted=false` state with the recorded coordinator
    and Modeling Agent IDs.
  - Actual `continue --run-id l3-real-20260730k --execute` with the unresolved pending question
    returned the authoritative waiting state without creating a resume transcript, changing `k`'s
    non-secret inventory (`1381837742b7e86f6bf0481916e33858598be10ef4a388c166cfb8b36f3c7534`),
    or changing the correction-ledger SHA.
  - The focused timing tests prove later delegation after valid recovery modeling bypasses the old
    duplicate deadline, while a genuinely first late delegation still halts. Maximum-five/no-six
    and credential-cleanup gates remain covered.
- Defect:
  1. **High — exact answer release invalidates the correction required to resume `k` (L3-06,
     L3-23).** Reproduction on a temporary byte-identical `k` copy: mechanically release the exact
     frozen answer (which correctly replaces `pending-question.json` with
     `released-answer.json`), then call `continue_run(k, execute=True)`. Expected: the preserved
     authoritative recovery state remains valid and the command uses recorded coordinator Session
     `019fb1e6-161e-7692-8ead-26e7b918a64c`. Actual: `_effective_continuation_state` re-runs
     `_recovery_wait_correction`, which requires the original pending file and rejects any released
     answer, raising `recovery waiting correction lacks retained raw evidence` before resume.
     A synthetic authoritative overlay confirms the downstream resume command would use that exact
     recorded Session; the real transition is blocked by correction revalidation. Evidence:
     `run_l3.py:570-650,1276-1284,1524-1534` and the isolated reproduction.
- Regression/safety: L3 `48/48`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
  `git diff --check`; active `ontology-platform.service`; `8001/api/health`; and `5173/` all PASS.
  `status` now reports the authoritative `k` recovery state and the existing five-start ledger;
  no sixth start was made by this round.
- Still unexecuted: a real answer release/resume for `k`, any Protocol/platform work, and remaining
  live L3 semantic acceptance. Do not release `k`'s answer until this defect is repaired.
- Recommendation: Requirement Developer should preserve an immutable raw snapshot for correction
  verification (or record an equally hash-bound released-answer transition) so correction evidence
  is not invalidated by the authorized answer release; add a test for exact-answer then same-ID
  resume, then rerun this Round 12 scope.

### Independent Round 13 — 2026-07-30T15:37:55+08:00

- Scope and safety: offline recovery-answer transition retest only. I did not release the real
  `k` answer, invoke its live continuation, create an Agent/Protocol process or platform resource,
  or edit code/records. All releases/resumes below ran only against an exact temporary `k` copy;
  only this shared plan was edited.
- Overall result: **PASS** — the recovery correction now remains valid across the authorized exact
  answer transition and preserves the same coordinator Session for the next resume.
- Exact-copy transition evidence:
  - Before release, the immutable non-secret snapshot records the grounded pending question, its
    original SHA-256, and the exact recorded coordinator ID. Exact release creates that snapshot
    before deleting `pending-question.json` and writes only the frozen-contract answer.
  - Reconciliation preserves the prior v1 correction and appends a hash-bound v2 correction; it
    then remains idempotent. The authoritative state stays `WAITING_FOR_ANSWER / PENDING` after
    release, and the retained raw state remains byte-identical.
  - The post-release resume branch invoked only the recorded coordinator Session and reached the
    mocked Protocol handoff; no fresh start was reserved. Snapshot drift, exact-answer drift, and
    missing snapshot each fail closed before resume. No pending question remains after release.
- Real `k` remains untouched: its non-secret inventory SHA remains
  `1381837742b7e86f6bf0481916e33858598be10ef4a388c166cfb8b36f3c7534`; raw state, transcript and
  pending-question SHA are unchanged. `status` reports authoritative
  `WAITING_FOR_ANSWER / PENDING`, `halted=false`, recovery correction present, and the existing
  five-start ledger.
- Regression/safety PASS: L3 `51/51`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
  `git diff --check`; active `ontology-platform.service`; `8001/api/health`; and `5173/` all PASS.
  L3 coverage retains maximum-five/no-six and Protocol credential-cleanup/secret-leak rejection.
- Defects: none in this Round 13 scope. Round 12's High release-transition blocker is FIXED.
- Still unexecuted: real answer release and live same-session continuation of `k`, Protocol/platform
  application and live L3 semantic acceptance. This offline PASS does not authorize those actions.
- Recommendation: no further recovery-answer repair is required. A real `k` answer/retry remains a
  separate authorized decision and must be assessed from the retained raw evidence.

### Independent Round 14 — 2026-07-30T15:52:59+08:00

- Scope and safety: offline resume-write repair review only. I did not invoke real `k`
  continuation, alter its evidence, reserve a new start, or create an Agent/Protocol/platform
  resource. The bwrap write probe and continuation ran only in temporary directories; only this
  shared plan was edited.
- Overall result: **PASS** — the resumed coordinator command now has the required writable work
  sandbox shape, and v3 preserves the failed read-only resume as hash-bound evidence while making
  the next same-session retry deterministic and non-consuming.
- Resume/isolation evidence:
  - `_codex_exec_command` places `--sandbox workspace-write -C /work` on the parent `codex exec`
    before `resume <recorded-session> -`. The focused command-shape test passes.
  - A direct bwrap probe built from `_coordinator_command` wrote atomically to `/work`, could not
    write the read-only `/opt`, and found neither `/repo` nor `/opt/tester-only`. It used only
    temporary input/work/home directories and did not launch Codex.
  - An exact temporary `k` copy selected `coordinator-resume-2.jsonl`, targeted coordinator Session
    `019fb1e6-161e-7692-8ead-26e7b918a64c`, reached the mocked Protocol handoff, and had
    `reserve_coordinator_start` patched to fail if called; it was not called.
- Evidence/correction integrity:
  - Real `k` non-secret inventory remains
    `c1dfc86ba1ace27377c0b94e64e9c3a114d9d9f7fa85eecfa347567bb9ae67a1`.
    Its raw state/coordinator evidence, snapshot, exact answer, and resume-1 transcript/stderr
    remain retained.
  - The append-only v1/v2/v3 chain is present. v3 binds snapshot and frozen-answer hashes,
    resume-1 transcript/stderr hashes, the prior-v2 correction SHA, and original
    state/coordinator/child-rollout evidence; it records the former read-only harness failure as
    `runtime/infrastructure`. Two status reads left the correction-ledger SHA unchanged
    (`75012ad1ca1e852a45206be9588c0ff06379b8ee4047ef9f809d74f7e7be6643`). Focused drift and
    idempotency tests fail closed/pass respectively.
- Regression/safety PASS: L3 `54/54`; L1 `15/15`; M1 `13/13`; L3 Ruff; working/cached
  `git diff --check`; active `ontology-platform.service`; `8001/api/health`; and `5173/` all PASS.
  Status reports `WAITING_FOR_ANSWER / PENDING`, the existing five-start ledger, and no start 6.
  L3 tests retain max-five/no-six and credential-cleanup/secret-leak checks.
- Defects: none in this Round 14 scope. The read-only resume-write defect is FIXED.
- Still unexecuted: the real `k` resume-2, any Protocol/platform application, and L3 semantic
  acceptance. This offline PASS does not authorize a live retry.
- Recommendation: no further adapter repair is needed. A real resume-2 remains a separate
  authorized action and must be evaluated from fresh retained evidence.

### Independent Round 15 — 2026-07-30T16:06:40+08:00

- Scope and safety: independent offline retest of multi-question append-only recovery only. I
  copied the current `l3-real-20260730k` evidence into temporary directories and made every
  answer, resume transcript, cycle record, and drift mutation there. I did not release the real
  `k` answer, invoke its continuation, reserve a coordinator start, or create an Agent/Protocol/
  platform resource. Only this test plan was edited.
- Overall result: **FAIL** — the append-only record writer can preserve three distinct cycles in
  isolation, but the actual same-session path becomes unrecoverable after the second frozen
  answer and prior-cycle question-hash tampering is not detected.
- Executed recovery checks:
  - Exact-copy flow: the existing `invocation-target` answer plus the real current second
    question, then `output-continuity`, followed by a same-coordinator resume-3 output and
    `missing-score-behavior`, produced `recovery-cycle-1..3.json`. The records have sequential
    indexes, three distinct pending-question SHA-256 values, the same coordinator ID, exact
    frozen answers, and origins `coordinator.jsonl`, `coordinator-resume-2.jsonl`, and
    `coordinator-resume-3.jsonl`. The byte content of cycles 1--2 remained unchanged while cycle
    3 was appended. Invalid answer ID and duplicate release were rejected without changing the
    pending question or existing records. Missing resume-4 origin and swapped cycle-1/2 records
    both failed closed.
  - The genuine copied `continue_run(k, execute=True)` path could not perform that resume-3:
    after releasing the exact second answer, correction reconciliation failed first with
    `recovery waiting classification evidence hash drift`; no fresh start was attempted. To
    complete the append-only writer and negative-record checks, the subsequent same-session
    output was represented only by its correctly shaped retained resume-3 transcript and one
    atomic pending question in that temporary copy.
  - Replacing cycle 2's `pending_question_sha256` with cycle 1's hash (while preserving ordering,
    coordinator, answer, and origin) still returned authoritative `WAITING_FOR_ANSWER / PENDING`.
    Thus the record reader checks only record ordering/coordinator and never re-hashes each
    frozen question, validates the answer contract, or binds prior cycle evidence into the
    correction.
- Defects:
  1. **High — multi-cycle release regresses the correction version and blocks same-session
     continuation (L3-06, L3-23).** Reproduce on an exact temporary `k` copy: release the exact
     answer for current question 2 (`output-continuity`), then call `continue_run(k,
     execute=True)`. Expected: a new, hash-bound correction revision reflects the next release
     and resumes the recorded coordinator without a fresh start. Actual:
     `_recovery_wait_correction()` falls back to correction v3 once no pending file exists;
     v3 already represents the prior answer, so reconciliation raises `recovery waiting
     classification evidence hash drift` before the command executes. Evidence: `run_l3.py`
     `_recovery_wait_correction()` revision selection and `_snapshot_recovery_pending_question()`
     record append path; isolated exact-copy reproduction above.
  2. **High — prior recovery-cycle question-hash drift is accepted (L3-06, L3-23).** On the
     completed three-cycle temporary copy, replace only cycle 2's stored question hash with cycle
     1's valid hash, retain valid resume-4 evidence, then run `local_scenario_status()`. Expected:
     fail closed because a frozen cycle record no longer binds its stored question content to its
     hash. Actual: status remains `WAITING_FOR_ANSWER / PENDING`. Evidence: `_recovery_cycle_records()`
     validates only JSON parsing, coordinator ID, and sequence; it does not validate record
     fields/content hashes, exact answer, or originating-transcript hash.
- Real-state read-only verification: real `k` still has current question 2 pending (SHA-256
  `beb43e7f7ed6d4cebf1d480aa6f5f735b6a7a1412c3bb7c37cbbe8469ea00560`) and the prior frozen
  `invocation-target` release. Its raw retained state remains `PAUSED / NOT_PASSED /
  runtime/infrastructure`; the authoritative `status` overlay is `WAITING_FOR_ANSWER / PENDING`,
  `halted=false`, with the existing five starts (three historical, no sixth).
- Regression and environment evidence: L3 launcher `55/55`, L1 `15/15`, M1 `13/13`, focused L3
  Ruff, `git diff --check`, active `ontology-platform.service`, health endpoint, and frontend
  endpoint all PASS; frontend build and Playwright `38/38` also PASS. Full backend `pytest -xq`
  is **not green** (1 failed, 181 passed, 2 skipped): pre-existing/out-of-scope
  `tests/test_mcp_auth.py::test_mcp_startup_requires_environment_key` expected a RuntimeError but
  none was raised. Repository-wide Ruff is likewise blocked by 47 existing findings outside the
  L3 files. The L3 suite retains maximum-five/no-six and credential-cleanup/secret-leak rejection
  coverage; no secret value was emitted by this round.
- Recommendation: Requirement Developer should repair both correction revision monotonicity over
  every completed cycle and strict validation of each immutable cycle record (schema, question
  hash, exact answer, coordinator and transcript hash), add focused regressions, then request a
  Round 16 retest. Do not perform another real `k` answer release or continuation until fixed.

### Independent Round 16 — 2026-07-30T16:20:28+08:00

- Scope and safety: offline retest of Delivery's Round 15 correction-chain repair. I reviewed the
  L3 launcher/test diff and exercised only an exact temporary copy of the current `k` runtime and
  ledgers. I did not change production code or the Delivery record, release the real answer,
  invoke real continuation, reserve a fresh start, or create Agent/Protocol/platform resources.
  Only this shared plan was edited.
- Overall result: **PASS** — the Q2 recovery transition now appends a monotonic, hash-bound
  correction revision; all requested cycle/correction links validate fail-closed; and same-session
  resume selects the expected recorded Session without consuming a start.
- Exact-copy recovery evidence:
  - Starting from real `k`'s Q1 released answer and Q2 pending question, exact Q2
    `output-continuity` release first reconciled the pending transition, appended cycle 1 and 2,
    then appended correction
    `l3-duplicate-first-modeling-gate-correction-v5:l3-real-20260730k`. v5 retains all earlier
    ledger bytes, links `previous_correction_id` and SHA-256 to v4, and binds
    `cycle_count=2` plus the exact SHA-256 of cycle 2 as its head.
  - Cycle 1 (`invocation-target`) and cycle 2 (`output-continuity`) each matched the frozen answer
    contract, canonical pending-question hash, same recorded coordinator ID, expected origin path
    and transcript hash. Cycle 2 links to cycle 1's event hash and to v4's correction hash; cycle
    1 correctly has no predecessor links. Repeated status reads left the full correction ledger,
    pre-v5 revisions, both cycle files, and global start ledger byte-stable.
  - A mocked continuation from that exact copy passed only the recorded coordinator Session,
    selected `coordinator-resume-3.jsonl`, returned the mocked PASS handoff, and did not call or
    alter `reserve_coordinator_start`/the start ledger.
- Negative matrix PASS: each mutation below caused both `local_scenario_status()` and
  `continue_run(..., execute=True)` to fail before runtime execution: cycle 2 question hash
  replaced with cycle 1's; answer body; coordinator ID; origin path; origin transcript SHA;
  prior-cycle SHA; prior-revision SHA; and v5 `previous_correction_sha256`. This verifies the
  repaired reader validates schema, canonical question hash, exact frozen answer, coordinator,
  origin, cycle predecessor, revision predecessor, monotonic correction revisions, and transition
  head rather than merely record ordering.
- Real-state read-only verification: real `k` remains unchanged with question 2 pending (SHA-256
  `beb43e7f7ed6d4cebf1d480aa6f5f735b6a7a1412c3bb7c37cbbe8469ea00560`), prior released answer,
  and raw retained `PAUSED / NOT_PASSED / runtime/infrastructure` evidence. Authoritative status
  remains `WAITING_FOR_ANSWER / PENDING`, `halted=false`, three historical/five total starts; no
  sixth start or live operation occurred.
- Regression/safety PASS: L3 `57/57`, L1 `15/15`, M1 `13/13`, focused L3 Ruff, `git diff --check`,
  active `ontology-platform.service`, backend health, and frontend endpoint all pass. L3's 57-test
  suite includes the Protocol credential-home destruction and retained-artifact secret-leak
  rejection checks, along with maximum-five/no-six enforcement; no secret value was emitted.
- Defects: none in this Round 16 scope. Round 15's two High recovery-chain defects are FIXED.
- Recommendation: the repair is suitable for a separately authorized real `k` Q2 release and
  same-session continuation decision. Any live step must retain the same evidence/cleanup gates
  and be independently evaluated from resulting raw evidence.

### Independent Round 17 — 2026-07-30T16:33:27+08:00

- Scope and safety: independent offline test of the dispatch-marker and recovered-Protocol
  completion repair. I read the R2.2-001 requirement, L3 design, shared plan and current launcher
  diff, then used temporary copies for all dispatch, Protocol, final-state and drift mutations. I
  did not release an answer, resume a coordinator, run Protocol, create a scope/key/Batch, or make
  a platform write against real `k`; I did not edit product code or the Delivery record.
- **Important evidence note:** during initial inventory I inadvertently invoked the normal
  `run_l3.py status` command against real `k`. Its reconciliation appended the deterministic v8
  correction (v7 was the ledger head immediately before that command); no other real `k` artifact
  was modified, and no resume/new start/Protocol execution occurred. I notified the main agent
  immediately and performed no further real status invocation. Read-only ledger review confirms
  v8 is `READY_FOR_PROTOCOL`, has three-cycle head
  `759eae318d1b5cb4a7b01c4f47ce8f42b7d0745e4b2871531603f0c549183fe6`, and links to v7 by the
  recorded previous-correction SHA.
- Overall result: **PASS** for the repaired offline recovery contract, with the above real-evidence
  write disclosed as a process deviation rather than a product defect.
- Executed evidence:
  - Exact marker parser check: a `command_execution` item containing both terminal strings did not
    match; an `agent_message` whose trimmed text was exactly `L3_COORDINATOR_DISPATCHED` did. The
    same exact-message rule guards waiting and dispatch resume evidence.
  - On an exact temporary copy of the stable real `k` READY state, v8 used the existing approved
    candidate/dispatch, skipped `_execute_command` for the coordinator entirely, entered only the
    existing Protocol branch, and left the global start ledger byte-identical. The mocked existing
    Protocol path created only temporary retained completion/audit evidence.
  - Successful temporary Protocol completion produced authoritative `PASS / PASSED / passed` v9,
    with v9's previous correction ID/SHA bound to v8 and final-state, protocol-result,
    protocol-rollout-audit and platform-fact-audit SHA evidence retained. Earlier ledger bytes
    were an exact prefix of the v9 ledger.
  - Drift matrix PASS: corrupting v9 previous-correction hash, final-state scope, retained Protocol
    audit, or changing the dispatch transcript to command-output-only all caused both status and
    continuation to fail closed before runtime work.
- Regression/safety PASS: L3 `60/60`, L1 `15/15`, M1 `13/13`, focused L3 Ruff, `git diff --check`,
  active `ontology-platform.service`, backend health, and frontend endpoint passed. The L3 suite
  continues to cover maximum-five/no-six and credential-home cleanup/retained-secret rejection.
- Unexecuted cases and residual risk: no real recovered Protocol application, platform acceptance,
  semantic validation/reasoning/query, or live cleanup was performed; L3 remains `IN PROGRESS`.
  Real `k` now awaits a separate authorized decision at `READY_FOR_PROTOCOL`; that decision must
  review the real v8 evidence, execute only the existing Protocol path, and independently inspect
  raw final/audit/cleanup evidence before treating L3 as complete.
- Defects: none in the Round 17 offline implementation scope. The accidentally appended real v8 is
  the only process deviation; it is deterministic and hash-linked but should remain explicitly
  recorded in the Delivery evidence history.
- Recommendation: do not redo coordinator work or create another fresh start. If the user/main
  agent authorizes the next live step, run only the recovered Protocol branch and request a new
  independent test round for the resulting raw completion evidence.

### Independent Round 18 — 2026-07-30T16:38:57+08:00

- Scope and safety: offline retest of the confirmed recovered-Protocol startup repair. I reviewed
  the launcher/test diff and used only temporary directories for command and retry-residue tests.
  I did not invoke real `k` status, resume, Protocol, or cleanup, and did not edit code or the
  Delivery record.
- Overall result: **PASS** — Protocol now uses the L1-proven interpreter-resolved uv runtime
  mount, does not mount the backend root, and permits exactly the evidenced one-time empty-work
  retry while rejecting residue drift.
- Executed evidence:
  - `_protocol_command()` binds
    `/home/yangxiang/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu` (the resolved
    interpreter runtime) and does not bind `BACKEND_ROOT` or any backend `.env` path. The existing
    venv and `app` mounts remain explicitly scoped.
  - A temporary retained failed-attempt layout with empty `protocol-1.jsonl`, required MCP
    initialization stderr, preserved application REST revoke-200/project-delete-204 log, empty
    `protocol-work`, and absent `protocol-home` produced the hash receipt. It records all three
    artifact hashes, `protocol_work_empty=true`, `protocol_home_absent=true`, and the verified
    cleanup statuses.
  - Independent negative checks for nonempty work, nonempty transcript, altered stderr, present
    protocol-home, and missing cleanup-log evidence each failed closed. The one-time receipt also
    prevents silently re-admitting the same residue.
  - Prior dispatch-marker and recovered v8/v9 behavior remains covered by the full launcher suite:
    exact agent-message marker matching, READY_FOR_PROTOCOL coordinator skip, hash-bound final
    correction, and drift rejection all remain green.
- Regression/safety PASS: L3 `62/62`, L1 `15/15`, M1 `13/13`, focused L3 Ruff, `git diff --check`,
  active `ontology-platform.service`, backend health, and frontend endpoint passed. The L3 suite
  retains maximum-five/no-six and credential cleanup/secret-leak rejection coverage.
- Defects: none in the Round 18 repair scope.
- Unexecuted/residual risk: the repaired command has not yet launched a real recovered Protocol;
  therefore real MCP initialization, platform application, semantic acceptance and final cleanup
  evidence remain unverified. L3 remains `IN PROGRESS`; any live retry must use only the admitted
  `k` residue, preserve the original application REST log and produce a new independent raw-evidence
  review.
- Recommendation: the narrow retry admission and mount repair are ready for a separately
  authorized recovered-Protocol retry. Do not create a fresh coordinator start or broaden scope;
  request the next independent round after retained live evidence exists.

### Independent Round 19 — 2026-07-30T16:40:40+08:00

- Scope and safety: offline retest of the second recovered-Protocol harness repair only. I used
  temporary retry evidence/protocol input; I did not invoke real `k` status, Protocol, resume, or
  cleanup, and did not edit code or the Delivery record.
- Overall result: **PASS** — the launcher owns the no-key probe, supplies only a redacted ordering
  proof to the already-keyed Protocol Agent, and narrowly admits the verified cancelled-probe
  residue as attempt 2.
- Evidence:
  - `credential-proof.json` states no-key rejection before temporary key creation and contains no
    credential material. The Protocol prompt explicitly says `Do not repeat the no-key probe` and
    no longer asks the keyed Agent to perform it.
  - A temporary attempt-2 residue with first receipt, cancelled `cancel_build_session` transcript
    / explicit credential-lifecycle block, empty stderr/work, absent credential home, and revoke
    200/project-delete 204 application log produced `protocol-retry-receipt-2.json`, hash-binding
    all retained evidence and naming the duplicated probe as runtime/infrastructure.
  - The launcher converts absent or invalid `protocol-result.json` to the explicit
    `Protocol Agent did not publish a valid protocol-result.json` L3 error rather than leaking an
    unclassified filesystem traceback. Existing tests cover retry drift/nonempty work and prior
    isolation, marker, v8/v9 recovery behavior.
- Regression/safety PASS: L3 `64/64`, L1 `15/15`, M1 `13/13`, focused L3 Ruff, `git diff --check`,
  active service and backend/frontend health pass.
- Defects: none in this offline repair scope.
- Unexecuted/residual risk: real attempt-3 recovered Protocol, actual modeling Batch/validation/
  reasoning/query and final cleanup evidence remain unexecuted; L3 is still `IN PROGRESS`.
- Recommendation: a separately authorized live retry may use only the hash-bound attempt-2
  residue. Do not create a fresh coordinator start; request independent raw-evidence review after
  the live result.

### Independent Round 21 — 2026-07-30T16:45:00+08:00

- Scope and safety: offline retest of the role-specific Protocol timeout and attempt-4 retry
  admission. No real `k` status, Protocol, resume, cleanup, or product/Delivery-record edit was
  performed.
- Overall result: **PASS** — the coordinator/resume budget remains 300 seconds and first response
  remains 60 seconds; only Protocol execution explicitly receives the separate 900-second terminal
  budget.
- Evidence: `_execute_command` defaults to `TERMINAL_TIMEOUT_SECONDS=300`; coordinator call sites
  use that default, while only `_apply_protocol` passes
  `terminal_timeout_seconds=PROTOCOL_TERMINAL_TIMEOUT_SECONDS` (`900`). Attempt 4 accepts only
  transcript proof that schema/SHACL were atomically applied and approved instances/relations were
  materializing, rejects Expected-RDF-IRI/fence text, requires empty stderr/work, absent protocol
  home and revoke-200/project-delete-204 cleanup. The 66-test L3 suite covers the hash receipt and
  corruption rejection plus earlier marker/v8-v9/isolation paths.
- Regression/safety PASS: L3 `66/66`, L1 `15/15`, M1 `13/13`; affected compiler/modeling suites
  `101 passed`; focused L3 Ruff, `git diff --check`, service and backend/frontend health pass.
- Defects: none in Round 21 scope.
- Unexecuted/residual risk: real 900-second Protocol retry, final validation/reasoning/query/result
  and semantic acceptance/cleanup remain unexecuted; L3 remains `IN PROGRESS`. Any live retry must
  use only the hash-bound attempt-4 residue and receive independent raw-evidence review.

### Independent Round 22 — 2026-07-30T16:48:00+08:00

- Scope/safety: read-only independent acceptance of the real recovered `k` completion evidence.
  I did not run status/continue, start any Agent, or modify runtime/product/Delivery-record files;
  only this plan is appended.
- Overall result: **PASS** — retained real evidence proves one completed recovered Protocol path.
- Evidence: raw `recovery-final-state.json` is `PASS / PASSED / passed`, owns Project
  `ff626c04-016e-40d2-899c-1a6fcbc2cec4`/Ontology `5b447112-230d-45b7-b8c1-af3f5afedc88`, and
  records model-key revoke, Project delete, host-admin revoke, isolated-runtime exit and removed
  credential home with no retained secret. v9 is the terminal recovery correction, linked to v8
  and its final-state hash. Global ledger has exactly five coordinator starts.
- `protocol-6.jsonl`, protocol result, protocol-only MCP audit and platform fact audit agree on
  completed Build Session `6ff1fa6f-4489-46ff-b71b-0c8a2b5a41b7`, three applied batches
  (schema/entities/relations), one SHACL-invalid dry-run-only batch, conforming validation,
  succeeded/consistent reasoning and complete published-path/draft-exclusion/explicit-unknown
  query flags. The applied-batch list is checked item-by-item against platform fact audit.
- Attempt 5 correctly archives the former singular-result contract as `platform-contract`: receipt
  hashes transcript/result/cleanup evidence, names the list-vs-singular mismatch, and the archived
  prior result retains four applied batches. Its retry receipt proves the then-current work was
  empty and protocol home absent; after the successful final attempt, only its final result is
  retained in protocol work. v9→v8 and v9→final-state SHA-256 links both verify.
- Regression PASS: L3 `68/68`, L1 `15/15`, M1 `13/13`, affected backend `101/101`, focused L3
  Ruff and `git diff --check`. The user service is active; backend `/api/health` and frontend `/`
  both return successfully.
- Residual: this validates retained evidence, not a repeatability claim; no additional live start
  is authorized. No defects found in Round 22 scope.

### Independent Round 20 — 2026-07-30T16:42:30+08:00

- Scope and safety: offline retest of the relation dry-run and attempt-3 recovery repair. I did
  not invoke real `k` status, Protocol, cleanup, or resume, and did not modify product code or the
  Delivery record.
- Overall result: **PASS** for the repaired compiler/retry contract.
- Evidence: `compile_create_relation` and `compile_delete_relation` now require absolute RDF IRIs
  for source, predicate and target before RDF delta construction. The targeted modeling regression
  suite covers invalid source/predicate/target rejection with zero side effects/no write fence and
  preserves valid absolute relations. Public Protocol guidance states client item IDs are never
  IRIs and requires entity Batch apply plus platform-returned entity IRI binding before the relation
  Batch.
- Attempt-3 review: `_prepare_protocol_work` admits only prior receipts plus exact transcript
  evidence for the relative-IRI dry-run escape, `ontology_write_fenced`, missing reasoning, empty
  stderr/work, absent protocol home, and cleanup revoke-200/project-delete-204 log. It emits a
  hash-bound attempt-3 receipt; any mismatch is runtime/infrastructure drift. The L3 suite covers
  this and prior isolation/marker/v8-v9 paths. MCP auth is isolated from local `.env` by the
  explicit-empty-key test override.
- Regression/safety: backend pytest completed green (reported stable result `820 passed, 10
  skipped`); targeted modeling `65`; L3 `65/65`; L1 `15/15`; M1 `13/13`; focused checks passed.
  Repository-wide Ruff remains blocked by 47 pre-existing unrelated findings; focused L3 Ruff and
  `git diff --check` pass. Service and backend/frontend health pass.
- Defects: none in this repair scope.
- Unexecuted/residual risk: real attempt-3 Protocol/modeling application and final semantic
  acceptance/cleanup evidence remain unexecuted; L3 stays `IN PROGRESS`. Any live retry must use
  only the hash-bound residue and be independently reviewed from raw evidence.
