# v5 多视角方法接线修复与 Demo 重建验证

日期：2026-11-02。状态：修复及工程检查通过，真实建模已启动，独立语义验证待完成。

用户授权修复多视角方法迁移问题，尽量复用已有提示词，并重新执行 Demo 建模验证。
上一轮大量对话不作为新 Agent 输入；仅复用固定版本的公开业务来源及既有通用方法。
归属 R5.0-003／004 与 R4.0-007、既有动作／流程／规则／接口语义合同。

范围：冻结现有 ontology-modeling 业务分析／多视角／身份复用章节，补全已有语义合同，
接通 Operation 精确读取，强化实际模型逐条件核对与跨定义一致性提示。
不恢复旧 Runner，不改变 Skill 输入隔离，不增加 Agent／节点数量或七视角输出硬门。

授权运行采用 GLM Flash／low，独立 3 CNY 金额预算，覆盖生产、纠错与独立验收。
在新隔离项目从空模型建模，原 Demo 及九条 CQ 保留作为对照；新生产只得到相同四份 v2
原始材料和九条公开 draft CQ，不得到旧模型、候选、私有评分或旧资源数量目标。
独立冻结保留原 29 项业务标准，追加六项多视角／消费／一致性核对，合计 35 项。

原件目录：`workspaces/v5-runs/demo-multiview-20261102-inputs/`；
run：`workspaces/v5-runs/demo-multiview-20261102-start1/`。
GitNexus 未索引 modeling_instructions，影响按实际调用点检查：只影响新 Task prepare、
原生精确读取工具 schema 和独立评价提示；旧 binding／checkpoint 不自动升级。

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
