# R1.2-005 Rule Definition Query and Trigger Explanation Delivery Record

- Requirement source: `docs/requirements/requirements-v1.2.md`, R1.2-005
- Status: delivered (documentation-only; product requirement remains `未实现`)
- Started: 2026-07-20T21:17:20+08:00
- Last updated: 2026-07-20T23:17:28+08:00
- Design: `docs/delivery/designs/2026-07-20-r1-2-005-rule-definition-read-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-20-r1-2-005-rule-definition-read-test-plan.md`
- Delivery baseline: clean detached worktree at `326c966d2f994610e186f1017caec8f46ff307b9`
- Delivery commit: `Refine R1.2-005 rule definition read` (resolve immutable hash with
  `git log -- docs/delivery/records/2026-07-20-r1-2-005-rule-definition-explanation-delivery-record.md`)

## Confirmed contract

- Current behavior: the fixed Ontology `rules` read model exposed through REST/MCP returns Rule
  identity, status, current definition ID, version, and name only. The separate REST
  `/api/semantic/rule-definitions` surface serializes the stored definition body, but the normal
  consumer-Agent MCP path has no Ontology-scoped rule-detail or resource-trigger explanation
  contract. Rule execution and lineage records exist, with exact premise support for eligible
  Platform DSL results and coarser proof for other engines.
- Target behavior: provide an authorized, explicit REST/MCP drill-down that returns the stored
  current active Rule Definition body and minimal identity/currentness metadata. The consuming
  Agent interprets the definition together with facts, derived statements, and lineage obtained
  from existing query capabilities.
- In scope: refine the smallest public REST/MCP contract needed to read the current Rule Definition
  body for every supported Rule language, with authorization, identity, and currentness behavior.
- Non-goals: no platform-side trigger evaluation or explanation; no normalized condition tree,
  comparison, threshold, binding, matched-value, or resource-specific explanation response; no
  enlargement of ordinary Context Query/recall results; no Dify-specific production branches; no
  effective classification or Class-hierarchy materialization owned by R1.2-006; no exposure of
  secrets or undocumented engine internals; and no product implementation in this delivery.
- Acceptance summary: an authorized consumer Agent can read the current stored definition body for
  the Dify Platform DSL fixture and identify `total_tokens >= 50000` plus its direct result template.
  Existing facts and lineage remain responsible for actual values and derived statements; the Agent
  composes and explains them. At least one non-Platform-DSL definition proves raw-body retrieval is
  language-neutral. This delivery freezes reviewed documentation only and leaves the requirement
  `未实现`.
- Refinement: in progress. The prior R1.2-004 audit identified that unconditional normalized
  condition/comparison/threshold fields fit Platform DSL but cannot be faithfully guaranteed for
  every supported `sparql_construct` or `workflow_state_machine` definition. The user requires a
  minimal delivery and does not want ordinary recall/context responses enlarged with rule detail;
  rule definition and trigger explanation are an explicit, on-demand drill-down.

## Timeline

### 2026-07-20T21:17:20+08:00 — source and current-state audit — main agent

- Context: R1.2-005 is `未实现` and depends on the v1.2 consumer query loop plus v1.0 lineage and
  semantic-context foundations. The worktree started clean and detached.
- Action/decision: read the authoritative requirement, v1.0 R-005/R-006 contracts, the prior v1.2
  boundary audit, the fixed Rules read model, rule-definition API/service, MCP registration, and
  rule-language validators/execution path. Treat the requirement as a new refinement, not the
  already-delivered v1.0 R-005 lineage requirement.
- Evidence: `docs/requirements/requirements-v1.2.md`; `docs/requirements/requirements-v1.0.md`;
  `docs/delivery/records/2026-07-20-r1-2-004-related-query-aggregation-delivery-record.md`;
  `backend/app/api/modeling_batches.py`; `backend/app/api/semantic.py`;
  `backend/app/services/semantic_rule_definition.py`;
  `backend/app/services/semantic_rule_execution.py`; `backend/app/mcp/tools/modeling_batches.py`;
  GitNexus query for Rule definition and execution paths.
- Outcome/next step: resolve the cross-language public response shape first, then refine actors,
  inputs, outputs, evaluation versus recorded execution, failure/currentness semantics,
  permissions, history, and acceptance scenarios one consequential question at a time.

### 2026-07-20T22:13:23+08:00 — minimal consumption boundary — user and main agent

- Context: the user considers the existing recall response sufficiently dense and wants R1.2-005
  delivered in the simplest form with minimal consumer-Agent interpretation cost.
- Action/decision: rule definition detail and trigger explanation will be opt-in drill-down
  information. Ordinary Context Query/recall responses will not embed full rule bodies, normalized
  conditions, matched values, bindings, or lineage trees. They may retain the existing compact Rule
  identity/version/status and stable identifiers needed to request detail.
- Evidence: user refinement decision; current Context Query already returns compact Rule metadata,
  while the fixed Rules read model exposes stable Rule/current-definition identifiers.
- Outcome/next step: refine the smallest drill-down contract and avoid adding cross-language
  normalization unless an acceptance case actually requires it.

### 2026-07-20T22:33:09+08:00 — raw-definition contract and documentation-only scope — user and main agent

- Context: the user confirmed that a consumer Agent can understand the stored rule source and does
  not need a second platform-authored semantic explanation. The user also limited this delivery to
  requirement design and documentation.
- Action/decision: remove the proposed resource-trigger explanation endpoint and all platform-side
  rule normalization/evaluation from R1.2-005. The future product delta is limited to authorized,
  on-demand current Rule Definition reads over public REST/MCP with minimal metadata. Existing
  semantic facts, derived statements, run/currentness state, and lineage remain separate inputs that
  the consuming Agent interprets. This delivery will update the requirement, write one design and
  one shared test plan, run the mandatory plan review, and commit documentation only; it will not
  edit backend/frontend code, run implementation testing, restart services, or mark R1.2-005
  implemented.
- Evidence: user refinement confirmation; current REST Rule Definition response already serializes
  `body`, while the consumer MCP Rules read path returns only summary/current-definition identity.
- Outcome/next step: confirm whether the existing REST definition-by-ID contract should remain the
  canonical read and receive only a thin MCP counterpart in the future implementation plan.

### 2026-07-20T23:09:37+08:00 — contract freeze and documentation draft — user and main agent

- Context: the user confirmed that the existing REST Definition-by-ID contract remains canonical
  and the future product delta is only a thin MCP counterpart.
- Action/decision: rewrote R1.2-005 as `规则活动定义按需读取`; froze a one-input
  `get_semantic_rule_definition(rule_definition_id)` MCP design that reuses existing service,
  authorization, and serialization; wrote one shared future product test plan. Kept ordinary Rules
  and Context responses compact, and kept this delivery documentation-only.
- Evidence: `docs/requirements/requirements-v1.2.md` R1.2-005;
  `docs/delivery/designs/2026-07-20-r1-2-005-rule-definition-read-design.md`;
  `docs/delivery/test-plans/2026-07-20-r1-2-005-rule-definition-read-test-plan.md`.
- Outcome/next step: run the mandatory independent plan-review gate against the real repository and
  dispose of every evidence-backed Critical/High finding before documentation closure.

### 2026-07-20T23:13:42+08:00 — plan review Round 1 — plan reviewer and main agent

- Context: the reviewer returned `REVISE` with two evidence-backed High findings and no Critical.
- Action/decision: accepted both High findings. First, direct Rule Definition creation changes the
  Rule's `current_definition_id` without always marking the former Definition `superseded`, while
  Modeling Batch replacement does mark it; the plan now makes the current pointer the sole
  authority and does not expand 005 into lifecycle repair. Second, existing HTTP/MCP pre-auth maps
  unresolved and foreign IDs differently; the plan now requires no unauthorized body disclosure
  but does not promise new cross-transport error normalization.
- Evidence: `backend/app/services/semantic_rule_definition.py` `create_rule`;
  `backend/app/services/modeling_batches.py` `_apply_rule`; `backend/app/security/http.py`
  authorization mapping; `backend/app/mcp/runtime.py` `_authorize_tool`; reviewer Round 1 report.
- Outcome/next step: revised requirement, design, and shared test plan to preserve the approved
  minimal transport-only delta; send the changed plan back for Round 2 review.

### 2026-07-20T23:15:34+08:00 — plan review Round 2 — plan reviewer and main agent

- Context: Round 2 returned `REVISE` because four stale phrases still contradicted the accepted
  Round 1 dispositions; it found no new design issue and no Critical.
- Action/decision: accepted the remaining High consistency findings. Removed test assumptions that
  an old Definition is `superseded`; replacement tests now compare IDs and the fresh current pointer
  while preserving the exercised write path's stored status. Removed remaining not-found/error
  parity promises; success payloads remain equal, while failure tests only assert no Definition data
  and accept current transport-specific mappings.
- Evidence: reviewer Round 2 report; corrected design sections 4.3/4.4 and test-plan sections 2, 3,
  4.3.
- Outcome/next step: submit the fully aligned documents for Round 3 review.

### 2026-07-20T23:16:45+08:00 — plan review Round 3 — plan reviewer and main agent

- Context: the fully corrected requirement, design, and shared test plan were re-reviewed against
  the real repository.
- Action/decision: reviewer returned `PASS` with no remaining evidence-backed Critical/High issue.
  It confirmed current-pointer authority, unchanged stored old-definition status, success-payload
  parity only, failure-without-Definition-data semantics, multi-language raw-body coverage, and the
  documentation-only completion boundary.
- Evidence: reviewer Round 3 report; `git diff --check` clean.
- Outcome/next step: close documentation consistency checks, run GitNexus change detection, and
  commit the reviewed artifacts without product implementation or runtime restart.

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | old Definition is not always marked `superseded` | accepted-high | direct service and Modeling Batch paths differ | use `current_definition_id` only; no lifecycle repair |
| 1 | unknown and foreign IDs have differing REST/MCP error mappings | accepted-high | HTTP and MCP pre-auth branches differ | require no body disclosure; no new error normalization |
| 2 | test plan retained `superseded` fixture assumptions | accepted-high | stale sections 2 and 3 contradicted Round 1 | assert pointer/ID only; preserve stored status |
| 2 | design/test retained error-category parity wording | accepted-high | stale sections 4.3/4.4 and test cases contradicted Round 1 | success parity only; failure means no Definition data |
| 3 | no Critical/High finding | PASS | full reviewer recheck against repository | no further plan change |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

## Final verification

- Required checks: requirement/design/test-plan/record path and terminology consistency passed;
  linked Markdown paths exist; `git diff --check` passed; mandatory plan review passed after three
  rounds. GitNexus `detect_changes(scope=all)` reported low risk, zero changed symbols, and zero
  affected processes for the tracked documentation diff.
- Runtime/restart health: intentionally not run because no backend/frontend/runtime code changed and
  implementation is explicitly deferred.
- Documentation/status sync: R1.2-005 is renamed and narrowed in the authoritative v1.2 requirement;
  reviewed design and shared test plan are linked; product status remains `未实现`; current API/MCP
  references are unchanged because the future MCP tool does not exist yet.
- Cleanup: no test or runtime data was created; no cleanup required.
- Residual risks and follow-ups: future implementation must perform fresh symbol/API impact analysis,
  register the read-only `PROJECT_RESOURCE` MCP policy/tool, reuse the existing Definition service,
  pass the shared plan and independent testing, update generated MCP docs, restart/verify runtime,
  and only then mark R1.2-005 implemented.

## Retrospective

- Scope or design deviations: the original requirement proposed normalized trigger explanations.
  User refinement intentionally reduced it to on-demand raw Definition reads and Agent-side
  interpretation, with no product implementation in this delivery.
- Rework and root causes: plan-review Rounds 1 and 2 removed assumptions that every old Definition
  is `superseded` and that REST/MCP failure mappings are identical. Both assumptions came from
  extrapolating one code path into a universal contract.
- What shortened or delayed delivery: reusing the existing REST schema/service and existing compact
  `current_definition_id` eliminated new response models, normalization, evaluation, migrations,
  UI, and runtime work. Two extra review rounds were needed to remove stale wording completely.
- Reusable lessons: for thin transport parity, promise parity only where the shared implementation
  actually exists; use explicit current pointers rather than secondary status fields when write
  paths maintain lifecycle state differently.
