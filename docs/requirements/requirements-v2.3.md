# v2.3 本体建模团队运行标准化需求

## 文档信息

- 文档状态：R2.3-001 已完成需求细化，待设计与实现；R2.3-002～R2.3-004 已确认路线，
  待按依赖顺序分别细化
- 基础版本：`docs/requirements/requirements-v2.2.md`
- 关联版本：`docs/requirements/requirements-v2.0.md`、
  `docs/requirements/requirements-v2.1.md`、`docs/requirements/requirements-v1.1.md`
- 当前实施需求：R2.3-001 Team Runner、Agent Package 与 Codex Team Adapter
- 关联交付记录：
  `docs/delivery/records/2026-07-30-r2-3-001-ontology-modeling-team-standard-delivery-record.md`
- 总体目标：固定本体建模团队的机械运行基础，使后续建模流程优化主要通过新增 Agent、
  调整 Modeling Team Profile 和优化 Skill 完成
- 更新日期：2026-07-31

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
| R2.3-001 | Team Runner、Agent Package 与 Codex Team Adapter | P0 | `待实现（需求细化已完成）` | R2.2-001 L0/L1/L3；Codex 多 Agent；平台认证与 MCP |
| R2.3-002 | 新作用域真实业务切片建模 | P0 | `待细化` | R2.3-001 |
| R2.3-003 | 已有 Project/Ontology 增量建模 | P0 | `待细化` | R2.3-002 |
| R2.3-004 | Pi Team Adapter | P1 | `待细化` | R2.3-001；R2.0-002；R2.3-002/003 证据 |

## 总体交付顺序

```text
R2.3-001 Runner、Package、Codex Adapter
  -> 真实 Agent 能力与互操作冒烟，不实际建模
  -> R2.3-002 从新作用域完成一轮真实业务切片
  -> R2.3-003 用全新团队继续 002 的已有非空 Project/Ontology
  -> R2.3-004 整体切换到 Pi Team Adapter
```

后续需求不得为了通过自身验收修改已经在 R2.3-001 接受的 Team Runner 核心语义。真实运行暴露
Runner、Adapter 或平台合同缺陷时，可以按独立需求的评审和测试流程修复对应窄层；建模质量问题
应优先通过 Agent、Skill、Profile 或业务输入合同处理。

## R2.3-001 Team Runner、Agent Package 与 Codex Team Adapter

当前状态：`待实现（需求细化已完成）`

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

当前状态：`待细化`

优先级：`P0`

### 现状是什么，需要改成什么

当前：

- R2.3-001 只证明 Runner、Package、Profile、Codex Adapter 和 Agent 能力边界，不执行真实建模；
- R2.2 L3 已有真实三 Agent 证据，但使用场景专用 launcher，不能证明 R2.3 Runner 的建模闭环。

目标：

- 使用 R2.3-001 的基础三 Agent Profile 和未修改的 Team Runner；
- 从全新 Project/Ontology 开始完成一个有界业务切片的真实建模；
- 验证直接 Agent 协作、持续用户对话和 Protocol-only 平台写入；
- 产生可供 R2.3-003 继续使用的非空 Project/Ontology。

### 已确认范围

- 业务切片、来源、用户问题和尝试预算在 R2.3-002 开始前单独细化；
- Modeling Agent 负责真实业务语义和本体判断；
- Protocol Agent 通过正式平台入口完成 Build Session、Lease、不可变 Modeling Batch
  `dry_run -> apply_atomic`、validation、reasoning 和查询；
- Coordinator 在建模期间继续与用户对话，但不审核模型或监看 Agent 语义进度；
- 本需求不修改 Team Runner 的团队语义、Profile/Package 合同或 Codex Adapter 接口；
- 不以额外专业 Agent 作为完成前提，也不进行 Profile 质量对照。

### R2.3-002 最小完成门

1. 使用全新 Runner run、Agent Sessions、Project、Ontology、Build Session 和 Lease。
2. 基础三 Agent Profile 完成真实业务切片，只有 Protocol 执行平台写 MCP。
3. 用户可以在建模期间继续与 Coordinator 对话并提供明确补充信息。
4. 正式 Modeling Batch 完成 dry-run/apply，validation conforms，reasoning consistent，通用查询
   支持已确认的业务问题。
5. Runtime、Build Session、Lease 和临时凭据完成收尾；Project/Ontology 有意保留给 R2.3-003。
6. 生成不含凭据、Agent 对话、隐藏答案或 tester-only 内容的 scope handoff，至少记录 Project ID、
   Ontology ID 和当前 workspace context。
7. 自动化回归、真实运行和独立测试 PASS。

### R2.3-002 非目标

- existing 模式真实增量建模；
- 新增 Agent 的质量效果；
- Pi Runtime；
- 把测试业务概念写成平台专属 API、Schema 或解释逻辑。

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

### 已确认范围

- R2.3-003 直接使用 R2.3-002 的 Project/Ontology 和非敏感 scope handoff，不另造独立业务 fixture；
- Team Runner、Codex Adapter 和基础三 Agent Profile 不因 existing 场景修改核心语义；
- Protocol 在写入前读取当前平台事实和 workspace context，并创建新的 Build Session/Lease；
- 本轮只通过新的 Modeling Batch 表达增量变化；
- existing 模式不删除 Project/Ontology，不抢占历史 Lease，不恢复历史 Agent Session；
- 增量业务目标、来源、用户问题和尝试预算在 R2.3-003 开始前单独细化。

### R2.3-003 最小完成门

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

### 已确认范围

- R2.3 不支持 Codex/Pi 混合团队；
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
