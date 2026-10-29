# v5 金额控制最小接入

日期：2026-10-29。基线 `e5a6756`。用户要求按既定能力计划继续，当前承接
[R5.0-001 F4／F7](../requirements/requirements-v5.0.md#r5-0-001)、R5.0-007 F5 及
[能力推进顺序](2026-10-29-v5-next-capability-priority.md)中的金额控制。

## 当前实现与最小选择

- v5 的 TaskControl 已持久保存预算开闭、在途活动及自然回合停稳状态；P0 控制实验
  仅注入 budget_pause／budget_resume，尚无正式金额链。
- Host 的 `modeling_team/task_budget.py` 已有授权、价表快照、累计去重、追加、覆盖与
  尾差投影；不需要新总账或新存储。v5 Host worker 使用现有后端环境，框架侧继续通过
  固定 HostBridge 调用，不引入旧 Runner。
- 实际 `provider-usage.jsonl` 提供传输身份与终态；金额数据来自 Codex 原生累计通知。
  二者必须绑定同一捕获会话；不能将传输次数当作另一次费用，或把累计快照重复累加。
- 本批采用冻结任务的 `amount + budget_ref`；新回合前、回合终态保存后及平台活动前
  刷新已有账本，再投影到原 TaskControl。当前忙碌回合不插入 HTTP 请求级金额拒绝。
- `budget`／`budget-add` 是 Host CLI；Agent 不获得创建／追加额度工具。追加授权、价表
  与用户暂停保持各自含义，新增阈值不能成为扩大业务范围的授权。

## 验证范围

在原有 PostgreSQL、Codex SDK／CLI、GLM 路由与公开工程 fixture 上验证：很小的测试
阈值耗尽、忙碌时等待回合结束、无追加恢复不新开调用、新 CLI 追加后原 run 接续、
同一执行不重放及单次实际应用。公开评价仅检验小场景，不升级为完整语义验收。

本轮研发仍由既有不限消耗授权覆盖。真实实验的 0.001 元初始值与 1 元追加是 Host
用于触发控制路径的工程测试阈值，不宣称用户追加了一个新的消费上限。
价表复用 `modeling_team/task-budget-prices.json` 的用户配置版本，不宣称它是当前市场价格。
外部 Host 原始用量未知并单列，不计入任务金额；native 计量覆盖与提供商最终结算分开报告。

GitNexus 对 CodexInvocation 和账本目标返回 UNKNOWN／not found，本批采用当前代码、
调用点与实际回归检查；不以空图结果证明无影响。没有修改现有账本核心或部署服务。
