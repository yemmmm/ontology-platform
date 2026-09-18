# R3.0-016 S2 设计：建模 Team 宿主交互接口 S2（启动 / 生命周期 / 检查点封装）

- 日期：2026-09-18
- 需求权威：`docs/requirements/requirements-v3.0.md` §R3.0-016（≈L1369–1575），S2 覆盖 A07–A10
- 上游交付：S1 设计与测试计划（`docs/delivery/designs/2026-09-18-r3-0-016-s1-host-interaction-interface-design.md`，实现 ceb4d4f，I Round 4 PASS）、R3.0-015 检查点与接续设计（2026-09-14）
- **主代理核对修订（2026-09-18，planner 交付后三处事实修正）**：
  1. `run` 子命令**无** `--authorization-reference`/`--session-timeout` 参数（二者仅 `checkpoint resume` 有），`start_run` 契约与 argv 已相应删改；`run` 的基线由 `runner.prepare`（≈L887）内部派生并经 `StartLedger.baseline_hash` 记账，**无基线线参数**，任务要求的基线预览继续走保留 CLI `baseline`。
  2. checkpoint 外层信封的溯源 `request_id` 就是**顶层键**（`_handle_checkpoint_outer` ≈L11012 `message.get("request_id")`），而 S1 回执包装在分发前无条件 pop 顶层 `request_id`（`__main__.py` L248–250）——原"独立 `checkpoint_request_id` 参数映射回信封"不可达。修订为**单一 `request_id` 语义 + 共享准入包装对 `action=="checkpoint"` 回注该键**（§3.4/§7.3），Runner 侧因此有一处最小改动，原"Runner 侧零改动"结论作废。
  3. 开放决策①②已裁决：`settle_source_run` 走**进程内调用**；`checkpoint resume` **支持** `--enable-outer-input-fifo`（argparse 已有），接续 run 默认启用。
- **计划评审 R1 修订（2026-09-18，plan_reviewer REVISE，1C/4H 全部 accepted-high）**：
  1. `resume_from_checkpoint` 合同纠错：`checkpoint resume` 的 `--run-id` 是**源 run**（`__main__.py` L3167 `source_root = runs_root / args.run_id`），`--new-run-id` 才是新 run，**无 `--source-run` 参数**；production 接续 `--freeze-started-at` 必填（schema v2 Task 硬性要求，runner.py L866）。§5.5 已重写。
  2. 真实 semantic-start 证据文件纠错：为 `evidence/semantic-start.jsonl`（runner.py L2358–2368）；run 内 `evidence/start-ledger.jsonl` 只含 reservation/presemantic_release/terminal_settlement，**不含 semantic start 事件**，不得指引宿主据其判定语义已开始。§5.1/§6.3 已改。
  3. A08 基线证据补接口落点：run 根 `baseline-manifest.json`（runner.py L1277）与 start-ledger reservation 的 `baseline_hash` 经 `start_run` 返回值定位引用（S1 查询面仍不改）。§5.1 已补。
  4. 受管启动落地时序补齐：run 根出现的有界等待（≤10s）、supervisor 写入时机、`.host-launches` 退出观察由 reaper 守护线程完成（兼防 zombie）、预检顺序修正（活进程优先于死记录）。§6 已重写。
  5. 实现不变量补充：checkpoint 回注必须在回执 digest 计算**之后**（否则两侧 digest 分叉，重放误报 `request_id_conflict`）；`settle_source_run` 的 `readback` 为必填参数；`stop_run` 的 `reason` 仅宿主台账记录、Runner 不消费。§3.4/§5.2/§5.6 已改。
- **计划评审 R2 修订（2026-09-18，2H 全部 accepted-high）**：
  1. StartLedger 效力边界纠错：multi-slice 预算豁免 run（含真实目标 task）**完全跳过 StartLedger**（runner.py L976–997），平台对它们无冻结时点新鲜度门与预算门；时点真实性与授权核查改为**宿主责任**，文档不再暗示存在不存在的平台拒绝（§3.1/§5.1/§5.5/§9）。
  2. `settle_source_run` 调用合同纠错：真实签名 `settle_source_run(*, run_root, stop_reference, readback)` 无 `base_url` 参数，且全仓唯一 readback 构造是 `http_readback`，无"空读回"形态——照抄 CLI 语义恒传 `http_readback(base_url, admin_key)`，删除"不读回"分支（§5.6）。
  3. 次要修正：终态 run 错误码为 `outer_input_channel_unavailable`（无 `run_not_active`，§5.2）；`.host-launches` 写入与 reaper 翻转须原子落盘（§6.2）。
- **计划评审 R3 修订（2026-09-18，1H accepted-high + 2 假设登记）**：
  1. StartLedger 豁免边界在证据面上的精确化：run 内 `evidence/start-ledger.jsonl` 的 reservation 事件对**一切 schema v2 task** 都写（runner.py L1282–1291 条件仅为 `schema_version == 2`），L976–997 的豁免只决定**全局** StartLedger（runs-root `.<req>-start-ledger.jsonl`）是否创建/记账。故豁免 run 的可核验特征是：**全局台账无该 run 记录 + run 内 reservation 行无台账身份/时点字段**；§5.5 措辞同步纠正（豁免 run 的 `freeze_started_at` 不入任何记录，错值无痕，宿主自律）。
  2. 假设登记（低风险，开发/L0 期核验）：L0 材料只读拷贝若不含 `.recovery-locks/<root>.lock`，origin.json 守卫的锁面证据保真度受限——开发实现时将锁文件随目录一并只读拷贝（或在 §5.6 记录保真局限）；L0 前须先在 `workspaces/modeling-run-ledger.md` 登记授权批次。
- 本设计为最小功能设计：只封装既有通道，不新增建模编排或业务状态机；安全关键实现细节集中附录 A

## 1. 目标

S2 在既有 `modeling-team-host` stdio MCP 服务（`modeling_team/host_ops_mcp.py`）与本地操作层
（`modeling_team/host_ops.py`）上新增 8 个宿主工具，覆盖需求动作表 S2 行：

| # | 工具 | 封装的既有通道 | 语义要点 |
| --- | --- | --- | --- |
| 1 | `start_run` | CLI `python -m modeling_team run` | 显式 run ID / Task / Profile / model profile(/overlay) / scope / 可选 base-url / 真实 `freeze_started_at`；受管子进程启动并登记；返回启动结果与查询入口（`get_run_status`/`get_run_events`），不阻塞至建模结束 |
| 2 | `pause_run` | 外层 FIFO `pause` 信封 | 复用 S1 §5/§9 受控提交；暂停 ≠ 停止 |
| 3 | `resume_live_run` | 外层 FIFO `resume` 信封 | 同线程继续，不重建线程、不热加载 |
| 4 | `stop_run` | 外层 FIFO `stop` 信封 | 终止并收尾，沿用既有 cleanup 语义，不新增删除捷径 |
| 5 | `inspect_checkpoints` | `checkpoints.inspect_checkpoints`（本地只读） | 列出全部或按包查看，含 production_resume_bindings / verify 结果；只读 |
| 6 | `save_checkpoint` | 外层 FIFO `checkpoint save` 信封（host/Coordinator 保存） | 复用 015 selector/kind 合同；不改冻结成果、不补历史检查点 |
| 7 | `resume_from_checkpoint` | CLI `checkpoint resume`（production/acceptance） | 必须显式源 run + 显式 checkpoint ID + 新 run ID；production 计 1 次 fresh start，acceptance 计 0 次；不覆盖源 run |
| 8 | `settle_source_run` | 既有 `checkpoint_recovery.settle_source_run`（进程内） | 只登记既有受控停止证明；不得凭"找不到进程"宣告停止或清除未知写入 |

目标效果：

1. 宿主从已知 run ID（或显式参数）出发，经 MCP 完成"启动 → 观察 → 暂停/继续/停止 → 检查点查看/保存 → 检查点接续 → 源 run 收口登记"闭环，常规交互无需手写 Python、不接触 FIFO 路径、不拼底层信封。
2. 每个工具返回可核验证据（提交回执、启动/接续证据、查询入口），严格区分 `submitted / accepted / rejected / unknown`；启动被接受 ≠ 语义开始已发生。
3. 请求关联与幂等复用 S1 §5 机制；错误复用 Runner 原码透传 + 少量新的生命周期/检查点操作层码。
4. 真实语义启动/接续仍受既有授权台账约束；接口层不新增、不放宽建模次数硬门。

## 2. 非目标（继承需求非目标与 S1 设计 §1）

- 不做 HTTP 服务化、网页管理端、远程/多租户、通用 SDK、后台任务队列、跨机器调度、自动监控/拉活。
- 不做自动批准、自动修复、自动重试、自动清理/GC、自动换模型；不重开写门。
- 不新建 RBAC/用户系统；不把宿主工具加入生产 Modeling/Protocol/Coordinator 或 Consumer 工具目录。
- 不改任何既有 CLI 合同（`run`/`baseline`/`checkpoint inspect|resume|settle-source`、保留 CLI `classify-failure`/`authorize-*`/`publish-handoff` 均原样）。
- 不新增建模次数代码硬门，也不把旧额度规则施加到 v3。
- 不迁移旧 run，不为旧 run 补身份/存活记录。
- 除 §3.4 的一处最小回注改动外，不改 S1 已交付查询面与 Runner 其它路径。
- 不覆盖需求动作表之外的动作；不支持的动作/模式返回原因，不静默切换。

## 3. 当前代码事实与缺口（2026-09-18 核对，主代理复核）

### 3.1 可直接复用（无改动）

- S1 操作层：`host_ops.py` 的 `resolve_run_root`（run_id 单段 + `relative_to(runs_root)` 路径收容）、`submit_fifo_action`（终态守卫、FIFO stat、request_id 去重/冲突、有界写入、`control/host-requests.jsonl` 提交台账）、`_process_observation`（三分证据：记录状态 / 进程观察 / `fifo_present` 事实）、`content_digest`、`ACTION_EVIDENCE`。
- S1 MCP 层：`host_ops_mcp.py` 12 工具 + `_call()` 结果信封封装（`{ok, data|error}`）。
- 生命周期：`__main__.py` `run` 子命令参数为 `--profile --task --task-overlay --model-profile --run-id --scope --base-url --freeze-started-at --enable-outer-input-fifo`（L2780–2796，**无** authorization/session-timeout/baseline 参数）；外层动作分发 `receive_outer`（runner.py ≈L3860 起，pause/resume/stop 分支 ≈L4093–4115，不校验未知额外字段）。
- 检查点：`checkpoints.py` `CHECKPOINT_KINDS`、`save_checkpoint`（≈L390，`content_signature` 去重排除 `request_id`）、`inspect_checkpoints`（≈L733，本地只读，返回 `consumes_semantic_start: False` 与两种接续模式的 `semantic_starts` 1|0）；`checkpoint_recovery.py` `settle_source_run`/`settlement_record_path`/`POSSIBLY_LIVE_STATES`/`acquire_root_run_lock`/`http_readback`/`chain_writer_lock_report`。
- 接续：`checkpoint resume` 子命令参数含 `--run-id --checkpoint-id --new-run-id --mode --session-timeout --authorization-reference --base-url --freeze-started-at --enable-outer-input-fifo`（L2882–2930）。
- 启动纪律：`start_ledger.py` `reserve()`（run_id 唯一、单一在途预约、预算耗尽、上次 start 需终态失败）与 `_validate_freeze_time`（tz-aware ISO-8601；冻结→启动 ≤20 分钟门；未来偏移 ≤1 分钟）。**但其效力有边界（评审 R2 纠错 + R3 精确化）**：`prepare` 对 multi-slice 预算豁免 run（task `multi_slice_workflow: true` → `multi_slice_budget_exempt`，runner.py L976–997 注释明言）**跳过全局 StartLedger**（runs-root `.<req>-start-ledger.jsonl` 不创建/不记账）——真实目标 task（`r3-0-006-real-full-cq-checkpoints`，v2 + multi_slice）即属此类：平台对它们**没有**冻结时点新鲜度门与预算门（AGENTS.md：平台不得以次数硬门代替用户授权）。注意 run 内 `evidence/start-ledger.jsonl` 的 reservation 事件对**一切 schema v2 task** 仍写（L1282–1291 条件仅为 `schema_version == 2`），只是豁免 run 的 reservation 行无全局台账身份；且豁免 run 的 `freeze_started_at` 仅做 v2 非空检查、不入任何记录。因此对此类 run，**冻结时点真实性与授权核查由宿主负责**（§5.1/§5.5 的"绝不造值/绝不复用旧时点"是操作层与宿主纪律合同，不依赖平台拒绝）；S2 不因豁免而新增平台硬门，也不得向调用方暗示存在不存在的平台拒绝。
- 基线：`runner.prepare`（≈L887）内部派生 baseline manifest 并以 `StartLedger.baseline_hash` 记账；任务要求的基线预览/保存继续走保留 CLI `baseline`（`--run-id --profile --task …`），`start_run` 不新增基线平台硬门。
- 凭据通道：`__main__.py` 所有 `checkpoint` 子命令要求环境变量 `ONTOLOGY_PLATFORM_ADMIN_API_KEY`（≈L2941）；非 formal scope 由 `_bootstrap_helpers` 从后端 DB 铸 key。

### 3.2 缺口 → S2 需要新增的部分

1. **无受管子进程启动**：现宿主只能与"已由 CLI 启动"的 run 交互。S2 新增受管启动（§6）。
2. **`save_checkpoint` 的双 `request_id` 冲突点（已定位的真实坑，主代理核对修正）**：checkpoint 信封的 015 溯源 `request_id` 是**顶层键**，而 S1 共享准入包装在分发前无条件 pop 顶层 `request_id`（`__main__.py` L248–250、L341–353）——不处置则 015 manifest 溯源字段静默丢失。处置见 §7.3（单一 ID + checkpoint 分支回注）。
3. **run 目录由 prepare 创建，早于其存在**：受管启动崩溃在 prepare 之前时无任何 run 内登记可读。处置：runs 根级 `.host-launches/<run_id>.json`（§6.2）。
4. **重复 run ID**：`runner.prepare`（≈L886）报 `run directory already exists`；宿主侧需在启动前给出可定位的已知状态/冲突，而不是让调用方解读子进程退出。

### 3.3 环境事实（用于测试计划与真实 L0）

- 后端 venv：`/home/yangxiang/ontology-platform/backend/.venv/bin/python`（含 `mcp`，Python 3.14.3，含 yaml）→ 受管启动用 `sys.executable -m modeling_team`。
- `.claude/modeling-team-host-mcp.json` 仅 command/args/cwd，无 env 块；S2 不得加入凭据（§8）。
- runbook S1 节（`skills/modeling-dev-loop/references/team-runbook.md` L495–556）的冷启动自检明确"S2 工具名不得出现" → S2 交付必须同步改写该节与自检期望（20 个工具）。
- 真实接续素材在 worktree：`…/runtime-checkout-auth018-2/workspaces/modeling-runs/` 下 `r30006-20260917-auth020-start1`（**51 个检查点包：48 materialization_progress + 2 scenario_mapped + 1 cq_frozen**；执行时须重数）、`…-resume1b`（2 包）、`…-resume2`（1 包 `materialization_progress-0001`，51 receipts/51 intents，root=自身）。源 run 已 CLEANED；接续链 start1 → resume1b → resume2 已有真实先例，`recovery/origin.json` 记录授权引用字符串形如 `auth-r3-0-020/resume1 (user-approved 2026-09-17 ~21:45 CST …)`。
- 接续链风险：auth020 的 value 层材料晚于检查点 0048，且清理记录含 `Build Session Ontology ownership drifted` / `no_in_flight_attempts:false` → 真实接续可能被 015 以 `write_unreconciled`/`scope_drift`/`artifact_changed` 拒绝。该风险进入测试计划 §5 的门与回退。

### 3.4 Runner 侧改动结论（主代理核对修订：一处最小回注）

`receive_outer` 的 pause/resume/stop 分支不校验未知额外字段；`checkpoint` 分支自校验字段
（`_handle_checkpoint_outer` ≈L10969：`invalid_checkpoint_command`/`checkpoint_invalid_kind`/
`invalid_checkpoint_request`），其 015 溯源 `request_id` 取自**顶层**。S1 的共享准入包装
（`_outer_input_receipt_recorder`）在分发前 pop 顶层 `request_id`，使 checkpoint 分支恒见
`None`——015 manifest 溯源被静默吞掉。

修订处置：共享准入包装在 pop 并构造回执后，**当 `action == "checkpoint"` 且 pop 到了合法
`request_id` 时回注 `message["request_id"] = request_id`** 再分发。效果：

- 该单一 ID 同时充当 S1 关联 ID（提交台账 + 回执）与 015 manifest 溯源 ID（两个面各自记录同一 ID）；
- 其它动作（user/question/issue_resolution/recover_provider/cq_*）信封与现行**逐字节一致**（不回注）；
- S1 层重放守卫仍按"同 ID 同 digest 返原结果、不重写 FIFO"拦截重复 save；015 的
  `content_signature` 去重本就排除 `request_id`，不受影响。

这是本轮唯一 Runner 侧改动（预计 3 行 + 回归测试）；若实现中发现其它信封/回执缺口，按
"最窄缺口 + T0 记录"另立变更，不并入本设计默认范围。

**实现不变量（评审 R1 补充）**：回注必须插在 `_outer_input_receipt_recorder` 内
`digest = content_digest(message)` **之后**、构造回执记录之前——Runner 侧 digest 按 pop 后
（无 `request_id`）信封计算，与宿主侧 `content_digest`（同样剥离 `request_id`）保持同形；
若先回注再算 digest，两侧 digest 分叉，所有 checkpoint 重放会在 S1 幂等判定处误报
`request_id_conflict`。测试须断言"回执 digest == 提交台账 digest"。

## 4. 总体架构

```
宿主 Agent ──stdio MCP──▶ modeling-team-host (host_ops_mcp.py, 12+8=20 工具)
                                │ _call() → {ok, data|error}
                                ▼
                        host_ops.py 操作层（扩展：启动管理 + 新动作封装）
                        ├── submit_fifo_action（既有）→ 外层 FIFO 信封 pause/resume/stop/checkpoint
                        ├── checkpoints.inspect_checkpoints（既有，只读）
                        ├── checkpoint_recovery.settle_source_run（既有，进程内）
                        ├── subprocess 受管启动 → python -m modeling_team run | checkpoint resume
                        └── runs 根级登记：.host-launches/<run_id>.json + stdout/stderr 日志
                                                        run 内：control/host-supervisor.json（S1 既有，零改动读取）
```

- **分层不变**：MCP 层只做参数/结果映射与 `_call()` 信封；语义判断留在 Runner/Coordinator/既有 015 代码；操作层不做业务语义判断。
- **复用优先**：生命周期三动作与 save_checkpoint 完全走 `submit_fifo_action`（含去重、冲突、有界写入、提交台账、回执）；inspect/settle 走既有本地入口；resume 走既有 CLI 子进程。
- **新增面最小**：新增仅两类文件级产物——runs 根级 `.host-launches/`（宿主所有）与启动日志；两者都落在 runs 根内，受 §8 路径收容约束。

## 5. S2 动作合同

通用约定（适用于全部 8 工具，不再逐条重复）：

- 结果信封 `{ok, data|error}`；`error = {code, object?, reason, retryable, next_action}`；Runner/015 原码**透传优先**（如 `checkpoint_incomplete`、`artifact_changed`、`source_active`、`write_unreconciled`、`scope_drift`、`approval_binding_changed`、`acceptance_binding_changed`、`checkpoint_kind_mode_mismatch`）。
- 变更类请求必带 `request_id`（S1 §5 语义）：同 ID 同 digest 已确认 → 返回原结果（不重写 FIFO）；同 ID 异 digest → `request_id_conflict`；结果不明 → `unknown` + `next_action` 指向 `get_request_result`，不自动重发。
- run_id 一律经 `resolve_run_root` 收容；路径类参数（task/profile/overlay/scope）一律收容于仓库根内（§8）。
- 操作层不判断业务语义；不因工具成功推断建模进展、写入安全或验收结论。

### 5.1 `start_run`

- 输入：`run_id`（新，单段）、`task`、`profile`、`model_profile`、`scope`、`freeze_started_at`（必填，取本轮真实冻结开始记录）、可选 `task_overlay`、`base_url`（http/https）、`request_id`。
  **不提供** `authorization_reference`/`session_timeout`/`baseline_ref`：前两者不是 `run` 子命令参数；基线由 run 内部派生记账，任务要求的基线预览/保存由宿主按既有合同走保留 CLI `baseline`（不经本工具、不加新平台硬门）；授权来源按 S1 惯例登记宿主台账。
- 行为：
  1. 预检（全部为**无副作用**检查，按序短路）：run_id 形状/路径收容；路径类输入不在仓库根内 → `input_path_invalid`；`freeze_started_at` 非 tz-aware ISO-8601 → `freeze_started_at_invalid`；`base_url` 协议非法 → `launch_arguments_invalid`。**缺失/形状非法的 `freeze_started_at` 一律拒绝（`freeze_started_at_invalid`），绝不用当前时间或近似时间补值**；编造/旧时点的**拒用是宿主纪律**（测试计划 S2-START-004b：工具必须接受形状合法的时点，不得暗示平台校验）——时点真实性核查是宿主责任：非豁免 run 由既有 ledger 20 分钟门裁决，multi-slice 豁免 run 平台无此门（§3.1），操作层只做形状校验、不暗示存在平台拒绝。然后按 run_id 占用状态分流：run 目录已存在 → 返回已知状态（附 `get_run_status` 快照引用）并报 `run_id_already_exists`；`.host-launches` 记录存在且进程观察为活 → `run_launch_in_progress`；记录存在但进程已死且无 run 根 → `run_launch_failed`（附原记录与日志引用；不自动清除宿主记录，陈旧记录的删除由宿主按 runbook 显式手工执行，工具不隐式覆盖）。
  2. 受管启动：构造 `[sys.executable, -m, modeling_team, run, --run-id …, --task …, --profile …, --model-profile …, --scope …, --freeze-started-at …, --enable-outer-input-fifo]`（可选 overlay/base-url 按 CLI 原名透传，不静默丢弃），按 §6 启动并登记。
  3. 返回：`{run_id, launched: true, pid, supervisor_ref?, launch_record, baseline_evidence: {manifest: "<run-root>/baseline-manifest.json（run 根出现后可定位）", hash_ref: "evidence/start-ledger.jsonl reservation 的 baseline_hash"}, query: {status: "get_run_status", events: "get_run_events"}, note: "launch accepted ≠ semantic start happened", semantic_start_evidence: "见 evidence/semantic-start.jsonl（真实语义开始时异步产生；start-ledger.jsonl 只有预约/结算事件，不代表语义已开始）"}`。
- 关键行为（对 A08）：validate/baseline/run 同一 Task/Profile/模型（CLI `validate` 为保留入口，宿主预检不重复其职责），不静默丢参；重复 ID 不多开 run、不隐式停旧 run、不改 ID；工具返回后原运行通道按既有进程托管方式可用（FIFO 已建立、`get_run_status` 可查）；不承诺跨宿主退出/重启存活。
- 不做的事：不轮询等待首个 semantic start；不为调用方"补"授权；不在失败后自动重试或换新 ID。

### 5.2 `pause_run` / `resume_live_run` / `stop_run`

- 输入：`run_id`、`request_id`；`stop_run` 可选 `reason`（**仅记录在宿主提交台账/digest 中，Runner 的 stop 分支不消费该字段**——文档与实现均不得暗示 Runner 读取它）。
- 行为：封装 `submit_fifo_action`（action = `pause` / `resume` / `stop`），完整继承 S1 §5 提交台账/回执、§9 有界写入（open ≤3s、write ≤3s、整体 ≤10s）与错误码；终态 run 沿用 `submit_fifo_action` 既有 `outer_input_channel_unavailable` 拒绝（host_ops.py L1618–1626，**无** `run_not_active` 码）。
- 返回：`{run_id, request_id, action, status: "submitted", consumption_evidence, next_action: "get_request_result"}`。
- 关键行为（对 A09）：三动作语义分开；stop ≠ pause；stop 携带既有收尾（cleanup、未知写入保留原对账边界），不新增删除资源捷径；resume 仅表达存活线程继续，不重建线程、不热加载代码或冻结输入；`resume_live_run` 对已退出 run 返回明确限制（不静默转为 015 接续）。

### 5.3 `inspect_checkpoints`

- 输入：`run_id`、可选 `checkpoint_id`。
- 行为：直接调用既有 `checkpoints.inspect_checkpoints`（本地只读），透传结果（包清单或单包详情，含 production_resume_bindings、verify 结果、`semantic_starts` 语义计数说明）。
- 返回：`{run_id, checkpoints|checkpoint, read_only: true, observed_at}`。
- 关键行为：不改任何冻结产物、不触发恢复、不做平台写入或模型调用；inspect 产生的诊断性落盘属既有 015 行为，宿主不额外包装或转移其位置。

### 5.4 `save_checkpoint`

- 输入：`run_id`、`request_id`（单一 ID，语义见 §7.3）、`command`（`save`，默认）、`kind`、`checkpoint_id`/scope selector（按 015 合同）、可选 `scope_refs`。
- 行为：封装 `submit_fifo_action(action="checkpoint", command="save", request_id=…, …)`；kind/selector 校验留在 Runner（`checkpoint_invalid_kind` 等原码透传）；共享准入包装按 §3.4 回注 `request_id` 供 manifest 溯源。
- 返回：`{run_id, request_id, action: "checkpoint", status, consumption_evidence, next_action}`。
- 关键行为（对 A10）：不改冻结成果、不补历史检查点；`content_signature` 写门与去重（排除 `created_at/checkpoint_id/request_id`）完全沿用既有实现；同 `request_id` 重放由 S1 层拦截，不产生第二次 save。

### 5.5 `resume_from_checkpoint`

- 输入：`source_run_id`、`checkpoint_id`（**必须显式**，绝不自动选最新）、`new_run_id`（新，单段）、`mode`（`production` | `acceptance`）、`authorization_reference`（宿主台账引用，原样透传 CLI）、`freeze_started_at`（**production 必填**——schema v2 Task 在 `prepare_from_checkpoint` 路径同样硬性要求显式冻结时点（runner.py L866），取**新 run 真实冻结窗口开启的真实记录**（宿主在发起接续时刻记录的真实时点，非编造）；**源 run 旧时点不得复用**——非豁免 run 会被 ledger 20 分钟门拒绝；multi-slice 豁免 run 平台无此门，且豁免 run 的该时点仅做 v2 非空检查、**不入 reservation 或任何记录**（run 内 reservation 行不含时点字段）——错值不会留下任何可事后察觉的痕迹，宿主必须自律拒用（评审 R3 纠错：风险是"错值无痕"，不是"污染 reservation"）；acceptance 模式不接受该参数）、可选 `request_id`、`session_timeout`（仅 acceptance 模式有意义，透传）。
- 预检（无副作用）：凭据预检（`ONTOLOGY_PLATFORM_ADMIN_API_KEY` 缺失 → `host_credential_missing`，不启动子进程后再失败）；`checkpoint_id` 未显式给 → `checkpoint_id_required`；`new_run_id` 已存在 → `run_id_already_exists`；`mode=production` 且缺 `freeze_started_at` → `launch_arguments_invalid`；`mode=acceptance` 且带了 `freeze_started_at` → `launch_arguments_invalid`；`freeze_started_at` 形状非法 → `freeze_started_at_invalid`。
- 行为：受管启动 `[sys.executable, -m, modeling_team, checkpoint, resume, --run-id <source_run_id>, --checkpoint-id <checkpoint_id>, --new-run-id <new_run_id>, --mode <mode>, --authorization-reference <authorization_reference>, --enable-outer-input-fifo]`（production 另加 `--freeze-started-at <值>`；acceptance 可另加 `--session-timeout <值>`。**注意 `--run-id` 即源 run**（`__main__.py` L3167 `source_root = runs_root / args.run_id`），不存在 `--source-run` 参数；`--enable-outer-input-fifo` 默认加，使接续 run 可继续被宿主交互），登记同 §6。
- 返回：`{new_run_id, source_run_id, checkpoint_id, mode, launched, pid, supervisor_ref?, launch_record, semantic_starts_note: "production=1 / acceptance=0（以 015 实际判定为准）", query}`。
- 关键行为（对 A10）：对账/隔离/根 run 锁/旧证据保留全部沿用 015；不覆盖源 run；被 015 拒绝时原码透传（`source_active`、`write_unreconciled`…），宿主不自动重试、不换检查点、不换新 run ID 绕过。

### 5.6 `settle_source_run`

- 输入：`source_run_id`、`stop_reference`（既有受控停止证明引用，必填）、`base_url`（默认 `http://127.0.0.1:8001`）、可选 `request_id`。
- 行为（**已裁决：进程内调用；评审 R2 修正调用合同**）：凭据预检同上后，进程内调用既有 `checkpoint_recovery.settle_source_run(*, run_root=…, stop_reference=…, readback=http_readback(base_url, ONTOLOGY_PLATFORM_ADMIN_API_KEY))`。**照抄 CLI 语义**（`__main__.py` L2546–2552）：该函数签名无 `base_url` 参数、`readback` 为必填关键字参数，且全仓唯一 readback 构造是 `http_readback`——**不存在"空读回"形态**，操作层不得自造 stub readback（stub 不可达会把每个已知 Build Session 判为 obstacle 使 settlement 恒拒；stub 伪造可达则静默绕过"不凭找不到进程宣告停止"守卫）。与 CLI 共用同一函数与同一落盘路径 `.recovery-settlements/<run_id>.json`（既有路径，不变更）。
- 返回：`{source_run_id, settled: true|false, settlement_record, refusals?}`；拒绝原码透传（含 `POSSIBLY_LIVE_STATES`、未知写入未对账等）。
- 关键行为：只登记既有证明；**不凭"找不到进程"宣告停止**，不清除未知写入，不做授权判定。

## 6. 受管启动与进程登记

### 6.1 启动方式

- `subprocess.Popen(args, cwd=<仓库根>, env=os.environ（继承，宿主侧可含 ADMIN key）, stdout/stderr=宿主所有日志文件, start_new_session=True)`；`sys.executable` 取当前解释器（venv 一致性由测试保证）。
- **reaper 守护线程（评审 R1 补充）**：每次受管启动后由操作层起一个 per-launch daemon 线程调用 `proc.wait()`（无超时、不阻塞工具调用），子进程退出时把 `.host-launches/<run_id>.json` 的 `status` 翻转为 `exited` 并记 `exit_code`。这是 `exited/exit_code` 字段的唯一观察者，同时避免长驻 MCP 服务进程积累 zombie；工具调用自身永不 join、永不等待该线程。
- 不做守护、不做重启、不做健康巡检；宿主退出后子进程按 `start_new_session` 存续（此时 reaper 随宿主消亡，`exited` 可能不再被写——该限制记入返回的 limitations 语义），符合"不承诺自动存活/拉起"。

### 6.2 两级登记（解决"prepare 未建 run 根"）

1. **runs 根级**：`.host-launches/<run_id>.json`，schema `modeling-team-host-launch/v1`：`{run_id, kind: "run"|"checkpoint_resume"|"checkpoint_settle", argv 摘要（不含凭据）, pid, started_at, host_session_ref, log_paths:{stdout,stderr}, status: "launched"|"exited"（仅 reaper 线程翻转，§6.1）, exit_code?, recorded_at}`；同目录 `<run_id>.out.log` / `<run_id>.err.log`。`.host-launches/` 沿用 `.recovery-locks/`、`.recovery-settlements/` 的 runs 根点目录先例。
2. **run 内**：`control/host-supervisor.json`（S1 §7.1 既有 schema `modeling-team-host-supervisor/v1`：pid/started_at/session_ref）由**启动操作本身**写入：launch op 在写完 `.host-launches` 记录后，对 run 根的出现做**有界非阻塞轮询（总计 ≤10s，间隔 0.5s）**——run 根在此窗口内出现则写 supervisor 并返回含 `supervisor_ref` 的完整结果；超时则不等待，返回 `launched: true` + 观察限制说明（进程观察暂 unknown，`get_run_status` 稍后可查），不报失败、不阻塞至建模结束。S1 `_process_observation` **零改动**即可消费。写入采用"存在即不改写"的幂等规则（已存在且 pid 一致则跳过；不一致不覆盖，改报 `run_launch_in_progress` 供人工裁决）。`.host-launches` 记录的写入与 reaper 线程的 `exited` 翻转均须**原子落盘**（沿仓库 `_atomic_json` 先例：临时文件+rename，防撕裂读）。

### 6.3 存活证据语义

启动返回后，`get_run_status` 的三分证据自动覆盖新 run：记录状态（state.json/事件）、进程观察（优先 `host-supervisor.json`，恢复类 run 用 `chain_writer_lock_report`；prepare 前崩溃无 run 根时为 `run_not_found` + `.host-launches` 记录可定位）、`fifo_present` 仅作事实。启动被接受 ≠ 语义开始；**首次真实 semantic start 证据以 run 内 `evidence/semantic-start.jsonl` 为准**（异步出现，接口只给入口不等待；`evidence/start-ledger.jsonl` 只含 reservation/presemantic_release/terminal_settlement 事件，**不得**作为语义已开始的依据）。

## 7. 请求关联、幂等与结果语义

### 7.1 继承 S1 §5

`control/host-requests.jsonl` 提交台账 + `evidence/outer-input-receipts.jsonl` 回执；同 ID 同 digest 复用原结果，同 ID 异 digest `request_id_conflict`；`unknown` 优先于臆断成功/失败。

### 7.2 结果四态

`submitted`（送入通道）/ `accepted`（Runner 或既有执行入口确认）/ `rejected`（明确拒绝，原码透传）/ `unknown`。启动类：`launched` 属于 submitted 级事实，语义开始由后续 run 证据确认；子进程创建/退出码 0 一律不得报为建模完成。

### 7.3 `save_checkpoint` 的单一 `request_id` 语义（主代理核对修订，替代 planner 原双 ID 方案）

- 现状事实：015 checkpoint 信封溯源 `request_id` 为**顶层键**；S1 共享准入包装在分发前无条件 pop 顶层 `request_id`。二者在同一键位上不可并存，独立第二参数在传输层不可达。
- 处置：`save_checkpoint` 使用**单一顶层 `request_id`**；共享准入包装按 §3.4 对 `action=="checkpoint"` 回注该键。该 ID 同时记录在：
  - `control/host-requests.jsonl`（S1 提交台账）与 `evidence/outer-input-receipts.jsonl`（S1 回执）；
  - checkpoint manifest 的 `request_id`（015 溯源）。
- 幂等与去重不受影响：S1 层按"同 ID 同 digest 返原结果"拦截重放（不重写 FIFO）；015 `content_signature` 去重排除 `request_id`，ID 变化不破坏内容去重。
- 测试须断言：回执与 manifest 记录同一 ID；其它动作信封不回注（逐字节一致）；同内容异 ID 的重复 save 仍被 `content_signature` 去重。

## 8. 边界与隔离（A07）

- 宿主工具只在 `.claude/modeling-team-host-mcp.json` 暴露；不进入生产 Modeling/Protocol/Coordinator、Consumer、独立验收方工具目录。S2 交付后该文件仅追加工具注册，仍无 env 块、无凭据、无隐藏材料路径。
- 路径收容：run_id 经 `resolve_run_root`（单段 + `relative_to(runs_root)`）；task/profile/overlay/scope 经统一的 `resolve_repo_path`（仓库根内，含 symlink 解析后复核）；`base_url` 仅 http/https；违规 → `input_path_invalid`/`launch_arguments_invalid`，不执行、不读取。
- 泄漏面：错误与摘要不含隐藏题/答案/凭据；受管启动日志与 `.host-launches` 记录不含 argv 中的敏感值（凭据只经环境变量传递，不入记录）。
- 独立验收方只能得到原合同允许的证据与验收输入，得不到创建/继续/修复被验收 run 的控制能力（新增工具不出现在其配置）。

## 9. 错误分类

新增操作层码（最小集，`retryable` 语义明确、不承诺无副作用重试除非证明）：

| code | 场景 | retryable | next_action |
| --- | --- | --- | --- |
| `run_id_already_exists` | run 目录/启动记录已存在（附已知状态引用） | false | `get_run_status` 或换显式新 run ID |
| `run_launch_in_progress` | 同 ID 在途启动且进程观察为活 | false | `get_run_status` 稍后复查 |
| `run_launch_failed` | 子进程未成功创建/立即退出；或预检发现旧启动记录进程已死且无 run 根（附原记录与日志引用） | false（排查后人工） | 读 `.host-launches` 日志；陈旧记录由宿主按 runbook 手工清除后可重用该 run ID（工具不自动清除、不隐式覆盖） |
| `freeze_started_at_invalid` | 缺失/非 tz-aware/明显非法 | true（更正后） | 提供本轮真实冻结开始记录 |
| `input_path_invalid` | 路径参数逃逸仓库根/runs 根 | false | 更正参数 |
| `launch_arguments_invalid` | 必填缺失/互斥/协议非法 | true（更正后） | 按 reason 补齐 |
| `host_credential_missing` | resume/settle 缺 `ONTOLOGY_PLATFORM_ADMIN_API_KEY` | true（注入后） | 宿主环境注入，不改仓库配置 |
| `checkpoint_id_required` | resume 未显式给 checkpoint ID | true | 显式指定，不自动选最新 |

既有码透传：S1 §9 全集、`request_id_conflict`、Runner 外层动作码、015 全部检查点/接续码、`prepare` 的 run 目录冲突（若未被预检拦截）、start ledger 预算/冻结时点原码（**仅非豁免 run 存在**，§3.1）。不新增通用"执行失败"折叠码。

## 10. 兼容与投放

- CLI 合同不变：`run`、`baseline`、`checkpoint inspect|resume|settle-source` 及保留 CLI 全部原样；宿主可继续用 CLI 启动的 run 走 S1 通道（S1 独立性保持）。
- runbook：`team-runbook.md` S1 节扩为 S1+S2（20 工具清单、启动纪律、真实冻结时点来源、授权引用登记格式 `auth-<batch>/<action> (user-approved <time>)`、接续/settle 时机、凭据注入方式——只写环境变量名，不写值）；冷启动自检改为"恰为 20 个 S1+S2 工具"。
- 配置：`.claude/modeling-team-host-mcp.json` 仅追加 8 个工具注册（无结构变化）。
- 投放顺序（实现落点）：① `host_ops.py` 新增启动管理与 8 个 op 函数 + 单测 → ② `__main__.py` 共享准入包装 checkpoint 回注（§3.4，唯一 Runner 侧改动）+ `host_ops_mcp.py` 注册 8 工具 + 契约测试（20 工具）→ ③ runbook/文档 → ④ 确定性测试全绿 → ⑤ 真实 L0（测试计划 §5）。
- 回滚：新增为纯增量（新工具 + `.host-launches/` 点目录 + 一处回注）；移除工具注册与回注即回到 S1 行为，runbook 恢复自检表述。

## 11. 验收映射

| 验收 | 本设计落点 | 主要证据 |
| --- | --- | --- |
| A07 (S1+S2) | §8 隔离；配置无凭据；新增工具不外溢 | 配置 diff、工具目录断言（恰 20 工具、生产/Consumer/验收配置不含）、错误文本扫描 |
| A08 | §5.1 + §6 | 启动参数透传断言；重复 ID 冲突；`freeze_started_at` 缺失/非法格式拒绝（时点合理性与伪造处置见 §5.1/§5.5 豁免边界：平台无合理性门，宿主纪律保证）；启动后 `get_run_status` 可交互；`evidence/semantic-start.jsonl` 真实 semantic-start 证据（真实 L0；R1 纠错后的证据文件） |
| A09 | §5.2 | 三动作回执与后续状态各自可观察；stop 后 run 终态、pause 后仍可 resume；代码/挂载未重载不报修复生效 |
| A10 | §5.3–5.6 | inspect 只读；save 复用 015 写门/去重且溯源 ID 双面一致；production/acceptance 接续计数与隔离；settlement 记录；unknown 写门未被绕过；旧证据保留 |

## 12. 实现落点（文件级）

| 文件 | 改动 |
| --- | --- |
| `modeling_team/host_ops.py` | 新增：`resolve_repo_path`、启动管理（`launch_managed_run`、`.host-launches` 读写、supervisor 幂等写入）、8 个 op 函数、新错误码常量 |
| `modeling_team/host_ops_mcp.py` | 注册 8 工具（`TOOL_NAMES` 12→20）、docstring 风格与 `_call()` 复用 |
| `modeling_team/__main__.py` | 共享准入包装 checkpoint 分支回注 `request_id`（§3.4，唯一 Runner 侧改动，~3 行 + 回归测试） |
| `skills/modeling-dev-loop/references/team-runbook.md` | S2 节 + 冷启动自检改 20 工具 |
| `.claude/modeling-team-host-mcp.json` | 仅追加工具注册（无凭据） |
| `modeling_team/tests/test_host_ops_s2.py`、`test_host_ops_mcp.py`（扩展）、`test_managed_launch.py`、`test_outer_input_receipts.py`（回注回归） | 新增/扩展测试 |
| `docs/delivery/designs|test-plans/2026-09-18-r3-0-016-s2-*.md` | 本设计与测试计划 |

## 附录 A：安全关键实现细节（仅列不变量）

1. 所有路径参数先解析后使用：`Path(...).expanduser().resolve()` 后必须 `is_relative_to(runs_root)`（run_id）或仓库根（输入引用）；拒绝 `..`、绝对路径逃逸、symlink 落点逃逸。
2. FIFO 写入沿用 S1 §9 硬上限：open（O_NONBLOCK+poll）≤3s、单次 write ≤3s、单工具 ≤10s；`fifo_line_too_large` 上限沿用 S1。任何情况下不得为等确认而阻塞至终态。
3. 凭据只经进程环境传递；`.host-launches` 记录、启动日志、错误文本、`next_action` 中不得出现 key 值；仓库配置文件不加 env。
4. 重复启动防护：预检 + `.host-launches` 记录 + run 根存在性三重判断；任何分支都不得隐式 stop 旧进程或删除旧 run 根。
5. `start_new_session=True` 后宿主不持子进程句柄等待；不得在工具调用内 join 建模全流程。
6. supervisor 文件"存在即不改写"；发现 pid 冲突时不得覆盖证据，只报冲突。
7. `unknown` 优先：任何超时/部分写/子进程异常，结果一律 `unknown` + 证据引用，不改报失败重试，不隐式换新 request_id。

### 代码锚点（2026-09-18 HEAD 01396e2，行号为约值）

`modeling_team/__main__.py`：`_KNOWN_OUTER_ACTIONS`（≈L161–184）、`_outer_input_receipt_recorder`（L230–266，pop 顶层 `request_id`）、共享包装 pop 点（≈L341–353）、run 子命令参数（L2780–2796）、`checkpoint resume` 参数（L2882–2930）、checkpoint 子命令凭据门（≈L2941）。
`modeling_team/runner.py`：`receive_outer`（≈L3860；pause/resume/stop ≈L4093–4115）、`_handle_checkpoint_outer`（≈L10969，溯源 `request_id` 取顶层 ≈L11012）、`prepare` run 目录冲突（≈L886）与内部 baseline 派生（≈L887–897）、v2 Task 必填 `freeze_started_at`（≈L865）、`prepare_from_checkpoint`（不接受冻结时点手填覆盖之外的新语义）。
`modeling_team/checkpoints.py`：`CHECKPOINT_KINDS`、`save_checkpoint`（≈L390）、`inspect_checkpoints`（≈L733）。
`modeling_team/checkpoint_recovery.py`：`settle_source_run`、`settlement_record_path`、`POSSIBLY_LIVE_STATES`、`acquire_root_run_lock`、`http_readback`、`chain_writer_lock_report`。
`modeling_team/start_ledger.py`：`reserve`、`_validate_freeze_time`（20 分钟 / 1 分钟未来偏移）。
`modeling_team/host_ops.py`：`resolve_run_root`、`submit_fifo_action`、`_process_observation`、`content_digest`、`ACTION_EVIDENCE`。
`modeling_team/outer_input.py`：FIFO 0600/0700、keeper fd、fail-closed。
