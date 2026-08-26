# R3.0-004 主体绑定的语义知识访问控制 — 功能设计

- 日期：2026-08-23（2026-08-25 修订）
- 状态：已实现并验收（2026-08-26 独立测试 Round 1 PASS；设计经 plan_reviewer 两轮评审通过，
  见附录 B；实现期偏差处置见附录 B 末条）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-004
- 共享测试计划：
  `docs/delivery/test-plans/2026-08-23-r3-0-004-semantic-knowledge-authorization-test-plan.md`
- 交付边界：实现语义知识读取面的主体绑定授权与 Project 级保护集控制面；不改 MCP 进程级单主体
  模型；不做 RBAC 产品化、Role 模型、跨请求授权缓存或管理 UI；不实现 R3.0-002/003/005/006

## 0. 修订说明（2026-08-25）

本设计第一轮采用"Ontology RDF policy graph"方案：保护策略以
`{vocab}SemanticProtectionPolicy / protects / requiredGrant` 词汇作为 RDF 语句存入默认图集的
policy graph，随本体一起干跑/应用。该方案已整体废弃，替换为 **Project 级 PostgreSQL 保护集
（Protection Set）**。调整原因（业务决策已冻结）：

1. **保护集跨 Ontology**：一个保护集需要覆盖同一 Project 下多个 Ontology 的语义资源；按
   Ontology 存储 policy graph 无法自然表达跨 Ontology 成员关系。
2. **保护集属于控制面**：保护集是语义知识安全控制面，不是 Ontology 业务语义，也不是业务数据
   权限；把它混入本体内容会同时污染建模语义和授权语义。
3. **生命周期独立**：保护集变更不要求与语义资源创建通过同一 Modeling Batch 原子发布，也不依赖
   当前 active/default graph set 的发布状态；绑定本体发布会带来不必要的耦合与等待。
4. 由此删除：RDF 策略词汇、policy graph canonical role 的授权用途、策略随 Batch/Lease/dry-run
   发布、policy graph 自保护与导出过滤、RDF 策略结构容错、每请求读取 policy graph 的性能设计。

第一轮中与存储无关的读取安全合同（与不存在不可区分、宽范围无痕过滤、HTTP/MCP 同路径、
`SemanticVisibilityPolicy` 退役）保留并沿用；授权判定公式从"单策略 AND 全部令牌"修正为
"多保护集 OR、保护集内多 grant OR"。

## 1. 目标

1. 所有 Consumer Agent 可调用的语义读取面（HTTP 与 MCP）使用服务端认证得到的主体与项目上下文
   做资源级授权；调用方自报的 label/role/visibility_context 不再构成任何权限依据。
2. 受保护语义资源对无权主体在所有语义读取面一律呈现为"资源不存在"：精确请求与真不存在完全
   不可区分，宽范围查询返回无痕授权子集。
3. 保护集存储在 **PostgreSQL**，归属于 Project，可包含同一 Project 下多个 Ontology 的语义资源
   IRI；不进入任何 RDF graph、语义查询、导出或 SPARQL。
4. 授权令牌（Semantic Grant）绑定到 API key（`api_keys.semantic_grants`），由现有 admin-only
   `/api-keys` 接口管理，服务端每次请求从 key 记录解析。
5. Project Admin 绕过本 Project 的保护集；Org Admin 绕过所有 Project 的保护集。
6. HTTP 与 MCP 走同一授权代码路径（单一共享授权服务）。
7. 按需求原文完成一次语义模块示例验收（备件成本语义仅对持相应 grant 的主体可见），名称只出现在
   测试 fixture 中，产品代码不含工业售后专属分支。

## 2. 非目标

1. 不做业务数据安全：SQL 可查询哪些行/列/租户仍由外部系统落实（R3.0-005、Business Data
   Authorization 词条边界不变）。保护集只控制语义知识读取，不承担 PostgreSQL 行、列、租户等
   业务数据安全。
2. 不建立正式 Role 模型、grant 目录、策略表达式语言、继承体系或 RBAC 子系统；grant 保持规范化
   字符串，未来可增加 Role → grant 映射。
3. 不做保护集管理 UI；管理面只提供 HTTP API 与 MCP 工具。
4. 不做自动保护闭包：不因子类、实例、关联路径自动扩大保护成员；但查询结果只要引用了无权资源
   就必须整体隐藏相关结果（见 §5.4）。
5. 不做逐语句的任意 SPARQL 改写；SPARQL 面按整体限制处理（见 §7）。
6. 不做跨请求授权缓存、授权变更推送或按 key 的预计算可见集；无保护集时保留快速路径。
7. 不把建模流程记录面（Modeling Batch、Build Session、Workflow Artifact/Event、验证/推理运行
   记录、规则定义）纳入本交付的资源级过滤（判定与理由见 §9；已记录边界，不在本交付修复）。
8. 不修改 MCP 进程级单主体模型；不为多主体并发增加新的进程模型。
9. 不引入领域专属路由、schema 字段、分支或排序规则（CLAUDE.md 平台/参考本体边界）。

## 3. 业务对象：保护集（Protection Set）

### 3.1 定义

- **保护集**是 Project 级语义知识安全控制面对象：一个命名的资源 IRI 集合加上一组
  `allowed_grants`。主体满足任一 grant 即视为满足该保护集。
- 保护集归属于 **Project**（不是 Ontology）；成员可来自同一 Project 下多个 Ontology；**禁止
  跨 Project**。
- 保护集是语义知识安全控制面，不是 Ontology 业务语义，也不是业务数据权限。
- 业务名称统一为"保护集（Protection Set）"；不使用"权限集（Permission Set）"作为业务名称。

### 3.2 成员

- 正式成员是**语义资源 IRI**（类、属性、关系、指标、映射、枚举个体等）。
- 文件、批量选择只是录入入口，最终必须展开为明确的资源 IRI 列表入库。
- 允许引用**尚未存在**的资源 IRI（悬空 IRI）；悬空 IRI 保持保护语义，待资源创建后即被覆盖。
- 删除 Ontology 不自动删除其保护集成员记录；悬空成员由明确的保护集管理操作清理。
- `resource_iri` 是成员业务标识；`ontology_id` 仅作为授权 scope 判断的定位元数据（§7），不使
  Ontology 成为保护集所有者。

### 3.3 授权公式（OR 语义）

对主体 `S` 与资源 `R`（同 Project）：

```text
visible(S, R) ⇔ is_org_admin(S)
             ∨ (S 为该 Project 的 Project Admin)
             ∨ R 不属于该 Project 任何保护集
             ∨ ∃ 保护集 P：R ∈ members(P) ∧ allowed_grants(P) ∩ grants(S) ≠ ∅
```

- **多保护集之间 OR**：R 属于 HR 和审计两个保护集时，主体满足任意一个即可访问，不要求同时满足
  所有保护集。
- **保护集内多 grant OR**：`allowed_grants` 是"任一满足"列表，不是"全部持有"列表。旧设计
  "持有所需全部令牌""多 requiredGrant 按 AND"语义废除。
- `allowed_grants` 为空的保护集对非 Admin 主体不可见（fail-closed：没有任何 grant 能满足它）。

### 3.4 生命周期

- 保护集变更**不是 Modeling Batch 内容**，不依赖当前 active/default graph set 发布状态，没有
  干跑/应用/租约环节；管理操作直接生效。
- 与资源创建的顺序两种都允许：
  - 推荐**先保护后创建**（先把目标 IRI 加入保护集，再创建资源）；
  - 允许**先创建后保护**，接受期间资源在 Project 内短暂普通可读的风险。
- 资源移出最后一个保护集后，立即恢复为 Project 内普通可读（未加入任何保护集的资源默认可读）。

## 4. PostgreSQL 数据模型（最小）

一个 Alembic migration（下一个序号 `0032`）：

```text
semantic_protection_sets
  id            UUID PK
  project_id    UUID NOT NULL FK → projects.id ON DELETE CASCADE
  name          VARCHAR(200) NOT NULL        -- Project 内唯一
  description   TEXT NULL
  allowed_grants JSONB NOT NULL DEFAULT '[]' -- 字符串数组，去重、去空
  created_at    TIMESTAMPTZ NOT NULL
  updated_at    TIMESTAMPTZ NOT NULL

semantic_protection_set_members
  protection_set_id UUID NOT NULL FK → semantic_protection_sets.id ON DELETE CASCADE
  resource_iri      TEXT NOT NULL
  ontology_id       UUID NULL FK → ontologies.id ON DELETE NO ACTION   -- 仅 scope 定位元数据
  created_at        TIMESTAMPTZ NOT NULL
  PRIMARY KEY (protection_set_id, resource_iri)

api_keys
  + semantic_grants JSONB NULL              -- 字符串数组；NULL/缺失 → 空 grant 集
```

约束与取舍：

1. **Project 内名称唯一**：`UNIQUE(project_id, name)`；技术标识用稳定 `id`，名称允许修改。
2. **同一保护集内 `resource_iri` 唯一**：由复合主键保证；重复添加幂等。
3. **非空保护集不可直接删除**：删除前必须显式移除全部成员（服务层在同一事务内校验，违反返回
   管理面错误 `protection_set_not_empty`），避免批量意外公开。
4. **Project 删除级联删除保护集**（`ON DELETE CASCADE`）；成员的 `ontology_id` 为**无外键的可空
   定位列**（实现修订：设计的 `FK ON DELETE NO ACTION` 会阻止本体删除、使 R-6/A10 的悬空成员
   永远无法出现，自相矛盾；去掉外键后本体删除不受成员影响，成员悬空合法）。
5. **不用外键要求 `resource_iri` 必须在 RDF 中存在**（悬空 IRI 是合法状态）。
6. 不建 Role 表、策略表达式、缓存表或管理 UI 后端表。

## 5. 呈现与隐藏合同

### 5.1 精确请求：与真不存在不可区分

受保护语义资源对无权主体在所有语义读取面（精确 IRI、精确 label、关系/邻域、指标、映射、证据、
lineage、导出、SPARQL）一律表现为"资源不存在"。实现方式是**复用同一条"未找到"代码路径**：

- `GET /api/semantic/resources/{iri}`：过滤后资源不在 items 中，自然落入现有
  `HTTPException(404, detail=f"Resource not found: {resource_iri}")`。
- `POST /api/semantic/context:query` 精确 IRI anchor：过滤 anchor 行后走现有 `anchor_not_found`
  分支（同一 warnings、recall、空 primary/related）。
- 精确 label、`q=`/`entity=`、shape guidance 精确 class IRI、lineage 精确 target、evidence 精确
  reference_id：按"未命中/未知目标"的现行合同返回。

**等价基准定义（评审 H-1 修订）**：现行"未找到"合同会回显请求目标本身（如 404 detail 中的
`resource_iri`、context:query 的 `original_queries`/`normalized_queries` 回显）。这些回显是请求
内容的复述，不是资源存在性信号。因此逐字节等价的对照基准定义为**同目标对照**：对同一请求目标，
"无权主体的响应"必须与"该目标在对照范围内真不存在时的响应"逐字节一致——对照通过把同一 IRI/
label 请求指向确实不含它的图集/本体范围（或对照项目）构造。仅当某面不存在同目标对照构造时，
才豁免"回显请求目标的字段"（逐一列举：404 detail 中的请求 IRI、`original_queries`/
`normalized_queries`）后比较其余字节，豁免必须在用例中注明。**回显请求范围**与回显请求目标同类：
`context:query` anchor 面的响应含 `scope` 块（`ontology_id`、`ontology_name`、
`workspace_version`、`source_signature`、`derived_state` 等），它回显的是本次请求的范围而非目标
存在性；同目标对照必然指向不同范围（`O_c`/P2），故该面把 `scope` 块及 scope 派生字段列入命名豁
免，其余字节仍须逐字相等（评审 H-5）。禁止用"另一个不存在的 IRI"做对照
（其回显必然不同，断言永远不可满足）。

### 5.2 宽范围：无痕子集

过滤必须发生在**分页/计数/排序/截断/cursor 计算之前**，只返回授权子集：

- Context Query：候选过滤在 `_fuse_multi_expression` 之前对各候选源统一应用；`limit`、
  `matches_truncated`、match/context cursor、`recall_summary` 全部在授权子集上计算。
- 读模型/语句列表：行级过滤在 limit 之前；证据列表在 `total` 与分页之前。
- 禁止"先分页再过滤"（会使 truncated/cursor 泄露被隐藏项的存在）；禁止新增任何揭示过滤发生的
  warning。

### 5.3 禁用 403；`forbidden_scope` 保持

- 语义知识读取面不返回 403/forbidden（403 会成为存在性信号）。
- 项目边界校验的 `forbidden_scope`（跨项目访问，MCP 与 HTTP 现有合同）保持不变——它不泄露业务
  语义。保护集管理面（model scope 控制面接口）的 scope 拒绝沿用现有 403 `forbidden_scope` 合同，
  同样不属语义知识读取面。

### 5.4 语句与挂接隐藏（无自动闭包，结果级整体隐藏）

- 不做成员闭包计算（不因子类、实例、路径自动扩大保护范围）；保护范围恒等于成员 IRI 列表。
- 但**查询结果只要引用了无权资源，就必须整体隐藏相关结果**：凡 subject、predicate 或 object 位
  是无权成员 IRI 的语句，对无权主体隐藏（谓词位隐藏是对决策的字面规则的保守一致性细化，方向只
  收紧不放宽）；通过关系、路径、mapping、evidence、lineage 或派生内容引用无权资源的结果行/条目
  同样整体隐藏。
- 挂接隐藏：挂接到不可见成员的 evidence 关联、mapping 记录、lineage/provenance 展开、派生指标
  语句按同一 s/p/o 规则过滤。
- 证据 reference 可见性：reference 存在至少一条可见关联，或本无任何关联时可见；其全部关联均不可
  见且存在关联时，该 reference 整体按不存在处理。

## 6. 主体令牌模型（Semantic Grant）

### 6.1 存储与解析

- grant 是绑定到 API key 的**规范化字符串**（strip、去重、丢弃空串），不携带语义；本期不建立
  正式 Role 模型，未来可增加 Role → grant 映射。
- `ApiKeyModel.semantic_grants: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)`。
- `AuthPrincipal` 新增字段 `semantic_grants: frozenset[str] = frozenset()`（frozen dataclass 带
  默认值，兼容现有构造点）。
- `resolve_api_key`（HTTP）与 `_authorize_tool`（MCP，每次工具调用重读 `ApiKeyModel` 重建
  principal）把记录列表解析为 grant 集；NULL/缺失 → 空集；元素类型异常 → warning 日志 + 按空集
  处理（fail-closed，不让授权面变成 500）。
- 会话用户（`resolve_session`）构造 principal 不带 grant；其 org-admin 身份由绕过规则覆盖。
- grant 更新**无需重启**即生效：HTTP 每请求解析、MCP 每工具调用重读；key 撤销后 grant 随之失效
  （现有撤销语义不变）。

### 6.2 管理面（admin-only，沿用现有 `/api-keys` 接口族）

- `ApiKeyCreate` 增加 `semantic_grants: list[str] | None = None`；校验：每项非空字符串、长度
  ≤128、可打印、去重后 ≤64 项。
- `ApiKeyRead` 返回 `semantic_grants`（admin 管理面可见）。
- 新增 `PATCH /api-keys/{key_id}` 仅替换 `semantic_grants`，写 `api_key_updated` 审计事件。
- **grant 分配与撤销仅允许 admin**：Project Admin 只能管理本 Project 的 key；Org Admin 可管理全
  部；model 主体不能给自己或其他 key 增加 grant（现有 `_require_admin` + `_visible_key` 边界即
  满足，无需新机制）。

## 7. 共享授权服务

### 7.1 `SemanticAccessResolver`（新文件 `backend/app/services/semantic_access.py`）

```text
resolve(principal, scope) -> SemanticAccessView:
    if principal.is_org_admin: return all_visible_view
    if principal 为 scope 所属 Project 的 Project Admin: return all_visible_view
    sets = SELECT semantic_protection_sets WHERE project_id = scope.project_id   # 一次查询
    if sets 为空: return fast_path_view(requires_filtering=False)
    members = SELECT members WHERE protection_set_id IN sets                    # 一次查询
    unauthorized = { m.resource_iri
                     for m in members
                     if not any(allowed_grants(P_m) ∩ principal.semantic_grants
                                for P_m 覆盖 m 的保护集) }
    return View(requires_filtering=bool(unauthorized), unauthorized=unauthorized, ...)
```

- `SemanticAccessView`（frozen，每请求一个）：`requires_filtering`、`is_member_visible(iri)`、
  `filter_statement_rows(rows)`（s/p/o 命中即丢弃）、`filter_quads(quads)`（导出面）、
  `filter_evidence_targets(targets)`、`scope_unauthorized_members(ontology_ids)`（SPARQL 判定用）。
- **从 PostgreSQL 读取保护集及成员**（不是 RDF）；按 Project、查询 scope、主体 grants 计算不可见
  成员集。
- **HTTP 与 MCP 必须走同一授权代码路径**：MCP 工具调用与 HTTP 路由注入同一个 view。
- 应用位置：scope 解析后、响应组装前（注入点清单见 §9）。

### 7.2 Project Admin 绕过

- Project Admin（admin scope 且 `project_id` 绑定为该 Project）对本 Project 的保护集**绕过**：
  授权服务返回全可见视图。旧设计"项目绑定 admin 不是 org-admin，不绕过"结论**废除**。
- Org Admin（admin scope 且未绑定 Project，`AuthPrincipal.is_org_admin`）绕过所有 Project。
- 绕过不改变项目边界：跨 Project 访问仍按现有 `forbidden_scope`/404 合同拒绝。

### 7.3 快路径与性能

- Project 无任何保护集：view 为 `requires_filtering=False`，所有过滤调用为恒等操作；唯一新增成本
  是每请求一次保护集存在性查询（单表索引查询）。
- 有保护集：过滤为内存集合匹配；成员数通常个位数到数千。不做跨请求缓存（已冻结决策）；实测瓶颈
  后另立需求决策缓存方案。

### 7.4 fail-closed

PostgreSQL 保护集查询异常（连接失败、超时等）时，授权服务抛**通用依赖错误**（HTTP 503 / MCP
`dependency_error`，复用现有依赖错误合同）：**不放行**（会泄漏），也**不伪装成正常空结果**（会把
故障伪装成"全部不存在"）。坏 grant 记录（非字符串元素）按 §6.1 fail-closed 为空集。

## 8. SPARQL 面

不做任意查询重写。判定规则：

1. 解析本次查询 scope（现有 `SemanticQueryScopeResolver` 输出的 ontology/graph 集合）。
2. 计算该 scope 内的无权保护成员：`scope_unauthorized_members(scope.ontology_ids)`，成员按
   `ontology_id` 定位元数据归属；`ontology_id` 为空或失效的成员**保守视为在 scope 内**
   （fail-closed）。
3. 交集非空 → 整个 SPARQL 请求返回**通用 scope 错误**：复用 `SemanticQueryScopeNotReady`
   （HTTP 409 + `{"code": "scope_not_ready"}`；MCP `scope_not_ready`），消息使用与"scope 无可查询
   图"相同的通用常量文案，**不说明保护集、grant 或受保护资源**。
4. 交集为空（无保护集 / 成员都在 scope 外 / 主体满足全部覆盖保护集 / Admin 绕过）→ SPARQL 行为
   与现状完全一致。
5. **不得**因同一 Project 的其他、不在本次 scope 内的保护成员而拒绝查询。

保护集及其成员永远不进入 RDF 存储，因此默认图集 `role=policy` 的 graph 不再承载保护策略；现有
graph set 的 policy canonical role 与 `include_policy` 导出参数保持现状（导出的只是 legacy
policy graph 内容，与保护集无关），本交付不修改、不删除。

## 9. 读取面处置表（保留并校正）

### 9.1 HTTP（`backend/app/api/semantic.py` 除非另注）

| # | 面 | 处置 |
| --- | --- | --- |
| 1 | `GET /api/semantic/scopes:discover` | 不适用资源级过滤（目录级；"本体含受保护内容"粗粒度信号已接受）；保持现状 |
| 2 | `POST /api/semantic/context:query` | 过滤；anchor 精确 IRI 走 §5.1 同不存在合同；过滤在分页/cursor 前 |
| 3 | `POST /api/semantic/sparql:query` | 整体限制（§8）；补 principal 注入 |
| 4 | `GET /api/semantic/resources/{iri}` | 过滤 read-model items → 自然落入现有 404（逐字节一致）；补 principal |
| 5 | `GET /api/semantic/statements` | 行级过滤（limit 前）；补 principal |
| 6 | `GET /api/semantic/export` | 补 principal；Admin 全量；项目 key 仅其项目本体 graph + quad 级过滤；越权 `graph_iri` 无痕省略 |
| 7 | `GET /api/semantic/graph-sets/{id}` | 补 principal；项目边界保持现行中间件 403 `forbidden_scope` 合同（`graph_set_id` 已在所有权接缝内，跨项目与无法解析归属的同拒绝，不改 404——评审 H-3）；成员/指针元数据不做资源级过滤 |
| 8 | `GET /api/semantic/graph-sets/{id}/export` | quad 级过滤；`include_evidence` 时同步过滤挂接；补 principal |
| 9 | `GET /api/semantic/graph-sets/{id}/shapes/classes/{class_iri}` | 受保护类返回与未知类完全一致响应；补 principal |
| 10 | `GET /api/semantic/graph-sets/{id}/read-models/{model_name}` | 行级过滤（与查询过滤叠加，limit 前）；补 principal |
| 11 | `GET /api/ontologies/{ontology_id}/lineage`（`ontologies.py`） | target 为不可见成员/语句 → 与未知 target 同 not-found 合同；展开行过滤 |
| 12 | `GET /api/projects/{id}/evidence-references`（`evidence_references.py`） | reference 可见性过滤（§5.4），`total`/分页在过滤后计算 |
| 13 | `GET /api/evidence-references/{id}` | 整体隐藏的 reference → 与未知 id 同 404；否则关联过滤 |
| 14 | `GET /api/evidence-references/{id}/associations`、`GET /api/projects/{id}/evidence-associations` | 挂接到不可见成员的关联无痕过滤 |
| 15 | `GET /api/semantic/graph-sets/{id}/missing-evidence-facts`（`fact_evidence.py`） | 隐藏不可见语句的 fact_id（`count` 同步减少） |
| 16 | `GET /api/projects/{id}/evidence-artifacts`、`/evidence-artifacts/{id}`、`/chunks`（`evidence.py`） | 不适用+理由：artifact/chunk 与语义成员无挂接边；已记录边界（§13 R-3） |

### 9.2 MCP（对照 `MCP_TOOL_POLICIES` 全部 read 工具）

与第一轮相同面清单适用同样的处置：`query_semantic_context`（过滤+404 合同）、
`semantic_sparql_query`（整体限制）、`get_semantic_read_model`/`get_ontology_read_model`（行级过
滤）、`export_semantic_graph_set`（quad 级）、`get_entity_statement_context`（过滤+404 合同）、
`list_evidence_references`/`get_evidence_reference`（reference 可见性）、
`inspect_semantic_statement_provenance`/`get_ontology_lineage`（过滤+404 合同）；
`describe_semantic_graph_set`、`discover_semantic_scopes`、`get_modeling_context` 等目录/流程元数
据面不适用；建模流程记录面（Modeling Batch、workflow artifact、验证/推理运行记录、规则定义）维
持已记录边界（§13 R-2）。HTTP 与 MCP 同名面由同一 service 承载，等价性由共享代码路径保证。

## 10. 保护集管理 API 与 MCP 工具

### 10.1 HTTP（全部要求 model scope；admin 继承 model）

| 方法与路径 | 语义 |
| --- | --- |
| `GET /api/projects/{project_id}/protection-sets` | 列出本 Project 保护集（含 allowed_grants、成员计数） |
| `POST /api/projects/{project_id}/protection-sets` | 创建（name Project 内唯一、description、allowed_grants、初始成员可选） |
| `GET /api/protection-sets/{protection_set_id}` | 读取详情与成员清单（分页） |
| `PATCH /api/protection-sets/{protection_set_id}` | 修改 name/description/allowed_grants |
| `DELETE /api/protection-sets/{protection_set_id}` | 删除（成员非空 → `409 protection_set_not_empty`） |
| `POST /api/protection-sets/{protection_set_id}/members` | 批量添加成员（resource_iri 列表 + 可选 ontology_id 定位元数据；幂等） |
| `DELETE /api/protection-sets/{protection_set_id}/members` | 批量移除成员（按 resource_iri） |

- 管理面沿用现有授权接缝：Project 归属解析（R-008 §5.3）、model scope 校验（不足 → 403
  `forbidden_scope`）、写审计事件。
- **归属接缝扩展（评审 H-2 修订）**：现有 HTTP 中间件只对 `OWNER_RESOURCE_KEYS`
  （`backend/app/security/http.py`）中登记的路径/查询/主体键做 Project 归属校验。必须把
  `protection_set_id` 加入 `OWNER_RESOURCE_KEYS`，并在 `_project_for_resource`/
  `_collect_resource_ids` 中增加保护集类型解析（查 `semantic_protection_sets.project_id`）；
  `set_id` 路径参数统一命名为 `protection_set_id`。MCP 侧 PROJECT_RESOURCE 工具的归属校验经
  `_collect_resource_ids` 同步获得。不扩展该接缝会造成跨 Project 控制面绕过（项目 P 的 model
  key 可操作项目 P2 的保护集）。
- 新增全部路由必须登记进 `HTTP_ROUTE_POLICIES`（`test_authorization.py` 对每个操作要求注册），
  scope 为 `model`。
- 普通 Consumer（read scope）**不能读取保护集定义、成员清单或授权规则**：read 主体调用上述任何
  路由按现有 scope 合同 403 `forbidden_scope`（控制面拒绝，非语义知识读取面，无存在性泄漏问题）。

### 10.2 MCP 工具（新增，model scope，PROJECT_RESOURCE 归属）

建模团队只有平台协议 Agent 持有 Project-scoped model key 并调用平台接口（决策 15），因此保护集
管理必须提供 MCP 工具：

| 工具 | 语义 |
| --- | --- |
| `list_semantic_protection_sets` | 列出授权 Project 的保护集 |
| `create_semantic_protection_set` | 创建 |
| `update_semantic_protection_set` | 修改 name/description/allowed_grants |
| `delete_semantic_protection_set` | 删除（非空拒绝） |
| `add_semantic_protection_set_members` | 批量添加成员 IRI |
| `remove_semantic_protection_set_members` | 批量移除成员 IRI |

工具进入 `MCP_TOOL_POLICIES` 注册（`required_scope="model"`、`mutates_state` 相应设置），复用
`_authorize_tool` 的 Project 归属校验；与 HTTP 面共用同一 service 层（同一代码路径）。

### 10.3 审计

创建、修改、成员增删、grant 修改和删除必须写现有 `security_audit_events`（追加型安全事件），
event_type 建议：
`semantic_protection_set_created / _updated / _deleted / _members_added / _members_removed` 与
`api_key_updated`（grant 变更）。details 走现有字段 allowlist（`_AUDIT_DETAIL_KEYS`，
`backend/app/security/auth.py`），需为其扩充分量类型允许的键（如 `name`、`member_count`、
`grants_added`/`grants_removed` 等，实现时按最小必要确定）；不含 key 明文（grant 字符串本身非
秘密）。

### 10.4 建模团队职责分工（决策 15）

- 本体建模团队中，只有**平台协议 Agent** 直接持有临时 Project-scoped model key 并调用平台建模/
  保护集接口；建模 Agent、建模协调 Agent 不持平台写凭证。
- 流程：**建模 Agent** 提出保护范围（哪些资源 IRI 需要保护、建议的 grant）→ **建模协调 Agent**
  批准意图 → **平台协议 Agent** 转换为严格 MCP 调用执行（§v2.2 协作与错误路由不变）。
- 未来**保护集 Agent** 负责专业判断，但仍通过平台协议 Agent 落地，不直接持 key。

## 11. `SemanticVisibilityPolicy` 退役（保留第一轮方案）

1. 删除 `backend/app/services/semantic_visibility.py`（`SemanticVisibilityPolicy`/
   `VisibilityDecision`）与 `Settings.semantic_graph_visibility_labels`（含 `.env.example` 引用）。
2. 删除 `SemanticExportRequest.visibility_context`；消费面不再存在任何自报可见性字段。
3. `SemanticReadModelService`（`semantic_read_model.py`）与 `SemanticExportService`
   （位于 `semantic_graph_set_export.py`，即图集导出服务）的 `visibility_policy` 参数位改为传入
   `SemanticAccessView`（实现阶段核实：评审确认 2 中"类名为 `SemanticGraphSetExportService`"
   不准确，真实类名即 `SemanticExportService`）；`visibility_graph_omitted` warning 随类消失
   （该 warning 本身是存在性信号）。
4. 删除 `backend/tests/test_semantic_visibility.py`；调整相关 label 用例；完成门含全仓 grep 无
   残留（测试计划 R4）。

## 12. 需求与术语修订（实现阶段执行）

1. `requirements-v3.0.md` §1 存储分层表述：Ontology/RDF 保存业务语义和 Schema 映射；PostgreSQL
   保存 Project 级保护集与 API key grants；PostgreSQL 中的保护集属于平台控制面，不是业务行数据。
2. §1 原则句与 R3.0-004 正文：`forbidden` 改为与资源不存在不可区分的合同（精确 404/空结果、宽范
   围无痕子集、SPARQL 通用 scope 错误）；`forbidden_scope` 项目边界合同保持。
3. R3.0-004 验收示例：从 ServiceManager/ServiceOperator 角色改为 grant 持有（`cost-visibility`
   grant）主体对比。
4. R3.0-006 验收列表项同步改写。
5. R3.0-004 状态行与文档信息区链接更新为指向本设计与配套测试计划；R3.0-002/003/005/006 状态不变。
6. `glossary.md` 新增 Protection Set / Protection Set Member / Semantic Grant 词条并修订
   Semantic Knowledge Authorization（含 `_Avoid_`：Permission Set、Ontology policy graph、把
   grant 称为正式 Role、把语义知识保护误认为业务数据权限）。

## 13. 风险与已记录边界

- **R-1 粗粒度信号（已接受）**：SPARQL 整体失败与"scope 含受保护内容"信号已接受；scope
  discovery 仍列出含受保护内容的本体（目录级）。
- **R-2 建模流程记录面（已记录边界）**：Modeling Batch/Workflow Artifact/验证与推理运行记录可含
  受保护 IRI 或口径文本；本交付不逐项过滤，收紧需独立需求决策。
- **R-3 evidence artifacts/chunks（已记录边界）**：与语义成员无挂接边，不在挂接隐藏范围内。需求
  验收句"导出、证据与 lineage 不含该模块内容"中的"证据"按 evidence reference/association 解释；
  验收 fixture 同时保证 artifact/chunk 文本不含受保护模块内容，使验收句在不扩展过滤范围的前提
  下成立（评审确认 1）。
- **R-4 检索投影残留**：pgvector/搜索投影物理含受保护文本，查询时后过滤；平台内部信任边界不变。
- **R-5 先创建后保护的窗口**：决策 16 允许，窗口期内资源 Project 内普通可读；操作规程推荐先保护
  后创建。
- **R-6 悬空 IRI 清理**：Ontology 删除后成员悬空是合法状态，依赖人工/管理操作清理；无自动清理。
- **R-7 `ontology_id` 定位元数据失真**：成员的 ontology 失效/迁移后定位失效，SPARQL 判定按保守
  在 scope 内处理（可能多拒，不泄漏）；管理操作可修正。
- **R-8 性能**：每请求两次索引查询（保护集 + 成员）+ 内存过滤；当前规模可接受；缓存另立决策。

## 14. 验收标准

fixture：项目 P 含备件成本语义模块（类、成本指标、映射、枚举个体各至少一个成员 IRI）；保护集
`cost-visibility`；两个 key：Manager key 持 `cost-visibility` grant，Operator key 无 grant（名称只
在 fixture）。

| ID | 标准 |
| --- | --- |
| A1 | 精确不可区分：Operator 对受保护成员的精确请求在每个适用面按 §5.1 等价基准（同目标对照，或列举豁免回显字段）逐字节等价 |
| A2 | 宽范围无痕：授权子集、无 warning/cursor/total/计数/排序差异泄露；过滤在分页/cursor/排序前 |
| A3 | 语义知识读取面无 403/forbidden；`forbidden_scope` 项目边界合同不变（正反例） |
| A4 | SPARQL：scope 内含无权保护成员 → 409 `scope_not_ready` 通用错误；scope 外保护成员不触发拒绝 |
| A5 | 保护集内容不进入语义读取、导出或 SPARQL（PostgreSQL 控制面，天然满足并有负向测试） |
| A6 | 挂接隐藏：引用无权资源的关系、路径、mapping、evidence、lineage、派生内容被隐藏 |
| A7 | OR 公式：同资源多保护集任一满足即可访问；单保护集多 grant 任一满足即可 |
| A8 | 绕过：Project Admin 绕过本 Project；Org Admin 全局绕过；跨 Project 仍拒绝 |
| A9 | 管理面：model 可管理保护集但不能管理 key grants；read/Consumer 不能读控制面；admin-only grant 管理 |
| A10 | 生命周期：先保护后创建、先创建后保护都允许；移出最后一个保护集后恢复普通可读；悬空 IRI 保持保护；非空保护集不可删除 |
| A11 | fail-closed：空 allowed_grants 不可见；PostgreSQL 授权读取异常 → 通用依赖错误 |
| A12 | grant 即时生效/失效：更新无需重启；撤销 key 后立即失效 |
| A13 | HTTP/MCP 等价（同一授权代码路径，双 key MCP 实例或 HTTP+MCP 组合证明） |
| A14 | `SemanticVisibilityPolicy` 系列从消费面与仓库移除，无残留引用 |
| A15 | migration + 服务重启 + 健康检查 + live 双 key 验证通过；现有读面回归全绿 |
| A16 | §12 的需求与术语修订已落盘；审计事件写入验证 |

以上验收只证明语义知识保护，不证明数据库成本列不可查（业务数据安全边界不变）。在修订经过审核
前，R3.0-004 不得标记为已实现或已验收。

## 附录 A 技术要点（实现细节，非主线）

- migration：`0032_semantic_protection_sets.py`，建两张表 + `api_keys` 加列；降级逆操作。
- 主要改动文件：新增 `backend/app/services/semantic_access.py`、
  `backend/app/services/semantic_protection_set.py`、
  `backend/migrations/versions/0032_semantic_protection_sets.py`；修改
  `backend/app/repositories/models.py`、`backend/app/security/auth.py`、
  `backend/app/security/http.py`（OWNER_RESOURCE_KEYS/HTTP_ROUTE_POLICIES 归属与路由策略扩展）、
  `backend/app/api/auth.py`（/api-keys）、`backend/app/api/semantic.py`、
  `backend/app/api/evidence_references.py`、
  `backend/app/api/fact_evidence.py`、`backend/app/api/ontologies.py`、
  `backend/app/services/semantic_context_query.py`、`semantic_read_model.py`、
  `semantic_graph_set_export.py`、`semantic_export.py`、`scoped_sparql_query.py`、
  `evidence_reference.py`、`ontology_lineage.py`、`backend/app/mcp/runtime.py`（policy 注册）、
  `backend/app/mcp/tools/semantic.py`、`backend/app/mcp/tools/evidence.py`；删除
  `backend/app/services/semantic_visibility.py`；测试见配套共享测试计划。
- `AuthPrincipal` 为 frozen dataclass：新字段带默认值即可，现有构造点不需改动。

## 附录 B 评审记录

- **第一轮评审（2026-08-26，plan_reviewer）**：结论 REVISE。H-1 逐字节等价与回显字段矛盾
  （accepted-high → §5.1 增加同目标对照等价基准定义）；H-2 保护集归属接缝缺失
  （accepted-high → §10.1 增加 `protection_set_id` 归属接缝扩展与 `HTTP_ROUTE_POLICIES` 登记，
  附录 A 补 `security/http.py`）；H-3 §9.1 第 7 行 404 目标与中间件 403 合同冲突
  （accepted-high → 第 7 行改为保持现行 `forbidden_scope` 合同）；H-4 fixture 无法构造 scope 外
  用例（accepted-high → 测试计划增加第三本体 `O_c` 干净 scope，`PS_DANGLING` 补 ontology_id）。
  确认项：1) 需求验收句"证据"按 reference/association 解释，fixture 保证 artifact 不含受保护
  内容（§13 R-3 已补记）；2) `SemanticExportService` 名称有误，实际为
  `SemanticGraphSetExportService`（§11.3 已修正）；3) 审计 details allowlist 需扩展（§10.3 已补）。
  修订后送 plan_reviewer 复审。
- **第一轮复审（2026-08-26）**：四处 High 修复全部验证通过；遗留 H-5（context:query anchor 的
  `scope` 块回显不在豁免列表，同目标对照必然不同范围 → §5.1 与测试计划 §3 已把 scope 块列入该面
  命名豁免）与 H-6（§10.1 路由表 `{set_id}` 与归属键 `protection_set_id` 命名矛盾 → 路由表已统一
  为 `{protection_set_id}`）。评审方确认两项修正后整体 PASS，无需再次复审。
- **实现偏差处置（2026-08-26，主 Agent）**：1) §11.3 类名按实现事实修正——图集导出服务真实类名
  即 `SemanticExportService`（`semantic_graph_set_export.py`）；2) §4 成员 `ontology_id` 改为无
  FK 可空定位列（原 `FK ON DELETE NO ACTION` 与 R-6/A10 悬空成员语义矛盾）。两者均为文档纠偏，
  不改架构，无需再评审。
