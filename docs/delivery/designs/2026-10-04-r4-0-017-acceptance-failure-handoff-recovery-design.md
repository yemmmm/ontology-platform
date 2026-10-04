# R4.0-017 验收运行故障的交接路径修复与局部失败恢复设计

## 1. 设计状态、依据与边界

本文是 [R4.0-017](../../requirements/requirements-v4.0.md#r40-017-验收运行故障的交接路径修复与局部失败恢复) 的详细设计，承接 R4.0-009 的独立验收边界、R4.0-013 的证据归因、R4.0-016 的范围／入口记录以及现有 R3.0-011／R3.0-012 的 packet、报告和恢复合同。本文只修复和验证已经暴露的 Examiner→证据→Judge→报告交接边界；不扩大 Judge 权限、不新建整批重跑或恢复平台、不把运行失败解释成模型质量。

本文交付的是可评审方案。真实故障复测、受控独立验收和语义结果必须另行记录；任何后续成功都不能覆盖原始失败、旧报告或冻结题池。

## 2. 已知问题与目标

真实运行暴露了几类相互独立的阻塞：旧步数／预算限制、Judge 原生输入长度上限、单题超限导致整批中断、子进程 stdout／异常输出不完整，以及交接／分组／报告收口阶段无法把已取得答案交给可判定输入。多次已取得 Consumer 回答，却没有对应的有效 Judge verdict。

目标是沿一条真实路径核对并修复最窄阻塞：

- Examiner 实际读取与回答完整抵达 packet；
- packet 以无损、可定位的方式进入 Judge，输入体积受控但不截断必要证据；
- 分组或单题失败不会吞掉其余可独立判定题，完整分母和未完成项保留；
- 首个失败阶段、异常类别、子进程输出和清理状态可观察；
- 失败可在原授权和既有安全接续路径内恢复，不重复隐式启动、不拼接旧报告、不把诊断成功当语义 PASS。

## 3. 复用的现有合同与故障层

| 路径 | 复用／核对点 | 失败归属 |
| --- | --- | --- |
| Examiner 查询／作答 | 现有 `platform-examiner` 工具、read scope、分页和显式未知合同 | 语义答案问题或读取未完成，保持原状态；不由宿主补写事实 |
| Packet／证据汇总 | `modeling_team/acceptance_runtime.py` 的 `AcceptanceBatchPacket`、响应引用和 model binding | 内容／引用丢失为 platform-contract 或 collaboration/routing；输入受限需可恢复反馈 |
| Judge 分组／输入 | `modeling_team/__main__.py` 的 per-question grouping、partial judging、visibility 入口 | 单组／单题失败保留 `runtime-infrastructure`／既有第一失败层，不扩大成模型失败 |
| Child 执行 | `modeling_team/runtimes/codex.py` `run_v3_acceptance_child` 及其输出／异常诊断 | native 启动、stdout、退出码和清理问题归 runtime/infrastructure；未知根因保留未知 |
| 收口／报告 | `validate_acceptance_verdict`、`build_batch_report`、现有 handoff／attempt | 分母、未完成、skipped、旧报告和 digest 保持完整；不以局部 PASS 收口全批 |

`platform-examiner` 和 Judge 仍是隔离角色。Judge 不获得平台读取能力、隐藏资料或生产修复权；宿主只做合同、资源和报告完整性核对。

## 4. 设计决策

### D017-1：先建立交接边界，再定位具体失败

验证顺序固定为 Examiner 作答完成 → 保留原始响应／引用 → packet 组装与 digest → Judge 输入／分组 → 每题 verdict → batch report／handoff close。每一阶段都记录输入、输出、数量、绑定和第一异常；不得只用最终“child failed”覆盖底层故障。

### D017-2：保持全局分母，允许局部继续

题集在 R4.0-016 登记的冻结分母保持不变。可独立判定的题继续进入 Judge；超限题、失败组、缺 packet 或失败 child 明确标记未完成和首失败层。整批 PASS 仍要求所有应验收题有有效裁决、无待复核／未完成／漂移；局部成功不缩小分母。

### D017-3：输送优化必须无损，窄读取不能变成删证据

输入体积过大时，优先按题／组分隔、复用已有 response handle／artifact 引用、只传当前题需要的已保留事实和明确摘要；摘要必须可回到完整原始响应。不能用截断文本、伪造引用、删除分页尾或跨题拼接来过 Judge 输入限制。Consumer 仍可按原合同取得其所需事实；不为 Judge 诊断新增查询。

### D017-4：保留第一错误和后续结果

运行记录至少保留阶段、时间、question／group、异常类别、退出码、受控的 stderr／stdout 摘要、清理结果、输入／输出路径和是否存在不确定写入。私有正文、凭据和隐藏答案不进入开发 Agent。后续重试、可观察性补充或成功继续记录为新事件，不能覆盖首错误。

### D017-5：修复先过 T0，再走既有恢复

某个 guard 阻断时，先核对它保护的写入完整性、授权、分母／证据完整性是否真实存在；若风险由上层覆盖且后果可恢复，优先将错误变成可定位、可重试反馈；只有必要硬门才保留并收窄。没有不确定写入时，优先沿既有同 run／acceptance-only 路径继续；需要 fresh start 仍按用户授权计数，不能由修复自动追加。

## 5. 受影响失败案例与处理

| 案例 | 首要检查 | 期望处理 |
| --- | --- | --- |
| Judge 输入超过 native cap | 记录实际 packet 体积、题／组边界和是否已保留完整 artifact | 通过无损分组／引用继续可判题；超限题单独未完成；不截断或假造响应 |
| 单题或一组异常中断整批 | 比较预期分母、已到达题目和剩余题目 | 其余独立题继续；失败题保留第一错误和未完成状态；报告不能整批 PASS |
| child stdout／退出异常 | 保留启动参数白名单、退出码、stderr 摘要、child artifact 和清理状态 | 给出类型化运行诊断；无法定位时写原因未知；后续成功不覆盖原异常 |
| source／handoff／写入锁阻断 | 核对 source process、write tail、Batch／Attempt／receipt 和 handoff state | 沿既有停止／对账／恢复通道处理；不删锁、伪改 state 或重放未知写入 |
| Judge map／group／报告 stale | 核对题目 identity、freeze／model binding、selector、attempt 和 report path | 只读拒绝或重建当前输出绑定；旧报告原样保留，不拼接成新 PASS |

所有案例先判运行／路由状态，再判断是否有充分语义证据；不能因 Consumer 已回答而强行判 PASS，也不能因 Judge 没判而把模型标为失败。

## 6. 详细交接流程

1. 宿主读取 R4.0-016 范围台账，锁定本次可验收题集、visibility、冻结摘要、model binding、attempt 和完整分母。
2. Examiner 逐题或按既有批次读取；对每题保存 answer、tool response、分页／完整性、显式未知及 artifact 引用。响应缺失时标为未完成，不让后续摘要补写。
3. Packet builder 计算输入统计和 binding，记录题／组数量、引用数量、原始 artifact 路径、摘要算法和可回溯关系；检查隐藏题隔离和 Judge 无读取工具。
4. 先用安全的组／题边界启动 Judge。每组结束即写入该组 verdict／failure；组失败不删除其他组输入。单题无法装载时记录原因、保留全局分母并继续可行组。
5. Judge 收口时执行现有 verdict 合同、skipped／drift／source failure 校验和完整 PASS 门。报告同时包含完成题、未完成题、首失败、输入／输出证据和旧报告引用，不重复计题。
6. 若需修复，先完成窄实现或 prompt-contract 修复、开发回归和独立故障 fixture，再在获准范围内继续既有 attempt／acceptance-only 路径；新输出写新目录，原始 run／report 不改。

## 7. 实施触点与最小变更

| 触点 | 计划核对／变更 | 不做的事 |
| --- | --- | --- |
| `modeling_team/__main__.py` | 核对 per-question／group 分组、partial judging、首失败和 report close；必要时把单题／组异常改为可恢复继续 | 不缩小题集、不吞错、不新增 Judge 权限 |
| `modeling_team/runtimes/codex.py` | 保留 child 退出、stdout／stderr、解析和清理诊断；必要时补最小类型化输出 | 不把所有 native 异常包装为 modeling-quality |
| `modeling_team/acceptance_runtime.py` | 核对 packet 绑定、response 引用和输入统计；只在无损传输无法验证时修窄缺口 | 不新增诊断查询、报告大改或跨批拼接 |
| `modeling_team/competency_questions.py`、现有 report／host ops | 复用冻结／identity／attempt 合同，保留旧报告和题目分母 | 不修改业务题意、答案、冻结池或资源 |
| `skills/modeling-dev-loop/references/team-runbook.md` | 补失败层、首错误、局部继续和安全恢复操作 | 不增加每次 run 的全面预检或固定重试 |

若当前代码已经有 partial/group 逻辑，仅补实际故障暴露的观察或输入边界；不为未来规模提前重建 packet、调度或恢复框架。

## 8. 验收标准、审阅与证据分层

| 编号 | 验收场景 | 通过标准 |
| --- | --- | --- |
| A1 | 修复预算／Judge 输入限制 | 用实际组装、接收、分组、判定和收口路径验证边界；不只测 helper |
| A2 | 一题／一组失败，其余可判 | 其余题继续并各自落报告；失败题未完成；分母不变且整批不可 PASS |
| A3 | Consumer 证据较多、使用窄读取／输送优化 | 需要的语义、分页和引用完整；可从摘要回到原始响应；不截断、造证据或补查 |
| A4 | native／stdout／异常处理失败 | 首阶段、异常类型、退出／清理和安全诊断可见；未知根因明确保留，后续成功不覆盖 |
| A5 | 窄修复后安全接续 | 使用既有授权和安全入口，分别报告实际答题、有效裁决、未完成与失败；不新增全面预检或未授权 start |

独立设计审阅检查分母与旧件不可变、局部继续、无损证据、Judge 隔离、首错误观察、T0 防御复核和恢复授权；有 Critical／High 时修订后重审。开发测试验证输入／输出和异常边界；独立功能验收使用独立泛化 fixture 和真实组装路径；后续真实语义验收单独核对业务结果。任何 mechanical／runtime PASS 都不等于语义 PASS。

## 9. 结论边界

本文不声称已经解决 Start2／3／4／5 的所有历史阻塞。原始事件、旧报告、冻结题池和已取得 Consumer 回答必须在实现和验收中保留；未能定位的 stdout、入口或路由原因继续标记为未知。只有在实际受影响的交接链复测、独立故障验收和相应真实运行证据齐备后，才能更新 R4.0-017 的交付状态。
