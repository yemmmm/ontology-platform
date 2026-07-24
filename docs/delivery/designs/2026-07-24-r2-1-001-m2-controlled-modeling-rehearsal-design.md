# R2.1-001 M2 受控建模流程演练执行设计

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M2
- Status: implemented and independently accepted
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Shared test plan:
  `docs/delivery/test-plans/2026-07-24-r2-1-001-m2-controlled-modeling-rehearsal-test-plan.md`

## Goal

由主 Agent 在受控条件下，使用未来自主建模 Agent 将使用的正式平台入口，重新完成 M1 的
Workflow-as-Tool 变更影响建模任务。演练必须暴露并记录工具合同、dry-run 反馈、修正、apply 和
应用后语义验证，不以复制 M1 Turtle 或 RDF 图同构作为成功标准。

## Confirmed contract

- 输入固定为 M1 不可变资料包、合成 C -> B -> A Fixture、语义问题和行为验收。
- 使用全新的 Project、Ontology、Build Session 和 Evidence References。
- 常驻 `ontology-platform.service` 保持 `legacy_only`；经用户确认，演练使用临时隔离的
  `rdf_primary` 后端，不持久修改常驻服务配置。
- 最终候选只通过 Modeling Batch `dry_run` 和 `apply_atomic` 写入。
- 不调用 `POST /api/semantic/edits`、`datasets:load`，不直接写数据库/RDF Store，不使用
  `validate=false`，不添加 Dify 专属 API、Schema、转换器、查询分支或解释逻辑。
- M2 保留 Project 及其运行证据供独立测试和 M3 交接；只有确认不再需要时才清理。

## Model adaptation within existing generic commands

M2 不复制 M1 IRI 或 Turtle。候选使用平台分配的通用资源 IRI，并通过现有 Modeling Command
表达同一语义行为：

1. Class：
   `ModeledComponent`、`PublicationStateBearing`、`Workflow`、`WorkflowVersion`、
   `PublishedWorkflowVersion`、`WorkflowTool`、`ToolInvocation`、`Variable`、
   `VariableBinding`、`VariableUse`、`ChangeSet`、`ExplicitGapComponent`。
   `PublishedWorkflowVersion` 是 `WorkflowVersion` 子类，用于可执行 RDFS 推理。
2. Object Property：
   `hasVersion`、`versionOf`、`activeLatestVersion`、`hasInvocation`、`invokesTool`、
   `toolTargetsVersion`、`bindingAtInvocation`、`bindingSource`、`bindingTarget`、`hasUse`、
   `usesVariable`、`producesVariable`、`derivedFromVariable`、`declaredByVersion`、
   `changeAppliesToVersion`、`deletesVariable`、`previousVersion`。
   这些需要被 Shape 约束的对象谓词全部使用 `create_property(object_class_id)` 创建，并由
   Fixture 的 `create_relation.relation_type_iri` 引用同一个 `/property/{id}` IRI。不得用
   `create_relation_type` 生成 `/relation-type/{id}` 后再让 Shape 的 `path_id` 指向同名
   `/property/{id}`。
3. Datatype Property：
   `publicationState`、`completeness`、`unknownDetail`、`variableName`、`dataType`、
   `variableRole`、`useKind`、`callSiteId`、`callSiteLocation`、`sourceKind`。
4. Shape：
   使用 target-Class、`min_count`、`max_count` 和 `pattern` 验证 Version、Published Version、
   Invocation、Binding、Use、Change 和 Explicit Gap。`ExplicitGapComponent` 必须带
   `unknownDetail`，从而把未知项建模为显式事实。
5. Fixture：
   使用 `create_entity` 建立带文字字段的资源，使用 `create_relation` 建立对象关系。官方资料、
   合成 Fixture 和 Agent 建模理由使用不同 Evidence，并在批次 Item 上关联。

`sh:sparql`、`sh:targetSubjectsOf` 和 `rdfs:subPropertyOf` 不在当前结构化命令合同内，因此 M2
不依赖这些表达。固定验收关注语义行为，不要求与 M1 的 RDF 图同构。

## Execution sequence

1. 探测常驻服务模式，启动临时隔离的 canonical 后端并再次探测模式。
2. 创建 Project、Ontology、Build Session，登记官方来源与合成 Fixture Evidence。
3. 提交一个故意错误的 Shape dry-run，确认平台返回可定位的阻塞反馈；修正后继续。
4. TBox/Shapes 批次依次 dry-run、获取 lease、apply。
5. 已发布 C -> B -> A Fixture 批次 dry-run、apply。
6. Current Draft 与 Explicit Gap Fixture 分别 dry-run、apply。
7. 无效 Invocation 只做 dry-run，必须被既有 Shape 拒绝，绝不 apply。
8. 读取 Graph Set，取得角色为 `shapes` 的唯一成员 IRI，将它显式传给 validation；不得依赖当前
   默认解析所查找的单数 `shape` 角色。演练日志必须同时保存 Graph Set member、validation 请求
   和返回的 run ID/status。正式 run 读接口用于复核状态、Graph Set 和 source signature；由于
   当前公开读模型不返回已持久化的 `shape_graph_iris`，独立测试另用仓库内只读 ORM 检查精确
   断言该字段，禁止任何数据库写入。随后执行 reasoning，并用 scoped SPARQL 验证发布、草稿、
   完整上下文和显式未知。
9. 使用一个已知缺少 `invokesTool` 的 Invocation 做隔离 dry-run/候选验证并确认 Shape violation，
   证明 validation 成功不是空 Shape 图造成的假通过；该无效候选永不 apply。
10. 导出批次/运行证据，追加演练日志，形成不含隐藏状态的最小操作清单。
11. 独立测试完成后停止临时后端，确认常驻服务仍为原模式且前后端健康。

## Failure behavior

- `legacy_only`：仅在隔离实例使用已支持配置启用 `rdf_primary`，不修改常驻服务。
- dry-run 校验错误：记录 Batch、Item、finding、修正与后续结果；使用新的不可变 Batch/
  idempotency key，不覆盖失败历史。
- 工作区版本冲突或 lease 过期：重新读取 Modeling Context，按正式 API 更新版本/lease 并记录。
- 现有命令无法表达固定验收语义：立即停止 M2，作为独立通用平台需求细化并取得用户确认。
- apply 后 validation、reasoning 或查询失败：保留 Project 和运行证据，进入开发/测试缺陷循环；
  不使用 RDF 旁路修复。

## Acceptance

- Evidence -> dry-run -> 反馈修正 -> apply -> validation/reasoning/query 正式链路完整通过；
  正式请求显式使用 Graph Set 的 `shapes` member，独立只读检查证明 run 持久化了同一 IRI。
- 已发布删除返回 B、A 和完整 C -> B -> A 调用、Binding、变量使用上下文。
- Current Draft 与 active Latest 明确分离。
- 无效 Invocation 被已应用 Shape 的隔离 dry-run 拒绝，证明不是空 Shape 假通过；Explicit Gap
  返回 `unknownDetail`。
- `PublishedWorkflowVersion -> WorkflowVersion` 推理可验证且不改变平台/Agent责任边界。
- 每轮关键失败可追踪；最小清单可直接交给 M3；无旁路和 Dify 专属平台改动。

## Validation evidence boundary

`SemanticValidationRunModel` 已持久化 `shape_graph_iris`，但当前 REST/MCP run 读模型没有返回该
字段。M2 不为测试便利扩展平台 API。执行与 M3 清单只使用正式入口，并通过显式请求参数、Graph
Set member 和已知违规拒绝证明 Shape 生效；独立测试使用场景包内的只读验证脚本查询该 run row，
只断言 `shape_graph_iris == [expected_shapes_member]`，不更新、插入或删除任何数据。

## Implementation result

受控演练在隔离 `rdf_primary` 后端完成。首轮保留了跨 Batch `item_ref` 失败，修正后第二轮通过
完整 Evidence -> dry-run -> feedback -> apply -> validation/reasoning/query 路径。独立测试
复核了成功与失败 Project、同一 Shapes 负例、精确 Shape 图持久化、四组 scoped 查询和全部聚焦
回归测试，结论为 PASS。常驻服务保持 `legacy_only`，未修改产品代码或引入 Dify 专属能力。
