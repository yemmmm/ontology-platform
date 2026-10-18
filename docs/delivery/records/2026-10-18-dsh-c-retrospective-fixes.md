# DSH low C组复盘问题修复

用户授权“请修复发现的问题”，承接[C组复盘](../modeling-retrospectives/2026-10-18-dsh-low-c-retrospective.md)，
沿R4.3-022／029／030／032／035修复现有输入、投影和方法采用，不增加建模权限或新机制。

## 根因纠正与修改

1. **宿主任务在v2筛选中遗漏。** C组配置把900秒timeout、operation前缀、关闭要求及
   其他约束写在`delivery_objective`，另有`authorization_budget`、`initial_run_id`、
   `freeze_started_at`。实际native delivery_start只包含observed_state和session_reference，
   `_task_context`未选这些字段，故不能将偏差直接归为Agent忽略已收到的指令。
   2026-10-14旧路径曾发送完整config的历史结论保留，不能证明本次v2路径也发送了它。
   现在明确传入以上字段；完整目标只在bootstrap／恢复提供，更新走changes，不变正文
   不反复注入。额度标明配置快照，余额沿实际轮次核算，不新增平台次数硬门。
2. **补读参数说明不足。** 原工具selection仅是无字段object，Agent把length当页面大小、
   沿过期observation引用重读并猜测授权文件。补齐现有bytes／json参数说明和具体读法，
   指向返回的原件范围／continuation及当前窄查询；保留精确区间超界拒绝、摘要与权限。
   新说明明确reference不是文件读取授权，没有扩大可读目录或截断原件。
3. **成功交接仍推动决策chain。** 只将可识别的DSH queued派发、artifact received及
   public-input queued／claimed／settled作为例行记录；原件与程序观察保持。
   pending／failed／canceled／unknown、错误、损坏及未知形状继续送达；普通角色消息
   未整体屏蔽，也没有把48次event-only投递全部当作可删除调用。
4. **原生错误标志遗漏。** tool/result的message.isError未参与成功过滤；碰巧为成功
   JSON的错误正文可能被过滤，普通文本错误则只剩原件引用而无明确错误标志。
   现在该标志始终保留为决策，并投影tool_error，不扩散工具正文或私有CQ。
5. **生产侧身份／路径试错。** DSH实际加载说明按冻结Profile列出本角色获准接收方，
   明确Host不是队友endpoint、reply只用于仍活跃的反向请求、材料按已发布成员路径读取，
   Coordinator仅用现有三种scenario-map文件名。已终态队友不再接收纯进度通知。
   未消费输入守卫仍保留，沿原反馈自然结束活动再接收，没有新增终态协议或无界重试。
6. **报告资格与关闭描述。** Host验收摘要补出原报告blind_status字符串，隐藏曝光明细
   留原件，旧报告缺值返回null；Delivery按原标签描述，不从hidden推断blind。
   同时明确宿主原始参数及关闭要求、standby与stop的区别。未新增自动关闭机制。

本次修改仅modeling_team及文档，无产品backend／frontend代码或共享配置变更，
不需要产品systemd服务重启。新进程加载；不热改或重启已经关闭的C组及旧授权。

## 影响与验证

GitNexus未找到Delivery当前投影和报告摘要符号，风险UNKNOWN；对共享mcp_response返回
CRITICAL（138个受影响符号、96个流程），已向用户告知，并避开该共享入口修改。
实际核对Delivery bootstrap／恢复／投递／查询、原生错误与035 journal、Host报告摘要及
DSH装载调用点；不声称图覆盖当前Delivery代码。
staged detect_changes返回low，但changed_symbols为空；同样不能当作当前符号覆盖。

- 回归先在旧代码观察到目标缺失、成功交接重复唤醒、错误标志遗漏及盲评标签缺失。
  首次一条错误测试未消费bootstrap而读错packet，纠正后确认真实tool_error缺失；
  后续又先复现完整目标重复进入稳定delta，再修复。
- 定向四文件：**190 passed，19.44秒**；原件分页／摘要／权限、输入更新与恢复、
  正常交接不唤醒、真实错误／pending／unknown可见及报告资格不泄露明细均覆盖。
- Team全量：**3349 passed、12 skipped、318 subtests passed**，509.83秒，退出0。
  359项既有rdflib／fork弃用告警保留；受测源码摘要与最终文件一致。Python Ruff F类、
  文档链接及git diff --check通过。真实语义及降耗不由工程检查替代。
- 保留C组原件的旧／新投影对照：handoff 62条，排除0→36；dispatch 52条，排除0→42；
  wire 830条，排除800→800。增加排除的是已知成功交接，原事件不改写；此计数不是
  实际唤醒／turn减少或token节省比例。

命令在backend目录执行，真实固定DSH／bwrap使用现有本地HTTP/SSE fixture，
没有请求外部模型或写入平台模型，不消耗建模轮次：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_delivery_token_reduction.py \
  ../modeling_team/tests/test_delivery_wakeups.py \
  ../modeling_team/tests/test_delivery_ops.py \
  ../modeling_team/tests/test_delivery_decision_input.py -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short \
  --junitxml=../workspaces/dsh-c-retro-fixes-20261018/full.xml
```

原件位于gitignored `workspaces/dsh-c-retro-fixes-20261018/`：full.log／full.xml、
tested-source-sha256.json及retained-projection.json。只保存计数与来源，不复制隐藏内容。
本轮是工程纠正；实际自主读取／参数采用、压力压缩、同条件净token、Host转移和费用仍待
后续获准验证，原C组四题非盲结果及旧组失败不改写。
