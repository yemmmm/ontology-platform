# 最小安装链新组：GLM Flash high 首轮运行

2026-10-16用户要求“开启新的一轮建模，授权三次，模型使用glm-5.3-flash high”。
沿用[R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026)最小安装链，
Task／Profile均为`r4-3-026-minimal-installation-chain`，新建scope与会话。
生产代码为`f58f3c3`；全部生产、Delivery、Consumer与Judge请求使用
`glm-direct / glm-5.3-flash / high`，未沿用上一组Delivery的特殊模型配置。

## 结果与证据边界

- 最小链公开**1/1**、隐藏**3/3**独立语义回归通过，报告标记均保留
  `non-blind-regression`。原始报告、逐题响应和Judge裁决不改写。
- 两个fields-only Class与一条`installed at`关系类型实际应用，revision0→1→2；
  没有创建NamedIndividuals或安装实例事实。实际端点为安装资产→现场，与源定义及
  独立Judge裁决一致，没有发生自查后的端点修模。
- 完整关联扫描检查3个资源、23条语句，issues与unresolved_references均为空；
  Build Session正常完成，无活动租约。两份验收报告的前后绑定及保留响应复核无漂移、
  无unavailable，逐份`batch_report_is_full_pass`复算为true。
- 初建消耗**1/3轮，剩余2轮**，fresh semantic-start为1；没有实质修模或授权越界。
  独立只读验收与技术输入纠错未扣建模轮次。
- Delivery发生多次宿主补位：启动漏传profile、切片题审核完成前冻结、生产结束后
  尝试补早期反馈检查点，以及只完成隐藏题就发出final。后续沿原通道纠正，保留原
  错误与过早final；**不能记为Delivery自主交付PASS**。

run为`r4326-20261016-glmhigh-d-start1`，Delivery为
`minimal-chain-20261016-glmhigh-d`；宿主台账保存在
[授权记录](../../../workspaces/minimal-chain-20261016-glmhigh-d/authorization.json)，
补位保存在同目录`host-supplements.jsonl`。

完整冻结为`cq-batch-0002`，摘要
`sha256:4936ace8954b07049caa6d62869ebef32d484e8f9ad4ae3763879b5cdbe5a435`。
此前部分冻结`cq-batch-0001`原样保留，不作为最终分母。

| 范围 | 实际独立报告 | SHA256 |
| --- | --- | --- |
| 隐藏3题 | [原报告](../../../workspaces/modeling-runs/r4326-20261016-glmhigh-d-start1/acceptance-v3/reports/cq-batch-0002/attempt-0001/batch-report.json) | `7545d8abd6624ffa7a11e3285cf55f3a912cc8ed016784b30da486fbfcf828de` |
| 公开1题 | [原报告](../../../workspaces/modeling-runs/r4326-20261016-glmhigh-d-start1/acceptance-v3/public-regression/cq-batch-0002/attempt-0001/batch-report.json) | `89d7bb82ce51c0df78d2ed90db9a15feef5c5be03dd46488bf90f16301f0f55d` |

两份报告的`model_binding_digest`相同：
`sha256:3092f6b62b1b10cf0d7b2c7b94aa4caf5917818bf80fd29a78339c4df5b85508`。
隐藏报告已通过`complete_cq_acceptance`交回原Runner，`cq_verdict=pass`；公开回归
独立保留，不覆盖隐藏报告或其闭包。模型资源与原Team／Consumer保留，只读待命；
Runner写能力已封口，宿主额外启动admin凭据于04:43:51 UTC撤销。本scope只读验收凭据
随原Consumer保留至显式stop，见[资源记录](../../../workspaces/minimal-chain-20261016-glmhigh-d/final-resource-status.json)。

## 时间线与成本缺口

时间统一为UTC；报告文件mtime仅为本机落盘时点，不当作模型内部完成时间。

| 时点 | 事实与来源 |
| --- | --- |
| 04:09:07 | 宿主配置和授权台账就绪；原始用户消息精确时间未取得 |
| 04:12:04 | `evidence/semantic-start.jsonl`首次真实开始，20分钟启动期限内 |
| 04:22:28 | 完整题池冻结；早先部分冻结与重复唤醒均保留 |
| 04:24:57 | 两概念批原子应用完成，revision0→1 |
| 04:25:40 | 安装关系批原子应用完成，revision1→2 |
| 04:27:36 | `modeling_finish_changes`成功，关闭所属Session |
| 04:30:30 | 只读查询超时issue沿原线程guidance恢复，未改模型 |
| 04:34:12 | 生产交接与真实写能力封口 |
| 04:34:45—04:37:23 | 隐藏Consumer/Judge操作开始至报告落盘，约158秒的操作窗口 |
| 04:39:36—04:42:10 | 公开Consumer/Judge操作开始至报告落盘，约154秒的操作窗口 |

从宿主配置就绪到两批报告齐备约33分钟，包含等待、审核、压缩和技术推进，不能称为
33分钟有效语义工作或无故障性能基线。生产语义、Delivery审核／压缩、文档、等待及
技术诊断的完整有效工时和Agent重叠尚不能准确拆分，均保持unknown；不能确认语义
有效时间是否过半。两批独立消费操作窗口分别记录，不与生产语义时间合并或外推效率。
本轮未扩展平台／harness，发现等待后缩短到既有live验收通路。

用量原件保留于Delivery的`native/usage-events.jsonl`及运行的原生／provider事件；
整轮按角色归一化输入、缓存、输出、压缩归属和账单未完整对账，不据局部线程计数
报告整轮成本，也不将累计输入作为费用。

## 故障、未执行项与后续范围

`issue-1`为只读`query_semantic_context`三次5秒超时。完整类／实体／事实读模型及
关联检查可用，Delivery以guidance恢复原线程；独立验收取得实际受治理响应并通过。
保留该超时和即时召回自查缺口，不推导模型缺失，不声称已修复查询服务。
最小Task未启用检查点；早期`public-feedback`未执行，不新增补验前置门。

本组过程存在宿主纠偏，后续自主交付效果仍待验证。旧组失败、越界及更大业务范围
的质量／效率结论不改变。本轮中用户新增的
[R4.3-027](../../requirements/requirements-v4.3.md#r4-3-027)仅登记，提交`c42dc86`；
当前验收仍使用现有批内串行实现，未实施三个题目任务并行。

## 2026-10-16 用户显式关闭

用户后续要求“关闭本轮建模任务”。沿原Delivery发送`停止`，撤回生产／验收启动权限；
原Team、两批验收Consumer和Delivery均已实际退出。正常清理记录保留：只读凭据撤销
出现`ModelingReadError`，宿主按原key身份补充撤销；Runner已落盘`CLEANED`但自有
MCP子进程及owner未退出，宿主精确SIGTERM后Delivery正常退出0。没有修改平台代码。
最终核对本轮五把临时平台凭据均已撤销，无所属进程残留，两份验收报告SHA256未变；
模型资源和证据保留。消耗仍为1轮，未使用2轮随本任务关闭，不再自动启动。
实际关闭核查见[停止记录](../../../workspaces/minimal-chain-20261016-glmhigh-d/stop-completion.json)。
