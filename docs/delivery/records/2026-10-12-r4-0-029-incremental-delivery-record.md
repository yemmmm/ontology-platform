# R4.0-029 增量建模实现与验证

- 权威范围：[R4.0-029](../../requirements/requirements-v4.0.md#r40-029-基于已有模型的增量建模)。
- 复用[既有设计](../designs/2026-10-12-r4-0-029-incremental-modeling-design.md)，D1—D8 无新业务取舍。
- 用户授权：根据设计完成 v4-029 并通过测试；实现基线 `40843fc`，开始时工作树干净。
- 通用工程实现及 A1—A10 受控独立功能 PASS；A11 未授权／未执行，整体 PARTIAL。
- 未启动生产 Team、未追加 semantic start；没有模型质量、真实增量或语义检索 PASS 结论。

## 实现

1. 内部 `incremental start --request` 生成不可变请求／获准正文／正常 v4 Task／scope／Delivery
   配置，复用已有 Delivery 监督链。明确当前 Project／Ontology IDs、目标、资料有效时点、
   Profile／model profile、授权引用／期限／额度及本轮验收范围。重复 UUID 核对原回执，
   未知启动不二次启动；已启动请求到期后仍可只读核对，不能启动未启动的 prepared 请求。
2. existing 单／多本体按实际 ID 检查归属、修订和 writer／Attempt 状态；原单 ID 入口保持。
   拓扑明确 existing ID 或获准新建 name，不按名称复用，不假定首本体预建。创建回执
   归本轮并持久保留，未知创建禁止重放。完整原获准范围保留；映射按拓扑条目顺序绑定，
   不因原范围／计划顺序不同误配依赖，也不缩小 Protocol 交接范围。
3. unified 现有 identity binding／审批／计划复用。空写计划仅用于有当前候选审批及当前
   受治理读取的复用；核对真实观测 read artifact、IRI、当前修订及候选内容 digest，
   支持原生 MCP envelope。`protocol_check_plan_coverage` 把 reuse 与 actual apply 分账，
   新项仍须明确计划或业务 disposition，记录 `evidence/plan-coverage.jsonl`。空计划不发
   Batch，不伪造 update／dry-run／apply，也不能掩盖未知写入。已有身份禁止 create，
   update／delete 目标必须一致。普通写计划仍沿原批准、翻译、dry-run、apply 原子／版本合同。
4. Delivery 固定原请求／run、截止时间和生产额度；恢复不能提高授权。新入口不给修复或
   部署权限，待命咨询和原目标检查点恢复维持原语义。existing Batch 禁越出本轮绑定 ID。
   失败保留旧模型和新增资源；只清理本轮实际创建且可证明所有权的 Session／Lease／Key。
5. 公开反馈保持观察性质，通过内部公开投影读取器与统一入口接线。当前 001 生产存储
   尚未实现，CLI 非空 feedback_ids 准确返回 `incremental_feedback_unavailable`；可用获准
   公开原文作为资料执行通用改进目标，不注入隐藏答案或 Judge 私有理由。此处没有实现
   001 采集服务，也不把反馈期望自动写成业务事实。
6. 当前 Task、unified／scenario-map 合同、Protocol 指令和宿主 runbook 同步。新 CQ 范围、
   旧题集／报告隔离、共享修改前引用检查、生产关联自查与独立只读验收沿已有方法；
   不新增 diff 引擎、反馈 Runner、平台业务推理或角色数量硬门。

## 验证

- 开发聚焦回归：58 passed、5 subtests passed；新增纯复用／漂移／审批／无写入测试通过。
- 完整 Team 回归：2723 passed、11 skipped、316 subtests passed（238.18 秒）；
  `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`。
  日志：`workspaces/r4029-team-regression.log`。
- 全量后最后拓扑及输入边界改动定向复验：211 passed、5 subtests passed（48.70 秒），
  覆盖 scenario-map、Runner、staged／unified、Protocol、Delivery、scope 及新增029用例。
  日志：`workspaces/r4029-final-regression.log`。
- 独立功能测试最终 43 passed；必要相邻独立回归 89 passed、5 subtests passed，
  最后真实 gate 接线与新增独立用例合计 60 passed。后端权限夹具独立复验 4 passed。
  初轮真实 Task loader 拒绝获准快照（D029-1 High）已窄修并复验；历史失败保留在
  [独立记录](../tests/2026-10-12-r4-0-029-incremental-acceptance.md)。
- 额外完整后端首轮：26 failed、1026 passed、56 skipped（381.75 秒）。一项本次影响为
  Team identity 测试桩遗漏新 existing 入口必需修订，已补修订／ID，保持无 membership
  不能发 Key 的原断言。其余25项实际请求本机 `.env` 开启的实网 Jev 重排服务，导致
  原排序／分页／游标断言变化；未修改检索实现或运行配置。测试进程显式关闭实网 Jev
  后全量复验 1052 passed、56 skipped（274.72 秒），Jev 专门测试仍按其显式启用／mock
  配置执行。命令：`cd backend && env -u DEEPSEEK_API_KEY SEMANTIC_JEV_ENABLED=false
  PYTHONPATH=.. uv run pytest -q`；日志：`workspaces/r4029-backend-final-regression.log`。
- 最后恢复边界补验：87 passed、5 subtests passed（2.47 秒），日志
  `workspaces/r4029-final-boundaries.log`。新增 gate retry 开发用例首跑仅测试假 scope teardown
  未恢复导致 ERROR，修正 fixture 归属后通过；产品无对应 cleanup 缺陷。
- 新增代码／测试 Ruff、JSON／YAML 解析及 git diff --check 通过。217 个文档链接中，
  本次新增／修改链接均有效；3 个历史已退役前端页面链接在原 HEAD 同样失效，未扩大029
  范围修改它们。Runner 的4项既有 Ruff 未使用变量／import告警不属本次新增行，未顺带重构。
- T0 复核发现原 topology-open latch 在 existing 应用失败后禁止下一tick重新检查；
  保留防御的理由是实际拓扑/资源绑定完整性，但拒绝不得永久卡死。窄修为重置原 latch
  并沿既有定位反馈允许同run修正；未知创建仍不重放，明确401/403/404/422写前拒绝可重试。
  独立真实 CandidatePlatformGate 接线验证修正后open及unknown仅一次POST，未新增守卫。

## 证据及运行边界

GitNexus impact 对拓扑方法返回 LOW，但未找到当前 coverage handler；detect_changes
为 MEDIUM，定位 scope／bootstrap 调用链，索引未完整覆盖新增文件。以实际调用点、diff
和测试补足，不宣称完整图覆盖。

业务冲突处理、真实新线程／semantic-start、新增业务及停止后反馈改进的真实建模与
受治理检索效果均未验证。受控功能 PASS 不能替代 A11／L1。001 生产反馈读取仍取决于
001 服务；没有新建一套反馈流程。变更为 Team 工具／提示／文档及后端测试桩，不改变
backend／frontend 服务实现或共享运行配置。因包含 backend 测试代码修改，按仓库 Runtime
Restart Rules 在所需测试通过后重启本地用户服务；2026-10-12 重启后 unit active (running)，
`/api/health` 返回 status=ok，前端首页HTTP200。
