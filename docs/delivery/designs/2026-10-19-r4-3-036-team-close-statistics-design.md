# R4.3-036 建模Team关闭统计与逐Agent用量、活动时间及生命周期设计

权威范围：[R4.3-036](../../requirements/requirements-v4.3.md#r4-3-036)。
2026-10-19用户确认可行性建议，并授权新建需求、设计及独立审阅。本轮只交付文档；
不实施、不启动服务、Provider调用、建模／修模或真实验收，不改变既有授权额度。

## 1. 基线与最小方案

核对源码HEAD为`8ed70b646a0280cd23beb285ee5339fcdf9b0bb5`；工作区另有DSH／GLM
兼容等未提交修改。本设计读取当前入口，不接管该工作，不以其尚未验证行为作为已验收依赖。
固定Harness接口以`dsh_build.py`当前声明及实际装载摘要为准，不修改外部Harness仓库。

| 入口 | 已有能力 | 本需求必要增量 |
| --- | --- | --- |
| `modeling_team/usage_report.py`及`references/model-usage-report.md` | 显式scope、归属、去重、累计、JSON／Markdown、请求吞吐与覆盖 | 自动构建本次实际来源清单；增加成员、活动区间和关闭摘要；复用原核算结果 |
| `messages_provider_proxy.py`、`deepseek_provider_proxy.py`、`usage_capture.py` | DSH／Codex代理attempt及部分逐响应usage；DSH已有session绑定 | 保留各实际attempt计时，补可证明的成员／时钟定位；计时不依赖响应具有usage |
| `runtimes/dsh.py`、`codex.py`及各自Delivery／acceptance适配器 | 原生会话、进程、停止及清理 | 生命周期和工具执行的最少数值事件，各路径准确披露可观测覆盖 |
| `runner.py:cleanup`、`host_ops.py:stop_run/get_request_result` | 停止提交、Runner清理、原请求回执和终态状态 | 实际清理后生成run汇总；既有查询返回附加统计与报告引用 |
| `delivery.py`关闭循环及`native_runtime_closed`、`delivery_ops.py` | Delivery等待所绑定owner退出；独立operation有状态及退出观察 | runtime关闭后汇总Delivery末段；各operation收尾汇总，任务级显式组合 |

最小方案为“既有数值主账＋少量生命周期／工具事件＋确定性收尾汇总”。不建数据库、
Endpoint、常驻监控服务、前端、统计Agent或自动故障恢复系统。统计不产生LLM请求。
复用019／034既有JSON／Markdown生成能力；不要运行整个Host目录扫描或读取全局凭据。

## 2. 范围与身份（D1、D5）

两个视图必须并存：

- `run_close`：本run实际拥有的生产／CQ作者和关联子任务；Delivery若仍在线，只作为
  任务截至cutoff的非终态行，不能计作本run已退出成员。子任务是否属于run由原账本证明。
- `task_close`：显式task／Delivery业务session实际绑定的全部run、修模轮、Delivery、
  公开反馈、Consumer／Judge及获准接续；失败和被替代成员保留。已知Host／辅助模型
  成本沿019单列，缺可分配的Host记录仍unknown，不阻塞Team关闭。

成员键为`runtime + native_session_identity + process_instance + agent_id`，附role、
task_ref、业务session、run、round、operation／batch及精确模型／effort。Codex thread与
DSH session保留各自身份字段，不互填；PID只作观测，不作稳定身份。没有实际身份的
启动失败使用Host在启动前生成的唯一instance，原生会话字段null。不得由目录或时间猜配。

采集首次launch前记录实例起点，进程创建失败也保留。ready／会话绑定成功可作为可选
初始化分界；退出需原owner的wait／returncode或既有进程身份核对。请求stop不是exit。
恢复原session但新进程代次另列实例，session级累计跨代次仍按019基线去重。成员生命周期
时间取实例区间之和，跨代次最早启动到最晚退出的跨度另列，不能把离线间隔算存活时间。

统计清单由原启动／注册／operation账本逐个生成，随实际启动登记来源。未调用须有依据
才记not_invoked；已启动但没有usage为unknown，不因零报告、idle或零写入记零消耗。
自动scope延用019来源类型及冻结字节长度／摘要／binding，新活动来源另设`activity`
解析，不把它伪装成现有只允许四类event的numeric usage记录。历史scope和CLI仍可读。

## 3. 时间定义、并发及缺口（D2、D4、D5）

| 字段 | 定义 |
| --- | --- |
| `llm_request_seconds` | Σ每次实际上游attempt从发起到完成／失败的持续时间；失败、取消、压缩分别保留。重试实际发了两次即两段，不能按成功response_id消掉失败请求 |
| `tool_execution_seconds` | Σ根工具调用进入实际执行接点至执行返回／失败的持续时间；不包括调度前排队和结果按序提交等待 |
| `active_seconds` | 同一成员的LLM和根工具执行区间并集；重叠只算一次，缺口时只能给已观察并集小计 |
| `lifecycle_seconds` | 实例launch开始至确认exit；包含初始化、空闲、暂停、调用、等待、收尾。未退出只给截至cutoff的elapsed，最终生命周期为null |

LLM时间是客户端可观察的请求往返，包括网络、供应商排队和流式传输；不称供应商纯
推理／GPU计算时间，不拿turn或TTFT替代。工具内部长轮询、sleep、等待子任务仍属于
工具执行；可按明确工具／控制证据单列等待子集，活动时间不代表有效语义工作时间。
工具内部触发LLM时，LLM累计与工具累计可重叠，active取并集不重复计时。

DSH在本仓库Node composition注册数值观察器，复用固定Harness `tools/execute(exec,next)`
waterfall，以`try/finally`记录真实委托区间及callId／rootCallId／session。`next()`结果原样
返回，异常原样抛出，不改signal、调用身份、权限、并发或重试。该接点位于prepare后、
按模型顺序写结果前；计入委托层的实际RPC往返，不声称远端工具的纯CPU时间。只计根调用
作Agent总量，嵌套调用若保留为明细／子集，不能再次加到根调用。prepare阶段拒绝／取消
没有执行区间，调用状态单列，不能伪造一次零耗时成功。`tool/call → tool/result`差值只可
作为历史端到端交付观察，不作执行耗时：固定Harness会按模型顺序commit并行结果。

Codex的Host动态工具在真实`tool_handler`委托前后计时；其他受控MCP工具复用实际
服务端执行边界。原生item自带明确执行duration时可作该调用补充／核对，同一call只计一次。
仅item通知到达时刻或turn跨度不能冒充实际执行起止。订阅／无代理的内部LLM请求、
无法取得实际起止的原生工具如实unknown；本期不修改Codex客户端或扩大其工具权限来补数。
DSH生产、Delivery及Consumer／Judge共用composition观察接点，Host回调与Node同call
记录为来源核对而非两次调用。需要覆盖矩阵说明每条实际runtime／角色路径及缺口。

新采集持续时间用源端单调时钟，附UTC用于展示。区间并集仅在证明同一clock_ref且
起止可比较时计算；本机Linux Node和Python时钟须在实施时核实公共单调时钟域，并保存
clock_ref及进程代次，不能直接混用`performance.now()`等进程相对值。不兼容时只给各源
duration和覆盖，active为unknown，不为补齐建设跨机器时钟校准系统。跨boot、时钟倒退、
缺start／end、事件冲突和日志截断给定位；不得给负数或用相邻事件填补。未闭合请求列
unfinished及截至cutoff下界，不混入已完成duration总和。

Team墙钟是run启动请求开始到该run实际收尾完成，任务运行墙钟是首次获准runtime启动
到任务最终收尾；授权至独立PASS／收尾仍沿001单列，不能改写其起点。全Team活动并集
仅跨可比较的成员区间计算；Σ成员活动时间称累计Agent时间，可能大于Team墙钟。
`生命周期−已观察活动`只能称未覆盖／其他时间，不能统称idle或等待。

## 4. 用量及附加统计（D3、D7）

完全复用019／034 token主账：统一input已含cache，reasoning属于output，压缩是总量
子集；provider response、原生session累计、Consumer快照核对而非相加。失败／取消／
恢复／压缩的已知usage均保留，attempt只有时间没有usage时，token保持unknown。
token去重与时间去重分别处理，不要求一次失败请求有response_id才能统计其执行时间。

每个成员、角色及runtime／模型分组返回：输入／缓存／未缓存／输出／推理／缓存写入，
相应覆盖；token已知占比及其分母；缓存命中率及可计算输入覆盖；LLM调用和实际attempt
次数、失败／取消／未完成数；根工具请求／实际执行／成功／失败／未完成次数及耗时Top 5；
压缩次数与已知token子集；有证据的暂停／等待区间；退出原因、清理状态及残留定位。
未明确失败不能按成功数补齐，prepare拒绝与已执行失败分开。缓存率按配对样本加权，
不同模型／Provider口径分组，不能平均各Agent百分比。token份额只称已知小计占比。

价格版本、币种和计费定义完整时附本地估价，否则金额unknown；不预置价格或登录账单。
工具耗时Top 5按根调用的实际累计执行时间排序，明确样本覆盖；不作跨业务效率排名。
CPU／内存、自动根因评分、每阶段强制性能预算及新看板均不在本期。

## 5. 收尾、发布及返回合同（D6、D8）

顺序为：原stop收窄新工作准入 → 原owner处理在途／未知写入并执行原清理 → 确认
所统计Agent runtime退出 → 现有采集有界flush → 冻结当前来源前缀 → 复用离线核算
生成JSON／Markdown → 发布Host关闭摘要。失败／清理不完整也执行可用的统计分支，
保留第一失败层；不能用统计PASS覆盖清理失败或模型质量结论。

生产`Runner.cleanup`在adapter／acceptance收尾后生成run汇总，原缓存清理回执附统计
引用；独立evaluation owner在各成员收尾后生成operation汇总。Delivery在`finally`内
`runtime.close()`后、`native_runtime_closed`落盘后生成自身末段与task汇总，不能在
`finish_delivery`或standby时提前冻结最终用量，也不能依赖已退出的LLM再写总结。
Host驱动进程不是LLM Agent，task收尾时刻是其完成关闭统计的截点；宿主自身若仍在执行
其他工作，单列已知成本／缺口，不声称其已最终退出。

`stop_run`保留原submitted／accepted／rejected和request_id语义；`get_request_result`
读原回执并附只读统计引用，`get_run_status`也可从同一终态状态读取，以覆盖无request_id
的关闭。独立operation沿`get_evaluation_status`，Delivery沿原session／conversation状态
返回。原`stopped`控制回执若早于Delivery runtime退出，统计保持pending，关闭后追加
独立`close_statistics_ready`事件；不改写原控制回执、不把submitted当最终关闭。

终态查询附加`close_statistics`，最少合同如下（结构示意，字段值非真实结果）：

```json
{
  "schema_version": "team-close-statistics/v1",
  "view": "run_close",
  "closure_status": "closed",
  "report_status": "ready",
  "coverage_status": "partial",
  "cutoff_at": "2026-10-19T00:00:00Z",
  "report_ref": "evidence/close-statistics/report-1/report.json",
  "markdown_ref": "evidence/close-statistics/report-1/report.md",
  "summary": {
    "input_tokens": 100,
    "output_tokens": 20,
    "lifecycle_seconds": 60,
    "llm_request_seconds": 20,
    "tool_execution_seconds": 10,
    "active_seconds": 25
  },
  "limitations": ["delivery_still_running"]
}
```

summary为本view实际统计范围，报告同时含逐成员表和task截至cutoff视图。零输入的缓存率
为null；缺数值为null。`closure_status`为closing／closed／incomplete／unknown，
`report_status`为pending／ready／unavailable；closure、report与coverage各自独立。
已关闭且报告ready不表示coverage complete，更不表示完整业务语义通过。

报告引用复用Host私有目录及权限，摘要只含非秘密身份、数值、固定原因码与定位，不含
题面、答案、工具参数／结果、推理、凭据或自由错误正文；不注入生产／盲测上下文。每次
冻结来源、配置摘要、cutoff及scope保留，可按原离线命令复算。发布需JSON／Markdown
两份完整后才标ready；使用临时输出目录完成后原子发布目录／引用，失败不暴露半份ready。
同一关闭及同一源快照重复查询返回同一报告，不重复累加；后续取得迟到数值生成新版本并
引用前版，旧文件和原语义报告／digest不改写。不得为了统计重新启动任何Agent。

flush复用DSH已有最多1秒策略，其他新增collector遵循同一有界上限；异常、队列满或
进程被强杀只影响覆盖。统计生成／落盘失败时原stop和资源清理结果保持，返回unavailable
和固定原因码；正常查询只读取已发布结果，不反复全量解析日志。可复用离线命令另行补报，
没有常驻自动重试队列；报告计算不能在持有运行控制／工具锁时进行。硬杀无法执行finally
时，只读终态查询根据原账本返回unknown／unavailable及原件引用，不伪造关闭时刻。

## 6. 实施交接与验收

直接实施范围：扩展既有`usage_report.py`／capture与文档；必要时一个具体的Host数值
activity helper统一写入；各Adapter／Node composition／Provider接点采集；Runner、
Delivery及evaluation收尾与原查询返回接线。helper只解决重复数值写入，不建立可扩展
遥测框架。`tools/execute`接口已定向核对；Node／Python公共时钟和Codex可观测能力须
在开发专项中证明，无法取得则按已确认缺口合同返回，不阻塞其他路径交付。

开发前对实际变更符号及查询返回调用方做GitNexus impact；不可用时定向调用检查并披露。
本次仅设计，没有声称完成图影响覆盖。范围不要求修改backend／frontend；如实现实际
涉及它们，须按仓库对应全套测试／重启规则执行，不把本设计当豁免。

| 验收 | 核心场景与证据 |
| --- | --- |
| A1 | 正常run、独立evaluation、Delivery最终关闭均自动产出逐Agent表／总览及JSON／Markdown；既有stop提交不假称关闭；原查询能获取最终引用，无新增模型调用 |
| A2 | LLM 20秒、工具10秒且重叠5秒得到active 25秒；两个并行10秒工具累计20秒／并集10秒；不同Agent相加不冒充Team墙钟；长等待工具有解释 |
| A3 | 并行工具短任务先结束但结果晚commit、嵌套工具、prepare拒绝、异常／取消／工具内LLM、两处采集同call，执行时间与次数准确且不重复；DSH生产／Delivery／Consumer／Judge与Codex覆盖分别记录 |
| A4 | 重复usage通知／副本、同session跨进程恢复、新session替代、失败请求无usage、压缩及Consumer末段；token与attempt分别去重，缓存／推理不重复计数，所有失败和未知保留 |
| A5 | 启动失败、暂停、standby、跨代次离线间隔、Delivery仍在线、独立子任务提前完成、清理残留；生命周期／任务墙钟及终态范围准确，不将生命周期差值判为等待 |
| A6 | 缺起止、时钟不可比／倒退、事件截断、unfinished、缺Host／辅助记录；null／已知小计／覆盖明确，不补零、不猜时长或费用，不产生虚假完整率 |
| A7 | shutdown末次请求／迟到usage、flush超时、强杀、采集／报告写失败；原stop、字节流、写入和清理保持，无统计锁死；report unavailable与cleanup incomplete分开，首因不被覆盖 |
| A8 | 同关闭重复查询／stop、同冻结scope复算、迟到新版本与发布中断；两份同源，原件／旧报告不改，未完成目录不标ready；无题答／正文／凭据泄漏，旧scope与查询字段保持兼容 |
| A9 | 后续另行授权真实任务中，至少核对实际选定runtime的全链成员、末次usage、真实工具及退出证据；工程／设计PASS不替代真实统计覆盖、L1语义、净降耗或费用对账 |

新增或更新`modeling_team/tests/test_usage_report.py`、`test_dsh_usage_report.py`、各runtime
及Host／Delivery收尾查询测试，覆盖以上反例；运行Team全量与必要文档合同检查。
测试无需真实Provider，复用固定DSH＋离线Messages fixture验证执行边界和同钟条件；
真实A9待届时有效授权，不为补统计启动历史任务或追加建模轮次。

决策主表在权威需求D1—D8，本设计不复制另一份。独立设计审阅Round 1 PASS，0 Critical／0 High，无设计级关键未决假设；结论见
[审阅记录](../records/2026-10-19-r4-3-036-design-review-record.md)为准，A1—A9均未实施／验证。

后续实施说明（2026-10-19）：用户另行授权按本设计实现及测试；工程变更、覆盖矩阵和
开发证据见[实现测试记录](../records/2026-10-19-r4-3-036-implementation-test-record.md)。
以上设计阶段结论保留；后续工程证据不替代真实 A9、独立语义或净降耗结论。
