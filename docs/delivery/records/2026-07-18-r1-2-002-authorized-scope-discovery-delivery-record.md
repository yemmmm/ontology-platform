# R1.2-002 Project 与 Ontology 的授权发现和范围解析 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-002
- Status: delivered
- Started: 2026-07-18T17:54:16+08:00
- Last updated: 2026-07-19T12:04:49+08:00
- Design: `docs/delivery/designs/2026-07-19-r1-2-002-authorized-scope-discovery-design.md`
- Shared test plan: `docs/delivery/test-plans/2026-07-19-r1-2-002-authorized-scope-discovery-test-plan.md`
- Delivery baseline: worktree at `628296f Record reliable modeling artifact handoff requirement`;
  pre-existing user changes in `AGENTS.md`, `CLAUDE.md`,
  `docs/requirements/requirements-v1.2.md`, and the R1.2-001 delivery record are excluded
- Delivery commit: implementation commit subject `Deliver authorized semantic scope discovery`;
  use `git log -- <this-record-path>` for the immutable hash. Earlier refinement commit:
  `Refine v1.2 consumer query requirements`.

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

- Refinement correction (2026-07-19): the earlier sentence saying consequential decisions remained
  open became stale later in the same refinement session. The 13 decisions recorded below and
  synchronized into the requirement are the confirmed contract. The user has now requested
  implementation, so the earlier refinement-only delivery boundary no longer applies.

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

### 2026-07-19T11:08:27+08:00 — implementation resumption and source audit — main agent

- Context: 用户在 refinement commit `527966a Refine v1.2 consumer query requirements` 后指定
  `requirement-delivery`，要求开始实施 R1.2-002。
- Action/decision: 继续使用本记录，不重复建立交付历史；确认 13 项用户决定已进入权威需求，
  refinement 已完整结束。重新读取 R1.2-002、R1.2-001、v1.0 R-008、术语表、现有 REST/MCP
  授权和语义范围路径；当前工作树在开始本轮前 clean。
- Evidence: `git status --porcelain=v1`; `git log -5`; GitNexus 索引刷新至 `527966a`；GitNexus
  `query/context`; 上述源码与需求路径。
- Outcome/next step: 当前行为仍只有分离 CRUD 列表，MCP 无发现工具；进入风险探针和设计。

### 2026-07-19T11:08:27+08:00 — risk probes — main agent

- Context: 设计最可能因工作空间就绪、派生告警或目录容量语义而返工。
- Action/decision: 探针 1 直接核对 `OntologyWorkspaceService.context()`，确认能以
  `ready/incomplete` 和 issues 判断权威工作空间；探针 2 核对 `SemanticReadScopeResolver`，确认
  missing/stale reasoning/rule 已有公开告警来源；探针 3 只读查询真实 PostgreSQL 目录规模，并以
  极端单 Project 多 Ontology 情形审查分页边界。
- Evidence: `backend/app/services/ontology_workspace.py`;
  `backend/app/services/semantic_read_scope.py`; `backend/app/services/modeling_workspace.py`；
  `cd backend && uv run python ...` 返回 2 Projects、2 Ontologies、单 Project 最大 1 Ontology。
- Outcome/next step: 复用现有就绪/版本/派生状态原语；不能因当前数据小而使用无界嵌套响应，设计
  采用 Project/Ontology 分别计数的有界 keyset 候选流。

### 2026-07-19T11:08:27+08:00 — design and shared test plan freeze candidate — main agent

- Context: 已确认合同和风险探针足以形成评审候选。
- Action/decision: 写入功能设计与唯一共享测试计划。设计新增独立 REST/MCP 发现入口、扁平有界
  候选流、授权优先过滤、共享就绪评估，并明确 archived/unavailable 的实际查询失败语义；不新增
  前端页面和数据库迁移。
- Evidence: `docs/delivery/designs/2026-07-19-r1-2-002-authorized-scope-discovery-design.md`;
  `docs/delivery/test-plans/2026-07-19-r1-2-002-authorized-scope-discovery-test-plan.md`。
- Outcome/next step: 进入强制 plan_reviewer 门禁；评审前不修改产品代码。

### 2026-07-19T11:08:27+08:00 — pre-edit impact analysis — main agent

- Context: 仓库要求修改任何既有符号前先执行 upstream impact；本轮尚未修改产品代码。
- Action/decision: 对 `SemanticQueryScopeResolver.resolve`、`_resolve_ontology`、
  `register_semantic` 和 `MCP_TOOL_POLICIES` 执行 GitNexus impact。全部为 LOW；前两者影响现有
  partial/explicit scope 测试，MCP 注册影响统一 registry 及 surface/auth/catalog 测试，无
  HIGH/CRITICAL 风险。
- Evidence: GitNexus `impact` on exact symbol UIDs；GitNexus process catalog 未报告相关执行流。
- Outcome/next step: 开发交接必须覆盖上述直接和间接回归面；无需因 blast radius 阻断评审。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| 1 | PASS；无 evidence-backed Critical/High finding | accepted-pass | R-008 auth model、HTTP read policy、MCP GLOBAL_SAFE/revalidation、workspace/version/derived primitives、scope resolver 与共享测试矩阵 | 无修订；冻结设计和测试计划 |

### 2026-07-19T11:15:51+08:00 — mandatory plan review Round 1 — plan reviewer and main agent

- Context: 评审候选设计和共享计划已完成，产品代码尚未修改。
- Action/decision: `plan_reviewer` 独立核对需求、R-008、授权代码、MCP runtime、就绪/版本/派生
  原语、scope resolver 和测试覆盖，结论 PASS，无 Critical/High finding。主 Agent 接受 PASS，无
  finding 需要接受、降级、拒绝或重新评审。
- Evidence: reviewer cited `backend/app/security/auth.py`, `backend/app/security/http.py`,
  `backend/app/mcp/runtime.py`, `backend/app/services/ontology_workspace.py`,
  `backend/app/services/modeling_workspace.py`, `backend/app/services/semantic_read_scope.py`,
  `backend/app/services/semantic_query_scope.py` and reviewed design/test plan.
- Outcome/next step: 设计和共享测试计划标记 reviewed；以 HEAD `527966a` 加本需求三份文档作为
  固定开发基线，进入 requirement_developer。

### 2026-07-19T11:15:51+08:00 — development handoff freeze — main agent

- Context: plan review PASS，预编辑 impact 全为 LOW。
- Action/decision: 固定需求、reviewed design、shared test plan、本记录路径和完整必测命令，要求
  developer 覆盖 service、REST、MCP、scope resolver、测试和公开文档，不提交、不编辑本记录。
- Evidence: HEAD `527966a457667a2c5ddaa0fbcdef1a6c585dbcc1`；工作树仅含本需求设计、
  计划、记录，以及交接前新出现且明确排除的未跟踪
  `docs/delivery/records/2026-07-19-r1-1-003-reliable-modeling-artifact-handoff-delivery-record.md`。
- Outcome/next step: 等待显式 development-ready；期间不启动独立测试。

### 2026-07-19T11:33:55+08:00 — development-ready and stable diff audit — developer and main agent

- Context: developer 已停止全部写入并返回 `DEVELOPMENT_READY`；主 Agent 随后审查稳定 diff 和
  新增文件，不与开发并发测试。
- Action/decision: 实现覆盖共享 discovery/readiness service、REST、MCP principal/policy、
  SemanticQueryScopeResolver archived/unavailable 行为、schemas、专项回归与 API/MCP/platform/
  architecture/requirements 待验收文档。无 migration、无前端页面。主 Agent 确认真实 diff 未改
  GitNexus 误报的 Context/SPARQL schema 或 MCP `_closure_values`/`visit` 逻辑。
- Evidence: 专项 `78 passed`；backend `726 passed, 6 skipped`；frontend build PASS（既有 chunk
  warning）；Playwright `37 passed`；Ruff/format、docs sync、`git diff --check` PASS；systemd active；
  backend/frontend HTTP 200；组织管理员与 Project key REST、Project key FastMCP 均通过；临时
  API keys 3/3 清理。稳定 tracked diff SHA-256
  `f82205aca2d3bfa18c296cd8ad28e7685392f268b2e829a4165839ff5a511bda`，新增 service/test/design/
  plan 各自 SHA-256 已在当前交接命令输出保存。
- Outcome/next step: 一次辅助脚本 detached SQLAlchemy object 失败已确认不是产品 defect，改用纯
  Project ID 重跑通过；进入独立测试。

### 2026-07-19T11:33:55+08:00 — GitNexus HIGH disposition and independent-test freeze — main agent

- Context: `detect_changes(unstaged)` 报 HIGH、107 symbols、7 processes；规则要求不得忽略。
- Action/decision: 主 Agent 逐文件比对后判定为工具 hunk/行位移误归因，而非真实 HIGH blast
  radius。7 条流程全部只因 `_closure_values`/`visit` 被标记 touched；实际 `runtime.py` diff 仅新增
  policy 项和独立 `runtime_principal()`，上述函数内容未变。`schemas.py` 和 `semantic.py` 的既有
  Context/SPARQL 定义也只是被新定义前插导致行位移。保留 HIGH 原报告和本证据化降级，不删除
  告警；新增未跟踪 service/test 不在该工具统计内，交给 tester 独立代码审查。
- Evidence: GitNexus affected processes `proc_37`, `proc_141`, `proc_181`, `proc_182`, `proc_195`,
  `proc_196`, `proc_204` 均锚定未改的 `_closure_values`/`visit`；`git diff` 逐 hunk 审查；backend
  全量与 MCP auth/surface/runtime 回归通过。
- Outcome/next step: 风险降级为 LOW/MEDIUM 的新功能与 scope 行为回归面，可进入
  `requirement_tester`；固定 HEAD `527966a` 加当前 worktree，明确排除无关 R1.1-003 记录。

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| 1 | HEAD `527966a` + tracked diff `f82205ac...` + hashed new files | 实现完整 R1.2-002；辅助验收脚本 detached-object 非产品失败 | 78 focused；726 passed/6 skipped；build PASS；37 Playwright；runtime REST/MCP PASS | DEVELOPMENT_READY；交独立 Round 1 |
| 2 | HEAD `527966a` + repaired worktree | 修复 Round 1 D1/D2：cursor 身份边界与默认完整性材料 | 81 focused；729 passed/6 skipped；build PASS；37 Playwright；runtime boundary PASS | DEVELOPMENT_READY；交独立 Round 2 |

### 2026-07-19T11:51:55+08:00 — repair Cycle 2 development-ready — developer and main agent

- Context: developer 接受 Round 1 D1/D2 并停止全部写入。
- Action/decision: cursor filter fingerprint 绑定 `authorized_project_id`（含 org-admin `None`
  sentinel）；配置 `SECRET_KEY` 时稳定派生 integrity key，未配置时使用进程私有随机材料并明确
  cursor 不跨重启/进程。新增同主体续读、跨授权边界拒绝、filter binding、默认配置和 REST/MCP
  parity 回归。变更限于新增 service/test 与相关 API/MCP/design 文档。
- Evidence: focused `81 passed`; backend `729 passed, 6 skipped`; frontend build PASS（既有
  chunk warning）；Playwright `37 passed`; Ruff/docs sync/diff check PASS；systemd active；health 和
  frontend HTTP 200；真实 PostgreSQL 同 Project 续读 200、跨 Project 和 Project-to-org 均
  `400 invalid_cursor`；3 keys、2 Projects/Ontologies 已清理。
- Outcome/next step: 第一次 runtime setup 的未提交 Project FK 失败已完整回滚，修正数据准备顺序
  后通过，非产品 defect。主 Agent 审查窄修和新增回归后冻结 Round 2 基线。

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| 1 | HEAD `527966a` + development-ready worktree | FAIL | D1 High cross-authorized-catalog continuation reuse can omit valid candidates；D2 High default integrity key is predictable；full/runtime stopped after blocker | shared test plan Round 1；independent service verification；25 focused passed |
| 2 | HEAD `527966a` + Cycle 2 repaired worktree | PASS | 无；未执行用例 0 | shared test plan Round 2；28 focused；729 passed/6 skipped；37 Playwright；真实 REST/MCP/Context/SPARQL；cleanup 0 residue |

### 2026-07-19T12:00:30+08:00 — independent Round 2 PASS — tester and main agent

- Context: developer 已停止 Cycle 2 写入；tester 先复测 Round 1 D1/D2，再完成此前未执行门禁。
- Action/decision: Round 2 `PASS`。D1/D2 和同主体正常分页独立通过；无新 defect、无未执行用例。
  主 Agent 接受 PASS，允许进入需求状态、设计结果、文档和最终门禁同步。
- Evidence: focused `28 passed`; backend `729 passed, 6 skipped`; frontend build PASS；Playwright
  `37 passed`; systemd active；backend/frontend HTTP healthy；真实组织/Project 发现、外国名称空
  结果、REST/MCP parity、发现 scope 到 Context/read-only SPARQL、partial/archived/
  workspace_not_ready/empty Project 全部通过；临时 keys/Projects/Ontologies 零残留。
- Outcome/next step: 唯一残余运行特性是未配置 `SECRET_KEY` 时 cursor 仅在当前进程生命周期有效，
  已在 API/MCP/design 文档明确，不违反验收；进入主 Agent 最终全量验证和提交关闭。

### 2026-07-19T11:43:47+08:00 — independent Round 1 and defect validation — tester and main agent

- Context: tester 审查稳定实现并执行独立 service checks；首次报告因安全分类器中断，随后仅用
  非操作性摘要成功追加同一 Round 1，失败历史完整保留。
- Action/decision: Round 1 `FAIL`。主 Agent 接受 D1 High：cursor 未绑定
  `authorized_project_id`，跨授权目录复用会错误跳过本目录候选；接受 D2 High：`SECRET_KEY`
  未设置时使用公开固定 fallback，不能满足 reviewed design 的 cursor 篡改拒绝合同。两项均与
  R1.2-002 授权范围、分页正确性和明确验收直接相关，不降级、不接受为残余风险。
- Evidence: shared test plan Independent Round 1；tester 独立内存目录验证；其余 focused
  `25 passed`；未创建持久测试数据。
- Outcome/next step: 将两个 confirmed root cause 交回 requirement_developer；要求身份绑定、
  deployment-specific/ephemeral-safe integrity key 策略和专项回归，再返回新 DEVELOPMENT_READY。

### 2026-07-19T11:43:47+08:00 — repair handoff Cycle 2 — main agent

- Context: Round 1 两个 High 缺陷阻断 PASS，full/runtime 用例按 tester 记录未执行。
- Action/decision: developer 必须只修 cursor trust boundary，不改筛选/排序合同或放宽测试；增加
  跨 Project reuse 拒绝、默认配置不可预测完整性、正常同身份续读和 REST/MCP 回归。不得编辑
  delivery record/shared test plan，不得提交。
- Evidence: reviewed design cursor/filter boundary；Round 1 D1/D2。
- Outcome/next step: 等待修复 DEVELOPMENT_READY 后，原 tester 先复测 D1/D2，再执行完整
  Round 2。

## Final verification

- Required checks: main-agent final backend `729 passed, 6 skipped`; frontend build PASS with only
  the existing chunk-size warning; Playwright `37 passed`; changed-file Ruff check/format PASS;
  interface documentation sync PASS; `git diff --check` PASS.
- Runtime/restart health: `ontology-platform.service` active after restart; backend health returned
  HTTP 200 `{"status":"ok"}`; frontend returned HTTP 200; authenticated discovery returned HTTP
  200 with bounded page metadata. The first health request ran 16 ms after restart and hit the normal
  startup window; the readiness poll succeeded after 7 seconds.
- Documentation/status sync: R1.2-002 is `已实现`; design is implemented/independently verified;
  API, MCP, platform guide, architecture overview, generated interface inventories, shared test plan
  and this record are synchronized.
- Cleanup: tester removed all temporary keys/Projects/Ontologies with zero residue; main-agent final
  runtime check created one uniquely named admin API key and deleted it in `finally`.
- Residual risks and follow-ups: without configured `SECRET_KEY`, discovery cursor integrity is
  process-private and cursors intentionally expire on restart/process change; documented clients
  restart discovery. GitNexus HIGH is retained as line-shift/hunk over-attribution to unchanged
  `_closure_values`/`visit`; staged detect_changes and exact diff remain part of commit closure.

### 2026-07-19T12:04:49+08:00 — final verification and documentation closure — main agent

- Context: independent Round 2 PASS and requirements/design/test status sync completed.
- Action/decision: 主 Agent 重跑全部仓库门禁，重启受管服务并验证新发现端点；需求状态更新为
  `已实现`。只保留已文档化的无 `SECRET_KEY` process-lifetime cursor 特性，不接受其他残余 defect。
- Evidence: backend `729 passed, 6 skipped`; build PASS; Playwright `37 passed`; Ruff/format/docs
  sync/diff PASS；systemd active；8001/5173 HTTP 200；临时 admin key 的 discovery HTTP 200 且 key
  已清理。
- Outcome/next step: 显式暂存 R1.2-002 文件，排除无关 R1.1-003 记录；运行 staged GitNexus
  detect_changes、检查 staged diff 后提交 `Deliver authorized semantic scope discovery`。

### 2026-07-19T12:04:49+08:00 — staged scope and GitNexus commit audit — main agent

- Context: 最终门禁通过，准备提交；工作树另有无关未跟踪 R1.1-003 delivery record。
- Action/decision: 只暂存 17 个 R1.2-002 product/test/design/record/docs 文件，无关 R1.1-003 保持
  未跟踪。`detect_changes(staged)` 仍报 HIGH、107 symbols、7 processes；再次确认 7 条只锚定
  staged diff 未改的 `_closure_values`/`visit`，属于大文件前插的行位移误归因。新增 service/test
  仍不在当前 index 的 symbol 清单中，但已由 exact staged diff、独立代码审查和完整验证覆盖。
- Evidence: `git diff --cached --check` PASS；staged stat 17 files、1267 insertions、64 deletions；
  GitNexus affected processes `proc_37`, `proc_141`, `proc_181`, `proc_182`, `proc_195`, `proc_196`,
  `proc_204`; backend/MCP/Playwright/independent Round 2 evidence above.
- Outcome/next step: HIGH 告警保留且证据化降级；staged scope 可提交，不包含无关文件。

## Retrospective

- Scope or design deviations: 实现遵守 reviewed design；唯一补充是明确未配置 `SECRET_KEY` 时
  cursor 的 process-lifetime 行为，不新增 migration 或前端页面。
- Rework and root causes: Round 1 暴露 cursor 未绑定授权 Project 以及固定默认完整性材料；根因是
  首轮开发只绑定筛选条件、测试也只覆盖同主体/filter 篡改，未覆盖跨身份复用和默认配置。
- What shortened or delayed delivery: 已完成的 13 项功能澄清和共享 readiness 原语缩短实现；两次
  tester 最终回执被安全分类器中断，只影响记录方式，不影响执行证据或缺陷闭环。
- Reusable lessons: 范围发现必须与 semantic retrieval/Build Context 分离；任何 opaque continuation
  state 都应同时绑定筛选和授权目录，并对默认配置做独立验收；GitNexus hunk 级 HIGH 必须结合
  exact diff 和受影响流程证据处置。
