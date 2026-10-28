# OntoWeave v5 执行入口

归属：[R5.0-001](../../docs/requirements/requirements-v5.0.md#r5-0-001)、
[实施计划 P0](../../docs/delivery/implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

当前实现是 **P0 无推理接入检查**。独立包 `ontoweave_modeling` 不导入旧
`modeling_team`／Runner，独立依赖环境不修改后端、默认任务入口或现有任务。
后续有界 Agent、LangGraph 编排和持久业务工作空间按 P0 放行结果推进。
当前 9 项开发测试及未验证范围见[验证记录](../../docs/delivery/test-docs/2026-10-28-v5-codex-p0-validation.md)。

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
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/src modeling_team/v5/tests
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/src modeling_team/v5/tests
```

每次指定不存在的输出目录；已有目录会被拒绝，避免覆盖证据。
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

## 剩余放行条件

P0 V1—V8 仍需真实模型、获准 MCP 与平台资源、原预算账本、PostgreSQL
checkpointer 和独立评价上下文的证据。当前隔离网络的环境只用于无推理检查，
后续真实执行需另接获准 provider／工具路由，不能直接当作生产 Agent。
空 home 实测仍启用了 5 个运行时内置 Skills；后续需按授权裁剪并核对出站上下文。
未满足 P0 放行条件前不进入 P1 全面实现，不切换默认入口。
