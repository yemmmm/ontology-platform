# R3.0-008A 独立测试 Round 1 证据

- 日期：2026-09-03
- 执行者：`requirement_tester`（独立验收轮；未创建、未延续、未评估任何真实建模运行，未消耗 modeling attempt）
- 代码基线：commit `b8c4f84`（HEAD of `main`）+ 工作区未提交变更，经 `git status --porcelain` 核对仅限：
  `backend/app/services/{modeling_batches,modeling_handlers,semantic_command_compiler,semantic_context_query,semantic_sparql_templates}.py`
  与新增 `backend/tests/test_r3008a_{semantic_value_integrity,controlled_value_chain}.py`（另有与本需求无关的未跟踪 `.codex/agents/`，不属产品代码）
- 读取面选择登记（计划 §8 L2）：进程内 FastAPI `TestClient` + 真实 Oxigraph store（`http://127.0.0.1:7878`，
  token 域图，测试内建清理）+ 真实场景 PostgreSQL（`R3005_SQL_ADAPTER_DSN`，只读 SQL）
- fixture 载体登记：pytest fixture 经 `KEY_MODEL` 等价 model-scope key + 真实 Build Session + Modeling Batch
  （dry-run → apply）seeding（测试内 sqlite 控制面 + token 域 Oxigraph 图，非 8001 共享运行时库）；
  seeding 批次 ID 由测试内 `env.seeding_batch_ids` 登记（每轮随机 token 域，不落库于共享面）

## 1. 实现复核（先审后测）

开发者声明逐条对照 `git diff backend/app/services/`（+211/−4）：

| 声明 | 复核结论 | 证据 |
| --- | --- | --- |
| G7 独立双图视图（ontology+data graph 装载，同批投影扩到两类目标图；G2–G6 仍只查 ontology graph） | 一致 | `modeling_batches.py` `_validate_relational_mapping_commands` 新增段：`g7_graphs = {graph_iri, data_graph_iri}`，`g7_view` 双图 parse；删除/插入投影按 `target_graph in g7_graphs` 过滤；既有 G2/G3/G5/G6 查询块零改动（B7 测试亦证 G2 视图未泄漏） |
| G7-d 仅 subject 位存在性（目标以 subject 出现任意三元组即存在；delete_entity 的 object 位通配删除在投影下为 no-op） | 一致 | 悬挂判定 `if not any(g7_view.triples((target, None, None)))`；删除投影 `predicate == "?p"` 分支按 subject 整体移除，代码注释与设计 §3.3 口径相同 |
| DSN 豁免 | 一致 | `semantic_command_compiler.py` `_RELATIONAL_DSN_EXEMPT_FIELDS` frozenset 增 `"semantic_value"` |
| 投影两处 | 一致 | `semantic_context_query.py` `_mapping_candidates` SELECT 增 `?semanticValue` + OPTIONAL + `data["semantic_value"]` 非空透传；`semantic_sparql_templates.py` `enum-meaning-list`/`enum-meaning-detail` 各增变量 + OPTIONAL + `detail_variables` |
| fixture graph set 含 `asserted_data` 成员 | 一致（有端到端测试证明） | `test_r3008a_controlled_value_chain.py::test_graph_set_contains_asserted_data_member` 直接查 `SemanticGraphSetMemberModel.role`，且 S3 召回经 data graph 端到端成立 |

命令面（`modeling_handlers.py` ALLOWED_FIELDS 两处 + 编译层 create/update）、G7-a/b/c 拒绝形态
（`invalid_resource_reference`，`path=["payload","semantic_value"]`）、G7-d 新 code
`semantic_value_dangling` 归属规则均与设计 §3.2/§3.3 一致。

## 2. L1 健康与基线

| 检查 | 结果 |
| --- | --- |
| `systemctl --user is-active ontology-platform.service` | active |
| `curl http://127.0.0.1:8001/api/health` | 200 |
| `curl http://127.0.0.1:5173/` | 200 |
| `uv run alembic current`（backend/） | `0032_semantic_protection_sets (head)`（零 migration，符合设计 §5） |
| Oxigraph `http://127.0.0.1:7878` | 可达（200） |
| 场景库 `industrial_service_v3` | 已装载：work_orders=12 行 |
| 独立基准复核（测试者直连 psycopg，与被测链路无共享代码） | S5 基准 `cause_code='PART_SHORTAGE'` 延期订单 = `[WO-1001, WO-1008]`（与测试写死值一致）；L1 `currency='CNY'` spare_parts=6 |

## 3. 命令与结果

```text
# 聚焦（双门控 + DSN）
RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1 \
R3005_SQL_ADAPTER_DSN=postgresql://ontology:***@localhost:5434/ontology_platform \
uv run pytest tests/test_r3008a_semantic_value_integrity.py tests/test_r3008a_controlled_value_chain.py -v
→ 25 passed, 0 skipped in 35.35s
   （S5 含适配器真实 SQL 执行并与独立基准比对；S1 CNY 计数真实执行）

# 全量 R1 第一次（默认门控）
uv run pytest
→ 957 passed, 36 skipped in 47.31s

# 全量 R1 第二次（门控）
RUN_OXIGRAPH_SPARQL_RUNNER_TESTS=1 R3005_SQL_ADAPTER_DSN=postgresql://***@localhost:5434/ontology_platform uv run pytest
→ 985 passed, 8 skipped in 95.44s
   8 个 skip 均为既有无关门控（RUN_POSTGRES_CONCURRENCY_TESTS /
   RUN_POSTGRES_MIGRATION_TESTS / RUN_V1_FULL_CHAIN_ACCEPTANCE），无假失败、无 008A skip
```

## 4. 用例判定

- S1–S6、S5c (i)–(iv)：PASS（`test_r3008a_controlled_value_chain.py` 对应用例；S5 双 DSN 实测）
- B1–B7、B6 零猜测物化、S6 升降级往返：PASS（`test_r3008a_semantic_value_integrity.py` 13 用例）
- F1/F2 未授权无痕 + 无泄露子串：PASS（终态不可区分断言 + 禁词扫描 + 无痕子集合同）
- F3 授权合同回归：PASS（全量套件内 `test_semantic_access_*`、`test_semantic_protection_sets.py` 全绿）
- F4 边界守恒 grep 门：PASS——五个产品文件 grep
  `缺料|PART_SHORTAGE|WAITING_PARTS|work_orders|work_order_delay_events|spare_parts|cause_code|PartShortage`
  零命中；`git status` 确认无其他产品文件/路由/MCP 工具/migration 变更
- F5 RDF 未复制业务行：PASS（行级标记扫描 + 业务类 typed-instance 断言）
- F6 建模零消耗：PASS——测试内账面断言（消费期前后 batch/session 集合相等）+ 共享面账面核对：
  8001 控制面库（5434/ontology_platform）`build_sessions`、`modeling_batches` 总数均为 0、近 3 小时新建 0；
  测试 fixture 全部使用独立 sqlite 控制面与 token 域 Oxigraph 图，未触碰 8001 共享运行时库/RDF 图
- R1 全量回归：PASS（两次全量均绿，见 §3）
- R2 依赖套件（R3.0-003/004/005/007）：PASS（含于全量：`test_modeling_batches_relational_mapping.py`、
  `test_semantic_command_compiler_r3003.py`、`test_r3005_authorized_sql_chain.py`、`test_r3005_sql_exec_adapter.py` 等全绿）
- R3 装载器幂等：PASS（等效满足）——本轮对场景库仅有只读 SELECT；独立计数复核基线未变
  （work_orders=12、S5 基准两行），无需重装载（计划 §9.3 可选项）

## 5. 清理与残留复核（计划 §9）

- fixture 图清理：测试 teardown `DROP SILENT` token 域图；测试者事后直查 7878 Oxigraph：
  `r3008a` 域图残留 = 0（store 当前命名图为空）
- fixture key/project/ontology：sqlite 内存控制面随引擎销毁，无持久化 key；无含 key 的临时文件产生
- 8001 共享运行时：库与 RDF 图零写入（见 F6）
- 无临时探针/脚本残留

## 6. 缺陷

无。未发现 G7 拒绝路径放行、授权泄露、边界守恒破坏、RDF 业务行复制或建模预算消耗。

## 7. 残余风险（非缺陷）

- G7-c/G7-d 扫描仅在批内含枚举命令或 `delete_entity` 时执行：不含这两类命令的批次不会检出图中既有的
  直写残留（悬挂/多值）——与设计触发集合口径一致，属既定边界而非缺口。
- `businessMeaning` 与 L3 标签措辞不一致时平台不仲裁（设计 §4.2 既记录边界）。
- 测试断链矩阵 (v)「未授权主体」由 F1/F2 用例覆盖（不动 fixture），与计划 §3.5 一致。
