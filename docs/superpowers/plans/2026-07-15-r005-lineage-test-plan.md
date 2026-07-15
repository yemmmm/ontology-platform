# R-005 统一知识来源与推导链独立测试计划

## 1. 测试依据

- 需求：`docs/requirements-v1.0.md` R-005。
- 设计：`docs/superpowers/specs/2026-07-15-r005-unified-lineage-design.md`。
- 依赖：R-002 Evidence Reference、R-004 Modeling Batch 与 forward recovery。

测试 Agent 应复用本计划，不重新定义目标或扩大到 R-006/R-107。

## 2. 独立测试职责

测试 Agent 在开发 Agent 完成后执行以下工作：

1. 先做代码和迁移审查，核对实现是否覆盖设计中的写入路径，而不仅是 API mock。
2. 运行定向服务/API/MCP 测试和全量 backend pytest。
3. 在真实 PostgreSQL、Oxigraph 和本地 service 上完成最小端到端验收。
4. 重点寻找伪证据、错误前提链、跨项目泄漏、历史覆盖和幂等重复。
5. 将发现按严重程度、复现步骤、预期/实际结果和涉及文件报告给主 Agent；不得自行放宽验收。

## 3. 必测场景

### A. 标识和生命周期

- 相同 quad、相同 revision 的重复记录幂等。
- 相同 quad 在 delete 后 reinsert，`statement_id` 相同、`occurrence_id` 不同。
- 默认查询只返回当前 occurrence；`include_history=true` 返回失效记录和 Audit。
- datatype、language tag、IRI object 不发生 statement ID 碰撞。

### B. Modeling Item 与 Supporting Context

- 带内联 Evidence、已有 Evidence ID、rationale、Competency Question 的 R-004 Item。
- 一个 Item 多个输出 statement，全部可回到同一 Item。
- 多个兼容 Item 产生同一 quad，全部 Origin 保留且不重复。
- partial apply 的 failed/not_applied Item 不产生 lineage。
- 无 Evidence 内容返回 `missing`，rationale 不被包装为 Evidence。

### C. 人工和 canonical 编辑

- insert 返回 actor、reason、time、Audit 和 occurrence。
- update/delete 使旧 occurrence 失效，新语句产生新 occurrence。
- 缺 actor/reason 时仍返回来源，但不能虚构认证主体或理由。

### D. 派生链

- Platform DSL 输出包含 Rule IRI/version、Run、exact premises 和递归链。
- exact premise 依赖无 Evidence 时，派生结果为 `dependency_evidence_status=contains_missing`。
- SPARQL CONSTRUCT 和 OWL 当前路径为 `coarse`，返回 input revisions/signature。
- derived result 的 `evidence_references` 为空；只能通过 premises 汇总 dependency 状态。
- stale/superseded result graph 不作为默认 current 结果，历史查询仍可读取。
- 失败 Run 不创建输出 occurrence。

### E. 查询边界

- `statement`、`resource`、`rule` 三类 target。
- `max_depth=0`、最大深度、节点上限、环和 truncation warning。
- 不存在 target 返回 404/MCP `not_found`；存在但旧来源未知返回 partial。
- 调用方不能用 target ID 读取其他 Ontology/Project 的 Evidence excerpt。
- REST 与 MCP 对同一 target 返回一致的核心字段和状态。
- 兼容 MCP 工具返回 `deprecated=true` 且不再伪称 subject IRI 是唯一 statement。

### F. 幂等与恢复

- 相同 R-004 idempotency key 重试不增加 lineage 行数。
- 模拟 RDF 已应用、PostgreSQL 记录待补齐的 recovery，补齐后无重复。
- lineage 记录失败时不得把 Attempt 错误标记为成功；恢复仍能收敛。

## 4. 建议测试命令

开发者可调整新增测试文件名，但测试 Agent必须覆盖相同范围：

```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/test_lineage_service.py tests/test_lineage_api.py tests/test_mcp_surface.py -q
uv run pytest tests/test_modeling_batches.py tests/test_semantic_phase5.py -q
uv run pytest
```

若新增真实 PostgreSQL/Oxigraph 定向测试，使用仓库现有 fixture/marker，不以 SQLite 结果替代
PostgreSQL 唯一约束、JSONB 和事务行为。

## 5. 真实运行时验收

1. 确认 PostgreSQL/Oxigraph 和 `ontology-platform.service` 可用。
2. 通过真实 API 创建或选择测试 Project/Ontology。
3. 通过 R-004 写入：
   - 一个带 Evidence 的模型结构；
   - 一个无 Evidence 的 asserted Fact；
   - 一个可产生结果的 Platform DSL Rule。
4. 调用 REST lineage 查询三个 target，核对 Evidence、missing、Audit 和 exact premise。
5. 调用 MCP `get_ontology_lineage` 核对同一结果。
6. 删除并重新插入 Fact，验证 history。
7. 重启服务并验证记录仍可查询。

运行时完成条件：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时检查：

```bash
journalctl --user -u ontology-platform.service --no-pager -n 200
```

## 6. 完成门槛

- Alembic head 升级成功。
- 全量 backend pytest 无失败。
- 所有必测场景通过，或存在明确外部依赖 blocker 且已报告精确命令和错误。
- 没有派生结果直接绑定 Evidence、没有 rationale 冒充 Evidence、没有跨项目 Evidence 泄漏。
- service 重启后 backend/frontend 健康，真实 lineage 查询仍成功。
