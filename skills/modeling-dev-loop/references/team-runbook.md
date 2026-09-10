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

其他业务或验收阶段选择对应 Task/Profile，不把这一 v3 配置固化为所有建模的合法条件。
旧 002/008B/009 Task 保留各自范围，不能冒充完整 v3 入口。旧
`modeling_team.foreground_monitor` 标为 `ARCHIVAL_ONLY`，不要启动。

## 最小准备与启动

在仓库根执行。先核对用户授权和余额、任务允许的源文件/角色输入、依赖健康、已有写入及
进程状态。按任务要求冻结代码/配置/源材料；要求 clean checkout 时使用明确提交或隔离
checkout 保留用户改动，不能清空工作区来满足前置。复用已有健康与验收证据，不展开全面审计。

配置检查不启动模型，也不写平台：

```bash
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-011-competency-question.yaml \
  --task modeling_team/tasks/r3-0-006-real-full.yaml
```

根据本次授权填好 `modeling_run_id`、`modeling_scope_file` 和 `modeling_freeze_started_at`；
scope 复用获准的 create/existing 配置；新建范围可复用
[new-scope-create.yaml](../../../modeling_team/scopes/new-scope-create.yaml)。
时间取本轮真实冻结开始时点，不能编造为满足时间门。
按任务要求使用 `baseline --run-id ... --profile ... --task ...` 保存基线；该命令预览基线，
不创建 semantic start。显式 model profile/overlay 被选用时，validate、baseline 和 run
必须使用同一选择；没有该选择则沿用配置，不擅自换模型。

只有授权足够且最小准备完成后才执行：

```bash
uv run --project backend python -m modeling_team run \
  --profile modeling_team/profiles/r3-0-011-competency-question.yaml \
  --task modeling_team/tasks/r3-0-006-real-full.yaml \
  --run-id "$modeling_run_id" \
  --scope "$modeling_scope_file" \
  --freeze-started-at "$modeling_freeze_started_at" \
  --enable-outer-input-fifo
```

用宿主工具的可持续进程会话承载命令，记录 session/PID、启动参数和宿主输出位置，及时返回
控制权以读取增量。不要等待整轮退出才处理用户问题，也不要把一次不保活的临时工具调用
误报为后台守护。CLI 从实际源码 checkout 运行，scope 指向的是平台资源，两者都要记录。

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

## 外层输入与恢复边界

`run --enable-outer-input-fifo` 创建 `<run-root>/control/outer-input.fifo`。用当前
[CLI](../../../modeling_team/__main__.py) 与 [Runner](../../../modeling_team/runner.py)
已接受的 action，每条消息恰一条换行结尾的 JSON；使用 JSON 序列化或预先写好的消息文件，
不要通过 shell 拼接用户答案。确认 FIFO 仍属于该 live run，并用有界/非阻塞写入，避免进程
退出后宿主卡在打开 FIFO。按返回 rejection 修正对应消息，不手工修改冻结 artifact。

- 用户答案按已显示问题的 run/project/delivery 绑定经 `user` 输入；实际字段以当前合同为准。
- CQ 的 `cq_interview`、`cq_review`、`cq_freeze`、`cq_handoff_complete` 走直接通道，不能
  通过 Coordinator 转发私有问题或答案。审核使用当前 `review_id`、revision/digest，不能
  宿主代批或就地改写冻结题池。具体见 [CQ 设计](../../../docs/delivery/designs/2026-09-08-r3-0-011-competency-question-batch-acceptance-design.md)。
- 已存在 `issue_resolution` 合同的 issue，读取该 issue 的绑定和允许 resolution 后再提交；
  不把此 action 当成任意 run 的通用修复命令。
- 顶层 CLI 没有 `status`/`resume` 子命令。外层 `{"action":"status"}` 只触发 drain，
  不是完整状态快照；直接读上述事件和状态即可。
- 外层 `pause` 会 interrupt 当前 turn；当前 Codex adapter 的 `resume()` 不重建子进程也
  不重新加载代码/挂载。不能靠 `{"action":"resume"}` 或 `state=RUNNING` 证明继续成功。
  同 run 续跑必须由仍有效的输入/issue 通道触发实际工作并看到新的进展证据。
- `stop` 会进入 cleanup，不能当作暂停。存在不确定写入时先查询实际结果，再决定生命周期操作。

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
