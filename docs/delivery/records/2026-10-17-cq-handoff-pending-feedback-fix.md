# CQ生产交接等待回执修复

用户在三轮复盘后明确要求修复问题二，并分析问题一的Delivery任务用量。本次只修
F2反馈合同；F1只补离线分析，不改唤醒／输入策略、不恢复暂缓的021、不新增建模或验收。
归属R3.0-011／016、R4.3-029及AGENTS T0；历史运行／冻结／裁决只读保留。

## 原因与最小修复

原路径：`TeamRunner._handle_cq_handoff_complete`检测到`pending_agents`时，用
`cq_batch_scope_unauthorized`表达“生产角色尚未报告完成”；真实`retry`在CQ异常中
存在，但`_outer_input_receipt_recorder`只持久化code，Host `_receipt_outcome`再统一
提示修binding，导致Delivery误判授权缺口。

现在：

1. 仅pending生产角色分支改为已注册的`cq_production_pending`；真正scope错误保留
   `cq_batch_scope_unauthorized`。JSON角色合同同步。
2. CQ拒绝持久化已有错误的`detail`和`retry`；Host读取时返回`reason`、
   `retryable=true`，`next_action`保留原指导并明确新request_id重试。原始接受回执、
   幂等处理及缺新字段的历史回执保持兼容，不改写旧证据。
3. Delivery实际instructions／skill说明新码与旧证据的含义，仍核对真实生产完成，
   不扩大授权、不补无关delivery_binding、不等run先terminal。

T0复核：生产角色尚未完成时，直接封写会阻断最后写入，故readiness校验必要且保留；
其拒绝原本可恢复，问题在反馈分类及持久化丢失，不应删除校验或再增审批门。
等待拒绝不quiesce、不生成handoff；角色完成后用原freeze绑定和新request_id正常交接。

## 影响与兼容性

GitNexus impact未找到`_handle_cq_handoff_complete`和`_receipt_outcome`，风险UNKNOWN，
不能声称图完整覆盖。已聚焦检索Runner CQ dispatch、CLI共用stdin/FIFO admission、
回执写入、Host请求结果与幂等重查、Delivery实际说明及CQ注册合同。受影响的是
pending-role拒绝和CQ回执附加指导，未改后台平台API／授权／写入算法。
提交前detect_changes返回low／0流程，但符号映射包含不匹配旧位置，仍不能作为完整
图覆盖；实际影响结论以调用点、diff和上述合同回归为准。

所有历史scope拒绝码继续存在；历史CQ回执缺detail/retry时继续沿旧通用提示。当前
新Runner／Host进程加载修复，保留待命线程不热改、不为测试启动新模型或终止旧组。
`backend/`及`frontend/`无改动，应用systemd服务不需要重启。
接口说明同步[宿主MCP文档](../../reference/mcp.md#r43-029-deliveryhost-私有接单)。

## 验证记录

- RED：修改现有premature-handoff断言及新增端到端回执用例后，先在旧实现运行，
  2 failed／22 deselected；实际错误均为旧授权码，与预期等待码不同。
- GREEN：Runner handoff／CQ wiring／CLI receipts／Host ops四文件，**167 passed**。
  新用例走真实Runner及共用CLI admission→持久化→Host读取；断言等待码、原因、
  对应重试指导及保持生产写入开放，再以原freeze、无delivery_binding、新request_id
  成功交接至read-only。旧回执和真正scope拒绝的原测试继续通过。
- Team全量：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest
  ../modeling_team/tests -q`，**3140 passed、12 skipped、318 subtests passed**，
  283.53秒；359条依赖弃用／多线程fork警告，0 failed。
- Ruff逐文件与HEAD基线比较：0新增；9条历史诊断保持，未顺带修复无关导入／变量。
- Delivery skill quick_validate、CQ JSON注册码唯一性及diff格式检查通过。
- Delivery任务用量：95个唯一response、三次已绑定压缩；三个原生线程逐响应求和
  与终态累计全部一致。原件hash／离线脚本及数值JSON保存在既有Host私有复盘目录。
  详见[复盘任务归属追加](../modeling-retrospectives/2026-10-17-flashx-serial-deep-retrospective.md#6-用户追问delivery-token主要完成了什么任务)。

本次是开发回归与保留证据分析，不是新独立语义验收或实际Agent自主接续PASS。
