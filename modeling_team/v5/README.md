# OntoWeave v5 执行入口

归属：[R5.0-001](../../docs/requirements/requirements-v5.0.md#r5-0-001)、
[实施计划 P0](../../docs/delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

当前实现包含 **P0 无推理接入、真实 SDK／MCP、PostgreSQL 工作空间／checkpoint、自然回合控制及平台故障探针**。独立包 `ontoweave_modeling` 不导入旧
`modeling_team`／Runner，独立依赖环境不修改后端、默认任务入口或现有任务。
Host-only 探针暂时复用旧工具模块，不代表 P1 生产依赖切分已经完成。
当前 47 项开发测试、独立工程 PASS、冻结平台小目标 6/6，以及计量 PARTIAL 边界见
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

真实 Agent 已在 thread 创建前通过公开配置关闭上述系统 Skills，工具循环已实际走通。
`outputSchema` 的失败证据保留，用户已确认“自然 JSON 返回＋程序结构校验”。本任务最新授权
取消原 3 元额度门，后续 Host 探针按 `usage_only` 保留原始用量与身份；完整统计覆盖仍 PARTIAL。
此项仅适用于本任务，不改变其他任务的预算。没有新增费用总账或备用执行器。

工作空间只保存候选业务内容；checkpoint 保存执行引用，平台保有实际模型，独立报告保有验收结论。
跨批部分成功的恢复只复用原回执并保留已拒绝项，不自动更改分批或冒称全部完成。
本批在选型证据结论处按用户要求暂停；P1—P4、完整计量和默认切换仍须后续交付。
