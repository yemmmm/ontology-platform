# Graphiti：持续摄入、实体消歧与双时间事实图

## 1. 阅读范围与版本

- 仓库：<https://github.com/getzep/graphiti>
- 源码快照：`345e73161a61b0a4400f80c64e5bba6a584acb7b`
- 调研日期：2026-10-23；许可证：Apache-2.0。
- 本文分析开源 Graphiti 的 Python 核心，不将 Zep 托管产品功能自动归入该仓库；重点是 add_episode、实体和边解析、时间、来源、检索与删除。没有部署数据库或执行 LLM。

## 2. 建模定位：随时间演化的事实记忆

Graphiti 接收消息、文本、JSON 等 episode，把其中实体和事实持续整合到图中。目标不是只做一次离线抽取，而是让后续输入能够补充已有实体、识别重复事实，并让过时事实停止在当前时间有效。

其“ontology”主要表现为可选的 Pydantic 实体／关系类型和属性定义，以及允许的端点类型组合。这提供类型化属性图，不是默认生成 OWL 类表达式、公理体系或执行描述逻辑一致性检查。[S1] [S2]

## 3. 图里存储的不同层次

| 对象 | 关键字段／连接 | 含义 |
| --- | --- | --- |
| EpisodicNode | source、content、source_description、valid_at、entity_edges | 输入事件及来源 |
| EntityNode | name、labels、name_embedding、summary、attributes | 被多次提及的实体 |
| EntityEdge | name、fact、fact_embedding、episodes、时间字段、attributes | 两实体间的一条事实 |
| EpisodicEdge | episode → entity，MENTIONS | 原始输入提及实体 |
| CommunityNode | summary、name_embedding 及成员连接 | 实体群的聚合摘要 |
| SagaNode | 首尾 episode、summary，HAS_EPISODE / NEXT_EPISODE | 连续 episode 的序列组织 |

所有基础 Node 都有 UUID、group_id、labels 和 created_at。group_id 用于图分区及检索范围；它与“实体类型”是不同维度。实体 identity 使用 UUID，名称并非数据库中唯一身份的充分条件。[S2] [S3]

## 4. 单个 Episode 的实际处理链

`Graphiti.add_episode()` 的本快照路径如下：[S1]

1. 校验用户提供的实体类型和排除类型，建立请求级 driver/clients scope。
2. 根据 reference_time 和 group_id 取得历史 episode，或使用显式提供的历史 UUID。
3. 建立当前 EpisodicNode；若传入已有 UUID，则读取对应 episode。
4. `extract_nodes()` 抽取实体，使用当前及历史文本处理上下文。
5. `resolve_extracted_nodes()` 检索已有候选并完成实体消歧，产生 UUID 映射。
6. 抽取关系、修正端点指针、去重与矛盾处理。
7. 抽取实体属性及摘要，只把新事实边用于摘要更新以减少重复。
8. 保存 episode、MENTIONS、实体与事实边；按需维护 saga 和 community。

注释中有“关系与属性并行”的描述，但该 add_episode 实现先 await 边处理，再 await 属性处理；不能仅凭注释宣称这两个步骤实际并行。内部仍有受限并发，例如批量 embedding、候选搜索和独立对象调用。

仓库存在 bulk 和 combined extraction 路径，它们为批处理提供另一套组织方式；不能把辅助函数存在误认为单条 add_episode 的默认路径。

## 5. 实体消歧：候选召回与最终决策分离

### 5.1 候选从哪里来

`_collect_candidate_nodes()` 合并 identity property 查询、规范名称精确查询和语义检索候选，也可接受调用方指定的已有节点集合。identity properties 是可选机制，不代表所有 add_episode 调用默认都为每类实体配置了主键。[S4]

### 5.2 如何确定是否合并

`resolve_extracted_nodes()` 对每个新节点按阶段判断：

- 先尝试配置的身份属性精确匹配。
- 再做确定性的名称匹配和模糊相似处理。
- 剩余有候选但不确定的项交给 LLM 解析。
- 没有候选或没有确认重复的实体保留为新节点。

`dedup_helpers.py` 包括名称规范化、精确索引、MinHash 候选和 Jaccard shingle 相似度等逻辑。检索 embedding 是找到可能重复实体的方法之一，但不能概括为“余弦阈值超过就一律合并”。[S4] [S5]

返回值除了规范实体，还包括原 UUID→目标 UUID 映射及重复节点对。关系抽取后利用映射替换端点，确保旧名称和新名称最终指向同一个规范节点。

### 5.3 关系补出的端点

边抽取有时产生实体抽取阶段没有给出的端点。当前实现会 materialize 这些节点，先和本轮已解析节点按规范名称匹配，再让剩余端点进入通常的实体消歧流程。否则它们尚未入库，数据库检索无法看到本轮新实体，容易产生重复。[S1]

## 6. 事实边：文字事实与结构化类型同时保留

EntityEdge 不仅有关系 name，还保留完整 fact 句子并生成 fact_embedding。相同的关系名称可以有不同事实文本；事实中的条件、时间和解释未必全部成为独立节点，因此不能只导出 source/name/target 就认为语义没有损失。

自定义 edge_types 为关系附加 Pydantic 属性，`edge_type_map` 将允许关系映射到主体类型、客体类型组合。`enforce_edge_type_signatures()` 检查实际端点标签：[S6]

- strict 模式下丢弃不符合签名的自定义关系。
- 非 strict 模式下把它改为默认关系名，并清空不再适用的自定义属性。
- 没有声明签名的关系类型不被同样限制。

该检查类似属性图的端点类型约束，不等同于 OWL domain/range 的推理语义。单条 add_episode 的内部调用并没有公开开启 strict 参数，不能宣称它默认严格拒绝所有不匹配关系。

## 7. 去重和矛盾不是同一操作

`resolve_extracted_edges()` 先做本轮快速去重，再生成事实向量，检索重复候选与更广义的冲突候选。重复候选受端点对限制；矛盾候选范围可更广。[S6]

`_dedupe_extracted_edge()` 的精确快速路径对相同方向端点及规范 fact 文本直接复用旧边，并增加 episode 来源。其他情况把候选索引交给 LLM，分别返回 duplicate_facts 和 contradicted_facts；程序验证索引范围，避免模型随意引用不存在的候选。

重复事实通常复用已有 UUID、扩展支持来源；矛盾事实则进入时间失效逻辑。两者不能混为“删除旧边”。完整事实文字相同的快速路径会提前返回，因此也不应假设每次重复出现都重新推断时间属性。

## 8. 双时间模型及实际语义

| 字段 | 代码意图 | 示例性理解 |
| --- | --- | --- |
| `created_at` | 系统创建记录的时间 | 今天摄入一份旧公告 |
| `expired_at` | 系统将事实标为过期的时间 | 今天得知它已不成立 |
| `valid_at` | 事实开始有效的时间 | 公告说任职从去年开始 |
| `invalid_at` | 事实停止有效的时间 | 公告说上月离任 |
| `reference_time` | 产生该边的 episode 参考时间 | 解析“昨天”等表达的基准 |

存在两类时间轴并不自动提供完整双时态数据库的全部查询和版本语义；应以相应查询过滤器和更新行为为准。[S3]

`_apply_temporal_invalidation()` 处理已经带结束时间的历史事实，也考虑晚到数据：若候选的开始时间更晚，新来的旧事实本身可能被标记为已过期。`resolve_edge_contradictions()` 对区间是否重叠作判断；不重叠的历史事实不会仅因为文字不同就相互失效。[S6]

当前还有专门的 future temporal normalization：对“计划／承诺将发生”的事实，valid_at 表示作出陈述时该计划事实成立，未来发生日期留在 fact 或属性中；软截止日期不直接作为 invalid_at。该辅助函数含英文正则规则，不能推断所有语言都获得完全相同的时间归一化保障。[S7]

失效候选由 LLM 判断，时间也可能由 LLM 抽取。代码中的区间逻辑提高更新可控性，但无法使错误的矛盾判断自动变真；没有显式起止时间、同一时点冲突或复杂条件事实时尤其需要检查实际结果。

## 9. 来源、删除、摘要和增量组织

`episodes` 字段记录支持事实的输入，MENTIONS 把 episode 连接到实体。若 `store_raw_episode_content=False`，保存前会清空 episode 正文；仍有来源 ID 不代表仍可从数据库重读完整证据。[S1]

`remove_episode()` 会移除事实的该条来源，保留仍有其他 episode 支持的边；删除只由该 episode 提及的实体，并尝试根据剩余 episode 重建受影响摘要。删除不只是删原文节点，也涉及派生事实和摘要维护。[S1]

Community 使用 label propagation 分组，再由模型生成摘要；它是图结构聚合，不是子类分类。更新为可选项，add_episode 默认 `update_communities=False`。Saga 用 HAS_EPISODE 和 NEXT_EPISODE 表达输入序列，并维护摘要状态；Saga 的时间顺序也不等同于实体事实的有效期。[S1] [S8]

## 10. 检索与 Agent 边界

搜索配置把事实、实体、episode 和 community 视为不同召回对象；可组合全文、向量、BFS 等方法。重排选项包括 RRF、MMR、节点距离、episode 提及次数和 cross-encoder，取决于对象类型与具体 recipe。[S9]

这些机制解释了为何图中同时保留事实句、实体摘要和原始 episode：它们服务不同粒度的记忆检索。Graphiti 可以作为 Agent 的长期记忆组件，但主摄入流程本身是异步维护管线，没有领域专家→本体设计师→OWL 验证师这样的角色协商图。

仓库有时间、去重、bulk、saga、检索等单测。本文仅阅读相关实现和测试入口，未运行测试或复现准确率。数据库 driver 抽象支持多个后端，但具体索引、查询和部署特性仍需查看对应 driver，不能根据统一接口假定完全同等。

## 11. 固定版本源码索引

- [S1：Graphiti 主入口](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/graphiti.py)
- [S2：节点模型](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/nodes.py)
- [S3：边模型](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/edges.py)
- [S4：实体抽取与解析](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/node_operations.py)
- [S5：确定性消歧辅助函数](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/dedup_helpers.py)
- [S6：边抽取、去重与失效](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/edge_operations.py)
- [S7：未来事实的时间归一化](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/temporal_edge_utils.py)
- [S8：社区构建](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/community_operations.py)
- [S9：搜索配置](https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/search/search_config.py)

[S1]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/graphiti.py
[S2]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/nodes.py
[S3]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/edges.py
[S4]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/node_operations.py
[S5]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/dedup_helpers.py
[S6]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/edge_operations.py
[S7]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/temporal_edge_utils.py
[S8]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/utils/maintenance/community_operations.py
[S9]: https://github.com/getzep/graphiti/blob/345e73161a61b0a4400f80c64e5bba6a584acb7b/graphiti_core/search/search_config.py
