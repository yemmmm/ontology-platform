# DSH Delivery 上下文超限定位与修复

授权：用户要求“定位并修复一下delivery上下文超限问题”。归属
[R4.3-030](../../requirements/requirements-v4.3.md#r4-3-030) 的按需唤醒／有界输入与
[R4.3-032](../../requirements/requirements-v4.3.md#r4-3-032) 的Delivery运行时接线。
不启用030 F3换线程／F4连续动作，不重启此前已关闭的建模任务，不追加模型调用授权。

## 现场与根因

原任务为 `minimal-chain-20261018-dsh-low-b`，原生DSH固定构建`687f282`。
11:51:56Z的失败请求为HTTP400／CONTEXT_WINDOW_EXCEEDED，259条消息、2502856字节，
max_tokens=256000；前次成功请求input5848＋cache_read775680，实际输入781528。
原native记录有134次host_observation投递、54次yield，但无compaction事件。
完整旧会话、已关闭任务、模型、授权和验收结果保留。

两处已证实原因：

1. **已声明压缩插件没有实例化。** entry.mjs装载compaction-basic，却漏装其硬依赖
   tokenMeter。Cordis保留等待依赖的插件，不等于创建compaction服务；原host/inspect
   只列挂载名，未区分服务实际就绪。固定本机DSH的服务探针得到补装前
   tokenMeter=false／compaction=false，补装后两者true。
2. **普通原生事件仍触发模型。** 正常inbox入队／消费、成功messageId回执、idle及
   completed的turn/end进入Delivery变化链。原生产角色活动结束不是新的业务阶段，
   排队处理也不等于需要Delivery决策；它们推动重复等待推理和累计上下文。

第二处的直接工程作用为减少例行输入；第一处恢复超限前的原生压力压缩。
不是通过换模型、扩大窗口、截断旧消息或新建会话来规避失败。

## 最小变更与边界

- 只在config.deliveryTools选定的Delivery分支装载既有token-meter，补齐
  compaction-basic依赖；生产及独立验收的现有分支不新增插件。
- Host-only inspect增加两个服务就绪布尔值，并随原baseline保留；不新增模型工具或
  任意读取能力。Python按实际Delivery插件集合核对，使用原模型／effort。
- 原生摘要调用不继承会话请求的effort，会回落provider默认档；因此将所选Delivery
  effort同时传给其provider默认配置，实际压力测试确认聊天／摘要均为deepseek-flash/low。
- 原生compaction默认含context-overflow恢复重试。为保持原显式恢复边界，Delivery
  maxOverflowRetries=0；正常pre-step压力压缩有效，收到失败后不自动摘要／重放请求。
- 只将有明确成功结构的RPC回执、正常next-turn拼接、idle及completed活动结束作为噪声。
  取消、失败、未知类型／结果、坏形状、错误工具及异常用量继续送达。
  程序观察／队列投影继续使用原件；阶段、待办、写入、权限与报告变化不受影响。

该变更没有新增运行次数硬门，也没有修改隐藏题、评分、业务范围或模型内容。
新Delivery进程加载新装载配置；旧原生baseline不热迁移，沿原绑定漂移反馈处理，
不自动复活已撤回的授权。仅modeling_team代码改变，无产品backend/frontend改动，
无需产品systemd服务重启。

GitNexus impact对DSHDeliveryRuntime及_dsh_wire_noise均Target not found／UNKNOWN。
实际定向核对Delivery启动／恢复、原生compaction依赖、共享entry的条件分支、
Delivery唤醒／模型投影与原件保留；不声称索引图覆盖。staged detect_changes虽返回low，
但changed_symbols=0，未覆盖本次符号，不能据此宣称完整图分析。

## 测试与效果边界

先红后绿：旧实现的服务实例化、压力压缩与六种例行事件回归失败；启用原生压缩后又
观察到失败请求触发额外摘要、摘要effort偏离所选low，分别用回归复现再修正。
测试压力资料分成可保留最近尾部的历史消息；单个大消息小于原生retain预算时不可
选取压缩区间，不将该原生选择规则误判为依赖仍未修复。

定向五文件：**152 passed，152.63秒**，覆盖真实固定DSH＋bwrap＋本地Messages
fixture，未请求外部模型。其后补充畸形RPC身份及非字符串状态保护，均先观察失败，
修正后的6个相关用例通过；这些最终改动进入完整全量检查。
首轮全量为接收最后一项修正而主动SIGINT中止，退出2，不计PASS；
full-interrupted.log/xml保留原件，最终全量使用新源码摘要。

压力回归实际生成compaction/end检查点，后续请求不再含被压缩历史，保留最近历史与
最新用户输入，runtime_session_id保持；四个实际HTTP调用为两次聊天、原生摘要、
下一次聊天，模型及effort一致。历史后发生400时只有原聊天及失败请求，不产生额外
摘要／重试；原有恢复、控制、精确工具集合及角色隔离继续验证。

最终Team全量：**3333 passed、12 skipped、318 subtests passed**，534.05秒，退出0；
359项既有依赖／fork弃用告警保留。代码摘要与最终源码一致；Python Ruff、两份Node
语法、文档链接／需求锚点及git diff --check均通过。命令均在backend目录：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_delivery_wakeups.py ../modeling_team/tests/test_dsh_delivery.py \
  ../modeling_team/tests/test_dsh_runtime.py ../modeling_team/tests/test_dsh_events.py \
  ../modeling_team/tests/test_dsh_acceptance.py -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short
```

原事件用既有投影函数只读复核：b1的1120条wire记录，旧836／新1078条例行记录不进入
决策输入；b2的1194条为旧877／新1140。新增排除均为上述已知正常类型，错误／未知
继续可见。原件没有删改；这是投影机械证据，不能由条数或字节推算实际token节省。

原件在gitignored `workspaces/delivery-context-fix-20261018/`：service-dependency-probe.json、
retained-event-projection.json、focused.log/xml、full.log/xml、tested-source-sha256.json。
本次未执行新真实Delivery自主交付、独立语义验收或同条件token对照，故真实L0完整链、
独立L1及全任务净降耗仍待另行授权验证；不把本地工程PASS用于覆盖历史失败。
