# R2.3-003 Existing-scope 增量建模设计

- 状态：Current Draft，待 plan review
- 权威需求：`docs/requirements/requirements-v2.3.md#R2.3-003-已有-projectontology-增量建模`
- 交付记录：
  `docs/delivery/records/2026-08-11-r2-3-003-existing-scope-incremental-modeling-delivery-record.md`
- Source bundle：
  `docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json`
- 更新日期：2026-08-11

## 1. 目标

使用一个全新的正式四角色 Modeling Team，通过 `existing` 模式连接 R2.3-005 Start75 保留的非空
Project/Ontology，只依赖当前平台事实、非敏感 scope handoff 和批准 source bundle 完成一次真实增量
建模。增量结果同时：

1. 解析 Start75 已建模的两个 `ExplicitUnknown`，保留其旧来源边界；
2. 新增一个 C evaluation -> B publishability decision -> A publication outcome 业务切片；
3. 保持 Start75 既有版本、输出、调用和发布关系正确且可查询；
4. 在同一最终 model state 上通过 validation、reasoning、governed retrieval 和两条独立 CQ。

## 2. 非目标

- 不恢复 Start75 Agent Session、Prompt、旧 verdict 或本地运行目录；
- 不复制、删除、重建或覆盖 Start75 本体；
- 不把 Dify、Workflow、Decision、Publication 等业务概念加入平台生产域；
- 不建设通用多需求编排、长期 Project 生命周期、自动回滚、并发写入或 Pi Adapter；
- 不建模普通 numeric score 阈值、其他 diagnostic、人工 review 后续或更多案例；
- 不把精确四次 start 授权解释为必须运行四次；首个完整 PASS 后 success-stop。

## 3. 功能合同

### 3.1 基线与启动

正式输入绑定 Start75 Project `7fc146d8-c76f-417b-9314-854544f269fc`、Ontology
`fd762f52-2f5e-4bc0-902a-5583135ab64d` 和一个不可变、非敏感 handoff。任何 Agent 启动、账本 reserve、
Build Session/Lease 或平台写入前，Runner 必须：

1. 验证 clean checkout、Task/Profile/model manifest/source manifest digest；
2. 通过授权平台读取重新确认 Project/Ontology 归属、Ontology 状态、默认 Graph Set、workspace version、
   没有 active Build Session/Lease 或 in-flight Attempt；
3. 将 live workspace version 与 handoff 比较；不一致时零副作用失败，不自动改写 handoff；
4. 确认本需求专属 StartLedger 已登记精确四次用户授权且没有 active reservation。

### 3.2 Agent 输入边界

- Coordinator 只得到目标、roster、CQ/验收标准和非敏感 scope identity，不得到 raw business sources；
- Modeling 得到当前平台只读事实、旧批准业务资料和两个新增 source 文档；
- Protocol 得到平台 mechanics、当前 scope、Modeling 的完整增量 candidate 和必要只读/写工具；
- Acceptance 得到冻结 handoff 与验收标准；每条 CQ 的 Source/Platform Examiner 仍按 R2.3-005 的
  fresh、隔离、只读边界创建和回收；
- 任一角色都不得看到 Start75 Agent 对话、旧答案、旧 verdict 或 tester-only 内容。

### 3.3 增量 candidate 与写入

Modeling 发布的 candidate 必须是“本轮完整增量”，不是对 Start75 candidate 的完整重发，也不是对本轮
candidate 的 patch。它用平台中立的 `existing_entity_ref` 声明需要引用的 Start75 语义实体 ID 与预期
Class，不携带平台 IRI；其余只包含 R2.3-003 新增/更新的语义项、完整 citations、constraints、dependencies
和 required retrieval paths。

Protocol 在翻译前使用 ontology-scoped live read model 为每个 `existing_entity_ref` 生成 Host/Tool
确定性的 existing-binding receipt。receipt 绑定 candidate digest、Project/Ontology、workspace version、
semantic ID、实际 IRI、Class 和 read evidence；缺失、重复或不匹配时在零 mutation 下冲突。纯 translator
只接受 candidate 加这份冻结 receipt，已有关系端点使用 receipt IRI；R2.3-005 create candidate 不接受该
参数且维持原翻译字节。Protocol 随后按当前 workspace version 对每个依赖阶段执行
`dry_run -> apply_atomic`。不得从 Start75 文件或 candidate 文本猜测平台 ID。每次成功 apply 后使用
receipt 的 after-version 作为下一阶段 expected workspace version。

两个旧 `ExplicitUnknown` 不删除。Modeling 应优先采用追加的 resolution 表达，将旧 unknown、当前结论和
新 Evidence 连接起来；如选择 `update_entity`，只能修改明确提供的 predicate，且必须通过 apply 前后
readback 证明旧 label/question/rationale 与关系没有丢失。平台现有字段级 update 会替换该 predicate 的旧值，
因此不能把不完整 property map 当成全量实体重建。

条件业务逻辑必须作为本体语义表达，而不是 Runner/Protocol 的硬编码分支。Modeling 可以选择通用语义
Rule、Condition/Decision/Outcome 对象或等价结构；验收只要求来源忠实、条件边界明确、可查询、可验证，
不预设 Class/predicate/IRI 答案。

### 3.4 写后失败

existing scope 不提供自动回滚。失败处理以第一次平台 mutation 为边界：

- mutation 前的 runtime/routing/platform 失败可以清理本轮资源，并在剩余授权内 fresh retry；
- 任一 apply 后应优先在同一存活 Team run 中读取当前状态、形成完整修订 candidate 和新 Batch 修复；
- apply 后若 Team terminal、mutation state unknown 或无法 readback 对账，停止新 start，保留 Project/
  Ontology、fence/attempt/session 证据并请求人工处理；
- 后续 start 只有在当前 model state 已通过正式 readback/validation 对账、形成新的明确 handoff 后才可
  继续。不得把原 Start75 workspace version 继续当作基线，也不得删除整个 Project 来恢复。

### 3.5 验收

Protocol 在最终写入后完成完整 readback、validation conforms、reasoning consistent 和 candidate 声明的
governed retrieval paths。Coordinator 只在 Modeling-ready 与 Protocol-silent 都成立后冻结两张 CQ ticket。
两轮按 `base-continuity -> no-score-policy-and-case` 串行执行，每轮 fresh Source/Platform Examiner，
两张 current/usable PASS 必须绑定同一个最终 model state。这样原样复用 R2.3-005 已验收的两轮
Carrier/revalidation/settlement 数量合同，不把本需求扩成通用 N-CQ 框架。

旧 unknown 的存在本身不是失败；如果查询不能区分“旧来源下未知”和“新来源下已解析”，或者旧 CQ 因
新增语义变得歧义，则为 modeling-quality FAIL。

## 4. 当前最小实现

### 4.1 复用基线

原样复用 R2.3-005 的四角色生命周期、Team Transport、candidate receipt、分阶段 Batch、governed retrieval、
Acceptance Carrier/Examiner、settlement、DeepSeek proxy/credential 和 aggregate cleanup。R2.3-003 只增加
需求特有的身份、existing scope、source/CQ 和账本政策，不重写这些已验收能力。

### 4.2 必需实现差异

1. 新增 R2.3-003 Task、四角色 Profile、model manifest、两 CQ acceptance standard、existing scope
   handoff/config；
2. 扩展 candidate authoring/receipt/translator，加入仅 R2.3-003 可用的 `existing_entity_ref` 与
   read-model binding receipt；translator 对 existing ref 不发 create/update command，只把新 relation 的
   endpoint 绑定到 live IRI。当前最小模型采用追加 resolution 对象/关系，不要求 `update_entity`；005 的
   create-only translator 输入/输出保持不变；
3. 把散落的 R2.3-005 formal Task/Profile 判断收口为两个明确注册的 formal run contract；R2.3-005 继续只
   接受其精确 create 合同，R2.3-003 只接受其精确 existing 合同，未知组合 fail closed；
4. 为 R2.3-003 增加独立 StartLedger namespace 与 `initial_authorization` 事件：固定初始 cap 0，空账本
   只接受一次绑定用户授权 ID/reference、精确 `additional_starts=4` 的初始授权；该事件不要求 prior
   terminal failure，后续 budget extension 仍要求正常前置。replay、locking、重复 ID/reference、事件顺序
   和 reserve 都 fail closed；不得读取、修改或消费 R2.3-005 的 Start75–77 账本；
5. 增加 nonempty-existing PlatformScope 路径：不调用 `_empty_context`，而是读取完整 workspace/history，
   只拒绝 active Session/Lease、in-flight Attempt/fence、身份或 handoff 漂移；cleanup 比较本轮 before/after
   workspace、确认本轮 Session/Lease terminal 并撤销 key，永不删除 P/O，也不因历史 batch/session 报错；
6. existing preflight credential 必须绑定 exact P/O/handoff/default Graph Set/workspace version，检查发生在
   initial authorization 之后、reservation/run root/Agent/Build Session 副作用之前；
7. Task/source staging 使用本需求的增量 candidate、两份新资料和两条 CQ；Acceptance Carrier 的两轮
   语义与 005 保持不变，只替换 requirement-owned standard/question/source binding；
8. Protocol 继续使用平台通用工具，不增加 Dify 专属 API、schema、read model 或硬编码查询。

“formal run contract” 只是两个已知需求的确定性身份/资产/作用域策略映射，不是动态插件系统、后台调度器
或通用 orchestration framework。

## 5. Future productization

- 任意需求声明式注册、动态 source/CQ、跨 Project 调度；
- existing-scope 自动 snapshot/rollback、跨 run crash recovery、长期 mutation journal；
- Project 生命周期 UI、并发 team 协调、通用 semantic migration；
- 自动把旧 unknown 转成通用时间版本知识状态。

以上均不属于 R2.3-003 完成门。

## 6. 风险核验结果

1. 平台字段级 `update_entity` 只触碰 payload 中给出的 predicate；existing relation 可引用绝对 IRI 追加；
   rule apply 会推进 workspace version。对应 4 个后端测试于 2026-08-11 PASS。
2. 当前正式 Runner 是 R2.3-005/create-only，Task/Profile/manifest/preflight/ledger 多处精确绑定；因此仅新增
   YAML 不可运行，必须实现第 4.2 节的窄扩展。
3. 当前 `PlatformScope._existing()` 会调用 `_empty_context()` 并拒绝任意历史 batch/session，不能用于
   Start75；必须实现第 4.2(5) 的 nonempty-existing 路径。
4. 当前本机数据库仍存在 Start75 Project/Ontology，历史 Build Session completed、Lease released；但正式
   API 因没有当前 read credential 返回 401，所以 live workspace drift 必须留到授权 preflight，不可用 retained
   文件代替。
5. 当前 Protocol translator 只生成 `create_*` 且要求 relation endpoint 在本轮 candidate 声明；必须实现
   existing binding receipt，不能重发旧资源或猜 IRI。
6. 当前 StartLedger 不允许 zero cap 的首次授权；必须实现一次性 `initial_authorization`，不能复用 005
   retry budget 事件。
7. GitNexus index 落后 HEAD 1 commit；按仓库入口刷新时因 invalid UTF-8 在 `LOWER` 阶段失败。旧索引只
   用于定位，设计结论以当前源码和测试为准。

## 7. 完成标准

- 权威需求、source bundle、设计、共享测试计划和交付记录一致；
- plan review 无未处理 Critical/High；
- deterministic tests 覆盖两个 formal contract 隔离、003 ledger、existing preflight、source visibility、
  delta candidate、两 CQ 和写后失败；完整 repository-required suite PASS；
- 用户已授权精确四次 starts；一个真实 R2.3-003 Team run 在 Start75 Ontology 上完成组合目标与独立验收，
  首次完整 PASS 后停止；
- Runtime/credential/Build Session/Lease/child/proxy 清理为零残留，Project/Ontology 保留；
- 需求状态、设计结果、测试轮次、runtime health、cleanup 和 commit 全部同步。
