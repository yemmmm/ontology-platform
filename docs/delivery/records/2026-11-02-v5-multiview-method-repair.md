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
