# 2026-10-20 Delivery指导请求身份与阶段交接修复

用户在[10M复盘](../modeling-retrospectives/2026-10-19-minimal-chain-10m-delivery-retrospective.md)
后要求修复。基线`f274943`，归属R4.3-030 F3／022／032及OPT-20261019-DSH-03。
本次只修复导致新指导请求无法对账、阶段交接无法采用的窄缺陷，不实现F4或启动新模型。

## 修改及边界

- Delivery调用submit_instruction省略request_id或显式传null时，复用原standby／
  acceptance机制，在调用Host提交前生成身份；同session／native call及原参数跨恢复
  保持相同ID，显式ID不覆盖。原FIFO账本和Runner回执负责幂等，不新增重放机制。
- 原始Host工具的可选参数合同保持。Delivery使用实际返回的request_id及receipt_tracking，
  供程序投影、冻结通知和阶段交接绑定；不要求Agent补造ID或再轮询同一成功回执。
- 历史缺身份行保留uncorrelated及原件位置，新增可恢复的request_identity_missing
  反馈，说明检查原admission／delivery／consumption，不为取得ID重发不确定动作。
  该项影响边界时，提示改为status=deferred、准确blocker及原件范围，不再提供
  thread_boundary催Agent反复申请。原run可以继续当前线程，原有效决定和交接意图保留。
- 未将历史缺身份记录自动追认为已消费，也不改写原账本。真实回执、用户控制、
  unknown write、待送输入及空闲门保持；原成功／失败模型、冻结和报告不变化。
- 实际Delivery instructions与skill、MCP参考文档同步说明缺省身份及deferred提示。

按T0，未知提交／写入和控制保护有必要；本次修正的是合法可选参数制造无法关联请求的
实现缺口，并将不可操作的重复候选降为可定位反馈。没有新增次数／token硬门或恢复平台。
历史null-ID尚不能仅凭账本证明实际消费；本次没有为旧任务执行对账写入或热迁移。

## 影响与验证

调用面为Delivery原生工具callback→call_tool→Host submit_instruction→既有FIFO／
请求账本→Runner实际回执→request投影→phase hint／yield／原阶段切换。Codex与DSH
均提供稳定原生call identity，修改共用Delivery层。GitNexus impact未收录
_call_tool_raw、_request_projection和maybe_switch_phase_thread，返回UNKNOWN；
使用源码和调用点检查，不声称图覆盖完整。
提交前detect_changes对10个暂存文件返回low，但changed_symbols为0，未覆盖实际修改
的Python符号；保留索引覆盖限制，不把该结果当完整影响证明，也不为本次窄修重建索引。

- 新增回归先**4 failed／1 passed**，分别复现缺省／null身份、生产阶段无法绑定通知、
  历史缺身份无可操作反馈。修复后通过，显式ID兼容保留。
- 使用真实临时FIFO验证恢复前后同原生调用、无回执时重投、收到实际回执后重投均不
  重写FIFO，只有一条Host提交账本；投影进入settled，真实通知身份使生产边界切换。
  切换本身使用既有PhaseRuntime测试替身，不调用模型。
- 阶段切换、决策输入和调优专项：**80 passed，4.96秒**。
- 最终相关回归：**520 passed、2 skipped、3 subtests passed，77.00秒，退出0**。
  覆盖全部Delivery测试、Host工具／MCP／S2、DSH Delivery／合同及Runner／性能输入
  合同；已有unknown receipt／write、忙状态、待送输入和恢复反例继续通过。
  两项跳过是未启用MODELING_TEAM_DELIVERY_LIVE_CODEX_BOUNDARY的真实Codex边界探测，
  本次没有把它们记为通过，也没有启动外部模型来补测。
- 修改Python的Ruff、Delivery skill validator通过；Markdown链接／格式及git diff检查通过。

最终相关命令：

```sh
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_delivery*.py ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_host_ops_mcp.py ../modeling_team/tests/test_host_ops_s2.py ../modeling_team/tests/test_dsh_delivery.py ../modeling_team/tests/test_dsh_contracts.py ../modeling_team/tests/test_contracts.py ../modeling_team/tests/test_r4023_runner_contracts.py ../modeling_team/tests/test_performance_input_contracts.py -q --tb=short
uv run ruff check ../modeling_team/delivery.py ../modeling_team/tests/test_delivery_request_identity.py
uv run python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py ../modeling_team/skills/delivery
```

测试日志保存在gitignored `workspaces/delivery-request-identity-20261019-repair/related-tests.log`。
未修改backend／frontend，无产品服务重启要求。工程通过证明新缺省身份和确定性交接
路径，不证明真实Agent已采用或完整任务≤10M；已运行的冻结提示／旧进程不会自动更新。
030／032整体仍部分验证，F4未实施、021暂停；真实降耗与原独立语义验收仍分开判断。
