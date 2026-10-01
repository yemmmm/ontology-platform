# R4.0-012 开发与独立测试记录

- 权威需求：[R4.0-012](../../requirements/requirements-v4.0.md#r40-012-证据追溯能力阶段性停用与多视角建模解耦)。
- 已审阅设计：[详细设计](../designs/2026-10-01-r4-0-012-tracing-suspension-design.md)。
- 设计基线：`a6d4c72`，方案审阅 Agent 只读审查 PASS，无 Critical／High，无新增关键假设。
- 本文只把设计 §8 已有验证要求作为共享执行记录，不增加范围或完成门。
- 当前状态：开发完成，独立 Round 2 判定 A1—A7 功能 PASS；A8／L1 未授权、未执行，整体 PARTIAL。
- 每轮保留基线、命令、结果、失败、清理与未执行项。开发者只追加开发自测段；独立测试者追加独立轮次，不互相覆盖。

## 1. 验收映射

| 编号 | 检查范围 | 必需证据 |
| --- | --- | --- |
| A1 | 实际角色输入、Task／Skill／reference、动态反馈和工具嵌套 Schema | v4 运行配置组装无来源留存／补证任务，不能仅关键词删除或宿主提示绕过 |
| A2 | 无证据候选／Batch 的 dry-run、同内容批准、apply、读回、交接 | 无缺证 warning、无平台 Evidence／Association／fact binding；身份与内容绑定正确 |
| A3 | Context Query 各投影、普通资源／事实、构建与治理读取 | 无 lineage／证据 repository 隐式依赖，无追溯专用字段，无伪造 supported／complete |
| A4 | 授权、分页截断、stale、语义未知、规则结果身份 | 原合同保留；业务映射与 label／mapping 命中解释不误删 |
| A5 | REST／MCP／目录、旧别名、Runner staged capability、通用 command | 专用入口与别名均不可调用；无历史只读替代；旧参数正常验证失败 |
| A6 | 导航、实体、事实、检索、治理和构建页面及请求 | 无追溯入口、缺证指标或占位；共享页面正常 |
| A7 | 新写入、规则／推理零纯追溯采集；拒绝重试、unknown、新 checkpoint 接续／fork | 真实 PostgreSQL／RDF 及必要 HTTP 证据；事务、幂等、fence、COMMIT 不确定处理和授权恢复保留 |
| A8 | 有界真实建模及独立语义验收 | 需单独真实建模授权；未执行前明确 PARTIAL，不用 A1—A7 替代 |

## 2. 执行规则

- 先读需求、设计和实际改动；仅在开发者明确 development-ready、停止写入后独立测试。
- 复用现有测试及 fixture，必要的新测试须检验外部行为或真实边界，不新增一次性语义裁判。
- 仅创建和清理可确认归属的测试资源；保留失败记录，不操作其他活动 run。
- 测试者不修改产品代码或降低断言标准；失败交回开发者修复后追加复测轮。
- 记录 developer tests、independent functional acceptance 和 L1，不能混称。
- 代码、配置、环境未变化的已通过检查可复用；对修订、失败及证据缺口做针对性复测。

## 3. 仓库必需检查

```bash
cd backend
uv run pytest
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests
```

```bash
cd frontend
npm run build
npx playwright test
```

按新 fixture 执行 `backend/tests/test_checkpoint_data_live.py` 等必要真实依赖检查。
接口变更同步 `scripts/sync-interface-docs.py`，Skill 变更执行现有 validator；完成必需测试后
重启 `ontology-platform.service`，检查 active、`http://127.0.0.1:8001/api/health`、
`http://127.0.0.1:5173/` 和受影响接口。重启前确认不存在会被本次合同切换破坏的活动运行。

## 4. 开发自测

### 开发首轮（2026-10-01，基线 a6d4c72 + 当前未提交增量）

- 实施前 `impact(ModelingBatchService, upstream)`：CRITICAL，直接调用 3、全链 106、
  96 processes；已由主 Agent 向用户提示。`SemanticContextQueryService` 为 LOW。
  前端 `bindFactEvidence`／`readModel` 图查询为 UNKNOWN（符号未收录），使用具体调用点及 diff；
  上述图的泛化传播不等同于各条执行链的精确覆盖。
- 只读运行核对：没有正在执行的 Modeling Team／Claude 建模进程；PostgreSQL 中
  validating／applying／recovering Attempt 为 0，推理／规则／校验 pending／running 为 0，
  未释放且未过期的 Ontology Lease 为 0。12 个 active Build Session 的活动时间均在
  2026-09-12—18，保留原状态，未停止或清理。服务使用 uvicorn `--reload`，最终 HTTP
  结果须在稳定增量完成必需检查并重启后重新取得。
- `cd frontend && npm run build`：PASS。首次调用误在仓库根执行，报 Missing script: build；
  改为 frontend 后通过。首次类型检查发现误删共享 Plus／Workflow import，恢复对应 import
  后通过；未增加新功能。
- `npx playwright test evidence-references.spec.ts stage4-tools.spec.ts build-context-debug.spec.ts`：
  16 PASS、2 FAIL；失败来自新测试把默认页面误写为 Project Brief，实际既有默认回退为
  Overview。修正测试期望后 `npx playwright test evidence-references.spec.ts` 为 2 PASS，
  无放宽入口不可用或请求断言。
- `npx playwright test --grep-invert 'Live contract'`：39 PASS，过滤表达式的大小写未匹配
  实际 suite 标题，因此实际执行全部 39 项，含 4 项真实 backend／Oxigraph。
  本轮运行于改动中的 reload 服务，仅作阶段回归，不作为稳定版本运行验收。
- 补充 GraphSet 无专用请求断言并清理普通 fixture 后，
  `npx playwright test semantic-governance.spec.ts frontend-workflow-reshaping.spec.ts`：8 PASS。
  普通 Facts 请求不带 `field_set=evidence`；旧 Evidence URL／stored tab 回到默认 Overview，
  GraphSet 与 Facts 均无 evidence／lineage／provenance 专用请求。
- 修正 GraphSet 中文文案后再次 `npm run build`：PASS，3133 modules，vite build 通过；
  只有现有 bundle-size 提示。
- `cd backend && uv run python ../scripts/sync-interface-docs.py --write`：接口清单已同步；
  最终增量仍须 `--check`。
- 以上为开发侧验证，尚未完成 backend／Team 全量回归、稳定运行检查或独立功能验收。

后续开发轮次与稳定交接证据在本节追加。

### 开发定向回归（2026-10-01，增量尚在修改）

- 后端首轮全量 `cd backend && uv run pytest -q --continue-on-collection-errors`：
  874 PASS、106 FAIL、38 SKIP、4 collection errors（83 秒）。失败清单主要为 Batch 旧
  evidence fixture、Context/read model 旧追溯字段、退役路由／MCP 和 r3008 旧候选合同。
  此轮保留为迁移依据，不记为稳定集成通过；后续只按明确失败分组修复。
- `cd backend && uv run pytest tests/test_semantic_context_query.py tests/test_semantic_context_query_api.py -q`：
  54 PASS、10 FAIL。第一失败为旧断言读取已撤下的 `evidence_reference_ids`，其余涉及旧
  lineage／compact 返回预期；测试迁移及复测尚未完成，不记为 PASS。
- `uv run pytest tests/test_semantic_read_model_stage2_execution.py tests/test_semantic_read_model_stage3_execution.py -q`：
  33 PASS、2 FAIL，旧 missing-evidence 筛选及 publication readiness 断言尚未迁移。
- 角色提示已要求逐段保留与本需求无关的已有合同；恢复未完成前不能进入独立测试。
- `RUN_TRACING_SUSPENSION_LIVE=1 uv run pytest tests/test_tracing_suspension_live.py -q`：
  首轮新测试误取 workspace version 顶层字段，改为已有 `workspace.workspace_version` 后，
  无证据 Batch dry-run／apply／幂等重放、旧字段 422、canonical 写入、full／compact Context、
  普通 Facts、规则运行及派生结果身份均走通。整项仍 FAIL，推理返回旧本地配置路径不存在：
  `/home/yangxiang/projects/ontology-platform/backend/scripts/dev_owl_reasoner.py`。
  确認当前脚本存在后，仅把 gitignored `backend/.env` 的 reasoner 路径改为
  `/home/yangxiang/ontology-platform/backend/scripts/dev_owl_reasoner.py`，待必需测试通过后正常
  重启和复测。每轮 HTTP fixture 的项目、图、规则、API key 及关联记录在 finally 清理；
  未触碰已有业务资源。重复定位轮保留于开发日志，不算独立运行验收。

### 开发 A5 合同迁移（2026-10-01）

- 接手六个现有入口测试模块：`test_evidence_rest_surface.py`、`test_mcp_surface.py`、
  `test_mcp_tools_endpoint.py`、`test_lineage_api.py`、`test_lineage_mcp.py`、
  `test_fact_evidence_api.py`；只迁移本需求改变的合同，没有修改产品代码。
- 初始六模块执行在 `test_fact_evidence_api.py` collection 阶段失败：旧 router 引用已经
  撤去的 `compile_bind_fact_evidence`。其余五模块执行为 14 PASS、7 FAIL，失败均为旧
  lineage／MCP 注册和兼容调用期望。旧 artifact router 隔离测试仍绿，无法证明生产停用。
- 改为真实生产 router 注册检查，覆盖 Artifact／Chunk／Reference／Association、事实绑定
  和 lineage 的已撤下路由（包括 history 参数）；保留历史 artifact/chunk 仍在数据库的断言。
  MCP 验证六个专用工具及旧别名不在实际目录且直接调用为 Unknown tool，同时保留共享
  工具准确集合、Batch 嵌套字段和业务 payload 指导的原断言。
- 最终命令：`cd backend && uv run pytest tests/test_evidence_rest_surface.py tests/test_mcp_surface.py tests/test_mcp_tools_endpoint.py tests/test_lineage_api.py tests/test_lineage_mcp.py tests/test_fact_evidence_api.py -q --tb=short`：
  40 PASS（10.28 秒）。六模块 Ruff 和 `git diff --check` PASS。已停止六文件写入并交回
  后端全量回归；这仍是开发自测，不是独立验收。

### 开发 Team 合同迁移（2026-10-01）

- 首轮 Team 全量 `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`：
  1878 PASS、129 FAIL、12 ERROR、1 SKIP、306 subtests PASS（190.32 秒）。主要失败为旧
  proof／evidence-map／staged-association 工具期望、中性候选 v2、008B／009 旧版本及
  translator golden fixture；没有把此轮记为通过。
- 分担八个现有测试模块：008B staged decisions／runner wiring／gate feedback rearm，
  009 unified graph／runner wiring／plan-ref capability／submission recovery，以及
  014 dry-run before translation。第一轮 115 PASS、4 FAIL，剩余为 entity-binding fixture
  仍声明中性 v2；改为明确 v3 fixture 后最终 121 PASS（11.32 秒），Ruff／diff check PASS。
- 上述迁移只修改五个测试文件中的明确版本及字面追溯字段，不引入自动剥除旧字段的 helper。
  新增旧 `evidence_refs` 与旧 schema 版本拒绝断言；保留真实 read handle、批准内容 digest、
  干运行内容与 workspace 不一致、未知写入和恢复反例。八模块已停止写入交回 Team 全量。
- 再分担 23005 candidate-progress／issue-escalation、23008 non-JSON interim 和 23009
  feedback／timeout 五个模块。只修改两文件中的明确候选 fixture（v3 kind、去掉字面
  `evidence_citations`），Unicode／尾随空白的原始字节归属、消息身份、时钟和修复反例
  保持。五模块 85 PASS（1.18 秒），Ruff／diff check PASS，已冻结交回 Team。

### 开发集成收敛（2026-10-01）

- 后端迁移后第一轮全量：1002 PASS、1 FAIL、44 SKIP（113.66 秒），仅 canonical 旧
  inline-evidence 测试失败。修复后第二轮 1003 PASS、44 SKIP（115.22 秒），但其中新增
  R-005 模块六项跳过，故未作为稳定通过；随后撤掉新 skip，迁移必要普通 history、
  直接编辑／规则新写入零采集断言，第三轮 `cd backend && uv run pytest -q --tb=short`：
  1009 PASS、38 SKIP（112.27 秒），无新增 skip／xfail。38 项为既有环境／opt-in 门，
  必需真实依赖边界另行执行。
- 既有真实依赖：`RUN_CHECKPOINT_DATA_LIVE=1 CHECKPOINT_DATA_HTTP_BASE_URL=http://127.0.0.1:8001 uv run pytest -q tests/test_checkpoint_data_live.py`：
  1 PASS。首次遗漏 `tests/` 路径报 file not found，修正路径后执行。
  `RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest -q tests/test_modeling_batches_postgres.py`：
  首轮旧断言期待 1 Reference／2 Associations 失败，迁移为明确零纯追溯新增后 2 PASS。
  该测试变更后最终全量为 1009 PASS、38 SKIP（113.63 秒），无失败或 collection error。
  后端受影响子集 58 PASS、compileall PASS；定向 Ruff 排除原有 F541／E402 后 PASS。
- 前端代码与构建输入未再变化，复用已通过的 `npm run build`；稳定后端代码阶段执行精确
  `cd frontend && npx playwright test`：39 PASS（10.3 秒），含四项实际 backend／Oxigraph
  检查。最终重启后的服务健康与受影响 HTTP 检查仍待完成。
- 当前 `sync-interface-docs.py --check`、ontology-modeling Skill validator 及 changed diff
  格式检查 PASS；新增 v4 Task 入口和本地文档链接检查 PASS。
- A1／F7 分类：CQ 合同中的 `evidence_refs: [{source, locator}]` 是独立题池／判定依据，
  只交给 competency-question 角色；`competency_questions.public_projection` 不包含该字段，
  没有向 Modeling 转交留存任务。按设计 §2.1 第 5 项、§3.1 与 F7 保留这些独立验收记录，
  不将其当作平台 Evidence 资源机械删除；继续保留既有公开投影不泄露的断言。


### 开发真实运行检查与最终收敛（2026-10-01）

- Team 第二轮全量为 1952 PASS、57 FAIL、13 SKIP（192.76 秒）。其中 translator 12 项
  historical fixture 新增 `SkipTest` 被开发侧审计识别，此轮不能作为稳定通过；要求撤掉该
  跳过，用显式 v3 literal fixture 继续执行原 golden 语义／delta／IRI／shape 断言。
- Backend worker 接管 7 个剩余 Team 模块（实际 6 文件改动）：97 PASS、5 subtests PASS，
  Ruff／compileall／diff check PASS。恢复 socket 模块无需修改，授权、增量修订、完整性、
  未知写入和恢复断言保留。
- `test_protocol_retrieval_gate.py`、`test_staged_associate_evidence_forwarder.py` 首轮
  5 FAIL／42 PASS：仅旧 tracing 硬门与已退役 socket／CLI 工具正向期待失败。普通检索
  fixture 改为无 trace 字段，错 predicate／subject／object、分页和跨 CQ 绑定负向保持；
  旧 trace 状态不再阻断。Offline forwarder 的真实子进程、原封 envelope 和未知写入分类
  测试全部保留，三项当前集成期待改为拒绝且零 child／intent／receipt。
  `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests/test_protocol_retrieval_gate.py ../modeling_team/tests/test_staged_associate_evidence_forwarder.py`：
  47 PASS（18.07 秒），Ruff／diff check PASS。
- Team 生产文件冻结后，重启前 SQL 检查 in-flight Attempt、有效未释放 Lease、
  pending/running validation／reasoning／rule 各为 0。使用本机 user bus 环境执行
  `systemctl --user restart ontology-platform.service` 成功；status 为 active (running)。
  首次 curl 时启动构建尚未完成、端口未监听，等待 ready 后 8001 `/api/health` 返回
  `{"status":"ok"}`、5173 返回前端 HTML，二者均通过。
- 新增 opt-in live 验证此前先发现 fixture workspace_version 路径错误，修正后又发现本机
  gitignored `backend/.env` 的 reasoner 命令仍指向旧 checkout；经主 agent 明确授权，仅将
  该命令路径修复为当前 checkout，重启后执行
  `cd backend && RUN_TRACING_SUSPENSION_LIVE=1 uv run pytest -q tests/test_tracing_suspension_live.py`：
  1 PASS（8.64 秒）。真实 HTTP／PostgreSQL／Oxigraph 证明退役路由 404、catalog 工具
  不再注册、旧 Batch 字段 422、dry-run／apply／幂等重放、canonical 写入、普通 full／compact
  Context 与 Fact、规则身份及真实推理正常；本次项目域新增 EvidenceReference／Association／
  FactEvidenceBinding／StatementOccurrence 为 0，规则与推理 metadata 无 tracing 字段。
  测试 finally 只清理自有资源。
- `detect_changes({repo:"ontology-platform",scope:"all"})`：163 changed symbols、273
  affected、129 files、CRITICAL。已先前告知公共 ModelingBatchService 调用面风险；覆盖
  Batch／Canonical write／Context／ReadModel／Reasoning／Rule 与 Team candidate／runtime。
  索引仍包含退役路由，且部分前端 symbols 未索引；只作为变更影响提示，实际执行路径由
  调用点检查与相关测试验证，不能把图索引数量当运行覆盖证明。
- Docs check 在系统 Python 首次因缺 FastAPI 未运行；改为正确环境
  `cd backend && uv run python ../scripts/sync-interface-docs.py --check`：PASS。
  Team 最终全量与新增 skip／xfail／early-return diff 审计尚待余下 fixture 完成。


### 开发 A1 提示合同修复（2026-10-01）

- 主 agent 复核发现当前 Modeling 提示仍要求读取 v4 Task 只挂给 Coordinator／Protocol 的
  staged/unified 执行合同，且 Modeling 与 Protocol 各一处 unified candidate literal 为旧 v1。
  撤销生产冻结后，只改为 Modeling 可见 `r4-0-012-modeling-contract.json`，明确 Task
  `unified_semantic_graph` 选择及当前 v2 candidate contract，并在该角色 reference 补齐
  stage3 slot 的完整语义出版字段；没有重新暴露 Protocol receipt 或执行字段。
- 新增 `test_r4012_role_contract.py` 使用真实配置 loader 的 v4 Task／Profile：验证 Modeling
  可見 reference 与 Protocol 专有合同隔离、自足 slot fields/schema、根据可见合同构造的 slot
  经真实 validator 接受，以及旧 v1 拒绝；检查实际加载 Modeling／Protocol 提示不含旧 literal
  或不可见合同依赖。首轮在 reference 编辑尚在进行时按临时 `slot` key 取值，1 FAIL／2 PASS；
  对齐最终 `stage3_slot` key 后 3 PASS（0.11 秒），Ruff／diff check PASS。
- translator golden 改读一次性迁移生成的 checked-in v3 静态 fixture，历史 run 文件保持不变。
  不加入 runtime 通用自动 strip；checked-in fixture 缺失或类型错误应直接失败，新增
  SkipTest 已撤除。此刻新增 skip／xfail／collection filtering diff 命中 0；最终全量待记录。
- gate／forwarder 两文件最终复测 47 PASS（16.66 秒），offline fixture 的真实 timeout
  逻辑保持；live fixture 与该三文件定向 Ruff PASS，开发文件已停止写入。


### 开发最终通过与停止写入（2026-10-01）

- translator 定向 16 PASS，原 12 项 golden delta／IRI／Shape／闭包断言实际执行，未 skip。
  退役 staged 工具入口定向 23 PASS，仅改变当前 listing／schema／dispatch／socket／活跃
  提示 reference 的旧正向期待，离线历史 forwarder/gate 断言保持。revision 定向 17 PASS；
  Backend worker `test_r23002.py` 最终 38 PASS、18 subtests PASS，Ruff／compileall／
  diff check PASS，后停止写入。
- 最后 Team 全量在仓库根执行
  `env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q modeling_team/tests`：
  **2022 PASS、1 SKIP、314 subtests PASS（169.40 秒）**；无 FAIL／ERROR。
  命令、摘要与各组定向结果在 `/tmp/r4012-team-final.log`。唯一 SKIP 为原有
  `test_r23005_producer_smoke.py` 的显式 `R23005_RUN_REAL_SMOKE` opt-in；当前该值未启用，
  retained auto-select golden 可用，translator golden 亦实际执行。没有将新旧候选不兼容
  转为 skip／xfail 或 collection 排除。
- 最终 diff 审计：没有新增 tracked skip／xfail／collection filtering；仅两个 fixture
  constructor 的新增 return，未引入测试 early-return。新增 live opt-in 条件已另行以
  `RUN_TRACING_SUSPENSION_LIVE=1` 实际执行通过。Team 最终相关文件 Ruff 与 diff check
  PASS；runner.py 四项 F401／F841 经 `git show HEAD:... | ruff check --stdin-filename ... -`
  对照全部在基线同样存在，未扩修无关 lint。
- Team 的 A1 prompt/contract freeze 已恢复，Backend worker 与 Team worker 均返回明确
  停止写入；开发协调方测试代码及产品文件也已停止写入。前后端代码在上述全量、重启和
  live 检查后未再修改；后续窄提示合同修复不改变服务 runtime endpoint 输入。
- 开发结果为 development-ready，等待独立功能验收。A8／L1 未授权，本轮没有 semantic start，
  不以这些机械／合同／运行检查报告真实语义质量 PASS。


### 开发修复 Round 1 缺陷（2026-10-01）

- 完整读取下方独立 Round 1；只接受 D1／D2／D3 的窄处置，不修改其 FAIL／缺陷／失败
  历史。生产与测试文件本轮允许修复；未新增角色、框架或提交。
- D1 先补真实生产 app 的 HTTP regression，`uv run pytest -q tests/test_semantic_access_http.py -k export_graph_set`：
  旧参数 true／false 各 FAIL（实际 200），正常 protected-quads 导出 PASS，7 deselected。
  `semantic.py::export_graph_set` 只检查 `include_evidence` 的存在，使用相邻 export_dataset
  相同 422 `unsupported_parameter`；不扩大到其他未知 query。复测整个
  `uv run pytest -q tests/test_semantic_access_http.py`：10 PASS（3.89 秒），普通导出、
  operator／manager 授权过滤保持。
- D2 新增实际 v4 loader + `TeamRunner._task_text` 四角色回归，初始 4 FAIL／3 PASS。
  动态静态前缀改为必要 workspace read／refresh／authorization checks／read-write validation，
  保留首次完整读取、compaction／stale 重读、角色私有资料隔离和 handoff 复用；同步原
  prompt-cache 合同的对应句，未改其他提示。`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests/test_r4012_role_contract.py ../modeling_team/tests/test_prompt_cache_contract.py`：
  33 PASS（0.48 秒），包含真实动态文本及原缓存／资料隔离分支检查。
- D3 live fixture 保存实际创建的 `key.name` actor，按这个本轮唯一 actor 清理 audit；新增
  本轮确实产生 audit、finally 后该 actor audit 为 0 的真实 SQL 断言。live 中补普通导出、
  旧参数 true／false 422 和无授权导出 401；需在后端 full 通过、正常重启后实际执行。
- 历史归属确认：只查询指定两个 developer actor 的四个精确 audit。04:22:13—14 和
  05:18:40—41 UTC、唯一 fixture UUID、class/entity RDF identifier、标签
  `Evidence inspection equipment`／`Device <UUID>` 及 canonical-write command 与本 agent
  同一新 fixture 两轮完全一致。因此仅按精确 actor + ID 删除以下四条，并验证两 actor 各 0：
  `cc45b33a-70f6-53cc-98a4-db137cac8ddf`、`85b421d5-5276-41a3-8086-8810e6638960`、
  `843dc916-5b83-5aec-9dbf-f1f02718970c`、`882eb588-288b-43c9-8e2a-720bf987856f`。
  确认与删除报告 `/tmp/r4012-d3-owned-cleanup.json`。没有重删独立 Round 1 已清的两条，
  没有按全库 prefix 删除或操作未知身份。
- 四个本轮测试文件 Ruff PASS；`cd backend && uv run python ../scripts/sync-interface-docs.py --check`
  与 diff check PASS。`cd backend && uv run pytest` 全量已启动，结果随后追加。


### Round 1 修复开发验证结束（2026-10-01）

- `cd backend && uv run pytest`：1011 PASS、38 SKIP、116.46 秒，无 FAIL／ERROR；日志
  `/tmp/r4012-round1-fix-backend-full.log`。Team 只执行上列受影响 33 项，复用其他 2022
  full／前端 build／39 Playwright 稳定证据，未重复扩测。
- 重启前 in-flight Attempt、有效 Lease、pending/running validation／reasoning／rule 各为 0。
  正常重启 user service 成功，active (running)；启动构建就绪后 backend health 为 ok，
  frontend 为 HTTP 200。`RUN_TRACING_SUSPENSION_LIVE=1 uv run pytest -q tests/test_tracing_suspension_live.py`：
  1 PASS（8.66 秒），日志 `/tmp/r4012-round1-fix-live.log`。实际正常导出内容保留，旧选项
  true／false 都为 422 unsupported_parameter，无认证导出 401；本轮实际产生的 audit 用
  真实 actor 清理后 SQL count 为 0，同时此前 Batch／规则／推理／零纯追溯采集断言保持。
- 清理后只读核对又定位到开发原始 04:21 的三轮同 fixture 残留，每轮两条。逐条比对
  actor UUID、相同 class/entity RDF identifier 与独有 fixture 标签、canonical-write 类型，
  时间均属于本 developer 最初复现、早于独立验收；按三个精确 actor 和六个精确 ID 补删，
  不按 prefix 删除。与上述给定四条合计确认自有 10 条，报告仍为
  `/tmp/r4012-d3-owned-cleanup.json`。各 actor 剩余 0；只读 prefix 检查 audit 总计 0，
  live fixture 项目／key 均 0。独立测试已补清的两条没有重复修改，没有未确认记录删除。
- 最终稳定修复指纹 `/tmp/r4012-round1-fix-fingerprint.json`，六文件：
  `backend/app/api/semantic.py`、`backend/tests/test_semantic_access_http.py`、
  `backend/tests/test_tracing_suspension_live.py`、`modeling_team/runner.py`、
  `modeling_team/tests/test_r4012_role_contract.py`、`modeling_team/tests/test_prompt_cache_contract.py`。
  full／runtime／live 后再次对照六项指纹未变。接口 doc check／相关测试 Ruff／diff check PASS。
- **development-ready / record-ready；全部开发产品、测试、文档写入停止，未提交。**
  D1／D2／D3 为开发侧已修复，仍需独立 Round 2 判断；下方 Round 1 FAIL 历史不变。
  A8／L1 仍未授权，本轮 semantic start 为 0。

## 5. 独立测试

### Round 1 — 独立功能验收（2026-10-01）

**结论：A1—A7 功能 FAIL；需求整体 PARTIAL，A8／L1 BLOCKED（未授权、未执行）。**
发现一项 Medium 产品合同缺陷、一项 Low 动态提示残留，以及一项 Low 测试 fixture 清理缺陷。
建议主 Agent 将以下窄问题交需求开发 Agent 修复，再以同一文档追加 Round 2；测试者未改产品代码、
未提交，未创建、继续或修改任何被验收语义 run，semantic start 消耗为 0。

#### 基线、审查与复用证据

- HEAD：`a6d4c72e34ac9fc4b5f9d47942826c50c8340913` 加 development-ready 未提交增量。
  交接清单 `/tmp/r4012-independent-baseline.json` 为 140 文件，SHA256
  `174a9dd1d166fce380b364b52d7e83c6870344c42f406281d84e160824b2fc46`；测试前及结束核对
  全部 140 文件内容指纹一致（共享测试／交付记录除外）。开发者在本轮期间停止写入。
- 已读上级与仓库 AGENTS.md、R4.0-012 F1—F7／A1—A8、已评审设计及本文所有开发轮次。
  定向检查 Batch、canonical／直接编辑、Context／ReadModel、规则／推理、checkpoint、Runner、
  mechanics／capability、实际 v4 Task／Profile／角色输入和页面的 diff／调用点。
  复用开发 full suites：backend 1009 PASS／38 既有 SKIP；Team 2022 PASS／1 既有 opt-in
  SKIP／314 subtests；frontend build 与 39 Playwright PASS。没有机械重跑全量或启动新框架。
- 大段删除主要退役 fact-evidence decoration、专用 REST／MCP 与 proof-v2 publication 合同。
  授权、分页、stale、规则执行、item dependency／原子应用、unknown／恢复仍有现存测试；
  本轮定向执行相关反例。translator checked-in v3 literal fixture 正常加载，原 golden
  delta／IRI／Shape 12 项实际执行；未新增 skip／xfail／collection filtering。此为定向审查，
  不宣称图索引全链覆盖或所有历史测试断言均逐行审计。

#### 实际命令与结果

1. 在 `backend/` 执行：

   ```bash
   RUN_TRACING_SUSPENSION_LIVE=1 RUN_CHECKPOINT_DATA_LIVE=1 CHECKPOINT_DATA_HTTP_BASE_URL=http://127.0.0.1:8001 RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest -q tests/test_tracing_suspension_live.py tests/test_checkpoint_data_live.py tests/test_modeling_batches_postgres.py tests/test_checkpoint_data.py tests/test_r005_independent_acceptance.py tests/test_lineage_service.py tests/test_evidence_rest_surface.py tests/test_mcp_surface.py tests/test_semantic_context_query.py tests/test_semantic_access_mcp.py tests/test_semantic_read_model_stage2_execution.py tests/test_semantic_read_model_stage3_execution.py tests/test_semantic_derived_state.py --tb=short
   ```

   **136 PASS，16.12 秒，无 SKIP**。包含实际 HTTP／PostgreSQL／Oxigraph 无证据写入、
   幂等回放、旧字段 422、full／compact Context、普通 Facts、规则身份／推理、零纯追溯新增，
   真实 capture lock-before-snapshot／fork 与 PG 并发，及 COMMIT ack 丢失机制反例。

2. 在仓库根执行：

   ```bash
   env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q modeling_team/tests/test_r4012_role_contract.py modeling_team/tests/test_translate_candidate_to_batches.py modeling_team/tests/test_protocol_retrieval_mcp.py modeling_team/tests/test_protocol_retrieval_gate.py modeling_team/tests/test_r30008b_staged_decisions.py modeling_team/tests/test_r30009_unified_graph.py modeling_team/tests/test_r30014_dry_run_before_translation.py modeling_team/tests/test_staged_associate_evidence.py modeling_team/tests/test_staged_associate_evidence_forwarder.py modeling_team/tests/test_proof_v2_runtime_asset.py --tb=short
   ```

   **181 PASS／11 subtests PASS，19.67 秒，无 SKIP**。候选／批准内容绑定、旧 schema／
   旧 evidence 字段拒绝、golden 翻译、已退役 staged／socket capability 不可调用均执行。

3. 在 `frontend/` 执行：

   ```bash
   npx playwright test evidence-references.spec.ts semantic-governance.spec.ts build-context-debug.spec.ts stage4-tools.spec.ts frontend-workflow-reshaping.spec.ts
   ```

   **26 PASS，7.1 秒**。旧 URL／stored tab 回到 Overview，Facts／GraphSet 无专用请求，
   Entities/Search、Rules、治理／构建页共享交互及正常错误／分页可用。

4. 在 `backend/` 执行：

   ```bash
   uv run pytest -q tests/test_semantic_access_authorization.py tests/test_semantic_access_http.py tests/test_semantic_context_cursor.py tests/test_checkpoint_data_seal_read.py tests/test_modeling_batches_delete_recovery.py tests/test_modeling_batches_service.py -k 'recovery or atomic_validation or idempotency or retryable or forbidden or protected or denied or cursor or checkpoint or sealed' --tb=short
   ```

   **30 PASS／83 有意 deselected，4.47 秒**。受限资源／关系读取、Context／export 过滤、
   cursor 绑定、原子拒绝、幂等冲突、恢复已写 RDF／释放 fence／安全重试及 sealed source 边界。

5. 补充独立探针（通过 `uv run python - <<'PY'` 执行 inline fixture，未写产品或测试代码）：
   真实 loader 加载 `r3-0-011-competency-question.yaml` 与
   `r4-0-012-tracing-suspension.yaml`，调用 `TeamRunner._task_text(role)`，读取各角色
   instruction、Skill 及挂载 references；Modeling 可见 r4 semantic contract，自足 slot
   字段与 v2 unified candidate 正确，Protocol 专有执行合同不向 Modeling 挂载。
   CQ `question.evidence_refs` 属独立题池依据，`public_projection` 不包含它，按 F7 保留。
   mechanics 设置 `PROTOCOL_PROOF_GATE=1`、`PROTOCOL_FORMAL_CANDIDATE_GATE=1` 后仅列出
   receipt／conflict／translate，mechanics 与 capability 嵌套 trace keys 均为 0；直接调用
   `write_candidate_item_evidence_map`／`verify_scoped_retrieval_fallback` 均为 -32601。
   首次探针缺 `modeling_team` 模块搜索路径，导入失败；改为 `PYTHONPATH=.:modeling_team`
   后执行成功，没有把未执行算为通过。发现 D2 下述动态提示残句。
6. 使用临时 admin key 与新 Project／Ontology 执行实际 HTTP 旧参数反例，结果见 D1。
   再用独立新资源执行 canonical entity 写入 → `/checkpoint-data/capture` → `/fork`：
   snapshot schema 为 `r3-0-017-platform-data/v2`，八类纯追溯表均不在 inventory，
   edit audit 无 `evidence_status`；fork 后真实 RDF、audit ID 与 graph revision
   `last_edit_audit_id` 正确保存／重映射，源 Ontology archived。
   v1 反例首次遗漏必需 `target_project_id`，422 只证明请求缺字段；补齐后实际为
   **409 `snapshot_invalid` / `Snapshot schema or digest does not match`**，正确拒绝旧格式。
   探针原误断言 400，因此脚本 exit 1；此为测试预期错误，实际证据为 typed 409，非产品缺陷。
7. 运行健康：无重启或环境修改。首次 `systemctl --user` 因测试进程无 user bus 返回
   `Failed to connect to bus: No medium found`；补 `XDG_RUNTIME_DIR=/run/user/<uid>` 与
   `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus` 后 `is-active` 为 active。
   实际 8001 `/api/health` 为 `{"status":"ok"}`，5173 `/` 为 HTTP 200。

#### 验收项结果

| 编号 | Round 1 | 实际证据／限制 |
| --- | --- | --- |
| A1 | FAIL（Low 残留） | 实际 v4 输入／当前 reference／schema 可用，但动态前缀仍声明 full evidence obligation（D2）；未用运行时忽略提示绕过 |
| A2 | PASS | 无证据候选与真实 Batch／canonical 写入、幂等回放、旧字段拒绝；交接内容与批准绑定反例通过 |
| A3 | PASS | Context full／compact、resource/fact 与关联读取无追溯字段；RecordingLineage 零调用，read-model 无证据 repo 装饰 |
| A4 | PASS | 受限读取／scope／mapping命中／分页／cursor／stale／no-match 与 explicit unknown 合同保留；规则结果 rule_id／rule_version 与派生 run 身份保留；真实业务意义判定留到 A8 |
| A5 | FAIL（Medium） | 专用路由、MCP、旧别名、staged／command／legacy proof env 不可用；Graph Set export 静默忽略 include_evidence（D1） |
| A6 | PASS | 26 页面测试，无入口／请求／缺证占位，共享功能可用 |
| A7 | PASS（产品边界） | 真实 PG／RDF、规则／推理及直接编辑零纯追溯采集，新 v2 保存／fork、锁顺序、并发和故障恢复；接续宿主的冻结／身份／授权机制复用同基线开发 full-suite，未启动任何真实 run；fixture 清理问题 D3 已补清本轮自有数据 |
| A8 | BLOCKED／未执行 | 没有真实 semantic start 授权，L1 无本轮语义质量结论 |

#### 缺陷与最小复现

**D1 — Medium，A5：Graph Set export 静默接受已停用参数。**
位置：`backend/app/api/semantic.py:1651` 的 `export_graph_set`。
以已认证 admin 请求创建新 Project／Ontology，取实际 `default_graph_set_id`，调用
`GET /api/semantic/graph-sets/{graph_set_id}/export?include_evidence=true`；`false` 亦同。
期望：按设计 §5.1 对已撤去 `include_evidence` 返回参数错误，不成功空结果。
实际：两者均 **HTTP 200，body `"\n"`**。同部署 `/api/semantic/export?include_evidence=true`
返回 **422 unsupported_parameter**；Facts `kind=missing_evidence` 和 `field_set=evidence`
均正确 400。handler 移除参数签名后未检查 request query，框架静默忽略。
建议只补该 export handler 的旧参数拒绝与外部行为测试，不扩大为一般未知 query 参数管控。

**D2 — Low，A1：实际动态任务仍保留泛化证据义务。**
位置：`modeling_team/runner.py:3382`。上述实际 v4 loader 后调用 `_task_text("modeling")`，
coordinator／protocol／CQ 亦同，均得到
`This reuse never skips a task-required live workspace read, a refresh, a validation, or a full evidence obligation.`
期望：实际动态输入只表达当前来源隔离、必要重读、授权与读写验证义务。
实际：虽然具体摘录／补证字段和工具已撤去，旧泛化 obligation 仍可能被解释为证据留存职责。
此项是提示歧义，不因关键词单独推断存在完整追溯任务或运行阻断；建议最窄明确当前义务。

**D3 — Low，测试 fixture：finally 清理 audit actor 身份不匹配。**
位置：`backend/tests/test_tracing_suspension_live.py:316` 使用 `key:{key_id}`，
而 `backend/app/security/auth.py:129` 的真实 principal actor 是 `key:{record.name}`。
本轮 live test 成功后仍残留同一自有 actor
`key:r4012-live-160c4d0a8f7b43bc9c99be55486aaea4` 的两个技术审计记录：
`9f516eca-b0a4-5d62-a077-13e34b0a6e1d`（05:42:29.241886 UTC）、
`5701547e-bb2c-46e4-a222-28a8e43b6764`（05:42:29.777467 UTC）。
期望：finally 仅且完整清理自有测试 audit。实际：Project／图／key 已清理，两个 audit 漏删。
测试者按这两个精确 ID 加精确 actor 补删 **2 条**，该 actor 剩余 **0**；未清理历史或身份不明记录。
此前开发 actor 如 `key:r4012-live-78ffdaf5010c47eb9207e15b0ab73069`（05:18:40—41 UTC）、
`key:r4012-live-78a1c1ea4b734925a7f5388679a04c59`（04:22:13—14 UTC）仍可识别，
但不属于本测试者，可由开发者核对归属后处理。建议 fixture 使用实际解析 actor 或记录的精确 audit ID。

#### 清理与交接

- live／checkpoint／PG fixture 按自有范围执行 finally；另补清 D3 本轮两条技术 audit。
  独立 export 项目 DELETE 204，4 图／key 清理；独立 checkpoint 的 2 项目／8 图／2 audit／key
  均清理，旧格式探针 key 清理。未清理开发历史资源或其他活动 run。
- 本轮不创建临时脚本／日志；已删除本次 Playwright 生成的 `.last-run.json`。
  测试者唯一仓库内容修改为本文 Round 1。结束时 140 文件指纹仍一致、`git diff --check` 通过。
- 已向主 Agent 报告并等待其决定修复；本轮完成后停止写入。Round 2 应先复测 D1／D2／D3
  和相邻 export 授权、动态提示／catalog、清理身份边界，复用其余未变输入证据。

### Round 2 — 缺陷修复独立复测（2026-10-01）

**结论：A1—A7 功能 PASS；整体 PARTIAL，A8／L1 BLOCKED（未授权、未执行）。**
Round 1 的 D1／D2／D3 均 FIXED，相邻边界 PASS，无新缺陷或 REGRESSION；无需再交开发修复。
历史 Round 1 失败与证据保留。此结论不证明真实业务语义质量，semantic start 消耗仍为 0。

#### 基线与复测范围

- HEAD 仍为 `a6d4c72e34ac9fc4b5f9d47942826c50c8340913` 加未提交增量。Round 2 manifest
  `/tmp/r4012-independent-round2-baseline.json` 为 142 文件，SHA256
  `ffcabd3a6a68f1ac8cc78acc0f7e01c7dca3334b6b5af2add8be3911758e0ed3`；测试前后内容一致。
- 相对 Round 1 的六文件增量已核对：Graph Set export handler、其 HTTP 测试、live fixture、
  Runner 动态任务文案、实际 v4 角色合同测试与 prompt-cache 合同测试。
  D1 仅拒绝退役 `include_evidence`，D2 保留来源隔离／必要重读并明确授权与验证义务，
  D3 使用真实 key.name actor 归属且断言清理后为 0，没有放宽其他断言或改产品范围。
- 复用 Round 1 未变的候选／批准／写入／读取／checkpoint／UI 证据；开发新 backend 全量
  1011 PASS／38 既有 SKIP、Team 受影响 33 PASS、重启与 live 证据作为同基线补充。
  本轮不重跑全部 suite、不开新审计、不启动或继续任何语义 run。

#### 实际命令、证据与结果

1. 在 `backend/` 执行：

   ```bash
   RUN_TRACING_SUSPENSION_LIVE=1 uv run pytest -q tests/test_tracing_suspension_live.py tests/test_semantic_access_http.py --tb=short
   ```

   **11 PASS，10.74 秒，无 SKIP**。真实 HTTP／PG／RDF 中普通 export 为 200 且包含已写
   class RDF；旧参数 true／false 均为 422 `unsupported_parameter`；未认证 export 为 401。
   受限 principal 的普通 export 仍过滤 protected quad，resource／Context／read-model
   授权反例保持。真实 Batch／canonical／规则／推理和零追溯采集断言继续通过。
   live fixture 在 finally 前按实际 actor 读到 audit count > 0，清理后同 actor count 为 0。
2. 在仓库根执行：

   ```bash
   env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q modeling_team/tests/test_r4012_role_contract.py modeling_team/tests/test_prompt_cache_contract.py modeling_team/tests/test_proof_v2_runtime_asset.py modeling_team/tests/test_protocol_retrieval_mcp.py --tb=short
   ```

   **50 PASS／11 subtests PASS，0.68 秒，无 SKIP**。实际 v4 四角色 `_task_text()`、可见
   references、必要首次完整读取／source isolation、prompt-cache 静态前缀合同保持；
   `full evidence obligation` 消失，替换为 `authorization checks, and read/write validation`。
   首次命令误列不存在的 `test_mcp_tool_schema_contract.py`，exit 4／no tests ran；随后改为
   实际存在的 `test_protocol_retrieval_mcp.py` 执行上述通过命令，未把未执行当作 PASS。
3. 独立 inline 探针（`PYTHONPATH=.:modeling_team`，没有写临时脚本）：实际 v4 loader，
   `_competency_questions=True`，对 coordinator／modeling／protocol／competency-question
   分别调用 `TeamRunner._task_text()`；四角色旧义务均不存在，授权／验证与完整首次读取均在。
   设置 `PROTOCOL_PROOF_GATE=1` 和 `PROTOCOL_FORMAL_CANDIDATE_GATE=1`，catalog 仍仅
   receipt／conflict／translate；两个退役 proof 工具直接调用均为 -32601，未复活停用入口。
4. 测试后通过只读 SQL 核对：`actor LIKE 'key:r4012-live-%'` 的 audit 剩余 **0**，
   `name LIKE 'r4012-live-%'` 的 API key 剩余 **0**。开发侧历史清理报告
   `/tmp/r4012-d3-owned-cleanup.json` 记载五个已确认 fixture actor 共 10 条精确 audit
   删除且各剩余 0；本测试者没有执行其清理，也没有触碰身份不明资源。
5. 用 user bus 环境查询 service `is-active` 为 **active**；8001 `/api/health`
   返回 `{"status":"ok"}`，5173 `/` 为 **HTTP 200**。本测试者未重启或修改运行环境。

#### 逐项复测结论与交接

| 检查 | Round 2 | 结论依据 |
| --- | --- | --- |
| D1／A5 旧 export 参数 | FIXED | true／false 422，明确 unsupported_parameter；普通 export 200 有真实 RDF |
| D2／A1 动态提示残留 | FIXED | 实际四角色组装无旧义务；授权、读取与验证要求保留 |
| D3 fixture actor 清理 | FIXED | 真实 actor 下 audit >0 → finally 0；数据库只读核对 audit／key 总残留 0 |
| export auth／保护集过滤 | PASS | 未认证 401；受限 principal 导出过滤 protected quad |
| prompt cache／可见 refs／mechanics catalog | PASS | 当前合同可用；legacy proof env 不恢复入口，两个退役工具 -32601 |
| A2／A3／A4／A6／A7 | PASS | 复用未变 Round 1 证据，加本轮必要相邻真实运行与授权回归 |
| A8／L1 | BLOCKED／未执行 | 无 semantic start 授权，未产生本轮独立语义质量结论 |

- 所有本轮 live fixture 自有资源均由修复后的 finally 清理；没有测试临时文件或过程日志。
  测试者仅追加本段，未改产品代码／其他记录，未提交。
- 结束时 142 文件指纹一致，`git diff --check` 通过；没有 STILL FAILING／REGRESSION 项。
  **Round 2 已完成并停止写入，交回主 Agent 收尾；无需额外功能测试轮次。**

## 6. 当前未执行范围

- A8／L1：没有本轮真实 semantic start 授权，未执行。
- A1—A7 功能检查已完成；开发及独立轮次保留于上文，不据此推导 A8／L1 通过。
