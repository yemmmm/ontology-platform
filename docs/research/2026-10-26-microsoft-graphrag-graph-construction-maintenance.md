# Microsoft GraphRAG 方案设计调研：图的构建与维护

- 调研日期：2026-10-26。
- 研究对象：微软开源 [GraphRAG](https://github.com/microsoft/graphrag)，标准索引、Fast 索引、增量更新与查询设计。
- 发布版依据：[v3.3.0][release]，发布于 2026-10-08，为本次查询时的最新发布版。
- 固定源码：[5faaaf4f5685fa2056fa8c3bf9342cb089f2942f][commit]，对应 v3.3.0 标签。
- 证据范围：官方文档、固定版本源码与上游 Issue；未运行索引、模型推理、增量实验或性能基准。
- 关联阅读：[2026-10-23 GraphRAG 源码调研](llm-ontology-kg/09-microsoft-graphrag.md)。该文使用另一源码快照，本专题的具体实现结论以本页版本为准。

本文保存本次调研结论。它是外部方案研究资料；末节的架构观察不构成 OntoWeave 的产品需求、已批准设计或实施决定。

## 1. 核心设计

微软 GraphRAG 将文档加工成“实体关系图＋分层社区摘要＋向量索引”，再用这些不同粒度的知识组织问答上下文。原始论文尤其关注跨整个语料库归纳主题的问题：先建立实体关系网络，再为联系紧密的实体集合预生成摘要，查询时汇总相关内容。[原始论文][paper]

整体流程可以用纯文本表示：

```text
原始文档
  → TextUnit 文本块
  → 实体与关系抽取
  → 重复项合并与描述汇总
  → 实体关系图
  → Hierarchical Leiden 分层社区
  → 社区报告与摘要

文本块、实体描述、社区报告
  → 向量索引
  → 与图结构、来源文本一起组织查询上下文
```

图主要承担知识连接、主题组织和检索上下文生成的职责。社区是图上连接紧密的实体集合，其层级表示聚类粒度，不能直接解释为业务概念的继承层级。[官方数据流][dataflow]

## 2. 图如何从文档构建

### 2.1 文档分块与来源关联

输入文档先切分成 TextUnit。实体、关系记录保存对应的 `text_unit_ids`，文本块再关联原始文档，从而保留“图中知识→文本块→源文档”的回溯链。[数据流][dataflow] [输出表结构][outputs]

例如，两份文档分别描述“甲公司向乙公司供货”和“乙公司参与丙项目”。当两次抽取的“乙公司”被合并后，它就成为连接两份文档的节点。这个例子用于说明连接方式，不代表算法一定将这些节点划入同一个社区。

### 2.2 为每个文本块抽取局部子图

标准路径使用 LLM 同时抽取实体与关系：

| 对象 | 核心内容 |
| --- | --- |
| Entity | 名称、类型、描述 |
| Relationship | 起点、终点、关系描述、关系强度 |

抽取器还可以在同一次对话内继续补抽遗漏项，即 gleaning。解析阶段对名称、类型及关系端点做大写转换和字符串清理。[GraphExtractor 实现][extractor]

默认关系表主要用自然语言 `description` 表达关系含义，没有独立的业务谓词类型字段。`weight` 来自模型给出的关系强度，不能据此解释成经过校准的事实真实性概率。[输出表结构][outputs]

### 2.3 合并重复项并汇总描述

首次构图采用确定性的分组规则：

- 实体按 `(title, type)` 分组，收集各处描述、来源文本块并统计出现频率。
- 关系按 `(source, target)` 分组，合并描述与来源，关系强度求和。
- 过滤端点无法在实体表中匹配的关系。

随后调用 LLM，把同一个实体或关系的多段描述汇总成统一描述。[抽取结果归并][merge-extract] [描述汇总 workflow][extract-workflow]

这条默认路径主要依赖名称匹配。字符串清理可以消除部分表面差异，但别名不一定自动合并，同名对象也可能混淆。描述汇总本身不等于对矛盾事实逐项裁决。

### 2.4 构建分层社区

社区发现阶段先将关系端点规范化成无向边，去除反向重复，再把加权边列表交给 Hierarchical Leiden。算法将联系紧密的实体聚成社区，并按配置递归细分；可配置最大社区规模、随机种子，以及是否仅使用最大连通分量。[社区划分实现][cluster]

因此，关系方向在社区计算阶段被消除，社区树表达的是网络结构。它与类型标签、业务分类或本体中的 `subClassOf` 分别承担不同职责。

### 2.5 生成社区报告、持久化与向量索引

LLM 根据社区中的实体、关系及可选 claim 等内容生成报告，包括摘要、主要发现与完整内容，为不同粒度的检索提供材料。[官方数据流][dataflow]

逻辑产物包括 `documents`、`text_units`、`entities`、`relationships`、`communities`、`community_reports` 和可选 `covariates`。默认输出为 Parquet 表；文本块、实体描述和社区报告还会生成向量并写入配置的向量库。图数据库不是默认运行前提。[输出模型][outputs] [索引架构][architecture]

## 3. Standard 与 Fast 的取舍

| 环节 | Standard GraphRAG | FastGraphRAG |
| --- | --- | --- |
| 实体生成 | LLM 抽取实体及描述 | NLP 抽取名词短语 |
| 关系生成 | LLM 抽取关系描述与强度 | 同一文本块内的实体共现 |
| 描述汇总 | LLM 汇总实体和关系描述 | 省去这类汇总 |
| 社区报告 | 主要利用实体、关系等描述 | 主要利用关联文本块 |

Fast 路径降低抽图阶段的 LLM 成本，但改变了边的构建依据。官方文档指出，其图通常更嘈杂，也更难直接用于 GraphRAG 之外的场景。本次未测量两种路径的实际成本和质量差异。[索引方法说明][methods]

## 4. 图如何增量维护

### 4.1 更新粒度是新增文档批次

v3.3.0 的 `standard-update` 工作流先筛选新增文档，对它们运行完整索引流程，生成独立的增量图、社区和报告，再把这些产物与旧索引合并。[PipelineFactory][factory]

```text
输入文档集合与旧 documents 表
  → 按 title 筛选新增文档
  → 对新增文档完整执行抽取、聚类、报告及向量生成
  → 合并旧产物与增量产物
  → 针对合并后的输出执行向量生成
```

它没有在抽取新文档时把整个旧图作为模型上下文。新旧图主要通过合并规则中匹配的实体名称和关系端点连接。

### 4.2 各类产物的合并规则

| 对象 | 固定版本中的处理方式 | 依据 |
| --- | --- | --- |
| 新文档 | 根据文档 `title` 是否已存在判断新增 | [文档差异识别][delta] |
| 实体 | 按 `title` 合并，保留已有 ID 和首个 type，合并来源与描述，重新统计 frequency | [实体合并][update-entities] |
| 关系 | 按 `(source, target)` 合并，保留首个 ID，合并描述与来源；weight 使用均值 | [关系合并][update-relationships] |
| 实体与关系描述 | 合并之后再次调用描述汇总流程 | [更新 workflow][update-graph] |
| 文本块 | 追加新文本块，将其中的实体 ID 映射到合并后保留的 ID | [文本块更新][update-text-units] |
| 社区 | 给新增社区及 parent 重新编号，再与旧社区拼接 | [社区合并][update-communities] |
| 社区报告 | 使用社区编号映射后，与旧报告拼接 | [社区报告合并][update-communities] |
| 向量 | 针对合并后的输出执行向量生成流程 | [向量更新][update-embeddings] |

首次构图与增量合并存在需要注意的差别：首次实体分组包含 type，增量实体分组仅使用 title；首次重复关系强度求和，增量合并中的 weight 使用均值。因此不能假设增量结果与全量重建等价。[首次归并][merge-extract] [实体更新][update-entities] [关系更新][update-relationships]

### 4.3 缓存如何降低重复处理成本

GraphRAG 在 LLM 调用外提供缓存：输入和调优参数一致时可以复用已有结果，以减少重复推理并帮助索引任务重试。缓存负责计算复用，不承担事实更新或失效判断。[缓存设计][architecture]

## 5. 持续维护的实际边界

### 5.1 同名文档修改正文不会被识别

`get_delta_docs()` 比较新旧文档的 title 集合，没有比较正文或内容哈希。同名文档即使内容变化，也不会进入这条增量路径的新增集合。[差异识别实现][delta]

### 5.2 删除源文档不会自动撤销其知识贡献

差异函数虽然计算 `deleted_inputs`，但 `load_update_documents()` 只返回 `new_inputs`。本次检查的默认更新链没有把文档删除传播成实体、关系、社区及摘要的撤销。[差异识别][delta] [更新文档加载][load-update]

### 5.3 社区和报告没有进行全局刷新

新增社区及报告来自增量文档自身，再追加到旧结果；这条更新链没有在实体关系合并后，对整个新旧联合图重新运行 Leiden，也没有重新生成既有社区报告。

由此可推得：当新资料引入大量跨批次连接时，既有社区结构和报告可能落后于合并后的关系网络。这个判断来自控制流与合并代码，未通过运行实验量化其影响。[工作流定义][factory] [社区与报告合并][update-communities]

### 5.4 默认路径没有完整的事实生命周期维护

来源 ID 提供回溯基础，但名称归并和描述摘要没有在这条路径中解决别名消歧、矛盾裁决、按来源撤回事实及旧事实失效的完整维护。普通关系表也没有独立的有效期字段。[输出模型][outputs] [更新描述流程][update-graph]

可选 claim 通道具有状态和日期字段，但不能据此推定普通 relationships 自动获得相同的事实失效机制。

### 5.5 社区引用完整性存在上游已报告问题

[Issue #2540][issue-2540] 报告：实体合并保留旧 ID、丢弃重复增量 ID 后，新增社区中的 `entity_ids` 或 `relationship_ids` 可能仍指向被丢弃的记录。

截至 2026-10-26 本次查询，该 Issue 状态为 open。所查版本的实体合并会生成 ID 映射，文本块更新会使用实体映射，而社区合并函数没有将同样的映射应用到成员列表；关系合并也未返回对应的关系 ID 映射。[实体合并][update-entities] [文本块更新][update-text-units] [关系合并][update-relationships] [社区合并][update-communities]

这是源码观察与上游问题报告，未在本次运行复现。其潜在影响是部分社区成员引用无法解析，进而影响依赖这些引用的查询。

## 6. 查询为什么需要这些不同产物

| 查询方式 | 如何使用图及其派生产物 | 适合的问题 |
| --- | --- | --- |
| Local Search | 匹配相关实体，再组合关联实体、关系、原文与社区信息 | 围绕具体对象的问题 |
| Global Search | 对指定层级的社区报告分批生成中间结果，再以 Map-Reduce 汇总 | 整个资料库的主题与全局归纳 |
| DRIFT Search | 利用社区背景展开更细的追问与局部检索 | 需要从概览逐步深入的问题 |

对应依据：[Local Search][local-search]、[Global Search][global-search]、[查询方式概览][query]。

## 7. 已有图的接入与架构观察

微软提供 Bring Your Own Graph 方案：将已有图转换为实体、关系表，按查询需求补充文本块和向量，跳过文本抽图，直接执行社区发现与报告生成。仅面向 Global Search 的基本配置可以只执行 `create_communities` 和 `create_community_reports`。[自带图方案][byog]

结合 OntoWeave，本次讨论形成的架构观察是：可以独立评估“权威语义图之上的社区摘要与多粒度检索层”。实体身份、明确业务关系、来源和事实生命周期由权威语义层负责；社区与报告作为可重建的衍生检索产物。

这只是研究判断。本次没有设计具体集成接口、变更 OntoWeave 需求、实施平台改动，或验证该分工在本项目中的效果。

## 8. 来源与复核边界

- 原始论文用于说明方法目标，不把作者报告的效果视为本次复现结果。
- 所有具体代码链接固定到 v3.3.0 对应的完整 commit SHA。
- 官方文档与 Issue 链接是可变页面，其内容和状态以本次查询日期为界。
- 别名、矛盾和全局刷新等影响判断保留为静态分析；未作运行、质量或生产可用性验收。

[release]: https://github.com/microsoft/graphrag/releases/tag/v3.3.0
[commit]: https://github.com/microsoft/graphrag/commit/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f
[paper]: https://arxiv.org/abs/2404.16130
[architecture]: https://microsoft.github.io/graphrag/index/architecture/
[dataflow]: https://microsoft.github.io/graphrag/index/default_dataflow/
[outputs]: https://microsoft.github.io/graphrag/index/outputs/
[methods]: https://microsoft.github.io/graphrag/index/methods/
[local-search]: https://microsoft.github.io/graphrag/query/local_search/
[global-search]: https://microsoft.github.io/graphrag/query/global_search/
[query]: https://microsoft.github.io/graphrag/query/overview/
[byog]: https://microsoft.github.io/graphrag/index/byog/
[issue-2540]: https://github.com/microsoft/graphrag/issues/2540
[extractor]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/operations/extract_graph/graph_extractor.py
[merge-extract]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/operations/extract_graph/extract_graph.py
[extract-workflow]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/extract_graph.py
[cluster]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/operations/cluster_graph.py
[factory]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/factory.py
[delta]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/update/incremental_index.py
[load-update]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/load_update_documents.py
[update-entities]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/update/entities.py
[update-relationships]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/update/relationships.py
[update-graph]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/update_entities_relationships.py
[update-text-units]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/update_text_units.py
[update-communities]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/update/communities.py
[update-embeddings]: https://github.com/microsoft/graphrag/blob/5faaaf4f5685fa2056fa8c3bf9342cb089f2942f/packages/graphrag/graphrag/index/workflows/update_text_embeddings.py
