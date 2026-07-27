# R2.1-001 M4 建模 Agent 主动业务语义澄清共享测试计划

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M4
- Design:
  `docs/delivery/designs/2026-07-27-r2-1-001-m4-proactive-semantic-clarification-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Status: PASS — core M4 requirement accepted through Round 30; runtime closure recorded below
- Test rounds: append-only

## Fixed test boundary

The visible inputs are the M4 sanitized brief, allowed direct-source excerpts, generic public platform
contract and deterministic feedback produced by the same run. The following are never Agent-visible:

- the complete `requirements-v2.1.md`, M1–M3 answer models, Batch payloads, answer queries, retained
  runs, acceptance specifications and hidden-answer files;
- the baseline and variant values of the three business decisions;
- host responder source, audit and response directories, except for the one read-only response file
  corresponding to an Agent request.

Each run uses a fresh Project, Ontology, Build Session, external Agent process, temporary `CODEX_HOME`,
staging root and host answer contract. The normal platform remains separate; formal M4 application uses
an isolated `rdf_primary` backend only after its write mode is verified.

## Completion gates

1. The Agent independently identifies and serially asks every withheld lifecycle, identity and
   missing-value decision from the visible-input gaps. An independent check must match each question's
   own terms and stated impact to its business decision; the Agent receives neither an area enumeration
   nor an expected question count. Questions do not leak a hidden answer or prescribe ontology structure.
2. Facts explicit in the visible brief are not asked again. Duplicate, concurrent, malformed or ineligible
   requests fail closed and cannot substitute for a necessary clarification.
3. Each accepted answer has a complete request/response/audit/Agent-log/Batch/query hash chain.
4. Baseline and withheld answer variants make the required current-target and output-continuity semantic
   differences observable in tester-owned queries; a decision log alone is insufficient. The pinned
   variant returns a concrete older C target and contract, while the non-successor variant returns explicit
   old-contract removal and distinct new-contract addition/discontinuity facts.
5. The uncertain response becomes an explicit model gap and remains unknown in the read-only consumer;
   it is never converted to a fallback, absence or confirmed fact.
6. All final writes use immutable Modeling Batch dry-run then `apply_atomic` with a fresh version and
   valid lease. No direct RDF, semantic edit, dataset load, `validate=false`, Dify-specific product code
   or main-agent semantic intervention is permitted.
7. Validation uses the explicit Shapes graph and rejects an Agent-created invalid Invocation. A supported
   reasoning expectation, C -> B -> A context query and Current Draft/Latest Version separation pass.
8. Input/mount, host-path, transcript, credential, request/response receipt and hidden-contract secrecy
   audits pass. The accepted M1–M3 behavior suites still pass.
9. An independent tester records PASS in a later round of this plan; temporary isolated services and
   uniquely owned data are cleaned up, then regular service health is verified.

## Planned cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| M4-01 | Visible-input and hidden-answer isolation | Frozen M4 manifest/staging hashes; exact mounts; no hidden answer, M1–M3 answer artifact, credential or host path in Agent namespace/transcript. |
| M4-02 | Clarification spool policy | Atomic request/host response hashes; symlink, duplicate ID, malformed JSON, tampered response, ineligible request and simultaneous-open-question negatives fail closed. No hidden-decision category or count is Agent-visible. |
| M4-03 | Necessary, serial questions | Tester maps each accepted question's terms and impact to a withheld visible-input gap; one outstanding request at a time; no question for documented current/draft facts. Generic or decoy questions cannot satisfy the required gaps. |
| M4-04 | Lifecycle baseline | Baseline hidden answer leads the Agent to model B as following C Latest Version; withheld query observes the new C contract on the current B target. |
| M4-05 | Lifecycle variant | A fresh pinned-version answer run returns the concrete earlier published C Version and its contract as B's current target. Tester query proves this positive target differs from M4-04. |
| M4-06 | Output-identity baseline and variant | Successor answer produces a modeled continuity relation. Non-successor answer returns explicit old-contract removal plus distinct new-contract addition/discontinuity facts. Tester-owned queries prove the positive distinction without comparing graph text. |
| M4-07 | Explicit unknown | Missing-score response is `uncertain`; its reason, named gap and consumer result remain unknown and contain no invented fallback/absence behavior. |
| M4-08 | Answer-to-model traceability | Every accepted request binds one response, assumption change, immutable Batch item/rationale or gap, dry-run/apply Attempt and query result. |
| M4-09 | Formal semantic path | Fresh Project/Ontology/Session, Evidence separation, dry-run correction or acceptance, atomic apply, Shapes graph, invalid Invocation rejection and no bypass. |
| M4-10 | Reasoning and retained M3 semantics | Supported inference, published C -> B -> A propagation, draft/latest separation and explicit pre-existing gap remain valid. |
| M4-11 | Blind consumer | Fresh isolated read-only consumer derives an explanation only from platform facts, distinguishes source/synthetic/inference/judgment, observes M4 differences and preserves unknown. |
| M4-12 | Variant/mutation independence | Tester-owned remove/sentinel/decoy mutations and separate withheld queries cannot be satisfied by Cartesian joins, stale baseline results, a negative absence check or an answer log without model change. |
| M4-13 | Scope review | Diff confirms no backend, frontend, migration, M1–M3 or Dify-specific platform change; any platform-gap result is documented as blocked rather than patched here. |
| M4-14 | Focused regressions | M4 launcher/responder/consumer tests, M1 behavior suite, M2 behavior suite, M3 scenario suite and relevant generic backend tests pass. |
| M4-15 | Runtime closure | Ruff, `git diff --check`, isolated-service cleanup and regular `8001`/`5173` health checks pass. |

## Required verification

The implementation agent must run its focused M4 tests and the applicable M1/M2/M3 suites before handoff.
The independent tester must create fresh baseline and variant acceptance runs rather than inspecting only
the producer's model or decision log. It must verify response-file and transcript hashes before using
any semantic result, construct withheld semantic queries independently, and retain all failed rounds in
this plan.

Required final commands, subject to exact M4 runner names finalized in implementation:

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests`
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py`
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/test_scenario_m2.py`
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m3/tests`
- `uv run --directory backend pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py`
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m4`
- `git diff --check`

After any changed backend or frontend surface (none is planned), run the repository-required complete
suite/build, restart `ontology-platform.service`, and verify `http://127.0.0.1:8001/api/health` and
`http://127.0.0.1:5173/`. Scenario-only work still verifies regular runtime health after isolated-run
cleanup.

## Test rounds

Initial state: no M4 implementation or independent test round has run. Append every later round below;
never replace a failed round with its repair result.

## Round 1 — 2026-07-27 independent test (FAIL)

### Baseline and scope

- Worktree handoff was uncommitted. Relevant M4 design, this shared plan and the complete
  `docs/evaluation-scenarios/dify-workflow-impact-m4/` package were untracked; the main-agent-owned
  delivery record was modified and was not edited by this tester. No `backend/`, `frontend/`, migration,
  or M1--M3 scenario change was present.
- Executed the focused M4 protocol/semantic checks, a real `bwrap` mount preflight, M1--M3 and generic
  semantic regressions, formatting/diff checks, and regular-service health checks. The temporary
  `/tmp/m4-independent-round1` preflight root was deleted after the mount probe.
- Did not and cannot execute a fresh external-Agent baseline or withheld-variant formal Modeling Batch
  run: the sole launcher deliberately exits with `BLOCKED` unless `--prepare-only` is supplied.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (preflight only) | `prepare-only` verified frozen staging hashes; an actual `bwrap` probe confirmed `/opt/input-manifest.json` is readable, request mount writable, response mounts read-only, and neither `/mnt/host` nor `/opt/hidden-contract.json` exists. A formal-Agent transcript/credential audit remains unexecuted with M4-04--M4-12. |
| M4-02 | PASS | Focused tests cover canonical/malformed, duplicate, pre-created response, ineligible, simultaneous and API credential negatives. An additional independent symlink request was rejected as `request is not a regular non-symlink file`. |
| M4-03 | FAIL | Three natural, semantically equivalent clarification questions were each answered `not_eligible`; see defect M4-R1-01. Exact hidden-contract tokens rather than the question's business meaning are required. |
| M4-04 | BLOCKED | No fresh baseline Agent run, Project/Ontology/Session, Batch, query, or semantic observation exists. |
| M4-05 | BLOCKED | No fresh withheld pinned-version Agent run or positive alternate-target query exists. |
| M4-06 | BLOCKED | The unit test only passes hard-coded observation dictionaries; no baseline/variant applied model or tester-owned query exists. |
| M4-07 | BLOCKED | The responder unit test emits `uncertain`, but no Agent-created explicit gap or read-only consumer result exists. |
| M4-08 | BLOCKED | No Agent decision log, consumption receipt, immutable Batch input, dry-run/apply Attempt, or query hash chain exists. |
| M4-09 | BLOCKED | No formal Modeling Batch dry-run/apply, lease, Evidence separation, Shapes graph or invalid-Invocation rejection was run. |
| M4-10 | BLOCKED | No formal inference/context-query proof of C -> B -> A propagation or draft/latest separation was run. |
| M4-11 | BLOCKED | No fresh isolated read-only consumer run exists. |
| M4-12 | BLOCKED | No tester-owned applied-model remove/sentinel/decoy mutation run exists; static positive-observation helpers do not prove mutation independence. |
| M4-13 | PASS | `git diff --check` passed and worktree inspection found only allowed M4 docs/scenario artifacts plus the main-agent delivery record; no product, migration or M1--M3 change was made. |
| M4-14 | PASS | M4: 8 passed; M1: 13 passed; M2: 5 passed; M3: 27 passed; generic Modeling Batch/validation/reasoning/context-query tests: 69 passed. |
| M4-15 | PASS | M4 Ruff and `git diff --check` passed. No isolated service was started; temporary preflight root was cleaned. `ontology-platform.service` was active and both `GET :8001/api/health` and `GET :5173/` succeeded. |

### Commands and actual results

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` — **8 passed**.
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m4` — **All checks passed**.
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` — **13 passed**.
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/test_scenario_m2.py` — **5 passed**.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m3/tests` — **27 passed**.
- `uv run --directory backend pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py` — **69 passed** (five existing deprecation warnings).
- `python3 .../run_m4_clarification.py --run-root /tmp/m4-independent-nonprepare --variant baseline --run-tag m4-independent-nonprepare` — exit **2**, `{"status": "BLOCKED", "reason": "only --prepare-only is available until an independent formal run is configured"}`.
- The README's documented `python .../run_m4_clarification.py` command cannot start in this environment because `python` is not installed; `python3` successfully ran the preflight.

### Defects

1. **M4-R1-02 — Critical: no formal external-Agent execution path is implemented.**
   - Reproduction: invoke `run_m4_clarification.py` without `--prepare-only` using a fresh root and either supported variant.
   - Expected: the launcher starts the isolated Agent/responder/API spool lifecycle and retains the required decision, Modeling Batch, validation, reasoning, query and consumer evidence for independent acceptance.
   - Actual: parser/launcher exits 2 with `only --prepare-only is available until an independent formal run is configured`.
   - Evidence: launcher lines 210--214; direct independent invocation above; README also says formal baseline/variant application remains a later independent step.
   - Impact: M4-04--M4-12 are unimplemented and unexecuted. Preparation, mocked protocol checks and hard-coded semantic audit observations are not formal behavioral proof.

2. **M4-R1-01 — High: eligible natural-language clarifications are rejected by hidden token matching.**
   - Reproduction: send canonical requests whose business meaning directly covers each visible gap, for example: `Does B follow C's latest release or an earlier published release?`, `Is quality rating the successor to quality score, or a separate change?`, and `What should B do if scoring data is unavailable?`.
   - Expected: the responder recognizes each question and stated impact by business meaning, returning the matching `answered` or `uncertain` result without requiring a fixed wording, as required by the design's clarification transport contract.
   - Actual: all three return `{"status":"not_eligible","reason":"The request does not reach an answerable visible-input gap."}`. The implementation requires every hidden `required_terms` token (including literal forms such as `invocation`, `quality_rating`, `contract`, `missing`, and `fallback`) to occur in the request.
   - Evidence: independent `python3` tempfile probe on 2026-07-27, three requests/three `not_eligible` responses. Existing focused test accepts only hand-crafted requests containing the hidden token sets, so it does not catch this behavior.
   - Impact: violates wording-independent proactive clarification and makes a real Agent's valid question unreliable; M4-03 fails before any formal semantic run.

3. **M4-R1-03 — Low: the scenario README's launcher command is not executable as documented.**
   - Reproduction: run its documented `python docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py ...` command.
   - Expected: documented preflight command starts the launcher.
   - Actual: `/bin/bash: python: command not found`; `python3` works.
   - Evidence: Round 1 isolation-preflight command exit 127 before the corrected `python3` invocation.

### Round conclusion and required next step

**FAIL.** The reusable protocol/preflight and regression checks are healthy, but the M4 acceptance
contract is not met: M4-03 has a verified behavior defect, and M4-04--M4-12 have no executable formal
run or evidence. Do not accept `PREPARED` namespaces as a substitute for baseline/variant behavior.
Send M4-R1-01 and M4-R1-02 to the requirement developer, then request a new stable handoff and retest
the same plan starting with M4-03--M4-12 and the affected isolation regressions.

## Round 2 — 2026-07-27 independent repair retest (BLOCKED)

### Scope and repair disposition

- Retested the same stable M4-only scenario handoff. Concurrent main-agent documentation changes to the
  delivery record and requirements file were preserved and not edited by this tester; no product code was
  changed by this round.
- **M4-R1-01 — FIXED:** focused M4 tests increased to 10 passing. An independent tempfile probe sent the
  three Round-1 natural questions and received `answered`, `answered`, and `uncertain` respectively.
  The documented-current-draft decoy remains `not_eligible` in the focused test.
- **M4-R1-02 — FIXED structurally, not yet behaviorally accepted:** a non-prepare invocation now executes
  `verify_isolated_write_mode` and returns `BLOCKED: isolated backend canonical-mode response is invalid`
  when port 8012 is absent. It no longer exits on a hard-coded `--prepare-only` condition, and the
  launcher includes host responder/API watch services, fresh Codex home, bwrap/Codex command and final
  audit paths. A formal Agent run could not start for the independent reason below.
- **M4-R1-03 — FIXED:** README now documents `python3`.

### Formal-environment attempt and cleanup

The established M3 runner confirms that formal acceptance requires a temporary backend at `8012` with
`product_write_mode=rdf_primary`; it does not provide a reusable startup script. To reproduce that path
without touching regular `8001`, this round created a uniquely named PostgreSQL database
`m4_round2_20260727` from `template0`, a separate Oxigraph container on `127.0.0.1:7879`, and passed
only the isolated database/RDF URLs and RDF-primary mode flags to Alembic. This is the minimum fresh
backend setup implied by the M3/M4 launchers.

Alembic stopped during migration `0002_relation_type_name_scope` before the backend could start:

```text
psycopg.errors.UndefinedObject: constraint "uq_relation_types_ontology_name"
of relation "relation_types" does not exist
```

The fresh database and container were then explicitly stopped/dropped. Final checks confirmed no
`m4_round2_20260727` database, no `ontology-platform-m4-round2-oxigraph` container, and no listeners on
8012 or 7879. Regular `ontology-platform.service`, `:8001/api/health` and `:5173/` remained healthy.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (preflight); BLOCKED (formal transcript) | Frozen manifest/mount protocol and no-host-contract command assertions pass. No formal Agent transcript can exist until the isolated backend starts. |
| M4-02 | PASS | Focused 10-test suite retains fail-closed spool and credential checks. |
| M4-03 | FIXED / PASS | Natural lifecycle and output-identity questions were `answered`; natural missing-score question was `uncertain`; focused decoy remains rejected. |
| M4-04 | BLOCKED | Fresh baseline Agent/Batch/query cannot start because the isolated backend cannot migrate. |
| M4-05 | BLOCKED | Fresh pinned/non-successor Agent/Batch/query cannot start for the same reason. |
| M4-06 | BLOCKED | No applied baseline/variant models or tester-owned positive semantic queries exist. |
| M4-07 | BLOCKED | No Agent-created explicit gap or consumer observation exists. |
| M4-08 | BLOCKED | No formal request/response/decision/Batch/query hash chain exists. |
| M4-09 | BLOCKED | No Project/Ontology/Session, dry-run/apply, Shapes or invalid-Invocation evidence exists. |
| M4-10 | BLOCKED | No formal reasoning or C -> B -> A query evidence exists. |
| M4-11 | BLOCKED | The new consumer launcher was structurally inspected but cannot start against a non-existent isolated backend; no consumer record exists. |
| M4-12 | BLOCKED | M4 still supplies no executed tester-owned mutation path, and no applied model is available to mutate. |
| M4-13 | PASS | M4 implementation remains scenario-local; concurrent documentation edits were preserved. No backend/frontend/migration implementation was edited for M4. |
| M4-14 | PASS | M4 10; M1 13; M2 5; M3 27; focused generic backend 69 all passed (the backend suite retains five deprecation warnings). |
| M4-15 | PASS | M4 Ruff and `git diff --check` passed. Round-owned database/container/ports were cleaned; normal service and health endpoints passed. |

### Commands and actual results

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` — **10 passed**.
- Independent responder probe — lifecycle/output natural questions: **answered**; missing-score natural
  question: **uncertain**.
- Non-prepare launcher against absent `8012` — exit **2**, structured
  `BLOCKED: isolated backend canonical-mode response is invalid`; confirms the formal path reaches the
  actual dependency preflight rather than `--prepare-only` logic.
- Fresh isolated database (`template0`) + isolated Oxigraph +
  `DATABASE_URL=<owned-db> OXIGRAPH_URL=http://127.0.0.1:7879 SEMANTIC_*={rdf,rdf_primary,rdf,true}`
  `uv run --directory backend alembic upgrade head` — **failed** at migration `0002` as recorded above.
- M1/M2/M3 and generic backend regression commands — **13/5/27/69 passed**; M4 Ruff and diff check
  passed; regular health checks passed.

### Defect

1. **M4-R2-01 — Critical acceptance blocker: a fresh isolated PostgreSQL database cannot migrate to
   head.**
   - Reproduction: create a unique database from `template0`, then run the repository Alembic upgrade
     with the standard isolated M3/M4 database URL.
   - Expected: the database reaches the current migration head so a separate `rdf_primary` backend can
     boot on 8012 without using or mutating the regular service state.
   - Actual: `0001_initial_metadata` creates
     `uq_relation_types_ontology_name_source_target`, but `0002_relation_type_name_scope` immediately
     attempts to drop the absent older `uq_relation_types_ontology_name`; Alembic raises
     `UndefinedObject` and exits non-zero.
   - Evidence: independent Round-2 command output and
     `backend/migrations/versions/0001_initial_metadata.py` / `0002_relation_type_name_scope.py`.
   - Impact: no fresh isolated backend, external Agent, Modeling Batch, consumer or mutation acceptance
     can run. M4-04--M4-12 remain unexecuted; no test result was promoted from structural proof to PASS.

### Round conclusion and next step

**BLOCKED.** Round-1 responder and launcher defects are repaired at the protocol/structural level, but
the required fresh runtime cannot be established because the repository migration chain fails on a new
database. Have the responsible developer repair and independently verify the migration chain on a fresh
owned database, then return a stable M4 handoff. The next round must first execute fresh baseline and
variant runs, then the read-only consumer and tester-owned mutation/query evidence for M4-04--M4-12.

## Round 3 — 2026-07-27 independent formal-attempt retest (BLOCKED)

### Fresh runtime preconditions proved

- Independently ran `RUN_POSTGRES_MIGRATION_TESTS=1 uv run --directory backend pytest
  tests/test_migrations.py -rs`: **4 passed**.
- Created owned database `m4_round3_20260727` from `template0`, separate
  `ontology-platform-m4-round3-oxigraph` on `127.0.0.1:7879`, then ran Alembic with isolated
  `DATABASE_URL`, `OXIGRAPH_URL`, and RDF-primary settings. `alembic upgrade head` completed through
  revision `0031_retrieval_label_evidence`.
- Started an isolated `8012` backend only for this database and confirmed canonical mode:
  `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`,
  `legacy_write_blocked=true`. The fresh database received a bootstrap-admin record only for the existing
  host MCP key; it was dropped with the database during cleanup.

### Formal baseline attempt and scope change

The baseline launcher was invoked without `--prepare-only` with a 600-second bound. It started the host
clarification and API watch services, entered bwrap and launched a real fresh `/codex exec` process.
The attempt's transcript SHA-256 was
`dfb16213dc22b8d88a93ad6a235b44d6fdc42786f6b9eea9edc3661b09c89351`.

At the snapshot actually launched, the host proxy environment was present but M4's bwrap command had no
`HTTPS_PROXY`/`HTTP_PROXY` forwarding, unlike the accepted M3 launcher. The Agent transcript recorded
WebSocket retries and HTTPS-fallback timeouts. It made **zero** API-spool or clarification-spool requests,
created no runtime record or decision log, and no Modeling Batch or semantic result existed. The bounded
attempt was stopped; because `KeyboardInterrupt` occurs outside the launcher's handled timeout path, it
did not write a final-run audit.

During this attempt, another agent changed `run_m4_clarification.py` and its test at approximately
11:54--11:55 local time to add a proxy allowlist. The current focused suite then reported 11 passed, but
that newer snapshot was not the code executed by this formal attempt. This round therefore does not
claim that the new proxy implementation is behaviorally verified.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (fresh migration/mount preconditions); BLOCKED (complete formal audit) | Fresh isolated RDF-primary backend and actual bwrap/Codex start were proven, but no completed Agent transcript/audit exists. |
| M4-02 | PASS | Current focused protocol suite: 11 passed. |
| M4-03 | PASS (retained) | Natural-language matching repair remains covered by the focused suite; no new Agent question was reached in this attempt. |
| M4-04 | BLOCKED | Baseline Agent did not reach any API call, Batch or current-target query. |
| M4-05 | BLOCKED | Pinned/non-successor run was not started after the baseline transport failure and mid-round source change. |
| M4-06 | BLOCKED | No applied baseline/variant models or independent positive semantic queries. |
| M4-07 | BLOCKED | No modeled explicit gap or consumer observation. |
| M4-08 | BLOCKED | No request/response/decision/Batch/query hash chain. |
| M4-09 | BLOCKED | No Project/Ontology/Session, dry-run/apply, Shapes or invalid-Invocation result. |
| M4-10 | BLOCKED | No reasoning or C -> B -> A query evidence. |
| M4-11 | BLOCKED | Consumer was not started: no successfully applied model and the launcher snapshot changed mid-round. |
| M4-12 | BLOCKED | No applied model was available for tester-owned remove/sentinel/decoy mutations. |
| M4-13 | PASS | M4 stayed scenario-local; migration changes were separately handed off and M5 artifacts were not touched. |
| M4-14 | PASS | M4 11; M1 13; M2 5; M3 27; focused generic backend 69; migration tests 4 all passed. |
| M4-15 | PASS | M4 Ruff, `git diff --check`, regular 8001/5173 health and owned-resource cleanup passed. |

### Defect / residual blocker

1. **M4-R3-01 — High (observed in launched snapshot; superseded but unverified): proxy environment was
   not propagated into the formal Codex namespace.**
   - Expected: the bwrap allowlist passes only configured HTTP(S) proxy variables needed for the external
     Agent transport, with values redacted from audits, as M3 already does.
   - Actual in the launched baseline: host proxy configuration was present; M4 command construction had
     no proxy environment entries; Codex exhausted WebSocket and HTTPS fallback timeouts before its first
     platform request.
   - Evidence: baseline transcript hash above and launcher/M3 command inspection at the time of launch.
   - Current status: a concurrent untested patch added proxy-allowlist code and one focused test after the
     baseline had begun. It requires a new stable-snapshot formal run; do not mark this defect fixed from
     static testing alone.

### Cleanup and conclusion

The owned database, Oxigraph container, 8012/7879 listeners, temporary backend logs/PID, Agent process
and copied Codex-auth run root were all removed. Final verification found no matching database/container,
no 8012/7879 listeners, and regular `ontology-platform.service`, `:8001/api/health` and `:5173/` healthy.

**BLOCKED. M4 is not unblocked or accepted.** A new Round 4 must use the stable proxy-allowlist snapshot
in a new isolated environment and perform fresh baseline and pinned/non-successor runs before consumer,
query and mutation acceptance can be evaluated.

## Round 4 — 2026-07-27 independent formal acceptance (FAIL)

### Stable handoff and fresh runtime

- Tested the stable M4 snapshot: `run_m4_clarification.py`
  `e96353b965c6a62a4e3fac858b21b073f39cc771a76a89297448fcd36dda12ae`, focused test
  `f5e40326187b9c9eec1bec5467681c1204312fdab360650974144ca4e0c6c312`, and input manifest
  `33c1fcda30232160c4f9536f1f91494d959725711e983589b965375358ac5973`.
- The focused M4 suite reported **11 passed** and Ruff/diff checks passed before the formal run.
- Created a new database `m4_round4_20260727` from `template0`, a dedicated Oxigraph container bound
  only to `127.0.0.1:7879`, upgraded Alembic through `0031_retrieval_label_evidence`, and started an
  isolated backend on `8012` with `canonical_store=rdf`, `product_write_mode=rdf_primary`,
  `read_mode=rdf`, and `legacy_write_blocked=true`. This proves the repaired fresh-migration path and
  the required RDF-primary precondition without using the regular service database.

### Formal baseline result

Ran the baseline launcher without `--prepare-only`, with a new run root, backend port `8012`, and a
600-second bound. The proxy allowlist is behaviorally effective: the real fresh Codex process started,
read the staged inputs, and reached the host API spool gateway. It created its first request,
`openapi_contract_001.json`; the host audit then correctly rejected that request as non-canonical JSON:

```json
{"at":"2026-07-27T03:59:07.458207+00:00","filename":"openapi_contract_001.json","policy":"rejected","reason":"request is not canonical JSON"}
```

The request bytes ended with a newline, while the gateway requires exact compact canonical JSON. Its
SHA-256 before cleanup was
`443bc3677bc3a904767df6cfa2fe9bf3eeb43c99e68e3fd76e49ca4bb0714b73`. The Agent then waited for a
response; it created no clarification request, decision record, Modeling Batch, semantic result, or
consumer evidence. The bounded run was terminated after this deterministic failure. As in Round 3,
interrupting outside the launcher's timeout handler means a final-run audit was not emitted.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (preflight and launch) | Fresh isolated migration/RDF-primary backend and actual bwrap/Codex start passed. Complete final audit is unavailable because the deterministic failed run was interrupted. |
| M4-02 | PASS | The gateway failed closed on the non-canonical request; focused protocol suite has 11 passing tests. The failed Agent serialization is separately recorded as M4-R4-01. |
| M4-03 | BLOCKED | The Agent did not reach a clarification request. |
| M4-04 | FAIL | Baseline cannot progress past its first required platform request, so no current-target model or semantic proof exists. |
| M4-05 | BLOCKED | Variant was not started after the baseline failure. |
| M4-06 | BLOCKED | No applied baseline/variant models or output-identity queries exist. |
| M4-07 | BLOCKED | No explicit unknown/gap result or consumer observation exists. |
| M4-08 | BLOCKED | No formal clarification/decision/Batch/query hash chain exists. |
| M4-09 | BLOCKED | No Project/Ontology/Session, dry-run/apply, Shapes, or invalid-Invocation evidence exists. |
| M4-10 | BLOCKED | No formal reasoning or C -> B -> A query evidence exists. |
| M4-11 | BLOCKED | Consumer was not started because the baseline produced no applied model. |
| M4-12 | BLOCKED | No applied model was available for the planned tester-owned mutation checks. |
| M4-13 | PASS | This round changed only this test-plan record; no M5 or product implementation artifact was touched. |
| M4-14 | PASS (focused M4) | Stable focused M4 suite: 11 passed. Broader M1/M2/M3/generic suites were not rerun in this bounded formal-failure round; their Round-3 results are retained as historical evidence only. |
| M4-15 | PASS | Owned database/container/listeners/run root/backend log and copied auth were removed. `ontology-platform.service` was active; `GET :8001/api/health`, `GET :5173/`, and `git diff --check` passed. |

### Defect

1. **M4-R4-01 — High acceptance blocker: the formal Agent does not serialize the mandatory API-spool
   envelope as canonical JSON.**
   - Reproduction: create the fresh isolated RDF-primary runtime above, then run
     `python3 docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root
     /tmp/m4-round4-baseline --variant baseline --run-tag m4-round4-baseline --backend-port 8012
     --timeout-seconds 600`.
   - Expected: the Agent writes exact compact, sorted canonical JSON bytes accepted by the host gateway,
     then continues through clarification, formal Modeling Batch and semantic acceptance evidence.
   - Actual: the first `GET /openapi.json` envelope contains a trailing newline and is rejected with
     `request is not canonical JSON`; the Agent waits rather than recovering with a valid new request.
   - Evidence: gateway audit timestamp and request SHA-256 above; the gateway's rejection itself is the
     intended fail-closed behavior.
   - Impact: the baseline is unusable and all semantic/modeling, variant, consumer, and mutation
     acceptance cases remain unexecuted. This is an Agent prompt/launcher contract robustness defect,
     not a gateway defect.

### Cleanup and conclusion

Explicit cleanup stopped the isolated `8012` backend and Oxigraph container, dropped
`m4_round4_20260727`, and deleted the exact temporary run root, backend log and PID file. Final checks
found no owned database/container, no `8012`/`7879` listener, and a healthy regular service.

**FAIL.** Proxy propagation and fresh migration are now behaviorally proven, but M4 is not accepted:
the formal baseline Agent cannot issue its first valid platform request. Have the requirement developer
repair the formal Agent/API-spool serialization or recovery contract, then retest this same plan with a
fresh baseline first. Only after it passes should the pinned/non-successor variant, read-only consumer,
and mutation/query cases be run.

## Round 5 — 2026-07-27 independent formal repair retest (FAIL)

### Stable handoff and scope

- Retested the supplied terminal-line-ending repair snapshot. The launcher SHA-256 remained
  `e96353b965c6a62a4e3fac858b21b073f39cc771a76a89297448fcd36dda12ae`; the focused test SHA-256 was
  `3e023f419c5b10ef76fbcdecbd44b9c7089d4ebb8d4b175776eb820a0a55322b`; and the frozen manifest SHA-256
  was `33c1fcda30232160c4f9536f1f91494d959725711e983589b965375358ac5973`.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests -q`
  passed **17** tests; M4 Ruff and `git diff --check` passed.
- Created the new owned `m4_round5_20260727` database from `template0`, dedicated local Oxigraph on
  `127.0.0.1:7879`, upgraded Alembic through `0031_retrieval_label_evidence`, and booted a separate
  `8012` backend. Its canonical-mode response confirmed `rdf`, `rdf_primary`, `rdf`, and
  `legacy_write_blocked=true`. The regular service database was not used.

### Formal baseline facts

The strict non-`--prepare-only` baseline launched a real isolated Codex process with a 600-second
bound. This time the Round-4 API failure is **fixed behaviorally**: after its normal temporary-file
attempt was fail-closed, the Agent's final `/openapi.json` request was forwarded to the isolated platform
with HTTP 200. Gateway evidence recorded request ID `openapi_schema_01`, raw-request SHA-256
`cec9b3f85a3f97357d0a117864ffb6f410d39c1216642c51c202ecb090bfe738`, canonical-request SHA-256
`3274472fd22cb7ab2009ec87409c51cc4cc6551f5fe166bc6a862d7baf778965`, and response SHA-256
`75364795c3c8b0bca50c98fbc5794494a99c9f0ffe766f3385846213e560500c`.

The same live Agent then submitted the first material business clarification, `current_c_target_01`.
It is a serial lifecycle/current-target question, but its final `.json` request ends with a single LF.
The host clarification responder rejected it with `request is not canonical JSON`, never wrote the
matching response, and the Agent waited. Its raw SHA-256 was
`17f32ff43d82952de652b1f2e5c0b1d6771bcd0ce7aac5df8ab06220d210ee1b`; byte inspection ended in
`7d 0a`. This proves the new transport normalization is applied by `m4_api_file_spool_gateway.py`, but
not by `m4_clarification_responder.py`. The failing process was deliberately stopped rather than allowed
to consume the full timeout; because this is outside the launcher's handled timeout path, no final-run
audit was emitted.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (preflight/launch); BLOCKED (complete final audit) | Fresh migration/RDF-primary backend, frozen inputs, bwrap and a real Codex process were proven. The run was interrupted after deterministic transport failure, so its final audit cannot be claimed. |
| M4-02 | FAIL | API LF/CRLF normalization works, but the clarification spool rejects the same allowed terminal-LF transport form. The temporary `.tmp` names were correctly rejected fail-closed; that does not repair the final clarification request. |
| M4-03 | FAIL | The Agent independently reached a first material, serialized lifecycle/current-target clarification, but received no response because of the transport defect. It therefore cannot complete the three required questions. |
| M4-04 | BLOCKED | No answered lifecycle decision, Project/Ontology/Session, Batch, applied model, or baseline semantic query can exist after the first clarification response is unavailable. |
| M4-05 | BLOCKED | The fresh pinned/non-successor run was not started after the baseline transport failure. |
| M4-06 | BLOCKED | No baseline/variant applied models or positive output-identity query observations exist. |
| M4-07 | BLOCKED | The missing-score clarification, explicit gap and consumer observation were not reached. |
| M4-08 | BLOCKED | There is API evidence up to OpenAPI retrieval, but no accepted clarification response, decision, Batch, apply Attempt or query hash chain. |
| M4-09 | BLOCKED | No formal Modeling Batch dry-run/apply, Shapes, invalid-Invocation rejection, validation or reasoning evidence exists. |
| M4-10 | BLOCKED | No formal C -> B -> A reasoning/context-query result exists. |
| M4-11 | BLOCKED | Blind consumer was not started because no model was applied. |
| M4-12 | BLOCKED | No applied model was available for independent remove/sentinel/decoy mutation checks. |
| M4-13 | PASS | This tester changed only this shared test plan; M5 and product/migration implementation files were not edited. |
| M4-14 | PASS (focused M4) | Focused M4 suite: **17 passed**; Ruff and diff check passed. M1/M2/M3 and generic backend suites were not rerun after the formal baseline failed, so previous-round results remain historical only. |
| M4-15 | PASS | The owned database, Oxigraph container, 8012/7879 listeners, Agent/responder/gateway processes, run roots, logs and copied authentication were removed. Regular service was active; 8001 health and 5173 checks passed. |

### Defect

1. **M4-R5-01 — High acceptance blocker: clarification responder lacks the declared terminal-LF/CRLF
   transport normalization.**
   - Reproduction: establish the fresh isolated RDF-primary runtime above and run the strict baseline
     launcher. Allow the Agent to create its first material clarification request after successful
     `GET /openapi.json` forwarding.
   - Expected: the responder accepts exactly one terminal LF or CRLF on an otherwise compact canonical
     clarification envelope, compares/uses the normalized canonical bytes, and creates the matching
     read-only response. Other whitespace or malformed requests remain fail-closed.
   - Actual: `current_c_target_01.json` with otherwise canonical contents plus a final LF was rejected as
     `request is not canonical JSON`; no response was created and the Agent could not continue.
   - Evidence: clarification audit timestamp `2026-07-27T04:09:59.005910+00:00`, request SHA-256 and
     terminal bytes above. The responder's `parse_request` compares `raw != canonical`, while the API
     gateway first calls `strip_transport_line_ending(raw)`.
   - Impact: M4-02 and M4-03 fail and M4-04--M4-12 cannot be evaluated. Round-4's API-spool trailing-LF
     defect is fixed; this is a distinct responder-side transport defect exposed only by the live
     clarification path.

### Cleanup and conclusion

All Round-5 resources were explicitly stopped and deleted; verification found no
`m4_round5_20260727` database, no `ontology-platform-m4-round5-oxigraph` container, no 8012/7879
listener, and no M4 process. `ontology-platform.service` remained active and normal endpoints were
healthy.

**FAIL.** Do not treat the 17 focused tests or successful OpenAPI forwarding as complete M4 acceptance.
Have the requirement developer apply the same strictly bounded terminal-transport normalization to the
clarification responder and test that live path, then rerun this same plan from a fresh baseline before
starting the variant, consumer, mutation and semantic acceptance cases.

## Round 6 — 2026-07-27 independent formal transport retest (FAIL)

### Stable handoff and fresh preconditions

- Tested the shared `m4_transport` snapshot: launcher SHA-256
  `e96353b965c6a62a4e3fac858b21b073f39cc771a76a89297448fcd36dda12ae`, transport-helper SHA-256
  `b02e16cf2c21c10e9a1c77145e53f90a4dd2d1abf0315b6d5aa13d04c2d8d06b`, focused-test SHA-256
  `588ae4c1f6eca4f234a3e5e1108832afcceae03ebd64e742a5a21b0c5f444d76`, and frozen manifest SHA-256
  `33c1fcda30232160c4f9536f1f91494d959725711e983589b965375358ac5973`.
- Focused M4 tests passed **25**; M4 Ruff and `git diff --check` passed.
- Created `m4_round6_20260727` from `template0`, a separate local Oxigraph container, then upgraded
  through Alembic `0031_retrieval_label_evidence` and booted a dedicated 8012 backend. Its canonical
  mode was `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`, and
  `legacy_write_blocked=true`.

### Live transport closure proved

The strict baseline started a real isolated Codex process with a 600-second bound. Both prior
terminal-transport failures are now **behaviorally fixed**:

- `openapi01` forwarded `GET /openapi.json` with HTTP 200. Its raw request SHA-256 was
  `d8195b23c48707c82a9595eb88df58c091aa88f6dfa333479772ab13683204bc`, canonical request SHA-256
  `38e6c445c2339698f4a5c30ba60b5f06ff278cd6c10ac3031b71b34601907c0d`, and response SHA-256
  `235817ded6666b374296258462d8bf246616d03f4dc48b2579efdf210ca287f4`.
- The first material serial clarification `ctarget01` received the correct `answered` response:
  `B invokes C through C's Latest published Version.` Its raw request SHA-256 was
  `53e2f03bfdf56bc9ccd9cf335c13df8b2b55ba01b0e3a5e05c83af57dd564777`, canonical request SHA-256
  `f1a86b183aae673dbfa6ebcf6f58626005fd6670455502875080c76b7e6cc85d`, and response SHA-256
  `22652f0c53fa5534b99604ec0416712f156fcee35be01be4c02e51ab52f1880c`.

After the closure, the Agent successfully created a fresh Project, Ontology, Build Session and retrieved
modeling context, all through forwarded public API requests (HTTP 201/200). It then needed the ontology
lease before it could submit the required immutable Batch.

### Formal blocker and bounded retry

The Agent submitted `lease01.json`; the host API gateway correctly rejected it because ID `lease01` is
seven characters while the strict spool contract requires at least eight. After one natural bounded
retry window, the Agent emitted `lease02.json`, again seven characters, and received the same rejection.
Neither request could produce a response, so no lease, Batch, validation, reasoning, query, variant or
consumer run was possible. The run was then terminated rather than consuming its remaining timeout.

Evidence:

- `lease01.json` SHA-256: `7b8d324c36d3d6b31cf12ed26ae403de410d194338c79ef0a1a570cb9b62683f`
  — rejected at `2026-07-27T04:16:45.441237+00:00`.
- `lease02.json` SHA-256: `c14720e00c3e4c79aa3ec05af3ae5a94635cd08ef10a8679cbffb7bd99a1793c`
  — rejected at `2026-07-27T04:18:10.521651+00:00`.
- Both audits state `request filename is not strict ID.json`. The gateway fail-closed result is correct.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (preflight/launch); BLOCKED (complete final audit) | Fresh isolated migration/RDF-primary backend, frozen inputs, bwrap and real Codex execution passed. The deterministic lease failure was interrupted, so no final-run audit exists. |
| M4-02 | PASS | Shared transport helper now accepts permitted terminal LF/CRLF forms on both API and clarification paths; actual OpenAPI and clarification request/response audits prove it. Gateway correctly rejected the malformed API filenames. |
| M4-03 | PASS (first question); BLOCKED (complete set) | The Agent independently asked one material lifecycle/current-target question and received the correct answer. It could not proceed to identity and missing-score questions after lease failure. |
| M4-04 | BLOCKED | The baseline lifecycle answer is recorded, but no lease, Batch/apply or semantic current-target observation exists. |
| M4-05 | BLOCKED | Pinned/non-successor variant was not started after baseline lease failure. |
| M4-06 | BLOCKED | No baseline/variant applied model or output-identity proof exists. |
| M4-07 | BLOCKED | Missing-score uncertain response, explicit gap and consumer observation were not reached. |
| M4-08 | BLOCKED | API and first clarification receipts/decision entries exist, but no complete Batch/apply/query chain exists. |
| M4-09 | BLOCKED | Project/Ontology/Session and context exist, but no lease, dry-run/apply, Shapes, invalid-Invocation or validation proof exists. |
| M4-10 | BLOCKED | No formal reasoning/context-query proof exists. |
| M4-11 | BLOCKED | Consumer was not started because no model was applied. |
| M4-12 | BLOCKED | No applied model was available for independent mutation checks. |
| M4-13 | PASS | This tester edited only this shared test plan; no M5, product, migration or main delivery-record file was changed. |
| M4-14 | PASS (focused M4) | Focused M4 suite: **25 passed**. Broader M1/M2/M3/generic suites were not rerun after the formal failure; earlier results remain historical only. |
| M4-15 | PASS | Owned database, Oxigraph, 8012/7879 listeners, Agent/responder/gateway processes and run roots were removed. Regular service, 8001 health, 5173 and diff check passed. |

### Defect

1. **M4-R6-01 — High acceptance blocker: the formal Agent emits API-spool IDs below the gateway's
   required minimum and cannot recover with a legal replacement.**
   - Reproduction: run a fresh formal baseline through successful OpenAPI, clarification, Project,
     Ontology, Build Session and modeling-context calls; observe its lease acquisition request.
   - Expected: the Agent writes an ID and filename matching the gateway's strict ID rule, receives the
     lease response, and proceeds to immutable dry-run/apply. If an input is rejected, it retries using
     a distinct legal ID.
   - Actual: it wrote `lease01.json` and then `lease02.json`; both IDs are seven characters, so both
     were rejected before HTTP forwarding and the Agent waited for unavailable response files.
   - Evidence: exact audit timestamps and request hashes above. Project/Ontology/Session requests with
     longer IDs were forwarded successfully, isolating the failure to short lease IDs.
   - Impact: formal M4 cannot obtain a lease or execute Batch/semantic/variant/consumer/mutation gates.
     The gateway's fail-closed behavior is correct; the visible Agent/API-spool contract or Agent
     recovery behavior must be corrected.

### Cleanup and conclusion

All Round-6 resources were explicitly terminated and deleted. Final verification found no owned
database/container/listener or M4 child process; regular `ontology-platform.service`, 8001 health and
5173 remained healthy.

**FAIL.** The terminal transport repairs are now proven on both spools, but M4 remains unaccepted due
to the lease-request filename minimum-length blocker. Have the requirement developer make the legal API
spool ID rule actionable to the formal Agent and cover its recovery path, then rerun this same plan from
a fresh baseline before any variant/consumer/mutation acceptance work.

## Round 7 — 2026-07-27 independent formal lifecycle retest (FAIL)

### Stable handoff and fresh runtime

- Tested launcher SHA-256 `9422f8d57ecc1e44df8c4fd6a1548aa4d357e3ca74ce7f8a3e0d8b9c4a3b138e`, shared
  transport-helper SHA-256 `b02e16cf2c21c10e9a1c77145e53f90a4dd2d1abf0315b6d5aa13d04c2d8d06b`, focused-test
  SHA-256 `51625c4a7168aef35c15917fc024d5d0ebbc6c377ced59b4a7e1e30b861be629`, and manifest SHA-256
  `f27caa24b09296d421411ebb272ee99c22f1bd4683974ce8bc6cd7a044ea1ea9`.
- Focused M4 suite passed **33**; M4 Ruff and `git diff --check` passed.
- A fresh `m4_round7_20260727` database, dedicated Oxigraph and isolated 8012 backend upgraded and
  booted successfully in RDF-primary mode (`rdf`, `rdf_primary`, `rdf`, legacy writes blocked).

### Formal baseline evidence

The strict non-`--prepare-only` baseline ran for its configured 600-second bound and emitted a final
audit with exit code `124` and status `INCONCLUSIVE`. Unlike prior rounds, it made substantial real
progress before the bounded timeout:

- `/openapi.json` forwarded with HTTP 200, raw-request SHA-256
  `28f9e388486c5160092aac1b40efcd28469e3bc9a8227941bef8d2a27725353f` and response SHA-256
  `9c5e7d940fc945e703fbdc85567ab4f85b492e8ce7125c744a6b1dc792b2c583`.
- All three required business questions were asked one at a time and received the expected statuses:
  current C target `answered`, output continuity `answered`, and missing-score `uncertain`. The final
  audit inventories all three request/response SHA pairs and the clarification audit SHA-256
  `2372e07d1b093a48ccedd11961849b566ddc68d3c03444dde5a1edc09c3e3d73`.
- Fresh Project, Ontology, Build Session, lease acquire/renew and modeling context calls succeeded.
  `acquire_lease_round7` forwarded with HTTP 200; no short-ID lease rejection occurred.
- Initial dry-run correctly failed HTTP 422 because it included `lease_token`; the Agent recorded the
  feedback and resubmitted without it. It then completed validated dry-runs and atomic applies for
  schema, resources, and relationship assertions. The final audit retains all immutable request/response
  hashes; its API-audit SHA-256 is
  `50e3c15544ebc4073e2acb3666ff0699492baac31e99dca1386d147178493fee`.

### Tester-owned baseline semantic observation

Before cleanup, the tester issued a read-only public project-scoped SPARQL query. Response SHA-256 was
`8aafccb3e8438136331c5ca32bccfa803c4a566a5d3753763a2d17eca0477eb4`.
It positively observed:

- `Workflow B` invokes `C Latest published Version`, while `C Current Draft` is separate;
- the Latest Version has `quality_rating:number`;
- `quality_rating:number` has the positive `succeeds field` relation to `quality_score:number`;
- `Workflow B` has the named `Missing-score behavior unresolved` Business Gap.

The same response explicitly reported missing current reasoning/rule results. No Agent runtime record,
Agent validation run, reasoning run, semantic query result, handoff checkpoint, or completed Build
Session was created before timeout.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | PASS (isolation/launch); FAIL (completion audit) | Frozen staging, actual isolated Codex launch and host-path audit passed, but final status is `INCONCLUSIVE` and `runtime_record_sha256` is null after timeout. |
| M4-02 | PASS | Terminal transport and strict API filenames worked on final requests; `.tmp` intermediate files were correctly fail-closed. |
| M4-03 | PASS | All three material questions were serial, business-level and non-prescriptive; two were answered and missing-score was uncertain. |
| M4-04 | PASS | Tester SPARQL positively observed B -> C Latest published Version and its `quality_rating:number` contract, distinct from Current Draft. |
| M4-05 | BLOCKED | Pinned/non-successor variant was not started because baseline did not complete. |
| M4-06 | PASS (baseline); BLOCKED (variant) | Positive baseline `succeeds field` evidence exists; no non-successor positive discontinuity run exists. |
| M4-07 | BLOCKED | A named unresolved Business Gap is modeled, but no completed Agent query/record or blind consumer proves preservation of unknown. |
| M4-08 | BLOCKED | Clarification and Batch/audit chains exist, but no runtime record or completed query chain binds the full result. |
| M4-09 | BLOCKED | Fresh Session, lease, dry-run correction and atomic applies are proven; Shapes, invalid-Invocation rejection and formal validation are absent. |
| M4-10 | FAIL | Tester query reports missing reasoning/rule results; no C -> B -> A reasoning or retained M3 semantic proof exists. |
| M4-11 | BLOCKED | Blind consumer was not started because baseline did not complete. |
| M4-12 | BLOCKED | Variant and tester-owned mutation checks were not run. |
| M4-13 | PASS | This tester modified only this shared plan; no product, migration, M5 or delivery-record implementation was edited. |
| M4-14 | PASS (focused M4) | Focused M4: **33 passed**. Broader M1/M2/M3/generic suites were not rerun after this timeout. |
| M4-15 | PASS | All owned database/container/listeners/run roots and copied credentials were removed; regular service, 8001 health, 5173 and diff check passed. |

### Defect

1. **M4-R7-01 — High acceptance blocker: the formal Agent cannot complete the required M4 lifecycle
   within the bounded run and leaves no final runtime/semantic evidence.**
   - Reproduction: run the fresh formal baseline with the required 600-second bound after successful
     OpenAPI, clarification, lease and Batch access.
   - Expected: within the formal run, complete the modeled baseline with validation, reasoning, governed
     query evidence, checkpoint, runtime record and completion status, so the variant/consumer/mutation
     gates can begin.
   - Actual: the Agent spent the remaining budget incrementally probing Modeling Batch payload fields.
     It applied schema/resources/relations, but exited 124 while still progressing, produced no runtime
     record, and did not issue validation/reasoning/query/completion operations.
   - Evidence: final audit status `INCONCLUSIVE`, transcript SHA-256
     `9a5153911e009ebc7c6f2e54cebce4e9551a3236af464b5bc57c99aba4f9f37b`, null runtime record hash, and
     tester SPARQL warnings that reasoning/rule results are missing.
   - Impact: the baseline is only partially proved. Variant, blind consumer, mutation independence,
     reasoning and complete traceability cannot be accepted.

### Cleanup and conclusion

All Round-7 resources and tester-owned read-only response files were removed after evidence capture.
No Round-7 database/container/8012/7879 listener remained; regular `ontology-platform.service` and its
8001/5173 endpoints stayed healthy.

**FAIL.** Round 7 fixes and proves transport, serial clarification, legal lease IDs, formal Batch
dry-run/apply, and baseline asserted semantic facts, but it does not complete the M4 acceptance lifecycle.
Have the requirement developer make the public Batch contract/action plan sufficiently executable for
the Agent to reach validation, reasoning, governed query and final record inside the bounded run; then
retest fresh baseline before the pinned variant, blind consumer and mutation cases.

## Round 8 — 2026-07-27 independent formal lifecycle retest (FAIL)

### Stable handoff and fresh runtime

- Verified launcher SHA-256 `d382c24c4de65dd085bc3b954a7e3a1679be2bbd8fd551a21575458ef58b8faf`,
  transport helper SHA-256 `b02e16cf2c21c10e9a1c77145e53f90a4dd2d1abf0315b6d5aa13d04c2d8d06b`,
  focused-test SHA-256 `0d7fa93a7eacf94cc101b750856ba351a405209548ac3b6881c96728be559113`, and
  input-manifest SHA-256 `039315734096c947535b74f84d822a28f4e3eeec2b121237231e561ccf3317f3`.
- Focused M4 suite: **46 passed in 0.50s**. M4 Ruff and `git diff --check` passed.
- Created a new `m4_round8_20260727` database from `template0`, a dedicated Oxigraph on `7879`, and
  an isolated backend on `8012`; migrations reached `0031_retrieval_label_evidence`. Health and
  canonical mode were good: `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`,
  and legacy writes blocked.
- Ran the required non-prepare baseline with `--timeout-seconds 600` in
  `/tmp/m4-round8-baseline`. The pinned/non-successor variant, blind consumer and mutation checks were
  intentionally not started after this baseline's terminal acceptance failure.

### Formal baseline evidence

- The real Agent independently completed all three serialized business clarifications. The host
  clarification audit records raw/canonical/response hashes for `c-target-version` (`answered`),
  `score-semantics` (`answered`), and `missing-score-behavior` (`uncertain`); its audit SHA-256 is
  `3c9149aa60054acad240fc58435436bee66b1e8de2501f01cf2780959a843a36`.
- Project, Ontology, Build Session, modeling/workspace context and lease acquisition all forwarded
  successfully. Schema dry-run and atomic apply both returned HTTP 200 with a `create_shape` command.
- The explicit invalid-Shape negative case was correctly fail-closed through the public Batch API:
  `invalid-shape-dryrun-m4-001` returned HTTP 200 and `attempt_status=validation_failed`, with a
  blocking `shacl_violation` whose report says `conforms=false`; it did not apply.
- The Agent recovered from two rejected instance candidates, reached `entities-dryrun-m4-003` with
  `attempt_status=validated`, then atomically applied the valid entities and the continuity relation.
  Runtime receipts retain both rejected candidates, valid dry-run/apply, continuity dry-run/apply,
  Shape apply and invalid Shape dry-run.
- `validation-m4-001` returned HTTP 200, `status=succeeded`, `conforms=true`. Persistent graph set
  `7aad57b4-63ed-5542-852f-b35691ef6ecb` received successful reasoning and rule runs. The Agent
  correctly rejected its first two governed queries because they carried the missing-rule-pointer
  warning, created a current empty rule pointer, and accepted `query-m4-003` only after the warning-free
  positive response. Runtime receipts and the decision log bind each response to its host audit.
- At approximately 596 seconds the Agent successfully created `checkpoint-m4-001` (HTTP 200,
  expected revision 1). The completion request and response files were generated at the timeout edge.
  Subsequent gateway evidence shows `complete-m4-001` did in fact forward at `05:18:47.259751Z` and
  returned HTTP 200 with `body.status=completed`, but this arrived too late for the launcher's final
  audit/Agent terminal bookkeeping.

### Terminal audit failure

The mandatory host final audit is authoritative for acceptance. It reports:

- `status=INCONCLUSIVE`, `runtime_terminal_status=INCONCLUSIVE`, and `agent_exit_code=124`;
- `completion_gate_errors=[]`;
- API-audit SHA-256 `5753164b004ed2fb7fdd136ed3095598f389af97cccf4f8986205f7df418282b`;
- runtime-record SHA-256 `bed327a716d70082acab726f11402c036d453c1f6fe3586153e563fcba2fbe64` and
  decision-log SHA-256 `7bfe9293c0488ccab1627f8e4b71854ac08cac6c3ece97619feede78fd0e3bfd`.

The runtime record has receipts through `checkpoint`, but no `complete` receipt or post-completion
final GET receipt. Therefore the late HTTP completion cannot replace the required launcher terminal
status `COMPLETED` nor establish the complete host-owned final audit chain.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | FAIL | Fresh isolated RDF-primary baseline and host-path audit launched correctly, but the final audit is `INCONCLUSIVE` with exit 124, not required `COMPLETED`. |
| M4-02 | PASS | Real API and clarification spool flows completed under the strict transport contract; host audits contain immutable raw/canonical/response hashes. |
| M4-03 | PASS | All three material questions were independently asked one at a time; two were answered and missing-score correctly remained uncertain. |
| M4-04 | PASS | Successful governed semantic query accepted only after a current rule pointer removed warnings; the decision log records positive C-version/continuity/gap observation. |
| M4-05 | BLOCKED | Pinned/non-successor variant was not started after baseline terminal-audit failure. |
| M4-06 | PASS (baseline); BLOCKED (variant) | Baseline asserted/queried continuity path completed; no required non-successor variant evidence exists. |
| M4-07 | BLOCKED | The uncertain missing-score gap is retained in the completed baseline query path, but blind consumer proof was not run. |
| M4-08 | FAIL | Receipts bind all completed responses through checkpoint, but not completion/final GET; the terminal audit is not completed. |
| M4-09 | PASS (through checkpoint); FAIL (terminal) | Lease, Shape apply, invalid Shape rejection, valid applies and validation all passed, but final completion audit failed. |
| M4-10 | PASS | Successful validation (`conforms=true`), persistent reasoning, current rule pointer and warning-free governed query are all host-audited. |
| M4-11 | BLOCKED | Blind consumer was not started because the prerequisite baseline final audit failed. |
| M4-12 | BLOCKED | Pinned variant and independent mutation-rejection checks were not run after the baseline failure. |
| M4-13 | PASS | This tester changed only this shared test-plan file; no product, migration, M5 or main delivery-record file was edited. |
| M4-14 | PASS (focused M4) | Focused M4: **46 passed**. Broader M1/M2/M3/generic suites were not rerun. |
| M4-15 | PASS | All Round-8 owned resources were removed after evidence capture; regular service health and workspace checks passed. |

### Defect

1. **M4-R8-01 — High acceptance blocker: launcher timeout races the final completion path and records
   `INCONCLUSIVE` despite the late HTTP completion.**
   - Reproduction: execute the fresh non-prepare baseline with its mandatory 600-second bound.
   - Expected: the Agent completes the checkpoint, completion, final GET and all final receipts before
     the bound; the host final audit has `status=COMPLETED`, terminal status `COMPLETED`, exit code 0,
     and receipt-bound completion evidence.
   - Actual: checkpoint succeeded near 596 seconds. The completion request was generated at the bound
     and its HTTP 200 response was forwarded after the launcher had already classified the Agent as exit
     124/`INCONCLUSIVE`; runtime has no completion or final-GET receipt.
   - Evidence: final audit fields and SHA-256 values above; gateway entry
     `complete-m4-001` at `05:18:47.259751Z`, HTTP 200, versus final terminal
     `INCONCLUSIVE`/124.
   - Impact: the formal baseline does not satisfy the required terminal acceptance contract. Variant,
     blind-consumer and mutation gates must remain unexecuted.

### Cleanup and conclusion

All Round-8 database, Oxigraph container, isolated 8012/7879 listeners, Agent/responder/gateway
processes and run roots were explicitly removed after evidence capture. The regular
`ontology-platform.service`, `8001` health endpoint and `5173` frontend remained healthy; `git diff
--check` remained clean.

**FAIL.** Round 8 materially proves the full modeling, Shape, invalid SHACL, validation, persistent
reasoning and warning-free governed-query sequence, and even obtains a late HTTP completion. It still
fails the mandatory host-owned terminal contract because the launcher records exit 124 and
`INCONCLUSIVE`, without completion/final-GET receipts. Have the requirement developer eliminate the
end-of-budget completion race (or make the formal run complete materially earlier), then rerun this same
plan from a fresh baseline before any variant, consumer or mutation acceptance work.

## Round 9 — 2026-07-27 independent 660-second bounded-baseline retest (FAIL)

### Scope and fresh environment

- Round 8's 600-second failure remains historical and unchanged. Round 9 used the same frozen runner,
  manifest, prompt, command contract and model configuration, changing only the formal command bound to
  `--timeout-seconds 660`.
- Re-verified launcher SHA-256 `d382c24c4de65dd085bc3b954a7e3a1679be2bbd8fd551a21575458ef58b8faf`,
  transport SHA-256 `b02e16cf2c21c10e9a1c77145e53f90a4dd2d1abf0315b6d5aa13d04c2d8d06b`,
  focused-test SHA-256 `0d7fa93a7eacf94cc101b750856ba351a405209548ac3b6881c96728be559113`,
  and frozen input-manifest SHA-256
  `039315734096c947535b74f84d822a28f4e3eeec2b121237231e561ccf3317f3`.
- Focused M4 suite: **46 passed in 0.41s**; M4 Ruff and `git diff --check` passed.
- Created fresh `m4_round9_20260727`, dedicated Oxigraph `7879`, and isolated `8012` backend upgraded
  to head. The authenticated canonical-mode check was HTTP 200 with `rdf_primary`, RDF reads and legacy
  writes blocked. (An initial 401 preflight was corrected before any Agent launch by using the runner's
  exact key parser and matching isolated bootstrap key; it is not a formal-run attempt.)

### Receipt timeline and 600-second gate

Relative times below are measured from formal runner start `2026-07-27T05:25:04Z`; gateway and
clarification audit timestamps retain the precise fractional-second evidence.

| Relative time | Receipt / result |
| --- | --- |
| +31.438s, +155.990s, +195.559s | The three serialized clarifications: current C target `answered`, output continuity `answered`, missing-score `uncertain`. |
| +175.770s | Lease acquisition HTTP 200. |
| +271.668s / +282.895s | Schema dry-run validated and Shape-containing atomic apply HTTP 200. A prior schema dry-run at +244.285s returned HTTP 500, then recovered. |
| +294.374s | Invalid Shape dry-run HTTP 200, `attempt_status=validation_failed`, blocking `shacl_violation`. |
| +424.382s | Extra `operational-schema-dry-001` payload probe HTTP 422. |
| +487.677s | Extra `operational-schema-apply-001` Shape-containing modeling apply HTTP 200. |
| +550.390s | Valid instance atomic apply HTTP 200. |
| +560.629s | Validation HTTP 200, `status=succeeded`, `conforms=true`. |
| +570.397s | Persistent graph-set reasoning HTTP 200, `status=succeeded`. |
| +583.628s | First governed query HTTP 200 but carried `derived_result_missing`; it is not the required warning-free positive query. |
| +597.216s | Rule run HTTP 200; it established the pointer but was still a non-terminal semantic operation. |
| **+607.289s** | Second governed query HTTP 200 and warning-free, but it is beyond the 600-second core gate. |
| **+614.132s / +628.741s** | Pre-checkpoint session GET and checkpoint HTTP 200, both after the core gate and not allowed tail-only actions. |

The hard rule required all clarifications, lease, Shape apply, invalid dry-run, validation, reasoning,
positive warning-free governed query and checkpoint by 600 seconds. It further allowed only completion
forwarding, final GET, runtime and final-audit convergence from 600 to 660 seconds. Round 9 violates
both parts: the positive query and checkpoint were not complete by 600 seconds, and the post-600 query,
session GET and checkpoint were forbidden non-terminal work. The tester stopped the runner immediately
after observing this violation; no complete/final GET/final host audit was permitted or produced.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | FAIL | Fresh RDF-primary isolated baseline launched, but cannot satisfy the required <=600-second core gate or terminal completion contract. |
| M4-02 | PASS | Host API/clarification audits retained request method/path/status and hashes; Agent recovered from the pre-600 canonical-JSON rejection. |
| M4-03 | PASS | All three material serial clarifications completed at +31.438s, +155.990s and +195.559s. |
| M4-04 | BLOCKED | Baseline semantic data was created, but the required warning-free governed-query acceptance occurred after the hard core deadline. |
| M4-05 | BLOCKED | Pinned/non-successor variant was not started after baseline hard-gate failure. |
| M4-06 | BLOCKED | No accepted baseline terminal run or required variant comparison exists. |
| M4-07 | BLOCKED | The uncertain gap was captured, but blind consumer validation was not started. |
| M4-08 | FAIL | Runtime contains receipts through initial governed query but no checkpoint/complete/final-GET final chain; checkpoint occurred only after the forbidden tail boundary. |
| M4-09 | FAIL | Shape, invalid SHACL, valid apply and validation succeeded, but required lifecycle completion timing failed. |
| M4-10 | FAIL | Reasoning completed by +570.397s, but the only warning-free governed query was +607.289s and thus cannot satisfy the 600-second acceptance gate. |
| M4-11 | BLOCKED | Blind consumer was not started. |
| M4-12 | BLOCKED | Variant and independent mutation-rejection checks were not started. |
| M4-13 | PASS | This tester changed only this existing test plan; no product, migration, M5 or main delivery-record file was edited. |
| M4-14 | PASS (focused M4) | Focused M4: **46 passed**; broader suites were not rerun. |
| M4-15 | PASS | Round-9 database, Oxigraph, 8012/7879 listeners, Agent/gateway/responder and run roots were removed after evidence capture; normal service health remained good. |

### Defect

1. **M4-R9-01 — High acceptance blocker: the 660-second extension does not preserve the required
   600-second core lifecycle boundary.**
   - Reproduction: use the frozen M4 inputs and a fresh isolated RDF-primary backend, execute the
     formal baseline with `--timeout-seconds 660`, and audit each receipt relative to runner start.
   - Expected: complete all core receipts, including warning-free positive governed query and checkpoint,
     no later than 600 seconds; reserve 600–660 solely for completion/final-GET/runtime/final-audit
     convergence.
   - Actual: repeated schema/payload exploration consumed the budget. The first governed query had a
     missing-derived-pointer warning at +583.628s; the warning-free query arrived at +607.289s. The
     Agent then made a session GET and checkpoint at +614.132s/+628.741s, all prohibited tail work.
   - Evidence: timeline above from the immutable API gateway audit. No completion, final GET or final
     host audit existed because the tester stopped the runner after the first hard-gate violation.
   - Impact: changing only the outer timeout does not make M4 acceptable. Pinned variant, consumer and
     mutation tests must remain unrun.

### Cleanup and conclusion

All Round-9 resources were removed after evidence capture. The regular service stayed active; `8001`
health and `5173` checks passed, and `git diff --check` passed.

**FAIL.** The 660-second experiment proves most individual core operations can complete, but it fails
the explicit timing contract and performs forbidden post-600 semantic work. Have the requirement
developer make the Agent's bounded action plan deterministic enough to complete all core receipts by
600 seconds, then rerun this same plan fresh before any variant, consumer or mutation acceptance work.

## Round 10 — 2026-07-27 independent principal-sequence baseline retest (FAIL)

### Stable snapshot and fresh runtime

- Verified the new reviewed snapshot: runner SHA-256
  `914dffa1210db10684d9df9fd81a3da1cd88affccf5dcc3d03d756c4447d4a9e`, transport SHA-256
  `b02e16cf2c21c10e9a1c77145e53f90a4dd2d1abf0315b6d5aa13d04c2d8d06b`, focused test SHA-256
  `974e111e5ee9683b45866bcf99e0635f8b1b0e29760543f4d19df13b2f7faf8c`, and frozen manifest
  SHA-256 `3ddef9e5c5fad13179b19f157fc875fe9b83ee396eadb8b4275a2a97834d44b8`.
- Focused M4 suite: **64 passed in 0.62s**. M4 Ruff and `git diff --check` passed.
- Created fresh `m4_round10_20260727`, dedicated Oxigraph `7879`, and isolated `8012` backend migrated
  to head. Canonical-mode authentication returned HTTP 200 with RDF-primary writes, RDF reads and legacy
  writes blocked. The API credential was parsed through the runner's own `load_api_key` logic and used
  as the fresh backend bootstrap key before Agent launch.

### Host receipt timeline

Relative times use the host final audit's `runner_started_at=2026-07-27T06:08:06.449069Z`.

| Relative time | Receipt / result |
| --- | --- |
| +27.228s, +64.828s, +90.633s | Three serialized clarifications: published C target `answered`, score-contract continuity `answered`, missing-score behavior `uncertain`. |
| +116.433s | OpenAPI GET HTTP 200. No modeling/schema/rule/operation/query probe preceded the principal resource anchor. |
| +207.725s to +210.260s | Principal Project HTTP 201, then Ontology, Build Session, contexts and lease all succeeded. |
| +258.858s | `principal_schema_dry_run` HTTP 200, `attempt_status=validated`. |
| +262.750s | `shape_apply` HTTP 200, `attempt_status=applied`, same `client_batch_id=principal-schema-v1`, same items SHA-256 `99d23929fb6a585845e7257891e98e7f747f270f727b6637ad5ba14e784485b0`. |
| +333.640s | `invalid_shape_dry_run` HTTP 200, `attempt_status=validation_failed`; expected blocking SHACL result. |
| +334.315s | The single permitted `valid_instance_dry_run` HTTP 200 returned `attempt_status=validation_failed`; Agent correctly wrote terminal `BLOCKED` and exited 0. |

The principal API flow has no rejected request and no extra schema/modeling/rule/query probe before its
anchor. Its Batch chain is exactly principal schema dry-run -> same Shape apply -> invalid dry-run -> one
valid instance dry-run. The latter instance request uses only `create_entity` and `create_relation`, as
required. It did not apply valid instances or enter validation/reasoning/query/checkpoint/complete after
the known blocking result.

### Blocking valid-instance evidence

- Batch `17ddb9db-53ed-4baf-8b89-1724bb942eab`, attempt
  `d3a49c38-3063-4ace-a0fc-d946dcdfb85b`, returned one blocking finding:
  `code=shacl_violation`, `severity=error`, `scope=item`, `retryable=false`, `path=[]`, message
  `Canonical write does not conform to SHACL shapes`, and `report_summary.conforms=false`.
- The blocking finding covers `entity_a`, `entity_b`, `entity_c`, `relation_a_publishes_b`,
  `relation_b_gap`, `relation_b_invokes_c`, `relation_b_targets_latest`, `relation_c_has_draft`,
  `relation_c_has_earlier`, and `relation_c_has_latest`. The remaining findings are non-blocking
  `missing_evidence` warnings.
- Command summary: 19 items total — nine `create_entity` (`entity_a`, `entity_b`, `entity_c`, draft,
  earlier/latest C versions, score, rating and gap) and ten `create_relation` items. No forbidden Batch
  command kind is present.
- Runtime terminal reason is exactly `Valid instance dry-run did not validate.` The host final audit is
  `status=BLOCKED`, `runtime_terminal_status=BLOCKED`, `agent_exit_code=0`; it contains no completion,
  final-GET or `DEVELOPMENT_READY` state.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | FAIL | Fresh isolated baseline was correctly launched but terminal host audit is `BLOCKED`, not `COMPLETED`. |
| M4-02 | PASS | All host receipts use the fixed transport contract; no request was rejected. |
| M4-03 | PASS | All three required serial clarifications completed before principal creation. |
| M4-04 | BLOCKED | No valid applied instance or accepted governed query exists after valid dry-run failure. |
| M4-05 | BLOCKED | Pinned/non-successor variant was not started because baseline failed. |
| M4-06 | BLOCKED | No accepted baseline terminal model or variant exists. |
| M4-07 | BLOCKED | Uncertain missing-score answer exists, but no blind-consumer test was eligible. |
| M4-08 | FAIL | Receipt evidence binds work through the blocked valid dry-run only; no completion/final GET chain exists. |
| M4-09 | FAIL | Principal schema/Shape and intentional invalid SHACL proof pass, but the purported valid instance dry-run also violates SHACL. |
| M4-10 | BLOCKED | Validation, persistent reasoning and governed query were correctly not attempted after the blocking valid dry-run. |
| M4-11 | BLOCKED | Blind consumer was not started. |
| M4-12 | BLOCKED | Variant and mutation checks were not started. |
| M4-13 | PASS | This tester changed only this existing test plan; no implementation, migration, M5 or main record file was edited. |
| M4-14 | PASS (focused M4) | Focused M4: **64 passed**; broader suites were not rerun. |
| M4-15 | PASS | Round-10 owned database, Oxigraph, 8012/7879 listeners and run roots were removed; regular service checks passed. |

### Defect

1. **M4-R10-01 — High acceptance blocker: the fixed principal valid-instance payload does not conform
   to the Shape graph that its same principal schema batch applies.**
   - Reproduction: run the frozen Round-10 baseline against a fresh RDF-primary backend; follow the
     direct principal schema dry/apply, intentional invalid dry-run, then `valid_instance_dry_run`.
   - Expected: the intentional invalid instance fails SHACL; the one designated valid instance Batch
     validates and can be atomically applied.
   - Actual: both dry-runs return `validation_failed`. The purported valid batch has the blocking SHACL
     finding documented above, so the Agent correctly terminates `BLOCKED` rather than fabricating a
     valid apply.
   - Evidence: valid dry-run request SHA-256
     `ca7573861db49c90e5cbfb20db75c9fc025c7d55a5349e866c6de53649c0fca2`, response SHA-256
     `8bd2b35ba6942c36eb4cb0a3934144650e984f74139f307f93b88424d48b25f2`, and host final audit
     SHA-256 `927a9c23786f99b69f6c052cec650f0a579c21fc71cfcdde873e2f8e2d437a31`.
   - Impact: the valid apply, semantic lifecycle, terminal completion and all variant/consumer/mutation
     gates remain ineligible.

### Cleanup and conclusion

All Round-10 resources were removed after evidence capture. The normal service remained active;
`8001` health, `5173` and `git diff --check` passed.

**FAIL.** Round 10 proves the reviewed host sequence eliminates the prior exploratory and timing
problems, but it exposes a deterministic Shape/payload incompatibility at the first valid-instance gate.
Have the requirement developer correct the fixed principal valid-instance contract, then rerun this same
plan from a fresh baseline before the variant, consumer or mutation stages.

## Round 11 — 2026-07-27 independent offline one-time ABox-correction repair retest (PASS for repair scope)

### Stable snapshot, scope, and review boundary

- Independently verified the reviewed stable files before testing: runner
  `c03f63e16efd1b7abfaa526013d77a2bb19d496cf9ed8bd06f1cd6a0e49dce34`, focused tests
  `80bdefcc154950bbfe010861691646b54ab6455be1dae6a47a8f36f23cf554f6`, Agent prompt
  `39425830a2797d35ca5b7c4068004d3a12d20c2d12287c1ea421c6f06b1b5afc`, command contract
  `07a30a41b2b821e893588220bc5fd872a09597f5d32a61c427056d761273171e`, input manifest
  `e697e1268cce44e776bf1307f0f5591415ad2dfa6cbf25914bb6a8094dc22607`, and API gateway
  `e1bcd2c90c29d56c29c5c3ca97b49b2507a02a9d75563084432d7efa20599323`.
- Reviewed the prompt/command contract and host final-gate implementation. The repair permits exactly
  one correction only after the first valid-instance dry-run is a 2xx `validation_failed` whose every
  blocking finding is SHACL with non-empty fingerprint and attributed client item IDs. It requires a new
  batch and idempotency identity, unchanged item-ID set/command kinds/dependency topology, changes only
  finding-attributed items, correction dry-run validation, and immediate exact correction apply. Schema
  is frozen after the principal Shape-containing apply.
- This was an offline retest of that repair only. Per the test assignment, no live Agent was run, no
  isolated service/database/container was started, no product code was changed, and no M5/M5-P0 path was
  touched. Pre-existing unrelated migration, requirement, delivery-record and M5 worktree changes were
  preserved. This round changes only this append-only test-plan record.

### Commands and actual results

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **80 passed** in 0.48s.
- `uv run --directory backend pytest -vv ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests -k correction` —
  **16 passed, 64 deselected** in 0.71s. This includes the qualified positive correction path and
  rejection of changed non-finding items, added/removed/renamed IDs, changed command kind or dependency,
  no-op corrections, missing/mismatched fingerprint evidence, reused batch/idempotency identity, original
  apply, second correction, post-correction schema operation, and correction after a directly valid
  candidate.
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` —
  **13 passed**.
- `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/test_scenario_m2.py` —
  **5 passed**.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m3/tests` —
  **27 passed** in 0.62s.
- `uv run --directory backend pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py` —
  **69 passed** in 6.92s (five pre-existing deprecation warnings).
- `RUN_POSTGRES_MIGRATION_TESTS=1 uv run --directory backend pytest tests/test_migrations.py -rs` —
  **4 passed** in 3.60s (three deprecation warnings). This was run because the current worktree includes
  the independent migration repair; it did not modify M4 product scope.
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m4` —
  **All checks passed**. `git diff --check` — **passed**.
- `systemctl --user --no-pager --full status ontology-platform.service`; `curl --fail --silent --show-error http://127.0.0.1:8001/api/health`; `curl --fail --silent --show-error http://127.0.0.1:5173/` —
  service **active**, backend returned `{"status":"ok"}`, and frontend returned the preview HTML. No
  owned `8012` or `7879` listener existed.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | BLOCKED (not executed) | No fresh isolated Agent baseline or terminal host audit was run by design of this offline-only repair retest. |
| M4-02 | PASS (offline) | The full focused M4 suite passes; host final-audit fixtures bind correction request/response hashes and reject malformed correction evidence. |
| M4-03 | PASS (retained regression) | Full focused suite passes; no live question flow was run in this repair-only round. |
| M4-04 | BLOCKED (not executed) | No accepted live baseline/current-target query was run. |
| M4-05 | BLOCKED (not executed) | No pinned-version fresh variant was run. |
| M4-06 | BLOCKED (not executed) | No successor/non-successor applied-model comparison was run. |
| M4-07 | BLOCKED (not executed) | No live explicit-gap plus blind-consumer observation was run. |
| M4-08 | PASS (offline correction chain) | Positive fixture completes only when runtime and canonical decision-log correction evidence bind original/correction hashes, fingerprints, batch IDs and changed-item before/after hashes; negative cases fail closed. Full live answer-to-model chain remains unexecuted. |
| M4-09 | PASS (offline correction gate); BLOCKED (live) | Positive fixture accepts first SHACL-attributed candidate failure -> correction dry-run validated -> exact atomic apply; static and negative tests reject original apply, a second correction and post-Shape schema Batch. A real Modeling Batch remains unexecuted. |
| M4-10 | PASS (regression); BLOCKED (live) | The required generic semantic suites pass (validation, reasoning and context-query included), but no new formal M4 reasoning/query run was started. |
| M4-11 | BLOCKED (not executed) | No live read-only consumer was run. |
| M4-12 | BLOCKED (not executed) | No tester-owned applied-model remove/sentinel/decoy mutation run was performed. |
| M4-13 | PASS | Scope remained scenario/test-plan-only; no M5/M5-P0 or product implementation edit was made by this tester. |
| M4-14 | PASS | M4 **80**, M1 **13**, M2 **5**, M3 **27**, focused generic backend **69**, and migration **4** all passed. |
| M4-15 | PASS | Ruff and diff checks passed; the regular service and both health endpoints were healthy, and no isolated runtime was created. |

### Defects and residual risks

No defect was found in the reviewed offline one-time ABox-correction gate. The positive and negative
tests demonstrate that the gate keeps TBox/Shape frozen and fails closed for an ineligible or expanded
correction.

The residual acceptance risk is material: this round deliberately did not execute a real fresh Agent,
isolated RDF-primary backend, actual SHACL finding, correction Batch or semantic/consumer/mutation
queries. Therefore it does not supersede Round 10's live baseline blocker or establish M4 acceptance.
After the responsible developer integrates this repair with a valid fresh principal payload, run a new
fresh baseline first; only after its terminal audit is completed should pinned/non-successor variants,
blind-consumer and mutation cases be run.

### Conclusion

**PASS for the stable offline one-time ABox-correction repair scope.** The repair contract and host final
gate are covered by focused positive/negative tests and the required adjacent regressions pass. **M4 as
a whole remains not accepted** because the live cases intentionally left BLOCKED here, and Round 10's
fresh-baseline Shape/payload failure remains historical until a new successful live baseline supersedes
it. Recommend the requirement developer proceed to a fresh formal baseline after the principal valid
payload is available, then request independent retest.

## Round 12 — 2026-07-27 independent live autonomous-correction baseline (FAIL)

### Fresh isolated environment and frozen snapshot

- Used the same reviewed stable M4 snapshot as Round 11: runner
  `c03f63e16efd1b7abfaa526013d77a2bb19d496cf9ed8bd06f1cd6a0e49dce34`, focused tests
  `80bdefcc154950bbfe010861691646b54ab6455be1dae6a47a8f36f23cf554f6`, Agent prompt
  `39425830a2797d35ca5b7c4068004d3a12d20c2d12287c1ea421c6f06b1b5afc`, command contract
  `07a30a41b2b821e893588220bc5fd872a09597f5d32a61c427056d761273171e`, input manifest
  `e697e1268cce44e776bf1307f0f5591415ad2dfa6cbf25914bb6a8094dc22607`, and API gateway
  `e1bcd2c90c29d56c29c5c3ca97b49b2507a02a9d75563084432d7efa20599323`.
- Created owned PostgreSQL database `m4_r12_20260727_1557` from `template0`, started owned container
  `ontology-platform-m4-r12-oxigraph` on `127.0.0.1:7879`, and migrated the owned database to head
  using only its `DATABASE_URL`, `OXIGRAPH_URL` and `rdf_primary` settings. Migration reached
  `0031_retrieval_label_evidence`.
- Started an owned backend only on `127.0.0.1:8012` with RDF canonical store, RDF-primary product
  writes, RDF reads and legacy writes blocked. Its authenticated canonical-mode response was HTTP 200
  with `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf` and
  `legacy_write_blocked=true` before the Agent launch. The bootstrap key was obtained through the
  runner's existing key parser and is not recorded here.
- Ran exactly one baseline and supplied no fixed ABox payload or semantic intervention:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round12-baseline --variant baseline --run-tag m4-round12-baseline --backend-port 8012 --timeout-seconds 660`.

### Authoritative host evidence and timeline

The launcher returned Agent exit code `0`, but the host-owned final audit is **`BLOCKED`**, not
`COMPLETED`; it is authoritative. Its relevant hashes are: final runtime record
`c7d9f4026d2f023b2c7ddea0471c95a5422d28a885bc72ff0ef44bae66cc7c6e`, decision log
`a4a641b7eab73dc8577eb8f597ed2f7d633e863978260e3a8fb00db375b38460`, API audit
`c88dc50921db9a0d421ea976d12c041bedb0fc1ec5afa9273fe38e3c9e6dab0d`, clarification audit
`640e6754697a0feb90f94f2859c11844953c8029e63568230c37c2bd9f6c0d03`, and transcript
`9019d822e9e8150dfcb5ac00e396f66640f54ab5bda10c3f73a5abfc8f89dc8f`.
The transcript did not contain a forbidden host path.

Relative to the final audit's `runner_started_at=2026-07-27T07:58:53.711847Z`:

| Relative time | Host-observed event |
| --- | --- |
| +46.045s / +74.399s / +111.400s | Three serial clarification responses: current target `answered`, contract continuity `answered`, missing-score behavior `uncertain`. The response bytes remain host-owned and are not reproduced here. |
| +46.636s | `GET /openapi.json` — HTTP 200. |
| +218.964s to +219.677s | Fresh Project (201), Ontology (201), Build Session (201), modeling/workspace context (200), and ontology lease (200). |
| +220.454s | `principal_schema_dry_run` Modeling Batch, including Shapes — HTTP **500**. Request SHA-256 `70bfb41fc624458afe537e9368b1065b483980e49bd07cf1333fbf91f778bae1`; response SHA-256 `492f7e98a6eae573b7da4e26f126136e0d2849e68df56349cf1d785079a89924`. |

No invalid-instance proof, candidate ABox dry-run, correction dry-run/apply, validation, reasoning,
governed query, checkpoint, completion or final GET followed. This is a strict stop, not a skipped
success. The Agent correctly set `BLOCKED` after the failed closed-sequence operation; its runtime did
not provide a terminal reason string.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | FAIL | Fresh isolated baseline launched successfully, but authoritative host final audit is `BLOCKED`, not `COMPLETED`. |
| M4-02 | PASS | API and clarification transport completed with host hashes; no request was rejected and the transcript host-path scan passed. |
| M4-03 | PASS | All three material questions completed serially before platform modeling; two were answered and the missing-score branch remained uncertain. |
| M4-04 | BLOCKED | Principal schema dry-run failed before an applied instance or governed current-target observation. |
| M4-05 | BLOCKED (not started) | Per handoff, no pinned/non-successor variant was run after the baseline did not complete. |
| M4-06 | BLOCKED (not started) | No applied baseline or variant model exists. |
| M4-07 | BLOCKED (not started) | No applied model or blind-consumer result exists. |
| M4-08 | FAIL | The chain reaches clarification, setup and principal dry-run request/response hashes only; no Batch acceptance/apply through final receipt chain exists. |
| M4-09 | FAIL | The first principal Shape-containing dry-run returned HTTP 500 rather than a deterministic validation result, so neither the intentional invalid-instance proof nor the candidate/correction gate is eligible. |
| M4-10 | BLOCKED | Validation, reasoning and governed query were not reached. |
| M4-11 | BLOCKED (not started) | No consumer was started by instruction. |
| M4-12 | BLOCKED (not started) | No mutation checks were started by instruction. |
| M4-13 | PASS | This tester changed only this append-only test plan; no product, M5/M5-P0, requirements, design or delivery-record file was changed. |
| M4-14 | PASS (retained) | Round 11 against these unchanged hashes passed M4 80, M1 13, M2 5, M3 27, generic backend 69 and migration 4. No new regression suite was run after the failed live baseline. |
| M4-15 | PASS | All owned Round-12 resources were stopped/removed after evidence capture; no 8012/7879 listener remained, and regular `ontology-platform.service`, `:8001/api/health` and `:5173/` were healthy. |

### Defect

1. **M4-R12-01 — High acceptance blocker: principal schema dry-run returns an unhandled RDF/Turtle parse failure.**
   - Reproduction: create the fresh RDF-primary environment above and execute the exact frozen
     Round-12 baseline command without supplying an ABox payload.
   - Expected: the principal Shape-containing schema dry-run returns its governed validated or
     validation-failed Modeling Batch response, allowing the closed sequence to continue or terminate
     deterministically. The ABox candidate/correction decision is only evaluated after that stage.
   - Actual: the API gateway received HTTP 500 at `principal-schema-dry`; the host response was the
     plain `Internal Server Error` body. Isolated backend evidence traces the failure to
     `semantic_canonical_write._validate_candidate` calling RDFLib Turtle parsing for the compiled
     schema delta, which raises `rdflib.plugins.parsers.notation3.BadSyntax`.
   - Evidence: request/response SHA-256 values and API-audit SHA-256 above; backend stack terminates at
     `inserted.parse(..., format="turtle")`. No hidden answer, credential or raw payload is needed to
     reproduce the defect.
   - Impact: the live run cannot reach the first candidate ABox dry-run, so the newly tested one-time
     correction branch is not behaviorally exercised despite its Round-11 offline PASS.

### Cleanup and conclusion

The owned database, Oxigraph container, 8012 backend, Agent/responder/gateway processes and
`/tmp/m4-round12-baseline` were removed after evidence capture. No variant, consumer or mutation process
was started. Regular health checks remained successful.

**FAIL.** The autonomous Agent independently completed the required serial clarification stage and
reached the principal schema path, but an unhandled platform 500 blocks the closed sequence before any
candidate ABox or one-time correction can be tested live. Have the requirement developer repair the
generic schema-delta RDF serialization/validation failure, add a regression test at that layer, and then
rerun one new fresh baseline before any variant, consumer or mutation acceptance work.

## Round 13 — 2026-07-27 independent Round-12 compiler-repair gate (PASS)

### Stable repair and constrained scope

- Independently verified the repair handoff hashes: `semantic_command_compiler.py`
  `0be7a5f375ec504dde48fea62c17348357a10c4378e3aa881da696db4443b361`,
  `test_modeling_batches_service.py`
  `c5073ce0d0858cc6aedb7265eadceec5fb1aefb4e0890e1b54e90cd9dca3b5ce`, and
  `test_semantic_command_compiler_r12.py`
  `fad0851d1f60f0d73283a18360ca1735a28cb2798c6a3f0dc0b68f6398ce78dc`.
  The M4 runner, test, prompt, command-contract, manifest and gateway hashes remain the stable Round-11
  values.
- Reviewed the appended design exception and delivery handoff. The permitted generic repair is limited
  to deterministic valid blank-node labels for arbitrary accepted Shape/property IDs, recognized bare-XSD
  datatype normalization, and a representative Modeling Batch regression. It adds no M4 answer payload,
  Shape relaxation, retry, special route or M5 scope.

### Commands and actual results

- `uv run --directory backend pytest -vv tests/test_semantic_command_compiler_r12.py tests/test_semantic_command_compiler_stage2.py tests/test_modeling_batches_service.py` —
  **85 passed** in 3.20s. The repair gate
  `test_urn_schema_ids_and_bare_string_datatype_validate_in_one_principal_dry_run` passed: the
  representative URN-shaped Class/Property/Shape plus bare `string` principal schema dry-run is
  `mode=dry_run`, `attempt_status=validated`, and has no blocking finding.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **80 passed** in 0.51s; M1/M2/M3 scenario suites — **13/5/27 passed**; semantic validation/reasoning/
  Context Query API regressions — **18 passed** in 4.05s (three existing deprecation warnings).
- `uv run --directory backend ruff check app/services/semantic_command_compiler.py tests/test_semantic_command_compiler_r12.py tests/test_modeling_batches_service.py ../docs/evaluation-scenarios/dify-workflow-impact-m4` —
  **All checks passed**. `git diff --check`, regular service status, `:8001/api/health`, and `:5173/`
  checks all passed; no `8012`/`7879` listener was present before the conditional live run.
- Known non-M4 local full-suite failure independently reproduced with
  `uv run --directory backend pytest -q tests/test_mcp_auth.py::test_mcp_startup_requires_environment_key` —
  **1 failed**: it did not raise after the test removed only process `ONTOLOGY_MCP_API_KEY`, because
  `Settings()` reloads the configured key from `backend/.env`. This is outside the R12 compiler/M4 scope
  and was not changed.

### Case results and conclusion

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-09 / R12 repair gate | PASS | The prior generic principal-schema 500 is prevented for the representative public URN/bare-datatype command set; it validates rather than becoming a changed validation failure. |
| M4-02/03 | PASS (regression) | Full M4 transport and clarification unit suite remains 80/80. |
| M4-13 | PASS | Only this test plan was edited by this tester; no product, delivery-record, requirements, M5 or M5-P0 file was modified. |
| M4-14 | PASS | Compiler/Modeling Batch 85, M4 80, M1 13, M2 5, M3 27, and focused validation/reasoning/query 18 all passed. |
| MCP/auth full-suite environment check | KNOWN FAIL, non-blocking to this gate | The single named test fails because `.env` reload defeats its process-environment deletion; no MCP/auth change was made or requested. |

**PASS.** The explicit repair gate is independently satisfied, so Round 14 may run one fresh autonomous
baseline. This does not itself prove the full M4 runtime or correction path; the live host audit remains
authoritative.

## Round 14 — 2026-07-27 independent autonomous baseline after compiler repair (FAIL)

### Fresh runtime and authoritative evidence

- Created owned database `m4_r14_20260727_1630` from `template0`, owned Oxigraph container
  `ontology-platform-m4-r14-oxigraph` on `127.0.0.1:7879`, and a fresh authenticated backend on
  `127.0.0.1:8012`. Alembic reached `0031_retrieval_label_evidence`; before launch the authenticated
  canonical-mode response confirmed `canonical_store=rdf`, `product_write_mode=rdf_primary`,
  `read_mode=rdf`, and `legacy_write_blocked=true`.
- Ran exactly one unsupplemented autonomous baseline with the frozen M4 runner:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round14-baseline --variant baseline --run-tag m4-round14-baseline --backend-port 8012 --timeout-seconds 660`.
  No fixed schema/ABox payload, retry, semantic intervention, variant, consumer or mutation check was
  supplied or started.
- The authoritative host final audit is **`BLOCKED`** with Agent exit code `0`. Its relevant hashes are:
  API audit `70318dba70157e3cd058129e4d8f1e47d360873fe52747a8a81b7661553e541d`, clarification audit
  `09c901147e9df4767d7280267ed62cb8e7ce752ab18c5445c2eb0711055e8388`, runtime record
  `4422f8d107decf1efe55ac8b49018b6b00c5314c9f2e27972f78d0053a8c1b32`, decision log
  `0d395e77588a7e44354183e4ce3498f24c220ee4cf6c67e948324f9773e62d86`, and transcript
  `2326038f1265e86378280c0e661da7012a22660b10fa10e4f2a59a4e006650fb`. The transcript host-path scan
  passed. Hidden answers and credentials are not reproduced.

### Host timeline

Times are relative to `runner_started_at=2026-07-27T08:27:26.693184Z`.

| Relative time | Host-observed event |
| --- | --- |
| +34.002s | Current-C-target clarification received an `answered` response. |
| +34.502s | `GET /openapi.json` — HTTP 200. |
| +95.161s to +107.653s | Fresh Project, Ontology, Build Session, modeling/workspace context and lease all succeeded. |
| +128.665s | A quality-output-continuity clarification was `not_eligible`; no third missing-score clarification was completed. |
| +198.990s | Principal Shape-containing schema dry-run — HTTP 200, `attempt_status=validated` (only non-blocking Evidence warnings). |
| +214.037s | Exact principal schema atomic apply — HTTP 200, `attempt_status=applied`, `batch_status=applied`. |
| +226.600s | Intentional invalid-instance dry-run — HTTP 200, expected blocking `shacl_violation`. |
| +278.936s | First candidate valid-instance dry-run — HTTP **500**. Request SHA-256 `1d505a0b6e3d9b0fb270069b0485ffda8bd9592e9873a76596d565a9c231dd99`; response SHA-256 `87db7a1ea644276063fa53cea558e3fae4fe2a7d9a22ebbbd984eb45eb3200cd`. |

The Agent correctly stopped under the closed sequence. Its terminal reason is: `The first valid-instance
dry-run returned HTTP 500 with a non-JSON Internal Server Error; the closed sequence forbids retry or
probing.` No correction, valid-instance apply, validation, reasoning, governed query, checkpoint,
completion or final GET occurred.

### Case results

| ID | Result | Evidence / conclusion |
| --- | --- | --- |
| M4-01 | FAIL | Fresh isolated baseline launched, but host final audit is `BLOCKED`, not `COMPLETED`. |
| M4-02 | PASS (fail-closed) | Host spool retained audited rejections for two non-strict temporary filenames and did not forward them; the accepted transport receipts are hash-bound. |
| M4-03 | FAIL | Only the lifecycle clarification was accepted; output continuity was `not_eligible` and the missing-score question was never completed. Thus not all material ambiguities were serially clarified. |
| M4-04 | BLOCKED | No governed current-target query was reached. |
| M4-05 | BLOCKED (not started) | No pinned/non-successor variant was started by instruction. |
| M4-06 | BLOCKED (not started) | No applied baseline instance/variant comparison exists. |
| M4-07 | BLOCKED (not started) | No consumer/gap conclusion exists. |
| M4-08 | FAIL | The trace is complete only through the first candidate dry-run; no correction/apply through final receipt chain exists. |
| M4-09 | FAIL | Round-12 principal schema 500 is fixed in this real run, and intentional invalid SHACL is correctly rejected, but the candidate dry-run itself is an unhandled 500 rather than a governed validation result. |
| M4-10 | BLOCKED | Validation, reasoning and governed query were not reached after the candidate-dry-run failure. |
| M4-11 | BLOCKED (not started) | No blind consumer was started. |
| M4-12 | BLOCKED (not started) | No mutation test was started. |
| M4-13 | PASS | This tester changed only this test-plan append; no product code, requirements, design, delivery record, M5 or M5-P0 surface was modified. |
| M4-14 | PASS (Round 13 retained) | The compiler/Modeling Batch and focused scenario regressions passed before this fresh baseline; no new broad suite was run after this terminal live failure. |
| M4-15 | PASS | All owned Round-14 resources were removed after evidence capture; no 8012/7879 listener remained and regular 8001/5173 health passed. |

### Defect

1. **M4-R14-01 — High acceptance blocker: candidate ABox SHACL validation raises an unhandled
   `InConstraintComponent` load error.**
   - Reproduction: use the fresh RDF-primary environment and exact Round-14 autonomous command above;
     let the Agent construct the principal schema and first candidate instance Batch without injecting a
     payload.
   - Expected: the candidate dry-run returns a governed Modeling Batch result—`validated` or a structured
     `validation_failed` with SHACL findings—so that the existing one-time finding-driven correction gate
     can either apply or terminate deterministically.
   - Actual: after the principal schema validated/applied and the intentional invalid case returned its
     expected SHACL finding, the candidate dry-run returns HTTP 500/non-JSON `Internal Server Error`.
     Isolated backend evidence is `pyshacl.errors.ConstraintLoadError: InConstraintComponent must have at
     most one sh:in predicate`, raised while `SemanticCanonicalWriteService._validate_candidate` invokes
     `pyshacl_validate`.
   - Evidence: request/response/API-audit hashes above and the isolated backend traceback. The result is
     a compiler/platform Shape-constraint correctness failure in a real generic Modeling Batch path, not
     an Agent transport or fixed-payload issue.
   - Impact: the one-time ABox correction branch is still not behaviorally reached; no valid instance,
     semantic acceptance, variant, consumer or mutation evidence may be claimed.

2. **M4-R14-02 — High acceptance blocker: the fresh Agent did not complete all required material
   clarifications before modeling.**
   - Reproduction: the same fresh Round-14 baseline without an injected model or answer payload.
   - Expected: independently ask and receive/record one serial clarification for lifecycle, output
     continuity and missing-score behavior, preserving the latter as explicit uncertain, before formal
     modeling.
   - Actual: lifecycle was answered, the quality-output-continuity request was `not_eligible`, and no
     missing-score request was completed. The Agent nonetheless progressed to schema and instance work.
   - Evidence: clarification audit SHA-256 above; host response statuses/timestamps in the Round-14
     timeline. No hidden-answer content is required to verify the missing accepted request chain.
   - Impact: even after the platform candidate-validation 500 is repaired, the baseline cannot establish
     M4's proactive-clarification acceptance gate without a fresh run that independently completes all
     three material gaps.

### Cleanup and conclusion

The owned backend was stopped, the owned database and Oxigraph container were removed, and the owned
run root was moved to the system recycle bin after the hashes/traceback above were retained. No owned
8012/7879 listener remained; regular service health passed.

**FAIL.** Round 13 fixes and behaviorally proves the original principal-schema blank-node/datatype
failure, but Round 14 exposes a distinct generic Shape-constraint compilation/merge defect at candidate
ABox validation. Have the requirement developer fix this `sh:in` multiplicity error and add a regression
that validates an Agent-equivalent multi-Shape candidate before requesting another fresh baseline. Do not
run variant, consumer or mutation acceptance until a baseline reaches authoritative `COMPLETED`.

## Round-14 `sh:in` repair gate — planned

Before another live baseline:

1. Compiler assertions must prove every present `enum_values` collection produces exactly one `sh:in`
   triple whose object is one complete RDF list, with deterministic Turtle-valid and constraint-distinct
   list-node identities. No direct repeated `sh:in` literal triples are permitted.
2. A focused Modeling Batch service regression must dry-run and apply an Agent-equivalent schema with
   multiple Shapes and at least two enum-bearing constraints. A subsequent allowed-value ABox dry-run
   must return `mode=dry_run`, `attempt_status=validated` and no blocking finding.
3. The same applied schema must return a governed `validation_failed` result with a blocking SHACL
   finding for a disallowed enum value. An HTTP 500, non-JSON response, `ConstraintLoadError`, or silently
   accepted disallowed value fails the gate.
4. Required compiler/Modeling Batch, M4 and preceding scenario regressions, Ruff and diff checks must
   pass. Only after an independent offline PASS may one fresh unsupplemented baseline run. No fixed ABox,
   Shape relaxation or live retry is allowed; variant, consumer and mutation remain gated on a
   `COMPLETED` baseline.
5. Replay the exact Round-14 output-continuity request through the responder and require `answered`, not
   `not_eligible`. A genuinely combined lifecycle-plus-output question must remain `not_eligible`.
6. Prompt and host-audit tests must require all three ambiguities explicitly listed in the visible
   business brief to have one eligible, consumed, hash-bound response before the principal schema
   request. A `not_eligible` response, duplicate decision, or missing listed ambiguity must fail; the
   Agent must revise the unresolved question or stop `BLOCKED`.

## Round-12 repair gate — planned

Before a new live baseline:

1. A focused Modeling Batch service regression must submit one principal schema candidate containing
   URN-shaped class, property and Shape IDs plus a bare `string` datatype. The dry-run must return a
   governed `mode=dry_run`, `attempt_status=validated` response with no blocking finding and must not
   raise RDFLib `BadSyntax` or HTTP 500. A `validation_failed` result does not unblock M4 and fails this
   repair gate.
2. Compiler assertions must prove the Shape property-node term is a valid deterministic RDF blank-node
   label, two distinct Shape/constraint identities do not merge, and the recognized bare `string`
   datatype becomes the XSD string IRI. Existing `xsd:*` and arbitrary absolute datatype IRIs must remain
   unchanged.
3. Required backend and M4 focused regressions, Ruff and diff checks must pass. Because backend behavior
   changes, the repository-required full backend suite, service restart and health checks remain closure
   gates; the repair handoff may use focused checks before independent retest.
4. Only after independent offline PASS may one fresh baseline run. It must receive no fixed ABox or
   semantic intervention and must reach the autonomous candidate/correction path. Variant, blind
   consumer and mutation cases remain gated on a `COMPLETED` baseline final audit.

## Round 15 — 2026-07-27 independent offline multi-enum and clarification repair gate (PASS)

### Stable scope and gate evidence

- Reviewed the current narrow repair handoff: each `enum_values` collection is one deterministic RDF
  list behind one `sh:in`; the service regression applies multi-enum Shapes, validates an allowed ABox
  and returns structured SHACL rejection for a disallowed value. The clarification responder accepts the
  exact Round-14 output-continuity question, keeps genuinely combined questions fail-closed, and the M4
  contract/tests require all three visible ambiguities to have eligible, consumed, hash-bound responses
  before principal schema submission.
- Stable scenario hashes before this round were runner
  `7399e8121e1babc53207a0ac0b8ae0876a4cd32682d18d3e3473ca922c3b035c`, M4 tests
  `890068a4828f523bc7dddf8ae64e46d65590a6ea6b10d7b38ab8494e2f73e359`, Agent prompt
  `b428b9a23c29ef42bd5cfa0c70610715c07403a63f4a526b43af1953df3a4de7`, and manifest
  `d1482134037c6f95928e53556680085293ea3d29c0513cff40374c53d74bc0e1`.

### Commands and actual results

- `uv run --directory backend pytest -vv tests/test_modeling_batches_service.py tests/test_semantic_command_compiler_r12.py tests/test_semantic_command_compiler_stage2.py` —
  **87 passed** in 3.42s. This includes the multi-enum applied-schema test proving allowed ABox
  `validated` and disallowed value governed `validation_failed`/`shacl_violation` without a 500.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **86 passed** in 0.53s; M1/M2/M3 — **13/5/27 passed**; focused validation/reasoning/Context Query —
  **18 passed**; isolated migration checks — **4 passed**.
- Ruff over the changed compiler/tests and M4 scenario, manifest JSON parsing, and `git diff --check` —
  **passed**. The repository-required `systemctl --user restart ontology-platform.service` completed;
  service became active and `:8001/api/health` plus `:5173/` succeeded. No `8012`/`7879` listener was
  present before live setup.
- Known full-suite environment failure was independently reproduced:
  `uv run --directory backend pytest -q tests/test_mcp_auth.py::test_mcp_startup_requires_environment_key` —
  **1 failed** because `Settings()` reloads the configured key from `backend/.env` after the test removes
  only its process environment variable. It is unrelated to M4 and not changed here.

### Conclusion

**PASS.** The Round-14 repair gate passes independently. The previous platform `sh:in` 500 and the
clarification-recognition/completeness regressions are covered offline, so exactly one fresh unsupplemented
Round-16 baseline is eligible. No M4 acceptance result is claimed from this offline gate alone.

## Round-16 resource-ID integrity repair gate — planned

Before another live baseline:

1. The frozen Agent prompt/command contract must require returned Project, Ontology and Build Session IDs
   to be persisted immediately and every scoped path to be rebuilt from those persisted values just
   before atomic request publication.
2. The contract must require Bash helper scratch variables to be `local` and a pre-publication equality
   assertion between the scoped path ID and the corresponding runtime-record ID. A local mismatch may be
   corrected before publication but must never be forwarded as an API attempt.
3. A focused regression must freeze these instructions and the updated manifest source hash. Existing
   M4, M1–M3, compiler/Modeling Batch, semantic, migration, Ruff and diff gates must remain green.
4. Only after independent offline PASS may exactly one new fresh baseline run without a fixed schema or
   ABox. The host audit must show the lease path uses the exact ID returned by Build Session creation.
   Variant, consumer and mutation remain gated on a `COMPLETED` baseline.

## Round 16 — 2026-07-27 one fresh autonomous baseline (FAIL)

### Preconditions and execution

- Fresh owned PostgreSQL database `m4_r16_20260727_1700` (created from `template0`) and fresh owned
  Oxigraph container `ontology-platform-m4-r16-oxigraph` were provisioned on port `7879`. Alembic
  migrations completed through `0031_retrieval_label_evidence`; the isolated `8012` backend reported
  `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf` and
  `legacy_write_blocked=true`. Its process environment independently confirmed that same fresh database
  and RDF settings.
- Ran exactly once, with no fixed schema/ABox, no answer injection and no retry:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round16-baseline --variant baseline --run-tag m4-round16-baseline --backend-port 8012 --timeout-seconds 660`.
  The runner started at `2026-07-27T09:02:19.147615+00:00` and ended `BLOCKED` with agent exit code 0.

### Actual result and evidence

| Case | Result | Evidence |
| --- | --- | --- |
| Three serial material clarifications | PASS | Host audit recorded lifecycle `answered` at 09:02:44Z, output-continuity `answered` at 09:03:01Z, and missing-score `uncertain` at 09:03:18Z. All three consumption receipts exist; no hidden-answer content is recorded here. |
| Project, ontology and Build Session setup | PASS | Public API returned 201 for project, ontology and Build Session creation; modeling/workspace context returned 200. |
| Ontology lease before principal schema | FAIL | The request was `POST /api/build-sessions/52cf03a29d0b053061f7007048b1e8a86a37d57e873cfe7723602ce8b3743f2c/ontology-leases/76792554-9d51-4ab8-8f91-5c8c6067a2ff:acquire` and returned 404 `build_session_not_found`. The actual freshly created Build Session ID was `6e501ed2-ff0f-4d8f-a76c-aa17919eca95`; the wrong path segment is the workspace-context response SHA prefix. A post-run read-only `GET /api/build-sessions/6e501ed2-ff0f-4d8f-a76c-aa17919eca95` returned HTTP 200, confirming the created session remained visible. |
| Principal schema, ABox dry-run/correction, apply and semantic acceptance | BLOCKED | The agent stopped before submitting any Modeling Batch. |
| Variant, blind consumer and mutation | NOT EXECUTED | Explicitly gated on a `COMPLETED` baseline and not started. |

The host final audit is authoritative: status/runtime terminal status `BLOCKED`, no completion-gate
errors, transcript host-path check false. Hashes: API audit
`e2fddd15872fa8aca2740934c3dbb870b831192f5a0c97887af8449229395735`, clarification audit
`8c4dee0ac41598def1a42dd3f19495232d990bd92c10b1e4343ca1acef338a57`, runtime record
`a43541042d04dfd73702a015fcc08353dae7a32485f33c12e2acd0c509658226`, decision log
`73b4081a0b54b7c872edba8c858b0543521e85059643a334afbaf7dce61de490`, transcript
`a440188e37e568da6f25806800d2b1ed06569a72d4faacd564217553a9ecae45`.

### Defect

1. **M4-R16-01 — High acceptance blocker: Agent execution helper overwrites the Build Session ID before
   lease acquisition.**
   - Reproduction: run the exact fresh Round-16 baseline command above; do not inject any model or ABox.
   - Expected: acquire the lease through the public path using the Build Session ID returned by the 201
     create-session response, then continue to principal schema submission.
   - Actual: the Agent Bash helper `record(){ ... s=$(sha256sum response)... }` does not declare `s`
     local, overwriting outer `s=session_id`. Lease acquisition consequently uses the workspace-context
     response SHA prefix (`52cf...`) rather than the created session (`6e501...`) and receives 404. The
     agent correctly stops `BLOCKED`, but M4 cannot reach its modeling/correction acceptance path.
   - Evidence: exact host gateway paths/statuses above, fresh-session response ID, successful read-only
     GET of that ID, fresh-database process configuration, and final-audit hashes. This is an Agent
     execution/prompt robustness defect, not a missing platform session or a recurrence of the Round-14
     compiler/SHACL failure.

### Cleanup and conclusion

After the parent agent's incident inspection, the isolated backend was stopped and the owned database,
Oxigraph container and run root were removed (the run root was moved to the system recycle bin). No
`8012`/`7879` listener remained. The regular `ontology-platform.service` stayed active and the regular
`:8001/api/health` plus `:5173/` checks passed. No further live requests, retries, variants, consumer or
mutation tests were run.

**FAIL.** Round 15 remains PASS and Round 16 independently proves all three clarification outcomes, but
the baseline is terminally blocked before a Modeling Batch. Have the requirement developer correct the
Agent helper variable scope and add a regression that preserves the returned Build Session ID across
receipt hashing; then request a new independent baseline. Do not claim overall M4 acceptance.

## Round 17 — 2026-07-27 independent resource-ID offline gate (PASS)

### Scope, frozen inputs and evidence

- Independently reviewed the Agent-visible prompt and command contract. Both require immediate atomic
  persistence of returned Project/Ontology/Build Session IDs; just-in-time record reads for every scoped
  path; function-local Bash scratch variables; equality assertions before spool publication; and
  fail-closed rebuild/`BLOCKED` behavior. The covered scoped paths include child creation, context,
  lease, Modeling Batch, pre/final Build Session GET, checkpoint and complete.
- Frozen source hashes: runner `fff0fc406c0b11f350ec83f950726b16386e9c0c072e7b7ace5dd9fa0e426b74`, M4 tests
  `c306b8e218f3f399029cff397c3c85c28e8788ba09a7d2ff2c4f3384e37c46f3`, Agent prompt
  `205317f072979babcdc2f3b1c76f8137f440cf17ba9035e715f0c229225f9b6b`, platform contract
  `dfdb112ca977bcaf0da69396206bd1860271e41cd460c607a165ae703247ca48`, scenario contract
  `63628f18667d5558b1a1d5615f84e42cc9406687ac9639301d6cabcae31c40d6`, manifest
  `a71c13b7ae360e04c79a5f147cc0aa9a2500ed3d570274ab9737fc3468185aa4`, and gateway
  `e1bcd2c90c29d56c29c5c3ca97b49b2507a02a9d75563084432d7efa20599323`.

### Commands and actual results

- Static prompt/contract assertion for the complete scoped-ID rules — **passed**.
- `uv run --directory backend pytest -vv tests/test_modeling_batches_service.py tests/test_semantic_command_compiler_r12.py tests/test_semantic_command_compiler_stage2.py` — **87 passed**.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` — **88 passed**, including the Agent-visible ID-integrity and manifest-hash regressions.
- M1/M2/M3 — **13/5/27 passed**; focused semantic validation/reasoning/context query — **18 passed**; PostgreSQL migration checks — **4 passed**.
- Ruff over changed compiler/tests and M4 scenario, manifest parsing, and `git diff --check` — **passed**.
  No backend implementation changed after the prior restart, so no restart was required; the regular
  service was active and `:8001/api/health` plus `:5173/` succeeded. No `8012`/`7879` listener existed
  before isolated setup.

### Conclusion

**PASS.** The resource-ID instructions, frozen manifest and focused regressions are independently
verified. Exactly one new unsupplemented Round-18 baseline is eligible; it must compare the host-owned
create-session response body ID with the lease path ID and must stop after any terminal result.

## Round 18 — 2026-07-27 one fresh autonomous baseline (FAIL)

### Preconditions and execution

- Created fresh owned PostgreSQL database `m4_r18_20260727_1718` from `template0` and fresh owned
  Oxigraph container `ontology-platform-m4-r18-oxigraph` on `7879`; migrated through
  `0031_retrieval_label_evidence`. The isolated `8012` backend reported RDF canonical mode
  (`rdf`/`rdf_primary`/`rdf`, legacy writes blocked).
- Executed exactly once with no fixed schema/ABox, no injected clarification response, and no retry:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round18-baseline --variant baseline --run-tag m4-round18-baseline --backend-port 8012 --timeout-seconds 660`.
  Started at `2026-07-27T09:15:58.015895+00:00`; final status was `BLOCKED` with agent exit code 0.

### Actual result and evidence

| Case | Result | Evidence |
| --- | --- | --- |
| Initial clarification request | FAIL | Host clarification audit recorded `policy=rejected`, reason `request is not canonical JSON`; no clarification response was supplied. |
| API resource creation/session-ID and lease comparison | BLOCKED | The request was rejected before any API envelope was published. Host final audit reports `api_audit_error=missing`, with no API requests/responses, so no create-session body ID or lease path ID exists to compare. |
| Principal schema, correction, apply and semantic acceptance | NOT EXECUTED | The Agent remained fail-closed and reached its own `BLOCKED` terminal status. |
| Variant, blind consumer and mutation | NOT EXECUTED | Gated on a completed baseline and not started. |

The host final audit records no completion-gate errors and no forbidden host transcript path. Evidence
hashes: clarification audit `7e8643573329ed95f39be77b79d079b269b72af260b9cee779ae5ef2f1d3d9fb`,
runtime record `e62874c079ac852e7eb314b050a594a88c4458c685ccdb5a7e9f315937276b12`, decision log
`ff3cc23d631cfb5993d0a2700835b662773e093d2d956762ba5d4a50ad4e2f70`, transcript
`9be10ab8314446494a6e3d989e5e7153946731a1b3242802586fe79e8dbe1ba3`.

### Defect

1. **M4-R18-01 — High acceptance blocker: Agent request serialization is incompatible with host canonical
   JSON verification.**
   - Reproduction: run the exact fresh Round-18 command above, without modifying the staged prompt,
     contract, ABox or host responder.
   - Expected: clarification request JSON is serialized in the host's canonical byte representation and
     receives a host response, allowing the normal three-question sequence and subsequent resource-ID
     checks.
   - Actual: Agent code uses Python `json.dumps` default `ensure_ascii=True`, escaping the visible
     U+2019 character as `\\u2019`; host canonical verification serializes semantically equivalent JSON
     with `ensure_ascii=False`. The raw-byte mismatch is rejected as non-canonical JSON, no response is
     written, and no API request is attempted. The Agent correctly eventually records `BLOCKED` rather
     than attempting an unverified fallback.
   - Evidence: host rejection reason, absent API audit/response artifacts, final-audit hashes and the
     natural Agent terminal record above. This is a transport canonicalization compatibility defect, not
     an ID-integrity or semantic-platform failure.

### Cleanup and conclusion

The isolated backend was stopped. The owned database and Oxigraph container were removed and the run root
was moved to the system recycle bin; no `8012`/`7879` listener remained. The regular service remained
active, `:8001/api/health` and `:5173/` passed, and `git diff --check` passed.

**FAIL.** Round 17's offline resource-ID gate remains PASS, but the Round-18 baseline cannot reach it
because canonical JSON transport rejects the first clarification request. Have the requirement developer
align Agent/transport JSON serialization with the host canonicalization contract and add a Unicode
punctuation regression before a new independent baseline. Do not run variant, consumer or mutation cases
until a baseline reaches authoritative `COMPLETED`.

## Round-18 Unicode canonicalization repair gate — planned

Before another live baseline:

1. `parse_request` must accept both sorted compact JSON renderings of the same Unicode request:
   direct UTF-8 produced with `ensure_ascii=False` and standard `\uXXXX` escaping produced with
   `ensure_ascii=True`, each with no suffix or exactly one currently allowed final line ending.
2. Both accepted byte forms must return identical parsed content and identical normalized canonical
   request bytes/hash for matching and evidence. Raw request hashes must remain distinct and auditable.
3. Existing rejection cases must remain rejected: unsorted keys, extra/internal whitespace, duplicate
   keys, malformed UTF-8/JSON, wrong envelope, and all unsupported trailing bytes.
4. M4 and preceding offline gates, Ruff, manifest and diff checks must pass independently. Only then may
   one fresh unsupplemented baseline run; variant, consumer and mutation remain gated on `COMPLETED`.

## Round 19 — 2026-07-27 independent Unicode canonicalization offline gate (PASS)

### Scope and direct boundary evidence

- Directly exercised the clarification parser with a request containing U+2019. Compact sorted direct
  UTF-8 (`ensure_ascii=False`) and compact sorted escaped JSON (`ensure_ascii=True`) were both accepted,
  parsed to identical values and normalized to identical canonical UTF-8 bytes/hashes, while retaining
  distinct raw byte hashes.
- Direct negative checks confirmed rejection of duplicate keys, unpaired surrogate, extra whitespace and
  unsupported suffixes. M4 regression also retains malformed UTF-8/JSON, wrong envelope and noncanonical
  ordering rejection coverage.
- Frozen sources: runner `fff0fc406c0b11f350ec83f950726b16386e9c0c072e7b7ace5dd9fa0e426b74`, M4 tests
  `fd66f31f197ad6a982e65286766678e92dd5afa071b7241093bfe1ad1df86edc`, responder
  `83801a1f83a2cae53b6fd02baf45ea567b76d4de4965f7595ea90ce989c74b8b`, gateway
  `e1bcd2c90c29d56c29c5c3ca97b49b2507a02a9d75563084432d7efa20599323`, prompt
  `205317f072979babcdc2f3b1c76f8137f440cf17ba9035e715f0c229225f9b6b`, contract
  `dfdb112ca977bcaf0da69396206bd1860271e41cd460c607a165ae703247ca48`, manifest
  `a71c13b7ae360e04c79a5f147cc0aa9a2500ed3d570274ab9737fc3468185aa4`.

### Commands and actual results

- Direct parser script — **passed**: raw UTF-8 and escaped U+2019 renderings normalized identically;
  raw hashes differed; duplicate/surrogate/whitespace/suffix boundaries rejected.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **92 passed**.
- Existing stable gates were rerun: backend compiler/Modeling Batch **87 passed**, M1/M2/M3
  **13/5/27 passed**, focused semantic **18 passed**, and migration **4 passed**.
- Ruff, manifest parse and `git diff --check` — **passed**. No backend implementation changed after the
  regular service was last restarted; `ontology-platform.service` remained active and `:8001/api/health`
  plus `:5173/` succeeded.

### Conclusion

**PASS.** Unicode canonicalization accepts the two designated semantically equivalent compact renderings
without weakening fail-closed rejection. A fresh Round-20 baseline is eligible once the exclusively owned
`8012`/`7879` resources are available; it must compare create-session and lease-path IDs and stop on its
first terminal result.

## Round 20 — 2026-07-27 one fresh autonomous baseline (INCONCLUSIVE: invalid infrastructure)

### Preconditions and execution

- `8012` was occupied by an unrelated parallel workflow and was not touched. To preserve isolation, this
  run used fresh owned PostgreSQL database `m4_r20_20260727_1744`, fresh owned
  `ontology-platform-m4-r20-oxigraph` on `7879`, and isolated backend `8013`; this port deviation is
  solely conflict avoidance. Migrations completed through `0031_retrieval_label_evidence`, and the
  isolated backend reported RDF canonical mode (`rdf`/`rdf_primary`/`rdf`, legacy writes blocked).
- Ran exactly once, with no fixed schema/ABox and no retry:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round20-baseline --variant baseline --run-tag m4-round20-baseline --backend-port 8013 --timeout-seconds 660`.
  The Agent naturally ended `BLOCKED` at the first terminal condition.

### Observed valid progress

| Case | Result | Evidence |
| --- | --- | --- |
| Three material clarifications | PASS | Host audit recorded lifecycle `answered`, output-contract `answered`, and missing-score `uncertain`; each has a request/response hash. |
| Project, ontology, Build Session and lease resource IDs | PASS | Public setup calls returned 201/201/201 and lease acquisition returned 200. The host-owned Build Session create-response ID matched the Build Session segment in the lease path. |
| Principal schema dry-run | INFRASTRUCTURE BLOCKED | First dry-run request was forwarded exactly once (raw/canonical SHA-256 `ecdd42f2332b969d1d6e808e8a99704606a87ef27a39396c4bc9b2a7ec8e5f27`) and returned HTTP 500/non-JSON. |
| Candidate/correction, apply, semantic acceptance, variant, consumer and mutation | NOT EXECUTED | The baseline stopped at the first terminal condition; none was started. |

### Infrastructure finding and invalidity rationale

The owned Oxigraph was started without explicit `--bind 0.0.0.0:7878`; its container log showed only a
localhost listener. Requests to the published host port reset the peer connection. The backend's
principal-schema failure is therefore `RdfStoreUnavailable: [Errno 104] Connection reset by peer`, from
`RdfStore.graph_exists` → `query_sparql` during candidate-delta validation, not a product/schema result.
The preceding modeling-context request already had the related semantic-count query failure. This run is
invalid as M4 acceptance evidence and **does not create an M4 product defect**.

The final audit has status/runtime status `BLOCKED`, no completion-gate errors and no forbidden host path.
Hashes: API audit `d124923f2aeb74d3bcda1739c8cef86ee3d9a95d6eaeb6b3e9417e20db298ca5`, clarification audit
`cf78f78ed1e4bba2d9f2b4f5fcda9bd92e36601a72afe00582f892e313d48076`, runtime record
`58533640c1de5c234973a5a3cbaad1218fc7fc5093282ddc6face13fe28fa5e0`, decision log
`083b4ccac2d5cbda744ede6cae4d750e291c4cebe2b2a8c129edfcc2da4cc192`, transcript
`20121b13b18fa55495234029fdac51b818dfcf7198ac28a445bdc96592787e38`.

### Cleanup and conclusion

After traceback capture, the isolated `8013` backend was stopped; the owned database, container and run
root were removed (run root moved to the system recycle bin). No owned `8013`/`7879` listener remained;
the pre-existing unrelated `8012` workflow was left untouched. The regular service stayed active,
`:8001/api/health` and `:5173/` passed, and `git diff --check` passed.

**INCONCLUSIVE.** Round 19 remains PASS, and the clarification plus resource-ID/lease portions are valid
observations, but the absence of a correctly reachable isolated RDF store invalidates all principal-schema
and downstream acceptance conclusions. A newly assigned baseline must start Oxigraph with explicit public
container binding and require both a direct host-port query and modeling-context semantic warning-free
gate before running the Agent. No variant, consumer or mutation run is authorized until a valid baseline
reaches `COMPLETED`.

## Round-21 final-audit repair gate — planned

Round 21 produced a completed real workflow but its final audit reported four incompatible evidence
comparisons. Before classifying the preserved baseline:

1. All schema/ABox evidence must use one graph-set ID. Schema dry/apply must share
   `source_signature_before`; schema apply must expose a non-empty `source_signature_after` equal to the
   intentional-invalid and first-candidate `source_signature_before`.
2. Direct-success candidate dry/apply must share `source_signature_before`. In the correction branch,
   failed-candidate/correction-dry/correction-apply must share it. A negative test must prove a
   cross-phase signature splice is rejected.
3. `optional_rule_absent` must be checked using the existing prompt-defined `code`, `message`,
   `request_id` and `response_sha256` evidence, with negative cases for any mismatch.
4. Checkpoint response continuity and the complete request's `expected_revision` must be compared with
   `runtime-record.json.checkpoint.session_revision`; wrong or stale revisions must still fail.
5. The prompt, input manifest and frozen manifest hash remain unchanged. M4 focused tests, Ruff, manifest
   verification and `git diff --check` must pass.
6. Re-run the host final audit against a copy of the preserved Round-21 evidence with the original run
   metadata. Do not overwrite the original evidence and do not run another live Agent.

## Round-22 fresh-workspace role repair gate — planned

Before another withheld variant:

1. The staged generic command contract must name the authoritative current workspace roles
   `asserted_ontology`, `asserted_data`, `shapes` and `policy`, and require the Agent to use returned role
   values without shortening them.
2. It must state that a ready fresh workspace with required members, empty initial hashes and zero resource
   counts is valid input to the first Modeling Batch rather than a blocker.
3. Focused tests must freeze these statements and synchronize the command-contract SHA, input manifest and
   runner frozen-manifest SHA. Manifest verification and `--prepare-only` must pass.
4. After the offline gate, run exactly one new fresh unsupplemented `pinned-non-successor` variant. Do not
   reuse or retry the failed Round-22 workspace.

## Round-24 entity-property IRI repair gate — planned

Before another withheld variant:

1. `create_entity` and `update_entity` must preserve explicit property IRIs and expand non-empty bare
   property IDs through the platform property namespace.
2. Empty or non-string property keys must fail at compilation; no relative `<bare>` predicate may enter a
   compiled RDF delta.
3. Compiler tests must cover create/update, explicit IRI preservation and invalid keys. A Modeling Batch
   service test must prove the same bare-property candidate dry-runs and applies successfully, with only
   absolute predicates reaching the RDF store.
4. Relevant backend suites, M4 focused tests, Ruff and `git diff --check` must pass. Backend changes require
   the normal service restart and health checks.
5. The preserved Round-24 failure is evidence only; do not retry its recovering workspace. After offline
   PASS, use one new fresh withheld variant.

## Round-26 blind-consumer repair gate — planned

1. The consumer runner must require Project/Ontology/graph-set IDs, verify their relationship through the
   host, and stage a read-only scope file containing only those identifiers.
2. The consumer prompt must freeze the exact canonical bodyless-GET request envelope, lower-case
   request-ID plus `<id>.json` filename rule, response directory and request/response hashing procedure.
3. The read-only gateway must reject global discovery/list paths and foreign Project/Ontology/graph-set
   IDs, allowing only necessary verified-scope GET paths/read-model prefixes.
4. `consumer-record.json` must identify the supplied scope and separately record: current C target/version
   plus B contract; output continuity/discontinuity; and missing-score state. Every slot must bind to
   successful in-scope receipt IDs/hashes, and `unknown` must cite a positively observed explicit gap.
5. The wrapper must not report `COMPLETED` for exit zero plus an arbitrary record. Tests must reject the
   observed no-forwarded-request/`BLOCKED` record, irrelevant receipt, missing slot, fabricated/unbound
   claim and absence-derived unknown; a valid scope-bound three-slot record is accepted.
6. M4 focused tests, Ruff, manifest/staging checks and diff checks must pass. Then run one new consumer
   against the preserved Round-26 model; do not rerun the modeling Agent.

## Round-28 consumer read-model discovery gate — planned

1. The platform `statement-list`/Ontology `facts` response must preserve its selected subject, predicate
   and object bindings, plus object IRI/literal kind and literal datatype/language where applicable.
2. Backend service and public Ontology-route tests must prove the facts response contains actual
   predicate/object content without changing existing read-model envelope/provenance fields.
3. The consumer prompt must require a scoped Ontology `modeling-context` GET first and use its returned
   `query_entries` REST URLs for semantic entities/facts; invented shortened paths are not allowed.
4. Every final observation slot must bind to a successful allowed `semantic-read-models` request.
   Project/Ontology metadata and modeling-context discovery receipts cannot satisfy semantic observations.
5. `consumer-record.json` must use exact top-level keys `terminal_status`, `scope`, `receipts`,
   `observations` and `claim_classifications`. All three maps must have exactly
   `current_target_contract`, `output_continuity` and `missing_score` slots. The first observation must
   contain non-empty `current_target`, `target_version` and `b_contract`; the second non-empty
   `old_contract_change`, `new_contract_change` and `continuity`; the third exactly `state=unknown`,
   `explicit_gap_observed=true` and a non-empty `gap`. `claim_classifications` is a slot-to-enum map,
   with each value one of `source`, `synthetic`, `inference` or `judgment`.
6. Focused tests must accept a positive fixture containing all actual observation fields whose hashes bind
   to scoped semantic read-model gateway entries. Negative controls must reject the Round-28
   metadata-only record, missing/empty first or second observations, a receipts-only record, wrong
   classification map shape, an absent/non-explicit gap and unbound semantic receipts.
7. Run the repository-required full backend suite with `cd backend && uv run pytest`, plus focused M4
   tests, Ruff and diff checks. If the full suite is externally blocked, record the exact blocker and the
   narrower successful checks; do not silently replace it with focused tests.
8. After backend tests, restart the normal `ontology-platform.service`, verify active status,
   `:8001/api/health` and `:5173/`, then restart the isolated backend and verify its preserved `facts`
   response contains subject/predicate/object before running one new consumer. Do not rerun the modeling
   Agent or mutate the model.

## Round 21 — 2026-07-27 fresh baseline evidence and preserved-evidence final-audit repair (PASS)

### Original fresh baseline facts

- The fresh isolated baseline used the corrected explicitly bound Oxigraph and backend `8013`, because
  unrelated `8012` remained occupied and untouched. Direct host SPARQL `ASK {}` succeeded; the first
  modeling-context response was HTTP 200 with `resource_counts_warning=null`.
- Three material clarifications were accepted (`answered`, `answered`, `uncertain`). The created Build
  Session ID `be48c8bd-973d-4cdf-bd2a-6a4ce7b3ea19` exactly matched the lease response and lease-path
  session segment. Principal schema dry-run/apply validated and applied; intentional invalid ABox dry-run
  returned governed `shacl_violation`; the first actual candidate ABox validated and applied without a
  correction request. Validation, reasoning, positive governed query, checkpoint, complete and final GET
  all succeeded; the final Build Session was `completed`.
- The original host audit nevertheless recorded `INCONCLUSIVE`, hash
  `5e79ebabbf641a9d0604bf48efdbb818922e205b113e3774cbf2d496beff86e1`, with four erroneous gate labels:
  `valid_instance:not_matching_validated_apply`,
  `governed_query:missing_optional_rule_absent_decision`, `checkpoint_response_mismatch`, and
  `complete_expected_revision_mismatch`.

### Independent repair verification

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **100 passed**. Ruff, manifest JSON parsing and `git diff --check` passed.
- `--prepare-only` succeeded in a separate temporary namespace, proving the frozen manifest and staging
  path remained valid after the repair.
- The original run root was copied to a distinct temporary directory. A minimal Python harness invoked
  the current internal `_final_audit` only on that copy, retaining the original run tag
  `m4-round21-baseline`, runner start `2026-07-27T09:42:49.596611+00:00`, agent exit code `0`, canonical
  mode and host metadata. It emitted `status=COMPLETED` and `completion_gate_errors=[]`; re-audit hash
  `539144ce8555e35e8a41efbc8c07435b11358ebe5ba09d1bbdee275ec996abae`.
- The original final-audit hash remained exactly `5e79ebabbf641a9d0604bf48efdbb818922e205b113e3774cbf2d496beff86e1`.
  No original file was overwritten and no Agent/API process was started for re-audit.
- Signature continuity remains enforced: one graph set
  `ab052530-b6a8-5aad-8b31-4b584dc82f19`; schema dry/apply share before signature
  `193207831a6ba2594113197e42eed9a9`; schema apply after signature
  `7e607c97d96bbb1cd1f853258a9ff24c` equals intentional-invalid, candidate dry-run and candidate-apply
  before signatures. The dedicated continuity check returned no errors.

### Cleanup and conclusion

The Round-21 isolated backend, owned database, Oxigraph container, original run root, re-audit copy and
prepare-only directory were removed (directories moved to the system recycle bin). No owned `8013`/`7879`
listener remained; unrelated `8012` was verified still present and was not touched. The regular service
remained active; `:8001/api/health`, `:5173/`, and diff checks passed.

**PASS.** The preserved fresh baseline re-audits to authoritative `COMPLETED`; all four former audit
errors are resolved while continuity validation remains stronger. This verifies the normal baseline
closure only. No new Agent run, correction replay, variant, consumer or mutation scenario was performed.

## Round 22 — 2026-07-27 fresh withheld `pinned-non-successor` variant (BLOCKED)

### Preconditions and execution

- Created fresh owned database `m4_r22_20260727_1815`, explicitly bound owned Oxigraph container
  `ontology-platform-m4-r22-oxigraph` on `7879`, isolated backend `8013`, and run root
  `/tmp/m4-round22-variant`; unrelated `8012` was not touched. Direct host `ASK {}` passed; isolated
  health and RDF canonical mode passed.
- Executed exactly once, unsupplemented and without retry:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round22-variant --variant pinned-non-successor --run-tag m4-round22-variant --backend-port 8013 --timeout-seconds 660`.

### Actual result

| Case | Result | Evidence |
| --- | --- | --- |
| Three withheld-variant clarifications | PASS | Host audit has lifecycle `answered`, output-contract identity `answered`, and missing-score `uncertain`. |
| Resource IDs and context precondition | PASS | Project/ontology/Build Session creation returned 201; modeling-context returned 200 with `resource_counts_warning=null` and expected fresh zero counts. |
| Lease, schema, ABox, semantic acceptance and withheld semantic facts | BLOCKED | No lease or Modeling Batch was submitted. After reading fresh workspace context, the Agent recorded `BLOCKED`: `Workspace context lacks data or shapes graph`. |
| Positive variant query proof | NOT EXECUTED | No ontology model exists, so no tester semantic query can prove the pinned Version 1 target, old-contract removal, distinct addition/discontinuity, or unknown missing-score gap. |
| Consumer and mutation | NOT EXECUTED | Not authorized and not started. |

The host final audit is terminal `BLOCKED` with no completion-gate errors. Evidence hashes: API audit
`393493cee88362fd8c803360a02a7244f811cb0bd1d1f7399228939a2723d248`, clarification audit
`afafb93a467836e253bd441a59ce20af6c7d01b1f772745cced5b9892af7bf09`, runtime record
`49e632381f02fb6804f3c5158eb3b9d1f21dcde1abd216bec4a0a672b744d4e8`, decision log
`ce4a0f6b8190a76254f3e73b3a0c447ba4903be34e461a9529eb70322979342e`, transcript
`756fdd101a88b566f10f9e92e469fb8772161826f73a26321ce47e3a43c0c03e`.

### Defect

1. **M4-R22-01 — High acceptance blocker: withheld-variant Agent treats an expected empty fresh workspace
   as a terminal block.**
   - Expected: after fresh resource/context reads, acquire the lease and construct the variant ontology;
     an empty data/shapes graph is the normal initial state for this scenario.
   - Actual: with warning-free zero resource counts, the Agent exits before lease acquisition with
     `Workspace context lacks data or shapes graph`.
   - Impact: no evidence exists for the pinned non-successor facts or variant semantic isolation.

### Preservation and conclusion

**BLOCKED.** Per instruction, the owned `8013`, database, Oxigraph and run root are preserved for the
next diagnostic/consumer decision; no retry, consumer, mutation or cleanup was performed. Fix the Agent
fresh-workspace interpretation before requesting another independent withheld variant baseline.

### Cleanup update — 2026-07-27

After the diagnostic handoff was accepted, the owned Round-22 backend was stopped; its Oxigraph container,
database and run root were removed (run root moved to the system recycle bin). No owned `8013`/`7879`
listener remained. No `8012` listener was present at cleanup time and none was touched. The regular
service remained active; `:8001/api/health`, `:5173/`, and `git diff --check` passed.

## Round 23 — 2026-07-27 independent fresh-workspace contract gate (PASS)

### Scope and evidence

- Verified the current platform command contract declares exactly the authoritative workspace roles
  `asserted_ontology`, `asserted_data`, `shapes`, and `policy`; it forbids role inference/renaming and
  explicitly permits a reported-ready fresh workspace to proceed with empty hashes and all-zero counts.
  It requires `BLOCKED` only if a required member is actually absent or workspace state is non-ready.
- Manifest verification passed for all four staged sources and the manifest hash matched runner constant
  `FROZEN_MANIFEST_SHA256=e55c3f9071c624321594be3750c8871d5ed3cf3db61a2f15a72e958718501dd1`.
- `--prepare-only` produced exactly five staged files, all mode `0444`; the hidden contract remained host
  only and the Agent-visible mount contained only the declared input files plus workspace/response mounts.

### Commands and actual results

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **101 passed**. Ruff, manifest JSON parsing and `git diff --check` passed.
- In-memory negative controls using the focused test's exact contract assertions rejected both a missing
  required role and removal of the non-ready fail-closed clause. This confirms the contract gate is not an
  unconditional continue instruction; no product/scenario file was modified.
- The temporary prepare-only namespace was moved to the system recycle bin after verification.

### Conclusion

**PASS.** The new fresh-zero workspace semantics and exact required-role fail-closed contract are staged
and hash-bound. One fresh withheld variant baseline is eligible. This gate itself does not execute an
Agent or prove variant business semantics.

## Round 24 — 2026-07-27 fresh withheld `pinned-non-successor` live variant (BLOCKED)

### Preconditions and execution

- Created the new owned database `m4_r24_20260727_1835`, explicitly bound Oxigraph container
  `ontology-platform-m4-r24-oxigraph` on `7879`, isolated backend `8013`, and run root
  `/tmp/m4-round24-variant`. Direct host Oxigraph `ASK {}` returned `true`; isolated health and RDF
  canonical mode (`canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`,
  `legacy_write_blocked=true`) passed.
- Executed exactly once, with no tester-supplied schema/ABox, retry, consumer, or mutation:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root /tmp/m4-round24-variant --variant pinned-non-successor --run-tag m4-round24-variant --backend-port 8013 --timeout-seconds 660`.
- The first `modeling_context` was HTTP 200, `workspace.state=ready`, all eight resource counts were
  zero, and `resource_counts_warning=null`; the run therefore passed the fresh-workspace gate. The three
  host clarifications were consumed as lifecycle `answered`, contract identity `answered`, and missing
  score `uncertain`.

### Actual result

| Case | Result | Evidence |
| --- | --- | --- |
| Resource identity and lease | PASS | Project `ca57ac1a-b57c-4480-8673-0ef3e49f5c6a`, ontology `d5f3b6af-18e1-4ace-beaf-9ee9bb8c10b7`, and Build Session `9141a04e-75ce-4a2e-af11-8e45d93abc58` were created; lease was HTTP 200, `lease_revision=1`, and used the same session/ontology IDs. |
| Principal schema and intentional SHACL boundary | PASS | Principal schema dry-run was `200/validated`; shape apply was `200/applied`; intentional invalid ABox dry-run was `200/validation_failed` with one blocking `shacl_violation`. |
| First instance validation and autonomous correction dry-run | PASS | Initial instance dry-run correctly returned blocking SHACL failure; the Agent's correction dry-run returned `200/validated`, no blocking findings. |
| Validated correction apply / final session completion | BLOCKED | The following `apply_atomic` returned `200` but `attempt_status=recovering`, `batch_status=recovering`; recovery recorded `uncertain_execution: Expected RDF IRI, got: 'is_latest'`. Runtime terminal status is `BLOCKED` (`Validated instance correction apply failed.`); no checkpoint, completion or final completed-session audit exists. |
| Variant semantic acceptance queries | NOT EXECUTED | Because no valid ABox was atomically applied, tester-owned public semantic queries cannot establish the pinned Version 1 binding, old field removal, distinct new addition/discontinuity, or unknown gap. |
| Consumer and mutation | NOT EXECUTED | Explicitly prohibited until a completed baseline exists. |

The host final audit is terminal `BLOCKED`, while its structural `completion_gate_errors` list is empty;
it is not a completed Build Session. Evidence hashes: API audit
`a1f243fdf837133caf604228bbedeefc774f72f621a3d0e36fbb5a156ca26f92`, clarification audit
`3054c7164c043d85723c193a9351572a7545e1ccf856e20c2b6ddd1507d57f90`, runtime record
`e3c04d564901280016751e8746da8f98aeab8a48216ce4ff8c666e084bc9d590`, decision log
`e0c228f171af9a22fce6dc70f69300244accb671be4957f6efe8468009663930`, transcript
`baef6c39cea60d9915dfd2bf933281c30530090278cd50ce64ab8e02606554d9`.

### Defect

1. **M4-R24-01 — High acceptance blocker: a Modeling Batch accepted by dry-run cannot be applied when
   it contains a bare predicate token.**
   - Reproduction: fresh warning-free workspace; submit the Agent-generated corrected instance batch.
     Its correction dry-run is `200/validated` (`ae07af2d-0997-4903-8a0e-36bca6e7e700`), then submit its
     `apply_atomic` counterpart (`7826634c-9a92-4ab7-b152-7138f269d1d2`).
   - Expected: a validated dry-run must either apply atomically or the dry-run must reject the exact
     unsupported predicate form before it is presented as valid.
   - Actual: apply transitions to recoverable uncertainty with `Expected RDF IRI, got: 'is_latest'`.
     The corrected batch contains `is_latest`/`version_number` as bare predicate tokens; the dry-run
     normalized them, but the Oxigraph write path rejects `is_latest` as a non-IRI.
   - Impact: the withheld pinned-non-successor baseline cannot reach completed session state, so none of
     its semantic acceptance assertions can be truthfully tested.

### Preservation and conclusion

**BLOCKED.** The Agent runner exited normally, but the requirement run did not complete. The owned
backend `8013`, Oxigraph `7879`, database, container and `/tmp/m4-round24-variant` are deliberately
preserved for diagnosis/retest; no consumer or mutation was started. A requirement developer should fix
the dry-run/apply predicate-validation consistency (or contract-supported predicate representation), then
request a new fresh variant baseline rather than retrying this workspace.

### Cleanup update — 2026-07-27

After root-cause confirmation, the owned Round-24 backend process group on `8013` was stopped, the owned
`ontology-platform-m4-r24-oxigraph` container was removed, and the exact owned database
`m4_r24_20260727_1835` was dropped after confirming it had no remaining sessions. The run root
`/tmp/m4-round24-variant` was moved to the system recycle bin. Verification found no owned `8013` or
`7879` listener, no matching container/database and no run-root path. The unrelated `8012` listener was
not touched (none was present at the check). The regular service remained healthy: `:8001/api/health`
returned `{"status":"ok"}` and `:5173/` returned successfully.

## Round 25 — 2026-07-27 offline property-IRI dry-run/apply consistency gate (PASS)

### Scope and boundary verification

- Read-only review of `semantic_command_compiler._property_iri` confirms that only a non-empty string
  property key is accepted; a bare key expands through the canonical `property` namespace, while a key
  containing `:` is retained as an explicit IRI.
- Stage2 compiler tests exercise both `create_entity` and `update_entity`: bare `is_latest` expands to
  `http://op.local/ns/property/is_latest`; explicit
  `http://op.local/ns/property/email` is unchanged; empty and non-string keys raise
  `InvalidCommandPayload`. Their normalized deltas contain no `<is_latest>` relative predicate.
- Modeling Batch service coverage creates the `is_latest` schema property, submits the same bare-key
  entity candidate first as dry-run and then as `apply_atomic`. It asserts
  `dry_run.attempt_status=validated`, `applied.attempt_status=applied`, and RDF insert predicates include
  `<https://r004.test/resource/property/is_latest>` but not `<is_latest>`.

### Commands and actual results

- `uv run --directory backend pytest tests/test_semantic_command_compiler_stage2.py` — **34 passed**.
- `uv run --directory backend pytest tests/test_modeling_batches_service.py` — **54 passed**.
- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **101 passed**.
- `uv run --directory backend ruff check app/services/semantic_command_compiler.py
  tests/test_modeling_batches_service.py` — passed. The full compiler test file reports 16 Ruff findings,
  but the identical 16 findings occur on the `HEAD` version; they are pre-existing test-file lint debt,
  not a property-IRI regression.
- The frozen input manifest SHA is
  `e55c3f9071c624321594be3750c8871d5ed3cf3db61a2f15a72e958718501dd1`, matching the runner constant.
  A fresh `--prepare-only` namespace passed with four declared sources, five staged read-only files, the
  expected mount policy, and a host-only hidden contract; the temporary namespace/output were moved to
  the system recycle bin.
- `git diff --check` passed. `ontology-platform.service` is active; `:8001/api/health` returned
  `{"status":"ok"}` and `:5173/` returned successfully. No Round-24 `8013` or `7879` listener exists.

### Conclusion

**PASS.** The Round-24 bare-property failure is covered offline at compiler and Modeling Batch service
levels: generated RDF predicates are absolute and a validated bare-key candidate applies unchanged. No
live Agent/variant, consumer, or mutation was run in this round. Exactly one new fresh
`pinned-non-successor` variant is authorized for the next round; it must use a new database, Oxigraph
namespace and run root rather than the cleaned Round-24 workspace.

## Round 26 — 2026-07-27 fresh withheld `pinned-non-successor` live variant (INCONCLUSIVE)

### Preconditions and one-time execution

- Created the owned database `m4_r26_20260727_184806`, explicitly bound owned Oxigraph container
  `ontology-platform-m4-r26-oxigraph` on `7879`, isolated backend `8013`, and run root
  `/tmp/m4-round26-variant`. Direct host `ASK {}` returned `true`; the final isolated canonical gate was
  `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`, and
  `legacy_write_blocked=true`; isolated health passed. (The isolated backend was restarted before the
  Agent started because its first configuration inherited legacy mode; no Agent/API workflow had run.)
- Executed exactly once, unsupplemented and without tester supplied schema/ABox, retry, consumer, or
  mutation: `uv run --directory backend python
  ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_clarification.py --run-root
  /tmp/m4-round26-variant --variant pinned-non-successor --run-tag m4-round26-variant --backend-port
  8013 --timeout-seconds 660`.
- The first modeling-context response was HTTP 200 with `workspace.state=ready`, zero counts for every
  modeled resource, and `resource_counts_warning=null`. The three required clarifications were
  `answered`, `answered`, and `uncertain`.

### Actual result

| Case | Result | Evidence |
| --- | --- | --- |
| Resource identity and lease | PASS | Project `17b71934-6dce-4f6c-be04-b542622331cd`, ontology `94f997b3-a8d9-4f31-8566-966ce03596d1`, and Build Session `2e845b3e-e01a-44c6-86c2-1f75eb839192` were created; lease returned 200. |
| Schema and ABox workflow | PASS | Principal schema dry-run `validated` and apply `applied`; intentional invalid ABox returned governed `validation_failed`; valid instance dry-run `validated` and the unchanged `apply_atomic` returned `applied`. No finding-driven correction was needed. |
| Validation through checkpoint | PASS | Validation, reasoning, governed query, pre-checkpoint GET and checkpoint all returned 200. Checkpoint `04d61c07-44c7-4a3c-b958-7ad06d4f2a80` advanced the session to revision 2. |
| Complete and final audited closure | INCONCLUSIVE | The server processed `complete-session-20260727` as HTTP 200 and marked the Build Session `completed`, revision 3 at `2026-07-27T11:02:18.296436+00:00`; however the Agent exceeded the fixed 660-second deadline immediately afterwards. It did not consume the complete response into `runtime-record.json` or issue the required final GET. The runner records `agent_exit_code=124`, `runtime_terminal_status=INCONCLUSIVE`, final-audit `status=INCONCLUSIVE`, and no completion-gate errors. |
| Tester-owned positive semantic queries | PASS | Main-agent scope decision authorized subsequent public read-only queries against the preserved completed server state; the exact bindings are recorded below. |
| Consumer and mutation | NOT EXECUTED | Not authorized before a successful completed final audit. |

### Defect

1. **M4-R26-01 — High acceptance blocker: the fixed 660-second Agent window expires after the server
   completes the Build Session but before the Agent consumes completion evidence and performs final GET.**
   - Reproduction: run the fresh unsupplemented pinned-non-successor variant under the required
     `--timeout-seconds 660` ceiling.
   - Expected: Agent records the complete response, retrieves the terminal session, and host final audit
     reports `COMPLETED` before the deadline.
   - Actual: server response is already `200/completed` (revision 3), while the host audit records
     `agent_exit_code=124`, runtime `INCONCLUSIVE`, and lacks completion receipt/final GET.
   - Impact: the required terminal evidence and independent semantic assertions cannot be accepted even
     though the underlying server-side write/session completion occurred.

### Preservation and conclusion

**INCONCLUSIVE pending direct read-only acceptance.** The Agent-side final audit completion condition was not
achieved, but the server-side Build Session completed and core modeling chain is intact. Evidence hashes:
API audit `d1412ac44e17aa1f9e5a9d8e466aefb68fa2f8e5b4936a8c56eb8b1d9e127cbf`, clarification audit
`b897b22e4495eebc3341216d5219ed2e0b5fa308e8558c0587841dcb2a075c27`, runtime record
`aeea93e2b0e4a10be6d4c6330f3345ea2705a2ce5f3018da769004dd0e8ca387`, decision log
`5cf21d2a502724e20aeaa07d32dd454d350dce0e8c1654bcc7a19b631b8d0d38`, transcript
`8067b6c235dfd8d38490b14bb422817690a4fc1a787315dec36d8c98b113ad1a`.

The owned `8013`, `7879`, container, database and run root are deliberately preserved. Do not retry this
workspace or start mutation. The main-agent-authorized tester-owned direct read-only semantic query and
one fresh blind read-only consumer use this preserved server state without writing API; their results
follow.

### Direct read-only acceptance and blind consumer continuation

- Tester-owned public `POST /api/semantic/sparql:query` requests scoped to the preserved project/ontology
  returned HTTP 200 and `scope.status=complete`. The governed current-impact binding is:
  `target=C Published Version 1`, `bContract=quality_score:number`,
  `continuity=discontinuous: quality_score:number removed; quality_rating:number distinct addition`, and
  `gap=unresolved; business owner cannot confirm behavior`.
- A second public read-only query returned two distinct modeled published-state resources:
  `c_published_version_1` labeled `C Published Version 1` and
  `c_latest_published_version` labeled `C Latest Published Version`. Together with the governed
  `current_c_target` and `contract_used_by_b` facts, this proves the accepted current B contract binds
  Version 1 rather than silently substituting the separately modeled latest version. It also positively
  proves old `quality_score:number` removal, distinct new `quality_rating:number` addition and explicit
  non-successor/discontinuity; the missing-score fact is explicitly unknown, not inferred from absence.
- Ran exactly one fresh blind read-only consumer at `/tmp/m4-round26-consumer` with backend `8013` and a
  600-second ceiling. It made no upstream platform request: all five locally written request files were
  rejected by the host read-only gateway before dispatch because their names (`001.json`, `002.json`,
  `003.request.json`, `004`, `005.get`) violate the strict lowercase-ID filename contract. No unsafe API
  method was declared, and no write occurred.
- The consumer Agent exit code is 0 and its wrapper audit mechanically says `COMPLETED`, but its actual
  `consumer-record.json` terminal status is `BLOCKED`: it received no response, produced no variant
  explanation, and retained missing-score as `unknown`. The wrapper's completion criterion therefore is
  insufficient for consumer acceptance.

### Additional defects

2. **M4-R26-02 — High acceptance blocker: the blind read-only consumer prompt omits the spool envelope
   and strict filename protocol.**
   - Expected: a fresh consumer can construct valid bodyless GET envelopes and read the platform scope.
   - Actual: it attempts five incompatible filenames; the gateway rejects each before dispatch, leaving
     the consumer without modeled facts and terminal `BLOCKED`.
   - Impact: the required independent consumer cannot derive the pinned variant explanation, despite the
     platform's direct semantic query proving it.

3. **M4-R26-03 — Medium reporting defect: consumer wrapper reports `COMPLETED` when the consumer's own
   record is `BLOCKED`.**
   - Expected: wrapper success must include the record's semantic terminal state, not merely Agent exit
     code plus record-file existence.
   - Actual: `consumer-audit.json` reports `COMPLETED`, while `consumer-record.json` reports `BLOCKED`.

### Continued conclusion

Round 26 remains **INCONCLUSIVE** for its original Agent-final-audit condition. Direct read-only semantic
acceptance is positive, but blind consumer acceptance is blocked by the consumer-spool protocol defect.
Consumer and variant runtime state remain preserved; no mutation was run.

## Round 27 — 2026-07-27 blind-consumer offline contract gate (PASS)

### Scope and offline verification

- Verified `verify_consumer_scope` performs host-only relationship checks before staging: the project
  response ID must match, the ontology must belong to that project, and workspace context must match both
  ontology and default graph-set IDs. `consumer_paths` stages only the prompt plus a canonical,
  read-only `consumer-scope.json`.
- Verified the read-only gateway requires a verified scope, accepts only bodyless `GET`, and permits only
  exact project/ontology/workspace/graph-set paths plus matching scoped read-model prefixes. Global,
  foreign and malformed paths are rejected without forwarding; the normal modeling gateway remains able
  to forward its permitted methods.
- Verified the prompt freezes the canonical compact JSON `<id>.json` envelope, scope-only rule and three
  answer-neutral receipt slots. The consumer record validator requires exactly
  `current_target_contract`, `output_continuity`, and `missing_score`; every receipt must bind a successful
  forwarded audit entry's request ID and both request/response hashes. It also requires explicit
  `missing_score={state:unknown, explicit_gap_observed:true}` and valid slot classifications.
- Negative controls cover Round-26 behavior: invalid filenames and an exit-0 record whose semantic state
  is `BLOCKED` are not classified as completed; absent/unbound slots, irrelevant receipts, wrong hashes,
  missing scope and non-explicit unknown gaps all fail validation.

### Commands and actual results

- `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **114 passed**. This includes scope/staging, exact read-only allowlist and normal-gateway regression,
  record binding/negative controls and canonical-prompt tests.
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_readonly_consumer.py ../docs/evaluation-scenarios/dify-workflow-impact-m4/m4_api_file_spool_gateway.py ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests/test_m4_clarification.py` — passed.
- `git diff --check` — passed.
- Read-only host verification against preserved Round-26 state passed. Runtime and original workspace
  evidence agree on project `17b71934-6dce-4f6c-be04-b542622331cd`, ontology
  `94f997b3-a8d9-4f31-8566-966ce03596d1`, and default graph set
  `3b69bc3f-f806-5300-bef2-7306335a0ec4`; the backend verifier returned the same exact triple.

### Conclusion

**PASS.** The repaired blind-consumer gate fail-closes on the former protocol/semantic-terminal failures
while retaining a scope-bound, read-only path for a fresh consumer. One new consumer run is authorized
against the preserved Round-26 IDs. No consumer was started in this offline round and no mutation is
authorized.

## Round 28 — 2026-07-27 fresh blind read-only consumer against preserved `8013` scope (FAIL)

### Scope and execution

- Executed exactly once with no modeling Agent, mutation, retry, answer injection, expected-value input,
  or access to modeling logs:
  `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_readonly_consumer.py
  --run-root /tmp/m4-round28-consumer --run-tag m4-round28-consumer --backend-port 8013
  --timeout-seconds 600 --project-id 17b71934-6dce-4f6c-be04-b542622331cd --ontology-id
  94f997b3-a8d9-4f31-8566-966ce03596d1 --graph-set-id 3b69bc3f-f806-5300-bef2-7306335a0ec4`.
- The staged consumer input contained only read-only `consumer-prompt.md` and `consumer-scope.json`
  (both mode `0444`). The run root did not exist before execution and is retained as evidence.

### Actual result

| Acceptance case | Result | Evidence |
| --- | --- | --- |
| Wrapper terminal state and consumer readiness | FAIL | The Agent exited `0`, but wrapper and `consumer-record.json` both ended `INCONCLUSIVE`, not `COMPLETED` / `CONSUMER_READY`. Validation errors were `not_ready`, all three receipt slots unbound, and `claim_classifications_invalid`. |
| Current target/version and B-contract receipt | FAIL | No scoped semantic fact response was obtained. The record correctly says the two successful metadata responses contain no target-contract fact. |
| Continuity/discontinuity and explicit missing-score-unknown receipt | FAIL | No modeled continuity or compatibility fact was returned. The record keeps `missing_score={state:unknown, explicit_gap_observed:true}`, but it cannot bind the required semantic slot receipt. |
| Claim classifications | FAIL | The record contains source, inference and judgment classifications, but the contract validator rejects the set because the required semantic receipt basis is absent. |
| Scope and write safety | PASS | Gateway audit has exactly two forwarded, scoped bodyless `GET`s (project and ontology) and 29 rejected guessed paths. Every request declaration used `GET`; there is no forwarded global, foreign, or write request. |

### Defect

1. **M4-R28-01 — High acceptance blocker: a blind consumer cannot discover a permitted scoped read-model path that supplies the three required semantic slots.**
   - Reproduction: run the fresh consumer with only the Round-27 prompt/scope files and the preserved
     project, ontology, and graph-set IDs.
   - Expected: it uses the supplied read-only protocol to receive three successfully forwarded,
     scope-bound semantic responses for current target/B-contract, continuity/discontinuity, and the
     explicit missing-score gap; their receipts validate and the wrapper reports `COMPLETED`.
   - Actual: only `GET /api/projects/<project>` and `GET /api/ontologies/<ontology>` returned 200. They
     expose metadata/topic descriptions but not the required facts. The consumer then made 29 in-scope
     path guesses, each safely rejected by the exact allowlist, and wrote an `INCONCLUSIVE` record with
     unbound slots.
   - Evidence: `/tmp/m4-round28-consumer/host/api-audit.jsonl` has two forwarded and 29 rejected entries;
     `consumer-audit.json` records the five validation errors; `consumer-record.json` and transcript show
     no semantic fact response was available. Audit SHA-256 is
     `22db1ab8a260e5d90d6a8484d8fd1945d20ac18c32875378d13d4d9145ede6d0`.

### Preservation and conclusion

**FAIL.** The fail-closed wrapper and gateway security behavior pass, but the user-facing M4 blind-consumer
acceptance cannot pass until the consumer is given a discoverable, scope-bound read-model contract (or an
equivalent allowed bodyless GET route) that returns the three required facts. Preserve `8013`, its owned
database/Oxigraph state, and `/tmp/m4-round28-consumer`; do not rerun this consumer. A requirement developer
should repair the consumer read-model contract before a new consumer run is authorized.

## Round 29 — 2026-07-27 Round-28 consumer-discovery repair acceptance (PASS)

### Scope and non-goals

- This is a repair-only independent test round. Per authorization, it did **not** run a blind consumer,
  modeling Agent, Modeling Batch, migration, or mutation. It only exercised the repaired public read
  contract with authenticated `GET` requests.
- Reviewed the Round-28 contract change: the consumer prompt now mandates
  `GET /api/ontologies/<ontology_id>/modeling-context` first and permits subsequent requests only to the
  exact returned `query_entries.entities.rest` / `query_entries.facts.rest` URLs. The gateway permits
  that scope-bound path, and record validation now rejects extra keys in every receipt and observation
  inner object.

### Automated regression and static results

- `uv run --directory backend pytest -q tests/test_semantic_read_model_stage2_execution.py
  tests/test_modeling_batches_read_model_retrieval.py ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests`
  — **146 passed**.
- `uv run --directory backend pytest -q ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests` —
  **121 passed**, including the new extra-receipt-key and extra-observation-key rejection cases.
- `uv run --directory backend ruff check app/services/semantic_read_model.py
  tests/test_semantic_read_model_stage2_execution.py tests/test_modeling_batches_read_model_retrieval.py
  ../docs/evaluation-scenarios/dify-workflow-impact-m4` — passed.
- Full backend `cd backend && uv run pytest` — **1 failed, 807 passed, 10 skipped**. The sole failure is
  the existing `tests/test_mcp_auth.py::test_mcp_startup_requires_environment_key`: deleting the process
  variable does not defeat the checked-out `.env` reload. The precise exclusion rerun
  `uv run pytest -q -k 'not test_mcp_startup_requires_environment_key'` passed **807**, skipped **10**,
  deselected **1**. No MCP/auth implementation is in this repair scope.
- `git diff --check` — passed.

### Runtime read-only acceptance

- Normal `ontology-platform.service` remained `active`; `:8001/api/health` returned 200 and `:5173/`
  returned HTTP 200.
- The preserved Round-26 Oxigraph container remained on `127.0.0.1:7879`. The pre-repair isolated
  `8013` process was stale, so it was restarted without migrations or model operations. The first
  restart shell failed before parsing its URL because this host has no `python` executable; it neither
  started a service nor touched data. The successful retained restart is uvicorn PID `4048495`, recorded
  in `/tmp/m4-round26-variant/host/isolated-backend-round29-retry.log`, after explicit assertion of
  `DATABASE_URL` database `m4_r26_20260727_184806`, `OXIGRAPH_URL=http://127.0.0.1:7879`, and canonical
  `rdf` / `rdf_primary` / `rdf` / legacy blocked `true`.
- `GET /api/semantic/canonical-mode` on `8013` returned exactly
  `canonical_store=rdf`, `product_write_mode=rdf_primary`, `read_mode=rdf`, and
  `legacy_write_blocked=true`.
- `GET /api/ontologies/94f997b3-a8d9-4f31-8566-966ce03596d1/modeling-context` returned the exact
  scope-bound facts URL
  `/api/ontologies/94f997b3-a8d9-4f31-8566-966ce03596d1/semantic-read-models/facts`; the next GET used
  that returned URL verbatim. Its `statement-list` has 214 items, all 214 with non-empty `subject`,
  `predicate`, `object`, and valid `object_kind`; 100 are `iri` and 114 are `literal`.
- Literal metadata was also checked: 14 literal items include a string `object_datatype`, none contain
  null or non-string datatype/language metadata, and no literal item includes `object_language`.

### Conclusion

**PASS for the Round-28 repair scope.** The fresh consumer now has a discoverable, scope-bound,
bodyless-GET read-model path, public facts preserve statement identity/kind and literal metadata, and the
record contract fail-closes on extra inner keys. There is no defect or blocker in this authorized
read-only repair verification. End-to-end blind-consumer acceptance remains **not executed by explicit
round instruction**, rather than passed by inference; a future authorized consumer run is required for
that separate acceptance case. The preserved `8013`, `7879`, database and model state remain retained.

## Round 30 — 2026-07-27 fresh blind read-only consumer after discovery repair (PASS)

### Preconditions and one-time execution

- Confirmed `/tmp/m4-round30-consumer` did not exist before starting. Preserved isolated `8013` returned
  health `ok` and canonical mode `rdf` / `rdf_primary` / `rdf` with legacy write blocked; preserved
  Oxigraph remained on `127.0.0.1:7879`.
- Executed exactly once, with no modeling Agent, mutation, answer injection, retry, or additional
  consumer: `MCP_API_KEY="$ONTOLOGY_MCP_API_KEY" uv run --directory backend python
  ../docs/evaluation-scenarios/dify-workflow-impact-m4/run_m4_readonly_consumer.py --run-root
  /tmp/m4-round30-consumer --run-tag m4-round30-consumer --backend-port 8013 --timeout-seconds 600
  --project-id 17b71934-6dce-4f6c-be04-b542622331cd --ontology-id
  94f997b3-a8d9-4f31-8566-966ce03596d1 --graph-set-id
  3b69bc3f-f806-5300-bef2-7306335a0ec4`.

### Actual result

| Acceptance case | Result | Evidence |
| --- | --- | --- |
| Wrapper, terminal state and strict record shape | PASS | Agent exit `0`; `consumer-audit.json` reports `COMPLETED` with no validation errors; `consumer-record.json` reports `CONSUMER_READY` and exact scope/slot shapes. |
| Discoverable read path and scope boundary | PASS | First forwarded path was the required ontology `modeling-context`; its returned `entities.rest` and `facts.rest` were then used verbatim. Gateway audit has exactly three forwarded paths, all within the supplied ontology scope, and no rejected/global/foreign request. |
| Current target/version and B contract | PASS | Consumer reports `C Published Version 1`, `Version 1`, and `quality_score:number`. The facts response independently contains asserted `current_c_target`, `contract_used_by_b`, and Version-1 facts. |
| Continuity and explicit unknown gap | PASS | Consumer reports old `quality_score:number` removed, `quality_rating:number` distinct addition, and `discontinuous`; missing score is exactly `unknown` with an explicit unresolved business-owner gap. All are present as asserted facts in the returned statement list. |
| Receipt bindings and classifications | PASS | All three slots bind the forwarded `facts` receipt ID and its canonical request/response hashes. Independent canonicalization of the raw request (which has one permitted trailing newline) yields the audited request SHA; response SHA also matches. All classifications are `source`. |
| No-write gateway safety | PASS | The only requests have exact envelope keys, empty headers, `body:null`, and `GET` methods: modeling-context, returned entities URL, and returned facts URL. No POST/PUT/PATCH/DELETE declaration or forwarding occurred. |

### Evidence and preservation

- Consumer audit SHA-256: `7dfc9a897941f6098e287c44b3a9bc4515ca38e110720658ae692c932fb4d66c`.
  Consumer record SHA-256: `ddc015e74990ebb1491b0f09fb176b97fb0da70580a1f3c0f2c12d0ae8505c22`.
- The facts receipt is `facts`, canonical request SHA
  `a8e91c7583fa6f4c26166cc39727a289555e0181a094fd263ba3eb83f0367e56`, response SHA
  `afc30db10a1d79e6af76c11bcd412bf37d3beedf839c1c99099909ff34c64b3e`.
- Preserve `/tmp/m4-round30-consumer`, `8013`, `7879`, the isolated database, and modeled state. Do not
  retry this consumer.

### Conclusion

**PASS.** The repaired blind consumer independently discovers the scope-bound public read model, derives
the required pinned target, discontinuity, and explicit unknown-gap conclusions from modeled facts, and
produces three valid scoped receipts without a write or scope escape. No defect or blocker was found in
this authorized end-to-end consumer acceptance.

## Round 31 — 2026-07-27 M4 isolated runtime closure (PASS)

### Exact target confirmation

- Confirmed `127.0.0.1:8013` was owned isolated uvicorn PID `4048495`, started by the Round-29 restart
  with `app.main:app --host 127.0.0.1 --port 8013`.
- Confirmed the exact owned container was `ontology-platform-m4-r26-oxigraph`, running and bound only as
  `127.0.0.1:7879->7878/tcp`.
- Confirmed the exact owned PostgreSQL database was `m4_r26_20260727_184806` (one connection before
  stopping 8013). The evidence roots `/tmp/m4-round26-variant` and `/tmp/m4-round30-consumer` existed
  before cleanup and were explicitly retained.

### Cleanup and result

- Sent `TERM` only to PID `4048495` and confirmed `8013` no longer listened.
- Removed only `ontology-platform-m4-r26-oxigraph`; `7879` no longer listened.
- The host has no `psql`, so the project PostgreSQL driver was used with an admin connection to verify
  and target only `m4_r26_20260727_184806`. The first termination SQL omitted its `FROM
  pg_stat_activity` clause and safely failed before any drop. A subsequent read-only check confirmed the
  target still existed with zero connections. The corrected statement terminated only target-database
  connections (`0`) and executed the explicit quoted command `DROP DATABASE
  "m4_r26_20260727_184806"`.
- Post-cleanup verification passed: neither `8013` nor `7879` has a listener, the exact owned container
  is absent, the exact owned database no longer exists, and both evidence roots remain present.
- Normal runtime was unaffected: `ontology-platform.service` is `active`, `:8001/api/health` returned
  `{"status":"ok"}`, and `:5173/` returned HTTP 200. No operation targeted `8012`, any other database,
  container, M5 resource, or evidence root.

### Conclusion

**PASS.** The M4 isolated runtime was closed using only the verified owned PID, container, and database;
all requested retained evidence and normal application services remain available.
