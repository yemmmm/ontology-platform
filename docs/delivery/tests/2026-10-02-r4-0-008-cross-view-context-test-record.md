# R4.0-008 跨视角 Context Query 开发与测试记录

日期：2026-10-02。权威范围为 [R4.0-008](../../requirements/requirements-v4.0.md#r40-008-跨视角语义检索与上下文组织)
及已独立复审 PASS 的[详细设计](../designs/2026-10-02-r4-0-008-cross-view-context-design.md)。
开发起点 `afd239a`，工作树初始干净。用户授权按设计完成开发和测试；本轮没有真实建模、
业务脚本执行、外部数据库业务查询或外部 API 调用授权。

结论：功能实现、最终后端全量回归及重启后隔离数据的真实依赖验证通过。这里记录的是开发验证，
不是独立功能验收或 A10 真实语义验收。整体状态保持 PARTIAL。

## 实现范围

- REST、MCP、能力目录和实际 Modeling Team 读取代理共同支持 `semantic_roles`。
  trim／去重后按声明字符串精确匹配，只筛主命中；角色不成为新的资源 kind。
- 主命中与关联资源读取已有 semantic／action／parameter／rule 注解；异常或多值定义
  显式诊断，不猜测业务内容。compact 保留身份、语义及未知／冲突，省略关联规则正文并标明投影；
  原始注解 fact 同样省略正文，主命中仍保持 full。
- 双向遍历现有明确关系，支持 depth 0—3、跨获准 Ontology、多根和环；
  使用 Ontology／kind／IRI 完整身份，调用和绑定不会因同名而合并。
  授权在推进 frontier 之前完成，输出 kind 过滤不阻断获准中间关系。
- RDF 与向量按稳定顺序分块补读，完整注解与原始向量文档先授权、再筛选计额；
  隐藏或非目标候选不占用合格窗口，不产生隐藏存在性提示。
- 共享有界展开预算与最终页大小分离，返回 complete／partial／not_requested；
  合格候选窗口超限与上下文展开 partial 分别表达。context cursor 恢复产生它的原匹配页，
  再续读上下文，并保留进入下一匹配页的游标。
- 已有 mapping、metric、Operation 使用原合同投影，不新增工单等领域生产代码；
  Protocol 冻结可选角色，partial 提供可恢复反馈，Consumer／Examiner 说明同步读取边界。
  正常读取不依赖 Evidence／lineage，也不增加执行能力。

## A1—A9 开发验证覆盖

主要用例在 [Context Query 测试](../../../backend/tests/test_r4008_context_query.py)、
[向量补读测试](../../../backend/tests/test_r4008_vector_recall.py)、
[运行依赖测试](../../../backend/tests/test_r4008_live_context.py)与
[Team 合同测试](../../../modeling_team/tests/test_r4008_context_contract.py)。
既有 Context Query、cursor、API、MCP、保护集测试纳入后端全量回归。

| 条款 | 开发验证内容与边界 |
| --- | --- |
| A1 | 明确／缺失角色、大小写、多值 OR、非 Class 节点、词法／向量原始块被隐藏或非目标角色占满后继续读；按完整身份去重 |
| A2 | 共享 Action 的不同调用／绑定、参数、方向、typed literal；full／compact 保持身份和已保存语义 |
| A3 | 双向边、跨 Ontology 可见／受限定义、fact-only 遍历、深度、环与重叠根；生产代码不解释业务谓词 |
| A4 | 注解结构化读回、未知／冲突、非法 JSON、多值及不同 RDF term 的歧义；compact 正文无原始 literal 旁路，full 精确锚点可补读 |
| A5 | 隐藏桥接节点、嵌套脚本 IRI、原始向量 mapping evidence 引用；当前保护集变化及隐藏集合变化的响应／游标边界 |
| A6 | 不同页大小全页集合相同，多页生产器、可见候选超窗、展开 partial、未请求展开；三页主命中中第二页单独用 context cursor 续读 |
| A7 | 角色／主体／源版本绑定与当前保护成员校验，末尾范围重检；复用既有 cursor／授权回归，不保留旧权限来继续旧页 |
| A8 | 普通非工单业务 fixture 与既有 mapping、metric、Operation 关联投影；不执行业务 SQL 或 API，不声明 010／011 交付 |
| A9 | REST／MCP／能力目录与活动读取适配参数一致；依赖错误传播，不伪装完整空结果；partial 不当作完整，追溯停用合同纳入回归 |

测试 fixture 能验证平台合同和既有值的读回，不能证明实际业务建模质量、语义答案正确率，
也不能证明说明与脚本在所有业务输入上的语义一致性。

## 测试轮次与结果

| 轮次 | 结果 | 修复／证据 |
| --- | --- | --- |
| 初次后端全量 | 1102 passed，39 skipped，4 failed | 3 项接口文档同步失败及 1 项范围重复解析合同失败；同步文档，将末尾检查限制到已准备的 Ontology，不再次全范围 resolve |
| 第二次后端全量 | 1107 passed，41 skipped | 全量通过；随后定向核对发现 RDF term 歧义判断及空命中末尾范围重检两处缺口，局部修复后 21 项定向用例通过 |
| 最终后端全量 | 1108 passed，41 skipped，244.15s | `/tmp/r4008-backend-pytest-closure.log`；7632 warnings，未将 skipped 或 warnings 当作新增验收证据 |
| Modeling Team 合同 | 64 passed | 角色冻结／代理／消费、既有 protocol、acceptance 与 runtime 定向套件 |
| Lean runtime 适配 | 39 passed，11 subtests passed | 更新旧的 depth=2 拒绝断言；验证 depth 0／2／3、mapping 与角色透传，保留 depth=4 拒绝 |
| 真实 PostgreSQL 向量 SQL | 1 passed | 实际 pgvector、等距离结果与 IRI 稳定续页，3／3／1 无遗漏；临时表事务回滚 |
| 重启后真实 REST／Oxigraph／PostgreSQL | 2 passed，3 warnings，7.56s | `/tmp/r4008-live-pytest-closure.log`；包含实际 pgvector 续页与 REST Context Query、compact、第二匹配页上下文及第三匹配页；查询后精确清理并断言无残留 |

后端全量命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings`。
真实依赖命令：`cd backend && env ONTOLOGY_LIVE_CONTEXT_TEST=1 uv run pytest tests/test_r4008_live_context.py -q --tb=short --disable-warnings`。
运行依赖测试默认 skip，必须显式启用；全量的 skipped 不算这些运行合同的 PASS。
运行测试前两轮各为 1 passed／1 failed，失败分别发生于 fixture 创建 Key：
`unbound API keys must include admin`、`user_id must be a member of the selected Project`。
将 read Key 绑定隔离 Project 并加入对应用户成员后通过；失败轮亦执行 cleanup 并断言无残留。
这两处只修改 opt-in fixture 初始化，运行产品代码未变；最终启用的 2 项用例验证修正后的测试。

## 静态检查、影响分析与运行状态

新增测试及本轮 backend 文件 Ruff 通过，`git diff --check` 通过。
Team Ruff 有一项基线已存在的 F402：`acceptance_runtime.py` 中循环变量 `field` 遮蔽
`dataclasses.field`；该处未修改，没有顺带修复。Team 本轮文件忽略这一个基线错误后 Ruff 通过。

GitNexus 的共享向量候选函数影响分析给出 CRITICAL，已在改动前说明共用调用影响；
`detect_changes` 输出存在损坏标识和明显不可信的流程关联，本轮不把它作为图覆盖证据。
使用实际调用点检查、diff、全量后端及相关 Team 测试验证共用接口兼容性，
未为本需求修复或重建 GitNexus 索引。

接口目录同步检查 `backend/.venv/bin/python scripts/sync-interface-docs.py --check` 通过。
需求、设计、测试记录及 REST／MCP 文档共 5 份文档的 104 个本地链接／锚点与围栏检查通过。
使用系统 Python 时缺少 FastAPI，改用已有 backend 虚拟环境，没有安装或更改依赖。

2026-10-02 13:40:27 +08 重启 `ontology-platform.service`；启动脚本构建前端期间首次端点
连接失败，13:40:44 启动完成后 user systemd 为 active，backend `/api/health` 返回
`{"status":"ok"}`，frontend `5173/` 返回 HTTP 200，受影响 Context Query 在上述真实依赖测试中
返回 HTTP 200。没有前端代码变更，不额外运行 UI Playwright 套件。
当前环境调用 user systemd 需明确
`XDG_RUNTIME_DIR=/run/user/1000`、`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`；
未设置时 `systemctl --user` 报 `Failed to connect to bus: No medium found`。

## 完成边界

本轮交付平台功能和开发证据，没有独立验收方参与测试生产或语义评判。
独立功能验收尚未执行；A10 随 R4.0-009 后续统一真实建模授权开展，未授权、未执行。
不以 fixture、运行端点通过、方案审阅 PASS 或本记录替代真实独立语义验收；整体 PARTIAL。
