# R4.0-027 统一模型修订编号交付记录

权威范围：[requirements-v4.0.md](../../requirements/requirements-v4.0.md#r40-027-ontology-统一模型修订编号与重复版本机制退役)。
授权：2026-10-08 用户“开始实施027”。标准需求交付，未启动真实建模，未执行外部业务 SQL／API。

## 实现与迁移

Ontology 已有 `model_revision` 是唯一当前模型状态编号。新 Ontology 从 0 开始，既有编号不重置。
读取、dry-run、未写入失败、投影重建、代码或配置改变不推进。实际应用、部分应用与恢复收敛
按已提交状态推进；幂等重试不再次推进。未知写入保留 Attempt、内容哈希及原子恢复证据，
现有写入围栏在未收敛期间阻止将不确定 RDF 当作稳定状态读取，反馈指向原 Attempt。

REST／MCP、Query Scope、读取回执、Context 游标、投影、Team 交接及工作台使用整数
`model_revision`，写入预期值为 `expected_model_revision`。字符串哈希和布尔值不再接受。
Attempt 的 `workspace.expected_version/before_version/after_version` 结构保留，值改为编号。
租约、权限、计划／内容 digest、批准、幂等和恢复归因保留独立职责。

迁移 `0035_ontology_model_revision` 在本机 PostgreSQL 已执行：

- 保留 Ontology `dbef2380-21c1-40ac-85c5-1c4013d8b7e9` 的资源身份、模型图、内容哈希和编号 23。
- 新增可空整数绑定列；旧 Attempt 和投影的原始哈希列保留，不回填为新编号。
- 旧 current manifest、待执行旧 job 标为 stale；索引成功重建后使用编号绑定恢复。
- 核对迁移前的 1 个 Ontology、1641 条 Job、588 条 Manifest、38 个 Batch、68 个 Attempt、
  16 个检查点仍存在；除投影必要状态外，原有字段逐项一致。
- Context 游标 v2 失效，须从第一页重读。旧交接和未完成 Attempt 须重新读取与准备；
  历史冻结证据、检查点与旧哈希回执保留原样，不转换为当前合同。
- 不支持把新编号自动降级为历史哈希；数据库降级需要明确回滚方案。

## 验证

| 验收项 | 证据 |
| --- | --- |
| A1 写入、部分应用、恢复 | revision 事务／回滚测试，Batch 部分应用和故障恢复断言；真实 API 0→1、幂等重试不推进 |
| A2 漂移与安全继续 | 真实接口拒绝旧 expected_revision，返回 current_model_revision；重读后新的幂等键应用成功；原子／同内容回归 |
| A3 索引生命周期 | 构建前后／发布锁下漂移检查，失败与旧索引降级回归；真实显式重建；独立 PostgreSQL 会话在构建期间写入后旧 job 为 stale 且不发布 manifest |
| A4 模型与配置分离 | 编号不依赖内容哈希或代码公式；Embedding 配置 hash 兼容性独立检查；升级后既有编号 23 未变 |
| A5 读取与分页 | 读取结束漂移检测、cursor/auth 回归；真实分页后写入使旧游标返回 409；写入围栏期间读取可恢复失败 |
| A6 旧绑定处置 | 实际迁移逐字段核对，旧 scope preflight 拒绝，旧冻结 start53 不能作为新编号交接；当前生产路径依赖检查 |

功能交付 PASS，证据分层如下：

- `cd backend && uv run pytest`：1005 passed / 56 skipped。跳过项是 opt-in 运行／语义场景，
  不计作通过。部分应用、恢复、游标、授权、失败投影与配置兼容均有功能回归覆盖。
- `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`：
  2509 passed / 10 skipped；后续受影响 Team 集成检查另有 77 passed / 1 skipped，CQ CLI／合同 21 passed。
- `cd frontend && npm run build`：通过；`npx playwright test`：42 passed，含真实 API/Oxigraph。
- 隔离 R4027 HTTP 全链与 PostgreSQL 跨会话构建漂移：通过，重启后重复验证 1 passed。
- `sync-interface-docs.py`：同步检查通过；`git diff --check`：通过。
- `ontology-platform.service` 已按要求重启，active；8001 `/api/health` 返回 ok，5173 返回 200。
  重启后保留模型仍为编号 23，当前 pgvector 分区直接读取返回向量候选。

上述是开发者功能／实际依赖验证；独立业务语义验收未执行。

隔离实际接口测试：`RUN_R4027_HTTP=1 uv run pytest tests/test_r4027_http.py` 使用唯一临时 Project／
Ontology／API Key，真实 PostgreSQL、Oxigraph 和 HTTP；清理自身资源，不修改保留模型。
同进程故障注入与独立 SQL 会话验证属于开发者功能证据，不代表独立业务语义验收。

既有模型通过现有 `retrieval:rebuild` 重建，Job
`5cda2def-2262-46fe-bb56-e679a6ba610e` 为 current，编号仍为 23。受治理 hybrid 请求返回 200；
候选窗口／页大小造成的完整性警告保留，未声称完整业务覆盖或问答质量。

GitNexus `detect_changes` 报 CRITICAL（跨层合同），但索引包含已退役 GraphSet 符号，不能视为
当前精确调用图；使用当前代码／调用点、完整回归、真实数据库与接口验证补充覆盖。
未新增真实 semantic start，不声称独立语义 PASS。
