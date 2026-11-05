# Codex CLI 执行记录展示粒度

- 日期：2026-11-01
- 问题：交互界面、推理摘要和非交互执行事件是否可以调整展示粒度。
- 本机版本：`codex-cli 0.166.0`，通过 `codex --version` 确认。
- 范围：只读核对本机 CLI 帮助、安装包与官方文档；不修改用户配置、不发起模型调用。

## 核对记录

- `codex --help`：支持 `-c key=value` 临时配置和 `--strict-config`。
- `codex exec --help`：支持 `--json` 输出 JSONL 事件，`-o/--output-last-message` 保存最终消息。
- 安装包二进制包含 `hide_agent_reasoning`、`show_raw_agent_reasoning`、`model_reasoning_summary` 和 `model_verbosity` 字段；字段作用及取值以以下官方配置文档为准。

## 结论

可以分别调整推理事件显示、推理摘要详略和终端呈现方式。本次核对的帮助与官方配置文档中，没有发现统一控制全部工具调用、参数、输出展示粒度的 `quiet/normal/verbose` 开关。

| 需求 | 配置或操作 | 边界 |
| --- | --- | --- |
| 隐藏推理事件 | 顶层 `hide_agent_reasoning = true` | 官方说明适用于 TUI 与 `codex exec`；不能据此推断其他工具事件也被隐藏。 |
| 推理摘要详略 | 顶层 `model_reasoning_summary = "auto" / "concise" / "detailed" / "none"` | 具体支持情况依模型；不是工具输出长度设置。 |
| 显示提供方发出的原始推理内容 | 顶层 `show_raw_agent_reasoning = true` | 只有当前模型实际发出这类内容时生效；不会解锁未提供的内部推理。 |
| 便于终端选择与复制 | `/raw` 或默认 `Alt+R`；持久设置为 `[tui]` 下 `raw_output_mode = true` | 切换原始滚屏格式，不代表取消工具输出截断或增加执行事件。 |
| 导出程序可处理的执行事件 | `codex exec --json "任务" > events.jsonl` | 非交互模式；可以由调用方按事件类型筛选呈现。 |
| 调整回答详略 | 顶层 `model_verbosity = "low" / "medium" / "high"` | 需要模型支持；控制模型回答，不是执行日志级别。 |

临时减少推理显示：

```bash
codex -c hide_agent_reasoning=true
```

长期使用可把下面配置加入 `~/.codex/config.toml` 的顶层，避免误放在其他 TOML 表内：

```toml
hide_agent_reasoning = true
```

如果希望保留简短推理摘要，可以使用以下配置；具体摘要支持取决于模型：

```toml
hide_agent_reasoning = false
model_reasoning_summary = "concise"
```

`tool_output_token_limit` 的官方定义是工具输出存入历史的 token 预算，不能当作纯粹的屏幕展示长度设置。

## 验证范围

已核对本机版本、CLI 帮助、二进制字段及已打开的官方页面。未修改用户配置，未启动模型任务，也未进行交互界面操作验证。不能据此宣称所有模型均支持所有摘要或 verbosity 档位。

当前官方命令文档将 `Ctrl+O` 标为复制最近完成的输出；本次不沿用旧版本教程中“展开记录”的快捷键说法。

## 来源

- 本机：`codex --version`、`codex --help`、`codex exec --help`。
- [官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)：推理显示、摘要、verbosity、`tui.raw_output_mode` 和 `tool_output_token_limit`。
- [官方 CLI 命令参考](https://learn.chatgpt.com/docs/cli/reference)：`--json`、`--output-last-message` 和快捷键。
- [官方交互命令参考](https://learn.chatgpt.com/docs/developer-commands?surface=cli)：`/raw`、`/tui` 和 `/export`。
