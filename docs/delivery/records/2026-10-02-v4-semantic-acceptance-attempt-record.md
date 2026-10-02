# v4 真实建模与独立验收轮次记录

## 本轮授权与边界

2026-10-02 用户明确要求 Team 各角色统一切换为 `gpt-6.1-sol`、effort `medium`，授权五次建模并验收 v4 各需求。
授权 ID：`user-20261002-v4-sol-medium-five-starts`。真实取时为 2026-10-02T13:59:14Z（北京时间 21:59:14，非高峰）；用户显式模型选择覆盖时段调度。

采用 model profile `openai-sol-medium`，显式覆盖 coordinator、modeling、protocol、competency-question、acceptance、source-examiner、platform-examiner。
生产和独立 CQ 验收均须显式传递这一 profile；旧配置保留作为历史运行复现入口，不为历史模型静默换绑。

获准目标为已实现 v4 条目的 L0 Runtime 与 L1 Modeling quality，并补齐 007／008／010／011 独立功能验收。
R4.0-001 仅登记未实施，保留未验收；005 自动物化及 004 并行同步不属于当前交付范围。
不执行外部业务 SQL／API 或规则脚本。数据库和 API 映射的样例语义可按获准资料验收，不把语义描述当成在线执行成功。

Task 复用 `modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml`，Team profile 为 `r3-0-011-competency-question`，scope 为新建隔离 Project。
生产只接收 Task 获准输入；隐藏题与验收答案不进入生产角色。业务补充及 CQ 审核代办权限等待用户答复；未授权前不代批冻结。

## 模型配置验证

模型路由白名单新增精确模型 `gpt-6.1-sol`，沿用 OpenAI Codex 订阅认证和原有 effort 透传。
新增七角色 profile 与加载回归；路由／模型目录相关 80 项测试 PASS，v4 Task 的 validate 确认七角色 requested/effective effort 均为 medium。
GitNexus impact 为 LOW（3 个直接依赖、0 条已索引流程）；detect_changes 为 low。未改 backend／frontend、API 或存储合同。
完整 Team 回归：2114 passed、1 skipped、314 subtests passed（155.81 秒），日志 `/tmp/r4-sol-medium-team-tests.log`；skip 不计 PASS。Ruff、diff check 与配置 validate 通过。冻结提交后续补入。本轮不为模型配置启动应用服务或修改全局 Codex／Claude provider。

## 额度与进展

上限 5 次 fresh semantic modeling starts；目前尚未启动，已消耗 0，剩余 5。
宿主台账为 `workspaces/v4-acceptance-20261002/authorization.json`。启动接受、CQ 访谈及基线冻结不冒充正式语义开始，实际计数以运行语义开始证据为准。
安全继续同一存活运行不重复计数；生产检查点接续或重建建模线程计为新 start。独立 acceptance-only 接续不消耗建模 start。

真实结果尚未产生，各条目的整体 PARTIAL／未验收状态不因本次授权而改写。每轮追加 run ID、冻结版本、实际角色模型、第一阻塞、写入／保留状态、独立判定及余额。

## 2026-10-02 22:20 +08 观察与截止约束

用户后续明确授权宿主代答访谈、补充标记为测试定义的业务资料并审核冻结 CQ。
本轮补充为 `workspaces/v4-acceptance-20261002/approved-business-supplement-v1.md`，通过 CQ 私有访谈与生产 owner 通道分别送入，不含隐藏题或旧版答案。

- 启动前失败 `r4009-20261002-solmedium-auth01-start1`：operator-admin Key 未绑定用户，未创建 Project/Ontology，semantic starts=0。绑定原 Key 到当前唯一启用既有 org-admin 用户，未新增用户/权限。维修证据在宿主目录。
- 第一次语义开始 `r4009-20261002-solmedium-auth01-start1b`：2026-10-02T14:12:16.610366Z，冻结提交 `8e6a18c`，基线摘要 `23774bccd0aecabe0ee3e0485a2a76e5f800a4d3b7b6aabc2e77562ffe8ce5ab`；四个实际角色 config 均为 gpt-6.1-sol medium。
- 第一阻塞为 runtime/infrastructure：Coordinator 日志 `workspace routing discovery timed out`，SDK 两种传输重试后终止。当前宿主未继承代理；复用 .bashrc 中既有 localhost 出站代理后，同一 endpoint 返回 HTTP 401（未认证网络探测，非模型服务成功）。不改运行时或提示合同，不降模型。
- 第一轮已退出；临时 Project/Protocol Key 和 admin Key 均撤销，scope 按 scenario_mapped-0001 已发布检查点引用保留。没有 staged Batch 写入事件，不声称取得 L0/L1 PASS；runtime secret audit 未全部清除标记保留在原始清理记录，不声称全局零残留。
- 已消耗 1 次，余额 4；下一步带正确代理环境 fresh start，不重写失败产物。

独立功能验收实际 324 passed／1 skipped；008、010 的 A1—A9 有界 PASS；007 A4—A6 与 011 A5／A7 保留具体覆盖缺口。见 [独立记录](../tests/2026-10-02-v4-independent-functional-acceptance.md)。各项真实 A10 未执行，整体仍 PARTIAL。

用户要求北京时间 2026-10-03 01:00 未完成即停止所有本轮任务并收回余额。
已安装 user systemd timer `v4-acceptance-deadline-20261003.timer`，触发 UTC 2026-10-02 17:00:00，AccuracySec=1s；list-timers 确認显示 01:00:00 +08。
脚本 `workspaces/v4-acceptance-20261002/deadline-stop.py` 首先撤销剩余额度，再按台账向存活 Runner 发 stop；必要时在 30 秒收尾窗口后只停止仍匹配的本轮进程组。保留资源与未知写入供重启前核对，不删除平台数据。结果落宿主目录；用户未重新授权前不再开 start。
