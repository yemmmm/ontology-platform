# R-003 Build Context 调试页设计

**Date:** 2026-07-15  
**Status:** Approved for implementation  
**Requirement:** `docs/requirements-v1.0.md` R-003，后续可演进到 R-107

## 1. 目标

在现有 Debug 区域增加一个只读的 Project 级 `Build Context` 诊断页，直接展示
`GET /api/projects/{project_id}/build-context` 返回的服务器恢复视图，帮助开发者和外部 Agent
集成方核对：

- 平台已经观察到的事实；
- Agent 通过 Build Session 和 Checkpoint 报告的状态；
- 两类状态之间是否存在明显差异；
- 最近会话、阻塞、失败、未解决事项和工作区版本是否符合预期。

该页面是受控调试能力，不是面向普通用户的构建进度工作台。R-107 仍负责完整的 Evidence、
Build Session、建模批次和 Agent 活动工作台。

## 2. 现状与类型迁移

后端 R-003 接口已经返回新的顶层契约：

```text
project
generated_at
platform_state
agent_state
```

前端 `types.ts` 中仍保留旧的扁平 `BuildContext` 定义，但全仓没有运行时代码引用该类型。实现时
直接用新契约覆盖旧定义，不保留 legacy union、适配器或双结构判断。现有 Playwright mock 中的
旧响应仅是未被消费的历史桩；新增测试使用新契约，后续碰到旧桩时可机械更新。

## 3. 信息架构

在 Debug 阶段增加稳定 Tab：

```text
Debug
├── Debug
├── Build Context
├── Agent Test
├── Recall
├── MCP Tools
└── Graph Sets
```

Debug 首页增加 `Build Context` 工具卡。页面使用当前选中的 Project，不依赖当前 Ontology 或
Graph Set 是否就绪，因此不能被 ontology workspace gate 阻塞。

## 4. 页面内容

### 4.1 顶部状态

- Project 名称；
- `generated_at`；
- 手动刷新按钮；
- 请求失败时可重试的错误状态；
- 简短边界说明：平台事实和 Agent 报告分别展示，读取不会更新 `last_activity_at`。

### 4.2 Platform State

- Project Brief：完整度、缺失字段；
- Competency Question：按状态显示计数；
- Ontology Workspace：名称、状态、workspace state、是否可编辑、问题和不透明
  `workspace_version`；
- Evidence Reference 数量；
- Modeling Batch 数量及已有摘要。

页面不得把空 `modeling_batches` 解释成建模已经完成。R-004 接线完成前，空数组只显示为“未观察
到建模批次”。

### 4.3 Agent State

- active sessions；
- recent completed/cancelled sessions；
- Session status、revision、最后活动时间和最新 Checkpoint；
- 当前步骤、下一步、phase、关注 Ontology、blockers 和 failure；
- completed summary、cancel reason 和 unresolved items；
- 使用 `recent_sessions_next_cursor` 继续加载历史会话。

点击 Session 后只读调用 `GET /api/build-sessions/{session_id}`，展示 Checkpoint 历史、Lease
摘要、涉及的 Ontology、最近活动、批次与 Evidence 入口。首版可使用页面内详情区或抽屉，但不
引入新的顶层 Tab。

### 4.4 诊断提示

以确定性规则给出提示，不计算含义不清的完成百分比：

- 最新 Checkpoint 含 blocker 或 failure；
- Session 已完成但仍有 unresolved items；
- Agent 最新阶段为 `handoff`，但平台没有观察到建模批次；
- Ontology workspace 不可编辑或存在 issues。

提示只解释现有响应，不推断 Agent 的下一步，也不修改平台状态。

### 4.5 原始响应

提供可折叠的格式化 JSON，便于核对 REST/MCP 契约。原始响应必须与当前加载、分页合并后的
展示语义一致；不得展示接口本身未返回的 lease token、Graph IRI 或内部 Graph Set 信息。

## 5. 明确不做

- 不创建、恢复、完成或取消 Build Session；
- 不追加 Checkpoint；
- 不获取、续期或释放 Ontology Lease；
- 不提供任意请求体编辑器；
- 不托管或调用 Agent；
- 不把 Agent 报告状态提升为平台事实；
- 不将该页作为 R-003 完全实现的依据。R-004 apply 接线和 R-008 授权仍是独立缺口。

## 6. 前端实现

- 新增 `frontend/src/pages/BuildContextDebugPage.tsx`；
- 在 `frontend/src/types.ts` 以 R-003 新结构覆盖未使用的旧 `BuildContext` 类型，并补充 Session、
  Checkpoint、Workspace、Detail 类型；
- 在 `frontend/src/App.tsx` 的 `WorkspaceTab`、`workspaceTabs`、页面分发和 Debug 工具卡中注册
  `build-context`；
- 使用现有受治理 `request`，请求 `/projects/{project_id}/build-context` 和按需请求
  `/build-sessions/{session_id}`；
- 文案进入现有 i18n 词典，样式继续放在 `frontend/src/styles.css`。

## 7. 验收标准

1. Debug 首页可进入独立 Build Context Tab，刷新后展示当前 Project 的新 R-003 响应。
2. Platform State 与 Agent State 在视觉和语义上明确分离。
3. 页面在没有 Ontology、没有 Session、没有 Batch 时均能显示有效空状态。
4. active/recent Session 显示最新 Checkpoint、阻塞、失败和未解决事项。
5. recent Session 可根据 cursor 继续加载；Session 详情可只读查看。
6. 页面不会发出任何修改型 Build Session 或 Lease 请求，普通读取不改变 Agent 活动状态。
7. 页面不显示 Graph IRI、Graph Set 内部成员或 lease token。
8. 旧前端 `BuildContext` 类型被新契约直接覆盖，没有遗留双结构兼容逻辑。
9. `cd frontend && npm run build` 通过。
10. 新增 Playwright 覆盖入口、正常响应、状态分区、Session 详情、分页和空/错误状态；全量
    `cd frontend && npx playwright test` 通过。

