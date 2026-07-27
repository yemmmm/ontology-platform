# v2.1 本体建模流程重构需求

## 文档信息

- 文档状态：M1–M4 已实现并通过独立验收；长期迭代继续
- 基础版本：`docs/requirements/requirements-v1.0.md`
- 关联版本：`docs/requirements/requirements-v1.1.md`、`docs/requirements/requirements-v1.2.md`、
  `docs/requirements/requirements-v2.0.md`
- 总体目标：重构 Ontology 建模流程，使其以可解释、可验证、可复用和可演进的业务语义模型为中心
- 当前实施需求：R2.1-001 当前 M1–M4 已完成；后续阶段保持既定顺序
- 目标用户：需要将业务知识沉淀为可复用本体的建模人员、建模 Agent 工作流开发者和语义质量调优人员
- 更新日期：2026-07-27

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
| R2.1-001 | 本体建模流程重构 | P0 | 迭代中（M1–M4 已完成并通过独立验收，后续阶段待实施） | v1.0 语义平台边界、v1.1 建模工作流证据、R2.0-002 检查点 |

## R2.1-001 本体建模流程重构

当前状态：`迭代中（M1–M4 已完成并通过独立验收，后续阶段待实施）`

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

### 建模结构的迭代授权

R2.1-001 固定的是业务目标、平台与 Agent 责任边界、M1 场景和验收结果，不在需求阶段冻结唯一的
Class、Property、Relation、Shape、公理、规则、IRI 或版本表达方式。建模 Agent 可以自行选择初始
结构，并在同一 M1 过程中根据正例、反例、查询结果和语义问题多次调整，不需要为每个内部建模
选择逐项取得用户确认。

每轮调整仍需记录当前假设、模型变化、针对的问题、测试结果和保留限制，避免无法解释的任意改模。
只有以下变化需要重新取得用户确认：

- 改变 M1 的业务目标、合成 Fixture 或完成门槛；
- 改变 Ontology、Semantic Platform Core、建模 Agent 与消费 Agent 的责任边界；
- 引入新的平台能力、Dify 专属适配或超出当前最小范围的工作流机制；
- 把合成事实改写为官方来源事实，或改变 Evidence 与来源忠实度边界。

初始设计可以将 `Workflow` 与 `Workflow Version` 分开，也可以采用其他能够通过 Fixture 的结构；
具体选择属于可验证的建模假设，不因写入第一版设计而永久冻结。正式验收以当轮模型能否提供完整
影响上下文为准，不以是否保持某个预先指定的类图为准。

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
C：Content Quality Scoring Workflow
  Input: content:string
  Output: quality_score:number
  -> 作为 Workflow Tool 被 B 调用

B：Content Generation Workflow
  -> 把待评估内容绑定到 C.content
  -> 把 C.quality_score 绑定到本地 quality_score
  -> IF/ELSE 使用 quality_score 决定是否形成 approved_content:string
  -> 作为 Workflow Tool 被 A 调用

A：Campaign Publication Workflow
  -> 把 B.approved_content 绑定到本地 publish_content
  -> 后续发布准备节点或 Output 消费 publish_content
```

首个正例 Change Set 固定为：C 的新版本删除一个已被 B 使用的 Output，并发布为新的 Latest
Version；被删除的 Output 固定为 `quality_score:number`。基于已建模事实，现有通用查询应能取得
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

该三层内容处理场景是为 M1 设计的合成验收数据，不是 Dify 官方文档声称存在的产品内置应用或
标准业务流程。官方资料只用于支持 User Input Workflow 可发布为 Tool、调用方可以消费 Workflow
Tool 的 Output、Current Draft 与 Latest Version 的区别以及发布行为等通用 Dify 语义。需求、
模型、Evidence 和最终报告必须把“官方来源事实”“合成 Fixture 事实”和“Agent 推论”分开标注，
不得用官方文档的 provenance 为合成业务内容背书。

首轮查询断言至少覆盖：

1. 对已发布的删除型 Change Set，查询能取得 B 和 A 两个调用方候选及完整 `C -> B -> A` 依赖路径；
2. B 的调用位置、`quality_score` Binding、IF/ELSE 使用位置和 `approved_content` Output 可追踪；
3. A 的调用位置、`approved_content -> publish_content` Binding 和后续使用位置可追踪；
4. 相同删除只存在于 C 的 Current Draft 时，查询明确返回草稿状态，不把它混入当前 Latest Version
   的已发布变化；
5. 每一层结果均返回完整性或明确缺口，消费 Agent 能区分“确认没有路径”和“路径尚未建模”。

当前固定 Dify 快照已经包含 Start、Output、Iteration、Version Control、Orchestration Logic 和
Manage Apps 页面，但没有包含被 Output 页面引用的 `Dify Tools` 页面。M1 进入正式建模和验收前，
应创建新的不可变快照或场景资料包补入该官方页面；不得原地修改
`dify-foundations-2026-07-18-5396c1a`，也不得把本次在线查看结果直接当成可复现验收输入。

### 第一版最小实现约定

M1 第一版不编写独立的正式设计文档，也不以一份脱离模型的共享测试计划作为实施前置条件。
需求条目固定业务目标和边界；可审阅的候选本体、Shapes、Fixture、SPARQL 查询断言与逐轮记录共同
构成可演进的设计和轻量验收清单。只有当后续工作需要新增平台 API、存储、运行时、Dify 专属适配
或其他难以回退的架构能力时，才另行细化平台需求并编写正式设计。

第一版使用 repo-local、可提交、可离线复现的场景包，至少包含：

- 一个补齐 Workflow-as-Tool 官方语义来源的不可变场景资料包，记录固定提交、文件哈希和来源；
- 一版本体候选及其 Shapes，明确区分 Workflow、Workflow Version、Workflow Tool、Tool
  Invocation、Variable、Binding、Use 与 Change Set；
- 已发布 Output 删除正例、仅 Current Draft 删除反例，以及至少一个应被 Shapes 拒绝的无效
  Fixture；
- 可执行的 validation、受当前开发 reasoner 支持的 RDFS 推理和只读 SPARQL 查询断言；
- 一份逐轮记录，说明建模假设、模型变化、针对的问题、结果、限制和下一轮候选。

首版优先通过离线确定性测试固定模型质量，再使用现有通用平台路径做真实运行验收。允许使用
SPARQL property path 组合已建模 Invocation 关系取得传递调用方；这属于消费查询，不把
`Dependency Path` 强制物化为平台专属数据结构。真实平台验收只验证通用导入/应用、
validation、reasoning、Context Query 或 scoped SPARQL 能否保存和取回这些 RDF 事实，不要求
平台输出 Dify 业务结论。

### 第一版实现结果

第一版场景包位于 `docs/evaluation-scenarios/dify-workflow-impact-m1/`，包含不可变补充资料包、
候选本体、Shapes、四组隔离 Fixture、三条查询、十三项离线断言和追加式迭代/独立测试记录。
它已经证明：

- 已发布删除能够返回 B、A 两个调用方候选及完整 C 输入、C 输出、B Binding、IF/ELSE 生产、
  B Output、A Binding 和下游使用路径；
- 仅 Current Draft 的相同删除与 active Latest 路径分离；
- 无效调用结构被 SHACL 拒绝，显式缺口必须携带未知说明；
- 有限 RDFS 推理产生领域兼容的 `referencesVariable` 结论，标准 RDFS 闭包不混淆
  `VariableUse` 与 `Variable`；
- 真实受管工作区能够以 `validate=true` 写入候选并完成 validation、reasoning 和 scoped SPARQL；
  整个过程没有新增 Dify 专属平台代码，临时 Project/Ontology 已清理。

独立测试经历两轮失败并保留记录：第一轮发现输入 Binding 与内部生产链缺失，第二轮发现
RDFS superproperty 的 domain 冲突；修复后第三轮通过。当前运行时仍为
`SEMANTIC_PRODUCT_WRITE_MODE=legacy_only`，因此 Modeling Batch canonical writer 未能进入
本轮真实应用链。M1 已通过现有 generic governed semantic-edit 路径完成验收；是否启用 Modeling
Batch canonical writer 以及其对任意候选 RDF 的剩余表达边界，作为独立通用平台问题保留，不在
M1 中修改平台或做 Dify 定制。

### M2：受控建模流程演练

M2 不扩展新的 Dify 业务语义，也不要求自主建模 Agent 立即承担流程探索成本。其目标是由主 Agent
在受控条件下扮演建模者，使用未来自主建模 Agent 将使用的正式平台入口，完整重演一次 M1 建模
任务，先暴露建模流程、工具合同、错误反馈和应用链中的问题。

M2 固定使用 M1 的不可变资料包、合成业务事实、语义问题和行为验收作为输入与结果基准。现有 M1
本体可以作为调试和结果对照，但不得把已有 Turtle 通过直接 RDF 写入伪装为正式建模流程成功。
模型内部结构仍可调整，M2 不要求新候选与 M1 RDF 图同构。

M2 至少执行以下路径：

1. 创建全新的 Project、Ontology 和 Build Session，并登记本轮资料与 Evidence；
2. 通过平台正式建模入口形成候选操作，执行 Modeling Batch dry-run；
3. 根据平台返回的确定性校验、影响范围和错误信息修改候选，并保留每轮失败与修正记录；
4. 通过 Modeling Batch apply 应用最终候选；
5. 对应用结果执行 validation、reasoning，以及 Context Query 或 scoped SPARQL；
6. 使用 M1 的已发布删除、Current Draft、无效结构和显式缺口场景验证最终语义行为；
7. 形成一份追加式演练日志和一份只包含必要步骤、输入、工具及失败处理的最小操作清单。

M2 的成功路径不得使用 `POST /api/semantic/edits`、`datasets:load`、直接数据库写入、
`validate=false` 或其他旁路装载最终 RDF。允许对现有通用平台能力做只读探测和使用已支持的测试
配置，但不得为 Dify 增加专用 API、Schema、转换器、查询分支或解释逻辑。

M2 开始时必须先探测当前 canonical/product write mode。若
`SEMANTIC_PRODUCT_WRITE_MODE=legacy_only` 仍阻塞 Modeling Batch，则应记录最小复现并判断：

- 若只是现有通用能力的测试配置未启用，可以在隔离测试环境按已有合同启用后继续；
- 若 Modeling Batch 缺少承载必要通用本体表达的能力，应停止 M2，将缺口作为独立通用平台需求
  细化并取得用户确认；
- 不得再次通过 generic semantic edit 绕过阻塞后宣称 M2 完成。

M2 完成门槛：

- 从资料/Evidence 到 Modeling Batch dry-run、修正、apply 和应用后查询的正式路径完整通过；
- M1 的发布状态区分、C -> B -> A 上下文、无效结构拒绝和显式未知语义行为保持成立；
- 每次关键失败都能追踪到输入、Batch、平台反馈和修正结果；
- 最小操作清单不包含主 Agent 的隐藏本地状态或未记录步骤，能够直接交给 M3；
- 没有直接 RDF 成功旁路，也没有新增 Dify 专属平台能力。

### M2 实现结果

M2 场景包位于 `docs/evaluation-scenarios/dify-workflow-impact-m2/`。主 Agent 在用户允许的隔离
`rdf_primary` 后端中新建 Project、Ontology 和 Build Session，分别登记官方资料、合成 Fixture
和建模合同 Evidence，并只通过 Modeling Batch 完成 TBox、Shapes、published、draft 和
explicit-gap 候选的 dry-run 与 `apply_atomic`。常驻服务配置未修改，演练前后均保持
`legacy_only`。

首轮真实演练保留了一个跨 Batch 误用 `item_ref` 的失败：draft Batch 返回四个
`unresolved_item_ref` 和后续 Shape violation。修正为引用已应用资源 IRI 后，第二轮完整通过；
错误 Shape 与缺少 `invokesTool` 的 Invocation 均被 `shacl_violation` 拒绝且未 apply。应用后
validation 显式使用 Graph Set 的 `shapes` member 并 `conforms=true`，reasoning
`consistent=true` 且产生预期 subclass entailment，scoped SPARQL 返回恰好 B、A、完整
C -> B -> A 上下文、独立 draft 和显式未知项。

独立验收复核了两轮留存 Project、Evidence、Batch/Attempt、validation/reasoning 运行记录，
重放同 Shape 负例和全部 scoped 查询，并通过 M1 13 项、M2 5 项及 69 项聚焦后端测试。整个路径
未调用 semantic edit、`datasets:load`、直接数据库/RDF 写入或 `validate=false`，也未新增
Dify 专属平台能力。最小操作清单已满足 M3 交接条件；M2 的场景 Project 和运行证据继续保留，
作为 M3 的流程证据而非答案型建模输入。

### M3：自主建模 Agent 复现

M3 以 M2 已完整通过、正式建模路径稳定且最小操作清单可用为前置条件。其目标是在一个新的空
Project/Ontology 中，由自主建模 Agent 根据同一资料、合成业务事实、语义问题和平台反馈独立形成
并应用本体候选，验证建模质量不依赖主 Agent 逐步代做。

自主建模 Agent 可以使用 M2 形成的通用操作清单、`m3-reusable-lessons.md` 经验交接和平台工具
说明，但不得读取或复制 M1/M2 的最终 `ontology.ttl`、`shapes.ttl`、`run_rehearsal.py`、最终
Batch payload、runtime record 或答案型查询结果。主 Agent 可以处理环境故障、权限或明确的平台
阻塞，但不得替 Agent 选择 Class、Property、Shape、公理、关系结构或修改最终候选。Agent 可以
根据 dry-run、validation、reasoning 和查询失败自主迭代，无需与 M1 使用相同的 IRI 或内部结构。

M3 至少覆盖：

1. 自主 Agent 从允许的输入建立术语边界、候选 TBox、Shapes 和必要实例事实；
2. 自主执行 Modeling Batch dry-run，根据确定性反馈完成至少一次可记录的接受或修正决策，并
   apply 最终候选；
3. 应用后的模型通过与 M1 相同的语义行为验收，而不是 RDF 文本、三元组数量或类图同构比较；
4. 独立消费 Agent 只使用平台返回的事实、来源、版本、依赖路径、Binding、变量使用和未知项，
   给出调用方候选与影响解释；平台与本体不输出高、中、低影响等级；
5. 记录自主运行中的重试、人工介入、未解决问题和下一轮模型优化建议。

M3 完成门槛：

- 自主建模 Agent 在没有答案型本体产物的情况下完成正式 dry-run/apply 闭环；
- 已发布删除能够取回 B、A 及完整 C -> B -> A 上下文，Current Draft 不混入当前发布链；
- 无效结构被拒绝，显式缺口不被消费 Agent 误判为“确认没有影响”；
- 消费 Agent 的结论能够逐项追溯到平台事实，并明确区分来源事实、合成事实、推论和自身判断；
- 不依赖主 Agent 的隐藏语义决策，不使用直接 RDF 写入旁路，不引入 Dify 专属平台能力。

M3 已于 2026-07-26 完成并通过独立验收。自主建模 Agent 在隔离的新
Project/Ontology/Build Session 中形成并应用自己的模型，记录 Checkpoint 并完成 Session；
独立测试以正式 Modeling Batch 构造 baseline、正交 decoy 及九个传播角色各自的 remove 和
unrelated-sentinel 变体，20 个隔离环境、9/9 角色均通过。第二个全新只读消费 Agent 只依据
平台事实给出调用链和影响解释，明确区分官方来源、合成 Fixture、推论与自身判断，保留未知项且
不输出风险等级。运行隔离、请求/响应消费回执和完整回归证据见本需求的追加式交付记录与共享测试
计划。

M2、M3 均不要求单独编写正式设计文档。其当前设计和验收合同由本需求、M1 场景包、各阶段追加式
日志与可执行语义测试共同承载。只有探测出必须新增平台 API、存储、运行时或其他难以回退的通用
能力时，才暂停当前阶段并为该平台缺口单独细化需求和设计。

### M4：建模 Agent 主动业务语义澄清验证

M4 在扩大业务范围前，先验证自主建模 Agent 能否发现固定资料和初始业务输入不足以决定的关键
业务语义，并主动面向用户逐轮澄清。M3 已证明 Agent 能够根据静态输入自主完成建模，但没有验证
Agent 能否区分“可由资料确定”“必须询问用户”和“当前只能保留未知”三类语义，也没有验证用户
回答能否稳定转化为可追踪的模型变化。

M4 复用 M3 已通过的正式建模与平台验证路径，不扩展成模块业务，不把 Coverage、Work Unit、
独立 review、Shared Modeling Directory 或完整产品化访谈机制设为前置条件。固定场景应在不泄露
答案型模型的前提下加入若干会实质影响术语边界、身份、生命周期、关系约束或查询结果的业务歧义。
用户角色持有与资料一致的隐藏业务答案合同；建模 Agent 只能通过可见资料和逐轮问答获得这些
业务决定。

M4 至少覆盖：

1. 建模 Agent 主动识别会影响模型或验收结果的关键歧义，并一次提出一个可由用户回答的问题；
2. 每个问题说明其影响的业务决定或建模边界，但不通过问题文本泄露隐藏答案或预设模型结构；
3. 用户回答后，Agent 记录“问题与回答 -> 假设变化 -> 模型变化 -> 验证结果”的可复核链路；
4. 对资料已经明确的内容不重复要求用户决定；对用户无法确认的内容保留显式未知，不自行补全；
5. 澄清完成后，Agent 仍只通过正式 Modeling Batch dry-run/apply、validation、reasoning 和
   Context Query 或 SPARQL 完成建模与验收。

M4 完成门槛：

- 固定场景中所有会改变目标语义行为的预置关键歧义均被正确澄清或明确保留为未知；
- 独立测试证明用户回答确实改变相应模型行为，而不是只被记录在对话或说明文档中；
- 用户拒答或回答未知时，最终模型和消费结论不把未知冒充为已确认事实或“确认不存在”；
- 建模 Agent 没有读取隐藏答案合同、M1–M3 答案型本体产物或由主 Agent 代做语义选择；
- M3 已通过的来源忠实度、正式应用、无效结构拒绝、推理、查询和只读消费边界没有回归。

M4 的固定歧义、用户回答合同、Agent 提问接口、测试隔离方式和独立验收用例在 M4 开始实施时
细化；本阶段不预先固定问题的自然语言措辞，也不要求不同模型生成完全相同的问题文本。

### M5：Pi Agent 交互式建模合同复现

M5 以 M4 通过并冻结交互式业务语义澄清合同为前置条件，在全新的隔离
Project/Ontology/Build Session 中使用真实 Pi Agent 重放同一场景。M5 验证建模方法、用户
澄清链路和正式平台闭环能否迁移到 Pi Runtime，不重新探索 M4 的业务答案，也不以本阶段恢复
R2.0-002 已暂停的完整多角色编排、常驻服务、崩溃恢复、管理 UI 或生产化 Runtime 集成为目标。

Pi Agent 可以获得 M4 冻结后的通用任务合同、平台工具说明、提问/暂停/回答/继续协议和非答案型
经验，但不得读取 M4 的最终本体、Batch payload、答案型查询结果、隐藏答案合同或运行记录。测试
使用同一份由用户角色持有的隐藏答案合同回答 Pi Agent 自主提出的问题；验收比较业务语义行为和
问题必要性，不比较问题措辞、IRI、RDF 文本、三元组数量或类图同构。

M5 完成门槛：

- 固定并记录 Pi 版本、模型名称、模型参数、角色 Prompt/Skill 版本和平台工具合同；
- Pi Agent 能够完成必要问题的提出、暂停、逐轮回答和继续，并把回答落实为可追踪模型变化；
- 在全新隔离环境中通过与 M4 相同的正式应用、validation、reasoning、查询和未知项验收；
- 独立测试证明 Pi 运行没有读取 M4 答案产物、接受主 Agent 隐藏语义代做或绕过 Modeling Batch；
- Pi Runtime 差异若导致失败，应形成有证据的最小问题清单；不得通过放宽 M4 语义质量门槛宣称
  复现成功。

M5 通过之前不启动 M6。M5 通过只证明当前交互式建模合同可由 Pi Agent 复现，不代表
R2.0-002 的原完整验收链恢复或完成。

### M6：从业务切片扩展到模块业务

M6 以 M4、M5 均通过为前置条件，把已验证的单一业务语义切片扩展为边界清晰的模块业务，重点
验证跨切片术语一致性、概念和身份复用、模块内及模块间关系、约束组合、推理、查询，以及后续
演进时的影响范围。M6 的具体业务模块、资料范围、复用和演进合同、能力问题、规模上限与完成
门槛尚未细化；这些内容必须在 M5 结束后根据 M4/M5 的真实结果形成独立阶段合同，不能在当前
路线确认中预设。

M6 不因扩大业务范围自动引入 Coverage、Work Unit、独立 review 或 Shared Modeling Directory。
只有 M6 的规模或实际失败证明某项机制直接保护建模质量、来源忠实度或检索完整性时，才把该机制
纳入当轮设计和验收。

### 待后续细化

以下内容尚未形成合同，不在本次记录中提前决定：

- M4 的固定歧义、隐藏答案合同、逐轮交互协议和独立验收场景；
- M5 的固定 Pi/模型版本、Prompt/Skill 装配方式和 Runtime 隔离方案；
- M6 的业务模块选择、资料范围、模块复用与演进合同；
- 基于现有通用查询能力的查询组合、字段选择、分页和完整性验收方式；
- M4–M6 是否因实际失败引入 Brief、Coverage、Work Unit、独立 review 或 Shared Modeling
  Directory；
- 与知识实例、知识图谱写入及后续消费检索的关系；
- M6 之后的长期质量指标、迁移方式和旧流程退役条件。

R2.1-001 的 M1 在第一版本体候选、Fixture 和查询断言形成后即可进入逐轮验证，不设置独立正式
设计评审或共享测试计划文档门槛。第一版结构是可验证假设，不是最终方案；每轮必须保留建模假设
和调整记录，也不得以首轮通过宣称长期建模流程或最终本体结构已经确定。M2 受控建模流程演练已
完成；M3 自主建模 Agent 复现和 M4 主动语义澄清均已通过独立验收。当前 M1–M4 切片关闭；
下一阶段仍按既定顺序实施 M5，M5 通过后才细化并实施 M6。每个阶段开始前仍需冻结该阶段的场景、输入、
角色边界和验收合同，不以本次路线排期代替阶段级设计与独立测试。
