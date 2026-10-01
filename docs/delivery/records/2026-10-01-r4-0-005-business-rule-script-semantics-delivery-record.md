# R4.0-005 业务规则分类与脚本语义：交付记录

- 权威范围：[v4.0 R4.0-005](../../requirements/requirements-v4.0.md#r40-005-业务规则分类与脚本语义)，[已确认设计](../designs/2026-10-01-r4-0-005-business-rule-script-semantics-design.md)。
- 用户授权：按设计完成开发和测试。使用 `requirement-delivery` 标准交付，按设计 §8 分开记录开发验证、独立功能测试与后续真实语义验收。
- 开发基线：`3537d3d`；开始时工作区干净。本轮拥有产品增量、开发测试、合同／API 文档、需求状态及本记录；独立测试者拥有[唯一测试文档](../test-plans/2026-10-01-r4-0-005-business-rule-script-semantics-test-plan.md)及自有临时探针。
- A11 真实建模、独立资料语义验收未授权，不启动 semantic modeling start，不消费真实建模额度。不执行业务脚本／外部调用，D2 自动派生物化能力仍未交付。

## 实现及合同

规则是普通 Entity，沿用 `semantic_definition` 中的身份、说明、范围、未知和已知冲突。
新增 `rule_definition` 保存两类规则、逐条语言／版本／正文、外部 Consumer 执行约定、
输入／输出状态、缺失策略及共同变更说明。编译为同一实体上的 `op:ruleDefinition` JSON
字面量；复用 Entity 注解写入，不新增表、资源类型、规则专用 API 或执行器。

注解沿用 003 的省略／对象替换／null 清除约定。字段类型、枚举、非空文本和未知字段接受
确定性校验；字段可省略，文本可 null 表示未知，部分声明可保存而不宣称完整或可执行。
执行环境为文本，共同说明外部环境、绑定、输出、失败和副作用约定。平台不判断阈值、
同类对象错绑、文本冲突或敏感信息；已知冲突仍由共同声明保留，独立语义判断留待 A11。

输入／输出复用原 003 参数合同，不扩展 `parameter_definition`。005 使用原 004 的五类
`sourceKind` 和普通参数／值／对象／调用／迭代关系；条件及结果身份／有效范围也为普通
定义和边，不藏引用、不保存业务行、实参、运行状态或凭证。关联 Action 不代表动作发生。
Shape、OWL、平台 Rule Run／`rule-result` 与外部判断保持分层，自动新知识物化不在本期。

Protocol 中立候选复制 `semantic.rule_definition`，非实体注解反馈 item／字段错误。
Unified 候选扩展同名可选字段，更新仍由原批准物化计划／授权身份绑定承接，不新增中立
更新语法。Batch 的 create/update Entity payload 白名单和活动接口合同同时放行注解，
经过 `_compile`／`prepare` 校验再写入。实体 list/detail 的 `detail_fields` 和精确 resource
的 `properties` 等价读回，普通关系沿用端点授权及分页前过滤。
Modeling／Protocol 活跃指令和两份挂载 reference 同步，API 字段约定见
[接口文档](../../reference/api.md#r40-005-业务规则与脚本声明)。不增加证据／追溯职责。

## 开发验证

- 相关后端回归：005／003／004／002，42 PASS（13.91 秒）。首轮一个开发断言误用 `outputs`，改为既有 `resource_outputs` 后通过；无产品故障或新增 skip。
- Team 相关合同回归：13 PASS／3 subtests PASS（0.18 秒，包含一项被导入而收集的既有测试）；随后将该导入改为非 test 别名避免重复收集，完整 Team 套件覆盖最终输入。
- 新增后端测试覆盖两类／两种语言、同名规则独立说明、冲突保留、来源关系、部分状态、字段错误修复、替换／清除、Protocol 实体目标和引用错误、完整 Batch service 的创建／更新／apply、受治理读回及分页前过滤。Batch service 使用既有测试依赖；真实 PostgreSQL／Oxigraph／HTTP 证据由独立测试提供。
- 变更后端文件及新测试 Ruff PASS；JSON 解析、API 链接／围栏和 `git diff --check` PASS。
- 后端全量：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short`，1053 PASS／38 既有 SKIP（115.55 秒），日志 `/tmp/r4005-backend-full.log`。覆盖当前产品实现；后续仅修改旧 Team 合同断言和文档，不重复后端全量。
- Team 初轮全量：2032 PASS／1 FAIL／1 既有 SKIP／314 subtests PASS（147.93 秒）；唯一失败是 002 的旧 `item_optional_fields` 清单未包含新增合法 `rule_definition`。仅同步预期，002＋005 相关 5 PASS（0.10 秒），最终 Team 全量：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests --tb=short`，2033 PASS／1 既有 SKIP／314 subtests PASS（169.56 秒），日志 `/tmp/r4005-team-full-final.log`。
- 服务按要求于 2026-10-01 20:11:42 +08 重启，使用已验证的 uid=1000 用户总线环境 `XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`，unit active；启动脚本完成既有 frontend build。就绪后 `/api/health` 为 `{"status":"ok"}`、5173 HTTP 200。无前端源码变更，不额外运行 Playwright。

GitNexus 对 `translate_candidate_to_batches` upstream 分析为 LOW，直接调用者为
`protocol_retrieval_mcp.handle`，间接为 `main`。当前索引不能定位 `compile_command` 和
`_compile_action_annotation`，改用当前编译器、canonical write 和 Batch prepare 调用点检查。
`detect_changes(scope=all)` 报 CRITICAL／267 flows，但将未修改的 `ModelingWriteEffect`
字段和 `UNIFIED_APPROVALS_FIELDS` 标为 changed；已向用户警告。实际 diff 未改变上述字段，
因此不声称准确的图影响覆盖；使用当前 diff、全量回归及独立真实依赖验证。

## 独立功能与完成边界

独立测试者使用自建档案移交场景、规则和业务断言，验证 A1—A10 的机械／功能范围。
A3、A4、A9 分别验证身份、冲突内容保留和授权，不凭 fixture 宣称真实对象／阈值语义正确
或自动自由文本敏感保护。完整测试轮次与资源清理记录在唯一测试文档。
第 4 轮 T1—T6 与第 5 轮 T7／T8 已全部通过，独立功能结论 PASS。A11 留待后续统一授权，
整体真实语义状态为 PARTIAL。

### 独立功能结果与交付收尾

- 第 4 轮：369 项成功断言，T1—T6 完成。完整候选／回执／Protocol 创建，unified 批准物化计划更新，真实 Batch `_compile`／`prepare`／dry-run／apply_atomic／幂等及 list/detail/exact/export 读回均通过；注解省略保持、null 清除、恢复通过。18 项非法创建／更新反例及未知／覆盖字段被拒绝，内容与 workspace version 不变，引用错误修正后同一 BuildSession／目标可继续。
- 第 5 轮：只补剩余 T7／T8，41 项断言 PASS。资源／关系／statement 与公开基线的授权子图逐项相等；隐藏与不存在同 reader／同 IRI 精确响应相同，过滤先于 limit／计数。entity-list 42→39、entity-relations 45→15、statement-list 239→194；实际首行和 count、export、正文隐藏、role mounted 输入均有原始证据。
- 测试轮次 1—4 的输入解包、update 字段、请求前置敏感字段与 IRI 前缀比较错误全部修正；未修改产品或新增 skip／xfail，未以后一轮成功覆盖原错误。当前产品缺陷 0，独立功能 PASS；无需追加产品修复或新功能测试。
- 原始日志 `/tmp/r4005-independent-round4.log`、`/tmp/r4005-independent-round5-governance.log`；JSON `/tmp/r4005-independent-result-r4005-d437f809d69c46a7b9698d161adae18c.json`、`/tmp/r4005-independent-result-r4005-99c1b3db0a904dab8403e1ea90b85af8.json`。所有轮次自有 Project／Ontology／API key／graph-set／registry／graph-state／revision／Named Graph 清理并核对不存在，第 5 轮 `result=PASS`／`cleanup=true`。
- 暂存后 GitNexus 检测仍为上述陈旧映射的 CRITICAL／267 flows，实际产品 diff 与已验证输入相同。变更检查与当前回归证据的边界已披露，不宣称准确的图覆盖。
- 并行 R4.0-006 需求／设计提交 `273bc83` 只修改文档，保留其内容，不纳入 005 实现；未改变冻结产品／角色输入，不重复功能验证。005 需求状态、设计实施结果和本记录已同步。
- 授权范围内开发与独立功能测试完成。平台不执行脚本，自动派生物化未交付；A11 未授权／未执行，整体 PARTIAL。提交仅包含本条和相关合同／回归测试；通过 `git log -- 本记录路径` 可追踪交付提交。
