# Codex turn 派发时钟与计量误暂停修复

归属 [R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)。用户在完成本轮
建模测试和计量异常定位后明确要求修复；本次仅修改运行时及回归测试，不启动收费模型调用。

## 真实失败与 T0 复核

原 run 为 `minimal-chain-20261021-codex-glm-5cny-085853-r1`。隐藏验收成员的首个代理
请求开始于 `09:19:56.029323Z`，本地 `llm_start` 记录为 `09:19:56.040079Z`，晚
10.756 毫秒。请求在 `09:20:10.253098Z` 以 HTTP 200 结束，原生 turn 尚在运行。
预算按请求开始时间与 turn 起点严格比较，未能关联在途 turn；到 `09:20:21.034650Z`
误判请求结束后超过 10 秒仍缺 usage，触发全局 `metering_error` 暂停。

计量缺测和预算准入仍须保护；问题是把异步 RPC 应答／通知的本地观察时刻当成因果起点。
删除全部缺测校验会掩盖真实成本缺口，原子应用和独立语义验收也不能证明调用成本。
本次因此修正时钟来源，保留原身份匹配、在途等待、真实 turn 结束后的结算宽限与显式
用户继续规则，不放宽比较窗口，不补造 usage，不改写旧账本或运行证据。

## 实现与范围

- Codex `_rpc` 在持有原 I/O 锁、派发 `turn/start` 前记录墙钟和单调时钟。
- 收到真实原生 turn ID 后，`_activity_turn_start` 使用这组派发时钟记录同一开始事件，
  并消费该暂存值；重复开始通知仍只记录一次。RPC 失败清空尚未消费的派发时钟。
- 复用现有 activity 字段和计量归属合同，不新增平台接口或存储字段。首次鉴权启动、
  后续消息、Consumer／Judge 和预算控制启动均沿同一 `_rpc` 入口。
- 新启动的 Codex 运行时加载本次代码。已完成模型、非盲回归结果及原待命进程保留；
  不以这次工程修复宣称旧进程已热更新或追加真实语义验证。

GitNexus 的 `_activity_turn_start` impact 返回 not found／UNKNOWN。依据当前调用点及
`acceptance.py` 的 Codex adapter 入口检查影响，不宣称图索引已覆盖当前符号。
暂存 `detect_changes` 返回 3 文件、6 符号、0 流程、low；其中函数映射与当前变更不一致，
仍保留索引陈旧限制，不将该结果当成没有调用影响的证明。

## 验证

- 三种时序用例先在原代码上因同一 `metering_error` 失败：普通 RPC 应答先到、普通
  原生通知先到、首次鉴权路径缓冲通知。修复后检查实际 activity 文件及预算投影。
- 用例验证双时钟都来自派发时刻、重复通知不重复计量、在途 turn 不误暂停；turn
  结束后仍无 usage 则原 10 秒结算保护继续生效。既有异线程、异凭据和失败传输用例保留。
- 预算、Codex 计量、owner 集成及 close-statistics 相关测试 **115 passed**；补充双时钟
  断言后 Codex 计量模块 **25 passed**。编译及 `git diff --check` 通过。
- modeling_team 全量回归 **3762 passed、12 skipped、318 subtests passed**，
  556.72 秒；359 项既有 warning，无失败。全量运行使用相同最终生产代码；新增双时钟
  断言另由上述 25 项模块回归覆盖。

日志：`workspaces/codex-metering-dispatch-full-regression.log`。原现场定位和冻结数值回放位于
gitignored 的 `workspaces/minimal-chain-20261021-codex-glm-5cny-085853/diagnostics/`；原件
保持不变。修改不涉及 backend／frontend 或共享运行配置，无需重启本地应用服务。
