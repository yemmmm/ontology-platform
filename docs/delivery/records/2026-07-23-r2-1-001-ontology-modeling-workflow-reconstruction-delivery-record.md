# R2.1-001 本体建模流程重构 Delivery Record

- Requirement source: `docs/requirements/requirements-v2.1.md` R2.1-001
- Status: M1/M2 已交付；M3 待实施；R2.1-001 长期迭代继续
- Started: 2026-07-23T17:11:19+08:00
- Last updated: 2026-07-24T17:32:30+08:00
- Worktree baseline: `1dc5d54` (Pause R2.0-002 and record ontology workflow rethink)
- Design: M1 uses its candidate artifacts; M2 execution contract is
  `docs/delivery/designs/2026-07-24-r2-1-001-m2-controlled-modeling-rehearsal-design.md`
- Shared test plan: M2 uses
  `docs/delivery/test-plans/2026-07-24-r2-1-001-m2-controlled-modeling-rehearsal-test-plan.md`

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

### 2026-07-24T01:31:52+08:00 — Authorize first minimal implementation without a formal design document — main agent + user

- Context: The user confirmed that M1 is an iterative modeling experiment and questioned whether a
  separate design document is needed.
- Decision: Do not create a standalone formal design or shared test-plan document for M1. The
  requirement entry fixes the business contract; the candidate ontology, Shapes, Fixture, executable
  query assertions, scenario README, and iteration record jointly carry the evolving design and
  lightweight acceptance checklist.
- Implementation boundary: Use a committed, offline-reproducible scenario pack and existing generic
  RDF, SHACL, RDFS reasoning, Context Query, and scoped SPARQL capabilities. Do not change platform
  product code or introduce Dify-specific behavior.
- Formal-design trigger: Only a separate requirement that adds platform API, storage, runtime,
  Dify-specific adaptation, or another hard-to-reverse architecture change requires a formal design.
- Outcome/next step: Review this minimal delivery plan, then implement and independently test the first
  candidate model.

### 2026-07-24T01:37:47+08:00 — Review M1 minimal delivery plan — plan reviewer + main agent

- Result: `PASS`; no evidence-backed Critical or High issue.
- Evidence: Current scoped SPARQL accepts standard read-only `SELECT` property paths; the development
  reasoner supports only RDFS subclass, subproperty, domain, and range entailments; managed Graph Sets
  separate ontology, data, and shapes graphs for validation, reasoning, and scoped query.
- Main-agent disposition: No findings required revision. Accept the reviewer assumptions as completion
  gates: isolate published, draft-only, and invalid Fixtures; use RDFS only for a separately stated
  supported entailment; compute transitive callers with scoped SPARQL; and exercise a managed workspace
  write/application path rather than claiming success from an ungoverned raw dataset load.
- Reviewer verification: 41 focused repository tests passed across the development reasoner, scoped
  SPARQL, SHACL validation, and reasoning service.
- Outcome/next step: Freeze the reviewed scope and hand it to the requirement developer.

### 2026-07-24T01:48:56+08:00 — Produce first candidate scenario package — requirement developer

- Stable state: Uncommitted worktree containing only the main-agent requirement/record updates and new
  files under `docs/evaluation-scenarios/dify-workflow-impact-m1/`; no platform product code changed.
- Artifacts: Candidate ontology and Shapes; isolated published, draft-only, invalid, and explicit-gap
  Fixtures; three scoped-SPARQL queries; immutable supplemental official source pack; one executable
  offline acceptance suite; scenario README; and iteration log.
- Modeling decision: Keep Tool Invocation as a first-class resource on Workflow Version. Compute caller
  reachability with SPARQL property paths, while limiting RDFS acceptance to a separately named
  subclass entailment supported by the development reasoner.
- Developer verification: `uv run --directory backend python
  ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` ran 9 tests successfully;
  `git diff --check` passed.
- Runtime state: Local service, backend health, and frontend were healthy. The developer did not create
  a runtime Project/Ontology; README records the governed semantic-edit path and a claimed Modeling
  Batch expressiveness limitation for independent verification.
- Outcome/next step: Freeze this state for independent contract and real-runtime testing.

### 2026-07-24T01:55:40+08:00 — Independent test Round 1 — requirement tester + main agent

- Result: `FAIL`. Offline acceptance passed 9/9 and 69 focused platform regressions passed, but the
  model did not satisfy the confirmed end-to-end context contract.
- Accepted High defect: The positive Fixture omitted C's `content:string` Input, represented the input
  Binding as `B.content -> B.content`, and did not relate B's IF/ELSE use to production of
  `approved_content`. The current query could therefore pass from independent facts without proving
  the required propagation path.
- Accepted High runtime defect: A fresh owned managed workspace proved that active runtime Modeling
  Batch dry-run is blocked by `SEMANTIC_PRODUCT_WRITE_MODE=legacy_only`. Governed ontology and Shapes
  edits succeeded, but the published Fixture with `validate=true` failed because the data-only
  candidate validation could not see the subclass axiom stored in the separate ontology graph.
- Main-agent disposition: Both findings are requirement-relevant and reproducible. Repair the missing
  Input/Binding/production semantics, add anti-cartesian assertions, and make the published Fixture
  pass governed validation without disabling validation or using a raw dataset loader. Treat the
  Modeling Batch runtime configuration as an explicit generic limitation; do not alter platform
  product code in M1.
- Cleanup: The tester verified ownership of the uniquely named temporary Project/Ontology, deleted the
  Project, and confirmed it returned 404 afterward.
- Detailed evidence: Scenario `iteration-log.md`, Independent test Round 1.
- Outcome/next step: Return confirmed defects to the requirement developer, then run Round 2.

### 2026-07-24T02:03:10+08:00 — Repair Round 1 defects — requirement developer

- Stable state: Repaired scenario package only; platform product code, requirements, delivery record,
  and the append-only failed Round 1 record were preserved.
- Model repair: Added C's current `content:string` Input, a real B-upstream-to-C-input Binding, an
  explicit IF/ELSE-to-`approved_content` production relation, stable call-site identifiers and
  locations, and explicit previous/current Change Set versions.
- Query/test repair: The context query now requires every C-to-B-to-A data-use link. Eleven offline
  tests include remove-and-swap mutations for nine critical links, direct base-type assertions for
  data-only SHACL, and a separately stated limited-RDFS entailment.
- Developer verification: 11/11 scenario tests passed; scenario test Ruff check and
  `git diff --check` passed.
- Real runtime evidence: In a fresh owned workspace, governed semantic edits for ontology, Shapes, and
  published Fixture all succeeded with `validate=true`; managed validation succeeded with
  `conforms=true`; reasoning succeeded with `consistent=true`; scoped SPARQL returned both A and B.
  The temporary Project was deleted and a follow-up GET returned 404.
- Residual limitation: Active runtime remains `product_write_mode=legacy_only`, so Modeling Batch's
  canonical writer cannot be used. No configuration or product-code change was made; the generic
  governed semantic-edit path is verified.
- Outcome/next step: Run independent Round 2 over the repaired model, property semantics, mutation
  assertions, and managed-runtime acceptance.

### 2026-07-24T02:07:09+08:00 — Independent test Round 2 — requirement tester + main agent

- Result: `FAIL`. All Round 1 repairs, 11 offline tests, 69 focused regressions, and fresh governed
  runtime validation/reasoning/scoped-SPARQL acceptance passed.
- Accepted High defect: `producesVariable rdfs:subPropertyOf derivedFromVariable` placed a
  `VariableUse -> Variable` predicate below a `Variable -> Variable` predicate. Standard RDFS closure
  therefore inferred B's IF/ELSE Variable Use to also be a Variable, collapsing a required concept
  boundary. The development reasoner's non-recursive implementation hid this invalid inference.
- Evidence: Independent `owlrl.RDFS_Semantics` closure reproduced the conflicting `rdf:type Variable`
  assertion. This is a semantic model failure, not a style preference.
- Main-agent disposition: Replace the incompatible superproperty with a domain-compatible generic
  relation, update the limited-RDFS expectation, and add a standards-based regression that forbids
  Variable Use from being inferred as Variable. Preserve all passing propagation and runtime behavior.
- Runtime/cleanup: Fresh governed writes with `validate=true`, validation, reasoning, and both scoped
  queries passed; the uniquely owned temporary Project was deleted and confirmed absent.
- Detailed evidence: Scenario `iteration-log.md`, Independent test Round 2.
- Outcome/next step: Apply the narrow TBox/test repair, then run Independent Round 3.

### 2026-07-24T02:09:30+08:00 — Repair Round 2 TBox defect — requirement developer

- Model repair: Introduced `referencesVariable` with the compatible
  `VariableUse -> Variable` domain/range; made `usesVariable` and `producesVariable` its
  subproperties; kept `derivedFromVariable` exclusively `Variable -> Variable`.
- Test repair: The limited development-reasoner expectation now infers `referencesVariable`. A
  standards-based RDFS closure regression verifies that B's IF/ELSE remains a Variable Use and is
  never inferred to be a Variable.
- Verification: 12/12 scenario tests passed; scenario test Ruff check passed; focused reasoner and
  validation tests passed 3/3; `git diff --check` passed.
- Runtime decision: No intermediate runtime was created because this repair changed only TBox
  hierarchy and inference assertions; Independent Round 3 was instructed to decide whether fresh
  runtime evidence was needed.
- Outcome/next step: Run Independent Round 3.

### 2026-07-24T02:12:06+08:00 — Independent test Round 3 — requirement tester + main agent

- Result: `PASS`.
- Semantic acceptance: Compatible property hierarchy and standard RDFS closure preserve the
  `VariableUse`/`Variable` concept boundary. The development reasoner produces only the declared
  compatible subproperty entailment.
- Executable acceptance: 12/12 scenario tests and 69 focused platform regressions passed;
  `git diff --check` passed. Source hashes, provenance layers, SHACL isolation, exact C-to-B-to-A
  context, draft separation, explicit gaps, limited/standard RDFS, and mutation resistance are covered.
- Fresh runtime acceptance: Because the TBox participates in reasoning, the tester created a fresh
  owned workspace and repeated governed `validate=true` ontology/Shapes/Fixture writes. Managed
  validation conformed, reasoning was consistent, and scoped context SPARQL returned one complete
  C-to-B-to-A row. No raw loader or validation bypass was used.
- Boundary verification: No Dify-specific platform code was added. The active
  `product_write_mode=legacy_only` Modeling Batch blocker remains explicit but does not block the
  verified generic governed semantic-edit path.
- Cleanup: The uniquely owned temporary Project was deleted and confirmed absent.
- Detailed evidence: Scenario `iteration-log.md`, Independent test Round 3.
- Outcome/next step: Synchronize requirement status, run final checks, and commit the M1 first version.

### 2026-07-24T02:14:08+08:00 — Final verification and documentation sync — main agent

- Requirement sync: Marked M1 first version implemented and independently accepted while keeping
  R2.1-001 in long-term iteration. Recorded the two failed rounds, final PASS, runtime boundary, and
  next-iteration status without claiming a final ontology design.
- Final executable checks:
  - Scenario acceptance: 12/12 passed.
  - Focused Modeling Batch, validation, reasoning, and Context Query regression suite: 69/69 passed
    with five pre-existing deprecation warnings.
  - Scenario test Ruff check and `git diff --check`: passed.
- Runtime health: `ontology-platform.service` remained active; backend `/api/health` returned
  `{"status":"ok"}`; frontend returned HTTP 200. No restart was required because only documentation,
  RDF/query Fixtures, and a scenario-local test were changed.
- Change-scope check: GitNexus reported zero changed symbols, zero affected processes, and low risk for
  the tracked documentation changes; manual status review confirmed the remaining additions are
  confined to the scenario package.
- Residual risk: Active `legacy_only` product write mode blocks Modeling Batch canonical apply. M1 uses
  the independently verified governed semantic-edit path; any product-mode or generic batch-
  expressiveness work must be a separate platform requirement.
- Delivery commit: Subject `Add minimal workflow impact ontology`; `git log -- <this record path>`
  resolves the immutable commit hash.

### 2026-07-24T09:53:33+08:00 — Split the next workflow proof into M2 and M3 — main agent + user

- Context: After accepting M1 as complete, the user agreed that the formal modeling path should be
  exercised by the main Agent before an autonomous modeling Agent is asked to discover both the
  workflow and the ontology at the same time. The user requested two explicit milestones.
- Decision: M2 is a controlled formal-path rehearsal in which the main Agent performs the M1 task
  through Project/Ontology/Build Session, Evidence, Modeling Batch dry-run/correction/apply, and
  post-apply semantic verification. M3 starts only after M2 passes and asks an autonomous modeling
  Agent to reproduce the M1 semantic behavior in a fresh workspace without answer-shaped ontology,
  Shapes, Batch payloads, or main-Agent semantic decisions.
- Boundary: Neither milestone may claim success through `semantic/edits`, raw loading, direct
  database writes, validation bypasses, or Dify-specific platform behavior. A continuing
  `legacy_only` or generic Modeling Batch expressiveness blocker must be classified and handled as
  configuration or a separately confirmed generic platform requirement.
- Acceptance direction: Compare semantic behavior rather than RDF graph identity. M2 must leave a
  complete append-only rehearsal log and minimal repeatable operating checklist. M3 additionally
  requires an independent consumer Agent to trace its impact explanation to platform facts while
  keeping final impact judgment outside the ontology and platform core.
- Outcome/next step: R2.1-001 now records M1 complete, M2/M3 refined, and M2 controlled modeling
  rehearsal as the next implementation stage.

### 2026-07-24T15:32:58+08:00 — Start M2 delivery and capture baseline — main agent

- Context: The user requested execution of the R2.1-001 M2 controlled modeling rehearsal.
- Baseline: Clean worktree at `8b640fa` (`Define M2 and M3 modeling milestones`). M1's immutable
  source pack, ontology, Shapes, four Fixtures, three queries, executable scenario tests, and prior
  iteration evidence are present under `docs/evaluation-scenarios/dify-workflow-impact-m1/`.
- Current behavior: M1 proved the semantic behavior through the generic governed semantic-edit
  path, while the active runtime was still recorded as `product_write_mode=legacy_only`; the
  formal Modeling Batch canonical path has not yet replayed the M1 task.
- Target and non-goals: M2 must use a fresh Project/Ontology/Build Session and the formal
  Evidence -> Modeling Batch dry-run/correction/apply -> post-apply verification path. It must not
  use semantic edits, raw RDF loading, validation bypasses, direct database writes, or Dify-specific
  platform behavior, and it does not require RDF graph identity with M1.
- Tooling evidence: GitNexus was 35 commits behind `HEAD`, so its initial search result is not used
  as current-path evidence; the index must be refreshed before code-impact decisions.
- Outcome/next step: Confirm the one execution-environment choice that can materially affect M2,
  then probe the active write mode and formal path.

### 2026-07-24T15:36:00+08:00 — Confirm isolated canonical-mode execution — user + main agent

- Decision: If `legacy_only` is only a configuration blocker, M2 may start a temporary isolated
  backend with canonical product writes enabled and continue through the formal Modeling Batch
  path.
- Boundary: Do not persistently change the regular `ontology-platform.service` configuration.
- Outcome/next step: Refresh code intelligence, probe the active configuration and formal-path
  contracts, and stop for separate requirement refinement if the blocker is generic Modeling Batch
  expressiveness rather than configuration.

### 2026-07-24T16:04:21+08:00 — Probe M2 formal-path assumptions — main agent

- Probe 1, active mode: Authenticated `GET /api/semantic/canonical-mode` on the regular service
  returned `canonical_store=legacy`, `product_write_mode=legacy_only`, and `read_mode=legacy`.
- Probe 2, isolated mode: A temporary backend on port 8012 started with
  `SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary`, `SEMANTIC_CANONICAL_STORE=rdf`, and
  `SEMANTIC_READ_MODE=canonical`; its authenticated mode endpoint returned those values. The
  regular service configuration was not changed.
- Probe 3, formal dry-run: In a fresh owned Project/Ontology/Build Session, one structured batch
  containing a Class, Datatype Property, and Shape passed the real Modeling Batch dry-run with
  `attempt_status=validated`. The only findings were non-blocking `missing_rationale` warnings.
  Project cleanup returned HTTP 204.
- Expressiveness conclusion: Modeling Batch does not accept arbitrary Turtle, `sh:sparql`,
  `sh:targetSubjectsOf`, or arbitrary `rdfs:subPropertyOf`. M2 can preserve the fixed behavior by
  using existing generic commands: Class parent links for RDFS inference, Object/Datatype
  Properties for topology and fields, target-Class Shapes for cardinality/pattern constraints, and
  an explicit-gap Class whose Shape requires `unknownDetail`. This is an allowed internal model
  change, not a Dify-specific platform extension.
- Code-intelligence evidence: GitNexus was refreshed to `8b640fa` before tracing
  `submit_modeling_batch -> ModelingBatchService.submit -> compile/validate/execute`.
- Outcome/next step: Freeze the minimal M2 execution design and shared test plan, then run the
  mandatory plan review.

### 2026-07-24T16:11:44+08:00 — M2 plan review Round 1 — plan reviewer + main agent

- Result: `REVISE`.
- Accepted High: Default Graph Set validation resolves role `shape`, while the default workspace
  registers role `shapes`; an empty Shape graph can therefore return `conforms=true` and create a
  false M2 PASS.
- Disposition: `accepted-high`. The design and test plan now require reading the Graph Set's
  `shapes` member, passing its IRI explicitly, reading the persisted validation run to prove the
  non-empty exact Shape set, and rejecting a known-invalid Invocation with that applied Shape.
- Confirmed assumption: Every object predicate constrained by a Shape is created with
  `create_property(object_class_id)`, and Fixture relations reference that exact `/property/{id}`
  IRI; no `/relation-type/{id}` versus `/property/{id}` mismatch is allowed.
- Evidence: `backend/app/services/ontology_workspace.py`,
  `backend/app/api/semantic.py`, `backend/app/mcp/tools/semantic.py`,
  `backend/app/services/semantic_validation.py`, and the revised M2 design/test plan.
- Outcome/next step: Re-review the revised plan before development handoff.

### 2026-07-24T16:13:40+08:00 — M2 plan review Round 2 — plan reviewer + main agent

- Result: `REVISE`.
- Accepted High: `SemanticValidationRunModel` persists `shape_graph_iris`, but the formal REST/MCP
  validation-run read model omits it, so the Round 1 persisted-run assertion was not executable
  through the stated public path.
- Disposition: `accepted-high`. The execution path now records the exact Graph Set member, explicit
  validation request, run ID and public run status. Independent testing uses a scenario-local
  read-only ORM verifier to assert the stored `shape_graph_iris`; it may not write SQL. The M3
  checklist remains formal-entry-only and proves Shape activation through explicit parameters plus
  a known-invalid rejection.
- Boundary decision: M2 will not add an API/MCP field solely for test observability. If the public
  field later becomes a consumer requirement, it must be refined as a separate generic platform
  capability.
- Evidence: `backend/app/repositories/models.py`,
  `backend/app/services/semantic_validation.py`, `backend/app/api/schemas.py`, and revised M2
  design/test plan.
- Outcome/next step: Re-review the executable evidence path.

### 2026-07-24T16:14:46+08:00 — M2 plan review Round 3 and development freeze — plan reviewer + main agent

- Result: `PASS`; no remaining Critical/High findings or unverified core assumptions.
- Closed findings: Explicit `shapes` member selection prevents empty-Shape false PASS; the
  scenario-local read-only verifier makes the persisted input assertion executable without adding a
  platform API; constrained object predicates and Fixture relations share exact `/property/{id}`
  IRIs.
- Frozen artifacts: M2 execution design and shared test plan dated 2026-07-24, this delivery record,
  requirement R2.1-001 M2, and clean code baseline `8b640fa` plus the listed uncommitted M2 docs.
- Development boundary: Implement the deterministic scenario package, exact reviewed payloads,
  append-only rehearsal log, minimal M3 checklist, and focused tests. Do not change the semantic
  contract, product code, requirement status, delivery record, or commit.
- Required verification: M1 scenario suite, focused Modeling Batch/validation/reasoning/Context
  Query tests, scenario Ruff, `git diff --check`, isolated runtime checks, and explicit no-bypass
  review.
- Outcome/next step: Hand the fixed scope to the requirement developer.

### 2026-07-24T16:26:31+08:00 — M2 development cycle 1 and main-agent review — requirement developer + main agent

- Development-ready state: Added only
  `docs/evaluation-scenarios/dify-workflow-impact-m2/`: REST rehearsal runner, safe ignored runtime
  record, read-only validation-run verifier, focused offline tests, append-only log template and M3
  checklist. No live run or product-code change occurred.
- Developer verification: M2 focused tests 4/4 passed; scenario Ruff and `git diff --check` passed.
- Main-agent review found confirmed pre-live defects:
  - `previousVersion` was attached to Version rather than Change Set;
  - the caller property path used zero-or-more and would include C itself;
  - the context query did not require the complete C -> B -> A input/binding/use path;
  - official, synthetic and Agent/model-contract Evidence were mixed;
  - Invocation Shape omitted call-site location;
  - a failed live run after workspace creation would not persist safe progress IDs.
- Impact: These defects could either fail the live assertion or produce a semantically incomplete
  PASS and an untraceable partial run. They are confined to the new scenario package; no indexed
  product symbol is edited.
- Outcome/next step: Repair the reviewed payload/query/Evidence/logging contract, strengthen focused
  tests, then return a new stable development-ready state before live execution.

### 2026-07-24T16:32:52+08:00 — M2 live rehearsal Round 1 — main agent

- Stable state: Repaired scenario package passed 5/5 focused tests, Ruff, and `git diff --check`.
- Result: `FAIL` at the draft Fixture dry-run; the runner stopped without using a bypass.
- Successful prior stages: Fresh Project `eca27355-177d-45ab-a8d0-bb27573ab242`, Ontology
  `458c1939-0c13-4f35-a34f-4470199dbc4f`, Build Session
  `c1ac6d1a-7395-4826-9256-1036c85850cb`, three Evidence layers, intentional bad-Shape
  rejection, corrected TBox/Shapes dry-run/apply, and published Fixture dry-run/apply.
- Failed Batch evidence: Batch `d68bdc03-c54a-4dca-b760-cd4f85cb5c47`, Attempt
  `9c9597f5-06c7-4a4b-895a-382c55bae145`, status `validation_failed`. Four relation Items returned
  `unresolved_item_ref`; candidate SHACL then rejected the incomplete Change/Version structure.
- Root cause: `item_ref` is scoped to one Modeling Batch. The draft payload referenced `c`, `c-v2`
  and `c-quality-score` from the already applied published Batch as if they were current-Batch
  Items.
- Evidence preservation: The safe runtime record was archived locally as
  `runtime/runtime-record-0d952d8711d7.json`; the append-only rehearsal log records the owned
  workspace. No API key, lease token, header, cookie, direct DB/RDF write, semantic edit, raw load,
  or validation bypass was used.
- Outcome/next step: Resolve cross-Batch references to the emitted existing entity IRIs, preserve
  run-specific failure records, and link the corrected live round to `0d952d8711d7`.

### 2026-07-24T16:37:21+08:00 — M2 defect repair and live rehearsal Round 2 — developer + main agent

- Repair: Draft Fixture relations now use emitted entity IRIs for resources applied by the
  published Batch; only resources declared in the current draft Batch use `item_ref`. The runner
  also preserves one ignored runtime record per run, accepts `--corrects-run-tag`, and records a
  failed dry-run response before asserting its expected status.
- Pre-live verification: M2 focused tests passed 5/5, scenario Ruff passed, and
  `git diff --check` passed.
- Result: `PASS`; corrected run tag `2fde5cd4f165` explicitly corrects failed run
  `0d952d8711d7`.
- Owned workspace: Project `94dcff15-dc45-40d3-b85f-b9318d96aef6`, Ontology
  `a093b881-f2ad-4fc9-aaa5-541e77a01992`, Build Session
  `f17db96f-c78f-4fbd-9089-b66899458469`.
- Evidence layers: official `abc6301e-9ab4-4f8f-a8d0-013bc2dae891`, synthetic Fixture
  `86fa990a-ef1f-49a6-bca7-287f6baf9bcf`, and model contract
  `e8b68a43-0c98-4367-bb0c-4860185c4f5b`.
- Modeling gates: The intentional bad Shape and known-invalid Invocation both stopped at
  `validation_failed` with `shacl_violation`. Corrected TBox/Shapes, published Fixture, draft
  Fixture, and explicit-gap Batches each passed dry-run and `apply_atomic`.
- Managed services: Validation run `9225a4fc-d693-45b0-b5f8-473c1721c2a0` succeeded with
  `conforms=true` using the exact Shapes graph
  `http://ontology-platform.local/semantic/graph/shapes/a093b881-f2ad-4fc9-aaa5-541e77a01992`.
  The scenario-local read-only ORM verifier confirmed the exact persisted `shape_graph_iris`.
  Reasoning run `37bc96ef-de33-4856-962c-46d27b84b32d` succeeded with `consistent=true`, created
  its result graph, and exposed the expected subclass entailment.
- Query acceptance: published callers returned exactly B and A; exact C -> B -> A context returned
  one complete row; draft/latest separation and the explicit known-gap/unknown-detail result each
  returned one row.
- Isolation and traceability: The normal service stayed in `legacy_only`; the isolated backend ran
  in `rdf_primary` canonical mode. No semantic edit, raw dataset load, direct DB/RDF write,
  `validate=false`, credential disclosure, or Dify-specific platform change was used. Safe local
  records are `runtime/runtime-record-0d952d8711d7.json` and
  `runtime/runtime-record-2fde5cd4f165.json`.
- Outcome/next step: Freeze this state for independent requirement testing. Retain both owned
  Projects and their immutable Batch/Attempt evidence until testing and M3 handoff are complete.

### 2026-07-24T16:48:37+08:00 — M2 independent acceptance and closure — requirement tester + main agent

- Independent result: `PASS`; all M2 completion gates are met and no product defect or retest loop
  is required.
- Regression evidence: M1 scenario passed 13/13, M2 scenario passed 5/5, focused Modeling Batch,
  validation, reasoning and semantic-context backend tests passed 69/69, scenario Ruff and
  `git diff --check` passed.
- Runtime evidence: The tester independently re-read both retained Projects, their three-layer
  Evidence, Build Session, Batch/Attempt histories, Graph Set, validation and reasoning runs. It
  repeated the scoped queries with callers=2 (B/A), exact context=1, draft=1 and gap=1.
- Negative evidence: An independent dry-run against the same applied Shapes produced Batch
  `b12bf02c-32a6-4dd5-927a-0e5da84499e6` / Attempt
  `c510c80a-04dc-417c-808c-4901eed6180e`, stopped with one `shacl_violation`, and had no apply
  attempt or workspace after-version.
- Shape activation: The read-only verifier confirmed validation run
  `9225a4fc-d693-45b0-b5f8-473c1721c2a0` persisted exactly the expected singleton
  `shape_graph_iris`; it performed no database write.
- Boundary evidence: Static and runtime review found no semantic edit, dataset load, direct
  DB/RDF write, `validate=false`, Dify-specific product path, credential, lease token, cookie or
  Authorization value in the tracked artifacts.
- Runtime closure: The isolated `127.0.0.1:8012` backend was stopped after acceptance. The regular
  systemd unit remained active; backend `8001` health returned OK, frontend `5173` returned HTTP
  200, and authenticated canonical-mode remained `legacy_only`.
- Documentation: Requirements v2.1 now records M1/M2 complete and M3 as the next implementation;
  v2.0 cross-reference, M2 design, shared test plan, README, rehearsal log and minimal handoff
  materials are synchronized to the accepted result.
- Retention: Success Project `94dcff15-dc45-40d3-b85f-b9318d96aef6` and failed Project
  `eca27355-177d-45ab-a8d0-bb27573ab242` remain intentionally retained for traceability and M3
  handoff. Local runtime JSON remains ignored and is not committed.
- Outcome/next step: Commit the scoped M2 delivery. R2.1-001 remains iterative; the next requirement
  stage is M3 autonomous modeling Agent reproduction.

### 2026-07-24T17:32:30+08:00 — Distill M2 lessons for M3 — main agent

- User request: Preserve the modeling lessons from M2 as reusable M3 documentation.
- New artifact:
  `docs/evaluation-scenarios/dify-workflow-impact-m2/m3-reusable-lessons.md`.
- Reusable content: mode preflight, Evidence separation, dependency-ordered Batches, Batch-local
  `item_ref`, immutable dry-run correction, explicit `shapes` selection, positive plus negative
  validation controls, layered semantic gates, behavior-based acceptance, explicit unknowns,
  safe progress records and the human-intervention boundary.
- Input-isolation correction: The prior minimal checklist pointed M3 to `run_rehearsal.py`; that
  script contains M2's final answer-shaped payload and would invalidate autonomous reproduction.
  The checklist now describes only formal generic calls and explicitly forbids M3 from reading or
  executing the runner. Requirements v2.1 and the scenario README carry the same boundary.
- Scope decision: This is documentation and handoff hardening only. It does not change platform
  behavior, M3's semantic acceptance criteria or the M2 implementation, so no new design/review/test
  cycle is required.
- Outcome/next step: Use the new lessons document and revised checklist as M3's process inputs;
  withhold M1/M2 model artifacts, payloads, runtime records and answer-shaped query results.
