# R3.0-012 CQ 为核心的阶段验收 — 交付设计

- 日期：2026-09-13
- 状态：权威正文与判定边界修订完成，独立计划评审 Round 4 专项复核 PASS；历史轮次保留。
  尚未实现，产品测试、真实运行和语义验收均为 NOT RUN。
- 需求：[requirements-v3.0.md 的 R3.0-012](../../requirements/requirements-v3.0.md#r30-012-cq-为核心的阶段验收)
- 关联需求：R3.0-006、R3.0-008B、R3.0-009、R3.0-011。
- 关联计划：[共享测试计划](../test-plans/2026-09-13-r3-0-012-cq-centered-staged-acceptance-test-plan.md)。

## 1. 为什么需要这项需求

R3.0-011 已经提供了能力问题生成、审核冻结、隐藏题隔离、`cq-acceptance`、批次报告和只读
Platform Examiner/Acceptance 路径，但真实运行仍把 CQ 取证绑在生产终态包装上。auth010-start4
约 139 分钟的运行中，模型主体在约第 59 分钟已落库，后约 80 分钟消耗在终态和证据修复，12
次 issue 往返累计约 64 分钟，最终没有得到独立 CQ 判定。31 份原始回执实际为 17 次 dry-run
和 14 次 apply，历史摘要中的 15 次 apply 不作为计数依据。证据见
[运行记录](../../../workspaces/model-compare-20260912/auth010-start4-log.md) 和
[终态记录](../../../workspaces/model-compare-20260912/auth010-start4-terminal-record.md)。

最新 auth011 只作为状态证据：在 `bf5ab85` 上冻结 24 题（全景 8 题，其中 5 公 3 隐；切片
16 题，其中 11 公 5 隐），197 项 dry-run validated、175 项 applied、22 项未应用；11:50
用户主动停止，run 为 CLEANED、failed-written-retained（见 [auth011 宿主记录](../../../workspaces/auth011-20260913/host-record.md)）。它没有证明 #17 的真实终局已走通，也
没有证明 CQ 质量；#18 是建议题量反馈问题，#19 是大批次 inline 重复撰写造成的提交瓶颈。

当前代码基线已经包含 #17/#14 的修复提交，但不能从提交推导真实验收通过。现有实现的关键差距是：

| 现状 | R3.0-012 目标 |
| --- | --- |
| `__main__.py::_run_cq_acceptance` 读取 `production_delivery.ready` 与 `pending_writes`，这两个值来自 handoff 文件本身 | 宿主根据已有 receipt、Attempt、模型状态和在途状态验证 handoff；布尔值只能是派生结果，不能是唯一证据 |
| `runner.py::_cq_production_readiness` 主要根据 Coordinator/Modeling/Protocol 的 `completed` 或 `blocked` 状态返回 ready，`checks` 字段没有独立验证静默和交付 | 允许模型交付已确定且无不确定写入时开始 CQ；把角色状态、已应用内容、未应用内容和未知写入分开记录 |
| `runtimes/codex.py::_complete_generic_retrieval` 要求整组查询 matched、无截断、所有 asserted 项 `supported` 且 lineage complete；`terminal_report_blocked` 还负责 stdout/io lock 排空 | `cq_semantic` 的启动和交接不等待通用 terminal 质量门；继续保留读写安全、stdout/io lock、未决和未知写入防护。`full_joint` 行为不变 |
| Judge packet 带冻结 evidence bundle 和 Examiner 自报的 locator，但 Judge 无平台访问，也没有收到宿主校验后的真实响应内容 | 宿主按现有只读代理回执读取本批真实响应 artifact，校验 request/response digest、tool、scope、page 和路径后，把必要响应 bytes/投影交给 Judge |
| `_cq_execute_batch` 只有在全部 hidden report 到齐时才建立 Judge packet；早期有效报告会因后段失败没有逐题裁决 | 有真实响应支撑的 `completed`/`unanswered` report 可交 Judge，区分正确 unknown、语义不足和服务故障；未执行题仍留在完整分母中 |
| 报告目录固定为 `acceptance-v3/reports/<batch_id>/`，重跑同一批次存在覆盖旧证据的风险 | 沿用该根目录，使用现有 child session/host acceptance attempt 的唯一目录；占用路径直接拒绝，旧证据不可覆盖 |

## 2. 目标、选择器和范围

### 2.1 目标

本需求增加一个可明确选择的阶段验收范围，使已应用且可稳定读取的模型能够尽早接受真实 CQ
检验。CQ 取证必须同时满足：冻结题集、实际平台只读查询、获准范围、必要业务证据、独立
Acceptance 判定和前后状态绑定。终态报告、完整联合 checklist、全量结构 lineage 或 SQL
结果的缺口不能阻止 CQ 阶段开始，但其状态必须在报告中保留。

### 2.2 `acceptance_target` 是任务参数

任务参数采用封闭枚举：

```yaml
parameters:
  acceptance_target: full_joint  # 可选值：full_joint | cq_semantic
```

- 省略时等价于 `full_joint`。v3 任务的 Runner 配置快照仍应写出归一化后的值，便于审计。
- `cq_semantic` 只能用于已经选择 R3.0-011 能力问题流程的兼容 v3 Task；它不能把旧 R2.3
  run 或未选择 CQ 流程的 run 改造成新合同。
- Runner 在第一次真实 start 前把值写入 `acceptance-v3/run-contract.json`，并绑定 run ID、
  Task/Profile digest。start 之后、报错之后和 handoff 之后均禁止改变；历史 run 不追溯改口径。
- `acceptance_mode` 继续表示既有 `read-only-acceptance` 执行模式，`blind_status` 独立记录
  盲测/已暴露回归状态；二者都不被 `acceptance_target` 替代。
- 新选择器使用 `parameters.acceptance_target`，不再使用初版未实现的
  `parameters.acceptance_scope`。`candidate_publication.py` 的旧 continuation carrier 顶层
  `acceptance_scope` 仍是旧合同对象，不是此枚举；不迁移旧 carrier、加别名或展平合并。
  两个字段原本处于不同 envelope，不能仅因同名断言运行时类型冲突；本次改名只消除新合同歧义。

两种范围的关系如下：

| 范围 | 启动和通过条件 | 结论边界 |
| --- | --- | --- |
| `full_joint`（默认） | 继续 R3.0-006 的完整路径和既有通用 terminal/联合验收门 | 仍分别报告语义检索、语义授权、SQL 和业务数据安全声明 |
| `cq_semantic` | 通过本设计的最小生产交接、完整冻结隐藏题集、授权只读查询、必要业务证据和独立 Judge | 只报告 CQ 阶段结果；不表示 R3.0-006 full PASS、SQL 结果正确、完整授权专项、全量 lineage、L2 或 L3 已通过 |

`cq_semantic` 不是降低答案正确性标准。它只改变“何时可以开始取证”和“哪些终态包装不再是
前置条件”。必要业务事实没有来源或平台证据，仍不能 PASS。

## 3. 功能合同

### 3.1 最小生产交接

Delivery/Runner 复用现有 run 配置、Batch/Attempt、receipt、workspace/graph state、验证和
推理记录，生成一个与当前 run 和 freeze 绑定的生产交接。交接至少能核对：

- `run_id`、Project、获准 Ontology 集合、`freeze_id`/`freeze_digest`；
- 每个获准 Ontology 的 workspace state、graph state，以及读取所需的授权 scope 和工具；
- 每个相关 Batch 的 dry-run 状态、apply 状态、权威回读和验证/推理结果；
- 已应用内容、明确未应用内容、已知缺口和任何未知写入；
- Coordinator、Modeling、Protocol 的角色状态、已交付 artifact/digest 和当前在途状态；
- 宿主计算出的 `ready`、`pending_writes`、阻断原因和交接证据 digest。

`production_delivery.ready=true` 和 `pending_writes=false` 只允许作为上述证据的派生字段。只
带这两个布尔值的 handoff 必须拒绝并返回 `cq_batch_scope_unauthorized` 或可定位的等价合同
错误，不能靠修改布尔值重试。

交接判定遵循以下顺序：

1. 先确认 run、Task selector、freeze 和 authorized Ontology 集合彼此一致。
   handoff、model binding 和实际交付状态中的 Ontology 集合必须相同；只校验“每项都在授权集合内”
   不足以证明完整交付覆盖。
2. 确认每个已声明 apply 的 Batch/Attempt/receipt/readback 可以闭合；历史 dry-run 失败若已被
   合法修正并重验成功，不再阻挡交接；确定的失败计划可记录为 `not_applied` partial gap。
   只有已声称 applied 却没有对应合法 dry-run/成功回读，或 apply 写入状态不确定时，才不得交接。
3. 确认没有实际在途 mutation、未知写入、未能安全收尾的写 lease，或其他仍可能改变生产
   资源而无法判断结果的状态。这里要核对宿主的实际写/进程/代理状态，而不是只读取角色报告的
   `completed` 或 `blocked`。闲置但仍有效的 lease，以及不影响资源静默的终态 advisory issue，
   不得单独阻挡 CQ；`terminal_report_blocked` 仍可排空 stdout 和 io lock，并保留未知写安全，
   CQ 不绕过这些保护。
4. 把已知 `not_applied` 与 `unknown_write` 分开。已知未应用内容可被记录为 partial delivery；
   只要当前已应用部分可稳定读取，允许 CQ 使用完整冻结题集取证。未知写入禁止开始 CQ。
5. 角色状态为 `blocked` 只有在阻断原因是已知、写入状态确定且没有影响交接的在途操作时才可
   进入 ready；“blocked”本身不能自动等价为 ready。

008B 的七项 joint checklist 可以保持 `pending`。它不是 `cq_semantic` 启动前置；其状态和
未完成项仍进入报告。生产 handoff 仍然是生产角色的交接，不等待 CQ 或独立 Acceptance
terminal。

### 3.2 CQ 批次执行和独立判定

`cq_semantic` 沿用 R3.0-011 的 `cq-acceptance` 入口、一个连续 Platform Examiner 会话、
一个独立 Acceptance Judge、v3 batch packet、现有 `platform_read_proxy` 和 host-only 报告。
入口消费 `--run-root`、`--freeze-id`、`--model-handoff`，并读取已冻结的 `acceptance_target`。

执行顺序为：

1. reload freeze，确认 digest、排序、问题版本、public/hidden 分组及获批覆盖决定仍未被修改。
   按获批清单查漏题/承诺覆盖，不把“每切片必须有专属 hidden 题”写成硬门；批准排除与实际
   漏题分列。空 hidden 集、遗漏获批题或暴露题不得靠缩分母绿灯。
2. 使用宿主实际只读调用建立 pre-batch model binding。binding 必须闭合完整获准 Ontology
   集合、Project、workspace/graph 状态和授权 read tools；对于本批实际引用的语义资源，按
   §4.2 从只读 proxy response 中保存有界 evidence/lineage 语义投影，作为初始绑定。
3. Platform Examiner 只得到隐藏题的题干、scope、content version、授权只读 proxy 和报告
   schema；它不读参考答案、evidence bundle、原始业务材料、tester-only 真值或生产对话。
4. Examiner 按冻结顺序逐题查询和提交报告。`unanswered` 只有在没有可供判定的有效响应时
   才归为未完成；有效响应中的合法 unknown 或业务语义不足仍交 Judge，分别按允许的 unknown
   或 `model-recall-insufficient` 判定。只读服务故障、未执行和响应无法取得才归
   `platform-runtime-incomplete`。这些单题状态都不能阻止继续执行其他题；所有题的 ID/version、
   状态、failure layer 和 evidence locator 都要留在 host 报告。
5. 在建立 Judge packet 前执行 post-batch model binding 及 §4.2 的引用证据回读。workspace、
   graph 或本批引用的 evidence/lineage 语义发生漂移，保留已有报告但取消该批有效 PASS；
   post-read 不可用也必须记录为 runtime/infrastructure，不能把它解释成正确的 unknown。
6. 宿主只从当前批次的只读代理 receipt 和响应 artifact 取真实响应，按 §4.1 校验后给 Judge
   一个只含冻结依据、校验后的响应内容和 Examiner reports 的 packet。Judge 没有平台工具。
7. Judge 对已取得有效响应的题逐题判定。没有有效响应的题不被静默删除：保留为未执行或运行时
   未完成；若 packet 合同需要逐题结果，则由宿主按原始状态生成 `platform-runtime-incomplete`
   记录，不伪造 Judge 的 `pass`。
8. 报告完整题集的 executed、unexecuted、verdicts、coverage gaps、blind status、model
   delivery state、readiness evidence 和 cleanup。报告输出是 CQ 结果，不覆盖 full_joint
   或 R3.0-006 的状态。

### 3.3 CQ 逐题判定口径

Acceptance Judge 使用冻结参考答案、获批业务依据、实际查询响应和 Examiner 报告判断必要
业务含义，不做字面匹配：

- 必要业务主张必须能从实际平台查询响应中定位到资源、关系、规则、值或映射，并与冻结获批
  原文/业务依据相互佐证。需要 Evidence/Lineage 才能核对的必要业务事实仍须有可核对依据；
  但不要求每个业务资源都逐项 `supported` 或全量 lineage 完整。平台返回的 Evidence 状态
  原样保留，Agent、宿主或 Judge 不得补写或推断 `supported`。
- `Lineage Completeness`、`Evidence Status` 和 truth score 是不同概念。结构技术三元组没有
  逐条 evidence/lineage 标记时，可以作为 advisory 记录，前提是它不是该题必要业务依据；
  不能因此把业务事实的缺证改写成 advisory。术语边界以
  [glossary](../../reference/glossary.md) 为准。
- 冻结答案明确允许的 unknown，且查询没有与其冲突的已支持事实，可以通过。Examiner 补猜、
  把缺失当确定或通过常识填空不能通过。
- 参考答案与获批材料冲突、题面有关键歧义或材料不支持时，使用
  `question-answer-review`，不把题目问题归因给模型；旧版本和裁决保留。
- 若冻结原题要求数据库实际数值，而本阶段不执行 SQL 结果证据链，使用既有
  `question-answer-review`、`failure_layer=null`，在 `note` 标记
  `sql-result-outside-cq-scope` 并说明缺少的数值验证。保留已有语义证据，不把只答指标口径
  算作原题 PASS；原题仍在完整分母，其他题继续。不新增 verdict 枚举或在闭集 schema 外
  偷加 reason 字段。拆成语义题/SQL 题须经用户在冻结前批准，旧 freeze 不就地改写；来源中
  可直接证明的阈值/时限等业务数值仍按普通四态判断。
- 有效查询但业务关系、规则、值语义或映射不足时，使用 `model-recall-insufficient`，归因
  `modeling-quality`。
- 只读代理不可用、响应 artifact 缺失/篡改、digest 或 scope 不闭合、post-read 失败等，使用
  `platform-runtime-incomplete`，归因 `platform-contract` 或 `runtime/infrastructure`。

获批批次的完整 CQ PASS 必须同时满足：非空完整获批 hidden 题集均为有效 `pass`；无
unexecuted、待复核、模型召回不足或平台未完成题；无遗漏获批题/承诺覆盖、暴露题或模型状态
漂移；所有必要业务主张的实际查询响应与获批来源闭合。任一非 PASS 裁决均阻止整批 PASS，
不只未执行/运行未完成题会阻止。partial delivery 可以与 CQ 批次 PASS 并存，但交付仍为
partial，不代表完整模型交付或 R3.0-006 full PASS。

覆盖按冻结前用户批准的题集/覆盖决定，而非每切片题数判断。跨切片题可覆盖无专属隐藏题的
切片；用户事先批准本批排除某切片时保留批准依据和排除项，非空获批题集全通过可发布该批
CQ PASS，但 `全场景隐藏覆盖` 必须单独标为未覆盖/未通过。未获批排除、运行后漏题或删题仍
阻止该批完整 PASS；获批空隐藏集可以保留并继续流程，但不能产生空集 CQ PASS。复用现有
冻结审批引用与报告 coverage 信息表达这些区别，不建设新题库系统，也不修改旧 freeze schema。
报告构建器在 CQ target 下从冻结时的获批审核记录核对排除项，将获批排除与实际
`coverage_gaps` 分开汇总；没有可核对批准就不能推断“用户已接受缺题”。旧 full_joint 聚合不改。

### 3.4 有界排障和退出

报错按其是否影响 CQ 有效取证处理：

- 影响授权 scope、freeze/binding、只读查询、必要业务证据、写入确定性或资源安全的错误，
  必须修复、重试同一批次或明确报告阻断；不得靠改报告字段绕过。
- 只影响 terminal 包装、完整 joint checklist、无关结构覆盖或其他未纳入本轮的缺口，记录为
  非阻断缺口，不能拖住 CQ 启动。
- 已经执行的有效问题继续交 Judge；后续题失败不抹掉前面结果。无法继续时明确已执行与未执行
  题，保留第一阻塞层。
- 用户 stop 立即停止本批持有的 child/proxy，保留 run、已写资源、报告、receipts 和
  `failed-written-retained` 等既有证据；不自行恢复、重跑或追加 semantic start。
- 同一 `batch_id` 的再次只读尝试必须使用新的现有 session/attempt 目录。任何旧报告路径已存在
  时拒绝写入；不覆盖历史证据，不创建通用版本治理系统。

## 4. 最窄实现触点和数据流

### 4.1 Judge 使用真实平台响应

现有 `ScopedReadProxy` 为每次成功只读调用生成内存 receipt：
`tool`、`request_digest`、`response_digest`、`artifact_path`、page tuple、ticket/model
state binding。当前 child report 的 locator 也会被 receipt 校正和绑定，但逻辑 locator 不等于
响应文件已经落盘；当前代理 `handle` 只有转发、摘要、receipt 和返回值，没有响应持久化。
R3.0-012 只在 CQ scope 补齐“留存真实响应并交给 Judge”这一接缝：

1. 宿主为 CQ proxy 接入当前 attempt 的响应留存回调，在成功读取发生时按 receipt 的相对
   locator 保存规范化请求和原始 `result`，不含 key、token 或 host socket；不能等 child
   teardown 后从 digest 重建响应。留存失败须可观察，该调用不能提供有效判题证据。
   `_cq_execute_batch` 按 Examiner report 引用的当前 child receipt ordinal/tool 取 artifact；
   同时覆盖 §4.3 中有成功查询证据的未回答题。
2. 宿主从当前 proxy receipt 的授权 artifact 根解析 locator；必须命中该 receipt 登记的真实
   artifact，不能任意打开 Agent 指定的文件。保持既有 Runner 相对路径合同，拒绝 child 提交
   的绝对路径、`..`、根外路径、不存在文件、digest 不匹配、跨 session 或越权 tool。
   宿主内部解析为绝对路径不改变 child locator。同一 receipt 可支撑多题并复用，
   重复引用不是错误。分页/截断信息原样保留：需要全量集合的断言必须完成相关分页；已返回的
   单项事实可在足够支持该题时使用，不重新建立“任何查询都须全量无截断”的平台门。
3. 宿主读取 artifact 中的 `result`，按既有 `_digest(result)` 的 canonical JSON 算法重算
   `response_digest`，不对整个外层 envelope 或任意文件字节求 hash 后比较；规范化请求按
   既有 request digest 算法校验。只把必要的真实响应或等价的保留字段投影放入 Judge packet，
   并保留原 digest、request digest、tool、page
   和 question binding。投影不得把自报 `answer` 当成 response，也不得截断后仍宣称完整。
4. Judge packet 的最小增量是一个按 question ID 绑定的 `platform_read_responses`（名称可按
   现有 schema 命名）字段；其内容由现有 receipt artifact 产生，不新建查询审计系统、不让
   Judge 获得平台 key/路径访问或写能力。
5. Judge 只对 packet 中存在且通过 digest/scope 校验的 response 作语义比较。伪造 locator、
   不存在 artifact、响应与 digest 不符或响应本身不支持答案均保留失败状态，不能依赖 Examiner
   自报 IRI 与 answer 和参考答案恰好相同来 PASS。

### 4.2 前后模型绑定包含证据状态

当前 `_cq_observed_state_entry` 的 digest 只覆盖 workspace/source signature 和 graph
revision/content hash。`EvidenceReferenceService.associate` 不推进这些版本，因此仍保留
原有全交付范围的模型前后重验，另在宿主补一份本次回答实际引用证据的有界核对记录：

1. 初始值取 Examiner 实际读取时由 proxy 保存的响应，而不是验收前预扫所有 Ontology。
   按 receipt/资源 ID 去重，保存用于回答的资源、语义值、evidence 状态、证据引用及内容、
   lineage/premise 标识和必要缺口。成功空查询也保存状态、scope、分页与结果空集。
2. Examiner 退出后，宿主复用相同授权只读操作/参数回读这些引用；资源可精确读取时优先精确
   读取，集合/不存在类结论核对原有查询及其所需页链。保留原始响应；比较规范化语义投影，
   排除请求 ID、耗时、排序分数等非语义噪声，集合按稳定资源/证据 ID 排序。
3. 原始与回读的语义值、证据内容、关联身份、lineage/premise 或缺口发生变化均记 drift；
   不能只比较数量，等量替换仍须识别。与该批回答无关的全库资源不进入这次核对。
4. 记录置于本次 host-only attempt 报告的 `evidence_recheck`，不修改旧 v1 model binding 的
   闭集字段，不新增 backend workspace 字段、聚合 API、数据库表或全图快照。
   相关回读不可用时不声称证据稳定，保留报告并记录 `platform-runtime-incomplete`。

Judge 只消费通过前后模型与引用证据核对的回答。若发生漂移或无法重验，保留 Examiner 的
原始回答，但不发布对应快照的有效逐题 PASS 或整批 PASS；生产者后续修复需要另记验收尝试。

### 4.3 部分报告交给 Judge

在 `_cq_execute_batch` 中把当前的 `batch_complete = len(reports) == len(hidden)` 拆为两个判断：

- `judgeable_reports`：通过 report sink、question ID/version 在本批且具有真实响应的
  `completed` 或 `unanswered`。成功空结果仍是有效响应，可由 Judge 判业务不足或正确 unknown；
- `unexecuted_or_failed`：实际服务/代理故障导致的 `runtime-incomplete`、响应不可取得或
  没有执行的题。不能把已执行的语义失败写进未执行列表。

当 `judgeable_reports` 非空且 pre/post binding、evidence bundle 和 cleanup 条件允许时，Judge
packet 只带可判题的冻结依据、响应和报告，返回这些题的 verdict。Host report 仍以全部 hidden
题为分母，实际未执行题进 `unexecuted_question_ids`，已执行服务失败单独保留。某题冻结依据
无法读取时只使该题缺乏有效裁决，不拖住其他依据完整的题；原文可读但参考答案与原文冲突则
交 Judge 判 `question-answer-review`。全局状态漂移/无法重验时保留回答，但不发布有效 PASS。

这是一处最小的 packet/报告接缝调整，不改变 Platform Examiner 单批次顺序、report sink、
四态定义或旧 R2.3 packet。若现有 Judge sink 必须看到一个完整题列表，则对缺报告题使用明确的
`platform-runtime-incomplete` 记录，并在 Judge packet 中标明其来源是 host 未执行/运行失败；
绝不能用空 answer 或 `unknown` 伪装成 Examiner 已完成。

### 4.4 交接与 terminal 的分流

数据流保持现有角色边界：

```text
Task acceptance_target
  -> run-contract snapshot
  -> Runner/Delivery verifies production handoff
  -> cq-acceptance reads verified handoff + freeze
  -> pre-binding + read-only Platform Examiner
  -> receipt-bound response projection/bytes
  -> independent Acceptance Judge
  -> batch report (CQ scope + full-joint status separated)
```

- `full_joint` 继续进入既有 `_terminal_report_guard`、`terminal_report_blocked` 和
  `_complete_generic_retrieval` 路径。
- `cq_semantic` 的 CQ 启动只依赖 §3.1 的 verified production handoff；不能把通用 retrieval
  completeness 或七项 checklist PASS 当作启动前置。
- `terminal_report_blocked` 仍负责 pending stdout/io lock 和写入安全。不能通过把所有
  `terminal_report_blocked` 都改成允许来实现 scope 分流；Protocol 仍须报告或保留未决写状态。
- `_handle_cq_handoff_complete` 与 `_cq_production_readiness` 应消费同一份宿主验证结果，不能
  一个信任 transport status、另一个信任 handoff 布尔值。

具体接线复用 host-only `cq_handoff_complete`：Delivery 在生产方声明交付后请求交接，Runner
先停止派发新的生产工作，并在既有 staged 写入/证据回贴 handler 上进入本 run 的只读交接期，
拒绝新 mutation、排空已进入的调用；若仍有未定写入，保留现场并返回可恢复原因。只读交接期
不复用 unknown-write 的永久拒绝标志，不要求终止角色。确定静默后，Runner 根据 §3.1 的证据
写入 `acceptance-v3/production-handoff.json`，事件中保存该文件 digest 与交付绑定。
CLI 的 `--model-handoff` 必须与此 Runner 记录匹配，并以实际授权 key 对全部交付范围重验；
不能仅信任任意用户文件。每次验收 attempt 保留本次 handoff 副本和对应事件引用。

这里不能只依赖“同一事件处理”：外层输入与 CapabilityBroker 写入来自不同线程。Runner 为
本 run 共用一个局部互斥/condition、交接阶段和在途 mutation 集合；两类 staged mutation 在
同一锁内检查阶段并登记调用，再释放锁执行远端操作，结束时登记已知结果并通知等待者。
handoff 在该锁内切换为 `quiescing`，新 mutation 返回可恢复拒绝；锁外等待已准入调用结束，
不能持锁等待网络。归零后仍须检查 unknown-write/receipt，不以“调用已返回”推导结果确定；
只有全部确定才保存 handoff，随后保持只读阶段。等待未排空时返回可观察的 pending 原因，
主循环仍处理结果和 stop。恢复生产由 Delivery 按原授权另行请求，不由验收者解除屏障。
这只是当前 run 两个已存在写入口共用的原子准入，不建设通用锁或跨机器协调系统。

CQ 可获得 handoff complete 通知并终态，但 Runner 在该次只读验收交回结果前保留所需范围、
读取凭据和生产暂停，不因全 roster terminal 提前 cleanup。Delivery 经既有 host-only 输入
交回不含隐藏题的 `cq_acceptance_complete` 摘要（attempt/report digest/CQ verdict），Runner
核对当前 attempt 的保留报告后结束交接期并按 CQ scope 正常收尾。该摘要只用于生命周期交接，
不能由 Coordinator 自报 PASS。语义失败也允许报告 PARTIAL/不通过后正常收尾；用户 stop
始终可中止并走现有资源保留清理路径。若 Delivery 选择修模，须先结束本次验收、按原授权
恢复生产并另记后续交接，不能让验收者恢复模型或把隐藏答案反馈给生产角色。

完成回交通路明确为以下最小增量：

- 在 `__main__.py::_KNOWN_OUTER_ACTIONS/_CQ_OUTER_ACTIONS` 与
  `runner.py::handle_cq_outer_input` 注册 `cq_acceptance_complete`。Delivery 通过当前
  `control/outer-input.fifo` 发送，仍由前台轮询分派；CQ scope 的启动路径启用这个既有通道，
  不再假设独立 CLI 能直接访问 Runner 内存，也不向 Examiner/Judge 暴露 FIFO。
- Runner 生成 handoff 时分配并记录唯一 `acceptance_attempt_id`、batch ID 和固定报告目录，
  CLI 消费该 attempt，不自行另建一个 Runner 不知道的 ID。再次验收先由 Delivery 请求新的
  handoff/attempt，原 handoff 副本、报告与事件全部保留，不在 pending attempt 上并行重试。
- host-only 完成 envelope 为 `action`、`run_id`、`freeze_id`、`freeze_digest`、`batch_id`、
  `acceptance_attempt_id`、`report_digest`、`cq_verdict`；不带题干、答案、query result 或
  自选 host 路径。Runner 从登记的固定目录读取报告，校验当前 run/freeze/attempt、报告摘要
  与汇总 verdict 后接纳。stale、伪造、摘要冲突返回可恢复错误；完全相同的重复消息只回确认，
  不重复收尾。
- 用本 run 的 `cq_acceptance_phase` 区分 `quiescing`、`acceptance_pending`、
  `acceptance_complete`；状态写入现有 state/events。pending 时不能因 roster terminal 进入
  `TERMINAL_REPORT_COMPLETE`；前台循环继续轮询 FIFO，保留读权限但不调度生产任务，沿用
  外层等待的 T3 扣除口径，不能用无 LLM 输出触发 run-fallback。完整、partial 和 failure
  报告均可完成回交，然后走原有唯一 `cleanup_once`；正常收尾不要求 CQ 全绿。
- 当前 `cq-handoff-request` 在交接成功时关闭，不能覆盖外部验收。交接成功进入 pending 的
  同一状态转移中打开 `cq-acceptance-wait`，直至当前 attempt 结果验证接纳或 stop/失败退出
  才关闭；同步扩展既有 `CQ_WAIT_WINDOW_KINDS` 闭集，落 wait tracker 与 state/events。
  与其他 CQ/issue 等待按实际时间区间去重扣除，
  关闭窗口后仍保留累计扣除，不重置生产 active 时长，也不在收尾时补算等待。T3 仍只检查
  原有效时长及原配置阈值，不能调大 10800 秒默认值或全局禁用来遮蔽缺口。前台 FIFO 轮询
  和 stop 不依赖 LLM 输出。此为需求功能合同第 8 项的实现接线，不是可选调优。
- Delivery 启动并监看独立 `cq-acceptance` 进程；正常退出后发送上述完成消息。若子进程失败
  或退出而缺完整报告，Delivery 用已有报告构建器留存 runtime-incomplete/未执行题记录并
  回交，不伪造 Judge 裁决。进程仍运行而未回交时显示 pending，不自行扩大超时或重启。
  若 Delivery 本身失联，仅保留可观察 pending 与既有用户 stop/宿主故障退出路径，不承诺
  自动恢复；stop、异常退出和正常回交汇合到幂等 `cleanup_once`，保留已经生成的证据。

| 最窄改动面（后续实现） | 复用部分与必要增量 |
| --- | --- |
| `modeling_team/contracts.py`、Task/Profile 校验、`runner.py` 配置快照 | 验证并冻结 `parameters.acceptance_target`；旧缺省继续 full_joint，不新增重复 CLI 选择器或迁移旧 carrier |
| `runner.py::_cq_production_readiness/_handle_cq_handoff_complete` 与 staged handlers | 共用本 run 的锁/condition、阶段及在途调用登记；原子关新写后排空旧写，验证结果并生成绑定 handoff |
| `runner.py::_terminal_report_guard`、`runtimes/codex.py::terminal_report_blocked` | 仅 cq_semantic 分离通用质量门；保留 I/O 同步与写入安全；完整模式行为不变 |
| `__main__.py::_run_cq_acceptance/_cq_execute_batch`、outer action 注册/FIFO/终态循环及 `cleanup_once` | 消费 Runner 登记的 attempt，执行证据回读/部分题判定；注册完成 envelope，pending 继续外层轮询，校验回交后唯一收尾 |
| `acceptance_runtime.py` 的 v3 packet/report sink 与 `agent-packages/v3-acceptance-batch/` | CQ scope 下增加由宿主生成的真实响应包，允许部分题受判；同步闭集 schema、输入生成器与消费端，不改旧 R2.3 packet |
| 现有 `ScopedReadProxy`、`read_proxy_mcp.py` 与 child teardown | 复用 receipt 合同，CQ scope 接入宿主响应留存回调；成功读时保存请求/result，在 teardown 前保留本 attempt 引用证据，不增加 Examiner 工具权限 |
| `competency_questions.py` 报告构建及 scope 对应角色提示 | 复用四态和完整分母，补 scope/交付状态/advisory/证据重验摘要；Coordinator 只收脱敏结果，不读取 Judge 依据 |

### 4.5 报告目录和谁产出谁消费

| 产物 | 生产者 | 消费者 | 保留规则 |
| --- | --- | --- | --- |
| `acceptance-v3/run-contract.json` | Runner | CQ CLI/报告 | run 开始冻结，旧 run 不改 |
| `acceptance-v3/production-handoff.json` 与其 Runner 事件 | Delivery 请求、Runner 生成 | `cq-acceptance` | 与 run/freeze/model binding 绑定；缺证不能靠布尔值补齐 |
| `acceptance-v3/reports/<batch_id>/<attempt>/batch-report.json` | host `cq-acceptance` | Delivery/Acceptance review | attempt 目录唯一，旧报告不覆盖 |
| proxy response artifacts/receipts | 只读 proxy/runtime；CQ 分支新增响应留存 | host Judge packet builder | Runner 相对 locator，按 canonical result 校验 digest；child 结束后仍保留本 attempt 引用证据 |
| Examiner reports | Platform Examiner/report sink | host 和 Judge | 每题保留，拒绝只重提同题，不跳过后续题 |
| Judge verdicts | 独立 Acceptance | host batch report | 不持有平台写、Team transport 或生产 run 控制能力 |

需求功能合同第 9 项约束这些保留产物：创建新 attempt 时原子占用唯一目录，已发布路径不得
被 `_write_host_only_json` 的 `os.replace` 覆盖。每个最终报告只发布一次；中间结果与最终
报告使用不同已登记名称，临时文件只用于首次完整发布。新尝试保留旧 handoff 副本、原始
响应、失败报告与清理证据；冲突可恢复地申请新 attempt，不通过改全局 JSON writer 波及旧路径。

## 5. 高风险假设

1. 就绪链：当前源码以 terminal 推断静默，不能直接使用。两类 staged mutation 与 host
   handoff 跨线程，必须以 §4.4 的局部锁/condition 统一准入，并验证两种竞争顺序及未知写入；
   不能用单独布尔值代替。该风险只涉及本 run，不需要通用锁或 ticket 框架。
2. 当前只读代理已有 digest/相对 locator，但缺实际响应落盘。必须按 §4.1 在读取发生时接入
   CQ scope 留存回调，以 teardown 后仍可按 canonical digest 验证响应的用例证明链路；若
   只交响应投影，必须保留判定所需字段和原 digest，缺字段时判 runtime incomplete。
3. 现有 v3 packet/report sink 能通过最小字段扩展表达“部分报告可判、剩余题未执行”，并能用
   child session 或 host acceptance attempt 生成不覆盖旧证据的目录；旧 R2.3 packet、逐题 fresh
   合同和 `acceptance_mode` 不受影响。

## 6. 验收标准和非目标

### 6.1 验收标准

- 默认 `full_joint` 与现有 R3.0-006、R2.3 路径兼容；显式 `cq_semantic` 在 run 开始冻结，
  报错后不能切换。
- checklist pending 时，若 verified production handoff 已满足，CQ 可以启动；未知写入、
  未决写或不一致回读不能启动。
- CQ 使用完整获批 hidden 分母；空集、遗漏获批题/承诺覆盖、暴露题、待复核和未执行题
  不会被缩分母洗绿。获批某切片零专属隐藏题不构成题量硬门；批次 PASS 与全场景覆盖分开。
- Platform Examiner 只使用真实授权只读查询；Judge 收到宿主校验后的真实响应内容，不能只
  依赖 Examiner 自报答案或 IRI。
- 必要业务主张缺实际平台语义或获批来源支持时不能 PASS；不相关技术结构标记缺口可以作为 advisory。
- 部分批次的有效题可得到逐题 Judge verdict；状态漂移、post-read 失败或响应 artifact 失效
  会取消完整 PASS，并保留已经产生的报告。
- CQ 结果与 SQL、完整授权专项、全量 lineage、重复性、产品化和 R3.0-006 full PASS 分开报告。
- 原题必须验证 SQL 实际数值而本阶段不执行时保持待复核，不能仅凭语义口径取得该题 PASS。
- 用户 stop 后只清理本次验收持有的 child/proxy，保留已写资源和失败证据。

### 6.2 非目标

- 不建设新的平台业务 API、数据库表、通用 snapshot/lock/ticket/audit/编排框架或管理 UI。
- 不改变后端 Evidence、Lineage、授权、查询结果或 RDF 业务行语义；不虚构 `supported`。
- 不重建 R3.0-011 的 CQ 生成、审核、隐藏题隔离和冻结流程；只补其与阶段验收之间的实际交接。
- 不修改旧 R2.3 的 Source/Platform/Acceptance Examiner 合同、历史 freeze、verdict 或保留模型。
- 不把 R3.0-013“缩减各 Agent 上下文占用”带入本需求设计；R3.0-013 当前仅登记，后续另行
  细化。本需求不预设摘要、消息格式、线程、缓存或压缩阈值。
- 不把 `#19` 大批次 file-backed 提交修复作为本需求的隐含前置；若它阻断真实 run，按独立
  platform-contract 记录，不降低 CQ 判定标准。

## 7. 交付状态

本轮仅交付需求设计和共享测试计划；外部 Round 3 REVISE 后修订，Round 4 专项复核 PASS。
Round 1/2/3/4 的问题、严重度处置和修订/复核记录保留在共享测试计划 §6。
代码实现、独立产品测试、真实 modeling start、真实 Platform Examiner、Acceptance Judge、
L0/L1/L2/L3 均为 NOT RUN。后续开发以本设计和共享测试计划为固定范围，分别记录机械测试、
真实运行和语义质量证据；本轮结论不能替代这些验收。
