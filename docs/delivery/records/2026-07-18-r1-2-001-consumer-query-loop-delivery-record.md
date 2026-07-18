# R1.2-001 消费 Agent 查询闭环与绕行消除 Delivery Record

- Requirement source: `docs/requirements/requirements-v1.2.md` R1.2-001
- Status: in-progress
- Started: 2026-07-18T00:00:00+08:00
- Last updated: 2026-07-18T17:47:59+08:00
- Design: pending post-refinement design
- Shared test plan: pending post-refinement test planning
- Delivery baseline: clean worktree at `4710725 Update GitNexus index metadata`
- Delivery commit: pending

## Confirmed contract

- Current behavior: 受支持的 REST/MCP 已提供 Context Query、固定语义读模型和 scoped SPARQL，但消费
  Agent 仍须知道内部 ID、英文标签、IRI、支持的读模型名称和派生图结构；在 Dify 合成参考本体验收中，
  为完成两个问题曾绕过公开接口读取内部服务/ORM。
- Target behavior: 消费 Agent 仅以已认证且授权的 REST/MCP，从业务范围与自然语言问题出发，建立可发现、
  可解释、可继续精确查询的消费闭环；平台准确区分知识缺失、未命中、过滤/截断、派生未物化和范围不足。
- In scope: R1.2-001 的闭环合同、两条参考问题的公开路径、范围/版本/匹配/事实来源说明、机器可读诊断，
  以及 REST/MCP 核心语义与错误状态一致性。
- Non-goals: 不调用通用 LLM 生成最终自然语言答案；不让平台替外部 Agent 规划或回答；不读取平台数据库、
  ORM、内部服务或源码；不引入 Dify、客服、发票或合同专用分支；不自动把后续 R1.2 子需求全部视为已实现。
- Acceptance summary: 两个参考问题可完全经公开 REST/MCP 回答，且每个答案可说明实际范围、语义版本、
  主要匹配、关联事实和断言来源；各诊断状态可区分并提供后续入口；同身份/范围/请求下 REST 与 MCP
  的核心语义和错误状态一致。
- Refinement: 用户已确认 R1.2-001 是 v1.2 的查询闭环与共同验收合同；自身不新增万能查询、消费
  编排或自动回答接口，由 R1.2-002 至 R1.2-007 提供具体能力，并以公开 REST/MCP 全链路验收收口。
  没有显式范围或已配置的会话默认范围时，平台返回 `scope_required` 和当前身份的授权 Project
  候选及后续发现入口，不扫描全部范围、不因候选唯一而静默选中。
  R1.2-001 的 P0 完成要求 R1.2-002 至 R1.2-006 全部通过闭环验收，并要求闭环涉及的接口具备
  明确截断、稳定续读、能力发现及 REST/MCP 一致性；不等待 R1.2-007 对全部平台接口完成 P1 泛化。
  不新增跨接口统一诊断对象；各公开能力保留简单、领域相关的状态结构，并逐接口保证 REST/MCP
  核心状态一致。R1.2-001 不规定公共响应字段或统一字段名，只验收各状态能够被对应公开接口准确
  区分；只有确实可继续查询时才要求该接口提供必要续读参数。
  闭环只查询当前语义状态并返回实际语义版本/revision；lineage 可用于追溯来源和历史变化，但
  调用方选择历史或不可变发布版本查询不在范围内。查询期间版本变化不得伪装成单一一致结果。
  REST/MCP 只要求核心事实、排序、版本、领域状态、权限和范围语义一致，不要求 HTTP 与工具
  传输包装逐字段相同；传输相关续读形式可不同，但续读结果必须一致。
  最终 PASS 以确定性的结构化事实断言和公开接口调用轨迹为准，不评价外部 Agent 的自然语言
  文案质量；真实 Agent 演示只作为易用性证据。

## Timeline

### 2026-07-18T00:00:00+08:00 — source and current-state audit — main agent

- Context: 用户指定 `requirement-delivery`，要求细化 v1.2 的第一个需求。
- Action/decision: 确认首项为 P0、未实现的 R1.2-001；已读取仓库指南、需求源、交付技能与既有
  R1.1-002 交付记录。工作区干净，未发现 R1.2-001 的既有设计、测试计划或交付记录。
- Evidence: `AGENTS.md`; `docs/requirements/requirements-v1.2.md`; `git status --short`; `git log -1`;
  `docs/delivery/records/2026-07-17-r1-1-002-staged-modeling-workflow-delivery-record.md`.
- Outcome/next step: 先以一问一答收敛会影响闭环边界的功能合同；合同确认前不写产品设计或代码。

### 2026-07-18T15:08:17+08:00 — refinement paused — user and main agent

- Context: 用户要求先暂停 R1.2-001 的需求细化，转而整理整个 `docs/` 文档结构。
- Action/decision: 保留已建立的交付记录和未确认的范围问题，不继续设计、探针或实现；本记录随文档
  重构移入 `docs/delivery/records/`。
- Evidence: 当前会话用户指令；`docs/README.md`。
- Outcome/next step: 在用户明确恢复 R1.2-001 细化后，从尚未回答的范围定位问题继续。

### 2026-07-18T15:27:39+08:00 — refinement resumed and current-state audit — user and main agent

- Context: 用户明确恢复 R1.2-001 细化。当前 HEAD 为 `6842b7e Reorganize documentation structure`；
  工作树已有 `AGENTS.md`、`CLAUDE.md` 修改，均视为本需求之外的用户基线改动。
- Action/decision: 重新核对 v1.2 需求原文、v1.0 R-005/R-006/R-008 以及真实 REST/MCP 查询路径。
  当前 Context Query 的 REST/MCP 已共享 `SemanticContextQueryService`，但仅有 `matched/no_match`
  主状态；固定读模型和规则摘要仍是另一条公开路径，Project/Ontology 发现、跨语言候选、任务聚合、
  规则正文/触发解释、有效分类及稳定续读分别留给 R1.2-002 至 R1.2-007。
- Evidence: `docs/requirements/requirements-v1.2.md`; `docs/requirements/requirements-v1.0.md` R-005、
  R-006、R-008；`backend/app/services/semantic_context_query.py`；`backend/app/api/semantic.py`；
  `backend/app/api/modeling_batches.py`；`backend/app/mcp/tools/semantic.py`；刷新后的 GitNexus 查询图。
- Outcome/next step: 先确认 R1.2-001 是版本级闭环/共同验收合同，还是自身还需新增消费编排接口；
  该选择会直接改变后续设计、接口数量和子需求边界。

### 2026-07-18T15:46:29+08:00 — functional refinement decision 1 — user and main agent

- Context: R1.2-001 与后续具体需求的职责边界需要确认。
- Action/decision: 用户确认 R1.2-001 只定义从授权业务范围和自然语言问题到可核查答案事实的完整
  公开查询路径、共享诊断语义与版本级验收门槛；不新增万能查询、消费编排或自然语言回答接口。
- Evidence: 当前会话用户确认“同意”；`docs/requirements/requirements-v1.2.md` 实施顺序建议。
- Outcome/next step: 继续确认调用方未提供 Project/Ontology 范围时的平台行为。

### 2026-07-18T17:00:25+08:00 — functional refinement decision 2 — user and main agent

- Context: 消费 Agent 未提供 Project/Ontology 且没有显式配置会话默认范围时，需要确定失败关闭与
  发现体验的边界。
- Action/decision: 用户确认平台不得扫描全部可访问 Project，也不得因候选唯一而静默选中；应返回
  `scope_required`、当前身份可访问的 Project 候选和继续发现 Ontology 的入口。显式配置的会话默认
  Project/Ontology 属于合法、可验证范围。
- Evidence: 当前会话用户确认“同意”；`docs/requirements/requirements-v1.2.md` R1.2-001、R1.2-002。
- Outcome/next step: 确认 R1.2-001 的 P0 完成门槛是否等待 R1.2-007 的全部 P1 泛化能力。

### 2026-07-18T17:05:07+08:00 — functional refinement decision 3 — user and main agent

- Context: R1.2-001 是 P0，而 R1.2-007 是覆盖面更广的 P1；需要避免 P0 闭环被无关接口的分页
  泛化阻塞，同时不能允许闭环以不可继续读取的截断结果通过。
- Action/decision: 用户确认 R1.2-002 至 R1.2-006 全部完成是 R1.2-001 的必要条件；R1.2-001
  不等待 R1.2-007 全量完成，但闭环实际使用的接口必须明确截断、提供稳定续读、可发现参数/字段/
  限制，并保持 REST/MCP 状态一致。
- Evidence: 当前会话用户确认“同意”；`docs/requirements/requirements-v1.2.md` 版本级验收及实施顺序。
- Outcome/next step: 确认跨不同查询接口的机器可读诊断采用何种兼容性策略。

### 2026-07-18T17:16:50+08:00 — functional refinement decision 4 — user and main agent

- Context: 曾建议在各领域状态之外增加统一诊断结构，以统一表达完整性、原因和继续入口。
- Action/decision: 用户拒绝该方案，原因是会让返回结构持续膨胀。R1.2-001 不建立跨接口统一诊断
  对象；各接口只表达自身必要的机器可读状态，REST/MCP 一致性按同一能力逐接口保证。
- Evidence: 当前会话用户反馈“返回的结构越来越复杂”。
- Outcome/next step: 确认最小状态合同是否只保留单一领域状态和必要的续读参数。

### 2026-07-18T17:39:29+08:00 — functional refinement decision 5 — user and main agent

- Context: 在拒绝统一诊断对象后，需要确认 R1.2-001 是否仍规定跨接口公共字段。
- Action/decision: 用户确认 R1.2-001 保持纯验收层级，不设计公共响应结构、不规定统一字段名。
  知识不存在、未命中、歧义、截断、推导过期或未物化由对应子需求和接口以最小必要结构区分；
  仅在确实可继续查询时提供续读参数，正常成功响应不增加诊断层级。
- Evidence: 当前会话用户确认“同意”。
- Outcome/next step: 确认闭环只查询当前语义状态，还是把历史/不可变版本选择纳入范围。

### 2026-07-18T17:43:37+08:00 — functional refinement decision 6 — user and main agent

- Context: v1.0 R-006 当前只查询当前语义状态，而不可变发布版本选择仍属于 R-105。
- Action/decision: 用户确认 R1.2-001 只验收当前语义状态；每次结果应返回实际语义版本或 revision，
  lineage 可追溯当前事实的来源和历史变化，但不提供历史/不可变版本选择。查询期间语义版本变化时，
  平台必须要求重新读取或明确标记变化，不能拼成看似一致的单次结果。
- Evidence: 当前会话用户确认“同意”；`docs/requirements/requirements-v1.0.md` R-006、R-105。
- Outcome/next step: 确认 REST/MCP 一致性要求是语义一致还是传输结构逐字段完全相同。

### 2026-07-18T17:45:14+08:00 — functional refinement decision 7 — user and main agent

- Context: REST 使用 HTTP 状态/响应模型，MCP 使用工具返回/错误格式，若要求逐字段相同会把传输
  差异错误提升为产品合同。
- Action/decision: 用户确认按核心语义一致验收，而非传输格式完全相同。同身份、范围和业务参数下，
  核心事实、排序、语义版本、领域状态、权限与范围判断必须一致；HTTP/MCP 包装及分页链接形式可异，
  但继续读取后的结果必须一致。
- Evidence: 当前会话用户确认“同意”。
- Outcome/next step: 确认版本级验收评价平台结构化事实闭环，还是同时评价外部 Agent 的自然语言文案。

### 2026-07-18T17:47:59+08:00 — functional refinement decision 8 and contract freeze — user and main agent

- Context: 平台负责结构化语义上下文，外部 Agent 负责最终回答；若以 LLM 文案判定 PASS，会让验收
  随模型和表达波动，且越过平台责任边界。
- Action/decision: 用户确认最终 PASS 只评价公开 REST/MCP 是否返回完整、可核查的结构化事实，以及
  调用轨迹是否全程没有内部绕行；不评价自然语言文案质量。真实消费 Agent 演示可作为易用性证据，
  但不能替代固定事实断言。至此角色、范围、失败行为、版本、一致性和验收边界已确认，并写回需求源。
- Evidence: 当前会话用户确认“同意”；`docs/requirements/requirements-v1.2.md` R1.2-001。
- Outcome/next step: 功能合同已冻结；后续如继续交付，先做最高风险探针，再编写设计与共享测试计划。

## Review disposition

| Round | Finding | Main-agent disposition | Evidence | Plan impact |
| --- | --- | --- | --- | --- |
| — | pending | — | — | — |

## Development and defect history

| Cycle | Stable state | Change or defect | Verification | Outcome |
| --- | --- | --- | --- | --- |
| — | — | pending | — | — |

## Independent test rounds

| Round | Stable state | Result | Defects/unexecuted cases | Evidence |
| --- | --- | --- | --- | --- |
| — | — | pending | — | — |

## Final verification

- Required checks: pending reviewed test plan.
- Runtime/restart health: not run; no code changed.
- Documentation/status sync: pending delivery.
- Cleanup: no test data created.
- Residual risks and follow-ups: functional contract frozen; risk probes and design are pending.

## Retrospective

- Scope or design deviations: pending.
- Rework and root causes: pending.
- What shortened or delayed delivery: pending.
- Reusable lessons: pending.
