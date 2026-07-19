# R1.2-002 Project 与 Ontology 授权范围发现共享测试计划

- Requirement: `docs/requirements/requirements-v1.2.md` R1.2-002
- Design: `docs/delivery/designs/2026-07-19-r1-2-002-authorized-scope-discovery-design.md`
- Status: independent PASS (Round 2, 2026-07-19)
- Independent rounds: append below; do not replace prior rounds

## 完成门禁

- 后端聚焦测试与完整 `cd backend && uv run pytest` 全部通过。
- REST/MCP 对相同身份、筛选、分页返回一致的核心数据和排序。
- `cd frontend && npm run build` 与 `cd frontend && npx playwright test` 通过，用于确认工具目录和
  既有前端未回归；本需求无新增页面。
- `systemctl --user restart ontology-platform.service` 后服务 active，`8001/api/health` 与 `5173/`
  健康；公开 REST 和 MCP 实际调用通过。
- requirements、API、MCP、platform guide、设计结果与本计划测试轮次已同步。

## 确定性测试矩阵

| 类别 | 场景 | 预期 |
| --- | --- | --- |
| 成功 | 组织管理员无筛选遍历 | 分页覆盖全部授权 Project/Ontology，排序稳定，无重复遗漏，范围参数可直接复用。 |
| 成功 | Project 绑定 read key | 只返回绑定 Project 及子 Ontology，不出现其他 Project 的项、数量或错误细节。 |
| 筛选 | Project ID/名称命中 | ID 精确、名称 trim+casefold 包含；返回 Project 及全部授权 Ontology。 |
| 筛选 | Ontology ID/名称命中 | 返回 Ontology 及内嵌父 Project；不展开未命中的兄弟 Ontology。 |
| 筛选 | Project/Ontology 同时命中及重名 | 所有授权候选保留，`resource_type`/`matched_on` 明确，不自动选择。 |
| 筛选 | 描述、拼写、翻译或外国 ID | 不匹配；成功空集合，不泄漏外国资源。 |
| 筛选 | `queryable=true/false` | 只筛 Ontology；无匹配 Ontology 的 Project 不保留，false 项保留不可用原因。 |
| 就绪 | ready draft/active | queryable=true，返回非空 workspace_version；派生缺失/过期只形成公开告警。 |
| 就绪 | archived | 可发现但 queryable=false、ontology_archived；Project 查询排除，显式查询 scope_not_ready。 |
| 就绪 | workspace 损坏/缺失 | queryable=false、workspace_not_ready；不返回可伪装为有效的版本。 |
| 聚合 | complete/partial/unavailable/空 Project | 状态与完整子集合一致；partial 列明排除；unavailable 查询返回 scope_not_ready。 |
| 分页 | limit=1 全量续读 | `has_more`、`next_cursor`、`generated_at` 正确，Project/Ontology 都计入 limit。 |
| 分页 | 名称相同与相同创建时间 | ID tie-breaker 保证确定顺序。 |
| 分页 | cursor 换筛选或篡改 | invalid_cursor，不静默从第一页重启。 |
| 分页 | 两页之间新增/改名/删除 | 不承诺快照；无服务错误，最终语义查询重新校验当前范围。 |
| 失败 | 空白 query、非法 queryable、limit 边界 | 空白等同无筛选；非法值稳定失败；1/100 可用、0/101 拒绝。 |
| 授权 | 缺失/无效认证、缺 read scope | REST 分别为 401/403；MCP 返回对应稳定错误，不执行目录读取。 |
| 一致性 | REST/MCP 同一主体同一参数 | 核心 items、排序、状态、版本、原因一致，仅传输包装不同。 |
| 闭环 | 发现返回的 Project/Ontology query_scope | 可直接调用 Context Query 和 scoped SPARQL；当前授权/就绪/版本被重新校验。 |
| 回归 | 现有 CRUD、本体创建、Build Context、R-006 查询 | 原成功行为保持；不暴露 Graph Set，不混入 Build Context。 |

## 实现审查检查项

- 授权过滤发生在查询/匹配/计数之前，服务不先加载外国数据再从响应删除。
- cursor 是有版本、筛选绑定的 keyset cursor，不使用不稳定 offset，也不包含秘密。
- Project 聚合状态基于完整授权子集合，不被当前页或筛选结果扭曲。
- 目录和实际查询复用同一就绪判断；archived/unavailable 行为没有两套实现。
- 公开返回不含 `graph_set_id`、graph IRI、结果图 IRI、Build Session 或建模状态。
- MCP policy 允许 Project 绑定 read key 执行无 Project 参数的发现，但服务强制使用当前主体限制。
- HTTP/MCP 错误不泄漏外国 Ontology 所属 Project 或存在性。

## 真实运行时验收

1. 用组织管理员和 Project 绑定 read key 分别调用 REST 发现接口，保存脱敏的请求参数、状态码和
   响应断言。
2. 用相同 Project key 调用 `discover_semantic_scopes`，比较核心 `data`。
3. 使用返回的 Project 与 Ontology `query_scope` 分别调用 Context Query；使用安全只读 ASK/
   SELECT 调用 scoped SPARQL，确认无需内部 Graph Set/IRI。
4. 对唯一命名的测试 Project/Ontology 制造 archived、workspace incomplete、derived missing/stale
   状态；逐项验证后恢复或删除仅由本轮创建的数据。
5. 重启 systemd unit 后重复健康检查和至少一条 REST/MCP 发现调用。

## 清理

测试数据使用唯一前缀 `r1-2-002-acceptance-<timestamp>`。只清理可由此前缀和记录 ID 双重确认的
Project/API key/派生测试记录；无法证明归属时不删除并在独立轮次记录残留。

## 独立测试轮次

以下轮次由 `requirement_tester` 在开发停止写入后的稳定状态追加；失败与修复历史均保留。

### Independent Round 1 — 2026-07-19 — FAIL

- Result: `FAIL`.
- Defect D1 — `High`: pagination continuation state is not scoped to the caller's authorized
  catalog and can produce an incorrect empty page when reused in another authorized catalog.
- Defect D2 — `High`: the default local configuration does not provide a deployment-specific
  continuation-state integrity value, so the reviewed tamper-rejection contract is not met.
- Evidence: independent service-level verification.
- Other focused checks: `25 passed`.
- Full/runtime cases: not completed after blocking defects and response interruption.
- Cleanup: no persistent test data created.

### Independent Round 2 — 2026-07-19 — PASS

- Result: `PASS`.
- Round 1 defects: D1 and D2 are fixed and independently retested; normal same-caller pagination
  also passes.
- Focused checks: `28 passed`.
- Backend regression: `729 passed, 6 skipped`.
- Frontend build: `PASS`, with the existing chunk-size warning only.
- Browser regression: Playwright `37 passed`.
- Runtime health: `ontology-platform.service` is active; backend health and frontend HTTP checks
  pass after restart.
- Real public-interface acceptance: authorized organization/Project discovery, foreign-name empty
  results, REST/MCP parity, discovery scope reuse in Context Query and read-only scoped SPARQL, and
  partial/archived/workspace-not-ready/empty-Project behavior all pass.
- Cleanup: all uniquely created temporary API keys, Projects, and Ontologies were removed; residue
  count is zero.
- Unexecuted cases: none.
- Residual risk: without configured `SECRET_KEY`, continuation tokens are process-lifetime only as
  documented.
- GitNexus: the reported HIGH remains the previously reviewed line-shift over-attribution; this
  round found no independent evidence that the reported execution flows changed.
