# R2.3-001 Team Runner and Codex Adapter Shared Test Plan

## Status

- Requirement: `docs/requirements/requirements-v2.3.md`, R2.3-001
- Design:
  `docs/delivery/designs/2026-07-31-r2-3-001-team-runner-codex-adapter-design.md`
- Status: reviewed; awaiting development-ready handoff
- Live-run producer: Requirement Developer under the reviewed plan
- Test owner: independent Requirement Tester after stable retained live evidence exists
- Runtime under test: real local Codex app-server `0.146.0`

## Completion rule

PASS requires all automated checks, one real base three-Agent capability run, one real
specialist-Profile interoperability run, real empty-scope `create` and `existing` lifecycle
evidence, exact cleanup, resident service health, and an independent test round.

No result may claim ontology modeling quality. Any Modeling Batch submission is a failure.

## Preconditions

- repository baseline and tested worktree state are recorded;
- PostgreSQL, Oxigraph, backend `127.0.0.1:8001`, and frontend `127.0.0.1:5173` are healthy;
- local Codex is authenticated and version/config prerequisites pass;
- `bwrap`, backend virtual environment, and required repository Skills exist;
- run IDs are unique and `workspaces/modeling-runs/<run-id>` does not exist;
- the live-run producer owns any temporary existing-mode fixture and records its IDs before the
  run;
- no unrelated Project, Ontology, API key, Runtime process, or run directory is a cleanup target.

## Automated contract and configuration cases

| ID | Case | Required result |
| --- | --- | --- |
| A01 | Load both committed Profiles and all Packages | Valid objects with frozen unique roster |
| A02 | Missing/unknown Package or Skill/reference | Fails before scope or Agent startup |
| A03 | Path traversal, absolute path, unsafe run ID | Rejected without creating outside files |
| A04 | Duplicate Agent, missing Coordinator/Protocol, two Protocol roles | Rejected before startup |
| A05 | Runtime differs within one Profile | Rejected |
| A06 | Unknown communication endpoint/self-edge/duplicate edge | Rejected |
| A07 | Coordinator or Modeling platform permission | Rejected |
| A08 | non-Protocol platform-write permission | Rejected |
| A09 | credential/temporary path/runtime identity in Package or Profile | Rejected |
| A10 | deprecated Skill reference | Rejected |
| A11 | Task attempts to change Profile, permission, Runtime, or scope | Rejected |
| A12 | valid Agent Package Runtime loader | Shared role fields remain Codex-neutral |
| A13 | generated Codex configs | only Protocol contains ontology MCP and project key |
| A14 | strict Codex config preflight | every Agent config parses before first turn |
| A15 | Skill staging and discovery | only declared Skills staged; `extraRoots/set` and forced list return exact enabled paths and no errors |
| A16 | Skill injection | first-turn model-visible input contains the declared Skill instructions/hash |
| A17 | missing/disabled/path-mismatched Skill | fails before first Agent turn |
| A18 | Agent namespace mount allowlist | no host root, repository, sibling home/work/skills/socket, backend `.env`, or host run root |
| A19 | Modeling Skill role contract | team Profile defers platform calls to Protocol while standalone fallback remains documented |

## Automated Runtime Adapter and transport cases

| ID | Case | Required result |
| --- | --- | --- |
| R01 | app-server initialize/thread start/turn start parsing | Stable Agent identity without leaking Codex fields into core contract |
| R02 | active recipient delivery | exact text sent through `turn/steer` with expected turn ID |
| R03 | idle recipient delivery | exact text sent through `turn/start` on same Thread |
| R04 | stale active-turn precondition | one exact re-read/retry, no duplicate or rewrite |
| R05 | unauthorized recipient | transport rejects and records routing failure |
| R06 | free-form Unicode/multiline text | byte-equivalent recipient input |
| R07 | Coordinator outer user message | delivered only to Coordinator |
| R08 | Coordinator explicit peer forward | exact user text reaches declared peer |
| R09 | ordinary Coordinator response | no peer delivery is created |
| R10 | Agent completed/blocked result | one structured terminal envelope |
| R11 | Adapter settled before all Agent results | Runner does not report team complete |
| R12 | all results but active turn remains | Runner waits for settled state |
| R13 | app-server malformed JSON/exit/lost Thread | runtime failure and cleanup |
| R14 | partial roster startup failure | already-started Agents stop; no replacement Agent |
| R15 | pause/resume/stop | mechanical state and same Thread identities preserved as applicable |
| R16 | one Runner input stream | second run cannot be attached to the same process |
| R17 | sibling filesystem and `/proc` probe | non-Protocol Agent cannot read Protocol home/config/key or sibling process environment |
| R18 | broker endpoint isolation | Agent can use only its own endpoint and cannot impersonate a sibling |
| R19 | non-Protocol write probe | no credential is discoverable and authenticated platform write is denied |

Protocol fixtures used in R01-R16 emulate only app-server wire responses; they do not constitute a
second Runtime Adapter or acceptance Agent.

## Automated platform scope and cleanup cases

| ID | Case | Required result |
| --- | --- | --- |
| P01 | create preparation | unique empty Project/Ontology and Protocol model key recorded as owned |
| P02 | create cleanup | key revoked, exact empty Project deleted, admin key self-revoked |
| P03 | create ownership mismatch | deletion refused and evidence preserved |
| P04 | create scope has a write/Batch | deletion refused; platform-contract failure |
| P05 | existing resolution | Project/Ontology relation and empty workspace verified |
| P06 | existing missing/mismatched/non-empty scope | fails without takeover or deletion |
| P07 | existing cleanup | only run keys revoked; scope still readable and unchanged |
| P08 | key creation failure after scope create | exact owned empty scope cleaned |
| P09 | Agent startup failure after scope create | Runtime and exact scope/key cleanup complete |
| P10 | secret scan | no plaintext key in Profile, Package, Task, state, transport, transcript, or evidence |
| P11 | terminal cleanup | Agent processes stopped and `secrets/` destroyed |
| P12 | ambiguous cleanup target | no destructive call issued |

Unit tests use an in-process HTTP test client or narrow platform-client stub for failure injection.
Real acceptance below must use the resident platform and database receipts.

## Real base three-Agent capability run

Use the committed `base-three-agent` Profile and `base-capability-smoke` Task in `create` mode.

Required evidence:

1. one foreground Runner and exactly three real Codex app-server/Thread identities;
2. each Agent receives its Package instructions, declared Skill/reference inputs, same Task, and
   complete frozen roster; `skills/list` and model-visible first-turn evidence prove actual Skill
   discovery and injection;
3. Coordinator assigns initial work to Modeling and Protocol;
4. Modeling sends one free-form direct message to Protocol without Coordinator relay;
5. Protocol calls only an allowed non-mutating platform tool and sends the exact result to Modeling;
6. while Modeling or Protocol is active, the outer caller sends a unique ordinary status message
   to Coordinator and receives a Coordinator reply;
7. the ordinary message creates no peer delivery;
8. the outer caller then sends a uniquely marked explicit supplemental instruction; Coordinator
   forwards it verbatim to the named Agent, or asks for clarification first if the supplied test
   message is intentionally ambiguous;
9. every Agent reports its own completed/blocked result;
10. Adapter state proves all Threads settled before Coordinator's final team summary;
11. no Modeling Batch, Build Session, Lease, ontology resource, or graph statement is created;
12. Protocol alone has platform MCP configuration/tool events; real non-Protocol probes cannot
    read Protocol config/key through guessed paths, sibling `/proc`, or broker endpoints and cannot
    perform an authenticated platform write;
13. Protocol key and admin key are revoked, exact empty create scope is deleted, Agent processes
    stop, secrets are destroyed, and resident services remain healthy.

## Real specialist interoperability run

Use `source-specialist-smoke` with `specialist-interoperability-smoke`. Record the Git hash of
Runner and Codex Adapter files before and after the run.

Required evidence:

1. four real Codex Threads start from the Profile;
2. the Source Specialist receives its own Package instructions and declared Skill; discovery and
   model-visible input prove the Skill was injected;
3. Coordinator assigns it a bounded non-modeling capability task;
4. it exchanges at least one direct free-form message with another non-Coordinator Agent;
5. it has Team Transport but no platform MCP;
6. it reports its own terminal result and participates in settled completion;
7. no Runner/Adapter code changed to add or run it;
8. no modeling write occurs and complete create-mode cleanup succeeds.

The run proves extension mechanics only.

## Real existing-scope lifecycle run

The Requirement Developer creates one uniquely owned empty Project/Ontology fixture before starting
the Runner and records its initial workspace context. The independent tester must not create,
continue, steer, or mutate the run it evaluates.

Run the base Profile in `existing` mode and require:

1. Runner resolves the exact IDs and verifies the Ontology belongs to the Project;
2. no Build Session or Lease is created and no pre-existing resource is changed;
3. the run-specific Protocol key is scoped to the fixture Project;
4. the capability task completes with zero modeling writes;
5. Runner cleanup revokes only its keys and leaves Project/Ontology present;
6. post-run workspace context equals the initial context;
7. the Requirement Developer, not Runner or independent tester, deletes the uniquely owned fixture
   after evidence capture and records direct cleanup evidence.

## Independent evidence boundary

The Requirement Developer produces and settles the real base, specialist, create-mode, and
existing-mode runs and freezes their evidence paths before the independent handoff. The independent
Requirement Tester:

- does not create, continue, steer, stop, or clean those Agent runs;
- does not provide user messages or business answers to them;
- may run offline/unit/regression checks and read-only platform/process/health verification;
- directly inspects retained Runtime events, platform receipts, scope/key cleanup, secret
  destruction, and service health;
- records any missing evidence as FAIL/BLOCKED rather than recreating the run.

## Failure and boundary checks

- invalid configuration must fail before starting any Agent;
- Runtime/provider failure must be classified as runtime/infrastructure, not Agent blocked;
- Agent blocked must remain that Agent's declared outcome and Coordinator must not claim success;
- ambiguous user text must not enter peer modeling context without Coordinator clarification;
- peer text must never be changed, summarized, or semantically routed by Runner;
- Codex inner `read-only` sandbox or same-UID mode bits alone are never accepted as cross-Agent
  isolation evidence;
- every Agent namespace must exclude sibling homes, secrets, sockets, host run root, and sibling
  `/proc` state;
- a Skill request without successful exact-path discovery and model-visible injection evidence is
  failure;
- the effective Modeling Package plus Skill must not instruct the Modeling Agent to perform
  platform calls in a Profile with a distinct Protocol role;
- no dynamic Agent creation, replacement, privilege change, or Profile switch is accepted;
- no timeout is treated as modeling-quality evidence;
- cleanup uncertainty must preserve the target and produce BLOCKED/FAIL evidence rather than delete.

## Regression and required commands

Planned commands, updated with exact implemented entry points during development:

```bash
uv run --project backend python -m unittest discover -s modeling_team/tests -p 'test_*.py'
uv run --project backend ruff check modeling_team
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/base-three-agent.yaml \
  --task modeling_team/tasks/base-capability-smoke.yaml
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/source-specialist-smoke.yaml \
  --task modeling_team/tasks/specialist-interoperability-smoke.yaml
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

If any file under `backend/` changes, also run:

```bash
cd backend && uv run pytest
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

Before commit, run `git diff --check`, GitNexus `detect_changes(scope="compare",
base_ref="main")`, inspect `git status`, and exclude unrelated changes.

## Independent test rounds

Append-only rounds go below. Preserve every failed round and its later disposition.

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

## Cleanup ledger

For each real run record:

- run ID and Profile;
- stable Agent IDs and redacted Runtime IDs;
- scope mode and exact ownership classification;
- Project/Ontology/key IDs without plaintext secrets;
- Agent process stop results;
- key revocation results;
- owned-scope deletion or existing-scope preservation result;
- secret-directory destruction;
- backend/frontend health;
- producer-owned fixture cleanup owner and result.

No cleanup item is inferred from a launcher summary when direct platform/process evidence is
available.

## Round 1 — 2026-07-31T03:15:31+08:00 — independent retained-evidence review — FAIL

- Stable state: uncommitted R2.3-001 worktree based on `5c0e61c45b1183b54a24de986ca38ff0e29a5e21`;
  implementation under `modeling_team/`; frozen producer evidence:
  `workspaces/modeling-runs/r23001-base-20260731r`,
  `workspaces/modeling-runs/r23001-specialist-20260731s`, and
  `workspaces/modeling-runs/r23001-existing-20260731t1`. The tester did not create, continue,
  steer, stop, clean, or otherwise mutate those runs or their fixture.
- Executed automated/static checks:
  `uv run --project backend python -m pytest modeling_team/tests -q` (`25 passed`);
  `uv run --project backend ruff check modeling_team` (`All checks passed`);
  both `python -m modeling_team validate` Profile/Task commands (base roster of 3 and specialist
  roster of 4); and `git diff --check` (PASS).
- Executed retained-evidence/read-only checks: inspected each raw Codex rollout, app-server event
  metadata, Team Transport receipt, terminal record, state/secret paths, and recorded PID state;
  verified model-visible staged `ontology-modeling` Skill input for every Agent; verified one
  `ontology_platform/check_platform_health` call and no modeling MCP call in each run; verified all
  recorded Agent PIDs have stopped and no retained `auth.json`, `config.toml`, `secrets/`, or socket
  remains. Read-only DB checks find each create scope deleted, the existing fixture deleted after
  evidence capture, and all three scopes have zero Project/Ontology, Build Session, Lease,
  Modeling Batch, or active Project key rows. `curl --fail http://127.0.0.1:8001/api/health` returned
  `{"status":"ok"}` and frontend `http://127.0.0.1:5173/` returned `200`.
- Passed evidence within the failed round: base has three and specialist has four distinct real
  Codex Thread IDs; base/raw Coordinator rollout contains the ordinary status input and a Coordinator
  reply; base and existing retain exact direct Modeling-to-Protocol health-result receipts; all
  settled records have one accepted terminal result per roster member; Protocol is the only Agent
  with `ontology_platform` tool events; and current resident cleanup/health state is clean.

### Confirmed defects

1. **Critical — dynamic `exec` can escape its staged path allowlist and read sibling Agent material.**
   Reproduction by static trace: `modeling_team/runtimes/codex.py:704-715` accepts any string that
   merely starts with `/skills/` or `/agent/home/sources/`, then replaces that prefix and invokes
   host `subprocess.run`. A request such as
   `cat /skills/../../protocol/home/config.toml` passes the prefix check and resolves from the
   Modeling Agent's host `skills` directory into the sibling Protocol `home`; it runs outside the
   bubblewrap namespace. This violates A03, R17–R19 and the required per-Agent secret isolation.
   Existing `test_dynamic_exec_reads_only_staged_skill_and_source` tests a direct forbidden path but
   not traversal. No adversarial retained-run probe demonstrates denial. Expected: canonicalized
   path containment (or no host dynamic shell) and failed real sibling, `/proc`, broker-impersonation,
   and unauthenticated-write probes. Actual: bypass is possible by construction and no live denial
   evidence exists.
2. **High — ordinary Coordinator replies are not mechanically returned by the Runner.**
   Reproduction by static trace: `CodexRuntimeAdapter._notification`
   (`modeling_team/runtimes/codex.py:621-624`) only queues top-level `params.text` for
   `item/completed`/`item/updated`. The retained base app-server evidence records
   `item/agentMessage/delta` events, while the base evidence directory contains no
   `coordinator.jsonl`. `TeamRunner.drain` can therefore emit no outer Coordinator reply despite
   the raw internal rollout containing one. Expected: outer user text is returned exactly as a
   Coordinator message without becoming a peer delivery. Actual: only the internal Codex rollout
   proves the reply; the Team Runner's output/evidence path drops it. This fails acceptance 4 and
   R07/R09's live path.
3. **High — base Agent terminal ownership is not exactly once.** The Modeling rollout
   `runtime/modeling/home/sessions/2026/07/30/rollout-2026-07-30T18-57-28-019fb463-829b-7622-bf67-d7ef34ba8949.jsonl`
   records accepted `report_task_result(completed)` at lines 43–44, then a second attempt at
   lines 64–66 after the supplement, rejected with `Unexpected response type`. The broker retained
   only one result, but R10 and the real-run acceptance require the Agent itself to submit one
   terminal envelope. Expected: no second terminal call after a completed result. Actual: two
   calls, one rejected.
4. **Medium — specialist extension proof lacks required immutable hash evidence.**
   `r23001-specialist-20260731s` contains four real Threads, Skill input, direct exchange, one
   Protocol health call, terminal results, and cleanup, but neither state, evidence, nor delivery
   material records the Runner/Codex Adapter hashes before and after the run. Requirement/test-plan
   item 7 cannot be independently established. Expected: retained before/after hashes for
   `modeling_team/runner.py` and `modeling_team/runtimes/codex.py`. Actual: absent.
5. **Medium — live adversarial isolation evidence is absent.** The real rolls prove the normal
   allowlisted MCP surface, not the required failures for sibling files, `/proc`, broker
   impersonation, and unauthenticated platform writes. Static namespace construction and unit tests
   cannot satisfy the explicit real-run R17–R19 gate, especially with defect 1 present.

- Unexecuted/blocked acceptance work: no safe retest of the frozen evidence was performed because
  these defects require implementation repair and fresh producer-owned runs. The test plan's direct
  producer fixture-cleanup record is also absent, although the independent read-only DB state now
  confirms that fixture no longer exists.
- Conclusion: **FAIL**. Do not accept R2.3-001 or create a new independent test plan. The
  Requirement Developer should first repair the confirmed causes, add focused regressions (including
  traversal and app-server Coordinator-message extraction), then produce fresh base, specialist,
  and existing producer-owned runs with retained adversarial and hash evidence before Round 2.

## Round 2 — 2026-07-31T03:57:25+08:00 — independent retained-evidence retest — FAIL

- Stable state: the same uncommitted R2.3-001 worktree, with fresh frozen producer evidence at
  `workspaces/modeling-runs/r23001-round2-base-accept`,
  `workspaces/modeling-runs/r23001-round2-specialist-accept`, and
  `workspaces/modeling-runs/r23001-round2-existing-accept`. The tester performed only offline,
  static, process/health, database-read, and retained-evidence checks; it did not create, continue,
  steer, stop, clean, or mutate a Team Run or fixture.
- Automated checks PASS:
  `uv run --project backend python -m pytest modeling_team/tests -q` (`30 passed, 7 subtests
  passed`); `uv run --project backend ruff check modeling_team` (`All checks passed`); both Profile
  validation commands (base roster 3, specialist roster 4); and `git diff --check`.
- Round 1 defects fixed and independently evidenced:
  - canonical read containment now uses strict path resolution; the base raw Modeling rollout
    executes each of the five prescribed probes exactly once, including
    `cat /skills/../../protocol/home/config.toml`, and each fails. Existing-mode raw execution
    independently repeats the five failure categories. No probe result exposes private data;
    `test_dynamic_exec_rejects_traversal_and_host_probe_paths` and denial-evidence tests pass;
  - `item/agentMessage/delta` assembly yields retained `coordinator.jsonl` entries that exactly
    match raw Coordinator replies to ordinary outer status messages. No ordinary-status peer
    delivery is present;
  - every Agent has exactly one successful `report_task_result` call in each fresh run; non-
    Coordinator terminal results have retained Coordinator handoff records;
  - base and existing deliver the exact supplement once to Modeling and Protocol before their
    terminal handoffs; Modeling-to-Protocol health request/result receipts are direct, and Protocol
    is the sole `ontology_platform/check_platform_health` caller;
  - specialist has four real Thread identities, model-visible Skill input for all four Agents, a
    direct Source Specialist-to-Modeling receipt, no specialist platform MCP call, and matching
    before/after SHA-256 values for `runner.py` and `runtimes/codex.py`;
  - existing has `owned=false`, identical before/after empty context, and retained producer fixture
    cleanup `DELETE 204`, then Project/Ontology `GET 404`.
- Independent cleanup/zero-write verification PASS: read-only DB checks for the three frozen scope
  identifiers return no Project/Ontology, Build Session, Lease, Modeling Batch, or active Project
  key; all recorded app-server PIDs have stopped; no retained `auth.json`, `config.toml`, secret
  path, or socket remains; backend health returned `{"status":"ok"}` and frontend returned `200`.

### Confirmed defect

1. **High — Coordinator's post-settlement user-facing final summary is absent.** This is distinct
   from the Coordinator's own terminal result: that result is correctly submitted once, but it is
   submitted *before* settlement. In the raw Coordinator rollouts, the accepted terminal reports
   occur at `19:47:53.129Z` (base), `19:50:34.054Z` (specialist), and `19:53:11.647Z` (existing),
   while the corresponding `settled.jsonl` records are later at `19:48:11.981948Z`,
   `19:50:36.375433Z`, and `19:53:13.971562Z`. After the Coordinator's terminal result, no
   non-empty user-facing final summary is retained; the existing raw rollout's final answer is
   empty. The Runner emits its own settled envelope but never returns the settled fact to the
   Coordinator for a user-facing summary. This fails real-base requirement 10 and the requirement's
   terminal contract: Runtime settlement must precede the Coordinator's final user report.
   Expected: exactly one Coordinator-owned final user summary after all Threads settle. Actual:
   Coordinator terminal result precedes settlement and no post-settlement final user message exists.

- Conclusion: **FAIL**. Round 1's five recorded defects are fixed for this evidence set, but the
  terminal handoff/settlement sequence remains a release-blocking defect. The Requirement Developer
  should route the once-only settled fact to the Coordinator and retain its post-settlement final
  user message, then produce fresh producer-owned evidence for a Round 3 retest. No modeling-quality
  claim is made.

## Round 3 — 2026-07-31T04:37:03+08:00 — independent retained-evidence retest — FAIL

- Stable state: the same uncommitted R2.3-001 worktree, with fresh frozen producer evidence at
  `workspaces/modeling-runs/r23001-round3-base-envelope`,
  `workspaces/modeling-runs/r23001-round3-specialist-envelope`, and
  `workspaces/modeling-runs/r23001-round3-existing-envelope`. The tester performed only offline,
  static, process/health, database-read, and retained-evidence checks. It did not create, continue,
  steer, stop, clean, or mutate a Team Run or fixture.
- Automated checks PASS:
  `uv run --project backend python -m pytest modeling_team/tests -q` (`32 passed, 7 subtests
  passed in 0.13s`); `uv run --project backend ruff check modeling_team` (`All checks passed`);
  both Profile validation commands (base roster 3 and specialist roster 4); and `git diff --check`.
- Passed retained-evidence checks: direct comparison of every delivery ledger record with the target
  raw Runtime user message establishes the exact unrewritten `{sender_id,text}` envelope for all
  5 base, 7 specialist, and 7 existing-mode deliveries. Each base Agent (3), specialist Agent (4),
  and existing-mode Agent (3) has exactly one accepted `report_task_result`; non-Coordinator
  results have terminal Coordinator handoffs. Direct sender attribution, the ordinary Coordinator
  reply, and exactly-once Coordinator supplement delivery to each declared existing-mode target
  are retained. Only Protocol invokes `ontology_platform/check_platform_health`, once per run.
- Passed security/lifecycle checks: raw base and existing-mode rolls retain five failed fixed probes
  (sibling Skill traversal, `/proc`, broker socket, foreign run state, and unauthenticated project
  write), without private-data disclosure. Each run has exactly one settlement and one non-empty
  Coordinator final after it: base `20:26:32.960522Z` then `20:26:39.767246Z`, specialist
  `20:24:59.201775Z` then `20:25:06.591311Z`, and existing `20:28:58.724575Z` then
  `20:29:03.017302Z`. Retained before/after hashes and current hashes agree for `runner.py`
  (`d53d799c19d7b6afc0df1de4b92d4b4fe1fd7712c8f6f255c2b03b3709698d28`) and `runtimes/codex.py`
  (`1479ed8cbf1163b2aa63aeb743550b24c27da0c035f1362cf117421aeaf90ac4`). All recorded Agent PIDs
  are gone; states are `CLEANED`; private credential material is absent; and the read-only DB query
  for all three scope Project IDs finds zero Projects, Ontologies, Build Sessions, Leases, Modeling
  Batches, and active Project keys. Backend health returned `{"status":"ok"}` and frontend health
  returned `200`. Existing-mode before/after context remains the same empty workspace, and its
  producer fixture ledger contains four records including owner `DELETE 204`, then Project and
  Ontology `GET 404`.

### Confirmed defect

1. **High — Existing-mode Modeling attempts to re-forward an already delivered outer supplement.**
   In the frozen raw Modeling rollout
   `runtime/modeling/home/sessions/2026/07/30/rollout-2026-07-30T20-27-25-019fb4b5-de7e-7e71-a78c-04cb6b39dfa4.jsonl`,
   Modeling receives the exact Coordinator envelope at `20:27:55.450Z`, then calls
   `send_team_message` with the same text first to `modeling` at `20:27:58.257Z` and again to
   `/root/modeling` at `20:28:03.821Z`. Both calls are rejected by transport with `Unexpected
   response type`, so no duplicate delivery, write, or secret disclosure occurred. Nevertheless,
   this is a real role-contract violation: `modeling_team/agent-packages/modeling/instructions.md`
   lines 14–16 say that a Coordinator-forwarded supplement is already delivered and that Modeling
   must not re-forward that outer text to any Agent. Expected: Modeling consumes the single direct
   Coordinator delivery and performs no forwarding attempt. Actual: it attempts two self-directed
   re-forwards, relying on transport rejection rather than honoring its role boundary. The rejected
   deliveries therefore do not satisfy the required explicit Agent behavior.

- Conclusion: **FAIL**. Round 2's missing post-settlement Coordinator summary is fixed, and all
  other requested Round 3 checks pass, but the existing-mode role still violates the explicit
  outer-supplement handling contract. The Requirement Developer should correct the Modeling
  role/task interaction and add a focused regression that asserts no re-forward attempt (not merely
  no successful duplicate receipt), then provide fresh producer-owned evidence for a Round 4 retest.

## Round 4 — 2026-07-31T04:47:17+08:00 — independent retained-evidence retest — PASS

- Stable state: the same uncommitted R2.3-001 worktree, with fresh frozen producer evidence at
  `workspaces/modeling-runs/r23001-round4-base-envelope`,
  `workspaces/modeling-runs/r23001-round4-specialist-envelope`, and
  `workspaces/modeling-runs/r23001-round4-existing-envelope`. The tester performed only offline,
  static, process/health, database-read, and retained-evidence checks. It did not create, continue,
  steer, stop, clean, or mutate a Team Run or fixture.
- Automated checks PASS:
  `uv run --project backend python -m pytest modeling_team/tests -q` (`33 passed, 7 subtests
  passed in 0.14s`); `uv run --project backend ruff check modeling_team` (`All checks passed`);
  both Profile validation commands (base roster 3 and specialist roster 4); and `git diff --check`.
- Raw Runtime Delivery contract PASS: all 4 base, 5 specialist, and 6 existing-mode ledger records
  match exactly one recipient-side raw user envelope with identical `sender_id`, `recipient_id`,
  `kind`, and `text`; `kind` is `peer` for peer deliveries and `outer-forward` for forwarded outer
  context. Direct peer sender attribution is therefore preserved, including the Modeling↔Protocol
  health exchange and Source Specialist↔Modeling interoperability exchange. In both base and
  existing-mode evidence, the outer supplement has exactly two successful delivery calls,
  Coordinator→Modeling and Coordinator→Protocol, one each. A raw scan of every non-Coordinator
  rollout finds **zero** `send_team_message` calls carrying that exact supplement text (the Round 3
  defect is fixed, rather than merely being transport-rejected).
- Terminal/lifecycle contract PASS: every frozen Agent has exactly one successful raw
  `report_task_result` call (base 3, specialist 4, existing 3); non-Coordinator terminal results
  have Coordinator handoffs; each run has exactly one settlement and exactly one non-empty retained
  Coordinator final after settlement. The raw Coordinator records include the post-settlement
  sender event. Settlement/final times are base `20:42:04.828024Z` → `20:42:10.253846Z`, specialist
  `20:40:53.145770Z` → `20:40:58.505670Z`, and existing `20:44:08.871488Z` →
  `20:44:14.119227Z`.
- Security, permissions, and cleanup PASS: Protocol alone successfully calls
  `ontology_platform/check_platform_health`, once per run; the staged ontology-modeling Skill and
  bounded sources are present in the raw Agent inputs. Base and existing raw rolls execute the five
  fixed isolation probes (sibling traversal, `/proc`, transport socket, foreign run state, and
  unauthenticated project write) and retain only their prescribed failure categories, with no
  private data disclosed or ontology writes. Before/after and current hashes agree for `runner.py`
  (`aa6b5dd070581d0021d80ebbb7da8cecd6eb563f9a7d042a1e85bd1e618d04b5`) and `runtimes/codex.py`
  (`7390b88329ca0e1b1cc32021cf735bd0ee61a2715e32b7cd822e0640e9ecb6f4`). All 10 recorded Agent
  PIDs are gone, every state is `CLEANED`, and every retained Agent has
  `private_credentials_destroyed=true`; no retained `auth.json`, `config.toml`, or socket exists.
  Read-only DB queries for the three scope Project IDs return zero Projects, Ontologies, Build
  Sessions, Leases, Modeling Batches, and active Project keys. Backend health returned
  `{"status":"ok"}` and frontend health returned `200`.
- Scope ownership PASS: base and specialist create scopes retain revoked keys and developer-owned
  Project deletion. Existing-mode is explicitly `owned=false`, retains identical before/after empty
  workspace context, and its three producer-fixture records show runner preservation followed by
  producer-owned `DELETE 204`, Project `GET 404`, and Ontology `GET 404`.

- Conclusion: **PASS**. All historical acceptance gates, including the Round 3 no-re-forward
  behavior, are independently evidenced for the three frozen Round 4 runs. No product, Skill,
  design, delivery record, run, or fixture was changed by the tester.
