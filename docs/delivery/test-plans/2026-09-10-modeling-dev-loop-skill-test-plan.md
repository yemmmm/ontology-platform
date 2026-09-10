# modeling-dev-loop Skill 交付与验证记录

日期：2026-09-10。范围：仓库内新建开发推进 Skill，核查现有建模 Skill 的存废。
权威目标：用户本轮批准的设计，以及以下两项修订：符合 AGENTS.md、有充分把握收益明确且
无可预见负面影响的设计变化可自主决定；每次额度耗尽后先清楚整理进展、问题、修改再申请。
本交付不授权真实 semantic modeling start、真实 Claude Code 修复、platform apply 或 SQL 验收。

## 1. 旧 Skill 核查

结论：`skills/ontology-modeling/` 仍有效，保留；没有清理条件成立。

- [Modeling package](../../../modeling_team/agent-packages/modeling/package.yaml) 的
  `required_skills` 直接指向该 Skill；当前
  [v3 Profile](../../../modeling_team/profiles/r3-0-011-competency-question.yaml) 使用此 package。
- [Runner](../../../modeling_team/runner.py) 将必需 Skill 纳入基线；
  [Codex Runtime](../../../modeling_team/runtimes/codex.py) 的 `_stage_skills` 将其目录复制到
  角色隔离环境。它不是仅剩文档链接的旧文件。
- `.agents/skills/ontology-modeling` 是现有规范目录的相对符号链接。
- 最近更新为 `8f62a11`（2026-09-08）；其 Team Profile 边界明确把平台调用交给 Protocol，
  没有另起旧 Harness。角色指令及版本化 Task 补充具体执行合同，不替代共享建模方法。
- [废弃清单](../../../skills/ontology-modeling/references/deprecated-artifacts.md) 标记的是
  `ontology-builder` 等更早资源；本次不扩大为清理这些历史证据。
- `modeling_team/foreground_monitor.py` 的 `ARCHIVAL_ONLY = True`：新 Skill 不使用此旧 P2 启动器。

已执行：官方 `quick_validate.py skills/ontology-modeling` → `Skill is valid!`；
`python3 skills/ontology-modeling/evals/validate_skill.py` → validation passed；
`uv run --project backend python -m modeling_team validate --profile
modeling_team/profiles/r3-0-011-competency-question.yaml --task
modeling_team/tasks/r3-0-006-real-full.yaml` → exit 0，正确加载四个角色。

## 2. 新 Skill 验证范围

只做格式、路径、现有命令合同检查与独立情境应用。情境测试不启动真实 Agent runtime，不访问
隐藏业务答案，不写平台；不把文档检查或纸面行为测试报告为 L0 Runtime/L1 Modeling quality PASS。

| 情境 | 输入 | 检查结果要求 |
| --- | --- | --- |
| S1 启动与恢复 | 完整 v3，剩 1 次 start；仅记得旧 Task；挂载修复只对新子进程生效 | 找到完整 task/profile、实际观察与输入通道；不猜 status/resume 命令；核实生效和写状态后决定恢复，fresh start 计数 |
| S2 额度与不确定写 | 3 次用尽；前两轮零写失败，第三轮 apply 响应超时；开发单测通过 | 保留首阻塞与三轮证据，先查写状态；不给退款、不擅自启动；面向用户讲清进展、问题、修复验证及缺口、下轮计划 |
| S3 等待与空转 | CQ 审核 8 分钟无新日志；另一角色每分钟重复同一失败 | 区分合法等待与无有效进展，前者交用户审核，后者有界诊断；不按时间杀 run、不代答、不重放写入 |
| S4 自主设计与升级 | 有证据的可恢复反馈设计；另一个提议改变题池以提升通过率 | 前者完成 T0 与影响判断后可自主留痕推进；后者不能因高信心越过来源、隔离和验收边界 |
| S5 外部修复交接 | Claude Code 可高权限修复平台；共享目录有用户改动；修复涉及服务重启 | 任务含责任范围、复现、证据与验证；保持主控可观察；守护当前写入；不暴露隐藏答案，不以退出码代替验证 |
| S6 已知答案与独立性 | 需要业务澄清；验收者已参与当前修复；本轮只完成 L0 | 复用已确认答案，未确认项交用户；使用新的独立验收者；不拿机械或 L0 成功宣布 L1，后阶段不前置 |

基线 S1/S2 在新 Skill 编写前启动，由独立 Agent 只读执行；用户要求继续后开始编写，基线
报告在编写期间返回。本轮不声称严格的先 RED 后 GREEN 实验。初稿后交新的独立 Agent 使用新 Skill
处理同一 S1/S2 及 S3～S6；只提供情境输入，不提供预期答案或基线结论。
发现有证据的缺口才修订并复测变更面，不为构造失败而增加测试轮次。

## 3. 执行记录

### 基线情境应用

执行者 `/root/skill_baseline`（未提供新 Skill、预期答案或其他 Agent 历史）。S1 找到了正确
完整 Task/Profile 和 FIFO，并识别修复不自动进入旧 child；没有虚构顶层 status/resume 命令。
S2 保留额度耗尽与不确定写入边界，但要求用户“先允许只读核对第三轮写入状态”，这属于本来
已经授权、应自主进行的必要只读核查。用户说明还省略了已完成五切片访谈的正向进展、有效耗时
及清晰的逐轮修改/验证区分。实际原句：“请先允许只读核对第三轮写入状态，并完成挂载/传输修复
的独立真实复核；状态安全后再授权追加 3 次 fresh starts。”

新 Skill 明确复用授权并先完成安全核查；进展模板区分业务进展、问题、修改、验证层级、时间、
资源和下轮计划。基线没有提供真实运行证据，不能据此判定平台实现或模型质量失败。

### 初稿机械检查

- `quick_validate.py skills/modeling-dev-loop`：`Skill is valid!`。
- 初稿 19 个相对链接、5 个 Markdown 文件检查通过；发现入口符号链接正确解析。
- `git diff --check`：通过。
- 命令合同核对发现清理结果实际在 `state.json.cleanup`/宿主终态输出及 `cq-cleanup.jsonl`，
  不是独立 `cleanup.jsonl`；已修正参考表，另补现有 create scope 的直接链接。
- 独立情境应用进行中；本次不启动真实 modeling、Claude Code 修复、平台写入或服务重启。

### Round 1 独立情境应用与修订

执行者 `/root/skill_forward_test`，只收到 Skill、原始 S1～S6 情境和允许副作用范围，未提供
本计划的期望答案或基线结论。独立输出保留在
`workspaces/modeling-runs/modeling-dev-loop-skill-20260910/independent/round1.md`。
六个情境均产生决定及 S5 修复任务文本，但本轮判为 **REVISE（指令应用）**：

- S1 应用结果提出“启动带新挂载的新 Claude child，继续同一 semantic start”，未先证明
  当前 Team 有保留同一语义会话上下文的合法恢复机制。主流程据此收紧计数和角色边界：外部
  Claude 修复进程不能顶替 Modeling；无法证明这种恢复时，新建模会话按 fresh start 计。
- 独立报告指出未知写入的实际读取入口和安全交接判据不具体。已补现有 MCP/HTTP GET 对照、
  原请求/Attempt 绑定字段、在途/失败/已应用的区分及资源核对；没有新增查询或恢复服务。
  相关路径与字段从当前 backend MCP/API/service 源码核实，未做真实平台读取。
- 独立报告指出 L0 收口依据不足。已补目标运行终点、事件/交接、写回执与资源处置的报告要求，
  并指向当前 Task 与归属测试计划，不把本 Skill 变成全场景统一语义验收器。
- S6 应用把 SLA 未知是否处理只按是否纳入 L0 判断。已明确：当前候选/写入依赖的业务确认
  不因只验收 L0 而跳过，必须澄清或按合同保留明确未知。
- S2/S3/S4/S5 能保留未知写入、额度、等待用户、T0 自主设计、隐藏题和重启边界；S2 不再
  为已有授权内的只读核查额外请示，并报告五切片进展及未提供的时间数据。

修订后仅复测上述四个变更面；不重复完整六情境或扩大到真实建模。旧独立报告保留不改写。

### Round 2 独立变更面复测与收口

同一独立测试者只读当前两个变更文件，四项情境均能据文本执行，报告无 Skill 使用阻塞缺口。
原始结果：`workspaces/modeling-runs/modeling-dev-loop-skill-20260910/independent/round2.md`。
结论为 **PASS（指令应用复测）**：

- 新 Modeling child 未有保留原语义上下文的已证实恢复机制时计 fresh start，不能混用外部
  Claude 修复进程与 Modeling 身份或用旧 run ID 绕过计数。
- 通过现有 Session/Batch/Attempt/context 读取定位原 apply，区分在途、失败与实际已写状态；
  不把失败、404 或 safe_to_retry 当作零写入或可重放证明。
- L0 按本轮具体终点与真实证据收口，不把健康/PID/RUNNING 当作整轮通过，不前置 L1～L3。
- 当前候选/写入依赖的 SLA 未知仍须确认或按合同保留，不因只验收 L0 而猜测写入。

最终机械检查：官方 Skill validator 通过；24 个本地链接、3 段 Bash 语法（只检查不执行）、
UI 元数据和发现链接通过；`git diff --check`/暂存差异检查通过。GitNexus staged
`detect_changes`：8 个变更文件，0 个变更符号，0 条受影响执行流，risk `low`。

交付内容：`skills/modeling-dev-loop/`、`.agents/skills/modeling-dev-loop` 发现链接及
对应 `.gitignore` 例外、本验证记录。未修改现有 ontology-modeling、Team/平台代码，未纳入
原有 AGENTS.md、CLAUDE.md 或 `.codex/agents/` 用户改动。无需 backend/frontend 套件或服务
重启。没有真实 semantic start、Claude 修复调用、platform apply、SQL 或 L0/L1 验收证据；
运行效果应在后续获准任务中验证，本次指令验证不替代这些证据。
