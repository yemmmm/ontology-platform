# v5 最小 HITL 真实运行验证

## 范围与结论

用户于 2026-10-29 要求启动建模任务验证 HITL。基于已提交代码 `ee531a1` 新建一次真实
任务，复用缺少正式名称的公开演示场景，所有托管角色采用
`glm-direct / glm-5.3-flash / low`。沿本次 v5 推进已有 `usage_only` 授权，不建立新金额
预算。归属 [R5.0-001 F9](../../requirements/requirements-v5.0.md#r5-0-001)与
[P1.3](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#p1-3)。

**本次最小 HITL 真实链通过**：Agent 实际读原文后提问，部分答复保持未决，完整答复解决
原问题，新 CLI 进程恢复原 run，忙碌时输入排队并由下一适用回合消费；只有一次实际应用。
独立原生只读评价按公开工程判据 **1/1 PASS**。本轮没有修改运行代码或提示，没有追加
semantic start，也未为取得通过而修模或更改判据。

本场景不是盲测，不是完整业务语义验收或完整 P1.3／v5 验收。输入沿用用户此前
“你直接回答即可”的工程代答授权，作者记录为 `host-on-existing-user-test-delegation`；
正式名称由宿主代答，不称用户亲自给出名称。

## 绑定与原始证据

- Task：`v5-hitl-validation-20261029`；run：`v5-hitl-validation-20261029-start1`。
- 工作单元：`hitl-validation-unit`；semantic-start **1**，初建轮次 **1**。问答接续及
  内部 `round=2` 不另算修模轮次。
- 原运行：`workspaces/v5-runs/hitl-validation-20261029-start1/`。
- 输入、CLI 回执及阶段快照：`workspaces/v5-runs/hitl-validation-20261029-inputs/`。
- 原文：[hitl-source.md](../../../modeling_team/v5/tests/fixtures/hitl-source.md)，SHA256：
  `0f7d29ba2eba55150627e26bb059ab87f26904b7a06abed7b13295c74dd6b7ed`。
- 冻结公开工程判据：`v5-hitl-validation-public-criterion-20261029`，1 题，SHA256：
  `1ba5644eb6ed578c71f30520d0f83d6ba124b7343fd064f9e42ad0f84c0d4cd3`。
- 汇总：原运行中的 `runtime-summary.json`；原生回合、用量和工具事件均保留。
  私有运行连接、密钥及 gitignored 原始产物不提交。

## 实际验证过程

请求 ID 为 `human-request-88ef53c1cf87df40d33b7721`、revision 1。原问题是：
“请提供这个概念定义的正式名称（业务含义为‘本次人工确认的演示业务对象’）。您希望该
概念叫什么名字？” 请求包含原工作单元、model 步骤、来源摘要、基线和执行引用。

| 检查 | 实际行为与证据 | 结果 |
| --- | --- | --- |
| 缺少输入 | `model-00000` 实际读取 `scenario` 后返回问题；start 自然退出于 `waiting_input`；没有应用 | 通过 |
| 部分答复 | `partial-naming-001` 明确名称尚未确认，带 `partial=true`；新 CLI resume 后由 `model-00001` 一次消费；仍等待同一问题，没有重复提问或应用 | 通过 |
| 重复提交 | 部分答复及完整答复各以相同消息 ID、正文、作者及请求版本重提一次；回执完全相同，最终各只有一条队列记录、一次交付与消费 | 通过 |
| 完整答复 | `full-naming-001` 确定名称“人工确认演示对象”；新 CLI resume 后由 `model-00002` 一次消费，Agent 明确解决原请求 | 通过 |
| 忙碌时主动输入 | 两份状态快照均显示 `hitl-validation-unit → model-00002` 在途；期间提交 `busy-supplement-001` 为 queued，没有 steer／interrupt；下一回合 `self-check-00002-000` 一次消费 | 通过 |
| 应用与读回 | 仅 `apply-00002` 一次完成，模型 revision 0→1；自查实际调用受治理查询，最终 `handoff_ready`，无在途执行 | 通过 |
| 独立只读检查 | 独立原生上下文实际成功读取原文、冻结题、目标和人工输入，并查询实际模型；首个报告即 1/1 PASS | 通过 |

部分答复正文仅确认演示用途并要求保持名称未决；主动补充仅重申不创建实例、不推断关系
或约束。所有输入保留代答作者，没有补入行业事实。最终问题状态为 `resolved`；部分和
完整答复分别关联 `model-00001`、`model-00002`，主动补充关联自查回合。独立评价得到
三条带来源与 partial 标记的人工输入，不接收生产候选或生产自查作为模型证据。

只读评价中有一次针对不存在 material ID 的读取失败，随后依据已成功读取的四份材料和
实际模型完成报告；该失败事件保留，没有改写材料或手工修报告。本轮未发现需要修改
HITL 代码／提示的缺陷。

## 资源与清理

项目 `781b60bb-c62e-4593-b651-1acbb1cdb2d6`；Ontology
`bd0244fc-b59e-4952-b399-bad18b73b7dd`；Class
`69452def-1a9e-580c-8c67-69f4d04486cc`。实际应用的 Batch
`8a949554-6e24-44e0-9686-d49783e623d6`、Attempt
`366270a8-e9eb-496b-b39e-9bcbeca983c4` 均为 applied，模型及检索投影 revision 1。

cleanup 确认 session 终态、无在途 Attempt，返回 `written-retained`；同时保留旧兼容层
`legacy_scope_disposition=failed-written-retained`，不将其混作本次任务失败结论。
按原清理回执和读凭据绑定中的四个精确 key ID 只读核实，modeling、acceptance、protocol、
admin 全部撤销。清理后 scope 会清空 admin／protocol ID；最初取空字段的宿主核查误差
记录在 `key-probe-null-fields.json`，改用原回执 ID 后的结果保存在
`owned-key-verification.json`，未创建替代凭据。

## 时间与用量

授权记录为 `06:17:13Z`；首个真实原生回合于 `06:19:18Z` 开始，间隔 **2 分 5 秒**。
从该回合开始到四个凭据全部撤销（`06:28:54.513962Z`）墙钟为 **9 分 36.514 秒**，
包含人工输入等待与宿主核查。五个原生回合耗时累计 **180.016 秒**；11 个完成的上游
请求耗时累计 **138.102 秒**，无未结束请求。这些时间互有覆盖，不能与墙钟相加。
宿主有效准备／核查／文档时间未完整分类计时，保留 unknown。

每个原生 thread 取最后累计用量，重复通知不重复相加，五个执行均有用量：

| 用途 | 原生执行数 | 输入 token | 输出 token | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 建模／问答接续 | 3 | 46577 | 1421 | 47998 |
| 治理自查 | 1 | 21969 | 551 | 22520 |
| 独立公开工程检查 | 1 | 15348 | 713 | 16061 |
| 合计 | **5** | **83894** | **2685** | **86579** |

上述原生量不是完整上游金额结算，金额计量保持 **PARTIAL**。外部 Host 用量 unknown，
单列且不计入任务费用。

## 证据边界与后续

本次覆盖单工作单元、公开命名场景、实际部分／完整答复、消息重提、忙碌时输入、新进程
恢复及一次应用。多单元局部挂起、变化版本下更复杂的业务重审、停止／暂停等反例的
更广泛真实组合未在本轮逐项运行；它们的已有开发测试不冒充本次真实实测。

CLI reply／input 先持久入队；已退出的等待进程仍需显式 resume，没有后台自动唤醒或
新 UI。本轮未增加项目记忆或金额控制等能力。

运行代码、依赖、配置与服务均未修改；复用同一 `ee531a1` 环境下已有 **96 passed、
0 skipped** 的开发测试及 Ruff 结果，详见[交付记录](../records/2026-10-29-v5-minimal-hitl-delivery.md)。
本轮另执行真实 CLI／平台／独立只读链，文档做本地链接、围栏和 diff 检查；未重复运行
backend／frontend 套件或重启服务，也未增加独立工程验收角色。
