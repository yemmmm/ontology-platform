# Demo GLM 冷启动建模复测

日期：2026-11-02。状态：**本轮测试结束，整体 PARTIAL，未取得合格的完整独立语义验收**。同一 run 内三轮业务建模已实际应用至 revision 3，保留 51 个资源；最后的完整读取补验因报告格式失败及读取覆盖缺口未闭环。运行已停止，临时平台凭据已撤销。

用户要求继续使用 Demo 测试建模效果，模型使用 GLM。本轮复用当前完整 Demo v2 原始来源与九条公开 CQ，从新隔离本体开始，核对当前提示和工具合同能否复现完整模型，保留现有 revision 8 模型及历史证据。按已确认默认，为独立复测创建 3 CNY 金额预算，生产、自查、独立验收共用同一账本；外部 Host 用量单列。

实际结果表明，GLM 能根据准确公开反馈自行修正字段合同、结构关联、职责角色和接口绑定；但首轮交接、自查与独立判分不能稳定保证完整性，且在两次补验中连续产生不合规报告。因此本轮不能记为首次自主成功，也不能用若干原始 36/36 PASS 宣称完整 L1 通过。已知托管调用费用按冻结价表估算 **1.82846344 CNY**，未追加预算。

## 来源与验证范围

- [R5.0-001／003／004／006](../requirements/requirements-v5.0.md)：可控运行、完整建模、应用读回与独立验收。
- [v5 Host runbook](../../skills/modeling-dev-loop/references/v5-runbook.md)及[当前入口](../../modeling_team/v5/README.md)。
- Demo 原文：`examples/llm-access-lab/business.md`、API／Schema 的获准冻结投影、`competency-questions.json`。
- [前轮最终模型核查](2026-11-02-v5-final-model-connectivity-audit.md)：revision 8，59 个资源，36/36 有界独立 PASS；该结果不继承为本轮证明。

本轮采用 `scripts/modeling`、`glm-flash-low`（glm-direct／glm-5.3-flash／low）。生产不接收旧模型、旧候选、私有问题、答案或评分。独立评价另用冻结包与只读上下文，机械关联扫描不替代语义评价。任务范围仅为公开构造 Demo 的有界复测，不代表客户业务盲测、SQL 执行验收、完整 L2 或净降耗证明。

## 执行记录

输入、预算、原始事件和结果保存在 `workspaces/v5-runs/demo-glm-repeat-20261102-inputs/` 与 `workspaces/v5-runs/demo-glm-repeat-20261102-start1/`。实际启动、应用、读回、评价、用量及资源收尾将据原件追加。

启动代码基线 `1a356e8`，Demo 代码未变。生产实际绑定 glm-direct／glm-5.3-flash／low，新原生线程 `01a19b47-b179-7ad0-b49b-0845793f747c`，首个原生 task_started 为 `2026-11-02T08:02:10.377Z`。新 Project 为 `54a5f3f0-3558-4fec-8ff7-e5b919d9d81f`，Ontology 为 `0e79fff2-5fe4-4bab-89c3-7332b24645fe`；初建第 1 轮、fresh semantic start 1。36 项标准在生产前冻结，保留原题摘要，剔除旧运行的方法观察和局部修复反馈，避免把旧运行证据当作新运行输入。

## 实际失败与窄修复

首个候选 42 项变更在 `apply-00000` 整批被原子拒绝：四个表映射的 `source_key` 使用了带 scheme 的连接串。回执为 `not_written`，revision 仍为 0；预分配身份不算实际资源。GLM 根据准确反馈自行修正，Host 没有代改候选。

`apply-00001` 随后因 `ontology_lease_conflict` 再次明确未写入。数据库和原始提交证据确认持有租约的是首个被拒批次的 Session `bb72d931-1a34-473f-8bb9-a11d740c91bb`。v5 `_close_applied_sessions` 跳过所有 `not_written` 操作，导致已确认未写入的旧 Session 和租约没有收口。原运行自然暂停，第三个原生回合返回的候选保留。

T0 复核：并发写租约直接保护应用完整性，须保留；本例的问题是已知未写入后没有执行已有收尾，而非应删除租约。允许现有关闭流程处理 `not_written`，仍使用实际快照绑定所有者、平台的在途 Batch 检查和正常 Session 终止释放，不放宽未知／部分写入门，也不增加恢复框架。直接调用点仅后续 apply 和 finalize；GitNexus 未找到该新方法，风险 UNKNOWN，未宣称图谱影响覆盖。

先扩展既有测试，得到 `not_written` 分支 1 failed／1 passed，准确复现后继应用前未关闭原 Session；再删除该跳过分支，相关文件 **18 passed**。未知／部分结果和缺回执仍保持阻断。实际沿既有 finalize 关闭遗留 Session，读取证实 revision 0、bindings 为空；原候选、拒绝和 Session 回执保留。全量 v5 **251 passed、1 条既有 warning、110.34 秒、无 skip**。测试文件 Ruff／format 通过；worker 的既有 I001 导入顺序问题与 HEAD 完全一致，未引入新诊断，见 `ruff-baseline.json`。

证据位于输入目录下 `lease-conflict-before.json`、`lease-closure-red.log`、`lease-closure-green.log`、`lease-closure-live-recovery.json`；没有修改 backend／frontend，不需重启平台应用服务。

## 首版实际模型与独立报告的限制

第三次被拒 `apply-00002` 为 `field meaning column is not mapped: token_hash`，仍未写入。GLM 自行补齐该列映射后，`apply-00003` 实际原子写入 **revision 0→1**，42 项变更形成 **39 个资源**（三项为关系断言）。生产自查返回 ready。

复用通用完整治理扫描，读到 232 条 statement／39 个资源，coverage complete、未解析引用 0，但有 **12 个 no_observed_association 候选**；机械结论仍为 not_evaluated。初版平台数据快照为 `108af33570744eaab757d25b2e36e531`。扫描未在首次独立评价前反馈给生产。

独立 `fresh-full-36` 报告 36/36 PASS，但原第 36 项没有处置上述 12 个候选，第 32 项将四表／三连接映射列作接口映射依据；第 20 项也误把 42 个 change binding 称为资源数。实际 41 次成功只读调用包括七项材料、一次治理查询、33 次精确读取；这些读取并不能自行补足判定中的缺口，原报告保留，未据此宣称完整多视角语义通过。

随后 `fresh-association-four` 在同一 revision 1 复核原第 31、32、33、36 项（正文保持，仅局部重编号），同样报告 PASS。它明确承认 12 个规则／流程／行为节点没有结构边，却以语义定义文本提及充当关联；接口及角色视角仍没有准确的实际表达定位。该结论与当前方法的“明确引用／逐项有源处置”存在口径冲突，不能用两个 PASS 相互证明。

本次以 **PARTIAL／待修订** 保留完整多视角结论。当前 R4.0-002 F2 要求结构化关联解析到定义，R4.0-024 F3 要求合理独立或待定有业务依据与影响说明；不是要求零游离或固定节点数。Host 通过正常 source-revise 给生产追加公开完整读回及已有方法合同，未提供私有题目、答案或评分，也没有代写候选。原五份来源未变，原模型身份、预算及历史报告保留；新公开材料 `public-model-review` 在自然边界激活，进入第二轮质量复核。该介入不记为自主建模／自主验收完成。

## 第二、三轮实际修模

第二轮 `apply-00004` 实际写入 revision 1→2，形成 **41 个资源／274 条 statement**；完整机械扫描的关联候选、未解析引用均为 0。模型新增接口范围定义及通用“适用于定义”谓词，为原 12 个候选建立结构关联。但该通用谓词被标成 `business_role`，接口仍主要是路径／请求类型清单，不能用零候选代替角色含义与接口字段绑定正确性。

独立 `repaired-full-36` 在 revision 2 返回 **PARTIAL，35/36**。第 36 项暴露独立读取方把 `resource-relations` 当成按 anchor 过滤的局部图，多次读取相同的完整本体图后，仍宣称覆盖不足。这属于读取合同理解问题，不能推导为模型资源缺失。评价提示最小补充既有行为：该 family 返回整个获准本体关系图，应按真实端点和 completeness 检查，同 revision 不按不同 anchor 重复读图；没有新增平台过滤行为。相关 acceptance／material-read 测试 **36 passed、1 条既有 warning**，CLI Ruff 与 format 通过。

针对实际角色误标，共享 `ontology-modeling` 方法只澄清业务职责／参与、谓词种类、RDF 类型和语义角色的区别；不增加节点配额或新硬门。Skill validator 与冻结合同测试 **17 passed**。原绑定没有热替换；本轮通过完整 source-revise 显式追加公开治理观察与通用澄清，第三轮保留原定义身份、预算和正确工作，不传私有题、答案、评分或旧候选。

第三轮首次返回包含 JSON 语法错误，`model-00005` 得到 `result_json_missing_or_ambiguous`；并非仅因回复含说明文字。随后 `model-00006` 的七个新增实体漏 `value.label`，触发七项根错误及 24 项下游引用错误，编译拒绝、未写入。GLM 在 `model-00007` 自行修复，Host 没有修改候选或增加解析恢复机制。

`apply-00007` 实际写入 **revision 2→3**，51 个资源／341 条 statement，Batch `9c7f56a5-4045-4f7f-91fa-9fd2023aa00b`、Attempt `4053df6a-4f9b-4340-aee1-75b77a6f67ba`。它将通用适用谓词改为 `applicability`，增加管理操作者和调用方的职责及负责范围，增加五组请求字段／参数到既有业务属性或凭证定义的绑定，并保持响应空 schema 等真实未知。完整治理扫描为 complete，关联候选 0、未解析引用 0，机械语义判定仍为 `not_evaluated`。生产自查 ready 后，启动 `final-role-binding-full-36` 独立验收；该包保留原 36 题与主冻结身份，仅同步已公开的 source-revise 材料。

本任务是 **1 次 fresh semantic start、3 轮实质业务建模**。技术纠错回合与自查不重复计业务轮；金额授权不套用默认三轮余额门。第一轮源中四表 `source_key`、缺列映射和第三轮 JSON／label 错误属合同或格式纠错；租约泄漏属平台合同缺陷；关联、职责和接口含义缺口属建模质量；独立重复读图属读取合同问题。各层证据与原报告分别保留。

## revision 3 的完整读取补验

`final-role-binding-full-36` 原始报告为 **36/36 PASS**，绑定 revision 3、原 `freeze_id=v5-demo-glm-repeat-36-20261102`，原题 SHA256 为 `18a435959ef7b6cb4aa35ba6881042ad5f3acf252e568d4202f082a96183aca2`。本次 37 次成功只读调用包括八份材料、一次治理查询、28 次资源读取；完整关系图只读一次，85 条边、paging complete，已避免按不同 anchor 重复读同一全图。

但它仍未证明整体验收：合并查询中直接返回的 `semanticDefinition` fact、资源内的 `data.semantic_definition` 以及精确 detail 后，仅有 **43/51** 份定义正文。八个未读项包括字段对应、负责范围、接口归属、授权访问、凭证启用等属性／谓词的定义。查询还明确返回 matches truncated、context expansion incomplete／scoring unavailable，不能把 scope complete 或关系图完整换成定义全文覆盖。原 PASS 保留并附证据限制，不直接升级为完整 L1 通过。

Host 初次统计误报 29/51，原因是漏算查询资源对象中的嵌入定义，后核对原始响应改正为 43/51，并公开纠正；不是模型变化。原补验导航包及其错误历史数字不重写，另存 `read-scope-host-count-correction.json`。这项 Host 统计错误也属于本轮成本与证据限制。

随后只追加 **一次** `complete-read-full-36` 全量读取补验，模型、业务范围、原题与预算不变。独立材料仅增加从真实应用绑定提取的 51 个去重资源 IRI、原生类型和合法读取 family，不含私有业务答案、原报告语义理由或修改候选。原冻结目标本来已含这些绑定；这次补充用于直接执行已有完整性条件，不另加评分标准。最终结论以该独立上下文自己的读回及逐题判断为准，不能继承前报告的 PASS。

该补验首次执行已读到全部 51 份正文与 85 条完整关系边，原生报告仍为 36/36 PASS，但附加了 `cq_id: null` 等不适用于本冻结标准的可选 CQ／SQL 字段，触发 `result_schema_invalid: cases/35/cq_id: None is not of type 'string'`。原生输出与只作归档解码的 `unvalidated-complete-read-report-attempt0.json` 均保留；不删除字段后冒充正式验收。随后沿相同 evaluation_id 的已有报告纠错通道运行 attempt 1，反馈仅为准确格式错误，不修改候选、评分合同或私有语义判断。没有为此新增解析器、放宽 schema 或建模轮次。

attempt 1 再次自称 PASS，却在第 29 项的 JSON 值中输出 `" frozen-c29".trim()`；真实错误为 `Expecting ',' delimiter`，line 34／column 57／position 16093，回复共 21442 字符。框架返回可恢复的 `result_json_missing_or_ambiguous`，没有正式报告。这个新上下文也仅读到 **47/51** 份定义正文，不能继承上次上下文的全量读取。两次补验均只读 API 的 12000/13424 字符、runtime-observations 的 12000/13393 字符，未沿 `next_offset` 读取尾页；直接读过 source ID 不等于读完来源。

另一个读取合同观察：`read_model_resource` 的说明与技术导航材料把 `resource-list` 写为不按 anchor 过滤的全本体清单，但本轮两次实际调用均只返回 1 项、`visible_count=1`、`complete=true`。不能用该标记证明 51 资源清单完整；本轮全范围由冻结的去重应用绑定、完整治理 SPARQL 扫描及实际逐项正文交叉核对。`resource-relations` 则实际返回完整的 85 条关系。此处只记录准确行为与合同不一致，未顺带修改读取 API 或扩建验收框架。

有界收口不再追加评估执行；预算仍有余额，不把余额当作必须耗尽的目标。完整语义验收保持 **PARTIAL／未接受**。保留各次原件，而不把 JSON 修补、其他上下文的读取或 Host 检查算成独立 Agent 的当前证明。

| 实际模型 | 资源／statement | 机械关联候选／未解析引用 | 独立原始结果与证据限制 |
| --- | ---: | ---: | --- |
| revision 1 | 39／232 | 12／0 | 主 36/36、局部 4/4 PASS；关联处置与多视角证据不足 |
| revision 2 | 41／274 | 0／0 | 35/36 PARTIAL；重复读取全图、角色与字段绑定仍有缺口 |
| revision 3 | 51／341 | 0／0 | 主报告 36/36 PASS，但只有 43/51 正文；补验 0 读到 51/51 却 schema 失败，补验 1 仅 47/51 且 JSON 语法失败；两次补验来源尾页未读 |

零候选只说明完整机械扫描未观察到游离或未解析引用，不证明各关联含义正确；资源数也不是模型质量评分。前轮 59 资源／revision 8 的结果与本轮范围、Host 介入、失败及读证路径不同，不作能力或成本排名。

## 用量、时间与资源收尾

所有 17 个已知托管原生执行均为 Codex／glm-direct／glm-5.3-flash／low：8 次生产建模调用、3 次生产自查、6 次独立评价执行（5 个 evaluation_id，含一次报告纠错）。失败与纠错消耗全部保留。

| 托管执行类别 | 输入 token（含缓存） | 其中缓存输入 | 输出 token | 冻结价表估算 CNY | 原生执行区间并集秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 生产建模 | 3477253 | 3056832 | 110063 | 0.92180964 | 2216.899 |
| 生产自查 | 896022 | 742144 | 5715 | 0.19158088 | 289.136 |
| 独立评价 | 3288451 | 2928896 | 74235 | 0.71507292 | 1790.499 |
| 合计 | 7661726 | 6727872 | 190013 | 1.82846344 | 4296.534 |

取每个不同原生 thread 的末次累计 usage，未把累计样本重复相加；输入包含缓存，不能再把缓存数加一次。总输入加输出为 7851739 token。预算授权 3 CNY，剩余估算 1.17153656 CNY；已知原生计量 17/17、unknown=0、provisional=0、inflight=0、pending_settlement=0，价表版本 `user-20261020`。这些是本地冻结价表估算，不是供应商账单。

外部 Host 用量与有效劳动时间未知，按现有规则单列、未计入任务费用或预算；平台内部排序等未接线辅助用量也未完整采集，不按零估价。**全任务计量仍为 PARTIAL**，不据高缓存率或局部 token 数宣称净降耗。

最早保留的 Host 观察为 08:00:39 UTC，首个真实 semantic start 为 08:02:10.377 UTC，相隔约 91 秒；这不是精确的用户授权时间戳。最后原生回合结束于 12:52:01.115 UTC。首末原生时间窗 17390.738 秒包含轮间停顿／接续等待，不能叫作有效建模时间。上表原生区间含工具与供应商等待；生产合计区间为 2506.035 秒，也不能代替纯语义推理劳动。基础设施、harness、Host 评审与文档的有效劳动没有完整计时，不编造比例；未在本轮继续扩展平台或 harness。

最终含平台数据快照：`e69f290555e340608dd9bb4d116bef75`，51 个对象、model_read_error=null，见 `snapshot-final.json`。运行 stop 生效，control.mode=stopped、active 为空，`scope_disposition=written-retained`；该处置只表示非空工程模型保留，不表示语义接受。旧清理器的 `failed-written-retained` 兼容标记在回执中另列。

`cleanup-database-readback.json` 的只读核对确认：本轮四个明确归属的临时平台密钥均已撤销，六个 Build Session 均为 completed／cancelled，当前 Lease 已释放，无 validating／applying／recovering Attempt；旧 Ontology revision 8 与本轮 revision 3 均保留。三个机械扫描的临时管理员也分别有撤销成功回执。没有撤销共用 GLM 账户凭据，没有删除实际模型、失败 Workspace 或原始事件。

## 交付与未证明范围

窄租约修复已提交为 **`859aa65`（Close rejected modeling sessions before retry）**；全量 v5 251 项结果覆盖的 worker／测试文件 SHA256 到收尾时未变。后续两处指令澄清仅复用相关合同、validator、Ruff／format 与真实读回证据，不重复跑无关后端／前端套件。指令暂存 diff 的 GitNexus `detect_changes` 返回 2 文件、0 已索引符号、risk low；这不代表获得图谱影响覆盖。文档链接与 diff 格式另作本地检查。

本轮通过显式公开 source-revise 提供角色澄清与技术导航；**修复后的默认新绑定能否从头自主完成，尚未重新冷启动验证**。当前没有完整业务盲测、完整 L2 重复性、九条 CQ 的 SQL 执行或真实供应商模型能力测试。Q7 的 created_at 格式／时区待确认，Q8 拒绝／回放事件与 Q9 调价历史无持久来源，均不得编造或按零回答。后续改善重点有本轮直接证据：完整分页读取、跨定义覆盖、自查与独立判分准确性、结构化报告输出稳定性；本轮不把这些问题扩大成新的平台完成门。

原始工件位于前述 inputs／run 目录，关键索引为 `source-freeze-audit.json`、`independent-read-audit-first.json`、`independent-read-audit-final.json`、`independent-read-audit-complete.json`、`independent-report-format-failure-final.json`、`observed-usage-summary.json`、`final-budget-summary.json`、`snapshot-final.json`、`stop-final.json`、`cleanup-final.json` 与 `cleanup-database-readback.json`。私有题与语义理由未回传生产，原件未随研究文档提交。
