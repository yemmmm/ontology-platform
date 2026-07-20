# R1.1-003 Reliable Modeling Artifact Handoff Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-003
- Status: in-progress
- Started: 2026-07-19T11:12:20+08:00
- Last updated: 2026-07-19T14:27:07+08:00
- Design:
  `docs/delivery/designs/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-design.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-test-plan.md`
- Delivery baseline: worktree at `527966a457667a2c5ddaa0fbcdef1a6c585dbcc1`;
  pre-existing R1.2-002 record/design/test-plan changes are unrelated and excluded
- Delivery commit: `Refine reliable modeling artifact handoff requirement`; resolve the immutable
  hash with `git log -- docs/delivery/records/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-delivery-record.md`

## Confirmed contract

- Current behavior: the platform persists immutable, Build Session-scoped Modeling Workflow
  Artifacts through REST/MCP with content hashes, idempotency, version succession, and a 1 MiB
  inline-content limit. A modeling subagent still has no reliable large structured-output handoff
  channel independent of PTY, chat, or rollout text.
- Target behavior: a modeling subagent writes its complete structured result to a controlled,
  addressable, integrity-verifiable channel and returns only a bounded manifest; the main agent
  validates and persists the exact result before dry-run, review, lease, or apply, and a replacement
  agent can resume accurately after interruption.
- In scope: atomic publication, bounded handoff manifest, size/hash/schema/reference validation,
  explicit generation/handoff/validation states, interruption recovery, failure-closed behavior,
  secret/permission controls, and a Dify end-to-end rerun using at least the prior 27-item scale.
- Non-goals: granting subagents Ontology Lease/apply authority, relying on PTY/chat/rollout recovery,
  building a general Agent runtime or orchestration engine, implementing a general source crawler,
  or treating the Dify corpus as a permanent mirror of current official documentation.
- Acceptance summary: terminal truncation cannot lose the artifact; two specified interruption
  points resume without regeneration or duplicate Batch/review; corrupt or invalid artifacts do
  not reach dry-run/apply; lineage across Draft, Batch, Attempt, Review, and events remains stable;
  the fixed Dify corpus completes the R1.1-004 integration rerun after this capability lands.
- Refinement: user-confirmed contract frozen on 2026-07-19. The first version uses a
  Runtime-controlled atomic file and bounded manifest, then main-agent validation and platform
  persistence; platform authority, immutable correction, two-round retry, lifecycle, one-MiB
  scope, Codex-only first implementation, CAS concurrency, and cross-requirement completion gates
  are confirmed below.

## Timeline

### 2026-07-19T11:12:20+08:00 — source and current-state audit — main agent

- Context: the user requested refinement of the next v1.1 requirement.
- Action/decision: selected R1.1-003 because the authoritative v1.1 document explicitly marks it
  as the next major unmet requirement; treated R1.1-002 as delivered and R1.1-004 as a delivered
  corpus awaiting post-R1.1-003 integration rerun.
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-003; GitNexus process
  `Create_modeling_workflow_artifact -> _scan_string`; `backend/app/services/modeling_workflow.py`;
  `git status --porcelain=v1`; HEAD `527966a457667a2c5ddaa0fbcdef1a6c585dbcc1`.
- Outcome/next step: refine the first-version handoff channel and authority boundary with the user
  before writing a design or implementation plan.

### 2026-07-19T11:27:44+08:00 — refinement decision 1 — user and main agent

- Context: the first-version handoff channel determines whether subagents require platform
  credentials and whether large payloads remain coupled to terminal output.
- Action/decision: the user confirmed one supported first-version path: the modeling subagent
  atomically publishes the complete JSON in a Runtime-controlled workspace and returns only a
  bounded manifest. The authorized main agent rereads and validates the exact file before
  persisting it as a Modeling Workflow Artifact.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: subagents receive no platform credential, Ontology Lease, or apply authority;
  next refine the authoritative recovery source before and after platform persistence.

### 2026-07-19T11:36:41+08:00 — refinement decision 2 — user and main agent

- Context: interruption recovery requires an unambiguous authority boundary between the
  Runtime-controlled file and the platform's immutable Artifact.
- Action/decision: the user confirmed that the atomic file plus bounded manifest is the temporary
  recovery source only before platform persistence. After Artifact creation and its success event,
  the platform Artifact is the sole authoritative content and the local payload may be cleaned.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: a replacement agent first reads platform state and only consumes the local
  file when the recorded phase is generated-but-not-persisted; next refine failure and correction
  semantics.

### 2026-07-19T11:46:05+08:00 — refinement decision 3 — user and main agent

- Context: a correction round must be reproducible even when the original modeler context no
  longer exists, without forcing a replacement modeler to rediscover the whole task.
- Action/decision: the user confirmed that each correction uses a fresh clean context with an
  explicit complete handoff: the original business artifacts, current Modeling Context, exact
  previous draft, schema/version contract, structured validation findings, and bounded correction
  scope. Reusing a surviving modeler context is an optional optimization only.
- Evidence: user question and confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: the main agent must not patch model content; a correction produces a new
  immutable generation and supersedes relationship. Next refine the automatic retry/blocking
  boundary.

### 2026-07-19T11:48:51+08:00 — refinement decision 4 — user and main agent

- Context: unbounded automatic correction can consume excessive model budget and create divergent
  immutable versions without resolving a repeated contract failure.
- Action/decision: the user confirmed a maximum of two automatic correction rounds within one
  validation or review stage. Each round creates a new immutable version and records the failure
  and delta; success continues the workflow.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: after two failures, or an earlier repeated same-class failure, append a
  blocked event and stop model calls, dry-run, lease, and apply until the user supplies information
  or explicitly authorizes continuation. Next refine controlled-file retention and cleanup.

### 2026-07-19T11:59:24+08:00 — refinement decision 5 — user and main agent

- Context: local payloads must survive the two required interruption points without becoming an
  indefinite, untracked second artifact store.
- Action/decision: the user confirmed a Build Session-scoped, gitignored runtime area. Keep the
  complete file until the platform Artifact and success event are durable; then delete it and keep
  only the bounded manifest, hash, and platform ID. Keep a validation-failed file only until its
  replacement is durable or the Session terminates, then clean it.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: secret/token/Authorization detection deletes the original immediately and
  records only a redacted blocker; recovery or periodic cleanup removes crash leftovers. Next
  refine which artifact kinds the first version supports.

### 2026-07-19T12:01:11+08:00 — refinement decision 6 — user and main agent

- Context: making every workflow artifact a large-file concern would expand a reproduced modeler
  handoff defect into a general upload and file-management platform.
- Action/decision: the user confirmed that the first version supports only the modeling subagent's
  complete seven-field Modeling Draft / Modeling Batch candidate JSON. Business Knowledge Pack,
  Coverage Matrix, Review Report, and other artifacts continue through existing Artifact APIs.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: internal atomic-publication and manifest helpers may be reusable, but this
  requirement adds no generic upload, user file-management, or frontend file surface. The
  R1.1-004 fixed Dify corpus is the integration input. Next refine automatic recovery behavior.

### 2026-07-19T12:06:14+08:00 — refinement decision 7 — user and main agent

- Context: normal process interruption should not force regeneration or user involvement when
  durable state already identifies one safe next action.
- Action/decision: the user confirmed idempotent automatic recovery keyed by stable generation ID
  and content hash. A replacement agent detects generated, validated, Artifact-persisted, Batch,
  dry-run, review, and rework stages and continues the first missing safe step without asking.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: generation/hash disagreement, state-chain conflict, missing file, failed
  validation, semantic change, or potentially duplicated charged action fails closed and asks the
  user; ordinary technical recovery does not. Next refine the accepted payload-size boundary.

### 2026-07-19T12:07:27+08:00 — refinement decision 8 — user and main agent

- Context: the existing platform accepts at most 1 MiB of canonical content per Modeling Workflow
  Artifact; changing that boundary would add object storage, chunking, or persistence concerns to
  a terminal-handoff defect.
- Action/decision: the user confirmed the existing 1 MiB single-artifact limit for the first
  version. Canonical UTF-8 JSON size is checked without truncation; oversized drafts fail closed
  and require a smaller vertical slice rather than automatic splitting or a raised limit.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: a risk probe must prove the representative Dify draft of at least 27 items is
  comfortably within the limit; otherwise the design is blocked for explicit reconsideration.

### 2026-07-19T12:14:04+08:00 — refinement decision 9 — user and main agent

- Context: implementing several runtime adapters would broaden the first repair without improving
  the reproduced Codex handoff failure.
- Action/decision: the user confirmed a runtime-neutral manifest, atomic-publication, integrity,
  and recovery contract, with first-version implementation and acceptance limited to the current
  Codex subagent path, ontology-builder Skill, and repo-local Harness.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: the platform does not host or launch an Agent Runtime, and no Claude Code or
  OpenCode adapter is required. Next refine concurrent generation conflict behavior.

### 2026-07-19T12:14:55+08:00 — refinement decision 10 — user and main agent

- Context: two modelers publishing successors for the same logical draft can create divergent
  validation, review, and Batch chains.
- Action/decision: the user confirmed one active generation chain per Build Session, artifact key,
  and modeling stage, guarded by expected previous generation CAS. Different Ontologies or artifact
  keys may proceed concurrently.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: a losing concurrent generation records generation_conflict and cannot
  overwrite, merge, persist, or create a Batch. Selecting it later requires an explicit new
  version. Next confirm completion-gate ownership across R1.1-003, R1.1-004, and R1.1-001.

### 2026-07-19T12:17:01+08:00 — refinement decision 11 and contract freeze — user and main agent

- Context: R1.1-003, R1.1-004, and R1.1-001 need distinct completion claims so a reliable transport
  is not mistaken for repeatable modeling quality.
- Action/decision: the user confirmed that R1.1-003 requires the fixed R1.1-004 Dify corpus to pass
  Draft handoff/recovery, dry-run, independent review and rework, main-agent apply, competency
  queries, validation, lineage, and Build Session completion. The same run may close R1.1-004's
  remaining integration gate. Repeatable business-value improvement remains R1.1-001.
- Evidence: user confirmation in the R1.1-003 refinement conversation.
- Outcome/next step: collaborative functional refinement is complete. Synchronize the frozen
  contract into the requirement source; design, risk probes, test plan, plan review, implementation,
  and independent testing remain future delivery phases until requested.

### 2026-07-19T12:18:19+08:00 — requirement sync and refinement verification — main agent

- Context: the request is refinement-only; product design and implementation are not authorized by
  this scope. An unrelated R1.2-002 workflow committed its pre-existing files as `dd81f9e` while
  this refinement was in progress, advancing HEAD without changing the R1.1-003 files.
- Action/decision: synchronized all eleven confirmed decisions into the authoritative R1.1-003
  section and kept this record in-progress for future design and delivery phases.
- Evidence: `git diff --check -- docs/requirements/requirements-v1.1.md
  docs/delivery/records/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-delivery-record.md`
  exited 0; GitNexus detect_changes reported low risk, zero affected execution processes; current
  uncommitted scope contains only the requirement and this record.
- Outcome/next step: commit the isolated refinement artifacts. Risk probes, shared design/test
  plan, mandatory plan review, delegated development, independent testing, runtime restart, and
  R1.1-003/R1.1-004 closeout remain pending a future implementation request.

### 2026-07-19T12:26:35+08:00 — implementation authorization and risk probes — main agent

- Context: the user explicitly requested completion of the remaining requirement-delivery phases.
- Action/decision: resumed at commit `2de5ec7` and probed the three assumptions most likely to
  invalidate the frozen contract: representative payload size, real Codex file/manifest handoff,
  and platform-side linear/idempotent concurrency.
- Evidence: live PostgreSQL contains two 32-item Dify drafts of 32,422 and 32,433 canonical bytes,
  leaving 96.91% headroom under 1 MiB. An isolated real `codex exec --ephemeral` created an
  atomically published 42,227-byte/40-item JSON with matching SHA-256, byte count, and item count,
  while its final manifest was 163 bytes and the temporary file was absent. Focused service tests
  returned `2 passed`; the opt-in real PostgreSQL concurrency test returned `1 passed` with
  `RUN_POSTGRES_CONCURRENCY_TESTS=1`.
- Outcome/next step: all probes support the frozen contract. Reuse the current platform Artifact
  CAS and event/checkpoint facts; implement the missing Codex-controlled spool, bounded manifest,
  validation/recovery, lifecycle, and Skill/Harness integration without a new general upload API.

### 2026-07-19T12:30:42+08:00 — design and shared test plan freeze — main agent

- Context: the three probes removed the storage-size, Runtime-output, and platform-CAS unknowns.
- Action/decision: froze one functional design and one shared test plan. The design uses a
  gitignored Build Session/artifact/generation spool, fresh ephemeral Codex with
  output-last-message redirected to a temporary file, trusted validation plus atomic publication,
  a bounded manifest/state machine, local head CAS, existing platform Artifact CAS, platform-first
  recovery, two-round rework, and terminal cleanup. It adds no general upload API, migration, or UI.
- Evidence:
  `docs/delivery/designs/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-design.md`;
  `docs/delivery/test-plans/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-test-plan.md`;
  Harness baseline `20 tests OK`; Skill structure validation passed; `git diff --check` passed.
  Direct host execution of `run_evals.py` lacked `jsonschema`, so the reviewed required command
  is the backend uv environment where the dependency exists.
- Outcome/next step: send the exact frozen requirement/design/test plan and repository constraints
  to the mandatory plan reviewer. No implementation starts before PASS or accepted-high repair.

### 2026-07-19T12:36:30+08:00 — plan review round 1 and revision — plan reviewer and main agent

- Context: the independent reviewer returned REVISE with three evidence-backed High findings.
- Action/decision: the main agent verified and accepted all three. The revised design now covers
  runner death with complete temp output or post-rename/pre-state output, live-child identity and
  conflict handling; freezes the dry-run-to-apply envelope while preserving one immutable Batch
  content hash; and maps generated/validated/persisted/blocked to stable Event/Checkpoint IDs,
  payloads, locators, and next steps including retroactive recovery recording.
- Evidence: Codex output-last-message behavior; modeling batch request hash and immutable content
  construction; existing Build Checkpoint/Event schemas; revised design generation, recovery,
  exact apply, and platform-recording sections; revised test-plan D/F/I sections.
- Outcome/next step: return the changed plan to the same reviewer. No developer handoff until PASS.

### 2026-07-19T12:38:52+08:00 — plan review round 2 and revision — plan reviewer and main agent

- Context: Round 2 confirmed the apply-envelope and Event/Checkpoint findings resolved, but found
  one remaining High: a replacement runner cannot infer a dead Codex child's exit code from PID
  identity and a complete-looking temp file.
- Action/decision: accepted-high. Added a minimal detached supervisor that waits for Codex and
  atomically persists trusted owner-only process status. Recovery publishes only with matching
  durable exit-zero evidence; non-zero, signal, missing, invalid, or mismatched status fails closed
  without rerun. Aligned success/non-zero/unknown-status crash tests and publication wording.
- Evidence: revised design controlled-spool, running recovery, state/failpoint, and error sections;
  revised test-plan B/D sections.
- Outcome/next step: return the second revision to the reviewer. Development remains gated.

### 2026-07-19T12:39:58+08:00 — plan review round 3 PASS — plan reviewer and main agent

- Context: the reviewer rechecked the durable supervisor, state/failpoint ordering, exact apply,
  and platform recovery-record revisions against the repository.
- Action/decision: reviewer returned PASS with no remaining evidence-backed Critical/High issue.
  The main agent freezes the reviewed design/test scope for development.
- Evidence: plan reviewer Round 3; `git diff --check` passed; design marked reviewed PASS.
- Outcome/next step: commit the reviewed planning baseline, then hand the exact requirement,
  design, shared test plan, delivery record, constraints, and verification commands to the
  requirement developer. Developer must not edit this record or commit.

### 2026-07-19T13:07:51+08:00 — development cycle 1 ready — requirement developer and main agent

- Context: developer implemented the reviewed plan from stable baseline `c4a6157`, did not edit
  this record, did not commit, and stopped writing after an explicit DEVELOPMENT_READY signal.
- Action/decision: added the repo-local controlled handoff runner and 17 focused tests; integrated
  bounded/redacted Harness outcomes, Skill routing/reference, and eval traces. No backend, REST,
  MCP, database, migration, frontend, or platform Runtime code changed. Self-review fixed supervisor
  argument ordering, system-Python schema dependency, duplicate-key/NaN parsing, and cleanup/CAS
  crash/lock races.
- Evidence: final `.codex` suite `38 passed`; Skill validator `10 references / 34 MCP dependencies`;
  Skill evals `7 cases`; backend focused `74 passed`; real PostgreSQL concurrency `2 passed`;
  backend full `729 passed, 6 skipped, 166 warnings in 71.04s`; changed-Python Ruff/format and
  `git diff --check` passed; GitNexus LOW/0 affected processes, with hidden `handle_hook` reported
  UNKNOWN/not indexed rather than HIGH. Main-agent diff inspection confirmed exactly ten product/
  Skill/Harness files and no delivery-record edit by developer.
- Outcome/next step: stable independent-test baseline is `c4a6157` plus implementation file-set
  digest `96d00401cac9017bde1f8f200a125f28161cf64a57df5b0f8561622d56cca964`.
  Deferred to independent test/closeout: real production Codex run, fixed-corpus 27+ platform run,
  Event/Checkpoint runtime assertions, service restart/health, and terminal cleanup.

### 2026-07-19T14:18:42+08:00 — independent test round 1 FAIL and containment — requirement tester and main agent

- Context: tester independently passed direct regressions, real Codex handoff/recovery, Artifact,
  and dry-run gates, then observed the real detached supervisor during a long correction run.
- Action/decision: accepted-high product defect. Supervisor wrote unbounded, unredacted Codex stderr
  to `.diagnostic.tmp` while live and scanned only the final 2 KiB after normal exit. Real v1 reached
  93,436 bytes; v2 contained the full prompt. This violates the reviewed no-prompt/no-hidden-
  reasoning/no-secret local-file contract, so tester stopped before Lease/apply.
- Evidence: shared test plan Round 1; `.codex/modeling_handoff.py` supervisor stderr path; real spool
  file size/content-category inspection without echoing content. Passed evidence: 38 direct/Harness,
  32-file corpus plus 24 tests, 7 Skill evals, Ruff/format, PostgreSQL concurrency, fresh Codex
  32-item/42,342-byte handoff, both interruption recoveries, exact Artifact hash, stable
  Event/Checkpoint facts, and canonical dry-run 32 items/0 Findings.
- Outcome/next step: tester terminated only the uniquely identified idle test process group, read no
  partial output, deleted diagnostic/temp inputs, removed two local generations, restored
  `legacy_only`, and verified service/backend/frontend health. Platform Project/Session and
  immutable BLOCKED review history remain for repair/retest. Send High defect to developer; Round 2
  must prove bounded in-memory/redacted diagnostics during live/crash states before resuming apply.

### 2026-07-19T14:27:07+08:00 — repair cycle 2 ready and GitNexus disposition — requirement developer and main agent

- Context: developer reproduced the Round 1 High and repaired only the supervisor diagnostic path.
- Action/decision: removed all raw stderr files. A drain thread now continuously consumes PIPE
  stderr into a constant-memory accumulator with at most 4 KiB scan overlap; durable status stores
  only byte count, booleans, and named secret categories. Live, nonzero, normal, and supervisor-
  crash paths persist no prompt, stderr, matched token, hidden reasoning, or raw diagnostic.
- Evidence: focused `20 passed`; full `.codex` `41 passed`; Skill validator/evals PASS; backend
  focused `74 passed`; PostgreSQL concurrency `2 passed`; Ruff/format/diff PASS. Added >200/250 KiB
  live/nonzero/crash stderr, split-secret, bounded status, and no-file regressions. No spool residue.
- Outcome/next step: repair stable state is `c4a6157` plus implementation digest
  `a1bef6ff4a79f3e712cece4bef7b3b68f146eb0406da61691dc45a24fe47dab8`.
  GitNexus final detect reported CRITICAL/52, but every affected process attributed the Skill
  Markdown section name `Reference map` as a changed code step in unrelated frontend/backend flows;
  no product-code file or indexed product symbol changed, while hidden `.codex` remains unindexed.
  Main agent rejects/downgrades this as evidence-backed graph name-collision false positive and
  preserves the warning here. Return the stable repair to the same independent tester for Round 2.

### 2026-07-19T15:56:29+08:00 — independent test round 2 FAIL and containment — requirement tester and main agent

- Context: tester first reproduced the repaired diagnostic contract, independently passed the
  full regression suites, and resumed the retained Build Session with one fresh correction
  generation. During the live run it inspected the process boundary rather than any partial model
  output.
- Action/decision: accepted-high product defect. The runner invoked `codex exec` without the
  supported `--ignore-user-config` flag and retained the user configuration location, so Codex
  loaded global MCP configuration. Its process tree started the ontology MCP with the environment
  variable name `ONTOLOGY_MCP_API_KEY`. A read-only filesystem sandbox does not constrain external
  MCP tools; therefore the supposedly credential-free Modeler had a platform-capable channel.
- Evidence: shared test plan Round 2; live supervisor/Codex/MCP parent-child tree; variable-name-only
  inspection (no value read); `codex exec --help` confirms `--ignore-user-config`. Before the High,
  independent checks passed: backend `729 passed, 6 skipped`; real PostgreSQL concurrency `2
  passed`; `.codex` `41 passed`; Skill validator `10 references / 34 MCP dependencies`; seven Skill
  evals; fixed corpus 32-file verification and `24 passed`; Ruff, format, and diff checks.
- Outcome/next step: tester sent SIGTERM only to the unique Codex process group; supervisor,
  code-mode host, and MCP children exited without SIGKILL. No partial draft was read or reused;
  inspection failed closed as `handoff_file_missing`, and session cleanup removed exactly one local
  generation. Platform state remains six Artifacts, one Batch, eight Events, four Checkpoints, with
  no new write, Lease, or apply; service/backend/frontend remain healthy in `legacy_only`. Repair
  must isolate user configuration and platform/MCP credential categories while preserving only the
  minimum Codex authentication/proxy environment, then restart independent testing in Round 3.

### 2026-07-19T16:03:00+08:00 — repair cycle 3 ready — requirement developer and main agent

- Context: developer repaired only the credential/configuration boundary exposed by Round 2 and
  stopped writing without editing the shared test plan or this record.
- Action/decision: `codex exec` now always receives `--ignore-user-config`; the child environment
  is built from a positive allowlist backed by category denial for platform, MCP, API key, token,
  authorization, cookie, Lease, password, secret, and credential names. Credential-bearing proxy
  URLs are rejected. `HOME`/`CODEX_HOME` remain solely for file-backed Codex authentication, which
  the CLI documents as independent from ignored user configuration. Explicit empty source input no
  longer falls back to the real process environment.
- Evidence: a black-box supervisor/fake-Codex test supplies a malicious user config declaring an
  ontology MCP, captures actual argv/environment, and proves the ignore flag, absent MCP loading,
  visible file auth, absent credential categories, and credential-free proxy behavior. Focused
  handoff `21 passed`; full `.codex` `42 passed`; Skill validator/evals PASS; backend workflow/API/
  MCP focused `15 passed`; Ruff, format, and diff checks PASS. GitNexus reports UNKNOWN/zero indexed
  dependents because the hidden `.codex` supervisor is not indexed.
- Outcome/next step: stable implementation digest is
  `eb0e05e72533f8a59f9870e0e3750660aec420f4805b8105051958db12f0f859`. Round 3 must use the
  production Codex binary and inspect the live process tree/environment-category boundary before
  accepting a result, then resume the retained platform workflow only if no global MCP is started.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | Temp-output crash window contradicted generated/validated ordering | accepted-high | Codex output-last-message and original design/test ordering | Added running/temp/final recovery, process identity, four crash failpoints, aligned states/tests |
| 1 | Dry-run envelope could not become exact valid apply | accepted-high | modeler schema; modeling batch request/content hashes | Froze fresh apply Attempt envelope and same immutable Batch/hash assertions |
| 1 | Generation/handoff/validation platform recording unspecified | accepted-high | R1.1-003 contract; checkpoint/event schemas | Added stable Event/Checkpoint mapping, payloads, next steps, and retroactive recovery tests |
| 2 | Dead child plus temp file did not prove successful Codex exit | accepted-high | runner cannot recover reaped-process exit code | Added detached supervisor, durable exit status, fail-closed unknown/non-zero handling and crash tests |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | `c4a6157` + digest `96d00401...a964` | Implemented controlled spool/supervisor/manifest/recovery/CAS/lifecycle plus Skill/Harness integration; self-review fixed four local issues | 38 `.codex`; 7 eval; 74 focused; 729 backend; 2 PostgreSQL; Ruff/diff | DEVELOPMENT_READY; independent runtime/Dify gates pending |
| Repair 1 | Round 1 FAIL baseline | High: live supervisor persisted unbounded/unredacted stderr prompt in `.diagnostic.tmp` | Real v1/v2 diagnostic evidence; no partial output read | Assigned for root-cause repair |
| 2 | `c4a6157` + digest `a1bef6ff...dab8` | Replaced raw diagnostic file with bounded in-memory streaming classifier | 20 focused; 41 `.codex`; Skill/eval; 74 focused; 2 PostgreSQL; Ruff/diff | DEVELOPMENT_READY for Round 2 |
| 3 | `c4a6157` + digest `eb0e05e...f859` | Ignored global user config and restricted the child to a credential-free allowlisted environment | 21 focused; 42 `.codex`; Skill/eval; 15 backend focused; Ruff/format/diff | DEVELOPMENT_READY for Round 3 production-boundary retest |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 | `c4a6157` + digest `96d00401...a964` | FAIL | High unbounded/unredacted live stderr file; apply/query/validation/lineage/completion not executed | Shared test plan Round 1; real Codex 32-item recovery/Artifact/dry-run passed; containment complete |
| 2 | `c4a6157` + digest `a1bef6ff...dab8` | FAIL | High global Codex config loaded a credentialed ontology MCP; correction persistence and all later gates not executed | Shared test plan Round 2; full independent regressions passed; unique process-group containment complete |

## Final verification

- Required checks: pending reviewed design and shared test plan
- Runtime/restart health: pending
- Documentation/status sync: pending
- Cleanup: pending
- Residual risks and follow-ups: pending refinement

## Retrospective

- Scope or design deviations: pending
- Rework and root causes: pending
- What shortened or delayed delivery: pending
- Reusable lessons: pending
