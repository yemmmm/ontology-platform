# 2026-10-20 建模终态反馈与协作成本窄修

用户要求本轮建模完成后复盘Delivery token优化是否生效，并实施新识别优化。
真实最小链公开1/1、隐藏3/3独立非盲验收通过，授权3轮用2轮；
[复盘及数值边界](../modeling-retrospectives/2026-10-20-dsh-glm-low-retrospective.md)保留r1失败、r2成功及Host成本。
本次工程归属022／029／030／031／032及原OPT-20261019-DSH-01／05，不新建编排或计数硬门。

## 原因与最小变更

1. DSH终态守卫原来对正常排队、unknown及在途投递统一输出“unknown dispatches require Host reconciliation”。
   本轮真实消息仍排队，Delivery及Coordinator误判为平台／未知投递，反复转述并走Host issue。
   保留同一阻断条件，反馈只根据真实queued／unknown／in_flight计数给出对应下一步；仅真实unknown要求Host对账。
2. Broker原来将此拒绝记为broker_rejection，ack固定not_applicable被读作工具不适用。
   增加runtime_input_pending窄类别，贯通Broker→Runner既有白名单落盘→Delivery投影的agent_id，
   不携带候选、隐藏业务或原始终态正文。accepted、missing handoff及其他拒绝保持原义。
3. 重复issue pause原来不返回实际state，已resolved被角色误解为仍paused。
   仅补当前受控state，原状态机、epoch及CAS不变；沿现有允许错误通道按ISSUE_STATES白名单重建，
   Codex及DSH均可读取，不反射任意socket正文。
4. `c54ff35`已在fresh r2前持久化Modeling字段和相同错误请求纠正提示；后续补窄为字段/schema拒绝，
   正常cq_freeze_pending在依赖清除后仍可原样接续。Delivery实际instructions／skill说明ack含义、
   当前回执优先及避免旧pause／终态催办；宿主skill补充本身上下文成本和增量观察方法。

T0结论：真实未消费／未知输入、授权及写入完整性保护有必要。本次准确反馈使Agent自修复，
没有删除守卫、伪造消费、放宽模型语义、重放apply或改变独立裁决。上游HTTP500保留至供应商边界，
没有通过换模型／代码假装修复；Consumer误标签由原独立Judge纠正，不加平台语义硬门。

## 验证

- 第一组新增回归在原码确认5 failed／16 passed；修复后21 passed。
- 继续沿真实Broker→Runner→Delivery边界检查，新增两反例先2 failed／7 passed，补齐落盘和角色投影后22 passed。
- 最终相关**560 passed、2 skipped、7 subtests passed，147.90秒，退出0**。
  包括DSH真实本机隔离工程fixture（本地假provider、无外部模型）、原生输入、Transport、issue诊断／
  升级／同线程恢复、最小链挂载、全部Delivery测试及Host工具。两跳过项是未设置
  MODELING_TEAM_DELIVERY_LIVE_CODEX_BOUNDARY的真实Codex边界探测，不计PASS。
- 新用例验证排队与unknown分流、在途回执等待、消费后可正常终态、blocked报告仍可交接；
  新类别真实落盘及投影保持角色；重复pause在waiting_repair和resolved下返回真实状态且不改变账本，
  非法state仍不能通过原错误转发器。另直接核对Codex原错误转发器可保留三个合法state且拒绝bogus。
- 修改Python的Ruff通过，除Runner原7项既有F401/F811/F841；HEAD与当前JSON诊断逐项相同、无新增。
  两个修改skill的quick_validate通过，相关Markdown链接和git diff格式通过。

最终命令在backend目录执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_dsh_events.py ../modeling_team/tests/test_dsh_runtime.py ../modeling_team/tests/test_dsh_contracts.py ../modeling_team/tests/test_transport.py ../modeling_team/tests/test_r30016_issue_control_diagnostics.py ../modeling_team/tests/test_r23005_issue_escalation.py ../modeling_team/tests/test_r23009_self_reported_issue_resume.py ../modeling_team/tests/test_r4326_minimal_chain.py ../modeling_team/tests/test_delivery*.py ../modeling_team/tests/test_dsh_delivery.py ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_host_ops_mcp.py -q --tb=short
```

私有日志为`workspaces/minimal-chain-20261020-dsh-glm-low/optimization-final-tests.log`及红灯／lint对照原件。
GitNexus对两个守卫/类别入口及新增落盘/投影入口返回UNKNOWN；issue control索引LOW但无调用者，
实际采用源码调用点和贯通回归，不能称图分析覆盖完整。提交前detect_changes返回LOW，
16文件、5个索引符号、0条执行流；未覆盖上述新入口，不把0流解释为无影响证明。

只修改modeling_team、提示及skill，没有backend/frontend变更或产品服务重启。
当前已验收DSH进程和冻结提示没有热迁移；工程通过不等于真实Agent已采用或净降耗通过。
未用的1轮没有用于追加基准测试。F4未实施、021暂停、030整体及净费用边界保持。
