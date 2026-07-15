# R-005 统一知识来源与推导链设计

## 1. 状态与目标

本设计细化 `docs/requirements-v1.0.md` 的 R-005，承接 R-002 的 Evidence Reference 和
R-004 的 Modeling Batch、Modeling Item、Edit Audit 与恢复机制。

目标是让平台能够对当前 Ontology 中的事实、RDF 模型结构、版本化 Rule Definition 和派生结果
返回一份诚实且结构化的 lineage：它由谁或哪次运行产生、有哪些外部证据或建模上下文、使用了
哪些前提、何时发生，以及当前是否仍有效。

首版只提供后端持久化、REST、MCP、文档和测试，不新增前端页面。R-006 可直接消费本需求的
结构化结果；R-107 再决定如何在工作台展示完整链路。

## 2. 设计原则

1. **语句实例是底层锚点。** RDF 知识以规范化 `(subject, predicate, object, graph,
   graph_revision)` 标识一个不可变 Statement Occurrence。
2. **业务对象是查询入口。** Fact 通过 `statement_id` 查询；Class、Property、Entity、Shape 等
   Semantic Resource 通过资源 IRI 聚合其当前 Statement Occurrences。
3. **证据、理由、推导和审计严格分离。** Evidence Reference 不代表平台验证过原始文档；Agent
   rationale、Competency Question 和人工 reason 都不能转换成 Evidence。
4. **派生结果不直接继承文档证据。** 它只能指向产生它的 Run、定义版本和前提链，再从前提递归
   汇总依赖证据状态。
5. **无法证明时明确降级。** 引擎不能输出精确证明时返回 `coarse` 或 `unavailable`，不得伪造前提。
6. **复用现有存储边界。** RDF Dataset 仍保存实际语句；PostgreSQL 保存 Statement Occurrence
   索引、来源链接和精确前提链接，并复用现有 Evidence、Batch、Run 和 Audit 记录。
7. **写入幂等、查询有界。** R-004 恢复或网络重试不得重复生成 lineage；递归查询必须限制深度
   和节点数量。

## 3. 范围

### 3.1 首版包含

- R-004 Modeling Item 产生的 RDF 模型结构和事实。
- canonical command 和受治理直接 RDF 编辑产生的语句。
- Rule Definition 版本及其 Modeling Item、Evidence、rationale、Competency Question 和 Audit。
- OWL reasoning、SPARQL CONSTRUCT、Platform DSL 和 workflow rule 产生的语句。
- 当前 lineage 查询、可选历史查询、证据状态、推导证明级别和陈旧状态。
- REST、MCP、迁移、服务级测试和真实运行时验收。

### 3.2 首版不包含

- 通用文档上传、解析、版本化或 Source Adapter；属于 R-101。
- 来源变更后的自动影响分析和增量重建；属于 R-102，但会复用 `statement_id` 和 premise 链。
- 不可变发布 release 的按版本查询；属于 R-105。
- 通用异步任务和分布式执行；属于 R-106。
- 新前端 lineage 图或工作台；属于 R-107。
- 强制任何 OWL reasoner 输出完整形式证明。
- RDF-star、通用 PROV-O 图存储或独立 provenance 图数据库。
- 修复现有直接 RDF 写入的跨 RDF/PostgreSQL 原子性；缺失记录通过 `partial` 明确暴露。

## 4. 领域模型

### 4.1 Lineage Target

统一查询支持三种目标：

| `target_type` | `target_id` | 含义 |
| --- | --- | --- |
| `statement` | `statement_id` | 一个规范化 RDF quad 的稳定哈希；Fact 和派生事实使用此入口。 |
| `resource` | 资源 IRI | 聚合该 IRI 作为 subject 的 RDF 模型结构或实体描述。 |
| `rule` | Rule IRI | 查询当前或历史 Rule Definition 版本的建模来源。 |

普通调用方不提交 Graph Set ID 或 graph IRI。服务按 Ontology 解析默认工作区和当前派生指针。

### 4.2 Statement ID 与 Statement Occurrence

- `statement_id` 继续使用现有 `compute_fact_id(subject, predicate, object_ntriples,
  graph_iri)` 算法，使现有 Fact Evidence Binding 无需迁移标识。
- `occurrence_id = sha256(statement_id + ":" + graph_revision)`。
- object 必须保存规范化 N-Triples term，保留 IRI、datatype 和 language tag 的差异。
- asserted graph 删除后再插入相同 quad 会产生新的 occurrence。
- reasoning/rule result graph 每次 Run 使用独立不可变 graph，首版记为 revision `1`。
- 资源查询默认只返回当前 asserted 语句和当前派生指针中的语句；`include_history=true` 才返回
  已删除 asserted occurrence 和非当前 result graph 中的 occurrence。

### 4.3 Origin

一个 Statement Occurrence 可以有多个 Origin：

- `modeling_item`：R-004 中实际 applied 且产生该 quad 的 Modeling Item；兼容重复效果合并时可有
  多个 Item Origin。
- `edit_audit`：人工编辑、canonical command 或 Modeling Batch 的技术写入审计。
- `reasoning_run`：OWL Reasoning Run。
- `rule_run`：CONSTRUCT、Platform DSL 或 workflow Rule Run。
- `legacy_unknown`：迁移前已存在、无法可靠还原产生者的语句。

Origin 只回答“由什么产生”，不回答“是否有外部证据”。

### 4.4 Supporting Context

查询服务按 Origin 复用现有记录，不复制证据正文：

- Modeling Item：Evidence Associations、`rationale`、`competency_question_ids`、Batch 和 Attempt。
- asserted Fact：`fact_evidence_bindings` 中的 Evidence Reference。
- Edit Audit：actor、reason、created_at 和 command metadata。
- Rule Definition：创建该版本的 Modeling Item 及关联上下文。

`evidence_status` 与 `lineage_status` 分开：

- asserted 内容：`supported | missing`；
- derived 内容：`not_applicable`，另返回
  `dependency_evidence_status = supported | contains_missing | unknown`；
- `lineage_status = complete | partial | missing`。

有 rationale 或 Competency Question 但没有 Evidence 时，`supporting_context_status=present`，
`evidence_status` 仍为 `missing`。

### 4.5 Derivation

派生语句必须返回：

- producing Run、engine name/version 和运行时间；
- Rule Definition ID、Rule IRI 和不可变 version（规则路径）；
- Graph Set source signature、input graph revisions 和 consumed derived pointers；
- `proof_level = exact | coarse | unavailable`；
- exact 时返回 premise Statement Occurrences，并允许递归查询；
- coarse 时返回版本化输入快照和原因，不猜测具体 premise。

首版证明能力：

| 执行路径 | 证明级别 |
| --- | --- |
| Platform DSL | 当所有 `when` triple pattern 可由 matched binding 和输入 graph 解析时为 `exact`；否则 `coarse`。 |
| SPARQL CONSTRUCT | `coarse`，记录模板版本、bindings 和输入快照。 |
| OWL reasoning | reasoner 提供 proof 时可为 `exact`；当前 command runner 默认为 `coarse`。 |
| Workflow rule | 按实际执行器；复用 DSL 时与 DSL 相同。 |

## 5. PostgreSQL 持久化

新增 Alembic `0026_semantic_statement_lineage`。

### 5.1 `semantic_statement_occurrences`

| 字段 | 含义 |
| --- | --- |
| `id` | 64 位 deterministic occurrence hash，主键。 |
| `ontology_id` | Ontology 外键和隔离边界。 |
| `graph_set_id` | 写入时工作区，可空以兼容直接编辑。 |
| `statement_id` | 现有 quad hash，索引。 |
| `subject_iri` / `predicate_iri` | RDF IRI。 |
| `object_ntriples` | 规范化 object term。 |
| `graph_iri` | 实际 named graph。 |
| `graph_revision` | 该 occurrence 生效的图修订。 |
| `assertion_kind` | `asserted | owl_inferred | construct_derived | rule_derived | workflow_derived`。 |
| `status` | `active | invalidated`。 |
| `invalidated_revision` | 删除或替换发生的图修订，可空。 |
| `invalidated_by_audit_id` | 使其失效的 Edit Audit，可空。 |
| `created_at` / `invalidated_at` | 生命周期时间。 |

唯一约束为 `(statement_id, graph_revision)`。`ontology_id`、`statement_id`、`subject_iri`、
`graph_iri` 和 `status` 建索引。

### 5.2 `semantic_statement_origins`

- `id` UUID；
- `statement_occurrence_id` 外键；
- `origin_kind`；
- `origin_id`；
- `origin_metadata` JSONB，只保存无法从权威表读取的稳定摘要；
- 唯一键 `(statement_occurrence_id, origin_kind, origin_id)`。

异构 Origin 不建立伪外键；Lineage Service 必须按 Ontology/Project 重新校验被引用对象作用域。

### 5.3 `semantic_statement_premises`

- `derived_occurrence_id`；
- `premise_occurrence_id`；
- `proof_kind`，首版只持久化 `exact`；
- 唯一键 `(derived_occurrence_id, premise_occurrence_id)`。

coarse 输入快照继续保存在 Run metadata，不生成猜测性 premise rows。

## 6. 写入路径

### 6.1 Canonical 与直接编辑

新增 `SemanticLineageRecorder`，在 RDF 写入成功、图 revision bump 完成后、PostgreSQL commit
之前调用：

1. 对 delete quad 将最新 active occurrence 标记为 invalidated；
2. 对 insert quad 按 bump 后 revision 创建 occurrence；
3. 创建 `edit_audit` Origin；
4. 对 R-004 传入的 item effect map 增加所有对应 `modeling_item` Origins；
5. 使用唯一键和 deterministic ID 保证恢复重放幂等。

R-004 的 operation plan 已保存每个 Item 的 compiled command。执行阶段按 Item delta 建立
`quad -> modeling_item_ids` 映射；只记录最终 applied Item。相同 quad 由多个兼容 Item 产生时保留
全部 Origin。

Rule-only Modeling Item 不产生 Statement Occurrence；查询 `target_type=rule` 时从当前/历史
Rule Definition、Modeling Item result 和 Audit 组合返回 Definition Lineage Item。

### 6.2 Reasoning 与 Rule Run

成功写入 result graph 后、Run commit 前：

- 为每个输出 statement 创建 revision `1` occurrence；
- 创建 `reasoning_run` 或 `rule_run` Origin；
- Platform DSL 额外投影 `?g`，按 `binding_index` 和 `when` patterns 解析 exact premises；
- 若某个 premise 没有已有 occurrence，按运行时输入 revision 创建 `legacy_unknown` occurrence，
  并使整条 lineage 为 `partial`；
- CONSTRUCT/OWL 当前只记录 Run input snapshot，不创建 premise edge；
- Run 失败或未写入结果图时不创建输出 occurrence。

### 6.3 历史兼容

迁移不扫描 Oxigraph。查询当前 RDF 语句但找不到 occurrence 时，服务返回一个只读合成的
`legacy_unknown` Lineage Item，使用当前 graph revision 并标记 `lineage_status=partial`、
`warning=legacy_lineage_unavailable`。后续更新或派生运行会正常持久化新的 occurrence。

## 7. 查询服务与协议

新增 `OntologyLineageService.get_lineage(...)`，由 REST 和 MCP 共用。

### 7.1 REST

```text
GET /api/ontologies/{ontology_id}/lineage
    ?target_type=statement|resource|rule
    &target_id=<opaque-id-or-iri>
    &include_history=false
    &max_depth=3
    &limit=100
```

约束：

- `max_depth` 为 `0..5`；
- `limit` 为 `1..200`；
- exact premise 递归遇到重复 occurrence 时返回引用，不重复展开；
- 达到深度或节点上限时返回 `truncated=true` 和稳定 warning；
- Ontology 不存在或 target 不属于该 Ontology 时返回 `404`；
- 不接受 graph IRI 或 Graph Set ID 覆盖。

响应骨架：

```json
{
  "ontology_id": "ontology-id",
  "target": {"type": "statement", "id": "statement-id"},
  "lineage_status": "complete",
  "evidence_status": "not_applicable",
  "dependency_evidence_status": "contains_missing",
  "items": [
    {
      "item_kind": "statement",
      "statement_id": "...",
      "occurrence_id": "...",
      "statement": {
        "subject": "...",
        "predicate": "...",
        "object": "..."
      },
      "graph_revision": 3,
      "assertion_kind": "rule_derived",
      "status": "active",
      "origins": [],
      "supporting_context": {
        "evidence_references": [],
        "rationales": [],
        "competency_questions": [],
        "edit_audits": []
      },
      "derivation": {
        "proof_level": "exact",
        "run": {},
        "definition": {},
        "premises": []
      },
      "staleness": {"is_stale": false, "reason": null}
    }
  ],
  "warnings": [],
  "truncated": false
}
```

`graph_iri` 只放在 `technical_trace` 中，普通业务摘要不依赖它。API 可返回技术跟踪信息，但前端
不得把原始 graph IRI 当作业务来源名称展示。

### 7.2 MCP

新增：

```text
get_ontology_lineage(
  ontology_id,
  target_type,
  target_id,
  include_history=false,
  max_depth=3,
  limit=100
)
```

工具只返回平台记录的结构化上下文，不调用 LLM 解释结论。现有
`inspect_semantic_statement_provenance` 保留兼容注册，但改为委托统一服务并返回
`deprecated=true`；新调用方必须使用 `get_ontology_lineage`。

### 7.3 查询状态

- `lineage_status=complete`：asserted 语句有可信 Origin；派生语句还有满足执行器能力的 Run 和
  proof 信息。
- `lineage_status=partial`：存在 Run/Audit/legacy origin，但精确前提或历史来源不可得。
- `lineage_status=missing`：目标存在但没有可信来源记录。
- target 不存在不是 `missing`，而是 `404`。

## 8. 安全与权限接缝

R-005 不实现 R-008，但所有服务入口必须保留 `authorize_read(ontology_id, actor)` 接缝；当前
行为与其他 Ontology 读接口一致。服务必须先从 Ontology 推导 Project，再过滤 Evidence、Batch、
Audit、Rule 和 Run，不能因为调用方知道 ID 而跨项目读取 Evidence excerpt。

MCP/REST 响应不得返回 Lease token、凭据、未作用于当前 Project 的 Evidence 或原始外部文档。

## 9. 验收标准

1. R-004 创建带 Evidence 的 Class/Fact 后，可分别按 resource IRI 和 statement ID 查询到
   Modeling Item、Evidence Reference、rationale/CQ（若提供）和 Edit Audit。
2. 无 Evidence 的 asserted 内容允许写入；查询明确返回 `evidence_status=missing`，不会构造伪
   Evidence。
3. 人工或 canonical 编辑至少返回 actor、time、reason、Audit 和具体 Statement Occurrence。
4. Platform DSL 派生语句返回 Rule Definition version、Rule Run 和 exact premise chain；递归链
   遇到缺失证据时返回 `dependency_evidence_status=contains_missing`。
5. SPARQL CONSTRUCT 和当前 OWL runner 至少返回 Run、定义/引擎版本、输入 revisions、
   `proof_level=coarse`；不得绑定伪造的文档证据或前提语句。
6. 删除和重新插入同一 quad 产生不同 occurrence；默认只返回当前 occurrence，历史查询返回完整
   lifecycle 和失效 Audit。
7. R-004 幂等重试和向前恢复不重复创建 occurrence、origin 或 premise。
8. 迁移前内容仍可查询，结果明确为 `partial` 和 `legacy_lineage_unavailable`。
9. REST 与 MCP 复用同一服务、Ontology scope、深度/数量上限和状态语义。
10. 跨 Ontology/Project target 或 Evidence 不可见；不存在 target 返回稳定 `404/not_found`。
11. Alembic 升级、全量 backend pytest、MCP registry、真实 PostgreSQL/Oxigraph 定向验收、服务
    重启及 health 检查全部通过。

## 10. 实现顺序

1. Migration、SQLAlchemy models、statement/occurrence identity helpers。
2. Lineage recorder、repository 和查询服务。
3. canonical direct edit 与 R-004 item effect 接线。
4. Rule/Reasoning Run 输出与 premise 接线。
5. REST、MCP 和兼容工具适配。
6. 定向测试、全量测试、运行时验收和文档同步。
