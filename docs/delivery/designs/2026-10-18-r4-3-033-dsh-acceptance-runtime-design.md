# R4.3-033 DSH独立验收运行时适配设计

## 1. 目标、授权与当前基线

权威需求：[R4.3-033](../../requirements/requirements-v4.3.md#r4-3-033)，实质决策以其
D1—D8为主表。本轮仅需求、设计与独立设计审阅；不实现、不请求外部模型，不启动／
恢复生产、修模或真实验收，不消耗或追加建模轮次。设计通过不代表工程、L0或L1通过。

例子：Q1—Q5同批最多三个Consumer作答。Q2进程退出无报告，其他任务继续，之后
Judge只裁决具备有效回答和证据的题；Q2留在全分母，整批不能PASS。若Q3提交格式
错误，原sink准确返回缺少的绑定，Q3在原session修正即可，不重启整批或修模型。

### 1.1 所查事实

- OntoWeave基线提交：`4d9bc85`（032设计交付），核对日期2026-10-18。
- 本机DSH：`/home/yangxiang/deepseek-harness`，HEAD为
  `687f282e8625c6b8d11ff58211a90524be2e4317`。已跟踪源码无修改；存在本地插件、缓存及
  图片等未跟踪资料，不读取为角色输入、不继承全局配置、不清理这些用户文件。
- 定向核对同提交DSH `packages/sdk/server/src/server.ts`：prompt调用followup并返回
  messageId；session.event含原生seq；wait只证明静止且可能抛原Agent错误。turn/end与
  status通知都不是业务报告。`packages/mcp/mcp-client/src/tools.ts`保留稳定工具映射、
  content／structuredContent及isError，不需要为本条建立Delivery专有callId桥。
- 031已审设计及并行工作树中的`runtimes/dsh.py`、`dsh_build.py`、`dsh_events.py`、
  `dsh_node/entry.mjs`、`messages_provider_proxy.py`可作为必要组件复用候选；
  [031开发记录](../records/2026-10-18-r4-3-031-implementation-test-record.md)当时仍标最终全量
  运行中，未有真实A4／独立L1。本设计不接管或修改这些文件，不把未提交实现作为已交付
  依赖。实施时对齐最终接口名称／字段，不重开业务决定。
- 工作区含029、复盘、演示及031的未提交／已暂存工作。本轮仅负责033条目、适配组
  状态、本设计与审阅记录；同一需求文件其余既有变更保留且不混入本次提交。
- 本轮只做已知入口与调用点核对，不改代码调用关系、不声明GitNexus图影响覆盖。后续
  跨模块实现按AGENTS使用impact／detect_changes；不可用或索引陈旧时披露并检查调用点。

### 1.2 当前入口与必要增量

| 当前入口／合同 | 核对事实 | 本条增量 |
| --- | --- | --- |
| `__main__.py::_cq_run_platform_session` | 直接创建CodexRuntimeAdapter；正式逐题与public-feedback共用 | 用显式验收runtime选择窄实现，不由生产runtime推断 |
| `_cq_run_platform_questions` | 三线程，每题单独packet、adapter、报告／observable／teardown | 保持调度，给每题绑定实际runtime身份，继续空位接续 |
| `_cq_execute_batch` | 模型前后读、响应留存／重验、judgeable过滤、Judge分组，Judge直接构造CodexAdapter | 只替换子任务构造接点；保留绑定、评分及完整分母 |
| `runtimes/codex.py::launch_v3_acceptance_child／run_v3_acceptance_child` | 装私有树／proxy／sink，接纳报告、部分报告留存、retained owner | 保留Codex；增加DSH v3子任务等价入口，不能只调用031 start_roster |
| `acceptance_runtime.py::AcceptanceBatchPacket／ScopedReadProxy／ReportSinkServer／V3BatchReportContract` | 题答隔离、范围、真实响应、冻结原文读取、报告绑定已存在；v3格式拒绝可纠正 | 复用原实例与schema，不建新裁决器或改成普通文字报告 |
| `evaluation_owner.py::EvaluationOwner` | 当前直接读thread_id、_child_agent、adapter.agents；控制、保留、只读追问、关闭 | 给所选子任务增加窄身份／控制／输出／资源接点，DSH不填伪thread ID |
| `delivery_ops.py::start_evaluation`、`host_ops_mcp.py`、Delivery工具及CLI／只读接续 | 已冻结operation请求、模型profile／题集／输出根，当前未传runtime | 原启动链传递runtime并绑定到request／回执，保持权限与去重 |
| `model_routing.py`与031三角色DSH Profile | 验收查canonical package ID：platform-examiner及acceptance；现DSH Profile无这两项 | 新显式验收模型Profile，精确校验所需角色，不自动使用生产绑定 |

## 2. 范围、选择与装载

### 2.1 当前路径清单与配置

本条支持当前`cq-acceptance`公开／隐藏批次、`public-feedback`公开生产诊断，以及当前
调用同一正式批次实现的只读验收接续。早期反馈仍无Judge、无正式attempt、不被叫作
独立语义验收。roster内CQ作者沿031适配；题目审核沿029由获准宿主经原私有Host提交，
不新增Harness出题服务、宿主审核Agent或让最终Judge代审题目。历史Lean Source／
Platform／Acceptance、standalone_platform_examiner及旧实验入口继续原合同；不作为033完成门。

新增选择参数为`runtime: codex | dsh`，CLI为`--runtime`，省略codex。Host／Delivery
`start_evaluation`及其工具schema、白名单／调用参数校验、CLI参数组装、operation请求及
expected binding同时增加该可选字段，正式与早期反馈均贯通。只读接续显式传递本次
选择，不借原生产Profile改变验收runtime；仍读旧输入根、写新attempt输出根，不启动
TeamRunner。原请求幂等键／digest须包含runtime；同一operation_id改runtime应按原
冲突合同反馈，而不能返回旧Codex操作假装DSH执行。旧请求／报告缺runtime按codex
解释；新请求必须核对实际报告runtime，DSH请求遇到缺字段不得按默认成功匹配。

runtime独立于生产和Delivery，可混合运行并如实披露。本期同一验收operation的当前
Consumer／Judge统一所选runtime；不增加逐题运行时矩阵或自动回退。031三角色Profile
不得凭继承成为验收模型Profile。新增独立DSH验收Profile，只声明`platform-examiner`
与`acceptance`（public-feedback只需要前者），保持现有RoleModelBinding及profile摘要；
Judge虽然packet.role叫acceptance-judge，绑定键仍为现行`acceptance`。按实际执行角色
验证精确provider／model／requested与effective effort，不要求启动不存在的旧Source角色。
复用031已交付的原生DeepSeek目录与Messages代理，不把Codex effort映射搬到DSH。

配置示意（尚未实施，不能直接当成当前CLI已支持）：

```text
cq-acceptance --runtime dsh --model-profile <显式获准的DSH验收Profile> <原绑定参数>
public-feedback --runtime dsh --model-profile <显式获准的DSH验收Profile> <原公开参数>
```

缺少验收binding或provider／model／effort不兼容，在读取真凭据和创建模型任务前返回
字段级可定位错误及原选择；允许修正后重试。不得自动把deepseek-v4-flash更名、改变档位、
回退Codex订阅或从宿主默认模型补齐。配置正确不构成真实provider绑定验证。原Host工具的service_tier／Codex环境投影也须
按runtime分支：DSH显式fast返回unsupported-runtime-setting，不静默忽略；unset／default
仅表示未请求Codex fast，不能继承MODELING_TEAM_CODEX_SERVICE_TIER成为DSH设置。
固定DSH上下文／压缩以实际composition记录，不套Codex默认窗口或推理上限。

### 2.2 最小实现接点

保留Codex Adapter和现有carrier，新增窄`DshAcceptanceRuntime`实现（建议放
`runtimes/dsh_acceptance.py`），提供当前实际用到的bind／launch／run v3 child、资源身份、
控制、只读追问及收尾接点。factory只有codex／dsh两个分支，不建运行时注册框架、不使
验收继承生产roster Adapter，不强制把全部旧Codex子进程改为新抽象。

可将两条路径确实共用的v3首输入生成、私有树／MCP描述和必要事件／进程控制提成小函数。
原packet、sink、scope及报告validator仍在现有模块；不得导入CodexAppServer来运行DSH，
也不复制整个CodexAdapter。031组件在实现后按实际共用处复用，不先造通用进程平台。

每题Consumer、每个原Judge组各自一个DSH进程、session store及私有树。固定Node组件、
必要插件、bwrap隔离及Messages持钥沿031；不装默认sdk组合或全局AGENTS／skills发现。
仅给子进程随机provider代理凭据，真API key与平台read key由Host／原forwarder持有。
模型输入为本角色原instructions／v3 skill和当前packet／允许manifest，不挂生产run根、
宿主HOME、仓库、兄弟目录、日志或隐藏tester资料。

### 2.3 角色权限与实际工具

| 执行者 | 允许输入及能力 | 必须不可用 |
| --- | --- | --- |
| CQ作者（031） | 原Task.role_sources、出题方法与原草题工具 | 生产写入／语义查询、未获准tester材料；隐藏草题向生产转发 |
| 获准审核宿主（029） | 原私有审核入口及明确授权 | 由Delivery／生产Coordinator／最终Judge代审；隐藏题指导生产修模 |
| 单题Consumer／Platform Examiner | 单题题面／身份、获准范围及原语义读工具、报告sink／必要有界交接 | 参考答案、业务源正文／Judge依据、兄弟回答、写入及生产控制 |
| 独立Judge | 原冻结题答、受限依据引用／原文、已接纳回答和重验真实响应、报告工具 | 平台查询／写入、生产运行工具、任意目录／原日志读取 |
| 保留的Consumer | 原session、原授权治理读及只读咨询输出 | 已关闭报告提交、Judge私有依据、改写报告或生产模型 |

DSH连接原只读与报告MCP shim（不是Team Transport），工具schema从原服务导出；用
显式`(serverName, rawName)`映射核对真实公开工具名。保留完整JSON、coverage／分页、
错误结构及isError，不能把结构化结果压成一句成功。只读代理自身产生并留存响应身份，
报告sink绑定session／packet，故这里无需032为Host operation所需的原生callId双向桥。
可保留DSH真实call ID作日志关联，但不把它改成原proxy句柄或平台业务请求ID。

031的read_role_material若用于instructions／skills，只允许本角色冻结manifest；不得
把Judge业务依据复制到该通道。v2依据仍由原sink的read_frozen_evidence或原受限冻结
material读取通路产生校验回执；普通handoff／启动时挂载不等同实际读原文。报告引用
也必须由原HandoffMaterials recipient权限解析，不能直接打开任意宿主路径。保持现行
已授权交接工具的局部输出能力，不开放对输入／冻结依据／旧证据的编辑。

冻结记录实际DSH提交／构建、依赖锁、composition／插件、启动桥摘要、原角色材料、
实际工具全集及schema、题集／packet、精确模型绑定。只有serverInfo版本号不足以证明
同构建；这些Host私有原件不广播给生产或盲测角色。

## 3. 原验收数据流与身份

沿原carrier顺序执行，不增加评分或自动语义校验层：

1. 核对原授权、visibility、freeze、handoff及runtime／精确验收模型配置。验收不创建或
   接续生产run，不写StartLedger。技术准备错误返回原Host可操作反馈。
2. 原Host通过McpReadForwarder实际观察授权模型，得到本批pre_binding；handoff只是
   允许范围，不用其旧digest代替现场状态。每题packet绑定同一批实际模型状态。
3. 复用三任务调度；每题DSH Consumer经独立ScopedReadProxy读治理接口。Host留存
   canonical请求／响应、授权tool及摘要、artifact定位。`p0`等ID在本session解析，先
   验证原回执／文件及范围再交Judge，不能用另一个题的同名句柄或仅用模型自述。
4. Consumer报告经原V3BatchReportContract／sink逐题接纳；已接纳后内容固定。全部
   Consumer结束／失败后，原程序重验报告证据与模型post_binding，漂移不产生有效PASS。
5. 保留原judgeable判定：有完成／未回答的合法报告、真实平台响应及可解析冻结依据才
   能进入Judge。沿006 v1内嵌／v2引用及007无损响应registry／体积分组，原分组顺序，
   不新加逐题Judge流水。资料未知不擅补答案，模型不能裁定自身通过。
6. 独立DSH Judge在自己的session读取需要的原文并按原四态逐题提交；原sink核对
   question／version／freeze／model_binding与证据／source-read回执，不从自然语言猜裁决。
7. 按原完整题目顺序归并原分母，保留未执行、runtime-incomplete、待复核及未通过项。
   子任务启动但无报告的“已启动事实”与报告合同中的“未执行项”可同时存在，不改原
   executed算法。报告完成后沿原owner保留／退出路径收尾。

最小运行关联追加到现有question-task、sessions、teardown及原始事件，避免改变packet
精确字段或摘要算法：

| 身份组 | 内容及解释 |
| --- | --- |
| 原业务绑定 | run_id、attempt／输出根、batch_id、visibility、freeze_digest、model_binding_digest、question_id／content_version、Judge组身份、packet_digest |
| 实际执行 | runtime、process_instance／PID启动身份、原生sessionId、模型Profile及精确角色binding、构建／工具／材料摘要 |
| 消息与活动 | Host dispatch_id、真实messageId、session事件seq及turn/start／end活动引用；没有回执的messageId保持null／unknown |
| 读与报告 | 原proxy响应句柄／摘要／artifact、source读取回执、接纳报告／verdict摘要及其接纳顺序、首失败及收尾 |

DSH不向thread_id／Codex turn_id填session或messageId。旧Codex原字段保留，新owner读取
统一runtime identity。相同字符串session名的不同进程代次也不可混绑；新attempt不能覆盖
旧session目录或原题目任务记录。只增加维持绑定所需元数据，不新建数据库表或服务。

## 4. 消息、报告与可恢复错误

### 4.1 分开四种事实

- prompt响应仅表示持久入队；agent/inbox/spliced原生事件证明领取，turn/start／end
  证明活动边界。复用031 seq重读／去重与事件缺口处理，通知可能早于RPC响应。
- 单次tool成功不证明语义结果。只有原sink实际接纳的报告进入回答／裁决集合；即使
  只有报告引用，也先展开校验再接纳。sink响应丢失时查Host已接纳列表／绑定，不盲重提。
- 报告完成不等于进程退出。DSH成功报告后等待原活动和在途调用稳定，在所选保留策略
  下关报告入口并保留Consumer，或按原生命周期销毁本题资源。不要求杀进程才能腾出
  三题并发名额；已完成只读保留会话不计正在作答。
- idle、wait返回、空自然语言或turn/end无报告均不产生PASS。保留已接纳的部分报告，
  在原有界结束窗口检查真实任务状态，未齐时记录技术未完成；不无期限等一份不会来的
  报告，不强制每个step都成为业务报告，也不将SDK maxTokens结束当成功。

报告已接纳与超时／退出／停止竞态由同一资源锁顺序核对；若报告先被接纳，保留其有效
内容并单列后续技术异常／清理，不能覆盖成“未报告”；若关闭先发生，迟到输出留作诊断，
不再改变已固定报告。完整批PASS继续要求原绑定与全分母，不由所有进程退出推导。

### 4.2 反馈、归因与恢复

复用当前v3 sink可纠正分支：格式／缺字段／参数错误返回类型、对象／question、绑定及
修正办法；同session内可再提交未被接纳的报告。已接纳报告不可覆盖，冻结／模型漂移／
越权证据仍不能PASS。保留必要输入与授权硬门，不移植legacy report三次拒绝门、单turn
或Codex-specific ExaminerRunMetrics推理次数／首turn字段守卫。DSH真实原生用量和
活动另记；缺token／TTFT保持unknown，不因缺Codex指标使run死亡。

| 现象 | 当前所需处理 |
| --- | --- |
| Consumer明确没有回答／无结果，仍有真实合法读取 | 沿原unanswered与证据交Judge，不从空召回直接判模型缺失 |
| 原材料与参考答案冲突／范围有歧义 | 原question-answer-review，保留分母及待复核；不由适配器改题／改分 |
| proxy／sink参数或报告格式错 | platform-contract或实际可证层；可定位纠正，不永久杀死run |
| provider鉴权／额度、限流、断流、session不存在、进程异常 | 保留第一runtime/infrastructure或实际routing层；有界等待／原控制，非模型质量结论 |
| seq缺口／身份未知／回执丢失 | 保留unknown，重读原事件或Host原接纳记录；不能当idle或自动重放 |
| 模型状态漂移／响应文件无法重验 | 原校验禁止有效PASS，保留回答及差异；修复或新只读attempt沿既有路径 |

归因仅沿仓库四层；现有legacy error code可作为内层原因保留，不能创建第五种顶层。
证据不足保留未定位及下一步，不以强行归责为恢复门。provider等待、用户暂停与执行
期限按原账本区分；暂停不消耗本任务有效执行期限，不承诺供应商取消或停止计费。

错误修正／技术恢复能安全继续时保持原session、packet与目标；不新增自动重试循环。
DSH进程重启恢复指定持久session须先核对sink已接纳集合、未完成工具／请求、原seq与
输入状态再允许继续未决题，不自动发bootstrap并重做已接纳题。原session不可恢复或
原只读接续本就使用新会话时，另记attempt与输入／模型绑定、失败原件，按原接续要求
重新取得有效证据；不将跨attempt碎片合称一次会话通过。冻结／授权变化仍需原决定，
不创建新生产start，不追加修模轮次，也不让验收者修平台或模型。

## 5. 三题调度、owner控制与收尾

保留027的线程池／每题独立adapter。五题覆盖乱序与立即补位，不足三题直接执行；每题
独立proxy／sink／本地句柄。共享Host forwarder可保留，但凭据、返回路由和response
persistence保持原隔离，不允许一个题看到另一个题的上下文。绑定漂移是批次正确性
问题，不以“其余题继续”绕过；一个任务失败不应吞掉其他可安全运行任务的证据。

`EvaluationOwner`仅补所选DSH接点：统一身份、普通／活跃只读咨询派发、输出接收、
成员暂停／继续／退出及生命周期查询，不再直接把DSH塞进Codex agents字典。必要时
Codex分支保持原字段及行为，DSH走窄resource方法；不建设通用多机控制器。

- **暂停**：owner先关闭后续题／Judge组准入、记录请求ID与目标成员；DSH复用031
  实际PID及后代进程冻结，逐一确认停止，不能等模型领取或靠一句“已暂停”。暂停中
  owner仍可接输入及读取Host回执；freeze前已发读取／report可在Host结束，按接纳锁
  核对。启动中成员绑定时在首prompt前应用同一pause epoch，不越过准入。
- **继续**：原进程／session继续，实际解除冻结及原身份可核对；不重复题目或已接纳
  报告。正在生效的控制请求不能被更早的ack／迟到resume覆盖。旧Codex协作确认按
  原合同及实际限制披露，混合状态不报全体DSH暂停。
- **保留与追问**：Consumer报告固定后关闭sink报告入口，停止作答watchdog，保留
  原授权治理读／原session供只读追问，owner在线。普通咨询只面向被选择的Consumer，
  不广播Judge依据；活跃输入如需最近step领取，复用032已交付窄steer，或直接复用同一
  DSH底层Agent.steer接点，不能将next-turn prompt伪装活跃steer。追问不重新提交／
  覆盖报告，不补算原批通过，不把只读保留会话算作仍占三题名额。
- **停止**：先停止准入及咨询派发，关闭报告可写窗口；在途报告按实际接纳顺序核清。
  只终止本operation拥有的DSH／shim／代理及socket，冻结成员在业务准入关闭后解除
  冻结并退出；实际核对后代及owner退出，不只发SIGTERM就宣称清理。取消provider
  请求／停止计费不作承诺。若有多个成员／组，逐个收尾，保留部分结果和首失败。
- **证据与清理**：按原retained owner生命周期保持forwarder、线程与资源，最后统一
  停止；不能因worker退出触发bwrap die-with-parent杀死保留Consumer。销毁前将本次
  原始session／事件、报告与脱敏配置留在原Host私有evidence，排除key／token文件。
  清理只删临时输入树／随机凭据，不删原run／freeze／报告或DSH用户目录。残留另记，
  首失败不得被清理错误覆盖；本条不触碰生产retain_nonempty／Ontology生命周期。

## 6. 实施交接与验证

### 6.1 最小改动集合

1. 在原CLI／Host／Delivery启动和只读接续参数中贯通runtime、expected binding及报告
   核对；原默认Codex。补独立DSH验收Profile与实际角色路由校验，保持schema版本及
   package ID含义，不改变现有packet精确字段。
2. 增加DSH验收实现及resource，用031实际已交付的装载／私有树／JSON-RPC事件／
   Messages代理／PID控制小块，连接原MCP、sink、proxy及v3角色方法。当前031专用
   production entry若写死capability服务，增加窄参数或独立小入口，不让验收加载生产工具。
3. 只替换Consumer和Judge构造点，对齐EvaluationOwner实际身份／控制／保留／关闭，
   保留早期公开反馈的非正式属性。调整v3公共首输入中Codex专有工具名称／调用说明，
   精确匹配DSH最终schema；不改题目内容、评分标准或产物表示边界。原v3角色及skill的“模型
   record_flow_confirmation后等待”只适用原协作分支；DSH装载说明对齐Host实际冻结，
   不能把模型确认当实际暂停的前置条件，也不能将SIGCONT后继续误解成等待另一条模型
   resume消息。保留原scope／已接纳报告及控制来源，不改Codex历史指令合同。
4. 按下面矩阵验证并记录，工程提交前做GitNexus或披露的定向影响检查。本次不实施。

以上不涉及backend/frontend、平台API、数据库表、业务专用字段或新服务。若实施确需
改变这些边界，先指出具体不兼容证据并重新核对权威范围，不将其当作适配自然扩展。

### 6.2 需求—验证矩阵

| 验收 | 有界验证与核心反例 | 证据层级 |
| --- | --- | --- |
| A1 | Host／Delivery工具到CLI选择贯通，operation重试及改runtime冲突；早期反馈／正式／只读接续均实选DSH；缺两验收角色、模型不兼容／显式fast、旧记录／默认Codex | 工程／本地装载，非真实provider |
| A2 | 固定真实Harness向本地确定性Messages fixture装载，核对真实模型请求工具全集／schema及输入；Consumer不见答案／兄弟／源正文、Judge无平台写控，额外shell／全局session／宿主文件拒绝；冻结原文原通路回执 | 实际本地隔离／合同，不证明业务质量 |
| A3 | Consumer真实经proxy留请求响应；两个session同名p0不可混用，wrong packet／freeze／version／响应摘要拒绝；Judge v1／v2原文／无损分组，正常未知与四态全分母；漂移／篡改不能PASS | 工程功能；真实治理读与语义另证 |
| A4 | 五题峰值三、先完成者补Q4／Q5、单／两题；单题失败其余保留。活跃／空闲／provider等待及晚绑定暂停、真实继续，完成后保留咨询、明确stop、线程及后代退出 | 确定性调度＋实际本地进程控制 |
| A5 | 通知先到、相邻输入、seq缺口／去重、迟到／丢回执；报告先接纳后进程退出与反向竞态，空idle不通过；同session报告四次纠正仍可接纳，缺Codex指标不阻断；部分报告及恢复／新attempt、不盲重放、残留 | 工程与失败闭合，非semantic PASS |
| A6 | 另行获准后，复用026当前冻结和031实际模型、独立DSH Consumer治理读取＋独立DSH Judge全分母裁决；保留失败、介入及非盲标记，公开／隐藏分批验证 | 真实L0与有界独立L1分别判断 |

优先扩展现有`test_r4327_parallel_cq.py`、`test_r3011_acceptance_runtime.py`、
`test_r3012_platform_responses.py`、`test_v43_judge_references.py`、生命周期／operation绑定
及031本地装载fixture，DSH专有新测试放窄模块。不为本次输出写一次性语义裁判。
按仓库在backend运行`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`；
改Host/MCP合同须同步当前接口文档。若后续实现触及backend/frontend，再按AGENTS运行
对应全量与服务重启／健康检查，不能以Team测试代替。本轮文档不启动这些测试或服务。

真实授权后不以前置全面审计／新harness挡住20分钟semantic-start；033自己的独立只读
验收不计新建模轮，仍须有效授权。031真实模型暂缺时可先完成本地工程，不伪造A6；
032未交付也可由原Host启动DSH验收，明确Codex残余。更大业务、L2／L3及034统一计量／
默认切换不前置最小链L0／L1；适配不降低独立性或完整业务范围，也不预设净降耗。

## 7. 审阅与完成状态

需求细化与详细设计完成；独立设计审阅Round 1 PASS，0 Critical／0 High，结果记录于
[独立设计审阅记录](../records/2026-10-18-r4-3-033-design-review-record.md)。
无关键待用户决定项。D1—D8主表位于权威条目，F1—F7与A1—A6对应上述设计及验证。

本轮交付只建立可实施设计与其独立审阅证据；不证明033工程、真实L0、独立L1、自主交付、
L2、全链DSH切换或整任务成本改善。既有失败与授权保持原范围。
