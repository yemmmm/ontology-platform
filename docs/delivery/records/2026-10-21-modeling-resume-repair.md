# 建模接续已定位问题修复

用户在[原因复盘](../modeling-retrospectives/2026-10-21-codex-glm-low-budget-resume-retrospective.md)
后明确授权“修复已定位问题”。本次归属R4.4-002及R4.3-030／022／029／026，
只修复已证实的责任面，不重算历史费用，不追加金额或调用真实模型。

## 改动与边界

- **验收控制turn。** 按T0删除同一已绑定线程的turn变化终止门及易被steer清除的许可布尔值。
  thread身份、初始隔离、累计用量、预算准入及报告／冻结绑定保持；恢复后立即暂停不再误杀。
- **观察积压。** 只合并未尝试或已明确拒绝／预算延后的观察，使用最新状态和全部未送变化、
  事件、请求回执，追加合并身份记录，原journal不改写。部分确认页、unknown和在途送达
  保留原身份与偏移；历史读取错误及恢复后的事件正文均可见。
- **恢复结清与反馈。** 原provider恢复已实际派发并结清ledger时写出正式issue-control，
  Host待办可正常收敛。重复解决终态issue返回`issue_already_settled`及当前待办指引，
  不再要求重发旧动作；已完成Host依赖返回结果定位和可纠正的等待反馈。
- **过早冻结。** Delivery沿已授权、摘要绑定未变的最新Host结果读取完成状态；仅在其明确
  `selected_scope_complete=false`时提示继续原阶段。同run后续完整结果可立即重试。
  不新增固定题数、隐藏题数量、角色数量或永久流程门，也不重新解释CQ内容。

权威Delivery Skill、MCP参考及030恢复合同同步更新。原失败run、模型revision2、完整题池、
失败报告和旧回执均未改写；原进程不会热加载本次Python／Skill改动。
本轮没有修改backend／frontend或应用配置，不需要应用systemd重启。

## 验证

回归先确认原失败，再验证修复：快速恢复／暂停、同线程累计且拒绝异线程、旧观察与
最新Host结果合并、历史错误与事件不丢、分页／unknown不误确认、issue真实结清和准确反馈、
范围未完成可纠正且后续完整结果可冻结。治理／私有正文未泄露的断言保留。

- 相关模块首轮：193 passed、23 subtests passed；新增历史读取边界5项通过。
- Team全量回归3750项：3735 passed、12 skipped、318 subtests passed，3项旧FIFO断言失败。
  两项改为实际部分送达页／真实unknown送达，第三项验证首份合并输入直接包含原blocked
  Host结果且不会把该业务阻塞清掉；保留原确认及未解决问题边界。
  相关三个模块最终复验 **47 passed**；全量与此次复验之间业务源码没有变化，其他全量
  通过结果复用。没有把首轮3 failed的原日志改成单次全量全绿。
- Ruff按修改文件逐一与HEAD原件对照：现有15项基线问题，无本次新增；不借机清理旧问题。
- 文档新增链接及diff格式检查通过。GitNexus staged检查返回low，但索引未覆盖当前
  方法并有位置偏差；以实际diff、调用点和上述回归验证补足，不宣称完整图覆盖。

原始输出：[全量首轮](../../../workspaces/modeling-resume-repair-20261021/team-full-initial.log)、
[最终定向复验](../../../workspaces/modeling-resume-repair-20261021/focused-recheck.log)、
[静态检查基线对照](../../../workspaces/modeling-resume-repair-20261021/ruff-baseline-comparison.json)。

执行命令：从backend使用`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team -q --tb=short`；
上述两个模块为`test_delivery_cost_regressions.py`和`test_delivery_token_reduction.py`。
新增运行时用例直接调用实际Owner／Runner／Host派生及原生接口桩，不需要供应商调用。

## 结论

上述已定位问题已完成工程修复与对应回归验证；真实净token／费用改善、自主流程及原完整4题的独立语义重验
仍待新的运行授权。保留原PARTIAL，不用开发测试代替L1结果。
评分服务timeout仅定位到降级边界，服务内部原因未确定，本次未猜测性修改评分服务。
