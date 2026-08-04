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
| C61 | Requirement-specific ledger resolver | CLI `--requirement-id` resolves only fixed identities: omission is legacy R2.3-002 and formal R2.3-005 is explicit; unknown ID, filename/root override, and configuration mismatch fail before file creation |
| C62 | R2.3-005 exact +3 authorization | exhausted cap 1 appends one immutable authorization and replays cap 4 with one consumed/three remaining |
| C63 | R2.3-005 malformed authorization | +1, +2, +4, bool, blank ID/reference and forged ledger records fail without changing bytes |
| C64 | Legacy R2.3-002 budget compatibility | initial cap and exact +2 authorization behavior remain unchanged; historical ledger bytes are untouched |
| C65 | Authorization ordering | under one lock, latest real semantic start -> retryable incomplete terminal failure -> exhausted-cap +3 budget -> first exact repair baseline is enforced; wrong order or run leaves bytes unchanged |
| C66 | Authorization identity/concurrency | duplicate ID/reference and concurrent contenders at each management event yield exactly one valid append and deterministic replay |
| C67 | Retry gate remains mandatory | cap 4 or an interrupted failure/budget prefix cannot reserve; the complete ordered chain and exact tested repair baseline are required |
| C68 | Complete modeling-quality stop | modeling-quality or complete semantic result cannot authorize the next reservation despite remaining cap |
| C69 | Presemantic release accounting/rebind | after exactly one fresh reservation consumes the prior repair, never starts semantically, is released, and leaves no active reservation, one non-empty different baseline repair for the same failed run succeeds without new budget; fresh run ID remains required |
| C70 | Ledger mutation isolation | tests use temporary ledgers; implementation/test runs never mutate either live ledger or retained run evidence |
| C71 | Interrupted authorization resume | stopping after failure or budget leaves a valid prefix that cannot reserve; the exact next event resumes once without rewrite or duplicate append |
| C72 | Formal canonical ledger root | production formal Runner rejects a noncanonical caller `ledger_root` before file access; temporary tests use only the resolver/factory seam |
| C73 | Presemantic rebind fail-closed cases | unused repair, active/unreleased reservation, semantic-started reservation, different failed run, blank/equal baseline, duplicate/replay and concurrent rebind reject without byte changes except one valid concurrent winner |
| C74 | Foreground display binding | after successful foreground emit, only the exact Runner-generated formal question `delivery_id` is marked displayed and evidenced once |
| C75 | Failed emit is not display | an emitter exception leaves the question undisplayed, writes no `outer-question` evidence, and a later owner answer fails closed |
| C76 | Display envelope integrity | unknown ID or sender/recipient/text/reply/run/Project/origin drift cannot mark display; contradictory known-ID input fails without mutation |
| C77 | Display replay and ambiguity | duplicate exact emit is idempotent, consumed/late emit cannot reopen, and two actually displayed pending questions make text-only input fail as ambiguous |
| C78 | Coordinator prose is non-authoritative | verbatim, paraphrased, or absent Coordinator prose neither creates nor selects formal display binding; no fuzzy/ordered inference exists |
| C79 | Explicit unknown owner release | after exact display binding, literal `未知` is durably recorded once and released directly to the originating Modeling question with existing IDs intact |
| C80 | Legacy routing compatibility | schema-v1 and non-formal/schema-v2 paths preserve their historical Coordinator routing and do not require the new formal foreground-display contract |
| C81 | Production-shaped display path | formal normalize/prepare/start/live-scope/drain/emit plus Coordinator paraphrase and `未知` release succeeds without model/network calls and cleans all test-double residue |
| C82 | Receive-outer display path | a formal question first returned by `receive_outer()` is marked only after that output's successful emit; failure and success behavior matches top-of-loop `drain()` |
| C83 | Display evidence failure atomicity | validate the whole emitted batch before mutation; mixed valid/contradictory input changes nothing, and open/write/fsync failure cannot leave displayed state without durable evidence or allow owner input |

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
| I15 | Three-start authorization gate | before any new Producer, append-only evidence shows R2.3-005 cap 4/start count 1/active 0 plus prior retryable failure and repair authorization bound to the fresh baseline; R2.3-002 ledger hash is unchanged |
| I16 | Retry3 display repair and final-start gate | retry3 is recorded as incomplete collaboration/routing only after offline repair PASS; a fresh start4 baseline receives the sole repair authorization with no budget event, then the exact emitted question can accept one grounded `未知` response |

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
modeling run requires explicit new user authorization. The user supplied exactly three additional
starts on 2026-08-04; they are serialized repair retries, stop at the first accepted PASS or complete
modeling-quality failure, and do not expand the single successful-slice target.

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

## Independent test round 2 — 2026-08-04

### Scope, baseline, and safety boundary

- Tester: fresh independent read-only requirement Tester. This round validated only the offline D1
  `collaboration/routing` repair. No Producer, semantic start, Project/Ontology, MCP producer call,
  service restart, ledger write, run-root write, credential/key operation, or retained-run mutation
  was performed. The retained round-1 run remains `BLOCKED`; this round does not authorize another
  real start.
- Authority: `requirements-v2.3.md:460-469,1197-1204,1257-1275`; repair plan
  `docs/delivery/implementation-plans/2026-08-04-r2-3-005-schema-v2-outer-answer-routing.md`;
  this shared test plan.
- Code version: `git rev-parse HEAD` =
  `8c5c38c62d448ae90fe5f2ddfff63ba10fedb547`; implementation is uncommitted in the six expected
  `modeling_team/` runtime files plus the new focused test. The only test-plan change in this round
  is this append; no commit was made.
- Worktree/path check: `git status --short --branch` showed only those six implementation files and
  `modeling_team/tests/test_runner_r23005_owner_answer.py`; no backend, ledger, or
  `workspaces/modeling-runs` path changed. Recent-file scan found no run-root modifications. Added
  lines contained no secret-like material; `git diff --check` passed.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| Foreground JSONL decoder and cleanup boundary | PASS | `python3 -m unittest modeling_team.tests.test_runner_r23005_owner_answer -v`: 12/12 passed. Covers text-only `{"action":"user","text":...}`, exact schema-v2 keys, object/non-object/null/scalar/malformed/duplicate-key rejection (including nested duplicate), caught `main` failures, and one `cleanup()` call per rejected line. |
| Formal question observation and direct owner release | PASS | Focused suite proves only acknowledged Modeling→Coordinator `expects_reply` candidates are registered, exact Coordinator prompt matching marks visibility, zero/multiple/unshown candidates fail closed, and the text-only answer routes exactly once to originating Modeling with no Coordinator duplicate. |
| Question-ID consumption and failure burn | PASS | Focused suite covers success replay plus open/write/fsync persistence failures, Broker publication failure, and Runtime Adapter send failure; same or different text cannot allocate a second owner ID/release, record, or send. |
| Outer-user identity/order and typed payload | PASS | Focused tests plus a temporary fixture check verified the exact nine record keys, canonical `owner-answer-` SHA-256 preimage (`run_id, project_id, question_delivery_id, text`), exact Unicode/newline text, `delivery_id == release_id`, fsync-before-Broker ordering, direct Modeling recipient, and owner fields in Codex/Runtime envelopes. |
| Broker atomic direction/collision/lifecycle/terminal gates | PASS | Focused Broker tests reject duplicate/colliding publication, wrong direction, non-question/reply requests, and inactive/unacknowledged requests without state mutation. Modeling terminal reporting is blocked until the owner reply is delivered and acknowledged; then normal terminal reporting proceeds. |
| Legacy compatibility | PASS | Existing Runner/Transport/Codex/CLI regression command (`test_runner`, `test_runner_r63`, `test_transport`, `test_codex_isolation`, `test_foreground_monitor`) passed 88/88; schema-v1 outer-user and normal Delivery envelope tests remain green. |
| R2.3-005 regression set | PASS | `python3 -m unittest -v` over `test_r23005_a_revision`, `test_r23005_b_runtime`, `test_r23005_c_settlement`, `test_r23005_contracts`, `test_r23005_ledger_isolation`, and `test_r23005_t6_repeatability`: 67/67 passed. |
| Complete modeling_team discovery | PASS | Repository environment command `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`: 266/266 passed in 10.716s (exit 0). This supersedes an earlier system-Python attempt that collected a non-equivalent 267 and failed on unavailable/mismatched backend dependencies. |
| Ruff and whitespace | PASS | `backend/.venv/bin/ruff check modeling_team`: all checks passed; `git diff --check`: passed. |
| Secret/forbidden-path/side-effect review | PASS | Diff/status scans found no secret additions and only expected `modeling_team/` files; no backend, ledger, run-root, service, Producer, or retained evidence side effects were observed. |

### Unexecuted or not claimable

- No real Producer or semantic start was started, resumed, retried, or authorized. The retained
  round-1 run therefore remains `BLOCKED/collaboration/routing`; this deterministic round cannot
  prove Modeling quality, Protocol/Acceptance semantics, real source fidelity, or settlement.
- Backend pytest, service restart, and endpoint health checks were not in scope because the repair
  touched only `modeling_team/` and explicitly remained offline.

### Defects and conclusion

- No D1 product defect was reproduced. The focused, related, R2.3-005, and complete repository
  suites all pass in the repository's `uv` environment. No repair follow-up is requested for D1;
  preserve the prohibition on a real Producer rerun until separately authorized.

### Round conclusion

**Overall verdict: PASS for D1 deterministic schema-v2 outer-answer routing only.** This closes the
offline routing defect and does not change the retained round-1 `BLOCKED` result or authorize a new
semantic start.

## 2026-08-04 three-start budget extension — Independent round 1

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. Authority was `requirements-v2.3.md` R2.3-005's
  2026-08-04 authorization section, the approved three-start implementation plan, this shared plan,
  and shared cases C61-C73/I15. The checkout was at `HEAD=65e39931e5ea803533f0ae55d5354d854959595f`
  (short `65e3993`), with the Developer's uncommitted changes limited to
  `modeling_team/__main__.py`, `modeling_team/runner.py`, `modeling_team/start_ledger.py`,
  `modeling_team/tests/test_r23005_budget_extension.py` (untracked),
  `modeling_team/tests/test_r23005_contracts.py`, and
  `modeling_team/tests/test_r23005_ledger_isolation.py`.
- The six changed-file SHA-256 values at test time were: `start_ledger.py`
  `fa5b558464efaf66379e84491433b0e5c831aa727fb3b016c304f981919860ad`, `runner.py`
  `bff7789a91db7c7a25b0e3e581e1b7cc867061756beb75f62dad54fb073b2f59`, `__main__.py`
  `45665d17c7cbf1fa7708422203592ef9597730502d482788db19e6c44c48b269`,
  `test_r23005_budget_extension.py`
  `4648ab8b9355636fc61ff1b197ae9c47b02e316f8570c339f39580774254e302`,
  `test_r23005_contracts.py`
  `a210c53a3f5c8e62fc680231373939cc9755b585d5f00fcffe9f49ac4bb7d535`, and
  `test_r23005_ledger_isolation.py`
  `6198fcce234b1e54f47b12c228481cf12a5a795d02a59d5b6f975d252f5c879c`.
- No Producer/Agent, real semantic modeling, backend/frontend change, service restart, key/API
  operation, live ledger append, or retained-run/evidence mutation was performed. Temporary ledger
  fixtures and one temporary `prepare()` probe run root were cleaned after each check; no probe
  reservation reached `semantic_start`.

### Commands and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| R2.3-005 focused tests | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_budget_extension modeling_team.tests.test_r23005_contracts modeling_team.tests.test_r23005_ledger_isolation`: 55/55 passed. This covered resolver/default CLI, exact `+3`, strict ordering/replay, retry gate, presemantic rebind and fail-closed cases, temporary ledger isolation, and formal alternate `ledger_root` rejection. |
| R2.3-002/R63 focused regression | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_start_ledger_r63 modeling_team.tests.test_r23002 modeling_team.tests.test_runner_r63`: 43/43 passed; legacy exact `+2` behavior and historical contracts remained green. |
| Complete `modeling_team` discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`: 280/280 passed, exit 0 (10.939s). ResourceWarning/RuntimeWarning diagnostics were emitted by existing test/runtime paths but did not fail the suite. |
| Ruff and whitespace | PASS | `backend/.venv/bin/ruff check` over the six changed files passed; `git diff --check` passed. |
| GitNexus change review | PASS with limitation | `detect_changes(scope=compare, base_ref=main)` reported changed_files=5, changed_count=38, risk=low, affected_processes=[]; the untracked focused test is not indexed. `list_repos` reports the ontology-platform index at commit `286da60`, 14 commits behind HEAD, so this graph result is stale and not relied on to clear the canonical-root defect. |
| Live ledger and retained evidence immutability | PASS | Before and after all tests: R2.3-002 ledger size/mtime `21723 / 2026-08-02 18:17:55.574240726 +0800`, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; R2.3-005 ledger size/mtime `1225 / 2026-08-03 22:23:13.419389929 +0800`, SHA-256 `1f79ebd99de45de8cd2f78141e4ef25250203306c2638345aaf6e21b1968e079`; retained run `workspaces/modeling-runs/r23005-real-20260803t141820z/` file-list digest `0454c16f29e1011784692d2398b556c169c9de4b0ebb53666ca16373c2a38138` unchanged. |

### Canonical-root seam adversarial check

**D3 — High, `platform-contract` (NEW, STILL FAILING).** The formal production Runner must reject
any alternate ledger root before ledger access and use only the repository canonical
`workspaces/modeling-runs` ledger. The implementation rejects a caller-supplied `ledger_root`, but
`TeamRunner.__init__` also accepts `ledger_factory` and `_create_ledger()` validates only the returned
`StartLedger.config`; it never verifies that `value.path` and `value.lock_path` are under the
canonical root. A production caller can therefore supply the same factory seam used by temporary
tests and bypass the shared formal cap.

Minimal reproduction (executed with a temporary directory and no semantic start): instantiate a
formal `TeamRunner` with `ledger_root=None` and
`ledger_factory=lambda *, root, config, now: StartLedger(tmp / "attacker-ledger", config=config, now=now)`;
stub the already-required clean/canonical preflight; call `prepare()` with the formal Profile/Task.
Expected: fail closed before any alternate ledger file is opened or written. Actual:
`prepare_status=accepted`, `runner._ledger.path=/tmp/.../attacker-ledger/.r2-3-005-start-ledger.jsonl`,
and that alternate file was created with a `reservation` record. The canonical formal ledger hash
remained `1f79ebd99de45de8cd2f78141e4ef25250203306c2638345aaf6e21b1968e079` before, during, and after
the probe; the temporary ledger and run root were removed in cleanup. This is a production bypass of
C72/I15's shared-budget isolation, not merely a test failure. The temporary factory seam must be
made non-bypassable (or otherwise proven test-only) before an independent PASS or live authorization.

### Unexecuted or not claimable

- I15 cannot be claimed: the live formal ledger still contains only six historical records
  (two presemantic-release pairs and the one consumed `semantic_start`), with no new
  `terminal_failure`, `+3 budget_authorization`, or repair authorization. The Tester did not append
  those records because live-ledger mutation and a new Producer start are outside this round.
- No real four-role Producer, modeling-quality result, Acceptance round, or semantic settlement was
  started. Backend pytest, service restart, and endpoint health checks were not in scope because no
  backend/frontend surface changed. These remain unexecuted/BLOCKED, not PASS.

### Round conclusion

**Overall verdict: FAIL.** All deterministic budget/legacy/isolation suites and side-effect checks
passed, but D3 is a High `platform-contract` defect: the public factory seam allows a formal Runner
to reserve against an alternate ledger root. Require the requirement developer to close that seam,
add a regression proving a formal factory cannot redirect the ledger path, and then perform a new
independent round before any live `+3` authorization or Producer retry. No product code was modified
by this Tester; only this append-only test-plan record was changed.

## 2026-08-04 three-start budget extension — Independent round 2

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester, reusing the preceding round's cases and this same test
  plan. The Developer's D3 repair baseline was ready before this round: formal factory results now
  require exact canonical ledger and lock paths, the deterministic temporary seam constructs its
  ledger at the Runner-supplied canonical root, and a malicious redirect regression was added.
- Code/worktree baseline: `HEAD=65e39931e5ea803533f0ae55d5354d854959595f` (`65e3993`), with only
  the expected implementation/tests plus this test-plan file changed. Changed-file SHA-256 values
  were `start_ledger.py` `fa5b558464efaf66379e84491433b0e5c831aa727fb3b016c304f981919860ad`,
  `runner.py` `98d7c7bde5e75b39e0dc0e4df91b392025d3ed925acea2b14313e1ae33019a15`, `__main__.py`
  `45665d17c7cbf1fa7708422203592ef9597730502d482788db19e6c44c48b269`,
  `test_r23005_budget_extension.py`
  `4648ab8b9355636fc61ff1b197ae9c47b02e316f8570c339f39580774254e302`,
  `test_r23005_contracts.py`
  `37a28f40e3b8e0de6bf1975366f805da92e816015987def6c7d9425b0cd39e7f`, and
  `test_r23005_ledger_isolation.py`
  `97d710a1547be2114820180e1db4c145ccd14a03e52b09ab73ac9b5f88969713`.
- No Producer/Agent, real semantic modeling, backend/frontend operation, service restart,
  credential/key operation, live ledger append, or retained-run/evidence mutation was performed.
  The adversarial and legal-seam probes used temporary roots and unique temporary run IDs; every
  reservation was presemantic and all temporary run roots were removed.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| Repaired R2.3-005 focused set | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: 82/82 passed (8.751s). The direct modified-file subset also passed 56/56, including the new malicious redirect regression and all C61-C73 deterministic cases. |
| R2.3-002/R63 focused regression | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_start_ledger_r63 modeling_team.tests.test_r23002 modeling_team.tests.test_runner_r63`: 43/43 passed (1.207s). Legacy `+2`/historical behavior remained unchanged. |
| Full `modeling_team` discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`: 281/281 passed (10.860s, exit 0). Existing ResourceWarning/RuntimeWarning and expected negative-path stderr were non-failing diagnostics. |
| Required chain at cap 4 | PASS | Independent temporary-ledger probe executed start 1, exact `terminal_failure`/`+3`/repair, then starts 2 and 3 with retryable failure→repair without another budget, and start 4. State ended `semantic_start_count=4`, `cap=4`; all event ordering was exact. A separate probe stopped at count 2/cap 4 after `complete_modeling_quality_result=true`; budget, repair, and next reserve were all rejected with bytes unchanged. |
| Canonical factory seam (malicious redirect) | PASS / D3 FIXED | Independent formal `prepare()` with a factory returning `StartLedger(tmp/attacker, config=...)` was rejected before reservation with `ledger factory returned paths outside the canonical ledger root`; attacker and canonical files did not exist, `runner._ledger is None`, and no run root remained. |
| Canonical factory seam (legal temporary root) | PASS | Independent resolver override set a temporary canonical root; a factory that honored the supplied `root` was accepted, and both ledger and lock resolved exactly under that canonical root with only a presemantic `reservation`. Cleanup removed the temporary run/root. |
| Ruff and whitespace | PASS | `backend/.venv/bin/ruff check` over all six changed implementation/test files passed; `git diff --check` passed. |
| GitNexus change review | PASS with limitation | `detect_changes(scope=compare, base_ref=main)` reported changed_files=6, changed_count=38, affected_count=0, risk=low, affected_processes=[]; the untracked budget-extension test remains outside the index. `list_repos` reports the ontology-platform index at commit `286da60`, 14 commits behind HEAD, so this graph result is stale and is only supplemental evidence. |
| Live ledger and retained evidence immutability | PASS | Before/after: R2.3-002 ledger size/mtime `21723 / 2026-08-02 18:17:55.574240726 +0800`, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; R2.3-005 ledger size/mtime `1225 / 2026-08-03 22:23:13.419389929 +0800`, SHA-256 `1f79ebd99de45de8cd2f78141e4ef25250203306c2638345aaf6e21b1968e079`; retained run `workspaces/modeling-runs/r23005-real-20260803t141820z/` digest `0454c16f29e1011784692d2398b556c169c9de4b0ebb53666ca16373c2a38138` unchanged. |

### Defect disposition

- **D3 — FIXED.** The path/lock equality check rejects a factory redirect before `reserve()`, while
  the legal test seam remains available only when it honors the canonical root supplied by Runner.
  The independent malicious redirect and legal-seam probes both produced the required outcomes.
- No Critical, High, or ordinary product defect remains in the tested offline scope.

### Unexecuted or not claimable

- I15 and the live authorization gate remain unexecuted by design: the live formal ledger still has
  only six historical records (two presemantic-release pairs and one consumed `semantic_start`),
  with no new `terminal_failure`, exact `+3 budget_authorization`, or repair authorization. The
  Tester did not append or reserve against it. Delivery must perform that append-only sequence after
  the implementation is committed and retain its receipt before any Producer retry.
- No real four-role Producer, Modeling/Protocol quality result, Acceptance rounds, or settlement was
  started. Backend pytest, service restart, and endpoint health checks remain out of scope because
  no backend/frontend surface changed. These are not claimed as PASS.

### Round conclusion

**Overall verdict: PASS for the R2.3-005 three-start deterministic budget-extension and canonical
ledger contract.** Round 1's High D3 is fixed and independently verified; legacy compatibility,
strict chain/rebind behavior, complete-modeling stop, concurrency, and side-effect isolation all
pass. This PASS authorizes the Delivery Agent to follow the reviewed post-commit append-only
authorization procedure, but does not itself authorize a Producer start or claim the unexecuted
real I15/semantic acceptance gate.

## 2026-08-04 — Independent round 3 clean-commit confirmation

- Clean-commit baseline: `git status --porcelain=v1` was empty and `HEAD` was exactly
  `6c9bf4a3083892d2bf579bb97009f2f582fd66dc` (`6c9bf4a`, `Add R2.3-005 retry budget`). This commit
  contains the Round 2 implementation/test content with no drift. The six Round 2 SHA-256 values
  matched exactly: `start_ledger.py` `fa5b558464efaf66379e84491433b0e5c831aa727fb3b016c304f981919860ad`,
  `runner.py` `98d7c7bde5e75b39e0dc0e4df91b392025d3ed925acea2b14313e1ae33019a15`, `__main__.py`
  `45665d17c7cbf1fa7708422203592ef9597730502d482788db19e6c44c48b269`,
  `test_r23005_budget_extension.py` `4648ab8b9355636fc61ff1b197ae9c47b02e316f8570c339f39580774254e302`,
  `test_r23005_contracts.py` `37a28f40e3b8e0de6bf1975366f805da92e816015987def6c7d9425b0cd39e7f`, and
  `test_r23005_ledger_isolation.py` `97d710a1547be2114820180e1db4c145ccd14a03e52b09ab73ac9b5f88969713`.
- Independent commands/results: managed R2.3-005 discovery (`-p 'test_r23005*.py'`) **82/82 PASS**;
  independent malicious canonical factory redirect **REJECTED before access** with no attacker,
  canonical, or run-root files; legal temporary canonical seam **PASS** with exact ledger/lock paths
  and reservation-only state; R2.3-002/R63 focused **43/43 PASS**; full managed discovery **281/281
  PASS**; Ruff and `git diff --check` **PASS**. GitNexus `detect_changes(scope=compare, base_ref=main)`
  reported no changes (`changed_count=0`, `risk=none`); its index is stale by 15 commits and that
  limitation remains recorded.
- Side-effect audit: before/after, R2.3-002 ledger remained size/mtime `21723 /
  2026-08-02 18:17:55.574240726 +0800`, SHA-256
  `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; R2.3-005 ledger remained
  size/mtime `1225 / 2026-08-03 22:23:13.419389929 +0800`, SHA-256
  `1f79ebd99de45de8cd2f78141e4ef25250203306c2638345aaf6e21b1968e079`; retained run digest remained
  `0454c16f29e1011784692d2398b556c169c9de4b0ebb53666ca16373c2a38138`. No product code, ledger,
  retained evidence, or runtime resource was modified; no Producer/Agent or semantic start ran.
- I15/live append remains unexecuted: the Delivery Agent must still append the ordered
  `terminal_failure`, exact `+3 budget_authorization`, and repair authorization after this clean
  commit before any Producer retry.

**Round 3 conclusion: PASS — clean committed baseline confirmed with no drift.** This round closes
the baseline-evidence discrepancy only; it does not claim live authorization or real semantic
acceptance.

## 2026-08-04 retry2 live project-binding repair — Independent round 1

### Scope, baseline, and safety boundary

- Tester: fresh independent Requirement Tester. This round validated only the uncommitted repair
  in `modeling_team/runner.py` and
  `modeling_team/tests/test_runner_r23005_owner_answer.py`; no product fix, commit, ledger append,
  retained-evidence rewrite, Producer/Agent launch, platform write, service restart, or semantic
  modeling was performed.
- Authority: `docs/requirements/requirements-v2.3.md` R2.3-005,
  `docs/delivery/implementation-plans/2026-08-04-r2-3-005-live-project-binding-repair.md`, the
  latest R2.3-005 delivery record, and this shared test plan. The checkout was at HEAD
  `d8e31b2573d9888f5cd652877c1595694dc0db47` with exactly the two developer files modified.
- Before testing, the live formal ledger was SHA-256
  `b52f539e9a8a20b453ef382cef02d0a72404152ff715e994e533c7570f5338c9`, size `2427`, mtime
  `2026-08-04 10:28:17.994219457 +0800`; the historical R2.3-002 ledger was SHA-256
  `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`, size `21723`, mtime
  `2026-08-02 18:17:55.574240726 +0800`. The retry2 retained tree
  `workspaces/modeling-runs/r23005-real-20260804t021921z-retry2/` had 45896 sorted filename bytes
  and digest `b5f893826da25c66eafd04751cbc6a47fbe9ae11644d9ded55ed2156340d8788`.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| Formal binding helper/call-site review | PASS | `_project_binding()` branches on the existing `_formal_coordination_enabled()` predicate; formal mode reads only non-empty `self.scope.project_id`, non-formal mode reads only `self.run.scope["project_id"]`, and no branch writes `run.scope`. The four required owner-question paths (`_observe_modeling_question`, `_resolve_formal_owner_question`, `_record_outer_question`, `_release_owner_answer`) use the helper for project binding, while existing nine-field owner identity/hash, authorization/release IDs, display/consume gates, run/project/origin drift and duplicate/replay checks remain present. |
| Focused owner-answer suite | PASS | `uv run --project backend python -m unittest modeling_team.tests.test_runner_r23005_owner_answer`: 15/15, exit 0. This includes exact text-only schema-v2 release, owner identity/evidence, replay/failure burn, direction/ack, and envelope rejection cases. |
| Focused Runner and legacy R63 suite | PASS | `uv run --project backend python -m unittest modeling_team.tests.test_runner_r63 modeling_team.tests.test_runner`: 21/21, exit 0. |
| Production-shape live Project binding | PASS | `uv run --project backend python -m unittest -v` on the three repair regressions: 3/3. The integration test executes `TeamRunner.prepare()` with formal `normalize_formal_scope`, `start()`, a no-network `scope_factory` whose `prepare({"mode":"create"})` creates a live ID, then `drain()` on the first Modeling `expects_reply`. It proves mode-only `run.scope`, generated live ID in outer-question/outer-user/owner records, caller Project smuggling rejection, zero model calls, and zero test-double residue after cleanup. |
| Independent missing-live-scope reproduction | PASS | A separate temporary-ledger `prepare()` -> `start()` -> live-scope-ID removal -> Modeling question -> `drain()` probe failed exactly with `outer question project binding is missing` before creating `outer-question`/`outer-user` evidence; `run.scope` stayed `{"mode":"create"}`, question consumption stayed false, and cleanup residue was empty. The temporary run root was removed. |
| Formal missing binding and legacy schema-v2 compatibility | PASS | The focused regression also proves missing live binding fails before outer evidence mutation, and a schema-v2 R2.3-002-shaped non-formal run continues to bind `run.scope.project_id` even when `self.scope.project_id` contains a different ID. |
| All R2.3-005 tests | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: 82/82, exit 0. |
| Canonical managed `modeling_team` discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`: 284/284, exit 0. Existing ResourceWarning/RuntimeWarning and expected negative-path stderr were non-failing diagnostics. A non-canonical system-Python discovery was not used as acceptance evidence; it collected 285 and had four `ModuleNotFoundError: app` errors because backend was not on the environment path. |
| Ruff and whitespace | PASS | `uv run --project backend ruff check modeling_team`: all checks passed; `git diff --check`: exit 0. |
| GitNexus change review | PASS with stale-index limitation | `detect_changes(scope=unstaged)` and `detect_changes(scope=compare, base_ref=main)` each reported changed_files=2, changed_count=3, affected_count=0, risk `low`, and no affected processes. `.gitnexus/meta.json` records indexed commit `286da60c0680cd46b49e9f69e91572ba6e9c6b51` at `2026-08-02T15:52:38Z`, while checkout HEAD is `d8e31b2`; therefore the graph result is stale and supplemental only. |

### Side effects and unexecuted scope

- After all commands, both live ledgers retained the exact pre-test SHA-256, size, and full mtime
  values above; retry2 retained-tree digest and sorted filename-byte count remained exactly
  `b5f893826da25c66eafd04751cbc6a47fbe9ae11644d9ded55ed2156340d8788` / `45896`. `git status`
  still showed only the two developer files. No other run root, socket, credential, Project,
  Ontology, Session, Lease, or evidence residue was created; the one independent temporary run
  root was explicitly removed after cleanup.
- No backend/frontend file changed, so backend pytest, service restart, and endpoint health checks
  were not required by the repository gate. No real retry3 authorization sequence, terminal/repair
  ledger mutation, Producer start, semantic model, Acceptance round, or terminal settlement was
  executed. I15 and semantic acceptance remain unclaimed. The known clean-HEAD P2a frozen-hash
  concern was not turned into a PASS claim or a requested hash change.

### Defects and conclusion

- No defect found in the reviewed live Project-binding repair. The prior retry2 failure is covered
  by the production-shaped regression and is **FIXED** in this worktree. No STILL FAILING,
  REGRESSION, or BLOCKED case remains within the authorized offline scope.

**Round 1 conclusion: PASS for the deterministic live Project-binding repair and its adjacent
  owner-answer/legacy regression scope.** This PASS authorizes the parent Delivery flow to commit
  the two reviewed files and, only afterward, perform the exact retry2 terminal-failure -> fresh
  retry3 baseline/repair authorization sequence. It is not an I15 or real semantic acceptance PASS.

## 2026-08-04 retry3 display-binding repair — Independent round 1

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. The reviewed repair is the uncommitted worktree at
  `HEAD=15f3cd723994ea76aebf32732a4adde7ccbf3c78` (`Fix R2.3-005 live project binding`). The
  implementation/test hashes matched the Developer handoff exactly: `modeling_team/__main__.py`
  `c526569eca492e7f9b64d32ed03f17d784fa1d45cbe55ef86a6998b0a9d7cf69`,
  `modeling_team/runner.py`
  `2c64296e0f4ae438f8d3dbc6e86702e4b56d9c06f3341f50208ecf597ef22382`, and
  `modeling_team/tests/test_runner_r23005_owner_answer.py`
  `8fb6a23f27d5a4aaa4cd0933db2c9c3f920917875274645f3dd7376d61f3b352`.
- Authority and reused plan: `docs/requirements/requirements-v2.3.md` R2.3-005,
  `docs/delivery/implementation-plans/2026-08-04-r2-3-005-outer-display-binding-repair.md`,
  and this shared test plan (C74-C83/I16). The approved missing-score business response remains
  the literal `未知`; no business semantics were changed.
- No Producer/Agent was launched. No semantic start, reservation, ledger append, platform write,
  credential/key operation, retained-evidence rewrite, backend/frontend change, service restart,
  or commit was performed. The only repository edit in this round is this append-only test-plan
  section; the main agent retains ownership of the delivery record.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| Review of implementation and exact display contract | PASS | `observe_foreground_output()` validates the entire emitted batch by exact Runner `delivery_id`, immutable sequence/timestamp/text/route/reply fields, and current run/Project/origin binding; the foreground loop invokes it after successful `emit()` on both `drain()` and `receive_outer()` paths. Coordinator prose is a no-op for formal display. |
| C74-C79 focused owner-answer/display suite | PASS | `uv run --project backend python -m unittest modeling_team.tests.test_runner_r23005_owner_answer`: **23/23**, exit 0. Covers successful exact binding/evidence, failed emit, all envelope/binding drift cases, duplicate/consumed/multiple ambiguity, non-authoritative Coordinator paraphrase/absence, direct Modeling release, and the owner-answer schema/replay gates. |
| C80 legacy routing regression | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_start_ledger_r63 modeling_team.tests.test_r23002 modeling_team.tests.test_runner_r63`: **43/43**, exit 0. Legacy schema-v1 and non-formal schema-v2 owner routing remain intact. |
| C81 production-shaped live-scope path with literal unknown | PASS | Existing deterministic prepare/start/live-scope test passed within the focused suite. An additional no-network temporary-run probe performed formal normalize/prepare/start, sent one Modeling question, post-emit-bound it, released the literal `未知` directly to Modeling with the original `reply_to_delivery_id` and new owner/release IDs, and cleaned the test-double scope to zero residue. Model call count was zero. |
| C82 receive-outer display path | PASS | `test_receive_outer_output_uses_post_emit_display_hook` proves success through `receive_outer()` uses the same post-success hook; `test_receive_outer_emit_failure_does_not_bind_question` proves an emitter exception leaves it undisplayed and no display evidence. |
| C83 batch/evidence failure atomicity | PASS | Mixed valid-plus-contradictory batch is rejected before either record mutates. Open, write, and fsync injections leave `displayed=false` and fail the subsequent owner answer; foreground evidence failure is observed before `select()`/`receive_outer()`, so no owner input is consumed. Duplicate exact envelopes remain one evidence record. |
| All R2.3-005 managed discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: **82/82**, exit 0. |
| Complete managed `modeling_team` discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`: **292/292**, exit 0. Existing ResourceWarning/RuntimeWarning and expected negative-path stderr were non-failing diagnostics. |
| Ruff and whitespace | PASS | `uv run --project backend ruff check modeling_team` and `git diff --check`: exit 0; Ruff reported `All checks passed!`. |
| GitNexus change review | PASS with limitation | `detect_changes(scope=unstaged, repo=ontology-platform)` and `detect_changes(scope=compare, base_ref=main, repo=ontology-platform)` both reported `changed_files=5`, `changed_count=3`, `affected_count=0`, risk `low`, and no affected processes. The index is stale (`.gitnexus/meta.json` lastCommit `286da60c0680cd46b49e9f69e91572ba6e9c6b51`, checkout `15f3cd7`), so this graph result is supplemental and did not independently model the new observer symbol. |
| Live-ledger and retained retry3 immutability | PASS | Before/after R2.3-005 ledger stayed 15 lines/3355 bytes, SHA-256 `405832f8ccb08b905cc1c9c8bb84ca34ed38b70864ff789ac13d23e0a1799d1c`, mtime `2026-08-04 11:13:29.982439282 +0800`; R2.3-002 stayed 92 lines/21723 bytes, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`, mtime `2026-08-02 18:17:55.574240726 +0800`. Retained retry3 tree `workspaces/modeling-runs/r23005-real-20260804t030823z-retry3/` stayed 645 files, 27,281,986 bytes by `du -sb`, with canonical file-content/name digest `aef3a98d236e5622e8033a640520ff2187961d12312de77fef946dea6c956421`. |

### Defect disposition

- No Critical, High, or ordinary product defect was found in C74-C83. The retry3 defect remains
  correctly classified as `collaboration/routing`; the exact post-emission binding repair is
  independently **FIXED** within the deterministic offline scope.
- Residual limitation: GitNexus is stale by multiple commits and therefore cannot be treated as
  complete graph evidence until re-indexed. This does not block the focused test verdict because
  the direct suites and side-effect audit pass.

### Unexecuted or not claimable

- I16 live gate is not claimed: retry3 `terminal_failure`/repair ledger events, a fresh start4
  baseline and reservation, real four-role modeling, semantic quality, Acceptance rounds, and
  final settlement were intentionally not executed by the Tester. The Delivery Agent must perform
  the exact append-only authorization sequence only after the committed repair and this PASS.
- Backend pytest, service restart, and backend/frontend endpoint health were not required because
  no backend/frontend surface changed. No new runtime residue was left; the additional temporary
  production-shaped scope was cleaned and verified empty.

### Round conclusion

**Overall verdict: PASS for the R2.3-005 retry3 deterministic outer display-binding repair and
adjacent C74-C83 regression scope.** No developer fix is requested before commit. This PASS is not
an I16 live authorization or real modeling-quality acceptance; proceed only through the reviewed
post-commit retry3 terminal-failure -> fresh start4 baseline/repair gate.

## 2026-08-04 start4 retained failure audit — Independent round 1

### Scope, authority, and safety boundary

- This round is an independent, read-only audit of the retained failed run
  `r23005-real-20260804t040655z-start4`. It validates evidence integrity, the recorded failure
  classification, cleanup, source/display binding, and current service health. It does not create
  or continue a run, append a live ledger event, mutate a platform resource, use a credential, edit
  product code, rewrite retained evidence, or edit the delivery record.
- The reused authority is R2.3-005 in `docs/requirements/requirements-v2.3.md`, the retained run
  root and formal start ledger, the task snapshot, and this shared test plan. At the read-only
  baseline `HEAD` was `bc698a569d9bbaf9229f4b9a68e662fb9bb22ad0`; the worktree also contained
  unrelated parent edits to the delivery record and requirement file, which this Tester did not
  revert or modify.
- The test-plan file itself was SHA-256
  `821a1af2bd154adaf20c0c7d93e7306f7089649badbdd9b30b06d5d4734de205` and 65,655 bytes before
  this append. No other file was edited by this round.

### Retained run and ledger integrity

| Check | Result | Direct evidence |
| --- | --- | --- |
| Formal R2.3-005 ledger | PASS | `workspaces/modeling-runs/.r2-3-005-start-ledger.jsonl` has 20 lines, 4,535 bytes, SHA-256 `c44fb191e7298452dc99a6f01cc008a4a8db6eb7f0b9f3066cfd4fdc6b341cb8`. The last three events are start4 `reservation`, `semantic_start`, and one `terminal_failure` at `2026-08-04T04:22:17.830665+00:00`; the terminal event has `classification=collaboration/routing` and `complete_modeling_quality_result=false`. No later budget, repair, reservation, or semantic-start event is present. |
| R2.3-002 legacy ledger isolation | PASS | `.r2-3-002-start-ledger.jsonl` remains 92 lines/21,723 bytes, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`. |
| Retained evidence immutability | PASS | `workspaces/modeling-runs/r23005-real-20260804t040655z-start4/` remains 650 files, `du -sb=38,148,384`, and sorted filename/content digest `3c314f4919e392f1d66b58d6d5fbadd1660456edcbc89982efa5fdb419c51576` before and after the audit append. |
| Runtime code freeze | PASS | `evidence/runtime-core-hashes.jsonl` has matching `before_start` and `after_cleanup` hashes for Runner (`2c64296e...f22382`), capability MCP (`4229850e...48cbe`), Codex adapter (`961bb7...8e12`), and transport MCP (`692ef7...a10a5`). |

### Terminal failure, handoff, and classification

- `state.json` is `CLEANED`. Its acceptance cleanup record is `status=aborted`,
  `aborted_reason=runner-abort-before-settlement`, `settled=false`, `active_handles=0`,
  `zero_child_residue=true`, and `credentials_destroyed=true`; `evidence/aborted.jsonl` contains
  exactly one matching record. This is an authorized fail-fast terminal state, not a semantic PASS.
- `evidence/terminal-result-handoff.jsonl` has exactly three blocked handoffs (Modeling to
  Protocol, Modeling to Coordinator, and Protocol to Coordinator), and
  `evidence/terminal-handoff-ack.jsonl` has exactly three corresponding acknowledgements.
  `team-transport-events.jsonl` contains only the two accepted terminal reports from Modeling and
  Protocol. There is no Acceptance terminal handoff, `acceptance_start`, immutable ticket, CQ
  verdict, or settlement evidence.
- The failure is correctly retained as `collaboration/routing`: the authoritative requirement
  requires a fresh four-role task and fresh Project/Ontology for this slice
  (`requirements-v2.3.md:1480-1484`, `1535-1537`), and the task objective also says not to reuse a
  prior Project/Ontology (`modeling_team/tasks/r2-3-005-formal-acceptance.yaml:9`). However,
  Coordinator delivery-3 instructed Protocol to “Reuse the prior Project/Ontology”, and delivery-13
  repeated that stale direction as the governing instruction. The actual scope was
  `modeling_team/scopes/new-scope-create.yaml` (`mode: create`), while Protocol was given no
  authorized scope-creation operation. Modeling and Protocol therefore stopped before any
  platform call/write. This is a role/task routing contradiction, not `modeling-quality` (no model
  result was applied) and not `platform-contract` (no ontology-platform operation was invoked).
- The Protocol reply (delivery-11) also correctly rejected delivery-10 before execution: the
  candidate had only top-level keys `candidate_kind`, `candidate_revision`, `constraints`, `items`,
  and `scope`, with an integer revision, rather than the complete frozen v2 envelope and canonical
  asserted-data items required by the native receipt/evidence-map contract. No Batch Item was
  authored.

### Source fidelity, owner-answer display, and explicit unknowns

- `evidence/role-visibility-probe.jsonl` reports `passed=true` and the frozen source hashes match
  the current approved inputs: `workflow-landscape.md`
  `9dde79c61d9849776c9140aa5c3be02c17aea7800efa56135fb8dfaa0be7011e`, `release-register.md`
  `f5386a00a2a048831ce524ef605aed14c1124a6ac74fb8dc99c5b0a0f777caae`, `exception-handling.md`
  `cc0c69ef7428bd63ed7432ee0a9cae6d9acbca8cb267528a23fbaf0602638d9f`, and `official/tools.mdx`
  `92a97c639fb8d4782e95207cb84ede79b1739ff3abdb9bc1fe384f0741c2c96b`.
- The first three grounded questions are preserved as `question_delivery_id` values
  `delivery-1`, `delivery-6`, and `delivery-8`; the fourth `delivery-12` is the later scope-conflict
  question and has no owner answer. `outer-user.jsonl` has exactly three unique owner answers
  (`owner-answer-delivery-1`, `owner-answer-delivery-2`, `owner-answer-delivery-3`), each bound to
  its corresponding question delivery and the same run/Project ID. The first two answers preserve
  the grounded unknowns about current release binding and `quality_score`/`quality_rating`
  continuity; the third is the literal `未知` for absent-score behavior.
- The candidate in delivery-10 contains exactly three `explicit_unknown_entity` items
  (`unknown-current-binding`, `unknown-output-continuity`, and `unknown-b-no-score-behavior`) and
  zero `answerValue` properties, including nested objects. Its embedded owner/source artifact
  hashes are retained and match the displayed owner answers and approved sources. This proves
  source/display/unknown preservation only; because Protocol rejected the pre-call envelope, it is
  not a model receipt or semantic acceptance result.

### Cleanup and current runtime checks

- `state.json.cleanup.scope` records `mode=create`, owned Project
  `6c0eb439-192f-4f6f-9bbb-e75a86788c21` and Ontology
  `e5205807-a02a-4e67-9975-b26f380d9d60`, `owned_project_deleted=true`,
  `scope_disposition=deleted-empty`, and post-delete residual counts of zero for project, ontology,
  lease, session, and project-scoped key; `project_absent=true`, `ontology_absent=true`, and
  `fk_cascade=true`. A direct read-only PostgreSQL check independently returned zero for projects,
  ontologies, build sessions, ontology leases, write fences, modeling batches, and modeling
  workflow artifacts for those IDs. The project-scoped key is absent by cascade; the retained
  organization admin key is revoked (`revoked_at=2026-08-04T04:17:39.156832+00:00`). The only two
  project-linked database rows are the expected security audit create/revoke records.
- `systemctl --user --no-pager --full status ontology-platform.service` reports active/running;
  `curl --fail http://127.0.0.1:8001/api/health` returned `{"status":"ok"}` (HTTP 200), and
  `curl --fail http://127.0.0.1:5173/` returned the frontend HTML (HTTP 200). An unauthenticated
  current probe of `/api/semantic/canonical-mode` returned HTTP 401 (`invalid_authentication`),
  so it is not claimed as an authenticated canonical-mode check. The retained prestart evidence
  independently records HTTP 200 with `canonical_store=rdf`, `product_write_mode=rdf_primary`,
  and `read_mode=canonical`.

### Unexecuted scope and disposition

- No real semantic modeling, Protocol dry-run/apply, readback, validation, reasoning, governed
  retrieval, Acceptance Examiner rounds, CQ verdict, or settlement was executed or can be claimed
  from start4. The R2.3-005 live attempt budget is exhausted; do not start another semantic run
  without a new explicit authorization. This audit also did not request or perform a product fix.
- No retained-evidence integrity defect was found. The known task/coordination contradiction is a
  **collaboration/routing blocker** and should be corrected in the task/profile/Coordinator
  contract before any future authorized retry; the narrow fix must preserve fresh-scope creation,
  complete frozen-v2 candidate translation, and the existing display/unknown contracts.

**Overall verdict: BLOCKED for R2.3-005 live semantic acceptance; PASS for this round's retained
evidence integrity, cleanup, source/display binding, and failure-classification audit.**
