# 2026-10-14 建模缓存成本与 Delivery 输入需求登记

本次用户要求将当天关于DeepSeek Flash吞吐／缓存、成本根因、Delivery职责、
observation.json来源和输入优化的讨论整理为需求并记录优化点。
结果是[权威v4.3需求](../../requirements/requirements-v4.3.md#r4-3-019)新增019—022，
并在[现有优化台账](../modeling-retrospectives/optimization-tracker.md)登记四项。
初次均为已确认方向、待细化设计／实施；随后用户授权Delivery窗口翻倍，020的该
局部已实施并通过工程检查，其他范围待处理。未产生设计独立PASS或真实效果PASS。

## 讨论结论与证据基线

用户提供并确认已筛选建模API Key的10月14日控制台数值：

| 指标 | 控制台 | 保留本地回执 | 尚未对上的差额 |
| --- | ---: | ---: | ---: |
| 命中输入 | 265,742,976 | 149,235,200 | 116,507,776 |
| 未命中输入 | 22,043,975 | 13,326,858 | 8,717,117 |
| 输出（本地含推理） | 2,483,354 | 2,124,461 | 358,893 |

控制台总量290,270,305与三项加总一致，输入命中92.3402%。
按本次确认的50倍输入单价比例，未命中占输入费用80.5735%，不包含输出费用。
保留回执命中91.8020%；先前98.2208%仅四个初建生产角色，遗漏了Delivery等层，
不得再用它评价整轮费用。数据来源为用户控制台转录与保留日志，尚未获得供应商逐小时
或请求明细；日期按北京时间查找，控制台时区没有直接核验，整体账单归属为PARTIAL。
不能把差额猜为Claude Code、重试或供应商计费错误。

| 已记录层 | 未命中输入 | 输入命中率 |
| --- | ---: | ---: |
| Delivery宿主5线程 | 11,241,420 | 86.4585% |
| A/B初建四角色共8线程 | 1,235,223 | 98.2208% |
| B第二轮四角色 | 217,718 | 94.7059% |
| 正式Consumer | 132,313 | 95.0865% |
| 正式Judge | 285,340 | 87.9320% |
| 公开反馈 | 65,364 | 89.6074% |
| 测试业务代答 | 149,480 | 53.6180% |

Delivery占已记录未命中84.35%。其30次压缩输入8,943,782、命中27,520、
未命中8,916,262；生产另两次压缩未命中303,398，32次合计9,219,660。
按compacted.compaction_response_id绑定真实usage，不是时间邻接推断；
这些历史量不能直接作为未来承诺节省量。B第二轮最终provider_wait、0新写入，
但此前已记录79次模型响应；等待／零写入不等于零用量。

本次Codex0.162.1角色日志显示deepseek-flash采用未知模型fallback；有效窗口
258,400、自动压缩阈值244,800，与
[当天官方Flash规格](https://api-docs.deepseek.com/quick_start/pricing/)公布1M不一致。
同版本[本地压缩源码](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/compact.rs#L304)
使用Prompt默认空工具定义，正常工具请求携带工具定义，前缀发生变化；与本次压缩
近乎零缓存回执一致。未保留本次全部wire body，尚无修复前后真实对照。

吞吐的旧局部测量只涵盖初建生产角色：610次usage中482次能唯一匹配响应头至usage
完成的计时，流式窗口约195输出token/s，含推理；该计时不含响应头之前的等待／输入
处理。含工具执行等turn内活动的加权吞吐约153token/s。均不是完整API或整轮
成功性能基线，不能与控制台全天用量直接拼算吞吐或净费用。

原始数值、线程／响应去重、缺rollout时的累计通知核对、源文件摘要及诊断限制保存在
[宿主私有审计报告](../../../workspaces/v4-smallchain-deepseek-20261014/cache-cost-audit-20261014/report.md)、
[数值明细](../../../workspaces/v4-smallchain-deepseek-20261014/cache-cost-audit-20261014/analysis.json)和
[本地复算脚本](../../../workspaces/v4-smallchain-deepseek-20261014/cache-cost-audit-20261014/analyze.py)。
这些是既有gitignored证据引用，不作为隔离生产输入，也不要求将私有原件提交仓库。

## Delivery职责与输入问题

依据R4.0-023，Delivery是可信Host侧的全程交付负责人，负责用户沟通、授权／运行管理、
CQ委托审核、阶段推进、第一失败层判断、修复交接、确定性证据资格核对和结果交付。
Coordinator负责生产内部协同，Modeling负责业务模型，Protocol负责应用与读回，
独立Consumer／Judge负责真实消费与最终裁决。Delivery有必要读取相关业务原文、
准确错误／请求回执和反馈／验收依据，不要求每次通读全部原件或接管业务语义判断。

observation.json由DeliverySession.observe确定性汇集并由record_observation保存：

| 字段 | 来源 |
| --- | --- |
| runs.status | get_run_status：state、运行证据、进程登记与实际存活检查 |
| runs.pending | get_pending_actions：文件派生的待办／等待项 |
| runs.events | get_run_events：evidence/*.jsonl的游标增量页，默认200条 |
| runs.request_ledger | control/host-requests.jsonl的累计全文 |
| operations | 验收／公开反馈／修复operation记录、报告绑定、控制回执和日志尾部 |
| repair_verifications | 测试、部署及健康检查核验记录 |
| observation_count／wake_count／decision_digest | 程序观察／变化计数与唤醒判断；不等于模型请求或计费次数 |

最新快照覆盖更新，但既有原始事件／报告保留；多run、多operation及累计账本仍可变大。
唤醒指纹与模型输入是两个用途：前者去掉多种噪声做比较，后者目前主要仅过滤原生
App Server通知，其他观察完整传入，附原件读取引用。变化哈希不能替代实际变化正文。
read_delivery_artifact只有path参数，一次返回全文件，2MB上限没有解决段落／字段补查。
这是目前输入过重的具体缺口，不能从“有权读”推导“每次必须全文读”。

## 四项登记及完成边界

| 需求／优化编号 | 已确认目标 | 待细化技术选择 |
| --- | --- | --- |
| R4.3-019 | 整轮分层用量、正确吞吐口径与同Key账单对账；差额诚实保持PARTIAL | 在既有回执上补哪些必要身份／数值字段及如何对齐缺记录调用 |
| R4.3-020 | 真正加载所选模型的容量／压缩配置，避免不适配fallback | Delivery已按后续授权翻倍；其他角色及模型容量接线待细化，不全局写死1M |
| R4.3-021 | 本地压缩前缀稳定、缓存复用，摘要与工具执行边界保持 | SDK、配置或现有适配层的最小方案；不把所有空工具请求当压缩 |
| R4.3-022 | 原证据完整留存，Delivery默认必要决策输入、账本投影及有界原文补查 | 输入字段／变化表达、原件定位和读取参数；不建新状态服务或查询语言 |

优先细化022，用019完整口径量测；020／021分别对照，不混算窗口、模型、输入变化
的收益。真实效果比较须包含补查／输出／失败成本、阶段推进和原完整独立语义验收，
不预设节省比例，不删业务条件、未知写入、真实错误、版本绑定或必要题目覆盖。
公开／私有边界、原始冻结／裁决及现有授权保持；下一生产仍按已选择GLM配置推进。

初次登记检查覆盖编号、链接、格式和需求—优化映射，不能作为实现或效果验证。
后续局部实现与验证见下节；没有服务重启、外部provider请求或semantic start，
未修改活跃线程和旧运行证据。提交信息由本次宿主交付消息报告。

## Delivery窗口翻倍的后续授权与局部实现

用户追加指令：“另外我希望将delivery的上下文窗口增大一倍”。这是020的Delivery
局部实现授权；不启动下一轮建模，不修改生产／验收角色，不实施019／021／022。

| 参数 | 旧观测值 | 新Delivery值 |
| --- | ---: | ---: |
| 配置窗口（raw） | 272,000 | 544,000 |
| 有效输入窗口（95%） | 258,400 | 516,800 |
| 自动压缩阈值（raw的90%） | 244,800 | 489,600 |

所选模型仍为glm-direct／glm-5.3-flash／high，
[官方规格](https://docs.z.ai/guides/vlm/glm-5.3-flash)的1M上下文支持本次预算；
没有全局启用1M或关闭压缩。CLI默认及准备YAML明确设置两个值，可显式覆盖。
直接复用DeliveryRuntime的隔离测试代答者保留unset默认，不继承Delivery CLI值。
修改在下一新Delivery进程生效，不能将磁盘配置修改称作旧线程已热更新。

初次真实Codex本地探针发现config/read返回544,000，但token_count仍为258,400。
原因是[Codex0.162.1模型元数据](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/models-manager/src/model_info.rs)
对未知slug设max_context_window=272,000，with_config_overrides取两者最小值。
因此仅为外部provider且显式配置窗口的Delivery生成单模型启动catalog，保留所选
slug与原未知模型的工具／截断默认，仅定义本次会话窗口预算；不伪装成其他模型，
不改Codex二进制、生产角色配置或共享provider helper。内置模型仍采用自身元数据上限。
catalog的空base_instructions与原thread/start一致，获准Delivery developerInstructions
和原生工具关闭投影保持。

实现入口：

- [Delivery CLI接线](../../../modeling_team/delivery.py)：同一配置传入窗口与阈值。
- [DeliveryRuntime](../../../modeling_team/runtimes/delivery.py)：根TOML设置与外部模型启动catalog。
- [GLM准备配置](../configs/2026-10-14-asset-fault-workorder.yaml)：明确数值，原只读准备授权保持。
- [运行边界测试](../../../modeling_team/tests/test_delivery_runtime.py)与
  [会话接线测试](../../../modeling_team/tests/test_delivery_session.py)：CLI默认／显式覆盖、
  测试代答默认、内置／外部元数据边界、无效值、实际窗口及原生工具隔离。

工程验证：

- 定向离线回归：39 passed、1 skipped；最终全量包含后续新增的原生窗口回归。
- 真实Codex0.162.1／本地模拟Responses模型：
  `MODELING_TEAM_DELIVERY_LIVE_CODEX_BOUNDARY=1`运行
  `test_real_codex_external_delivery_context_window`，1 passed。
  读取原生token_count实际为516,800，捕获1次loopback请求、精确模型slug／high及仅
  `emit_user_message`动态工具；没有外部provider调用或semantic start。
- `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`：
  2874 passed、12 skipped、318 subtests passed，258.93秒。跳过包含明确opt-in的
  原生检查，该新增窗口检查已单独启用并通过；保留既有356条依赖弃用警告。
  [完整输出](../../../workspaces/v4-smallchain-deepseek-20261014/cache-cost-audit-20261014/delivery-window-team-regression.txt)
  及[原生探针数值](../../../workspaces/v4-smallchain-deepseek-20261014/cache-cost-audit-20261014/native-window-probe-result.json)
  保存在既有gitignored宿主目录。
- 四个变更Python文件Ruff通过；diff、四项编号／需求—台账映射、Markdown格式、
  新增本地链接／锚点、基线加总及准备YAML检查通过。
- GitNexus对DeliveryRuntime的impact未找到目标，detect_changes虽报low但没有定位
  变更符号／调用流，不能据此宣称完整图覆盖。已按实际CLI调用点、可选构造参数和
  测试代答复用边界核对局部影响；没有修改跨角色provider helper或工具权限。

独立设计／功能验收未执行，A1仅Delivery局部工程通过；其他角色配置与A2—A4
仍待证。长会话压缩次数、缓存命中、净成本及业务质量须在后续获准运行量测，
不能从窗口翻倍推导费用减半或语义质量改善。只修改Team CLI运行及文档，没有修改
backend／frontend或应用服务配置，因此不重启ontology-platform.service。
