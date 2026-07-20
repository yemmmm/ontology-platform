# ADR 0006: 使用 pgvector 建立可重建语义检索投影

## Status

Accepted

## Context

R-006 Context Query 已能在明确 Project/Ontology 范围内对 label、altLabel、描述、标识符、Rule 和
Operation 元数据做确定性词面匹配，但中文业务名称无法召回只有英文名称的资源。Phase 6 留下了
Search/Vector 文档生成器和 projection job/manifest 生命周期，运行时仍使用 `FakeVectorWriter`，
没有持久化向量查询能力。

R1.2-003 需要同时服务 Context Query、Entity 搜索和 Class 搜索，并保持 RDF Dataset/活动 Rule
定义为语义事实源。相似度只能扩大候选，不得成为新的等价断言。

## Decision

1. 在现有 PostgreSQL 17 部署中启用 pgvector，保存由 Ontology 当前语义状态重建的检索文档和
   embedding。v1 使用授权范围过滤后的 exact cosine search，不建立 HNSW/IVFFlat 近似索引；
   exact search 超时只能降级，不能返回完整 no-match。
2. 检索索引是 projection，不是权威存储。每条文档和 manifest 绑定 Ontology、workspace version、
   source signature、模型/维度/文档模板配置哈希和投影版本；只有完全匹配且 current 的分区可查。
3. 共享检索服务每次同时执行确定性词面和向量召回。显式 label、altLabel、Mapping 和稳定标识符
   依据优先；向量只产生带相似度和候选等级的 `semantic_candidate`。
4. 索引只包含语义元数据，不包含任意业务事实值、Evidence 原文、审计内容、秘密或查询正文。
5. 语义写入先提交权威事实，再在同一请求中同步重建受影响 Ontology 索引。索引失败返回
   `write_applied + index_failed/stale`，不得声称跨 Oxigraph、PostgreSQL 和外部 provider 原子回滚。
6. 首版不引入 rerank 模型。只有固定评测证明正确资源稳定进入 Top-K、但目标 Top-N 排序持续失败
   时，才另立需求引入并版本化 rerank。
7. 活动 Rule 集合的确定性 signature 是检索版本合同的一部分。Rule create/PATCH/DELETE 与
   manifest stale 在同一 PostgreSQL 事务提交；查询时重新计算 signature，确保提交后崩溃也不能
   继续读取旧 Rule 投影。

## Rejected alternatives

- **只补中文 altLabel/Mapping**：可以修复已知示例，但不能覆盖未知跨语言词面，也无法形成可复用
  检索基础；显式别名仍应作为高优先级证据保留。
- **受控翻译后词面匹配**：引入另一个外部模型依赖，翻译结果仍需候选治理，并会把查询扩展误当作
  本体依据。
- **独立向量数据库**：当前规模和部署不需要额外的权限、备份、一致性和运维边界；pgvector 能与
  现有 projection metadata、授权和版本过滤共存。
- **请求时全量 embedding**：调用量和延迟随 Ontology 规模线性增长，provider 故障会放大，并且
  无法提供稳定索引版本。
- **同步索引失败回滚事实**：Oxigraph、PostgreSQL 和外部 embedding API 没有分布式事务，会产生
  已写 RDF 但接口宣称失败的假原子性。
- **首版强制 rerank**：当前资源多为短 label、缺少 description，reranker 不能安全解决真实语义
  歧义，却增加延迟、费用、版本漂移和降级分支。
- **v1 使用 HNSW/IVFFlat**：pgvector 的近似索引会用召回率换速度，强 Ontology/version 过滤可能
  在 post-filter 后得到不足候选。R1.2-003 必须能区分完整 no-match，因此先使用 exact search；
  后续只有在固定 scope 下通过 exact parity、under-recall 和降级验收后才可引入 ANN。

## Consequences

- 部署必须使用包含 pgvector 的 PostgreSQL 17 镜像，并在 Alembic migration 前验证扩展可用；
  同主版本数据卷升级仍需在发布演练中验证。
- backend 增加 pgvector SQLAlchemy 依赖、检索文档表、范围/词面索引、真实 projection writer 和
  shared retrieval repository/service。
- 模型、维度、阈值、融合或文档模板变化都需要新的 projection version 和 backfill，不能原地改写
  current 结果。
- 同步重建增加语义写请求延迟；事实仍可在索引失败时使用词面路径读取。未来若规模证明同步合同
  不可接受，可在不改变 manifest/查询合同的前提下由后续需求迁移到持久异步任务。
- R1.2-002 的 Project/Ontology 目录继续保持确定性，不因共享模块存在而扩大语义发现范围。
- exact scan 的成本随过滤后文档数增长；达到查询预算时返回 degraded，不得为性能切换到未验收
  ANN。规模数据证明需要近似检索时，以新 projection version 另行设计和验收。
