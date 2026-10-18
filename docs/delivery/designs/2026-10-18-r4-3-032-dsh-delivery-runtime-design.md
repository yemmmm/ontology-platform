# R4.3-032 DSH Delivery运行时适配设计

## 1. 目标、范围与基线

权威需求：[R4.3-032](../../requirements/requirements-v4.3.md#r4-3-032)，全部实质决策在该条
D1—D8主表。本次只细化、设计并独立审阅，不实施、不发模型请求，不启动或恢复生产、
修模及语义验收，不消耗建模轮次。设计PASS不表示工程或真实运行PASS。

例子：Delivery请求宿主审核CQ后调用yield_delivery。Host继续观察，DSH实际结束当前
推理后才标等待；审核回执到达才送入下一次必要决策。其间用户补充“先保留原范围，
暂停生产”，Host保留原文和来源，活动中的Delivery在最近的step边界收到输入，不能
排在一个长turn之后；生产暂停按绑定运行时的原控制通路执行。DSH入队、领取、活动
结束、控制生效和业务完成有各自证据，任何一项都不能冒充下一项。

### 1.1 核对基线

- OntoWeave提交：`2beaab95c1f9b63198604c2fdf89a09c9918ecae`；2026-10-18核对。
- DSH本机：`/home/yangxiang/deepseek-harness`，提交
  `687f282e8625c6b8d11ff58211a90524be2e4317`，已跟踪文件无修改；用户本地插件／配置
  不继承、不清理。固定接口基线与031一致，实施须冻结实际构建、锁文件及composition。
- [官方SDK协议](https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sdk/protocol/README.md)
  和本机同提交源码确认：prompt返回messageId仅证明持久入队，resume恢复指定持久session，
  wait表示整体静止；SDK没有steer／cancel。底层Agent具有steer及cancel(keepInbox)。
- 030首批F1／F2已实施；[交付记录](../records/2026-10-17-r4-3-030-f1-f2-delivery-record.md)
  仅有工程证据，真实yield行为和降耗仍未验证。F3短线程／F4连续机械动作未实施／启用。
- 031设计已独立PASS；本轮阅读时contracts.py、runtimes/base.py出现并行未提交修改，
  仅作接口演进观察，不视为031工程交付。本设计不编辑它们；实施对齐031实际交付字段，
  不重新打开本条业务决定。032可先设计和离线开发，真实生产依赖所选路径实际可用。
- 已有README、029、复盘、演示等工作保留；仅修改032、适配组状态及本设计／审阅记录。

### 1.2 当前入口与真实缺口

| 入口 | 已有事实 | 本条必要增量 |
| --- | --- | --- |
| delivery.py::_run_delivery／DeliverySession | 独立Host交付session、约2秒观察、原始账本、v2输入、权限及standby已存在；直接构造Codex DeliveryRuntime | 独立选择Delivery runtime，所选循环不依赖Codex thread／turn私有字段 |
| runtimes/delivery.py::DeliveryRuntime | Codex dynamicTools回调、send／steer／poll／interrupt／close；busy在turn/completed清除 | 保留Codex实现，增加窄DSH实现及两者实际共用接口 |
| DeliverySession::_dispatch_observation／_restore_decision_inputs | accepted后推进分页；attempted／unknown及旧v1转换已有 | DSH accepted只表示运行时接收，另留queued／claimed／settled；恢复核对未消费页 |
| delivery_conversation.py::ConversationLog／ConversationServer | 用户原文、来源、派发及控制回执、去重／输入通路已有 | 沿原日志追加DSH原生关联；accepted_by_native不升级成已读／生效 |
| DeliverySession::tool_specs／call_tool | Host注入参数对模型隐藏；模型get精简，内部原始结果；CQ私有隔离 | 将同一清单／回调接入DSH，不重写Host权限与业务工具 |
| _yield_delivery／record_observation／_deadline_events | yield仅记录，程序继续观察；明确到期只唤醒一次 | 从DSH真实turn结束判断推理停止，不能以工具回执或idle单独结论 |
| model_routing.py::resolve_delivery_model_binding | 显式delivery绑定优先，否则继承Coordinator精确绑定及来源 | 先按原规则解析，再验证与Delivery runtime兼容；不得静默转换模型／effort |
| DSH SDK server.ts::prompt及agent-loop/src/agent.ts | prompt调用followup→next-turn；Agent.steer→next-step，cancel支持keepInbox | Node窄桥接底层公开Agent能力，不把prompt包装成steer，不fork核心 |
| DSH tools/src/index.ts::ToolDefinition／ToolRunContext | 自定义工具可取得真实agent／callId并返回JSON | 保留工具调用身份和结构化结果，直接桥接Host回调，避免普通MCP丢失callId |

本轮为已知入口的源码／调用点定向检查，没有修改代码或宣称GitNexus图覆盖。实施时
按AGENTS做实际跨模块impact／detect_changes；不可用时保留定向调用点及回归证据。

## 2. 配置、装载及权限

### 2.1 独立选择与最小接口

Delivery config新增runtime闭集codex／dsh，省略保持codex；它与生产Profile.runtime
分别选择。保持run_delivery及原锁、业务session ID、project／授权／模型绑定等合同。
旧记录缺runtime按codex读取；不能把旧Codex session.json改为dsh继续。新DSH使用
独立业务session目录，可显式绑定原获准run监督，但不是旧原生会话的延续，须先核对
原监督所有权已释放，不双重监督或重放动作。不建设自动迁移／故障切换。

保留原DeliveryRuntime作为Codex实现（名称无需为本需求重命名），增加窄
DeliveryRuntime协议和DSHDeliveryRuntime。接口覆盖start、派发（普通／活跃输入）、
poll、活动／身份查询、interrupt、close；仅替换_run_delivery所需接点，不让Delivery
继承生产roster Adapter或建通用runtime注册中心。Codex原wire及turn行为保持。

记录runtime、process_instance、runtime_session_id和实际活动seq引用；DSH不向
native_thread_id／turn_id填伪ID。旧Codex字段继续读取，新增统一身份供当前DSH路径
使用。busy须保守覆盖已排队／活动及在途工具，真实无活动和无待消费工作才可等待；
进程不可用、缺事件为unknown／supervision_interrupted，不能当idle。

model_profile继续用resolve_delivery_model_binding，保存binding_source；DSH首批复用
031原生DeepSeek及Host Messages持钥代理，精确验证provider／model／effort。不因
生产Team用DSH就强制Delivery同模型，也不把继承到的不支持模型自动改为DeepSeek。
service_tier=fast及Codex特有窗口／压缩配置不得静默忽略或套用DSH：显式提供但无
对应支持时返回字段级unsupported-runtime-setting；省略项使用DSH有效配置并冻结。
现有544000／489600默认只留在Codex分支，不能先填默认再误拒绝所有DSH配置。
DSH具体上下文／压缩由固定composition和实际provider配置记录，不承诺默认更省。

### 2.2 Delivery专用进程与工具桥

复用031固定Node装载、最小插件、事件泵、隔离及Messages代理；Delivery独立进程／
session，不与生产或验收共享历史。只装载现有Delivery instructions、required skill，
以及Host显式启用的efficiency引用；不继承宿主AGENTS、用户配置、全仓库或全局会话。
独立HOME／session store；只读运行依赖与必要方法文本。Host授权的业务补读继续通过
read_delivery_artifact／handoff能力，不增加任意read_role_material或文件路径权限。

DSH没有Codex dynamicTools回调；使用仓库内窄Node Delivery桥：

1. 用ctx.tools.register将session.tool_specs()的名称、说明和inputSchema逐项注册为
   ToolDefinition，使用官方所需的JSON output声明和稳定文本呈现；不改工具语义。
2. execute从ToolRunContext.agent.id和callId取得原生身份，向Python Host发桥接请求，
   由原session.call_tool(name, arguments, call_identity=...)执行。call_identity由
   业务session＋原生session＋真实callId构成，重启后不混用；不使用MCP request序号。
3. Host保存原始工具结果并按原022／030生成模型展示。桥接把该JSON完整返回，含
   ok=false、error、coverage和分页；不能把JSON再压缩成一句成功，也不能把投影
   反给内部Host判据。模型输出仅由原publish_delivery_message对外，assistant文本／
   reasoning／provider错误仍私有，不能直接发布到用户对话。

桥接采用同一私有stdio JSON-RPC传输：仓库启动插件构造官方JsonRpcLineTransport及
HarnessSdkJsonRpcServer，标准请求委托handleRequest；不同时装两个stdin server。
沿官方initialize等待loader就绪、shutdown／flush／root dispose及EOF清理方式，
增加本条必须的Host侧控制方法和server→Host工具回调。工具回调利用transport.request，
主事件泵持续分发双向响应；Python不得在等待工具返回时阻塞处理控制或原生事件。
这属于OntoWeave桥接协议，不冒称官方SDK已经支持；冻结版本和schema供验证。
工具handler通过独立受控执行队列进入原DeliverySession，变更／控制状态串行化；网络
等待不持有整个状态锁。已准入操作可完成，控制原子关闭后续准入，保留迟到回执。

本条选择直接工具桥而非在普通MCP上再补调用身份：当前MCP tools.ts仅传name／args，
不透传ToolRunContext.callId；publish去重和operation身份已依赖真实call_identity。
复用官方工具注册和JSON-RPC解决这个现有缺口，不增加通用MCP扩展或工具框架。

实际工具全集和schema在首个业务输入前核对，并留实际模型请求中的工具schema证据。
未声明工具、shell／编辑器／动态subagent／工作区发现／全局session读取不可用；
宿主真key不进DSH环境／材料／日志。工具未齐或额外能力未去除时只关闭不安全执行，
配置纠正后可重试原目标，不永久杀死业务run。CQ隐藏正文／答案／Judge内容继续由
原投影和材料授权控制，Delivery不因Host地位获得全目录权限。

## 3. 输入、消费与活动结束

### 3.1 普通与活跃输入

- 初次普通输入：session/prompt建立指定session并返回messageId。
- 活跃用户消息及确需决策的Host变化：仓库桥接方法ontoweave/delivery/steer定位本
  进程唯一获准且已创建的session，createUserMessage后调用ctx.agents.get(id).steer。
  返回真实messageId及Host dispatch关联；不接受任意session／目录／模型配置。
  它在最近step边界被领取，不承诺中断已经发出的provider请求。若活动刚结束，
  官方Agent.steer会唤醒同session，避免复制Codex stale-turn热重试。
- 普通事件、明确控制、Host回执保持原来源与顺序；先处理用户控制再派发普通变化。
  一个输入页只有一个在途dispatch，不能因busy切idle再发送同一页；Host队列不与
  DSH inbox重复排队。未送分页沿原顺序，bootstrap只确认自身。

官方SDK缺少活跃输入接口是032的明确增量；只用prompt排下一turn会使长活动期间的
用户消息饥饿，不满足原持续对话／022合同。窄steer沿底层现成方法，较fork SDK或重新
编排会话改动更小，不给模型新控制工具。

### 3.2 账本含义与事件归属

保留delivery_input_dispatch及conversation派发事件，accepted／accepted_by_native对
DSH只表示持久接收。追加dispatch_id、process_instance、runtime_session_id、message_id、
input_id／页范围或用户message_id，重用031原生事件关联；不要将DSH messageId填turn_id。

| 事实 | 必要原件／作用 |
| --- | --- |
| attempted | 发送前Host journal，尚不能确定DSH接受 |
| queued | 官方prompt或窄steer真实messageId，或持久inbox插入，才能确认本页已接收 |
| claimed | inbox非canceled移除、对应turn／step边界；只证领取，不证业务处理完成 |
| settled | 领取所在活动的turn/end及reason；失败、blocked、stopped、max-tokens不能当成功 |
| effect／control | 原Host request、application、授权／控制实际回执；不能从文字或idle推导 |

原始事件按session／seq保存，先通知后RPC返回可稍后补关联，同seq重读不重复推进。
缺口从持久日志核对；不能核对则unknown并保留第一失败，不猜“最近一次消息”。
DSH queued后可按原accepted语义推进“接收偏移”，同时保留该页未消费跟踪及原文引用；
不得只删pending而失去核对入口。恢复按inbox／turn原件分别处理：已queued未claimed
不重送；canceled且无效果可由原恢复通路重送同一事实页；claimed但结局不明先核对
工具账本。attempted但响应丢失时，通过桥接传递的Host dispatch关联及持久消息正文
中的input_id／页或原用户message_id核对；证据不足保持unknown，不自动复制。

活动结束以DSH真实turn/end为依据，结合pending inbox及在途工具；session.status／wait
仅辅助。yield_delivery仍仅记waiting_recorded和end_current_turn建议，模型自然结束后
才标本次推理结束。合法新增输入可让同turn继续step，不误报重复等待；没有变化仍连续
推理／主动轮询是需要实测暴露的合同偏离，不靠伪造idle、强制次数门或kill制造PASS。

## 4. 观察、用户控制和停止

### 4.1 按需决策保持

原observe／record_observation／_deadline_events、v2最小充分输入、主动get精简及按需
补读原样复用，DSH raw events只由适配器归一化实际状态变化；不将每个LLM chunk、
普通工具日志、用量／压缩事件当唤醒理由，也不把未知错误列入心跳白名单。约2秒程序
观察在busy／idle／暂停等待期间继续。就绪、首错误、unknown、明确到期、Host请求
结果及控制变化及时处理，不用模型轮询代替。既有期限只产生一次变化，不新增超时门。

stdin及启用时的ConversationServer保持可用；stdin EOF且没有server时仍记录
supervision_interrupted并结束监督，不永久空等；有server时EOF不吞掉仍可用的用户通路。
DSH事件泵／工具回调不能阻塞这两条输入。用户普通闲聊不自动转生产指令。

### 4.2 区分Delivery在线、生产暂停与撤权

Delivery是接收继续／撤销及观察回执的Host控制者，用户暂停生产不冻结Delivery自身。
生产／验收控制按实际绑定owner分发，暂停范围及证据逐项列出：

- 原Codex协作路径继续原消息／实际ack，不能把queued当生效。
- DSH生产按031接入其Host直接pause／resume及实际进程组证据；不能沿当前
  sourced_packet中“不要freeze”的Codex提示误阻止031接点，也不能先冻结Coordinator
  再等它发ack。通过原Host pause_run／resume_live_run工具到该run的Runner控制面，
  将031控制回执作为record_flow_confirmation证据，核对该校验接受绑定的Host证据。
- 独立验收owner在033前保留其现有控制合同，披露混合路径；不能从生产已停推导验收
  已停。Delivery保持在线和有授权的只读核对，不趁暂停发新生产／验收／修模工作。
  尚未实际暂停的owner写pending，已发调用／未知写入单列，不报全链已冻结。

撤回预算／取消／停止先用原apply_user_control关闭新业务准入并调用已有owner控制，
不等待Delivery模型读到消息。同步在Host handler准入处核对最新权限，防止DSH已缓存
工具schema继续启动工作。stop继续程序核对所有bound owners实际退出及在途调用回执；
未知结果保留，不能用提交停止或DSH进程退出冒称资源已结清。

SDK没有interrupt，仓库窄桥接ontoweave/delivery/interrupt在本进程唯一session上调用
Agent.cancel({kind:'user'}, {keepInbox:true})；它是当前Delivery活动的技术取消，不是
暂停生产按钮，不清inbox、不承诺远端请求取消／停止计费。Host先撤权，保留取消中
已准入工具的完成／unknown；看真实turn结束再决定是否派发取消／撤权说明。stop等待
期间禁止启动新推理，仅程序观察和收回在途回执；最后关闭本轮进程及代理。取消／撤权
后如需状态回复，原session可在已收窄权限下接收控制事实，不恢复额度或业务权限。

## 5. 失败恢复、交接与收尾

继续使用四种第一失败层；参数／格式错误返原调用者纠正，语义定位交Coordinator／
Modeling，平台／运行环境修复走029私有request_host_action→宿主→host_action_result。
Delivery不修改代码、重启平台、派生修复Agent或代审CQ；不把外部故障判模型质量差。

运行时错误保留原进程／session／事件、Host账本及supervision_interrupted。先确认旧
监督者和本轮进程已退出，原持久session可兼容恢复时，用session/resume恢复同一DSH
session，再核对inbox／中断活动、已调用工具／实际写入及有效用户控制，发送最新v2
bootstrap。resume可能修补中断turn，但不证明旧工具未执行；所有产生效果的工具均
通过原账本认领，不因重收事实或更换callId重放start_run／start_evaluation／freeze等。
恢复核清前保持效果性Host准入关闭，只允许原权限下核对；可确定的无关安全工作不被
永久阻断。读取缺口给精确对象、缺失原件及下一步，不能要求新建生产run来修工具错误。

SDK resume拒绝／存储不兼容时保留可恢复阻塞，交Host处理；不得静默新建原生session。
确需替代DSH会话是显式恢复动作，记录新旧身份和丢失历史，基于原账本／所有有效用户
约束／原yield决定及未决项完整bootstrap。缺可靠承接则继续等待Host，不以“新线程”
避开授权对账。它不是030 F3计划切阶段；本条不实现F3策略。是否新增实质建模／fresh
start仍查届时用户授权，Delivery runtime恢复本身不重置起点或增加轮次。

finish_delivery保持原standby／read_only_wait语义，保留Delivery和Team；只明确stop
销毁本轮所拥有的进程／socket／bridge／代理。资源由原Host生命周期负责，模型、
失败workspace、冻结报告及未知写入原件保留，清理残留不能覆盖第一阻塞。不热迁旧
Codex会话、不重建生产资源。原始LLM／压缩／错误事件连同任务、run、operation和
Delivery session关联交034，不在032重做计量或宣称降低token。

## 6. 实施交接与验证

### 6.1 最小改动面

| 文件／合同 | 交接范围 |
| --- | --- |
| modeling_team/delivery.py | Delivery runtime选择／工厂、统一身份、派发回执与未消费跟踪、控制优先和事件泵接点；保留原Session业务函数 |
| modeling_team/runtimes/delivery.py及窄DSH Delivery模块／Node桥 | 原Codex实现保留；DSH start／send／steer／poll／interrupt／close和工具回调，不新增通用编排 |
| 031实际交付的Node装载／stdio／隔离／Messages模块 | 复用真实接口；仅提取两条路径实际共用部分，不先搬空Codex Adapter |
| delivery_conversation.py及原journal读取 | 仅必要身份／消费关联，原回执含义和旧记录可读；不建新消息总线 |
| Delivery instructions／skill／package、Host config文档 | runtime中立的“结束当前活动”及控制说明；不要把native turn、SDK队列或DSH默认工具当权限合同 |
| 原Delivery runtime／session／decision-input／wakeups／conversation／Host actions测试 | 沿原fixture扩DSH协议与控制；不创建只匹配某次生产输出的一次性验收器 |

031若尚未交付，字段和模块落点可机械对齐其后代码；运行时身份、权限、控制、消费与
业务效果分离等决定已明确，不以“待接口”掩盖关键假设。032必须补齐Delivery专有
steer／interrupt／工具回调桥，不能误认为031生产prompt实现已覆盖。

### 6.2 验证映射及反例

| 验收 | 需要证据及核心反例 |
| --- | --- |
| A1／F1、F2 | 原Codex省略配置可运行；独立选择两种runtime，Unsupported精确反馈；固定DSH实际工具全集／schema、模型绑定、允许工具及拒绝shell／额外读取／私有CQ；JSON失败／coverage不丢失、真实callId可重建 |
| A2／F3、F4 | 先通知后响应、busy→idle竞态、同seq重读／缺口、queued未claimed、canceled、claimed未settled分别核对；yield后真实turn结束，稳定等待程序持续观察无重复推理；新变化／明确到期一次／unknown唤醒，不能用SDK wait或工具成功冒充 |
| A3／F4—F6 | 活跃／空闲用户输入保持来源／顺序，长provider调用期间控制先在Host生效，steer于下一step领取；三类暂停owner实际回执，DSH生产冻结时Delivery在线；撤权后缓存工具不得启动新工作，stop期间无新推理；EOF／server／process失败不永久等候 |
| A4／F5、F6 | 发送响应丢失、工具已执行但回执丢失、持久resume修补turn、恢复bootstrap与旧分页并存；旧用户约束、原有效决定、额度／起点、已完成效果、未决Host修复与unknown均保留；不重放已证动作、不静默换session或加生产轮次 |
| A5／F7 | 单独获准026最小链，由实际DSH Delivery推进生产／宿主CQ交接／独立验收／standby及stop；真实application、治理读取及独立L1按原合同，Codex验收／宿主介入／未启用范围逐项披露；局部工具成功、工程测试不等于自主交付或净降耗 |

工程阶段复用现有测试双，不需真实模型授权；实际装载可用固定本地组件检验。真实
推理结束、按需唤醒及有界交付必须由后续有效授权下的DSH调用证明，不从fixture外推。
本次只做文档相对链接／锚点、编号、围栏、需求—设计—验收一致性和diff检查；没有
代码变更，不运行backend／frontend测试或重启服务。

L0只证明Delivery运行时与控制接入；L1须独立于证据生产，不能创建／继续／修复被验收
run或改原件。033前可使用明确披露的原Codex独立路径，不要求先迁全部验收；完整
切换、默认选择及统一用量归034。030 F3／F4仍按原实测启用顺序，本条不提前实施。
实际授权后沿20分钟semantic-start及届时轮次规则，不前置全面审计或保护额度的mock。

## 7. 本轮状态

需求细化与设计已完成；独立设计审阅Round 1 PASS，0 Critical／0 High，无关键未决假设，
见[审阅记录](../records/2026-10-18-r4-3-032-design-review-record.md)。
本条尚未实施，工程、实际L0、独立L1、自主交付、L2、完整切换及净降耗均未验证。

后续工程：2026-10-18用户另行授权按本设计开发与测试，结果及未验证边界见
[开发测试记录](../records/2026-10-18-r4-3-032-implementation-test-record.md)。上述段落
保留设计轮结束时的事实，不将后续工程证据追记为设计轮已有的运行证明。
