# DSH 真实建模启动故障窄修复

本轮原授权：DSH、deepseek-flash、low，三次建模轮次，完成后关闭任务。
用户针对启动故障明确回复“同意”，授权修复两处缺陷、相关测试后继续原任务。
归属：[R4.3-031](../../requirements/requirements-v4.3.md#r4-3-031)。

## 证据与根因

Session `minimal-chain-20261018-dsh-low` 的 r1、r2 启动均未产生
`evidence/semantic-start.jsonl`，轮次实际消耗为0，剩余3。
两次原始 FAILED 状态、启动日志及清理证据保留在对应 gitignored run 目录。

- 非正式最小链的 carrier 保留历史正式 Coordinator capability descriptor，但
  Runner 只启动 Modeling／CQ 等适用 endpoint。DSH `_stage` 未按实际 formal contract
  区分，访问不存在的 Coordinator socket，抛出 FileNotFoundError。
- 部分角色尚未初始化时，Runner cleanup 查询整个 roster 的 provider wait；DSH
  直接索引不存在的 modeling agent，额外抛出 KeyError，阻断后续清理。

T0复核：第一处是错误装载历史角色能力，不是必要安全硬门。移除非正式 Coordinator
装载，保留实际 Modeling／CQ 的必要工具、权限和 schema 校验；不启动多余 endpoint。
第二处不存在实际等待者，返回无等待即可；保留已初始化角色的真实等待及恢复合同。
没有新增重试、计数硬门、角色、恢复框架或模型降级。只修改 DSH Adapter。

## 修复与验证

先补回归并观察失败：缺失 Coordinator socket 的 FileNotFoundError，以及未初始化
modeling 的 KeyError。再完成最小修复。测试使用本机固定 DSH／bubblewrap及离线
provider fixture，不请求外部模型。

在 backend 目录执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_dsh_runtime.py -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_dsh_events.py ../modeling_team/tests/test_dsh_delivery.py ../modeling_team/tests/test_dsh_acceptance.py -q
uv run ruff check ../modeling_team/runtimes/dsh.py ../modeling_team/tests/test_dsh_runtime.py
git diff --check
```

结果：**9 passed（65.69秒）＋33 passed（36.78秒）**，Ruff／diff检查通过。
覆盖实际隔离角色装载、工具表、暂停／继续、原session恢复、模型绑定、直接MCP透传、
部分启动失败后查询及重载，以及相关Delivery／验收路径。未重跑Team全量或产品测试；
本次无backend／frontend代码变更，无需重启产品服务。新Runner进程加载修复。
GitNexus impact未找到DshRuntimeAdapter，risk UNKNOWN；改用直接调用点与diff检查，
不宣称图覆盖。修复测试不代替真实启动、application或独立语义验收。

## 首次语义运行后的协议反馈修正

修复后的r3于05:49:17Z进入真实semantic start，两个batch原子应用到revision2，
Modeling原件保留。随后暴露两项真实接线限制：DSH只提供冻结材料读取／handoff输出，
Coordinator无法直接维护旧scenario-map挂载或动态CQ public文件；宿主已按原字节
转存其自行生成的图／拓扑，并通过原公开指令传递冻结事实，没有代写语义。
独立Delivery及一次显式原session恢复均遇provider HTTP400 INVALID_REQUEST，
外层沿已授权Host工具接管技术流程，未替换角色模型。

DSH terminal guard实际保护未消费的原生消息，但Broker把bool拒绝渲染为历史Protocol
检索错误，导致重复查询和错误issue归因。原始seq连续、无冲突；逐回合消费完原队列后
Modeling能报告completed。然而Coordinator已经报告blocked，后续派发触发
`dsh-dispatch-closed`并清理，未生成正式production handoff，故r3独立验收未执行。
不能手造Runner交接或把该轮称为语义PASS；模型及原失败证据保留，消耗1轮。

下一次start前持久修正权威DSH instructions：明确现有handoff输出到Host的原字节
转存方式，以及动态公开CQ输入通道；待收消息应自然结束活动以继续消费，普通等待
不能用blocked终态结束。Adapter仍保留queued／unknown拒绝，只改为可定位的
`runtime_input_pending` RoutingError，提示结束活动、消费原队列和核对unknown；
不再借用Protocol检索错误。没有删除写入／授权／未知结果保护或增加工具。
T0：未决输入保护确有必要，保留并收窄为可操作反馈；实际治理读回及独立验收仍另证。

先将原回归改为要求真实RoutingError，观察DID NOT RAISE失败；实现后事件／runtime
首轮15 passed，1条既有文案匹配失败。保留其unconsumed术语后，相关11 passed、
5 deselected（32.13秒），包含该终态回归、事件身份和工具／原会话路径；5条此前通过
且未受文案修正影响的测试未重复。Ruff／diff检查通过。原有未提交工作未改动。

## 授权任务终局（2026-10-18）

在同一三轮授权内，原r3失败现场保留；第二轮为
`minimal-chain-20261018-dsh-low-r4`，06:07:03Z真实开始。完整全景／切片审核后
冻结本轮独立题池，生产两批原子应用，原团队完成治理读回、关联检查和资源关闭。
Modeling／Coordinator均真实报告completed，Host按原字节转存Coordinator最终地图，
既有Runner发布正式只读handoff：ready=true、pending_writes=false、unknown_writes=[]。

复用现有`start_evaluation`／`cq-acceptance`，显式runtime=dsh及
`dsh-acceptance-deepseek-flash-low`，公开组先执行，再隐藏组三题，未超过三题并发。
两组各自独立Consumer／Judge报告full_pass=true：**公开1/1、隐藏3/3**，均无未执行题，
无实际coverage gap或model_state_drift，model binding digest相同。报告明确为
`non-blind-regression`，不扩称大业务、盲测或L2通过。隐藏报告由原Host合同回交，
06:15:24Z源Runner接受`cq_verdict=pass`、acceptance_complete。

用户要求的关闭已完成：源Runner state=CLEANED、PID退出、FIFO移除；两验收owner
lifecycle=stopped、无active／retained成员，记录的12个角色／owner PID均已退出，
DSH cleanup complete且无residual。13把已登记临时key撤销已由数据库读回确认；
各短Host操作另依原bootstrap finally撤销其临时admin。最终模型和历史失败证据保留。
**用2/3轮，fresh semantic starts=2；两次pre-semantic失败不扣轮，未用1轮已收回。**

实际生产/CQ及Consumer/Judge均验证deepseek-flash/low的DSH原生binding。
原Delivery HTTP400及显式恢复失败、Host文件转存／流程控制／私审／技术修复均披露：
本次是**有宿主补位的有界语义验收PASS**；DSH自主完整交付／034整条仍PARTIAL，
未切换任何标准默认，未把native supervision_interrupted改写为finish_delivery成功。
公开早期feedback／checkpoint acceptance continuation未触发，不冒称已执行。

完整原件在gitignored `workspaces/minimal-chain-20261018-dsh-low/`：
`authorization.json`、`final-report-verification.json`、`final-lifecycle-verification.json`、
`final-process-runtime-verification.json`、`final-key-verification.json`及原run／operation记录。
019现有离线报告已收集两轮、失败Delivery／恢复及六个验收原生session的数值原件，
输出`usage-report/report.json`及`.md`；usage／attribution／timing均partial，账单未提供。
Host及外部scoring用量不齐，不声称净降耗、完整费用或全任务token完整。
有效语义／技术时间未可靠分摊，保持unknown；阶段墙钟见原始时间戳，不用等待时间
冒充有效建模时间。没有继续扩展平台机制。
