# Codex预算原生用量与活动乱序关联修复

用户授权：定位并尝试修复本轮金额计量问题。范围归属
[R4.4-002 F5／F6](../../requirements/requirements-v4.4.md#r4-4-002)：独立来源乱序、
真实用量去重及可恢复计量反馈。本次不追加金额、启动新建模或恢复原暂停任务。

## 首阻塞与根因

原session为`minimal-chain-20261022-codex-glm-low-3cny-101405`，run为同名加`-r1`。
采用Codex／glm-5.3-flash／low，金额授权3元，初建1轮、fresh start 1次，无模型application，
独立语义验收尚未开始。原始结果和失败证据保留；不能据此判断模型质量。

`budget/state.json`原coverage唯一异常指向共享activity文件byte_offset=16757：
Modeling turn `01a1631d-c918-7511-8c65-70baccd67b6e`。
原生capture在2026-10-22T10:17:40.689366Z已经发布该turn的累计用量，
活动结束为10:17:40.693847Z；预算按独立source消费时，可能先读用量、后读活动。
`_update_attempt`对尚无对应activity的thread_usage直接返回，已消费数字不会因后来
activity出现而重试关联，导致has_usage=false，宽限后误报metering_error。

另一个同路径遗漏是：已有已计价用量后，仅新活动到达时，tick可能不重新计算summary，
新结束但确实缺数的turn也不能及时进入待结算／异常。这是计量合同缺陷，不是业务建模缺口。

## 最小修复与防御复核

- summary计算使用已有保留的Codex累计数值重新关联同thread／turn活动，复用原关联方法，
  不制造请求级usage，不重复计费；不同turn的数字不能覆盖缺数。
- tick在新增attempt时重算summary，无新活动／用量的健康tick继续复用已有投影。
- 保留缺少可信usage时的暂停：真实缺数直接保护金额授权，不能删掉或把费用填零。
  只纠正“已有明确原件却丢失关联”的误报；不增新守卫、编排或恢复机制。

影响检查：GitNexus impact找不到`_refresh_summary_unbounded`；staged detect_changes识别
两个代码文件但没有映射到符号，因此不宣称图覆盖。实际检查TaskBudget summary/tick、
RuntimeBudget注册、ActivityRecorder及Delivery／生产／验收预算接线和已有调用点。
只改预算内核及回归测试，不改API、平台业务语义或角色写入合同。

## 暂估金额的独立核对

| 来源组 | 成功传输 | 不同原生数值快照 | client_disconnected |
| --- | ---: | ---: | ---: |
| 生产Team共享capture | 43 | 43 | 6 |
| Delivery capture | 16 | 16 | 11 |

59次成功传输与59份原生数值对应；17次中断没有对应usage，原算法依据同身份已知最大
单次输入／输出的两倍暂估，未伪造缓存率。两组暂估分别0.554676和3.516458元。
因此原4.40594164元投影中，已定价0.33480764元、暂估4.071134元；这不是供应商账单。
修复乱序关联后金额不变，不能把17次真实中断的暂估直接删除或以0.335元代替全部消耗。

Delivery输入记录显示多次critical_event及busy steer，与断流时段重叠；10-20已有
[自动steer取消在途响应的历史](2026-10-20-codex-three-starts-repair.md)。
本轮未取得17次请求各自完整的取消原因或供应商usage，不能把所有中断归因于同一原因，
也不借本次修复改写R4.4-003用户／Host即时输入合同。此限制继续披露。

## 验证与账本修正

新增“数字先到、活动后到、跨tick及预算reload”参数化回归：同turn正确关联、其他turn
继续异常；修复前失败，修复后通过。预算内核、代理、集成、CLI及暂停合同106项通过。
Modeling Team全量回归3823 passed、12 skipped、318 subtests passed（446.57秒）；
359条warning保留在原输出，无失败。仅工程测试，不调用收费模型或进行真实语义验收。

原账本私有副本只读重算：唯一错误消失，准确补关联上述Modeling turn，已定价、暂估和
总额均未改变。随后通过原TaskBudget追加`host_metering_reconcile`事件写回关联修正，
保留原始state备份、事件、金额、3元授权及历史暂停原因。当前coverage.issues为空，
`admission_open=false`、`control_status=paused_confirmed`；原run仍PAUSED。
没有调用continue_authorized、清空预算、追加金额或发起任何收费模型请求。

本次仅改`modeling_team/`与本文档，无backend/frontend改动，不要求平台服务重启。
暂停中的旧Runner不热加载补丁；原账本关联修正保留，后续获准运行使用当前代码。
工程回归和账本修正不构成真实建模、独立语义验收或预算最终结清PASS。

## 原件

- `workspaces/modeling-budget-repair-20261022/ledger-recompute.json`：只读重算前后与补关联turn。
- 同目录`transport-coverage.json`、`original-budget-state.json`、`live-ledger-reconcile.json`、
  `team-regression.log`；原数值文件和原run不移除。
- 原Host目录`workspaces/minimal-chain-20261022-codex-glm-low-3cny-101405/`下
  `final-budget-snapshot.json`、`host-budget-intervention.json`与`result-summary.json`保持历史含义。
