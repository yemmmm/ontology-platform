# R4.0-003 可复用业务 Action 与外部能力关联：交付记录

- 权威范围：[v4.0 R4.0-003](../../requirements/requirements-v4.0.md#r40-003-可复用业务-action-与外部能力关联) F1—F6、D1—D4、A1—A9。
- 授权：本轮用户要求完成开发和测试；不包含 A10 真实建模、真实语义验收或外部业务调用。
- 当前结论：开发及开发验证完成，A1—A9 独立功能验收 PASS。A10 未授权、未执行，整体语义状态 PARTIAL。
- 开发起点 `d03443d`；期间其他会话提交了 R4.0-004 文档 `993efbe`，本轮保留其内容，不接管 004。

## 最小实现与复用边界

Action 和每个参数仍是普通 Entity；名称、业务含义及范围继承 `semantic_definition`。
新增 `action_definition` 的输入／输出状态与 `parameter_definition` 的结构化元数据，
各自保存为资源上的 JSON 字面量，支持省略保持、对象替换和 null 清除。未知字段或类型
返回字段可定位、可修正的 payload 错误，不新增表、路由或平台资源类型。

所有资源引用继续使用普通图关系。条件、效果、局部职责和外部能力关联使用独立语义节点，
以共同声明保留自然语言含义、适用范围、未知及冲突，并明确引用对象、Class、属性、规则、
参数或角色。共同条件与局部限制保留在图中，不实现条件覆盖、语义冲突裁决或执行许可判断。
结构化输出区分输入更新、新对象、计算值及未知；参数身份不等于实际对象不同。

中立候选和 unified 候选承接两个注释；Protocol 保留获准声明到实体命令。
新增中立 `operation` 定义和对它的 `definition_ref` 引用，沿用既有 Operation 编译、校验
和独立身份，目标 Class 在 Class 阶段之后绑定，能力在关联关系之前写入。没有调用任何
外部能力，不复制其执行风险、幂等性或凭证属性到 Action。

`entity-list`／`entity-detail` 和精确 resource 入口返回新注释；通用 statement 读取资源关系，
Class 拓扑与 Operation 定义沿用已有治理入口。引用不嵌入 JSON 元数据，复用端点过滤及
分页前授权过滤。条件／效果写入不推进业务状态，角色职责不产生 Grant，不新增追溯采集。
完整字段、更新语义和读取约定见 [API 合同](../../reference/api.md#r40-003-可复用-action-与业务参数)
与[中立候选合同](../../../modeling_team/references/platform-neutral-candidate-authoring.json)。

canonical 创建边界额外核对到：实体编译器拥有创建身份，调用方多余 `entity_iri` 不应单独
重定向注释。新注释和继承的 Entity 共同声明均采用编译产物的身份；回归证明实际实体、
Action 元数据和业务含义落在同一资源。未改变其他资源的身份合同。

## 开发验证

| 检查 | 最新有效结果与边界 |
| --- | --- |
| 后端全量 | `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short`：1028 PASS、38 既有 SKIP，119.85 秒；最终身份修复后执行 |
| Team 全量 | `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests --tb=short`：2030 PASS、1 既有 SKIP、314 subtests PASS，166.60 秒；最终 Entity 身份小修复前执行 |
| 最终受影响 Team 回归 | `test_r23002.py`、`test_r4002_semantic_definition_contract.py`、`test_r4003_action_contract.py`、`test_translate_candidate_to_batches.py`：58 PASS、18 subtests PASS；在最终修复后执行，其余 Team 输入不变，复用全量证据 |
| 初始相关组合 | Action、002、Operation、候选与合同回归：50 PASS、3 subtests PASS；后端新合同由最终全量覆盖 |
| 格式与合同 | 变更后端文件 Ruff PASS；JSON 解析、相应 Markdown 相对链接和 `git diff --check` PASS |
| 重启与运行健康 | 2026-10-01 18:18:05 +08 最终重启；systemd active，8001 `/api/health` 为 ok，5173 HTTP 200；用户总线环境见下文 |

测试中两处旧 Team 合同断言仍限定原命令集合，初轮全量得到 2 FAIL；按本次新增 Operation
合同更新预期后，上述完整重跑通过。最初两处开发断言使用错误的返回字段名，修正后相关
组合通过。身份修复期间主动中止旧输入的中间后端重跑，最终以 1028 PASS 的完整结果为准。
没有新增 skip／xfail 或缩减测试范围来隐藏失败。

运行 shell 缺少用户 systemd 环境，第一次 `systemctl --user` 只读检查返回
`Failed to connect to bus: No medium found`。核对 uid=1000 与既有 `/run/user/1000/bus` 后，
使用 `env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`
执行既有 unit 的 restart/status，无服务配置变更。启动期间健康重试有连接拒绝，最终两个
服务均已就绪；不将 systemd 刚进入 active 时的前端构建阶段误当作运行验证。

GitNexus 索引落后起点 63 个提交，`detect_changes(scope=all)` 初次给出 CRITICAL、267 个受影响
流程，提交前最终检测仍为 CRITICAL、200 个流程。结果将未修改的 `_COMPILERS`、`_inline_evidence`
等标为 changed；已向用户报告警告。
实际影响通过当前 diff、canonical／Batch／migration 编译调用点、Protocol 调用点及全量
回归核对，不声称完成当前图索引的准确影响覆盖，也未以陈旧结果推动重构。

## 独立功能验收与停止边界

独立测试者持有[唯一测试方案及逐轮记录](../test-plans/2026-10-01-r4-0-003-action-semantics-test-plan.md)，
以独立候选、断言及自有临时资源测试真实 HTTP／PostgreSQL／Oxigraph。开发自测不替代其结论。
最终 A1—A9 独立功能结论 PASS，无未解决产品缺陷。第 3 轮 249 项未受身份修复影响的
独立真实依赖断言与第 4 轮 41 项关联变更／授权断言均通过；第 4 轮另有 6 项独立 canonical
边界断言及 68 项有限相邻回归通过。所有轮次自有 Project、API key、Named Graph 清理并
核对不存在；原始 fixture 错误与逐轮证据保留在唯一测试记录中。A10 继续未授权、未执行。

同主语同谓词的 delete/create 同批次受既有 conflicting_item_effects 约束，本需求没有
要求单批次关联替换。独立测试按既有确定性合同先解除、再新增关联；中间零关联 Action
仍有效，不新增编排、能力选择或自动兼容判断。真实业务资料忠实度、建模质量和语义检索
质量留待用户统一授权的 A10，本记录不据预设 fixture 宣称真实语义 PASS。
