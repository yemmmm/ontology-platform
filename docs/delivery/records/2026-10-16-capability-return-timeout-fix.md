# Runner capability 成功结果回传丢失修复

当前范围为 [R4.3-024 F4 / R4.3-025 F5–F6](../../requirements/requirements-v4.3.md)
要求的回执与原调用反馈，不改变业务语义、授权、原子 apply 或独立验收。
用户要求先定位并解决第三个问题；本次不授权或启动任何新真实建模轮次。
历史失败模型及证据保持原样。

## 原故障与复现

源 run `r4326-20261016-postfix-flashx-round2`，原调用
`call_9f3b36d0c0a1473a89b727fc`：19:13:48.676 UTC 发出 submit，
19:14:05.550462 capability audit 已 ok，平台 Batch/Attempt 为 applied；
native 无相应 function_call_output/item-completed，19:18:48.794396 被 300 秒 watchdog 终止。

根因链为两处叠加：`_stdio_request` 对整个 Unix socket 调用设 15 秒超时，
服务端业务执行超过该窗口时客户端提前断开；`run_stdio_client` 随后异常回包使用
`id:null`，丢失原 JSON-RPC 请求 ID，客户端无法将其归入原等待调用。

对提交 `ca97c15` 的独立机械复现使用真实 Unix socket、RunnerCapabilityEndpoint
和 stdio client；仅注入 17 秒确定性工作，不调用平台、不启动 LLM 或语义建模。
请求 ID 为 73，旧 client 在 15.015 秒返回 error/id:null；dispatch 在 17.000 秒完成，
audit 仍为 ok。与实际失败链一致，不能把 300 秒 watchdog 当作最初故障原因。
原 live 没有保留 stdio 异常回包，具体异常发生由此精确代码路径与机械复现支持，
不是声称已从旧 run 找到一份不存在的 id:null 原始消息。

复现脚本及原始输出位于本机 gitignored
`workspaces/capability-return-repair-20261016/`，没有修改旧 run 证据。

## T0 与影响范围

业务响应 15 秒门不保护源忠实度、授权或原子性，反而可在成功写入后丢失回执。
连接/发送边界仍可有界，响应阶段复用现有 MCP/运行生命周期监督；不通过盲目放大
全局 timeout、不重放 apply、不添加结果重投递或恢复框架来掩盖问题。
合法请求的异常响应须关联原 ID；格式不合法而未能取到 ID 时仍为空。

GitNexus 对 `run_stdio_client` upstream 返回 CRITICAL，已在编辑前告知用户。
图中直接调用为本文件 main，共享模块由 Codex runtime staging 与 acceptance 引用；
图还泛化出 92 个流程/20 模块，不能把这些同名/导入传播视为逐条运行覆盖。
定向代码核对为所有使用 Runner capability stdio 通道的角色，平台 HTTP API 无变更。
具体变更和验证结果见下文。


## 最小修复与独立回传复测

`_stdio_request` 在 connect/send 后清除 socket read deadline，成功结果等待归现有
MCP/session 生命周期；没有延长 watchdog 或添加重投递。`run_stdio_client` 每行
重新初始化 request_id，已解析合法请求异常时返回原 ID，坏 JSON 不复用前一条 ID。
Token/role/schema 校验、服务端处理、写入身份和原子执行逻辑没有修改。

相同 17 秒 Unix socket 复测在 17.001 秒完整返回 result，ID=73 正确，dispatch 一次。
另以真实 CLI 子进程/OS stdin-stdout pipes 复测，17.046 秒完整返回同 ID 成功结果，
进程退出码 0。两项均无平台调用、无语义 start；它们验证回传机制，不证明旧模型语义质量，
也没有让已终止的原 Modeling 恢复。原版/修复后/真实 CLI 输出均保留于上述技术工作目录。


工具限制补记：GitNexus 仓库索引停留 2026-09-15、落后当前 370 提交，
`detect_changes` 将本次部分改动映到旧 `__all__` 行段并混入不在当前 diff 的文档符号。
因此其风险评级仅作警示，不能声称本次图影响覆盖准确；没有为小修复重建全索引。
当前调用点检查以 `main → run_stdio_client → _stdio_request` 及
`runtimes/codex.py` 将源码复制为 agent.home/runner_capability_mcp.py 的实际代码为准。
复现源码与原失败 run staged 客户端 SHA-256 完全相同，源匹配原证也保存在技术工作目录。


## 回归、提交与生效边界

新增两条行为回归：真实 Unix socket 的 80ms 延迟响应超过缩短为 20ms 的连接预算时，
仍返回完整原 ID 结果且只执行一次；异常情况下 string/int 请求保留各自 ID，后续坏 JSON
返回空 ID 而不串用前一条。将新回归注入 `ca97c15` 原函数后实际失败，分别为 TimeoutError
和 AssertionError；修复后通过。旧版服务器的 BrokenPipeError 作为预期断连旁证保留。
前后机械探针、回归旧版失败及源码匹配原始 JSON 均已落盘，不含真实密钥。

共享通道及直接建模相关七文件验证为 **91 passed，18.97 秒**：
`test_cq_capability_dispatch_regression.py`、`test_r3011_runner_wiring.py`、
`test_r23005_a_revision.py`、`test_direct_modeling.py`、`test_direct_submission.py`、
`test_direct_modeling_wiring.py`、`test_r4326_minimal_chain.py`。
Ruff 与 diff 空白检查通过。没有宣称 Team 全套或真实语义验收通过。

变更仅 modeling_team 客户端与对应测试，不触及 backend/frontend 可执行代码，
无需应用服务重启。新启动的 MCP 客户端会使用修复；已冻结的旧客户端不会热更新，
已终止的原 Modeling 不会因此恢复。旧 run 保持原结论和模型，本次 semantic starts=0，
额度没有变化。未增加工具、接口、表、治理门或恢复框架。

结论：已复现并修复可确定的“15 秒业务读超时 + 异常回包丢 ID”缺陷，
隔离机械回传与相关工程回归通过。原 live 未保留异常 stdio 帧，不夸称已取得旧现场的
全部桥接日志；下一次真实建模仍需新授权，当前不以本修复替代缺失的独立语义验收。
