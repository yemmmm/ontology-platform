# R4.0-001 独立功能验收

最终结论：A1–A9 独立功能验收 PASS（Round 8）。后端 21 项独立测试、6 项候选门回归与前端 7 项浏览器测试通过；实际 REST、标准 MCP stdio 与 PostgreSQL 持久化/公开反馈适配器及 fixture 清理通过。A10 未授权／未执行，整体真实语义交付仍为 PARTIAL。

## 范围与通过标准

复用[权威需求 A1–A9](../../requirements/requirements-v4.0.md#r40-001-基于真实使用反馈的本体持续改进)及[实施设计](../designs/2026-10-12-r4-0-001-semantic-feedback-design.md)，不另设业务完成门。
验收 agent 仅修改本测试文档和 `backend/tests/test_semantic_feedback_independent.py`。
生产实现、前端实现由其他 agent 负责；不创建、继续、修复建模 run。

非目标：A10 真实反馈修模及独立语义验收；不以功能状态、模拟诊断或 apply 回执宣称模型质量 PASS。

环境：后端现有 `r008_client` 使用真实 main-app 身份与权限中间件、SQLite 关系持久化及独立 Session 读回；MCP 调用注册工具与真实 runtime policies，仅替换 DB resource factory。另在主 agent 完成迁移和重启后验证实际 PostgreSQL/runtime 路径。前端绑定行为复用前端 agent 的浏览器测试结果，并明确其证据来源。

| 用例 | 对应验收 | 步骤与期望结果 |
| --- | --- | --- |
| T1 | A1/A2 | 提交单/多 query、过滤、原分页、旧修订、空结果、降级与部分页；内部独立读取保持原话、快照、实际参数；不调用检索或改模型 |
| T2 | A2 | 缺快照可保存；UTF-8 JSON 超 256 KiB 返回 413 并提供可修正反馈；非法 query/标签/正文准确拒绝 |
| T3 | A3 | 同主体同 ID 同正文 REST/MCP 重交保持 ID/时间和单记录；异正文 409；跨主体重复 ID 不泄露原文 |
| T4 | A4 | 无 Team/run 创建情况下提交并独立 Session 读回；停止/退出不构成依赖；运行状态和模型修订不被改变 |
| T5 | A5 | read Key 经 REST/MCP submit；admin 经 list/get/resolution；相同内容及错误合同 |
| T6 | A6 | read 禁止内部读取/处理；项目管理员不能凭反馈 ID 跨项目 get/resolve；越项目提交/显式 Ontology 拒绝；受限快照不返回服务器受保护资源信息 |
| T7 | A7 | 追加 unresolved/needs_clarification 与诊断；原提交不改写；pending 包含无记录及最新未解决/待澄清；稳定分页无重复漏项 |
| T8 | A8/A9 | 029 仅导出显式选定反馈的公开投影，不含私有快照、主体或隐藏报告；不启动模型、不修改旧报告 |
| T9 | A9 | 缺真实验证/独立结论不得 resolved；仅自测不闭环；有结构化同范围模型状态引用可以记录，但不等于业务语义 PASS |
| T10 | A1/A2 | 浏览器测试：已返回结果冻结、编辑 query/切项目不混投、空结果/多页、草稿同 ID 重试及仅已保存提示 |

通过标准：A1–A9 所列功能及必要权限/持久化回归通过；失败或无法执行明确 FAIL/BLOCKED。真实语义 A10 单列未授权/未执行。

## 测试轮次

### Round 1 — 2026-10-12

- 代码版本：基线 `382968c5fdd5e7aefb9abe0bdace173928256d95`，本轮实现及测试为未提交工作区；其他 agent 的前端与生产修改仍进行中。
- 命令：`cd backend && uv run pytest tests/test_semantic_feedback_independent.py -q`。
- 实际结果：12 passed、3 failed，2.86 秒；覆盖 T1–T7/T9 的 REST/MCP/关系持久化、权限及错误场景。T8 生产反馈接线尚未完成，T10 浏览器证据及实际 PostgreSQL/runtime 重启待实现方通知。
- 结论：FAIL。三个失败中两个由同一产品缺陷引起；另一个为测试预期过窄。
- D1（Medium，A5）：MCP/REST 同回执 `received_at` 格式不一致。复现：read Key 经 MCP submit 后 REST 同 ID 同正文重试，或 admin REST/MCP list 同页。期望同回执、同内容合同；实际 REST `2026-10-12T15:05:17.297762`，MCP `2026-10-12 15:05:17.297762`。证据为 `test_mcp_submit_and_get_use_runtime_read_admin_and_shared_storage` 与 `test_pending_pagination_is_stable_including_latest_open_outcomes` 的输出。已报告主 agent，建议开发修复后复测。
- 测试修正：`test_internal_reads_require_admin_and_feedback_owner_scope` 原先仅期待 403，实际跨项目 GET 404 为防存在性泄漏的合理合同；改为允许 403/404，不计产品缺陷。未放宽内容不泄漏断言。
- A10：未授权／未执行，无真实建模、隐藏验收或语义质量结论。

### Round 2 — 2026-10-12，双端可选参数补验

- 工作区：同基线，实现方仍在修复 D1/接线；增加 T3/T5 的缺快照双端重试与 MCP resolution 用例。
- 命令：`cd backend && uv run pytest tests/test_semantic_feedback_independent.py -q -k 'optional_omission or mcp_resolution'`。
- 实际结果：1 passed、1 failed，0.48 秒；MCP admin 追加处理与 REST 共享读回 PASS，read 调用者禁止处理 PASS。
- D2（Medium，A3/A5）：REST/MCP 同输入的可选参数省略导致重复 ID 冲突。复现：REST submit 省略 `result_snapshot` 和 `snapshot_complete` 后，MCP 同参数同 ID 重交。期望返回原回执；实际 `feedback_identity_conflict`。证据为 `test_optional_omission_has_same_retry_identity_across_rest_mcp`；MCP wrapper 补 None/False，REST 保存省略字段。已报告主 agent，需共享身份比较修复后复测，原始提交仍应保持。
- 状态：FAIL；D1 待修复确认，T8/T10/真实 runtime 仍待通知。A10 未执行。

### Round 3 — 2026-10-12，修复及公开反馈适配器复测

- 工作区：同基线；实现方修复接收时间 ISO UTC 和同次 ID 默认参数比较，新增 029 默认 feedback adapter。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_semantic_feedback_independent.py -q`。
- 实际结果：19 passed，3.63 秒。D1/D2 FIXED；T1–T9 后端已覆盖的边界全部 PASS。新增 T8 使用真实 main-app GET，仅桥接 Host HTTP transport 与 bootstrap helper，确认投影保留原话与客户端观察免责声明，排除私有 snapshot/history，显式本体范围不能超本轮范围，成功/拒绝时均调用临时 Key 撤销。
- 结论：本轮后端独立功能 PASS；T8 默认 prepare 接线、T10 浏览器证据和实际 PostgreSQL/runtime 尚待最后验证。测试仅验证结构/权限/资源合同，不冒称引用文本或业务语义真实。
- A10：未授权／未执行。

### Round 4 — 2026-10-12，待处理筛选与默认 029 接线

- 工作区：同基线；测试增加闭环条目排除/全历史可读，以及 `prepare_incremental` 默认适配器的保存反馈读取。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_semantic_feedback_independent.py -q`；`uv run ruff check tests/test_semantic_feedback_independent.py`。
- 实际结果：20 passed，4.84 秒；Ruff PASS。T7 pending 筛选排除最新 no_change_needed、完整列表保留历史；T8 默认 prepare 只读取显式选中 ID、临时 Key 撤销、私有 snapshot/未选反馈不进入生产 source，返回 prepared 与 semantic_start=not_observed，未调用 launcher。
- 结论：已执行后端 A1–A9 功能范围 PASS，D1/D2 保持 FIXED；T10 浏览器及真实 PostgreSQL/runtime 待重启后完成。A10 未授权／未执行。

### Round 5 — 2026-10-12，最终输入校验回归及独立浏览器执行

- 工作区：同基线；实现方新增 finite JSON、query scope 结构、strict revision 校验及 REST 原 query 保留。前端明确 422/413 拒绝可纠正，未知提交保持原 body 重试。
- 独立命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_semantic_feedback_independent.py -q`；`cd frontend && npx playwright test tests/semantic-feedback.spec.ts`。
- 实际结果：后端 20 passed，4.19 秒；前端 7 passed，4.5 秒。浏览器测试文件由前端实现 agent 编写，本 agent 已阅读并独立执行其全部断言，未复制另套测试。后端身份权限使用真实 main-app/runtime；浏览器使用已有 mockWorkspace HTTP fixture，不冒称真实召回后端 E2E。
- T10 PASS：空结果、原话/scope、降级、断网原 ID/body 重试、多页实际请求/不同修订冻结、query/project 草稿隔离、UTF-8 超限禁止静默截断、422 改说明、413 显式省略快照后同 ID 重交。前端全量 52 passed/13.1 秒及 build PASS 为实现方提供的开发证据，另行区分。
- 结论：A1–A9 已执行受控独立功能 PASS，无未解决产品缺陷；真实 PostgreSQL/runtime smoke 等主 agent 迁移重启后完成。A10 未授权／未执行。

### Round 6 — 2026-10-12，Team 退出和候选闭门相邻回归

- 主 agent 要求补 T4：旧 Team stop、候选门 closed 时，反馈不依赖 modeling context，既有模型门不得被放开。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. SEMANTIC_JEV_ENABLED=false uv run pytest tests/test_semantic_feedback_independent.py tests/test_mcp_candidate_gate.py -q`；`uv run ruff check tests/test_semantic_feedback_independent.py`。
- 实际结果：27 passed，3.99 秒（21 本次独立反馈测试 + 6 既有候选门回归）；Ruff PASS。临时 JEV 测试开关只影响本测试进程，不修改本机运行配置；反馈测试不调用 JEV 或语义检索。
- T4 PASS：模拟 `_read_candidate_platform_gate` 的 closed/team_stopped 状态，仅替换建模门来源，不绕过主体或项目授权；submit/list/get/resolution 均可正常保存/读取，read 不能内部 get、跨项目 submit 仍拒绝，建模 context 读取未发生，`get_modeling_context` 仍返回 candidate_receipt_required 且 gate 保持 closed。
- 结论：本次独立功能及必要候选门回归 PASS；实际运行时待迁移重启。A10 未授权／未执行。

### Round 7 — 2026-10-12，真实 REST/MCP stdio/PostgreSQL 首轮

- 前置条件由主 agent 完成：`0036_semantic_feedback` 迁移、统一服务重启 active、后端 health 和前端 200；开发全量受控环境 `SEMANTIC_JEV_ENABLED=false uv run pytest` 为 1079 passed/56 skipped/276.74 秒，不修改生产配置。
- 步骤：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python` 内联执行独立 fixture。新建独立 Project/成员/read Key，真实 HTTP submit；用 `mcp.client.stdio.stdio_client` + `ClientSession` 启动 `backend/.venv/bin/python -m app.mcp.server`（cwd backend，Key 仅子进程环境，不输出），分别用 read/admin 标准传输调用反馈工具；独立 PostgreSQL Session 读回；真实 029 adapter 投影；删除 fixture。
- 实际结果：业务断言均通过，包括 read 同 ID 同正文跨 REST/stdio 原回执、缺省快照双端重试、read 禁止内部读取、admin get/resolution/list、REST 后续分页/处理读回、PostgreSQL 原话/空白 query/主体/历史单条持久化、无 BuildSession、公開投影无私有 snapshot/history、后端/前端 200。
- 测试脚本清理断言失败：先 DELETE Project 后对已被该 API 删除的 project-bound read Key 再次 `assert revoke(kid)`，返回 false，不是产品错误。独立检查确认 fixture Project 与反馈不存在；已明确撤销唯一剩余 bootstrap admin Key `0bca7c10-d994-48dc-84e3-822fd866cb7b`，adapter 临时 Key `61ceb038-17aa-49db-9111-e29cc8f23851` 已在 finally 撤销。无残留测试项目/反馈/有效临时 Key。
- 结论：功能断言 PASS、测试脚本清理预期需修正。下一轮调整撤销顺序并保存最终可读 runtime 回执。A10 未授权／未执行。

### Round 8 — 2026-10-12，真实 runtime 最终复核与清理 PASS

- 环境与命令：同 Round 7 已迁移重启的实际服务；`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python` 内联 stdio/PostgreSQL fixture，先撤销 read Key 再 DELETE Project，最后撤销 bootstrap admin。
- 测试资源：Project `ba2ad78c-e116-4ef4-9705-dad5fffaf075`；feedback `3f9e34ee-5eb5-43e6-9417-767039517590`。
- 实际回执：`{"feedback_id":"3f9e34ee-5eb5-43e6-9417-767039517590","received_at":"2026-10-12T15:25:58.663726+00:00","status":"received"}`；REST/标准 MCP stdio 重试完全相同。
- 独立结果：PASS，exit 0。read REST submit 与 stdio submit 原回执；stdio read 内部 get 拒绝；stdio admin get/resolution/list 与 REST 追加历史一致；独立 PostgreSQL Session 校验原话、raw queries 空白、服务器提交主体、单记录与追加历史；本 fixture 未生成 BuildSession；真实 029 adapter 只返回 public projection，private snapshot/history 未外流；后端 health 与前端均 HTTP 200。
- 真实传输边界：`StdioServerParameters(command=backend/.venv/bin/python,args=['-m','app.mcp.server'],cwd=backend,env=...)`，read/admin 各自初始化 `ClientSession` 后 `call_tool`，没有 monkeypatch 身份/授权/resource factory，没有绕过服务端启动认证。密钥未输出。
- 清理 PASS：只删除本轮 fixture Project/反馈；已从独立 DB Session 确认 Project 不存在、反馈计数为 0、admin revoked、read Key 不存在或 revoked；029 adapter 临时 Key 由其 finally 撤销。首轮清理断言问题 FIXED。
- 最终结论：A1–A9 独立功能 PASS，无未解决产品缺陷。A10 未授权／未执行，无 semantic modeling start、真实反馈修模效果或隐藏验收结论。
