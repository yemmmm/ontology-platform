# v5 Demo 功能扩展与已有模型续建验证

日期：2026-11-01。状态：当前 Demo 的有界 L1 验证完成。空本体 29/29 PASS，原模型续建 30/30 PASS；两个 run 已停止并清理临时凭据，模型及全部失败证据保留。

同日后续[完整性复核](2026-11-01-demo-model-granularity-audit.md)发现当前续建模型遗漏非空创建条件、
余额映射残留旧单位，原独立报告存在漏检。上句保留当时报告结果；当前不能据此保证模型完整性，
须修模和独立重验，未回写或覆盖原评价。

## 目标与授权

用户要求查看 v5 测试 Demo，为其增加功能，再验证建模能力及在已有模型上继续建模的能力；允许使用 GLM。
本次沿 `scripts/modeling` 和 v5 工作空间，默认使用 `glm-flash-low`，为本次任务创建独立 3 CNY 金额预算。
现有无关工作树改动保留。生产建模与独立只读验收分离，历史 PASS 不继承为本次结论。

## 来源与验证范围

- `docs/requirements/requirements-v5.0.md`：v5 权威需求。
- `skills/modeling-dev-loop/SKILL.md` 与 `references/v5-runbook.md`：宿主执行合同。
- `modeling_team/v5/README.md`：当前执行入口。
- Demo：`examples/llm-access-lab/`，此前 GLM 默认冷启动在原模型 revision 3 独立 20/20 PASS；历史 run 已停稳并撤销临时凭据。
- 原 Project：`40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`；Ontology：`755f1e0e-cf5d-47f2-a2a3-95220f4cba96`，14 个既有资源。
- 本次输入及原件：`workspaces/v5-runs/llm-access-v2-20261101-inputs/`；生产仅获 scope、business、api、schema、change、baseline-inventory 六项。
- 续建标准生产前冻结 30 项；另冻结空本体新建的相同业务 29 项标准，沿同一 task_ref／3 CNY 预算，后者不要求旧 IRI 保留。

## 执行与结论

功能为每模型可配置正整数 `quota_cost`，默认 1，提供独立修改接口。新调用按当前配置扣额，`calls.charged_units` 保留历史扣额；回放仍扣 0 且返回当前余额，旧库补默认 1。业务说明升级为 v2，应用／包版本为 v0.2.0。

开发红测为 11 failed／26 deselected；实现后 37 passed、1 条既有 Starlette 提醒。最后代码测试原件 `demo-tests.log` 为 37 passed、2.72 秒；Ruff check／format 通过。真实 HTTP 观察 23 组，默认费用回归与新增费用分别保留，临时服务器已停止。仅改独立 Demo，未修改平台后端／前端，不需重启平台服务。

续建 run 为 `workspaces/v5-runs/llm-access-v2-20261101-existing`，按 existing 绑定原项目／本体。首语义原生 task_started 为 2026-10-31 17:16:56.504 UTC，线程 `01a192f6-e13e-7221-8899-2d1b31296d12`，实际 glm-direct／glm-5.3-flash／low。原 run 不重启，历史验收保持其原 revision，不继承为 v2 PASS。

GitNexus impact 未找到 Demo 的 `make_call`，风险 UNKNOWN；已通过独立示例内调用点和 diff 核对影响，仅覆盖模型登记／配置／扣额／回放与 SQLite 初始化。未宣称图上的全调用覆盖。

## 实际阻塞与窄修复

1. 金额模式的两 run 共用账本时，一方刷新会读取另一方持续追加的原生用量，但沿旧的累计观察 end 把新样本永久过滤，误报传输缺测并产生超过 3 元的暂估。新红测实际得到 0.0072 而非 0.0048。v5 仅对专用持续原生流显式登记 follow；解析器按实际观察时点延长该样本依据，固定切片仍保持原上界。9 项预算测试、119 项账本／用量回归、第一次完整 v5 223 项通过。账本原件和暂停保留，通过现有账本追加一次 Host rescan 记录，重读三份原始流并按原 source／offset 去重；恢复结果为 0.22883124 CNY、provisional=0、coverage complete，原授权仍为 3 元。没有补零、删除真实缺测或追加预算。
2. v5 精确读取只开放四种 family，未接通平台已有的 table-mapping-detail／join-mapping-detail。映射读取红测 4 failed、原生绑定红测 2 failed；加入这两种 family 并同步生产／评价技术说明，定向 30 passed。后端 API、授权及 revision 检查未改。第二次完整 v5 **229 passed、1 条既有 warning、210.06 秒**，含实际 PostgreSQL 测试且无 skip；Ruff check／format 通过。
3. 原 run 的受治理投影只给 IRI，新 existing run 没有原生绑定。Host 将保存的 before-v2 完整数据中显式 v:id 与资源类型同原 14 份实际应用回执逐项核对，并核实当前仍为 revision 3，再交接到既有 applied-bindings.json。原件为 native-identity-handoff.json。没有猜 ID、修改业务模型或替建模 Agent 写候选；生产收到署名 host-technical 的通用工具合同及身份交接说明。此项属于一次技术补位，不能宣称自动 existing 初始化默认路径通过；该缺口后续单独闭环。
4. 空本体最后一批被原子拒绝（business_key 列缺 property_iri），但 result 的 resource_bindings 含预分配身份，v5 曾不区分 write_state 全部放入 applied-bindings.json。Host 一度据缓存误报 13 个已写入资源，已向用户更正：该时点实际为 9 个，最后 4 个 not_written。红测复现 not_written／unknown 污染缓存；修复为只登记 write_state=applied，保持真实错误／预分配原件。原 run 自然暂停后，按两份真正 applied 回执核对恢复 9 项缓存，无模型写入、无候选代改。原件为 fresh-applied-binding-reconcile.json；此项直接保护实际模型与执行身份的可信边界。定向 43 passed，最终完整 v5 **229 passed、1 条既有 warning、201.49 秒**（v5-regression-binding-final.log），再沿原检查点接续已保存候选。

T0 复核：预算、真实缺测暂停及原生身份检查直接保护真实授权和写入完整性，保留；过时观察窗口造成的样本丢弃没有保护本例的固定切片不变量，仅在显式 follow 的专用流收窄。映射问题复用已有受治理接口，不增加业务专用 API 或新治理／恢复框架。修复及工程回归占用了较多时间；停止扩展平台／harness，沿原 run 恢复当前验证。

## 已有模型续建：独立 30/30 PASS

原本体在 revision 3 上一次实际原子更新至 revision 4。变更前后完整平台 RDF 数据对比为
14 个原生资源全部保留，未增删资源，实际仅四个 subject 改变：Model、CallRecord、models
表映射和 calls 表映射。删除／新增各 6 个 triple，原件为 existing-model-delta.json。
最初候选使用错误的 entity-detail 映射引用，被编译器可恢复拒绝，未发生写入；后继 Agent
实际读取完整 table-mapping-detail，沿原目标自行纠正。候选、错误、真实 apply 意图及回执均保留。

生产自查 ready 后，独立 `existing-v2-full-30` 绑定同一原 Project／Ontology 的 revision 4，
新线程 `01a19310-0162-7b01-8362-627db0adb69c`，实际 GLM Flash／low。
最终三十项逐题 passed=true，证据 IRI 共 14 个，全部为原目标资源且覆盖全部原资源。
原生评价有 9 次材料读取、1 次治理查询及 19 次精确展开，包含 4 次表映射详情和
3 次连接映射详情；直接读取冻结题、同版来源、真实 HTTP 观察及署名技术输入。
报告为[续建独立报告](../../workspaces/v5-runs/llm-access-v2-20261101-existing/evaluations/existing-v2-full-30/private-report.json)，完整性复核见 inputs 下 acceptance-summary-existing.json。

通过范围包括原规则回归、默认／可修改正整数扣额单位、当前费用与历史实际扣额的区别、
正余额不足拒绝、变价后的零扣额回放、状态／去重次序、跨模型共享额度、旧库升级、
完整字段／连接映射和既有身份保留。结果是构造业务的有界 L1；一次 Host 身份交接及
运行时技术说明如实保留，不升级为无人补位的 existing 默认初始化或客户业务盲测。

该 run 已 stop／cleanup，原模型保留（existing-retained）。收尾回执确认
no_in_flight_attempts=true、aggregate_keys_non_active=true、protocol／admin 密钥撤销，
before／after 都无活动 Session／Lease／Attempt；读取临时密钥按 Host cleanup 先行撤销。
原快照及失败未覆盖。

## 空本体完整建模：独立 29/29 PASS

run 为 `workspaces/v5-runs/llm-access-v2-20261101-fresh`，新 Project
`596fa5ee-7b05-4e21-9cb6-a1296408d03c`、Ontology
`16eb3be0-e002-4756-a93c-8e298ee08992`。生产只获 scope／business／api／schema 四项，
使用独立新原生上下文和同一任务预算；不继承既有模型、候选、评价或身份清单。

三次真正 applied Batch 将模型从 revision 0→1→2→3：三个 Class，三个 relation_type
及三个表映射，最后一个表映射及三条连接映射。实际完整平台快照
`fe30a93b0cd74addb0202fef89966a63` 含 **13 个原生资源：3 Class、3 relation_type、4 table_mapping、3 join_mapping**。
读取声明缺 api、fields-only 映射提交、候选元数据和 business_key 的 property_iri 缺失等
原始失败均保留。修复仅由原 Modeling 依据公开来源／准确反馈完成；Host 没有代写候选。
被拒绝批次不算已应用；最后 apply-00006 的实际回执为 applied、revision 2→3，四个映射都真正写入。

生产治理自查完成后，独立 `fresh-v2-full-29` 绑定 revision 3，新线程
`01a1931e-f829-7183-af17-2307564dbc8e`，GLM Flash／low，最终 **29/29 PASS**。
逐题有非空实际模型证据，共引用 11 个真实 IRI；原生执行直接读取六份材料，执行一次治理
查询及十五次精确展开（涉及十三个不同 IRI，含全部四个表映射和三个连接映射）。
并非每个资源都单列为某题引用，未把引用资源数量当作新的评分标准。
报告为[空本体独立报告](../../workspaces/v5-runs/llm-access-v2-20261101-fresh/evaluations/fresh-v2-full-29/private-report.json)，完整性复核见 acceptance-summary-fresh.json。

该 run 已 stop／cleanup，实际模型 written-retained。sessions_terminal、
no_in_flight_attempts、aggregate_keys_non_active 均为 true；临时读取／协议／管理凭据撤销。
整个任务共两个 fresh semantic starts，各为原计划范围内的一个建模轮次；候选纠错、分步
交付和技术接续不重复算新轮，没有独立 PASS 后再修模。

## 执行耗时、token 与金额

宿主最早保留的时点为 2026-11-01 01:12:03 +08，统计截止 02:09:04 +08，记录窗口
**57 分 01 秒**；它不冒充用户发言的精确时刻，此前准备与宿主有效劳动 unknown。
首末原生时刻为 01:16:56.504—02:02:53.905 +08，窗口 **45 分 57.401 秒**；
原生执行区间并集 **26 分 06.663 秒**，生产并集 **23 分 35.597 秒**。

| 阶段 | 输入 token | 输出 token | 原生线程 | 本阶段原生区间并集 |
| --- | ---: | ---: | ---: | ---: |
| 生产建模与纠错 | 1,898,962 | 53,375 | 9 | 18 分 47.708 秒 |
| 生产自查 | 734,255 | 14,531 | 5 | 7 分 18.242 秒 |
| 独立验收 | 416,553 | 14,873 | 2 | 4 分 58.177 秒 |
| 合计 | **3,049,770** | **82,779** | **16** | 跨阶段并集见上文 |

输入＋输出 **3,132,549**；缓存输入 **2,561,472** 已包含在输入内。使用既有 distinct-thread
统计脚本取各线程最后累计值，包含全部失败和纠错，known-native 终态覆盖 complete。
原生区间包含工具／提供商等待，各阶段存在重叠，不能相加当总墙钟或纯有效语义劳动。
三次因实际代码新变化执行的完整 v5 回归分别 212.93、210.06、201.49 秒，合计
10 分 24.48 秒；其余诊断、准备、文档有效工时未精确计量。

同一 3 CNY 账本已计价 **0.87064344 CNY**，provisional=0，估算余额 **2.12935656 CNY**，
十六个原生计量单元已知、无本轮已登记缺测。外部 Host 用量单列 unknown、不扣任务金额；
平台内部排序用量未完整归集，全任务计量保持 PARTIAL，未取得提供商最终账单。
原件为 inputs 下 observed-usage-summary.json、task-budget/state.json 和 final-task-summary.json。

本轮宿主记录窗口中，生产原生区间不足一半，主要受真实平台合同缺口定位、修复与必要回归影响；
没有扩展业务或新建治理／恢复框架。更短后继路径是复用本次已验收 Demo、冻结来源及
已核实原生身份交接；相关代码／环境未变时复用测试。自动 existing 初始化仍须单独闭环。

## 最终边界

完成的是构造可运行 Demo 的功能扩展、有界 L1、新建与已有模型续建；程序开发测试、生产
自查及独立语义验收分别取证。三处窄运行缺陷修复后工程回归 229 passed，账本／用量 119 passed，
Demo 37 passed；GitNexus staged 检查 low／20 个文件／零已索引符号，影响核对来自直接调用点、
diff 和上述测试，不宣称图上的完整覆盖。没有修改平台后端／前端，无需重启应用服务。

尚未证明自动 existing 原生身份初始化、客户业务盲测、在线 SQL Consumer E2E、同条件 L2、
任意规模、净降耗或最终账单；旧 v1 的 PASS 和所有未完成／失败证据均保持其原范围。

同日后继[问数与 SQL 消费审查](2026-11-01-demo-model-to-sql-readiness.md)实际查询本次续建模型
revision 4：九题中四题可直接支撑 SQL、三题需补充条件、两题缺事件映射。六条 SQL 在
自有 Demo 副本中执行并核对，未修改模型；该结果不回改本记录的历史验收范围。
