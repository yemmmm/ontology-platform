# M3 业务说明：Workflow-as-Tool 发布变更影响上下文

## 业务用户叙述

我是一个使用 Dify Workflow 组织内容生产与发布流程的业务负责人。团队把可复用的 Workflow
发布成 Tool，再由其他 Workflow 调用。现在我准备发布 `Content Quality Scoring Workflow`
的新版本，其中删除了已有调用方正在使用的 `quality_score:number` 输出。

在发布前后，我需要消费 Agent 能够从语义平台取得足够事实，回答“哪些当前调用链值得进一步
检查、变化如何沿变量使用路径传播、哪些信息仍然未知”。我不要求平台或本体替我判断高、中、低
风险，也不要求它断言某个业务流程一定受影响；最终判断由消费 Agent 基于平台事实完成。

这是一组为了验证通用本体建模能力而构造的合成业务数据，不是 Dify 官方预置应用。

## 我要解决的业务问题

1. 当被调用 Workflow 的新 Latest Version 删除一个已发布 Output 时，当前发布调用链中有哪些
   直接和传递调用方候选？
2. 对每个候选，能否看到从被删除 Output 到调用位置、输出 Binding、调用方内部变量使用、
   调用方 Output，以及下一层 Workflow Tool 调用的完整数据使用路径？
3. 相同删除若只存在于 Current Draft、尚未发布，能否与当前 Latest Version 的调用链清楚区分？
4. 如果某一层节点、Binding 或变量使用信息没有建模，消费 Agent 能否看到明确的未知项，而不是
   把空结果误解成“确认没有后续影响”？
5. 模型能否拒绝一个缺少必要调用目标、调用位置或等价关键结构的无效 Tool Invocation？
6. 模型中声明的至少一项分类或关系语义，能否由当前平台支持的推理能力稳定推出，而不是全部
   依靠实例显式重复声明？

## 术语和业务边界

- `Workflow`：具有业务身份、可以持续演进的流程。
- `Workflow Version`：Workflow 在某一时点的可区分版本。Current Draft 与 Latest Version 是
  不同发布状态，不能混为同一当前运行版本。
- `Workflow Tool`：由符合 Dify 条件的 Workflow 发布出来、供其他 Workflow 调用的 Tool。
- `Tool Invocation`：某个调用方 Workflow Version 中的一次具体 Tool 调用。它应能定位到稳定
  调用位置，并指向所调用的 Tool 或其当前目标版本。
- `Input/Output Contract`：被调用 Workflow 对外暴露的输入和输出变量合同，包括名称、数据类型
  和必要时的必填性。
- `Variable Binding`：调用位置两侧变量之间的显式绑定。输入 Binding 表示调用方把什么传给
  被调用方；输出 Binding 表示被调用方结果进入调用方的哪个本地变量。
- `Variable Use`：变量在调用方内部被条件、处理节点、Output 或下一层 Tool Invocation 使用的
  位置。
- `Change Set`：相对于明确前一版本和目标版本的变化集合。本轮正例只处理删除 Output，不把
  rename 猜测为等价迁移。
- `Explicit Gap`：已知某部分业务资料未建模、不可用或无法确认。未知必须带可理解的说明。

这些是业务含义，不指定必须创建哪些 Class、Property、Shape、公理或 IRI。自主建模 Agent 应选择
并解释自己的模型结构。

## 合成业务事实

### C：Content Quality Scoring Workflow

- 业务用途：对生成内容进行质量评分。
- 旧的已发布版本接收 `content:string`。
- 旧的已发布版本返回 `quality_score:number`。
- 它作为 Workflow Tool 被 B 调用。
- 正例 Change Set：C 的新版本删除 `quality_score:number`，并发布为新的 Latest Version。
- 反例 Change Set：相同删除只存在于 Current Draft；当前 Latest Version 仍是保留
  `quality_score:number` 的旧版本。

### B：Content Generation Workflow

- 业务用途：生成内容并根据质量评分决定是否形成可发布内容。
- B 的当前发布版本中有一个稳定可识别的 C Tool 调用位置。
- B 把待评估内容绑定到 C 的 `content` Input。
- B 把 C 的 `quality_score` Output 绑定到本地 `quality_score` 变量。
- B 的 IF/ELSE 使用该本地变量。
- 条件处理产生 `approved_content:string`，并由 B 的对外 Output 暴露。
- B 自身也作为 Workflow Tool 被 A 调用。

### A：Campaign Publication Workflow

- 业务用途：准备营销活动内容的发布。
- A 的当前发布版本中有一个稳定可识别的 B Tool 调用位置。
- A 把 B 的 `approved_content` Output 绑定到本地 `publish_content`。
- `publish_content` 被后续发布准备节点或 A 的 Output 使用。

### 显式未知

另有一处调用或变量使用记录已知不完整。模型需要表达“缺少哪类事实”和自然语言说明，使消费
Agent 明确当前资料不足。不得仅省略三元组或返回空查询结果。

## 期望的业务行为

对于已发布删除，平台的通用查询结果应让消费 Agent逐项追踪：

```text
C 的旧/新版本与已发布删除
  -> B 中调用 C 的位置
  -> B 传给 C.content 的输入 Binding
  -> C.quality_score 到 B 本地变量的输出 Binding
  -> B 的 IF/ELSE 使用及 approved_content 产生/输出
  -> A 中调用 B 的位置
  -> B.approved_content 到 A.publish_content 的 Binding
  -> A 的后续使用位置
```

结果还应包含相关发布状态、版本、合同、来源性质、推论状态和完整性信息。直接调用方 B 和传递
调用方 A 都应成为进一步分析候选。

对于只存在于 Current Draft 的相同删除，查询可以返回草稿变化和潜在路径，但必须明确它没有进入
当前 Latest Version 调用链，不能把它当成已经发布的变化。

## 来源与判断边界

以下三类内容必须分开记录，而且使用不同的承载渠道：

1. `official source Evidence`：Dify 资料实际说明的 Workflow-as-Tool、Output 合同和
   Current Draft/Latest Version 发布语义，Evidence excerpt 必须是资料原文；
2. `synthetic fixture Evidence`：本说明中的 C、B、A、变量、调用、Binding、Use 和 Change Set，
   Evidence excerpt 必须直接摘录本说明，不能伪装成 Dify 官方事实；
3. `modeling decision rationale`：建模 Agent 对概念边界、约束、公理和查询方式的选择与理由，
   只记录在 Modeling Item `rationale`、Build Checkpoint 和执行日志，不创建 Evidence Reference。

官方资料不能为合成的 C/B/A 业务事实背书。Agent 推论也不能伪装为来源事实。

## 非目标

- 不解析真实 Dify DSL，不执行 Workflow，不比较运行指标。
- 不判断或输出高、中、低影响等级。
- 不把路径上的 Workflow 断言为业务上一定受影响。
- 不处理 Output rename 的语义等价。
- 不建设 Dify 专属 API、Schema、查询分支、排序规则或影响分析器。
- 不复制 M1/M2 的答案型本体、Shapes、Batch payload、查询或运行结果。
- 不要求模型与既有候选使用相同名称、IRI、三元组数量或类图。

## 本轮完成标准

- 在全新空白 Project/Ontology 中，通过正式 Modeling Batch dry-run 与 `apply_atomic` 建立模型；
- 至少一次 dry-run 接受或修正决策可追踪；
- 正例通过已显式激活 Shapes 的 validation，Agent 自己构造的已知无效 Invocation 被拒绝；
- 至少一个由当前平台支持的推理预期成立；
- 自主 Agent 自己编写的查询能够取得完整 C -> B -> A 上下文、区分 draft/latest 并返回显式未知；
- 独立消费 Agent 仅依据平台事实形成候选与影响解释，并逐项区分官方来源、合成事实、推论和
  自身判断；
- 没有主 Agent 语义代做、直接 RDF 写入旁路或 Dify 专属平台改动。
