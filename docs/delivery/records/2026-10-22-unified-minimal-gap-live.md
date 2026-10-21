# 通用建模方法与最小链：缺口修复及十五元真实运行

本次用户明确授权补齐通用方法用于最小链业务的 gap，并启动 Codex／glm-5.3-flash
真实建模；金额人民币十五元，同一目标可多次建模，由宿主依据实际证据决定。
当前权威范围为 R4.3-026 的 2026-10-20 通用基线调整，以及 R4.3-024／025、
R4.3-029／030 和 R4.4-002 的适用执行／隔离／金额合同。

## 授权与边界

- Host 首次观察授权：2026-10-21T16:52:20Z（新加坡时间 2026-10-22 00:52:20）。
- Task：`r4-3-026-minimal-installation-chain`；Profile：`unified-modeling`。
- 所有托管角色使用 Codex／`glm-5.3-flash`；用户未指定 effort，按现有宿主
  runbook 默认选择 `glm-flash-max`。配置校验通过不等于真实线程已启动。
- 同一个 `resource_authorization.mode=amount`、稳定 `budget_ref` 与十五元授权覆盖
  初建、必要修模、独立验收、失败重试及收口，不以三轮次数为第二资源门。
- 唯一业务来源仍为安装资产与现场的原 `scenario.md`；完整原公开／隐藏题集由私有 CQ
  起草并经 Host 逐点审核冻结。Host、实现助手、生产与独立 Consumer/Judge 各守原边界。
- 冻结价表复用已确认的本地三桶配置，外部 Host 用量单列且不扣任务金额；费用是估价，
  不声称供应商账单。金额余额不扩业务范围或模型授权，也不要求花满才结束。
- 保护当前工作区既有未提交文档及其他材料。旧任务、预算、失败证据不接续、不改写。

## 启动前确认的缺口及最窄实现

现有通用角色／Skill 和跨场景技术合同已对齐，10-20 原目录全量工程验证有保留记录。
本次不重新建设 Team。根据 10-21 真实运行原件，定向核对首轮强制技术合同读取、
create scope 拓扑提示、工具参数／短报告引用和已拒交接请求处理；只修仍存在的责任面。
实现变更及相关检查结果在本记录后续追加，工程结果不作为语义验收通过证明。

## 运行记录

私有工作目录：`workspaces/minimal-chain-20261022-codex-glm-15cny-0055/`。
用户原文、配置、授权、预算快照和真实 semantic-start 证据分别保留，不把预算登记或
Delivery 会话建立称为已开始语义建模。当前准备完成，真实运行结果待后续追加。

正常目标是完成当前完整有界模型的 application、实际治理读回、自查和独立语义验收。
未通过时先区分模型质量、平台合同、协作／路由及基础设施，按原预算修最窄失败层；
保留原失败，不以服务健康或工具成功代替 L1，不将最小链结果外推较大场景或 L2／L3。

## 缺口修复与开发验证

本次实现仅改通用提示装配及对应合同，没有新业务概念或平台流程引擎：

1. 当前 unified 直接路径首轮完整读取业务源和现行 direct-modeling 合同；其余获准
   合同继续挂载，使用时按需有界读取，历史非 unified 路径保留原始初读合同。
   对本最小链，两个必读来源合计 18,000 字节；这是静态输入范围，不能当作真实 token 降幅。
2. create scope 的 bootstrap 身份不转成 existing 放置；单 Ontology 拓扑遵循当前分支，
   拓扑仍由建模 Agent 决策，平台不代替选择。
3. request／feedback 使用实际各自字段；短消息可直接内联，无已发布材料时省略 body_ref，
   有材料时沿真实发布回执与接收通道引用，不取消已有权限校验。
4. 显式拒绝结束该次请求；按真实 readiness 变化使用新 request_id 重试，不继续等待已拒请求。

开发助手完成相关验证：R4.3-026、prompt cache、R4.0-012 共 43 passed；
work board 29 passed。改动测试 Ruff、diff 检查通过；Runner 整文件的 7 项既有
Ruff 告警保留。变更 Skill validator、宿主最终检查及共享核心全量回归另行记录。
GitNexus detect_changes 为 low，但索引未识别本轮 Runner／包文件；不声称图级完整覆盖，
采用实际调用点、当前／历史路径及真实装配测试补充。尚未取得本次真实语义或效率证据。

## 本次真实采用及共享核心回归

真实 semantic start 为 `2026-10-21T17:03:02.656782Z`，距首次观察授权 642.66 秒，
在二十分钟内。启动代码 `72d4514`，baseline SHA256
`54634ab85611a0616bff61add5a049220db07a581f97415e5437693c8ad9264b`。
实际冻结的 Coordinator／Modeling 指令及 Modeling Skill 摘要与本次代码一致。
Delivery 与生产绑定均为 Codex／glm-5.3-flash／max；production 阶段原生线程于
17:11:48 成功切换，未以 yield 或申请代替实际 switched 证明。

共享 Runner 改动在真实启动后运行一次 modeling_team 全量，命令为 backend 目录下：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run --no-sync pytest -q ../modeling_team/tests --tb=short
```

结果：**3779 passed，12 skipped，318 subtests passed**，359 warnings，627.94 秒。
两项变更 Skill validator、最终 diff 检查亦通过。没有 backend／frontend 代码改动，
不需要重启应用服务；启动前现有 `/api/health` 返回 ok。

全景一题及切片三题均经 Host 阅读当前私有快照和业务来源逐点审核；完整原公开一题／
隐藏三题冻结，不减少分母，也不把 Host 审核作为 Consumer／Judge 独立验收。

生产两批实际应用：17:12:33 的两个 Class、17:13:04 的一条 relation_type；
Batch／Attempt 回执均为 applied，当前 revision 2。Modeling 完成治理读回、自查、
COMPLETE／coverage complete 的最终关联检查（3 个资源、21 条 statement、0 issue）、
关闭本次建模 session 且无剩余 lease。模型保留资产→现场方向、非所有权含义和未给基数的未知。
自查原件同时披露 query 的 ambiguous／ranking degraded／expansion incomplete，
及关系 statement 读的 has_more=true；不能把这些限制抹去或称为独立语义 PASS。

生产交接仍出现一次 cq_production_pending：Coordinator 终态未结清。Delivery 已按
当前合同等待真实 terminal_report_accepted 变化并以新请求重试，没有把已拒请求继续
当 pending 等待。该事实只追加本轮采用证据，不证明所有旧协作错误均已消除。
后续独立验收、金额／token、资源待命及最终收口仍待下节记录。

## 独立语义验收与资源结论

当前新通用方法组合取得最小链 **L1 有界独立非盲回归 PASS**：公开 1/1、隐藏 3/3；
全部四题均有有效裁决，无未执行题，evidence recheck 无 drift／unavailable。
两组冻结 digest 均为 `sha256:ef991cf325e90c54e4562b13b687dfd7a0672daf297885c22dd429d5e500641d`，
模型绑定 digest 均为 `sha256:72b4a4fc640f3129c2ff4302fddcc6f3c016ba3ff9d32c7e15dac98aca7740d8`。

- 公开报告 SHA256：`8343a63acd9872317a4b8e12d117cc6ebe0e90911d946c7ea3f259758f3c4233`。
- 隐藏报告 SHA256：`bf619eec7f202ac50b909d400fb3d78d9e4fa7b71a8c39892638f952056d1d10`。
- 真实报告路径分别为本 run 的 `acceptance-v3/public-regression/cq-batch-0001/attempt-0001/`
  与 `acceptance-v3/reports/cq-batch-0001/attempt-0001/`；Host 只读汇总和实际 operation
  report binding 留在私有目录，不改写报告。
- 两组实际 `work_state=completed`、`lifecycle=standby`；原 Consumer 保留 idle。
  acceptance 阶段原生线程切换于 17:21:31 实际完成。
- `complete_cq_acceptance` 于 `17:26:20.713641Z` accepted，Runner 计算 `cq_verdict=pass`。
  两次 standby 请求于 `17:27:25.766994Z`、`17:29:33.536863Z` accepted。
- 实际初建 1 轮／fresh semantic-start 1 次，无独立验收后实质修模；预算允许多轮不表示
  必须用完。当前最小业务目标已满足，不追加无必要 start 或重复实验。

资源实际保留：模型 revision 2、生产 Team 和现有 Consumer。写入凭据均已停用，
Build Session 终态，无剩余 lease，无 pending／unknown／in-flight write。
本次不是新题盲测，不覆盖资产—故障—工单、完整工业服务、L2／L3 或全链自主交付 PASS。

### 收口状态投影的最窄修复及边界

Host 复核期间先将 `read_only_wait` 当成收口异常，此判断过强，现予纠正：
当前 raw state 明确保存 `READ_ONLY_WAIT/read_only_wait/working/read-only`，readiness、
写入封存和 retained members 安全。`settled.jsonl`／`coordinator-final.jsonl` 未见，
不能以缺少该证据推断 Runner 故障，也不强制改状态、重启、停止团队或再发 standby。
原阶段报告、状态、回执、模型和独立报告均保留。

确认的程序缺陷是 Host 投影读取错误层级：实际附加状态在 `recorded_state.extra_fields`，
`get_run_status` 却从其直接层读取，导致 lifecycle／work_state／write_phase 等顶层为 null；
`finish_delivery` 也读取错误层级，可能把真实 standby 误报 read_only_wait。
本次仅修正现有字段投影和调用方读取，保留旧直接形状读取，不新增生命周期机制或放松封存条件。

三个直接受影响测试文件共 **166 passed**（16.48 秒），Ruff 与 diff 检查通过；
Host／Delivery 全组件及 CQ／standby 相关回归在最终提交前另行记录。
当前真实 run 无需新动作：其安全只读状态如实交付。投影修复由下次自然启动的
Host／Delivery facade 采用；不能追称当前旧 Delivery 进程已热加载或原 run 已转 standby。

## 用量、费用和耗时

只读统计截止 `2026-10-21T17:35:22.207517Z`，覆盖本次 12 个真实线程，含 Delivery
三个阶段线程、生产／CQ、两个 Judge 和四个 Consumer。使用现有 R4.3-019 归一化／去重，
从实际 runtime registration 明确收集 10 个 member 的 22 个数值来源，冻结前缀及摘要后复算。
已知输入／输出完整覆盖这些线程，但 provider 缺失记录、含糊身份、Host／开发助手及未接线
检索／排序辅助调用仍有缺测，总体统计 **PARTIAL**；不把缺数计零。

| 角色 | 输入 token | 输出 token | 已知合计 |
| --- | ---: | ---: | ---: |
| Delivery | 5,251,272 | 100,025 | 5,351,297 |
| Coordinator | 1,627,329 | 19,408 | 1,646,737 |
| Modeling | 1,321,799 | 9,864 | 1,331,663 |
| CQ | 277,825 | 4,173 | 281,998 |
| Consumer | 344,241 | 6,947 | 351,188 |
| Judge | 355,046 | 5,486 | 360,532 |
| 托管链已知小计 | **9,177,512** | **145,903** | **9,323,415** |

缓存和推理分别是输入和输出子集，没有再次相加。外部 Host／开发助手 token 为 unknown，
单列且不扣任务金额；未接线辅助调用也保持 unknown。已知小计低于 10M 不能证明完整任务
10M 目标通过，不作同条件净降耗或单项因果结论。
统计原件为私有目录 `usage-snapshot-173522/scope.json`、`report.json`、`report.md` 及
`token-usage-summary.json`；只是数值统计，不是新增语义验收器。

金额最终观测主账估算 **2.46355384 元**，其中已知数值定价 **1.46307984 元**、
保守暂估 **1.000474 元**，十五元剩余估算 **12.53644616 元**。
计量截止 `17:30:10.429187Z`，仍显示两个在途单元，保留尾差及覆盖限制；
不是供应商账单或全部费用结清证明，没有追加预算。

任务开始观察为 `2026-10-21T16:52:20Z`。准备至真实 semantic-start 为 **10分42.66秒**；
真实开始至完整四题报告为 **21分22.92秒**，至 Runner 验收回交为 **23分18.06秒**。
独立验收两组并行，公开约 2分31秒、隐藏约 3分48秒；不能相加当墙钟。
这些是可定位阶段窗口，生产包含 CQ、协调和等待，不冒充有效语义工时。
有效语义、技术、评审、等待的严格互斥分类仍 unknown；追加收口诊断和数值核对已单列披露，
不继续扩大平台／harness，也不以补齐统计为由追加模型调用或停止待命团队。
最终墙钟截止和最终提交见本文件后续记录及私有 execution-time-summary。

## 最终检查与交付截止

最终 Host／Delivery 全组件及 CQ／standby 相关回归：**593 passed，2 skipped**，83.35 秒。
命令在 backend 目录执行：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run --no-sync pytest -q \
  ../modeling_team/tests/test_host_ops*.py ../modeling_team/tests/test_delivery*.py \
  ../modeling_team/tests/test_team_standby.py ../modeling_team/tests/test_r3011_cq_lifecycle.py --tb=short
```

新 Host 进程对当前原 run 的真实读取返回 `lifecycle=read_only_wait`、`work_state=working`、
`write_phase=read-only`、无 first_blocker，证明投影修复生效；没有改写原状态。
当前旧 Delivery 不热加载，保留其原结论与安全只读态。此前 3779 项全量对应启动版本
`72d4514`，不将追加修复的 593 项结果拼接成新一次全量 PASS。
最终 GitNexus detect_changes 为 low，但仍未映射改动的 Python 符号；以聚焦调用点与
实际行为回归补充，不能宣称完整图覆盖。最终 diff 检查通过，只提交本轮拥有路径，
原 README、需求草稿、复盘材料及其他未提交工作保留。

本次业务目标与适用最小链 L1 已完成，保留原模型、独立报告、待命成员及剩余预算。
不对原 run 强制新增生命周期动作，也不为数字统计停止原团队。
最后完成时间和总墙钟以私有 `execution-time-summary.json` 的交付截止点为准，
用户可见回复直接展示起止、总耗时、token 和费用，不只提供文件链接。
