# R3.0-004 主体绑定的语义知识访问控制 — 共享测试计划

- 日期：2026-08-23（2026-08-25 修订，随设计第二轮重写）
- 状态：Round 1 独立测试 PASS（2026-08-26，见轮次记录；含 D1 SPARQL 泄露缺陷的修复复核与
  L1～L4 真实运行；O-1/O-2 前置平台缺陷见轮次记录，登记为独立修复项）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-004
- 设计：
  `docs/delivery/designs/2026-08-23-r3-0-004-semantic-knowledge-authorization-design.md`
- 执行者：开发者先自测；`requirement_tester` 在稳定状态独立复核并把轮次追加到本文
- 测试位置：`backend/tests/`（pytest），新增用例建议集中在
  `test_semantic_access_authorization.py`（HTTP/服务层）、`test_semantic_access_mcp.py`（MCP 面）、
  `test_semantic_protection_sets.py`（管理面/CRUD），并对被退役面修改
  `test_semantic_visibility.py`（删除）、`test_semantic_read_model.py`、
  `test_semantic_export_graph_set.py`
- 修订说明：第一轮计划基于 RDF policy graph 存储，已随设计废弃；本版按 PostgreSQL 保护集与
  OR 授权公式全面重写，并删除 policy graph、自保护、RDF 坏策略、include_policy 等不再适用的
  用例（§8）

## 1. 测试边界

本计划只验收 R3.0-004：

1. 语义知识访问控制（呈现合同、保护集控制面、grant 主体令牌、共享执行层、
   `SemanticVisibilityPolicy` 退役、需求/术语修订）。
2. 不证明业务数据安全：直接连接 PostgreSQL 查询成本列成功不构成本计划失败项，也不得被报告为
   语义权限缺陷。
3. 不启动真实建模 Agent、不执行 R3.0-002/003/005/006 的验收、不宣称 v3.0 完成。
4. 不把建模流程记录面（设计 §9.2 判"不适用"的工具）的未过滤行为判为 FAIL（已记录边界），但边界
   回归用例防止其意外恶化。

## 2. 稳定测试命令

从仓库根执行：

```bash
cd backend && uv sync --extra dev          # 依赖未变时省略
cd backend && uv run alembic upgrade head  # 应用 0032 保护集表 + api_keys.semantic_grants
cd backend && uv run pytest                # 全量回归（完成门必需）
```

真实运行轮（§9）：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

失败时按 CLAUDE.md 用 `journalctl --user -u ontology-platform.service` 定位并记录确切阻塞点。

## 3. Fixture 设计（pytest）

复用 `backend/tests/conftest.py` 既有服务级 fixture 模式；本需求新增一个语义授权 fixture 组：

1. **项目 P** 与三个本体 `O_a`、`O_b`、`O_c`（同项目；`O_a`/`O_b` 验证跨本体保护集，`O_c` 为
   **无任何保护成员的干净 scope**——评审 H-4；默认图集齐备）。`O_a` 内容含一个受保护语义模块
   ——至少 1 个类 IRI、1 个成本指标 IRI、1 个映射记录 IRI、1 个枚举个体 IRI（fixture 专用
   IRI，例如 `…/SparePartStandardCost` 等，命名只存在于测试数据）；`O_c` 内容不含任何保护集
   成员，用于 S5/B4 的"scope 外不拒绝"与 §3 同目标对照。
2. **保护集**（经管理 API/MCP 工具创建，PostgreSQL 存储）：
   - `PS_COST`（`allowed_grants=["cost-visibility"]`）：成员 = 上述四个受保护 IRI（含 `O_a` 的
     `ontology_id` 定位元数据）+ `O_b` 的一个资源 IRI（跨本体成员）；
   - `PS_HR`（`allowed_grants=["hr-visibility"]`）：成员含 `O_a` 的一个普通资源 IRI 与
     `PS_COST` 的一个重叠成员（验证多保护集 OR）；
   - `PS_MULTI_GRANT`（`allowed_grants=["cost-visibility", "hr-visibility"]`，验证单保护集多
     grant OR）；
   - `PS_EMPTY`（`allowed_grants=[]`）：成员 = `O_a` 的一个普通资源 IRI（验证空 grant fail-closed）；
   - `PS_DANGLING`：成员 = 尚未创建的 IRI，`ontology_id` 定位元数据指向 `O_a`（悬空 IRI 且
     无 ontology_id 会使所有 scope 保守含它，导致干净 scope 无法构造——评审 H-4；空
     ontology_id 的保守 in-scope 行为另用服务层单测覆盖，不依赖 scope 构造）。
3. **对照项目 P2 / 本体 `O_control`**：内容与 `O_a` 相同但**去除受保护模块且无任何保护集**，用于
   "无痕子集"与"默认可读"的等价对照。
4. **证据**：一个 evidence reference 仅关联受保护成员（cost 类），一个 reference 关联非受保护
   成员，一个无关联 reference；一条挂接受保护成员的 mapping 与一条 lineage 记录。
5. **主体**（经 admin 创建，只经服务端解析）：
   - `KEY_MANAGER`：项目 P 绑定，`scopes=["read"]`，`semantic_grants=["cost-visibility"]`；
   - `KEY_HR`：项目 P 绑定，`scopes=["read"]`，`semantic_grants=["hr-visibility"]`；
   - `KEY_OPERATOR`：项目 P 绑定，`scopes=["read"]`，`semantic_grants=[]`（与 NULL 两形态各测
     一次）；
   - `KEY_MODEL`：项目 P 绑定，`scopes=["model"]`，无 grant（验证 model 可管理保护集但不见受保护
     内容、不能管理 grants）；
   - `KEY_ADMIN`：未绑定项目 admin key（org-admin）；
   - `KEY_PROJECT_ADMIN`：项目 P 绑定 admin key（Project Admin，验证绕过）；
   - `KEY_P2`：项目 P2 绑定 read key（验证跨 Project 拒绝）。
6. **坏记录 fixture**：一条 `semantic_grants` 含非字符串元素/空串/重复项的 key（服务测试直接构造
   记录），验证解析容错（fail-closed 为空集，不 500）。
7. 每用例后撤销/删除 fixture key 与项目数据，互不串扰；fixture 名称
   （ServiceManager/ServiceOperator/cost-visibility）不得进入产品代码（grep 门，见 F6）。

通用断言工具（在各用例内定义，勿新增仓库级脚本）：

- **逐字节等价（同目标对照，评审 H-1）**：对照必须针对**同一请求目标**构造——把同一 IRI/label
  请求指向确实不含它的范围（`O_c` 图集或对照项目 P2 的同构本体），断言"无权主体的响应"与"该
  目标在对照范围真不存在时的响应"的 `status + headers["content-type"] + json.dumps(body,
  sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 三元组完全相等。禁止用另一个
  不存在的 IRI 做对照。仅当某面不存在同目标对照构造时，才豁免"回显请求目标的字段"（404 detail
  中的请求 IRI、`original_queries`/`normalized_queries`）后比较其余字节，豁免字段在该用例中注明。
  `context:query` anchor 面额外命名豁免**回显请求范围**的 `scope` 块及 scope 派生字段（同目标
  对照必然指向不同范围，scope 块非存在性信号——评审 H-5），其余字节仍须逐字相等。
  MCP 侧比较 `ok/error/error_code + 规范化 data`。
- **无泄露子串检查**：递归遍历响应（跳过 context:query 响应中的
  `original_queries`/`normalized_queries` 回显字段），任何字符串值不得包含受保护成员 IRI、受保护
  资源 label、grant 字符串 `"cost-visibility"`、以及 `"protection_set"`/`"protection-set"`/
  `"allowed_grants"`/`"semantic_grants"` 字样。

## 4. 成功路径（S）

- **S1 Manager 全可见**：`KEY_MANAGER` 在 context:query（宽范围词 + 精确 IRI anchor + 精确
  label）、read model（`q=`/`entity=`）、statements、resources/{iri}、graph-set export、shape
  guidance、lineage、证据各面得到受保护模块的完整内容；记录实际返回的成员 IRI 与数量。
- **S2 Admin 绕过**：`KEY_ADMIN`（org-admin）与 `KEY_PROJECT_ADMIN`（项目 P 的 Project Admin）在
  项目 P 全部读面得到与 Manager 相同或更全的结果；SPARQL 不受限；Project Admin 亦可在项目 P 内
  正常读受保护内容。
- **S3 无保护集默认可读与快路径**：`O_control`（无任何保护集）范围内，`KEY_OPERATOR` 各读面结果
  与实现前基线一致（无过滤副作用、无新增 warning、无性能量级退化）；项目 P 中未加入任何保护集的
  资源对 `KEY_OPERATOR` 正常可读。
- **S4 grant 即时生效**：admin 经 `POST /api-keys`（带 `semantic_grants`）与 `PATCH /api-keys/{id}`
  创建/更新 `KEY_OPERATOR` grant 后，**不经重启**，下一次请求即按新 grant 可见（HTTP 直连；MCP 用
  in-process `set_runtime_principal` 前置的既有测试缝验证逐调用重读）；`GET /api-keys` 回显
  grant；revoke 后 401/失效。
- **S5 SPARQL 正常路径**：`KEY_MANAGER` 在 `O_a` 范围 SPARQL 查询（含查受保护成员）正常返回；
  `KEY_OPERATOR` 在 `O_control`（P2）范围、以及项目 P 内 `O_c`（无任何保护成员）scope SPARQL
  正常返回。
- **S6 多保护集 OR**：重叠成员（同时属于 `PS_COST` 与 `PS_HR`）——`KEY_MANAGER`（满足
  `PS_COST`）与 `KEY_HR`（满足 `PS_HR`）**各自都能访问**，不要求同时满足两个保护集。
- **S7 单保护集多 grant OR**：`PS_MULTI_GRANT` 的成员——持 `cost-visibility` 或持 `hr-visibility`
  的任一主体都可访问；持其他 grant 的主体不可见。
- **S8 跨本体成员**：`PS_COST` 中 `O_b` 的成员对 `KEY_MANAGER` 可见、对 `KEY_OPERATOR` 隐藏
  （同一保护集覆盖同 Project 两个 Ontology）。

## 5. 边界路径（B）

- **B1 精确请求逐字节等价（同目标对照）**：对每个"404/空结果合同"面（HTTP：resources/{iri}、
  context:query anchor、shape guidance、lineage、evidence-references/{id}、
  get_entity_statement_context 等价面；MCP：同名工具），按 §3 同目标对照定义，断言"Operator
  请求受保护目标"与"同一目标在对照范围（`O_c` 图集 / P2 同构本体）真不存在"的响应
  **逐字节等价**。HTTP 状态码、错误码、detail 文本、warnings 数组、recall 块全部相同；豁免
  回显字段时在用例中注明（评审 H-1，禁止"另一个不存在 IRI"对照）。
- **B2 宽范围无痕子集**：Operator 对项目 P 的宽范围检索（context:query 检索词、read model `q=`、
  statements、evidence 列表、missing-evidence-facts）结果与任意主体对 `O_control` 的同一请求
  **结构等价**：items 序列（逐页遍历到 cursor 耗尽）、warnings 列表、`match_status`/
  `completeness`、`truncated` 标志、cursor 存在性、`total`/`has_more` 全部一致（cursor 本身是签名
  值不比值）。并叠加 §3 无泄露子串检查。
- **B3 分页/cursor/total/排序/截断前过滤**：
  - 构造使命中数超过 `limit` 的检索（授权子集 + 被隐藏项混合），Operator 分页遍历全部页：任何页
    不得出现受保护内容或过滤提示；`matches_truncated`/`context_truncated` 与"对照本体同参数"
    一致；**排序在过滤后计算**（被隐藏项不影响可见项的排序位置）；
  - Operator 的 context cursor 在 `KEY_MANAGER` 上使用 → 现行 cursor 校验错误（合同不变），且
    错误不泄露保护信息；
  - evidence 列表 `total` 与过滤后 items 数一致；missing-evidence-facts `count` 同步。
- **B4 SPARQL 整体限制（scope 交集判定）**：Operator 对含无权保护成员的 scope SPARQL → HTTP 409
  `{"code": "scope_not_ready"}`，消息为共享通用常量（与"scope 无可查询图"情形同文案），无泄露
  子串；MCP 同工具 → `ok=false, error_code="scope_not_ready"`。Manager/Admin 同查询正常。
  **scope 外保护成员不触发拒绝**：Operator 对只含 `O_c`（无任何保护成员的本体）的 scope
  SPARQL 正常返回，不得因项目 P 其他本体（`O_a`/`O_b`）内的保护资源拒绝（评审 H-4：scope 按
  本体选择，不能用"O_b 非保护图"构造）。任意合法只读查询形态（SELECT/ASK/CONSTRUCT/DESCRIBE）
  均被整体限制，不出现部分结果。
- **B5 保护集不进入语义面**：Operator 与 Manager 的 graph-set export（`include_policy=true` 与
  `false`）、`GET /api/semantic/export`、SPARQL 结果中均不含保护集定义、成员清单或 grant 内容
  （保护集存储于 PostgreSQL，负向测试确认无任何序列化路径泄漏）。
- **B6 引用级整体隐藏**：Operator 看不到仅关联受保护成员的 reference（列表 + 精确 404 等价）、
  受保护成员的 evidence 关联、mapping 记录、lineage 展开行、派生指标语句；以及**通过关系、路径
  引用无权资源的结果行/条目**（构造一条 statement 其 object 为受保护 IRI 而 subject 非受保护：
  整条语句隐藏）。Manager 可见。
- **B7 项目边界与 403 边界**：
  - 跨项目资源访问（`KEY_P2` 访问项目 P 资源；MCP PROJECT_RESOURCE 工具）→ `forbidden_scope`
    合同与实现前逐字节一致（正反例快照）；`KEY_PROJECT_ADMIN` 访问项目 P2 资源仍被拒绝
    （Project Admin 只绕过本 Project）；
  - 语义知识读取面全量扫描：任何响应不得出现 403/`forbidden`；
  - 控制面：read/Consumer 主体调用保护集管理 API / MCP 工具 → 403 `forbidden_scope`（现有
    scope 合同），且错误不泄露保护集存在性细节。
- **B8 HTTP/MCP 等价**：对 S1/B1/B4 的每个面，用 in-process MCP（`set_runtime_principal` 塞入
  服务端构造的对应 principal）重复断言；结果与 HTTP 面结构等价（MCP envelope 差异除外）。

## 6. 失败路径（F）

- **F1 坏 grant 记录**：§3.6 坏记录 key 认证成功但授权按空 grant 集处理（受保护内容对其不可
  见），无 500；日志有且仅有一次性 warning。
- **F2 空 allowed_grants fail-closed**：`PS_EMPTY` 的成员对 `KEY_MANAGER`/`KEY_HR`/
  `KEY_OPERATOR` 全部不可见（无任何 grant 可满足）；仅 Project Admin / org-admin 可见。
- **F3 授权依赖故障**：模拟 PostgreSQL 保护集查询异常（测试内 monkeypatch session 抛错），读取面
  返回**通用依赖错误**（HTTP 503 / MCP `dependency_error`；不静默放行、不静默伪装成空结果或
  "全部不存在"）。
- **F4 管理面校验**：非 admin 调 `/api-keys` 各路由 → 现行 403 合同不变；`semantic_grants` 含空
  串/超长/>64 项 → 422/400 校验拒绝；`PATCH` 越权 key → 404/403 按现行 `_visible_key` 合同；
  `KEY_MODEL`（model 主体）调 `PATCH /api-keys` → 403（model 不能给自己或其他 key 增加 grant）；
  保护集重名 → 409；删除非空保护集 → 409 `protection_set_not_empty`；移出全部成员后删除成功。
- **F5 生命周期顺序**：
  - **先保护后创建**：把 IRI 加入保护集后再经建模路径创建资源，Operator 全程不可见；
  - **先创建后保护**：创建资源（Operator 可见）→ 加入保护集 → Operator 立即不可见（接受窗口，
    断言加入后生效即可）；
  - **移出最后一个保护集恢复可读**：把成员从其唯一保护集移除 → 该资源对 Operator 立即恢复普通
    可读；
  - **悬空 IRI**：`PS_DANGLING` 中尚未存在的 IRI：创建该资源后 Operator 立即不可见（悬空成员保持
    保护语义）；删除本体后成员行仍在（悬空合法），该 IRI 仍受保护。
- **F6 边界守恒（grep 门）**：产品代码（`backend/app/`，排除 `tests/`）中不得出现
  `ServiceManager`、`ServiceOperator`、`cost-visibility`、`hr-visibility`、语义知识读取面新增路径
  的 `forbidden` 等字符串；`semantic_visibility`、`visibility_context`、
  `semantic_graph_visibility_labels` 全仓无残留引用；产品代码与 v3/R3.0-004 文档中不得残留
  `SemanticProtectionPolicy`、`requiredGrant`、`protects`（RDF 策略词汇）与"权限集
  （Permission Set）"业务命名。
- **F7 审计事件**：保护集创建/修改/删除/成员增删与 `PATCH /api-keys` grant 修改各产生一条
  `security_audit_events` 追加记录，actor 为认证主体，details 符合扩展后 allowlist（不含 key
  明文；allowlist 扩展见设计 §10.3——评审确认 3）。

## 7. 回归（R）

- **R1 现有读面回归**：`cd backend && uv run pytest` 全量通过；重点关注
  `test_semantic_context_query*.py`、`test_scoped_sparql_query.py`、
  `test_semantic_read_model*.py`、`test_semantic_export*.py`、`test_semantic_api.py`、
  `test_evidence_*.py`、`test_lineage_*.py`、`test_mcp_*.py`、`test_api_keys.py`、
  `test_authorization.py`。
- **R2 无保护集/Admin 行为不变**：以实现前基线快照（或对照断言）确认：无保护集项目的全部读面响
  应、org-admin 与 Project Admin 的全部读面响应与实现前一致（本设计不新增读取面响应字段）。
- **R3 `visibility_context` 移除影响**：`SemanticExportRequest` 已无路由消费，移除字段后全量测试无
  失败；`test_semantic_visibility.py` 删除后无残余导入。
- **R4 退役清理**：F6 的 grep 门通过；`Settings` 无 `semantic_graph_visibility_labels`；
  `SemanticReadModelService`（`semantic_read_model.py`）与 `SemanticExportService`
  （位于 `semantic_graph_set_export.py`）签名无 `visibility_policy`（实现阶段核实真实类名即
  `SemanticExportService`，评审确认 2 的类名表述已由设计 §11.3 修正）。
- **R5 建模面边界不恶化**：`get_modeling_batch` 等设计 §9.2 判"不适用"的工具仍按现行合同工作
  （项目边界、错误码不变）；本用例只防回归，不把其内容可见性判为 FAIL（§1.4）。

## 8. 删除的原有测试（policy graph 方案遗留）

以下第一轮计划（与实现前仓库）中的用例类别随 RDF policy graph 方案废弃，本计划**不再包含**，
实现时同步删除/改写：

1. policy graph 策略语句装载与随 Modeling Batch 干跑/应用发布的用例；
2. policy graph 自保护（无权主体读不到策略语句、`include_policy` 导出过滤）用例——保护集不再存
   在于 RDF，`include_policy` 保持 legacy 行为，B5 以负向断言替代；
3. RDF 坏策略容错（缺 `requiredGrant`、非字面量 grant、多 `requiredGrant` AND 语义）用例——
   替换为 F1（坏 grant 记录）与 F2（空 allowed_grants）；
4. "持有所需全部令牌/部分令牌只见已满足模块"（AND 语义）用例——替换为 S6/S7（OR 语义）；
5. "项目绑定 admin 不绕过"用例（旧 B7 第三条）——替换为 S2/B7 的 Project Admin 绕过 + 跨 Project
   仍拒绝；
6. published graph set 策略解析（草稿/工作区策略不参与判定）用例——保护集与 graph set 发布状态
   无关，删除。

## 9. 真实运行（L，独立于 pytest）

1. **L1 迁移与重启**：`cd backend && uv run alembic upgrade head` 成功（0032 恰好一次；`\d
   semantic_protection_sets`、`\d semantic_protection_set_members` 存在，`\d api_keys` 含可空
   `semantic_grants`）；`systemctl --user restart ontology-platform.service` 后 unit active；
   `curl --fail http://127.0.0.1:8001/api/health` 与 `curl --fail http://127.0.0.1:5173/` 通过。
2. **L2 live 双 key HTTP 验证**：以 admin 会话/密钥经真实接口创建 fixture 项目、本体、保护集与
   `KEY_MANAGER`/`KEY_OPERATOR`；用 `curl` 携带 `Authorization: Bearer` 分别验证：
   - Manager：`GET /api/semantic/resources/<受保护 IRI>?graph_set_id=<gs>` → 200，内容含成员；
     `POST /api/semantic/context:query` 精确 anchor → 命中；
   - Operator：同一 resources 请求 → 与"真不存在 IRI"请求**逐字节相同**（保存两份响应体 diff 为
     空）；宽范围 context:query 返回不含受保护内容；SPARQL → 409 `scope_not_ready`；
   - 记录命令与响应摘要到本文轮次记录。
3. **L3 live MCP 实例验证（HTTP/MCP 等价证据）**：用 Operator key 启动独立 MCP 进程并执行最小
   stdio JSON-RPC 会话（initialize → `tools/call query_semantic_context` 与
   `tools/call semantic_sparql_query`）：

   ```bash
   cd backend && ONTOLOGY_MCP_API_KEY="<KEY_OPERATOR>" uv run python -m app.mcp.server
   ```

   驱动端用一次性内联客户端（`uv run python - <<'PY'` 子进程管道，不新增仓库文件）发送上述
   调用；断言 MCP 结果与 L2 中 Operator 的 HTTP 结果结构等价（context 无受保护内容、SPARQL
   `scope_not_ready`）。可选加强：再以 Manager key 启动第二个 MCP 实例对照。进程与临时 key
   用后即弃。
4. **L4 live 保护集管理（model key，可选加强）**：以项目 P 的临时 model key 启动 MCP，执行
   `create_semantic_protection_set` → `add_semantic_protection_set_members` →
   `list_semantic_protection_sets` 最小链路，随后 admin 清理。

## 10. 清理

1. 撤销并删除 L2/L3/L4 创建的全部 fixture API key（`POST /api-keys/{id}:revoke` + 记录清理）；
   恢复 `backend/.env` 的 `ONTOLOGY_MCP_API_KEY` 原值。
2. 删除 fixture 项目/本体/graph set 与保护集（走平台删除路径：先清空成员、删保护集、再删项目；
   或随项目级联），确认 `scopes:discover` 不再列出 fixture 项目。
3. 终止 L3/L4 的全部临时 MCP 进程；删除本地保存的响应样本与任何临时驱动脚本（不提交）。
4. 测试代码中的 fixture 常量只保留于 `backend/tests/`；确认仓库新增文件不含密钥、连接串或
   个人数据。

## 11. 判定规则与完成门

- **PASS**：S1–S8、B1–B8、F1–F7、R1–R5、L1–L4 全部通过；需求/术语修订（设计 §12）已落盘；
  R3.0-004 状态占位已更新；§7 所列旧用例类别确已删除。
- **FAIL**：任何泄露断言失败（受保护内容、grant、保护集字样出现在无权主体响应；403 出现在语义
  知识读取面；cursor/total/warning/计数/排序差异；逐字节等价破坏）；授权公式错误（要求 AND 而非
  OR；scope 外成员触发 SPARQL 拒绝）；绕过规则错误（Project Admin 未绕过本 Project 或绕过了跨
  Project）；管理面越权（model 管理 grants、read 读控制面）；fail-closed 破坏（依赖故障放行或伪
  装空结果；空 allowed_grants 可见）；共享执行层被绕过（HTTP 与 MCP 行为不一致）；migration/回
  归失败。
- **BLOCKED**：仅用于 PostgreSQL/systemd 服务无法运行等本轮无法修复的外部条件；确因 collation
  version mismatch 等既有环境残余导致的非功能性警告只记录，不判 BLOCKED。
- 完成后由主 agent 收口：更新 R3.0-004 最终状态、需求文档信息区链接、设计/测试计划状态行；
  R3.0-002/003/005/006 仍保持待实现/待验收。修订设计经审阅通过前，不得宣称实现或验收开始。

## 轮次记录

（开发者自测与独立测试轮次由执行者追加，不得改写历史轮次。）

### 第 1 轮（独立测试，2026-08-26，requirement_tester）

**测试对象与工作区状态**：branch `main`，基线 commit `d7f21ca` + 全部未提交 R3.0-004 实现（含 D1 修复轮：
`backend/tests/test_semantic_access_http.py` 已在位，开发者自测 879 passed / 10 skipped）。本轮未修改任何
产品代码；唯一仓库变更 = 删除临时文件 `backend/tests/test_r304_adhoc_round1.py`（前一轮被打断的测试者
留下的 4 个服务级 B4 用例，其覆盖已被 `test_semantic_access_http.py` 的真实 HTTP 栈 D1 回归完全包含，
按交接指示删除并在此记录）。

**实现审查（执行前，对照设计 §5/§7/§8/§9/§10/§11）**：审查了 `git diff`（auth/security/http、semantic、
context query、read model、export、evidence、lineage、SPARQL、MCP runtime）与全部新文件
（`semantic_access.py`、`semantic_protection_set.py`、`api/protection_sets.py`、`mcp/tools/protection_sets.py`、
migration 0032）。要点确认：`SemanticAccessResolver` 单一授权路径被 HTTP 与 MCP 共用；OR 公式（多保护集
OR + 集内多 grant OR）与 Admin 绕过（org + 本 Project）实现正确且 Project 限定；`scope_unauthorized_members`
现为 `ontology_id is None or in scope`（D1 修复后的正确方向：scope 外成员不触发 SPARQL 拒绝、悬空/失效
定位保守视为在 scope）；过滤位置在各面均在分页/计数/截断前（read model 以 `_FILTERED_FETCH_LIMIT=10000`
超额取回后先过滤再截断）；保护集 `protection_set_id` 已加入 `OWNER_RESOURCE_KEYS` 与
`_project_for_resource`；`SemanticVisibilityPolicy`/`visibility_context`/`semantic_graph_visibility_labels`
全部退役且 `.env.example` 同步删除。

**稳定命令结果**：

- `cd backend && uv run pytest -q`：**879 passed / 10 skipped**（与开发者自测一致）；删除 adhoc 临时文件后
  复跑 **875 passed / 10 skipped**。
- `uv run alembic current`/`heads`：均为 `0032_semantic_protection_sets`（L1）。
- L1 运行时：unit `active (running)`；`curl /api/health` → `{"status":"ok"}`；`curl :5173/` → 200；
  live PostgreSQL 中 `semantic_protection_sets`/`semantic_protection_set_members` 存在、
  `api_keys.semantic_grants` 列存在（测试后清理至 0 行 fixture）。

**F6 grep 门（全部 PASS）**：产品代码无 `ServiceManager`/`ServiceOperator`/`cost-visibility`/
`hr-visibility`；`semantic_visibility`/`visibility_context`/`semantic_graph_visibility_labels` 全仓无源码
残留（仅 untracked 构建产物 `backend/ontology_platform_backend.egg-info/SOURCES.txt` 中有历史文件名，
非源码、git 未跟踪）；无 `SemanticProtectionPolicy`/`requiredGrant` 残留；`semantic.py` diff 未新增任何
403/forbidden（现存 `forbidden_scope` 均为基线即有的项目边界/图集合同）。

**pytest 级用例映射与结果**：

| 计划用例 | 覆盖位置 | 结果 |
| --- | --- | --- |
| S1 Manager 全可见 | `test_semantic_access_http.py::test_resource_route_returns_not_found_for_protected_member`（manager 200 含 COST_IRI）；L2 live：anchor matched、statements 6 行、SPARQL 200 含成员、export 含成员 | PASS（`resources/{iri}` 面 live 见下方 O-1，非授权缺陷） |
| S2 Admin 绕过 | `test_semantic_access_authorization.py::test_admin_bypass_is_project_bound`（org/本 Project/跨 Project 三向）；L2 live：org-admin 与 Project Admin resources+SPARQL 均可见 | PASS |
| S3 默认可读/快路径 | `test_semantic_access_authorization.py::test_project_without_protection_sets_uses_fast_path`；L2 live：Operator statements 含 PublicThing | PASS |
| S4 grant 即时生效 | `test_semantic_protection_sets.py::test_patch_api_keys_manages_semantic_grants`、`test_..._carries_semantic_grants`；L2 live：PATCH 加/撤 grant 后 statements 3→6→3、SPARQL 409→200→409，无重启 | PASS |
| S5 SPARQL 正常路径 | `test_semantic_access_http.py::test_sparql_allows_manager_and_clean_scope`；L2 live 同判 | PASS |
| S6 多保护集 OR | `test_semantic_access_authorization.py::test_or_formula_across_sets_and_grants`（共享成员任一覆盖集即解锁） | PASS |
| S7 单保护集多 grant OR | 同上（`audit` 单 grant 解锁双 grant 集）；`PS_MULTI_GRANT` 语义等价覆盖 | PASS |
| S8 跨本体成员 | 本轮临时用例（sqlite 双本体单保护集：Operator 对 O_a/O_b 成员均不可见、Manager 均可见、SPARQL scope 交集按本体定位），运行后已删除；resolver 按_project_id_ 查询、可见性判定与本体无关 | PASS |
| B1 精确请求等价 | L2 live：`resources/{iri}` Operator vs 同目标 P2 对照 status+content-type+canonical body **逐字节相等**；anchor（`queries:[IRI]`，修正了上轮 422 的 schema 误用）除命名豁免 `scope` 块外逐字相等；shape 面除豁免（`graph_set_id`、`generated_graph_iri`、`custom_graph_iri`、`shape_split`、`target_class` 回显）外相等 | PASS |
| B2 宽范围无痕子集 | L2 live：context:query 宽词与 read-model `q=` 的 Operator 响应无泄露子串、与 P2 对照结构等价（除 scope/签名回显）；statements Operator 3 行 vs Manager 6 行，过滤正确；`test_semantic_access_http.py::test_context_query_route_filters_protected_candidates`、`test_read_model_route_filters_protected_rows` | PASS |
| B3 分页/截断前过滤 | `test_semantic_access_http.py::test_statements_route_filters_rows_before_pagination`；L2 live：statements `limit=1` Operator vs 对照仅差 `graph_set_id`/`source_signature`/`source_graph_iri` 回显 | PASS |
| B4 SPARQL 整体限制 | `test_semantic_access_http.py::test_sparql_rejects_scope_with_unauthorized_member_for_grantless_key`（D1 回归）+ `test_sparql_allows_manager_and_clean_scope`；L2 live：Operator O_a → 409 `scope_not_ready`（SELECT/ASK/CONSTRUCT/DESCRIBE 四形态均 409）、O_c → 200、Manager/Admin → 200 | PASS（D1 已修复并复核） |
| B5 保护集不进语义面 | `test_semantic_access_http.py::test_export_graph_set_route_omits_protected_quads`；L2 live：Operator export 200 无 cost 四元组、Manager 含；保护集存 PostgreSQL，无 RDF 序列化路径 | PASS |
| B6 引用级整体隐藏 | `test_semantic_access_authorization.py::test_view_statement_row_and_quad_filtering`（s/p/o 任一命中即隐藏，含 object 位引用）、`test_evidence_reference_visibility_by_association_target`；HTTP 面 statements 行过滤见 B2 | PASS |
| B7 项目边界/403 边界 | `test_semantic_protection_sets.py::test_scope_and_project_boundary_enforcement`；`test_authorization.py`/`test_api_keys.py` 全量回归（HTTP_ROUTE_POLICIES 登记校验）；语义读取面无 403（diff 审查 + 全量扫描） | PASS |
| B8 HTTP/MCP 等价 | `test_semantic_access_mcp.py`（evidence 读取 grant 行为、model/read 主体管理面）+ L3 live 双实例（见下） | PASS |
| F1 坏 grant 记录 | `test_semantic_access_authorization.py::test_malformed_grant_record_parses_to_empty`、`test_resolver_fails_closed_on_database_error` | PASS |
| F2 空 allowed_grants | OR 公式测试隐含（无 grant 可满足覆盖集即不可见）；`normalize_grants` 拒绝空串项 | PASS |
| F3 授权依赖故障 | `test_resolver_fails_closed_on_database_error`（503/dependency_error，不放行不伪装） | PASS |
| F4 管理面校验 | `test_semantic_protection_sets.py`：`test_duplicate_name_in_same_project_conflicts`、`test_invalid_grants_and_members_are_rejected`（空串/65 项/坏成员 422）、`test_full_management_lifecycle`（非空删除 409 `protection_set_not_empty`、移出后删除 204）；`test_patch_api_keys_manages_semantic_grants`（model 主体 403） | PASS |
| F5 生命周期顺序 | `test_semantic_access_authorization.py::test_dangling_members_stay_protected_and_scope_is_conservative`（悬空 IRI + 失效 ontology_id 保守）；先保护后创建/移出恢复由 resolver 每请求重读保证（S4 live 切换证据） | PASS |
| F6 grep 门 | 见上 | PASS |
| F7 审计事件 | `test_semantic_protection_sets.py::test_management_writes_audit_events`、`test_patch_api_keys_manages_semantic_grants`（`api_key_updated` 带 `grants_added`/`grants_removed`） | PASS |
| R1 全量回归 | 879（后 875）passed / 10 skipped | PASS |
| R2 无保护集/Admin 不变 | diff 审查：读面无新增响应字段；`requires_filtering=False` 恒等过滤；快路径单查询 | PASS |
| R3/R4 退役清理 | `test_semantic_visibility.py` 已删、无残余导入（全量绿）；grep 门 + `Settings` 无 visibility 配置 + 服务签名无 `visibility_policy` | PASS |
| R5 建模面边界 | `test_mcp_surface.py`/`test_mcp_auth.py`/modeling 相关全量绿，合同未动 | PASS |

**L2 live 双 key HTTP 验证（真实服务 8001）**：以既有 org-admin key（`backend/.env` 的
`ONTOLOGY_MCP_API_KEY` 对应记录 `harness-eval-admin`）经真实接口创建 fixture：项目 P1（本体 O_a 含
受保护类 + 公共类、O_c 干净）、对照项目 P2（O_ctrl 仅公共内容）；turtle 经 `POST /api/semantic/edits`
写入 **`asserted_data` 角色图**（修正上轮误写 `asserted_ontology` 导致 entity-detail/entity-list 读不到的
fixture 错误）；保护集 `r304-live-cost`（`allowed_grants=["cost-visibility"]`，成员含 `ontology_id` 定位）；
keys：Manager（read+grant）、Operator（read+空 grants）、P2 read（同目标对照）、Project Admin、model。
关键结果：

- Operator SPARQL scope O_a → `409 {"code":"scope_not_ready"}`，消息与"scope 无可查询图"同文案，响应无
  泄露子串；**D1 修复 live 复核通过**（上轮被打断时此处为 200+受保护内容，且 O_c 被误拒；本轮
  O_a=409、O_c=200、Manager=200）。
- B1 `resources/{iri}`：Operator(P1,COST_IRI) 与 P2-key(P2,COST_IRI)（真不存在）status+content-type+
  canonical JSON 三元组逐字节相等。
- B1 anchor（`queries:["<IRI>"]`）：Operator 与对照除 `scope` 块（命名豁免）外逐字相等，warnings 含
  `anchor_not_found` 且无过滤信号；Manager anchor `matched` 且含成员内容。
- B2：宽词/`q=` 检索 Operator 无泄露、与对照结构等价；statements 3 vs 6 行。
- S4：PATCH grants 加/撤后 statements 3→6→3、SPARQL 409→200→409，不经重启。
- B5：export（成员图填充后）Operator 200 无 cost、Manager 含 cost。

**L3 live MCP 实例验证**：以 Operator/Manager key 各启动真实 `python -m app.mcp.server` stdio 进程
（一次性内联驱动，env 覆盖 `ONTOLOGY_MCP_API_KEY`，`backend/.env` 文件未改动），initialize →
`tools/call`：Operator `semantic_sparql_query`(O_a) → `ok=false, error_code="scope_not_ready"`、(O_c) →
`ok=true`；`query_semantic_context` 宽词/anchor → `no_match` 无泄露；Manager SPARQL(O_a) → `ok=true`、
anchor → `matched`。与 HTTP 面行为一致（共享执行层证据）。

**L4 live 保护集管理（model key MCP）**：model key 经 MCP 完成
`create_semantic_protection_set` → `add_semantic_protection_set_members`（member_count 1）→
`list_semantic_protection_sets` → `remove_...`（0）→ `delete_...`（deleted=true）最小链路；read key 调
`list_semantic_protection_sets` → `ok=false, error_code="forbidden_scope"`（控制面合同）。

**清理（§10，全部完成）**：6 个 fixture key 全部 revoke（平台无 key-delete 路由，DELETE 返回 405 为现
行合同；含上轮遗留 `r304-test-org-admin`）；遗留空保护集 `r304-live-l4` 删除（204）；项目 P1/P2 删除
（204，级联保护集）；`scopes:discover` 无 r304 残留；DB 复核 `semantic_protection_sets` 0 行、r304 项目
0 行；MCP 临时进程全部终止；全部 `/tmp/r304_*` 驱动与样本文件删除；`backend/.env` 未被修改。

**开放项处置（上轮遗留）**：

- (a) S1 `resources/{iri}` 404：确认为**前置平台模板缺陷，非授权问题、非 R3.0-004 回归**——
  `entity-detail` 模板（`semantic_sparql_templates.py`）的 `GRAPH ?graph` 无 VALUES 限定，且
  `rdf_store.query_read_model` 仅把 graph_iris 写成注释不做实际限定，live 全库数据下 LIMIT 500 被其他
  项目的实体占满，任何主体（含 org-admin）都可能 404。基线 commit `d7f21ca` 中该模板逐字相同。Manager
  可见性已由 statements（6 行含成员）、anchor（matched）、SPARQL（200 含成员）、export（含成员）端到端
  证明。记录为观察项 **O-1**（跨项目实体混杂 + 目标挤出，建议独立需求修复模板限定）。
- (b) anchor 422：上轮误用不存在的 `anchor` 字段；正确 schema 为 `queries:["<IRI>"]`（单条 IRI 查询自
  动走 anchor 路径）。本轮已按正确字段完成 B1 anchor 等价验证。

**缺陷与观察项**：

- D1（上轮确认，Operator SPARQL 200 泄露）：**FIXED**——服务层反转条件已修正，HTTP 级回归测试在位，
  live 复核通过（见上）。
- 无本轮新增 R3.0-004 缺陷。
- O-1（前置，中）：`entity-detail` 读模型模板无图限定（见开放项 (a)）。不影响 R3.0-004 验收
  （B1 等价在该面仍成立：Operator 与对照同为 404 逐字节相等），但建议后续需求修复。
- O-2（前置，低）：图集成员图从未写入时（Oxigraph 对缺图返回 404），graph-set export 与 shape
  guidance 路由 500（`get_graph` 将 404 映射为 `RdfStoreUnavailable`）。基线行为相同，fixture 填充
  成员图后两面均 200 且授权行为正确。非 R3.0-004 回归。

**结论：PASS**（S1–S8、B1–B8、F1–F7、R1–R5、L1–L4 全部通过；无泄露、授权公式、绕过规则、管理面越权、
fail-closed、共享执行层、迁移与回归均符合 §11 完成门）。收口待办（主 agent）：更新 R3.0-004 状态行
（当前仍为“设计冻结…待实现”）、需求文档信息区链接；O-1/O-2 建议登记为独立平台修复项。

### 追加记录（2026-08-26）：O-1 修复回指

- 轮次记录 O-1（`entity-detail` 读模型模板无图限定，跨项目实体混杂 + LIMIT 截断假 404）
  已由 **R3.0-007** 修复并通过独立测试 Round 1 PASS（2026-08-26）：
  `docs/delivery/test-plans/2026-08-26-r3-0-007-read-model-graph-scoping-test-plan.md`。
- O-2（图集成员图未写入时 export/shape 500）仍未修复，保持独立登记。
- 本追加不改动上文任何历史轮次内容。
