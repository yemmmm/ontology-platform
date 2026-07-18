# R1.2-002 Project 与 Ontology 的授权发现和范围解析 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-002
- Status: in-progress
- Started: 2026-07-18T17:54:16+08:00
- Last updated: 2026-07-18T22:08:51+08:00
- Design: deferred by refinement-only scope
- Shared test plan: deferred by refinement-only scope
- Delivery baseline: worktree at `628296f Record reliable modeling artifact handoff requirement`;
  pre-existing user changes in `AGENTS.md`, `CLAUDE.md`,
  `docs/requirements/requirements-v1.2.md`, and the R1.2-001 delivery record are excluded
- Delivery commit: refinement documentation commit `Refine v1.2 consumer query requirements`;
  use `git log -- <this-record-path>` for the immutable hash

## Confirmed contract

- Current behavior: authenticated REST already exposes `GET /api/projects` and
  `GET /api/projects/{project_id}/ontologies`. A Project-bound principal sees only its Project and
  foreign resources fail closed; an organization admin can list all Projects. These CRUD-shaped
  responses do not provide name-resolution outcomes, queryability, current semantic version, or
  unavailable reasons, and no equivalent Project/Ontology discovery MCP tools exist. R-006 scope
  resolution still requires a caller-supplied `project_id`, `scope_mode`, and Ontology IDs when using
  Ontology scope.
- Target behavior: an authenticated consumption Agent can discover only authorized Project/Ontology
  metadata, resolve names or stable IDs into explicit candidates, understand whether each candidate
  can be queried and at which current semantic version, and directly construct R-006 Context Query
  or scoped SPARQL parameters without reading internal Graph Set identifiers.
- In scope: authorized Project/Ontology listing, name and stable-ID resolution, candidate
  disambiguation, queryability and current-version reporting, unavailable-reason reporting, REST/MCP
  parity, and fail-closed ownership filtering.
- Non-goals: semantic queries without an explicit or configured scope; Dataset-wide semantic scans;
  Graph Set exposure; historical or immutable-version selection; organization/user administration;
  fuzzy or multilingual semantic resource recall owned by R1.2-003; final natural-language answers.
- Acceptance summary: a name-only Agent can obtain usable scope IDs through public REST/MCP; only
  authorized candidates are visible; duplicate names, unavailable/current-state cases, forbidden
  resources, and absent resources remain distinguishable; returned scope can be passed directly to
  R-006 query APIs.
- Refinement: collaborative refinement started; consequential discovery and failure semantics remain
  to be confirmed one decision at a time. The current confirmed direction is a dedicated
  authorized-scope discovery capability shared by REST and MCP. A consumption Agent calls this
  capability as the first scope-establishment step, receives accessible Projects and their Ontology
  metadata, then explicitly selects scope for the existing Context Query or scoped SPARQL path. It
  is not an optional filter added to the semantic query interface. This first-step rule belongs to
  the external Agent/Skill consumption protocol; the server remains stateless and does not require
  proof of a prior discovery call when a client already supplies a valid explicit scope. Discovery
  covers the complete authorized logical collection through stable cursor pagination; the first-step
  protocol continues until `has_more=false`, and includes unavailable Ontologies with explicit
  `queryable=false` reasons. Discovery never exposes unauthorized candidates or their counts;
  explicit authorization failures preserve R-008's anti-enumeration semantics rather than promising
  that every foreign Ontology can be distinguished from a nonexistent one. Project queryability is
  `complete`, `partial`, or `unavailable`: partial Project scope remains queryable over ready
  Ontologies with explicit exclusions, while an explicitly selected unavailable Ontology fails with
  `scope_not_ready`. Each Ontology exposes its existing `workspace_version`; Project discovery does
  not invent a separate aggregate `scope_version`. The dedicated discovery capability may accept
  its own optional metadata `query` and `queryable` filters; these never become semantic Context
  Query inputs or search RDF content. This delivery is refinement-only: requirement and delivery
  record synchronization are in scope, while design, test-plan, implementation, and agent handoffs
  are explicitly deferred. Discovery is limited to consumption scope identity and readiness; it does
  not include Build Sessions, modeling progress, batches, blockers, or other Build Context content.
  Ontology business `status` and technical `queryable` are separate: ready `draft` and `active`
  Ontologies are queryable, while `archived` Ontologies remain discoverable but are not queryable.
  The optional metadata `query` performs deterministic lexical matching only: exact stable ID or
  trimmed, case-insensitive name containment. It does not search descriptions or provide fuzzy,
  multilingual, synonym, or vector matching. Without `query`, all authorized Project/Ontology
  metadata is returned through pagination. A Project match expands its authorized Ontologies; an
  Ontology-only match returns the parent Project context with only matched Ontology candidates.
  Missing, stale, or unmaterialized reasoning/rule results produce warnings but do not make an
  otherwise ready Ontology unqueryable. Cursor pages read current catalog state and carry
  `generated_at`; no catalog snapshot or revision is introduced, and final semantic queries
  revalidate authorization, readiness, and Ontology versions.

## Timeline

### 2026-07-18T17:54:16+08:00 — source and current-state audit — main agent

- Context: 用户指定 `requirement-delivery`，要求细化 v1.2 R1.2-002；R1.2-001 细化产生的
  未提交文档修改仍在工作树中，必须保持独立。
- Action/decision: 读取 R1.2-002、R1.2-001 已确认合同、v1.0 R-008 授权合同、术语表和真实
  REST/MCP/授权/语义范围路径。确认现有 REST 列表已经执行 Project 隔离，但它是 CRUD 读模型，
  不能完整满足消费 Agent 的范围发现合同；MCP 没有 Project/Ontology 发现工具。
- Evidence: `docs/requirements/requirements-v1.2.md`; v1.0 R-008 in
  `docs/requirements/requirements-v1.0.md`; `backend/app/api/ontologies.py`;
  `backend/app/api/schemas.py`; `backend/app/security/http.py`;
  `backend/app/services/ontology_crud.py`; `backend/app/services/semantic_query_scope.py`;
  `backend/tests/test_authorization.py`; GitNexus `query`, `context`, `route_map`, and `tool_map`.
- Outcome/next step: 先确认授权元数据发现是否允许在未指定 Project 时跨“当前身份可访问范围”
  搜索 Ontology 候选；确认前不编写产品设计或代码。

### 2026-07-18T17:54:16+08:00 — tooling limitation — main agent

- Context: GitNexus context resource reported that the code index was one commit behind HEAD.
- Action/decision: attempted the repository-prescribed incremental analyze; it failed in GitNexus's
  local FTS index before code analysis. Continued with the previous index because the missing commit
  is documentation-only, and cross-checked all relevant implementation details in source files.
- Evidence: `node .gitnexus/run.cjs analyze` failed with `FTS index 'file_fts' is inconsistent`;
  current HEAD `628296f`; indexed commit `6842b7e`.
- Outcome/next step: the source audit is sufficient for refinement; index cleanup/rebuild is outside
  this requirement and will not be performed without separate scope.

### 2026-07-18T19:10:20+08:00 — functional refinement proposal 1 — user and main agent

- Context: 需要确定名称解析是复用现有 Project/Ontology CRUD 列表，还是提供面向消费 Agent 的
  独立授权范围发现合同。
- Action/decision: 用户提出新增一个可选 `query` 的 Project 情况查询接口；未传 `query` 时返回
  当前身份有权访问的全部 Project 及其 Ontology 元数据，传入时在同一授权元数据集合中筛选。
  主 Agent 推荐接受该方向，并让 REST/MCP 复用一个服务合同，不把语义 Dataset 搜索混入发现。
- Evidence: 当前会话；现有 `GET /api/projects` 与
  `GET /api/projects/{project_id}/ontologies` 仅提供分离的 CRUD 列表。
- Outcome/next step: 确认“返回全部”的容量语义是单次无界响应，还是逻辑全集加稳定分页；随后再
  收敛 `query` 的匹配字段与精确度。

### 2026-07-18T19:15:58+08:00 — functional refinement decision 1 — user and main agent

- Context: 前一轮把可选 `query` 参数与授权范围发现能力放在同一接口的提议，仍可能让“查业务
  知识”和“先了解可用范围”混为一个调用。
- Action/decision: 用户确认应新增独立的 Project/Ontology 授权范围发现接口。消费 Agent 在首轮
  查询时固定先执行范围发现，取得有权访问的 Project 和 Ontology 信息；现有 Context Query/
  scoped SPARQL 不承担这一步，也不通过同一个 `query` 参数兼做范围发现。此决定取代上一轮尚未
  确认的可选 `query` 筛选方案。
- Evidence: 当前会话用户说明。
- Outcome/next step: 确认“首轮固定调用”是外部 Agent/Skill 的消费协议，还是服务端对每次语义
  查询强制校验先前调用记录。

### 2026-07-18T19:25:12+08:00 — functional refinement decision 2 — user and main agent

- Context: 需要决定首轮发现流程是否引入服务端调用顺序状态，以及已有明确范围的集成是否仍可
  直接查询。
- Action/decision: 用户确认首轮固定调用由外部消费 Agent/Skill 的协议保证。服务端不记录或校验
  “已先调用发现接口”的状态；持有明确 Project/Ontology ID 的客户端可以直接调用现有查询接口，
  服务端仍在每次请求上重新验证身份、授权、归属和范围有效性。
- Evidence: 当前会话用户确认。
- Outcome/next step: 确认授权范围清单的容量和续读合同，避免组织管理员拥有大量 Project 时首轮
  响应无界增长。

### 2026-07-18T19:27:38+08:00 — functional refinement decision 3 — user and main agent

- Context: 授权组织管理员可能拥有大量 Project/Ontology；单次无界返回与 R1.2 紧凑响应和稳定
  续读目标冲突。
- Action/decision: 用户确认发现结果使用稳定游标分页。逻辑集合包含当前身份有权访问的全部
  Project/Ontology；外部 Agent/Skill 的首轮发现流程继续读取到 `has_more=false`。未就绪的
  Ontology 不被过滤，返回 `queryable=false` 和明确不可用原因。
- Evidence: 当前会话用户确认；`docs/requirements/requirements-v1.2.md` R1.2-001、R1.2-007。
- Outcome/next step: 收敛无权资源、不存在资源与防枚举要求之间的失败语义。

### 2026-07-18T19:28:59+08:00 — functional refinement decision 4 — user and main agent

- Context: R1.2-002 原文要求无权访问与不存在分别明确，但对外确认任意 Ontology 是否存在会破坏
  v1.0 R-008 已确认的资源防枚举边界。
- Action/decision: 用户确认以防枚举为优先。发现清单不返回无权资源、遮蔽占位符或相关数量；
  未认证保持 `401 invalid_authentication`，显式外部 Project 越权保持 `403 forbidden_scope`，
  不能安全暴露归属的 Ontology 与不存在 Ontology 对外统一为 `404 scope_not_found`。授权集合内的
  未就绪、归档、删除/不存在和版本变化仍可按安全上下文明确表达。需求验收不再要求区分无权
  Ontology 与不存在 Ontology。
- Evidence: 当前会话用户确认；`docs/requirements/requirements-v1.0.md` R-008；
  `backend/app/security/http.py`; `backend/tests/test_authorization.py`.
- Outcome/next step: 确认 Project 中仅部分 Ontology 可查询时，Project 聚合状态和后续查询行为。

### 2026-07-18T20:36:28+08:00 — functional refinement decision 5 — user and main agent

- Context: 一个 Project 可能同时包含已就绪和未就绪 Ontology，需要避免把部分不可用误报为整个
  Project 不可查询，也不能在明确 Ontology 查询中静默跳过目标。
- Action/decision: 用户确认 Project 聚合状态为 `complete`、`partial`、`unavailable`。
  `complete` 表示全部 Ontology 可查询；`partial` 表示至少一个可查询，并列出被排除 Ontology
  及原因，Project 范围查询仅覆盖就绪集合；`unavailable` 表示没有可查询 Ontology。显式选择
  未就绪 Ontology 时返回 `scope_not_ready`，不降级为其他范围。
- Evidence: 当前会话用户确认；现有 `SemanticQueryScopeResolver.resolve()` 的 Project/明确
  Ontology 分支语义。
- Outcome/next step: 确认 Project 范围是否需要一个随成员、可用性或 Ontology 版本变化而改变的
  聚合语义版本标识。

### 2026-07-18T21:41:10+08:00 — functional refinement decision 6 — user and main agent

- Context: 可以为多 Ontology Project 计算聚合 `scope_version`，但这会新增一个没有现存领域对象
  对应的版本概念和跨接口校验成本。
- Action/decision: 用户明确拒绝 Project 级聚合版本，认为没有必要且会增加复杂度。发现接口仅返回
  每个 Ontology 已有的 `workspace_version`；后续查询重新解析当前范围并返回实际使用的 Ontology
  版本。Project 本身只表达聚合可查询状态，不伪造单一语义版本。
- Evidence: 当前会话用户决定。
- Outcome/next step: 确认独立发现接口是否保留自身的筛选参数，还是首版始终分页返回完整授权目录并
  由 Agent 在目录中匹配名称/ID。

### 2026-07-18T21:47:10+08:00 — functional refinement decision 7 and delivery scope — user and main agent

- Context: 需要消除“独立发现接口不能叫 query”与“不能把发现混入 Context Query”之间的歧义，
  并明确本轮是否进入交付技能的后续设计和实现阶段。
- Action/decision: 用户确认独立发现接口可保留自身的可选元数据 `query`，匹配 Project/Ontology
  名称和稳定 ID，并可按 `queryable` 状态过滤；首轮仍可无筛选分页读取完整授权目录。该参数不
  进入语义 Context Query，也不搜索 RDF Dataset。用户同时明确本次只做需求细化，不实际开发；
  因此本轮只同步需求合同和交付记录，不创建设计/测试计划，不运行评审、开发或测试代理，不修改
  产品代码。
- Evidence: 当前会话用户确认与补充范围。
- Outcome/next step: 继续确认“Project 情况”是否只包含消费查询范围与就绪性，还是还要混入建模
  Build Session、进度和未决事项。

### 2026-07-18T21:49:36+08:00 — functional refinement decision 8 — user and main agent

- Context: “Project 情况”可能被理解为完整 Build Context，导致首轮消费发现混入建模过程状态并
  放大响应。
- Action/decision: 用户确认发现接口只包含消费查询所需的 Project/Ontology 标识、描述、业务状态、
  查询就绪性、Ontology 版本、不可用原因及可直接构造的公开查询范围参数。Build Session、建模
  批次、进度、阻塞项和未决事项继续由 Build Context 接口负责。
- Evidence: 当前会话用户确认；`docs/reference/glossary.md` 中 Build Context 与 Structured
  Semantic Context 的职责边界。
- Outcome/next step: 确认 Ontology 的 `draft`、`active`、`archived` 业务状态与 `queryable` 技术
  状态之间的关系。

### 2026-07-18T21:52:55+08:00 — functional refinement decision 9 — user and main agent

- Context: Ontology 的业务生命周期状态不能替代查询工作空间的技术就绪判断；同时 v1.2 查询当前
  语义状态，首版不能因尚未具备不可变发布版本而让默认 `draft` Ontology 全部不可消费。
- Action/decision: 用户确认 `draft`、`active` 在工作空间完整时均可查询；`archived` 仍出现在授权
  发现结果，但返回 `queryable=false`、原因 `ontology_archived`，并从 Project 范围查询中排除。
  任意业务状态下工作空间缺失或损坏均为 `queryable=false`、原因 `workspace_not_ready`。响应分别
  返回 `status` 与 `queryable`，调用方不需要自行推断。
- Evidence: 当前会话用户确认；`OntologyStatus` 当前枚举；R1.2 查询当前语义状态的已确认边界。
- Outcome/next step: 确认独立发现接口的元数据 `query` 是确定性词面匹配，还是承担模糊/多语言
  语义召回。

### 2026-07-18T21:54:14+08:00 — functional refinement decision 10 — user and main agent

- Context: 范围目录筛选必须保持确定性，并与 R1.2-003 的本体内部多语言/语义候选召回分离。
- Action/decision: 用户确认稳定 ID 使用精确匹配；Project/Ontology 名称使用去除首尾空白、忽略
  大小写的包含匹配。首版不搜索描述，不做拼写纠正、翻译、同义词、向量或模糊匹配。Project 与
  Ontology 同时命中时均保留，返回资源类型和 `matched_on`；重名候选不自动选中。
- Evidence: 当前会话用户确认；R1.2-003 的能力边界。
- Outcome/next step: 确认筛选命中父 Project 或子 Ontology 时，返回的关联目录范围。

### 2026-07-18T21:57:10+08:00 — functional refinement decision 11 — user and main agent

- Context: 元数据筛选命中父 Project 或子 Ontology 时，需要在“足够建立范围”和“避免无关目录
  展开”之间确定一致规则。
- Action/decision: 用户确认无 `query` 时分页返回完整授权目录；命中 Project 时返回该 Project
  及其全部授权 Ontology；只命中 Ontology 时返回必要的父 Project 元数据和命中的 Ontology
  候选。`queryable` 过滤作用于 Ontology，过滤后无子项的 Project 不保留；显式筛选不可查询项时
  返回不可用原因。无匹配是成功空集合，不是接口错误。
- Evidence: 当前会话用户确认。
- Outcome/next step: 盘点剩余功能不确定性；优先确认派生结果过期/缺失是否影响整个 Ontology 的
  `queryable` 判断。

### 2026-07-18T21:58:45+08:00 — functional refinement decision 12 — user and main agent

- Context: 当前语义工作空间可能可读，但 Reasoning/Rule 结果可能缺失、过期或尚未物化；若把二者
  等同，会阻断仍可准确读取的权威断言事实。
- Action/decision: 用户确认只要默认语义工作空间完整，`draft`/`active` Ontology 即保持
  `queryable=true`。派生结果缺失、过期或未物化只返回简要警告（例如
  `derived_results_stale`），不在发现接口展开推理详情；后续查询和 R1.2-006 负责准确解释派生
  状态。只有权威工作空间缺失/损坏或 Ontology 已归档才令 `queryable=false`。
- Evidence: 当前会话用户确认；R1.2-006 职责边界；现有语义读取允许携带派生状态警告。
- Outcome/next step: 确认分页读取期间目录变化是否需要快照一致性。

### 2026-07-18T22:06:24+08:00 — functional refinement decision 13 — user and main agent

- Context: 稳定分页可以通过目录快照提供跨页强一致性，但这需要新 revision、快照生命周期或
  聚合令牌，与用户已拒绝的复杂度方向相悖。
- Action/decision: 用户确认首版不建立目录快照或目录 revision。游标使用稳定排序，页面返回
  `generated_at`；每页读取调用时的当前授权目录，分页期间发生增删改时不承诺同一时刻快照。
  Agent 选定范围后的实际语义查询重新校验授权、工作空间状态和 Ontology `workspace_version`；
  范围失效时返回当前错误并重新执行发现。
- Evidence: 当前会话用户确认。
- Outcome/next step: 所有重要功能项已收敛；同步权威需求条目并结束本轮 refinement-only 工作。

### 2026-07-18T22:06:24+08:00 — refinement contract synchronized — main agent

- Context: 用户明确本次只做需求细化，不进入设计或开发。
- Action/decision: 将 13 项已确认决定整合进 `docs/requirements/requirements-v1.2.md`
  R1.2-002，补齐需求定位、首轮消费协议、独立发现能力、就绪性、筛选/候选、分页、授权失败关闭、
  非目标和确定性验收标准。需求实现状态保持 `未实现`，本交付记录保持 `in-progress`，供未来设计
  与实现继续追加。
- Evidence: `docs/requirements/requirements-v1.2.md` R1.2-002；本记录前述时间线。
- Outcome/next step: 本轮需求细化完成；设计、共享测试计划、计划评审、开发、独立测试、运行时
  验证和提交关闭均按用户范围延期。

### 2026-07-18T22:07:57+08:00 — refinement documentation verification — main agent

- Context: 本轮只修改需求文档和新增交付记录，且工作树中已有 R1.2-001 与仓库指南的用户修改。
- Action/decision: 检查 Markdown diff、空白错误和工作树范围；未运行产品测试或重启服务，因为
  没有修改 backend/frontend、依赖、迁移或运行配置。未提交，避免把现有 R1.2-001/指南修改与
  R1.2-002 细化错误捆绑。
- Evidence: `git diff --check` PASS；`git diff --stat`；`git status --short`；
  `git diff -- docs/requirements/requirements-v1.2.md`。
- Outcome/next step: refinement-only 轮次完成，未来从本记录继续设计与实现。

### 2026-07-18T22:08:51+08:00 — refinement commit authorization — user and main agent

- Context: 前一事件因工作树含已有 R1.2-001/指南修改而延期提交；用户随后明确要求将当前所有
  变更推送到远端。
- Action/decision: 用户授权把当前全部文档变更作为一个提交，并将当前分支连同既有领先提交一起
  推送到其已配置上游。GitNexus `detect_changes(scope=all)` 报告 4 个已跟踪文档文件、0 个代码
  symbol、0 个受影响流程、LOW risk；新增 R1.2-002 交付记录由 Git 尚未跟踪，因此不计入其 symbol
  数量，但已人工核对。
- Evidence: 当前会话用户指令；`git status --short`; `git branch -vv`; `git remote -v`;
  GitNexus `detect_changes`.
- Outcome/next step: 以 `Refine v1.2 consumer query requirements` 提交当前全部变更并推送
  `agent-semantic-layer-platform`。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |

## Final verification

- Required checks: `git diff --check` PASS; requirement diff manually inspected
- Runtime/restart health: not run; no product/runtime files changed in this refinement-only round
- Documentation/status sync: R1.2-002 contract synchronized; implementation status remains `未实现`
- Cleanup: not applicable; no runtime test data created
- Residual risks and follow-ups: design, implementation, test planning, runtime verification, and
  product-delivery closure remain deferred; refinement documentation commit/push is authorized

## Retrospective

- Scope or design deviations: refinement replaced the initial broad name-resolution paragraph with
  a dedicated first-step catalog discovery contract; no product design was created
- Rework and root causes: the original wording conflicted with R-008 anti-enumeration and did not
  separate business status, workspace readiness, and derived-result freshness
- What shortened or delayed delivery: one-question-at-a-time decisions prevented API design details
  from being mistaken for confirmed product behavior
- Reusable lessons: scope discovery should remain distinct from semantic retrieval and Build Context
