# R2.3-002 New-Scope Business Slice Shared Test Plan

## Status

- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-002
- Design:
  `docs/delivery/designs/2026-07-31-r2-3-002-new-scope-business-slice-design.md`
- Status: R2.3-002 delivered; Round78 independent Acceptance PASS and Round79 docs-only audit PASS
- Producer: Round78 retained Producer model (completed)
- Independent test owner: fresh Round78 Acceptance Agent; Round79 documentation audit by Requirement Tester

## Completion rule

PASS requires Task v1 regression, Task v2 configuration/isolation tests, exact Protocol tool
authorization, one real bounded semantic run on the final runtime-affecting baseline, independent
Agent acceptance of the frozen L3 gates, successful retained-scope handoff, exact credential and
Runtime cleanup, resident service health, and a recorded independent PASS round. For the current
closure, PASS additionally requires the ordered `r` terminal classification and mandatory closeout,
both independent no-semantic-start P2 repair tests, the unique continuing-authorization tranche,
two matching fresh baselines, and the same independent tester's Phase A then Phase B evidence.

## Automated cases

| ID | Case | Required result |
| --- | --- | --- |
| C01 | Existing schema-v1 Tasks | R2.3-001 smoke validation and tests remain unchanged |
| C02 | Valid schema-v2 Task | role source sets, Protocol allowlist, retention policy, and evidence fields load |
| C03 | unknown role/tool, duplicate/path escape/symlink/missing source | fail before scope or Agent startup |
| C04 | tester-only, runtime, delivery, historical run, or secret source | fail closed |
| C05 | source staging | only assigned role receives file at stable relative path and manifest hash matches |
| C06 | source basename collision | preserved relative paths prevent overwrite |
| C07 | non-Protocol config | no ontology platform MCP or key |
| C08 | Protocol config/preflight | exact Task-declared tools and no extras |
| C09 | Task attempts key/project/migration/repair/governance write | rejected |
| C10 | first-turn task text | no R2.3-001 health-only or no-modeling hard-code for v2 |
| C11 | baseline manifest | Runner, Adapter, Profile, Packages, Skills, Task, sources, MCP code hashed |
| C12 | semantic-start marker | written once only after visibility probes and before business delivery |
| C12a | outer user control envelope and release gate | canonical `action=user` JSON passes stdin decode to exactly one Coordinator outer-user delivery with verbatim text; `type=user_message` reproduces fail-fast; actual send requires current grounded question delivery ID/text -> unique answer ID, zero prior release, exactly one send, and correlated Coordinator forward; duplicate prompts release nothing |
| C13 | empty create cleanup | exact owned Project deleted and keys revoked |
| C14 | successful non-empty retention | no delete; disposition retained; workspace version captured |
| C15 | non-empty without retention | no delete and explicit blocker |
| C16 | written failed scope | Runner does not delete |
| C17 | handoff | exactly five allowed fields, atomic immutable write, values match scope |
| C18 | Runtime cleanup | Agents stopped, secrets destroyed, no plaintext key in retained evidence |
| C19 | terminal category | first failure category preserved; cleanup issue appended |
| C20 | start ledger authorization/exhaustion | historical four distinct +2 approvals still permit cap ten; duplicate, malformed, or concurrent authorization/reservation fails before scope/Runtime; current continuing-authorization tranche ordering is covered by C41 |
| C21 | every later-start authorization | only the immediately prior frozen narrow non-modeling failure plus tested repair, exact new baseline, and valid 20-minute freeze accepted; attempt nine rejects missing fourth approval, missing attempt-eight repair, and wrong baseline before accepting only the Round-21-bound exact baseline |
| C22 | modeling-quality first result | second reservation rejected |
| C23 | pre-semantic release/rebind | release is append-only idempotent and terminal; release-vs-start concurrency has one winner, late start after release/rebind/new reserve fails with unchanged count; a fresh-run baseline may rebind only after the prior repair was consumed by exactly one released never-started reservation, while unused/active/started/same-baseline/concurrent cases fail closed |
| C23a | Codex authentication preflight | missing/non-file host auth fails before ledger, run directory, Project/key, or Runtime state; valid auth continues and private staging retains its defensive check |
| C24 | failed Session with no write | no in-flight Attempt, Session cancelled, Lease released, empty scope deleted |
| C25 | applying/recovering Attempt | cleanup stops; Session/scope not deleted |
| C26 | Session/Lease/workspace drift | cleanup blocks without guessing or destructive call |
| C27 | cleanup retry | terminal cancellation/revocation/disposition is idempotent |
| C28 | failed non-empty producer | retained as failed evidence; no handoff candidate or publication |
| C29 | handoff publication gate | requires all Agent completed, platform terminal proof, and independent Phase A PASS |
| C30 | handoff credential | fresh publisher credential is not exposed and is revoked |
| C31 | handoff recheck | version/ownership/session drift or deleted scope rejects publication |
| C32 | handoff immutability | one atomic publication only; later deletion cannot create another valid handoff |
| C33 | P0 provenance gate | recover the original zero initial formal envelope with canonical SHA-256 `4e66b6d21d4b8e9cff9c279d965b638d8dd849a25a692b964a04d1e80ad3a50f`; record the unique `candidate_required_assertions` artifact as missing; block old-run PASS and new producer authorization/start, but do not block mandatory terminal classification/closeout |
| C34 | `r` terminal classification | append exactly one immutable `terminal_failure` with `failure_category=runtime/infrastructure` and `complete_modeling_quality_result=false`; validate lineage max-depth errors, 00:14:48 turn interruptions, zero `report_task_result`, `PAUSED`, and later process loss as causal evidence; retain max-depth/candidate/verifier gaps as secondary unresolved facts |
| C35 | failed-run closeout order | freeze non-secret evidence -> terminal failure -> admin reread and no applying/recovering proof -> required current-revision failure checkpoint with reason/unresolved items -> cancel using returned revision -> reread cancelled/released -> revoke old Project key by ID and every temporary/bootstrap admin/read key with direct proof -> retain non-secret failed-written scope/evidence -> destroy and prove absence of all three auth/config/temp credential sets; no reacquire/complete/separate release |
| C36 | candidate-required-assertions/v1 | Modeling supplies a nonempty platform-neutral statement set; revision binds delivery/reply chain and canonical digest; Protocol preserves it as a nonempty duplicate-free asserted-data quad set with one-to-one computed fact IDs and one lineage response each; `max_depth` is `0..5`; empty/duplicate/extra/unbound/drifted inputs fail closed and Delivery does no semantic selection |
| C37 | native verifier and fallback gate | native verifier accepts only `mode=create` and rejects vacuous proof; `complete=true` is accepted only after an observed eligible `fallback_required` episode and completed verifier item, while direct generic `complete=true` remains an alternative success path |
| C38 | P2-monitor operating unit | schema-v1 base profile/task run through the real foreground CLI/TeamRunner/Codex Adapter/app-server/Team Transport/`TeamRunner.drain()`/terminal-result-handoff/ack/settlement/cleanup under `foreground_monitor.py`; proves parent-PM boundary/process persistence, all-agent settlement and secret cleanup only, with no fallback test, business source, or StartLedger event; any required mechanical scope is owned and cleaned |
| C39 | P2-Protocol repair preflight | no TeamRunner or `modeling_team run`; schema-v2 production `CodexRuntimeAdapter.start_roster` plus real Broker/stdio/private-bwrap/app-server/native-MCP path proves correlated candidate/fallback -> Broker terminal guard/report acceptance -> Protocol cleanup, never reserves StartLedger or marks semantic start, and never claims/fabricates Runner handoff, Modeling terminal, ack, or all-three settlement; fully cleans one owned ephemeral platform scope |
| C40 | repair baseline delta | baseline manifest adds only monitor command/argv/descriptor, `modeling_team/foreground_monitor.py` and `modeling_team/references/p2-monitor-contract.json` SHA-256/lifecycle/evidence path, and Protocol candidate/verifier launch/tool-schema hashes; two fresh manifests from the clean tree are canonical-content/hash identical |
| C41 | closure/start ordering | enforce `r` classification -> mandatory closeout -> P2 monitor+Protocol PASS -> unique tranche 8 `+2` -> two fresh baselines -> repair authorization -> reservation/start -> three Agents completed+settled -> success cleanup/evidence freeze -> same tester Phase A -> handoff -> Phase B -> final gates |
| C42 | F1 model/reasoning audit | parser/Profile/Adapter/config surfaces still expose no supported Team model or reasoning-effort setting; no switch to Terra/xhigh is made |
| C43 | canonical candidate/materialized digests | fixed platform-neutral fields, canonical UTF-8 JSON/SHA-256 ordering, candidate binding, Protocol graph-role resolution, materialized digest, and zero semantic drift |
| C44 | exact native proof schema | exactly ten top-level fields; strict nonempty nested candidate/lineage objects; max_depth `0..5`; reject missing/extra/duplicate/unbound/mismatched members |
| C45 | same-run double baseline | same prospective run ID and stable file set are hashed twice before reservation/start with no ledger/scope/fixture/evidence/PID access; full manifests and hashes match |
| C46 | real foreground P2 monitor | persistent monitor covers TeamRunner, Codex Adapter/app-server, Team Transport/Broker, actual `TeamRunner.drain()` terminal-result-handoff/ack/all-agent settlement, secret cleanup, and at least one parent-PM turn boundary using nonbusiness smoke without semantic start |
| C47 | real Protocol correlation and cleanup | synthetic candidate traverses production delivery/reply path before native verifier; sequence ends at Broker terminal guard/report acceptance and Protocol cleanup; it does not claim Runner handoff/Modeling terminal/all-three settlement; staged key/delete evidence proves API/DB zero residuals |
| C48 | stable baseline inputs | `_baseline_manifest` hashes the exact listed stable code/descriptor/schema files; omission/addition/byte drift fails closed and ephemeral fixture/evidence/PID values are excluded |
| C49 | P2 resource boundary and deletion evidence | first-stage artifact covers every project-scoped read/model/Protocol key exact ID/`revoked_at`/non-active, cancelled Session, Lease auto-release, ownership/cleanup receipts/no in-flight Attempts, and org-admin key exact ID=`ACTIVE` solely for authenticated DELETE; after DELETE prove Project/Ontology absent/project-scoped active residuals zero/FK cascade, immediately revoke org-admin, freeze second-stage ID/`revoked_at`/non-active plus retained audit row, and aggregate all created keys non-active |
| C50 | exact plural proof schema | ten top-level fields use `entities_read`/`statements_read`; nested field sets, canonical algorithms, full lineage response boundary, nonempty/one-to-one rules, and max_depth `0..5` are strict |
| C51 | actual fresh-Producer fallback ordering | final fresh Producer proves app-server query item -> sanitized `fallback_required` -> native `mode=create` verifier -> Modeling terminal -> real Runner terminal-result-handoff/ack -> Protocol terminal -> 3/3 settlement; invalid order fails; this is not a P2-Protocol claim |
| C52 | external candidate binding | observer matches nested delivery_id/reply chain/revision/semantic_digest/candidate_digest against raw Modeling Broker envelope and Protocol receipt; fabricated self-consistent IDs fail |
| C53 | foreground monitor implementation | `modeling_team/foreground_monitor.py` plus stable descriptor drives the real persistent monitor across a parent-PM boundary and secret cleanup; exact call-site lifecycle is observed |
| C54 | monitor/baseline call-site binding | monitor implementation/descriptor and Runner/Adapter/Transport call-site hashes are in `_baseline_manifest`; omission/addition/byte drift and ephemeral value inclusion fail closed |
| C55 | P2 provenance path separation | P2-monitor is the only P2 test that proves `TeamRunner.drain()` terminal-result-handoff/ack/all-agent settlement/cleanup; P2-Protocol remains schema-v2 production Adapter/Transport without TeamRunner/`modeling_team run` and any Runner handoff, Modeling terminal, ack, all-three settlement, TeamRunner invocation, StartLedger reserve, or ledger event fails |
| C56 | P2 Protocol fallback evidence | real Broker delivery/reply -> eligible ontology-scoped query completion -> sanitized `fallback_required` -> later verifier complete -> Broker terminal guard/report acceptance -> Protocol cleanup is observed; direct verifier, missing/early fallback, manual `sender_id='runner/terminal-result'`, or fabricated Runner/settlement evidence fails |
| C57 | P2 Session/Lease cleanup order | admin reread/no in-flight -> optional failure/terminal checkpoint -> one Session cancel -> atomic lease auto-release -> reread cancelled Session and every Lease `released` with `released_at`; explicit post-cancel release, second release, or `session_terminal` is not success |
| C58 | P2 deletion evidence and residuals | first-stage non-secret artifact records project-scoped keys non-active, Session cancelled, Lease auto-release, ownership/cleanup receipts/no in-flight Attempts, and org-admin key ACTIVE solely for authenticated DELETE; post-delete Project/Ontology/project-scoped active residuals/FK cascade are verified, org-admin is immediately revoked with second-stage ID/`revoked_at`/non-active + retained audit row, and aggregate evidence proves all created keys non-active |
| C59 | two-stage key/delete evidence | no new deletion credential, direct DB delete, or hard-delete; the still-active org-admin key authorizes DELETE, then is immediately revoked and joined with the pre-delete artifact into final aggregate cleanup evidence |
| C60 | P2/Producer provenance ownership | monitor directly observes real `TeamRunner.drain()` handoff/ack/all-agent settlement; Protocol ends at Broker guard/report acceptance and cleanup; final fresh Producer alone proves Modeling terminal -> real Runner handoff -> Protocol terminal -> all-three settled |

Run focused checks with:

```bash
uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'
uv run --project backend ruff check modeling_team
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/base-three-agent.yaml \
  --task modeling_team/tasks/new-scope-business-slice.yaml
```

## Real-run preflight

Before any reservation or semantic start, the failed run `r` must pass the Round 48 closure gate:
freeze the recoverable P0 envelope digest and missing-candidate fact, append its one immutable
`runtime/infrastructure` terminal failure, perform the mandatory ordered closeout, and preserve its
non-secret failed-written evidence. P0 blocks PASS/new-start authorization but does not block that
closeout. The independent tester then runs both P2 tests described below; only after both PASS may
the delivery side append the unique continuing-authorization tranche 8 `+2`, generate two matching
fresh baselines, and bind repair authorization to the second baseline.

- freeze the reviewed requirement, design, test plan, Profile, Packages, Skills, Task, sources,
  Runner, Adapter, and relevant platform MCP hashes;
- verify PostgreSQL, Oxigraph, backend `127.0.0.1:8001`, frontend `127.0.0.1:5173`, authenticated
  Codex app-server, `bwrap`, and backend environment;
- confirm no run directory or platform identity is reused;
- run role visibility probes before Modeling receives the business material;
- record the 20-minute gate origin and semantic-start count only after the Round 48 closeout, P2,
  tranche, two-baseline, and repair-authorization gates;
- atomically reserve the authorized fresh run in the cross-run ledger and verify concurrent/over-budget
  denial; no reservation is created for P2 or baseline evidence;
- confirm the answer contract remains tester-only and no answer is in staged inputs.
- before a business start, use one temporary production Adapter/Protocol roster and scope to prove
  three deterministic layers independently: real bwrap read-only mechanics mount, exact registered
  Agent callback read plus negative matrix, and real app-server native MCP `dry_run=validated`.
  Do not require a no-candidate model Thread to choose `exec`, and do not label callback evidence as
  model behavior; all three layers must share the same staged config and finish with zero residuals.

The two independent P2 tests are intentionally no-semantic-start evidence. They deliver no business
source, make no R2.3-002 StartLedger reservation or `semantic_start`, and retain no product scope.
P2-monitor uses only schema-v1 base smoke and does not test fallback; P2-Protocol uses the production
Adapter/Transport path without TeamRunner or `modeling_team run`, and any TeamRunner/ledger event is a
failure. When a real path requires platform state, that P2 run may create one uniquely owned ephemeral
Project/Ontology/bootstrap-admin/read/model-or-Protocol key, Build Session, and Lease. Before deleting
the Project, freeze a first-stage artifact covering every project-scoped read/model/Protocol key exact
ID/`revoked_at`/non-active, cancelled Session, Lease auto-release, ownership, cleanup receipts, and no in-flight Attempts;
record the org-scoped bootstrap-admin key exact ID as `ACTIVE` solely for the upcoming authenticated
DELETE and exclude it from first-stage non-active assertions. Use that active org-admin credential for
DELETE, verify Project/Ontology absence, project-scoped active residuals zero, and FK cascade behavior,
then immediately revoke it and freeze second-stage exact ID/`revoked_at`/non-active plus retained audit
row. Aggregate both artifacts and prove every created key ended non-active; no new deletion credential,
direct DB delete, or hard-delete is allowed. Session cleanup is ordered as
admin reread/no in-flight -> optional failure/terminal checkpoint -> one Session cancel -> atomic lease
auto-release -> reread cancelled Session and every Lease released with `released_at`; no explicit
post-cancel release is allowed. Existing FK may cascade-delete project-scoped key/Session/Lease rows.
The org-scoped bootstrap-admin revoked audit row (`project_id=NULL`) remains and is never hard-deleted;
post-delete Project/Ontology absence and zero active residuals are required. P2-monitor alone proves
real `TeamRunner.drain()` terminal-result-handoff/ack/all-agent settlement/cleanup; P2-Protocol ends at
Broker terminal guard/report acceptance and Protocol cleanup, and must not claim/fabricate Runner
handoff, Modeling terminal, ack, or all-three settlement. The final fresh Producer proves the complete
candidate/receipt/query/verifier -> Modeling terminal -> real Runner handoff -> Protocol terminal ->
all-three settled sequence. P2-Protocol repairs/verifies the producer-side candidate-artifact contract
for fresh runs; it does not rewrite `r` or fabricate its missing historical artifact. A future
implementation change must run the AGENTS.md GitNexus upstream impact check before editing any symbol
and must surface HIGH/CRITICAL risk; this plan revision edits no code.

## Real producer run

Use `base-three-agent`, `new-scope-business-slice`, and create mode. Required direct evidence:

1. fresh run, three fresh Threads, fresh Project/Ontology/Build Session/Lease;
2. exact per-role staged-source manifests and passed visibility probes;
3. Coordinator initial assignment and continued response to an outer user message while peers work;
4. semantic Modeling-to-Protocol delivery and Protocol receipt/conflict feedback;
5. each released answer follows a grounded Coordinator question, is verbatim, and only one answer
   is released at a time;
6. Protocol alone calls the formal platform MCP and every Batch is immutable
   `dry_run -> apply_atomic`;
7. Shape negative is rejected without workspace movement;
8. final platform facts contain the published `C -> B -> A` path, Draft isolation, output-field
   continuity, explicit unknown, source/Evidence lineage, and either complete generic-query state or
   an eligible `fallback_required` episode with native verifier `complete=true`; candidate-required-
   assertions and one-to-one lineage are bound to the same revision/digest;
9. validation conforms and reasoning is consistent;
10. Build Session completed, Lease released, keys revoked, Runtimes stopped, secrets destroyed;
11. non-empty Project/Ontology retained and handoff matches live platform identity/version;
12. all Agents settled and Coordinator final summary faithfully represents terminal results.

At producer cleanup, the scope is only `retained-pending-acceptance`; no R2.3-003 handoff exists.

If the first run ends before a complete semantic result, record its primary failure category and
evidence. A second fresh start requires a confirmed narrow non-modeling defect, its tested repair,
and a newly frozen baseline. A modeling-quality failure does not authorize start two.

## Independent Agent round

The Requirement Tester must first review the stable implementation and append a round below. It
starts one separate fresh no-history read-only Agent only after producer settlement and evidence
freeze. The Agent cannot create, continue, steer, stop, or mutate the producer run. In Phase A it
reports `PHASE_A_PASS`/FAIL/INCONCLUSIVE for:

- source/answer isolation and fresh identities;
- real role collaboration and Protocol-only writes;
- immutable Batch and Shape-negative integrity;
- published path, Draft isolation, field continuity, explicit unknown, Evidence/lineage, and query
  completeness;
- validation/reasoning;
- Session/Lease/key/Runtime/secret closure;
- retained pending-acceptance state and direct platform match.

Runner summaries are indexes only. Missing raw evidence is not repaired by recreating the run.
The tester/acceptance Agent receives a fresh read-only credential only if supplementary live
queries are needed; it never receives the revoked Protocol/admin key. The credential is revoked
after the query evidence is frozen. Only after Phase A PASS may the Delivery Agent run the
deterministic publisher. The same independent Session then receives only the published handoff and
direct read-only platform evidence for Phase B. It verifies exact fields, identity/version binding,
immutability, and absence of secrets or semantic duplication, then returns the final
PASS/FAIL/INCONCLUSIVE recorded for R2.3-002.

## Regression, runtime, and closure

Because no backend/frontend source change is planned, run the complete repository-local team suite,
Ruff, configuration validation, service restart (shared runtime configuration is exercised), and:

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
git diff --check
```

If implementation changes `backend/`, additionally run `cd backend && uv run pytest`. If it changes
`frontend/`, additionally run `cd frontend && npm run build && npx playwright test`.

## Test rounds

No independent round has run yet. Append every round; never replace failed history.

### Round 1 — 2026-07-31 independent implementation/preflight test — FAIL

- Stable baseline: uncommitted development-ready worktree supplied after cycle 1. Requirement
  implementation surfaces: `modeling_team/contracts.py`, `runner.py`, `platform_scope.py`,
  `runtimes/codex.py`, `start_ledger.py`, `handoff.py`, v2 Task and focused tests. No producer
  semantic run, Project/Ontology creation, Agent steering, or fresh semantic start was performed.
- Commands and results:
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 42 tests.
  - `uv run --project backend ruff check modeling_team`: PASS.
  - v2 and v1 `python -m modeling_team validate` using `base-three-agent`: PASS.
  - `git diff --check`: PASS.
  - Restart plus health checks: service became active after startup; `GET /api/health` and frontend
    `GET /` both PASS. The immediate post-restart backend probe was connection-refused while the
    service was still starting; the 10-second retry passed.
- Executed automated/static cases:
  - C01, C02, C05, C07--C10, C11, C15, C16, C18, C20, C22 and C23 have passing focused
    implementation evidence, subject to the failures below.
  - C03/C04: FAIL. A role source pointing at `docs/requirements/requirements-v2.3.md`, a known
    role absent from the base profile, a repo-local symlink, a fixture named `secret-answer.txt`,
    and a `historical-run` fixture were all accepted by `load_task`. The source gate does not meet
    the required fail-closed boundary.
  - C12: FAIL. No role visibility probe exists and `TeamRunner.start()` records semantic start
    immediately after roster startup, before calling the first-turn delivery loop. The required
    visibility-before-semantic-start proof and the 20-minute gate are absent.
  - C13, C14, C17, C19, C21, C24--C27, C29, C31 and C32: FAIL. `PlatformScope` reads flattened
    `recent_sessions`, but the real REST Build Context returns sessions under
    `agent_state.active_sessions` and `agent_state.recent_sessions`. An offline actual-shape
    reproduction deleted an owned empty Project without a Session detail/cancel request, and
    retained a non-empty producer with `workspace_version: None`. `OntologyWorkspaceContextRead`
    has no version/revision field. A semantic-start terminal failure is never recorded by the
    Runner/CLI, so the conditional second start cannot become reachable. Deleting a published
    handoff permits the same producer to publish another one.
- Defects requiring repair before a producer run:
  1. **Critical — C13/C14/C24--C27/C29/C31:** incorrect Build Context response parsing can skip
     active Session/Lease/Attempt checks and destructive cancellation/cleanup; retained producer
     state can be accepted without a completed Session. Evidence: `modeling_team/platform_scope.py`
     reads root `recent_sessions` at lines 161--164 and 274--275, whereas
     `backend/app/services/build_sessions.py` returns it at lines 299--305. The actual-shape
     reproduction made no `/api/build-sessions/session-1` request yet returned
     `owned_project_deleted=True`.
  2. **Critical — C14/C17/C31:** final workspace-version binding is impossible with the selected
     platform response; `_workspace_version()` returns `None` and the publisher accepts it.
     Evidence: `platform_scope.py:262-268`; `backend/app/api/schemas.py:72-79`. The retained
     reproduction returned `workspace_version: None`.
  3. **High — C03/C04:** Task v2 source validation accepts forbidden/indirect inputs and roles not
     in the selected roster. Evidence: `contracts.py:347-366`; focused loader reproduction above.
  4. **High — C12/C19/C21:** no visibility-probe mechanism, no 20-minute enforcement, and no
     production call to `StartLedger.terminal_failure`; the ledger's permitted second-start path is
     therefore unreachable. Evidence: `runner.py:177-191`, `start_ledger.py:54-96`, and the only
     production CLI lifecycle at `__main__.py:100-125`.
  5. **High — C32:** handoff immutability is path-existence-only; after deleting the file, the same
     run publishes again. Evidence: `handoff.py:18-44`; focused reproduction printed
     `republished-after-deletion: True`.
- Unexecuted by explicit scope: C06 collision fixture, full live Codex MCP/visibility preflight,
  real producer evidence, Phase A/Phase B independent Agent acceptance, and semantic/retrieval
  gates. These remain unexecuted, not passed; a real producer must not start until the defects are
  repaired and a fresh baseline is frozen.

### Round 2 — 2026-07-31 independent retest after development cycle 2 — FAIL

- Stable baseline: uncommitted development-ready cycle-2 worktree. Round 1 history is retained.
  No producer semantic run, Project/Ontology creation, Agent steering, or fresh semantic start was
  performed in this round.
- Commands and results:
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 46 tests.
  - `uv run --project backend ruff check modeling_team`: PASS.
  - v2 and v1 `python -m modeling_team validate` using `base-three-agent`: PASS.
  - `git diff --check`: PASS.
  - Restart plus health checks: service active, backend `/api/health` and frontend `/` PASS after
    frontend startup completed. The first frontend probe at 10 seconds was connection-refused while
    Vite preview was still starting; the next 10-second retry passed.
- Fixed and verified from Round 1:
  - C03/C04 source boundary: requirements, `secret-*`, and `historical-*` fixture paths now fail
    closed; focused tests also cover a source role absent from the selected Profile and a symlink.
  - C13/C24/C25 actual nested Build Context shape: code reads
    `agent_state.active_sessions`/`recent_sessions`; focused tests now prove cancellation before
    empty-scope deletion and block `applying` cleanup.
  - workspace version now comes from the actual Modeling Context shape
    (`workspace.workspace_version`), not Workspace Context; source implementation confirms that
    response at `backend/app/services/modeling_batches.py:525-555`.
  - C32 path deletion and concurrent publication: append-only locked publication receipt rejects
    republishing after handoff-file deletion and permits one concurrent winner. Shape-negative
    dry-run receipt was added to Task objective and terminal evidence.
- Still failing / blocking:
  1. **Critical — C14/C29/C31:** successful non-empty cleanup can cancel an active Build Session
     and then label the producer `retained-pending-acceptance`; it also permits retention when the
     Build Context has no Session at all. A focused actual-shape reproduction produced that retained
     disposition after `POST /api/build-sessions/session-1:cancel`. Success must instead require
     an explicitly `completed` owned Build Session identity and released Lease before retention or
     handoff recheck. Evidence: `modeling_team/platform_scope.py:203-238, 328-348`.
  2. **High — C12:** visibility evidence remains a host-filesystem comparison of
     `run.root/sources/<role>`; it neither executes inside each role's bubblewrap namespace nor
     proves forbidden paths unavailable before business delivery. Runtime Adapter declares no probe
     operation. Evidence: `modeling_team/runner.py:207-230`,
     `modeling_team/runtimes/base.py:39-61`, and Codex copies source files into private homes at
     `modeling_team/runtimes/codex.py:123-127`.
  3. **High — C12/C21:** the 20-minute gate is bypassable because `--freeze-started-at` is optional
     and ledger reservation substitutes current time; it is also checked only after scope/key and
     Runtime startup. A retry repair may omit `baseline_hash`, after which any second baseline is
     accepted. Focused temporary-ledger reproductions printed `semantic start accepted using default
     current freeze timestamp` and `second start accepted with no repair baseline binding`.
     Evidence: `modeling_team/__main__.py:71-108`, `start_ledger.py:33-48, 82-143`, and
     `runner.py:165-189`.
- C06 collision fixture: PASS. Two same-basename `instructions.md` source entries were staged at
  their distinct stable relative paths without overwrite.
- Unexecuted, therefore not PASS: a live in-namespace Codex MCP/visibility preflight; all real
  producer collaboration, Batch/Shape, validation,
  reasoning, generic-query, cleanup and retained-handoff evidence; independent Phase A/Phase B
  acceptance. No start budget was consumed. Repair the three defects above, add regressions for
  them, then return the stable worktree for Round 3 before considering a producer run.

### Round 3 — 2026-07-31 independent retest after development cycle 3 — FAIL

- Stable baseline: uncommitted development-ready cycle-3 worktree. No producer semantic run,
  Project/Ontology creation, Agent steering, or fresh semantic start was performed.
- Commands and results:
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 50 tests.
  - `uv run --project backend ruff check modeling_team`: PASS.
  - v2 and v1 `python -m modeling_team validate` using `base-three-agent`: PASS.
  - `git diff --check`: PASS.
  - Restart plus backend `/api/health` and frontend `/`: PASS after normal startup.
- Fixed and verified from Round 2:
  - C14/C29/C31 success retention now requires one exact owned `completed` Build Session and only
    released Leases; its identity and final workspace version are retained and rechecked. Focused
    actual-shape tests reject zero, cancelled, active, multiple, and foreign Sessions without
    cancellation, while the completed/released case is retained.
  - v2 missing freeze is rejected before run-directory creation; repair authorization requires a
    non-empty exact new baseline hash; second-start baseline mismatch is rejected. The Run/Adapter
    order records runtime visibility probe before semantic start and first Task turn.
  - Codex now invokes a bubblewrap probe constructed from each Agent's `namespace_command` after
    roster preflight and before semantic start; v1 does not call the v2-only probe.
- Still failing / blocking:
  1. **High — stale freeze preflight (C12/C21):** `StartLedger._reserve()` validates only timestamp
     syntax, not the elapsed 20-minute gate. A stale 2020 freeze was accepted by
     `TeamRunner.prepare()` and created a run directory; it would proceed to scope/key/Runtime
     startup before the later `mark_semantic_start()` check. The requirement requires stale freeze
     rejection before run directory, scope, key, and Runtime. Evidence:
     `modeling_team/runner.py:78-106`, `modeling_team/start_ledger.py:109-140`; focused output:
     `stale freeze accepted by prepare; run directory exists: True`.
  2. **High — Runtime proc isolation evidence (C12):** the new probe checks only the always-absent
     `/proc/999999/environ`, while the same bubblewrap command explicitly mounts `/proc`.
     It therefore does not prove the requested proc category is denied; a matching safe bubblewrap
     check printed `proc-self-readable` for `/proc/self/environ`. Evidence:
     `modeling_team/runtimes/codex.py:99-139, 240-245`.
- Unexecuted, therefore not PASS: a live authenticated Codex app-server visibility/MCP preflight;
  real producer collaboration, actual immutable Batch/Shape receipts, validation/reasoning,
  generic query, cleanup, retained-handoff, and independent Phase A/Phase B acceptance. No start
  budget was consumed. Fix the two blockers and add regressions before Round 4; do not begin the
  producer yet.

### Round 4 — 2026-07-31 independent retest after development cycle 4 — FAIL

- Stable baseline: uncommitted development-ready cycle-4 worktree. No producer semantic run,
  Project/Ontology creation, Agent steering, or fresh semantic start was performed.
- Commands and results:
  - Focused freeze and PID-resolution tests: PASS (eight tests): stale/future reservation,
    semantic-start elapsed-time recheck, missing/stale prepare rejection, sibling PID evidence
    construction, missing sibling PID rejection, nested-bwrap PID resolution, and MCP-child
    exclusion.
  - Direct v2 `prepare()` checks using a temporary ledger and a scope-factory spy: PASS. Stale,
    future, and missing freeze each printed
    `rejected-before-run-directory-scope-and-reservation`; no run directory, Scope call, or ledger
    reservation was created.
  - Direct safe bubblewrap command made from `namespace_command()`: FAIL. The unmodified probe
    command exited 1 with `bwrap: Unknown option -c`. A diagnostic-only command with a `--`
    delimiter inserted before `/bin/sh` exited 0 and printed
    `self-proc-readable;sibling-proc-denied`; it did not alter source or start an Agent.
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 56 tests.
  - `uv run --project backend ruff check modeling_team`: PASS.
  - v2 and v1 `python -m modeling_team validate` using `base-three-agent`: PASS.
  - `git diff --check`: PASS.
  - Service restart plus backend `/api/health` and frontend `/`: PASS after normal startup. The
    immediate probes during frontend build were connection-refused; the final backend response was
    `{"status":"ok"}` and the frontend response succeeded.
- Fixed and verified from Round 3:
  - **C12/C21 freeze gate:** `StartLedger.reserve()` now rejects stale and future timestamps before
    reservation, and `TeamRunner.prepare()` calls it before `root.mkdir`; missing freeze also
    rejects before mutable run state. `mark_semantic_start()` rechecks elapsed freeze time, so a
    once-valid reservation cannot start after the 20-minute gate. Evidence:
    `modeling_team/runner.py:77-99`, `modeling_team/start_ledger.py:35-49,108-150` and the focused
    PASS checks above.
  - **C12 PID test design:** evidence contains only fixed categories, never host PID values; the
    test suite covers sibling app-server PID paths, rejects missing sibling PIDs, selects the inner
    app-server beneath bwrap, and excludes a protocol MCP child. Evidence:
    `modeling_team/runtimes/codex.py:111-151,393-421` and
    `modeling_team/tests/test_codex_isolation.py:19-92`.
- Still failing / blocking:
  1. **High — Bubblewrap Runtime cannot execute its visibility probe (C12):**
     `probe_role_visibility()` replaces the child command with `['/bin/sh', '-c', script]` but
     omits bubblewrap's required `--` command delimiter. The actual generated command therefore
     treats `-c` as a bubblewrap option and fails before it can check role files, self `/proc`, or
     real sibling process isolation. The same delimiter omission also affects the app-server
     command assembled by `namespace_command()`. Expected: the in-namespace probe executes before
     semantic start; actual: exit 1, `bwrap: Unknown option -c`. Evidence:
     `modeling_team/runtimes/codex.py:140-147,244-353`; direct temporary-runtime reproduction
     above. The 56 tests mock `subprocess.run`, so they do not exercise bubblewrap argument
     parsing.
- Unexecuted, therefore not PASS: authenticated live Codex app-server and MCP visibility preflight
  (blocked by the defect above); real producer collaboration, immutable Batch/Shape receipts,
  validation/reasoning, generic query, cleanup, retained-handoff, and independent Phase A/Phase B
  acceptance. No start budget was consumed. Repair the bubblewrap command, add a non-mocked
  bubblewrap execution regression, then return the stable worktree for Round 5; do not begin the
  producer before that retest.

### Round 5 — 2026-07-31 independent retest after development cycle 5 — PASS (pre-producer readiness)

- Stable baseline: uncommitted development-ready cycle-5 worktree. No semantic producer run,
  Project/Ontology creation, Agent steering, authenticated app-server startup, or fresh semantic
  start was performed.
- Exact Runtime regression checks:
  - The non-mocked `test_generated_visibility_probe_runs_in_real_bwrap_with_inner_sibling_pid`
    passed. It starts only temporary `bwrap ... -- /bin/sh -c 'exec sleep 30'` sibling processes,
    resolves their inner host PIDs, and invokes the generated `probe_role_visibility()` command.
  - A separate direct temporary-runtime execution passed and printed
    `real-bwrap-probe: passed; self-proc-visible; sibling-inner-pid-denied; evidence-pid-free`.
    It confirms the generated command executes `/bin/sh -c` after the bubblewrap separator, sees
    `/proc/self/environ`, denies the actual sibling inner PID path, and returns evidence containing
    only categories, not host PID values.
  - Generated app-server command shape passed: all bwrap options precede `--`, followed by
    `/agent/bin/codex --config web_search=\"disabled\" ... app-server`. The v1/non-bwrap command
    remains `[codex, app-server]` with no separator. Mocked PID tests still cover nested bwrap and
    protocol MCP-child resolution/exclusion.
- Commands and results:
  - Focused Runtime command, non-mocked bubblewrap, PID-evidence, and v1/non-bwrap tests: PASS,
    5 tests.
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 58 tests.
  - `uv run --project backend ruff check modeling_team`: PASS.
  - v2 and v1 `python -m modeling_team validate` using `base-three-agent`: PASS.
  - `git diff --check`: PASS.
  - Service restart plus backend `/api/health` and frontend `/`: PASS after normal startup; backend
    returned `{"status":"ok"}` and the service was active.
- Fixed and verified from Round 4:
  - **C12 bubblewrap command boundary:** `namespace_command()` inserts `--` before the Codex child,
    and the visibility probe retains that boundary when replacing it with `/bin/sh -c`. The actual
    non-mocked command now executes rather than treating `-c` as a bubblewrap option. Evidence:
    `modeling_team/runtimes/codex.py:135-153,245-355` and
    `modeling_team/tests/test_codex_isolation.py:98-208`.
- Result scope: the deterministic implementation/pre-producer gate is PASS and has no known
  remaining automated or local-runtime defect. The requirement's real producer collaboration,
  immutable Batch/Shape receipts, validation/reasoning, generic query, cleanup,
  retained-scope handoff, and independent Phase A/Phase B acceptance remain **UNEXECUTED**, not
  failed, because this round intentionally did not create or continue a semantic producer run and
  did not consume the authorized start budget. Requirement-level completion remains subject to the
  completion rule above.

### Round 6 — 2026-07-31 independent test of first real producer platform-contract repair — FAIL

- Stable baseline: cycle-6 uncommitted development-ready worktree. No producer/Agent semantic
  modeling, Project/Ontology/Session/Lease creation, live `publish-handoff`, or second semantic
  start was performed. The only real CLI smoke was the read-only `baseline` command.
- Commands and results:
  - Focused existing contract, task-text, baseline, retained-input, and offline-handoff tests:
    PASS, 5 tests. These tests do not cover the defects below.
  - Direct fake-Adapter Runner exercise: PASS. For v2, Scope-derived Protocol context is injected
    automatically into the Protocol text as exactly `project_id`, `ontology_id`, and
    `workspace_version`; it is absent from Coordinator/Modeling text and excludes the fake private
    key. v1 retains its original no-context task text. This used no Runtime, ledger, or platform.
  - `python -m modeling_team baseline --run-id r23002-baseline-future-r6 ...`: PASS. Its manifest
    and hash exactly match `TeamRunner.preview_baseline`; it created no run directory or ledger
    record. The ledger and failed first producer `r23002-real-20260731b` directory hashes were
    unchanged before/after this check and the full suite.
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 64 tests.
  - `uv run --project backend ruff check modeling_team`, v2 and v1 validation, and
    `git diff --check`: PASS.
  - Existing service was active; backend `/api/health` returned `{"status":"ok"}` and frontend
    `/` succeeded. No restart was needed because this cycle changes only team-runner assets.
- Still failing / blocking:
  1. **High — Protocol-only Modeling Batch reference is not sufficient to construct the required
     payloads without guessing (C08/C09/C12):** the reference proves only top-level field-name
     sets. It omits envelope types/defaults/constraints, which fields are required for every
     `create_*` command, the property datatype-vs-object-class alternative, and the nested Shape
     constraint grammar. In particular, its `create_shape` entry permits an untyped
     `constraints` value but does not name `path_id`; a no-resource direct Handler preparation of
     `{"target_class_id":"class","constraints":[{}]}` failed with
     `Missing required field: path_id`. A likewise reference-permitted partial entity payload
     failed with `Missing required field: class_iri_or_legacy_id`. The staged public protocol also
     points to `/opt/mechanics-contract.json`, but no such current Protocol-visible input is
     staged. The reference contains no tester-only answer or expected domain structure, which is
     correct, but it cannot be the promised exact mechanical contract. Evidence:
     `modeling_team/references/modeling-batch-item-contract.json:4-22`,
     `backend/app/api/schemas.py:500-526`, `backend/app/mcp/tools/modeling_batches.py:25-75`, and
     `backend/app/services/semantic_command_compiler.py:843-962,1239-1255,1433-1447`.
  2. **High — offline handoff does not bind retained input to the CLEANED state (C17/C29/C31/C32):**
     `publish_offline_scope_handoff()` checks only state name/run ID, then trusts
     `retained-handoff-input.json` for terminal results and scope. It never requires exact equality
     with `state.cleanup.scope` or `state.terminal_results`. A temporary no-network reproduction
     set `state.json` to `CLEANED` with `scope_disposition=deleted-empty` and Protocol `blocked`,
     while retained input claimed a distinct retained scope and three completed Agents. A fake
     recheck matching the retained values caused the function to write a handoff:
     `MISMATCH_ACCEPTED: True`. Expected: reject any terminal-result or scope identity/version/
     Session/disposition mismatch before bootstrap/recheck/publication. Evidence:
     `modeling_team/handoff.py:82-119`; the existing happy-path test changes both files together
     and therefore misses this mismatch.
  3. **High — retained handoff input can persist credential-like Agent terminal content
     (C17/C18/C30):** `_write_retained_handoff_evidence()` copies the entire
     `terminal_results` object without an allowlist or recursive secret rejection. A temporary
     completed Protocol result with the non-secret canary summary
     `credential-canary-must-not-be-persisted` was written verbatim, printing
     `UNFILTERED_TERMINAL_SUMMARY_PERSISTED: True`. Expected: retained input remains non-sensitive
     regardless of Agent-provided summary content, while retaining only the mechanically necessary
     completion proof. Evidence: `modeling_team/runner.py:550-574`. Normal cleanup calls this
     helper only after `retained-pending-acceptance`, but that gate does not sanitize its payload
     and does not repair the offline state/input mismatch.
- Unexecuted: a live successful retained producer and independent Phase A/B; live
  `publish-handoff` CLI with a real bootstrap credential (intentionally not invoked because no
  successful retained scope exists and it would mutate key state); actual immutable Batch/Shape,
  validation/reasoning/query, cleanup, and handoff evidence. No second-start budget was consumed.
  Repair all three High defects, add negative regressions for the exact contract, state/input
  mismatch, and secret canary, then return the stable worktree for Round 7. Do not launch the
  second producer start before that retest.

### Round 7 — 2026-07-31 independent retest of Round 6 High defects and deterministic gates — FAIL

- Stable baseline: cycle-7 uncommitted development-ready worktree. This round did not start a
  producer/Agent, create a Project/Ontology/Session/Lease, invoke live `publish-handoff`, or
  consume the second semantic-start budget. All focused publisher reproductions used temporary
  directories and fake bootstrap/request functions only.
- Commands and results:
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 65 tests. This covers the repaired retained-input canary, state/evidence mismatch
    rejection, happy-path publisher, Phase rejection, drift, exactly-once/concurrent publication,
    and deletion-after-publication regression. It does not assert that a failed Phase A is rejected
    before `bootstrap_admin`.
  - `uv run --project backend ruff check modeling_team`: PASS. A first unqualified `ruff check`
    was unavailable in the shell; the repository-prescribed `uv run --project backend` command
    passed.
  - v2 `python -m modeling_team validate --profile modeling_team/profiles/base-three-agent.yaml
    --task modeling_team/tasks/new-scope-business-slice.yaml`: PASS, roster exactly
    `coordinator`, `modeling`, `protocol`. The matching v1 `base-capability-smoke` validation:
    PASS. `git diff --check`: PASS.
  - Baseline/role-boundary regression: PASS through the full suite. v2 assigns the mechanical
    contract only to Protocol, while v1 has no v2 role source; the task-text unit test confirms
    injected scope context is Protocol-only and excludes private/admin material. No test action
    changed the real start ledger or failed producer tree.
  - Immutable-input check: PASS. Before/after SHA-256 values were identical for
    `workspaces/modeling-runs/.r2-3-002-start-ledger.jsonl`
    (`4af19019a7c2c328daac1f4fc0b67a7fefb31ac275c04f45b4194b78ad38299f`)
    and recursive failed-run `r23002-real-20260731b`
    (`b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`).
  - Local runtime health: PASS. `ontology-platform.service` was `active`; backend
    `GET /api/health` returned `{"status":"ok"}` and frontend `/` returned success. No restart was
    needed because this review changed no product runtime code.
  - Direct temporary offline-publisher checks: `BLOCKED` terminal status and `deleted-empty`
    disposition both reject before fake `bootstrap_admin`; state/evidence scope mismatch remains
    rejected before bootstrap by the automated negative test. Retained input now writes exactly the
    three completed role statuses and excludes the credential-like summary canary. These repair the
    Round 6 C17/C18 state-binding and retained-secret findings for the normal cleanup path.
- Still failing / blocking:
  1. **High — the Protocol-only contract still omits the required mode/lease conditional
     (C08/C09/C12):** the new v2 reference correctly supplies the item/evidence payload fields,
     all six command envelopes, property branch, Shape `path_id`, unknown-key compiler behavior,
     defaults, and forbidden targets, without a tester answer. But it states only that
     `lease_token` is optional/default-null and has no conditional rule for `mode`:
     `modeling_team/references/modeling-batch-item-contract.json:4-15`. The actual service rejects
     a dry run containing any lease and rejects every non-dry-run apply without a lease:
     `backend/app/services/modeling_batches.py:201-206`. Therefore Protocol must still guess a
     mechanically mandatory envelope condition for its required dry-run then apply sequence; the
     invalid examples are not fully decidable from the Protocol-visible reference. Expected: encode
     the exact `dry_run => omit lease_token` and `apply_* => require lease_token` behavior in the
     visible contract and test each invalid example.
  2. **High — `PHASE_A_FAIL` performs privileged publisher work before rejection (C29/C30):**
     `publish_offline_scope_handoff()` reads the verdict at
     `modeling_team/handoff.py:83`, but constructs `PlatformScope` and calls
     `recheck_retained_producer()` at lines 115-124 before the only Phase-A gate in
     `publish_scope_handoff()` lines 21-24. A temporary no-network reproduction with otherwise
     matching CLEANED state/evidence and verdict `PHASE_A_FAIL` raised the expected error but printed
     `PHASE_FAIL_BOOTSTRAP_CALLED=True`. The recheck obtains a fresh admin credential when absent
     (`modeling_team/platform_scope.py:408-415`). Expected: reject any non-PASS verdict before
     bootstrap, platform queries, or credential creation; add a test asserting both fake bootstrap
     and fake request have zero calls.
- Additional observations (not the release decision):
  - **Medium — declared scalar types are stricter than the current handler/compiler:** despite the
    reference declaring strings, no-resource handler preparation accepted integer `name` for
    `create_class` and `create_relation_type`, integer entity `label`, and integer Shape `path_id`.
    This does not prevent Protocol from constructing valid string payloads, but means the stated
    type contract is not an exact acceptance contract. Either enforce the declared types or label
    them as supported construction types rather than full handler acceptance semantics.
  - **Medium — private retained-evidence helper lacks its own successful-scope guard:** a direct
    temporary call to `_write_retained_handoff_evidence()` with `owned=false` and
    `scope_disposition=deleted-empty` still created its input file. Normal `cleanup()` invokes the
    helper only after `retained-pending-acceptance`, and the offline publisher rejects this forged
    input before bootstrap, so no normal-path publication was observed. Add a helper-level guard to
    keep the persistence invariant local and regression-test it.
- Unexecuted: real successful producer collaboration; real immutable Batch/Shape apply/dry-run,
  validation/reasoning/query, cleanup and independent Phase A/B evidence; and live publisher
  bootstrap/revocation. These remain intentionally unexecuted because this round found High
  deterministic gate defects and must not consume the authorized second start. Repair both High
  defects (and preferably the two Medium invariant/type gaps), add the two precise negative
  regressions, then return for Round 8 retest before any second producer start.

### Round 8 — 2026-07-31 independent retest of Round 7 defects and deterministic gate — PASS with non-blocking Medium

- Stable baseline: cycle-8 uncommitted development-ready worktree. No producer/Agent was started;
  no Project/Ontology/Build Session/Lease was created; no real `publish-handoff`, credential
  bootstrap, or second semantic start occurred. Direct checks used only temporary directories,
  fake Sessions, and fake publisher callbacks.
- Commands and results:
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 67 tests. `uv run --project backend ruff check modeling_team`: PASS. v2 and v1
    `python -m modeling_team validate --profile modeling_team/profiles/base-three-agent.yaml`
    commands: PASS with the exact three-role roster. `git diff --check`: PASS.
  - Contract/service direct checks: PASS. The Protocol-visible contract now declares
    `dry_run => lease_token omitted or null`, both apply modes => non-empty string, and a required
    `expected_workspace_version` equal to Service's current value. The real Service rejected a
    dry run with a lease (`invalid_lease_token`), `apply_atomic` and `apply_partial` without a
    lease (`ontology_lease_conflict`), and a stale workspace version
    (`workspace_revision_conflict`). Pydantic rejected empty apply leases and an empty workspace
    version, while it accepted dry-run null and non-empty apply leases. Thus the relevant invalid
    requests are decidable from the reference and rejected at the actual API/Service boundary.
  - Phase-A direct checks: PASS. For both `PHASE_A_FAIL` and another non-PASS value
    `PHASE_A_BLOCKED`, a missing run root still produced the Phase gate error before state/evidence
    reads, fake bootstrap, fake request, destination parent `mkdir`, receipt, or lock creation;
    all counters and destination effects were zero. The new focused test covers the fail case;
    the independent blocked-value check confirms the guard is not limited to one spelling.
  - Retained-input direct checks: PASS. `_write_retained_handoff_evidence()` itself rejected
    `deleted-empty`, `owned=false`, extra scope fields, and a missing identity field without
    creating a file. A valid owned retained scope created status-only evidence containing exactly
    three `completed` statuses and no summary/credential canary. This closes the Round 7 helper
    invariant gap.
  - Prior state-binding, publisher success/concurrency/replay/deletion-after-replay, drift,
    baseline-preview, and role-private context regressions: PASS in the full suite. v2's contract
    is Protocol-only and injected scope remains absent from Coordinator/Modeling; v1 remains
    unchanged.
  - Immutable inputs: PASS. Before/after SHA-256 was unchanged for the semantic-start ledger
    (`4af19019a7c2c328daac1f4fc0b67a7fefb31ac275c04f45b4194b78ad38299f`) and recursively for
    failed producer `r23002-real-20260731b`
    (`b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`). Existing service was
    active, `/api/health` returned `{"status":"ok"}`, and frontend `/` succeeded; no restart was
    needed because this test round did not change product runtime code.
- Fixed since Round 7:
  1. **High C08/C09/C12 fixed:** the visible contract has the exact lease/mode and workspace
     invariants, with Service-level negative evidence for dry-run lease, both missing apply leases,
     and stale workspace version.
  2. **High C29/C30 fixed:** `publish_offline_scope_handoff()` now rejects every non-PASS Phase A
     verdict immediately after reading the verdict artifact and before reading run/evidence or
     initiating any publisher side effect.
  3. **Medium retained-helper invariant fixed:** the writer now requires exactly the owned,
     retained-pending-acceptance scope keys before it can persist status-only input.
- Remaining observation (non-blocking Medium): canonical Protocol types are now clearly called
  out as strings/integers for `create_class.name`, property fields, Shape `path_id`, and Shape
  counts; however direct no-resource Handler preparation also accepts integer
  `create_relation_type.name`, entity `label`, and Shape `target_class_id`, while those remaining
  contract entries state only the canonical type without an explicit current-acceptance note. The
  contract does not assert a false runtime rejection and Protocol is instructed to send canonical
  values, so this does not block the final real start; add matching acceptance annotations (or
  enforce scalar validation) in a follow-up to make the reference exhaustive.
- Unexecuted: the last authorized real producer start; actual Batch/Shape dry-run/apply receipts,
  validation/reasoning/query, cleanup, and independent live Phase A/B; and live publisher
  bootstrap/revocation. No Critical or High deterministic defect remains. The remaining Medium is
  documentation precision only and does not require another repair round before the final
  authorized real start.

### Round 9 — 2026-07-31 independent test of budget-extension and attempt-2 routing repair — FAIL

- Stable baseline: cycle-9 uncommitted development-ready worktree. This round did not start a
  producer/Agent, create platform resources, create a real Build Session/Lease, publish a real
  handoff, or write the real ledger. All authorization and CLI-success cases used a temporary
  repository root/ledger; the only real CLI invocation deliberately used invalid `+0` and was
  rejected before opening the ledger for write.
- Commands and passing results:
  - Temporary full ledger chain: PASS for the intended chain `start1 -> retryable incomplete
    failure + exact repair -> start2 -> retryable incomplete failure + exact repair -> user +2
    authorization -> start3 -> retryable incomplete failure + exact repair -> start4`; `start5`
    was rejected at cap four. Concurrent identical authorization produced exactly one record;
    duplicate ID/reference, zero, three, and boolean values rejected; wrong repair baseline,
    modeling-quality failure, and a missing latest repair rejected. A presemantic release did not
    consume a start. Ordinary Runner paths have no `authorize_budget` caller; the only product
    caller is the explicit CLI command.
  - CLI isolated-root check: exact `+2` returned zero; duplicate returned exit 2 with immutable-ID
    error. The real invalid CLI check `authorize-budget --additional-starts 0 ...` returned exit 2
    with `budget authorization is invalid`, and real ledger SHA-256 remained unchanged.
  - Routing/settlement regression: PASS in focused and full tests. Profile package roles drive
    Coordinator dependencies for both v1 and v2; early broker report leaves Coordinator absent from
    results, Modeling and Protocol may independently be completed/blocked, each receives one
    mechanical terminal handoff to Coordinator, the Coordinator retry is the sole successful
    terminal result, true duplicate reports reject, and all three settle once before cleanup.
    Coordinator instructions prohibit semantic review and clearly say rejection is not success and
    requires a later retry.
  - `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
    PASS, 71 tests. `uv run --project backend ruff check modeling_team`, v1/v2 validation, and
    `git diff --check`: PASS. `ontology-platform.service` was active; backend health returned
    `{"status":"ok"}` and frontend `/` succeeded.
  - Immutable real evidence: PASS. Before/after SHA-256 was unchanged for start ledger
    `a511b0b1b9950c9f84715bf1725797699f92a2e63e73e6e89c38632b7d6e97ee`, failed run b
    `b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`, and failed run c
    `f4b7e08ba8e821b27142b07871f945db6d118eef0659a69b3d2bd08e86bb45cb`.
- Still failing / blocking:
  1. **High — budget authorization is neither exact `+2` nor globally unique:**
     `StartLedger.authorize_budget()` accepts every integer from one through two and only rejects a
     repeated ID or reference (`modeling_team/start_ledger.py:40-67`). In a temporary ledger,
     `authorize_budget(1, "one", "one start")` succeeded (`ILLEGAL_NONEXACT_PLUS1_REJECTED=False`)
     and a second distinct `authorize_budget(2, "two", "second distinct authorization")` also
     succeeded (`SECOND_DISTINCT_AUTHORIZATION_REJECTED=False`). The isolated CLI likewise accepted
     `--additional-starts 1` with exit 0 and wrote two authorization records after the preceding
     `+2`. Expected: precisely one append-only user authorization, exactly `additional_starts=2`,
     so cap is exactly 4; no later distinct ID/reference may extend it. Actual behavior allows a
     cap of 3 or repeated extensions beyond 4. Add a global-existing-authorization guard and exact
     `== 2` validation, with CLI negative tests.
  2. **High — the Agent-visible dynamic MCP error hides the missing role names and can recreate the
     Coordinator retry deadlock:** broker-level `report_task_result` correctly raises
     `terminal result requires completed roles: modeling, protocol`, but
     `CodexRuntimeAdapter._team_transport_dynamic_result()` discards that payload and returns only
     `Team Transport rejected the request` (`modeling_team/runtimes/codex.py:947-948`). A fake
     socket reproduction printed `DYNAMIC_PREMATURE_SUCCESS=False`,
     `DYNAMIC_PREMATURE_MISSING_ROLES_VISIBLE=False`, and that generic text. Expected: the exact
     missing-role reason reaches the Coordinator's dynamic tool result so its visible instruction
     to wait/retry is actionable; rejection remains non-terminal. Existing tests cover only the
     broker exception, not this Runtime-to-Agent error rendering. Preserve the error text (without
     fabricating a success), and add this adapter-level regression.
- Medium / start3 decision: Round 8's non-blocking canonical-type documentation precision note
  remains unchanged. It does not itself block start3. The two High defects above do block start3:
  the first can silently expand the authorized attempt budget and the second can leave the live
  Coordinator unable to identify which terminal handoffs it must await. Repair both and rerun the
  focused ledger/CLI/adapter/settlement checks before any real start3.
- Unexecuted: actual attempt-2 producer collaboration, platform Batch/Shape/validation/query,
  cleanup, and live independent Phase A/B. No second-start budget was consumed by this test round.

### Round 10 — 2026-07-31 independent retest of Round 9 High defects and dynamic adapter path — FAIL

- Stable baseline: cycle-10 uncommitted development-ready worktree. No producer/Agent, platform
  resource, real ledger write, or real handoff was started. All ledger/CLI success checks used a
  temporary repository root. Dynamic checks used local temporary Unix sockets only.
- Fixed and passing since Round 9:
  1. **Budget authorization High fixed:** `authorize_budget()` now accepts only exact `+2` and
     rejects every second authorization globally. A temporary full chain confirmed concurrent
     distinct IDs have one winner; `+1`, `+3`, same ID/reference, and a second distinct request all
     reject; start3/start4 succeed only after the immediately previous retryable incomplete failure
     plus matching repair baseline; start5 rejects at cap four. Forged multiple authorization and
     forged `additional_starts=3` ledgers fail closed without a write. CLI `+1`/`+3` returned code 2
     without a ledger file; first `+2` succeeded; a second `+2` returned code 2 without appending.
  2. **Coordinator dynamic retry High fixed on the real socket path:** a temporary real
     `TeamTransportBroker` socket returned the safe, exact result
     `Team Transport rejected the request: terminal result requires terminal roles: modeling,
     protocol`; Coordinator remained absent from results, normal send remained unchanged, Modeling
     completed and Protocol blocked reports succeeded, and Coordinator retry succeeded. The
     adapter's malformed/non-string/overlong response tests pass and a missing socket returned the
     generic `Team Transport is unavailable` without reflecting a canary.
  3. v1/v2 role-driven Coordinator dependencies, settled-once/post-settlement reporting, cleanup,
     and Coordinator instructions remain passing. The Coordinator remains a mechanical receiver,
     not a semantic reviewer.
  4. `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`:
     PASS, 75 tests. Ruff, v1/v2 validate, and `git diff --check`: PASS. Service was active,
     `/api/health` returned `{"status":"ok"}`, and frontend `/` succeeded. Real ledger/run b/run c
     hashes remained respectively `a511b0b1b9950c9f84715bf1725797699f92a2e63e73e6e89c38632b7d6e97ee`,
     `b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`, and
     `f4b7e08ba8e821b27142b07871f945db6d118eef0659a69b3d2bd08e86bb45cb`.
- Still failing / blocking:
  1. **High — dynamic transport error allowlist accepts arbitrary forged role names and can leak
     attacker-controlled text:** `_safe_transport_error()` accepts any comma-separated tokens that
     match a broad identifier regex (`modeling_team/runtimes/codex.py:977-984`), rather than the
     actual frozen Coordinator dependency set. A temporary real socket response
     `terminal result requires terminal roles: attacker` was reflected verbatim; a response
     `terminal result requires terminal roles: modeling, secret-from-untrusted-socket` likewise
     printed the canary. Expected: only the exact allowed missing-role list for this frozen
     Coordinator dependency is reflected; unknown, duplicate, extra, or canary-bearing role lists
     are reduced to the generic rejected-request result. Actual: an untrusted socket can falsely
     direct Coordinator to await a nonexistent role and leak controlled content. Add direct socket
     regressions for unknown/extra/duplicate roles and a prefix-canary, then bind validation to the
     actual dependency list before reflection.
- Medium / start3 decision: the earlier canonical-type documentation precision note remains
  non-blocking. The new High is blocking: it defeats both the requested safe error boundary and the
  accurate Coordinator retry instruction. Do not begin real start3 until this allowlist is narrowed
  and independently retested.
- Unexecuted: actual attempt-2 producer collaboration, platform Batch/Shape/validation/query,
  cleanup, live independent Phase A/B, and live publisher. No authorized start was consumed.

### Round 11 — 2026-07-31 independent final retest of dynamic roster allowlist — PASS

- Stable baseline: cycle-11 uncommitted development-ready worktree. No producer/Agent or platform
  resource was started, and no real ledger was written. Dynamic verification used temporary local
  Unix sockets and a temporary broker only.
- Dynamic socket matrix: PASS. With the current registered complete roster, only the exact
  Coordinator object received the exact canonical sorted dependency text
  `terminal result requires terminal roles: modeling, protocol`. A real temporary broker socket
  left Coordinator non-terminal on the early report; Modeling completed, Protocol blocked, and the
  Coordinator retry then succeeded with all three broker results present. Normal dynamic send
  remained unchanged.
  - Each of attacker, extra role, duplicate role, missing role, wrong order, prefix/suffix canary,
    non-Coordinator caller, detached Coordinator object, incomplete roster, and duplicate Modeling
    role returned exactly generic `Team Transport rejected the request`, with no canary reflection.
    This verifies the Runtime binds reflected dependency text to the current frozen roster's unique
    Modeling and Protocol Agent IDs, rather than accepting a broad string pattern.
- Budget and lifecycle regressions: PASS in the focused/full suite. Authorization remains exactly
  one `+2`, forged multiple/cap-over-four records fail closed, CLI invalid counts do not append, the
  repaired start3/start4 chain requires immediately preceding retryable incomplete failure plus
  matching baseline, and start5 rejects. v1/v2 Coordinator dependency/retry, settled-once, cleanup,
  and Coordinator mechanical-only instructions remain passing.
- Full final gate: `uv run --project backend python -m unittest discover -s modeling_team/tests -p
  'test_*.py'` PASS, 75 tests; Ruff, v1/v2 validate, and `git diff --check` PASS. Existing service
  was active; `/api/health` returned `{"status":"ok"}` and frontend `/` succeeded. Real
  ledger/run b/run c SHA-256 values remained unchanged:
  `a511b0b1b9950c9f84715bf1725797699f92a2e63e73e6e89c38632b7d6e97ee`,
  `b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`, and
  `f4b7e08ba8e821b27142b07871f945db6d118eef0659a69b3d2bd08e86bb45cb`.
- Conclusion: no Critical or High deterministic defect remains. The earlier Medium about exhaustive
  current-runtime type annotations in the Protocol construction reference remains documentation
  precision only; canonical Protocol values are enforced by task instruction and the observation
  does not block the authorized real start3. Real producer collaboration, Batch/Shape evidence,
  cleanup, independent Phase A/B, and live publisher remain unexecuted and must be evaluated in
  the separately authorized live attempt.

### Round 12 — 2026-07-31 independent baseline-completeness and final pre-start gate — PASS

- Stable baseline: uncommitted development-ready worktree. This round did not start a producer or
  Agent, create platform resources, mutate the real ledger, or alter production source. The
  transport-change proof used only a temporary run root and a process-local mocked digest result.
- Baseline completeness and side-effect boundary: PASS. `preview_baseline` includes
  `files.team_transport`, whose value equals the SHA-256 of the actual
  `modeling_team/transport_mcp.py`; it created neither the proposed run root nor a ledger change.
  In the focused/full suite, preview remains byte-for-byte equivalent to prepare's baseline
  manifest. Replacing only that transport file's digest in the local mock changes both the manifest
  entry and `baseline_hash`; the real transport file digest was unchanged.
- Runtime-core evidence: PASS. Independent temporary records for both `before_start` and
  `after_cleanup` contain `runner_sha256`, `codex_adapter_sha256`, and
  `transport_mcp_sha256`. The three values agree between phases and respectively match the real
  repository files and baseline manifest, retaining the established runner and Codex-adapter
  bindings while adding the Team Transport binding.
- Regressions and final deterministic gate: PASS. The full `modeling_team` suite exercised the
  Round 11 budget (+2/cap-four/chain/start5) and exact dynamic-route safeguards: 76 tests passed.
  `uv run --project backend ruff check modeling_team`, v2 and v1 profile/task validation, and
  `git diff --check` passed. Existing service status was `active`, `/api/health` returned
  `{"status":"ok"}`, and frontend `/` succeeded. Real ledger/run b/run c SHA-256 values remained
  exactly `a511b0b1b9950c9f84715bf1725797699f92a2e63e73e6e89c38632b7d6e97ee`,
  `b0f8001c540c46e9fa2fd7e4e36b8896cf49d1f57bcbef235ffecbf812e85cf3`, and
  `f4b7e08ba8e821b27142b07871f945db6d118eef0659a69b3d2bd08e86bb45cb`.
- Defects and decision: no Critical or High deterministic defect was reproduced. The prior Medium
  (exhaustive current-runtime type annotations in the Protocol construction reference) remains
  documentation precision only: reproduction is inspection of optional construction annotation
  coverage; expected canonical Protocol values are still enforced by task instruction, actual
  behavior is covered by the passing suite, and its evidence is Round 11. It does not block start3.
  Real producer collaboration, Batch/Shape/validation/query evidence, cleanup, independent live
  Phase A/B, and live publisher remain unexecuted; no authorized start was consumed. The main agent
  may proceed to the separately authorized real start3, followed by independent live acceptance.

### Round 13 — 2026-07-31 independent run-d source-routing and start4 final gate — PASS

- Stable baseline: uncommitted development-ready worktree. This round used only in-process task
  construction, mocked digest values, and a temporary staging/evidence root. It did not start a
  producer or Agent, create platform resources, alter implementation, or write the real ledger.
- V2 source-routing: PASS. Independently constructed task text for Coordinator, Modeling, and
  Protocol has the canonical sorted list of exactly that role's
  `/agent/home/sources/...` files, each exactly once, and makes their reading mandatory before
  teammate work or terminal reporting. No other role's staged path, host path, or tester-only
  staged path appeared. A temporary `_stage_sources` plus `_probe_role_visibility` produced a
  source manifest and role-probe paths/SHA-256 values exactly matching `role_sources`.
- Runtime instructions: PASS. Protocol's generated text names the exact staged Batch construction
  contract path, treats Codex `Array<unknown>` as the non-conflicting platform-general fallback,
  and assigns envelope translation solely to Protocol. Its Package additionally prohibits
  re-delegating exact items, session/lease fields, and idempotency to Modeling. Modeling's Package
  requires the platform-neutral candidate fields (classes, properties, relations, Shapes, entities,
  evidence, explicit unknowns, dependencies) and prohibits authoring the platform envelope. The
  v1 task text for both Modeling and Protocol was byte-for-byte equal to its prior compatibility
  contract.
- Frozen baseline: PASS. Preview's manifest contains the real digests for `runner`,
  `instructions:modeling`, and `instructions:protocol`; a process-local single-file digest change
  for each one independently changes its manifest entry and the baseline hash. This binds the
  run-d routing and Package instruction surfaces to the reserved baseline.
- Regression and final gate: PASS. `uv run --project backend python -m unittest discover -s
  modeling_team/tests -p 'test_*.py'` completed 78 tests successfully (the printed budget rejection
  lines are expected negative CLI assertions); Round 12 baseline binding plus Round 11 exact-route
  and budget/start-chain protections remain covered. Ruff, v2/v1 profile-task validation, and
  `git diff --check` passed. Existing service was `active`, `/api/health` returned
  `{"status":"ok"}`, and frontend `/` succeeded. Before/after SHA-256 values were unchanged for
  the real ledger, run c baseline, and run d baseline respectively:
  `2d2cfec1f09208e3d5e5e4f5fce2b7ad2a42f9e1b78d2257545f3014449384ac`,
  `844de6bb67ab8c88e66ff63acaf0e4363ac2aede49e9916e3b4cd698d80fcf18`, and
  `21fe343430630a884bc2f1387f7cfe350cae0b40656b5538d181b97f6a828286`.
- Defects and decision: no Critical or High deterministic defect was reproduced. The existing
  Medium on exhaustive Protocol construction-reference type annotations remains documentation
  precision only: inspection reproduces incomplete optional annotation coverage, while expected
  canonical Protocol behavior is enforced by the task/Package contracts and the 78-test evidence.
  It is not a start4 blocker. Real producer collaboration, Platform Batch/Shape/validation/query,
  cleanup, independent live Phase A/B, and live publisher remain unexecuted; no authorized start
  was consumed. The main agent may proceed with separately authorized real start4 and independent
  live acceptance.

### Round 14 — 2026-07-31 independent attempt4 conflict-loop, delivery-ack, terminal-order, and second-plus-two gate — PASS

- Stable baseline: uncommitted development-ready worktree. All direct verification used temporary
  ledgers, brokers, adapters, staging/evidence roots, and process-local CLI root patches. This
  round did not start a producer or Agent, create platform resources, modify implementation, or
  write the real ledger.
- Budget authorization and start chain: PASS. After a first exact `+2`, two concurrent distinct
  second authorization requests yielded exactly one winner; a third, non-2 values, duplicate IDs,
  and a forged three-event ledger all failed closed without expanding the cap. A temporary ledger
  completed start1 through start6 only via an immediately preceding retryable narrow failure plus
  matching repaired baseline; start5/start6 therefore each passed their repair chain and start7 was
  rejected at cap six. The isolated CLI accepted exactly two distinct `+2` authorizations and did
  not append invalid or third records.
- Delivery correlation and conflict loop: PASS. Delivery IDs are global and monotonic; only one
  active exact reversed reply can close an `expects_reply` request. Ordinary, unrelated, forged,
  wrong-direction, and duplicate replies did not close it. A queued Protocol feedback reply kept
  Modeling terminal completion rejected; Runner drain preserved delivery correlation and only its
  successful adapter send acknowledged the reply, after which Modeling could complete. A synthetic
  adapter failure produced no acknowledgement and kept Modeling rejected. The revisable
  candidate->conflict->revision->second-reply path completed; the unrevisable path allowed Modeling
  `blocked` (while no-request `completed` was rejected), then Protocol and Coordinator `blocked`
  in order.
- Terminal handoffs and runtime contract: PASS. Protocol rejected its terminal report after a
  Modeling result but before its delivered handoff; a successful Runner handoff acknowledgement
  enabled retry. Coordinator likewise waited for Protocol's delivered handoff. The runtime envelope
  preserves only mechanically correlated sender/recipient/kind/text/delivery/reply fields; MCP
  schemas contain no added semantic typed payload, and all three Package instructions consistently
  require acting on the exact `text` content. Full regression also covered v1/v2 three-of-three
  settlement and cleanup.
- Final deterministic gate: PASS. `uv run --project backend python -m unittest discover -s
  modeling_team/tests -p 'test_*.py'` passed 86 tests (printed budget-rejection lines are expected
  negative CLI assertions). Ruff, v2/v1 profile-task validation, and `git diff --check` passed.
  Existing service was `active`, `/api/health` returned `{"status":"ok"}`, and frontend `/`
  succeeded. Real ledger/run d/run e SHA-256 values were unchanged before/after this round:
  `c15d67ebbf0a7b6705c2e824a77d61ba3de2c362615d98ad07271c725562e443`,
  `21fe343430630a884bc2f1387f7cfe350cae0b40656b5538d181b97f6a828286`, and
  `9686ec5a0f9c6f74b0cf51bbe067c3e9f2458249d08d1c4cdecd133bf7fad4de`.
- Defects and decision: no Critical or High deterministic defect was reproduced. The existing
  Medium on exhaustive Protocol construction-reference type annotations remains documentation
  precision only: reproduction is inspection of optional annotation coverage, expected canonical
  behavior is enforced by the task/Package contracts and the 86-test evidence, and it does not
  block start5. Real producer collaboration, Platform Batch/Shape/validation/query, cleanup,
  independent live Phase A/B, and live publisher remain unexecuted; no authorized start was
  consumed. The main agent may proceed with separately authorized real start5 and independent live
  acceptance.

### Round 15 — 2026-07-31 independent live narrow-fix, foreground lifecycle, and minimal writer preflight — PASS

- Stable baseline: uncommitted development-ready worktree. Broker/foreground checks used temporary
  directories and mocked Runner construction only. The platform preflight deliberately bypassed
  Team Runner and did not reserve or mark a semantic start. Its fresh temporary scope was explicitly
  released, cancelled, key-revoked, and deleted before this round completed.
- Conflict correlation repair: PASS. A Protocol-to-Modeling conflict simultaneously
  `reply_to_delivery_id`-linked to the candidate and `expects_reply=true` was successfully
  acknowledged, thereby closing the candidate while retaining the conflict as a pending revision
  request. Modeling `completed` was then rejected until it sent a new `expects_reply` revision
  linked exactly to the conflict delivery ID; forged, wrong-link, duplicate, and terminal-handoff
  acknowledgement-before-source-result requests were rejected. The final Protocol receipt had to be
  delivered and acknowledged before Modeling could complete. The directly reproduced prior High
  (silent Modeling completion after an acknowledged conflict) is FIXED.
- Foreground lifecycle: PASS. A terminal `TERMINAL_REPORT_COMPLETE` state causes the foreground
  event loop to return without waiting for stdin, after which `main()` calls cleanup. A simulated
  `KeyboardInterrupt` invoked cleanup and returned 130. An unrelated `AssertionError` propagated
  rather than being swallowed (the narrow normal-error handler is unchanged).
- Live authenticated writer preflight: PASS. The active service reported
  `canonical_store=rdf`, `product_write_mode=rdf_primary`, and `read_mode=canonical`. Against a
  fresh Project/Ontology/Build Session/Lease and temporary project-scoped model key, one
  `create_class` Modeling Batch `dry_run` returned HTTP 200 with `attempt_status=validated` and no
  workspace movement. The lease was explicitly released (HTTP 200, `state=released`), the Build
  Session cancelled (HTTP 200), the Protocol and bootstrap-admin keys revoked, and the owned Project
  deleted (HTTP 204). A direct PostgreSQL read then found zero Round15 temporary Projects,
  Ontologies, Sessions, and Leases. No Team Runner or semantic-start ledger operation participated.
- Final gate and retained evidence: PASS. `uv run --project backend python -m unittest discover -s
  modeling_team/tests -p 'test_*.py'` passed 88 tests; printed budget-rejection lines are expected
  negative CLI assertions. Ruff, v2/v1 profile-task validation, `git diff --check`, backend health,
  and frontend health passed. Real ledger `semantic_start` count remained 5 and its SHA-256 remained
  `661e6b24687bc8d1474bcca46722109666ff31148a3f75a53b234061a5de4eff` before/after. The run-f
  non-runtime state/evidence/source snapshot digest remained
  `a069d6b207f5b49b18b8e721c61b374545622fec95f5b4d392816263eb9b9a66`; the test neither altered
  its retained evidence nor its keys, Session, or Lease state.
- Defects and decision: no Critical or High defect remains from this round. The prior Medium on
  exhaustive Protocol construction-reference type annotations remains documentation precision only
  and does not block the next authorized live attempt. Producer collaboration and its independent
  live Phase A/B acceptance remain separate, unexecuted work; this preflight consumed no semantic
  start.

### Round 16 — 2026-07-31 independent cap-8, launch contract, Latest gate, and production app-server MCP preflight — PASS

- Stable scope and non-goals: all ledger cases used `TemporaryDirectory`; the production check used
  a temporary run-like root and a fresh owned PlatformScope only. It did not call `TeamRunner.start`,
  reserve or mark a semantic start, run a business producer, read business sources, write the real
  start ledger, or alter the retained run-g evidence. The initial auth-home probe correctly failed
  closed before app-server startup because the current `CODEX_HOME` had no `auth.json`; its owned
  temporary Project/Ontology/Session/Lease was immediately deleted and API-checked. The authorized
  historical Codex auth home was then checked only for `auth.json` existence/permissions, temporarily
  set for the preflight process, and restored afterwards; no credential value was read or recorded.
- Cap-8 authorization and start budget: PASS. A temporary ledger accepted three distinct immutable
  `+2` authorizations (cap 8), recorded starts 1--8 through the required narrow-repair chain, and
  rejected start 9. It also rejected a fourth authorization, duplicate authorization ID, non-`2`
  increment, a forged four-authorization JSONL ledger, and a concurrent final-third-authorization
  race (exactly one accepted and the other rejected; the subsequent fourth was rejected).
- Frozen Protocol launch contract: PASS. `protocol_mcp_launch_spec` rendered
  `SEMANTIC_CANONICAL_STORE=rdf`, `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`, and
  `SEMANTIC_READ_MODE=canonical` only in Protocol's private `ontology_platform` MCP config.
  Coordinator/Modeling configs and the bwrap app-server command contained neither those variables
  nor an injected ambient-environment sentinel. The baseline manifest binds
  `protocol_mcp_launch.py` and the exact three-value non-secret runtime contract; changing the
  canonical-store contract changed the preview baseline hash.
- Latest and outer-answer gate: PASS. The v2 Task says a published/latest Tool with no deployment
  binding must first produce one grounded Tool-binding question, await an outer answer, and otherwise
  retain `explicit_unknown`; it contains no tester-only answer path or matching logic. Coordinator's
  task/Package instruction requires the exact outer answer once with
  `reply_to_delivery_id` set to the current Modeling question delivery ID. Team Transport accepted
  only the active reversed reply and rejected forged and duplicate reply bindings.
- Production Protocol-only MCP preflight: PASS. Using the production `CodexRuntimeAdapter` actual
  source staging, `_write_config`, Protocol private config, bwrap namespace, Codex app-server and
  its live `ontology_platform` MCP server, one fresh temporary Project/Ontology/model key/Build
  Session/Lease was created. The app-server's native `mcpServer/tool/call` invoked exactly one
  `submit_modeling_batch` containing one minimal `create_class` `dry_run`; the independent platform
  read returned one batch with `attempt_status=validated`. This was not a systemd environment or a
  side-process substitute. The Lease was explicitly released, Session cancelled, Protocol key
  revoked, Project deleted (HTTP 204 and subsequent API 404), bootstrap-admin key revoked, and a
  direct PostgreSQL check found zero temporary Projects, Ontologies, Sessions, and Leases. No secret,
  IDs, request body, or retained run evidence was retained in this test record.
- Final checks: PASS for requirement scope. `uv run --project backend python -m unittest discover -s
  modeling_team/tests -p 'test_*.py'` passed 89 tests (the printed budget-rejection lines are expected
  negative CLI assertions). `uv run ruff check ../modeling_team`, v1 and v2 profile/task validation,
  `git diff --check`, active `ontology-platform.service`, backend health, and frontend health passed.
  Full backend Ruff additionally reports two pre-existing, unchanged F401 findings outside this
  requirement (`app/services/semantic_build_overview.py:6` and
  `app/services/semantic_vector_projection.py:15`); this Low out-of-scope hygiene finding was not
  modified by the round and does not alter the R2.3-002 conclusion. No restart was needed because
  this round changed no runtime code or configuration.
- Retained evidence and decision: PASS. Before/after this round the real ledger stayed at 6 semantic
  starts and 2 authorizations with SHA-256
  `6b7be7815cbf31125041d5ef5e9bba0069d9f94e5d8f47e556faf80854ef15e3`; the run-g non-runtime
  state/evidence/source snapshot digest stayed
  `ed06466f1a3f452ca3b58bfd0db4464398ac3acdce4882e5319a320ede2a828f`. No Critical, High, or
  Medium R2.3-002 defect was found. Real business producer collaboration and independent live Phase
  A/B acceptance remain unexecuted and require their separate authorization; this preflight consumed
  no semantic start.

### Round 17 — 2026-07-31 independent attempt7 and Protocol mechanics-runtime retest — FAIL

- Stable scope: no business producer, repair authorization, StartLedger write, or retained-run mutation
  was performed. The real ledger stayed at 7 semantic starts and 3 authorizations with SHA-256
  `6e36514dd542f7a56c78c05780ef4ea68291cdcc760708842485b16bfc836ca6`; attempt7 (`r23002-real-20260731h`)
  non-runtime snapshot digest stayed `6ebfec1724f3d1eb2a1caa1c6da154748da0df39cf8856310870def9a3f02b7c`.
- Attempt7 evidence: PASS. Its sole terminal-failure record is `platform-contract` with
  `complete_modeling_quality_result=false`; state is `CLEANED` with owned scope
  `deleted-empty`. The three answers are exactly reverse-linked to their grounded questions:
  `delivery-5 -> delivery-1` (Latest published C), `delivery-7 -> delivery-6` (successor
  continuity), and `delivery-9 -> delivery-8` (business owner cannot confirm absent-score behavior).
  Candidate `delivery-10` resolves B's Tool binding to C v2, preserves the output-field successor
  relation and an ExplicitUnknown with no invented behavior, and requires the separate invalid
  draft-binding Shape instance as dry-run only. All attempt7 MCP elicitations are Team Transport;
  no ontology-platform MCP mutation was attempted.
- Mechanics helper and staging: PASS. The new `modeling_team.protocol_mechanics.protocol_mechanics_contract`
  is value/field equivalent for the same run ID to the retained R2.2 L3
  `run_l3.py` helper; the old helper has no local diff. Its serialized content contains no business,
  tester-only, or secret material. A v2 Protocol creates only run-owned
  `runtime-assets/protocol/mechanics-contract.json` (parents `0700`, file `0444`) outside Agent home;
  Coordinator, Modeling, and v1 create/mount none. The v2 baseline binds the helper and its digest
  changes when the helper digest is drifted.
- Namespace mount: PASS, but consumer path fails. A production adapter-generated bwrap command exposes
  the mechanics file read-only only at `/opt/mechanics-contract.json`; Agent-home aliases, host asset
  path, and repository host alias are absent. In-namespace `chmod` and append attempts fail, and the
  host asset digest is unchanged.
- **High defect — Protocol Thread cannot read the required mounted mechanics contract.** Reproduction:
  start a fresh v2 Protocol-only production `CodexRuntimeAdapter` roster with the live bwrap/app-server
  path and mount the run-owned asset; request the preflight-only Thread to execute exactly
  `cat /opt/mechanics-contract.json` before any platform operation. Expected: the controlled dynamic
  read accepts this exact read so the same Thread can then make the one allowed MCP dry-run. Actual:
  `CodexRuntimeAdapter._dynamic_read_path` accepts only `/skills/` and `/agent/home/sources/`, and has
  no `/opt/mechanics-contract.json` mapping; `_dynamic_tool_result` therefore returns
  `dynamic exec path is not permitted` (classified `exec-policy`). The live app-server/bwrap process
  was started with the mounted asset, but this hard adapter policy makes the required Thread read
  unreachable. Evidence: `modeling_team/runtimes/codex.py` dynamic read allowlist and the production
  namespace mount reproduction above. The required same-Thread ontology MCP `create_class` dry-run
  was deliberately **not executed** after this High failure; substituting a direct call would not test
  the required sequence.
- Temporary-resource cleanup: the interrupted no-write preflight scope was deleted and its uniquely
  identified temporary bootstrap-admin key revoked; direct DB checks found zero matching temporary
  Projects and Sessions and no active interrupted admin key. No platform mutation beyond temporary
  scope lifecycle occurred.
- Final checks: `uv run --project backend python -m unittest discover -s modeling_team/tests -p
  'test_*.py'` passed 90 tests; team Ruff, v1/v2 validation, `git diff --check`, service status, and
  backend/frontend health passed. No restart was needed. Overall result is **FAIL** because the High
  runtime-read defect blocks the required production preflight. Have the requirement developer make
  the exact Protocol-only `/opt/mechanics-contract.json` read available through the controlled dynamic
  read path, add a live/adaptor regression, then rerun this same test-plan Round after the fix.

### Round 18 — 2026-07-31 independent real Thread mechanics-read retest — FAIL

- Stable scope: no business producer, repair authorization, StartLedger write, or retained-run mutation
  occurred. Before/after, the real ledger remained 7 starts and 3 authorizations with SHA-256
  `6e36514dd542f7a56c78c05780ef4ea68291cdcc760708842485b16bfc836ca6`; attempt7 non-runtime
  snapshot digest remained `6ebfec1724f3d1eb2a1caa1c6da154748da0df39cf8856310870def9a3f02b7c`.
- Runtime-reader repair and negative matrix: PASS locally. The verified descriptor reader returns the
  exact current preflight run-ID contract bytes and rejects wrong role, v1/null identity, unregistered
  Agent, wrong run root/raw/virtual path, symlink file/parent, nonregular target, wrong mode, and
  tampered bytes. The pre-existing skills/source virtual-path and host-probe denial matrix remains
  unchanged. Production bwrap still exposes only `/opt/mechanics-contract.json`, rejects Agent-home
  and host aliases, rejects chmod/append, and preserves the host asset digest.
- **High defect — actual Protocol Thread does not issue the required `/opt` read.** Two independent
  fresh v2 Protocol-only production adapter/bwrap/app-server preflights used the exact mandatory
  `exec` instruction `cat /opt/mechanics-contract.json`, prohibited source, Team Transport, and MCP
  use, and waited for terminal Thread state. Expected: one accepted `item/tool/call`/dynamic-tool
  callback proving the Thread read the exact current run-ID contract, followed by the one same-Thread
  private ontology MCP `create_class` dry-run. Actual: both Threads became `idle` with zero
  `dynamic-tool-calls.jsonl` records; no `exec` call was emitted. The adapter-side descriptor function
  can read the correct bytes, but that is not Thread evidence and cannot substitute for the required
  App Server tool invocation. Therefore no ontology MCP call was made after the unmet precondition;
  `validated` is **not established** for this Round.
- Cleanup and final checks: both temporary no-write scopes were deleted; DB found zero matching
  Projects/Sessions and zero active temporary Protocol keys. `unittest discover` passed 91 tests,
  team Ruff, v1/v2 validation, `git diff --check`, active service, backend health, and frontend health
  passed. No restart was needed. Overall **FAIL**: have the requirement developer expose/force the
  intended preflight-only Thread tool-call path (with an integration regression that observes the
  callback), then rerun the same test plan before any business producer attempt.

### Round 19 — 2026-07-31 independent deterministic Protocol mechanics and private-MCP preflight — PASS

- Stable scope: this round used one fresh, temporary production `CodexRuntimeAdapter`, one registered
  schema-v2 Protocol Agent, one private Protocol config/scope/key, and one real Codex app-server
  Thread. It did not start a model turn, a business producer, a repair authorization, a StartLedger
  write, or mutate retained attempt evidence. This is intentional: the synchronized requirement,
  design, and test-plan deterministic gate expressly evaluates the adapter callback rather than
  whether a model elects to issue `exec`.
- A — namespace and asset isolation: PASS. The actual production bwrap command made the exact
  current-run canonical mechanics bytes readable only at `/opt/mechanics-contract.json`; Protocol
  Agent-home aliases, the runtime-asset host path, the repository host alias, and alternate aliases
  were absent. In-namespace `chmod` and append attempts failed and the host asset SHA-256 was stable.
  The roster had exactly the one registered v2 Protocol identity; no Coordinator/Modeling asset or
  mount participated.
- B — controlled callback and fail-closed matrix: PASS. On that same live app-server Protocol Agent,
  `_dynamic_tool_result` for exact `exec` `cat /opt/mechanics-contract.json` returned the canonical
  bytes for the current run ID exactly. This is explicitly **callback white-box evidence, not model
  behavior**. The focused regression
  `CodexIsolationTests.test_protocol_mechanics_dynamic_read_fails_closed_for_identity_path_and_file_drift`
  passed: wrong role, v1/null identity, unregistered Agent, wrong virtual/raw path, wrong run root,
  symlink file/parent, nonregular target, mode drift, and byte tampering all fail closed. Existing
  skills/source reader and host-probe denials remain covered by the 91-test suite.
- C — same app-server private ontology MCP: PASS. Without creating a second process or replacing the
  callback route, the same Protocol Agent's app-server `_rpc` `mcpServer/tool/call` invoked its private
  `ontology_platform` server once for one minimal `create_class` `dry_run`. Independent Platform API
  readback found exactly one Modeling Batch and `attempt_status=validated`.
- Cleanup: PASS. The Lease was released, Build Session cancelled, Protocol key revoked, and owned
  Project deleted (HTTP 204 followed by GET 404); the temporary bootstrap-admin key was also revoked.
  Direct PostgreSQL verification found zero matching temporary Projects, Ontologies, Sessions, Leases,
  and active Protocol keys.
- Final regression and retained evidence: PASS. Focused negative test passed; `uv run --project
  backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'` passed 91 tests (the four
  budget-authorization rejection lines are expected negative assertions); team Ruff, v1/v2
  profile-task validation, `git diff --check`, active `ontology-platform.service`, backend health,
  and frontend health all passed. No restart was needed because this round changed no runtime code or
  configuration. The real ledger remains 7 semantic starts and 3 authorizations with SHA-256
  `6e36514dd542f7a56c78c05780ef4ea68291cdcc760708842485b16bfc836ca6`; attempt7
  (`r23002-real-20260731h`) non-runtime snapshot digest remains
  `6ebfec1724f3d1eb2a1caa1c6da154748da0df39cf8856310870def9a3f02b7c`.
- Defects and decision: no Critical, High, or Medium defect was found in this deterministic gate.
  Round 17/18's model-turn observation remains historical evidence only and is not a failure of this
  expressly non-model-behavior acceptance gate. Overall result is **PASS**; no developer repair or
  retest is required for this scope.

### Round 20 — 2026-07-31 independent Attempt8 Session/checkpoint narrow-repair preflight — FAIL

- Stable scope: no model turn, business producer, semantic-start ledger operation, budget
  authorization, retained-run mutation, or business source delivery occurred. The real ledger remains
  at 8 semantic starts and 3 authorizations (SHA-256
  `7a936efd6cad6f5730341908e714dd301b169c02e6bf51d8c9a53b5e7b5c3149`); Attempt8
  `r23002-real-20260731i` stays `CLEANED`, `deleted-empty`, and its non-runtime snapshot digest is
  `de9bbc5200ffc04121de71e9717a17f72bff9f888f215c4f36fafbd24c055023`.
- Tool/config/mechanics boundary: PASS in isolation. The exact v2 Task surface contains
  `save_build_checkpoint` and equals the repository allowlist; schema-v1/default remains unchanged
  with no v2 Protocol tools. A fresh temporary production `CodexRuntimeAdapter`, one registered v2
  Protocol Agent, private config/key/scope, bwrap app-server, and native private
  `ontology_platform` MCP were used. The v2 mechanics asset remains Protocol-only and no model turn
  was started.
- A — Attempt8 malformed-create reproduction: PASS. On the real app-server MCP, a
  `create_build_session` request with Attempt8-style nested `initial_checkpoint.run_id` and custom
  workspace data returned `error_code=forbidden_scope` (`MCP resource owner cannot be resolved`). A
  direct PostgreSQL query immediately found zero Sessions for that client ID.
- B — positive formal lifecycle: PASS as a platform capability. A fresh client session created with
  `initial_checkpoint=null` returned Build Session revision 1. The exact initial checkpoint
  `<run_id>-initial` (`modeling`, `schema_and_instance_modeling`,
  `validation_and_reasoning`, scoped ontology, `blockers=[]`) used that revision and returned
  Session revision 2; Lease acquisition used revision 2. The same app-server submitted exactly one
  minimal `create_class` dry-run and received flat `attempt_status=validated`. A fresh
  `get_build_session.session.revision` remained 2 and was used for the exact final checkpoint
  `<run_id>-final` (`handoff`, `semantic_acceptance_complete`, `delivery_handoff`, scoped ontology,
  `blockers=[]`), which returned revision 3. Completion with old revision 2 correctly returned
  `session_revision_conflict`; completion with final revision 3, explicit `session_id`,
  `client_request_id`, nonempty summary, and `unresolved_items=[]` returned `completed` revision 4,
  released the Lease, and a same-app-server reread returned that exact terminal summary/unresolved
  state. The reread checkpoint chain contains the distinct final sequence 2 and initial sequence 1
  (newest-first response order).
- Cleanup: PASS. Every uniquely named temporary Round20 scope (including parser-diagnostic runs) had
  its runtime stopped, Protocol key and bootstrap key revoked, Project deleted (HTTP 204 then GET
  404), and direct PostgreSQL verification found zero matching Projects, Ontologies, Sessions,
  Leases, or active Protocol keys.
- **High defect — final checkpoint revision source is ambiguous and can consume the exhausted
  producer budget.** Expected: the frozen Protocol-visible mechanics/prompt must bind final
  `expected_revision` unambiguously to the latest **Build Session** receipt, i.e. the Session
  revision returned by an explicit `get_build_session` reread after the preceding lifecycle work;
  a Modeling Batch attempt/workspace/graph receipt is not interchangeable. Actual:
  `modeling_team/protocol_mechanics.py` declares
  `final_checkpoint.fields.expected_revision = "latest_platform_receipt.revision"`, while the
  production proof above requires `get_build_session.session.revision`; the focused regression
  asserts the ambiguous string. Batch dry-run responses contain different receipt shapes and
  workspace revisions, so a Protocol model has no fail-closed canonical source to select. This is a
  High producer-budget risk: Attempt8 is the eighth/final authorized semantic start, and a guessed
  request must not be allowed to burn a newly authorized producer attempt.
- **High defect — completion/checkpoint mechanics are not an exact non-invented request contract.**
  Expected: Protocol-visible mechanics and first-turn prompt must bind `session_id` to the create
  receipt and enumerate the mandatory complete request fields: final Session revision,
  deterministic `client_request_id`, nonempty mechanical `summary`, and
  `unresolved_items=[]`; checkpoint calls must likewise make their `session_id`/receipt binding
  explicit. Actual: the final helper only lists the completion tool, final revision reference, and
  reread; it omits `session_id`, `client_request_id`, summary, and unresolved-items fields.
  `runner.py` and the frozen public protocol provide only high-level “complete/re-read” wording.
  The real MCP succeeds when those values are supplied manually, but the model-visible contract
  leaves it to the model to invent them. This is also High producer-budget risk rather than a
  documentation-only issue.
- Regression and resident runtime: focused `test_r23002`, `test_codex_isolation`, and
  `test_platform_scope` passed 66 tests; full `modeling_team` discovery passed 91 tests (the four
  budget-authorization rejection lines are expected negative assertions); team Ruff, v1/v2
  validation, `git diff --check`, active service, backend health, and frontend health all passed.
  No restart was needed because this round changed no runtime code/configuration.
- Decision: overall **FAIL** despite the successful temporary platform lifecycle. Have the
  requirement developer make the Protocol-visible helper/prompt an exact, fail-closed lifecycle
  contract: use an explicitly named latest Build Session receipt revision for final checkpoint, and
  bind all checkpoint/complete identifiers and mandatory completion fields without model invention;
  add focused assertions for those bindings. Then rerun this same test plan before requesting or
  consuming any new producer authorization.

### Round 21 — 2026-07-31 independent checkpoint-contract repair retest — PASS

- Scope and retained evidence: no model turn, business producer, semantic-start ledger operation,
  budget authorization, retained-run mutation, or business-source delivery occurred. The real ledger
  remains at 8 semantic starts and 3 authorizations (SHA-256
  `7a936efd6cad6f5730341908e714dd301b169c02e6bf51d8c9a53b5e7b5c3149`); Attempt8
  `r23002-real-20260731i` remains `CLEANED`, `deleted-empty`, and its non-runtime snapshot digest
  remains `de9bbc5200ffc04121de71e9717a17f72bff9f888f215c4f36fafbd24c055023`.
- Contract-repair inspection: PASS. The Protocol-only mechanics no longer uses
  `latest_platform_receipt`. It requires `get_build_session` after Batch application, validation,
  reasoning, and governed query; the final checkpoint binds its `session_id` to the create receipt
  and `expected_revision` only to `get_build_session_receipt.session.revision`. Initial checkpoint,
  Lease, final checkpoint, completion, and completed reread each contain the exact receipt-bound
  identifiers/revisions. Completion explicitly supplies deterministic `client_request_id`,
  nonempty `summary`, and `unresolved_items=[]`. The v2 first-turn task text requires this pre-final
  reread and the exact contract bindings; schema-v1/default has no v2 Protocol tools.
- Fresh production Protocol-only lifecycle: PASS. A temporary private production
  `CodexRuntimeAdapter` scope with exactly one registered v2 Protocol Agent and native private MCP
  rejected a nested-run-ID malformed create with `forbidden_scope` and created zero Sessions. The
  positive no-model chain created revision 1, saved the exact initial checkpoint to revision 2,
  acquired its Lease using revision 2, and submitted one minimal `create_class` dry-run with flat
  `attempt_status=validated`. The same app-server explicitly reread Build Session revision 2 before
  the final checkpoint; that exact value produced final revision 3. Completion from stale revision 2
  correctly returned `session_revision_conflict`; exact completion from final revision 3 returned
  revision 4 and `completed`. A same-app-server reread confirmed the terminal status, exact summary,
  empty unresolved items, released Lease, and distinct final/initial checkpoints (sequences 2/1).
- Cleanup: PASS. Runtime and broker were stopped; Protocol and bootstrap keys were revoked; owned
  Project deletion returned HTTP 204 and subsequent GET returned 404. Direct PostgreSQL verification
  found zero matching temporary Projects, Ontologies, Sessions, Leases, and active Protocol keys.
- Regression and resident runtime: PASS. Focused `test_r23002`, `test_codex_isolation`, and
  `test_platform_scope` passed 66 tests; full `modeling_team` discovery passed 91 tests (the four
  budget-authorization rejection lines are expected negative assertions). Team Ruff, v1/v2
  profile-task validation, `git diff --check`, active `ontology-platform.service`, backend health,
  and frontend health all passed. No restart was needed because this round changed no runtime code or
  configuration.
- Defects and decision: both Round 20 High defects are **FIXED**. No Critical, High, or Medium
  defect was found in this narrow repair retest. Overall result is **PASS** for the exact Session /
  checkpoint contract and its no-model production preflight. This does not authorize or replace a
  future real business-producer/model attempt; a new explicit producer authorization remains required
  before such an attempt.

### Round 22 — 2026-07-31 independent fourth `+2` / cap-ten ledger delta retest — PASS

- Scope and stable baseline: this was an independent no-model, no-producer ledger-contract retest.
  No live ledger mutation, budget authorization, producer reservation/start, repair authorization,
  Platform resource operation, or retained-run mutation occurred. The reviewed implementation delta
  is confined to the fixed `_MAX_BUDGET_AUTHORIZATIONS = 4`, matching four exact `+2` extensions,
  its four-extension docstring, and focused ledger/CLI regression coverage; it does not expand the
  Task tool surface, Runner producer path, backend, or frontend.
- C20 — authorization cap, malformed/forged records, and concurrency: PASS. In a temporary,
  lock-protected ledger, three distinct exact `+2` authorizations produced cap 8 and rejected the
  ninth reservation. A unique fourth authorization produced cap 10. A fifth request, duplicate ID,
  duplicate reference, malformed `1`/boolean values, and a forged ledger containing five
  authorization events all failed closed with byte-identical ledger content after rejection. Five
  concurrent distinct authorization requests admitted exactly four and rejected one; the resulting
  cap was exactly 10.
- C21 — later-start chain: PASS. A temporary chain rejected attempt nine without the fourth
  authorization, after fourth authorization but without an Attempt8 repair, with the wrong baseline,
  and with expired or future freeze times, each without appending a record. It admitted attempt nine
  only after the immediate Attempt8 `runtime/infrastructure` failure with
  `complete_modeling_quality_result=false`, a repair authorization appended after that failure, the
  exact new baseline, and a valid freeze. Attempt ten likewise rejected before an immediate Attempt9
  repair; after its exact repair, concurrent reservations produced exactly one active reservation and
  one rejection.
- Regression and runtime: PASS. Focused `test_r23002`, `test_codex_isolation`, and
  `test_platform_scope` passed 66 tests; full `modeling_team` discovery passed 91 tests (the four
  printed budget-authorization errors are expected negative CLI assertions). Team Ruff, schema-v1
  and schema-v2 profile/task validation, and `git diff --check` passed. The resident
  `ontology-platform.service` was active; backend `/api/health` and frontend `/` were healthy. No
  restart was needed because this round changed no runtime code or configuration.
- Live-ledger preservation: PASS. Read-only before/after checks both reported 40 records, 8
  `semantic_start` events, and 3 `budget_authorization` events, with unchanged SHA-256
  `7a936efd6cad6f5730341908e714dd301b169c02e6bf51d8c9a53b5e7b5c3149`.
- Defects and decision: no Critical, High, or Medium defect was found for C20/C21. Overall result
  is **PASS** for the fourth-authorization/cap-ten implementation delta. Residual operational risk:
  the real ledger intentionally still has only three authorization records, so no real Attempt9 may
  begin until the authorized owner appends the distinct fourth `+2` event and freezes the next
  baseline; this tester round neither performs nor substitutes for either action.

### Round 23 — 2026-07-31 independent presemantic auth/release/rebind repair retest — PASS

- Scope and preservation: no live ledger mutation, real host-auth creation/copy, budget or repair
  authorization, producer reservation/start, model turn, Platform write, or retained-run mutation
  occurred. All behavioral tests used temporary auth directories, mocked CLI next boundaries, and
  temporary lock-protected ledgers.
- C23a — host authentication preflight: PASS. A temporary ordinary non-symlink `auth.json` was
  accepted while a read guard proved the preflight did not open its contents or emit output; missing,
  directory, and symlink forms rejected without an auth-content read. CLI missing-auth handling
  returned before bootstrap, `TeamRunner`, `PlatformScope`, run-directory, and ledger work. A valid
  temporary auth reached the intended mocked `prepare` boundary without Runtime start. Removing that
  file after a successful preflight caused `_write_config` to reject before producing private
  `auth.json` or `config.toml`, proving the staging-side defensive check.
- C23 — release/rebind: PASS. First release appended once and retained its first reason; duplicate
  release returned the idempotent no-op result, and later mark rejected with unchanged semantic-start
  count. A release-versus-mark race had exactly one winner under the file lock and never produced
  both terminal events. A released reservation consumed the prior repair without consuming a start;
  an old delayed mark after a fresh rebind/new reservation rejected. Fresh rebind chains succeeded
  only through new run IDs and exact baselines, with the ordinary stale-freeze gate still preventing
  append. Unused, active/no-release, started, same-baseline, multiple/foreign, misordered, and
  concurrent rebind cases failed closed. A temporary ledger with three historical release records
  for the one consumed reservation was accepted as the same terminal released state.
- Regression and resident runtime: PASS. Focused `test_r23002`, `test_codex_isolation`, and
  `test_platform_scope` passed 69 tests; full `modeling_team` discovery passed 94 tests (printed
  budget and missing-auth errors are expected negative assertions). Team Ruff, schema-v1 and
  schema-v2 profile/task validation, and `git diff --check` passed. The resident
  `ontology-platform.service`, backend `/api/health`, and frontend `/` were healthy. No restart was
  needed because this round changed no runtime code or configuration.
- Live evidence: PASS. Read-only before/after ledger checks remained 46 records, 8
  `semantic_start` events, and 4 `budget_authorization` events with unchanged SHA-256
  `9734451eb6ec86e3eb17f12d324bfe4a32c30592fc7fd69b13fd6310f8e4337d`. Run
  `r23002-real-20260731j` has no semantic start and has its three historical release entries.
  Its recorded Project/Ontology, Project-linked Build Session/Lease, and Project key all had direct
  PostgreSQL count zero; its retained cleanup state records credential revocation and `CLEANED`.
- Defects and decision: no Critical, High, or Medium defect was found for C23/C23a. Overall result
  is **PASS** for this presemantic auth/release/rebind repair. Residual risk is intentionally
  bounded: the local host may remain logged out, so this proves the deterministic host-file gate and
  its mocked next boundary, not a new authenticated Producer/model run; no such run is authorized by
  this round.

### Round 24 — 2026-07-31 independent no-model outer-control preflight — PASS

- Scope and preservation: no auth, repair, reservation, semantic start, model turn, Producer,
  Platform scope operation, live-ledger write, or retained-run mutation occurred. The foreground
  path was exercised only with temporary `StringIO`, a controlled fake adapter, and a temporary
  `TeamRunner` run root; answer selection was a tester-side deterministic control gate and was not
  introduced into Runner, Task, Profile, Package, Skill, or Agent-visible sources.
- C12a — exact foreground envelope: PASS. For each of the three frozen tester-only answers, canonical
  `json.dumps({"action":"user","text":<verbatim>}) + "\\n"` passed the actual
  `_foreground_event_loop` JSON decode and actual `TeamRunner.receive_outer`. Each created exactly
  one `RuntimeDelivery(sender_id="user/outer", recipient_id="coordinator",
  kind="outer-user")` with byte-identical text and exactly one `outer-user` evidence entry. The
  prior `{"type":"user_message",...}` form reproducibly raised `unknown outer Runner action`
  with zero delivery and zero outer-user evidence.
- C12a — tester-side release gate: PASS. A controlled deterministic gate accepted only a current
  Modeling-to-Coordinator grounded question with an exact delivery ID/text that mapped to one frozen
  answer ID, zero/expected prior releases, and a Coordinator prompt. It generated one canonical
  JSONL line, sent no second line for a repeated pending prompt, and required an exact
  Coordinator-to-Modeling `outer-forward` of the same answer with the original question
  `reply_to_delivery_id` before releasing the next answer. Unmatched/ambiguous question, unexpected
  prior answer, wrong order, duplicate answer, missing forward, and mismatched forward all stopped
  before an additional release.
- Attempt9 retained evidence: PASS. `r23002-real-20260731k` records Modeling's current grounded
  Tool-binding question as `delivery-3` and has no `outer-user` evidence before cleanup. The
  delivery record preserves the failed legacy `type=user_message` envelope and its
  `unknown outer Runner action`; the live ledger classifies the run `collaboration/routing` with
  `complete_modeling_quality_result=false`. State is `CLEANED`/`deleted-empty`; direct PostgreSQL
  counts for its recorded Project, Ontology, project-linked Session, Lease, and Project key are all
  zero.
- Regression and resident runtime: PASS. Focused `test_r23002`, `test_codex_isolation`, and
  `test_platform_scope` passed 69 tests; full `modeling_team` discovery passed 94 tests (printed
  budget and missing-auth errors are expected negative assertions). Team Ruff, schema-v1 and
  schema-v2 profile/task validation, and `git diff --check` passed. The resident
  `ontology-platform.service`, backend `/api/health`, and frontend `/` were healthy. No restart was
  needed because this round changed no runtime code or configuration.
- Live-ledger preservation: PASS. Read-only before/after checks stayed at 50 records, 9
  `semantic_start` events, and 4 `budget_authorization` events with SHA-256
  `89298ec73db5d2dd1d5b1e6d7f36f7be87f6f9bce3602c6e4380c31ac5e65a0b`.
- Defects and decision: no Critical, High, or Medium defect was found for C12a. Overall result is
  **PASS** for the no-model outer-control preflight. Residual risk remains explicit: the gate proves
  deterministic controller mechanics and the Runner boundary, but not a new semantic Producer
  outcome; any future answer release still needs the live per-run grounded-question and correlated
  forward evidence before a separately authorized Producer attempt can continue.

### Round 25 — planned independent Protocol reasoner preflight

- Scope: no model turn, producer reservation, semantic start, live-ledger write, or mutation of
  `r23002-real-20260731l`. Use a fresh temporary PlatformScope and the production schema-v2 Protocol
  Adapter/config/namespace/app-server/MCP path.
- Launch-contract checks: require the private Protocol MCP config to contain exactly
  `SEMANTIC_REASONER_COMMAND=/backend/scripts/dev_owl_reasoner.py` and
  `PATH=/backend/.venv/bin:/usr/bin:/bin`; require the namespace to bind only the exact host
  `backend/scripts/dev_owl_reasoner.py` file read-only at that path. Prove the fixed PATH resolves
  `python3` to the mounted backend venv and imports `rdflib`; reject a
  missing/non-file/symlink/drifted script. Prove no scripts-directory, repository, `.env`, or
  ambient-environment inheritance, and prove Coordinator, Modeling, schema-v1, and the Codex
  app-server general environment receive neither reasoner variable nor fixed PATH.
- Baseline checks: require the manifest to bind the exact reasoner path, fixed PATH contract, and
  host script SHA-256; changing any of them changes the baseline hash without hashing ambient
  environment.
- Real-runtime check: through the same native app-server MCP RPC path used by production Protocol,
  create the minimum temporary modeled state, execute `run_semantic_reasoning`, and require
  `status=succeeded` and `consistent=true`. A direct script invocation, mocked MCP, or resident
  backend health alone does not satisfy this case.
- Cleanup and preservation: close/release temporary Session/Lease state, revoke the key, delete the
  exactly owned temporary Project/Ontology, stop Runtime processes, and prove zero residual rows.
  Compare the live ledger byte-for-byte and verify attempt-ten state/evidence digests are unchanged.
- Regression gate: focused reasoner/Adapter/baseline tests, full `modeling_team` suite, Ruff, v1/v2
  validation, `git diff --check`, systemd service status, backend health, and frontend health.
- Decision: PASS only with all checks above. Any failure remains presemantic and blocks requesting
  or consuming another producer authorization.

### Round 25 — 2026-08-01 independent Protocol reasoner preflight — PASS

- Scope and preservation: the final acceptance execution used one fresh temporary PlatformScope,
  Protocol key, production `CodexRuntimeAdapter`, schema-v2 Protocol private config, real bwrap,
  real Codex app-server, and its native `mcpServer/tool/call` RPC. It started no model turn and did
  not create a Producer reservation or `semantic_start`. Earlier parameter/empty-graph calibration
  probes were each independently cleaned before the final integrated execution; none wrote the
  ledger or retained Attempt evidence. The final temporary run was
  `r23002-round25-00c87234717c`.
- Launch isolation and baseline: PASS. The Protocol private MCP block contains exactly
  `SEMANTIC_REASONER_COMMAND=/backend/scripts/dev_owl_reasoner.py` and
  `PATH=/backend/.venv/bin:/usr/bin:/bin`; the actual host script SHA-256 is
  `af5cc22bf8c0f17596d94d17da37247908c409b0c435d88a2383cb099a8c5a43`.
  Focused automated coverage passed for v2-only config, no ambient sentinels, exact single-file
  read-only bind, missing/directory/symlink rejection, role/v1 isolation, and script/contract
  baseline drift without ambient-environment hashing. Direct namespace inspection found neither a
  repository bind, scripts-directory bind, nor `/backend/.env`; append to the mounted script
  failed. The app-server general environment contained neither fixed reasoner variable nor fixed
  PATH. Its ordinary PATH therefore selected `/usr/bin/python3` as intended; under the configured
  MCP-child PATH, `python3` resolved to `/backend/.venv/bin/python3`, had
  `sys.prefix=/backend/.venv`, and imported `rdflib 7.6.0`.
- Native MCP reasoning: PASS. Through the registered Protocol app-server RPC, the final scope read
  its workspace, created one Build Session and Lease, submitted the same two-item temporary
  class/entity Batch as `dry_run=validated` and `apply_atomic=applied` with mode-specific
  idempotency keys, then invoked `run_semantic_reasoning`. The actual result was
  `status=succeeded`, `consistent=true`; no mock, direct reasoner invocation, resident-backend
  bypass, or model turn supplied this result.
- Cleanup: PASS. The same protocol path released the Lease and cancelled the Session; Runtime and
  broker stopped. The exact temporary Protocol key and bootstrap key were revoked, the exact owned
  Project deletion returned 204, and direct PostgreSQL counts after deletion were all zero for
  Project, Ontology, Build Session, Lease, and Project key.
- Live evidence preservation: PASS. Before/after the ledger was byte-identical at SHA-256
  `914853953fc38fa0ebbf364f2aefffa16fb4edbb885ca473440c954be7f21d9b`, 54 records, 10
  semantic starts, and 4 budget authorizations. Attempt
  `r23002-real-20260731l` was not opened or mutated; its `state.json` SHA-256 stayed
  `3c7b666b110b2e5153cd8aa015564e63e1a7a63f223cb2980b8472b4e31fee14` and its non-runtime
  evidence-tree digest stayed `4d7e78beafdd94c21552962f60be1ab25f2e998c3f49132a5e40fc06282c467b`.
- Regression and resident runtime: PASS. Focused `test_r23002` plus `test_codex_isolation` passed
  63 tests; full `modeling_team` discovery passed 95 tests (printed budget/missing-auth lines are
  expected negative assertions). Team Ruff, schema-v1 `base-capability-smoke` and schema-v2
  `new-scope-business-slice` validation, and `git diff --check` passed. The resident service was
  active; backend `/api/health` returned `status=ok` and frontend `/` returned 200. No restart was
  needed because this tester round changed no runtime code or configuration.
- Defects and decision: no Critical, High, or Medium product defect was found. Overall result is
  **PASS** for the narrow Protocol reasoner repair and its required no-model production preflight.
  This round does not authorize, reserve, or consume any new Producer semantic-modeling attempt.

### Round 26 — planned continuing-authorization ledger preflight

- Contract: record the 2026-08-01 user instruction once as continuing authority through R2.3-002
  completion. Permit the Delivery Agent to append only exact `+2` tranches with unique IDs and
  sequence-bound references; do not create an infinite cap or require another user interaction.
- Preservation: all existing four authorization records and ten starts remain valid and immutable.
  Forged amounts, duplicate IDs/references, malformed historical records, concurrent duplicates,
  or ordinary Runner paths attempting authorization fail closed.
- Exhaustion ordering: `authorize_budget` succeeds only while holding the ledger lock and only when
  semantic-start count equals the currently replayed cap. Unconsumed-cap authorization is rejected;
  at cap 10 two concurrent requests with different IDs/references yield exactly one success. Ordered
  replay accepts the historical tranches after starts 2/4/6/8 and rejects two consecutive
  well-formed authorization records when no intervening starts consume the first tranche.
- Reservation gates: a fifth tranche raises the cap from 10 to 12, but start 11 still requires the
  immediately preceding retryable false-complete failure, Round 25 repair evidence, exact new
  baseline, fresh run ID, single active reservation, and 20-minute freeze gate. Modeling-quality or
  incomplete repair history remains blocked.
- Lifecycle: continuing authority stops being usable after R2.3-002 completion, explicit user
  withdrawal, or requirement termination; the local implementation need not add a productized
  workflow state machine, but Delivery must not append further tranches after terminal closure.
- Regression: focused ledger/CLI/Runner tests, full `modeling_team`, Ruff, v1/v2 validation,
  `git diff --check`, detect-changes review, and live-ledger before/after evidence. The independent
  round may append the real fifth tranche only after code checks pass, then must prove 55 records,
  10 starts, 5 authorizations, cap 12, and no reservation/platform/runtime mutation.

### Round 26 — 2026-08-01 independent continuing-authorization ledger preflight — PASS

- Scope and before-state: this was an independent StartLedger/CLI/Runner check. Before any write,
  the real ledger SHA-256 was
  `914853953fc38fa0ebbf364f2aefffa16fb4edbb885ca473440c954be7f21d9b`, with 54 records, 10
  semantic starts, four authorization records, and ordered replay cap 10. Historical authorization
  records after starts 2/4/6/8 replayed compatibly. Attempt
  `r23002-real-20260731l` remained unopened; state and non-runtime evidence digests were
  `3c7b666b110b2e5153cd8aa015564e63e1a7a63f223cb2980b8472b4e31fee14` and
  `4d7e78beafdd94c21552962f60be1ab25f2e998c3f49132a5e40fc06282c467b`.
- Ledger contract: PASS. Focused tests covered ordered replay, forged consecutive well-formed
  authorizations without consumption, exact `+2` validation, ID/reference uniqueness, malformed
  inputs, no-append direct and CLI rejection before consumption, Runner non-self-authorization,
  and cap-10 concurrent fifth-tranche behavior (two distinct calls yield exactly one success and
  cap 12). The start-11 negative cases still require the immediately prior retryable false-complete
  attempt-ten terminal record, independently tested Round-25 repair baseline, exact baseline,
  fresh run ID, no other active reservation, and the 20-minute freeze; missing repair, wrong
  baseline, or expired freeze rejects before reservation.
- Regression and change review: PASS. Focused `test_r23002`, `test_runner`, and `test_transport`
  passed 54 tests; full `modeling_team` discovery passed 95 tests. Ruff, schema-v1 and schema-v2
  validation, and `git diff --check` passed; service was active and backend/frontend health passed.
  `detect_changes(scope=all)` reported CRITICAL across the pre-existing shared dirty worktree
  (17 files, 233 symbols, 283 flows). This is a review warning for the aggregate parallel R2.3
  changes, not a new Round-26 product edit; this round changed no product symbol.
- Authorized ledger mutation: PASS. Only after all code checks passed, the locked production CLI
  appended exactly one `budget_authorization` record with `additional_starts=2`, ID
  `2026-08-01-continuing-authorization-tranche-5`, and reference
  `2026-08-01 user continuing authorization through R2.3-002 completion; tranche 5`. The prior
  54-line prefix remained byte-identical to the before SHA. After append the ledger has 55 records,
  10 semantic starts, five authorizations, replay cap 12, and SHA-256
  `a1f7304b9c019d6fdab55d89ff5ba8dc92ca9180c751238fd895774b4ca95c9d`.
- Preservation: PASS. The only newly appended event is the fifth authorization; no reservation,
  presemantic release, semantic start, Platform scope/key/session/lease/batch operation, or Runtime
  process was created. Attempt-ten state/evidence digests remained exactly unchanged. No cleanup is
  required because the authorized append-only ledger record is the requested durable result.
- Defects and decision: no Critical, High, or Medium product defect was found. Overall result is
  **PASS** for the continuing-authorization fifth tranche and its reservation safeguards. Cap 12
  does not itself reserve or start attempt 11; the existing exact repair/baseline/fresh-ID/single-
  reservation/freeze gates remain mandatory.

### Round 27 — planned Protocol cross-Batch ordering preflight

- Contract tests require the Agent-visible construction contract and Protocol instructions to state
  the exact platform-mechanical schedule: class; property/relation type; entity; bind generated IRI;
  relation; dependency-safe Shape. The contract must forbid semantic mutation, unbound forward
  references, Shape-first application, and delegation of exact Item authorship to Modeling.
- A focused regression proves the ordering text is part of the schema-v2 Protocol private source and
  therefore the frozen baseline, while schema v1 and non-Protocol roles remain unchanged.
- Independent real-path execution uses a fresh temporary PlatformScope, production
  `CodexRuntimeAdapter`, real bwrap/app-server, and native MCP RPC without a model turn. It applies a
  minimal relationship-bearing model in the required order, then creates a Shape requiring that
  relationship and observes successful semantic validation.
- Cleanup releases the Lease, cancels the Session, revokes both temporary keys, deletes the exact
  Project, and directly proves zero Project/Ontology/Session/Lease/key residuals. The ledger must
  remain exactly 59 records, 11 semantic starts, five authorization records, cap 12; attempt eleven
  state/evidence must remain byte-identical.
- Only a PASS may bind this repair to attempt eleven and freeze a fresh attempt-twelve baseline.
  Failure stops before reservation, Project creation, business-source delivery, or model startup.

### Round 27 — 2026-08-01 independent Protocol cross-Batch ordering preflight — PASS

- Before/after preservation: PASS. The live ledger was frozen and rechecked byte-identically at
  SHA-256 `2e4b80ff77a4c297daffcdfbb170ce73c253f20e618f97e43e9fd3e1bb11e7a9`, 59 records,
  11 semantic starts, five authorizations, and replay cap 12. Retained Attempt 11
  `r23002-real-20260801m` was never opened: its `state.json` SHA-256 remained
  `2e5a0b43b5af76937265740e54d7ccca93d3abc0cd4038ba85c479f4a96a5d5b`, and its
  non-runtime evidence-tree digest remained
  `885335ef5c48aa36a27e1af955b17d4db36659a9e486196e41ec072108b6f320`.
- Contract and regression: PASS. Focused `test_r23002` passed 34 tests; full `modeling_team`
  discovery passed 96. Ruff, schema-v1 `base-capability-smoke`, schema-v2
  `new-scope-business-slice`, `git diff --check`, active service, backend `/api/health`, and
  frontend `/` (200) passed. The contract schedule/prohibitions are Protocol-private and the
  frozen baseline binds their source digest; schema v1 and non-Protocol roles remain isolated.
- Native production path: PASS. Fresh temporary run `r23002-round27-fcd5bbc0b8db` used the
  production `CodexRuntimeAdapter`, real `bwrap`, real app-server, schema-v2 private Protocol
  config, and direct app-server `mcpServer/tool/call` calls to the registered
  `ontology_platform` MCP server. No `turn/start`, model turn, Runner reservation, semantic start,
  business source, or Attempt 12 activity occurred. The only staged Agent-visible inputs were
  `public-protocol.md` and `modeling-batch-item-contract.json`; the Protocol MCP child had the
  fixed reasoner/PATH contract.
- Ordered native MCP evidence: PASS. The formal `get_ontology_workspace_context` and
  `get_modeling_context` reads supplied the actual graph-set ID and initial workspace version.
  The five separate stages were class (`c113ef6a-863d-49f2-8673-b000eca158a4`), vocabulary
  (`6aff787d-553f-4da8-8679-f83ec01b27da`), entity (`46d40548-1429-4e93-81bc-8b14e1036110`),
  relation (`34b34d16-55ac-4a82-9758-b6be528985e6`), and dependency-safe Shape
  (`0b17b482-818b-4ce4-b0c1-0b9a1aaf5c76`). Every stage observed
  `dry_run=validated`, then the identical `apply_atomic=applied`, and advanced only from the
  returned workspace version. The entity Batch reread exactly matched the applied receipts for
  generated source/target entity IRIs before relation construction. The relation used the applied
  object-property IRI; the post-relation Shape required that same property (`min_count=1`), and
  native `run_semantic_validation` returned `conforms=true` (run
  `bf529962-df36-4bbb-8668-fe3fc8af92e0`).
- Cleanup: PASS. The temporary Lease was explicitly released and Session cancelled through the
  same native MCP path; the Protocol runtime stopped with private credentials destroyed. The exact
  Protocol key and bootstrap key were revoked, and the exact owned Project deletion returned 204.
  Direct PostgreSQL counts for the exact temporary Project, Ontology, Build Session, Lease,
  Project key, and active bootstrap key were all zero.
- Defects and decision: no Critical, High, or Medium product defect was found. Overall result is
  **PASS**. This independently proves the narrow cross-Batch repair on the production Protocol
  path; it does not itself bind a repair baseline or reserve/start Attempt 12.

### Round 28 — planned Protocol validation-scope preflight

- Contract tests require the Protocol-private platform reference and instructions to enumerate only
  `asserted_only` and `asserted_plus_reasoning`; the separated R2.3-002 flow must select explicit
  `asserted_only`, while the latter requires a formally bound reasoning result graph IRI.
- Production Adapter/bwrap/app-server/native-MCP no-model execution in a fresh temporary scope must
  apply a minimal valid model, directly observe validation with `asserted_only` returning
  `conforms=true`, and retain a separate exact rejection for illegal `all` without treating it as the
  positive result.
- Cleanup and preservation require zero Project/Ontology/Session/Lease/key residual, byte-identical
  ledger at 64 records/12 starts/six authorizations/cap 14, and byte-identical Attempt 12 state and
  non-runtime evidence digest. No Producer reservation/start is permitted.
- Only PASS may bind the Attempt 12 repair and freeze the next fresh baseline.

### Round 29 — planned retained-success cleanup/handoff recovery

- Unit regression supplies the exact `PlatformScope.cleanup()` success superset, including mode,
  Session terminal evidence and key-revocation fields. Writer must accept it only when
  `mode=create`, `sessions_terminal=true`, `protocol_key_revoked=true`, and
  `admin_key_revoked=true`; it validates the seven formal fields and persists only the exact
  non-secret projection plus completed terminal statuses.
- Negative tests retain rejection for each missing/invalid formal field, non-owned/non-retained
  scope, incomplete Agent terminal statuses, existing immutable target, every missing/false cleanup
  safety confirmation, and secret canaries in extra cleanup metadata. No extra field may appear in
  the retained input.
- Recovery operates on `r23002-real-20260801o` only after code checks: re-read Project/Ontology,
  completed Session revision 4, released Lease, revoked keys and workspace version; write the missing
  retained input exactly once, append after-cleanup runtime hashes, remove any remaining local secret
  directory, and atomically move state from CLEANING to CLEANED without rerunning any Agent, Batch,
  validation, reasoning, query, Session completion, or semantic-start ledger event.
- Independent verification freezes Producer evidence before recovery, verifies exact allowed new
  files/state transition, proves retained live scope identity/version and zero active temporary keys/
  leases/runtimes, then proceeds to Phase A independent semantic acceptance. Any drift stops.

### Round 28 — 2026-08-01 independent Protocol validation-scope preflight — BLOCKED

- Executed scope: focused `modeling_team.tests.test_r23002` passed 35 tests; full
  `unittest discover -s modeling_team/tests -p 'test_*.py'` passed 97 tests; `ruff check
  modeling_team`, schema-v1 and schema-v2 validation, and `git diff --check` passed. The resident
  service was active, `/api/health` returned `{"status":"ok"}`, and frontend `/` returned 200.
- Native production path: PASS. Fresh temporary run `r23002-round28-310053c4e3c4` used production
  `CodexRuntimeAdapter`, schema-v2 Protocol private configuration, real bwrap and Codex app-server,
  and native `mcpServer/tool/call` RPC only. It staged exactly Protocol's
  `modeling-batch-item-contract.json` and `public-protocol.md`; no business source, model turn,
  Runner reservation, semantic start, or ledger write occurred. One temporary class Batch was
  `dry_run=validated` then `apply_atomic=applied`. Native `run_semantic_validation` with explicit
  `asserted_only` returned `conforms=true`, `status=succeeded`, zero violations, and validation run
  `9575e4f7-f36d-441e-819f-e609f86b1880`. A distinct native call with `validation_scope=all`
  returned exactly `{"ok":false,"error_code":"validation_error","error":"Unsupported validation scope: all"}`.
- Cleanup: PASS. The native path released its Lease and cancelled its Session. Runtime and broker
  stopped; the exact Protocol key and bootstrap key were revoked, owned Project deletion returned
  204, and direct PostgreSQL counts were zero for Project, Ontology, Build Session, Lease, Protocol
  key, and active bootstrap key.
- Preservation: the live ledger was byte-identical at SHA-256
  `f7ba3b4ae791e24ebc1390cf4cc53c67198864baad8a426bdb0e4cbf40adb10a`, 64 records, 12 semantic
  starts, six budget authorizations, and replay cap 14. Attempt 12 `state.json` remained
  `dba0c567513b5e2d8b07d99601789861274320b5790c75fee6b6ad6134e09397`. However, the stored
  pre-round non-runtime evidence digest (`6b1153ef7e5ac2ff5d06abd5392ff27c4b41c85c555f2de03935c355e2b043`)
  could not be reproduced from the available digest description: the documented path-plus-NUL-plus-
  bytes calculation over the retained tree produced `0ce0ed5737d3cace0651b20aa71ed624a0d527e9b33d960210e2b8e83f4ff31c`,
  and excluding runtime/evidence/source common subsets did not match. This tester did not open or
  write that retained run, but byte-identical non-runtime evidence is not formally proven.
- Decision and defect: overall **BLOCKED**, not a product failure. Blocker B28-01 (Medium,
  evidence/acceptance): the authoritative non-runtime evidence-digest algorithm/input set is absent,
  so the required Attempt-12 preservation gate cannot be reproduced. Reproduction: compute the
  retained Attempt-12 digest from the stated path-plus-NUL-plus-bytes rule; actual value is
  `0ce0…ff31c`, not the frozen `6b115…6b043`. Expected: reproduce the frozen digest byte-for-byte.
  Actual: no matching available input set. The delivery owner should provide the original digest
  script or explicit file manifest, then rerun only this preservation check before binding the repair
  baseline; no product-code repair is indicated.

### Round 28 — preservation-only retest/correction — PASS

- Retest scope: no Platform request, temporary scope, Agent runtime, ledger write, or implementation
  change was made. The restored original digest algorithm is exactly: set `directory` to Attempt
  12's `evidence/` directory; for each file in sorted recursive path order, hash its path relative to
  that directory, a NUL byte, and its bytes. It intentionally excludes the retained run's runtime,
  snapshots, and state files.
- Result: PASS. The exact 14-file evidence directory produced SHA-256
  `6b1153ef7e5ac2ff5d06abd5392ff27c4b41c85c555f2de03935c355e2b6b043`, equal to the frozen
  baseline. Attempt 12 `state.json` remained
  `dba0c567513b5e2d8b07d99601789861274320b5790c75fee6b6ad6134e09397`; ledger remained
  `f7ba3b4ae791e24ebc1390cf4cc53c67198864baad8a426bdb0e4cbf40adb10a`, 64 records, 12 starts,
  six authorizations, cap 14. Direct database recheck for
  `r23002-round28-310053c4e3c4` found zero Project, Ontology, Build Session, Lease, and active
  bootstrap-key residuals. `git diff --check` passed.
- Correction and decision: B28-01 is **RESOLVED**. The prior whole-run calculation was an incorrect
  input set, not retained-evidence drift. Combining this preservation retest with the recorded
  native MCP, cleanup, and regression evidence, the final Round 28 result is **PASS**, with no
  Critical, High, or Medium defect. The delivery owner may bind the tested repair baseline subject
  to the requirement's remaining ledger/fresh-ID/single-reservation/freeze gates.

### Round 29 — 2026-08-01 independent successful-scope cleanup recovery — PASS

- Phase A, developer repair: PASS. Review of `TeamRunner._write_retained_handoff_evidence()` confirms
  that it accepts only `mode=create`, owned `retained-pending-acceptance` scope, terminal Sessions,
  revoked Protocol and bootstrap keys, all required non-empty mechanical identifiers, and exactly the
  three completed Agent statuses. Its payload is a non-sensitive projection only and uses
  `O_CREAT|O_EXCL` plus read-only mode, so it cannot overwrite prior retained input. Focused
  `test_r23002` passed 36; full `modeling_team` discovery passed 98; Ruff, schema-v1/v2 validation,
  and `git diff --check` passed. The focused cases cover secret canary exclusion and every
  safety-field missing/false rejection.
- Pre-restore read-only gate: PASS. Attempt 13 `r23002-real-20260801o` was frozen while
  `CLEANING`: run tree `38cadbe07d55244b2cb5d9ff15ab0feeb5f80e0f7a5907c97276035772d6979e`
  (574 files), evidence tree `c807f50453b947c039590cac8e5f5df7fd5874032f5b2332145ba14aa28ee419`
  (13 files), state SHA `d3f08022f442d9b065f9000bc2670489dadf915d445b3240fcb77bb1e8c0e552`,
  and ledger SHA `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c`
  (67 records, 13 starts, six authorizations). Direct database/service reads confirmed Project
  `83f5ec15-07b1-446d-8f91-6c4bb9026ba6`, Ontology
  `e2c56164-e3f5-485c-9489-1f11532c90ff`, workspace version
  `0ca556b9639743ba70ab629a66221504971780e670b8a4ae5d169a42e5ac1277`, Build Session
  `ed3b1e77-4e78-4377-b178-4768b2425750` completed at revision 4, released Lease, no active
  Project or bootstrap key, no run-owned secrets, and no runtime process for this run.
- Recovery and post-check: PASS. No Agent, Batch, validation, reasoning, query, completion API,
  PlatformScope cleanup, Project creation, or ledger operation occurred. The tested writer created
  the exact once-only `retained-handoff-input.json` (mode 0444, SHA
  `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`); its projection has no
  secret/credential/token/key/canary content. It appended only `after_cleanup` to runtime-core hashes
  and atomically moved state to `CLEANED` with full cleanup scope and terminal results. The restored
  runner hash is `d159724ddf7004da41b1a42c1039426eadb969215354d9fa632b964cb0f0c25a`; Adapter and
  transport hashes remain unchanged from `before_start`, as expected for the narrow Runner repair.
  Final run tree is `31582d09ead812ed628904f1f018da8f4b3ba3313c279e8ef3f41017a203e51b` (575 files),
  evidence tree `c1eca2ff6c622874f4136fd9589508e5099f897d3d93ed18c274d89ba1b0bd3f` (14 files), and
  state SHA `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`; ledger is byte-identical.
- Decision: no Critical, High, or Medium defect. Overall **PASS**. The retained successful scope is
  safely restored for the separately governed offline handoff; this round did not publish a handoff
  or interpret semantic results.

### Round 30 — 2026-08-01 Phase A independent acceptance — INCONCLUSIVE

- Scope executed: a short-lived `read` key (`cb33e7f3-e732-484b-a2dc-1247f1fead21`) was used only
  for five GET receipts, then revoked; its bootstrap admin (`1abc3390-8f12-4ee3-8d74-5b081562667e`)
  was also revoked. Two fresh, ephemeral, no-history, read-only Codex acceptance sessions were
  started outside the Team roster: `019fb971-002f-7980-a9a1-28f0f4486bcd` and
  `019fb972-e186-7123-a42f-746514657cb3`. They received only the frozen R2.3-002 gate, tester-only
  contract, manifests, raw runtime/Agent evidence, live read receipts, and Round-29 closure evidence.
- Actual result: both sessions completed evidence-reading command items but emitted no final turn or
  required gate JSON. Therefore G1--G7 are each **INCONCLUSIVE**; no coordinator/runner/producer
  summary was promoted into a semantic PASS. No Platform write, Batch, validation, reasoning, query,
  Session operation, semantic ledger operation, producer communication, or handoff publication was
  performed by this round.
- Evidence and decision: the independent evidence record is
  `workspaces/modeling-runs/r23002-real-20260801o/evidence/phase-a-independent-acceptance.json` and
  the exact publisher input is `evidence/phase-a-verdict.json` with
  `{"verdict":"PHASE_A_INCONCLUSIVE"}`. Overall **BLOCKED** (acceptance-execution evidence), not a
  product semantic failure. Do not publish the handoff; the delivery owner should repair/replace the
  independent acceptance execution path and then start a new fresh read-only Agent Session.

### Round 30 correction — 2026-08-01 append-only evidence recovery

- Correction: the second recorded independent session `019fb972-e186-7123-a42f-746514657cb3` did
  produce `item_4` Agent JSON followed by `turn.completed` in
  `/tmp/r23002-phase-a-agent2-events-6ujab6.jsonl`. The original Round-30 artifact is preserved;
  [phase-a-round30-correction.json] records the recovered result.
- Corrected verdict: **PHASE_A_FAIL**. G2, G5 and G7 were PASS; G1, G3 and G6 were INCONCLUSIVE;
  G4 was FAIL because the then-supplied evidence showed generic-query truncation/degraded recall and
  invalid cursor continuation. The two INCONCLUSIVE findings were caused by incorrect supplied paths
  for the tester-only contract and runtime closure evidence, not an Agent finalization failure.

### Round 31 — 2026-08-01 Phase A fresh independent retry — FAIL

- Fresh acceptance identity: `019fb979-06e0-7fa2-84c8-50a31ee569a7`, ephemeral/no-history,
  non-roster and read-only. Its final event was followed by `turn.completed`; final-output SHA-256 is
  `3121acd5a8a7713f22f8594da57472cedcf2d415e8fa313ecbeafe61b7e8f0e6`. It used the corrected
  tester-only contract, source/visibility/outer-user/correlated-delivery material, runtime-core
  hashes, and targeted raw Protocol rollout Batch records. Read key
  `0e723256-42cd-498e-9973-257612bac364` (project read) and bootstrap key
  `b7478a28-a0a5-41ec-8e34-19618a4c3c7c` were both revoked after the session.
- Gate results: G1 PASS; G2 PASS; G3 PASS; **G4 FAIL**; G5 PASS; G6 PASS; G7 INCONCLUSIVE. The
  raw Protocol receipts establish matching dry-run/apply delta hashes for all six applied Batches
  and a separately rejected no-movement Shape probe. The independent Agent directly found that the
  frozen `quality_rating:number` successor answer was retained as an explicit unknown, and the raw
  generic query recorded truncation, missing vector index, `evidence_missing`, `lineage_missing`,
  invalid cursor continuation, and facts spanning another ontology. These establish G4 failure.
- Live-read limitation: all credentialed requests made from the isolated acceptance sandbox returned
  connection status `000`, so G7's current identity/version check is INCONCLUSIVE; no semantic POST
  query was attempted once that environment limitation was known. This does not affect the
  independently demonstrated G4 FAIL. The round performed no Batch, validation, reasoning, Session,
  Lease, ledger, producer communication, or handoff action.
- Evidence/decision: [Round31 independent evidence] is
  `workspaces/modeling-runs/r23002-real-20260801o/evidence/phase-a-independent-acceptance-round31.json`;
  publisher input `evidence/phase-a-verdict-round31.json` is exactly
  `{"verdict":"PHASE_A_FAIL"}`. Do **not** publish the handoff. Repair the G4 semantic
  retrieval/modeling failures and make a separately governed fresh Phase A retry available.

### Round 32 — 2026-08-01 Attempt-14 repair preflight — BLOCKED

- Frozen protection baseline: ledger SHA-256
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c`, 67 records, 13 semantic
  starts, six budget authorizations and cap 14. Attempt-13 `r23002-real-20260801o` state SHA stayed
  `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`; retained handoff input SHA
  stayed `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`; the 21-file evidence
  tree digest stayed `74acd1e4ed34d1b99db79fa083b798308100dea4d13de25025ae1e8493f71236`.
- A/contract review: focused `test_r23002` passed 37 and full `modeling_team` discovery passed 99;
  Ruff, schema-v1/v2 validation and `git diff --check` passed. The reviewed Modeling instructions
  require one grounded material-gap question at a time and reassessment after every answer, reject
  incomplete retrieval receipts, and contain no answer count or expected ontology. The Protocol
  reference is likewise generic. The current v2 Task—not role-private instructions—still contains
  the authorized C->B->A business scope.
- Blocking native sandbox proof: a fresh temporary fixture used the production
  `CodexRuntimeAdapter`, actual `bwrap` namespace construction, real Protocol package staging and
  its exact two private staged source files (`public-protocol.md` and
  `modeling-batch-item-contract.json`). Inside that exact namespace,
  `/backend/.venv/bin/python -c 'import modeling_team.protocol_mechanics'` returned code 1:
  `ModuleNotFoundError: No module named 'modeling_team'`. The mechanics contract mount exists but
  does not provide the declared `verify_scoped_retrieval_fallback` helper.
- Decision: **BLOCKED**, B32-01 (High, runtime/contract). The required real Protocol cannot access
  or execute the fallback helper it is instructed to use. Per the acceptance boundary, no host-side
  helper substitute was used; no Codex app-server/native MCP temporary scope, Batch, validation,
  reasoning, Team Runner, semantic start, ledger write, or Attempt-14 action occurred. Positive and
  negative fallback proof, temporary cleanup, and native MCP checks are therefore **not executed**.
  Resident service was active; backend health was `ok` and frontend returned 200. Developer must
  make the helper available through a frozen Protocol-private executable mechanism, with matching
  instructions/reference, before a new Round32 retry.

### Round 32 — planned attempt-fourteen repair preflight

- Contract tests require Modeling to reassess all source-derived, consumer-material gaps after each
  grounded answer and to ask only one question at a time, without exposing tester answers/counts or
  scenario-specific expected structures. A candidate cannot be frozen while an unanswered material
  question remains merely because an earlier question was answered.
- Contract tests require Protocol to treat truncation, missing required Evidence/lineage,
  cross-ontology facts, invalid continuation, or otherwise incomplete ontology-scoped generic query
  evidence as a blocker. Modeling must not accept such a receipt as completed. A generic scoped
  non-vector fallback is allowed; semantic invention and scene-specific query code are not.
- The frozen fallback algorithm binds the selected Ontology and authoritative resource counts from
  `get_modeling_context`. For the fresh create scope, formal applied Batch receipts enumerate
  class/property/relation-type/Shape/entity by `command_kind` and resource outputs; every receipt's
  `ontology_id`, output ID/IRI, workspace chain and immutable delta hash must bind the target, and
  receipt-derived counts must equal the corresponding authoritative counts. It first proves the
  fresh asserted-data graph empty and reconstructs the expected distinct asserted triple set from
  normalized applied deltas, allowing only create-only inserts into the target data graph. Relation Items instead
  bind normalized source/predicate-or-relation-type/target triples plus Batch delta hash, require each
  triple in the complete ontology facts read, and compare distinct relation sources computed by the
  platform rule to the authoritative relation count. With known sufficient capacity, the facts read
  distinct triple set must equal the reconstructed set exactly, while its distinct subject count
  equals the authoritative fact count; row count is never compared to that subject count. Ontology-
  scoped entities independently equal the entity count and bind every resource to the target. Lineage/
  statement provenance binds each candidate-required assertion. Missing
  completeness metadata provides no proof and must be compensated by exact authoritative-count
  equality plus known sufficient capacity; unknown/insufficient capacity, receipt/read mismatch,
  unbound ownership, missing provenance, or failed cursor continuation blocks. Absence of warnings
  alone is never completeness evidence.
- Review exact prompt/Task deltas, focused/full tests, Ruff, schema validation, diff check and a
  no-model role-contract preflight. The preflight must use production Adapter/native MCP with a
  temporary non-semantic scope: prove degraded-vector fallback success and independently prove
  receipt-count drift, wrong-ontology receipt, missing/drifted relation triple, read-count/ownership,
  Evidence/lineage, and continuation failures cannot yield completed. The positive fixture must
  include multiple relations sharing one source and multiple facts sharing one subject. Negatives
  preserve every subject while dropping one triple and add one unexpected triple;
  then prove exact cleanup and ledger/Attempt-13 preservation. Freeze a new baseline only after
  independent PASS. Preserve Attempt 13 and all Phase-A evidence; do not publish its handoff or
  mutate its retained scope.
- Attempt 14 may use the one remaining ledger start only after a tested repair authorization binds
  the new baseline to Round 32 PASS. The outer controller may release each frozen answer only after
  a newly observed grounded question, exactly once. Final acceptance requires a fresh Phase A/B and
  live G7 check from a host-reachable read-only path.

### Round 32 retry — planned Protocol-private verifier runtime repair

- Stage a minimal stdio MCP wrapper plus verifier module as exact immutable run assets; verify
  regular-file identity/digest against the baseline, retain verified descriptors through process
  launch, pass them to bwrap, mount their `/proc/self/fd/<n>` inodes read-only under Protocol-only
  `/opt`, and start a
  required `protocol_mechanics` local MCP server with system Python. It exposes exactly the fallback
  proof verifier and has no credential, network, platform, write, query-authoring, or semantic role.
- Replace the reference's host import string with the exact MCP server/tool/launch contract and make
  Protocol instructions require that native call. Baseline manifest includes wrapper, verifier and
  the Agent-visible launch/tool contract. Test baseline drift plus replacement after verification but
  before `Popen`; the mounted/executed bytes must remain the verified inode or startup must fail.
- Coordinator/Modeling must have no asset path, mount, config or tool visibility. Protocol cannot
  import the host repository; it must list and call the local MCP tool inside the real bwrap/app-
  server namespace. Tampered/missing/symlink/writable/wrong-role assets and unknown tool calls fail
  closed. Existing mechanics JSON and reasoner remain exact file mounts.
- GitNexus upstream impact is LOW for `_stage_protocol_mechanics_contract` (one direct),
  `_write_config` (one direct), `namespace_command` (two direct/three aggregate), and
  `_require_expected_mcp_servers` (one direct/two aggregate); isolation,
  dynamic-tool policy, runtime asset, config and real-bwrap tests cover the blast radius.
- The schema-v2 pre-turn MCP check requires the exact per-role server set and exact tool set:
  Protocol has team transport, ontology platform allowlist and one verifier; other roles have only
  team transport. Server startup failure, zero/wrong/extra tool, extra server and wrong-role config
  all fail before semantic start and release the reservation.
- After implementation, repeat all original Round 32 production native-MCP positive/negative,
  cleanup, ledger/Attempt-13 preservation and service-health gates. No semantic start or repair
  authorization occurs until this retry passes.

### Round 32 second retry — planned real-response schema and graph-role repair

- Verifier input is the full formal `{ok,data}` response family: initial/final modeling context
  (identity at `data.ontology.id`), workspace context, exhaustive session Batch inventory,
  `get_modeling_batch` details, entity/fact read models, and raw statement lineage responses.
  Protocol does not invent `command_kind` or per-item deltas in submit
  receipts; Batch detail Items supply commands/outputs and the applied Attempt supplies top-level
  normalized delta/hash/workspace versions.
- Every input must have `ok is true` and an object-valued `data`; parse only `data.*`. Add fail-closed
  cases for `ok:false`, missing/non-object `data`, and otherwise plausible fields misplaced at the
  response root.
- Take the unfiltered inventory after the Session and all writes are stable. Its request limit must
  exceed returned count, `next_cursor` is absent/null, and its Batch IDs exactly equal detail IDs.
  Classify details as write Batches with exactly one applied `apply_atomic` Attempt, or non-write
  validation Batches containing only `dry_run` Attempts in `validated`/`validation_failed` state.
  Only applied write Attempts contribute delta/workspace state; reject any non-write Batch with an
  applied, partially-applied, applying or recovering Attempt. The real positive must retain a
  rejected Shape dry-run probe, and a negative must prove that counting its proposed delta fails.
  Bind asserted-ontology, asserted-data and Shapes member roles/owners from workspace context.
  Command-to-graph rules permit schema, entity/relation and Shape create inserts only in their formal
  graph roles; delete/clear/drop/unknown graph or role mismatch blocks. Recompute delta hashes and
  require a contiguous applied workspace chain.
- For asserted-data, require effective statement-list capacity
  `min(requested_limit, 1000)` strictly greater than expected count; expected count at or above 1000
  blocks. Add a boundary negative with 1000 expected statements plus one hidden extra same-subject
  statement. Reconstruct
  object terms from its real `subject/predicate/object/object_kind/object_datatype/object_language/
  source_graph_iri` fields, compute canonical platform fact IDs on both read and delta sides, and
  compare exact sets; validate graph, distinct subject/fact count, relation Item payload triples and
  distinct source/relation count. Compare entity-list `iri`s to formal entity output IRIs and require
  bound data graph. Other create resource-output counts
  equal final modeling-context counts.
- Candidate-required assertions are exact current quads/fact IDs. Raw
  `get_ontology_lineage(target_type=statement,target_id=fact_id)` must bind the same Ontology and exact
  target, be non-truncated, and contain a matching item with exact statement ID/quad, technical-trace
  Graph Set/data graph, origins and supporting Evidence. Deprecated resource provenance is not a
  duplicate gate. Add real-shape positives for all
  three exact graph roles and negatives for incomplete/mismatched Batch inventory, nested identity
  drift, command/graph mismatch, top-level delta
  drift/hash drift, workspace break, wrong fact ID/graph, missing/extra fact with same subject, entity
  IRI drift and exact lineage scope/target/statement/quad/trace/truncation/evidence failures.
- Repeat production native MCP B-D and exact cleanup/preservation. Do not authorize Attempt 14 until
  the real-response positive and full negative matrix pass.

### Round 32 retry — 2026-08-01 independent native-MCP retest — FAIL

- **Frozen inputs and A/regression:** before the retest, the R2.3 start ledger remained SHA-256
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c` (67 records, 13 semantic
  starts, six authorizations, cap 14). Attempt 13 state, retained handoff input and 21-file evidence
  tree remained respectively `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`,
  `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`, and
  `74acd1e4ed34d1b99db79fa083b798308100dea4d13de25025ae1e8493f71236`. Focused R2.3-002 tests
  passed 37, full `modeling_team` discovery passed 101, Ruff passed, both v1/v2 profile/task
  validations passed, and `git diff --check` passed before the append-only test record update.
- **B32-01 runtime repair:** PASS. A temporary, empty, fully cleaned scope started the production
  `CodexRuntimeAdapter` under bwrap for all three actual roles. Coordinator and Modeling exposed
  only `team_transport/{send_team_message,report_task_result}`. Protocol exposed exactly that
  transport pair, the frozen 20-tool `ontology_platform` allowlist, and exactly
  `protocol_mechanics/verify_scoped_retrieval_fallback`. The two private executable assets and the
  mechanics JSON were mode 0444; the namespace command held two verified `/proc/self/fd/<n>`
  read-only asset mounts. Role-visibility probes passed for all three roles. An app-server native
  `mcpServer/tool/call` returned structured `{complete:true}` for a valid mechanical proof; its
  insufficient-capacity proof returned MCP error `-32010` (fail closed). The temporary Project,
  Protocol key and bootstrap key were deleted/revoked.
- **B positive real-receipt/retrieval gate:** FAIL, defect **B32-02 (High, platform-contract)**.
  In a separate temporary empty scope, the real Protocol native `ontology_platform` MCP created a
  Build Session and lease, then completed a class `dry_run` and `apply_atomic` pair. Native reads of
  `get_modeling_context`, `get_ontology_read_model(classes)`, and
  `get_ontology_read_model(facts)` were made before calling the native verifier. The formal apply
  receipt does not match the verifier's declared proof input: `get_modeling_context` binds identity
  as `ontology.id`, not `ontology_id`; each receipt item lacks `command_kind` and
  `normalized_deltas`; and the actual class delta is in asserted-ontology graph
  `.../graph/ontology/<ontology-id>`, while the verifier admits only asserted-data graph inserts.
  The native verifier rejected the unaltered formal read/receipt construction with `-32010:
  modeling context does not bind the selected ontology`. This is not repairable by a Protocol
  host-side conversion: even a receipt projection that added the missing identity/item fields would
  still reject schema/property/relation-type/Shape deltas as outside the target data graph, although
  their counts are mandatory to the same verifier. Therefore a real fresh scope cannot produce the
  required successful fallback proof, including the planned shared-source relations and shared-subject
  facts, using the current generic MCP receipts/reads.
- **C negatives and D:** the one native capacity negative above passed; the focused unit suite also
  covers wrong ontology, receipt-count drift, same-subject missing-plus-extra triple, missing
  provenance, invalid continuation, and insufficient capacity. They are not a substitute for the
  required real-receipt positive/negative matrix, which is **BLOCKED by B32-02**. Both temporary
  nonempty scopes were explicitly cancelled, Protocol keys revoked, Projects deleted (HTTP 204), and
  bootstrap keys revoked. No Team Runner, ledger reservation/start, Attempt 14, retained Attempt 13
  mutation, validation/reasoning acceptance, producer communication, or handoff publication was
  performed.
- **Conclusion:** overall **FAIL**, not PASS. A developer must align the generic retrieval proof
  contract with the actual formal MCP schemas and their multi-graph storage model (or add a generic,
  governed receipt/read projection), then rerun this same Round 32 retry plan from B through D before
  any repair authorization, new baseline, or Attempt 14 start.

### Round 32 third retry — planned B32-03 statement-list scope repair

- Add a backend regression that represents the target Graph Set's asserted-ontology and
  asserted-data graphs plus a foreign Ontology asserted-data graph. Prove `statement-list` selects
  only the exact `role=asserted_data` member, compiles an explicit `VALUES ?graph` for that graph,
  returns the requested facts, and excludes same-scope schema and foreign data statements even when
  either would otherwise fill the bounded response.
- Add only a `statement-list` role-aware selection branch and bind its filtered `{graph_iris}` in the
  SPARQL template; do not change the API, repository, response schema, limit or any other read
  model's selection. Run the
  focused read-model tests and full backend suite, then restart and health-check the managed service.
- Repeat Round 32 B-D through production bwrap/Codex Protocol native MCP. The positive must use
  unmodified formal responses and exact lineage, and the full proof-copy negative matrix must start
  from that real positive. Clean all temporary resources and prove ledger/Attempt13 preservation.
  No repair authorization, baseline or Attempt 14 is allowed before PASS.

### Round 32 fourth retry — planned B32-04 computed fact-ID repair

- Keep the formal facts response unchanged: rows contain subject, predicate, object metadata and
  source graph, with no synthetic `fact_id`. The verifier must compute the canonical four-term ID
  and use it for exact delta-set comparison and required-assertion correlation.
- The lineage request record retains its computed request `fact_id`; validate that the raw lineage
  target, statement ID/quad, technical trace, origins and Evidence all bind that same computed ID.
  Add a positive without row `fact_id` and negatives for changed quad, forged optional row ID,
  mismatched lineage-record ID and mismatched raw lineage target/statement.
- Repeat the same production Protocol native-MCP B-D positive and complete proof-copy negative
  matrix, cleanup, frozen evidence and health checks. No Attempt 14 action before PASS.

### Round 32 fifth retry — planned B32-05 actual read-envelope binding

- Use unmodified entity-list and statement-list envelopes. Require exact workspace
  `default_graph_set_id` and `source_signature`, the expected `model_name`, asserted include, and
  exact asserted-data `source_graph_iri` on every row; do not require absent `ontology_id`,
  `truncated` or `next_cursor` fields.
- Preserve entity output/count equality and fact computed-ID exact-set equality. For statements,
  prove completeness only through `min(requested_limit,1000) > expected applied statement count`
  plus exact set/count equality. Add negatives for graph-set/signature/model/include/row-graph drift,
  missing/extra items and insufficient capacity. Keep only Batch inventory's real `next_cursor`
  negative; this proof has no generic query receipt and must not synthesize continuation coverage.
- Repeat the same production Protocol native-MCP positive, complete proof-copy negatives, cleanup,
  frozen ledger/Attempt13 and health gates. No Attempt14 action before PASS.

### Round 36 — planned B32-06 Protocol fallback routing repair

- Freeze the Protocol contract so an incomplete/degraded/truncated generic query in an eligible
  fresh-create run mandates collection of the formal proof and a native
  `protocol_mechanics.verify_scoped_retrieval_fallback` call before terminal conflict. A
  `complete=true` result is successful retrieval evidence; tool failure/incomplete proof blocks.
- Add contract tests that reject optional wording and require this exact order. Run a Protocol-only
  production bwrap/native-MCP exercise with a real fresh-create proof and an incomplete query
  receipt; raw events must show the verifier call and a success receipt derived from its result.
  Also prove verifier error remains fail-closed. This preflight creates no semantic start.
- Preserve and explicitly clean Attempt14's failed-written Project/Session/keys, then verify DB zero
  residue, frozen evidence and service health. Append exactly one immutable Attempt14
  `terminal_failure` classified `collaboration/routing` with
  `complete_modeling_quality_result=false`; verify idempotent duplicate rejection. Only after
  independent PASS may the continuing user authorization append the next exact +2 tranche, bind a
  new repair baseline to that failure, and prove the ledger accepts the fresh reservation.

### Round 37 — planned B32-07 Protocol verifier elicitation authorization

- Accept `protocol_mechanics` elicitation only for a schema-v2 Protocol Agent. Prove schema-v1
  Protocol, schema-v2 Coordinator/Modeling, unknown/extra servers and wrong tools remain denied;
  exact MCP preflight continues to require the one verifier tool.
- Preserve sanitized elicitation evidence and add no platform credential, network or dynamic exec
  capability. Run Codex isolation, focused/full modeling-team, Ruff, v1/v2 validation and diff gates.
- Repeat Round36's real Protocol-only incomplete-query success route and verifier-error conflict
  route, then cleanup and verify zero residue/frozen evidence/health. No semantic start before PASS.

### Round 38 — planned B32-08 exact verifier tool argument contract

- Replace the verifier tool's arbitrary-object input schema with the exact ten required top-level
  proof fields and `additionalProperties=false`. Descriptions require direct, unmodified full
  envelopes and forbid a nested `proof` wrapper or reconstructed workspace/read projection.
- Unit-test the exact tools/list schema and direct valid/invalid calls. Repeat the production
  Protocol-only real positive: the same proof must first verify directly, then the Agent call must
  preserve it and return success after `complete=true`. Retain the actual invalid-proof conflict.
- Cleanup every temporary process/scope/key and prove DB zero residue, frozen ledger/Attempt14 and
  service health. No budget, baseline or semantic start before independent PASS.

### Round 39 — planned B32-09 deterministic terminal verifier gate

- For v2 Protocol in fresh-create scope, derive a monotonically replaced retrieval episode only from
  completed App Server `mcpToolCall` items whose query arguments bind `scope_mode=ontologies` and a
  non-empty string `ontology_ids` list. Project/empty/malformed scope queries do not create or replace
  episodes. A successful matched generic envelope needs no verifier only with complete recall, no
  aggregate/page truncation or cursors, no cross-scope item, supported asserted Evidence, complete
  lineage and no missing/partial/truncated Evidence/lineage warnings. Error, no-match, degraded,
  truncated, cursor-bearing, cross-scope or Evidence/lineage-incomplete results arm fallback; only a
  later completed native verifier item for that episode satisfies the attempt obligation.
  Elicitation alone never does.
- Reject `report_task_result` before broker delivery only while the current eligible episode is
  armed and unsatisfied. Preserve the episode across turns and replace it on another eligible query.
  After successful apply_atomic, validation or reasoning, enter an independent `query_required`
  state that blocks terminal and cannot be cleared by a verifier; only a later eligible completed
  query replaces it. Failed operations and dry-runs do not invalidate. Do not gate v1,
  other roles, non-create scope, `send_team_message`, no-query conflict paths or complete generic
  results. Return only one fixed retryable error.
- Unit-test complete-without-verifier, incomplete rejection, verifier success/error completion,
  elicitation-only, unfinished item, verifier-before-query, prior-episode verifier, later-query,
  project/empty/malformed query scope, recall-complete with missing Evidence/lineage, scope leakage,
  mutation invalidation, mutation-then-verifier non-bypass, failed/dry-run non-invalidation,
  cross-turn satisfaction, role/schema/scope non-regression, sanitized evidence and unchanged broker
  rules. Because GitNexus reports the shared transport helper CRITICAL
  aggregate (one direct, 456 total), run all Codex isolation, transport, runner and complete
  modeling-team tests.
- In production Protocol-only bwrap, observe the actual incomplete generic MCP item, prove the first
  terminal report is rejected, then observe a completed native verifier item and correlated success
  or conflict terminal acceptance. Also prove the complete generic path can terminate without a
  verifier. Cleanup and preservation gates remain mandatory; no semantic start before PASS.

### Round 40 — planned B32-10 production Team Transport gate binding

- Add one default-false RuntimeAdapter terminal guard, pass it from TeamRunner to the Broker, and
  invoke it synchronously at the start of `TeamTransportBroker.report` before terminal state changes.
  Broker owns the fixed retry error; absent/exact-false alone allows, while true/non-bool/exception
  fails closed without reflecting callback data. For normal stdio, Codex takes a per-Agent App
  Server I/O lock, drains/applies pending notifications, then reads state under a state lock. The
  legacy dynamic helper, already inside ordered notification dispatch, adds a host-internal top-level
  Broker-request marker so the callback skips only the second drain and still applies the same state
  decision. Agent-local forwarding and tool arguments cannot create that top-level marker.
- Unit-test direct Broker blocked/allowed results, zero result mutation on rejection, fixed error,
  unaffected send, default adapters, Runner hook wiring, eligible/noneligible Codex states, single-
  reader stdout locking, pending query notification drain-before-guard, internal marker rejection
  from ordinary MCP arguments, actual Unix-socket stdio forwarding, dynamic-helper parity and all
  prior gate matrices. Add bounded deadlock tests for blocked and allowed dynamic callbacks received
  from both `_rpc` and foreground drain, plus an interleaving where query completion is pending when
  normal stdio report reaches Broker; it must not see idle/old state.
  Re-run isolation, transport, runner, R2.3-002 and complete modeling-team suites because Broker
  `report` and Runner `start` both have CRITICAL aggregate impact.
- Repeat the production Protocol-only B fixture. Required evidence order is actual eligible
  incomplete query -> `fallback_required` -> actual report MCP rejected before broker plus sanitized
  `terminal_blocked` -> actual verifier item completed/failed -> later actual report MCP accepted by
  Broker. No synthetic App Server item may substitute.
- Rebuild A with the same deterministic temporary platform setup, but compute in memory a sanitized
  completeness checklist covering result status, recall, aggregate/pages/cursors, Ontology scope,
  Evidence, lineage and blocking warnings before discarding the response. PASS requires an actual
  complete generic item and accepted terminal without verifier; otherwise record the exact failed
  member as INCONCLUSIVE/FAIL without broadening the fixture. Cleanup and preservation remain hard
  gates; no ledger/budget/semantic start before independent PASS.

### Round 32 second retry — 2026-08-01 independent real-response native-MCP preflight — FAIL

- **A / frozen inputs:** PASS. Before the fixture, focused `test_r23002` passed 37 and full
  `modeling_team` discovery passed 101; Ruff, v1/v2 profile-task validation, and `git diff --check`
  passed. The ledger remained SHA-256
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c` (67 records, 13 starts),
  Attempt-13 state remained `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`,
  and its retained handoff input remained
  `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`.
- **B / production native fixture:** FAIL, defect **B32-03 (High, ontology read-scope contract)**.
  A production `CodexRuntimeAdapter` Protocol Agent ran in its bwrap namespace and used only native
  `mcpServer/tool/call`. In one temporary create scope it created a Build Session/checkpoint/lease;
  applied class, property/relation-type, three entity, two shared-source relation, and Shape Batches
  through dry-run then apply-atomic receipts; and retained a separate malformed Shape dry-run with
  `attempt_status=validation_failed`. Each later Batch bound only the immediately prior formal
  workspace version and outputs (the first setup probe's cross-Batch `depends_on` was rejected as
  expected platform input validation and was fully cleaned before this fixture).
- The required native `get_ontology_read_model(model_name=facts, ontology_id=<temporary ontology>,
  limit=1000)` returned statement rows from unrelated live Ontology graph IRIs. It did not contain
  the two expected temporary shared-source relation statements in the returned set, so their exact
  fact IDs and `get_ontology_lineage` requests could not be bound. This violates the updated
  contract's ontology-scoped stable fact inventory prerequisite and prevents construction of a real
  positive proof; the native verifier was deliberately not called with invented/missing assertions.
  This is a Platform read-scope failure, not a verifier fixture failure.
- **C:** BLOCKED by B32-03. No claimed positive proof exists from which to form the required native
  proof-copy matrix (envelope, inventory, rejected delta, graph/hash/workspace/fact/entity/lineage,
  1000-capacity, and continuation negatives). Existing deterministic unit coverage remains passing,
  but it is not promoted to this real-response gate.
- **D / cleanup and preservation:** PASS. The temporary Session was cancelled (200), Protocol key
  revoked (200), Project deleted (204), and bootstrap key revoked. A direct database recheck found
  zero matching Project, Ontology, Session, active Lease, or active temporary key residual. Ledger,
  Attempt-13 state, and retained input remained byte-identical; backend health returned `ok`, frontend
  returned 200, and the service remained active. No Team Runner, ledger write/reservation, Attempt14,
  handoff publication, or retained-scope mutation occurred.
- **Conclusion:** overall **FAIL**. Developer repair must make the generic `facts` read model bind
  the requested Ontology/current graph set before the same B-D real-response preflight can resume.
  Do not authorize a baseline, repair start, or Attempt14 first.

### Round 32 third retry — 2026-08-01 independent native-MCP preflight — FAIL

- **A / B32-03 regression:** the current backend/modeling regressions, Ruff, v1/v2 validation and
  `git diff --check` were rerun without a failure result. Frozen ledger remained
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c` (67 records, 13 starts);
  Attempt-13 state and retained input remained respectively
  `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a` and
  `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`.
- **B32-03 result:** PASS. A production bwrap/Codex Protocol native-MCP fixture created the formal
  Session/checkpoint/Lease and dry/apply class, schema, entity, shared-source relation and Shape
  Batches plus the rejected Shape dry-run. Its native facts read contained only the temporary
  asserted-data graph; foreign and schema graph rows were absent.
- **New B32-04 (High, formal read-response contract):** FAIL. The unmodified public facts rows use
  the generic `id`, `iri`, `subject`, `predicate`, `object`, `object_kind`, and `source_graph_iri`
  shape, but do not expose `fact_id`. The native verifier requires that exact stable field before
  lineage binding. The tester did not calculate or insert an ID outside the received `{ok,data}`
  response, so the real positive proof correctly stopped fail-closed.
- **C:** BLOCKED by B32-04. Without an unmodified real positive, the complete native proof-copy
  envelope/inventory/rejected-delta/graph/hash/workspace/fact/entity/lineage/capacity/cursor matrix
  was not recorded as pass.
- **D:** PASS. Session cancellation 200, Protocol-key revocation 200, Project deletion 204, and
  bootstrap-key revocation completed. Direct DB checks found zero matching Project, Ontology, Session,
  active Lease, or active temporary key; ledger/state/input stayed byte-identical; service was active,
  backend health `ok`, frontend 200. No Team Runner, ledger write, Attempt14 or handoff occurred.
- **Conclusion:** overall **FAIL**. Expose canonical `fact_id` in the generic facts read response,
  then repeat this same B-D plan before any authorization or producer start.

### Round 32 fourth retry — 2026-08-01 independent native-MCP preflight — FAIL

- **A / frozen protection:** the ledger, Attempt-13 state and retained input remained respectively
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c` (67/13),
  `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`, and
  `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`.
- **B32-04 result:** PASS as far as raw fact identifiers. Production bwrap/Codex Protocol native MCP
  created the real multi-graph fixture, rejected Shape dry-run, and target-only facts read. The
  unmodified rows had no `fact_id`; the verifier's own canonical calculation supplied computed IDs
  for the two shared-source relation lineage requests, without host projection or response mutation.
- **New B32-05 (High, formal entity-response contract):** FAIL. The unmodified generic entity-list
  read response does not contain `ontology_id`, but the verifier still requires that field before it
  can validate entity output identity/count. It returned `-32010: ontology-scoped entity read is
  invalid`. The tester did not inject the selected Ontology identity from a separate response into
  that entity envelope, so no artificial real positive was created.
- **C:** BLOCKED by B32-05; no complete native proof-copy matrix was claimed. The B32-04 optional
  forged-ID, lineage-record and raw-lineage negatives likewise require a successful real baseline.
- **D:** PASS. Session cancel 200, Protocol-key revoke 200, Project delete 204, bootstrap revoke and
  DB zero residual checks passed. Frozen identifiers, service active state, backend health `ok`,
  frontend 200 and `git diff --check` remained intact. No Team Runner, ledger action, Attempt14 or
  handoff occurred.
- **Conclusion:** overall **FAIL**. Align entity-read proof identity with the actual generic response
  contract (for example, derive binding from the verified asserted-data member rather than requiring
  a non-existent field), then rerun the same B-D preflight.

### Round 32 fifth retry — 2026-08-01 independent native-MCP preflight — PASS

- **A / frozen protection:** before and after the fixture, the start ledger remained
  `9a52debf465372740aca5ecc47d492c29102be7a3b5b242fdad3e843bdd6ec1c` (67 records, 13 semantic
  starts); Attempt-13 state remained `a29a1fb737b32e59def3d3b6be6d52d4817835869960f24f521b9c1b7ab4aa0a`;
  retained input remained `2900b16f1e4882d419eb10a2f33c1b4765b6ed7ecc127886da09a590c728baa8`.
- **B / real positive:** a production `CodexRuntimeAdapter(use_bwrap=True)` Protocol Agent used only
  native `mcpServer/tool/call` to create the formal Session/checkpoint/lease, then dry-run and
  apply class, property/relation-type, three entities, two same-source relations, and Shape Batches.
  A distinct malformed Shape dry-run returned `validation_failed`. After the final stable workspace
  receipt, no more mutation call was made: real entity-list, statement-list, batch inventory/details,
  and exact statement lineage reads were used unchanged. The positive verifier returned
  `complete=true`, `expected_triple_count=15`, `fact_subject_count=3`, and
  `relation_source_count=1`.
- **C / proof-copy negatives:** PASS, 24/24 real-response copies fail-closed through native verifier
  error `-32010`: envelope (`ok`, missing/root/extra data), inventory/detail mismatch, a real
  cursor-bearing inventory read, rejected-delta, graph/delta-hash/workspace-chain, relation delta,
  same-subject fact/source graph/forged optional fact ID, entity identity/graph, workspace graph-set,
  read signature/model name, lineage record/target/trace/evidence, and 1000-capacity. No synthetic
  statement cursor was created or asserted.
- **D / cleanup and preservation:** PASS. The Session reached terminal cancellation, Protocol key
  revoke returned 200, Project delete returned 204, and bootstrap key revocation returned true.
  Direct database recheck found zero matching Project, Ontology, Session, active Lease, and Project
  API-key rows. Service remained active; backend `/api/health` was `ok`, frontend was 200; focused
  `test_r23002` (37), full modeling-team discovery (101), scoped Ruff and `git diff --check` passed.
  No Team Runner, ledger action, Attempt14, handoff publication, retained-evidence mutation, restart,
  or commit occurred.
- **Conclusion:** overall **PASS** for the specified Round32 B-D native-MCP preflight. This is a
  verifier/read-contract acceptance result only; it neither authorizes nor starts Attempt14.

### Round 36 — 2026-08-01 B32-06 independent Protocol-only routing acceptance — FAIL

- **A / Attempt14 failed-written scope cleanup:** PASS. The retained state identified Project
  `4f5e1d41-67c3-47e4-94ea-f866f26785b0`, Ontology
  `743b8665-3af8-44e6-bc4e-81af8cd42265`, and Session
  `cbd024b8-a7ea-4ec6-8492-e8198381295d`. A fresh temporary bootstrap admin reread the Session as
  already `cancelled`, confirmed terminal state, deleted the Project (204), and revoked itself.
  Direct DB counts for that Project/Ontology/Session/active Lease/active Project key are all zero.
  The run directory and all Attempt14 evidence were not removed or changed.
- **B / native behavior preflight:** FAIL, **B32-06 High (Protocol native verifier authorization)**.
  In a separate fresh temporary create scope, a bwrap/Codex Protocol Agent had a direct native
  `protocol_mechanics.verify_scoped_retrieval_fallback` positive proof available (`complete=true`)
  and was prompted to first call real bounded ontology-scoped hybrid query then use that unchanged
  proof for the eligible incomplete/degraded/truncated route. Raw app-server elicitation evidence
  records ontology-platform being accepted, then `server_name=protocol_mechanics` being **declined**
  by the runtime. The Adapter's elicitation policy permits only `team_transport` and
  `ontology_platform`, so the Protocol Agent cannot make the required native verifier call.
- **Required behavior not accepted:** therefore the positive route could not demonstrate actual
  `query incomplete -> native verifier complete=true -> successful retrieval receipt`, and the
  verifier-error route could not demonstrate an actual Protocol conflict. Direct host-side native
  verifier success is not substituted for Protocol-Agent behavior.
- **Temporary scope/protection:** the interrupted fixture was stopped and direct DB found zero
  `r23002-r36-native` Projects; its temporary credentials and platform scope were removed. Attempt14
  ledger (`08d7d06bda5b172566b71ea538b21badeeefa211e34cd467bca22948c9157344`), state and every
  retained evidence hash stayed identical. Service remained active, backend health `ok`, frontend
  200, focused `test_r23002` (37) and `git diff --check` passed. No TeamRunner, semantic ledger
  action, new modeling attempt, handoff, restart, or commit occurred.
- **Conclusion:** overall **FAIL**. Fix the Protocol runtime elicitation allow-list to accept the
  required `protocol_mechanics` server for schema-v2 Protocol only, then rerun this same actual
  positive and verifier-error route before accepting B32-06.

### Round 37 — 2026-08-01 B32-07 independent Protocol-only routing acceptance — FAIL

- **Authorization and boundary:** PASS. The real bwrap Protocol turn issued ontology-platform then
  `protocol_mechanics` MCP tool calls; both elicitation requests were accepted. Focused regression
  coverage retains decline for v1 Protocol, v2 Modeling, v2 Coordinator, and unknown servers.
- **Positive behavior:** FAIL, **B32-08 High (Protocol proof preservation)**. The fresh create scope
  produced a real eligible degraded hybrid query (`vector index missing`) and a separately native-
  verified formal fallback proof (`complete=true`). In the actual Agent route, after the accepted
  verifier call, Protocol sent a retrieval-completeness conflict instead of the required success:
  native verifier returned `-32010: retrieval fallback proof failed: workspace is not ready`.
  This differs from the unmodified proof's direct success and proves that the Agent did not preserve
  the supplied full proof exactly when making its native call.
- **Error behavior:** PASS. The second actual Protocol turn called accepted native verifier with an
  invalid proof and returned a Modeling retrieval-completeness conflict (not success), bound to the
  real request delivery.
- **Cleanup/protection:** PASS. Temporary Session/scope/keys/process were stopped and DB found zero
  `r23002-r37-native` Projects. Ledger and every Attempt14 retained state/evidence hash remained
  unchanged; service active, backend health `ok`, frontend 200 and `git diff --check` passed. No
  TeamRunner, ledger action, modeling attempt, handoff, restart, or commit occurred.
- **Conclusion:** overall **FAIL**. Keep the narrow B32-07 authorization repair; separately make
  Protocol transmit the collected fallback proof unmodified, then rerun the same real positive path.

### Round 38 — 2026-08-01 B32-08 independent Protocol-only acceptance — FAIL

- A fresh bwrap Protocol-only fixture was rebuilt without TeamRunner, ledger, budget or semantic
  start. Its direct native verifier baseline passed before the Agent route. The real Agent positive
  turn did not complete within the bounded 50-second collection window, so no full native tools/call
  arguments were available for the required frozen-proof deep-equality assertion and no successful
  retrieval receipt was obtained.
- This is **FAIL**, not PASS: wrapper static contract coverage cannot substitute for the requested
  real positive/error routing and raw-argument evidence. Fixture finally-cleanup ran; do not infer a
  product success from the direct verifier baseline.

### Round 38 diagnostic addendum — 2026-08-01 B32-08 proof-difference recovery — BLOCKED

- The bounded final retry reached a normally completed real Protocol turn and captured the native
  verifier-call boundary. Its sanitized, pre-cleanup diagnostic shows the expected and actual direct
  proof objects have the same ten top-level keys, but are not deeply equal: canonical payload sizes
  are 104443 and 104444 bytes respectively, with distinct SHA-256 digests.
- Structural-diff recovery is **BLOCKED**: the retained diagnostic intentionally persisted only key
  names, byte counts, digests, and equality status; it retained neither object, type map, raw
  arguments, nor business text. The temporary runtime directory was subsequently cleaned. Therefore
  no first or complete differing JSON path, expected/actual type, scalar summary, or collection
  length can be reconstructed honestly.
- No stateful `begin`/`put`/`append`/`verify` proof-collection interface exists in the current
  protocol wrapper. Do not add one merely to repair this narrow test: it would be a new MCP state
  surface beyond B32-08. For the next bounded retry, the test harness should recursively compare the
  in-memory expected and intercepted actual arguments before cleanup, persist at most 20 sanitized
  paths (types, lengths, and redacted scalar digests only), then discard raw arguments.

### Round 38 structural-diff retry — 2026-08-01 B32-08 Protocol-only — FAIL

- A new fresh bwrap Protocol fixture used a 300-second bound and a tester-only observer. It retained
  no proof or message text: for MCP items it persisted only top-level keys, value types, selected
  nested-object keys, and server/tool metadata; any verifier arguments would have been compared only
  in memory and summarized as at most 20 redacted JSON-pointer differences before cleanup.
- The actual item shape was identified, but the completed turn issued only
  `ontology_platform/query_semantic_context`; it issued no
  `protocol_mechanics/verify_scoped_retrieval_fallback` item. Consequently verifier candidates are
  zero, `deep_equal` is unavailable, broker-correlated successful receipt is absent, and there are
  no structural-diff paths to report. This is a routing/execution failure, not evidence that the
  proof is preserved.
- Cleanup passed after the terminal turn: Session terminal confirmation, Protocol key revoke 200,
  Project delete 204, bootstrap-key revocation true, and temporary runtime removal. No ledger,
  semantic start, Attempt14, handoff, baseline, or retained-evidence mutation occurred.

### Round 39 — 2026-08-01 B32-09 independent Protocol-only terminal-gate acceptance — FAIL

- **Code-level gate:** PASS. Focused Codex-isolation/transport/runner/R2.3-002 suites passed 94
  tests; full `modeling_team` discovery passed 108; scoped Ruff, schema-v2 validate and
  `git diff --check` passed. Static review confirms the required completed-item state machine and
  sanitized transition writer are present.
- **A / complete generic path:** INCONCLUSIVE at the real-Agent layer. A fresh deterministic
  temporary fixture used host-native MCP only (no Agent modeling, ledger or semantic start) to
  apply one class and one asserted entity with Evidence. The actual bwrap Protocol completed its
  valid ontology-scoped keyword generic-query item, but its sanitized gate evidence transitioned
  `idle -> fallback_required`, not `complete`; it correctly made no verifier or terminal report.
  The raw response was intentionally not retained, so the precise missing completeness member is
  unavailable. Unit coverage remains the only evidence for complete-without-verifier acceptance.
- **B / terminal gate:** FAIL, **B32-09 High (runtime/infrastructure)**. In a separate fresh fixture
  with the same deterministic setup, an actual completed ontology-scoped hybrid generic-query item
  transitioned `idle -> fallback_required`. Protocol then issued an actual completed
  `team_transport/report_task_result` MCP item. There is no sanitized `terminal_blocked` transition,
  no fixed gate-rejection callback record, no verifier completed item and no accepted broker result.
  Production `team_transport` is the agent-local stdio MCP server; its normal MCP item path does not
  traverse Adapter `_team_transport_dynamic_result`, where the B32-09 guard was placed. Thus the
  real route cannot prove the mandated pre-broker gate and is disconnected from it.
- **Cleanup and preservation:** temporary App Servers/brokers/scopes were stopped. Each Project
  delete returned 204, Protocol-key revoke 200, bootstrap revoke true, terminal-session check true,
  and direct DB residual counts for Project/Ontology/Session/active Lease/active Project key were
  all zero. The explicit direct Session-cancel call returned 422, but the terminal helper and Project
  cascade left zero rows. Ledger and Attempt14 state hashes remained unchanged. No TeamRunner,
  budget/ledger/semantic start, handoff or retained-evidence mutation occurred.
- **Conclusion:** overall **FAIL**. Bind the terminal verifier gate to the real agent-local
  `team_transport` MCP execution path (or route that server through the Adapter guard), retain only
  sanitized result evidence, then repeat B before retesting the real complete generic path. Do not
  authorize a budget/baseline/start from this round.

### Round 44 — 2026-08-01 B32-10 independent Broker-bound terminal-gate retest — INCONCLUSIVE

- **Code-level:** PASS. Focused isolation/transport/runner/R2.3-002 suites passed 99 tests; full
  `modeling_team` discovery passed 113; scoped Ruff, schema-v2 validate and `git diff --check`
  passed. This includes normal stdio and legacy dynamic callback deadlock/ordering regression.
- **B / production terminal gate:** PASS. A fresh Protocol-only bwrap fixture reused the prior
  host-native minimal Evidence-backed class/entity setup without TeamRunner, ledger/budget, Agent
  modeling or semantic start. Sanitized completed-item and gate evidence has this order: eligible
  ontology-scoped generic query completed; `idle -> fallback_required`; first normal agent-local
  `team_transport/report_task_result` item failed, `terminal_blocked` was recorded, and Broker had
  no Protocol result; an actual `protocol_mechanics/verify_scoped_retrieval_fallback` item then
  failed (a permitted completed attempt); finally a later normal report completed and Broker recorded
  Protocol `blocked`. The observer deliberately does not retain error text; the fixed Broker error
  is bound by the actual failed report plus the `terminal_blocked` transition (emitted only by the
  guard) and zero pre-guard Broker mutation.
- **A / complete generic path:** INCONCLUSIVE. A second fresh scope used the unchanged setup and
  completed the valid keyword query without verifier. Its in-memory-only sanitized checklist finds
  `formal_success=false`; therefore result status, recall, truncation/pages/cursors, scope, lineage
  and warning requirements cannot be positively established, and adapter completeness is false.
  No terminal report was sent or accepted. Raw result content was discarded as required. This is an
  actionable platform/MCP envelope gap, not evidence of a complete path.
- **Cleanup/preservation:** both temporary scopes stopped their App Servers/brokers and removed run
  directories; Protocol revoke was 200, Project delete 204, bootstrap revoke true, terminal check
  true, and direct DB counts for Project/Ontology/Session/active Lease/active Project key were zero.
  Direct Session cancel returned 422 before terminal cleanup, but no residual Session remained.
  Ledger and Attempt14 hashes were unchanged. No baseline, budget, semantic start, handoff or
  retained-evidence mutation occurred.
- **Conclusion:** overall **INCONCLUSIVE**; B32-10 B is accepted, but the A complete generic path
  still lacks a real formal envelope. Do not create a baseline until A is repaired/reproven; do not
  rerun B without a changed A-capable platform condition.

### Round 45 — 2026-08-01 A-envelope diagnostic and acceptance-gate correction

- The one permitted A-only diagnostic confirmed the actual App Server shape is
  `item.result.structuredContent` with keys `ok,error,error_code`; Runtime extracts the correct path,
  but the temporary environment returned `ok=false`. A remains **INCONCLUSIVE**, not PASS, and no
  complete generic or terminal evidence is claimed.
- Independent gate review **APPROVES THE NEXT BASELINE** and supersedes only Round44's “do not create
  a baseline” recommendation. Generic complete and native-verifier complete are alternative success
  paths. The current environment is known to enter fallback, and production B already proves the
  actual stdio/Broker enforcement needed for that path. Requiring both alternatives would promote a
  non-applicable branch into a new prerequisite contrary to staged minimal acceptance.
- This is not a retrieval waiver. The next real producer must obtain actual native-verifier
  `complete=true` and correlated Protocol success on the applicable fallback path; otherwise the
  run remains blocked/failed. Preserve A as deferred/non-applicable for this baseline and retain all
  Round44/45 evidence and cleanup results unchanged.

### Round 45 — 2026-08-01 A-envelope structural diagnostic — INCONCLUSIVE

- One fresh Protocol-only bwrap A fixture reused the unchanged minimal host-native Evidence/lineage
  setup and did not run B. The actual completed generic-query item's safe structure is
  `item.result: object` with keys `_meta`, `content`, `structuredContent`; its text content parses as
  a JSON object with the same top keys as `structuredContent`.
- The runtime extractor path **matches** the actual shape: `item.result.structuredContent` is an
  object with keys `ok`, `error`, and `error_code`, so there is no B32-10 extractor-shape mismatch.
  It reports `ok:false`; the only permitted retained error datum is `error_code=null`. Raw error,
  text and result payload were discarded. Consequently every positive generic-completeness member
  remains unavailable/false and no no-verifier terminal report was sent.
- Cleanup passed: adapter/broker stopped, Protocol revoke 200, Project delete 204, bootstrap revoke
  true, terminal-session check true, DB Project/Ontology/Session/active-Lease/active-key residuals
  all zero. Direct Session cancel was 422 before terminal cleanup but no row remained. Ledger and
  Attempt14 hashes were unchanged; no TeamRunner, budget, semantic start, handoff or retained
  evidence mutation occurred.
- **Conclusion:** A remains **INCONCLUSIVE**, now with a precise formal platform failure rather than
  an unknown envelope shape. Do not retry the fixture; diagnose the query's `ok:false` response by
  its platform-side safe error code/trace under separately authorized diagnostic scope.

### Round 46 — B32-11 Protocol contract repair plan

- Preserve Attempt15 q as a formal `platform-contract` failure with
  `complete_modeling_quality_result=false`; do not alter its ledger, evidence, budget or history.
- Contract tests must prove the Protocol-private reference and instructions require a Shape-bound
  object predicate to be a `create_property(object_class_id)`, bind the relation predicate to that
  formal `/property/{id}` output, and reject the divergent `/relation-type/{id}` plus
  `/property/{same-id}` combination before write. A compiler fixture must demonstrate both matching
  property binding and the distinct relation-type counterexample.
- Wrapper tests must prove `tools/list` declares `mode.enum == ["create"]`, local argument
  validation rejects `fresh_create` with `-32602` without invoking the native verifier, and valid
  direct `create` arguments retain identity when passed through. Run only focused wrapper/R2.3-002,
  scoped Ruff and `git diff --check`; no real run, ledger action, cleanup, restart or commit.

### Round 46 — 2026-08-01 B32-11 independent requirement test — PASS

- **Scope executed:** the plan's Protocol-private reference/instruction contract; the actual
  `ModelingCommandHandlerRegistry.prepare` compiler fixture; and the
  `protocol_retrieval_mcp` JSON-RPC wrapper. No TeamRunner, platform write, native MCP verifier,
  ledger/budget/baseline mutation, cleanup, service restart, or commit was performed.
- **C1 — object-property/Shape/relation contract: PASS.**
  `R23002Tests.test_object_property_relation_and_shape_path_binding_is_protocol_explicit` confirmed
  that the reference and Protocol instructions require `create_property(object_class_id)`, use its
  formal `/property/{id}` `resource_iri` for `create_relation`, use the same property
  `resource_id` for Shape `path_id`, and prohibit the same-predicate `create_relation_type`
  combination.
- **C2 — compiler positive and counterexample: PASS.** The same executed fixture calls the real
  semantic command registry: it asserted `sh:path == <property_iri>` and that the compiled
  `create_relation` predicate equals that path. With the same ID passed to
  `create_relation_type`, its formal IRI and resulting relation predicate were asserted unequal to
  the Shape's `/property/{same-id}` path. This is the required divergent
  `/relation-type/{id}` versus `/property/{id}` counterexample.
- **C3 — retrieval-wrapper closed mode: PASS.** `tools/list` exposed exactly
  `mode.enum == ["create"]`; a `fresh_create` call returned `-32602` and the mocked native verifier
  was asserted not called; a valid direct `create` object was forwarded by identity to the verifier.
- **Commands and evidence:** an initial targeted unittest command used a stale class name and failed
  at test discovery only; no product assertion ran. The corrected R2.3-002 module run passed
  **38 tests**; the three wrapper-focused tests passed; complete
  `unittest discover -s modeling_team/tests` passed **114 tests**; `ruff check modeling_team` and
  the B32-11-file scoped Ruff check passed; v2
  `python -m modeling_team validate --profile modeling_team/profiles/base-three-agent.yaml --task
  modeling_team/tasks/new-scope-business-slice.yaml` returned the expected profile/task/roster;
  final `git diff --check` passed.
- **Conclusion:** PASS. No B32-11 defect found. The scope intentionally does not re-run Attempt15
  or establish a new semantic-modeling baseline; its preserved `platform-contract` failure remains
  outside this contract-repair test.

### Round 47 — reviewed closure plan for `r23002-real-20260801r`

- **P0 provenance gate (independent, read-only):** hash and freeze the exact original formal
  `initial_modeling_context` from `r`; recover `candidate_required_assertions` only when one
  attributed Modeling candidate delivery is uniquely correlated to Protocol evidence. Verify the
  recovered objects are passed unchanged, while final context/workspace/Batch/read/lineage objects
  are fresh read-only responses. Missing, duplicate, uncorrelated, or digest-drifting source is
  **INCONCLUSIVE** and stops before classification, tranche, authorization, reservation, or start.
  A synthetic zero context or inferred assertion selection is a test failure.
- **P1 failed-run closeout:** after P0, reread admin ownership, workspace, Session, all Attempts and
  Lease; reject `applying`/`recovering`. Append the immutable terminal classification before cleanup
  proof. If needed, save one failure checkpoint at the current returned revision, cancel with its
  returned revision, reread cancelled/released state, revoke the old model key by ID, and read that
  key plus every temporary admin key. Verify non-secret evidence is frozen before destroying all
  runtime `auth.json`, private `config.toml`, and temporary credentials. Assert no reacquire,
  complete, or separate release call occurs.
- **P2 independent lifecycle gate:** before repair authorization, a tester passes a no-semantic-start
  monitor-start → continuously monitored producer-command lifecycle → monitor-stop → secret-
  destruction proof. The monitor must remain attached through terminal/cleanup and across parent/PM
  turn boundaries. The test creates no Platform scope/key/Session/Lease, ledger reservation, or
  semantic start.
- **P3 ledger/order gate:** verify precisely `r` terminal classification → `r` cleanup proof → one
  unique tranche 8 `+2` → independent P2 repair evidence → fresh baseline plus repair authorization
  → fresh reservation/start. Any duplicate tranche, authorization before P2, or start before a
  reservation fails closed.
- **P4 fresh acceptance order:** observe completed and settled Coordinator/Modeling/Protocol; then
  Session/Lease/key/runtime-secret cleanup; then freeze evidence; then Phase A PASS by the same
  independent tester; then deterministic handoff publication; then that tester's fresh Session
  Phase B; only both phases PASS permit final PASS. A producer summary, cleanup claim, or handoff
  cannot substitute for an earlier required observation.
- **F1 Terra configuration audit:** no Profile/package/runtime change is planned. Parser and Codex
  launch tests must continue to show that there is no supported model/reasoning-effort field; the
  closure plan therefore explicitly does **not** switch to `gpt-5.6-terra`/`xhigh`. Any future switch
  requires a separately reviewed runtime-interface implementation, profile mapping, launch mapping,
  and regression/real-runtime evidence.

### Round 48 — planned settled closure and narrow repair evidence

This is a new planned round. Rounds 1–47 remain immutable history; this entry clarifies and
supersedes only the active closure order and repair contract. No code, runtime, ledger, key, Session,
or delivery-record mutation is part of the plan revision.

#### P0 provenance disposition

The tester first performs a read-only provenance check. The original zero initial formal envelope is
recoverable and must be frozen with canonical SHA-256
`4e66b6d21d4b8e9cff9c279d965b638d8dd849a25a692b964a04d1e80ad3a50f`. The unique
`candidate_required_assertions` artifact is missing. P0 therefore blocks PASS for `r` and blocks
repair authorization/new-producer start until that artifact is repaired, but it does not block the
mandatory terminal classification or failed-run closeout. No synthetic zero envelope or inferred
required-assertions selection is accepted.

#### One immutable terminal classification

After freezing the non-secret provenance/gap evidence, append exactly one `terminal_failure` for `r`:

```text
failure_category=runtime/infrastructure
complete_modeling_quality_result=false
```

The causal evidence is fixed to the recoverable validation errors from `max_depth=10` lineage calls
at `00:14:46-00:14:47`, active Protocol/Modeling turn interruption at `00:14:48`,
`report_task_result` call count `0`, `state=PAUSED`, and later disappearance of run-specific
processes without normal cleanup. Max-depth, missing candidate, and verifier issues are retained as
secondary unresolved facts in the failure checkpoint; none changes the terminal category.

#### Mandatory closeout test and evidence order

The tester checks this exact order and direct evidence:

1. Freeze non-secret failed-written scope, raw event/receipt references, P0 digest, and unresolved
   gap list.
2. Append the one terminal failure above; no second or replacement classification is allowed.
3. Reread admin ownership, Project/Ontology, workspace, Session, every Attempt, and Lease; prove no
   Attempt is `applying` or `recovering`.
4. **Must** save one failure checkpoint at the current revision returned by step 3. The checkpoint
   reason is the runtime/infrastructure failure and it names unresolved candidate, lineage,
   verifier, and process-loss items.
5. Cancel using the checkpoint's returned revision, then reread `cancelled` Session and released
   Lease. Assert no reacquire, completion, or separate Lease-release call.
6. Enumerate and revoke the old Project model key by exact ID, then every temporary/bootstrap
   admin/read key. Retain direct per-key revocation proof.
7. Retain the non-secret failed-written scope and evidence; it is not a handoff candidate.
8. Destroy all three role/runtime `auth.json` files, private `config.toml` files, and temporary
   credentials; prove absence directly after the evidence freeze.

Any missing closeout observation is a recorded gap, not permission to alter the category or claim
cleanup. The old run remains non-PASS while P0 or closeout evidence is incomplete.

#### Candidate-required-assertions/v1 test contract

Use a platform-neutral, non-business candidate fixture and verify that Modeling owns a **nonempty**
required-statement list. The immutable candidate revision includes the originating `delivery_id`,
the exact `reply_to_delivery_id` chain, a canonical digest, and the statements. Protocol must carry
that same frozen revision after receipts into a nonempty, duplicate-free canonical asserted-data quad
set. Each quad has one computed fact ID and exactly one matching full lineage response; every lineage
response binds the same quad, Ontology, graph, and digest. `max_depth` accepts only integers `0..5`.
The fixture must fail closed for an empty list, duplicate quad/fact ID, extra or unbound lineage,
missing lineage, wrong graph/Ontology, and revision/digest drift. Delivery is limited to mechanical
correlation and must not select assertions.

The native verifier must reject a vacuous `mode=create` proof. A verifier `complete=true` is valid
only when a real eligible `fallback_required` retrieval episode was observed and the native verifier
item completed; a verifier error or `complete=false` is not success. A direct generic-query
`complete=true` path remains the alternative success path and must be accepted without a verifier.

#### Two independent no-semantic-start repair tests

- **P2-monitor:** start a continuous monitor before a harmless monitored producer-command lifecycle,
  keep it attached through terminal/cleanup and parent/PM turn boundaries, stop it only after the
  command lifecycle, and prove secret destruction. Freeze the exact monitor command/argv, opened
  descriptor contract, `modeling_team/foreground_monitor.py` SHA-256, lifecycle timestamps, and
  append-only evidence path.
  Assert no business source, Project, Ontology, key, Session, Lease, StartLedger record, or semantic
  start exists.
- **P2-Protocol:** through the production Adapter, bwrap, private config, app-server, and native MCP,
  create a minimal ephemeral Project/Ontology/key/Session/Lease and exercise the candidate,
  lineage, max-depth, duplicate/drift, native `mode=create`, and eligible-fallback verifier contract.
  Use no business source, StartLedger, or Producer semantic start. Revoke keys, cancel/complete as
  contractually required, release Lease, delete the ephemeral Project, destroy temporary secrets,
  and query direct residual counts to prove zero state.

The minimal repair baseline-manifest delta is limited to the monitor command/argv/descriptor,
the `modeling_team/foreground_monitor.py` and
`modeling_team/references/p2-monitor-contract.json` SHA-256 values, lifecycle/evidence path, and the Protocol candidate/verifier fixture,
production launch, and tool-schema hashes. After both P2 tests pass, generate a fresh `baseline-1`,
then regenerate a fresh `baseline-2` from the clean tree; canonical manifests and hashes must match
exactly. Any unexpected delta fails closed. Before any later implementation edits, the implementer
must run GitNexus upstream impact analysis per AGENTS.md and warn on HIGH/CRITICAL risk; no code edit
is authorized by this documentation round.

The focused repair set is C37 (verifier/fallback gate), C38 (monitor operating unit), C39 (production
Protocol preflight and zero residuals), and C40 (minimal manifest delta and repeatability); it must
run without a TeamRunner reservation, business source, or semantic start.

#### Exact sequence gate

Round 48 passes only if the evidence order is exactly:

`r` terminal classification -> `r` mandatory closeout -> independent P2 monitor **and** P2 Protocol
repair evidence PASS -> unique continuing-authorization tranche 8 `+2` -> two fresh matching
baselines -> repair authorization -> reservation/start -> fresh producer's three Agents completed
and settled -> successful Session/Lease/key/runtime-secret cleanup and evidence freeze -> same
independent tester Phase A PASS -> deterministic handoff -> that tester's fresh Session Phase B ->
final repository/runtime/requirement gates.

No earlier tranche, authorization, baseline binding, reservation, or semantic start is valid. F1 is
retained: no Team model/reasoning switch is attempted because no supported configuration surface
exists and it is outside the narrow repair.

**Planned result:** not executed in this documentation revision; ready for plan re-review.

### Round 49 — planned accepted-High correction: proof, lifecycle, transport, and baseline

Round 48 is retained as historical plan text. This Round 49 entry is the current active correction
for the five accepted High findings and remains unexecuted; it does not authorize code, runtime,
ledger, key, Session, or semantic-start work.

#### H1 — platform-neutral Modeling candidate and canonical digests

The Modeling candidate uses exactly this semantic statement shape and never includes a platform graph
IRI or platform-generated ID:

```json
{
  "graph_role": "asserted_data",
  "subject": "<semantic subject>",
  "predicate": "<semantic predicate>",
  "object": "<semantic object>",
  "object_kind": "<iri|literal|...>",
  "object_datatype": null,
  "object_language": null
}
```

The two optional terms are always present as a string or JSON `null`; unknown fields, any
`source_graph_iri`, and all platform IDs fail closed. Canonical JSON is UTF-8 encoded
`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, with no whitespace.
Sort statements lexicographically by their canonical JSON UTF-8 bytes and reject duplicate bytes. The
semantic payload is exactly
`{"schema_version":"candidate-required-assertions/v1","statements":[<sorted items>]}`;
`semantic_digest` is SHA-256 over its canonical JSON UTF-8 bytes.

The candidate binding payload is exactly the canonical object containing
`schema_version`, `candidate_revision`, `delivery_id`, ordered `reply_chain`, and `semantic_digest`;
`candidate_digest` is SHA-256 over that UTF-8 canonical JSON. Protocol alone resolves
`graph_role=asserted_data` to the final workspace `source_graph_iri` after formal receipts, creates
sorted exact materialized quads, and computes `materialized_digest` as SHA-256 over canonical JSON of
`{"candidate_digest":<digest>,"quads":[<sorted exact quads>]}`. It computes fact IDs from those
quads. The tester recomputes all digests and rejects any semantic or binding drift.

#### H2 — exact ten top-level proof fields and strict nested shapes

The native verifier input has exactly this top-level set, with no `proof` wrapper or extra member:

```text
mode, initial_modeling_context, final_modeling_context, workspace_context,
batch_inventory, batch_details, entities_read, statements_read,
candidate_required_assertions, statement_lineage
```

`candidate_required_assertions` is a strict object containing the shared metadata/bindings
(`schema_version`, `candidate_revision`, `delivery_id`, `reply_chain`, `semantic_digest`,
`candidate_digest`), nonempty sorted platform-neutral `items`, `materialized_digest`, and nonempty
sorted `materialized_quads` with the resolved `source_graph_iri`. `statement_lineage` is a strict
object containing the same metadata/materialized bindings, integer `max_depth` in `0..5`, and
nonempty `records`; each record contains a computed fact ID, exactly one matching materialized quad,
and one full `{ok:true,data:<lineage>}` response. Wrapper and verifier reject missing/extra nested
members, empty/duplicate/unbound records, wrong graph/Ontology, fact/quad mismatch, out-of-range
max-depth, and any revision/chain/digest mismatch.

The focused implementation tests explicitly target `modeling_team/protocol_retrieval_mcp.py` and
`modeling_team/protocol_mechanics.py`: tools/list exposes the ten direct arguments, nested shape
validation is strict, and positive/negative calls prove no top-level expansion. This proof is used
only after an observed eligible `fallback_required` episode; direct generic `complete=true` remains
the alternative success path.

#### H3 — same prospective run ID, same files, two pre-start manifests

After P2 passes and the unique tranche-8 `+2` record, select one fresh prospective run ID. Compute
`_baseline_manifest` twice with that exact same ID and exact same stable file set, before any
reservation or semantic start. Neither computation may write StartLedger or create/read ephemeral
scope, key, Session, Lease, fixture, evidence, or PID state. Compare every manifest entry and final
hash byte-for-byte; omission, addition, reordering, or drift fails closed. The run ID is an identical
external binding argument, not a stable-file entry; no ephemeral value may enter the manifest digest.

#### H4 — P2 monitor must exercise the real foreground lifecycle

The P2 monitor starts before and remains attached through the real foreground
`TeamRunner -> CodexRuntimeAdapter -> app-server -> Team Transport/Broker -> ordered settlement ->
secret cleanup` lifecycle, across at least one parent-PM turn boundary. It stops only after all three
terminal/settlement observations and secret-absence proof. Exact command/argv, descriptor ownership,
lifecycle states, boundary marker, and the SHA-256 of
`modeling_team/foreground_monitor.py` are read from stable
`modeling_team/references/p2-monitor-contract.json` together with its own SHA-256 and append-only
evidence path.

Use the closest accepted R2.3-001 nonbusiness smoke, `modeling_team/profiles/base-three-agent.yaml`
with `modeling_team/tasks/base-capability-smoke.yaml`, or an equivalent production-lifecycle fixture.
This cannot count as an R2.3-002 semantic start: it is schema-v1 mechanics-only, carries no
R2.3-002 business source or candidate, prohibits Modeling Items/Batch/Build Session/Lease, and does
not reserve or mark StartLedger semantic start. If the real path requires owned ephemeral auth/config
or other resources, create and fully clean those resources under this P2 test's ownership and retain
direct API/database zero-residual proof.

#### H5 — P2 Protocol must prove production transport correlation and zero residuals

Before native verification, send a synthetic nonbusiness Modeling candidate through the real
`TeamTransportBroker`/production stdio path. Retain one exact `delivery_id`, ordered
`reply_to_delivery_id` chain, Protocol receipt, and terminal handoff. A byte-equivalent production
stdio path is acceptable only if it preserves these envelope bytes and broker correlation checks; a
direct in-process function call is not evidence.

Through the production Adapter, bwrap, app-server, and native MCP verifier, explicitly create and
list by ID a bootstrap-admin key, a read-only key, a Protocol key, and any required Project model
key. Exercise the candidate/materialization/lineage contract, `mode=create` vacuous rejection, and
eligible-fallback completion. Revoke every recorded key ID directly, settle/cancel the Session,
release the Lease, delete the owned temporary Project/Ontology, destroy secrets, and prove via both
API reads and direct database residual counts that temporary Project/Ontology/Session/Lease/key rows
are zero. No business source, StartLedger semantic start, or Producer semantic start is allowed.

#### H6 — exact stable baseline files and omission/drift tests

The planned `_baseline_manifest` update hashes only these stable code/descriptor/schema inputs:

```text
modeling_team/runner.py
modeling_team/contracts.py
modeling_team/protocol_mechanics.py
modeling_team/protocol_retrieval_mcp.py
modeling_team/protocol_mcp_launch.py
modeling_team/transport_mcp.py
modeling_team/runtimes/codex.py
modeling_team/agent-packages/modeling/instructions.md
modeling_team/agent-packages/protocol/instructions.md
modeling_team/references/candidate-required-assertions-v1.json
modeling_team/references/native-retrieval-proof-v1.json
modeling_team/references/p2-monitor-contract.json
```

The candidate descriptor freezes semantic field scope and digest algorithms; the native proof
descriptor freezes the ten top-level/nested schemas; and the monitor descriptor freezes command/argv,
descriptor ownership, lifecycle states, boundary marker, and evidence handoff.

The existing modeling-batch item contract, Profile, Task, Skills, and source entries remain governed
by the prior baseline rules. Tests extend `modeling_team/tests/test_runner.py` and
`modeling_team/tests/test_r23002.py` to prove every listed file is present, omission/addition/byte
drift fails closed, and two calls with the same prospective run ID and file set are identical.
Runtime tests must prove that test fixtures, evidence, runtime directories, credentials, descriptor
file descriptors, and PIDs are excluded. The monitor command/argv and lifecycle contract must be
loaded from the stable descriptor, never generated from an ephemeral fixture.

#### Round 49 focused cases and sequence

Round 49 focuses C43 (canonical semantic/candidate/materialized digest), C44 (exact ten-field and
nested proof schema), C45 (same-run double baseline before reservation), C46 (real foreground P2
monitor across a parent-PM boundary), C47 (real Broker correlation and key/resource zero-residual
proof), and C48 (stable baseline file omission/drift). The required order remains:

`r` terminal classification -> `r` mandatory closeout -> P2-monitor and P2-Protocol PASS -> unique
tranche 8 `+2` -> two same-ID matching baselines -> repair authorization -> reservation/start ->
three Agents completed/settled -> success cleanup/evidence freeze -> same tester Phase A -> handoff
-> Phase B -> final gates.

**Planned result:** not executed; ready for plan re-review.

### Round 53 — 2026-08-01 independent Round52 implementation test — FAIL

- **Frozen test state:** tested the parent-supplied stable dirty-worktree target
  `f1498c7b3d6a9714ce8468afd42f5c4615884bf3cc1d969a83a4fc5fc3eef55c`, excluding the unrelated
  `AGENTS.md` and `CLAUDE.md` edits. The tester changed no product file and did not edit the delivery
  record. Backend health was `ok`, frontend returned 200, and `ontology-platform.service` was active
  before and after the test.
- **C43--C58 local regression: PASS.** Focused strict nested-candidate/native-proof positive plus
  empty, duplicate, unbound, digest, graph, max-depth, and extra-field negatives passed. The wrapper
  exposes the exact ten plural top-level fields. `PlatformScope` covers two-stage project-key/admin
  evidence, DELETE-exception `finally` admin revoke, and Session cancel/auto-Lease-release without a
  second explicit release. The monitor descriptor/append-only evidence/secret-cleanup tests passed.
  Commands: focused unittest group **14 PASS**; focused backend asserted-data graph binding
  **24 PASS**; full `unittest discover -s modeling_team/tests -p 'test_*.py'` **117 PASS**; `ruff
  check modeling_team backend/app/services/semantic_read_model.py
  backend/app/services/semantic_sparql_templates.py
  backend/tests/test_semantic_read_model_stage2_execution.py`, schema-v1/schema-v2 validation,
  reference JSON parsing, and `git diff --check` all passed. Required backend regression from the
  repository `backend/` directory passed **821 tests, 10 skipped**. An initial root-directory
  `pytest -q` collection was discarded as environment-invalid because it recursively collected
  preserved historical runtime plugin caches and raised 19 same-module import mismatches; no product
  test assertion failed, and the repository-prescribed backend-directory command passed.
- **C48 same prospective ID double baseline: PASS.** Two pre-start `modeling_team baseline` calls
  for the same new prospective ID produced the identical hash
  `c6d91bc9d9502e3e8b1fa97e678c5bcb722bdc1db891ef06c609dffcf061887f` without a ledger action or
  platform scope creation.
- **C59 / real P2-monitor: FAIL (High, collaboration/routing).** The owned no-business run
  `r23002-p2m-round53-anrawb` used the reviewed monitor, schema-v1 base profile and capability-smoke
  task through the real foreground CLI, TeamRunner, Codex Adapter, app-server, bwrap and Broker. It
  observed Modeling-to-Protocol health delivery, one Coordinator outer-supplement forwarded to both
  peer roles, Protocol's correlated reply, and real Modeling `terminal-result-handoff` to Protocol
  and Coordinator. Protocol then completed an actual app-server turn but never emitted its terminal
  result; after a bounded no-progress wait, the run remained `RUNNING` with six deliveries and only
  the two Modeling handoff records. Thus Protocol terminal, Coordinator retry, acknowledgement and
  all-agent settlement were not observed and this cannot be accepted as the required P2-monitor
  proof.
- **P2-monitor cleanup: PASS.** The tester interrupted only that owned foreground Runner (exit 130),
  which executed its normal cleanup. Retained safe artifact
  `workspaces/modeling-runs/r23002-p2m-round53-anrawb/state.json` reports `CLEANED`, all three
  private credentials destroyed, Session terminal/Lease auto-release, project Protocol key revoked,
  active bootstrap admin before DELETE and revoked after DELETE, Project/Ontology absence, and zero
  Project/Ontology/Session/Lease/active-project-key residuals. Monitor evidence at
  `/tmp/r23002-round53-p2-monitor-AnRAWb/evidence/p2-monitor.jsonl` contains the six descriptor
  stages and one parent-PM boundary. No R2.3-002 StartLedger reservation, `semantic_start`, business
  source, retained product scope, manual terminal sender, or TeamRunner use outside this monitor path
  occurred.
- **C60 / real P2-Protocol: BLOCKED.** The implementation/repository supplies only local verifier
  and adapter tests; it has no executable TeamRunner-free production P2-Protocol fixture/driver that
  constructs the required schema-v2 `start_roster` plus real Broker/stdio/bwrap/app-server/native-MCP
  candidate/reply/query/fallback/verifier sequence. Creating one ad hoc would be new test-harness
  design rather than execution of the reviewed Round52 implementation. It was therefore not replaced
  by a direct verifier or local mock, and no claim of Protocol terminal, Runner handoff, ack, or
  all-three settlement is made.
- **Historical-state evidence:** post-test SHA-256 values were StartLedger
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431` and preserved old-run state
  `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`. A tester pre-run hash was not
  captured at the stable-state handoff, so unchanged-history is not promoted beyond the direct fact
  that this v1 P2 execution made no StartLedger call.
- **Conclusion:** FAIL. Local gates and cleanup pass, but the real P2-monitor could not reach the
  required Protocol terminal/ack/all-agent settlement, and the required real P2-Protocol execution
  is BLOCKED by the missing reviewed production driver. Do not authorize tranche 8, a new baseline,
  repair start, or semantic start. A Requirement Developer should first diagnose the real Protocol
  terminal-report stall and provide the reviewed TeamRunner-free P2-Protocol execution fixture; then
  rerun this same plan as a new independent round.

### Round 50 — planned final boundary, schema, ordering, and external-binding correction

Round 49 remains historical plan text. This Round 50 entry records the active correction and is not
executed; Round 51 below supersedes it only for P2 path execution and deletion cleanup while retaining
its schema, digest, baseline, external-binding, and ordering rules. It does not authorize
implementation, runtime mutation, ledger/key/Session changes, semantic start, or delivery-record edits.

#### P2 boundary, cleanup, and key-history assertions

P2 delivers no business source, creates no R2.3-002 StartLedger reservation or `semantic_start`, and
retains no product Project/Ontology. P2-monitor is the only foreground/TeamRunner path; P2-Protocol is
TeamRunner-free and uses the production Adapter/Transport path specified by Round 51. When either real
path actually requires platform state, the P2 test may create one uniquely owned ephemeral
Project/Ontology, bootstrap-admin key, read key, model-or-Protocol key, Build Session, and Lease.
Before deleting that Project it must freeze a first-stage artifact covering every project-scoped
read/model/Protocol key exact ID, `revoked_at`, non-active proof, cancelled Session, Lease auto-release,
ownership, cleanup receipts, and no in-flight Attempt; record the org-scoped bootstrap-admin key exact ID as `ACTIVE`
solely for the upcoming authenticated DELETE and exclude it from first-stage non-active assertions.
Use that active org-admin credential for DELETE, verify Project/Ontology absence, project-scoped active
residuals zero, and FK cascade behavior, immediately revoke it, and freeze second-stage exact ID,
`revoked_at`, non-active proof, and retained org-admin audit row. Aggregate both artifacts and prove
every created key ended non-active. Existing FK may cascade-delete project-scoped key/Session/Lease rows
after deletion; they need not remain, and no migration/archive/detach/history-retention productization
is added. No new deletion credential, direct DB delete, or hard-delete is allowed. The org-scoped
bootstrap-admin revoked audit row with `project_id=NULL` remains and is never hard-deleted. Acceptance
requires the staged terminal/revocation evidence, post-delete Project/Ontology absence, and zero active
Project/Ontology/Session/Lease/key residuals. This supersedes Round 48's literal zero-scope/key wording
and Round 50's generic history-retention wording.

#### Exact candidate and native proof schema

The platform-neutral Modeling item field set is exactly:

```text
graph_role, subject, predicate, object, object_kind, object_datatype, object_language
```

`graph_role` must equal `asserted_data`; datatype/language are string or JSON `null`; source graph
IRIs, platform IDs/IRIs, fact IDs, workspace versions, receipt fields, and unknown fields fail
closed. Canonical serialization is UTF-8
`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, with no whitespace.
Items sort lexicographically by canonical JSON UTF-8 bytes and duplicates fail. The exact semantic
digest input is `{"schema_version":"candidate-required-assertions/v1","statements":[sorted
items]}`. The exact candidate binding fields are `schema_version`, `candidate_revision`,
`delivery_id`, `reply_chain`, and `semantic_digest`; `candidate_digest` hashes their canonical JSON,
preserving reply-chain order.

After formal receipts/reads, Protocol alone maps `graph_role=asserted_data` to the final
`source_graph_iri` and emits materialized quads with exactly:

```text
graph_role, source_graph_iri, subject, predicate, object, object_kind, object_datatype, object_language
```

They use the same canonical ordering; `materialized_digest` hashes exactly
`{"candidate_digest":<digest>,"quads":[sorted materialized quads]}`. Fact IDs are computed by
Protocol/verifier, never supplied by Modeling.

The native proof has exactly these ten top-level fields, no `proof` wrapper, and no extra member:

```text
mode, initial_modeling_context, final_modeling_context, workspace_context,
batch_inventory, batch_details, entities_read, statements_read,
candidate_required_assertions, statement_lineage
```

`candidate_required_assertions` has exactly
`schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
items, materialized_digest, materialized_quads`; both arrays are nonempty and sorted. Its items use
only the platform-neutral field set, while materialized quads use the resolved graph field set.
`statement_lineage` has exactly
`schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
materialized_digest, max_depth, records`; `max_depth` is an integer `0..5`. Each record has exactly
`fact_id, quad, response`; `response` is the full unprojected `{ok:true,data:<object>}` lineage
envelope. One record/fact ID/quad/lineage response is one-to-one. Wrapper/verifier negative tests
cover missing/extra/empty/duplicate/unbound/wrong-graph/mismatched members, digest/revision/chain
drift, max-depth bounds, and vacuous `mode=create`. Direct generic `complete=true` remains the
alternative producer path; this proof is fallback-only.

#### Actual fallback sequence and external raw-envelope binding

The P2-Protocol fixture must observe this exact order:

`real Modeling synthetic candidate delivery -> Protocol correlated receipt/reply -> platform
materialization/reads -> real completed eligible ontology-scoped query_semantic_context item ->
sanitized retrieval-state fallback_required -> later native verifier mode=create complete=true ->
Broker terminal guard/report acceptance -> Protocol runtime cleanup`.

The observer must retain the actual app-server query item and sanitized retrieval-state transition.
Verifier-before-query, a verifier without prior `fallback_required`, any Modeling-terminal/Runner-
handoff/all-three-settlement claim from this fixture, or manual `sender_id='runner/terminal-result'`
is FAIL. A direct native verifier call by itself is not acceptance evidence. If the real producer
obtains direct generic `complete=true`, that remains a valid alternative producer success path, but the
P2 fixture must exercise fallback only through Broker guard/report acceptance. The final fresh Producer
must separately prove `candidate/receipt/query/verifier -> Modeling terminal -> real Runner
terminal-result-handoff/ack -> Protocol terminal -> all three completed+settled`.

The independent observer compares nested candidate `delivery_id`, ordered `reply_chain`,
`candidate_revision`, `semantic_digest`, and `candidate_digest` against the raw Team Transport/Broker
Modeling envelope and Protocol receipt, retaining only safe IDs/digests. A fabricated self-consistent
new ID/digest that does not match Broker evidence fails; Delivery never selects assertions.

#### Real foreground monitor and stable baseline

The persistent monitor implementation is the concrete file `modeling_team/foreground_monitor.py`; its
descriptor has the exact v1 fields/values `schema_version="p2-monitor-contract/v1"`,
`command="uv"`, `argv=["run","--project","backend","python","-m",
"modeling_team.foreground_monitor","--contract",
"modeling_team/references/p2-monitor-contract.json"]`,
`required_stages=["monitor_started","foreground_started","parent_pm_boundary",
"agent_terminal_settled","secret_absent","monitor_stopped"]`, `parent_pm_boundary_count=1`,
`evidence_mode="append_only_run_local"`, `secret_targets=["auth.json","config.toml",
"temporary_credentials"]`, and `resource_policy="at_most_one_owned_ephemeral_scope"`. Its
exact command/argv, descriptor ownership, lifecycle states, parent-PM boundary marker, and evidence
handoff come only from `modeling_team/references/p2-monitor-contract.json`. P2 uses
`modeling_team/profiles/base-three-agent.yaml` + `modeling_team/tasks/base-capability-smoke.yaml` or
an equivalent R2.3-001 nonbusiness/presemantic fixture, starts monitoring before the foreground
command, crosses at least one parent-PM turn boundary, observes app-server/Transport/Broker/settlement
and secret cleanup, then stops. If the real path requires ephemeral platform resources, their direct
API/DB cleanup proof is required; they do not become a semantic start or retained product scope.

The implementation plan updates `_baseline_manifest` and hashes both monitor files plus these exact
call-site files: `modeling_team/runner.py` (`TeamRunner.prepare`, `start`, `_baseline_manifest`,
terminal handoff/settlement/cleanup), `modeling_team/runtimes/codex.py`
(`CodexRuntimeAdapter.start_roster`, `start_task`), and `modeling_team/transport_mcp.py`
(`TeamTransportBroker.send`, `report`, `ack_terminal_handoff`). It also retains the Round 49 stable
candidate/proof descriptor and Protocol implementation inputs. Omission/addition/byte drift fails
closed; generated command lines, evidence/PID/credential/descriptor-FD values and fixtures are
excluded. Compute two full manifests with the same prospective fresh run ID and same stable files
before reservation/start, without ledger or ephemeral reads; every entry and hash must match.

#### Focused cases and unchanged global order

Round 50 executes C49 (P2 boundary/key history), C50 (plural ten-field/nested schema), C51 (actual
fallback order), C52 (raw external candidate binding), C53 (foreground monitor lifecycle), and C54
(monitor/call-site baseline binding). No test may claim PASS from a direct verifier call without
fallback state. The global order remains: `r` fixed runtime/infrastructure classification and mandatory
closeout -> P2 PASS -> unique tranche 8 `+2` -> same-ID double baseline -> repair authorization ->
reservation/start -> three Agents completed/settled -> cleanup/evidence freeze -> same tester Phase A
PASS -> handoff -> Phase B -> final gates. F1 remains no Terra/xhigh switch.

**Planned result:** not executed; ready for plan re-review.

### Round 51 — planned P2 path split, evidence-first deletion, and exact Session cleanup

Round 50 remains retained plan history for the candidate/proof schema, digest algorithms, baseline
inputs, raw-envelope binding, fallback order, and global sequencing. Round 51 is the current active
test correction; it is not executed and authorizes no code, runtime, platform, ledger, key, Session,
semantic-start, launch-agent, or delivery-record mutation.

#### Independent P2-monitor test

Run the existing schema-v1 `modeling_team/profiles/base-three-agent.yaml` with
`modeling_team/tasks/base-capability-smoke.yaml` through the real foreground CLI under
`modeling_team/foreground_monitor.py`. The evidence must show the foreground CLI -> TeamRunner ->
CodexRuntimeAdapter -> app-server -> Team Transport/Broker -> `TeamRunner.drain()`
terminal-result-handoff -> ack -> all-agent settlement -> cleanup path, one parent-PM turn boundary,
process persistence, and secret absence. This test is the only P2 proof of those real TeamRunner
lifecycle facts; it does not test
`fallback_required`, native verifier proof, candidate materialization, or business-slice semantics.
If the current CLI genuinely requires mechanical platform state, allow at most one directly owned
ephemeral mechanical scope and clean it; assert no R2.3-002 business source and no R2.3-002 StartLedger
event.

#### Independent P2-Protocol test

Do not invoke TeamRunner and do not run `modeling_team run`. Construct schema-v2 production
`CodexRuntimeAdapter.start_roster` and the actual `TeamTransportBroker`/production stdio/private
bwrap/app-server/native-MCP path exactly as the existing Round 27/32 fixtures do. The fixture may
enter `create`/`fallback_eligible`, but must not invoke `TeamRunner.prepare`, `TeamRunner.start`,
StartLedger reserve, or `mark_semantic_start`; assert that any TeamRunner invocation or ledger event
fails the test. Capture real Broker delivery/reply correlation and the exact sequence:

`query_semantic_context` completed eligible ontology-scoped item -> sanitized `fallback_required` ->
later native verifier complete -> Broker terminal guard/report acceptance -> Protocol runtime cleanup.

Verifier-before-query, missing `fallback_required`, direct verifier-only proof, or terminal handoff
before verifier fails. Manual `sender_id='runner/terminal-result'`, or any claim/fabrication of Runner
terminal-result-handoff, Modeling terminal, ack, or all-three settlement also fails. The fixture may own
one ephemeral platform scope, but its evidence proves only production Adapter/Transport/Protocol
correlation and verifier mechanics, not Producer behavior or a semantic start. The final fresh Producer
alone proves `candidate/receipt/query/verifier -> Modeling terminal -> real Runner handoff/ack ->
Protocol terminal -> all-three settled`.

#### Exact Session/Lease cleanup assertions

For either P2 path when a Session/Lease exists, assert this exact order and direct receipts:

`admin reread/no in-flight -> failure/terminal checkpoint if applicable -> cancel Session once -> cancel atomically auto-releases all leases -> reread Session cancelled and each Lease state=released with released_at`.

After the single Session cancel, no explicit Lease release may be issued. A second release or
`session_terminal` is not success. Before deleting the Project, freeze a first-stage non-secret
artifact covering every project-scoped read/model/Protocol key exact ID, `revoked_at`/non-active status,
cancelled Session, Lease auto-release, ownership, cleanup receipts, and no in-flight Attempt; record the org-scoped
bootstrap-admin key exact ID as `ACTIVE` solely for the upcoming authenticated DELETE and exclude it
from first-stage non-active assertions. Use that active org-admin credential for DELETE, assert
Project/Ontology absence, project-scoped active residuals zero, and FK cascade behavior, then immediately
revoke it and freeze second-stage exact ID, `revoked_at`, non-active status, and retained audit row.
Aggregate both artifacts and prove every created key ended non-active. Existing FK may cascade-delete
project-scoped key/Session/Lease rows; the test must not require those rows to remain. No new deletion
credential, direct DB delete, hard-delete, migration/archive/detach/history retention is permitted. The
org-scoped bootstrap-admin audit row (`project_id=NULL`) remains and must never be hard-deleted. Retain
the aggregate evidence as the complete cleanup proof.

#### Round 51 focused cases and order

Round 51 executes C55 (separate monitor/Protocol paths), C56 (real fallback and terminal ordering),
C57 (single cancel/atomic Lease release), and C58 (pre-delete evidence plus post-delete residuals),
while preserving C43–C54's schema, digest, baseline, and external-binding assertions. The global order
remains: `r` runtime/infrastructure terminal classification -> mandatory closeout -> P2-monitor PASS
and P2-Protocol PASS -> unique tranche 8 `+2` -> same-ID double baseline -> repair authorization ->
reservation/start -> three Agents completed/settled -> success cleanup/evidence freeze -> same tester
Phase A -> handoff -> Phase B -> final gates. F1 remains no Terra/xhigh switch.

**Planned result:** not executed; ready for plan re-review.

### Round 52 — planned two-stage key/delete evidence and P2 provenance ownership

Round 51 remains retained plan history for its path split, Session/Lease order, and global gates. Round
52 is the current active test correction for the final two accepted High findings; it is not executed and
authorizes no code, runtime, platform, ledger, key, Session, launch, semantic-start, or delivery-record
mutation.

#### Two-stage key/delete evidence

For either P2 path that owns an ephemeral Project, freeze a first-stage non-secret artifact before
DELETE. It must cover every project-scoped read/model/Protocol key with exact ID, `revoked_at`, and
non-active status; cancelled Session; Lease auto-release; ownership; cleanup receipts; and no in-flight Attempt. It must
also record the exact org-scoped bootstrap-admin key ID as `ACTIVE`, solely because that credential
authorizes the upcoming authenticated Project DELETE; exclude it from the first-stage non-active
assertion and use that still-active org-admin credential for DELETE. No new deletion credential, direct
DB delete, or hard-delete is permitted.

After DELETE, verify Project/Ontology absent, project-scoped active residuals zero, and existing FK
cascade behavior. Immediately revoke the org-admin key and freeze a second-stage artifact containing
its exact ID, `revoked_at`, non-active status, and retained org-admin revoked audit row
(`project_id=NULL`). Aggregate both
artifacts and prove every created key ended non-active; project-scoped key/Session/Lease rows may
cascade-delete and need not remain, while the `project_id=NULL` org-admin audit row is retained and
never hard-deleted.

#### P2-monitor provenance test

P2-monitor is the only P2 test that may claim the real schema-v1 TeamRunner terminal lifecycle. Under
`foreground_monitor.py`, directly observe `TeamRunner.drain()`, terminal-result-handoff, ack,
all-agent settlement, and cleanup through the real foreground TeamRunner/Codex Adapter/app-server/
Team Transport path. This remains no-business/no-semantic-start evidence and does not test the
Protocol fallback proof.

#### P2-Protocol provenance test

P2-Protocol remains TeamRunner-free schema-v2 production Adapter/Broker/stdio/private-bwrap/app-server/
native-MCP. Its required evidence ends at:

`query_semantic_context -> fallback_required -> later verifier complete -> Broker terminal guard/report acceptance -> Protocol runtime cleanup`.

It must not claim or fabricate Runner terminal-result-handoff, Modeling terminal, ack, or all-three
settlement; manual `sender_id='runner/terminal-result'` is forbidden. Any such event or claim fails the
test. The final fresh Producer alone proves:

`candidate/receipt/query/verifier -> Modeling terminal -> real Runner terminal-result-handoff/ack -> Protocol terminal -> all-three settled`.

Round 52 executes C59 (two-stage key/delete evidence) and C60 (P2/Producer provenance ownership), while
preserving C43–C58 schema, digest, baseline, candidate-binding, fallback, Session, and ordering gates.
The global order remains unchanged: `r` closeout -> P2-monitor PASS -> P2-Protocol PASS -> tranche 8
authorization -> two baselines -> repair authorization -> fresh reservation/start -> final Producer
provenance/settlement -> cleanup/evidence freeze -> Phase A -> handoff -> Phase B -> final gates.

**Planned result:** not executed; ready for plan re-review.

### Round 54 — 2026-08-01 independent D53 retest at supplied stable digest `b5c53858f235f898c82d5d28de522b5ce1fb505d76e98f5de097ffcf7930fef1` — FAIL

This is an independent retest of the Round 53 defects. The tester made no product-code or
delivery-record change. Real attempts used only fresh, owned P2 monitor/driver run IDs and stopped
after the deterministic P2-Protocol failure; no tranche, baseline/producer semantic start, or new
business-model attempt was launched.

#### C61 — D53-01 real P2 monitor with smallest base-capability smoke — PARTIAL / BLOCKED

Command (fresh temporary `mode: create` scope and FIFO-backed foreground process):

```bash
uv run --project backend python -m modeling_team.foreground_monitor \
  --contract modeling_team/references/p2-monitor-contract.json \
  --run-root /tmp/r23002-round54-p2-monitor-GzqkyS \
  --evidence /tmp/r23002-round54-p2-monitor-GzqkyS/evidence/p2-monitor.jsonl \
  -- /tmp/r23002-round54-p2-monitor-GzqkyS/run-monitor.sh
```

Actual result: PASS for the directly observable normal lifecycle. The monitor returned zero; its
evidence records `parent_pm_boundary: count=1`, `agent_terminal_settled: returncode=0`, and no
secret. `workspaces/modeling-runs/r23002-p2m-round54-gzqkys/state.json` is `CLEANED`, with
Coordinator, Modeling, and Protocol all `completed`; `settled.jsonl` and
`terminal-result-handoff.jsonl` contain real Modeling-to-Protocol/Coordinator then
Protocol-to-Coordinator terminal handoffs. This is real foreground monitor, CLI, TeamRunner, Codex
Adapter/app server, Broker, and parent-PM-boundary evidence—not assistant-text-only evidence.

However, the required adverse ordering is not proved: the safe retained evidence contains no
Protocol early rejected report, no subsequent valid `retry_report_task_result_once` native-tool
call, and no persistently auditable `ack_terminal_handoff` record. The natural base smoke merely
waited for Modeling's terminal handoff. Code inspection cannot substitute for an observed event;
the Broker acknowledgement is in-memory. Therefore this subcase is **BLOCKED / INCONCLUSIVE**, not
accepted as proof that the repair enforces reject-then-retry-and-ack ordering. Unblock condition:
a smallest real smoke that emits those three safe events in the required order without relying on
assistant prose.

The owned monitor scope passed two-stage cleanup: project/ontology absence, zero project-scoped
active-key residuals, terminal Session/auto-released Lease, then revoked org-admin with retained
audit row. No matching run process remained.

#### C62 — D53-02 TeamRunner-free real P2-Protocol driver — FAIL (D54-01, High, collaboration/routing)

Commands (two independent owned runs):

```bash
uv run --project backend python -m modeling_team.p2_protocol_driver \
  --contract modeling_team/references/p2-protocol-driver-contract.json \
  --run-id r23002-p2p-round54-driver --timeout 600
uv run --project backend python -m modeling_team.p2_protocol_driver \
  --contract modeling_team/references/p2-protocol-driver-contract.json \
  --run-id r23002-p2p-round54-diagnostic --timeout 120
```

Expected: the TeamRunner-free schema-v2 Adapter/Broker/stdio/private-bwrap/app-server/native-MCP
path delivers the synthetic candidate, then records delivery receipt, retrieval query and fallback,
verifier `mode=create` completion, Broker terminal acceptance/report, Protocol runtime cleanup, and
two-stage scope cleanup.

Actual: both runs fail immediately after `candidate_delivered`; the diagnostic command exits nonzero
with `p2 protocol driver failed: unexpected P2 Broker delivery`. The driver enqueues its synthetic
candidate then calls `broker.drain()` and treats that still-queued candidate as an unexpected reply.
Neither run reaches receipt/query/fallback/verifier/Broker acceptance. Evidence:
`workspaces/p2-protocol-runs/r23002-p2p-round54-{driver,diagnostic}/evidence/p2-protocol-driver.jsonl`
contains only `driver_started`, `protocol_roster_started`, `candidate_delivered`, `driver_failed`
(`P2ProtocolDriverError`), then runtime/scope cleanup stages. This blocks the required P2-Protocol
acceptance path; it must be repaired before another real retest.

Both failed driver scopes nevertheless passed cleanup-on-error: each evidence stream asserts
`project_absent=true`, `ontology_absent=true`, `active_project_residual_count=0`, followed by the
second-stage org-admin revoke/audit evidence. No TeamRunner or fabricated terminal-handoff event was
observed or claimed.

#### C63 — historical isolation, determinism, and regression gates — PASS

- Before and after all owned attempts, the historical ledger SHA-256 stayed
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431` and the old real-run
  state SHA-256 stayed `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`.
- Two same-ID prospective baselines for `r23002-p2-prospective-round54` produced the identical
  `dfd128f4faba67a2ee26d7247d9caeb7350123bd2a419c4c26406d84de73bc42`.
- Focused: `python -m unittest modeling_team.tests.test_p2_protocol_driver
  modeling_team.tests.test_runner modeling_team.tests.test_protocol_retrieval_mcp
  modeling_team.tests.test_foreground_monitor modeling_team.tests.test_r23002` — 59 passed.
- Full modeling: `python -m unittest discover -s modeling_team/tests -p 'test_*.py'` — 121 passed.
- Focused backend: `python -m pytest -q backend/tests/test_semantic_read_model_stage2_execution.py`
  — 24 passed (3 deprecation warnings).
- Full backend: `cd backend && uv run pytest -q` — 821 passed, 10 skipped (188 warnings).
- `python -m modeling_team validate` passed for base-capability-smoke and new-scope-business-slice;
  Ruff, every reference JSON parse, and `git diff --check` passed.
- Final runtime remained healthy: backend `/api/health` returned `{"status":"ok"}`, frontend
  returned HTTP 200, and `ontology-platform.service` was active.

**Round 54 conclusion: FAIL.** D54-01 is a confirmed High Broker-routing defect; C61 also lacks the
required real adverse-order/ack evidence, so neither P2 acceptance claim may be promoted. Recommend
that the Requirement Developer repairs D54-01 and adds durable safe evidence for C61's required
ordering, then request a new tester retest using this same plan. Round 53 remains unchanged.

### Round 55 — 2026-08-01 independent P2-only retest at supplied handoff digest `1ac0ddd21bd3909d071c72c158c5901d1f03a5cab4bf12a29ebc9a1758b8f89e` — FAIL

This round tested only the two minimum nonbusiness P2 gates. The tester changed no product,
requirement, design, or delivery-record file; did not run C→B→A, old `r`, StartLedger reservation,
budget authorization, or semantic start. `AGENTS.md` and `CLAUDE.md` remain excluded unrelated
worktree edits.

#### C64 — real P2-monitor adverse-order smoke — BLOCKED (D55-01, High, platform-contract/runtime)

The owned preflight command was:

```bash
uv run --project backend python -m modeling_team.foreground_monitor \
  --contract modeling_team/references/p2-monitor-contract.json \
  --run-root workspaces/modeling-runs/r23002-p2m-round55-adverse2 \
  --evidence workspaces/modeling-runs/r23002-p2m-round55-adverse2/evidence/p2-monitor.jsonl \
  --extract-adverse-order -- /tmp/r23002-round55-monitor-3uhVoh/run-monitor.sh
```

Expected: one real foreground CLI/TeamRunner/production Adapter/Broker smoke and the monitor-owned
safe extractor, before runtime deletion, recording only the strict safe order: Protocol rejection for
missing Modeling handoff -> real Modeling-to-Protocol handoff -> real ack -> accepted retry ->
all-three completed settlement.

Actual: no TeamRunner or platform scope started. The monitor first appends its own evidence under the
required CLI run root; the real `modeling_team run` then fails closed with `run directory already
exists`. This prevents one process from both owning the actual run root and observing the runtime
before its cleanup. The initial owned script attempt was also rejected before child start due missing
executable permission; it was corrected by `chmod 700` and not counted as a real attempt. Evidence
hashes: first monitor evidence
`145352309228887829ac9a8ac6ef308603478f854b679bef4c4c0512571c5e96`; structural-preflight evidence
`bcb5618b934388606590a2a287727a914814295080ac9b38a1b98f3f525484b4`.
No terminal ordering can be inferred from settlement or assistant text. Unblock condition: provide a
reviewed monitor/CLI handoff that permits the extractor to read the actual live run root without
precreating a directory rejected by the Runner.

#### C65 — real TeamRunner-free P2-Protocol — FAIL (D55-02, High, runtime/infrastructure)

Command:

```bash
uv run --project backend python -m modeling_team.p2_protocol_driver \
  --contract modeling_team/references/p2-protocol-driver-contract.json \
  --run-id r23002-p2p-round55-protocol --timeout 900
```

Expected: directed candidate claim by `delivery_id`, real Protocol Adapter receive/ack, only the
correlated Protocol-to-synthetic reply, then real query -> `fallback_required` -> native
`mode=create` verifier completion -> Broker terminal acceptance, followed by runtime and two-stage
scope cleanup. TeamRunner, business sources, semantic start, and fabricated terminal evidence are
forbidden.

Actual: D54-01's directed claim repair works: safe evidence records
`candidate_delivered delivery-1` followed by only `candidate_receipt delivery-2
reply_to_delivery_id=delivery-1`. The real Protocol bwrap/app-server then made no observable
`query_completed` or `fallback_required` progress for about four minutes. This is an actual
post-receipt runtime stall, not a missing candidate correlation. Per fail-fast policy, the tester sent
SIGINT to the driver Python process; its `finally` completed in the same owned run. No additional
run was started. The safe evidence file is
`workspaces/p2-protocol-runs/r23002-p2p-round55-protocol/evidence/p2-protocol-driver.jsonl`
SHA-256 `01b66610429e86ce6b11c8612772bc98cf77b54a9ac7ee6c23e8906f3fe2cecc`.
It contains no TeamRunner/Runner-handoff claim, and no query/fallback/verifier/Broker terminal stage.

Cleanup-on-interrupt PASS: `protocol_runtime_cleanup` reports
`credentials_destroyed=true`; first stage is ready, terminal, and Lease-auto-released; DELETE is
204 with Project/Ontology absent and active residual count zero; second stage revokes the org admin
and retains its audit row; `driver_stopped` has `cleanup_error_types=[]`. The retained run root
contains only baseline, safe evidence, and staged sources—no runtime, runtime-assets, or transport
directory. Backend health remained `{"status":"ok"}`.

#### C66 — isolation, validation, and regression — PASS

- Before and after P2, old StartLedger SHA-256 remained
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431`; old
  `r23002-real-20260801p/state.json` remained
  `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`.
- `modeling_team validate` passed for P2 adverse-order and v2 new-scope profile/task; all reference
  JSON parsed; Ruff and `git diff --check` passed.
- Focused unittest modules (monitor, driver, Runner, transport, Protocol retrieval, R2.3-002): 73
  passed. Full `modeling_team/tests`: 125 passed. Full backend:
  `cd backend && uv run pytest -q`: 821 passed, 10 skipped (188 warnings).
- Two same-ID prospective P2 baselines were identical:
  `ec3149870345d6dd66ee81e9746ee15d783488c677bcd80919d9edca4c6f527e`.
  Backend health, frontend HTTP 200, and `ontology-platform.service` active were rechecked.

**Round 55 conclusion: FAIL.** Neither required real acceptance sequence is proved. D55-01 blocks
the monitor's live safe extraction contract; D55-02 stalls after real correlated receipt before the
required query/fallback sequence. Recommend developer diagnosis and narrow repair of both defects,
then a new independent round in this same plan. Do not proceed to old-r closeout, tranche/baseline
authorization, producer, or semantic start.

### Round 56 — 2026-08-01 independent P2-only retest at handoff digest `0c521f43e88fc4f7d3a61b2a402c26978f63e85cb973d2ef8911f7a4be91c23f` — FAIL

This round ran only one fresh run per P2 gate. It did not run C→B→A, old `r` closeout,
StartLedger/tranche/reservation, budget authorization, or semantic start. No product,
requirement/design, or delivery-record file was modified.

#### C67 — P2-monitor sibling-handoff adverse-order smoke — FAIL (D56-01, High, platform-contract/runtime)

Preflight verified the target `workspaces/modeling-runs/r23002-p2m-round56-adverse` did not exist and
there were zero same-ID monitor sibling roots. The exact real command was:

```bash
uv run --project backend python -m modeling_team.foreground_monitor \
  --contract modeling_team/references/p2-monitor-contract.json \
  --run-root workspaces/modeling-runs/r23002-p2m-round56-adverse \
  --evidence workspaces/modeling-runs/r23002-p2m-round56-adverse/evidence/p2-monitor.jsonl \
  --extract-adverse-order -- /tmp/r23002-round56-monitor-FtMX0c/run-monitor.sh
```

The monitor created the sibling handoff root
`workspaces/modeling-runs/.r23002-p2m-round56-adverse.monitor-6b8d46e0b1e0e57f42f1107f78fc89a3`
and the CLI created the live target only after `prepared`. The retained phase timeline uses the
recorded `recorded_at_ns` values, not wall-clock inference:

- `prepared.json`: 1785570247519930624;
- monitor `extraction_failed.json`: 1785570277529860885, `error_type=TimeoutError`;
- runner `failed.json`: 1785570280536238372.

The retained phase-file SHA-256 values are `prepared.json=ef16097fdeb4e61396a1d089cd9b0ce49b169ce6efe2d6fbf3103700fe17c2c4`,
`extraction_failed.json=e7a26708cc85285a18a9aee8213a392f18ca3ad1d14b19e1ba60a6468f34c289`, and
`failed.json=8403f573b7de97492f051df69d7f523575118ff8ba9ed77340b2ecb3540478de`.

Thus the monitor waited exactly 30.009930261 seconds after `prepared` for
`runner-to-monitor/cleanup_pending.json`, but that phase was never written. It consequently never
wrote `monitor-to-runner/extraction_complete.json` or the safe
`evidence/p2-adverse-order.jsonl`. The CLI-side retained log is
`evidence/p2-monitor.jsonl` (SHA-256
`2cde58abf572475fb9869644e47b064a530c919dd7499a1d5d7ee02334081c9c`): it contains
`monitor_started`, `foreground_started`, `parent_pm_boundary`, `secret_absent`, and
`monitor_stopped returncode=130`, with no adverse-order record. The monitor command returned exit
2 with `P2 monitor cleanup handoff timed out`. This is a direct phase/CLI failure, not a settlement
inference; the required reject -> Modeling handoff -> ack -> retry -> all-three order is unproved.

The CLI nevertheless completed its own finally cleanup: `state.json` is `CLEANED`, private
runtime credentials are destroyed, Session is terminal, Lease auto-released, Project DELETE returned
204, Project/Ontology are absent, project-scoped active residuals are zero, and the org-admin key was
revoked with its retained audit row. The sibling handoff files remain immutable diagnostic evidence.
The run had no terminal results because the monitor terminated it before `cleanup_pending`.

The local preexisting-target fail-closed check passed (4 focused monitor/driver checks total); it
confirmed a preexisting target is rejected without starting a child. Unblock condition: make the
foreground CLI publish `cleanup_pending` before its bounded monitor deadline, while preserving
nonce/root/immutable digest acknowledgement and safe extraction before cleanup.

#### C68 — TeamRunner-free P2-Protocol — PASS (bounded P2 gate)

Preflight compiled the exact fixture and loaded the exact contract; it confirmed schema-v2, a single
Protocol role, and only Protocol-scoped reference input. The sole real command was:

```bash
uv run --project backend python -m modeling_team.p2_protocol_driver \
  --contract modeling_team/references/p2-protocol-driver-contract.json \
  --run-id r23002-p2p-round56-protocol --timeout 900
```

Safe evidence (SHA-256
`6260275f5d5afd17bf1fafcfc4092009412122565ff891646dc60fb6bef8f1d1`) directly records the
required ordered stages:

`candidate_delivered delivery-1` -> `candidate_receipt delivery-2
reply_to_delivery_id=delivery-1` -> `query_completed episode=1` ->
`fallback_required episode=1` -> `verifier_completed episode=2 mode=create` ->
`broker_terminal_guard blocked=false` -> `protocol_report_accepted status=blocked`.

The correlated receipt was validated by the driver and only the Protocol-to-synthetic reply was
accepted. No TeamRunner, business source, semantic-start, fabricated handoff, raw triple, or backend
compiler change was used. The sanitized retrieval transition evidence
(`protocol-retrieval-gate.jsonl`, SHA-256
`f02da5089bf29ae6686844bbbe66582183808614383a36ae6a3db1c27bb25a5e`) contains the query/fallback
state transitions without prompt/message/result/credential content.

Protocol cleanup passed: `protocol_runtime_cleanup credentials_destroyed=true`; first-stage evidence
has `ready_for_delete=true`, terminal Session, auto-released Lease, and non-active project key;
authenticated DELETE returned 204 with Project/Ontology absent and active residual count 0; second-stage
org-admin finally revoke is non-active with retained org-admin audit; `driver_stopped` has
`cleanup_error_types=[]`. No run process remained.

#### C69 — isolation, preflight, determinism, and regressions — PASS

- Before and after both P2 runs, the StartLedger SHA-256 remained
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431`; old
  `r23002-real-20260801p/state.json` remained
  `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`.
- Same-ID prospective P2 baseline twice produced the identical
  `0827ee9acd0a9f22ec335be362f5f941127396bd0ebba563d2ad305d8ab5fc01`.
- Focused local preflight/ordering checks: 4 passed; focused regression suite: 73 passed.
  Full `modeling_team/tests`: 129 passed. Full backend `cd backend && uv run pytest -q`: 821
  passed, 10 skipped (188 warnings).
- P2 adverse/profile and v2 profile/task validation, Python compile, all reference JSON parsing,
  Ruff, and `git diff --check` passed.
- Final health remained backend `{"status":"ok"}`, frontend HTTP 200, and
  `ontology-platform.service` active; no P2 process remained.

**Round 56 conclusion: FAIL.** C68 independently passes its bounded TeamRunner-free acceptance
sequence, but C67 cannot prove the monitor-required adverse order because `cleanup_pending` was
not emitted before the 30-second handoff deadline. Recommend a narrow developer repair of D56-01 and
a new independent Round57 in this same plan; do not proceed to old-r closeout, tranche/semantic
start, or Producer.

### Round 57 — 2026-08-01 independent C67 P2-monitor retest at handoff digest `fde4268ba479380c97e0ab0926873d9858ccf5e7f8098a76814bfbf8c9ad5d31` — FAIL

This round re-tested only C67 with one fresh real monitor run:
`r23002-p2m-round57-adverse`. C68 TeamRunner-free Protocol remained the Round 56 PASS and was
not repeated. No old `r` closeout, C→B→A, StartLedger/tranche/reservation, budget authorization,
semantic start, product-code, requirement/design, or delivery-record change was made.

#### C70 — real sibling-handoff monitor lifecycle — FAIL (D57-01, High, platform-contract/runtime)

Before launch, the canonical target root and same-ID sibling handoff root were both absent. The exact
command was:

```bash
uv run --project backend python -m modeling_team.foreground_monitor \
  --contract modeling_team/references/p2-monitor-contract.json \
  --run-root workspaces/modeling-runs/r23002-p2m-round57-adverse \
  --evidence workspaces/modeling-runs/r23002-p2m-round57-adverse/evidence/p2-monitor.jsonl \
  --extract-adverse-order -- /tmp/r23002-round57-monitor-9BtgF6/run-monitor.sh
```

The repaired handoff path worked through its timing boundary. The retained phase timeline, based only
on explicit phase `recorded_at_ns` values, is:

- `prepared.json`: 1785571654951300086;
- `cleanup_pending.json`: 1785571708262339706 (53.311039620 seconds after prepared, within the
  120-second foreground deadline);
- `extraction_failed.json`: 1785571708293505138, `error_type=ValueError`;
- runner `failed.json`: 1785571708316048017.

The monitor therefore did not fail by premature 30-second timeout. It entered cleanup pending, then
the safe extractor failed in 31ms with
`P2 adverse-order requires exactly one rejection and one retry`. The target retained no
`evidence/team-transport-events.jsonl`, so the extractor had no direct safe records for the early
Protocol report rejection and later retry. It did not write
`evidence/p2-adverse-order.jsonl` or `monitor-to-runner/extraction_complete.json`; the monitor
returned exit 2 with `foreground monitor failed: P2 adverse-order requires exactly one rejection
and one retry`. The retained monitor log
`evidence/p2-monitor.jsonl` has SHA-256
`d0a83c43aaa23a0dd3d7fac08f0067ec91b73364bc5700a73dd22e8921b4b418`.

The safe evidence inventory is exactly `app-server-events.jsonl`, `coordinator-final.jsonl`,
`coordinator.jsonl`, `deliveries.jsonl`, `mcp-elicitations.jsonl`, `outer-user.jsonl`,
`p2-monitor.jsonl`, `runtime-core-hashes.jsonl`, `settled.jsonl`, `terminal-handoff-ack.jsonl`,
and `terminal-result-handoff.jsonl`; there is no `dynamic-tool-calls.jsonl` or
`team-transport-events.jsonl`. The redacted App Server event ledger has 397 events and contains no
`item/tool/call` method (only ordinary item/thread/turn notifications plus 11 MCP elicitation
requests), so the retained evidence does not show a Codex adapter dynamic Team Transport callback
or a safe dynamic result that the Runner then failed to aggregate. This narrows D57-01 to an
upstream callback/routing or contract-observability gap; it does not prove which internal branch
prevented the callback, and raw terminal summaries are not used to fill that gap.

Direct raw `terminal-result-handoff.jsonl`, `terminal-handoff-ack.jsonl`, and `settled.jsonl`
files exist (SHA-256 respectively
`c38919976cee34a530e42ecbc23b66f4a8d1fe09ad04085306458745fae19799`,
`18e48d5cc228dfaad790efdb1125de63f2aae119bda4086e661fe5a916b16f11`, and
`3f063b6a926bdc4a34ff699af5bf191df5d1bad458a5e86e22fb0708d575ce58`), and `state.json`
is `CLEANED` with Coordinator, Modeling, and Protocol all `completed`. Those raw terminal
summaries are not accepted as safe adverse-order proof: the contract requires the extractor's
sanitized, same-handoff ordered records, and no wall-clock or assistant-text inference is allowed.

The immutable sibling handoff root is
`workspaces/modeling-runs/.r23002-p2m-round57-adverse.monitor-988a0bef5c6b13bb8941280473d5fe7c`.
Phase SHA-256 values are:
`metadata.json=4e848efa0d2049e2efd08920dd846ee89f322bbc3d17bc195a2f1a59d49c260a`,
`prepared.json=bc1ec94f916ae0c08ff83503c43f0aa48e62827cbaf3a8d068c15d79694bf4d2`,
`cleanup_pending.json=f029d6cd378e1e1a0f90e1fb1793016bd656a8d3d3a06c15f9612f7ceb9bf52b`,
`extraction_failed.json=03a3901bc0e108383ceb0dbb5ed5eb7877c30de9d3bf7129093ec51f2bb99b6a`, and
`failed.json=a7bc8027f2d5cc64bfdb457e1d8ffe33afa64ca4f570083d8964da2c6263bd25`.

Cleanup assertions passed despite extraction failure: all three private runtime credentials were
destroyed; first-stage scope evidence records terminal Session, auto-released Lease, no in-flight
Attempts and non-active project key; authenticated DELETE returned 204 with Project/Ontology absent
and active project residuals zero; second-stage org-admin finally revoke is non-active and its
`project_id=NULL` audit row is retained. No run process remained.

#### C71 — local gates and isolation — PASS

- Preexisting-target fail-closed, sibling-handoff, receipt-binding and adverse extractor focused
  checks: 4 passed; focused modeling regression modules: 76 passed.
- Full `modeling_team/tests`: 131 passed.
- P2 adverse/profile and v2 profile/task validation, Python compile, all reference JSON parsing,
  Ruff, and `git diff --check` passed.
- Same-ID prospective baseline twice matched:
  `da1fb3be30c426c7de0a935a0cc48456e7ebda5813e7426d1c807b0cb2f4ca89`.
- Backend code was unchanged in this retest; Round 56 full backend remains the applicable result
  (`cd backend && uv run pytest -q`: 821 passed, 10 skipped, 188 warnings). This round rechecked
  backend health `{"status":"ok"}`, frontend HTTP 200, and active
  `ontology-platform.service`.
- Old StartLedger SHA-256 remained
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431`; old
  `r23002-real-20260801p/state.json` remained
  `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`.

**Round 57 conclusion: FAIL.** The 120-second foreground and cleanup handoff timing repair is
observed, and the real smoke reaches rejection/handoff/ack/settlement, but D57-01 prevents the
required sanitized adverse-order evidence because `team-transport-events.jsonl` is absent.
Recommend adding direct safe report rejection/retry records (or an equivalent reviewed sanitized
source) and rerunning this same C67 gate as Round 58. Do not repeat C68 or start any old-r/semantic
workflow.

### Round 58 — 2026-08-01 independent C67 P2-monitor adverse-order retest at handoff digest `9e15320fd14155a689c564830982b516f8be19b087aeca6bb419ede864cc0c9b` — PASS

This round re-tested only C67 after the D57-01 transport-observer repair. C68 Protocol and the
deadline repair remained closed and were not repeated. No full C→B→A flow, old `r` closeout,
StartLedger/tranche/reservation action, semantic start, requirement/design/delivery-record edit,
or product-code edit was made by the tester. The tester made only this append-only test-plan update.

#### C72 — one real sibling-handoff P2-monitor run — PASS

The canonical target and same-ID sibling were absent before launch. The sole fresh run was
`r23002-p2m-round58-adverse`, using a `mode: create` scope fixture and the real foreground
`TeamRunner`/Codex Adapter/app-server/stdin `transport_mcp`/private Unix socket/Broker path. The
exact monitor command was:

```bash
uv run --project backend python -m modeling_team.foreground_monitor \
  --contract modeling_team/references/p2-monitor-contract.json \
  --run-root workspaces/modeling-runs/r23002-p2m-round58-adverse \
  --evidence workspaces/modeling-runs/r23002-p2m-round58-adverse/evidence/p2-monitor.jsonl \
  --extract-adverse-order -- /tmp/r23002-round58-monitor-rCLjW8/run-monitor.sh
```

The real command completed with exit 0. The retained monitor log
`workspaces/modeling-runs/r23002-p2m-round58-adverse/evidence/p2-monitor.jsonl` (SHA-256
`706920293f01f2d6aff126d4789c00eccae0c69b274b6ef5647ab1479a5034c3`) records
`monitor_started`, `foreground_started`, exactly one `parent_pm_boundary`,
`agent_terminal_settled returncode=0`, `secret_absent`, and `monitor_stopped returncode=0`.

The immutable sibling handoff root is
`workspaces/modeling-runs/.r23002-p2m-round58-adverse.monitor-f814c0b0b98d1531dae0016b8656ec6a`;
its root and phase directories are `0700`, every phase file is `0600`, all phase nonce/root/run-ID
bindings match, and no `failed.json` or `extraction_failed.json` exists. Explicit phase timestamps
(not wall-clock inference) are:

- `prepared.json`: `1785573859451866261`;
- `cleanup_pending.json`: `1785573959169579188`, 99.717712927 seconds after prepared and within
  the fixed 120-second foreground deadline;
- `extraction_complete.json`: `1785573959211563404`, 0.041984216 seconds after cleanup pending.

Phase SHA-256 values are `metadata.json=9187c4838ecaf0c02bb1513f6f4d28e23d235f31c0c825cbc0baab0c135bae63`,
`prepared.json=73f9f9789ffa9615d7528345fd887470b30bf45667aa790224bb76ac3df69b9f`,
`cleanup_pending.json=5696e90c3297bc344ab01fd5a08ea3bd1862e438d25d0ada672585ad1800d10`, and
`extraction_complete.json=242800b1d22ec7c36ae92272d6804ac0541f67dd665dfb18e45b46254f271e35`.

The safe Codex/Team Transport observer evidence is
`evidence/team-transport-events.jsonl` (SHA-256
`c2fb76a331214da68753aaba6cae8591a79056939ff125368282c8fd0d875c4a`, mode `0600`, exactly four
records). Every record has exactly the six fields `agent`, `tool`, `status`, `category`, `ack`, and
`recorded_at_ns`; no args, error, summary, result, prompt, message, credential, token, or secret
field is present. The file contains exactly two Protocol `report_task_result` records in file and
`recorded_at_ns` order: one `rejected/missing_modeling_handoff`, followed by one
`accepted/terminal_report_accepted`. Modeling and Coordinator each have one separate accepted
terminal-report observer record. The ordinary stdio path is directly evidenced: the redacted
`app-server-events.jsonl` (SHA-256
`f861f0de357c0af576fdcd18b80450af59d487ea5fd00bdb8c34df05f753d0a8`) has 419 metadata-only events
and no `item/tool/call` method, and no
`dynamic-tool-calls.jsonl` exists, so this run does not depend on a legacy dynamic callback and
does not double-record the stdio report.

The extractor created `evidence/p2-adverse-order.jsonl` with exactly eight safe records, mode
`0600`, SHA-256
`545586fefef76b8d6edda3533bd0c2d30b7a88ad804f39bc265cd290227a2e74`, and output length 1237:

1. Protocol report rejected for missing Modeling handoff;
2. actual Modeling terminal handoff delivered to Protocol;
3. the same handoff ID acknowledged by Protocol with accepted/true and sequence 1 -> 2;
4. Protocol terminal-report retry accepted;
5–7. Coordinator, Modeling, and Protocol terminal results completed;
8. one all-three settlement completed.

The monitor acknowledgement binds the output digest and byte length exactly before CLI cleanup.
The retained `settled.jsonl` contains one event with exactly Coordinator, Modeling, and Protocol all
`completed` (SHA-256 `6498d5b405704f2c1de9fcb7e431cd885e981382d1f71c5e6475dd869a4b7beb`); the
terminal-handoff and acknowledgement evidence are SHA-256
`d0ad950ab55559774e1b42b9b394a9e1364d935f9e7c1611c4a7fcb9d2d91ccc` and
`7d8e548b75940ec8727e29555fcf386fe7a6e45c27e67a32d16e61dbe87fbf3c`. No raw summary, elicitation
count, or wall-clock inference was used for this gate.

Cleanup passed exactly once in both stages: `state.json` is `CLEANED`; all three private Runtime
credential sets are destroyed; first-stage evidence has terminal Session, auto-released Lease, no
in-flight Attempts, and non-active project-scoped key; authenticated DELETE returned 204; Project
and Ontology are absent; Lease/Ontology/Project/project-scoped-key/Session residual counts are all
zero with FK cascade true; the org-admin key was immediately revoked, non-active with
`project_id=NULL`, and its audit row retained; aggregate key state is non-active. No run, monitor,
Agent, or transport process remained.

#### C73 — local regression, isolation, and health — PASS

- Focused observer/monitor/Runner/Transport/Codex/R2.3-002 suite:
  `uv run --project backend python -m unittest modeling_team.tests.test_foreground_monitor modeling_team.tests.test_p2_protocol_driver modeling_team.tests.test_runner modeling_team.tests.test_transport modeling_team.tests.test_codex_isolation modeling_team.tests.test_r23002` — 121 passed.
- Full `modeling_team/tests`: `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'` — 137 passed.
- Ruff, Python compile, P2 and base/new-scope profile/task validation, all reference JSON parsing,
  and `git diff --check`: PASS.
- Same-ID read-only baselines were byte-identical: P2 prospective baseline hash
  `9130b0ffe1311a6b4b74e46e30069b2278f6f99e465efb9abda7766d55c788e6`; base/new-scope prospective
  baseline hash `91d1c6f2cedd92df18fcc50330b4b373d5c4e8137dd2949a9053971445f6d025`.
- Backend code was not changed by this retest; Round 56's applicable backend result remains
  `cd backend && uv run pytest -q`: 821 passed, 10 skipped, 188 warnings. Post-run health was
  backend `{"status":"ok"}`, frontend HTTP 200, and active `ontology-platform.service`.
- Protected hashes remained unchanged after the run: StartLedger
  `dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431`; old
  `r23002-real-20260801p/state.json`
  `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88`.

**Round 58 conclusion: PASS for C67; P2 overall PASS when combined with the independent Round 56
C68 Protocol PASS.** The independent real P2-monitor now proves the required sanitized
adverse-order sequence, ordinary stdio observer path, bounded handoff/extraction acknowledgement,
all-Agent settlement, and exactly-once two-stage cleanup. No new defect was found. The P2 gate is
therefore releasable to the next Delivery Agent stage (old-`r` closeout, tranche authorization, and
the final fresh Producer), subject to that stage's own gates; this tester did not enter or execute
any of those workflows.

### Round 58 erratum — 2026-08-01 read-only old-run protection target audit — PASS

This append-only erratum audits a stale protected-target reference discovered in the preceding P2
rounds. Earlier C66/C69/C73 text protects `r23002-real-20260801p/state.json` (for example, lines
3302–3305, 3410–3413, and 3631–3632), while the authoritative closure plan and the causal delivery
audit identify the unique unclosed historical run as `r23002-real-20260801r`. This round was strictly
read-only: no product, requirement, design, delivery-record, test-code, Platform, database, ledger,
resource, key, Session, Lease, P2, or semantic-start mutation was performed. Only this test-plan
section was appended.

#### Erratum-A — ledger sequence and authoritative target — PASS

The exact read-only command was:

```bash
nl -ba workspaces/modeling-runs/.r2-3-002-start-ledger.jsonl | sed -n '64,80p'
```

The ledger SHA-256 is
`dbbb38f6249d5a793c1497c9aae2ba90ff612f6c43a4b1765e101a78a0f6d431`. The relevant immutable
sequence is:

- lines 70–71: `r23002-real-20260801p` reservation and `semantic_start`;
- line 72: `r23002-real-20260801p` `terminal_failure`, `classification=collaboration/routing`,
  `complete_modeling_quality_result=false`;
- line 74: `r23002-real-20260801p` repair authorization;
- lines 79–80: `r23002-real-20260801r` reservation and `semantic_start` only.

No `terminal_failure` or `repair_authorization` event exists for `r23002-real-20260801r` in the
ledger. This is consistent with the authoritative target references: Test Plan Round 47 names `r`
and requires its terminal classification/closeout before P2 (lines 2492–2515), the Design closure
revision names `r` and preserves its historical failed-written evidence (lines 750–787 and
804–859), and the Delivery Record causal audit names `r` as `runtime/infrastructure` with
`complete_modeling_quality_result=false` (lines 2755–2776). The later `p` assertions are therefore
a stale protected reference, not a change of target.

#### Erratum-B — retained state hashes and pre-P2 hash limitation — PASS

Read-only `sha256sum`/`stat` checks recorded:

| Path | State | SHA-256 | mode/size | mtime (+08:00) |
|---|---|---|---|---|
| `workspaces/modeling-runs/r23002-real-20260801r/state.json` | `PAUSED` | `a3c397ee4bc2ab3d394d639a130880cbdcbec34a36553aa3305420bfa7d22632` | `0600` / 54 | 2026-08-01 08:14:48.392568320 |
| `workspaces/modeling-runs/r23002-real-20260801p/state.json` | `CLEANED` | `7c8251e894a65de993af347d265c5abcf1b7a730eb33947ede6d01992a9c2b88` | `0600` / 3045 | 2026-08-01 05:12:47.709031058 |

No retained pre-P2 `r/state.json` hash was found. The current `a3c397…` value is therefore not
presented as a before/after equality proof. The conclusion below is a strong temporal/resource
isolation inference from independent mtime, identity, ledger, process, journal, and API/DB evidence;
it is not a fabricated pre-P2 cryptographic hash comparison.

#### Erratum-C — filesystem/runtime non-overlap — PASS

For the mtime audit, copied `sources/`, `platform/`, `skills/`, and `references/` snapshots were
excluded; only run-owned root metadata, evidence, and runtime data files were considered. The exact
read-only inventory used `find … -printf` plus a Python `os.stat` range calculation. `r` has root
files from `08:01:31.788` through state write `08:14:48.392`, evidence through
`08:15:18.091`, and run-owned runtime data through `11:02:43.572`. The first P2 run-owned file is
Round 53 root metadata at `13:47:30.682` (runtime data `13:47:30.841`), leaving no P2 write-time
overlap with `r`.

| retained run | root/evidence or monitor mtime range (+08:00) | runtime data max (+08:00) | retained state/evidence |
|---|---|---|---|
| `r23002-p2m-round53-anrawb` | 13:47:30.682–13:51:53.022 | 14:01:40.314 | `state=CLEANED`, SHA `31da0a018fe538e4d0bffb0d565fd9b05468f818a97de968309406df044420ae` |
| `r23002-p2m-round54-gzqkys` | 14:28:05.244–14:29:43.869 | 14:42:47.980 | `state=CLEANED`, SHA `4a1ab7d40a2d569a8afe3c69c2975af9fb5d41c7333d12ace64a333c78c08195` |
| `r23002-p2m-round55-adverse` | monitor only, 14:56:59.133 | n/a | no `state.json` or Platform scope; SHA `145352309228887829ac9a8ac6ef308603478f854b679bef4c4c0512571c5e96` |
| `r23002-p2m-round55-adverse2` | monitor only, 14:57:18.435 | n/a | no `state.json` or Platform scope; SHA `bcb5618b934388606590a2a287727a914814295080ac9b38a1b98f3f525484b4` |
| `r23002-p2m-round56-adverse` | 15:44:07.515–15:44:40.714 | 15:44:40.314 | `state=CLEANED`, SHA `1b78414aa106bff4ae8099feba2dcaf0d6ff5fb88d54c036ce850f79527123e0` |
| `r23002-p2m-round57-adverse` | 16:07:34.946–16:08:28.457 | 16:08:28.204 | `state=CLEANED`, SHA `806d536c48ead5d55a9b4fa85e409f3463b99bd94147e29014a16f169dd88bdf` |
| `r23002-p2m-round58-adverse` | 16:44:19.446–16:45:59.370 | 16:45:59.074 | `state=CLEANED`, SHA `308702226acbcec63a09c06817f909e45d15fea36d9c6af40510dec6f0975e19` |

The P2-Protocol roots are also later and disjoint: `r23002-p2p-round54-driver` 14:30:36.534–
14:30:40.214, `r23002-p2p-round54-diagnostic` 14:31:34.192–14:31:37.748,
`r23002-p2p-round55-protocol` 14:57:47.853–15:02:02.963, and
`r23002-p2p-round56-protocol` 15:45:48.189–15:50:16.032. Their driver evidence SHA-256 values
are respectively `d6c94752cf72deb87a957e21d6cdd33ea3625b7dab8782f342700d68a2bba4f5`,
`0ede48771d2a123db4fa949c0301896b7cb15c1ffc7e5d65c81bff76312d9930`,
`01b66610429e86ce6b11c8612772bc98cf77b54a9ac7ee6c23e8906f3fe2cecc`, and
`6260275f5d5afd17bf1fafcfc4092009412122565ff891646dc60fb6bef8f1d1`.

#### Erratum-D — P2 identity/resource disjointness — PASS

The state files and retained Protocol driver cleanup receipts were read without exposing tokens or
summaries. Every P2-created project, ontology, project key, and org-admin key is disjoint from `r`:

| P2 run | Project | Ontology | project-scoped key | org-admin key |
|---|---|---|---|---|
| `r23002-p2m-round53-anrawb` | `c6b772ae-767f-4079-ad6f-96f5b0f79ced` | `09d63928-afbc-40e8-bfa1-30a496d1fdfb` | `7d5c3abd-16e4-4de0-ab69-69eff8fc81ec` | `742db828-df19-4cc3-9ea1-b606b5b0a3a6` |
| `r23002-p2m-round54-gzqkys` | `5a51750e-a9f5-4237-8311-ea91253ff8e8` | `9228f42a-979c-4c29-baf2-8ab50003ace2` | `0a0aea6f-cda1-43cd-a1be-c5e5e7128b0b` | `1fa74413-1118-41ee-bb67-731941850c88` |
| `r23002-p2m-round56-adverse` | `db5b6e5e-0d58-4e4c-8ec4-92f69e2b1e9b` | `8fb01228-cd93-459b-93f1-5a0539e8440a` | `12f1ce3d-0ad4-426b-a6e8-658c33e9526a` | `23b02b0a-19dd-4a12-8977-750787eb052e` |
| `r23002-p2m-round57-adverse` | `66ad1c3a-4eb5-4054-ba6b-d73b690a1791` | `fa5ce866-9e4b-42ef-ab82-865a217fbe44` | `0f4c4969-8c06-4524-804b-cb4349d2a91d` | `01d27d93-6f5f-4aa3-9b0d-6de79e0d9e98` |
| `r23002-p2m-round58-adverse` | `54595da3-e7c9-4582-b22d-97ac5698179b` | `1552e7e2-7266-47f7-8d0a-a61499abaaca` | `bd0feadb-ebf6-49ff-a8cc-fdd884d647b6` | `e4b08d09-249f-4898-9fab-952c07219f34` |

P2-Protocol run IDs and retained identity evidence are:

| P2-Protocol run | Project | Ontology / Session / Lease IDs | project key / org-admin key | driver evidence |
|---|---|---|---|---|
| `r23002-p2p-round54-diagnostic` | `52934f8e-41cd-4dcc-a447-daa528c411ca` | not retained; cleanup says ontology/session absent/terminal and Lease auto-released | `b3971ba1-22ec-41c7-8d59-9aa1a9d543f0` / `05eebedb-18a5-4e7f-9e38-6035e106390c` | `evidence/p2-protocol-driver.jsonl`, SHA `0ede4877…d9930` |
| `r23002-p2p-round54-driver` | `ff185eda-0d61-462c-935f-77b0168c3f28` | not retained; cleanup says ontology/session absent/terminal and Lease auto-released | `e4f017d2-c2c1-4263-9ad4-bbb58dd7399d` / `794a8aa3-16b1-4ece-bc0a-2600166e0051` | SHA `d6c94752…a4f5` |
| `r23002-p2p-round55-protocol` | `a01ffa72-4c30-486b-8a03-ef37b65bf73b` | not retained; cleanup says ontology/session absent/terminal and Lease auto-released | `6a9e0e01-03ab-434d-a4ee-d531236e1407` / `00eef850-9583-4827-a843-c713d9e10d43` | SHA `01b66610…2cecc` |
| `r23002-p2p-round56-protocol` | `b5748887-431a-4778-8c40-5a7de2b0c02f` | not retained; cleanup says ontology/session absent/terminal and Lease auto-released | `9f228a57-f25e-429c-aeb9-91a367d9308c` / `30a75525-c48a-4d88-9bc3-ebfbce78b49e` | SHA `6260275f…f1d1` |

The two Round 55 monitor-only IDs have only their `evidence/p2-monitor.jsonl` records and no
`state.json`, Platform scope, or key/Session/Lease identity. For every scoped P2 run, cleanup
evidence records `session_terminal=true`, `lease_auto_released=true`, authenticated DELETE `204`,
and zero Project/Ontology/Session/Lease/key residuals. No P2 identity equals any `r` identity:
Project `dfd7fe8e-15ab-4432-9c67-4d8348d61122`, Ontology
`bf512947-d224-46d0-85b6-5723711af0e4`, Session `62f4967a-c9e7-4715-ab5d-6af8a3bbd241`, Lease
row key (Ontology) `bf512947-d224-46d0-85b6-5723711af0e4`, or model key
`96a1973c-cf53-4f5b-a86f-7e51247cb1d9`.

#### Erratum-E — independent read-only Platform API/DB and process/log checks — PASS

The following reads were performed with no write verb or mutation:

```bash
curl -H 'Authorization: Bearer [loaded local read credential]' -sS \
  http://127.0.0.1:8001/api/projects/dfd7fe8e-15ab-4432-9c67-4d8348d61122
curl -H 'Authorization: Bearer [loaded local read credential]' -sS \
  http://127.0.0.1:8001/api/ontologies/bf512947-d224-46d0-85b6-5723711af0e4/workspace-context
curl -H 'Authorization: Bearer [loaded local read credential]' -sS \
  http://127.0.0.1:8001/api/build-sessions/62f4967a-c9e7-4715-ab5d-6af8a3bbd241
cd backend && .venv/bin/python - <<'PY'
# SQLAlchemy SELECT-only reads of ProjectModel, OntologyModel, BuildSessionModel,
# OntologyLeaseModel, BuildCheckpointModel, ModelingBatchModel and ApiKeyModel.
PY
```

The API returned `200` for all reads: the `r` Project and Ontology still exist, Ontology status is
`draft`, and workspace state is `ready`. The Session remains `active`, revision `2`, client ID
`r23002-real-20260801r`, with one initial checkpoint; the Lease row is the same Ontology-scoped row,
now API-reported `expired` (DB `expires_at=2026-08-01 00:12:24.498190+00:00`, `released_at=NULL`),
and the r model key `96a1973c-cf53-4f5b-a86f-7e51247cb1d9` remains active with `model` scope. The
DB contains seven `r23002` batches (six `applied` plus the retained `r23002-invalid-probe` open
batch), which is the expected failed-written historical scope and not a P2 resource.

The read-only process check was:

```bash
ps -eo pid=,args= | rg 'r23002-(real-20260801r|real-20260801p|p2m-round5[3-8]|p2p-round5[4-6])' | rg -v 'rg '
journalctl --user -u ontology-platform.service \
  --since '2026-08-01 13:40:00' --until '2026-08-01 16:50:00' --no-pager -o cat |
  rg 'c6b772ae|09d63928|5a51750e|9228f42|db5b6e5e|8fb01228|66ad1c3a|fa5ce866|54595da3|1552e7e2|dfd7fe8e|bf512947|r23002-real-20260801r|r23002-real-20260801p'
```

No matching `r`, `p`, or P2 run process remained. The 45 matching service-log lines in the P2
window are P2-created-ID POST/GET/DELETE records (including `204` then `404` for deleted P2 scopes);
no `r` Project/Ontology ID or `r` run ID appears in that window. This independently corroborates the
filesystem non-overlap and the cleanup receipts without relying on a launcher summary.

#### Erratum-F — impact assessment, defect, and release decision — PASS

P2 semantic, P2-monitor, and P2-Protocol conclusions remain independently valid. These P2 runs have
no R2.3-002 business semantic start, their platform identities are disjoint from `r`, their retained
cleanup is complete, and the Round 58 C67 monitor PASS plus Round 56 C68 Protocol PASS are unchanged.
The stale `p` path therefore affects only the old-run protection assertion; it does not turn either P2
subgate into a failure and does not authorize a fresh semantic start.

**D58-E01 — Medium, stale protected-target reference.** Reproduction: inspect the protected hash
assertions at Test Plan lines 3302–3305, 3410–3413, and 3631–3632, then compare the immutable
ledger lines 70–80 and authoritative closure references above. Expected: every future protected
old-run hash/mtime check names unclosed target `r`; actual: those later assertions name already
closed-control `p`. Actual P2 evidence and the read-only audit show no write to `r`; the defect is
documentation/test-reference risk, not a product or P2 runtime defect. Minimum remedy is to bind all
future protected-target checks to `r` and retain `p` only as historical closed-control evidence; no
developer code repair or P2 rerun is recommended.

**Round 58 erratum conclusion: PASS.** The evidence is sufficient to authorize the Delivery Agent to
execute the already-reviewed B old-`r` closeout under the established order. This tester did not enter
B, did not append a ledger terminal event, and did not perform cleanup. After B, the existing order
remains `r` terminal classification -> `r` closeout -> independent P2 PASS (already established) ->
tranche/baselines/repair authorization -> any fresh reservation/start. Future protected target is
fixed to `r`; no pre-P2 `r` hash is asserted retroactively.

### Round 59 — v2 retrieval-contract amendment and remaining-start gate (planned)

This is a future implementation/test gate, not a result for `s`, P2, `r`, or any new run. It
supersedes only the active v1 candidate/proof, retrieval-completion, evidence, and cursor assertions
where they conflict with the following v2 cases. `s` remains retained `platform-contract BLOCKED`:
the 48 materialized business facts do not offset 0/48 mechanical per-assertion Evidence bindings,
30/30 empty entity/relation Evidence arrays, or its unconsumed truncated query cursor. No test may
recover `s`, write post-hoc Evidence to it, append a tranche, or make a semantic start.

| Case | Scope and setup | Expected mechanical evidence / PASS condition |
| --- | --- | --- |
| C74 candidate v2 canonical provenance | Unit/service fixtures construct attributed Modeling deliveries with `candidate-required-assertions/v2`. Each item has exactly `assertion_id, graph_role, subject, predicate, object, object_kind, object_datatype, object_language, evidence_citations`; each citation has exactly `source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id`. | Stable sorted/unique item and citation bytes; SHA-256 semantic/candidate digest recomputation. Missing/duplicate assertion ID, missing/empty citation, non-released owner-answer ID, platform IRI/ID/receipt/fact field, ontology Evidence individual, FNV digest, extra field, or any digest drift FAILs closed before apply. |
| C75 receipt term binding and RDF vocabulary | Generated-IRI apply receipts cover resource outputs and relation-delta facts. Bind each candidate term with exactly `assertion_id, term_position, candidate_term, binding_kind, client_item_id, batch_id, resource_output_iri`; materialize actual terms and recompute SHA-256 `materialized_digest` from candidate digest + sorted bindings + sorted quads. | `binding_kind=resource_output` requires its own nonempty formal receipt IRI; `binding_kind=relation_delta` requires JSON-null output IRI plus its own applied delta. No label lookup is accepted. Tests cover IRI, language literal, RDF 1.1 plain literal, and actual `xsd:string`; plain/xsd:string compare only by permitted lexical no-language semantics while their fact IDs use different actual platform terms. Missing/ambiguous/duplicate binding, receipt mismatch, drift, or invented IRI FAILs. |
| C76 per-assertion platform Evidence gate | For every candidate assertion, Protocol writes inline/associated Evidence and verifies a sorted `evidence_bindings` record with exactly `assertion_id, evidence_citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id`. | An actual platform `EvidenceReference` is linked to the exact fact/receipt and visible in the returned lineage. Empty entity/relation evidence arrays, warning `missing_evidence`, ontology-resource impersonation, wrong fact/item/batch, duplicate/missing binding, or a write attempted before all required citations bind FAILs this workflow. The test must also prove the generic backend apply behavior is not globally tightened. |
| C77 deterministic full pagination | Fixture supplies multiple match and context pages with overlapping stable IDs, plus negative truncated/degraded/warning/non-null cursor variants. The v2 `pagination` proof has exactly `schema_version, streams`; each stream has `stream_kind, pages`; every page has `request_cursor, next_cursor, returned_item_ids, truncated, degraded, blocking_warnings, response`. | Tool/protocol evidence shows each cursor request in order through null, cross-page union/de-dup by stable identity, and no contradictory duplicate content. Any unconsumed cursor, `truncated=true`, `degraded=true`, or nonempty blocking warning prevents complete/final reporting; an Agent prose claim cannot override it. |
| C78 verifier transition and generic lineage target | Adapter/Broker tests inject native verifier success, `failed`, JSON-RPC `-32602`, other error envelope, absent data, and `data.complete=false`; fixtures include an ObjectProperty resource and relation fact that share superficially similar decorations. | Only a success envelope without error and `data.complete=true` may transition `fallback_required -> fallback_satisfied`; every other case remains required and Broker rejects terminal report. Lineage records have exactly `assertion_id, fact_id, quad, target, response`; target exactly `target_kind, target_id`, with ObjectProperty=`resource` and relation fact=`statement`. Decoration/label selection or target mismatch FAILs. |
| C79 P2a generated-IRI + evidence integration | Independent no-semantic-start fixture drives the production Protocol/receipt/read/verifier path against one owned disposable generic scope. It contains 48 representative assertion categories but no business-answer Judge, and performs no TeamRunner start, StartLedger reservation, `semantic_start`, or reuse of `s`. | Retain safe unmodified receipt/read envelopes, v2 candidate digest, term/materialized/evidence-binding digests, all 48 assertion IDs, actual EvidenceReference IDs, pagination streams, native verifier success envelope, and cleanup proof. It must demonstrate C74–C78 end-to-end and all named negative branches fail closed. Independent tester PASS is required before `t`; mock-only evidence is insufficient. |
| C80 sole fresh producer `t` | Only after C79 independent PASS, verify ledger/read-only authorization shows remaining budget exactly one and no newly appended tranche, then use a new run/Project/Ontology/Sessions/Lease/credentials. | `t` retains immutable v2 Modeling delivery, full receipt-to-term/Evidence/lineage/pagination proof, governed complete retrieval, C→B→A, all three terminal+settled, cleanup/evidence freeze, same tester Phase A PASS, deterministic handoff, and fresh-session Phase B PASS. Any missing assertion evidence, incomplete pagination, failed verifier, or any failure is final: no retry or post-hoc repair. |

#### Round 59 acceptance order

1. Implement and run focused C74–C78 regression checks with no Platform/ledger semantic-start mutation.
2. Run independent C79 P2a; it must finish, clean its owned disposable scope, and PASS all v2 proof
   and fail-closed assertions.
3. Independently verify `s` remains BLOCKED/retained and the ledger's sole remaining semantic-start
   budget is unchanged; do not append a tranche.
4. Only then start fresh `t` once. The independent tester evaluates the evidence in C80 order; Phase A
   precedes handoff and the same tester opens a fresh Session for Phase B.

Round59 non-goals remain explicit: no Judge, Consumer, mutation/recovery suite, UI, backend table,
historical Evidence backfill, or domain-specific read-model branch. A future generalized evidence
productization effort must be separately refined and cannot be used to postpone the one bounded v2
repair path.

### Round 60 — plan-review correction for resolver, selector, pagination, and C79 matrix (planned)

Round60 supersedes Round59 C74–C80 only where its exact fields and gates below are stricter. It is
not an execution result. No case may mutate `s`, append a ledger tranche, or start `t`.

| Case | Setup | Required PASS evidence and negative assertions |
| --- | --- | --- |
| C81 deterministic Evidence resolver | Supply staged immutable manifest artifacts and immutable `outer-user` records with project/authorization/release binding. Invoke only Protocol's deterministic resolver for all source and owner-answer citations. | Resolver returns exactly `document_name, exact_excerpt, source_locator, artifact_sha256, excerpt_sha256`; source must be a manifest member and answer must match released `owner_answer_id`. Reject arbitrary path, hash/excerpt/locator drift, unauthorized project/release/permission, absent/unreleased answer, ambiguous record, and attempt to let an Agent choose text. Prove no Batch apply occurs if any of 48 citations fails. |
| C82 Evidence identity/cardinality/transaction | Use same citation across multiple assertions, multiple citations on one assertion, duplicate retry, partial association failure, and cross-project reuse fixtures. Canonical citation fields are exactly `source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id`; sorted tuple order and SHA-256 digest are recomputed. | Reference identity is exactly `(project_id, source_artifact_sha256, source_locator, excerpt_sha256)` and only same-boundary idempotent reuse succeeds. Every assertion×citation has one `evidence_bindings` row exactly `assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id`; verifier proves one-to-one full-set coverage. Duplicate row/key, aggregate-only proof, missing/substituted/drifting row, cross-project/release reuse, or partial dry-run/create transaction FAILs before apply. |
| C83 multi-delta selector and materialized digest | Generate resource, relation, literal and vocabulary candidates with multiple normalized-delta quads, create-entity system quads, duplicate-looking literals, plain/xsd:string/language/boolean values, and receipt attempts. Bind using exact `assertion_id, term_position, candidate_term, binding_kind, client_item_id, batch_id, applied_attempt_id, quad_digest, delta_index, resource_output_iri`. | Kinds are only `literal_delta|resource_output|relation_delta|vocabulary`; each non-vocabulary receipt tuple selects exactly one applied delta. System quads are excluded; no label/decorate inference. Plain/xsd:string has semantic comparison only and raw stored term in quad/fact ID; lang/typed values strict. Native proof includes required top-level `materialized_digest`, SHA-256 of candidate digest + ordered term/evidence-binding digests + ordered quads. 0/>1 match, FNV, null/wrong receipt IRI, selector/digest drift, or omitted top-level digest FAILs. |
| C84 signed pagination chain | Fixture produces independent match/context multi-page streams with valid/invalid signed cursors and response metadata; vary principal, project, scope, ontology IDs, query/filter/depth/limits, workspace/source signatures, duplicate IDs, and context roots. Page fields are exactly `stream_kind, request_fingerprint_sha256, page_index, request_cursor, next_cursor, response_digest, root_match_ids_digest, response`. | Recomputed fingerprint binds all named request/scope fields. First cursor null, subsequent cursor equals preceding next, index contiguous, and only null closes each stream. Final context roots bind to de-duplicated match union. Bad cursor/signature/fingerprint/scope/stream, cross-stream reuse, contradictory duplicate, non-null terminal, truncated/degraded/blocking warning all keep retrieval incomplete. This validates helper metadata; it does not require a backend query algorithm change. |
| C79-R60 frozen 48-row matrix (mandatory P2a gate) | Freeze one SHA-256-addressed 48-row assertion-ID/category matrix derived from approved candidate/source material. Each row explicitly declares source/citation requirement, expected resolver result, resource/relation/literal/vocabulary binding kind, plain/xsd:string/language/boolean category, lineage target_kind, and match/context coverage. | Matrix IDs/categories cannot be arbitrary synthetic business assertions or answer keys. P2a may apply a minimal generated-IRI representative subset only, but it must statically resolve and coverage-check all 48 rows and execute representative Evidence/receipt/lineage/pagination branches. Missing row/digest/dimension, invented 48, uncovered category, unresolved citation, or missing negative branch is FAIL. Independent C79-R60 PASS is required before `t`. |
| C80-R60 unique fresh producer | After C81–C84 and independent C79-R60 PASS, read-only verify `s` remains BLOCKED and exactly one authorized start remains with no new tranche. | Fresh `t` resolves all actual 48 citations and successfully completes EvidenceReference/association precondition before its first apply; then retains v2 receipt/selector/digest/pagination/verifier/C→B→A/Phase A/handoff/fresh Phase B evidence. Any failure is terminal with no post-hoc `s` repair, `t` retry, or tranche append. |

#### Round 60 mandatory order

1. Focused C81–C84 regressions pass without a semantic start.
2. Independent P2a performs C79-R60 matrix validation and minimal generated-IRI integration; it must
   preserve all 48 matrix inputs/evidence digests and clean only its own disposable scope.
3. Independently verify C79-R60 PASS, retained `s` BLOCKED, and no ledger change/new tranche.
4. Only then consume the one remaining start for `t` under C80-R60. No earlier PASS substitutes for
   the matrix or all-48 pre-apply Evidence resolver gate.

### Round 61 — inline Evidence closure and frozen matrix gate (planned)

Round61 keeps the Round60 selector/pagination acceptance and supersedes only its resolver/bridge and
matrix details. It adds no tool, SAFE protocol surface, backend table, runtime action, ledger event, or
semantic start. Cases C79/C80 are revised below; prior failed rounds remain unchanged.

| Case | Setup | Required PASS evidence and negative assertions |
| --- | --- | --- |
| C81-R61 inline candidate citation mapping | Build attributed Modeling candidate items with explicit citations exactly `document_name, excerpt, source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id` (owner nullable). For owner answers, retain the immutable outer-user record exactly `owner_answer_id, project_id, run_id, authorization_id, release_id, question_delivery_id, delivery_id, text, released_at`. Submit through existing `submit_modeling_batch` item `inline.evidence` only. | Protocol performs only canonical hash/text/locator checks and maps every citation to every carrying item; it never reads or guesses source. Candidate citation missing/duplicate/hash/text/locator mismatch, non-unique mapping, owner/project/release mismatch, or any new create/associate tool/SAFE surface fails closed. |
| C82-R61 dry-run all-item Evidence gate | Use all matrix-required citations and inspect formal `dry_run` `operation_plan.evidence` and `operation_plan.missing_evidence` before any apply. | Every item/citation is covered exactly once before the first `apply_atomic`; any missing/duplicate/mismatch or `missing_evidence` yields zero first apply. A write is not accepted merely because a later read might recover Evidence. |
| C83-R61 existing transaction/recovery boundary | Exercise apply with PostgreSQL EvidenceReference + modeling-item association + lineage + finalize and inject Oxigraph failure; also test rule-only/delete-only items and failed `t`. | The four PostgreSQL operations commit in one DB transaction; Oxigraph failure enters existing `recovering` and does not claim instant cross-store zero-partial. Rule/delete-only items do not count toward 48 asserted lineage. Failed `t` has no retry. No new Evidence API/tool is observed. |
| C84-R61 post-apply Evidence verifier | Read statement occurrence → modeling-item origin → EvidenceReference after platform fact IDs are generated. | `evidence_bindings` rows have exactly `assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id`; verifier recomputes full one-to-one coverage and idempotency. It rejects preprovided fact/reference assumptions, duplicate/missing/replaced/drifted rows, and cross-scope reuse. |
| C79-R61 frozen matrix artifact and P2a gate | Freeze `modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json` with exact top fields `schema_version, source_run_id, source_candidate_digest, rows, matrix_digest`; schema/version is `r2-3-002-proof-v2-assertion-matrix/v1`, `source_run_id` is exactly `r23002-real-20260801s`, rows sort by assertion ID, and matrix digest is SHA-256 of the compact sorted-key object excluding itself. Each of 48 rows has exactly `assertion_id, subject, predicate, object, object_kind, object_datatype, object_language, approved_citations, binding_category, literal_category, target_kind, p2a_branch_id, match_coverage, context_coverage`, with approved citations using the six exact citation fields. | Implementation derives the artifact from retained `s` rev7 handoff + approved sources; independent tester verifies source candidate digest, all 48 IDs/categories/citations, and matrix hash. P2a applies only a minimal representative generated-IRI subset but statically validates all rows and executes resource/relation/literal/vocabulary, plain/xsd/lang/boolean, inline Evidence, statement lineage, pagination, and both target-kind branches. Arbitrary synthetic48, wrong path/schema/source candidate/assertion/citation/category, row omission, digest drift, or missing negative branch FAILs. |
| C80-R61 matrix-bound unique fresh `t` | After independent C79-R61 PASS, verify exact `proof_matrix_path` + `proof_matrix_digest` in TeamRunner baseline, repair authorization/reservation/start expected digest, and `t` candidate proof `matrix_binding` (exactly those two fields); verify `s` remains BLOCKED and budget remains one with no new tranche. | StartLedger rejects semantic start for wrong/missing matrix path/hash/source candidate or absent P2a PASS. With exact match, fresh `t` may start once; its assertion IDs/scope/citations must equal matrix rows before first apply, and all 48 inline Evidence operation-plan entries must pass. Any failure is terminal: no post-hoc `s` evidence, retry, or new tranche. |

#### Round61 acceptance order

1. Run C81-R61 through C84-R61 focused checks with no semantic start.
2. Generate and independently verify the immutable 48-row matrix artifact; run P2a minimal real apply plus
   static all-row validation, and retain its evidence/cleanup.
3. Confirm C79-R61 PASS, exact matrix hash in all expected baseline/authorization/reservation evidence,
   retained `s` BLOCKED, and exactly one remaining start with no ledger tranche append.
4. Only then consume that one start for `t` under C80-R61. Phase A source fidelity checks precede handoff;
   the same tester uses a fresh Session for Phase B. Any failed gate stops the workflow.

### Round 62 — implementation-visible evidence map and StartLedger binding (planned)

Round62 preserves Round61's inline transaction, term, pagination, and matrix-row rules. It makes the
remaining implementation surfaces explicit without adding a tool, table, ledger event, tranche, or
runtime operation. C80 is superseded below only for gate-binding details.

| Case | Setup | Required PASS evidence and negative assertions |
| --- | --- | --- |
| C81-R62 candidate-local map | After attributed candidate receipt, before submit, generate run-local immutable `evidence/candidate-item-evidence-map.json` with exact top fields `schema_version, run_id, candidate_digest, rows, map_digest`; schema is `r2-3-002-candidate-item-evidence-map/v1`; rows exact `assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256`, sorted/unique; map digest excludes itself. | Map path is regular, run-local, non-symlink/non-escaping, hash matches canonical bytes, and rows use candidate-provided values only. Missing/extra/duplicate row, wrong candidate digest, path escape, raw-source read/guess, or map mutation after receipt fails and prevents submit/apply. Map path+digest are in candidate proof and stable baseline. |
| C82-R62 dry-run evidence visibility | Use existing Batch request inline `evidence[{document_name,excerpt}]` and inspect additive `_attempt_response`/schema `operation_plan.evidence` rows exact `client_item_id, document_name, normalized_excerpt_sha256, dedupe_identity`. | Legacy no-evidence attempts may omit/return empty; R2.3 dry-run must expose safe rows without extra raw source. Protocol exact-projects map to plan: each `(client_item_id,document_name,excerpt_sha256)` once, stable dedupe identity, zero missing/duplicate/extra/hash/text mismatch and no `operation_plan.missing_evidence` before first apply. Batch request schema and non-R2.3 consumer behavior remain unchanged. |
| C83-R62 owner-answer identity/fidelity | Exercise Runner `outer-user.jsonl`, RuntimeDelivery/`receive_outer`/prompt forwarding, and candidate owner citation. Record exact fields `owner_answer_id, project_id, run_id, authorization_id, release_id, question_delivery_id, delivery_id, text, released_at`; owner ID is `owner-answer-` + canonical SHA-256 over run/project/question/text. | Host tester recomputes ID/hash and checks standing authorization, release delivery, project/run, exact text and UTC release across outer-user/transport records. Duplicate prompt cannot mint a second ID; mismatched owner/release/authorization or source document citation fails. Protocol does not read staged manifest. |
| C84-R62 apply/recovery boundary | Inject a PostgreSQL EvidenceReference/modeling-item association/lineage/finalize failure and an Oxigraph cross-store failure after existing apply path; include rule-only/delete-only items. | No pre-created Evidence/fact IDs are required. The four PostgreSQL operations are one DB transaction; Oxigraph error follows existing `recovering`, with no instant zero-partial claim. Postapply verifier reads occurrence→modeling-item origin→EvidenceReference and fills exact evidence binding row. Rule/delete-only does not satisfy asserted 48. Failed `t` has no retry. |
| C79-R62 P2a pass artifact and matrix gate | Implementation creates tester-owned `workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` with exact fields `schema_version, matrix_path, matrix_digest, source_run_id, p2a_run_id, verifier_complete, evidence_hashes, tested_at`; schema `r2-3-002-proof-v2-gates/p2a-pass/v1`, source run `r23002-real-20260801s`, external canonical SHA-256 pass digest. | Independent tester checks exact matrix path/hash/source, sorted 64-hex evidence hashes, true verifier_complete, UTC tested_at, and P2a real representative apply plus static all-48 matrix validation. Missing/wrong path, symlink/escape, bad canonical hash/schema/source, false verifier, evidence-hash mismatch, wrong P2a run, or arbitrary synthetic48 fails. |
| C80-R62 pre-start gate and binding propagation | Extend existing `authorize_repair`, `reserve`, `mark_semantic_start` payloads with R2.3-only exact `gate_binding={matrix_path,matrix_digest,p2a_pass_path,p2a_pass_digest,source_run_id}`; old run/P2 payloads without it remain compatible. Task/profile has pre-launch exact `expected_matrix_binding` (same five fields), and baseline includes matrix/P2a/call-site hashes. | Repair writes first binding; reservation byte-equals prior repair; mark byte-equals reservation; semantic_start event stores same binding. Runner preflight reads canonical files and rejects missing/wrong path, symlink/escape, hash/schema/source/P2a verifier/evidence mismatch, gate-binding mismatch, task/profile mismatch, or candidate matrix path/digest mismatch before writing semantic_start. No new event/tranche; cap18, consumed17, remaining1. |

#### Round62 mandatory order

1. Run C81-R62 through C84-R62 with no semantic start and retain only safe map/plan/identity evidence.
2. Create and independently PASS C79-R62 P2a artifact against the fixed 48-row matrix; no ledger event or
   tranche is added.
3. Verify C79-R62 plus exact gate binding in baseline, repair authorization and reservation; verify `s`
   remains BLOCKED and remaining budget is one.
4. Only then allow C80-R62's preflight and one `t` semantic start. Any failed preflight rejects without
   writing `semantic_start`; `t` failure remains terminal and cannot retry.

### Round 63 — citation groups and split lifecycle gates (planned)

Round63 retains the Round62 map/dry-run/ledger surfaces and supersedes only their row projection and
lifecycle timing. No Batch locator/owner field, new tool/table/event, or semantic start is added by this
plan amendment.

| Case | Setup | Required PASS evidence and negative assertions |
| --- | --- | --- |
| C81-R63 citation-group map | Build a map with one row per assertion×citation, exact row fields `assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256, inline_evidence_identity, citation_group_digest`; use distinct citation digests sharing document/excerpt and exact duplicates. | `inline_evidence_identity` equals SHA-256 of canonical `{document_name,normalized_excerpt_sha256}`; group is `(assertion_id,client_item_id,inline_evidence_identity)` and group digest is SHA-256 over sorted unique citation digests. Exact duplicate digest/identity fails; distinct digests in same group remain visible. Map rows/path/digest remain immutable. |
| C82-R63 dry-run group projection | Feed existing Batch inline `evidence[{document_name,excerpt}]`; inspect safe dry-run plan rows exact `client_item_id, inline_evidence_identity, dedupe_identity`. | Protocol projects map by group and proves exactly one plan row per client-item×inline identity×dedupe identity, with no missing/extra; citation-level multiplicity is not incorrectly demanded from the plan. Wrong group, extra/missing identity, unstable dedupe, or locator/owner smuggled into Batch request fails before first apply. |
| C83-R63 postapply group Evidence | Read statement occurrence→modeling-item origin→EvidenceReference for multiple citations in one group and reused references across assertions. | Every citation row has exact `assertion_id,citation_digest,evidence_reference_id,client_item_id,batch_id,fact_id,inline_evidence_identity,citation_group_digest`; same/corresponding reference and correct group digest are retained. Verifier rejects omitted/replaced citation, wrong group/reference, duplicate row, or aggregate-only coverage. |
| C84-R63 owner-answer sequence | Simulate Runner question receipt, user answer, answer delivery/release creation, fsync, Modeling send, and send failure. | Owner ID is fixed prefix `owner-answer-` plus SHA-256 of canonical UTF-8 `json.dumps({"run_id":...,"project_id":...,"question_delivery_id":...,"text":...}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, independent of release; record fields are exact nine-field outer-user schema; answer delivery ID is `release_id`, and Modeling receives same owner ID/release/text only after fsync. Tester binds question delivery, answer delivery/release, text, project/run/authorization, and record. Send failure retains record, fails run, and never reuses ID; no duplicate prompt minting. |
| C79-R63 mark-before-start gate | With matrix/P2a artifacts, task/profile expected binding, and ledger repair/reservation binding valid but no live candidate/map, call `mark_semantic_start` preflight. Also remove/corrupt each artifact and mismatch each binding. | Valid pre-start gate succeeds without requiring candidate/map/map digest. Missing/wrong matrix/P2a/path/hash/source/verifier, task/profile mismatch, or repair→reservation mismatch rejects before writing semantic_start. Baseline contains actual matrix/P2a digests plus map/proof schema/path/callsites, never nonexistent map digest. |
| C80-R63 candidate-before-submit/apply gate | After valid semantic_start, deliver candidate variants with wrong assertion IDs/scope/citations/matrix binding and a valid candidate. Observe first submit (including dry_run), map generation, and plan comparison. | Wrong candidate fails before first submit/apply; start is already consumed and cannot retry. Valid candidate creates immutable map, records map digest in runtime proof/evidence, then dry-run group projection controls first apply. Plan mismatch blocks apply only after submit/dry-run; no semantic-start event is rewritten. |

#### Round63 acceptance order

1. Pass C81-R63 through C84-R63 without a semantic start.
2. Pass C79-R63 using only pre-start matrix/P2a/task/profile/ledger evidence; do not wait for or inspect a
   live candidate/map.
3. Consume the one legal semantic start, then apply C80-R63 candidate gate before any submit/apply and
   group-projected dry-run gate before first apply. Any mismatch is terminal with no retry.

### Round 64 — independent P2a Protocol execution and C74-C84 regression (FAIL)

This round used the existing test plan and was executed by the independent tester on 2026-08-01
(Asia/Singapore). It did not modify product code, requirements, design, delivery records, the StartLedger,
or the retained `s` scope. It did not enter TeamRunner, perform a semantic start, run C→B→A, or reuse any
previous run. The tester-owned P2a gate path was absent before and after the attempt.

#### Scope, preconditions, and static checks

The service preflight passed: `systemctl --user --no-pager --full status ontology-platform.service`
reported `active (running)`, `curl --fail http://127.0.0.1:8001/api/health` returned HTTP 200
`{"status":"ok"}`, and `curl --fail http://127.0.0.1:5173/` returned HTTP 200. The immutable
StartLedger SHA-256 was
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, unchanged by this round. The
frozen matrix validated 48 rows, matrix digest
`db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b`, and source candidate digest
`7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`. The fixed gate file
`workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` and its parent directory were absent;
the unique run directory `workspaces/p2a-protocol-runs/r23002-p2a-round64-201608` was also absent.

The focused regression commands were:

```bash
uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'
# 152 passed
cd backend && uv run pytest -q \
  tests/test_modeling_batches_api.py \
  tests/test_modeling_batches_service.py \
  tests/test_semantic_context_query.py \
  tests/test_semantic_read_model_stage2_execution.py
# 121 passed, 7 deprecation warnings
```

These checks covered the C74-C78 proof/mechanics, matrix, Protocol MCP schema, owner/gate binding and
legacy compatibility checks, plus the C81-C84 operation-plan, generic target-kind, Evidence and semantic
read regressions. Both commands passed without a platform mutation.

#### Single real P2a attempt

The one permitted real attempt was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round64-201608 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

Expected: the Protocol-only Codex adapter/broker would start the required native MCP servers, deliver the
generated-IRI candidate, observe dry-run and apply receipts, complete retrieval/pagination and the native
v2 verifier, accept one terminal report, and then clean its disposable scope. Actual: the process exited
with status 1 after 3.637 seconds at Protocol roster startup. Codex app-server returned `-32603` for
`thread/start`: `required MCP servers failed to initialize: protocol_mechanics: handshaking with MCP
server failed: connection closed: initialize response`. Consequently there was no candidate delivery or
receipt, dry-run, apply, retrieval, native verifier completion, or accepted Protocol report. No PASS
artifact was written.

Retained run-local evidence is regular, run-local, and contains no forbidden provenance strings:

| Evidence | SHA-256 |
| --- | --- |
| `workspaces/p2a-protocol-runs/r23002-p2a-round64-201608/baseline-manifest.json` | `e417d515c43d843cc5c6c178d3a8e2bc69dc01b442d0051d69820fc8063b2912` |
| `workspaces/p2a-protocol-runs/r23002-p2a-round64-201608/evidence/app-server-events.jsonl` | `03918837a0b6f449539faf0b7bc87d483ef1d37e3824f026941e1dc9176d8e14` |
| `workspaces/p2a-protocol-runs/r23002-p2a-round64-201608/evidence/p2a-protocol-driver.jsonl` | `44df60c9a3184a0491814cab9f88520105a247bd38d5d117701b9b7ef58a136f` |

The driver evidence records `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted`
with authenticated HTTP `204`, `scope_cleanup_second_stage`, and `driver_stopped`. It records the owned
Project `ef573e2e-e018-4704-8f93-e8770a930475`, deleted project key
`ceae8a16-07ac-4cbf-a07a-430423def929`, and revoked bootstrap-admin key
`8a53eb70-7879-4ae2-aa5c-0a802e52baf7`. Independent read-only PostgreSQL checks after the run found
zero Project, Ontology, Build Session, Lease, or project-scoped-key rows for the P2a Project; the admin
key remained only as a revoked row, with the expected create/revoke/revoke audit records. No P2a process
remained. The official gate path remained absent and the StartLedger SHA remained unchanged.

#### Defect and conclusion

**D64-P2A-01 — High / blocking.** Reproduction: run the exact command above from a healthy local service
with the frozen contract and a new run ID. Expected: `protocol_mechanics` returns a successful MCP
`initialize` response and Protocol roster startup proceeds to candidate delivery. Actual: the required
server closes during initialize and app-server refuses to create the Protocol thread (`-32603`), so C79
cannot be independently accepted and C80/t is not authorized. Code inspection narrows the likely cause:
`CodexRuntimeAdapter._stage_protocol_retrieval_mcp` stages only `protocol-retrieval-mcp.py` and
`protocol_mechanics.py`, while the staged `protocol_mechanics.py` fallback imports the sibling `proof_v2`
module; the isolated `/opt` runtime has no staged `proof_v2.py`. This is a product/runtime defect to be
confirmed and repaired by the requirement developer; the tester made no fix.

**Round 64 conclusion: FAIL.** Static C74-C84 regressions and preflight passed, but the sole real P2a
attempt failed before Protocol initialization. No P2a PASS artifact exists, and no semantic start or
ledger mutation occurred. Do not proceed to `t`; repair D64-P2A-01 and request a fresh independent test
round before any P2a PASS gate or subsequent start.

### Round 65 — D64 runtime-asset retest and fresh P2a (FAIL)

This is an independent second test round on 2026-08-01 (Asia/Singapore), using the same test plan after
the D64 runtime-asset repair. Round64's failed run and evidence were retained unchanged. This round did
not modify product code, requirements, design, delivery records, the StartLedger, or the retained `s`
scope; it did not enter TeamRunner, perform a semantic start, run C→B→A, or enter `t`.

#### D64 repair validation and preflight

The service remained healthy: the user service was `active (running)`, backend `/api/health` returned
HTTP 200 `{"status":"ok"}`, and frontend `/` returned HTTP 200. The StartLedger SHA-256 remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`. The fixed gate file and parent
directory were absent, while the Round64 run directory remained present. The supplied handoff digest
was `3f161734deb738eb289674d666eac00497ad7f94f59de83658ee27996a1e8480`.

The focused checks were:

```bash
uv run --project backend python -m unittest \
  modeling_team.tests.test_proof_v2_runtime_asset \
  modeling_team.tests.test_matrix_artifact \
  modeling_team.tests.test_p2a_protocol_driver \
  modeling_team.tests.test_proof_v2 \
  modeling_team.tests.test_protocol_retrieval_mcp \
  modeling_team.tests.test_runner_r63 \
  modeling_team.tests.test_start_ledger_r63 \
  modeling_team.tests.test_contracts \
  modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_protocol_retrieval_mcp_assets_are_protocol_only_and_fd_bound \
  modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_mcp_preflight_requires_exact_protocol_and_non_protocol_servers
# 27 passed
```

The staged runtime check independently observed `runtime-assets/protocol/proof_v2.py` as a regular,
non-symlink file owned by UID 1000, mode `0600`, under a `0700` parent. Source, staged, and contract
SHA-256 all matched
`f26aa508af663cacfe4852b98f9334c980dee90091a23de6d4e12286c9b4f27e`; the mount path was
`/opt/proof_v2.py`. A subprocess using the staged wrapper/verifier/proof asset returned exit code 0 for
MCP `initialize` and `tools/list`; server name was `protocol_mechanics`, tool name was
`verify_scoped_retrieval_fallback`, and the v2 schema exposed `pagination`. A first local diagnostic
invocation targeted the wrong temporary wrapper path and produced only a tester harness JSON-decode
error; it created no repository, service, or P2a state and was corrected by the passing check above.

#### Single fresh real P2a attempt

The only fresh run in this round was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round65-1785587656 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run began at approximately `2026-08-01T20:34:54+08:00` and ended with exit status 1 after the
900-second bound (`elapsed_seconds=903.767`). It passed `driver_started`, `matrix_validated` (48 rows;
representatives `r23002-a009`, `r23002-a004`, `r23002-a008`, `r23002-a001`),
`protocol_roster_started`, candidate delivery/receipt, and `apply_observed` (`state=query_required`).
Candidate digest was
`ea32bff5596a9a7f2cb69c009d8c587b29138be628e631091b28104701da5169`; delivery IDs were `delivery-1`
and receipt `delivery-2`. Retrieval evidence recorded episode 1, followed by the complete generic
retrieval transition at episode 3. The process then stopped making progress and failed with
`P2a Protocol sequence did not complete before timeout`.

The required `dry_run_observed`, native v2 verifier completion (`fallback_satisfied`), and accepted
Protocol terminal report were absent. The retained `protocol-retrieval-gate.jsonl` contains submit,
validation, reasoning, and three semantic-query transitions, but no verifier transition. No PASS
artifact was written.

Run-local evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `db2919b1af8935e438038c9d6e5877c2f27b5b4c5da1b6b6012834ba860f22b8` |
| `evidence/app-server-events.jsonl` | `46d57d4dd3f504d48bfbea2be8f93281aa847d5d7555712bcd1abd0ff3d813a5` |
| `evidence/mcp-elicitations.jsonl` | `b51968fa0706b5343e95740e09150f4e6d87bf46b2fc66998f95c24eb64df986` |
| `evidence/p2a-protocol-driver.jsonl` | `bf38129f4169bb2940b7ae71422d100a7a8b8864e744bb13ff937089196ea5da` |
| `evidence/protocol-retrieval-gate.jsonl` | `2d335d1c12b9bc1f5a7e54c7d62446648e5b3a11a4b29d461a180c6a8ca2b3df` |

The driver recorded successful runtime credential destruction and two-stage scope cleanup. Owned
identities were Project `a850018e-2cdb-4386-bead-5d8d0ba981b6`, project key
`9dece116-b688-406c-88d1-cbebea0d5c70`, and bootstrap-admin key
`c7e89f38-f44e-4b8a-b253-3d3e424ddfdb`; authenticated DELETE returned `204`, Session was terminal,
Lease auto-released, and the second-stage admin key was revoked with retained audit evidence.
Independent read-only PostgreSQL checks found zero Project, Ontology, Build Session, Lease, or
project-scoped-key rows for this scope, zero active rows for either key, and exactly the expected three
create/revoke/revoke audit records. No run process remained. The official gate path remained absent, the
ledger SHA remained unchanged, and no forbidden provenance string appeared in retained run evidence.

#### Defects and conclusion

**D65-P2A-01 — High / blocking.** Reproduction: execute the exact fresh-run command above with a
healthy service and the repaired runtime asset. Expected: after generic retrieval reaches the fallback
branch, Protocol invokes the native `protocol_mechanics/verify_scoped_retrieval_fallback` with the full
v2 proof, reaches `fallback_satisfied`, and reports one accepted terminal result before the 900-second
bound. Actual: `protocol-retrieval-gate.jsonl` stops at episode 3 `generic_complete`; no verifier
transition or terminal result occurs, and the driver times out. This prevents C79-R65 PASS and leaves
`t` unauthorized.

**D65-P2A-02 — Medium / acceptance-blocking instrumentation gap.** The driver requires
`dry_run_observed` by counting `submit_modeling_batch` entries in run-local
`evidence/dynamic-tool-calls.jsonl`. The real run produced no such file, while the Protocol retrieval
gate independently records the `submit_modeling_batch` mutation transition and `apply_observed`. Thus
the run cannot prove the mandatory dry-run gate even when native MCP item completion shows the submit
path. The requirement developer should bind dry-run observation to the actual native MCP completion
receipt/operation plan (while retaining the exact compare-before-apply assertion), not to an unrelated
dynamic-tool callback file.

**Round 65 conclusion: FAIL.** D64's MCP initialization defect is fixed and the isolated runtime asset
checks pass, but the single fresh real P2a stalled after generic retrieval and timed out without native
v2 verification, dry-run proof, or terminal acceptance. Cleanup and no-mutation gates passed; no official
P2a PASS artifact exists. Do not proceed to `t`; repair D65-P2A-01 and D65-P2A-02, then request another
independent test round.

### Round 66 — 2026-08-01 D65 observation/dry-run repair retest and fresh P2a (FAIL)

This is an independent third P2a test round using the same test plan after the D65 observation and
authoritative dry-run-readback repair. It did not modify product or test implementation, the
requirements/design/delivery documents, the StartLedger, or retained producer `s`; it did not enter
TeamRunner, perform a semantic start, run C→B→A, or start `t`. The only real P2a run was
`r23002-p2a-round66-1785591466`.

#### Static checks and preflight

- The user service was `active (running)`; backend `/api/health` returned HTTP 200 `{"status":"ok"}`
  and frontend `/` returned HTTP 200. The frozen matrix validated 48 rows with matrix digest
  `db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b` and source candidate digest
  `7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`.
- D65/P2a/proof/MCP/isolation focused checks passed (`24 tests`):
  `uv run --project backend python -m unittest modeling_team.tests.test_d65_protocol_observation
  modeling_team.tests.test_p2a_protocol_driver modeling_team.tests.test_proof_v2
  modeling_team.tests.test_protocol_retrieval_mcp modeling_team.tests.test_runner_r63
  modeling_team.tests.test_start_ledger_r63 modeling_team.tests.test_contracts
  modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_protocol_retrieval_mcp_assets_are_protocol_only_and_fd_bound
  modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_mcp_preflight_requires_exact_protocol_and_non_protocol_servers`.
- The complete modeling-team baseline passed (`158 tests`, 2.437 seconds):
  `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`.
  The operation-plan/backend regression passed (`121 passed`, 7 deprecation warnings):
  `cd backend && uv run pytest -q tests/test_modeling_batches_api.py
  tests/test_modeling_batches_service.py tests/test_semantic_context_query.py
  tests/test_semantic_read_model_stage2_execution.py`.
- Before the run, the official gate path
  `workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` was absent, the unique run
  directory did not exist, and StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`. Retained `s` state SHA-256
  was `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round66-1785591466 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run started at approximately `2026-08-01T21:37:46+08:00`, exited with status 1 after the
driver-recorded `100.418` seconds, and passed only `driver_started`, `matrix_validated`,
`protocol_roster_started`, `candidate_delivered`, and `candidate_receipt`. The real Protocol path
then produced a candidate evidence-map file which the driver rejected before any authoritative
dry-run readback or apply. The terminal traceback is:

```text
ProofV2Error: candidate item evidence map has missing or extra fields
P2AProtocolDriverError: candidate evidence map is invalid
```

The rejection occurs in `_promote_candidate_item_evidence_map` while validating the exact v1 map
contract. Consequently `dry_run_observed`, `apply_observed`, `retrieval_observed`,
`native_verifier_completed`, and `protocol_report_accepted` are absent. No broker terminal result was
invented by the tester. The runtime-owned map is removed during cleanup, so the retained safe error
evidence does not claim which extra/missing key the Protocol emitted; the reproducible defect is the
real Protocol-to-driver map schema mismatch itself.

Run-local evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `61a98948d5a0a7c5fdc15c4be380713e989242ab53bf6ca95695e21ad58cede7` |
| `evidence/app-server-events.jsonl` | `e6624aaed1499d5a7788690e5beedcc7b76ecbb2dac8a2ca10135e7105cb4e1f` |
| `evidence/mcp-elicitations.jsonl` | `5fbfec23f8e58da6603f12a2ba2bfca34019611c584b6582b362b3b71892117b` |
| `evidence/p2a-protocol-driver.jsonl` | `7159ad5486f6aface526960d94d392db7e495710c06af1dec5941d9b5a817575` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted` with
authenticated HTTP 204, and `scope_cleanup_second_stage`; `cleanup_errors` was empty and
`driver_stopped` was recorded. The Session was terminal, the Lease auto-released, the project key
was non-active/revoked, the owned empty Project/Ontology was absent with residual counts all zero,
and the bootstrap-admin key was immediately revoked with its audit row retained. No P2a process
remained. The official gate path remained absent. The StartLedger SHA remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state SHA
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Defect and conclusion

**D66-P2A-01 — High / blocking.** Reproduction: run the exact command above with the frozen
contract and a fresh run ID. Expected: the real Protocol writes the exact
`r2-3-002-candidate-item-evidence-map/v1` map (top-level
`schema_version, run_id, candidate_digest, rows, map_digest`; exact citation-group row fields),
the driver promotes it, and authoritative dry-run/readback proceeds. Actual: the driver reaches the
real map and fails closed because its top-level fields do not match the exact contract. This blocks
C79-R66 before dry-run and leaves `t` unauthorized.

**Round 66 conclusion: FAIL.** D65's native-observation and idle-bound repairs were not reached by
the real acceptance path because the Protocol candidate-map producer is not aligned with the frozen
v1 map contract. Cleanup and no-mutation gates passed; no official P2a PASS artifact exists. Do not
proceed to `t`; repair only the Protocol map emission/contract alignment, run the focused regressions,
and request another independent fresh P2a round. The tester made no product fix and did not retry this
run.

### Round 67 — 2026-08-01 canonical Evidence-map writer retest and fresh P2a (FAIL)

This independent fourth P2a round reused the same test plan after the D66 canonical MCP writer
repair. It did not modify product or test implementation, requirements/design/delivery documents,
the StartLedger, or retained producer `s`; it did not enter TeamRunner, perform a semantic start,
run C→B→A, or start `t`. The only real P2a run was `r23002-p2a-round67-1785592807`.

#### Owned-surface digest, static checks, and preflight

- The eight-file implementation/test surface matched the developer handoff digest
  `c28946a62a14618a923ace316af11659ad3e03759da08ed8a18bfa300d484f66` using the standard
  lexicographic `sha256sum FILES... | sha256sum` order:
  `modeling_team/agent-packages/protocol/instructions.md`,
  `modeling_team/protocol_retrieval_mcp.py`, `modeling_team/runner.py`,
  `modeling_team/runtimes/codex.py`, `modeling_team/tests/test_codex_isolation.py`,
  `modeling_team/tests/test_protocol_retrieval_mcp.py`,
  `modeling_team/tests/test_proof_v2_runtime_asset.py`, and
  `modeling_team/tests/test_r23002.py`.
- The canonical writer focused suite passed exactly 10 tests, covering the three-way `tools/list`
  surface, fixed `evidence/candidate-item-evidence-map.json` publication, `0600` regular-file and
  idempotent behavior, tamper/extra/missing/overwrite fail-closed branches, Protocol instructions,
  Runner baseline and Adapter preflight. Command:
  `uv run --project backend python -m unittest modeling_team.tests.test_protocol_retrieval_mcp
  modeling_team.tests.test_proof_v2_runtime_asset
  modeling_team.tests.test_r23002.R23002Tests.test_runner_stages_relative_role_sources_and_baseline
  modeling_team.tests.test_codex_isolation.CodexIsolationTests.test_mcp_preflight_requires_exact_protocol_and_non_protocol_servers`.
- The complete modeling-team baseline passed (`160 tests`, 2.393 seconds):
  `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`.
- Service preflight passed (`active`, backend `/api/health` HTTP 200 `{"status":"ok"}`, frontend `/`
  HTTP 200). The frozen matrix remained 48 rows with digest
  `db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b`, and source candidate digest
  remained `7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`.
- Before the run, the official gate path was absent, the unique run directory did not exist,
  StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state
  SHA-256 was `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round67-1785592807 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run started at approximately `2026-08-01T22:00:07+08:00`, exited with status 1 after the
driver-recorded `89.394` seconds, and passed `driver_started`, `matrix_validated`,
`protocol_roster_started`, and `candidate_delivered`. The native `protocol_mechanics` MCP path was
actually reached (the safe elicitation evidence records the server acceptance), and the new canonical
writer produced a map that reached the driver's strict promotion gate. The gate rejected it with:

```text
ProofV2Error: candidate evidence map run_id drifts
P2AProtocolDriverError: candidate evidence map is invalid
```

This is a narrower D66 repair boundary than Round66: the writer now emits the canonical envelope, but
the Protocol-supplied `run_id` does not equal the current run ID
`r23002-p2a-round67-1785592807`. The driver correctly remains strict; the runtime-owned map is
removed during cleanup, so this round does not infer the incorrect run ID value. Because the failure
occurs before promotion/readback, `candidate_receipt`, `dry_run_observed`, `apply_observed`,
`retrieval_observed`, `native_verifier_completed`, and `protocol_report_accepted` are absent. No
Broker terminal result was invented and idle fast-fail was not the failure path.

Run-local safe evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `3879fe668998ffc6a2dc33fd5949158788a65e4b61edaf753e7e17985ffbfac7` |
| `evidence/app-server-events.jsonl` | `d820dbebd2f6c2ca04e7b7e7932b579efb1df4e9de9dbf8f65579e59ed2593ab` |
| `evidence/mcp-elicitations.jsonl` | `810fec4b14980ff8a62573d8eed1f129ce0569feadf061da821855600fdec977` |
| `evidence/p2a-protocol-driver.jsonl` | `981addba402c8fe42fa9358ac60fb78e261700380291f9eeb54c82cd75a73043` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted` with
authenticated HTTP 204, and `scope_cleanup_second_stage`; `cleanup_errors` was empty and
`driver_stopped` was recorded. The Session was terminal, the Lease auto-released, the project key
was non-active/revoked, the owned empty Project/Ontology was absent with residual counts all zero,
and the bootstrap-admin key was immediately revoked with its audit row retained. No P2a process
remained. The official gate path remained absent. After the run, StartLedger SHA-256 remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851` and retained `s` state SHA
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`; service health
remained active/API 200/frontend 200.

#### Defect and conclusion

**D67-P2A-01 — High / blocking.** Reproduction: execute the exact command above with the frozen
contract and a fresh run ID. Expected: the real Protocol calls the canonical
`write_candidate_item_evidence_map` MCP tool with the current run ID, the driver promotes the exact
map, and authoritative dry-run/readback proceeds. Actual: the canonical writer was reached but the
map's `run_id` failed the exact equality check against the current run, so the driver stopped before
the dry-run gate. The narrow repair is to bind the writer's run ID to the active P2a run context; do
not relax the driver check or create a second run/retry in this round.

**Round 67 conclusion: FAIL.** Canonical writer surface/negative tests and the real Protocol MCP
path are now proven, but run-ID binding remains incorrect in production. Cleanup and no-mutation
gates passed; no official P2a PASS artifact exists. Do not proceed to `t`; repair only the writer
run-ID propagation, rerun focused checks, and request another independent fresh P2a round. The tester
made no product fix and did not retry this run.

### Round 68 — 2026-08-01 D67 runtime-authoritative run-ID retest (FAIL)

This independent fifth P2a round reused this test plan after the D67 runtime-authority repair. It
did not modify product or test implementation, requirements/design/delivery documents, the
StartLedger, or retained producer `s`; it did not enter TeamRunner, perform a semantic start, run
C→B→A, or start `t`. The only real P2a run was
`r23002-p2a-round68-1785594002`. The run was allowed to reach a real Protocol `turn/completed`
before the PM issued a controlled stop; this is not a naturally-triggered idle fast-fail.

#### Owned-surface digest, static checks, and preflight

- The ten-file D67 implementation/test surface matched the developer handoff digest
  `ee95677960f10d74f9a7ed6008b9f11668c804fee47f68d06ebf22d54733d6cc` using the standard
  lexicographic `sha256sum FILES... | sha256sum` order: Protocol instructions, P2a driver and
  contract, retrieval MCP, Runner, Codex runtime, and their focused tests (`test_codex_isolation`,
  `test_p2a_protocol_driver`, `test_protocol_retrieval_mcp`, and `test_r23002`).
- The focused D67 suite passed exactly 92 tests (`Ran 92 tests in 1.812s`, `OK`):
  `uv run --project backend python -m unittest modeling_team.tests.test_protocol_retrieval_mcp
  modeling_team.tests.test_p2a_protocol_driver modeling_team.tests.test_codex_isolation
  modeling_team.tests.test_r23002 modeling_team.tests.test_proof_v2_runtime_asset`.
- The complete modeling-team baseline passed exactly 162 tests (`Ran 162 tests in 2.464s`, `OK`):
  `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`.
- Service preflight passed (`ontology-platform.service` active, backend `/api/health` HTTP 200
  `{"status":"ok"}`, frontend `/` HTTP 200). The frozen matrix remained 48 rows with digest
  `db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b`, and source candidate digest
  remained `7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`.
- Before the run, the official gate path was absent, the unique run directory did not exist,
  StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state
  SHA-256 was `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round68-1785594002 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run started at approximately `2026-08-01T22:20:02+08:00`. The real Protocol called the D67
canonical writer and the driver promoted the map successfully:

```text
stage=candidate_item_evidence_map_promoted
map_digest=8077da4fdf890fcccc68f28fec60bb4455a7063014fc3d855c99003fd4197f17
row_count=4
sha256=4f93a8241184341e7b85d0b1952eb93e00eecd4ce64022c7560b044dc331d3e3
```

The app-server evidence contains `turn/completed` as its final event (line 248); the evidence
writer's last-line mtime is `2026-08-01T22:22:20.020234+08:00`. The retained event projection only
contains method/parameter-key summaries, so no event payload timestamp is claimed beyond this
observable write time. No `batch_history_snapshot`, `dry_run_observed`, `apply_observed`,
`retrieval_observed`, native verifier event, or Broker terminal result appeared. Since the driver
idle guard only armed after `retrieval_seen`, it continued polling after the completed/idle turn.
At the PM's direction, the tester sent `Ctrl-C` at `2026-08-01T22:27:56+08:00` after confirming the
completed turn and the absence of any downstream stage; this controlled stop is the reason this
round is FAIL, not a natural fast-fail result.

Run-local safe evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `6aa64edc2e0cb6b7f86e1e0ca42c6e984d132e8f5e0d0e2bc25b45389c0f2460` |
| `evidence/app-server-events.jsonl` | `db751ed329e7d14e277fc1f9762b5c9fc61e43c71e0ed900fd2d0d3b4b3e4555` |
| `evidence/candidate-item-evidence-map.json` | `4f93a8241184341e7b85d0b1952eb93e00eecd4ce64022c7560b044dc331d3e3` |
| `evidence/mcp-elicitations.jsonl` | `52bd26bf3d243f7a83f6236ea5708a837240a7210ac1162bf07988bcc1fda753` |
| `evidence/p2a-protocol-driver.jsonl` | `c610d75c39857e9ecac69afb5fa6d7dbd3a37bb36537751689edb4560e20380c` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted` with
authenticated HTTP 204, and `scope_cleanup_second_stage`; `cleanup_errors` was empty and
`driver_stopped` recorded `elapsed_seconds=462.533`. Credentials were destroyed, the protocol key
and bootstrap-admin key were revoked, the Lease auto-released, and the owned Project/Ontology/Session
and project-scoped key residual counts were all zero. No Round68 P2a process or isolation runtime
remained after the controlled stop. The official gate path remained absent. After the run,
StartLedger SHA-256 remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, retained `s` state SHA
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`, and backend/frontend
health remained HTTP 200.

#### Defect and conclusion

**D68-P2A-01 — High / blocking.** Reproduction: execute the exact command above with the frozen
contract and a fresh run ID where the real Protocol promotes the canonical map but completes its
turn before issuing the dry-run/retrieval stages. Expected: once the Agent is idle, the driver
should fail fast after the existing grace window with the missing downstream stages, including the
post-map/pre-dry-run boundary. Actual: `run_driver` lines 792–797 only invokes `_idle_stage_error`
when `agent.state == "idle"` **and** `retrieval_seen` is true; `_idle_stage_error` lines 503–520
also returns `None` whenever `retrieval_seen` is false. This run had a promoted map but
`retrieval_episode == 0`, so the completed/idle turn was not bounded and required PM-controlled
termination. The narrow repair is to cover the post-map/pre-dry-run missing-stage case (for example
by arming the same idle grace on map promotion or another earlier required stage) while preserving
the existing strict stage checks and evidence semantics; do not relax map validation or create a
second run.

**Round 68 conclusion: FAIL.** D67 run-ID authority is proven by successful map promotion, but the
driver's idle fast-fail does not cover a completed turn before retrieval/dry-run. Cleanup and
no-mutation gates passed; no official P2a PASS artifact exists. Do not proceed to `t`; repair only
the narrow driver lifecycle guard, rerun focused checks, and request another independent fresh P2a
round. The tester made no product fix and did not retry this run.

### Round 69 — 2026-08-01 D68 all-stage idle-fast-fail handoff retest (FAIL)

This independent sixth P2a round reused this test plan after the D68 all-stage idle-fast-fail
repair. It did not modify product or test implementation, requirements/design/delivery documents,
the StartLedger, or retained producer `s`; it did not enter TeamRunner, perform a semantic start, run
C→B→A, or start `t`. The only real P2a run was `r23002-p2a-round69-1785594955`, and it exited
naturally with a strict candidate-receipt validation failure; the tester did not interrupt or retry it.

#### Owned-surface digest, static checks, and preflight

- The two-file D68 implementation/test surface matched the developer handoff digest
  `21ed17a173ce11a0fd3b4d8aae25e7ceadd57fac08710ae6f1a0d104f029fa8e` using the standard
  lexicographic `sha256sum FILES... | sha256sum` order: `modeling_team/p2a_protocol_driver.py` and
  `modeling_team/tests/test_p2a_protocol_driver.py`.
- The focused D68 suite passed exactly 93 tests (`Ran 93 tests in 1.786s`, `OK`), including the
  table-driven full-stage idle cases and D67 run-ID authority coverage:
  `uv run --project backend python -m unittest modeling_team.tests.test_protocol_retrieval_mcp
  modeling_team.tests.test_p2a_protocol_driver modeling_team.tests.test_codex_isolation
  modeling_team.tests.test_r23002 modeling_team.tests.test_proof_v2_runtime_asset`.
- The complete modeling-team baseline passed exactly 163 tests (`Ran 163 tests in 2.433s`, `OK`):
  `uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'`.
- Service preflight passed (`ontology-platform.service` active, backend `/api/health` HTTP 200
  `{"status":"ok"}`, frontend `/` HTTP 200). The frozen matrix remained 48 rows with digest
  `db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b`, and source candidate digest
  remained `7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`.
- Before the run, the official gate path was absent, the unique run directory did not exist,
  StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state
  SHA-256 was `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`. No P2a process
  was active.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round69-1785594955 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run started at approximately `2026-08-01T22:36:03+08:00` and exited naturally with status 1
after the driver-recorded `100.364` seconds (cleanup completed at approximately
`2026-08-01T22:37:44+08:00`). The real Protocol invoked the D67 canonical writer and the strict
map was promoted, confirming the runtime-authoritative run-ID handoff:

```text
stage=candidate_item_evidence_map_promoted
map_digest=9651c8ea200029d7a36dfcb1a9a26760f05a3dd419ab5bbc6ba926d248fe1c98
row_count=4
sha256=fec8562649fff7462f0be3fe5fd6c299f39b3d6ca88ad5faf90e471b90308da4
run_id=r23002-p2a-round69-1785594955
```

The next real Protocol delivery was rejected by the frozen candidate-receipt envelope validator:

```text
P2AProtocolDriverError: P2a candidate receipt fields are invalid
```

The required receipt field set is exactly
`{"status", "candidate_revision", "semantic_digest", "candidate_digest"}`; the validator also
requires the accepted status and exact candidate bindings. The retained safe evidence confirms only
that the received object failed this exact-field validation. The raw receipt is not retained after
cleanup, so this round makes no claim about which extra or missing field caused the rejection.
Because the failure occurred at receipt validation, `candidate_receipt`, `dry_run_observed`,
`apply_observed`, `retrieval_observed`, `native_verifier_completed`, `protocol_report_accepted`,
and any Broker terminal result are absent. D68's natural idle fast-fail path was not reached; no
manual termination was used.

Run-local safe evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `596a2f6f11ad6f888eddad7548f6e551bebc93b2d31f36fee2994e285443cd05` |
| `evidence/app-server-events.jsonl` | `c3726cae0b6410a92eb70ff6222ed9b0714bbf6147c118c557a4fa4d3e75d488` |
| `evidence/candidate-item-evidence-map.json` | `fec8562649fff7462f0be3fe5fd6c299f39b3d6ca88ad5faf90e471b90308da4` |
| `evidence/mcp-elicitations.jsonl` | `81d74e81066cdca866984f2f820c057e14afcc99625fad0375f62b202981fb0d` |
| `evidence/p2a-protocol-driver.jsonl` | `5488241a3bd68d9e7dc79e5ee430875c855479ae676e92a24ea1461175418454` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted` with
authenticated HTTP 204, and `scope_cleanup_second_stage`; `cleanup_errors` was empty and
`driver_stopped` recorded `elapsed_seconds=100.364`. Credentials were destroyed, the protocol key
and bootstrap-admin key were revoked, the Lease auto-released, and the owned Project/Ontology/Session
and project-scoped key residual counts were all zero. No Round69 P2a process or isolation runtime
remained. The official gate path remained absent. After the run, StartLedger SHA-256 remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, retained `s` state SHA
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`, and backend/frontend
health remained HTTP 200.

#### Defect and conclusion

**D69-P2A-01 — High / blocking.** Reproduction: execute the exact command above with the frozen
contract and a fresh run ID. Expected: after map promotion, the real Protocol sends exactly one
candidate receipt with the four frozen fields (`status`, `candidate_revision`, `semantic_digest`,
`candidate_digest`) and the exact candidate bindings, allowing authoritative dry-run/readback to
begin. Actual: the real receipt reached `_validate_candidate_receipt` but failed the exact field-set
check. The safe retained evidence cannot identify an extra versus missing field, so no narrower
claim is made. The only permitted repair is to align the Protocol receipt emitter with the frozen
four-field envelope and binding values, with an isolated producer/validator contract test; do not
relax the driver's strict validator or start a second run in this round.

**Round 69 conclusion: FAIL.** D68's all-stage idle table and D67 runtime-authoritative map handoff
are statically covered, and this real run independently proves map run-ID authority, but the real
Protocol receipt contract is still not aligned. Cleanup and no-mutation gates passed; no official
P2a PASS artifact exists. Do not proceed to `t`; repair only the receipt-emission boundary, rerun
focused checks, and request another independent fresh P2a round. The tester made no product fix and
did not retry this run.

### Round 70 — 2026-08-01 D69 deterministic receipt retest (FAIL)

This independent seventh P2a round reused this test plan after the D69 deterministic receipt-builder
repair. It did not modify product or test implementation, requirements/design/delivery documents,
the StartLedger, or retained producer `s`; it did not enter TeamRunner, perform a semantic start, run
C→B→A, or start `t`. The only real P2a run was `r23002-p2a-round70-1785596013`. The run reached a
natural D68 stage-specific idle failure; the tester did not interrupt, retry, or write a gate.

#### Owned-surface digest, static checks, and preflight

- The twelve-file D69 implementation/test surface matched the developer handoff digest
  `062d162fa8948b81df81df0dde29246de9c34bd70c38fd0692467e18df0b4b01` using the standard
  lexicographic `sha256sum FILES... | sha256sum` order: Protocol instructions, P2a driver and
  contract, `protocol_mechanics.py`, retrieval MCP, Runner, Codex runtime, and the five focused
  tests (`test_codex_isolation`, `test_p2a_protocol_driver`, `test_proof_v2_runtime_asset`,
  `test_protocol_retrieval_mcp`, and `test_r23002`).
- The focused D69 suite passed exactly 95 tests (`Ran 95 tests in 1.762s`, `OK`), covering the
  deterministic receipt MCP→existing-validator path, caller extra/missing-field rejection,
  candidate semantic/object tamper and cross-candidate rejection, sender/recipient/reply correlation,
  and D67/D68 authority/idle gates:
  `uv run --project backend python -m unittest modeling_team.tests.test_protocol_retrieval_mcp
  modeling_team.tests.test_p2a_protocol_driver modeling_team.tests.test_codex_isolation
  modeling_team.tests.test_r23002 modeling_team.tests.test_proof_v2_runtime_asset`.
- The complete modeling-team baseline passed `168 passed, 104 subtests passed in 2.49s`:
  `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests`.
- Service preflight passed (`ontology-platform.service` active, backend `/api/health` HTTP 200
  `{"status":"ok"}`, frontend `/` HTTP 200). The frozen matrix remained 48 rows with digest
  `db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b`, and source candidate digest
  remained `7bfb8f5b10338b9a8ba8dc0a33fcdf69d64060d0c4f184c855373733a366f471`.
- Before the run, the official gate path was absent, the unique run directory did not exist,
  StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state
  SHA-256 was `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`. No P2a process
  was active.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round70-1785596013 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The run started at approximately `2026-08-01T22:53:52+08:00` and exited naturally with status 1
after the driver-recorded `186.272` seconds. The real Protocol returned a correlated candidate receipt
and the runtime-authoritative map was promoted:

```text
stage=candidate_receipt
delivery_id=delivery-2
reply_to_delivery_id=delivery-1

stage=candidate_item_evidence_map_promoted
map_digest=c8d5afe3d249e1c8f6f5459791a395b953c2925ce9348c29223d03be079345d9
row_count=4
sha256=3ed3d78dade8b515f0e8145fd61d46792bf09d8c91f733377b60aab30b0521ca
```

The Protocol mechanics and Team Transport approvals are present in the sanitized
`mcp-elicitations.jsonl` (two `protocol_mechanics` and two `team_transport` acceptances), and the
driver's `delivery-2`/`reply_to_delivery-1` record proves that the Protocol itself sent the
correlated reply through Team Transport. The retained app-server projection intentionally strips
tool names and arguments; therefore the safe evidence directly proves the accepted native server
path plus the exact receipt and correlation, but does not independently expose a raw
`tools/call(name=build_candidate_receipt)` record. This limitation is recorded rather than inferred
away.

After map promotion, no `batch_history_snapshot`, `dry_run_observed`, `apply_observed`,
`retrieval_observed`, `native_verifier_completed`, or Broker terminal result appeared. The app-server
trace ended with `turn/completed` at event 178 (safe evidence file mtime
`2026-08-01T22:56:57.313091+08:00`). The repaired all-stage idle guard then naturally failed after
the existing approximately one-second grace; the driver evidence finished at
`2026-08-01T22:56:58.566135+08:00` with:

```text
P2AProtocolDriverError: P2a Protocol turn completed idle before stages: dry_run_observed,
apply_observed, retrieval_observed, native_verifier_completed, protocol_report_accepted
```

This is direct evidence that D68's post-map/pre-dry-run fast-fail now works naturally. It is still a
FAIL for the required P2a acceptance because the real Protocol did not reach the authoritative dry-run
and all downstream stages.

Run-local safe evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `b86d4ae4c55f789507b24f4b62cb4213a6abdb218ae14ec11ffaa984a1b85318` |
| `evidence/app-server-events.jsonl` | `3d522551a494dd65a63f4444bd8a996dd6c73f76036282d30d13afaeeb150115` |
| `evidence/candidate-item-evidence-map.json` | `3ed3d78dade8b515f0e8145fd61d46792bf09d8c91f733377b60aab30b0521ca` |
| `evidence/mcp-elicitations.jsonl` | `d7261bc8790f49a3bb4a4894859772301615df1fbc9ee7e09e7963ed5de4005e` |
| `evidence/p2a-protocol-driver.jsonl` | `352e511c319b9b311ea9173ad7777df462923cb956717222d1de59c43ad03c78` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, `scope_deleted` with
authenticated HTTP 204, and `scope_cleanup_second_stage`; `cleanup_errors` was empty and
`driver_stopped` recorded `elapsed_seconds=186.272`. Credentials were destroyed, the protocol key
and bootstrap-admin key were revoked, the Lease auto-released, and the owned Project/Ontology/Session
and project-scoped key residual counts were all zero. No Round70 P2a process or isolation runtime
remained. The official gate path remained absent. After the run, StartLedger SHA-256 remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, retained `s` state SHA
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`, and backend/frontend
health remained HTTP 200.

#### Defect and conclusion

**D70-P2A-01 — High / blocking.** Reproduction: execute the exact command above with the frozen
contract and a fresh run ID. Expected: after the exact Protocol-owned receipt and map publication,
the real Protocol performs authoritative dry-run/readback, apply, retrieval, native verification
(`complete=true`), and a correlated Broker terminal report before idle. Actual: the Protocol turn
completed after map promotion with all five downstream stages absent, and the driver correctly
failed fast at the earliest missing stage. The narrow repair is to keep the strict receipt/map and
idle gates and repair only the Protocol task execution path so it continues from map promotion into
the required dry-run/application/retrieval/native-verifier/terminal sequence; do not relax any gate,
synthesize evidence, or start a second run in this round.

**Round 70 conclusion: FAIL.** D69 deterministic receipt validation is proven in the real path, the
map run-ID authority and correlated Team Transport reply are proven, and D68's natural all-stage idle
fast-fail is fixed. However, the real Protocol stopped before authoritative dry-run and all downstream
acceptance stages; the sanitized evidence also does not expose the specific `build_candidate_receipt`
tool name. No official P2a PASS artifact exists. Do not proceed to `t`; repair only the narrow
Protocol continuation/receipt-tool evidence boundary, rerun focused checks, and request another
independent fresh P2a round. The tester made no product fix and did not retry this run.

### Round 72 — 2026-08-02 independent P2a continuation/overlay retest (FAIL)

This independent eighth P2a round reused this test plan after the D70 P2a-only planner, overlay,
runtime-subclass and projection implementation. The tester did not modify product or test
implementation, requirements/design/delivery documents, the StartLedger, or retained producer `s`;
it did not enter TeamRunner, perform a semantic start, run C→B→A, or start `t`. Exactly one fresh
real P2a run was attempted: `r23002-p2a-round72-1785638646`. The developer's earlier `fe58...`
handoff value was withdrawn as an unpublished path→digest canonical-JSON signature. The accepted
public handoff algorithm was `sha256sum <11 files> | LC_ALL=C sort -k2 | sha256sum`, producing the
11-file digest `a45de5e9c3dfe844d93e733fa6606d06b81690868fd85cdf2c031bd685e057f6`; this correction is
handoff bookkeeping, not a product failure.

#### Owned-surface digest, static checks, and preflight

- The accepted 11-file surface was exactly:
  `modeling_team/p2a_batch_plan.py`, `modeling_team/p2a_protocol_overlay_mcp.py`,
  `modeling_team/runtimes/p2a_codex.py`, `modeling_team/p2a_protocol_driver.py`,
  `modeling_team/references/p2a-overlay-contract.json`,
  `modeling_team/references/p2a-protocol-driver-contract.json`,
  `modeling_team/tests/test_p2a_batch_plan.py`,
  `modeling_team/tests/test_p2a_batch_plan_service.py`,
  `modeling_team/tests/test_p2a_codex_runtime.py`,
  `modeling_team/tests/test_p2a_protocol_driver.py`, and
  `modeling_team/tests/test_p2a_protocol_overlay_mcp.py`. The focused suite was run with
  `PYTHONPATH=. uv run --project backend pytest -q` over those five test modules and passed `35
  passed, 6 subtests passed in 0.72s`. An initial invocation without `PYTHONPATH=.` failed only at
  collection with `ModuleNotFoundError: modeling_team`; the corrected repository-root command is
  the test result used for this round.
- Complete modeling-team coverage passed `197 passed, 104 subtests passed in 2.74s`:
  `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests`. Focused Ruff, Python
  compilation, both P2a contract JSON parses, and `git diff --check` passed.
- The focused runtime test directly asserted the five forbidden global/platform surfaces remained
  byte-identical: `modeling_team/runner.py`, `modeling_team/protocol_mechanics.py`,
  `modeling_team/protocol_retrieval_mcp.py`, `modeling_team/runtimes/codex.py`, and
  `backend/app/api/schemas.py`. The overlay contract exposes exactly the two P2a tools and the
  driver contract includes `postapply_evidence_observed` in its required stages.
- Preflight passed: `ontology-platform.service` was active, backend `/api/health` returned HTTP
  200 with `{"status":"ok"}`, frontend `/` returned HTTP 200, the official gate
  `workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` was absent, and the unique run
  directory did not exist. The StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`; retained
  `workspaces/modeling-runs/r23002-real-20260801s/state.json` SHA-256 was
  `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`. No P2a process was active.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round72-1785638646 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The driver exited naturally with status 1 after `46.998` seconds. Direct run-local evidence proves
the sequence through the promoted four-row map:

```text
stage=driver_started
stage=matrix_validated row_count=48 matrix_digest=db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b
stage=protocol_roster_started agent_id=protocol
stage=candidate_delivered candidate_digest=22f03578616c3753f0d231308bb1da52bdff7a79cafdad0d5890f1f2c70f0ec7
stage=candidate_receipt delivery_id=delivery-2 reply_to_delivery_id=delivery-1
stage=candidate_item_evidence_map_promoted map_digest=1b03e82c76e711b081370af48e03ab0922b7a046f8cf76731e20844c8e663390 row_count=4 sha256=d153ea07fa7f57c981e70a19405a39be6cecd9deaaf951122488ffed79061709
```

The map contains exactly four candidate rows and binds run ID, candidate digest, citation/group
digests, client item IDs and inline Evidence identities. The retained sanitized MCP projection has
four elicitation decisions in order: `protocol_mechanics` accepted, `team_transport` accepted,
`protocol_mechanics` accepted, and `p2a_protocol_overlay` declined. This is the full safe evidence
boundary; the retained app-server projection does not preserve raw tool names, arguments, or the
reason for the overlay decision, so no narrower cause is inferred.

No `batch_history_snapshot`, `dry_run_observed`, `apply_observed`,
`postapply_evidence_observed`, `retrieval_observed`, `native_verifier_completed`, or
`protocol_report_accepted` stage appeared. The app-server trace ended at `turn/completed`, and the
driver's natural idle guard reported:

```text
P2AProtocolDriverError: P2a Protocol turn completed idle before stages: dry_run_observed,
apply_observed, postapply_evidence_observed, retrieval_observed, native_verifier_completed,
protocol_report_accepted
```

Run-local evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `3b0403205934dc9b3291c27fd6374f4c2aefc368177cc1c249096c7980d3436e` |
| `evidence/app-server-events.jsonl` | `3e0cd07e4d4f2f02809b98654c060bc0814bbc9db66301f819c691f789a2803e` |
| `evidence/candidate-item-evidence-map.json` | `d153ea07fa7f57c981e70a19405a39be6cecd9deaaf951122488ffed79061709` |
| `evidence/mcp-elicitations.jsonl` | `c8e39825eea334d5e2a91344b0e50fad836e5e85ecb9dcf7dc011e6917c96274` |
| `evidence/p2a-protocol-driver.jsonl` | `b45b37b0df6423152e11f70ec910f5518e807d80f328ec3b793b86cb7344e7fa` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, authenticated
`scope_deleted` HTTP 204, `scope_cleanup_second_stage`, and `driver_stopped`; cleanup errors were
empty. The Session reached terminal, the Lease auto-released, project-scoped and bootstrap-admin
keys were revoked, and Project/Ontology/Session/Lease/key residual counts were all zero. After the
run, the service remained active, backend/frontend remained HTTP 200, the official gate remained
absent, no P2a process remained, StartLedger remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state
remained `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Defect and conclusion

**D72-P2A-01 — High / blocking — Protocol overlay continuation boundary.** Reproduction: execute
the exact command above with a fresh run ID after the accepted static preflight. Expected: after
the exact candidate receipt and map, Protocol invokes the P2a overlay, submits authoritative
dry-run/readback, applies, observes post-apply Evidence/lineage, retrieves paginated results,
completes the native verifier with `complete=true`, and sends the correlated Broker terminal report.
Actual: the safe retained evidence records a `p2a_protocol_overlay` elicitation decline and the
Protocol turn completes after map promotion; all six required downstream stages are absent. The
evidence does not establish why the overlay was declined, so the defect is limited to the
observable collaboration/routing continuation boundary. Repair only that boundary and preserve
strict map/projection/idle gates; do not synthesize stages, relax validation, or start another run
in this round.

**Round 72 conclusion: FAIL.** Static P2a planner/overlay/runtime/projection coverage and all
preflight/no-mutation gates pass, and the real run proves candidate receipt, four-row map promotion,
correlated delivery, and complete cleanup. Required authoritative dry-run through Broker acceptance
was not reached. No official P2a PASS artifact exists. The tester made no product or test fix and
did not retry this run; request a narrow developer repair followed by a new independent test round.

### Round 73 — 2026-08-02 independent P2a approval/native-verifier retest (FAIL)

This independent ninth P2a round reused this test plan after the D72 P2a-only Host approval repair.
The tester did not modify product or test implementation, requirements/design/delivery documents,
the StartLedger, or retained producer `s`; it did not enter TeamRunner, perform a semantic start,
run C→B→A, or start `t`. Exactly one fresh real P2a run was attempted:
`r23002-p2a-round73-1785639819`.

#### Handoff, static checks, and preflight

- The public eleven-file handoff digest matched `cc26345832a1150c261657c2b58df6ff735e6181dda49216314a53aac8f8174d`
  using the stated `sha256sum <files> | LC_ALL=C sort -k2 | sha256sum` algorithm.
- The dedicated P2a Host-approval/negative suite passed `25 passed`:
  `PYTHONPATH=. uv run --project backend pytest -q modeling_team/tests/test_p2a_codex_runtime.py`.
  It covers accepted overlay approval and wrong/missing/extra/tool/server/role/task/run/preflight/
  tamper drift, while the normal non-overlay policy remains unchanged. The P2a focused suite passed
  `51 passed, 6 subtests passed in 0.85s`, and complete `modeling_team` passed `213 passed, 104
  subtests passed in 2.96s`.
- All five forbidden global/platform surfaces remained byte-identical; Python compilation, focused
  Ruff, both P2a contract JSON parses, and `git diff --check` passed.
- Preflight passed: `ontology-platform.service` was active, backend `/api/health` returned HTTP 200
  with `{"status":"ok"}`, frontend `/` returned HTTP 200, the official gate
  `workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` was absent, and the unique run
  directory did not exist. StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`; retained
  `workspaces/modeling-runs/r23002-real-20260801s/state.json` SHA-256 was
  `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`. No P2a process was active.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round73-1785639819 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The driver exited naturally with status 1 after `169.979` seconds. Safe run-local evidence proves
the following ordered stages:

```text
stage=driver_started
stage=matrix_validated row_count=48 matrix_digest=db6383a114f94a2c47bf28be52ca1eb88dce5e553a037c5fb407912d0882508b
stage=protocol_roster_started agent_id=protocol
stage=candidate_delivered candidate_digest=22f03578616c3753f0d231308bb1da52bdff7a79cafdad0d5890f1f2c70f0ec7
stage=candidate_receipt delivery_id=delivery-2 reply_to_delivery_id=delivery-1
stage=candidate_item_evidence_map_promoted map_digest=5196cdd4371fef1da032c419ae2a5adbfbd0b54e91f1893d7a9e8468816302e3 row_count=4 sha256=171032fb93ee155bb3213c7d020deb39b43f7dbb7e5fc94ce51f528522c741d8
stage=batch_history_snapshot inventory_sha256=1518aebc196fab37bc5e25f096d773e401eea377ae4a8536761c0cd732f42aea
stage=dry_run_observed batch_id=35dfd5ec-9394-4e59-a13e-0f36a0209b4c attempt_id=8565809b-1c8d-4284-bd96-8eacaf933779 plan_sha256=703b89abdebc8e4e02fcd177427d913f77df650faf5e490c0c7791cd62c55867
stage=apply_observed batch_id=35dfd5ec-9394-4e59-a13e-0f36a0209b4c attempt_id=a5e033f2-dce6-44d7-8acd-673449bf7798
stage=postapply_evidence_observed batch_id=35dfd5ec-9394-4e59-a13e-0f36a0209b4c detail_sha256=e2b94196a99db59ea569a8920cd28ac726f5c39e47f99b513fd48ae0a40f6554
stage=retrieval_observed episode=1
```

The promoted map has exactly four rows, and the dry-run snapshot reports four operation-plan
Evidence rows. The Protocol-owned observer accepted the formal dry-run/readback projection and
post-apply Evidence bindings; the retained safe record does not expose raw R0/R1/R2 payloads or
tool arguments, so the claim is limited to the recorded authoritative snapshot, plan digest and
post-binding evidence. Retrieval gate evidence records the required submit, validation, reasoning,
fallback and complete-state transitions through episode 2.

The sanitized MCP projection records 36 accepted elicitation actions: `protocol_mechanics` 3,
`team_transport` 1, `p2a_protocol_overlay` 4, and `ontology_platform` 28. For the overlay, only the
server/action acceptance is claimed; raw tool names and arguments are intentionally absent from safe
evidence.

The native verifier then emitted one safe event with
`tool=verify_scoped_retrieval_fallback`, `status=rejected`, `complete=false`, `category=failed`,
`proof_arguments_sha256=b3ce54f8e38eafd9c79e9afa5d4769283933281825aca42ac32cd96339bb55cf`, and
`result_envelope_sha256=74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b`. No
`native_verifier_completed` or `protocol_report_accepted` stage appeared. The Protocol turn ended at
`turn/completed`, and the driver's natural idle guard reported:

```text
P2AProtocolDriverError: P2a Protocol turn completed idle before stages: native_verifier_completed,
protocol_report_accepted
```

Run-local evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `afbcf718de9a14bc8a6f9b782868bac30d299fbfd3dd71e4b260e44df4a54db7` |
| `evidence/app-server-events.jsonl` | `2df685d312d103a2d820169b044da6e3847bdbbe3e9e0b3885501f3066475870` |
| `evidence/candidate-item-evidence-map.json` | `171032fb93ee155bb3213c7d020deb39b43f7dbb7e5fc94ce51f528522c741d8` |
| `evidence/mcp-elicitations.jsonl` | `3d5fcbc6d2488a1ab449d44b5ccde04a9188e5f405ed72edf9855192f30ed80c` |
| `evidence/native-verifier-events.jsonl` | `4df044bc756327005cc69097838df2447d655652c3442e8d78fd9c16e344bb66` |
| `evidence/protocol-retrieval-gate.jsonl` | `495f64e2e50d8b8134287e2b06731dfbee5a4041b14f3ffe146b6989ff620ba1` |
| `evidence/p2a-protocol-driver.jsonl` | `79c03f342af26da0f8a4f92b725c8dbd986ab55613dafc1afc370b8fac902ff5` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, authenticated
`scope_deleted` HTTP 204, `scope_cleanup_second_stage`, and `driver_stopped`; cleanup errors were
empty and elapsed cleanup/driver time was `169.979` seconds. The Session reached terminal, the Lease
auto-released, project-scoped and bootstrap-admin keys were revoked, and Project/Ontology/Session/
Lease/key residual counts were all zero. After the run, the service remained active, backend/frontend
remained HTTP 200, the official gate remained absent, no P2a process remained, StartLedger remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state remained
`1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Defect and conclusion

**D73-P2A-01 — High / blocking — native verifier and terminal acceptance.** Reproduction: execute
the exact command above with a fresh run ID after the accepted static preflight. Expected: after
receipt/map, exact-four dry-run/readback, apply/post-binding and retrieval, the native verifier emits
`complete=true` and Protocol sends the correlated Broker terminal report. Actual: the native verifier
safe event is `status=rejected`, `complete=false`, and the Protocol turn becomes idle with both
`native_verifier_completed` and `protocol_report_accepted` absent. The retained evidence does not
establish the cause of the rejected verifier result; no cause is inferred. Repair only this narrow
acceptance boundary while preserving all earlier strict gates; do not synthesize completion, relax
proof validation, or start another run in this round.

**Round 73 conclusion: FAIL.** This round independently proves overlay server/action acceptance,
candidate receipt, four-row map/plan, Protocol-owned dry-run/readback, exact-four apply and post-apply
Evidence binding, retrieval progression, and complete cleanup. Native verifier acceptance and the
Protocol-owned Broker terminal report were not proven. No official P2a PASS artifact exists. The
tester made no product or test fix and did not retry this run; request a narrow developer repair and
new independent test round.

### Round 74 — 2026-08-02 independent P2a native-failure classification retest (FAIL)

This independent tenth P2a round reused this test plan after the D73 native-proof repair. The tester
did not modify product or test implementation, requirements/design/delivery documents, the StartLedger,
or retained producer `s`; it did not enter TeamRunner, perform a semantic start, run C→B→A, or start
`t`. Exactly one fresh real P2a run was attempted: `r23002-p2a-round74-1785641969`.

#### Handoff, focused checks, and preflight

- The exact thirteen-file handoff matched the public digest
  `4df8de33cfed3d30291de51d31c6608d3253dcad077e3931736568de28d0846b` using
  `sha256sum <files> | LC_ALL=C sort -k2 | sha256sum`.
- The pure exact-four verifier fixture and its wrong-IRI, literal/resource, terminal-cursor and
  unconsumed-cursor cases passed `8 passed` (`test_proof_v2.py`). P2a safe error classification
  (`-32602`/`-32010`) passed 2 parametrized cases; the driver safe-schema/raw-event reader passed 2
  cases. The extended focused suite passed `62 passed, 6 subtests passed`; the wider related suite
  passed `73 passed, 19 subtests passed`, plus the two safe-reader cases for an aggregate `75/19`.
  Complete `modeling_team` passed `221 passed, 104 subtests passed in 2.85s`.
- All five forbidden global/platform surfaces remained byte-identical. Ruff, Python compilation,
  both P2a contract JSON parses, and `git diff --check` passed. The developer's shared-worktree
  GitNexus HIGH result across prior dirty files was treated only as an isolation audit, not as this
  round's owned-surface proof.
- Preflight passed: `ontology-platform.service` was active, backend `/api/health` returned HTTP 200
  with `{"status":"ok"}`, frontend `/` returned HTTP 200, the official gate
  `workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json` was absent, and the unique run
  directory did not exist. StartLedger SHA-256 was
  `964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`; retained
  `workspaces/modeling-runs/r23002-real-20260801s/state.json` SHA-256 was
  `1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`. No P2a process was active.

#### Single fresh real P2a attempt

The exact command was:

```bash
uv run --project backend python -m modeling_team.p2a_protocol_driver \
  --contract modeling_team/references/p2a-protocol-driver-contract.json \
  --root . --run-id r23002-p2a-round74-1785641969 \
  --base-url http://127.0.0.1:8001 --timeout 900
```

The driver exited with status 1 after `276.587` seconds because the native verifier stage never
completed before the bounded sequence timeout. Safe run-local evidence proves:

```text
stage=candidate_receipt delivery_id=delivery-2 reply_to_delivery_id=delivery-1
stage=candidate_item_evidence_map_promoted map_digest=6d8a7f5fd9677aa665f4ea3d4280aa98c7cf44191a869751d9b14557e3e7e8f9 row_count=4 sha256=6e6b72f9417f46da1876406de84f113188ada650fe786ec4787a2c1f6bf6289c
stage=batch_history_snapshot inventory_sha256=2f2eae102c2f1115e986e0515e726f759da520a9994c7b7b06b724229b3fcdae
stage=dry_run_observed batch_id=260aaee7-74a8-4b87-93b6-90dcfaf0488e attempt_id=72a8255f-61b0-489a-8d8d-6e843b01f2b9 plan_sha256=a36d209f7446404445b4b6d85a65e9b489ac7e845ad9b59a24db4997774c8360
stage=apply_observed batch_id=260aaee7-74a8-4b87-93b6-90dcfaf0488e attempt_id=231ee7d1-a5a2-42d6-9a76-a8cc1e27fad4
stage=postapply_evidence_observed batch_id=260aaee7-74a8-4b87-93b6-90dcfaf0488e detail_sha256=71a0964ac1725d14df3b7d5f156aac9c1923066456572ae9b7510b8c39791703
stage=retrieval_observed episode=1
stage=native_verifier_failed error_code=-32010 failure_layer=proof_validation mode_create=true top_level_exact=true types_valid=true
```

The map has exactly four rows and the dry-run plan has four Evidence rows. The sanitized MCP
projection contains 49 accepted actions: `protocol_mechanics` 3, `team_transport` 3,
`p2a_protocol_overlay` 4, and `ontology_platform` 39. Overlay acceptance is claimed only at the
server/action level; raw tool names, arguments and private payloads are not retained.

Retrieval evidence reaches the complete state through episode 2, including the fallback and
validation/reasoning transitions. The P2a-only native failure event is the safe six-field schema:
`error_code=-32010`, `failure_layer=proof_validation`,
`error_message_sha256=bbad0ccc8d218e6c0a9cc8ea0e4ede17b80c7979b152e660e9948f0e4c38453f`,
`mode_create=true`, `top_level_exact=true`, and `types_valid=true`. No raw error text, metadata,
arguments or result was retained. No `native_verifier_completed` or `protocol_report_accepted`
stage appeared; no Broker terminal report was accepted.

The driver ended with:

```text
P2AProtocolDriverError: P2a Protocol sequence did not complete before timeout: native_verifier_completed
```

Run-local evidence hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `baseline-manifest.json` | `7b88d0fb5ef00ab591502d7c92f03fdf586d70d84c57b54baef057ba18505368` |
| `evidence/app-server-events.jsonl` | `9ae89ce7f2991ed4b884f7fea57ec1448caeff23be8e4e6ec6dbcb41a81680d8` |
| `evidence/candidate-item-evidence-map.json` | `6e6b72f9417f46da1876406de84f113188ada650fe786ec4787a2c1f6bf6289c` |
| `evidence/mcp-elicitations.jsonl` | `c636984fcf6236e5855ed7a2530f1ed6470409c8a209949e5988a5b7252e9b64` |
| `evidence/native-verifier-events.jsonl` | `6c20bf48734c457188f16a18ad8ba7ddc89bdabeb8636144ef1b1078aab3df59` |
| `evidence/protocol-retrieval-gate.jsonl` | `0f860725bacda2c7df4e021e2b2419392c28d35d3f44cd380c43999da7920356` |
| `evidence/p2a-protocol-driver.jsonl` | `bba0586a5ba1fd68409780f489dc9b9757d52692ce84091a91575b27a8b74b98` |

#### Cleanup and no-mutation checks

The driver recorded `protocol_runtime_cleanup`, `scope_cleanup_first_stage`, authenticated
`scope_deleted` HTTP 204, `scope_cleanup_second_stage`, and `driver_stopped`; cleanup errors were
empty and elapsed driver time was `276.587` seconds. The Session reached terminal, the Lease
auto-released, project-scoped and bootstrap-admin keys were revoked, and Project/Ontology/Session/
Lease/key residual counts were all zero. After the run, the service remained active, backend/frontend
remained HTTP 200, the official gate remained absent, no P2a process remained, StartLedger remained
`964a54d3c4d8970463d40d614ca6435ebc967f3b36749e23062d8a69510a3851`, and retained `s` state remained
`1a2bdaceb6d4a2643aab60f73832845220fd4c0511e101bf415c2959ed9cb8f5`.

#### Defect and conclusion

**D74-P2A-01 — High / blocking — native verifier completion.** Reproduction: execute the exact
command above with a fresh run ID after the accepted static preflight. Expected: after the now-passing
receipt/map/dry-run/apply/post-Evidence/retrieval stages, the native verifier emits `complete=true`
and Protocol sends the correlated Broker terminal report. Actual: the P2a-safe event records
`error_code=-32010`, `failure_layer=proof_validation`, and the public structural booleans, while
`native_verifier_completed` and `protocol_report_accepted` remain absent. The retained evidence does
not expose the underlying error text or cause; no cause is inferred. Preserve the safe schema and
all earlier strict gates; do not synthesize completion, relax proof validation, or start another run
in this round.

**Round 74 conclusion: FAIL.** Static exact-four/native-negative coverage, global isolation checks,
and all preflight/no-mutation gates pass. The real run proves overlay acceptance, exact-four dry-run,
apply/post-binding and complete retrieval progression, but native verifier completion and the
Protocol-owned Broker terminal report were not proven. No official P2a PASS artifact exists. The
tester made no product or test fix and did not retry this run; request a narrow developer repair and
another independent test round.

### Round 76 shared-plan amendment — Agent-led real semantic acceptance (NOT EXECUTED)

This append-only amendment supersedes the current acceptance path, not the historical Round70–74 FAIL
records. Round75 requirement/design review did not execute a real run and is not acceptance evidence.
P2a driver/native-verifier/native-proof/continuation tests may remain mechanical regression evidence,
but no such test or official P2a gate can produce semantic PASS. Round75 real P2a and fresh `t` remain
paused. This documentation round runs no test, model, platform write or gate command.

#### Acceptance baseline and ownership

Before a real round, the tester must freeze and independently inspect:

1. one simple slice and its Producer `ready_for_acceptance` revision;
2. the exact canonical Round76 ticket and digest, including source bundle digest, competency questions,
   model-state identity/digest, read-tool allowlist and timeout;
3. a retained live Project/Ontology/workspace version and source signature with Producer writes paused;
4. a fresh Acceptance Agent identity, session/thread/work directory and read-only credential/tool surface;
5. absence of Producer transcript, expected answers, hidden tester answers, prior Acceptance context,
   write tools and access to mutable retained evidence.

Coordinator owns ticket publication and routing; Producer owns modeling; Acceptance Agent owns only the
read-only verdict; Delivery/runtime owns transport, identities, timeout and cleanup. The independent
tester observes this separation and never creates, continues or repairs the Producer run being judged.

#### Mechanical checks are necessary but not semantic PASS

Focused deterministic tests may prove exact ticket/result schemas, canonical digest/binding rejection,
fresh-context launch, read-only allowlist enforcement, timeout, transport, identity isolation, no-write
guards and cleanup. Existing receipt/map/exact Batch planning/dry-run/apply helpers may be regression
tested. These checks prove only mechanics. Mocks, fixtures, P2a `complete=true`, Driver stages, Broker
terminal results, Producer summaries or plan-review PASS are never equivalent to slice semantic PASS.

Any later implementation round must run the repository-required static/unit checks before the real
acceptance round, but the shared completion decision comes from the fresh Acceptance Agent against
retained live state. Failed historical rounds remain recorded and cannot be rewritten as PASS.

#### Fresh Acceptance Agent real round

The independent tester launches exactly one fresh Acceptance Agent for the frozen ticket and observes
that it:

1. reads every approved source needed by the slice and verifies `source_bundle_digest`/source locations;
2. reads the exact ticket-bound Project/Ontology/workspace state without mutation or Producer help;
3. checks source fidelity and slice scope, including rejection of unsupported or out-of-scope claims;
4. evaluates ontology classes/properties/relations/Shapes and explicit unknowns as business semantics;
5. independently observes validation and reasoning results through non-mutating operations;
6. exercises governed retrieval, consumes every required page, and rejects truncated/degraded/incomplete
   results or blocking warnings;
7. follows Evidence and lineage back to approved sources or released owner answers without conflating
   Agent rationale, source Evidence and explicit unknowns;
8. answers every frozen competency question from the approved sources and live platform state;
9. returns one canonical Round76 result bound to the exact ticket digest, slice/revision, source digest
   and model state.

The Acceptance Agent may return only:

- **PASS:** all eight checks and every competency question PASS, evidence references are independently
  resolvable, no state drift/write occurred, and the result binds the exact frozen revision/state;
- **FAIL:** at least one claim is disproven or one required quality check fails, with evidence and exactly
  one primary `failure_layer` from `modeling-quality|interview|protocol-delivery|platform|runtime`;
- **BLOCKED:** missing/unavailable approved source, read capability, live state or timeout prevents an
  honest verdict. Partial evidence or a mechanical success must not be promoted to PASS.

#### Failure, repair and retest matrix

| Result/layer | Coordinator route | Required next evidence |
| --- | --- | --- |
| `FAIL/modeling-quality` | Modeling Agent | New slice revision and new ticket; fresh Acceptance Agent |
| `FAIL/interview` | Coordinator asks one bounded user question, then Modeling | Released answer provenance, new revision/ticket/round |
| `FAIL/protocol-delivery` | Protocol Agent | Corrected formal delivery/readback, new revision/ticket/round |
| `FAIL/platform` | Platform implementation owner | Independently tested narrow fix, new ticket/round on frozen state |
| `FAIL/runtime` | Delivery/runtime owner | Independently tested runtime fix, new fresh Acceptance Agent round |
| `BLOCKED/*` | Owner of missing condition | Blocking condition resolved; no semantic reuse; new round |

Acceptance Agent never applies a repair, continues a Producer run or edits retained evidence. Every
repair invalidates the old ticket/result for current acceptance. A later PASS must be a new round with
fresh context; earlier FAIL/BLOCKED records remain append-only.

#### Slice and integration completion gates

A slice is accepted only by a valid fresh-Agent PASS for its frozen ticket. If more than one slice is
included, a new independent Acceptance Agent must PASS a final integration ticket bound to the exact set
of accepted slice revisions and final model state. Cleanup must prove Acceptance runtime/credential
destruction without deleting or mutating retained Producer state/evidence.

The current shared-plan completion gate explicitly excludes official P2a gate creation or consumption,
Round75 continuation success and fresh `t`. It also preserves the approved non-claim: this round does not
validate real explicitly typed datatype or language-tagged literal writes. A test round may be recorded
as PASS only after the real fresh Acceptance Agent evidence above exists; until then this amendment is
`NOT EXECUTED` and R2.3-002 remains incomplete.

### Round 76 plan-review High closure — shared test amendment (NOT EXECUTED)

This append-only plan closes H1–H4 at design level and adds the required future negative and real
checks. This docs-only round executes none of them and does not start an Agent, call the platform, write
a gate, consume a semantic start, or modify code/configuration.

#### H1 lifecycle checks

| ID | Check | Required result |
| --- | --- | --- |
| R76-H1-01 | Future Producer freezes a revision; Coordinator uses `publish_acceptance_handoff` before its existing completed report; inspect three Broker results and session settlement. | Ticket signal is a separate immutable artifact; all three unchanged `TaskResult` statuses are completed; settled occurs after them. No ready status exists in Broker. |
| R76-H1-02 | Independently remove/corrupt the ticket, leave one terminal non-completed/unsettled, leave one Producer Runtime alive, or leave any Producer write credential active. | Every case prevents sidecar launch and returns explicit BLOCKED ownership; no result, semantic start or platform write is created. |
| R76-H1-03 | After valid handoff/settlement, inspect Producer process/root/key teardown before sidecar start, then inspect independent sidecar root/session/thread/key. | Producer runtimes are stopped and all write keys revoked/destroyed; retained non-empty model/evidence remains; every sidecar identity differs. |
| R76-H1-04 | Submit the sidecar result and compare Producer terminal evidence before/after. Attempt duplicate result and make optional old-Coordinator summary unavailable. | Independent carrier preserves one result; Producer terminals are byte-identical; duplicate rejects; summary absence cannot block or change verdict. |
| R76-H1-05 | Bootstrap retained `r23002-real-20260801s` from retained rev7 handoff, settled and cleanup evidence using a new coordinating Agent. Inspect old sessions and StartLedger. | Old blocked terminals remain historical, no old Producer session resumes, no Producer run/fresh `t` starts, and semantic-start count is unchanged. |

#### H2 credential and read-surface checks

| ID | Check | Required result |
| --- | --- | --- |
| R76-H2-01 | Inspect created acceptance key record, local credential manifest, sidecar environment and MCP catalog. | Server key is exact retained Project + scope `[read]`; manifest additionally binds Ontology/ticket/round/config; no admin/model/Producer key or secret reaches sidecar; MCP exposes only ticket tools. |
| R76-H2-02 | Attempt every write/admin family, including `submit_modeling_batch`, Build Session/Lease mutation, Evidence writes, `run_semantic_validation`, `run_semantic_reasoning`, credential mutation and delete. Compare model/workspace/evidence/key inventory before/after. | Tools are absent or authorization rejects; no state changes. Validation/reasoning run tools are never called. |
| R76-H2-03 | Use exact existing allowlisted reads for state, model/retrieval and Evidence/lineage; exhaust all pagination. | Reads resolve only ticket Project/Ontology/state; every response is retained/digested; no cross-Project or unresolved-owner read succeeds. |
| R76-H2-04 | Exercise the four new validation/reasoning list/get MCP wrappers against Producer-created run IDs and wrong-Project/run/unscope list negatives. | Correct runs are read without creating/rerunning; wrong owner/unscoped list rejects; workspace and persisted run inventory remain unchanged. |
| R76-H2-05 | End sidecar through PASS, FAIL, BLOCKED, timeout and crash paths; inspect revoke/audit and retry a read with the old key. | Each path revokes the read key, destroys plaintext/runtime secret, preserves receipt, and the post-revoke MCP call fails. |

#### H3 carrier, references and no-oracle checks

| ID | Check | Required result |
| --- | --- | --- |
| R76-H3-01 | Validate exact ticket/result schemas, canonical digests, exclusive creation and task-root containment; try duplicate, overwrite, symlink, traversal and binding drift. | Valid artifacts retain exact bytes/digests; every negative rejects before publication and cannot mutate the first artifact. |
| R76-H3-02 | Resolve both typed ref variants; tamper source/platform bytes, location/tool allowlist, request/response digest, model/ticket binding, page ordinal/cursor, final-page flag and sequence completeness. | Only allowlisted, present, digest-correct, fully paginated and bound references resolve. Resolver emits no semantic judgment. |
| R76-H3-03 | In two isolated mechanical fixtures with identical valid ticket/evidence references, submit one FAIL and one PASS result; separately submit BLOCKED with each mechanically responsible failure layer. | Carrier/resolver preserves each supplied verdict and layer unchanged instead of deriving a verdict from evidence. This proves no deterministic semantic oracle; it is not semantic PASS evidence. |
| R76-H3-04 | Route all five layers with and without the mapped owner in the active roster. | Present owner receives external handoff; absent owner leaves explicit BLOCKED for project-management delegation. No verdict rewrite, Acceptance repair or automatic retry occurs. |

For R76-H3-03, single-submit remains mandatory per actual round: the two verdicts use distinct isolated
round IDs and carriers. The case proves passthrough only and cannot be cited as model acceptance.

#### H4 gate-free retained-s checks

| ID | Check | Required result |
| --- | --- | --- |
| R76-H4-01 | Parse the new acceptance task/profile/sidecar config and compare hashes of existing `r2-3-002-t.yaml` task/profile before/after. Search config, mounts, tool catalog and process access. | Existing `t` assets are unchanged. New assets contain no `expected_matrix_binding`, semantic-start/StartLedger mutation, P2a/native verifier/proof or official-gate path/tool; attempts to access them fail. |
| R76-H4-02 | Before bootstrap launch, read retained Project/Ontology/modeling context and source manifest; compare the exact IDs/version/signature/digests frozen in Round76. | Exact retained binding succeeds or the round is BLOCKED before Agent launch; drift never falls back to P2a. |
| R76-H4-03 | Run one future real fresh Acceptance Agent only for `retained-s-c-published-output`, with no Producer transcript/expected answer, and answer its single bounded CQ from approved sources plus live state. | Canonical Agent result and typed evidence exist; every read page is complete; no write, official gate, fresh `t` or semantic-start consumption occurs. |
| R76-H4-04 | Inspect StartLedger, P2a gate directory, `t` runtime/processes, Producer/Acceptance credentials and retained workspace before/after the real round. | Semantic-start count and P2a/gate state are unchanged; no `t` process exists; Producer write credentials are absent; acceptance read key is revoked; retained workspace is unchanged. |
| R76-H4-05 | Review CQ/slice scope and literal claims. | Only the simple published-version/output slice is judged; no claim of real datatype or language-tagged literal validation is made. |

The first real round remains `NOT EXECUTED`. Completion still requires fresh-Agent semantic evidence;
these lifecycle/security/carrier/gate-free checks and their future mechanical PASS cannot substitute for
the Agent verdict.

### Round 77 Agent-first operational acceptance round (NOT EXECUTED)

This supersedes Round76's implementation-gate test expansion with one real operational round. No test,
Agent or platform request is executed by this docs-only amendment.

#### Phase 1 — Delivery preflight

Delivery freezes the Round77 ticket/allowlist/evidence directory, verifies the retained source and model
digests, and uses the requirement's exact HTTP inventory to prove: Project contains only O; every target
graph set/run/Evidence/lineage owner resolves to P/O/G; workspace/source state matches; no Producer,
fresh `t`, semantic start or P2a/gate process/change exists. It records the before-inventory digest,
creates one `scopes=[read]` Project key, and proves no admin/model/Producer secret is in the Agent input.
Any second Ontology, owner ambiguity, missing target V/R, source/state drift or unfreezable request is
`BLOCKED` before launch.

#### Phase 2 — one fresh Acceptance Agent

The independent Agent receives only the ticket, sources, base URL, read key and exact allowlist. It
executes the state, model, validation/reasoning list, context/SPARQL query, Evidence and lineage requests
defined by the requirement; consumes every offset and both semantic cursor chains; writes each canonical
request, raw response, request/response hash and typed ref in its unique evidence directory; and returns
one bound Round76 `PASS|FAIL|BLOCKED` result. It performs no repair and makes no datatype/language-literal
claim. Mechanical success cannot replace its semantic verdict.

The independent evidence reviewer must confirm that every request is allowlisted, all returned owner/
state fields bind the ticket, V/R were read rather than rerun, retrieval/lineage are complete, approved
sources were not changed, and the Agent—not deterministic code—made the semantic decision. Any outside
request, missing page/cursor, missing audit, source/retained mutation or state change invalidates the
round as BLOCKED.

#### Phase 3 — cleanup and conclusion

Delivery stops the Agent, records after inventory, revokes the read key, verifies a final target GET with
that key is rejected, destroys plaintext/process secrets and preserves the evidence directory/result.
Before/after inventory must match except for the acceptance key's active→revoked lifecycle; StartLedger,
P2a/gate, `t`, workspace/source and Producer evidence remain unchanged. The reviewer records the real
round verdict and five-layer route without repairing it. Until this exact operational round is executed
and independently reviewed, Round77 remains `NOT EXECUTED` and R2.3-002 incomplete.

### Round 78 fresh simple slice with inline Evidence (NOT EXECUTED)

This docs-only amendment supersedes only Round77's retained-s target. It runs no Agent, API, platform test
or semantic start. The real round has the following four phases and fail-closed gates.

#### Phase 1 — Delivery reserves the one start

Record baseline ledger/resources/credentials/processes, reserve and start exactly once, create one fresh
Project/Ontology/Session/Lease and isolated evidence directory, then launch separate fresh Modeling and
Protocol Agents (`terra-xhigh` where available). Any second start, fresh t, P2a/native verifier/gate access,
or ownership ambiguity invalidates the round.

#### Phase 2 — candidate and Protocol Evidence gates

Give Modeling only approved sources and the CQ. Inspect the actual submitted candidate/batch before any
semantic write: <=12 in-scope items, explicit unknowns, and every item has non-empty inline
`document_name,excerpt` Evidence resolvable in an approved source; no expected answer, P2a or cross-run
Evidence ID is present. Every operation is a fresh RDF create for class/property/entity/relation/shape;
reject delete and rule-only operations before write because their modeling-item origin lineage is not
guaranteed. Reject before write on any mismatch.

Protocol may make at most three dry-run calls and one apply. Before apply, independently compare candidate,
batch and successful dry-run operation plan: item counts match and every operation has the corresponding
non-empty Evidence count. After apply, inspect per-item EvidenceReference/Association IDs, Evidence
search/list results and modeling-item origin lineage; all must bind the fresh Project/Ontology/item and the
submitted inline source. Apply uncertainty, missing Evidence or need for semantic correction is BLOCKED
without another start. Protocol/producer may run validation/reasoning before write-key revocation.

#### Phase 3 — fresh independent Acceptance

After successful readback, stop producers and revoke every write key. Delivery creates one temporary
Project `[read]` key and freezes the new-state ticket with the Round77 existing-HTTP allowlist parameterized
by fresh IDs. A new non-producer Acceptance Agent reads approved sources, state, existing validation/
reasoning, retrieval, Evidence and lineage, then returns one bound PASS|FAIL|BLOCKED for source fidelity,
scope, structure, unknowns and the CQ. Request audit and before/after inventory enforce read-only mechanics;
no deterministic check supplies the semantic verdict and Acceptance performs no repair.

#### Phase 4 — cleanup and completion gate

Stop all runtimes, revoke the acceptance read key and prove it fails, destroy plaintext secrets, and retain
the successful non-empty model/evidence. An empty failed scope may be cleaned; an applied non-empty failure
is retained for diagnosis. PASS requires the fresh Agent PASS, complete per-item Evidence/lineage, all keys
revoked, runtimes stopped and StartLedger exactly baseline +1. Otherwise record honest FAIL/BLOCKED; do not
patch retained s or invent PASS. This plan makes no real datatype/language-tag literal write claim and
remains NOT EXECUTED until the operational round produces independent evidence.

#### Round 78 High closure checks — canonical writer pre-start (NOT EXECUTED)

These checks run before Phase 1 and do not weaken any later Round78 gate:

| ID | Check | Required result |
| --- | --- | --- |
| R78-H-01 | With unset/default or explicit `legacy_only`, collect unit/MainPID/8001 listener, backend `Settings()` and authenticated canonical-mode evidence; inspect ledger/start/resources before and after. | Gate rejects before reservation/start or Project creation; ledger/start and resource inventory remain unchanged. Static source/config alone cannot pass. |
| R78-H-02 | While still at zero start, set only gitignored `backend/.env` or authoritative unit environment `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`; run Settings/config probe and restart the service. | Config resolves exactly `rdf_primary`; tracked files are unchanged; unit reaches active/running with a new recorded PID/start timestamp. |
| R78-H-03 | After restart, inspect full unit status and listener ownership, `curl --fail` backend `127.0.0.1:8001/api/health` and frontend `127.0.0.1:5173/`, then call authenticated `GET /api/semantic/canonical-mode`. | Both endpoints are healthy; listener belongs to the unit/repo; active HTTP response is 200 with `product_write_mode=rdf_primary` and matches Settings/process evidence. Only then may Phase 1 reserve/start. |
| R78-H-04 | Make config change, restart, health, auth or active-mode proof unavailable/ambiguous; separately attempt a config change after reservation/start. | First case is BLOCKED before semantic start with unchanged ledger/resources; second is prohibited and invalidates the round. No cleanup-time config mutation is allowed. |

The resulting preflight artifacts join the Round78 evidence directory. Passing these mechanical checks is
necessary but cannot replace Modeling Evidence gates, Protocol readback or the fresh Acceptance Agent
verdict; this amendment executes none of them.

#### Round 78 acceptance Evidence-layer correction (NOT EXECUTED)

This latest section supersedes any earlier check that treated fact-audit bindings as the Modeling Batch
inline Evidence gate. It permits one new fresh acceptance round/read key against the unchanged applied
model, with no ledger reserve/start or semantic/model write.

| ID | Check | Required result |
| --- | --- | --- |
| R78-E-01 | Reconcile Protocol artifacts with the live readback: 12 candidate/batch/apply item IDs, 15 associations and five approved-source EvidenceReferences. | 12/12 items resolve; every item has at least one current-run `target_type=modeling_item` association; all refs have exact approved document/excerpt/digest and none comes from P2a/another run. |
| R78-E-02 | For every applied item, follow its mapped resource/statement origin lineage back to the Modeling Item and associated reference. | Every chain is in the fresh P/O/run, `evidence_status=supported`, `lineage_status=complete`, untruncated and warning-free; Acceptance can independently reach the approved source. |
| R78-E-03 | Retain and inspect fact-audit queue separately; compare its seven `missing_evidence` observations with the complete modeling-item origin chains. | 7/7 remains recorded as a FactEvidenceBinding diagnostic. It neither disproves inline Evidence nor causes FAIL/BLOCKED by itself. No bridge/projection is implemented. |
| R78-E-04 | Freeze exact-ID Evidence reference/association and resource/statement lineage GETs in the new read ticket; retain fact-audit GET as diagnostic and execute with a fresh read key. | Requests stay read-only and fully audited; semantic verdict uses the modeling-item origin chain, not FactEvidenceBinding count; key is revoked and no model/ledger/start state changes. |

Missing or foreign reference/association, item-to-origin mismatch, partial/unsupported/truncated/warning
lineage, or inability of the fresh Acceptance Agent to follow the chain remains honest FAIL/BLOCKED. A
mechanically complete chain is necessary but still cannot substitute for its source-fidelity or CQ verdict.

### Round 78 independent Acceptance Agent execution — BLOCKED/platform

This is the independent read-only Acceptance Agent round for the fresh simple slice. The canonical
result is retained at
`workspaces/modeling-acceptance/r23002-acceptance-r78-20260802T112140Z/output/acceptance-result.json`
with SHA-256
`4a2cb3c084e9c947bc7045df843db0830ab83ed9d80ff1549219e77a196fac58`. It is bound to ticket
`r23002-acceptance-r78-20260802T112140Z` (ticket digest
`40bc1353525bc33d796a26084956a4c34ed02d4390ca4db0748c0ee34a539e9c`), slice revision `r3`, and
the unchanged Project/Ontology/workspace state from the producer run.

| Check | Result | Evidence/notes |
| --- | --- | --- |
| Source fidelity | PASS | The three approved source/state bindings and five persisted source references matched the ticket and approved source bundle. |
| Scope | PASS | The fresh applied run stayed within the bounded simple slice (12 applied modeling items). |
| Ontology structure | PASS | The required Workflow/Output, Tool and published Version relationships plus `quality_rating:number` were observed. |
| Explicit unknowns | PASS | Dynamic-versus-pinned binding and runtime value/mapping remained explicit unknowns rather than invented claims. |
| Validation/reasoning | PASS | Existing validation conformed with zero violations; reasoning succeeded and was consistent. |
| Evidence/lineage | PASS | 12/12 items, 15 current-run modeling-item associations, five approved-source references and nine complete supported origin chains were independently resolved; all were untruncated and warning-free. The seven missing FactEvidenceBinding observations remained a separate diagnostic and were not treated as the inline-Evidence gate. |
| Competency question | PASS | CQ1 was answered from approved sources plus live state: B binds C by workflow identity, C Version 2 is latest published, and B consumes C's `quality_rating:number`; dynamic-versus-pinned remains unknown. |
| Governed retrieval | BLOCKED | The context-query first page returned `matches_page.truncated=true` with a `next_match_cursor`. The one required cursor continuation returned HTTP 400 `invalid_context_cursor` (`Cursor signature is invalid`), so the complete retrieval chain could not be consumed. |

Overall verdict: **BLOCKED**, primary failure layer `platform`. The blocking artifact is
`evidence/context-query-cursor-error.json`; the SPARQL cross-check was complete but carried
`derived_result_missing` and cannot bypass the incomplete governed-context retrieval. The Acceptance
Agent made no write/admin/semantic mutation, and before/after evidence showed the applied model,
workspace, ledger, and retained producer evidence unchanged. The result is not PASS and must be
retested with a new acceptance round after the narrow cursor-signature/platform issue is resolved;
no new semantic modeling start is authorized or required for this repair.

### Round 78 narrow REST context-cursor repair verification — PASS (2026-08-02T20:00:56+08:00)

This independent tester round covers only the cursor-signing lifecycle repair in the four files
listed below. It does not re-run a semantic modeling start, mutate the retained model, or claim
that R2.3-002 has reached its final semantic PASS. The pre-existing `target_kind`/lineage
presentation changes in `semantic_context_query.py` remain shared-worktree context and are not
attributed to this repair.

#### Scope and implementation review

- `backend/app/api/deps.py` uses a module-level `threading.Lock` and an `app.state` double check;
  the codec is initialized once per FastAPI application, with `Depends(get_settings)` supplying
  settings and separate app states yielding isolated codecs.
- `backend/app/api/semantic.py` injects that codec only for the REST Context Query endpoint and
  passes it into the service.
- `backend/app/services/semantic_context_query.py` keeps `cursor_codec` optional at the end of
  the constructor, preserving existing positional callers. REST uses the injected per-app codec;
  direct/MCP construction without one keeps the prior per-query `from_settings` behavior.
- `backend/tests/test_semantic_context_query_api.py` covers cross-request ephemeral continuation,
  per-app isolation, and concurrent initialization. No production or test code was edited by this
  tester.

#### Verification evidence

Working tree was already dirty; relevant file SHA-256 values were:

```text
backend/app/api/deps.py                         46f07db7462747adc4c99dd45be0f617e68f91ff1702c66f30103d499f420c1e
backend/app/api/semantic.py                     dd6da4371dd19d8d8648dc2f5facdea0e4525ba2643e63ecc93c22438cb32f3f
backend/app/services/semantic_context_query.py  7622295f6caa2cd9e266deabc0a64ffa1cc1bbaa23adc25b4324b0b10b27b0ce
backend/tests/test_semantic_context_query_api.py 335e42252c1690debe2643c7c70586a28b6e57eb93bb0423150116ec61092ba0
```

Commands and results:

| Check | Result |
| --- | --- |
| `cd backend && uv run pytest -q tests/test_semantic_context_cursor.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query.py tests/test_semantic_context_query_independent.py` | **PASS** — 68 passed, 3 existing deprecation warnings |
| `cd backend && uv run pytest` | **PASS** — 826 passed, 10 skipped, 188 warnings, 37.41 s |
| `cd backend && uv run ruff check app/api/deps.py app/api/semantic.py app/services/semantic_context_query.py tests/test_semantic_context_query_api.py` | **PASS** — All checks passed |
| `git diff --check -- backend/app/api/deps.py backend/app/api/semantic.py backend/app/services/semantic_context_query.py backend/tests/test_semantic_context_query_api.py` | **PASS** — no whitespace errors |

Runtime restart and health evidence:

- `systemctl --user restart ontology-platform.service` completed; final full status was
  `Active: active (running)` with MainPID `409709`, uvicorn `410164/410171`, and frontend
  preview `410208/410224` under the unit cgroup.
- After the normal startup wait, `curl --fail http://127.0.0.1:8001/api/health` returned
  `{"status":"ok"}` and `curl --fail http://127.0.0.1:5173/` succeeded.
- The first health probe at approximately 22 ms was a transient connection-refused while the
  service was still starting; the subsequent bounded wait succeeded and the unit remained active.

Conclusion: **PASS for the narrow REST cursor repair**. The repaired service is eligible for a
new independent read-only Acceptance round against the unchanged retained model. This round does
not override the preceding Acceptance result (`BLOCKED/platform`) until that new Acceptance Agent
consumes the complete governed-retrieval cursor chain.

### Round 78 fresh independent Acceptance retest after cursor repair — BLOCKED/platform (2026-08-02)

This is a new fresh, read-only Acceptance Agent round for the unchanged fresh simple slice. It used
only the frozen ticket
`workspaces/modeling-acceptance/r23002-acceptance-r78-20260802T120405Z/runtime/acceptance-ticket.json`
(SHA-256 `93b96a3c07e0fa1086001ad287f9c16d725c3780c3adefb746d2d9e748b79985`), its approved source
bundle, request manifest, base URL, and the ticket's read key. No candidate, Protocol result/transcript,
expected answer, prior acceptance result, model write, validation/reasoning rerun, key mutation, or
Producer continuation was used.

#### Requests and evidence

- The frozen allowlist contained 40 requests (38 GET inventory calls, context-query initial, and
  SPARQL). All 40 were dispatched once with the read key and HTTP 200. The initial context response
  returned one live `matches_page.next_match_cursor`; the Agent copied it byte-for-byte into exactly
  one continuation request, which also returned HTTP 200. No cursor was generated, edited, replayed,
  or guessed. The match stream ended `truncated=false,next_match_cursor=null`; the context stream was
  complete on its initial page; the continuation response also reported both streams complete. The
  SPARQL response was `truncated=false`. Thus 41 concrete read requests were audited (40 frozen + 1
  live continuation), each with canonical method/path/body digest and raw response SHA-256.
- Evidence is retained under
  `workspaces/modeling-acceptance/r23002-acceptance-r78-20260802T120405Z/evidence/`, including
  `request-manifest.json`, `live-request-manifest.json`, `record-*.json`, `responses/*.raw`,
  `execution-summary.json`, and `independent-assessment.json`.
- Ticket-bound Project/Ontology/Graph Set/workspace/source signature matched exactly; the Project
  contained one Ontology. The existing validation run was read as `succeeded`, `conforms=true`, zero
  violations/warnings; the existing reasoning run was read as `succeeded`, `consistent=true`, with
  no rerun. Twelve modeling-item association targets and nine lineage targets were in the fresh
  scope; all nine lineage responses were supported, complete, untruncated, and warning-free.
- The fact-audit queue returned seven `missing_evidence` observations with empty bindings. Per the
  frozen Round78 contract these remain a diagnostic only and do not replace the complete
  modeling-item Evidence/lineage chains.

#### Independent semantic gates

| Gate | Result | Independent basis |
| --- | --- | --- |
| source_fidelity | PASS | Approved source file hashes matched the ticket; persisted release/workflow references and nine complete origin chains resolved to the approved bundle. |
| scope | PASS | One ticket Project/Ontology and the bounded 12-item state; no foreign scope appeared in the read responses. |
| ontology_structure | PASS | Workflow/Output classes, B/C/C Version 2/output entities, Tool/latest-version/consumes-output relations, and their asserted triples were present. |
| explicit_unknowns | PASS | The model does not assert a release-ID pin or runtime output mapping; those remain explicit unknowns in the acceptance answer. |
| validation_reasoning | PASS | Only the ticket-bound existing runs were read; both were current/succeeded with the stated zero-violation/consistent results. |
| governed_retrieval | **BLOCKED** | Cursor completeness is fixed, but the initial live context page still contains three generated shape-constraint related facts with `evidence_missing` and `lineage_missing` warnings. They do not change CQ1's direct answer, but the ticket requires complete governed retrieval and forbids ignoring blocking warnings. `derived_result_missing` and `ambiguous_match` were retained as non-blocking diagnostics. |
| evidence_lineage | PASS | All requested modeling-item association responses and all nine approved resource lineages were current-run, supported, complete, untruncated, and warning-free. |
| competency_questions | PASS | CQ1 is answered from approved release/workflow text plus live B→C, C→Version 2, and B→`quality_rating:number` triples; dynamic-vs-pinned and runtime value/mapping remain unknown. |

Overall verdict: **BLOCKED**, primary failure layer `platform`. The narrow cursor-signing repair is
verified, but the remaining live `evidence_missing`/`lineage_missing` governed-context warnings are
not silently downgraded. The canonical result is
`workspaces/modeling-acceptance/r23002-acceptance-r78-20260802T120405Z/output/acceptance-result.json`
with SHA-256 `4c2e277767b2be4aa2c670772c0780314655b4701f35f46317087cfecc9a6a93`; its ticket digest is
`aed7ad95ed16c5bc591d856fce66c027a514a208ffb8f7d77931fe3bbf06f31a`, and model-state digest is
`13bd86f748bcf818898dd4c073fd25f2ba2f83d71c53d716ae76e6ac1935759a`. No acceptance-side write or
state mutation was performed. Delivery should route this blocking warning to the platform owner and
open another fresh acceptance round after the warning is resolved; no new semantic modeling start is
authorized or required for this retest.

### Round 78 generated-shape lineage projection repair verification — PASS (2026-08-02T22:37:27+08:00)

This independent tester round covers the narrow generated Shape constraint lineage projection repair.
It does not perform semantic writes, alter the retained model, or attribute the earlier shared-worktree
cursor/`target_kind` changes to this repair. The implementation under review is the current diff in
`backend/app/services/semantic_context_query.py`; the REST and MCP paths are exercised through their
existing tests.

#### Contract review

- A Shape field is projected to a lineage target only when its provenance is exactly `generated`, its
  path canonicalizes to a valid absolute RDF IRI, and the internal marker's `resource`/ID agrees with
  that canonical path. The public item has `target_kind=resource`; lineage is called with
  `target_type=resource` and the property IRI, never with the synthetic constraint hash.
- Synthetic constraint IDs remain the stable hash of ontology/class/path, and the public constraint
  retains the supplied provenance. Invalid generated BNodes/relative paths and non-generated
  `custom`/`merged` fields retain the projection but fail closed: no lineage call, no `target_kind`,
  and no public lineage `target_type`/`target_id`; only `lineage: {status: missing}` plus the existing
  `evidence_missing`/`lineage_missing` warnings are emitted.
- Unknown or forged internal `_lineage_target` markers are popped and never leak to REST/MCP output;
  statement/resource candidates continue to use their explicit target kinds and existing lineage
  behavior.

#### Verification evidence

The worktree was already shared/dirty; relevant SHA-256 values at this round were:

```text
backend/app/services/semantic_context_query.py       a0a9f69d8e17a9ee88ef14ec009ee7fd81fd212464f5a3e14c8ee47f2c49f928
backend/tests/test_semantic_context_query.py          728d141d4b56826525031d46242e91f0c0f939f79a2eaca0fd832f1d7e900462
backend/tests/test_semantic_context_query_api.py      4a146abe53776d0441f75f7414c48909f66b6f4cd9fa92e920c9c459fc4ed181
backend/tests/test_semantic_context_query_mcp.py      77420c296698bc39660aef33fc6423e307f689b1cd802811244b9a1dacbfafaa
```

Commands and results:

| Check | Result |
| --- | --- |
| `cd backend && uv run pytest -q tests/test_semantic_context_query.py tests/test_semantic_context_query_independent.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py` | **PASS** — 77 passed, 3 existing deprecation warnings |
| `cd backend && uv run pytest` | **PASS** — 834 passed, 10 skipped, 188 warnings, 38.10 s |
| `cd backend && uv run ruff check app/services/semantic_context_query.py tests/test_semantic_context_query.py tests/test_semantic_context_query_independent.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py` | **PASS** — All checks passed |
| `git diff --check --` (the implementation and four related test files) | **PASS** — no whitespace errors |

Runtime evidence after the required restart:

- `ontology-platform.service` is `active (running)` since `2026-08-02 22:36:57 +08:00`, MainPID
  `642192`, with uvicorn `642591/642598` and frontend preview `642676/642693` under the unit cgroup.
- After the bounded startup wait, `curl --fail http://127.0.0.1:8001/api/health` returned
  `{"status":"ok"}` and `curl --fail http://127.0.0.1:5173/` succeeded.
- The first immediate probes observed normal startup connection refusal before listeners were ready;
  subsequent health probes succeeded and the unit remained active.

Conclusion: **PASS for the generated-shape lineage projection repair**. The unchanged retained model
can proceed to a fresh independent read-only Acceptance round. This narrow tester PASS does not replace
the prior semantic Acceptance `BLOCKED/platform` verdict or authorize any new semantic modeling start.

### Round 78 final fresh independent Acceptance Agent — PASS (2026-08-02)

This is the final fresh read-only semantic acceptance for ticket
`r23002-acceptance-r78-20260802T143944Z`. The ticket SHA-256 is
`2527003f6426c585d813e03cf3d8d948b774a2f7f26873d2a50f6eec6206a3ec`. No Producer, candidate,
Protocol artifact/transcript, expected answer, prior acceptance result/assessment, semantic/model
write, validation/reasoning rerun, or key mutation was read or performed.

#### Execution evidence

- The frozen allowlist contained 40 requests. All 40 were dispatched once and returned HTTP 200.
  The initial context response returned one live `match_cursor`; it was copied byte-for-byte into
  exactly one continuation request, which also returned HTTP 200. The concrete audit therefore has
  41 requests, canonicalized from exactly `method`, `path`, and `body`; raw response bodies, request
  digests, response digests, and page records are retained under the ticket evidence directory.
- Match pagination completed as 20 initial + 9 continuation items (`truncated=false`, no cursor on
  the final page); context pagination completed as 3 + 0 (`truncated=false`, no cursor). The
  allowlisted SPARQL response was complete (`truncated=false`, 14 bindings, complete scope).
- The approved source bundle and all three frozen source-file hashes matched. The five frozen
  persisted EvidenceReferences matched exact document/excerpt/hash content, with 15 current-run
  reference associations. All 12 frozen modeling-item targets resolved through 15 current-run
  item associations, and all nine requested resource lineages were supported, complete,
  untruncated, and warning-free.

#### Independent gates

| Gate | Result | Basis |
| --- | --- | --- |
| source_fidelity | PASS | Frozen source bundle and persisted reference/excerpt/digest bindings matched. |
| scope | PASS | One ticket Project/Ontology/Graph Set; no foreign or excluded scope; bounded 12-item slice. |
| ontology_structure | PASS | Workflow/Output classes, B/C/C Version 2/output resources, and required relations/triples present. |
| explicit_unknowns | PASS | Workflow identity versus release-ID pinning and runtime mapping remain explicit unknowns. |
| validation_reasoning | PASS | Existing ticket-bound validation conformed with zero violations; reasoning succeeded/consistent; neither rerun. |
| governed_retrieval | PASS | Both live cursor streams and SPARQL completed; no evidence/lineage warning remained in returned items. |
| evidence_lineage | PASS | 12/12 items, 15 associations, five references, and nine complete supported lineages. |
| competency_questions | PASS | CQ1 independently answered from approved sources and exact live facts. |

The initial `matches_truncated` warning was resolved by the live continuation. `derived_result_missing`
is non-blocking because this asserted-only CQ uses the current reasoning pointer and direct asserted
triples, not a rule result. `ambiguous_match` is non-blocking because exact resource/statement IDs,
source lineage, and complete pagination disambiguate the repeated normalized labels. The 7/7 empty
FactEvidenceBinding observations remain the ticket-approved diagnostic only; they do not override the
complete modeling-item Evidence/lineage chains.

#### CQ1 and final result

CQ1 answer: **B binds C as a Tool by workflow identity; C Version 2 is published and marked latest;
B consumes C's `quality_rating:number` output.** Whether B dynamically resolves the latest version or
pins Version 2, and the runtime output value/mapping, remain unknown.

Overall verdict: **PASS**, no failure layer. The structured result is
`workspaces/modeling-acceptance/r23002-acceptance-r78-20260802T143944Z/output/acceptance-result.json`
with SHA-256 `280fff95c39e85629c417ff5fb3b72d5eb0ba54f6da1cb147b69f14c18dbb7b6`; it binds model-state
SHA-256 `9cdacd58ccb13584c27049a3ef54a779d754c090b177e918167a224a26a671bc`. The Agent sent no
semantic/model/admin/write request, made no validation/reasoning rerun, and did not mutate the model,
workspace, ledger, or retained evidence. The read key remains active for Delivery cleanup.

### Round 79 — 2026-08-03 post-delivery documentation audit — PASS (docs-only)

Scope: independently read `AGENTS.md`, the v2.3 requirement, R2.3-002 design, delivery record,
reference lessons, this shared plan, and retained StartLedger evidence. No product code, runtime,
backend/frontend test, platform write, or service restart was performed.

| Check | Result | Evidence |
| --- | --- | --- |
| Current target/order/dependencies | PASS | Requirement table and order are `001 → 002 → 005 → 003 → 004`; 003 keeps 002 as semantic dependency and 005 as operational prerequisite. |
| R2.3-005 target/boundary | PASS (static contract only) | Future/`待细化`; clean checkout/status, tracked `Task`/`Profile`/`Runner`/`Adapter`, one simple Producer dry-run/apply/readback/validation/reasoning slice, three terminals + settlement, immutable handoff/cleanup, and fresh read-only Acceptance outside Runner are explicit. Runner is not semantic authority; Driver/Producer self-report is not a verdict. P2/P2a/monitor/native-verifier/proof-matrix/orchestrator/recovery/Pi/literal gates are excluded; no target implementation or 005 acceptance is claimed. |
| Round78 evidence boundary | PASS | Record header/retrospective and requirement state that Round78 proves only the retained model and independent Acceptance PASS, not clean-checkout Runner reproducibility. |
| Record metadata/history | PASS | `Status: delivered (independent Acceptance PASS)`, `Last updated: 2026-08-03T00:42:06+08:00`, conclusion/closeout, and append-only retrospective agree; no historical round was removed. |
| Metrics | PASS | Calendar arithmetic = `56:58:16`; ledger has 18 `semantic_start` events; requirement/design/record retain the 10 route labels (R59/60/61/62/63/71/75/76/77/78), the shared plan retains its relevant planned/executed round history and all 10 P2a FAIL headings (R64–70/R72–74), only Round78 is accepted, and final run evidence binds r1/r2/r3 inside start 18. |
| Lessons and defect boundary | PASS | Lessons are explicitly reference-only/non-normative; exactly three confirmed platform defects are separated from Protocol/runtime/harness issues, and the literal-write gap is deferred to R2.4-001. |
| Docs diff/format | PASS | `git diff --check -- docs` passed; docs diff contains only the expected requirement, record, lessons, and this shared plan (no unrelated docs). |

Conclusion: **PASS for this documentation audit**. The shared-plan status line still preserves its
historical “Round 52 … no development handoff” wording; it is not evidence that R2.3-005 started or
that Round78 lacked its appended PASS. R2.3-005 remains future/unimplemented and requires a later
clean-checkout implementation and independent test round.

### Round 80 — 2026-08-03 metadata-correction audit — PASS (docs-only)

Re-read the corrected header against the retained append-only history. The status now identifies
R2.3-002 as delivered with Round78 independent Acceptance PASS and Round79 documentation-audit PASS;
the Producer owner points to the completed retained Round78 model; and the independent-test owner
names the fresh Round78 Acceptance Agent plus the Round79 Requirement Tester audit. These statements
match the Round78 final PASS and Round79 headings/results below, while Round79 itself remains unchanged.

`git diff --check -- docs` passed. No product tests, runtime actions, or other file edits were made.

Conclusion: **PASS**. The prior historical-header ambiguity is resolved; R2.3-005 remains future and
unimplemented.
