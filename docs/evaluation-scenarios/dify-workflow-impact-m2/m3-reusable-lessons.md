# 从 M2 到 M3：自主建模可复用经验

## 文档目的

本文把 R2.1-001 M2 受控建模演练中经过真实运行和独立验收的经验，转换为 M3 自主建模 Agent
可以使用的通用工作方法。

M3 要验证的是 Agent 能否根据原始资料、合成业务事实、语义问题和平台反馈独立完成建模，而不是
能否复现 M2 的答案。因此本文只沉淀流程、质量门禁、平台合同和失败处理，不提供 M1/M2 的最终
本体结构或答案。

## 使用边界

### M3 可以使用

- 固定的原始资料、合成业务事实、术语边界和 Competency Questions；
- 本文记录的通用建模经验；
- `minimal-checklist.md` 中的正式平台操作顺序；
- Project、Ontology、Build Session、Evidence、Modeling Batch、Graph Set、validation、
  reasoning 和 scoped query 的通用接口说明；
- 当前 M3 运行自己产生的 dry-run finding、运行状态和查询结果。

### M3 不得读取或复制

- M1/M2 的最终 `ontology.ttl`、`shapes.ttl`；
- M2 的 `run_rehearsal.py`、最终 Modeling Batch payload 或由其展开的命令清单；
- M1/M2 的答案型 SPARQL、预期结果值或最终模型资源名称；
- M2 的 runtime record、成功 Project 内容、资源 IRI、Batch/Attempt ID；
- M2 的 `README.md`、`rehearsal-log.md` 和独立验收明细；这些材料只供运行负责人和独立测试方
  追踪 M2，不作为自主建模 Agent 输入；
- 主 Agent 对 Class、Property、Shape、公理、关系结构或最终候选的隐藏选择。

这条边界很重要：平台操作经验可以复用，建模答案不能复用。

## M2 得到的核心经验

### 1. 先验证写入模式，再开始建模

M2 证明，健康检查通过不等于 Modeling Batch 的 canonical writer 已经可用。建模前必须分别探测：

- 常驻服务当前模式；
- M3 隔离实例是否为预期的 canonical store、product write mode 和 read mode；
- 当前身份是否能创建工作区、读取建模上下文并提交 dry-run。

M3 行动：

1. 使用全新的 Project、Ontology 和 Build Session；
2. 在产生候选前记录模式探针；
3. 模式不符时停止，把问题归类为环境阻塞，不能改走 semantic edit 或直接 RDF 写入。

### 2. 来源 Evidence 与建模判断必须使用不同渠道

M2 初期曾把官方资料、合成 Fixture 和 Agent 的建模理由混在一起。这样会让消费方无法区分
“来源事实”“测试设定”和“建模判断”，也不符合 R-002 对 Evidence 必须保存直接原文、不得保存
Agent 推断的合同。

M3 只登记两类 Evidence Reference：

- `official source`：权威资料实际表达的内容；
- `synthetic fixture`：为了验证模型而人为构造的业务事实；

Agent 的概念边界、约束选择、假设和理由必须记录在 Modeling Item `rationale`、Build
Checkpoint 和追加式执行日志中，不能创建 `modeling decision` Evidence。任何推论或 Agent 判断
都不能伪装成来源事实。每个 Modeling Batch Item 应引用与其声明性质一致的官方或合成 Evidence，
没有直接来源支持的建模结构可以保留明确的 `rationale` 和“无 Evidence”状态。

### 3. 候选按依赖顺序分批，不能把 `item_ref` 当作全局 ID

M2 的真实失败表明：`item_ref` 只在当前 Modeling Batch 内有效。前一 Batch 已创建并应用的资源，
在后续 Batch 中必须使用平台返回的稳定资源 IRI，不能继续使用原来的 `item_ref`。

M3 建议采用以下依赖顺序，但具体本体结构由 Agent 决定：

1. 基础 TBox 和必要 Property；
2. Shapes 与约束；
3. 主要正例 Fixture；
4. 草稿、显式未知等边界 Fixture；
5. 只用于拒绝验证的负例。

每一批开始前重新读取 modeling context。批内新资源可以用 `item_ref`；跨批资源只能使用已应用
结果返回的稳定 IRI。不要由名称猜测 IRI。

### 4. dry-run 是建模反馈回路，不是 apply 的形式前置

M2 最有价值的不是“一次通过”，而是失败能够被保留、解释和修正。M3 对每个候选都应执行：

```text
形成假设
  -> 提交新的 immutable dry-run
  -> 按 finding 定位 Item、字段、路径或语义约束
  -> 记录接受、修正或停止决定
  -> 使用新的 idempotency key 提交修正版
  -> dry-run validated 后才 apply_atomic
```

不得覆盖失败 Attempt，也不得在失败后放宽为 `validate=false`。修正轮必须显式关联被修正的前一轮，
使“输入 -> Batch -> finding -> 决策 -> 新 Batch”可追踪。

### 5. `conforms=true` 之前要先证明正确的 Shapes 被激活

M2 发现默认 Graph Set 的角色名是 `shapes`，而某些默认解析路径查找的是 `shape`。如果不显式传入
正确的 Shape 图，空 Shape 集也可能产生没有意义的 `conforms=true`。

M3 必须：

1. 读取当前 Graph Set；
2. 找到唯一角色为 `shapes` 的 member；
3. 将该 graph IRI 显式传给 managed validation；
4. 使用一个已知违反当前候选约束的负例做 dry-run；
5. 只有“正式数据 conforms + 已知负例被同一 Shapes 拒绝”同时成立时，才认为约束生效。

M3 不需要 ORM 或数据库检查。若公开平台结果不足以证明实际使用的 Shape 图，应作为通用可观测性
缺口报告，不能增加私有数据库步骤作为自主 Agent 的正式依赖。

### 6. apply 成功不等于建模成功

M2 建立了四层相互独立的完成门禁：

| 门禁 | 证明什么 | 不能替代什么 |
| --- | --- | --- |
| Modeling Batch dry-run/apply | 候选可以被正式编译和原子应用 | 不能证明业务语义正确 |
| Validation + 负例 | 正例满足约束，错误结构能被拒绝 | 不能证明预期推论成立 |
| Reasoning | 声明的公理产生预期类型或关系推论 | 不能证明消费查询上下文完整 |
| Competency Query | 模型能够回答业务语义问题并暴露未知项 | 不能证明来源和判断边界正确 |

M3 必须逐层保留证据。任何一层失败都应回到模型或 Fixture 修正，不能用后续层的成功覆盖前一层。

### 7. 以语义行为验收，不追求与 M1/M2 图同构

M2 使用与 M1 不同的结构化 Modeling Command 和平台分配 IRI，仍然通过了相同的行为验收。这说明
M3 的目标应是：

- 概念边界可解释；
- 无效结构稳定被拒绝；
- 预期推论可复现；
- Competency Questions 所需的完整上下文可取回；
- draft/published、known/unknown 等业务状态不会被混淆；
- 每个结果可追溯到来源、合成事实、推论或 Agent 判断。

类名、IRI、三元组数量、Shape 写法或内部图结构与 M2 不同，不应单独判定失败。

### 8. 查询断言要证明完整路径，而不只是“有结果”

M2 预审发现，过宽的 property path 和缺少关键连接条件的查询可能返回看似正确的行，却没有证明
完整业务上下文。M3 构造验收查询时，应明确：

- 起点、终点和每个必要中间角色；
- 调用、Binding、变量产生和使用等关键连接；
- 版本或发布状态过滤；
- 预期唯一性、允许的多值和结果完整性；
- 未知信息如何显式返回。

查询返回非空不是完成条件。必须证明返回结果包含回答 Competency Question 所需的全部事实。

### 9. “不知道”必须建模为事实，不能被空结果代替

M2 证明，缺少细节和确认没有影响不是同一件事。M3 遇到资料缺口时，应把未知项、缺口类型和说明
作为显式模型事实，并让 Shapes 要求必要的未知说明。

消费 Agent 只能根据这些事实说明“当前信息不足”，不能把空路径、空字段或未建模内容解释为
“确认不存在影响”。

### 10. 运行记录要支持失败后继续，但不能保存秘密

M2 首轮失败发生在部分 Batch 已应用之后。如果只在最终成功时保存记录，就会失去已创建工作区和
失败 Attempt 的定位信息。

M3 每完成一个有外部状态的阶段就应更新安全运行记录，至少包含：

- run tag、当前阶段和修正关系；
- Project、Ontology、Build Session；
- Evidence、Batch、Attempt、validation、reasoning run ID；
- 状态、finding code/path 摘要；
- Graph Set member、source signature；
- 查询名称、结果数量和断言状态；
- 人工介入类型及原因。

不得记录 API key、lease token、cookie、Authorization header、完整秘密配置或未脱敏原始响应。

### 11. 环境协助与语义决策必须分开

M3 的主 Agent 可以：

- 启停隔离服务；
- 提供凭据和处理明确的权限、网络、进程故障；
- 解释公开工具合同；
- 在平台缺少通用能力时决定是否暂停并细化新需求；
- 在运行结束后组织独立测试和清理。

主 Agent 不可以：

- 替自主建模 Agent 选择 Class、Property、Shape、公理或关系结构；
- 修改 Agent 的最终候选或给出答案型查询结果；
- 根据 M1/M2 最终模型提示“正确答案”；
- 把语义失败重新归类为环境问题后绕过。

所有人工介入都应记录为 `environment`、`permission`、`tool-contract` 或 `semantic-decision`。
出现 `semantic-decision` 介入时，本轮不能证明完全自主，应修正流程后重新运行。

## M3 推荐的最小执行循环

```text
读取允许输入与非目标
  -> 建立术语边界和建模假设
  -> 创建新工作区并登记官方/合成 Evidence，另记 modeling rationale
  -> 形成第一批候选
  -> immutable dry-run
  -> 根据 finding 自主修正或说明接受理由
  -> validated 后 apply_atomic
  -> 显式 Shapes validation + 已知负例
  -> reasoning
  -> Competency Query / scoped query
  -> 消费 Agent 形成可追溯解释
  -> 独立测试复核
```

执行期间始终遵守三条停止规则：

1. 正式命令无法表达必要的通用本体语义：停止并提出通用平台缺口；
2. 必须依赖 M1/M2 答案产物才能继续：停止并修正输入隔离；
3. 只有绕过 validation 或 canonical writer 才能继续：停止，不得宣称成功。

## M3 完成前检查

- [ ] 使用全新的 Project、Ontology、Build Session，且模式探针符合预期；
- [ ] 自主 Agent 没有读取禁止输入；
- [ ] 官方与合成 Evidence 分层；建模判断只进入 rationale/checkpoint/log；
- [ ] 至少一轮 dry-run 决策可追踪，失败 Attempt 未被覆盖；
- [ ] 所有 apply 均来自已 validated 的候选并使用 `apply_atomic`；
- [ ] 显式选择 `shapes` member，正例 conforms，已知负例被拒绝；
- [ ] reasoning 和 Competency Query 分别通过；
- [ ] 查询证明完整语义上下文，并显式暴露未知；
- [ ] 消费结论区分来源事实、合成事实、推论和 Agent 判断；
- [ ] 人工介入没有替代语义建模决策；
- [ ] 运行记录不包含秘密，失败与修正链完整；
- [ ] 独立测试按行为合同验收，而不是与 M2 图同构。

## M2 尚未证明的内容

M2 由主 Agent 受控执行，因此没有证明：

- 自主 Agent 能在没有答案提示时选择足够好的初始模型；
- Agent 能否正确理解和利用复杂 dry-run finding；
- 多轮自主修正是否会引入语义漂移；
- 消费 Agent 能否只基于平台事实形成可靠解释；
- 需要多少人工介入才能稳定完成；
- 当前最小循环是否需要 Brief、Coverage、Work Unit 或独立建模评审。

这些正是 M3 应记录和验证的内容，不应在开始前通过增加复杂工作流提前假设答案。

## 关联材料

- 需求：`docs/requirements/requirements-v2.1.md` R2.1-001 M3
- M3 安全操作清单：`minimal-checklist.md`
- M2 实现与工具合同：`README.md`（仅运行负责人/测试方）
- M2 追加式运行记录：`rehearsal-log.md`（仅运行负责人/测试方）
- M2 独立验收：
  `docs/delivery/test-plans/2026-07-24-r2-1-001-m2-controlled-modeling-rehearsal-test-plan.md`
