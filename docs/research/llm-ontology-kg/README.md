# 大模型本体学习与知识图谱构建：开源项目源码调研

调研日期：**2026-10-23**。本目录记录项目本身的建模理念、知识组织方法、主要数据结构、提示与模型调用、归并和验证、Agent／工作流组织及代码边界，供后续按机制查阅。

这是外部项目研究资料，不是 OntoWeave 产品需求、架构决定或实施建议。没有针对本仓库设计集成方案，也没有修改平台代码。

## 1. 文档目录

| 文档 | 主要研究对象 | 重点 |
| --- | --- | --- |
| [01 AutoSchemaKG](01-autoschemakg.md) | 无预定义领域 Schema 的图谱构建 | 实体／事件／关系抽取、概念化、来源图、分片 |
| [02 EDC](02-edc.md) | Extract–Define–Canonicalize | 关系定义、候选检索、谓词归一化、Schema 扩展与迭代 |
| [03 OntoGen](03-ontogen.md) | ontorag 仓库中的科学本体生成 | TERMO、术语与同义词、类别种子、投票、分类层级去环 |
| [04 OntoGPT](04-ontogpt.md) | LinkML 与已有本体指导抽取 | 递归 schema walking、OAK grounding、术语验证、RDF/OWL 导出 |
| [05 多 Agent 本体生成研究](05-multi-agent-ontology-generation.md) | 保险合同到 OWL/RDF 的研究代码 | CQ、SRD、TIP、LangGraph、文件工具、QA 与 HermiT |
| [06 KAG](06-kag.md) | OpenSPG 上的知识构建与问答 | Schema 约束、对象属性展开、Chunk 互索引、Planner/Executor |
| [07 Graphiti](07-graphiti.md) | 持续更新的时态事实图 | episode、实体消歧、事实去重／失效、来源与检索 |
| [08 iText2KG / ATOM / C-Unseen](08-itext2kg-atom.md) | 增量图及后续时间图研究 | 原子事实、名称与类型 embedding、并行归并、双时间、弱信号 |
| [09 Microsoft GraphRAG](09-microsoft-graphrag.md) | 社区报告驱动的语料索引 | 实体关联、描述汇总、Leiden、FastGraphRAG、增量索引 |
| [10 LightRAG](10-lightrag.md) | 实体与关系双层检索 | 无向端点对、描述归并、来源跟踪、恢复、local/global/mix |
| [11 LLMs4OL](11-llms4ol.md) | 本体学习的任务与基准 | Term Typing、Taxonomy、非分类关系判断、评分和微调 |
| [12 机制与术语索引](12-mechanism-index.md) | 跨项目查阅入口 | 相同术语的不同含义、角色交接物、验证层次、代码定位 |
| [源码版本锁](sources-lock.json) | 11 个上游仓库 | 固定 commit、许可证记录、文档映射与引用源码路径 |

## 2. 这些工作属于什么研究领域

这组项目跨越几条彼此关联、但目标不同的研究线：

- **Ontology Learning / Ontology Engineering**：从知识材料学习概念、类型、分类关系、非分类关系和公理，或辅助本体工程。LLMs4OL、OntoGen、多 Agent OWL 研究与这条线关系最直接。
- **Information Extraction / OpenIE / Knowledge Graph Construction**：抽实体、关系、事件，再做归一化、实体链接和知识融合。EDC、AutoSchemaKG、iText2KG/ATOM 体现不同路线。
- **Ontology Population / Schema-guided Extraction**：模式已存在，抽取符合模式的实例并链接已有术语。OntoGPT 和 KAG 的约束构建路径属于这一类。
- **Temporal Knowledge Graph / Agent Memory**：持续记录新事实、处理重复和时间变化。Graphiti、ATOM 着重于这一层。
- **Graph-based RAG / Knowledge-augmented Generation**：用图、原文和摘要组织检索与问答。Microsoft GraphRAG、LightRAG、KAG 体现不同结构。

领域划分用于解释任务，不是互斥标签；例如一个构图项目也能提供检索。详细对应与证据在各文档及 [LLMs4OL](11-llms4ol.md) 中展开。

## 3. 输出物的区别

| 项目 | 主要产物 | Schema 从哪里来 | 本文核对到的形式化边界 |
| --- | --- | --- | --- |
| AutoSchemaKG | 实体／事件图、概念节点与映射 | 从图元素及上下文开放概念化 | 概念短语不自动成为 OWL 类层级 |
| EDC | 规范谓词三元组、关系定义字典 | 外部 schema 或逐步扩展 | 重点是关系词表，非完整类／公理体系 |
| OntoGen | 术语表、同义词、分类图对象 | 多次类别生成与层级归纳 | 主 taxonomy 脚本输出 Tree/wordmap pickle |
| OntoGPT | 模板实例、规范 ID、验证报告 | 预设 LinkML 和外部本体 | 能导出 RDF/OWL；语义依赖模板映射 |
| 多 Agent 研究 | 累积的 TTL 类、属性、公理和事实 | CQ、语义需求、设计计划 | 确有 RDF 解析和 OWL 一致性检查；仍需区分质量审阅 |
| KAG | SPG 子图、文本及多种索引 | 领域 schema 与开放抽取结合 | Python Builder 不等于自动生成完整 OWL |
| Graphiti | 带来源与时间的实体事实图 | 可选 Pydantic 类型与开放事实 | 端点签名和时间更新，不是 OWL 推理 |
| iText2KG / ATOM | 归并实体关系图／时间图 | 开放标签和关系名称 | 向量归一化、时间列表合并，不是公理学习 |
| Microsoft GraphRAG | 实体关联图、层级社区、报告 | 类型提示、开放描述、聚类 | 社区层级不等于 taxonomy |
| LightRAG | 实体／关系描述图与向量索引 | 类型指导、开放关系描述 | 关系按无向端点对合并 |
| LLMs4OL | 任务预测、指标和模型产物 | 基准的类型／关系候选空间 | 主要测子任务，不是完整构图平台 |

## 4. 阅读方法与证据等级

每篇项目文档尽量沿“输入→中间知识→模型调用→程序后处理→持久化→维护／查询”解释，不只复述 README。

文档中的结论分为三类：

1. **项目／论文主张**：说明作者提出的目标和方法。论文链接用于追溯，不将作者报告的效果当作本次复现结果。
2. **当前源码事实**：来自固定 commit 中的方法、数据字段、prompt、控制流和输出代码。核心出处附固定版本链接。
3. **静态推断或疑点**：例如某调用分支与注释不同、先后次序可能影响归并、字段与方法不一致。文中明确标为静态观察，不宣称已动态复现故障。

没有运行上游模型推理、加载全部外部本体、部署图数据库或重现论文分数。只检查相关代码和部分测试入口；“仓库存在测试”与“本次运行测试通过”严格区分。

## 5. 版本与收录边界

项目代码可能比论文更新，因此以每篇页首 SHA 为实现依据。所有源代码链接固定到该 SHA，不用可变的 main 分支支撑具体函数行为。`sources-lock.json` 保存引用路径，便于后续定位同一快照。

这不是 GitHub 热度排名，没有用不同时点的 star 数比较项目。收录兼顾常见工程项目、与 ontology learning 直接相关的方法及多 Agent 研究原型；较新的研究代码并不因被收录就被视为成熟产品。

多 Agent 本体生成仓库在本快照根目录未见 LICENSE，已单独标为公开研究代码；其余许可记录来自对应快照文件。代码许可与论文、数据、本体或模型的许可并不自动相同。

本文档集不承诺覆盖上游所有目录、插件、后端或历史版本。范围重点是可能影响知识表示与生成结果的实现；各篇明确列出未审阅或未验证的部分。
