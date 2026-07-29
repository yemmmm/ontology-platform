# R2.1-001 M5 测试轮次状态

- 记录日期：2026-07-29
- 最终状态：`CLOSED / FAIL`
- 保留范围：仅保留每轮测试的结论和最小原因；已关闭的 M5 测试实现、输入包、设计和详细测试计划均已清理。
- 说明：离线门禁 `PASS` 只表示对应修复通过，不代表 M5 通过；未执行的平台闭环不能补记为通过。

## M5-P0：Pi 对 M3 静态合同兼容性预演

| 轮次 | 状态 | 最小结论 |
| --- | --- | --- |
| 1–4 | `BLOCKED` | Pi JSONL/SSE 终态读取与路径/协议证据未满足。 |
| 5 | `FAIL` | 双次真实 settlement 已修复，但 Ruff 门禁失败且 Producer/Consumer/Batch/mutation 未执行。 |
| 6 | `PASS` | Round 5 的格式问题修复；双次 settlement 证据有效。 |
| 7 | `BLOCKED` | Producer 预演形成 validated 54-item baseline，但 apply 因 lease 过期失败，未进入下游闭环。 |
| 8 | `PASS` | Host-side lease recovery 离线状态机通过；未重跑真实 Producer。 |

阶段结论：`阶段收尾（部分验证，不构成 PASS）`。该场景不再继续实现 Pi 专属 Consumer、mutation 或 Host 编排；其问题证据仅作为 v2.2 R2.2-001 的 Adapter 迁移输入。

## M5：Pi 对 M4 交互式建模合同复现

| 轮次 | 状态 | 最小结论 |
| --- | --- | --- |
| 1–4 | `FAIL` / `BLOCKED` | 准入、传输或运行前置条件未满足，未形成有效正式闭环。 |
| 5 | `OFFLINE_READY` | Round 4 修复后的离线准备通过。 |
| 6 | `FAIL` | Pi 的澄清问题/执行序列未满足冻结的 M4 合同。 |
| 7 | `PASS` | Round 6 修复的离线门禁通过。 |
| 8 | `INCONCLUSIVE` | 正式调用的上游终态无法据此判定成功。 |
| 9 | `PASS` | Direct-DeepSeek 离线门禁通过。 |
| 10 | `FAIL` | Direct schema 合同不匹配。 |
| 11 | `PASS` | Round 10 schema 修复的离线门禁通过。 |
| 12 | `FAIL` | 嵌套 Modeling Item 合同不匹配。 |
| 13 | `PASS` | 嵌套 Modeling Item/envelope 修复的离线门禁通过。 |
| 14–15 | `FAIL` | 正式证据审计失败。 |
| 16 | `PASS` | Round 15 修复的离线门禁通过。 |
| 17–18 | `FAIL` | Pi 在 dry-run 中错误携带 lease token；未发生 Modeling Batch 写入。 |
| 19 | `PASS` | 精确 token-retry 的离线门禁通过。 |
| 20–21 | `FAIL` | Pi 未正确完成合格澄清问题的选择/工具顺序。 |
| 22–23 | `FAIL` | `item_ref` 与依赖拓扑的引用合同不匹配。 |
| 24 | `PASS` | item-reference 指引修复的离线门禁通过。 |
| 25–26 | `FAIL` | canonical writer 子进程配置缺失。 |
| 27 | `PASS` | canonical writer 子进程修复的离线门禁通过。 |
| 28 | `FAIL` | entity `properties` 映射不符合平台校验。 |
| 29 | `FAIL` | 最小 M4 Host + Pi 正式运行未达 M4 `COMPLETED`。 |
| 30 | `FAIL` | 正式运行前置检查失败。 |
| 31 | `INTERRUPTED` | 主机重启中断；结果仅作历史重建。 |
| 32 | `FAIL` | 最终正式尝试的前置检查失败。 |
| 33 | `FAIL` | 最后一次常规授权的 live 尝试失败。 |
| 34 | `FAIL` | 例外尝试 1/3 失败。 |
| 35 | `PASS` | security-correction 离线门禁通过。 |
| 36 | `FAIL` | 例外尝试 2/3 失败。 |
| 37 | `PASS` | 最后尝试前的离线修复门禁通过。 |
| 38 | `FAIL` | 例外尝试 3/3 失败。 |
| semantic-package 离线 2–3 | `FAIL` | semantic package 的协议/证据链不满足。 |
| semantic-package 离线 4 | `PASS` | 离线修复门禁通过；不代表 live 成功。 |
| 39 | `FAIL` | Provider 502 终态失败且 Pi 未串行消费 canonical clarification；无语义包、无平台写入。 |

最终结论：新增授权已用尽。Round 39 是最终 live 结果；不得自动重试、修复 Runtime/semantic package/Host executor，或创建平台资源。未来执行需建立新的范围与模型调用授权。
