# Codex三次续跑与金额计量修复

用户授权“3次启动建模的机会，遇到问题定位问题并解决，然后重新启动建模”，并明确
“仍同时受原3元额度限制”。执行者为Codex，所有选定模型保持`glm-5.3-flash`／`low`。
业务仍为[R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026)的通用最小安装链；
资源合同为[R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)，自动观察投递调整
归[R4.3-030](../../requirements/requirements-v4.3.md#r4-3-030)。

## 授权与原费用

三个新semantic start全部绑定原预算
`workspaces/minimal-chain-20261020-codex-glm-3cny-123453/budget`，授权总额仍为¥3，
没有追加、重建或清零。旧失败run、原事件及报告均保留；每次停止先取得官方stop回执，
再结束旧Host监视进程并撤销其临时管理凭据，避免旧代码持续改写新计量结果。

原中断调用没有真实token回执。Host依据同线程相邻真实原生数值，以最大实际单次
输入45680、输出220的两倍暂估输入91360、输出440，按冻结的未命中输入及输出价
估算¥0.09312，绑定唯一proxy session／request／attempt。该值是有数值依据的暂估，
**不是实际usage或严格上界**，不伪造缓存率。未来对应真实回执到达时替换暂估。

## 真实失败与最窄修复

新Host目录：`workspaces/minimal-chain-20261020-codex-restarts-135307/`。
三个run前缀均为`minimal-chain-20261020-codex-restarts-135307`。

| 启动 | run后缀 | 真实semantic-start UTC | 结果／首阻塞层 |
| --- | --- | --- | --- |
| 1/3 | `-s1-r1` | 2026-10-20T14:01:00.327091Z | 已停止；自动观察steer取消Codex在途响应，client_disconnected缺数触发预算暂停，runtime/infrastructure及platform-contract |
| 2/3 | `-s2-r1` | 2026-10-20T14:09:48.331409Z | 已停止；传输先结束、原生数值后到，整体计数门把既有覆盖撤回，platform-contract |
| 3/3 | `-s3-r1` | 2026-10-20T14:18:43.998573Z | 真实建模中；结果待原件闭环 |

这些失败不构成modeling-quality结论。没有第4次启动授权。

T0复核：金额边界、来源／凭据匹配及真实缺测暂停仍有必要，但已计价的原生数值与
传输行重复要求逐请求usage，会把可对账的迟到／中断变成整个run不可用。保留原数值
核算和冻结价表，用同capture session／provider／credential alias／model的传输组
核对去重原生样本；仅对未匹配差额以该组已观测最大真实单次输入／输出的两倍暂估。
新原生数值到达后，差额暂估相应减少，避免叠加；原始失败状态保持，未虚构请求级回执。
不同凭据、无数值依据、真正累计回退和缺价继续保留可恢复暂停。

Host-only的`record_attempt_estimate`只绑定已结束的唯一调用并写明依据，不增加授权、
不清除暂停，也未暴露给Delivery／生产模型。重复提交替换同一估算，不重复累计。

另将Codex自动状态观察保留在原待送队列，忙碌时不再steer，等待自然turn结束再投递；
显式用户输入与预算控制保留各自即时通路，程序仍约2秒观察。DSH路径保持原行为。
该调整修复权威执行行为，未以运行中临时提示代替持久修复。

## 验证与证据边界

- 修复前复现缺数／迟到覆盖及忙碌观察取消问题；当前定向预算、Delivery输入／观察回归通过。
- 当前4个修改Python文件Ruff、diff及本地链接检查通过；最终Team全量回归
  **3703 passed、12 skipped、318 subtests passed**，628.29秒、359项warning、0失败。
  命令为`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --disable-warnings --maxfail=8`。
- GitNexus索引滞后，新计量符号无法解析；用当前源文件、注册调用点、测试及diff核对，
  不声称取得图索引完整影响覆盖。暂存detect_changes为7文件／0符号／0流程／low，
  该结果受旧索引限制，不能等同当前代码无跨模块影响。
- 仅修改modeling_team与需求／交付文档，不涉及backend／frontend应用代码，无需重启本地应用服务。

私有原件包括`authorization.json`、`interrupted-attempt-estimate.json`、
`pre-start3-reconciliation.json`、各次bootstrap／凭据生命周期记录、各Delivery session、
run目录、`final-repair-team-regression.log`。私有CQ审核通过原Host journal记录，
题目及答案不注入Delivery或生产角色；冻结不代替独立Consumer／Judge验收。

当前费用由本地冻结价表估算，含暂估及尾差；不等于供应商账单。外层Host等未接线费用
不计入这个主账，也不以此报告全任务财务覆盖。原始费用、暂估、真实替换及三次失败
均保留，不能仅汇报第三次的局部成本。
