# R3.0-017 共享测试计划（检查点数据快照与分叉续跑 fork-to-new-project）

- 日期：2026-09-18；需求：§R3.0-017（`docs/requirements/requirements-v3.0.md` L1582 起；状态表 L239：P2，`2026-09-18 已实现并通过开发验证`）
- 配套设计：`docs/delivery/designs/2026-09-18-r3-0-017-checkpoint-data-fork-design.md`
- **诚实声明**：实现先于本计划完成（codex 会话，当前在 git 暂存区，工作树即被测状态，基点 HEAD `b677a44`）。本计划为交付流程补件，用于随后的独立功能验收盲跑（requirement_tester）与计划评审（plan_reviewer）；开发自测（`backend/tests/test_checkpoint_data.py` 6 节点、`backend/tests/test_checkpoint_data_live.py`、`modeling_team/tests/test_r30017_checkpoint_data.py` 5 节点、`test_r30015_checkpoints.py` 回归更新）只作基线对照，**不视为已验收**。
- 用法：开发自测与独立功能验收共用 §1–§4、§7；真实运行时检查用 §5。基线失败比对按"失败清单"而非总数。
- 计划评审：Round 1（2026-09-18，plan_reviewer）REVISE——High-1 表数量误记 27（实为 26，F-SNAP-004 与 §7 已改并锚定代码集合）、High-2 无非空 lineage 重映射用例（新增 F-FORK-012，F-FORK-004 交叉引用）；两项均 accepted-high，另有 3 项假设经主 agent 确认登记为决策 13/14 与既有问题注记。Round 2 专项复核 PASS（2026-09-18，两处修订核实解决、无新增发现）。
- 边界重申（需求第 6 点）：本计划全部证据为机械回归与数据往返层面；不以任何一条通过宣布真实 LLM 建模质量或独立语义验收通过。

## 1. 证据分层

| 层 | 证据 | 本计划位置 |
| --- | --- | --- |
| D0 | 静态核对（现状事实、接口/参数/错误码存在性、文件落位） | §7 |
| M | 确定性单测/契约测试（进程内服务与假 RDF Store、TestClient、tmp run 根、CapturingAdapter、monkeypatch 数据通道） | §3 |
| I | 独立功能验收（M 用例盲跑 + 全量基线失败清单比对 + 泄漏扫描） | §4 |
| L0 | 真实运行时：真实 PostgreSQL/Oxigraph 数据往返（含并发写锁时序）+ 服务重启后真实认证 HTTP 保存/fork/封存读写 | §5 |

本需求的 L0 **不含真实 LLM 建模**：需求登记边界明确"验证分别记录机械回归、PostgreSQL/Oxigraph 数据往返和服务重启检查，不以此宣布真实 LLM 建模质量或独立语义验收通过"。团队侧 fork 恢复路径的机械证明使用 CapturingAdapter（无模型 provider）。

fixture 形态规则：快照、manifest 的 `platform_data` 块、恢复文件（`recovery/origin.json`、`imports.json`、角色包）必须由真实 `save_checkpoint`/`prepare_fork_plan`/`CheckpointDataService` 代码路径产出，不得手写臆造字段或摘要；摘要算法一律调用被测代码（`snapshot_digest`、`file_digest`）。

## 2. 测试数据与隔离

1. **后端确定性层**：进程内 `in_memory_session`（sqlite）+ 测试自有假 RDF Store（`graph_exists/export_named_graph/put_named_graph/graph_content_hash/drop_named_graph`，可注入 PUT 失败与 COMMIT 响应丢失）；HTTP 面复用既有 `r008_client` fixture（组织 admin key 与项目级 p1-admin key 双主体）；不触碰真实数据库。
2. **真实数据库（仅 §5）**：临时 UUID 的源 Project/Ontology 与目标 Project；`test_checkpoint_data_live.py` 自带 finally 清理——先按 project_ids 反查 ontologies 与 graphs（COMMIT 后响应异常也能发现身份），依次删 Graph Set Member/Set、`semantic_graph_state`/`semantic_graph_revision`/`semantic_graph_registry` 行、Projects、测试自建 ApiKey，并 drop 全部涉及图。独立轮不得影响任何既有项目数据，结束后核对该清理确实执行。
3. **admin key 生命周期**：`/api/checkpoint-data/*` 要求组织管理员（scope admin 且不绑定项目）。live HTTP 模式由测试 `create_api_key(project_id=None, scopes=["admin"])` 创建并在 finally 删除；密钥明文只存在于内存与请求头，不落入任何断言、日志、记录或本计划文档。团队侧用例的宿主凭据（`canonical_admin_key`）用随机假值注入并做全树泄漏扫描。
4. **团队侧隔离**：独立 tmp run 根与 RUNS_ROOT 隔离（沿用 015/017 测试惯例）；`CapturingAdapter` 不启动模型 provider；`platform_data_request` 以 monkeypatch 替身注入；快照内容置哨兵值（如 `HOST-PRIVATE-ONLY`）做泄漏扫描。
5. **快照文件落位与权限**：`checkpoints/<id>/host-private/platform-data.json`，文件 0600、host-private 目录 0700、写入后 fsync；断言不复制进新 run 的角色可读产物（角色包与任务文本无 `platform-data.json`、无快照内容）。
6. **基线比对**：后端 `cd backend && uv run pytest -q`；Team 在 backend 目录 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`；均不加 `-x`，产出完整失败清单后 diff（新增失败=缺陷；既有失败须能对应已登记原因）。

## 3. 确定性用例

命名：`F-<域>-<序>-<成功|边界|失败|回归>`；域：SNAP 快照保存 / FORK 分叉导入 / SEAL 源封存 / HOST 宿主接口 / REG 回归。

交付合同映射：合同 1（显式分叉选择与参数校验）→ HOST 组；合同 2（快照内容、锁与 barrier、fence 不发布）→ SNAP 组；合同 3（新身份、重映射、完成索引来源、独立写链）→ FORK 组；合同 4（审批原件与 imports 台账）→ FORK-004/HOST-010；合同 5（封存、预落盘、pending、失败清理，含封存读形态）→ SEAL 组（F-SEAL-004 为封存读收窄补证，§9）与 FORK-006/007、HOST-009/010；合同 6（分层记录）→ §4/§5 结构本身。

### A 组（SNAP，保存与快照）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| F-SNAP-001-成功 | 成功 | 绑定平台的 run 保存检查点（`platform_bindings.project_id` 存在）自动附带数据 | 先 `wait_until_drained` 再以宿主凭据调 `capture`（payload 恰为 `{project_id, ontology_ids}`，多 Ontology 时 `ontology_ids` 取 `ontology_ids` 或退化 `ontology_id`）；manifest 含 `platform_data = {path: "host-private/platform-data.json", digest: "sha256:"+文件字节摘要, snapshot_digest}`；文件落位 `checkpoints/<id>/host-private/platform-data.json` 且 `st_mode & 0o077 == 0`；`_signature_payload` 去重含 `platform_data`（同数据重放 `status=="reused"`，改 snapshot_digest 后生成新包） |
| F-SNAP-002-失败 | 失败 | 保存缺宿主数据凭据（`canonical_admin_key` 与 `scope.admin_key` 均缺） | `CheckpointError checkpoint_data_credentials_missing`（obj=`platform_data`，phase=`checkpoint-save`，文案 "a scope-bound checkpoint requires the host data snapshot credential"）；此前检查点目录与 manifest 不变、不产生新包；旧包仍可原地接续（保存失败不破坏既有检查点） |
| F-SNAP-003-失败 | 失败 | 写 fence 未沉淀时不出数据快照 | `OntologyWriteFenceModel` 命中任一 Ontology → capture 报 `snapshot_write_unsettled`（"An apply fence is still present"），HTTP 面 409 同码；runner 侧 admission 未 drain → 既有 `checkpoint_write_unreconciled`（015 语义不放松）；该检查点不发布 `platform_data` |
| F-SNAP-004-成功 | 成功 | 快照内容清单与"不复制"边界 | `schema_version == "r3-0-017-platform-data/v1"`；`tables` 的表名集合恰等于被测服务 `model_types` 的 26 张表（projects、ontologies、briefs/interview/evidence/数据源/保护集、CQ/关联/映射/规则、图 registry/revision/state/set/member、occurrence/origin/premise、fact bindings；断言锚定代码集合本身，不硬编码数字，防漂移）；`completed_operations` 只含非 `dry_run` attempt 且 item `status == "applied"` 的条目（字段 `session_id/batch_id/attempt_id/client_item_id/client_batch_id/batch_complete/content_hash/idempotency_key`）；`digest` 为去除 `digest` 键后规范化 JSON 的 sha256（用被测 `snapshot_digest` 复算一致） |
| F-SNAP-005-边界 | 边界 | 范围校验 | Project/Ontology 缺失或不属于该项目 → `snapshot_scope_missing`（"Project/Ontology scope is missing" / "Ontology scope does not match Project"）；Graph Set 含 registry 之外的图 → `snapshot_external_graph`（"Graph Set includes an unowned graph"）；两者均无任何写入 |
| F-SNAP-006-成功 | 成功 | 多 Ontology 与空边界 | 同项目两 Ontology（其一仅有工作区默认图、无自定义内容；另一带自定义 shapes 图 `<prefix>/shapes/<owner>/custom`）capture+fork 成功；自定义图确定性重映射到 `<prefix>/shapes/<new_owner>/custom` 且内容保留；不存在的图以空串进入 `graphs`，fork 可解析为空图 |

### B 组（FORK，分叉导入与身份重映射）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| F-FORK-001-成功 | 成功 | 保存时数据冻结（合同 2/3 核心） | capture 之后源侧继续写（改 RDF 图内容与 evidence `excerpt`）再 fork：新图内容为保存时快照（"Before checkpoint"），源图保留后续写入（"After checkpoint"）；新项目中 evidence `excerpt` 为保存时值；evidence 关联外键按映射重挂（`evidence_reference_id == mapping[reference]`、`ontology_id == mapping[ontology]`）；业务资源 IRI（如 `target_id: urn:business:Order`）原样保留；保护集 `allowed_grants` 保留；新 Ontology workspace `state == "ready"` 且 `default_graph_set_id` 与源不同 |
| F-FORK-002-成功 | 成功 | 新身份与重映射 | 返回 `{project_id, ontology_ids, source_project_id, snapshot_digest, identity_mapping, derived_results: "recompute_required"}`；平台 ID 为 `uuid5(target namespace, 旧 id)`；默认工作区图 IRI 按新 Ontology 确定性重映射、非属主前缀图映射到 `<prefix>/fork/<uuid4>`；`statement_id`/occurrence id 与 `fact_evidence_bindings.fact_id` 按新图 IRI 用 `statement_id_for_quad`/`occurrence_id_for` 重算；导入后 revision `content_hash` 以新图实存内容回填 |
| F-FORK-003-成功 | 成功 | 完成索引只来自快照、不吸收旧链尾部 | `prepare_fork_plan` 的 reconciliation 全部由 `snapshot.completed_operations` 构造（`pending_new_dry_run/recoverable_new_batch/blocked/scope_drift` 为空、`readback_counters` 空）；readback 不得读源 run 可变批次（注入"读即断言失败"的 readback）；保存后向旧链追加 `status:"unknown"` 且无回执的 intent，fork 结果不受影响且 `origin.old_chain_writes == "unchanged; no reconciliation claim"` |
| F-FORK-004-成功 | 成功 | 审批原件与 imports 台账（合同 4） | approvals 经 `validate_business_approvals` 且原件不改；`origin` 记 `source_run_id/root_run_id/new_run_id/checkpoint_id/checkpoint_digest/snapshot_digest/authorization_reference/fork_reason` 与 `source_writer` 报告；fork 成功后 `imports` 含 `identity_mappings` 与 `approval_rebinding = {source_project_id, target_project_id, checkpoint_digest, snapshot_digest, business_approvals, translation_approval: "fresh_review_required"}`；角色包获 `fork_scope`、`identity_mapping` 与重发布/重走翻译审批指令；`SemanticStatementOrigin.origin_kind` 置 `legacy_unknown` 且 `origin_metadata` 保留 `fork_source_project_id/snapshot_digest/source_origin_kind/source_origin_id`（origin 断言须在 F-FORK-012 种入的非空 origin 行上验证，空表不构成证据） |
| F-FORK-005-失败 | 失败 | 摘要损坏/清单不符拒绝导入 | 篡改 snapshot 表内容 → `snapshot_invalid`（"Snapshot schema or digest does not match"）；表集合与预期不符 → `snapshot_invalid`（table inventory）；projects/ontologies 行与 scope 不符 → `snapshot_invalid`（scope does not match）；graph 清单或属主不符 → `snapshot_invalid`；全部无 SQL 写入（源 Project 行数不变） |
| F-FORK-006-失败 | 失败 | 导入失败只清理本次新建图；清理失败明确报告 | RDF PUT 抛错 → SQL 回滚 + 逐个 drop 本次已写新图；源图逐字节不变；不残留新 Project 行；drop 再失败 → `fork_cleanup_incomplete`，报出未清理图 IRI 清单 |
| F-FORK-007-失败 | 失败 | COMMIT 响应丢失保留新图与预分配身份 | commit 成功后注入异常 → `fork_commit_unknown`，message 含 target_project_id 与 "new graphs are retained"、指示先确认再重试；目标 Project 行与新图保留可读回；不删新图、不自动重试、不换新项目 |
| F-FORK-008-失败 | 失败 | 目标已存在 | `target_project_id` 已有 Project → `fork_target_exists`（409，"Target Project already exists; inspect its receipt"）；不覆盖既有目标 |
| F-FORK-009-成功 | 成功 | 规则外键环与旧审计引用 | `SemanticRule.current_definition_id` 先置空导入、后按 mapping 重挂（定义 FK 与新规则 id 一致）；`SemanticGraphRevision.last_edit_audit_id`、`EvidenceAssociation.edit_audit_id`、occurrence `invalidated_by_audit_id` 置空（旧审计/旧授权不复用）；新 Ontology `external_mappings` 记 `checkpoint_fork_origin = {source_project_id, source_ontology_id, snapshot_digest}` 且不携带源 ARCHIVE_KEY |
| F-FORK-010-成功 | 成功 | 不复制凭据/租约/会话/批次/在途写入 | 源项目预置 `BuildSessionModel`、`ModelingBatchModel`（含 attempt 与 item_results）、`OntologyLeaseModel`、`ApiKeyModel` 行后 capture+fork：目标项目这些表零行（fork 导入清单不含它们）；在途写入由 F-SNAP-003（fence）与 F-FORK-003（不读尾部）共同覆盖 |
| F-FORK-011-成功 | 成功 | 独立写链 | `origin_chain_roots` 遇 `schema_version == "r3-0-017-fork/v1"` 即停止（后续 run 的恢复链只含 `[fork, later]`，不重新引入分叉前 unknown）；fork 新图可继续写入且不回写源图 |
| F-FORK-012-成功 | 成功 | 非空语句级 lineage 的身份重映射（计划评审 Round 1 High-2 新增；合同 3 核心） | capture 前种入真实 lineage 数据：源图写入含三元组的语句行（`semantic_statement_occurrences`，含 subject/predicate/object_ntriples/graph_iri/graph_revision）、对应 `semantic_statement_origins`（origin_kind 取生产者来源）、`semantic_statement_premises`、`fact_evidence_bindings`。fork 后断言：(a) 新 occurrence `id == occurrence_id_for(statement_id_for_quad(subject, predicate, object, 新图 IRI), graph_revision)`，且新 statement_id ≠ 旧 statement_id（图 IRI 参与身份）；(b) 新 binding `fact_id == 新 statement_id`；(c) origin 行持久化为 `origin_kind == "legacy_unknown"` 且 `origin_metadata` 含 `fork_source_project_id/snapshot_digest/source_origin_kind/source_origin_id`（F-FORK-004 的 origin 期望在本用例数据上验证）；(d) premise 的 `derived_occurrence_id` 指向新 occurrence id；(e) 新图内容与旧图逐三元组等价（业务 IRI 不变）。**现有开发自测未种入语句级行（输入恒为空表）——本用例由独立验收轮构造执行**：以被测服务代码路径（真实 capture+fork）在进程内 sqlite+假 RDF Store 上跑通，临时脚本跑完即清理，结果与证据记录于 §8；若发现缺陷进入缺陷循环 |

### C 组（SEAL，源封存）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| F-SEAL-001-成功 | 成功 | 源封存标记 | fork 提交时源项目全部 Ontology `status == "archived"` 且 `external_mappings["checkpoint_fork_archive"] == {target_project_id, snapshot_digest}`（行锁序与 capture 一致）；`project_is_checkpoint_archived` 为真；源 run、检查点与旧 Attempt 不被改写 |
| F-SEAL-002-成功 | 成功 | 读可写拒（HTTP/MCP/语义写） | `GET /api/projects/<源>` 200；`PATCH` → 409 `{"code": "checkpoint_source_archived"}`；`POST /api/semantic/datasets:load`（trig 指向旧图）→ 409（`LockedSemanticGraph`，消息前缀 `checkpoint_source_archived: source Project is read-only`）；SPARQL 编辑与 canonical 写入同前缀阻断（`LockedSemanticGraph`/`CanonicalWriteBlocked`）；MCP `mutates_state` 工具触及源项目资源 → `PermissionError("checkpoint_source_archived: source Project is read-only")`；目标项目 `PATCH` 200 可继续推进 |
| F-SEAL-003-边界 | 边界 | 封存门作用域与不泄露 | 非 UNSAFE 方法与 `scope == "read"` 不拦；`/api/checkpoint-data/` 前缀自身不受该门拦截（capture/fork 不因源封存被拒）；ownership 判定先于封存判定（跨项目请求不泄露封存状态，404/403 语义不变）；未封存项目写路径零影响（全量回归见 G1） |
| F-SEAL-004-边界 | 边界 | 封存源读形态（合同第 5 点封存读收窄；2026-09-19 补证，证据见 §9，独立复核证据见 §10） | 走真实 readiness/query-scope 代码路径（`OntologyQueryReadinessEvaluator`/`SemanticQueryScopeResolver`，不 mock 判定）：治理语义查询（服务层 `ScopedSparqlQueryService` 与 HTTP `POST /api/semantic/sparql:query`）项目级与 Ontology 级均 409 `scope_not_ready` 且不触及 RDF Store；scope discovery 报 `queryable=false`/`reason=ontology_archived`（项目级 `query_status=unavailable` + excluded 明细）；`GET /api/projects/<源>` 仍 200（对照 `PATCH` 409 `checkpoint_source_archived`）；范围外 Ontology 随源封存、无 fork 副本（不在 identity mapping、新项目不含其数据）且同样不可查询；新项目 scope `complete`、语义查询继续 |

### D 组（HOST，宿主接口与 CLI）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| F-HOST-001-成功 | 成功 | CLI fork 接线 | `checkpoint resume --mode production --fork-reason <原因>` → 以 `fork_reason` 传入 `prepare_from_checkpoint`（monkeypatch 记录 kwargs 证实）；成功后 `resume_lock.release()` 并按 `--new-run-id` 重新 `acquire_root_run_lock`；不传 `--fork-reason` 时 kwargs 不含该键（`**{}` 条件展开）；其余实参（`--run-id`=源 run、`--checkpoint-id`、`--new-run-id`、`--authorization-reference`、`--freeze-started-at`）与 015 合同一致不变 |
| F-HOST-002-失败 | 失败 | acceptance 拒绝 fork | CLI `--mode acceptance --fork-reason …` → stderr `checkpoint failed: fork requires production mode`、退出码 2（在 run loader 之前拒绝）；宿主工具 `resume_from_checkpoint(fork_reason=…, mode!="production")` → `HostOpError launch_arguments_invalid`（"fork_reason requires production mode and a nonempty reason"，next_action 指明 production+理由），不创建子进程 |
| F-HOST-003-边界 | 边界 | fork_reason 空值校验 | 宿主工具层空串/纯空白/非字符串 → `launch_arguments_invalid`（同上文案，obj=`fork_reason`）；CLI 传入仅空白字符串 → `prepare_fork_plan` 报 `CheckpointError fork_reason_required`（"fork needs an explicit reason"，obj=`fork_reason`）；两种拒绝均无子进程、无新 run 根 |
| F-HOST-004-失败 | 失败 | 无快照旧检查点拒绝 fork | manifest 无 `platform_data` 或 `host-private/platform-data.json` 缺失 → `checkpoint_data_missing`（"checkpoint has no saved platform data"）；不自动补历史快照、不静默降级为原地接续；原地接续对该包仍按 015 可用（F-REG-001） |
| F-HOST-005-边界 | 边界 | 快照文件被改/被替换为符号链接 | `file_digest` 与 manifest `platform_data.digest` 不符或路径为 symlink → `artifact_changed`（"platform snapshot digest mismatch"）；`inspect_checkpoints` 的 issues 含 `"platform data snapshot is missing or changed"` 且 `fork_resume.available == false` |
| F-HOST-006-失败 | 失败 | scope/handoff/新 run 冲突/审批失效 | 快照 `project_id`/`ontology_ids` 与 `production_resume_bindings` 不符 → `snapshot_scope_mismatch`；`production_handoff` 包 → `checkpoint_kind_mode_mismatch`（"handoff requires acceptance"）；新 run 根已存在 → `resume_new_run_exists`；源审批失效 → `approval_binding_changed`；源 run/检查点不被改写、不换 ID 重试 |
| F-HOST-007-失败 | 失败 | 源 writer 未停止 | `state.json` 状态不可得或写者活跃（`source_writer_settles_recovery` 不成立）→ `source_active`（"stop source writer before forking"）；fork 前不产生任何平台写入 |
| F-HOST-008-成功 | 成功 | inspect 的 fork_resume 视图 | 有快照、verify 无 issue 且非 handoff 包 → `fork_resume = {available: true, snapshot: <manifest.platform_data 引用>, requires: "explicit fork_reason and stopped source writer"}`；无数据旧包 `available: false`；inspect 只读（run 树 digest 前后不变） |
| F-HOST-009-边界 | 边界 | HTTP 通道错误映射与重试语义 | 服务端 409 带 code → `CheckpointError` 原码透传（如 `snapshot_write_unsettled`/`fork_target_exists`）；无 code → `checkpoint_data_failed`；网络层失败：capture → `checkpoint_data_unavailable`（retryable，retry 提示 retry capture）；fork → `fork_result_unknown`（不可重试，retry 提示 "inspect platform state before retrying"，禁止自动重试或换新项目绕过） |
| F-HOST-010-成功 | 成功 | 预分配目标 ID 先落盘（合同 5） | fork HTTP 调用之前：`prepare_fork_plan` 以 `uuid4` 预分配目标 project_id、`uuid5(target, 旧 id)` 预分配 ontology_ids；`write_recovery_files` 先写含 `origin.fork_pending = {target_project_id, ontology_ids, snapshot_digest}` 的恢复文件（`recovery/*.json` 0600）；fork 成功后 `origin.platform_fork` 落位、`fork_pending` 移除、`plan.scope`/run.scope/角色包以服务端返回更新并重写恢复文件；fork 失败时新 run 根保留 `fork_pending` 供读回（与 F-FORK-007/F-HOST-009 共同构成 pending 语义） |
| F-HOST-011-失败 | 失败 | fork 缺宿主平台凭据 | `prepare_from_checkpoint(fork_reason=…)` 无 `canonical_admin_key` → `CheckpointError checkpoint_data_credentials_missing`（"fork requires the host platform credential"，obj=`platform_data`，phase=`checkpoint-fork`）；发生在任何平台写入之前 |

### E 组（REG，回归与隔离）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| F-REG-001-回归 | 回归 | 默认原地接续不变 | 不传 `fork_reason`：CLI/宿主工具/runner 均走 `prepare_recovery_plan`（非 `prepare_fork_plan`）；argv 不含 `--fork-reason`；015 既有接续、settle、写门（`write_unreconciled` 等）行为与既有测试一致；`test_r30015_checkpoints.py`（含 `checkpoint_data_standin` 回归更新）与 015 resume 套件全过 |
| F-REG-002-回归 | 回归 | 保存路径增量不越界 | `platform_bindings` 无 `project_id` 的 run 保存不发起 capture（无 HTTP 调用）；015 既有保存用例经 standin 注入通过，且 standin 不掩盖真实凭据路径（真实路径由 F-SNAP-002 证明拒绝语义）；保存的数据捕获与写位置读取在同一 admission 窗口（`begin_capture/end_capture` 包裹，015 drain 语义不变） |
| F-REG-003-回归 | 回归 | 源侧不可变 | `prepare_fork_plan` 对源 run 根只读（树 digest 前后不变）；fork 完成后源 run 根、`checkpoints/` 目录与旧 unknown 结论未被改写、未清账 |
| F-REG-004-回归 | 回归 | 全量基线 | 后端与 Team 两套全量失败清单与已登记基线 diff 无新增（§2.6 命令）；既有失败须能对应登记原因 |
| F-REG-005-回归 | 回归 | 快照数据不进角色可读产物 | 哨兵快照内容不出现在角色包、任务文本与恢复文件之外的任何产物；`platform-data.json` 不复制进新 run 角色产物（断言任务文本无该文件名）；全树泄漏扫描无凭据值 |

## 4. 完成门（确定性 vs 真实证据，分开陈述）

- **G1 确定性完成门（I 验收 PASS 条件）**：§3 全部用例按预期；两套全量基线失败清单无新增（F-REG-004）；文档一致——需求条目与状态行（requirements-v3.0.md L1582/L239）、设计文档、`docs/reference/api.md` 两条 checkpoint-data 路由、CLI `--fork-reason` help 文案与实现一致；新增文件 Ruff 通过（`runner.py` 全文件 Ruff 存在 HEAD 遗留的 3 个未用 import 与 1 个未用局部变量，本次未扩改，不构成新增缺陷）。
- **G2 真实证据门（不并入 I 验收，独立轮执行）**：真实 PostgreSQL/Oxigraph 数据往返（含并发写锁下"SQL 与 RDF 同代"时序）通过；按 AGENTS.md Runtime Restart Rules 重启 `ontology-platform.service` 后，经 `CHECKPOINT_DATA_HTTP_BASE_URL` 走真实认证 HTTP 的保存/fork/封存读写通过；临时资源与测试 ApiKey 由 finally 清理并复核。任一未达成按 §5.4 记 gap，需求不得标完成（G1 可先行给出确定性面结论）。
- **明确排除**：真实 LLM 建模与独立语义验收**不在本需求完成门内**——按需求登记边界（合同第 6 点与非目标），机械与数据往返证据不得被表述为语义建模或语义验收通过；`derived_results: "recompute_required"` 即为此边界的落码形态。

## 5. 真实运行时检查（L0）

### 5.1 前置

- 本地栈就绪（`./scripts/start-local.sh` 或 systemd 单元管理）；`Settings` 指向真实 PostgreSQL 与 Oxigraph。
- 直连模式：backend 目录 `RUN_CHECKPOINT_DATA_LIVE=1 uv run pytest tests/test_checkpoint_data_live.py -q`（不带 `CHECKPOINT_DATA_HTTP_BASE_URL`，服务层直调，仍用真实库与图存储）。

### 5.2 直连模式核验点（开发自测已跑通，独立轮重跑）

- **锁与快照时序**：写者先持源 Ontology `FOR UPDATE` 行锁；capture 线程发起后被阻塞（`future.result(timeout=0.1)` 超时仍在等）；写者随后改**另一 SQL 行**（Project.description，锁行本身不变，防 serialization error 假阳性）并写 RDF 后提交；capture 返回的快照必须同时含新 SQL（"Saved generation"）与新 RDF（"Saved"）——证明快照建立在写者完成后（先锁后 REPEATABLE READ）。
- fork 后：源 Ontology `status == "archived"`；新图内容 "Saved"、源图保留 fork 后写入 "Later"；新图可继续写 "Continued" 且源图不受影响；新 Ontology workspace ready。
- 可选加测（不阻塞）：在已激活事务的 session 上调 capture → `snapshot_transaction_active`（该分支仅 PostgreSQL 方言可达）。

### 5.3 服务重启后 HTTP 往返（G2 必需）

1. 按 AGENTS.md：`systemctl --user restart ontology-platform.service`；`systemctl --user --no-pager --full status ontology-platform.service` 确认 active；`curl --fail http://127.0.0.1:8001/api/health` 与 `curl --fail http://127.0.0.1:5173/` 通过；失败查 `journalctl --user -u ontology-platform.service` 并记录阻断。
2. backend 目录 `RUN_CHECKPOINT_DATA_LIVE=1 CHECKPOINT_DATA_HTTP_BASE_URL=http://127.0.0.1:8001 uv run pytest tests/test_checkpoint_data_live.py -q`：测试自建组织 admin key，经真实认证 HTTP 完成 capture（含 §5.2 时序）→ fork（200，`project_id == target_project_id`）→ 源封存（PATCH 源 409 `checkpoint_source_archived`、GET 源 200）。
3. 重启语义备注：已启动的旧 MCP 进程需重新加载代码后才暴露 `fork_reason` 参数（设计记录）；独立轮冷启动 stdio 会话天然加载新代码。

### 5.4 gap 记录与清理

- 任何未走通项记录：动作、请求/目标 ID、原码、证据路径、归因（接口缺陷/运行时缺陷/环境），不据此宣布 G2 通过或 FAIL 之外的语义结论。
- `fork_result_unknown` 人工恢复规程（决策 14）：先以预分配的 target_project_id 经平台读回确认目标 Project 是否已创建（已创建即视为首次分叉已生效，读回其 identity_mapping 收尾，不得再发起 fork）；确认未创建才换新 `new_run_id` 重跑。误判重试的后果是同快照双项目 + 源 ARCHIVE_KEY 指针被覆盖，按 gap 记录并人工修正指针。
- 清理：确认测试 finally 已删临时 Project/Ontology/图/ApiKey（SQL 与 RDF 双面复核）；撤销/删除本轮注入的任何真实凭据；凭据字面值不出现在记录、日志与本计划；源检查点的 `host-private/platform-data.json` 保留为证据，不删除。

## 6. 决策处置记录（原开放决策均已裁决，无新增开放项）

1. 保存接口不新增宿主入口：继续用 `save_checkpoint`，绑定平台时自动附带数据（设计"宿主使用"）。
2. PostgreSQL 一致性取"独立连接先持 Ontology 行锁、再建立 REPEATABLE READ 只读快照"，避免等锁期间先建旧 SQL 快照随后读新 RDF。
3. 数据与检查点文件一起在 host-private 发布并校验摘要；不用恢复时的当前数据库冒充保存时数据。
4. 旧检查点无快照明确不支持 fork，不自动补历史快照。
5. 图 IRI：默认工作区前缀确定性重映射；非属主前缀映射到 `<prefix>/fork/<uuid4>`。
6. statement origin 保留生产者来源为 source reference（`legacy_unknown` + origin_metadata），不声明旧生产者在新项目运行过。
7. fork 前先落盘预分配目标 ID（`fork_pending`）；COMMIT 响应丢失保留新图与预分配身份供读回，不把"收到异常"当 SQL 零写入证据。
8. capture 网络失败可重试（`checkpoint_data_unavailable`）；fork 结果不明不可自动重试（`fork_result_unknown`，先 inspect 平台状态）。
9. acceptance 模式不接受 fork（CLI 与宿主工具双面拒绝）。
10. 派生推理/验证/检索投影在新项目重新计算（`derived_results: "recompute_required"`），旧结果不声明有效。
11. 保存的数据捕获并入既有写 admission 窗口（`begin_capture/end_capture`），不引入跨 run 平台级静默。
12. 数据接口仅组织管理员（HTTP admin scope + `is_org_admin` 双门），角色不直接调用；封存门 ownership 先行，不跨项目泄露封存状态。
13. 分叉封存按**源项目整体**执行：源项目全部 Ontology 一并 `archived`，含不在快照范围内的 Ontology（与需求原文"旧项目封存为只读证据（不删除、不再写入）"一致；范围外 Ontology 随项目只读、数据不在 fork 副本内）。`prepare_fork_plan` 只对账 manifest 恢复绑定与快照 scope，不对账"项目全部 Ontology"——多 Ontology 项目部分绑定的 fork 由调用方自行确认后果（评审 Round 1 假设确认，登记为设计语义）。
14. `fork_result_unknown` 后的人工恢复路径：自动重试已禁止；人工经平台读回确认目标 Project 未创建后，须换新 `new_run_id` 重跑（旧 run 根会 `resume_new_run_exists`），服务端以新预分配 `uuid4` 目标从同一快照再导入。**风险**：若人工误判"未提交"而实际已 COMMIT，会从同一快照建立第二个新项目并覆盖源 ARCHIVE_KEY 指针——操作员必须先按 target_project_id 读回确认（§5.4）。

## 7. D0 记录（2026-09-18 计划核对，静态事实）

- 被测状态：22 个暂存文件（+1795/-40），基点 HEAD `b677a44`；另有无关未跟踪目录（`.codex/agents/`、`docs/diagrams/modeling-team-guide/`）与未暂存 `skills/modeling-dev-loop/SKILL.md`，不在被测范围。
- 接口：`POST /api/checkpoint-data/capture`（`CaptureRequest{project_id, ontology_ids(min_length=1)}`）、`POST /api/checkpoint-data/fork`（`ForkRequest{snapshot, name(1..200), target_project_id: UUID}`），注册于 `backend/app/api/routes.py` 与 `docs/reference/api.md`。
- 权限门：`_ADMIN_PATHS` 含 `/api/checkpoint-data`（前缀匹配 → scope admin，`security/http.py` L85–96）；`require_host` 再查 `principal.is_org_admin`，非组织管理员 403 `{"code": "forbidden_scope"}`——项目级 admin key（`r008_client` 的 `p1_admin_key`，scopes=["admin"] 但绑定项目）同样被拒（开发自测已证 403）。
- 服务层错误码清单（HTTP 均 409 `{code, message}`）：`snapshot_transaction_active`（仅 PostgreSQL 方言且事务已激活）、`snapshot_scope_missing`、`snapshot_write_unsettled`、`snapshot_external_graph`、`snapshot_invalid`（digest/表清单/scope/graph 清单四类）、`fork_target_exists`、`fork_cleanup_incomplete`、`fork_commit_unknown`；capture 端点 finally `session.rollback()` 释放 Ontology 锁。
- 封存错误面：HTTP `_check_checkpoint_archive` → 409 `checkpoint_source_archived`（仅 UNSAFE_METHODS、scope≠read、非 `/api/checkpoint-data/` 前缀；资源 id 取自 path params 与 JSON body）；`semantic.py` dataset load（trig/n-quads/json-ld）与 SPARQL 编辑 → `LockedSemanticGraph("checkpoint_source_archived: source Project is read-only")`；`semantic_canonical_write.py` → `CanonicalWriteBlocked` 同前缀（Ontology 级为 "source Ontology is read-only"）；MCP `_authorize_tool` 对 `mutates_state` 工具 → `PermissionError` 同文案。
- 团队侧错误码清单：`fork_reason_required`、`checkpoint_data_missing`、`checkpoint_kind_mode_mismatch`、`artifact_changed`、`snapshot_scope_mismatch`、`resume_new_run_exists`、`source_active`、`approval_binding_changed`、`checkpoint_data_failed`（服务端无 code 兜底）、`checkpoint_data_unavailable`（capture 网络失败，retryable）、`fork_result_unknown`（fork 网络失败，不可自动重试）、`checkpoint_data_credentials_missing`（save 与 fork 两处）、`checkpoint_write_unreconciled`（数据捕获前 drain 失败）；宿主工具层 `launch_arguments_invalid`（fork_reason 需 production+非空）。
- CLI：`checkpoint resume` 新增 `--fork-reason`（help："Explicitly restore saved data into a new Project; record why"）；acceptance+fork 在 run loader 之前拒绝（stderr `checkpoint failed: fork requires production mode`，退出码 2）；fork 成功后 `resume_lock.release()` + `acquire_root_run_lock(args.new_run_id, runs_root)`；`fork_reason is not None` 才透传。
- 宿主工具：`resume_from_checkpoint` 新增 `fork_reason: str | None`（校验块 `host_ops.py` ≈L3171–3178；argv 条件追加 `--fork-reason`）；MCP 工具 `tool_resume_from_checkpoint` 透传同名可选参数（`host_ops_mcp.py`）。
- 文件落位与校验：`PLATFORM_DATA_PATH = "host-private/platform-data.json"`；保存时 0600/0700/fsync；manifest `platform_data = {path, digest("sha256:"+文件字节), snapshot_digest}`；`_verify_package` 对缺失/symlink/摘要不符记 issue `"platform data snapshot is missing or changed"`；`_checkpoint_inspection.fork_resume = {available, snapshot, requires}`（available = 有数据且无 issue 且非 handoff）。
- 保存路径：`runner._save_run_checkpoint` 以 `begin_capture/end_capture` 包裹全流程；`platform_bindings.project_id` 存在时先 `wait_until_drained` 再 capture，凭据取 `canonical_admin_key or scope.admin_key`。
- fork 执行序：`prepare_from_checkpoint(fork_reason=…)` → 凭据门 → `prepare_fork_plan`（校验 + 预分配 uuid4/uuid5 + origin/imports/scope 构造，accounting `semantic_starts: 1, kind: "fork"`）→ `run.prepare` → `_materialize_checkpoint_recovery` → 写 `fork_pending` 恢复文件 → POST fork → 更新 scope/origin（`platform_fork`）/imports（`identity_mappings`、`approval_rebinding`）/角色包（`fork_scope`、`identity_mapping`、重发布指令）→ 重写恢复文件。
- 身份重映射：平台 ID `uuid5(target namespace, 旧 id)`；statement identity 以 `statement_id_for_quad(…, 新图)` 重算、occurrence 以 `occurrence_id_for` 重算、fact binding `fact_id` 同步重算；导入表恰 26 张（以 `model_types` 表名集合为准；2026-09-18 计划评审 Round 1 纠正原误记的"27"），不含 `BuildSessionModel`/`ModelingBatchModel`/attempt/`OntologyLeaseModel`/`ApiKeyModel`。
- 完成索引来源：capture 只收 `attempt.mode != "dry_run"` 且 item `status == "applied"` 的结果；fork 的 reconciliation 仅由 `snapshot.completed_operations` 构造；`origin_chain_roots` 遇 `r3-0-017-fork/v1` 停止链回溯。
- live 测试形态：`RUN_CHECKPOINT_DATA_LIVE=1` opt-in；可选 `CHECKPOINT_DATA_HTTP_BASE_URL` 切真实 HTTP；finally 清理含"COMMIT 后身份再发现"（按 project_ids 反查 ontologies/graphs）。
- 基线情况（按设计文档 2026-09-18 验证记录，独立轮须实跑复核）：backend `uv run pytest -q` 1013 passed / 37 skipped（0 failed）；Team 全量 2006 passed / 1 skipped / 339 subtests passed（0 failed）；live 直连与重启后 HTTP 均 PASS。注意：R3.0-016 S2 计划早前登记的 7 个 `test_deepseek_codex_runtime` 失败在最新记录中未再出现——以独立轮实跑失败清单为准，不做总数推断。`runner.py` 全文件 Ruff 有 HEAD 遗留 3 个未用 import + 1 个未用局部变量；新增文件 Ruff 通过；GitNexus 索引不完整（公共写入口被标 Critical），影响核对以直接调用点检查 + 全量回归 + 真实接口测试代替。
- 开发自测覆盖缺口（评审 Round 1 High-2 核实）：三份新测试文件均未种入语句级 lineage 行（`semantic_statement_occurrences`/`origins`/`premises`/`fact_evidence_bindings` 输入恒为空表），`checkpoint_data.py` L334–350 身份重算与 L405–415 origin 改写在既有测试中未被执行——由 F-FORK-012 在独立验收轮补证。
- 既有问题（不计入本需求缺陷，评审 Round 1 假设 3）：`POST /api/semantic/graphs` 等图创建路径不持 Ontology 行锁（015 既有面；registry 行在 SQL 快照外，撕裂风险低），本需求的锁时序证明覆盖 dataset load / SPARQL edit / canonical write（含 batch apply）三条主写路径。

## 8. 独立验收 Round 1（待 requirement_tester 追加）

**结论**：G1 确定性完成门 **PASS**（0 缺陷）；G2 真实证据门 **PASS**（直连 live、服务重启、真实认证 HTTP 三段全过，清理复核干净）。两门分开陈述，G2 通过不并入 I 验收语义（§4 边界不变）。

- 执行者：requirement_tester（独立于实现会话）；日期：2026-09-18；轮次：Round 1。
- 被测状态：工作树 = 基点 HEAD `b677a44` + 暂存 22 文件（+1795/−40）+ 本计划文件（未跟踪）；未提交任何内容；无关未暂存/未跟踪项未触碰。
- 临时测试文件（跑完即删，本节为唯一证据记录）：`backend/tests/test_r30017_round1_fork012.py`（12 用例）、`modeling_team/tests/test_r30017_round1_host.py`（13 用例）；`workspaces/modeling-runs` 扫描确认无 r3017* 残留 run 根。

### 8.1 §3 用例结果（全部 PASS，0 FAIL / 0 BLOCKED）

| ID | 证据来源 | 结果 |
| --- | --- | --- |
| F-SNAP-001 | dev `backend/tests/test_checkpoint_data.py`（随基线全过：capture payload 恰为 `{project_id, ontology_ids}`、manifest `platform_data{path,digest,snapshot_digest}`、0600/0700/fsync、重放 `reused`） | PASS |
| F-SNAP-002 | 独立 team 临时 test_snap002：freeze 不杀 run（evidence 落 `checkpoint-save-failed`，code=`checkpoint_data_credentials_missing`、obj=`platform_data`、phase=`checkpoint-save`、文案一致；无新包）；直接 `_save_run_checkpoint` 同码 raise；既有检查点树 digest 前后不变；补凭据后 `saved`，再失去凭据不破坏已发布包 | PASS |
| F-SNAP-003 | 独立 backend 临时 test_snap003：fence 命中任一 Ontology → `snapshot_write_unsettled`（"An apply fence is still present"） | PASS |
| F-SNAP-004 | 独立 backend 临时 test_snap004：`schema_version` 一致；`tables` 表名集合 == 被测 `model_types` 26 表（锚定代码集合断言）；`completed_operations` 仅含非 dry_run 且 item applied 条目（8 字段逐项）；`digest` 以被测 `snapshot_digest` 复算一致 | PASS |
| F-SNAP-005 | 独立 backend 临时 test_snap005：Project/Ontology 缺失或不属同项目 → `snapshot_scope_missing` 两文案各自命中；Graph Set 含 registry 外图 → `snapshot_external_graph`；均无写入 | PASS |
| F-SNAP-006 | dev 套件（多 Ontology、自定义 shapes 图确定性重映射、空图 fork）随基线全过 | PASS |
| F-FORK-001 | dev 套件（保存后源侧写入不入 fork、evidence excerpt 冻结值、FK 按映射重挂、业务 IRI/保护集保留、workspace ready 且 set 不同）+ §8.3 live 同点 | PASS |
| F-FORK-002 | 独立 backend 临时 test_fork002：平台 ID `uuid5(target, 旧 id)`、默认工作区图确定性重映射、非属主图 → `<prefix>/fork/<uuid4>`、revision `content_hash` 以新图实存内容回填、`derived_results: "recompute_required"`；statement/occurrence/fact_id 重算在 F-FORK-012 独立验证 | PASS |
| F-FORK-003 | dev 套件（reconciliation 全由 `completed_operations` 构造、四类计数为空）+ 独立 team 临时 `plan()` 注入"读即断言失败" readback（fork 未读源可变批次）+ `origin.old_chain_writes == "unchanged; no reconciliation claim"` | PASS |
| F-FORK-004 | dev 套件（approvals 原件、imports `identity_mappings`/`approval_rebinding`、角色包 `fork_scope`）+ origin 期望在 F-FORK-012(c) 非空行上验证 | PASS |
| F-FORK-005 | 独立 backend 临时 test_fork005：篡改摘要/缺表/scope 不符/graph 清单多余/foreign owner → `snapshot_invalid` 四类各自命中；全部无 SQL 写入（源 Project 行数不变） | PASS |
| F-FORK-006 | 独立 backend 临时 test_fork006：PUT 失败 → 回滚+逐图 drop；drop 再失败 → `fork_cleanup_incomplete` 报未清理图 IRI 与前缀；源图逐字节不变；无新 Project 行 | PASS |
| F-FORK-007 | dev 套件（COMMIT 后注入异常 → `fork_commit_unknown`，message 含 target_project_id 与保留语义，新图与身份可读回，不自动重试） | PASS |
| F-FORK-008 | dev 套件（`fork_target_exists` 409，不覆盖既有目标） | PASS |
| F-FORK-009 | 独立 backend 临时 test_fork009：`SemanticGraphRevision.last_edit_audit_id`/`EvidenceAssociation.edit_audit_id`/occurrence `invalidated_by_audit_id` 三处置空；新 Ontology `external_mappings.checkpoint_fork_origin={source_project_id, source_ontology_id, snapshot_digest}` 且无源 ARCHIVE_KEY | PASS |
| F-FORK-010 | 独立 backend 临时 test_fork010：源预置 BuildSession/Batch(attempt+item_results)/Lease/ApiKey 后 fork，目标项目这些表零行 | PASS |
| F-FORK-011 | dev 套件（`origin_chain_roots` 遇 `r3-0-017-fork/v1` 停止，新链只含 `[fork, later]`；新图独立写链） | PASS |
| F-FORK-012 | 独立 backend 临时 test_fork012（计划指定由独立轮构造，真实 capture+fork 于进程内 sqlite+假 Store）：种入 occurrence×2（asserted/active + rule_derived/invalidated）、origin×2（modeling_item/rule_run）、premise×1、fact binding×1 后：(a) 新 occurrence `id == occurrence_id_for(statement_id_for_quad(s,p,o,新图IRI), revision)` 且新 statement_id ≠ 旧（图 IRI 参与身份）；(b) 新 binding `fact_id == 新 statement_id`；(c) origin 持久化 `legacy_unknown` 且 metadata 含 `fork_source_project_id/snapshot_digest/source_origin_kind/source_origin_id` 四键、两种来源各自保留；(d) premise `derived_occurrence_id`/`premise_occurrence_id` 双端指向新 occurrence；(e) 新图与源图逐三元组等价、业务 IRI 不变 | PASS |
| F-SEAL-001 | 独立 backend 临时 test_seal001：源 Ontology `status=="archived"` + `checkpoint_fork_archive={target_project_id, snapshot_digest}`；`project_is_checkpoint_archived` 源真/目标假 | PASS |
| F-SEAL-002 | 独立 backend 临时 test_seal002（服务层五路：SPARQL update、turtle 定点、trig dataset load、canonical `_lock_ontology`、MCP `_authorize_tool` 均 `checkpoint_source_archived` 前缀阻断）+ dev HTTP 面 + §8.3 live（PATCH 源 409 / GET 200） | PASS |
| F-SEAL-003 | 独立 backend 临时 test_seal003：GET 源 200；`/api/checkpoint-data/` 前缀豁免（封存后 capture 复跑 200）；未知 Project PATCH 404（ownership 先于封存判定，不泄露封存态）；源 PATCH 409 typed `checkpoint_source_archived` | PASS |
| F-HOST-001 | 独立 team 临时 test_host001_cli（真实 CLI 子进程，种子源 run 落 RUNS_ROOT）：production+`--fork-reason` → payload `checkpoint_data_missing`（该码仅 fork prepare 路径可达，证明 kwarg 进入 `prepare_from_checkpoint`）；源树 digest 不变；无新 run 根；不传参路径由 F-REG-001 证 | PASS（方法注记见 8.5-1） |
| F-HOST-002 | 独立 team 临时 test_host002（宿主工具 acceptance+fork → `launch_arguments_invalid`，文案/obj/next_action 全验，`no_spawn` 断言零子进程）+ test_host002_cli（真实 CLI：run loader 之前拒绝，stderr `checkpoint failed: fork requires production mode`、退出码 2、无 Traceback、无 run 根存在性报错、无新 run 根） | PASS |
| F-HOST-003 | 独立 team 临时：宿主工具空串/纯空白/非字符串三类 → `launch_arguments_invalid`（obj=`fork_reason`）；CLI 纯空白字符串 → prepare 层 `fork_reason_required`（"fork needs an explicit reason"）；均无子进程、无新 run 根 | PASS |
| F-HOST-004 | 独立 team 临时 test_host001_cli（无数据旧包 production fork → `checkpoint_data_missing`，无静默降级为原地接续）+ dev 套件；该包原地接续仍可用由 015 回归证 | PASS |
| F-HOST-005 | dev 套件（摘要不符 → `artifact_changed` "platform snapshot digest mismatch"）+ 独立 team 临时 test_host008（篡改 platform-data.json 字节 → inspect issues 含 "platform data snapshot is missing or changed"、`available false`）；symlink 判定与摘要校验同守卫表达式（`checkpoints.py` L336–341），code-read 核实 | PASS（symlink 分支为代码读） |
| F-HOST-006 | 独立 team 临时 test_host006 两节：handoff 包 → `checkpoint_kind_mode_mismatch`；快照 project 不符 → `snapshot_scope_mismatch`（源树不变）；占用新 run 根（源根同级）→ `resume_new_run_exists`；保存后审批置空 → `approval_binding_changed` | PASS |
| F-HOST-007 | 独立 team 临时 test_host007：state.json 缺失 → `source_active`（"source writer state is unavailable"，obj=`state.json`）；state=RUNNING 无 settlement → `source_active`（"stop source writer before forking"，obj=`source_run_id`）；两分支源树 digest 均不变、fork 前无平台写入 | PASS（文案分支见 8.5-2） |
| F-HOST-008 | 独立 team 临时 test_host008：`fork_resume={available true, snapshot==manifest.platform_data, requires "explicit fork_reason and stopped source writer"}`；无数据旧包 `available false`；inspect 只读（树 digest 前后不变） | PASS |
| F-HOST-009 | 独立 team 临时 test_host009：409 带 code 原码透传（`snapshot_write_unsettled` retryable）；500 无 code → `checkpoint_data_failed`；网络层 capture → `checkpoint_data_unavailable`（retryable，"retry capture"）；fork 网络/OS 失败 → `fork_result_unknown`（不可重试，"inspect platform state before retrying"） | PASS |
| F-HOST-010 | 失败半：独立 team 临时 test_host010（fork 动作抛 `fork_result_unknown` 后 `recovery/origin.json` 保留 `fork_pending={uuid4 target_project_id, [uuid5(target,"ontology")], snapshot_digest}`，run.scope 携带预分配身份供读回；恢复文件无凭据值、无哨兵）；成功半：dev 套件（`platform_fork` 落位、`fork_pending` 移除、角色包 `fork_scope`/`identity_mapping`） | PASS |
| F-HOST-011 | 独立 team 临时 test_host011：无 `canonical_admin_key` 时 `prepare_from_checkpoint(fork_reason=…)` → `checkpoint_data_credentials_missing`（"fork requires the host platform credential"，obj=`platform_data`，phase=`checkpoint-fork`），先于任何 run 创建（无 run 根、源树不变） | PASS |
| F-REG-001 | 015 既有套件（`test_r30015_checkpoints.py` 含 standin 回归更新、015 resume 套件）随团队基线全过；不传 `--fork-reason` 即原地 `prepare_recovery_plan` 路径 | PASS |
| F-REG-002 | 负向：独立 team 临时 test_reg002（unbound 保存注入"调用即断言失败"数据通道替身未触发；evidence 终于 `checkpoint-saved`；manifest 无 `platform_bindings.project_id`、无 `platform_data` 键）；`begin_capture/end_capture` 包裹与 drain 语义由 015 回归 + F-SNAP-002 共同证 | PASS |
| F-REG-003 | 独立 team 临时 test_reg003：plan 前后源树 digest 不变；`old_chain_writes=="unchanged; no reconciliation claim"`；`fork_reason`/`authorization_reference` 记录；accounting `{semantic_starts: 1, kind: "fork"}` | PASS |
| F-REG-004 | §8.2（两套失败清单为空） | PASS |
| F-REG-005 | §8.4（用例内断言 + 全树扫描） | PASS |

### 8.2 F-REG-004 基线（按失败清单比对，非总数）

- 后端：`cd backend && uv run pytest -q` → **1025 passed, 37 skipped, 0 failed**（登记 1013 + 独立临时 12；失败清单为空）。
- Team：backend 目录 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q` → **2019 passed, 1 skipped, 339 subtests passed, 0 failed**（登记 2006 + 独立临时 13；失败清单为空）。
- 两套失败清单均空 → 与登记基线零 diff、无新增失败；§7 提示历史 7 个 `test_deepseek_codex_runtime` 失败未复现。

### 8.3 G2 真实证据门

1. 直连：`cd backend && RUN_CHECKPOINT_DATA_LIVE=1 uv run pytest tests/test_checkpoint_data_live.py -q` → **1 passed**（真实 PostgreSQL/Oxigraph；写锁时序证：capture 阻塞于源 Ontology FOR UPDATE 后建快照，快照同时含写者新 SQL "Saved generation" 与新 RDF "Saved"；fork 后源 archived、新图 "Saved"、新图可继续写 "Continued" 且源图不受影响）。
2. 重启（AGENTS.md Runtime Restart Rules）：`systemctl --user restart ontology-platform.service` → **active (running) since 2026-09-18 22:49:17 +08, Main PID 2570490**；`curl --fail http://127.0.0.1:8001/api/health` → `{"status":"ok"}`；`curl --fail http://127.0.0.1:5173/` → HTTP 200。
3. 重启后真实认证 HTTP：`RUN_CHECKPOINT_DATA_LIVE=1 CHECKPOINT_DATA_HTTP_BASE_URL=http://127.0.0.1:8001 uv run pytest tests/test_checkpoint_data_live.py -q` → **1 passed**（测试自建组织 admin key，经真实 HTTP capture（含时序）→ fork 200 `project_id == target_project_id` → 源 PATCH 409 `checkpoint_source_archived` / GET 200）。
4. 清理复核（finally 确实执行，SQL 与 RDF 双面）：Projects 按 "R3017 live source"/"R3017 live fork" 反查 → 0 行；ApiKeys 按 name "r3017-live-check" → 0 行；Oxigraph 全命名图 SPARQL 查 `urn:r3017:` 主体 → 0 bindings。源检查点 host-private 文件按 §5.4 保留未动。

### 8.4 泄漏扫描（F-REG-005）

- 哨兵 `HOST-PRIVATE-ONLY` 全仓扫描（排除 .git/.venv/__pycache__）：仅命中两份测试文件的 fixture 定义处（各自含角色包/任务文本/恢复文件负向断言）与本计划文档示例；`workspaces/`（含 modeling-runs 全部 run 树）零命中。
- 团队侧假凭据标记（随机假值，非真实密钥）仅存在于测试文件定义处；本轮运行树无 r3017* 残留目录。
- 用例内断言：fork 失败路径 `recovery/*.json` 无凭据值、无哨兵；任务文本无 `platform-data.json` 字样、无哨兵；dev 用例断言角色包无哨兵。
- 真实 admin key 明文仅存在于 live 测试进程内存与请求头（测试自建并在 finally 删除）；未落入本轮任何断言、日志、记录或本节文字。

### 8.5 缺陷与注记

**缺陷：0 项。** 注记（不计缺陷）：

1. F-HOST-001 的静态 monkeypatch kwargs-record 断言未单独执行，以真实 CLI 子进程动态行为证明替代（`checkpoint_data_missing` 仅 fork prepare 路径可达 → `fork_reason` kwarg 确已传入）+ `__main__.py` argv 条件构造（`fork_reason is not None` 才透传）code-read；等价覆盖合同意图。
2. F-HOST-007 计划文本将 "stop source writer before forking" 覆盖两分支；实现给"状态不可得"分支独立文案 "source writer state is unavailable"（obj=`state.json`），fail-closed 语义一致，属计划措辞不精确而非实现缺陷。
3. `modeling_team/runner.py` 全文件 Ruff 4 项（3 未用 import + 1 未用局部变量）经 `git show b677a44:modeling_team/runner.py` 比对与 HEAD 逐字节一致——遗留项，非本次新增（§4 已登记）。其余 7 个新增/改动 .py 文件 Ruff 全过。

### 8.6 未执行/部分执行与残余风险

- 未执行整例：无。部分执行三处已标注：F-HOST-001（方法注记 1）、F-HOST-005（symlink 分支 code-read，摘要分支已实跑）、F-HOST-010（成功半由 dev 套件证，失败半独立实跑）。
- 残余风险：真实 LLM 建模与独立语义验收不在本需求完成门内（§4 明确排除，`derived_results: "recompute_required"` 即边界落码）；GitNexus 索引不完整（§7 登记），影响面以直接调用点检查 + 两套全量回归 + 真实接口测试代替；决策 13（源项目整体封存，范围外 Ontology 随项目只读、数据不进 fork 副本）与决策 14（`fork_result_unknown` 人工恢复纪律）仅机械层验证，真实操作依赖 §5.4 规程。
- 合规：本轮全程未在记录中写入任何密钥明文；未修改产品代码与暂存集；临时测试文件与基线输出临时文件已删除。

## 9. 交付后补充（2026-09-19 开发自测，非独立验收轮）

**性质声明**：本节为开发自测补证，**不是独立验收轮**，不改写 §8 既有记录；§8 的 G1/G2 结论与本节互不影响。被测状态：基点 HEAD `7697601`，工作树另含宿主未提交的 `docs/requirements/requirements-v3.0.md` 修订（2026-09-19 外部评审 F1–F9 采纳结果）与 `skills/modeling-dev-loop/SKILL.md`、`.codex/agents/`、`docs/diagrams/modeling-team-guide/` 等他人改动——全部未触碰、未纳入本轮提交。

- **背景**：需求 2026-09-19 修订把合同第 5 点收窄为"封存后项目元数据与落库证据仍可读，经治理语义查询按既有 archived 就绪性返回 not ready（409 `scope_not_ready`）；范围外 Ontology 无 fork 副本，同样不可查询；语义查询在新项目继续"。既有 F-SEAL-002/003 只证了 `GET` 200 与写阻断，治理语义读路径零覆盖，故新增 F-SEAL-004 补证（§3 C 组已登记）。
- **被测代码事实（只读核对，未改产品代码）**：fork 提交时源项目全部 Ontology 置 `status="archived"`（`backend/app/services/checkpoint_data.py` L437–450）；`OntologyQueryReadinessEvaluator` 对 archived 直接判不可查询 `reason="ontology_archived"`（`authorized_scope_discovery.py` L55–56，R3.0-004 引入的既有平台语义，非本需求缺陷）；查询范围解析在全部 Ontology 被排除时抛 `SemanticQueryScopeNotReady`（HTTP 409、code `scope_not_ready`，`semantic_query_scope.py` L138–156）。
- **分层事实（封存写门 × 治理语义查询，实测钉住）**：`required_scope` 对 `/api/semantic/context:query` 与 `/api/semantic/sparql:query` 一律返回 `"read"`（`security/http.py` L109–110），`_check_checkpoint_archive` 对 `scope=="read"` 直接放行（同文件 L579）——治理语义查询不被封存写门拦截，read key 与组织 admin key 同样到达 readiness 层得到 409 `scope_not_ready`；PATCH 等 UNSAFE 写路径则先被门拦为 409 `checkpoint_source_archived`（F-SEAL-002 语义不变）。两层机制在用例内同时钉住。
- **新增确定性用例**：`backend/tests/test_checkpoint_data_seal_read.py`（6 用例；进程内 sqlite + 假 RDF Store，真实 `CheckpointDataService.capture`+`fork` 产生封存态；源项目含快照范围外 Ontology `extra`；假 Store 的 `query_sparql` 若被封存源查询触达即断言失败——证明拒绝发生在 readiness 层而非空数据）：
  1. `test_sealed_source_project_scope_query_is_not_ready`：项目级 scoped SPARQL → `SemanticQueryScopeNotReady`（"Semantic query scope is not ready"、409、`scope_not_ready`），RDF Store 零触达；
  2. `test_sealed_source_ontology_scope_query_is_not_ready`：Ontology 级 scoped SPARQL → 409 `scope_not_ready`；resolver 直调同判（"One or more selected Ontology workspaces are not ready"）；
  3. `test_scope_discovery_reports_sealed_ontologies_as_not_queryable`：项目条目 `query_status="unavailable"`、两个 excluded Ontology 均 `reason="ontology_archived"`；ontology 条目 `status="archived"`、`queryable=false`、`unavailable_reason="ontology_archived"`；`queryable=true` 过滤下封存项目零条目；
  4. `test_out_of_scope_ontology_is_sealed_without_fork_copy`：`extra` 随 fork 一并 `archived`，不在 identity mapping、新项目仅 1 Ontology、其图内容不进新项目任一图，查询同样 409 `scope_not_ready`；
  5. `test_forked_project_continues_semantic_queries`：新项目 scope `"complete"`、命中唯一 fork Ontology、dataset 子句注入后到达 Store（合同"语义查询在新项目继续"）；
  6. `test_sealed_source_http_reads_and_semantic_query_not_ready`：真实 HTTP capture+fork 后 `GET /api/projects/<源>` 200、`PATCH` 409 `checkpoint_source_archived`（F-SEAL-002 对照）；`POST /api/semantic/sparql:query` 项目级与 Ontology 级均 409 `scope_not_ready`（read key 与 admin key 同判，RDF Store 零触达）；`GET /api/semantic/scopes:discover` 报 `archived`/`queryable=false`/`ontology_archived` 与项目 `unavailable`+excluded 明细。
- **执行结果**（backend 目录，`uv run pytest`；warnings 为既有 FastAPI/Starlette deprecation，与本轮无关）：

  | 命令 | 结果 |
  | --- | --- |
  | `uv run pytest tests/test_checkpoint_data_seal_read.py -q` | **6 passed, 5 warnings** |
  | `uv run pytest tests/test_checkpoint_data.py tests/test_checkpoint_data_seal_read.py -q` | **12 passed, 11 warnings** |
  | `uv run pytest tests/test_checkpoint_data.py tests/test_checkpoint_data_seal_read.py tests/test_authorized_scope_discovery.py tests/test_scoped_sparql_query.py tests/test_semantic_read_scope.py -q` | **70 passed, 13 warnings** |
  | `uv run ruff check tests/test_checkpoint_data_seal_read.py` | **All checks passed** |

- **实测纠偏登记（非缺陷）**：HTTP 用例初版按"封存门先拦 POST"的静态推断断言 `checkpoint_source_archived`，实测为 `scope_not_ready`；核对 `required_scope`/`_check_checkpoint_archive` 后确认语义查询端点因 read scope 豁免而不经封存门（见上分层事实），测试按实测行为修正。未改任何产品代码或需求文本来迁就测试。
- **GitNexus**：commit 前 `detect-changes --repo ontology-platform`（本轮编辑前后各跑一次，结论一致）→ 3 文件 4 符号、受影响流程 0、风险 low——4 个命中符号均为工作树内他人未提交的 requirements/SKILL 文档符号，第 3 个文件为本计划文档自身的修订（无符号映射）；本轮新增测试文件为未跟踪新文件、不涉及任何产品符号。索引不完整的既有登记（§7）不变；影响核对以直接调用点核对 + 针对性回归代替。
- **边界**：本轮为确定性机械证据，不构成独立验收，不据此宣布真实 LLM 建模质量或独立语义验收通过；§4 分层与"明确排除"不变。

## 10. 独立复核轮（2026-09-19，F-SEAL-004 交付后补充）

**结论：F-SEAL-004 独立复核 PASS（0 缺陷）。** 本轮独立复核 §9（2026-09-19 开发自测）新增的封存源治理语义读语义证据；测试构造独立于写该证据的开发会话（场景形状、假 Store 判定机制、查询入口组合均不同），不改写 §8 与 §9 任何记录。

- 执行者：requirement_tester（独立于 §9 开发会话）；日期：2026-09-19；轮次：交付后补充独立复核轮（F-SEAL-004 专项）。
- 被测状态：HEAD `1f1e988`（含 `d8ef199` 的 F-SEAL-004 开发自测与 F1–F9 需求修订）；工作树他人未提交改动（`skills/modeling-dev-loop/SKILL.md`、`.codex/agents/`、`docs/diagrams/modeling-team-guide/`）未触碰、未纳入本轮任何操作；未执行 git commit。
- 临时测试文件（跑完即删，本节为唯一证据记录）：`backend/tests/test_r30017_round2_seal004.py`（5 用例，Round 1 命名惯例）。独立构造要点：源项目 3 个 Ontology（2 个入快照范围、1 个范围外），入范围者跨多个默认图类目（ontology+data）多三元组内容；假 RDF Store 为内容寻址封存守卫（`query_sparql` 仅当查询串命中任一封存源图 IRI 才断言失败，其余查询照常记录应答——区别于 §9 的全局计数器式守卫），fork 后对全部源图 IRI 布防。
- 分层事实只读复核：`security/http.py` `required_scope` 对 `POST /api/semantic/context:query` 与 `POST /api/semantic/sparql:query` 返回 `"read"`（L109–110），`_check_checkpoint_archive` 对 `scope=="read"` 直接放行（L579）——与 §9 登记一致。

### 10.1 逐点结果（全部 PASS）

| 被测点 | 独立验证方式与结果 | 结果 |
| --- | --- | --- |
| a) 项目级与 Ontology 级 scoped SPARQL → 409/`SemanticQueryScopeNotReady`，Store 零触达 | 服务层三入口：resolver 直调项目级（"Semantic query scope is not ready"）；`ScopedSparqlQueryService.query` Ontology 级混合列表（范围外+两个入范围 id）与项目级 **ASK 形态**查询均 409 `scope_not_ready`；`store.queries == []`（零触达，且守卫若被触达测试即失败） | PASS |
| b) scope discover：封存项目 `unavailable`、excluded `reason="ontology_archived"` | `discover(queryable="false")`：恰 1 项目条目 `query_status="unavailable"` + 3 个 excluded 全 `ontology_archived`；3 个 Ontology 条目 `status="archived"`/`queryable=false`/`unavailable_reason="ontology_archived"`；`discover(queryable="true")` 零条目；`discover(query="Logi")` 按名检索命中唯一封存 Ontology 且 `queryable=false` | PASS |
| c) 范围外 Ontology 随 fork 置 archived、不在新项目、图内容不进新项目 | 3 个源 Ontology 全 `archived`；范围外 id 不在 identity mapping、其全部图 IRI 与 mapping 键值集双侧不相交；新项目恰含 2 个映射 Ontology；范围外哨兵内容仅存在于其原图（全 Store 图扫描）；resolver 对其单独查询 409 `scope_not_ready` | PASS |
| d) 新项目语义查询继续（到达 Store） | 服务层项目级查询：scope `complete`、含 2 个 fork Ontology、`query_type=="select"`、Store 恰收到 1 条查询且 FROM 子句含新图 IRI（封存守卫布防下通过，证查询只指向新图） | PASS |
| e) HTTP 面对照：GET 200 / PATCH 409 `checkpoint_source_archived`；语义查询 POST 409 `scope_not_ready`（read key 与 admin key 双验证） | 真实 HTTP capture（2/3 Ontology 入范围）+fork 后：`GET /api/projects/<源>`（read key）200；`PATCH`（org admin key）409 `checkpoint_source_archived`；**项目级 admin key 在封存项目下 POST 新 Ontology** 亦 409 `checkpoint_source_archived`（过 ownership 后命中封存门）；`POST /api/semantic/sparql:query` read key 项目级与项目级 admin key Ontology 级（范围外 id）均 409 `scope_not_ready`；`POST /api/semantic/context:query`（read key）409 `scope_not_ready`（§9 未覆盖的第二查询入口）；`GET /api/semantic/scopes:discover` HTTP 面 `queryable=false`/`true` 与服务层同判；**新项目 HTTP 语义查询 200** 且 Store 恰收到 1 条指向新图的查询；全程封存源图零触达 | PASS |

### 10.2 开发自测套件原样重跑

`cd backend && uv run pytest tests/test_checkpoint_data_seal_read.py -q` → **6 passed**（与 §9 记录一致，原样通过）；临时文件 Ruff `All checks passed`。

### 10.3 基线（按失败清单比对，非总数）

- 后端：`cd backend && uv run pytest -q` → **1024 passed, 37 skipped, 0 failed**（登记 1013 + d8ef199 新增 6 + 本轮临时 5 = 1024；失败清单为空，零新增）。
- Team：backend 目录 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q` → **2006 passed, 1 skipped, 339 subtests passed, 0 failed**（与登记 2006 逐一相符；本轮无团队侧临时用例；失败清单为空，零新增）。

### 10.4 缺陷与注记

**缺陷：0 项。** 注记（不计缺陷）：

1. 授权层先于封存层的既有事实：项目级 key PATCH `/api/projects/<id>` 被 `security/http.py` L474–478 一律 403 `forbidden_scope`（本轮初版误以其为 409 探针，实测 403 后改用"项目级 admin key 在封存项目下 POST Ontology"证封存门 409）。该 403 为需求外既有授权规则，非 R3.0-017 缺陷，且与 F-SEAL-003"ownership 判定先于封存判定"的分层一致。
2. 本轮分层复核再次确认：语义查询端点的 409 来自 readiness 层（`ontology_archived` → `SemanticQueryScopeNotReady`），封存写门因 `required_scope=="read"` 豁免不参与；写路径（PATCH/项目下 POST Ontology）则由封存门拦 409 `checkpoint_source_archived`。两层在 e) 用例内同请求面钉住。

### 10.5 清理与边界确认

- 临时测试文件 `backend/tests/test_r30017_round2_seal004.py` 已删除（tests 目录 grep 零匹配）；本轮未产生其他临时文件或输出文件。
- `workspaces/modeling-runs` 扫描无 `r3017*` 残留 run 根。
- 本轮无产品代码、需求、设计文档变更；§3 C 组 F-SEAL-004 行仅在既有证据指针括注内追加"独立复核证据见 §10"，其余列未动。G2 真实证据门维持 Round 1 结论，本轮未重跑 live；不声明真实 LLM 建模或独立语义验收通过（§4"明确排除"不变）。
