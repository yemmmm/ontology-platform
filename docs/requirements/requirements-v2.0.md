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
| R2.0-001 | Pi 建模 Agent Runtime 能力验证 | P0 | 已细化，待实现 | v1.1 R1.1-002 至 R1.1-007 |
| R2.0-002 | Pi 第一方建模 Agent Runtime 正式集成 | P0 | 待细化；仅在 R2.0-001 PASS 后启动 | R2.0-001 |

R2.0-002 当前只表示已确认的后续方向，不在本文中预先冻结生产架构、平台接口、部署方式、迁移范围
或真实建模验收合同。R2.0-001 的结论、限制和改造清单是 R2.0-002 细化的输入；若 R2.0-001 FAIL，
则不得以 R2.0-002 名义继续默认集成 Pi，应重新选型或先解决明确阻塞项。

## R2.0-001 Pi 建模 Agent Runtime 能力验证

当前状态：`已细化，待实现`

优先级：`P0`

### 需求定位

本需求是 Pi 的可行性验证和 v2.0 选型门禁。它回答的是：

> Pi 的原生能力和公开 SDK/Extension 扩展机制，是否足以承载平台后续需要的第一方建模 Agent
> Runtime，而不需要依赖 Pi 私有接口、维护高风险核心 fork，或放弃必需的建模能力？

本需求可以创建 repo-local、可删除的 Pi 验证原型，执行文档核验和最小隔离探针，并记录明确的
改造清单。它不交付生产级 Pi 集成，不要求真实业务资料建模，也不证明使用 Pi 后的建模质量已经
提升。

### 当前现状

当前建模 Agent 主要运行在 Claude Code、Codex 等外部 Runtime 中。仓库通过 Skill、项目级 Agent
定义、Hook、Harness、共享建模目录和本地 Adapter 建立工作流，但平台不能稳定控制这些 Runtime
的会话、工具、事件和调试能力。

Pi 提供轻量 Agent Runtime、SDK 和 Extension 机制，但部分能力可能不是原生内置功能。例如多
Agent 编排、MCP、权限确认、后台运行或特定平台集成都可能需要扩展。当前尚无一份基于本项目建模
需求的系统能力矩阵，也没有证据证明这些扩展可以只使用公开、可维护的接口完成。

### 目标行为

建立一份可复核的 Pi 建模 Agent 能力矩阵。每项能力都必须说明：

- 该能力为什么是当前或后续建模 Agent 的必需能力；
- Pi 的对应原生能力、公开 SDK、Extension 事件或其他公开扩展点；
- 使用的 Pi 仓库、版本、commit、软件包、许可证和官方资料位置；
- 文档核验结论和必要的最小隔离探针；
- 能力分类、证据、已知限制、风险和后续预计改造面；
- 是否会把 Pi 专属概念泄漏进 Semantic Platform Core 或公开平台协议；
- 最终 PASS、FAIL 或 BLOCKED 结论。

### 能力分类

每项能力使用以下固定分类：

| 分类 | 含义 | 对 R2.0-001 的影响 |
| --- | --- | --- |
| `native` | Pi 原生公开能力可以直接满足需求 | 可以通过 |
| `extension_feasible` | 可以只使用公开 SDK/Extension/稳定协议实现，不修改 Pi 核心 | 可以通过，但必须记录改造面和风险 |
| `fork_required` | 必须修改、patch 或长期维护 Pi 核心/私有接口 | 必需能力出现时不得 PASS |
| `unsupported` | 当前无法满足，或没有足够证据证明可实现 | 必需能力出现时不得 PASS |

不能把“理论上可以重写一个 Agent”归为 `extension_feasible`。该分类必须能指出具体公开扩展点，
并在文档不足或行为不确定时用最小探针证明关键假设。依赖未合并分支、未发布私有 API、运行时
monkey patch 或不可维护的源码复制，均按 `fork_required` 处理。

### 必需能力清单

以下全部是 R2.0-001 的必需验证维度。001 不实现完整建模工作流，但不能因某项能力需要后续改造
就从矩阵中删除。

#### 1. Runtime 嵌入和生命周期控制

- 能够通过公开 SDK 或稳定 RPC/进程协议创建、启动、观察、停止和释放 Agent Session；
- 能够程序化提交 Prompt、等待完成、取消当前运行，并在运行中安全处理 steer/follow-up 等输入；
- 能够取得稳定 Session/Run 标识，并由平台自己的上层 Runtime Adapter 管理生命周期；
- Pi 版本可以固定和重复安装，验证代码不依赖用户全局未固定配置。

#### 2. 模型与 Provider 抽象

- 可以显式选择模型、Provider 和推理档位，并读取实际生效配置；
- 可以在不修改 Modeling Workflow Package 的情况下替换受支持模型或 Provider；
- API key/OAuth 等模型凭证可以由 Runtime 注入或受控读取，不进入 Prompt、事件摘要或建模产物；
- 001 至少进行一次真实模型调用 smoke；不要求为多个 Provider 准备真实生产凭证或比较模型质量。

#### 3. Prompt、Skill 和上下文装配

- 可以设置或扩展系统提示词，加载项目上下文和运行时无关的建模 Skill；
- 可以按角色装配不同工具、Prompt、Skill 和有界上下文；
- 可以注入稳定产物定位符而不是依赖完整聊天历史传递大载荷；
- 可以观察实际加载的上下文和资源版本，支持后续实验复现。

#### 4. 自定义工具和工具控制

- 可以注册带输入 Schema 的自定义工具，并取得结构化结果和稳定错误；
- 可以使用 allowlist/denylist 或等价机制只暴露当前角色需要的工具；
- 可以在工具执行前拦截、检查、修改或阻止调用，并在执行后观察、裁剪或规范化结果；
- 可以取消超时工具、限制大输出，并把工具调用与 Session、Turn 和 Agent 角色关联；
- 可以禁用默认 shell、文件编辑或其他高风险工具，而不影响自定义平台工具运行。

#### 5. 多角色和隔离上下文

- 可以创建主 Agent、业务整理、Work Unit 建模、独立评审和召回验收所需的隔离 Session/上下文；
- 角色间通过显式输入、稳定产物或结构化结果交接，不依赖共享隐藏对话；
- Pi 不必原生内置 subagent，但必须能通过公开 SDK/Extension 或受控子进程建立上述隔离；
- 必须能够限制子角色的工具和凭证，保证只有协调角色在后续集成中可能获得正式写入能力。

#### 6. 结构化产物与大载荷交接

- Agent 能够生成可进行 Schema 校验的结构化结果，或通过自定义工具提交结构化结果；
- 大型建模产物可以先写入受控通道，再只返回定位符、哈希和有界摘要；
- Runtime 不强迫完整产物依赖 TUI、标准输出或聊天消息返回；
- 完整性、哈希、Schema 和中断恢复所需的公开扩展点可以由后续 Adapter 使用。

#### 7. Session 持久化和恢复

- 能够选择临时或持久 Session，并重新打开、继续或派生已有 Session；
- 能够观察压缩、重试、分支或恢复相关事件，避免把 Runtime 内部摘要当作平台事实；
- Runtime 或上层 Adapter 能在进程中断后识别已完成、进行中或结果不确定的阶段；
- 001 不要求实现平台级恢复，只验证公开状态和事件足以支持后续恢复设计。

#### 8. 生命周期事件、监控和调试

- 可以观察 Session、Agent、Turn、Message、模型请求和工具执行的关键生命周期；
- 事件能够携带或关联稳定 Session、Turn、消息和工具调用标识，并保留明确顺序；
- 可以记录模型、token/usage、耗时、重试、错误、取消和工具结果状态；
- 可以在不保存隐藏推理、完整敏感 Prompt 或大载荷的前提下生成有界调试事件；
- 监控扩展失败时的行为可以被识别和测试，不能静默把断录状态报告为完整记录。

#### 9. 用户交互和暂停继续

- 主 Agent 可以提出用户可见问题并接收回答；
- 子角色需要澄清时可以暂停并把问题返回协调角色，恢复时不要求重建整个 Session；
- 交互式、无 UI、SDK 或 RPC 模式的差异必须明确，不能只在 TUI 中可用却宣称可嵌入；
- 用户取消、拒绝、修改范围或延迟回答时，Runtime 能进入可判断的状态。

#### 10. 安全、信任和扩展边界

- 能够明确 project trust、Extension 加载、工具权限和本地代码执行的安全边界；
- 必须验证第三方 Extension 是否拥有宿主完整权限，并给出只加载第一方固定扩展的后续策略；
- 凭证、Lease token、完整 Prompt、原始资料和大型候选不得默认进入日志或 Session 外部事件；
- 必须能够禁用或拦截危险工具；若隔离必须依赖容器/沙箱，应明确它属于上层部署责任；
- 不要求 001 建设生产 sandbox、secret vault 或细粒度权限系统，但缺少可行控制点时不能 PASS。

#### 11. 平台和工作流扩展条件

- 自定义工具或 Adapter 后续可以调用现有 REST/MCP/CLI，而不要求 Semantic Platform Core 感知 Pi；
- Shared Modeling Directory、Modeling Workflow Artifact、Execution Event、Profile 和质量门禁可以
  通过稳定工具/事件接口接入；
- Pi Session、消息或内部事件不能直接成为平台语义事实，也不能替代 Build Session、Modeling
  Batch、Evidence、Validation 或当前语义状态；
- 001 只需使用 fake/local tool 证明调用、事件和错误链路，不连接真实平台写接口。

#### 12. 分发、许可和可维护性

- 明确 Pi 许可证是否允许集成、修改和再发布，并保留所需声明；
- 能够固定 Pi 与第一方 Extension/Workflow Package 版本，记录升级兼容风险；
- 能够以 repo-local 依赖或隔离包运行，不强制污染用户全局 Pi 配置；
- 能够说明以后发布独立 Agent、Pi Package、Skill/Plugin 兼容入口的可行方式；
- 维护面必须主要位于平台自有 Adapter、Extension 和 Workflow Package，而不是 Pi 核心 fork。

### 验证方式

验证采用“官方资料核验 + 最小隔离探针”，不建设生产功能：

1. 固定 Pi upstream、版本或 commit，并保存依赖锁文件和许可证信息；
2. 为每个必需能力建立矩阵项，引用对应官方 API、事件或扩展点；
3. 对文档无法证明、最可能迫使重构的能力执行小型 repo-local 探针；
4. 至少真实验证一次模型调用、一次自定义工具调用、一次工具阻断、一次生命周期事件采集、一次
   Session 持久化/继续，以及两个隔离 Session 的显式产物交接；
5. 平台扩展条件使用 fake/local tool 和合成结构化产物验证，不调用真实 Modeling Batch apply；
6. 记录实际命令、版本、结果、限制、失败和清理方式，使另一开发者可以重复验证；
7. 汇总后给出唯一版本级结论：`PASS`、`FAIL` 或 `BLOCKED`。

最小探针只证明 Runtime 机制，不以模拟业务内容、Prompt 文案或模型回答质量作为 PASS 依据。

### 验证产物

R2.0-001 至少交付：

- Pi 能力矩阵，覆盖全部必需能力和四级分类；
- repo-local 最小验证原型、依赖锁和可重复运行说明；
- 一份共享测试计划，保留每轮失败、修复或阻塞证据；
- 能力验证报告，包含 Pi 版本、官方资料、探针结果、限制、安全风险和维护成本；
- R2.0-002 输入清单：正式集成需要新增、改造、复用或删除的组件；
- 是否启动 R2.0-002 的明确结论。

### PASS、FAIL 与 BLOCKED

#### PASS

只有同时满足以下条件才能 PASS：

- 全部必需能力均为 `native` 或 `extension_feasible`；
- 所有 `extension_feasible` 项都指向公开扩展点，并有足以排除核心 fork 的证据；
- 最高风险假设已经通过真实 Pi 运行探针，而不是只根据接口名称推断；
- 工具限制、事件观测、隔离 Session、恢复状态和凭证边界没有已知不可控缺口；
- 验证代码和结果可以在干净环境按固定版本重复；
- 已形成 R2.0-002 的明确改造面，且不要求改变 Semantic Platform Core 的确定性权威边界。

#### FAIL

出现以下任一情况必须 FAIL：

- 任一必需能力为 `fork_required` 或 `unsupported`；
- 只能通过 Pi 私有 API、长期核心 patch 或复制其内部实现完成关键能力；
- 无法限制高风险工具、隔离角色凭证，或无法避免秘密进入可见日志/上下文；
- 无法取得建模调试所需的关键事件，且公开扩展机制不能补足；
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
- 不建立生产级多 Agent 调度、远程执行、sandbox、secret vault、权限系统或管理 UI；
- 不比较 Pi 与 Claude Code/Codex 的模型回答质量、token 成本或任务速度；
- 不 fork Pi 核心来让验证“通过”；
- 不在验证通过前把 Pi 类型、Session 或事件结构写入平台公开 API 和持久化 Schema；
- 不在本需求中最终修改 ADR 0001；正式边界调整由 R2.0-002 细化时基于验证结论处理。

### 验收标准

- 能力矩阵完整覆盖本需求十二类能力，每项包含分类、官方证据、探针证据、限制、风险和后续改造；
- 四级分类规则被一致应用，没有把“可以重写核心”记录为 `extension_feasible`；
- 最小验证原型能够在固定 Pi 版本下重复运行，并完成规定的真实模型、工具、阻断、事件、Session
  继续和隔离交接探针；
- 验证过程不调用真实平台写接口，不产生平台业务数据，不要求 backend/frontend 代码或服务变更；
- 安全评估明确 Extension、项目 trust、工具执行和凭证边界，并证明高风险默认工具可以被禁用或
  拦截；
- 事件与调试评估证明后续能够识别运行、工具、模型、错误、中断和断录状态，或者将缺口如实判为
  `fork_required`/`unsupported`；
- Session、多角色和结构化产物评估证明后续改造存在公开、可维护的实现路径，但不把探针冒充为
  已完成建模工作流；
- 验证报告给出唯一 `PASS`、`FAIL` 或 `BLOCKED` 结论，并逐项说明判定依据；
- 只有 PASS 才建议进入 R2.0-002；FAIL 或 BLOCKED 时，需求状态和后续路线与证据一致；
- 所有原型、临时 Session 和测试凭证均有明确清理方式，仓库不提交真实密钥或外部服务凭证。

## 后续需求细化规则

R2.0-001 PASS 后再细化 R2.0-002。R2.0-002 至少需要基于能力矩阵重新确认：

- Pi 采用 SDK 嵌入、RPC 子进程还是独立服务；
- 第一方 Extension、Runtime Adapter 和 Modeling Workflow Package 的模块边界；
- Local/Formal Profile、现有 Harness/Hook/Adapter 的复用、替代和兼容策略；
- 主 Agent 与子角色的工具和凭证隔离；
- 平台事件、Runtime 观测事件和语义事实的映射边界；
- 真实端到端建模、故障恢复、安全和建模质量验收；
- 第一方 Agent、Skill、Plugin 或独立包的发布方式。

这些内容是后续设计输入，不因写入本节而成为 R2.0-001 的实现或完成条件。
