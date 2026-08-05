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
| C65 | Authorization ordering | under one lock, exhausted-cap mechanical failure requires failure -> +3 budget -> repair, while a repairable failure with remaining cap requires direct failure -> repair with no budget event; retained `10/8/0`, wrong order, wrong run and mutation-free rejection are covered |
| C66 | Authorization identity/concurrency | duplicate ID/reference and concurrent contenders at each management event yield exactly one valid append and deterministic replay |
| C67 | Retry gate remains mandatory | cap 4 or an interrupted failure/budget prefix cannot reserve; the complete ordered chain and exact tested repair baseline are required |
| C68 | Requirement-scoped incomplete modeling-quality repair | R2.3-005 alone permits `modeling-quality,false` to authorize a fresh-baseline repair and next reservation within existing cap; `complete=true`, budget expansion from modeling-quality, and all R2.3-002 modeling-quality retries remain rejected |
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
| C84 | Second exact +3 tranche | a temporary valid cap/count/active `4/4/0` ledger accepts one distinct exact +3 event, replays `7/4/0`, and can continue through repair, start5 reservation and semantic start |
| C85 | Repeated-tranche safety | early/wrong-order/count-below-cap, malformed/blank/forged events, IDs or references duplicated across either tranche, and concurrent contenders fail without byte drift; interruption after authorization resumes exactly once |
| C86 | Second-tranche CLI and isolation | explicit `--requirement-id R2.3-005` performs the valid temporary transition; omitted/default selection remains R2.3-002 and rejects the R2.3-005 transition; both live ledgers remain byte-identical |
| C87 | Fresh-scope Producer contract | R2.3-005 task requires only the run-created Project/Ontology, forbids prior-scope reuse and a second start, adds `public-protocol.md` only to Protocol, and keeps raw business sources away from Coordinator |
| C88 | Runner proof-gate projection | a run without `expected_matrix_binding` receives neutral candidate/Protocol ownership text and excludes proof matrix, evidence-map and native-verifier prerequisites; a bound R2.3-002 proof task retains them |
| C89 | Runtime proof-gate projection | non-proof R2.3-005 does not stage/mount proof assets, configure proof-only MCP, or require proof-only tools, while retaining generic mechanics and platform tools; bound R2.3-002 behavior is unchanged |
| C90 | Neutral candidate translation | a source-grounded, platform-neutral candidate shaped like retained start4 delivery-10 reaches Protocol deterministic candidate-v2/Batch translation and a mechanical receipt/conflict instead of a missing-envelope rejection |
| C91 | Acceptance readiness invariant | Acceptance cannot start before distinct Modeling and Protocol ready/silent signals and continues to use the existing independent ticket/verdict path; Producer repair creates no semantic verdict shortcut |
| C92 | No-start smoke safety and scope binding | production-shaped Runtime smoke binds its receipt only to a Runtime-generated run-owned synthetic fresh-create Project/Ontology identity, rejects caller/prior identities, and retains prompt/config/tool/delivery/scope evidence while performing no business modeling, platform call, ledger mutation, real Project/Ontology/Session/Lease/key creation, Acceptance start or semantic PASS claim |
| C93 | Producer and full regression | accepted R2.3-002 proof-v2 behavior, settlement/Acceptance, display binding, budget/ledger isolation and complete managed `modeling_team` discovery remain PASS |
| C94 | Complete immutable revision contract | Modeling package and R2.3-005 task require every revision to be a complete self-contained candidate carrying all unchanged items/citations/constraints/queries; Runner projects that task objective without a behavior change, and patch-only fields cannot substitute for the full candidate |
| C95 | Protocol no-merge contract | Protocol never reconstructs candidate history across deliveries and invokes the neutral/proof receipt against the entire current candidate before every receipt or conflict response |
| C96 | Retained partial-revision rejection | a production-shaped start5 revision 6 containing only one replacement item is rejected as incomplete with no prior-delivery merge, platform call or evidence mutation |
| C97 | Complete corrected revision path | the retained revision 5 content plus the explicit Shape correction remains a full 38-item candidate with complete metadata and reaches the ordinary neutral receipt path |
| C98 | Revision repair regression boundary | accepted R2.3-002 proof behavior, non-proof R2.3-005 gate, Producer smoke evidence, Acceptance/lifecycle and complete managed tests remain unchanged; live ledgers/start5 evidence are byte-stable |
| C99 | Ordinary neutral envelope checklist | one scenario-neutral immutable reference is staged to Modeling+Protocol only and freezes exact neutral envelope, string-list constraints, unique `item_id`, non-empty `item_kind`, object `semantic`, optional object-list `evidence_citations`; transport and Batch/platform IDs are outside |
| C100 | Vocabulary closure | every fact, relation and Shape predicate/path used by the current candidate is declared exactly once; retained start6 r2 undeclared predicates are rejected before mechanics/platform work |
| C101 | Object-range closure | every object predicate has one declared target class; heterogeneous targets require a declared common superclass/subclasses or split predicates, and `resource`/external placeholders fail |
| C102 | Executable path closure | negative probes and executable Shapes reference only declared properties/paths and cannot imply an undeclared answer-value field |
| C103 | Protocol exact-current candidate | Protocol passes the exact entire delivered candidate to the receipt before every response and never fabricates a reduced conflict candidate or adds transport fields to neutral semantics |
| C104 | Start6 production-shape and regression | retained r1 wrapper fails; full r2 carry-forward passes revision completeness but exact-current receipt rejects object constraints before semantic closure; corrected full candidate reaches neutral receipt, immutable reference leaks no business answer/Batch contract, and full regressions PASS |

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
| I17 | Second-tranche live append gate | after reviewed deterministic and smoke PASS, exactly one new +3 authorization and one start4 repair are appended under the R2.3-005 lock, yielding cap/count/active `7/4/0` before reservation; no duplicate terminal event and no R2.3-002 ledger drift |
| I18 | Real Runtime Producer handoff smoke | current non-proof R2.3-005 package/profile projects a frozen neutral candidate plus Runtime-generated run-owned synthetic fresh scope to Protocol candidate-v2/Batch mechanics, retains the scope-bound receipt, rejects prior/caller scope identities and leaves zero platform/resource/ledger mutation; independent Tester audits the retained smoke |
| I19 | Start5 Producer-to-Acceptance path | one fresh serialized start5 uses only its run-owned Project/Ontology, reaches Modeling+Protocol ready/silent after required platform stages, then and only then starts independent Acceptance; first full PASS stops further starts |
| I20 | Start5 retained failure audit | independent read-only evidence proves revisions 1-5 narrowed, revision 6 was a one-item cross-delivery patch, Protocol rejected it before platform calls, classification is `collaboration/routing,false`, and cleanup/ledger state is exact `7/5/0` |
| I21 | Start6 complete-revision gate | after reviewed commit and independent C94-C98 PASS, exactly one start5 repair binds a fresh baseline; one serialized start6 must send only complete candidate revisions, reach dry-run before any further candidate-loop expansion, and stop at first full PASS |
| I22 | Start6 retained failure audit | read-only evidence proves full r2 carry-forward, repeated vocabulary/range closure conflict before platform calls, `collaboration/routing,false`, cleanup and exact ledger `7/6/0` |
| I23 | Final start7 authoring-closure gate | after C99-C104 independent PASS and one fresh start6 repair, exactly one final serialized start7 applies the neutral checklist, reaches whole-candidate receipt and dry-run without another shaping loop, and stops at full PASS or cap exhaustion |

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

## 2026-08-04 Producer reuse and second +3 tranche — Independent round 1

### Scope, baseline, and safety boundary

- Tester: fresh independent Requirement Tester, reusing this shared plan and the reviewed
  `docs/delivery/implementation-plans/2026-08-04-r2-3-005-producer-reuse-and-second-tranche.md`.
  Authority was R2.3-005 (including the second exact `+3` section), accepted R2.3-002
  `r2-3-002-t` Task/Profile and Protocol source, and cases C84-C93/I17-I19.
- Code baseline was `HEAD=efc55eafefab13edba3070f95af9d70f1e066cdf`; the implementation was
  intentionally uncommitted. The worktree contained only the expected documentation, package,
  Runner/Runtime/Protocol, task and test changes plus the new producer smoke/plan files. No
  backend/frontend/UI/live-state path was changed. `git diff --check` passed.
- This round was read-only against live state. I did not reserve or start a semantic run, append
  either ledger, call the ontology platform, create Project/Ontology/Session/Lease/key, restart
  services, invoke the opt-in Runtime smoke, or mutate retained evidence. Temporary test fixtures
  were self-cleaned. The single skipped test below is the explicit `R23005_RUN_REAL_SMOKE=1`
  opt-in test; the retained smoke evidence, rather than a skip, is the I18 evidence audited here.
- Before and after all checks, the live snapshots were unchanged: R2.3-002 ledger
  `21723` bytes/mtime epoch `1785665875`, SHA-256
  `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; R2.3-005 ledger
  `4535` bytes/mtime epoch `1785817337`, SHA-256
  `c44fb191e7298452dc99a6f01cc008a4a8db6eb7f0b9f3066cfd4fdc6b341cb8`. The retained
  no-start smoke remained `workspaces/.r2-3-005-producer-smoke/r23005-neutral-runtime-probe/evidence.json`,
  regular mode `0400`, `4453` bytes, SHA-256
  `aa4c44f6af9c66445461e2273548d50b1542b3080c41dcb9d2bda2b2e43c0d06`.

### Executed checks and results

| Check | Result | Direct evidence and notes |
| --- | --- | --- |
| C84-C86 second exact `+3`, malformed/order/duplicate/concurrency/interruption, CLI/default and legacy isolation | PASS | `uv run --project backend python -m unittest modeling_team.tests.test_r23005_budget_extension modeling_team.tests.test_r23005_ledger_isolation modeling_team.tests.test_r23005_a_revision`: **29/29**. Temporary ledgers progressed `4/4/0 -> 7/4/0`, then a synthetic start5 reservation/semantic start; invalid events and concurrent contenders stayed byte-stable. R2.3-002 default/explicit-selector and both live ledgers were isolated. |
| C87-C91 loaded Producer contract and gate projection | PASS | `uv run --project backend python -m unittest modeling_team.tests.test_codex_isolation modeling_team.tests.test_protocol_retrieval_mcp modeling_team.tests.test_r23005_producer_smoke`: **61 tests, 60 PASS, 1 expected opt-in skip**. Loaded R2.3-005 Task/Profile prove fresh run-owned scope, no second start, Protocol-only `public-protocol.md`, and no Coordinator business-source bytes; loaded R2.3-002 `expected_matrix_binding` enables proof gate; unbound R2.3-005 exposes only generic mechanics, while proof-gated raw MCP rejects a neutral candidate; readiness requires distinct Modeling ready and Protocol silent signals. |
| C90 neutral candidate translation and strict Batch contract | PASS | The unbound receipt tests accept the source-grounded neutral candidate and return exactly `status`, `candidate_revision`, `semantic_digest`, `candidate_digest`. The retained smoke Batch is `dry_run`, `lease_token=null`, run-owned client/session/idempotency IDs, current synthetic Ontology, one deterministic `create_class` item, and satisfies every required field in `modeling-batch-item-contract.json`. |
| I18/C92 retained no-start Runtime evidence audit | PASS | Read-only JSON audit independently recomputed the neutral candidate/receipt, candidate and semantic digests, exact protocol-tool and synthetic-scope digests, smoke prompt digest, loaded task projection digest, platform-guard script digest, and verified the exact Batch contract. Evidence records `semantic_start=false`, `platform_calls=0`, `ledger_mutations=0`, `acceptance_started=false`, guard attempted/accepted calls `0/0`, no real key/server, unchanged before/after platform-resource snapshots, no residual process, and caller/prior scope both `rejected`. Evidence is a regular non-symlink `0400` file with forbidden-token scan clear and atomic-retention code path reviewed. Runtime identity, guarded TOML and reply-text preimages are not retained; no undocumented digest algorithm was guessed. |
| Bound-vs-unbound raw MCP tool surface | PASS | Read-only `PROTOCOL_PROOF_GATE=0` lists exactly `build_candidate_receipt` and `verify_scoped_retrieval_fallback`; `PROTOCOL_PROOF_GATE=1` adds only `write_candidate_item_evidence_map`, and a neutral candidate is rejected with `-32602`/`candidate-required-assertions/v2`. |
| Accepted R2.3-002/proof-v2 and P2a frozen surfaces | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23002 modeling_team.tests.test_runner_r63 modeling_team.tests.test_protocol_retrieval_mcp modeling_team.tests.test_proof_v2_runtime_asset`: **54/54**. `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests/test_p2a_codex_runtime.py`: **29 passed**; `test_proof_v2_runtime_asset.py`: **3 passed**. Frozen hash assertions and proof asset staging remained green. |
| C93 focused/all/full regression | PASS | All R2.3-005 discovery: `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: **87 tests, OK, 1 expected skip**. Complete managed unittest discovery: **303/303 OK, 1 expected skip**. Complete pytest discovery: `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests`: **352 passed, 1 skipped, 163 subtests passed**. `uv run --project backend ruff check modeling_team`: all checks passed; compile with a temporary `PYTHONPYCACHEPREFIX` and `git diff --check`: pass. |
| GitNexus change/risk review | PASS with limitation | Read-only `detect_changes(scope=compare, base_ref=main, repo=ontology-platform)` returned changed_files `17`, changed symbols `55`, affected_count `0`, risk `low`, affected_processes `[]`. Untracked smoke/plan files are outside the indexed diff. Upstream impact inspection of changed `TeamRunner.prepare` reports aggregate **HIGH** (151 impacted, 20 direct callers); changed MCP `handle` reports aggregate **HIGH** (122 impacted, one direct caller; depth-1 view LOW). Direct callers include `__main__.py`, `TeamRunner.start`, and covered Runner/protocol tests; full suites above pass. GitNexus index is 20 commits behind `HEAD` (`lastCommit=286da60`), so graph evidence is supplemental, not a clean-commit proof. |
| Excluded-path and side-effect review | PASS | `git diff --name-only`/status scans show no `backend/`, `frontend/`, `workspaces/modeling-runs/`, Project/Ontology/Session/Lease/key, service, Acceptance/PlatformScope/Broker/lifecycle or UI file changes. Final live ledger/evidence mode, size, mtime and hashes equal the before snapshot. |

### Defects and unexecuted scope

- No D1 Critical or D2 Major implementation defect was reproduced in C84-C93/I18. The high
  GitNexus aggregate impact is a review warning, not a failing behavior; direct call coverage and
  all regression suites are green. No Requirement Developer repair is requested for this scope.
- I17 (live second-tranche append) is intentionally **BLOCKED/NOT EXECUTED** for this independent
  Tester: the required `terminal_failure -> exact +3 budget_authorization -> fresh repair` append
  and start5 gate belong to Delivery after commit and authorization. No live event was fabricated
  or appended, so the live R2.3-005 ledger remains at 20 records/cap `4` and I19 remains unclaimed.
- I19 (real start5 Modeling-to-Acceptance, semantic quality, two CQs, settlement and cleanup) is
  likewise **BLOCKED/NOT EXECUTED** by design. The retained no-start Runtime smoke is a mechanical
  handoff gate only and is not a semantic PASS; the explicit opt-in test skip does not weaken I18
  because the retained real Runtime evidence was independently checked above.

### Round conclusion

**Overall verdict: BLOCKED for the full R2.3-005 live gate; PASS for the current deterministic
Producer-reuse/second-tranche implementation and retained I18 smoke evidence.** No developer fix is
requested before commit. Delivery may proceed only with the reviewed post-commit I17 append-only
sequence and then the separately authorized, serial I19 start; stop on the first complete semantic
PASS and preserve all live/retained evidence.

## 2026-08-04 start5 complete candidate revision repair — Independent round 2

### Scope, authority, and safety boundary

- This is the second independent Requirement Tester round for the reviewed complete-candidate
  repair. It reuses this shared plan (C94-C98/I20-I21), the authoritative R2.3-005 start5
  subsection, and `docs/delivery/implementation-plans/2026-08-04-r2-3-005-complete-candidate-revision-repair.md`.
  The test document was the only file edited by this round.
- The worktree baseline was `HEAD=98b50b8a7aa2b0c1936c8312111be0a5e1a6d710` (implementation still
  uncommitted) with
  the expected requirement/delivery/test-plan documentation changes, the Modeling and Protocol
  instruction changes, the R2.3-005 task change, the focused
  `modeling_team/tests/test_r23005_complete_revision.py`, and the repair plan. A status-path
  allowlist check found no other changed path: no Runner, Runtime, mechanics, MCP, Acceptance,
  PlatformScope, Broker, backend, frontend, UI, service, or live-state path changed.
- This round was read-only against the live ledger and retained start5 evidence. It did not start
  Agent Runtime or smoke, call the ontology platform, create or mutate Project/Ontology/
  Session/Lease/key resources, append repair/reservation/semantic-start events, restart services,
  or modify retained evidence. Temporary test fixtures self-cleaned.

### I20 retained start5 audit and immutability snapshots

| Check | Result | Direct evidence |
| --- | --- | --- |
| Retained revision 6 (`delivery-18`) | PASS | `workspaces/modeling-runs/r23005-real-20260804t065900z-start5/evidence/deliveries.jsonl` shows Modeling -> Protocol, sequence 18, revision 6, one `shape:ExplicitUnknown` item, five constraints, three citation records, and `revision_basis`/`revision_operation` patch metadata; revision 5's other items/full metadata are not present in this delivery. |
| Retained Protocol response (`delivery-19`) | PASS | Sequence 19 is Protocol -> Modeling and rejects revision 6 as a one-item patch, explicitly forbidding cross-delivery reconstruction/mutation and requesting all items/citations before deterministic translation. No later delivery, receipt, dry-run, apply, readback, validation, reasoning, Acceptance, or settlement evidence exists. |
| No business platform call | PASS | The retained MCP-elicitations evidence has only `team_transport` (17) and `protocol_mechanics` (1); no ontology-platform MCP server appears. The delivery sequence stops at the pre-write conflict, matching the recorded `BLOCKED/collaboration-routing` terminal. |
| Cleanup and terminal classification | PASS | Retained `state.json` is `CLEANED`; `scope_disposition=deleted-empty`, post-delete Project/Ontology/Session/Lease/project-key residual counts are all zero, child handles/residue are zero, and credentials are destroyed/revoked. The terminal ledger event is `terminal_failure`, `classification=collaboration/routing`, `complete_modeling_quality_result=false`. |
| R2.3-005 ledger | PASS | Read-only `StartLedger(requirement_id='R2.3-005')` replay returned cap/count/active `7/5/0` over 25 records; no new event was appended. Before and after hashes are identical: 5,696 bytes, SHA-256 `9f141d19624bedf76b2fa9628e753895d7cf9602f53883de79b251492c3c7bac`. |
| R2.3-002 ledger isolation | PASS | Before and after the exact same snapshot command returned 21,723 bytes and SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; no legacy ledger drift. |
| Retained start5 tree | PASS | Before and after the exact same read-only command: 648 regular files and `du -sb=40,699,105` bytes. No tree digest algorithm was inferred; equality of the same count/size command is the retained-evidence immutability check. |

### Executed checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| C94-C98 focused repair suite | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_complete_revision`: **5/5**. C94 confirms complete self-contained/no-patch wording is projected to Modeling and the task while Runner behavior is unchanged; C95 confirms Protocol no-merge and receipt-before-every-response wording; C96 rejects the retained partial candidate without mutation/history merge; C97 accepts the corrected complete 38-item candidate with unchanged constraints/citations/dependencies/queries; C98 keeps proof-bound R2.3-002 and neutral R2.3-005 gates distinct. |
| All R2.3-005 tests | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: **92 OK, 1 expected skip**. |
| Complete managed unittest regression | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests`: **308 OK, 1 expected skip**. |
| Complete pytest regression | PASS | `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests`: **357 passed, 1 skipped, 163 subtests passed**. |
| Ruff, compile, whitespace | PASS | `uv run --project backend ruff check modeling_team`, compileall with a temporary `PYTHONPYCACHEPREFIX`, and `git diff --check` all passed. |
| GitNexus compare-main review | PASS with limitation | Read-only `detect_changes(scope=compare, base_ref=main, repo=ontology-platform)` returned `changed_files=6`, `changed_symbols=[]`, `affected_count=0`, `risk_level=low`, and no affected processes. The indexed graph is stale by 21 commits (`indexedAt=2026-08-02`, `lastCommit=286da60...`), so this result is supplemental rather than a fresh graph proof. |
| Frozen-surface/path review | PASS | Current status contains only the expected docs, Modeling/Protocol instructions, R2.3-005 task, repair plan, and focused test; no forbidden Runner/Runtime/mechanics/MCP/Acceptance/PlatformScope/Broker/backend/frontend/live-state diff. |

### Defects, non-claims, and next action

- No D1 Critical, D2 Major, or ordinary product defect was reproduced in C94-C98 or I20. The
  retained failure remains correctly classified as `collaboration/routing`; no Requirement
  Developer follow-up is requested for this repair scope.
- I21 is **NOT EXECUTED/BLOCKED by design** in this round. The implementation is not committed,
  so no start5 repair authorization, fresh baseline binding, reservation, or semantic start6 was
  appended or run. Real start6 dry-run/application/readback/validation/reasoning, Acceptance,
  semantic quality, settlement, and final cleanup remain unclaimed. Delivery may perform that
  sequence only after commit and this independent deterministic PASS; it must stop at the first
  complete PASS and must not fabricate I21 evidence.
- Backend pytest, service restart, and endpoint checks were not required because no backend or
  frontend surface changed. No new runtime residue was created by this round.

### Round conclusion

**Overall verdict: BLOCKED for the full R2.3-005 live gate because I21 remains NOT EXECUTED;
PASS for the complete-candidate deterministic repair (C94-C98) and retained start5 I20 audit.**
No developer fix is requested. After commit, Delivery may proceed with exactly one reviewed
start5 repair authorization and one serialized start6, preserving the live-ledger and retained-
evidence boundaries above.

## 2026-08-04 neutral candidate authoring closure — Independent round 3

### Scope, authority, and safety boundary

- This is the third independent Requirement Tester round. It reuses this shared plan's C99-C104
  and I22-I23 cases, the R2.3-005 `start6 neutral candidate authoring closure` subsection in
  `docs/requirements/requirements-v2.3.md`, and the reviewed
  `docs/delivery/implementation-plans/2026-08-04-r2-3-005-neutral-candidate-authoring-closure.md`.
  The allowed implementation surface was limited to the scenario-neutral reference,
  Modeling/Protocol instructions, the R2.3-005 task, and the focused test. No mechanics, MCP,
  Runner, Runtime, platform, Acceptance/lifecycle, backend, frontend, or live-state path was
  edited by this Tester.
- The execution baseline was `HEAD=5c3be74584deb7487db268c0c0c0c7c518fa72ba`. Before checks,
  `git status --porcelain` contained the parent requirement/delivery edits plus the expected
  neutral plan/reference/instructions/task/focused-test paths; no retained run path was tracked.
  The Tester did not request a repair, start7 reservation, semantic start, Runtime/smoke run,
  platform call, service restart, resource mutation, or commit. Temporary clean-checkout and
  compile caches were outside the repository and did not touch retained evidence.
- The required C99-C104 clean-checkout portability gate was run explicitly. A temporary checkout
  was produced with `git archive HEAD` and only the current neutral reference, instructions,
  task, and focused test copied in; it contained no
  `workspaces/modeling-runs/r23005-real-20260804t075359z-start6/evidence/deliveries.jsonl`.
  This is the acceptance condition for a clean checkout and is distinct from the retained-evidence
  audit in I22.

### I22 retained start6 audit and immutability snapshots

| Check | Result | Direct evidence |
| --- | --- | --- |
| Start6 terminal and classification | PASS | Retained `state.json` is `CLEANED`; Acceptance is `aborted`, `settled=false`, `active_handles=0`, `zero_child_residue=true`, and `credentials_destroyed=true`. The final retained Protocol response is a pre-write conflict, and no Acceptance verdict or settlement is present. |
| Start6 candidate failure path | PASS | `deliveries.jsonl` has 12 records. Retained r1 `cba-slice-r1` has 16 public `id/type/facts` items; full r2 `cba-slice-r2` has 16 `item_id/item_kind/semantic` items and object constraints with no patch fields. After the mechanical envelope correction, Protocol reports undeclared `upstreamOf`/`invokesAsPublishedTool` and `affectedSubject` range `resource`; it stops before platform work. |
| No platform work | PASS | Retained MCP elicitations contain only `team_transport` and `protocol_mechanics`; no ontology-platform MCP server appears. No Build Session, dry-run/apply, readback, validation, reasoning, receipt success, Acceptance, or settlement evidence exists after the conflict. |
| Cleanup | PASS | Retained cleanup is owned create-scope deletion with `scope_disposition=deleted-empty`, `owned_project_deleted=true`, `project_absent=true`, `ontology_absent=true`, `fk_cascade=true`, and residual counts zero for project, ontology, lease, session, and project-scoped key; the project key is revoked and child residue is zero. |
| Formal ledger state | PASS | Read-only replay of `.r2-3-005-start-ledger.jsonl` returned 29 records, cap/count/active `7/6/0`, and valid strict replay. No event was appended. The legacy R2.3-002 ledger replay remained 92 records and was not opened for write. |
| Before/after live-state equality | PASS | R2.3-005 ledger before/after: mode `664`, 6,622 bytes, SHA-256 `956a20aa027487af7e54c02edbd04bad2022d550f660eef75c5381706058ecdf`; R2.3-002 before/after: 21,723 bytes, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`. Start6 evidence before/after: 14 files, 151,772 bytes, and all 14 per-file SHA-256 values equal (including `deliveries.jsonl`, 56,705 bytes, `a5654d6652e5c2371f823ddf13a68472ef0f0a5a4375ca3326dae16f90fbb2ac`). |

### Executed checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| C99-C104 focused suite in the current checkout | PASS (non-portable) | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring`: **6/6 OK**. The assertions pass only because this checkout has the ignored retained start6 deliveries. |
| C99-C104 in a clean checkout without retained evidence | **FAIL — D2 Major** | The exact command `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring` ran all six tests in `/tmp/r23005-clean-checkout.8ymSJu` and every test errored with `FileNotFoundError` at `modeling_team/tests/test_r23005_candidate_authoring.py:39` (`_retained_candidate`) for the absent ignored `workspaces/.../start6/evidence/deliveries.jsonl`. No C99-C104 case was skipped, but none was executable. |
| All R2.3-005 discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: **98 OK, 1 expected opt-in skip**. |
| Complete managed `modeling_team` unittest discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests`: **314 OK, 1 expected opt-in skip**. Existing ResourceWarning/runtime diagnostic output did not fail the suite. |
| Ruff, compile, whitespace | PASS | `uv run --project backend ruff check modeling_team`, compileall with a temporary `PYTHONPYCACHEPREFIX`, and `git diff --check` all passed. |
| GitNexus compare-main review | PASS with scope limitation | `detect_changes(scope=compare, base_ref=main, repo=ontology-platform)` returned `changed_files=6`, `changed_symbols=[]`, `affected_count=0`, `risk_level=low`, and no affected processes. Untracked reference/focused-test/plan files are not represented in this indexed result. |

### Defect, disposition, and unexecuted scope

- **D2 Major — C99-C104 are not clean-checkout portable.** Reproduction: construct a clean
  checkout without ignored `workspaces/`, copy the tracked/current neutral test inputs, and run
  the focused unittest command above. Expected: all six C99-C104 tests execute against a tracked
  structural fixture and pass. Actual: all six terminate in `FileNotFoundError` before their
  assertions because `_retained_candidate()` hard-requires the ignored retained start6 delivery
  file. The normal-checkout 6/6 result therefore cannot serve as independent acceptance evidence.
  A Requirement Developer must add a tracked scenario-neutral structural fixture or an equivalent
  fallback that preserves I22 as the only retained-evidence audit. Do not start7 until an
  independent follow-up round reruns C99-C104 in a clean checkout and passes.
- I23 is **NOT EXECUTED/BLOCKED by design**. No start6 repair authorization, start7 reservation or
  semantic start, dry-run/application/readback/validation/reasoning, Acceptance, semantic quality,
  settlement, or final cleanup was attempted by this Tester. The retained start6 audit is not a
  live completion result.
- No product code, test fixture, ledger, retained evidence, service, or platform resource was
  modified by this round. The only Tester edit is this appended round record.

### Round conclusion

**Overall verdict: FAIL — STOP.** C99-C104's deterministic assertions are green only with the
ignored retained artifact; the mandatory clean-checkout gate is a D2 Major failure. Requirement
Developer follow-up is required to add the tracked structural fixture/fallback, followed by a new
independent Tester round. Do not authorize or run start7, and do not claim I23, until that round
returns PASS.

## 2026-08-04 neutral candidate authoring closure remediation — Independent round 3.1

### Scope, authority, and safety boundary

- This is a separate remediation round for the D2 Major recorded in round 3. It reuses C99-C104
  and I22-I23 in this shared plan, the authoritative R2.3-005 start6 closure subsection, and the
  reviewed neutral-candidate authoring plan. The developer remediation adds only the tracked
  structural fixture `modeling_team/tests/fixtures/r23005-neutral-candidate-authoring-fixtures.json`
  and updates the focused test helper/assertions; no mechanics, MCP, Runner, Runtime, platform,
  Acceptance/lifecycle, backend, frontend, or live-state path changed.
- The final verification baseline remained `HEAD=5c3be74584deb7487db268c0c0c0c7c518fa72ba`.
  The final current-workspace focused/full/static checks below were rerun after the latest helper
  rename and fact-key closure assertion. The Tester edited only this appended test-plan round;
  no code, fixture, ledger, retained evidence, service, platform resource, reservation, semantic
  start, or commit was performed.

### C99-C104 remediation and fixture integrity

| Check | Result | Direct evidence |
| --- | --- | --- |
| Independent clean-checkout C99-C104 | PASS | Fresh `git archive HEAD` checkout `/tmp/r23005-clean-remediation-final.HQMKv4` received only the current focused test, tracked fixture, neutral reference, instructions, and task; no `workspaces/` files were copied. `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring` ran **6/6 OK**. |
| Fixture/reference leak scan | PASS | Independent read-only scan found no `dify`, `workflow`, business answer/expected-answer, `quality_score`, `quality_rating`, `project_id`, `ontology_id`, `batch_id`, `platform_id`, `object_id`, UUID, or C/B/A edge in either neutral reference or structural fixture. Generic “object”/“Batch” checklist wording is not an identifier leak. |
| Structural fidelity | PASS | Neutral reference has the exact five-field example envelope, non-empty string constraints, unique non-empty item IDs/kinds, object `semantic`, and object-list citation shape. Fixture r1 retains the public `id/type/facts` wrapper; r2 retains complete item IDs/semantics, object constraints, and only intentional transport `delivery_id`/`reply_chain`; corrected has exactly the five neutral fields, string constraints, unique item IDs, declared fact/relation/Shape path keys, and no transport/platform IDs. Corrected fixture receipt is `accepted`; r1 and r2 reject at the constraints stage. |

### I22 retained start6 audit and live immutability

| Check | Result | Direct evidence |
| --- | --- | --- |
| Retained start6 terminal/failure | PASS | `state.json` is `CLEANED`; Acceptance is aborted/unsettled with zero active handles/child residue and destroyed credentials. Twelve deliveries stop at Protocol's pre-write conflict: r1 wrapper failure, full r2 object constraints, then undeclared `relatesTo`/`dependsOn` vocabulary and `resource` object range after mechanical correction. |
| No platform work and cleanup | PASS | Retained MCP servers are only `team_transport` and `protocol_mechanics`; no ontology-platform server, Build Session, receipt success, dry-run/apply, readback, validation, reasoning, Acceptance, or settlement result exists. Owned create scope is deleted-empty with project/ontology/lease/session/project-key residuals all zero and keys revoked. |
| Formal ledger replay | PASS | Read-only strict replay of `.r2-3-005-start-ledger.jsonl` remains 29 records, cap/count/active `7/6/0`; the legacy R2.3-002 ledger remains 92 records. No event was appended. |
| Before/after snapshots | PASS | Both snapshots match exactly: R2.3-005 ledger mode `664`, 6,622 bytes, SHA-256 `956a20aa027487af7e54c02edbd04bad2022d550f660eef75c5381706058ecdf`; R2.3-002 ledger 21,723 bytes, SHA-256 `4750fa251d3d2beb84b52d486864019c493f3db5c2bdd0e5e06f58ae6b171a2b`; retained start6 evidence 14 files/151,772 bytes with all per-file SHA-256 values unchanged (including `deliveries.jsonl` 56,705 bytes, `a5654d6652e5c2371f823ddf13a68472ef0f0a5a4375ca3326dae16f90fbb2ac`). |

### Final remediation checks

| Check | Result | Direct evidence |
| --- | --- | --- |
| Focused C99-C104 in current workspace | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring`: **6/6 OK** after the final helper/fact-key edits. |
| All R2.3-005 discovery | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_r23005*.py'`: **98 OK, 1 expected opt-in skip**. |
| Complete managed modeling-team unittest | PASS | `uv run --project backend python -m unittest discover -s modeling_team/tests`: **314 OK, 1 expected opt-in skip**. |
| Complete managed modeling-team pytest | PASS | `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests`: **363 passed, 1 skipped, 163 subtests passed**. |
| Ruff, compile, whitespace | PASS | `uv run --project backend ruff check modeling_team`, compileall with temporary `PYTHONPYCACHEPREFIX`, and `git diff --check` all passed. |
| GitNexus compare-main | PASS with scope limitation | `detect_changes(scope=compare, base_ref=main, repo=ontology-platform)` returned `changed_files=6`, `changed_symbols=[]`, `affected_count=0`, `risk_level=low`, and no affected processes. Untracked fixture/test/reference/plan files are outside this indexed comparison. |

### Disposition and unexecuted scope

- The round-3 D2 Major is **FIXED**: C99-C104 now execute and pass in a clean checkout without
  ignored retained evidence, and the tracked fixture remains scenario-neutral and structurally
  faithful. No remaining defect was reproduced in the remediation scope; no further Requirement
  Developer fix is requested before the next gate.
- I23 remains **NOT EXECUTED/BLOCKED by design**. This round did not perform start6 repair
  authorization, start7 reservation/semantic start, Runtime or platform calls, dry-run/application,
  readback/validation/reasoning, Acceptance, semantic quality, settlement, or final cleanup. The
  retained start6 evidence is an I22 audit only and cannot claim the final start7 gate.

### Round conclusion

**Overall verdict: PASS for the C99-C104 remediation and I22 retained-evidence audit; BLOCKED for
the complete R2.3-005 live requirement because I23 remains NOT EXECUTED.** The D2 Major from round
3 is fixed. Delivery may separately follow the reviewed, authorized final-slot sequence only after
the required clean commit/baseline gates; do not claim I23 from this round.

## 2026-08-04 start7 atomicity boundary — Independent focused round 4

### Scope, authority, and safety boundary

- This round validates only the start7 atomicity-boundary repair against the existing focused
  candidate-authoring, complete-revision, producer-smoke, task/profile, and retained-start7 checks.
  It reuses this test plan and the applicable R2.3-005 requirement/design; no new test plan or
  acceptance scheme was created.
- The final developer handoff was checked before testing. The final worktree has seven modified
  paths: the two pre-existing GitNexus instruction files plus the five R2.3-005 modeling/protocol,
  neutral-reference, task, and focused-test paths. The Tester edited only this appended round;
  no product implementation, prompt/reference/task rollback, ledger, retained evidence, service,
  platform resource, reservation, semantic start, or commit was performed.
- The intended boundary is explicit: Modeling owns whole-candidate semantic integrity; Protocol
  translates the complete candidate through dependency-ordered class/property/entity/receipt-bound
  IRI/relation/Shape stages, with each stage independently `dry_run`/`apply_atomic` and bound to
  preceding receipts. Modeling-facing neutral candidates must not encode fresh scope/session/batch
  mechanics, receipt IDs/IRIs, stage strategy, or whole-candidate atomic application.

### Focused checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Existing focused suites | PASS (one expected opt-in skip) | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring modeling_team.tests.test_r23005_complete_revision modeling_team.tests.test_r23005_producer_smoke`: **13 tests OK**, with only `test_neutral_handoff_projects_generic_runtime_without_semantic_start` skipped because real Codex Runtime smoke is explicit opt-in. |
| Task/profile validation | PASS | Direct validation from the absolute checkout root found the formal roles exactly (`coordinator`, `modeling`, `protocol`, `acceptance`), neutral-reference role source exactly Modeling+Protocol, no expected-matrix binding, and the task objective's semantic-integrity/per-stage-atomicity/receipt-binding language. |
| Protocol contract and closure | PASS | Current focused C99-C104 and complete-revision assertions pass, retaining the exact-current candidate envelope plus vocabulary, range, dependency/path closure, and complete revision requirements while checking the new semantic-vs-Protocol atomicity handoff. |
| Neutral reference/fixture boundary scan | PASS | Independent scan of the neutral reference and tracked structural fixtures found no fresh Project/Ontology, Session/Lease, Batch/Item, `dry_run`/`apply_atomic`, receipt ID/IRI, stage-order, whole-candidate-atomic, platform-execution, or platform identifier terms in candidate constraints/examples. |
| Modeling producer smoke neutral candidate | **FAIL — D2 Major** | Independent scan of `modeling_team/r23005_producer_smoke.py:280-289` found prohibited mechanics in `neutral_candidate()` constraints: `fresh Project/Ontology only; no prior scope reuse` and `Protocol owns candidate-v2/Batch translation`; hits were `['fresh project', 'batch']`. |

### Retained start7 audit and immutability

| Check | Result | Direct evidence |
| --- | --- | --- |
| Retained start7 terminal/cleanup | PASS | Read-only state audit remains `CLEANED`; Acceptance is aborted/unsettled with zero active handles and child residue, credentials destroyed, owned project/ontology absent, FK cascade complete, and all residual counts zero. Retained MCP evidence has no ontology-platform server or platform work. |
| Formal live ledger replay | PASS | Read-only replay remains strict-valid with **cap/count/active = 10/7/0**; live ledger SHA-256 is `ce51034d2eab182495c722dcc08a92c3dbf2009e51ac9eb1e4e681239408ea43`. No event was appended. |
| Start7 evidence before/after | PASS | The before and final read-only snapshots are identical: **14 files, 116,431 bytes**, and all 14 per-file SHA-256 values match (including `deliveries.jsonl` `38c41c488f2721a57ba31e4ba16db8ca7ff9ff92098ce9f6d0c9e7468f5d0649`). |

### Defect and disposition

- **D2 Major — the producer-smoke candidate is not neutral under the repaired boundary.** Reproduce
  with `from modeling_team.r23005_producer_smoke import neutral_candidate; print(neutral_candidate()["constraints"])`
  or scan its lower-cased constraints for the prohibited terms. Expected: no fresh
  Project/Ontology, Session/Lease, Batch/Item, `dry_run`/`apply_atomic`, receipt IDs/IRIs, stage
  strategy, or whole-candidate atomic-apply language. Actual: the exact fresh-scope and Batch
  translation strings above remain in the reusable Modeling-facing smoke candidate. The focused
  smoke test passed/skipped because the final scope-tightening reverted the helper/import
  assertion; it does not establish the required neutrality gate.
- This is a requirement-relevant failure, not an excluded fixture or a live-runtime artifact. A
  Requirement Developer should remove the mechanics from the smoke candidate (and/or add the
  requirement-scoped assertion to the existing focused test), then the Tester should rerun this
  same focused round. Do not claim a clean repair commit or authorize/start8 on this evidence.
- I23/start8 is **NOT EXECUTED/BLOCKED by design**: no reservation, live semantic start, Runtime or
  platform call, dry-run/application/readback/validation/reasoning, Acceptance, settlement, or
  cleanup was attempted. No full repository suite or broad audit was run.

### Round conclusion

**Overall verdict: FAIL — STOP for the focused start7 atomicity-boundary acceptance; BLOCKED for the
complete R2.3-005 live requirement.** The semantic-vs-Protocol contract, current envelope/closure,
neutral reference/fixtures, task/profile, focused suites, and retained start7 immutability checks
pass, but D2 Major remains in the Modeling producer-smoke candidate. Requirement Developer repair
and a new independent focused round are required before a clean commit or start8.

## 2026-08-04 start7 atomicity boundary remediation retest — Independent round 5

### Scope and safety boundary

- This remediation retest reuses the same C99-C104/complete-revision/producer-smoke plan and
  round-4 failure evidence. The developer's stopped change removes the producer-smoke mechanics
  and restores C104 coverage for that neutral candidate. Round 4 is preserved unchanged.
- The Tester edited only this appended round. No product fix, new checker, full suite, live start,
  platform mutation, ledger append, retained-evidence mutation, service action, or commit was done.

### D2 retest and focused checks

| Check | Result | Direct evidence |
| --- | --- | --- |
| D2 `neutral_candidate()` constraints | **PASS — D2 FIXED** | Inline assertion over `neutral_candidate()["constraints"]` found no prohibited fresh Project/Ontology, Session/Lease, Batch/Item, `dry_run`/`apply_atomic`, receipt ID/IRI, platform-execution, atomic-apply, or stage-order terms. The constraints are exactly `the semantic candidate is complete, self-contained, and immutable` and `all semantic references close over this candidate`. |
| C104 smoke coverage | PASS | Existing `R23005CandidateAuthoringTests.test_c104_corrected_candidate_receipt_projection_and_scope_boundaries` ran **1/1 OK** and now asserts the same prohibited-term set against the imported `neutral_candidate()` constraints. |
| Existing focused suites | PASS (one expected opt-in skip) | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring modeling_team.tests.test_r23005_complete_revision modeling_team.tests.test_r23005_producer_smoke`: **13 tests OK**, `test_neutral_handoff_projects_generic_runtime_without_semantic_start` skipped because real Codex Runtime smoke requires explicit opt-in. C99-C104 and C94-C98 all pass. |
| Task/profile validation | PASS | Absolute-root validation found roles exactly `coordinator`, `modeling`, `protocol`, `acceptance`; neutral reference source roles exactly Modeling+Protocol; both expected-matrix bindings are `None`; all semantic-integrity/per-stage-atomicity/receipt-binding objective phrases remain present. |

### Retained start7 audit and immutability

| Check | Result | Direct evidence |
| --- | --- | --- |
| Formal ledger strict replay | PASS | Read-only `StartLedger(requirement_id='R2.3-005')` replay validated **34 records**, cap/count/active **10/7/0**. Live ledger SHA-256 remains `ce51034d2eab182495c722dcc08a92c3dbf2009e51ac9eb1e4e681239408ea43`; no event was appended. |
| Start7 terminal/cleanup | PASS | Retained `state.json` remains `CLEANED`; Acceptance is aborted/unsettled with `active_handles=0`, `zero_child_residue=true`, credentials destroyed; owned scope is `deleted-empty`, project/ontology absent, FK cascade true, and all residual counts zero. Ten deliveries remain and MCP servers are only `team_transport`. |
| Before/after evidence equality | PASS | Before and after retest snapshots are identical: ledger mode `664`, size `7,802`, same SHA and mtime; start7 evidence has **14 files / 116,431 bytes**, with all 14 per-file SHA-256 values unchanged, including `deliveries.jsonl` `38c41c488f2721a57ba31e4ba16db8ca7ff9ff92098ce9f6d0c9e7468f5d0649`. |

### Disposition and readiness

- The round-4 **D2 Major is FIXED**. The reusable Modeling-facing smoke candidate is now
  semantic-only, and C104 directly protects this boundary. No focused defect remains.
- I23/start8 remains **NOT EXECUTED/BLOCKED by design**. No live semantic start, Runtime or
  platform call, dry-run/application/readback/validation/reasoning, Acceptance, settlement, or
  cleanup was attempted in this retest. No full repository suite or broad audit was run.
- The repaired state is ready for the developer's clean repair commit and the required clean
  baseline/authorization gates for start8. This Tester does not authorize or launch start8.

### Round conclusion

**Overall verdict: PASS for the focused start7 atomicity-boundary remediation; BLOCKED for the
complete R2.3-005 live requirement because I23/start8 remains unexecuted.** D2 is fixed, retained
evidence is immutable, and the next safe action is a clean repair commit followed by the separately
authorized start8 sequence.

## 2026-08-04 start8 entity-label closure remediation — Independent round 6

### Scope and safety boundary

- This round reuses the shared candidate-authoring, complete-revision, producer-smoke, task/profile,
  lint/diff, and retained-evidence scope. It validates the final entity-label closure repair without
  changing any prior round. The Tester edited only this appended round; no code fix, new checker,
  live start, platform/ledger mutation, service action, or commit was performed.
- The target contract is narrow: every `create_entity` materialization has a non-empty
  source-grounded label (`semantic.values.label` for `entity`/`explicit_unknown`, or
  `semantic.invalid_instance.label` for a materialized `negative_probe`); Protocol rejects blank
  labels and never derives them from IDs or question text. Existing exact-current envelope,
  vocabulary/range/path closure, staged atomicity, and neutral-constraint exclusions remain in
  scope.

### Focused checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Existing focused offline suites | PASS (one expected opt-in skip) | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_candidate_authoring modeling_team.tests.test_r23005_complete_revision modeling_team.tests.test_r23005_producer_smoke`: **14 tests OK**, with only `test_neutral_handoff_projects_generic_runtime_without_semantic_start` skipped because real Codex Runtime smoke is explicit opt-in. C99-C105 and C94-C98 pass. |
| Label closure and non-derivation | PASS | Existing `test_c105_materialized_entity_labels_are_required_and_not_derived` rejects missing `semantic.values.label` for `entity` and `explicit_unknown`, and missing `semantic.invalid_instance.label` for `negative_probe`; C104 validates labels on the neutral example/corrected fixture and the required no-derivation phrases. |
| Modeling/Protocol/reference/task contract | PASS | Existing C104 assertions find the label paths and “derive or invent” prohibitions in Modeling instructions, Protocol instructions, neutral-reference closure checklist, and task objective; neutral candidate constraints remain free of platform mechanics. |
| Task/profile validation | PASS | Absolute-root validation found roles exactly `coordinator`, `modeling`, `protocol`, `acceptance`; neutral source roles exactly Modeling+Protocol; both expected-matrix bindings `None`; semantic-integrity, staged-atomicity, receipt-binding, label-path, and no-derivation objective phrases present. |
| Lint and whitespace | PASS | `uv run --project backend ruff check modeling_team/tests/test_r23005_candidate_authoring.py` and `git diff --check` both passed. |

### Retained start8 defect evidence and immutability

| Check | Result | Direct evidence |
| --- | --- | --- |
| Retained delivery-7/9 defect matches | PASS (historical evidence) | `deliveries.jsonl` sequence 7 reports `probe-published-release-missing-output` with `invalid_instance` missing a non-empty label; sequence 9 reports both `unknown-output-continuity` and `unknown-b-no-score-behavior` missing entity labels and states Protocol cannot synthesize from IDs/questions. Delivery 6 has the missing probe label; delivery 8 adds that probe label but still leaves both explicit-unknown labels absent. |
| Formal ledger strict replay | PASS | Read-only `StartLedger(requirement_id='R2.3-005')` validated **38 records**, cap/count/active **10/8/0**. Live ledger SHA-256 is `9573a90741e36517f908ece47545c29d17cfa386ecd5e3b2c71300ad1b4ffde4`; no event was appended. |
| Start8 cleanup | PASS | Retained `state.json` remains `CLEANED`; Acceptance is aborted/unsettled with `active_handles=0`, `zero_child_residue=true`, credentials destroyed; owned scope is `deleted-empty`, project/ontology absent, FK cascade true, all residual counts zero. Nine deliveries remain and retained MCP servers are only `team_transport`. |
| Before/after retained evidence equality | PASS | Before and after snapshots match exactly: ledger mode `664`, size `8,726`, same mtime/SHA; start8 evidence has **17 files / 163,599 bytes**, and all 17 per-file SHA-256 values are unchanged, including `deliveries.jsonl` `0ff1d6cbca1695ff8d4f75bdd18ed15bdc25b16edbfcdcd031d22c1a9fa3fa99`. |

### Disposition, residual risk, and readiness

- The entity-label closure repair is **PASS** for the focused offline acceptance. No current-code
  defect was reproduced. The retained start8 conflict is historical evidence of the defect that
  the current neutral reference/fixtures/instructions/task and C105 guard now cover.
- Residual risk is intentionally bounded: no live Protocol/platform translation was rerun, so the
  repaired label contract still needs confirmation in a fresh authorized start. I23/start9 is
  **NOT EXECUTED/BLOCKED by design**; this Tester did not reserve or launch it, and no full suite or
  broad audit was run.
- The repaired state is ready for a clean repair commit and the required clean-baseline and
  authorization gates before start9. Do not treat retained start8's aborted run as a live PASS.

### Round conclusion

**Overall verdict: PASS for the focused start8 entity-label closure remediation; BLOCKED for the
complete R2.3-005 live requirement because start9 remains unexecuted.** The label paths,
non-derivation/rejection behavior, exact-current neutral closure, ledger, cleanup, and retained
evidence immutability all pass; next safe action is clean commit followed by separately authorized
start9.

## 2026-08-04 incomplete-modeling repair policy — Independent round 7

### Scope and safety boundary

- This round reuses the existing R2.3-005 budget-extension/ledger-isolation, R2.3-002 ledger
  compatibility, and r63 tests. It validates only the policy-scoped `start_ledger.py` change and
  its existing tests; all main-agent requirement/design/delivery-record edits and prior rounds are
  preserved.
- The Tester edited only this appended round. No code fix, commit, live start9, direct repair,
  ledger/evidence/platform mutation, full suite, or new checker/harness was performed.

### Focused policy checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Requirement-scoped policy | PASS | Existing C61/C68 checks show `R2.3-005` alone has `allow_incomplete_modeling_quality_repair=True`, while the default/`R2.3-002` policy remains `False`, with legacy filenames/caps/increments unchanged. |
| One central eligibility predicate | PASS | `_repair_failure_eligible` is used by `authorize_repair`, strict replay repair/reservation validation, strict next-start validation, and nonstrict reserve; C68 plus existing sequence/rebind tests pass. `complete_modeling_quality_result=True` remains rejected. |
| Mechanical budget boundary and retained-like direct repair | PASS | C68 builds a temporary retained-like cap/count/active `10/8/0` prefix, rejects a direct budget authorization, accepts `modeling-quality,false` repair with a fresh baseline, rejects stale/equal baseline and wrong gate binding byte-stably, then accepts the matching reservation without a budget event. Cap remains 10 and semantic count 8. |
| Invalid order/run/gate/active/concurrency paths | PASS | C65/C67/C69/C73 and C68 cover wrong order/run, stale/equal baselines, released/active reservations, gate mismatch, rebind generations, and concurrent repair serialization; all pass with failed operations leaving temporary ledger bytes unchanged. |
| CLI and legacy rejection | PASS | C61 formal selector authorizes the incomplete repair; unknown/legacy selectors and `R2.3-002` `modeling-quality,false` repair are rejected without append. Complete failures and budget-predecessor violations remain rejected. |
| Focused existing test set | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_r23005_budget_extension modeling_team.tests.test_r23005_ledger_isolation modeling_team.tests.test_start_ledger_r63 modeling_team.tests.test_runner_r63` plus the 13 relevant R2.3-002 ledger compatibility methods: **43/43 passed**. |
| Targeted static checks | PASS | Ruff on `modeling_team/start_ledger.py` and `modeling_team/tests/test_r23005_budget_extension.py`, targeted `py_compile` (temporary external cache), and `git diff --check` all passed. |

### Retained formal ledger and start8 evidence

| Check | Result | Direct evidence |
| --- | --- | --- |
| Formal ledger strict replay | PASS | Read-only replay remains **38 lines**, cap/count/active **10/8/0**; mode `664`, size `8,726` bytes, SHA-256 `9573a90741e36517f908ece47545c29d17cfa386ecd5e3b2c71300ad1b4ffde4`. No event was appended. |
| Start8 retained cleanup | PASS | `state.json` remains `CLEANED`; Acceptance is aborted/unsettled with zero active handles/child residue and destroyed credentials; scope is `deleted-empty`, project/ontology absent, FK cascade true, residual counts zero. |
| Start8 evidence immutability | PASS | Before/after snapshots match exactly: **17 files / 163,599 bytes**, all per-file SHA-256 values unchanged (including `deliveries.jsonl` `0ff1d6cbca1695ff8d4f75bdd18ed15bdc25b16edbfcdcd031d22c1a9fa3fa99`). |

### Known tooling limitation and disposition

- Developer-provided GitNexus review raised a **CRITICAL impact warning** for the shared ledger
  path. The stale index refresh also failed on invalid UTF-8; no graph result was treated as a
  clean-commit gate, and this round did not expand into a refresh or broad audit. Direct source
  inspection and the focused tests above are the authoritative evidence for this policy.
- No functional defect was reproduced. The policy is ready for a clean repair commit and, after
  the required clean-baseline and explicit authorization gates, direct repair authorization of the
  retained incomplete start8 followed by start9. Neither direct repair nor start9 was performed.

### Round conclusion

**Overall verdict: PASS for the focused incomplete-modeling ledger policy; BLOCKED for the complete
R2.3-005 live requirement because direct start8 repair/start9 remains unexecuted.** Formal/legacy
eligibility separation, central predicate coverage, mechanical budget behavior, invalid-path
closure, 43 focused tests, static checks, and retained ledger/evidence immutability all pass.

## 2026-08-05 formal Acceptance provider-auth staging — Independent round 8

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. This round validates only the formal R2.3-005
  persistent Acceptance provider-auth staging repair in `acceptance_runtime.py`,
  `runtimes/codex.py`, and the focused contract tests. No real Producer, semantic start,
  Project/Ontology, MCP producer call, ledger/evidence mutation, service restart, key operation,
  or retained-run mutation was performed; start11 remains explicitly fresh and unexecuted.
- Authority: R2.3-005 in `docs/requirements/requirements-v2.3.md`, the approved design, and this
  shared plan. Stable code baseline is HEAD `965a196edbb110b84029c27a27226650a9cf209c`; the
  supplied code/test diff hash is
  `fac008cd67b396e800f7cfd274844d8723aa82bb4bc91c865f0ea066c2a2e87f`.
- Worktree check: only the pre-existing main-agent changes in `AGENTS.md`, `CLAUDE.md`,
  `docs/requirements/requirements-v2.3.md`, and the three supplied modeling-team files were
  present before this tester appended this round. No product code was modified by the Tester.

### Executed checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Formal positive provider auth and real config content | PASS | `uv run --project backend python` temporary formal carrier probe staged exact synthetic auth bytes into Acceptance `home/auth.json`, observed mode `0600` under owner/mode-checked `0700` home, and inspected `config.toml`; only `team_transport` and the expected Runner `runner_capability` MCP sections were present. No Protocol MCP, platform key/config, or source bytes were present. |
| Formal provider auth cleanup | PASS | The same probe set `_coordination_enabled=True`, registered the Agent, called `CodexRuntimeAdapter.stop()`, and observed `auth.json` and `runner-capability.token` removed. Existing `test_formal_stop_destroys_capability_material_and_is_idempotent` also passed. |
| Non-formal and R2.3-002 compatibility | PASS | `test_codex_acceptance_config_has_no_auth_or_sources_and_separate_capabilities`, `test_nonformal_stop_preserves_formal_capability_material`, and existing host-auth preflight tests passed; the non-formal Acceptance path still stages no auth/sources and does not remove formal-only artifacts. |
| No platform key/source/extra MCP | PASS | Focused contract tests `test_read_only_key_lifecycle_revokes_plaintext_and_allowlist_excludes_writes` and `test_capability_separation_and_opaque_idempotent_child_start` passed; the real formal config probe found no `protocol`/`platform` MCP section and an empty `home/sources`. |
| Symlink/invalid/parent fail-closed staging | PASS | Formal symlink test plus an independent temporary probe rejected source directory, source symlink, destination symlink, pre-existing destination, and destination parent mode `0755`; no destination auth was created for source/parent failures. `_copy_private` source `lstat`/`O_NOFOLLOW` and target `_write_private` `O_EXCL|O_NOFOLLOW`, mode `0600`, fsync path were directly inspected. |
| Child existing-path regression and cleanup | PASS | `test_codex_child_resource_seam_stops_and_destroys_private_tree_without_launching` and `test_child_report_sink_and_terminal_recycle_are_immutable` passed; child resource stop/destroy leaves no private tree or active child residue. |
| Focused contract/runtime tests | PASS | `uv run --project backend python -m unittest -v` over 7 R2.3-005 contract/isolation methods (formal positive/negative, non-formal, allowlist, capability separation, child recycle, child cleanup): **7/7 passed**; adjacent Codex isolation cleanup/preflight set: **5/5 passed**. |
| Ruff, compile, whitespace | PASS | `uv run --project backend ruff check modeling_team/acceptance_runtime.py modeling_team/runtimes/codex.py modeling_team/tests/test_r23005_contracts.py`; `uv run --project backend python -m py_compile` on the same three files; and `git diff --check` all passed. |

### Unexecuted or not claimable

- No real app-server Acceptance launch was performed, so a live provider response/401 recovery,
  real four-role Acceptance lifecycle, semantic model quality, Protocol/platform behavior, or
  final settlement remains unclaimed.
- No backend/frontend full suite, service restart, or platform health check was necessary for
  this modeling-team-only offline repair and none was run.

### Defects and conclusion

- No defect was reproduced in the scoped provider-auth change. Formal positive content, private
  modes/ownership boundary, no-source/no-platform/no-extra-MCP contract, invalid-path fail-closed
  behavior, child existing-path regression, cleanup, and focused static checks all pass.
- Residual risk is limited to live Acceptance provider authentication and the already retained
  R2.3-005 runtime/semantic evidence; those require a separately authorized fresh run and are
  not replaced by this deterministic round.

### Round conclusion

**Overall verdict: PASS for the formal Acceptance provider-auth repair and its focused regression
scope; the complete R2.3-005 live requirement remains BLOCKED/unproven.** This round is complete;
stop writing the shared test plan after this entry.

## 2026-08-05 narrow governed retrieval contract — Independent round 9

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. This round validates only the six-file narrow retrieval
  contract delta and its model-visible projection. No product implementation, prompt/requirement
  source outside the supplied delta, ledger, stash, platform resource, service, or real semantic
  start was touched. No fresh start13 was attempted.
- Authority: R2.3-005 start12 retrieval-focused repair contract in
  `docs/requirements/requirements-v2.3.md`, the approved design/implementation plan, and this
  shared test plan. Stable baseline is HEAD `27e8e48484114f5bebe83823b6441bf4145f58b8`; the exact
  supplied six-file diff SHA-256 is
  `44f52425e55db92f64be17fdc7acfced99289d0faad22f06fe09bad7cf4f70b4`.
- Worktree check: the six supplied files are the only task delta (`docs/delivery/implementation-plans/2026-08-04-r2-3-005-producer-reuse-and-second-tranche.md`,
  `docs/requirements/requirements-v2.3.md`, Protocol instructions, the modeling-batch contract,
  formal task YAML, and the focused Codex isolation test). No product runtime code was modified.

### Executed checks and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| C88 model-visible prompt projection | PASS | `uv run --project backend python -m unittest -v modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_c88_runner_prompt_projects_loaded_002_proof_and_loaded_005_neutral_contract` passed. The ordinary v2 Protocol prompt contains the newly required inline Evidence/reference, entity/explicit-unknown non-empty evidence, and EvidenceReference/Association/origin-lineage clauses while proof-only material remains absent. |
| Protocol retrieval gate regressions | PASS | `uv run --project backend python -m unittest -v` over `test_protocol_retrieval_gate_requires_completed_eligible_query_and_current_verifier` and `test_protocol_retrieval_gate_fails_closed_for_result_quality_and_semantic_state_changes`: **2/2 passed**. Existing incomplete/degraded/truncated/fallback state transitions and unexpected-response terminal behavior remain fail-closed and unchanged. |
| C95/C98 candidate/proof boundary | PASS | `test_c95_protocol_never_merges_history_and_builds_each_current_receipt` and `test_c98_proof_bound_002_and_neutral_005_boundaries_remain_distinct`: **2/2 passed**. Ordinary R2.3-005 remains unbound to proof-v2 matrix/native-verifier requirements; current-candidate receipt ownership is preserved. |
| Adjacent C94/C97 revision projection | PASS | `test_c94_complete_revision_contract_is_projected_to_modeling_and_task` and `test_c97_retained_complete_correction_reaches_ordinary_neutral_receipt`: **2/2 passed**. Complete candidate carry-forward and ordinary neutral receipt behavior remain intact. |
| JSON/YAML parse and task/profile validation | PASS | `uv run --project backend python` read/parsed `modeling-batch-item-contract.json`, formal task/profile YAML, loaded the strict configuration, and verified the exact four-role roster and ordinary retrieval contract section. |
| Model-visible High-D closure review | PASS | Direct source inspection across Protocol instructions, `ordinary_v2_execution` contract JSON, formal task objective, and Runner-generated Protocol prompt confirms: run-owned ontology scope; per-CQ narrow queries/resource types; vector-missing lexical fallback; context-before-match pagination with new context chain and no cursor mixing; fallback readback not substituting complete generic retrieval; one-to-one inline/reference citation mapping; entity/explicit-unknown evidence non-emptiness; receipt-only extended metadata; and EvidenceReference/Association plus origin lineage after apply/readback. Protocol's role-specific final coordination signal remains `silent_for_acceptance`; the task-level successful-retrieval gate remains before acceptance readiness. |
| Ruff and diff check | PASS | `uv run --project backend ruff check modeling_team/tests/test_codex_isolation.py` and `git diff --check` both passed. |

### Unexecuted or not claimable

- No live `query_semantic_context`, vector/lexical fallback, cursor chain, EvidenceReference,
  Association, or origin-lineage calls were executed. No real Protocol/Acceptance run, platform
  write/readback, or semantic PASS is claimed.
- No full repository discovery, backend/frontend suite, service restart, ledger replay, or retained
  evidence audit was run; these are outside this focused retrieval-contract round.

### Defects and residual risk

- No defect was reproduced in the scoped six-file delta. C88/C95/C98 and retrieval-gate regressions
  pass, and the newly added High-D candidate-evidence clauses are present in every relevant
  model-visible layer.
- Residual risk is live-only: actual runtime behavior must still prove exact ontology scoping,
  lexical fallback, two-cursor pagination ordering, non-truncated generic completion, and post-apply
  Evidence/Association/origin-lineage readback in a separately authorized fresh start. The existing
  terminal Unexpected-response behavior was not changed by this delta.

### Round conclusion

**Overall verdict: PASS for the focused governed-retrieval contract and High-D model-visible closure;
the complete R2.3-005 live requirement remains BLOCKED/unproven.** Round 9 is complete; stop writing
the shared test plan after this entry.

## 2026-08-05 formal candidate progress and explicit +1 authorization — Independent round 10

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. This round validates the supplied R2.3-005 A+B delta:
  explicit positive authorization amounts with retained `+3`/R2.3-002 compatibility; the formal-only
  candidate/revision/receipt/conflict progress gate; Codex dispatch turn binding and started/completed
  barrier; one bounded redrive; timeout and terminal cleanup exception paths; and formal-only
  Protocol conflict-tool exposure. No implementation or test code was changed by the Tester.
- Baseline/worktree: HEAD `cb9d758403488dd190d5cbd96e45575eda76ac63`; the supplied implementation is
  uncommitted in the shared worktree. Pre-existing user edits in `AGENTS.md` and `CLAUDE.md` were
  preserved. No real start14/Acceptance run, canonical ledger append, platform resource, service,
  credential, retained evidence, or commit was performed.
- The prior Round 9 “stop writing” sentence is historical; this is the next independent append-only
  round in the same shared test plan.

### Focused execution and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Formal candidate progress unit/runner tests | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_r23005_candidate_progress.py -q`: **8 passed**. Exact candidate envelope, string-list constraints, dual digests, strict receipt/conflict binding, revision path, missing turn-id fail-closed, and one-redrive dispatch were exercised. |
| Explicit authorization and historical ledger policy | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_r23005_budget_extension.py -q`: **20 passed, 18 subtests passed**. Formal `+1` isolated extension, replay/order/concurrency/invalid values, ordinary formal `+3`, and R2.3-002 exact `+2` compatibility passed. |
| Runtime/dispatch and Protocol exposure regressions | PASS | `test_p2a_codex_runtime.py`: **29 passed**; `test_codex_isolation.py`: **49 passed, 33 subtests passed**; `test_p2a_protocol_driver.py`: **15 passed, 21 subtests passed**. Runtime dispatch receipts, turn events, formal-only MCP exposure, old provider/runtime boundaries, and Protocol prompts remain green. |
| Candidate/receipt/Protocol legacy boundaries | PASS | Combined `test_r23005_complete_revision.py test_r23005_producer_smoke.py test_protocol_retrieval_mcp.py`: **16 passed, 1 skipped, 13 subtests passed**; `test_r23005_candidate_authoring.py`: **7 passed, 3 subtests passed**; `test_proof_v2_runtime_asset.py test_d65_protocol_observation.py`: **6 passed**. The single skip is the expected explicit real-Codex smoke opt-in. |
| Adjacent R2.3-005/Runner regression | PASS | Combined R2.3-005 A/B/C/contracts/ledger-isolation/T6 suites: **72 passed, 7 subtests passed**; Runner/owner-answer/P2 protocol suites: **48 passed, 23 subtests passed**. |
| Static checks | PASS | Ruff on every supplied Python implementation/test file, `PYTHONPYCACHEPREFIX=/tmp/r23005_pycache uv run --project backend python -m py_compile ...`, and `git diff --check` all passed. |

### Defect reproduced: terminal progress can be revived by a late receipt

| ID / severity | Reproduction steps | Expected | Actual / evidence |
| --- | --- | --- | --- |
| R23005-B-01 — **P1, acceptance-blocking** | In a temporary in-memory probe, create `FormalCandidateProgress(clock=lambda: 0.0)`, observe a valid `platform-neutral-candidate-v2` delivery `d1`, bind `RuntimeDispatchReceipt("start", "turn-1")`, mark the exact started/completed barrier, call `redrive_ready()`, mark one redrive with `RuntimeDispatchReceipt("start", "turn-2")`, mark its barrier, then call `redrive_ready()` again to latch `FormalCandidateRoutingError`/`state="exhausted"`. Submit a valid four-field receipt (the exact pending revision and both computed digests) with `reply_to_delivery_id="d1"`. Repeat with a fresh progress object, bind `turn-1`, advance the injected clock to `120.0`, call `check_deadline()` to raise `FormalCandidateProgressTimeout`, then submit the same exact receipt. Command: `PYTHONPATH=. uv run --project backend python - <<'PY' ...` (the probe only imports `candidate_progress`/runtime dataclasses; it writes no file or ledger). | Once the bounded redrive is exhausted or the 120-second receipt/revision timeout is latched, any late response must be ignored/rejected and must not revive terminal progress. The state must remain `exhausted` (routing terminal) or timeout-failed; no later `complete` transition is permitted. | The direct probe printed: `exhausted_raise= FormalCandidateRoutingError state= exhausted`; `late_after_exhausted_before= exhausted`; `late_after_exhausted_result= accepted after= complete`; `timeout_raise= FormalCandidateProgressTimeout state= awaiting_receipt`; `late_after_timeout_before= awaiting_receipt`; `late_after_timeout_result= accepted after= complete`. Thus a correctly bound late receipt changes `exhausted -> complete`, and also changes the timed-out pending state to `complete`; the `_timeout_latched` flag is not consulted by `observe_delivery`. |

The ordinary focused tests pass because they stop at the routing exception/timeout and do not submit a
late valid response afterward. This is a real contract defect, not a test-environment failure. The
Tester did not modify the implementation or add a permanent checker; the minimum safe repair is to
make terminal/exhausted/timeout-latched progress immutable against all late receipts/conflicts and
then rerun this same Round 10 document.

### Unexecuted or not claimable

- No real start14, independent Acceptance agent, platform materialization/readback, semantic model
  quality, canonical `+1` authorization append, or live ledger/evidence mutation was attempted.
- No backend/frontend full suite, service restart, or endpoint health check was needed for this
  modeling-team-only offline test and none was run. The live R2.3-005 requirement therefore remains
  unproven independently of the offline defect.

### Round conclusion

**Overall verdict: FAIL for the supplied formal candidate-progress A+B delta.** All ordinary focused
tests and static checks pass, but R23005-B-01 is a reproducible P1 acceptance blocker: a late valid
receipt revives both exhausted and timed-out progress. Ask the requirement Developer to repair this
narrow state-immutability defect, then rerun Round 10 in this same test plan before any real start14.

## 2026-08-05 formal candidate terminal-latch repair — Independent round 11

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. This round reuses the same Round 10 scope and validates
  only the claimed R23005-B-01 repair: terminal/timeout/failure latches, pre-parse late-delivery
  rejection, normal receipt and conflict-to-revision continuity, and the adjacent frozen runtime
  regression. No implementation or test code was changed by the Tester.
- Baseline/worktree: HEAD remains `cb9d758403488dd190d5cbd96e45575eda76ac63`; the Developer's
  uncommitted changes are shared in place. `AGENTS.md`/`CLAUDE.md` and all other user changes were
  preserved. No real start14/Acceptance run, canonical ledger append, platform resource, retained
  evidence, service action, or commit was performed.

### Focused execution and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Original exhausted late-receipt/conflict reproduction | PASS | The temporary in-memory probe repeated candidate `d1` -> `turn-1` started/completed barrier -> one redrive `turn-2` barrier -> second `redrive_ready()` routing failure. It then submitted exact four-field receipt and six-field conflict. Output: `exhausted_raise= FormalCandidateRoutingError state= exhausted`; `exhausted_late_receipt= None state= exhausted identity_same= True`; `exhausted_late_conflict= None state= exhausted identity_same= True`. |
| Original receipt-timeout reproduction and repeated deadline | PASS | After `turn-1` dispatch, injected clock `120.0`; both first and second `check_deadline()` calls raised `FormalCandidateProgressTimeout` while retaining `state=awaiting_receipt` and `latched=True`. Exact late receipt/conflict both returned `None`, state and identity unchanged. Output: `receipt_timeout_1= ...`, `receipt_timeout_2= ...`, `receipt_timeout_late_receipt= None ... identity_same= True`, `receipt_timeout_late_conflict= None ... identity_same= True`. |
| Revision-timeout and terminal-failure latch reproduction | PASS | A valid conflict moved to `awaiting_revision`; after the same 120-second deadline, a complete revision and late conflict both returned `None`, with `state=awaiting_revision`, identity unchanged, and timeout latched. Calling `mark_terminal_failure()` twice left one idempotent latch; all late receipt/conflict returned `None`. |
| New candidate-progress regression tests | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_r23005_candidate_progress.py -q`: **12 passed**. This includes four new late-response/latch groups plus normal receipt, normal conflict→revision, one-redrive, turn-id, and envelope checks. |
| Adjacent Runner/ledger/legacy smoke | **FAIL — one stale frozen-hash contract** | Combined command over `test_p2a_codex_runtime.py`, `test_runner.py`, `test_p2_protocol_driver.py`, `test_r23005_budget_extension.py`, `test_r23005_complete_revision.py`, `test_r23005_producer_smoke.py`, `test_r23005_candidate_authoring.py`, and `test_protocol_retrieval_mcp.py`: **96 passed, 1 skipped, 36 subtests passed, 1 failed**. Re-running `test_p2a_codex_runtime.py -k 'not byte_frozen'` gives **28 passed, 1 deselected**, confirming the functional related tests pass. |
| Static checks | PASS | Ruff on the supplied implementation/test files, targeted `PYTHONPYCACHEPREFIX=/tmp/r23005_round11_pycache uv run --project backend python -m py_compile ...`, and `git diff --check` all passed. |

### Defect R23005-R11-01: frozen Runner hash was not synchronized

| Severity | Reproduction | Expected | Actual / evidence |
| --- | --- | --- | --- |
| **P1 process/acceptance gate blocker** | Run `uv run --project backend python -m pytest modeling_team/tests/test_p2a_codex_runtime.py modeling_team/tests/test_runner.py modeling_team/tests/test_p2_protocol_driver.py modeling_team/tests/test_r23005_budget_extension.py modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_r23005_producer_smoke.py modeling_team/tests/test_r23005_candidate_authoring.py modeling_team/tests/test_protocol_retrieval_mcp.py -q`. | The frozen-surface test must match the actual Runner bytes after the approved terminal-latch repair, or the test contract must be updated by the Developer in the same change. | `test_normal_runtime_and_platform_surfaces_remain_byte_frozen` fails: expected `modeling_team/runner.py` SHA `c07ae488eddecf19b2b2f22173cbf9c8586a8f00f322c80323ca6a0853705fe6`, actual `a4bf6d92287565c79c2ebb57dd96a12da0f146f7833e0061a085214e7a690be2`. The actual hash is a real changed Runner file (the new `mark_terminal_failure` synchronization and candidate-progress integration), not an accidental Tester edit. The failure is therefore stale frozen metadata that must be synchronized before acceptance; Tester did not alter the test. |

The claimed B-01 repair itself is **PASS**: exhausted, receipt-timeout, revision-timeout, and explicit
terminal-failure states now reject late receipt/conflict/revision and retain identity; repeated
deadlines remain latched and repeat the same timeout without changing state. Normal pending receipt
and normal conflict -> revision -> receipt paths remain green. Round 11 is nevertheless not a clean
PASS because the required adjacent frozen-surface regression fails until the Runner hash contract is
updated and independently rerun.

### Unexecuted or not claimable

- No real start14, Acceptance Agent, platform materialization/readback, semantic model quality,
  canonical `+1` authorization append, or live ledger/evidence mutation was attempted.
- No backend/frontend full suite, service restart, or endpoint health check was run; the live
  R2.3-005 requirement remains unproven.

### Round conclusion

**Overall verdict: FAIL for Round 11 due solely to R23005-R11-01 (stale frozen Runner hash).** The
P1 late-response state-immutability repair is independently PASS, and all other focused/legacy/static
checks pass. Ask the Developer to synchronize the frozen hash as part of the approved Runner change,
then rerun this same Round 11 document before any real start14.

## 2026-08-05 frozen Runner hash synchronization — Independent round 12

### Scope, baseline, and safety boundary

- Tester: independent requirement Tester. This final offline round reuses Round 11 and checks only
  the reported frozen-hash synchronization plus the necessary candidate-progress, Runner, ledger,
  legacy, and static regressions. No implementation or test behavior was changed by the Tester.
- HEAD remains `cb9d758403488dd190d5cbd96e45575eda76ac63`. Read-only worktree inspection shows the
  same production implementation files as Round 11; the only reported new change is the frozen
  `modeling_team/runner.py` expected hash/comment in `test_p2a_codex_runtime.py`. Actual
  `sha256sum modeling_team/runner.py` is
  `a4bf6d92287565c79c2ebb57dd96a12da0f146f7833e0061a085214e7a690be2`, matching the updated test
  constant exactly. No real start14/Acceptance run, canonical ledger append, resource/evidence
  mutation, service action, or commit was performed.

### Focused execution and results

| Check | Result | Direct evidence |
| --- | --- | --- |
| Frozen Runner/platform surfaces | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_p2a_codex_runtime.py::test_normal_runtime_and_platform_surfaces_remain_byte_frozen -q`: **1 passed**. The Round 11 stale expected `c07ae488...` is gone; the expected `a4bf6d92...` equals the actual Runner digest. |
| Candidate-progress and normal path | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_r23005_candidate_progress.py -q`: **12 passed**. Normal pending receipt and normal conflict -> revision -> receipt remain green alongside the new latches. |
| Round 11 related Runner/ledger/legacy regression | PASS | The same combined focused command over Codex runtime, Runner, P2 protocol, budget extension, complete revision, Producer smoke, candidate authoring, and Protocol retrieval MCP suites: **97 passed, 1 skipped, 36 subtests passed**. |
| Explicit authorization ledger | PASS | `uv run --project backend python -m pytest modeling_team/tests/test_r23005_budget_extension.py -q`: **20 passed, 18 subtests passed**. Formal `+1`, historical formal `+3`, R2.3-002 exact `+2`, replay/order/concurrency and invalid paths remain intact. |
| B-01 original minimal repros | PASS | The direct in-memory probe repeated exhausted late exact receipt/conflict, receipt-timeout late receipt/conflict with repeated deadline, revision-timeout late complete revision/conflict, and idempotent terminal-failure latch. Output: `exhausted= exhausted late_receipt= None late_conflict= None identity_same= True`; `receipt_timeout_errors= ['FormalCandidateProgressTimeout', 'FormalCandidateProgressTimeout'] state= awaiting_receipt latched= True late_receipt= None late_conflict= None identity_same= True`; `revision_timeout= awaiting_revision late_revision= None late_conflict= None identity_same= True`; `terminal_failure= True late_receipt= None late_conflict= None state= awaiting_receipt identity_same= True`. |
| Static checks | PASS | Ruff on all supplied implementation/test files, targeted `PYTHONPYCACHEPREFIX=/tmp/r23005_round12_pycache uv run --project backend python -m py_compile ...`, and `git diff --check` all passed. |

### Defects and disposition

- No defect reproduced. The Round 11 P1 late-response state-immutability repair remains PASS, and
  the stale frozen-hash gate is fixed by the exact actual Runner digest. No test implementation was
  edited by the Tester; the expected constant now matches the approved changed Runner surface.
- The one expected real-Codex smoke skip remains explicit opt-in and is not treated as a failure.

### Unexecuted or not claimable

- No real start14, independent Acceptance Agent, platform materialization/readback, semantic model
  quality, canonical `+1` authorization append, or live ledger/evidence mutation was attempted.
- No backend/frontend full suite, service restart, or endpoint health check was run; this is an
  offline modeling-team contract PASS and does not claim live R2.3-005 semantic acceptance.

### Round conclusion

**Overall verdict: PASS for the final offline Round 12 scope.** Frozen Runner hash, candidate
progress/latch behavior, normal receipt/revision flow, authorization ledger compatibility, related
Runner/legacy suites, and static checks all pass. The live requirement remains unclaimed until a
separately authorized real start14/Acceptance run.

## Waived offline Round 13 — start15 is the test

The user explicitly waived independent offline testing for this exceptional retry. The luna-max Developer performs
only focused smoke checks for the following implementation invariants before commit:

- the retained redrive `text` is byte-identical to the original candidate, including Unicode, whitespace, and key
  order; all original Runtime attribution and reply-binding fields are identical;
- redrive is a direct same-thread Runtime delivery with `kind=candidate-redrive`, not a second Team Transport event,
  new candidate identity, revision, or semantic start;
- Protocol instructions require immediate `build_candidate_receipt` use on the redelivered `text` and an exact
  response bound to the original delivery; free text and malformed receipt/conflict remain invalid;
- after an invalid formal response has occupied or been acknowledged against the original request, the Broker permits
  exactly one formal-only CAS replacement reply without deleting immutable delivery history; wrong request/reply,
  participant drift, repeated reopen, or non-formal use is rejected;
- exactly one redrive is possible, with the existing matching-turn barrier, timeout, exhausted state, late-response
  latch, controlled cleanup, and terminal ledger behavior unchanged;
- formal gate off, R2.3-002, schema-v1, ordinary schema-v2, receipt/conflict/revision, budget replay, and frozen
  runtime surfaces regressions remain green.

There is no Requirement Tester Round 13 and no offline PASS claim. After the focused developer checks and commit, the
single real start15 is the test; its live evidence and cleanup determine the result.
