# R4.3-027 实现与工程验证记录

范围：[权威需求](../../requirements/requirements-v4.3.md#r4-3-027)、
[设计](../designs/2026-10-16-r4-3-027-parallel-cq-design.md)。用户授权设计和实现；
本次未启动、恢复或修复真实建模，不新增建模轮次，不改历史运行证据。

## 实现

`modeling_team/__main__.py`在现有CQ验收及checkpoint验收重执行路径内，每题建立独立
Consumer会话，同批最多三题，完成后即接续。所有题绑定同一冻结／实际观察模型／权限，
逐题解析本会话回执，再按冻结顺序归并；Judge仍走原只读证据重验、资料引用、响应去重
及体积分组。单题失败不重做整池，失败、未执行及完整分母继续保留，报告发布不覆盖。

每题进度写到本attempt的`question-tasks/NNNN.json`，最终报告提供
`sessions.platform_examiner.tasks`和`sessions.timing`，记录实际起止、重叠区间、摘要、
首阻塞、清理和原生用量。原生指标可能把未提供的子字段归零，`usage_gap`明确标注
这不是已对账账单、缺字段不代表真实零用量；本次没有调用外部模型或取得实际成本对照。

原EvaluationOwner支持在途成员集合、逐成员暂停／继续确认、启动期间控制及停止。
原生控制派发不持有owner锁等待异步确认；stdout确认在agent IO锁外处理。
已完成成员在其他题工作时仍可确认；原工作线程保留至owner最终清理，避免
`bwrap --die-with-parent`随启动线程退出杀死保留Consumer。沿既有入口继续只读追问，
报告保持固定；生命周期不新增服务或生产恢复机制。

## 验证与证据边界

- 新测试先在旧实现失败：Consumer收到整批题目，无法三题独立并发。
- 工程测试以同步屏障证明三任务真实重叠、慢题未结束时空位接续，覆盖五题、两题、
  乱序、单题失败和重复`p0`的会话隔离；多成员控制覆盖异步确认和晚启动成员。
- 原生CLI测试复用受控App Server、真实bwrap子进程、AF_UNIX sink/proxy及canonical
  MCP forwarder；外部模型与业务数据库由既有fixture替代。五题运行能核对五个不同Thread、
  峰值三题、完整五题裁决、原生指标及最终清理。另覆盖暂停、同Thread恢复、固定报告
  只读追问、进程故障隔离、漂移和越权合同。
- 回归中发现并修复真实控制互锁与父线程生命周期问题；旧测试的整批会话数、单题失败
  传播和共享回执路径已按新合同更新。清理依据本owner资源证据，不扫描其他在途运行。
- GitNexus对`_cq_execute_batch`影响分析为LOW，直接调用者为CQ验收入口，间接包含
  checkpoint验收续跑。EvaluationOwner在索引中未命中，该部分以实际调用点及回归覆盖，
  不声称图索引覆盖。没有修改后端、前端或共享服务配置，无需服务重启。

工程验证结论：**PASS（全量范围及失败项修复后的组合证据）**；未另行开展独立功能验收。

- 全量命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short`。
  首轮3057 passed／6 failed／12 skipped，定位为串行夹具断言及用量缺口期望，修正后保留原日志。
  第二轮3062 passed／1 failed／12 skipped、318 subtests passed（366.01秒）；唯一失败为
  角色提示标题漏掉仍适用的`R3.0-011`版本标记。
- 补回版本标记后，`test_r3011_acceptance.py`整文件37 passed；全量失败项复验
  `uv run pytest ../modeling_team/tests --lf -q --tb=short`为1 passed／661 deselected。没有执行逻辑变更，按文档／
  提示合同检查复用其余全量结果，**不声称存在单次全量全绿结果**。
- 当前原生CLI、并发、控制和standby专项49 passed（27.68秒），包括五题原生并发样本。
  原平台响应／Judge部分裁决等专项中，除最后的标题标记检查之外的执行结果均通过；
  checkpoint及运行证据夹具已在第二轮全量通过。
- 当前生产改动与新增测试的Ruff F类检查、`git diff --check`、本地文档链接及
  `modeling-dev-loop`的`quick_validate.py`检查通过。
- GitNexus staged变更检测为low，但索引包含旧行号和缺失新成员；以上结论以当前diff、
  实际调用点和运行测试为准，不将0个受影响流程视为全覆盖证明。

日志留存于本机`/tmp/r4327-team-tests.log`、`/tmp/r4327-team-final.log`、
`/tmp/r4327-final-native.log`；可按上述命令复现。本次仅覆盖工程实现，独立业务语义及
真实成本／效率仍未验证。

受控五题原生CLI样本（相对Consumer阶段起点，秒；fixture模型输出，不是外部模型计费）：

| 题目 | 开始 | 结束 |
| --- | ---: | ---: |
| cq-9 | 0.0015 | 0.7432 |
| cq-7 | 0.0029 | 0.7298 |
| cq-extra-3 | 0.0043 | 0.7176 |
| cq-extra-4 | 0.7194 | 1.5197 |
| cq-extra-5 | 0.7311 | 1.5254 |

该样本前三题重叠区间为0.0043—0.7176，第四题在首个空位接续；Consumer阶段墙钟1.526秒，
批次墙钟2.378秒。每个fixture Consumer报告100 input／20 output tokens；total字段缺失，
成本未对账。这些值只证明工程并发与记录可用，没有同范围真实串行基线，不计算提速倍数。

| 验收项 | 本次证据及结论 |
| --- | --- |
| A1 | 工程任务／受控原生子进程三题重叠、上限与接续可验证；真实模型并发效果待证 |
| A2 | 沿原冻结、权限、盲测、回执、独立Judge及漂移合同验证；不改变生产访问范围 |
| A3 | 工程覆盖乱序、首阻塞、部分裁决、未执行和不可覆盖发布；完整分母不变 |
| A4 | 记录每题／批次墙钟及原生指标／缺口；真实业务独立语义、串并行成本与提速均未验证 |

本次工程通过不构成真实L1语义PASS或效率收益证明，也不追认既有运行的失败或授权越界。
