# R2.1-001 本体建模流程重构 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.1.md` R2.1-001
- Status: 细化中；M1 需求边界、合成 Fixture 与建模 Agent 迭代授权已确认
- Started: 2026-07-23T17:11:19+08:00
- Last updated: 2026-07-23T20:31:50+08:00
- Worktree baseline: `1dc5d54` (Pause R2.0-002 and record ontology workflow rethink)
- Design: not created; final process is intentionally not frozen
- Shared test plan: not created; acceptance contract is intentionally not frozen

## Initial context

- Current state: R2.0-002 is paused at its Pi Runtime/real-run checkpoint. Its original knowledge-
  graph-oriented workflow has not completed merge, review, apply, post-apply verification, Claude
  retirement, or final independent PASS.
- Target state: refine an ontology-centered modeling workflow without equating document knowledge-
  graph construction with ontology modeling completion.
- Dependencies: v1.0 semantic platform boundary; v1.1 modeling-workflow evidence; R2.0-002 Pi Runtime
  checkpoint and its real-run evidence.
- Non-goals: no final workflow design, implementation, acceptance criteria, Claude retirement, or
  automatic continuation of R2.0-002 is authorized by this migration.

## Decision history

### 2026-07-23T17:11:19+08:00 — Migrate R2.0-003 to v2.1 — main agent + user

- Context: R2.0-003 was recorded in v2.0 only as a background placeholder after R2.0-002 was paused.
  The user requested that the requirement belong to v2.1 instead.
- Action/decision: Remove R2.0-003 from `requirements-v2.0.md`; create v2.1 R2.1-001 with the same
  name, background, current directions, and unresolved refinement topics. Update v2.0 and the
  R2.0-002 record to reference R2.1-001.
- Evidence: `docs/requirements/requirements-v2.0.md`; commit `1dc5d54`; R2.0-002 delivery record.
- Outcome/next step: R2.1-001 remains `待细化`. Begin collaborative functional refinement only when the
  user asks to determine the final ontology modeling workflow.

### 2026-07-23T18:00:38+08:00 — Confirm minimal-ontology iteration route — main agent + user

- Context: The user wants R2.1-001 to remain a longer optimization process but considers the current
  end-to-end workflow too large to optimize effectively. The immediate goal is to construct a minimal
  ontology that is distinguishable from an instance-heavy knowledge graph.
- Action/decision: Adopt a `minimal ontology -> semantic tests -> incremental expansion` route. M1 uses
  one bounded semantic slice, a small TBox, at least one executable constraint, at least one executable
  inference expectation, and positive/negative fixtures. The platform Modeling Batch and deterministic
  verification boundary remains at final candidate application.
- Deferred by default: Full Coverage, Work Unit partitioning, independent review, Shared Modeling
  Directory recovery, Pi Runtime integration, complete execution events, and bulk instance extraction.
  Each mechanism is restored only when an observed modeling-quality failure justifies it.
- Evidence: `docs/requirements/requirements-v2.1.md`; current v1.1 simple-priority guidance; current
  class/property/relation/SHACL compiler and limited RDFS reasoner.
- Outcome/next step: Inspect the pinned Dify corpus for a bounded first semantic slice.

### 2026-07-23T18:00:38+08:00 — Inspect Dify change-impact slice — main agent

- User candidate: Modify a child workflow, infer which parent workflows are affected, then assess
  impact from the actual change.
- Terminology finding: Dify documentation uses `sub-workflow` for the internal workflow of an Iteration
  node. Cross-application reuse is documented as a Workflow published as a Tool. The candidate should
  therefore use `callee Workflow`, `caller Workflow`, `Workflow Tool`, and `Tool Invocation`, not one
  overloaded parent/child relationship.
- Pinned-source evidence:
  - `official/en/cloud/use-dify/nodes/start.mdx` states that only User Input workflows can be reused as
    tools in other Dify apps.
  - `official/en/cloud/use-dify/nodes/output.mdx` states that Output variables define a Workflow Tool's
    return schema and are accessible to the invoking parent workflow.
  - `official/en/cloud/use-dify/build/version-control.mdx` distinguishes Current Draft, Latest Version,
    Previous Versions, and publication.
  - `official/en/cloud/use-dify/nodes/iteration.mdx`,
    `official/en/cloud/use-dify/build/orchestrate-node.mdx`, and
    `official/en/cloud/use-dify/workspace/app-management.mdx` provide counterexamples for internal
    sub-workflows, copied nodes, and duplicated independent apps.
- Supplemental official-source check:
  - `https://docs.dify.ai/en/cloud/use-dify/workspace/tools` confirms that a User Input Workflow can be
    turned into a Tool and reused across apps.
  - `https://docs.dify.ai/en/cloud/use-dify/build/version-control` confirms that a draft becomes the new
    Latest Version only when published.
- Source gap: The current immutable corpus snapshot does not include the Dify Tools page even though
  the pinned Output page links to it. Formal M1 modeling must use a new immutable snapshot or
  scenario-specific source pack; the existing snapshot must not be edited in place.
- Assessment: Workflow-as-Tool change impact is the strongest current M1 candidate because it requires
  concept boundaries, publication-state semantics, dependency inference, binding constraints, and
  negative cases that distinguish an ontology from a flat workflow knowledge graph.
- Remaining boundary: Dependency reachability and structural contract risk can be deterministic.
  Prompt/model/internal-logic changes without an interface change require Agent interpretation and
  runtime evidence; M1 must not fabricate a precise impact level from topology alone.
- Outcome/next step: Ask whether M1 should first close only published interface-contract changes or also
  include behavior-only changes with an explicitly uncertain impact result.

### 2026-07-23T18:02:21+08:00 — Verify route documentation — main agent

- Checks: `git diff --check`; pinned Dify corpus verification; Dify corpus unit tests.
- Result: Snapshot `dify-foundations-2026-07-18-5396c1a` verified with 32 files; all 24 corpus tests
  passed. The test run emitted one pre-existing Python invalid-escape `SyntaxWarning`.
- Scope: Documentation and source analysis only; no runtime, platform schema, corpus snapshot, or
  modeling implementation was changed.

### 2026-07-23T18:31:21+08:00 — Confirm impact-information boundary — main agent + user

- Clarification: The user confirmed Workflow-as-Tool change impact as the M1 slice but corrected the
  responsibility boundary. Ontology should identify the information needed for impact analysis, and
  the platform should return all modeled facts, dependency paths, bindings, versions, provenance, and
  unknowns. The consuming Agent performs the actual impact judgment.
- Decision: M1 does not require Ontology or Semantic Platform Core to compare before/after behavioral
  test metrics or produce impact severity. Test metrics and output comparisons are optional external
  observations that a consuming Agent may use; if submitted as facts, the platform may return them
  without interpreting them.
- Deterministic platform result: Direct and transitive caller candidates, publication state, affected
  call sites, input/output bindings, downstream variable use, dependency paths, sources, and explicit
  missing information.
- Agent result: Decide which candidates are actually affected, how they are affected, and the final
  impact size from the returned context plus the actual Workflow/DSL change and optional runtime
  evidence.
- Boundary: Semantic Platform Core does not parse Dify DSL, execute behavior tests, compare metrics, or
  make domain-specific impact judgments. Dify concepts remain reference-ontology data.
- Outcome/next step: Refine the minimum information contract that must be returned for each affected
  caller candidate.

### 2026-07-23T18:38:48+08:00 — Confirm caller-internal propagation context — main agent + user

- Question: Whether an affected-caller result must include how a bound Workflow Tool output is used by
  downstream nodes inside the caller, rather than returning only caller Workflow IDs.
- Decision: Yes. Each caller candidate must include the stable call site, input/output bindings,
  upstream input source, downstream variable-use path, conditions, outputs, and any next Workflow Tool
  invocation. Transitive results must preserve the cross-Workflow propagation path.
- Completeness: Missing node, binding, or variable-use facts must be returned as explicit gaps. An empty
  path result cannot be interpreted as evidence that no downstream impact exists.
- Responsibility boundary: The platform returns modeled topology, contracts, provenance, and
  completeness; the consuming Agent decides whether path membership creates actual business impact.
- Outcome/next step: Refine the first concrete Change Set and positive/negative fixtures for M1.

### 2026-07-23T18:51:46+08:00 — Confirm ontology-first fixture and no platform adaptation — main agent + user

- Fixture decision: Use a three-level `C -> B -> A` Workflow-as-Tool chain. C publishes a version that
  removes or renames an Output consumed by B; B's derived output is consumed by A. The positive case
  must expose the full cross-Workflow binding/use path. The negative case keeps the same C change in
  Current Draft without changing Latest Version.
- User reminder: Required impact context must come from improving the ontology structure and modeled
  instance facts. It must not be implemented by customizing platform capabilities for Dify data.
- Boundary decision: M1 reuses existing generic Context Query, SPARQL, validation, inference, and
  provenance. It does not add Dify-specific REST/MCP APIs, response fields, read models, query branches,
  ordering rules, DSL parsing, fixture generation, or impact judgment.
- Escalation rule: If a correctly modeled required fact cannot be retrieved through current generic
  capabilities, record reproducible evidence and refine a separate generic platform requirement before
  changing platform code.
- Outcome/next step: Define the concrete Workflow/variable names, Change Set fields, ontology elements,
  and positive/negative query assertions.

### 2026-07-23T18:55:04+08:00 — Select Output deletion as the first positive Change Set — main agent + user

- Decision: The first positive Fixture uses a newly published C version that deletes one Output already
  bound and consumed by B. Output rename is deferred to a later case.
- Reason: Deletion has an unambiguous before/after contract. Rename requires additional semantic
  identity or mapping facts to decide whether the new variable is equivalent to the old one; without
  those facts it must be modeled as one deletion plus one addition.
- Outcome/next step: Choose concrete C/B/A workflow purposes, node names, the deleted Output, and exact
  positive/negative query assertions.

### 2026-07-23T20:16:03+08:00 — Confirm synthetic Dify-valid C/B/A Fixture — main agent + user

- Decision: Use a synthetic but Dify-valid three-Workflow acceptance scenario rather than claiming the
  official documentation contains an existing three-level application chain.
- Fixture:
  - C is `Content Quality Scoring Workflow`; it accepts `content:string` and initially returns
    `quality_score:number`.
  - B is `Content Generation Workflow`; it calls C, binds `quality_score`, uses it in IF/ELSE, and
    exposes `approved_content:string`.
  - A is `Campaign Publication Workflow`; it calls B, binds `approved_content` to `publish_content`,
    and passes it to a downstream publication-preparation node or Output.
- Positive change: Publish a new C Latest Version that deletes `quality_score:number`.
- Negative change: Keep the same deletion only in C Current Draft.
- Evidence boundary: Official Dify sources support Workflow-as-Tool, Output contract, and publication
  semantics. C/B/A purposes, variables, bindings, and changes are synthetic Fixture facts. Documents
  and reports must keep official facts, synthetic facts, and Agent inferences explicitly separated.
- Outcome/next step: Define stable IRIs/IDs, the Change Set structure, ontology elements, and executable
  query definitions.

### 2026-07-23T20:31:50+08:00 — Delegate ontology-structure choices to iterative modeling — main agent + user

- User direction: The modeling structure does not need to be fixed or individually confirmed now. The
  modeling Agent may decide the initial structure and adjust it repeatedly in later iterations.
- Decision: Requirements freeze the M1 goal, responsibility boundary, Fixture, and acceptance outcome,
  not one immutable set of Classes, Properties, Relations, Shapes, axioms, rules, IRIs, or version
  representation.
- Working rule: The modeling Agent records each hypothesis, model change, targeted problem, test result,
  and known limitation. Internal structure changes do not require user confirmation.
- Reconfirmation triggers: A change to the business goal, Fixture, completion gate, platform/Agent
  responsibility boundary, platform capability scope, Dify-specific adaptation, or source/evidence
  truth boundary.
- Outcome/next step: Produce and review an initial M1 ontology design and shared test plan, then iterate
  the model against the agreed positive and negative Fixtures.
