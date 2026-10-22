# Delivery 事件排队与输入增长修复（134133）

用户在[本轮复盘](../modeling-retrospectives/2026-10-22-codex-glm-low-134133-retrospective.md)后要求“请修复上述问题”。本次沿 R4.3-030 F1/F2/F3、R4.3-022、R4.3-029及原 OPT-20261019-DSH-03／05修复已定位的运行实现与提示合同；不扩大业务、模型或验收范围。

## 已实现的修复

1. **及时接收工具与完成事件。** 原生 `poll` 每次有界消费最多256条已就绪事件，只有首次读取可等待。文本通知不再每条都等待下一次同步观察，事件顺序及用户控制机会保留；不新增后台线程或调度框架。
2. **避免反复全量解析 journal。** 在原文件锁下维护进程内增量游标，仅保留 Host 请求／结果及其原始字节引用；后续只解析追加的完整行。替换、截短、同大小改写会重建，半行重试、损坏记录仍报告，外部 Host 进程写入的结果可见。原始 journal 及原读取接口保留。游标依赖既有 append-only 合同，不另建持久索引。
3. **去除 journal 中的重复队列快照。** `session.json` 继续保存完整待投递队列，journal 保留实际 decision／dispatch 事件，普通状态快照不再反复附带整份 `delivery_inputs`。恢复测试核对重建队列一致，不删除或改写旧证据。
4. **阶段提示和当前决策前置。** 当前 `core` 位于普通周期活动之前，阶段切换提示位于 `core` 首部。模型侧普通活动按 run 汇总计数，显式索引指向保留 packet 中的完整分组；当前角色卡、重试结果、未决身份及 coverage 继续提供，原包全文保留。Delivery 角色包与 Skill 同步要求按具体缺口补读活动，避免为重复等待或已就绪的切换扩读旧活动。
5. **纠正原生 JSON 错误的归属。** Modeling 权威角色指令要求先修复本地序列化并使用已发布的 prepared request 引用；解析前失败本身不升级平台恢复 issue。语义正文保持，先前未知写入继续先对账；合法请求或材料通道实际失败仍可升级。

没有删除授权、写入原子性、未知结果对账、源忠实度、实际治理读回或独立语义验收。程序不代替 Agent 作业务判断，也不以流程错误永久终止 run。

## 验证证据

新增专项文件 `modeling_team/tests/test_delivery_134133_regressions.py` 共11项：通知突发与完成接收、有界让出、真实本地子进程管道、仅解析新增行、精确结果引用与调用方隔离、损坏／半行、截短／替换、跨进程 Host 回执、同大小改写、队列恢复、核心前置及完整原件可读。用例先复现原缺陷后修复；原生管道使用本地 fixture，不连接模型。

从 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest`：

| 范围与时点 | 结果 |
| --- | --- |
| `../modeling_team/tests/test_delivery*.py`、`test_r4329_independent.py`、`test_host_wait.py`，覆盖全部生产实现修改 | 447 passed、2 skipped，41.58秒 |
| 专项、`test_dsh_delivery.py`、`test_r44002_budget_integration.py`、`test_contracts.py`、`test_unified_modeling_baseline.py`、`test_r4326_minimal_chain.py`，覆盖角色提示及配置装载 | 86 passed、3 subtests passed，31.57秒 |
| 最终专项与 `test_delivery_runtime.py`，补齐跨进程／同大小改写及管道 fixture 后 | 26 passed、2 skipped，1.02秒 |

范围重叠，不将以上数量相加。跳过项是需显式启用的真实 Codex 边界；未调用收费 Provider。最终 Ruff、`git diff --check`、Delivery Skill 格式和相关本地链接检查通过。GitNexus 未找到所改方法，采用直接调用点、diff及相关回归检查，不声称图谱影响覆盖。

### 保留原包离线回放

输入来自原 `minimal-chain-20261022-codex-glm-low-3cny-134133` 冻结 decision-view 引用的精确 packet。临时目录装载新代码并对照原活动计数、重试结果、覆盖缺口及阶段身份，无平台／模型调用，核对原 view 未改写。机器结果保存在 `workspaces/delivery-input-repair-20261022/offline-replay.json`。

| 原输入 | 原字节数 → 新字节数 | core 起始偏移 | 阶段提示起始偏移 |
| --- | --- | --- | --- |
| production | 56,706 → 37,189 | 32,151 → 110 | 34,072 → 118 |
| acceptance | 97,118 → 71,462 | 35,890 → 112 | 该包无此提示 |

约296.7MB的原 journal 只读投影首次读取1.645秒，随后五次读取中位数0.000105秒；3条请求／3条结果，`history_complete=true`。这是单机离线观察，说明重复全扫已被消除，不代表真实工具延迟或墙钟承诺。

## 生效与未验证边界

新建 Delivery 进程加载上述实现与角色提示；原运行未热替换、恢复或重新启动。改动不涉及 backend/frontend，无需应用服务重启。没有新增预算、semantic start、修模或收费模型调用。

本次工程修复及离线检查通过，**真实 token 降幅、全任务净效果、模型实际采用及自主最终收口仍待获准运行验证**。R4.3-030／022及原03整体保留 PARTIAL／待调整，原10M未达及原非盲有界语义结果不改写；字节减少和机械测试不代替独立语义验收。
