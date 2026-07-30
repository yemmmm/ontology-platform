# R2.3-001 Team Runner and Codex Adapter Delivery Record

- Requirement source: `docs/requirements/requirements-v2.3.md`, R2.3-001
- Status: in-progress
- Started: 2026-07-30T18:55:53+08:00
- Last updated: 2026-07-31T00:55:37+08:00
- Design: pending
- Shared test plan: pending
- Delivery baseline: clean worktree at `2e3b3b933ee6035b11d855d70ca1bdcffb013aeb`
- Delivery commit: pending

## Confirmed contract

- Current behavior: R2.2-001 L0, L1, and L3 prove a bounded three-Agent modeling team, but its
  accepted role configuration, prompts, isolation, continuation, protocol mechanics, and evidence
  handling remain scenario-local; the maintained `ontology-modeling` Skill still describes a
  single Modeling Agent.
- Target behavior: deliver a stable repository-local Team Runner, Agent Package/Profile format,
  Runtime Adapter contract, and Codex Team Adapter so later modeling approaches primarily add or
  change real Agents and Skills instead of rebuilding launch and communication mechanics.
- In scope:
  - one Team Runner process manages one Team Run and starts the fixed roster selected by one
    Modeling Team Profile;
  - Profiles reference Agent Packages containing shared role instructions, required
    Skills/references, and permission declarations; Runtime Adapters add only thin native loading;
  - one homogeneous Runtime per team run; R2.3-001 implements Codex only while keeping the contract
    free of Codex-specific fields;
  - one Coordinator and one Protocol Agent per run, plus the fixed Modeling/specialist Agents named
    by the Profile;
  - free-form direct Agent communication with retained Runtime context and no custom candidate
    revision/readiness/approval state machine;
  - a persistent Coordinator that dispatches the started roster, continuously receives and replies
    through the current user conversation, forwards only explicit modeling input verbatim, and
    aggregates Agent terminal results without supervising or judging modeling;
  - Protocol-only platform-write configuration; Coordinator has no platform MCP and other Agents
    may receive only Package-declared read-only tools;
  - Runtime-neutral user-message send/receive, Agent lifecycle, direct communication, settlement,
    and stop operations;
  - minimum local state for current-run resume, diagnosis, exact resource ownership, and cleanup;
  - mechanical empty-scope `create` and `existing` lifecycle checks without Modeling Batch writes;
  - a base real three-Agent capability smoke and a separate Profile with one additional real Agent
    proving Package/Profile-only extension without Team Runner changes.
- Non-goals:
  - real ontology modeling, Modeling Batch application, or modeling-quality claims in R2.3-001;
  - a real Pi team, per-Agent mixed Runtimes, cross-Runtime messaging, or a fake second Adapter;
  - dynamic Agent discovery/scaling, runtime roster changes, multiple Protocol Agents, or
    concurrent write-scope ownership;
  - Coordinator semantic approval, progress monitoring, stall diagnosis, or proactive Agent pause;
  - platform audit records, immutable event history, hidden reasoning capture, or long-term
    transcript retention;
  - backend Agent Runtime, new chat UI/API, message database, remote scheduling, management UI, or
    multi-run orchestration.
- Acceptance summary:
  - real Codex Agents load the declared instructions, Skills, task, roster, and permissions;
  - Coordinator dispatches work, remains responsive to mechanically relayed user messages, and
    reports the settled team outcome;
  - Agent-to-Agent direct communication works without Coordinator relay;
  - Protocol alone has platform MCP configuration, while no Agent performs actual modeling writes;
  - empty `create` and `existing` platform scopes are resolved and cleaned according to ownership;
  - adding one real specialist Agent requires only its Package/Profile and leaves Team Runner code
    unchanged;
  - Runtime/Agent processes, temporary credentials, owned empty resources, and local state are
    cleaned exactly, with independent testing.
- Refinement:
  - R2.3-001 covers Runner/Package/Profile/Codex capability smoke without modeling.
  - R2.3-002 uses the unchanged Runner for one real new-scope business slice.
  - R2.3-003 launches a fresh team against the exact non-empty Project/Ontology intentionally
    retained by R2.3-002, using only platform facts and a non-secret scope handoff.
  - R2.3-004 implements the complete Pi Team Adapter against the same team contracts.

## Timeline

### 2026-07-30T18:55:53+08:00 — source and current-state audit — Delivery Agent

- Context: R2.2-001 L3 is implemented and independently accepted, while its design explicitly
  remains a repository-local evaluation scenario rather than a reusable product Runtime.
- Action/decision: preserve v2.2 as closed scope and begin collaborative refinement of a new
  R2.3-001 requirement before design or implementation.
- Evidence: `docs/requirements/requirements-v2.2.md`;
  `docs/delivery/designs/2026-07-30-r2-2-001-ontology-modeling-team-l3-design.md`;
  `docs/evaluation-scenarios/ontology-modeling-team-l3/`;
  `skills/ontology-modeling/SKILL.md`.
- Outcome/next step: confirm consequential functional boundaries one question at a time, beginning
  with Runtime portability.

### 2026-07-30T19:32:57+08:00 — Runtime boundary refinement — User and Delivery Agent

- Context: the standard may either bind itself to Codex, require immediate Codex/Pi parity, or
  separate the stable team contract from Runtime-specific lifecycle mechanics.
- Action/decision: keep the team contract Runtime-neutral and deliver only the Codex adapter in
  R2.3-001.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: Pi parity is not an R2.3-001 completion gate; confirm whether the three core
  roles remain mandatory while later roles are optional plug-ins.

### 2026-07-30T20:27:41+08:00 — control and communication topology refinement — User and Delivery Agent

- Context: the L3 hierarchy routes Modeling output through the Coordinator before launching a
  separate Protocol Agent, but future modeling teams may require direct collaboration among several
  specialized Agents.
- Action/decision: use centralized workflow control with decentralized communication. The
  Coordinator owns task state, user interaction, approval of semantic state changes, and terminal
  outcome. Registered Agents may directly exchange messages and versioned Artifact references over
  Team-manifest channels. Direct communication does not transfer platform-write or semantic-change
  authority.
- Evidence: user confirmation in the active refinement session; current Codex supports addressable
  Agent messaging, while the Runtime-neutral contract will expose a Team Communication Port rather
  than Codex-specific message semantics.
- Outcome/next step: define whether roles are fixed one-per-run or capabilities with multiple
  scope-bounded Agent instances.

### 2026-07-30T20:36:35+08:00 — Agent cardinality refinement — User and Delivery Agent

- Context: a general standard could immediately support several Protocol writers with
  scope-specific ownership, but current expected workflows do not require that concurrency.
- Action/decision: require one Coordinator and one Protocol Agent per R2.3-001 run. Permit multiple
  Modeling or specialist Agent instances. Defer multiple Protocol Agents, concurrent write scopes,
  and their ownership/Lease design to a later requirement triggered by observed demand.
- Evidence: user direction in the active refinement session.
- Outcome/next step: confirm whether the Coordinator may dynamically assemble allowed specialist
  Agents during a run or must follow a fully instantiated topology fixed before launch.

### 2026-07-30T21:05:44+08:00 — fixed run roster refinement — User and Delivery Agent

- Context: the proposed capability registry would let the Coordinator create Agent instances
  dynamically, but the user's intended optimization loop compares deliberately designed modeling
  approaches rather than dynamically scaling one run.
- Action/decision: freeze the Agent roster before each run. The Coordinator receives the identities
  and roles of already started Agents and dispatches work among them; it does not discover, create,
  scale, or retire Agent instances. Adding an Agent later creates a new versioned modeling-team
  approach for separate quality evaluation.
- Evidence: user correction in the active refinement session.
- Outcome/next step: keep dynamic team assembly out of R2.3-001 and confirm how much of direct
  Agent communication must be structured and retained.

### 2026-07-30T21:55:09+08:00 — communication and event refinement — User and Delivery Agent

- Context: requiring every direct Agent message to use a rigid schema would constrain future
  modeling approaches, while retaining only unstructured chat would make material state changes
  difficult to audit.
- Action/decision: allow free-form direct Agent communication without Coordinator relay. Require
  versioned Artifacts for state-changing outcomes and make the Coordinator responsible for
  publishing the corresponding team execution events. Do not require hidden reasoning capture.
- Evidence: user confirmation and ownership direction in the active refinement session.
- Outcome/next step: distinguish Coordinator-authored workflow events from mechanically captured
  Runtime identities, tool calls, platform receipts, and cleanup evidence.

### 2026-07-30T22:11:08+08:00 — event evidence and heterogeneous Runtime refinement — User and Delivery Agent

- Context: “Runtime evidence” needed a precise boundary, and a near-term Pi Agent may fill the
  Modeling role while other team roles remain on Codex.
- Action/decision: the Coordinator authors team-level workflow events. Runtime Adapters
  mechanically capture Agent identity, lifecycle, and message-delivery facts. Semantic Platform
  receipts prove platform calls and results. Amend the initial single-Runtime assumption: the team
  contract and communication transport must support per-Agent Runtime binding so a Codex
  Coordinator can collaborate with a Pi Modeling Agent without changing the role or Artifact
  contracts.
- Evidence: user confirmation and Pi planning information in the active refinement session.
- Outcome/next step: decide whether R2.3-001 must implement and live-test a real Pi Modeling Agent
  adapter or only freeze and test the heterogeneous-Runtime extension contract.

### 2026-07-30T22:16:17+08:00 — correction: homogeneous team Runtime — User and Delivery Agent

- Context: the preceding entry interpreted the Pi direction as a mixed Codex/Pi team.
- Action/decision: correct that interpretation. A modeling-team run is homogeneous: Coordinator,
  Modeling Agent, Protocol Agent, and any other configured roles all use the selected Runtime.
  R2.3-001 must keep the team, communication, Artifact, and event contracts portable across a
  Codex team and a future Pi team, but does not design per-Agent Runtime mixing.
- Evidence: user correction in the active refinement session.
- Outcome/next step: decide whether a complete Pi team adapter is implemented in R2.3-001 or only
  reserved as a contract-compatible follow-up.

### 2026-07-30T22:20:04+08:00 — R2.3 Runtime delivery scope — User and Delivery Agent

- Context: the standard must accommodate a near-term all-Pi modeling team without expanding the
  current delivery into simultaneous Codex and Pi implementation.
- Action/decision: keep core contracts free of Codex-specific fields; implement and live-test the
  Codex Team Adapter in R2.3-001; define the Runtime Adapter interface and exercise it with a second
  test adapter; defer the complete Pi Team Adapter, Pi role definitions, and real Pi acceptance to
  a later requirement.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: confirm whether R2.3-001 includes one stable deterministic Team Runner outside
  the Agent team for lifecycle, platform scope, evidence, and cleanup mechanics.

### 2026-07-30T22:25:07+08:00 — Team Runner boundary refinement — User and Delivery Agent

- Context: without a stable mechanical runner, each Agent/Skill experiment would continue
  rebuilding startup, credentials, evidence, and cleanup logic in scenario-specific scripts.
- Action/decision: include one deterministic repo-local Team Runner outside the modeling team. It
  reads the frozen run configuration, starts the selected Runtime Adapter, prepares empty platform
  scope and temporary credentials, forwards exact external answers, collects evidence, and performs
  cleanup/health checks. It cannot dispatch modeling work, choose semantic content, judge quality,
  or change the Agent roster.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: decide whether Coordinator events and standard Artifact metadata remain only
  in the local run directory or are also archived through the existing platform Modeling Execution
  Record capability.

### 2026-07-30T22:32:43+08:00 — audit scope refinement — User and Delivery Agent

- Context: the existing platform can preserve Modeling Execution Records, but durable audit is not
  required to establish the standard multi-Agent modeling approach.
- Action/decision: keep platform Execution Record integration, long-term event archival, immutable
  audit chains, and audit query/UI out of R2.3-001.
- Evidence: user direction in the active refinement session.
- Outcome/next step: distinguish deferred audit from the minimum local operational state required
  for clarification resume, failure diagnosis, cleanup, and requirement acceptance.

### 2026-07-30T22:35:32+08:00 — minimum local state refinement — User and Delivery Agent

- Context: even without audit, a paused or failed run needs enough state to resume the same
  Coordinator, identify its current Artifact, and clean only owned resources.
- Action/decision: retain only local operational state for the current run: roster/Runtime
  identities, current Coordinator stage, pending and released answers, current candidate and
  Protocol Artifacts, owned platform resource identifiers, terminal state, and cleanup result.
  This is not a long-term audit feature.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: confirm the Coordinator approval boundary that authorizes the single Protocol
  Agent to perform platform writes after direct peer communication.

### 2026-07-30T23:31:41+08:00 — direct collaboration simplification — User and Delivery Agent

- Context: a proposed candidate revision/readiness/dispatch state machine duplicated persistent
  Agent conversation context and would make the Coordinator an unnecessary semantic gate.
- Action/decision: remove custom candidate revision, readiness, dispatch authorization, and hash
  flow. Modeling and Protocol Agents communicate directly and retain the latest content in their
  Runtime Sessions. The Protocol Agent asks follow-up questions directly and proceeds when it has
  enough information. Only user questions, platform Modeling Items/Batches and results, terminal
  outcome, and minimum pause/resume state require structure.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: refine whether the Coordinator monitors long-running Agent progress and how
  soft collaboration stalls differ from Runtime process failures.

### 2026-07-30T23:37:32+08:00 — Coordinator intervention and continuous conversation — User and Delivery Agent

- Context: proactive progress monitoring and stall intervention would require the Coordinator to
  interpret incomplete modeling activity and may make the workflow less stable.
- Action/decision: keep progress watchdogs, stall diagnosis, and Coordinator-initiated Agent pause
  out of R2.3-001. Keep the Coordinator Session responsive during modeling so the user can continue
  the conversation, provide information, request status, or issue control instructions. The
  Coordinator may route relevant messages but does not supervise semantic progress.
- Evidence: user direction in the active refinement session.
- Outcome/next step: define how unsolicited user information is delivered to active Agents without
  silently changing an in-flight platform write.

### 2026-07-30T23:40:02+08:00 — user-message routing refinement — User and Delivery Agent

- Context: a continuously responsive Coordinator must not silently turn every user message into a
  modeling input.
- Action/decision: forward user text verbatim only when the user explicitly identifies it as
  supplemental business information, a correction, a scope change, or a modeling instruction.
  Keep ordinary conversation and status questions within the Coordinator interaction. When intent
  is ambiguous, ask the user before forwarding.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: define terminal ownership so the Coordinator can report completion without
  becoming the model-quality judge.

### 2026-07-30T23:42:09+08:00 — terminal ownership refinement — User and Delivery Agent

- Context: allowing the Coordinator to decide that a model is correct would conflict with its
  lightweight routing and user-conversation role.
- Action/decision: every started Agent reports its own completed or blocked task result. Protocol
  additionally reports the terminal platform outcome and evidence. Runtime reports which Agent
  Sessions have settled. Coordinator waits for those facts, then reports the team outcome to the
  user without inspecting ontology quality. Independent quality evaluation remains outside the
  production team.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: define how fixed Agent rosters and Skill combinations are packaged as
  selectable modeling approaches for later experiments.

### 2026-07-30T23:45:11+08:00 — Modeling Team Profile refinement — User and Delivery Agent

- Context: future modeling-quality experiments need to change Agent/Skill combinations without
  changing Team Runner mechanics or dynamically scaling an active run.
- Action/decision: define each fixed roster and Skill combination as one lightweight Modeling Team
  Profile selected before launch. Team Runner starts every Agent in that Profile and gives the
  resulting roster to Coordinator. A new Agent or Skill combination creates a new Profile; a
  separately evaluated Profile may later become the default.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: define how a Profile references Agent prompts and Skills and how Runtime
  Adapters install them for Codex or a future Pi team.

### 2026-07-30T23:48:40+08:00 — Agent Package and Skill loading refinement — User and Delivery Agent

- Context: embedding prompts in Team Profiles would duplicate role semantics and make future
  Codex/Pi support maintain separate modeling rules.
- Action/decision: Profiles reference Agent Packages. A Package contains Runtime-neutral role
  instructions, required Skill and reference paths, and permission/tool declarations. Team Runner
  supplies the per-run task and roster. Codex Adapter loads this through custom-Agent developer
  instructions and enabled Skills; a future Pi Adapter maps the same content into Pi role prompts
  and Workflow Packages. Runtime-specific loader configuration may differ, but role semantics and
  modeling methods remain shared.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: confirm the stable platform-tool permission boundary for Protocol and future
  specialist Agents.

### 2026-07-31T00:19:42+08:00 — platform permission refinement — User and Delivery Agent

- Context: future specialist Agents may need platform retrieval while the team must retain one
  unambiguous write authority.
- Action/decision: keep platform-write MCP exclusive to Protocol. Coordinator receives no platform
  MCP. Modeling defaults to no platform MCP, and a future specialist Agent may receive only the
  read-only tools declared by its Agent Package. Team Runner generates isolated Runtime
  configuration and temporary credentials; no dynamic privilege escalation is allowed.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: confirm whether standardization acceptance requires one real Codex end-to-end
  run plus offline extensibility tests, without a second live quality-comparison profile.

### 2026-07-31T00:28:41+08:00 — correction: real-Agent extensibility proof — User and Delivery Agent

- Context: a proposed fake Agent and fake Runtime Adapter would add test-only logic solely to prove
  an extension point.
- Action/decision: do not implement fake Agent orchestration or a second fake Runtime. Add one real
  Codex specialist Agent through a new Agent Package/Profile and exercise its startup, direct
  communication, Skill loading, permissions, terminal result, and cleanup through the unchanged
  Team Runner. Judge only the extension mechanics, not quality improvement. Keep the core/Adapter
  boundary Runtime-neutral by design; defer cross-Runtime proof to the real Pi Team Adapter.
- Evidence: user direction in the active refinement session.
- Outcome/next step: decide whether this real additional Agent participates in the single
  end-to-end acceptance Profile or runs as a separate interoperability smoke.

### 2026-07-31T00:30:34+08:00 — real-Agent acceptance split — User and Delivery Agent

- Context: placing an extra Agent in the only end-to-end run would mix extension mechanics with a
  new modeling approach and complicate the semantic result.
- Action/decision: use the base three-Agent Profile for one real end-to-end modeling run. Use a
  separate minimal Profile with a real specialist Agent to prove Package/Profile-only extension,
  Skill loading, direct communication, permissions, terminal handling, and cleanup without
  modifying Team Runner or claiming quality improvement.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: refine whether Team Runner supports starting a fresh modeling-team run against
  an existing Project/Ontology in addition to creating an empty scope.

### 2026-07-31T00:44:55+08:00 — version roadmap and existing-Project requirement split — User and Delivery Agent

- Context: mechanically resolving an existing empty scope in Runner tests does not prove that a
  fresh Agent team can understand and safely extend a non-empty model created by an earlier run.
- Action/decision: organize the roadmap as:
  - R2.3-001: Team Runner, Team Profile, Agent Package, Runtime Adapter contract, Codex Adapter,
    empty `create/existing` lifecycle, and real-Agent capability/interoperability smoke without
    actual modeling;
  - R2.3-002: one real business-slice model in a newly created scope;
  - R2.3-003: launch a fresh team against an existing non-empty Project/Ontology and complete an
    incremental modeling loop without changing Team Runner;
  - R2.3-004: implement the complete Pi Team Adapter.
- Evidence: user confirmation of the 001 boundary and direction to insert a dedicated existing-
  Project team-validation requirement before Pi.
- Outcome/next step: decide whether R2.3-003 continues the exact Project produced by R2.3-002 or
  uses an independently prepared existing Project fixture.

### 2026-07-31T00:47:46+08:00 — R2.3-002 to R2.3-003 scope handoff — User and Delivery Agent

- Context: an independently seeded fixture would not prove continuity between two real team runs.
- Action/decision: R2.3-002 intentionally retains its owned Project/Ontology after revoking
  temporary credentials, releasing its Lease, closing its Build Session, and stopping Agent
  Runtimes. It publishes a non-secret handoff containing scope identifiers and workspace context.
  R2.3-003 starts a wholly fresh team against that scope, inherits no Agent conversation or hidden
  answer, creates its own Build Session/Lease, and proves incremental modeling preserves the prior
  model. Existing mode never deletes the scope; test-owned final cleanup may occur after independent
  R2.3-003 acceptance.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: settle the user-facing transport for continuous Coordinator conversation, then
  settle whether R2.3-001 supports concurrent team runs.

### 2026-07-31T00:49:15+08:00 — continuous user-conversation transport — User and Delivery Agent

- Context: a persistent internal Coordinator needs a user transport, but a new chat UI, backend
  session service, or message store would substantially expand Runner productization.
- Action/decision: reuse the current Codex conversation as the user-facing surface. The outer
  caller forwards user text exactly through Team Runner to Coordinator, and returns Coordinator
  text exactly to the user. Neither layer answers on Coordinator's behalf or changes message
  meaning. Runtime-neutral send/receive operations map to the Codex Coordinator Session in the
  first Adapter.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: confirm the one-run-per-Runner concurrency boundary.

### 2026-07-31T00:50:05+08:00 — Runner concurrency boundary and refinement close — User and Delivery Agent

- Context: allowing one Runner to manage several active teams would require scheduling, routing,
  multi-run state, and broader recovery behavior unrelated to the first Runner capability proof.
- Action/decision: one Team Runner process manages one Team Run. R2.3-001 does not build or test a
  multi-run scheduler. Future callers may start independent Runner processes with distinct run IDs,
  directories, credentials, and platform scopes; platform Lease/workspace-version rules remain the
  authority for same-Ontology write concurrency.
- Evidence: user confirmation in the active refinement session.
- Outcome/next step: functional refinement has no remaining material question. Write the
  authoritative v2.3 requirement source before design and shared-test planning.

### 2026-07-31T00:55:37+08:00 — Authoritative v2.3 requirement source written — Delivery Agent

- Context: functional refinement was complete and the user approved writing the agreed roadmap and
  R2.3-001 contract into the repository.
- Action/decision: created `docs/requirements/requirements-v2.3.md`; recorded R2.3-001 as the current
  P0 requirement with completed refinement, and recorded R2.3-002, R2.3-003, and R2.3-004 as ordered
  follow-up requirements whose detailed acceptance contracts remain pending refinement.
- Evidence: `docs/requirements/requirements-v2.3.md`; this delivery record.
- Outcome/next step: requirement writing is complete. R2.3-001 design and shared-test planning are
  the next delivery stage and have not started.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

## Final verification

- Required checks: pending
- Runtime/restart health: pending
- Documentation/status sync: pending
- Cleanup: pending
- Residual risks and follow-ups: pending

## Retrospective

- Scope or design deviations: pending
- Rework and root causes: pending
- What shortened or delayed delivery: pending
- Reusable lessons: pending
