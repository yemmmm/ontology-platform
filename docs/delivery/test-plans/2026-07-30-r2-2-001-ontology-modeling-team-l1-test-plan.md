# R2.2-001 Ontology Modeling Team L1 Shared Test Plan

## 1. Scope and completion gate

This plan verifies the reviewed L1 design for the v2.1 Dify Version Control slice. One shared file
holds all independent rounds. L1 completes only when a real fresh Codex run is `PASS`, the latest
independent round is `PASS`, the temporary key is revoked, owned resources are cleaned and resident
services remain healthy.

## 2. Test data boundary

Agent-visible:

- pinned Version Control source page and its manifest/source hash;
- bounded business questions and one explicitly synthetic Workflow name;
- public platform command/role contracts.

Tester-only:

- behavioral acceptance oracle;
- forbidden-answer inventory and isolation sentinel;
- expected event/tool categories;
- cleanup and credential assertions.

Forbidden from Agent-visible input: M1 ontology/Shapes/fixtures/queries, M2/M3/M4/M6 candidates,
Batch outputs, historical accepted IRIs and tester assertions.

## 3. Automated cases

| ID | Case | Expected |
| --- | --- | --- |
| L1-01 | Verify manifest and staged hashes | Only declared v2.1 source files and public contracts are staged |
| L1-02 | Probe coordinator namespace | source readable, team-work writable; repository, tester-only, backend, protocol home and key absent |
| L1-03 | Probe protocol namespace | approved candidate/public protocol readable; original source, tester-only, repository and coordinator home absent |
| L1-04 | Validate S0 role evidence | coordinator, Modeling Agent and protocol-planning Agent are distinct; no platform write occurs |
| L1-05 | Validate coordinator dispatch | task ID, candidate hash and requested outcome are complete; no Items, key or hidden answer |
| L1-06 | Validate role MCP boundary | coordinator/modeler have zero ontology MCP; real protocol Agent is the only ontology MCP caller |
| L1-07 | Validate temporary-key lifecycle | unique Project-scoped model key is absent before dispatch and revoked on every terminal path |
| L1-08 | Validate Build Session/Lease sequence | create, acquire, dry-run, apply and completion order follows returned revisions/tokens |
| L1-09 | Validate immutable Batch transition | dry-run is validated; unchanged candidate applies atomically with a fresh idempotency key |
| L1-10 | Validate workspace transition | apply advances the authoritative workspace version |
| L1-11 | Validate semantic behavior | applied model distinguishes Workflow, draft version and latest/live version through a generic read |
| L1-12 | Validate deterministic constraint | invalid/missing version classification is rejected by platform validation or candidate dry-run |
| L1-13 | Validate source fidelity | official source, synthetic fixture and Agent modeling rationale remain distinguishable |
| L1-14 | Reject answer leakage | no forbidden M1-M6 answer artifact/path/content enters staged input, prompts, transcripts or team-work |
| L1-15 | Validate terminal audit | event/receipt hashes, IDs, key revocation, cleanup and health are complete and repeatably auditable |
| L1-16 | Failure injection before protocol launch | no key exists and no platform resource contains modeled content |
| L1-17 | Failure injection after key creation | key revoked, Session cancelled/completed safely and cleanup remains owned/bounded |
| L1-18 | Audit publication failure | previous receipt remains intact and protected; temporary material is removed |
| L1-19 | Probe isolated write mode | exact sanitized REST/MCP configuration resolves `rdf_primary` before credentials/team startup |
| L1-20 | Reject resident-mode reuse | `legacy_only` canonical dry-run remains rejected; L1 never mutates resident `8001` |
| L1-21 | Validate host bootstrap lifecycle | host-only ephemeral org-admin key prepares/deletes scope, never enters Agent namespaces and self-revokes |
| L1-22 | Reject backend secret mount | `/backend/.env` is absent; host long-term key fingerprint is absent from protocol files/env/evidence |
| L1-23 | Reject MCP credential fallback | sanitized MCP startup without the run model key fails authentication |
| L1-24 | Validate per-candidate immutability | each applied structural/fixture Batch reuses identical content/client batch after validated dry-run |

## 4. Real-runtime acceptance

1. Confirm resident backend `8001`, frontend `5173`, PostgreSQL and Oxigraph health.
2. Allocate a unique loopback port, prove the exact sanitized configuration is `rdf_primary`, start
   the isolated REST runtime and verify health without modifying `8001`.
3. Bootstrap a host-only ephemeral org-admin key; prove it is absent from all Agent namespaces.
4. Run one fresh L1-S0 simulation and audit role/isolation/no-write evidence.
5. Run one fresh L1-S1 team with unique runtime, Project, Ontology and Session IDs.
6. Require each applied candidate to use identical content/client batch for validated dry-run then
   apply, with an advanced workspace and application read.
7. Require a negative dry-run to prove the version constraint rejects invalid input.
8. Require behavioral draft/latest distinction through scoped SPARQL or a generic read model.
9. Require coordinator/modeler zero MCP calls and protocol-Agent-only platform calls.
10. Require `/backend/.env` absent and MCP authentication failure when the run model key is removed.
11. Require Build Session terminal state, lease release, both key revocations and uniquely owned resource
   cleanup.
12. Stop the isolated runtime and recheck resident backend/frontend health.

Mocks may prove launcher state transitions and failure cleanup, but cannot prove MCP authorization,
workspace advancement, graph persistence, constraint behavior or runtime role isolation.

## 5. Regression commands

```bash
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l1/tests
uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l1
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests
git diff --check
```

If backend or frontend product code changes, run the full repository checks and restart rules from
`AGENTS.md`. Scenario-only/docs changes still require pre/post service health.

## 6. Cleanup

Cleanup may delete only the Project whose create receipt and unique run tag match the current run.
The host-admin key deletes it through the formal route and verifies Project `404`; the launcher then
verifies the protocol model key is revoked and self-revokes the host-admin key through the trusted
bootstrap. Both exact key records must be terminally revoked. If ownership cannot be proven, skip
Project deletion, still revoke both keys, and report the retained IDs rather than guessing.

## 7. Independent rounds

No L1 independent test round has run yet.

### Independent Round 1 — 2026-07-30 09:49 +08:00 — FAIL

**Worktree/version.** `816a2b0` plus the uncommitted R2.2-001 L1 scenario, design, requirement and
test-plan files shown by `git status --short`. This round did not modify product or scenario code;
it only appends this shared plan. The resident `ontology-platform.service` was already active.

**Executed commands and results.**

```text
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l1/tests
  Ran 11 tests in 0.008s — OK
uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l1
  All checks passed!
uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests
  Ran 21 tests in 0.025s — OK
git diff --check
  exit 0
curl --fail --silent --show-error http://127.0.0.1:8001/api/health
  {"status":"ok"}
curl --fail --silent --show-error http://127.0.0.1:5173/
  exit 0
systemctl --user --no-pager --full is-active ontology-platform.service
  active
```

The current timeout normalization unit case passes. The historical f evidence remains
`INCONCLUSIVE`: isolated mode and health passed; S0 and the S1 coordinator completed; no-key MCP
authentication was rejected; the Project and both exact temporary key records were cleaned/revoked.
Its saved error is `data must be str, not bytes`, so it did not retain the protocol timeout transcript
or prove a Batch, workspace advance, generic read, constraint, Build Session terminal state or
protocol-only MCP calls.

**Case results.**

| Cases | Result | Evidence / reason |
| --- | --- | --- |
| L1-01, L1-05, L1-13 | PASS (offline/static) | Manifest/input, candidate/dispatch and forbidden-candidate checks pass in the 11 L1 tests. |
| L1-02, L1-03, L1-19, L1-22, L1-23 | PASS (bounded evidence) | Namespace/config construction tests pass; f records `rdf_primary`, absent `/backend/.env` probe and no-key MCP rejection. This is not a substitute for successful S1 evidence. |
| L1-07, L1-17 | PASS (f timeout path only) | f records a Project-scoped model key and host-admin key both revoked and the owned Project deleted. Build Session safe closure is not applicable because none was created. |
| L1-04, L1-06, L1-15, L1-21 | FAIL | The launcher accepts S0 by checking only `no_platform_write`; it neither verifies distinct role events nor audits actual MCP callers. It also never returns the normalized protocol result to the S1 coordinator for team closure, so the launcher—not the coordinator—would close the team run. |
| L1-08 to L1-12, L1-24 | BLOCKED | f timed out before `protocol-result.json`/any Batch. No evidence exists for Session/Lease, immutable dry-run/apply, workspace advance, generic draft/latest read, negative validation, or candidate immutability. |
| L1-14, L1-16, L1-18, L1-20 | BLOCKED | No executed real acceptance scan/failure injection/publication-failure test/resident legacy-mode rejection evidence. Current unit suite does not exercise these cases. |

**Defects.**

1. **P1 — S0 violates the no-platform-resource acceptance boundary.**
   - Reproduction: read `run_l1.py:518-543`.
   - Expected: complete L1-S0 with no platform resource creation, then begin fresh S1 setup.
   - Actual: launcher starts isolated REST, bootstraps admin, then `POST`s Project and Ontology at
     lines 525-538 before executing S0 at line 543. Historical f confirms those resources existed
     during S0 (`scope` plus S0 success in `runtime/runs/l1-live-20260730f/audit/state.json`).
   - Impact: directly fails requirements-v2.2 L1-S0 condition and invalidates L1-04 as an
     acceptance proof.

2. **P1 — S1 coordinator never receives the protocol result or closes the team run.**
   - Reproduction: inspect `run_l1.py:549-579`.
   - Expected: after the separate protocol Agent reports, its normalized result returns to the same
     S1 coordinator Session, which closes the team run; the launcher remains mechanical.
   - Actual: after `execute_agent(..., "protocol", ...)` at line 572, launcher validates the file and
     sets `PASS` itself. There is no coordinator resume/closure invocation.
   - Impact: contradicts the reviewed L1 design role/process boundary and leaves L1-04/L1-06/L1-15
     without the required auditable role/result-routing evidence.

3. **P1 — Real protocol terminal state is not independently diagnosable or accepted.**
   - Reproduction: historical f runs S1 protocol until the 300-second global timeout; the saved state
     contains `data must be str, not bytes` and no protocol transcript/result. Current
     `execute_agent` has a unit-tested bytes normalization branch, but its only live control is one
     blocking `subprocess.run(... timeout=TIMEOUT_SECONDS)` with no first-response/progress/terminal
     observation.
   - Expected: preserve the actual Codex/provider terminal category and bound first response and
     terminal waits separately; a real S1 must create the required receipts or fail with a
     trustworthy runtime/infrastructure record.
   - Actual: f is inconclusive, no Batch was produced, and the underlying protocol-runtime cause is
     unavailable from the retained evidence.
   - Impact: the runtime/infrastructure cause is still external/unconfirmed, but the terminal
     observability/acceptance implementation is insufficient to classify it.

**Conclusion and residual risk.** FAIL. Offline regression and resident health pass, and f cleanup
evidence is good, but the two P1 role-flow violations are confirmed by code review and S1's required
real-write evidence is blocked by the unresolved protocol timeout. No fresh live attempt was run:
the plan permits one only on a correction-free path, which this worktree is not. A requirement
developer should correct the S0/S1 sequencing and coordinator result-routing/terminal evidence,
then an independent Round 2 should first rerun the affected failure/role cases and one fresh bounded
S1 real attempt.

### Independent Round 2 — 2026-07-30 10:31 +08:00 — PASS (manual acceptance)

**Method and scope.** Per the user decision, this is a read-only manual acceptance of the existing
`l1-i` material, not a new automated acceptance program and not a rerun. Reviewed:
`runtime/runs/l1-i/audit/{state,s0-audit,coordinator-dispatch}.json`,
`protocol-work/protocol-result.json`, coordinator/protocol transcripts and retained Codex rollout
metadata. Current resident checks were also read directly: backend health returned `{"status":"ok"}`;
frontend returned `200`; `ontology-platform.service` was `active`.

**Manual evidence and case result.**

| Cases | Result | Manual evidence |
| --- | --- | --- |
| L1-01 to L1-05 | PASS | Staged source/hash is recorded; S0 has a coordinator plus two independent child rollouts explicitly identified as `modeling_agent` and `protocol_planning_agent`; its transcript has zero ontology MCP events and `s0-audit.json` records `no_platform_write: true`. S1 coordinator produced the candidate and canonicalized dispatch. |
| L1-06 to L1-08 | PASS | S0 and S1 coordinator transcripts have zero ontology MCP events; protocol transcript has 33 MCP calls and is the sole caller. It created Build Session `87d07624-94d1-4a3e-b282-d2708a222a62`, acquired/renewed the lease, then completed it with lease state `released`. |
| L1-09, L1-10, L1-24 | PASS | Platform transcript receipts show structural Batch `0d89b822-34dc-4e4d-b100-1444a4444f5f` used the same `client_batch_id` and content hash for `dry_run: validated` then `apply_atomic: applied`, advancing `ae3d…bb72` to `c90f…acdd`. The same immutable transition occurred for the two-version instance Batch, advancing `c90f…acdd` to `d109…0038`. |
| L1-11 | PASS | Generic asserted entity read contains exactly the required distinct resources: `SyntheticReleaseWorkflow` (Workflow), `Current Draft` and `Latest Version` (Version State), plus distinct `SyntheticReleaseWorkflow Current Draft` and `SyntheticReleaseWorkflow Latest Version` (Version). The applied instance Batch binds each Version to the same Workflow and its respective different state. |
| L1-12 | PASS | Applied structural Shape has `min_count: 1` and `max_count: 1` for both Version-to-Workflow and Version-to-state properties. Negative dry-run Batch `87f8fcf6-8fbe-4d7d-b69d-01d14bc6e4cd` is `validation_failed`, `applied: false`, with a retained `shacl_violation`. |
| L1-13 to L1-15, L1-19, L1-22, L1-23 | PASS | Candidate identifies the synthetic fixture; transcripts, MCP receipts, batch IDs, state and hashes are retained. The sanitized probe is `rdf_primary`, `/backend/.env` is absent, no-key MCP authentication is rejected, and the reviewed evidence contains no configured host-path/key marker. |
| L1-07, L1-17, L1-21 | PASS | State records the Project-scoped model key `8718f0bf-d75d-4423-bafc-36046aa30028` and host-admin key `fdf80384-7504-494b-b0d8-69fffa84d1ee` as separately revoked; owned Project `0eed24b8-7e7e-4b40-8e97-6f13c0a10a69` is deleted. |
| L1-16, L1-18, L1-20 | NOT RUN (non-goal for this manual round) | No new failure-injection, audit-publication-failure or resident legacy-mode experiment was run. They are not needed to determine whether l1-i actually completed the bounded L1 semantic/write acceptance. |

**Non-blocking test-tool issue.** The saved launcher state is `INCONCLUSIVE` solely with
`S1 lacks one distinct modeling child rollout identity`. Manual rollout metadata proves the child
exists: S1 coordinator `019fb0cb-faad-7903-ae75-d3ad4fb4cd55` has child
`019fb0cc-24cb-7b60-a8d2-b610cdc5b865` with role `modeling_agent`. The automated audit incorrectly
counts the earlier S0 parent/children from the same coordinator home as S1 children. This is a P2
test-tool/accounting defect, not a business-modeling or platform-write failure. It prevented the
launcher from reaching its later automatic coordinator-closure/audit-publication path, but does not
negate the retained real S0/S1, MCP, platform receipt, semantic-read, credential-cleanup and service
health evidence reviewed above.

**Conclusion.** PASS for the user-requested manual L1 acceptance. `l1-i` is sufficient evidence of
the bounded L1 result: no-write S0 role split; protocol-Agent-only real write; governed dry-run/apply;
workspace advancement; deterministic negative rejection; and generic Current Draft/Latest Version
distinction. The P2 rollout-accounting defect remains a residual automation-maintenance item, not a
reason to reopen the accepted business slice or rerun the complete modeling task.
