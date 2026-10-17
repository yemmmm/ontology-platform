# 2026-10-17 Claude Code 上轮复盘与通用流程纠正

范围：最近完成的 `minimal-chain-20261016-flashx-low-b`（HEAD e8a06fb），沿用
[上轮报告](2026-10-17-flashx-low-b-minimal-chain-retrospective.md) 的导航并复核原件。
用户本次授权修复共性问题、实施明显有效优化，然后以 glm-5.3-flash 最多三轮建模，结束后关闭。
上轮启动通道、残留进程及其 PG 启动事故先跳过；不清理其他会话，不重写旧运行证据。

## 需求验证与旧项

R4.3-026 上轮最终 start4 公开1/1、隐藏3/3全分母独立报告 full_pass=true，
Runner cq_verdict=pass；原件为该 run 的 acceptance-v3 双目录及 cq-acceptance-complete.jsonl。
这证明最小链最终语义结果；三轮累计返工、宿主接管事实保留，不证明自主交付或净效率。
R4.3-029 journal 已有有限实证，Delivery 流程自主性及净成本仍待证。
024/025/013 的旧局部采用保留，原大范围、自查发现错误、增量及未发生场景仍待实测。
不以本次文档修正关闭这些整项需求。

## 已定位问题与最小纠正

1. **提前冻结：流程合同。** start1 cq-freeze.jsonl 的首冻 hidden_question_count=0，
   后补3题；host-results 的 selected_scope_complete 在仅全景审核后误报为真。
   上轮报告并列的历史样本说明范围完成判断是共性问题。本次在宿主 runbook、Delivery
   实际 instructions/skill 区分单次review完成与完整选题阶段完成，按既有回执继续切片阶段。
   不新增固定题数／隐藏题硬门，保持任务差异及可恢复性。预计避免整轮返工，真实收益待证。
2. **冻结后14m32s等待：流程交接。** start4 outer-input-receipts、idle-inquiry、
   outer-instruction 和 deliveries 的绑定时间线成立。Delivery合同原已有发送确认的要求，
   不能误称从未规定；本次补强立即回告及实际投递/进展核对，宿主仅在缺位时有记录地补位。
   14m32s是旧样本观察，不能预先宣称每轮节省同样时间。
3. **Judge标签与理由矛盾：独立验收输出。** start3公开报告的唯一负判note明确称全部
   必要定义和区别已表达，且两条返回均绑定mic-concepts；答案和note与负标签直接冲突。
   本次在实际Judge提示增加提交前一致性自查，负判须指出有证据的剩余缺口，保留单次
   不可变提交、完整题集和原评分标准。未用程序替代语义判分，不覆盖旧失败。真实效果待证。
4. **空题集fail：纠正旧归因。** competency_questions.batch_report_acceptance_verdict
   明确把无verdict返回fail，complete_cq_acceptance明确只绑定隐藏验收；原报告公开PASS
   不覆盖隐藏分母缺口。它不是代码违反当前合同或模型失败的证据。无需另加硬拒绝／改接口，
   在宿主口径解释coverage gap，优先修第一项的提前冻结。
5. **启动方式专属问题跳过。** Delivery stdin接恒空源、外环工具误用和残留进程导致的
   PG事故不纳入本次平台修复；新轮使用现有可交互Delivery入口，不沿用该错误启动包装。

## 下一轮与验证

保持R4.3-026同一最小业务源、Profile和新scope，全部角色含独立验收使用glm-5.3-flash，
未指定effort沿默认max；不同于上轮flashx-low，不能把全部性能差异归于流程。
公开/隐藏验收在相同只读模型和冻结身份上复用现有并行能力，各保留完整独立报告。
不改变源、业务范围、隐藏隔离、应用完整性及独立判分。三次为上限，不要求耗尽；
初建和检查后的新实质修模分开扣账，fresh-start单列。结束后停止本组owner/Runner/Delivery，
撤销临时凭据，保留模型及证据。现场记录置于workspaces/minimal-chain-20261017-flash-retro。

启动前为提示／文档变更；启动后又定位下述通用唤醒缺陷。无需产品服务重启，
工程检查不表示新轮语义或效率PASS。仓库已有未提交文档和演示材料保持原状。

工程验证：backend目录下以env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest运行
test_contracts、test_r4326_minimal_chain、test_r3011_acceptance、test_delivery_host_actions及
test_r4329_independent：74 passed、3 subtests passed（4.71s）。delivery和modeling-dev-loop
Skill校验通过，Task/Profile/glm-flash-max配置验证通过，git diff --check通过。
无执行代码改动，无产品重启。GitNexus未索引到所查Host符号且返回旧文档位置，故不宣称
图覆盖；实际变更以本地diff和合同回归为证据。

## 新轮中发现的通用运行缺陷与窄修复

同一start1启动后出现1292条topology_missing_artifact重复事件（真实反馈仅1次），
Delivery已观察到34次client_disconnected。关联到程序每次检查写新关闭事件，以及
无status的reasoning/userMessage、已批准MCP调用、serverRequest/resolved和空限额通知
未被识别为常规原生记录，持续形成新的决策输入，steer导致当前推理反复重启。
前述次数为当时观察窗口，不外推为全部调用成本。并非ClaudeCode启动专属问题。

T0：保留拓扑校验和每次gate.close，不删除任何写入约束；同fingerprint复用已有
反馈去重，首次错误和不同原因仍记录。Delivery只过滤证据已确认的常规事件，真实错误、
非空限额、未知事件及未知写入仍触发；原始观察继续完整保留，不改变授权/源/模型/验收。
仅改变重复通知，无新增治理或恢复机制。GitNexus目标未索引，已聚焦检查全部9个
_multi_slice_gate_reject调用点及Delivery事件投影/发送入口，未声称图覆盖。

反例：重复gate测试修前1 failed（3事件/1反馈），原生常规记录修前7 failed/4 passed；
修后相关8个测试文件 **147 passed**（27.07s）。新代码只在重载后的Delivery进程生效，
保留原run及建模线程，不热写冻结产物；Runner去重在下一新Runner生效，当前拓扑已打开，
不为验证此修复重开建模或消耗轮次。净收益与完整语义结果后续据本轮证据更新。

## 最终新轮结果与停止（2026-10-17 UTC）

- Run `r4326-20261017-flash-retro-start1`；全角色glm-5.3-flash/max；初建1/3、余2，
  fresh semantic-start1；实际确认额度边界，无实质修模。达到范围目标即停，未耗尽预算。
- semantic-start02:55:05；完整首冻03:03:53（公开1+隐藏3）；Delivery03:04:23回告冻结，
  Coordinator03:06:33正式派单、Modeling03:06:56确认；两批apply03:07:12/03:07:37；
  revision2为2个Class和1条正确方向关系。治理读回无NamedIndividual/实例安装事实，
  关联完整无issues，Build Session正常关闭；原读回退化披露保留。
- 生产handoff03:14:53，pending/unknown/in-flight writes均空、写凭据撤回；
  公开/隐藏验收03:15:26几乎同时启动（既有027并行能力）。两组分别1/1及3/3，
  full-pass helper重新核对通过、完整分母、同freeze和model_binding，响应重检无漂移。
  **non-blind-regression PASS**，不追称盲测泛化；Runner03:18:52记录cq_verdict=pass。
  报告为run内acceptance-v3/public-regression和reports的cq-batch-0001/attempt-0001。
  公开文件sha256:59dd235a28820a2772b6ac9f41f152c659bd3a520cf7b4eee9f923e27d3676a6；
  隐藏文件sha256:c23a773fec8a344d602da3e089f1c77774750c9c69e4995006cf27f0bde9fd16，
  后者与Runner完成回执一致。
- 03:19开始显式stop，03:21:57全组退出且凭据回收；项目/模型/持久报告保留。
  宿主仅补齐本组未撤回的只读key与CLEANED却存活的源owner，未触碰其他会话。
  收尾原记录披露ModelingReadError，不能冒充自主关闭通过。

### 收尾缺陷：已定位并修复（真实窄验证通过）

sealed scope的seal_work已将admin_key清空，而ModelingReadKeyLifecycle.revoke在进入
try/finally之前就因缺admin拒绝，导致远端key未撤回、本地forwarder和明文未释放。
源码McpReadForwarder使用asyncio.to_thread(queue.get)，未stop会留下等待中的executor；
本次源stdout已有stopped而进程仍活，与该路径吻合。未据此归因其他历史105个进程。

修复复用PlatformScope现有Host bootstrap/revoke回调，仅在最终撤销时使用临时管理key，
完成原API revoke、状态读回及原只读key401/403证明后撤回临时key；不把admin放回scope，
不复活生产写权限。所有失败分支均在finally释放本地forwarder/明文，失败仍精确报错。
T0：资源完整性/真实撤销是必要边界，保留校验，只改清理顺序及已有Host生命周期复用。
GitNexus类级impact给CRITICAL（已在编辑前告知），精确方法未解析；实际聚焦检查两个
revoke调用方：启动回滚及最终cleanup，不改公共接口。当前全部相关回归 **206 passed、
13 subtests passed**（17.06s）；新增4反例修前4 failed。
真实API/MCP探针：新建测试只读key→原admin撤回→scope保持sealed→新实现撤回read key、
读回revoked并观察401、临时admin撤回、canonical forwarder退出，探针进程exit0。
无LLM调用/模型变更/新semantic-start；凭据对账最终活跃数0。原run证据不改，自动完整关闭
仍待下一获准新Runner采用，不能把宿主补位回填成旧Runner已修好。

### 需求与优化闭环

026追加本次获准1轮的有界模型及四题独立回归通过；整体仍部分验证，原更大业务范围及
完整自主交付未证明。029宿主两次私有CQ交接、完整首冻和Delivery即时回告实际成立；
Delivery唤醒窄修重载后流程走通，但首次缺陷/宿主介入/自动收尾失败保留，净效率待证。
024/025最小两批应用证据追加，不关闭自查发现错误及其他操作范围；013引用交接实际采用，
原其他范围不自动关闭；015早期反馈未执行，不判效果失败；028未触发增量，保持原状态。
Judge本轮4/4标签与依据一致，只有一轮正例，不证明错误率消除。

首semantic-start→完整独立回执23m47s，→关闭26m52s；包含本轮诊断/重载及等待，
不是无故障性能基线。有效语义工时、完整token/费用和净节省unknown，未从存活跨度推算。
上轮FlashX low与本轮Flash max不可做单因素效率归因。不增加更多平台或harness建设。
