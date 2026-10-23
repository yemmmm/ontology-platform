# 机制与术语索引：按问题定位项目实现

本文件是前 11 篇项目文档的交叉索引。所有结论继承对应文章的固定 commit 和静态分析范围；这里不重复列出版本，也不提供本仓库的应用方案。

## 1. “Schema”在不同项目中指什么

| 使用位置 | Schema 的真实对象 | 主要代码入口 |
| --- | --- | --- |
| [AutoSchemaKG](01-autoschemakg.md) 的抽取配置 | JSON 结果结构 | ProcessingConfig、LLM 输出验证 |
| AutoSchemaKG 的 dynamic schema induction | 抽象概念与实体／事件／关系映射 | generate_concept、concept_to_csv |
| [EDC](02-edc.md) | 谓词名称到自然语言定义的字典 | SchemaDefiner、SchemaCanonicalizer |
| [OntoGPT](04-ontogpt.md) | 类、字段、范围、嵌套及 grounding 配置 | LinkML、SchemaView、SPIRESEngine |
| [KAG](06-kag.md) | SPG 类型、属性、关系和约束 | SchemaClient、SPGPrompt |
| [Graphiti](07-graphiti.md) | Pydantic 实体／关系属性及端点签名 | entity_types、edge_types、edge_type_map |
| [多 Agent OWL 研究](05-multi-agent-ontology-generation.md) | TTL 中的类、属性、限制等模式内容 | SRD→TIP→Coder→HermiT |

相同词汇并不保证相同表达能力。结构化 JSON schema 解决输出形状；领域 schema 定义对象类型；OWL 公理赋予形式语义。三者可以组合，但不能互相替代。

## 2. 知识整理的中间产物

| 想查阅的机制 | 项目与具体实现 | 中间产物的作用 |
| --- | --- | --- |
| 术语、缩写、定义分别保存 | [OntoGen](03-ontogen.md)：Termo | 先确定可复用词汇，再组织分类 |
| 关系先写自然语言定义 | [EDC](02-edc.md)：SchemaDefiner | 为相似度检索和语义判别提供解释 |
| 实体和事件分别建模 | [AutoSchemaKG](01-autoschemakg.md)：三类抽取 prompt | 把过程句纳入图节点 |
| 按已有类递归拆任务 | [OntoGPT](04-ontogpt.md)：_parse_line_to_dict | 每次只处理一个 class 的局部字段 |
| 业务语义与技术设计分开 | [多 Agent 研究](05-multi-agent-ontology-generation.md)：SRD、TIP | 将需求与 TTL 编写解耦 |
| 将长文拆为自包含事实 | [ATOM](08-itext2kg-atom.md)：extract_atomic_facts | 降低单次关系抽取上下文复杂度 |
| 保留原始 episode | [Graphiti](07-graphiti.md)：EpisodicNode | 事实来源、历史上下文与删除支持 |
| 文本与图互相可回溯 | [KAG](06-kag.md)：source 边 | 从图节点回到 chunk |
| 聚合区域生成报告 | [Microsoft GraphRAG](09-microsoft-graphrag.md)：community_reports | 让全局问题消费压缩后的区域知识 |
| 保存每个图对象完整来源集合 | [LightRAG](10-lightrag.md)：entity_chunks/relation_chunks | 支撑重建、删除与恢复 |

中间产物也可能是误差传播点：模型生成的定义、原子事实、摘要和计划都不是未经改写的原始证据。判断来源完整性要沿输入与派生产物分别追溯。

## 3. 归一化与身份处理的不同层次

| 操作 | 例子 | 实现代表 | 保证与边界 |
| --- | --- | --- | --- |
| 字符串规范化 | 大小写、空格、连字符 | 多个项目 | 减少词面差异，不解决同名异义 |
| 同义词／缩写映射 | 缩写与全称共用节点 | OntoGen | 依赖缩写抽取及词表正确性 |
| 外部 ID grounding | 名称→MONDO 等 CURIE | OntoGPT | 可验证标识符，仍需词义正确 |
| 谓词归一化 | 两种关系表述映到同一关系 | EDC | 候选召回与 LLM 判断；不解决所有实体身份 |
| 向量实体／关系合并 | 相似名称和类型匹配 | iText2KG、ATOM | 阈值相似不是语义等价证明 |
| 多阶段实体消歧 | 身份属性、名称、模糊、LLM | Graphiti | 仍受候选召回和上下文影响 |
| 建立规范名连接 | 原名→OfficialName | KAG | 连接不等于物理合并或 owl:sameAs |
| 按键聚合并汇总描述 | 同 title 或同端点对 | GraphRAG、LightRAG | 简洁稳定，但可能合并同名对象或多种关系 |

“对齐”可能表示链接外部 ID、添加相似边、统一名称、归并对象或修改谓词。阅读论文和类名时应检查最终写了什么数据，而不是仅凭 aligner/matcher/canonicalizer 的名称判断。

## 4. Agent 协作与普通并行的区别

| 项目 | 决定执行顺序的主体 | 交接内容 | 协作形态 |
| --- | --- | --- | --- |
| 多 Agent OWL 研究 | LangGraph 状态与路由 | SRD、TIP、TTL、QA／机器错误 | 显式角色交接和修复闭环 |
| KAG Solver | Planner 生成 Task，程序按依赖调度 | task arguments、parents、memory、result | 问答阶段的任务 DAG |
| OntoGPT | LinkML 字段范围及递归函数 | 父字段片段、子对象、grounding 结果 | Schema 驱动的递归流程 |
| EDC | 固定阶段和固定 refinement 轮数 | 三元组、定义、候选、实体／关系提示 | 多阶段抽取与迭代 |
| OntoGen | CLI 脚本和分类循环 | 词表、类别、当前树、投票关系 | 多次采样与结构更新 |
| AutoSchemaKG | shard 与批处理循环 | 抽取结果、图邻域、概念列表 | 数据并行 |
| ATOM | asyncio 与线程池 | 原子事实、小图、成对合并结果 | 抽取并行与归并并行 |
| Graphiti | add_episode 维护流程 | 实体映射、重复边、失效边、摘要 | 增量记忆维护 |
| GraphRAG / LightRAG | 索引／查询 pipeline | 图、摘要、检索上下文 | 多阶段生成和检索 |

多个模型调用、多个 prompt 或并发线程并不自动构成 multi-agent。明确角色目标、共享状态、交接物、允许动作、路由和反馈，才能具体解释系统如何协调工作。

## 5. 验证层次：检查成功分别意味着什么

| 检查 | 能发现什么 | 不能据此推断什么 | 代表实现 |
| --- | --- | --- | --- |
| JSON／记录解析 | 字段和分隔格式错误 | 事实真实 | 各抽取器 |
| 输出模型／类型检查 | 不符字段、类型、端点签名 | 原文支持、领域完整 | OntoGPT、Graphiti、KAG |
| 外部术语验证 | ID 不存在、标签不符、范围不符 | 实体关系真实 | OntoGPT TermValidator |
| 分类图结构检查 | 自环、部分循环、未知节点 | is-a 语义正确 | OntoGen |
| 多次采样投票 | 回答不稳定、低共识候选 | 多模型共同偏差消失 | OntoGen |
| LLM 关系判别 | 相似谓词是否可归一 | 形式等价证明 | EDC |
| Turtle 语法解析 | RDF 文本格式错误 | OWL 一致或业务正确 | 多 Agent 研究 |
| OWL 推理 | 特定逻辑不一致／不可满足 | 完整性、原文忠实、CQ 全部可答 | 多 Agent 研究的 HermiT |
| 时间区间更新 | 部分重叠／失效关系 | 矛盾候选判断必然正确 | Graphiti |
| CQ→SPARQL→答案判定 | 图与查询组合能否回答问题 | 所有本体结构正确 | 多 Agent 研究评测 |
| QA／RAG 分数 | 最终回答表现 | 本体公理或实体对齐正确率 | KAG、GraphRAG、LightRAG |

HermiT 的一致性检查也与 SHACL 数据约束不同。前者关注公理的逻辑可满足性；后者用于显式数据形状验证。不能把一个项目执行 RDF parse 就写成“完成本体验证”。

## 6. 事件、时间和多元关系

不同项目保留复杂语义的方法不同：

- AutoSchemaKG 用事件句作为节点，再连接实体与其他事件；结构简洁，但完整论元角色未必展开。
- 多 Agent 研究通过设计模式提示生成事件／关联节点，配合角色、时间、数量等属性；产物表达取决于实际 TTL。
- KAG 的 SchemaConstraintExtractor 按非基本属性递归生成对象和边，可以承载领域事件结构。
- Graphiti 在事实边上区分有效与系统记录时间，并保留事实文字。
- ATOM 在五元组边上累积观察、开始、结束时间列表；不自动等同于完整多段区间推理。
- GraphRAG、LightRAG 的关系描述能包含条件和时间，但默认图结构不会把每个条件都展开成形式约束。

同样出现“时间”字段，可能表示文本发布日期、模型抽取时刻、观察时间、事实开始、事实结束或系统失效。必须按字段定义和更新函数理解。

## 7. 源码检查时容易误判的地方

本次各篇已经记录了一些具体例子：

1. 配置字段存在，但主调用链未消费它，不代表功能完整启用。
2. docstring 写了默认值或并行行为，实际函数签名和 await 顺序可能不同。
3. 支持导出 OWL，可能只是把已有模板实例序列化，不代表发现新公理。
4. 同一个 repo 的旧论文、Star 版本、ATOM 版本可能使用不同权重、模型和合并规则。
5. 模型输出的来源句是改写后的 atomic fact，不一定是原始证据 span。
6. 启用了验证器，仍可能返回 skipped、unresolved 或在重试上限后继续。
7. 图按无向关系聚类或合并，可能让方向只留在文本描述里。
8. 局部二分类 F1、整图结构质量、事实准确率和最终问答分数衡量的对象不同。

具体函数、版本及限定条件均在项目专文中；这些观察不应被外推为上游全部版本的永久缺陷。
