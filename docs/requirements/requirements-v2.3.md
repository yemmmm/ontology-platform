# v2.3 本体建模团队运行标准化需求

## 文档信息

- 文档状态：R2.3-001、R2.3-002、R2.3-005 已交付并通过独立验收；R2.3-003 为
  `Current Draft（功能范围已确认，待 plan review、实现与真实运行）`。R2.3-005 的 Start75
  `r23005-real-20260810-deepseek-start75` 在正式 DeepSeek v4 Flash Team 上完成新作用域建模、五阶段应用、
  validation/reasoning、七条 governed retrieval、两轮 CQ PASS、Acceptance settlement、四角色 terminal
  chain 与零残留清理；Independent Round 29 对 804 个 retained 文件做只读复核，审计前后 digest 一致，
  固定 provider key 在产物中 0 命中。Start72–74 的失败及历史凭据证据继续原样保留，不被 Start75 改写。
  R2.3-003～R2.3-004 仍须按依赖顺序推进。
- 基础版本：`docs/requirements/requirements-v2.2.md`
- 关联版本：`docs/requirements/requirements-v2.0.md`、
  `docs/requirements/requirements-v2.1.md`、`docs/requirements/requirements-v1.1.md`
- 当前下一目标：R2.3-005 已完成；按严格成功即停止合同，不再消费已授权但未使用的 Start76–77。
  R2.3-003 改为继续 Start75 保留本体的 existing-scope 增量建模；最初授权的四次 semantic starts 已全部
  终止。用户于 2026-08-11 在修订合同 plan review PASS 后追加授权三次，精确 authorization ID/reference
  为 `user-20260811-r23003-revision-start1-3`；只能在实现完成、独立 deterministic PASS、服务重启和健康
  检查通过后使用。首次完整 semantic PASS 后 success-stop。
- 接手指南：`docs/delivery/archive/r2-3-005/r2-3-005-successful-modeling-handover.html`；阶段性旧计划和
  会话交接快照统一保存在 `docs/delivery/archive/r2-3-005/`，不再作为当前运行指令。
- 关联交付记录：
  `docs/delivery/records/2026-07-30-r2-3-001-ontology-modeling-team-standard-delivery-record.md`、
  `docs/delivery/records/2026-07-31-r2-3-002-new-scope-business-slice-delivery-record.md`、
  `docs/delivery/records/2026-08-03-r2-3-005-producer-runner-formalization-delivery-record.md`
- 总体目标：固定本体建模团队的机械运行基础，使后续建模流程优化主要通过新增 Agent、
  调整 Modeling Team Profile 和优化 Skill 完成
- 更新日期：2026-08-10

## 背景

R2.2-001 已通过 L0、L1 和 L3 证明一个由 Coordinator、Modeling Agent 和 Protocol Agent
组成的本体建模团队可以在隔离环境中完成真实建模闭环。最终 L3 同时表明，当前能力仍被包裹在
场景专用 launcher、角色 TOML、提示词、Session 审计、凭据、作用域、恢复和清理脚本中。

这种实现可以提供可信验收证据，但不适合作为后续日常建模入口：

- 每次增加 Agent 或调整角色，仍可能重新修改启动、Session、消息和清理脚本；
- 当前维护的 `ontology-modeling` Skill 仍以单 Modeling Agent 为入口，与已验证的团队方案不一致；
- Coordinator、Modeling Agent、Protocol Agent 的提示词和 Skill 没有形成可选择的团队配置；
- Codex 的 Session、subagent 和消息机制直接出现在场景实现中，未来整体切换 Pi 时容易侵入团队合同；
- L3 主要从空作用域开始，尚未分阶段证明标准团队能够在新作用域和已有非空 Project/Ontology
  上完成真实建模。

v2.2 曾否定把平台协议、Consumer、mutation、Judge、验收和语义修复集中进公共 Host Workflow。
v2.3 不恢复该方案。v2.3 引入的 **Team Runner** 只承担确定性的运行机械能力，不分配语义任务、
不审核候选、不生成 Modeling Items、不修复本体，也不判断建模质量。Agent 继续拥有智能判断，
Semantic Platform Core 继续拥有权限、Build Session、Lease、Modeling Batch、验证、推理、
查询和持久化事实。

## 与既有版本的关系

1. R2.2-001 的三个核心角色、Protocol-only 平台写边界和真实 L3 证据是 v2.3 的起点，但
   L3 场景、历史启动额度、tester-only 答案和恢复更正不是生产 Runner 依赖。
2. R2.1-001 的建模质量目标继续有效；v2.3 先固定运行基础，再分别验证新作用域、已有作用域和
   Pi Runtime，不在 R2.3-001 中宣称建模质量提升。
3. R2.0-002 的 Pi Local Runtime 和 Workflow Package 是 R2.3-004 的实现证据，但不约束
   R2.3-001 的 Team、Profile、Package 或 Runtime Adapter 合同。
4. v1.1 的 Modeling Execution Record 能力继续保留，但 v2.3 当前不建设运行审计，也不把
   长期事件留档作为 Runner 完成门。
5. Dify 或其他参考业务资料只用于后续有界验收，不能进入 Team Runner、Agent Package Schema
   或平台生产代码成为领域专属行为。

## 需求列表

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.3-001 | Team Runner、Agent Package 与 Codex Team Adapter | P0 | `已交付（独立验收 PASS）` | R2.2-001 L0/L1/L3；Codex 多 Agent；平台认证与 MCP |
| R2.3-002 | 新作用域真实业务切片建模 | P0 | `已交付（独立验收 PASS）` | R2.3-001 |
| R2.3-005 | Modeling Team Runner 正式化收口与可重复调用 | P0 | `已交付（Start75 独立验收 PASS）` | R2.3-001；R2.3-002 真实建模与验收证据 |
| R2.3-003 | 已有 Project/Ontology 增量建模 | P0 | `Accepted（start20 语义建模与 start20-2 Acceptance-only 均 PASS）` | R2.3-005 Start75 保留本体与运营基线；R2.3-002 批准来源 |
| R2.3-006 | 精简隔离 Examiner Runtime | P0 | `已实现；三次授权 operation（live-4/5/6）均为 BLOCKED（最后一次 live-6 为 Acceptance child-timeout）；清理/不变性/typed failure 证据独立 PASS，语义完成门未通过，待新 operation 授权复验` | R2.3-001 Team Runtime；R2.3-003 Acceptance-only 性能与隔离证据；R2.3-005 formal Acceptance |
| R2.3-004 | Pi Team Adapter | P1 | `待细化` | R2.3-005；R2.3-003；R2.0-002；R2.3-002/003 证据 |

## 总体交付顺序

```text
R2.3-001 Runner、Package、Codex Adapter
  -> 真实 Agent 能力与互操作冒烟，不实际建模
  -> R2.3-002 从新作用域完成一轮真实业务切片
  -> R2.3-005 Modeling Team Runner 正式化收口与可重复调用
  -> R2.3-003 用全新团队继续 005 Start75 的已有非空 Project/Ontology
  -> R2.3-006 精简并隔离 Source/Platform/Acceptance Examiner 上下文与查询通道
  -> R2.3-004 整体切换到 Pi Team Adapter
```

R2.3-003 以 R2.3-005 Start75 的语义结果和保留非空 Project/Ontology 作为 existing-scope 基线，
同时复用 R2.3-002 已批准、随后由 R2.3-005 再次使用的业务来源。R2.3-005 的完成证据同时满足其
运营启动前置。R2.3-004 必须排在 R2.3-005、R2.3-003 之后；Pi Adapter 的证据不能替代 Modeling
Team Runner 的可重复调用证据。

后续需求不得仅为了刷过业务语义验收而静默修改已经在 R2.3-001 接受的 Team Runner 核心语义。
R2.3-002 的预检或真实运行暴露 Runner、Adapter、Profile、Package、Skill 或平台合同缺陷，
或者发现与本轮建模闭环直接相关的有界优化时，可以在 R2.3-002 交付范围内评审、实施和测试对应
修改；涉及核心角色、权限或 Runtime-neutral 合同的实质变化仍须显式更新需求并取得用户确认。

## R2.3-001 Team Runner、Agent Package 与 Codex Team Adapter

当前状态：`已交付（独立验收 PASS）`

优先级：`P0`

### 现状是什么，需要改成什么

当前：

- R2.2 L0/L1/L3 各自包含场景专用 launcher、角色配置、输入 staging、Codex Session、
  用户答案恢复、凭据和清理逻辑；
- 增加角色或更换 Skill 尚不能只通过声明一个新团队方案完成；
- Coordinator 主要以测试任务和阶段退出方式工作，尚未成为建模期间持续在线的用户会话入口；
- Codex 专有的 Session、rollout 和 Agent 标识与场景逻辑耦合；
- `create` 和 `existing` 作用域没有统一的 Runner 入口；
- L3 的候选文件、hash、历史恢复和审计规则服务于特定验收，不应直接升级为通用团队状态机。

目标：

- 建立一个稳定、确定性、repo-local 的 Team Runner；
- 建立可选择的 Modeling Team Profile 和可复用 Agent Package；
- 通过 Runtime Adapter 隔离 Codex 专有生命周期，首版实现 Codex Team Adapter；
- 使用真实 Codex Agent 验证角色、Skill、权限、通信、持续用户对话和终态处理；
- 机械验证空作用域 `create` 与 `existing` 生命周期；
- R2.3-001 不提交真实 Modeling Batch，不判断建模质量。

### 核心概念

#### Team Runner

Team Runner 是本体建模团队之外的确定性本地程序，不是第四个 Agent。

Team Runner 负责：

- 读取 Team Profile、Agent Package 和本轮 Task；
- 建立唯一 run ID 和隔离运行目录；
- 调用所选 Runtime Adapter 启动固定 Agent roster；
- 向 Coordinator 提供已经启动的 roster；
- 机械转发当前对话中的用户原文和 Coordinator 原文回复；
- 装载角色 instructions、Skill、工具和权限；
- 维护暂停/继续、失败诊断和精确清理所需的最小本地状态；
- 执行空作用域 `create`/`existing` 的机械准备、读取和清理；
- 停止 Agent Runtime、撤销临时凭据、清理本轮拥有的资源并检查结果。

Team Runner 不负责：

- 决定 Agent 应如何拆分或完成建模任务；
- 解释业务资料、选择本体结构或判断语义；
- 生成、修改、重排或修复 Modeling Items；
- 审核候选、批准语义或判断模型质量；
- 模拟用户答案、提供 tester-only 信息或替 Agent 回答业务问题；
- 根据运行时表现动态增加、删除或替换 Agent；
- 抢占已有 Lease、接管历史 Build Session 或删除不属于本轮的资源。

#### Modeling Team Profile

每个 Modeling Team Profile 表示一套在运行前已经确定的建模方案，至少声明：

- profile ID；
- homogeneous Runtime profile；
- 固定 Agent roster；
- 每个 Agent 对应的 Agent Package；
- 本轮允许的 Agent 直接通信关系；
- Profile 级非敏感运行参数。

一个运行启动后不得动态增减 Agent、切换 Profile 或改变 Agent 权限。增加 Agent、删除 Agent
或改变 Skill 组合时，应创建另一套 Profile 并独立验证；这不要求修改 Team Runner。

#### Agent Package

每个 Agent Package 至少包含：

- 稳定 Agent/角色标识和说明；
- Runtime-neutral 的角色 instructions；
- Required Skills 与 references；
- 工具和平台权限声明；
- Runtime-native 薄装载配置；
- 本轮 Task Prompt 的输入合同。

Profile 只引用 Agent Package，不内嵌大段角色提示词。角色 instructions 说明“是谁、负责什么、
不能做什么”，Skill 说明“怎样完成专业工作”，Task Prompt 只提供本轮任务、允许资料和 roster。

Codex 和未来 Pi 可以使用不同的装载方式，但共享同一角色语义、Skill 方法和参考资料，避免维护
含义不同的两套提示词。凭据、临时路径、tester-only 内容和历史答案不得写入 Agent Package。

#### Runtime Adapter

Runtime Adapter 把 Team Runner 的稳定操作映射到具体 Agent Runtime，至少覆盖：

- 启动固定 roster；
- 向指定 Agent 发送消息；
- 接收 Agent 消息；
- Agent 间直接通信；
- 读取 Agent/Session 机械状态；
- 等待 Agent 终态；
- 暂停、继续和停止 Runtime；
- 读取当前运行清理所需的非语义标识。

团队合同不得依赖 Codex Session、canonical task name、rollout 或 Pi RPC 等专有字段。Adapter
可以在自己的实现和本地状态中保留这些字段。

R2.3-001 只实现 Codex Team Adapter，不实现第二个 fake Adapter，也不运行真实 Pi 团队。
R2.3-004 以后使用同一合同实现完整 Pi Team Adapter。

### Runtime 与并发边界

- 一个 Team Run 中的全部 Agent 使用同一种 Runtime；R2.3 不支持 Codex/Pi 混合团队；
- 一个 Team Runner 进程只管理一个 Team Run；
- R2.3-001 不建设多运行调度器、全局任务队列或远程协调；
- 未来调用方可以启动多个独立 Runner 进程，但每个进程必须使用不同 run ID、运行目录、凭据和
  平台作用域；
- 同一 Ontology 的并发写安全仍由平台 Lease、workspace version 和 Modeling Batch 合同负责，
  Runner 不实现新的分布式锁。

### 固定角色与权限

#### Coordinator

Coordinator 是一个 Team Run 的控制面主 Agent 和持续用户会话入口，但不是语义审批者或所有
Agent 消息的中转站。

Coordinator 负责：

- 接收已启动的固定 roster 并向 Agent 分配初始任务；
- 在其他 Agent 工作期间持续接收和回复用户消息；
- 将用户明确标记为补充事实、纠正、范围变化或建模指令的原文转发给相关 Agent；
- 当用户消息是否影响建模不明确时，先向用户确认；
- 接收各 Agent 的 completed/blocked 结果；
- 在 Runtime 报告全部 Agent 已进入终态后，向用户汇总团队完成或阻塞状态。
- Coordinator 必须是最后登记终态的角色；在 Modeling 和 Protocol 尚未都登记
  completed/blocked 时，Team Transport 必须拒绝 Coordinator 的 terminal result，但不得终止
  Coordinator Session，使其仍可完成在途用户问答和接收专业 Agent 结果；被拒绝的调用不算
  terminal result，也不计入“成功登记一次”的限制。错误必须列出尚未终态的依赖角色；当这些
  角色均已终态后，Coordinator 必须重试并成功登记一次；该规则由 Profile 角色决定，对基础
  三 Agent Profile 的 v1/v2 Task 一致生效；
- Protocol 必须在 Modeling 之后登记终态。Protocol 向 Modeling 返回平台 receipt、validation、
  reasoning、query 结果或可修订的 translation conflict 后必须保持 Session 活动；Modeling 必须
  先处理该反馈，选择提交修订候选继续循环，或登记 completed/blocked。Runner 将 Modeling 的
  terminal result 作为机械 handoff 交给 Protocol，Protocol 才可登记自身终态；Coordinator
  继续最后登记。被依赖门拒绝的 Protocol 调用与 Coordinator 一样不计成功次数；

Coordinator 不负责：

- 监看建模内容、定期检查语义进度或判断 Agent 是否思考太久；
- 诊断建模卡点或主动暂停 Modeling/Protocol Agent；
- 审核候选、发布 `candidate_ready`、批准 dispatch 或决定本体正确性；
- 代替其他 Agent 修改专业结果；
- 调用 Semantic Platform MCP。

#### Modeling Agent

- 负责业务资料理解、本体语义、约束、Shape、实例意图和显式未知等建模判断；
- 使用 Required Skill 完成 Profile 分配的任务；
- 可以与 Protocol 和其他已启动 Agent 直接自由沟通；
- 语义内容变化通过持续 Agent 对话交给相关 Agent，不创建 Runner 级候选 revision 状态机；
- 默认无 Semantic Platform MCP。

#### Protocol Agent

- 是当前 Team Run 中唯一可以配置平台写 MCP 和临时平台凭据的 Agent；
- 负责把建模沟通结果转换为严格平台请求；
- 可以与 Modeling Agent 直接沟通并保留自身 Session 上下文；
- 可以自行处理不改变语义的机械协议问题；
- 不能补造业务事实、改变本体含义或绕过平台约束。

R2.3-001 只验证 Protocol 的平台配置和权限隔离，不提交真实 Modeling Batch。真实写入合同由
R2.3-002 验证。

#### 其他专业 Agent

- Agent Package 可以声明完成任务所需的只读工具；
- 非 Protocol Agent 不得获得平台写 MCP；
- R2.3-001 增加一个真实专业 Agent Package/Profile 做独立互操作冒烟；
- 该冒烟只证明新增 Agent 不需要修改 Team Runner，不证明建模质量提升。

### Agent 通信与用户持续对话

已启动 Agent 可以按 Profile 直接使用自然语言通信，不要求每条消息符合 JSON Schema，也不要求
Coordinator 转发。R2.3-001 不增加候选 revision、`candidate_ready`、`dispatch_authorized` 或
候选 hash 状态机。

自然语言正文保持无 Schema。为防止可修订请求在真正交付前被终态关闭，Team Transport envelope
可以携带纯机械关联字段 `delivery_id`、`expects_reply` 和 `reply_to_delivery_id`；它们只证明某条
回复对应某条待回复 delivery，不表达 candidate 类型、语义状态或审批结论。Runner 只有在
Runtime Adapter 成功接受 delivery 后才记录 delivery acknowledgement；终态门只能依赖已确认
交付的匹配回复或 terminal handoff，不得把 Broker 入队或 result 写入当作已交付。

只有下列内容需要最小结构：

- 向用户提出的问题及对应原始回答；
- Agent completed/blocked 终态；
- Protocol 平台终态；
- 暂停、继续、终止和清理所需的本地状态。

用户持续对话复用当前 Codex 对话表面：

```text
用户
  <-> 当前对话中的外层调用方
  <-> Team Runner 机械消息传输
  <-> Coordinator Session
```

- 外层调用方和 Team Runner 必须原样传输用户与 Coordinator 消息；
- 外层调用方不得代替 Coordinator 回答或改变消息含义；
- 普通对话和状态询问只由 Coordinator 回复，不自动进入建模上下文；
- 只有用户明确声明的补充事实、纠正、范围变化或建模指令才原样转发给建模 Agent；
- R2.3-001 不新增聊天 UI、后台会话服务、消息数据库或审计 API。

### 平台作用域

Team Runner 支持两种显式模式：

```yaml
scope:
  mode: create
```

- 创建本轮唯一拥有的空 Project/Ontology；
- 创建和撤销必要的临时凭据；
- R2.3-001 冒烟完成后删除本轮创建的空作用域。

```yaml
scope:
  mode: existing
  project_id: "<project-id>"
  ontology_id: "<ontology-id>"
```

- 读取并校验指定 Project/Ontology 是否存在、可访问且状态允许启动；
- 不接管已有 Build Session/Lease；
- 不删除已有 Project/Ontology；
- R2.3-001 只对测试拥有的空 existing 作用域做机械读取和生命周期验证。

真实新作用域建模属于 R2.3-002，真实非空 existing 作用域增量建模属于 R2.3-003。

### 最小本地状态

R2.3-001 不写入平台 Modeling Execution Record，也不建设长期审计。Team Runner 只保留当前运行
所需的本地状态：

- run ID、Profile 和已启动 roster；
- Runtime/Agent 标识；
- Coordinator 当前可继续 Session；
- 待回答问题和已机械释放的原始回答；
- 当前平台作用域和本轮拥有的资源标识；
- Agent 与 Protocol 终态；
- 清理结果。

不要求保存隐藏推理、长期完整 transcript、不可篡改事件链或审计查询。需求验收证据保留至独立
测试完成，正常运行的后续保留策略不在 R2.3-001 中产品化。

### 失败与清理

- Profile、Package、Skill、权限或 Runtime 配置不完整时，在启动 Agent 前失败；
- 任一 Agent 启动失败时停止本轮，并清理已经启动的本轮 Runtime；
- Agent 自己报告 blocked 时，Coordinator 汇总该终态，不自行修复或宣称成功；
- Runtime 进程失败、失联或不能继续时，由 Team Runner 报告实际 Runtime 失败；
- R2.3-001 不加入 Coordinator 主动进度 watchdog 或自动卡顿暂停；
- `create` 模式只删除精确归属于本轮的空作用域；
- `existing` 模式不删除 Project/Ontology；
- 临时凭据必须撤销，Agent Runtime 必须停止，本地秘密必须销毁；
- 所有清理都按唯一所有权执行，目标不明确时停止删除并报告。

### R2.3-001 验收标准

1. Team Runner 可以读取一个基础三 Agent Profile 和对应 Agent Packages，并在隔离的 Codex
   Runtime 中启动完整固定 roster。
2. Coordinator、Modeling Agent 和 Protocol Agent 收到正确的 instructions、Required Skills、
   Task Prompt、roster 和权限。
3. Agent 可以绕过 Coordinator 直接通信；Coordinator 可以完成初始任务分配。
4. 在其他 Agent 工作期间，用户可以通过当前对话和机械转发与 Coordinator 持续交互并取得回复。
5. 普通对话不进入建模任务；用户明确的补充信息可以原样传递，含义不清时先取得确认。
6. Protocol 是唯一具有平台 MCP 配置的 Agent；Coordinator 无平台 MCP，其他 Agent 不具有平台
   写权限。
7. 每个 Agent 对自己的 completed/blocked 终态负责；Runtime 提供 settled 状态；Coordinator
   只汇总并向用户报告。
8. `create` 模式可以创建、读取并清理一个空测试 Project/Ontology，且无 Modeling Batch 写入。
9. `existing` 模式可以解析并读取一个测试拥有的空 Project/Ontology，且不会接管、覆盖或删除它。
10. 新增一个真实专业 Agent 时，只增加其 Agent Package/Profile；Team Runner 不修改即可完成
    Skill 装载、直接通信、权限、终态和清理冒烟。
11. 一个 Runner 进程只管理一个 run；不存在后台服务、多运行调度器或隐式并发作用域。
12. Runtime、临时凭据、本轮空资源和本地秘密按所有权完成清理，常驻平台服务保持健康。
13. 自动化回归、真实 Codex 能力冒烟和独立测试 PASS；测试不宣称本体建模质量已验证。

### R2.3-001 非目标

- 真实业务本体、Modeling Items、Modeling Batch dry-run/apply、validation、reasoning 或业务查询；
- 比较三个或四个 Agent 的建模质量、重复成功率或统计显著性；
- 真实 Pi 团队或 Codex/Pi 混合团队；
- 动态 Agent 创建、运行中扩缩容、多个 Protocol Agent 或并行写入设计；
- Candidate Artifact 版本机、语义审批流或 Host Judge；
- Coordinator 进度监看、卡顿判断或主动暂停；
- 平台执行审计、长期历史、管理 UI、远程执行或后台 Agent Runtime；
- 多 Team Run 调度和跨机器协调。

## R2.3-002 新作用域真实业务切片建模

当前状态：`已交付（独立验收 PASS）`

优先级：`P0`

### 现状是什么，需要改成什么

当前：

- R2.3-001 只证明 Runner、Package、Profile、Codex Adapter 和 Agent 能力边界，不执行真实建模；
- R2.2 L3 已有真实三 Agent 证据，但使用场景专用 launcher，不能证明 R2.3 Runner 的建模闭环。

目标：

- 以 R2.3-001 的基础三 Agent Profile 和 Team Runner 为基线，允许按本需求边界修复问题和实施
  直接相关优化；
- 从全新 Project/Ontology 开始完成一个有界业务切片的真实建模；
- 验证直接 Agent 协作、持续用户对话和 Protocol-only 平台写入；
- 产生一个有意保留的非空 Project/Ontology；该对象原计划供 R2.3-003 继续使用，但后续 R2.3-003
  已改为连接 R2.3-005 Start75，本对象只保留为 R2.3-002 交付证据，除非未来需求另行指定。

### 已确认范围

- 业务切片固定复用 R2.2-001 L3 已验收的 Dify Workflow-as-Tool `C -> B -> A`
  调用影响链，以及该场景已经冻结的 Agent-visible 来源和业务问题；
- Modeling Agent 负责真实业务语义和本体判断；
- Protocol Agent 通过正式平台入口完成 Build Session、Lease、不可变 Modeling Batch
  `dry_run -> apply_atomic`、validation、reasoning 和查询；
- Coordinator 在建模期间继续与用户对话，但不审核模型或监看 Agent 语义进度；
- 本需求不以修改 Team Runner 核心语义、Profile/Package 合同或 Codex Adapter 接口作为启动
  前提，但允许按下述边界修复 R2.3-001 问题或实施直接相关优化；
- 不以额外专业 Agent 作为完成前提，也不进行 Profile 质量对照。

### R2.3-001 问题与优化边界

- R2.3-002 不要求 Team Runner、Codex Adapter、基础 Profile、Agent Package、Skill 和确定性
  辅助工具在整个交付期间保持字节级不变；
- 来源盘点、预检或真实运行以直接证据暴露 R2.3-001 缺陷时，可以在 R2.3-002 内修复；
- 发现能够直接改善团队运行正确性、稳定性、可观察性、建模质量或语义检索质量的有界优化时，
  可以在 R2.3-002 内实施；
- 修改不得依赖 tester-only 答案、答案型本体或验收查询结果向 Agent 泄漏语义，也不得扩展到
  后台调度、长期审计、跨机器协调、管理 UI 或其他未来产品化能力；
- 已接受的三角色职责、Protocol-only 平台写边界和 Runtime-neutral 团队合同继续作为默认目标；
  若证据要求实质改变这些核心合同，必须先更新权威需求并取得用户确认；
- 每项修改必须记录触发证据、影响层、验证结果及对 R2.3-001 文档和验收结论的影响，不得作为
  未记录的场景内临时补丁；
- 违反 R2.3-001 或 R2.3-002 已确认合同、影响正确性、权限边界或真实验收的缺陷必须在
  R2.3-002 完成前修复；
- 非阻断优化不是 R2.3-002 完成门。可以在最终 semantic start 前明确纳入，也可以记录为后续项；
  仅发现可优化点不使 R2.3-002 失败；
- 一旦选择实施并改变运行行为，最终真实 PASS 必须覆盖修改后的基线；不得因非阻断优化持续延迟
  首次真实建模或突破已授权启动预算。

### 运行基线与证据冻结

- 在 Modeling Agent 开始真实语义工作前，可以修改、测试并重新冻结 R2.3-001 资产或直接相关
  平台实现；该阶段的失败和修改不消耗 fresh semantic modeling start；
- 每次 semantic start 必须记录 Runner、Codex Adapter、Profile、Agent Packages、Skills、Task、
  业务输入和相关平台代码的精确版本或 hash；
- semantic start 后不得向运行中的团队热替换上述资产或平台代码；
- 影响 Agent 行为、通信、权限、资源生命周期、平台写入或语义查询的修改必须终止并保留当前
  尝试证据；修改完成并通过对应测试后，使用重新冻结的基线和 fresh start 验证；
- 纯文档、测试说明或不影响运行行为的留证改进不要求重新启动真实建模；
- R2.3-002 的最终 PASS 必须绑定最终交付基线；取得 PASS 后再修改运行行为时，原 PASS 不能作为
  修改后基线的真实验收证据。该优化必须暂缓，或者在用户授权的剩余或新增启动预算内重新验收。

### Agent-visible 输入与隔离

R2.3-002 复用 R2.3-001 已验收的外层 bubblewrap namespace、角色私有 staged 输入、
Package/Skill 装载、禁止挂载宿主仓库和 Protocol-only MCP，不建设第二套隔离或 staging 机制。
在该机械边界上增加真实建模场景合同：

- 每个角色只看到本轮 Profile、自己的 Agent Package、Required Skills/references、Task、完整
  roster，以及 L3 冻结来源包中明确分配给该角色的 Agent-visible 文件；
- 冻结 manifest 为每个可见文件记录稳定路径、输入分类、来源版本和 SHA-256，并与本次
  semantic start 的基线共同留证；
- 每个 Agent 使用全新 Session，不继承当前交付会话、L3 Session、父会话历史或其他 run 上下文；
- 不挂载或暴露宿主仓库根目录、需求/设计/测试/交付文档、历史运行目录、旧本体、Modeling
  Batch、答案型查询结果、rollout 和 tester-only 目录；
- 冻结业务答案只有在 Coordinator 提问后，才通过本轮用户消息逐项进入允许输入；
- Runner newline-delimited outer control 的用户输入信封固定为
  `{"action":"user","text":"<verbatim answer>"}`。Delivery controller 必须使用确定性编码
  生成该对象，并在真实 producer 前以无模型测试证明 stdin -> JSON decode -> `receive_outer` ->
  Coordinator `outer-user` delivery；不得手写未定义的 `type=user_message` 等替代信封。错误 action
  必须 fail fast，且不得把一个业务答案重复释放；
- 合法 outer 信封不等于答案已获授权释放。每次真实发送前，Delivery controller 必须先观察本轮
  Modeling 当前 grounded question 及 Coordinator prompt，记录 question `delivery_id`、原文和唯一
  frozen answer ID 的匹配，确认本轮 `outer-user` 尚未包含该答案且没有其他未被提问的答案释放，
  再发送预生成 JSONL 一次。发送后必须保留 question -> outer-user -> Coordinator correlated
  forward 的直接证据；重复 prompt 不得触发第二次答案；
- 运行期间不得临时联网补充业务资料。若冻结来源不足，应停止并形成新的输入版本，不在原
  semantic start 中浏览或混用新资料；
- 模型 Provider 通信以及 Protocol 对本地 Semantic Platform MCP 的访问不受业务资料网络限制；
- 第一个 Agent turn 前执行角色级可见性和禁止项探针；探针通过后才允许 Modeling 接收真实业务
  资料并开始计入 semantic start。

相对于 R2.3-001，以上新增内容只保护真实业务来源忠实度、历史答案隔离和建模质量证据；它不改变
001 已接受的 Runtime、namespace、Skill 装载或角色权限合同。

### 协作证据、失败分层与投入边界

- Coordinator 必须完成初始任务分配，并在 Modeling 和 Protocol 工作期间持续响应用户；
- 真实协作证据至少包含 Modeling 直接发送给 Protocol 的业务语义、候选或约束内容，以及
  Protocol 对机械协议结果或需要语义修正的问题直接返回相关 Agent；单纯健康检查消息不能证明
  真实建模协作；
- 用户补充信息仍通过 Coordinator 原样进入相关 Agent，Coordinator 不审批候选或代替 Modeling
  修改专业结果；
- 只有 Protocol 调用平台写 MCP。Runner 或交付侧可以执行作用域、凭据、证据和清理机械操作，
  但不得生成 Modeling Items、修复语义或替 Agent 判断业务答案；
- 一次运行的主失败必须稳定归类为 `modeling-quality`、`platform-contract`、
  `collaboration/routing` 或 `runtime/infrastructure`；后续 cleanup 失败作为附加事实保留，不覆盖
  最先阻断原建模目标的原因；
- 机械格式问题由 Protocol 处理；平台状态冲突必须重新读取或停止；语义冲突退回 Modeling；
  需要新业务事实时才由 Coordinator 询问用户；
- 只验收真实运行中自然出现的错误路由，不为未出现的错误建设故障注入矩阵或专用验收程序；
- 交付记录必须分别统计语义建模与基础设施、harness、评审和文档时间。若语义建模少于有效投入
  的一半，暂停扩展并提出更小的继续路径。

### 用户问题与回答

- 复用 R2.2-001 L3 已冻结的三项业务缺口答案，但在运行开始时继续归类为
  `tester-only`，不得进入 Agent-visible 来源、Task、Profile、Agent Package 或历史 Session；
- 只有建模团队根据可见资料识别出会实质改变模型或业务查询的问题，并由 Coordinator 向用户
  提问后，外层调用方才机械匹配并逐项原样回复对应答案；
- 问题一次只释放一个答案；未被团队识别和询问的缺口不得主动提示，也不得补充建模建议、
  隐藏验收条件或答案型结构；
- “业务方无法确认”必须原样回复，由建模团队决定如何表达可查询的显式未知；
- 已释放的原始问题和回答成为本轮允许的场景输入并保留可复核证据，但冻结答案集合和匹配逻辑
  不是 Team Runner、Profile、Agent Package 或 Agent Skill 的依赖。

### 业务语义与检索完成门

R2.3-002 复现 R2.2-001 L3 已接受的语义与检索结果，不提高业务难度：

- B 调用 C 的 Latest published Version，Current Draft 作为独立状态保留且不混入当前发布链；
- `quality_rating:number` 是 `quality_score:number` 的后继表达，两代字段及其连续性均可读取；
- 缺失数值评分时 B 的行为保持为业务方无法确认的可查询显式未知，不由 Agent 或平台补造；
- 现有通用查询从当前平台事实返回完整已发布 `C -> B -> A` 路径、相关版本、字段连续性、
  显式未知、Evidence/lineage 和无静默截断的完整性状态；
- 关键事实能够追溯到本轮冻结的 Agent-visible 来源或已释放的用户原始回答；Evidence、
  Agent rationale、用户回答和显式未知保持可区分；
- Protocol 提交的每个不可变 Modeling Batch 都先完成 `dry_run`，只有同一内容才可
  `apply_atomic`；最终 workspace version 前进，validation `conforms=true`，reasoning
  `consistent=true`；
- 复用 L3 的 Shape 负例，要求其在 `dry_run` 被拒绝且不改变 workspace；
- 不增加新业务问题、自动 Judge、独立 Consumer、mutation、重复建模、Profile 质量对照或
  Runtime 横向比较。

### 尝试预算与启动门

- R2.3-002 初始授权两次 fresh semantic modeling start；该预算是硬边界，耗尽后必须停止并
  请求新的用户授权。2026-07-31 在前两次分别以 `platform-contract` 和
  `collaboration/routing` 失败且均未形成完整建模质量结果后，用户明确追加授权两次，当前累计
  上限为四次；随后第三、第四次仍以 `collaboration/routing` 失败且未形成完整应用/验证结果，
  用户再次明确追加授权两次，将累计上限提高为六次；第五、第六次随后均因隔离 Protocol MCP
  实际仍运行于 `SEMANTIC_PRODUCT_WRITE_MODE=legacy_only` 而以 `platform-contract` 失败，且未形成
  完整应用/验证结果。用户第三次明确追加授权两次，将累计上限提高为八次。第七、第八次继续在
  平台写入前暴露受控的 `platform-contract` 缺陷，均未形成完整建模质量结果；Round 21 已独立
  证明对应 Protocol mechanics/Build Session 修复。用户第四次明确追加授权两次，当前累计上限为
  十次。第九次因外层控制误用了未定义的 `type=user_message` 信封而以
  `collaboration/routing` 失败；Round 24 已独立证明正确的 `action=user` 信封和问题相关性门。
  第十次完成三项用户问答、四轮候选修正、正式 Batch 应用、Shape 负例、validation 和 governed
  query，但隔离 Protocol MCP 未配置 `SEMANTIC_REASONER_COMMAND`，因此 reasoning 失败并以
  `runtime/infrastructure`、`complete_modeling_quality_result=false` 终止。当前十次预算已耗尽。
  2026-08-01 用户明确变更授权合同为“本次任务直到完成无需再次授权”。从该指令起，Delivery
  Agent 可以基于这一份持续授权按固定 `+2` tranche 机械扩展本地账本上限，无需每两次再次
  中断并询问用户；每个 tranche 仍必须使用唯一 ledger authorization ID/reference 并绑定这份
  持续授权及 tranche 序号，不得一次写入无限额度或绕过 start 计数。任务完成、用户撤回授权或
  R2.3-002 终止时该持续授权立即失效。每个 tranche 只能在同一账本锁内确认当前
  `semantic_start_count == current_cap` 后追加；追加后任何同步或并发的下一 tranche 必须因当前
  cap 尚未耗尽而拒绝。账本读取也必须按顺序重放并拒绝未消费前一 tranche 就出现的后续授权；
- Modeling Agent 第一次收到真实业务资料并开始语义工作时计为一次 start；在任何 Agent 开始
  语义建模前失败的确定性配置、权限、平台健康或 Runtime 预检不计入；
- Codex 运行路径必须在账本 reservation、Project/key 创建和 run 目录创建前确认宿主
  `CODEX_HOME/auth.json` 是可用的普通文件；缺失时以 `runtime/infrastructure` 预检失败返回，不得
  复制其他工具凭据、依赖当前外层会话的隐藏认证或先创建临时平台资源；
- 每次计数的 start 都必须使用全新的 Runner run、Agent Sessions、运行目录、Project、
  Ontology、Build Session 和 Lease；失败作用域不得被下一次 start 复用；
- 同一 start 内，Protocol 处理不改变语义的机械协议问题，以及 Modeling Agent 根据
  `dry_run`、validation、reasoning 或查询反馈修正本轮候选，不产生新的 start；
- 初始第二次以及后续 start 只用于上一计数 start 因已定位的
  `runtime/infrastructure`、`platform-contract` 或 `collaboration/routing` 窄层故障而未形成
  完整建模质量结果，并且必须保留上一轮原始证据、修复对应窄层、通过独立测试并绑定新的冻结
  baseline；
- 如果一个已绑定 repair baseline 的 reservation 在 `semantic_start` 前失败并有 append-only
  `presemantic_release`，该 run 不计入 start 且 run ID/目录不得复用。允许责任方通过同一受控
  repair CLI 为原 semantic failed run 追加一个新的 baseline 绑定，但仅当：上一 repair 已被
  恰好一个 reservation 使用；该 reservation 从未 `semantic_start`；已有 release；新 baseline
  非空且不同。每次重新绑定仍须使用 fresh run ID、重新通过独立窄修复证据和 20 分钟门；未使用
  的 repair、未释放/已 semantic-start 的 reservation、错误前序或并发重绑必须 fail closed；
- `presemantic_release` 对同一 reservation 是 append-only 幂等操作；重复 cleanup 不得追加多条
  更正记录，也不得改变首次失败原因。历史上已存在的重复 release 仍可读取，但不能授权额外
  start 或放宽上述 rebind 条件。release 是该 reservation 的不可逆终态：其后任何迟到的
  `mark_semantic_start` 必须 fail closed；release 与 semantic-start 并发时在同一文件锁下只能
  一个成功，绝不允许同一 run 同时具有有效 release 和后续 semantic start；
- 第七次及其后的隔离 Protocol MCP 必须在 Runtime 启动前通过固定 allowlist 运行合同直接绑定
  `SEMANTIC_CANONICAL_STORE=rdf`、`SEMANTIC_PRODUCT_WRITE_MODE=rdf_primary` 与
  `SEMANTIC_READ_MODE=canonical`。三项名称和值必须进入 baseline manifest；实现不得读取、复制
  或哈希整个外层 `os.environ`，不得把三项变量注入 Coordinator、Modeling 或 Codex app-server
  通用环境。systemd manager 或常驻服务的环境不得替代对隔离 MCP 子进程的实证。独立预检
  必须复用生产 Codex Adapter 的同一 Protocol MCP launch-spec 构造器、私有 config 渲染与
  namespace command 启动真实 app-server/MCP 路径，并完成一个可清理的最小 Modeling Batch
  `dry_run=validated`；不得另写一个仅复用相同 dict 的旁路 subprocess 代替生产路径；
- 第七次 start 已证明固定 canonical mode 生效，但冻结的 `public-protocol.md` 要求读取
  `/opt/mechanics-contract.json`，而生产 namespace 未提供该路径；Protocol 在未写平台前
  以 `platform-contract` 失败，empty scope 已删除。第八次也是当前最后一次可用 start，只有在
  独立测试证明 R2.2 L3 已接受的无语义 mechanics contract 由 run-owned、无可写别名的 host
  staging 以只读方式仅挂载给 Protocol 后才可授权；不得把该文件放入可写的 Agent home，
  不得向 Coordinator/Modeling 暴露，也不得借机加入业务语义、tester-only 答案或 secret；
- Protocol-only Round 17 进一步证明，仅有 bwrap 只读挂载仍不足：Codex Adapter 的动态
  `cat` callback 必须允许当前 v2 Protocol 读取该唯一虚拟路径。callback 直接在 host 读取，
  因此必须同时绑定当前 run root、已登记的同一 Agent 实例、精确 raw/real path、无 symlink、
  regular file、`0444` mode 和由 canonical helper 加当前 run ID 生成的 SHA-256；读取与校验必须
  在同一 file descriptor 上完成。不得开放整个 `/opt`，不得只信 Agent 字段或先验路径检查；
- 上述 Protocol-only 预检是机械分层证据，不要求模型在无 Modeling candidate 时主动选择
  `exec`。同一个生产 Adapter/Protocol roster 必须分别证明：真实 bwrap namespace 中唯一挂载
  可读且不可写；生产 callback 对同一已登记 Agent 返回 canonical 当前-run bytes 并对负例
  fail closed；同一真实 app-server 通过原生 MCP RPC 完成 `dry_run=validated`。三层必须使用
  同一临时 scope/config 并完整清理，但不得把 callback 白盒证据冒充为模型行为证据；
- 第十次 start 证明宿主 `backend/.env` 的推理器配置不会进入隔离 MCP 子进程。下一次 producer
  授权前，生产 Codex Adapter 必须只为 schema-v2 Protocol 将已接受的
  `backend/scripts/dev_owl_reasoner.py` 以精确单文件只读方式挂载到
  `/backend/scripts/dev_owl_reasoner.py`，并由同一 Protocol MCP launch spec 固定注入
  `SEMANTIC_REASONER_COMMAND=/backend/scripts/dev_owl_reasoner.py` 和
  `PATH=/backend/.venv/bin:/usr/bin:/bin`，确保脚本的 `/usr/bin/env python3` 只解析到已挂载且
  包含 `rdflib` 的 backend venv。不得挂载 `backend/scripts/`
  目录、读取或复制宿主 `.env`/ambient environment，也不得向 Coordinator、Modeling、v1 或
  Codex app-server 通用环境暴露这两个变量。baseline 必须同时绑定脚本内容 hash 和精确
  reasoner/PATH 变量合同。独立预检必须通过生产 Adapter、私有 config、真实
  bwrap/app-server/MCP 路径，在全新
  可清理临时作用域实际执行一次 `run_semantic_reasoning` 并直接观察 `status=succeeded`、
  `consistent=true`，随后证明零残留；不得使用或改变第十次保留的失败作用域，也不得把常驻
  backend 的健康或旁路 subprocess 成功当作该子进程合同的证明；
- 第十一次 start 的平台写入证明：当前 create-only 公共合同在 Shape 激活后会立即对后续 Batch
  执行 SHACL 校验，因此依赖实体属性或关系断言的 Shape 不得先于对应实体和关系应用。Protocol
  必须保持 Modeling 候选语义不变，并按平台通用拓扑顺序拆分不可变 Batch：先 class，再 property/
  relation type，再 entity；重新读取并绑定平台生成的实体 IRI 后创建 relation；只有目标实体、属性
  与关系断言均已存在后才创建依赖它们的 Shape。每个阶段仍须独立 dry-run 后 apply，workspace
  version 与输出 ID/IRI 只从前一阶段正式 receipt/重读绑定。Protocol 不得用重排候选内部业务含义、
  删除/停用已应用 Shape、放宽校验或把精确 Item 编写委托回 Modeling 来规避该顺序；不能满足依赖时
  必须在首次危险 Shape 写入前返回机械冲突；
- 第十二次 producer 启动前，独立无模型 Protocol-only 预检必须经生产 Codex Adapter、真实
  bwrap/app-server 与原生 MCP RPC，在全新临时作用域按上述顺序实际应用一个含关系依赖 Shape 的
  最小平台通用模型，并直接证明最终 validation 成功。预检必须释放 Lease、取消 Session、撤销 key、
  删除 Project 并证明零残留；不得读取业务来源、写 StartLedger、启动 Producer 模型或改变第十一次
  保留失败证据；
- 第十二次 start 已证明跨 Batch 顺序修复生效：class、vocabulary、entity、relation、Shape 均正式
  应用，Shape 负例拒绝且 workspace 不移动，reasoning 成功一致；但 Protocol 将 MCP 暴露的无枚举
  `validation_scope:string` 猜为 `all` 后被服务拒绝，因此 validation、governed query 和 Session
  completion 未完成。该轮以 `platform-contract`、`complete_modeling_quality_result=false` 终止；
- 下一次 producer 前，Protocol 可见的平台通用合同必须明确绑定正式后端允许值：
  `asserted_only` 或 `asserted_plus_reasoning`，不得使用其他值。当前分离执行 validation 与 reasoning
  的流程显式使用 `asserted_only`；只有需要把正式 reasoning result graph 纳入同一次验证且已从正式
  receipt 绑定其 graph IRI 时才使用 `asserted_plus_reasoning`。缺少所需 reasoning graph IRI 时必须在
  调用前返回机械冲突，不得猜测 scope 或 graph。独立无模型生产 Protocol 预检必须分别证明
  `asserted_only` 成功、非法 `all` 被拒绝，并完成零残留与 ledger/第十二次证据不变检查；
- 第八次 start 在三层预检通过后仍于首次 `create_build_session` 前失败：Protocol 把 Runner 的
  `run_id` 和自定义 phase/workspace 字段放入 `initial_checkpoint`。平台授权层会递归把嵌套
  `run_id` 当作受保护资源 ID，因无法解析 owner 而返回 `forbidden_scope`；即使越过授权，该对象
  也不符合 `InitialBuildCheckpoint` 的正式 schema。该次没有创建 Session、Lease 或 Batch，empty
  scope 已删除，累计八次 start/三次追加授权已经耗尽；未经新的用户明确授权不得继续 producer；
- 修复不得放宽后端授权或跳过冻结生命周期。v2 Protocol 必须以 `initial_checkpoint=null/omit`
  创建 Session，再调用正式 `save_build_checkpoint`：初始 checkpoint 使用 `<run_id>-initial`、
  最新 revision、合法 `phase=modeling` 与固定 modeling/validation step；完成 dry-run、应用、
  validation、reasoning 和查询后，必须以 `<run_id>-final`、最新 revision、合法 `phase=handoff`
  保存最终 checkpoint，再用其返回 revision 完成并重新读取 Session。`save_build_checkpoint` 只可
  加入 v2 new-scope Task 的 Protocol 工具面，不得扩大 v1/default 工具面；
- 新预算授权前，独立 Protocol-only 预检必须先以非法嵌套 `run_id` 复现拒绝且证明零 Session，
  再用 fresh client session 完成 create(null) -> initial checkpoint -> acquire lease -> 最小
  `create_class` dry-run validated -> final checkpoint 的两段 revision 链，并完成 release/cancel、
  key/project 清理和数据库零残留。该确定性预检不交付业务来源、不启动模型、不写 StartLedger；
- 2026-07-31 Protocol-only Round 21 已满足上述门：真实 app-server/MCP 观察到非法 create
  `forbidden_scope` 且零 Session，正确链路依次得到 Session revision 1、初始 checkpoint revision
  2、`dry_run=validated`、pre-final Session revision 2、最终 checkpoint revision 3、completed
  revision 4，并完成 Lease 释放、API 404 与数据库零残留。账本保持八次 start/三次追加授权；
  该 PASS 只解除机械预检门；用户随后已明确授权新的两次 start，须先通过上限十次/第四次授权
  的账本变更评审、实现与独立测试，才可冻结第九次 baseline；
- Modeling 不得仅凭“按 Workflow identity 配置”“存在 published latest”或“没有记录 B 的单独
  deployment”推断 B 当前解析到 C Version 2。只有 Coordinator 就 Tool 绑定/升级语义提出有依据
  的业务问题并收到已释放原始回答后，候选才可断言 `resolvesToPublishedVersion=c:v2`；否则必须
  保留为显式未知，且不得宣称对应 consumer question 已回答；
- 如果一次 start 已形成完整建模结果但未通过业务语义与检索完成门，必须按
  `modeling-quality` 失败停止；不得自动使用第二次机会修改 Prompt、Skill、冻结答案或验收门
  重刷结果；
- 在后续实施轮完成需求、输入和运行基线冻结后，必须在 20 分钟内启动第一次真实语义建模；
  未达到该门时停止、报告时间消耗并缩减准备工作，不继续扩建 harness。

### 作用域、Session 终态与清理

- 成功运行在所有 Modeling Batch Attempts 收敛后，将 Build Session 显式完成为 `completed`，
  释放 Lease，撤销临时 Project key 和 org-admin key，停止全部 Runtime 并销毁本地秘密；
- 成功运行创建的非空 Project/Ontology 是 R2.3-002 的有意保留结果。Runner 可以完成机械
  `CLEANED`，同时记录 `scope disposition=retained`；不得把预期保留报告为删除失败或资源泄漏；
- 失败运行若作用域仍为空，Runner 按 R2.3-001 的精确所有权规则删除 Project/Ontology；
- 失败运行若已经发生平台写入，Runner 不自动删除非空 Project。封存失败证据后，由交付或独立
  测试侧根据精确所有权删除该失败 Project，并保留直接删除结果；
- 失败 Build Session 只有在不存在 `applying` 或 `recovering` 的 in-flight Attempt 后，才可显式
  `cancelled` 并记录失败原因和未解决事项；不得仅等待 Lease 过期代替 Session 收尾；
- 存在 in-flight Attempt、所有权不明确、资源身份或目标 workspace 漂移时停止删除并报告
  blocker，不猜测目标或强制清理；
- 无论 Project 最终保留还是删除，临时凭据、本地秘密和 Agent Runtime 都必须按本轮精确所有权
  完成清理；
- 成功 Project/Ontology 按原合同保留；原定“交给 R2.3-003 并在其验收后删除”的安排已被当前
  R2.3-003 Start75 existing-scope 合同 supersede。该对象继续作为 R2.3-002 证据保留，删除需未来
  明确授权。

### Scope handoff 与漂移检查

- R2.3-002 在成功 Build Session 完成并取得最终平台状态后，发布一份不可变、非敏感的
  scope handoff；
- handoff 只记录 R2.3-002 run ID、Project ID、Ontology ID、最终 workspace version 和
  `scope disposition=retained`；
- handoff 不复制模型摘要、业务问题答案、Agent 对话、Prompt、tester-only 内容、凭据或平台
  历史记录，也不重复记录清理责任；
- 成功 Runner 的内部 `retained-handoff-input` 可以接收 `PlatformScope.cleanup()` 返回的完整机械
  清理 evidence，但必须要求七个正式输入字段存在且类型正确，同时要求
  `mode=create`、`sessions_terminal=true`、`protocol_key_revoked=true` 与
  `admin_key_revoked=true`；任一清理确认缺失或不为真都必须 fail closed。仅把 run ID、三角色 completed
  状态及 `project_id`、`ontology_id`、`workspace_version`、`completed_session_id`、
  `scope_disposition`、`owned` 写入不可变文件。`mode`、Session/key 清理状态或任何其他额外字段
  既不得导致首次真实成功 cleanup 失败，也不得进入 handoff 输入；缺少正式字段、非 owned/
  非 retained 状态、非三角色 completed 或目标文件已存在仍须 fail closed；
- 该 handoff 的身份与漂移规则继续作为历史合同和可复用模式保留，但当前 R2.3-003 不消费它；
  R2.3-003 使用 Start75 新发布的 handoff，并按自身章节执行同等级 live 漂移检查。

### 独立 Agent 验收

- 生产真实证据的建模团队全部 settled、Runtime 停止并封存证据后，才启动一个全新 Session、
  不继承父会话或建模团队历史的独立验收 Agent；
- 独立验收 Agent 不是 Team Run roster 成员，不创建或继续建模 run，不向建模 Agent 释放答案，
  不持有平台写凭据，也不修改保留的 Project/Ontology；
- 验收 Agent 获得 R2.3-002 冻结需求、业务语义与检索完成门、tester-only 验收合同、精确运行
  基线、封存的原始 Runtime/Agent 事件、平台 receipts、查询结果和清理证据；
- 验收 Agent 可以通过独立只读权限补充查询当前保留作用域；补充结果必须追加到验收证据，不得
  触发 Modeling Batch、Build Session、Lease 或其他写入；
- 验收必须直接核对具有真实语义内容的 Modeling 与 Protocol 通信、Protocol MCP 调用、不可变
  Batch 的 dry-run/apply receipts、Shape 负例、validation/reasoning、通用查询、来源与
  Evidence/lineage、Session/Lease/凭据收尾和 scope handoff；
- 验收 Agent 对每项完成门给出 `PASS`、`FAIL` 或 `INCONCLUSIVE`，引用具体平台事实或原始证据；
  主交付 Agent负责最终裁决和问题分层；
- 不编写新的硬编码 Judge、Consumer、mutation、答案型断言程序或场景专用判分器。确定性脚本
  只允许收集、封存、hash 和校验机械证据完整性，不得根据预设本体结构、路径或固定答案替代
  Agent 的语义评估；
- Runner 汇总只作为证据索引，不能替代原始证据。缺少必要证据时记录 `FAIL` 或
  `INCONCLUSIVE`，不得创建、继续或修改原运行补证。

### R2.3-002 最小完成门

1. 使用全新 Runner run、Agent Sessions、Project、Ontology、Build Session 和 Lease。
2. 基础三 Agent Profile 完成真实业务切片，只有 Protocol 执行平台写 MCP。
3. 用户可以在建模期间继续与 Coordinator 对话并提供明确补充信息。
4. 正式 Modeling Batch 和通用查询满足上述业务语义与检索完成门。
5. Runtime、Build Session、Lease、临时凭据和 Project/Ontology 按上述成功保留与失败清理合同
   完成收尾。
6. 生成满足上述最小字段和漂移检查合同的 scope handoff。
7. 自动化回归、真实运行和上述独立 Agent 验收 PASS。

### R2.3-002 非目标

- existing 模式真实增量建模；
- 新增 Agent 的质量效果；
- Pi Runtime；
- 场景专用 launcher，或复制 Team Runner 已有的 Session、消息、凭据、作用域、清理和留证逻辑；
- 把所有发现的非阻断优化都升级为 R2.3-002 完成门；
- 把测试业务概念写成平台专属 API、Schema 或解释逻辑。

### R2.3-002 Round 50 活动修订：P2 真实边界、检索合同与证据绑定

本节记录 Round 50 的活动基线，修订并替代此前把 P2 文字化为“绝对零作用域/零 key”的表述；
此前 Round 及其测试历史保留不改。Round 51 在本文后部进一步 supersede 本节的 P2 路径与删除
清理条款，但保留本节的 schema、digest、baseline、外部绑定与顺序合同。P2 仍不是 R2.3-002
业务 semantic start，也不产生可保留的产品作用域。

#### P2 最小真实运行边界

- P2 不得读取或交付 R2.3-002 业务来源，不得创建 R2.3-002 StartLedger reservation 或写入
  `semantic_start`，不得保留 Product/Project/Ontology 作为交付结果；P2 运行失败或清理问题不
  得消耗 R2.3-002 fresh semantic modeling start；
- P2-monitor 为了真实执行 foreground CLI、TeamRunner、Codex Adapter、app-server、Team
  Transport/Broker、MCP 和 settlement，最多可以创建一个精确归属、不可复用的 ephemeral
  Project/Ontology、bootstrap-admin/read/model-or-Protocol key、Build Session 和 Lease。P2-
  Protocol 不运行 TeamRunner；它只使用生产 Adapter/Transport/stdio/bwrap/app-server/native
  MCP path，且两条路径都只有在真实路径实际需要时才创建资源，不得用旁路 subprocess 或
  in-process mock 代替；
- P2 在删除 ephemeral Project 之前必须先冻结第一阶段非敏感 evidence artifact：其中覆盖每个
  project-scoped read/model/Protocol key 的精确 ID、`revoked_at` 和 non-active 状态、已取消的
  Session、Lease 已由 cancel atomically auto-released、资源 ownership、cleanup receipts，以及
  no in-flight Attempt 证明。artifact 还必须记录 org-scoped bootstrap-admin key 的精确 ID 与
  `ACTIVE` 状态，明确它
  仅用于即将进行的 authenticated Project DELETE，因此不计入第一阶段 non-active assertion；
  必须使用该仍 active 的 org-admin credential 发起正式 DELETE。随后验证 Project/Ontology 不
  存在、project-scoped active residual count 为零并记录既有 FK cascade 行为；立即 revoke 该
  org-admin key，冻结第二阶段 artifact，记录其精确 ID、`revoked_at`、non-active 状态和保留的
  org-admin revoked audit row。最终 aggregate cleanup evidence 合并两阶段并证明每个 created
  key 最终均为 non-active。不得新增 deletion credential、direct DB delete 或 hard-delete；也不
  新增 migration、archive、detach 或通用 history-retention productization。project-scoped
  key/Session/Lease rows 可按现有 foreign-key contract cascade-delete，不要求删除后保留；
  `project_id=NULL` 的 org-scoped bootstrap-admin revoked audit row 必须保留，永不得 hard-delete。
  验收同时要求精确的删除前/删除后 evidence，以及删除后 Project/Ontology 不存在、active
  Project/Ontology/Session/Lease/key residual count 全为零；
- 现有“P2 创建任何作用域或 key 即失败”的旧句只在历史测试轮中保留；当前 P2 以本节的真实
  边界为准。

#### Modeling/Protocol 候选与原生 proof 合同

- Modeling 的平台中立 required assertion item 字段集合固定为
  `graph_role, subject, predicate, object, object_kind, object_datatype, object_language`；其中
  `graph_role` 必须为 `asserted_data`，datatype/language 必须是 string 或 JSON `null`。不得出现
  `source_graph_iri`、任何平台 IRI/ID、fact ID、workspace version 或 receipt 字段；Delivery 不
  选择 assertions；
- canonical JSON 固定为 Python `json.dumps(value, ensure_ascii=False, sort_keys=True,
  separators=(",", ":"))` 的 UTF-8 bytes，无空白。Items 按各自 canonical JSON UTF-8 bytes
  字典序排序，重复 canonical bytes fail closed。`semantic_digest` 输入固定为
  `{"schema_version":"candidate-required-assertions/v1","statements":[sorted items]}`；
  `candidate_digest` 输入固定为包含实际冻结值的 canonical object
  `{"schema_version":"candidate-required-assertions/v1","candidate_revision":<string>,
  "delivery_id":<string>,"reply_chain":[<delivery IDs in order>],"semantic_digest":<hex>}`；
  reply chain 保持实际 delivery 顺序，不得排序；
- Protocol 只有在正式 workspace receipt/read 完成后，才把 `graph_role=asserted_data` 解析为
  最终 `source_graph_iri`，生成 materialized quad。Materialized quad 字段固定为
  `graph_role, source_graph_iri, subject, predicate, object, object_kind, object_datatype,
  object_language`；按相同 canonical JSON bytes 排序。`materialized_digest` 输入固定为
  `{"candidate_digest":<digest>,"quads":[sorted materialized quads]}`。Protocol 计算 fact ID，
  Modeling 不提供；三种 digest 必须可重算且不得漂移；
- 原生 proof 的顶层字段集合严格固定为以下十个且不得有 `proof` wrapper 或额外字段：
  `mode`, `initial_modeling_context`, `final_modeling_context`, `workspace_context`,
  `batch_inventory`, `batch_details`, `entities_read`, `statements_read`,
  `candidate_required_assertions`, `statement_lineage`；
- `candidate_required_assertions` 是严格 object，字段集合固定为
  `schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
  items, materialized_digest, materialized_quads`；items 和 materialized_quads 必须非空并按上
  述规则排序。`statement_lineage` 是严格 object，字段集合固定为
  `schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
  materialized_digest, max_depth, records`；`max_depth` 只能是 `0..5`。每个 record 字段集合固定
  为 `fact_id, quad, response`；response 必须保留未投影的完整 `{ok:true,data:<object>}` lineage
  MCP envelope，且一条 record 与一个 computed fact ID、一个 materialized quad、一个 lineage
  response 一一对应；
- wrapper 和 verifier 必须拒绝 nested 缺失/额外字段、空 items/records、重复 quad/fact ID、
  extra/unbound lineage、错误 graph/Ontology、fact/quad 不匹配、revision/reply-chain/digest
  漂移及 `max_depth` 越界。`mode=create` 的 vacuous proof 必须拒绝。只有真实完成的
  ontology-scoped `query_semantic_context` 进入 `fallback_required` 后，后续完成的 native
  verifier `mode=create` 才能给出 `complete=true`；direct generic `complete=true` 是另一条合法
  producer 成功路径，不要求同时具备两者。

#### P2 真实顺序、外部绑定与 monitor baseline

- P2-Protocol 的直接证据顺序固定为：真实 Modeling synthetic candidate delivery -> Protocol
  correlated receipt/reply -> platform materialization/reads -> real completed eligible
  ontology-scoped `query_semantic_context` item -> sanitized runtime state `fallback_required` ->
  later native verifier `mode=create` `complete=true` -> Broker terminal guard/report acceptance ->
  Protocol runtime cleanup。P2-Protocol 不得声称或伪造 Modeling terminal、Runner
  `terminal-result-handoff`、ack 或 all-three settlement；verifier-before-query、没有
  `fallback_required` 的 direct verifier、terminal-handoff-before-verifier、或手工
  `sender_id='runner/terminal-result'` 均为 FAIL；
- 独立 P2 observer 必须把 nested candidate 的 `delivery_id`、reply chain、candidate_revision、
  semantic_digest、candidate_digest 与 raw Team Transport/Broker Modeling envelope 和 Protocol
  receipt 逐项对比，只保留安全 digest/ID。自洽但不匹配 Broker 原文的新 ID/digest 不是证据；
- P2 必须观察真实 app-server query item 及 sanitized retrieval-state transition；仅直接调用
  native verifier 不构成 acceptance evidence。若真实 producer 走 direct generic complete path，
  该路径仍可按独立完成门验收；P2-Protocol 只覆盖上述 fallback 到 Broker terminal guard/report
  acceptance，最终 fresh Producer 才负责证明 `Modeling terminal -> real Runner
  terminal-result-handoff -> Protocol terminal -> all three completed+settled`；
- 持久 monitor 的稳定实现文件固定为 `modeling_team/foreground_monitor.py`，合同描述文件固定
  为 `modeling_team/references/p2-monitor-contract.json`。两者 SHA-256 以及依赖的 CLI/runner
  call sites（`modeling_team/runner.py` 的 `TeamRunner.prepare/start/_baseline_manifest` 与
  terminal handoff/settlement、`modeling_team/runtimes/codex.py` 的
  `CodexRuntimeAdapter.start_roster/start_task`、`modeling_team/transport_mcp.py` 的
  `TeamTransportBroker.send/report/ack_terminal_handoff`）必须进入 `_baseline_manifest`；
  任一 omission/addition/byte drift fail closed。monitor command/argv/lifecycle 只能从该稳定
  descriptor 读取。Descriptor v1 的固定字段和值为：`schema_version="p2-monitor-contract/v1"`、
  `command="uv"`、`argv=["run","--project","backend","python","-m",
  "modeling_team.foreground_monitor","--contract",
  "modeling_team/references/p2-monitor-contract.json"]`、
  `required_stages=["monitor_started","foreground_started","parent_pm_boundary",
  "agent_terminal_settled","secret_absent","monitor_stopped"]`、
  `parent_pm_boundary_count=1`、`evidence_mode="append_only_run_local"`、
  `secret_targets=["auth.json","config.toml","temporary_credentials"]`、
  `resource_policy="at_most_one_owned_ephemeral_scope"`。不能使用没有路径的脚本哈希泛称；
- 同一 prospective fresh run ID、同一稳定文件集必须在 reservation/start 前计算两次完整
  baseline manifest/hash；两次计算均不得写 ledger、创建作用域、读取 fixture/evidence/PID；完整
  entries/hash 必须 byte-for-byte 相同。Stable baseline 只包括上述 code/descriptor/schema，不
  包括 ephemeral fixture、evidence、credential、descriptor FD 或 PID。

Round 50 不改变 fixed `runtime/infrastructure` terminal classification/mandatory closeout、
P2 PASS 在 tranche 8 之前、Phase A 在 handoff 之前以及 F1 不切换 Terra/xhigh 的顺序合同。

### R2.3-002 Round 51 活动修订：P2 路径拆分、删除前证据与 Session 收尾顺序

本节是当前可执行合同，修订 Round 50 中把两条 P2 路径合并、以及把项目作用域行保留误写为
通用历史保留的部分。Round 50 的候选 schema、digest、baseline、外部 envelope 绑定、fallback
顺序、`runtime/infrastructure` closeout、P2 在 tranche 8 之前和 Phase A/handoff/Phase B
顺序均继续有效；本节不授权任何代码、运行时、ledger、key、Session 或 delivery-record 变更。

#### 两条相互独立的 P2 路径

- **P2-monitor（monitor-only）。** 使用既有 schema-v1
  `modeling_team/profiles/base-three-agent.yaml` 与
  `modeling_team/tasks/base-capability-smoke.yaml`，由
  `modeling_team/foreground_monitor.py` 启动真实 foreground CLI，并贯穿
  `TeamRunner`、`CodexRuntimeAdapter`、app-server、Team Transport/Broker、`TeamRunner.drain()`、
  terminal-result-handoff、ack、all-agent settlement 与 cleanup。它是唯一证明真实
  `TeamRunner.drain()` terminal-result-handoff/ack/all-agent settlement 的 P2 路径，只证明
  parent-PM boundary、process persistence 与 secret cleanup，不测试 `fallback_required` 或
  native verifier。若当前 CLI 的真实机械路径确实需要 platform state，可创建并清理一个有明确
  ownership 的 ephemeral mechanical scope；不得读取 R2.3-002 business sources，也不得产生
  R2.3-002 StartLedger event。
- **P2-Protocol（protocol-only）。** 不得运行 TeamRunner，也不得调用
  `modeling_team run`。按既有 Round 27/32 fixture 的真实生产方式，构造 schema-v2 的
  `CodexRuntimeAdapter.start_roster`，接入实际 `TeamTransportBroker`、production stdio
  transport、private bwrap、app-server 和 native MCP。它可进入 `create`/`fallback_eligible`
  contract，但绝不得调用 `TeamRunner.prepare`、`TeamRunner.start`、StartLedger reserve 或
  `mark_semantic_start`。必须穿过真实 Broker delivery/reply，并直接观察
  `query_semantic_context` item -> `fallback_required` -> later verifier complete -> Broker
  terminal guard/report acceptance 的顺序，然后完成 Protocol runtime cleanup。它不得声称或
  fabricated Runner `terminal-result-handoff`、Modeling terminal 或 all-three settlement；不得
  手工发送 `sender_id='runner/terminal-result'`。该证据证明生产 Adapter/Transport/Protocol
  correlation 与 verifier contract，明确不证明 Producer 或 semantic start；任何 TeamRunner 调用
  或 ledger event 都是 FAIL。

两条路径都不得交付业务来源、不得复用 `r` 的历史 evidence，也不消耗 R2.3-002 fresh semantic
modeling start。P2-monitor 与 P2-Protocol 各自独立 PASS 后，才可继续既定 tranche 8、双 baseline
和 fresh semantic start 顺序。

#### Session/Lease 精确清理顺序

当任一 P2 路径实际创建 Build Session/Lease 时，清理必须严格执行：

`admin reread/no in-flight -> failure/terminal checkpoint if applicable -> cancel Session once -> cancel atomically auto-releases all leases -> reread Session cancelled and each Lease state=released with released_at`。

不得在 Session cancel 成功后再显式 release Lease；第二次 release 或 `session_terminal` 不得被
当作成功。删除 Project/Ontology 之前完成上述 reread，并冻结第一阶段 artifact：每个
project-scoped read/model/Protocol key 的精确 ID、`revoked_at`、non-active、Session cancelled、
Lease auto-released、ownership、cleanup receipts、no in-flight Attempt，以及 org-scoped bootstrap-admin key 的
精确 ID/`ACTIVE`（仅授权即将进行的 authenticated DELETE，排除在第一阶段 non-active assertion
之外）。使用该 active org-admin credential 进行正式 Project DELETE，验证 Project/Ontology 不
存在和 project-scoped active residual/cascade；随后立即 revoke org-admin key 并冻结第二阶段
artifact（其 ID、`revoked_at`、non-active、retained org-admin audit row）。最终 aggregate cleanup
evidence 合并两阶段并证明每个 created key 最终 non-active；不得新增 deletion credential、direct
DB delete 或 hard-delete。

Round 51 不增加数据库 migration、archive、detach 或通用 DB history-retention productization；
上述两阶段 artifact 是本轮最小 evidence retention，仅用于证明删除前终态、authenticated
delete、删除后零 active residual 和最终 key revocation。

### R2.3-002 Round 52 活动修订：双阶段 key/delete 证据与 P2 provenance 责任

本节是当前最终活动合同，继续保留 Round 50 的 schema/digest/baseline/外部绑定以及 Round 51
的 P2 路径拆分、Session 顺序和全部全局门禁；仅进一步修订 key/delete 证据边界与 P2 provenance
责任。本节不授权代码、运行时、platform、ledger、key、Session、launch、semantic start 或
delivery-record 变更。

#### 两阶段 key/delete evidence

第一阶段 artifact 必须覆盖每个 project-scoped read/model/Protocol key 的精确 ID、
`revoked_at`、non-active 状态、Session cancelled、Lease auto-released、ownership、cleanup
receipts 和 no
in-flight Attempt。它还必须记录 org-scoped bootstrap-admin key 的精确 ID 与 `ACTIVE` 状态，并
明确该 key 仅用于即将进行的 authenticated Project DELETE，因此排除在第一阶段 non-active
assertion 之外。必须使用该仍 active 的 org-admin credential 执行正式 DELETE；不得创建新的
deletion credential、直接删除数据库或 hard-delete。

DELETE 后必须验证 Project/Ontology absent、project-scoped active residual 为零并记录既有 FK
cascade 行为；随后立即 revoke org-admin key。第二阶段 artifact 记录该 key 的精确 ID、
`revoked_at`、non-active 状态以及保留的 org-admin revoked audit row。最终 aggregate cleanup
evidence 合并两个 artifact，并证明每个 created key 最终均为 non-active；project-scoped
key/Session/Lease rows 可按既有 FK cascade-delete，不要求删除后保留，org-scoped
`project_id=NULL` bootstrap-admin revoked audit row 永不 hard-delete。

#### P2 provenance responsibility

- P2-monitor 是唯一证明真实 schema-v1 TeamRunner 路径中 `TeamRunner.drain()`、terminal-result-
  handoff、ack、all-agent settlement 和 cleanup 的 P2 测试；这些事实必须在
  `foreground_monitor.py` 的真实 foreground lifecycle 中直接观察。
- P2-Protocol 必须保持 TeamRunner-free 的 schema-v2 production Adapter/Broker/stdio/bwrap/
  app-server/native MCP 路径。其证据只到真实 `query_semantic_context -> fallback_required ->
  later verifier complete -> Broker terminal guard/report acceptance -> Protocol runtime cleanup`；
  不得声称、伪造或手工发送 `sender_id='runner/terminal-result'` 以制造 Runner
  terminal-result-handoff、Modeling terminal 或 all-three settlement。
- 最终 fresh Producer 才证明完整 v2 顺序：candidate/receipt/query/verifier -> Modeling terminal
  -> real Runner terminal-result-handoff -> Protocol terminal -> all-three settled。P2 的 PASS 不得
  代替该 Producer provenance evidence。

### R2.3-002 Round 59 活动修订：检索合同 v2、逐断言证据与唯一剩余 producer

本节是 Round 52 之后的当前最小活动合同。run `s` 的 48 个业务事实虽已 materialize，但检索
evidence 为 `platform-contract BLOCKED`：0/48 可机械逐断言绑定平台 Evidence，30/30 entity/
relation item 的 evidence arrays 为空，generic query 首屏 truncated 且 Protocol 未消费 cursor。
`s` 必须保留为失败证据，既不恢复、也不 post-hoc 补证或转写为 PASS。当前仅剩一次已授权
semantic start；不得新增 tranche，且这一次只能在下列 P2a 独立 PASS 后用于全新的 `t`。
本 Round59 对此前持续授权/tranche 的一般表述作本轮收窄：不得以该表述追加额度；`t` 失败即停止，
任何后续 start 必须取得新的明确用户授权并重新细化。

#### 当前最小范围

- 将 Modeling→Protocol required-assertions 合同升级为 `candidate-required-assertions/v2`。Modeling
  item 仅含平台中立字段 `assertion_id, graph_role, subject, predicate, object, object_kind,
  object_datatype, object_language, evidence_citations`；`assertion_id` 稳定、非空且唯一，
  `graph_role=asserted_data`，不得出现 platform IRI/ID、Batch、receipt、workspace、fact ID 或
  ontology 的 Evidence individual。每个 item 的非空 `evidence_citations` 逐项冻结，citation
  字段严格为 `source_artifact_sha256, source_locator, excerpt_sha256, owner_answer_id`，其中
  `owner_answer_id` 仅对已释放的 owner answer 为非空 string，否则为 JSON `null`。没有任何 item
  缺证时 Protocol 才可 `apply`；Delivery 不得选择或补造 assertion/citation。
- Protocol 只可从正式 Batch `dry_run/apply` receipt 的 `batch_id`、`client_item_id` 与真实
  `resource_outputs.resource_iri` 绑定候选 semantic term，形成严格的 `term_bindings`，再生成带
  实际平台 IRI 的 materialized quads。`term_bindings` 的字段固定为 `assertion_id, term_position,
  candidate_term, binding_kind, client_item_id, batch_id, resource_output_iri`；`term_position` 只能是
  `subject|predicate|object`，`binding_kind` 只能是 `resource_output|relation_delta`。前者的
  `resource_output_iri` 必须为真实非空 receipt IRI，后者必须为 JSON null 并以同一 `client_item_id`/
  `batch_id` 的 applied delta 绑定；不得猜 label。所有 v2 digest 使用 canonical UTF-8 JSON
  SHA-256，`term_bindings` 必须进入 `materialized_digest`；不得继续使用 rev7 FNV 或相互冲突的
  digest 规则。
- RDF/XSD 词汇表是固定机械合同：`iri` 对应实际 `<IRI>` 且 datatype/language 为 null；有 language
  的 literal 对应实际 `"lex"@lang`；无 language/datatype 的 RDF 1.1 plain literal 与
  `"lex"^^<http://www.w3.org/2001/XMLSchema#string>` 在语义比较中仅以相同 lexical form 相等，
  但 materialized quad 与 fact ID 必须保留实际平台 term，绝不将 plain literal 重写为
  `xsd:string`。Protocol 独立以 receipts/delta/read 重算并拒绝 label 猜测、缺失、歧义、重复或
  digest drift。
- Protocol 对每个 assertion 先写入 inline/associated 平台 Evidence，再以
  `assertion_id, evidence_citation_digest, evidence_reference_id, client_item_id, batch_id,
  fact_id` 的严格 evidence binding 在 apply 前后验证。只接受平台 `EvidenceReference`，不得以
  ontology 内的 Evidence resource 冒充。`missing_evidence` 在本 workflow 是阻断门；不改变
  backend 通用 apply 语义。
- 通用查询必须由工具/协议机械消费每个 match/context cursor，跨页 union 后按 stable item identity
  去重，直至所有 cursor 为 null；`truncated`、`degraded` 或 blocking warning 均不得 complete。
  native verifier 仅在成功 envelope 且 `data.complete=true` 时可转为 `fallback_satisfied`；失败、
  `-32602`、任何 error envelope 或不完整 data 保持 required。ObjectProperty resource lineage 与
  relation-fact lineage 必须由显式通用 `target_kind` 区分，禁止按 decorate 结果猜 statement lineage。

#### v2 proof、验证与唯一 start 顺序

v2 native proof 顶层字段严格为 `mode, initial_modeling_context, final_modeling_context,
workspace_context, batch_inventory, batch_details, entities_read, statements_read,
candidate_required_assertions, term_bindings, materialized_quads, evidence_bindings,
statement_lineage, pagination`，无 wrapper/extra fields。candidate envelope 严格为
`schema_version, candidate_revision, delivery_id, reply_chain, semantic_digest, candidate_digest,
items`；每个 `evidence_citations` 为已排序且无重复的上述 citation object。`materialized_digest`
精确哈希 `{"candidate_digest":...,"term_bindings":[...],"quads":[...]}` 的 canonical JSON；
evidence binding 和 lineage 再与该 digest、真实 fact ID 一一对应。verifier 必须独立重算，而非信任
Agent text 或 receipt label。

P2a 是不消耗 semantic start 的 real generated-IRI + evidence integration fixture，必须覆盖 48
类代表 assertion、真实 term/receipt binding、逐断言 Evidence、ObjectProperty/relation target-kind、
plain-literal/xsd:string、全部 pagination 和全部 fail-closed 分支。独立 tester PASS 后，才可用唯一
剩余 start 创建 fresh `t`；`t` 必须逐断言证据完整，完成完整 `C -> B -> A`、Phase A 与 Phase B。
`t` 失败不得重试。未来产品化（通用 evidence migration/backfill、Judge、Consumer、mutation、
recovery、UI、新 backend table 或新额度）不属于本轮。

### R2.3-002 Round 60 活动修订：Evidence resolver、multi-delta proof 与全分页链

Round59 保留为已审阅历史。本节关闭其 Evidence identity/cardinality、literal/multi-delta、分页
continuation 和 materialized digest 的未定项，并仅替代与本节冲突的 Round59 v2 细节；不授权
delivery、code、runtime、ledger 或 semantic start 变更。

#### 冻结的 deterministic Evidence resolver

在任何 Batch `apply` 前，Protocol 只能调用一个确定性 helper；不得由 Agent 读取任意 host path、
猜 excerpt/locator 或自行选择 Evidence。helper 接收已冻结 candidate citation 与本 run 的
`project_id, authorization_id, release_id`，只允许：

- source citation 从本 run staged immutable source manifest 的已授权 artifact 解析，返回严格
  `document_name, exact_excerpt, source_locator, artifact_sha256, excerpt_sha256`；
- owner-answer citation 从 immutable `outer-user` record 按 `owner_answer_id`、相同
  authorization/release binding 解析并 hash，返回相同的 document/excerpt/locator/hash 投影；
- 拒绝 hash、locator、manifest、release、permission 或 authorization 不一致，及任何未授权路径、
  未释放答案或解析歧义。

解析结果以 `(project_id, source_artifact_sha256, source_locator, excerpt_sha256)` 作为
EvidenceReference idempotency identity；同一 citation 可以复用同一 platform EvidenceReference，
但不得跨 Project/authorization/release 复用。每 assertion×citation 必须产生一条独立
association binding，其 target 在 pre-apply 为 `(assertion_id, client_item_id)`，并在 post-apply
增加唯一 `fact_id` 对照。任何重复 key、非幂等重试、部分事务、EvidenceReference/Association
dry-run 或创建失败都使整个 workflow 在**任何** Batch apply 前失败；所有 48 个 required citation
都先 resolve 并完成该预检，绝不部分 apply。

citation 的 canonical JSON 字段/顺序固定为 `source_artifact_sha256, source_locator,
excerpt_sha256, owner_answer_id`，UTF-8 `json.dumps(..., ensure_ascii=False, sort_keys=True,
separators=(",", ":"))` 后 SHA-256；citation list 按这四字段 tuple 排序。candidate 可保存其
list digest，但 verifier 的覆盖单位始终是逐 `assertion_id × citation_digest` 行，不能以 aggregate
digest 代替。完整 association row 的唯一键为 `(assertion_id, citation_digest,
evidence_reference_id, client_item_id, batch_id, fact_id)`；verifier 重算全集合并要求一对一覆盖，
重复、漏项、替换、cross-project reuse 或 drift 均 fail closed。

#### term binding、literal 和 multi-delta selector

Round59 `term_bindings` 的字段集合更新为 `assertion_id, term_position, candidate_term,
binding_kind, client_item_id, batch_id, applied_attempt_id, quad_digest, delta_index,
resource_output_iri`。`binding_kind` 只能是 `literal_delta, resource_output, relation_delta,
vocabulary`；`term_position` 只能是 `subject, predicate, object`。`quad_digest` 是 canonical
normalized applied-delta quad 的 SHA-256，`delta_index` 仅作为该 receipt 内第二 selector。
resource/relation/literal 均须以 `client_item_id + batch_id + applied_attempt_id + quad_digest`
唯一绑定；0 或大于 1 命中失败。`resource_output_iri` 仅 `resource_output` 为非空且等于同 receipt
输出；其余 binding 为 null，`vocabulary` 还必须匹配固定 RDF/XSD vocabulary table。create_entity 的
system quads 从 candidate selector 排除；candidate literal 只可从 applied normalized_delta 的 exactly
one canonical semantic match 取得。plain/xsd:string 只按 Round59 的 RDF1.1 semantic comparison
比较，materialized quad/fact ID 继续使用实际 stored term；language 和其他 typed literal 必须严格相等。

`materialized_digest` 成为 native proof 顶层的必填字段。其值为 canonical SHA-256：
`{"candidate_digest":...,"term_bindings_digest":...,"evidence_bindings_digest":...,"materialized_quads":[ordered quads]}`；
两个 binding digest 分别哈希各自 ordered rows。verifier 必须以 formal receipt/delta/read 重算全部
三个 digest，不得接受 rev7 FNV、Agent label 或自报结果。

#### 分页链与 P2a matrix

每个 `pagination` page 精确字段为 `stream_kind, request_fingerprint_sha256, page_index,
request_cursor, next_cursor, response_digest, root_match_ids_digest, response`。fingerprint 是
principal、project、scope_mode、ontology_ids、queries、filters、depth、limit、context_limit、workspace
signature 和 source signature 的 canonical SHA-256。首 page cursor 必为 null；后页 cursor 必等于前页
next_cursor；page_index 从 0 连续；null next_cursor 是且仅是终止。match/context streams 独立，context
root IDs 必须绑定 final match union；重复、跨 stream/scope、cursor/fingerprint/signature 不符或任何
truncated/degraded/blocking warning 都 fail closed。helper 可独立验证 signed cursor 和 response
metadata，但本轮不要求改变 backend query algorithm。

C79/P2a 必须冻结一个 48-row assertion-ID/category matrix（带 matrix SHA-256），每行明确 source/
Evidence requirement、resource/relation/literal/vocabulary binding 类型、plain/xsd:string/language/
boolean 词汇类别、target_kind 与 match/context pagination 覆盖。它只能从已批准的业务 candidate/
source contract 导出，不能任意制造“48 synthetic assertions”或充当答案 Judge。P2a 可在 disposable
scope apply 最小代表集合，但必须对全部 matrix rows 运行静态 resolver/coverage validation；真实 `t`
则必须在 apply 前完成全部 48 citation/Evidence 预检。C79 matrix PASS 为强制门，之后才可使用唯一
剩余 start；本节仍不允许新增 tranche、恢复/补证 `s` 或 retry `t`。

### R2.3-002 Round 61 活动修订：inline Evidence 闭环与冻结 48-row matrix

Round61 保留 Round60 已关闭的 multi-delta selector、RDF literal、materialized digest 和分页链；
仅替代 Round60 的 Evidence resolver/预创建假设及 matrix 的泛化描述。本节不新增 Evidence/MCP
bridge、SAFE_PROTOCOL_TOOLS、create/associate tool、backend table、运行态或账本操作。

#### 现有 inline Evidence 写路径闭环

- `candidate-required-assertions/v2` 的每个 item 必须显式携带非空 citation list；citation 的精确
  字段升级为 `document_name, excerpt, source_artifact_sha256, source_locator, excerpt_sha256,
  owner_answer_id`，`owner_answer_id` 可为 null。Modeling Agent 拥有业务 source/evidence 并填写
  exact 文本、locator 与 hashes；Protocol 不读取、猜测或替换 source。
- Protocol 只机械校验 canonical citation hashes，并把每个 citation 映射到承载对应 assertion 的
  每个 `submit_modeling_batch` item.inline `evidence[{document_name, excerpt}]`。现有 Batch inline
  evidence 是唯一写路径；不添加 Evidence create/associate MCP tool 或 SAFE_PROTOCOL_TOOLS。
- `dry_run` 必须证明 `operation_plan.evidence` 对每个 item 完整覆盖 assertion citations 后，才可
  执行首个 `apply_atomic`。任一 citation 缺失、重复、hash/文本/locator 不符、映射不唯一或
  `operation_plan` 报 `missing_evidence`，均禁止首个 apply；已有失败 recovery 路径负责跨存储异常，
  不宣称 PostgreSQL/Oxigraph instant zero-partial，fresh `t` 失败不得重试。
- apply 内 PostgreSQL EvidenceReference、modeling-item association、lineage 和 finalize 必须在
  同一 DB transaction；Oxigraph 跨存储失败保持既有 `recovering` 语义。apply 后 verifier 沿
  `statement occurrence -> modeling_item origin -> EvidenceReference` 读取并重算绑定；fact_id
  生成后才填入 proof，不要求 candidate 预填或直接建立 fact association。rule-only/delete-only
  item 不得作为 48 asserted lineage 的成功项。
- source fidelity 由独立 tester 在 P2a/`t` Phase A 使用 host staged immutable sources 与
  outer-user record 复核 `document_name/excerpt/hash/locator`；Protocol 隔离内不需要读取 manifest。
  `owner_answer_id` 是 Runner 分配、写入 outer-user 并随 delivery 交给 Modeling 的稳定 ID（可用
  exact answer delivery ID），必须绑定 `project_id, run_id, authorization_id, release_id`。outer-user 的
  最小记录字段固定为 `owner_answer_id, project_id, run_id, authorization_id, release_id,
  question_delivery_id, delivery_id, text, released_at`；candidate citation 必须逐字段匹配。
- post-apply `evidence_bindings` 的精确字段仍为 `assertion_id, citation_digest, evidence_reference_id,
  client_item_id, batch_id, fact_id`，由 readback 填充；verifier 重算全集合、一对一覆盖与
  idempotency，不要求 pre-apply `evidence_reference_id` 或 `fact_id`。

#### 固定 matrix artifact 与 semantic-start gate

唯一 matrix 路径固定为 `modeling_team/references/r2-3-002-proof-v2-assertion-matrix.json`。其顶层
字段严格为 `schema_version, source_run_id, source_candidate_digest, rows, matrix_digest`，其中
`schema_version="r2-3-002-proof-v2-assertion-matrix/v1"`，`source_run_id="r23002-real-20260801s"`，
`rows` 按 `assertion_id` 排序。每行严格为
`assertion_id, subject, predicate, object, object_kind, object_datatype, object_language,
approved_citations, binding_category, literal_category, target_kind, p2a_branch_id,
match_coverage, context_coverage`；`approved_citations` 使用上述六字段 citation object 的排序、
去重形式；`binding_category` 只能是 `resource_output|relation_delta|literal_delta|vocabulary`，
`literal_category` 只能是 `none|plain|xsd:string|language|boolean`，`target_kind` 只能是
`resource|statement`，`p2a_branch_id` 为非空 string，`match_coverage/context_coverage` 为 boolean。
matrix canonical bytes 为 UTF-8 compact JSON
（sort keys、无空白），`matrix_digest` 是对排除自身的完整 object 计算 SHA-256。

artifact 由 implementation 阶段从 retained `s` rev7 handoff 与 approved sources 生成，再由独立
tester 核对；Modeling `t` 不得自行生成、改写或宣称 `s` 已 accepted。所有绑定字段名固定为
`proof_matrix_path` 与 `proof_matrix_digest`：二者必须同时进入 TeamRunner baseline、repair
authorization/reservation/start 的 expected digest 和 `t` candidate proof 的 `matrix_binding`；
`matrix_binding` 严格只有这两个字段。在 P2a PASS 且 path/digest 完全匹配前，StartLedger 必须
拒绝 `t` 的 `semantic_start`。

P2a 真实 apply 只需最小代表子集，但必须覆盖 `resource_output, relation_delta, literal_delta,
vocabulary`、plain/xsd:string/language/boolean、inline Evidence、statement lineage、pagination 和
两类 `target_kind`；静态逐行验证全部 48 rows 的 citation/category/coverage，禁止任意 synthetic48
替代。`t` 可以重述业务语义，但其 assertion IDs、scope 和 citations 必须与 matrix 精确一致，
否则在首个 apply 前失败。C79/C80 的 wrong matrix path/digest/source candidate/assertion/citation、
P2a evidence 不足或 ledger gate 漏放均为负例；本轮仍禁止新增 tranche、恢复/补证 `s`。

### R2.3-002 Round 62 活动修订：candidate-local map、dry-run plan 与实际 gate binding

Round62 保留 Round61 的 inline Evidence、事务/recovery、term、pagination 和 matrix row 条款，
只把实现闭环和 StartLedger gate 写成现有接口可落地的最小面。本节是实现计划，不表示下列
artifact 或代码已经存在；不新增 resolver/Evidence MCP bridge、tool、table、tranche 或
delivery-record 操作。

#### Candidate-local evidence map 与 dry-run 可见性

Protocol 在收到 attributed candidate receipt 后、第一次 `submit_modeling_batch` 前，写一次性
run-local immutable 文件 `evidence/candidate-item-evidence-map.json`（相对 run root，禁止 symlink
escape）。文件顶层严格为 `schema_version, run_id, candidate_digest, rows, map_digest`，其中
`schema_version="r2-3-002-candidate-item-evidence-map/v1"`，`run_id` 为当前 run；每 row 严格为
`assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256`，按
`assertion_id,citation_digest,client_item_id,document_name,excerpt_sha256` canonical bytes 排序、去重。
`map_digest` 是排除自身的 compact sorted-key UTF-8 JSON SHA-256；map path/digest 进入 candidate
proof 与 stable baseline。`document_name` 和 hash 只来自 candidate citation，Protocol 不猜、不读
source，map 不保存 raw excerpt。

现有 Batch API request 继续只接受 item.inline `evidence[{document_name,excerpt}]`；citation hashes
留在 map/proof，不扩展 request schema。对 generic dry-run attempt response 做最小 additive 扩展：
`operation_plan.evidence`（或保持同形的 safe equivalent）是逐 row 严格
`client_item_id, document_name, normalized_excerpt_sha256, dedupe_identity`，不得泄露已提交
excerpt 之外的 raw source。旧客户端/legacy attempt 在无 inline evidence 时仍可省略或返回空数组；
R2.3 Protocol dry-run 必须返回该字段。

Protocol 将 map rows 与 dry-run evidence plan 做 exact projection compare：每个
`client_item_id,document_name,excerpt_sha256` 恰好一次，`dedupe_identity` 对相同 identity 必须稳定，
无缺失、重复、extra、hash/文本 mismatch 后才允许首个 apply。后端 `_attempt_response`/response
schema 的这一 additive 字段不能改变既有 apply/recovery 或非 R2.3 consumer 语义。

#### Runner-owned outer-user answer identity

Runner-owned immutable `outer-user.jsonl` record 的字段严格为
`owner_answer_id, project_id, run_id, authorization_id, release_id, question_delivery_id, delivery_id,
text, released_at`。`owner_answer_id` 固定为
`owner-answer-` 加 canonical UTF-8 JSON（`run_id, project_id, question_delivery_id, text`）的 SHA-256；
`authorization_id` 来自 task/profile 中 baseline-bound 的 standing owner-answer authorization constant；
`release_id` 是 Runner 释放答案给 Modeling 的 delivery ID；`released_at` 是 Runner 写入的 UTC 时间。
RuntimeDelivery/`receive_outer`/Runner prompt 必须把这些 ID 与原文 text 交付 Modeling，candidate 的
owner citation 必须匹配。同一 answer 不得因重复 prompt 生成第二个 ID。独立 tester 在 host 侧重算
ID/hash，核对 delivery/release/project/run 与 outer-user/transport records；source document citation
仍由 tester 对 staged immutable source manifest 复核，Protocol 隔离内不读取 manifest。

#### Matrix/P2a 真实文件与 StartLedger gate

实现阶段创建固定 matrix artifact 后，tester-owned P2a PASS artifact 的唯一路径固定为
`workspaces/modeling-runs/.r2-3-002-proof-v2-gates/p2a-pass.json`。其顶层严格为
`schema_version, matrix_path, matrix_digest, source_run_id, p2a_run_id, verifier_complete,
evidence_hashes, tested_at`；`schema_version="r2-3-002-proof-v2-gates/p2a-pass/v1"`，
`evidence_hashes` 为排序的 64-hex SHA-256 数组，`tested_at` 为 UTC RFC3339，其他字段与固定 matrix
及 run 绑定。P2a pass digest 是完整 canonical compact JSON 的 SHA-256（不在文件内重复写入）。

不新增 ledger event/tranche。现有 `authorize_repair`、`reserve`、`mark_semantic_start` payload
增加 `gate_binding`；对 R2.3-002 fresh `t` 它严格为
`matrix_path, matrix_digest, p2a_pass_path, p2a_pass_digest, source_run_id`，并要求：repair
authorization 先写一份，reservation 与上一 qualifying repair authorization byte-equal，
`mark_semantic_start` 与 reservation byte-equal，semantic_start event 保存同一 binding。旧 run/P2
没有该字段时保持兼容，不因历史缺失被改判。

在 `mark_semantic_start` 前，Runner 必须本地读取 canonical matrix/P2a files，拒绝 missing、symlink
或 path escape、bad canonical hash/schema/source run、`verifier_complete=false`、evidence hash mismatch，
并将 gate binding 与 task/profile 的 baseline-bound `expected_matrix_binding`（同五字段）逐字段比较。
matrix artifact、P2a pass digest 和 gate-validation call sites 进入 stable baseline。Task/Profile 在
启动前固定 expected binding，不能等待 candidate 运行后才决定；candidate proof 的 `matrix_binding`
至少必须与 matrix path/digest 完全一致。任一 gate 或 task/profile mismatch 都在写 semantic_start
前拒绝。Cap/ledger 仍为 18，consumed 17，remaining 1。

### R2.3-002 Round 63 活动修订：citation group identity 与两阶段 lifecycle gate

Round63 保留 Round62 的 inline Evidence、dry-run safe plan、term、pagination、matrix 与 ledger
条款；只细化 citation identity 以及 semantic-start 前/后的责任边界。本节不扩展 Batch request
schema（locator/owner 不进入 Batch API），不新增 tool/table/event/tranche。

#### Citation identity/group contract

Candidate map 仍是一条 `assertion_id × citation` 一行；每行字段严格为
`assertion_id, citation_digest, client_item_id, document_name, excerpt_sha256,
inline_evidence_identity, citation_group_digest`。`inline_evidence_identity` 是
`SHA-256(canonical_json({"document_name":<document_name>,"normalized_excerpt_sha256":<excerpt_sha256>}))`；
`citation_group_digest` 是对同一 `(assertion_id, client_item_id, inline_evidence_identity)` group 内
sorted unique `citation_digest` 数组 canonical JSON 的 SHA-256。完全相同 citation digest/identity 的
重复行拒绝；不同 citation digest 即使同 document/excerpt 也可显式属于同一 group，不得被错误去重。

dry-run `operation_plan.evidence` 只证明每个 `(client_item_id, inline_evidence_identity,
dedupe_identity)` 恰好一行且无 extra/missing；Protocol 先按 group 投影 map，再与该 plan 比对，不要求
Batch API 承载 locator 或 owner-answer 字段。post-apply `evidence_bindings` 每个 citation row 都
必须引用同一或对应的 EvidenceReference，并携带
`assertion_id, citation_digest, evidence_reference_id, client_item_id, batch_id, fact_id,
inline_evidence_identity, citation_group_digest`。Verifier 依次重算 candidate citation 全集、group
digest、inline plan identity 与 reference 绑定；漏项、替换、错误 group、错误 reference 或重复均
fail closed。

#### 两阶段 lifecycle gate 与 owner-answer 时序

- **Mark-before-start gate：** `mark_semantic_start` 之前只验证 canonical matrix artifact、独立 P2a
  pass、task/profile `expected_matrix_binding` 与 ledger `gate_binding`，不得要求 live `t` candidate、
  candidate map 或 map digest。TeamRunner baseline 绑定 matrix/P2a 实际 digest、map/proof schema、
  fixed expected paths 与 callsites，不绑定尚不存在的 map digest。
- **Candidate-before-submit/apply gate：** semantic_start 合法消耗唯一 remaining start 后，Modeling
  candidate 到达；在第一次 `submit_modeling_batch`（包括 dry_run）前，Protocol/Runner 验证
  candidate assertion IDs、scope、citations 与 frozen matrix、candidate `matrix_binding` exact match，
  再生成 candidate-local map。任何 mismatch 在第一次 submit/apply 前失败；该 start 已消耗且不得重试。
  map digest 进入 runtime proof/evidence；dry-run 后的 group-projected plan compare 才控制首个 apply。
- **Owner answer ordering：** Runner 先收到并记录 question delivery；用户答复时，Runner 生成 answer
  delivery ID（即 `release_id`），按 canonical UTF-8
  `json.dumps({"run_id":...,"project_id":...,"question_delivery_id":...,"text":...}, ensure_ascii=False,
  sort_keys=True, separators=(",", ":"))` 的 SHA-256 加固定前缀 `owner-answer-` 生成不依赖 release 的
  `owner_answer_id`，写完整九字段
  outer-user record 并 fsync，然后才向 Modeling 发送同一
  `owner_answer_id, release_id, text`。发送失败仍保留 record、run 失败且不得复用 ID。Independent
  tester 必须同时绑定 question delivery、answer delivery/release 和 outer-user record。

### R2.3-002 Round 71 活动修订：P2a exact-four literal live scope 用户裁决

用户于 2026-08-02 确认本节裁决。它只替代 Round59～Round61 中与 **P2a 真实 apply literal
覆盖范围**冲突的文字，不改变 candidate/receipt binding、four binding kinds、Evidence、lineage、
pagination、matrix 静态校验、StartLedger gate 或 fresh `t` 的其他合同。本节不是对当前代码能力的
追认，也不把静态分支测试改称真实写入证据。

#### P2a current minimal live contract

P2a 必须使用恰好四个 candidate-bearing Modeling Batch Items 完成一次 real generated-resource
`dry_run -> apply_atomic -> readback -> native verifier`。四个 item 必须一一覆盖
`resource_output, relation_delta, literal_delta, vocabulary`，不得增加隐藏 class/property/entity
support item；同时必须覆盖 `resource` 与 `statement` 两类 target、inline Evidence、safe dry-run
Evidence plan、post-apply Evidence/statement lineage、实际 receipt/delta/fact ID binding、validation/
reasoning 和完整 match/context pagination 链。

本轮 P2a 的唯一 live literal 写入要求是 **RDF 1.1 plain literal**。P2a 不要求、也不得为了完成本轮
而真实写入任何显式 typed datatype literal，包括显式 `xsd:string`、`xsd:boolean`、`xsd:integer`、
`xsd:decimal` 或其他 datatype；同样不要求也不得新增 language-tagged literal 的真实写入路径。
P2a 的 materialized quad、statement read 和 fact ID 必须保留并证明平台实际写入的 plain term，不能
把它改写或描述为 typed `xsd:string`。

candidate 可把该 plain lexical value 的比较 datatype 表达为完整
`http://www.w3.org/2001/XMLSchema#string`，仅用于 proof verifier 按 RDF 1.1 规则验证“无 datatype 的
plain literal”和“完整 XSD string datatype 描述”具有相同 lexical form。这个 normalization 是
**proof comparison**，不是 typed literal write：applied normalized delta、stored quad、readback、fact ID
和验收陈述都必须继续表明实际 term 是 plain literal。不得以 candidate datatype、semantic equality
或 verifier complete 声称平台已经真实写入显式 `xsd:string`。

#### Static branches and non-claims

现有 proof-v2 对 boolean、其他 typed datatype 和 language equality/drift 的 static/unit branches 可以
保留，并继续验证严格比较与 fail-closed 行为；这些 branch 不是 P2a live completion gate，也不能作为
真实 Batch write/read/lineage 证据。固定 matrix 继续逐行验证实际 rows 的 assertion、citation、binding
category、target 与 pagination coverage；不得为了满足已取消的 P2a live literal 范围而制造 synthetic
typed/language rows、改写业务 candidate 或扩张 item 数量。

因此，P2a PASS 只可声明：真实 plain literal 写入、plain/full-XSD-string proof normalization、四类
binding、两类 target、Evidence/lineage 与 pagination 已完成。它不得声明显式 typed literal 或
language-tagged literal 的 Modeling Batch 写入能力已经实现或通过 live acceptance。

#### Future requirement boundary

通用 Modeling Batch 显式 RDF literal envelope 是独立的未来平台能力，记录于
`docs/requirements/requirements-v2.4.md` 的 `R2.4-001`。它不属于 R2.3-002 current minimal，不是
本轮 P2a PASS、唯一剩余 semantic start 或 fresh `t` 启动的前置条件；不得在 D70/P2a 窄修复中顺带
修改 backend handler/compiler/API。R2.4-001 后续必须单独细化、设计、review、实现和 live acceptance。

### R2.3-002 Round 75 活动修订：同一 Protocol Agent 的有界原生证明自纠正

用户于 2026-08-02 裁决：当前最小路径先验证同一个 Protocol Agent 能否在同一
Agent/thread/run 内读取上一轮工具调用返回的可行动错误，修正原生 verifier 的 proof input，
并继续完成原任务。Round 74 提出的 deterministic native-proof builder 不再属于当前实现或
验收前置条件，而是后移为仅在本路径仍不能稳定闭环时才重新评估的 future/contingent 方案。

#### 当前最小运行合同

- 原始 Protocol turn 可以在同一 turn 内自行读取 native verifier 错误并重试；原始 turn 与至多
  一次 Host continuation 合计最多调用 native verifier 三次，每一次调用都计入同一个预算；
- Host 只可在 Protocol 自然结束当前 turn、仍无 native success/Broker report 且满足设计冻结的
  全部前置状态时，向同一 Agent/thread/run 发送一次固定 continuation；不得新建 Agent、thread、
  run、scope、Project、Ontology 或 Session，也不得发起第二次 continuation；
- continuation 必须复用 exact existing Project/Ontology/Build Session/Lease、credential identity
  及其原始 expiry；严禁 acquire、renew、extend、restore 或 recreate Lease、Session、credential。
  driver 必须在 `send_message` 前比较冻结 baseline identity/expiry 与当前 Runtime/平台可见状态；
  任一状态 invalid、missing、changed 时 continuation 不可用，必须 fail closed 并走既有清理；
- 自纠正只允许调整 native verifier 的 argument contract 或 proof validation 输入，并可补充调用
  只读平台工具；不得重复 `dry_run`/`apply_atomic`，不得重新写平台、修改候选或业务语义、重建
  receipt/map/Batch plan，也不得在 native verifier 返回 `complete=true` 前提交 Broker report；
- 只有已安全分类为 `argument_contract` 或 `proof_validation` 的失败允许进入本有界纠正路径。
  Host 配置/审批错误、平台状态歧义、deterministic plan 失败、apply 不确定、transport、runtime、
  infrastructure 以及任何不能安全归入上述两类的失败都必须 fail closed；
- 第三次 native verifier 调用仍失败、continuation turn 第二次自然 idle、continuation 投递失败或
  出现不可纠正失败时，当前运行立即终止为失败并进入既有清理；Host 不替 Protocol 调 verifier，
  不合成成功，也不代发 Broker report；
- raw tool error 只允许在 Runtime 的瞬时 Agent 会话上下文中供 Protocol 读取，不得写入 driver
  evidence、文档、长期日志或 Broker payload。driver 只可保留安全的尝试计数、失败层、continuation
  状态和既有 digest/布尔判定，不得保留 raw arguments、raw result、raw error 或对话内容；
- 清理只可延后到本次有界纠正成功或终态失败；本修订不改变既有 write/apply、删除、凭据销毁、
  source fidelity、retrieval completeness 或独立验收合同。

#### 当前保留与明确后移

- 继续保留已经验收的 receipt、candidate/map 和 Batch-plan deterministic tools，以及既有 exact-four
  平台写入链；本轮不得以自纠正为由删除、替换或扩展这些工具；
- Round 74 的 native-proof builder、第三个 overlay tool、四资产 staging/approval 合同及其实现顺序
  全部后移为 future/contingent，不得在当前最小路径中实施；
- 与 builder schema 一起提出的两个 review High 也随 builder 一并后移，本轮不得单独展开为新的
  schema、观察面、分类系统或完成门；
- 只有本次严格有界的同 Agent/thread/run 自纠正仍不能完成原生证明，且用户另行授权后，才可重新
  评估 builder；该未来评估不能追溯性改变本轮结果或把部分证据记为 PASS。

## R2.3-005 Modeling Team Runner 正式化收口与可重复调用

当前状态：`已交付（Start75 独立验收 PASS）`。Start75 在一个 fresh create scope 内完成完整建模、
平台应用、检索、双 CQ、settlement、terminal handoff 和 cleanup；Independent Round 29 保持 retained
证据不变并确认全部完成门。历史失败仍按 append-only 记录保留。

优先级：`P0`

### 权威目标与最小结果

从一个干净 checkout 且 git status 干净的仓库开始，一次稳定的 Modeling Team 任务（即 Runner 启动
并管理这一组固定 Agent 直到任务终态）必须使用一套正式
跟踪的最小 Modeling Team `Task`、`Profile`、`Runner`、`Adapter` 基线，完成 **一次**真实、简单的
业务切片及其验收。Coordinator、Modeling、Protocol 按平台合同完成所需的 `dry-run`、`apply`、
readback、validation 和 reasoning；Modeling、Protocol 完成建模收尾并分别向 Coordinator 返回就绪
消息后保持静默，不再操作平台。Coordinator 随后向 Team 内固定的只读 Acceptance 角色下发验收
任务；Acceptance 读取不可变 acceptance handoff，并通过两个本轮全新的隔离子 Agent 分别读取批准
资料和平台事实，独立判断语义结果。任务取得最终结果后，四个固定 Agent 各自登记 terminal，Runner
记录团队 settlement，精确清理本任务拥有的凭据、Runtime、Session、Build Session/Lease 及其他资源，
并保留可复核证据。

Runner 只负责确定性机械能力（基线装载、启动、传输、终态/settlement、证据交接和所有权清理），
本身不是 Agent，也不是语义权威；Coordinator 负责整体业务调度，Modeling、Protocol 负责建模，
Acceptance 负责独立语义裁决。`Producer` 只可作为 Coordinator、Modeling、Protocol 的解释性统称，
不新增角色、运行时对象、接口或状态机，也不把 Team 抽象成两个独立侧。

正式 Modeling Team Profile 的 roster 必须且只包含 Coordinator、Modeling、Protocol、Acceptance 四个
固定角色；现有三角色 Task/Profile 和对应运行测试不保留兼容路径，必须升级为四角色合同或删除。
Runner 不得继续把缺少 Acceptance 的三角色 Profile 作为合法完整建模任务启动。既有历史需求、交付
记录和运行证据仅作为事实档案保留，不因此保留三角色运行能力。

### 已确认的 Acceptance 角色与子 Agent 生命周期

- Acceptance 是 Modeling Team 的固定角色，由 Runner 启动；在同一次建模任务中允许保留多轮上下文，
  不随单个业务切片的验收轮结束而回收；
- Acceptance 的固定存活范围仅限一次 Modeling Team 任务；本任务 terminal 与
  settlement 后，它与 Coordinator、Modeling、Protocol 一起结束。下一次任务必须创建全新的
  Acceptance，不继承上一任务的对话、结论或隐藏上下文；确需复用的信息只能通过明确的版本化任务
  输入重新提供；
- 验收目标由用户或版本化需求拥有，包括业务切片目标、批准资料、验收问题、通用质量门和未知信息
  处理规则；Coordinator 只把这些内容与切片 revision、资料 digest、平台状态标识和允许的只读边界
  冻结成当前验收任务，不得自行新增、删除或修改验收标准；
- 每个业务切片开始验收时，Acceptance 通过 Runner 提供的受限接口请求创建两个全新的子 Agent：
  `Source Examiner` 仅访问问题与批准资料，`Platform Examiner` 仅访问问题与冻结的平台只读接口；
- 两个 Examiner 不接收预期语义答案、Modeling/Protocol 对话、既有裁决或对方结果，不得互相通信、继续创建
  子 Agent 或获得模型写权限；Acceptance 接收两份不可变结果，负责比较和裁决；
- 验收任务本身也不得携带预期语义答案、Modeling/Protocol 对话或预设 `PASS` 结论；Source Examiner
  从批准资料独立推导来源结论，Platform Examiner 从平台只读结果独立推导平台结论，Acceptance 依据
  冻结标准比较两者；
- Acceptance 自身不直接读取原始批准资料，也不调用平台查询接口；它只接收冻结的验收问题/标准、
  Source Examiner 的答案与资料引用/覆盖范围/缺失说明、Platform Examiner 的答案与平台证据/查询范围/
  完整性说明，以及自身允许保留的历史轮次摘要。Acceptance 只负责检查报告证据充分性、比较结论和
  裁决，不得绕过 Examiner 重新取证；
- 两个 Examiner 的终态报告必须同时声明结论的可回答性并绑定实际证据。批准资料缺少相关证据时，
  Source Examiner 必须明确报告“因缺少相关证据无法回答”并指出缺口，不得猜测答案；只有 Platform
  Examiner 也没有生成无依据的确定答案、且其查询覆盖足以证明平台保留了未知时，本题才可能 `PASS`。
  任一 Examiner 给出无法由其允许证据支持的确定答案时，即使两份答案文本相同也绝不能 `PASS`；
- 对批准资料本可回答的问题，Platform Examiner 无法从平台事实形成有证据的答案，或给出无法由
  平台证据支持的确定答案，均属于 `FAIL/modeling-quality`；Coordinator 将差异交回 Modeling、Protocol
  优化本体结构、建模内容或通用语义表达后重新验收，不得归为 `BLOCKED`；
- 批准资料实际包含可用证据、但 Source Examiner 自身给出无资料证据的确定答案时，属于
  `BLOCKED/acceptance-evidence` 而不是建模质量问题；本轮结束并回收两个 Examiner，Coordinator 使用
  相同冻结任务或只增加资料定位提示的新 revision，重新创建一对全新 Examiner，且不得把上一轮错误
  答案传给它们；该情况不得要求 Modeling、Protocol 修改本体；
- 本轮裁决及其证据保存后，Acceptance 通过 Runner 接口回收两个 Examiner 的进程、Session、临时凭据
  和私有输入；下一切片创建新的两个 Examiner，不复用其身份或上下文；
- Runner 校验创建/回收范围、执行强制超时清理并维护资源账；Acceptance 只能操作自己当前验收轮的
  子 Agent，不能直接创建或销毁任意 Agent；
- 同一个 Acceptance 同一时刻只允许一个活动验收轮；当前两个 Examiner 完成结果交付并被回收后，
  才能为下一业务切片创建新的 Examiner；
- Acceptance 可跨轮保留切片问题与验收标准、两个 Examiner 的最终报告、自身裁决、差异原因、
  修改建议以及轮次/证据摘要；不得保留 Examiner 内部对话、临时凭据、底层工具日志或未形成终态
  报告的中间运行上下文；
- Examiner 因超时、进程崩溃、凭据准备失败或接口不可用等基础设施原因未形成终态报告时，Runner
  使用完全相同的冻结输入，只重建失败的 Examiner；每个 Examiner 每轮最多重试一次，第二次仍失败
  则本轮返回 `BLOCKED` 并清理资源。语义不一致属于 `FAIL`，不得通过重试改变结果；
- `Platform Examiner` 必须预置一个在本轮开始前已冻结版本的只读平台召回 Skill，用于改善通用
  查询策略、召回完整性和证据组织；该 Skill 不得包含切片答案、Modeling/Protocol 对话或验收裁决；
- R2.3-005 只要求该 Skill 具备基础通用能力：正确使用批准的平台只读查询接口、处理分页与结果
  完整性、保留 Evidence/lineage/查询依据，并区分“平台未建模”与“当前查询未召回”；Skill 版本写入
  验收轮证据。高级召回策略、业务专项知识和后续效果调优不属于当前完成门；
- Coordinator 负责建模与验收的串行调度：先下发建模收尾/静默指令，等待 Modeling、Protocol 各自
  确认已完成在途操作，再下发 Acceptance 任务；验收期间不下发其他建模任务，Modeling、Protocol
  保留会话但不得操作平台；
- Acceptance 的 `PASS|FAIL|BLOCKED` 结果只返回 Coordinator，不直接向 Modeling、Protocol 下发
  指令。`PASS` 后 Coordinator 下发下一切片或结束任务；`FAIL` 后 Coordinator 转发差异与修改建议，
  等待建模修复和新的收尾/静默确认，再启动使用全新 Examiner 的验收轮；`BLOCKED` 不触发建模修复；
- 每个 `BLOCKED` 只结束当前验收轮：Acceptance 保存明确的 `blocked_reason` 与证据并回收两个
  Examiner；Coordinator、Acceptance、Modeling、Protocol 均保留，不自动登记任务 terminal，也不由
  Runner 强制结束或重启整个 Team。Runtime/平台不可用时，Coordinator 可在环境恢复后用相同冻结任务
  和全新 Examiner 重验；批准资料缺失时，Coordinator 先判断是资料包确实不完整还是 Examiner 未找到
  已有资料，随后等待用户/版本化需求补齐资料，或提供不含预期答案的资料定位提示，形成新 ticket
  revision 后重验；后续是否继续重验、等待或结束任务由 Coordinator 根据阻塞原因决定；
- 资料定位提示只可包含批准资料的文件名/路径/文档范围、章节标题、业务术语别名或搜索关键词，以及
  资料格式和读取方法；不得包含预期答案、具体业务结论、Platform Examiner 结果或上一轮错误答案。
  每次新增提示都必须进入新 ticket revision，并对 Acceptance 可见；
- Runner 不对验收轮设置统一数字上限；Coordinator 只有在环境恢复、批准资料/ticket 修正、增加合规
  定位提示或模型 revision 变化后，才可创建新的验收轮，不得对完全相同的失败条件无变化重复运行。
  每轮必须记录启动原因、ticket revision、模型状态和结果；单个 Examiner 的一次基础设施自动重试
  规则保持不变；
- 新的真实语义建模 start 使用独立的用户授权预算；R2.3-005 当前只允许一个真实建模切片，Coordinator
  不得因验收失败自行开启第二个全新建模任务；
- 当前最小范围依赖上述 Agent 协作协议，不增加 Runner 阶段门、写入冻结、Lease 撤销、pause/resume
  状态或“Producer 侧”抽象。Runner 强制隔离可作为未来加固项，但不是 R2.3-005 完成门。
- 本条后移的“Runner 阶段门/强制隔离”特指由 Runner 机械允许或阻止 Agent 平台操作、冻结写入、撤销
  Lease，或引入通用 Producer/Acceptance 双侧状态机；它不后移本需求已经确认的只读模型状态重验、旧
  `PASS` 作废与 settlement 完整性校验。后者只决定验收证据能否被消费以及团队能否声明 settled，
  不阻止 Agent 发起平台操作，也不替代 Coordinator 的协作调度，仍属于 R2.3-005 当前完成门。

### 2026-08-05 用户变更：可恢复问题升级与协作式暂停

本节 supersede 上述把 pause/resume 完全后移的文字，但不引入 Runner 硬中断、自动修复或通用后台
编排。用户暂停 R2.3-005 原有建模/验收目标推进，要求先实现 Team 成员发现问题后经 Coordinator
升级、由外层用户/主协调者引导或修复、再在同一 Team run 中继续的最小恢复链；现有 Agent home、
批准资料、runtime asset 和运行证据的文件隔离继续保留。

- Modeling、Protocol、Acceptance 或 Coordinator 遇到不能自行安全处理的问题时，使用原生、严格
  schema 的非终态 `report_issue`，不得用自由文本 terminal `blocked` 代替。问题分类固定为
  `business_clarification|protocol_guidance|platform_repair|runtime_recovery`，并绑定 reporter、失败操作、
  mutation state、请求动作和 Runner 分配的唯一 issue identity；不得包含凭据或任意平台写入指令。
- Issue 首先交给 Coordinator。Coordinator 使用受约束的 issue-control 动作向相关成员下发 `pause`；
  这是协作式指令，成员收到后停止新的工具调用、peer message 和 terminal report并结束当前 turn。
  Runner 不调用 `turn/interrupt`，不撤销 Lease/凭据，不销毁进程或运行目录，也不把 paused/idle 当成
  settled。已有手工 `action=pause` 不进入本恢复链。
- Issue pending 后，Runner 只冻结该 run 的候选 deadline、自动 redrive、terminal settlement 和 cleanup
  推进，并写 append-only issue/pause evidence；不新增 StartLedger event，不调用 prepare/start，也不
  消耗新的 semantic start。一次 run 同时只允许一个 active issue，重复回答、重复 resume、错误 reporter、
  错误 run/thread/candidate binding 均 fail closed。
- Runner 以结构化 outer issue envelope 将 Coordinator 当前问题交给外层。外层对业务/协议问题可提供
  grounded answer 或明确的机械指导；真实业务决策仍归用户，主协调者不得发明事实。Resolution 先交给
  Coordinator，再由其用受约束 `resume` control 原样下发给 reporter；原 Agent 在仍存活的同一 Codex
  thread 上开始新的 turn 继续，不声称恢复被停止的同一个 turn。
- 平台问题进入 `WAITING_REPAIR`。主协调者在 Agent namespace 之外修复并验证平台，提供 repair
  component、pre/post binding、verification reference 和 write-state reconciliation；Coordinator 随后
  下发 resume。共享服务/数据修复可在健康与状态重读后原地继续。若修复要求替换 Runner、Transport、
  Protocol mechanics、Skill、Agent instructions 或已退出的 App Server/thread，必须返回
  `rebind-required` 或 terminal，不得假装 checkout 改动已进入隔离 Runtime。
- 文件隔离保持：role source、Agent home/work、原 candidate、原 baseline 和每次 repair 前后快照都保留。
  对可安全刷新的 `ontology_platform` MCP，只允许 Host 创建新的隔离版本、记录 digest、显式 reload 并
  重验精确工具面；失败则保留 paused 并回滚，不覆盖原始快照。跨进程 crash recovery、跨 run 恢复、
  多 issue 队列、自动平台修复和管理 UI 不在当前最小范围。
- 真实运行中凡是可由更清晰的 Task、角色 instructions、Skill、工具参数说明或 handoff 提示避免的错误，
  必须记录为 `prompt-contract` defect，绑定原始调用/回执和负责的提示词位置。本 run 可用 grounded
  guidance 原地恢复，但在下一次 semantic start 前必须修改并验证权威提示词；不得只记录经验、继续沿用
  已知会诱发同一错误的 prompt。平台/runtime 实现缺陷仍按其真实层分类，不得用提示词掩盖。
- `mutation_state=unknown`、原子 apply 结果不确定或平台状态无法通过正式 receipt/readback 对账时，不得
  resume 写入。完整 modeling-quality 结果、不可恢复 Runtime 死亡和外层明确 abort 仍走既有 terminal、
  cleanup 和后续授权规则，不能用 issue pause 绕过。

### 当前真实验收深度（已确认）

- R2.3-005 只完成一个真实、简单的建模切片，不为证明验收生命周期增加第二个建模切片或新的语义
  建模 start；
- 真实切片复用 R2.3-002 已批准的 Dify Workflow-as-Tool `C -> B -> A` 资料和简单建模目标，但必须
  使用全新的四角色 Modeling Team 任务以及全新的 Project/Ontology；不得连接或续写 R2.3-002 的保留
  模型，也不得把该运行变成 R2.3-003 existing-scope 增量场景；
- 批准资料从 R2.3-002 已版本化输入中选择，不引入新的业务数据集；两个验收问题必须分别具有直接
  来源依据并覆盖一个可回答关系问题和一个显式未知问题；
- `CQ1` 固定为：“在 B 调用 C 作为 Tool 的关系中，当前能够确认的最新发布版本是什么，B 消费的是
  哪个输出？”批准来源为 R2.3-002 的 `official/tools.mdx`、`release-register.md` 和
  `workflow-landscape.md`；
- `CQ2` 固定为：“当 C 因 classifier dependency 不可用而没有返回 numeric score 时，B 会采取什么
  处理动作？”批准来源为 R2.3-002 的 `exception-handling.md`；Source Examiner 必须只依据资料判断
  可回答性，ticket 不携带预期答案或本需求中的验收分析；
- 该切片必须提供两个独立验收问题，并由同一个固定 Acceptance 串行执行两个真实验收轮；每一轮都
  创建一对全新的 Source/Platform Examiner，并在保存终态报告和裁决后真实回收该对 Examiner；
- 第二轮必须发生在第一轮 Examiner 已回收之后，从而直接证明固定 Acceptance 的跨轮上下文以及
  子 Agent 的回收后重建；不得只用 mock 或单元测试宣称真实 Runtime 生命周期成立；
- 当前真实运行不故意制造 `FAIL`、`BLOCKED` 或第二个业务切片；其路由、重试、停止和清理分支由
  确定性测试覆盖。每个验收结果必须绑定 question、slice revision 和完整模型状态标识；
- 任一问题 `PASS` 后发生新的平台写入或 slice/model revision 变化时，旧模型状态上的全部既有 `PASS`
  自动失效，不得与新状态的结果拼接。Coordinator 必须在最终模型状态上重新串行验收两个问题，且
  每个问题使用全新的 Examiner 对；两个 `PASS` 都绑定同一个最终模型 revision 才满足语义完成门。

### 2026-08-04 追加三次语义建模启动授权

- 初始唯一一次 R2.3-005 `semantic_start` 已由
  `r23005-real-20260803t141820z` 消耗。该运行在用户答案进入 Modeling 前因
  `collaboration/routing` 缺陷终止，没有形成完整 modeling-quality 结果；用户选择“未知”是来源忠实的
  合法答案，不是该次 `BLOCKED` 的原因。
- 用户于 2026-08-04 明确新增授权三次语义建模启动。R2.3-005 累计 cap 从 `1` 提高到 `4`，当前
  `semantic_start` 已消耗 `1`、剩余 `3`。这三次是失败修复后的串行重试预算，不是三个新业务切片；
  当前目标仍只接受一个成功的简单 `C -> B -> A` 切片。
- 新启动严格串行。首次取得满足本需求完成门的真实 PASS 后立即停止，不为耗尽预算继续启动。机械失败
  且 `complete_modeling_quality_result=false` 时，在记录独立修复证据和新冻结 baseline 后允许下一次
  start；本段最初将所有 `modeling-quality` failure 视为终态，但该规则已由下文 start8 后的
  R2.3-005-specific incomplete-modeling repair policy 正式 supersede。
- 仅 `semantic_start` 事件消耗预算。reservation 后在业务语义开始前失败并合法
  `presemantic_release` 不扣减 cap，但必须保留失败证据，且不得并发启动另一个 run。
- 授权必须追加到独立的 `.r2-3-005-start-ledger.jsonl`，不得重写既有六条记录，也不得修改或借用
  R2.3-002 历史账本。R2.3-005 的本次授权 tranche 精确为 `+3`；旧 R2.3-002 的 `+2` 合同保持不变。
  预算扩容不替代失败分类或 repair gate：本次 cap 已耗尽的初始扩容路径在下一 reservation 前必须按
  顺序追加当前失败的 `terminal_failure`、本次 `budget_authorization` 和绑定修复后 baseline 的
  `repair_authorization`；cap 尚有余额时不得伪造额外 budget event，而是 failure 后直接追加 repair。
- 三个账本管理命令使用固定的 `--requirement-id` 选择器：省略时只保持既有 R2.3-002 行为，操作
  R2.3-005 必须显式传入 `R2.3-005`。未知 requirement、任意 filename/root 或 requirement/config
  错配必须在创建/打开文件前拒绝；正式 Runner 只使用仓库 canonical
  `workspaces/modeling-runs`，不得通过 caller-supplied `ledger_root` 绕过共享 cap。
- R2.3-005 的追加顺序由账本状态机强制而不是依赖人工操作：`terminal_failure` 只接受最新真实
  `semantic_start`；`budget_authorization` 必须看到该 run 的 retryable/incomplete failure 且当前 cap
  已耗尽。首次 `repair_authorization` 在 cap 已耗尽时必须看到紧随 failure 的本次 budget event；cap
  尚有余额时必须直接紧随可修复 failure，且不得追加 budget。后续唯一 rebind 例外继承
  上文 presemantic rebind 合同：如果该 repair 已被恰好一个 fresh reservation 使用、该 reservation
  从未 `semantic_start` 且已有 `presemantic_release`、当前没有 active reservation，则可为同一 semantic
  failed run 追加非空且不同的新 baseline repair，不得新增 budget；并发 rebind 只能一个成功。每一步
  在同一文件锁下先完整验证再 append；中断留下的合法前缀可安全续接，但 failure/budget 前缀不能
  reserve，错序、错误 run、未使用 repair、未 release、已 start、相同 baseline、duplicate 或并发
  contender 在失败时保持账本字节不变。
- 每次 start 继续使用全新 Project/Ontology、四角色 Session、凭据和 run root。用户原文“未知”不得
  预先注入；只有新运行再次提出同一 grounded question 后，Runner 才可按已修复的 owner-answer 合同
  原样释放一次。

### 2026-08-04 四次启动预算终态

- 追加授权后的 retry2、retry3、start4 均按串行 gate 使用 fresh run/Project/Ontology；每次机械失败都
  在下一次启动前完成窄修复、独立离线 PASS 和新 baseline 绑定。正式账本最终为 cap `4`、
  `semantic_start_count=4`、active `0`，不再存在可用启动额度。
- retry3 暴露的 foreground display-binding 缺陷已由 commit `bc698a5` 修复并通过独立 C74-C83 验收。
  start4 中 Modeling 的三个真实澄清都成功显示、唯一绑定并原样直达 Modeling，证明该修复有效；
  业务回答保留批准资料中的未知，没有把缺失证据变成确定事实。
- start4 在任何平台 API 调用、dry-run 或写入前 `BLOCKED/collaboration-routing`：Protocol 把 run-owned
  fresh scope 误判为需要复用 existing scope，Coordinator 随后把任务目标中的禁止复用误路由成复用
  旧 Project/Ontology；同时 Modeling 的语义候选与 Protocol 负责的
  `candidate-required-assertions/v2` 确定性 envelope 没有完成责任交接。没有形成完整
  modeling-quality 结果，不能据此评价本体质量。
- Modeling、Protocol 已形成 blocked terminal handoff；Acceptance 未形成 terminal，Runner 无法自然
  settlement，故在无进展后 fail-fast 中断并由 finally cleanup 收口。fresh Project/Ontology 已删除，
  Session/Lease/key/child/credential 零残留；该清理证据不替代缺失的语义与 Acceptance PASS。
- R2.3-005 仍未达到最小完成门。继续工作必须先用最小离线路径修复 fresh-scope 指令和
  Modeling-to-Protocol candidate-envelope 责任路由，并通过独立确定性验收；任何新的真实
  `semantic_start` 都需要用户另行明确授权。不得追加 budget/repair/reservation 或启动第五次运行来
  绕过当前 `BLOCKED`。

### 2026-08-04 再追加三次语义建模启动授权

- 用户在看清 start4 未进入 Acceptance 的原因后，明确要求按修正方向继续，并再授权三次真实语义
  建模；三次用完必须停止并向用户重新申请。该授权是新的精确 `+3` tranche：正式累计 cap 计划从
  `4` 增至 `7`，当前已消耗 `4`、计划剩余 `3`，仍只接受同一个简单业务切片的首次完整 PASS。
- 该授权不允许立即启动 start5。必须先证明当前账本状态机能安全表示第二个独立 `+3` tranche，补齐
  重复 tranche 的正向、错序、重复、并发和中断恢复覆盖，并由独立 Tester PASS 后，才能把本次授权
  追加到 canonical R2.3-005 账本；不得修改或借用 R2.3-002 账本。
- Producer 修复必须复用 R2.3-002 Round78 已验收边界：Modeling 只拥有平台无关业务语义，Protocol
  独占 deterministic candidate-to-v2-envelope、Batch、dry-run/apply/readback/validation/reasoning；
  Acceptance 合同不得成为 Producer ready 之前的新前置条件。四角色 roster 和同一 Runner 任务保持，
  Acceptance 只在 Modeling、Protocol ready/silent 后接收冻结 ticket。
- start5 之前必须先通过一个不计入 `semantic_start` 的真实 Runtime 交接 smoke：使用冻结、无业务推理
  的平台无关 candidate，证明 Protocol 在当前 Task/Profile/隔离 Runtime 中自行构造并校验 v2 envelope，
  正确绑定 fresh-create scope，形成相关机械 receipt；不得创建/应用业务模型或把 smoke 宣称为语义 PASS。
- 三次新启动严格串行，首次完整 PASS 后立即停止。当时只允许 retryable mechanical failure 且
  `complete_modeling_quality_result=false`、独立修复 PASS 和 fresh baseline 齐备时使用下一次；该限制现由
  start8 后的 R2.3-005-specific incomplete-modeling repair policy 扩展，但完整 modeling-quality 结果仍
  永久停止。若累计 start 达到 `7` 仍未 PASS，必须再次找用户申请，不得自行增加 cap。

### 2026-08-04 start5 完整 candidate revision 修复

- 第二个 `+3` tranche、start4 repair 和 start5 已按序写入。start5 使用 fresh Project/Ontology，
  Modeling 已把平台无关 candidate 交给 Protocol；前五个 revision 的 pre-write conflict 持续收敛，
  证明 Producer 职责修复生效。但 revision 6 只发送一个 Shape 的替换 patch，遗漏上一版其余 37 个
  items 和完整 citations/queries，违反 immutable candidate 必须完整、自包含的合同。
- Protocol 正确拒绝跨 delivery 重组或修改 candidate。全程没有业务平台 API/MCP 调用、dry-run、apply、
  readback、validation、reasoning 或 Acceptance 结果；fresh 资源已删除空、零残留。终态记录为
  `BLOCKED/collaboration-routing`、`complete_modeling_quality_result=false`，正式账本 cap/count/active
  `7/5/0`，本批剩余两次，不得自动启动 start6。
- 最小修复只允许在 Modeling package/task 明确每个 revision 必须完整重发所有未变
  items/citations/constraints/queries（Runner 仅投影 task objective，不改行为），Protocol 不得合并历史 patch，
  并以 retained revision 5/6 生产形状建立回归。不得增加 candidate-history/
  patch-merge 状态机、修改 mechanics/platform/Acceptance 或重跑 Runtime smoke。独立 Tester PASS 和 fresh
  baseline 之前不得追加 start5 repair、reservation 或 semantic start。

### 2026-08-04 start6 neutral candidate authoring closure

- start6 的完整 revision 修复已生效：r2 完整携带所有语义、citations、constraints、dependencies 和
  consumer queries，且无 patch 字段。但 r1 使用错误的 neutral item wrapper；r2 修复 wrapper 后仍使用
  未声明的 `upstreamOf`/`invokesAsPublishedTool`、跨异构对象的 `affectedSubject: resource` range，并有
  未声明的 fact/Shape path。Protocol 在第二个 pre-write conflict 后按 I21 fail-fast。
- 全程无 Build Session、业务平台 MCP/API、receipt success、dry-run、apply、readback、validation、reasoning
  或 Acceptance；fresh scope 删除空、零残留。终态 `BLOCKED/collaboration-routing`、
  `complete_modeling_quality_result=false`，正式账本 `7/6/0`，最后一次 start7 不得自动使用。
- 最后修复只允许增加一份只投影给 Modeling/Protocol 的场景无关 immutable ordinary-neutral authoring
  reference，并在 package/task 引用：精确 envelope/item wrapper、string-list constraints、unique item IDs、
  谓词/Shape path 全声明、对象 range 单一闭合、异构对象使用显式
  common superclass/subclass 或拆分 predicate；Protocol 必须把 exact entire delivered candidate 交给 receipt，
  不得缩减重写。不得把本业务候选/答案作为 Agent 输入，不改 mechanics/MCP/Runner/Runtime/platform/
  Acceptance，不增加自动 closure 或再跑 smoke。C99-C104 独立 PASS、clean commit、fresh baseline 前不得
  repair/start7；若 start7 未 PASS，cap 7 耗尽后必须向用户申请。

### 2026-08-04 start7 staged-atomicity closure

- start7 `r23005-real-20260804t102802z-start7` 证明前述 neutral authoring 修复生效：Modeling 交付完整
  self-contained candidate，string-list constraints、谓词/range/Shape path 和显式未知均闭合。Protocol 不再因
  envelope、缩减 candidate 或未声明 vocabulary 拒绝。
- Protocol 的 concrete conflict 指出 candidate 把 whole-candidate semantic integrity 误写为一次
  `apply_atomic`；公共平台契约实际要求按 class、property/relation type、entity、receipt-bound generated IRI、
  relation、dependency-safe Shape 分阶段转换，每个 apply stage 独立原子化。运行未触达 Build Session、
  platform dry-run/apply、readback、validation/reasoning 或 Acceptance，终态仍为
  `BLOCKED/collaboration-routing`、`complete_modeling_quality_result=false`。
- fresh Project/Ontology 已删除空、密钥撤销、进程和临时资源零残留，backend/frontend health 均为 200。
  用户随后明确追加三次真实建模额度；正式账本 34 records，SHA
  `ce51034d2eab182495c722dcc08a92c3dbf2009e51ac9eb1e4e681239408ea43`，cap/count/active `10/7/0`。
- 最小修复只澄清 Modeling/Protocol 共享职责边界：candidate 的完整/不可变只指语义完整性；平台 stage
  排序、每阶段 dry-run/apply_atomic 和 receipt-bound IDs/IRIs 仅由 Protocol 负责，禁止进入 Modeling
  constraints。Round 4 因 neutral smoke 示例仍含 fresh scope/Batch mechanics 记录 D2 Major；修复同一既有
  示例与 C104 后 Round 5 聚焦 PASS。不得新增 start7 专用 checker、审计 harness 或 mock/smoke 前置门；
  clean commit 和 fresh repair baseline 后直接运行 start8。

### 2026-08-04 start8 entity label closure

- start8 `r23005-real-20260804t112405z-start8` 保持 staged-atomicity 修复：neutral candidate constraints 未
  泄漏平台执行 mechanics。Protocol 对完整 r1 返回 concrete conflict，指出 materialized negative probe
  缺少 `create_entity` 必填的非空 label；Modeling 的完整 r2 修复 probe label，但两个 explicit_unknown
  entities 仍缺少 label，随后双方正确 BLOCKED。
- 终态分类为 `modeling-quality`、`complete_modeling_quality_result=false`。未触达 Build Session、Lease、
  Batch、dry-run/apply、readback、validation/reasoning 或 Acceptance；fresh scope 删除空、密钥撤销、进程
  与平台残留为零，backend/frontend health 均为 200。正式账本 38 records，SHA
  `9573a90741e36517f908ece47545c29d17cfa386ecd5e3b2c71300ad1b4ffde4`，cap/count/active `10/8/0`。
- 最小修复把非空 source-grounded label 定义为所有 entity-producing candidate items 的共享闭合规则：
  entity/explicit_unknown 使用 `semantic.values.label`，materialized negative probe 使用
  `semantic.invalid_instance.label`；Protocol 必须拒绝缺失值，且不得从 item/entity ID 或问题文本推导、
  生成业务 label。不得改 platform mechanics 或增加 start8 专用 checker。
- 独立 Round 6 聚焦 14 PASS、1 个明确 opt-in skip；C104-C105、task/profile、Ruff/diff、ledger replay 和
  17 个 retained evidence hashes 均 PASS/unchanged。clean commit 与 fresh repair baseline 后直接运行 start9。
- start9 pre-reservation 随后证明旧 ledger policy 把所有 `modeling-quality` failure 永久封死：canonical
  `authorize-repair` 在零 mutation 前返回 `failed run cannot authorize a second start`。本需求现正式
  supersede 旧规则：仅 R2.3-005 且 `classification=modeling-quality`、
  `complete_modeling_quality_result=false` 时，可在独立修复 PASS、fresh baseline、剩余 cap 和正常串行门
  下追加 repair authorization；`complete=true` 或已有完整语义结果仍永久停止。R2.3-002/R2.2 的历史
  modeling-quality 禁止重试合同保持不变；budget authorization 仍只接受 retryable mechanical failure，
  不得因 modeling-quality 扩 cap、改写 terminal event 或绕过用户授权。

### 明确边界

以下内容不是 R2.3-005 的前置条件，也不得为了本需求重新引入为完成门：P2、P2a、monitor、native
verifier、proof matrix、Acceptance 之外的通用 acceptance framework/orchestrator、
delivery-recovered/context resume、
R2.3-003 非空增量建模、Pi Runtime，以及 explicit datatype 或 language-tagged literal 写入。
Platform Examiner Skill 的高级召回调优同样后移，不得扩张为当前验收前置条件。
Runner 强制写入冻结、验收阶段门和通用 Producer/Acceptance 双侧状态机同样后移。
这里的“验收阶段门”仍采用上文限定含义：后移的是平台操作的机械阶段执法，不是模型状态只读重验、
旧 `PASS` 失效和 settlement CAS/一致性 readback；这些被动完整性检查不得自行冻结写入、撤销 Lease
或分配语义任务。
R2.3-005 的正式 Runner、四角色合同和追加重试预算机械能力已经实现，并通过 plan review、clean-commit
确定性测试和独立离线验收；这只证明实现可进入受控真实重试，不宣称本需求已完成。仍须按已授权预算
完成一次真实四角色 Modeling Team 运行、独立 Acceptance、settlement 与清理证据后，才能把本需求
标记为完成。

### 现有证据边界

Round78 证明了保留模型及其独立 Acceptance 结果，但**没有**证明当前正式 Runner 的新一次真实调用。
clean commit `6c9bf4a` 已独立证明 Runner/ledger/CLI 的离线确定性、旧合同兼容和 canonical ledger
隔离；它没有执行 I15 live append、fresh Project/Ontology、四角色真实建模、Acceptance、settlement
或清理，因此真实可重复调用仍待本次受控重试证明。

## R2.3-003 已有 Project/Ontology 增量建模

当前状态：`Current Draft（2026-08-12 start16–start18 三次真实启动已全部消耗；start18 首个
delete-only Batch 成功 apply 后因上下文围栏未跟随 workspace version 前进而超时，删除前完整语句
receipt 已受控回补且 RDF 语义精确恢复；围栏窄修与全量回归 PASS，但 L0/L1/L2 未完成、当前授权
已耗尽）`

优先级：`P0`

### 现状是什么，需要改成什么

当前：

- R2.3-001 只机械验证空 existing 作用域；
- R2.3-005 Start75 已从 fresh create scope 完成 C -> B -> A 业务切片、两个 `ExplicitUnknown`、
  validation/reasoning、三类语义对象检索、两个 CQ、独立验收与清理，并有意保留非空
  Project/Ontology；
- 尚未证明全新四角色团队可以只依赖当前平台事实、非敏感 handoff 和批准的新资料继续该模型。

目标：

- 使用全新的 Runner run 和全新的 Agent Sessions；
- 通过 existing 模式连接 R2.3-005 Start75 明确保留的非空 Project/Ontology；
- 不继承 Start75 Agent 对话、历史 Prompt、旧 verdict、隐藏答案或本地运行目录；
- 用批准的增量资料解析 Start75 的两个 `ExplicitUnknown`，并完成一个相关但独立的
  “C 评估结果 -> B 可发布性决策 -> A 发布结果”业务切片；
- 证明既有模型保持正确、两个已解析 unknown 资源已安全删除、当前结论和新增切片均可可靠检索。

本节经用户确认 supersede 本文此前“R2.3-003 必须继续 R2.3-002 Project/Ontology”的文字。新的精确
existing-scope 基线是 Start75 `r23005-real-20260810-deepseek-start75` 创建并保留的 Project
`7fc146d8-c76f-417b-9314-854544f269fc`、Ontology
`fd762f52-2f5e-4bc0-902a-5583135ab64d`。R2.3-002 仅保留为原批准来源和历史语义链的来源依赖，
不再是本需求要连接的平台作用域。

### 已确认范围

- R2.3-003 直接使用 Start75 Project/Ontology 和新发布的非敏感 scope handoff；启动前必须通过平台
  重新读取 Project/Ontology 归属、当前 workspace version、默认 Graph Set、Build Session 与 Lease
  状态，任一身份、版本或所有权漂移都停止并等待人工处理；
- Team Runner、Codex Adapter 和基础四 Agent Profile 不因 existing 场景修改核心语义；
- Modeling 在构造首个 candidate 前通过独立 project-scoped read credential 调用
  `get_modeling_context`，并按需调用受限的 `get_ontology_read_model` 与
  `query_semantic_context`，以当前 workspace version、类/实体/事实和相关语义邻域作为建模依据；它不得
  获得任何写工具、Build Session/Lease、Batch、validation/reasoning mutation 或 Protocol credential；
- Modeling 的 read credential 与精确三工具/P/O/model/scope allowlist 必须由 Runner-owned local proxy 在
  backend 转发前机械执行，不能只依赖 Prompt、MCP tools/list、客户端 enabled_tools 或 Project ownership；
  成功 context response 形成绑定 run/P/O/workspace version/response digest 的不可变 receipt。没有该 receipt
  时 direct Team Transport 与 candidate capability 均不得发布候选；
- Protocol 在收到 candidate 后独立重读当前平台事实和 workspace context，验证 Modeling 观察后未发生
  workspace drift；只有 exact version revalidation receipt 成立才可创建新的 Build Session/Lease 或调用任何
  stateful tool，drift 通过 typed zero-mutation conflict 请求完整 revision；
- Platform/Protocol 必须通过显式 canonical identity 字段绑定 existing entity；不得从 full IRI 尾段猜
  semantic ID/Class。硬删除前必须用 scope/entity/workspace-bound opaque cursor 读取完整的 subject/object
  statement page chain，并取得显式 completeness/snapshot digest；未完整时禁止删除；
- 本轮只通过新的不可变 Modeling Batch 表达增量变化；除两个目标 `ExplicitUnknown` 及其级联关系外，
  不得删除、重建或覆盖 Start75 的类、属性、实体、关系、Shape、Evidence 或 lineage；
- existing 模式不删除 Project/Ontology，不抢占历史 Lease，不恢复历史 Agent Session；
- 新 source bundle 固定为
  `docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json`：复用 manifest
  中列出的既有批准资料，只新增 `scoring-and-publication-policy.md` 和
  `manual-review-publication-case.md`；用户已授权由交付侧构造并冻结这些合成业务资料，无需逐条
  业务确认；
- source 文档只陈述业务事实，不规定 Class、predicate、IRI、Shape、Modeling Item、平台命令或 CQ
  预期答案；ontology structure 仍由 Modeling Agent 判断；
- 用户于 2026-08-11 明确授权四次 fresh semantic starts，授权标识冻结为
  `user-20260811-r23003-start1-4`。R2.3-003 独立账本从 `cap/count/active=0/0/0` 通过首次授权事件变为
  `4/0/0`；不得借用或修改 R2.3-005 Start76–77。四次是上限而非必须消费数量，首次完整 PASS 后
  success-stop。
- 上述四次现已全部以 terminal failure 结束。用户随后追加精确三次 fresh semantic starts，authorization
  ID/reference=`user-20260811-r23003-revision-start1-3`、`additional_starts=3`。该事件必须作为现有 003
  ledger 的严格 budget extension 追加，使 cap 从 4 变为 7，不重写初始授权/四次失败；必须校验最新
  retryable terminal predecessor、ID/reference 唯一性与 lock/replay。只有修订实现、独立确定性验收、
  restart/health 全部 PASS 后才可 reserve；首次完整 semantic PASS 后剩余额度不再消费。
- 上述 `+3` 也已全部以零 mutation terminal failure 结束并完成 append-only reconciliation。用户于
  2026-08-11 再追加精确一次 fresh semantic start，authorization ID/reference=
  `user-20260811-r23003-modeling-read-start1`、`additional_starts=1`；该事件把 cap 从 7 增至 8，不重写
  前 25 行。它只可在 Modeling read-only 合同完成 plan review、实现、独立测试、restart/health 后 reserve，
  不得在设计或测试阶段启动。
- 上述 `+1` 已由 `r23003-real-20260811-deepseek-start9` 消费。Modeling 正确构造了完整 24-item candidate，
  但 App Server 因 `modeling_read_proxy` 缺少专用 MCP approval/trust 配置而在 proxy/backend 前拒绝四次
  `get_modeling_context`；pre-candidate gate 因而保持关闭，candidate/receipt/Session/Lease/Batch/mutation
  均未发生。独立 Round24 证明 retained scope 无漂移并完成 key/private-artifact cleanup，ledger 以
  `runtime/infrastructure`、canonical `zero-mutation` append-only reconciliation 收口为 cap/count=`8/8`。
  Round25 已独立证明窄修只允许 active R2.3-003 Modeling read proxy，005/default/foreign role/unknown server
  继续 fail closed。该确定性 PASS 不等于 live L0/L1/L2。
- 用户随后于 2026-08-11 明确追加三次 fresh semantic starts，authorization ID/reference=
  `user-20260811-r23003-post-approval-fix-start1-3`、`additional_starts=3`。该严格 budget extension 已在 start9
  retryable terminal predecessor 后把 cap/count/active 从 `8/8/0` 变为 `11/8/0`；只能用于已通过 Round25
  的 Runtime approval 修复后的 live run，首次完整 PASS 后 success-stop，不为消耗额度继续启动。
- 用户于 2026-08-12 在 start15 收口后明确追加三次 fresh semantic starts，authorization
  ID/reference=`user-20260812-r23003-post-carrier-start1-3`。该 `+3` 将 strict ledger 从
  `cap/count/active=14/14/0` 扩为 `17/14/0`，并已由 start16–start18 全部消耗。start16 暴露 active
  run-owned Lease 被 context fence 误报 drift；start17 暴露数字 revision 被 Prompt 生成为字符串；start18
  成功进入真实 Phase B 并 apply 第一个 delete-only Batch，随后因围栏仍绑定写前 workspace version
  而阻断后续批次，修复派生状态后又在 300 秒 candidate-progress 超时前未来得及发布 revision。
  本轮终态 strict replay 为 `cap/count/active=17/17/0`，59 条记录，授权已耗尽。
- start18 超时时已删除 `unknown-cross-release-output-meaning` 及其 9 条 incident statements，
  因此不得用“零 mutation”或 before/after workspace 相等收口。交付侧只使用删除前完整 receipt
  受控回补该资源；回补后当前 9 条语句摘要与原 receipt 均为
  `7f1e9b359f9e19da1ddf8d7ce3d652e7d1592b81b070d3df50d899a18d84bc91`，两个 unknown 均存在，
  三个新业务实体均不存在。这只证明 RDF 语义已恢复；Batch/workspace/reasoning/retrieval
  历史仍保留且必须如实记录。
- R2.3-003 的 stateful context fence 只保护 candidate 身份、exact P/O、workspace version、ready/issues
  与 active recovery。同一 Protocol 进程成功 `apply_atomic` 后，fence 必须用响应中经核对的
  `before_version/expected_version/after_version` 机械前进；当前 run-owned Lease 与可修复的 derived stale
  不是 ontology identity drift，不得因它们自我阻断后续 Batch。外部 workspace drift、wrong P/O、
  not-ready/issues 或 recovering.active 仍在回调前 fail closed。
- 原生 `translate_candidate_to_batches` MCP 必须为 R2.3-003 透传 candidate、requirement ID、existing-binding
  receipt、完整 deletion-impact receipts 与 Phase-A readback 状态；普通/R2.3-005 仍只接受 candidate。
  Protocol 不得在 native translator 拒绝后手工拼 Batch。工具返回的 create stages 必须先按序完成
  dry-run/apply 和 durable readback，刷新 workspace-bound receipts 后才允许取得并执行最终 delete-only
  Phase-B Batch；缺 receipt 或 readback=false 时删除保持 fail closed。
- existing scope 不提供自动回滚。第一次平台 mutation 前的失败可以在剩余授权内 fresh retry；任一
  apply 后优先由同一存活 Team 读取当前状态并用新 Batch 修复。apply 后 Team terminal、mutation state
  unknown 或正式 readback 无法对账时，停止新的 start 并保留平台状态；只有完成状态对账并形成新的
  明确 handoff 后才可继续，不得沿用旧 workspace version、自动删除 Project 或把部分写入冒充 Start75
  原始基线。
- 首个 candidate receipt 后、首次 mutation 前如 live identity/deletion-impact read 发现 mismatch，Runner
  必须使旧 receipt 失效并允许一次绑定 typed conflict 的完整 candidate revision，再由 replacement receipt
  重新开放 platform gate；foreign/stale、并行或 mutation 后的 binding revision 一律拒绝。

### 已确认的组合建模目标

1. `quality_score` 与 `quality_rating` 的旧 unknown 必须由新来源解析：两者是同一 content quality
   measure 的跨版本 rename，measure/range/unit/calculation/interpretation 不变，数值存在时可跨版本
   业务比较；每个 release payload 仍必须使用该 release 实际发布的字段名。
2. B 无分数动作的旧 unknown 必须由新来源解析：当 C 因 classifier dependency 不可用而无 numeric
   score、返回 `CLASSIFIER_UNAVAILABLE` 时，B 不自动重试、不报告 publishable，而是形成
   `manual review required` 决策；A 只发布 B 明确报告 publishable 的结果，因此该决策下 A 持有内容
   等待 review，不创建 published result。
3. 原两个 `ExplicitUnknown`（semantic IDs 精确为 `unknown-cross-release-output-meaning` 和
   `unknown-b-no-score-behavior`，expected Class 精确为 `ExplicitUnknown`）在当前结论、新 Evidence 和所需关系已写入后必须硬删除，不保留 tombstone、
   resolution wrapper 或“历史 unknown”实体。迁移采用单调两阶段：Phase A 先用不可变 Batch 写入并
   readback 当前结论、新 Evidence/lineage 和业务切片；Phase B 只有在 Phase A durable 后，才从 live read
   model 枚举目标的全部入边/出边、生成 tool-owned 完整 impact receipt，并用独立 delete-only Batch 删除
   目标。candidate 只声明冻结目标与 `delete_mode=full_live_impact`，不声明 IRI、triples 或预期边集合；
   用户对目标资源的硬删除决定同时授权删除其全部 incident triples。发现身份漂移、读取不完整或 receipt/
   workspace 漂移时 Phase B fail closed，Phase A 的正确新增语义可以保留但不得
   进入最终 Acceptance。删除历史 unknown 不等于删除其来源文档；新结论仍必须直接引用批准 source。
4. 新业务切片必须建模 source 中的具体链：`content-review-001` 经 C 得到无 numeric value 与
   `CLASSIFIER_UNAVAILABLE`，B 形成 `decision-review-001=manual review required`，A 形成
   `publication-outcome-review-001=held for review`，且没有 published result。该具体事实不得被简化为
   仅修改 unknown 文本或仅增加一个未连接的状态字段。
5. 不对普通 numeric score 的阈值/决策、其他 diagnostic、自动重试、人工 review 后续结果或其他
   Workflow 外推规则；资料未说明的内容继续保留为明确未知或范围外。

### 验收问题与独立性

最终模型当前回答以下两条不携带预期答案的 CQ：

1. 当前 B 消费 C 的哪个已发布版本/输出，历史 `quality_score` 与当前 `quality_rating` 的业务连续性和
   release 内字段使用边界是什么？
2. C 以 `CLASSIFIER_UNAVAILABLE` 成功结束但没有 numeric score 时，B 和 A 分别采取什么动作；对
   `content-review-001`，能否沿 C evaluation result、B decision 和 A publication outcome 得到完整、
   source-grounded、非截断的业务链，且明确哪些后续行为仍未定义？

CQ 数量由 versioned acceptance standard 声明，为任意正整数 N；Runner/Carrier 不得硬编码 2 或特定
`cq-001/cq-002` 集合。当前 003 standard 仍声明上述两题，不为证明 N-CQ 虚构第三个业务问题。所有 CQ
使用同一个 fresh Acceptance，严格按 standard 顺序串行执行；每题创建 fresh Source/Platform Examiner，
上一题终态 cleanup 后才能开始下一题。Examiner 不接收业务答案、Producer 对话或旧 verdict。Source
Examiner 只从该题批准资料推导答案，Platform Examiner 只从冻结 model state 的只读平台事实推导答案，
Acceptance 比较两侧结果。任一题非 current/usable PASS 时不推进；settlement 只在同一 model-state epoch
下全部 N 题 PASS 且全部 child cleanup 后成立。后续仅修改 acceptance standard 即可使用不同 N，无需修改
Runner/Carrier 代码；实现只保留通用输入大小和运行资源安全限制，不设业务 CQ 数量上限。

003 acceptance standard 必须使用 deletion-aware unknown policy，精确绑定
`unknown-cross-release-output-meaning`、`unknown-b-no-score-behavior` 两个待删 semantic IDs 与
`ExplicitUnknown` expected Class，并要求
所有非目标 explicit unknown 保持；005 原 `preserve-explicit-unknown` policy 和两题行为保持兼容。每张
ticket 都携带 Runner-owned ordinal/count/previous/next/is-final 元数据，角色不得从 CQ ID 名称推断顺序。

### R2.3-003 最小完成门

进入真实运行前，必须已经有 R2.3-005 的独立验收证据；该证据只证明 Runner 运营基线，不替代
本需求自身的增量语义验收。

1. 使用全新的 Team Runner run、Coordinator、Modeling、Protocol、Acceptance Sessions、Build Session
   和 Lease。
2. Agent 只读取当前平台事实、允许的新业务资料和非敏感 scope handoff；Modeling 的平台面精确限制为
   `get_modeling_context`、`get_ontology_read_model`、`query_semantic_context`，Protocol 保持唯一写入者。
3. Modeling 在 candidate 前读取当前 Modeling Context 和必要详细 read model；Protocol 在 candidate 后、
   写入前独立重读并验证同一 workspace version。既有模型被正确读取且没有历史 Agent 对话泄漏。
4. Phase A 增量 Batch 和 Phase B delete-only Batch 均完成 dry-run/apply/readback，workspace 单调前进，
   既有模型未被错误覆盖或重建。Acceptance freeze 前必须证明新结论/Evidence/业务切片 durable、两个目标
   及其声明的级联边不存在、所有非目标资源保持。
5. 最终 validation、reasoning 和 governed retrieval 同时支持 Start75 既有结果、两个 unknown 对应的
   source-grounded 当前结论，以及新增 decision/publication 切片；两个旧 unknown 资源查询不存在；
   acceptance standard 声明的全部 N 条 CQ 均在同一最终 model state 上取得 current/usable PASS。
6. existing 模式保留 Project/Ontology，只清理本轮 Runtime、Build Session/Lease 和临时凭据。
7. 本轮不删除 Start75/R2.3-003 Project/Ontology；是否在未来需求后删除必须另行明确授权，不属于
   Team Runner existing 模式。
8. 自动化回归、真实运行和独立测试 PASS。

### R2.3-003 非目标

- 复用或恢复 R2.3-002 Agent Session；
- 合并两个并发写入团队；
- 自动解决历史 fenced、冲突或未知所有权状态；

### R2.3-003 当前主链同步瘦身（2026-08-11 用户确认）

为避免先按冗余主链完成一次建模、再因瘦身重复完整验证，以下改动与 R2.3-003 当前实现同步完成，并由
同一次后续真实建模验证：

1. 业务/候选合同只以 Task objective 和角色 package 为权威；Runner 只投影 run/scope、能力名、delivery、
   CQ 顺序等运行期机械字段，不再复制 003 业务规则、目标 ID、候选 item schema 或历史 delivery 示例。
2. 删除对 `runner.py`、`codex.py`、Protocol 等整文件 SHA-256 的交付门。兼容性由 003/005 的精确行为测试
   证明，不因无关字节变化刷新哈希。
3. cleanup 完成门以停止资源、删除私密临时文件之后的最终扫描为准；pre-cleanup 扫描只作诊断历史，不能
   覆盖最终事实或制造 `实际无残留但 verdict=false`。仍必须证明 key revoked、无真实 process/socket、无
   当前 secret occurrence。
4. 后续只有已在真实运行或需求开发中造成候选漂移、错误阻断、重复验证或虚假失败的无用功能才可继续
   删除，并必须加入本节/设计与同一共享测试计划；普通代码美化、超大类拆分、Ledger 重写、通用插件化、
   全面清理 002/005 历史兼容均不属于当前范围。
5. 保留直接保护建模正确性的边界：Modeling 三工具只读查询、workspace revalidation、existing identity/
   delete-impact receipt、两阶段删除与写后对账、N-CQ 串行验收、授权次数和最小凭据撤销。

用户新授权 `user-20260811-r23003-post-revision-contract-start1-3` 已把 cap/count 从 `11/11` 扩为
`14/11`。start13–start15 均已消费并在平台写入前零写入终止；三次都已完成独立清理、canonical
reconciliation 和 append-only terminal failure。当前 cap/count/active=`14/14/0`，授权已耗尽。
start14 证明正整数 revision 到达 Carrier 后被旧 safe-string 合同拒绝；start15 穿过该修复并完成
revision 1 receipt、standalone typed conflict 和完整 revision 2，但 Carrier 又因旧的全局 immutable
identity 假设拒绝 replacement。两处合同现均已有 003-only 行为修复和 005/default 隔离回归；真实 Phase
A/B、readback、validation/reasoning/retrieval 和 N-CQ 仍未完成。任何新 live start 必须获得新的显式授权，
首次完整 PASS 后停止。

2026-08-12 新授权 `user-20260812-r23003-post-carrier-start1-3` 又将 cap/count 从 `14/14`
扩为 `17/14`。start16–start18 现已全部消耗；strict replay 为 59 条记录、
cap/count/active=`17/17/0`。start18 第一次证明了 candidate、receipt、live binding、完整
delete-impact read、Build Session/Lease、dry-run 和一个 delete-only apply 的真实路径，但围栏
在成功 apply 后没有前进 workspace version，导致后续 Batch 被自我阻断。超时后已用删除前完整
receipt 精确回补 RDF，不伪称平台历史回滚。当前围栏修复及 003/005/full suites 均 PASS，
但真实 Phase A、第二个 Phase B 删除、最终 readback/validation/reasoning/retrieval 和 N-CQ 仍未完成。
当前无剩余启动授权。

start18 transcript 同时暴露 native MCP wrapper 当时只接受 `candidate`，没有把底层 translator 已支持的
003 binding/impact/readback 参数暴露给 Protocol；Agent 因此绕过工具手工组装并错误地先执行删除。
commit `57e227c` 已补齐该窄通道并明确禁止手工 fallback，回归证明 create stages 在前、durable Phase-A
readback 后 delete-only 在最后，且 005/default candidate-only 行为不变。该确定性修复没有新增授权，
不能替代尚未完成的真实语义验收。

2026-08-12 用户再次明确授权三次 fresh semantic starts，authorization ID/reference=
`user-20260812-r23003-post-translation-bridge-start1-3`、`additional_starts=3`，把 strict ledger 从
`cap/count/active=17/17/0` 扩为 `20/17/0`。start19 已消费第一次：四个 Phase-A create Batch 均完成
dry-run/apply，业务切片在 workspace `1dc0698513e253e72c282eedb8b234d2b5764c7ddaf9326bb8181160669adce3`
durable；两个目标被放入同一 delete-only Batch 时，平台以 `conflicting_item_effects` 在 dry-run 阶段
fail closed，因此没有执行删除且两个 unknown 仍存在。该运行已以 `platform-contract` terminal failure
收口，strict replay 为 `cap/count/active=20/18/0`，剩余两次授权。

Phase B 现在必须把两个冻结目标分别放入两个按候选顺序排列、单目标且 receipt-bound 的 delete-only
Batch，禁止合并或重排。后续 start 在 readback 确认 start19 的四个 Phase-A 实体均存在时，使用完整的
8-item continuation candidate：四个 Phase-A existing refs、两个目标 refs 和两个有序 delete declarations，
不得重新创建 Phase-A 资源。首次完整 semantic PASS 后停止，不为消耗剩余额度继续启动。

start20 使用上述 8-item continuation 完成了两个有序单目标 Phase-B delete apply，并在 workspace
`18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0` 读回四个 Phase-A 实体仍在、
两个目标及其 incident statements 不存在；validation conforms、reasoning consistent，governed retrieval
返回完整 supported/lineage 结果。独立 tester 在同一冻结图上按批准 source 验证 CQ-001/CQ-002 均为
current/usable PASS。形式化 Acceptance Agent 未启动：旧 Runner 进程在构造 handoff 时把正整数 revision
直接送入 safe-string `slice_revision`，两次以 `-32001` 拒绝；该 003-only decimal projection 已由 commit
`8b1a999` 修复，但运行中进程不能热加载。start20 以 `platform-contract`、非零 mutation 终态收口，strict
ledger=`cap/count/active=20/19/0`。剩余一次授权不再用于重复建模；正式 in-run Acceptance handoff 仍是
未完成的机械门，不得把独立语义/CQ PASS 改写为完整 formal-run PASS。

### R2.3-003 Acceptance-only continuation

用户已确认不再重复 start20 的 Modeling/Protocol 写入链，而以一次独立 Acceptance-only continuation
补齐形式化验收。首次 `r23003-acceptance-only-start20-1` 因缺少撤钥后旧 key denial 证据而保留为
BLOCKED 历史轮；权威成功 continuation ID 为 `r23003-acceptance-only-start20-2`，复用 R2.3-002 Round 77/78
已证明的一次性 operational acceptance，不新增 Runner 模式、Task/Profile/Package、sidecar、backend API
或通用验收框架。

本轮精确绑定：

- retained run=`r23003-real-20260812-deepseek-start20`；candidate revision=`"2"`；candidate digest=
  `a5e1c2752b24a321e8aa8aa5e12664cf0dfdf0935c42c2ef4960785b0336b8cc`；
- Project=`7fc146d8-c76f-417b-9314-854544f269fc`；Ontology=
  `fd762f52-2f5e-4bc0-902a-5583135ab64d`；Graph Set=
  `277fd804-e485-5156-b7a7-ca6a1081f950`；workspace version=
  `18e4912e2ab90f808d4b31ab01befc1c0bea3471426abfc1e915cf27869157c0`；
- acceptance standard=`modeling_team/references/r2-3-003-acceptance-standard.json`；source manifest=
  `docs/evaluation-scenarios/ontology-modeling-team-r2-3-003/agent-input/manifest.json`；
- question order 只由 standard 的 ordered positive-N `competency_questions` 决定；当前 N=2，但流程、票据、
  轮次推进和 settlement 不得依赖 `cq-001/cq-002` 名称或固定数量。

操作边界：

1. 不调用 StartLedger，不 reserve，不产生 `semantic_start`，不启动 Modeling、Protocol 或 Producer
   Coordinator，不创建 Build Session/Lease/Batch，不执行 validation/reasoning mutation，不修改本体；最后一个
   已授权 semantic start 保持未使用。
2. 在 repo-local、gitignored 目录
   `workspaces/modeling-acceptance/r23003-acceptance-only-start20-1/` 冻结 operation-local
   `r2-3-003-acceptance-only-ticket/v1` ticket、standard/source
   digests、exact read request allowlist、before inventory 和唯一 evidence/output 目录。任何 live P/O/G/workspace、
   candidate binding 或 source digest 漂移都在 Agent 启动前 `BLOCKED/state-invalidated`。
3. 该 ticket 不调用 Producer `publish_ticket`、`build_acceptance_verdict` 或其 R2.3-005 handoff/五阶段 receipt
   validator；不得伪造 start20 未产生的 handoff。它必须直接包含 continuation/retained-run/candidate、P/O/G/
   workspace、model-state、standard、source-manifest、ordered CQ、request-allowlist 和 evidence-root digests。
   operation-local `r2-3-003-acceptance-only-verdict/v1` 必须绑定 ticket/model/source/two-report digests，并显式
   提供 `verdict,current,usable,failure_layer,blocked_reason` 与 question ordinal/count/previous/next/final。
4. Delivery 在 preflight 后只创建一把 host-owned、Project-scoped `read` 临时 key；所有 fresh Platform Examiner
   只获得 operation-local proxy capability，不获得明文 key。代理只暴露冻结的最小 read operations：Ontology
   modeling context/read model/entity statement context、P/O-scoped semantic context query，以及 G-scoped validation/
   reasoning run read。每条 allowlist 固定 `tool,method,path_template,body_schema 或 body_digest,P/O/G scope`；代理
   在 backend 调用前拒绝未知 tool/path/字段和 scope 漂移，禁止静默参数裁剪，并持久化真实 pre-send request
   digest、response digest 与 artifact。最后一题完成后 exactly-once revoke，验证旧 key 401/403。
5. 一个 fresh、持久的 Acceptance Agent 按 standard 顺序处理全部 N-CQ。同一题的 Source Examiner 只能读取
   ticket question 与该题 approved source bytes；Platform Examiner 只能读取 ticket 与上述冻结 model state，
   不得看到 source bytes、历史答案或 tester verdict。Acceptance 只接收两份 typed report 与 standard/ticket，
   不直接读取 source 或平台，不修复模型。
6. 每题必须在前一题 `PASS` 且 `current=true,usable=true`、两个 fresh Examiner 已清理、model-state digest 未变后
   才能进入下一题。`FAIL` 或 `BLOCKED` 立即停止；最终 settlement 要求按 standard 顺序恰好 N 份 typed verdict，
   每份绑定 ticket/model/source/report digests，并且全为 current/usable PASS。
7. 主协调者只核对 operation-local envelope schema、identity/digest、request allowlist、轮次顺序、exactly-one
   key create/revoke、before/after 不变和清理；
   不把已有独立 CQ 结论预填给 Agent，不以脚本判断业务答案，不把 start20 的 historical handoff failure 改写。

该 Acceptance-only continuation 的 PASS 可以关闭 R2.3-003 的 formal Acceptance 完成门，但只证明 retained
start20 final state 上的独立 N-CQ 验收；它不证明旧 Producer 进程内 handoff 热加载成功，也不把 operational
流程提升为 L3 产品能力。

2026-08-12 最终结果：`r23003-acceptance-only-start20-2` 以 canonical ticket digest
`6134dcf73d9b46f86bc81afd1574c70a2c316fcf1973a81e275f23a5963190b0` 完成 N=2 ordered settlement；
CQ-001/CQ-002 均为 `PASS,current=true,usable=true`。独立 Round43 重放 ticket/verdict/report digest、exact
read audit、单一 Project read key create/revoke、撤销后旧 key HTTP 401、DB revoke、model/ledger 不变量、
cleanup 与 service health 后全部 PASS。该 operational continuation 未消费 semantic start，未修改本体。

R2.3-003 非目标继续包括：

- 删除两个目标 ExplicitUnknown 之外的 Start75 资源，或在解析结果/新 Evidence 未原子写入时提前删除；
- 普通 numeric score 阈值、其他 diagnostic、人工 review 工作流或更多发布案例；
- Pi Runtime；
- 长期 Project 生命周期管理或管理 UI。

## R2.3-006 精简隔离 Examiner Runtime

当前状态：`已实现；三次授权 operation（live-4/5/6）已全部消耗：live-4 为 Platform 单波读取后 90 秒 child
watchdog（child-timeout），live-5 为 Platform report receipt-count mismatch（acceptance-evidence），live-6 为
Acceptance child 3 steps 后无 terminal report 触发 child-timeout；清理/不变性/零残留与 typed failure 证据
独立 PASS，语义完成门（ordered N=2）未通过，需新的 operation authorization 做真实 N=2 复验`

### 背景与问题

R2.3-003 的成功 Acceptance-only retry 证明当前 read-model 足以回答两道 CQ，但实际 Examiner 运行暴露了
编排和上下文边界问题，而不是主要的平台查询性能问题：

- Platform Examiner 单次模型调用输入约 26k–33k tokens，其中绝大多数是可缓存的系统、项目、memory、
  skills、插件和协作说明；每题又经历 13–17 次模型调用，累计 token 被重复计算；
- 两个 `get_ontology_read_model` HTTP 请求各在约 1 秒内完成，说明接近两分钟的 Examiner 墙钟时间主要来自
  大上下文、多轮澄清、协作消息和 Host 人工转发；
- Platform Examiner 启动时缺少完整 CQ、P/O/G、请求 envelope 或 digest 规则时，会向主 Agent/Acceptance
  追问；Platform 与其他 Examiner 的协作通道也未机械关闭。这削弱了 fresh Examiner 的独立性；
- Source/Platform Examiner 继承了大量与单题语义判断无关的工程历史。约 25k cached prefix 不是 25k 份不同
  数据，但仍说明 role runtime 没有按最小任务包隔离。

### 目标行为

1. 每个 Source Examiner 和 Platform Examiner 都是 fresh、无主线程对话继承的独立运行实例。Host 注入的
   role task packet 必须显式且完整；平台强制的 system/safety 指令可以保留，但主会话历史、memory summary、
   插件目录、无关 skills、开发/提交规则和其他 CQ 记录不得成为 role task context。
2. Source Examiner 只获得当前 CQ、该题 approved source bytes/path+digest、source-report schema 和最小角色
   约束；不得读取平台结果、其他 CQ、历史答案或 tester verdict。
3. Platform Examiner 只获得当前 CQ、冻结 P/O/G/workspace/model-state digest、operation-local read proxy
   capability、exact request schema 和 platform-report schema。它直接调用 proxy；proxy 返回 structured
   response、canonical request digest 和 response digest。Examiner 永远不获得 plaintext key。
4. Platform Examiner 不得向主 Agent、Acceptance、Source Examiner 或其他 Agent询问 CQ 语义、scope、schema
   或查询结果。Source Examiner 同样不得联系 Platform Examiner。必要输入缺失或不合法时立即返回 typed
   `BLOCKED/acceptance-input`；平台读取失败返回 `BLOCKED/platform`，source 不可读返回
   `BLOCKED/source-missing`。
5. 每题启动一个 fresh Acceptance Agent，只获得 ticket/standard、当前题两份 typed reports 及其 digests、
   question ordinal/count 和 verdict schema；不得读取批准 source bytes、平台 raw response、主线程历史、前题
   report 或已有结论。Host 在前一题 typed PASS 后机械启动下一题并聚合 ordered verdicts；Acceptance 不积累
   persistent thread，不补问或修复 Examiner 输出。
6. Host/Delivery 只承担确定性机械：构造最小 task packet、关闭横向协作路由、提供 strict proxy、收集 typed
   output、校验 digest/order、撤销 key 和清理。Host 不解释 CQ、不人工转述查询结果、不替 Agent 生成报告。

### 当前最小范围

- 先只覆盖 formal semantic Acceptance 的 Source/Platform/Acceptance 三类 Agent；不重构 Modeling、Protocol、
  Coordinator 或通用 Codex 会话。
- 优先复用 R2.3-003 operation-local strict read proxy、typed report/verdict 和 positive-N 机制；不增加 backend
  API、领域专属 read model 或通用 Agent 编排框架。
- 不使用本次对话的 collaboration subagent 作为正式 Examiner；使用 Runner-owned、fresh thread/process 的受限
  role runtime。每个 child 的工具面只含其 role-private source/report 或 platform-proxy/report capability。
- `fork_turns=none` 只是候选机制，不单独作为验收证据。实现必须以实际首轮上下文清单/turn 记录证明没有
  主线程历史继承，并分别记录不可移除 platform prefix、role packet、source/read-response token 数。
- proxy 必须为每个允许 tool 固定 exact JSON argument schema；在进入 `McpReadForwarder`/backend 前拒绝未知、
  缢余、缺失或错误类型字段，禁止 schema-property filtering 后继续调用。拒绝证据必须显示 backend_calls=0。
- 每个 Examiner 正常路径最多 3 个可观测 inference steps；缺输入不得通过协作追问增加轮次。role packet（不含批准 source
  bytes、平台 response 和不可移除 system/safety prefix）目标不超过 4k tokens。
- 本地 accepted baseline 的性能目标是单个 Examiner 通常不超过 60 秒、不得超过 90 秒；外部 provider 故障或
  限流必须单独分类，不可用放宽语义/隔离边界来换取速度。确定性完成门以无历史继承、无横向询问、最多
  3 turns 和直接 proxy 调用为主，墙钟时间作为必须报告的性能门。
- 先修上下文与编排。只有在精简后 Platform Examiner 仍因事实缺失或关联表达不清无法在 3 turns 内完成时，
  才评估通用 `query_semantic_context`/关联事实投影；不得为某个 CQ 添加业务专属 API 或返回字段。

### 验收

- 使用 R2.3-003 retained final workspace 的 CQ-001/CQ-002 做只读验证，不创建 semantic start，不修改 ontology
  或 ledger；需要新的 operation authorization，但不消耗 003 已关闭的剩余授权。
- 对每题证明 Source/Platform fresh、上下文输入清单符合角色边界、横向协作请求在发送前被拒、缺字段得到
  typed BLOCKED、Platform 直接通过 proxy 获得 structured response+digests、Acceptance 只基于 typed reports
  裁决。
- 正常 N=2 必须产生 ordered `PASS,current=true,usable=true`，并通过 N=1/3/5 的机械顺序测试；旧 R2.3-003
  结论只能作为预期回归事实，不能注入 Examiner task packet。
- 记录每个 Agent 的 first-call/total/cached/task/evidence tokens、模型调用次数、time-to-first-token、总墙钟时间、
  proxy HTTP 时间和协作拒绝证据，以区分模型、编排和接口耗时。
- Runner-owned operation metrics 必须记录：fresh thread identity、Host 发出的 canonical `first_turn_input` 清单/
  digest、`turn/start` 数量、每次累计 token-usage 增量（或 provider 等价精确事件）、TTFT 和 terminal time。
  未收到完整 metrics 时不得宣称本需求性能 PASS；第 4 个 inference step 到达前必须中断并返回
  `BLOCKED/runtime-budget`。实现前先以真实 Codex App Server 小探针确认 token-usage 事件名与粒度。
- key create/revoke exactly once、post-revoke 401/403、零 plaintext/process/socket residue、model/ledger 前后不变，
  且 R2.3-005/default Agent 路径无行为变化。

### 非目标

- 不把项目 AGENTS、安全规则或系统指令全局删减；只控制 Examiner role task context。
- 不追求跨机器调度、多租户策略、通用 Agent 沙箱、长期审计服务或新的管理 UI。
- 不因性能目标减少 source fidelity、model-state binding、fresh Examiner、typed report 或独立 Acceptance。
- 不重新执行 R2.3-003 语义建模，不恢复已删除 unknown，不使用其未消费授权启动新需求。

## R2.3-004 Pi Team Adapter

当前状态：`待细化`

优先级：`P1`

### 现状是什么，需要改成什么

当前：

- R2.3-001 只实现 Codex Team Adapter；
- 团队合同已经避免 Codex 专有字段，但尚未由第二个真实 Runtime 验证；
- R2.0-002 已有 Pi Local Runtime、多角色、RPC、事件和 Workflow Package 证据，但角色与
  R2.3 Team Profile/Agent Package 合同不同。

目标：

- 实现完整 Pi Team Adapter；
- 单次运行中的 Coordinator、Modeling、Protocol、Acceptance 和其他临时子 Agent 全部使用 Pi；
- 复用 R2.3-001 的 Team Runner、Profile、Agent Package、通信、用户对话、权限和终态合同；
- 不修改 Semantic Platform Core 或增加 Pi 专属平台接口。

R2.3-004 只有在 R2.3-005 的 Modeling Team Runner 运营基线和 R2.3-003 的已有模型增量证据均完成后
才可开始；Pi Runtime 的替换不能倒置或绕过该顺序。

### 已确认范围

- R2.3 不支持 Codex/Pi 混合团队；
- 本需求排在 R2.3-005、R2.3-003 之后；R2.3-005 的可重复 Modeling Team invocation 是进入本需求的
  运营前置，不由 Pi Adapter 的首次实现反向补足；
- Pi 可以使用 Runtime-native Session、RPC、事件和 Workflow Package 装载，但角色语义与 Skill
  内容必须继续共享；
- Pi Adapter 至少复现 R2.3-001 的基础角色能力和额外真实 Agent 互操作冒烟；
- 是否使用 R2.3-002/003 业务切片完成真实 Pi 建模，在 R2.3-004 开始前单独细化；
- Pi Runtime 故障不能成为平台事实，平台写入仍只由 Protocol 通过公开接口完成。

### 2026-08-05 R2.3-005 start12 retrieval-focused repair contract

start12 的语义写入、验证、推理和负向探针已成功，但 Protocol 将两条 CQ 合并到一次
`hybrid` 查询，未消费 `next_match_cursor`，并以实体回读替代通用召回完整性；该路径保持
`platform-contract` 阻断，不修改历史运行证据。后续 fresh scope 只修复以下窄合同：

1. `query_semantic_context` 必须绑定 run-owned `project_id`、`scope_mode=ontologies` 和精确
   `ontology_ids`；ticket、run、model-state 只进入 Protocol receipt/Acceptance handoff。
2. 每条 CQ 独立、使用窄 `resource_types`；`vector_index_missing` 或 degraded hybrid 结果
   必须改用 lexical，不能当作完整召回。
3. 每个 match page 先只消费 `context_cursor` 至 `next_context_cursor=null` 且不截断，再只用
   `next_match_cursor` 进入下一 match page，并为其建立新的 context 链；两类 cursor 不能同时
   传递或跨页复用。全部链完成前不得报告 retrieval complete。
4. 每个 candidate citation 必须逐项绑定 inline Evidence `{document_name, excerpt}` 或现有
   reference ID；额外 source digest/location/owner-answer 元数据留在 Protocol receipt/evidence
   binding，不伪装成平台字段，并在 apply/readback 核对 EvidenceReference、Association 与
   origin lineage。
5. 仅 generic retrieval complete/non-truncated 且 Evidence/lineage 门满足时可发出
   `ready_for_acceptance`；实体/事实 fallback readback 不能替代该门。start13 必须使用全新
   Project/Ontology 和完整 self-contained candidate，复用 start12 的语义经验而非历史状态。

### R2.3-004 初始完成门

1. Pi Adapter 实现 R2.3-001 冻结的 Runtime Adapter 操作。
2. 一个 homogeneous Pi team 可以装载相同 Profile、Agent Package、instructions、Skills 和权限。
3. Pi Coordinator 可以持续接收用户消息、调度固定 roster 并汇总 Agent 终态。
4. Pi Agent 可以直接通信，Protocol 仍是唯一平台写入角色。
5. Pi 角色能力冒烟、停止、最小状态和清理 PASS。
6. 真实建模范围按 R2.3-004 后续细化合同通过独立验收。

### R2.3-004 非目标

- Codex/Pi 混合团队；
- 修改 Team Runner 核心语义以迁就 Pi；
- Pi 专属平台 API、数据库 Schema 或后台 Runtime 服务；
- Runtime 横向质量优劣结论，除非后续细化明确增加对照实验。

## R2.3-002 Round 76 活动修订：Coordinator 驱动的独立 Agent 语义验收

用户于 2026-08-02 明确改变当前路线：业务切片的语义 PASS 必须由一个全新上下文、独立、只读的
Acceptance Agent 基于批准来源和 retained live platform state 作出，不再由 P2a driver、native verifier、
native-proof 固定程序、Round75 continuation 或 Producer Agent 自述充当语义验收权威。本节是
R2.3-002 最新 current-minimal 合同；凡 Round59～Round75、Matrix/P2a gate、设计或测试计划中要求以
official P2a gate、native `complete=true`、Driver terminal stage 或 fresh `t` 作为当前完成前提的文字，
均被本节替代并只保留为历史证据。未冲突的 source fidelity、Protocol-only 写入、dry-run/apply
完整性、Evidence/lineage、清理与 literal 范围裁决继续有效。

### 当前最小角色与流程

1. Coordinator 为一个简单业务切片冻结唯一 acceptance ticket。Producer Agents 完成该切片后只可
   报告 `ready_for_acceptance`，不得自判 PASS，也不得在 ticket 冻结后继续修改该 revision。
2. Coordinator 请求启动一个全新的 Acceptance Agent。该 Agent 不复用 Producer Agent、thread、
   session、transcript、隐藏答案或本地工作目录；它只接收 ticket、批准来源和 ticket allowlist 中的
   只读平台工具。
3. Acceptance Agent 直接读取批准来源和 ticket 绑定的实时平台状态，独立检查 source fidelity、
   slice scope、ontology structure、explicit unknowns、validation/reasoning、governed retrieval、
   Evidence/lineage 以及全部 competency questions。它不得把 Producer rationale、自述、Driver stage
   或机械 helper 成功当作这些检查的替代证据。
4. Acceptance Agent 返回一个绑定 frozen ticket/revision/digest/model state 的结构化
   `PASS|FAIL|BLOCKED` 结果。Coordinator 只验证信封、绑定和证据可读性并执行路由，不得改写 verdict。
5. `PASS` 只接受 ticket 中冻结的 slice revision 和 model state。`FAIL` 必须由 Coordinator 按
   `modeling-quality|interview|protocol-delivery|platform|runtime` 路由给对应责任方；修复产生新 revision
   后必须启动新的独立 Acceptance Agent/round。`BLOCKED` 表示批准来源、只读工具、live state 或时间
   边界不足以作出诚实判断，不得降级成 PASS；解除阻塞后同样新建验收轮次。
6. 允许逐切片验收；所有被集成的 slice revision 均 PASS 后，再由新的独立 Acceptance Agent 对冻结
   集成 model state 做一次集成验收。早期 slice PASS 不自动覆盖后续 revision 或集成状态。

### 最小 acceptance ticket

Coordinator 冻结的 ticket 使用以下最小 JSON 形状；数组顺序和 canonical compact JSON SHA-256
共同形成 `ticket_digest`，ticket 发布后不可原地修改：

```json
{
  "schema_version": "r2-3-002-slice-acceptance-ticket/v1",
  "ticket_id": "acceptance-ticket-001",
  "slice_id": "simple-slice-001",
  "slice_revision": "revision-1",
  "producer_run_id": "producer-run-id",
  "model_state": {
    "project_id": "project-id",
    "ontology_id": "ontology-id",
    "workspace_version": "workspace-version",
    "source_signature": "source-signature",
    "build_session_id": "build-session-id"
  },
  "model_state_digest": "64-hex-canonical-model-state-sha256",
  "source_bundle_digest": "64-hex-approved-source-bundle-sha256",
  "competency_questions": [
    {"id": "cq-001", "question": "bounded business question"}
  ],
  "allowed_read_tools": ["approved-read-tool"],
  "timeout_seconds": 600
}
```

`timeout_seconds` 必须为正数；当前简单切片默认 600 秒，未经用户明确授权不得超过 1200 秒。
`allowed_read_tools` 必须是本轮预检通过的只读 allowlist，不得包含 Modeling Batch submit/apply、
Build Session/Lease mutation、credential mutation、删除或其他平台写操作。validation/reasoning 仅可使用
不改变 retained model state 的现有读取/计算入口。ticket 不携带 Producer transcript、预期答案、
tester-only hidden answer、PASS 提示或修复建议。

### 最小 acceptance result

Acceptance Agent 返回以下最小结构；`ticket_digest`、slice/revision、source digest、完整 `model_state`
及其 digest 必须与 ticket 完全一致：

```json
{
  "schema_version": "r2-3-002-slice-acceptance-result/v1",
  "acceptance_round_id": "acceptance-round-001",
  "ticket_id": "acceptance-ticket-001",
  "ticket_digest": "64-hex-canonical-ticket-sha256",
  "slice_id": "simple-slice-001",
  "slice_revision": "revision-1",
  "model_state": {
    "project_id": "project-id",
    "ontology_id": "ontology-id",
    "workspace_version": "workspace-version",
    "source_signature": "source-signature",
    "build_session_id": "build-session-id"
  },
  "model_state_digest": "64-hex-canonical-model-state-sha256",
  "source_bundle_digest": "64-hex-approved-source-bundle-sha256",
  "verdict": "PASS",
  "failure_layer": null,
  "checks": {
    "source_fidelity": "PASS",
    "scope": "PASS",
    "ontology_structure": "PASS",
    "explicit_unknowns": "PASS",
    "validation_reasoning": "PASS",
    "governed_retrieval": "PASS",
    "evidence_lineage": "PASS",
    "competency_questions": "PASS"
  },
  "competency_question_results": [
    {"id": "cq-001", "status": "PASS", "answer": "grounded answer", "evidence_refs": ["evidence-ref"]}
  ],
  "evidence_refs": ["approved-source-or-live-platform-reference"],
  "summary": "bounded acceptance summary"
}
```

`PASS` 要求全部 checks 和 competency questions 均 PASS，证据足以复核且 live model state 与 ticket
完全一致。`FAIL` 的 `failure_layer` 必须是上述五类之一；`BLOCKED` 使用最接近的责任层并在 summary
说明缺失条件。任何 binding drift、写操作、超时、证据不足、静默截断、未消费分页、来源不一致、
业务范围外推、错误本体结构或未知被补造都不能成为 PASS。

### 所有权、只读边界与当前暂停项

- Coordinator 拥有 ticket、round identity、冻结/解冻和失败路由，但不拥有语义 verdict；Producer
  Agents 拥有建模与修复；Acceptance Agent 只拥有本轮只读检查和 result；Delivery Agent 只拥有
  transport、Runtime lifecycle、identity、credential/allowlist 配置、cleanup 和信封完整性。
- Acceptance Agent 不修复模型、不继续 Producer run、不发送 Modeling candidate、不调用写工具、
  不更改 retained evidence，也不向 Producer transcript 追溯答案。验收期间 ticket 绑定的 model state
  保持只读；任何写入都使本轮失效并要求新 ticket/round。
- 确定性代码只可验证 transport、lifecycle、identity、cleanup、canonical envelope/binding integrity。
  receipt、candidate/map、exact Batch planning 与其他已通过的机械 helper 可以复用，但其成功只证明
  机械前置条件，不能判定业务语义 PASS。
- P2a driver、native verifier、native-proof builder 和 Round75 continuation 仅保留为诊断、机械辅助或
  future/contingent 资产，不是当前 completion gate。Round75 real run 与 fresh `t` 立即暂停；当前路线
  不要求、不得创建或消费 official P2a gate。现有实现若仍强制该 gate，属于待修正 implementation gap，
  不是恢复 P2a 验收的理由。
- 当前仍不验证显式 datatype 或 language-tagged literal 的真实写入；Round71 的 plain-literal 与
  future R2.4-001 边界保持不变。
- current minimal 只选择能在短轮次内完成的简单业务切片。不得为此实现通用 orchestration、持久化
  acceptance framework、后台调度、管理 UI、自动修复或其他 L3 productization 能力。

### 更新后的 R2.3-002 完成门

R2.3-002 当前 completion gate 是：至少一个简单业务切片按上述 ticket 完成 Producer
`ready_for_acceptance`，由全新只读 Acceptance Agent 对 retained live state 返回绑定正确且证据充分的
PASS；若本轮包含多个已接受切片，则新的独立集成验收也 PASS；相关 Runtime/credential/temporary
resource cleanup 完成；历史 FAIL 与修复轮次保留。机械单测、Producer/Coordinator/Broker terminal、
P2a/native verifier/Driver success 或 plan-review PASS 均不得单独满足此门。

交付事实：Round78 简单业务切片已在保留的非空 Project/Ontology 上完成 Producer
`ready_for_acceptance`，最终全新只读 Acceptance Agent 对冻结状态的八项门全部给出 PASS；Context
Query 的两条分页链、SPARQL、Modeling Item Evidence/lineage、验证/推理与 CQ 均有直接证据。最终
临时 read key 已撤销并证明 HTTP 401，模型、workspace、source、StartLedger 与 Evidence 保持不变。
结果、失败历史、平台修复和清理摘要见本需求关联的 delivery record 与共享 test plan。

## R2.3-002 Round 76 plan-review High closure

本节接受并关闭 Round 76 计划评审的 H1～H4；它 supersede 上一节中与本节冲突的生命周期、凭据、
carrier 和 gate-free 实现文字，但不重写 Round59～Round75 历史。本节仍是 docs-only current-minimal
合同：不授权代码、配置、测试、真实 Agent、平台写入、semantic start、gate 或 commit。

### H1 closure：有界两阶段 lifecycle

当前实现事实是 `TeamTransportBroker.report` 只接受现有 `completed|blocked` terminal status，且
`TaskResult` 是不可重复的 Agent 终态；`TeamRunner` 只在三个 terminal result 都存在且 Runtime
`wait_settled` 成功后发布 session-level `settled`。不得为验收新增 Broker status，也不得把
`ready_for_acceptance` 塞入 `TaskResult`。

新生产轮使用以下有界两阶段流程，而不是通用 orchestrator：

1. Producer team 保持现有 Coordinator/Modeling/Protocol roster 和 Broker。Protocol 完成正式写入与
   readback，Modeling 冻结 slice revision；Coordinator 在自己的 `completed` terminal 前，通过新的
   task-scoped、local-only `publish_acceptance_handoff` 工具一次性发布 canonical ticket。这个
   `ready_for_acceptance` signal 是独立 handoff artifact，不是 Broker result/status。
2. 三个 Producer Agent 仍分别通过 `report_task_result(status="completed")` 终止；只有三者均
   `completed`、session 已 `settled`、ticket/handoff retained 且非空后，Delivery 才结束全部 Producer
   Runtime，将其 runtime roots 封存为只读历史证据，并撤销/销毁全部 Producer write credentials。
   Project、Ontology、
   workspace、source-bound model evidence 必须保留且保持非空。
3. Delivery 重新核对 retained handoff、Producer cleanup receipt 和 ticket binding 后，才在独立
   runtime root/session/thread/credential 中启动一个 Acceptance sidecar。任何 Producer Runtime 仍活跃、
   write credential 仍有效、terminal 非 completed、未 settled、handoff 缺失或 retained state 漂移都
   阻止启动并形成 `BLOCKED/runtime` 或最接近的明确层。
4. Acceptance sidecar 通过独立 `submit_acceptance_result` carrier 一次性把 result 交给 Coordinator/
   项目管理协调层。它不修改三个 Producer terminal record。若未来把 verdict 摘要送回原 Coordinator
   thread，只能是可选、非权威、无工具的 user-facing summary；该 thread 的可用性和 summary 成功都
   不是验收或需求完成前提。

对已清理并 retained 的 `r23002-real-20260801s` 允许一个严格 bootstrap 例外：新的协调 Agent 可基于
retained rev7 handoff 和已 settled/cleanup evidence 冻结 bootstrap ticket，即使历史三个 terminal 是
`blocked`。它不得继续任一旧 Producer session、不得修改旧 terminal、不得开启新 Producer run 或
fresh semantic start。此例外仅用于验收已有 retained `s`，不能放宽后续生产轮的三 completed 门。

### H2 closure：真实 read-only surface 与最小缺口

代码现状已按 `backend/app/security/auth.py`、`backend/app/security/http.py`、
`backend/app/mcp/runtime.py` 和 MCP tool registrations 核对：API key 目前只有 `read|model|admin`
scopes，`model` 蕴含 `read`，`admin` 蕴含 `model+read`；project-scoped `read` key 已可由
`POST /api/api-keys` 创建并由 `POST /api/api-keys/{key_id}:revoke` 撤销。MCP `_authorize_tool`
会在每次调用时重读 key、拒绝 revoked key，并验证 Project-owned resource。当前 key record 只原生
绑定 `project_id+scopes`，不原生保存 Ontology/ticket/round 或逐工具 allowlist；不得虚构这些能力。

当前最小 credential lifecycle 因而采用两层绑定，不改数据库或安全模型：Delivery 使用 host-owned
admin 能力创建一个独立、project-scoped、仅 `read` 的 acceptance key；local immutable credential
manifest 绑定 key ID、Project、Ontology、ticket digest、acceptance round、创建 receipt 和 sidecar
config digest；独立 MCP config 只注册 ticket 的精确 read allowlist。admin/model/Producer key 均不得
进入 sidecar。sidecar 结束（包括 timeout/crash/BLOCKED）后必须撤销 read key、销毁 plaintext/runtime
secret，并保留 revoke/audit receipt；撤销后任何调用必须失败。

当前已存在且可按 ticket 选择的只读 MCP 工具为：

- identity/state：`check_platform_health`、`get_project_build_context`、`get_build_session`、
  `get_modeling_context`、`get_build_context`、`get_ontology_workspace_context`；
- model/retrieval：`get_ontology_read_model`、`get_semantic_read_model`、
  `query_semantic_context`、`semantic_sparql_query`、`describe_semantic_graph_set`、
  `list_semantic_derived_pointers`、`inspect_semantic_projection_status`；
- Evidence/lineage：`list_evidence_references`、`get_evidence_reference`、
  `get_ontology_lineage`、`inspect_semantic_statement_provenance`。

实际 allowlist 必须取该 ticket 所需的最小子集，不能默认暴露整组。`run_semantic_validation` 和
`run_semantic_reasoning` 在现有 policy 中均要求 `model` 且 `mutates_state=True`，验收明确禁止调用。
REST 已有 `GET /api/semantic/validation-runs`、`GET /api/semantic/validation-runs/{run_id}` 及 reasoning
对应接口，但当前 MCP 没有这些 list/get read wrappers。最小实现面仅新增四个通用、
Project-owned、`read`、`mutates_state=False` MCP wrapper：
`list_semantic_validation_runs`、`get_semantic_validation_run`、
`list_semantic_reasoning_runs`、`get_semantic_reasoning_run`。list 必须带 ticket-bound graph-set/
Ontology scope，get 必须解析 run owner；它们只复用现有 read service，不改变语义服务或数据模型。
Acceptance Agent 读取 Producer 已落地的 validation/reasoning result，绝不新建或重跑。

### H3 closure：独立 carrier、typed references 与路由

Ticket/result 位于独立、local-only、task-scoped acceptance root，以 canonical compact JSON、SHA-256、
exclusive-create 和只读 mode 一次发布；不得使用 TeamTransport terminal `TaskResult` 承载。ticket 经
`publish_acceptance_handoff` 发布一次，result 经 `submit_acceptance_result` 提交一次；重复、覆盖、
symlink、越界路径、digest/binding drift 均拒绝。确定性 resolver 只验证 schema、allowlist、文件存在、
digest、ticket/model-state binding 和分页完整性，原样保存 Agent verdict，不判断业务语义。

Round 76 `evidence_refs` 改为以下 typed union，supersede 上一节的非结构化 string 示例：

- `approved_source` 精确字段：`type,ref_id,ticket_digest,source_bundle_digest,location,artifact_path,
  artifact_digest`。`location` 必须落在 ticket 批准来源中，artifact bytes 与 digest 一致；
- `platform_read` 精确字段：`type,ref_id,ticket_digest,model_state_digest,tool,request_digest,
  response_digest,artifact_path,page`。`page` 精确包含
  `ordinal,input_cursor,output_cursor,has_more,sequence_complete`；非分页响应固定 ordinal `0`、cursor
  为 null、`has_more=false,sequence_complete=true`。最后一页之外的每页必须形成无间断 cursor chain，
  且只有最后一页可 `sequence_complete=true`。

Result 的 `failure_layer` 对 `PASS` 必须为 null；对 `FAIL` 和 `BLOCKED` 都必须明确为
`modeling-quality|interview|protocol-delivery|platform|runtime` 之一。证据缺失、只读能力缺口、凭据/
Runtime/timeout 或 binding 问题按责任归因成 `BLOCKED`，不得伪装成语义 `FAIL`。固定 owner map 为：
`modeling-quality -> Modeling`、`interview -> Coordinator/user`、`protocol-delivery -> Protocol`、
`platform -> repository developer`、`runtime -> Delivery/runtime`。owner 不在当前 roster 时，Coordinator/
项目管理层保留 verdict 并标记外部委派所需的 `BLOCKED`；禁止改写 verdict、让 Acceptance Agent 修复，
或启动通用 auto-repair。

### H4 closure：新的 acceptance-only gate-free surface

不得复用或修改 `modeling_team/tasks/r2-3-002-t.yaml` 与
`modeling_team/profiles/r2-3-002-t.yaml`。后续最小实现创建三个独立资产：

- `modeling_team/tasks/r2-3-002-acceptance-s.yaml`：只引用 frozen acceptance ticket、批准来源和 CQs；
- `modeling_team/profiles/r2-3-002-acceptance-sidecar.yaml`：只有一个 `acceptance` Agent；
- `modeling_team/references/r2-3-002-acceptance-sidecar-config.json`：绑定 runtime root、ticket/result
  carrier、read credential manifest、timeout 和精确 tool allowlist。

三者必须显式不含 `expected_matrix_binding`、`semantic_start`、StartLedger mutation、P2a/native verifier/
native-proof/official gate path 或 tool，并在 sidecar filesystem/MCP surface 中不可访问这些资产。

第一个目标不是 fresh `t`，而是 retained `r23002-real-20260801s` 的简单子切片
`retained-s-c-published-output`：只回答 B 实际绑定 C 的哪个已发布版本及消费哪个 Output。bootstrap
ticket 必须在启动前通过真实只读重读绑定 retained Project
`436040de-fbd4-47b5-8711-a95416379ea0`、Ontology
`e48272ff-bb82-4784-93e4-ccb39144e78d`、workspace version
`7243849bf3c1d821bcb4852715f84e1dfa94f85a6097cdb5183adfe16976002a`、source signature
`b4b185ff1900edba0e46f72db4b6c633`，以及 approved source manifest
`workspaces/modeling-runs/r23002-real-20260801s/source-manifest.json` digest
`20edb54595b8b4e3214b03b67fe5b357962f0d11ce5e928345126f4ce17d0b5c`。retained handoff digest 另绑定为
`98b2968fd04313bd8bc74efbbfe89a8f3f4ec42dce4d7c7abcfb2e9a49a3eafb`；它是候选 handoff，不是答案或
semantic oracle。任一实时 binding 不匹配、Project/Ontology 不可读或所需 read wrapper 未实现都返回
明确 `BLOCKED`，不得回退 P2a、不得创建 official gate、不得启动 fresh `t` 或消耗剩余 semantic start。
该简单切片继续不验收真实 explicit datatype 或 language-tagged literal 写入。

## R2.3-002 Round 77 Agent-first operational acceptance reduction

本节 supersede Round 76 中要求先实现 acceptance loader/profile、integrated sidecar、local carrier/
resolver、security/response proxy、per-Ontology policy enforcement 和 validation/reasoning MCP wrappers
的 current-minimal 文字；这些能力全部移到 future productization，且只在一次真实 operational
acceptance 后按证据重新评估。Round 77 先以现有 collaboration/team Agent 机制跑通一次，不创建新的
`modeling_team` roster、Task/Profile/Package/Runtime 产品面。

### 一次性操作流程

1. 主协调者/项目管理 Agent 在 repo-local、已由 `workspaces/` gitignore 覆盖的唯一目录
   `workspaces/modeling-acceptance/<acceptance_round_id>/` 冻结一次性 canonical ticket JSON、批准来源
   副本/只读路径、request allowlist 和唯一 `evidence/` 目录。ticket 延续 Round 76 的 identity、state、
   CQ、verdict 与 typed-ref 合同，并直接增加 `base_url,graph_set_id,validation_run_id,
   reasoning_run_id,request_allowlist,approved_source_paths,evidence_dir`；不需要 loader 或 carrier。
2. Delivery Agent 只做机械工作：核对 retained state/owner、记录 before inventory，使用现有
   `POST /api/api-keys` 创建精确 Project 且 `scopes=["read"]` 的临时 key，启动/观察独立 Agent，结束
   后用 `POST /api/api-keys/{key_id}:revoke` 撤销并验证旧 key 已失效，最后记录 after inventory 与清理。
   host admin secret 只归 Delivery；admin/model/Producer secret 不交给 Acceptance Agent。
3. 主协调者通过当前 collaboration/team agent 机制直接启动一个 fresh independent Acceptance Agent。
   它不属于 `modeling_team` Producer roster，不继续旧 session，只接收临时 read key、base URL、ticket、
   批准来源和 request allowlist。对象固定为 `r23002-real-20260801s` 的
   `retained-s-c-published-output`；不启动 Producer、fresh `t`、semantic start、P2a 或 official gate。
4. Agent 的平台访问只读，但可写自己唯一 `evidence/` 目录，保存 request record、原始 response、SHA-256、
   typed refs 和 Round 76 结构的最终 `PASS|FAIL|BLOCKED` JSON。它不得写 retained run/source/evidence，
   不得修复模型。主协调者只人工/机械核对 ticket binding、JSON 可读性和 evidence 路径后按五层路由，
   不用程序判定语义。FAIL/BLOCKED 的修复由外部 owner 完成并另开 fresh round。

本轮不实现 request proxy；allowlist 是冻结合同和事后审计边界，不是通用强隔离声明。Agent 每个请求都
必须先写 `method,path,canonical_body_digest`，Delivery 保留 Agent request log、可用的服务访问证据及
before/after inventory。任何 allowlist 外请求、缺失审计、retained evidence/source 写入或状态变化都
使本轮无效并返回 `BLOCKED/runtime|platform`。

### 本地实验的 owner preflight

现有 API key 只绑定 Project，不绑定 Ontology。Round 77 仅因以下 fail-closed preflight 才接受该本地
实验边界：`GET /api/projects/{P}/ontologies` 必须只返回 ticket Ontology；Ontology response 的
`project_id` 必须为 P；workspace/modeling context 必须给出同一 Ontology、workspace version、default
graph set 与 source signature；graph-set response 必须为 `scope_type=ontology,scope_id=O`；所有目标
validation/reasoning item 必须返回同一 graph-set/source signature；Evidence reference 必须返回同一
Project，lineage 必须返回 O 且其 technical trace 只指向 G。存在第二 Ontology、任何 owner 无法确认、路径/
body 不能固定到 O，或 before inventory 与 ticket 不一致时，必须在启动 Acceptance Agent 前
`BLOCKED`。这不是多租户或通用 per-Ontology security proof。

### 静态核对后的 exact HTTP allowlist

固定身份为 P=`436040de-fbd4-47b5-8711-a95416379ea0`、
O=`e48272ff-bb82-4784-93e4-ccb39144e78d`、
G=`0780fc06-9448-5690-8cda-866bff2071e6`、validation run
V=`d2611eac-16ef-488b-83ad-59b926dfa3a4`、reasoning run
R=`8886c6e7-b14e-4c82-9dae-bdeb571504b2`。ticket 冻结以下 Agent requests，除此之外全部禁止：

| Method | Exact path/query or body template | Purpose/binding |
| --- | --- | --- |
| `GET` | `/api/projects/P/ontologies` | 必须仅返回一个 O，且 `project_id=P` |
| `GET` | `/api/ontologies/O` | `id=O,project_id=P` |
| `GET` | `/api/ontologies/O/workspace-context` | `ontology_id=O,default_graph_set_id=G,source_signature=ticket` |
| `GET` | `/api/ontologies/O/modeling-context` | `project.id=P,ontology.id=O,workspace.workspace_version=ticket` |
| `GET` | `/api/semantic/graph-sets/G` | `id=G,scope_type=ontology,scope_id=O,source_signature=ticket` |
| `GET` | `/api/semantic/validation-runs?graph_set_id=G&limit=200&offset=N` | 只接受 item `run_id=V,graph_set_id=G,source_signature=ticket`；N 从 0 按 200 增长到 `summary.total` 全消费 |
| `GET` | `/api/semantic/reasoning-runs?graph_set_id=G&limit=200&offset=N` | 同上，只接受目标 R 并全消费 |
| `GET` | `/api/ontologies/O/semantic-read-models/entities?include=asserted&allow_stale_derived=false&field_set=summary&limit=2000` | entity topology；响应绑定 G/source signature |
| `GET` | `/api/semantic/graph-sets/G/read-models/fact-audit-queue?include=asserted&allow_stale_derived=false&field_set=evidence&limit=2000&kind=asserted` | asserted facts 与 Evidence binding；响应绑定 G/source signature |
| `POST` | `/api/semantic/context:query`，初始 body 精确为下述 C1；后续 body 只可在 C1 增加响应给出的单一 `match_cursor` 或 `context_cursor` | 非变更 read-scope POST；两条 cursor chain 均消费至完成，响应 scope 必须 P/O/workspace/source 一致 |
| `POST` | `/api/semantic/sparql:query`，body 精确为下述 Q1 | 非变更 read-scope POST；`truncated=false` 且 scope 绑定一致 |
| `GET` | `/api/projects/P/evidence-references?search=S&limit=200&offset=N` | S 仅为 ticket 冻结的批准文档名；全分页，所有 item `project_id=P` |
| `GET` | `/api/ontologies/O/lineage?target_type=resource&target_id=L&include_history=false&max_depth=3&limit=200` | L 只允许 ticket 冻结的 invocation、C-v2 与 output resource IRI；`ontology_id=O,truncated=false` |

C1 是 canonical JSON：
`{"project_id":"436040de-fbd4-47b5-8711-a95416379ea0","scope_mode":"ontologies","ontology_ids":["e48272ff-bb82-4784-93e4-ccb39144e78d"],"query":"Which published version of C does B bind as a Tool, and which output does B consume?","resource_types":["instance","relation","fact"],"assertion_types":["asserted"],"search_mode":"hybrid","depth":1,"limit":20,"context_limit":100}`。
Q1 使用同一 P/O、`timeout_seconds=30,result_limit=2000`，其 query 精确为：

```sparql
SELECT ?s ?p ?o WHERE {
  VALUES ?s {
    <http://ontology-platform.local/semantic/entity/8f343d3e-275f-5c6e-818d-7f3e76f8f783>
    <http://ontology-platform.local/semantic/entity/f1f4dc71-6b79-5693-8cc0-4d2c03c6d01c>
    <http://ontology-platform.local/semantic/entity/eadf4b2f-bf91-5a76-83e0-a4fbd344d76d>
  }
  ?s ?p ?o .
}
ORDER BY ?s ?p ?o
```

S 只允许 `official/tools.mdx`、`sources/release-register.md`、`sources/workflow-landscape.md` 在批准来源
目录下的完整冻结路径；L 只允许上述三个 VALUES resource IRI。ticket 记录 C1/Q1 及每个 S/L request
的 canonical digest，不允许 Agent 改写 query、搜索其他文档或扩大 target。

当前 middleware 将 `POST /api/semantic/context:query` 和 `POST /api/semantic/sparql:query` 明确归为
`read`；其余 POST/PUT/PATCH/DELETE 均不在 Agent allowlist。虽然已有
`GET /api/semantic/{validation|reasoning}-runs/{run_id}`，当前 HTTP owner resolver 的 `run_id` 分支不解析
validation/reasoning run，因此 project read key 不能可靠使用它们；Round 77 只用带 `graph_set_id=G` 的
list routes，并在响应内匹配 V/R，不虚构 MCP wrapper 或修复 auth。

Delivery-only 请求是创建/撤销/读取 key receipt；不得进入 Agent allowlist。before/after inventory 至少
覆盖上述五个 state/owner GET、两个 run list、read models、Evidence counts、workspace/source signature
及 StartLedger/P2a/gate 文件状态。两次 inventory canonical digest 必须一致，唯一允许变化是临时 read
key 从 active 到 revoked。本轮仍不验证真实 explicit datatype 或 language-tagged literal 写入。

## R2.3-002 Round 78 fresh simple slice with inline Evidence

本节只 supersede Round77 的 retained-s 验收对象；其一次性 ticket、独立只读 Acceptance、请求审计、
五层 verdict 路由和非产品化边界继续有效。retained `r23002-real-20260801s` 仍是有效诊断/模型证据，
但 Protocol 实际提交的平台 Evidence 为空，不能被接受，也不得通过事后补证改写为 PASS。

### 唯一 fresh semantic start 与 Agent 所有权

使用唯一剩余的已授权 semantic start，且只创建一次 fresh Project/Ontology 和一个 deliberately small
slice：基于同一批准来源回答“B 绑定 C 的哪个已发布版本，以及 B 消费哪个 Output”。不启动 fresh t、
P2a、native verifier 或 official gate。当前 collaboration team 是执行机制：主 Agent 为 Coordinator，
另启 fresh、职责分离的 Delivery、Modeling、Protocol、Acceptance Agents；Modeling 与 Protocol producer
在可用时使用先前指定的 `terra-xhigh`，Acceptance 必须 fresh、independent 且不是 producer。

Delivery 独占 ledger 的一次 reserve/start、fresh resource、credential、request/evidence directory、service
health 和 cleanup 生命周期。ledger 最终必须相对基线精确 `+1`。失败且为空的 scope 可清理；已经 apply
且非空的失败模型必须保留诊断，不得删除。任何路径都不得再启动第二次语义建模。

### Modeling candidate 与写前 Evidence gate

Modeling 只接收批准来源和 CQ，不接收 expected answer。candidate 总计不得超过 12 个 semantic items，
只含回答 CQ 必需的 class/property/entity/relation/shape、明确 unknowns；每个 item 都必须内联至少一个
`evidence[{document_name,excerpt}]`，且 document/excerpt 可在批准来源中逐字定位。不得引用另一 run 的
`evidence_reference_ids`。为匹配现有 modeling-item origin lineage，本轮只允许这些类型的 fresh RDF
create items，不允许 delete 或 rule-only operation。Delivery/Protocol 在任何 semantic write 前检查实际提交的 candidate/batch item：
item 数量、逐项非空 evidence array、批准来源归属、范围和 unknowns；缺证、超限、越界或复用 P2a/其他
run Evidence 的 candidate 直接拒绝，且不得消耗 apply。

Protocol 只接收 candidate、冻结的 Project/Ontology/Session/Lease 和 write credential。它直接调用现有
平台 API、保持调用上下文、读取 actionable errors，并且只可修正 schema/identifier/request shape 等形式
payload，不得改业务语义。最多调用 3 次 dry-run，必须至少一次成功后才可调用最多 1 次
`apply_atomic`。成功 dry-run 中每个 `operation_plan` item 的 Evidence 必须非空，item 数和逐项 Evidence
数必须与实际 candidate/batch 对应；否则禁止 apply。apply 后的正式 readback 必须逐 item 得到非空且
归属 fresh state 的 EvidenceReference/Association IDs，并通过 Evidence search/list 与 modeling-item origin
lineage 反查到该 item 的 inline source。任何 apply 不确定性或需要语义修正的情况均为 BLOCKED，不允许
第二 semantic start；validation/reasoning 可由 Protocol/producer 在 write key 撤销前运行，Acceptance
只能读取既有结果。

### 独立只读验收与完成条件

Protocol readback 成功后，Delivery 停止 producer runtimes、撤销全部 write credentials，创建临时 fresh
Project `scopes=[read]` key，并冻结绑定新 P/O/G/workspace/source signature、validation/reasoning run、
source manifest、CQ、request allowlist 和 evidence directory 的 acceptance ticket。Round77 经静态核对的
既有只读 HTTP surface 按 ticket 的 fresh IDs 参数化复用：owner/context/graph-set、validation/reasoning
list、semantic/read models、`context:query`、`sparql:query`、Evidence search/list 和 lineage；不新增 wrapper、
proxy、carrier 或框架。Acceptance 从批准来源和 live platform 独立判断 source fidelity、scope、ontology
structure、unknowns、validation/reasoning、retrieval、Evidence/lineage 和 CQ，直接返回
`PASS|FAIL|BLOCKED`；确定性检查不得代替语义 verdict，Agent 不得修复或写平台。

本轮成功仅定义为：一个 fresh slice 获得独立 Acceptance Agent PASS；所有 write/read credentials 已撤销，
所有 runtime 已停止，非空模型及完整证据保留，StartLedger 相对基线精确 `+1`。任一检查失败都必须诚实
记录 FAIL/BLOCKED，不得发明 PASS。仍不声明验证了真实 explicit datatype 或 language-tagged literal
写入，也不据此定义任何新产品代码或通用安全/编排能力。

### Round 78 plan-review High closure — active canonical writer preflight

在任何 StartLedger reserve/start、semantic start、Project/Ontology/Session/Lease 或 credential 创建前，
Delivery 必须证明将接收本轮 HTTP 写请求的 active `ontology-platform.service` 正运行于 requirement-approved
canonical write mode：`product_write_mode=rdf_primary`（或后续权威 requirement 明确给出的精确等价值）。
当前 Settings 默认 `legacy_only` 明确禁止；不得仅从源码默认、静态 `.env` 或 shell 值推断 active mode。

fail-closed preflight 必须在同一证据目录保留并交叉绑定：`systemctl --user show/cat/status` 给出的 active/
running、MainPID、start timestamp、unit/environment；8001 listener PID/cgroup/cwd/command 确认其属于该 unit
和本 repo；从 backend 工作目录、按该 unit 有效环境执行的 `Settings()` redacted probe；以及用 Delivery-only
admin credential 对 `GET http://127.0.0.1:8001/api/semantic/canonical-mode` 的原始响应。只有最后一项返回
HTTP 200 且 `product_write_mode=rdf_primary`，并与 Settings/process evidence 一致，gate 才 PASS；同时保存
尚无 ledger reservation/start、semantic start 和 fresh resources 的 baseline inventory。

若配置缺失或错误，Delivery 只能在上述零-start 状态下将 gitignored `backend/.env` 或该 unit 的权威
systemd environment 中唯一的 `SEMANTIC_PRODUCT_WRITE_MODE` 改为 `rdf_primary`，不得改 tracked config 或
其他 semantic mode。随后运行 Settings parse/config probe，重启 `ontology-platform.service`，等待
active/running，保存完整 status，并用 `curl --fail` 验证 backend `127.0.0.1:8001/api/health` 和 frontend
`127.0.0.1:5173/`；再以新的 PID/start timestamp 重做 authenticated canonical-mode 与 Settings/process
binding proof。任一步不能安全修改、重启、健康验证或证明 active mode，均在 semantic start 前
`BLOCKED/platform|runtime`。ledger reservation/start 后，包括 cleanup 在内都禁止再改该配置；Round78
其余 inline Evidence、Protocol、Acceptance 和 cleanup gates 全部不变。

### Round 78 acceptance Evidence-layer correction

本节 supersede Round77/78 中把 `fact-audit-queue.evidence_bindings` 作为本轮 inline Evidence 完整性
前提的任何文字。平台合同分为两层：Modeling Batch inline evidence 持久化 EvidenceReference 与
`target_type=modeling_item` 的 EvidenceAssociation；applied RDF resource/statement lineage 再把资源或
语句连接到 originating Modeling Item。`fact-audit-queue.evidence_bindings` 则来自独立
FactEvidenceBinding API，当前不会由 Modeling Batch inline evidence 自动投影。

已保留的 Round78 Protocol readback 为 12/12 applied items、15/15 modeling-item associations、5 个
EvidenceReferences，并有 resource origin-lineage coverage；这证明 producer readback 链存在，不等于
Acceptance PASS。fact-audit 的 7/7 `missing_evidence` 观察也必须保留，但在 modeling-item origin chain
完整时既不证明 inline Evidence 缺失，也不得单独触发 FAIL/BLOCKED。

当前 source-fidelity/Evidence gate 精确要求：批准来源 EvidenceReferences 非零，excerpt 与 source digest
精确可核；所有 Associations 都指向当前 run 的 `modeling_item` IDs；batch/apply item IDs 能映射到 applied
resource/statement 的 origin lineage；每条 lineage 均 `evidence_status=supported`、`lineage_status=complete`、
未 truncated 且 warnings 为空；fresh Acceptance Agent 能独立沿该链回到批准来源。任何一项缺失仍
FAIL/BLOCKED，不得弱化 lineage，也不得借用其他 run 的 Evidence。

最新 read allowlist 因而保留 Round77/78 的 owner/context/model/query/run reads，并允许 ticket 精确冻结的
`GET /api/projects/{P}/evidence-references`、`GET /api/evidence-references/{E}`、
`GET /api/evidence-references/{E}/associations`、
`GET /api/projects/{P}/evidence-associations?ontology_id={O}&target_type=modeling_item&target_id={I}` 及 applied
resource/statement 的 `GET /api/ontologies/{O}/lineage`。fact-audit GET 可保留为诊断请求，但其
FactEvidenceBinding count 不进入 verdict gate。自动 FactEvidenceBinding bridge/projection 是 future generic
capability，不是当前完成前提，也不在本轮实现。允许基于已 apply 且未修改的模型创建新的 fresh
acceptance round/ticket/read key；这不改变模型、不 reserve/start ledger，也不消耗 semantic start。

### 2026-08-05 R2.3-005 explicit one-start authorization

用户在 start13 的 Protocol 收件停滞修复方向上明确追加一次真实语义建模启动授权。该授权不是新业务
切片：仍复用同一个简单 `C -> B -> A` 目标，并只在独立修复与新冻结 baseline 完成后串行使用。
正式账本的当前状态为 `cap/count/active=13/13/0`；本次用户授权使 isolated ledger 的 cap 从 13
增加到 14，成功接受的完整 modeling-quality 结果仍立即停止后续启动。

R2.3-005 的 formal ledger 保留普通授权的默认 `additional_starts=3` 约定；当用户明确给出不同数量时，
该条 `budget_authorization` 可以记录任意正整数的真实数量，本次协调层把用户的“一次”编码为 `1`。
`bool`、零、负数、非整数、错序、重复或并发落败的记录必须在同一账本锁下 fail closed，不得部分追加；
strict replay 与 `_start_cap` 必须按每条记录实际的 `additional_starts` 累计，而不是按默认值重放。
省略用户数量时协调层仍传默认 3，CLI 不通过省略参数隐式写入授权。

R2.3-002 的历史账本仍只接受精确 `+2`；R2.3-005 既有精确 `+3` 记录及其 JSONL 字节、顺序和重放结果
保持兼容。实现和确定性测试只使用隔离临时账本，不改写当前 canonical ledger；只有 Delivery 在开发、独立
测试和提交完成后，才可按本次授权追加一条 `additional_starts=1` 的正式记录。

### 2026-08-06 R2.3-005 start24 terminal outcome and prompt-contract state

Start24 `r23005-real-20260806t011151z-start24` continued the accepted r2 lineage without rebuilding the business
slice. Modeling produced the complete immutable `dify-cba-slice-r3` candidate from the frozen source material;
Protocol accepted it and completed dependency-ordered apply/readback, asserted-only validation, consistent reasoning,
and the required lexical cursor repair. The candidate and semantic digests are both
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`. The exact candidate is retained as the
gitignored, read-only pre-prepare carrier
`modeling_team/.continuations/r23005-start24-r3-exact-candidate.json` (carrier SHA-256
`9acce460e1e2d28712deaac4a9901cf2357f947fc54d853344cff41c2bacd806`, mode `0444`), mechanically extracted from
the retained start24 `delivery-3` bytes and bound to accepted `delivery-4`.

Acceptance did not start a ticket, Examiner, or verdict: the current Runner process was started before commit
`2173848`, so its formal `runner_capability` approval handler could not be rebound in place. Three immutable ticket
publication requests were declined. This is a `runtime/infrastructure` plus `platform-contract` `rebind-required`
outcome, not a modeling-quality failure and not an Acceptance PASS. The same-run process/thread is not safely
reattachable; a future authorized run must stage the carrier before `Runner.prepare` and use a fresh Runner process
with the repaired handler. The Runner's normal `action=stop` path then completed cleanup; all child turns/processes,
private credentials, sockets and secrets were removed, while the non-empty Project/Ontology was retained for
diagnosis. Project `62ea52c5-2077-4b15-a39b-9adbecd09e93`, Ontology
`fbd3faec-737a-4472-abab-2a43794e6659`, and both project/admin key receipts remain directly auditable; both keys
are revoked and non-active.

The canonical R2.3-005 ledger now records `cap/count/active=31/24/0`, strict replay PASS, 118 lines, and SHA-256
`ed91d6d882b94cc10157c8a5301ab28c024526461c5e878c08ee97c4428ac060`. Start24 has one terminal failure record
with `classification=runtime/infrastructure` and `complete_modeling_quality_result=false`; no start25 is implied
or authorized by this outcome.

The pre-start prompt repair required by the prior delivery is now bound to the real prompt surfaces and tests:

- Prompt A: Modeling distinguishes an accepted candidate receipt from platform/retrieval completion, and
  neither Modeling nor Protocol emits `ready_for_acceptance` or `silent_for_acceptance` before dry-run,
  apply/readback, validation, reasoning, and governed retrieval gates complete.
- Prompt C: Modeling and Protocol require source-grounded `evidence_citations` on every formal relation item before
  accepting the candidate; a missing citation is a complete-candidate conflict.
- Prompt D: Protocol freezes the complete query tuple and keeps context and match cursor chains separate,
  including a fresh context chain for every match page.
- Prompt E: Coordinator's canonical Acceptance-ticket schema, run-specific bindings, structured Protocol receipt
  handoff, Runner-built draft, and unchanged Coordinator publication are implemented by `ebea0eb`. Focused offline
  contract tests pass; a real Acceptance round is still required and no Acceptance-ready or PASS claim follows from
  this implementation result alone.

These prompt changes remain ordinary current-scope safeguards for R2.3-005 and do not add Consumer, mutation,
recovery, orchestration, or productization scope. Acceptance remains unproved until a future fresh Runner binds a
formal ticket and an independent Acceptance round returns a verdict.

### 2026-08-06 R2.3-005 Prompt E implementation review and evidence boundary

The platform-contract repair is commit `ebea0eb` (`Add R2.3-005 acceptance ticket pipeline`), building on prompt and
approval changes in `749b6bc` and `2173848`. It closes the Coordinator canonical-ticket gap without moving semantic
meaning into the Runner:

- Prompt-only defects fixed in the authoritative instruction surfaces: (A) an accepted candidate receipt is not
  full platform/retrieval completion and `ready_for_acceptance`/`silent_for_acceptance` are gated; (C) formal relation
  items require source-grounded citations; (D) the complete query tuple and context/match cursor chains are frozen.
- The E handoff now has a structured Protocol receipt path. Protocol must read the nested handoff contract and use
  Runner-observed artifacts; it may not hand-calculate receipt summaries, digests, pages, or paths. The stage
  validator and the prompt agree that readback uses `get_modeling_context` and rejects an inconsistent tool/mode.
  These are prompt/contract fixes in `modeling_team/agent-packages/protocol/instructions.md`,
  `modeling_team/references/acceptance-stage-handoff-contract.json`, and the Runner-owned validator in
  `modeling_team/acceptance.py`.
- Runtime/platform wiring fixes are separate from prompt guidance: completed Protocol MCP results are captured by
  the Codex runtime sink; immutable response artifacts are keyed by both request and response digests so the same
  request with different responses cannot overwrite; Protocol capability endpoints are staged, authorized, and
  cleaned by the Runner. The relevant runtime/Runner surfaces are in `modeling_team/runtimes/codex.py`,
  `modeling_team/runner.py`, and `modeling_team/capability_mcp.py`.
- The ticket-pipeline test helper uses a synthetic `submit_modeling_batch` payload to exercise carrier validation;
  that pseudo-schema is a test-fixture limitation, not a live platform acceptance or a replacement for the frozen
  `modeling-batch-item-contract.json`. It must not be cited as semantic proof. Existing start24 intervention and
  runtime hash/digest records remain raw evidence; no prior hash failure is relabeled as PASS.

Verification fact: `PYTHONPATH=. uv run --project backend pytest -q
modeling_team/tests/test_r23005_ticket_pipeline.py modeling_team/tests/test_r23005_contracts.py
modeling_team/tests/test_r23005_t6_repeatability.py` returned **46 passed, 3 subtests passed**. This is offline
implementation evidence only; the next fresh Runner must prove the full five-stage/retrieval handoff, unchanged
ticket publication, and independent Acceptance.

### 2026-08-06 R2.3-005 start25 terminal candidate-envelope-invalid and repair ordering

Start25 `r23005-real-20260806t034500z-start25` used a fresh Runner and staged the exact start24 r3 carrier before
`Runner.prepare`. Its `source-manifest.json` directly binds
`modeling_team/.continuations/r23005-start24-r3-exact-candidate.json` at mode `0444`, SHA-256
`9acce460e1e2d28712deaac4a9901cf2357f947fc54d853344cff41c2bacd806`, accepted `delivery-4`, revision
`dify-cba-slice-r3`, and candidate/semantic digest
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`. The run then failed at the first Modeling
delivery with `reason_code=candidate-envelope-invalid`, classification `modeling-quality`, and
`complete_modeling_quality_result=false`; no Protocol platform call, Acceptance ticket, verdict, or semantic-quality
claim exists. Cleanup reached `CLEANED`, deleted the empty owned Project/Ontology, revoked keys, and left zero child,
credential, socket, or process residue.

The pre-reservation repair-ordering defect is also retained: after start24's latest incomplete terminal failure,
the first start25 preparation failed closed with `next start lacks a frozen narrow repair baseline`. It produced no
run directory, reservation, or semantic start. Delivery then computed the fresh clean-HEAD baseline
`bff57388c98e7e1515fc99f6c7e7b69bd96d81529b5f898e7c836cb3fdc59b82` and appended the required `authorize-repair`
event before the actual start25 reservation/start; that repair event does not consume a semantic start.

The new prompt-contract defect is carrier extraction ambiguity: the exact continuation carrier is a metadata
envelope containing a canonical `candidate_text` string and an equivalent parsed `candidate` object. Modeling sent a
non-canonical candidate envelope, so the Runner correctly rejected it before Protocol. Before the next
`semantic_start`, the authoritative Modeling/task prompt must state that only `candidate_text` is parsed and sent as
the complete candidate JSON, while carrier metadata is coordination context; it must also require recomputation and
matching of the accepted candidate/semantic digests. This is a prompt-contract repair, not permission to mutate or
rebuild the r3 business semantics.

The canonical ledger now has SHA-256
`07379e4ac130de8f3844364bffa73f66847303c074da24b376e48bd86bbb6958`, strict replay PASS,
`cap/count/active=31/25/0`, 122 lines, and `6` remaining starts. No start26 is authorized until the extraction
prompt repair is implemented and independently verified.

Direct task-input evidence adds a collaboration/routing layer to this run. The start25 `task.snapshot.yaml` was
copied from an older continuation task and differed from the HEAD authoritative
`modeling_team/tasks/r2-3-005-formal-acceptance.yaml`: it retained only the carrier-path addition while dropping the
Prompt A accepted-receipt-versus-full-gate text, Prompt C relation-citation gate, Prompt D frozen query tuple and
cursor-chain text, and the Prompt E `acceptance-stage-handoff-contract.json` Protocol role source. The Runner's raw
terminal classification remains `modeling-quality`/`candidate-envelope-invalid`; the delivery diagnosis additionally
records `collaboration/routing` + `prompt-contract/stale-launch-input`. This does not rewrite the raw verdict. Before
start26, the launcher must derive a fresh task snapshot from the authoritative HEAD task, add only the exact r3 carrier
path, retain all current A/C/D/E text and role sources, and make the Modeling instruction explicit: send only the
carrier's five-field canonical candidate (`candidate`/parsed `candidate_text`), never the complete continuation
envelope or its coordination metadata.

### 2026-08-06 R2.3-005 Runtime-neutral mechanical spine

The user approved pausing the live start sequence long enough to code the fixed deterministic path, then restoring
the original modeling/Acceptance goal. ADR 0008 is authoritative for the current minimal design. This change
supersedes the start25 wording that asks Modeling to parse the carrier itself: parsing, digest verification,
serialization, recipient/reply binding, and publication are mechanical responsibilities and must not be performed by
Agent shell commands or free-form prompting.

1. Every formal continuation launch must pass the tracked authoritative Task unchanged. An optional append-only Task
   overlay binds the exact base `task_id` and Task SHA-256 and may add only one immutable Runner-private candidate
   publication source. It cannot replace objective, role sources, Protocol tools, gates, Profile, or Packages.
2. The overlay and carrier path, bytes, mode, and digest are frozen before ledger reservation and included in baseline
   preview/reservation. `task.snapshot.yaml` is the authoritative Task; the overlay receives its own immutable
   snapshot and manifest record. Base drift fails before scope or Runtime mutation.
3. Modeling decides whether to reuse the approved carrier, then invokes the role-bound
   `modeling_publish_staged_candidate` operation. The Runner parses only `candidate_text`, verifies equality with the
   parsed `candidate`, validates the existing formal candidate contract, recomputes both digests, matches the accepted
   carrier identity, and publishes the original candidate text as an ordinary Modeling-to-Protocol request with
   `expects_reply=true`.
4. Candidate bytes, path selection, digest calculation, recipient identity, and reply flags are not model arguments.
   A wrong role, repeated invocation, missing/drifted carrier, invalid envelope, candidate mismatch, or digest mismatch
   must create no Team Transport delivery.
5. The new loader, validator, publication service, and capability schema are Runtime-neutral and contain no Codex
   thread/rollout/app-server or Pi RPC field. Codex only projects the capability into its private runtime config;
   R2.3-004 Pi must adapt the same operation rather than reimplement candidate parsing or transport publication.
6. Existing Protocol cursor verification, candidate progress, Prompt E ticket pipeline, pause/resume, settlement,
   cleanup, and ledger policies are reused. This change does not add a workflow engine, arbitrary Task patches,
   automatic semantic retries, backend APIs/tables, or Pi Runtime itself.
7. The earlier user waiver remains explicit: no Plan Reviewer or independent Requirement Tester is required for this
   exceptional round. Focused and complete developer regression are required; the next live run is the semantic and
   Acceptance test and must not claim PASS before independent Acceptance evidence exists.

The user additionally authorized five future semantic starts. Current strict replay remains
`cap/count/active=31/25/0` with six already authorized starts. Because the immutable ledger policy permits a budget
authorization only when the current cap is exhausted, the new `+5` is retained as an explicit pending authorization
and must be appended exactly once after the existing six are consumed; it does not authorize rewriting or bypassing
the current ledger.

Implementation verification completed on 2026-08-06. The tracked Task plus read-only
`r23005-start26-r3` overlay validated successfully against the retained start24 r3 carrier; baseline preview hash is
`d3f51603ae406c2777ab41e9b6093717dd6a2efcd0e1555319b13910e03c705a`. Focused affected regression passed 150 tests
and 51 subtests; the complete `modeling_team/tests` suite passed 429 tests, skipped 1, and passed 177 subtests. This
proves only the deterministic mechanical contract and Codex projection. R2.3-005 remains incomplete until a fresh
live start reaches Protocol/platform work and independent Acceptance evidence.

### 2026-08-06 R2.3-005 start26 pre-semantic Runtime repair

Start26 `r23005-real-20260806t054000z-start26` froze the authoritative Task, overlay, retained carrier, and exact
baseline successfully. Coordinator completed `thread/start`, while Modeling timed out before thread identity. The
Runner correctly emitted `presemantic_release`, performed normal cleanup, deleted the empty scope, revoked all keys,
and retained no child process or credential residue. No `semantic_start` was written, so strict replay remains
`cap/count/active=31/25/0`, with six authorized starts remaining; the ledger now contains 125 lines and has SHA-256
`6fd08ada03e7c620c53679bed7ab340f31803fdba6edef7a8523e76211cbdebc`.

The root cause was a Codex projection integration defect: Modeling received a required `runner_capability` MCP
configuration, but `namespace_command` mounted the corresponding private socket only for Coordinator, Protocol, and
Acceptance. Thread startup therefore waited for an unreachable required MCP until the 15-second RPC deadline. The
mount condition now follows the Runtime-neutral role capability descriptor, so Modeling receives the socket only
when its typed operation is configured; legacy/no-overlay runs remain unchanged. A direct regression assertion and
the complete Modeling Team suite pass (`429 passed, 1 skipped, 177 subtests`). The next live run must reuse the same
carrier/overlay semantics and perform only the fresh Runtime/ledger reservation required after the pre-semantic
release.

### 2026-08-06 R2.3-005 start27 foreground-control repair

Start27 `r23005-real-20260806t055331z-start27` proved the start26 socket repair: Coordinator, Modeling, Protocol, and
Acceptance all completed `thread/start`, and the Runner wrote `semantic_start`. The Delivery wrapper had been launched
through `python - <<'PY'`; that heredoc was also the Runner's control stdin. Once Python consumed the script, the
foreground control loop immediately observed EOF, performed cleanup, and returned success before any typed candidate,
Protocol receipt, platform operation, or Acceptance round could be evidenced. The run is therefore terminal
`collaboration/routing`, `complete_modeling_quality_result=false`, not a semantic-quality result. Cleanup deleted the
empty owned scope, revoked all keys, and retained zero runtime children.

Formal CLI operation now treats EOF before `TERMINAL_REPORT_COMPLETE` as a fatal coordination boundary, records the
terminal classification, and returns non-zero; legacy non-formal EOF behavior remains unchanged. The Delivery launch
must use an stdin-preserving PTY and an in-process `python -c` bootstrap wrapper, not heredoc/stdin script injection.
Focused EOF/terminal/legacy tests pass, and the complete `modeling_team/tests` suite passes
`430 passed, 1 skipped, 177 subtests`. Canonical ledger strict replay is `cap/count/active=31/26/0`, 129 lines,
SHA-256 `70655dc9fd7e098b9264b61ed353f33b77e146b6bc5553fae6d2ab07e9d0e7a3`, with five already-recorded starts
remaining and the later `+5` still pending. The next start must reuse the same carrier/overlay semantics.

### 2026-08-06 R2.3-005 start30 status and repair gate

Start30 `r23005-real-20260806t074302z-start30` completed the five Protocol platform stages and the required
cross-agent handoffs: Protocol retained and sent `delivery-5` after `silent_for_acceptance`, and Modeling sent
`ready_for_acceptance`. The Coordinator could not publish an Acceptance ticket because the existing draft capability
could not bind the retained handoff by delivery ID without asking the Agent to reconstruct or resend it. This created
issue-3, a `collaboration/routing` defect; no Acceptance ticket, Examiner, or verdict exists and
`complete_modeling_quality_result=false`.

Coordinator used the valid five-field abort shape and persisted the exact reason. Runner reached
`TERMINAL_REPORT_COMPLETE`; cleanup completed and the written platform scope is retained as `failed-written-retained`.
Before another semantic start, the formal Runner-private delivery-bound ticket-draft operation, explicit terminal-
handoff prompts, and action-specific `issue_control` `oneOf` schemas must be committed and verified. The strict ledger
replay is `cap/count/active=31/29/0`, 141 lines, SHA-256
`f33535e141170c17f042cf790217d3b6d0109ede5c8b23807383ced7e0acda1a`, with 2 remaining starts; the same candidate
semantics and retained evidence remain the continuation baseline.

### 2026-08-06 R2.3-005 start31 ordinary-reply routing failure and repair gate

Start31 `r23005-real-20260806t083205z-start31` reused the retained candidate/overlay semantics and baseline
`9e2fd6d978f4909fdc482e9949f7a37501849466ea589bb6ea395d45afef03e6`. Protocol completed dry-run, apply, readback,
validation, reasoning, and governed retrieval, and sent the exact Prompt-E handoff as `delivery-5` (text digest
`ae913494aa4ac14a668c8cb8a7f73ee67565b817558517e5c279c164b27e1cd8`).

Coordinator's first typed draft request used the guessed `cq-1` and was correctly rejected without revision mutation.
It then asked Protocol for IDs; Protocol replied in `delivery-7` with two slugs, which are not the requirement-owned
Acceptance ticket IDs. The pre-repair Runner classified every Protocol -> Coordinator delivery as a handoff, attempted
to parse that ordinary array, raised `stage handoff delivery is not an object`, and exited 2/`CLEANED`. No issue, ticket,
Acceptance, Examiner, or verdict exists. The run is `collaboration/routing`, `complete_modeling_quality_result=false`,
with written scope `failed-written-retained` and zero key/session/process residue.

The durable gate is: register only the exact canonical bytes produced by the Runner-private handoff builder; route all
other Protocol peer replies normally and fail closed on mutated known handoff identities. Runner task text must inject
the exact two frozen IDs from the acceptance policy (`cq-001`,`cq-002`) so Coordinator never guesses or asks Protocol;
Protocol response slugs cannot become ticket IDs. Developer verification passed `442 tests, 1 skipped, 177 subtests`.
Strict ledger replay is `cap/count/active=31/30/0`, 145 lines, SHA-256
`d219531abef2078e4cd8f04dbbc7deff459bb72e24399c6f66f00dd40652279a`, with 1 remaining start.

### 2026-08-06 R2.3-005 start32 canonical handoff identity failure and repair gate

Start32 `r23005-real-20260806t090130z-start32` reused the retained candidate/overlay semantics and baseline
`19246c30c190da84ab0b0b3dea9c0b2c5a1aa13e197722ac7039246d3de7cb24`. Protocol completed all five platform stages
(dry-run, apply, readback, validation, and reasoning) and governed retrieval completed both competency questions
with `generic_complete`. The Runner-private handoff builder succeeded with handoff digest
`7dd7f977feb2ac08158658011642bba42c9ea4fa302bfcd4db21ba1edfbfdcf7`.

Protocol's `delivery-6` contained the same 6,850-byte handoff object as the builder: parsed objects were deeply
equal and the canonical JSON SHA-256 was
`33f260dcda87d26ee28d1af7b7feec328bb654a093e4717682ae397deb35e4ee`, while the raw delivery SHA-256 was
`c160a9e39be6269079e8c1657c4a5d7e4874f0c7eefbe56ef601f02d000866f9`; the only difference was JSON key insertion
order. The pre-repair raw-byte classifier nevertheless reported a mutation, the formal wrapper exited 2 and
`CLEANED`, and no acceptance-stage-handoff evidence, ticket, or Acceptance round was produced. The run is
`collaboration/routing`, `complete_modeling_quality_result=false`; cleanup retained the written scope as
`failed-written-retained` and left zero key/session/process residue.

The durable repair is a canonical semantic-identity gate: parse JSON before classification, accept only the exact
builder semantic object regardless of insignificant whitespace/key order, keep raw bytes only as evidence, and fail
closed on field/value/array-order mutations or reserved handoff markers while routing ordinary arrays, text, and
unrelated objects normally. Developer regression after the repair passed `442 tests, 1 skipped, 177 subtests`; Ruff
and `git diff --check` passed. Strict ledger replay is now `cap/count/active=31/31/0`, 149 lines, SHA-256
`2f30f720d0fa5a151b5b8ac378a0a5bd7bad072a310dcc7ba66e48906cd075bd`, with **zero remaining** starts. The repair
must be committed before requesting a new user authorization; no further semantic start is authorized in the
exhausted tranche.

### 2026-08-06 R2.3-005 start33 delivery-bound draft rejection and platform-ID repair

Start33 `r23005-real-20260806t101159z-start33` reused the retained r3 candidate/overlay semantics. Protocol completed
the five required stages and both competency-question retrievals with `generic_complete`; the Runner-private
canonical handoff succeeded as `delivery-5` (handoff digest
`1936cadd560a1bf25e79bf6fedd1542721eecb1837edd90071b1efaf057b7053`). The first external guidance supplied a factual
gate-complete notice bound to the candidate and `delivery-5`; Modeling then emitted `ready_for_acceptance`.

Coordinator's two delivery-bound draft requests for the frozen questions were both rejected with generic `-32001`.
No draft or ticket was created, and no Acceptance round, Examiner report, or verdict exists. The exact failure was a
platform-contract mismatch: `platform_read_scope` applied the role/workflow safe-ID rule to live platform identifiers,
rejecting the digit-leading Project/Ontology/graph-set UUIDs before ticket construction. This record does not make a
semantic-quality claim.

The narrow repair adds a dedicated platform-scope identifier rule while retaining the stricter role-ID rule. A
temporary in-memory replay of the retained start33 handoff and platform evidence built both CQ draft objects
successfully. This is developer/contract evidence only and does not turn the retained run into an Acceptance result.
The live run remains `issue-1` / `WAITING_OWNER`, with no ticket, Acceptance, Examiner, or verdict. The current
authorization tranche is **1/3 consumed, 2 remaining**.

### 2026-08-06 R2.3-005 start33 terminal closeout

Coordinator issued a legal outer `abort` using exactly the five fields `action`, `issue_id`, `reporter_id`,
`control_epoch`, and `reason`. Runner reached `TERMINAL_REPORT_COMPLETE`; terminal classification is
`platform-contract`, with `complete_modeling_quality_result=false`.

Cleanup retained the non-empty Project, completed the Session, released the Lease, and left zero keys, child/runtime
processes, capability sockets, or local credential projections. User `AGENTS.md`/`CLAUDE.md` diffs were restored.
Strict R2.3-005 ledger replay is `cap/count/active=34/32/0`, 154 lines, SHA-256
`fe942e0ddd26cd5253aa107558adcb4781510877074c8615b7ee7a2a56ec654a`, with **2 remaining** starts.

### 2026-08-06 R2.3-005 start34 entity-identifier preservation failure and gate

Start34 `r23005-real-20260806t105645z-start34` used the exact retained carrier
`modeling_team/.continuations/r23005-start24-r3-exact-candidate.json` (SHA-256
`9acce460e1e2d28712deaac4a9901cf2357f947fc54d853344cff41c2bacd806`) as Runner-private `delivery-1`, without
reconstructing its semantics. Protocol returned an accepted receipt bound to that delivery as `delivery-5`, for
revision `dify-cba-slice-r3` and candidate/semantic digest
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`.

Protocol wrote the class, property, and entity stages; entity batch `r23005-entities` applied atomically. Direct
artifact inspection then found at least six Modeling-owned explicit `entity_id` values changed during
candidate-to-platform translation: `c-version-1` -> `c-v1`, `c-version-2` -> `c-v2`, `c-current-draft` -> `c-draft`,
`quality-score-field` -> `quality-score`, `quality-rating-field` -> `quality-rating`, and
`unknown-cross-release-output-meaning` -> `unknown-cross-release-meaning`. No relation or Shape batch was submitted.
The platform correctly executed the submitted entity batch, so this is a `modeling-quality` / Protocol prompt-contract
defect rather than a platform execution or platform-contract defect.

The run was formally aborted from `issue-1` / `WAITING_OWNER`, preserved all start34 evidence, and reached
`TERMINAL_REPORT_COMPLETE` with `issue_abort=true` and `complete_modeling_quality_result=false`. Acceptance never
started or settled: no ticket, Acceptance round, Examiner, or verdict exists. Cleanup retained the non-empty Project
as `failed-written-retained`, cancelled the Build Session, released the Lease, revoked all relevant keys, destroyed
all role-private credentials, and left zero child/process/socket/token/credential or in-flight-attempt residue.

Before start35, the authoritative Protocol prompt contract **must** be repaired and verified so every explicit
candidate identifier is preserved byte-for-byte in candidate-to-platform translation. Abbreviation, normalization,
or substitution of any explicit identifier is forbidden, and the next start must reuse the exact retained candidate.
Strict ledger replay is `cap/count/active=34/33/0`, 158 lines, SHA-256
`2ec4cf833a007f8ffa30f9227f068e9de00ef2d10cbae26c06ab879596d39424`, with **1 remaining** start. Start34 provides
no Acceptance PASS or semantic acceptance conclusion.

### 2026-08-06 R2.3-005 start35 governed-query planning failure and next-authorization gate

Start35 `r23005-real-20260806t110812z-start35` reused the exact retained candidate carrier as `delivery-1`. Protocol's
bound `delivery-4` receipt was accepted for revision `dify-cba-slice-r3`, with candidate/semantic digest
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`. The start34 identifier-preservation repair
worked: entity dry-run, apply input, formal outputs, downstream relations, and reasoning all preserved
`c-version-1`, `c-version-2`, `c-current-draft`, `quality-score-field`, `quality-rating-field`, and
`unknown-cross-release-output-meaning` byte-for-byte.

Protocol completed dry-run and apply for the class, property, entity, relation, and Shape stages. The negative probe
was dry-run-only and rejected as required. Semantic validation succeeded with `conforms=true`, and reasoning succeeded
with `consistent=true`. These results establish the completed platform stages but do not substitute for governed
retrieval or Acceptance.

Governed retrieval remained incomplete. Protocol first submitted unsupported resource types (`entity`, `entities`,
and `individual`), then froze the first valid tuple as `resource_types=["relation"]`. Exhaustive lexical pagination
returned relation evidence but could not return the `fieldName` and `fieldDatatype` fact statements also required by
the first competency question; a returned Shape statement additionally lacked lineage. The frozen tuple could not be
changed without violating the immutable continuation contract. No canonical handoff, gate-complete notice,
`ready_for_acceptance`, `silent_for_acceptance`, ticket, Acceptance round, Examiner report, or verdict was produced.

This failure is `modeling-quality`, with `complete_modeling_quality_result=false`: the owning defect is Protocol's
query-planning prompt contract, while the platform correctly rejected unsupported resource types and enforced the
frozen-query behavior. The run raised `issue-1`, paused at `WAITING_OWNER`, then used the authorized exact resolution
and Coordinator's exact five-field abort. Runner reached `TERMINAL_REPORT_COMPLETE` with `issue_abort=true`. Cleanup
retained the non-empty Project as `failed-written-retained`, terminated the Session/Lease with zero in-flight
attempts, revoked all relevant keys, destroyed all role-private credentials, and left zero Acceptance-child,
process, socket, token, or credential residue.

Before any future semantic start, the authoritative Protocol prompt **must** be repaired and verified so the first
valid immutable retrieval tuple is selected from the advertised resource-type contract and includes every evidence
family required by the competency question. A new user authorization is required after that repair; the exhausted
tranche cannot authorize another run. Strict ledger replay is `cap/count/active=34/34/0`, 162 lines, SHA-256
`6ced4b919a4bd7e17d5f36f7577db6fe1c3f092728a9fa2e598db280ac3e67f8`, with **zero remaining** starts.

### 2026-08-06 R2.3-005 exhausted incomplete-modeling-quality budget/repair sequencing

The user has explicitly authorized three additional real modeling starts under
`user-20260806-r23005-start36-38`, but that authorization is not yet registered. Its pre-start36 registration was
rejected with `budget authorization requires the latest retryable failure`, and no ledger event or semantic start was
created. The authoritative ledger remains `cap/count/active=34/34/0`, 162 lines, SHA-256
`6ced4b919a4bd7e17d5f36f7577db6fe1c3f092728a9fa2e598db280ac3e67f8`, with zero remaining starts and no start36.

At an exhausted cap, strict budget authorization and repair must have one legal sequence when the latest terminal
result is incomplete `modeling-quality` and the formal configuration enables that repair. Budget-predecessor and
strict-replay eligibility **must** reuse `_repair_failure_eligible`, which is also authoritative for the repair gate,
instead of admitting only `_RETRYABLE` classifications. The following cases remain prohibited: complete
modeling-quality results, incomplete modeling-quality results when the configuration is disabled, and any sequence
that violates the existing exact-predecessor, authorization-identity, cap-consumption, or repair-baseline contracts.

At exhausted cap, the explicit budget event must still precede the exact repair event, and the repair must precede a
fresh baseline/reservation. Only after this narrow repair is committed and verified may the pending authorization be
registered. That registration makes start36 the next eligible semantic start; it does not automatically execute
start37 or start38.

### 2026-08-06 R2.3-005 start36 candidate-receipt ordering failure

The repaired ledger accepted the pending three-start authorization and the start35 repair against clean baseline
`f78b73d469db1dc1500986ec45412d606126d66261b48ffaaaf9a6e60f8b5929`. A first invocation of
`r23005-real-20260806t134038z-start36` lacked the Delivery-only admin credential and failed canonical preflight before
the run root, reservation, or semantic-start boundary; it therefore consumed no attempt. The corrected invocation
reused the same run ID and exact authorized baseline, used the established ephemeral bootstrap/revoke wrapper, and
recorded exactly one reservation and semantic start without duplicating budget or repair authorization.

Modeling published the exact retained candidate as `delivery-1`, revision `dify-cba-slice-r3`, digest
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`. Protocol did not return the accepted
candidate receipt, so Runner remained `awaiting_receipt`; Protocol nevertheless executed class, property, entity, and
relation dry-run/apply_atomic stages and Shape dry-run. After 120 seconds Runner closed
`candidate-progress-timeout` as `collaboration/routing`, with `complete_modeling_quality_result=false`. Shape apply,
validation, reasoning, governed retrieval, handoff, and Acceptance have no evidence and must not be inferred.

Before start37, the candidate receipt is a mechanical execution barrier: Protocol **must** deliver and bind the exact
accepted receipt before any platform batch is permitted. This gate must prevent a model from bypassing receipt order;
prompt guidance alone is insufficient. Cleanup retained the written Project, terminated the Session/Lease, revoked
temporary credentials, and left no start36 runtime residue. Strict replay is `cap/count/active=37/35/0`, 167 lines,
SHA-256 `09d616619f3f40fedcd5ed00b0ca6b52337c5173ccc75f4a051a579e30c62210`, with **2 remaining** starts. No start37
is automatically launched.

### 2026-08-06 R2.3-005 mechanical candidate-receipt enforcement

The start37 gate is implemented as a Runner-owned atomic closed/open carrier. A formal v2 candidate begins closed;
candidate replacement, revision, conflict, and terminal transitions close it again. Only formal registration of the
exact accepted receipt may open it. Protocol prompt instructions must describe the same order, but prompt behavior is
not accepted as enforcement evidence.

Only formal v2 runtime receives the private gate environment binding and read-only namespace mount. Backend MCP
`_run_tool` **must** evaluate the carrier before resolving platform resources or dispatching the requested function
and fail closed with `candidate_receipt_required` while the gate is closed. Legacy and non-formal execution must
receive no gate environment variable, mount, or runtime directory. The carrier contract remains Runtime-neutral so a
future Pi adapter reuses the same Runner state rather than implementing an adapter-specific receipt authority.

GitNexus reported CRITICAL blast radius for the backend runtime surface and HIGH for launch wiring. The accepted
mitigation is formal-v2-only opt-in wiring with zero default-path behavior difference. Verification passed **452
modeling tests, 1 skipped, 195 subtests**, **843 backend tests, 10 skipped**, Ruff, and diff checks. The service restart
and post-restart backend/frontend health checks remain pending with root; start37 must not begin until that runtime
verification is complete. This repair itself does not change the ledger or consume a semantic start.

### 2026-08-06 R2.3-005 candidate-receipt barrier delivery closeout

The mechanical receipt barrier is committed as `e9bd80f`. The repository-managed service was restarted and reached
`active`. A backend curl issued approximately 4 ms after restart preceded listener readiness; bounded short polling
succeeded on attempt 5. Backend `/api/health` returned `{"status":"ok"}`, and frontend port `5173` returned HTTP
success.

The start37 receipt-barrier prerequisite is now satisfied by committed implementation, regression evidence, service
restart, and live endpoint health. This closeout does not authorize an automatic start37 and does not mutate the
semantic-start ledger.

### 2026-08-06 R2.3-005 start37 retrieval result and final-start gate

Start37 `r23005-real-20260806t141512z-start37` live-proved the mechanical candidate-receipt barrier. Modeling's exact
retained candidate was `delivery-1`, revision `dify-cba-slice-r3`, digest
`7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998`; Protocol's accepted `delivery-4` bound
the original delivery, Runner formally registered it, and the gate opened while platform artifact count remained
zero. One external narrow intervention on the same Coordinator thread then produced factual, non-reply `delivery-5`
to wake the retained Protocol workflow without rebuilding the candidate, receipt, or business semantics.

Class, property, entity, relation, and Shape dry-run/apply_atomic stages passed. The negative probe was rejected in
dry-run, validation conformed, reasoning was consistent, and explicit Modeling-owned entity IDs remained exact. Both
mixed relation-plus-fact competency-query chains consumed all cursors, but unrelated schema/RDFS/SHACL structural rows
raised Evidence/lineage warnings and the written `quality-rating-field` `fieldName=quality_rating` fact was not
returned. Protocol did not claim completeness. No handoff, ready/silent gate, ticket, independent Acceptance round,
verdict, or PASS exists.

The exact authorized abort closed start37 as `platform-contract`, with
`complete_modeling_quality_result=false`. Cleanup retained the non-empty Project, terminated Session/Lease activity,
revoked keys, destroyed private credentials, and left zero runtime or in-flight residue. Strict replay is
`cap/count/active=37/36/0`, 171 lines, SHA-256
`f9790fe7e43f459df24e22de8e09d959b3df2264abfab828ec6f0c45f8adb75b`, with **1 remaining** start.

An independent fact-only read diagnostic returned one terminal page and 17 asserted facts for each original CQ; all
were Evidence-supported and lineage-complete. CQ2's required unknown facts were returned, while CQ1 still omitted
`fieldName=quality_rating`. All temporary keys were revoked. This diagnosis is not Acceptance evidence.

Commit `55e2dee` replaces the external continuation with one Runner-owned, direct, delivery-ID-bound Protocol wake
after accepted receipt registration and fails closed on duplicate or drifting wake state; **456 modeling tests**
passed. Before start38, each `consumer_query.required_paths` evidence family **must** be queried through its own
independently frozen narrow chain, and a Host-owned verifier must judge candidate-bound required-path completeness
without treating unrelated structural-row warnings as relevant. This final-start gate does not automatically launch
start38.

### 2026-08-06 R2.3-005 pending authorization for start39–41

The current user message explicitly authorizes three additional real modeling starts under authorization
`user-20260806-r23005-start39-41`. This is a pending extension, not an immediate ledger event: strict replay still
contains the previously authorized start38 allowance at `cap/count=37/36`, and the authorization-extension contract
allows the next extension to be registered only after that allowance is consumed and start38 reaches a terminal
result.

After start38 terminal handling, the Runner must immediately register the pending authorization through the normal
strict-ledger path before reserving start39. This requirement neither starts start38 nor authorizes start39, start40,
or start41 to execute before that registration.

### 2026-08-06 R2.3-005 final pre-start38 retrieval gate

The retained start37 Project/Ontology was diagnosed read-only through seven independently frozen exact-path queries.
Every chain used predicate-kind-specific relation/fact scope, asserted lexical retrieval, depth 3, 50/50 limits, and
terminal match-page plus context-subchain pagination. All seven returned an exact-predicate statement with supported
Evidence references and complete lineage. This also proved that a path-only gate can false-accept: the `fieldName`
chain may select `quality_score` even though the candidate-connected CQ requires the `quality-rating-field` value
`quality_rating`.

Before start38, the Host-owned verifier **must** bind every `consumer_query.required_paths` member to the connected
subject/object/value declared by the accepted candidate and judge the whole connected family only after independently
exhausting match and context pagination. If hybrid retrieval reports degraded completeness, the verifier **must**
execute an independently frozen lexical chain; it must not reuse the degraded chain as completeness evidence.

The existing Codex coarse warning gate may suppress a duplicate rejection only when a schema-marked Host receipt
states that this candidate-bound verification completed. Legacy execution and any execution without that receipt
retain their previous warning behavior. Host remains the semantic acceptance authority; Pi and other Runtime adapters
consume the same neutral contract and do not implement their own semantic gate.

Verification passed **21 focused tests**, **66 targeted runtime tests**, and **480 passed, 1 skipped, 195 subtests**
in the complete modeling suite. Three runtime-related tests were added, including query-state authority coverage.
Ruff and diff checks passed. GitNexus `detect_changes` classified the scope LOW with **29 changed symbols and 0
affected processes**. Start38 must not begin until an independent final review passes on this stable state. The
pending `user-20260806-r23005-start39-41` authorization remains unchanged and must be registered only after start38
terminal handling.

### 2026-08-06 R2.3-005 independent final review closeout

Independent final review passed: Protocol cannot forge the schema-marked Host completion receipt; execution without
that receipt, legacy execution, and non-formal execution retain the prior warning-block behavior; and Pi is not bound
to semantic gate authority. No start38 blocker remains. The stable repair state may be committed, and start38 may
launch from that committed state under the existing allowance. The pending
`user-20260806-r23005-start39-41` authorization remains unchanged and may be registered only after start38 terminal
handling.

### 2026-08-06 R2.3-005 start38 Host-retrieval pass and Acceptance projection-binding gate

Start38 `r23005-real-20260806t153245z-start38` reused the exact r3 candidate under committed HEAD `181225e`. The
candidate receipt barrier and direct ID-bound wake passed without external intervention. Protocol completed every
modeling stage, required negative dry-run probe, semantic validation, and reasoning. It then executed 14
Host-observed retrieval episodes across the seven independently frozen required paths; episode 14 reached
`host_receipt_complete`, including the connected `quality-rating-field fieldName quality_rating` statement with
supported Evidence and complete lineage. Canonical handoff `delivery-6`, gate-complete/silent `delivery-7`, and both
immutable CQ tickets were published. Therefore the modeling and Host-retrieval portions are real live evidence and
must be reused; a later retry must not rebuild the candidate or rediscover those already proven layers.

Independent Acceptance exposed a narrower collaboration/routing defect before CQ1 children were created. Both source
and platform attempt-0 `acceptance_child_start` calls supplied a caller-constructed
`{ticket_digest, acceptance_round_id, question_id}` input and used the ticket digest as the child-input digest. Runner
rejected both with MCP `-32001`; CQ2 did not start, and no Examiner report, verdict, settlement, or PASS exists.

The owning defect is the Acceptance prompt/capability binding to the Host-private projection contract.
`RunnerAcceptanceCarrier.project_child_input` deterministically owns the source/platform projections and their
canonical SHA-256 values, while the model-visible Acceptance surface did not expose that projection or instruct a
valid opaque binding. The durable repair must make Acceptance consume the exact Runner-projected kind-specific input
without manually reconstructing it. It must preserve ticket digest, model-state, source/platform isolation,
attempt/recycle, and independent verdict boundaries. Tests must accept the exact projected bindings and reject the
start38 fabricated envelope and ticket-digest substitution.

The exact abort reached `TERMINAL_REPORT_COMPLETE` with Acceptance `settled=false`, zero active/retained children,
destroyed private credentials, terminal Session/Lease state, revoked keys, and retained non-empty Project evidence.
The ledger records start38 as `classification=collaboration/routing` and
`complete_modeling_quality_result=false`. After strict replay passed at `37/37/0`, the already explicit user
authorization was registered as `user-20260806-r23005-start39-41`, `additional_starts=3`. Current strict replay is
`cap/count/active=40/37/0`, 176 lines, SHA-256
`80163dec934749eb743102c7f8f0941fc1c6ccae990842e87eb7237b9b74c08f`, with **3 remaining** starts.

Start39 is blocked until the authoritative Acceptance prompt/Skill plus capability projection binding is repaired,
reviewed, and verified. The available allowance does not authorize an immediate repair event, reservation, or
semantic start, and no start39 may begin while knowingly carrying the same prompt-contract defect.

### 2026-08-06 R2.3-005 pre-start39 Host-derived child-input repair

The narrow projection-binding repair is implemented. `acceptance_child_start` treats `input_ref` and `input_digest`
as optional compatibility fields; when they are omitted, common Runner dispatch uses the frozen `round_id` and
requested `kind` to call the existing `RunnerAcceptanceCarrier.project_child_input` path and supplies its canonical
projection/digest. Acceptance Agents must not construct or hash this Host-private input and must not use
`ticket_digest` as `input_digest`. The authoritative instructions, formal Task, and packaged Skills state that rule.

Exact explicit legacy input remains compatible only when both fields equal the Runner-derived canonical pair. Partial
input, wrong projection or digest, cross-kind/cross-round reuse, ticket-metadata construction, ticket-digest
substitution, and unknown endpoint arguments fail closed. Capability endpoint schemas must maintain
`required ⊆ arguments ⊆ properties`; omission is valid only for the two Host-derived compatibility fields.

The real start38 CQ1 fixture freezes source digest
`b2577d6e649c8593087a518754ef510a4f4f49b0f3171f3f3daf2a92b4a0cacc` and platform digest
`2926d748a84333ea115f1564d6b289f7c6f3214dfcce00f5797a9819ab2927f5`. GitNexus impact analysis is LOW.
Verification passed **63 focused tests plus 21 subtests**, full modeling regression **483 passed, 1 skipped, 195
subtests**, Ruff, and diff checks.

This closes implementation and local verification only. Start39 remains blocked pending a separately recorded
independent final review PASS; no repair authorization, reservation, or semantic start may precede that result.

### 2026-08-06 R2.3-005 independent final review cleared start39

Independent final review is **PASS**. Omitted Host-derived child inputs and the exact explicit legacy pair are both
reachable, while partial, wrong, cross-round, cross-kind, and unknown-argument inputs fail closed. Original
`start_child` ticket/capability validation, request replay, child lifecycle, report/recycle, and settlement contracts
are not weakened. The repair adds no Runtime- or Pi-specific coupling or semantic authority.

No start39 blocker remains. The stable repair may be committed, and start39 may launch from that committed reviewed
baseline through the normal strict-ledger repair/reservation sequence under the already registered allowance.

### 2026-08-07 R2.3-005 start39 zero-Agent-turn Delivery launcher defect

Start39 `r23005-real-20260806t160248z-start39` consumed one semantic-start allowance from committed HEAD `e62e375`
and baseline `d7c38a8c44ad82dc287d0f4e422769f4f03eafd70171d6b2d9b1a09d7d94a0c6`, but it did not execute the semantic
workflow. Delivery placed the foreground Runner below a Python heredoc and `subprocess.call`. The child inherited the
heredoc's EOF rather than the outer PTY and immediately failed with
`foreground CLI ended before terminal report completion`. Only thread/startup notifications exist; there was no Agent
turn, candidate publication, platform write, Host retrieval, ticket, Acceptance child, verdict, or settlement.

This failure is `collaboration/routing`, `complete_modeling_quality_result=false`, and belongs to the Delivery launch
contract. It does not invalidate the reviewed Host-derived Acceptance projection repair. Automatic cleanup deleted
the empty owned scope, terminalized Session/Lease state, revoked all keys, destroyed private role credentials, and
left zero child/process/in-flight residue.

Current strict replay is `cap/count/active=40/38/0`, SHA-256
`0e06710337d899cdae8b154918dcbd68e71161473397f968ff5847647e26b492`, with **2 remaining** starts. No start40 is
authorized to launch yet. Before start40, the authoritative Delivery prompt/checklist must be repaired and verified to
reuse the start38 shell-direct PTY contract: the tool-owned PTY directly hosts
`uv run ... python -m modeling_team run`, retains a live session ID, and receives later control through
`write_stdin`. Python-heredoc/subprocess foreground indirection is forbidden. Only after that narrow Delivery repair
review may the normal strict-ledger repair/reservation sequence proceed.

### 2026-08-07 R2.3-005 start40 runtime-infrastructure failure

Start40 `r23005-real-20260806t161228z-start40` reused the retained r3 candidate and start38 overlay from baseline
`1656c31` through the corrected shell-direct PTY. Candidate receipt, platform dry-run/apply, readback, validation,
reasoning, governed retrieval, and the acceptance-stage handoff completed in fresh Project
`1e877b1e-2d91-473e-9f90-06ff26e7740d` / Ontology `5a162467-05f8-4806-83fc-cefcbcde26bd`.

CQ2 proved omitted child inputs bind the Host projections, but Source Examiner attempt 0 and the sole identical-input
attempt 1 both ended in typed `child-timeout` and were recycled. Platform start was rejected twice with generic MCP
`-32001` before any handle/read key existed. No semantic Examiner report, CQ verdict, settlement, or complete
modeling-quality result exists. Same-run issue guidance recovered the first recycle after Acceptance incorrectly sent
the whole readiness object. Commit `8efe993` (`Constrain acceptance recycle references`) durably freezes the required
one-key `completion_ref` contract in prompts, schema, Skill, and tests.

At the user's direction, issue 2 used formal abort rather than verdict repair. Runner reached
`TERMINAL_REPORT_COMPLETE`; children, processes, credentials, keys, Build Session, and Lease are terminal/clean, while
the non-empty failed-written Project is retained as evidence. Ledger classification is `runtime/infrastructure` with
`complete_modeling_quality_result=false`; strict replay is `cap/count/active=40/39/0`, 184 lines, SHA-256
`3c8aedd517feb412b07acd88b2a4109ef510946f545a2c23df784ad2299f51c6`, leaving **1** authorized start. This does
not authorize repair, reservation, or start41 without a new user instruction.

### 2026-08-09 R2.3-005 start41–start68 accumulated repair and live boundary

The start41–start68 sequence reused the accepted r3 semantics and progressively repaired only observed Runtime,
platform-contract, and collaboration/routing defects. The committed baseline before the current repair includes
DeepSeek Flash/max/Responses role configuration, bounded inactivity detection, foreground/FIFO outer control,
Examiner output pumping and report schemas, Host-owned candidate staging and handoff identity, Host-derived Examiner
inputs and verdict structures, read-proxy digest preservation, and Host-derived verdict evidence references.

Start68 `r23005-real-20260808-deepseek-start68` reached the furthest real boundary. Modeling published the unchanged
`dify-cba-slice-r3` candidate; Protocol completed dry-run, apply, readback, validation, reasoning, governed retrieval,
and acceptance-stage handoff. Both frozen tickets were published. cq-001's fresh Examiner pair produced bound reports,
Acceptance submitted the verdict successfully, and Coordinator confirmed `PASS`. This is valid partial evidence but
not the requirement result.

The remaining live failure was deterministic: after cq-001 PASS, Coordinator waited for cq-002's verdict without
sending cq-002 `acceptance_start`. No cq-002 verdict, persistent-role terminal set, team settlement, terminal report,
or complete cleanup proof exists. The run was aborted and the canonical ledger recorded
`classification=collaboration/routing`, `complete_modeling_quality_result=false`. Ledger state is 307 records,
SHA-256 `e023fe04913d301cdd59db7816c1de595d9d75547ce437575f0852014e5a0c5d`, and
`cap/count/active=67/67/0`; no real start remains authorized.

### 2026-08-09 R2.3-005 sequential-CQ deterministic repair gate

The user confirmed that Coordinator remains the semantic scheduler. The repair therefore updates both authoritative
Coordinator prompt surfaces to require cq-001 PASS -> exact already-published cq-002 round, while formal Runner uses
the existing Acceptance carrier only as a pre-transition validator. The Host does not choose or dispatch a CQ. It
rejects unpublished, early, replayed, duplicate, third, post-final, stale-state, wrong-ticket, incomplete-cleanup, and
unusable-PASS starts before phase transition or Runtime enqueue. Before cq-002, passive live-state revalidation makes
any post-PASS platform drift invalidate old PASS evidence and require fresh tickets plus both CQs on the new state.

Mandatory plan review required two High revisions (round/ticket ordering and stale-PASS revalidation) and passed on
round 3. Independent Round 7 passed every behavior/runtime gate but failed the frozen full-Ruff gate on one pre-existing
unused test local. The one-line lint-only repair preserved behavior. Independent Round 8 then passed focused 6/6,
R2.3-005 172/172 with one opt-in skip, related 66/66, complete modeling-team unittest discovery 488/488 with one
opt-in skip, full Ruff, diff checks, GitNexus change detection, service restart, backend health, and frontend HTTP 200.
No live model call or semantic start occurred during these deterministic rounds.

This evidence permits a clean implementation commit and a request for new start authorization only. R2.3-005 remains
`NOT_PASSED` until one fresh authorized run completes both real CQ verdicts on one final model state, all four
persistent-role terminal reports, team settlement, terminal report, strict cleanup, and ledger closeout.

### 2026-08-09 R2.3-005 start69–start70 live result and terminal-routing repair gate

The user authorized exactly three fresh semantic starts (`start69`–`start71`). Start69 failed before platform work
because the shared Protocol prompt incorrectly treated the formal task as capability smoke; the repaired prompt then
passed independent Round 9. Start70 proved that repair and the sequential-CQ repair in one real run: Protocol completed
the five platform stages and all seven governed retrieval paths, both frozen CQ rounds ran in order against one final
model state, all four Examiner children reported and were recycled, cq-001 and cq-002 both received `PASS`, and
Acceptance reached settled state.

Start70 nevertheless did not reach the requirement terminal. The generic dependency graph could deliver a Protocol
terminal handoff only after Modeling reported, while Modeling correctly waited for its own explicit Runner terminal
handoff. Because Modeling had no dependency predecessor, the remaining roles deadlocked after Acceptance settlement.
The run was stopped and recorded as `classification=collaboration/routing`,
`complete_modeling_quality_result=false`. Cleanup reached `CLEANED`, destroyed role credentials, left zero active
Acceptance children, and retained the non-empty failed-written Project/Ontology as required. Strict ledger state is
314 records, 75,867 bytes, SHA-256 `8cdd1aea036c5f3adbe93b43f6c5a5d82dba0d5832f1c6e41f4de1e217764da4`;
exactly one authorized start (`start71`) remains.

The reviewed repair adds `modeling <- acceptance` only for formal coordination. Thus a settled Acceptance sends the
existing explicit terminal handoff to Modeling, then the unchanged chain continues Modeling -> Protocol ->
Coordinator. FAIL/BLOCKED paths leave Acceptance unsettled and all persistent roles live for revision. Non-formal
dependency graphs remain byte-compatible. Acceptance instructions also freeze each competency-question result item
to exactly `{status, answer, evidence_ref_ids}`, require `PASS|FAIL|BLOCKED`, and forbid Examiner answerability labels
or identifier/typed-reference fields; Host tests prove invalid labels are rejected without round/verdict mutation.
This deterministic repair does not complete R2.3-005. Only a clean committed start71 may prove the remaining four-role
terminal, Team settlement, terminal report, cleanup, and ledger gates.

### 2026-08-09 R2.3-005 start71 final authorized result and Acceptance terminal-report gate

Start71 ran from clean commit `b3ac7ca` and baseline
`c80347e0ff753181c1eff5e0c209e3d739d3d9fd22d9ddf1a9fa41540d470292`. It independently repeated the full
semantic success boundary: exact r3 candidate/receipt, five platform stages, all governed retrieval paths, two frozen
tickets, ordered cq-001 then cq-002, four fresh Examiner reports and recycle, two usable `PASS` verdicts on one final
model state, and matched Acceptance settlement CAS/readback.

The formal terminal chain still did not start. Acceptance sent an ordinary completion delivery to Coordinator and
ended its turn without calling Team Transport `report_task_result`; consequently there was no Acceptance terminal
result, no Modeling/Protocol/Coordinator terminal handoff, no four-role settlement, and no final report. The role's
formal task-text branch omitted the generic terminal-tool instruction and its package told it to return the verdict to
Coordinator and await another ticket/settlement instruction. This is `collaboration/routing`, not a modeling-quality
result. Cleanup is `CLEANED`, Acceptance remains durably `settled`, all four child attempts are terminal/recycled,
credentials are destroyed, and the non-empty failed-written Project/Ontology is retained.

The exact start69–start71 authorization is exhausted. Strict ledger state is 317 records, 76,502 bytes, SHA-256
`b0ee08342ed4fa29c437aec835f88cf89cfe4bdc5c1510c6e7275106908b1a86`. No start72 may launch without new explicit
user authorization. The reviewed deterministic repair makes final cq-002 usable PASS require exactly one
`report_task_result(status=completed)` after the verdict route, mechanically rejects Acceptance non-completed terminal
status, and serializes the existing settlement finalizer behind one Runner-owned lock shared by foreground drain and
the terminal guard. It adds no automatic Agent report and preserves FAIL/BLOCKED revision reachability. Implementation,
independent testing, documentation sync, and commit may proceed offline; another live proof remains separately gated.

Implementation and independent Round 12 passed. A true two-thread test proves one settlement call/CAS/artifact/evidence
record, accepted completed report, and one Modeling handoff; settled-plus-blocked is rejected. Formal/non-formal actual
Runner start coverage and direct four-role order pass. R2.3-005 discovery is 176/176 with one opt-in skip, complete
modeling-team discovery is 493/493 with one opt-in skip, full modeling-team Ruff/diff/GitNexus and restarted service
health pass. Repository-wide Ruff still reports 48 pre-existing findings outside `modeling_team`; these are recorded
as non-blocking P2 baseline debt and do not weaken the requirement-scoped gate.

## 2026-08-10 R2.3-005 start72 审计、Luna-max 切换与授权边界

start72 `r23005-real-20260809-deepseek-start72` 的业务语义证据达到完整边界：候选、五阶段
Protocol 写入与 governed retrieval、两轮有序 CQ、四个独立 Examiner、两份 usable PASS verdict、settlement
CAS/readback、Acceptance -> Modeling -> Protocol -> Coordinator terminal handoff 与 Team settled 均成立。
但 Independent Round 13 在保留的 Runtime 产物中发现同一个真实 DeepSeek provider key：四个
`shell_snapshots/*.sh`、Protocol session JSONL 及 SQLite/WAL 共 7 个文件、21 次。因此该运行只可表述为
“semantic evidence PASS，overall requirement FAIL”；账本中的 `runtime/infrastructure,false` 是 Delivery
后审计分类。保留证据不得改写，暴露的 key 必须由提供方撤销/轮换并由用户确认。

后续 formal R2.3-005 Team 的模型选择改为独立 manifest
`modeling_team/model-manifests/r2-3-005-luna-max.yaml`，六个 package ID 精确绑定
`gpt-5.6-luna/openai/max`。共享 package YAML 和非正式/R2.3-002 路径不受影响。`TeamRunner.prepare`
在任何平台、账本、run root、transport、capability 或进程副作用前校验六包 manifest，并把 loader、初始
baseline 与 post-preflight 三个 digest 绑定。正式路径不得解析或注入 DeepSeek key；provider auth 只以
owner-only、non-symlink、O_NOFOLLOW/O_EXCL/0600/fsync 的临时 `auth.json` 进入 app-server 初始化，并在首个
turn 被接受后、任何模型选择的 ServerRequest/tool/MCP dispatch 前删除。

首轮 barrier 对 response 前普通 notification 做 buffer/replay；任何带 `id` 的 ServerRequest 必须先删
auth，再按当前 Codex schema typed respond。MCP discovery 读取 `tools` 字典 value 的 `name`，不得假设
opaque key 等于工具名，同时继续对 server/tool 集合做 exact fail-closed。同步 JSON-RPC error 与异步
ErrorNotification 均只允许安全的 method/code/category、`will_retry`、规范 variant 和可选整数 HTTP status；
provider free text 不得进入异常、stderr 或 evidence。typed Runtime failure queue 由 startup 和 Runner
drain 共同 exactly-once 收口；错误、warning 和状态心跳不得刷新 model-progress 时钟。

Independent Rounds 14–18 证明 manifest、非正式兼容、auth barrier、secret scan、opaque MCP 形状、typed
failure、Runner cleanup/terminal、R2.3-005 回归和服务健康均通过。最终确定性基线为 runner
`2796c938...`、Codex Runtime `e39b3645...`，R2.3-005 pytest discovery 272 passed/1 skipped/71 subtests，
完整 `modeling_team` 663 passed/1 skipped/218 subtests。真实 Luna 空业务 smoke 已能完成
initialize/thread/MCP/turn-start，并准确看到 Coordinator 的五个 Team Transport 工具；但 300 秒内没有
matching `turn/completed|turn/finished`，故 provider gate 仍为 `runtime/infrastructure` FAIL。

账本已登记 `user-20260809-r23005-start72-74`，start72 已消费，start73–74 数值上仍可用。用户于
2026-08-10 又明确追加三次授权，冻结标识为 `user-20260810-r23005-start75-77`；严格账本要求当前 tranche
在 start74 终态后才登记下一笔 authorization，因此当前只记录用户决定，不提前修改账本。概念上未消费
授权共 5 次（start73–77），但在 key rotation 与 Luna matching-terminal gate 完成前全部暂停。

## 2026-08-10 R2.3-005 formal Team 回退 DeepSeek v4 Flash

用户确认放弃当前 Luna provider gate，正式 R2.3-005 Team 的四个持久角色与 Source/Platform Examiner
统一回退到精确 tuple `deepseek-v4-flash/deepseek/max`。新的 formal-only manifest 取代 Luna manifest；
共享 package YAML、非正式运行与 R2.3-002 行为保持不变。Luna Rounds 14–22 的 deterministic 成果与失败/
BLOCKED 证据继续保留，但不再是后续 semantic start 的前置条件。

回退不得恢复 start72 的 provider key 环境注入。真实 key 只能存在于仓库外固定路径
`~/.config/ontology-platform/modeling-team-deepseek.env` 的 owner-owned、regular、non-symlink、mode `0600`
本机凭据文件以及 Runner-owned provider proxy 的内存中。`TeamRunner.prepare`
必须在平台、账本、run root、transport、capability 或 Agent 进程副作用前校验凭据文件元数据与 exact
assignment 形状，并冻结仅含 canonical path、device、inode、size 与 mtime-ns 的内存 binding；Runtime
启动前必须通过 `O_NOFOLLOW` 重新打开、fstat exact binding 后才读取 key，防止 preflight/start TOCTOU。
不得把 key 或 key digest 写入 baseline、manifest 或 evidence。正式 Codex/App Server 与 Examiner
进程的 env、argv、TOML、auth、shell snapshot、session JSONL、SQLite/WAL/SHM、stderr 和 Runner evidence
均不得包含 key bytes。正式路径必须忽略 ambient `DEEPSEEK_API_KEY`/`LLM_API_KEY`，不得把 Host env
sentinel 读入 Adapter memory；只有固定文件可以为正式 proxy 提供 key。非正式/R2.3-002 旧 provider
解析兼容性不受此限制。

Runner 为每个正式 Team run 启动一个 loopback-only、临时端口、生命周期受控的 DeepSeek provider
proxy。正式 Codex config 只获得 proxy base URL、model/provider/reasoning 和无 secret 的 provider 定义；
不得配置 `env_key`、静态 bearer token 或 key-bearing command。Proxy 只允许冻结的 Responses API 方法/
路径与有界请求体，移除任意来宾 Authorization 后注入 Host key，流式转发响应，且不记录 header/body/
provider free text。启动失败、非 allowlist 请求、上游连接失败或 proxy 提前终止均归类为安全的 typed
`runtime/infrastructure` failure。正式 DeepSeek 仍必须使用现有首轮 notification buffer/ServerRequest
防死锁路径，但 credential transition 为无文件的 `provider_proxy_ready`，不得要求或模拟 `auth.json`。
stop 必须先停止所有 Agent/Examiner，再关闭 proxy 网络入口；在 key buffer 仍可用于内存比较时扫描全部
Runtime 产物。持久角色与 Examiner 的 stderr 必须由 formal-only 有界 drain 持续消费并执行跨 chunk
sentinel 比较，既避免 pipe backpressure，也不得持久化 stderr 原文或 digest；命中只记录安全计数并令
credential cleanup 失败。审计 evidence 只记录计数/布尔结果而不记录 key digest，最后覆盖并释放内存 key。

完成门要求六 package manifest/preflight、formal/non-formal request shape、proxy allowlist/streaming/
lifecycle、secret sentinel 全类扫描、failure/cleanup 和完整回归独立 PASS。随后只允许一次无业务 source、
无 platform/Runner reservation/StartLedger mutation 的 formal Coordinator 空任务 smoke；只有 matching
terminal 且 zero-secret/zero-residue 才重新开放 start73。不得把离线或 mock-only PASS 当成 provider PASS。

实施与 Independent Round 25 已满足上述 Runtime/provider 完成门：完整 deterministic 回归、服务健康、
proxy/auth/streaming/cleanup/secret gate 均通过，唯一真实空任务以精确 `deepseek-v4-flash` 收到 matching
`turn/completed`，且 key 未进入任何 Runtime 产物。该结果只重新开放 start73，不代表任何业务模型、CQ、
Acceptance 或 settlement 已通过。

## 2026-08-10 R2.3-005 start73 Examiner 终态仲裁修订

start73 `r23005-real-20260810-deepseek-start73` 完成候选发布、五阶段平台应用、governed retrieval 与
`cq-001` 双 Examiner PASS，但两个 Examiner 的 terminal report 已持久化后，absolute child watchdog 又迟到
记录 `runtime/child-timeout`。Carrier 因而同时保留 PASS report 与 retryable failure，`cq-001` 状态落为
`retryable`，顺序门以 `prior_round_cleanup_required` 正确拒绝 `cq-002`。该运行受控停止并记为
`runtime/infrastructure,false`；保留运行证据、平台对象和账本不得事后改写。

同一 Examiner handle/attempt 必须恰有一个终态赢家。Terminal report 与 infrastructure failure 的检查、
持久化、round 状态、pending report、recycle 和 cleanup 必须由 Carrier 的同一互斥边界仲裁：report 先赢时
迟到 watchdog 不得写 failure、设置 retryable 或终止进程；failure 先赢时 late report 必须 fail-closed。
Formal Source/Platform Examiner 必须先在 Carrier 注册 resource/proxy receipt，再激活 stdout pump，避免合法
Platform report 在 resource 尚不可见时被误判。Direct/non-formal Runtime 保持原 immediate-pump 行为。
只有 failure 真正持久化后 watchdog 才可终止 child；failure callback 的非冲突持久化异常必须进入既有
typed Runtime failure queue 并 exactly-once 清理，不得静默悬挂或伪造 PASS。

Independent Round 26 已验证 report-first、failure-first、双线程边界、recycle/late callback、formal deferred
pump、direct/non-formal 兼容与 callback-error typed failure，完整回归和服务健康均通过。该修订只恢复
start74 的运行资格，不把 start73 的 `cq-001` 局部 PASS 解释为完整 semantic acceptance。

## 2026-08-10 R2.3-005 start74 最终清理审计修订

start74 `r23005-real-20260810-deepseek-start74` 的候选、五阶段应用、validation/reasoning、governed
retrieval、两轮 CQ、settlement 和四角色 terminal chain 均形成完整 PASS 证据，但 retained `state.json`
中 coordinator/modeling/protocol 的 credential cleanup 投影为 false。独立 Round 27 确认最终文件中没有固定
DeepSeek key bytes 或敏感私有文件；失败来自 Runtime 逐角色清理时反复扫描整个 run root：前三个角色审计时
Protocol 尚未删除的临时 `config.toml` 仍合法存在，因而被误记为残留。start74 继续保留为 semantic PASS、
overall `runtime/infrastructure,false`，不得事后改写或追认。

正式 Runtime cleanup 必须采用两阶段边界：先停止所有 Examiner/持久角色并删除各自私有 artifact，再在
provider proxy 的 mutable key buffer 尚可比较时，对 run root 执行恰好一次最终 aggregate secret audit，
然后关闭 proxy、验证 listener/thread/socket 已退出并覆盖 key。最终投影只可包含安全计数/布尔值，不得包含
secret、路径、异常文本或 secret digest。目录遍历、metadata/read、live `/proc` surface 任一失败必须通过
`scan_complete=false` 与 `scan_error_count` fail-closed，且不得伪造成 secret match。

首次 cleanup 的 aggregate 与 per-role 投影必须在 lifecycle lock 下锁存；重复 stop/读取不得重扫或把失败
翻成成功。Child destroy 残留、role unlink/stop/stderr 异常、proxy shutdown/close/join/socket/wipe 异常均须
以安全计数保留并令完成门失败，同时继续清理其余资源。新 run 只能在没有 active role/child/proxy 后重置该
lifecycle snapshot；non-formal 与 R2.3-002 的 stop 行为和 evidence schema 不变。Independent Round 28 已以
确定性回归、完整 modeling_team 回归和服务健康验证该修订；该 PASS 只验证未来 cleanup 机械边界，不改变
start74 retained verdict，也不构成新的 semantic start。

## 2026-08-10 R2.3-005 Start75 最终验收

Start75 `r23005-real-20260810-deepseek-start75` 在已提交的 DeepSeek Runtime、Examiner 终态仲裁和最终
aggregate cleanup 基线上完成唯一一次正式语义运行。运行创建 fresh Project/Ontology，按
`class/property/entity/relation/shape` 完成 dry-run/apply，validation conforms、reasoning consistent，
并保留七条 governed retrieval 路径及 Evidence/lineage。`cq-001`、`cq-002` 均为 current/usable PASS，
四个 fresh Examiner child 无 infrastructure failure，settlement CAS/readback 与五条 terminal handoff
顺序完整。

Independent Round 29 仅以普通文件只读方式审计 retained tree，未连接 SQLite、未启动进程或模型、未调用
平台、未修改账本。804 个文件的审计前后快照一致；最终 aggregate/per-role audit 均为 scan complete、
zero match、zero error、zero child residue，proxy listener/thread/socket 已关闭且 key buffer 已覆盖。固定
DeepSeek key bytes 在 retained 非 SQLite 产物中 0 files/0 occurrences。严格账本只记录 Start75 的一次
reservation 与一次 semantic_start，无 terminal failure 或后续 start。因此 R2.3-005 完成门为 PASS，
Start76–77 不再执行。
