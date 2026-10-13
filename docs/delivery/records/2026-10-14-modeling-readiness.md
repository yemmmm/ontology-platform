# 2026-10-14 下一轮小链建模准备

用户授权：完成上一轮复盘后的准备与窄修复，可分工执行。本记录不新增 semantic start
或建模轮次；上一轮三轮额度已用尽。工程验证和真实建模质量分别记录。

## 已选定的下一轮范围

- Task：[资产—故障—工单](../../../modeling_team/tasks/r4-0-009-asset-fault-workorder.yaml)。
  只表达三者的业务含义、已确认关系及必要共享定义，不预设 Ontology 数量。
- 保留完整业务资料作为证据，但不按所有表、列或业务模块扩展范围。
  合同覆盖、SLA、成本利润、备件采购、SQL/API 映射均不在本次小链任务内。
- 新 CQ 池只衡量该链：建议约 4—6 题，包括身份、关系、未知和隐藏覆盖；题数不是硬门。
  CQ 作者依据资料拟题，实际批准池为准。上一轮 30 题分母与未完成结果保持不变。
- 首链公开反馈选择少量已批准公开题；最终独立验收仍须有实际读取、答案与判定。
  第二条链待小链反馈后另行明确范围，不自动纳入。

## 责任与运行参数

| 项目 | 已确定安排 |
|---|---|
| 业务事实 | `business_input_role: user`；已批准来源之外的业务含义向用户确认，未知如实保留。测试代答须有单独明确授权 |
| CQ 审核 | 当前用户保留审批；若下一轮委托 Delivery，先记录明确授权及题目版本。审核不能查看隐藏答案或给生产角色隐藏题 |
| 建模及验收模型 | 复用 `glm-flash-high.yaml`，全部八角色 GLM 5.3 Flash/high；修复执行器沿用 Codex/gpt-6.1-sol/high |
| Profile / Scope | 复用 `r3-0-011-competency-question.yaml` 与 `new-scope-create.yaml` |
| 首链交接 | Coordinator 发布状态及公开交接引用；Delivery 主动观察并调用既有 `public-feedback`。不添加 TeamTransport 边 |
| 验收超时 | 每次 `start_evaluation` 显式传 `session_timeout: 900`（本次小链建议值）；这是整个 child session 时限，不是空闲超时。超时保留 PARTIAL，依据进展再处理 |
| 验收凭据 | 启动时为实际项目绑定只读 key，通过进程环境 `R3011_ACCEPTANCE_PLATFORM_READ_KEY` 传入。不得写入 YAML、日志或提示；完成后撤销。现在项目尚未创建，不提前伪造 key |
| 版本 | 启动时冻结实际 commit、Task/Profile/model-profile、角色提示、检索实现和工具合同摘要；本次工程记录不冒充未来 baseline |

已提供[准备配置](../configs/2026-10-14-asset-fault-workorder.yaml)，仅允许 read/supervise，
未启动 Delivery 或模型。启动时必须创建新的 session/run ID 和本次授权记录；不得复制旧的
`authorization_reference`、轮次计数、freeze_id、项目凭据或过期截止时间。获新建模授权后
才按实际授权开放 production/evaluation。无需新增配置框架。

## 必要修复与检查

1. 历史 applied 计划由绑定 intent/receipt/Attempt 证明，不因后续版本增长重验旧 reuse；
   待执行计划仍须核对当前候选批准、身份与版本。同 run 已应用 Attempt item 可作为身份来源。
2. guidance/abort 携带 repair-only 字段时在 Host 返回可修正错误；工具说明一致。
3. Delivery 能在自身 evaluation status 取得受限、脱敏错误尾部，仍不可任意读取宿主文件。
4. 派单带准确 Task ID，Protocol 按 BuildSession → checkpoint → lease 顺序建立上下文。
5. checkpoint capture 复用已修复的 run-owned credential 路径；不改回已撤销 launcher key。
6. 下次启动使用新进程加载当前 MCP 工具；HTTP 服务健康不能证明旧 MCP 子进程已更新。

首次真实开始前只做授权、必要凭据、配置和加载版本检查，沿用 20 分钟启动上限。
恢复演练不作为每轮前置条件；若真实遇到恢复，才核对对应 checkpoint、候选、计划与写入状态。
重复失败按第一阻塞层定位，不靠扩大建模范围或未经授权 fresh start 处理。

## 验证与完成边界

全 Team 回归：2820 passed、11 skipped、318 subtests passed。独立工程验收 PASS，
无未解决 Critical／High；相关合同、技能、JSON/YAML 及链接检查通过。
没有 backend/frontend 变更，不触发服务重启；下一轮使用新进程加载。GitNexus 未识别
Python 改动目标，采用调用点与测试验证，不宣称图谱影响覆盖。

工程和独立测试结果记录在[测试记录](../tests/2026-10-14-modeling-readiness-test.md)。
当前没有新增真实建模、首链公开反馈或最终语义验收证据；相关优化仍为待实测。
首链是否更快得到质量反馈、历史复用开销是否降低，必须由下一轮实际证据判断。
