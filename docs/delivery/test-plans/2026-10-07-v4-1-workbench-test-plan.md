# v4.1 工作台共享测试计划

权威需求：[v4.1](../../requirements/requirements-v4.1.md)。
设计：[工作台设计](../designs/2026-10-07-v4-1-workbench-design.md)。
本文件保留每轮结果，不能以开发自测替代独立验收。

| 用例 | 范围 | 必须验证的行为 |
| --- | --- | --- |
| T01 | 001 | 无 Ontology 项目直进工作区、导航/旧路由、四种状态/未知/下一动作、来源时点 |
| T02 | 002 | Brief 与公开 Team CQ 分开；覆盖/可见性/版本/审核/冻结；隐藏 sentinel 不进入响应、页面、缓存/导出 |
| T03 | 003 | 七列矩阵/未登记；modeled 未 apply；失败只影响原验收；共享定义/依赖/修订及不完整提示 |
| T04 | 004 | 无 Class/多 Class、七视角、同 IRI 切换、精确详情/关联图、调用点/同类型对象位置、全部必要映射与脚本字段；无执行 |
| T05 | 005 | 非首个主命中页上下文续页；两类游标/改变查询/范围/过滤/投影重置；过期与预算/compact省略；受限对象不泄露 |
| T06 | 006 | 公开反馈与正式报告分开，接通public-regression固定真实目录且保留非盲标签；完整分母/未执行/待复核；当前模型/冻结/digest匹配、漂移、已删资源与缺证分别表达；原public note与版本绑定答案点保留、不凭文本伪造结构化裁决；L0—L3/SQL/API/DL边界 |
| T07 | 007 | Session/Team/宿主不串联；dry-run/apply/回读关联；未知写入/恢复/历史不可恢复；配置/额度/计时未知和真实记录；阶段结束有剩余工作 |
| T08 | 008 | 用户/状态、成员/角色、Grant、业务角色关联、保护集/成员、Key一次明文及撤销；非管理员拒绝；成员不自动获Grant；本地防误操作锁文案 |
| T09 | 009/022 | 旧 CRUD/Run/results REST/MCP与内部入口不能执行；页面无退役请求；专用执行分支清理证据；新业务规则语义/SHACL/OWL/查询保留；stub不DL PASS |
| T10 | 010 | 真正 Team/宿主 fixture 按项目绑定读取；RUNNING 已有公开CQ/地图但无handoff/cleanup仍可接入；Runner实际scope写绑定含create返回身份及合法拓扑更新；历史cleanup嵌套/handoff绑定及真实身份冲突；无绑定/错误/缺少/未接入分开；跨项目/普通Key/路径穿越/符号链接拒绝；刷新不改源；隐私字段白名单；两个freeze复用同题ID但版本/可见性不同，私有正文不得因旧public ID释放 |
| T11 | 011 | 已有反馈/修复只读关联、无自动修复执行/空占位页；隐藏诊断不进入生产投影 |
| T12 | 全部 | build、全Playwright、backend全pytest、差异/合同检查、重启active/health/前端/受影响REST、桌面/小屏/键盘浏览 |

测试分层：Playwright fixture 验证页面和网络交互；backend 测试验证真实产物格式/权限/安全投影；
受治理 RDF/接口集成验证用于 mocks 无法证明的共享语义路径；本次不新启建模或业务执行。
fixture 使用自有临时数据，清理只处理唯一可识别的测试项目/Key/文件。保留失败证据。
各 T 项必须列明自动/手工证据与未执行内容；完整 PASS 需要覆盖要求，而非只运行命令成功。

## 开发验证

- 首轮退役定向：`/tmp/retirement-focused2.log`，269 passed、1 skipped，17.81s。
- 首轮后端全量（开发并发中，不能作为稳定交付）：从 backend 执行
  `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`，
  `/tmp/v41-backend-round1.log`：38 failed、1077 passed、54 skipped，282.22s。
  退役方正在迁移剩余旧 CRUD/运行/统计断言；3 项接口目录同步失败待稳定后运行
  `uv run python ../scripts/sync-interface-docs.py --write`。本轮失败保留，未算 PASS。
- 前端首次 build 通过；35项fixture首轮包含旧导航/Recall/旧规则断言失败，迁移与新增覆盖进行中。
  等待开发方精确命令/完整结果及最终稳定代码验证。

## 独立验收 Round 1

待稳定开发交接；未执行，不是 PASS。

## 开发后续轮次（保留失败）

- Team 全量：2468 passed、8 skipped、314 subtests passed，207.93s；命令从backend执行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests`，日志 `/tmp/retirement-team-full.log`。
- 退役最终定向157 passed/1 skipped；OWL实际/历史模式8 passed；不是最终全后端PASS。
- 前端中间47fixture：43 passed/4 failed；业务确认来源调整后的断言、精确详情被旧data遮盖、图容器高度、表单label问题正在末次验证，不覆盖首轮失败。

- 后端增量稳定定向34 passed；Runner绑定29 passed/5 subtests；真实保留run+DB只读投影通过，报告准确stale（live_model_binding_changed）。
- 前端后续52fixture中间51 passed/1 failed（stub GET fixture仍为旧数据），仅修mock后最终52 passed，29.2s；build通过。另补真实public_regression_report kind提示，最终全量在重启后执行。

### 独立验收 Round 1 执行记录（2026-10-07）

- 基线：`362b41e` 加开发已停止写入的 v4.1 工作树；测试期间未修改产品、需求、设计、交付记录，也未启动/继续/修复真实建模。
- 总体结论：**FAIL**。实际生产产物 schema 与读取投影不一致，不能由前端简化 fixture 的绿色结果替代真实产物接入。
- 首次定向命令含不存在的 `tests/test_subject_access.py`，collection error，无用例执行；证据 `/tmp/v41-independent-round1-focused.log`。纠正为仓库实际 `tests/test_r4006_subject_access.py` 后重跑。
- 正式独立定向：从 `backend/` 执行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q tests/test_modeling_workbench.py tests/test_semantic_resource_list.py tests/test_semantic_context_query.py tests/test_r4006_subject_access.py tests/test_semantic_rule_definition_mcp.py ../modeling_team/tests/test_workbench_platform_binding.py`：**88 passed**，6.75s；证据 `/tmp/v41-independent-round1-focused-corrected.log`。这些测试支持读取、鉴权、游标、退役及 Runner 绑定的有界行为，未覆盖下述真实形状缺陷。
- 实际保留产物只读核查：使用现有 `ModelingWorkbenchService._handoff/_feedback` 投影公开交接与早期反馈；只输出字段形状/数量，未输出凭据、隐藏题/答案或原私有日志，未改源文件。

| 用例 | Round 1 状态及证据 | 未执行/缺口 |
| --- | --- | --- |
| T01 | PARTIAL：审阅 `App.tsx/ProjectWorkbenchPage.tsx` 及现有前端无 Ontology/四状态用例 | 真实页面及下一动作待稳定重启；fixture 的 host pending_work/next_action 不能证明生产接入，未结构化记录应保持未知 |
| T02 | PASS（有界）：独立 workbench tests 的 public sentinel/两 freeze 同题 ID 不释放另一版本私有答案；固定白名单及 no-store 路由审阅 | 浏览器实际响应/存储核查待 Round 2 |
| T03 | PARTIAL：真实地图 schema/候选修订及 modeled 未 apply 定向通过，七列/未登记前端实现审阅 | 重启页面交互待 Round 2 |
| T04 | PASS（有界）：resource-list 无 Class、多 Class、共享身份/保护过滤、Operation 精确 binding 和实际 RDF 模板通过；前端默认 GraphSet 按 workspace 身份选择 | 真实 HTTP/页面全字段与图核查待 Round 2 |
| T05 | PASS（有界）：Context Query 定向、两类游标/权限过滤及 RDF 查询通过；前端非首页上下文续页/compact/精确下钻实现及既有用例审阅 | 重启后实际接口/页面待 Round 2 |
| T06 | **FAIL D02**；报告适用性 drift/deleted/missing/tamper、public-regression 固定路径与原 full_pass 不重评定向通过 | 真实早期反馈第一故障内容被丢弃，见 D02；页面核查待修复 |
| T07 | **FAIL D01/D02**；运行/Session/宿主独立、配置/余额/分类时间限制和只读入口审阅 | 实际 handoff 已应用批次与 pending 专项状态丢失，见 D01；第一阻塞信息丢失，见 D02 |
| T08 | PASS（有界）：既有管理员 API tests 独立执行通过，组织/项目权限、角色/Grant、保护资源及普通 Key 拒绝已检查；前端一次明文/撤销/本地锁用例审阅 | 真实管理 HTTP roundtrip/页面待 Round 2 |
| T09 | PASS（有界）：旧 MCP 退役测试执行；REST/MCP/batch 删除 diff 和业务规则语义/SHACL/OWL/stub 警告实现审阅 | 重启实际 REST/完整页面无退役请求与保留能力待 Round 2 |
| T10 | **FAIL D01/D02**；独立 RUNNING 无 handoff/cleanup、嵌套历史绑定/冲突、普通 Key/跨项目/穿越/符号链接/只读源/hash、Runner create 实际身份及拓扑更新 tests 通过 | producer 的 list[object] 和 typed failure 实际形状未正确投影 |
| T11 | PARTIAL：只读反馈/报告/运行关联，无自动修复按钮/新占位页，隐藏诊断白名单审阅 | 真实反馈字段受 D02 影响，待修复/页面核查 |
| T12 | BLOCKED（本轮未执行）：主 Agent 全 pytest 尚在运行；等待稳定修复、required suites 与服务重启 | 服务/完整 Playwright/桌面小屏键盘及真实 REST 未执行，不标 PASS |

#### D01 — High：真实交接事实被标量白名单丢弃

- 复现：读取 `workspaces/modeling-runs/r4009-20261003-solmedium-auth01-start4c/acceptance-v3/production-handoff.json`，传给 `ModelingWorkbenchService._handoff`。
- 期望：保留实际已应用批次、未应用/未知写入和专项未完成状态，并使用封闭字段投影，页面可以区别交接与剩余验收工作。
- 实际：原 `applied_batches` 有 **63** 个对象，输出缺少 `applied_batches`；原 `joint_checklist.state=pending`，输出 `joint_checklist={}`。同一 scalar-list 白名单也会丢弃非空 `not_applied/unknown_writes` 对象列表。
- 代码证据：生产形状 `modeling_team/runner.py:7549`、`:7804`；读取 `backend/app/services/modeling_workbench.py:910`。当前 frontend fixture 用简化 bool/scalar，不能证明这一产物合同。
- 修复目标：按实际 producer schema 分别投影这些对象列表，并保留 `joint_checklist.state`；补实际 producer 形状测试。不得透传任意 JSON。

#### D02 — High：真实早期反馈只剩第一失败阶段，故障内容消失

- 复现：读取 `workspaces/modeling-runs/r4009-20261005-glmflashhigh-auth03-start1/early-feedback/*/feedback.json`（两份保留记录），传给 `ModelingWorkbenchService._feedback`；也可使用 producer 的 `first_failure={stage,failure:{status,reason}}` 形状确定性复现。
- 期望：保留获准的第一失败状态、原因/类型化阻塞层与代码及来源，不能让平台/运行时失败只剩阶段而失去归因；私有诊断及任意原日志仍须隔离。
- 实际：原 `first_failure` 包含 `failure/stage`，内层 `failure` 有 `reason/status`；输出仅 `{stage:checkpoint-binding}`。类型化 `blocked_layer/blocked_reason/evidence.reason_code` 的实际 producer 形状同样丢失。
- 代码证据：`modeling_team/__main__.py:1733` 的 `_cq_typed_failure`，`:3091`/`:3133` 的反馈生产；`backend/app/services/modeling_workbench.py:739` 只投影平铺 `stage/code/failure_layer`。
- 修复目标：按当前 typed failure schema 做安全字段投影并补测试；敏感内容不能以原始 failure 透传。

本轮建议：先由需求开发修复 D01/D02，稳定交接后在**同一计划 Round 2**复测失败项与必要相邻回归，补真实 HTTP、浏览器及重启证据。Round 1 FAIL 永久保留。

#### Round 1 补充核定（保持原基线，只读）

主 Agent 要求同轮统一核查真实 schema，进一步确认 **D03 High**；因此 T03/T10 为 **FAIL**，建议开发本次一并修复 D01/D02/D03。

- 定向启动前另一次组合命令在 `backend/` cwd 错用 `modeling_team/__main__.py` 路径，`rg` exit 2，后续 `pytest` 未启动；纠正后单独执行上述正式独立定向命令。该命令错误未计作测试 PASS。
- D03 复现：实际 `workspaces/modeling-runs/r4009-20261002-solmedium-auth01-start2/scenario-map/scenario-map.json` 的 `adjustments[].review` 含 `definition_ids/before_refs/after_refs/coverage/coverage_note/references/outcome/reason`，其中 `coverage=incomplete`、`outcome=pending`；调用现有 `scenario()` 后对应 adjustment 只剩 `change/approved_by_coordinator`，`review` 整块缺失。
- 期望：共享定义变更的实际前后修订、引用重审范围及 incomplete/pending 状态可读；不把未读全的依赖误称为完整。
- 证据：producer/schema `modeling_team/scenario_map.py:429` `_validate_review`；reader `backend/app/services/modeling_workbench.py:305` 的 adjustments scalar records；前端直接消费这一投影。实际源只读，没有改变地图或隐藏材料。
- 修复目标：沿当前 review schema 对定义/候选引用、coverage/outcome/reason 做固定字段投影，补实际 producer 形状回归；不要递归透传任意 JSON或隐藏诊断。

## 独立验收 Round 2（2026-10-07，修后稳定交接）

- 基线：仍为 `362b41e` 加已停写的 v4.1 工作树；D01/D02/D03 已修改 service/tests，前端修正没有权威来源的剩余工作/下一动作明确未知。未改变 producer、保留 run 或冻结材料。
- **D01 FIXED**：独立回放实际 start4c 生产交接，63 条 apply、1 条 not_applied、unknown_writes 及 `joint_checklist.state=pending` 正确保留；源 SHA 不变。
- **D03 FIXED**：独立回放实际 start2 地图，review 八字段含 incomplete/pending 原义完整保留；源 SHA 不变。
- **D02 FIXED**：独立回放实际 auth03-start1 两份 first_failure，状态和公开机器代码正确；未绑定公开冻结时自由文本不释放并有 `reason_detail_visibility`。初次回放把 early-feedback 的总文件数误断言为 2（目录另有成功 feedback）而失败；纠正为 first_failure 记录数 2 后通过，未改变产品或源文件。
- 独立定向复测：从 `backend/` 执行与 Round 1 正式定向相同的命令：**91 passed**，6.95s；`/tmp/v41-independent-round2-focused.log`。包含三缺陷真实 producer 形状和私有 sentinel 相邻回归。
- 主 Agent 交接证据：全后端 **1129 passed / 54 skipped**，281.50s，`/tmp/v41-backend-final-round2.log`；Team 未再修改代码，复用 **2468 passed / 8 skipped / 314 subtests**；前端 build 已通过。主 Agent 重启后 systemd active、8001 health ok、5173 HTTP 200；独立 live 在明确健康信号后执行。

### 独立真实 HTTP 与浏览器

- `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python /tmp/v41-independent-live.py --run`（backend cwd）：全步骤 PASS，`/tmp/v41-independent-round2-live.log`。使用唯一 `v41-independent-<uuid>` 项目、Ontology、用户、Key、受限 IRI、固定根 test-only artifact 目录；未调用 Runner/start/继续/修复或外部 SQL/API 业务执行。受保护 bootstrap Key 只进脚本内存，不输出。
- 真实 Oxigraph 验证：无 Class/多 Class resource-list、精确业务规则脚本文本；两主命中页/上下文游标归属、角色过滤仅主命中、变更查询拒绝游标；受限 IRI 不进入 list/context/detail，受限与不存在同为 404；成员/业务角色关联不自动获 Grant，显式角色 Grant/用户禁用/Key 撤销立即生效；组织/项目管理员与普通 Key/跨项目隔离；旧规则 REST 404/410、旧 rule Context 类型 422。
- 固定根 HTTP RUNNING fixture 无 handoff/cleanup 仍接入 public CQ/map；公开投影 sentinel 不返回，no-store，连续刷新源 SHA 不变；跨项目 run 为 404，普通 model Key 为 403。
- 实际保留 run 独立 HTTP 读取：`/tmp/v41-independent-round2-retained.log`。add03-start3 正式报告和 `public_regression_report` 都准确 **stale / live_model_binding_changed**，提示 sessions/full_pass 不在原 report digest，`full_pass_verification=recorded_only_not_rescored`；源 SHA 不变。start4c 绑定项目已删除，不伪装在线可恢复；start2/auth03-start1 缺绑定，不猜挂项目。
- `node /tmp/v41-independent-browser.cjs`：最终功能流程 PASS，`/tmp/v41-independent-round2-browser.log`。通过真实服务检查无 Ontology 四状态/未知、public CQ 冻结绑定、七列矩阵/未登记、精确规则脚本/关联图、compact→精确下钻、实际管理页面/防误操作锁、桌面/390px小屏/键盘；浏览只有 GET 与受治理只读 Context POST，无写请求、退役/建模请求，响应/存储不含 private sentinel 或 Key。
- 浏览器初次 selector 匹配同一说明的摘要和详情两处 strict error，收窄到 `scenario-cell-detail`；随后 Context 查询使用默认 5s 可见等待早于真实响应而失败，改为明确等待该 POST 返回 200 后通过。保留 `/tmp/v41-independent-round2-browser-attempt1.log` 至 `attempt4.log`，未靠修改产品或放宽目标掩盖。最终日志里的“GET-only navigation”应读为“GET + 受治理只读 Context POST”；断言准确禁止其他写请求。
- 实际截图已查看：`/tmp/v41-independent-empty-desktop.png`、`empty-mobile.png`、`model-desktop.png`、`model-mobile.png`、`access-desktop.png`、`access-mobile.png`（同前缀 `v41-independent-`）。没有仅凭“不横向溢出”判 UX 全体 PASS。
- 主 Agent 首次重启后完整 Playwright：**2 failed / 54 passed**，33.9s，`/tmp/v41-playwright-final.log`。两旧合同问题：全 Context blanket 禁止 graph_iri（获准图位置不属于退役 Evidence/lineage）；seed 的 alice/acme 未具 resource-list 所需 canonical entity 的 NamedIndividual + op:id。已交主 Agent 迁移测试；本记录保留失败，不算全套 PASS。

### D04 — High 候选：总览/模型详情没有按设计把完整技术结构置于次级

- 需求依据：R4.1-001 首页可理解的当前事实/成果/有效报告摘要、技术原始记录次级；R4.1-004 先业务含义、范围、关联及未知，再展开技术身份与图位置。设计明确“来源/时点/范围放摘要旁，技术信息用详情展开”；不只用原始结构替代阅读。
- 复现：项目 Overview 有地图/应用产物时四卡直接展开完整 `slices/field_states/field_sources/entries`，header 在四卡前展开 `state/platform_binding`；模型选择规则资源时定义详情先展示全部 `graphSetId/ontology_id/ontology_name`，随后才展示业务含义和脚本。
- 实际证据：`frontend/src/pages/ProjectWorkbenchPage.tsx` 的 `StateCards.summary/StateCards` 与 header `FieldTable`；`frontend/src/pages/SemanticModelPage.tsx` 的定义详情 `FieldTable(selectedRow.locations)` 位置；实际 `/tmp/v41-independent-model-desktop.png` 确认。
- 期望最小修复：首层仅真实事实摘要及来源，完整结构下钻折叠；Ontology 范围选择保留可读名称，技术位置在业务详情之后展开。不新增推导确认/验收结论、状态库或其他平台能力。
- 当前：已报告主 Agent，待严重程度/修复处置。因此 **Round 2 尚非整体 PASS**；三项原缺陷 FIXED 和上述有界成功不覆盖 D04/T12 完整 gate。

自有 live fixture 暂保留供修后页面复验，最终由独立测试方按唯一 manifest 清理；现有运行、项目和源材料未变更。

### Round 2 冻结结论

主 Agent 已接受 D04 为 **accepted-high**，交前端按上述最窄分层修复；因此独立 **Round 2 总体 FAIL**。D01/D02/D03 **FIXED**，真实 HTTP 与浏览器有界功能成功保持；D04 **STILL FAILING / 待修复**。完整 Playwright 的两旧测试合同已由开发迁移，定向 live 4 项通过；最后 UI 稳定后的完整套与重启页面复验尚未执行。下一轮复用本计划和唯一自有 fixture，核查摘要没有吞掉必要阅读字段，并由独立测试方最终清理。


## 独立验收 Round 3（2026-10-07，最终 UI 复验）

- 基线：`362b41e` 加最终停写 v4.1 工作树；本轮产品变更仅为 D04 前端信息分层及其两项前端测试；相关需求/接口/指南同步由主 Agent 完成。后端与 Team 的 Round 2 稳定代码未变，因此复用对应独立 91 项、真实 HTTP/实际保留产物及全套证据，不重复启动建模或重跑无变化的全套。
- 总体结论：**PASS（R4.1-001—011 与关联 R4.0-022 的独立功能验收）**。D01/D02/D03 维持 **FIXED**；D04 本轮 **FIXED**。没有 STILL FAILING、REGRESSION 或本次需求必需项 BLOCKED。
- 最终开发验证交接：前端 build PASS；`cd frontend && npx playwright test` **58 passed，44.1s**，`/tmp/v41-playwright-final-round3.log`。两项旧测试合同问题已迁移，D04 新增两项断言通过。后端 **1129 passed / 54 skipped**、Team **2468 passed / 8 skipped / 314 subtests** 仍适用于本轮未变代码；各套 skipped 没有当作执行或 PASS。
- 主 Agent 完成最终 `ontology-platform.service` 重启：is-active 为 active、8001 `/api/health` 为 ok、5173 HTTP 200。独立浏览器在明确健康信号后执行。最终六个文档链接检查、接口文档同步、相关文档 10 pytest 与 diff check PASS，由主 Agent记录。

### 实际复测步骤与 D04 证据

- 命令：`node /tmp/v41-independent-browser-round3.cjs`；**exit 0 / PASS**，`/tmp/v41-independent-round3-browser.log`。复用 Round 2 唯一自有 fixture 与真实本地服务，新的临时浏览器脚本只增加 D04 阅读断言，未修改产品代码或保留 run。
- Overview：四状态继续独立；场景地图先显示 **1 个切片 / 1 条视角记录**、原状态 active/modeled 和来源时点。完整 slices/scope/note 初始隐藏；在 390px 页面用键盘 Enter 展开后，Fixture slice、bounded test only、expression not application、active 全部可读。运行 `platform_binding` 初始折叠，展开可读原 project 身份。
- 模型详情：首层业务含义、适用范围、显式未知与完整只读规则脚本可见；DOM 顺序确认资源业务详情在读取位置前。GraphSet/Ontology 技术详情初始折叠，键盘展开后 `graphSetId/ontology_id/ontology_name` 均保留；没有以摘要删除必要字段。
- 实际截图已查看：`/tmp/v41-independent-round3-overview-desktop.png`、`/tmp/v41-independent-round3-overview-mobile.png`、`/tmp/v41-independent-round3-model-desktop.png`、`/tmp/v41-independent-round3-model-mobile.png`。分别核查事实摘要、技术信息次级、模型业务详情顺序及小屏阅读；未只凭无横向溢出判通过。
- 必要相邻回归：空项目四状态/剩余工作未知/下一动作未知、公开 CQ 版本冻结、七列矩阵和未登记、精确规则脚本及关联图、compact Context → 精确资源恢复脚本、管理页面本地锁、小屏与键盘、验收/运行页面只读成功。浏览器实际请求只有 GET 与受治理只读 Context POST；没有退役规则/建模/自动修复请求，响应与 local/sessionStorage 不含私有 sentinel 或 Key。Round 2 脚本和失败尝试、截图均保留。

### 最终逐项矩阵

下表将本轮实际复测与未变代码的有效证据合并；“复用”不是本轮重新执行。

| 用例 | Round 3 状态 | 已执行及证据 | 未执行或边界 |
| --- | --- | --- | --- |
| T01 / 001 | **PASS / D04 FIXED** | 本轮真实空项目、四状态、明确未知、摘要/来源/键盘展开；最终 Playwright T01 两项及导航相关回归通过 | 没有推断宿主未记录的剩余工作或下一动作 |
| T02 / 002 | **PASS** | 本轮公开 CQ/freeze 页面与网络/存储 sentinel 检查；复用 workbench 两 freeze 同题 ID 隔离、公开版本/覆盖/审核白名单测试；最终 T02 fixture通过 | 私有题/答案未阅读或导出 |
| T03 / 003 | **PASS / D03 FIXED** | 本轮实际矩阵 7 视角与 6 未登记、modeled 不等于 apply；摘要展开保留原切片范围/说明；复用实际 start2 review 八字段及 SHA、独立 producer 测试与最终 T03 fixture | 不用列表摘要把 incomplete/pending 重评为完整 |
| T04 / 004 | **PASS / D04 FIXED** | 本轮真实精确资源、业务含义/范围/未知/脚本与技术位置顺序、关联图；复用真实 RDF 七角色、无 Class/多 Class/同 IRI/精确 Operation 与隐私过滤；最终 T04 多位置、切视角、字段顺序/compact精确下钻测试 | SQL/API/脚本外部执行属于非目标，未执行 |
| T05 / 005 | **PASS** | 本轮真实 compact 查询及精确下钻；复用真实 HTTP 非首页命中/上下文游标归属、过滤、查询改变400与受限资源隔离；最终 T05 续页/重置/过期/省略测试通过 | 没有把 budget/compact 的显式部分结果视为完整 |
| T06 / 006 | **PASS / D02 FIXED** | 复用实际两份 first_failure 安全投影、真实正式/公开回归报告 stale/live_model_binding_changed 与 SHA、digest外full_pass仅记录；独立 drift/deleted/missing/tamper 和最终 T06 分母/诊断fixture通过；本轮验收页面无执行入口 | 未产生新的真实 L1/L2/L3 裁决；未知/失效不补为当前 PASS |
| T07 / 007 | **PASS / D01/D02 FIXED** | 复用实际63 apply/专项pending/unknown写入与第一阻塞记录、独立测试；本轮运行/宿主页面、剩余工作/动作未知、技术记录展开；最终 T07 配置/时间/恢复/交接fixture通过 | 没有启动、继续、恢复或修复任何被读取 run |
| T08 / 008 | **PASS** | 复用真实 HTTP 用户/状态/成员/角色/Grant/业务关联/保护资源/一次明文Key/撤销及普通Key/跨项目拒绝；本轮管理页与本地锁/小屏；最终 T08 全管理表单与授权fixture通过 | 本地锁只防当前浏览器误操作，未作为服务器权限替代 |
| T09 / 009/022 | **PASS** | 复用实际旧REST禁用/旧Context类型拒绝、独立旧MCP退役与全后端/Team删除执行分支证据；本轮脚本只读、无退役请求，保留 SHACL/OWL/查询及 stub 警示相关全套通过 | 未执行已退役规则，未称 stub 为真实 DL PASS |
| T10 / 010 | **PASS / D01/D02/D03 FIXED** | 复用真实固定根RUNNING无handoff接入、跨项目/普通Key拒绝与SHA；实际保留run drift/已删资源/无绑定分别表达；独立符号链接/穿越/两个freeze及Runner实际create身份/拓扑更新测试；本轮读页面无私有泄漏 | 没有猜挂历史项目；未修改保留源，也未新启真实建模 |
| T11 / 011 | **PASS** | 复用反馈/报告/运行只读关联与私有诊断隔离测试；本轮验收/运行页面无自动修复或执行请求；最终完整Playwright通过 | 没有加入自动修复产品流程或占位治理页 |
| T12 / 全部 | **PASS** | 最终build、58项Playwright、适用全后端与Team、文档/接口检查、重启健康；本轮真实1440px/390px/键盘及受影响REST/页面回归通过；最终自有资源清理并独立回读验证 | 各套明确 skipped 保留；真实新建模质量、可重复性及产品化不属于本次工作台功能验收 |

### 最终自有资源清理与核验

- 清理命令（backend cwd）：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python /tmp/v41-independent-live.py --cleanup`：**exit 0 / CLEANUP PASS**；`/tmp/v41-independent-round3-cleanup.log`。
- 限定 manifest 唯一前缀 `v41-independent-3f836aa834eb`，删除前验证自有项目/Key/User 名称及图/目录身份；未处理任何已有用户项目、运行或保留源。
- 再执行独立只读核验：两自有项目 HTTP404、三 Key 和一 User 数据库行不存在、所有自有图 ASK=false、唯一 test-only run 目录不存在：**exit 0 / CLEANUP VERIFIED**；`/tmp/v41-independent-round3-cleanup-verify.log`。manifest 和测试日志/截图保留供审计，无明文凭据。

本轮无新增产品缺陷，建议主 Agent 按最终功能 PASS 完成交付记录和提交，无需再次派开发修复。Round 1/2 FAIL、缺陷及失败尝试原样保留；本结论不覆盖或重写任何真实语义验收结果。
