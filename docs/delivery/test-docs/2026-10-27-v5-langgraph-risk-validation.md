# v5 LangGraph 两项风险验证

## 范围与判定

2026-10-27 用户要求设计测试并调用子 Agent，验证并行协作与写入恢复两项风险。承接
[选型评估](../../research/2026-10-27-v5-modeling-team-orchestration-options.md) 的 V1、V2 及
V3 中紧邻恢复窗口的部分，关联 R5.0-001 F3、R5.0-003 F5、R5.0-004 F3。

本轮使用真实 LangGraph、磁盘 SQLite checkpointer、确定性 Agent 替身和隔离的应用账本。
不调用付费模型，不运行生产 Team，不改后端／前端依赖及服务。结论只能证明编排机制；
模型语义判断、真实平台 application、PostgreSQL checkpointer、多机调度与费用收益未验证。

测试源码放在 `scripts/v5_langgraph_risks/`；依赖、数据库和原始事件证据放在 gitignored
`workspaces/v5-langgraph-risk-validation/`。测试产生的业务内容是测试夹具，不是生产定义。

## 执行前测试设计

| 编号 | 测试 | 可观察判据 |
| --- | --- | --- |
| P1 | 同一图动态分派多个 Agent 节点 | 同步屏障证明任务执行区间重叠，至少两个已开始才允许任一个结束；不能只用总耗时推断并行。 |
| P2 | 同一父图中 A 等澄清，B 有独立后续步骤 | 保留中断前后事件与 checkpoint；实测 B 后续步骤是否被 superstep 挡住。作为限制对照，不预先把行为算作能力通过。 |
| P3 | 独立工作单元运行，A 等待时 B 跨步骤完成 | 分离 thread 身份，A 仍有未解决 interrupt 时 B 已完成；用磁盘状态重建图后只恢复 A。 |
| P4 | 工作单元之间真正交换成果并重入 | 生产方发布的带身份结果由另一单元读取并影响输出；共享问题／回答有范围，保留请求、读取、答复及再次推进的记录。不能只有平行输出后拼接。 |
| R1 | 朴素写入后、节点返回前强制退出 | 外部账本已提交、graph 仍待执行该节点；新进程恢复导致重复效果，负对照准确暴露风险。 |
| R2 | 原操作身份＋效果对账，同一崩溃窗口恢复 | 保留原操作身份与真实回执，重启后读取已提交效果；节点可以重执行，业务效果仍只有一次。 |
| R3 | 超时后效果未知／明确未写入 | 已提交则读回；确认未写入才以原身份安全执行；无法确认时保留未知，不盲目新建身份。 |
| R4 | 已完成流程重复接续 | 完成 checkpoint 已持久化后再恢复，效果数量保持不变。 |

超时仅为防止测试挂起；并行、等待和故障窗口通过事件／屏障控制，不靠短暂 sleep 猜测。
崩溃测试必须有不同进程 PID、退出码、磁盘账本和 checkpoint 证据。测试不得访问现有
业务数据库或清理其他任务资源。每次使用独立证据目录。

## 职责与独立性

- 并行实验子 Agent：仅负责并行测试脚本及其开发验证。
- 恢复实验子 Agent：仅负责恢复测试脚本及其开发验证。
- 主 Agent：隔离依赖、测试范围、结果整合及需求／选型记录同步。
- 独立测试子 Agent：审查判据与代码，另开证据目录复跑，检查负对照和原始记录；只编辑本文记录测试轮次，不修复实验实现。

独立机制测试通过不等于独立业务语义验收通过。

## 执行记录

### 执行前独立审查

独立测试侧读取 AGENTS、对应 v5 条款和实现草稿后提出以下证据缺口。这里是静态审查，
不冒称故障复现；后续修正不覆盖这份初始记录。

| 编号 | 草稿缺口 | 处理状态 |
| --- | --- | --- |
| T1 | P3 在同一图／Saver 上恢复，未覆盖磁盘重建；B 完成时未重新证明 A 仍有 interrupt。 | 第 1 轮 P3 已修正并复核。 |
| T2 | P4 读取了 payload，但 B 恒定返回 accepted；A 的范围由驱动器硬编码，缺少真实消费影响。 | 第 1 轮 P4 已修正；两种 payload 导致接受／拒绝，A 使用 B 的实际磁盘结果。 |
| T3 | P2 的初始阻塞谓词只查看事件前缀，不能直接证明首次 invoke 返回前无 follow_step。 | 第 1 轮已保存并检查首次 invoke 结束时的事件快照。 |
| T4 | 恢复草稿使用新输入 invoke，而非恢复原 pending 节点；operation_id 来自 CLI 闭包，没有在前置 checkpoint 中保存。 | 第 1 轮未计通过；第 2 轮以 None 恢复、节点从 state 取原 ID，已修正并独立复核。 |
| T5 | R3 草稿仅调用应用账本分支，未发生图节点 TimeoutError。 | 第 2 轮补真实节点 TimeoutError 并检查后续对账分流；超时图完整接续仍未测。 |
| T6 | 第 1 轮将实际重叠、局部等待和交换分开验证，尚未在同一协作场景证明并发。 | 第 2 轮 P4 采用两线程并发 invoke、屏障／事件及同场景交接，已补足。 |

### 第 1 轮：并行／协作独立复跑（2026-10-27 17:58—18:00，UTC+8）

- 基线提交：`811f38ac1495bdc2390aeddbbf53e64a7bfb3a0b`，新增实验脚本尚未提交。
- 当前输入 SHA-256：`parallel_probe.py` 为 `1890c82a55e916a22f60eb02b5ca8df25954aab7fd305aab0f754ea85572ae99`；
  `test_parallel_probe.py` 为 `d2034e8f40b6d8b466be0b28f1ef666df583d5da41993075d79b35f017c47d9a`。
  完整清单保存在 `workspaces/v5-langgraph-risk-validation/independent-round1/source-sha256.txt`。
- 环境实际读取：Python 3.12.3、LangGraph 1.2.18、langgraph-checkpoint 4.3.1、
  langgraph-checkpoint-sqlite 3.1.2、pytest 9.1.1；45 包冻结清单见实验 `requirements.txt`。
- 未修改实验实现，仅独立复跑并检查 JSON、磁盘 checkpoint 和工作空间账本。

实际命令：

```bash
workspaces/v5-langgraph-risk-validation/.venv/bin/python scripts/v5_langgraph_risks/parallel_probe.py --output-dir workspaces/v5-langgraph-risk-validation/independent-round1/parallel
workspaces/v5-langgraph-risk-validation/.venv/bin/python -m pytest scripts/v5_langgraph_risks/test_parallel_probe.py -q --basetemp=workspaces/v5-langgraph-risk-validation/independent-round1/parallel-pytest --junitxml=workspaces/v5-langgraph-risk-validation/independent-round1/parallel-pytest.xml
```

| 用例 | 结果 | 独立核对 |
| --- | --- | --- |
| P1 | PASS | 两个 Send 任务均先进入 started，再出现任一个 ended；屏障通过。 |
| P2 | PASS（限制对照成立） | 首次 invoke 有 interrupt；B first_step 已运行且全程只运行一次，follow_step 在首次返回前缺席，恢复 A 后才发生。等待任务在磁盘快照中存在。 |
| P3 | PASS | 关闭／重开 Saver 并重新 compile；B 已完成两个节点且 next 为空时，A 的 snapshot 与原等待状态完全相同并仍有 interrupt；随后只恢复 A。磁盘中 A／B 分别有 4／5 个 checkpoint。 |
| P4 | PASS | 从磁盘核对 A 发布内容→B 读取→B 带 fact_id／revision／scope 的决定→A 收到完全相同决定；installation 输入走 finalized，repair 输入走 rejected。 |
| R1—R4 | BLOCKED（本轮未执行） | 等待 T4／T5 修正后的恢复脚本，不把草稿计为通过。 |

自动断言 **4 passed，0 failed（0.47 秒）**；独立原始证据核对通过。
证据目录为 `workspaces/v5-langgraph-risk-validation/independent-round1/`，包含 CLI／pytest
日志、JUnit、四项 JSON、SQLite 文件和 `parallel-evidence-audit.json`。本轮并行机制范围
结论 **PASS**，两项风险的总体结论仍等待恢复组。

该结论支持 LangGraph 原生并行节点，以及应用明确划分 thread 后的局部等待与交接。
共享工作空间、独立单元的驱动和答复归属由实验应用代码提供；P3 的驱动是顺次 invoke
不同 thread，P1 单独证明原生节点实际重叠。未验证多机调度、真实模型自主协商或业务语义。

### 第 2 轮：并发协作增强与恢复独立验证（2026-10-27 18:02—18:04，UTC+8）

本轮复测修正后的 P4，并回归 P1—P3；首次独立执行修正后的 R1—R4。第 1 轮记录保持，
本轮 P4 结论替代“拆开验证并行与交接”的证据范围。基线提交及运行环境同第 1 轮。
执行前哈希保存于 `independent-round2/source-sha256.txt`；主 Agent 在执行期间仅统一了
并行两文件的 100 列格式，复用语义不变的结果。最终文件 SHA-256 独立重读如下：

| 文件（相对 `scripts/v5_langgraph_risks/`） | SHA-256 |
| --- | --- |
| `parallel_probe.py` | `7c105d080cc68fc1b8a9b631dab435a9670fe4b9ad0468e1d310934a0a28edde` |
| `test_parallel_probe.py` | `11a154b58dbb25bb1c1d14fa968aafe97a6b9b8afd371a4953e2e946c27fdfaa` |
| `recovery_probe.py` | `7a6bcd510946f55f47ba811782542a7afd1a51c330eeb797e4edbbcf63976df2` |
| `test_recovery_probe.py` | `18497a5f4a36e3b03cdce005c1b83723f82e3cc5ae5f9ebc501330d506f0af6a` |
| `requirements.txt` | `ac568463645aec72a787f7a5f42bf5c7238773f04fff09ecc6005fa89e4bd780` |

实际命令：

```bash
workspaces/v5-langgraph-risk-validation/.venv/bin/python scripts/v5_langgraph_risks/parallel_probe.py --output-dir workspaces/v5-langgraph-risk-validation/independent-round2/parallel
workspaces/v5-langgraph-risk-validation/.venv/bin/python scripts/v5_langgraph_risks/recovery_probe.py run --output-dir workspaces/v5-langgraph-risk-validation/independent-round2/recovery
workspaces/v5-langgraph-risk-validation/.venv/bin/python -m pytest scripts/v5_langgraph_risks/test_parallel_probe.py scripts/v5_langgraph_risks/test_recovery_probe.py -q --basetemp=workspaces/v5-langgraph-risk-validation/independent-round2/pytest --junitxml=workspaces/v5-langgraph-risk-validation/independent-round2/pytest.xml
```

两条 CLI 均退出 0；自动断言 **9 passed，0 failed（6.97 秒）**。独立测试侧另从事件、
SQLite 和 checkpoint 核对以下事实，结果保存在
`workspaces/v5-langgraph-risk-validation/independent-round2/independent-evidence-audit.json`。

最终 100 列格式化后，按主 Agent 要求定向复测 P4：

```bash
workspaces/v5-langgraph-risk-validation/.venv/bin/python -m pytest scripts/v5_langgraph_risks/test_parallel_probe.py -q -k p4 --basetemp=workspaces/v5-langgraph-risk-validation/independent-round2/final-format-p4 --junitxml=workspaces/v5-langgraph-risk-validation/independent-round2/final-format-p4.xml
```

结果 **1 passed，3 deselected**；这是同一 P4 的定向复测，不增加独立用例数。
最终哈希另存 `independent-round2/final-source-sha256.txt`；R 组输入保持不变，复用已通过结果。

| 用例 | 本轮结果 | 独立证据 |
| --- | --- | --- |
| P1 | PASS（回归） | 真实 Send 扇出、两个 started 早于任一个 ended。 |
| P2 | PASS（限制对照回归） | 单图 interrupt 时 B 的后续节点待恢复后执行，未把这一限制记为独立等待能力。 |
| P3 | PASS（回归） | 磁盘重建后 B 完成、A 等待状态不变，再恢复 A。 |
| P4 | FIXED／PASS | 两个线程同时调用独立 thread_id，两个初次 graph 调用区间实际重叠；A 发布、B 消费并形成带引用决定，A 的 interrupt 持久化后 B 跨步完成，B 返回后才恢复 A。两场景中 A 的等待快照保持，消费结果分别导致 finalized／rejected。 |
| R1 | PASS（重复效果负对照成立） | PID 1298134 在账本提交后被 SIGKILL（-9）；checkpoint 仍 next=effect、无 applied 状态，已有原操作 ID；新 PID 1298240 恢复节点，最终两条同 ID 效果，inserted 为 true／true。 |
| R2 | FIXED／PASS | PID 1298297 在相同窗口被 SIGKILL（-9），PID 1298327 以 None 恢复；节点两次进入且 ID 未变，应用幂等处理后仍一条效果，inserted 为 true／false，最终 next 为空。 |
| R3 | FIXED／PASS（限定范围） | 两个真实节点分别在提交后／未确认效果时抛 TimeoutError，子进程退出 1，均留下 pending effect；对账分别读回一条效果／保留未知且不写。可信“确认未写入”夹具沿原 ID 应用一次。未恢复这两个超时图到完成。 |
| R4 | PASS | 两个独立进程完成／再接续；graph 返回两次，effect 节点只进入一次，账本同一条效果保持不变。 |

证据总目录：`workspaces/v5-langgraph-risk-validation/independent-round2/`，包含两个 CLI
日志、完整 pytest 日志／JUnit、时间线、各场景 SQLite、提交窗口、进程退出码及独立核对。
当前无待修的本轮机制缺陷，**两项核心风险的有界工程验证 PASS**。

## 最终结论与未验证边界

LangGraph 原生具备动态并行节点和持久中断／恢复。同一 graph/thread 的 superstep 会让
等待影响兄弟分支后续推进；独立 thread_id 配合应用的并发驱动和共享成果交接，可以在
同一场景中让 A 等待时 B 继续，并让 B 的实际结果影响 A 的后续行动。

外部应用与 checkpoint 没有自动成为同一事务。进程被杀后节点会重执行；本轮由应用账本
按原操作 ID 幂等处理才将效果保持一次。这不等于外部调用只发生一次，更不等于框架原生
保证 exactly-once。真实平台应用需复用自身提交身份、实际回执及对账合同。

本轮尚未验证真实 LLM 工具调用／自主协商／语义质量、OntoWeave 实际 application 与
治理读取、PostgreSQL checkpointer、多人对同一问题的自动归并及权限范围、超时图完整
恢复、多机调度、费用收益及完整 v5。R5.0-001／003／004 和选型 V1／V3 均不能整体关闭；
这里只确认它们对应的核心机制与上述局部证据。确定性业务内容均为测试夹具。

## 主 Agent 交付检查

最终四份 Python 源码哈希与独立审计一致；Ruff 检查和 100 列格式检查通过，隔离环境
45 个依赖兼容。四份相关 Markdown 的 37 个本地链接、9 个锚点及 git diff 检查通过。

GitNexus 对本次 9 个暂存文件运行了 `detect_changes(scope="staged")`，未映射出符号。
其索引落后当前基线 513 个提交且不包含新增实验，因此不把该输出当作图影响覆盖；
本次以源码、调用点、明确文件范围及独立运行证据核对。变更仅涉及隔离实验与文档，
没有后端／前端或生产运行配置变更，无需重启应用服务。
