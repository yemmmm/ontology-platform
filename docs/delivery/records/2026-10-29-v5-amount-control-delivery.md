# v5 金额控制最小接线交付

日期：2026-10-29。基线 `e5a6756`。用户要求按既定能力计划继续；本批承接
[R5.0-001 F4／F7](../../requirements/requirements-v5.0.md#r5-0-001)及 R5.0-007 F5。
来源、选择与验证范围见[接入核对](../../research/2026-10-29-v5-amount-control-integration.md)。

## 实现与边界

- 任务支持 `authorization.mode: amount`，必须绑定稳定 `budget_ref`；路径在准备时固定。
  复用现有 Host TaskBudget 的授权、价表、追加、累计去重和尾差投影，没有第二份总账。
- Codex 原生累计通知作为数字来源，保留线程、turn、原执行与原始文件；每个 v5 执行
  实际新建线程，累计段绑定实际事件引用与零基线。传输尝试与原生来源关联同一捕获身份，
  按来源各自语义读取，不对传输源套用累计观察窗口。
- 新原生执行前核对既有金额、模型价表／操作准入；原生终态和原结果先持久保存，再刷新
  金额及 TaskControl。暂停后可读取／对账已有结果；下一新回合或平台活动等待预算恢复。
  不在已开始回合的 HTTP 请求或工具后续插入金额拒绝，不调用原生 interrupt。
- CLI 增加 `budget`／`budget-add --authorization-file`，status 返回预算投影；按需读取
  时刷新，无新常驻服务。创建和追加仍是 Host 真实授权动作，不给 Agent 额度写工具。
  追加不取消用户暂停；相同追加身份重试不重复加款；相同预算跨 run／角色累计。
- `usage_only` 保留本轮研发授权，不要求金额账本；次数模式和旧入口默认切换未纳入。
  没有新表／迁移、后台／UI 或财务框架，也未修改账本核心。

## 真实任务与故障接续

任务／run 为 `v5-amount-20261029`／`v5-amount-20261029-start1`。
全部托管角色使用 `glm-direct / glm-5.3-flash / low`，复用公开“演示设备”单概念 fixture，
原文 SHA256 `99de578cdbdca5e276ded24231cc27f38cb18c197fd104499f3701e51e87a328`。
题集 `v5-team-public-criterion-20261029`，SHA256
`efdddd6de59435f11f5d1f36a4adc35679f020c688d311f18801948cad2fe82e`，生产前已冻结。
本批不增加业务对象、实例或额外业务事实，也不是新的盲测。

本轮研发仍沿用户既有不限消耗授权。Host 初始 0.001 元和追加 1 元均为触发控制路径
的工程测试阈值，不宣称用户新增了一个任务消费上限。原授权、追加及价表快照均保留。

| 验证点 | 实际证据 |
| --- | --- |
| 忙碌时耗尽 | 首个 model-00000 仍 active，预算已关闭，TaskControl 为 waiting_for_turn_end；原回合的后续请求继续到 completed |
| 尾差 | 首回合最终估算 0.01266368 元；相对 0.001 元阈值尾差 0.01166368 元，未伪装为零尾差或已知上界 |
| 无追加恢复 | 新 CLI resume 后仍 paused，执行目录仍只有 model-00000，没有新上游调用 |
| 独立用户暂停 | 显式 pause 后追加额度，budget_open=true 但 mode=paused，仍需明确 resume |
| 原 run 接续 | 追加 1 元后余额恢复；新 CLI 沿原 checkpoint 完成 peer、建模、自查，没有重放 model-00000 |
| 追加幂等 | 再提交同一追加文件，授权总额仍 1.001 元 |
| 写入与读取 | 只有 apply-00002 一次实际应用，模型 revision 1；真实治理自查完成 |
| 独立公开工程检查 | amount-check-001，1/1 PASS；评价使用独立只读上下文，费用计入原预算 |

首轮接线遗漏 provider 捕获会话归属，造成 metering_error；随后发现 transport 来源
不应继承累计窗口。按 T0 保留原始记录，只修来源关联和窗口接线，没有放宽授权、
制造用量、编辑原回执、换预算清零或另开 semantic start。新正确来源与已有尝试按
原请求身份去重。Host 在真实修复、计量恢复后，通过已有授权追加路径清除相应暂停原因；
不是忽略一个尚未恢复的计量错误。

首个 Agent 的 waiting_peer 回执带空 issues，曾收到既有 unresolved_reason_required
反馈；Agent 在同一任务内继续处理。后续另有一轮普通 peer 交流与再读，不隐去额外
调用，也不把它算作新实质修模。收口按 T0 删除“正常等待 peer 也必须报告问题”的限制：
依赖已在实际请求中表达，不能要求 Agent 编造问题；其他错误状态仍须给出原因。
同步收窄权威提示并补回归，不改原始回执、不另开真实冷启动，也不扩展协作流程。

## 工程检查

新增金额检查覆盖累计去重／跨进程读取、忙碌时等待原回合结束、预算关闭时禁止新执行、
原结果复用、追加幂等、保留用户暂停、任务与预算绑定、usage_only、不带价表禁止调用、
跨 run／生产和评价累计，以及后续传输尝试继续被纳入。

最终金额检查 **8 passed，5.68 秒**。最终金额接线后完整 v5 回归 **126 passed，
1 条既有第三方 warning，101.20 秒**，日志为
`workspaces/v5-runs/amount-20261029-full-tests-final.log`；随后仅调整正常 peer 等待的校验与
提示，另跑对应合同／流程／通信回归。Ruff check／format 与
文档本地链接／diff 检查在提交前核对。
最后这组回归 **31 passed，1 条既有 warning，42.35 秒**；原 model-00000 回执原样
重解析为 waiting_peer，不再要求编造问题，没有新调用。5 份相关 Markdown 的 62 个本地
链接及代码围栏检查通过，最终 Ruff check／format、暂存 diff 检查通过。

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
```

未修改 backend／frontend、依赖或共享服务配置，不需要重启应用服务。
GitNexus 对 v5 与金额目标未找到已索引符号，本批采用当前调用点、diff、回归与实际运行；
不宣称图覆盖完整。没有额外独立工程测试角色；独立原生上下文只覆盖上述公开业务小检查。
提交前 staged detect_changes 为 15 个文件、0 个已索引符号／流程、low；该结果受上述
索引缺口限制，不作为运行代码无影响的证明。

## 用量、资源及证据

共 1 semantic start、1 初建轮次；7 次原生执行包括 3 次建模、2 次 peer、1 次自查、
1 次独立评价。33 个真实上游请求身份全部出现在账本，无遗漏；重复来源不增加金额。

输入 222524 token（其中缓存输入 152640）、输出 6051，合计 **228575 token**。
按冻结用户价表 `user-20261020`，逐执行重算合计与账本均为 **0.09714080 元**：
生产 0.08666696 元，独立评价 0.01047384 元；授权 1.001 元，余额 0.90385920 元。
该价表是用户配置，不宣称当前市场价格。原生来源覆盖 7/7，pending／inflight 为 0，
不等于提供商逐请求账单最终结算；后者仍 PARTIAL。外部 Host 用量 unknown，单列且不扣任务金额。

首个上游请求 `11:47:43.331227Z`，最后请求结束 `11:57:04.743209Z`，墙钟
9 分 21.412 秒；四个本轮凭据全部撤销至 `11:58:18.161446Z`，共 10 分 34.830 秒。
该窗口包含工程修复及暂停，不是纯语义建模时间；Host 有效开发分类计时 unknown。

Project `a5e389c4-7947-445e-af8c-89fc0900d8b3`，Ontology
`ca5ed3f6-a94c-447a-8d99-7bf7a0ced1f8`。cleanup 为 written-retained，原模型、
记忆、两份命名快照和事件保留；四个精确凭据 ID 经后端只读核实均已撤销，最终无在途活动。

运行目录 `workspaces/v5-runs/amount-20261029-start1/`；输入与宿主操作在对应
`amount-20261029-inputs/`，稳定账本在 `amount-20261029-budget/`。
`runtime-summary.json` 保留逐执行 token、金额复算、33 请求对账、时点与清理结果；
原始私有材料、连接、凭据和账本不提交仓库。当前完成的是新栈金额控制子集，
不关闭完整计量、P1.5／P4 或完整业务语义验收。
