# v2.0 第一方建模 Agent Runtime 需求

## 文档信息

- 文档状态：v2.0 方向已确认；R2.0-001 已细化，待实现
- 基础版本：`docs/requirements/requirements-v1.0.md`
- 关联版本：`docs/requirements/requirements-v1.1.md`、`docs/requirements/requirements-v1.2.md`
- 总体目标：以 Pi 为首个候选实现，建立平台可控制、可观测、可调试且可替换的第一方建模
  Agent Runtime
- 当前实施需求：R2.0-001 Pi 建模 Agent Runtime 能力验证
- 目标用户：平台建模工作流开发者、建模质量调优人员和后续第一方建模 Agent 使用者
- 更新日期：2026-07-22

## 背景

v1.0 和 v1.1 坚持外部建模 Agent 与平台核心分离：外部 Agent + Skill 负责资料理解、业务澄清、
知识提取和建模判断，平台负责确定性验证、Evidence、Modeling Batch、持久状态、版本、审计、
查询和治理。该边界避免平台核心过早绑定特定模型、Agent 框架或模型供应商，并且仍是平台语义
事实和治理责任的基础。

实际建模工作流同时表明，只通过外部 Runtime 的 Skill、Plugin 或项目 Hook 驱动建模，会使以下
能力受到外部 Runtime 设计和版本变化影响：

- Agent、Session、Turn、消息和工具调用的完整生命周期观测；
- 工具调用前后的拦截、参数约束、结果处理和危险操作控制；
- 主 Agent 与角色化子 Agent 的上下文隔离、交接和恢复；
- 中断、压缩、重试、模型切换和长任务状态的确定性调试；
- Prompt、Skill、工具、模型、Runtime 和工作流版本的实验对比；
- token、耗时、错误、返工和质量问题的稳定关联。

v1.1 已通过 repo-local Harness、Hook、双 Session mailbox、Shared Modeling Directory、Profile 和
Adapter 缓解部分问题，但这些适配仍依赖 Claude Code、Codex 等外部 Runtime 提供的能力和行为。
当 Runtime 无法暴露所需事件或改变 Hook、子 Agent、工具和会话合同后，平台难以保证建模过程的
监控和调试能力保持一致。

因此，v2.0 调整的是产品交付边界，而不是语义事实权威边界：平台产品可以提供一个第一方、可替换
的建模 Agent Runtime；Semantic Platform Core 继续保持确定性，不把 Agent 的判断、隐藏推理或
会话状态当作平台事实，也不依赖某个模型供应商。

Pi 是 v2.0 的首个候选 Runtime。它是否适合作为正式集成基础，必须先通过 R2.0-001 的能力验证，
不能因为已经选择候选实现就预先认定选型成功。

本文所称 Pi 固定指向 `earendil-works/pi`（原 `badlogic/pi-mono`）仓库及其中的
`@earendil-works/pi-coding-agent`。R2.0-001 必须再固定一个可重复取得的 commit 和依赖锁；同名的
其他 Pi 项目、旧包或 GPU 部署工具不属于验证对象。

## 术语和架构边界

### Semantic Platform Core

负责 Project、Ontology、当前语义状态、Evidence、Modeling Batch、Lease、确定性校验、版本、
审计、查询、权限和持久化的核心平台能力。它不调用通用模型做建模判断，也不把 Agent Runtime
内部状态作为语义事实来源。

### First-party Modeling Agent Runtime

由平台项目官方维护和交付、但与 Semantic Platform Core 解耦的建模 Agent 运行环境。它负责模型
调用、会话、上下文、工具调度、角色协作、事件观测、暂停恢复和调试。Pi 是首个候选实现，不是
平台公开协议中不可替换的永久类型。

### Modeling Workflow Package

与具体 Runtime 尽量解耦的建模方法和能力集合，包括 Prompt、Skill、角色职责、产物 Schema、
建模规则、质量门禁和验收方法。第一方 Runtime 可以直接加载该 Package；后续也可以把它发布为
外部 Agent 可使用的 Skill、Plugin 或独立 Agent 包。

三者的目标关系为：

```text
用户
  -> First-party Modeling Agent Runtime
       -> Modeling Workflow Package
       -> Semantic Platform Core 的受支持接口
            -> 确定性校验、Evidence、Batch、持久化和查询
```

Agent 可以提出模型、问题、解释和下一步，但只有 Semantic Platform Core 的成功写入、校验、查询
和治理记录构成平台事实。第一方 Runtime 不获得绕过 R-004、R-008 或其他强制平台协议的特殊写入
通道。

## 与既有版本的关系

1. v2.0 继承 v1.0 的语义平台、建模批次、证据、查询、权限和治理合同，不重新定义这些确定性
   协议。
2. v2.0 继承 v1.1 的业务访谈、Coverage、分片建模、独立评审、质量门禁、共享产物和执行 Profile
   作为建模 Agent 能力基线，但不要求 R2.0-001 运行真实端到端建模。
3. v1.1 的 Claude Code/Codex Skill、Hook、Harness 和 Adapter 在 v2.0 正式集成完成前继续保持现有
   定位；R2.0-001 不切换默认 Runtime，也不废弃兼容路径。
4. v1.2 的消费 Agent 查询优化与 v2.0 的建模 Runtime 可以独立推进；Pi 集成不是 v1.2 查询能力的
   前置条件。
5. 是否修改 ADR 0001 的平台边界、是否正式选用 Pi、以及生产部署和发布方式，均在 R2.0-001
   验证结论之后决定。

## v2.0 总需求

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.0-001 | Pi 建模 Agent Runtime 能力验证 | P0 | 已验证，PASS | v1.1 R1.1-002 至 R1.1-007 |
| R2.0-002 | Pi 第一方建模 Agent Runtime 正式集成 | P0 | 待细化；仅在 R2.0-001 PASS 后启动 | R2.0-001 |

R2.0-002 当前只表示已确认的后续方向，不在本文中预先冻结生产架构、平台接口、部署方式、迁移范围
或真实建模验收合同。R2.0-001 的结论、限制和改造清单是 R2.0-002 细化的输入；若 R2.0-001 FAIL，
则不得以 R2.0-002 名义继续默认集成 Pi，应重新选型或先解决明确阻塞项。

## R2.0-001 Pi 建模 Agent Runtime 能力验证

当前状态：`已验证，PASS`

优先级：`P0`

### 需求定位

本需求是 Pi 的轻量可行性验证和 v2.0 后续建模 Agent 实验的前置门禁。它只回答：

> Pi 的原生能力和公开 SDK/Extension 扩展机制，是否足以搭建平台建模 Agent，并让开发者监看
> 建模流程、取得阶段 Summary，从而在后续需求中迭代建模效果？

本需求采用最简单的 repo-local、可删除原型和宽松探针，只需提供足以说明能力存在的可复核证据。
它不追求生产级严谨性，不交付正式集成，不运行真实业务资料建模，也不证明 Pi 已经提升建模质量。
真实建模、流程调优和质量对照由 R2.0 后续需求承接。

候选 upstream 固定为 `https://github.com/earendil-works/pi`，核心验证包为
`@earendil-works/pi-coding-agent`；选择具体 commit 时以公开可取得、可锁定依赖和可重复运行为准，
不得在验证过程中无记录地跟随 `main` 漂移。

### 当前现状

当前建模 Agent 主要运行在 Claude Code、Codex 等外部 Runtime 中。仓库通过 Skill、项目级 Agent
定义、Hook、Harness、共享建模目录和本地 Adapter 建立工作流，但平台不能稳定控制这些 Runtime
的会话、工具、事件和调试能力。

Pi 提供轻量 Agent Runtime、SDK 和 Extension 机制，但当前没有一个 repo-local 原型证明它能够
装配建模 Prompt/Skill、运行隔离角色、调用结构化工具、完成显式交接与用户澄清，并把关键流程
事件和阶段 Summary 暴露给外部监看者。

### 目标行为

建立一份精简、可复核的 Pi 建模 Agent 能力矩阵和最小原型。每项当前最小能力说明：

- 该能力为什么是当前或后续建模 Agent 的必需能力；
- Pi 的对应原生能力、公开 SDK、Extension 事件或其他公开扩展点；
- 使用的 Pi 仓库、版本或 commit、软件包和官方资料位置；
- 文档核验结论和一个足以说明能力存在的最小探针；
- 能力分类、证据、已知限制和后续预计改造面；
- 是否会把 Pi 专属概念泄漏进 Semantic Platform Core 或公开平台协议；
- 最终 PASS、FAIL 或 BLOCKED 结论。

001 的完成标准是“可以开始后续建模 Agent 与建模效果实验”，不是“已经满足生产 Runtime 的
安全、可靠性、治理和部署要求”。

### 能力分类

每项能力使用以下固定分类：

| 分类 | 含义 | 对 R2.0-001 的影响 |
| --- | --- | --- |
| `native` | Pi 原生公开能力可以直接满足需求 | 可以通过 |
| `extension_feasible` | 可以只使用公开 SDK/Extension/稳定协议实现，不修改 Pi 核心 | 可以通过，但必须记录改造面和风险 |
| `fork_required` | 必须修改、patch 或长期维护 Pi 核心/私有接口 | 必需能力出现时不得 PASS |
| `unsupported` | 当前无法满足，或没有足够证据证明可实现 | 必需能力出现时不得 PASS |

不能把“理论上可以重写一个 Agent”归为 `extension_feasible`。该分类必须指出具体公开扩展点，
并用最小证据说明可行。依赖未合并分支、未发布私有 API、运行时 monkey patch 或不可维护的源码
复制，均按 `fork_required` 处理。

`extension_feasible` 还必须符合薄扩展边界：可以新增平台自有 Adapter、Extension 和 Workflow
Package，并组合 Pi 的公开 SDK、事件、Session 与工具接口；但如果必须在外层重新实现 Agent loop、
Session 存储、事件模型、工具调度等 Pi 核心子系统，即使没有直接修改 Pi 源码，也不能判为
`extension_feasible`，应根据缺口判为 `fork_required` 或 `unsupported`。

### 当前最小能力合同

以下能力直接决定能否用 Pi 搭建可调优的建模 Agent，因此属于 R2.0-001 的 PASS 门槛。

#### 1. Runtime 嵌入和生命周期控制

- 能够通过公开 SDK 或稳定 RPC/进程协议创建、运行和释放 Agent Session；
- 能够程序化提交 Prompt、等待完成，并取得可关联的 Session/Run 标识；
- Pi 版本可以固定和重复安装，验证代码不依赖用户全局未固定配置。

#### 2. 模型与 Provider 抽象

- 可以显式选择一个可用模型与 Provider，并完成一次真实模型调用 smoke；
- Modeling Workflow Package 不绑定唯一模型供应商；
- 不比较多个 Provider、模型质量、token 成本或推理档位效果。

#### 3. Prompt、Skill 和上下文装配

- 可以设置或扩展系统提示词，加载项目上下文和运行时无关的建模 Skill；
- 可以按角色装配不同 Prompt、Skill、工具和有界上下文；
- 可以注入稳定产物定位符，不要求依赖完整聊天历史传递大载荷。

#### 4. 自定义工具和结构化产物

- 可以注册带输入 Schema 的自定义工具，并取得结构化结果和稳定错误；
- Agent 可以输出可进行 Schema 校验的结构化结果，或通过自定义工具提交结果；
- 较大结果可以写入 repo-local 受控路径并返回定位符和简短摘要；
- 001 使用 fake/local tool 证明调用、结构化结果和错误链路，不连接真实平台写接口。

#### 5. 多角色、显式交接和用户澄清

- 可以创建至少两个具有不同角色上下文的隔离 Session；
- 角色间通过显式输入、稳定产物或结构化结果交接，不依赖共享隐藏对话；
- 主 Agent 可以提出结构化问题，外部协调器能够识别暂停、提交回答并继续原 Session；
- 上述能力可以由 Pi 原生能力或薄 Extension/Adapter 提供，不要求 Pi 内置 subagent 产品概念。

#### 6. 流程监看和阶段 Summary

- 外部监看者至少能够关联角色、Session、流程阶段、模型调用状态、工具调用及结果状态、提问、
  暂停、继续、最终产物位置和失败原因；
- 监看能力可以由 SDK 事件、Extension 事件或简单 Adapter 组合提供，不要求生产监控系统或 UI；
- 选择一个代表性阶段，在阶段结束时根据该阶段可见事件生成一份结构化 Summary；
- Summary 至少包含阶段、角色、步骤目标、简明动作、输入/输出或产物引用、可见问题与决定、结果、
  未解决项和下一步；不要求逐步骤持续生成，也不要求保存隐藏推理或完整 transcript；
- Summary 使用同一 Session、临时 Session 或扩展工具均可，由最小实现决定。

### 验证方式

验证采用“少量官方资料核验 + 一个可重复运行的最小场景”，不建设生产功能，也不追求精确性能或
完备边界测试：

1. 固定 Pi upstream、版本或 commit，并保存依赖锁；
2. 用一个合成建模任务串联 Prompt/Skill、两个角色 Session、显式交接、自定义工具、结构化产物、
   用户澄清和流程事件；
3. 至少完成一次真实模型调用；其余平台能力使用 fake/local tool，不调用真实 Modeling Batch；
4. 监看输出至少显示角色/Session、阶段、模型与工具调用状态、提问/暂停/继续、产物或错误；
5. 在一个代表性阶段结束时，根据该阶段可见事件生成一份符合最小字段合同的 Summary；
6. 记录实际命令、固定版本、运行结果和已知限制，使另一开发者可以按说明重复运行；
7. 汇总后给出唯一版本级结论：`PASS`、`FAIL` 或 `BLOCKED`。

探针只证明 Pi 可以承载后续建模 Agent 和流程调优实验，不以合成任务的模型回答质量作为 PASS
依据，也不把探针冒充为已完成平台集成。

### 验证产物

R2.0-001 至少交付：

- 精简 Pi 能力矩阵，覆盖六类当前最小能力和四级分类；
- repo-local 最小验证原型、依赖锁和可重复运行说明；
- 一份共享测试计划，保留每轮失败、修复或阻塞证据；
- 能力验证报告，包含 Pi 版本、官方资料、探针结果、限制和后续最小改造面；
- 后续需求输入清单：真实建模 Agent、流程优化与质量实验需要新增、改造或复用的组件；
- 是否启动 R2.0-002 的明确结论。

### PASS、FAIL 与 BLOCKED

#### PASS

只有同时满足以下条件才能 PASS：

- 六类当前最小能力均为 `native` 或 `extension_feasible`；
- 所有 `extension_feasible` 项都指向公开扩展点，并有足以排除核心 fork 的证据；
- 最小场景已通过真实 Pi 运行，证明建模 Agent 装配、显式交接、用户澄清、流程监看和一个阶段
  Summary 可以成立；
- 验证代码和结果可以按固定版本与说明重复；
- 已形成后续真实建模与流程调优的最小改造面，且不要求改变 Semantic Platform Core 的确定性
  权威边界。

#### FAIL

出现以下任一情况必须 FAIL：

- 任一当前最小能力为 `fork_required` 或 `unsupported`；
- 只能通过 Pi 私有 API、长期核心 patch 或复制其内部实现完成关键能力；
- 无法建立至少两个隔离角色、显式交接或 SDK/RPC 用户澄清链路；
- 无法取得最小流程事件或在阶段结束时生成 Summary，且公开扩展机制不能补足；
- 探针结果与文档声明冲突，并且没有可接受的公开替代路径。

FAIL 后应记录重新选型、缩小目标或先解决阻塞项的建议，不得直接启动默认 Pi 集成。

#### BLOCKED

只有在外部条件使关键探针无法执行、且现有证据不足以判定 PASS/FAIL 时使用 BLOCKED，例如固定
版本无法取得、必要模型服务不可用或官方接口状态不明确。BLOCKED 不是暂时视为 PASS；解除阻塞后
必须继续同一需求的验证和测试记录。

### 明确不在范围

- 不正式集成 Pi 到 backend、frontend、systemd 服务或生产部署；
- 不切换现有 Claude Code/Codex 建模入口或默认 Runtime；
- 不使用真实业务资料完成端到端本体建模和质量验收；
- 不接入真实 Build Session、Lease、Modeling Batch dry-run/apply、Evidence 或 lineage 写路径；
- 不迁移、删除或重写 v1.1 的 Harness、Hook、Adapter、Profile、共享目录和 Agent 定义；
- 不验证凭证隔离、危险工具控制、project trust、sandbox、权限系统或其他生产安全能力；
- 不验证崩溃恢复、完整 Session 持久化、压缩/分支/重试语义或分布式协调；
- 不建立生产级多 Agent 调度、远程执行、监控服务、审计存储或管理 UI；
- 不要求完整 Prompt、token/成本、精确耗时、重试链或逐步骤 Summary；
- 不比较 Pi 与 Claude Code/Codex 的模型回答质量、token 成本或任务速度；
- 不完成生产分发、升级兼容、许可证再发布和运维方案论证；
- 不 fork Pi 核心来让验证“通过”；
- 不在验证通过前把 Pi 类型、Session 或事件结构写入平台公开 API 和持久化 Schema；
- 不在本需求中最终修改 ADR 0001；正式边界调整由 R2.0-002 细化时基于验证结论处理。

以上事项属于未来产品化候选范围。只有后续真实建模或流程优化证明某项能力直接影响建模效果、
实验可复现性或立即应用模型的正确性时，才应提前进入后续需求的完成门槛。

### 验收标准

- 能力矩阵完整覆盖六类当前最小能力，每项包含分类、官方证据或探针证据、限制和后续改造；
- 四级分类规则被一致应用，没有把“可以重写核心”记录为 `extension_feasible`；
- 最小原型能够在固定 Pi 版本下运行一个合成场景，完成真实模型调用、Prompt/Skill 装配、自定义
  工具、结构化产物、两个隔离角色的显式交接，以及 SDK/RPC 提问、暂停、回答和继续；
- 验证过程不调用真实平台写接口，不产生平台业务数据，不要求 backend/frontend 代码或服务变更；
- 监看输出能够关联角色/Session、流程阶段、模型和工具调用状态、问题、暂停/继续、产物或错误；
- 一个代表性阶段结束时能够生成包含阶段、角色、目标、动作、输入输出、问题与决定、结果、未解决
  项和下一步的 Summary；
- 多角色、结构化产物、用户澄清和监看能力存在公开、可维护的实现路径，但原型不冒充已完成真实
  建模工作流或生产 Runtime；
- 验证报告给出唯一 `PASS`、`FAIL` 或 `BLOCKED` 结论，并逐项说明判定依据；
- 只有 PASS 才建议进入 R2.0-002；FAIL 或 BLOCKED 时，需求状态和后续路线与证据一致；
- 原型不提交真实密钥或外部服务凭证。

## 后续需求细化规则

R2.0-001 PASS 后再细化 R2.0-002。R2.0-002 至少需要基于能力矩阵重新确认：

- Pi 采用 SDK 嵌入、RPC 子进程还是独立服务；
- 第一方 Extension、Runtime Adapter 和 Modeling Workflow Package 的模块边界；
- Local/Formal Profile、现有 Harness/Hook/Adapter 的复用、替代和兼容策略；
- 如何运行真实资料建模、比较现有流程并持续优化建模效果；
- 哪些监看事件和阶段 Summary 最能解释遗漏、返工和质量瓶颈；
- 主 Agent、建模角色、评审角色和用户澄清的实际工作流；
- 只有在真实实验需要时才加入恢复、安全、平台事件映射、分发和运维能力。

这些内容是后续设计输入，不因写入本节而成为 R2.0-001 的实现或完成条件。
