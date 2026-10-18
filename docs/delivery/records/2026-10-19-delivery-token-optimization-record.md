# Delivery token 优化：首批修复与三任务验证

用户授权按上一轮建议修改，再由Codex执行建模、复盘并继续迭代。总计最多3个建模任务，
每任务最多3轮建模机会；生产、Delivery、CQ、独立Consumer／Judge及外层Codex Host
固定`glm-5.3-flash / low`。本次复用R4.3-026最小安装链原完整范围，不降低评分或分母。

## 首批范围与实现

归属R4.3-019／022／029／030，依据
[前轮输入复盘](../modeling-retrospectives/2026-10-18-codex-flashx-low-retrospective.md)。

- 同一provider wait按wait_id／epoch识别。首次错误及Host恢复待办保持，同一状态不反复
  发起必然被冻结Profile拒绝的升级；wait清除／新epoch后重新处理。未新增CQ通信权限、
  次数硬门或自动重启；原正式issue与Host恢复路径保留。
- CQ可恢复码`cq_waiting_provider`补入既有注册表。已批准slice通知因同一provider wait
  被拒时不每drain重发，wait清除／变化后继续；普通错误仍可重试，不永久关闭run。
- 增量输入省略未变化task_context及run identity，实际变化、授权、未知写入和必要当前
  状态仍提供；bootstrap／恢复重新给完整上下文。原journal和分页确认不改写。
- coverage六个索引共享顶层精确evidence引用，使用`evidence_ref="evidence"`指向它；
  覆盖计数和省略说明保留。Delivery实际加载skill同步说明，不新增引用服务。

首批不启用030 F3短线程／F4机械动作，不恢复暂缓021。是否继续改动由每组真实证据决定，
不能用缓存率提高或离线体积减少代替净降耗，也不能把Host补位转移成本藏掉。

## 工程检查

新回归先在原实现确认失败，再实施修复：重复升级／CQ等待恢复、稳定上下文省略及
共享引用读取均覆盖。Delivery四文件定向192 passed；Runner provider／CQ定向分别
49、15、68、81 passed（各组有重叠，不相加），后者8 subtests passed。
另一会话只读复核Delivery diff及恢复／unknown边界，没有严重阻塞；不称语义验收。

Team全量：**3353 passed、12 skipped、318 subtests passed**，514.75秒，退出0；359项
既有弃用告警保留。测试前后源码摘要一致。原日志／JUnit及源码摘要在gitignored
`workspaces/token-optimization-20261019/`。GitNexus未索引两个修改入口，impact UNKNOWN；
调用点及定向回归用于当前影响核对。staged detect_changes为low，但主要运行入口覆盖
仍缺，不能声称图分析完整。只有modeling_team／skill改动，不需产品服务重启。

## 实验授权与执行责任

全局台账为`workspaces/token-optimization-20261019/authorization.json`，3任务各自核算
初建及验收后实质修模轮次，fresh semantic-start单列。成功不强行耗尽3轮；每组成功／
机会耗尽后关闭自己的operation／run／临时凭据，保留模型／冻结池／原证据。

独立Codex Host负责真实启动、监督、私有CQ审核、交接、收尾及只读复盘；外层主Agent
负责代码修复、监督和证据核对。隔离生产Team仍决定语义，独立Consumer／Judge只读验收，
Host复盘不代替最终裁决。全景审核与整池审核分开，不将隐藏问题反向送入生产修模。

每组采集所有实际线程的input／cached／uncached／output、压缩子集、响应数、Host
补位与自身用量、错误／读取及墙钟。缺原件保持unknown；缓存与推理不重复加总。
旧FlashX只作参考，后续三组使用相同Flash low配置；真实语义、L0、降耗和费用分别结论。
本记录先记工程与授权，实际每组run、模型身份、质量、token和优化决定随结果补记。
