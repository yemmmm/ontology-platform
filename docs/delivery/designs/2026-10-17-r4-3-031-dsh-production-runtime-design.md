# R4.3-031 DSH生产Team运行时适配设计

## 1. 范围与核对基线

权威需求：[R4.3-031](../../requirements/requirements-v4.3.md#r4-3-031)，实质决策主表在
该条。本轮授权仅需求细化、设计和独立设计审阅；不实现、不发外部模型请求、不启动／
恢复建模，不消耗建模轮次。设计审阅不代替工程、L0或独立L1验收。

例子：Coordinator向Modeling发送当前获准建模任务。DSH返回messageId时只能显示
“已入队”；看到该消息被inbox实际取出后才显示“已消费”。Modeling提交直接变更后，
application回执证明实际应用，业务完成仍由现有工具结果及独立验收确认。用户暂停时，
本地DSH必须实际停止执行，不能仅停止Runner读日志。

- OntoWeave源码基线：`02f56fe34cc2f0a1735c7d71fe4001dd5f532cce`。
- 本机DSH：`/home/yangxiang/deepseek-harness`，提交
  `687f282e8625c6b8d11ff58211a90524be2e4317`；已跟踪文件无修改；有用户本地未跟踪插件／
  配置，不继承、不清理。此提交是本设计的接口基线，不以浮动master承诺兼容。
- 2026-10-17定向查阅官方[SDK协议](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sdk/protocol/README.md)、
  [SDK服务](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sdk/server/README.md)、
  [MCP桥](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/mcp/mcp-client/README.md)，并核对本机对应源码。
  上游持续变化；实施冻结构建／SDK／锁文件／实际插件清单与摘要，变更版本须重新核对必要差异。
- 当前工作区其他README、029设计、复盘、优化跟踪和演示资料属于既有工作；本轮只改031
  条目、状态索引和本设计／审阅记录，不将相邻需求顺带交付。

### 1.1 实际入口与缺口

| 入口 | 已有能力／当前事实 | 本条必要差异 |
| --- | --- | --- |
| `contracts.py::load_profile`、`_load_package` | Profile.runtime仅codex；Package强制runtime.codex.sandbox | 增加显式dsh分支，选定运行时对应配置才是有效配置；旧Codex合同不变 |
| `__main__.py`生产启动处（当前约4297行） | 直接构造CodexRuntimeAdapter | 在此按Profile选择两种Adapter；不替换验收／Delivery的独立构造处 |
| `runtimes/base.py::RuntimeAdapter` | roster／消息／状态／等待／控制／清理已有边界 | 保留方法，补实际需要的运行时身份和dispatch消费状态，见§3 |
| `runtimes/codex.py::start_roster`、`probe_role_visibility`及配置生成 | 角色私有树、bwrap隔离、MCP服务、材料和权限探测在Codex文件内实现 | 仅抽取两种Adapter实际共用的角色树／MCP启动描述；不继承整个CodexAdapter伪装运行时 |
| `runner.py::_drain_deliveries`、`_relay_flow_message`／`_observe_flow_confirmation`、issue控制、`candidate_progress.py` | 发出回执即ack broker；部分逻辑读agents.thread_id／active_turn_id及turn屏障 | broker ack只表示交给运行时；DSH另记消费／活动，去除所选路径对Codex私有字段的依赖 |
| `transport_mcp.py`、`capability_mcp.py`、`modeling_readonly.py`、`handoff_materials.py` | 实际路由、直接提交、读取及文件引用服务已经存在 | 原schema／授权／业务回执不变，由DSH MCP客户端连接 |
| `model_routing.py`、`deepseek_provider_proxy.py::ResponsesProviderSession` | provider选择、Host持钥、流式代理和等待恢复已有；代理仅POST /responses | 显式DSH原生路由和必要Messages代理，不把Responses直接当Messages，也不改历史路由 |
| DSH `sdk/server/src/server.ts` | initialize进程级绑定；prompt仅入队；event逐session广播；wait为整体静止 | 每角色独立进程／session，持续读事件并按messageId、seq关联；不从wait推断逐消息成功 |
| DSH `core/agent-loop/src/inbox.ts`、`core/agent/src/types.ts` | durable agent/inbox/spliced含插入、移除、canceled；turn/start/end有真实边界 | 用持久事件还原入队和实际消费，无需给DSH核心增加逐消息完成API |

以上是源码及调用点定向核对，不声明GitNexus图覆盖。本轮不改调用关系；实施跨模块改动时
执行适用impact／detect_changes或说明不可用并保留定向调用点检查。

### 1.2 角色与邻项边界

首条验证路径复用026 Task、业务资料和角色方法；显式DSH Profile保持同一roster：
Coordinator、Modeling、competency-question。CQ作者虽在固定roster，仍是私有题目角色，
不能把其题目／答案通过共享目录、事件、对话或资料工具给生产两角色。031负责此Profile
成员启动与权限；033负责独立CQ子任务及Consumer／Examiner／Judge实际验收路径，
不在031提前改写。031可由现有Codex Delivery监督并由Codex独立验收，必须披露混合状态。

024／025直接提交和原子application、015成功回执信任、028既有模型感知及024自查保持。
不恢复Protocol、模型独立dry-run、SHACL或OWL自动推理前置门。较大所选场景所需的
获准文件工作目录和工具沿同一Adapter配置提供；不迁全部历史实验，不新增常驻角色。
032拥有Delivery切换，033拥有独立验收切换，034拥有用量规范化／完整默认切换；031只
提供其后可复用的实际运行身份、事件和资源生命周期，不提前建设统一运行时注册框架。

## 2. 配置与隔离装载

### 2.1 显式选择，冻结有效配置

Profile沿用schema_version 1，将runtime闭集扩为codex／dsh。新增独立DSH Profile引用
原026 packages，避免修改原Codex Profile默认。Package.runtime可同时有codex与dsh；
loader验证已声明块，装配时要求被选择的块存在，禁止从codex.sandbox推断DSH权限。
DSH块仅声明当前需要的read-only／workspace-write文件权限，取值与实际bwrap挂载对齐；
Role.permissions、Task.role_sources仍是能力与材料权限权威，不能用此块扩大。

启动配置示意（尚未实现的合同，不能直接用于现有CLI）：

```yaml
# Profile最小增量
runtime: dsh
# 同一原Package的runtime增量，codex块原样保留
# runtime:
#   dsh:
#     sandbox: read-only
```

Harness二进制／构建路径、固定composition和插件版本由Host装配，不允许Profile／Task
夹带任意启动命令或SDK补丁。baseline记录实际路径、DSH提交与构建摘要、依赖锁、SDK
协议／serverInfo、composition和bridge摘要、原角色instructions／Skills／sources摘要、
最终工具名及schema摘要、请求与有效provider／model／effort。serverInfo版本0.0.1不足以
代替真实提交／构建摘要。不在本条改变全局默认或运行中热切Adapter。

### 2.2 每角色一个进程、一个session

使用Node DSH运行时＋stdio JSON-RPC，在Python Adapter内管理传输；无需额外Python
SDK依赖。进程级initialize适合每角色不同模型／工具；sessionId由Host为run/agent生成，
不是Codex threadId。生成角色私有composition，仅装载agent loop、session／持久化、
system prompt、所选LLM、MCP及必要上下文压缩依赖；以固定DSH组件实际依赖为准。
不用用户全局sdk默认组合减黑名单：其base会带入coding persona、工作区发现及其他工具。
无需修改DSH核心，可增加仓库内窄Node启动入口加载所需官方插件并报告工具装载清单；
该入口不承担任务语义或编排。

- 复用bwrap角色私有树及PID隔离；仅挂载该角色获准sources／Skills／references及可写产物。
  独立HOME、配置、工作目录和session store；不挂整个仓库、真实HOME、兄弟目录、历史
  日志或宿主凭据。DSH依赖构建使用只读必要目录，不带用户插件、.git和开发文档目录。
- 将instructions作为该角色固定system section；按原方法显式加载required_skills。
  原handoff工具只读取已发布引用，不能冒充源文件读取。为DSH补一个窄
  `read_role_material`能力：只接受本角色启动manifest中的material_id和有界offset／limit，
  返回原UTF-8文本、来源摘要及明确分页／读完状态；允许集恰为该角色的instructions／
  Skills／references与Task.role_sources，引用文件仅在原授权范围内可读。不接受任意路径，
  不开放目录遍历、环境读取或通用编辑。启动输入给出material_id与原角色相对路径对应，
  原required_skills的固定正文可直接装入system section，其余按需读。大场景原文件产物
  仍走write_handoff_output等已获准工具，仅开放已批准输出目录。
  不自动启用DSH全局Skill／AGENTS／仓库发现，不把宿主AGENTS和本设计注入隔离模型。
- 工具只有原Team Transport、角色能力、获准读取／交接工具。MCP名称投影使用明确的
  `(serverName, rawName)`映射；公开名与实际schema一致，参数和结构化原始结果保持，
  不从拼接名称反推或修改业务含义。启动后比对实际注册工具全集与预期，不只查有无一项。
- 不装载shell、编辑器、动态subagent、浏览器、全局session查询或任意插件管理。缺少
  必需工具按platform-contract反馈；额外权限未收窄前不开始语义任务。修正配置后可继续
  原目标，不因一次配置错误永久杀死run。
- tools/list与真实模型请求中的工具schema均留证；角色可见性探测包括允许源及隐藏CQ、
  兄弟目录、宿主HOME／环境和未授权路径的拒绝。提示“请勿读取”不能代替隔离。
- Host留存原始全部事件；下发模型的消息只来自原broker及角色材料权限，不能把DSH
  session.event广播原样转发给其他角色。CQ可读其私有种子不等于可把内容发给Modeling。

### 2.3 provider与凭据

首批支持DSH原生`deepseek-official`，由显式DSH模型配置选准确model／effort；本机模型
目录支持`deepseek-flash`及low／high／max等原生effort，必须以initialize精确解析结果
核对。新的运行时路由独立于旧`deepseek-direct` Responses绑定；不把旧deepseek-v4-flash
自动改名成deepseek-flash，不沿旧Codex low→high映射静默改档。现有GLM或Codex订阅
Profile选DSH时若无已交付路由，返回unsupported-runtime-provider/model/effort及原选择，
允许显式改为已获准兼容配置；不自动回退。设计不为任何具体模型新增调用授权。

现有ResponsesProviderSession仅接受/responses；最小新增Host Messages会话代理，复用
持钥、固定TLS上游、流式透传、清理和安全错误方式，支持DSH文本请求实际需要的
POST /v1/messages，向固定DeepSeek Messages端点注入真凭据；DSH只持本轮随机代理凭据。
保留anthropic-version、所用tool-changes beta及必要关联头，不做协议或业务内容翻译。
只读schema注册／模型握手不要求外部模型调用；真实绑定须在届时获准调用中验证。
本条文本任务不开放Files API或图像上传；不引入通用provider目录／代理框架。真实key
不写DSH配置／环境／session日志／Agent材料。代理不记录完整请求体或凭据。

原生重试与Host重试分别记录；流已开始后的错误不自动重放同一请求。代理错误保留
鉴权／额度／限流／网络首因；不得将代理所有非2xx统一成模型质量失败。保留DSH原始
LLM用量／压缩事件和关联头供034读取，031不先做字段归一化或节省比例承诺。

## 3. 身份、消息与完成

### 3.1 最小运行时中立合同

`AgentRuntimeIdentity.runtime_identity`承载真实DSH sessionId；新增只在需要处读取的
Adapter身份查询，替代Runner对`.agents[*].thread_id/active_turn_id`的私有访问。Codex
返回原thread／turn，DSH返回session及真实turn/start的seq。进程实例／restart代次
和session共同参与绑定，不能让新会话碰巧沿用run/agent字符串被当作原会话。

在原RuntimeDispatchReceipt保留Codex mode／turn_id的同时增加DSH分支，最少包含：
`runtime=dsh, mode=enqueue, dispatch_id, runtime_identity, message_id`；DSH `turn_id=null`。
`dispatch_id`是Host本地发送关联身份，message_id是DSH durable enqueue身份；本地ID
明确标为Host关联，不能冒称DSH turn。Codex旧start／steer／turn字段继续读取与输出。

增加逐dispatch状态读取／事件：queued、claimed、settled、canceled、failed／unknown及
对应原始seq引用。DSH活动区间用真实turn/start与turn/end seq；一个活动可有多个step，
不把SDK请求次数当模型轮次。`AgentState`保留旧Codex字段，DSH附原生session／活动
引用和pending dispatch状态；不往last_completed_turn_id填messageId凑旧屏障。

只将当前DSH路径依赖的屏障改为逐dispatch及原业务证据；candidate_progress旧正式
Protocol turn屏障只对Codex历史路径继续生效，不将该旧路径完整迁移设为031前置。
当前直接写入026路径若仍触达旧字段，应在实现中改用上述公共身份／状态，不能以
“返回空值就通过”规避。provider等待、issue恢复及终态守卫必须接入同一身份。

### 3.2 事件处理与竞态

Python持续读取stdio，RPC响应与notification分别分发，等待RPC不能阻塞事件泵。
原始事件按进程实例、sessionId、seq顺序留存；RPC响应关联JSON-RPC id。先到的事件
可暂存再绑定稍后返回的messageId；重读同seq不重复推进状态，gap先从该角色持久log
补齐，缺原件则unknown。不得猜测“最近一次发送”就是本次回复。

`agent/inbox/spliced`先还原各pending列表；找到messageId插入证明queued，非canceled
移除且关联当前真实turn边界证明claimed。此处claimed只证明运行时领取输入，不能
证明已向模型完整提供或业务处理完成。`outcome=canceled`或无turn的删改保持canceled／
待核对；pause不清空inbox。收到本次claimed所在turn/end记录settled及实际reason；
error、blocked、stopped、max-tokens等不得变成业务成功，maxTokensAsSuccess禁用。
保留step和LLM事件供核对是否实际请求。`session.status=idle`、`session/wait`完成都不能
单独把某条未claimed输入判消费，更不能把整个run判完成。

broker的ack_delivery仅结束broker→Adapter交接，含义明确标为dispatched／queued；
原业务回复仍按reply_to_delivery_id与任务身份绑定。DSH消费状态另存原run证据，不把
broker队列删除解释成模型已读。RuntimeMessage只是普通输出，不接受“已完成”文字为
TaskResult；`report_task_result`仍由原工具和终态依赖校验产生。

busy时session/prompt作为后续普通turn入队，不能宣称等价Codex steer。控制无需等消息：
用户pause／abort由Adapter直接执行；技术反馈／补充消息沿队列送达。迟到消息落入尚未
确认的终态时，先撤回候选完成状态并处理pending；已接受业务终态的角色不被自动重启，
保留迟到原件并按原路由返回可定位反馈，原run等待必要处置。并发提交结果与发送由
Adapter串行化状态更新，避免先判完成后丢消息；不增加常驻调度服务。

`terminal_report_blocked`仅保护实际未消费的必需交接、未知写入及原终态依赖。当前活跃
turn内部调用报告工具是正常行为，不能要求调用者先idle／turn/end才准报告，否则死锁。
可纠正错误给准确反馈并保留run；TaskResult接受后等待已发工具回执和本地资源收尾，
`wait_settled`返回整体静止不代表独立语义通过。

## 4. 暂停、provider等待与恢复

### 4.1 本机暂停使用进程组冻结

本条选择Linux已有SIGSTOP／SIGCONT控制，不虚构session/pause或让SDK resume承担
取消语义，不为暂停fork DSH核心。每角色启动独立session／进程组；记录Host侧PID、
PGID、进程启动身份及该组后代。动态spawn／shell已关闭，MCP本地shim继承该组。
Host的broker／能力服务／观察循环及provider代理不随角色组冻结，继续保存回执。

当前Runner.receive_outer的pause／resume仅经`_relay_flow_message`发送给Coordinator，
`_observe_flow_confirmation`以自然语言JSON确认生效，并未调用Adapter.pause。这是本条
须补的实际接点：DSH分支直接绑定原request_id执行Adapter.pause／resume，Host控制
回执作为实际生效证据；原用户消息保留于Host账本，在恢复时按需要转告Coordinator。
不能先冻结Coordinator再等待它ack，也不把其文字确认当冻结完成。Codex原协作分支保留。
关闭dispatch时原drain仍读取事件和保存回执，新增消息留在broker，不能丢弃或ack成消费。

暂停顺序：

1. 在原Runner控制下阻止新任务／消息dispatch及新的能力写入准入，记录已有在途调用；
   该控制与写入准入检查使用同一锁边界，不能check后又在暂停窗口偷偷派发。
2. 对各角色组SIGSTOP并核对所有所拥有DSH／MCP子进程实际为停止态；有新后代须纳入
   本轮核对，bwrap外壳停止不等于内部Node停止。逐组失败记录具体身份，不宣称全run已暂停。
3. 读取已准入application调用结果。之前发到后端的写入可能在暂停之后提交，暂停不回滚
   它；按既有Batch／application查询对账。可确认则记录，不能确认保持unknown。

“本地执行已冻结”和“平台写入已核清”分别报告；本地冻结后可标PAUSED，但必须带在途／
未知写入，禁止把PAUSED解释成无写入。没有全组停止证据时保持pause-pending并返回
runtime/infrastructure可操作错误，用户stop仍可执行。代理可结束此前已发送的云端LLM
请求，冻结不保证供应商取消／停止计费；返回数据在Host安全保存或缓冲，不能在暂停期间
触发新的模型请求或工具apply。031不将云端取消作为暂停承诺。

resume先核对有效授权和原run／进程身份，核对未知写入；涉及未知资源的写入继续关闭，
安全的无关工作可继续。解除相应准入门并SIGCONT原组，原session／inbox／历史保持，
不重新start_task、不追加业务轮次、不重放已确认的工具操作。连接在暂停中超时则按
原始错误进入provider／工具恢复，而不假定SIGCONT能让网络请求成功。

### 4.2 可恢复provider等待

复用现有provider_wait_status／recover_provider_wait调用形态及Runner issue账本，在
RuntimeAdapter正式声明所选路径所需的可选方法；Codex实现不变。记录准确role／session／
wait_id、原请求或活动、原因及recovery状态；错误来源可用DSH step／LLM事件和Host代理，
不能仅靠文本匹配或idle推断。用户显式暂停优先于自动provider重试。

鉴权／额度／限流／网络错误耗尽本次原生有界重试后，保留run并进入可恢复等待；Host
修复凭据／环境后，按原控制epoch、wait_id及session核对，向同一session发送获准恢复
说明并等待实际claimed／新活动。消息入队后仅标恢复已提交，看到执行才标恢复已生效。
Coordinator自发恢复自身的原有避免自等待逻辑保持；不因DSH enqueue不是start/steer
触发旧mode硬拒绝。未知模型写入先核对再接续，恢复说明不重发旧apply内容。

SDK session/resume只用于进程意外退出后恢复原持久session，不能把它当用户继续按钮。
持久session可读且写入已核清时方可恢复；新进程有新实例身份，旧失败证据保留，恢复
过程不能自动追加语义任务。若恢复会新开实质修模／fresh production start，先核对届时
轮次授权；没有授权不启动。缺持久历史／兼容性不符时保持可定位阻塞，不静默开空会话。

## 5. 停止与资源完整性

stop先关闭新dispatch／写入准入，清点在途请求。暂停中的角色组先安排终止，再SIGCONT
让其处理终止／退出，不能先放开业务准入。活跃组发送SDK shutdown并等进程退出；失败
按本轮已记录进程身份TERM→有界等待→KILL，不按模糊进程名或整个用户session杀进程。
原始日志／失败目录留存；只清理本轮进程、shim、socket、代理、临时凭据和本轮资源。

清理前核对Batch／application及既有资源生命周期：保留非空模型，未确定写入不盲删／
重建；沿原retain_nonempty策略。cleanup_identifiers返回本轮DSH session、PID／PGID、
代理／socket标识及残留核查结果；Host私有信息不转给生产Agent。无残留证据才能报告
清理完成；清理失败保持原首阻塞并附独立cleanup缺口，不覆盖原失败。quota／授权不
写成Adapter尝试次数硬门。

## 6. 实施交接与验证分层

### 6.1 最小变更范围与次序

1. `contracts.py`、原026 Packages增DSH块、独立DSH Profile和显式DSH模型配置；
   `__main__.py`仅生产装配分支。模型配置只交付已支持精确路由，不改旧默认。
2. `runtimes/base.py`加逐dispatch／原生身份合同，新增`runtimes/dsh.py`及最小Node
   composition／启动入口；从`codex.py`提取已实际重复的私有树／MCP启动小块。
   保留Codex配置和原事件／证据读取，不重写整个运行时层；`capability_mcp.py`补
   上述只读角色材料工具，原handoff输出能力保持。
3. `runner.py`所选路径及必要屏障读公共身份／状态；外部pause／resume直接调用DSH
   Adapter控制并以实际状态确认，不依赖被冻结角色的协作确认；provider等待与issue恢复接收enqueue
   并以真实消费确认。`transport_mcp.py`继续原业务校验，仅必要终态竞态接点对齐。
4. 原provider会话模块旁增加窄Messages代理和精确DSH模型路由，复用持钥／清理；
   保留runtime身份／LLM／压缩事件供034接入，不在031重做usage报告。
5. 补RuntimeAdapter合同与DSH工程测试；修改实际选用的Host说明与配置用法。本轮设计
   不直接修改活跃角色instructions／Skills。当前若只改modeling_team无需产品服务重启；
   若后续实现确实改backend／frontend则按AGENTS完整测试并重启验证。

实施若发现固定版本无法装载所需最小权限或运行身份，报告具体缺口，修最窄层；不能
先增加新治理／恢复框架或偷偷降低验收。版本升级是需定向重核的技术选择，不是重开
业务语义或模型授权。031工程交付不以032—034完整就绪为前置。

### 6.2 与权威验收的对应证据

| 条目／层级 | 必须覆盖的行为与反例 | 实际证据 |
| --- | --- | --- |
| A1 工程 | 两种runtime解析、旧Package可读；缺DSH块／不支持provider准确反馈；角色材料、实际工具全集及schema一致；禁止全局配置／隐藏题／兄弟目录／真key | fixture合同、真实隔离进程探测、工具清单／请求schema及冻结baseline；只列配置不算实际装载 |
| A2 工程 | 通知早于RPC回执、busy排队、快idle、两条输入相邻、取消移除、seq重读／缺口、报告与迟到消息竞态；无idle→业务成功推断 | 原事件与dispatch投影逐项关联；工具report只认原绑定，未知保持unknown |
| A3 工程／本地L0控制 | 活跃／空闲暂停、全部角色组实际停止、暂停前apply迟到、未知写入不重放、长暂停网络失效、用户pause优先、provider等待后同session恢复、进程死后安全恢复、停用中cleanup | 本轮PID／PGID与进程状态，Host在途／Batch查询，原session／wait_id／control_epoch及首次新活动、资源残留核查 |
| A4 真实L0 | 在届时单独获准的026运行中，三个真实DSH成员按权限工作；Modeling调用024／025提交，原平台返回有效application；沿原合同完成必要治理自查 | 真实模型／MCP调用、候选／显式变更／application身份、模型版本和原始读取；不得以mock或一条SDK回复代替 |
| 邻项独立L1 | Consumer／Judge按冻结题集实际治理读回独立裁决 | 由033或明确披露的保留Codex验收路径交付；本条不自行判模型质量 |

工程测试允许fake provider／确定性事件fixture验证故障控制，不把mock run前置到下一次
真实建模。真正授权运行后只做安全启动必要检查，遵守20分钟semantic-start规则及默认
三轮计数，技术纠错不重复计轮。完整业务、L2重复性、全链DSH和净降耗均分别待证。

## 7. 决策与本轮状态

D1—D8主表见权威需求。当前无待用户决定的关键业务／范围／授权项；实际模型、额度
和运行时点留在后续明确运行授权，设计不代填。独立审阅见
[设计审阅记录](../records/2026-10-17-r4-3-031-design-review-record.md)。

当前状态：需求／设计完成，独立设计审阅Round 1 PASS：0 Critical／0 High，无关键
未决假设。未实施；工程、L0、L1和净降耗未验证。审阅后仅同步本状态，不改§1—6方案。
