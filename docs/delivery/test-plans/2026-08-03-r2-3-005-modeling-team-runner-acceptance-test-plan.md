# R2.3-005 Modeling Team Runner Acceptance Shared Test Plan

## Status and ownership

- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-005
- Design: `docs/delivery/designs/2026-08-03-r2-3-005-modeling-team-runner-acceptance-design.md`
- Status: plan approved; implementation and test execution pending
- Main documentation owner: root agent
- Independent acceptance owner: a fresh Acceptance role in the real four-role task

## Completion rule

R2.3-005 is complete only when the exact four-role Profile starts through Runner from a clean
checkout/status-clean worktree, existing three-role formal assets are rejected or upgraded, the
Runner-owned acceptance capability, child lifecycle and cleanup contracts pass deterministic tests,
the failure classifications preserve explicit unknowns, and one fresh real modeling slice completes
the required dry-run, apply, readback, validation, and reasoning contract plus two sequential independent CQs on the same persistent Acceptance. Each CQ must use a fresh
Source Examiner/Platform Examiner pair, with Round 2 starting only after Round 1 child cleanup
evidence is durable. Both real verdicts must be `PASS` and bind to the same final model-state digest;
boundary revalidation must prove that no stale PASS is consumed after state drift. No intentional real
FAIL/BLOCKED run is required.

## Automated contract cases

| ID | Case | Required result |
| --- | --- | --- |
| C01 | Exact four-role Profile | loads one Coordinator, Modeling, Protocol, Acceptance and no extra role |
| C02 | Missing/duplicate Acceptance or legacy three-role Profile | fails before scope or Agent startup |
| C03 | source-specialist formal Profile | rejected as incomplete modeling workflow |
| C04 | Acceptance Package permissions | Team Transport only; no platform, source, write, or spawn permission |
| C05 | Child descriptors | only the two predeclared kinds load; arbitrary package/path is rejected |
| C06 | Generic Codex feature flags | `multi_agent`, `multi_agent_v2`, and model-visible `spawn_agent` remain disabled/rejected |
| C07 | Readiness/silence messages | accepted as non-terminal coordination events and do not create terminal results or settlement |
| C08 | Acceptance routing | Acceptance verdict can reach Coordinator only; direct Modeling/Protocol route is rejected |
| C09 | Phase seriality | Coordinator cannot assign a new modeling task during acceptance |
| C10 | First child start | exactly one Source Examiner and one Platform Examiner start for an active round |
| C11 | Duplicate child start | same-kind second active child, different ticket digest, or cross-round handle fails closed |
| C12 | Caller authorization | only live Acceptance with the matching task/round capability can start/recycle children |
| C13 | Child nesting/communication | Examiner spawn, Team Transport, peer communication, and platform write are rejected |
| C14 | Opaque handle | Acceptance receives no PID, credential, raw socket, or unrestricted package path |
| C15 | Identical infrastructure retry | one retry uses the same ticket digest and a fresh child session |
| C16 | Second infrastructure failure | current round becomes `BLOCKED/runtime-infrastructure`; no third retry |
| C17 | Terminal child report | report is immutable, digest-bound, and required before recycle |
| C18 | Recycle cleanup | child process/session/temp credentials/private input are destroyed and receipt is fsynced |
| C19 | Round ordering | Round 2 start before Round 1 cleanup is rejected |
| C20 | Ticket schema | exact schema/ticket/acceptance-round/run/model/source/CQ/read-allowlist/timeout fields and question projection load; expected answer/dialogue/PASS fields are rejected |
| C21 | Source-location hint | allowed location-only hint creates a new ticket revision; answer-bearing hint fails |
| C22 | Source insufficient evidence | report contains `因缺少相关证据无法回答` and a concrete gap; no guess is accepted |
| C23 | Unsupported Source definite answer | `BLOCKED/acceptance-evidence`, not PASS and not modeling-quality repair |
| C24 | Platform evidence completeness | report includes scope, query basis, completeness, Evidence/lineage, and miss-vs-absence distinction |
| C25 | Platform semantic gap | source-answerable but unsupported/platform-unanswerable result is `FAIL/modeling-quality` |
| C26 | Legitimate unknown | source insufficient + Platform preserves unknown produces PASS with explicit unknown |
| C27 | Unsupported same text | identical unsupported answers from both Examiners never produce PASS |
| C28 | Ticket/source digest mismatch | `BLOCKED/acceptance-input`; no semantic verdict is accepted |
| C29 | Model-state digest | ticket, both reports, and verdict contain the same complete state identity |
| C30 | State change invalidation | a later platform write/model revision invalidates old PASS and requires both CQs again |
| C31 | Blocked round scope | BLOCKED cleans only the child pair; Acceptance and the other three roles remain live |
| C32 | Coordinator recovery decision | runtime recovery, source correction, and model repair route to their distinct next actions |
| C33 | Evidence sanitization | no credentials, hidden prompts, raw source bundle, or untrusted child error is written |
| C34 | Final settlement | all four persistent roles terminate once; every owned Session/Build Session/Lease/key is completed/cancelled/released/revoked with zero-residue evidence |
| C35 | Capability endpoints | Coordinator private config receives only publish plus read-verdict capabilities; Acceptance private config receives only get/child/report/submit capability; Team Transport and generic spawn cannot invoke child lifecycle |
| C36 | Child input projection | Source child sees question/source bundle only; Platform child sees question/state/read scope only; each input digest is recorded |
| C37 | Child report sink and carrier | child submits once to Runner-owned sink; Acceptance retrieves by opaque handle; no Team Transport terminal result is used |
| C38 | Report replay binding | task/round/ticket/source/input/handle/session/model-state mismatch or old report replay is `BLOCKED/acceptance-input` |
| C39 | Platform read-only credential | child receives project-scoped `read` key and ticket-minimal MCP allowlist; write/mutation calls fail; revoke and post-revoke failure are evidenced |
| C40 | State boundary revalidation | before pair, after PASS/before next CQ, and before settlement snapshots match or atomically invalidate all old PASS and issue a new ticket |
| C41 | Four-role cleanup migration | terminal dependencies, baseline, retained handoff and cleanup include Acceptance; no hard-coded three-role path remains |
| C42 | Clean baseline gate | non-empty `git status --porcelain` or baseline digest drift fails before semantic start |
| C43 | Ticket ownership and delivery | Coordinator-only capability endpoint publishes the requirement-bound immutable ticket; Acceptance-only endpoint can get/ack it and cannot replace it |
| C44 | Child request idempotency | exact `request_id` replays its receipt; a different request ID or digest fails closed; attempt is limited to 0/1 |
| C45 | Infrastructure recycle evidence | terminal recycle requires report digest; crash/timeout recycle requires immutable infrastructure-failure digest and increments retry exactly once |
| C46 | Runner-bound model-state envelope | Source child never receives platform state; Runner adds the ticket-bound opaque state digest at report ingestion |
| C47 | Infrastructure BLOCKED verdict | after the second child infrastructure failure, nullable report digests plus matching infrastructure/failure evidence digests form a canonical `BLOCKED/runtime` verdict |
| C48 | Validation/reasoning read wrappers | four generic read-only wrappers are ticket-scope bound, read existing Producer results, and reject run/start/mutation behavior |
| C49 | Typed evidence resolver | approved-source/platform-read union, digest binding, and complete pagination cursor chain are required; generic refs alone fail |
| C50 | Settlement CAS and late-write detection | settlement requires matching state/version token plus post-cleanup readback; drift withholds settlement and reroutes both CQs |
| C51 | Platform scope shim | every Platform Examiner read is bound to ticket Project/Ontology/graph and rejects same-Project foreign ontology/graph or missing binding |
| C52 | Full model-state and semantic checks | ticket/report/verdict carry the complete state envelope and source bundle digest; eight checks and every CQ result align with the round and all PASS is required for PASS |
| C53 | Infrastructure failure receipt chain | recycle receipt carries immutable failure/cleanup digests and typed `infrastructure_failure` evidence ref; Acceptance retrieves the bound failure record before submitting `BLOCKED/runtime` |
| C54 | Canonical acceptance round identity | ticket and verdict use `acceptance_round_id`; internal `round_id` aliases cannot be submitted in the canonical JSON |
| C55 | Modeling platform contract receipts | each ticket/verdict `modeling_receipts` item contains stage, successful stage-specific status, digest, run/Project/Ontology/slice/state bindings, and the complete typed `platform_read` evidence ref/page; all five stages are current-run and matching |
| C56 | Standard artifact binding | immutable requirement-owned rubric artifact is staged for Acceptance and its ref/digest binds ticket, verdict, and evidence |
| C57 | Verdict submission idempotency | stable verdict `request_id` replays the durable receipt or allows get-by-digest recovery; conflicting retries fail closed |
| C58 | Coordinator verdict recovery | lost sanitized notification is recoverable by Coordinator round lookup when digest is unknown; zero/multiple receipts fail closed |
| C59 | Canonical platform preflight | before reservation/scope/Session/Lease/start, authenticated `GET /api/semantic/canonical-mode` is HTTP 200 with `product_write_mode=rdf_primary`, cross-bound to unit/PID/start-time/process-env; mismatch consumes no semantic start |
| C60 | Canonical digest preimage | ticket/verdict digest computation excludes only its self-digest fields and nested ticket-digest refs as specified; published digests verify without self-reference |

## Service-level and integration cases

| ID | Scenario | Required evidence |
| --- | --- | --- |
| I01 | Coordinator assigns one slice, receives separate Modeling/Protocol ready+silence, and starts Round 1 | ordered phase events; no late modeling assignment |
| I02 | Source and Platform Examiner receive the same question but disjoint approved inputs | per-child input digest and access-scope evidence |
| I03 | Acceptance compares two valid reports and emits PASS to Coordinator | verdict plus both report digests and model-state digest |
| I04 | Platform Examiner misses a modeled fact | FAIL/modeling-quality routed to Modeling/Protocol; no BLOCKED label |
| I05 | Source Examiner cannot support a definite answer | BLOCKED/acceptance-evidence; child pair recycled; no ontology repair |
| I06 | Platform outage on first attempt then recovery | one retry, fresh session, same frozen ticket, eventual report or second-failure BLOCKED |
| I07 | Approved source bundle is incomplete | Coordinator waits for source/version correction or creates location-only hint revision |
| I08 | Model repair changes final workspace revision | old PASS invalidated; both CQs rerun with fresh pairs |
| I09 | Two real sequential CQs on fresh four-role task | Round 1 cleanup precedes Round 2; same Acceptance thread; fresh child IDs |
| I10 | Task settlement and cleanup | Acceptance ends with other persistent roles; child resources are already absent; Sessions/Build Sessions/Leases/credentials are terminal or revoked with zero-residue evidence |
| I11 | State drift between CQ1 and CQ2 | old CQ1 PASS is marked invalid; both CQs rerun on a new ticket/model-state digest before completion |
| I12 | Clean-checkout and canonical preflight | clean clone/status and inherited canonical-platform preflight precede prepare; one complete invocation settles and cleans; any second check is no-semantic-start and cannot create/apply a model |
| I13 | Real modeling-to-acceptance handoff | the same fresh four-role run records dry-run/apply/readback/validation/reasoning before ready/silence and binds those receipts into both CQ tickets and final verdicts |
| I14 | Authenticated canonical writer gate | exact active service unit/PID/start time and authenticated `rdf_primary` response are bound before any fresh write scope; stale/legacy-only process blocks without semantic start |

## Real acceptance run

Use one fresh Project/Ontology and one fresh four-role Modeling Team task. Reuse only the approved
R2.3-002 Dify Workflow-as-Tool `C -> B -> A` source corpus and simple objective; do not continue the
retained R2.3-002 model, enter R2.3-003 scope, or introduce a new business dataset.

The two frozen questions are:

1. `在 B 调用 C 作为 Tool 的关系中，当前能够确认的最新发布版本是什么，B 消费的是哪个输出？`
   Approved sources: `official/tools.mdx`, `release-register.md`, `workflow-landscape.md`.
2. `当 C 因 classifier dependency 不可用而没有返回 numeric score 时，B 会采取什么处理动作？`
   Approved source: `exception-handling.md`.

Tickets contain the frozen questions, approved source digests, model/read scope, standard reference,
allowlist, timeout, and current-run modeling receipts. They do not contain expected answers or the
acceptance analysis. Run the two rounds sequentially on the same persistent Acceptance. Record
the real child start/recycle receipts, raw sanitized report envelopes, verdicts, model-state binding,
and final cleanup. The real run must distinguish an explicit source unknown from an incorrect answer.
Before Acceptance starts, retain the Protocol-owned receipts for every required platform stage: each
dry-run and apply, formal readback, validation result, and reasoning result. Every receipt must bind
the current run ID, Project/Ontology, slice revision, and model-state digest; receipts from R2.3-002
or another Project/Ontology are diagnostic only and cannot satisfy this run's completion gate.

Before creating the real Project/Ontology, capture `git rev-parse HEAD`, an empty
`git status --porcelain`, the clean clone/worktree path, and the Profile/Task/Package/Skill manifest
digest. Also capture active service status, backend/frontend health, an authenticated
`GET /api/semantic/canonical-mode` HTTP 200 response with `product_write_mode=rdf_primary`, and
cross-bound unit/PID/start-time/process-environment evidence before any reservation or scope creation.
The same evidence must show the first semantic start occurred only after the clean-baseline
gate. After the real run, a repeatability preflight may use a fresh clean run root and run ID only
for configuration/capability staging and cleanup ordering. It must not create a Project/Ontology,
deliver business input, apply a model, or consume a semantic-start budget. A second real semantic
modeling run requires explicit new user authorization and is outside this requirement.

## Evidence and reporting requirements

Every test round records command or fixture, start/end time, requirement/design revision, result,
defect classification (`modeling-quality`, `platform-contract`, `collaboration/routing`, or
`runtime/infrastructure`), and retained evidence path. A failed test must identify the smallest
repair layer; it must not be relabeled BLOCKED merely because the report is inconvenient.

The final delivery record must append the plan-review disposition (including disposition of all High
findings), implementation/test rounds, clean-checkout evidence, real acceptance result, runtime
health, child cleanup, read-key revoke evidence, credential cleanup, state invalidation checks, and
any remaining late-write or Skill-tuning risk.

## Verification commands (implementation phase)

```bash
cd backend && uv run pytest
python -m unittest discover -s modeling_team/tests
git diff --check
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

The backend/frontend commands are required only if implementation changes those surfaces. The
current design itself is documentation-only and requires no service restart.

## Explicit non-claims

Passing this plan does not prove a generic product scheduler, automatic crash recovery, permanent
Acceptance memory across tasks, a mechanical platform write freeze, or advanced retrieval quality.
Those remain future productization items.

## Independent test round 1 — 2026-08-04

### Scope, baseline, and safety boundary

- Tester: fresh independent read-only Tester. The retained run `r23005-real-20260803t141820z`
  was not started, resumed, retried, messaged, or otherwise mutated. No producer command, MCP
  producer call, service restart, platform write, key operation, or evidence rewrite was performed.
- Requirement/design revision: `requirements-v2.3.md` R2.3-005, the design and this shared plan at
  the reviewed baseline `2f0bb1eee733c07b795621c6b773a4c0e003c4ff`.
- Worktree check: `git rev-parse --show-toplevel`, `git status --short --branch`, and
  `git rev-parse HEAD` reported the repository root, clean status, and the baseline commit.
- Retained evidence under
  `workspaces/modeling-runs/r23005-real-20260803t141820z/` and its
  `operator/terminal-summary.json` were inspected read-only. The only modified file in this
  round is this test-plan append; no commit was made.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| One semantic start, cap 1, no second start | PASS | `evidence/semantic-start.jsonl` has one record; the formal ledger has 6 lines with exactly one `semantic_start` and no second start; summary reports cap `1`, `semantic_start_count: 1`, and `active_reservation_count: 0`. The historical R2.3-002 ledger remains 92 lines/18 starts. Actual SHA-256 values match summary (`formal=1f79eb...`, `old=4750fa...`). |
| Grounded question and Coordinator prompt | PASS | `evidence/deliveries.jsonl` contains exactly one `delivery-1` with the original grounded question text; `evidence/coordinator.jsonl` contains the same question in the Coordinator prompt. The Coordinator and Modeling session JSONL records corroborate the same delivery and no answer. |
| Required outer records and exact answer input | BLOCKED | No `outer-question.jsonl` or `outer-user.jsonl` exists in the retained run. A run-root scan finds `未知` only in the operator summary; no role session `user_message`, transport delivery, or app-server event contains that answer. Summary says `user_answer_released: false` and `user_answer_injected: false`. |
| Text-only envelope versus schema-v2 owner-answer path | FAIL (P1, `collaboration/routing`) | Requirement `requirements-v2.3.md:460-469` fixes stdin to `{"action":"user","text":"<verbatim answer>"}`. The live path in `modeling_team/__main__.py:80-83` passes that decoded object unchanged to `TeamRunner.receive_outer`; `runner.py:1297-1311` then sends schema-v2 through `_release_owner_answer(..., message.get("question_delivery_id"))`, and `runner.py:1369-1373` rejects a missing/unknown question ID before delivery. `runner.py:1339-1360` only creates the needed question record for a separate `action=question`, which the fixed text-only envelope cannot carry. Existing tests only call schema-1 `receive_outer` (`modeling_team/tests/test_runner.py:526-533, 743-750`) or directly pre-seed an ID and call the private release helper (`modeling_team/tests/test_runner_r63.py:95-101`); no test proves the real v2 stdin path. This is the observed reason the sole start could not receive `未知` and is a real contract mismatch, not a modeling verdict. |
| Protocol/Acceptance semantic gate | BLOCKED (not evaluated) | Protocol session ended awaiting a Modeling request after reading only its private contract/tool inventory; no Build Session, Lease, Modeling Batch, dry-run/apply, readback, validation, reasoning, or semantic receipt exists. Acceptance has no ticket/round/child/report/verdict artifacts. `acceptance-carrier` contains only `evidence/cleanup.json`. Therefore no Modeling PASS/FAIL and no Acceptance PASS/FAIL/BLOCKED can be assigned. |
| PTY termination and lifecycle state | PASS with evidence limitation | `operator/terminal-summary.json` records PTY `90198`, escalation `write_stdin Ctrl-C`, CLI exit `130`, and `answer_envelope_sent: false`; `evidence/aborted.jsonl` records `runner-abort-before-settlement`, `settled: false`, and `state.json` is `CLEANED`. No independent raw PTY transcript or exit record is retained, so exit 130 is summary-only corroborated by the abort/CLEANED records. |
| Scope/resource/credential cleanup | PASS | `state.json` post-delete residual counts are all zero for Project, Ontology, Session, Lease, and project-scoped key; scope is `deleted-empty`, protocol/admin keys are non-active/revoked, and child `active_handles`/residue are zero. Service journal directly records creation, key revocation, DELETE 204, then Project/Ontology GET 404 for the run IDs. Read-only GETs without credentials returned 401 and did not mutate state. |
| Process/socket/private capability residue | PASS | Read-only `ps`, `find -type s`, token/capability searches, and `ss -xl` found no run process, socket, private token, or capability residue (the only `ps` matches were the inspection shell/search itself). Summary reports all corresponding counts as zero. |
| Retained hashes and historical six-item residue | PASS | `source-manifest.json` hashes match every staged source and current source; `runtime-core-hashes.jsonl` before/after hashes match current Runner/Transport/Capability/Codex files; summary formal/old ledger hashes match actual files; all six historical residue artifacts exist with the recorded mode, size, and SHA-256. Run-root file count is 622, equal to the summary secret-scan count, with `bootstrap_secret_occurrences_in_run_root: 0`. |

### Unexecuted or not claimable

- C01-C60 deterministic contract cases and the required full backend/modeling test suites were not
  run in this independent evidence round; the tester did not run producer or mutate test fixtures.
- I01-I14 real modeling-to-acceptance cases were not reached. In particular, no acceptance ticket,
  examiner pair, two sequential CQs, modeling receipt chain, verdict, state invalidation, or four-role
  settlement exists. These remain `BLOCKED`, not PASS.
- No semantic `PASS`, `FAIL`, or `BLOCKED` verdict is asserted for the model. The only stable run
  classification is `BLOCKED/collaboration/routing` before Acceptance and before any modeling-quality
  result.

### Defect and next action

**D1 — P1, collaboration/routing (STILL BLOCKING).** Reproduction: with the real schema-v2 task,
  decode the requirement-mandated stdin line `{"action":"user","text":"未知"}` and pass it through
  `_foreground_event_loop` to `receive_outer`; `question_delivery_id` is absent, so
  `_release_owner_answer` raises `owner answer requires a question delivery ID`. Supplying an ID is
  not a compliant recovery because no outer-question record is created by the text-only envelope and
  an unknown ID is rejected. Expected: the Delivery controller must retain the grounded `delivery-1`
  binding while delivering the exact text-only answer envelope once, producing an immutable outer-user
  record and correlated Coordinator forward. Actual: no outer records or release occurred, and the
  run had to abort before settlement. Smallest repair layer: `collaboration/routing` envelope/driver
  binding (plus a real schema-v2 stdin-to-release regression test); do not rerun the producer until
  that repair is independently verified.

**D2 — P2, evidence completeness (observation).** PTY exit 130 is present only in the operator
  summary; no retained raw PTY transcript or machine-readable exit artifact was found. The abort
  record, CLEANED state, cleanup counts, and direct service journal corroborate termination/cleanup,
  but a future run should retain a sanitized PTY exit receipt so this fact does not rely on operator
  self-report alone.

### Round conclusion

**Overall verdict: BLOCKED.** Resource cleanup, one-start accounting, source/question fidelity,
hash integrity, and zero-residue checks pass. The one real run cannot be accepted because the
requirement-mandated text-only answer envelope has no working schema-v2 `question_delivery_id`
binding path; Protocol and Acceptance semantic acceptance never began, so no modeling PASS/FAIL is
permitted. Require the requirement developer to repair D1 and add a real schema-v2 stdin regression
test, then perform a new independent round only with explicit authorization for any new semantic
start.
