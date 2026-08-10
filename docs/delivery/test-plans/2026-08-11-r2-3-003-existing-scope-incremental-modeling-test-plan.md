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

### Round 1 — 2026-08-11 independent deterministic contract test — PASS / real run BLOCKED

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
  not PASS. Therefore this round is a deterministic implementation gate PASS, while the requirement-level
  completion gate remains BLOCKED pending an authorized real run and independent read-only acceptance.
- Defects: none found in the executed deterministic scope. Recommendation: do not request a product-code
  repair from the requirement developer for this round; proceed only after the main agent decides the
  separate real-run authorization/operation gate.
