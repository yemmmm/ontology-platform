# DSH 真实建模启动故障窄修复

本轮原授权：DSH、deepseek-flash、low，三次建模轮次，完成后关闭任务。
用户针对启动故障明确回复“同意”，授权修复两处缺陷、相关测试后继续原任务。
归属：[R4.3-031](../../requirements/requirements-v4.3.md#r4-3-031)。

## 证据与根因

Session `minimal-chain-20261018-dsh-low` 的 r1、r2 启动均未产生
`evidence/semantic-start.jsonl`，轮次实际消耗为0，剩余3。
两次原始 FAILED 状态、启动日志及清理证据保留在对应 gitignored run 目录。

- 非正式最小链的 carrier 保留历史正式 Coordinator capability descriptor，但
  Runner 只启动 Modeling／CQ 等适用 endpoint。DSH `_stage` 未按实际 formal contract
  区分，访问不存在的 Coordinator socket，抛出 FileNotFoundError。
- 部分角色尚未初始化时，Runner cleanup 查询整个 roster 的 provider wait；DSH
  直接索引不存在的 modeling agent，额外抛出 KeyError，阻断后续清理。

T0复核：第一处是错误装载历史角色能力，不是必要安全硬门。移除非正式 Coordinator
装载，保留实际 Modeling／CQ 的必要工具、权限和 schema 校验；不启动多余 endpoint。
第二处不存在实际等待者，返回无等待即可；保留已初始化角色的真实等待及恢复合同。
没有新增重试、计数硬门、角色、恢复框架或模型降级。只修改 DSH Adapter。

## 修复与验证

先补回归并观察失败：缺失 Coordinator socket 的 FileNotFoundError，以及未初始化
modeling 的 KeyError。再完成最小修复。测试使用本机固定 DSH／bubblewrap及离线
provider fixture，不请求外部模型。

在 backend 目录执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_dsh_runtime.py -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_dsh_events.py ../modeling_team/tests/test_dsh_delivery.py ../modeling_team/tests/test_dsh_acceptance.py -q
uv run ruff check ../modeling_team/runtimes/dsh.py ../modeling_team/tests/test_dsh_runtime.py
git diff --check
```

结果：**9 passed（65.69秒）＋33 passed（36.78秒）**，Ruff／diff检查通过。
覆盖实际隔离角色装载、工具表、暂停／继续、原session恢复、模型绑定、直接MCP透传、
部分启动失败后查询及重载，以及相关Delivery／验收路径。未重跑Team全量或产品测试；
本次无backend／frontend代码变更，无需重启产品服务。新Runner进程加载修复。
GitNexus impact未找到DshRuntimeAdapter，risk UNKNOWN；改用直接调用点与diff检查，
不宣称图覆盖。修复测试不代替真实启动、application或独立语义验收。
