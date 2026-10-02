# R4.0-009 多视角真实验收入口开发与测试记录

日期：2026-10-02。权威范围为 [R4.0-009](../../requirements/requirements-v4.0.md#r40-009-多视角真实建模与独立语义验收)
及已独立复审 PASS 的[详细设计](../designs/2026-10-02-r4-0-009-multiview-semantic-acceptance-design.md)。
开发起点 `f72f186`，工作树初始干净。用户授权按设计完成开发和测试；真实建模、业务资料／
访谈批准、冻结 CQ 审核、外部 SQL／API 与业务脚本执行仍按设计另行授权。

结论：D8／D9 功能实现与开发验证通过，009 核心段 Task 已准备。没有本轮实际 semantic start、
run ID、冻结题池或独立语义裁决；A1—A12 真实验收均未执行，009 整体保持 PARTIAL。
开发验证不代替独立功能验收，也不提供 L0 Runtime／L1 Modeling quality、L2 或 L3 结论。

## 实现与影响范围

- `platform-runtime-incomplete` 接受 `collaboration/routing`，无关响应／跨题回执错绑按
  路由取证未完成分类；模型知识不足仍只能配 `modeling-quality`。四态及其他合法组合保留，
  不改历史报告。活动 Judge、仍可加载的 v3 提示与 CQ reference 同步解释该组合。
- CQ child 只获准 `query_semantic_context`、`get_semantic_read_model`、
  `get_entity_statement_context`、`get_ontology_read_model`、`semantic_sparql_query`。
  交接 binding、packet 与 child schema 使用同一工具集合，各 Ontology 不允许不同工具范围。
- Host 前后状态观察仍使用 `get_ontology_workspace_context`；forwarder 要求 child 语义工具与
  host 状态工具的并集注册。状态响应仅提取既有模型／图状态摘要，不进入逐题响应证据。
  必要工具缺失仍阻断当前启动，并在异常链中标明缺失工具；四个已停用追溯工具不再成为启动依赖。
- child 越界工具在转发前拒绝，不生成成功 receipt。响应收集器同时核对本批工具范围与 CQ
  语义集合；Judge packet 拒绝生产／宿主／追溯工具响应，可信 digest 不能使旁路材料合法化。
  旧宽目录 handoff 返回 `cq_read_tools_unsupported`，要求新 handoff／attempt，旧产物不重写。
- [009 Task](../../../modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml)复用 012
  的角色、profile、全部来源、staged／unified／CQ／checkpoint 参数与追溯停用合同。
  仅明确核心段目标、获准访谈及映射未验边界，不加入预制业务答案、隐藏题或 tester-only 输入。

生产代码只修改 `modeling_team/`，未修改 backend／frontend、平台路由、资源 Schema、权限模型
或运行配置；不新增验收调度框架。因此本轮不适用 backend／frontend 全套检查与 systemd 重启。
现有 Codex runtime 已按 packet 传递工具目录，无需调整。

## 功能验证与测试轮次

本需求用例位于[009 合同测试](../../../modeling_team/tests/test_r4009_acceptance_contract.py)。
既有批次、响应／receipt／分页、恢复、生产交接和 checkpoint 仅验收接续覆盖纳入 Team 全量。
旧 v3 proxy 测试改用语义 read model，旧 R2.3 完整目录与单 Ontology workspace 读取测试保持原合同。

| 轮次 | 结果 | 原因及处置 |
| --- | --- | --- |
| 新合同首次收集 | 收集失败 | `_cq_read_tools` 尚未实现；随后修正测试 helper 导入名，不作为语义失败 |
| 新合同构建 Round 1 | 20 passed／21 failed | 测试自身误用 sink 字段、未补齐 proxy scope、用错 receipt 类型；真实 server 使用合成 Key 被 `MCP authentication failed` 拒绝。改为当前真实 `register_all` 目录的受控 stdio 服务，只测注册，不伪称通过实际 Key 认证 |
| 新合同构建 Round 2 | 23 passed／18 failed | 测试自身使用错误 receipt／sink 属性及二次 packet 构建未移除派生 bundle digest；修正 fixture |
| 新合同构建 Round 3 | 40 passed／1 failed | `build_batch_report` 不自带 `full_pass`；改为调用既有 `batch_report_is_full_pass` |
| CQ／恢复定向回归 | 151 passed／7 failed，22.21s | 一项上述报告断言，六项旧 v3 测试仍让 child 读 workspace 或未对齐 packet／binding。改用语义 read model，声明合法 `model_name` 与相同工具集合 |
| 新合同＋proxy 定向复核 | 63 passed，9.42s | D8 恢复／汇总、D9 packet／转发前拒绝、真实注册目录／必要工具缺失、可信 Brief 旁路、proxy／bridge 通过 |
| Team 全量 | 2095 passed／1 skipped／314 subtests passed，166.97s | `/tmp/r4009-team-tests.log`；包括控制 App Server、实际 CLI／Unix socket／MCP 链、前后状态漂移、逐题恢复、旧 attempt 留存及 checkpoint 接续。模型提供者为受控 fixture，不是真实语义运行 |
| 补充交接用例首轮 | 43 passed／2 failed | 新用例混用两个旧 fixture 的 run ID；改为复用同一生产交接 fixture |
| 最终 009 定向 | 45 passed，6.57s | `/tmp/r4009-new-contract-tests.log`；覆盖正常／checkpoint 输出目录、完整语义工具 binding／packet／schema 与旧交接原文不变。全量后仅补充测试 fixture，生产代码未变 |

执行命令（均在 `backend/`）：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short --disable-warnings
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4009_acceptance_contract.py -q --tb=short
```

真实注册验证直接调用当前 `app.mcp.tools.register_all`，并通过受控 FastMCP stdio 进程走实际
forwarder 注册检查；没有使用数据库中的 Key 认证或业务工具调用。缺失语义／host 状态工具时
启动失败，停用追溯工具缺席时可启动。受控 CLI 的宿主状态读取及 drift 检查不构成真实模型证据。
Brief 旁路反例具有真实重算 digest／receipt；收集器不给语义响应，Judge 不接收，批次不能 PASS。

## 来源准备、覆盖与未执行项

获准来源候选保持现有四份实验输入：[场景说明](../../evaluation-scenarios/industrial-service-v3/modeling-input/scenario-brief.md)、
[待访谈术语](../../evaluation-scenarios/industrial-service-v3/modeling-input/business-terms.md)、
[Schema](../../evaluation-scenarios/industrial-service-v3/modeling-input/schema.sql)、
[样例数据](../../evaluation-scenarios/industrial-service-v3/modeling-input/sample-data.sql)。
009 Task 不改旧 manifest 和历史快照；角色来源加载检查通过。

业务负责人尚未确认完整行为／分支／重复调用／循环合同、判断与推导规则及脚本、
业务职责与读取政策、一次共享含义修订案例、数据库映射含义和 API 样例。
这些是设计已披露的待确认资料，不从 Schema、公开设计例子或 tester-only 答案生成业务真值。
本轮没有替用户或业务负责人批准补充资料，也没有起草／冻结真实隐藏题。

| 条款／覆盖 | 本轮功能证据 | 真实证据状态与待办 |
| --- | --- | --- |
| A1／C10 | Task 复用获准来源候选与角色边界 | 未执行；补充资料、访谈、CQ 与有界覆盖待批准 |
| A2／C1 | 复用已有对象／分类能力 | 未执行；共享身份、同名异义、分类与局部限制待真实查询 |
| A3／C2 | 复用已有 Action／调用／绑定能力 | 未执行；重复调用及同类对象不同来源待业务合同和实际模型 |
| A4／C3 | 复用已有控制／值来源能力 | 未执行；正常、回退、条件输出、循环待获批实例 |
| A5／C4 | 语义 read model／完整定义工具可用于补读 | 未执行；脚本说明／正文／边界输入待确认及独立语义推演；无脚本执行 |
| A6／C5 | 复用 007 共享维护／引用重审 | 未执行；获准共享修订案例及生产期修订待运行 |
| A7／C6 | CLI、只读代理、响应／分页与恢复回归通过 | 未执行；跨视角业务链待真实 Examiner 读取与 Judge 裁决 |
| A8／C7 | child 取证范围隔离通过 | 未执行；同一真实模型的普通主体、授权／受限／不存在对照需独立专项 |
| A9／C8 | 明确第二段边界 | 未执行；010 交付后补数据库粒度／标识／编码等，数值证据另需 SQL 授权 |
| A10／C9 | 明确第二段边界 | 未执行；011 交付后补 API 获准请求／响应样例，未授权真实调用 |
| A11／C10 | D9 注册、子集、host 状态隔离、Judge 来源与 Brief 反例通过 | 未执行；真实无 Evidence 的生产／写入／回读／隐藏批次及独立裁决待授权 |
| A12／C10 | D8 错误组合拒绝、同题修正、继续后题、四态汇总与旧报告保留通过 | 未执行；真实失败归因及完整覆盖汇总待本轮 run／freeze／attempt 绑定 |

核心段范围为 A1—A8、A11—A12；映射段为 A9—A10，并补验变动核心语义。两段不能拼成未发生的
E2E 会话；缺口不删题、不缩分母。007／008 独立功能验收缺口仍保留，010／011 未交付，
相邻需求真实验收状态不因本次开发结果改变。

## 静态检查与工具限制

`git diff --check` 通过；本轮 Team 文件 Ruff 忽略基线已有 F402 后通过。
未忽略时唯一报错是 `acceptance_runtime.py` 原有 `for field` 遮蔽 `dataclasses.field`，
本轮未修改该循环，不顺带修复。新 Task 加载、CQ JSON 解析、实际角色提示与失败组合检查通过。
需求／设计／本记录的 107 个本地链接／锚点、Markdown 围栏及其余 11 条需求正文保持检查通过。

GitNexus 对 `build_platform_batch_packet` 的 upstream 分析为 LOW：直接调用
`_cq_execute_batch`，间接到普通 CQ CLI 与 checkpoint acceptance 接续。
需求中的历史函数名 `validate_v3_question_verdict` 未索引命中，实际当前入口为
`validate_acceptance_verdict`，已按直接引用核对 sink／packet／汇总调用。
`detect_changes` 报 CRITICAL，但把未修改的 `evidence_failures` 映射到大量不相干的后端／前端
流程；已向用户说明，以 focused call-site、diff 与 Team 回归代替，不声明完整图覆盖。
