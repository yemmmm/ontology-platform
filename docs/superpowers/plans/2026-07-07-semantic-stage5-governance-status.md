# Semantic Stage 5 — Governance Status

- **Date:** 2026-07-07
- **Spec:** `docs/superpowers/specs/2026-07-07-semantic-stage5-governance-design.md`
- **Plan:** `docs/superpowers/plans/2026-07-07-semantic-stage5-governance.md`
- **Inventory:** `docs/semantic/functional-semantic-load-inventory.md` Stage 5
- **Status:** 已实施并通过功能测试

## 0. 当前完成状态（2026-07-07 更新）

Stage 5 Governance 已完成本轮交付：

- 后端补齐三类 run history list 端点：
  `GET /api/semantic/validation-runs`、`GET /api/semantic/reasoning-runs`、
  `GET /api/semantic/rule-runs`，支持 `graph_set_id`、`kind`、`limit`、`offset`，
  返回 `{items, summary{total, stale_count, superseded_count}}`。
- `/api/semantic/projections/status` 返回 `stale_projection_count`。
- named graph registry 返回 `statement_count` 与 `latest_audit_at`。
- `/api/semantic/status.derived` 返回 `stale_derived_count`。
- RDF parse failure 透传结构化 `detail.message/line/column`。
- 前端 DTO/API 已同步 Stage 5 字段和 run list helper。
- `GraphGovernancePage` 显示 stale projections 与 latest graph deltas。
- `NamedGraphsPage` 显示 statement count、latest audit、freshness，并支持 current/stale 过滤。
- `SemanticRunsPage` 从 ID-only 查询增强为 run history table + detail panel。
- Playwright governance mocks 覆盖 projection status、run list、OWL consistency read model、graph set run triggers。

已执行验证：

```bash
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test semantic-governance.spec.ts
```

结果：backend `403 passed`；frontend build 通过；governance Playwright `6 passed`。

## 1. 任务背景

用户要求完成 `docs/semantic/functional-semantic-load-inventory.md` 中 **Stage 5 —
Governance** 的改造。Stage 5 不是从零构建，而是补完 Phase 8 §1–§9 已设计但未交付的
governance 细节，让六个 governance 页面（GraphGovernancePage、NamedGraphsPage、
GraphSetPage、SemanticEditWorkbenchPage、SemanticRunsPage、SemanticImportExportPage）成
为"在 graph-native 化的 Stages 1–4 之上的专家与审计视图"。

用户明确指示：使用 subagent 减少主上下文消耗；有疑问按推荐架构实施，不咨询用户。

## 2. 已完成的工作

### 2.1 范围调研（已完成）

通过两个 Explore subagent 完成了：

- **Stage 5 scope research** — 确认六个 governance 页面均已存在（Phase 8 已交付），
  后端 `/api/semantic/*` 路由全部 full 实现无 stub，真正的工作量在补完 Phase 8 §1–§9
  列出的"必须显示/必须提供"清单中尚未交付的项。
- **Phase 8 + backend gap audit** — 提取了 Phase 8 文档对六个页面的精确要求清单，
  审计后端能力的就绪状态，识别出 5 项 backend 缺口与按页面分组的 frontend 缺口。

### 2.2 设计文档（已完成）

文件：`docs/superpowers/specs/2026-07-07-semantic-stage5-governance-design.md`（13 节）

包含：
- §1 Goal / Non-Goals
- §2 Locked-In Decisions（11 条决策）
- §3 Shared Foundations（Stages 1–4 已具备的能力）
- §4 Backend Changes（5 项 + 测试要求）
- §5 Frontend Rebuilds（按 6 页面分章节 + i18n + Routing）
- §6 Error Handling
- §7 Testing Strategy（backend + frontend + 12 个 Playwright case）
- §8 Migration Strategy（additive only）
- §9 Happy-Path E2E Plan（10 步）
- §10 Implementation Order & Subagent Decomposition（Phase A–G）
- §11 Open Questions

### 2.3 实施计划（已完成）

文件：`docs/superpowers/plans/2026-07-07-semantic-stage5-governance.md`（Phase A–G）

包含每个 task 的具体文件路径、改动点、commit 信息模板，以及 spec → plan 的覆盖
映射表。

### 2.4 任务追踪（已完成）

在主 agent 的 TaskCreate 系统中创建了 6 个任务：

| ID | Task | Status |
| --- | --- | --- |
| #1 | Stage 5 spec & plan docs | completed |
| #2 | Backend gaps: list runs + projection status + graph registry fields + parse error structure | completed |
| #3 | GraphGovernancePage + NamedGraphsPage frontend rebuild | completed |
| #4 | GraphSetPage + SemanticRunsPage + EditWorkbench + ImportExport frontend rebuild | completed |
| #5 | i18n + Playwright governance coverage | completed |
| #6 | Verify: backend tests + frontend typecheck + Playwright + commit | completed |

## 3. 待完成的工作（按 Phase 拆分）

### Phase A — Backend extensions（单 subagent，未开始）

5 个 task：

- A1：三类 run 的 list 端点（`GET /{validation,reasoning,rule}-runs`）
- A2：`/projections/status` 加 `stale_projection_count: int`
- A3：`SemanticGraphRegistryRead` 加 `statement_count`、`latest_audit_at`
- A4：`SemanticGovernanceStatusResponse.derived` 加 `stale_derived_count`
- A5：`_format_parse_error` 结构化（line/column）+ `SemanticEditPreviewResponse.parse_error`

涉及文件：
- `backend/app/api/schemas.py`
- `backend/app/api/semantic.py`
- `backend/app/services/semantic.py`
- `backend/app/services/semantic_graph_registry_service.py`（或等价位置）
- `backend/app/repositories/semantic_*_run_repository.py`（三个）

### Phase B — Backend tests（单 subagent，依赖 A）

7 个测试文件（详见 plan Task B1）。

### Phase C — Frontend pages 1–2（两并行 subagent，依赖 A）

- C1：GraphGovernancePage（stale projection tile、locked/editable 拆分、latest graph
  deltas section）
- C2：NamedGraphsPage（4 新列、3 新过滤器、2 新行操作、CopyableIri 组件）

### Phase D — Frontend pages 3–4（两并行 subagent，依赖 A）

- D1：GraphSetPage（QueryScopeSegmentedControl、SPARQL prefilled 链接）
- D2：SemanticRunsPage（重大改造：RunHistoryTable + 详情面板）

### Phase E — Frontend pages 5–6（两并行 subagent，依赖 A）

- E1：SemanticEditWorkbenchPage（ParseErrorBanner、EvidenceBindingPanel、
  AuditRecordShapeCard、Apply gating、reasoning impact 选项）
- E2：SemanticImportExportPage（5-step wizard + SPARQL prefilled）

### Phase F — i18n + Playwright（单 subagent，依赖 C–E）

- F1：`frontend/src/i18n/zh.ts` 加 ~50 个 governance 缺失 key
- F2：`frontend/tests/semantic-governance.spec.ts` 加 12 个 Playwright case

### Phase G — Verify + status flip（主 agent）

- G1：`cd backend && uv run pytest tests/semantic/`
- G2：`cd frontend && npx tsc --noEmit`
- G3：`cd frontend && npx playwright test semantic-governance.spec.ts`
- G4：spec §0 status 从 `Proposed` 改为 `Implemented`
- G5：最终 commit

## 4. 关键决策摘要

| 主题 | 决策 |
| --- | --- |
| 整体定位 | 补完 Phase 8 验收要求，不重写、不加新顶级 stage、不复活 legacy 路由 |
| Backend | 5 项向后兼容的字段扩展 + 3 个新 list 端点；无 schema 迁移 |
| Run history | envelope `{items, summary{total, stale_count, superseded_count}}`，offset/limit 分页 |
| Parse error | rdflib 异常文本用 regex 抽 line/column，匹配不到时返回 None，保留 flat error 字段 |
| SPARQL prefilled | 纯前端实现，读 graph set members 生成 `FROM NAMED` 子句，无 backend 改动 |
| Import flow | 改造为 5-step wizard；保留 "Advanced: skip wizard" 入口 |
| i18n 约定 | 沿用 flat literal-English key 风格，加到现有 Phase 8 section 下 |
| Subagent 派发 | Phase A、B 串行；Phase C–E 各 2 个并行；F 单发；G 主 agent |

## 5. 当前停顿点

主 agent 已发出 Phase A backend subagent 的派发请求，但被用户中断用于生成本总结。
计划在用户确认后重新派发 Phase A subagent 继续。

## 6. 下一步行动

1. 重新派发 Phase A backend subagent，让其读 spec §4 + plan Phase A 后实施 A1–A5。
2. Phase A 完成后由主 agent 跑 `cd backend && uv run pytest tests/semantic/` 验证现有
   测试不退化，然后 commit。
3. 派发 Phase B backend tests subagent。
4. Phase B 完成后并行派发 Phase C、D、E（共 6 个 subagent）。
5. Phase F（i18n + Playwright）。
6. Phase G 主 agent verify + status flip + 最终 commit。

## 7. 风险与注意事项

- **Run history endpoint 性能**：`stale_count` 统计若按行遍历可能慢；plan 中已要求
  `limit` 上限 100 并文档化。
- **Parse error regex 覆盖面**：rdflib 不同版本错误格式不同；当前 regex 覆盖
  `at line N, column M` 和 `at offset N` 两种，其他格式退化为 flat message。
- **SPARQL prefilled**：必须使用 graph member IRIs 而非 graph set ID。
- **Playwright mock URL 一致性**：mock 路由必须与 `semanticApi.ts` 的实际 URL 完全
  一致，否则会绕过 mock 走真实 API。
- **Frontend DTO 同步**：Phase C–E 的 frontend subagent 必须先读 Phase A 的 schema
  diff 再写 types.ts，避免类型漂移。

## 8. 提交历史（待补）

实施开始后，预期提交序列：

```
feat(semantic): Stage 5 backend extensions ... (Stage 5 §4)
test(semantic): Stage 5 backend coverage (Stage 5 §4.6)
feat(frontend): Stage 5 GraphGovernancePage + NamedGraphsPage ... (Stage 5 §5.1-5.2)
feat(frontend): Stage 5 GraphSetPage + SemanticRunsPage ... (Stage 5 §5.3,5.5)
feat(frontend): Stage 5 EditWorkbench + ImportExport ... (Stage 5 §5.4,5.6)
i18n(frontend): add Stage 5 keys (zh) (Stage 5 §5.8)
test(frontend): add Stage 5 Playwright coverage (Stage 5 §7.3)
docs(semantic): Stage 5 spec and plan
```
