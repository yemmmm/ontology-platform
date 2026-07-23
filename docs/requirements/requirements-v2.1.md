# v2.1 本体建模流程重构需求

## 文档信息

- 文档状态：M1 路线、业务切片、建模边界与首个删除型 Fixture 已确认，详细语义合同待细化
- 基础版本：`docs/requirements/requirements-v1.0.md`
- 关联版本：`docs/requirements/requirements-v1.1.md`、`docs/requirements/requirements-v1.2.md`、
  `docs/requirements/requirements-v2.0.md`
- 总体目标：重构 Ontology 建模流程，使其以可解释、可验证、可复用和可演进的业务语义模型为中心
- 当前实施需求：无；先细化 R2.1-001
- 目标用户：需要将业务知识沉淀为可复用本体的建模人员、建模 Agent 工作流开发者和语义质量调优人员
- 更新日期：2026-07-23

## 背景

现有建模流程主要从业务文档中识别概念、实体、属性和关系，再以 Evidence、Coverage、CQ、
语义检索和 provenance 验证写入结果。这套流程能够支持有来源、可治理的知识图谱构建，但在实际
运行中逐渐把“Ontology 建模”收敛为“从文档抽取并写入知识图谱”。

平台底层已经具备类、属性、关系类型、Shape、规则、语义校验以及部分推理接口等本体技术基础，
当前流程却没有把业务语义定义、概念边界、约束、公理、推理预期、复用和演进作为首要建模目标
与质量对象。R2.0-002 的真实运行还表明，即使 Runtime、角色编排和平台写入链路逐步打通，如果
建模目标和产物合同仍以知识抽取与图谱写入为中心，完整跑通旧流程也不能证明平台已经形成有
区别度的本体建模能力。

因此需要重构 Ontology 建模流程，并重新确定 Agent、平台确定性能力、建模产物、质量门禁与实际
应用之间的责任边界。

## 与既有版本的关系

1. v2.1 继承 v1.0 对平台确定性验证、Evidence、Modeling Batch、持久化、查询和治理的责任边界，
   不把 Agent 判断或隐藏推理写成平台事实。
2. v2.1 以 v1.1 的业务访谈、Coverage、Work Unit、独立评审和共享建模目录作为现有工作流证据，
   但不预设这些机制必须原样保留。
3. R2.0-002 已暂停在 Pi Runtime 与真实运行检查点；Pi Runtime、真实运行证据和未完成链路均可
   作为 R2.1-001 的输入，但不构成对最终流程的约束。
4. 在 R2.1-001 完成细化和真实验收前，不退役现有 Claude 建模路径，也不恢复 R2.0-002 的旧验收链。
5. 本版本不把“双轨建模”作为需求定义或既定方案；是否以及如何区分不同建模活动，留待需求细化。
6. Dify 或其他参考业务资料只能用于验证通用建模能力，平台不得引入领域专属 API、Schema 或解释逻辑。

## v2.1 总需求

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.1-001 | 本体建模流程重构 | P0 | 细化中（M1 核心合同与 Fixture 已确认） | v1.0 语义平台边界、v1.1 建模工作流证据、R2.0-002 检查点 |

## R2.1-001 本体建模流程重构

当前状态：`细化中（M1 路线、Workflow-as-Tool 切片、建模边界与删除型 Fixture 已确认）`

优先级：`P0`

### 当前记录范围

本需求当前只确认以下方向：

- 以本体建模质量为核心，避免继续把文档知识图谱化等同于本体建模完成；
- 建模流程应面向业务语义定义、概念边界、约束、公理、推理预期、复用和演进等本体问题；
- 保留 R2.0-002 已验证的 Pi Runtime、真实运行证据和问题记录，后续按新流程需要决定复用范围；
- 在新流程完成细化和真实验收前，不退役现有 Claude 建模路径；
- 不以“双轨建模”命名或预设最终方案。

### 已确认的长期迭代路线

R2.1-001 是一个较长的本体建模效果优化过程，但不把旧流程的全部机制放进每轮实验的完成门槛。
当前采用“最小本体、语义测试、逐轮扩展”的路线：

```text
选择一个有界业务语义切片
  -> 明确业务语义问题、术语定义、概念边界和非目标
  -> 构建以 TBox、约束和推理预期为主的本体候选
  -> 使用少量正例与反例验证约束和推理
  -> 通过平台 Modeling Batch dry-run/apply 写入最终候选
  -> 通过 validation、inference、Context Query 或 SPARQL 验收
  -> 根据真实失败决定下一轮增加哪一种建模或协作机制
```

每轮只引入能够解释实际质量问题的一项主要变化，并记录假设、固定场景、模型变化、测试结果、
仍未解决的问题和下一轮决定。Brief、Coverage、Work Unit、独立评审、Shared Modeling Directory、
Pi Runtime、完整执行事件和其他既有能力都可以复用，但不能仅因已经存在就自动成为每轮前置门槛：

- 术语或业务边界持续歧义时，再加强结构化访谈和术语合同；
- 规模导致上下文过载时，再引入 Work Unit；
- 重要语义静默遗漏时，再引入 Coverage；
- Agent 自审不能发现重复错误时，再引入独立评审；
- 跨 Session 无法可靠继续时，再引入 Shared Modeling Directory；
- 手工流程已经稳定且需要重复执行时，再推进 Pi Runtime 集成。

### 当前最小范围：M1 最小本体纵向切片

M1 的目标不是批量抽取业务实体和事实，而是证明一个业务语义模型能够定义概念含义、拒绝无效
结构并产生可验证推论。它是当前范围上限，不是以元素数量代替质量的量化指标：

- 只选择一个有界业务切片和少量权威资料；
- 以三个左右的语义问题驱动模型，至少覆盖概念区分、无效状态或结构、预期推论；
- 首轮候选原则上控制在约五至八个核心 Class、三至五个 Property/Relation；
- 至少提供一个可执行语义约束和一个当前平台能够执行的推理预期；
- 使用少量正例和反例作为测试 Fixture，不要求导入真实业务实例或构建完整知识图谱；
- 探索期产物优先使用可直接审阅的 repo-local 文件；只在最终候选边界复用 Evidence、
  Modeling Batch dry-run/apply、确定性校验和应用后语义验证。

M1 至少证明：

1. 核心术语具有可区分的定义、身份或边界，不能只依靠名称相似度；
2. 一个违反业务语义的反例被约束稳定拒绝；
3. 一个未直接声明的结论能够由模型语义稳定推出；
4. 目标语义问题能够通过 validation、inference、Context Query 或 SPARQL 得到可解释结果；
5. 修改相关约束或公理后，验证或推理结果按预期变化。

### M1 业务切片：Workflow-as-Tool 变更影响范围

Dify 资料中的“子工作流”至少有两种不同含义，M1 不应继续混用：

- `Iteration 内部流程`：Iteration 节点在同一个 Workflow 内部为每个数组元素执行的一组步骤；
- `Workflow-as-Tool 调用依赖`：一个以 User Input 开始的独立 Workflow 发布为 Tool，另一个
  Workflow 通过 Tool 调用并消费它的输入输出合同。

用户提出的“修改子工作流并推导受影响主工作流”对应第二种含义。M1 建议使用
`被调用工作流（callee Workflow）`、`调用方工作流（caller Workflow）` 和
`Workflow Tool`，不使用容易把内部流程、复制产物和独立应用混在一起的“主/子工作流”作为
正式模型术语。

当前资料支持以下初步语义：

- 只有以 User Input 开始的 Workflow 能够作为 Tool 被其他 Dify 应用复用；
- 被调用 Workflow 的 Input 定义构成 Tool 输入合同，Output 节点定义 Tool 返回合同，调用方
  Workflow 可以引用这些输出变量；
- Current Draft 是尚未上线的工作版本；发布后草稿成为新的 Latest Version；
- 复制 Workflow、跨 Workflow 复制节点或 Iteration 内部流程不自动形成对原 Workflow 的运行时
  调用依赖，必须作为影响传播的反例；
- 因此，未发布草稿变更、已发布实现变更、输入输出合同变更和被调用 Workflow 删除不能被视为
  同一种影响。

候选本体可以围绕 `Workflow`、`Workflow Version`、`Workflow Tool`、`Tool Invocation`、
`Input/Output Contract`、`Variable Binding`、`Change Set` 和 `Dependency Path` 建立概念边界。
首轮确定性能力目标为：

1. 根据 Tool Invocation 依赖推导一个变更可能影响的直接和传递调用方 Workflow；
2. 区分仅存在于 Current Draft 的变更与已经进入 Latest Version 的变更；
3. 当输入或输出被删除、重命名、改变类型或必填性，并且调用方存在对应 Binding 时，返回对应
   调用位置、Binding、上下游变量使用和依赖路径；
4. 对 Prompt、模型选择、内部节点逻辑或输入输出合同等变化，返回消费 Agent 判断影响所需的所有
   已知事实、来源、版本、调用路径、绑定关系和明确未知项，不由本体或平台给出最终影响等级。

这里的“评估影响范围”不是要求 Ontology 或 Semantic Platform Core 代替消费 Agent 得出高、中、
低风险结论。三者职责明确区分为：

- Ontology 定义 Workflow、Version、Tool、Invocation、Contract、Binding、Change 和 Dependency
  等概念、关系、约束，以及分析某类变化时需要关注哪些信息；
- Semantic Platform Core 保存已提交的本体与实例事实，执行确定性约束和依赖推导，并通过现有
  Context Query、SPARQL、validation、inference 和 provenance 能力返回完整可用上下文；
- 消费 Agent 读取平台上下文和实际 Workflow/DSL 变化，结合业务用途、调用方式以及可选运行证据，
  判断哪些调用方真正受影响、影响表现和影响大小，并生成最终解释。

内部行为变化的前后测试指标、真实输出对比和业务效果属于消费 Agent 可以按需使用的外部观察
证据，不是 Ontology 必须生成的内容，也不是平台在 M1 中必须执行或比较的能力。若这些观察已经
由外部 Agent 提交为明确事实，Ontology 可以描述其含义，平台可以连同来源返回；缺失时只需明确
报告未知，不能阻断依赖范围查询，也不能由平台补造结论。

建模 Agent 负责读取业务资料并形成上述本体；外部 Agent 可以把实际 Workflow、Version、Binding
和 Change Set 作为明确事实提交。Semantic Platform Core 不解析 Dify DSL、不执行测试、不比较
指标，也不作领域影响判断。

Dify 的 Workflow、Tool、Version、Binding 和 Change 仍是参考本体数据，不得成为平台专属 API、
Schema、排序规则或解释分支。

### 已确认的最小影响上下文建模目标

本体模型不能只记录“某个 Workflow 调用了另一个 Workflow”。它必须表达足够的 Version、
Invocation、Binding、Contract 和变量使用事实，使消费 Agent 能够通过平台现有通用查询能力，沿
实际数据使用路径取得以下上下文并自行判断影响：

- 被修改 Workflow、变更前后 Version、Current Draft/Latest Version 状态以及已知 Change Set；
- 从被修改 Workflow 到当前调用方的完整 Tool Invocation / Dependency Path，并区分直接与传递调用；
- 每一层调用所在的 Workflow Version、Tool 调用节点或稳定调用位置；
- 调用方传入被调用 Workflow Input 的 Variable Binding，以及绑定值在调用方内部的上游来源；
- 被调用 Workflow Output 到调用方变量的 Binding，以及该变量在调用方内部被哪些后续节点、条件、
  Output 或下一层 Tool Invocation 继续使用；
- 相关 Input/Output Contract、变量名称、类型、必填性、来源、Evidence、版本和 provenance；
- 每一层依赖、Binding 和变量使用路径的完整性状态，以及未建模、不可用或无法确认的明确未知项。

对于传递调用，本体中建模的变量使用路径不能在第一层调用方停止。例如 C 被 B 作为 Tool 调用，
而 B 的输出又被 A 调用或消费时，现有通用查询应能读取
`C -> B 调用位置 -> B 内部变量使用/输出 -> A 调用位置` 的可追踪上下文。平台只陈述已建模
拓扑、合同与事实，不把“位于路径上”直接解释为“业务上一定受影响”；最终筛选和解释仍由消费
Agent 完成。

若某个 Workflow 的节点、Binding 或变量使用尚未建模，本体实例必须显式记录相应完整性状态或
缺口，使现有通用查询能够连同事实一起返回。消费 Agent 不能因为路径查询没有返回数据就宣称
不存在后续影响。M1 的“影响范围可分析”要求的是上下文与缺口均显式，而不是平台保证业务资料
已经绝对完整。

上述内容是对本体结构和实例事实完整性的要求，不是新增平台产品能力的清单。M1 必须通过优化
Ontology 中的通用概念、关系、约束和实例建模，复用现有 Context Query、SPARQL、validation、
inference 与 provenance 获得结果；不得为 Dify 新增专属 REST/MCP 接口、响应字段、Read Model、
查询分支、排序规则、DSL 解析器或影响分析器。若现有通用能力确实无法读取一个已正确建模的必要
事实，必须先以独立证据说明通用能力缺口，再单独细化平台需求，不能在 M1 中静默定制适配。

### 已确认的首个 Fixture

M1 使用一个三层 Workflow-as-Tool 调用链验证本体能否提供完整影响上下文：

```text
C（被调用 Workflow）
  -> 作为 Workflow Tool 被 B 调用
  -> C 的一个 Output 绑定到 B 的变量并被后续条件或 Output 使用
  -> B 又作为 Workflow Tool 被 A 调用
  -> A 消费 B 对应的输出
```

首个正例 Change Set 固定为：C 的新版本删除一个已被 B 使用的 Output，并发布为新的 Latest
Version。基于已建模事实，现有通用查询应能取得
`C -> B 调用位置 -> B Binding -> B 内部使用/Output -> A 调用位置 -> A Binding/使用位置`
的完整路径、版本、合同、来源和完整性信息。平台不输出“A/B 一定受影响”或影响等级，消费 Agent
根据这些事实形成最终分析。

Output 重命名不进入首个正例。它保留为后续扩展案例，因为判断“新名称是否仍代表原变量”需要
额外的语义身份或映射事实；在这些事实不存在时，重命名只能被表示为删除旧 Output 和新增新
Output，不能由平台猜测二者等价。

反例 Change Set：C 发生相同变化，但只存在于 Current Draft，Latest Version 尚未改变。查询仍可
返回草稿变化及其潜在调用上下文，但必须清楚区分它尚未进入当前发布调用链，不能把它与已经发布
的变化混为同一状态。

Fixture 中的 C、B、A、节点、变量、Version、Change Set、Binding 和使用路径都作为参考本体的
实例数据由外部 Agent 提交；平台不生成 Dify Fixture，也不通过代码识别其业务含义。

当前固定 Dify 快照已经包含 Start、Output、Iteration、Version Control、Orchestration Logic 和
Manage Apps 页面，但没有包含被 Output 页面引用的 `Dify Tools` 页面。M1 进入正式建模和验收前，
应创建新的不可变快照或场景资料包补入该官方页面；不得原地修改
`dify-foundations-2026-07-18-5396c1a`，也不得把本次在线查看结果直接当成可复现验收输入。

### 待后续细化

以下内容尚未形成合同，不在本次记录中提前决定：

- 本体建模的目标用户、入口、阶段划分和人机协作方式；
- 业务资料、现有本体、术语标准和用户意图如何成为建模输入；
- M1 Fixture 的具体 Workflow/节点/变量名称、删除型 Change Set 字段和查询断言；
- M1 本体候选的最终 Class、Property、Relation、约束、公理和推理规则；
- 后续切片的模块复用和演进合同；
- 基于现有通用查询能力的查询组合、字段选择、分页和完整性验收方式；
- 现有 Brief、CQ、Coverage、Work Unit、review、Modeling Batch 和 Shared Modeling Directory
  的保留、调整或替换范围；
- 与知识实例、知识图谱写入及后续消费检索的关系；
- 真实场景、质量指标、完成门槛、迁移方式和旧流程退役条件。

R2.1-001 的 M1 在完成详细语义合同、需求细化、设计评审和共享测试计划前不得进入实现，也不得
以当前路线和候选场景宣称最终建模方案已经确定。
