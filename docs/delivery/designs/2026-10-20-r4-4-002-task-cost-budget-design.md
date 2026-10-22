# R4.4-002 建模任务金额预算与近实时成本控制设计

> 2026-10-22 用户更新：全部新输入及控制入队，目标当前原生 turn/activity 自然结束后
> 再投递，不在忙碌时 steer／interrupt。金额按回合边界近似控制，已开始回合的工具后续
> 和用量回执自然完成，允许并记录尾差；新回合仍沿原预算准入。此最新口径覆盖本文原
> 即时打断／逐请求截断的历史决策，不追加预算或自动恢复已有任务。权威范围见
> [R4.4-002／003](../../requirements/requirements-v4.4.md#r4-4-003)。

- 日期：2026-10-20。
- 权威范围：[R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)，F1—F8、A1—A15。
- 状态：需求／详细设计完成，独立设计Round 1 PASS，0 Critical／0 High，无关键未决
  假设；审阅原件与边界见[审阅记录](../records/2026-10-20-r4-4-002-design-review-record.md)。
  工程、真实预算控制及独立业务语义均未验证。
- 代码基线：`5edfab2`。本轮只修改002需求、设计、审阅记录及文档导航；保留其他在途改动。
- 本轮授权包含设计和独立设计审阅，不含实现、部署、Provider调用、建模／修模、金额
  追加或旧任务恢复。下列新字段、模块和入口均为拟实现合同，不是当前可运行功能。
- D1—D13的决策理由以[需求决策表](../../requirements/requirements-v4.4.md#r4-4-002)为主。

## 1. 当前事实与最小方案

用户授权同一业务目标使用¥10；初建、修模、公开反馈及正式独立验收共同消耗这¥10。
换run、线程或Delivery阶段不能重新得到¥10。程序按真实用量估价，达到额度后请求该
任务各执行方暂停，用户可以看到谁尚未暂停、哪些费用仍在途，明确追加并继续后接续原账。

| 已核对入口 | 当前能力及缺口 | 本条增量 |
| --- | --- | --- |
| `usage_report.py`：`build_report`、`_read_sources`、`_deduplicate`、`_account`、`_account_dsh_native` | 019／034离线归属、来源选择、去重、累计及原生替代；`_costs`要求账单价表定义和窗口 | 抽出两入口共用的数值核算函数；在线仅处理变化来源／受影响会话，另加三档预算估价，不放宽账单判定 |
| `usage_capture.py`：`NumericReceiptWriter`；`dsh_usage.py` | 已有numeric-only原件、字段presence及DSH互斥桶归一化 | 继续写原件；最少附加预算绑定／来源登记和采集异常状态，不另存token主账 |
| `close_statistics.py`：`ActivityRecorder`及成员登记／原生会话绑定 | 真实成员、进程代次、LLM起止、来源和关闭发布 | 在调用发生前把同一真实成员与来源注册给预算；关闭报告仍独立发布 |
| `delivery.py`：`DeliverySession`、`_run_delivery`、`record_observation` | 原业务授权／运行绑定，程序约2秒观察，模型按需唤醒；原生失败后宿主进程可能退出 | 启动模型前初始化预算监视；监视与推理分开，普通数值变化不进入决策指纹；异常退出保留账和待暂停对象 |
| `host_ops.py`：`start_run`、`pause_run`、`resume_live_run` | 已有管理启动、同run控制、请求身份及实际回执 | 透传可信预算绑定，启动前核对额度；复用原暂停信封并保留自动预算来源 |
| `runner.py`：`_relay_flow_message`、`_control_dsh_flow` | Codex由Coordinator协作暂停／确认；DSH冻结实际进程组并关闭新写准入 | 预算暂停复用上述能力；分别记录生产成员控制覆盖，不把Coordinator收到等同全部成员确认 |
| `delivery_ops.py`：`start_evaluation`、`relay_evaluation_message`；`evaluation_owner.py` | 验收owner、当前及保留Consumer／Judge控制、阶段等待和回执 | 公开反馈及正式验收继承同一预算；阶段间也检查预算，暂停不预建Judge |
| `runtimes/delivery.py`、`dsh_delivery.py`、`codex.py`、`dsh.py`、`dsh_acceptance.py` | 各自实际启动／发送／数值采集；DSH Delivery没有生产Adapter的pause方法 | 最小预算准入检查；补Delivery原生进程的暂停／恢复证据，Host监视及控制入口持续在线 |
| `runner.py`、`start_ledger.py`；Delivery与Host活跃指令 | 当前非formal多切片已跳过StartLedger次数门，其他旧路径及文字仍有次数约束 | 仅显式金额模式分支不再检查次数余额，保留计数／基线／授权等非额度事实；旧模式保持 |

选择“原用量主账＋任务预算投影＋既有owner控制”。仅靠Agent自行报数或发消息不能及时
覆盖Delivery自身与隐藏验收；每次循环生成完整019／036报告又有不必要的扫描和关闭依赖。
不新增数据库、独立常驻服务、通用调度器、逐请求预留事务或管理页面。

## 2. 身份、授权和价表

2026-10-21用户调整外部Host统计策略：外部Host消耗仅单列展示，不计入任务金额成本、
费用汇总或预算扣减。离线报告沿真实`role: host`绑定保留`external_host_usage`，从
任务费用估算输入中排除，即使具备匹配价表也不生成任务费用项或金额缺测项。
原始数值、历史报告及独立账单对账记录保留，其他角色和未接线辅助成本沿原范围处理。

### 2.1 一个目标绑定一份预算

原Delivery配置增加可选`resource_authorization.mode=amount`及`budget_ref`；省略时保持
历史次数模式。预算对象包含：

| 字段 | 约束 |
| --- | --- |
| `budget_id / task_ref` | Host生成的稳定身份；原业务目标／来源／操作范围引用原授权，不从run目录猜测 |
| `authorization_reference / currency / amount` | 真实用户授权引用、单币种及十进制金额字符串；默认CNY，有限非负，零即耗尽 |
| `allowed_bindings / allowed_operations` | 沿原授权的provider／接入路由／模型／操作；金额不能扩权，修复或辅助模型只在原授权内接入 |
| `price_snapshot / price_version` | 每个获准绑定的三档单价、单位1,000,000、币种及用户配置来源；不含凭据 |
| `origin_session_ref / bound_owners` | 原Delivery业务session及其后真实接续session、run、operation、成员来源登记 |
| `authorization_events` | 初始额度、追加、撤回及继续的稳定请求身份、来源和时间；历史消耗不归零 |

首版预算目录置于`<origin-delivery-session>/cost-budget/`，属于已有Host私有证据目录。
后续session通过`budget_ref`引用原对象，不复制余额。Host登记接续后才能换监督owner；
同机同预算仅一个在线数值监视owner，沿现有文件锁约定避免两个接续进程同时接管。
新建run／独立验收的Host入口在启动前固定预算绑定；新成员从其owner继承，Agent参数不能
改写。历史运行不自动加入，用户须明确新金额、目标与接入起点；已有累计的基线另存，不能
把接入前消耗误算或悄悄删去。不能拆分的共享会话拒绝作为完整预算来源，保留原件待核对。

拟在原`modeling_team` Host CLI下增加`task-budget create/add/show`；原`authorize-budget`
继续表示历史`additional-starts`，不复用同名参数偷换含义。创建／追加读取Host提供的完整
结构化文件和用户授权引用；不让Delivery模型或测试业务代答人直接调用授权写入口。追加
使用`authorization_id`去重，同身份异内容返回可定位冲突；`continue_authorized`须引用
用户明确继续指令。自然语言“预算好像够了”、业务代答、读统计均不能增加权限。

### 2.2 自定义三档价表

任务第一次调用之前冻结所有计划使用绑定；选择器精确包含provider／接入路由和实际模型，
不存在通配兜底。配置允许显式零；NaN、Infinity、负数、缺价、币种混用或重复匹配给
`budget_config_invalid / budget_price_missing / budget_currency_mismatch`可修正反馈。
模型返回的实际绑定与计划不符时，保留已发生费用／缺口并暂停新消耗，不静默套另一模型价。

尚未使用、原本已获准的绑定允许在首次使用前补一次缺价，追加不可变快照版本；已冻结
绑定不被全局配置或新快照重定价，晚到usage仍使用调用时绑定的快照。新增未授权模型仍须
用户变更授权。首版不提供已用绑定的任务内改价／自动换汇／供应商价格校验。

示意配置（虚构单价；不是当前CLI可直接执行的文件）：

```yaml
mode: amount
budget_id: equipment-goal-001
task_ref: equipment-goal
authorization_reference: user-message-ref
currency: CNY
amount: "10"
prices:
  - provider: example-route
    actual_model: example-model
    cached_input_per_million: "0.2"
    uncached_input_per_million: "2"
    output_per_million: "8"
```

## 3. 共用用量核算与预算金额

### 3.1 仍只有一套token主账

从019／034抽出最小共用纯函数，输入显式绑定的数值记录，输出规范化可计费单元、来源
选择及问题。019离线报告和预算投影共同调用；不复制另一份去重／DSH算法，不让预算
自行给业务消息分配token。原价表与账单状态保持原合同，预算金额独立标`local_estimate`。

- provider响应以原provider／非秘密Key引用／response_id去重；无response_id时，只有
  真实单次request绑定才可替代。实际再次请求的重试有新身份，失败不退款。
- Codex累计以实际thread和连续计数段取起止差；新线程先登记真实0基线或已知旧累计，
  不把恢复时看到的总量当增量。计数下降、缺基线或多任务混用返回问题。
- 同一累计区间和响应明细互为核对／替代。流式累计、末次usage、代理和原生不相加；
  以019已确定的覆盖单元重算受影响区间，在线金额作“新单元金额−旧单元金额”更新。
  来源切换必须替换整个重叠覆盖区间，不能仅从新增记录再加一遍。不能证明对应关系则
  保留已知不重叠小计并异常暂停，不猜哪条应退款。
- DSH仍用`native_numeric_event`的真实session／seq／turn／step、retry和compaction
  合同；消息与attempt对同一步的修订是替换，明确重试为新消耗。压缩是总额子集。
  provider原件优先，原生替代不把019的`partial`升级成账单完整。GLM继续读已保留的
  原生数值事件；不启用`messages_provider_proxy.py`当前对GLM关闭的SSE观察器。
- 036成员汇总、Consumer末段快照及已发布报告是覆盖／核对来源，不能把各run总量再
  加到任务中。跨代次相同原生会话不重算，成员细分不明时显示未分配，不丢掉可信总量。

### 3.2 三桶和精度

规范化后的三桶为`C`缓存输入、`U`未缓存输入、`O`输出。输入包含缓存时，`U=I-C`；
DSH互斥桶为`I=原U+R+W`、`C=R`、`U=原U+W`。缓存写入只在未缓存桶计一次；
推理已在输出内则不再加，只有实际定义证明单独且未包含时才并入输出。定义未知不能凭
字段名称猜测。数值必须有限非负整数，子集超过总量不能通过取max或补零掩盖冲突。

金额使用Python `Decimal`和十进制字符串，直接累计未显示舍入值：

`charge = (C × cached_rate + U × uncached_rate + O × output_rate) / 1,000,000`。

不逐请求舍入到分。采用足以覆盖已校验token／价表位数的Decimal精度，累计过程不先量化；
UI／Markdown可显示6位小数和“约”，极小非零显示`<0.000001`，阈值使用原值。例子中
100万缓存、10万未缓存、1万输出得到¥0.48；1 token的许多小调用仍能累计到阈值。

### 3.3 暂估、待结算及异常

每个覆盖单元同时保留原usage缺值及预算的估算依据，原件不补写虚假0。

| 观察情况 | 预算行为 |
| --- | --- |
| 三桶已知，来源／身份可核对 | `usage_priced`，按冻结价计算；仍为本地估价 |
| 总输入／输出已知、缓存未知 | `cache_unknown`；常见缓存价≤未缓存价时按全未命中；反向自定义价格用`I×max(两项输入价)`，不伪称真实命中量 |
| 请求正常在途，尚无usage | 列`inflight`；可用增量照计，未结算余额不保证覆盖最终费用，不仅因等待而报采集故障 |
| 请求已结束、关键usage未到 | 即时列`pending_settlement`，允许最多10秒到达宽限；有绑定可信输入／输出上限或其他现成可靠数值才做保守暂估，无依据不生成数字 |
| 超过10秒仍缺关键值且无可信暂估；身份／定义／数值冲突；明确采集丢失 | `metering_error`并关闭新消耗、进入同一暂停路径；已知小计保留，可补数据后恢复 |

10秒宽限不阻止已经达到额度时立即请求暂停。保守暂估不等同预留，每单元只保留一个当前
有效金额；真实值到达后替换暂估并保留修订依据，允许累计或余额向上／向下修正。修正
让余额转正不自动继续；原生替代可用于近似预算，但不能忽略有证据的未计量重试／压缩。
仅缺供应商账单或019账单完整性为partial，不构成本条计量异常；真实失败attempt无usage
且无法可信涵盖才暂停。既有采集函数仍不中断当前请求，异常由预算观察转换为可恢复暂停。

## 4. 运行归集、保存和查询

### 4.1 程序更新周期

预算监视由原Delivery Host进程承载，独立于原生模型busy／idle的Python工作线程，每2秒
消费登记来源的新完整记录；不等待Host巡检、run关闭或036报告。价表、绑定和零额度在
`runtime.start/send`前处理。控制发出走原owner队列，不把较慢的FIFO／进程确认阻塞
数值读取。原生用量落到已登记可读来源后，健康、本机无积压时应在5秒内发布新投影并
登记必要的暂停触发；5秒是采集可用到程序投影／触发的边界，不是Provider产出usage的
时限或全部Agent暂停确认的承诺。

复用源文件offset／seq进行增量读取和`native_numeric_event`等数值投影，不全量扫描
原生正文。每周期最多处理4MiB／4096条完整记录，按来源轮转；剩余保留为backlog。
半行等下轮，不当作已消费；坏行、截断／换文件、身份冲突给定位，不能默默跳过后声称
完整。新增来源先登记覆盖起点和基线。连续10秒积压／来源读取不可用，或监视心跳超过
10秒未推进时标异常暂停；正常无新usage时监视仍可确认健康，不从安静推断故障。
阈值是本条默认实现参数，验证使用可控时钟；不能静默放宽后仍宣称5秒目标通过。

各Runner／evaluation owner在已有循环中至多2秒检查预算状态和监视心跳，在其实际
launch／start_task／send／steer／before_next_task前再次检查。监视owner退出时，仍在线
owner由同一共享状态登记一次异常暂停并执行自己的控制，不等待Delivery模型判断。
预算未初始化、接管未完成或来源未知时只拒绝新的消耗，返回可定位的可重试反馈；不
杀死run、不回滚已应用资源。监视接管沿原session恢复，不自动新建业务run。

### 4.2 最少持久文件

拟新增一个小模块`modeling_team/task_budget.py`，承担配置、投影、监视和状态归约，不
建立通用账本／调度框架。在预算私有目录内：

- `authorization.json`：初始不可变预算／价表／原授权引用。
- `events.jsonl`：授权追加／撤回／继续、成员绑定、源cursor及覆盖单元的金额修订、
  暂停epoch和分项回执。只存身份、数值、固定状态及原件定位，不复制正文或token历史。
- `state.json`：原子替换的最新可重建投影，含已提交事件序号、源截止点、已选覆盖
  单元及监视心跳。`budget.lock`沿既有`fcntl`约定串行化本机短写入；不持锁跨RPC。

数值修订和消费cursor在同一已提交事件中，先追加后发布state。崩溃后从state序号重放
已提交后缀，未提交记录重新读源并按身份重算，不二次扣款。截断尾行不视为已提交；
中段坏账／源冲突保持旧安全小计并异常暂停，不自行修证据。重复来源副本合并原件定位。
不以文件mtime认定成本身份，不保存另一份可独立累加的token主账。大量历史不进入每次
模型输入。迟到记录补入原预算；关闭后的新投影／报告用新版本，不覆盖冻结历史。

### 4.3 状态与权限

Host CLI及既有run／operation／Delivery状态返回`budget_ref`和简明投影；给Delivery
增加只读`get_task_budget`工具，复用原权限／会话绑定。查询本身不flush、不重算、不写
心跳、不发消息、不调用模型。金额包含：

`authorized_amount / priced_amount / provisional_amount / charged_estimate /
remaining_estimate / overspend_estimate / pending_settlement / inflight_count /
metered_through / observed_at / price_version / coverage / control_status`。

`charged_estimate=priced_amount+provisional_amount`，二者覆盖单元互斥；
`remaining_estimate=authorized_amount-charged_estimate`可为负；超额为
`max(0,-remaining_estimate)`。待结算未知量不伪造进charged，余额标“未结清”。逐角色／
模型合计与未分配小计可核对；范围外Host／辅助模型另列金额或unknown且`deducted=false`。

Host／用户看完整获准数值；Delivery看任务额度及获准流程分项，不获得隐藏题答、私有
评语、私有成员可枚举清单或原生日志。生产角色只收到与自己有关的暂停原因／继续指令，
不开放整个预算目录或隐藏验收分项。独立Consumer／Judge只收到原owner的控制，预算
文件不成为其语义证据。外部可见报告沿原投影规则屏蔽不获准身份／引用。

普通数值和心跳更新不唤醒模型；耗尽、计量异常、追加／撤回及明确继续以稳定事件身份
进入原控制／用户状态通道。预算暂停可由程序完成时，无需先让Delivery推理一次。

## 5. 耗尽、暂停和继续

### 5.1 原因与实际状态分开

`charged_estimate >= authorized_amount`时立即登记`budget_exhausted`（含零额度），
关闭本预算的新消耗准入并创建暂停epoch。`metering_error`用相同路径；同一未变原因／
epoch不重复广播，晚到用量只更新余额和尾差。用户暂停、授权撤回／到期、预算耗尽、
计量异常及原写入安全阻塞分别保留，清除一个原因不会清除其他原因。

每个owner记录`requested → submitted → instruction_delivered → effective`或
`unknown / failed / not_running`。全局展示按实际成员聚合；所有活跃绑定执行方满足
其真实证明后才称`paused_confirmed`，否则`pause_pending`，列未确认对象／调用。
已退出者须有退出证据，未启动角色显示`not_started`，不能为了收集暂停回执创建Judge。
暂停中后来登记的成员继承关闭状态，不能从旧快照漏过一次新启动。

### 5.2 各执行方的最小控制

| 对象 | 预算控制与证据 |
| --- | --- |
| Delivery宿主程序 | 继续数值监视、输入、查询、回执对账；不冻结整个Python owner，不启动普通模型新turn |
| Delivery原生模型 | 新send／steer／阶段新线程关闭；忙碌的Codex沿原生控制通知协作等待并确认，DSH补仅冻结已绑定原生进程组的pause/resume及PID身份验证；不关其Host侧代理／监视 |
| DSH生产／CQ | `pause_run`到原Runner，复用`_control_dsh_flow`的实际进程冻结／写准入结果；已在Host执行的请求仍按原回执落定 |
| Codex生产／CQ | 原Coordinator控制通道通知全部实际成员；按成员记录原线程确认／停发新任务事实，Coordinator收到或代答不能证明其他成员已暂停；复用transport身份，不增加业务消息握手 |
| 公开反馈／正式公开与隐藏Consumer／Judge | `relay_evaluation_message`到原evaluation owner，现有active／retained成员逐一控制；DSH用process结果，Codex用原确认；`before_next_task`关闭下一阶段 |
| 已接入主预算的辅助调用 | 所属owner关闭新调用，记录原调用的真实结束／在途；不声称外层Host和未接线辅助调用受控 |

预算控制沿原信封携带`source=task_budget`、`budget_ref / epoch / reason / request_id`，
不能伪称用户新发了暂停指令；用户动作仍保留原来源。控制请求使用由epoch及owner派生的
稳定身份，恢复先查原结果，未知送达不以新ID盲重放。发送失败只保留pending并继续核对／
原请求重试，不能标全体有效或永久终止。预算原因与原user-flow等待分别保留，避免预算
resume误解除用户主动暂停；DSH仅在全部暂停原因均解除后恢复原进程。

拒绝新消耗包括fresh run／operation、实质修模派单、原生普通新turn／steer、压缩／技术
重试和辅助新模型调用；旧活跃turn内Provider已接受的工作属于在途尾部。平台可观察并能
独立安排的下一次请求须再查预算，不能把整条自动重试链无限归为一条在途。无法观察的
Codex turn内部调用如实列控制限制，不伪称请求级硬停。已准入Host工具可完成原写入和
回执，暂停不能取消未知Batch／Attempt或跳过后续只读对账。

### 5.3 在途、必要收口与超额量级

暂停通知／确认本身需要的已有协作模型调用属于有限安全收口；以原控制身份登记，每个
活跃线程每epoch至多一次暂停控制turn（busy时优先同turn steer），重复状态不再开turn。
允许原请求的回执落定及必要资源保护；禁止把继续建模、再跑题／Judge或模型总结称为
收口。程序化状态／报告／只读对账和已有写入完成不受预算阻断；所有实际模型消耗继续
计回原账，包括这一次控制turn。技术纠错与恢复不能无限免费运行。

首版是软预算，不预留精确请求费用。每个任务启动前保存实际并发角色／请求数、已有
上下文／输出／重试限制、可观察边界及缺口；不额外发模型请求验证它们。对于具有可信
限制的调用，使用`q_i=(Imax_i×max(输入单价)+Omax_i×输出单价)/1,000,000`说明单次
最坏估价。触发之后的尾部按“当时在途请求＋控制延迟内实际新准入请求＋有限控制turn＋
迟到但尚未计量的已发生请求”列身份与金额；有上限时各`q_i`相加，不能用单个请求
上限代替并发总量，已经计入阈值的费用不得再称新增尾差。

例如三条在途请求各有可信未结算上限¥0.02，控制延迟内一条¥0.02，两个控制turn各
¥0.01，则新增可解释上界¥0.10；这是虚构验证样本。无可信单次限制、Provider超限、
协作不确认或不能观察的turn内部调用时，明确`tail_bound=unknown`、pause_pending及
实测尾差，不承诺“最多超¥x”。工程测试验证上述计算及拒绝虚假上界；真实A12必须
记录并发、usage延迟、5秒程序延迟和实际暂停时长，才能报告该次实际超额量级。

### 5.4 追加和同任务接续

Host按真实用户授权追加`delta_amount`，新总额=历史授权总和，消费保持不变。追加不足
仍耗尽；足额但未明确继续则保持暂停。用户同时明确“追加¥x并继续”可一次登记两项
来源，不再索取重复批准。计量异常需先补齐／核对，余额转正不能掩盖未解决缺口。

用户明确继续后，程序复核当前额度／授权／写入状态及各原因，清除获准解除的预算原因，
用原run／operation、线程／session及回执接续；重新读取原未完成请求和冻结版本，不
盲重发写入。原用户暂停／停止／到期仍有效，旧stopped进程不被自动复活。离线接管先
读原cursor／金额修订／控制回执、补迟到usage，再启动新的获准消耗。单纯补齐usage
或价表只解除计量缺口，不自行形成用户继续授权。

## 6. 实施边界与验证交接

本轮不修改下列活跃合同，实施时作为同一次金额模式交付同步：

| 改动面 | 最小交接要求 |
| --- | --- |
| `task_budget.py`、`usage_report.py`、`usage_capture.py`／`dsh_usage.py` | 共享数值核算，Decimal三档估价、增量cursor／替换、近实时监视和类型化反馈；原离线CLI／账单结论兼容 |
| `delivery.py`、`host_ops.py`／`host_ops_mcp.py`、`delivery_ops.py`、`evaluation_owner.py`、`__main__.py` | 可信绑定、Host授权／追加、只读查询、程序触发与实际owner控制；不增加公共backend业务API |
| 实际Codex／DSH生产、Delivery和验收runtime及036成员登记 | 首调用前登记，继承预算；关闭新消耗，保留原生控制／usage及失败边界，旧namespace正常装载 |
| `runner.py`／`start_ledger.py`相关调用 | 金额模式绕开“次数余额”这一条件，保留其余基线／gate binding／源忠实度／写入安全；历史字节与原语义不重写 |
| `AGENTS.md`、`skills/modeling-dev-loop/SKILL.md`及相关运行reference、Delivery instructions／Skill、实际Task／Profile／启动合同 | 显式金额新授权不再默认三轮，不要求逐修模申请次数或轮余额确认；次数／semantic-start仍用于分析；旧次数授权保留 |
| `modeling_team/references/model-usage-report.md`及现有Delivery使用说明／工具清单 | 说明预算估算、覆盖、暂停／确认、尾差、追加及未实施历史；沿现有合同校验同步，不新增另一份接口清单 |

不要求前端改造、backend迁移、Host全部辅助模型接线或账单MATCHED才能交付托管链预算。
若implementation触及共享数值内核，应依AGENTS跑受影响Team完整回归；只改本文档无需
产品测试或服务重启。实施后的runtime变更须做真实装载的本地有界验证；本轮不执行。

| 需求验收 | 后续验证意图与反例 |
| --- | --- |
| A1／A2／A7 | 虚构¥0.48、多模型／路由、显式零、小额精度、价表冻结／未用绑定补价；Codex含缓存与DSH互斥桶同价；反向缓存价格与缺值；旧账单缺价结论不变 |
| A3／A6 | 可控时钟回放usage到达后≤5秒；10秒待结算宽限／正常长在途／丢失／积压／监视退出分别判断，缓存未知有依据暂估与真实替换，修正不自动继续 |
| A4／A5 | Delivery、生产／CQ、公开反馈、隐藏／公开Consumer／Judge、压缩与实际失败重试；复制原件、累计换源、跨session／进程／重启和崩溃在追加／state发布之间，不双扣不清零 |
| A8／A9 | 0、恰到／超出、重复触发、多owner部分送达／确认、迟到负余额、追加不足／足够但无继续、计量恢复与用户暂停叠加；不同任务隔离 |
| A10／A11 | Host／辅助覆盖明确未扣，权限不泄露私有成员／正文；同目标多轮不触旧次数门，历史次数仍有效；未知写入落定／对账，预算不足不能缩题或跳过独立验收 |
| A12及控制补充 | 先离线原件回放与真实本地Codex／DSH接口fixture装载，验证所有实际调用边界及旧入口；另获运行授权后记录真实托管链、实际暂停与尾差、接续，并由独立验收分别判工程／控制与业务语义 |

控制专项须覆盖：Delivery自己busy时耗尽、监视不随DSH原生进程冻结、Coordinator已确认
但另一生产成员未确认、Consumer暂停期间不启动Judge、部分SIGSTOP失败、同一epoch
回执不明、暂停与新成员注册竞态、继续与旧预算暂停晚到竞态；状态须保持pending或
继续受原原因限制，不通过重新发模型任务“证明已恢复”。不得为本次输出新建一次性
语义裁判。现有测试优先扩展`test_usage_report.py`、`test_dsh_usage_report.py`、
`test_delivery_wakeups.py`、`test_host_ops.py`、`test_delivery_ops.py`、DSH／Codex
runtime及evaluation owner的相关用例，预算纯数值及状态用例集中一个新测试模块即可。

## 7. 设计检查与证据边界

独立审阅核对本设计能否满足F1—F8及A1—A15、当前实际入口、旧授权兼容、预算状态
与暂停事实分离、数值主账复用以及当前最小范围。审阅发现和修订另存
[审阅记录](../records/2026-10-20-r4-4-002-design-review-record.md)。

设计PASS只能证明方案可交接实施，不能证明5秒更新、实际全员暂停、预算精确不超支、
真实成本覆盖、token净降耗、工程交付或独立业务语义通过。无新的金额或运行授权产生。
