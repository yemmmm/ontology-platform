# R1.1-002 分阶段、可追溯的建模工作流设计

## 1. 状态与决策摘要

设计状态：原平台/Skill 方案与 2026-07-18 repo-local Codex Harness 增补方案均已评审通过，开发就绪。
需求来源为 `docs/requirements/requirements-v1.1.md` 的 R1.1-002，效果证据归入 R1.1-001；功能契约和首轮 Dify
业务目标已由用户逐项确认。

1. 首版交付重构后的 `ontology-builder`、Build Session 下不可变 Modeling Workflow Artifact、
   追加式 Modeling Execution Event、REST/MCP 查询与 JSON/Markdown 导出，不新增复杂前端页面。
2. 外部 Agent 负责业务理解、提问、建模和质量判断；平台只做结构、权限、幂等、引用归属、内容
   哈希、版本、顺序、秘密扫描和持久化等确定性工作。
3. Artifact 以逻辑 `artifact_key` 形成线性版本链；Event 以 `client_event_id` 幂等追加并由平台分配
   Session 内序号。两者均不可 PATCH/DELETE，更正只能追加新版本或 superseding event。
4. 新资源使用 `workflow_artifact_id` 和 `execution_event_id`，避免与 R-002 旧 Evidence Artifact 的
   `artifact_id` 授权含义冲突。
5. 首轮真实运行使用 Codex CLI `gpt-5.6-terra` + `medium`，业务整理、建模和评审分别启动独立新
   上下文；模型不足作为证据留档，不在同轮中静默换模。
6. Dify 核心纵向切片只覆盖 Workflow 输入/节点与数据依赖、发布、API 执行、运行状态和日志排障；
   知识库、插件及其他应用类型进入 Coverage Matrix 的 `DEFERRED` 项。

## 2. 目标、非目标与完成门槛

### 2.1 目标

- 让另一个已授权 Agent 不依赖原聊天或本地缓存即可恢复同一 Build Session，读取当前业务产物、
  已确认问题、历史决定、评审/返工和明确下一步。
- 让主 Agent 通过版本化 Business Knowledge Pack、Modeling Coverage Matrix、模型草案、评审报告
  和验收报告显式交接各角色产物。
- 在 apply 前执行业务、语义、覆盖、证据、平台和独立评审门禁，在 apply 后执行查询、validation
  与 lineage 验收。
- 为后续比较工作流版本保留 Runtime、模型、推理档位、角色 prompt 版本、耗时、token/成本摘要和
  结构化质量问题，但不把这些指标当作质量结论。
- 用官方 Dify 网页完成一次真实、可复核的端到端运行，并由用户判断模型是否对业务理解有价值。

### 2.2 非目标

- 不运行旧 Skill 建立单 Agent 对照，不把旧 traces 当作新流程效果证据。
- 不托管 Agent Runtime，不生成 Codex/OpenCode/Claude Code 专用持久 Agent 配置，不建设通用编排
  引擎或自动任务调度。
- 不由平台解析业务网页、生成问题、判断本体质量、推断根因或自动选择下一步。
- 不保存完整聊天、隐藏推理、系统 prompt 正文、完整原始网页、凭证或秘密。
- 不新增复杂 Workflow UI；R-107 是否接入由真实使用反馈决定。
- 不为 Dify 新增专用表、接口、枚举或语义命令。

### 2.3 首轮高优先级能力问题

1. 一个 Dify Workflow 在发布和 API 执行前，需要哪些输入、节点及数据依赖？
2. 发布后的 Workflow 应如何调用，并如何理解运行状态、输出和关键执行信息？
3. Workflow 执行失败时，哪些运行与日志信息可以定位问题，并指导下一步排查？

R1.1-002 只有在平台/Skill 门禁、独立测试、真实 Dify 运行和用户业务价值评审全部通过后才标记
`已实现`。单次运行只为 R1.1-001 提供首轮证据，不足以证明可重复改善。

## 3. 角色与工作流

### 3.1 角色

- **业务整理子 Agent**：扫描资料，输出 Business Knowledge Pack、Coverage Matrix 和最多三个阻塞
  问题；不得定义 Class、Property、RelationType 或 Modeling Batch。
- **建模子 Agent**：只读取已确认业务产物、Evidence 和当前 Modeling Context，输出模型草案与
  Modeling Batch 草案；不得获取 lease 或 apply。
- **质量评审子 Agent**：读取原始资料清单、关键原文/可访问来源、Pack、Matrix、模型草案和 dry-run
  Findings，输出 `PASS | REVISE | BLOCKED`；不得修改或提交模型。
- **主 Agent**：向用户提问、持久化产物/事件、组织返工、调用 dry-run、唯一获取 lease 和 apply、
  执行反向验收并结束 Session。

三个子角色必须是独立新上下文。Runtime 不支持子 Agent 时只能记录为单 Agent fallback，不能把同一
上下文角色切换写成多 Agent 结果。

### 3.2 首版阶段

`recovery -> global_scan -> business_confirmation -> core_modeling -> dry_run -> review -> apply ->
verification -> expansion_or_handoff`

主 Agent 在每个阶段保存 Artifact/Event，并在中断点保存 Build Checkpoint。Checkpoint 仍表达当前
位置和下一步；Execution Event 表达发生过的动作、显式决定和引用。Modeling Batch、Validation、
Evidence、Audit 与当前语义读模型继续是平台事实来源，Event 不复制或覆盖它们。

## 4. Modeling Workflow Artifact

### 4.1 版本模型

新增 `modeling_workflow_artifacts`，每一行即一个不可变版本：

- `id`、`project_id`、`build_session_id`、可选 `ontology_id`；
- `artifact_key`：Session 内稳定的逻辑产物名，例如 `business-knowledge-pack`；
- `client_version_id`、`request_hash`：版本创建幂等键与规范请求哈希；
- `version`：同一 `(build_session_id, artifact_key)` 下从 1 递增；
- `artifact_type`：`business_knowledge_pack | modeling_coverage_matrix | modeling_draft |
  review_report | verification_report`；
- `content_format`：`json | markdown`；
- `content`：JSON object/list 或 Markdown string，使用 JSONB 保存；
- `content_hash`：JSON 使用排序、紧凑 UTF-8 canonical encoding，Markdown 使用原 UTF-8 bytes；
- `created_by_role`、`workflow_name`、`workflow_version`、`role_prompt_version`；
- 可选 `supersedes_workflow_artifact_id`、`created_at`。

唯一约束：

- `(build_session_id, client_version_id)`；
- `(build_session_id, artifact_key, version)`。

创建时锁定 Build Session 行。首版必须没有 supersedes 且分配 version 1；后续版本必须 supersede 当前
最新版本，artifact key/type/Session 不变，否则返回 stale/conflict。相同 `client_version_id` 与相同
规范请求返回原行；不同请求返回 `idempotency_conflict`。不提供修改和删除 API。

### 4.2 内容边界

- JSON format 只接受 object/list；Markdown 只接受 string。
- 单版本 canonical content 首版上限 1 MiB，超限返回 `workflow_artifact_too_large`。
- 平台不解释业务结论，也不强制某个领域本体；`ontology-builder` 用模板和 eval 保证 Pack、Matrix、
  review 的结构。
- Pack 和 Matrix 的机器交接使用 JSON；Markdown 主要用于人类复盘和导出。模型草案允许 JSON，报告
  允许 JSON 或 Markdown。

## 5. Modeling Execution Event

### 5.1 追加模型

新增 `modeling_execution_events`：

- `id`、`project_id`、`build_session_id`、可选 `ontology_id`；
- `client_event_id`、`request_hash`、Session 内 `sequence`；
- `workflow_name`、`workflow_version`、`phase`、`event_type`、`status`；
- `report_source`：`agent_reported | user_reported | platform_observed`；外部 REST/MCP 只能提交前两种；
- `actor_role`、`role_prompt_version`、`agent_runtime`、`agent_model`、`reasoning_effort`；
- `summary`、input/output Artifact version IDs；
- 可选 `question_id`、`question_state`、用户可见的 `question_text` / `answer_text`、
  `expected_question_head_event_id` 和 Interview Answer ID；
- 显式 decisions、rejected alternatives、unresolved items、blockers 和 next step；
- typed `related_resources`，引用 Competency Question、Evidence Reference、Modeling Batch/Attempt、
  Validation 或 Lineage 等稳定平台资源；Finding 使用 Attempt ID + 平台分配的稳定
  `finding_fingerprint`，不以 code/path 猜测唯一性；
- `quality_issues`、可选 duration/model/token/cost metrics；
- 可选 `supersedes_execution_event_id`、`occurred_at`、服务器 `created_at`。

首版事件类型采用需求列出的 12 种：`source_scanned`、`artifact_created`、`question_asked`、
`answer_recorded`、`decision_recorded`、`dry_run_completed`、`review_completed`、`rework_requested`、
`batch_applied`、`verification_completed`、`phase_completed`、`blocked`。

事件 payload canonical JSON 上限 64 KiB。`quality_issues` 确定性校验 category、introduced/detected
phase、detected role、severity、rework cost 和 preventable phase；根因允许 `unknown` 或显式
hypothesis，不由平台升级为事实。

问题使用 Agent 生成的稳定 `question_id` 串联整个 Session。`question_state` 为
`open | answered | skipped | uncertain | reopened`。创建 Event 已锁定 Build Session 行；在同一锁内
读取该 question ID 的当前 head，并执行线性状态转换：

- 首个 `question_asked(open)` 要求不存在 head，`expected_question_head_event_id=null`；同 ID 重复 open
  返回 `question_state_conflict`。
- `answer_recorded(answered|skipped|uncertain)` 必须令 `expected_question_head_event_id` 等于当前
  open/reopened head。answered 需要用户可见 answer 或 Interview Answer ID；skipped/uncertain 需要
  显式原因。
- `question_asked(reopened)` 只能从 answered/skipped/uncertain head 转换，必须精确引用该 current
  head，语义上重新成为 open。
- 对 resolved answer 的更正必须精确引用 current head，同时令
  `supersedes_execution_event_id=current head`；否则不能用普通 answer event 静默替换。

任一 expected head 缺失、stale、foreign 或状态不允许都返回 409 `question_state_conflict`，并返回当前
head ID/state（不含 answer 内容）。Session 行锁使两个并发回答只有一个成功，后一个看到新 head 后
冲突。按 sequence 取每个 question ID 唯一 head 得到 current state；Build Session workflow summary
和 export 都返回该状态，使恢复 Agent 不重复 answered/skipped 问题，只在来源变化、用户 reopen 或
模型冲突暴露新含义时再次提问。

### 5.2 顺序、幂等与更正

创建事件锁定 Build Session 行，先检查 `(build_session_id, client_event_id)`，再以 Session 当前最大
sequence + 1 分配序号。相同 ID/请求返回原事件，不同请求返回 `idempotency_conflict`。Artifact/Event
追加不增加 Build Session revision，避免日志写入让 lease/checkpoint 的 expected revision 无关失效；
只更新 `last_activity_at`。

superseding event 必须引用同 Session 的更早事件且不能形成分叉式重写。原事件始终可读；导出同时
展示原事件和更正关系。

### 5.3 引用归属

服务层逐一解析 Artifact、Event 和相关平台资源，要求全部属于同一 Project；Session-scoped 资源还
必须属于当前 Session。Modeling Batch 在形成 Attempt findings 时，为每个 Finding 追加稳定唯一
`finding_fingerprint`：对 Attempt ID、Finding 在该 Attempt 中的稳定 ordinal、code、scope、排序后的
client item IDs、path 和 canonical details 做 SHA-256；结果与 Finding 一起持久化并由 REST/MCP 返回。
Event 只能引用该 Attempt 中精确存在的 fingerprint。即使多个 item 产生相同 code/path，也不会把
review/返工关联到错误 Finding。

外部 payload 不能将 `report_source=platform_observed`，也不能自报 actor 覆盖认证主体。Lease 只记录
ontology ID/revision 等非秘密摘要，永不保存 token。

## 6. REST 与 MCP 合同

### 6.1 REST

- `POST /api/build-sessions/{session_id}/modeling-workflow-artifacts`
- `GET /api/build-sessions/{session_id}/modeling-workflow-artifacts`
- `GET /api/modeling-workflow-artifacts/{workflow_artifact_id}`
- `POST /api/build-sessions/{session_id}/modeling-execution-events`
- `GET /api/build-sessions/{session_id}/modeling-execution-events`
- `GET /api/modeling-execution-events/{execution_event_id}`
- `GET /api/build-sessions/{session_id}/modeling-workflow:export?format=json|markdown`

Artifact list 支持 type、key、ontology、`current_only`、cursor/limit；Event list 支持 phase、event type、
cursor/limit，cursor 使用稳定 sequence。Export 包含 Session 摘要、全部 Artifact 版本/当前版本索引和
按 sequence 排序的完整 Event 时间线；JSON 返回结构化对象，Markdown 返回可复盘时间线。首版 export
上限 8 MiB，超限返回 `modeling_workflow_export_too_large`，调用方仍可用分页 API 读取全部数据。

POST 成功为 201，相同幂等重试为 200。GET 需要 `read`，POST 需要 `model`。不存在或 foreign opaque
资源遵守 R-008 的 404 防枚举；显式 foreign Project 返回 403。

### 6.2 MCP

新增同一 service 的七个工具：

- `create_modeling_workflow_artifact`
- `get_modeling_workflow_artifact`
- `list_modeling_workflow_artifacts`
- `record_modeling_execution_event`
- `get_modeling_execution_event`
- `list_modeling_execution_events`
- `export_modeling_workflow_record`

MCP 采用与 REST 相同的 schema、幂等、错误与 Project resolver；写工具使用认证 principal 的 actor。
工具加入 runtime registry、catalog 分类、`docs/reference/mcp.md` 和 `ontology-builder` 的依赖/eval 契约。

## 7. 安全、隐私与失败行为

- 复用 `backend/app/security/secrets.py` 的递归高可信 scanner；所有 HTTP 写入在 service/persistence
  前拒绝 secret。MCP 在统一 runtime wrapper 中执行同一 scanner，避免 adapter 差异。
- 主 Agent 对用户回答、网页摘录和业务产物负提交前脱敏责任；平台不自动修改内容。命中返回 422
  `secret_in_payload` 和类别，不返回原值/路径上下文。
- 允许 `<TOKEN>`、`${API_KEY}`、`REDACTED` 等占位符和凭证术语；拒绝真实平台 key、JWT、AWS key、
  非占位 Bearer token 与真实 credential 字段。
- `workflow_artifact_id`、`execution_event_id` 加入 HTTP/MCP 资源归属解析；body 中相关资源也由 service
  复核，不能只依赖 middleware。
- 产物/事件不存完整系统 prompt，只保存版本；不存 chain-of-thought；不默认保存完整原始网页。

稳定业务错误：

| HTTP | code | 语义 |
| --- | --- | --- |
| 404 | `build_session_not_found` / resource not found | 不存在或 opaque foreign 资源 |
| 409 | `session_terminal` | terminal Session 禁止继续追加 |
| 409 | `idempotency_conflict` | client ID 已用于不同请求 |
| 409 | `workflow_artifact_version_conflict` | supersedes 不是当前版本或版本链不一致 |
| 409 | `workflow_reference_conflict` | 引用不属于同 Project/Session 或类型不匹配 |
| 409 | `question_state_conflict` | question expected head stale/缺失或状态转换非法 |
| 413 | `workflow_artifact_too_large` / `modeling_workflow_export_too_large` | 确定性大小边界 |
| 422 | `secret_in_payload` / `invalid_modeling_workflow_payload` | 秘密或结构非法 |

## 8. `ontology-builder` 重构

### 8.1 Skill 结构

保持 `SKILL.md` 小于 500 行，只描述触发范围、阶段、门禁、恢复与资源导航。详细内容进入一层
references：

- `workflow-artifacts.md`：Pack、Coverage Matrix、draft、review、verification 与 Event 的模板；
- `role-handoffs.md`：三个独立角色的输入、禁止项和 record-ready 输出；
- `quality-gates.md`：七个门禁、Finding 分类、PASS/REVISE/BLOCKED 和返工规则；
- 现有 modeling、ambiguity、安全、batch format references 按 v1.0 当前工具更新并去重。

不把交付历史、README、安装指南或 Runtime 专用 Agent 文件放入 Skill。旧 Skill 的历史设计与失效
原因记录在本设计第 10 节。

### 8.2 行为门禁

- 启动时读取 Build Context、活动 Session、当前 Artifacts/Events、Modeling Context，不假设空项目。
- 全局扫描后必须先持久化 Pack 和 Matrix，再让用户确认摘要、能力问题和阻塞歧义。
- 每轮最多三个阻塞问题；已确认/跳过/未确定状态进入 Artifact/Event，恢复后不无故重复提问。
- 模型草案必须由能力问题驱动并将重要知识项映射回 Matrix/Evidence。
- dry-run 后由独立 reviewer 看原始资料清单、关键摘录和 Findings；只有 PASS 才能由主 Agent apply。
- apply 后必须用 read model、Context Query/SPARQL、validation 和 lineage 验收，不以 dry-run/apply
  成功代替业务通过。

### 8.3 Eval 与 forward test

替换旧单 Agent fixture，至少覆盖：恢复与不重复提问、全局扫描/Pack/Matrix、角色边界、门禁阻塞、
review 发现整理遗漏、idempotent event/artifact retry、apply/verification、秘密拒绝和断点恢复。静态
trace 只验证结构与工具契约；真实 Codex forward test 才验证角色隔离与输出质量。

Skill 完成后运行 `quick_validate.py`、仓库自带 structural/eval/registry checks，并用三个独立
`codex exec -m gpt-5.6-terra -c 'model_reasoning_effort="medium"'` 上下文执行首轮 Dify 工作流。

Forward test 额外启动一个临时主 Agent Codex 上下文来实际执行 Skill 的平台步骤。只通过临时 CLI
config/profile 为该主 Agent 注册 ontology-platform stdio MCP，command 指向当前仓库
`backend` 的 `uv run python -m app.mcp.server`；凭证使用专属、Project-bound `model` key，通过不打印
明文的进程环境注入。配置和凭证不写进 Skill、prompt、Artifact/Event、shell log 或 Git，运行结束
删除临时配置并撤销唯一测试 key。

业务整理、建模、reviewer 子角色不继承主 Agent 的 MCP 配置或环境，也不获得任何平台 key；主 Agent
只把必要的 versioned Artifact/Evidence/Modeling Context 输入传给 read-only 子角色。测试必须证明
子角色 `codex mcp list` 中无 ontology-platform server，且对受保护 HTTP 写路径无凭证请求得到 401；
只有主 Agent 的 Project-bound model key 能写 workflow records、获取 lease 和 apply。这样既实际
验证 Skill 的 MCP 依赖，又不靠 prompt 约束子角色写权限。

## 9. 首轮 Dify 真实运行

### 9.1 来源集合

每次运行先读取 `https://docs.dify.ai/llms.txt`，只选择与三项能力问题直接相关的当前 canonical 页面：

- Quick Start / Workflow 创建与发布；
- Workflow App API guide、Get App Parameters；
- Run Workflow、Get Workflow Run Detail、List Workflow Logs；
- Errors/Rate Limits，以及核心节点/变量说明中实际需要的页面。

资料清单记录 URL、最终 URL、标题、读取时间、权威等级、新鲜度、扫描状态和相关摘录。旧链接发生
重定向时记录 final URL；不把整页网页保存进平台。知识库、插件和其他 app 类型标记为 DEFERRED。

### 9.2 固定实验条件

- Runtime：当前本地 Codex CLI；记录精确版本。
- 三个独立角色：`gpt-5.6-terra`、reasoning `medium`、各自 prompt version。
- 临时主 Agent：同样固定 `gpt-5.6-terra` + `medium`，使用临时 ontology-platform MCP 和专属
  Project-bound model key，负责平台读写、用户提问、dry-run、lease/apply 和验收。
- 三个子角色：无 ontology-platform MCP、无平台 credential、read-only；只通过显式版本化输入交接。
- 每个角色记录开始/完成时间；CLI 能提供时记录 token 使用，费用未知时显式 `unknown`。
- 不在失败后静默换模；如需第二轮换模/提高 effort，作为新的 workflow version 和独立运行。

### 9.3 业务验收

完成后让消费 Agent 只使用平台当前语义状态、Evidence 和查询能力回答三项能力问题，再由用户评审：

- 是否正确区分 Workflow 定义、发布状态、API 调用与一次 Workflow Run；
- 是否能解释输入、节点/变量依赖、输出、状态和日志之间的关系；
- 是否能基于证据给出失败排查方向而不捏造 Dify 行为；
- 是否能指出 DEFERRED、AMBIGUOUS、UNSUPPORTED 或 MISSING 内容，不宣称全产品覆盖。

## 10. 旧 Skill 评估与替换原因

当前 `skills/ontology-builder/` 是 v1.0 平台能力陆续落地后做过工具名对齐的早期单 Agent 流程：

- `SKILL.md` 把恢复、访谈、证据、建模、apply 和验证放在同一上下文顺序执行；
- 没有 Business Knowledge Pack、Coverage Matrix、版本化角色交接或独立 reviewer；
- 依赖本地 `.ontology-build.md` 和聊天上下文保存部分业务判断；
- eval cases/traces 主要验证工具调用、stop reason、幂等恢复和安全动作，不能证明资料覆盖或业务质量；
- 平台没有 workflow artifacts/events，因此不同 Agent 无法从平台恢复业务理解、问题/回答和评审返工。

这些是已知结构性限制，不需要重新运行旧 Skill 才成立。旧文件可作为迁移材料，但新流程完成前不
视为有效基线，也不把静态 trace 成功解释为建模效果。

## 11. 迁移、文档与 rollout

- 新增 Alembic `0028_modeling_workflow_records`，仅增表/索引/FK，不回填旧聊天或本地 ledger。
- 更新 models、schemas、service、REST router、MCP tools/registry/catalog、security resolver、Modeling
  Finding fingerprint 和测试。
- `get_build_session` 增加兼容性的 `modeling_workflow_summary`（当前 Artifact 列表、Event count/last
  sequence/next step 摘要），不内联大 content；旧字段保持不变。
- 更新 `docs/reference/api.md`、`docs/reference/mcp.md`、`docs/architecture/overview.md`、`docs/guides/platform-guide.md`、glossary 和需求
  状态；API/MCP inventory 继续由 registry 同步测试约束。
- 后端全量测试与真实 PostgreSQL concurrency 通过后重启 `ontology-platform.service`，验证 migration
  head、health、受保护 REST、MCP registry、JSON/Markdown export，再运行 Dify 场景。
- 前端无功能改动，不新增 frontend build/playwright 门槛；若实现过程中实际修改 frontend，则按
  `AGENTS.md` 补跑 build、Playwright、重启和浏览器验收。

## 12. 风险探针结论

1. **Session 内并发序号：通过。** 真实 PostgreSQL 双连接复用 Session row lock，得到唯一 `[1, 2]`
   序号；临时 Project 已清理。设计复用该事务模式。
2. **秘密扫描与授权命名：可复用但需新命名。** 现有 scanner/测试通过；`artifact_id` 已属于 Evidence
   Artifact，因此新资源固定为 `workflow_artifact_id` / `execution_event_id`。
3. **官方 Dify source URL 会迁移。** `llms.txt` 可用且提供当前 canonical 页面；旧 Workflow URL 会
   重定向。真实运行必须从索引发现并记录 final URL。

## 13. Plan review

### Round 1 — 2026-07-17 — REVISE

- `accepted-high`：当前 Codex 只有 agentmemory MCP；原计划未定义临时 ontology-platform MCP 与主/
  子角色 credential 隔离，Skill 不能真实执行且共享 model key 会让子角色具备 lease/apply 权限。
  修订为临时主 Agent MCP + Project-bound model key，子角色无 MCP/credential，并增加 401/registry
  denial test 与测试 key 撤销。
- `accepted-high`：Event 只有通用 status，不能恢复 question 的 answered/skipped/open 等状态。增加
  question ID、五态状态机、事件链、current state summary/export 和不重复提问测试。
- `accepted-high`：Attempt + Finding code/path 在多个 item 同类错误时不唯一。为 Attempt Findings
  增加包含 ordinal/item IDs/details 的持久稳定 fingerprint，Event 精确引用并覆盖重复 code/path 测试。

修订后的设计与共享测试计划必须由同一 reviewer Round 2 PASS 后才能开发。

### Round 2 — 2026-07-17 — REVISE

- `accepted-high`：Round 1 只要求 answer 引用任意较早同 question event，两个并发 Agent 可从同一
  open head 分叉，后写 sequence 会静默成为当前答案。修订为 Session row lock 下的 per-question
  linear head CAS：每次转换精确声明 expected current head，stale/并发返回
  `question_state_conflict`，更正必须 supersede current head；增加并发回答、duplicate open、stale
  transition 和 reopen/correction 测试。

修订后的计划必须由同一 reviewer Round 3 PASS 后才能开发。

### Round 3 — 2026-07-17 — PASS

- reviewer 确认 per-question current-head CAS 和并发/stale/correction 测试关闭静默分叉；临时主
  Agent MCP/credential 隔离与 Finding fingerprint 方案仍完整。
- 无剩余 evidence-backed Critical/High finding，允许按本设计进入开发。

## 14. 验收标准

- Artifact 不可变、线性版本、幂等创建、content hash、分页查询和跨 Project 隔离正确。
- Event 幂等、并发稳定排序、追加更正、过滤/分页、结构化质量问题和资源引用归属正确。
- question 状态链可恢复且不重复提问；重复 code/path Finding 仍有唯一稳定引用。
- REST/MCP 同合同；JSON/Markdown export 能恢复完整时间线且不复制秘密或平台第二真相。
- 认证 actor 不可伪造，foreign/unknown refs fail closed，真实秘密在持久化前拒绝。
- 新 Skill 的角色、Artifact、Coverage、七门禁、恢复、eval 和 forward test 与需求一致。
- Codex Terra/medium 临时主 Agent 通过 ontology-platform MCP 执行，三个子角色无平台凭证且独立运行
  Dify 官方文档，正式写入只由主 Agent执行。
- 三项能力问题可由持久模型和证据回答，用户确认实际业务价值；限制和 deferred 范围明确。
- 独立 requirement tester PASS、全量测试、真实依赖、migration、重启健康、文档/需求同步和 commit
  全部完成。

## 15. 2026-07-18 repo-local Codex modeling Harness 增补设计

### 15.1 目的与边界

Harness 记录一次 `ontology-builder` 主 Codex session 的建模过程，供后续比较角色委派、阶段返工、
门禁缺口和可优化环节。它补充平台中稳定、跨 Agent 可恢复的 Modeling Workflow Artifact/Event，
不替代平台事实来源，也不把聊天记录变成第三套业务状态。

- Harness 只位于当前仓库 `.codex/`，不打包为 Plugin，也不随 `ontology-builder` Skill 发布。
- Skill 只在仓库脚本存在时显式激活；不存在时继续原建模流程，不能把本地观测能力变成外部依赖。
- 每个主 Codex session 一份运行记录。新 session 恢复相同 Build Session 时新建记录，并引用前序
  session，不合并原始事件或复盘文档。
- 不修改 backend/frontend、数据库或平台 API。平台 Event/Artifact/Build Session ID 只作为稳定链接。
- 当前不实施定时清理；raw 目录保持 gitignored，由使用者显式处理。

### 15.2 文件与身份模型

项目 Hook 配置为 `.codex/hooks.json`，确定性 runner 和结构化输出 Schema 位于 `.codex/hooks/`。
首次使用或 Hook 文件变化后，操作者必须在 Codex `/hooks` 审核并 trust 当前精确 hash；Skill 同时
检查脚本存在与 activation acknowledgment。未 trust 只使本地复盘降级，不阻断平台建模，但主 Agent
必须把告警展示给用户，不能声称 Harness 正在记录。

激活命令必须携带主 Agent 生成的唯一 `run_id` 和一次性随机 `activation_nonce`；
`PreToolUse(Bash)` Hook 从可信 Hook payload 取得 `session_id`，写入同时包含
`run_id/session_id/cwd/activation_nonce/hook_config_hash` 的 acknowledgment，再把 session 与 run
绑定。实际 `activate` CLI 只在 nonce、cwd、run 和 acknowledgment 全部匹配后报告 active；Hook 未
trust、被禁用、配置 hash 变化或未执行时，CLI 必须非零退出并明确报告“本 session 未记录”，不得
自行创建伪 active run。这样既避免 CLI 子进程猜测当前主 session，也避免并发窗口选择最近记录。

运行文件位于 `workspaces/ontology-harness/<run-id>/`：

- `metadata.json`：run/session/build/project、前序 run、状态与时间；
- `events.jsonl`：先落盘、追加式、带 sequence 和 event fingerprint 的白名单事件；
- `state.json`：已总结 sequence、pending/retry/finalization 状态，不把游标混入事件日志；
- `session.md`：由已验证 delta 确定性重建的实时摘要；
- `raw/`：仅在白名单允许且确有复盘价值时保存有界片段，不保存 transcript。

session 到 run 的 registry 也放在 gitignored Harness 根目录。所有状态写入使用进程锁；JSON 状态采用
同目录临时文件、`fsync` 和原子替换；JSONL 在锁内一次写完整行并 `fsync`。事件 fingerprint 由
Hook event、tool use ID/agent ID、规范化白名单 payload 计算，重复 Hook 不产生重复业务事件。

### 15.3 Hook 路由与阶段识别

配置使用当前 Codex 原生 command Hooks：`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、
`SubagentStart`、`SubagentStop` 和 `Stop`。runner 总是先验证 `cwd`、session/run 映射和输入 Schema，
未知 session 或未激活 run 直接成功退出。Hook stdout 只返回 Codex 所需 JSON，不输出诊断文本。

| 时刻 | 确定性事件 | Luna |
|---|---|---|
| activate | 创建 run 和绑定 | 不调用 |
| UserPromptSubmit | 保存有界用户可见 prompt | 不调用 |
| PreToolUse(Agent) | 委派意图、角色、输入边界、预期产物 | 调用一次 |
| SubagentStart | agent ID/type | 不调用 |
| SubagentStop | 最终回答、偏差、问题、下一步 | 调用一次 |
| 普通 Stop | `turn_output` | 不调用 |
| 有显式 checkpoint 的 Stop | 关联阶段输出 | 调用一次 |
| completed/cancelled finalize | 终态与最终增量 | 有界 flush 后调用最终总结 |

`PostToolUse` 只白名单处理 Modeling Workflow/Build Session 相关工具。成功的
`record_modeling_execution_event` 且 event type 为 `phase_completed`、`review_completed`、
`rework_requested`、`blocked`、`verification_completed` 等时写 authoritative checkpoint；下一次
同主 session 的 Stop 才能关联为阶段输出。平台不可用时，显式 `checkpoint` CLI 写
`agent_reported_local`，并保持待对账状态。自然语言、普通 Stop 和失败的平台调用不能推进 phase。

成功的 `complete_build_session`/`cancel_build_session` 触发对应 `completed`/`cancelled` finalize。
`paused`、`interrupted` 只留本地；普通 Stop 和 subagent 结束绝不发布最终文档。

### 15.4 白名单、秘密拒绝与总结输入

允许保存：用户可见 prompt、委派任务/角色/Artifact 引用、subagent 最终回答、主 Agent
`last_assistant_message`、相关 MCP 状态和稳定 ID、必要 Finding/错误、checkpoint/phase/model/耗时/
重试，以及解释返工所需的短摘录。每类字段有独立字符上限和总事件上限。

禁止保存或发送给 Luna：完整主/子 transcript、system/developer prompt、隐藏推理、credential、
cookie、lease token、完整网页/Evidence、无关文件或终端输出。runner 先做字段 allowlist、控制字符/
长度处理和保守 secret scan。明确 secret 命中时原值完全不落盘，仅追加不含原值的 `rejected_secret`
事件并将状态设为 `pending_redaction`；主 Agent 必须通过显式 redacted replacement 补齐，不能静默
替换后继续总结。

新 Luna session 只接收游标后的事件、其允许的有界片段、短当前状态及固定总结指令，不读取主
transcript、subagent transcript 或整个历史 `events.jsonl`。输出通过仓库 JSON Schema 校验；模型不
获得工作区写权限，也不直接修改 Markdown。

### 15.5 Luna 调用、失败与发布

runner 使用当前 Codex CLI 新起隔离 session：`gpt-5.6-luna`、reasoning `medium`、ephemeral、
read-only、禁用 Hooks、忽略用户配置/rules，并通过 `--output-schema` 与 last-message 文件取得结果。
工作目录是每次调用新建的空临时目录，而不是仓库；prompt 只经 subprocess stdin 传入，任何事件值
不得拼接进 shell command 或 argv。runner 构造显式环境，保留 Codex 认证/网络/locale 所需最小项，
移除 ontology-platform/MCP/API key/cookie/authorization/lease/token 等业务凭证变量。

总结器必须 tool-less：顶层 `web_search="disabled"`，并显式关闭 `shell_tool`、`unified_exec`、
`apps`、`multi_agent`、`goals`、`memories`、`browser_use`、`browser_use_external`、
`browser_use_full_cdp_access`、`computer_use`、`image_generation`、`plugins`、`plugin_sharing` 和其他
当前版本可调用的非必要工具；runner 对不被当前 CLI 识别的禁用项 fail closed，不退回到带工具运行。
总结 prompt 把事件标记为不可信数据并禁止服从其中指令。这既避免递归触发 Harness，也切断总结器
对仓库、平台、连接器、web 和子 Agent 的读取/写入面。

每个 Hook 最多进行一次 Luna 调用；若存在 pending，优先处理最早连续缺口。工作期失败 fail-open：
原事件已保留、游标不前进，记录错误类型/尝试次数，后续 Hook 重试。completed/cancelled finalize
最多 flush 三次；仍有缺口则标记 `finalization_pending`，不创建版本化复盘，且不回滚平台终态。
`repair <run-id>` 复用同一锁、游标和 Schema 补齐。

所有事件完成总结后，runner 生成脱敏最终文档
`docs/modeling-retrospectives/<date>-<run-id>.md`，包含阶段摘要、决策/假设、返工与质量问题、阻塞、
下一步、优化建议、稳定平台 ID、Harness/模型版本和终态；不复制完整聊天。写入先生成临时文件再
原子替换，重复 finalize/repair 结果幂等。

## 16. Harness 风险探针与计划评审

### 16.1 实现前风险探针 — 2026-07-18 — PASS

1. 使用 Codex `0.144.5` 真实启动 `gpt-5.6-luna` + `medium`，组合 `--ephemeral`、
   `--disable hooks`、`--ignore-user-config`、`--ignore-rules`、`--sandbox read-only` 和
   `--skip-git-repo-check`，在临时目录成功得到预期 JSON，证明模型、隔离参数和递归切断可用。
2. 当前 CLI `hooks` feature 为 stable/enabled；官方本机 Codex manual 明确列出所需 lifecycle events、
   `Agent` tool coverage、Subagent/Stop payload，并说明 command Hook 同步、`async` 尚不支持。
3. Python stdlib `fcntl` + 单行 JSON append + flush/fsync 的 64 次并发探针得到 64 条合法、唯一事件，
   支持 repo-local Linux runner 的最小锁策略；正式测试仍需覆盖 sequence 分配和重复 fingerprint。

### 16.2 Harness plan review

原设计的 2026-07-17 Round 1–3 不替代本增补审查。

#### Round 1 — 2026-07-18 — REVISE

- `accepted-high`：repo-local Hook 需要精确 hash trust，脚本存在不能证明 activation Hook 已执行。
  增加 activation nonce acknowledgment、CLI fail-closed、Skill 明确降级告警、`/hooks` trust 说明和
  真实 Codex Hook smoke。
- `accepted-high`：read-only 不会关闭 Luna 默认 shell/web/apps/subagent 工具。不可信事件存在 prompt
  injection 读取秘密的风险。增加空临时 cwd、最小环境、stdin、全部非必要工具显式关闭和真实恶意
  注入隔离 smoke。

修订后的设计和共享测试计划必须由同一 reviewer Round 2 PASS 后才能开发。

#### Round 2 — 2026-07-18 — PASS

- reviewer 确认 Hook trust、activation nonce acknowledgment、CLI fail-closed 和真实 Hook smoke 已关闭
  假激活风险。
- reviewer 确认空临时 cwd、stdin、受限环境、tool-less feature 配置和真实恶意注入 smoke 已关闭
  Luna 读取仓库/环境秘密风险。
- 无剩余 evidence-backed Critical/High finding，允许按冻结设计进入开发。
