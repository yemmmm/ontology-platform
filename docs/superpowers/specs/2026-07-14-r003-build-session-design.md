# R-003 外部 Agent 构建会话与恢复协议设计

**Date:** 2026-07-14  
**Status:** Draft  
**Owner:** Agent  
**Requirement:** `docs/requirements-v1.0.md` R-003

## 1. 背景

外部建模 Agent 已经可以读取 Project Brief、能力问题和 Ontology 工作区，也可以通过 MCP
提交单条语义编辑或业务命令。但当前平台没有“一次构建工作”的持久记录：

- `GET /projects/{project_id}/build-context` 只是 Project、Brief、Ontology 和能力问题的旧聚合；
- Agent 中断后，当前步骤和下一步仍依赖聊天记录或本地文件；
- 平台不能区分 Agent 报告的进度与已经实际落库的结果；
- 两个 Agent 可以同时基于旧状态修改同一 Ontology，直到写入后才发现问题；
- 语义写入、Evidence Reference 和未来 R-004 建模批次没有统一的会话归属。

R-003 增加 Project 级 Build Session、追加式 Checkpoint 和 Ontology 级写租约。它只保存外部
Agent 的服务器端工作状态，不运行模型、不保存完整对话，也不接管外部文档阅读进度。

## 2. 设计目标

1. Agent 读取一次 Project 级 Build Context，即可获得全局状态和可恢复会话。
2. 一个 Build Session 可以依次处理 Project 内多个 Ontology。
3. 平台观察到的事实与 Agent 自己报告的计划明确分开。
4. Agent 断线、进程退出或租约过期后，active Session 仍可恢复。
5. 同一 Ontology 的 Agent 写入受租约和工作区版本双重保护，不发生静默覆盖。
6. REST 与 MCP 复用同一服务和状态语义，所有网络重试不会创建重复资源。
7. 外部构建协议不要求 Agent 读取或回传 Graph Set ID、graph IRI 或图成员角色。

## 3. 非目标

- 不托管 Agent、模型调用、对话、规划器或任务调度器。
- 不保存浏览器状态、外部文档阅读光标或 Agent 本地文件路径。
- 不在 R-003 定义 schema/entity/relation/fact 等批量写入格式；该格式属于 R-004。
- 不实现面向普通用户的进度工作台；该 UI 属于 R-107。
- 不把 Ontology Lease 当作身份权限；认证和 Project 授权属于 R-008。
- 不移除现有 Graph Set 存储和内部查询能力。
- 不为 Build Session 引入事件溯源、消息队列或后台保活任务。

## 4. 核心决策

### 4.1 Project 是恢复范围

Build Context 和 Build Session 均归属 Project。Agent 恢复时先看到 Project Brief、全部
Ontology、未解决事项和活动会话，再决定当前处理哪个 Ontology。

Build Session 不绑定单个 Ontology，也不锁定整个 Project。当前关注的 Ontology 记录在
Checkpoint 中；实际写入哪个 Ontology 由 R-004 批次明确指定。

### 4.2 Ontology 是外部写入范围

普通 Agent API 使用 `ontology_id`。平台通过 `OntologyWorkspaceService` 解析默认语义工作区，
内部记录实际 Graph Set、图修订和来源签名。

对外返回一个不透明的 `workspace_version`。首版通过
`SemanticGraphSetService.source_signature_for(...)` 按当前图成员和图修订重新计算，而不是直接
读取可能过期的缓存字段。调用方只能把它作为乐观并发令牌使用，不能解析其中的 Graph Set 或
图信息。

### 4.3 平台事实与 Agent 报告分开

Build Context 的顶层分为两部分：

- `platform_state`：从 Brief、能力问题、Ontology 工作区、Evidence、批次、验证和审计确定性
  派生，Agent 无法通过 Checkpoint 改写。
- `agent_state`：Build Session 和最新 Checkpoint，表示 Agent 报告的阶段、当前步骤、下一步、
  阻塞项和失败说明。

例如 Agent 可以报告“建模完成”，但如果没有成功批次和验证记录，平台状态仍显示“未观察到
完成结果”。服务不能把两者合并成一个含义不清的 `progress=100%`。

### 4.4 Build Session 不是 Agent 身份

一个 active Session 可以由另一个已授权 Agent 实例恢复。Session 代表连续工作过程，不代表
固定进程、模型、聊天窗口或 API key。

恢复者必须提交最新 Session revision。若旧 Agent 仍在追加 Checkpoint，乐观锁会返回冲突，
不会覆盖较新的进度。

## 5. 领域模型

### 5.1 Build Session

Build Session 保存一段 Project 级连续工作过程。首版状态只有：

```text
                 complete
              ┌────────────> completed
              │
create ────> active
              │
              └────────────> cancelled
                  cancel
```

- `active`：可追加 Checkpoint、恢复、获取租约和关联 R-004 批次；
- `completed`：显式完成后的终态；
- `cancelled`：显式取消后的终态。

不增加以下状态：

- `paused`：Agent 不在线只是缺少活动，不是持久业务状态；
- `failed`：失败属于 Checkpoint 或具体批次，修正后可以在同一 Session 继续；
- `expired`：过期的是 Ontology Lease，不是 Session；
- `blocked`：阻塞项是 Checkpoint 内容，不改变 Session 生命周期。

`resume` 是 active Session 上的动作：校验可恢复、更新最近活动并返回最新上下文。completed 或
cancelled Session 不可重新打开；继续工作时新建 Session，并使用 `previous_session_id` 连接前序。

### 5.2 Build Checkpoint

Checkpoint 是 Agent 上报的追加式进度记录，不能修改或删除。字段包括：

- `phase`：`intake`、`modeling`、`verification`、`handoff`；
- `current_step`：当前正在做什么，必填自由文本；
- `next_step`：计划下一步，可空；
- `ontology_id`：当前关注的 Ontology，可空；
- `summary`：本步骤结果摘要，可空；
- `blockers`：阻塞说明列表；
- `failure`：可选结构化失败说明，不代表 Session 进入失败状态。

Checkpoint 的 phase 只用于稳定分组和 UI 展示，平台不根据 phase 自动生成下一步，也不根据
phase 判断某项建模工作已经完成。

### 5.3 Ontology Lease

Ontology Lease 协调不同 Build Session 的 Agent 写入：

- 同一 Ontology 同一时刻最多有一个有效租约；
- 不同 Ontology 可以并行；
- 读取、构建上下文和 dry-run 不需要租约；
- R-004 apply 必须提交有效 lease token；
- 租约到期后旧 token 立即失效，但 Session 仍保持 active；
- 同一 Session 恢复时可以轮换自己的 token，使旧 Agent 实例失去写权限；
- 租约不是权限，仍需执行 R-008 的授权校验。

首版租约只强制保护新的 R-004 Agent apply 路径。现有专家级直接语义编辑或 UI 写入如果暂未
接入租约，仍会更新 `workspace_version`，从而使基于旧版本的 Agent apply 返回冲突。R-004
落地后，普通 Agent 建模流不得绕过该 apply 路径。

## 6. 持久化设计

首版只新增三张表，不增加 Session-Ontology 中间表。某 Session 涉及哪些 Ontology，可由
Checkpoint、有效/历史租约和后续 R-004 批次派生。

### 6.1 `build_sessions`

```sql
CREATE TABLE build_sessions (
    id                  VARCHAR(36)  PRIMARY KEY,
    project_id          VARCHAR(36)  NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    client_session_id   VARCHAR(255) NOT NULL,
    create_request_hash VARCHAR(64)  NOT NULL,
    previous_session_id VARCHAR(36)  REFERENCES build_sessions(id) ON DELETE SET NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'active',
    revision            INTEGER      NOT NULL DEFAULT 1,
    created_by          VARCHAR(255),
    last_resume_request_id VARCHAR(255),
    terminal_request_id VARCHAR(255),
    terminal_request_hash VARCHAR(64),
    completion_summary  TEXT,
    unresolved_items    JSONB        NOT NULL DEFAULT '[]',
    cancel_reason       TEXT,
    last_activity_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_build_sessions_project_client
        UNIQUE (project_id, client_session_id),
    CONSTRAINT ck_build_sessions_status
        CHECK (status IN ('active', 'completed', 'cancelled'))
);

CREATE INDEX ix_build_sessions_project_status_activity
    ON build_sessions(project_id, status, last_activity_at DESC);
```

`client_session_id` 由调用方稳定生成，用于创建请求重试。重复请求如果 payload 一致，返回已有
Session；如果同一 ID 对应不同 `previous_session_id` 或初始 Checkpoint，返回
`idempotency_conflict`。`create_request_hash` 保存规范化创建请求的 SHA-256，只用于比较重试
内容，不保存完整请求副本。

`terminal_request_id` 和 `terminal_request_hash` 只记录第一次成功的 complete/cancel 请求。
同一请求重试返回现有终态；同一请求 ID 配不同 payload 返回 `idempotency_conflict`。resume
不改变 Session revision，只更新 `last_activity_at` 和 `last_resume_request_id`，因此重复恢复不会
制造虚假版本冲突。

### 6.2 `build_checkpoints`

```sql
CREATE TABLE build_checkpoints (
    id                   VARCHAR(36)  PRIMARY KEY,
    build_session_id     VARCHAR(36)  NOT NULL
                         REFERENCES build_sessions(id) ON DELETE CASCADE,
    client_checkpoint_id VARCHAR(255) NOT NULL,
    sequence             INTEGER      NOT NULL,
    ontology_id          VARCHAR(36)  REFERENCES ontologies(id) ON DELETE SET NULL,
    phase                VARCHAR(32)  NOT NULL,
    current_step         TEXT         NOT NULL,
    next_step            TEXT,
    summary              TEXT,
    blockers             JSONB        NOT NULL DEFAULT '[]',
    failure_code         VARCHAR(100),
    failure_message      TEXT,
    related_batch_id     VARCHAR(36),
    reported_by          VARCHAR(255),
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_build_checkpoints_session_client
        UNIQUE (build_session_id, client_checkpoint_id),
    CONSTRAINT uq_build_checkpoints_session_sequence
        UNIQUE (build_session_id, sequence),
    CONSTRAINT ck_build_checkpoints_phase
        CHECK (phase IN ('intake', 'modeling', 'verification', 'handoff'))
);

CREATE INDEX ix_build_checkpoints_session_created
    ON build_checkpoints(build_session_id, sequence DESC);
CREATE INDEX ix_build_checkpoints_ontology
    ON build_checkpoints(ontology_id)
    WHERE ontology_id IS NOT NULL;
```

`related_batch_id` 在 R-004 表创建前不设置外键；R-004 实现时根据最终批次表决定是否补充
`ON DELETE SET NULL` 外键。

### 6.3 `ontology_leases`

一条 Ontology 最多保留一行当前租约槽位。释放和过期后复用该行，不需要后台清理任务。

```sql
CREATE TABLE ontology_leases (
    ontology_id            VARCHAR(36) PRIMARY KEY
                           REFERENCES ontologies(id) ON DELETE CASCADE,
    project_id             VARCHAR(36) NOT NULL
                           REFERENCES projects(id) ON DELETE CASCADE,
    build_session_id       VARCHAR(36) NOT NULL
                           REFERENCES build_sessions(id) ON DELETE CASCADE,
    token_hash             VARCHAR(64) NOT NULL,
    revision               INTEGER     NOT NULL DEFAULT 1,
    acquired_by            VARCHAR(255),
    acquired_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    renewed_at             TIMESTAMPTZ,
    expires_at             TIMESTAMPTZ NOT NULL,
    released_at            TIMESTAMPTZ,
    last_request_id        VARCHAR(255),
    last_request_operation VARCHAR(32),
    last_request_hash      VARCHAR(64),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_ontology_leases_session
    ON ontology_leases(build_session_id);
CREATE INDEX ix_ontology_leases_expiry
    ON ontology_leases(expires_at);
```

token 使用至少 256 bit 的安全随机值，响应中返回原值，数据库只保存 UTF-8 token 的 SHA-256。
同一 Session 重试获取租约时仍只有一行租约；若原响应丢失，平台可以轮换 token 并递增 lease
revision，而不是保存或恢复明文 token。`last_request_*` 用于拒绝同一客户端请求 ID 对应不同
操作或 payload；它不保存明文 token 或完整响应。

### 6.4 配置

新增配置：

```text
BUILD_SESSION_LEASE_TTL_SECONDS=300
```

服务端固定 TTL，首版不允许调用方自行指定。Agent 建议每 60 至 120 秒续期一次。服务使用
数据库时钟判断过期，避免多个 API 进程之间的系统时钟差异。

## 7. 并发算法

### 7.1 追加 Checkpoint

在一个数据库事务中：

1. `SELECT build_sessions ... FOR UPDATE`；
2. 校验 Session 为 active；
3. 先按 `(session_id, client_checkpoint_id)` 查询幂等命中；
4. 校验 `expected_revision == session.revision`；
5. 校验 `ontology_id` 归属同一 Project；
6. 使用 `max(sequence) + 1` 创建 Checkpoint；
7. Session revision 加一并更新 `last_activity_at`；
8. 提交并返回新的 Session revision。

幂等查询先于 revision 校验，保证第一次请求成功但响应丢失后，调用方使用旧 expected revision
重试时仍能拿到原结果。

### 7.2 获取 Ontology Lease

在一个数据库事务中锁定 Ontology 和租约槽位：

1. 校验 Session active，Ontology 与 Session 属于同一 Project；
2. 锁定 `ontology_leases` 对应行；不存在时尝试插入，唯一键冲突后重新读取；
3. 若现有租约未释放、未过期且属于其他 Session，返回 `ontology_lease_conflict`；
4. 若属于同一 Session，可返回当前租约或在恢复场景轮换 token；
5. 若已释放或过期，替换持有 Session、生成新 token、递增 revision；
6. `expires_at = database_now + 300 seconds`，更新 Session 最近活动；
7. 提交后仅在本次响应中返回明文 token。

获取租约不等待、不抢占其他 active Session。调用方可以读取冲突响应中的到期时间后决定稍后
重试，但平台不负责调度等待队列。

### 7.3 续期与释放

续期需要 `lease_token`、`expected_lease_revision` 和 `client_request_id`。服务锁定租约行，校验
token hash、Session、revision 和未过期状态，然后把到期时间设置为数据库当前时间加固定 TTL。

释放也需要 token。第一次释放设置 `released_at` 并递增 revision；相同请求重试返回当前已释放
状态。完成或取消 Session 时，平台在同一事务中释放该 Session 的所有租约。

resume 只校验 expected Session revision、记录最近活动并返回当前恢复上下文，不递增 Session
revision。这样第一次 resume 成功但响应丢失时，同一 expected revision 仍可安全重试；如果期间
出现了新 Checkpoint，resume 会看到真正的 revision 冲突。

### 7.4 工作区版本

R-004 dry-run 返回当前 `workspace_version`。apply 同时校验：

1. Session active；
2. lease token 有效；
3. 请求中的 `expected_workspace_version` 仍等于当前值。

租约防止多个 Build Session 同时通过 Agent apply 写入；workspace version 还可以发现租约之外
的专家编辑、UI 编辑或系统修复。任一校验失败都不得开始 RDF 写入。

### 7.5 最近活动

以下成功操作更新 Session `last_activity_at`：创建、resume、追加 Checkpoint、获取/续期/释放
租约、complete/cancel，以及后续 R-004 批次状态变化。普通 GET、Build Context 轮询和 MCP
只读工具不更新该字段，避免监控和 UI 刷新把无人工作的 Session 伪装成活跃状态。

首版不增加通用活动事件表。最近活动列表由 Checkpoint、租约时间和 R-004 批次时间按时间倒序
聚合；只有出现无法从这些权威记录表达的真实活动类型时，才考虑独立 activity 表。

## 8. REST 契约

所有请求和响应使用 Pydantic `extra="forbid"`。actor 在 R-008 完成后只能来自认证主体；在
R-008 之前沿用受控依赖提供的开发主体，不能让业务服务直接信任任意请求字段。

### 8.1 Project Build Context

```http
GET /api/projects/{project_id}/build-context?recent_session_limit=10
```

响应骨架：

```json
{
  "project": {"id": "p-1", "name": "Dify knowledge"},
  "generated_at": "2026-07-14T10:00:00Z",
  "platform_state": {
    "project_brief": {
      "completeness": 0.8,
      "missing_fields": ["inference_scope"]
    },
    "competency_question_counts": {"approved": 4, "passed": 2},
    "ontologies": [
      {
        "id": "ont-1",
        "name": "Dify API",
        "status": "draft",
        "workspace": {
          "state": "ready",
          "workspace_version": "opaque-version-token",
          "editable": true,
          "issues": []
        }
      }
    ],
    "evidence_reference_count": 12
  },
  "agent_state": {
    "active_sessions": [],
    "recent_sessions": [],
    "recent_sessions_next_cursor": null
  }
}
```

普通 Build Context 不返回 Graph Set ID、graph IRI 或图角色。受控
`get_ontology_workspace_context` 继续提供平台诊断所需的底层详情。

现有同路径旧接口由新服务替换并移除 `Deprecation`/`Sunset` 响应头。前端目前不依赖旧响应；
旧 API 测试改为验证新的 Project 级结构。

### 8.2 创建 Build Session

```http
POST /api/projects/{project_id}/build-sessions
```

```json
{
  "client_session_id": "agent-run-20260714-001",
  "previous_session_id": null,
  "initial_checkpoint": {
    "client_checkpoint_id": "cp-001",
    "phase": "intake",
    "current_step": "Review project brief",
    "next_step": "Inspect existing ontologies",
    "ontology_id": null,
    "summary": null,
    "blockers": [],
    "failure": null
  }
}
```

创建 Session 与可选初始 Checkpoint 在同一事务中完成。首次创建返回 `201`；幂等命中返回
`200` 和已有资源。

### 8.3 读取与恢复

```http
GET  /api/build-sessions/{session_id}?checkpoint_limit=50&checkpoint_cursor=...
POST /api/build-sessions/{session_id}:resume
```

resume 请求：

```json
{
  "client_request_id": "resume-002",
  "expected_revision": 7
}
```

响应至少包含 Session、最新 Checkpoint、分页历史、当前有效或过期租约摘要、涉及的
Ontology ID、后续 R-004 批次摘要以及证据引用入口。Build Context 和 Session 详情中的租约
永远不返回 token。

### 8.4 追加 Checkpoint

```http
POST /api/build-sessions/{session_id}/checkpoints
```

```json
{
  "client_checkpoint_id": "cp-008",
  "expected_revision": 8,
  "phase": "modeling",
  "current_step": "Model workflow publication operation",
  "next_step": "Dry-run the modeling batch",
  "ontology_id": "ont-1",
  "summary": "Created the operation parameter draft",
  "blockers": [],
  "failure": null
}
```

### 8.5 完成与取消

```http
POST /api/build-sessions/{session_id}:complete
POST /api/build-sessions/{session_id}:cancel
```

完成请求：

```json
{
  "client_request_id": "complete-001",
  "expected_revision": 12,
  "summary": "Updated API operation knowledge and verified the batch",
  "unresolved_items": ["Publication benchmark has not run yet"]
}
```

取消请求必须提供非空 `reason`。完成或取消都释放全部租约并返回终态 Session。重复执行相同
终态操作返回当前资源；completed 与 cancelled 之间互相转换返回冲突。如果 R-004 已存在状态
为 `applying` 或 `recovering` 的批次，complete 返回 `in_flight_batch`，不能把未收敛的写入标记
为会话完成。

### 8.6 Ontology Lease

```http
POST /api/build-sessions/{session_id}/ontology-leases/{ontology_id}:acquire
POST /api/build-sessions/{session_id}/ontology-leases/{ontology_id}:renew
POST /api/build-sessions/{session_id}/ontology-leases/{ontology_id}:release
```

获取请求包含 `client_request_id`、`expected_session_revision` 和可选 `rotate_token=false`。响应：

```json
{
  "ontology_id": "ont-1",
  "build_session_id": "bs-1",
  "lease_token": "returned-only-on-acquire-or-renew",
  "lease_revision": 3,
  "expires_at": "2026-07-14T10:05:00Z"
}
```

renew/release 请求还必须带 `lease_token` 和 `expected_lease_revision`。

## 9. 错误协议

新接口使用结构化 `detail`：

```json
{
  "detail": {
    "code": "session_revision_conflict",
    "message": "Build Session changed after the caller last read it",
    "current_revision": 9
  }
}
```

稳定错误码：

| HTTP | code | 含义 |
| --- | --- | --- |
| 404 | `build_session_not_found` | Session 不存在或调用方不可见 |
| 404 | `ontology_not_found` | Ontology 不存在或不属于可见 Project |
| 409 | `idempotency_conflict` | 同一客户端 ID 对应不同 payload |
| 409 | `session_revision_conflict` | Session revision 已变化 |
| 409 | `session_terminal` | 对 completed/cancelled Session 执行活动操作 |
| 409 | `in_flight_batch` | Session 仍有 applying/recovering 批次 |
| 409 | `ontology_lease_conflict` | 另一个 Session 持有有效租约 |
| 409 | `lease_revision_conflict` | lease revision 已变化 |
| 409 | `lease_expired` | token 对应的租约已过期 |
| 409 | `workspace_revision_conflict` | Ontology 工作区自 dry-run/读取后发生变化 |
| 422 | `checkpoint_validation_failed` | phase、步骤或失败结构不合法 |

跨 Project 资源统一按 404 处理，不能通过冲突响应泄露其他 Project 的名称、Agent 或详细进度。

## 10. MCP 契约

新增 `backend/app/mcp/tools/build_sessions.py`，注册：

- `get_project_build_context`
- `create_build_session`
- `get_build_session`
- `resume_build_session`
- `save_build_checkpoint`
- `complete_build_session`
- `cancel_build_session`
- `acquire_ontology_lease`
- `renew_ontology_lease`
- `release_ontology_lease`

工具参数与 REST schema 一一对应，统一调用 `BuildSessionService`，不通过 HTTP 回调自身。

旧 `get_build_context(project_id)` MCP 工具保留一个发布周期，直接委托
`get_project_build_context` 的新服务并在 description 标记 deprecated，不保留旧响应结构或第二套
聚合逻辑。后续由 R-011 对照运行时 registry 删除旧别名并更新 `docs/mcp.md`。

## 11. 服务边界与代码落点

### 11.1 新增

- `backend/migrations/versions/0022_build_sessions.py`
- `backend/app/api/build_sessions.py`
- `backend/app/services/build_sessions.py`
- `backend/app/mcp/tools/build_sessions.py`
- `backend/tests/test_build_session_service.py`
- `backend/tests/test_build_session_api.py`
- `backend/tests/test_build_session_mcp.py`

### 11.2 修改

- `backend/app/repositories/models.py`：增加三个 SQLAlchemy model 和状态 enum；
- `backend/app/api/schemas.py`：增加请求、详情、摘要和错误 schema；
- `backend/app/api/routes.py`：注册 Build Session router；
- `backend/app/api/interview.py`：移除旧 build-context handler 和该路由的 deprecation header；
- `backend/app/services/interview.py`：移除旧 `get_build_context` 聚合；
- `backend/app/mcp/tools/__init__.py`：注册新工具域；
- `backend/app/mcp/tools/interview.py`：旧工具改为兼容委托；
- `backend/app/core/config.py`、`.env.example`：增加固定租约 TTL；
- `docs/api.md`、`docs/mcp.md`：记录真实接口和兼容期；
- `docs/requirements-v1.0.md`：实现后更新状态、提交和验证证据。

### 11.3 服务职责

`BuildSessionService` 只负责 PostgreSQL 会话状态、Checkpoint、租约和上下文编排。它通过现有
服务读取 Brief、能力问题和 Ontology workspace context，不直接查询 RDF，也不自行判断本体
建模是否正确。

Build Session 不直接关联 Evidence Reference，也不增加“Session 使用某文档”的表。Session
详情中的证据入口从 R-004 批次及其具体 Evidence Association 派生，保持 R-002 的具体建模项
证据边界。

R-004 批次服务通过一个窄接口调用：

```python
guard = build_session_service.authorize_apply(
    session_id=session_id,
    ontology_id=ontology_id,
    lease_token=lease_token,
    expected_workspace_version=expected_workspace_version,
)
```

返回内部解析的 Graph Set、目标图和当前 workspace version。批次成功或失败后，R-004 再调用
`record_batch_activity(...)`；R-003 不导入 R-004 的具体命令编译器，避免循环依赖。

## 12. 事务和双存储边界

Build Session、Checkpoint 和 Lease 全部在 PostgreSQL 内，可使用单一数据库事务。

R-004 apply 还会写 RDF，无法与 PostgreSQL 使用同一原子事务。R-003 不声称解决该问题；R-004
必须设计持久批次记录和恢复状态：

1. 在 PostgreSQL 中记录准备应用及内部解析的工作区版本；
2. 执行 RDF 写入和确定性校验；
3. 更新图修订、审计、Evidence Association 和批次结果；
4. Build Context 根据批次记录显示成功、失败或恢复中。

如果 RDF 成功但 PostgreSQL 最终提交失败，R-004 的恢复器必须根据 idempotency key 和 RDF
delta 收敛；不能用一个 Checkpoint 冒充跨存储事务完成。

## 13. 安全与隐私

- lease token 只保存哈希，不写日志、Checkpoint、审计 delta 或 Build Context；
- Checkpoint 文本限制长度，拒绝把完整文档或密钥作为进度说明保存；
- 结构化日志只记录 Session ID、Ontology ID、操作、revision、结果和耗时；
- `created_by`、`reported_by`、`acquired_by` 在 R-008 后来自认证主体；
- Build Context 不返回其他 Project 的 Session、租约冲突详情或 Evidence；
- cancel reason、failure message 和 blockers 按审计数据处理，不提供物理删除入口。

## 14. 验证方案

### 14.1 服务级

- Session 创建、客户端 ID 幂等及 payload 冲突；
- 可选初始 Checkpoint 与 Session 原子创建；
- Checkpoint 顺序、幂等、phase 校验和 revision 冲突；
- active → completed/cancelled 转换及终态拒绝；
- 失败 Checkpoint 后继续追加成功 Checkpoint；
- resume active、拒绝恢复终态；
- Ontology 跨 Project 拒绝；
- 同 Ontology 租约冲突、不同 Ontology 并行；
- token hash、续期、释放、过期和同 Session token 轮换；
- complete/cancel 自动释放全部租约；
- workspace version 变化后 apply guard 拒绝。

### 14.2 REST

- Project Build Context 同时包含 `platform_state` 和 `agent_state`；
- Build Context 不暴露 Graph Set ID、graph IRI 或 lease token；
- 分页游标不会静默遗漏 Checkpoint；
- 每个稳定错误码和 HTTP 状态；
- 旧 build-context deprecation header 被移除；
- OpenAPI schema 对所有写请求拒绝额外字段。

### 14.3 MCP

- 十个新工具进入运行时 registry；
- 每个工具复用服务层且输入字段与 REST 一致；
- 旧 `get_build_context` 只作为委托别名；
- MCP 列表、详情和 Build Context 不暴露 SQLAlchemy 对象、Graph Set 细节或 lease token；只有
  acquire/renew 的直接响应可以把当前明文 token 返回给调用方。

### 14.4 PostgreSQL 并发

SQLite 无法证明 `SELECT FOR UPDATE` 和唯一租约槽位在竞争条件下正确。至少增加一个真实
PostgreSQL 集成测试，用两个独立事务同时获取同一 Ontology 的租约，断言只有一个成功，另一个
得到 `ontology_lease_conflict`。

### 14.5 交付命令

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest
```

R-003 不改变前端；本项不要求 Playwright。若实现过程中修改 R-107 相关 UI，则另行执行
`cd frontend && npm run build` 与 `cd frontend && npx playwright test`。

## 15. 实施顺序

1. 增加迁移、model、enum 和 schema；
2. 实现 Build Session 与 Checkpoint 服务及测试；
3. 实现 Ontology Lease、工作区版本 guard 和 PostgreSQL 并发测试；
4. 新增 REST router，替换旧 build-context 聚合；
5. 新增 MCP 工具并保留旧工具委托别名；
6. 更新 API/MCP 文档并运行全量 backend pytest；
7. 在 R-004 中接入 apply guard、批次活动和 Evidence Association。

R-003 可以先独立交付 Session、Checkpoint 和租约 API；但在 R-004 apply 接入租约与
workspace version guard 之前，只能标记为“进行中”，不能标记为“已实现”。

## 16. 被否决的方案

### 16.1 Build Session 绑定 Graph Set

否决。v1 普通 Agent 以 Project 和 Ontology 工作，不应管理内部图组合。Graph Set 只进入平台
审计和高级语义接口。

### 16.2 Build Session 绑定单个 Ontology

否决。Agent 恢复时需要 Project 全局认识，一个连续任务也可能依次更新多个 Ontology。

### 16.3 Project 级租约

否决。它会阻止不同 Agent 并行处理不同 Ontology，冲突范围过大。

### 16.4 只使用乐观锁，不使用租约

否决。只在 apply 时发现冲突会让两个长时间运行的 Agent 重复完成相同建模工作。Ontology
Lease 提前表达正在编辑，workspace version 再处理租约之外的变更。

### 16.5 增加 paused、failed、expired 状态

否决。这些词分别描述 Agent 在线情况、一次尝试结果和租约状态，会使 Session 状态机承担
互不相同的含义。

### 16.6 为每个 Session 建立 Ontology Target 表

首版否决。涉及的 Ontology 可以从 Checkpoint、租约和 R-004 批次派生；在出现无法由这些记录
表达的真实需求前，不增加第四个状态来源。
