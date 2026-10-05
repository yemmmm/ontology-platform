# 进展、设计决定与额度申请

在已有运行记录中保留 run ID、时间、授权来源/余额、原始失败、修改提交、验证层级、资源状态
和证据路径。不要再建一套平台计数器。用自然中文报告实际发生的内容，未知就写未知，不能把
下面的格式填成虚构进展。正文先让用户理解发生了什么，再给必要的技术标识和链接。

## 最新摘要（R4.0-021）

在已有运行记录顶部维护这份短摘要作为导航；历史阶段、原事件、冻结、checkpoint、失败、
报告和清理证据保留原样。阶段变化、新阻塞、配置/授权变化或接续交接等实质变化时更新
摘要；日常巡检只追加新增事件与待办，无变化不重填下列字段。摘要注明本次核实时间和范围，
各事实引用已有来源/时间即可，不逐字段重新取时或重复核查。缺失/冲突/不可读写 `unknown`
或待核实及 limitation，不从 `RUNNING`、角色自报、handoff ready 推导语义 PASS。
新结果替代旧阶段状态或重新准备资源时写明新时点、适用范围及旧记录链接，不覆盖旧裁决。

```text
核实时间 observed_at：[UTC ISO-8601；显示时区另声明]；当前范围：[本阶段/批次]
run/checkpoint/process：[真实 ID、来源；角色 terminal、handoff ready、managed exit 分开]
语义成果/验收：[已有表达/回执/检索证据；范围、应验收分母/已执行/有效裁决/通过]
first_blocker：[第一失败层/准确错误/证据；无或 unknown，不删除历史失败]
completed：[本阶段已证实完成及范围]
remaining：[原获准目标未完成项/依赖]
next：[具体入口和动作；条件满足则汇报后继续]
authorization：[来源引用、适用范围、production 已用/剩余；不可得写 unknown]
wait：[无，或缺失决定/权限/兼容性/额度；影响动作与独立可做项]
resource：[实际保留/撤销/重新准备/待核实状态、时点和范围]
handoff：[下一观察者、时间、run 根/日志偏移/恢复入口；未安排如实写明]
evidence：[get_run_status 核实来源及原 events/pending/profile/报告链接、行号或偏移]
limitations：[只覆盖什么、未执行什么、冲突/不可读证据、unverified 项]
```

run 级 status 不含完整 session 授权余额时引用宿主台账，不能由 tool/semantic-start 数量猜额度。
摘要用安全白名单，不带隐藏题面/答案、凭据或完整环境；报告样式不是新 API/状态机/审核门。
用户短进度只说明实际成果、第一阻塞与下一动作，需要时附关键证据链接；详细字段和历史
定位留在运行记录，不要求每次向用户重复整份摘要。

## 配置交接（R4.0-019）

在既有 session 台账记录执行者、model/profile、effort、service tier（`unset`/`fast`/`default`
off）、适用角色/范围、更新时间和授权引用。新指令只更新适用项，保留未改变的原目标/约束；
最新适用用户指令优先于 Skill 默认及分时段安排，角色无需统一配置。每次入口分开写：

| 事实 | 来源与限制 |
| --- | --- |
| 用户请求 | 台账/交接消息的时点、角色/范围、授权；未指定写 unset |
| 启动传递 | argv/profile 和 launch record 的 service_tier 或本次 CLI child env 处理 |
| 实际生效 | profile.snapshot/角色 requested/effective effort、实际隔离 TOML/native thread 安全字段 |

production checkpoint 不支持 model_profile 覆盖时写 `unsupported`，effective 仍为 source
profile；acceptance override 单独核对。读不到实际配置写 `unverified` 和 next action，外部
provider 对 Codex fast 字段写 `not_applicable`，不静默替换。旧线程 immutable，不为统一
配置擅自重开 start；不能由 fast 推导提速、计费或语义质量。处理详见
[运行参考](team-runbook.md#session-配置传递与核对r40-019)。

## 阶段汇报后的动作（R4.0-020）

本阶段结束后先填 completed/remaining/next/authorization/wait/resource/handoff，仍有已授权
明确待办且条件满足则继续；隐藏验收完成而公开待办仍可执行时不报整体完成。live
`cq-acceptance` 保持源 Runner 存活、生产静默，报告回源 `complete_cq_acceptance`；
S4 则先确认有效 COMPLETE handoff checkpoint 与安全资源保留，再 stop/receipt/managed exit
并在新输出目录接续验收，不向已死源 FIFO 收口。不丢失 checkpoint、待办或额度。
缺实质业务、权限、兼容性或新额度时仅阻塞相关动作，独立工作继续。目标完成、暂停/取消、
到期或确无安全动作才收尾；余额不触发无必要 start。结束进程临时密钥及时撤销，连续资源
按原生命周期保留，已撤销 key 不复活；必要重新准备记录真实时点，不批量改旧清理证据。

## 分类耗时（R4.0-021）

沿已有事件和记录追加区间，不逐工具强制打点；源信息不足可合并并说明限制。

| category | 工作范围 |
| --- | --- |
| production_semantic_modeling | 生产访谈、语义分析、候选建模修订与获准业务资料处理 |
| independent_consumer_judge | 独立检索回答和 Judge 判定，scope 区分 public/hidden |
| waiting | 等业务回答/授权/接口/进程资源或明确下一动作 |
| repair_test | 故障诊断、窄修复、开发测试及独立功能复测 |
| review_docs | 方案评审、记录审阅、设计及文档维护 |
| startup_cleanup | 最小启动准备、停止清理、资源恢复与交接 |

```json
{
  "session_ref": "<safe session reference>",
  "interval_id": "<stable id>",
  "category": "repair_test",
  "scope": "<stage/agent/public/hidden>",
  "started_at": "<UTC ISO-8601>",
  "ended_at": null,
  "duration_seconds": null,
  "basis": "observed|event-derived|estimate",
  "source_refs": ["<existing event/record>"],
  "overlaps": ["<other interval id>"],
  "note": "<coverage and uncertainty>"
}
```

统一保存 UTC，报告声明显示时区。明确端点可计算时才写 duration；缺结束时点不猜 duration，
长无事件窗口不能都填生产语义。墙钟总耗时按 session 实际经过时间或可定位区间 **union**，
重叠不能重复累加；累计 Agent 时间另命名 `cumulative_agent_seconds`，不与墙钟相加。
分类可重叠时单列 overlaps，不把非互斥类别总和当总量。只有进程窗口或局部估算时写
unknown/`basis=estimate`、覆盖窗口和来源，不外推全 session，不伪造 CPU/token/计费。
生产语义与独立消费分开展示，合并比例须写分子/分母和统计窗口。语义有效时间不足一半时
报告原因、暂停扩展平台/harness 并提出更短通路；数据不足写不能确认比例，报表完整不是
语义 PASS，不为填表延迟第一次真实 start。

## 每轮结束

说明走到哪一步，产出了什么，为什么停止，采取了什么修复以及是否实际复测，剩余多少次。
有源忠实度/检索质量证据则明确列出；没有则明确未取得，不能用工具调用次数替代建模成果。
区分启动拒绝、实际执行题数、有效裁决及完整分母；只读验收 continuation 记 0 production
start，生产 checkpoint continuation 仍记 1 次。历史 partial/fail 不拼成新 PASS。

## 额度耗尽后申请

先完成已有授权内安全可做的窄修复、写状态核查和证据整理，使下一轮计划具体可审阅。
仍有不确定写入或关键设计待决时，先讲清该阻塞及处理计划；追加额度不能消除这个前置。
需要用户操作才能解决的阻塞应明确提出，不能静默等待或继续新建 run。

建议按以下顺序写，简单轮次可用连贯段落，不强制表格：

1. **目标与结果**：本轮原目标、授权总数与已用次数，目前到达的阶段。先讲业务进展，再附 run ID。
2. **各次尝试**：每次推进到哪里、主要产物、第一阻塞及资源状态。保留各轮失败，不用后续成功覆盖。
3. **问题与修改**：用普通语言解释原因、做了什么、为什么能改善；附相关设计决定/commit。
4. **证据与缺口**：哪些修复已自测/独立验证，哪些真实步骤仍未执行。代码通过测试不等于模型通过验收。
5. **耗时与资源**：语义建模和基础设施/修复、评审、文档的有效时间；平台资源是保留、清理完成还是待核实。
6. **下一轮计划与申请**：剩余目标、为什么需要 fresh start、优先验证什么、建议追加的具体次数。

申请句应具体，例如：“申请追加 3 次 fresh modeling starts。下一轮先验证修复后的交接能否
推进到正式写入，再继续本轮尚未完成的检索与独立验收。”这只是表达示例，实际步骤和次数
以本轮证据与用户目标为准。新授权到达前不启动；不能把失败自动退款或把沉默当作同意。

## 自主设计决定

记录问题证据、变化内容、预期收益、为何符合 AGENTS.md、对相关语义/兼容性/授权/资源/验收的
影响判断及验证计划。证据足够则自行决定并告知用户，不因改动较大或涉及多个文件自动申请。
影响未知或确实越过业务/范围/兼容性/授权边界时，整理具体推荐方案和备选取舍交用户决定，
并说明依赖该决定的动作；继续不依赖它的安全工作。

## 会话交接

保留当前目标、授权和余额、真实进程/session、实际 checkout/服务版本、run 根与日志偏移、
当前阶段和等待对象、未决设计/写状态、已完成修复及下一动作。明确后续监控由谁接手，
未实际安排接手时不能声称“后台持续监控中”。
