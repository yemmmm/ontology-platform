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
| 3/3 | `-s3-r1` | 2026-10-20T14:18:43.998573Z | PARTIAL；金额耗尽，已正式停止并CLEANED，无独立语义验收 |

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

## 第三次运行终态

修复代码已提交`2454530`。第三次完成了真实生产启动、拓扑确认和完整CQ冻结，
冻结池为公开1题／隐藏3题，覆盖相同完整业务范围；没有模型application或独立语义
验收通过证据。切片阶段曾用新编号重复全景题，Host通过正式绑定审核修改原题的切片
归属并删除完全重复副本，Runner逐条accepted，保留全部答案点与未知及原四题分母。
该prompt-contract缺陷现已在通用CQ权威角色说明中明确：按原proposed scope kind分阶段
发布、复用稳定题号，scope-only修改走既有私有Host审核；后续既有CQ／DSH合同检查
24 passed、最小链回归10 passed，链接及diff检查通过。未为验证提示效果新增启动，
不以合同检查证明新提示的真实采用或降耗效果。

第一次预算触及发生于14:33:08Z，当时估算¥3.23246424。迟到原生实测替换暂估后降至
¥2.89209596，原金额授权未变，Host沿`continue_authorized`恢复同一run一次（非fresh
start）。14:35:29Z再次触及¥3.02699692，随后暂停期间暂估／尾差继续增加；没有再次
恢复或新增启动。14:36:32Z正式stop回执accepted／stopped，run进入CLEANED，14:36:47Z
Host监督进程退出130。确切所属PID均不存在，预算全部owner退出，入口关闭，
`control_status=paused_confirmed`；临时管理及验收平台密钥数据库读回均revoked。
scope因已有有效`cq_frozen-0001` checkpoint引用保留，未删除其模型／冻结／原始证据。

最终冻结价表主账：

| 字段 | CNY |
| --- | ---: |
| 原授权 | 3 |
| 已定价数值小计 | 0.99107052 |
| 暂估 | 2.582974 |
| 合计估算 | 3.57404452 |
| 估算超额尾差 | 0.57404452 |

这些数值不等于实际供应商扣费；Host及其他未接线成本不在主账。暂停指令本身没有
立即形成全部owner有效暂停，最终停稳依赖Host正式stop；因此预算暂停／尾差真实验收
仍为PARTIAL，不能用入口关闭或本地测试PASS代替。原始账本仍有10个未闭合inflight
生命周期计数，进程退出不伪造这些请求的实际usage或零消耗。原运行清理原件还保留
`private_credentials_destroyed=false`等限制；只确认上述临时平台密钥已撤销，不声称
所有本地凭据副本都已销毁或全任务成本已结算。

停止时总墙钟约1087秒，生产角色可观察LLM累计772.06秒（非互斥墙钟），实际工具
5.64秒；私有CQ等待窗口910.00秒（与其他工作可能重叠）。没有application，无法据此
给出有效业务语义建模占比；主要耗时落在流程／审核／暂停，停止扩展harness，不再
增加实验。本轮不能形成L1建模质量结论，也没有全任务token降耗PASS。

终态私有证据：`final-budget.json`、`same-run-resume-after-late-reconciliation.json`、
`start3-bootstrap-cleanup.json`、run `state.json`、`competency-questions/frozen/freeze-0001.json`、
Host正式审核／stop回执及`evidence/close-statistics/report-451a80a975f797820d15639f/`。
