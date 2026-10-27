# v5 Agent 执行层横向比较

日期：2026-10-27。状态：**官方资料与本地源码比较完成，尚未执行五方案的同条件运行对照；没有成本、质量或最终选型 PASS。**

用户已确认 LangGraph 编排选型，要求比较 Codex、DSH、OpenAI SDK、Deep Agents、`create_agent`，并指出 DSH 的轻量核心与定制空间值得期待，`create_agent` 可能留下较多优化工作；随后补充 DSH 的早期版本风险，要求重点评估 SDK 方案。本记录承接 [R5.0-001](../requirements/requirements-v5.0.md#r5-0-001) 和[编排选型记录](2026-10-27-v5-modeling-team-orchestration-options.md)。这里的 OpenAI SDK 指 **OpenAI Agents SDK**，不是普通 `openai` API 客户端、Codex SDK 或托管 Agents API。

## 1. 当前判断

**综合版本风险与 Python 接入结构，建议优先验证 OpenAI Agents SDK，以 Deep Agents 作为主要对照；Codex 保留现有基线，DSH 保留定制备选，`create_agent` 作为按需组装的基线。** 初始 DSH 优先建议据补充评估调整；Agent 执行层尚未选定。关键条件是当前 GLM 路由能承接所需上下文与控制能力，详见 [SDK 构建方案评估](2026-10-27-v5-openai-agents-sdk-assessment.md)。

DSH 的优势有源码依据：运行核心、模型适配、工具、上下文处理和持久化可以按插件组合；不必先写完整 Agent 循环才获得定制能力。Deep Agents 的竞争力则在于已组合好的上下文与委派能力，以及与 Python／LangGraph 的直接衔接。两者值得比较“完成同一业务工作实际还要维护多少代码”，不能用核心大小直接推导成本或质量。

此前直接推荐 `create_agent` 过早。它已有可复用中间件，优化并非全部重写；但选择、组合、参数调整与交互验证仍由我们承担。也不能因 Codex／DSH 拥有内部会话就排除它们：外层业务流程和内层模型／工具循环职责清楚时，两层状态是合理分工。

## 2. 同一尺度下比较五种方案

“已有”表示官方提供能力，不表示所有模型兼容、默认启用或已经在 OntoWeave 验证。下表的接入代价是基于接口与源码的判断，尚无工时／性能实测。

| 方案 | 已有能力 | 需要选择、定制或补齐的部分 | v5 适配判断 |
| --- | --- | --- | --- |
| **Codex，通过官方 SDK／app-server** | 完整运行时；工具执行、会话接续、流式事件、Skills、压缩；公开 turn 启动、steer、interrupt 控制。Python SDK 已提供稳定发布并绑定运行时版本。 | 收窄实际工具与输入；映射事件、用量及控制结果；深改循环与上下文策略受公开扩展面约束。不能整体沿用旧适配器。 | **现有基线，仍可竞争。** 重新用官方接口评估薄接入层，不把旧适配器的历史职责当作 Codex 的必然代价。[SDK](https://learn.chatgpt.com/docs/codex-sdk)、[app-server](https://learn.chatgpt.com/docs/app-server) |
| **DSH，通过 SDK＋profile／插件** | 可组合运行核心；自动压缩、会话日志与恢复、工具管线；完整 profile 可组合 Skills、子 Agent、结果外置等能力。 | 选择最小插件集合；当前公开 SDK 缺少单会话 cancel／pause；模型路由、调用准入和完整用量接入需验证。上游仍为开发预览。 | **定制备选。** 可插拔有价值，版本跟随与控制接入成本需要纳入比较。[架构][dsh-architecture]、[Python SDK][dsh-sdk]、[发布状态][dsh-readme] |
| **OpenAI Agents SDK** | 工具循环、handoff、会话与可恢复运行状态；当前 `SandboxAgent` 默认提供文件、shell、compaction，并可加 Skills／Memory。 | 选择普通 Agent 或 SandboxAgent；接入工作目录、工具与存储；核对非 OpenAI 路由及所选高级能力，不能只验证普通文本调用。 | **优先验证建议。** Python 接入可减少独立运行时桥接；GLM 的原生压缩等能力尚未证实。[运行](https://developers.openai.com/api/docs/guides/agents/running-agents)、[SandboxAgent](https://developers.openai.com/api/docs/guides/agents/sandboxes) |
| **Deep Agents** | 基于 LangChain／LangGraph 的预组装 Agent；历史摘要、大结果外置、文件工具和独立上下文子 Agent；可配置 Skills、Memory，任务规划可选。 | 选择 backend 和持久化；裁剪工具及默认指令；接入业务状态、预算和中断合同；核对内外层图的运行身份。 | **主要对照。** 有望少写通用 Agent 工程，Python 接入直接；默认能力是否适合建模须实测。[概览](https://docs.langchain.com/oss/python/deepagents/overview)、[定制](https://docs.langchain.com/oss/python/deepagents/customization) |
| **LangChain `create_agent`** | 已有模型／工具循环、结构化输出和 LangGraph 运行基础；可用官方摘要、工具错误处理、重试、调用上限、文件和子 Agent 等中间件。 | 自己确定中间件集合、顺序、阈值、模型和错误政策，并验证组合效果。 | **按需组装基线。** 简单有界工作可能最省事；若多数工作都要长上下文、文件和委派，应先比较现成 harness。[Agent](https://docs.langchain.com/oss/python/langchain/agents)、[中间件](https://docs.langchain.com/oss/python/langchain/middleware/built-in) |

五者都不能自动提供 OntoWeave 的业务工作空间、授权账本、应用对账或独立语义验收。这些是本项目已有／新增的业务责任，应共用同一合同，不在每个执行器里重复实现。

## 3. DSH：值得期待的部分与实际缺口

### 3.1 “轻量”首先成立于职责与组合

本地核对 `/home/yangxiang/deepseek-harness` 的固定提交 `687f282e8625c6b8d11ff58211a90524be2e4317`，版本 `0.2.1-rc.2`；与本项目 [dsh_build.py](../../modeling_team/runtimes/dsh_build.py) 的 pin 一致。下列 DSH 来源均固定到该提交。

核心把 session、system prompt、tools、agent、agent loop、scope、LLM 等责任分开；扩展通过 Cordis 服务与事件挂接。自动压缩既有现成后端，也有替换接口。这支持“定制有明确位置”的判断，不证明安装包、启动时间、内存或总 token 更少。[架构][dsh-architecture]、[压缩合同][dsh-compaction]。

`sdk-minimal` 是独立的显式组合，不继承完整 `dsh-base`；提供 shell、图像读取、工作目录、JSONL 和自动压缩，省去完整 profile 的 Skills、子 Agent、文本文件工具等组件。它不是已经适合建模的最终配置；应按真实任务加减工具。Python SDK 安装同版本运行时包，因此精简插件组合也不等于精简分发包。[最小 profile][dsh-minimal]、[SDK][dsh-sdk]。

### 3.2 优化能力已有，但仍需要合理配置

| 能力 | 已有实现与本项目要做的事 |
| --- | --- |
| 长上下文 | 自动压缩可保留近期内容并总结较早历史，原日志仍在。压缩本身会调用模型，必须计费；系统提示、工具定义或一个巨大工具单元仍可能造成压力。不能只记录压缩后 token。[压缩后端][dsh-compaction-basic] |
| 工具结果外置与裁剪 | 可组合 spill／pruner 等插件；需要保证外置结果能按授权再次读取，且重要条件／例外没有只留在不可达内容中。[默认组合][dsh-base] |
| Skills 与子 Agent | 完整组合已有相关插件；选择性装载可以避免重写通用能力。内部委派不自动具有独立业务单元的预算、长期等待与验收隔离。[默认组合][dsh-base] |
| 会话恢复 | SDK `resume_session` 读取原持久历史，不偷偷换新 session；不恢复原 shell／浏览器等外部进程。恢复会话与确认平台应用结果仍是两件事。[SDK][dsh-sdk] |

### 3.3 两个会影响新接入方式的事实

**采用受支持的启动路径。** 当前上游要求应用通过命名 profile 启动；Python SDK 运行正常 `dsh` CLI，通过 profile 与有序 patches 定制。本项目旧 [entry.mjs](../../modeling_team/runtimes/dsh_node/entry.mjs) 直接建立 Cordis Context 并挂载插件。新 v5 接入应优先验证 SDK／profile，而不是照搬旧入口；本轮未修改或宣称旧路径运行失败。[上游启动合同][dsh-architecture]。

**公开控制接口有缺口。** 固定版本的 `HarnessSdkRequestMap` 提供 initialize、prompt、resume、wait、工作目录和 shutdown，没有单会话取消／暂停请求。内核存在取消机制，不等于 Python 调用侧已有对应公共 API。旧 [dsh.py](../../modeling_team/runtimes/dsh.py) 的 pause 使用 `SIGSTOP`，只暂停本地进程，不能证明远端模型已取消或停止计费。因此需要验证能否用一个小的受支持插件／桥接补齐调用准入、取消与结果结算，不能默认已有。[SDK 协议源码][dsh-protocol]。

以上并不否定 DSH。它们恰好给出了有界验证目标：**保留其现成 Agent 能力后，业务工具、预算控制和运行观察能否以少量、清楚的代码接入。**

## 4. `create_agent` 与 Deep Agents 的取舍

`create_agent` 已是可用的 Agent 循环，而非裸 LangGraph 节点。官方中间件覆盖摘要、工具／模型重试、错误反馈、调用限制、人工输入、文件与子 Agent 等常见能力。因此，“所有优化都要自己实现”不准确；更准确的成本是**自己选择并维护组合政策**。[中间件目录](https://docs.langchain.com/oss/python/langchain/middleware/built-in)。

Deep Agents 在 `create_agent` 上组装通用能力，返回 `CompiledStateGraph`；可继续配置工具、backend、子 Agent 和 middleware。适合将它作为某个业务工作单元的内部执行器。默认文件／委派行为不直接等于本项目语义方法；仍需收窄输入、输出和可写范围。[定制接口](https://docs.langchain.com/oss/python/deepagents/customization)。

本项目的选择依据是工作形态：短输入、少量工具、明确结果的步骤可以直接用 `create_agent`；长期阅读、多轮工具调用、大结果和局部委派较多时，先试 Deep Agents 或 DSH 的现成组合。没有证据时不预先拆成多种执行器，更不为五个候选同时建设一套通用适配平台。

## 5. Codex 与 OpenAI Agents SDK 不应被低估

Codex 有官方程序接口，不能仅用 CLI 文本驱动的困难评价它。app-server 已区分 thread、turn、item，提供 steer、interrupt、压缩和实际事件；Python SDK 使用本地 app-server。v5 可评估只绑定工作单元、调用控制与结果的薄接入，而不搬入旧 Runner 的协调职责。[SDK](https://learn.chatgpt.com/docs/codex-sdk)、[控制接口](https://learn.chatgpt.com/docs/app-server)。

OpenAI Agents SDK 则允许应用掌握运行与存储。当前 `SandboxAgent` 已有文件、shell、compaction 的默认组合，Skills／Memory 按需加入；应与 DSH／Deep Agents 的可用组合公平比较。普通 Agent 的模型适配成功，不足以证明 SandboxAgent 的全部能力在现有 GLM／其他路由下等价，需分别验证。[SandboxAgent](https://developers.openai.com/api/docs/guides/agents/sandboxes)、[模型与 provider](https://developers.openai.com/api/docs/guides/agents/models)。

两者的运行状态都不能与外层流程各自重放同一次副作用。Agents SDK 的 history、session、服务端 conversation 等也应选择明确的会话权威，避免重复注入同一段历史。[运行与状态策略](https://developers.openai.com/api/docs/guides/agents/running-agents)。

## 6. 与 LangGraph 的共同边界

例如，安装单元等待返修单元确认共用定义时，外层 LangGraph 保存这个业务等待关系；DSH／Codex／其他执行器只保存本次语义工作的模型与工具历史。恢复后先读工作空间与实际应用结果，再继续必要推理。

| 层 | 负责什么 | 不应重复承担什么 |
| --- | --- | --- |
| LangGraph＋任务控制 | 工作单元依赖、就绪调度、业务等待、恢复入口、预算准入与用户控制协调。 | 不复制执行器内部每条聊天和每次工具循环。 |
| 所选 Agent 执行器 | 有界语义判断、模型／工具循环、局部上下文处理、执行事件与实际用量。 | 不另起一套全项目业务调度、预算或应用恢复权威。 |
| 语义工作空间与平台 | 持续业务内容、版本冲突、授权读取、应用身份与回执。 | 不依赖聊天摘要判定已应用或已验收。 |

内部子 Agent 可服务于有界工作，跨业务单元的持久依赖由外层承接；不强制新增角色。模型重试、工具重试和流程重执行也要明确各自负责的失败层，避免重试相乘。任何已开始的模型调用都需结算，框架暂停不等于远端零费用。

## 7. 下一步应如何验证

本轮只做比较与记录，未新建收费任务、预算或生产接入。已有 [9 项 LangGraph 机制测试](../delivery/test-docs/2026-10-27-v5-langgraph-risk-validation.md) 只支持编排机制，不作为任一候选 Agent 的成绩。

结合补充评估，建议先验证 OpenAI Agents SDK 与当前模型的一个有界执行单元，Deep Agents 为主要对照，Codex 提供现有基线；DSH 和 `create_agent` 保留同合同下的备选。先验证实际会改变选择的最小接入，不先重写整个 Team，也不把五套完整实现作为首次真实建模的前置门。

| 比较项 | 需要留下的证据 |
| --- | --- |
| 配置等价 | 固定材料、任务、工具权限、provider／模型／effort；不同默认能力单列。模型无法等价时不作纯执行器成本排名。 |
| 上下文处理 | 大工具结果、必要补读和一次压缩；检查条件、例外与来源可读性，并记录新增摘要调用。 |
| 修正与控制 | 可恢复工具错误、用户补充、暂停／停止／恢复；原任务身份与预算不变，在途调用有实际结果或明确未知。 |
| 接续与应用 | 杀进程后接续；成功效果不重复，未知效果读回。复用已有操作身份与平台能力。 |
| 完整成本 | 统计全部角色、子 Agent、压缩、重试和恢复补读；记录输入／输出、往返、墙钟与人工介入，外部 Host 单列。 |
| 质量与维护 | 同一冻结目标独立评价；演练换工具、改压缩策略、增加一种可恢复结果，观察实际涉及的模块与补丁。 |

最终选择应同时满足业务质量与控制边界，再比较全任务成本和维护工作。SDK 若能以少量公开接口适配满足现有模型、上下文和控制需求，可进入第一条业务链；若需要大量补写上下文管理，应与 Deep Agents 比较实际成本。DSH 的可定制性仍保留价值，但须计入版本跟随和控制扩展。此条件判断不是预设胜负。

## 8. 证据范围

本轮核对了当前 v5 需求、旧 Codex／DSH 适配入口、DSH 固定源码与上述官方在线文档。DSH 固定版本可回查；其他在线文档访问日期为 2026-10-27，具体候选包版本须在运行对照前锁定。本地 Codex CLI 为 `0.164.0`，未据此声称当前 SDK 所有文档能力均已本地验证。

没有执行候选 SDK 的安装、真实模型基准、生产改造或独立语义验收。修改范围仅为本比较、编排选型记录和 v5 需求中的选择状态；文档链接与 diff 检查不升级为运行 PASS。

[dsh-readme]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/README.md
[dsh-architecture]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/docs/architecture.md
[dsh-sdk]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/python/sdk/README.md
[dsh-minimal]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/bundle/sdk-minimal/README.md
[dsh-compaction]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/compaction/compaction/README.md
[dsh-compaction-basic]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/compaction/compaction-basic/README.md
[dsh-base]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/bundle/base/cordis.patch.yml
[dsh-protocol]: https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/sdk/protocol/src/types.ts
