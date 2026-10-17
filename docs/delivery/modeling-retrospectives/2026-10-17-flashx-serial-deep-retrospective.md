# 2026-10-17 FlashX 串行三轮深入复盘

本次范围为最近完成的 `r4326-20261017-serial-flashx-{low,high,max}-round{1,2,3}`，
不是此前 flashx-low-b 三轮。先读[优化台账](optimization-tracker.md)、关联权威需求及
[批次简短记录](2026-10-17-flashx-serial-efforts.md)，再核对原始报告、运行事件、
实际角色配置与原生数值回执。未启动模型、修模、重验、平台写入或服务重启。

结论：三轮在同一最小安装链上均有完整四题独立非盲回归通过；当前主要问题是流程
状态解释与 Delivery 输入成本。提高 effort 没有在本样本显示额外质量收益，也没有
消除流程误判。当前场景不足以检验复杂建模能力，不能将三次通过外推为完整业务通过。

## 1 关联需求与旧优化复核

| 需求／优化 | 本次实际证据 | 验证结论及缺口 |
| --- | --- | --- |
| R4.3-026 | 三个独立新 scope，公开1/1、隐藏3/3分别通过；两概念、一条有向关系，revision2 | 有界语义回归通过，整体仍部分验证；low三处、max两处宿主阶段纠偏；旧小链／完整业务未覆盖 |
| R4.3-024／025 | 三轮各两批成功创建并实际治理读取；high一次字段校验失败未写入，约9秒后自行正确提交 | 原子应用及技术自修有正证据；语义自查发现错误后的实质修模、其他变更操作仍未覆盖 |
| R4.3-029 | 宿主CQ审核与Delivery技术推进分工实际采用；high无阶段纠偏；low／max有反例 | 部分验证；平台实际部署修复、语义失败分层诊断与全任务净成本仍待证 |
| R4.3-022／005 | 各轮产生70／91／79个decision packet；原生线程实际收到81／104／96条host_observation（含分页） | 输入减量尚未闭环；重复完整状态和非决策事件残留，022效果状态改为待调整；计数不等于模型调用或可删除次数 |
| R4.3-019 | 用既有离线工具汇总18个原生线程与12个Consumer快照；原生逐response去重和终态累计逐字段一致 | 部分数值可复算；Consumer终态、Host及供应商账单未闭合，仍部分验证 |
| R4.3-020 | 三Delivery实际窗口516800；九个生产线程实际258400并有fallback metadata警告 | 保留Delivery局部生效；生产侧配置缺口仍存在，未发生生产压缩，不能证明扩大其窗口会改善本任务 |
| RETRO-20261017-01／02、R4.3-013 | 三轮一个实际slice，空cross-slice未引出假缺口；短内联交接采用，但max误读兄弟角色路径 | 01追加局部正证据；02／013仍待实测，接收方材料合同及净成本未闭合 |
| R4.3-015／028、RETRO-20261013-09 | 单切片新建，无增量旧模型感知、阶段早反馈或原限定遗漏反例复测 | 未触发，不因本批通过关闭，也不判新失败 |
| R4.3-021 | 三轮各一次真实压缩、缓存输入均为0 | 沿用用户暂缓决定；新数值不自动授权重启压缩器设计或实现 |

适用需求为 [v4.3](../../requirements/requirements-v4.3.md)。工程、独立功能验收、实际
采用与独立语义裁决分别保留；本次复盘核验已有裁决资格，不另作一次独立验收。

## 2 质量、轮次与时间

| effort | 首次apply | 两批完成 | Modeling终态 | handoff | 完整验收 | 宿主阶段纠偏 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| low | 3:18 | 3:39 | 4:33 | 6:41 | 10:01 | 3处 |
| high | 5:59 | 6:35 | 7:55 | 8:43 | 11:27 | 无；宿主CQ审核及只读key准备仍存在 |
| max | 5:11 | 5:29 | 7:06 | 9:19 | 11:35 | 2处 |

表中为各轮semantic-start后的跨度，非有效语义工时；完整验收取Runner
`cq-acceptance-complete.jsonl`，不是第一份报告到达。批次授权07:31:56Z，首轮
07:32:05Z启动；末轮08:07:35Z完成验收，批次08:09:28Z收口，登记至收口约37分32秒。
每轮初建一次、fresh semantic-start一次，无实质修模，三轮额度全部用尽。
轮间修提示和核对也保留在批次墙钟内；原用户消息至登记的更早时间未知。

六份原始 `acceptance-v3/**/batch-report.json` 均核对：每轮公开1题与隐藏3题同freeze／
model binding，执行分母完整，`full_pass=true`，无drift／unavailable；Runner完成
回执pass。原件资格均为 **non-blind-regression**，不是严格盲测。本次不将隐藏答案
或评分细节整理进生产输入。独立成员未参加生产创建／修复，资格边界沿原批次记录。

从两批完成到验收仍需约6:22／4:52／6:07，但包含必要读取、自查、生产收口及独立
Consumer／Judge，不能全部认定为浪费。只有low和max的具体等待误判有宿主纠偏证据。
有效语义时间占比unknown，不从阶段跨度反推“语义不足一半”。

## 3 新补齐的用量证据

复用 `python -m modeling_team.usage_report`，显式scope及独立JSON／Markdown报告位于
`workspaces/flashx-serial-retrospective-20261017/{low,high,max}-scope.json`、
`{low,high,max}-report/`；18线程逐响应与终态累计核对、源hash另存
`native-statistics.json`。未修改原生回执或语义报告，压缩按真实
`compaction_response_id`绑定，作为总量子集，未重复相加。

| effort | 已知样本输入 | 样本未缓存输入 | Delivery输入／占样本 | Delivery未缓存 | 其中压缩未缓存／占Delivery未缓存 |
| --- | ---: | ---: | ---: | ---: | ---: |
| low | 11,789,582 | 1,114,510 | 9,640,001／81.8% | 808,129 | 483,766／59.9% |
| high | 12,985,447 | 1,108,967 | 8,787,754／67.7% | 713,258 | 486,381／68.2% |
| max | 11,636,260 | 1,025,828 | 8,065,139／69.3% | 731,571 | 484,823／66.3% |

样本含生产三角色、Delivery、两个Judge及四个Consumer的现存数值快照。Consumer
快照仍非终态，Host未分摊、账单未提供，故上述**不是完整任务成本或最终账单**；
占比仅针对当前已知样本，补齐缺项后会变化。缓存输入不等于免费，费用unknown。
原生回执内所有已核线程response求和与最终累计一致，未发现计数下降；工具保留缺
累计基线等限制，未把累计通知与response相加。压缩占样本未缓存输入43.4%—47.3%。

Delivery各一次压缩，其余已取得原生记录的生产与Judge线程均无压缩。Delivery实际
收到81／104／96条host_observation，共约131／183／173万字符；对应模型响应
38／29／28个（含压缩）。消息、分页、turn、响应及请求attempt是不同计数。

Modeling输入为815,426／1,931,599／2,016,775，输出7,597／17,230／19,418，
其中推理2,703／6,078／9,073。更高档在本样本产生更多建模推理，但四题质量相同；
轮间提示、宿主介入、provider波动及动作不同，不能据此建立纯effort性价比排名。

## 4 逐项定位

### F1 Delivery职责已变窄，输入仍持续积累（部分定位，把握高／中）

- **观察**：三轮Delivery仍占已知样本输入68%—82%，每轮一次约48.5万未缓存输入的
  压缩。high即使没有宿主阶段纠偏，仍有104条观察输入、一次压缩。
- **原件与责任面**：Delivery原生rollout中的user `host_observation`及对应
  `session-events.jsonl`；`modeling_team/delivery.py::record_observation`在决策摘要
  变化时保存完整当前投影，`_model_observation`继续发送当前runs、operations和
  host_actions等集合；后期Host历史集合约5KB、run集合约9—11KB，消息总长可约30KB。
  超32KB后分页又增加消息。单条长度有界不等于整轮上下文有界。
- **另一个已定位残留**：`_is_decision_event_noise`未排除无错误的MCP starting／ready、
  remoteControl disabled等事件；三轮实际决策packet均含32条MCP启动状态、9条remote
  control状态。这些非决策状态仍进入fingerprint链和LLM输入。警告与真实错误需逐种
  判断，不能将所有warning／provider error一律过滤。
- **影响与限制**：持续当前状态复制、事件输入和最终压缩的机制成立；尚未以同条件
  对照分离各机制的净贡献，不能声称所有观察可删除或约48.5万输入可全部节省。历史
  普通provider事件过滤的修复仍有效，这里是剩余路径，不据此宣布旧修复完全无效。
- **最小建议**：沿022／029，仅缩减已证实无动作的成功启动状态与不变历史字段；
  新变化、首阻塞、授权、未知写入、必要存活及当前准确引用保留。先用保留packet核对
  决策信息完整性，再在后续获准任务观察压缩／总量／质量。不恢复暂缓的021，不新建
  监控平台。022由待实测改为待调整；具体方案未获用户确认，本次不实施。

### F2 handoff回执含义不准确，诱发授权与终态误判（已定位，把握高）

- high一次、max两次过早交接被拒；原件为各run的`evidence/outer-input-receipts.jsonl`
  及Delivery `session-events.jsonl`保留的对应请求结果。high随后自行重试成功；max经宿主
  说明后才成功，Modeling终态08:03:06Z、Coordinator接受08:03:47Z、handoff08:05:18Z。
- `TeamRunner._handle_cq_handoff_complete`的`pending_agents`分支返回
  `cq_batch_scope_unauthorized`，实际detail/retry却是等待生产角色报告。通用外层
  next_action又提示修binding，与真实缺口不一致；`delivery_binding`不决定readiness。
- 第一层为platform-contract反馈歧义，叠加collaboration/routing解释错误；保留生产
  收口校验有必要，它保护写入完整性。拒绝本身可恢复，应修准确反馈而不是删除校验。
- 当前`57ab8c4`已补Delivery提示，未更改平台错误码；当轮通过指导恢复不等于新提示
  自主生效。建议最小修回执的code／next_action，准确表达等待角色及新request_id
  重试条件；需沿原接口检查调用方兼容，之后用原分支确定性复测及获准运行验证。

### F3 low过早冻结与误以为handoff自动启动验收（已定位；已有修正）

第一冻结07:33:36Z hidden=0，但Host结果已明确`selected_scope_complete=false`；
Delivery把请求completed／无当前待审题误当全流程完成。宿主在不可变handoff前拦住，
07:34:33Z同run完整冻结。另有等待run先terminal、等待不存在evaluation operation两处
误判。首层collaboration/routing、修改面prompt-contract；`ef5f6b9`已修实际说明。
high实际读Host结果字段、完整冻结、主动回告及启动验收，支持该纠正本次局部生效；
max又发生F2，故不以一次high自主推进关闭029。没有证据支持固定隐藏题数量硬门。

### F4 max把Coordinator本地路径当成接收方挂载（已定位；已修待新会话）

07:58:08Z issue-1请求补挂`/agent/work/scenario-map/`，实际Coordinator已完整内联
获准任务／scope／source／topology／slice。`CodexRuntimeAdapter`的Coordinator地图
绑定仅给该角色，接收方visibility probe印证其不可见；这是正确隔离下的交接误读，
不是缺挂载的平台故障。宿主沿原issue指导、07:59:35Z恢复，08:00:51Z Modeling确认。
首层collaboration/routing；`d41174f`已补两角色实际说明。应按需发布recipient-specific
材料，不扩大共享目录权限；原线程未热加载，新提示采用仍待验证。

### F5 high字段格式错误自行恢复，证明可恢复校验有用（已定位，把握高）

07:49:35Z intent1 `validation_failed`，workspace_before_version=0；07:49:44Z
intent2 applied，后续intent3 applied。原件`evidence/staged-decisions.jsonl`及同
response_digest的回执。未发生不确定写入或平台报废，约9秒技术自修，不算实质修模。
它保护真实写入边界且允许继续，应保留；一次小成本纠错不支持新增审批或重写编排。

### F6 max CQ限流因无通信边不能issue升级，保留Host恢复（已定位，把握高）

`provider-wait.jsonl`有111条`issue-report-unavailable`，不是111次模型请求或新事故。
`_report_provider_wait_issue`循环尝试Broker报告；`transport_mcp.py::report_issue`要求
reporter→coordinator边，而本批冻结Profile只有coordinator↔modeling，无CQ→coordinator。
Coordinator自身限流也只能Host恢复。07:56:45Z原provider_wait经Host恢复后继续，无
新start、无语义质量损失。第一失败层runtime/infrastructure（provider限流），其次
collaboration/routing（该report通路不适用）。Host恢复可用，不应扩大隐藏角色通信
权限来消除报错。111条重复日志及其决策输入有降噪空间，优先级低于F1/F2；不量化节时。

三轮另有37／61／47条`responseStreamDisconnected, will_retry=true`通知；这些是保留
通知条数，不代表唯一外部请求失败数或三轮死因。现有重试后取得终局，未发现由此
报废run；供应商内部原因及准确关键路径损失unknown，不继续扩大为供应商审计。

## 5 下一步优先级及本次边界

1. **先解决F1的剩余输入路径**：它在无阶段纠偏的high仍存在，和已确认022／029目标
   直接相关。减少不变历史与已知无动作事件优先于改压缩器；收益方向可信，分钟／费用
   尚不可量化。任何删减须保留实际决策变化、必要存活和证据定位，出现漏阻塞即撤回窄修。
2. **F2优先改平台反馈含义**：提示已打补丁，重复要求Agent解释误导错误码会继续产生
   兜底成本；保留原生产收口守卫及兼容性检查。F3／F4先验证已修实际说明，不重复建设。
3. **后续获准验证优先切回既有较大场景**：最小链继续用于流程回归；仅靠两概念一关系
   无法区分复杂语义、自查修模或028增量感知能力。不新增固定A/B次数，不降低原评分，
   不因本次low较快就全局降档，也不因max推理更多就默认升档。

本次补齐关联验证记录与既有台账，未新增未经确认的优化编号或改动生产合同。019保持
部分验证；022实际效果待调整；026、029及其他旧项保留原适用局部通过和剩余缺口。
原材料／冻结／报告／裁决只读；无生产或修模余额，不为验证建议追加运行。

## 6 用户追问：Delivery token主要完成了什么任务

本次追加只分析同三轮Delivery原生记录，未读取或推算其他会话费用。逐个唯一
`response_id`取usage，以该响应实际发出的工具调用划分；多任务响应不拆成虚构的
单任务费用。压缩按`compaction_response_id`识别，三类互斥且合计等于线程终态累计。
可复算脚本与数值原件在宿主私有目录
`workspaces/flashx-serial-retrospective-20261017/followup/`的
`analyze_delivery_tasks.py`、`delivery-task-attribution.json`，含源hash和逐响应归属。

| 实际处理内容 | 响应数 | 三轮输入／占Delivery全部输入 | 未缓存输入／占Delivery全部未缓存 |
| --- | ---: | ---: | ---: |
| 状态解读、等待、文字报告，无控制动作 | 48 | 15,073,895／56.9% | 388,455／17.2% |
| 流程控制及必要证据补读 | 44 | 9,964,029／37.6% | 409,533／18.2% |
| 上下文压缩，形成后续接续摘要 | 3 | 1,454,970／5.5% | 1,454,970／64.6% |
| 合计 | 95 | 26,492,894 | 2,252,958 |

“无控制动作”允许仅调用`emit_user_message`发布文字消息；其余此类响应无工具调用。
输入包含每次请求复用的长历史及工具／状态上下文，**不是独占该任务的新文本量**，
也不能反推每个token具体执行了什么推理。三轮合计输出73,965，其中推理47,656已包含
在输出内；主要输入量随多轮状态判断重复携带上下文，未缓存输入的最大单项是压缩。
缓存输入仍有供应商计费语义，缺账单及价格绑定，不把上述比例叫费用占比。

流程控制具体在做：

| 任务 | 三轮实际动作 | 行为与边界 |
| --- | --- | --- |
| 启动、目标与授权传达 | start_run 3次；submit_instruction共6次（含冻结回告） | 启动三组、传初建余额及冻结事实；max额外尝试读取宿主私有授权资料后按启动包继续 |
| CQ阶段组织 | request_host_action 6次；freeze_cq 4次 | 请Host分别审核全景／切片、核对阶段回执并冻结；low一次过早冻结后补完整池，因此比三轮多1次冻结；Delivery未承担实际CQ语义审核 |
| 故障处理 | resolve_issue 3次；recover_provider 2次 | low/high各处理Modeling限流，max恢复CQ／Coordinator限流，并处理路径可见性误报 |
| 生产交接就绪判断 | complete_cq_handoff 6次 | low/high/max分别1／2／3次；high/max共3次过早交接；准确回执修复见下方记录 |
| 独立验收组织 | start_evaluation 6次；complete_cq_acceptance 3次 | 各轮分别启动公开／隐藏组、等待真实报告、核对分母和绑定、完成回执；Consumer作答与Judge评分由独立线程完成，不计作Delivery的语义工作 |
| 补读、核对与收尾 | read_delivery_artifact 10次；get_run_status 3次、get_run_events 1次；finish_delivery 3次 | 读Host技术字段、issue、请求账本，核对待命与封口；high收尾连续两次引用身份失效后改读小账本，再查状态 |
| 对外汇报 | emit_user_message 7次，另有普通assistant文字回复 | 进度／结果发布；含于相应响应用量，不另加一份费用 |

无控制动作响应的典型任务为：“第二批写入已发生，继续观察”“没有新阻塞，等待
Coordinator报告”“某Consumer完成，等待Judge报告”。low还重复等待run先terminal；
max两次handoff拒绝后反复核对授权和freeze绑定；high没有宿主阶段纠偏，仍产生13个
状态／文字响应与一次压缩。必要异常观察仍有价值，不能将48个响应全部判为可删除。

本轮另看到low/high收尾围绕`request_id=null`的standby／acceptance记录补查；high在
账本不断追加时两次引用身份失效，随后换读取方式恢复。原件为Delivery原生工具调用与
对应输出，原因在于读取整文件身份随追加变化，不等于请求执行失败；额外补读可以
解释局部成本，不足以量化其对压缩触发或总墙钟的独立贡献。本次只分析，不修改这些
收尾路径，也不将其误归为handoff错误码修复范围。

因此，022的下一步应针对实际无变化输入和重复历史携带；保留必要阻塞观察、授权、
未知写入与正式验收动作。用户本次仅授权实施F2，F1仍为分析／待调整，021继续暂缓。
F2修复及测试见[交接等待回执修复记录](../records/2026-10-17-cq-handoff-pending-feedback-fix.md)。
