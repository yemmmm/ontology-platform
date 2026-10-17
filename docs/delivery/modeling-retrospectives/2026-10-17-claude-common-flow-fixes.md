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

本次仅提示／文档变更；合同与相邻回归结果见本次追加记录。无需产品服务重启，
工程检查不表示新轮语义或效率PASS。仓库已有未提交文档和演示材料保持原状。

工程验证：backend目录下以env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest运行
test_contracts、test_r4326_minimal_chain、test_r3011_acceptance、test_delivery_host_actions及
test_r4329_independent：74 passed、3 subtests passed（4.71s）。delivery和modeling-dev-loop
Skill校验通过，Task/Profile/glm-flash-max配置验证通过，git diff --check通过。
无执行代码改动，无产品重启。GitNexus未索引到所查Host符号且返回旧文档位置，故不宣称
图覆盖；实际变更以本地diff和合同回归为证据。
