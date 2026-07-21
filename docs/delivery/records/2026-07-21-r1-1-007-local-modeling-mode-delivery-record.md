# R1.1-007 本地/正式建模执行 Profile Delivery Record

- Requirement source: `docs/requirements/requirements-v1.1.md` R1.1-007
- Status: in-progress (refinement complete; design and implementation pending)
- Started: 2026-07-21T20:33:39+08:00
- Last updated: 2026-07-21T22:57:40+08:00
- Design: pending later refinement
- Shared test plan: pending later refinement
- Delivery baseline: `e7c4dd4`; unrelated in-progress R1.1-005/R1.1-006 changes are preserved
- Delivery commit: pending

## Confirmed contract

- Current behavior: simple-first is documented, but the executable modeling path can still require
  the complete productization workflow.
- Target behavior: provide a Local Modeling Mode that keeps repo-local collaboration and platform
  quality gates while removing productization mechanisms from the default critical path; the
  modeling workflow itself remains unchanged.
- In scope: the execution-profile boundary for productization capabilities and a later local entry
  point that preserves the same modeling activities.
- Non-goals: local Ontology storage, direct platform bypass, capability deletion, or a generic
  feature-flag framework.
- Acceptance summary: complete the unchanged modeling workflow and its quality gates without making
  authentication management, version history, audit records, or similar productization features
  completion prerequisites; no quantitative comparison with the full profile is required. The
  local Harness process record remains enabled for modeling-process optimization and is not
  classified as an audit feature or a requirement of formal modeling mode.
- Refinement: the user confirmed the core direction and requested only the necessary requirement
  information now. Ordinary modeling and local optimization use Local Modeling Mode by default;
  formal delivery, strict evaluation, complete recording, or full-chain acceptance select the full
  workflow. An Agent may recommend that switch but must not perform it silently. Remaining manual
  approval gates and acceptance thresholds are confirmed. Local Modeling Mode remains
  a continuous, multi-round business conversation: the modeling Agent actively confirms facts,
  terminology, boundaries, exceptions, and competency questions throughout modeling. The main
  modeling Agent is the sole user-facing interlocutor. A worker or reviewer Agent that needs an
  answer stops and returns the question directly to the main Agent; the main Agent either answers
  from already confirmed context or consults the user first. When business descriptions change,
  the main Agent identifies and informs affected subagents, which assess whether to keep, modify,
  or rebuild their existing modeling results.

## Timeline

### 2026-07-21T20:33:39+08:00 — requirement seed — user and main agent

- Context: R1.1-005 simplifies evaluation startup and R1.1-006 provides shared collaboration state,
  but neither establishes one repository-wide lightweight modeling execution contract.
- Action/decision: add R1.1-007 for a Local Modeling Mode; productization mechanisms are not default
  gates, while reviewed platform dry-run/apply and semantic retrieval verification remain.
- Evidence: `AGENTS.md`; `docs/requirements/requirements-v1.1.md`; `skills/ontology-builder/SKILL.md`.
- Outcome/next step: pause before design, test planning, plan review, or implementation until the
  user continues requirement refinement.

### 2026-07-21T21:05:50+08:00 — source and current-state audit — main agent

- Context: refinement resumed while R1.1-005/R1.1-006 worktree changes remain uncommitted and must
  be preserved as the delivery baseline.
- Action/decision: treat R1.1-006 as the shared-directory and quality-gate data contract; treat the
  R1.1-005 fast-local launcher as an evaluation entry rather than the ordinary modeling entry.
  R1.1-007 must define the execution-profile selection contract instead of adding another state
  store or duplicating those two requirements.
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-006/R1.1-007;
  `docs/delivery/designs/2026-07-21-r1-1-006-lightweight-shared-modeling-directory-design.md`;
  `skills/ontology-builder/SKILL.md`; `.codex/fast_local_launcher.py`; `git status --short --branch`.
  GitNexus reported its index nine commits behind; refresh was not performed because its runner
  required an unplanned package installation, so current files remain authoritative.
- Outcome/next step: confirm when Local Modeling Mode is selected by default and which user intent
  selects the existing full workflow before refining retained steps and quantitative acceptance.

### 2026-07-21T21:17:26+08:00 — refinement decision 1 — user and main agent

- Context: the requirement needed a deterministic choice between the lightweight daily path and
  the existing full productization/evaluation path.
- Action/decision: default ordinary modeling and Prompt/model/slicing optimization to Local
  Modeling Mode without an extra option. Explicit formal-delivery, strict-evaluation,
  complete-recording, or full-chain-acceptance intent selects the full workflow. The Agent may
  recommend switching modes with a reason but cannot switch silently.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: define which human confirmation points remain mandatory in Local Modeling
  Mode.

### 2026-07-21T21:23:37+08:00 — refinement clarification 2 — user and main agent

- Context: "mandatory confirmation points" could be misread as the only moments when the Agent may
  speak with the user.
- Action/decision: distinguish procedural approval gates from business conversation. Local
  Modeling Mode removes repeated mechanical approvals, but the whole modeling process remains an
  interactive interview. The modeling Agent must proactively conduct multiple rounds with the user
  to confirm business facts, terminology, scope, exceptions, priorities, and competency questions;
  interaction is not limited to blockers or failures.
- Evidence: user clarification in the R1.1-007 refinement conversation.
- Outcome/next step: confirm whether one coordinating modeling Agent is the sole user-facing
  interlocutor or whether worker/reviewer Agents may question the user directly.

### 2026-07-21T21:43:45+08:00 — refinement decision 3 — user and main agent

- Context: multi-Agent execution needs one clear user-conversation owner without suppressing
  questions discovered by workers or reviewers.
- Action/decision: the main modeling Agent is the only Agent that talks directly with the user.
  Worker and reviewer Agents write questions and uncertainties to the shared directory; the main
  Agent consolidates and deduplicates them, asks the user, and propagates the answers back to the
  affected Work Units.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: define how changed business answers invalidate already produced modeling
  results, reviews, and Batch plans.

### 2026-07-21T21:58:45+08:00 — refinement correction 4 — user and main agent

- Context: the previous decision incorrectly made the shared directory a mailbox for subagent
  questions and proposed automatic Work Unit invalidation after business changes.
- Action/decision: supersede those details. A subagent stops when it needs clarification and
  returns the question directly to the main Agent without first persisting it in the shared
  directory. The main Agent answers from confirmed context when possible; otherwise it asks the
  user and then returns the answer to the subagent. When the user's business description changes,
  the main Agent determines which subagents may be affected and sends each the change. Each affected
  subagent evaluates whether no change, an edit to existing modeling, or full remodeling is needed.
- Evidence: user correction in the R1.1-007 refinement conversation.
- Outcome/next step: confirm who owns the final decision to accept affected subagent assessments
  and invalidate downstream review or Batch artifacts when semantic content changes.

### 2026-07-21T22:04:57+08:00 — refinement decision 5 — user and main agent

- Context: affected subagents can best assess their own Work Units, but downstream merge and
  quality gates need one accountable coordinator.
- Action/decision: each affected subagent returns `no_change`, `modify_existing`, or `remodel` with
  its reason. The main Agent does not replace the subagent's detailed modeling judgment, but owns
  impact consolidation, acceptance of the assessments, and the decision to proceed. Unchanged
  semantic content may reuse its candidate/review/Batch plan; changed merged semantic content
  invalidates the old review and Batch plan and requires a new review and dry-run.
- Evidence: user acceptance in the R1.1-007 refinement conversation.
- Outcome/next step: define how a business change is corrected after the old semantic result has
  already been applied to the platform.

### 2026-07-21T22:10:27+08:00 — refinement decision 6 — user and main agent

- Context: a later business change may affect semantic content that is already part of platform
  current state.
- Action/decision: do not automatically roll back or replay the old Batch. The main Agent reads the
  current platform semantic state and sends it with the business change to affected subagents.
  They produce an incremental corrective candidate with additions, modifications, or deletions as
  needed. The correction receives a new independent review, dry-run, and apply, followed by
  verification of affected and dependent competency questions and retrieval queries. Deletion,
  irreversible impact, or unclear blast radius requires consulting the user before apply.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: quantify workflow-overhead reduction without treating necessary multi-round
  business conversation as overhead.

### 2026-07-21T22:17:39+08:00 — refinement correction 7 — user and main agent

- Context: the proposed acceptance threshold incorrectly treated Local Modeling Mode as a shorter
  modeling workflow and introduced a percentage comparison with the full workflow.
- Action/decision: supersede that interpretation. Business interview, source analysis, work
  splitting, subagent modeling, merge, independent review, platform dry-run/apply, competency
  questions, and retrieval verification do not change. Only productization capabilities such as
  authentication management, versioning, audit records, checkpoints, Harness records, and related
  governance features are removed from the default completion path. Do not require quantitative
  comparison between Local Modeling Mode and the full profile.
- Evidence: user correction in the R1.1-007 refinement conversation.
- Outcome/next step: confirm whether platform-enforced write contracts are bypassed or merely hidden
  from the modeling Agent and handled automatically by the local integration.

### 2026-07-21T22:22:16+08:00 — refinement correction 8 — user and main agent

- Context: Harness recording had been grouped with audit and other productization mechanisms that
  Local Modeling Mode should omit.
- Action/decision: reclassify the Harness. Its modeling-process record is retained in Local Modeling
  Mode because it supplies evidence for continuous optimization of the Skill, prompts, role
  collaboration, and workflow. It is not an audit feature. Formal modeling mode does not require
  the local Harness record. Other platform-enforced write contracts remain candidates for automatic
  handling rather than bypass; exact Harness failure behavior remains to be confirmed.
- Evidence: user clarification in the R1.1-007 refinement conversation.
- Outcome/next step: confirm whether Local Modeling Mode blocks when Harness recording cannot be
  established or continues with an explicit missing-record marker.

### 2026-07-21T22:23:17+08:00 — refinement decision 9 — user and main agent

- Context: Local Modeling Mode needs Harness evidence for later process optimization without making
  a local recording outage an implicit or invisible failure mode.
- Action/decision: attempt Harness activation by default. If activation fails, pause and tell the
  user rather than silently continuing. The user may repair/retry or explicitly continue without a
  recording; the latter marks the run `recording_unavailable`, allows modeling-result acceptance,
  and excludes the run as a complete process-optimization sample. A mid-run recording interruption
  follows the same rule at a safe stopping point.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: finish the boundary for automatically satisfying platform-enforced write
  contracts without exposing productization orchestration to the modeling Agent.

### 2026-07-21T22:26:09+08:00 — refinement decision 10 — user and main agent

- Context: Local Modeling Mode must use the existing protected platform write path without making
  credentials or concurrency contracts part of the modeling Agent's working context.
- Action/decision: use configured credentials and stop with a redacted configuration/authentication
  error when they are missing or invalid; do not add an unauthenticated write path. The local tool
  automatically handles Build Session, Lease, current workspace version, idempotency, and Batch
  capacity. It does not add version history, audit chains, or permission-management features.
  Harness remains the sole retained local process record for workflow optimization.
- Evidence: user confirmation and follow-up question in the R1.1-007 refinement conversation.
- Outcome/next step: credentials are provisioned once outside the Agent context. The launcher/tool
  reads and uses them; no credential value enters Agent prompts, subagent handoffs, the shared
  directory, Harness records, or user-visible errors. Refine the useful and safe Harness capture
  boundary next.

### 2026-07-21T22:29:14+08:00 — refinement decision 11 — user and main agent

- Context: the retained Harness record must be useful for process optimization without becoming a
  hidden-reasoning archive, credential store, or duplicate store for large modeling payloads.
- Action/decision: capture visible user/main-Agent dialogue; main-Agent/subagent questions, answers,
  pauses, and resumes; phase transitions; bounded tool outcomes; review/rework; and final
  verification. Never capture hidden reasoning or credentials. Full source bodies, large candidates,
  and Batch payloads remain outside the record and are referenced by path, content hash, and bounded
  summary. Raw records remain in the gitignored local workspace and do not publish a retrospective
  by default.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: choose one shared modeling-workflow implementation with execution profiles or
  two independently maintained Skills.

### 2026-07-21T22:37:43+08:00 — refinement decision 12 — user and main agent

- Context: local and formal modes submit different envelopes and omit different infrastructure
  steps, but both ultimately produce platform `ModelingItemInput` items and use the same modeling
  method and quality gates.
- Action/decision: keep one shared modeling core and define separate local/formal Profile,
  Schema, and Adapter resources. Do not copy the full `ontology-builder` Skill. Thin mode-specific
  entry points are allowed only when both directly reference the same core rules.
- Evidence: user confirmation; `skills/ontology-builder/references/modeler-handoff.schema.json`;
  R1.1-006 shared-directory design; `backend/app/api/schemas.py`.
- Outcome/next step: assess whether stable role-specific details should also move into Skills
  preloaded by subagents.

### 2026-07-21T22:44:47+08:00 — subagent Skill architecture assessment — main agent

- Context: current subagent prompts are concise, but repeated task handoffs can still carry stable
  modeling guidelines, quality gates, schemas, and large task content.
- Action/decision: recommend capability-specific subagent Skills, subject to user confirmation.
  Claude Code 2.1.74 supports preloading full Skill content through a subagent definition's
  `skills:` field. Put stable methods, stop rules, and output contracts in those Skills; keep each
  Agent definition limited to role identity, tools, and its preloaded Skills. Pass dynamic business
  content only as run/work-unit IDs, bounded change messages, file locators, and schema paths.
  Skills do not replace the shared directory or current task data.
- Evidence: `.claude/agents/*.md`; `skills/ontology-builder/references/role-handoffs.md`;
  `skills/ontology-builder/references/modeling-guidelines.md`; R1.1-006 design; official Claude Code
  subagent documentation at `https://code.claude.com/docs/en/sub-agents`.
- Outcome/next step: confirm the initial capability split and keep role Skills mode-neutral where
  possible.

### 2026-07-21T22:50:25+08:00 — refinement decision 13 — user and main agent

- Context: role-specific stable methods are repeatedly useful, while business content and Work
  Unit state remain dynamic and should not be embedded in a Skill.
- Action/decision: add four initial capability Skills: `ontology-business-organizer`,
  `ontology-work-unit-modeler`, `ontology-model-reviewer`, and
  `ontology-retrieval-evaluator`. Convert project subagent definitions into thin wrappers that keep
  role identity/tool restrictions and preload the applicable Skill. Main-Agent delegation passes
  only run/work-unit IDs, output-contract or schema path, bounded business-change information, and
  expected output path. Shared files remain the source for Brief, Coverage, sources, dependencies,
  and current results. Do not create per-domain or per-Work-Unit Skills.
- Evidence: user confirmation; current `.claude/agents/*.md`; official Claude Code subagent Skill
  preload support; `skill-creator` progressive-disclosure guidance.
- Outcome/next step: confirm the first runtime target and whether separate Codex subagent
  configuration is part of R1.1-007.

### 2026-07-21T22:55:03+08:00 — refinement decision 14 — user and main agent

- Context: the capability Skills can remain runtime-neutral, but wiring and validating both Claude
  Code and Codex subagent runtimes would expand the first delivery substantially.
- Action/decision: first delivery wires and validates the four Skills only through Claude Code
  project subagents and the current Harness. Keep Skill content compatible with the Agent Skills
  structure, but defer Codex subagent configuration and do not make dual-runtime acceptance a
  completion gate.
- Evidence: user confirmation in the R1.1-007 refinement conversation.
- Outcome/next step: functional refinement is complete; synchronize the authoritative requirement
  and glossary, then pause before design, plan review, or implementation.

### 2026-07-21T22:55:03+08:00 — refinement scope freeze — main agent

- Context: scope, actors, dialogue, inputs, outputs, Profile selection, failure behavior, change
  consistency, credentials, Harness recording, role Skills, runtime support, non-goals, and
  acceptance scenarios have all been confirmed.
- Action/decision: update R1.1-007 to `已细化，待实现`; define one shared modeling core, Local/Formal
  Profile-Schema-Adapter boundaries, continuous user dialogue, direct subagent-to-main clarification,
  local Harness optimization evidence, automatic platform write contracts, four capability Skills,
  and Claude-only first-runtime acceptance. Explicitly reject workflow shortening and quantitative
  efficiency comparison.
- Evidence: `docs/requirements/requirements-v1.1.md` R1.1-007;
  `docs/reference/glossary.md`; refinement decisions 1-14 above.
- Outcome/next step: create the design and shared test plan only when implementation delivery begins.

### 2026-07-21T22:57:40+08:00 — refinement documentation verification — main agent

- Context: the confirmed contract was synchronized into the authoritative requirement and glossary.
- Action/decision: renamed R1.1-007 to `本地/正式建模执行 Profile`, updated it to `已细化，待实现`,
  and checked requirement summary, detailed status, routing rules, Harness semantics, Profile names,
  non-goals, and acceptance criteria for contradictions.
- Evidence: `rg` consistency searches over the requirement/glossary/record; `git diff --check` PASS;
  no trailing whitespace in the three affected documents.
- Outcome/next step: refinement is closed. Design, shared test plan, plan review, implementation,
  independent testing, runtime verification, and commit closure remain future delivery work.

## Review disposition

No plan review has started because the detailed contract is intentionally pending.

## Development and defect history

No implementation has started.

## Independent test rounds

No independent testing has started.

## Final verification

- Required checks: documentation consistency inspection and `git diff --check` after refinement.
- Runtime/restart health: not required for documentation-only requirement capture.
- Documentation/status sync: requirement summary/status, detailed R1.1-007 contract, routing rule,
  and glossary synchronized to the confirmed refinement.
- Cleanup: none.
- Residual risks and follow-ups: implementation design must verify current Claude Code Skill preload,
  local/formal Schema adapters, Harness capture coverage, and platform-contract automation against
  the real runtime. These are design/probe tasks, not unresolved product decisions.

## Retrospective

Not applicable before refinement and implementation.
