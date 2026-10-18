# R4.3-034 DSH用量对账与完整切换验证设计

## 1. 范围、授权与事实基线

权威范围为[R4.3-034](../../requirements/requirements-v4.3.md#r4-3-034)，D1—D8以该条
决策主表为准。本轮仅细化、设计和独立设计审阅，不实施、不改默认配置、不请求外部
模型、不启动／恢复建模、修模或真实验收，不追加轮次。验收项是未来验证目标。

例子：DSH返回未缓存输入40、缓存读取60、缓存写入0、输出20。019统一总输入应为
100、缓存60、未缓存40；不能将DSH的inputTokens=40直接当总输入后再减缓存。
同一压缩请求出现在代理数值回执和compaction/summary中，只计一次，同时列为压缩
子集；失败压缩即使没有summary仍可能产生成本。Delivery转给宿主的工作也计入全任务。

核对日期2026-10-18；OntoWeave代码基线`f34fe1f`。工作区已有README、029、复盘、
需求及演示材料变更，本轮只修改034及其索引、新设计和审阅记录，不接管其他工作。

| 基线 | 已有事实及本条缺口 |
| --- | --- |
| 019 `usage_report.py`、`usage_capture.py`、[使用说明](../../../modeling_team/references/model-usage-report.md) | 已有显式scope、逐响应去重、累计段、快照核对、双视图对账及JSON／Markdown报告；身份／累计仍以Codex thread为主，不能直接接DSH的分离输入桶 |
| 031 [开发记录](../records/2026-10-18-r4-3-031-implementation-test-record.md) | 工程／本地DSH装载控制有证据；真实provider L0、application、独立L1待证；Delivery／验收仍Codex |
| 032／033 [Delivery设计](2026-10-18-r4-3-032-dsh-delivery-runtime-design.md)／[验收设计](2026-10-18-r4-3-033-dsh-acceptance-runtime-design.md) | 已独立设计PASS，尚未实施；034消费其实际绑定／原件，不以设计当运行证明 |
| `runtimes/dsh.py::_record／_pump` | Host私有dsh-wire／baseline等原件已有agent、session、process_instance；角色看不到run evidence。共享Messages代理attempt还没有逐请求唯一身份、起止及角色归属 |
| `messages_provider_proxy.py::_MessagesHandler.do_POST` | 原字节流透传，不保存响应正文；当前只记录usage_session_id、HTTP状态等，未采集usage；不能拿请求数当响应数或费用 |
| `delivery.py::_run_delivery`、`__main__.py::_cq_run_platform_session／_cq_execute_batch` | 当前构造Codex运行时；不能仅把生产Profile改DSH就声称全链迁移 |
| 030 | 首批F1／F2已实施，F3／F4尚未实施／启用；034不代为建设短线程或连续编排，比较中冻结实际启用项 |

本机DSH固定源码基线`687f282e8625c6b8d11ff58211a90524be2e4317`，只读核对：

- `packages/llm/llm/src/types.ts::TokenUsage`声明inputTokens为未缓存输入，三输入桶
  互斥，reasoningTokens包含在outputTokens内。
- `packages/llm/llm-deepseek/src/translate.ts`把Messages原始字段映射为上述桶；流内
  usage更新为覆盖值，message_stop时才产出最终usage；初始input／output为0，不能
  将此默认值冒充provider实际提供。
- 同目录`adapter.ts`请求带`x-deepseek-harness-session-id`及压缩时的
  `x-deepseek-harness-compact: 1`，可在本机Host代理读取身份／用途，无需另造LLM桥。
- `packages/llm/token-meter/src/usage-projection.ts`累计assistant/message／attempt，
  同turn／step替换最新值，重试另算；不累计compaction/summary。因此不能作全费用总量。
- `packages/compaction/compaction-basic/src/summarizer.ts`以purpose=compaction调用LLM；
  `region.ts`成功后保存compaction/summary及usage；失败／重试不保证都有summary。

[DeepSeek官方兼容说明](https://api-docs.deepseek.com/guides/anthropic_api/)确认Messages
端点及兼容范围，但未单独完整定义上述计费桶。上述字段结论来自固定Harness源码，
不是已完成真实账单核对。实施必须以保留provider数值／定义证据校核所用映射；不匹配
则报告definition_unknown／conflict，不能用通用Anthropic或Responses字段名猜公式。
本轮仅源码／调用点检查，无代码变更，不声明GitNexus图覆盖。

## 2. 最小接入与证据流

继续用019的Host离线scope→归一化→去重／累计核对→任务／账单／覆盖报告，不新增
数据库、公共API、UI、监控服务、常驻Agent、独立统计平台或运行完成硬门。

1. 031／032／033在已有baseline／operation／session记录中留存实际runtime、原生
   session、进程代次、角色、模型／effort、构建／插件／schema和资料摘要。034只补
   计量必须的关联；023／024等生产与写入合同不变。
2. Host在Messages代理注册已启动原生session到task／run或Delivery session／验收
   operation／role的映射。仅接纳当前代理所属owner的实际注册，不按目录或时间猜配。
   未知session的请求照常按原授权通路执行，数值列unallocated并给出定位。
3. 每次实际到达代理的上游调用生成唯一request_id，保存proxy_session_id、attempt
   index、注册session／owner绑定、压缩用途、时间／状态和数值。provider response_id
   与request-id响应头分别保留，不能拿DSH inbox messageId冒充provider response_id。
4. 019离线工具增加窄DSH原件读取，消费数值回执、冻结的session事件／wire和实际绑定。
   与Codex原件可同scope混合，保留runtime分组；原生事件作核对／补充，不能重复相加。
5. 工程／真实L0／独立L1／切换／效率／账单分别在现有交付记录和报告中给结论。
   本轮不创建正式验证用scope或运行结果，不伪造一套完整证据。

### 2.1 Messages最小数值采集

在`messages_provider_proxy.py`原读流旁增加**只观察数值的有界SSE解码**，不改变下游
字节、刷新顺序、错误路径或重试策略。此为034对019“不新增流解码器”的窄扩展，
只解决DSH缺provider原始字段、presence、响应身份和失败末段的现实缺口；不扩展旧
Responses代理，也不保存完整provider请求／响应／推理正文。

- 读取请求仅提取原生session头、压缩标记及精确请求model／effort；凭据、user-id、
  messages／system／tools正文不进入采集。session与purpose仅供本机绑定，不新增
  对外追踪协议；现有上游header策略不因统计被扩大。
- 每次实际转发前记录attempt_start及唯一request身份，响应头到达记headers_at和
  provider request-id；最终记录attempt_end及completed／http_error／stream_error／
  client_disconnected／transport_error，异常不存自由文本。
- 按完整SSE事件解析`message_start.message`中的id／model／usage、后续
  `message_delta.usage`及`message_stop`。分块、UTF-8、CRLF、多行data正确组帧；
  只保留白名单ID、字段存在性、数值、事件位置、状态和结束标记。
- 每请求每字段取最终实际给出的累计值，不相加message_start与delta；下降、同一
  终值冲突、非法值／超长事件、坏帧或中断记缺口。成功终态与数值完整性独立；中断
  时已见数值可作partial小计，不能当完整账单值，不因缺usage抹去attempt。
  message_start的初始output=0不代表最终输出；输出完整性必须有该协议终结阶段的
  output用量，缺终结值即使收到message_stop仍为partial。输入仅在协议确认其为
  完整请求输入的位置取值；不要求最终delta重复已经完整给出的输入字段。
- 观察器采用固定有界缓存；超过上限或采集写失败只影响计量覆盖，不关闭模型流、
  不等待统计完成、不重发上游请求。沿NumericReceiptWriter的白名单及私有0600／
  0700写入方式，必要时扩展窄response_usage事件，不引入正文日志。
- 新回执记录time_basis、clock_ref、first_output_at可用性；缺实际首输出时间则不报
  generation吞吐。模型可见thinking文本长度不能换算reasoning token。

Host保存的原始数值回执本身是provider字段白名单投影原件，含字段存在性与定义版本；
通过scope记录文件、冻结字节长度／SHA256和真实偏移，可独立复算。旧dsh-wire／
session原件可能含业务正文，继续留在原Host私有位置；报告只给定位和必要数字，不复制
正文给角色。缺失provider回执时不能声称仅靠Harness默认值已完成账单对账。

## 3. 身份、口径与去重

### 3.1 最小合同增量

沿用`model-usage-scope/v1`、规范回执及原JSON／Markdown出口，只增可选字段／源kind，
旧输入输出含义不变；实现若确有不兼容再升局部版本，不先造兼容框架。

| 层 | 必要新增／保留 |
| --- | --- |
| sources | 新DSH数值capture与原生event来源，显式path／kind／冻结范围；definition_ref绑定Harness提交、adapter／字段语义证据 |
| bindings／identity | `runtime`、`runtime_session_id`、`process_instance`；原task_ref、session_id（业务Delivery session）、run／round／operation／role／phase、provider／account_ref／key_ref、model／effort保持 |
| 请求 | request_id、proxy_session_id、attempt_index、真实provider response_id／request-id、注册绑定证据、用途／压缩标记、实际起止／终态、usage字段presence、原件定位 |
| 原生事件 | runtime session＋seq＋事件类型及实际turn／step／attempt（有则存），compactionId／summary.seq；不伪填Codex thread_id／turn_id |
| 报告 | runtime分组、原始桶与统一桶／定义来源、各字段覆盖、原生核对差异、未归属及未知attempt；原usage／attribution／timing／billing状态分别保留 |

`thread_id`只保留真实Codex值。内部核算session键为`(runtime, runtime_session_id)`，
旧Codex缺新增字段时明确映射真实thread_id；DSH缺session不能自动套thread。原报告
的去重、累计段、快照核对和分组须同时用此身份，不仅在JSON中加字段。进程重启不
重置原生session历史；新session另记与原任务的接续绑定，不伪称原session。

### 3.2 输入及输出映射

对已经核实为DSH互斥桶口径的数值，U=未缓存普通输入、R=缓存读取、W=缓存写入：

| 019字段 | 已知桶齐全时的映射 |
| --- | --- |
| input_tokens | U＋R＋W，包含全部输入 |
| cached_input_tokens | R |
| uncached_input_tokens | input_tokens−R，即U＋W；W仍单列，不能既收一次未缓存费又重复收缓存写入费 |
| cache_write_tokens | W，按真实价表确定是否独立类别 |
| output_tokens | 原始输出O |
| reasoning_output_tokens | 真实reasoningTokens（如有），O的子集；不再次相加 |

Messages原始字段input_tokens／cache_read_input_tokens／cache_creation_input_tokens
经已验证定义分别对应U／R／W；Harness TokenUsage.inputTokens／cacheReadTokens／
cacheWriteTokens同理。缺字段保持null；只有明确的协议／版本证据证明“不适用／省略
即0”才可作0，并注明依据。不能继承Harness translator／projection中的`??0`默认。
没有全输入时仍可展示已知原始U／R／W，统一总输入及派生值unknown；局部字段可知
不代表完整usage。totalTokens不作input，不与其他字段相加。

计价继续019显式price_versions／币种／单位／生效窗口：若价表把W独立计价，普通
未缓存收费基数须从统一uncached中扣W；若价表将W含在未缓存费中，不能再收W。
实现仅为这一个实际DSH口径补必要计算，不能直接把两个重叠类别都交旧`_costs`求和；
缺定义／必要字段金额unknown。不内置当前价格、汇率、缓存倍数或订阅折算。

### 3.3 三层核对

1. **provider请求为主账。** 有provider response_id时沿019以provider／非秘密key_ref／
   response_id去重。同ID冲突按字段unknown；相同请求的多份来源合并定位。无response_id
   时，仅有Host代理生成、实际单次转发的唯一request_id及绑定证据才作替代身份。
   不按token相同、文本、时间、messageId或session单独去重；每次重试是独立attempt。
2. **原生事件核对。** assistant/message、assistant/attempt及wire／持久文件副本先按
   同session＋seq去重；同turn／step的attempt与最终message按实际重试／替换语义核对，
   不能逐条求和。没有provider唯一关联的原生记录只核对／给partial原生小计，不和
   provider主账相加；不为补齐归属用时间邻近匹配。provider原件缺失且原生语义清楚
   时可给明确标注的partial替代小计，不能进入完整账单MATCHED。
3. **累计和压缩。** TokenUsageProjection只作其覆盖范围的普通assistant子集对照，
   沿019连续段和基线规则，不与逐请求相加。压缩按原生session头＋compact标记与唯一
   proxy request绑定，从主账选择compaction_subset；summary／compactionId仅作
   成功压缩交叉核对。失败／重复压缩仍按实际请求计入总量与子集，不能仅取成功summary。
   标记缺失而summary不能唯一关联时，主账已知量照计，压缩分类unknown，不按相邻
   时间补绑，也不要求一定存在Codex compaction_response_id。

## 4. 完整链边界、默认切换与恢复

### 4.1 选定路径与依赖清单

本期“完整切换”明确指：**经当前`python -m modeling_team delivery --config …`配置启动的026最小业务链，贯通
生产Team、CQ作者、Delivery、公开反馈、正式公开／隐藏Consumer与Judge、必要
只读验收接续、standby及stop**。凡在该任务中实际触发的增量修模／技术恢复也须
按真实runtime计入。非必发入口可以用确定性选择测试证明路由，真实未触发单列；
不能称其真实运行已验证。更大业务、全部历史Lean／standalone入口迁移不属当前门。

切换清单按下列三类逐项记录实际配置、进程、session、插件、模型绑定及证据：

| 类别 | 判定 |
| --- | --- |
| 当前路径必经模型角色 | 生产成员／CQ作者、Delivery、完整验收Consumer／Judge均实际DSH；有Codex残余即mixed，不报完整DSH链 |
| 宿主监督／CQ审核／平台修复／测试代答及辅助模型 | 不强迫把外层Codex／Claude宿主本身搬进DSH，原职责与独立性保持；实际runtime、人工／模型介入、用量与覆盖全列。存在此类残余时只能称“所选路径完整切换”，不能称零Codex或全自主 |
| 明确未采用的历史入口与保留的Codex选择 | 列入口及原因，不把保留可读／可选能力算成正在执行；不要求无限期双栈维护或全历史迁移 |

032／033独立runtime选择与旧缺省=codex的兼容合同保持。034交付的默认改变放在
**当前新任务的标准启动配置／示例**：标准Delivery配置显式runtime=dsh，绑定
026 DSH生产Profile和显式获准模型Profile；其公开反馈／start_evaluation及只读接续
均显式传runtime=dsh。不改所有旧Profile，不借模型名推断runtime，不把独立CLI
缺省改成dsh而把旧输入误迁移。实施从现有README标准启动路径与实际生成配置接线，
不存在的配置文件由该路径最小补齐，不另设全局默认服务／任务编排器。

验证须从**新的标准启动入口**追到子进程，不只检查YAML。明确指定codex的旧入口
仍选Codex；旧session／operation／run读取按原合同，不改变运行时。默认不能悄悄
补一个模型：DSH缺任一必要角色的精确binding就返回可修正配置错误。所有新任务仍
依赖届时有效授权，不因默认配置获得生产或验收许可。

### 4.2 阶段顺序与结果

| 阶段 | 可交付结论及必要证据 |
| --- | --- |
| 工程 | 019扩展／采集及选择贯通、原件复算／反例、本地装载；不是外部provider L0或语义PASS |
| 真实L0 | 在另行有效授权下，以031—033实际已就绪路径开始026；真实请求／工具／application、治理读回及资源状态可追溯，失败分层不丢原件 |
| 有界独立L1 | 原冻结完整分母、独立DSH Consumer／Judge、真实治理响应／报告、无漂移；非盲回归如实标注，不把资料复用说成盲测 |
| 所选路径切换 | 三条功能＋计量就绪，已获准的所选链L0／L1成立，再提交新任务标准配置切换；记录实际旧／新配置摘要与证据。验证前只显式选择DSH，不先变默认 |
| 效率／费用 | 依§5按各自可比性／覆盖单独给结论。账单延迟不阻塞安全建模、L0／L1或已有证据支持的切换；缺对照／账单则对应要求继续待证，034不能整体宣称全部完成 |

后续首次真实授权遵守20分钟semantic-start；启动前只检查当前授权、就绪组件和安全
装载，不前置完整审计或新harness。默认三轮／用户另定额度及实质修模计数沿仓库，
不因有对照设计自增运行次数；不足做对照时留下未验证，不挪用额度。

阻塞时保留原run／session／application及未知写入；沿031—033原恢复通路核清后继续
原目标，不热切runtime、不自动重播。必要新任务可显式codex，实际形成新start或实质
修模则照原授权计轮；旧失败不被新成功覆盖。标准配置若须回退，仅改后续新任务选择
并留摘要，当前运行／资源不被重建，不建设自动故障切换系统。

## 5. 有界对照与报告

复用[030设计](2026-10-17-r4-3-030-delivery-token-reduction-design.md)和026既有Task、
材料、题集及证据工具，不创建只识别本次输出的一次性语义验收器。沿019同一scope
输出JSON／Markdown，并在现有交付记录增加路径覆盖与对照表即可。

- A／B事先绑定业务范围、资料／题集／评分／freeze版本、精确模型与requested／
  effective effort、030启用项、代码／角色方法／工具schema、并发、上下文／压缩、
  key／provider及授权窗口。跨run的实际model_binding不同正常，必须证明业务输入
  同等；不能要求两个新建模型的资源ID相同。
- 优先同provider／精确模型／effort的Codex与DSH对照；兼容性不允许时，给迁移包整体
  观察，不归因为Harness单项收益。030与DSH同时变化且无法隔离时明确混杂因素，
  不为因果归属强制额外实验／全矩阵。无可比基线只报绝对值／范围与待证。
- 从实际授权到独立PASS与收尾的完整窗口，另列semantic-start成功窗口；失败／重启／
  恢复／追加修模成本不删除。有效建模、基础设施／harness／评审／文档、等待分别计时，
  并行不重复墙钟；语义有效时间不足一半按仓库停止扩展harness并报告原因。
- 逐角色／阶段报告Delivery与全任务总输入、缓存／未缓存、输出／推理、压缩次数与
  token子集、真实响应／未知attempt、补读次数／返回量（非provider token）、墙钟、
  宿主介入、估价及账单状态。DSH与Codex用量分列后再给同定义已知小计，不报不同
  tokenizer下token数为同等工作量；质量与成本均看完整任务结果。
- 降Delivery但增加Host／Coordinator开销须披露成本转移；缺Host／辅助调用不能说
  全任务净下降。缓存率升高、bytes下降、局部窗口或单次快照不是降耗证明；不预设
  百分比目标。质量必须保留同等业务范围、完整分母、正确未知和独立裁决；不达标的
  任务不能作为等质收益。
- 账单沿019显式导入供应商数值／价表，给账户／非秘密Key／模型／时区／半开窗口／
  计费时间基准、other_task、unallocated及有符号差额；禁止自动登录或读取凭据。
  本地估价、token匹配、金额匹配与归属分别判断；缺任一必要原件保持PARTIAL，
  相等不自动证明完整。采集失败只限制结论，不成为写入／验收硬拒绝。

## 6. 实施交接与验证映射

| 修改面（未来实施） | 最小增量与验证目标 |
| --- | --- |
| `messages_provider_proxy.py`、`usage_capture.py`及对应测试 | 请求身份／绑定／时序、numeric-only SSE旁路和白名单；原字节流、失败与无重试行为不变。覆盖分块、多行、缺字段／显式0、终态与中断、采集失败不阻塞（A1／A2） |
| `usage_report.py`及`test_usage_report.py`／使用说明 | DSH归一化、真实session身份贯穿核算、provider／原生／累计核对、压缩子集／计价无重叠；保留Codex及混合scope旧合同（A1—A3） |
| 031—033 baseline／session／operation实际接点 | 复用当前原件与注册映射，补必要owner／runtime绑定和数值capture接线；不修改评分／写入合同或重做运行框架（A2／A4） |
| 现行新任务标准配置／README／Delivery启动和评估传参 | 成功验证后显式DSH选择贯通，Codex显式入口／历史读取保留；旧运行不热迁，缺模型准确反馈（A4／A6） |
| 现有交付／测试记录、usage报告 | 记录L0、独立L1、覆盖清单、净效果／账单限制及实际授权；不另造裁判、数据库或控制面（A3—A7） |

先交付离线采集／报告、再随032／033接线，真实验证按授权启动；031的工程PASS可
复用，不前置重跑所有历史实验。Team改动在backend目录按仓库既有命令运行相关及
全量Team测试，DSH本地确定性Messages服务只作工程fixture；若触及backend／frontend
则另遵AGENTS全量／重启规则，不能为本设计先改产品服务。
实施涉及跨模块调用关系时按AGENTS做impact／detect_changes；工具不可用时披露
定向检查范围。不以本次文档审阅冒称代码图影响覆盖。

核心反例：相同输入桶不同定义、缺W／reasoning字段、显式零与缺省零、缓存双加、
重叠计价、message_start／多次delta重复、流中断无summary、有费用重试、共享session
与复制日志、缺原件／定义／绑定、累计缺基线、已知账单外调用、混合runtime、仅改配置
没有实际DSH进程、少题仍PASS、遗漏Host成本与030同时变更，分别对应权威A1—A7。

## 7. 设计收尾

需求、D1—D8、F1—F7及A1—A7已完成，无关键待用户决定项。独立设计审阅
Round 1 PASS：0 Critical／0 High，无关键未决假设；快照及范围见[审阅记录](../records/2026-10-18-r4-3-034-design-review-record.md)。
设计／文档检查不证明工程、真实L0、独立L1、默认已切换、重复性、净降耗或费用对账。
