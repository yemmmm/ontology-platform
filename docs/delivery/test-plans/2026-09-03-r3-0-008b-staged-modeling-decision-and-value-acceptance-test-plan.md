# R3.0-008B 建模决策分阶段流程与值语义联合验收 — 共享测试计划（第一段：机械增量）

- 日期：2026-09-03
- 路径：`docs/delivery/test-plans/2026-09-03-r3-0-008b-staged-modeling-decision-and-value-acceptance-test-plan.md`
- 状态：计划评审通过（2026-09-03，Round 3 窄确认 PASS，见设计文档状态区）。同日按用户
  外部评审四项发现修订（真实提交信封 + `inspect.signature` 对照、acceptance.py 端点分派
  与写转发器、coordinator approvals artifact 交叉校验、durable intent/幂等恢复），修订内容
  见设计文档状态区。待执行
  （开发者自测 → `requirement_tester` 独立复核；轮次记录区见文末）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-008B（最小验收条件 1–4）
- 设计：`docs/delivery/designs/2026-09-03-r3-0-008b-staged-modeling-decision-and-value-acceptance-design.md`
- 执行者：开发者先自测；`requirement_tester` 独立复核（独立验收轮次结构见 §8）
- 测试位置：`modeling_team/tests/`（pytest）+ `docs/delivery/evidence/2026-09-03-r3-0-008b/`
  （独立轮证据）
- 依赖基线：R3.0-002（场景地图/拓扑门/独立平台 MCP 门，Round 1 PASS）与 R3.0-008A
  （L1/L2/L3 合同与 G7，Round 1 PASS）全部已完成；本计划在其上叠加，不修改其用例
- 两段口径：本计划**只覆盖第一段机械增量**（阶段门/artifact schema/Runner 校验/三角色
  prompt 增量/任务条目）；第二段（真实建模运行联合验收）挂 R3.0-006 授权体系并待
  R3.0-009 机械增量完成后另行执行，其证据与本计划不得互替

## 1. 测试边界

本计划只验收 R3.0-008B 第一段：

1. 新模块 `staged_decisions.py` 的全部 artifact 合同与匹配规则（确定性单测）；
   Runner 门接线（stage3 先决门、checklist 终态门、approvals 交叉校验、ledger/intent/receipt
   交叉校验、kill-switch）；
   capability `protocol_staged_submit_modeling_batch` 的拒绝/通过路径（fake 写转发器）与
   durable intent 生命周期（含 unknown 裁决三分支）；提交信封与 backend
   `submit_modeling_batch` 真实签名的对照契约测试；
   守恒（无参数任务零行为变化）；smoke 任务条目机械链路。
2. **零 backend 改动是硬边界**：`git status`/`git diff` 下 `backend/`、`frontend/` 必须零
   变更（F4）；`SAFE_PROTOCOL_TOOLS` 字节不变；008A 交付的 G7 等完整性校验不重验（其
   Round 1 证据持续有效，交界不重复建设）。
3. **第二段范围（本计划显式不覆盖、不得声称覆盖）**：
   - 真实建模运行下的联合验收闭环（业务语义/共性/跨切片跨 Ontology/值语义召回与 SQL
     映射链的真实证据）；
   - 008A 验收条件 3 代表问题「查询因为缺料而延期的订单」的**真实场景复验**（008A 已以
     fixture 验收，本段只在 checklist schema 中登记该固定项）；
   - RDF 未复制业务行的**真实断言**（本段以零 RDF 写 + checklist 固定项登记代替）；
   - 阶段 3 共性抽象详细合同（R3.0-009 专项；本段只验槽位存在性与批准记录）；
   - checklist `verdict` 的语义真伪。
4. 第一段验收载体为确定性机械校验 + fixture 任务条目：**零 Modeling Batch 提交、零
   dry-run、零 apply、零 RDF 写、零 Build Session/Lease/modeling start、零 attempt 消耗**
   （L 账面核对，F5/F6）。
5. 设计 §4.2 已记录边界（delete 触发集合、evidence_refs 格式口径、措辞不仲裁、直连 HTTP
   绕行登记面）不判 FAIL。
6. 领域风味名称（缺料、`PS`、`PartShortage` 等）只出现在 fixture 与断言；产品代码与
   prompt 增量无领域分支、无业务语义（F4 grep 门）。

## 2. 稳定测试命令

从仓库根执行（002 先例）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q
uv run --project backend ruff check modeling_team
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-008b-staged-decisions-smoke.yaml
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-008b-staged-real.yaml
cd backend && uv run pytest    # backend 零 diff 时的确认性全量（基线不回归）
```

- 聚焦：`... -m pytest modeling_team/tests/test_r30008b_staged_decisions.py
  modeling_team/tests/test_r30008b_runner_wiring.py -q`。
- capability 转发在单测中一律使用注入式 fake 转发器（不触网络、不触 8001 共享运行时）；
  smoke 任务零提交，capability 只被拒绝路径触达（不触平台）。
- 若（例外）发生 backend 窄修复：`cd backend && uv run pytest` 全绿 →
  `systemctl --user restart ontology-platform.service` → 健康检查（§8 L1），并在轮次记录
  显式论证缺口与修复面。

## 3. Fixture 设计

1. **artifact fixture（pytest 内建，tmp run-root，不触真实 workspaces）**：以设计 §3.3/§3.6
   示例为蓝本的机械合法集——`value-semantics/conclusions/analysis-conclusions.json`
   （ac-0001「缺料」confirmed/`PS`/L3 + ac-0002「已完成」analyzed/L2）+
   `value-semantics/conclusions-archive/ac-0001.r1.json`（analyzed
   revision 1）+ `value-semantics/approvals/approvals.json`（含 ac-0001 revision 2 的
   `conclusion_confirmation` 与 `stage3_slot` 记录）+
   `value-semantics/unlock/materialization-unlock.json`（materialize 模式，confirmed_codes 含 ac-0001）
   + skip 形态变体 + `stage3-neutral-graph/neutral-candidate.json`（占位路径可达）+
   `joint-acceptance-checklist.json`（七固定项全 `pending`）+ ledger/receipt 配对集。
   占位值可用 `placeholder-*` 命名空间替换领域词，断言口径不变。
2. **违约 fixture 变体**（逐 reason code 一一对应，见 §5）；符号链接/路径逃逸变体（复用
   002 `_safe_gate_path` 测试形态）。
3. **capability 载荷 fixture**：设计 §3.6 的 create_entity + create_enum_meaning 双命令载荷
   （**真实信封**：`session_id`/`client_batch_id`/`ontology_id`/`idempotency_key`/
   `expected_workspace_version`/`items[{command_kind, payload}]`/`mode`/`lease_token`，含
   `value_traces`/`l3_nodes` 附参）及各违约变体；fake **写**转发器返回确定性成功/失败/
   不可判定（超时/不可解析响应）三类响应。信封违约变体含：缺 `idempotency_key`、缺
   `expected_workspace_version`、`items` 缺席/为空、`apply_atomic` 缺 `lease_token`、旧形态
   `build_session_id`+`commands[]`。
   **信封契约对照测试（防 fake 转发器假 PASS）**：测试以 `inspect.signature` 反射导入
   backend 真实工具 `submit_modeling_batch`（`PYTHONPATH=backend:.`，与既有单测同法），
   断言设计/实现采用的信封字段集合与真实签名逐参数一致（含 `mode`/`lease_token` 默认值
   语义：`apply_atomic` 必须显式携带 `lease_token`）；期望字段集合由测试作者独立写死，
   与被测代码无共享常量来源。
4. **smoke 任务条目**（`r3-0-008b-staged-decisions-smoke.yaml`，冻结资产）：零建模写——
   coordinator 维护 002 场景地图 + stage3 槽位 + 分析结论（占位条目）+ unlock（skip 形态）
   + checklist（七项 pending）全部结构合格；protocol 只观察 staged 门 reason code 流转并
   尝试一次 capability 提交以收集 `staged_value_materialization_locked` 拒绝回执（skip 模式
   下确定性拒绝，零平台调用）；expected_terminal_evidence：`staged-artifacts-structurally-valid`
   / `stage3-slot-accepted` / `staged-gate-reason-codes-reported` /
   `capability-rejection-receipted` / `zero-modeling-writes`。
5. **机械基准**：期望 reason code、receipt 字段、digest 均由测试作者按合同独立写死，与被测
   代码无共享常量来源（002 先例）。
6. 每用例后清理 tmp run-root；smoke 运行后清理 run workspace 与临时文件。

## 4. 成功路径（S，机械单测 + 接线）

- **S1 结论合同通过**：§3.1 合法 fixture 全过 `validate_analysis_conclusions`（含 archive
  链与 analyzed→confirmed 转换合法性）；entries 空列表合法（A2）。
- **S2 unlock 合同通过**：materialize 形态（confirmed_codes 与当前结论逐字段一致）与 skip
  形态（`skip_reason="no_schema_no_interface"`、无 confirmed 条目）均通过（A3）。
- **S3 stage3 槽位先决门**：staged 任务 run-root 中槽位不合格 → 门 closed 且 reason code 为
  `stage3_*`，同 tick 拓扑检查**未执行**（`_multi_slice_gate_opened` latch 未置位、
  state.json 未被 `close()` 覆写）；补齐槽位 artifact 后（真实修复序列），拓扑条件满足 →
  门 open 且只开闸一次；非 staged 任务不受槽位影响（A4/A5）。
- **S4 capability 通过路径**：合法载荷（真实信封 + confirmed 结论 + 匹配
  `property_iri`/`enum_value` + L3 附参闭合）经 fake 写转发器返回成功 → durable intent 先于
  转发落盘（`status=submitted`）→ receipt 写入（ordinal 递增、`intent_ordinal`/`idempotency_key`
  回填、逐命令 digest、value_traces/l3_nodes 回填、response_digest）→ intent 置
  `receipted`（顺序断言：receipt 存在时必先有同键 intent；A4）。
- **S5 物化追溯链闭合**：receipt → ledger 条目 → 结论推进 `materialized`（新修订）全链
  `validate_materialization_ledger` 通过；`reconcile_platform_batches` 对账一致（A4/A7）。
- **S6 checklist 结构门**：七固定项恰各一条、字段合法 → 通过；终态前缺失 → monitor 以
  `acceptance_checklist_missing` 反馈并拒绝终态（A4）。
- **S7 修订与历史**：ac-0001 以 revision 2 取代 revision 1、archive 保留、跨版本转换
  `analyzed→confirmed` 合法；`conflict→analyzed`（revision+1、confirmed_* 清空）合法（A7）。
- **S8 skip 语义**：skip 形态下 capability 对枚举命令稳定拒绝、对无枚举命令的载荷照常
  转发（fake）（A3/A4）。
- **S9 staged 可写 bind**：staged 任务的新 artifact 目录按设计 §3.9 唯一写者约束 bind 到
  对应角色沙箱（modeling：`value-semantics/conclusions/` + `conclusions-archive/` +
  `stage3-neutral-graph/`；coordinator：`value-semantics/unlock/` +
  `value-semantics/approvals/` + `joint-acceptance/`；
  protocol：`value-semantics/ledger/`；Runner host 侧独占
  `value-semantics/submission-receipts/` + `value-semantics/submission-intents/`，不经沙箱
  bind），bind 单元为目录、prepare 期只 mkdir 不预创建文件
  （可选 artifact 缺席即门语义）；负向检查：非写者角色对上述目录无写通路；三角色对
  `value-semantics/` 树只读互见；非 staged 任务 bind 集与 002 基线
  逐字节一致（A5/F1）。
- **S10 approvals 交叉校验通过**：coordinator approvals artifact（§3.6b）含 ac-0001
  revision 2 的 `conclusion_confirmation` 与 stage3 `stage3_slot` 记录 → 与 confirmed 结论、
  stage3 槽位交叉校验全过；结论以 revision 3 重回 `analyzed` 后旧 approval 失效（再次
  `confirmed` 需新 approval 条目）（A2/A4）。

## 5. 边界路径（B，逐条确定性拒绝）

- **B1 结论违约**：schema 漂移 / `analyzed` 带 `confirmed_enum_value` / `confirmed` 缺
  `confirmed_by` / `conflict` 缺 `conflict_note` → `conclusions_invalid_status_fields`；
  `analyzed→materialized`、`materialized→analyzed` → `conclusions_illegal_transition`；
  revision 回退/跳号 → `conclusions_revision_regression`；`materialized` 无 ledger 条目 →
  `conclusions_materialized_without_ledger`；非 JSON/符号链接 → `conclusions_unparsable`。
- **B2 unlock 违约**：confirmed_codes 与结论不一致 → `unlock_code_mismatch`；悬空
  conclusion_id → `unlock_dangling_conclusion`；skip 形态含 confirmed 条目或
  skip_reason 字面量错误 → `unlock_skip_inconsistent`。
- **B3 阶段 5 时点门**：无 unlock（或 skip 模式）时含 `create_enum_meaning` 的载荷 →
  `staged_value_materialization_locked`；结论 artifact 缺失/不可解析且载荷含枚举命令 →
  `staged_conclusions_unavailable`；门未开时任何提交 → `staged_gate_closed`。
- **B4 物化匹配违约**：无 trace → `staged_missing_trace`；结论 `analyzed` →
  `staged_conclusion_not_confirmed`；`conflict` → `staged_conclusion_conflict`；
  `materialized` → `staged_conclusion_already_materialized`；`property_iri` 或
  `enum_value` 不匹配 → `staged_trace_mismatch`；update 不带 `enum_value` 且目标无法回溯
  → `staged_unknown_enum_target`。
- **B5 L3 违约**：`semantic_value` 不在本批/已核销 L3 IRI 集合 →
  `staged_dangling_semantic_value`；`l3_nodes` 对应结论非 confirmed 或有效层级非 L3 或缺
  对应 `create_entity` → `staged_l3_unapproved`。
- **B6 载荷与转发违约**：`batch` 信封违约（缺 `idempotency_key` / 缺
  `expected_workspace_version` / `items` 缺席或空 / `apply_atomic` 缺 `lease_token` / 旧形态
  `build_session_id`+`commands[]`）→ `staged_submit_schema_mismatch`；fake 写转发器明确
  失败 → `staged_batch_forward_failed`（错误摘要透传，无吞并），intent 保持 `submitted`；
  fake 转发器不可判定（超时/响应不可解析）→ `staged_batch_forward_unknown`，intent 置
  `unknown`。**unknown 裁决三分支**：平台清单按 `client_batch_id`/`idempotency_key` 命中 →
  认领补 receipt、intent 置 `receipted`（同键重放不重复 apply）；确认未命中 → 允许同一
  幂等键重试；存在未裁决 unknown intent 时一切新提交被拒绝；悬置 unknown → monitor
  kill-switch `staged_unreconciled_batch`。
- **B7 ledger/对账违约**：ledger 条目与 receipt 三元组不一致 → `staged_ledger_stale`；
  `receipted` intent 无对应 receipt → `staged_unreconciled_batch`；
  平台批次清单出现不可对账批次（平台有而 intent 无 = 绕行直连；intent `receipted` 而平台
  无 = 假回执）→ `staged_unreconciled_batch` 且门关闭（kill-switch）。
- **B8 checklist 违约**：缺固定项/重复 item_id/字段漂移 →
  `acceptance_checklist_schema_mismatch`；非 JSON → `acceptance_checklist_unparsable`。
- **B9 stage3 槽位违约**：artifact 缺失/不可解析/schema 漂移/`approved_by` 空/
  `candidate_artifacts` 不可达或符号链接 → 对应 `stage3_*` code。
- **B10 参数依赖**：`staged_modeling_decisions: true` 而 `multi_slice_workflow` 缺失/false →
  `TeamConfigurationError`（contracts 校验）。
- **B11 approvals 交叉校验违约**：conclusions 中 `confirmed`/`materialized` 条目无同
  `conclusion_id`+`revision` 的 `conclusion_confirmation` 记录 →
  `conclusions_approval_missing`；stage3 槽位无对应 `stage3_slot` approval 记录 →
  `stage3_approval_record_missing`；approvals 非 JSON/schema 漂移 →
  `approvals_unparsable` / `approvals_schema_mismatch`。
- **B12 信封契约对照**：反射导入 backend `submit_modeling_batch` 真实签名，断言 capability
  信封字段集合与真实参数集逐项一致——若实现（含 fake 转发器包装层）出现 `build_session_id`/
  `commands` 等真实签名不存在的字段或缺失真实必填字段 → FAIL（防 fake 转发器假 PASS）。

## 6. 失败路径（F，若发生即 FAIL）

- **F1 守恒破坏**：无 `staged_modeling_decisions` 参数的既有任务（含 002 smoke/formal 任务
  fixture）任何行为变化；staged 检查/capability 广播泄漏到非 staged 任务；非 staged 任务的
  沙箱 bind 集与 002 基线不一致。
- **F2 绕过面激活**：staged 任务配置仍含直连 `submit_modeling_batch`（`protocol_tools`
  审计）；capability 在任一 §5 拒绝条件下放行。
- **F3 确定性破坏**：同一违约输入产生不同 reason code / 不同 receipt 字段；digest 计算
  不稳定。
- **F4 边界守恒（grep 门）**：`git diff` 范围超出设计附录 A 清单；`backend/`、`frontend/`
  任何变更；`SAFE_PROTOCOL_TOOLS` 字节变化；新增源码或 prompt 增量含
  `缺料`/`PS`/`PartShortage`/fixture 表列名等领域字符串；新增 API 路由/MCP 工具/migration。
- **F5 建模零消耗破坏**：测试期间平台出现新建 Build Session / Modeling Batch / modeling
  start（L 账面核对；capability 经 fake 转发器，零平台调用）。
- **F6 回归**：`modeling_team` 全量 pytest 出现新失败；backend 确认性全量低于基线；ruff
  报错。

## 7. 回归（R）

- **R1 modeling_team 全量**：§2 命令全绿（含 002 既有 `test_r30002_*`、`test_contracts.py`、
  `test_runner.py` 零回归）。
- **R2 backend 确认性全量**：`cd backend && uv run pytest` 与基线一致（证明零 diff 无隐性
  耦合）。
- **R3 任务资产**：两个新任务条目 + 复用 profile 通过 validate CLI；008B 真实任务条目头部
  注明双重启动门（009 机械增量 + 006 授权）未被移除。

## 8. 独立测试轮次（L）

1. **L1 健康与基线**：`ontology-platform.service` active；backend `/api/health` 200、
   frontend 5173 200；`alembic current` 不变（零 migration）；`git status` 核对改动仅限
   设计附录 A 清单；008A/002 既有测试计划状态未被改写。
2. **L2 机械 smoke（真实 Runner 链路，循 002 L 先例；完成门必需）**：以
   `r3-0-008b-staged-decisions-smoke.yaml` 执行一次真实 Runner 机械运行（staged 任务、
   零建模写）：观察 staged 门 reason code 流转（`stage3_*` → 拓扑 `topology_*` → 开闸 →
   capability 拒绝回执）与 artifact 合格性反馈；证据（门 state 文件时序、反馈投递记录、
   capability 审计日志）落 `docs/delivery/evidence/2026-09-03-r3-0-008b/`。运行时外部
   条件不可用（模型 API/沙箱故障）判 **BLOCKED**，不得以单测模拟冒充 L2 证据，由主代理
   裁决重试或降级并显式记录。
3. **L3 轮次记录**：§轮次记录登记每轮判定、缺陷与窄修复（只修最窄失败层并在设计文档
   登记）。轮次结构：开发者自测轮（全 S/B/F/R + L2 演练）→ 独立测试 Round 1（全量复证，
   含 L2 现场或在开发者轮证据上独立复核 Runner 日志与门 state 时序）→ 如 FAIL，窄修复后
   Round 2 复测失败项 + 受影响面。独立测试不创建也不延续其评估的运行，不改动已保留证据。

## 9. 清理

1. 删除全部 tmp run-root 与 smoke run workspace；确认真实 `workspaces/modeling-runs/` 无
   测试残留 artifact。
2. 删除临时探针与含密钥的临时文件；fake 转发器不留任何网络副作用；独立轮证据留存（脱敏）。
3. 平台零资源核对：无新建 Build Session / Modeling Batch / 保护集 / key（F5 账面）。

## 10. 判定规则与完成门

- **PASS**：S1–S10、B1–B12、F1–F6、R1–R3、L1–L3 全部通过；设计 §6 A1–A8 全部有证据。
  PASS 只允许声明「R3.0-008B 第一段机械增量完成并冻结」；R3.0-008B 需求整体保持待验收，
  第二段（真实运行联合验收）待 R3.0-009 机械增量完成并由用户授权 R3.0-006 modeling start
  后执行。
- **FAIL**：任一 staged 门/ capability 拒绝路径放行（B3–B7）；守恒破坏（F1/F2）；确定性
  破坏（F3）；边界守恒破坏（F4，含 backend 任何 diff）；建模零消耗破坏（F5）；回归失败
  （F6/R）。
- **BLOCKED**：仅用于模型 API/沙箱/系统服务等外部条件不可用（L2），须显式记录并由主代理
  裁决。
- 完成后由主代理收口：更新需求状态（登记第一段机械增量 PASS、第二段待执行）与文档信息区
  链接；R3.0-008A 证据不被改写或追溯解释；R3.0-009/R3.0-010 状态不变。

## 11. 验收标准映射（需求最小验收条件 → 第一段覆盖面）

| 需求最小验收条件 | 第一段机械可验证部分（本计划） | 交界/第二段显式排除 |
| --- | --- | --- |
| 1 完整场景展示阶段产物与批准关系（切片数与 Ontology 数可不同；共性详细合同归 009） | 各阶段 artifact schema、门、批准字段（`approved_by`/`confirmed_by`/`unlocked_by`）机械存在且可校验，且协调批准锚定 coordinator 独占 approvals artifact（S1–S3/S6/S7/S10、B1/B2/B9/B11）；smoke 任务条目机械链路（L2） | 真实场景的完整阶段产物与批准关系展示归第二段；009 详细合同不在本段 |
| 2 编码未知候选值只有可追溯分析结论、RDF 无猜测产物、编码确认后按原分析统一物化 | 物化命令无 confirmed 结论即 fail-closed（B3/B4）；按 `mapped_property`+候选值机械匹配与 conflict 拦截（B4）；修订/历史追溯链（S5/S7） | RDF 侧「无猜测 `EnumValueMeaning`/L3」机械校验归 008A G7（已验收，不重验）；真实 RDF 断言与真实统一物化归第二段 |
| 3 联合验收闭环 + 008A 代表问题「查询因为缺料而延期的订单」真实复验 | 仅 checklist schema 含 `r3008a_representative_question_recheck` 等七固定项（S6/B8） | **整条归第二段**：真实召回/SQL 映射链/断链无法确认/代表问题真实复验，第一段不得声称任何部分覆盖 |
| 4 RDF 未复制业务行；受控值建模不扩张为维表/事实表同步 | 第一段零 RDF 写（F5 账面）+ checklist 固定项 `rdf_no_business_rows` 登记（S6） | 真实 RDF 断言归第二段；「不扩张为同步」的语义判定归第二段 |

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）

### 开发者自测轮（2026-09-03，`requirement_developer`）

（本条为补登：自测实际发生在独立测试 Round 1 之前、其代码基线之上；Round 1 观察到的「标题
仍为待执行」即指本记录当时缺失。D-1/D-2 窄修复为 Round 1 之后追加，结果附于本节末。）

- 执行者：`requirement_developer`。离线自测范围：S1–S10、B1–B12、F1–F6、R1–R3 全部执行；
  **L2 延期**（真实 Runner smoke 需活跃 codex 运行时并消耗运行预算，开发轮不启动真实 run，
  留待独立测试轮执行——Round 1 亦因模型 API 外部条件判 BLOCKED，与本轮延期理由一致）。
- 用例落点：`modeling_team/tests/test_r30008b_staged_decisions.py`（制品合同层，29 例）与
  `modeling_team/tests/test_r30008b_runner_wiring.py`（Runner/Runtime 装配层，24 例）；全部
  期望 reason code、B12 信封字段集、checklist 七固定项由测试作者独立写死，不与实现共享常量。
- 命令与结果（仓库根）：
  - `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q`
    → **1177 passed, 1 skipped, 318 subtests passed**（002 基线之上零新失败，R1/F6）
  - `cd backend && uv run pytest` → **957 passed, 36 skipped**（与基线一致，R2/F6）
  - `uv run --project backend ruff check modeling_team` → 10 errors，全部为既有基线
    （`runner.py` F821 `RuntimeDispatchReceipt` 与未改动的 `test_r23008_*/test_r23009_*`），
    本次变更零新增（F6）
  - 两个任务条目 `validate` CLI（profile r3-0-002-modeling-team.yaml）→ roster
    [coordinator, modeling, protocol] OK（R3）
  - F4 范围门：`git status`/`git diff` 与设计附录 A 逐项一致，backend/frontend 零 diff，
    `SAFE_PROTOCOL_TOOLS` 字节不变；新增代码/prompt 增量中 `缺料`/`PartShortage`/裸 `PS`
    零命中（fixture 全部 `example.test`/`placeholder-*` 命名空间）
  - F5：本轮零后端资源消耗（所有 runner 级用例使用伪造 forwarder/adapter）；测试 workspace
    全部清理（`workspaces/modeling-runs/` 无 `r30008b-*` 残留）

**Round 1 后窄修复（D-1/D-2，2026-09-03）**：

- D-1：补六个 reason code 显式用例（`stage3_unparsable`/`stage3_missing_approval`/
  `stage3_candidate_artifact_unavailable`/`conclusions_schema_mismatch`/`unlock_unparsable`/
  `unlock_schema_mismatch`），期望值独立写死（新增
  `test_d1_stage3_slot_failure_reason_codes_are_typed`、`test_d1_conclusions_schema_mismatch_is_typed`、
  `test_d1_unlock_failure_reason_codes_are_typed`）。
- D-2：`runner.py::_check_staged_decision_gates()` 步骤 1 的
  `staged_intent_receipt_issues()` 读取损坏 intent/receipt JSON 时不再抛
  `StagedDecisionArtifactError` 穿透前台循环，收敛为 `staged_unreconciled_batch` kill-switch
  （类型化反馈 + gate 关闭 + latch；仅此一处异常收敛，capability handler 路径与其余逻辑未动）。
  回归用例 `test_d2_corrupt_intent_json_converges_to_typed_kill_switch_not_crash`。
- 修复后重跑：`pytest modeling_team/tests -q` → **1181 passed, 1 skipped, 318 subtests
  passed**；`ruff check modeling_team` → 10 errors（与既有基线一致，零新增）。

### 独立测试 Round 1（2026-09-03，`requirement_tester`）

**总体判定：BLOCKED（仅 L2）**——S1–S10、B1–B12、F1–F6、R1–R3、L1 全部通过；L2 真实
Runner 机械 smoke 因模型 API 外部条件不可用按 §8 判 BLOCKED，未以单测模拟冒充。解除条件与
证据见下。

- 执行者：`requirement_tester`（独立轮；未创建、未延续任何真实建模 run，未消耗 modeling
  attempt；L2 尝试的 smoke run 零建模写，失败后按 §9 清理并留存脱敏证据）。
- 代码基线：HEAD `aefa0ed`（`b308451` 之后一个仅改 `docs/requirements/requirements-v3.0.md`
  的文档提交，与本需求实现无关）；未提交变更经 `git status`/`git diff` 核对与设计附录 A 逐项
  一致（6 新文件 + 6 文件增量，`backend/`、`frontend/` 零 diff）。另有与本需求无关的用户既有
  改动：`AGENTS.md`/`CLAUDE.md`、未跟踪 `.codex/agents/`、两份 delivery 文档。
- 008A/002 既有测试计划与证据未被改动（`git status docs/delivery/` 仅新增本需求两份文档）。

**实现复核（先审后测）**：`git diff` 逐文件对照设计附录 A 与功能合同 §3——`contracts.py`
参数封闭集扩展 + 依赖校验（B10）、`capability_mcp.py` staged 操作 schema/注册
（`ROLE_OPERATIONS["protocol"]` 扩为超集，端点组装仍按任务分派、`handle` 按端点自身
operations 拒绝未配置操作，非 staged 端点不受影响）、`acceptance.py` 端点分派与 staged
handler 注入、`runner.py` `_check_staged_decision_gates()` 先于拓扑门（drain 内
`_check_multi_slice_topology_gate()` 调用次数仍恰 1）、capability handler 固定求值顺序
（门→信封→unlock→匹配→intent→转发→receipt）、`codex.py` staged bind 表与
`--ro-bind` value-semantics + 角色独占 `--bind` 嵌套、三处 prompt 增量仅角色/时点/拒绝义务
（无业务语义）。B12 信封对照测试含测试者独立写死的期望字段集
（`test_r30008b_staged_decisions.py:558-568`），本轮另以独立脚本直查
`inspect.signature(submit_modeling_batch)` 复核：参数集与默认值
（`mode=apply_atomic`、`lease_token=None`）逐项一致。

**命令与结果**（仓库根）：

```text
env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q
→ 1177 passed, 1 skipped, 318 subtests passed in 47.56s   # 002 基线之上零新失败（R1/F6）
uv run --project backend ruff check modeling_team
→ Found 10 errors                                        # 全部为既有基线，非本次引入（见下）
uv run --project backend python -m modeling_team validate --profile …002… --task …008b-smoke.yaml
→ roster [coordinator, modeling, protocol] OK
uv run --project backend python -m modeling_team validate --profile …002… --task …008b-real.yaml
→ roster OK                                              # R3
cd backend && uv run pytest -q
→ 957 passed, 36 skipped（与基线一致，R2/F6）
聚焦复跑（两轮，结果一致，F3）：test_r30008b_{staged_decisions,runner_wiring}.py → 53 passed
```

ruff 基线核实：F821 `RuntimeDispatchReceipt` 在 HEAD 版 `runner.py:4833` 已存在（本次仅行号
偏移、diff 中零出现）；其余 9 个 F401/F841 全部位于本次未改动的
`test_r23008_*/test_r23009_*` 文件。10 个错误均非本次变更引入（F6 不触发）。

**L1 健康与基线**：service active（6h）；`/api/health` 200；`/` 5173 200；
`alembic current` = `0032_semantic_protection_sets (head)`（零 migration）；
`SAFE_PROTOCOL_TOOLS` 在 diff 中零出现（字节不变）；F4 grep 门：新增产品代码、prompt 增量、
references 合同与两个任务条目中 `缺料`/`PartShortage`/裸 `PS` 零命中（fixture 命名空间为
`example.test`/`placeholder-*`）；smoke 与 real 任务 `protocol_tools` 均无直连
`submit_modeling_batch`（F2）。

**S/B/F/R 覆盖与独立补证**：开发者新增 53 个用例经复核为真实覆盖（非空转断言：逐 reason
code 断言、intent→receipt 顺序断言、bind 唯一写者负向断言、manifest 排除断言）。六个
reason code 未被用例显式断言（`stage3_unparsable`/`stage3_missing_approval`/
`stage3_candidate_artifact_unavailable`/`conclusions_schema_mismatch`/`unlock_unparsable`/
`unlock_schema_mismatch`），本轮以独立探针逐一直证拒绝行为正确（6/6 PASS）——记 Low 缺陷
D-1（测试覆盖缺口，非功能缺陷）。B6 unknown 裁决三分支、B7 对账双向、S4 intent 先于转发、
S9 非 staged bind 逐字节一致均有用例且复跑通过。

**L2（BLOCKED）**：启动命令
`PYTHONPATH=backend:. uv run --project backend python -m modeling_team run --profile
r3-0-002-modeling-team.yaml --task r3-0-008b-staged-decisions-smoke.yaml --run-id
r30008b-l2-smoke-r1 --scope <mode:create> --freeze-started-at <ISO>`。prepare 期 staged 九目录
注册证据落 `evidence/staged-decisions.jsonl`（`directories-registered`），scope Project/keys
建立；coordinator/modeling 线程与 team_transport MCP ready 后首个回合即失败：
`run failed: app-server closed its output`。独立可用性探针
`codex exec --skip-git-repo-check --sandbox read-only` →
`unexpected status 404 Not Found: https://chatgpt.com/backend-api/codex/responses`
（重连 5 次后放弃）——模型 API 对当前账号不可用，属 §8 判 BLOCKED 的外部条件。失败 run 的
cleanup 完整（state=CLEANED、owned project 已删、residual counts 全 0），平台账面前后一致
（build_sessions=0、modeling_batches=0、projects/ontologies 回到基线 1/1，F5 通过）。按 §9
删除该 run workspace 与临时 scope/probe 文件；脱敏证据留存于
`docs/delivery/evidence/2026-09-03-r3-0-008b/`（l2-runner-output.log、
l2-staged-decisions-events.jsonl、l2-app-server-events.jsonl、l2-run-state-summary.json、
l2-freeze-started-at.txt）。**未以单测模拟冒充 L2**；L2 待模型 API 恢复后由主代理裁决重试
（冻结的 smoke 任务与命令形态可直接复用）。

**缺陷与登记**：

- D-1（Low，测试覆盖缺口）：六个 reason code 无显式用例（见上，本轮探针已直证行为正确）。
  建议补用例后并入开发者轮记录。
- D-2（Low，健壮性）：monitor tick 路径 `_check_staged_decision_gates()` 对损坏
  （unparsable）的 intent/receipt JSON 文件会抛 `StagedDecisionArtifactError` 而非走类型化
  kill-switch，异常可穿透 `__main__` 前台循环使整个 run 崩溃（capability handler 路径已正确
  处理，test_b5 覆盖）。触发面窄（该两目录 Runner-host 独占、写入为原子替换，仅磁盘损坏或
  人为改写可触发），方向为 fail-closed 崩溃而非放行，不属 §10 FAIL 条款；建议第二段前把
  monitor 路径的该异常收敛为 `staged_unreconciled_batch` kill-switch。
- 登记确认（非缺陷）：生产 CLI 装配未绑定真实 host 写转发器（`staged_batch_forwarder=None`
  → `staged_batch_forward_failed` fail-closed），与设计状态区「写路径转发 model key 维持
  假设 2 待第二段实测」及 §3.11/§7 一致；第二段真实物化运行前必须补该接线。
- 流程观察：开发者自测轮未在本计划轮次记录区留痕（标题仍为「待执行」）；其离线自测结论仅
  存于代码与用例，建议开发者补记。

**结论**：除 L2（BLOCKED，外部条件）外全部通过。按 §10，PASS 需 L1–L3 全过，故本轮总体
判 **BLOCKED**；机械增量本身未发现任何门放行、守恒、确定性、边界或回归破坏。待模型 API
恢复后补做 L2 即可收口第一段（或由主代理裁决降级路径）。

### 独立测试 Round 2（2026-09-03，`requirement_tester`）

**工作区状态**：与 Round 1 同一稳定 worktree（main @ b308451 + 附录 A 未提交变更），叠加开发者
Round 1 缺陷的三项窄修复增量（未 commit）：D-1 新增 3 个 reason-code 用例、D-2
`_check_staged_decision_gates()` 步骤 1 异常收敛、D-3 开发者自测轮补记。本轮为修复复测轮，
复用 Round 1 记录中的基线与证据，未重复全量实现走查。

**D-3 核验（只追加）**：开发者自测轮记录位于第 276 行，Round 1 记录（第 317 行）原文完整未改写，
顺序为 计划占位区 → 开发者自测轮 → Round 1 → 本轮，符合只追加约束。

**修复项复测**：

- **D-1 → FIXED**。审阅 3 个新用例均真实非空洞：`test_d1_stage3_slot_failure_reason_codes_are_typed`
  （期望列表 `["stage3_unparsable","stage3_missing_approval","stage3_candidate_artifact_unavailable"]`
  为独立写死，逐一断言 `issue.reason_code` 属于该集合）、
  `test_d1_conclusions_schema_mismatch_is_typed`（构造缺 `schema_version` 的结论，独立断言
  `conclusions_schema_mismatch`）、`test_d1_unlock_failure_reason_codes_are_typed`（两组独立写死：
  `unlock_unparsable`、`unlock_schema_mismatch`）。至此 Round 1 缺失的六个 reason code 全部有
  显式断言（另一组三个由既有 test_b5 系列覆盖）。与 Round 1 独立探针结论一致。
- **D-2 → FIXED**。代码走查：`runner.py` `_check_staged_decision_gates()` 步骤 1 现将
  `staged_intent_receipt_issues(run_root)` 包入 try/except `StagedDecisionArtifactError`，
  收敛为 `staged_unreconciled_batch` kill-switch 并 `return False`，异常不再穿透前台循环。
  新回归用例 `test_d2_corrupt_intent_json_converges_to_typed_kill_switch_not_crash` 真实
  （corrupt intent-1.json → tick 返回 False、`_staged_gate_killed` 为真、reason_code 为
  `staged_unreconciled_batch`、feedback 已送达、第二次 tick 稳定、forwarder 未被触碰）。
  独立补充探针（第二潜在路径）：corrupt receipt 文件 + `platform_batches_ledger.json` 同时存在
  时 tick 仍返回 False 且 killed=True 不抛异常——因步骤 1 先于 ledger 分支读取 receipts，异常
  路径已封死。
- **D-3 → 通过**。见上。

**§2 稳定命令全套**：

- modeling_team 全量：`env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python
  -m pytest modeling_team/tests -q` → **1181 passed, 1 skipped, 318 subtests passed in 45.28s**
  （与预期一致；Round 1 为 1177 passed）。
- 聚焦双文件复跑：同环境 `pytest modeling_team/tests/test_r30008b_staged_decisions.py
  modeling_team/tests/test_r30008b_runner_wiring.py -q` → **57 passed**。
- ruff：`uv run --project backend ruff check modeling_team` → 10 errors，与 Round 1 基线完全
  相同的四个既有文件（runner.py 的 F821 `RuntimeDispatchReceipt` 等，b308451 即存在），
  **无新增错误**。
- 两个 validate CLI：smoke 任务与 real 任务均 `SMOKE_OK` / `REAL_OK`。
- backend 确认性全量：957 passed, 36 skipped in 48.38s，与基线一致。

**L2 重试（单独判定：BLOCKED 维持）**：先以
`codex exec --skip-git-repo-check --sandbox read-only` 简单探针测试模型 API，仍返回
`unexpected status 404 Not Found: url: https://chatgpt.com/backend-api/codex/responses`（重连
5 次后失败，与 Round 1 相同）。按主代理指示「仍 404 则维持 BLOCKED 登记（不需要以其他方式
补偿）」，未启动真实 Runner run，未以单测模拟冒充。模型 API 恢复后可直接复用 Round 1 记录中
冻结的命令形态与 smoke 任务重试。

**F4 范围审计复查**：`git status` 变更仍仅限附录 A 文件 + 本轮修复涉及的 4 个文件
（runner.py、test_r30008b_staged_decisions.py、test_r30008b_runner_wiring.py、本测试计划）
+ 用户既有改动（AGENTS.md、CLAUDE.md、.codex/agents/、两份 delivery 文档）；
`git diff --stat` 确认 backend/ 与 frontend/ 零 diff；本轮 diff 中 `SAFE_PROTOCOL_TOOLS`
零出现、无参考领域字符串进入产品代码。F5 复查：build_sessions=0、modeling_batches=0、
projects/ontologies 维持基线 1/1，无 r30008b workspace 残留。

**S/B/F/R 快速回归**：S1–S10、B1–B12、F1–F6、R1–R3 由全量 1181 passed 覆盖（含 Round 1
独立探针结论与 B12 独立写死字段集，本轮未改相关断言）；受 D-2 修复影响面仅 monitor tick
异常路径，其回归由新增 D-2 用例与聚焦复跑覆盖。无 STILL FAILING、无 REGRESSION。

**结论**：三项窄修复全部 FIXED/通过，§2 稳定命令全绿，F4/F5 干净，S/B/F/R 无回归。L2 仍因
模型 API 404（外部条件）BLOCKED。按 §10 总体判 **BLOCKED（仅 L2）**；机械增量本身（门语义、
守恒、确定性、边界、回归）全部通过。第一段收口仍差 L2 一次真实 Runner 机械 smoke，待模型
API 恢复后补做即可，无需对产品代码再作修复。

### 收口裁决（2026-09-03，主代理）

用户裁决：**跳过 L2 真实 Runner 机械 smoke**，完成第一段收口。裁决依据与登记：

- L2 两次尝试均因 codex 模型 API 外部 404（`chatgpt.com/backend-api/codex/responses`，
  重连 5 次失败）无法启动真实 Runner run；主代理另行两次独立探针确认同一根因。
- 本段机械面已由 1181 项确定性单测 + 两轮独立机械验收（Round 1 全量、Round 2 修复复测
  全绿）覆盖；L2 不可用期间不以单测模拟冒充（计划 §8 规则未被违反——L2 保持未执行，
  非被模拟）。
- 本计划最终判定登记为：**第一段机械验收通过（L2 未执行，用户裁决跳过）**。该判定不得
  解读为 L2 PASS；若后续需要 L2 证据（例如第二段真实运行前复核），模型 API 恢复后按
  Round 1 记录中冻结的命令形态与 `r3-0-008b-staged-decisions-smoke.yaml` 补做。
- 第二段（真实建模运行联合验收）待 R3.0-009 机械增量完成并由用户授权 R3.0-006
  modeling start 后执行；两段证据不互替。
