# v2.3 本体建模团队运行标准化需求

## 文档信息

- 文档状态：R2.3-001、R2.3-002 已交付并通过独立验收；R2.3-005 为当前下一项
  P0 目标、细化中；R2.3-003～R2.3-004 已确认路线，须按依赖顺序细化
- 基础版本：`docs/requirements/requirements-v2.2.md`
- 关联版本：`docs/requirements/requirements-v2.0.md`、
  `docs/requirements/requirements-v2.1.md`、`docs/requirements/requirements-v1.1.md`
- 当前下一目标：R2.3-005 Producer Runner 正式化收口与可重复调用
- 关联交付记录：
  `docs/delivery/records/2026-07-30-r2-3-001-ontology-modeling-team-standard-delivery-record.md`、
  `docs/delivery/records/2026-07-31-r2-3-002-new-scope-business-slice-delivery-record.md`
- 总体目标：固定本体建模团队的机械运行基础，使后续建模流程优化主要通过新增 Agent、
  调整 Modeling Team Profile 和优化 Skill 完成
- 更新日期：2026-08-03

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
| R2.3-005 | Producer Runner 正式化收口与可重复调用 | P0 | `细化中` | R2.3-001；R2.3-002 真实建模与验收证据 |
| R2.3-003 | 已有 Project/Ontology 增量建模 | P0 | `待细化` | R2.3-002（语义依赖）；R2.3-005（强制运营前置） |
| R2.3-004 | Pi Team Adapter | P1 | `待细化` | R2.3-005；R2.3-003；R2.0-002；R2.3-002/003 证据 |

## 总体交付顺序

```text
R2.3-001 Runner、Package、Codex Adapter
  -> 真实 Agent 能力与互操作冒烟，不实际建模
  -> R2.3-002 从新作用域完成一轮真实业务切片
  -> R2.3-005 Producer Runner 正式化收口与可重复调用
  -> R2.3-003 用全新团队继续 002 的已有非空 Project/Ontology
  -> R2.3-004 整体切换到 Pi Team Adapter
```

R2.3-003 仍然以 R2.3-002 的语义结果和非空 Project/Ontology 作为依赖，但只有在
R2.3-005 完成其强制运营前置后才可进入实现和真实运行。R2.3-004 必须排在
R2.3-005、R2.3-003 之后；Pi Adapter 的证据不能替代 Producer Runner 的可重复调用证据。

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
- 产生可供 R2.3-003 继续使用的非空 Project/Ontology。

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
- 成功 Project/Ontology 保留给 R2.3-003；existing 模式不删除它，最终由 R2.3-003 独立验收后的
  测试收尾负责删除。

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
- R2.3-003 启动前必须从平台重新确认 Project/Ontology 存在、归属关系正确，并且当前 workspace
  version 与 handoff 一致；
- 任一标识、归属或 workspace version 不一致时，R2.3-003 停止并报告漂移，等待人工确认；不得
  自动改写 handoff、回退平台状态或继续增量建模。

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

## R2.3-005 Producer Runner 正式化收口与可重复调用

当前状态：`细化中`

优先级：`P0`

### 权威目标与最小结果

从一个干净 checkout 且 git status 干净的仓库开始，稳定的 Runner invocation 必须使用一套正式
跟踪的最小 Producer `Task`、`Profile`、`Runner`、`Adapter` 基线，完成 **一次**真实、简单的
Producer 业务切片。该次调用按平台合同完成所需的 `dry-run`、`apply`、readback、validation 和
reasoning；三 Agent（Coordinator、Modeling、Protocol）各自登记 terminal，Runner 记录团队
settlement；随后生成不可变的 acceptance handoff，精确清理本轮凭据、Runtime、Session、Build
Session/Lease 及其他本轮拥有的资源，并保留可复核证据。一个全新的、独立的、只读的 Acceptance
Agent 必须在 Runner 之外读取该 handoff 和平台事实并独立判断语义 `PASS`。

Runner 只负责确定性机械能力（基线装载、启动、传输、终态/settlement、证据交接和所有权清理），
不是第四个 Agent，也不是语义权威；Producer Agent 负责业务语义，Acceptance Agent 负责独立
语义裁决。

### 明确边界

以下内容不是 R2.3-005 的前置条件，也不得为了本需求重新引入为完成门：P2、P2a、monitor、native
verifier、proof matrix、通用 acceptance framework/orchestrator、delivery-recovered/context resume、
R2.3-003 非空增量建模、Pi Runtime，以及 explicit datatype 或 language-tagged literal 写入。
R2.3-005 只记录上述未来目标；本轮不创建其 design、test plan 或 delivery record，也不宣称已经实现
或通过该目标。

### 现有证据边界

Round78 证明了保留模型及其独立 Acceptance 结果，但**没有**证明从干净 checkout、干净状态出发
的 Runner 可重复调用；该可重复性仍是 R2.3-005 的待细化、待实现和待验收内容。

## R2.3-003 已有 Project/Ontology 增量建模

当前状态：`待细化`

优先级：`P0`

### 现状是什么，需要改成什么

当前：

- R2.3-001 只机械验证空 existing 作用域；
- R2.3-002 从空作用域完成首轮真实建模，但尚未证明全新团队可以只依赖平台事实继续已有模型。

目标：

- 使用全新的 Runner run 和全新的 Agent Sessions；
- 通过 existing 模式连接 R2.3-002 明确保留的非空 Project/Ontology；
- 不继承 R2.3-002 Agent 对话、历史 Prompt、隐藏答案或本地运行目录；
- 完成一个新的增量建模目标，并证明已有模型保持正确。

R2.3-003 的语义依赖仍是 R2.3-002 的真实业务切片和非空模型；其运营启动前置则必须先满足
R2.3-005 的 Producer Runner 正式化收口与可重复调用完成门。

### 已确认范围

- R2.3-003 直接使用 R2.3-002 的 Project/Ontology 和非敏感 scope handoff，不另造独立业务 fixture；
- Team Runner、Codex Adapter 和基础三 Agent Profile 不因 existing 场景修改核心语义；
- Protocol 在写入前读取当前平台事实和 workspace context，并创建新的 Build Session/Lease；
- 本轮只通过新的 Modeling Batch 表达增量变化；
- existing 模式不删除 Project/Ontology，不抢占历史 Lease，不恢复历史 Agent Session；
- 增量业务目标、来源、用户问题和尝试预算在 R2.3-003 开始前单独细化。

### R2.3-003 最小完成门

进入真实运行前，必须已经有 R2.3-005 的独立验收证据；该证据只证明 Runner 运营基线，不替代
本需求自身的增量语义验收。

1. 使用全新的 Team Runner run、Coordinator、Modeling、Protocol Sessions、Build Session 和 Lease。
2. Agent 只读取当前平台事实、允许的新业务资料和非敏感 scope handoff。
3. 当前 workspace version 和既有模型在变更前被正确读取；没有历史 Agent 对话泄漏。
4. 增量 Modeling Batch 完成 dry-run/apply，workspace 前进，既有模型未被错误覆盖或重建。
5. 最终 validation、reasoning 和查询同时支持 R2.3-002 既有结果与 R2.3-003 新增结果。
6. existing 模式保留 Project/Ontology，只清理本轮 Runtime、Build Session/Lease 和临时凭据。
7. 独立验收后，测试收尾可以删除明确归属于 R2.3-002/003 的测试 Project；该删除不属于
   Team Runner existing 模式。
8. 自动化回归、真实运行和独立测试 PASS。

### R2.3-003 非目标

- 复用或恢复 R2.3-002 Agent Session；
- 合并两个并发写入团队；
- 自动解决历史 fenced、冲突或未知所有权状态；
- Pi Runtime；
- 长期 Project 生命周期管理或管理 UI。

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
- 单次运行中的 Coordinator、Modeling、Protocol 和其他 Profile Agent 全部使用 Pi；
- 复用 R2.3-001 的 Team Runner、Profile、Agent Package、通信、用户对话、权限和终态合同；
- 不修改 Semantic Platform Core 或增加 Pi 专属平台接口。

R2.3-004 只有在 R2.3-005 的 Producer Runner 运营基线和 R2.3-003 的已有模型增量证据均完成后
才可开始；Pi Runtime 的替换不能倒置或绕过该顺序。

### 已确认范围

- R2.3 不支持 Codex/Pi 混合团队；
- 本需求排在 R2.3-005、R2.3-003 之后；R2.3-005 的可重复 Producer invocation 是进入本需求的
  运营前置，不由 Pi Adapter 的首次实现反向补足；
- Pi 可以使用 Runtime-native Session、RPC、事件和 Workflow Package 装载，但角色语义与 Skill
  内容必须继续共享；
- Pi Adapter 至少复现 R2.3-001 的基础角色能力和额外真实 Agent 互操作冒烟；
- 是否使用 R2.3-002/003 业务切片完成真实 Pi 建模，在 R2.3-004 开始前单独细化；
- Pi Runtime 故障不能成为平台事实，平台写入仍只由 Protocol 通过公开接口完成。

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
