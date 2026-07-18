# v1 平台全链路验收测试计划

- 需求来源：`docs/requirements/requirements-v1.0.md` R-001～R-008、R-011。
- 设计：`docs/delivery/designs/2026-07-17-v1-platform-full-chain-acceptance-design.md`。
- 非目标：R-009、R-010、Pending 需求和外部 Agent/Dify 建模效果。

## 前置条件

1. PostgreSQL、Oxigraph 与 `ontology-platform.service` 可用，数据库已升级到 Alembic head。
2. 使用单独创建的测试身份；日志、提交和报告不记录任何明文密码或 API key。
3. 每个场景生成唯一资源前缀，记录 Project ID 以便只清理本轮创建的数据。
4. 捕获原始 `SEMANTIC_PRODUCT_WRITE_MODE`。RDF 写入场景前临时设为 `rdf_primary`、重启并
   验证有效模式；所有退出路径恢复原值、重启并健康检查。此临时运行设置不作为产品配置提交。

## 场景 A：认证后的建模主链路

| 步骤 | 需求 | 断言 |
| --- | --- | --- |
| 创建 Project、Ontology | R-001, R-008 | admin 可创建；workspace-context 含唯一默认 Graph Set 和完整角色。 |
| 建立 Session/Checkpoint/Lease | R-003, R-008 | session 属于 Project，checkpoint 追加，lease 只作用于该 Ontology。 |
| dry-run 带内联 Evidence 的 Batch | R-002, R-004 | 不写入 Evidence/Association/lineage，返回确定性候选与 finding。 |
| apply_atomic 创建 Class、实例/关系、Operation | R-004, R-007 | workspace version/lease 受保护；写入、Evidence Association 与 operation 当前态一致。 |
| 相同请求重试 | R-002, R-004 | 不产生重复 batch attempt、statement occurrence 或 Evidence Association。 |
| 第二 Ontology 的 global/multi-scope query | R-006, R-008 | `project` 与显式两 Ontology scope 都返回 owning Ontology/current version；显式 P2 id 被拒绝。 |
| lineage 与 Context Query | R-005, R-006, R-007 | 查询结果包含当前模型、Evidence/lineage 状态与 Operation，不暴露秘密。 |
| MCP 读取 parity | R-003, R-005, R-006, R-008 | 真实 stdio transport 下，同一身份和范围的工具返回等价核心状态。 |

## 场景 B：失败、恢复和隔离

| 步骤 | 需求 | 断言 |
| --- | --- | --- |
| 过期版本/错误 lease | R-003, R-004 | 写入被 fence，当前模型、Evidence 与 lineage 不改变。 |
| 无效 atomic batch | R-002, R-004, R-007 | 失败项不会留下孤立 Evidence、Association、Operation 或语句。 |
| `apply_partial` 与受控 recovery | R-002, R-004, R-005 | 独立成功项落库；failed/blocked 项无证据/lineage；不确定结果以原 key 重试后收敛且不重复。 |
| actor 与 secret 防护 | R-007, R-008 | 伪造 actor 被覆盖为 `key:<name>`；高可信测试秘密返回 `422 secret_in_payload`，无任何持久化或回显。 |
| 另建 Project 与 project-bound key | R-002, R-006, R-008 | REST/MCP 读取、Evidence 引用、Context/SPARQL 均拒绝跨项目访问且不泄露详情。 |
| MCP 启动认证和隔离 | R-008 | 无 key 子进程启动失败；短生命周期 P1 key 的真实 stdio client 对 P1 成功、对 P2 拒绝。 |
| 真实 PostgreSQL 并发 | R-003, R-004 | lease 和 batch idempotency race suites 在真实数据库运行。 |

## 场景 C：发布级回归与运行时

1. `cd backend && uv run pytest`
2. `cd backend && RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest tests/test_build_session_postgres.py tests/test_modeling_batches_postgres.py`
   Run the deterministic recovery companion in the same release gate:
   `uv run pytest tests/test_modeling_batches_service.py::test_recovery_observes_applied_rdf_and_finalizes_without_rewriting`.
   It is the only controlled `UncertainRdfStore` fault seam: it proves original-key retry convergence,
   write-fence removal, and no duplicate statement occurrence/origin without introducing fault injection
   into the production runtime.
3. `cd backend && uv run alembic upgrade head && uv run alembic current`
4. `cd frontend && npm run build`
5. 使用已配置、非泄露的测试凭据运行 `cd frontend && npx playwright test`；真实 contract 场景必须执行，不接受因缺 key 跳过。
6. `cd backend && uv run python ../scripts/sync-interface-docs.py --check`，以及文档同步测试。
7. 重启 `ontology-platform.service`；检查 unit active、`/api/health`、frontend、受保护 API 的 401 和带凭据的成功访问。
8. 用已记录的唯一 Project ID 清理本轮数据；无法证明归属的数据不删除。
9. 撤销临时 Project-bound key；恢复原 product write mode 并完成最终 restart/health。

## 缺陷规则与完成门槛

- 主链路任一写入、证据、lineage、查询、认证或恢复不一致为 High，必须修复并由独立测试复测。
- 真实依赖不可用只能标记 blocked，并记录精确失败命令、依赖状态和未执行场景；不能用 mock 成功替代。
- 每个独立测试轮次追加到本文件，保留失败和修复记录。
- 所有场景、回归、运行时检查和清理均通过后，才可标记 PASS。

## 测试轮次

### Round 0 — 计划冻结

- 状态：REVISE。初审发现 `legacy_only` 会阻断真实 R-004 写入，且原计划遗漏 recovery/partial、
  actor/secret、project-bound MCP transport、R-006 多本体范围。
- 处理：已加入受控 `rdf_primary` setup/restore、fault seam、真实 stdio MCP 和上述验收断言，待复审。

### Round 1 — 独立执行（2026-07-17）

- 状态：FAIL（High，验收 harness 未走完全程且不能证明多个必测契约）。
- 主验收命令：`cd backend && RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest -vv -s --tb=long tests/test_v1_full_chain_acceptance.py`；结果 `1 failed`（34.43s）。
  `test_v1_full_chain_acceptance.py:233` 读取不存在的 `scope.ontology_ids`；实际公开契约为
  `scope.ontologies[].ontology_id`（`app/services/semantic_query_scope.py`）。故 R-006 后续 project
  scope、stdio MCP parity/isolation、无 key 断言均未运行。
- 静态执行审查：现有 harness 没有读取或断言 Evidence Association/lineage，也没有 `apply_partial`
  与受控 cross-store recovery、伪造 actor 覆盖、`GRAPH ?g` 跨 Project probe，不能满足场景 A/B。
  仅提交结果状态、secret 错误文本和 Context Query 请求不足以证明这些契约。
- 已通过门禁：`RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest tests/test_build_session_postgres.py tests/test_modeling_batches_postgres.py`
  为 `3 passed`；`uv run pytest` 为 `689 passed, 4 skipped`（全链路测试默认 skip）；迁移 head 为
  `0027_r008_auth`；`uv run python ../scripts/sync-interface-docs.py --check` 通过，文档测试 `10 passed`；
  `frontend npm run build` 通过，`npx playwright test` 为 `33 passed, 3 skipped`。
- 实际运行与恢复：harness 的两组唯一 P1/P2 Project 均在 finally 中收到 `204` 删除；`rdf_primary`
  临时 manager setting 已恢复为原 unset 状态；服务 active，`/api/health` 和 frontend 成功，匿名
  `GET /api/projects` 为 `401`。单独无 key stdio 命令确认报 `ONTOLOGY_MCP_API_KEY is required`。
- 未执行/未证明：带 project-bound key 的真实 stdio MCP P1 success/P2 deny，lineage/Evidence/Operation
  查询 parity，partial/recovery 的收敛与无残留，actor/安全事件非持久化，`GRAPH ?g` 项目隔离，以及
  Playwright 的 3 个真实 live-contract 场景（环境未提供其所需前端认证配置）。修复验收 harness 后
  必须完整重跑本轮。

### Round 2 — 独立复测（2026-07-17）

- 状态：FAIL（仍有 High 验收缺口；不否定已通过的真实主链路）。
- 主验收命令：`cd backend && RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest -vv -s --tb=long tests/test_v1_full_chain_acceptance.py`
  通过。已实际覆盖修正后的 R-006 scope shape、REST Evidence Reference/Association、REST lineage、
  `apply_partial` 状态、`GRAPH ?g` 不返回 P2 graph、Project-bound key 的真实 stdio MCP P1 成功/P2
  拒绝/lineage 成功、无 key MCP 拒绝启动；临时 key revoke 与唯一 P1/P2 删除均返回成功。
- 受控 recovery：既有 `UncertainRdfStore` 原 key/fence/retry 组通过：`uv run pytest -vv
  tests/test_modeling_batches_service.py -k 'recovery_observes_applied_rdf_and_finalizes_without_rewriting or
  bounded_recovery_can_fail_when_no_side_effects_are_proven or recovery_stops_for_rdf_state_outside_the_persisted_plan
  or apply_partial'` 为 `4 passed`。这仍是服务级 fake RDF seam；全链路 harness 未把该 seam 纳入本轮。
- 未满足的 High 证明：`apply_partial` 只断言 item status，未读取 Evidence/Association/lineage 验证 failed/
  blocked 无残留；actor case 对 `ModelingBatchSubmit` 顶层 `actor` 的实际响应为 `422`（schema `extra=forbid`），
  仅证明安全事件出现，不能证明需求要求的“请求仍写入且 actor 强制覆盖”；因此 R-002/R-004 和 R-008
  的相关验收不能以此轮主 harness 宣告完成。
- 发布门禁：后端 `uv run pytest` 为 `689 passed, 4 skipped`；PostgreSQL 并发为 `3 passed`；migration
  `0027_r008_auth (head)`；接口文档 check 与文档测试通过；frontend build 通过，Playwright 仍为
  `33 passed, 3 skipped`。三个被跳过的真实 live-contract 需要 `ONTOLOGY_PLAYWRIGHT_API_KEY`；本轮未注入
  bootstrap key，避免运行现有不清理其 dataset/graph 的浏览器脚本。该 skip 与计划“必测真实场景零 skip”
  冲突。
- 运行态：Round 2 结束后 service active、`/api/health` 与 frontend 可访问、匿名 `/api/projects` 为 `401`、
  manager `SEMANTIC_PRODUCT_WRITE_MODE` 恢复为原 unset 状态；`git diff --check` 通过。残余风险为上述
  actor/partial 证明、recovery 的真实 HTTP/RDF 结合，以及未执行的 authenticated Playwright live-contract。

### Round 3 — 独立复测（2026-07-17）

- 状态：FAIL（High，浏览器 live-contract 的清理实际失败；不以其“通过”掩盖残留资源）。
- `RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest -vv -s --tb=long tests/test_v1_full_chain_acceptance.py`
  通过。其真实链路已验证 actor hint 被接受、成功 apply 的 audit actor 为 `key:*`、secret 拒绝、partial
  good item 唯一 Evidence Association、R-006/R-008/MCP 与 finally cleanup；write mode 恢复为 unset。
  但该 harness 本身没有 `UncertainRdfStore`/fault seam，不能宣称“全 HTTP/MCP harness 含 recovery”。
- actor/recovery 定向：actor compatibility API test 与三项 `UncertainRdfStore` original-key/fence/retry
  tests 为 `4 passed`；PostgreSQL lease/batch 并发为 `3 passed`。此 recovery 仍是服务级 fake RDF seam。
- 浏览器：`npx playwright test tests/live-contract.spec.ts` 在 service 已稳定后为 `4 passed`；全量
  `npm run build && npx playwright test` 为 `36 passed`、零 skip。首次紧接 full-chain fixture teardown
  的浏览器运行曾 3 failed，日志显示 fixture restart 返回过早、旧 `:8001` health 与新 service build
  重叠；稳定后重跑通过，表明 restart readiness probe 仍有竞争风险。
- 清理失败证据：全量浏览器后，数据库查询本轮 `R006 Live %`/`R006 Rules %` 项目发现 6 个；认证删除
  仅一个 `204`、五个 `409 Project could not be deleted`，仍有 5 个可证明属本轮的 Rule Project。现有
  Playwright `afterEach` 未断言 delete HTTP status，故其绿灯不能证明计划的项目/Oxigraph cleanup。
  测试人员未用 SQL 绕过产品删除语义清除这些依赖资源，待产品修复后重试并清理。
- 其余门禁：backend `689 passed, 4 skipped`；migration `0027_r008_auth (head)`；docs sync 与文档测试
  `10 passed`；显式 systemd restart 后 service active、health/frontend 成功、匿名 projects `401`、
  write mode unset、`git diff --check` 通过。

### Round 4 — 独立复测（2026-07-17）

- 状态：PASS。
- 删除顺序与历史残留：规则定义循环删除单测通过；先前 Round 3 记录的五个明确 Rule Project ID
  经 PostgreSQL 查询均不存在。真实浏览器 Rule 场景在创建 Ontology、Rule 与 Rule Run 后由 afterEach
  断言 Project DELETE `204`，因此覆盖了此前 409 的依赖组合。
- 浏览器与清理：`npm run build && npx playwright test` 为 `36 passed`、零 skip。运行前后独立审计
  `R006 Live/Rules` Project 总数均为 `10`，Oxigraph `.../live-` graph 总数均为 `3714`；afterEach 同时
  断言每个 Project DELETE `204` 与每个 graph DELETE 成功，证明本轮未遗留其拥有的 Project/graph。
- 主链路与 recovery：`RUN_V1_FULL_CHAIN_ACCEPTANCE=1 uv run pytest -vv -s --tb=long
  tests/test_v1_full_chain_acceptance.py tests/test_modeling_batches_service.py::test_recovery_observes_applied_rdf_and_finalizes_without_rewriting
  tests/test_ontology_workspace.py::test_delete_project_removes_rule_definition_cycle_before_ontology_cascade`
  通过。该组合包含真实 HTTP/stdio MCP 链路，以及唯一受控 `UncertainRdfStore` original-key retry、fence
  移除和无重复 occurrence/origin companion。
- 发布门禁：backend `690 passed, 4 skipped`；真实 PostgreSQL 并发 `3 passed`；migration
  `0027_r008_auth (head)`；interface docs check 与文档测试 `10 passed`；最终显式 systemd restart 后
  service active、重复 health 与 frontend 成功、匿名 projects `401`、manager write mode 恢复为 unset、
  `git diff --check` 通过。
- 残余风险：全链路的 cross-store 不确定性仍由受控 service-level fault seam 表达，而非对生产 Oxigraph
  注入故障；此为设计明确的测试边界，正常 HTTP/MCP/RDF 主链路已在真实依赖通过。
