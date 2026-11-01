# v5 多视角建模方法接线与采用复核

日期：2026-11-01。状态：已定位默认方法供给的迁移缺口；未修代码或启动新建模。

用户要求定位“少对象＋长说明”形成原因，确认 v5 是否保留 v4 多视角建模。
本次沿 v5 冻结指令、原生执行输入、表示合同和自查／验收核对实际接线；
不启动新建模或改变当前唯一模型，不把字段存在当作方法采用。

对象：Demo 原 run `v5-llm-access-lab-20261031-start3`、v2 续建 run，及其实际冻结的
生产指令；v4 对照为通用 Modeling／Coordinator 包及 ontology-modeling Skill。

来源：R5.0-003 及其声明方法，R4.0-007，多视角语义合同，v5 contracts／execution／instructions，
原 run 的 binding 与原生工作目录；前序实际模型与记录复核见
[模型粒度审查](2026-11-01-demo-model-granularity-audit.md)。

## 结论

**设计保留了多视角，当前 v5 的字段和平台能力也支持多视角；但默认实际执行输入没有完整继承
v4 的多视角建模方法。Demo 原建模与 v2 续建均未获得旧方法或等价的完整方法供给。**
不能因为模型有 semantic_role、界面有七个视角按钮，便声称真实建模完整采用了多视角。
此次“少对象＋长说明”首先是方法迁移与验证缺陷，不是已证明的模型能力或预算问题。

首层归为 platform-contract，修改面为 prompt-contract／获准方法冻结装配；结果层出现了
modeling-quality 缺口和独立验收漏检。已经定位具体缺失的输入路径，但未做修复对照运行，
不将某条提示、GLM 或 low effort 单独认定为唯一因果。

## 设计目标没有取消多视角

[方法设计 §2](../delivery/designs/2026-10-26-ontoweave-modeling-methodology-design.md)明确将
“多视角统一语义图”列为已有基础，并引用 R4.0-007／014 与 ontology-modeling Skill。
§5.1 仍要求从业务目标、端到端场景、事件／状态变化／决策点分析到对象、角色、条件、规则、
指标及必要的数据／接口映射。新工作空间是组织这些原则的方法，不是取消它们的授权。

这不要求七个 Agent、固定七轮或每个视角必须产生节点；视角是否适用仍由获准业务依据决定。
未分析不能直接当不适用，不能只给已有 Class 贴一个 role 就代替这项分析。

## v4 与 v5 实际接线差异

| 方法层 | v4 通用路径 | 当前 v5 默认路径及 Demo 原件 |
| --- | --- | --- |
| 生产方法 | Modeling package 声明 required_skills=ontology-modeling；包指令有 Active multiview collaboration | 使用 v5/instructions/modeling.md 摘要与冻结技术合同；没有该方法段落 |
| Skill 供给 | 旧 Codex Runtime 将 package.required_skills 复制为只读挂载并显式注入 | 新 CodexAgent 不挂载项目建模 Skill；实际五项环境 Skill 全部 disabled |
| 多视角职责 | Skill 与 Modeling／Coordinator 指令要求视角覆盖、稳定定义身份、跨视角引用及共享变更核对 | 有通用 S0—S9 和记录职责，但缺完整多视角评估及动作／规则／流程的对应建模指导 |
| 表示合同 | 完整 R4.0-012 包含多视角字段、动作、流程绑定、业务规则与接口映射语义 | 只抽取 multiview_semantic_definition，另详细带上 Class／关系／数据映射等执行片段 |
| 全局整合职责 | Coordinator 维护覆盖与实际表达对应，Modeling 提供原件 | v5 根工作单元可承担整合，但没有完整承接旧多视角覆盖职责的默认方法内容 |

没有单独 Coordinator Agent 不是缺陷；职责可以由根工作单元承担。缺陷在方法和职责没有
完整进入它的实际输入，不应以恢复角色数量或旧 Runner 作为修复前提。

## 三处决定性证据

### 1. 组装器只抽取字段级多视角声明

[contracts.py](../../modeling_team/v5/src/ontoweave_modeling/contracts.py) 的
`modeling_instructions()` 读取完整 `r4-0-012-modeling-contract.json` 后，实际仅选取：

```python
"semantic_definition": semantics["multiview_semantic_definition"]
```

完整合同中的以下四块没有进入 Demo 两个 run 的冻结技术输入：

- reusable_action_semantics：动作、参数、适用和结果的语义。
- process_binding_semantics：流程、调用位置、参数绑定、分支和结果之间的语义。
- business_rule_semantics：规则与相关对象、Action、流程的明确关联。
- interface_mapping：接口、消息、字段、业务参数和标识对应的语义。

保留下来的 semantic_role 规则确实列举 object、behavior、rule、business_role、process、
data_mapping、interface_mapping，但这是一个资源的角色声明，不能代替上述分析方法。
普通 entity／property／relation／operation 等写入能力没有被删除。

### 2. 独立运行环境没有其他方法补给

[codex_agent.py](../../modeling_team/v5/src/ontoweave_modeling/codex_agent.py) 的
`CodexAgent.start()` 只读挂载运行代码、获准材料及所需工具配置，没有挂载 ontology-modeling。
它会关闭环境中发现的 Skill，并将传入的 `self.instructions` 作为 developerInstructions。

原建模与增量运行的实际 `executions/model-00000/agent/events.jsonl` 都记录了五项原生 Skill，
全部 enabled=false；磁盘没有 ontology-modeling/SKILL.md。不是依据当前目录猜旧进程读了什么。
对应 frozen binding 也没有 ontology-modeling 引用或旧 Active multiview collaboration 段落。

关闭未批准环境 Skill 是输入隔离措施，不应全局取消。需要补的是获准、固定版本的方法内容，
可以继续使用冻结方法文本或明确供给的方法材料；不能指望外层会话有技能就自动传入内层。

### 3. 原生精确读取也尚未覆盖全部既有能力

`material_tools.py` 的 read_model_resource 只允许 class-detail、entity-detail、property-list、
relation-type-list、table-mapping-detail、join-mapping-detail 六个 family；后端已经有的
operation-detail 不在允许清单中。故“可以创建 Operation”不能推出 v5 已完整接通相应的
精确治理展开。本次仅定位静态合同差异，没有新增 Operation 或验证该缺口的真实读回。
Context Query 仍可能返回相关资源，因此不能扩大成“Operation 完全不可读取”。

### 4. 运行结果与自查／验收没有补回缺口

当前 Demo 的 role 分布为 object 2、process 1、rule 4、data_mapping 7；没有 behavior、
business_role 或 interface_mapping 资源。rule 标签的四项是授权 Class 和三个关系定义，
不是已独立表达全部准入／回放／扣额规则的证明。某视角无资源本身不判失败，但该运行没有
留下充分的适用性／表达对应，不能宣称已完整分析。

原 Task 的历史语义记录只有 coverage，创建提案仅有四类对象／关系／数据映射；通用自查虽
要求完整来源和真实读回，却仍将其报为完成。原独立评价也明确禁止来源补模型缺项，但实际
漏掉了非空授权集合条件和余额单位冲突。详见此前粒度审查；这不是“验收根本不存在”，而是
其针对方法采用及分项实际表达的验证不足，真实内容检查也有漏判。

## 为什么会走到少对象和长说明

已观测到的供给和执行链如下：

1. 新入口用 v5 通用方法摘要替代旧包／Skill 的完整方法供给。
2. 复用旧语义合同时主要选择角色字段，动作／流程／规则关联／接口语义没有一同供给。
3. Class fields-only、关系定义及数据映射有较详细的执行说明和示例；行为、规则和流程的
   独立语义表达缺少对等指导。规则可放在 semantic_definition 的合法回退仍在。
4. Agent 实际选择在少量 Class 的 business_meaning 放入大段处理逻辑，没有完整多视角覆盖证据。
5. 泛化的“完整自查”和冻结问答评价没有可靠识别这些缺口，历史 PASS 被宿主过度用于证明完整性。

第 1、2、4、5 项有源码、冻结输入、原生记录与实际模型支持。第 3 项形成偏向的解释是有依据的
因果推断，不是已完成 A/B 的质量效果证明。自然语言承载规则本身合法；错误不是出现长文本，
而是未按业务区分与消费需要形成充分的身份／关系、已知条件丢失且未被检出。

`git blame` 显示 semantic_definition 单块抽取于 c9f7171 引入，允许计算规则使用语义定义的
说明在 55851dd 加入。它们定位变更历史，不证明变更者意图或单条文字的独立效果。
不把问题归因于未经证明的“为了省额度而主动降低质量”。

## 应纠正的责任面

先补 v5 的获准方法供给，再开展完整修模：

1. 在当前 v5 方法中明确承接对象、行为、规则、角色、流程及数据／接口映射的分析与整合职责，
   包括身份／粒度选择、适用范围、条件／效果、例外和共享引用。复用旧语义原则，按当前
   工作空间／直接应用入口表达，不带回已退役的旧执行要求。
2. 同步供给相应的既有动作、流程、规则和接口语义合同，不能只留下角色字符串；核对现有
   原生写入与精确读取是否覆盖选用的表达类型，例如复用后端已有的 Operation 详情能力。
3. 利用现有语义记录保留有依据的视角判断、命题到实际表达位置及剩余缺口，复核来源变化的
   语义使用者。程序不替 Agent 判业务、不强制节点数或七视角全部适用。
4. 同时检查冻结／原生输入确实获得方法，以及真实模型能否通过独立消费表达完整条件、
   行为与规则关联；机械测试或“章节字符串存在”都不能单独升级为语义采用 PASS。

旧 Task 已冻结 instructions。只修改当前方法文件不会自动改变旧 checkpoint 的输入，后续
运行必须显式核对实际方法版本／冻结输入，再决定安全接续或新任务，不暗改旧证据。

本次没有实现上述修复；已将默认方法迁移缺口记录到 R5.0-003。没有新建模授权消费、模型写入、
预算变更或前后端更改。原评价原件、当前唯一模型及历史检查点保持。

## 可审阅证据

[汇总 JSON](../delivery/evidence/2026-11-01-v5-multiview-method-adoption-audit/summary.json)
保存两个实际 run 的冻结指令哈希、合同键、原生 Skill 清单、当前模型 role 分布和限制。
原始运行目录只读保留，未把私有凭据或隐藏题正文复制到公开证据中。
本次使用精确源码／调用点及冻结／原生原件核对，没有宣称 GitNexus 对当前 v5 的完整覆盖，
也没有为只读诊断运行模型或修改测试程序。
