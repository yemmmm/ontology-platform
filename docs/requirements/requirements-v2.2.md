# v2.2 本体建模团队协作需求

## 文档信息

- 文档状态：L0、L1 已实现并通过独立验收；独立 L2 已取消并合并到 L3；L3 待细化
- 基础版本：`docs/requirements/requirements-v2.1.md`
- 关联版本：`docs/requirements/requirements-v1.0.md`、`docs/requirements/requirements-v1.1.md`、
  `docs/requirements/requirements-v2.0.md`
- 当前需求：R2.2-001 本体建模团队三 Agent 协作
- 更新日期：2026-07-30

## 背景

R2.1-001 M3 已证明一个隔离的自主建模 Agent 可以通过正式平台入口完成建模闭环。后续 M5-P0
尝试把底层 Runtime 从 Codex 替换为 Pi 时，又为 Pi 重复实现了平台文件队列、Runtime 生命周期、
Producer 准入、lease recovery、Consumer 和 mutation 编排。v2.2 最初据此计划提取一套公共 Host
Workflow，并让每个 Runtime 只实现薄 Runtime Adapter。

进一步分析表明，这个方案仍然把过多职责固化在 Host：平台协议转换、运行编排、测试准入、
Consumer、mutation 和最终验收被放入同一个公共工作流，建模流程每次演进都需要修改 Host。
Runtime Adapter 同时把 Codex、Pi 的启动和事件差异提升成正式架构概念，但这些只是执行环境细节。

v2.2 因此不再以公共 Host Workflow 或 Runtime Adapter 为目标。当前目标是建立一个由三个专职
Agent 组成的 **本体建模团队（Ontology Modeling Team）**：建模协调 Agent 负责调度和关键决策，
建模 Agent 负责业务语义与本体判断，平台协议 Agent 负责把日常建模描述转换为严格平台协议并
调用平台建模 MCP。

当前交付 Session 不兼任团队内部的建模协调 Agent。它作为团队外部的交付 Agent，负责需求实现、
测试环境、用户消息转发、运行观测和收尾；正式建模由一个不继承交付 Session 历史的全新 Codex
Session 承担。

## 需求列表

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.2-001 | 本体建模团队三 Agent 协作 | P0 | L0、L1 已实现；独立 L2 已并入待细化的 L3 | R2.1-001 M3/M6 隔离证据；R-003、R-004 MCP |

## R2.2-001 本体建模团队三 Agent 协作

### 现状是什么，需要改成什么

当前：

- 当前交付 Session 同时负责需求实现、测试调度、平台机械操作和部分建模决策，职责容易混淆；
- 已验证的 Codex 路线主要是“主 Agent + 一个隔离建模 subagent”，没有独立的平台协议 Agent；
- 当前 Codex 配置只向 Agent 暴露平台只读 MCP；Build Session、Lease 和 Modeling Batch 写工具
  虽然已在平台实现，但未形成面向专职协议 Agent 的工具边界；
- M3/M5/M7 的 Host 同时承担平台协议、安全门、评测编排和运行收尾，流程过于固定；
- Pi 已有多角色 Runtime 证据，但其现有 coordinator、organizer、modeler、reviewer 角色并不是
  本需求确认的三 Agent 协作合同。

目标：

- 当前交付 Session 只作为交付 Agent，不进入本体建模团队，也不代做团队内关键建模决策；
- 启动一个全新、非 fork/resume、看不到交付 Session 历史的 Codex Session 作为建模协调 Agent；
- 建模协调 Agent 在自己的 Session 内调度建模 Agent 和平台协议 Agent；
- 建模 Agent 使用业务和建模语言形成候选，不需要编排 Build Session、Lease、版本或 Batch；
- 平台协议 Agent 把建模描述转换为严格 Modeling Items 和平台 MCP 调用；
- 机械格式问题由协议 Agent 自行修复；状态、范围、版本或内容冲突返回建模协调 Agent，由其决定
  询问协议 Agent、要求建模 Agent 修复，或追问用户；
- Host Workflow、Runtime Adapter、Consumer、mutation 和 Judge 不成为生产建模架构的一部分。

### 系统与角色

#### 本体建模团队

本体建模团队是完成一次本体建模任务的三 Agent 协作系统，不等同于其中的建模 Agent，也不是
Semantic Platform Core 或某个特定 Runtime。

```text
用户
  ↕
交付 Agent（当前交付 Session，团队外）
  ↕ 任务、原始用户回答、环境状态、暂停/继续/终止
建模协调 Agent（全新 Codex Session）
  ├─ 建模 Agent
  └─ 平台协议 Agent
       ↕
  Semantic Platform MCP
```

#### 交付 Agent

- 负责 v2.2 的实现、测试准备、运行监控、用户消息转发和资源收尾；
- 启动、继续或终止建模协调 Session；
- 只向建模协调 Agent 传递已冻结任务、用户原始回答、环境状态和控制指令；
- 不提供隐藏验收答案、预期本体、答案型 Batch/Query，且不替团队选择本体结构。

交付 Agent 是交付流程中的角色，不是本体建模团队的第四个 Agent。

#### 建模协调 Agent

- 是本体建模团队的唯一调度中心和用户问题出口；
- 分配建模 Agent 和平台协议 Agent 的任务，并综合两者反馈；
- 决定平台冲突应交由协议 Agent 重新读取状态、交由建模 Agent 修改候选，还是追问用户；
- 决定建模目标、范围和关键语义取舍，但不亲自拼装 Modeling Batch；
- 只有需要用户事实、范围变更、不可逆操作确认或无法消除的阻塞才返回交付 Agent。

#### 建模 Agent

- 读取允许的业务资料，识别语义缺口，形成和修正本体候选；
- 使用面向业务和本体的描述表达 Class、Property、Relation、Shape、规则和实例意图；
- 将业务歧义、证据不足和关键建模取舍反馈给建模协调 Agent；
- 不负责 canonical JSON、UUID、Build Session revision、workspace version、Lease 或 Batch 重试。

#### 平台协议 Agent

- 只负责理解并遵循公开平台建模协议；
- 把建模描述转换为严格 Modeling Items 和 MCP 参数；
- 调用 Build Session、Lease、Modeling Batch、validation、reasoning 和 query 等平台 MCP；
- 可以自行修复 JSON、Schema、必填字段、IRI、参数和操作顺序等不改变语义的机械问题；
- 遇到 workspace revision、Batch 内容、作用域、并发状态或需要改变语义内容的冲突时停止自行
  修复，并把完整错误和可选处理路径反馈建模协调 Agent；
- 不擅自补造业务事实、改变候选含义或绕过平台验证。

Semantic Platform Core 继续强制权限、范围、版本、Lease、Batch 一致性、确定性校验和原子写入；
协议 Agent 的自我纠错不能替代平台约束。

### 协作与错误路由

1. 交付 Agent 向建模协调 Agent 提交冻结任务和允许资料；
2. 建模协调 Agent 向建模 Agent 分配语义建模工作；
3. 建模 Agent 返回业务描述、候选和问题，不直接执行平台写入；
4. 建模协调 Agent 把获准执行的候选交给平台协议 Agent；
5. 平台协议 Agent 转换并调用平台 MCP：
   - 格式、Schema、必填字段、IRI 或调用顺序错误：自行修复并重试；
   - 平台状态可以无语义变化地重新读取：重新读取后继续；
   - workspace、Batch 内容、作用域、并发或语义冲突：停止并反馈建模协调 Agent；
6. 建模协调 Agent 判断冲突属于机械协议、建模候选还是用户事实：
   - 机械协议问题退回平台协议 Agent；
   - 建模问题退回建模 Agent；
   - 业务事实或范围问题通过交付 Agent 一次提出一个问题；
7. 用户回答由交付 Agent 原样转发，不追加隐藏验收提示；
8. 只有平台成功写入、验证、查询和治理记录构成平台事实。

### 资料与运行隔离

每次正式尝试必须使用全新的建模协调 Session、子 Agent Session、运行目录、Project、Ontology 和
Build Session。建模协调 Session 不从交付 Session fork/resume，也不继承其聊天历史、Memory、
历史 rollout 或项目级答案材料。

测试资料至少分为：

- `agent-visible`：冻结业务资料、建模目标、公开平台合同和已释放用户回答，三 Agent 可按职责读取；
- `team-work`：团队本轮产生的候选和允许交接结果；
- `tester-only`：隐藏答案、预期缺口、历史正确模型、答案型 Batch/Query、Judge 合同和 mutation
  规范，只供测试方使用；
- `audit`：manifest、Session ID、事件、平台 receipt 和隔离检查结果，只供交付与测试使用。

`tester-only` 是测试资料分类，不是产品架构概念。正式可信测试必须使用 `bubblewrap` 或等价 OS
隔离，使宿主仓库、交付 Session 状态、历史运行目录和 tester-only 资料在建模团队进程中不可见；
不能只依赖 Prompt 禁止读取。

三个团队 Agent 可以共享同一隔离运行根，但权限不同：

| 角色 | 允许资料 | 平台写 MCP |
| --- | --- | --- |
| 建模协调 Agent | agent-visible、team-work、两个 Agent 的反馈 | 不直接调用 |
| 建模 Agent | agent-visible 中的业务资料、当前任务和已公开回答 | 无 |
| 平台协议 Agent | 当前候选描述、公开平台合同、平台响应 | 有 |

### 当前最小范围：L0 三 Agent 协作与隔离探针

L0 只验证架构可运行，不执行真实本体写入，也不证明建模质量：

1. 交付 Agent 启动一个全新、受限且可继续的 Codex 建模协调 Session；
2. 建模协调 Agent 启动一个建模 Agent 和一个平台协议 Agent；
3. 建模 Agent 返回一个固定的非答案型建模描述；
4. 平台协议 Agent 调用一次允许的只读平台 health 或 modeling-context MCP，并返回规范结果；
5. 建模协调 Agent 向交付 Agent 提出一个固定测试问题，当前 Session 转交用户或测试回答后继续
   同一个建模协调 Session；
6. 建模协调 Agent 根据回答完成一次路由并正常结束；
7. 隔离探针证明团队可以读取 agent-visible、写 team-work，但看不到宿主仓库、交付 Session 状态
   和 tester-only；
8. 事件记录能够区分建模协调、建模和协议三个 Agent，并保留 MCP 调用及问答恢复证据。

首版优先使用 Codex 已有多 Agent 能力和可继续 Session；Pi 不是 L0 前置。只有 Codex L0 暴露
无法通过最小配置解决的能力缺口，或后续需要更强的常驻生命周期控制时，才以同一合同评估 Pi。

### 当前非目标

- 真实 Modeling Batch dry-run/apply 或完整本体建模；
- Consumer、Judge、mutation、重复成功率或 Runtime 横向对比；
- 将 Runtime Adapter、Host Workflow 或测试 launcher 提升为平台产品概念；
- backend 常驻 Agent Runtime、远程调度、跨机器协调或管理 UI；
- 生产级凭据代理、通用 sandbox 产品或自动崩溃恢复；
- 退役现有 Codex、Claude 或 Pi 历史路径。

### L0 验收标准

1. 建模协调 Session 是新鲜非 fork/resume Session，不含交付 Session 历史；
2. 三个团队角色均实际运行，职责和事件可区分；
3. 建模 Agent 无平台写 MCP，平台协议 Agent 使用受限平台 MCP，协调 Agent 不直接拼装调用；
4. 一次协议 Agent 平台只读调用成功，返回结果可追溯；
5. 一次问题、外部回答和同 Session 继续闭环成功；
6. agent-visible/team-work 访问符合预期，宿主仓库、交付状态和 tester-only 的隔离探针通过；
7. 未使用 Host 代做建模或协议选择，未引入 Runtime Adapter 正式概念；
8. L0 自动化测试、真实 Codex 冒烟和独立测试记录 PASS；本轮资源清理后常驻服务健康。

实现结果（2026-07-30）：

- fresh run `l0-r22-real-20260730o` 完成建模协调 Agent、建模 Agent、平台协议 Agent 三方协作；
- 平台协议 Agent 唯一调用 `check_platform_health` 并取得 PostgreSQL `status=ok`，其他角色无平台调用；
- 建模协调 Agent 提问后以同一 Session 恢复并完成；
- 临时 Project-scoped `read` key 已撤销，隔离与审计门通过；
- 21 项自动化测试和独立测试 Round 4 PASS。

### L1：版本状态简单业务切片的真实写入

L1 复用 v2.1 的 Dify 固定资料，但不直接建模完整的 Workflow-as-Tool `C -> B -> A`
影响传播切片。当前选择其中更小的 **Workflow 版本状态** 切片，只回答：

- 一个 Workflow 的工作版本和当前线上版本如何区分；
- 发布前的 Current Draft 为什么不能与 Latest Version 混为同一状态；
- 一个具体 Workflow 可以同时保留一个合成 Current Draft 和一个合成 Latest Version，且查询能够
  明确返回两者不同的业务含义。

Agent 可见资料只包含 v2.1 固定快照中的 Version Control 官方页面、对应 manifest/来源信息、
上述业务问题、合成 Workflow 名称和公开平台建模合同。M1–M6 已有 Ontology、Shapes、Batch、
查询、历史正确模型和隐藏断言均不可见。

L1 分两步执行：

1. `L1-S0 模拟`：在不开放写 MCP、不创建平台资源的条件下，用上述资料重放 L0 的三角色职责。
   建模 Agent 形成业务/本体候选描述，平台协议 Agent 只把获准候选转换成拟执行的公开命令计划，
   建模协调 Agent 完成派工和结果路由。该步骤验证 L0 角色边界对真实资料仍然成立，不声明平台
   写入成功。
2. `L1-S1 真实写入`：使用全新的协调、建模和协议 Agent Session、运行目录、Project、Ontology
   与 Build Session。建模 Agent 独立形成候选，建模协调 Agent 发出协议任务；只有单独隔离的
   平台协议 Agent 获得临时 Project-scoped `model` key，并通过公开 MCP 完成 Build Session、
   Lease、Modeling Batch `dry_run`/`apply_atomic`、应用后读取与 Session 收尾。

当前 Codex 不支持已验证的 child-only MCP 配置，因此不得把写 MCP 和 `model` key 放入协调 Agent
及其建模子 Agent 的共享配置。允许测试 launcher 根据协调 Agent 的显式派工机械启动单独隔离的
平台协议 Agent；launcher 只准备空 Project/Ontology、传递候选、托管临时 key 和清理资源，不得
构造 Modeling Items、选择本体结构、修复语义或提供隐藏答案。

L1 不改动常驻 `8001` 的 product write mode。测试 launcher 必须启动独立、唯一端口的
`rdf_primary` REST 环境，并让协议 Agent 的 stdio MCP 使用相同 PostgreSQL、Oxigraph 和
`rdf_primary` 配置；团队启动前先验证该配置，否则 fail-fast。宿主可通过受审计的本地 bootstrap
创建一把不进入任何 Agent namespace 的临时 org-admin key，仅用于空 Project/Ontology 准备、
Project-scoped `model` key 创建/撤销、Project 删除和清理验证。两把 key 必须分别追踪并在所有
终态撤销。

协议 Agent namespace 不得挂载 `backend/.env` 或包含长期平台 key 的宿主配置。stdio MCP 只挂载
净化后的应用代码和运行依赖，通过本轮进程环境取得临时 `model` key、数据库/图存储连接和
`rdf_primary` 模式；缺少本轮 key 时必须认证失败，不能回退到宿主 `.env`。

L1 最小验收：

1. L1-S0 使用真实版本资料完成三角色模拟，且没有平台写入；
2. L1-S1 的建模协调 Agent 与建模 Agent 看不到写 MCP、临时 key、宿主仓库和 tester-only；
3. 平台协议 Agent 只看到获准候选、公开协议和当前平台响应，且是唯一执行平台写调用的 Agent；
4. 协议 Agent 创建 Build Session、取得 Lease，并对同一不可变候选先完成 `dry_run`，再完成
   `apply_atomic`；workspace version 确实前进；
5. 应用结果至少表达 Workflow、Workflow Version、Current Draft 与 Latest Version 的可区分
   语义，并能通过一个通用 read model 或 scoped query 读取；
6. 至少一个与版本状态有关的最小约束由平台确定性验证，不能只写入无约束标签；
7. Agent 事件、MCP 调用、Batch receipt、Session/Lease 状态、输入哈希、凭据撤销和资源清理均可
   追溯，且无现有答案材料泄漏；
8. host-admin 与 protocol-model 两把临时 key 隔离、分别撤销，协议 namespace 看不到
   `backend/.env` 或其他平台凭据；
9. 自动化回归、真实 Codex 建模证据和独立测试 PASS；真实运行的最终验收可以由交付 Agent 与
   独立测试 Agent 直接复核平台 receipt、语义读取和清理证据，不要求再实现一套自动 Judge；
   独立 `rdf_primary` 环境退出、清理后常驻服务健康。

L1 不要求建模 Tool Invocation、Binding、变量使用、Change Set、传递影响路径、Consumer/Judge、
mutation、重复成功率或证明团队已提升完整业务切片的建模质量。这些是否进入完成门由后续 L3
细化决定；错误路由不再形成独立 L2 交付阶段。

实现结果（2026-07-30）：

- 使用 v2.1 固定 Version Control 页面完成 Workflow 版本状态简单切片，未建模完整
  Workflow-as-Tool 影响链；
- `L1-S0` 在平台资源创建前完成 Coordinator、Modeling Agent、Protocol Planning Agent
  三角色无写入模拟；
- `L1-S1` 中只有隔离的 Platform Protocol Agent 调用平台 MCP，真实完成 Build Session、
  Lease、不可变 Batch `dry_run -> apply_atomic`、负向约束验证、读取和 Session 收尾；
- 平台读取返回独立的 Workflow、Current Draft、Latest Version 以及分别连接到两种状态的两个
  Workflow Version；Shape 要求每个 Version 恰有一个所属 Workflow 和一个版本状态；
- 运行 `l1-i` 的自动 rollout 统计把同一运行目录中的 S0 children 混入 S1，因而误报
  `INCONCLUSIVE`。交付 Agent 和独立测试 Agent 直接复核原始 rollout、MCP receipt、Batch、
  workspace、语义读取及清理证据后判定 L1 `PASS`；该统计问题仅作为非阻断测试工具维护项；
- 15 项 L1 回归、21 项 L0 回归、Ruff、常驻服务健康检查和独立测试 Round 2 PASS；临时 Project
  已删除，host-admin 与 protocol-model key 均已撤销。

### 后续阶段

L1 通过后直接细化 L3，不再单独设计、实施或验收 L2：

- L3 使用真实业务切片验证三 Agent 协作是否提升建模质量；
- 原 L2 的错误路由能力作为 L3 内嵌验收维度：机械格式错误由平台协议 Agent 自行修复；平台
  状态冲突不得盲重试，必须重新读取或交由建模协调 Agent 决策；语义冲突必须退回建模 Agent，
  需要业务事实时才通过交付 Agent 询问用户；
- 优先使用 L3 真实运行中自然产生的错误证据；某类关键边界未自然出现时，只在同一 L3 范围内
  增加最小确定性探针，不建设独立错误矩阵、通用故障注入框架或单独 L2 场景；
- L3 必须区分 `modeling-quality`、`collaboration/routing` 和 `runtime/infrastructure` 失败，避免
  用基础设施或协议故障替代建模质量结论；
- Runtime 复现仅在需要时用 Pi 或其他 Runtime 重放同一团队合同。

L3 的具体业务切片、质量验收和评测设施范围仍需逐项细化，不能因合并 L2 而自动扩大。

### 与既有需求的关系

- v1.0 R-003/R-004/R-008 继续提供 Build Session、Modeling Batch、认证和 Project 隔离；
- v1.1 的建模方法、Coverage、Work Unit 和评审机制可作为后续团队任务，不是 L0 前置；
- v2.0 Pi Runtime 保留为候选实现，不决定本体建模团队的角色合同；
- v2.1 M3/M6 提供 Codex fresh-session、输入隔离和自主建模证据；
- v2.1 M5-P0 和原 v2.2 Host/Adapter 方案作为历史问题证据保留，不再作为目标架构；
- Consumer、Judge 和 mutation 仍属于独立评测设施，不进入本体建模团队生产职责。
