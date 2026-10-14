# R4.3-019 整轮模型用量、吞吐口径与账单对账设计

## 1. 范围、授权与基线

权威范围：[R4.3-019](../../requirements/requirements-v4.3.md#r4-3-019)，承接
R4.3-001／016、R4.0-021及R2.3-007。决策D1—D7主表在权威需求，不复制理由表。
2026-10-14用户授权细化与设计，本轮只有文档工作，无独立审阅、开发、provider调用
或新运行。静态代码基线`b186f35ad535b83507634138cc379eaa98374849`；无关未跟踪目录
`docs/presentations/`、`slide-deck/`保留。设计已形成，文档自查不标独立设计PASS。

例子：生产角色98.22%、保留整轮91.80%、控制台同Key全天92.34%的缓存命中率覆盖
不同。必须分开任务和账单窗口，计算已知用量与覆盖，再核对未匹配量和调用归属。
历史数值见[登记证据](../records/2026-10-14-modeling-cache-cost-requirements-registration.md)。
控制台时区未核验，未命中8,717,117差额仍PARTIAL；本轮不运行旧脚本或改写原件。

| 已查入口 | 当前能力／限制 | 本设计处理 |
| --- | --- | --- |
| 私有`cache-cost-audit-20261014/analyze.py` | 读rollout逐响应和App Server累计，绑定compaction ID；固定目录／线程、缺字段补0、断言跨线程重复 | 复用算法依据，采用显式范围与可定位覆盖报告，不直接当通用工具 |
| `modeling_team/runtimes/codex.py::_record_notification_header`、`_append_runtime_evidence` | 留存app-server-events.jsonl与隔离native rollout | 继续用原件，不改通知路由／角色权限 |
| `modeling_team/runtimes/delivery.py::DeliveryRuntime._handle` | 处理动态工具／turn终态，没有单独留tokenUsage通知，主要靠native rollout | 纯数值通知留存，不转发到模型输入 |
| `modeling_team/acceptance_runtime.py::ExaminerRunMetrics` | 累计增量／totals／ttft／turn耗时；若干缺字段归0，ttft也接受工具／命令delta | 作核对或turn活动来源，不当逐响应账单或provider首token |
| `modeling_team/deepseek_provider_proxy.py::ResponsesProviderSession`、`_SessionHandler.do_POST` | provider-neutral代理；有请求／重试汇总与透明字节转发，无逐attempt身份计时 | 可选Host数值observer，不解码／保存响应正文 |
| `modeling_team/model_routing.py::RoleModelBinding`、`ProviderSessionManager` | 实际provider、模型、requested/effective effort及共享代理 | 沿binding传身份；非秘密Key别名由Host给出，不从secret计算 |
| `modeling_team/delivery.py::_run_delivery` | Delivery独立native home／provider manager；测试代答可直接复用DeliveryRuntime | 传session／operation／实际角色，不按类名归Delivery |
| `backend/app/services/semantic_jev.py::JevReranker` | 辅助评分是另一模型，当前返回评分／模型，不是完整usage回执 | 已发生辅助模型与缺usage单列，本期不改backend |

本轮做聚焦源码／调用点核对，未做GitNexus图影响分析。后续实现共享代理时，核对
上述调用方及production／evaluation manager构造处，不以设计声称图覆盖。

## 2. 最小方案

新增Host离线模块`modeling_team/usage_report.py`，拟使用
`python -m modeling_team.usage_report --scope <scope.json> --output-dir <新报告目录>`。
这是拟交付命令，目前不存在。仅本地读写，不获取凭据、不调用provider或启动服务；
输出放已有gitignored Host工作目录，含`report.json`及`report.md`，由同一归一化结果
渲染，供既有复盘／优化台账引用，不另建台账或监控平台。

Host给出task/session/run/operation/thread绑定、源范围、窗口及可选供应商值／价表。
工具仅在指定根内枚举已知格式；未绑定项列unallocated及原件定位，不扫描全机。
源是私有原件，报告只含数值／元数据。成本观察不注入生产或独立盲测输入。

另补Delivery累计数值留存、代理上游attempt身份／计时。无需通用遥测框架、Codex
分支、SSE/JSON流解码器、自动控制台登录或跨客户端强行相关。没有唯一response↔attempt
绑定，完整API吞吐继续unknown；最小采集不承诺闭合所有历史账单差额。

数据流：范围及原件 → 响应去重／累计连续段核对 → 任务与账单两种视图 →
分层数值／计时／价格估算 → 对账与缺口 → JSON／Markdown。统计不参与run状态判定。

## 3. 输入和记录合同

以下是局部结构设计，实施按实际日志版本机械对齐，不是新HTTP／MCP合同。

### 3.1 范围清单

`schema_version=model-usage-scope/v1`：

| 字段 | 含义与证据 |
| --- | --- |
| task_ref、code_revision、config_refs | 任务身份、实际代码及profile／资料版本引用 |
| task_window | 授权开始、cutoff或完整PASS收尾、UTC及原时区、是否未完成、起止来源 |
| bindings | source path、session/run/operation/round/thread、role/phase、provider/key_ref/model及requested/effective effort，每项附绑定来源 |
| sources | 指定rollout、app-server事件、metrics、attempt、session／operation记录；种类、版本和字节范围 |
| layer_coverage | 实际层与observed/partial/unknown/not_invoked及依据，不预设角色数量 |
| billing_scope | provider/account_ref/key_ref/model、[start,end)、时区、计费时间口径、供应商值与来源；缺失允许但对账PARTIAL |
| price_versions | provider/model、币种、单位、生效窗口、来源／核实日期、计费类别单价及舍入；可不提供 |

key_ref采用供应商非秘密ID或Host人工别名，如`modeling-key-A`，记录筛选确认来源。
不存Key片段、digest或凭据路径；人工别名本身不能证明控制台匹配。
恢复沿同task与真实thread，不因新目录新建任务。共享线程按可证的响应／窗口切分；
无法切分的量单列共享／未分配，不让清单声明代替证据。

### 3.2 归一化用量

`schema_version=model-usage-record/v1`包含：

- 身份：provider/key_ref、response_id或真实request_id、thread/turn、session/run/
  operation、role/phase/round、source_mode=response或thread_cumulative，缺失null。
- 配置：requested_model、actual_model、两种effort。配置仅证明请求值，缺返回模型
  时actual_model=unknown，账单按可证明的模型组匹配，不伪造执行模型。
- 数值：input/cached/uncached/output/reasoning_output/cache_write tokens，缺失null；
  累计原值与连续段保留，model_context_window另作配置，不进入usage求和。
- 来源：path、真实byte_offset/length或record identity、所读范围digest、原时间及
  是否本机接收时间；每次扫描重置的line_no不当全文件定位。
- 覆盖：字段存在性、missing_fields、conflict/ambiguous/reset/truncated等及定位；
  不复制provider错误自由文本、业务或推理正文。
- 压缩：真实compaction_response_id绑定已去重response，kind=compaction只是子集。
  缺绑定时压缩用量unknown，空工具请求不作为压缩判据。

源字段映射区分已支持provider／日志schema，不建动态适配插件。不支持格式标
unsupported_source及覆盖缺口；字节估算独立展示，不进入真实计费用量。

### 3.3 输出与状态

`schema_version=model-usage-report/v1`包含metadata/scope/sources/task_usage/
billing_window_usage/layers/compaction_subset/timing_metrics/cost_estimates/
reconciliation/limitations。JSON保留整数，速率／金额注明公式与舍入。
append-only源绑定已读取前缀长度／digest，可替换文件绑定实际完整字节；新源或源
变化生成新报告，不覆写旧原件。首次读时实际冻结所读范围，报告不引用浮动latest值。

分别记录usage_status、attribution_status、timing_status、billing_status。observed只是
该源可读；complete仅在声明范围／必要字段都可证明时成立；partial保留安全小计；
unknown无证据；not_applicable有理由。不同字段完整性分开，缺cached不否定已知input。
账单状态MATCHED/PARTIAL/MISMATCH/NOT_PROVIDED：缺范围仍PARTIAL，MISMATCH
要求范围完整且差额超出显式舍入规则。不得单一PASS掩盖计时／归属缺口。

## 4. 去重、累计与分组

1. 留实际读取范围与解析缺口，半行、坏行、缺文件不变零；继续处理完整可信记录。
   scope结构无效返回本地输入错误，不触及运行进程。
2. 唯一响应键为(provider,key_ref,response_id)。provider／Key不明不与已知组强合并。
   无response_id仅接受真实唯一request绑定；同身份同数值合并源，数值冲突为conflict，
   不任取一份。可信总量可由完整累计段保留，冲突逐次小计不任选。
3. 累计按真实thread／连续段核对，重复不增，起止相减。只有fresh且零基线有依据才
   默认起点0；缺起点的终点只能叫“线程至此总量”，不是指定子窗口增量。乱序按真实
   事件顺序核对，不能取字段max掩盖重置／计数下降。
4. 同窗口逐响应齐全则取逐响应并交叉核对；只有累计可证明总量则取累计。部分重叠
   时总量取已证连续段，逐响应只作明细，差值叫unitemized residual；只有相同窗口、
   字段单调及包含关系有证据才能相减。否则两类并列且不相加，不声称完整总量。
5. 一个canonical成本单元只归属一次。role/phase未知仍可进入已证明任务总量；task
   自身未知不进目标任务，留账单窗口unallocated。复制会话不是新调用，实际fork后
   新response是新调用；跨task归属冲突不能静默二选一。
6. 压缩／失败／中止是总量子集，不能再相加。无usage的attempt单列；attempt与response
   可能表示同一次成本，无绑定不能声称总请求数=attempt数+response数。

示例：连续线程input从1,000升至1,800，两份复制rollout都记同response input=500。
若同窗口包含关系已证，本窗口总量800、逐次明细500、未细分300；不是1,800+500+500。
缺起点不能宣称800；input已证但cached缺失时，input=800、cached及命中率unknown。

## 5. 成本与账单对齐

常见“输入含缓存，推理含于输出”价表可用
`cached×p_hit + uncached×p_miss + output×p_output`再按unit换算，仅对已确认采用
此计价定义的provider适用。缓存写入是否输入子集／是否另收费按价表，不全局相加。
金额用Decimal，不同币种不换算合计，模型／价格生效段分别算；跨生效段只有累计
不能切分则金额unknown，不用均价补。订阅可报tokens但无API金额，缺价只限制金额。

任务视图回答“本任务用了什么”；账单窗口视图回答“控制台筛选范围有哪些已留存
调用”。后者区分目标task、已证other_task、unallocated、已知无usage。未提供其他
任务源时列outside_inventory_unknown，不解释为已发现其他客户端，更不全归Delivery。

按provider/account/key/model/[start,end)/计费时间口径对齐。供应商按request start
或结算归日而本地只有completion时，跨界为boundary_unknown；不默认北京时间／
服务器时区。累计跨日无逐次回执也无法硬切。输入／缓存／输出定义不一致为
not_comparable。差额vendor−local_matched允许正负，未齐范围仅raw_difference。

token与金额分别核对，税、折扣、舍入仅按已有供应商说明；无隐藏容差。MATCHED需
所比较字段与范围完整且一致，但attribution仍可PARTIAL。范围完整且真实差额为
MISMATCH，不自动断言供应商出错。控制台人工转录可导入，时区缺口继续PARTIAL。
历史8,717,117差额关闭需补同窗口供应商及实际来源证据，不因工程完成关闭。

## 6. 吞吐公式与覆盖

| 指标 | 分子／计时 | 限定 |
| --- | --- | --- |
| 请求完成输出速率 | 绑定response output / 请求发送前至usage完成秒数 | 请求级真实绑定；注明客户端／代理边界、是否含重试／输入处理 |
| 响应头后窗口速率 | output / headers至usage完成 | 不含头前等待，不能叫完整API吞吐 |
| 生成窗口速率 | output / 真正首输出至usage完成 | 无首输出为null，网络字节／工具输出不是首token |
| Agent turn活动速率 | 已归属本turn output / turn start至terminal | 含工具／等待，线程累计不能切turn则不算 |
| 整轮墙钟 | 授权开始至完整独立PASS及收尾，未完成至cutoff | 沿001，不从首次apply重置，不当API token/s |

Examiner ttft_ms可能源于commandExecution delta；metrics_complete不能证明provider
TTFT。推理已含总输出，缺分离统一注明“含推理总输出”，不宣称可见文本速度；
缓存输入不参与输出速率。失败／中止有usage仍入成本，无完成点不进成功吞吐样本。

完整配对样本Σoutput/Σduration为耗时加权速率，不平均每次速率。并行合计只在
同一可比较时钟上取Σoutput/区间并集秒数；最早start至最晚end另叫wall_window_rate，
注明包含空闲。各进程monotonic不能直接跨进程相减；并集需同源UTC或有证据校准。
每项列used/eligible/unknown样本、可算输出／已知输出覆盖、起止来源和失败分组。
总量未知则覆盖比例null，不用已知样本自称100%。历史482/610与195／153token/s
保留局部口径，不外推整轮成功基线。

## 7. 最少数值留存

### 7.1 Delivery

`DeliveryRuntime._handle`遇thread/tokenUsage/updated，仅保存thread/turn、接收UTC、
原字段存在性／非负整数及实际binding到native Host目录`usage-events.jsonl`。
不存完整notification，不改tool/send/steer/终态，不进入022模型输入。重复累计可留
原数值供离线去重，不在runtime重建计费状态。测试代答按实际operation／role传入，
无Host上下文保留unallocated，不按类名归Delivery。rollout仍为逐响应首选。

写失败／回调异常沿已有Host日志只给固定usage_capture_incomplete及非秘密身份，
原runtime继续；目录完全不可写时报告从源缺失和session记录标unknown，不为留存
失败再增阻断。采集器不读取或改变用户授权。

### 7.2 共享Responses代理

`ResponsesProviderSession`加可选on_attempt回调，默认None保持既有构造调用。
`ProviderSessionManager`在实际拥有统计上下文处接线：Delivery及Codex adapter
production／evaluation manager。具体回调与writer足够，不建observer框架，不改
on_failure、重试次数／退避／状态／cleanup。

每次上游发送前生成session-local request_id和attempt_index，记录start、end或
unfinished、HTTP status／固定transport类别、requested model/effort及可证明的
task/run/operation/provider/key_ref。do_POST已解析请求，只读配置字段，不归档body。
start先留存，进程意外终止可保留unfinished；两事件绑定同attempt。

共享会话请求通常无thread字段，role/thread为null，不能从相同模型／时间近猜测。
attempt_index>1证明重试，不证明收费或解释差额；未唯一绑定provider response，不把
代理start配某rollout output算API吞吐。本期不注入provider不支持的字段／header，
不新增流解码器来强补绑定。SDK内其他尝试未观测时另披露覆盖，不称全量请求可见。

回调异常只影响覆盖，原字节转发继续；锁不跨网络I/O，流中断／客户断开沿原行为。
白名单不含headers、Authorization、body、reason phrase、异常字符串、凭据路径。
A6须证明关闭或失败的采集不改变既有重试、转发、工具和权限边界。

## 8. 实施交接和验收

后续获准实施预计范围：

1. `modeling_team/usage_report.py`及`tests/test_usage_report.py`：scope、既有格式、
   去重／累计、双视图、覆盖、价表及两种报告，先验证A1—A5。
2. `runtimes/delivery.py`、`delivery.py`及`test_delivery_runtime.py`：数值白名单和
   session／operation接线，不改022观察投影／wake计数。
3. `deepseek_provider_proxy.py`、`model_routing.py`、`runtimes/codex.py`及既有相关
   测试：on_attempt及实际manager接线，A6覆盖回调异常、重试和断开。
4. `modeling_team/README.md`补Host CLI与报告边界；复盘／台账引用结果，不自动
   建模。无公共API、backend／frontend、migration或应用服务配置变更。

A1—A6为确定性计算／功能反例，不建当前运行专用一次性验收器。A7只读冻结历史
原件复算：同scope／源digest生成相同规范数值与Markdown表，生成时间等另列；
新源需新目录，不覆写旧报告。真实provider对账／新量测仅在另有授权时执行，缺供应商
数据不能以本地测试替代。成本包含补读、输出、失败、压缩、宿主及诊断，对照模型／
effort／窗口变化分组，不承诺节省比例或降低业务／独立验收标准。

未来完成定向和Team回归：从backend运行
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`，
变更Python Ruff及GitNexus／聚焦调用点检查。本轮未运行上述测试。限Team／文档无
应用服务重启需求；若实际diff需进入backend／frontend，先说明范围变化，执行仓库
必需全量测试与重启，不静默扩项。

## 9. 文档自查与剩余边界

需求F1—F6、决策D1—D7、设计§2—§8和A1—A7已对齐，检查本地链接／锚点、编号、
围栏、diff及仅本次路径。未改代码、旧运行证据、provider配置或暂停授权，未运行
产品测试、重启或外部请求。无未决关键选择，日志字段对齐不重新打开业务边界。
独立设计审阅、工程功能、真实对账及优化效果均未执行；成本统计不是语义质量证据。
