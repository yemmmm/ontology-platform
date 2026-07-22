# R2.0-001 Pi 验证问题清单

验证结论：`BLOCKED`（当前环境）。本文件只记录已确认或可能影响后续 R2.0-002 的问题；不把
未完成的探针视为 Pi 能力不足。

## 已确认问题

### P0：无法完成真实模型调用

- 证据：固定探针依赖 `@earendil-works/pi-coding-agent@0.81.1`，在 Node `v22.23.1` 下运行
  `pi --mode rpc --no-session` 后，提交 Prompt 返回 `No API key found for the selected model`。环境变量
  `ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`OPENROUTER_API_KEY`、`GOOGLE_API_KEY` 均未设置，也没有可用的
  Pi 本地认证配置。
- 影响：R2.0-001 的“至少一次真实模型调用”验收项未执行，因而当前不能给出 PASS/FAIL；自定义工具、
  结构化产物、双角色模型驱动交接和阶段 Summary 的端到端探针也不能完成。
- 最小解除方式：为隔离的 POC Runtime 配置一个可用 Provider 的短期凭证或 OAuth，再重跑合成场景。
  凭证不得写入仓库或 `backend/.local/pi-v2-001/`。

### P1：headless RPC 不会默认信任项目 Extension

- 证据：同一 `/clarify` Extension 命令在 `pi --mode rpc --no-session` 下没有加载，直接走模型并报出
  缺少 API key；加上 `--approve` 后，实际输出 `extension_ui_request`（`input`），外部协调器回传
  `extension_ui_response` 后收到 `clarification_received:workflow-only` 通知。
- 影响：后续 Runtime Adapter 若遗漏明确的项目资源信任配置，Prompt/Skill/Extension 可能未加载，却只在
  首次 Prompt 时暴露为不直观的模型错误。
- 最小处理：将 `--approve`（或等价的受控 SDK trust 配置）作为 POC 启动契约的一部分，并在启动时检查
  已加载的 Skill/Extension 清单；这不是本轮的安全设计要求。

## 可能存在的问题

### P2：upstream 与 npm 发布包不能混用为同一个“固定版本”

- 证据：本轮获取的 upstream `HEAD` 为 `a5afc3f171e422e08a2ccc342827719f9952f38a`；npm
  `0.81.1` 包元数据的 `gitHead` 为 `20be4b18d4c57487f8993d2762bace129f0cf7c6`。
- 影响：若后续一部分探针从 clone 的 `main` 运行、另一部分从 npm 包运行，结果不可复现，且 SDK/RPC
  行为差异无法定位。
- 最小处理：后续只以 `@earendil-works/pi-coding-agent@0.81.1` 的 `package-lock.json` 为执行基线；若需
  验证 upstream 源码，另行固定 commit、独立运行并在报告中与 npm 基线区分。

### P3：Pi 运行时有 Node 版本下限

- 证据：`@earendil-works/pi-coding-agent@0.81.1` 声明 `node >=22.19.0`；本机 `v22.23.1` 可安装并创建
  两个 in-memory SDK Session，因此本轮未受影响。
- 影响：后续将 POC 移到 Node 20 或较早 Node 22 环境会在运行前失败。
- 最小处理：后续启动说明和 CI/开发容器固定 Node `>=22.19.0`，不要把它当作可选依赖。
