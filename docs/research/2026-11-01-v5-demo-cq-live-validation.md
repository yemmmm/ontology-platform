# v5 Demo CQ 分阶段真实验证

日期：2026-11-01。状态：本轮有界验证完成。真实 GLM 的 3→6→9 分阶段目标读取及同 run
检查点接续通过；九题独立能力核对为 PARTIAL。九题仍为 draft，正式通过 0/9。
原模型保持 revision 4／14 资源，本轮没有 RDF apply。估算消耗 0.652301 CNY／3 CNY，
运行已停止、临时凭据已撤销。[可审阅汇总](../delivery/evidence/2026-11-01-v5-demo-cq-live/summary.json)。

## 目标与授权

用户授权继续 v5 建模，使用 Demo，将已有九条问数问题加入 CQ；允许多次建模、检查点接续，模型选择 GLM，额度由 Host 控制。本次建立独立 3 CNY 金额账本，所有生产、自查和独立评价共用，不恢复或追加旧预算。

## 已核对的依据

- 权威范围：`docs/requirements/requirements-v5.0.md` 的 R5.0-010，以及原有持续工作空间、来源修订和独立评价合同。
- 执行：`skills/modeling-dev-loop/SKILL.md`、`references/v5-runbook.md`、`modeling_team/v5/README.md`。
- 业务原文：`examples/llm-access-lab/` 及上一轮固定 v2 材料。
- 九题与稳定身份：`examples/llm-access-lab/competency-questions.json` 和真实项目 CQ。此前已导入九题，标准为 draft，未执行真实 GLM CQ 验证。
- 历史观察：`2026-11-01-v5-demo-incremental-modeling.md`、`2026-11-01-demo-model-to-sql-readiness.md`、自定义 CQ 实施记录；历史 PASS 不继承。

## 有界方案

复用项目 `40841ac8-1c93-4cb1-85ba-1a9e8fb7928b` 及本体 `755f1e0e-cf5d-47f2-a2a3-95220f4cba96`。旧运行已 stop／cleanup，临时凭据已撤销，不能直接把封口运行当作可恢复活跃检查点。本次在同一实际模型上建立新获准 v5 工作空间，保留原模型、旧报告及失败证据。

复用九个原生 CQ ID，分批选入当前生产目标：开始前 Q1—Q3；真实原生回合运行中 Q4—Q6；保存检查点并接续时 Q7—Q9。阶段性选择不删除问题，最后恢复全部九题选用。每阶段保留平台回执、固定题集、排队与实际消费证据；保存／排队不等同于被 Agent 读取。完成后用独立只读 GLM 上下文绑定实际模型和九题冻结包验证，分别报告标准就绪、模型可回答性、SQL 条件和执行状态。

不修改 Demo 补造事件，不代写生产候选，不把题目当业务事实，不把 draft 标准自动确认为业务真值。没有实际 SQL 执行就标记 not_run。

## 原件

本轮材料、授权、运行和回执保存在 `workspaces/v5-runs/demo-cq-live-20261101-inputs/` 与 `workspaces/v5-runs/demo-cq-live-20261101/`。此处随后追加实际进展、金额与验证边界。

## 首个实际阻塞及修复

`start --prepare-only` 已创建 activity=prepare 的工作记录。首次 `resume` 同步项目 CQ 后，
`SourceRevisions.activate` 一律把工作改成 model，导致 `MultiUnitFlow.advance` 跳过
prepare_scope，Host read_config 返回可恢复的 `platform_scope_not_prepared`。此时未启动
原生语义回合，没有模型写入，也没有准备平台资源。

T0 复核：平台访问范围准备保护真实授权和凭据边界，必须保留；问题是来源修订错误地绕过
它。最小修改仅使尚无 baseline_ref 的工作继续 prepare，已有基线仍按原 model 路径重入。
不增加守卫、角色、恢复框架或业务语义。新增测试先复现 activity=model 的红测，修复后
实际核对 prepare_scope 被调用。CQ／流程相关 **32 passed**，真实 PostgreSQL、无 skip。
原失败工作以带前置条件的 Host 技术记录恢复到 prepare，保留原状态及修复引用，没有代写候选。

GitNexus 未索引该 activate 符号，风险 UNKNOWN；按 cli、来源修订、单元流程及现有测试
直接核对影响，不声称图覆盖。修改源文件 Ruff 通过，两个修改文件 format check 和 diff
check 通过；测试文件原有三项 lint 问题与 HEAD 对比一致，本次未引入新诊断。
提交前 GitNexus detect_changes(scope=staged) 返回 low、6 文件、0 个已索引变更符号；
结合 activate 未命中，这不提供该新代码的图覆盖，影响结论仍来自上述直接调用点及回归。
原始工具回执另存 gitnexus-staged-detect-changes.json。

## 当前阶段证据

Q1—Q3 在启动前选入，真实 model-00001 已读取固定 cq-goals 和业务来源。
Q4—Q6 在原生回合尚未 turn/completed、没有 result.json 时由平台 PATCH 成功加入，
稳定 ID 保持，内容修订有记录；`cq-sync` 返回 queued。随后观察仍是 model-00001 活跃、
三题旧来源 activated／六题新来源 queued，未中断当前原生回合。后续实际消费仍须继续核对。

随后 model-00001 实际 turn/completed，model-00002 完整读取六题版本
`cq-f86981a17be09a2b0f7f3c0a`，next_offset=null。两者原生线程及读取摘要保存在
`stage2-actual-consumption.json`，平台九个稳定 ID 没有重复创建。2026-11-01 04:45:05 UTC
请求暂停，控制明确为 paused／waiting_for_turn_end，model-00002 仍 active；这不是已经停稳。

本次最小修复的完整 v5 回归为 **239 passed、无 skip、1 条既有依赖 warning、226.59 秒**。
原件为 `v5-full-regression.log`。未改 backend／frontend，不要求重启应用服务。

## 检查点接续

六题回合完成后控制达到 paused／settled、active={}，工作停在 self_check；六题生产核对
为 no_change。保存观察快照 `22a924b6c4e443eb85265c47991a6c9a`，真实模型读取无错误。
04:49:35 UTC 将 Q7—Q9 选入，三个平台 PATCH 均为 200，内容修订 2→3，九题标准仍 draft。
`cq-sync` 返回 queued；再读控制仍 paused／settled、无活动执行，当前来源仍是六题版本，
证明保存／同步没有自动恢复。

随后显式 resume 原 `v5-demo-cq-live-20261101`，继续原 PostgreSQL 工作空间、资源、授权
和金额账本。新来源修订使用新的 cycle／原生语义上下文；这不是旧原生线程热恢复、模型
回滚或 snapshot-fork，没有归档 Demo 项目。旧六题检查点、候选和原生终态保持。

model-00003 已完整读取九题快照 `cq-f5588ac7d3aa493f530507f8`，next_offset=null，
九个稳定 CQ ID 与平台快照一致。原件为 `stage3-actual-consumption.json`。截至此处，
开始前、忙碌中追加及暂停后显式接续的 **3→6→9** 固定目标投影／实际读取均走通；
这仍不等同于九题统计能力通过，生产终态、治理自查及独立评价继续分别取证。

## 交付范围澄清与未决业务问题

九题生产回合 no_change 后，第一次 self_check 实际返回 waiting_input，并持久保存四个
awaiting_answer 问题：凭证启用编码、调用时间语义、拒绝／回放事件来源、调价事件来源。
这是 Agent 对业务缺项的实际询问，没有被宿主伪答或直接改成 ready。

当前用户目标是分阶段加入 CQ 和验证接续，并未授权补建 Demo 事件采集。宿主以
`author=host-technical`、partial=true 提交 `host-scope-clarification.txt`，明确允许在
忠实表达获准来源后带能力缺口交接独立评价，四个问题仍无新答案、不得标为解决。
原任务和冻结 binding 保留，补充范围另存 `task-scope-clarified.json`；原生回合实际消费
该署名输入后才能继续原自查。后继评价必须独立读取它并保留技术输入身份，不能视为业务确认。

该额外往返记录为本任务 prompt-contract 交付边界不够明确的补充；不删除平台的业务询问
合同、不放宽模型正确性，也不把统计能力缺失改成 PASS。后续复用本场景时采用已补充的任务
说明；本轮沿原 start／预算继续，没有开启新模型写入链。

后继 self-check-00003-001 实际消费 `cq-live-host-scope-clarification`，完成 revision 4
治理查询并返回 ready；随后程序形成 handoff_ready。四个原业务请求仍 awaiting_answer，
reply_ids／replies 为空，resolved_request_ids=[]。三个生产候选均 no_change，当前 run
没有任何 apply operation；原 14 资源未清空、复制或增删。核对原件为
`production-handoff-verification.json`、`questions-at-handoff.json`。

## 独立评价与报告纠正

独立批次 `demo-nine-cq-20261101` 冻结九题当前 ID／内容版本／摘要，绑定实际 Ontology
revision 4，使用新的 GLM Flash／low 只读上下文。九题 criteria_ready 均为 false；评价器
没有 SQL 执行器，不能报告执行成功。完整题集、原始来源、署名 Host 输入和实际治理模型
必须实际读取，不能用生产记录或旧 PASS 替代。

首次独立原生回合完整返回后，验证器拒绝 `evaluation_original_source_not_read`，首个定位为
scope。按原生读取回执核对，缺 scope、cq-goals、baseline-inventory、human-inputs 和 target
五项直接读取；已读取冻结题、schema、business、api，并做了实际模型展开。该回合尚不是
有效语义裁决，也没有向项目发布结果，失败归在 platform-contract／读取合同与工具使用，
不归为模型质量。

保留原生事件、返回及原 report-attempt.json 的独立副本和 SHA256；仅在现有重试控制文件
的 contract_feedback 添加署名 Host 技术读取清单，明确本回合必须直读全部九个 material_id
并再次查询模型，不提供答案或预期分数。题集、标准、材料正文、模型、目标 revision 和
同一 evaluation-id 均未更改。随后按既有纠正机制启动独立新回合，原错误及追加反馈见
`independent-attempt-1-rejected-original.json`、`independent-read-coverage-host-feedback.json`。
此项属于一次技术补位，不宣称首轮自主完整读取已经通过。

第二个独立回合实际读齐全部九项材料并重新展开模型，但返回 Q1／Q2／Q5／Q6
passed=true、outcome=pass，违反九题标准仍为 draft 的既有合同，被
`cq_unready_criteria_cannot_pass` 可恢复拒绝；该回合也未发布有效结果。
原 report-attempt 与原生报告继续保留。宿主仅向同一重试反馈追加冻结元数据清单，明确
criteria_ready=false 时 passed=false／question-answer-review，并强调 answerability 与
sql_readiness 仍由独立侧按实际证据判断，不提供业务答案或这些维度的预期分类。
标准不确认、原模型不修改，第三个独立回合沿相同冻结继续。该问题属于结果分层合同的
工具使用／prompt-contract 不遵从，不能当作新增 CQ 失败或模型语义质量失败。

第三个独立回合 `evaluation-582e71198f7406ddd8af-002` 实际读齐全部九项材料，材料字节、
读取摘要与冻结 manifest 一致；实际模型读取只使用 read_material、query_semantic_context、
read_model_resource。最终冻结 `cq-freeze-2a4dbe6bafbd4da5ccf7f333`／九题快照
`cq-f5588ac7d3aa493f530507f8`／模型 revision 4 的报告通过现有完整性与版本校验，
结果为 **PARTIAL、0/9 正式通过**。九个结果均为 question-answer-review，已按匹配版本
写回项目，recorded=9、skipped_stale=[]。两份先前被拒原生报告没有作为有效裁决发布。

| 问题 | 独立可回答性／SQL 支撑 | 当前边界 |
| --- | --- | --- |
| Q1 模型调用与历史扣额统计 | 支持／支持 | 可按成功记录与历史 charged_units 统计，保留零调用模型 |
| Q2 凭证授权与调用汇总 | 支持／支持 | 两组明细分别聚合，避免授权与调用相乘 |
| Q3 新调用准入组合 | 条件支持／条件支持 | api_keys.enabled 的物理编码仍缺明确绑定依据 |
| Q4 正余额但不足调用 | 条件支持／条件支持 | 同一凭证启用编码缺口；余额与当前 quota_cost 比较已有依据 |
| Q5 历史扣额与当前配置差异 | 支持／支持 | 不把该差异解释为调价历史 |
| Q6 跨凭证重复请求标识 | 支持／支持 | 去重键为 (key_id, request_id)，request_id 非全局唯一 |
| Q7 UTC 日统计 | 条件支持／条件支持 | created_at 的时区、格式与精度不足，不能自行代入 UTC 边界 |
| Q8 拒绝与回放统计 | 不支持／不支持 | 缺获准事件来源及对应映射；缺行不等于次数为零 |
| Q9 最近调价历史 | 不支持／不支持 | 当前配置与成功扣额记录不能替代变更事件 |

上述四题“支持”是模型信息／SQL 条件维度的独立判断，不是正式通过；九题标准仍 draft。
全部 sql_execution=not_run，本轮没有执行 SQL。原件为
[独立私有报告](../../workspaces/v5-runs/demo-cq-live-20261101/evaluations/demo-nine-cq-20261101/private-report.json)
及同目录 public-feedback.json，发布回执见 inputs 的 independent-nine-cq-draft-correction.log。

独立理由也有表述边界：Q3／Q4 对 enabled 编码的概括偏宽，Q4 还将 models.enabled
并列为缺口；实际 revision 4 的 models 表映射已经明确 1=启用、0=停用，当前缺项须收窄
为 api_keys.enabled。原报告不改写，该理由差异不改变 Q3／Q4 的条件支持分类，也不能因
分类相符而宣称全部私有理由无误。本次不升级为完整 L1 语义 PASS。

## 最终持久化、计量与收尾

实际元数据回读确认仍为九个原 CQ ID、全部 active／selected、标准全为 draft；重复导入
仍返回同九个 ID。模型 before／after 均为 revision 4、14 资源，同一 IRI 集合；Batch 数
仍为 4，没有新增模型写入。九题不是 RDF 业务资源，也没有补建 Demo 事件功能。

本轮采用一个原始九题目标，分批吸收不是新的实质修模轮；记录为 **1 次 fresh semantic
start／1 轮建模任务／3 个生产建模原生回合／2 个生产自查原生回合／3 个独立原生回合**。
来源 cycle 和工作状态的 round=3 不冒充三个 fresh starts。所有回合共用原 3 CNY 账本。

| 原生阶段 | 输入 token | 输出 token | 回合数 | 区间并集 |
| --- | ---: | ---: | ---: | ---: |
| 生产建模与目标增量核对 | 1,579,157 | 31,187 | 3 | 13 分 31.549 秒 |
| 生产自查（含范围澄清后接续） | 224,639 | 2,945 | 2 | 2 分 21.706 秒 |
| 独立评价（含两份被拒原件） | 705,193 | 17,176 | 3 | 7 分 10.337 秒 |
| 合计 | **2,508,989** | **51,308** | **8** | **23 分 03.592 秒** |

输入加输出为 2,560,297；缓存输入 2,104,000 已包含在输入内，不重复相加。复用既有
distinct-thread 统计脚本取各线程最后累计值，包含两份被拒评价；八个原生计量单元均终态，
known-native 覆盖 complete。账本已计价 **0.65230100 CNY**、provisional=0，估算余额
**2.34769900 CNY**。外部 Host 用量 unknown，单列且不扣任务金额；平台内部排序用量未
完整归集，全任务计量保持 PARTIAL，不冒充提供商最终账单或净降耗证明。

首语义原生 task_started 为 04:40:23.372 UTC，末原生终态为 05:09:27.323 UTC，窗口
29 分 03.951 秒。最早保留宿主观察为 04:37:04 UTC，至运行 cleanup 05:10:59 的观察窗口
33 分 55 秒；观察至首语义开始为 3 分 19.372 秒，不冒充用户发言的精确时间。
生产建模及自查原生区间合计 15 分 53.255 秒，小于该观察窗口一半；原生区间包含工具／
上游等待，宿主有效劳动未精确计量。分阶段专项验证、独立两次报告纠正和交付边界澄清
占用了验证时间；全量工程回归 226.59 秒与生产重叠，不能再叠加成墙钟时间。
本轮没有扩展平台／harness；更短后继路径是一次选入完整九题，首轮明确完整来源清单、
draft 标准与能力维度，仅在专门测接续时重复三阶段。

最后保存九题独立 PARTIAL 观察快照，并 stop／cleanup。控制 stopped、active={}；
existing-retained，模型和项目 CQ 保留；无在途 Attempt、无活动 Session／Lease，
aggregate_keys_non_active=true，协议／管理凭据撤销。两份临时读取凭据也另从实际
ApiKey 记录核实 revoked_at，确认全部非活动。原件为 snapshot-nine-final.json、stop-final.json、
cleanup-final.json、read-key-revocation-verification.json。工作树原有无关改动保持。

## 验证边界

完成的是复用九条已保存 CQ、分批选入生产目标、自然回合边界处理、同 run 检查点接续、
独立分层能力核对和收尾。没有在每阶段重复创建相同九题；没有实际 RDF apply，因此
本轮不证明写入在途时追加 CQ 的全部故障窗口。一次原生身份交接、初始化状态恢复、
任务范围澄清和两次评价技术反馈全部保留，不宣称无 Host 补位的自动交付。
公开构造 Demo、既有模型核对与草稿标准不构成客户盲测、完整需求验收、正式 SQL E2E、
任意规模、业务能力全满足或净降耗。工程 239 passed、三阶段真实运行证据及独立 PARTIAL
各自保持证据层级。
