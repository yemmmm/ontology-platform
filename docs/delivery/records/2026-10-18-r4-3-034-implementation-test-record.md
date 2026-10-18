# R4.3-034 开发与测试记录

用户授权：“请根据设计完成R4.3-034需求的开发与测试”。

依据[权威需求](../../requirements/requirements-v4.3.md#r4-3-034)与已独立审阅PASS的
[设计](../designs/2026-10-18-r4-3-034-dsh-usage-and-cutover-design.md)，复用019与已交付
031／032／033接口。源码起点`5c4156e`；固定Harness提交
`687f282e8625c6b8d11ff58211a90524be2e4317`。本轮只进行工程实现和本地确定性测试，
未请求外部模型，未启动真实建模／修模／语义验收，未消费建模轮次。

## 实现

- Messages代理每次实际请求生成唯一request_id，记录原生session注册、角色、进程代次、
  精确模型／effort、压缩用途、起止、响应头及真实响应身份。生产、Delivery、Consumer／
  Judge在原输入准入前注册，恢复同session时更新代次；batch与operation身份分开。
- 有界SSE观察只保存数值白名单／presence／事件位置及固定错误码。分块、UTF-8、CRLF、
  多行data、初始／终结output、中断、下降和超限均有反例。256 KiB事件缓存及1024项
  异步队列隔离采集；采集阻塞、失败或队列满不会关闭模型流或追加上游请求。收尾最多
  等待1秒刷新，缺口只限制统计。数值文件0600／目录0700，恢复已有文件亦收紧权限。
- 019新增dsh_capture／dsh_native及原生session核算，保留Codex口径与混合scope。
  U／R／W归一化为input=U+R+W、cached=R、uncached=U+W；缺桶或定义不求总输入。
  推理仍是输出子集，provider原始字段和定义证据与Harness默认值分开。
- provider响应／真实唯一请求主账去重，复制日志合并来源，冲突字段unknown。原生seq
  副本去重、attempt／message替换和retry另计；普通累计只核对子集，缺基线不求delta。
  缺provider原件仅给partial原生小计，不进入完整账单MATCHED。压缩从实际代理compact
  标记选择，失败／重试无需summary，作为总量非加性子集。
- 显式价表下W独立计价时从普通未缓存收费基数扣除，W包含在未缓存费率中时不再叠加。
  缺定义／原件／必要数值保留unknown／partial，不预置价格或自动读取供应商凭据。
  实际请求／headers时间可报告；没有首输出时间则不报告generation吞吐。
- 使用现行Delivery配置显式贯通生产DSH Profile、Delivery和evaluation选择，README
  给出完整选择片段。旧省略runtime=codex、显式Codex、历史读取、standby／stop及原恢复
  语义保持。真实验证前不改标准新任务默认，不重建业务资源。

原始DSH业务日志继续在既有Host私有位置；离线报告只投影数字及定位，不把正文或报告
转给生产／盲测角色。task／round／operation及账户／非秘密key_ref由真实Host原件在
scope显式绑定，不猜目录、时间或把batch伪作operation。用法见
[Host用量说明](../../../modeling_team/references/model-usage-report.md#dsh-usage)。

## 验证与边界

验证命令（均在backend目录，禁止读取真实DeepSeek Key）：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_dsh_usage.py \
  ../modeling_team/tests/test_dsh_usage_report.py \
  ../modeling_team/tests/test_usage_report.py \
  ../modeling_team/tests/test_messages_provider_proxy.py \
  ../modeling_team/tests/test_usage_capture.py \
  ../modeling_team/tests/test_dsh_runtime.py \
  ../modeling_team/tests/test_dsh_delivery.py \
  ../modeling_team/tests/test_dsh_acceptance.py -q
```

最终当前代码全量结果：**3259 passed、12 skipped、318 subtests passed**，
耗时488.67秒；359条既有依赖／fork弃用warning，无失败。12个跳过覆盖既有真实模型、
隔离平台／RDF、原件回放及实装Codex等opt-in边界，不属于本轮工程PASS。
相关模块定向回归112 passed（91.34秒）；其后补充的非法原始用量反例及全部当前用例
已由最终全量覆盖。Ruff、git diff --check与文档相对链接／显式锚点检查通过。
最终全量日志及受测代码快照摘要保留于gitignored Host目录
`workspaces/usage-audit/r4-3-034-engineering/`，测试完成后核对受测代码与暂存快照一致。
期间一轮全量在补充非法字段处理后主动中断并重启；上面结果来自最后完整当前代码，
没有使用中断轮次充当PASS。
新增测试先观察到缺实现的失败，再完成实现并执行回归；工程fixture不作为真实provider
定义或账单证据。修改仅涉及modeling_team与文档，无backend／frontend可执行代码变更，
按仓库规则不运行产品全量测试、不重启产品服务。

GitNexus impact查询MessagesProviderSession与usage_report.build_report均返回
Target not found／risk UNKNOWN，索引未覆盖本批符号。定向检查代理三类调用者、
生产restore_session、Delivery／验收原始记录接点、usage_report读取／归属／去重／累计／
计价／渲染及全部相关测试；不能据此声称图覆盖。提交前detect_changes(scope=all)返回low但仅识别旧文档符号，还含当前变更中不存在的
pi-modeling-agent条目，未覆盖本批代码；该结果不作影响证明，采用上述定向调用检查。

| 验收项 | 工程证据与限制 |
| --- | --- |
| A1 | 互斥桶、零／缺值、累计基线／下降、推理子集、冲突、W不重叠计费及Codex回归；真实provider定义／账单待证 |
| A2 | 并发session注册、逐请求身份、缺绑定、同ID冲突、恢复／新session、分块／中断、采集失败／阻塞／超限不改流、不重试、无正文／凭据 |
| A3 | 同scope混合runtime、原生副本／替换／重试、provider优先、累计基线及末段原件读取；Host／辅助／收尾覆盖仍由真实scope逐项举证 |
| A4 | 复用032／033显式选择及兼容路由，三类实际本地DSH进程注册模型／session；真实完整链与默认切换未执行 |
| A5 | 仅本机固定DSH构建＋确定性Messages fixture；真实application、治理读回、独立完整分母L1未执行 |
| A6 | 复用原同session恢复／代次、显式Codex及不热迁的兼容测试；未创建真实新任务或追加轮次 |
| A7 | 保留019显式价格／账单窗口及partial边界，报告runtime分组与成本转移；无真实可比对照、Host全成本或供应商账单 |

## 后续真实验证与切换清单

不以工程测试代替下列结论；账单延迟不阻断安全建模或已有充分证据的切换，缺口仍须保留。

| 阶段 | 当前状态 | 真实证据要求 |
| --- | --- | --- |
| 工程实现／开发测试 | PASS，非独立语义验收 | 当前代码全量Team、相关反例、本地固定构建／隔离进程、静态／文档检查 |
| 真实L0 | 未执行 | 届时另行授权的026所选链、真实请求／工具／application、治理读回及资源状态 |
| 独立有界L1 | 未执行 | 独立DSH Consumer／Judge、冻结完整分母、实际治理响应与无漂移 |
| 所选新任务默认切换 | 未执行，旧默认保持 | L0／独立L1后从新标准配置追踪生产／CQ作者、Delivery、公开反馈、完整公开／隐藏验收的实际DSH进程／session |
| 非必发接续／standby／stop | 本地选择／控制回归 | 真实未触发入口单列，不能冒称都已实际运行 |
| Host与历史残余 | 未形成真实覆盖清单 | 宿主监督／CQ审核／修复／辅助调用全部runtime及成本；有残余不得称零Codex或全自主 |
| 等质净降耗 | 未验证 | 同资料／范围／题集／评分与模型／effort、实际030项、并发／压缩等；完整失败／恢复／收尾窗口与成功窗口分列，披露混杂／Host成本转移 |
| 真实费用对账 | 未验证 | 显式账单／价表、账户／非秘密Key／模型、时区／半开窗口、other_task／unallocated、有符号差额 |
| 更大业务／L2／自主交付 | 未验证 | 分别另获相应证据，不成为本次工程前置条件 |

真实授权后按仓库20分钟semantic-start及届时轮次推进。遇阻保留首因、原run、未知写入
与失败原件，优先同session核清后恢复；必要新任务显式Codex仍按授权计轮。不建设自动
故障切换，不借统计启动修模、不覆盖失败原件。034整条保持PARTIAL直至各自要求具证。
