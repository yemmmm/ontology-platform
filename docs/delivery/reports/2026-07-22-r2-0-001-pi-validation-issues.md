# R2.0-001 Pi 验证问题清单

本文件只记录已确认或可能影响后续 R2.0-002 的问题；不把未完成的探针视为 Pi 能力不足。

## 已确认问题

### P1：SDK 进程在完成 Session 后不能自行退出

- 证据：使用 `ModelRuntime.create()`、三个 in-memory `AgentSession`，并对每个 Session 调用
  `dispose()` 后，完整合成探针的三份 JSON 产物均已写出，但 Node 进程仍持续运行超过 45 秒，必须由
  `timeout` 终止。Pi `ModelRuntime` 没有公开的 `dispose()` 或 `close()` API。
- 影响：后续采用 SDK 嵌入方式的阶段/批次 Runner 可能无法按任务自然回收进程，导致本地实验脚本或
  CI 卡住。当前不能将“Session 已 dispose”当作进程生命周期已经结束。
- 最小处理：R2.0-002 细化时决定使用持久宿主进程，或采用可明确回收的 RPC 子进程边界；在此之前，
  POC Runner 必须有外部超时与退出策略。

### P2：headless RPC 不会默认信任项目 Extension

- 证据：同一 `/clarify` Extension 命令在 `pi --mode rpc --no-session` 下没有加载，直接走模型并报出
  缺少 API key；加上 `--approve` 后，实际输出 `extension_ui_request`（`input`），外部协调器回传
  `extension_ui_response` 后收到 `clarification_received:workflow-only` 通知。
- 影响：后续 Runtime Adapter 若遗漏明确的项目资源信任配置，Prompt/Skill/Extension 可能未加载，却只在
  首次 Prompt 时暴露为不直观的模型错误。
- 最小处理：将 `--approve`（或等价的受控 SDK trust 配置）作为 POC 启动契约的一部分，并在启动时检查
  已加载的 Skill/Extension 清单；这不是本轮的安全设计要求。

## 可能存在的问题

### P3：upstream 与 npm 发布包不能混用为同一个“固定版本”

- 证据：本轮获取的 upstream `HEAD` 为 `a5afc3f171e422e08a2ccc342827719f9952f38a`；npm
  `0.81.1` 包元数据的 `gitHead` 为 `20be4b18d4c57487f8993d2762bace129f0cf7c6`。
- 影响：若后续一部分探针从 clone 的 `main` 运行、另一部分从 npm 包运行，结果不可复现，且 SDK/RPC
  行为差异无法定位。
- 最小处理：后续只以 `@earendil-works/pi-coding-agent@0.81.1` 的 `package-lock.json` 为执行基线；若需
  验证 upstream 源码，另行固定 commit、独立运行并在报告中与 npm 基线区分。

### P4：Pi 运行时有 Node 版本下限

- 证据：`@earendil-works/pi-coding-agent@0.81.1` 声明 `node >=22.19.0`；本机 `v22.23.1` 可安装并创建
  两个 in-memory SDK Session，因此本轮未受影响。
- 影响：后续将 POC 移到 Node 20 或较早 Node 22 环境会在运行前失败。
- 最小处理：后续启动说明和 CI/开发容器固定 Node `>=22.19.0`，不要把它当作可选依赖。
