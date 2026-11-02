# v5 多视角方法接线修复与 Demo 重建验证

日期：2026-11-02。状态：工程修复已提交，本 Demo 经检查点修模与技术接续后独立 **35/35 PASS**；运行已停止，临时凭据已撤销。

用户授权修复多视角方法迁移问题，尽量复用已有提示词，并重新执行 Demo 建模验证。
上一轮大量对话不作为新 Agent 输入；仅复用固定版本的公开业务来源及既有通用方法。
归属 R5.0-003／004 与 R4.0-007、既有动作／流程／规则／接口语义合同。

范围：复用现有 ontology-modeling 业务方法及语义合同；纠正定义节点与业务行的混淆，
补齐定义资源关系端点、被拒提案接续及关系回执身份；接通实际关系／Operation 读取，
强化逐条件、跨定义与关联适用性的生产自查和独立验证。
不恢复旧 Runner，不改变 Skill 输入隔离，不增加 Agent／节点数量或七视角输出硬门。

授权运行采用 GLM Flash／low，初始独立 3 CNY，按用户委托额度管理追加至最终上限
5 CNY，覆盖生产、纠错与独立验收；最终托管调用计量估算 **4.24746196 CNY**。
在新隔离项目从空模型建模，原 Demo 及九条 CQ 保留作为对照；新生产只得到相同四份 v2
原始材料和九条公开 draft CQ，不得到旧模型、候选、私有评分或旧资源数量目标。
独立冻结保留原 29 项业务标准，追加六项多视角／消费／一致性核对，合计 35 项。

原件目录：`workspaces/v5-runs/demo-multiview-20261102-inputs/`；
run：`workspaces/v5-runs/demo-multiview-20261102-start1/`。
GitNexus 未索引相关私有函数，影响按实际调用点及组件验证：涉及新 Task prepare、原生
读取、生产自查／纠错提示，以及共用编译／执行器的定义端点和回执身份。旧 binding 的
冻结提示不自动升级，本轮额外指导均作为署名输入保留，未热改其业务来源或候选。

## 实现与开发验证

- prepare 从现有 ontology-modeling Skill 原文复用三个业务方法章节，以 v5 路由说明承接
  根单元整合及现有语义记录；未改旧 Skill、未开放环境 Skill。
- 同一冻结过程直接复用现有 R4.0-012 的动作、流程绑定、业务规则和接口映射合同，
  没有新建平行语义格式或复制一份维护。
- read_model_resource 增加 operation-detail，保留原 ontology scope／revision 拒绝行为；
  新测试同时覆盖正确版本读取、版本漂移和越权范围。
- 自查／独立评价提示要求逐条件实际表达依据及跨定义单位、时间、状态和结果一致性；
  没有新增节点数或视角枚举的程序语义判断。

新用例修复前 3 failed、6 passed；修复后定向 49 passed。完整 v5 回归 **242 passed、
1 条既有 Pydantic warning、192.93 秒**，真实 PostgreSQL 用例无 skip。Ruff check／format
及 diff check 通过。CLI 原有 CQ 小段格式随文件 formatter 规范化，不改变其行为。
原件为 inputs 下 focused-tests.log、v5-regression.log；测试不代替真实方法采用与语义验证。

## 真实启动和输入边界

新 Project `7426e636-7fae-4234-ab48-3e50699fe7d1`，Ontology
`0bbd5523-3ad5-4dc6-920e-2a761bc83cba`；原 Demo 未变。
真实原生线程 `01a197fb-3996-7d13-9e5b-e700f1828fd3`，turn/started 已确认；
实际 glm-direct／glm-5.3-flash／low。
冻结指令 SHA256 为 `2f840d10b5ad3957b5edf8f67f9550b8fbb1b57346728ef70e4e8ebdc2d1b5a4`，
复用方法与补全合同实际进入新 binding；证据为 method-freeze-proof.json。
启动时所有自有代码差异原文及 SHA256 保存在 started-owned-code.patch，随后工程检查完成再提交。

九条公开 CQ 已通过既有导入 API 写入新项目，全部保持 draft；临时管理凭据已撤销。
生产输入中的 public-cq 与导入使用同一公开文件，无旧评价答案或旧模型数字。
金额模式的原生用量持续记账，首次回合未结束时只报告运行状态，不把 RUNNING 当语义 PASS。

## 运行中暴露的窄合同问题

初批应用十个定义，随后补入十二个属性和四个关系定义，当前已应用 26 个资源。
阶段自查返回 revise，尚未交接为完整模型。一次业务含义重复字段不一致和一次嵌套映射
裸 IRI 均在写入前被准确拒绝，原 Agent 在同一目标内纠错，不改变其业务来源。

候选 value_rules 原已在 candidate 中冻结，不增加重复平行规则。实际提示差异是复用的
映射结构描述解析后的 API IRI，而嵌套候选引用同样要求 definition_ref 或回执引用。
现于原 R4.3-025 合同补明真实声明槽位及重复 semantic_definition 一致性，v5 直接复用，
示例包含列属性引用；未放宽引用来源或原子写入校验。示例经现有真实编译器验证。

根级自查曾返回建模提案；结果 schema 拦截后原阶段重试。复用已有子级自查职责文字，
将其用于全部 self_check 阶段，明确检查实际已应用内容并以 revise 交回修改意见。
按自然边界暂停并保存待应用候选／binding 摘要后，使用同一 run 的检查点接续，摘要一致；
没有 fresh start、重复已应用批次或预算清零。

最终阶段指令修复完整 v5 回归 244 passed、1 条既有 warning；后续引用提示更新的定向
35 passed，原共享编译／接线／统一建模合同回归 41 passed。Ruff 与 diff 检查通过。
日志为 v5-final-regression.log、nested-reference-focused-final.log、
shared-contract-regression.log。开发测试不替代独立语义验收。

本次另有一次署名 host-technical 的通用候选语法输入；不含业务答案或私有验收反馈。
因此本轮实际运行不能称为完全无 Host 技术介入的默认通路证明。

34 资源版本已通过生产自查，冻结原件交给独立 GLM 上下文按 35 项检查。Host 另核对
实际生产记录：材料审查写成“业务行留 SQLite，不建 RDF 实例”，coverage 将管理行为
放在对象／规则说明中。原 R4.0-012 明确允许普通行为／参数／流程定义节点，其身份不
代表真实业务行、调用参数或已发生事件；禁止物化业务数据不等于禁止 NamedIndividual。
在当前 R4.3-025 的 semantic_level 补明此既有边界，避免把极简概念链的 Class 示例泛化
为所有语义定义的唯一载体。没有强制新节点数、每接口一个节点或特定 Ontology 拓扑。
该提示澄清的冻结输入检查 17 passed，共享基线合同 9 passed；实际采用仍待后续运行验证。

## 首次独立报告的证据复核

独立 GLM 首次返回 35/35 PASS（multiview-full-35，revision 3）。原报告保持不变，
但 Host 不接受它作为此次完整性结论：第 33 项用对象间关系和连接映射证明规则关联；
实际授权 resource-relations 读取完整返回 27 条关系，六个规则定义没有入／出向边。
第 34 项未检查全部属性，属性“凭证剩余额度”的定义仍出现旧“剩余次数额度”说法。
这是独立报告的漏检，不能以增加题目数量证明验收更可靠。

窄修复是在通用独立提示要求检查 target.resource_bindings 中相关属性与嵌套映射，
关联判定给出实际 source／predicate／target；native 精确读取工具直接复用现有
resource-relations 投影，保留获准范围、版本检查和完整性边界，不增加语义代码裁判。
新的作用域／版本用例及评价流程回归 34 passed、1 条既有 warning；实际只读凭据读取
返回 revision 3／27 关系／complete=true。原 35 项冻结标准不变，独立新上下文复查已启动。

复查 native turn 正常结束，但报告 JSON 括号错位，返回可恢复
evaluation_report_needs_correction／result_json_missing_or_ambiguous；没有发布第二份有效
语义裁决，也没有写入生产。其原输出仍存在模糊关联的推断，不能作为首次 PASS 的复证。
工程完整回归 **246 passed、1 条既有 warning、211.78 秒**，实际 PostgreSQL 用例无 skip。
随后向原生产任务交接署名 host-method-contract 的原方法／表示边界澄清，复用当前
R4.0-012 与 R4.3-025 原文，不含独立题目、私有报告或业务答案，继续原完整目标。
本次属于同 run 的质量修订，金额账本和原失败／原 PASS 报告均保留。

直接向 handoff_ready 输入被 human_input_task_closed 正常拒绝；未删除该关闭边界。
先保存带平台数据的快照 bdae501618d749599ae2db6952639927，再调用已有
WorkPlan.reopen("modeling")／MultiUnitFlow.initialize 重开根代次 1，原检查点进入
round 5，随后原消息成功交接并 resume。root-quality-reentry.json 记录前后状态与
稳定 budget_ref，没有伪造来源修订、直接改写工作状态或 fresh start。
最后一处独立提示措辞更新由评价流程 17 项测试覆盖；完整 246 项结果适用于其余最终代码。

## 质量修订中的实际表达与端点限制

原 Agent 在重开后识别行为／流程／参数缺乏独立定义，成功新增 17 个普通语义定义实体、
4 个关系谓词、14 条关系。实际 revision 4 共 55 个资源／41 条关系记录。原 Demo 的
hash／revision 4／全部九条 CQ 仍不变。新增是定义节点，不是 SQLite 业务行或已发生事件。
本轮自查准确返回 revise，保留行为定义与原对象／六规则之间的关联为已知未表达范围。

同时发现 R4.3-025 编译器 _endpoint 只接受 entity，无法表达 R4.0-003 F2 已确认的
Action→Class 以及对属性／Operation／映射定义的普通关联；底层 relation 编译及治理图
原已支持这些 IRI 端点。GitNexus 未索引该函数，实际调用点只有 _relation_build 的两端，
影响复用此编译器的 v5 Host／旧统一图提交路径；不宣称图索引已覆盖其影响。

防御复核：

1. 真实、获准资源端点及谓词仍必要；端点只能是 NamedIndividual 并非既有不变量。
2. 原拒绝是可重试的，但表达同一获准 Class 关联将持续被拒，提示不能消除这个平台限制。
3. 改为已有资源种类集合（排除 relation／fact 记录），不会放开裸 IRI、未知种类或未选中引用。
4. 业务关联含义仍由 Modeling 和独立语义验收判断，程序不推断边的业务意义。
5. 回执绑定、授权／作用域、依赖编译、原子应用及实际读回继续保护写入完整性。

只修 _endpoint 的已验证资源种类选择，保留其余校验。新增 Class／property／Operation／
table_mapping 端点和本候选属性定义端点用例复现原拒绝；relation／fact 仍拒绝。
最终编译／应用／关系读取／底层命令组件回归 **161 passed**；v5 桥接／合同 **34 passed**。
编译器 Ruff 的 7 条既有诊断与 HEAD 对比完全一致，新增诊断为 0；未顺带修改旧代码。

另针对前次评价输出把可选 CQ／SQL 键写到 case 括号外，普通冻结评价提示沿原 schema
只要求必要 case 字段，不生成无绑定的 CQ ID／SQL 状态；custom CQ 路径保持原合同。

## 被拒结果接续的上下文缺陷

model-00006 实际已生成三个关联谓词与十九条跨资源边的完整提案，却把 status 返回为
“已提出”，在应用前被 schema 拒绝。随后的 model-00007 误判无新变更。追踪原输入发现
框架仍用 state.candidate_ref 的旧已应用提案填 previous_proposal，刚被拒的 native
response 只保存在执行记录，未进入纠错上下文。这是 platform-contract 的上下文接线缺陷，
不能归因于未表达业务范围已经完成，也不能由 Host 修改提案替 Agent 过格式门。

最小修复复用已有 previous_proposal／handoff material：优先原样交接最后被拒的 native
结果，明确 application_state=not_applied，要求核对其实际变更而非旧基线后才可 no_change。
格式校验保留，不翻译枚举、不改业务候选、不自动应用，也不以旧成功回执覆盖这次拒绝。
内联与 material 两条通道新用例均先复现失败，修复后 Flow 定向 **24 passed**；最终完整
v5 回归 **248 passed、1 条既有 warning、209.11 秒**，真实 PostgreSQL 用例无 skip。

当前 run 在自然边界暂停后，Host 通过已有 material 通道原样转交 model-00006 的完整
native response，SHA256 与原文一致（rejected-proposal-transport.json），没有修改其
无效 status 或任何业务内容；署名 host-execution-contract 输入仅澄清真实未应用状态和
实际材料引用。随后同检查点接续进入 round 8；原自查也已确认十九条边仍是未完成范围。

round 8 的引用路径误用候选 item_id，19 条关系的 from 端点被 binding_not_found 拒绝，
批次未写入；原 Agent 在 round 9 自行改用 actual_baseline.resource_refs 的实际路径，
三个谓词和十九条跨定义关系在同次原子应用成功。实际 revision 5 为 **58 资源／60 关系**，
六个旧规则定义均有实际关联；Host 完整读回记录为 model-verification-linked.json 与
host-rule-edge-observation-linked.json，不作为独立裁决。原 Demo hash／revision／九 CQ 未变。
生产自查 ready，并刷新 task/project 覆盖记录到 revision 5；最终独立 35 项上下文已启动。

初始 3 CNY 账本计量至 2.81084228 CNY。依据用户原话“模型选用glm，额度你自己把控”，
Host 已明确告知并追加 **1 CNY**，本轮总上限 **4 CNY**，只用于同一 Demo 验证收尾。
预算原引用不变、没有清零或扩大业务范围，授权事件和回执为
budget-supplement-final-acceptance.json；不是原 3 元上限内完成的承诺。

## 关联存在与关联语义的再次区分

multiview-repaired-35 在 revision 5 返回 35/35 PASS。Host 对实际字段进一步复核发现：
“登记模型”行为包含管理员登记与旧库启动升级两段含义，且通过“关联业务规则”连接到
适用范围仅为旧库启动路径的升级规则；该谓词实际声明“遵循或实现”。独立报告第 33 项
虽给出了真实三元组，仍未核对这两个触发／职责是否支持该关联。因此此 PASS 同样保留
原件而不作为最终完整性结论；这是 modeling-quality 和评价漏检，不是写入失败。

在原通用业务规则合同补明：关联还须核对谓词含义、两端含义／适用性及原文条件；不同
触发／职责／效果必须由源支持共同身份或保留区分，连通不证明遵循关系。同步既有
platform-neutral 镜像而不新增表示格式；独立提示同样要求来源支持的关联含义。
Host 只交接公开原文一致性复核问题和真实资源引用，不提供私有评分、候选或指定图改法。
沿已有 WorkPlan 根重开 generation 2／round 10，在同一 4 CNY 账本内继续此有界语义复核。

## 修订删除关系时的回执身份缺陷

原 Agent 按公开原文区分管理员登记与系统旧库启动升级，新增独立升级行为、修订登记定义，
并拟删除错误“遵循”边。apply-00010 在写入前准确拒绝 relation_binding_incomplete：
旧 applied-bindings 只有关系的回执位置，没有删除所需三元组。底层关系命令原就没有资源
IRI 输出，DirectModelExecutor 只复制通用 outputs，遗漏了已应用语句的身份交接。

保留删除的真实身份与闭合 target_ref 守卫；只在已应用 create_relation 回执上，从原
应用 payload 和真实同批 item outputs 确定性保留 source_entity_iri／relation_type_iri／
target_entity_iri。失败项或缺失输出不生成身份；不猜 IRI、不允许调用方自填身份覆盖。
新增用例先 1 failed／3 passed，直接执行／跨批绑定／后端整合及边界回归 **45 passed**。
执行器 7 条 Ruff 既有诊断与 HEAD 相同，新诊断 0；未更改后端 HTTP 合同或服务代码。

当前已写模型的 33 条关系绑定由同一修复方法从原封存成功 snapshot 还原，并逐条与完整
授权关系图交叉核对，模型仍 revision 5，无业务图修改。原件为
relation-binding-repair-proof.json／relation-binding-governed-proof.json；这是 Host 技术
身份修复，不是替 Agent 修改候选。原 Agent 曾把三元组字段加进 target_ref，已明确交接
其仍必须仅含 artifact_ref／path，实际身份由 Host 解析；同检查点继续纠错。

## 最终交付与验证边界

同一主体更新与删边组合被现有写入冲突校验拒绝后，Agent 自行拆成安全变更组；本轮没有
修改该后端组合限制。revision 6 应用独立升级行为／登记定义修订及两条正确关联，
revision 7 单独删除旧错误边。每次 apply 保持原子性，不宣称跨批事务。

| 项目 | 保留的原 Demo | 本轮重建 Demo |
| --- | ---: | ---: |
| 资源数 | 14 | **59** |
| 关系记录数 | 13 | **61** |
| 模型版本 | 4 | **7** |
| 项目 CQ | 9 条 | 9 条 draft |

新模型包括 10 个 Class、18 个普通语义定义实体、19 个属性／谓词、4 个关系类型、
4 个表映射和 4 个连接映射。行为／流程／参数有独立身份，规则与适用定义存在真实关联。
资源数只用于说明粒度变化；最终判断依据原文条件、实际字段、关联及独立读取。

`multiview-final-35` 在 revision 7 独立 **35/35 PASS**，冻结题 hash 和原 29 项业务标准
保持不变；新报告明确区分管理员登记与旧库升级，核对当前图而非沿用先前 PASS。
Host 另以完整治理图确认旧错误边不存在、升级行为到模型／升级规则两条边存在，原件为
final-applicability-proof.json。原 Demo 的 revision／内容 hash／九条 CQ 全记录未变；
新 CQ 保留 draft，Q7 时间格式／时区及 Q8／Q9 事件源缺口仍明确未知，未宣称已执行 SQL。

最终工程证据：完整 v5 **248 passed**；共用定义端点／编译／应用／读回组件 **161 passed**；
关系身份执行／跨批绑定／整合组件 **45 passed**；后续仅提示变更的冻结／评价合同
**34 passed**、共享规则合同 **12 passed**。这些范围部分重叠，不相加为独立用例总数。
既有 warning／lint 基线及中间失败保留，新增代码诊断为零；未改 backend/frontend 服务代码。

最终预算沿同一 task-budget：初始 3 元、按已告知的 Host 授权事件两次各追加 1 元，
最终上限 **5 元**。建模／生产自查计量 3.85110112 元，独立评价 0.39636084 元，合计
**4.24746196 元**；30 个用量单元全部已知，provisional／unknown／inflight／待结算均为 0。
外部 Host 和未接入的辅助用量仍单列 unknown、未计入该估算，不称为供应商总账或净降耗。

原生日志可复算：建模（含技术纠错）17 回合／4640.634 秒、生产自查 9 回合／2357.813 秒、
独立评价 4 回合／911.437 秒。它们是含工具／provider 等待的墙钟，不等于有效语义工时；
Host 编码／文档／审阅有效时间未单独计量，不能据此宣称语义时间占比或效率提升。
本轮协议／平台纠错较多，验收后已停止扩展平台与 harness；后续优先复用现有检查点、
真实引用及定向治理读取，避免重复广域召回。代码与时间原件为 final-code-and-time-proof.json。

最终平台快照 `67ebea03e7a045e3a5bc06d93dcc3f11` 已保存；stop／cleanup 已完成，
模型保留、Sessions terminal、无在途写入。四把本轮管理／协议／生产读／验收读密钥均
有撤销时间，见 cleanup-final.json、key-revocation-final-proof.json、usage-final.json。

本例完成有界 Demo 的修复与语义验证；过程中有 Host 技术接续、回执身份回填及公开原文
一致性复核。没有另开最新默认路径的无人干预 fresh run，也不把本例升级为全业务盲测、
完整 R5 递归／变化验收或净 Token 降耗证明。早期漏检 PASS 和格式失败报告均未覆盖删除。
期间部分召回出现 jev_reranking_degraded／scoring_unavailable，生产与评价使用实际授权
目标引用及精确投影补足读回；本例不宣称冷启动检索或 NL2SQL 执行已经完整验收。

## 2026-11-02 用户游离节点反馈的后续修正

用户继续反馈最终模型有游离节点。实际区分出四个连接映射因画布隐藏关系定义而断链，以及
“模型标识”已建而目录映射仍声称无对应属性的真实矛盾；历史 35/35 报告未覆盖后者的完整
关联处置。未用旧 PASS 排除反馈，也未因画布零度删资源或强加业务关系。

GLM／low 在保留项目上作局部修正，revision 8 为 59 资源／62 关系投影；只改变一项目录映射，
id 列正式绑定已有模型标识，九条 CQ 全记录及原 Demo 未变。共享方法增加最终完整关联／
映射矛盾核对，v5 复用已有资源清单投影；更新引用包装的澄清同步到权威技术合同。
完整治理扫描 379 statements／59 资源，游离候选与未解析引用均为 0，仍保留 not_evaluated。

画布保留谓词隐藏规则，仅以虚线显示连接映射经过实际关系定义 domain／range 的明确引用
路径，保留中间身份与字段。相关前端构建通过；Playwright 首轮 32 passed／旧颜色刷新用例
1 failed，未改代码原样复跑该用例及新增用例 2 passed，保留失败原件；v5 合同测试
36 passed、Ruff 和 Skill validator 通过。服务已重启并健康，真实 Chrome 当前同 revision 8
画布 36 节点／46 条线／8 条引用路径，零度节点 0、页面异常 0。

独立复核保留原 35 题并增加关联／映射一致性第 36 项，`connectivity-final-36` 在同一
revision 8 **36/36 PASS**；Host 核对独立会话实际读取清单／关系及相关定义，23 次只读调用
无失败。最终快照 `4c8215883c0f45739845dcfa1d1394e5` 已保存，运行停止，模型保留，
无在途写入，四把运行临时密钥均核对数据库撤销时间。

沿原 5 元预算，累计托管调用计量估算 **4.75448420 元**，本次局部修模／自查及追加复核
增加 **0.50702224 元**；累计 38 个用量单元全部已知，unknown／provisional／inflight／待结算
均为 0。外部 Host 仍不计入，保留原非盲测、非无人干预和非净降耗证明的边界。
全部来源、变更、读取、截图与验证限制见
[游离节点核查](../../research/2026-11-02-v5-final-model-connectivity-audit.md)。
