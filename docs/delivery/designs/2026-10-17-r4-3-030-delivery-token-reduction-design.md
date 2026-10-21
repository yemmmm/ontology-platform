# R4.3-030 Delivery 按需决策与有界上下文设计

## 1. 范围、事实与目标

权威范围为[R4.3-030](../../requirements/requirements-v4.3.md#r4-3-030)，实质决策主表在
该条。源码基线为`e3a7cb7d8df9f4ca0abcd53f5da70a0e3ff7dfaf`；本轮授权是需求细化、
设计及独立设计审阅，不包含实现、外部模型调用、建模、修模或真实验收。工作区已有
029设计、复盘、README、需求其他条目和演示材料改动，均不属于本轮。

例子：Delivery已决定等待当前CQ宿主审核。此后数分钟只有正常心跳，不必反复查询
状态并解释“继续等待”。程序仍持续观察；审核真实回执到达后，只给当前review绑定、
审核范围是否完成、下一阶段及必要引用，Delivery据此继续。若同时撤回授权或出现
未知写入，立即进入原处理通道，不能等审核完成才送达。审核内容仍由获准宿主负责。

最近DeepSeek最小链的Delivery有21,598,944输入token、102个唯一响应，见
[现有复盘](../modeling-retrospectives/2026-10-17-deepseek-high-usage-retrospective.md)。
它是瓶颈定位依据，不是同条件对照，也不能把其中30次状态查询全部视为可删除。
022的240个保留packet仅证实输入字节减少19.23%，不能当本需求token效果基线。

| 实际入口 | 当前能力与缺口 | 本条最小差异 |
| --- | --- | --- |
| `delivery.py::_run_delivery` | busy／idle均有约2秒程序观察；按变化steer／send，模型可在长线程中继续主动查询 | 明确交回等待的合同；等待不靠模型循环；不新增监督进程 |
| `record_observation`、`_model_observation`、`_dispatch_observation` | 完整原件、变化包、pending队列、送达记录及分页已存在；默认包仍展开完整当前snapshot | v2只呈现决策核心、实际变化及必要未决状态，沿原队列送达 |
| `DeliverySession.call_tool`、`observe` | 主动get类读取默认直接返回Host全量结果；内部观察也调用同一入口 | 仅Delivery模型侧改简明默认；程序保留原始Host结果，不能用简明结果反过来作观察源 |
| `_restore_decision_inputs`、session journal、conversation、Host请求账本 | 可恢复待送输入、原用户消息、请求和实际回执；缺有效计划／理由的明确持久承接 | 在原journal记录小型等待／接续说明；实际事实仍从原账本重建 |
| `runtimes/delivery.py::start/send/steer/_handle` | 一个app-server进程启动一个native线程；usage以实际thread标识采集 | F3仅在选定边界启动新线程；同一Delivery session／监督进程保留 |
| Host `freeze_cq`、`submit_instruction`、`complete_cq_handoff`及`delivery_ops.start_evaluation` | 审核、冻结、交接、验收启动及请求回执均已有；机械跟进仍经多次模型调用 | F4仅增加两个具体连续动作入口，内部复用原调用及权限 |
| `usage_capture.py`、`usage_report.py` | 已能归属多个真实线程及逐response去重，压缩计入总量子集 | 补线程切换绑定及全任务scope，复用019报告，不另造计量服务 |

上述为定向源码与调用点核对，不声明GitNexus图覆盖。只做文档设计不改变调用关系；
实施时再对跨模块实际变更做impact／detect_changes或有依据的调用点替代检查。

先交付F1＋F2；依据其真实结果再启用F3，F4按明确操作逐项实现。后两项的可靠承接与
操作边界在本设计确定，不要求第一批一起建设，不以大场景、费用对账或后两项效果
作为F1＋F2工程交付前置门。020窗口配置不变，021仍暂缓，模型／effort不降档。

## 2. F1：把等待交还现有程序

### 2.1 一次决定、持续观察

增加一个Delivery本地工具`yield_delivery`，用途仅为记录“当前没有可立即执行的新决定，
等待哪些已绑定事实”，随后结束当前模型turn。它不阻塞Python事件循环、不sleep、
不关闭native线程、不暂停生产，也不提交任何平台写入。字段是本地合同，不新增Host API：

| 字段 | 含义 |
| --- | --- |
| `input_id` | 作出决定依据的已读输入；主动补读时可附原工具结果引用 |
| `phase` | 当前交付阶段说明；不是平台合法流程枚举 |
| `waiting_for` | 等待对象的run／request／operation／Host request身份及所需结果说明；可多个 |
| `next_action`、`reason` | 获准下一步及为何暂时不能做；程序不解释自然语言为执行命令 |
| `active_decisions` | 仍有效的计划／约束／理由及原消息或证据引用；变更显式指向被替代记录 |

工具校验身份属于当前session及必要字段，追加原`session-events.jsonl`并返回简短
`waiting_recorded`及`end_current_turn`提示。模型在取得回执后直接结束turn，不再调用
状态工具确认同一等待。`turn/completed`才证明本次推理已经结束，工具成功本身不证明。
不引入“工具返回自动终止turn”的未验证原生API，也不靠强制interrupt或次数硬门实现。
若真实模型仍继续轮询，F1行为验收不通过，按prompt-contract纠正实际instructions／skill；
不能只凭新增工具或提示出现关键字判通过。允许不需要持久说明的普通turn自然结束。

`yield_delivery`是建议接续记录，不是唤醒白名单或新授权。程序始终按005／029原规则
观察所有绑定run、operation、Host待办、请求结果和用户输入，不只盯`waiting_for`。
当前轮的普通无变化观察只更新原件；等待记录自身的落盘不制造一次决策变化。
已有未投递的真实事件继续送达，不能因刚登记等待而清空队列或改成“全部已读”。

### 2.2 唤醒与异常

| 情形 | 行为 |
| --- | --- |
| 同一等待、已知正常心跳／日志增长 | 不启动turn；不重复发送“继续等待”；保留程序观察 |
| 当前需要的实际结果、就绪条件或版本／绑定改变 | 送达有正文的必要变化；模型决定下一步，或由已经明确授权的F4动作继续 |
| 新问题、首阻塞、失败、unknown、损坏或未知事件 | 沿原输入通路送达准确事实与引用；不因未列入waiting_for而忽略 |
| 用户消息、暂停／继续、取消／撤回预算／停止 | 原来源、顺序及优先级不变；按已有合作暂停或撤权／停止合同处理 |
| Provider失败、进程退出、输入通道断开、必要超时异常 | 保留第一失败层及supervision_interrupted；不得标完成或静默永久等候 |

观察频率沿用当前约2秒调度，不通过延长轮询间隔换token。异常在下次可用观察或输入
派发时处理，不叠加额外等待计时器；已有超时／存活检查继续使用。原观察循环还须按
已有明确的任务deadline、授权有效期或操作timeout计算一次“到期”状态变化并唤醒，
否则只有时钟前进、Host状态不变时不会被原digest识别。到期状态及是否已送达留在原
journal，不能每2秒重复唤醒；不能从普通心跳或未设置期限的等待臆造超时。到期仍
没有结果时只报告真实未完成及可恢复下一步，不能解释为批准或自动重发写入。

保留busy steer与idle send，用户控制优先；不为“结束推理”等到所有生产Agent停机。
保留stdin及启用时的ConversationServer真实输入通路。无server且stdin EOF的既有
supervision_interrupted不能被优化吞掉，验收须覆盖该已发生过的启动错误。

## 3. F2：当前决策的最小充分输入

### 3.1 展示合同

新的模型输入使用`delivery-decision-input/v2`，Host原始snapshot、事件及journal留存
方式不变。v2改变展示含义，不能仍声称是v1完整snapshot。以下为字段设计，不是现成工具响应：

```json
{
  "schema_version": "delivery-decision-input/v2",
  "input_id": "decision-42",
  "mode": "changes",
  "core": {
    "session_id": "delivery-A",
    "phase": "cq_review",
    "authorization_reference": "existing-authorization",
    "control_state": "active"
  },
  "unresolved": [{"kind": "cq_stage", "stage": "slice-review", "status": "pending"}],
  "changes": [{"kind": "host_result", "request_id": "review-A", "status": "completed",
               "review_complete": true, "selected_scope_complete": false,
               "remaining_stage": "slice-review"}],
  "evidence": {"path": "bound-session-journal", "source_ref": {}, "selection": {}},
  "coverage": {"complete": true, "omitted_sections": ["settled_history"]}
}
```

示例省略真实绑定及coverage细项，实施／验收不得使用这些占位值提交。`completed`
只表示宿主请求结束；示例仍有slice-review，不能据此冻结部分题池。

- `core`始终含目标／当前阶段、session及实际run身份、有效授权／控制、原任务起点与
  额度引用、首阻塞、必要freeze／model／report绑定。没有确切余额时保留unknown及
  权威记录引用，不从production_start_limit推导剩余修模轮次，不新增平台轮次门。
- `unresolved`保留所有当前未决／未知对象的紧凑身份、状态和定位，稳定正文不重复。
  新增／改变的未决事项、拒绝理由、错误和结果绑定在`changes`给当前决定所需正文；
  移除项给原身份及已知解决依据，不能只发“集合长度变了”或一个哈希。
- 第一次输入、native新线程或恢复时用`mode=bootstrap`，从最新事实提供完整当前核心
  和未决项的必要正文。正常变化包不重发不变run快照、settled集合和已读报告正文。
  首次启动也不再直接把整个config给模型；必要目标、已选task／profile／scope、模型
  与执行约束按明确字段提供，Host路径／凭据／隐藏正文不随便进入模型。
- 所有被省略的集合给总数、返回范围、完整性及精确原件读取位置；`complete`只指本次
  声明的决策投影／页已完整，不表示全源或业务任务完整。大变化给可读的必要短事实和
  引用；决定依赖的正文超量则显式分页，不能仅剩引用却声称已经充分。
- 复用022当前展示上限与分页实现：输出不超过32,000 UTF-8 bytes的既有实现边界，
  超量按页交付；原件选择读取默认／最大16,384 bytes。它们是展示预算，不是语义范围
  或累计线程token上限。不能对长控制文本、错误或大量未决项静默截断。

这里只按已知技术字段作投影；未知技术事件仍给类型、准确定位及当前异常／待处理信息，
不得通过扫描业务自然语言来猜语义完成。029的私有CQ／隐藏Judge正文与引用隔离保持。

### 3.2 主动查询与事实来源

`get_run_status`、`get_pending_actions`、`get_evaluation_status`及`get_request_result`
在Delivery模型侧默认用同一简明投影：必要状态、当前对象／绑定、首错误／下一步、
原件引用与coverage。该变化不修改底层Host工具供其他调用者使用的原合同。
`get_run_events`继续使用既有增量游标及获准事件投影；原件读取继续按selection补查。

在`call_tool`的共同调用路径上区分**内部原始结果**与**模型返回展示**：`observe`、
F4步骤判据、权限检查、`request_host_action`的当前绑定检查及`finish_delivery`收尾
必须取原始结果。内部选择由Python调用点控制，不接受模型通过工具参数开启内部权限。
先保存原始工具结果的精确journal引用，再生成简明输出；沿原read_delivery_artifact
的session绑定和私有内容限制读取，不新增任意文件读取路径。

返回的紧凑结果是有完整性说明的视图，不能参与Host `_receipt_outcome`等权威判定，
也不能被再次投影为“全部已完成”。未知或损坏的原始字段保留限制，不补默认成功。

### 3.3 顺序、恢复与旧记录

继续使用原pending输入队列及`delivery_input_dispatch` attempted／accepted／rejected／
unknown记录。观察变化不等于模型已经收到；只有原生send／steer成功确认的页推进
送达位置。输入页重发只重发事实，不能重放平台动作。2026-10-21用户授权修复恢复积压后，
允许将已知尚未送达的观察合并为当前bootstrap，完整携带未送变化、事件及请求回执，
并追加原input_id与新身份的合并记录；不新增消息总线或另一套ack协议。

每份包保留其input_id、观察身份及完整原始snapshot引用。多个包积压时保留较新
`current_state`定位；依赖可变状态的动作须核对最新绑定与授权，旧包不覆盖新控制。
新线程／恢复用最新bootstrap；合并只涵盖未尝试或已明确拒绝／预算延后的输入。
部分确认的分页、unknown／在途输入保留原身份、偏移及送达边界，conversation消息确认
不受影响；必要用户消息仍按原通路交付。旧事件
明确标历史事实，已完成效果从请求账本认领，不按事件数量重复操作。

旧v1 journal与原input_id不改写；读取时由新展示函数转换其事实，声明v2及原件版本。
缺少可靠当前状态时重新observe并给bootstrap，旧未决送达／未知状态仍保留。不能把
清空native历史等同清空Host待办。旧运行不热切换，历史记录的语义和验证结论不变。

## 4. F3：阶段短线程及接续

### 4.1 启用与边界

第一批默认不切线程。F1＋F2可比实测后，如果仍有已完成阶段历史反复进入后续输入、
上下文继续增长或压缩成本显著的证据，再选择以下自然边界启用；不设置固定token数或
每阶段必换，不用预计收益代替实际交接成本。

1. CQ全部选定范围已审核／冻结，公开确认已实际交付，正式生产已被确认开始之后。
2. 生产证据与写入状态已结清，交接实际成功，所选独立验收操作已绑定启动之后。

这两个边界仅是本需求首批支持的可选切换点，不是所有建模必须经历的合法流程。
F3实施时Host配置显式选择其中的边界，缺省关闭；不增加通用策略引擎。

切换需要旧native turn已经完成、没有正在执行的Delivery工具或F4连续动作，并能
确认当前写入及已提交动作归属。未知写入、未知提交回执、未交付用户控制或不完整
承接时延后切换，继续原线程核对；不能让“无法换线程”阻断原run或重启生产。
已经明确启动且只读执行中的验收可以跨线程观察，不必等验收进程退出。

### 4.2 承接来源

| 承接内容 | 权威来源及规则 |
| --- | --- |
| 原任务目标、完整范围、起点、deadline、获准模型／操作、轮次记录 | 既有配置、授权／效率记录及用户来源消息；保留原身份，不重新begin_round或增加额度 |
| 最新用户要求及仍有效的先前约束 | conversation原消息；不能只取“最后一条消息”。Delivery在yield记录有效引用及明确替代关系，原文可按权限读回 |
| 仍有效的计划、等待对象、决策理由与尚待回答问题 | 最新yield记录加原问题／答复来源；程序不能从日志自动推断业务计划。缺理由时可在旧线程补一份有界接续，成本计入 |
| run、operation、freeze、scope、report／model身份，应用／未知写入状态 | 最新实际Host读取、请求账本和原回执；模型摘要不能覆盖这些事实 |
| 在途动作、未投递输入、Host请求结果和未决用户控制 | 原journal、conversation dispatch和Host账本；接受、已送达、已消费、实际应用分别保留 |

若无法证明某早先约束已被替代，保留原引用及必要正文，不靠模型摘要自行删掉。
需补读的历史仍走原权限／selection，不能把整份历史作为新的默认前缀。确有大量
有效约束时允许分页及补读，不许为追求“小线程”丢失约束。

### 4.3 native线程替换与计量

在同一DeliverySession及app-server内抽取现有`thread/start`创建步骤，建立新native
线程；不销毁监督进程、ConversationServer、provider会话、生产run或验收operation。
新线程使用相同model／effort、工具边界、适用instructions及窗口配置，第一轮接收
bootstrap和承接内容。只启动一个当前可执行决策的线程；不让新旧Delivery同时提交动作。

原journal追加`from_thread_id`、`to_thread_id`、阶段、原因、承接引用和起止时间；
session记录当前线程，保留历史线程绑定。新线程创建已确认、但尚未启动推理前才
切换active绑定；创建失败则继续旧线程。创建响应未知且未发送turn/start时，保留
失败事实，不猜thread_id，不向未知线程发送动作。首轮输入回执未知时沿原unknown
输入恢复／对账，不能再创建一个线程重放相同动作。

`_handle`须按实际thread／turn归属更新busy／完成状态，避免旧线程迟到事件释放新
线程的忙状态。usage事件始终按事件携带的真实thread_id记录，包括旧线程迟到的
末次用量，不用当前active线程覆盖。原生创建／关闭记录与019 scope列出全部线程，
逐response与线程累计只作互核，任务起点与全链费用不因切换重置。

这不是021压缩算法：不总结重写旧rollout，不修改已有压缩阈值。cold start、静态提示
重发、承接、失败尝试与补读全部计入；有界单次切换收益不能冒充长期可重复收益。

## 5. F4：两个明确的机械连续动作

增加Delivery本地`continue_delivery`工具，首批只支持以下两个action；不是可执行任意
工具列表、脚本或条件表达式的通用编排器。原单步Host工具保留，其他工作仍可直接使用。

| action | 模型已确定且必须给出的输入 | 程序连续执行及完成判据 |
| --- | --- | --- |
| `freeze_and_notify` | 本次完整CQ选定范围、当前review／版本绑定、原Coordinator接收方；已核对全部阶段审核完成 | 调原freeze_cq→核对真实freeze及public projection→以delivery_guidance发送公开确认→查询原request_id的实际消费结果；给出结果。仅submitted不能完成 |
| `handoff_and_evaluate` | 当前完整生产handoff readiness及freeze绑定、一个明确选定的获准验收组、选定model_profile／timeout和已有合法参数 | 调原complete_cq_handoff→核对真实成功及返回model_handoff→为该组start_evaluation→核对实际operation启动身份；随后交原程序观察报告，不由程序作语义裁决 |

不自动起草／审核CQ、不根据“无pending”猜完整题池、不从文件存在猜生产就绪，
不自行决定公开／隐藏组或问题分母、不新建修模／fresh run、不调用stop销毁保留成员。
027原每批最多三个CQ题目任务并行保持；普通cq-acceptance不经过checkpoint接续锁，
该锁不能作为本动作的完成判据。一次连续动作只启动一个组，是本次控制实现范围的
选择，不是新增平台全局串行限制。其他获准组保留在任务未决范围，由Delivery按原
任务安排沿start_evaluation推进，不再次complete_cq_handoff；不为本条建设组调度器。
需要先等前组完成时，使用绑定合格报告、work_state=completed及实际题任务结束证据，
不要求保留owner／进程退出。一个组启动或通过均不等于完整分母交付。

工具参数必须带明确`continuation_id`和上述固定操作的原始合法绑定／参数。程序仅把
上一步真实结果中的规定字段传给下一步；不插入新的业务判断或由自然语言生成命令。
freeze／handoff的FIFO提交响应不是结果：用原request_id核对get_request_result，
再读取其consumption_evidence指向的当前冻结／交接证据取得真实freeze／model_handoff
及公开投影。不得从submitted响应补造这些字段，或把Runner消费等同Coordinator已开始。
沿原`call_tool`权限、授权有效期、当前控制及对应Host校验逐步执行；必要字段缺失／
范围改变返回可修正反馈。公开确认只取既有public projection，不能转发私有审核结果。

复用session journal记录每个连续动作及子步骤的实际request／operation身份、提交意图
和回执。每个有副作用步骤先落原身份，再调用；同continuation_id同绑定返回既有进度，
冲突参数返回可定位错误。恢复只认领已证实效果：未知提交先按原账本／资源核对，
不通过生成新ID再次发送。仅本地完成标志不能证明外部步骤成功。

原`_run_delivery`循环驱动短的提交／查询步骤，不在模型工具处理函数中长时间等待。
工具先返回已登记及跟进引用，Delivery随后yield；后续纯机械成功步骤由程序推进，
不会每步唤醒模型。只对**该连续动作拥有的、符合预定判据的普通中间成功回执**暂不
唤醒；原件与输入队列保留，最终给出步骤及真实结果。其他事件仍沿F1及时送达。

遇到拒绝、实际绑定变化、未知结果、超时、新语义选择、授权／用户控制变化时，停止
后续依赖动作并交回最小错误、已执行步骤及未决状态。已知可纠正错误允许原目标继续，
但程序不凭通用重试次数自动重放。用户控制优先于下一步；暂停不强杀正在写入的动作，
未知写入按原合同处理。CQ未就绪等普通反馈不成为run永久失败。

## 6. 效果口径和有界对照

### 6.1 指标与结论

复用019的task／session／run／operation／role／thread／response绑定和离线报告：

- 主指标为Delivery全任务`T_D = Σinput_tokens + Σoutput_tokens`；另列累计input，
  因其是本次已实证的主开销。cached已包含在input，reasoning已包含在output，
  compaction是总量子集。三者都不能再次加进T_D。
- 同时列cached、uncached、output／reasoning、唯一response数、实际压缩次数／token、
  补读调用与可归属token、线程数／切换成本、墙钟、宿主介入及各角色／全任务总量。
  无法把某次补读单独从累计响应分离时标unknown，不用字节估token填空。
- Delivery降耗成立要求同条件完整窗口的T_D下降，且其input下降；无用户指定百分比，
  不虚构20%／50%或固定token上限。报告实际差值和比例，不以缓存率上升替代。
- 全任务token净效果另判：完整可归属总量也须下降才可称净降耗；Host／辅助模型缺数
  则partial，不能把已知小计当总量。金额依019价表／账单证据，缺账单不称费用验证。
- 质量、范围、授权、异常处理和独立验收是必须保持的约束。墙钟或宿主介入增加时
  明列增量与原因：可单列已证的Delivery降耗，不能自动称综合净效率通过；有实质
  时间／介入取舍时提交用户，不预先授权以降耗换长时间停滞。

`input`与T_D的严格下降是当前比较判据，不是统计显著性或未来承诺；单个匹配样本
只证该有界窗口。L2可重复性与较大场景增长另行验证，不成为F1＋F2工程前置门。

### 6.2 比较范围

1. 工程阶段用既有fixture、保留packet和假runtime验证观察／送达／恢复行为，不调用
   provider；机械字节和调用变化只能说明工程机制，不关闭A5／A6。
2. 后续另获授权时，优先一组匹配的R4.3-026最小链前后对照。基线采用F1／F2之前的
   当前代码路径；变更组只开启F1／F2。固定源、Task／Profile、原完整公开1题／隐藏3题
   及评分、所有角色model／effort、窗口、并行、启动方式和宿主职责。两边均用正常
   fresh任务上下文；不把继承失败历史的成功片段当基线。历史跨provider数字仅作参考。
3. 在启动前冻结两组代码／配置及题集身份、正常收尾终点和授权，记录限流／故障／
   Host介入差异；窗口从原任务授权／启动准备开始，经完整验收到必要收尾末次用量。
   若任务失败或未交付，保留截止累计，不删失败成本补一个成功窗口。不能切掉
   验收之后的Delivery压缩或收尾响应；模型动作结束不等于usage已采集完整。
4. F3或F4后续各自启用时以已验证前一配置为基线，不在同一对照同时改模型、窗口、
   021或多个未归因优化。对照失败／不匹配就报告未验证，不自动重复试到下降。
   样本数增加和较大场景测试均按当时有效运行授权，设计不预占三轮或新增轮次。

本设计未创建对照run或scope，不更改保留报告。未来真正执行时复用019 scope与016
优化跟踪，只填实际身份；不另建只匹配一次输出的验收器或全套监控设施。

## 7. 实施交接和验证

| 对应项 | 最小实施位置 | 有意义的验证／反例 |
| --- | --- | --- |
| F1／A1 | delivery.py本地yield、原监督循环；Delivery instructions／skill | 多个无变化观察周期零新模型响应／主动轮询；工具登记不假装turn结束；静止Host跨越明确期限只唤醒一次；待办／用户控制／未知事件／EOF／失败可见；已有pending不被yield清空 |
| F2／A2 | 原投影、call_tool模型边界、原件读取与journal恢复 | 正常增量不重复完整snapshot；主动get与observe原始结果分离；新结果／移除／错误正文完整；超量分页、unknown投递、busy竞态和旧v1恢复不丢事实；CQ私有内容仍隔离 |
| F3／A3 | DeliveryRuntime线程创建／事件归属、session历史绑定 | 阶段切换前后目标／约束／起点／授权／额度不变；旧迟到事件不扰乱新线程；在途／unknown延后；线程创建及首次输入失败不重复生产动作；跨线程usage不漏不重 |
| F4／A4 | Delivery本地两个连续动作及原Host函数调用 | 正常成功无逐步LLM确认；完整审核后冻结并实际通知；handoff成功才启动单个已选组，其他组不遗漏、027每批上限保持；每步撤权／暂停、未知写入、重启、重复／冲突continuation可恢复，已完成效果不重放 |
| F5／A5 | 019采集／scope及已有效率记录 | 主指标、compaction／reasoning不双加；线程及角色成本转移完整；缺账单／usage保持unknown；不匹配基线不能PASS |
| A6 | 原获准场景与独立Consumer／Judge | 同范围／完整分母、源忠实、实际应用／治理读取、必要异常及独立语义无退步；有界结果不覆盖完整工业场景 |

扩展现有`test_delivery_wakeups.py`、`test_delivery_decision_input.py`、
`test_delivery_session.py`、`test_delivery_runtime.py`、`test_delivery_ops.py`、
`test_usage_report.py`及实际prompt／tool合同测试，不重建harness。实施后按实际范围
执行Team测试，涉及backend／frontend时才追加AGENTS对应全量测试及服务重启规则。
同步`docs/reference/mcp.md`、实际Delivery instructions／skill，以及宿主
`skills/modeling-dev-loop`相关接续说明；活跃技能若有validator则执行。

先完成F1＋F2工程验证，再在获准真实对照核对模型确实交回等待和token变化。F3与F4
分项实施、分项验收；某项未启用记未执行，不能把F1＋F2通过写成030整条完成。
独立验收人员不能创建、继续或修复被验收run，也不能改原证据。设计审阅PASS、工程
PASS、实际降耗、有界语义、较大场景增长及L2重复性分别记录。

## 8. 当前状态

需求与详细设计已完成，必要设计选择均已关闭。独立Reviewer首轮及最终澄清复核均
**PASS，0 Critical／0 High，无关键未决假设**。状态同步未改变设计§1—7及需求行为
合同。设计阶段当时无实现、A1—A6执行或真实降耗结论，见
[独立设计审阅记录](../records/2026-10-17-r4-3-030-design-review-record.md)。

2026-10-17后续实现授权下，按§7先交付F1＋F2工程实现与离线验证，见
[首批交付及测试记录](../records/2026-10-17-r4-3-030-f1-f2-delivery-record.md)。
§1的授权边界记录设计阶段事实，不代表后续未获实施授权；§1—7合同保持。
F3／F4尚未实施，真实等待行为、token降耗和独立业务语义未验证；030不整体关闭。
