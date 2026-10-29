# OntoWeave v5 执行入口

归属：[R5.0-001](../../docs/requirements/requirements-v5.0.md#r5-0-001)、
[实施计划 P0](../../docs/delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

当前实现包含 **P0 接入与 P1.1 整体框架**：显式 CLI、不可变任务绑定、版本化引用、单工作单元 LangGraph、原生执行登记／结果复用、自然回合控制、Host 平台桥和独立交接合同。后续[真实小链](../../docs/delivery/records/2026-10-29-v5-runtime-capability-progression.md)已完成实际应用、治理自查、自然暂停／原 run 接续与独立只读评价，已知六题基准 6/6 PASS，v5 开发测试 83 项通过；其余故障窗口及完整阶段范围继续分项验证。首批框架范围见[实施记录](../../docs/delivery/records/2026-10-29-v5-p1-1-framework-delivery.md)。

独立包 `ontoweave_modeling` 不导入旧
`modeling_team`／Runner，独立依赖环境不修改后端、默认任务入口或现有任务。
Host-only 探针暂时复用旧工具模块，不代表 P1 生产依赖切分已经完成。
P0 的 47 项开发测试、独立工程 PASS、冻结平台小目标 6/6，以及计量 PARTIAL 边界见
[验证记录](../../docs/delivery/test-docs/2026-10-28-v5-codex-p0-validation.md)。默认入口未切换。

## 复跑

在仓库根目录执行，需要 Linux、bubblewrap 和 Python 3.12：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv sync --locked --project modeling_team/v5 --group dev
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling.preflight \
  --model-profile modeling_team/model-profiles/glm-flash-low.yaml \
  --role modeling \
  --output-dir workspaces/v5-codex-p0/manual-001
uv run --locked --project modeling_team/v5 pytest \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/src modeling_team/v5/tests modeling_team/v5/scripts
```

每次指定不存在的输出目录；已有目录会被拒绝，避免覆盖证据。
显式 `resume` 探针使用原目录恢复，保留原分批、业务版本、checkpoint 和 native thread。
PostgreSQL 测试通过 `ONTOWEAVE_TEST_POSTGRES_CONFIG` 指定 Host 连接文件，未配置时明确 skip；
本批真实数据库测试无跳过，仅创建并删除自有随机 schema。
`.python-version` 固定本轮 Python 系列，`uv.lock` 固定 SDK、其绑定 CLI 及依赖。
当前候选为 `openai-codex==0.163.0`／CLI `0.163.0`，与全局 CLI `0.165.0`
分开。官方 SDK 的运行时绑定说明见[官方文档](https://learn.chatgpt.com/docs/codex-sdk)。

## 检查范围

- 从指定角色的现有模型 Profile 读取 provider／model／effort，不静默回退。
- 用真实 SDK 启动其绑定的 CLI，读取生效配置，创建不含 turn 的临时 thread，
  读取原生能力开关、Skills 和 MCP 清单；保存版本、二进制与配置哈希及 RPC 返回。
- 子进程采用现有运行时的 Linux namespace 隔离方式，并额外关闭网络。
  不挂载宿主仓库、宿主 home、隐藏材料或凭据，不继承宿主环境变量；
  模型地址固定为隔离 namespace 内不可用的地址，入口不调用 `turn/start`。
- 使用逐能力原生工具配置，不沿用无效的顶层 `default_tools_enabled`。
  配置读回不证明真实出站工具集合正确，仍须后续 V2 实测。

`preflight.json` 是候选环境证据，不是模型调用、预算结算、恢复或语义验收报告。
它不创建预算、迁移数据库、恢复旧任务或写入业务模型。

## 真实集成入口与剩余边界

`preflight` 入口仍禁用网络。以下脚本使用真实模型或真实平台，必须沿当次授权、
Host 私有连接文件及自有资源运行；本批原目录用于只读证据，不能盲目重放。

| 入口 | 用途 |
| --- | --- |
| `scripts/live_probe.py` | V1 自然工具回合；默认程序校验 JSON，`--native-output-schema` 仅为旧失败对照。 |
| `scripts/integration_cases.py` | 输入隔离、可恢复 SSE 错误、真实压缩与补读。 |
| `scripts/parallel_case.py initial/resume` | 两真实 Agent 的业务记录交接及 PostgreSQL／原 native thread 接续。 |
| `scripts/control_case.py` | 两成员忙碌时排队、自然暂停／停止和输入消费。预算只注入控制信号。 |
| `scripts/draft_case.py` | Agent 从公开来源生成通用定义计划。 |
| `scripts/platform_case.py` | 使用已有 backend 环境复用编译、应用、读取和资源收尾；凭据留在 Host。 |
| `scripts/platform_graph_case.py initial/resume` | 实际应用后的 checkpoint 丢失、未知响应、确认未写入及跨批部分成功。 |
| `scripts/acceptance_case.py` | 独立只读评价冻结目标；实际材料读取、完整题集及模型修订均须核对。 |
| `scripts/memory_case.py write/consume/evaluate` | 两 Agent 同记录版本冲突合并；新消费者仅从共享记忆答题，独立侧按原始依据评价。 |

真实 Agent 已在 thread 创建前通过公开配置关闭上述系统 Skills，工具循环已实际走通。
`outputSchema` 的失败证据保留，用户已确认“自然 JSON 返回＋程序结构校验”。本任务最新授权
取消原 3 元额度门，后续 Host 探针按 `usage_only` 保留原始用量与身份；完整统计覆盖仍 PARTIAL。
此项仅适用于本任务，不改变其他任务的预算。没有新增费用总账或备用执行器。

工作空间只保存候选业务内容；checkpoint 保存执行引用，平台保有实际模型，独立报告保有验收结论。
共享记忆有界验证与边界见[专门记录](../../docs/delivery/test-docs/2026-10-28-v5-shared-memory-validation.md)，
未据此声明完整记忆方案或净降耗通过。
跨批部分成功的恢复只复用原回执并保留已拒绝项，不自动更改分批或冒称全部完成。
P0 选型阶段曾按用户要求暂停，后续已继续共享记忆子集验证；P1—P4、完整计量和默认切换仍须后续交付。

## P1.1 框架入口

从仓库根目录使用同一锁定 v5 环境：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 python -m ontoweave_modeling --help
```

`start`、`status`、`pause`、`stop`、`resume`、`evaluate`、`cleanup` 均显式绑定 `--run-dir`。
首次准备可使用以下命令；它只冻结输入并保存 PostgreSQL 记录，不启动模型或平台资源：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 python -m ontoweave_modeling start \
  --task /absolute/path/task.yaml \
  --postgres-config /absolute/path/postgres-private.json \
  --run-dir workspaces/v5-runs/unique-run --prepare-only
```

去掉 `--prepare-only`，或对已准备目录执行 `resume`，会按获准任务真正调用模型／平台；
首批框架验证没有执行这类真实调用，后续真实小链证据见上述推进记录。旧 `python -m modeling_team` 入口与新任务默认路由未切换。
PostgreSQL 业务 schema 默认 `ontoweave_v5_workspace`，checkpoint 默认
`ontoweave_v5_checkpoints`，可由 Host 显式指定独立名称。私有连接文件为 psycopg 连接参数 JSON，
不会挂给生产 Agent。

任务文件的完整最小形状如下。路径相对任务文件解析；所有示例占位值都须替换为真实获准内容，
其中冻结题集应在生产前由独立侧准备，`sha256` 是其原始字节摘要：

```yaml
schema_version: ontoweave-task/v1
task_ref: authorized-task
run_id: unique-run
work_unit_id: bounded-unit
objective: 本次有界业务目标
materials: /absolute/path/approved-materials
model_profile: /absolute/path/glm-flash-low.yaml
instructions: 本次获准建模方法和角色说明
authorization:
  mode: usage_only
  reference: 当次真实Host授权引用
  budget_ref: 原预算引用（如有则保留）
scope:
  mode: create
  base_url: http://127.0.0.1:8001
evaluation:
  freeze_id: 独立冻结题集身份
  sha256: 替换为64位十六进制原始字节摘要
  case_count: 真实题目数量
```

`approved-materials/manifest.json` 使用已有材料合同，按材料 ID 列出相对 `path`、
`source_ref`、`sha256` 及可选 `source_ranges`。准备后从 run 内材料快照接续；原材料、Profile
变化不静默改变原绑定，快照篡改会返回准确错误。当前 Host 路由只接入 `glm-direct`，按
Profile 精确保留模型／effort；普通金额／次数模式仍待对应阶段接入，不自动降为 `usage_only`。

框架正常链为 `prepare → model → apply → self_check → handoff`。工作空间和 checkpoint
保存精确引用，实际应用仍走已有统一图／明确变更、编译器、跨批绑定及 executor；Host worker
使用 backend 环境，不导入旧 CLI 或启动 `TeamRunner`。原始原生事件、返回、用量及 executor
意图／回执各保留原件。缺失业务输入已接入下述最小 HITL 问答与持久等待；完整 P1.3
范围继续按阶段验证。

当次任务的 `instructions` 应采用[有界建模提示](instructions/modeling.md)，并附入适用的
现有统一图／直接变更／语义定义技术合同；只提供合同名称不足以让隔离 Agent 获得其内容。
业务材料继续以 `source_manifest` 的精确 ID 读取。准备好交给 Host 应用的完整变更返回
`proposed`，应用尚未发生不构成 `recoverable_issue`。后续变更复制 Host snapshot 的
`resource_refs` 到 `existing_resource_ref`；`receipt_item_path` 仅为来源位置，不是该绑定
引用的 path，`artifact_ref` 由 Host 解析，无需 Agent 尝试读取同名文件或 MCP resource。
真实任务中的缺口及修复见[推进记录](../../docs/delivery/records/2026-10-29-v5-runtime-capability-progression.md)。

暂停／停止先登记，等待在途原生回合自然结束，不调用 steer／interrupt；已返回候选保留。
`stop` 不会由 `resume` 静默撤销。未知原执行保持 `reconciliation_required`，有原完成事件或
回执时复用原结果；本阶段不承诺所有故障都能自动重连。应用恢复保持原操作身份和原分批，
不把 checkpoint 当外部副作用事务。

独立评价由 `evaluate --package /absolute/path/independent-materials --evaluation-id stable-id`
启动。该包使用材料 manifest，包含同版本原来源和 `frozen-questions`；Host 加入准确实际目标。
评价只获原材料、冻结题集与治理读取，具有独立原生上下文；不收到生产候选、自查或队列输入。
Host 统一统计所有在途角色供暂停／停止判断。私有题目、答案和理由只保存于评价原件，公开反馈
仅投影 verdict、范围及目标身份。格式或必需读取错误可沿同一评价身份重试，保持原冻结标准；
未知在途执行不会借新报告尝试重启。当前工程 fixture 的 PASS 不代表真实语义 PASS。

## 最小 HITL：问题、答复与主动输入

Agent 回合结束返回 `waiting_input` 和 `human_requests`，每个问题包含 `question`、
`reason`、`impact`。程序保存请求、版本、来源和原步骤后进入 LangGraph 等待节点，
不增加每步审批或常驻 Delivery LLM。工程与真实授权代答证据见
[最小 HITL 交付记录](../../docs/delivery/records/2026-10-29-v5-minimal-hitl-delivery.md)。

在上述锁定 v5 环境中执行，替换为当前实际 run、请求和消息身份：

```bash
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling questions \
  --run-dir workspaces/v5-runs/my-run
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling reply \
  --run-dir workspaces/v5-runs/my-run --request-id human-request-from-questions \
  --request-revision 1 --message-id stable-user-message-id \
  --author user --text-file /absolute/path/answer.txt
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling resume \
  --run-dir workspaces/v5-runs/my-run
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling input \
  --run-dir workspaces/v5-runs/my-run --message-id another-stable-message-id \
  --text '用户主动补充的内容'
```

`questions` 展示原问题、版本、答复和状态，不调用模型。`reply` 关联原请求；`input`
无需先有问题。两者支持 `--text`／`--text-file`、`--author`、`--message-id`、`--partial`。
作者是本机操作者声明的来源标签，不是新增身份认证。未知提交结果重试时复用消息 ID；
同身份不同内容返回冲突。授权宿主代答时保留用户原授权及实际代答作者。

答复先入队；busy 时不打断当前回合，下一适用回合消费。已退出等待的进程用 resume
恢复原 run，没有后台轮询模型服务。收到／交付／消费都不自动关闭问题；Agent 使用
`resolved_request_ids` 明确确认匹配非部分答复解决了哪些请求。重复确认已解决请求为
幂等，其他问题保持未决；基线变化保留旧问题／答复，刷新实际基线供 Agent 判断适用性。

重启／checkpoint 重入复用原始执行、问答及应用身份；应用后等待不重放创建。停止或
交接后的新输入不静默重新打开目标。只读评价获得冻结的有归属人工材料并必须实际读取，
不消费生产输入队列，也不获得写入权限。
