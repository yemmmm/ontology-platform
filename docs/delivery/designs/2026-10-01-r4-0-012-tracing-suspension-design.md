# R4.0-012 证据追溯能力阶段性停用详细设计

- 日期：2026-10-01。
- 状态：独立设计评审 PASS；实现及 A1—A7 独立功能验收 PASS，A8／L1 未授权、未执行，整体 PARTIAL。
- 权威需求：[v4.0 R4.0-012](../../requirements/requirements-v4.0.md#r40-012-证据追溯能力阶段性停用与多视角建模解耦)。
- 设计核对基线：`938b2c4`；实现基线：`a6d4c72`。设计阶段只读核对，后续实现与验收见第 10 节。
- 授权：用户确认 D1／D2，先授权详细设计，后授权子 Agent 开发与测试；未授权 fresh semantic start。

## 1. 目标、决策与范围

目标是让 Agent 不承担证据留存任务，合法模型无需 Evidence 和完整 lineage 即可经过
dry-run、翻译审阅、apply、受治理检索和独立语义验收。资料仍用于理解和核对业务含义。
本条不增加多视角资源类型、流程执行引擎或新的追溯体系。

| 决策 | 2026-10-01 已确认行为 |
| --- | --- |
| D1 | 专用 Evidence／lineage REST、MCP、页面及 Agent 入口对所有调用者停用，含旧 provenance 别名和 staged 补证能力 |
| D2 | 停止仅服务于完整追溯的后台采集；保留写入、授权、必要恢复以及正确解释语义结果所需记录 |
| 既有边界 | 无历史 Evidence／lineage 数据读写、迁移、回填或只读兼容；不据此清库、删全部历史表或改写旧验收结论 |

采用当前部署合同的一次性切换，不新增 Project／角色级证据模式或双轨 API。代码中仍可
存在未被生产入口调用的历史实现、空列和旧迁移，它们不构成启用能力；新主流程不得依赖它们。
后续若发现无法通过局部拆分保持写入、授权或恢复正确性的冲突，记录具体调用和失败，
通过 PushPlus 提醒用户裁决；普通字段调整与实现拆分由开发处理。

## 2. 当前依赖与改动边界

以下是本次定向代码核对结果，不是已完成的修改或全量图影响分析。

| 链路 | 当前实现事实 | 设计处理 |
| --- | --- | --- |
| 候选输入 | [普通候选合同](../../../modeling_team/references/platform-neutral-candidate-authoring.json)公开 `evidence_citations`；[staged_decisions.py](../../../modeling_team/staged_decisions.py)对值结论、统一候选和审批定义 `evidence_refs`，部分要求非空 | 删除来源追溯专用字段及对应必填检查，保留语义、未知、确认和内容版本绑定 |
| 角色与运行组装 | [Modeling 指令](../../../modeling_team/agent-packages/modeling/instructions.md)、[Protocol 指令](../../../modeling_team/agent-packages/protocol/instructions.md)、[Runner](../../../modeling_team/runner.py)及真实 Task 共同下发要求 | 同步修改最终加载链，不靠尾部追加“忽略旧要求” |
| 写入 | [modeling_batches.py](../../../backend/app/services/modeling_batches.py)生成证据计划、缺证 warning、Evidence 与 Association；[canonical REST](../../../backend/app/api/semantic.py)另有内联解析和关联入口 | 两条写入口一起解除依赖；保留真实事务、回执与审批绑定 |
| 普通检索 | [semantic_context_query.py](../../../backend/app/services/semantic_context_query.py)逐项调用 `get_lineage`，包括 compact 投影；[semantic_read_model.py](../../../backend/app/services/semantic_read_model.py)查事实证据表并形成治理门 | 删除查询与装饰链及缺证门，不仅删除最终 JSON 字段 |
| Protocol 完成 | [protocol_retrieval_gate.py](../../../modeling_team/protocol_retrieval_gate.py)要求 `supported`、非空证据 ID 和完整 lineage | 保留 scope、真实读回、谓词和值匹配、分页完整性；撤去追溯条件 |
| 对外入口 | [REST 注册](../../../backend/app/api/routes.py)、[MCP 注册](../../../backend/app/mcp/tools/__init__.py)、[工具目录](../../../backend/app/api/mcp_catalog.py)分别维护入口 | 三者与 Runner 私有 capability 同步撤下专用能力 |
| 自动记录 | [canonical write](../../../backend/app/services/semantic_canonical_write.py)、[直接编辑与旧推理入口](../../../backend/app/services/semantic.py)、[推理](../../../backend/app/services/semantic_reasoning.py)、[规则](../../../backend/app/services/semantic_rule_execution.py)调用 lineage recorder | 停止 asserted／derived occurrence、origin、premise 采集和纯证明计算 |
| 恢复 | [checkpoint_data.py](../../../backend/app/services/checkpoint_data.py)当前复制追溯表、重映射 occurrence 身份 | 新快照移除纯追溯数据；保留业务资料、语义数据、保护集、回执及新项目身份重映射 |
| 前端 | 导航、事实、治理、构建、实体／检索页面及共享类型含证据展示或请求 | 删除专用 UI 与请求；保留共享页面及错误、过期、截断状态 |

### 2.1 必须保留的共享机制

1. **身份与业务关联**：资源 IRI、statement／fact ID、Project／Ontology、源图、
   asserted／inferred／rule-derived 区分；数据库字段映射、参数来源、规则输入输出及规则身份。
   `semantic_lineage_identity.py` 的 canonical term 和 statement ID 函数继续使用，
   不因模块名称而删除或为改名另建抽象。
2. **写入确定性**：Batch／Attempt、client item 映射、delta、content／projection digest、
   dry-run 与 apply 的一致性、翻译批准、资源输出、版本、锁、lease、write fence、
   幂等、unknown reconciliation、清理及恢复回执。
3. **结果有效性**：[semantic_derived_state.py](../../../backend/app/services/semantic_derived_state.py)
   按图 revision／source signature／result pointer 处理过期；
   [semantic_read_scope.py](../../../backend/app/services/semantic_read_scope.py)据 pointer 定位有效结果。
   这些机制不依赖完整 statement lineage，全部保留。
4. **授权**：[semantic_access.py](../../../backend/app/services/semantic_access.py)对资源身份、
   statement 各位置、映射和嵌套引用执行过滤；保护集及 Graph Set 的 scope 检查保留。
   停用追溯不得改变既有 `forbidden`、无痕授权子集、过滤先于分页和计数的合同。
5. **实际执行和独立验收记录**：宿主保存工具响应、CQ exposure、审批、运行事件、冻结题池、
   Examiner read handle 和 Judge 判定；这些不是平台 Evidence 资源，不删、不要求 Modeling 整理。

特例：`semantic.py` 中 `_lineage_delta_from_edit` 同时供 `validate_operation_delta` 使用。
必须保留这条校验调用；仅为 occurrence 对账执行的前后全图 snapshot、差分与
`_reconcile_missing_active_occurrences` 可随追溯采集撤下。不能按函数名前缀批量删除。

## 3. 建模与交接合同

### 3.1 输入与候选

复用现有 staged／unified／CQ Runner 和角色职责。实施时新增一个有界 v4 Task，复用
[完整 v3 Task](../../../modeling_team/tasks/r3-0-006-real-full.yaml)的运行链和
[CQ profile](../../../modeling_team/profiles/r3-0-011-competency-question.yaml)的角色配置，
但仅挂载修订后的活跃合同；不再把旧证据要求带入 v4。Task 不是授权凭据。
现有综合 reference 若混有 Modeling 语义字段与 Protocol 执行字段，按既有 `role_sources`
提供各自所需的静态 reference；Modeling 不加载读回 proof／平台证据合同。
只拆实际存在的职责混杂，不新增通用提示生成或合同编译框架。

| 产物或字段 | 新合同 |
| --- | --- |
| 普通候选 `evidence_citations` | 从允许字段、例子、翻译器和 JSON Schema 删除；不保留可选空数组 |
| unified 候选 `evidence_refs` | 删除；`business_meaning`、`value`、`relation_endpoints`、切片／共享范围和 `unknowns` 保留 |
| 值语义结论 `evidence_refs` | 删除；假设、未知、状态、业务确认人、确认值／层级与修订保持；不可从样例自动确认业务含义 |
| 审批 decision `evidence_refs` | 删除；目标、决策、理由、范围、候选 revision／digest 保留；理由不要求来源引用 |
| identity binding 的 `receipt_ref`／`evidence_ref` | 保留其现有“写回执／平台读回”用途，由 Protocol／宿主负责；不作为来源证据字段下发给 Modeling |
| 平台执行与 CQ 交接中的 `evidence_ref`／`evidence_handle` | 保留实际工具响应定位，继续校验 scope、request／response digest；不改造成来源追溯包 |
| 联合清单中要求平台 Evidence 覆盖的检查 | 移除追溯判据；保留业务覆盖、语义缺口与真实执行状态，不用固定全量清单阻塞有界 CQ 交接 |

涉及字段集合改变的持久产物和 references 必须更新各自 schema version，并同步 loader、
validator、digest builder 和实际挂载；不让同一版本在不同地方表示两种字段集合。
仅对形状确实改变的合同升版；没有改变的提交回执、CQ、身份绑定和检查点宿主合同不机械升版。
不得静默丢字段后复用旧审批或旧 dry-run：新候选需重新产生内容摘要和同内容批准。
旧产物及已保留 run 文件原样留存，不增加旧追溯合同到新合同的转换层。

### 3.2 Protocol 与 Runner

- 正常翻译不生成 Evidence item、内联摘录、candidate-item-evidence-map 或补证任务。
  [protocol_mechanics.py](../../../modeling_team/protocol_mechanics.py)的候选翻译、
  [protocol_retrieval_mcp.py](../../../modeling_team/protocol_retrieval_mcp.py)的工具 Schema、
  [staged_decisions.py](../../../modeling_team/staged_decisions.py)的 envelope／projection 归一化同步调整，
  不再自动补 `evidence: []` 或证据 ID 数组。
- [capability_mcp.py](../../../modeling_team/capability_mcp.py)撤下
  `protocol_staged_associate_evidence`；Runner handler、
  [staged forwarder](../../../modeling_team/staged_batch_write_forwarder.py)及
  [CLI 注入](../../../modeling_team/__main__.py)撤去该路径。
  `write_candidate_item_evidence_map` 不再出现在实际工具目录，也不能通过直接 dispatch 调用。
- 普通完成门验证模型与实际平台读取是否一致。`ProtocolRetrievalGate` 不再筛掉无 Evidence
  的有效 statement；其返回路径记录删除证据 ID，继续保留 statement ID 与具体谓词／值。
- 旧 proof-v1/v2 专用实验代码不作为本次运行依赖；v4 Task 不选择它们，也不向角色暴露
  `evidence_bindings`、`statement_lineage` 等 proof-only 参数。可保留离线历史验证代码，
  不为让旧追溯实验继续运行而恢复专用工具。共享普通 readback／物化摘要检查继续有效。
- [modeling_workflow.py](../../../backend/app/services/modeling_workflow.py)及其 Schema
  移除 related resource 的 `evidence_reference`／`lineage` 类型和专用校验分支。
  CQ、Batch、Attempt、Finding、validation run、execution event 等继续可引用。
  业务问题可如实记为未知、冲突或缺失，不能用“缺平台证据”请求返工。

验收 A1 检查 Task、profile、agent package、Skill、references、Runner 动态提示及工具
嵌套 Schema 的**实际组装结果**。只检索某个文件或把所有含 `evidence` 的文本禁用均不足以证明。
历史 Task 可留存用于理解旧实验；本条不承诺调用已撤下能力的旧 Task 在新部署继续运行。
不重写其历史验收结论，活跃入口文档明确指向 v4 Task。

## 4. 后端写入及自动采集

### 4.1 Batch 与 canonical command

`ModelingItemInput` 的新公开形状：

```text
client_item_id, command_kind, payload, depends_on, rationale, competency_question_ids
```

`rationale` 仍是可选语义说明；不得变成逐资源来源举证。保留 Batch 顶层 scope、mode、
workspace version、幂等 key、lease 与现有认证主体规则。

实施修改集中于 [api/schemas.py](../../../backend/app/api/schemas.py)、Batch REST／MCP、
`modeling_batches.py` 及 Batch reference：

1. 删除公开 Evidence 输入和内联限制检查；`extra="forbid"` 保持，旧追溯专用输入按现有
   参数验证错误拒绝，不静默成功。正常业务 `payload` 不按词语屏蔽“证据”“来源”。
2. `_validate_evidence_and_questions` 只撤证据解析，保留 CQ 引用检查；删除缺证 warning。
3. dry-run operation plan 不再生成 evidence section；当前 `ModelingOperationPlanRead`
   仅包含 evidence，故删除这项纯证据公开投影，而非删除内部执行计划、delta 或 Attempt。
4. apply 不调用 `_persist_evidence`，结果、Batch 详情、modeling context、
   Build Session 汇总不再返回证据数组、候选或数量；数据库旧列可留默认空值，无须迁移。
5. canonical REST 去掉 `evidence_target_id`、引用／内联证据和关联返回，走原本无内联证据的
   正常提交路径。编译器 dispatch 撤下 `bind_fact_evidence`、`unbind_fact_evidence` 等专用命令，
   防止用通用 command 入口绕回已停用能力；非证据 command 行为不变。

失败继续按原层归因。删除 Evidence 依赖不能把 unknown 写入当作零写入，不能解除 fence、
跳过 dry-run、改变 apply_atomic 的原子范围，或把失败结果改写成成功。

### 4.2 D2 自动记录清单

| 记录或计算 | 处理 |
| --- | --- |
| Evidence Reference／Association、事实绑定 | 新写入不创建，正常读取不查询 |
| statement occurrence、origin、premise 全链 | 从 canonical、直接编辑、规则与两类推理入口停止 recorder 调用；不生成占位 origin |
| 只供 lineage 使用的 premise 解析、proof level、coarse reason、`lineage_*` metadata | 停止构造，不只过滤最终响应 |
| Edit Audit、Graph Revision、Graph State、Derived Result Pointer | 保留；公开 audit 投影移除 evidence status，实际 delta、actor、失败与版本仍可读取 |
| Rule／Reasoning／Validation Run | 保留结果、运行 ID、状态、输入图版本／source signature、结果图、截断和错误 |
| 规则结果 `rule_id`、`rule_version`、`assertion_kind` | 保留当前结果语义关联；规则组执行已在 `run_metadata.statements` 存这些字段，无须为它们保留完整 lineage |
| `semantic_lineage_identity.py` 规范化与 ID 运算 | 保留；它们也服务普通图读取和编译 |
| 宿主 `evidence/` 目录、审批／Attempt proof、验收 read handles | 保留技术和验收记录，目录名称不作为删除依据 |

规则组执行的 `_finalise_run` 会把 statement metadata 存入 run 并从运行查询返回。
因此必须在构造 statements 时去掉 `lineage_premises`、`lineage_proof_level` 和纯追溯
`lineage_origin_metadata`，不能只停 SQL recorder。`rule_id`／版本和实际输出继续记录。
DSL 的运行 bindings 若服务结果解释可保留，不额外生成逐 statement premise 链。

历史 SQLAlchemy models、迁移与无活动调用的 repository 暂不要求物理删除。本次验收检查
新运行未增加上述纯追溯记录，避免“入口隐藏但后台照常采集”。

## 5. 读取、接口与前端

### 5.1 正常读取合同

| 位置 | 删除 | 保留 |
| --- | --- | --- |
| Context Query 默认／compact／精简关联投影 | `evidence_reference_ids`、`evidence_status`、`lineage`、证明等级、依赖证据状态、缺证／链不完整 warning | ID、target kind、Ontology／图、谓词方向和值、自然语言说明、业务映射、assertion type、真实完整性和过期状态 |
| Fact／资源 read model | `evidence_ids`、`evidence_bindings`、缺证筛选、证据装饰查询 | fact ID、完整 RDF term、图定位、审阅状态、`derived_from.run_id` 和 stale 信息 |
| 治理／构建／工作区摘要 | 缺证数量、覆盖率、missing-evidence gate、证据列表游标 | 未决写入、校验、推理、索引、租约、恢复和已知业务缺口 |
| 检索命中解释 | 不删除 `label_evidence`、`mapping_evidence`、多表达式匹配 tier | 它们解释词语或映射命中，不表示来源证据充分 |

Context Query 不再构造／调用 `OntologyLineageService`。`derived_state` 保留
`kind/status/run_id`，移除 `proof_level/dependency_evidence_status`。
原有 source graph、resource／statement 区别不得丢失；生成 Shape 的合成 ID 仍不能冒充真实事实。
需要同时检查索引／模板投影，避免 [semantic_search_projection.py](../../../backend/app/services/semantic_search_projection.py)
或 [semantic_sparql_templates.py](../../../backend/app/services/semantic_sparql_templates.py)重新填回追溯字段。

撤去事实读取的 `kind=missing_evidence`、`field_set=evidence`、`include_evidence` 选项及工具说明。
普通 fact 查询仍可用；被移除的专用选项返回既有参数错误，不转换成成功空结果。
`provenance` 容器若仅承载图、run、scope 定位则保留所需子字段，不保留完整来源／前提链。
业务资料未支持某含义时依然报告未知或语义错误，不用 Evidence 缺失状态代替语义判断。

### 5.2 专用入口撤下

REST 从当前注册处移除下列路由族（均位于 `/api` 下）：

- `evidence.py`：project evidence artifacts、artifact 详情／chunks、单 chunk。
- `evidence_references.py`：project references 的创建／列表／resolve、单 reference、
  reference associations、project associations 查询／创建／batch。
- `fact_evidence.py`：Graph Set fact-evidence 创建／删除与 missing-evidence-facts。
- `ontologies.py`：`/ontologies/{ontology_id}/lineage`；保留其他 Ontology 路由。

MCP 撤下 `create_evidence_reference`、`list_evidence_references`、`get_evidence_reference`、
`associate_evidence_reference`、`get_ontology_lineage`、`inspect_semantic_statement_provenance`。
同步移除 `register_evidence`、静态目录中的证据文件项、任务 allowlist 和 Runner 补证 capability。
共享 semantic 工具其余部分保留。

不存在的 REST 路由按框架未提供合同处理；普通已认证调用验收预期为 404，认证中间件先拒绝
的请求仍遵守其原合同。MCP／Runner 调用按既有 unknown-tool／unknown-capability 机制失败。
不新增 410 兼容 handler，不成功返回空列表，不增加停用模式配置。

### 5.3 UI

修改 [App.tsx](../../../frontend/src/App.tsx)、[types.ts](../../../frontend/src/types.ts)、
[semanticApi.ts](../../../frontend/src/semanticApi.ts)及页面消费合同：

- 移除 Evidence tab／页面加载、创建绑定、Fact 的证据抽屉／缺证筛选、实体与结果的证据徽标。
- GraphGovernance 和 BuildContextDebug 移除纯证据指标、追溯展示和空占位。
  治理页继续展示校验失败、stale、未结清写入；构建页继续展示租约、Batch 和恢复状态。
- 旧 Evidence tab 状态回到已有默认页面；不新建历史或停用说明页面，不发起已撤下请求。
- 翻译文案和前端 fixtures 同步；通过浏览器请求记录证明共享页面不再调用专用入口。

## 6. 检查点、数据与版本切换

新 checkpoint 数据格式移除 Evidence Artifact／Chunk／Reference／Association、
FactEvidenceBinding 和 statement occurrence／origin／premise 的采集与恢复分支。
相应表仅空着不是保留历史兼容的理由。访谈、Project Brief、CQ、映射、规则、保护集、
图与版本、已应用 item 索引继续纳入快照。

`SNAPSHOT_SCHEMA` 升版，capture／fork 同步采用同一新格式；旧格式按既有不支持格式错误拒绝，
不伪造转换或从当前库补齐。宿主 checkpoint 的授权、摘要、freeze、文件完整性和原地接续流程
保持职责；本条验证停用后新建 run 的保存／接续／fork，不以旧追溯快照兼容为完成条件。
新格式仍保留以下恢复保证：

- 先锁 Ontology 再建立 repeatable-read 快照；在途／unknown 写入不能绕过 capture barrier。
- fork 预分配 Project／Ontology 身份、重映射图与语义资源引用、恢复保护集及已应用记录。
- COMMIT 响应丢失保留 pending 和目标图，不能作为失败清空；源封存规则保持。
- 新项目重算派生／检索状态，旧审批和写授权不复用；旧 run 和保留文件不改写。

实现代码、Agent 合同和前端作为同一部署增量切换；本设计不执行部署，也不处理任何活动 run。
部署前核实有无在途写入，不能把正在执行旧合同的 run 热切换到新形状。若确有活动 run，
先报告状态和可行的切换时机，不静默停止或清理它。

## 7. 实施顺序与交付检查

以下是本需求内部工作拆分，不是新增需求，也不建立独立编排框架。

| 顺序 | 工作包 | 可核对产物 |
| --- | --- | --- |
| S1 | 去掉后端公开字段、Batch／canonical 证据路径和专用入口；保留事务／授权边界 | 无 Evidence 的 dry-run／apply／读回成功；专用调用不可用 |
| S2 | 切断普通读取追溯装饰和自动采集；调整新 checkpoint 格式 | 全部响应投影无追溯字段；真实新写入／推理不增加追溯记录；恢复可用 |
| S3 | 同步候选、staged 审批／结论、Protocol、capability、提示和 v4 Task | 实际组装无补证要求；正常 readback 与 handoff 可闭合 |
| S4 | UI、接口文档、术语适用范围及活跃入口文档同步 | 页面无专用请求；公开合同和实际注册一致 |
| S5 | 完成必需回归、重启与运行检查，再按新授权开展有界真实建模及独立验收 | 分别记录 L0 和 L1；缺 L1 则保持 PARTIAL |

S1—S4 的改动必须整体验证后进入运行环境，不能以半套新后端配旧 Agent 的失败推断建模质量。
实现前按实际修改符号做 GitNexus impact；HIGH／CRITICAL 先提示用户。若图不可用或失真，
按仓库规则用具体调用点和 diff 核对并披露。本文只做定向代码检查，不声称图覆盖或独立评审。

本轮不提前修改当前 [REST 文档](../../reference/api.md)、[MCP 文档](../../reference/mcp.md)
或工具目录来伪装入口已撤下。实现时运行既有 `scripts/sync-interface-docs.py` 的同步／检查路径，
并更新 [glossary](../../reference/glossary.md)的 v4 适用范围；旧需求与历史报告不改写。

## 8. 验证设计与完成边界

复用现有 backend、Team、Playwright 和独立 CQ 路径。新增测试验证行为及反例，
不新建只匹配一次输出的语义裁判。

| 需求验收项 | 必需验证 | 关键反例／结果 |
| --- | --- | --- |
| A1 输入 | 捕获真实配置组装的各角色指令、挂载 reference、工具目录与嵌套 Schema；检查相关动态反馈 | 不存在追溯专用字段或补证职责；业务资料和宿主读回引用仍可用 |
| A2 写入 | 无证据候选翻译后经真实平台 dry-run、同内容 apply、读回、handoff；检查 SQL 行增量 | 无缺证 warning，无 Evidence／Association／fact binding；篡改投影或失效批准仍拒绝 |
| A3 读取 | Context Query 各投影、资源／事实、构建／治理与关联读取；将 lineage／证据 repository 查询设为测试失败点 | 正常读仍成功，无隐含追溯查询；没有虚构 `supported/complete` |
| A4 正确性 | 受限 IRI／映射、分页截断、结果过期、真实业务未知；运行规则并读取输出及规则身份 | forbidden、过滤、游标和 stale 不退化；未知仍可见；不把无追溯当无规则 |
| A5 入口 | REST route、MCP tools/list、目录、Runner 私有目录及直接调用；通用 command 的证据命令反例 | 专用能力和别名不暴露且不能执行；无历史只读替代路径 |
| A6 UI | 导航、实体、Facts、查询、治理、构建浏览；监控请求；检查旧 tab fallback | 无证据入口、指标或空卡片；共享功能和正常告警仍有效 |
| A7 运行完整性 | 真实 PostgreSQL／RDF 写入、规则／推理、拒绝后重试、unknown、停用后新快照原地接续／fork | 纯追溯表零增量；原子性／幂等／fence／COMMIT 不确定处理不变；snapshot 无追溯表，业务与授权恢复正确 |
| A8 独立语义 | 有界真实建模后由独立 Examiner／Judge 查询并核对获准资料 | Agent 不留存／补齐平台 Evidence；源忠实、业务关系、规则／映射和未知按实际含义判定 |

回归优先复用 `test_modeling_batches*`、`test_semantic_context_query*`、
`test_semantic_read_model*`、`test_semantic_access*`、`test_semantic_derived_state.py`、
`test_checkpoint_data*.py`、Team 的 `test_translate_candidate_to_batches.py`、
`test_r30008b_staged_decisions.py`、候选／检索／交接测试和现有前端页面测试。
追溯专用的旧测试改为入口停用断言或保留为明确的离线历史实现测试；不得大范围 skip
以掩盖共享逻辑回归，也不继续用旧“必须有证据”断言要求补回功能。

实现后的仓库必需命令：

```bash
cd backend
uv run pytest
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests
```

```bash
cd frontend
npm run build
npx playwright test
```

新 checkpoint 的真实依赖测试复用 `test_checkpoint_data_live.py`；其 fixture 先按新合同更新，
不能把旧非空 lineage fixture 当本期恢复要求。机制测试可故障注入，不能代替真实依赖检查。
完成必需测试后重启 `ontology-platform.service`，检查 active、backend `8001/api/health`、
frontend `5173/` 及受影响接口。相关 Skill 若改变，运行其现有 validator。

### 8.1 首轮真实场景

建议复用工业售后材料中的一个有界切片：工单／设备对象、已确认的状态或业务规则、
数据库标识及字段映射，形成对象—规则—数据映射的关联问题；加入一处业务未知和一处
受限语义读取。仅使用已支持表达，不等待 R4.0-002—011 全部实现，也不预先实现新 Action
或流程绑定方案。本条验证去除追溯后现有建模链能否产出正确可消费语义。

实际资料范围、公开／隐藏 CQ 由既有访谈和冻结流程形成，不把本设计里的预期答案下发给建模方。
验收方不创建、继续或修复被验收 run，不改保留记录；可用真实查询和获准资料说明判定，
但不向 Modeling 转交补证任务。L0 与 L1 分开记录，A1—A7 不能替代 A8。

启动须另有真实建模授权；获准后复用已有路径，在 20 分钟内开始首次 semantic start，
不再前置全面审计或重建 harness。记录轮次、run ID、额度和各类有效时间；优先安全恢复
同一 start。额度不足或需新的业务／范围决策时，通过 PushPlus 提醒用户，不自行追加。

## 9. 详细设计形成时的结论与未验证事项

- D1／D2 已闭合，没有新增待用户裁决的产品决策；具体实现按以上边界推进。
- 详细设计形成时仅完成设计；当时实际接口停用、提示组装、读写／恢复回归以及 L1 均未执行。
- 本轮文档检查证明文件链接、需求决策状态及设计映射一致，不证明实现或真实建模通过。
- 后续完成实现和相关验证后，再依据 A1—A8 更新需求状态；未经独立语义验收不标记完成。

本轮文档验证（2026-10-01）：两份变更文档的相对文件链接、锚点、代码围栏与表格格式检查通过；
需求中 D1／D2 的待确认文字已同步，F1—F7 和 A1—A8 均有设计落点；`git diff --check` 通过。
详细设计阶段未修改 executable code 或 Skill，因此该阶段未运行后端／前端测试、未重启服务。

## 10. 实现与独立功能验收（2026-10-01）

实现按本设计覆盖 Team 实际合同、REST／MCP、正常读写、纯追溯采集、checkpoint 与 UI，
未增加历史追溯兼容或模式开关。独立 Round 1 发现导出旧参数静默成功、动态提示残句及
测试清理 actor 错配；修复后 Round 2 判定 A1—A7 功能 PASS，三项均 FIXED，无回归。

最终后端全量 1011 PASS／38 既有 SKIP；Team 全量 2022 PASS／1 既有 SKIP，
后续提示修复的定向回归通过；前端构建和 39 项浏览器测试通过。真实 PostgreSQL／RDF／HTTP、
checkpoint／fork、重启健康与自有资源清理均有开发及独立证据。详见
[测试记录](../test-plans/2026-10-01-r4-0-012-tracing-suspension-test-plan.md)及
[交付记录](../records/2026-10-01-r4-0-012-tracing-suspension-delivery-record.md)。

A8／L1 尚无真实 semantic start 授权，本轮额度消耗 0，未产生真实语义质量结论。
需求整体保持 PARTIAL；后续获得授权后复用第 8 节路径，不将功能 PASS 当作语义验收。
