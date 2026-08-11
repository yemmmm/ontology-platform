# R2.3-003 Existing-scope 增量建模共享测试计划

- 状态：Approved；revised-contract plan review Round 4 PASS，待实现/独立复测
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
6. validation/reasoning、governed retrieval、Evidence/lineage、目标 unknown 硬删除和 standard 的全部 N 条 CQ 在同一最终 model state PASS；
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
- 003 Task 与四角色 authoritative prompts 不含 preserve-old-unknown、exactly-two、固定 `cq-001/cq-002`
  或 final-CQ2 指令；Acceptance/Coordinator 使用 Runner 投影的 ordinal/count/next/is-final 元数据。
- 005 `unknown_policy=preserve-explicit-unknown` 保持字节/行为；003 只接受结构化
  `resolve-and-delete-targets`、精确两个 target IDs、`preserve_non_targets=true`；缺失/额外 target、跨 contract
  policy、删除非目标 unknown 均 fail closed。
- FormalRunContract、003 handoff、acceptance standard 与 candidate 的 target 集合必须完全等于
  `{unknown-cross-release-output-meaning, unknown-b-no-score-behavior}` 且 Class=`ExplicitUnknown`；替换任一
  ID/Class、只给一个、增加第三个、asset cross-wire 均在 credential/Build Session/mutation 前拒绝；IRI 只
  接受 live canonical projection，不允许静态 handoff/candidate 提供。

### T3 — StartLedger

- `.r2-3-003-start-ledger.jsonl` 与 002/005 namespace/lock 隔离；
- 初始 cap/count/active 为 `0/0/0`，未授权 reserve 失败且不创建 run root；
- 空账本只接受一次 exact `initial_authorization +4`；prior-failure 不适用于该事件，重复/伪造/顺序错误
  授权失败；后续普通 budget extension 仍执行严格 predecessor；
- success-stop 后剩余 start 不消费；mutation 后 terminal 未对账时新 start 被拒绝；
- 原 cap/count/active=`4/4/0` 与四次 terminal failures 保持；修订门通过后只接受一次 exact
  `user-20260811-r23003-revision-start1-3` +3 strict extension，使 cap/count/active=`7/4/0`；提前追加、
  重复 ID/reference、错误数量、缺 retryable predecessor 均拒绝；
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
- backend real entity-list fixture 明确返回 `semantic_id/entity_iri/class_semantic_id/class_iri`；Protocol 对
  缺字段、full IRI 冒充 semantic ID、非 canonical IRI 和 synthetic-only shape 均拒绝，不拆 IRI 猜 ID；
- 005 translator 拒绝 existing binding/delete 输入且 create plan 字节不变；003 translator 不为普通
  existing ref 发 create/update，只用 receipt IRI 生成新 relation；仅对 impact receipt 完整匹配的
  `delete_existing_entity` 生成 `delete_entity`；所有新增关系有 source citation；
- 每阶段先 dry_run 再 apply_atomic，expected workspace version 严格串联；
- live read 枚举两个目标 unknown 的完整入边/出边；读取不完整、IRI/Class/version drift 均在 dry-run 前
  fail closed；candidate 只允许 `full_live_impact`，拒绝 Agent-authored IRI/triples/impact
  digest/expected-edge 集合；
- entity-statement projection 用 exact IRI 和 opaque cursor 分页；1 页、多页、>1000 statements 均取得
  显式 complete/snapshot digest，cursor scope/entity/workspace drift、漏页、重复页、truncated without cursor、
  未完成链全部禁止 delete；
- tool-owned impact receipt 绑定完整 page chain/snapshot/statements/candidate digest；增删一条 live edge、
  candidate drift、workspace drift 或伪造 impact digest 均使 translator 拒绝，Modeling 无法选择性遗漏边；
- start5 回归：rev1 receipt -> live binding mismatch -> typed conflict/旧 receipt invalidated/gate closed ->
  full rev2 reply -> replacement receipt/gate reopened；foreign/stale、无 reply_to、并行 rev、旧 receipt 复用、
  mutation 后 revision 均 fail closed；
- Phase A Batch 先写 resolution、新 policy、concrete case、新 Evidence/lineage 并取得 durable readback；
  Phase B 才以 delete-only Batch 删除两个目标，workspace version 严格串联；任一中间态不能冻结 Acceptance；
- readback 证明两个目标 semantic ID 及其级联关系不存在、非目标 Start75 资源保持；
- Acceptance `explicit_unknowns` check 证明目标删除且新结论/Evidence 完整，同时证明全部非目标 unknown 保持；
- invalid probe 被 validation_failed 拒绝且零 mutation；任一 apply 不确定时 fail closed。
- 注入 Phase B RDF apply 后/SQL commit 前失败：readback 为“均存在”时允许同 Team 新 Batch 重试，
  “均不存在”时只恢复机械记录且禁止重建，“部分删除/不完整”时阻止新 start 并请求人工对账；Phase A
  durable 语义在所有分支保持。
- delete-only recovery 精确回归：before statements 全在且无新边=`not_applied`；目标/全部 before statements
  均不在=`applied`；严格子集、目标与边混合、出现新 incident triple、cursor/snapshot 不完整=
  `partial_or_drifted`。`_resume_attempt` 仅前两态分别 retry/skip-RDF，第三态不得 retry；005 非删除路径回归。

### T6 — N-CQ Acceptance and settlement

- standard 接受任意正整数 N 个、唯一且有序的 CQ；空列表、重复 ID、字段/来源错误 fail closed；实现没有
  `len==2`、`cq-001/cq-002` 或“final CQ2”分支；
- 以 1/3/5 CQ standards 验证 ticket、串行推进、每题 fresh Source/Platform Examiner、上一轮 child 回收后
  才启动下一轮；当前 003/005 两题 standard 保持原顺序与问题字节；
- loader/task/prompt/ticket 全链使用 standard-owned ordered IDs 和 Runner-owned ordinal/count/next/is-final；
  非 `cq-NNN` 的合法唯一 ID 也可运行，证明未按名称推断顺序/final；
- ticket 不含预期答案、Producer 对话或旧 verdict；
- Source/Platform 两侧独立得出答案；N 份 CQ Acceptance verdict 与 2N 份 Examiner report 绑定同一
  最终 model state；
- 任一新 write 使全部旧 verdict 失效；
- 非最终 PASS 只推进恰好下一题，final PASS 不再启动新轮；任一非 PASS 停止推进；
- settlement 要求当前 epoch 恰好覆盖 standard 的完整有序 N 题、全部 usable PASS、无 active handles；
  terminal 顺序、settlement CAS/readback、Team settled 和 aggregate cleanup 保持 005 两题回归。

### T7 — Failure and cleanup

- mutation 前失败允许在剩余授权内 fresh retry；
- mutation 后同一 Team 的修订使用新 Batch 和新 final model state；
- mutation unknown、terminal-after-apply 或 readback 不一致阻止新 start 和自动删除；
- existing Project/Ontology 永远保留；只允许删除两个目标 unknown；本轮 Session/Lease/key/Agent/Examiner/proxy/run-private secret 精确清理；
- cleanup failure 作为附加事实保留，不覆盖第一阻断分类。

## 3. 真实运行测试

原四次 R2.3-003 semantic starts 已耗尽；用户新增授权精确三次。真实运行只在修订实现、独立
deterministic PASS、clean committed baseline、service restart/health PASS 且 exact +3 ledger extension
登记后进行；首个完整 PASS 后 success-stop。

### L0 — Start and scope

- 20 分钟内进入第一个真实 semantic modeling start；只做安全启动所需最小 preflight；
- 使用 exact Start75 Project/Ontology 和 live workspace version；全新 Team/Agent/Session/Lease/run root；
- 首次 Agent turn 前 source visibility、Protocol-only MCP 和 forbidden-path probe PASS。

### L1 — Modeling quality

- 直接检查 Modeling 完整增量 candidate、Protocol receipt 与每阶段 dry-run/apply/readback；
- 核对两个 unknown 对应的新结论、两个旧资源及级联边已删除、新 decision/publication slice、旧模型回归、显式范围外；
- validation conforms、reasoning consistent、required path retrieval 完整、非截断、有 Evidence/lineage；
- 不使用本次专用硬编码验收程序替代直接证据。

### L2 — Independent semantic acceptance

- standard 声明的全部 N 轮 fresh Examiner 均形成终态；全部 CQ current/usable PASS 且绑定同一 final model state；
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

### Round 8 — 2026-08-11 independent deterministic implementation gate — FAIL / live requirement BLOCKED

- Scope and safety: the worktree was reviewed at base commit `8f958b778c9bfe4960d5f46e96b52ac4e7eb7c9f` with the
  approved uncommitted implementation/test changes and the main-owned delivery-record edit. This round only
  inspected and exercised deterministic code paths. It did not edit product code, requirements, design, delivery
  record, retained evidence, Start75 scope, or the start ledger; it did not register/use the proposed `+3`
  authorization and did not start or continue a semantic modeling run.
- Deterministic regression commands and results:
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23003_revision_contract.py backend/tests/test_modeling_batches_delete_recovery.py -q`:
    **20 passed**, 3 warnings.
  - `uv run --project backend python -m pytest modeling_team/tests -q`: **713 passed, 1 skipped, 218 subtests
    passed** (42.92s).
  - `cd backend && uv run pytest`: **846 passed, 10 skipped** (856 collected; 188 warnings; 37.96s).
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23005_candidate_progress.py
    modeling_team/tests/test_r23005_ticket_pipeline.py modeling_team/tests/test_r23005_complete_revision.py -q`:
    **55 passed**. This covers the accepted-receipt -> typed conflict -> complete revision -> replacement receipt/
    gate lifecycle and the R2.3-005 preserve/two-CQ regression paths.
  - `uv run --project backend python -m compileall -q modeling_team backend/app backend/tests`: **PASS**;
    `git diff --check`: **PASS**; `cd backend && uv run python ../scripts/sync-interface-docs.py --check`:
    **PASS** (`Interface documentation is synchronized.`).
- Frozen policy/asset isolation: reversed, wrong-pair, wrong-Class, count-1/count-3, wrong delete mode, and
  Agent-supplied IRI/field variants were rejected by `validate_deletion_policy`/
  `validate_candidate_delete_declaration`. However, the exact candidate target gate is incomplete: a candidate
  containing **three** delete declarations (one duplicate frozen target) was accepted by
  `build_existing_entity_binding_receipt` and `translate_candidate_to_batches`, which emitted three delete
  commands; a candidate with **zero** delete declarations and a non-003 `review-001` existing reference was also
  accepted under `requirement_id="R2.3-003"` and emitted ordinary non-delete batches. Expected: the formal contract,
  handoff, standard, and candidate must all fail closed unless the exact two-target set and count are present before
  any live impact read or mutation. Actual: duplicate/zero/wrong-pair candidate variants can pass the translator.
  **High, platform-contract defect.**
- Canonical live backend entity shape: after restart, a read-only authenticated GET of
  `/api/ontologies/fd762f52-2f5e-4bc0-902a-5583135ab64d/semantic-read-models/entities?include=asserted&field_set=full&limit=2000`
  returned HTTP 200 with 10 entities. All 10 had `semantic_id`, `entity_iri`, and `class_iri`, but **all 10 lacked
  the required `class_semantic_id`** (`missing_by_field={'semantic_id':0,'entity_iri':0,'class_semantic_id':10,
  'class_iri':0}`). Expected: the canonical real backend projection contains all four explicit identity fields;
  actual: Protocol binding cannot consume the returned shape and fails closed with incomplete projection. **High,
  platform-contract defect**; the focused service projection test passes only its in-memory fixture and does not
  erase this live-shape failure.
- Entity statement pagination itself passed the 1001-statement two-page/snapshot-drift deterministic test, and
  `page_size`/opaque cursor/scope checks are covered by the focused suite. Tool-owned impact receipt integrity did
  not pass the adversarial chain check: `build_delete_impact_receipt` accepted two pages with `page_digest` values
  `wrong1/wrong2` and different snapshot values `s1/s2`, returning `ACCEPTED s1 ['wrong1','wrong2']` instead of
  recomputing/validating page digests and one common snapshot. Expected: any page/snapshot/cursor mismatch rejects
  before delete; actual: a canonically rehashed but forged receipt is accepted downstream. **High,
  platform-contract defect.**
- Phase ordering and delete-only gating: an instrumented candidate with one predicate, two frozen existing refs,
  two delete declarations, and a relation produced Phase-A `property`, then `relation`, then Phase-B
  `delete-only (phase=B, delete_only=true)` batches when `phase_a_readback=true`; with readback false both deletes
  returned `phase_a_readback_required` and no delete batch. This deterministic ordering check **PASS**. Recovery
  observer tests cover `not_applied`, `applied`, strict partial/new-edge states and no-retry classification, but a
  real post-RDF/pre-SQL injected delete transaction was not executed because no live mutation is authorized;
  that SQL/receipt injection branch remains **BLOCKED/unexecuted**, not PASS.
- N-CQ acceptance: arbitrary-ID synthetic carriers produced `N=3` and `N=5` ordered rounds with
  `settlement_ready=True`, while `N=1` completed its PASS round but returned `settlement_ready=False` (boundaries:
  `before-pair` x2 and `after-pass-before-next-cq`, with no `after-pass-before-settlement`). The implementation has
  a hard-coded requirement for both after-pass boundaries, so the required arbitrary positive N contract is
  impossible for N=1. **High, platform-contract defect.** Additionally, `validate_ticket` accepted a deletion-aware
  policy ticket with no `question_ordinal/question_count/previous_question_id/next_question_id/is_final_question`
  fields; expected every 003 ticket to carry Runner-owned progress metadata. **Medium, platform-contract defect.**
- Prompt/task and R2.3-005 isolation checks remain PASS in the focused/full suites: 003 uses ordered standard-owned
  IDs and generic N-CQ wording, while 005 retains `preserve-explicit-unknown` and its two-question behavior. The
  current 003 standard still has its approved two CQs; no prompt-only PASS is promoted to a real semantic result.
- Authorization/scope/residue readback: `.r2-3-003-start-ledger.jsonl` remains 15 lines with the original exact
  initial `+4`, four reservations, four semantic starts (`start2`–`start5`) and four terminal failures; no
  `budget_authorization`/revision `+3` event or new reservation was added. The current Start75 handoff still has
  only the approved structured deletion-policy addition relative to the reviewed baseline. No R2.3-003 run process
  or Unix socket was found. Existing retained Round 6 cleanup-failure facts were not rewritten.
- Service verification: `systemctl --user restart ontology-platform.service` completed and the unit is active. The
  first immediate backend curl raced the startup build and failed to connect; after the unit completed startup,
  `GET http://127.0.0.1:8001/api/health` returned HTTP 200 `{"status":"ok"}`, and `GET http://127.0.0.1:5173/`
  returned HTTP 200. The initial connection race is an environment startup timing observation, not a product test
  PASS/FAIL.
- Unexecuted live scope and residual risk: no new semantic start, Phase-A/Phase-B real dry-run/apply/readback,
  final live validation/reasoning/retrieval, N-CQ Examiner settlement, or live cleanup was attempted. Those L0–L2
  gates remain **BLOCKED** by the deterministic High defects above and by the already-consumed four-start evidence;
  this round cannot claim R2.3-003 completion.
- Result: **FAIL / requirement BLOCKED**. The deterministic regression suites, docs/compile/diff checks, service
  health, policy rejection matrix, Phase-A/B ordering, and 005 lifecycle are useful PASS evidence. Before any future
  authorization is used, repair the canonical live entity projection, exact candidate target/count gate, impact-page
  receipt binding, and N=1 settlement/progress enforcement; then rerun this plan as a new independent round.

### Round 9 — 2026-08-11 independent recheck after Round 8 repairs — PASS deterministic gate / requirement BLOCKED

- Scope and safety: development was stopped in the shared worktree at base `8f958b778c9bfe4960d5f46e96b52ac4e7eb7c9f`
  with the approved uncommitted implementation/test changes and the main-owned delivery-record append. This round
  only read and exercised deterministic paths plus read-only live entity projection/service checks. It did not edit
  product code, requirements, design, delivery record, retained evidence, Start75 scope, or the start ledger; it did
  not register/use a `+3` authorization and did not start or continue a semantic modeling run.
- Round 8 failure retests:
  - Read-only authenticated GET of
    `/api/ontologies/fd762f52-2f5e-4bc0-902a-5583135ab64d/semantic-read-models/entities?include=asserted&field_set=full&limit=2000`
    returned HTTP 200 and 10 items. Required `semantic_id`, `entity_iri`, `class_semantic_id`, `class_iri`,
    `project_id`, `ontology_id`, and `workspace_version` were present and non-empty for all 10
    (`missing` count 0 for every field; **PASS**).
  - Exact frozen target gate matrix (**PASS**): zero declarations → rejected (`exactly two delete declarations`);
    wrong pair → rejected (`target is not frozen`); duplicate target → rejected (`delete declarations drift`);
    extra declaration → rejected (`exactly two delete declarations`); exact two unique frozen targets → accepted.
    The gate is applied before translation/impact evidence, while the existing non-delete review-reference test
    remains covered by its generic read-only contract.
  - Tool-owned impact receipt chain (**PASS**): a valid two-page chain was accepted. Seven adversarial variants were
    each rejected: forged page digest (`page digest is invalid`), differing snapshot (`snapshot drifts`), wrong
    entity, wrong scope, cursor-chain mismatch, incomplete final page, and terminal page retaining a cursor. The
    chain now requires one entity/scope/workspace/snapshot, ordered opaque cursors, complete terminal page, unique
    statements, recomputed page digests, and recomputed aggregate snapshot digest. Backend receipt validation was
    also inspected and includes the canonical `entity_iri` field.
  - Arbitrary positive N-CQ settlement (**PASS**): synthetic ordered IDs settled for N=1 (`one`), N=3
    (`alpha,beta,gamma`), and N=5 (`north,east,south,west,center`), with the expected before-pair, between-CQ,
    and after-final settlement boundaries. Deletion-aware ticket metadata mutations for ordinal, count,
    previous/next adjacency, and `is_final_question` were rejected; a ticket missing all five progress fields was
    rejected. This verifies the ticket cannot bypass Runner-owned progress accounting.
  - Recovery and typed-receipt paths (**PASS**):
    `uv run --project backend python -m pytest backend/tests/test_modeling_batches_delete_recovery.py -q`
    → **3 passed**. The injected post-RDF/pre-SQL failure first returned recovery/pending with the graph empty,
    then converged to applied on retry with exactly one persisted delta and no duplicate RDF; all-present,
    all-absent, partial, and new-edge drift classifications are covered. Typed receipt/candidate progress
    `modeling_team/tests/test_r23005_candidate_progress.py` → **32 passed**, with the receipt/conflict/gate/revision
    subset → **12 passed**; foreign/stale IDs cannot bypass typed receipt validation.
- Required regressions:
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23003_revision_contract.py -q` → **21 passed**.
  - R2.3-005 lifecycle/preserve/two-CQ suite (`test_r23005_candidate_progress.py`, `test_r23005_ticket_pipeline.py`,
    `test_r23005_complete_revision.py`, `test_r23005_c_settlement.py`) → **67 passed**. Preserve-explicit-unknown
    policy and the two-CQ compatibility path remain green.
  - `uv run --project backend python -m pytest modeling_team/tests -q` → **716 passed, 1 skipped, 218 subtests
    passed** (42.85s); `cd backend && uv run pytest` → **848 passed, 10 skipped** (858 collected, 188 warnings,
    38.13s).
  - `uv run --project backend python -m compileall -q modeling_team backend/app backend/tests`, `git diff --check`,
    and `cd backend && uv run python ../scripts/sync-interface-docs.py --check` all **PASS**; interface output was
    `Interface documentation is synchronized.`
- Runtime and authorization invariants:
  - `ontology-platform.service` restart completed and remained active. The first immediate health poll raced the
    startup build; after startup, backend `/api/health` returned HTTP 200 `{"status":"ok"}` and frontend `/`
    returned HTTP 200. No service failure is inferred from the transient startup connection race.
  - `.r2-3-003-start-ledger.jsonl` remains exactly 15 lines with the original `+4` authorization, four reservations,
    starts 2–5, and four terminal failures; SHA-256 remains
    `fe750aaccd426e9d77212f934547224e5cab6ebd470bbc9598cb5657cbd3d977`. No revision `+3`/budget authorization or
    new reservation was created. Start75 handoff SHA-256 remains
    `aa20bcb28665fb069475450dc125ecf69d30ff4721ba52d7c775977f56b9e0aa`; only the approved structured deletion
    policy is present relative to the reviewed baseline. No retained run process or socket was found.
- Result: **PASS for the deterministic implementation gate; overall R2.3-003 requirement remains BLOCKED**. All
  Round 8 deterministic failures are fixed and the required regression/runtime checks pass. Real L0–L2 semantic
  acceptance remains unexecuted and cannot be promoted to PASS: no live candidate/delivery, receipt-backed binding,
  Phase-A/Phase-B dry-run/apply/readback, validation/reasoning, governed retrieval, N-CQ semantic verdict,
  settlement, or production cleanup was performed in this round. The four previously authorized semantic starts
  are consumed; no additional authorization or run was permitted. Residual live risk is therefore the unverified
  end-to-end modeling and cleanup evidence, not a remaining deterministic defect.

### Round 10 — 2026-08-11 independent StartLedger `+3` recheck — PASS narrow ledger gate / live requirement BLOCKED

- Scope and stable state: the worktree was at `195aa7d` with exactly the two-file uncommitted diff
  (`modeling_team/start_ledger.py` and its R2.3-003 contract test). This round did not edit product code,
  requirements, design, delivery record, retained evidence, or the real ledger; it did not register/use a new
  authorization and did not start or continue a live run.
- Exact R2.3-003 authorization matrix (all exercised against temporary ledgers, with rejected operations byte-stable):
  - Initial authorization is first-only and exact: cap is `4`, persisted amount is `4`; duplicate and wrong-amount
    calls reject without changing bytes.
  - After four semantic starts, each with a retryable terminal failure, authorization ID/reference
    `user-20260811-r23003-revision-start1-3` succeeds; replayed state is `cap=7`, `semantic_start_count=4`,
    `active_reservations=0`.
  - Premature, unconsumed, true no-predecessor (fourth start has no terminal failure), and non-retryable predecessor
    attempts reject. Boolean, zero, and negative amounts reject. Duplicate authorization ID and duplicate reference
    reject as immutable. Tampered initial amount and appended unknown-event replay both reject without further byte
    mutation.
  - Focused command
    `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_budget_extension.py modeling_team/tests/test_r23005_ledger_isolation.py
    modeling_team/tests/test_r23002.py -q` → **81 passed, 63 subtests passed in 2.62s**.
- Policy isolation: resolved fixed policies remain R2.3-002 `(initial=2, increment=2, strict=false,
  variable=false)`, R2.3-005 `(initial=1, increment=3, strict=true, variable=true)`, and R2.3-003
  `(initial=0, increment=4, strict=true, variable=true)`. Existing R2.3-005 budget/isolation tests are included
  in the focused result; no 002/005 policy or ledger namespace changed.
- Supplemental gates: `uv run --project backend python -m compileall -q modeling_team` and `git diff --check`
  both passed. Full `modeling_team` was not repeated independently in this narrow ledger-only round; the prior
  independent Round 9 result remains **716 passed, 1 skipped, 218 subtests passed**, and the current product diff
  is confined to StartLedger plus its tests. That prior result is supplementary rather than a new Round 10 run.
- Real-ledger no-mutation check: `workspaces/modeling-runs/.r2-3-003-start-ledger.jsonl` remains exactly 15 lines,
  SHA-256 `fe750aaccd426e9d77212f934547224e5cab6ebd470bbc9598cb5657cbd3d977`. It still contains only the original
  exact initial `+4` authorization, four semantic starts, and four terminal failures; no `budget_authorization`,
  `revision-start1-3`, additional `+3`, or new reservation was present. No retained R2.3-003 process or Unix socket
  was found.
- Result: **PASS for the narrow StartLedger `+3` deterministic gate; overall R2.3-003 remains BLOCKED** because
  live L0–L2 semantic candidate, receipt-backed binding, dry-run/apply/readback, CQ/settlement, and cleanup
  acceptance remain unexecuted by authorization/scope rules. No live evidence or authorization was consumed by this
  round.

### Round 11 — 2026-08-11 independent start6 prompt-contract repair recheck — PASS deterministic gate / live requirement BLOCKED

- Scope and stable state: this recheck used the shared worktree at HEAD `1865c7b2a33b9d070dd15d4624afc50dd8fe2024`
  with the prompt/task/Runner repair and its focused tests uncommitted. The tester did not edit product code,
  requirements, design, delivery record, or retained evidence, and did not start or continue a live run. Parent-owned
  `test_p2a_codex_runtime.py` has the approved frozen `runner.py` digest update; it was included only as a read-only
  regression input.
- Start6 evidence confirmed the repaired failure target: retained `delivery-4` used the wrong target IDs
  `unknown-quality-score-rating-sameness`/`unknown-b-absent-score-behavior`, `item_kind=entity_delete`, and nested
  `existing_entity_ref` delete payloads. The complete candidate did contain the bounded business slice, but the
  Protocol capability log shows three repeated `protocol_build_candidate_receipt` failures with
  `R2.3-003 candidate must contain exactly two delete declarations`; no conflict response was emitted and progress
  ended at `formal-reply-slot-reopen-rejected`.
- Prompt/task contract assertions (**PASS**, read-only): Modeling, Protocol, and the R2.3-003 task now carry the
  exact ordered IDs `unknown-cross-release-output-meaning`, `unknown-b-no-score-behavior`,
  `expected_class=ExplicitUnknown`, unique `item_id`, exact `item_kind=delete_existing_entity`, and direct
  `semantic={semantic_id,expected_class,delete_mode=full_live_impact}`. Modeling explicitly requires the complete
  candidate to retain both ordered delete items plus the bounded C-evaluation -> B-decision -> A-outcome slice,
  forbids `entity_delete`/nested refs and delete-only or patch-only revisions, and binds one full revision to the
  delivered conflict ID. Protocol's generated startup text explicitly forbids retrying a receipt-gate failure or
  sending an accepted receipt, and directs the native `protocol_mechanics/build_candidate_conflict` path with
  `expects_reply=true` and `reply_to_delivery_id`.
- Native conflict API and reply binding (**PASS**, read-only): calling `build_candidate_conflict` on the retained
  complete start6 candidate returned exactly the six-field conflict envelope
  (`status,candidate_revision,semantic_digest,candidate_digest,conflict_code,conflict_detail`). With the formal MCP
  gate enabled, `tools/list` advertised `build_candidate_conflict` and `tools/call` returned the same canonical JSON.
  Feeding that envelope as a `RuntimeDelivery(reply_to=delivery-4, expects_reply=true)` moved
  `FormalCandidateProgress` to `awaiting_revision`; no accepted receipt was produced in this path.
- Defect 1 — **Medium, collaboration/routing + platform-contract prompt/API mismatch**: the repaired Protocol
  receipt-gate branch says to send the native builder's exact `conflict_json`, but the native MCP API does not expose
  that field. Reproduction (formal gate enabled): `build_candidate_conflict` `tools/call` returned a result whose
  keys were exactly `content` and `structuredContent`; `conflict_json` was absent, while
  `content[0].text` was the canonical JSON serialization of `structuredContent`. Expected: the native branch must
  explicitly send the returned structured content/canonical text (or otherwise name the real API shape), while the
  `conflict_json` name remains reserved for the typed Runner capability. Actual: the instruction's literal
  `conflict_json` reference can leave Protocol without a payload and repeat the receipt/redrive failure observed in
  start6. Evidence: direct read-only MCP wrapper probe and the current `protocol_retrieval_mcp.py` response shape.
  Add a native MCP shape regression and revise the receipt-gate prompt before consuming start7.
- Focused deterministic results:
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py -q` — **73 passed, 2 subtests**.
  - R2.3-005 regression (`test_r23005_candidate_authoring.py`, `test_r23005_candidate_progress.py`,
    `test_r23005_complete_revision.py`, `test_r23005_contracts.py`, `test_r23005_c_settlement.py`,
    `test_r23005_sequential_cq.py`, `test_r23005_ticket_pipeline.py`, `test_r23005_t6_repeatability.py`) —
    **125 passed, 26 subtests**.
  - Frozen runtime hash regression `test_p2a_codex_runtime.py` — **29 passed**; full
    `uv run --project backend python -m pytest modeling_team/tests -q` — **718 passed, 1 skipped, 218 subtests**.
  - `uv run --project backend python -m compileall -q modeling_team backend/app backend/tests` and
    `git diff --check` — **PASS**.
- Read-only live/retained-state boundary: the parent live start6 had already appended the approved `+3`
  authorization and consumed start6 before/during this recheck. The canonical ledger is now **19 lines**, SHA-256
  `f31956c27a2c1e4dc38f6c59011dfd27701b3a4cbaf63f491d7134add64eeba3`, containing the initial `+4`, the exact
  revision `+3`, and start6 reservation/semantic-start/terminal-failure; this tester appended no ledger record.
  No start7/new reservation, matching start7 run directory, active modeling process, or related Unix socket was
  found. Read-only start6 fingerprints were `state.json=31925142e7520c0c674ad4889b9af78e7dcfa5bc14666d23158affbe8862ebad`,
  `formal-candidate-progress.jsonl=09cb25e74ac358525c0875f84494e5031f13aee1677eafe5afabba03c73b6d03`, and
  `capability-calls.jsonl=a52cda0663a427b9a3547d1bc1c5594f2610803f51f1960c6e9a736f1e4f2520`.
- Result: **FAIL for the repaired deterministic prompt/receipt-conflict gate; overall R2.3-003 remains BLOCKED**
  until Defect 1 is repaired and independently retested, then a fresh authorized start completes the semantic
  candidate, live binding, Phase A/B application/readback, validation/reasoning/retrieval, CQ settlement, and cleanup.
  The underlying native conflict builder and all listed regression suites pass, but the prompt/API naming mismatch
  is a release-blocking narrow routing defect. Recommendation: do **not** consume start7 until the developer updates
  the native-branch instruction and adds the MCP response-shape regression; preserve start6's collaboration/routing
  failure as historical evidence and do not rewrite it.

### Round 12 — 2026-08-11 recheck after native conflict result-shape prompt repair — FAIL / start7 remains blocked

- Scope and safety: the developer changed only the Protocol native-result instructions and generated Runner task text
  after Round11's API-shape defect. This recheck did not start/continue a live run, mutate the ledger, or edit retained
  start6 evidence; the tester changed only this test-plan record. HEAD remained `a220b766f42b67722ceb7b4b06d3faabea18a3b1`
  with the narrow repair uncommitted.
- Repair behavior probe: the native MCP wrapper still returns the real shape (`content` + `structuredContent`,
  canonical `content[0].text`), and the updated prompt now describes that shape. However, the required focused
  recheck command
  `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_p2a_codex_runtime.py -q`
  returned **99 passed, 3 failed, 2 subtests**.
- Defect 2 — **High, frozen-surface/regression contract**: `test_r23003_protocol_task_text_waits_for_candidate_receipt_before_platform_calls`
  still expects the approved phrase `native MCP result has only content and structuredContent`, but generated Runner
  text says `MCP result has only...`; `test_r23005_complete_revision::test_c95_protocol_never_merges_history_and_builds_each_current_receipt`
  still expects the frozen `exactly one of those two responses` wording, which the broad Runner rewrite removed; and
  `test_p2a_codex_runtime::test_normal_runtime_and_platform_surfaces_remain_byte_frozen` rejects actual
  `runner.py` SHA-256 `ee74babc1e24e75f7a4e94b300bf733bac080d929231591a35ff932fbd1c7667` against stale approved
  expectation `095f99a15933c16980b0de52e1e7f19007ee4607af8b671a97ec42d42a01a967`. Expected: preserve all 005
  frozen prompt assertions and update the approved Runner hash only after review of the intended generated-text
  delta. Actual: the narrow repair is not regression-clean.
- Other recheck evidence: the same command's 003/revision/005 candidate-progress/mechanical tests passed; the
  native MCP shape probe remains PASS. No start7/new reservation/process/socket was created. This round therefore
  remains **FAIL**, and the developer must repair the three regression failures (including an explicit MCP response
  shape regression) before another recheck or any start7 use.

### Round 13 — 2026-08-11 recheck after MCP shape regression addition — FAIL / start7 remains blocked

- The developer added the native MCP response-shape regression and updated the 003 generated-text assertions. No
  live run, ledger append, retained-evidence mutation, or product change was performed by the tester.
- Recheck command
  `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py modeling_team/tests/test_protocol_retrieval_mcp.py -q`
  → **83 passed, 1 failed, 15 subtests**. The new `test_candidate_conflict_tool_exposes_only_canonical_content_and_structured_content`
  passed and proves the native result shape; 003/revision/candidate-progress/mechanical tests also passed.
- Defect 3 — **Medium, R2.3-005 frozen prompt regression**: `test_r23005_complete_revision::test_c95_protocol_never_merges_history_and_builds_each_current_receipt`
  still fails because the broad Runner text rewrite removed the required frozen phrase
  `exactly one of those two responses`. Expected: preserve the accepted R2.3-005 wording/behavior while adding the
  native `content[0].text` branch. Actual: generated R2.3-005 Protocol text contains the new verified-response wording
  but not the frozen compatibility phrase. The approved Runner hash must also be refreshed only after this intended
  text is restored and the frozen-surface test passes.
- Result: **FAIL**, with start7 still blocked. Repair the single 005 prompt compatibility regression, refresh the
  reviewed frozen hash, and rerun this same focused set plus the full modeling-team suite before any live start.

### Round 14 — 2026-08-11 recheck after 005 wording restoration — FAIL / frozen hash drift

- The 005 generic wording was restored and the native MCP shape regression remained present. The exact focused
  contract command now passed **102 tests, 2 subtests**; the standalone native MCP regression file passed **11 tests,
  13 subtests**. No live run, ledger append, or retained-evidence mutation occurred.
- Full `uv run --project backend python -m pytest modeling_team/tests -q` reached **718 passed, 1 skipped, 218
  subtests** but failed the frozen-surface gate: actual `modeling_team/runner.py` SHA-256 was
  `47dbd1b81ea0203ff8b34889714f6166165b60d0f0259e5dbf042bb13dce04a6`, while the updated test still expected
  `05fb9e2f109f0c3541550588433b0124d8b8abb49514974d53fbbd20ba241060`. This is a release-blocking frozen-hash
  drift caused by the final Runner wording whitespace change, not a behavior-test failure.
- Result: **FAIL** for the deterministic gate; update the reviewed frozen hash to the final Runner bytes, rerun
  `test_p2a_codex_runtime.py` and the full modeling suite, then append a PASS recheck. Start7 remains blocked.

### Round 15 — 2026-08-11 final native-result/frozen-hash recheck — PASS deterministic gate / start7 may proceed

- Scope and safety: the final reviewed Runner bytes and frozen digest were rechecked in the shared worktree at
  HEAD `a220b766f42b67722ceb7b4b06d3faabea18a3b1`. `modeling_team/runner.py` SHA-256 is
  `47dbd1b81ea0203ff8b34889714f6166165b60d0f0259e5dbf042bb13dce04a6`, matching the approved frozen test. This
  tester edited only this append-only test plan; no product code, delivery record, retained evidence, real ledger,
  authorization state, or live modeling run was changed or started.
- Final focused gates all pass:
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py
    modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py
    modeling_team/tests/test_p2a_codex_runtime.py -q` -> **102 passed, 2 subtests passed**.
  - Native MCP result-shape regression, `uv run --project backend python -m pytest
    modeling_team/tests/test_protocol_retrieval_mcp.py -q` -> **11 passed, 13 subtests passed**. The native
    `build_candidate_conflict` result remains exactly `content` + `structuredContent`, with canonical JSON text;
    no `conflict_json` field is assumed.
  - Required ledger/policy focused command
    `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_budget_extension.py modeling_team/tests/test_r23005_ledger_isolation.py -q`,
    covering R2.3-003 plus R2.3-005 budget/isolation, -> **43 passed, 22 subtests passed**. Initial authorization remains exact first-only `+4`; after four semantic starts and
    retryable terminal failures, explicit `+3` ID/reference replays to `cap=7`, `semantic_start_count=4`,
    `active_reservations=0`; premature/unconsumed/no-predecessor, boolean/zero/negative, duplicate ID/reference,
    and tampered replay cases reject. R2.3-002 and R2.3-005 fixed policy/namespace assertions remain unchanged.
- Full deterministic regression: `uv run --project backend python -m pytest modeling_team/tests -q` -> **719
  passed, 1 skipped, 218 subtests passed**. `uv run --project backend python -m compileall -q modeling_team
  backend/app backend/tests` and `git diff --check` both pass.
- Read-only live boundary: `workspaces/modeling-runs/.r2-3-003-start-ledger.jsonl` remains **19 lines**, SHA-256
  `f31956c27a2c1e4dc38f6c59011dfd27701b3a4cbaf63f491d7134add64eeba3`, ending with start6 terminal failure. No
  R2.3-003 start7 directory, new reservation, active modeling process, or Unix socket was found; existing
  R2.3-005 start7-named directories are unrelated and were not modified.
- Result: **PASS for the repaired deterministic prompt/API/frozen gate**. The native conflict path is mechanically
  consistent with its actual MCP response shape, the full R2.3-005 regression remains green, and the approved hash
  is stable. The live R2.3-003 semantic acceptance is still unexecuted; start7 may proceed only under the existing
  authorization and normal live-run/cleanup controls, with its independent semantic result still to be tested.

### Round 16 — 2026-08-11 independent start7 evidence/ledger audit — FAIL/BLOCKED

- Scope and safety: this audit was read-only against the retained `r23003-real-20260811-deepseek-start7` evidence,
  shared R2.3-003 ledger, and cleanup artifacts. The tester did not start or continue a run, mutate retained
  evidence, append the ledger, edit product code, or edit the delivery record. Prestart scope evidence remains
  retained and exact (`project_id=7fc146d8-c76f-417b-9314-854544f269fc`,
  `ontology_id=fd762f52-2f5e-4bc0-902a-5583135ab64d`, `workspace_version=0d34f5ada161d2c6deb4a7b117c6b1469b540eef7eb1f04c8bdce97e5100ef02`);
  runtime core hashes before/after cleanup are unchanged.
- Accepted receipt followed by live-binding failure: `evidence/formal-candidate-progress.jsonl` records candidate
  revision `r2-3-003-existing-scope-incremental-v1`, delivery-5 digest
  `ac863afba7be5aca215ca9ae6a6f5e467570df65fc64c32b1b019e71579aa4a4`, receipt delivery-6 registered and state
  `accepted`. Only afterward, `evidence/issue-report.jsonl` records Phase-A binding failing closed because
  `relation-decision-produced-by` declared `workflow-b` with `expected_class=Workflow`, while the live canonical
  projection resolved `workflow-b` to actual `class_semantic_id=InvokingWorkflow`. The exact-Class contract correctly
  rejects the subclass as a mismatch; the candidate was not translated and no Phase-B delete batch was emitted.
- Conflict lifecycle defect: `evidence/capability-calls.jsonl` records `protocol_build_candidate_conflict` rejected
  with `TeamConfigurationError: typed candidate is not awaiting a Protocol response`; the issue report classifies
  the Runner request as **-32001** because the accepted receipt for original delivery-5 had already closed the
  conflict path. Expected repair sequence is receipt-v1 -> live binding mismatch -> typed conflict -> full revision-v2
  -> replacement receipt-v2, with stale receipt-v1 rejected and no duplicate accepted response.
- Mutation and cleanup: issue report/resolution state **zero-mutation** (only read-only workspace/modeling/project,
  entity/class/fact, and lineage calls), with abort reason `runner-abort-before-settlement`. Cleanup evidence reports
  `credentials_destroyed=true`, `active_handles=0`, `zero_child_residue=true`, `status=aborted`, and
  `settled=false`; state is `TERMINAL_REPORT_COMPLETE`. No retained start7 process or Unix socket remains. This is
  safe zero-mutation abort evidence, but it is not a successful semantic acceptance or settlement.
- Strict ledger defect and gate: `.r2-3-003-start-ledger.jsonl` is now **21 lines**, SHA-256
  `fc3f4cfb3d068b24ae974762c6e5039ae4063bba32f96c35aded44fa2204865c`. Its final records are start7 reservation
  and `semantic_start` only; no terminal-failure record follows the aborted run. The abandoned active reservation
  therefore remains unreconciled. Expected append-only repair is a retryable `platform-contract` terminal failure
  for start7 (without rewriting prior lines); until that reconciliation and the receipt-v2 lifecycle repair are
  independently verified, **start8 is blocked**.
- Result: **FAIL/BLOCKED** for live R2.3-003 acceptance and start8 admission. The exact-Class binding behavior and
  zero-mutation cleanup are correct safeguards, but the accepted-receipt/live-binding lifecycle rejects the needed
  typed conflict and the strict ledger lacks the required terminal-failure reconciliation. Developer must repair
  those narrow surfaces, then tester will re-run the receipt-v1 -> conflict -> revision-v2 -> receipt-v2 flow, stale
  receipt rejection, R2.3-005 compatibility/full suite, and final start8 gate.

### Round 17 — 2026-08-11 post-receipt lifecycle/ledger-repair recheck — PASS deterministic repair / BLOCKED start8

- Stable handoff and safety: the developer's final uncommitted repair was rechecked at HEAD `9e55c31545e50d4f64636543525c0fa13dfafcc5`; Runner SHA-256 is
  `eaea70c12e8c6d134ae609a45c84868f7174af883d3abd8d18956c6930ea01d7`, matching the updated frozen surface. The
  tester did not start a live run, append the real ledger, alter retained start7 evidence, or edit product code;
  only this test-plan round was appended.
- Post-receipt lifecycle regression: the new formal-progress test passes the required sequence receipt-v1 accepted
  -> live `Workflow`/`InvokingWorkflow` binding conflict -> typed zero-mutation conflict -> full revision-v2 with
  corrected `expected_class=InvokingWorkflow` -> replacement receipt-v2 accepted. Replay of stale receipt-v1 is
  rejected, and the existing conflict/revision/routing regressions remain green: **3 focused tests passed**.
- Focused deterministic commands (run serially to avoid the fixed credential-order fixture's shared run ID):
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py
    modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py
    modeling_team/tests/test_p2a_codex_runtime.py -q` -> **105 passed, 2 subtests passed**.
  - `uv run --project backend python -m pytest modeling_team/tests/test_protocol_retrieval_mcp.py -q` -> **11
    passed, 13 subtests passed**.
  - `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
    modeling_team/tests/test_r23005_budget_extension.py modeling_team/tests/test_r23005_ledger_isolation.py -q`
    -> **45 passed, 22 subtests passed**; R2.3-002/R2.3-005 policy and namespace regressions remain green.
  - Full `uv run --project backend python -m pytest modeling_team/tests -q` -> **722 passed, 1 skipped, 218
    subtests passed**. `compileall` and `git diff --check` pass.
- Abort reconciliation contract: the new strict temporary-ledger test passes a zero-mutation abort terminal failure
  with canonical seven-field evidence and permits the next reservation (**1 test passed**). A read-only probe using
  a temporary copy of the real 21-line ledger, the real start7 run ID/baseline, and canonical hashes of retained
  issue/cleanup evidence accepted `StartLedger.terminal_failure(..., terminal_evidence=...)` and then a probe start8
  reservation. This demonstrates that one controlled historical reconciliation is mechanically safe; it did not
  write the real ledger or launch a run.
- Live ledger gate remains blocked: the actual `.r2-3-003-start-ledger.jsonl` is still **21 lines**, SHA-256
  `fc3f4cfb3d068b24ae974762c6e5039ae4063bba32f96c35aded44fa2204865c`, ending with start7 reservation/semantic-start
  and no terminal failure. Start7's retained evidence still shows accepted receipt-v1, exact-Class binding mismatch,
  typed `-32001` on the old lifecycle, zero-mutation abort, `credentials_destroyed=true`,
  `active_handles=0`, `zero_child_residue=true`, `settled=false`, and no process/socket. The repair handles future
  issue aborts; it does not retroactively append this historical record.
- Result: **PASS for the repaired deterministic receipt/conflict/ledger API and R2.3-005 regression; BLOCKED for
  start8**. The parent/operator should perform exactly one append-only historical reconciliation through the strict
  `StartLedger` API (preferably a reviewed CLI/operator action) after appending canonical
  `evidence/terminal-reconciliation.jsonl` bound to start7 issue/cleanup hashes. Do not hand-edit or rewrite ledger
  lines, and do not let tests perform this mutation. Re-audit the resulting line/hash and reservation eligibility,
  then the final start8 gate may proceed under authorization.

### Round 18 — 2026-08-11 independent start8 evidence audit — FAIL/BLOCKED

- Scope and safety: this round only read retained `r23003-real-20260811-deepseek-start8` evidence and the shared
  ledger. No live run was started or continued, no ledger line was appended, and no product or retained evidence
  file was edited by the tester. Worktree HEAD is `64dc9e6619129a7607dc1128a8037932b2149e59`.
- Candidate and accepted receipt: `formal-candidate-progress.jsonl` records complete candidate revision
  `r2-3-003-incremental-1`, delivery-5 and delivery-6 accepted receipt, candidate/semantic digest
  `84ca5f468de332788215fb178ca0ae6c3df171a613215f51226010077a2c4a08`. The candidate contains the two frozen
  ordered delete declarations and the bounded business slice, but its business slice declares class `Content` and
  `Content`-typed predicates/entities; the retained ontology read model lists no `Content` class (only
  `ExplicitUnknown`, `InvokingWorkflow`, `OutputField`, `SemanticResource`, `Workflow`, and `WorkflowVersion`).
- Read-only impact evidence: both required delete-target statement contexts are complete with `next_cursor=null`:
  `unknown-cross-release-output-meaning` response digest
  `5f59350310730d1ed73de7085700041cff1418c9b47e435fcb7c0b12c478d5c6` (page/snapshot
  `7f1e9b359f9e19da1ddf8d7ce3d652e7d1592b81b070d3df50d899a18d84bc91`) and
  `unknown-b-no-score-behavior` response digest
  `e26363f6b741e554fbcca583e743f853205bd6c963f3209b0036d5841ab0bdde` (page/snapshot
  `de860a2476470b30b49f69c23a1c6a8cc6eaadf111e8c1deba14515395f58d15`). No Build Session, lease, batch, or
  mutation occurred.
- Typed conflict/transport failure: `capability-calls.jsonl` confirms `protocol_build_candidate_conflict` itself
  returned `ok=true` for `missing_class_dependency`. The subsequent exact typed conflict reply to Modeling, bound
  to `reply_to=delivery-5` and `expects_reply=true`, was rejected by Team Transport with **MCP -32000** after two
  attempts because delivery-6 had already been accepted for delivery-5; no replacement conflict delivery reached
  Modeling. This is a broker/progress second-reply defect, not a candidate-gate or mutation failure.
- Zero mutation and cleanup: `issue-report.jsonl` records mutation state as prose-prefixed
  `zero-mutation; only read-only platform calls performed (...)`, and the issue resolution/abort explicitly state
  zero mutation. Cleanup is clean: `state.json` is `CLEANED`; acceptance cleanup has
  `credentials_destroyed=true`, `active_handles=0`, `zero_child_residue=true`, `status=aborted`, and
  `settled=false`; scope before/after context is identical with no active leases/sessions/in-flight attempts and
  project/admin keys revoked. No start8 process or Unix socket remains.
- Automatic reconciliation failure and ledger state: the strict future-abort reconciler requires the canonical
  mutation-state value `zero-mutation`, so the prose-prefixed issue field was rejected and no start8 terminal-failure
  record was appended. The real `.r2-3-003-start-ledger.jsonl` is now **24 lines**, SHA-256
  `517c2688f7de25fc14ec63247fc04aa494ca1b5cb4b8e15c9d65d21729104d63`; line 22 is the corrected start7
  `platform-contract` terminal failure, lines 23–24 are start8 reservation/semantic-start, and the tail has no
  start8 terminal failure. Read-only `StartLedger` replay reports `start_cap=7`, `semantic_start_count=7`, and no
  active reservation; strict next-start eligibility is nevertheless blocked because the latest semantic start lacks
  its required terminal failure and the cap is consumed.
- Result: **FAIL/BLOCKED** for start8 and any start9/further semantic start. Developer must repair the standalone
  conflict broker path so a valid typed post-receipt conflict can reach Modeling exactly once, normalize/extract the
  canonical `mutation_state=zero-mutation` before automatic reconciliation, and preserve R2.3-005 behavior. After
  that handoff, tester will independently run the standalone conflict-broker/canonical-mutation-state tests plus
  the R2.3-005 compatibility and full modeling suite. No new live start is authorized while this blocker remains.

### Round 19 — 2026-08-11 standalone broker/mutation-prefix repair recheck — PASS deterministic / BLOCKED live budget

- Scope and safety: independently tested the stable uncommitted repair at HEAD `64dc9e6619129a7607dc1128a8037932b2149e59`.
  The tester did not start a live run, append the real ledger, alter retained evidence, edit product code, or edit the
  delivery record; only this append-only test-plan round was changed. Runner SHA-256 is
  `c53a1d83b030f1983696fdc50324fc279d831f718654bf16feccba4c1c1e4163`, matching the reviewed frozen test.
- Standalone post-receipt broker sequence: the focused R2.3-005 candidate-progress tests pass **2 tests** (32
  deselected), including receipt-v1 acceptance -> live binding mismatch -> one standalone Protocol-to-Modeling
  typed conflict (`reply_to=None`) -> full revision-v2 -> replacement receipt-v2, with stale receipt-v1 rejected.
  The conflict reply is now bound to the standalone conflict delivery rather than attempting a second reply to the
  accepted receipt; no duplicate accepted response is produced.
- Mutation-state/reconciliation contract: focused R2.3-003 tests pass **3 tests** (15 deselected), proving the exact
  canonical `zero-mutation` and the accepted `zero-mutation; ...` prefix normalize to strict ledger evidence, while
  nonzero/invalid mutation state is rejected without ledger mutation. The prompt wait-boundary assertion passes **1
  test** (17 deselected). Native `build_candidate_conflict` result shape remains canonical: **11 tests, 13 subtests**
  passed, with only `content` and `structuredContent` and canonical JSON content.
- Focused deterministic gates (run serially to avoid the fixed credential-order fixture's shared run ID) pass:
  `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
  modeling_team/tests/test_r23003_revision_contract.py modeling_team/tests/test_r23005_candidate_progress.py
  modeling_team/tests/test_r23005_mechanical_spine.py modeling_team/tests/test_r23005_complete_revision.py
  modeling_team/tests/test_p2a_codex_runtime.py -q` -> **107 passed, 2 subtests passed**; and
  `uv run --project backend python -m pytest modeling_team/tests/test_r23003_incremental_contract.py
  modeling_team/tests/test_r23005_budget_extension.py modeling_team/tests/test_r23005_ledger_isolation.py -q`
  -> **46 passed, 22 subtests passed**. R2.3-005 budget/namespace policy and frozen runtime surfaces remain green.
- Full deterministic regression: `uv run --project backend python -m pytest modeling_team/tests -q` -> **724
  passed, 1 skipped, 218 subtests passed**. `uv run --project backend python -m compileall -q modeling_team
  backend/app backend/tests` and `git diff --check` pass. The frozen Runner digest above matches
  `modeling_team/tests/test_p2a_codex_runtime.py`.
- Read-only live boundary: `.r2-3-003-start-ledger.jsonl` remains **24 lines**, SHA-256
  `517c2688f7de25fc14ec63247fc04aa494ca1b5cb4b8e15c9d65d21729104d63`. Its tail is unchanged: corrected start7
  `platform-contract` terminal failure, then start8 reservation and `semantic_start`, with no start8 terminal failure.
  The cap is consumed (`start_cap=7`, `semantic_start_count=7`, no active reservation); no new reservation, process,
  socket, or ledger write was made by this round. Therefore live start8/start9 acceptance remains **BLOCKED** pending
  the operator-controlled append-only reconciliation of the historical start8 zero-mutation abort; deterministic
  repair and all R2.3-005/full-suite gates are **PASS**.
