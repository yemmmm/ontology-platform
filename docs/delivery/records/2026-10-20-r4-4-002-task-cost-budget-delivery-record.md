# R4.4-002 工程交付与测试记录

- 日期：2026-10-20。
- 授权：用户要求“请实现v4.4-002需求，并通过测试”。本轮包含工程实现、本地工程测试及提交；不增加实际任务金额，不调用收费 Provider，不恢复旧建模任务。
- [权威需求](../../requirements/requirements-v4.4.md#r4-4-002)、[已审阅设计](../designs/2026-10-20-r4-4-002-task-cost-budget-design.md)。
- 状态：初版工程实现／本地测试PASS，Team 全量回归通过；后续价格配置增量按下文单列。未取得真实托管链预算控制或独立业务语义验收证据。

## 实现范围

- Host-only `task-budget create/add/show`，冻结自定义三档价表，任务金额授权及追加／继续；旧 `authorize-budget --additional-starts` 保持原义。
- `task_budget.py` 复用019／034用量核算，按实际覆盖单元估价、替换和去重，保存预算投影、来源进度及控制回执；普通数值变化不唤醒 Delivery。
- Delivery、生产／CQ、公开反馈和独立验收继承原预算。金额模式绕开次数额度，保留基线、授权、源忠实度、应用及写入对账边界。
- 暂停原因与实际暂停证明分开；DSH 控制已绑定原生进程，Codex 逐成员确认；Host 数值监视、查询和已准入工具保持在线。
- `AGENTS.md`、建模宿主 Skill、Delivery 合同及用量说明同步金额模式。预算不产生业务扩权，不能缩小题集或跳过独立验收。
- Decimal 按未舍入金额累计，缺缓存按较高输入价暂估，迟到用量替换暂估；共享活动／代理来源保留行身份，不被最后一个成员的绑定覆盖。
- 每2秒有界观察，单次最多4MiB／4096条，来源轮转；游标与差量事件持久化。事件追加后 state 发布崩溃、半行、坏行及来源积压均有回归，未知费用不补零，安全已知小计不清零。
- 每次可观察上游请求及重试检查预算；本地拒绝记 `not_admitted`，不伪造usage，也不抹掉此前已触达上游的失败请求。有限控制按成员／epoch持久化去重，Responses 只给精确匹配的新 Host 控制输入一次例外。
- Codex native turn／usage 与 DSH 原生数值按实际线程／session／step关联；计量缺数宽限和正常在途分别处理。物理暂停只控制已验证 DSH 原生进程组，Host 监视与已准入收口保持在线。

## 验证记录

验证从 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ...`，不发起真实建模。

| 轮次 | 范围 | 实际结果 |
| --- | --- | --- |
| 开发回归 | Host／Delivery 会话、观察、Host operations、Delivery operations | 275 passed，29.77s |
| 开发回归 | Runner、Host S2、旧验收／次数账本、公开反馈 | 93 passed，52 subtests passed，4.41s |
| 集成回归 | Delivery、观察、Runner、公开反馈 | 204 passed，8 subtests passed，26.72s |
| 工程合同测试 | 预算 CLI 及 Host／Runner／验收 owner 集成；不作为业务语义验收 | 15 passed |
| Team 全量 Round 1 | `../modeling_team/tests -q --disable-warnings --maxfail=8` | 3 failed，3627 passed，12 skipped，318 subtests passed，563.64s |
| 回归修复 | Round 1 两项旧 Codex fixture 兼容失败 | 2 passed，0.21s |
| 核心最终回归 | 数值／身份、native优先范围、不同step、重试拒绝、usage／CLI／集成 | 153 passed |
| 原生接口回归 | 新预算代理、旧 Codex／Lean／Delivery／DSH 运行时 | 129 passed，2 skipped，23 subtests passed，124.17s |
| 交叉工程检查 | CLI、Host／Runner／验收 owner、多成员共享来源及持久控制去重 | 22 passed |
| 集成收口 | 新预算代理／CLI／集成、usage、旧 Lean | 82 passed，23 subtests passed，3.25s |
| Team 全量 Round 2 | 与Round 1相同命令，初版 `728ac57` 冻结源码 | **3677 passed，12 skipped，359 warnings，318 subtests passed，588.57s** |

Round 1 第一阻塞均为工程合同：两个历史 native Agent fixture 未携带新增可选预算字段，分别影响 P2a idle send 与旧 Examiner continuation；一个新预算用例使用了旧的暂停原因断言格式。三项已修复，Round 2无失败。另有裸 Python 运行的开发检查被 `pydantic._internal._signature` 缺失阻断，统一使用上述 backend `uv` 环境后的相关测试通过，不归因模型质量。

静态及文档检查：改动的预算、Host、CLI、proxy、runtime及测试文件 Ruff 通过；`runner.py` 的7项及 `acceptance_runtime.py` 的1项存量 Ruff 发现与HEAD基线一致，本轮未扩大修改。相关 `py_compile`／`compileall`、暂存差异检查、11份文档本地链接检查均通过；修改后的两个 Skill 验证器通过。README 的预算创建／追加示例已在临时目录用真实 `TaskBudget` 验证，无 Provider 请求。

本地用例验证金额公式、源选择、去重、异常恢复、权限隔离、进程控制和消息合同。负责CLI与文档的Agent另对预算核心、Host／Runner整合做了交叉检查；CLI本身仍属开发测试。上述检查不是独立业务语义验收。

## 后续价格配置

- 用户要求：将 `glm-5.3-flash` 与 `deepseek-flash` 均设为缓存输入／未缓存输入／输出
  `0.02 / 1 / 4` 元／百万token。该值是用户指定的估算价，不是供应商报价验证。
- 保存为 [默认价表](../../../modeling_team/task-budget-prices.json)，覆盖两模型各自的
  Responses／Messages 路由。新建预算仅在任务省略价表时，按已明确获准绑定选择并冻结；
  显式价表优先，不增加金额授权，不改历史快照，创建重试不受后续默认改价影响。
- 预算核心／默认价格、CLI、集成、proxy、usage回归：**141 passed，4.50s**；验证四路由
  均按新价格得到样本金额¥0.16，其他模型／路由／币种、显式空价表及原授权边界保持。
- Host／Delivery／托管启动相关回归：**350 passed，42.48s**。该增量两组共491项通过；
  未重跑初版Team全量，运行时控制代码保持。Ruff、编译、JSON与文档链接检查通过。

## 证据边界

- GitNexus 索引落后473个提交；最终暂存 `detect_changes` 返回38文件、51个索引符号、4条旧执行流、medium。该结果仅作辅助，本轮以当前源码调用点、差异及相关回归检查影响，不宣称获得当前图索引的完整覆盖。
- 真实 Provider 的 usage 延迟、全员实际暂停时长、真实尾差、原任务接续及业务成果质量仍需按 A12 另获运行授权验证。本地回放、接口 fixture 和金额公式通过均不能替代该证据。
- 外层 Host 与未接线辅助调用单列范围外未知／已知金额，不从主预算扣除；主预算小计不代表完整任务成本，也不证明 R4.3-030 净降耗。
- 本轮不修改 backend／frontend，不需要重启本地应用服务。工作区原有 README、v4.3、复盘、设计及演示材料改动保留，不纳入本条提交。
