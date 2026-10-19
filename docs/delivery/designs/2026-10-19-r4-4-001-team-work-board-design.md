# R4.4-001 建模 Team 当前任务展台与协作请求设计

- 日期：2026-10-19。
- 权威范围：[R4.4-001](../../requirements/requirements-v4.4.md#r4-4-001)。
- 状态：需求／设计完成，独立设计Round 1 PASS，0 Critical／0 High，无关键未决假设；
  后续澄清复核见第7节及审阅记录。历史查询／统计关联增量独立复核PASS，0 Critical／High。
  后续工程已按用户续授权实现并通过本地测试，见[交付记录](../records/2026-10-19-r4-4-001-team-work-board-delivery-record.md)。
  真实采用、净token收益与独立业务语义未验证。
- 代码基线：`cb60bd57f372080f15b12ef531a24e14c3f858b0`；现有 README、v4.3、优化跟踪及
  复盘／演示材料变更属于其他工作。设计阶段仅新增本需求／设计／审阅记录并更新文档导航；
  后续工程基线与验证另见交付记录。
- 历史／复盘增量基线：`0f491b1`；定向读取当前019／036的已实现数值及关闭入口，
  不修改v4.3在途条目或接管相关实现。
- 决策 D1—D13 以权威需求为主表，本设计不再复制理由表。首版提供结构化展台与 CLI
  汇总；当前 Delivery 会话页可在后续消费同一投影，本轮不设计新管理页面。

## 1. 已有能力与必要增量

| 当前入口 | 已有事实／能力 | 本条必要增量 |
| --- | --- | --- |
| `modeling_team/transport_mcp.py` 的 `TeamTransportBroker.send`、`mcp_response` | 绑定发送者、检查 Profile 通信边、自然语言消息、delivery 身份及回复关联；待回复与结果主要在 Broker 内存 | 可选跟踪关联、本人卡片更新、请求关闭和按权限读展台；不扫描消息正文识别任务 |
| `modeling_team/runner.py` 的 `drain` 与 deliveries 证据 | 实际 Adapter 接受后 ack，记录发送者／接收者及delivery；Broker 接受不等于实际交付 | 在既有分发结果上绑定请求运输状态，不另发同一业务消息 |
| `modeling_team/host_ops.py` 的 `get_run_status`／`get_pending_actions` | 运行、阶段、实际活动和原队列派生；只读，不drain | 共享展台读取函数及简明索引；展台请求不混作正式Host issue或CQ待审 |
| `modeling_team/delivery.py` 的 `yield_delivery`、v2输入、私有journal | Delivery等待／计划理由、既有请求及按需变化输入 | 将展台作为按需工具可读原件；普通卡片更新不改变决策指纹 |
| `modeling_team/delivery_host_actions.py` | 宿主私有CQ审核／平台修复请求与结果 | 宿主汇总可引用原待办，生产展台不复制正文 |
| `modeling_team/runtimes/codex.py`／`dsh.py` | 隔离环境装载transport、工具白名单与运行适配 | 装载新增小模块／工具，并验证两种现有运行时的一致合同；不新增Provider |
| `modeling_team/close_statistics.py` 的 `read_close_statistics`／`publish_close_statistics`，`usage_report.py` | 036按实际成员冻结来源，发布同源数值JSON／Markdown及scope；019负责token归属与去重 | 读取已发布数值结果；关闭时附属生成历史复盘索引，保持数值主账和统计发布独立 |
| `frontend/src/pages/DeliveryConversationPage.tsx` | 绑定项目／session的对话和运行状态 | 首版不改；后续可只读消费相同展台投影，不从私有日志自行拼卡 |

当前 `send_team_message` 没有持续任务字段，消息回复身份只表达“回复了哪条消息”；
`get_pending_actions` 当前派生业务问题、CQ、issue及Provider待办，不能直接当成全部协作请求。
场景地图继续由 Coordinator 判断业务表达与未知，不从卡片推导 modeled 或修改地图。

方案比较：只在本人卡片写“等B”成本最低，但B缺少可见的待处理请求；双方手写两份记录会
漂移；选择一条请求双向投影，沿原消息发出时顺便登记。通用工单系统、独立调度服务、数据库
任务表和新页面均不解决本次额外必要问题，首版不引入。

## 2. 责任、粒度与读取视图

生产 Agent 只维护自己的工作内容，可在原允许通信边上提交署名请求。对方卡片中的“收到
请求”区由程序生成，不授权请求者改写对方目标、优先级或本人反馈。B 可在真实工作变化时
说明如何处理请求；Coordinator 沿原协作方式协调冲突，程序不自动排期、抢占或判断业务含义。

每个生产 Agent 每个 run 一张卡，可同时关联多个近期工作范围。`near_term_goals` 是自然
语言目标列表，允许“理解设备资料”“分析业务生命周期”或具体操作；建议少量近期项，不设
固定条数／时间段硬门，不拆成每次工具调用。普通目标持续期间无需更新，交接时保留未决项。

采用三个读取视图，全部从同一事实源派生：

- **生产 Agent 视图**：本人卡片、原 Profile 中允许 `owner → viewer` 通信的生产 Agent
  的共享工作摘要，以及本人作为发起者／接收者参与的请求。卡片只填写允许向这些接收者
  共享的工作摘要；源正文和产物正文继续沿原材料权限读取。无通信边的卡片／请求不返回
  正文或可枚举身份，不通过看板扩大原源材料访问面。
- **Delivery 视图**：绑定 run 的 Agent 身份、运行事实、可共享工作摘要、依赖两端、运输／
  请求状态及流程引用；不默认返回原 peer 消息全文或业务结果正文。未决正文仅沿已有授权
  读取；私有CQ审核、隐藏题／答案／Judge理由均不进入此投影。
- **用户／宿主视图**：沿本地原授权读取上述生产展台，并在独立上下文区展示已有 Delivery
  yield及宿主请求／结果的获准摘要。它们保留 session／request 身份和来源，生产Agent读
  工具不返回此区；未绑定session时显示缺来源，不要求Delivery／宿主重复手填卡片。

独立 Consumer／Judge 运行的内部卡片和消息不并入生产展台；不向独立验收Agent开放生产
展台新工具。历史Profile内存在Acceptance角色时也不据此公开私有验收正文，沿原材料边界。
卡片与请求的自然语言由有来源的Agent负责，不用关键词过滤器代替隔离或语义判断。

## 3. 最小数据合同

拟新增 `modeling_team/work_board.py`，处理校验、追加记录和投影；由每个 run 的既有 Broker
承接生产写入。事实源为 `<run-root>/evidence/work-board-events.jsonl`，不写入RDF／业务表，
不新增数据库迁移。各侧卡片是视图，不能分别保存可独立修改的请求副本。

事件带 `schema_version=team-work-board/v1`、run身份、单调序号、真实actor、UTC时间及事件
内容；身份和时间由程序填写。索引可在内存重建，持久事实以追加记录和原消息／运行回执为准。
原记录不覆盖，宿主读取不写文件。不缓存另一份会被当作权威的完整看板快照。

每个卡片更新事件保存本次完整本人字段，前次内容继续在原事件中，避免重建历史依赖当前
可变文件。`member_ref`由运行端按已有成员注册／原生会话绑定附加，可包含runtime、
runtime_session_id／Codex thread_id、process_instance和注册原件定位；模型不能自填。
缺少真实代次绑定时保留null／限制，不能把当前进程补给旧事件。历史序列按record_seq排序，
UTC时间用于筛选和展示，不以时间邻近关联成员。归档快照是带原序号／摘要的只读历史前缀，
不成为可独立修改的第二份当前状态。

### 3.1 本人工作卡

| 字段 | 含义 |
| --- | --- |
| `run_id / agent_id` | 服务端从run及端点绑定，不能由调用者冒充 |
| `current_work` | 当前具体关注，可为分析／理解活动 |
| `work_scope` | 可选的切片／文件／任务范围说明或获准引用 |
| `near_term_goals` | 自然语言近期目标，允许混合粒度 |
| `waiting_note` | 可选等待说明；有协作请求时引用request身份，普通工具等待不强制转请求 |
| `latest_result_refs` | 可选的最近成果定位，不复制候选、源正文或应用回执 |
| `reported_at / record_seq` | 最后一次有内容变化的实际报告位置 |

`update_work_card` 用一份小的完整本人字段替换上次本人字段；空列表／空等待说明表示清除，
不存在的可选字段按空处理，不能保留已清除的旧阻塞。请求区不在此可写对象内。与当前内容
相同则返回原位置，不追加事件或刷新时间。本人工作卡没有必须遵守的状态机或完成率。

汇总另外附上 `observed_runtime`，只从已有状态／Provider／投递事实派生，明确来源和观察
时间。缺卡为 `not_reported`，缺运行证据为 `unknown`；互不补推。长时间未更新只显示年龄，
不新增固定“失活”时限。原进程退出或工具异常仍可与旧卡内容同时显示。

### 3.2 协作请求

| 字段 | 含义与维护方 |
| --- | --- |
| `request_id` | 发起者在第一次提交前生成的UUID，按`(run_id, request_id)`唯一绑定，发起者另存为不可变归属 |
| `requester_id / assignee_id` | 真实消息发送者／接收者；不可改写 |
| `summary / related_work / blocking` | 发起者提供的可共享简述、受影响工作、是否实际阻塞；blocking只指该工作 |
| `message_bindings` | 原请求、更新、撤回通知的delivery身份及各自运输事实 |
| `requester_state` | `open / resolved / withdrawn`，仅发起者改变；resolved表示其判断当前依赖已满足 |
| `assignee_report` | `pending / in_progress / needs_input / responded / unable`；pending由创建派生，其余仅接收者报告 |
| `feedback_refs` | 反馈事件、原消息和获准结果定位；保留历次反馈，不从自然语言猜结果 |
| `created_at / updated_at` | 实际记录时间，不由读者或其他请求刷新 |

请求不是模型资源，也不是新的正式issue。A无须已经完全停工才能请求B；`blocking=false`
可表达后续期待，`true`也只说明关联工作受阻，不能推断整个Agent或run停止。

`responded`只表示B提供了结果。A可以在继续工作时关闭为resolved；未关闭不会增加额外
终态门。A已撤回／解决后B的晚到反馈仍追加原件，投影保留A判断并标晚到；新工作需求使用
新request身份，不用重开状态机重置旧历史。相互等待可在双方视图中看见，由原角色协调。

## 4. 写入入口与消息关联

本节为拟实现合同，当前工具尚不存在。沿原Transport增加三个小入口，并扩展一个旧入口：

| 入口 | 合同 |
| --- | --- |
| `update_work_card(card)` | 仅当前端点本人的工作卡；调用结果含原／新record_seq及是否改变 |
| `send_team_message(..., work_request?)` | 保留旧参数；可选元数据把原请求或B反馈绑定到持续记录，一次调用完成消息提交和登记 |
| `resolve_work_request(request_id, resolution, note, update_id)` | A记录resolved或withdrawn；resolved仅本地更新，withdrawn沿原通信通道给B一条有实际内容的撤回通知 |
| `get_work_board(agent_id?, request_id?, view?, from_time?, to_time?, record_seq?, cursor?, source_ref?)` | 默认current；可选history／version，按原身份过滤后分页；不能借参数切换成Host或其他Agent |

`work_request`只在需要持续跟踪时存在，支持：

- **request**：`request_id, action=request, summary, related_work?, blocking?`。发起身份来自
  当前端点，接收身份来自原recipient；同一请求不能换接收人。自然语言正文仍是原text／body_ref。
- **feedback**：`request_id, action=feedback, update_id, assignee_report, result_refs?`。
  当前发送者须是原B，接收者须是原A；说明和结果通过原text／body_ref交付，不另发一条反馈。

从Broker到`RuntimeDelivery`再到Codex／DSH原生消息信封，新增可选机械字段
`work_request_ref`，携带服务端绑定的run_id、request_id、requester_id及本次action／update_id。
接收者据此定位同一请求，不必解析正文寻找编号。原text保持不变，旧消息省略此字段；
接收者看到的request引用与工具／展台返回的一致，不能只在发送方工具回执里保留。

新请求沿原业务消息合同选择 `expects_reply`，展台元数据不会自动增开reply slot。
进度通报可用 `expects_reply=false`、不带 `reply_to_delivery_id`，避免为了报进度提前消费
原请求的回复位置。实际答复若回复位置仍有效，则照原合同反向绑定；已经结清时可发普通
反馈并用request_id关联，不能伪造或重复消费旧reply slot。展台从来不以reply slot已关闭
推断assignee_report或requester_state，也不改变原消息终态要求。

例如：A发送请求并附跟踪元数据；B可以直接在真实结果消息中附feedback/responded，跳过
in_progress；A下次推进工作时记录resolved，不向B发送“收到结果”的额外确认。B若先报告
needs_input，请求仍open，A通过原通道补资料，双方用同一request身份继续。

### 4.1 重试与部分成功

同run的request身份、反馈update身份和关闭update身份分别去重；身份与参与者校验先于去重
回显。反馈、关闭及定向读取均使用原request_id，不按显示简称、最新一条或接收者匹配；
A／C分别向B请求时使用各自UUID，即使简述相同也保留两条。获准同一调用者以同身份同规范化
参数重试时返回原登记及delivery引用，同身份不同内容返回 `work_request_conflict` 并保留原内容。
卡片采用内容相同即无变化，不要求为每次小报告生成更新ID。

Broker在原锁下先检查身份／Profile／参数，将关联意图及原消息身份写入run-local记录，再
沿原队列交付；实际Adapter结果沿原Runner事实追加运输投影。实现应在尚未产生消息副作用
时拒绝无效参数，不能先发送后发现身份错误。Transport服务器及隔离副本都调用同一Broker
入口，不能由stdio子进程直接改文件，避免两个写入者。

这里承诺一次调用、同一身份及可见分项结果，不承诺文件记录与Runtime交付跨进程原子完成。
返回 `record_status`、`message_status`、原定位及准确限制。登记成功只表示请求已记录；
queued、实际Runtime接受、失败／未知分别读取原回执，Runtime接受也不表示B完成工作。

若落盘失败且原消息尚未入队，返回可重试错误，无消息效果；若消息已被接受但后续记录或
回执失败，保留原请求／delivery身份并返回partial／unknown，先按原回执核对，不能换ID
再发一次。活Broker可从原请求映射返回既有消息；进程崩溃后的旧展台按保留记录只读重建，
不声称已恢复内存队列，不自动重发或启动run。无法证明交付的记录显示unknown，必要动作
沿既有宿主恢复／原消息核对路径处置；不把“展台登记成功”当作恢复依据。

展台记录错误不永久毒化Broker或run。Agent可修正参数；记录服务异常时原普通消息通道
继续可用，明确此次未登记／未知，宿主按原技术交接处理。后补关联必须引用真实消息，不能
伪造已送达或新增一条重复任务。撤回只撤回A的期待，不代替用户stop或强制取消B其他工作。

## 5. 聚合、Delivery输入与用户查看

新增Host只读函数／工具 `get_team_work_board(run_id, agent_id?, request_id?, view?, from_time?, to_time?, record_seq?, cursor?, source_ref?, include_statistics=false)`，复用
`host_ops.resolve_run_root`绑定；Delivery工具白名单开放流程投影，当前绑定与授权仍由Host
决定，模型参数不提供viewer权限开关。原get_run_status可附展台是否可读及索引引用，不
将完整卡片／请求集合塞回每次原状态查询。

增加只读CLI `python -m modeling_team work-board --run-id <run-id>`，默认按Agent显示当前
关注、近期目标、发出／收到请求、最近结果及报告／观察时间；`--json`输出同源结构化投影，
`--agent`／`--request`定位，分页显示续读方法。由已获准的本地用户／宿主执行，不新增
对外HTTP接口。用户可通过CLI或宿主直接展示的该汇总查看首版展台。

默认页提供必要短正文及各集合total／returned／complete／continuation，复用既有有界
读取习惯，不用哈希替换关键变化；过大内容显式分页。按参与者生成投影后再分页，不能以
页计数暴露被过滤对象。引用只给获准定位；详情继续走原材料读取接口，不新增任意路径读取。

Delivery沿030正常保持原监督：普通卡片更新和请求进度由程序保存，不改变决策指纹或增加
“再看一次展台”的模型turn；需要了解当前工作的具体决策缺口时调用新读工具。新阻塞、
无法处理、实际失败或结果不明若需要Delivery／宿主动作，原Agent仍须通过已有Coordinator
消息／正式issue／request_host_action通道升级；看板登记不会代替实际通知。程序不得为了
降噪吞掉这些原事件，已存在的消息只交付一次。需要唤醒时沿原v2给最小充分正文和原定位。

Delivery／Host上下文区只读取原yield／journal，不发布到生产文件；原Host请求completed
仍只表示该请求结束。历史没有展台的run显示unavailable，不从旧对话自动编造工作卡。
新run可引用旧成果，但不复制旧运输身份、未结请求或授权，不能因此重放业务或建模。

### 5.1 历史与指定版本入口（D11）

原读取入口的三个模式如下，不新增独立历史服务：

| 参数／模式 | 明确行为 |
| --- | --- |
| `view=current`（默认） | 当前本人卡片与关联请求；保持原有轻量读取 |
| `view=history` | 选定Agent的卡片变化或选定request的事件，按record_seq升序；无选择时为获准run历史 |
| `view=version, agent_id, record_seq` | 读取该Agent在指定卡片更新序号保存的完整内容；序号属于别的对象时给可修正错误，不取最近版本冒充 |
| `from_time / to_time` | 带明确时区的半开区间`[from_time,to_time)`，仅筛选history事件的记录时间；不改变统计窗口 |
| `source_ref / cursor` | 第一页捕获的同run来源前缀、最大完整序号及筛选条件；续页固定此范围，不能跳到新追加尾部 |

每条卡片历史返回真实actor、时间、序号、完整当次卡片以及`previous_record_seq`、
`changed_fields`；前后内容可在页内展示，超出页预算时给精确获准版本引用。前版不在当前
时间区间或本页中也能准确定位；确实缺失／损坏则标unknown，不能对着最新卡片猜diff。
请求历史保留原创建／反馈／关闭／晚到事件及消息回执引用，不把旧请求当作新待办。

固定前缀引用至少含相对路径、byte_length、sha256和max_record_seq；只接收本run由服务
返回的展台／归档来源，继续校验身份和材料权限，不提供任意文件读取。完整换行以前为可用
前缀，坏行／截断给原定位与coverage限制。后续append不改变该前缀；已有前缀被改写时
明确返回source_changed，不能悄悄换页或把当前记录补进旧查询。每页先权限过滤再计数，
旧版本与变化字段同样执行权限校验，不能从前版或计数泄露不可读内容。

CLI增加`--history`、`--from`、`--to`、`--record-seq`和服务返回的续页参数；`--record-seq`
与`--agent`组合对应version模式。以下为拟实现命令示意，当前尚不可执行：

```sh
python -m modeling_team work-board --run-id RUN --agent AGENT --history --from 2026-10-19T01:00:00Z --to 2026-10-19T02:00:00Z --with-statistics
python -m modeling_team work-board --run-id RUN --agent AGENT --record-seq 42
```

### 5.2 历史与数值统计共同查询（D12、D13）

两类原件共同归属于`<run-root>/evidence/`：展台保持work-board-events.jsonl；统计继续
使用036的close-statistics/report-*/report.json、report.md、scope.json和冻结sources。
`include_statistics=true`／CLI `--with-statistics`读取`read_close_statistics`已发布的真实
报告引用，不重新采集、扫描全Host目录或调用模型，不把卡片JSON塞进numeric usage源。

联合响应包含`history`、`statistics_groups`、`bindings`及两侧独立的source／window／coverage。
历史事件仅引用统计group身份，每个成员／会话的数值在statistics_groups列一次；不能为每个
卡片更新复制整轮消耗后再求和。input、cache、output、reasoning、LLM／工具／活动／生命
周期及其缺口直接消费019／036结果，不再实现计费、累计或活动并集算法。

关联只取已有run／Agent／实际成员清单、原生session和process_instance；多代次逐一列出。
已证明同一run／Agent但事件缺代次时，可给该Agent范围的既有统计摘要并标未细分；不把它
指派给单个历史事件。绑定冲突或只有同名／时间相近时保持unallocated／unknown。任务级
报告内的其他run或context成员不当作本run统计；会话累计跨代次按原主账展示一次，不把
同一session累计复制给各process后相加。

`--from/--to`只缩小历史列表，数值明确标为“所选统计报告内该成员／会话范围”，并单列
statistics_window／cutoff与history_window。首版提供时间线与数值并列查看，不计算每个
宏观任务或每张卡片的精确token。统计未发布或覆盖不足时返回unavailable／partial及已有
引用，历史仍可读；不以零补缺，也不为了查询在关闭流程之外自动生成新统计。

联合数值只在Host入口与Delivery的既有流程授权视图开放，不新增生产Agent统计权限。
Delivery只取得本run获准生产成员数值与流程摘要，不获取验收／Host私有成员正文或任意
原始数值采集源。Host可沿019原授权另读完整任务报告。对外返回的数值分组先筛选获准
成员，不能从总量／占比反推出隐藏成员；无法安全拆分的任务总计只给限制，不原样返回。

### 5.3 关闭后复盘留存

复用036的关闭发布接点：`publish_close_statistics(view=run_close)`完成其原报告发布后，
在原控制／工具锁之外调用work_board模块的附属归档函数。只处理这个run已有展台，不为
历史无展台的run补造卡片。统计不可用但历史存在时仍可留历史快照，索引中如实标数值缺口。
该分支不调用LLM、不重启Agent，不改变原停止／清理结果或数值报告ready语义。

在`evidence/work-board-retrospectives/snapshot-<fingerprint>/`写入：

- `work-board-events.jsonl`：本次完整行前缀，保持原序号与内容；
- `index.json`：schema版本、run身份、历史前缀长度／摘要／末序号、历史截点、统计报告
  相对引用／snapshot身份／scope与cutoff、实际成员关联定位、coverage及限制。

同一历史前缀和统计版本生成同一fingerprint；暂存目录完整后发布，随后更新同run复盘
指针`evidence/work-board-retrospective.json`。每次查询只读已有指针／索引；活跃run无
归档时直接只读当前历史前缀。索引失败显示archive_unavailable，不反写036已发布的报告
和指针，不阻塞旧统计读取。原关闭统计失败处理不接管此分支，不能把归档错误改写成统计失败。

晚到反馈或迟到统计在原有获准补报时生成新复盘版本，旧索引／快照／统计原件保留；普通
读取不触发补报。索引内使用相对run根的路径，复制／保留整个run证据目录即可一并保留两类
材料，不依赖原Agent临时home。统计scope已经冻结的数值sources沿原036位置留存；不改写
旧scope摘要，不复制一份另算数字。源文件缺失／摘要不符时给准确缺口，不回退到新版本
伪装旧报告。CLI增加`--archive-ref`，Host读取参数的source_ref可选择该服务登记索引；
先恢复其冻结历史与统计版本引用，再执行原权限过滤及历史选择，不能混入当前最新报告。

复盘目录及指针为Host私有，权限沿019／036目录0700／文件0600；卡片／请求正文存于独立
历史文件，原数值报告继续只含允许的数值和定位。生产工具仅能按原权限读取获准历史投影，
不能直接取得Host私有索引或统计文件路径。清理保留run证据及索引，归档故障只影响复盘
覆盖，按原技术反馈处理；不引入跨机器归档、全局索引、后台恢复或新页面。

## 6. 实施交接与验证

设计阶段只交付文档；后续工程已按用户明确续授权实施以下最小范围。下表保留设计时的
分层验收边界，实际工程结果与命令见交付记录，真实建模运行仍沿原授权控制：

1. 新增`work_board.py`及聚焦测试；扩展`transport_mcp.py`的Broker工具、绑定校验和持久
   记录。实现前对send／drain／公开工具做影响检查，保留原消息和旧任务兼容。
2. 在`runner.py`消费已有实际分发结果，扩展`runtimes/base.py`的`RuntimeDelivery`可选
   机械引用；`runtimes/codex.py`、`runtimes/dsh.py`装载新增模块和工具并透传到原生信封，
   核对隔离副本、工具白名单及基线清单，不能只测直接Python调用。
3. 在`host_ops.py`／`host_ops_mcp.py`、`__main__.py`及Delivery获准读取处提供同源汇总；
   包含历史／版本及可选统计读取，不扩展backend或frontend。036原run_close发布后增加
   隔离失败的附属归档调用，数值报告与旧来源合同保持。运行对外接口文档同步检查并按
   实际新增Host工具更新对应引用。
4. 在现有活跃角色合同中说明卡片粒度、低频触发、可选跟踪、自然反馈与原升级职责。独立
   验收包不加生产写卡能力，宿主监督说明只加原件读取入口。运行适用合同／技能校验。

| 验证层 | 覆盖及边界 |
| --- | --- |
| 文档／设计（本轮） | 链接、编号、示例与范围一致性；独立Reviewer核对需求／实际入口，只证明设计可实施 |
| 工程功能（未来授权） | A1—A7及A10—A12；经过真实Broker／MCP、Runner回执和036发布／查询接点。覆盖多请求者、越权、晚到、重复、固定前缀历史、归档故障及统计错配，不能只测投影helper |
| 运行时装载（未来授权） | 当前Codex及DSH环境实际发现工具、原身份绑定和授权视图；以有界装载证据为准，不新增Provider服务 |
| 真实采用与成本（未来授权） | A8；沿已授权业务run观察实际卡片和请求使用，单独记录维护、补读、减少询问及成本转移；没有匹配对照不宣称净降耗 |
| 独立业务语义（未来授权） | A9；沿原冻结证据和独立Consumer／Judge完成，与设计／工程结论分开 |

展台数据不是业务语义证据，不作为Judge标准答案或模型完整性判断依据。验证不新建只适用
本次输出的一次性验收器，不要求为记录表面完整而追加角色、建模轮次或修改既有运行证据。

## 7. 设计审阅与状态

作者已核对初版D1—D10、F1—F8及A1—A9的一致性和实际复用入口；非作者独立Reviewer完成
Round 1设计审阅并判PASS，0 Critical／0 High，无关键未决假设。请求身份澄清和最终复核
原件见[审阅记录](../records/2026-10-19-r4-4-001-design-review-record.md)。设计结论不覆盖工程或真实运行验收。

后续按用户要求新增F9—F10、D11—D13及A10—A12，补齐历史查询和与已有用量统计共同
留存／查询的入口。该增量已由原独立Reviewer定向复核PASS，0 Critical／0 High，无关键
未决假设；不继承原PASS充作新增范围的审阅证据，实际新原件与结论另记。
