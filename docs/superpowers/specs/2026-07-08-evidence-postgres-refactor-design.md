# Evidence 存储迁移至 Postgres（fact_id 级）

**Date:** 2026-07-08
**Status:** Approved (方案 B，激进重构)
**Owner:** Agent

## 背景与动机

当前 evidence 系统存在以下问题：

1. **evidence 存储在 RDF 三元组库**，每个 chunk 产生 6 条三元组（`prov:wasDerivedFrom` + 5 个字面量），文本被冗余存为 `<chunk> tag:text "原文..."`，对 RDF 来说不自然，查询开销大。
2. **missing_evidence 是显式标记而非派生**：`op:evidenceStatus "missing_evidence"` 字面量需要命令路径主动写入（`create_entity` / `create_relation` 默认打标），而不是基于 `evidence_bindings` 是否为空自动判定。导致 asserted tab 里"无 evidence 但未标记"的 fact 不会被 missing_evidence tab 收录。
3. **两套 evidence 表达并存，互不通查**：
   - `prov:wasDerivedFrom` + chunk 字面量（被 `_attach_evidence_bindings` SPARQL 读取）
   - `op:evidenceStatus` + `op:evidence` + reified `op:FactClaim`（通过 `compile_submit_assertion` 写入，但全代码库无读路径）
4. **fact_id 算法在读写两侧不一致**：`read_model._fact_id` 用 4-tuple `(s,p,o,g)`，`command_compiler._fact_id_for` 用 3-tuple `(s,p,o)`，同一条 fact 在写入和读取算出的 id 不同。
5. **PG 层已有 `evidence_chunks` 表，但语义不同**：现有表是文档解析切片（外键到 `evidence_artifacts`），与"fact 级证据绑定"是不同概念。

## 目标

- evidence 存储完全迁移到 Postgres，RDF 三元组库不再写任何 evidence 相关三元组
- 按 fact_id 级（sha256(s,p,o,g)）关联，每条三元组 (s,p,o) 拥有独立证据列表
- missing_evidence 成为派生状态：`SELECT count(*) FROM fact_evidence_bindings WHERE fact_id=?` = 0 即 missing
- 统一 fact_id 算法（4-tuple），消除读写侧不一致
- 清理所有相关死代码（submit_assertion、update_evidence_status、reified FactClaim 模型、op:evidenceStatus 谓词、prov:wasDerivedFrom + chunk 字面量）

## 非目标

- 不迁移现有 RDF 中的 evidence 数据（按用户决策，开发期重构）
- 不改 `evidence_artifacts` / `evidence_chunks` 这两张表的语义（仍是文档解析切片）
- 不引入缓存表（如 fact_registry）—— missing_evidence 实时算，FactAuditPage 分页查询性能足够
- 不改 review_assertion / 审计 / 推理 / 验证 / 规则执行的核心业务逻辑

## 架构

### 数据流

```
[用户在 FactAuditPage 选 PDF chunk 绑定到某 fact]
            │
            ▼
POST /api/semantic/graph-sets/{gs}/fact-evidence
{ fact_id, chunk_id (或 text), document_id, char_range, actor, reason }
            │
            ▼
compile_bind_fact_evidence (command_compiler.py)
  → 计算 fact_id（若调用方未提供）
  → 不写 RDF
  → FactEvidenceBindingRepository.create(fact_id, chunk_id, text, ...)
            │
            ▼
[PG fact_evidence_bindings 表落库]

[FactAuditPage 拉取 fact 列表]
            │
            ▼
GET /api/semantic/.../read-models/fact-audit-queue?kind=...
            │
            ▼
_compose_fact_audit_queue (read_model.py)
  → SPARQL 取 asserted_data 中所有 fact 三元组
  → 批量 SELECT * FROM fact_evidence_bindings WHERE fact_id IN (...)
  → 每个 fact 装上 evidence_bindings 数组
  → evidence_status = "missing_evidence" if len(bindings) == 0 else "with_evidence"
            │
            ▼
[前端按 evidence_status 渲染 missing 标签]
```

### Postgres schema

**新增表 `fact_evidence_bindings`**（与现有 `evidence_chunks` 文档解析切片解耦）：

```sql
CREATE TABLE fact_evidence_bindings (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id             TEXT        NOT NULL,  -- sha256(s,p,o,g)，应用层计算
    subject_iri         TEXT        NOT NULL,
    predicate_iri       TEXT        NOT NULL,
    object_value        TEXT        NOT NULL,  -- N-Triples 序列化
    graph_iri           TEXT        NOT NULL,

    -- 绑定来源（两种二选一）
    chunk_id            UUID        REFERENCES evidence_chunks(id) ON DELETE SET NULL,
    evidence_artifact_id UUID       REFERENCES evidence_artifacts(id) ON DELETE SET NULL,

    -- 冗余字段（无论 chunk_id 是否存在都填，避免 join）
    document_filename   TEXT,
    sequence            INT,
    char_start          INT,
    char_end            INT,
    text                TEXT        NOT NULL,

    -- 治理字段
    actor               TEXT,
    reason              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fact_evidence_bindings_fact_id  ON fact_evidence_bindings(fact_id);
CREATE INDEX idx_fact_evidence_bindings_subject  ON fact_evidence_bindings(subject_iri);
CREATE INDEX idx_fact_evidence_bindings_chunk    ON fact_evidence_bindings(chunk_id) WHERE chunk_id IS NOT NULL;
```

**字段决策依据**：
- `chunk_id` / `evidence_artifact_id` 可空：用户可能直接粘贴一段文本作为证据（无 PDF chunk 引用）
- `text` 必填且冗余：避免每次查询都要 join `evidence_chunks`
- 同时存 `subject_iri/predicate_iri/object_value/graph_iri`：方便从 `fact_id` 反查 fact 详情（无需重算）
- `chunk_id` 用 `ON DELETE SET NULL`：文档被删时绑定保留但失去引用，证据文本仍在 `text` 字段

### fact_id 算法标准化

提取到公共 util `backend/app/services/fact_id.py`：

```python
import hashlib

def compute_fact_id(
    subject_iri: str,
    predicate_iri: str,
    object_ntriples: str,  # 已规范化的 N-Triples 对象（IRI 包 <>, 字面量带引号+datatype）
    graph_iri: str,
) -> str:
    canonical = f"<{subject_iri}> <{predicate_iri}> {object_ntriples} <{graph_iri}>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

读写两侧都改调用这个函数。删除 `command_compiler._fact_id_for` 和 `read_model._fact_id` 两个旧实现。

**graph_iri 维度的影响**：同一条三元组 (s,p,o) 在不同 graph 里 fact_id 不同。这是有意为之 —— 不同 graph_set 的相同三元组是不同的 fact。

## 组件改造

### 后端命令编译器（`backend/app/services/semantic_command_compiler.py`）

**删除**：
- `compile_submit_assertion` (L240-286) + 注册 (L1606)
- `compile_update_evidence_status` (L289-320) + 注册 (L1607)
- `compile_bind_fact_evidence_text` (L399-443) + 注册 (L1610)
- `compile_unbind_fact_evidence` (L446-476) + 注册 (L1611)
- `compile_create_entity` 中默认打 missing_evidence 的两行 (L1000-1004)
- `compile_create_relation` 中默认打 missing_evidence 的两行 (L1140-1145)
- `_fact_id_for` / `_canonical_ntriples` (L1458-1473) → 改为引用新 util

**新增**：
- `compile_bind_fact_evidence`：接收 fact_id（或 s,p,o,g 四元组自动算）+ chunk_id 或 text，写入 PG（通过 repository）
- `compile_unbind_fact_evidence`：接收 binding_id 或 (fact_id, chunk_id)，从 PG 删除

**修改**：
- `compile_create_entity` / `compile_create_relation`：不再写 op:evidenceStatus 三元组
- `compile_update_fact` / `compile_delete_fact` / `compile_review_assertion`：fact_id 计算改用新 util（4-tuple）

### 后端服务层

**整文件删除**：`backend/app/services/semantic_missing_evidence.py`

**修改**（移除 missing_evidence_service 注入和 derived_from_missing_evidence 写入）：
- `backend/app/services/semantic_reasoning.py` (L34, 52, 62, 130-150, 179, 196, 266-267, 333, 345)
- `backend/app/services/semantic_validation.py` (L30, 53, 126-145, 164-165, 189-195, 294-295)
- `backend/app/services/semantic_rule_execution.py` (L39, 70-79, 153-159, 171, 190, 244-282, 301, 379-422, 462-483, 601-665, 799-843) —— 注意 L660-665 是写 derived_from_missing_evidence 三元组的，删除
- `backend/app/services/semantic_build_overview.py` (L24, 97, 133-137) —— `missing_evidence_count` 改为 PG COUNT 查询
- `backend/app/services/semantic_migration.py` (L685-695) —— `fact_claim` 分支改为 skip + warning log
- `backend/app/services/semantic.py` (L752-793) —— `_missing_evidence_write_warnings` / `_missing_evidence_read_warnings` 整个保护机制删除

### 后端读取层（`backend/app/services/semantic_read_model.py`）

**删除**：
- `_attach_evidence_bindings` (L1412-1445)
- `_EVIDENCE_BINDING_SPARQL` (L1447-1461)
- `_fetch_evidence_bindings` (L1463-1500+)

**修改**：
- `_decorate_fact_row` (L1115-1186)：`evidence_status` 改为派生 —— 接收预先批量查好的 `bindings_count` 字典，0 即 missing
- `_compose_fact_audit_queue` (L956-1090)：
  - 删除 `_FACT_KINDS` 中的 `"missing_evidence"`（L956）
  - SPARQL 不再 `OPTIONAL { ?subject op:evidenceStatus ?evidence_status }`
  - 三类 fact 都改为：SPARQL 取 fact → 批量查 PG → 装饰 evidence_bindings 数组 + evidence_status 派生
  - `kind=missing_evidence` 改为：SPARQL 取所有 asserted fact → 应用层反 JOIN（fact_id NOT IN PG bindings）
- `_missing_evidence_count` (L529-549)：改为 `SELECT COUNT(DISTINCT fact_id) FROM (...) LEFT JOIN fact_evidence_bindings ...` 或更直接的：先 SPARQL 取所有 fact_id 集合 A，PG 取所有有 binding 的 fact_id 集合 B，count = |A - B|

### 后端 SPARQL 模板（`backend/app/services/semantic_sparql_templates.py`）

**修改**：
- `fact-audit-queue` 模板 (L406-442)：删除 `OPTIONAL { ?subject op:evidenceStatus ?evidence_status }` (L437)
- `missing-evidence-list` 模板 (L444-479)：**整段删除**（被新查询策略替代）
- L123 的 `?s op:evidenceStatus "missing_evidence"` 子句删除
- L272, L286 等模板里所有 `op:evidenceStatus` 引用清理
- `ReadModelTemplate.evidence_status` 字段（默认 "not_applicable"）：从 schema 中移除

### 后端 API 层

**删除**：
- `backend/app/api/semantic.py` 的 `/graph-sets/{id}/missing-evidence` 路由 (L939-970)
- `_missing_evidence_service` 工厂和 import (L86, L207, L1642)
- `backend/app/api/schemas.py:915-916` 的 `submit_assertion` / `update_evidence_status` 从 fallback 列表移除
- 编辑 API 中的 `evidence_status` 参数（schemas.py:261, 318；semantic.py 相应处理）

**新增 API**（`backend/app/api/semantic.py` 或新建 `backend/app/api/fact_evidence.py`）：
- `POST /api/semantic/graph-sets/{gs}/fact-evidence` — 创建绑定
- `DELETE /api/semantic/graph-sets/{gs}/fact-evidence/{binding_id}` — 删除绑定
- `GET /api/semantic/graph-sets/{gs}/facts/{fact_id}/evidence` — 单 fact 查询（可选，前端可能不需要）
- `GET /api/semantic/graph-sets/{gs}/missing-evidence-facts?limit=...` — missing fact_id 列表 + count（替代旧 summary 端点，前端 FactAuditPage 的 missing_evidence tab 用）

### MCP 工具

**删除**（`backend/app/mcp/tools/semantic.py`）：
- `inspect_semantic_missing_evidence` 工具 (L17, L102, L322-325)
- `_missing_evidence_summary` 实现 (L511-522)

**新增**（可选，延后）：
- `inspect_fact_evidence(fact_id)` — 查询单个 fact 的所有绑定
- `list_missing_evidence_facts(graph_set_id, limit)` — 列出缺失证据的 fact

### Repository 层

新增 `backend/app/repositories/fact_evidence_repository.py`：

```python
class FactEvidenceBindingRepository:
    def __init__(self, session: Session): ...
    def create(self, *, fact_id, subject_iri, predicate_iri, object_value, graph_iri,
               chunk_id=None, evidence_artifact_id=None, document_filename=None,
               sequence=None, char_start=None, char_end=None, text, actor=None,
               reason=None) -> FactEvidenceBindingModel: ...
    def delete(self, binding_id: str) -> bool: ...
    def list_by_fact_ids(self, fact_ids: list[str]) -> dict[str, list[dict]]: ...
    def list_by_fact_id(self, fact_id: str) -> list[dict]: ...
    def count_facts_with_bindings(self, fact_ids: list[str]) -> set[str]: ...  # 返回有 binding 的 fact_id 集合
```

新增 model `backend/app/repositories/models.py`：`FactEvidenceBindingModel`

新增 Alembic 迁移：`backend/migrations/versions/0013_fact_evidence_bindings.py`，建表 + 索引。

### 前端

**删除**：
- `frontend/src/components/semantic/EvidenceBindingPanel.tsx`（status 选择器 + evidence IDs 输入是 RDF 写路径）
- `frontend/src/types.ts`：`SemanticEditEvidenceStatus` (L837)、`SemanticMissingEvidenceSummary` (L731-736)、`SemanticStatementItem.evidence_status` (L744)
- `frontend/src/semanticApi.ts`：`getMissingEvidenceSummary` (L383-387)、编辑 API 的 `evidenceStatus` 参数 (L168, L182, L197, L211)
- `frontend/src/i18n/zh.ts` L910 的"Statements written with missing evidence..."警示句

**修改**：
- `frontend/src/pages/FactAuditPage.tsx`：
  - 命令 payload 改用 `fact_id`（替代 `subject_iri`）
  - 命令名改为新 `bind_fact_evidence` / `unbind_fact_evidence`
  - L481 missing 标签改为派生：`(selected.evidence_bindings?.length ?? 0) === 0`
  - missing_evidence tab 仍存在，查询走新 `getMissingEvidenceFacts` API
- `frontend/src/components/semantic/EvidenceExplorerPanel.tsx`：missing tag 改为 length===0 派生
- `frontend/src/pages/GraphSetPage.tsx` (L95)：删除 `getMissingEvidenceSummary` 调用，改为新的 `getMissingEvidenceFacts` 或直接展示 count
- `frontend/src/pages/GraphGovernancePage.tsx` (L342, L363)：保留派生 count，删除字面量引用
- `frontend/src/pages/SemanticEditWorkbenchPage.tsx` / `SemanticImportExportPage.tsx`：删除 `SemanticEditEvidenceStatus` 相关 UI（status 选择器）
- `frontend/src/components/semantic/badges.tsx`：移除 `AssertionKind` 中 `missing_evidence`，简化 `EvidenceStatusBadge`

**新增**：
- `frontend/src/components/semantic/EvidenceChunkPicker.tsx`：PDF 文档树 + chunk 搜索 + 选片段 UI（接入现有 `listPdfDocuments` / `searchPdfChunks` 或新建 API）
- `frontend/src/semanticApi.ts`：新客户端 `bindFactEvidence` / `unbindFactEvidence` / `getMissingEvidenceFacts` / `getFactEvidenceBindings`

### 一次性清理脚本

新增 `backend/scripts/cleanup_legacy_evidence_rdf.py`：

```
对每个 graph_set 的 asserted_data 图：
  1. SPARQL CONSTRUCT 删除所有 ?s prov:wasDerivedFrom ?o 三元组
  2. SPARQL CONSTRUCT 删除所有 chunk IRI 的 5 个字面量三元组
  3. SPARQL CONSTRUCT 删除所有 ?s op:evidenceStatus ?o 三元组
  4. 删除所有 op:FactClaim 实例及其属性三元组
```

用户在部署时手动跑一次。

## 错误处理

- **fact_id 不匹配**：若用户传入的 fact_id 与 (s,p,o,g) 算出的不一致，bind 命令拒绝并返回 400
- **chunk_id 不存在**：绑定前校验 chunk_id 在 `evidence_chunks` 表中存在，否则 400
- **跨 graph_set 误绑**：fact_id 已包含 graph_iri，自然区分；前端 UI 限制只能绑定当前 graph_set 内的 fact
- **删除 chunk 后**：`ON DELETE SET NULL` 保护，绑定保留但 chunk_id 变空，`text` 字段仍在
- **重复绑定**：允许同一 fact 绑定多个 chunk，每个生成独立 binding_id

## 测试策略

### 后端

**新增**：
- `test_fact_evidence_repository.py` — repository CRUD
- `test_fact_id_util.py` — 4-tuple 算法稳定性
- `test_compile_bind_fact_evidence.py` — 命令编译器
- `test_fact_evidence_api.py` — REST 端点
- `test_read_model_evidence_decoration.py` — 派生 evidence_status、批量查 PG

**修改**：
- `test_semantic_command_compiler_stage2.py` — 移除 submit_assertion / update_evidence_status / bind/unbind 旧测试；create_entity/relation 不再断言 op:evidenceStatus 三元组
- `test_semantic_read_model*.py` — evidence_bindings 改为 PG mock；missing_evidence_count 改为 PG count
- `test_semantic_sparql_templates.py` — 删除 evidence_status 投影断言
- `test_semantic_migration_service.py` — fact_claim → submit_assertion 路径改为 skip 行为
- `test_semantic_phase5.py` / `test_semantic_stage4_e2e.py` — missing_evidence 端到端改写
- `test_semantic_reasoning.py` / `test_semantic_validation.py` — missing_evidence_dependencies 字段断言移除或改为空
- `test_evidence_rest_surface.py` — evidence API surface 更新

### 前端

- `FactAuditPage.test.tsx` — 绑定 chunk 流程、missing 派生
- `EvidenceChunkPicker.test.tsx` — 新组件
- 其他页面快照测试可能需要更新

### 端到端

- 完整跑一遍 FactAuditPage 流程：创建实体 → 看到 missing → 选 PDF chunk 绑定 → missing 标签消失
- 重启服务，确认 evidence 持久化在 PG，RDF 库不再有 evidence 三元组

## 实施顺序（高层）

1. **基础设施**：新增 `fact_id.py` util、PG 表和迁移、`FactEvidenceBindingRepository`、`FactEvidenceBindingModel`
2. **写入路径**：新命令编译器 `compile_bind/unbind_fact_evidence`、API 端点、Repository 集成
3. **读取路径**：重写 `_attach_evidence_bindings` 为 PG 批量查、装饰器派生、missing_evidence tab 反 JOIN
4. **删除旧写入**：移除 4 个旧命令、create_entity/relation 默认标记、SPARQL 模板的 evidence_status 投影
5. **服务层清理**：删除 `semantic_missing_evidence.py`、清理 reasoning/validation/rule_execution/build_overview
6. **API/MCP 清理**：删除 `/missing-evidence` 路由、`inspect_semantic_missing_evidence` 工具、编辑 API 的 `evidence_status` 参数
7. **前端 UI**：删除 `EvidenceBindingPanel`、修改 FactAuditPage 命令调用、新增 `EvidenceChunkPicker`、调整 badges
8. **测试**：跑全测试套件，修改/删除/新增
9. **清理脚本**：`cleanup_legacy_evidence_rdf.py`
10. **文档**：更新 ADR、`docs/semantic/` 相关章节、`CONTEXT.md`

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 老数据丢失 | 用户已知接受（开发期重构）。生产部署前需另行评估 |
| 测试套件大改 | 高层实施顺序中第 8 步独立处理，预计 1/3 测试用例受影响 |
| migration 服务异常 | semantic_migration.py 的 fact_claim 分支改为 skip + log，不影响其他迁移 |
| 前端 PDF chunk 选择 UI 复杂 | 可先实现 MVP（直接粘贴 text + document_id），后续迭代加 chunk 选择器 |
| rule_execution 失去 derived_from_missing_evidence 标记 | 这个语义在新模型下不存在（missing 是派生状态，无独立标记），删除即可 |

## 验收标准

1. RDF 三元组库中**没有任何** evidence 相关三元组（无 `op:evidenceStatus`、无 `prov:wasDerivedFrom`、无 chunk 字面量、无 `op:FactClaim`）
2. 创建实体/关系不再产生 evidence 标记
3. 用户可在 FactAuditPage 选 PDF chunk 绑定到具体 fact
4. missing_evidence tab 自动展示所有无 binding 的 fact（无需手动标记）
5. 解绑最后一个 evidence 后，fact 自动出现在 missing_evidence tab
6. 全测试套件通过
7. 老数据清理脚本运行后 RDF 库干净

## 文件影响清单（汇总）

**新增**：
- `backend/app/services/fact_id.py`
- `backend/app/repositories/fact_evidence_repository.py`
- `backend/app/api/fact_evidence.py`
- `backend/app/repositories/models.py` 新增 `FactEvidenceBindingModel`
- `backend/migrations/versions/0013_fact_evidence_bindings.py`
- `backend/scripts/cleanup_legacy_evidence_rdf.py`
- `frontend/src/components/semantic/EvidenceChunkPicker.tsx`

**删除**：
- `backend/app/services/semantic_missing_evidence.py`

**修改**：约 25 个文件（详见"组件改造"各节）
