# Team 启动、观察与恢复参考

供宿主按需读取。下列命令和路径于 2026-09-10 对当前仓库核实；使用时以实际 checkout、
归属需求和 CLI `--help` 为准。不要将此宿主参考挂载给隔离建模角色。

## 选择入口

当前完整 v3 链覆盖 R3.0-006/008B/009/011，使用：

- Task：[r3-0-006-real-full.yaml](../../../modeling_team/tasks/r3-0-006-real-full.yaml)。
- Profile：[r3-0-011-competency-question.yaml](../../../modeling_team/profiles/r3-0-011-competency-question.yaml)。
- 需求：[requirements-v3.0.md](../../../docs/requirements/requirements-v3.0.md)。
- 最新接线说明：[v3 execution gap closure](../../../docs/delivery/designs/2026-09-09-v3-execution-gap-closure-design.md)。
- 授权与轮次：[R3.0-006 attempt record](../../../docs/delivery/records/2026-08-27-r3-0-006-attempt-record.md)。

需要 R3.0-015 检查点时，启动前同时核对开关与验收范围：

| Task | `modeling_checkpoints` | `acceptance_target` |
| --- | --- | --- |
| `r3-0-006-real-full.yaml` | 未启用 | `cq_semantic` |
| [r3-0-015-checkpoint-recovery.yaml](../../../modeling_team/tasks/r3-0-015-checkpoint-recovery.yaml) | `true` | 默认 `full_joint` |

按本轮授权选择 Task；若获准目标仍为 `cq_semantic` 且需要检查点，在本轮 Task 配置中
显式保留 `acceptance_target: cq_semantic` 并启用 `modeling_checkpoints: true`，沿用
已获准的资料、角色和其他参数。不能仅换成 015 Task 就把验收范围扩大为 `full_joint`。
validate、baseline、run 必须绑定同一本轮 Task；已冻结运行不得就地修改 Task。

其他业务或验收阶段选择对应 Task/Profile，不把这一 v3 配置固化为所有建模的合法条件。
旧 002/008B/009 Task 保留各自范围，不能冒充完整 v3 入口。旧
`modeling_team.foreground_monitor` 标为 `ARCHIVAL_ONLY`，不要启动。

## 授权时的模型调度

下列命令于 2026-09-10 对本机核实：`cc-switch --help`、`cc-switch -a claude provider list`、
`cc-switch -a claude provider switch <ID>`；`claude --help` 支持 `--model` 与 `--effort max`。
高峰/非高峰划分是用户指定调度表，不代表已核实官方价格。

每次获得新的建模次数授权，先调用当前时间工具取得真实时间并转换为 Asia/Shanghai 北京时间：
周一至周五 09:00<=t<12:00 或 14:00<=t<18:00 为高峰；12:00、18:00 边界及周末为非高峰。
把取时、时区、是否高峰、选定模型/effort 和授权 ID 写入本轮宿主记录，之后按该记录核对，
不逐个任务重新判定。

ClaudeCode 侧（外部 Claude Code 开发/修复进程；主智能体自身是 Codex，不在切换范围）：

1. 用 `cc-switch -a claude provider list` 的当前标记现场发现 provider，不把机器特定
   provider ID 写进提示或脚本。`provider current` 原样输出带 API Key 片段，不直接原样
   输出或粘贴；确需其字段时先在工具内部捕获，只保留并输出 provider/model/base URL 白名单。
2. 高峰目标 provider 为 glm，实际模型 `glm-5.3-flash`、effort `max`；非高峰目标为
   deepseek，实际模型 `deepseek-flash`、effort `max`。当前 provider 已等于目标时不重复
   switch，但仍核验 model/effort 与记录一致；需要切换时用发现的 ID 执行 switch，并用
   `provider list` 的当前标记复核。
3. 启动前清除会覆盖切换结果的旧 ambient `ANTHROPIC_MODEL`、`ANTHROPIC_BASE_URL` 等模型
   变量；核验只读白名单字段（provider、model、effort、base URL 指向），不打印密钥或
   整份 settings。

Team 侧不经 cc-switch：模型绑定写在 Team 独立 model-profile。高峰 `glm-5.3-flash`、
effort `max`，选用 profile `glm-flash-max`（经 `glm-direct` 路由，与 `deepseek-direct`
同构：角色经宿主 loopback session 访问，密钥不进角色进程）；非高峰 `deepseek-flash`、
effort `max`，选用 profile `deepseek-flash-max`。profile ID 不含模型版本号后缀是因为
`SAFE_ID` 只允许 `[a-z0-9-]`（`openai-luna-xhigh` 对 `gpt-5.6-luna` 是同一惯例），精确
模型串以各角色 `model:` 绑定为准。选用 model profile/overlay 时，validate、baseline、run
使用同一选择，并保留角色实际模型证据与之对应；没有获准的选择则沿用配置，不擅自换模型。

执行环境不支持所需模型/effort 时，把缺口原样反馈给用户，不悄悄替换为可用模型。调度在授权
时选定并适用整个 run：时间跨过时段边界不中断当前 run、不偷偷另开 start，不给已冻结 run
换模型；新一轮授权才重新判定。

## 最小准备与启动

在仓库根执行。先核对用户授权和余额、任务允许的源文件/角色输入、依赖健康、已有写入及
进程状态，并完成上文 [授权时的模型调度](#授权时的模型调度) 的判定与记录。按任务要求冻结
代码/配置/源材料；要求 clean checkout 时使用明确提交或隔离 checkout 保留用户改动，不能
清空工作区来满足前置。复用已有健康与验收证据，不展开全面审计。

隔离 checkout 启动前确认其 `backend/.venv` 可用；优先复用与冻结提交兼容的现有环境，确需
安装时执行 `uv sync --frozen`。这是避免已发生的启动失败的准备动作，不增加平台门禁。
若本轮授权宿主扮演业务方回答者，在 CQ 首次 review 发布前，把同一项目中有来源、仍适用于
当前范围的既有确认通过 `cq_interview` 一次性交给 CQ 角色，并保留来源；不要携带隐藏题答案，
也不要把未获资料支持的内容补成确认。这样可以在第一次公开投影前确定题目可见性。

先按“选择入口”设置 `modeling_task_file` 为本轮已选 Task 路径；沿用
`modeling_team/tasks/r3-0-006-real-full.yaml` 不会自动开启检查点。
配置检查不启动模型，也不写平台：

```bash
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-011-competency-question.yaml \
  --task "${modeling_task_file:?请先设置本轮 Task 路径}"
```

根据本次授权填好 `modeling_run_id`、`modeling_scope_file` 和 `modeling_freeze_started_at`；
scope 复用获准的 create/existing 配置；新建范围可复用
[new-scope-create.yaml](../../../modeling_team/scopes/new-scope-create.yaml)。
时间取本轮真实冻结开始时点，不能编造为满足时间门。
按任务要求使用 `baseline --run-id ... --profile ... --task "$modeling_task_file"` 保存基线；该命令预览基线，
不创建 semantic start。显式 model profile/overlay 被选用时，validate、baseline 和 run
必须使用同一选择；没有该选择则沿用配置，不擅自换模型。

只有授权足够且最小准备完成后才执行：

```bash
uv run --project backend python -m modeling_team run \
  --profile modeling_team/profiles/r3-0-011-competency-question.yaml \
  --task "${modeling_task_file:?请先设置本轮 Task 路径}" \
  --run-id "$modeling_run_id" \
  --scope "$modeling_scope_file" \
  --freeze-started-at "$modeling_freeze_started_at" \
  --enable-outer-input-fifo
```

用宿主工具的可持续进程会话承载命令，记录 session/PID、启动参数和宿主输出位置，及时返回
控制权以读取增量。不要等待整轮退出才处理用户问题，也不要把一次不保活的临时工具调用
误报为后台守护。CLI 从实际源码 checkout 运行，scope 指向的是平台资源，两者都要记录。

环境交接教训（2026-09-10 auth003-start3 证实）：命令继承的环境由宿主工具自身的 workdir
决定，shell 内 `cd` 不改变它。同一宿主在主仓库 workdir 下 shell 带
`http_proxy`/`https_proxy`/`no_proxy`；直接把 workdir 换成 runtime-checkout 后代理键
全部缺席，并沿 `uv`→runner `python`→`bwrap`→`codex` 子进程全部缺席（6 键全 false）；
改为在已验证的宿主 workdir 启动 shell、shell 内 `cd` 到 clean checkout 再运行，三键仍为
true（presence 证据 `workspaces/skill-role-20260910/auth003-start3-proxy-presence.json`、
`auth003-launch-env-correction.json`）。因此工具直接更换 workdir 可能得到与已验环境不同
的环境，已有代理必须实际传到 runner/child 才算交接成功；需要 clean checkout 时从已验证
宿主 shell 启动并在 shell 内 `cd` 即可保留既有环境。核对只记录变量名与 presence，不输出
值或密钥，不写死代理地址；现有 adapter 已正确转发这些键，无需改平台代码。该教训仅在
真实传输失败时用于定位，不新增每次 start 的前置硬门、探针或检查框架。

## 从哪些证据观察

当前 run 根为 `workspaces/modeling-runs/<run-id>/`。先查看实际存在的文件，再读新增完整
JSONL 行；主智能体保存各日志行号/字节偏移，避免每轮重新读全量。末行尚未写完时等下轮，
不要将截断的半行立即归因平台损坏。优先读取元数据，按具体问题才深入对应内容。

| 来源 | 用途与边界 |
| --- | --- |
| 进程会话/PID、宿主 stdout/stderr | 存活、退出、Runner 向宿主交付的问题/错误；没有输出不等于死亡 |
| `state.json` | 顶层生命周期；不是每个 Agent 的实时进展或写入证明 |
| `evidence/app-server-events.jsonl` | 角色工具/turn 事件；可能含完整参数，禁止整份注入生产或修复 Agent |
| `evidence/staged-decisions.jsonl`、`multi-slice-gate.jsonl` | 阶段推进及具体门反馈；缺文件可能只是尚未到该阶段 |
| `evidence/competency-questions.jsonl` | CQ 审核与冻结元数据；私有审核快照只供用户/CQ 通道 |
| `evidence/outer-question.jsonl`、`outer-user.jsonl` | 实际访谈与回答绑定；按当前 run 发出的 ID 处理 |
| `evidence/runtime-failure.jsonl`、`terminal-classification.jsonl` | 第一失败及终态归因；不存在时不要猜出终态 |
| `state.json` 的 `cleanup`、宿主终态输出的清理结果、`evidence/cq-cleanup.jsonl` | 清理/保留证据；状态可能被后续终态覆盖，保留原输出，并用平台 Batch/Attempt 与资源读取核实实际状态 |

每次报告“当前阶段；最近有效进展；在等谁/什么；第一异常；下一动作”，不用重复输出整份日志。
默认 30～60 秒观察一次；若长期推理仍有活动则继续等待，若重复失败则检查同一失败的内容和
依赖是否改变。不要为制造心跳向建模角色反复发送催促消息。

### 角色会话 compaction 后可能永久丧失原生 tool call（2026-09-12 auth009-start1 实证）

长时间 run 的角色会话会自动 compaction。**modeling 型角色可能安然通过，coordinator 可能不
能**：auth009-start1 的 coordinator 在第二次 compaction（17:38:02Z）之后，每个 turn 仍正常
`task_started`/`task_complete`、仍能推理和输出文本，但**再没有发出任何一个原生 tool call**，
而是把 `send_team_message` 序列化成最终消息里的文本标记（先 `<tool_call>{...}</tool_call>`
JSON 方言，宿主提示后改成 `<function_calls><invoke>…` XML 方言，两者都不被执行）。角色自述的
归因是错的——它以为是自己“调用身份被拒绝（unsupported call）”，实际证据里没有任何 rejection，
因为那次调用根本没被尝试。宿主无法补救：外层 action 全集只有
`question | issue_resolution | user | status | pause | resume | stop`，**没有任何重置角色线程
的动作**；`turn_context` 记录在 compaction 前后逐字节相同，说明工具目录没丢，是模型侧行为。

识别特征（长 run 应持续监控，命中即按致命处理，不要继续等）：

- `deliveries.jsonl` 行数在角色 turn 持续 `task_complete` 的情况下**不再增长**；
- 角色会话 JSONL 在某个时间点之后**零 `function_call` item**，但 assistant 消息文本里出现
  `<tool_call>` / `<function_calls>` / `<invoke` 标记；
- 该角色在断点前不久有 `compacted` 事件。

auth009-start1 因此损失约 30 分钟：coordinator 三次 re-dispatch 都没发出任何 delivery，
idle-inquiry 每 300 秒循环唤醒、每次产出新的文本方言。宿主发一条明确的诊断便签（“你的调用被
写成了文本、从未执行，请用原生 tool call 重发”）**不足以恢复**。正确处置是判定
`TERMINAL_BLOCKED_RUNTIME_DEFECT` 并 `stop` 收尾，不要让它继续空转；`stop` 后 `state=CLEANED`、
`zero_residue=true`，run 根证据完整保留（见 auth009-start1-terminal-record.md）。

## 外层输入与恢复边界

`run --enable-outer-input-fifo` 创建 `<run-root>/control/outer-input.fifo`。用当前
[CLI](../../../modeling_team/__main__.py) 与 [Runner](../../../modeling_team/runner.py)
已接受的 action，每条消息恰一条换行结尾的 JSON；使用 JSON 序列化或预先写好的消息文件，
不要通过 shell 拼接用户答案。确认 FIFO 仍属于该 live run，并用有界/非阻塞写入，避免进程
退出后宿主卡在打开 FIFO。按返回 rejection 修正对应消息，不手工修改冻结 artifact。

- 用户答案按已显示问题的 run/project/delivery 绑定经 `user` 输入；实际字段以当前合同为准。
  非 formal v3 run（如 r3-0-006-real-full + r3-0-011 profile）不注册 Modeling→Coordinator
  问题为可答 outer question：`user` 动作必须显式绑定一个已注册的 question delivery ID，
  且该 ID 必须先经 `question` 动作注册（宿主自定义 ID，例如 `host-approved-business-001`）。
  正确两步模式（2026-09-11 auth006-start2 终止教训，start2 因 text-only `user` 触发
  `owner answer requires a question delivery ID` 的 fatal 边界而整 run 终止）：
  1) `{"action":"question","delivery_id":"host-<来源>-001","text":"<宿主通知/业务来源说明>"}`；
  2) `{"action":"user","question_delivery_id":"host-<来源>-001","text":"<完整答复文本>"}`。
  上述 fatal 是历史行为。本次实现对无副作用的字段/问题绑定错误返回
  `outer-input-rejected`（含 `code`、`retryable`、`issue_id`），修正消息后仍可输入，
  不消耗问题或 issue。持久化/实际发送失败不属于这一保证；答完即消费，同 ID 不可重放。
- CQ 的 `cq_interview`、`cq_review`、`cq_freeze`、`cq_handoff_complete` 走直接通道，不能
  通过 Coordinator 转发私有问题或答案。审核使用当前 `review_id`、revision/digest，不能
  未经本次明确委托由宿主代批，也不能就地改写冻结题池。具体见 [CQ 设计](../../../docs/delivery/designs/2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md)。
- 已存在 `issue_resolution` 合同的 issue，读取该 issue 的绑定和允许 resolution 后再提交；
  接口修复使用下节步骤，不把此 action 当成任意 run 的通用修复命令。
- **任何 issue（含 coordinator 自报）都只能由 `issue_resolution` 信封解除
  `WAITING_OWNER`**（2026-09-12 auth008-start2 实证：host 对 coordinator 报告的 issue-3
  只发了 `question`/`user` 便签，`evidence/issue-resolution.jsonl` 里始终没有 issue-3；
  coordinator 随后发起的 `issue_control` resume 被 transport 以 "requires persisted
  resolution" 拒绝（app-server-events.jsonl 15:30:59Z），run 停在 `WAITING_OWNER` 直到
  停止。同轮 issue-1/issue-2 用信封提交后立即 `pause`→`resume` 恢复）。便签只被 steer
  进当前 turn，不落 resolution、不改 issue 状态。
- **不要用便签否定一个 issue 存在**：start2 的 host 便签曾断言 "issue-3 does not exist /
  was never reported"，而 `evidence/issue-report.jsonl`（15:07:40Z）与
  `evidence/issue-control.jsonl`（15:07:45Z pause）都记录了它。判断 issue 状态只读这两个
  文件与 `state.json`，不凭记忆或本轮自述下结论。
- resolution 内容**会自动送到 coordinator**：`receive_outer` 在 `persist_issue_resolution`
  之后无条件向 coordinator 投递 `kind="issue-resolution"` 的 RuntimeDelivery
  （runner.py `receive_outer`，同时机械转发给 modeling），与谁报告的无关。
  `_dispatch_issue_control` 的 `self_resumed` 分支只跳过重复的 reporter 回送，不是缺口，
  不应据此修改 runner（改动会重新触发 R2.3-009 start20 的 "resume did not start a new
  turn" fatal）。
- **`projection.task_id` 是调用方提供的作者标识，不是平台读取值**（2026-09-12 auth009-start1
  实证）。Protocol 曾因 `get_project_build_context` 等三次权威读取都未返回 `task_id` 而
  deadlock，把 issue 升级给宿主。判定：该要求不是真不变量。`build_approval_projection(
  task_id: str, ...)`（`modeling_team/staged_decisions.py`）只是普通入参，无任何校验器交叉核对
  平台值；`APPROVAL_PROJECTION_FIELDS` 仅列出该字段名。真实先例携带的也都是调用方提供的值：
  `r30006-20260911-auth007-start1`、`r30006-20260911-auth006-start6`、`industrial-service-v3`、
  `r3-0-006-real-full`。裁定取值应取本 run 冻结任务定义 `task.snapshot.yaml` 自己声明的
  `task_id`（auth009-start1 为 `r3-0-006-real-full`，第 36 行），逐字使用，不得用占位符/空值/
  run_id 或其它派生值替代。同类“把作者字段当权威来源”的 prompt 合同缺陷值得在后续轮次修掉。
- 顶层 CLI 没有 `status`/`resume` 子命令。外层 `{"action":"status"}` 只触发 drain，
  不是完整状态快照；直接读上述事件和状态即可。
- 外层 `pause` 会 interrupt 当前 turn；当前 Codex adapter 的 `resume()` 不重建子进程也
  不重新加载代码/挂载。不能靠 `{"action":"resume"}` 或 `state=RUNNING` 证明继续成功。
  同 run 续跑必须由仍有效的输入/issue 通道触发实际工作并看到新的进展证据。
- `stop` 会进入 cleanup，不能当作暂停。存在不确定写入时先查询实际结果，再决定生命周期操作。
- **staged 写门 kill-switch 在本进程内不可恢复**（2026-09-14 auth015-start1 实证）：角色在计划改版
  （revision 2）后复用 revision 1 的 `client_batch_id` 提交，平台返回 `batch_content_conflict`，
  Runner 记 `staged_batch_forward_unknown` 并触发 `_staged_gate_kill_switch`（runner.py
  `_staged_gate_killed` 只在 prepare 重置）。宿主先做只读核查（build-session batches 列表）确认
  是否真实写入；即便核查结论是零写入（如 0f9ae6eb 仅 dry_run validation_failed），任何
  `issue_resolution` 都会被 `unknown_mutation_requires_reconciliation` 拒绝——本增量没有 unknown-write
  门重开路径，run 只能按终止处理（保留现场、归因、窄修复、按余额 fresh start）。预防规则已写入
  protocol instructions：改版计划必须换 `client_batch_id`（`-rN` 后缀）。

## CQ 必答点审核与验收诊断（R4.0-013）

### 生成后、冻结前的现有审核

CQ 起草者自查后，宿主在提交用户审核或按已有明确代审授权记录决定时，逐题复核公开／隐藏
题的每个必答点：有获准业务依据；题干明确要求或正确回答所必需；遗漏会改变业务判断或
违反题干的回答范围。资料出现过一句话不自动使其成为所有题的必答点。必要隐含条件、规则
副作用、结果身份和影响结论的授权／执行边界仍须保留；无关平台全局声明通过题意明确的
专项题或既有模型／调用检查覆盖。答案主动声称相反事实时仍应指出错误。

复用 `submit_cq_review.note`，按 `question_id / answer_points 的一基序号` 记录来源定位、
题意对应、保留／修改／移出本题及理由；同依据点可合并，但不得漏点。重排后按新内容版本
定位。该说明是私有人读文本，不是评分 DSL、自动关键词校验或新增必填字段；无检查记录
不得声称质量检查完成。自查不等于批准，未获代审授权时仍等待用户决定，不新增二次批准。

修订内容必须用现有 `modify`／`supplement` 和 `modified_question`，绑定待办的真实
review/version/digest；重发产生新的审核快照。仅记理由不改变内容，不能用 `approve` 暗改
答案或用 note 覆盖冻结题。需要保留的独立覆盖可澄清题干或在获批范围内拆题，不泄露答案。
决定及理由保存在私有 `competency-questions/reviews/decision-*.json`；全文记录 digest
覆盖 note，但 `review_decision_digest` 不包含 note，不能把理由称为新增冻结评分内容。
公开投影不增加字段，隐藏理由不能进入 scenario-map、共享事件正文或生产消息。

### Judge 诊断的交付资格

方案 A 只分析已有 packet／报告，不启动诊断补查或额外角色。业务资料证明预期；本题的真实
平台响应证明返回了什么；生产总结、宿主观察和 collaboration_context 不能补成模型证据。
Judge 对每个未满足点／重要错误断言的原 note 应保留答案点位置、题意与来源、Consumer
回答、真实响应的题号／摘要／路径／内容位置、诊断及限制。诊断缺失或与证据矛盾时记录缺口，
不代改 Judge 的根因和裁决。

同 packet 别题的已有相关响应只能作为诊断旁证，明确原 question_id、response_digest、
artifact_path 和内容，不能补成本题 evidence_refs／答案或据此 PASS。本题早先充分读取过
知识时，后来的空结果不能抹去已读内容，应核对 Consumer 是否漏用。仅有 no_match、partial、
未完成分页、投影省略或冲突时原因未确定；完整分页标记本身不证明完整语义范围。原始 request
不在 Judge packet，不能从 request_digest 反推查询词或过滤条件。Judge 看不到读取复核，
不能声称自己检查过稳定性；同一个 model_binding_digest 也不证明每题响应稳定。

交付依赖平台状态的归因前，只读取原报告的既有记录，逐项核对：

1. 本题及每个旁证的 question_id、response_digest、artifact_path 均可在
   `platform_read_responses` 中唯一匹配。缺失或不能唯一定位时，诊断资格未确认。
2. `evidence_recheck.question_status` 中本题与每个被引用旁证题均为 `stable`；
   drift／unavailable 明细也不能包含这些题或响应。缺复核、缺状态、drift 或
   `platform-runtime-incomplete` 均不通过资格，不能只核对本题。
3. 沿用报告的模型状态漂移和前后绑定核对；有漂移或核对失败时不确认稳定模型归因。
4. 不通过时，在宿主交付中写“Judge 原诊断：…；证据资格：未通过，原因：…；有效归因：
   原因未确定”。保留原 note、verdict 和响应；这是证据资格判断，不是新的语义裁决。
   可描述原响应当时包含的话，不能据此宣称稳定模型存在／缺失或根因已定位。

本题 stable、旁证 drift／unavailable 时，使依赖该旁证的归因无效，不用正常别题兜底。
不新增自动 note 解析器；由宿主按可定位引用核对，独立功能验证检查交付记录。
R3.0-012 已有原请求重放／状态复核仍用于证据稳定，不替换 Examiner 当时收到的原响应。

### 向用户报告结果、诊断与覆盖

从保留的 batch-report 分别说明应验收／已执行／有效裁决／通过题数、未满足、待复核、
未完成及覆盖缺口。沿用 `summary_by_scope` 按 verdict 计题，不新增自动诊断计数器；同题
多个原因只计一道题。每个未通过题给出逐点理由、证据定位、资格及限制，无证据时列未知。

报告使用“端到端语义消费未满足（原字段 `model-recall-insufficient`／`modeling-quality`）”；
其数量不是已证明模型缺失数，问答通过率也不是知识覆盖率。原因未确定仍可记录已证明的
答案错误，不能因此绕过端到端结论或宣称根因已定位。有依据的业务未知可以是正确答案。
skipped／漂移／读取复核失败按宿主原记录呈现，没有 Judge 的题明确无语义裁决；缺裁决、
待复核、未执行和覆盖缺口均阻止完整 PASS，不删题或缩分母。

保留第一实际阻塞层，不用平台／运行失败推导模型缺失。隐藏审核理由和诊断只交获准用户／
验收方，不回流生产角色或 Consumer；公开反馈归 R4.0-015。历史报告不回填、不批量重算，
复审或修题按原授权和版本另留记录；曝光旧题注明非盲回归及原始版本，不冒充盲测泛化。

## CQ 生产交接必须由宿主显式提交

对 `competency_question_acceptance: true` 且 `acceptance_target: cq_semantic` 的任务，
生产角色都报告 terminal 后，Runner 仍不会自动发布 CQ 生产交接。宿主必须沿当前 run 的
证据和待办完成以下核对与动作：

1. 读取 `get_run_status`、增量 `get_run_events` 和 `get_pending_actions`，确认当前
   Modeling、Protocol、Coordinator 结果已收齐，没有待处理 issue，已准入写入已排空，
   没有 unknown write，且当前冻结／生产结果仍绑定同一 run；若已存在 Runner 发布的
   handoff，再核对 `ready=true`、`pending_writes=false`、`write_phase=read-only` 和
   `unknown_writes=[]`。角色 terminal 只表示角色已结束，不表示 handoff 已发布。
2. 从当前 `complete_cq_handoff` 待办或对应最新事件取得 `freeze_id`、`freeze_digest`
   及可选 `delivery_binding`；不从历史 run、旧 attempt 或角色自报内容拼接绑定。若
   readiness 未满足，保留 Runner 的类型化拒绝和第一阻塞，先处理该阻塞。
3. 通过宿主 Host 通道提交 `complete_cq_handoff`（Runner action 为
   `cq_handoff_complete`）。核对返回 `ok=true`、`acceptance_phase=acceptance_pending`、
   当前 `acceptance_attempt_id` 和 `report_directory`；提交成功只说明 Runner 已接受
   生产交接，不说明 CQ 语义通过。
4. 用该 handoff 的当前绑定启动独立 `cq-acceptance`。报告落盘后调用
   `complete_cq_acceptance`，核对当前 attempt、Runner 重算的 `report_digest`、
   `cq_verdict`、已执行／未执行题目和完整分母；保留 PASS、PARTIAL 或失败报告。验收
   收口成功也不等于语义 PASS，不能用角色完成或机械 readiness 覆盖语义缺口。

提交前的 readiness 核对、交接回执和独立验收结果都应写入宿主收尾记录；不要因为角色已经
结束而提前 `stop`，也不要把 `publish-handoff`（离线交接）当作 run 内的
`cq_handoff_complete`。

## 场景地图进度：交接、保存与恢复（R4.0-014）

1. 在 Coordinator 生产 terminal 前，核对 Modeling 的最终候选／修订消息是否包含切片、
   视角、candidate_id/revision/关键 item 或获准路径、实际覆盖、未知／待办和下一步。
   Coordinator 从可访问候选核对内容后写地图；无实际产物只注明待核对，不以口头完成、
   文件存在或结构 PASS 升级。Protocol 经已有消息提供确定写入摘要，不读 Coordinator 私图。
2. 核对受影响 note 能说明当前已表达与未完成范围。部分表达用 modeled；仅分析无表达用
   pending，真实业务未决阻塞用 unknown，不适用须有业务范围依据。必要未知可已正确表达，
   同时保留 explicit_unknowns／候选 unknowns。modeled 不升级 shared_terms.confirmed，
   不证明 applied／独立 PASS。修订只重判失效范围，旧版标历史，语义变化仍做 007 review；
   实质进度变化记现有 adjustment，无变化不重复追加。不凑齐七视角或计算完成率。
3. 顺序保持：最终候选和写入结果明确 → Coordinator 同步并结束地图写入 → 生产静默／
   写入排空 → 原 handoff 绑定 digest → 独立只读验收。普通过期通过既有反馈修正，不新增
   不可恢复硬门。若 terminal 后才发现过期，不擅自重启角色修备注；在宿主交付记录说明
   差异、当前候选定位、后续恢复待同步项，不进入本次 Judge 业务证据，不覆盖绑定原件。
4. 计划 checkpoint 保存前尽量同步已到达的更新；紧急中断、额度／期限到达仍保存实际
   内容并注明待核对范围，不等语义同步、不改 manifest／stage_facts。恢复先按原机制核对
   checkpoint、scope／身份映射、全链写状态和候选，再判断下一工作，由 Coordinator 在
   获准生产的可写副本更新。确定成功写入不重放；pending 不代表未写入；unknown write
   走现有核实。缺候选／恢复历史如实报告，不从 note 重造产物或批准。
5. 验收-only 续跑继续保持源地图、checkpoint／报告只读，真正摘要漂移仍报告
   collaboration_binding_changed。fork 保留中立 candidate/item 进展，但平台身份按
   fork_scope／identity_mapping 核对；旧平台引用和回执标源历史，不能授权新 apply。
   旧 R3／保留 run 不批量改图，不把隐藏题、答案或私有诊断写进生产地图。
6. note 更新可能触发同范围 cq-slices-approved：CQ 对照 slice_id/name/scope/owner，
   相同内容只作状态通知，不重新出题、批准、冻结或加入隐藏题。真正范围变更走既有审核；
   不为消除重复通知改变 Runner 算法。


## cq_handoff_complete 之后的独立验收收口（acceptance_pending）

`cq_handoff_complete` 被接受并返回 `acceptance_phase=acceptance_pending` 后，live run 保持
pending：coordinator 已 terminal 不代表完成，Runner 在等宿主完成独立验收（R3.0-012 §4.5）。
历史 auth014-start1 中，宿主发送 `stop` 触发 cleanup，当前 Acceptance 以
`runner-cleanup-before-settlement` abort。R3.0-015 S4 已支持原生产进程退出后从有效
`production_handoff` 检查点另起独立验收尝试；旧尝试的 abort 记录仍保留。
原 run 存活且继续当前验收时，按以下步骤收口：

1. 保持 live run，避免因“生产已完成”而提前发送 `stop`。若按授权决定结束原进程后再验收，
   先确认有效 `production_handoff` 检查点已发布、所需资源可保留，再受控停止并走
   [S4 验收续跑](#验收续跑r30-015-s4)。原进程已经退出时先检查保留成果，不能假定有
   检查点，也不能从历史目录补造检查点。
2. 用当前权威入口启动独立验收会话：
   `uv run --project backend python -m modeling_team cq-acceptance --run-root ... --freeze-id ... --model-handoff ...`
   （参数先读 `--help`；独立验收者不得参与生产或修复）。
3. 验收进程退出后，把 digest-and-verdict 摘要经 FIFO 发送 `cq_acceptance_complete`
   envelope（字段见 Runner 合同 `CQ_ACCEPTANCE_COMPLETE_FIELDS`）；Runner 自行复读
   batch-report 并复核 digest/verdict 后才释放 terminal report。
4. 全部/部分/失败报告都同样完成收口；验收不需要全绿才算 run 正常结束。

## 建模检查点保存与检查（R3.0-015 S1）

R3.0-015 交付段 S1 覆盖阶段成果的**保存与检查**；跨进程生产续跑（S2）见下一节
[生产续跑](#生产续跑r30-015-s2)。启用需
选择声明 `parameters.modeling_checkpoints: true` 的 v3 Task
（[r3-0-015-checkpoint-recovery.yaml](../../../modeling_team/tasks/r3-0-015-checkpoint-recovery.yaml)；
该参数依赖 multi_slice_workflow、staged_modeling_decisions 与 unified_semantic_graph，
由 `modeling_team/contracts.py` 强制，validate 阶段即报错）。

保存都由 Runner 核实磁盘上的实际已发布产物；只有"阶段完成"文字而没有产物时返回
`checkpoint_missing_artifact` 可重试拒绝，该 action 不给 Agent 新增任何写权限：

- 自动触发（run 期间无需宿主操作）：访谈成果落盘后存 `scenario_mapped`；CQ 冻结后存
  `cq_frozen`；每个 staged 批次回执完成存 `materialization_progress`；production handoff 发布后存
  `production_handoff`。自动保存失败只记 `checkpoint-save-failed` 证据，不终止正常
  建模，也不回滚阶段事件本身。
- 宿主/Coordinator 请求（经 FIFO，每条一行 JSON）：
  `{"action":"checkpoint","command":"save","kind":"...","scope_refs":{...},"request_id":"..."}`，
  kind 取五类之一：`scenario_mapped`、`cq_frozen`、`semantic_approved`、
  `materialization_progress`、`production_handoff`（场景决定或 `semantic_approved`
  仍可按实际发布成果请求保存）。
  `{"action":"checkpoint","command":"inspect"}` 为只读查看。写声明类
  （materialization/handoff）在 staged 写在途或存在 unknown 时返回
  `checkpoint_write_unreconciled` 具体等待原因，不把在途状态包装成可恢复写入快照。

包落在 `<run-root>/checkpoints/<checkpoint-id>/`（manifest.json 最后原子发布，没有
manifest 的半包不会被列出；`checkpoints/` 不在角色挂载内，host-private 侧的冻结
题池/隐藏依据永不进入生产投影），事件在 `evidence/checkpoints.jsonl`
（`selector-enabled`、`checkpoint-saved`、`checkpoint-reused`、
`checkpoint-save-failed`、`scope-retention-reference`）。同一成果换新 request id
重复请求按内容去重复用，不产生新包，也不覆盖旧包。

宿主只读检查命令（需与 `run` 相同的宿主凭据通道 `ONTOLOGY_PLATFORM_ADMIN_API_KEY`，
缺失时准确报错；不写 run、Agent 或平台）：

```bash
uv run --project backend python -m modeling_team checkpoint inspect --run-id "$modeling_run_id"
# 追加 --checkpoint-id <id> 查看单包：可复用产物 / 待办 / 写对账 / 兼容性 /
# 预计授权消耗，状态 ready | needs_reconciliation | incompatible
```

记账与保留：保存与检查均不消耗 semantic start（inspect 输出含
`consumes_semantic_start: false` 与各交付段状态）。已发布且 digest 校验通过的包会让
空的 owned scope 在 cleanup 时改为 `retained-checkpoint-reference`（全部凭据仍吊销）；
仅 selector 标志、失败保存或临时目录不算保留依据。手工清理按设计 §3.4 顺序：先
`checkpoint inspect` 列出具体包及引用，核对无活跃写者、无 unknown 后按用户既有清理
授权移动具体 checkpoint 目录并保留失败/操作证据；本仓库不提供一键清空或自动 GC。

## 生产续跑（R3.0-015 S2）

宿主用 `checkpoint resume` 从一个已发布检查点跨进程续跑生产（design §4–§8）。
仅宿主凭据通道（`ONTOLOGY_PLATFORM_ADMIN_API_KEY`，与 `run` 相同），显式
checkpoint id 与全新 run id 必填（绝不自动选择、绝不覆盖已存在目录）：

```bash
uv run --project backend python -m modeling_team checkpoint resume \
  --run-id "$source_run_id" --checkpoint-id "$checkpoint_id" \
  --new-run-id "$new_run_id" --mode production \
  --authorization-reference "<用户授权引用（记入台账）>" \
  # 可选：--base-url（默认 http://127.0.0.1:8001）、--freeze-started-at（全新冻结时点，
  # 旧 run 的 deadline 不继承）、--enable-outer-input-fifo
```

`--mode acceptance` 不走生产续跑路径，见下节
[验收续跑](#验收续跑r30-015-s4)：非 `production_handoff` 检查点得到
`checkpoint_kind_mode_mismatch` 类型化拒绝（exit 2），不会静默落到生产续跑。

恢复时**重新核对全部状态**，不信任保存时的任何布尔结论：

- 恢复链（`recovery/origin.json` 多跳回溯）全链写尾，含检查点之后发生的写入；
- 平台侧逐 Build Session 的 Modeling Batches 回读，只走 cursor 分页端点
  （`GET /api/build-sessions/{id}/modeling-batches`、`GET /api/ontologies/{id}/modeling-batches`
  limit≤100 + next_cursor、`GET /api/modeling-batches/{batch_id}`）；截断视图
  （`platform_state.modeling_batches` 20 条、session 详情内嵌 50 条）**不是**对账来源；
- 已完成操作进入完成索引（按 origin_run/session/batch/attempt/client_item 键），
  预提交屏障拒绝把同一操作换新 Session 重放（后端幂等键按 Session 作用域，不跨
  Session 去重）；多跳链的操作归属原始 run；
- 业务审批只复用本检查点打包且来源通道校验通过的条目：`approved_by` 必须解析为
  源 run 自己 profile 的 coordinator agent，保存后被撤销/换版的决定保持撤销。

任何一类未闭合都是带 `code` 的类型化拒绝（至少 `checkpoint_incomplete`、
`artifact_changed`、`source_active`、`contract_incompatible`、`scope_missing`、
`scope_drift`、`write_unreconciled`、`approval_binding_changed`），字段为
`code/object_ref/phase/retryable/reason/next_action`，不含密钥或隐藏内容；按
`next_action` 处理后重试，不擅自改写源 run。

悬挂原写者（`source_active`）：读 inspection 的 `source_writer` 报告（state.json、
control FIFO、目录属主、平台 Session/Lease 与 `expires_at`、最早复查时间），经原 run
自己的 stop channel 停止，单次等待 ≤60s；`adjudicate_unknown_intent` 一类提示**不能**
替代平台精确回读释放写门。新 run 只为未完成操作新建 Build Session/Lease；恢复清理
只回收本轮线程/凭据/Session/Lease，继承的 scope 不删除（`inherited-retained`）。

宿主已受控停止原写者、fresh 源 run 的 `state.json` 仍停在 possibly-live 且 stop 通道已
消失时，先显式登记 settlement 再重试（命令只写 runs root 的
`.recovery-settlements/<run_id>.json`，不创建/恢复 run、Session 或 start，不改源 run）：

```bash
uv run --project backend python -m modeling_team checkpoint settle-source \
  --run-id "$source_run_id" --stop-reference "<停止事实引用>"
```

恢复入口在 gate 处实时复核该记录（run/state 匹配、FIFO 消失、已知 Session 均为
completed/cancelled 且无 active lease）；"无 FIFO、无 session" 本身不推断进程死亡，
带恢复来源的 run 仍只认 chain writer lock。

新 run 落盘 `<new-run>/recovery/{inspection,origin,imports}.json` 与
`recovery/roles/<role>.json`（0600）：角色启动包含 resume_kind、可读产物、已完成
范围、待办、禁止重放清单与下一步；翻译类计划按新 plan/client_batch_id/key 走新
Session 并由当前 Coordinator 按既有 014 路径审核（S3 自动迁移按设计不交付）。
staged 校验器一律重算，布尔 gate-open 状态永不还原；CQ 冻结池重新校验后采纳。

记账：续跑记 1 次 fresh semantic start（host 记录 `authorization_reference`），
平台侧没有硬计数门（`platform_hard_gate: false`）；准备（含对账）时间计入自用户
授权起的 20 分钟预算，超时只报告阻塞并请求更长准备窗口，不放宽任何门。

同机同一 root run 同时只允许一个续跑进程（root-run 文件锁，进程死亡由内核释放）。
手工清理源 run/检查点前先确认没有 active 恢复引用（新 run 的 `recovery/origin.json`
指向源 run 与具体检查点）；有 active 恢复时按用户既有清理授权先处理新 run 再动源。

## 验收续跑（R3.0-015 S4）

宿主对一个 COMPLETE `production_handoff` 检查点做验收-only 续跑（design §7）；
S3（翻译类计划自动迁移）按设计延后，S4 不依赖它。入口与 S2 相同的宿主凭据通道
（`ONTOLOGY_PLATFORM_ADMIN_API_KEY`），显式 checkpoint id 与全新 run id 必填：

```bash
uv run --project backend python -m modeling_team checkpoint resume \
  --run-id "$source_run_id" --checkpoint-id "$checkpoint_id" \
  --new-run-id "$new_run_id" --mode acceptance \
  --authorization-reference "<用户授权引用（记入台账）>" \
  # 可选：--session-timeout（重执行路径的子会话超时，默认 300s）、--base-url
```

入口先做**只读复核**，复用 S2 的 cursor 回读纪律：全链写尾必须闭合干净（unknown/
未回执写入即拒绝）、原写者必须已停（`source_active` 可重试，经原 run stop channel
处理，单次等待 ≤60s）、冻结池按快照摘要对源 run 里实际存储的 `freeze-NNNN.json`
重校验（handoff 的 freeze_id 是批次 id，不是文件名）、打包 handoff 必须仍等于源 run
已发布 handoff、平台侧对绑定本体无不可归属写入。任何漂移都是带 `code` 的
类型化拒绝（`acceptance_binding_changed`、`source_active`、`write_unreconciled`、
`scope_drift`、`checkpoint_kind_mode_mismatch` 等，字段
`code/object_ref/phase/retryable/reason/next_action`，不含隐藏题面或密钥），
源 run 一字不动，也绝不代改模型。

**输入/输出分离**：证据根（run-contract、冻结池、判定证据束）永远是原 run；旧
run_id、handoff 尝试字段、旧 partial/fail 报告与失败分类永不改写，也绝不向已死的
原 FIFO 投递任何消息。新尝试、新报告、平台读留存与宿主收尾记录只落新输出 run：
`recovery/origin.json` 在任何执行前先落（0600），终态记
`recovery/acceptance-continuation.json`。原 cq-acceptance CLI 的单根默认行为不变。

续跑语义：先按批次 id + 冻结摘要在全链（源 run 与既有续跑输出根）查找**完整可用
PASS 报告**（`full_pass` 且全分母判定重算通过）——存在则只做核验与收尾
（`mode: verification-only-closing`，0 次模型会话、0 次语义开始）；否则经既有
cq-acceptance 执行与独立 Judge 路径重新执行整个冻结批次（`mode: re-executed`），
冻结的 `acceptance_target`、题目分母与非盲状态不变，绝不把旧 partial 结果拼进新
PASS；attempt id 在全链上分配，永不复用已发布尝试目录。重执行路径与 cq-acceptance
一样需要 `R3011_ACCEPTANCE_PLATFORM_READ_KEY`（核验收尾路径不需要）。

记账：`semantic_starts: 0`（`consumes_semantic_start: false`）——验收续跑是挂靠
源 run 的独立尝试，不消耗建模开始；准备（复核）时间计入自用户授权起的 20 分钟
预算，执行时间在收尾记录单列。同机同一 root run 的生产续跑与验收续跑共用一把
root-run 锁，互斥不并发。手工清理时同样先核对 `recovery/origin.json` 链。

## 接口修复后继续同一 run

收到“接口已经修复完成，请继续”时，由宿主读取当前 live run 的唯一 pending issue、
`reporter_id`、`control_epoch`、mutation state 和修复对象，组装下列消息。占位值必须来自
当前 issue，epoch 也使用当前值；不要重用旧 run 的 ID。此步骤由宿主理解用户意图，Runner
只接收结构化输入，不解析自然语言关键词。

```json
{"action":"issue_resolution","run_id":"<当前 run>","issue_id":"<当前 issue>","reporter_id":"<当前 reporter>","control_epoch":1,"resolution_type":"repair_completed","repair_component":"external_service","resolution_text":"接口已经修复完成，请继续原失败步骤。"}
```

新简短修复格式必须显式包含 `run_id`，错投会在保存 resolution 前被拒绝。修复对象支持
`external_service`、`shared_backend_service`、`shared_backend_data`；后两者必须确实是当前
外部共享依赖，不能用来声称已热更新 Runner、Transport 或冻结提示。已确认无写入时不强制
提供 digest 或额外健康探针，责任 Agent 续跑原失败操作验证修复。旧五字段修复格式及 guidance
继续兼容；省略 run_id 的旧消息依赖目标 FIFO 绑定，不具备显式 run_id 的跨 run 防错投保护。

Runner 保存通知并交给 Coordinator，通过绑定 `resume` 在原 thread 创建新 turn。
`resume_waiting_reporter` 表示暂停 turn 尚未结束，Runner 保留原控制并在 reporter 空闲后
派发一次；宿主和 Coordinator 不重复保存 resolution 或发送 resume。保持观察，直到原失败
步骤出现新结果；保留原 CQ、审批、候选、请求、plan 和幂等键，不因接口修复重做前期建模。
若 Session/lease 已过期，由责任角色按既有合同处理，保留线程不延长授权或凭据有效期。

`mutation_state=unknown` 或 durable intent/receipt 未闭合时，所有非 abort resolution 均
不能解锁写入；旧格式中的 `reconciled` 等文字也不是核对证据。保留 issue、关闭的写门和原始
记录，按下方只读核查定位；本增量不提供 unknown-write gate reopen。不得改写 receipt 或
清除关闭状态。进程已死、线程已丢失或修复需要替换冻结运行代码时，也不能用此通知重绑；
按 Skill 的既有 fresh-start 额度与现场保留规则处理，不把 `stop` 当作暂停。

## 独立验收入口

验收前由宿主整理本轮目标中的具体运行终点及实际证据，按归属需求的
[测试计划](../../../docs/delivery/test-plans/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-test-plan.md)
与所选 Task 的 `expected_terminal_evidence` 判断。L0 报告至少说明：真实 run/加载基线、
目标中各步骤的事件和交接结果、若涉及写入则附确定性回执、终态及资源处置。宿主整理材料，
由该需求指定的验收者判定；最终语义验收另守独立边界。目标步骤均有真实证据才报告该范围
PASS；部分完成记 PARTIAL，已证实缺陷需修改记 REVISE，不能继续时记 BLOCKED 并指出第一
阻塞。不能仅凭健康端点、PID 或 RUNNING 宣布整轮 L0 完成；不因此要求 L1/L2/L3 提前完成。

当前 v3 批次入口是 `uv run --project backend python -m modeling_team cq-acceptance
--run-root ... --freeze-id ... --model-handoff ...`，具体参数先读 `--help`。
这会启动真实验收会话；`--unexecuted-report` 只生成未执行报告，不能据此声称验收通过。
交接冻结题池及获准模型绑定给独立验收流程，宿主不修改报告补齐缺口。
SQL Consumer 使用现有 `scripts/r3-0-006/consumer_rounds.py` 及归属设计，不另造一次性裁判。
语义 start 授权、apply 范围和验收/SQL 运行范围分别遵循用户本次授权与所选任务。

## apply 超时或在途写入的只读核查

复用宿主已获授权的读取客户端/MCP 配置，不从角色私有目录提取密钥，不为核查另建查询服务。
工具以当前注册前缀调用；下表是现有工具名、参数与等价 HTTP GET 路径，base URL 取实际环境。
接口来源：[Batch 工具](../../../backend/app/mcp/tools/modeling_batches.py)、
[Session 工具](../../../backend/app/mcp/tools/build_sessions.py)、
[Batch REST](../../../backend/app/api/modeling_batches.py)。

| 顺序 | 现有 MCP 调用参数 | 等价 GET 与观察点 |
| --- | --- | --- |
| 找到会话 | `get_project_build_context(project_id)`、`get_build_session(session_id)` | `/api/projects/{project_id}/build-context`、`/api/build-sessions/{session_id}`；核对 Project、Session、涉及 Ontology 与 lease；使用真实 ID |
| 找到 Batch | `list_session_modeling_batches(session_id, limit=100)` | `/api/build-sessions/{session_id}/modeling-batches?limit=100`；不按成功状态过滤，沿返回 cursor 读完所需范围 |
| 读取实际尝试 | `get_modeling_batch(batch_id)` | `/api/modeling-batches/{batch_id}`；按 `client_batch_id`、`content_hash`、Session/Ontology 和 `attempts[].idempotency_key` 绑定超时的原请求 |
| 核对当前资源 | `get_modeling_context(ontology_id)` | `/api/ontologies/{ontology_id}/modeling-context`；检查 `workspace.state`、`workspace.workspace_version` 与实际资源读取 |

Batch 详情含 `batch_status`、`attempts[]`；每个 Attempt 有 `mode`、`attempt_status`、
`workspace.before_version/after_version`、`items`、`recovery`、`completed_at`。
判读依据是匹配原请求的 **apply** 尝试，不是同 Batch 的 dry-run 验证成功：

- `applied`：核对资源输出和实际读取；记录该次已落库，不重放，继续原目标尚缺的工作。
- `applying` / `recovering`：仍在处理或恢复，继续有界读取；不重启共享服务或删除资源。
- `partially_applied`、`failed` 或 recovery 异常：检查 items、findings 和 recovery 以及
  资源实际状态；不能把失败状态等同于“零写入”，不由宿主拼补语义或直接重试。
- 查不到、401/403/404、列表被截断或读取失败：保留 UNKNOWN，先解决定位/读取权限/依赖；
  这些结果不能证明未写入。`recovery.safe_to_retry` 也不等于“无写入”或宿主重放授权。

安全交接需要当前受影响写请求已停止新增、相关 Attempt 不再在途、回执与实际资源相符且
归属明确。确认这些事实后，才由宿主按任务合同协调续跑/重启/保留或清理；不能把一次状态快照
当成持续无写入的保证。仍不确定则明确记录第一缺口与下一项只读核查，不增加硬拒绝或恢复框架。

## R3.0-016 S1+S2 宿主 MCP 工具（modeling-team-host）

宿主与建模 run 的交互闭环（启动 run → 查询待办 → 提交答复/修复通知/审核冻结/交接收口 →
pause/resume/stop → 检查点保存/接续/结算 → 核对处理结果）走本节工具面；自然语言理解、
业务判断与授权决定留在宿主。
需求：[R3.0-016](../../../docs/requirements/requirements-v3.0.md)；
设计与合同：[交付设计](../../../docs/delivery/designs/2026-09-18-r3-0-016-s1-host-interaction-interface-design.md)、
[S2 交付设计](../../../docs/delivery/designs/2026-09-18-r3-0-016-s2-start-lifecycle-checkpoint-design.md)。

### 手工接入（不自动改任何全局配置）

- 服务器：`backend/.venv/bin/python -m modeling_team.host_ops_mcp`（stdio，仓库根为 cwd）；
  配置片段：`.claude/modeling-team-host-mcp.json`（仿 `.claude/ontology-mcp.json`）。
- Claude Code：把片段内容并入项目/用户级 `mcpServers` 配置后重启会话；
  Codex：写入对应宿主配置的 mcp servers 段。两种宿主都只做手工合并，本仓库不提供
  任何自动注册脚本。
- 冷启动自检：`tools/list` 应返回且仅返回下表 20 个工具（12 个 S1 查询/提交 +
  8 个 S2 启动/生命周期/检查点）；出现 `resume_run`/`abort_run`/`create_run`/
  `checkpoint_run` 等表外名称即为错误安装，生产 `backend/app/mcp/tools` 与
  角色 agent-package 能力面也不得出现任何 S2 工具名。

### 固定 20 工具最小用法

| 工具 | 何时用 | 关键点 |
| --- | --- | --- |
| `get_run_status(run_id)` | 任何操作前的快照 | 记录状态/阶段/最后活动/第一阻塞/待办摘要/终态结论/存活观察；`run_id` ≠ 平台 session_id；RUNNING 不算语义进展 |
| `get_run_events(run_id, cursor?, limit?)` | 增量读证据事件 | cursor 逐字节偏移、**无遗漏**：完整行（含坏行/超长行占位）至少投递一次；停驻窗口内 at-least-once（同一行可能重复投递），宿主一律以 `(source, byte_offset)` 作事件唯一标识去重；每页为各停驻源的首行保留保底交付槽位，分页必收敛且 `has_more=true` 的下一页必非空；每条事件带 `source`/`line_no`/`byte_offset`：`line_no` 是本次扫描内的序号（续读从 1 重新计数，不是源内绝对行号），定位以 `byte_offset`（行首字节偏移）为准；页内输出按 recorded_at-近似排序；只读不 drain |
| `get_pending_actions(run_id)` | 发现待办与绑定 | 每项带可用动作与必填绑定；绑定原样进对应提交工具，不手拼信封 |
| `answer_question(run_id, channel, text, ...)` | 答复待答问题 | `channel=user` 需 `question_delivery_id`；`channel=cq_interview` 走 CQ 访谈；两通道不互通；text 原样传递（中文多行可以） |
| `register_question(run_id, delivery_id, text)` | 两步注册模式 | 仅当既有通道要求宿主注册；不用来顶替答复失败 |
| `submit_cq_review(run_id, <待办绑定>)` | CQ 审核决定 | 绑定全部取自 `cq_review` 待办；schema_version 工具自填 |
| `freeze_cq(run_id)` | 审核完成后冻结 | 审核与冻结是不同动作；未决问题仍拒绝 |
| `complete_cq_handoff(run_id, freeze_id, freeze_digest)` | 交付生产交接 | 成功 → `acceptance_pending` + attempt/report_directory；不等于整轮完成 |
| `complete_cq_acceptance(run_id, acceptance_attempt_id?)` | CLI cq-acceptance 报告落盘后 | 工具自算 report_digest/cq_verdict；收口成功 ≠ 验收 PASS |
| `resolve_issue(run_id, <issue 绑定>, resolution_type, ...)` | issue 等待的正式修复通知 | 唯一 resolution 通道；便签/答复不冒充修复 |
| `recover_provider(run_id, agent_id|role, text, wait_id?)` | provider 等待宿主接管 | 不自动换模型/重建线程/开新 run |
| `get_request_result(run_id, request_id)` | 核对处理结果 | accepted/rejected/submitted/unknown；接受 ≠ 建模推进 |
| `start_run(run_id, task, profile, model_profile, scope, freeze_started_at, task_overlay?, base_url?, request_id?)` | 受管发起新 run | 见下方 S2 节：argv 恰为 `run` 子命令实有参数，`freeze_started_at` 只做形状校验、绝不补值；`launch accepted ≠ semantic start happened` |
| `pause_run(run_id, request_id?)` | 暂停存活 run | pause ≠ stop；消费证据 `state.json` |
| `resume_live_run(run_id, request_id?)` | 继续同一存活线程 | 不重建线程；已退出/终态 run 明确报限制，不静默转 015 接续 |
| `stop_run(run_id, reason?, request_id?)` | 停止 run | 携带既有收尾与未知写入对账边界 |
| `inspect_checkpoints(run_id, checkpoint_id?)` | 只读查看已发布检查点 | 透传 015 结果，不改冻结产物、不触发恢复 |
| `save_checkpoint(run_id, kind, scope_refs?, command?, request_id?)` | 请存活 run 发布检查点 | 单一 `request_id` 双面落账；kind/selector 校验留在 Runner |
| `resume_from_checkpoint(source_run_id, checkpoint_id, new_run_id, mode, authorization_reference, freeze_started_at?, session_timeout?, request_id?)` | 从显式检查点接续 | `--run-id` 即源 run，绝不自动选最新包；`production` 必填新 run 真实冻结时点；拒绝原码透传 |
| `settle_source_run(source_run_id, stop_reference, base_url?, request_id?)` | 登记既有受控停止的结算 | 进程内调用既有 015 结算；**不凭"找不到进程"宣告停止** |

变更类工具都接受可选 `request_id`（每次提交内容唯一，≤128 字符）：写入 FIFO 前操作层
登记 `control/host-requests.jsonl`，Runner 准入后落 `evidence/outer-input-receipts.jsonl`。
同 `request_id` 同内容重复提交直接复用原结果（不二次写 FIFO）；同 id 不同内容明确拒绝。
无 `request_id` 的旧消息行为不变、不可关联查询。错误统一 `{ok:false, error:{code, reason,
retryable, next_action}}`，Runner 原拒绝码原样透传；`unknown` 只在 `get_request_result` 出现，
不得自动重发或换新 id 绕过。

### 保留 CLI 清单（S1 不封装，合同不变）

| CLI | 适用合同与调用时机 |
| --- | --- |
| `classify-failure` | 归因与四类失败分层登记；在决定修复/放弃前调用 |
| `authorize-repair` / `authorize-budget` / `authorize-initial` | 授权台账登记（repair/budget/initial 三类）；授权记录是后续 run 的凭据，不经 MCP 工具代签 |
| `publish-handoff` | 离线交接发布（`≠ cq_handoff_complete`：后者是 run 内 CQ 生产交接收口） |
| `cq-acceptance` | 独立验收执行器，产生 `acceptance-v3/reports/<batch>/attempt-NNNN/batch-report.json`；报告保留后由 `complete_cq_acceptance` 引用 |

## R3.0-016 S2 启动 / 生命周期 / 检查点工具

S2 把"启动一个受管建模 run、pause/resume/stop、检查点保存/只读检查/接续/源 run 结算"
封装进同一宿主工具面。每个启动动作都是一次**受管启动**：`subprocess.Popen`（`start_new_session=true`，
继承宿主环境，stdout/stderr 落宿主自有日志），启动前先登记
`workspaces/modeling-runs/.host-launches/<run_id>.json`（schema
`modeling-team-host-launch/v1`：argv 摘要、pid、started_at、host_session_ref、log_paths、
status），同目录另有 `<run_id>.out.log` / `<run_id>.err.log`；子进程退出由 per-launch
reaper 守护线程翻转 `status: exited` 并记 `exit_code`（该字段的唯一观察者）。

### 存活登记约定（S2 受管启动自动写入）

fresh run 无恢复来源时进程观察为 unknown。S2 启动类工具在 run 根出现后的 ≤10s 有界窗口内
自动写 `<run-root>/control/host-supervisor.json`（宿主写、Runner 不写）：
`{"schema": "modeling-team-host-supervisor/v1", "pid": <启动的 Runner 进程号>,
"started_at": "<ISO8601>", "session_ref": "<可选宿主会话引用>"}`；
存在即以 `/proc/<pid>` 报 `pid_alive`，写入遵守"存在即不改写"（pid 一致跳过，不一致不覆盖、
改报 `run_launch_in_progress` 供人工裁决）。续跑 run 自动用 `chain_writer_lock_report`
证据观察。宿主也可按既有惯例手工写入同一文件，格式不变。

| 工具 | 何时用 | 关键点 |
| --- | --- | --- |
| `start_run(run_id, task, profile, model_profile, scope, freeze_started_at, task_overlay?, base_url?, request_id?)` | 发起新 run | argv 恰为 `run` 子命令实有参数；`freeze_started_at` 只做形状校验（tz-aware ISO-8601），**绝不补当前时间**，编造/旧时点的拒用是宿主纪律；run 目录已存在 / 登记进程活 / 登记进程死 分别报 `run_id_already_exists`/`run_launch_in_progress`/`run_launch_failed`；返回 `launched:true`+`baseline_evidence`+`query`，`note: launch accepted ≠ semantic start happened`（真实语义开始只看 `evidence/semantic-start.jsonl`） |
| `pause_run(run_id, request_id?)` | 暂停存活 run | pause ≠ stop；走 FIFO `pause` 信封，`consumption_evidence: state.json` |
| `resume_live_run(run_id, request_id?)` | 继续同一存活线程 | 不重建线程、不热加载；对已退出/终态 run 明确报限制，**不静默转为 015 接续**（接续只能走 `resume_from_checkpoint`） |
| `stop_run(run_id, reason?, request_id?)` | 停止 run | 携带既有收尾与未知写入对账边界；`reason` 只进宿主提交台账与 digest，Runner 不读取 |
| `inspect_checkpoints(run_id, checkpoint_id?)` | 只读查看已发布检查点 | 透传 015 结果（含 `production_resume_bindings`、verify、`semantic_starts` 计数）；不改冻结产物、不触发恢复 |
| `save_checkpoint(run_id, kind, scope_refs?, command?, request_id?)` | 请存活 run 发布检查点 | 单一 `request_id` 双面落账（回执 + 015 manifest 溯源）；kind/selector 校验留在 Runner，原码透传；同 id 重放不产生第二次 save |
| `resume_from_checkpoint(source_run_id, checkpoint_id, new_run_id, mode, authorization_reference, freeze_started_at?, session_timeout?, request_id?)` | 从显式检查点接续 | argv 恰为 `checkpoint resume` 实有参数且 `--run-id` 即**源 run**，绝不自动选最新包；`production` 必填**新 run 真实冻结时点**（不复用源 run 旧时点），`acceptance` 不接受该参数、可带 `--session-timeout`；默认带 `--enable-outer-input-fifo`；被 015 拒绝时原码透传，不换包/换 ID/重试 |
| `settle_source_run(source_run_id, stop_reference, base_url?, request_id?)` | 登记既有受控停止的结算 | 进程内调用既有 015 结算，与 CLI 共用 `.recovery-settlements/<run_id>.json`；拒绝原码透传；**不凭"找不到进程"宣告停止**、不清未知写入 |

### 凭据通道与启动顺序

- `resume_from_checkpoint` / `settle_source_run` 需要平台凭据，只经宿主进程环境注入
  `ONTOLOGY_PLATFORM_ADMIN_API_KEY`；缺失即报 `host_credential_missing` 且不启动子进程、
  不做任何写入。凭据不得出现在配置文件、登记记录、日志或错误文本（argv 摘要天然无凭据）。
- 建议顺序：`inspect_checkpoints`（只读核对包/bindings/verify）→ 完成全部预检与门核查
  **之后**记录新 run 的真实冻结时点 → `resume_from_checkpoint` 或 `start_run` →
  每步以 `get_run_status`/`get_run_events`/`get_request_result` 核验 → 同一存活 run 上按需
  `pause_run` → `resume_live_run` → `save_checkpoint` → `inspect_checkpoints` → `stop_run` →
  需要时 `settle_source_run`。启动不等待首个 semantic start，也不自动重试/换新 ID。

### 证据位置

| 证据 | 位置 |
| --- | --- |
| 启动登记与退出观察 | `workspaces/modeling-runs/.host-launches/<run_id>.json`（`status: launched\|exited`、`exit_code`） |
| 启动日志 | `workspaces/modeling-runs/.host-launches/<run_id>.out.log` / `.err.log`（ledger/冻结时点等原码拒绝可在此定位） |
| 进程观察 | `<run-root>/control/host-supervisor.json`（被 `get_run_status` 原样消费） |
| 基线与语义开始 | `<run-root>/baseline-manifest.json`、`<run-root>/evidence/start-ledger.jsonl`（仅预约/结算，不代表语义开始）、`<run-root>/evidence/semantic-start.jsonl` |
| 提交与回执 | `control/host-requests.jsonl` + `evidence/outer-input-receipts.jsonl`（`get_request_result` 查询） |
| 检查点 | `<run-root>` 检查点目录 + `evidence/checkpoints.jsonl`；结算记录 `workspaces/modeling-runs/.recovery-settlements/<run_id>.json` |

### 陈旧 `.host-launches` 记录的手工清理

`.host-launches/<run_id>.json` 是宿主自有证据，工具**从不**隐式删除或改写它。当一条登记
的进程已死且 run 根不存在（`start_run` 报 `run_launch_failed`，附原记录与日志引用）需要
复用该 run id 时，由宿主按以下步骤显式清理：

1. 读该记录的 `argv`/`log_paths`，翻看 `.out.log`/`.err.log` 确认失败原因与是否留有
   部分建模产物；确认无 `.host-launches` 之外的清理义务（例如未收尾的
   `.recovery-locks/<root>.lock`）。
2. 核对 `get_run_status(run_id)` 确无 run 根、`.recovery-settlements/` 无该 run 结算记录，
   避免清掉仍被引用的登记。
3. 手工删除 `workspaces/modeling-runs/.host-launches/<run_id>.json` 及同名 `.out.log`/
   `.err.log`（可在台账中留一行删除记录），然后才可用同一 run id 重新 `start_run`。
   run 根仍存在时走 `run_id_already_exists` 分支，禁止用删记录的方式绕过。

现有 outer 原通道（`pause`/`resume`/`stop`/`checkpoint`）行为不变，只是由本工具面封装；
`start_run`/`resume_from_checkpoint` 封装的 CLI 子命令合同不变，CLI 仍是保留入口。
