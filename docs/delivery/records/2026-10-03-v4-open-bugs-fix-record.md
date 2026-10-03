# v4 待解决问题修复记录

日期：2026-10-03。范围来自[待解决清单](../open-bugs.md)，用户授权调用子 Agent
修复清单上的具体缺陷。主 Agent 负责汇总、检查和提交；子 Agent 分别负责提示合同、恢复
完成 helper、业务消费定位与修复。公开回归由独立 Agent 核对。

## 范围与保留边界

- 按当前 R4.0-007／009 和恢复／交接合同修复，不将 R4.0-013／014／015 整体视为已交付。
- 原运行、冻结输入、旧失败和旧 CQ 裁决保持保留。已暴露问题只作为公开回归，不恢复盲测属性。
- 本轮不以 Task 选择或合同挂载授予未来映射工作、外部数据库／API／脚本执行权限。
- 提示装载、确定性测试、Consumer 响应回放和真实平台 E2E 的证据分别记录。

## BUG-V4-001：Task 与当前范围一致

活动 009 Task 已挂载 R4.0-010／011 映射合同，但仍将自己描述为 `core-stage`、
`mapping acceptance deferred`。改为覆盖当前 run 明确获准的核心与映射范围，未获准、
不可用或未验证工作仍保留缺口。选择该 Task 本身不扩大授权。

修改[活动 Task](../../../modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml)，
沿用现有角色、输入和运行参数，不修改旧运行冻结副本。既有 Protocol 八类查询类型说明
和已修复编写合同不重复开发；本轮仅关闭剩余 Task 说明项。

## OPS-V4-005：宿主显式提交 CQ 交接

[宿主 Skill](../../../skills/modeling-dev-loop/SKILL.md)及
[运行参考](../../../skills/modeling-dev-loop/references/team-runbook.md)已补齐：
角色终态与写入排空核对、当前冻结绑定、`complete_cq_handoff`、
`acceptance_phase=acceptance_pending`／attempt／报告目录核对、独立验收和
`complete_cq_acceptance` 收口。交接成功与语义 PASS 分开记录，不新增调度机制。

## BUG-V4-004：恢复 run 验收完成绑定

[host_ops.py](../../../modeling_team/host_ops.py) 的 `_cq_completion_binding` 沿用原始本地
事件路径；本地缺少冻结事件时，读取当前已发布 handoff，并用既有 `reload_frozen_pool`
校验实际保留的冻结快照及绑定。历史 handoff 先选择最新匹配 attempt，历史冻结快照
不妨碍当前匹配快照。缺少真实冻结、绑定不一致及无可用报告仍按原类型化合同拒绝。

仅影响 `complete_cq_acceptance` 及其 Host MCP 调用，不改变 Runner 冻结、handoff、报告
摘要重算或 FIFO 合同。最终是否接受结果仍由 Runner 复核，不重新冻结、不伪造事件。

## ISSUE-V4-002／003：Consumer 解释实际响应

子 Agent 核对获准公开补充资料及原始平台响应，确认返回内容包含业务／流程维护责任及
关闭请求结果含义，但所选 G-04 响应没有技术映射维护责任人。作答合同修复位于
[活动 Platform Examiner 作答合同](../../../modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md)：
明确直接结论、对象／字段／版本，区分 API 响应、请求／动作结果与业务对象状态，分别
说明有依据的业务／流程维护、技术映射维护和平台授权边界，并保留未知和引用覆盖限制。
合同不包含本场景角色、状态判据或隐藏参考答案。

公开 Consumer 回放通过既有 `run_v3_acceptance_child`、只读 proxy 和报告 sink 执行，
只给开放题干与原始平台响应；不向 Consumer 提供业务补充、隐藏参考答案或原 Judge 裁决。
独立核对见[公开回归记录](../tests/2026-10-03-v4-open-bugs-public-regression.md)。
响应回放用于验证实际内容的消费，不替代当前平台检索、完整关系可发现性或整体 L1 验收。
G-04 公开回放输出 `unanswered` 并明确保留技术维护责任未知，该轮独立结论保留 `PARTIAL`。
随后通过正常受治理语义入口取得 11 条 receipt-backed 读取，模型返回技术映射维护定义，
Consumer 正确区分两类维护责任、已知引用重审及权限边界。独立验收已按 ISSUE-V4-002
有界关闭依据判为 PASS；本次使用 Project-scoped `[read]` 临时 key，撤销回读与旧 key
访问 `401` 均已核对，不据此推导普通主体或数据库行列权限通过。M-03 新回答已明确区分受理、
请求结果与工单状态，独立验收已按 ISSUE-V4-003 有界关闭依据判为 PASS；精确接口路径、
工单字段和真实执行状态未返回，仍保留未知，不宣称整体 L1 或在线执行通过。

## 验证记录

提示／Task 子 Agent 定向检查：

- `test_r4009_acceptance_contract.py`：46 passed。
- Skill quick validator、YAML 解析、相关 Markdown 链接／锚点检查、Ruff 和 diff check 通过。

恢复 helper 已对实际保留的 `r4009-20261003-solmedium-auth01-start4c` 做只读取证：当前
确实没有本地 `evidence/cq-freeze.jsonl`，可以解析已发布 handoff 及合法冻结快照，得到
`cq-batch-0001`／`attempt-0001` 和原报告目录。原报告字节摘要仍为
`sha256:c74a82d54dbfdc26de428a97510de37d2ada913b4189ff85fcd603a4001c1491`，
纯函数重算仍为 `partial`。本次没有向已终态 run 重发 FIFO，没有改写原报告或裁决。

helper 定向测试 6 passed；随后补充的恢复快照缺失／摘要破坏两分支 2 passed，均证明拒绝
发生在 FIFO／宿主请求写入之前。已有 Runner 测试覆盖报告缺失、伪造摘要／裁决和报告绑定
漂移。Ruff 与 diff check 通过。

主 Agent 运行 `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`：
初轮 2179 passed，1 skipped，165.35 秒，日志 `/tmp/v4-open-bugs-team-regression-20261003.log`。
上述新增两条快照失败测试在全量收集后加入，另做定向验证。之后只修正恢复快照缺失时的
操作反馈：有已发布 handoff 时提示恢复／校验原不可变快照，明确不重新冻结或伪造事件；
原始未冻路径仍提示正常冻结。当前 Host 分支 8 passed，Host MCP／Runner 摘要和漂移
边界另测 3 passed。最终代码全量回归为 **2181 passed，1 skipped，176.87 秒**，
日志 `/tmp/v4-open-bugs-team-regression-closeout-20261003.log`。

中间全量回归曾为 2180 passed、1 skipped、1 failed：TG41 的全局
`/tmp/r3011-acceptance-*` 清理断言与并行真实 Consumer 的仍在使用目录冲突，其自身
socket／业务断言通过。真实 child 终止并完成清理后，同一 TG41 用例独立运行 1 passed，
随后上面的最终全量通过；未为此改动产品或测试断言。失败日志保留于
`/tmp/v4-open-bugs-team-regression-final-20261003.log`。

GitNexus `detect_changes(scope=all)` 返回 LOW，但索引落后 112 commits，未映射本次 helper
符号；不据此声称图影响覆盖。当前调用点检查确认 helper 仅被 `complete_cq_acceptance`
调用，外层 Host MCP 转发和 Runner 复核合同未改。没有 backend／frontend 执行代码变更，
本次不需要重启应用服务。

Consumer 初次回放退出未提交报告；诊断 retry1 保留两题 `reports=0`／`reads=0` 与
provider `responseStreamDisconnected`／`workspace routing discovery timed out`。
当前 shell 未继承本机已有 localhost 代理环境，显式复用现场配置后 retry2 两题均完成
真实会话并清理子进程／proxy／sink／private root。实际挂载的 prompt 与 v3 Skill 字节哈希
分别与当前仓库文件一致。失败目录及旧报告均保留，不将网络失败归因于模型质量。

G-04 后续 live read 同样复用本机代理配置，临时 key 和子进程／proxy／sink 均已清理，
`writes_attempted=false`、fresh semantic start 消耗为 0。receipt 范围内模型状态摘要一致；
没有独立前后 workspace snapshot，故不宣称完整前后无漂移或整体 L1 通过。

五项均已按各自关闭依据完成。两项 Consumer 问题取得独立有界公开回归 PASS，
提示／操作说明取得合同验证，恢复 helper 取得相关测试与只读现场证据。原始第四轮
`partial` 裁决、失败目录和未知项保留，本轮不改变整体 L1／L2／L3 的验收结论。
