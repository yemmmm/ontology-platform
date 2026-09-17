# R3.0-016 建模 Team 宿主交互接口 S1 — 共享测试计划

- 日期：2026-09-18
- 状态：设计与计划成稿；未实现、未测试。覆盖 S1 验收标准 A01–A07、A11（A08–A10 属 S2）。
- 需求：[R3.0-016](../../requirements/requirements-v3.0.md#r30-016-建模-team-宿主交互接口)
- 设计：[交付设计](../designs/2026-09-18-r3-0-016-s1-host-interaction-interface-design.md)

本文件是本需求唯一共享测试计划。后续各轮在 §7 追加日期、代码基线、执行者、命令、
结果与证据路径；保留失败与修复历史。文档检查与机械 PASS 不证明实现或真实建模质量。

## 1. 证据分层

| 层级 | 验证目标 | 当前状态 |
| --- | --- | --- |
| D0 | 主代理核对需求/设计/源码依据、链接与格式 | 已完成（2026-09-18，见 §7） |
| M | 实现者功能自测 + Team 回归（基线对比规则见 §2） | 未开始 |
| I | 独立功能测试：从文件/进程/FIFO/工具面核实字段、路由、错误、隔离与消息效果，不依赖实现者自报 | 未开始（Round 1 待追加） |
| 真实 L0 | 在用户获准的真实建模运行中证明 S1 接口闭环与后续工作；复用同一获准 run 的证据 | 未开始；授权条件见 §5 |
| L1+ | 语义/检索质量 | 由 006/011/012 独立验收承担，本计划不覆盖 |

## 2. 测试数据与隔离

- 确定性测试一律用临时 run root（pytest tmp）与受控 Runner 测试替身（沿用
  `modeling_team/tests/` 现有替身模式）；FIFO 用真实 `OuterInputFifo` 对象在 tmp 目录
  建/收；不写真实 `workspaces/modeling-runs`，不触发真实 provider/平台调用。
- 回执测试必须走真实文件追加语义（`evidence/*.jsonl` 落盘后由另一读取路径核对）。
- MCP 面测试用进程内客户端走 initialize/tools/list/tools/call，断言固定 12 工具且
  无 S2 工具名。
- 隐藏内容泄漏检查：在隐藏题/答案、凭据位置放唯一标记，断言 `get_run_status`/
  `get_run_events`/`get_pending_actions` 与错误输出不含标记；标记不进正式资料。
- **Team 回归基线对比规则**：`modeling_team` 套件存在已知 r23006 时期基线失败
  （缺 acceptance-ticket.json fixture，约 23 项）。改动前后**对比失败清单而非总数**：
  只要求"无新增失败项"；既有失败项逐一列出并与基线核对，不得为凑绿修改无关测试。
- 配置片段以冷启动方式验证（假宿主客户端拉起 MCP 服务器），不自动注册到任何
  全局/生产配置。
- **fixture 证据形状规则（评审 R1 发现 2 后新增）**：测试 fixture 中的证据文件形状
  必须由真实 Runner 代码路径生成，或与真实 run 录制逐字段核对（重点：`cq-interview.jsonl`
  的 `wait_window_open` 快照、`cq-wait-windows.jsonl` 仅 cleanup 落 `closed-on-exit`、
  `outer-question.jsonl` 注册/展示同形双记录），不得按设计文档想象自造形状；I 层至少
  对上述关键源各核对一次真实 Runner 行为，防止"替身自造形状→虚假通过→真实 L0 才暴露"。

## 3. 确定性用例（按验收标准分组）

成功/边界/失败/回归四类在组内混合标注。所有变更类用例同时经 `get_request_result`
核对回执状态（除 A03-7 等专门用例外，均带唯一 `request_id`）。

### A01 状态快照与读取零副作用

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A01-1 | 运行中 run（state=RUNNING，多证据源） | 快照字段与权威记录一致；记录状态/最后活动/阶段各带来源与观察时间 |
| A01-2 | 等待输入（issue WAITING_OWNER + 已展示问题） | 第一阻塞与待办摘要正确呈现；不把等待报为失败 |
| A01-3 | provider 等待 run | provider 等待绑定（agent/role/wait_id）出现在状态与待办 |
| A01-4 | 终态 run（含 terminal-classification/settled） | 终态结论正确；存活观察不宣称存活 |
| A01-5 | 证据不完整（缺 state.json/截断/记录冲突） | 可读部分照给 + limitations 逐条；不包装成"无待办/已完成" |
| A01-6 | 旧 run 无身份绑定（无 supervisor 记录、无恢复来源） | 存活=unknown；已知等待/阶段/终态不被抹去；FIFO 存在性仅作事实字段 |
| A01-7 | 有 `recovery/origin.json` 的续跑 run / 带 `host-supervisor.json` 的 run | 分别经 chain_writer_lock / /proc 观察给出进程观察值与观察时间 |
| A01-8（回归） | 只读工具调用前后 run 根文件集合与内容逐字节不变 | 读取不触发 drain、模型调用、恢复、cleanup、平台写入；快照区分 run_id 与 session/project 绑定 |

### A02 事件增量读取

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A02-1 | 首次分页（limit 小于总量） | 事件+next_cursor+has_more；翻页不重不漏 |
| A02-2 | 两次读取之间追加"较早时间戳"行 | 晚到追加行仍被后续读取交付（字节偏移语义，不按时间跳过） |
| A02-3 | 读取间隙出现新证据文件 | 新源从 offset 0 读入，不漏 |
| A02-4 | cursor 用于另一 run | `cursor_run_mismatch` 类型化拒绝 |
| A02-5 | 末尾半行（无换行） | 本次不交付、不计损坏；补齐换行后下次交付 |
| A02-6 | 完整但非法 JSON 行 | 显式 corrupt 占位+limitations；后续行继续读取 |
| A02-7 | 超大单行 | truncated 占位+字节长度；不整包回传 |
| A02-8 | 多源事件 | 每条带 source 与源内序；ordering 标注近似，不虚构因果 |
| A02-9 | cursor 篡改/版本不识 | `cursor_invalid`，不静默重扫 |
| A02-10 | 空/缺 evidence 目录 | 空结果+limitation，不报错为无事件源 |

### A03 问题查询、注册与答复

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A03-1 | 经工具发现普通问题待办并提交中文多行答复 | 信封由工具按待办绑定拼装；接受回执+`outer-user.jsonl` 消费证据；待办不再显示该问题 |
| A03-2 | CQ 访谈经 `answer_question(cq_interview)` 提交中文多行文本 | `cq-interview-accepted` 序号/阶段返回；文本逐字保留 |
| A03-3 | 两步注册模式（`register_question`→`answer_question`）；formal run 上注册 | 注册+应答成功；formal run 的 Runner-owned 拒绝类型化透传且 run 继续 |
| A03-4 | 答复绑定错误（未知/已消费/未展示 delivery） | 类型化拒绝+回执 rejected；问题未被消耗，run 可继续 |
| A03-5 | 答复被接受但候选未推进 | `get_request_result`=accepted 与进展证据分开呈现，不把接受当推进 |
| A03-6 | 全程仅 MCP 工具操作（协议检查） | 无手写 Python、无 FIFO 路径读取、无手拼信封（会话记录留证） |
| A03-7（回归） | 同 `request_id` 重复提交已接受答复 | 返回原结果"已处理"，不二次写 FIFO、不重复消费 |

### A04 CQ 审核与冻结

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A04-1 | 按待办绑定提交当前 review 决定 | 接受+决定证据；窗口关闭 |
| A04-2 | 旧 revision/digest、错 run、错问题绑定 | `cq_review_stale` 等类型化拒绝；新待办不受污染；正确输入仍可在同一 run 继续 |
| A04-3 | 审核完成后显式冻结；未经审核请求冻结 | 冻结返回 freeze_id/digest/公开题 ID/隐藏计数；未审核冻结维持原类型化拒绝（审核与冻结不同动作） |
| A04-4（回归） | 重复提交同一决定 | Runner 现行语义透传（拒绝/幂等按现有合同），不产生第二份决定证据 |

### A05 issue 与 provider 恢复绑定

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A05-1 | 按待办绑定提交当前 issue 的 resolution | 接受+`issue-resolution.jsonl` 证据；等待解除 |
| A05-2 | 陈旧 epoch/reporter/issue_id | `issue_resolution_rejected` 透传；当前等待不被解除 |
| A05-3（回归） | 仅用问题/答复通道（无信封）后查 issue | issue 仍 WAITING_OWNER；操作层不存在"便签代 resolution"路径 |
| A05-4 | 按绑定 `recover_provider`（角色/wait 正确） | 接受+`provider-wait` host-recovery 证据 |
| A05-5 | 无 pending wait/错角色/缺 text | `provider_wait_not_pending`/`invalid_provider_recovery` 透传 |
| A05-6 | unknown 写入下的 issue resolution | `unknown_mutation_requires_reconciliation` 透传；写门状态不变 |

### A06 请求结果关联

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A06-1/2 | 接受路径 / 类型化拒绝路径 | 回执 accepted/rejected 与分种类证据链接；拒绝绝不报 accepted |
| A06-3 | FIFO 写成功但无回执（Runner 慢/随后退出） | 存活期= submitted（保留最后已知事实）；run 终态后=unknown；均不自动重发、不换新 ID |
| A06-4 | 通道不可用（无 FIFO/终态 run/未启用） | `outer_input_channel_unavailable`，有界返回不挂起 |
| A06-5 | 写超时/超长行 | `outer_input_write_timeout`/`fifo_line_too_large`；不写半行；不推断零写入 |
| A06-6 | 同 `request_id` 同内容重复 | 原结果复用，无第二次 FIFO 写入 |
| A06-7 | 同 `request_id` 不同内容 | `request_id_conflict` 明确拒绝 |
| A06-8 | 未知 `request_id`/跨 run 查询 | `request_id_unknown`/run 作用域拒绝 |
| A06-9（回归） | 旧消息（无 request_id） | 行为与现状一致、无回执副作用；查询给出可读指引 |

### A07 隔离与不泄漏

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A07-1 | 生产/角色/验收方工具目录与配置扫描 | 宿主工具只出现在独立配置片段；`backend/app/mcp/tools`、agent-packages、cq-acceptance 合同零变化 |
| A07-2 | 冷启动宿主配置片段 | 12 工具可用；不自动改全局配置 |
| A07-3 | 隐藏材料标记泄漏检查（状态/事件/待办/错误全表面） | 无隐藏题正文、答案、凭据；隐藏题仅计数/ID |
| A07-4 | `run_id` 路径逃逸尝试（`../`、绝对路径、符号链接） | `run_id_invalid`/拒绝；解析结果必须落在 runs root 内 |
| A07-5 | 独立验收方视角 | 仅原 CLI 合同与验收输入可用，无控制类工具能力 |

### A11 CQ 交接与验收收口

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| A11-1 | 全链：待办给出 handoff 绑定 → `complete_cq_handoff` → acceptance_pending → CLI `cq-acceptance` 产报告（保留）→ `complete_cq_acceptance`（工具算 digest/verdict）→ 终态释放 | 全程无手拼 FIFO 信封；各回执可查 |
| A11-2 | pass/partial/fail 三种报告 | 均正常收口；收口成功≠验收 PASS 的表述正确 |
| A11-3 | 在途/未知写入时请求 handoff | 原类型化就绪拒绝透传，不包装成交接成功 |
| A11-4 | 旧 freeze/attempt 绑定 | `cq_review_stale` 透传；用当前绑定仍可继续同一 run |
| A11-5 | 报告缺失/不可读 | `cq_acceptance_report_mismatch`；报告落盘后重试成功 |
| A11-6 | 信封 digest/verdict 与报告不符 | 拒绝；Runner 复算为准（工具与 Runner 用同一纯函数） |
| A11-7 | 重复 `cq_acceptance_complete`（相同/相异） | 相同→幂等确认；相异→拒绝；不改写已接受结果 |
| A11-8 | full_joint run 发送完成动作 | `cq_selector_incompatible`（in-run 终态路径）透传，不强制收口 |
| A11-9（回归） | 任一拒绝后查 `get_request_result` | 拒绝不被报为交接/验收成功；已接受 handoff 不等于整轮完成 |

## 4. 完成门（S1 段）

1. I 层对 §3 全部用例 PASS（失败与修复历史保留在 §7，不得抹除）。
2. `modeling_team` 套件回归按 §2 基线失败清单对比无新增失败；backend/frontend 套件
   不涉及（若实现引入 backend 改动则按 AGENTS.md 补齐并重启验证）。
3. 交付物齐备：`host_ops.py`/`host_ops_mcp.py`/回执改动、`.claude/modeling-team-host-mcp.json`
   片段、runbook 宿主工具节（含保留 CLI 清单与适用合同）；无任何 S2 工具/参数桩。
4. 真实 L0 轮次按 §5 记录完成（或明确记录阻塞与剩余授权）；授权消耗台账完整。
5. 设计/计划状态行同步更新，"需求细化 / 实现 / 独立功能验收 / 真实 L0"分段记录。

## 5. 真实 L0 用例（独立功能验收通过后执行）

- **前置**：I 层 PASS；用户本轮授权记录在案——**最多 3 次 fresh semantic modeling
  starts，模型 `glm-5.3-flash`、effort `high`**（用户 2026-09-18 决定，优先级高于
  runbook 默认档位；model profile 取 `glm-flash-high`，见 §6 O1 处置）。授权额度是
  边界不是稀缺资产：不为"保护额度"增加准备；每轮记录授权来源、run ID 与消耗；
  20 分钟规则适用。
- **复用规则**：一个获准 run 的证据可跨多个动作复用，不为每个动作另开模型会话；
  但不得为凑用例让 run 人为重历阶段。
- L0-1（第 1 次 start，主轮）：用现有 CLI 启动（S1 不封装启动），宿主**仅经 MCP 工具**
  完成观察闭环：`get_run_status`/`get_run_events` 增量续读、`get_pending_actions` 发现
  待办、真实访谈经 `answer_question`（中文多行）、CQ 审核/冻结经 `submit_cq_review`/
  `freeze_cq`、（如自然发生）issue/provider 事件经对应工具处理；全程记录"零手写
  Python/零 FIFO 路径/零手拼信封"。issue/provider 等待与 pass/partial/fail 分支以
  真实出现为准，未出现分支由 §3 确定性用例承担，如实记录未覆盖。
- L0-2（优先复用 L0-1 的 run；确需新 run 才用第 2 次 start）：走到 handoff →
  `complete_cq_handoff` → CLI `cq-acceptance` 独立报告 → `complete_cq_acceptance`
  → 终态释放；verdict 如实记录，收口成功不报验收 PASS。
- L0-3（第 3 次 start，保留）：仅当 L0-1/L0-2 因 S1 接口缺陷受阻，窄修复后用于复测；
  未使用则不消耗。
- **清理与保留**：失败 workspace、原始事件与写入/清理证据保留，不用后续成功覆盖；
  无自动 GC；手工清理按 runbook 既有授权与顺序；运行手册的存活登记（session/PID →
  `host-supervisor.json`）在每轮 L0 实际使用并留证。

## 6. 开放项处置（2026-09-18 主代理闭合）

- **O1（已闭合）**：用户授权为 `glm-5.3-flash`/effort `high`；现有 model profile
  `modeling_team/model-profiles/glm-flash-high.yaml` 即该组合（auth-r3-0-020 已实际
  使用验证）。真实 L0 统一选用 `glm-flash-high`，不沿用 `glm-flash-max`，不另建档。
- **O2（已闭合）**：准入路径最小 `request_id` 剥离 + `outer-input-receipts.jsonl`
  回执改动由需求 R3.0-016"提交、确认与错误反馈"第 3 条明确授权（"已有通道缺少关联
  确认时补最小关联与回执"），属 S1 实现范围；约束为保证旧行为逐字段不变、无通用
  队列。若实现中发现无法保持逐字段兼容，回设计修订（O2 原文），不在实现里就地扩
  合同。
- **O3（已闭合）**：MCP 服务器依赖 backend/.venv 的 `mcp` 包（FastMCP）——这是
  modeling_team 既有支持的唯一运行时；若该 import 在目标环境不可用，实现者改用
  `capability_mcp.run_stdio_client` 同构的自研 stdio 循环（机械替换，合同不变），
  并在结果中报告。

## 7. 本轮记录及后续执行

### D0 — 2026-09-18 主代理需求与设计核对（本计划成稿轮）

- 依据 2026-09-18 只读代码核对（设计 §2 与附录 A 的锚点均已对源码验证）；
  需求 R3.0-016 S1 范围、A01–A07+A11 与保留 CLI 清单逐条映射到设计 §4–§11 与本计划 §3。
- 本轮 0 次 semantic start；未修改任何代码。
- 后续轮次按日期追加于下方（M Round n / I Round n / 真实 L0 Round n），保留失败历史。

（待追加：M Round 1 — 实现者自测；I Round 1 — 独立功能测试；真实 L0 Round 1…）

### I Round 1 — 2026-09-18（requirement_tester 独立功能测试）

- **代码基线**：worktree HEAD `d28768942810ea34909cfe01b826fea0319b604a`（未提交），S1 变更为
  `host_ops.py`/`host_ops_mcp.py`/三个新测试文件/`.claude/modeling-team-host-mcp.json`/
  `__main__.py` 准入包装/runbook 宿主工具节。本轮 0 次 semantic start；未改任何产品代码。
- **实现预审（执行前）**：通过。无 S2 工具名/桩、无 shell/exec 原语（`host_ops*.py` 全文扫描）；
  `run_id` 单段校验+`resolve().relative_to(runs_root)`+`is_dir`，符号链接逃逸被拒；
  读工具零副作用（byte-identical 探针）；`host_ops` 不 import Runner 运行时（仅
  `chain_writer_lock_report`/`load_origin_record`/`pid_is_alive` 与 `competency_questions`
  纯合同函数）；A07 扫描：宿主工具仅出现在 `.claude/modeling-team-host-mcp.json`，
  `backend/app/mcp`、agent-packages、全局宿主配置零命中；`cq-wait-windows.jsonl` 不作派生源
  （仅 docstring 提及）。
- **fixture 证据形状核对（§2 规则，对照真实 Runner 源码）**：通过。`cq-interview.jsonl`
  `{ordinal, interview_ref, wait_window_open}`（runner.py L6799）；`cq-wait-windows.jsonl`
  仅 cleanup 落 `closed-on-exit`（L9876）；`outer-question.jsonl` 注册/展示同形 4 字段双记录
  （L8890/L8790）；`owner-answer-failure` 仅 `{owner_answer_id, release_id}`（L9013）；
  `provider-wait` 事件全集 `{observed, cleared, host-recovery, issue-reported,
  issue-report-unavailable, issue-settlement-skipped, coordinator-delivery-failed}`
  （L6420/6436/4199/6513/6508/4237/8379）；`provider-wait-recovery-failed` 落 `issue-control`
  （L8608），不在 provider-wait 内。
- **执行的命令与结果**（cwd 仓库根，`backend/.venv/bin/python`）：
  1. 全量回归 `python -m pytest modeling_team -q`：**7 failed / 1921 passed / 1 skipped**，
     失败清单与 §2 基线完全一致（`test_deepseek_codex_runtime.py` 的
     `test_fallback_file_rejects_group_or_other_permissions[388/416]` 与
     `test_fallback_file_rejects_missing_or_malformed_assignment` 5 参数化项），**零新增失败** → 回归门 PASS。
  2. 三个新测试文件重跑：69 passed（与 M 层自报一致；含真实 Runner harness 的
     CQ/A11 用例，`_CQRunner`/`_CompletionRunner` 走真实 `handle_cq_outer_input`）。
  3. 独立探针（/tmp/r3016s1_probes，已按临时文件规则清理；关键复现片段见下）：
     26 项探针 **24 passed / 2 failed**——两个失败均为缺陷 I-D1。
  4. MCP 冷启动（真实 stdio 子进程，按 `.claude/modeling-team-host-mcp.json` 的
     command/args/cwd 拉起，initialize/tools/list/4 次 tools/call）：**PASS**——恰好 12 工具、
     无 S2 名、`{ok,data|error}` 信封、`request_id_unknown`/`run_id_invalid` 类型化错误。
  5. 准入路径探针：129 字符 `request_id` 被 pop 但不关联（消息照常处理、无回执）；无
     `request_id` 旧行为逐位不变；读工具前后 run 根逐字节不变。
- **缺陷清单**（严重度降序）：
  - **I-D1（HIGH，违反 A02-1，波及 A02-6/A02-2 续读正确性）**：`host_ops.py::_scan_source`
    （L1164–1272）在正常/损坏/截断完整行路径上从不推进 `position`（仅 oversized-无换行分支
    L1202 设 `position = end`），每行的 `end` 都是 `start + len(本行)` 而非累计字节偏移。
    当一页从同一源交付 ≥2 行（常态），`next_cursor` 落在已交付数据内：翻页**重复交付**；
    行长不等时 offset 落在行中间，下一页把健康文件读出**虚构的 `corrupt:true` 占位 +
    `complete:false`**；整页读完 `has_more=false` 后 cursor 也不在 EOF。M 层
    `test_a02_1` 因双源时间戳交错、每页每源恰一行而掩盖了该缺陷。复现（tmp run root，
    alpha.jsonl 写 7 行等长记录，limit=3 翻页）：交付序列为 0,1,2 / 1,2,3 / 2,3,4 …，重复 12 项；
    行长不等（`"pad": "y"*300` 中间行）时第二页出现 `{'corrupt': True, 'parse_error':
    'Expecting value…'}` 且 `complete=False`。修复方向：每次 `readline` 后 `position = end`。
  - **I-D2（MEDIUM，违反 A01-3/A05 的 provider 等待可见性）**：`host_ops.py::_provider_pending`
    （L557–603）把"最新事件 ≠ `observed`"一律视为收口。真实 Runner 中 `observed` 每次
    wait 起始仅落一次（`runtimes/codex.py::consume_provider_waits` L5464 return-and-clear），
    之后 `issue-reported`（L6513）/`issue-report-unavailable`（L6508）/
    `coordinator-delivery-failed`（L8379）等信息性事件会成为该 agent 最新记录，而等待仍
    pending。最坏序列 `observed → issue-report-unavailable`（Coordinator 自身 parked，run 停在
    WAITING_OWNER、`host_action=recover_provider`、无 issue 可答）：`get_pending_actions`
    既无 provider_wait 项也无 issue_wait 项、无 limitation——宿主唯一恢复动作的
    agent_id/wait_id 绑定消失（`first_blocker`/`pending_summary` 同受影响）。复现：
    provider-wait.jsonl 依序写 `observed`（含 agent_id/role/wait_id/recorded_at）与
    `issue-report-unavailable`（更晚 recorded_at），`pending_items` 返回 provider_wait 项数 0。
    修复方向：仅 `host-recovery`/`cleared` 构成收口，信息性事件不关闭等待。
  - **I-D3（LOW，注释/派生准确性）**：`host_ops.py` L631–638 注释称"a failed answer never
    consumes a question"——与 runner.py L8990 相反（问题在持久化/发送尝试**之前**即标记
    consumed，失败烧毁该问题）。实际影响有界：该路径同时置 state=FAILED（终态），变更类
    工具被终态守卫拒绝，误导性"可答"项无法经工具行动；limitation 已记录。应更正注释并
    可选地在存在 failure 记录时标注该项。
  - **I-D4（INFO）**：事件的 `line_no` 是每次调用内的相对序（cursor 续读后从 1 重新计数），
    非源内绝对行号；跨页追溯 corrupt/truncated 占位时序号不单调。建议改为绝对行号或改名。
- **实现者 4 项偏差处置**：
  (a) owner-answer-failure 无问题绑定——**属实**（见上形状核对），保守收窄 + limitation 可接受；
  但其代码注释依据错误（I-D3）。(b) provider-wait 收口集 {host-recovery, cleared}——开发者
  **正确**：provider-wait.jsonl 不存在 `recovery-failed` 事件（该事件落 issue-control），
  设计 §7.2 的"host-recovery/recovery-failed"措辞与实际不符，应回写设计；但实现进一步把
  全部非 observed 事件当收口，引入 I-D2。(c) `submit_cq_review` 自填 `schema_version`——
  Runner 侧 `validate_review_decision` 强制该字段（competency_questions.py L473），工具用同一
  常量填充、其余绑定 Runner 全验，设计 §4 输入表也未列该字段；机械填充、已在待办注记与
  runbook 披露，**可接受**。(d) 新错误码 `request_id_invalid`——设计 §9 最小码表未列，但属
  传输/关联层、仅用于畸形 request_id 的类型化拒绝，**可接受**，建议设计 §9 补记。
- **§3 覆盖情况**：A01-1–A06、A07-1–A07-5、A11-1/2(部分)/4/5/9 已执行（I 探针 + M 层真实
  Runner 用例交叉核对）；其中 A02-1 FAIL（I-D1）、A01-3 的 provider 等待派生 FAIL（I-D2）。
  A02-2/3/5/6/7/8/9/10、A03 全部、A04-1/3（Runner 侧 stale/重复依赖 M 层真实 harness）、
  A05-1/3/4/5（Runner 侧 2/6 依赖 M 层）、A06 全部、A07 全部 PASS。未独立执行：A01-7 的
  chain_writer_lock/host-supervisor 独立运行（接受 M 层真实代码测试 + 帮助函数复用核对）；
  A06-5 写超时的独立触发（M 层 monkeypatch 用例 + 代码审读覆盖；`_write_fifo_line` 有界
  poll 循环核实）；真实 L0 全部（§5，按计划另行）。
- **残余风险**：I-D1 修复后需重点回归"每页多行同源 + 行长不等 + 末页后增量续读"组合；
  I-D2 修复需注意 `issue-settlement-skipped` 出现在 host-recovery 之后（应保持不重开等待）；
  `get_run_events` 单行 256KiB 截断对 `app-server-events.jsonl` 的宿主侧边界依赖文档自律。
- **结论**：**FAIL**（两处需修复：I-D1、I-D2；I-D3/I-D4 顺带处理）。回归基线干净、工具面/
  隔离/回执机制/有界通道/幂等冲突/路径安全全部通过。建议需求开发 agent 修复 I-D1/I-D2
  （并顺带 I-D3 注释、I-D4）后发起 I Round 2 复测；真实 L0 不启动。

### I Round 2 — 2026-09-18（requirement_tester 复测）

- **代码基线**：HEAD 仍为 `d28768942810ea34909cfe01b826fea0319b604a`；`runner.py` 相对 HEAD
  diff 为空（已复核），S1 变更仍限于 `host_ops.py`（未跟踪新文件）/`host_ops_mcp.py`/
  三个测试文件/`__main__.py` 准入包装/runbook。本轮 0 次 semantic start；未改任何产品代码。
- **Round 1 缺陷复测（代码审读 + 独立探针，均 FIXED）**：
  - **I-D1 FIXED**：`_scan_source` 每条完整行后 `position = end` 累计（host_ops.py L1232–1236，
    注释显式引用 I-D1）。探针：行长不等单源 limit=3 翻页 → 恰好 [0..6] 无重无漏；双源等长翻页；
    页边界 limit∈{2,3,4,9,10} × 9 事件全组合；整读后 cursor offsets == 两文件字节数、静默续读为空、
    追加行照常交付；A02-6 坏行+好行单页各交付一次（corrupt 占位 `byte_offset:0`，第二页空且
    `complete:true`）；坏行单独分页（占位页 1、好行页 2——per-source 扫描上限保护了单源形态）；
    截断行+分页同过。
  - **I-D2 FIXED**：`PROVIDER_WAIT_CLOSE_EVENTS = frozenset({"host-recovery","cleared"})`（L557），
    `_provider_pending` 改为文件序状态机（provider-wait.jsonl 追加only，文件序即因果序）。10 序列
    参数化探针全过：最坏序列 `observed → issue-report-unavailable`（Round 1 场景）保持 pending 且
    agent_id/role/wait_id 绑定与 `recover_provider` 动作可见；`issue-reported`/
    `coordinator-delivery-failed`/无 event 键快照均不收口；`host-recovery`/`cleared` 收口且其后
    `issue-settlement-skipped` 不重开；收口后新 `observed` 重开。`get_run_status` 侧最坏场景
    `pending_summary.counts.provider_wait==1`、`first_blocker.kind=="provider_wait"`。
  - **I-D3 FIXED**：limitation 措辞改为"the Runner consumes the question before the attempt;
    a retry is rejected"（L650–657），与 runner.py L8990 行为一致。
  - **I-D4 FIXED**：normal/corrupt/truncated 三类事件均带 `byte_offset`（行首字节偏移，探针与
    真实文件字节逐一核对；截断另带 `byte_length`）；`_scan_source` docstring 说明 line_no 为本次
    扫描内序号、定位以 byte_offset 为准；runbook L519 同步记载该语义。
- **执行的命令与结果**（cwd 仓库根，`backend/.venv/bin/python`）：
  1. 聚焦测试 `python -m pytest modeling_team/tests/test_host_ops.py
     modeling_team/tests/test_host_ops_mcp.py modeling_team/tests/test_outer_input_receipts.py -q`：
     **77 passed**（与 M 层自报一致，含 +8 新回归）。
  2. 全量回归 `python -m pytest modeling_team -q`：**7 failed / 1929 passed / 1 skipped /
     339 subtests passed（115.57s）**，失败清单与 §2 基线**逐项相同**（`test_deepseek_codex_runtime.py`
     的 permissions[388/416] + malformed_assignment 5 参数化项），**零新增失败** → 回归门 PASS。
  3. 独立探针套件（/tmp/r3016s1_r2/test_i2_probes.py，23 项；临时文件已按规则清理）：
     22 passed / 1 failed——唯一失败项是**故意保留的残余缺陷探针**（见 I2-D1）。
  4. runbook 检查：`grep byte_offset skills/modeling-dev-loop/references/team-runbook.md` → L519
     记载 cursor 逐字节偏移、line_no 续读重计数、定位以 byte_offset 为准。
- **新缺陷（严重度降序）**：
  - **I2-D1（MEDIUM，违反 A02-1"翻页不重不漏"与 A02-6"坏行显式上报"的多源翻页切边；波及
    设计 §6"晚到较早时间戳行经字节偏移天然交付"承诺）**：`host_ops.py::get_run_events`
    （L1369–1372）合并候选按 `(stamp_key, source, line_no)` 排序后取前 `limit` 条交付，随后
    `next_offsets[source] = max(已交付条目的 end)`——若同源某候选**物理在前**但**排序在后**
    （未入本页），其字节被游标直接跳过，**静默丢失**，且伴随 `has_more:true` 后紧跟空页的矛盾
    输出。三个复现（均为 tmp run root）：
    (a) 坏行占位：alpha.jsonl = `{corrupt json\n` + n=7 行，beta.jsonl = n=100，limit=2 →
    `P1=[('alpha.jsonl',7),('beta.jsonl',100)] has_more=True | P2=[] has_more=False`——坏行
    占位事件**从未交付**（仅 limitation 字符串提及），A02-6"以显式占位事件上报"落空；
    (b) 同源时间戳乱序：alpha 行1 n=1@10:00:09、行2 n=2@10:00:01，beta n=100@10:00:08，
    limit=2 → 交付并集 [2,100]，**n=1 永久丢失**；
    (c) 设计 §6 旗舰场景：alpha = n1@10:00:01、n2@10:00:03、晚到追加 n0@09:59:59（物理最后、
    排序最前），beta n100@10:00:02，limit=3 → `P1=[0,1,100] has_more=True | P2=[]`，
    **n=2 永久丢失**。形态 (a) 只需"同源坏/截断行 + 更晚时间戳已交付行 + 页截断"，恰好落在
    写入中断等宿主最需要事件流的诊断场景；形态 (b)/(c) 需时间戳乱序（晚到追加即产生）。
    修复方向：next_offset 的推进改为按源内**文件序**行走已交付候选、停在第一个未交付候选的
    行首 byte_offset（未交付者下次调用重扫），勿用已交付 end 的 max()。
- **结论**：**FAIL**（单一缺陷 I2-D1）。Round 1 全部点名复测项（I-D1 四组探针、I-D2 十序列+
    最坏场景状态呈现、I-D3 措辞、I-D4 字段+runbook）均 FIXED/PASS；回归基线干净；但按 §4.1
    "I 层对 §3 全部用例 PASS"门，A02-1 不漏读与 A02-6 显式坏行上报在多源翻页切边仍不成立。
    修复面窄（get_run_events 游标推进一处）。建议需求开发 agent 修复并按上述三形态补回归后发起
    I Round 3；真实 L0 继续不启动。

### I Round 3 — 2026-09-18（requirement_tester 复测）

- **代码基线**：HEAD 仍为 `d28768942810ea34909cfe01b826fea0319b604a`；`runner.py` 相对 HEAD
  diff 为空（已复核）。本轮 0 次 semantic start；未改任何产品代码。
- **I2-D1 修复核实（代码审读 + 独立探针，不信自报）**：`get_run_events`（host_ops.py
  L1345–1403）现以 `delivered_ids = {(source, byte_offset)}` 判交付，源内存在未交付已扫描候选时
  `next_offsets = min(未交付行首)`（停驻），全部已交付才推进到扫描前沿（max end）；合并排序与
  时间戳语义未动。三形态独立复测**全部 PASS**：(a) 坏行占位+同源更晚已交付行+limit=2 截断——
  交付并集（按 (source, byte_offset)）== 全部行、坏行占位恰一次（byte_offset==0）、终止、终cursor
  双源 EOF、`has_more:true` 后无空页、静默续读空、追加行照常交付；(b) 同源时间戳乱序 limit=1/2
  ——并集完整、终 cursor EOF；(c) 设计 §6 旗舰晚到追加+第二源 limit=3/2——并集 {0,1,2,100} 完整、
  终 cursor EOF。M 层新增 test_a02_11/12/13 已读：断言与探针一致（按 id 去重并集 + 坏行恰一次 +
  EOF cursor），突变验证声明与行为相符。
- **跨页重投递裁决（主代理指定由测试方裁定）**：**判定可接受——停驻窗口内 at-least-once、
  宿主以 (source, byte_offset) 去重为准**。事实：形态 (a) 交付计数 `alpha 好行×2、坏行占位×1、
  beta×1`；而顺序流（i3_e，双源各 5 行交错 limit=3）与行长不等翻页（i3_h）**零重复**——重复仅
  出现于停驻窗口内，且每事件带稳定 `source`/`byte_offset`/`line_no` 身份，去重确定且廉价。依据：
  设计 §6 从未承诺 exactly-once（承诺的是"天然不漏"、确定性合并序、显式占位），cursor 的单位是
  宿主持有的逐源字节偏移，`get_run_status` 分发的 `events_cursor` 快照本就允许宿主用旧 cursor
  重读（天然 at-least-once）；读取面零副作用，动作面有独立 request_id 幂等层；替代方案（cursor
  记账已交付集合→无界膨胀；或扣住不交→回到 I2-D1 丢失）严格更差。A02-1 的"不重"针对的是 I-D1
  那类"有序流整页重放"，该类已由 i3_e/i3_h 回归覆盖为零重复。**附带条件**：(1) 设计 §6"续读"条
  与 runbook L519 需补记该语义（当前仍写"不重不漏"无停驻窗口例外）——文档跟进项（LOW）；
  (2) 该语义成立的前提是**每个停驻窗口最终排空**——本轮发现实现违反此前提（见 I3-D1）。
- **新缺陷**：
  - **I3-D1（HIGH，违反 A02-1"不漏"+A02-6"坏行显式上报"+分页收敛性）**：**双源同时停驻→
    分页永不收敛，停驻行永不交付**。当 ≥2 个源各自停驻（各有未交付首候选：坏/截断行占位排序
    恒最后，或晚到追加/乱序时间戳行），合并 top-limit 每页都选中**相同的**已交付时间戳行，
    停驻源的首候选永远进不了页，窗口静态、页内容逐字重复、cursor 冻结。三个复现（tmp run root）：
    (1) alpha=`{corrupt a\n`+stamp07、beta=`{corrupt b\n`+stamp08、limit=2——每页
    `[(alpha,11),(beta,11)]`、`has_more=True`、cursor 冻结 `{alpha:0,beta:0}`，25 页不终止；
    (2) 更大窗口（每源 1 坏行+5 时间戳行）limit=4——39 页恒 `n=4 has_more=True` 不终止；
    (3) 混合形态：alpha 坏行停驻 + beta 乱序时间戳停驻（line1@09s、line2@01s）——每页恒
    `[(beta,53),(alpha,11)]`，beta line1 与 alpha 坏行占位永不交付。单源停驻总能终止（其余源
    到 EOF 后窗口独占页面，M 层 test_a02_11 即此形态）；limit=1 因每源扫描上限=1 亦自愈。
    触发面评估：一次崩溃可同时在多个 evidence 文件留下撕裂行（续写后成为完整坏行），设计 §6
    旗舰晚到追加行天然制造"乱序时间戳停驻"，故"一个坏行文件 + 一个晚到追加文件"即可触发，默认
    limit=200 的长 run 上页截断常态存在。影响：宿主"读至 has_more=false"永不结束；即便宿主
    自行限页，坏行占位/停驻行也**永久缺失**（比 I2-D1 的有限丢失更重）。修复方向：为每个停驻源的
    停驻首候选在下一页**保底交付槽位**（多停驻源间按确定性次序轮转，靠 cursor 推进自然轮转），
    其余槽位维持合并序；单源停驻终止性已具备。
- **受影响回归（全部 PASS）**：半行延迟与补齐后交付（A02-5）；行长不等 7 行 limit=3 翻页恰
  [0..6] 且零重复；>256KiB 截断行+分页（占位恰一次、byte_length 精确）；停驻进行中新证据文件
  从 offset 0 读入不漏（A02-3）；I-D2 抽查两组未动（最坏序列 observed→issue-report-unavailable
  保持 pending 且绑定+recover_provider 可见；host-recovery/cleared 收口、其后
  issue-settlement-skipped 不重开、cleared→observed 重开）。
- **执行的命令与结果**（cwd 仓库根，`backend/.venv/bin/python`）：
  1. 聚焦三文件：**80 passed**（与 M 层自报一致，含 test_a02_11/12/13）。
  2. 全量回归：**7 failed / 1932 passed / 1 skipped / 339 subtests（115.54s）**，失败清单与
     §2 基线**逐项相同**，零新增 → 回归门 PASS。
  3. 独立探针（/tmp/r3016s1_r3，15 项；测后已按临时文件规则清理）：**13 passed / 2 failed**
     ——两个失败均为 I3-D1 故意探针（双停驻终止性）。
- **结论**：**FAIL**（单一缺陷 I3-D1）。I2-D1 确认 FIXED；重投递语义按上裁决定性为可接受
  （附带文档补记条件）；回归基线干净；但按 §4.1 门，A02-1/A02-6 在"≥2 源同时停驻"形态下
  不成立且分页不收敛。建议需求开发 agent 修复 I3-D1（页选择保底槽位，改动仍限
  get_run_events）并补双停驻回归，同时回写设计 §6 与 runbook 的 at-least-once 语义，之后发起
  I Round 4；真实 L0 继续不启动。

### I Round 4 — 2026-09-18（requirement_tester 复测）

- **代码基线**：HEAD 仍为 `d28768942810ea34909cfe01b826fea0319b604a`；`runner.py` 相对 HEAD
  diff 为空（已复核）。本轮 0 次 semantic start；未改任何产品代码。
- **I3-D1 修复核实（代码审读 + 独立探针，不信自报）**：`get_run_events` 选页/游标块按六不变量
  重写（host_ops.py L1370–1489）：`_EventCandidate` 逐源候选池；**停驻头保底槽位**——每页先按
  `(head byte_offset, source)` 升序选各非空池 pool[0]（停驻行），limit < 停驻源数时未入选头的
  park 原地保留、下页再竞争；其余槽位从各池 pool[1:] 按 `(stamp, source, line_no)` 合并序填充；
  park 计算（min 未交付行首 / 全交付推进前沿）与 Round 3 相同；返回列表重排合并序。无饥饿论证
  独立复核成立：头交付严格推进该源 park（行字节非空，park 只前进），(byte_offset, source) 序下
  每个非空池终将轮到最小者；每页至少交付一个头 → 页数 ≤ 行数+源数级。
- **`_complete_line_remains` 改动核查（本轮唯一超块改动）**：`_scan_source` 两触发点改为探针
  ——仅当触发点后确有**可交付行**（完整换行行或超长截断占位尾）才置 `stopped_early`。独立
  探针：恰好 limit 行+尾随半行 → `has_more=false`（不再有空页）、补齐换行后续读交付；半行源+
  另一源有待发行 → `has_more=true` 且下一页非空；恰好 limit 行+尾随超长行 → `has_more=true`、
  下一页交付 truncated 占位恰一次（`byte_length` 精确）后 EOF。`_scan_source` 其余行为（半行
  延迟不计损坏、坏行占位、超长占位、position 累计）与 Rounds 2/3 结构一致并经回归探针复验。
- **独立探针结果**（/tmp/r3016s1_r4，18 项，测后已清理）：**18 passed**。覆盖：
  1. I3-D1 三形态：双坏行 limit=2（双占位页 1 即交付、恰各一次、并集完整、双源 EOF、终止）；
     三源停驻（坏行+乱序时间戳+早时间戳）limit=4（页数上限 2×行数+源数+4 内终止、并集完整、
     坏行恰一次、三源 EOF）；坏行+乱序混合 limit=2（终止、两停驻行恰一次、EOF）。
  2. 无饥饿专项：limit=1 × 3 源与 × 4 源全坏行停驻、limit=1 × 三类停驻混合（坏行头/乱序时间戳/
     晚到追加早时间戳）——全部有界终止（≤3×行数+8 页）、所有源排空到 EOF、占位恰一次。
  3. 页内输出合并序：保底槽位强占位入页时，stamped 事件 recorded_at 升序、stamp-less 占位
     恒居页尾（设计 §6"页内输出仍按合并序"条款成立）。
  4. 回归：a02_11/12/13 形态、行长不等 7 行 limit=3 恰 [0..6]、I2-D1 三形态（含终 cursor 追加行
     交付）、停驻中 limit=1 新源发现、I-D2 抽查（最坏序列 pending+绑定、收口/重开）。
  5. **独立性质探针（换种子 770209，30 迭代，2–5 源、坏行 18%/超长 16%/乱序时间戳、随机
     limit 1–4、首页截断后 60% 概率晚到追加、cap=512）**：有界终止、(source, byte_offset) 并集
     完整、占位恰一次、EOF 光标、has_more 后无空页——全部通过。
- **M 层新增回归审读（非只跑）**：test_a02_14（双坏行 limit=2，页数上限 2×行数+源+4，占位
  恰一次 [0,0]，EOF）、test_a02_15（三源 limit=4）、test_a02_16（坏行+乱序混合）、test_a02_17
  （seed 20260918，24 迭代，断言与自报相符：sorted 占位集合比对即"恰一次"（重复会使列表变长）、
  显式"placeholder re-delivered"守卫、EOF 光标、有界页数）——断言与实现/自报一致。突变验证
  声明未由我复刻，差异证据以 Round 3 同形态探针失败→本轮同形态探针通过替代。
- **文档一致性核对（设计 §6 修订 vs 实现 vs runbook L519）**：来源发现/cursor 拒绝码/损坏行/
  大小边界条款与实现一致（未变部分复用 Rounds 1–3 核对）；修订的"续读与选页"（保底槽位、
  `(head byte_offset, source)` 确定性轮转、任意 limit≥1 无饥饿、选集 vs 页内排序分离）、
  "投递保证与收敛性"（无遗漏、停驻窗口 at-least-once、(source, byte_offset) 去重、占位恰一次、
  有限收敛、has_more 下一页非空）、"半行不置位 has_more"三条与实现行为逐条相符，均由上述探针
  证实。runbook L519 措辞同核。Round 3 裁定的文档补记条件已满足。
- **执行的命令与结果**（cwd 仓库根，`backend/.venv/bin/python`）：
  1. 聚焦三文件：**84 passed**（与 M 层自报一致，含 test_a02_14–17）。
  2. 全量回归（两次运行一致）：**7 failed / 1936 passed / 1 skipped / 339 subtests（~115s）**，
     失败清单与 §2 基线**逐项相同**（`test_deepseek_codex_runtime.py` 的 permissions[388/416] +
     malformed_assignment 5 参数化项），零新增 → 回归门 PASS。
  3. 独立探针：**18 passed**（首轮 17+1，唯一失败为探针自身 str/Path 笔误，修正后全过）。
- **残余风险**：性质覆盖以种子为界（现有 M 层 20260918 + 我方 770209 两粒种子通过）；停驻窗口
  at-least-once 为宿主可见合同，宿主必须按 (source, byte_offset) 去重（runbook 已写明）；坏行
  集中场景的页数上界为 2×行数+源数级（实践可接受）；A01-7/A06-5 等以 M 层真实代码测试+代码
  审读代偿的用例处置沿用 Round 1 记录，未受本轮改动影响（改动仅限 get_run_events/_scan_source）。
- **结论**：**PASS**。I3-D1 确认 FIXED（六不变量实现 + 三形态/无饥饿/性质探针全过）；设计 §6
  与 runbook 回写与实现一致；回归基线干净；§3 已执行用例全部 PASS（含历轮处置）。S1 功能
  验收（I 层）达到 §4.1 门。真实 L0（§5）未启动，待主代理决定。
