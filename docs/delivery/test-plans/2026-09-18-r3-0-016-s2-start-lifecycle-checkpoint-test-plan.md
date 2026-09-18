# R3.0-016 S2 共享测试计划（启动 / 生命周期 / 检查点封装）

- 日期：2026-09-18；需求：§R3.0-016，S2 覆盖 A07–A10
- 配套设计：`docs/delivery/designs/2026-09-18-r3-0-016-s2-start-lifecycle-checkpoint-design.md`
- **主代理核对修订（2026-09-18）**：随设计修订三处——`start_run` 契约删去 `authorization_reference`/`session_timeout`/`baseline_ref`（`run` 子命令无这些参数，基线由 run 内部派生记账）；`save_checkpoint` 改单一 `request_id`（回执与 manifest 同 ID，依赖 §3.4 checkpoint 回注），原 `checkpoint_request_id` 双 ID 用例作废；开放决策①②已裁决（settle 进程内、resume 默认带 FIFO），决策区改为处置记录。
- **计划评审 R1 修订（2026-09-18，1C/4H 全部 accepted-high）**：`resume_from_checkpoint` 用例按真实 CLI 合同重写（`--run-id`=源 run、无 `--source-run`、production 必填 `--freeze-started-at`）；A08 补基线证据用例；S2-START-003/005 期望改为可达错误码；§2.7 去掉 `-x` 改失败清单比对；补回注 digest 一致性断言与启动时序/退出观察用例；真实 L0 执行序把冻结时点记录放在预检之后。
- **计划评审 R2 修订（2026-09-18，2H 全部 accepted-high）**：StartLedger 豁免边界（multi-slice run 无台账门→时点真实性改宿主责任；S2-START-008 限定非豁免 fixture、新增 S2-START-011）；`settle_source_run` 调用合同照抄 CLI（恒传 `http_readback`，删"不读回"分支）；§2.1 隔离改沿 S1 `repository_root=` 先例；L0 执行 checkout 落位（main 新 checkout + 源素材只读拷贝）与 settle 预期拒绝（G2 gap）写入 §5；`.host-launches` 原子写。
- **计划评审 R3 修订（2026-09-18，1H accepted-high + 2 假设登记）**：豁免边界断言面纠错——run 内 reservation 事件对一切 v2 task 都写（runner.py L1282–1291），S2-START-011 改为"全局台账无记录 + reservation 无台账身份/时点字段 + 返回无 ledger 语义"，与 S2-START-009 共存；S2-START-004 拆分（缺失/非法格式→工具级形状码；>1min 未来→S2-START-008 透传 ledger 原码；伪造时点→S2-START-004b 宿主纪律断言）；D0 删"ledger 唯一权威"措辞；§5 拷贝补充 `.recovery-locks/<root>.lock` 随带要求；设计 §5.5"污染 reservation"措辞同步纠正（实际是时点无痕）。
- 基线：S1 测试计划（I Round 1–4 + 真实 L0 auth-r3-0-021 start1：L0-1 11/12，L0-2 未达，#31/#32 已修复入主仓 01396e2）
- 用法：开发自测与独立功能验收共用 §1–§4、§7；真实 L0 用 §5。基线失败比对按"失败清单"而非总数（当前已知 ~7 个 test_deepseek_codex_runtime 失败、23 个 r23006 失败源于缺 acceptance-ticket.json）。

## 1. 证据分层

| 层 | 证据 | 本计划位置 |
| --- | --- | --- |
| D0 | 静态核对（现状事实、锚点、参数/旗标存在性） | §7 |
| M | 确定性单测/契约测试（tmp run 根、真实 FIFO 对象、进程内 MCP 客户端、子进程替身） | §3 |
| I | 独立功能验收（M 用例盲跑 + 基线失败清单比对 + 隔离/泄漏扫描） | §4 |
| L0 | 真实授权运行中的接口闭环 | §5 |

fixture 形态规则：所有信封/回执/manifest 形态必须来自真实 Runner/015 代码路径产出，不得手写臆造字段。

## 2. 测试数据与隔离

1. **tmp run 根**：每个用例独立 `tmp_path` 作为 runs 根，经既有 S1 先例注入（`resolve_run_root`/操作层函数的 `repository_root=` 参数或 monkeypatch，**无** `MODELING_TEAM_RUNS_ROOT` 环境变量——评审 R2 假设核实），互不共享；用例结束不清理平台侧资源（无平台写入）。
2. **真实 FIFO**：生命周期/保存类用例构造真实 `OuterInputFifo`（S1 惯例），不 mock 传输层；断言 `control/host-requests.jsonl` 与 `evidence/outer-input-receipts.jsonl` 内容。
3. **进程内 MCP 客户端**：经 stdio 内存通道调用；新增契约测试 `test_cold_start_exposes_exactly_the_20_s1_plus_s2_tools`，同时断言生产/Consumer/验收工具目录配置**不含**任何 S2 工具名（A07）。
4. **受管启动替身**：`launch_managed_run` 注入 fake launcher（记录 argv、返回可控 pid/Popen 替身），覆盖崩溃-before-prepare、立即退出、正常启动三类；`.host-launches/`、supervisor 写入、日志路径均断言。仅"真实 python -m modeling_team 可被拉起"一条用例用真子进程 + 秒级退出的无害命令（如 `--help`），不产生真实 run。
5. **路径收容矩阵**：`../`、绝对路径逃逸、symlink 指向 runs 根/仓库根之外、多段 run_id（含 `/`）。
6. **凭据**：resume/settle 用例在无 `ONTOLOGY_PLATFORM_ADMIN_API_KEY` 时必须报 `host_credential_missing` 且未创建子进程/未调用 settle；注入假值时不得出现在任何记录/日志/错误文本（扫描断言）。仓库配置文件断言无 env 块。
7. **基线比对**：`backend/.venv/bin/python -m pytest modeling_team/tests -q -rf` 全量跑（**不加 `-x`**，须产出完整失败清单），与已登记基线失败清单 diff（新增失败=缺陷；既有失败须能对应到已登记原因）。

## 3. 确定性用例

命名：`S2-<域>-<序>-<成功|边界|失败|回归>`。

### A 组（A08，start_run）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| S2-START-001-成功 | 成功 | 合法参数 + fake launcher | argv 与输入一一对应且**恰为** `run` 子命令实有参数（`--profile --task [--task-overlay] --model-profile --run-id --scope [--base-url] --freeze-started-at --enable-outer-input-fifo`；无 authorization/session-timeout/baseline 等幻参数）；`.host-launches/<id>.json`+日志生成；返回含 run_id/pid/query 入口、baseline_evidence 定位引用与 "launch accepted ≠ semantic start" note、semantic_start_evidence 指向 `evidence/semantic-start.jsonl` |
| S2-START-002-成功 | 成功 | run 根出现后写 supervisor | run 根在 ≤10s 有界窗口内出现 → `control/host-supervisor.json` 写入且 `get_run_status` 进程观察可用（S1 零改动读取）；run 根未出现 → 返回 launched+观察限制说明，不报失败、不阻塞（模拟 prepare 慢：>窗口） |
| S2-START-003-边界 | 边界 | prepare 前崩溃 | `get_run_status` 报 `run_not_found`（resolve_run_root 无 run 根）；`.host-launches` 记录与日志可定位失败原因；不抹其它记录 |
| S2-START-004-边界 | 边界 | 缺 `freeze_started_at` / 非法格式（非 ISO/非时间戳字符串） | 工具级 `freeze_started_at_invalid`；**绝不自动补当前时间**；不创建子进程（评审 R3 拆分：op 层仅做形状校验；时点合理性用例移 S2-START-008，伪造时点改宿主纪律断言 S2-START-004b） |
| S2-START-004b-边界 | 边界 | 显式传入编造/旧时点（豁免 run fixture，形状合法） | 工具**必须接受**该参数且不补值、不改写、不得在任何返回/记录中暗示平台校验过时点（宿主纪律断言，评审 R3：豁免 run 时点不入任何记录，错值无痕） |
| S2-START-005-失败 | 失败 | 已存在 run ID（有 run 根 / 记录+进程活 / 记录+进程死且无 run 根） | 分别为已知状态+`run_id_already_exists` / `run_launch_in_progress` / `run_launch_failed`（附原记录与日志引用）；旧进程未被停、旧 run 未被改写、未另起 ID；死记录不经工具自动清除 |
| S2-START-006-失败 | 失败 | 路径参数逃逸 / base_url 非 http(s) / 必填缺失 | `input_path_invalid` / `launch_arguments_invalid`；无副作用 |
| S2-START-007-回归 | 回归 | S1 通道对 CLI 启动 run 仍可用 | S1 12 工具行为不变（复用 S1 用例抽样） |
| S2-START-008-成功 | 成功 | ledger 拒绝（预算耗尽 / 20 分钟门 / 冻结时点未来 >1min）透传——**限定非豁免 fixture**（formal 非 multi-slice v2 task） | 原 ledger 错误码（`start_ledger.py` `reserve`/`_validate_freeze_time`）经启动日志/状态可定位、**不经工具改写为自有码**（评审 R3：>1min 未来属 ledger 校验，非 op 层形状校验），宿主不加第二道硬门、不重试、不换 ID |
| S2-START-011-边界 | 边界 | multi-slice 豁免 run 的台账豁免边界（评审 R2 提出、R3 纠错断言面） | 对 `multi_slice_workflow: true` 的 v2 fixture 与 S2-START-009 共存核验：**全局** StartLedger（runs-root `.<req>-start-ledger.jsonl`）无该 run 记录（runner.py L976–997 豁免）；run 内 `evidence/start-ledger.jsonl` 的 reservation 事件**仍存在**（一切 v2 task 都写，L1282–1291）但**不含台账身份/冻结时点字段**；`start_run` 返回不含 ledger 校验语义；冻结时点仅形状校验，真实性由宿主纪律保证（S2-START-004b） |
| S2-START-009-成功 | 成功 | 基线证据可定位且与记账一致（A08） | run 根 `baseline-manifest.json` 存在且与 start-ledger reservation 的 `baseline_hash` 一致；`start_run` 返回的 `baseline_evidence` 引用可定位到二者；不要求 S1 `get_run_status` 面变化 |
| S2-START-010-成功 | 成功 | 子进程退出观察（reaper） | 子进程退出后 `.host-launches` status 翻转 `exited`+exit_code；工具调用期间永不阻塞等待退出；无 zombie 残留（用例进程表断言） |

### B 组（A09，pause/resume/stop）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| S2-LIFE-001-成功 | 成功 | 三动作各自提交（真实 FIFO） | `status:"submitted"` + 回执；`get_request_result` 可查 accepted；三者后续状态可区分 |
| S2-LIFE-002-边界 | 边界 | stop 后再 pause / resume_live_run 对已退出 run | 终态守卫码 / 明确限制（不静默转 015 接续） |
| S2-LIFE-003-边界 | 边界 | FIFO 缺失/写超时/超长行 | S1 §9 三码透传，≤10s 返回，不永久挂起 |
| S2-LIFE-004-失败 | 失败 | 同 request_id 异 digest | `request_id_conflict`，不改写 FIFO |
| S2-LIFE-005-成功 | 成功 | 同 request_id 同 digest 重放 | 返回原结果，无第二次写入 |
| S2-LIFE-006-回归 | 回归 | stop 收尾语义 | cleanup 既有行为保留；未知写入仍需原对账，无删除捷径；代码/挂载未重载不得报修复生效 |

### C 组（A10，inspect/save/resume/settle）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| S2-CKPT-001-成功 | 成功 | inspect 全部 / 单包 | 只读（run 根 mtime+内容 hash 不变）；含 production_resume_bindings 与 verify 结果 |
| S2-CKPT-002-成功 | 成功 | save_checkpoint 单一 `request_id` 双面落账（修订版） | S1 回执（`evidence/outer-input-receipts.jsonl`）与 checkpoint manifest `request_id` 为**同一 ID**（§3.4 回注生效）；**回执 `content_digest` == 提交台账 `content_digest`**（回注在 digest 计算之后，两侧同形）；同内容重放被 S1 层拦截不二次写 FIFO；异 ID 同内容仍被 `content_signature` 去重 |
| S2-CKPT-002b-回归 | 回归 | 回注仅限 checkpoint 分支 | `user`/`issue_resolution` 等其它动作信封不回注，行为与 S1 逐字节一致；`action=="checkpoint"` 但无 `request_id` 时与旧行为一致 |
| S2-CKPT-003-失败 | 失败 | 非法 kind/selector/命令 | Runner 原码透传（`checkpoint_invalid_kind`/`invalid_checkpoint_command` 等），宿主不改写 |
| S2-CKPT-004-成功 | 成功 | production resume（fixture run + fake launcher） | argv 恰为 `checkpoint resume` 实有参数：`--run-id <source_run_id>`（**源 run**）`--checkpoint-id --new-run-id --mode production --authorization-reference --freeze-started-at --enable-outer-input-fifo`（**无 `--source-run`**）；登记齐全；`semantic_starts` 说明 1 |
| S2-CKPT-005-成功 | 成功 | acceptance resume | argv 同上但 `--mode acceptance`、无 `--freeze-started-at`（带则拒绝）、可带 `--session-timeout`；`semantic_starts` 0 |
| S2-CKPT-005b-失败 | 失败 | production 缺 `freeze_started_at` / acceptance 带了 `freeze_started_at` | 均 `launch_arguments_invalid`（预检拒绝，无子进程）——schema v2 Task 在接续路径同样硬性要求显式冻结时点 |
| S2-CKPT-006-失败 | 失败 | 未给 checkpoint ID / 源 run 活跃(`source_active`) / 对账拒绝(`write_unreconciled`/`scope_drift`/`artifact_changed`) | `checkpoint_id_required` 或原码透传；源 run 未被覆盖；未自动换包/换 ID/重试 |
| S2-CKPT-007-成功 | 成功 | settle-source（既有受控停止证明，进程内） | `.recovery-settlements/<run_id>.json` 登记，返回记录路径；与 CLI `checkpoint settle-source` 产出同形 |
| S2-CKPT-008-失败 | 失败 | settle 无 stop_reference / 疑似活 run / 未知写入未对账 | 原拒绝透传；**不得凭"找不到进程"宣告停止** |
| S2-CKPT-009-失败 | 失败 | resume/settle 缺凭据 | `host_credential_missing`，无子进程/未调用 settle，无部分写入 |
| S2-CKPT-010-回归 | 回归 | 旧证据保留 + unknown 写门 | resume 后源 run 证据与检查点未变；写门未绕过 |

### D 组（A07-S2，隔离与泄漏）

| ID | 类型 | 用例 | 期望 |
| --- | --- | --- | --- |
| S2-ISO-001-成功 | 成功 | 工具目录断言 | 宿主配置恰 20 工具；生产/Consumer/验收目录 0 个 S2 工具 |
| S2-ISO-002-失败 | 失败 | 全参数收容矩阵 | 全部 `input_path_invalid`/`launch_arguments_invalid`，无文件读取/命令执行 |
| S2-ISO-003-失败 | 失败 | 泄漏扫描 | 错误文本、`.host-launches`、日志、`next_action` 中无凭据值、无隐藏题/答案内容 |
| S2-ISO-004-边界 | 边界 | 配置文件形态 | 仍无 env 块；仅追加工具注册 |

## 4. 完成门（确定性 vs 真实证据，分开陈述）

- **G1 确定性完成门（I 验收 PASS 条件）**：§3 全部用例按预期；基线失败清单无新增；契约测试证明 20 工具与隔离；文档（runbook S2 节、设计）与实现一致。
- **G2 真实证据门（不并入 I 验收）**：A08 的"启动后可查询真实 semantic-start 证据"、A10 的"真实接续推进"由 §5 提供；未能达成时按 §5.6 记录 gap，**不阻塞 S2 交付与 I 验收**，但需求整体完成状态不得标 PASS（沿需求"各自独立功能验收及真实 L0 通过后才可称本需求完成"）。

## 5. 真实 L0（授权批：1 次 fresh semantic start，模型 glm-5.3-flash high）

### 5.1 授权与目标

- 新授权批（auth-r3-0-021 剩余 2 次已撤销作废，不沿用；本轮用户授权 1 次，2026-09-18）：**1 次 fresh semantic start**，模型 `glm-5.3-flash` high；授权来源按建模 run 台账惯例登记（`auth-<batch>/<action> (user-approved <时间>)`）。
- 用户裁决（2026-09-18）：**第一轮真实建模优先使用既有检查点**——优先将授权用于 `resume_from_checkpoint`（production，计 1 次 fresh start），接续既有检查点；仅当 §5.4 门不通过才回退 fresh `start_run`（此时 resume 侧记 gap）。取不到真实证据的那个启动类动作按用户裁决走确定性验收 + 真实 L0 缺口记录，不阻塞 S2 交付。

### 5.2 接续素材（2026-09-18 只读核对，执行时重验）

- 位置：worktree `/home/yangxiang/ontology-platform/workspaces/auth-r3018-20260917/runtime-checkout-auth018-2/workspaces/modeling-runs/`
- `r30006-20260917-auth020-start1`：**51 包**（48 materialization_progress + 2 scenario_mapped + 1 cq_frozen；以执行时实数为准）；manifest 绑定 model `glm-flash-high`、task `r3-0-006-real-full-cq-checkpoints`、profile `r3-0-011-competency-question`、project `0f3e6332-69c2-4e04-bc8a-ef954da6d51c`。
- `…-resume1b`（2 包）、`…-resume2`（1 包 `materialization_progress-0001`，51/51 receipts/intents，root=自身）。
- 已有真实接续链先例：start1 → resume1b → resume2（origin.json 含授权引用字符串）。
- 环境：素材在 worktree、台账在主仓（`workspaces/modeling-run-ledger.md`）；执行 checkout 需含 S2 实现 + 主仓 #31/#32 修复（01396e2）。
- **执行 checkout 落位（评审 R2 假设核实）**：`resume_from_checkpoint` 要求源 run 根位于**执行 checkout** 的 `workspaces/modeling-runs` 下；现有素材 worktree 的 `runner.py` 缺 #31 修复，不得直接作执行环境。落位方式：以主仓 main（含 S2 实现）新建执行 checkout/worktree，把候选源 run 目录**只读拷贝**进其 `workspaces/modeling-runs/`（原素材不动，保留证据）；执行前核对拷贝完整性（目录条目数一致）。**随拷贝一并带上的点目录**：`.recovery-locks/<root>.lock`（评审 R3 登记——origin.json 守卫的锁面证据；若执行 checkout 复用既有 `.recovery-locks/` 则原样保留；无法带上时须在 L0 记录中声明锁面证据保真局限）。

### 5.3 执行序列

1. 冷启动自检：恰 20 个 S1+S2 工具；生产/Consumer/验收目录无 S2 工具。
2. `inspect_checkpoints`（真实 run）：核对包数、production_resume_bindings、verify 结果（只读，不产生写痕迹）。**全部预检与门核查完成之后**才记录新 run 的冻结时点。
3. `resume_from_checkpoint`（production）：源 run=`…-resume2`（或 start1，按 §5.4 门择优）、显式 checkpoint ID、显式新 run ID、authorization_reference 按台账格式；**新冻结时点 = 发起接续时刻宿主记录的真实时点**（非编造、非源 run 旧时点——目标 task 为 multi-slice 豁免 run，平台无 20 分钟门（评审 R2），**宿主必须自律在记录后立即送入、不复用旧时点**；预检已在第 2 步完成）；凭据经环境变量注入。
4. 同一存活 run 上依序演练（每步 `get_run_status`/`get_run_events`/`get_request_result` 核验）：`pause_run` → `resume_live_run` → `save_checkpoint`（单一 request_id 双面断言）→ `inspect_checkpoints`（确认新包）→ `stop_run`。
5. `settle_source_run`：**预期被拒（评审 R2 假设核实，预先记录避免误判缺陷）**——两个候选源 run 均 `state: CLEANED`（不在 `POSSIBLY_LIVE_STATES`），且 resume2 带 `recovery/origin.json`（显式拒绝链上 run settle）；该工具在真实 L0 预计无成功证据，按原码记录拒绝原因，走 §5.6 G2 gap，不伪造 stop_reference。
6. 台账登记：授权来源、真实消耗（1 次 fresh start）、工具级结果、缺陷编号。

### 5.4 执行时门（任一不满足 → 回退 fresh `start_run` 并记 resume gap）

- 平台 project / Build Session 仍存活（admin-key 只读核查）。
- 目标包 verify 通过、production_resume_bindings 可用。
- Task/Profile 快照与当前一致；无未对账未知写入拦截（015 判定为准）。

### 5.5 成功判据

- L0-1（接续路径）：resume 被接受并在新 run 产生 ≥1 步真实进展（新检查点或新事件），全程无手写 Python/无 FIFO 手拼。
- L0-2（同 run 生命周期）：pause/resume/save/inspect/stop 各自可观察且结果语义正确。
- L0-3（回退路径，如走 fresh start_run）：`start_run` 启动成功、`get_run_status` 可交互、出现真实 semantic-start 证据（`evidence/semantic-start.jsonl`；`start-ledger.jsonl` 的 reservation 不算语义开始）；resume 侧以"证据不支持接续"记录 gap，并附 015 原码。

### 5.6 gap 记录与清理

- 任何未走通动作记录：动作、请求 ID、原码、证据路径、归因（接口缺陷 / 运行时缺陷 / 证据不支持），不判定为 S2 接口 PASS/FAIL。
- 清理：停止真实 run（`stop_run`）；撤销/轮换本次注入的 admin key；确认 `.host-launches` 日志与台账无凭据残留；不删除运行目录证据。

## 6. 决策处置记录（原"开放决策"，主代理已裁决）

1. `settle_source_run` 子进程 vs 进程内 → **进程内调用**（凭据门语义保留；与 CLI 共用同一函数与落盘路径）。
2. `checkpoint resume` 是否支持 `--enable-outer-input-fifo` → **支持**（argparse L2924–2930 已有）；`resume_from_checkpoint` 默认携带，使接续 run 可继续被宿主交互。
3. `checkpoint_request_id` 缺省格式 → **作废**（§7.3 修订为单一 `request_id`，无第二参数）。
4. 真实 L0 优先源 run → 维持"按 §5.4 门执行时择优"（用户已裁决优先检查点接续路径本身）。
5. 授权批 → 本轮用户授权 1 次 fresh start（2026-09-18），台账新开授权批登记；auth-r3-0-021 剩余额度已作废不沿用。

## 7. D0 记录（本轮核对，2026-09-18，主代理复核）

- 主仓 HEAD `01396e2` 含 S1 与 #31/#32 修复；`host_ops.py`/`__main__.py` 与 worktree 逐字节一致，`runner.py` 仅差 #31 结算块（不触及 S2 路径）。
- `_outer_input_receipt_recorder` 无条件 pop 顶层 `request_id`（L248–250）+ `_handle_checkpoint_outer` 顶层取溯源 `request_id`（≈L11012）→ 单一 ID + checkpoint 回注（设计 §3.4/§7.3，用例 S2-CKPT-002/002b）；**回注插入点必须在回执 digest 计算之后**（评审 R1 假设 1）。
- `checkpoint resume` 实参语义（评审 R1 纠错）：`--run-id` = **源 run**（`__main__.py` L3167 `source_root = runs_root / args.run_id`），`--new-run-id` = 新 run；**无 `--source-run`**；production 必填 `--freeze-started-at`（v2 Task，runner.py L866）；`--authorization-reference`、`--enable-outer-input-fifo` 已有（L2882–2930）；checkpoint 子命令凭据门 ≈L2941。
- 真实 semantic-start 证据 = `evidence/semantic-start.jsonl`（runner.py L2358–2368）；`evidence/start-ledger.jsonl` 只含 reservation/presemantic_release/terminal_settlement（评审 R1 纠错）。
- 基线落盘：run 根 `baseline-manifest.json`（runner.py L1277）+ start-ledger reservation 的 `baseline_hash`（评审 R1 补）。
- `settle_source_run` 为模块级函数（`checkpoint_recovery.py` L627），`readback` 为**必填**关键字参数；进程内调用可行，`base_url` 默认 `http://127.0.0.1:8001`（评审 R1 假设 3）。
- Runner stop 分支不消费 `reason` 字段（仅读 run_id/text/agent_id/role/wait_id）——`stop_run` 的 reason 仅宿主台账记录（评审 R1 假设 4）。
- **StartLedger 豁免边界（评审 R2 纠错 + R3 精确化）**：`prepare` 对 multi-slice 预算豁免 run 跳过**全局** StartLedger（runner.py L976–997）；真实目标 task 快照为 v2+`multi_slice_workflow: true`（task.snapshot.yaml L40/41/178）→ 无全局台账记账/预算/20 分钟门；但 run 内 reservation 事件对一切 v2 task 都写（L1282–1291），豁免特征 = 全局无记录 + reservation 行无台账身份/时点字段；时点真实性核查为宿主责任（S2-START-008 限定非豁免 fixture，S2-START-011/004b 断言豁免边界）。
- `settle_source_run` 真实签名 `(*, run_root, stop_reference, readback)`（checkpoint_recovery.py L627–632），无 `base_url` 参数；CLI 恒传 `http_readback(args.base_url, admin_key)`（`__main__.py` L2546–2552），全仓无"空读回"形态——工具照抄 CLI 语义（评审 R2 H2）。
- 终态 run 经 `submit_fifo_action` 的既有拒绝码为 `outer_input_channel_unavailable`（host_ops.py L1618–1626），无 `run_not_active` 码。
- 真实 L0 授权批执行前须在 `workspaces/modeling-run-ledger.md` 登记（评审 R2 假设：当前台账末条只有 auth-r3-0-021 作废记录）。
- `run` 子命令实有参数（L2780–2796）：`--profile --task --task-overlay --model-profile --run-id --scope --base-url --freeze-started-at --enable-outer-input-fifo`；**无** authorization/session-timeout/baseline 参数；基线由 `runner.prepare` ≈L887 内部派生并经 `StartLedger.baseline_hash` 记账。
- `checkpoint resume` 实有参数（L2882–2930）含 `--authorization-reference`、`--enable-outer-input-fifo`；checkpoint 子命令凭据门 ≈L2941。
- `prepare` run 目录冲突（runner ≈L886）；对**非豁免** run，ledger 20 分钟/预算门是既有新鲜度与授权校验（`start_ledger.py` `reserve`/`_validate_freeze_time`，S2-START-008 透传原码）；对豁免 run 平台无此门，不得在工具层新增等效硬门（评审 R3 措辞修正：不称"唯一权威"）。
- backend venv `python` 3.14.3 含 `mcp`/yaml → 受管启动用 `sys.executable -m modeling_team` 可行。
- 素材包数实盘 51（planner 计数；主代理初核 49——以执行时重数为准）；台账仅存主仓；runs 根点目录先例（`.recovery-locks/`、`.recovery-settlements/`）支持新增 `.host-launches/`。
- 已知基线失败：r23006 23 项（缺 acceptance-ticket.json）、test_deepseek_codex_runtime ~7 项；比对按清单。

## 8. 独立验收 Round 1（2026-09-18，requirement_tester 独立盲跑）

### 8.1 被测状态与环境

- 工作树（未 commit，即被测状态）：`M modeling_team/__main__.py`、`M modeling_team/host_ops.py`、`M modeling_team/host_ops_mcp.py`、`M modeling_team/tests/test_host_ops_mcp.py`、`M modeling_team/tests/test_outer_input_receipts.py`、`?? modeling_team/tests/test_host_ops_s2.py`、`?? modeling_team/tests/test_managed_launch.py`，外加交付文档与无关改动（`skills/modeling-dev-loop/SKILL.md`、`skills/modeling-dev-loop/references/team-runbook.md`、`.codex/agents/`、`docs/diagrams/modeling-team-guide/`）。基点 HEAD `01396e2`。
- 运行时：`backend/.venv/bin/python`（venv 含 `mcp`/yaml）。全程未使用 `uv run`（记忆：checkout 内 `uv run` 缺 yaml/mcp 必败）。
- 方法：先审后测——先通读 S2 diff 对照设计 §3.4/§5/§6/§9 记录偏差，再自建独立 harness 盲跑 §3 全部 A/B/C/D 用例（自行构造 fixture 与断言，不依赖开发自测）；全程未改任何产品代码。

### 8.2 执行命令与总体结果

1. 独立套件（覆盖 §3 全部确定性用例，22+ 用例 ID，38 个测试节点）：
   `cd /home/yangxiang/ontology-platform && PYTHONPATH=/home/yangxiang/ontology-platform backend/.venv/bin/python -m pytest /tmp/r3016s2_i/test_i_r3016s2_round1.py -q -rf`
   → **38 passed in 4.51s**（0 failed）。
2. 全量基线比对（§2.7，不加 `-x`）：`backend/.venv/bin/python -m pytest modeling_team/tests -q -rf`
   → **7 failed, 1994 passed, 1 skipped, 339 subtests passed in 126.33s**。
   失败清单 7 项全部为 `modeling_team/tests/test_deepseek_codex_runtime.py`（`test_fallback_file_rejects_missing_or_malformed_assignment` ×5、`test_fallback_file_rejects_group_or_other_permissions` ×2）＝已登记基线原因。**无新增失败**；此前登记的 23 项 r23006 失败本轮全部通过（按失败清单比对，不计总数）。
3. 真实子进程探针（S2-START-008 端到端路径）：真 launcher `subprocess.Popen(sys.executable -m modeling_team run …, start_new_session=True)` + 真实 `.host-launches` 日志读取（见 8.5）。
4. 独立 harness 为临时文件（`/tmp/r3016s2_i/`），本轮结束已删除；证据摘要落在本节。

### 8.3 逐用例结果（§3 全部 ID）

| 计划 ID | 判定 | 关键证据（独立断言） |
| --- | --- | --- |
| S2-START-001 | PASS | argv 与输入一一对应且恰为 `run` 实有参数集；`run --help`/`checkpoint resume --help` 真子进程旗标全集覆盖、无幻参数；`.host-launches/<id>.json`+`.out.log`/`.err.log`（`log_paths` 恰 {stdout,stderr}）；返回含 run_id/pid/query/`baseline_evidence`/`semantic_start_evidence`/note "launch accepted ≠ semantic start happened"/`observation_limitation` |
| S2-START-002 | PASS | run 根出现后 `control/host-supervisor.json` 写入（schema `modeling-team-host-supervisor/v1`，pid=子进程，start_new_session）；`get_run_status` 以 `liveness.process_observation.basis == "host_supervisor"` 原样消费（S1 面零改动） |
| S2-START-003 | PASS | prepare 前崩溃 → `get_run_status` 报 `run_not_found`；`.host-launches` 记录+日志可定位（status `exited`/exit_code）；其它记录未被抹 |
| S2-START-004 | PASS | 参数化 5 分支（空串/空白/`2026-09-18 08:00`/`not-a-time`/naive `2026-09-18T08:00:00`）均 `freeze_started_at_invalid`，逐分支 reason 文案精确（never substitutes the current time / is not an ISO-8601 timepoint / carries no UTC offset），无子进程、无 run 根、无登记写入 |
| S2-START-004b | PASS | 形状合法的编造时点逐字透传为 `--freeze-started-at`，无补值/改写，返回与登记中无任何"平台校验过时点"暗示 |
| S2-START-005 | PASS | 有 run 根→`run_id_already_exists`；登记+进程活→`run_launch_in_progress`（带 existing/launched pid）；登记+进程死无 run 根→`run_launch_failed`（附原记录与日志引用）；旧进程未被停、旧 run 未改写、死记录不被自动清除 |
| S2-START-006 | PASS | `../`、绝对路径逃逸、symlink 出仓、多段 run_id → `input_path_invalid`；`base_url` 非 http(s) 与缺必填 → `launch_arguments_invalid`；全部无副作用 |
| S2-START-007 | PASS | 真实 run 上 S1 12 工具回归抽样（get_run_status/get_run_events/pause/resume/stop + `owner_answer_rejected` 循环）行为与 S1 一致 |
| S2-START-008 | **PARTIAL（偏差记录，非缺陷）** | 见 8.5 |
| S2-START-009 | PASS | 真 `TeamRunner.prepare` 产物：run 根 `baseline-manifest.json` 存在且与 run 内 `evidence/start-ledger.jsonl` reservation 的 `baseline_hash` 一致；`start_run` 返回的 `baseline_evidence` 可定位二者 |
| S2-START-010 | PASS | reaper 线程独占 waiter：退出后 status 翻 `exited`+exit_code+exited_at；工具调用不 join/不阻塞（用阻塞型 Popen 替身验证 waiter 只发生 1 次且由 reaper 发起）；无 zombie 残留 |
| S2-START-011 | PASS | multi-slice 豁免 run：全局 `.<req>-start-ledger.jsonl` 无该 run 记录（runs 根无任何 `*start-ledger*` 文件）；run 内 reservation 行存在但仅 {baseline_hash,event,recorded_at}、无台账身份/冻结时点字段；`start_run` 返回无 ledger 校验语义 |
| S2-LIFE-001 | PASS | 真 `OuterInputFifo` 上 pause/resume_live/stop 各 `status:"submitted"`+回执，`get_request_result` 可查 accepted，三者后续状态可区分 |
| S2-LIFE-002 | PASS | stop 后 pause/终止态 resume_live_run → `outer_input_channel_unavailable` 明确拒绝，不静默转 015 接续 |
| S2-LIFE-003 | PASS | FIFO 缺失→`outer_input_channel_unavailable`、超长行→`fifo_line_too_large`，均 ≤10s 返回不挂起 |
| S2-LIFE-004 | PASS | 同 request_id 异 digest → `request_id_conflict`（reason 含 recorded content digest），FIFO 无第二次写入 |
| S2-LIFE-005 | PASS | 同 request_id 同 digest 重放返回原结果，无第二次写入 |
| S2-LIFE-006 | PASS | stop 不是结算：未知写入仍被 `write_unreconciled` 拦截，无删除捷径 |
| S2-CKPT-001 | PASS | inspect 全部/单包只读（run 树 digest 前后不变）；含 production_resume_bindings 与 verify 结果 |
| S2-CKPT-002 | PASS | 单一 `request_id` 双面：回执与 manifest 同 ID；回执 `content_digest` == 台账 `content_digest`（回注在 digest 之后，两侧同形）；同内容重放被 S1 层拦截不二次写 FIFO；异 ID 同内容仍被 content_signature 去重（结果标 reused） |
| S2-CKPT-002b | PASS | 回注仅限 `action=="checkpoint"`：`user`/`issue_resolution` 信封行为与 S1 一致；checkpoint 无 `request_id` 时无回执（预置意图经 materialization_progress 验证回执数不变） |
| S2-CKPT-003 | PASS | 非法 kind → Runner 原码 `checkpoint_invalid_kind` 透传，宿主不改写 |
| S2-CKPT-004 | PASS | production resume argv 恰为 `checkpoint resume` 实有参数：`--run-id <源run>` `--checkpoint-id --new-run-id --mode production --authorization-reference --freeze-started-at --enable-outer-input-fifo`，无 `--source-run`；登记齐全；note "consumes 1 semantic start" |
| S2-CKPT-005 | PASS | acceptance：无 `--freeze-started-at`（带则拒）、可带 `--session-timeout`；note "consumes 0" |
| S2-CKPT-005b | PASS | production 缺时点 / acceptance 带时点 → 均 `launch_arguments_invalid`，无子进程 |
| S2-CKPT-006 | PASS | 缺 checkpoint id → `checkpoint_id_required`；接续拒绝原码透传；源 run 证据未被覆盖、不换包/换 ID/重试 |
| S2-CKPT-007 | PASS | settle 进程内调用真实 `settle_source_run`（`http_readback` 语义同 CLI），`.recovery-settlements/<run_id>.json`（0700/0600）与 CLI 同形；二次 settle 原样拒绝（既有结算） |
| S2-CKPT-008 | PASS | 疑似活 run（PREPARING/POSSIBLY_LIVE）→ 原状态门拒绝；control FIFO 在场 → 拒绝障碍（不凭"找不到进程"宣告停止）；未知写入未对账 → `write_unreconciled` |
| S2-CKPT-009 | PASS | 缺 `ONTOLOGY_PLATFORM_ADMIN_API_KEY` → `host_credential_missing`（env 名在 reason），先于子进程/settle，无部分写入 |
| S2-CKPT-010 | PASS | resume/inspect/dedup save 后源 run 冻结证据与检查点未变（树 digest 不变）；写门未绕过 |
| S2-ISO-001 | PASS | MCP stdio 冷启动目录恰 20 工具（12 S1+8 S2），`TOOL_NAMES == S1+S2` |
| S2-ISO-002 | PASS | 见 S2-START-006；生产/Consumer/验收工具面按精确名扫描 0 个 S2 工具名（`backend/app/services/build_sessions.py` 的内部方法 `save_checkpoint` 被 Consumer 工具 `save_build_checkpoint` 包装，非工具面重名，不构成泄漏） |
| S2-ISO-003 | PASS | 错误文本/`.host-launches`/日志/next_action 无凭据值、无隐藏题/答案内容 |
| S2-ISO-004 | PASS | `.claude/modeling-team-host-mcp.json` 保持 command/args/cwd、无 env 块、无凭据（git 未改动）；工具注册在 `host_ops_mcp.py` 代码面恰 20 个 `@mcp.tool` 装饰器——设计 §225/§251/§272"仅追加工具注册（无结构变化）"由代码面注册满足，stdio 配置无 `tools` 数组属正确形态（S1 同形） |

### 8.4 三项开发申报局限复核

1. **S2-START-008 "仅静态扫描"** → 属实且按 G1 口径裁决：补偿证据充分（见 8.5）。
2. **`settle_source_run` 不产生 `.host-launches` 记录** → 与设计一致：该工具是进程内结算（checkpoint_recovery 模块函数，`http_readback` 读回同 CLI），非受管启动，设计/计划从未要求 `.host-launches` 记录；落盘路径为 `.recovery-settlements/<run_id>.json`（S2-CKPT-007 已证）。**非缺陷**。
3. **`.claude/modeling-team-host-mcp.json` 未改且无 tools 数组** → 与设计一致（见 S2-ISO-004 行）。**非缺陷**。

### 8.5 S2-START-008 裁决（真实子进程端到端在当前工作区结构性不可达）

三道既有平台门依次拦截（全部为 Runner/平台既有校验，非 S2 工具新增），每一道的原码文本都逐字落在 `.host-launches/<run_id>.err.log`、记录 `status:"exited"/exit_code:2`、不留 run 根——**工具不改写、不重试、不换 ID、不加第二道门**（这一点由 8.3 各 PASS 用例 + 下列探针共同证明）：

1. 非豁免、非 multi-slice v2 task（`r2-3-002-t` + `r2-3-002-t` profile）+ `--model-profile glm-flash-high` → `validation failed: model profile selection requires a formal run contract`（对应 runner.py 形式合同分支；multi-slice 非豁免 task 走 roster 绑定分支）。
2. formal task（`r2-3-009-formal-acceptance`）+ `--model-profile glm-flash-high`（绑 `competency-question` 而非 formal six）→ `run failed: team model profile role bindings drift`；全仓仅 `deepseek-v4-flash-max`/`openai-luna-medium` 绑 formal six（model-profiles 目录 grep 证实）。
3. formal task + `--model-profile deepseek-v4-flash-max` → `run failed: clean baseline gate rejected non-empty git status`（交付工作树未 commit，即被测状态本身）。

结论：端到端 ledger 门（预算/20 分钟/时点未来）需要一个"formal 合同 + formal-six 绑定 + 干净基线"的执行环境，本工作区结构性不可达，属**环境/交付形态约束**而非代码缺陷。按 G1 确定性门以补偿证据判定达标：真 `StartLedger.reserve` 对 stale/未来时点的原码拒绝码可复现且不被工具改写；runs 根无任何 `*start-ledger*` 全局台账文件（无工具层写入）；静态证实 S2 段新增代码无 `start_ledger`/`.reserve(` 调用；S2-START-011 豁免边界成立；A08b 证明子进程失败原码逐字可定位。
执行备注：探针第 2 步（multi-slice task + glm-flash-high）意外越过校验真正启动了一次 run（run 根已建），已立即 `kill -9` 进程组并删除该 run 根与全部相关 `.host-launches` 文件；随后复核 `.host-launches/`、`.recovery-settlements/` 为空、无 `iprobe*` 目录、无残留进程。

### 8.6 隔离 / 泄漏 / 残留扫描

- 假凭据（本轮独立 harness 生成的随机假值，仅测试进程内存/环境注入，字面值按 §8 卫生规则不落任何记录）在仓库全树 `grep -rl`（排除 `.git`/`.venv`）**0 命中**；任何记录/日志/错误文本/next_action 无凭据值。
- 真实仓库 `workspaces/modeling-runs/.host-launches/` 与 `.recovery-settlements/` 为空；无 `i-round1*`/`iprobe*` run 目录；无残留 `modeling_team run` 子进程；未 commit 任何文件。
- run 内断言：`.host-launches`/supervisor/台账/回执/manifest 均无凭据、无隐藏材料路径（S2-ISO-003）。

### 8.7 与开发自测的差异与备注

- 开发新增套件 `test_host_ops_s2.py`、`test_managed_launch.py` 在全量 run 中全部通过，未发现与开发自测结论相悖之处；本轮无新增缺陷（0 个 P0/P1/P2）。
- 备注 1（非缺陷）：独立 harness 内 A10 测试名误标为 `S2_START_007`，其断言实体是 S2-START-010（reaper）；S2-START-007 的 S1 回归实体由 A07 覆盖。
- 备注 2（非缺陷）：`start_run` 占用门在"记录+进程活"分支要求真实存活 pid，测试用 `_dead_pid()`/阻塞替身构造；与实现语义一致。

### 8.8 G1 判定与结论

- G1 确定性完成门：**达成**——§3 全部用例按预期（S2-START-008 以补偿证据记 PARTIAL，属环境约束而非代码缺陷）；基线失败清单无新增；20 工具与隔离由契约断言证明；runbook S2 节与设计文档核对与实现一致（env 变量名 `ONTOLOGY_PLATFORM_ADMIN_API_KEY`、20 工具、argv 合同、`host-supervisor.json` schema、`.host-launches` 工件、settle 进程内、手工清理纪律逐条吻合）。
- G2 真实证据门：**本轮未执行**（§5 真实 L0 不在独立验收 Round 1 范围，需授权批）。因此需求整体完成状态仍不得标 PASS。
- **I 验收 Round 1 结论：PASS**（确定性面）。无阻断缺陷，无需返工轮次；下一步由主代理决定是否发起 §5 真实 L0 授权批（resume 优先、settle 预期拒绝记 gap）。

---

## 9. 真实 L0 执行记录（2026-09-18，auth-r3-0-022，主代理执行）

**终局：0/1 starts 消耗；两项 start 类动作均被运行时阻断，按 §5.6 记 gap，不判定 S2 接口 FAIL；S2 交付不阻塞（用户既定裁决：确定性验收 + 真实 L0 缺口记录）。授权的 1 次 glm-5.3-flash high start 完整保留。**

### 9.1 已达成（接口侧真实证据，全部在档）

- 冷启动 20 工具自检通过（stdio 会话内 `tools/list`）。
- §5.3 序列的只读段全部真实执行：`inspect_checkpoints`（两来源）、`get_run_status`（run_not_found 语义）、专用 admin key 门 1 只读平台核查（存活校验）。
- §5.4 门评估真实执行：resume2/materialization_progress-0001 = ready / issues [] / production_resume.available true；start1/cq_frozen-0001 = needs_reconciliation → 选 resume2（用户裁决：优先接续检查点）。
- `resume_from_checkpoint`（production）真实发起：请求 ID 在档，被 015 `reconcile_write_tail` 拒绝（write_unreconciled，链 op 未知/in-flight）——015 门按设计工作 → §5.4 回退 fresh `start_run`，resume 侧 gap 归因**平台链状态**（`workspaces/auth-r3016-20260918/resume1-gap.md`，含 015 原码）。
- `start_run` 两次真实发起（start1 pid 641925 / start2 pid 665943）：argv 组装、`.host-launches/*.json`、FIFO 暴露、凭证 env 注入全部符合设计；两次均在语义开始前死亡（见 9.2）。
- `settle_source_run` 对两来源的预期拒绝按设计落地（恢复链来源→source_settlement_refused 仅链锁结算；CLEANED 来源→source_settlement_refused 无活写者）。
- 无手写 Python / 无 FIFO 手拼参与任何 run 交互（全程 S2 MCP 接口）。

### 9.2 缺口（按 §5.6 归因，均非 S2 接口缺陷）

| 动作 | 请求/运行 ID | 原码/现象 | 归因 | 证据 |
|---|---|---|---|---|
| resume_from_checkpoint | r30006-20260918-auth022-resume1 | write_unreconciled | 平台链状态（015 门按设计拒绝） | resume1-gap.md；launch json |
| start_run #1 | r30006-20260918-auth022-start1 | `run failed: app-server closed its output`（语义前，0 token，CLEANED） | 运行时缺陷 | start1-start2-infra-gap.md；.host-launches/*.err.log |
| start_run #2 | r30006-20260918-auth022-start2 | 同上 | 运行时缺陷 | 同上 |

运行时缺陷关联线索：两次失败为 01396e2（#31/#32，2026-09-18T08:10+08:00 入库）之后首批真实 run，失败位点（app-server 初始化完成后首 turn 前静默 EOF）与 #32 park/watchdog 域相邻——**线索非定论**，移交平台运行时排查；详见 `start1-start2-infra-gap.md`。

### 9.3 驱动模式局限（非产品缺陷）

每次 MCP 调用使用冷启动 stdio 会话，managed-launch 的 per-launch reaper 守护线程随服务进程退出，故 `.host-launches/*.json` 的 `status` 未翻转为 exited（进程确实已死，ps 与 err.log 为证）。生产部署为长驻 stdio 会话，不受此影响。

### 9.4 清理

- 真实 run：无存活进程（两次 CLEANED + ps 复核零残留）。
- admin key：auth022-s2-host-admin 于收口时吊销，明文文件删除（见台账）。
- 凭据残留扫描：`.host-launches` 日志与台账无明文凭据。
- 运行目录证据保留：run 根、launch 日志、evidence 全部不删除。
