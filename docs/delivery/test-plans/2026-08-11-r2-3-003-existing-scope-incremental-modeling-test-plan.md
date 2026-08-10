# R2.3-003 Existing-scope 增量建模共享测试计划

- 状态：Approved；plan review PASS；deterministic Round 1 PASS，真实 L0-L2 待执行
- 需求：`docs/requirements/requirements-v2.3.md#R2.3-003-已有-projectontology-增量建模`
- 设计：
  `docs/delivery/designs/2026-08-11-r2-3-003-existing-scope-incremental-modeling-design.md`
- 交付记录：
  `docs/delivery/records/2026-08-11-r2-3-003-existing-scope-incremental-modeling-delivery-record.md`
- 共享规则：所有后续独立测试 round 追加在本文末尾，不另建竞争测试文档。

## 1. 完成门

只有以下各组全部 PASS 才可把 R2.3-003 标记为完成：

1. requirement/source/design/test artifacts 一致且 digest 稳定；
2. R2.3-005 formal create 合同无回归，R2.3-003 formal existing 合同 fail closed；
3. R2.3-003 专属 ledger、零 cap 和 `user-20260811-r23003-start1-4` 精确四 start 授权边界正确；
4. existing-scope live drift preflight 在任何副作用前完成；
5. 真实增量 Batch 不覆盖 Start75 既有模型，workspace 单调前进；
6. validation/reasoning、governed retrieval、Evidence/lineage 和两条 CQ 在同一最终 model state PASS；
7. 独立 tester 完成只读复核，清理完成，服务健康；
8. 文档、状态、delivery record 与 commit closure 完成。

## 2. 确定性测试

### T1 — Source bundle

- JSON manifest schema/paths 合法，所有 base/incremental SHA-256 与文件字节一致；
- 新资料只陈述业务事实，不含 Class/predicate/IRI/Shape/Modeling Item、平台命令或预期 CQ 答案；
- Modeling 可见批准 source，Coordinator/Acceptance/Protocol 不越权获得 raw source；
- Start75 retained evidence 和旧 source 文件字节不变。

### T2 — Formal contract isolation

- 精确的 R2.3-005 Task/Profile/manifest 只接受 `scope=create`；
- 精确的 R2.3-003 Task/Profile/manifest 只接受冻结的 `scope=existing` 与 exact handoff；
- 005/003 交叉 Task/Profile/manifest、未知 requirement、任意 IDs/path、symlink、digest drift 全部在副作用前
  拒绝；
- 005 的 candidate/Acceptance/settlement/provider/cleanup 回归不变。

### T3 — StartLedger

- `.r2-3-003-start-ledger.jsonl` 与 002/005 namespace/lock 隔离；
- 初始 cap/count/active 为 `0/0/0`，未授权 reserve 失败且不创建 run root；
- 空账本只接受一次 exact `initial_authorization +4`；prior-failure 不适用于该事件，重复/伪造/顺序错误
  授权失败；后续普通 budget extension 仍执行严格 predecessor；
- success-stop 后剩余 start 不消费；mutation 后 terminal 未对账时新 start 被拒绝；
- replay、append、locking、baseline binding 与 previous terminal 顺序稳定。

### T4 — Existing preflight

- live Project/Ontology/ownership/default Graph Set/workspace version/Build Session/Lease/Attempt 全部匹配时通过；
- 既有历史 batch/completed session 是合法 baseline，不触发空作用域错误；
- missing、wrong owner、wrong Ontology、workspace drift、active Lease/Session、in-flight Attempt、fence 任一情况
  在 ledger/run root/credential/Agent/Build Session 副作用前失败；
- retained state 文件不能替代 live API 回执；credential/error 原文不进入 evidence。

### T5 — Delta candidate and application

- candidate 是完整本轮增量，不重发 Start75 全 candidate，不接受 patch-only revision；
- `existing_entity_ref` 只含平台中立 semantic ID/expected Class，不含 IRI；binding receipt 从 live read
  生成并绑定 candidate/scope/workspace，missing/duplicate/class mismatch fail closed；
- 005 translator 拒绝 existing binding 输入且 create plan 字节不变；003 translator 不为 existing ref 发
  create/update，只用 receipt IRI 生成新 relation；所有新增关系有 source citation；
- 每阶段先 dry_run 再 apply_atomic，expected workspace version 严格串联；
- old ExplicitUnknown、label/question/rationale/relations/Evidence/lineage 前后保持；
- resolution、新 policy 和 concrete case 均有新 Evidence/lineage；
- invalid probe 被 validation_failed 拒绝且零 mutation；任一 apply 不确定时 fail closed。

### T6 — Acceptance and settlement

- 两条 CQ 顺序固定，第二条合并 no-score policy 与 concrete case；两轮各自 fresh Source/Platform Examiner，
  上一轮 child 已回收后才启动下一轮；
- ticket 不含预期答案、Producer 对话或旧 verdict；
- Source/Platform 两侧独立得出答案；两份 CQ Acceptance verdict 与四份 Examiner report 绑定同一
  最终 model state；
- 任一新 write 使全部旧 verdict 失效；
- terminal 顺序、settlement CAS/readback、Team settled 和 aggregate cleanup 保持 005 已验收合同。

### T7 — Failure and cleanup

- mutation 前失败允许在剩余授权内 fresh retry；
- mutation 后同一 Team 的修订使用新 Batch 和新 final model state；
- mutation unknown、terminal-after-apply 或 readback 不一致阻止新 start 和自动删除；
- existing Project/Ontology 永远保留；本轮 Session/Lease/key/Agent/Examiner/proxy/run-private secret 精确清理；
- cleanup failure 作为附加事实保留，不覆盖第一阻断分类。

## 3. 真实运行测试

用户已授权精确四次 R2.3-003 semantic starts。真实运行只在 clean committed baseline 和 deterministic
PASS 后进行；首个完整 PASS 后 success-stop。

### L0 — Start and scope

- 20 分钟内进入第一个真实 semantic modeling start；只做安全启动所需最小 preflight；
- 使用 exact Start75 Project/Ontology 和 live workspace version；全新 Team/Agent/Session/Lease/run root；
- 首次 Agent turn 前 source visibility、Protocol-only MCP 和 forbidden-path probe PASS。

### L1 — Modeling quality

- 直接检查 Modeling 完整增量 candidate、Protocol receipt 与每阶段 dry-run/apply/readback；
- 核对两个 unknown 的 source-bounded resolution、新 decision/publication slice、旧模型回归、显式范围外；
- validation conforms、reasoning consistent、required path retrieval 完整、非截断、有 Evidence/lineage；
- 不使用本次专用硬编码验收程序替代直接证据。

### L2 — Independent semantic acceptance

- 两轮 fresh Examiner 均形成终态；两条 CQ current/usable PASS 且绑定同一 final model state；
- 独立 tester 在 Producer settled 后只读核验 source、platform receipts、query results、verdict、settlement 和
  cleanup，不创建/继续 run、不修改 retained evidence。

## 4. Repository-required checks

实现期间至少运行：

```text
cd backend && uv run pytest
python -m pytest modeling_team/tests
```

如改动前端则追加 `cd frontend && npm run build` 与 `cd frontend && npx playwright test`；若只改 backend/
modeling_team，不把前端测试设为无关完成门。代码变更完成后按 AGENTS.md 重启
`ontology-platform.service`，核验 backend `8001/api/health` 与 frontend `5173/`。

提交前必须运行 GitNexus `detect_changes(scope=compare, base_ref=main)`；若索引刷新仍被 invalid UTF-8 阻断，
记录精确 blocker，并以 git diff、目标测试和完整 suite 补充范围证据，不伪称 GitNexus 已完成。

## 5. 已执行的设计前探针

### 2026-08-11 Probe 1 — existing-resource 增量机制

- 方法：阅读当前 ModelingBatch/command compiler/canonical write 实现，运行 4 个目标测试。
- 命令：
  `cd backend && uv run pytest -q tests/test_semantic_command_compiler_stage2.py::test_update_entity_replaces_label_aliases_and_properties tests/test_semantic_canonical_write_stage2.py::test_update_entity_apply_replaces_label_aliases_and_properties tests/test_modeling_batches_service.py::test_multiple_relation_targets_for_same_subject_and_type_are_valid tests/test_modeling_batches_service.py::test_rule_only_apply_versions_logical_rule_and_changes_workspace_version`
- 结果：`4 passed, 3 warnings`。
- 结论：现有平台支持本需求所需的字段级 update、existing IRI 关系、rule 和 workspace version 前进；无需新增
  Dify 专属平台能力。

### 2026-08-11 Probe 2 — formal Runner 差异

- 方法：检查 `preflight.py`、`runner.py`、`start_ledger.py`、`contracts.py`、`model_manifest.py` 和 005 Task/Profile。
- 结果：当前 formal path 精确绑定 R2.3-005/create；003 需要设计第 4.2 节的窄正式合同扩展。
- 结论：不能把 config-only 方案交给开发。

### 2026-08-11 Probe 3 — retained scope

- 方法：本机 PostgreSQL 只读查询与未授权 API GET。
- 结果：Start75 P/O 存在，Session completed、Lease released；API 对资源 GET 返回 401。
- 结论：设计可继续，但真实启动必须用新 credential 完成 live workspace drift preflight。

## 6. Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

### Round 1 — 2026-08-11 independent deterministic contract test — FAIL / real run BLOCKED

- Stable state: development-stopped uncommitted worktree at `84b0abf655e7cac8068e634c4cb90cb2932be6d0`;
  `git diff --check` PASS. The implementation/test worktree was not reset or reverted. No semantic
  modeling run, Agent, Build Session, Lease, credential, platform write, or retained-evidence mutation
  was performed by this round. Before and after hashes were unchanged for the retained Start75 tree
  (`22750e36caeedb11bfc3ab9613fe66f85d45df01f63d43188c61205e5ded0634`) and the L3 source tree
  (`457549bdf325d6b0c4f796a762474dd79c90d5b55d5b922fb1bd28799ae23cf4`). R2.3-002 and R2.3-005
  ledger hashes were unchanged; the R2.3-003 canonical ledger did not exist before or after this
  read-only round.
- Commands and results:
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py -q`:
    PASS, 6 tests. This covers exact R2.3-003 formal assets, frozen Start75 handoff, cap `0` before
    authorization, exact initial `+4`, duplicate/early authorization rejection, live-preflight evidence
    sanitization and ordering, existing-entity binding/translation, 005 rejection, and non-empty
    existing cleanup without deletion.
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_contracts.py modeling_team/tests/test_r23005_ledger_isolation.py
    modeling_team/tests/test_platform_scope.py -q`: PASS, 65 tests, 32 subtests. This covers 005/003
    formal and ledger namespace isolation, fail-closed preflight ordering, and retained-scope cleanup.
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23005_sequential_cq.py
    modeling_team/tests/test_r23005_c_settlement.py modeling_team/tests/test_r23005_ticket_pipeline.py
    modeling_team/tests/test_acceptance_child_start_host_derived.py modeling_team/tests/test_r23005_t6_repeatability.py -q`:
    PASS, 40 tests. This covers the frozen two-CQ order, second-round prior-child cleanup, same-final-state
    settlement/CAS, terminal ordering, idempotent aggregate cleanup, and child residue checks reused by 003.
  - `uv run --project backend python -m pytest modeling_team/tests -q`: PASS, 700 passed, 1 skipped,
    218 subtests. `cd backend && uv run pytest`: PASS, 843 passed, 10 skipped. These are the full
    modeling-team and backend regression suites available in the repository environment.
  - Formal CLI smoke (read-only): matching 003 and 005 `validate` commands both exit `0` and return the
    exact four-role roster; 003 and 005 `baseline` commands both exit `0` with formal manifest paths and
    SHA-256 bindings. Both cross-wired `validate` pairs exit `2` with
    `validation failed: unknown or cross-wired formal run contract`. No smoke run root was created.
  - Source-bundle read-only checks: all 5 base and 2 incremental manifest paths exist, are not symlinks,
    and their SHA-256 values match `manifest.json`; incremental sources contain no detected IRI/predicate/
    Shape/Modeling Item/MCP/platform-command/expected-answer leakage. A direct preflight matrix accepted
    completed historical Batch/Session and rejected wrong Project/Ontology, workspace drift, active
    Session/Lease/Attempt/fence, and active historical Session. A direct binding matrix accepted the
    receipt-backed existing IRI relation and rejected missing/duplicate/class-mismatch/invalid-IRI/
    missing-evidence, candidate-digest, receipt-digest, and 005 cross-use inputs before translation.
  - Runtime health (no restart was needed for this read-only round): `ontology-platform.service` active;
    backend `GET /api/health` returned `{"status":"ok"}`; frontend `/` returned HTTP `200`.
- Environment classification: the plan's literal `python -m pytest modeling_team/tests` could not start
  because `python` is absent (`exit 127`). The equivalent `python3 -m pytest modeling_team/tests` reached
  collection but was blocked by the global environment's incompatible `pydantic-settings`/`pydantic`
  installation (`ModuleNotFoundError: pydantic._internal._signature`). The repository backend `uv` environment
  supplied the successful commands above; these environment issues are not product defects.
- Unexecuted/blocked scope: real L0 start, live existing-scope credential/API preflight against Start75,
  Modeling candidate, binding receipt from the live read model, dry-run/apply/readback, validation/reasoning,
  governed retrieval, semantic two-CQ verdicts, settlement, and production cleanup were intentionally not
  run per the tester instruction not to create or continue a real modeling run. They are `BLOCKED`/unexecuted,
  not PASS. Therefore the requirement-level completion gate remains BLOCKED pending an authorized real run
  and independent read-only acceptance.
- Defect 1 — **High, platform-contract/fail-closed ordering**: existing live-drift preflight is not the
  first credential-side-effect gate. Reproduction: inspect a formal R2.3-003 `TeamRunner.prepare` call with
  a missing/invalid DeepSeek credential and an injected/live existing-scope probe; at
  `modeling_team/runner.py:362-369`, `preflight_deepseek_credential(...)` runs before the existing-scope
  `run_existing_scope_preflight(...)` at `:403-414`. Expected: verify the exact live Project/Ontology,
  ownership, Graph Set, workspace version, and inactive Session/Lease/Attempt/fence first, then read/bind
  the formal credential, and only then reserve the ledger/create a run root. Actual: credential read and
  its failure can occur before the required existing-scope live-drift gate. Evidence: source inspection
  above; the successful focused tests do not assert this credential-vs-live-preflight ordering. The
  developer should repair this narrow ordering and add a regression that proves a live-scope rejection
  happens before credential read or any other side effect, then request Round 2. The same High preflight
  repair scope includes malformed/missing identity: a direct `canonical_existing_scope_preflight` probe
  with an otherwise valid live response but Project GET body `{}` returned `scope_disposition=retained`
  because `project.get("id", project_id)` defaults the missing ID to the requested path. Expected: a
  missing Project identity is rejected fail-closed before any later scope use. Round 2 must add and pass
  the missing-id/malformed Project regression as well as the credential-vs-live-preflight ordering check.
- No other defect was found in the executed deterministic scope. The real L0 start, live existing-scope
  credential/API preflight against Start75, Modeling candidate, binding receipt from the live read model,
  dry-run/apply/readback, validation/reasoning, governed retrieval, semantic two-CQ verdicts, settlement,
  and production cleanup remain `BLOCKED`/unexecuted by instruction.

### Round 2 — 2026-08-11 independent retest after High preflight repair — PASS / real run BLOCKED

- Stable state: developer stopped at the narrow repair worktree; no real semantic run was created or
  continued. The canonical R2.3-003 ledger now contains exactly the authorized initial event
  `user-20260811-r23003-start1-4` (`cap/count/active=4/0/0`); no reservation or semantic start was
  consumed. The retained Start75 tree digest remained `22750e36caeedb11bfc3ab9613fe66f85d45df01f63d43188c61205e5ded0634`,
  the L3 source tree remained `457549bdf325d6b0c4f796a762474dd79c90d5b55d5b922fb1bd28799ae23cf4`,
  and R2.3-002/R2.3-005 ledger hashes remained unchanged. `git diff --check` PASS.
- Fixed since Round 1: R2.3-003 defers DeepSeek credential read until after existing live-scope
  preflight and before ledger reservation/run-root creation; malformed/missing Project identity now fails
  closed instead of defaulting a missing response ID to the requested path. New regressions assert the
  live-preflight-before-credential event order and reject `{}`, `[]`, and wrong Project IDs.
- Commands and results:
  - Focused repaired contract set:
    `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_contracts.py modeling_team/tests/test_r23005_ledger_isolation.py
    modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_r23005_t6_repeatability.py
    modeling_team/tests/test_r23005_sequential_cq.py modeling_team/tests/test_r23005_c_settlement.py -q`:
    PASS, 87 tests, 27 subtests. The 003 file alone is 10 passed, including both Round 1 High regressions;
    005/003 formal identity, frozen baseline, ledger isolation, two-CQ ordering, settlement/CAS and cleanup
    remain PASS.
  - Full `uv run --project backend python -m pytest modeling_team/tests -q`: PASS, 704 passed, 1 skipped,
    218 subtests.
  - Full backend `cd backend && uv run pytest -q --disable-warnings`: PASS, 843 passed, 10 skipped.
  - Formal CLI smoke (read-only): matching 003/005 `validate` commands exit `0` with exact four-role rosters;
    matching 003/005 `baseline` previews exit `0` with manifest bindings
    (`r23003` hash `8e1f77fa64cab0e575d2eae578a9ccf0f8eff8673051eb86fcfa710501c11c4d`,
    `r23005` hash `5d02b98ab5108f12c78d61fe81c0100c838029ebfd62d2d354e5beb6b38bf147`). Both cross-wired
    validate pairs exit `2` with `validation failed: unknown or cross-wired formal run contract`; no smoke
    run root was created.
  - Runtime health: `ontology-platform.service` active; backend `/api/health` returned `{"status":"ok"}`;
    frontend `/` returned HTTP `200`. Retained Start75 and source hashes above were unchanged after all
    tests; no retained evidence was modified.
- Result: **PASS for the deterministic implementation gate**. The Round 1 High defects are FIXED by the
  focused regressions and full suites; no remaining deterministic defect was found. Real L0 start, live
  Start75 mutation/readback, validation/reasoning/retrieval, two semantic CQ verdicts, settlement and
  production cleanup remain `BLOCKED`/unexecuted by instruction, not PASS. Requirement-level completion
  therefore remains BLOCKED pending a separately authorized real run and independent read-only acceptance.
- Recommendation: no further requirement-developer repair is requested from Round 2; the main agent may
  proceed to the independent real-run gate when it is ready, preserving the exact four-start budget and
  success-stop rule.

### Round 3 — 2026-08-11 independent retest of start2 prompt-contract repair — PASS

- Stable state: development stopped at HEAD `59d73df0c316ae8e01da403ef3e1ec89e84b037c` with the
  start2 prompt-contract repair present in the uncommitted worktree. This round did not start or continue
  a semantic run, call the live platform, or modify retained evidence. `git diff --check` PASS; relevant
  changed paths are limited to the four role instruction packages and their focused regression tests
  (the main-agent delivery record remained untouched by this tester).
- Commands and results:
  - Focused prompt/transport/005 regressions:
    `uv run --project backend python -m pytest
    modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_complete_revision.py
    modeling_team/tests/test_r23005_ticket_pipeline.py -q`:
    PASS, 34 tests. The targeted subset for the fully-qualified transport surface, the R2.3-005 formal
    prompt smoke/full-run guard, nested handoff prompt, ticket-pipeline prompt, and qualified Codex
    transport callback also passed: 5 tests.
  - `test_codex_isolation.py::test_dynamic_transport_routes_only_profile_tool_and_blocks_spawn`:
    PASS, 1 test. The adapter successfully routes the fully-qualified
    `mcp__team_transport__send_team_message` callable through the broker and preserves the delivery.
  - Direct role-prompt audit: Coordinator, Modeling, Protocol, and Acceptance each name all four
    authoritative callables (`mcp__team_transport__send_team_message`, `...send_coordination`,
    `...report_task_result`, `...report_issue`) and explicitly state that bare aliases are unsupported by
    the App Server. No executable bare `send_team_message`/`send_coordination`/`report_issue` instruction
    was found; Acceptance's remaining bare `report_task_result` occurrence is in the explicit prohibition
    that non-final/FAIL/BLOCKED verdicts must not call it, not a callable instruction.
  - `git diff --check`: PASS. No runtime adapter source file was changed by the repair; the focused
    qualified-call regression covers its fully-qualified callback path. The App Server rejection of bare
    aliases is retained from start2 runtime evidence; the adapter's internal suffix normalization remains
    a callback compatibility layer and is not the Agent-visible tool surface.
- Result: **PASS** for the start2 prompt/tool-surface contract. The four-role prompts now expose the exact
  fully-qualified names required by the Runtime, forbid bare aliases, and preserve the R2.3-005 prompt
  gates. The direct bare-alias adapter acceptance observed in a temporary unit probe is recorded as
  non-blocking future hardening only, because it is below the App Server surface and was not the start2
  failure path. No real L0-L2 semantic run was started or continued in this round.

### Round 4 — 2026-08-11 independent retest of start3 startup-barrier and artifact-identity repairs — PASS / real run BLOCKED

- Stable state: development stopped at HEAD `902e8622fdfefed82953c4e3b02d53e820f378c9` with the start3
  repair present in the uncommitted worktree. This round did not start or continue a semantic run, call a
  live Project/Ontology endpoint, or modify retained evidence. The main-agent delivery-record edit remains
  present and was not overwritten by this tester. `git diff --check` PASS.
- Commands and results:
  - Focused R2.3-003/005, startup-gate, artifact, and frozen-surface regressions:
    `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_candidate_platform_gate.py modeling_team/tests/test_protocol_retrieval_gate.py
    modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_p2a_codex_runtime.py
    modeling_team/tests/test_r23005_candidate_progress.py -q`: **PASS, 109 passed in 1.51s**.
    This includes the generated Protocol startup-barrier contract, candidate gate lifecycle and receipt
    wakeup, different-tool/same-arguments result-artifact identity, R2.3-005 complete-revision compatibility,
    and the frozen normal runtime/platform surface hash check.
  - Backend formal gate enforcement:
    `cd backend && uv run pytest tests/test_mcp_candidate_gate.py -q`: **PASS, 4 passed, 3 deprecation
    warnings**. A closed/malformed/symlinked/oversized gate returns `candidate_receipt_required` before
    resource acquisition or callback execution; an open gate allows the callback; legacy launches without
    the gate environment retain the original path.
  - Explicit barrier sequence and namespace checks:
    `uv run --project backend python -m pytest
    modeling_team/tests/test_r23005_candidate_progress.py::test_runner_opens_platform_gate_only_after_registered_receipt
    modeling_team/tests/test_r23005_candidate_progress.py::test_runner_wakes_protocol_once_after_accepted_receipt_and_not_on_duplicate_drain
    modeling_team/tests/test_r23005_candidate_progress.py::test_runner_keeps_platform_gate_closed_after_protocol_conflict
    modeling_team/tests/test_candidate_platform_gate.py::test_codex_formal_config_and_namespace_bind_gate_read_only
    backend/tests/test_mcp_candidate_gate.py -q`: **PASS, 8 passed, 3 deprecation warnings**.
    The Runner remains closed after candidate delivery, opens only after the registered accepted receipt,
    wakes the same Protocol thread once, and closes on conflict; the backend gate prevents every platform
    call path before that receipt (including resources and callback).
  - Direct regression spot checks:
    `uv run --project backend python -m pytest
    modeling_team/tests/test_protocol_retrieval_gate.py::test_platform_artifact_identity_includes_tool_name
    modeling_team/tests/test_p2a_codex_runtime.py::test_normal_runtime_and_platform_surfaces_remain_byte_frozen
    modeling_team/tests/test_r23003_incremental_contract.py::test_r23003_protocol_task_text_waits_for_candidate_receipt_before_platform_calls -q`:
    **PASS, 3 passed**; followed by `git diff --check`: **PASS**.
- Defect status: **FIXED**. For identical argument/result envelopes, `get_ontology_workspace_context` and
  `get_modeling_context` now produce distinct request digests and immutable artifact paths because the tool
  name is included in the canonical request identity. The startup barrier is enforced at both Runner gate
  state and backend `_run_tool` before resource/auth/callback work; no remaining deterministic defect was
  found in this scope.
- Result: **PASS for the deterministic implementation gate**. Real L0 start, live retained-scope preflight,
  Modeling candidate, receipt-backed existing-entity binding, dry-run/apply/readback, validation/reasoning,
  governed retrieval, semantic two-CQ verdicts, settlement, and production cleanup remain **BLOCKED** and
  unexecuted by instruction, not PASS. Requirement-level completion remains BLOCKED pending separately
  authorized real modeling and independent read-only acceptance.
- Recommendation: no further requirement-developer repair is requested from Round 4. Preserve the exact
  four-start budget and do not launch a real run as part of this deterministic retest.

### Round 5 — 2026-08-11 independent retest of exact R2.3-003 Modeling prompt contract — FAIL / real run BLOCKED

- Stable state: development stopped at HEAD `7c2b5511c31675e21427cb2be469630ee742a7de` with the exact
  R2.3-003 Modeling package and Runner task-text additions present in the uncommitted worktree. This round
  did not start or continue a semantic run, call a live Project/Ontology endpoint, or modify retained
  evidence. `git diff --check` PASS.
- Commands and results:
  - R2.3-003 focused contract: `uv run --project backend python -m pytest
    modeling_team/tests/test_r23003_incremental_contract.py -q`: **PASS, 13 passed in 0.21s**. The package
    and generated Runner text contain the target 12–24 complete items, hard maximum 32, retained
    `existing_entity_ref`, bounded-scope wording, post-source prohibition on `exec`/shell/Python/filesystem/
    temporary paths, and the inline fully-qualified
    `mcp__team_transport__send_team_message` call with `recipient_id=protocol`, `expects_reply=true`, and
    candidate JSON as text.
  - R2.3-005 prompt/complete-revision compatibility: `uv run --project backend python -m pytest
    modeling_team/tests/test_r23005_complete_revision.py -q`: **PASS, 8 passed in 0.11s**. No 005 test
    failure was observed in the complete-candidate, protocol, or proof/neutral boundary checks.
  - Combined frozen-surface check: `uv run --project backend python -m pytest
    modeling_team/tests/test_r23003_incremental_contract.py modeling_team/tests/test_r23005_complete_revision.py
    modeling_team/tests/test_p2a_codex_runtime.py -q`: **FAIL, 49 passed, 1 failed**. The sole failure is
    `test_normal_runtime_and_platform_surfaces_remain_byte_frozen`: current
    `modeling_team/runner.py` SHA-256 is
    `d2e6d5a75064756f67843d3ca2144e169175bc60deb426d5019d92e6c270e9ed`, while
    `FROZEN_GLOBAL_SURFACES` still expects the prior Runner digest
    `4a775f0b0ffabf9312964f07b7aba175a42d36c642df739a70a16fd4808d6c34`.
    This drift is caused by the approved R2.3-003 `_task_text("modeling")` prompt addition; the frozen
    expected hash has not yet been refreshed. The five other frozen surfaces remain unchanged.
- Defect: **High, deterministic frozen-surface compatibility gate (pending developer hash refresh)**.
  Expected: the approved R2.3-003 Runner prompt change is represented by the updated expected Runner digest,
  while the R2.3-005 frozen compatibility test remains green. Actual: the 005/frozen suite fails on the
  stale expected digest before the final gate can pass. The focused 003 and 005 contract tests pass; no
  product behavior defect or real-run evidence was found. Developer should update only the frozen Runner
  expected digest, then request the next independent recheck; do not alter the 003 prompt contract or launch
  a real run to bypass this deterministic failure.
- Result: **FAIL for the deterministic implementation gate**. Real L0 start, live retained-scope preflight,
  Modeling candidate, receipt-backed existing-entity binding, dry-run/apply/readback, validation/reasoning,
  governed retrieval, semantic two-CQ verdicts, settlement, and production cleanup remain **BLOCKED** and
  unexecuted by instruction, not PASS. Requirement-level completion remains BLOCKED pending hash repair and
  a later independent PASS plus separately authorized real modeling/acceptance.

### Round 5 recheck — 2026-08-11 after approved frozen Runner digest refresh — PASS / real run BLOCKED

- Stable state: development stopped at HEAD `7c2b5511c31675e21427cb2be469630ee742a7de`; the only
  start3-follow-up change is the approved `FROZEN_GLOBAL_SURFACES["modeling_team/runner.py"]` digest refresh
  to `d2e6d5a75064756f67843d3ca2144e169175bc60deb426d5019d92e6c270e9ed`. No semantic run, live endpoint,
  or retained-evidence mutation was performed. `git diff --check` PASS.
- Recheck command:
  `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
  modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_p2a_codex_runtime.py -q`
  → **PASS, 50 passed in 0.50s**; followed by `git diff --check` → **PASS**.
  This revalidates the exact R2.3-003 Modeling package/Runner prompt (12–24 target, max 32, source-after
  exec/filesystem prohibition, inline fully-qualified transport arguments) and confirms R2.3-005 complete
  revision plus frozen normal runtime/platform surfaces are green after the hash refresh.
- Result: **PASS for the deterministic implementation gate**. Round 5's stale digest defect is FIXED. Real
  L0 start, live retained-scope preflight, Modeling candidate, receipt-backed existing-entity binding,
  dry-run/apply/readback, validation/reasoning, governed retrieval, semantic two-CQ verdicts, settlement,
  and production cleanup remain **BLOCKED** and unexecuted by instruction, not PASS. No further developer
  repair is requested; preserve the exact four-start budget and do not launch a real run in this recheck.

### Round 6 — 2026-08-11 independent read-only review of live starts 2–5 — FAIL / requirement BLOCKED

- Stable state and scope: development was stopped at HEAD `2c14b722218f5a3a0356ce48120c8752fd7c2816`.
  This round only inspected retained evidence under
  `workspaces/modeling-runs/r23003-real-20260811-deepseek-start{2,3,4,5}`, the append-only start ledger,
  source manifests, process/service state, and read-only platform responses. No semantic run was started or
  continued, and no product code, delivery record, or retained evidence was changed. `git diff --check`
  passed after the test-plan-only append.
- Start budget and terminal accounting: `.r2-3-003-start-ledger.jsonl` records exactly four semantic starts
  after the pre-semantic Start1 release: start2 (`collaboration/routing`, terminal failure), start3
  (`platform-contract`, terminal failure), start4 (`collaboration/routing`, terminal failure), and start5
  (`platform-contract`, terminal failure). No additional start was created.
- Start5 partial semantic evidence (the only run with a candidate exchange):
  - Modeling delivery-4 contained a 28-item candidate, revision
    `r2-3-003-existing-scope-increment-1`, text SHA-256
    `d35dc790a48f1e238052863379b25d6d0df918685b22322ac1d0732bddb2bf01`.
  - Protocol accepted delivery-4 as delivery-5; the formal progress log binds the accepted candidate and
    semantic digest to `76437a1c013d1cfe5c1389652fb3f7ad9dd5b8f89a6e86133904590c0df52833` and records the
    receipt as `state=complete`.
  - Protocol issue-1 fail-closed existing-entity binding identified four incorrect/missing live references
    (two WorkflowVersion IDs and two ExplicitUnknown/absent-class mappings), with `mutation_state=no writes`.
    The revised delivery-7 retained the same 28-item business candidate while correcting those four IDs/classes;
    its text SHA-256 is `1da57f1f0b2a9e562d6d61dec4ed9a9c5aaf46d819c4310c76c6b6df2f84932`.
  - Two typed `protocol_build_candidate_receipt` attempts for delivery-7 were rejected. The retained issue
    report records MCP error `-32001` (`Runner capability request rejected`); the capability log records the
    typed-path error `TeamConfigurationError: typed candidate delivery_id is foreign or stale`. The accepted
    receipt for delivery-4 could not be safely replaced, so issue-2 aborted the run before any platform write.
    There is no accepted receipt for delivery-7 and no formal dry-run/apply/readback or semantic acceptance.
- No-write and retained-scope checks: start5 issue reports explicitly record no Build Session, ontology lease,
  or submitted batch; its read-only `get_modeling_context` response still reports workspace version
  `0d34f5ada161d2c6deb4a7b117c6b1469b540eef7eb1f04c8bdce97e5100ef02`, `lease_active=false`, and six existing
  batches. Start2–4 preflight before/after scope records likewise remain at zero active lease/session/attempts,
  six modeling batches, the same graph set `277fd804-e485-5156-b7a7-ca6a1081f950`, and the same workspace
  version. No mutation evidence was found.
- Cleanup and residue: start3's retained cleanup aggregate reports revoked/non-active keys,
  `private_credentials_destroyed=true`, zero secret matches, closed proxy, and zero child residue. Start2 and
  start4 report closed proxy and zero child residue but **`private_credentials_destroyed=false` with
  `matched_secret_count=1` (secret scan `match_count=2` in each run)**; therefore their cleanup gates are not
  PASS. Start5's compact acceptance cleanup reports `status=aborted`, `settled=false`,
  `credentials_destroyed=true`, `active_handles=0`, and `zero_child_residue=true`, but does not retain the
  start2/4 aggregate secret-scan proof. A read-only process scan found no start2–5 role/deepseek/r23003
  processes and no run-root socket or PID files. This does not erase the retained credential residual.
- Source and service checks: all seven R2.3-003/L3 source files recomputed exactly to the checked-in manifest
  SHA-256 values (the retained Start75 tree digest remains the previously recorded
  `22750e36caeedb11bfc3ab9613fe66f85d45df01f63d43188c61205e5ded0634`).
  `ontology-platform.service` is active; `GET http://127.0.0.1:8001/api/health` returned HTTP 200
  `{"status":"ok"}`, and `GET http://127.0.0.1:5173/` returned HTTP 200.
- Primary blocker: **High, platform-contract** — the corrected candidate (delivery-7) cannot obtain the
  required typed receipt (`-32001`/foreign-or-stale delivery identity). This blocks the receipt-backed
  existing-entity binding and every downstream dry-run/application, readback, validation/reasoning,
  governed-retrieval, CQ, settlement, and final cleanup acceptance step. **Additional High cleanup defect:**
  start2 and start4 retain matched private credential material after abort. All four semantic starts are
  consumed, so this round cannot obtain a fresh live result.
- Result: **FAIL / requirement BLOCKED**. The records provide useful partial evidence (candidate delivery,
  accepted first receipt, corrected revision, fail-closed issue handling, no-write scope preservation, source
  fidelity, and service health), but no complete R2.3-003 semantic acceptance or PASS verdict. No further run is
  authorized in this round; repair the typed receipt binding and cleanup residual before requesting any future
  authorization.

### Round 7 — 2026-08-11 post-run security-remediation recheck — PASS for remediation / requirement remains BLOCKED

- Scope and safety: this was a read-only recheck after the main agent's precise removal of the 48 targeted
  `logs_2`/`state_5` SQLite/WAL/SHM private-cache artifacts from the start2 and start4 runtime trees. No run was
  started or continued, and this tester did not modify product code, the delivery record, or retained evidence.
- Targeted cache deletion: a recursive read-only count over each `runtime/` tree returned **0** files matching
  all six exact target suffixes (`logs_2.sqlite`, `.sqlite-wal`, `.sqlite-shm`, `state_5.sqlite`, `.sqlite-wal`,
  `.sqlite-shm`) for both start2 and start4. The retained sessions are still present (4 session JSONL files per
  run); retained evidence remains present (14 files under start2 evidence trees and 15 under start4 evidence
  trees).
- In-process secret scan: `/home/yangxiang/.config/ontology-platform/modeling-team-deepseek.env` has mode `0600`.
  A backend virtualenv Python process loaded `DEEPSEEK_API_KEY` in memory without printing its value, scanned
  642 files under each exact start2/start4 `runtime/` tree, and found `exact_occurrences=0` and
  `matched_files=0` for each. No credential value was emitted.
- Platform-key status: a read-only database query for the four exact R2.3-003 run model keys plus the related
  `r2-3-001-team-runner-admin` and `r2-3-003-live-preflight-admin` rows created during the four starts returned
  13 relevant rows with **0 active** (4 run keys, 4 runner-admin keys, 5 preflight-admin keys). All are revoked
  or otherwise non-active; no key was created by this recheck.
- Runtime residue: a `/proc` scan found 0 processes whose command line matched any retained R2.3-003 run name;
  start2 and start4 each have 0 Unix sockets and 0 `.pid` files in the run tree.
- Historical cleanup record and interpretation: `state.json` for start2 and start4 remains unchanged with
  `private_credentials_destroyed=false`, secret-audit `match_count=2` and `matched_secret_count=1`. Round 6's
  cleanup **FAIL** is intentionally preserved and not rewritten. The current cache deletion and exact in-process
  secret scan demonstrate a **post-run security-remediation PASS only**; they do not retroactively turn the
  historical run cleanup gate into PASS.
- Service health: `ontology-platform.service` is active; backend `GET /api/health` returned HTTP 200 with
  `{"status":"ok"}`; frontend `GET /` returned HTTP 200.
- Result: **PASS for the bounded post-run security-remediation checks; requirement remains BLOCKED/FAIL**. The
  Round 6 typed candidate-receipt blocker and absence of complete L0–L2 semantic acceptance remain in force.
  No new semantic start or evidence rewrite is authorized by this round.
