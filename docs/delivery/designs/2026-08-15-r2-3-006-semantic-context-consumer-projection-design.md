# R2.3-006 语义检索接口直接优化设计

- 状态：Implemented；完整 N=2 PASS（live-124），R2.3-006 已交付
- 权威需求：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- 关联实现：`backend/app/services/semantic_context_query.py`、`backend/app/services/semantic_sparql_templates.py`
- 关联设计：`docs/delivery/designs/2026-07-20-r1-2-004-related-query-aggregation-design.md`

## 1. 目标

直接优化 `query_semantic_context` 原接口的返回格式和内容，使 Platform Examiner 以更少
tokens 和更少困惑完成同一结论。不增加 `projection` 参数、不增加新端点或新组件。

## 2. 实测基线

- `query=versionState, resource_types=["fact"], limit=4, context_limit=0`：约 `1970 tokens`；
- `query=currentlyConsumesOutput, resource_types=["relation","fact"]`：约 `2477 tokens`；
- `query="Version 2", context_limit=3`：约 `3706 tokens`，related_context 首屏为 TBox 公理；
- probe-04：16 次查询、`evidence_tokens=29343`。

## 3. 直接修改内容

### 3.1 顶层 envelope 精简

- `query` 只保留 `queries` 和 `normalized_queries`；
- `scope` 只保留 `project_id/mode/status/ontologies`，每个 ontology 只保留
  `ontology_id/workspace_version`；
- `recall` 只保留 `mode/match_status/completeness`；
- `warnings` 继续保留 code/message（Protocol gate 依赖）。

### 3.2 item 公开投影

每个 `primary_matches`/`related_context` item 现在包含：

- 身份/类型：`id, kind, origin, label, iri, ontology_id, assertion_kind, target_kind`；
- 内容：`data`；
- 治理：`evidence_reference_ids, evidence_status, lineage, warnings`；
- 匹配说明：`match.score/candidate_level/lexical_score/matched_fields/reasons`；
- 多表达式支持：`matched_queries[indexes, evidence_tier], fusion`；
- mapping 候选继续保留 `mapping_evidence`。

移除：

- 内部字段 `_expression_indexes`；
- 重复展示字段 `aliases/description/distance/assertion_type`；
- item 级 `derived_state`；
- `match` 中的 `matched_terms/semantic_similarity/effective_score/method/threshold`。

Protocol gate、Codex formal retrieval gate、前端 ClassesPage 依赖的字段全部保留。

### 3.3 origin 分类

新增稳定字段 `origin`：

- `asserted_literal`：真实断言且 object 为 literal；
- `asserted_relation`：真实断言且 object 为 URI/bnode；
- `resource`：instance/concept/relation 资源本身；
- `derived_statement`：reasoning/rule 派生语句；
- `shape_constraint`：Shape 投影；
- `tbox_statement`：`rdf:type`、`rdfs:domain/range/subClassOf` 等 schema 公理。

### 3.4 语句 label 直接进入 `data`

`data` 增加：

- `subject_label`；
- `predicate_label`；
- `object_label`。

模型不需要为每个 IRI 再发一次实体查询。

### 3.5 related_context 事实优先排序

`_context_sort_key` 在 `distance` 之后加入 origin rank：

```text
asserted_literal
→ asserted_relation
→ resource
→ derived_statement
→ shape_constraint
→ tbox_statement
```

然后再按 kind/ontology/label/id。TBox 和 shape constraints 仍可翻页获取，但不再占满
`context_limit≤3` 的首屏。

### 3.6 neighborhood SPARQL 修复

保留上一轮修复：`VALUES ?anchor` 位于 `GRAPH` 内，真实 Oxigraph 可返回邻近语句。

### 3.7 精确 IRI anchor 模式

不增加新参数：当单表达式 `query` 本身是绝对 IRI（`http/https/urn`）时，原接口自动切换为
exact-anchor 模式：

- 跳过 lexical/semantic recall；
- 该 IRI 作为唯一 primary match 返回；
- `related_context` 使用同一 neighborhood 扩展和 factual order；
- `context_cursor` 可继续翻同一 anchor 的上下文；
- 未命中返回 `result_status=no_match` 和 `anchor_not_found` warning；
- `match_cursor` 在 anchor 模式下被拒绝。

Platform 提示词同步要求：从任何返回项的 `id/iri/subject/predicate/object` 得到绝对 IRI 后，
下一步直接以该 IRI 作为 `query` 做精确导航，不再靠关键词重猜。

### 3.8 初始方向查询默认条数

Platform proxy 的 `limit` 默认值和最大值从 `5` 调整为 `10`：初始不知道从哪开始时可以多看到几个
候选方向；命中 IRI 后改用 anchor 模式精确展开，不依赖大 limit。

## 4. 兼容性

- 不改请求 schema，不增加参数；
- 保留 Protocol gate/前端依赖字段；
- cursor 分页语义不变，context total order 仅 related_context 排序键调整；
- 不添加 CQ/业务字段。

## 5. 验证

- backend full：`850 passed, 10 skipped`；仅 2 个既有 owl-reasoner 环境失败；
- modeling_team full：`800 passed, 1 skipped, 273 subtests passed`；
- 直接接口 token 复测：
  - `versionState`：`1970 -> 1519`；
  - `currentlyConsumesOutput`：`2477 -> 1875`；
  - `Version 2 instance`：`1140 -> 765`；
  - `Version 2 context=3`：`3706 -> 3017`，首屏由 TBox 变为
    `Version 1 markedLatest / Version 1 publicationStatus / Version 2 markedLatest`。
- probe-05 真实 Platform child 仍为 provider child-timeout；接口 token/内容优化已生效，剩余
  卡点不在检索返回格式，而在 DeepSeek 停止生成与模型收敛。
- probe-06 在 exact-anchor 模式下提交成功：4 steps / 12 proxy calls / evidence 20926 /
  total 126086，较 probe-04（8/16/29343/309591）显著下降；coverage 主题从 12 个降到 6 个，
  证明“模糊起点 → IRI anchor”导航有效。

## 6. 非目标

- 不新增 projection/compact 开关或服务；
- 不修改 Protocol gate、前端和 R2.3-005/default 路径行为；
- 不实现通用图查询语言或业务专属投影。
