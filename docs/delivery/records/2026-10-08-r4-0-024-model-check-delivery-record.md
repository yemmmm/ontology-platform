# R4.0-024 游离节点生产自查开发与测试

## 范围与结论边界

- 权威范围：[R4.0-024](../../requirements/requirements-v4.0.md#r40-024-建模完成后的模型检查首项游离节点)。
- 需求独立审阅：冻结提交 `b3676ef`，独立 plan_reviewer 返回需求 PASS，0 Critical／0 High，
  无待确认关键假设。本次不是详细设计独立审阅或功能／语义验收。
- 用户已授权开发与测试；D1 明确复用 Coordinator／Modeling／Protocol，不新增检查角色。
- 本轮不授予真实 semantic modeling start 或外部 SQL／API 调用；不改写已有 CQ PASS。
  开发侧功能与依赖验证、独立功能验收、真实生产角色效果分别记录。

## 最小实施方案与实际变更

1. 活跃 `r4-0-009-multiview-semantic-acceptance` Task 向三个生产角色挂载
   `r4-0-024-model-check-contract.json`，CQ／最终验收角色不接收此生产合同或自查材料。
   原 Profile、语义判断权、平台写权限和 CQ 冻结／隐藏隔离不变。
2. 使用已有 `semantic_sparql_query` 受治理只读入口，显式绑定实际 workspace 中的
   asserted_ontology／asserted_data 图。扫描使用固定四列 RDF 查询，按实际返回数推进
   OFFSET；服务继续控制结果上限并报告 truncated。终页后以 result_limit=1 重新读同一
   scope，核对各 Ontology 的 workspace_version／source_signature。无直接数据库读取、
   新公共路由或以推理 stub 消除候选的路径。
3. Protocol 的既有 stdio `protocol_mechanics` 增加 `inspect_model_associations`，同步
   facade、Runner manifest、Codex 实际目录校验及对应 fixtures。工具只消费原始
   `{request,response}`，识别入边／出边／谓词使用及正式结构引用；泛用词汇、元类型、
   自引用和任意描述／URL 不构成业务连接。它始终返回 `semantic_verdict=not_evaluated`，
   不执行任何写入，也不批准模型正确性或整轮完成。
4. 完整扫描用于当前获准全范围；增量 focus 只能使用当前真实新旧／共享定义身份，须
   覆盖受影响范围。扫描保留其他获准资源为关联端点，不自动清理无关历史模型。
   读取失败、错 scope、坏查询、缺页或漂移返回可恢复反馈；合法部分窗口仅报告未观察到
   关联，不能推导真实模型缺陷。受治理 SPARQL 拒绝某范围时保留 PARTIAL，不降低授权。
5. 三角色指令和 `ontology-modeling` 的 platform-flow 明确：初始工作安排包含检查；
   Protocol 提供实际读取和候选，Modeling 作有业务依据的逐项处置及完整修订，Coordinator
   维护 `/agent/work/scenario-map/model-check.json` 及既有进度。批准修复后走既有
   dry-run／apply／读回并复查受影响关联，整轮 terminal 前保持可协作。没有新增 Runner
   完成硬门、角色复活机制、固定修复次数、自动强连／删并或追溯包义务。

## 影响核对

GitNexus 文件限定的 `protocol_retrieval_mcp.py:handle` 影响 LOW；
`protocol_mechanics_contract` 为 LOW，`SAFE_PROTOCOL_TOOLS_R30002` 为 LOW。
早期同名 `_dispatch` 宽查询返回 CRITICAL，命中多个无关模块；已向用户说明并改用文件
限定查询。当前改动不修改那些分派路径。新扫描符号及 Codex 目录校验未被当前索引覆盖，
对应入口与 manifest／staged facade 使用直接调用点、diff 和实际 stdio 测试核对，
不宣称全图影响覆盖。

提交前 `detect_changes(scope="all")` 返回 HIGH：26 个索引符号、6 条受影响流程、
16 个已跟踪文件。已在提交前向用户说明。6 条流程均从 Protocol facade `handle`
进入既有 proof／citation／materialized quad／neutral candidate／formal envelope／term
binding 合同。实际 diff 只为该入口增加只读扫描分支与目录项，没有修改既有调用合同；
这些流程及 staged 初始化、tools/list、manifest、Codex 精确目录校验均在全量 Team
回归中通过。索引中的旧 fallback 符号因新增代码导致行号偏移，不代表它们实际被修改。

## 开发验证与失败保留

- 首轮新测试因尚未实现 `MODEL_CHECK_QUERY`／工具函数而 collection 失败，随后实现。
- 接入发现 Task 白名单不允许现有受治理 SPARQL 读工具：仅在 multi-slice 允许清单中
  补该工具，仍须 Task 显式选择；平台原有 scoped/read-only/authorization 校验继续生效。
- 009 旧合同测试要求与 012 的 sources/tools 完全相同，现改为只允许新增本条合同／读工具，
  保留其余 Profile、参数和输入基线对照；原失败保留。
- 首轮真实 Oxigraph 扫描与修复通过，清理后 `get_graph` 返回 404，而测试误期望 None；
  修正测试为 `graph_exists=false`，复验完成。仅创建／替换／删除唯一自有临时 named graph，
  未修改用户项目或已有模型。
- Native manifest／staged facade 用例按新增只读工具同步目录；一个排序断言首轮失败，
  纠正期望顺序后该定向组 97 passed、74 subtests passed。
- 新扫描用例当前 **20 passed**，包括真实 Oxigraph、实际 RDFLib/SPARQL 查询、501资源分页、
  入边／谓词／跨 Ontology、正式 JSON／歧义引用、部分读取／scope／漂移反馈、实际授权
  拒绝不泄漏、生产角色 source mount 和 native facade 可恢复输入错误。
- 首轮全量 Team 回归：6 failed、2484 passed、8 skipped、310 subtests passed。
  失败为 4 个 native 目录 fixture 与 2 个历史 tools 集合精确断言；只同步新增目录／
  显式受治理读能力，保留历史 Task 不自动广告该工具及其余隔离／权限断言。
- 最终全量（包括 opt-in 隔离真实 Oxigraph）：**2491 passed、8 skipped、
  314 subtests passed**，170.42 秒。49 个 warning 为 RDFLib 既有 default_context
  弃用提示。8 个跳过按原测试条件保留，不当作通过。
  命令：`cd backend && RUN_R4024_RDF_LIVE=1 env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`。
- ontology-modeling skill validator、改动 diff 格式及本地文档链接检查通过。
  Ruff 对本轮文件检查仍报告 7 个既有问题（facade／Runner 历史未使用导入或变量），
  经 HEAD 基线对照无新增问题；不将其表述为全量 lint PASS，不顺带修改历史代码。

## 未验证范围

本轮未执行独立功能验收、真实生产三角色的查找—判断—修复—复查或 CQ／L1／L2 验收。
真实 Oxigraph 用例使用受控测试 scope resolver，证明查询／分页／扫描／清理行为，
不宣称经过真实项目鉴权、业务建模或语义裁决。需求 A1／A8／A10 中的实际生产效果
仍需后续获准运行验证；prompt 与机械合同通过不替代这些证据。

未修改 backend／frontend 可执行代码或应用运行配置，不要求应用全量测试／服务重启。
新的 Task／角色合同和 staged mechanics 在后续授权启动中加载，不热更新已冻结的旧 run。
